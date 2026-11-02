# -*- coding: utf-8 -*-
"""v7_workflow_cerebro_agente.py — workflow "v7 Cerebro Agente": el ORQUESTADOR es un AGENTE de n8n que tiene a los otros agentes como HERRAMIENTAS.

Mismo disparador y mismas entradas que "v7 Cerebro" ({phone, texto, pushName, modo, historial_json}) y misma salida (el 'V7: Adaptador' de la entrada no cambia).
Diferencia con el cerebro actual (orquestador = UNA llamada que devuelve JSON de pasos + código que despacha, reúne y compone): acá el agente llama a Turnos, Pagos,
Información y Urgencias (toolWorkflow, los mismos 4 sub-workflows), a derivar_secretaria / pasar_a_humano (workflow clinica) y a no_responder, VE lo que devuelven,
puede encadenar y ÉL le escribe la respuesta al paciente. El código no se va: lo verifica (nodo "Verificar salida", v7/verificador_core.js) y, si algo no cierra,
sale el RESPALDO (lo que devolvieron las herramientas armado por OrquestadorCore.componer, igual que hoy).

Orden:
  1. Lecturas y "Armar contexto": idénticas al cerebro actual (se importan, no se copian).
  2. "Pedidos por estado" (código): OrquestadorCore.despachar con una salida vacía → solo las REDES POR ESTADO (comprobante marcado → Pagos; confirmación pendiente o
     recordatorio → Turnos; charla de la clínica → silencio). Las que piden llamar a un agente se ejecutan ANTES del agente y su resultado entra en su mensaje.
  3. "Orquestador Agente" (IA con herramientas).
  4. Lecturas de Redis del estado de esta ejecución (libro de escrituras, ofertas, bloque, propuesta, triaje...).
  5. "Verificar salida" (código) → "Salida" (avisos, memoria SOLO en vivo, propuesta enviada) → "Devolver" (mismos campos que el cerebro actual + motivo_verificador / usado_respaldo).
Los ids de los workflows se resuelven al crearlos en n8n (marcadores @@ID:<clave>@@)."""
import json

from v7_lib import V7, Grafo
from v7_workflow_cerebro import (CTX, E, GRUPO, JS_CONTEXTO, JS_DESPACHO, MODO, SQL_DATOS, SQL_HISTORIAL, SQL_PRIMERO, SQL_RECORDATORIOS, _code_con)

NOMBRE = "v7 Cerebro Agente"
PROMPT_AGENTE = (V7 / "prompt_orquestador_agente.md").read_text(encoding="utf-8").strip()
ESFUERZO = "medium"
MAX_ITER = 8
AGENTE = "Orquestador Agente"
PLAN = "$('Pedidos por estado').first().json"

# Las redes por ESTADO son las de OrquestadorCore.despachar: se llama con una salida vacía del orquestador y se usa lo que arma el estado (plan.pagos / plan.turnos).
_l = JS_DESPACHO.split("\n")
assert _l[1].startswith("let o = {}"), "JS_DESPACHO cambió: revisar JS_PEDIDOS"
JS_PEDIDOS = "\n".join([_l[0], "const o = { text: '{\"pasos\":[]}' };"] + _l[2:])

JS_RES1 = "const r = (n) => { try { const x = $(n); return x.isExecuted ? (x.first().json || null) : null; } catch (y) { return null; } };\n"

