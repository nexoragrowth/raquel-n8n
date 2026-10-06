# -*- coding: utf-8 -*-
"""v7_workflow_cerebro.py — workflow "v7 Cerebro": recibe {phone, texto, pushName, modo} y devuelve {texto, enviar}.
Orden: contexto (historial por SQL + datos del consultorio + recordatorios + directrices del panel) → Asiri (AI Agent con 11 herramientas de código) →
chequeo de salida bidireccional contra el libro de escrituras → banlist (usted) → marca la propuesta como enviada → guarda en memoria (solo en modo vivo).
Los ids de los workflows de herramientas se resuelven al crearlos en n8n (marcadores @@ID:<clave>@@)."""
import json
from pathlib import Path

from v7_lib import V7, Grafo

GRUPO = "https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo"
PROMPT = (V7 / "prompt_asiri.md").read_text(encoding="utf-8").strip()
SQL_HISTORIAL = "SELECT message FROM n8n_chat_histories WHERE session_id = $1 ORDER BY id DESC LIMIT 30"
SQL_RECORDATORIOS = ("SELECT id_cita_dentalink, fecha_turno, hora_turno FROM recordatorios_enviados WHERE telefono = $1 AND confirmado_at IS NULL AND cancelado_at IS NULL "
                     "AND fecha_turno >= (now() AT TIME ZONE 'America/Argentina/Jujuy')::date ORDER BY fecha_turno, hora_turno")
SQL_DATOS = ("SELECT id::text AS id, contenido FROM knowledge_base WHERE id IN (20, 21, 24, 25, 36, 39) UNION ALL "
             "SELECT 'dir:' || clave AS id, valor AS contenido FROM agente_directrices WHERE clave = 'notas_para_asiri' ORDER BY 1")

FIJOS = {"tel": "$('Entrada').first().json.phone", "exec_id_actual": "$execution.id", "modo": "$('Entrada').first().json.modo"}
CLINICA_FIJOS = {**FIJOS, "texto_paciente": "$('Entrada').first().json.texto"}

