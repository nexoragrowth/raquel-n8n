# -*- coding: utf-8 -*-
"""v7_workflow_cerebro.py — workflow "v7 Cerebro" con ORQUESTADOR + SUB-AGENTES (08/10). Recibe {phone, texto, pushName, modo, historial_json} y devuelve
{texto, enviar, silencio, derivar_triaje, triaje, ...} (mismo contrato que el agente único: el adaptador del v6 no cambia).

Orden (docs/v7-orquestador-subagentes-2026-10-08.md §1 y §8):
  1. Lecturas (código): historial, recordatorios, datos del consultorio, identificar paciente (ver_turnos), confirmación guardada.
  2. "Armar contexto" (código): un único CONTEXTO para todos (sin desvíos por regex: no hay IF de cierre, saludo ni "sí directo").
  3. ORQUESTADOR (IA, UNA llamada, salida JSON): qué agentes y/o qué acción fija.
  4. "Despacho" (código): una llamada por sub-agente; ruteo por ESTADO a Turnos si hay una confirmación pendiente que el paciente vio.
  5. Sub-agentes (workflows): Turnos → Pagos → Información → [Urgencias, si el orquestador o un sub-agente la vio].
  6. "Reunir" (código): fuera de alcance → derivar a la secretaria (una vez, por código); pidió una persona → modo humano; no se entendió 2 veces → derivar.
  7. "Salida" (código): compone en orden fijo con los textos de las herramientas, verifica la parte de Turnos contra la agenda, pega los datos bancarios,
     avisa al grupo y guarda memoria SOLO con modo === 'vivo'.
Los ids de los workflows se resuelven al crearlos en n8n (marcadores @@ID:<clave>@@)."""
import json

from v7_lib import V7, Grafo

GRUPO = "https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo"
PROMPT_ORQ = (V7 / "prompt_orquestador.md").read_text(encoding="utf-8").strip()
SQL_HISTORIAL = "SELECT message, created_at FROM n8n_chat_histories WHERE session_id = $1 ORDER BY id DESC LIMIT 30"
SQL_RECORDATORIOS = ("SELECT id_cita_dentalink, fecha_turno, hora_turno FROM recordatorios_enviados WHERE telefono = $1 AND confirmado_at IS NULL AND cancelado_at IS NULL "
                     "AND fecha_turno >= (now() AT TIME ZONE 'America/Argentina/Jujuy')::date ORDER BY fecha_turno, hora_turno")
# Datos del negocio para INFORMACIÓN (la KB 24 bancaria la lee solo el código de la Salida: ningún modelo ve el alias ni el CBU).
KB_EXTRA = ["45", "41", "29", "30", "37", "42", "44", "3", "22", "23", "1", "26", "28", "43", "32", "33"]
# (20/10, BOT-06) KB 40 = presentación para los leads de anuncio (la que mandaba el v6 con "¡Hola! Quiero más información"): la pega el CÓDIGO tal cual.
# (20/10, panel "Conocimiento") Además de los ids fijos, las entradas que la clínica marcó en el panel "Asiri puede decírselo a los pacientes"
# (metadata.asiri = true, no archivadas): hasta KB_ASIRI_MAX, cada una recortada a KB_ASIRI_LARGO caracteres, como DATOS de Información.
KB_ASIRI_MAX, KB_ASIRI_LARGO = 12, 600
SQL_DATOS = ("SELECT id::text AS id, contenido FROM knowledge_base WHERE id IN (20, 21, 24, 25, 36, 39, 40, " + ", ".join(KB_EXTRA) + ") UNION ALL "
             "(SELECT 'asiri:' || id::text AS id, left(contenido, " + str(KB_ASIRI_LARGO) + ") AS contenido FROM knowledge_base "
             "WHERE metadata->>'asiri' = 'true' AND coalesce(metadata->>'archivado', '') <> 'true' AND id NOT IN (20, 21, 24, 25, 36, 39, 40, " + ", ".join(KB_EXTRA) + ") "
             "ORDER BY id LIMIT " + str(KB_ASIRI_MAX) + ") UNION ALL "
             "SELECT 'dir:' || clave AS id, valor AS contenido FROM agente_directrices WHERE clave IN ('notas_para_asiri', 'menu_bienvenida') OR left(clave, 4) = 'msg_' ORDER BY 1")