# Mensaje al agente: el contexto de siempre + datos que el código arma (menú, audio sin transcribir, staff reciente) + lo que el sistema ya hizo por estado.
JS_MENSAJE = JS_RES1 + """const ctx = $('Armar contexto').first().json;
const plan = $('Pedidos por estado').first().json;
const extra = [];
const resumen = (o) => o && !o.error ? { estado: o.estado, codigo: o.codigo || null, texto: o.texto || '', readback: o.readback === true, derivar: o.derivar || null, urgencia: o.urgencia === true, fuera_de_alcance: o.fuera_de_alcance === true } : { estado: 'error' };
for (const [nodo, clave] of [['Pagos forzado', 'pagos'], ['Turnos forzado', 'turnos']]) {
  const o = r(nodo);
  if (o) extra.push('RESULTADO DE «' + clave + '» (el sistema ya la llamó por vos con este mensaje: NO la vuelvas a llamar; usá este resultado): ' + JSON.stringify(resumen(o)));
}
if (String($('Entrada').first().json.texto || '').toUpperCase().indexOf('[AUDIO]') >= 0 && ctx.audio_transcripto !== true) extra.push('El paciente mandó un audio que NO se pudo transcribir: pedile que lo escriba, con esta frase: ' + OrquestadorCore.TEXTOS.PEDIR_TEXTO);
if (ctx.staff_reciente === true) extra.push('El último mensaje que NO es del paciente lo escribió la clínica (STAFF) hace menos de 6 h: si solo corresponde derivar, llamá no_responder.');
extra.push('MENÚ (si saluda solo o pide información sin decir de qué, pegalo tal cual):\\n' + (ctx.menu || ''));
return [{ json: { texto_agente: ctx.contexto + '\\n\\n' + extra.join('\\n\\n') } }];"""

JS_VERIFICAR = JS_RES1 + """const e = $('Entrada').first().json;
const ctx = $('Armar contexto').first().json;
const plan = $('Pedidos por estado').first().json;
const pj = (n, c, d) => { try { const v = JSON.parse($(n).first().json[c] || 'null'); return v === null ? d : v; } catch (x) { return d; } };
const recTurnos = $('Recordatorios').all().map((i) => i.json).filter((x) => x && x.id_cita_dentalink && x.fecha_turno).map((x) => ({ fecha: String(x.fecha_turno).slice(0, 10), hora_inicio: String(x.hora_turno || '').slice(0, 5) }));
const forzados = [['Pagos forzado', 'pagos'], ['Turnos forzado', 'turnos']].map(([n, t]) => ({ n, t, o: r(n) })).filter((x) => x.o)
  .map((x) => ({ tool: x.t, input: { forzado: true, pedido: plan[x.t] }, obs: x.o }));
const v = VerificadorCore.verificar({ salida: r('""" + AGENTE + """'), forzados, texto_paciente: e.texto, execId: String($execution.id), modo: e.modo,
  ctx: { staff_reciente: ctx.staff_reciente === true, charla_de_la_clinica: ctx.charla_de_la_clinica === true },
  estado: { libros: [].concat(pj('Redis GET libro', 'libro_raw', [])), hechos: [].concat(pj('Redis GET hechos', 'hechos_raw', [])), prop: pj('Redis GET propuesta', 'propuesta_raw', null),
    ofertas: pj('Redis GET ofertas', 'ofertas_raw', []), vistos: [].concat(pj('Redis GET turnos_vistos', 'vistos_raw', []) || [], recTurnos), bloque: String($('Redis GET bloque').first().json.bloque_raw || ''),
    bloque_exec: String($('Redis GET bloque_exec').first().json.bloque_exec_raw || ''), triaje: pj('Redis GET triaje', 'triaje_raw', null), ultimo_asiri: ctx.ultimo_asiri || '', repeticiones: ctx.repeticiones || 0,
    menu: ctx.menu, mensajes: ctx.mensajes || {}, anuncio: ctx.anuncio || '', consulta: ctx.consulta || '', datosPago: ctx.datos_pago, conversacion_nueva: ctx.conversacion_nueva === true, prop_pendiente: ctx.prop_pendiente === true } });
return [{ json: v }];"""