# (nombre del nodo, clave del workflow, descripción para el modelo, campos fijos, campos que decide el modelo)
HERRAMIENTAS = [
    ("ver_turnos", "ver_turnos", "Trae los turnos vigentes del paciente (de todas las fichas del celular). Llamala SIEMPRE antes de proponer un cambio, una cancelación o una confirmación, o cuando pregunten por su turno. Devuelve texto, sin ids. Si el celular tiene varias fichas te dice que preguntes para quién es.",
     FIJOS, {}),
    ("elegir_ficha", "elegir_ficha", "Fija para quién es el turno cuando el celular tiene varias fichas (familia). Pasá el nombre o el DNI que dijo el paciente. El código lo verifica contra las fichas reales; si no coincide, te dice qué pedir.",
     FIJOS, {"nombre": "Nombre y/o apellido del paciente tal como lo dijo, o vacío si dio el DNI.", "dni": "DNI del paciente si lo dio, o vacío."}),
    ("buscar_horarios", "buscar_horarios", "Devuelve el bloque de turnos disponibles (mañana y tarde) ya escrito para el paciente: pegalo TEXTUAL, sin cambiarlo. No le preguntes franja ni fecha. Solo se puede reservar lo que esta herramienta ofreció. Si el paciente dice que ninguno le sirve, volvé a llamarla con desde = el día siguiente al último horario ofrecido (máximo dos bloques por conversación).",
     FIJOS, {"desde": "Opcional. Fecha YYYY-MM-DD desde la que buscar el SIGUIENTE bloque.", "hasta": "Opcional. Fecha límite inclusiva YYYY-MM-DD si el paciente restringe la búsqueda (por ejemplo 'esta semana')."}),
    ("proponer", "proponer", "Prepara un cambio, una reserva, una suma de turno o una cancelación y te devuelve el texto de confirmación para el paciente: pegalo TEXTUAL y esperá su 'sí' en su PRÓXIMO mensaje. No escribe nada en la agenda. Tipos: cambio (cambia un turno que ya tiene), reserva (turno nuevo sin turno vigente), sumar (otro turno además del que ya tiene, solo si el paciente lo pidió), cancelacion.",
     FIJOS, {"tipo": "cambio | reserva | sumar | cancelacion", "fecha": "Fecha YYYY-MM-DD del turno nuevo (vacío si es cancelacion). Tiene que ser una fecha de buscar_horarios.", "hora": "Hora HH:MM del turno nuevo (vacío si es cancelacion). Tiene que ser una hora de buscar_horarios.",
             "fecha_turno_viejo": "Fecha YYYY-MM-DD del turno que tiene ahora y se cambia o cancela (de ver_turnos). Vacío si es reserva o sumar."}),
    ("ejecutar_propuesta", "ejecutar_propuesta", "Ejecuta en la agenda la propuesta que armaste con proponer. SOLO se puede llamar en el mensaje SIGUIENTE al que el paciente vio el texto de confirmación y dijo que sí. Nunca en el mismo mensaje en que proponés. Devuelve el mensaje final para el paciente: usalo. Si falla, el turno actual no se toca.",
     FIJOS, {}),
    ("confirmar_turno", "confirmar_turno", "Confirma la asistencia a un turno cuando el paciente responde a un recordatorio ('confirmo', 'ahí estaremos'). Si hay varios recordatorios pendientes pasá la fecha de cada uno (YYYY-MM-DD) y llamala una vez por fecha. Devuelve el mensaje para el paciente.",
     FIJOS, {"fecha": "Fecha YYYY-MM-DD del turno a confirmar; vacío si hay un solo recordatorio pendiente."}),
    ("avisar_grupo", "clinica", "Avisa a la clínica (grupo de WhatsApp) SIN dejar de atender al paciente. nivel FYI = novedad; ACCION = alguien tiene que hacer algo. Escribí un texto claro: qué pasó y qué hay que hacer.",
     {**CLINICA_FIJOS, "accion": "'aviso'"}, {"nivel": "FYI o ACCION", "texto": "Qué pasó y qué hay que hacer, en una o dos oraciones."}),
    ("pasar_a_humano", "clinica", "Pasa la conversación a una persona (silencia al bot hasta 1 h después del último mensaje de una persona). SOLO si el paciente pidió hablar con la secretaria, la doctora o una persona (motivo pidio_persona), hizo una queja (queja) o pidió la baja de sus datos (baja_de_datos). Tenés que pasar la frase LITERAL del paciente que lo justifica; el código la verifica y si no coincide NO lo pasa. Un error de otra herramienta no es motivo. Las urgencias NO van acá: van a derivar_triaje.",
     {**CLINICA_FIJOS, "accion": "'humano'"}, {"motivo": "pidio_persona | queja | baja_de_datos", "cita_textual": "Fragmento LITERAL, copiado tal cual, del mensaje actual del paciente que justifica el motivo."}),
    ("derivar_triaje", "clinica", "URGENCIAS: dolor o molestia, sangrado, hinchazón, golpe, no puede comer, aparato, alambre, bracket o ligadura roto, suelto, salido o que pincha. Pasa el mensaje al protocolo de urgencias de la clínica, que le responde al paciente por su cuenta (video de ayuda aprobado por la doctora, una pregunta, o la doctora). Después respondé exactamente [NO_REPLY]. Ante la duda entre urgencia y otra cosa, derivá.",
     {**CLINICA_FIJOS, "accion": "'triaje'"}, {"cita_textual": "Fragmento del mensaje actual del paciente que describe el problema, copiado tal cual."}),
    ("registrar_pago", "clinica", "Avisa a la clínica que el paciente mandó un comprobante de pago o dice que ya transfirió. No valida montos ni dice que el pago ingresó. Después decile que la secretaria lo verifica en su horario de atención.",
     {**CLINICA_FIJOS, "accion": "'pago'"}, {}),
    ("lista_espera", "clinica", "Anota para la clínica que el paciente quiere adelantar su turno si se libera uno. Después decile solo 'se lo dejo anotado a la clínica'; NO prometas que le van a avisar.",
     {**CLINICA_FIJOS, "accion": "'espera'"}, {"texto": "Opcional: hasta qué fecha o qué horarios le sirven."}),
]