# (28/10) Mensajes fijos editables desde el panel: filas `msg_<CLAVE>` (ver OrquestadorCore.MENSAJES_EDITABLES). Vacío o inválido = sale el estándar.
# (20/10, D3 del plan del 13/10; escalaciones reales 380–386) ¿Quién escribió PRIMERO en este chat? Si fue la clínica y el contacto no tiene ficha,
# es una charla de la clínica (plomero, proveedor, técnico): Asiri no se mete. Es estructura (fuente del mensaje), no lectura del texto del paciente.
SQL_PRIMERO = "SELECT message->'additional_kwargs'->>'source' AS fuente, message->>'type' AS tipo FROM n8n_chat_histories WHERE session_id = $1 ORDER BY id ASC LIMIT 1"
SUBAGENTES = [("turnos", "Agente Turnos"), ("pagos", "Agente Pagos"), ("informacion", "Agente Información"), ("urgencias", "Agente Urgencias")]

E = "$('Entrada').first().json"
CTX = "$('Armar contexto').first().json"
MODO = f"{E}.modo === 'vivo' ? 'vivo' : 'sombra'"

JS_CONTEXTO = """const e = $('Entrada').first().json;
const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
let override = null; try { override = e.historial_json ? JSON.parse(e.historial_json) : null; } catch (x) { override = null; }
const filas = Array.isArray(override) ? override : $('Historial').all().map((i) => i.json).filter((r) => r && r.message);
const hist = HistorialCore.armar(filas, 12);
const msg = (f) => { let m = f && f.message; if (typeof m === 'string') { try { m = JSON.parse(m); } catch (x) { m = null; } } return m; };
const ahoraMs = Date.now();
// "Conversación nueva" es un DATO (12 h sin mensajes) que ve el orquestador; no es una compuerta.
const ultFecha = filas.length ? Date.parse(String(filas[0].created_at || '')) : NaN;
const conversacion_nueva = filas.length === 0 || (!isNaN(ultFecha) && ahoraMs - ultFecha > 12 * 3600 * 1000);
// Último mensaje de ASIRI antes del mensaje actual (si después escribió el paciente o el staff, no hay confirmación pendiente vista).
let ultimo_asiri = '';
for (const f of filas) { const m = msg(f); if (!m) continue; const c = String(m.content || ''); if (m.type === 'human' || c.startsWith('[ATENCION HUMANA')) break; if (m.type === 'ai' && c && !c.startsWith('[')) { ultimo_asiri = c; break; } }
// (21/10, corte de bucle) ¿Cuántas veces seguidas Asiri ya mandó ese mismo texto (entre mensajes del paciente)? 0 = la última fue distinta.
let repeticiones = 0;
if (ultimo_asiri) {
  const nn = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const asiri = []; for (const f of filas) { const m = msg(f); if (!m) continue; const c = String(m.content || ''); if (m.type === 'ai' && c && !c.startsWith('[')) asiri.push(nn(c)); }
  for (let i = 1; i < asiri.length && asiri[i] === asiri[0]; i++) repeticiones++;
}
// Mensajes del paciente de las últimas 12 h (+ el actual): gestionar_turno verifica que el DNI que copió el modelo lo escribió el paciente (I3/8 de la crítica).
const textos_paciente = filas.filter((f) => { const m = msg(f); const t = f && f.created_at ? Date.parse(String(f.created_at)) : NaN; return !!m && m.type === 'human' && (isNaN(t) || ahoraMs - t < 12 * 3600 * 1000); })
  .map((f) => String(msg(f).content || '')).concat([String(e.texto || '')]);
// (21/10) una entrada por cita (la tabla puede traer la misma cita dos veces; antes además el nodo corría por fila del historial)
const recVistas = new Set();
const rec = $('Recordatorios').all().map((i) => i.json).filter((r) => r && r.id_cita_dentalink && r.fecha_turno && !recVistas.has(String(r.id_cita_dentalink)) && recVistas.add(String(r.id_cita_dentalink))).map((r) => {
  const f = String(r.fecha_turno).slice(0, 10);
  return DIAS[new Date(f + 'T12:00:00Z').getUTCDay()] + ' ' + Number(f.slice(8)) + '/' + Number(f.slice(5, 7)) + ' a las ' + String(r.hora_turno || '').slice(0, 5);
});
// (21/10, Lucas: "si tira un recordatorio y el paciente dice que sí, de la forma que sea, se le confirma") ¿Está respondiendo a un recordatorio?
// ESTADO, no texto: hay recordatorios abiertos y el último mensaje que NO es del paciente es un recordatorio (source reminder_note).
let ultimoNoPaciente = null; for (const f of filas) { const m = msg(f); if (!m || m.type === 'human') continue; ultimoNoPaciente = m; break; }
const recordatorio_pendiente = rec.length > 0 && !!(ultimoNoPaciente && (ultimoNoPaciente.additional_kwargs || {}).source === 'reminder_note');
const kb = {}; for (const r of $('Datos del consultorio').all().map((i) => i.json)) if (r && r.id !== undefined) kb[String(r.id)] = String(r.contenido || '').trim();
const j = new Date(ahoraMs - 3 * 3600 * 1000);
const ahora = DIAS[j.getUTCDay()] + ' ' + j.toISOString().slice(0, 10) + ' ' + j.toISOString().slice(11, 16);
const datos = [kb['20'] && '- Horarios de atención: ' + kb['20'], kb['21'] && '- Primera consulta: ' + kb['21'], kb['36'] && '- Cuota mensual del tratamiento: ' + kb['36'],
  kb['39'] && '- Control de contención: ' + kb['39'], kb['25'] && '- Dirección (solo si la piden): ' + kb['25']]
  .concat(""" + json.dumps(KB_EXTRA) + """.filter((k) => kb[k]).map((k) => '- ' + kb[k]))
  .concat(Object.keys(kb).filter((k) => k.startsWith('asiri:')).sort((a, b) => Number(a.slice(6)) - Number(b.slice(6))).map((k) => '- ' + kb[k]))   // cargadas por la clínica desde el panel
  .filter(Boolean).join('\\n');
const notas = kb['dir:notas_para_asiri'] || '';
// (28/10) ¿Audio YA transcripto? Estructura, no lectura de lo que dijo el paciente: la entrada arma "[AUDIO] <transcripción>"; sin texto después no hubo transcripción.
const texto_crudo = String(e.texto || '');
const i_audio = texto_crudo.toUpperCase().indexOf('[AUDIO]');   // (28/10) en cualquier parte: el buffer de 22 s puede juntar un texto escrito antes con el audio
const audio_cuerpo = i_audio >= 0 ? texto_crudo.slice(i_audio + 7).replace(/\[MEDIA:[^\]]*\]/g, '').trim() : '';
const audio_transcripto = i_audio >= 0 && audio_cuerpo.length > 0;
// (28/10) Comprobante MARCADO por la visión de la entrada ("[IMAGEN] ... TIPO: COMPROBANTE"): estructura que arma el sistema, no texto del paciente.
const comprobante_marcado = texto_crudo.toUpperCase().indexOf('[IMAGEN]') >= 0 && texto_crudo.indexOf('TIPO: COMPROBANTE') >= 0;
const mensajes = {}; for (const k of Object.keys(kb)) if (k.startsWith('dir:msg_')) mensajes[k.slice(8)] = kb[k];   // (28/10) { NO_ENTENDI: 'texto', ... }; el core descarta lo inválido
// (B2 de la crítica) Las notas del panel cambian el TONO, nunca el alcance: Información responde solo su lista cerrada de temas.
const datos_info = 'DATOS DEL CONSULTORIO (son los únicos datos que podés dar)\\n' + (datos || '(sin datos cargados: respondé FUERA_DE_ALCANCE)')
  + (notas ? '\\n\\nNOTAS DE LA CLÍNICA (cambian el tono o la forma; nunca agregan temas ni habilitan otra cosa):\\n' + notas : '');
// Datos bancarios (KB 24): los arma el CÓDIGO y los pega la Salida debajo de la parte de Pagos o de una reserva. Ningún modelo los ve.
const datos_pago = (() => {
  const raw = kb['24'] || '';
  const campo = (re) => { const m = raw.match(re); return m ? m[1].trim() : ''; };
  return [['Alias', campo(/Alias:\\s*(\\S+?)\\.?(?:\\s|$)/i)], ['Titular', campo(/Titular:\\s*([^.]+)\\./i)], ['CUIT/CUIL', campo(/CUIT\\/CUIL:\\s*(\\d+)/i)], ['CBU', campo(/CBU:\\s*(\\d+)/i)],
    ['Nro. de cuenta', campo(/cuenta:\\s*(\\d+)/i)], ['Banco', campo(/Banco:\\s*([^.]+)\\./i)]].filter((f) => f[1]).map((f) => f[0] + ': ' + f[1]).join('\\n');
})();
// Confirmación guardada que el paciente VIO y sigue vigente: estado (Redis + último mensaje de Asiri), no lectura del texto del paciente.
let propE = null; try { propE = JSON.parse($('Redis GET propuesta (entrada)').first().json.prop_entrada_raw || 'null'); } catch (x) { propE = null; }
const prop_pendiente = !!(propE && propE.enviada === true && AgendaCore.pendienteVista(propE, ultimo_asiri, new Date(ahoraMs).toISOString()));
let ident = {}; try { ident = $('Identificar paciente').first().json || {}; } catch (x) { ident = { ok: false, motivo: 'sin_respuesta' }; }
// (20/10, D3) Charla que inició la CLÍNICA con un contacto SIN ficha (plomero, proveedor, técnico): Asiri no responde ni deriva. Solo con
// los dos datos seguros: el primer mensaje guardado es del staff y Dentalink dijo "no hay ficha con este celular" (no un error de consulta).
let primero = null; try { primero = $('Primer mensaje').first().json || null; } catch (x) { primero = null; }
const charla_de_la_clinica = !!(primero && primero.fuente === 'wa_outbound') && ident.ok !== true && ident.motivo === 'sin_ficha';
const contexto = HistorialCore.mensajeAgente(hist, e.texto, ahora, rec, e.pushName || '', ident,
  { conversacion_nueva, confirmacion_pendiente: prop_pendiente ? { texto: propE.readback_text, minutos: Math.max(0, Math.round((ahoraMs - Number(propE.creada_ms || ahoraMs)) / 60000)) } : null });
return [{ json: { contexto, sistema_orq: PROMPT_ORQ, datos_info, datos_pago, menu: OrquestadorCore.menu(kb['dir:menu_bienvenida'] || ''), anuncio: kb['40'] || '', consulta: kb['21'] || '', mensajes, audio_transcripto, cita_audio: audio_cuerpo.slice(0, 300), comprobante_marcado, charla_de_la_clinica, recordatorio_pendiente, ultimo_asiri, repeticiones, conversacion_nueva, prop_pendiente,
  textos_paciente: JSON.stringify(textos_paciente.slice(-20)), turnos_json: JSON.stringify(ident && ident.ok === true && Array.isArray(ident.turnos) ? ident.turnos : []),
  hist_n: hist.length, rec_n: rec.length, con_notas: !!notas } }];"""