# Salida: mismos campos que la del cerebro actual (el Adaptador de la entrada los consume sin cambios).
JS_SALIDA = """const e = $('Entrada').first().json;
const execId = String($execution.id);
const ctx = $('Armar contexto').first().json;
const v = $('Verificar salida').first().json;
const pj = (n, c, d) => { try { const x = JSON.parse($(n).first().json[c] || 'null'); return x === null ? d : x; } catch (y) { return d; } };
const libros = [].concat(pj('Redis GET libro', 'libro_raw', []));
const prop = pj('Redis GET propuesta', 'propuesta_raw', null);
const hechos = [].concat(pj('Redis GET hechos', 'hechos_raw', []));
const vivo = e.modo === 'vivo';   // solo avisa y guarda memoria con modo 'vivo' EXPLÍCITO
if (vivo) for (const a of (v.avisos || [])) { try { await this.helpers.httpRequest({ method: 'POST', url: '""" + GRUPO + """', qs: { phone: e.phone, resumen: a.texto }, json: true }); } catch (x) { /* el aviso nunca rompe la respuesta */ } }
const texto = v.texto; const silencio = v.silencio === true || !texto;
// La propuesta de ESTA ejecución queda "enviada" solo si su read-back realmente va en el mensaje.
let propuesta_json = null;
if (!silencio && texto && prop && String(prop.exec_id) === execId && prop.enviada !== true && prop.readback_text && OrquestadorCore.norm(texto).includes(OrquestadorCore.norm(prop.readback_text))) propuesta_json = JSON.stringify({ ...prop, enviada: true });
// Una confirmación pendiente que el paciente vio y este mensaje no ejecutó (ninguna escritura) ni reemplazó por otra, se descarta.
const descartar_propuesta = ctx.prop_pendiente === true && !!prop && String(prop.exec_id) !== execId && !libros.some((l) => l && l.ok === true);
const hechosNuevos = libros.filter((l) => l && l.ok === true && l.readback_text && !l.simulado).map((l) => ({ ok: true, tipo: l.tipo, readback_text: l.readback_text }));
const hechos_json = hechosNuevos.length ? JSON.stringify(hechos.concat(hechosNuevos).slice(-10)) : null;
const tools = [{ tool: 'orquestador_agente', input: { forzados: (v.plan || {}).forzados || [] }, obs: JSON.stringify({ motivo_verificador: v.motivo_verificador, usado_respaldo: v.usado_respaldo, fija: (v.plan || {}).fija }).slice(0, 400) }].concat(v.traza || []);
const humano = { type: 'human', content: String(e.texto || ''), additional_kwargs: { source: 'wa_inbound' }, response_metadata: {} };
const ai = { type: 'ai', content: texto, additional_kwargs: { source: 'asiri_v7', agentes: (v.agentes || []).map((x) => x.agente) }, response_metadata: {}, tool_calls: [], invalid_tool_calls: [] };
return [{ json: { phone: e.phone, modo: vivo ? 'vivo' : 'sombra', hechos_json, texto, datos_pago_agregados: v.datos_pago_agregados || null, enviar: !silencio, silencio, derivar_triaje: v.derivar_triaje === true,
  triaje: v.derivar_triaje ? v.triaje : null, texto_original: null, motivo_chequeo: v.motivo_chequeo || null, motivo_banlist: null, fallo_agente: v.fallo_agente === true, modo_humano: v.modo_humano === true,
  propuesta_json, descartar_propuesta, tools, agentes: v.agentes || [], plan: { turnos: (v.plan || {}).turnos, pagos: (v.plan || {}).pagos, informacion: (v.plan || {}).informacion, urgencias: (v.plan || {}).urgencias, fija: (v.plan || {}).fija, por_estado: (v.plan || {}).forzados || [] },
  partes: v.partes || null, avisos: v.avisos || [], guardar: vivo && !silencio, msg_human: JSON.stringify(humano), msg_ai: JSON.stringify(ai),
  motivo_verificador: v.motivo_verificador || null, usado_respaldo: v.usado_respaldo === true } }];"""

DEVOLVER = ("const s = $('Salida').first().json;\nreturn [{ json: { texto: s.texto, enviar: s.enviar, silencio: s.silencio, derivar_triaje: s.derivar_triaje === true, triaje: s.triaje || null, texto_original: s.texto_original || null, "
            "modo: s.modo, motivo_chequeo: s.motivo_chequeo, motivo_banlist: s.motivo_banlist, fallo_agente: s.fallo_agente, modo_humano: s.modo_humano, descartar_propuesta: s.descartar_propuesta === true, "
            "tools: s.tools, agentes: s.agentes, plan: s.plan, avisos: s.avisos, motivo_verificador: s.motivo_verificador, usado_respaldo: s.usado_respaldo } }];")