JS_CONTEXTO = """const e = $('Entrada').first().json;
const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
let override = null; try { override = e.historial_json ? JSON.parse(e.historial_json) : null; } catch (x) { override = null; }
const filas = Array.isArray(override) ? override : $('Historial').all().map((i) => i.json).filter((r) => r && r.message);
const hist = HistorialCore.armar(filas, 12);
const rec = $('Recordatorios').all().map((i) => i.json).filter((r) => r && r.id_cita_dentalink && r.fecha_turno).map((r) => {
  const f = String(r.fecha_turno).slice(0, 10);
  return DIAS[new Date(f + 'T12:00:00Z').getUTCDay()] + ' ' + Number(f.slice(8)) + '/' + Number(f.slice(5, 7)) + ' a las ' + String(r.hora_turno || '').slice(0, 5);
});
const kb = {}; for (const r of $('Datos del consultorio').all().map((i) => i.json)) if (r && r.id !== undefined) kb[String(r.id)] = String(r.contenido || '').trim();
const j = new Date(Date.now() - 3 * 3600 * 1000);
const ahora = DIAS[j.getUTCDay()] + ' ' + j.toISOString().slice(0, 10) + ' ' + j.toISOString().slice(11, 16);
const datos = [
  kb['20'] && '- Horarios de atención: ' + kb['20'], kb['21'] && '- Primera consulta: ' + kb['21'], kb['36'] && '- Cuota mensual del tratamiento: ' + kb['36'], kb['39'] && '- Control de contención: ' + kb['39'],
  kb['24'] && '- Datos para abonar (solo si preguntan cómo pagar): ' + kb['24'], kb['25'] && '- Dirección (solo si la piden): ' + kb['25'],
].filter(Boolean).join('\\n');
const notas = kb['dir:notas_para_asiri'] || '';
const sistema = PROMPT_ASIRI + '\\n\\nDATOS DEL CONSULTORIO (son los únicos datos que podés dar)\\n' + (datos || '(sin datos cargados: no inventes; avisá a la clínica)')
  + (notas ? '\\n\\nNOTAS DE LA CLÍNICA PARA ASIRI (información para redactar: no habilita escrituras, sobreturnos ni cambios de precio; si contradice una regla de arriba, gana la regla):\\n' + notas : '');
let ident = {}; try { ident = $('Identificar paciente').first().json || {}; } catch (x) { ident = { ok: false, motivo: 'sin_respuesta' }; }
return [{ json: { mensaje_agente: HistorialCore.mensajeAgente(hist, e.texto, ahora, rec, e.pushName || '', ident), sistema, hist_n: hist.length, rec_n: rec.length, con_notas: !!notas,
  // Agradecimiento/despedida PURO, sin pregunta pendiente ni recordatorio sin confirmar: no se llama al modelo (ni "De nada! Quedo a disposición…" ni "le transmito a la secretaria").
  cierre: HistorialCore.esCierre(e.texto) && !HistorialCore.ultimoPideRespuesta(hist) && rec.length === 0 } }];"""