JS_DESPACHO = """const ctx = $('Armar contexto').first().json;
let o = {}; try { o = $('Orquestador').first().json || {}; } catch (x) { o = { error: 'sin salida' }; }
return [{ json: OrquestadorCore.despachar(o, { prop_pendiente: ctx.prop_pendiente === true, charla_de_la_clinica: ctx.charla_de_la_clinica === true, recordatorio_pendiente: ctx.recordatorio_pendiente === true, audio_transcripto: ctx.audio_transcripto === true, cita_audio: ctx.cita_audio || '', comprobante_marcado: ctx.comprobante_marcado === true }) }];"""

JS_RES = """const r = (n) => { try { const x = $(n); return x.isExecuted ? (x.first().json || null) : null; } catch (y) { return null; } };
const res = { turnos: r('Agente Turnos'), pagos: r('Agente Pagos'), informacion: r('Agente Información'), urgencias: r('Agente Urgencias') };
// Un sub-workflow que se cayó (continueOnFail) devuelve {error}: cuenta como error técnico de ese agente.
for (const k of Object.keys(res)) if (res[k] && res[k].error && !res[k].agente) res[k] = { agente: k, estado: 'error', error_tecnico: true, texto: '', herramientas: [], traza: [] };
"""

JS_VER_URGENCIA = JS_RES + """return [{ json: OrquestadorCore.urgenciaPendiente($('Despacho').first().json, res) }];"""