# ------------------------------------------------------------------------------------------------ herramientas
DESC = {
    "turnos": "Agente de TURNOS: sacar, cambiar o cancelar un turno, ver cuál tiene, elegir horario, para quién es, confirmar asistencia a un recordatorio, responder a la CONFIRMACIÓN PENDIENTE, lista de espera. Devuelve el texto armado por el sistema (bloque de horarios, '¿Procedo?', éxito) y un estado. Una vez por mensaje.",
    "pagos": "Agente de PAGOS: el paciente avisa que pagó, manda un comprobante o pide los datos para transferir (alias). Devuelve el texto de recepción; los datos bancarios los agrega el sistema (vos nunca los escribas). Una vez por mensaje.",
    "informacion": "Agente de INFORMACIÓN: precio de la primera consulta, horarios de atención, dirección, tratamientos, obra social, formas de pago, cómo se atiende. Responde solo con los datos del consultorio; si no corresponde dice FUERA_DE_ALCANCE. Una vez por mensaje.",
    "urgencias": "Agente de URGENCIAS: dolor, sangrado, hinchazón o golpe en la boca o los dientes; aparato, alambre o bracket roto, suelto o que pincha. Pasa el mensaje al protocolo de urgencias de la clínica, que le responde por su cuenta. Una vez.",
}
PEDIDO = "Lo que quiere el paciente en una línea, con TODOS los datos que dio (día, fecha, hora, nombre, DNI). Sin preguntas tuyas. Si contesta a la CONFIRMACIÓN PENDIENTE: 'responde a la confirmación pendiente'."


def _fijos_sub(clave):
    """Lo que NO decide el modelo: igual que _entradas_sub del cerebro actual, salvo `pedido` (lo escribe el agente)."""
    ent = {"tel": f"{E}.phone", "exec_id_actual": "$execution.id", "modo": MODO, "texto_paciente": f"{E}.texto", "ultimo_asiri": f"{CTX}.ultimo_asiri",
           "textos_paciente": f"{CTX}.textos_paciente", "turnos_json": f"{CTX}.turnos_json", "contexto": f"{CTX}.contexto",
           "datos": f"{CTX}.datos_info" if clave == "informacion" else "''"}
    return ent


def _fijos_forzado(clave):
    return {**_fijos_sub(clave), "pedido": f"{PLAN}.{clave}"}


def _fijos_clinica(accion):
    # derivar_secretaria con la clínica reciente (< 6 h) corre en modo sombra: no avisa al grupo ni silencia el chat (la secretaria ya está en esa charla).
    modo = f"({CTX}.staff_reciente === true ? 'sombra' : ({MODO}))" if accion == "derivar" else MODO
    return {"tel": f"{E}.phone", "exec_id_actual": "$execution.id", "modo": modo, "texto_paciente": f"{E}.texto", "accion": f"'{accion}'", "nivel": "''", "texto": "''", "moneda": "''"}