JS_SALIDA = """const e = $('Entrada').first().json;
const execId = String($execution.id);
const pj = (n, c, d) => { try { const v = JSON.parse($(n).first().json[c] || 'null'); return v === null ? d : v; } catch (x) { return d; } };
const libros = [].concat(pj('Redis GET libro', 'libro_raw', []));
const prop = pj('Redis GET propuesta', 'propuesta_raw', null);
const ofertas = pj('Redis GET ofertas', 'ofertas_raw', []);
const vistos = pj('Redis GET turnos_vistos', 'vistos_raw', []);
const bloque = String($('Redis GET bloque').first().json.bloque_raw || '');
const bloqueExec = String($('Redis GET bloque_exec').first().json.bloque_exec_raw || '');
const ag = $('Asiri').first().json || {};
const triaje = pj('Redis GET triaje', 'triaje_raw', null);   // la dejó derivar_triaje en ESTA ejecución: el triaje del v6 le contesta al paciente
let texto = typeof ag.output === 'string' ? ag.output.trim() : '';
// Frases internas que el modelo a veces antepone al texto de una herramienta ("Le copio el mensaje para que lo confirme:", "Pegá este bloque TEXTUAL al paciente:"):
// se quitan por código, línea por línea, solo cuando terminan en ':' y preceden al texto real (examen 06/10: 3 de 8 conversaciones las mostraron).
const RE_META = /^\\s*(?:(?:le|te) (?:copio|paso|comparto|transmito|dejo|env[ií]o) (?:el |la |este |esta )?(?:mensaje|bloque|texto|confirmaci[oó]n)[^\\n:]{0,60}:|peg[aá](?:lo|le|selo)? [^\\n:]{0,80}:|ac[aá] (?:va|tiene|le va)[^\\n:]{0,60}:|mensaje (?:para|de) confirmaci[oó]n:)\\s*/i;
let metaQuitada = false; while (RE_META.test(texto)) { texto = texto.replace(RE_META, '').trim(); metaQuitada = true; }
const hayOk = libros.some((l) => l && l.ok === true);
const avisos = []; let fallo_agente = false;
if (!texto || ag.error) {
  fallo_agente = true;
  if (hayOk) texto = '';   // el chequeo lo reemplaza por el resultado real de la agenda
  else { texto = 'Disculpe, tuve un inconveniente para responderle en este momento. Le aviso a la clínica para que se comunique con usted.'; avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] Asiri no pudo responder (error del agente o tiempo agotado): revisar y contestar a mano.' }); }
}
let silencio = false;
if (texto === '[NO_REPLY]' && !hayOk) silencio = true;
// Urgencia derivada: Asiri no contesta (el triaje manda el video, la pregunta o el aviso de que la doctora se comunica) y la memoria la guarda el triaje.
// Si en la MISMA respuesta hubo una escritura en la agenda, gana contarle lo que se hizo y la urgencia va al grupo como [ACCIÓN] (no se pierde ninguna de las dos).
let derivar_triaje = false;
if (triaje && !hayOk) { derivar_triaje = true; silencio = true; texto = null; }
else if (triaje && hayOk) avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] La paciente mencionó una urgencia en el mismo mensaje en que se hizo un cambio en la agenda: revisar y contestarle. «' + String(triaje.cita || '').slice(0, 160) + '»' });
let motivo_chequeo = null, motivo_banlist = null;
if (!silencio) {
  const propReadback = (prop && String(prop.exec_id) === execId) ? prop.readback_text : null;
  const c = ChequeoSalida.revisar({ texto, libros, ofertas, turnos_vistos: vistos, propuesta_readback: propReadback, bloque_ofertas: bloque || null, bloque_exec: bloqueExec || null });
  if (c.accion === 'reemplazar') { texto = c.texto; motivo_chequeo = c.motivo; if (c.avisar && c.avisar.nivel === 'ACCION') avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] ' + c.avisar.texto }); }
  const pidioDir = /direcci[oó]n|d[oó]nde (queda|est[aá]n|es)|ubicaci[oó]n|c[oó]mo (llego|llegar)/i.test(e.texto || '');
  const b = BanlistUsted.revisar(texto, { pacientePidioDireccion: pidioDir });
  if (b.bloquea) { motivo_banlist = b.why; texto = 'Disculpe, déjeme consultarlo con la clínica para darle la información correcta. Ya les aviso.'; avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] El filtro de seguridad bloqueó una respuesta de Asiri (' + b.why + '): revisar la conversación.' }); }
}
// La propuesta de ESTA ejecución queda "enviada" solo si su read-back realmente va en el mensaje (así ejecutar_propuesta sabe que el paciente lo vio).
let propuesta_json = null;
if (!silencio && prop && String(prop.exec_id) === execId && prop.enviada !== true && prop.readback_text) {
  const norm = (x) => String(x || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/[^a-z0-9:\\/ ]+/g, ' ').replace(/\\s+/g, ' ').trim();
  if (norm(texto).includes(norm(prop.readback_text))) propuesta_json = JSON.stringify({ ...prop, enviada: true });
}
const vivo = e.modo !== 'sombra';
const humano = { type: 'human', content: String(e.texto || ''), additional_kwargs: { source: 'wa_inbound' }, response_metadata: {} };
const ai = { type: 'ai', content: texto, additional_kwargs: { source: 'wa_outbound' }, response_metadata: {}, tool_calls: [], invalid_tool_calls: [] };
if (vivo) for (const a of avisos) { try { await this.helpers.httpRequest({ method: 'POST', url: '""" + GRUPO + """', qs: { phone: e.phone, resumen: a.texto }, json: true }); } catch (x) { /* el aviso nunca rompe la respuesta */ } }
const tools = (Array.isArray(ag.intermediateSteps) ? ag.intermediateSteps : []).map((s) => ({ tool: s && s.action && s.action.tool, input: s && s.action && s.action.toolInput, obs: String((s && s.observation) || '').slice(0, 400) }));
return [{ json: { phone: e.phone, modo: e.modo || 'vivo', texto, enviar: !silencio, silencio, derivar_triaje, meta_quitada: metaQuitada, triaje: derivar_triaje ? triaje : null, motivo_chequeo, motivo_banlist, fallo_agente, propuesta_json, tools, avisos, guardar: vivo && !silencio,
  msg_human: JSON.stringify(humano), msg_ai: JSON.stringify(ai) } }];"""