JS_REUNIR = JS_RES + """const n = r('Redis INCR noentendi'); const noentendi_n = n ? Number(Object.values(n)[0] || 0) : 0;
return [{ json: OrquestadorCore.reunir($('Despacho').first().json, res, { noentendi_n, texto_paciente: $('Entrada').first().json.texto }) }];"""

JS_SALIDA = JS_RES + """const e = $('Entrada').first().json;
const execId = String($execution.id);
const ctx = $('Armar contexto').first().json;
const plan = $('Despacho').first().json;
const pj = (n, c, d) => { try { const v = JSON.parse($(n).first().json[c] || 'null'); return v === null ? d : v; } catch (x) { return d; } };
const libros = [].concat(pj('Redis GET libro', 'libro_raw', []));
const prop = pj('Redis GET propuesta', 'propuesta_raw', null);
const recTurnos = $('Recordatorios').all().map((i) => i.json).filter((x) => x && x.id_cita_dentalink && x.fecha_turno).map((x) => ({ fecha: String(x.fecha_turno).slice(0, 10), hora_inicio: String(x.hora_turno || '').slice(0, 5) }));
const hechos = [].concat(pj('Redis GET hechos', 'hechos_raw', []));
const c = OrquestadorCore.componer({ modo: e.modo, texto_paciente: e.texto, execId, plan, reunion: $('Reunir').first().json, res,
  derivar_res: r('Derivar a secretaria'), humano_res: r('Pasar a humano'), libros, hechos, prop, ofertas: pj('Redis GET ofertas', 'ofertas_raw', []),
  vistos: [].concat(pj('Redis GET turnos_vistos', 'vistos_raw', []) || [], recTurnos), bloque: String($('Redis GET bloque').first().json.bloque_raw || ''),
  bloque_exec: String($('Redis GET bloque_exec').first().json.bloque_exec_raw || ''), triaje: pj('Redis GET triaje', 'triaje_raw', null),
  ultimo_asiri: ctx.ultimo_asiri || '', repeticiones: ctx.repeticiones || 0, menu: ctx.menu, mensajes: ctx.mensajes || {}, anuncio: ctx.anuncio || '', consulta: ctx.consulta || '', datosPago: ctx.datos_pago, conversacion_nueva: ctx.conversacion_nueva === true, prop_pendiente: ctx.prop_pendiente === true });
const vivo = e.modo === 'vivo';   // (08/10) solo avisa y guarda memoria con modo 'vivo' EXPLÍCITO
if (vivo) for (const a of c.avisos) { try { await this.helpers.httpRequest({ method: 'POST', url: '""" + GRUPO + """', qs: { phone: e.phone, resumen: a.texto }, json: true }); } catch (x) { /* el aviso nunca rompe la respuesta */ } }
const texto = c.texto; const silencio = c.silencio === true;
// La propuesta de ESTA ejecución queda "enviada" solo si su read-back realmente va en el mensaje (así la próxima respuesta sabe que el paciente lo vio).
let propuesta_json = null;
if (!silencio && texto && prop && String(prop.exec_id) === execId && prop.enviada !== true && prop.readback_text && OrquestadorCore.norm(texto).includes(OrquestadorCore.norm(prop.readback_text))) propuesta_json = JSON.stringify({ ...prop, enviada: true });
// (15/10, regla de Lucas: toda acción sobre la agenda se confirma JUSTO antes) Si había una confirmación pendiente que el paciente vio y este mensaje
// no la ejecutó (ninguna escritura) ni armó otra, se descarta: un "no, ese turno sí voy" seguido de silencio dejaba viva la propuesta y el
// siguiente pedido la ejecutaba sin volver a preguntar (prueba en vivo del 15/10, cancelación del 10/12).
const descartar_propuesta = ctx.prop_pendiente === true && !!prop && String(prop.exec_id) !== execId && !libros.some((l) => l && l.ok === true);
const hechosNuevos = libros.filter((l) => l && l.ok === true && l.readback_text && !l.simulado).map((l) => ({ ok: true, tipo: l.tipo, readback_text: l.readback_text }));
const hechos_json = hechosNuevos.length ? JSON.stringify(hechos.concat(hechosNuevos).slice(-10)) : null;
// Traza para el examen y la sombra: la decisión del orquestador y lo que hizo cada sub-agente (herramientas con su resultado).
const tools = [{ tool: 'orquestador', input: { pasos: plan.pasos || [] }, obs: JSON.stringify({ turnos: plan.turnos, pagos: plan.pagos, informacion: plan.informacion, urgencias: plan.urgencias, fija: plan.fija, fallo: plan.fallo_orquestador }).slice(0, 400) }]
  .concat(...Object.values(res).filter(Boolean).map((x) => (x.traza || []).map((t) => ({ ...t, agente: x.agente }))))
  .concat(['Derivar a secretaria', 'Pasar a humano'].filter((n) => r(n)).map((n) => ({ tool: n === 'Pasar a humano' ? 'pasar_a_humano' : 'derivar_secretaria', input: { cita: $('Reunir').first().json.cita }, obs: JSON.stringify(r(n)).slice(0, 400) })));
const agentes = Object.values(res).filter(Boolean).map((x) => ({ agente: x.agente, estado: x.estado, codigo: x.codigo || null, texto_libre_descartado: x.texto_libre_descartado || null }));
const humano = { type: 'human', content: String(e.texto || ''), additional_kwargs: { source: 'wa_inbound' }, response_metadata: {} };
// (§3.2) Un SOLO mensaje de Asiri en memoria, marcado como del bot v7 (el panel tiene que sumar 'asiri_v7' a SOURCES_DEL_BOT; ver docs §8).
const ai = { type: 'ai', content: texto, additional_kwargs: { source: 'asiri_v7', agentes: agentes.map((x) => x.agente) }, response_metadata: {}, tool_calls: [], invalid_tool_calls: [] };
return [{ json: { phone: e.phone, modo: vivo ? 'vivo' : 'sombra', hechos_json, texto, datos_pago_agregados: c.datos_pago_agregados || null, enviar: !silencio, silencio, derivar_triaje: c.derivar_triaje === true,
  triaje: c.derivar_triaje ? c.triaje : null, texto_original: null, motivo_chequeo: c.motivo_chequeo || null, motivo_banlist: null, fallo_agente: plan.fallo_orquestador === true, modo_humano: c.modo_humano === true,
  propuesta_json, descartar_propuesta, tools, agentes, plan: { turnos: plan.turnos, pagos: plan.pagos, informacion: plan.informacion, urgencias: plan.urgencias, fija: plan.fija, por_estado: plan.turnos_por_estado },
  partes: c.partes || null, avisos: c.avisos, guardar: vivo && !silencio, msg_human: JSON.stringify(humano), msg_ai: JSON.stringify(ai) } }];"""