def wf_cerebro_agente(esfuerzo=ESFUERZO):
    g = Grafo(NOMBRE)
    g.trigger({"phone": "5490000000651", "texto": "Hola", "pushName": "", "modo": "vivo", "historial_json": ""}, 0, 300)
    g.postgres("Historial", SQL_HISTORIAL, "$json.phone", 220, 300)
    g.postgres("Recordatorios", SQL_RECORDATORIOS, f"{E}.phone", 440, 300, una_vez=True)
    g.postgres("Primer mensaje", SQL_PRIMERO, f"{E}.phone", 550, 420, una_vez=True)
    g.postgres("Datos del consultorio", SQL_DATOS, "''", 660, 300, una_vez=True)
    g.subworkflow("Identificar paciente", "@@ID:ver_turnos@@", {"tel": f"{E}.phone", "exec_id_actual": "$execution.id"}, 770, 300)
    g.redis_get("Redis GET propuesta (entrada)", f"'propuesta:' + {E}.phone", "prop_entrada_raw", 825, 420)
    g._nodo("Armar contexto", "n8n-nodes-base.code", 2, {"jsCode": "const PROMPT_ORQ = " + json.dumps(PROMPT_AGENTE, ensure_ascii=False) + ";\n"
            + "".join((V7 / f"{m}.js").read_text(encoding="utf-8").rstrip() + "\n" for m in ("historial_core", "agenda_core", "orquestador_core")) + JS_CONTEXTO}, 880, 300)
    _code_con(g, "Pedidos por estado", JS_PEDIDOS, 1090, 300, ("orquestador_core",))
    g.si("¿Charla de la clínica?", f"{PLAN}.charla_de_la_clinica === true", 1300, 300)
    g.si("¿Forzar Pagos?", f"!!{PLAN}.pagos", 1510, 300)
    g.subworkflow("Pagos forzado", "@@ID:agente_pagos@@", _fijos_forzado("pagos"), 1620, 160)
    g.si("¿Forzar Turnos?", f"!!{PLAN}.turnos", 1840, 300)
    g.subworkflow("Turnos forzado", "@@ID:agente_turnos@@", _fijos_forzado("turnos"), 1950, 160)
    g.code("Armar mensaje del agente", JS_MENSAJE, 2170, 300, usar=("orquestador_core",))
    g.agente(AGENTE, f"$('Armar mensaje del agente').first().json.texto_agente", f"{CTX}.sistema_orq", 2390, 300, max_iter=MAX_ITER)
    g.modelo("Modelo Orquestador Agente", "gpt-5-mini", esfuerzo, 2390, 560)
    g.conectar_ai("Modelo Orquestador Agente", AGENTE, "ai_languageModel")
    y = 60
    for clave in ("turnos", "pagos", "informacion", "urgencias"):
        g.herramienta(clave, DESC[clave], f"@@ID:agente_{clave}@@", _fijos_sub(clave), {"pedido": PEDIDO}, 2700, y)
        g.conectar_ai(clave, AGENTE, "ai_tool")
        y += 90
    g.herramienta("derivar_secretaria", "Deriva a la secretaria lo que ningún agente atiende (cuánto debe, presupuesto de su caso, dólares, cuotas, quejas, bajas, proveedores, consultas clínicas sin urgencia, estudios o documentos). Una vez. Devuelve el texto para decirle al paciente.",
                  "@@ID:clinica@@", _fijos_clinica("derivar"), {"cita_textual": "La frase del paciente copiada tal cual.", "motivo": "Una línea con el motivo."}, 2700, y)
    g.conectar_ai("derivar_secretaria", AGENTE, "ai_tool"); y += 90
    g.herramienta("pasar_a_humano", "El paciente pide hablar con una persona, la secretaria o la doctora: pasa el chat a modo humano. Una vez. Devuelve el texto para decirle al paciente.",
                  "@@ID:clinica@@", _fijos_clinica("humano"), {"cita_textual": "La frase del paciente copiada tal cual.", "motivo": "Una línea con el motivo."}, 2700, y)
    g.conectar_ai("pasar_a_humano", AGENTE, "ai_tool"); y += 90
    # no_responder: el agente decide el silencio (agradece, se despide, sticker, le contesta al staff...). No hace nada en ningún sistema.
    g._nodo("no_responder", "@n8n/n8n-nodes-langchain.toolCode", 1.1, {"name": "no_responder", "language": "javaScript",
            "description": "No responderle nada al paciente (silencio): agradece o se despide sin pedir nada, avisa que está llegando, manda solo un sticker o emoji, 'ok' sin nada pendiente, o le contesta al STAFF sin pedir nada nuevo. No la combines con otras herramientas.",
            "jsCode": "return JSON.stringify({ ok: true, silencio: true });"}, 2700, y)
    g.conectar_ai("no_responder", AGENTE, "ai_tool")

    tel = f"{E}.phone"
    x = 3000
    lecturas = [("Redis GET libro", f"'escrituras:' + {tel} + ':' + $execution.id", "libro_raw"), ("Redis GET propuesta", f"'propuesta:' + {tel}", "propuesta_raw"),
                ("Redis GET ofertas", f"'ofertas:' + {tel}", "ofertas_raw"), ("Redis GET turnos_vistos", f"'turnos_vistos:' + {tel}", "vistos_raw"),
                ("Redis GET bloque", f"'bloque:' + {tel}", "bloque_raw"), ("Redis GET bloque_exec", f"'bloque_exec:' + {tel} + ':' + $execution.id", "bloque_exec_raw"),
                ("Redis GET triaje", f"'triaje_v7:' + {tel} + ':' + $execution.id", "triaje_raw"), ("Redis GET hechos", f"'hechos:' + {tel}", "hechos_raw")]
    for i, (n, k, prop) in enumerate(lecturas):
        g.redis_get(n, k, prop, x + 110 * i, 300)
    x += 110 * len(lecturas)
    _code_con(g, "Verificar salida", JS_VERIFICAR, x, 300, ("chequeo_salida", "orquestador_core", "verificador_core"))
    _code_con(g, "Salida", JS_SALIDA, x + 220, 300, ("orquestador_core",))
    x += 220
    g.si("¿Guardar hechos?", "!!$('Salida').first().json.hechos_json", x + 110, 420)
    g.redis_set("Redis SET hechos", f"'hechos:' + {tel}", "$('Salida').first().json.hechos_json", 43200, x + 160, 520)
    g.si("¿Marcar propuesta enviada?", "!!$('Salida').first().json.propuesta_json", x + 220, 300)
    g.redis_set("Redis SET propuesta enviada", f"'propuesta:' + {tel}", "$('Salida').first().json.propuesta_json", 43200, x + 440, 240)
    g.si("¿Descartar propuesta?", "$('Salida').first().json.descartar_propuesta === true", x + 550, 420)
    g.redis_del("Redis DEL propuesta", f"'propuesta:' + {tel}", x + 600, 520)
    g.si("¿Guardar en memoria?", "$('Salida').first().json.guardar === true", x + 660, 300)
    g.postgres("Guardar en memoria", "INSERT INTO n8n_chat_histories (session_id, message) VALUES ($1, $2::jsonb), ($1, $3::jsonb)", "[$('Salida').first().json.phone, $('Salida').first().json.msg_human, $('Salida').first().json.msg_ai]", x + 880, 240)
    g.code("Devolver", DEVOLVER, x + 1100, 300)

    for a, b, s_ in [("Entrada", "Historial", 0), ("Historial", "Recordatorios", 0), ("Recordatorios", "Primer mensaje", 0), ("Primer mensaje", "Datos del consultorio", 0), ("Datos del consultorio", "Identificar paciente", 0),
                     ("Identificar paciente", "Redis GET propuesta (entrada)", 0), ("Redis GET propuesta (entrada)", "Armar contexto", 0), ("Armar contexto", "Pedidos por estado", 0),
                     ("Pedidos por estado", "¿Charla de la clínica?", 0), ("¿Charla de la clínica?", lecturas[0][0], 0), ("¿Charla de la clínica?", "¿Forzar Pagos?", 1),
                     ("¿Forzar Pagos?", "Pagos forzado", 0), ("¿Forzar Pagos?", "¿Forzar Turnos?", 1), ("Pagos forzado", "¿Forzar Turnos?", 0),
                     ("¿Forzar Turnos?", "Turnos forzado", 0), ("¿Forzar Turnos?", "Armar mensaje del agente", 1), ("Turnos forzado", "Armar mensaje del agente", 0),
                     ("Armar mensaje del agente", AGENTE, 0), (AGENTE, lecturas[0][0], 0)]:
        g.conectar(a, b, s_)
    for (a, _, _), (b, _, _) in zip(lecturas, lecturas[1:]):
        g.conectar(a, b, 0)
    for a, b, s_ in [(lecturas[-1][0], "Verificar salida", 0), ("Verificar salida", "Salida", 0), ("Salida", "¿Guardar hechos?", 0), ("¿Guardar hechos?", "Redis SET hechos", 0), ("¿Guardar hechos?", "¿Marcar propuesta enviada?", 1),
                     ("Redis SET hechos", "¿Marcar propuesta enviada?", 0), ("¿Marcar propuesta enviada?", "Redis SET propuesta enviada", 0), ("¿Marcar propuesta enviada?", "¿Descartar propuesta?", 1),
                     ("Redis SET propuesta enviada", "¿Descartar propuesta?", 0), ("¿Descartar propuesta?", "Redis DEL propuesta", 0), ("¿Descartar propuesta?", "¿Guardar en memoria?", 1),
                     ("Redis DEL propuesta", "¿Guardar en memoria?", 0), ("¿Guardar en memoria?", "Guardar en memoria", 0), ("¿Guardar en memoria?", "Devolver", 1), ("Guardar en memoria", "Devolver", 0)]:
        g.conectar(a, b, s_)
    return g.json()