def wf_cerebro():
    g = Grafo("v7 Cerebro")
    g.trigger({"phone": "5490000000651", "texto": "Hola", "pushName": "", "modo": "vivo", "historial_json": ""}, 0, 300)
    g.postgres("Historial", SQL_HISTORIAL, "$json.phone", 220, 300)
    g.postgres("Recordatorios", SQL_RECORDATORIOS, "$('Entrada').first().json.phone", 440, 300)
    g.postgres("Datos del consultorio", SQL_DATOS, "''", 660, 300)
    g.subworkflow("Identificar paciente", "@@ID:ver_turnos@@", {"tel": "$('Entrada').first().json.phone", "exec_id_actual": "$execution.id"}, 770, 300)
    g._nodo("Armar contexto", "n8n-nodes-base.code", 2, {"jsCode": "const PROMPT_ASIRI = " + json.dumps(PROMPT, ensure_ascii=False) + ";\n" + "".join((V7 / f"{m}.js").read_text(encoding="utf-8").rstrip() + "\n" for m in ("historial_core",)) + JS_CONTEXTO}, 880, 300)
    g.si("¿Es un cierre?", "$json.cierre === true", 990, 300)
    g.code("Cierre sin respuesta", "return [{ json: { texto: null, enviar: false, silencio: true, derivar_triaje: false, triaje: null, modo: $('Entrada').first().json.modo || 'vivo', motivo_chequeo: 'cierre_puro', motivo_banlist: null, fallo_agente: false, tools: [], avisos: [] } }];", 1100, 120)
    g.agente("Asiri", "$('Armar contexto').first().json.mensaje_agente", "$('Armar contexto').first().json.sistema", 1100, 300, max_iter=5)
    g.modelo("Modelo Asiri", "gpt-5-mini", "low", 1100, 560)
    g.conectar_ai("Modelo Asiri", "Asiri", "ai_languageModel")
    y = 80
    for nombre, clave, desc, fijos, del_modelo in HERRAMIENTAS:
        g.herramienta(nombre, desc, f"@@ID:{clave}@@", fijos, del_modelo, 1400, y)
        g.conectar_ai(nombre, "Asiri", "ai_tool")
        y += 90
    exec_key = "'escrituras:' + $('Entrada').first().json.phone + ':' + $execution.id"
    tel = "$('Entrada').first().json.phone"
    g.redis_get("Redis GET libro", exec_key, "libro_raw", 1320, 300)
    g.redis_get("Redis GET propuesta", f"'propuesta:' + {tel}", "propuesta_raw", 1540, 300)
    g.redis_get("Redis GET ofertas", f"'ofertas:' + {tel}", "ofertas_raw", 1760, 300)
    g.redis_get("Redis GET turnos_vistos", f"'turnos_vistos:' + {tel}", "vistos_raw", 1980, 300)
    g.redis_get("Redis GET bloque", f"'bloque:' + {tel}", "bloque_raw", 2200, 300)
    g.redis_get("Redis GET bloque_exec", f"'bloque_exec:' + {tel} + ':' + $execution.id", "bloque_exec_raw", 2310, 300)
    g.redis_get("Redis GET triaje", f"'triaje_v7:' + {tel} + ':' + $execution.id", "triaje_raw", 2365, 420)
    g._nodo("Salida", "n8n-nodes-base.code", 2, {"jsCode": "".join((V7 / f"{m}.js").read_text(encoding="utf-8").rstrip() + "\n" for m in ("chequeo_salida", "banlist_usted")) + JS_SALIDA}, 2420, 300)
    g.si("¿Marcar propuesta enviada?", "!!$json.propuesta_json", 2640, 300)
    g.redis_set("Redis SET propuesta enviada", f"'propuesta:' + {tel}", "$('Salida').first().json.propuesta_json", 1800, 2860, 240)
    g.si("¿Guardar en memoria?", "$('Salida').first().json.guardar === true", 3080, 300)
    g.postgres("Guardar en memoria", "INSERT INTO n8n_chat_histories (session_id, message) VALUES ($1, $2::jsonb), ($1, $3::jsonb)", "[$('Salida').first().json.phone, $('Salida').first().json.msg_human, $('Salida').first().json.msg_ai]", 3300, 240)
    g.code("Devolver", "const s = $('Salida').first().json;\nreturn [{ json: { texto: s.texto, enviar: s.enviar, silencio: s.silencio, derivar_triaje: s.derivar_triaje === true, triaje: s.triaje || null, modo: s.modo, motivo_chequeo: s.motivo_chequeo, motivo_banlist: s.motivo_banlist, fallo_agente: s.fallo_agente, tools: s.tools, avisos: s.avisos } }];", 3520, 300)
    for a, b, s_ in [("Entrada", "Historial", 0), ("Historial", "Recordatorios", 0), ("Recordatorios", "Datos del consultorio", 0), ("Datos del consultorio", "Identificar paciente", 0), ("Identificar paciente", "Armar contexto", 0), ("Armar contexto", "¿Es un cierre?", 0), ("¿Es un cierre?", "Cierre sin respuesta", 0), ("¿Es un cierre?", "Asiri", 1), ("Asiri", "Redis GET libro", 0),
                     ("Redis GET libro", "Redis GET propuesta", 0), ("Redis GET propuesta", "Redis GET ofertas", 0), ("Redis GET ofertas", "Redis GET turnos_vistos", 0), ("Redis GET turnos_vistos", "Redis GET bloque", 0),
                     ("Redis GET bloque", "Redis GET bloque_exec", 0), ("Redis GET bloque_exec", "Redis GET triaje", 0), ("Redis GET triaje", "Salida", 0), ("Salida", "¿Marcar propuesta enviada?", 0), ("¿Marcar propuesta enviada?", "Redis SET propuesta enviada", 0), ("¿Marcar propuesta enviada?", "¿Guardar en memoria?", 1),
                     ("Redis SET propuesta enviada", "¿Guardar en memoria?", 0), ("¿Guardar en memoria?", "Guardar en memoria", 0), ("¿Guardar en memoria?", "Devolver", 1), ("Guardar en memoria", "Devolver", 0)]:
        g.conectar(a, b, s_)
    return g.json()