def _code_con(g, nombre, js, x, y, modulos):
    """Nodo Code con los módulos de v7/*.js antepuestos (una sola fuente de verdad, probada offline)."""
    pre = "".join((V7 / f"{m}.js").read_text(encoding="utf-8").rstrip() + "\n" for m in modulos)
    return g._nodo(nombre, "n8n-nodes-base.code", 2, {"jsCode": pre + js}, x, y)


def _entradas_sub(clave):
    ent = {"tel": f"{E}.phone", "exec_id_actual": "$execution.id", "modo": MODO, "texto_paciente": f"{E}.texto", "ultimo_asiri": f"{CTX}.ultimo_asiri",
           "textos_paciente": f"{CTX}.textos_paciente", "turnos_json": f"{CTX}.turnos_json", "contexto": f"{CTX}.contexto",
           "datos": f"{CTX}.datos_info" if clave == "informacion" else "''",
           "pedido": "$('Ver urgencia').first().json.pedido" if clave == "urgencias" else f"$('Despacho').first().json.{clave}"}
    return ent


ESFUERZO_PRODUCCION = "medium"   # (20/10) era "low": con el v7 para todos, 2 de 4 pedidos múltiples en vivo salieron mal ruteados (318950, 318965)


def wf_cerebro(esfuerzo=ESFUERZO_PRODUCCION):
    """El cerebro que se despliega como "v7 Cerebro". esfuerzo: razonamiento del ORQUESTADOR (ESFUERZO_PRODUCCION; "minimal"/"low" para medir latencia)."""
    g = Grafo("v7 Cerebro" if esfuerzo == ESFUERZO_PRODUCCION else f"v7 Cerebro ({esfuerzo})")
    g.trigger({"phone": "5490000000651", "texto": "Hola", "pushName": "", "modo": "vivo", "historial_json": ""}, 0, 300)
    g.postgres("Historial", SQL_HISTORIAL, "$json.phone", 220, 300)
    # (21/10, auditoría) una_vez: encadenados detrás de 'Historial' (hasta 30 filas) corrían una vez POR FILA: cada recordatorio aparecía 23–60 veces en el contexto.
    g.postgres("Recordatorios", SQL_RECORDATORIOS, f"{E}.phone", 440, 300, una_vez=True)
    g.postgres("Primer mensaje", SQL_PRIMERO, f"{E}.phone", 550, 420, una_vez=True)
    g.postgres("Datos del consultorio", SQL_DATOS, "''", 660, 300, una_vez=True)
    g.subworkflow("Identificar paciente", "@@ID:ver_turnos@@", {"tel": f"{E}.phone", "exec_id_actual": "$execution.id"}, 770, 300)
    g.redis_get("Redis GET propuesta (entrada)", f"'propuesta:' + {E}.phone", "prop_entrada_raw", 825, 420)
    g._nodo("Armar contexto", "n8n-nodes-base.code", 2, {"jsCode": "const PROMPT_ORQ = " + json.dumps(PROMPT_ORQ, ensure_ascii=False) + ";\n"
            + "".join((V7 / f"{m}.js").read_text(encoding="utf-8").rstrip() + "\n" for m in ("historial_core", "agenda_core", "orquestador_core")) + JS_CONTEXTO}, 880, 300)
    g.cadena("Orquestador", f"{CTX}.contexto", f"{CTX}.sistema_orq", 1100, 300)
    g.modelo("Modelo Orquestador", "gpt-5-mini", esfuerzo, 1100, 560)
    g.conectar_ai("Modelo Orquestador", "Orquestador", "ai_languageModel")
    _code_con(g, "Despacho", JS_DESPACHO, 1320, 300, ("orquestador_core",))
    g.si("¿No entendí?", "$('Despacho').first().json.contar_no_entendi === true", 1430, 300)
    g.redis_incr("Redis INCR noentendi", f"({E}.modo === 'vivo' ? 'noentendi:' : 'v7s:noentendi:') + {E}.phone", 1800, 1485, 420)
    x = 1540
    ifs = {}
    for clave, nodo in SUBAGENTES:
        if clave == "urgencias":
            _code_con(g, "Ver urgencia", JS_VER_URGENCIA, x, 300, ("orquestador_core",))
            ifs[clave] = g.si("¿Urgencias?", "$('Ver urgencia').first().json.hacer === true", x + 110, 300)
        else:
            ifs[clave] = g.si(f"¿{nodo.split(' ', 1)[1]}?", f"!!$('Despacho').first().json.{clave}", x, 300)
        g.subworkflow(nodo, f"@@ID:agente_{clave}@@", _entradas_sub(clave), x + 110, 160)
        x += 330
    _code_con(g, "Reunir", JS_REUNIR, x, 300, ("orquestador_core",))
    g.si("¿Derivar?", "$('Reunir').first().json.derivar === true", x + 110, 300)
    clin = {"tel": f"{E}.phone", "exec_id_actual": "$execution.id", "modo": MODO, "texto_paciente": f"{E}.texto", "cita_textual": "$('Reunir').first().json.cita",
            "motivo": "$('Reunir').first().json.motivo", "nivel": "''", "texto": "''", "moneda": "''"}
    g.subworkflow("Derivar a secretaria", "@@ID:clinica@@", {**clin, "accion": "'derivar'"}, x + 220, 160)
    g.si("¿Pasar a humano?", "$('Reunir').first().json.humano === true", x + 330, 300)
    g.subworkflow("Pasar a humano", "@@ID:clinica@@", {**clin, "accion": "'humano'"}, x + 440, 160)
    tel = f"{E}.phone"
    x += 550
    lecturas = [("Redis GET libro", f"'escrituras:' + {tel} + ':' + $execution.id", "libro_raw"), ("Redis GET propuesta", f"'propuesta:' + {tel}", "propuesta_raw"),
                ("Redis GET ofertas", f"'ofertas:' + {tel}", "ofertas_raw"), ("Redis GET turnos_vistos", f"'turnos_vistos:' + {tel}", "vistos_raw"),
                ("Redis GET bloque", f"'bloque:' + {tel}", "bloque_raw"), ("Redis GET bloque_exec", f"'bloque_exec:' + {tel} + ':' + $execution.id", "bloque_exec_raw"),
                ("Redis GET triaje", f"'triaje_v7:' + {tel} + ':' + $execution.id", "triaje_raw"), ("Redis GET hechos", f"'hechos:' + {tel}", "hechos_raw")]
    for i, (n, k, prop) in enumerate(lecturas):
        g.redis_get(n, k, prop, x + 110 * i, 300)
    x += 110 * len(lecturas)
    _code_con(g, "Salida", JS_SALIDA, x, 300, ("chequeo_salida", "orquestador_core"))
    g.si("¿Guardar hechos?", "!!$('Salida').first().json.hechos_json", x + 110, 420)
    g.redis_set("Redis SET hechos", f"'hechos:' + {tel}", "$('Salida').first().json.hechos_json", 43200, x + 160, 520)
    g.si("¿Marcar propuesta enviada?", "!!$('Salida').first().json.propuesta_json", x + 220, 300)
    g.redis_set("Redis SET propuesta enviada", f"'propuesta:' + {tel}", "$('Salida').first().json.propuesta_json", 43200, x + 440, 240)
    g.si("¿Descartar propuesta?", "$('Salida').first().json.descartar_propuesta === true", x + 550, 420)
    g.redis_del("Redis DEL propuesta", f"'propuesta:' + {tel}", x + 600, 520)
    g.si("¿Guardar en memoria?", "$('Salida').first().json.guardar === true", x + 660, 300)
    g.postgres("Guardar en memoria", "INSERT INTO n8n_chat_histories (session_id, message) VALUES ($1, $2::jsonb), ($1, $3::jsonb)", "[$('Salida').first().json.phone, $('Salida').first().json.msg_human, $('Salida').first().json.msg_ai]", x + 880, 240)
    g.code("Devolver", "const s = $('Salida').first().json;\nreturn [{ json: { texto: s.texto, enviar: s.enviar, silencio: s.silencio, derivar_triaje: s.derivar_triaje === true, triaje: s.triaje || null, texto_original: s.texto_original || null, modo: s.modo, motivo_chequeo: s.motivo_chequeo, motivo_banlist: s.motivo_banlist, fallo_agente: s.fallo_agente, modo_humano: s.modo_humano, descartar_propuesta: s.descartar_propuesta === true, tools: s.tools, agentes: s.agentes, plan: s.plan, avisos: s.avisos } }];", x + 1100, 300)

    for a, b, s_ in [("Entrada", "Historial", 0), ("Historial", "Recordatorios", 0), ("Recordatorios", "Primer mensaje", 0), ("Primer mensaje", "Datos del consultorio", 0), ("Datos del consultorio", "Identificar paciente", 0),
                     ("Identificar paciente", "Redis GET propuesta (entrada)", 0), ("Redis GET propuesta (entrada)", "Armar contexto", 0), ("Armar contexto", "Orquestador", 0),
                     ("Orquestador", "Despacho", 0), ("Despacho", "¿No entendí?", 0), ("¿No entendí?", "Redis INCR noentendi", 0), ("¿No entendí?", "¿Turnos?", 1), ("Redis INCR noentendi", "¿Turnos?", 0)]:
        g.conectar(a, b, s_)
    # Cadena de sub-agentes: cada IF va a su agente (rama verdadera) o al siguiente paso (falsa); el agente sigue al siguiente paso.
    siguientes = ["¿Pagos?", "¿Información?", "Ver urgencia", "Reunir"]
    for (clave, nodo), sig in zip(SUBAGENTES, siguientes):
        g.conectar(ifs[clave], nodo, 0)
        g.conectar(ifs[clave], sig, 1)
        g.conectar(nodo, sig, 0)
    g.conectar("Ver urgencia", "¿Urgencias?", 0)
    for a, b, s_ in [("Reunir", "¿Derivar?", 0), ("¿Derivar?", "Derivar a secretaria", 0), ("¿Derivar?", "¿Pasar a humano?", 1), ("Derivar a secretaria", "¿Pasar a humano?", 0),
                     ("¿Pasar a humano?", "Pasar a humano", 0), ("¿Pasar a humano?", lecturas[0][0], 1), ("Pasar a humano", lecturas[0][0], 0)]:
        g.conectar(a, b, s_)
    for (a, _, _), (b, _, _) in zip(lecturas, lecturas[1:]):
        g.conectar(a, b, 0)
    for a, b, s_ in [(lecturas[-1][0], "Salida", 0), ("Salida", "¿Guardar hechos?", 0), ("¿Guardar hechos?", "Redis SET hechos", 0), ("¿Guardar hechos?", "¿Marcar propuesta enviada?", 1),
                     ("Redis SET hechos", "¿Marcar propuesta enviada?", 0), ("¿Marcar propuesta enviada?", "Redis SET propuesta enviada", 0), ("¿Marcar propuesta enviada?", "¿Descartar propuesta?", 1),
                     ("Redis SET propuesta enviada", "¿Descartar propuesta?", 0), ("¿Descartar propuesta?", "Redis DEL propuesta", 0), ("¿Descartar propuesta?", "¿Guardar en memoria?", 1),
                     ("Redis DEL propuesta", "¿Guardar en memoria?", 0), ("¿Guardar en memoria?", "Guardar en memoria", 0), ("¿Guardar en memoria?", "Devolver", 1), ("Guardar en memoria", "Devolver", 0)]:
        g.conectar(a, b, s_)
    return g.json()
