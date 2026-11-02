# -*- coding: utf-8 -*-
"""v6_workflow_orquestador.py — workflows "v6 Orquestador" y "v6 Orquestador (sombra)": el patrón "Ultimate Assistant" de n8n aplicado a lo que YA TENÍA el v6.

Qué es: un AGENTE PADRE (gpt-5-mini, con memoria Postgres como el v6) que recibe el mensaje y tiene como HERRAMIENTAS a los 5 especialistas del v6
(Agendar, Confirmar, Cancelar, Urgencia, General), cada uno un agente completo (nodo Agent Tool de n8n) con SU modelo, SU prompt y SUS herramientas.
Los especialistas devuelven lo que encontraron y el PADRE le redacta la respuesta al paciente.

Qué NO se reescribe: los especialistas se COPIAN programáticamente del v6 (workflows/history/O155MqHgOSaNZ9ye_POST_token_webhook_*.json): modelos, herramientas
(toolHttpRequest, toolWorkflow buscar_horarios, buscar_conocimiento), conexiones ai_*, memoria. De cada prompt solo cambia lo que está en EDITS (con razón), más un bloque
corto al principio. Lo único que sale del v6 es el "Router - Clasificar Intent" (clasificador de una llamada), que lo reemplaza el padre.

Variantes: wf_v6_orquestador(modo_sombra=False) = vivo (herramientas originales); modo_sombra=True = las herramientas que ESCRIBEN (SIMULADAS) se reemplazan por
toolCode que devuelve un éxito falso con los mismos campos (ver SIMULADAS); las de solo lectura quedan reales.

Entradas / salida: las del cerebro actual ({phone, texto, pushName, modo, historial_json} → {texto, enviar, silencio, derivar_triaje, ...}) para enchufarse donde hoy se
llama "V7: Cerebro". Plomería reusada del cerebro (v7_workflow_cerebro): Historial, Recordatorios, Primer mensaje, Datos del consultorio, Identificar paciente, Armar contexto.
Los nodos que las expresiones de los prompts del v6 necesitan (Edit Fields - Extraer Datos, Extraer Horarios y Precio, Preparar Mensaje Final) existen con el mismo nombre y campos."""
import copy
import json
import uuid
from pathlib import Path

from v7_lib import ROOT, V7, Grafo
from v7_workflow_cerebro import (E, GRUPO, JS_CONTEXTO, MODO, SQL_DATOS, SQL_HISTORIAL, SQL_PRIMERO, SQL_RECORDATORIOS, _code_con)

NOMBRE_VIVO = "v6 Orquestador"
NOMBRE_SOMBRA = "v6 Orquestador (sombra)"
FUENTE_V6 = ROOT / "workflows" / "history" / "O155MqHgOSaNZ9ye_POST_token_webhook_1792531215.json"
PROMPT_PADRE = (V7 / "prompt_orquestador_v6.md").read_text(encoding="utf-8").strip()
PADRE = "Orquestador v6"
ESFUERZO = "medium"
MAX_ITER = 10
CTX = "$('Armar contexto').first().json"

# especialista (nodo agent del v6) → (nombre de la herramienta del padre, nombre del nodo del modelo)
ESPECIALISTAS = {
    "Sub-Agent Agendar": "agente_agendar",
    "Sub-Agent Confirmar": "agente_confirmar",
    "Sub-Agent Cancelar": "agente_cancelar",
    "Sub-Agent Urgencia": "agente_urgencia",
    "Sub-Agent General": "agente_general",
}
HERRAMIENTAS_PADRE = list(ESPECIALISTAS.values())

# ------------------------------------------------------------------------------------------------ descripciones (las del Router actual + sus intents)
COMUN = (" Mandale en `encargo` un pedido explícito y completo: qué necesitás (una sola tarea), qué dijo el paciente (frase textual), el contexto que ESTE agente necesita "
         "(ficha o familiar elegido, turnos y recordatorios, horarios ya ofrecidos, confirmación pendiente, si es paciente nuevo, datos que ya dio) y restricciones. No ve la conversación. "
         "Devuelve HICE/DATOS/TEXTO_FIJO/FALTA/ESCALÓ; no le redacta al paciente.")
DESC = {
    "agente_agendar": "Agente AGENDAR (intent agendar_nuevo): el paciente solicita un turno nuevo (\"quiero un turno\", \"primera vez\", \"necesito consulta\", \"agendarme\") o elige/acepta un horario "
                      "que se le acaba de ofrecer (\"el martes a las 10\", \"dale ese\", \"el primero\"), o contesta nombre, DNI o para quién es en ese flujo. Busca horarios, identifica o registra al paciente, "
                      "hace el read-back y reserva en la agenda." + COMUN,
    "agente_confirmar": "Agente CONFIRMAR (intent confirmar_post_recordatorio): el paciente afirma asistencia a un turno recordado (\"confirmo\", \"asisto\", \"voy\", \"dale\", \"sí\", 👍/✅/🙏) "
                        "o envía/avisa un comprobante de pago o transferencia. Confirma el turno en la agenda y registra el comprobante (avisa a la secretaria; nunca valida montos)." + COMUN,
    "agente_cancelar": "Agente CANCELAR (intent cancelar_o_reprogramar): el paciente no puede asistir, quiere cancelar, anular, suspender, cambiar, mover o posponer un turno existente, o pregunta si se puede "
                       "cambiar de fecha u horario. Identifica el turno, hace el read-back, lo cancela y, si quiere reprogramar, busca horarios nuevos." + COMUN,
    "agente_urgencia": "Agente URGENCIA (intent urgencia_dolor, MÁXIMA prioridad): dolor dental o de muela, sangrado, hinchazón, golpe, alambre o bracket salido o que pincha, o pide qué tomar. "
                       "Solo avisa a la doctora de inmediato y devuelve el texto fijo de recepción." + COMUN,
    "agente_general": "Agente GENERAL (intent consulta_general): precios de la consulta, ubicación o dirección, horarios de atención, alias y formas de pago, obra social, tratamientos, avisos de llegada, saludos "
                      "solos, consultar su propio turno; y TODO lo ambiguo o que no encaje en los otros cuatro (también pedidos que hay que derivar a la secretaria: fotos clínicas, quejas, presupuestos, "
                      "o \"pidió hablar con una persona\": decíselo así en el encargo)." + COMUN,
}
ENCARGO_FROMAI = ("={{ $fromAI('encargo', 'Encargo explícito y completo para este especialista: 1) qué necesitás (una sola tarea); 2) qué dijo el paciente (frase textual relevante); "
                  "3) el contexto que ESTE especialista necesita (ficha o familiar elegido, turnos vigentes y recordatorios abiertos, horarios ya ofrecidos, confirmación pendiente, si es paciente nuevo, "
                  "datos que ya dio); 4) restricciones que apliquen. No le pases el historial entero.', 'string') }}")

# ------------------------------------------------------------------------------------------------ prompts: bloque + cambios (TODO cambio está acá y en docs/v6-orquestador-diseno.md)
BLOQUE = """QUÉ RECIBÍS DEL ORQUESTADOR Y QUÉ DEVOLVÉS:
- Te llama el agente orquestador, no el paciente. Recibís un ENCARGO con el pedido puntual, la frase textual del paciente y el contexto que necesitás (ficha o familiar elegido, turnos y recordatorios, horarios ya ofrecidos, confirmación pendiente, datos que ya dio). No ves la conversación: trabajá con el encargo y tus herramientas, y si te falta algo pedilo con FALTA:.
- Devolvés DATOS CONCRETOS y qué hiciste, en secciones con estas etiquetas (solo las que correspondan, cada una al comienzo de una línea): HICE: (qué herramientas usaste y el resultado real: ids, fechas, horas), DATOS: (lo que encontraste), TEXTO_FIJO: (todo mensaje que más abajo diga "respondé EXACTAMENTE" o "pegá TAL CUAL", copiado sin cambios), FALTA: (el dato que necesitás del paciente, como pregunta puntual), ESCALÓ: (si avisaste a la secretaria, el motivo), FUERA_DE_AREA: (si el pedido no es de tu área, qué es), SIN_RESPUESTA (si no hay nada para decir).
- NO le redactás al paciente: eso lo hace el orquestador. Donde más abajo diga "respondé", "enviá" o "mostrale", devolvé ese contenido en TEXTO_FIJO o DATOS.
"""
IDENT = "Sos Asiri, la secretaria virtual de la Dra. Raquel Rodríguez (Áurea Odontología Estética, San Salvador de Jujuy).\n"
NO_CONV_CC = "NO conversas de temas personales, NO opinas, NO das diagnósticos ni indicaciones médicas.\n"
MAX_ESC_CC = "- Máximo UNA llamada a `escalar_a_secretaria` por turno. Si escalás, enviá el canned y terminá.\n"
CIERRES_CC = '- Cierres y avisos en camino ("ok", "gracias", "estoy llegando", "ya llegué"): Devolvé `[NO_REPLY]`.\n'
# (viejo, nuevo, destino, razón). destino: "padre" = la regla vive ahora en el prompt del padre; "eliminado" = ya no tiene sentido; "reemplazado" = cambia de forma.
_ID = (IDENT, "", "padre", "identidad y trato: ahora los tiene el padre, que es quien le habla al paciente")
EDITS = {
    "Sub-Agent Agendar": [
        _ID,
        ("NO conversas de temas personales, NO opinas, NO interpretas síntomas clínicos, NO das diagnósticos ni indicaciones médicas.\n", "", "padre", "sin diagnóstico ni opiniones: regla transversal del padre (NUNCA)"),
        (" y formato 24 hs", "", "padre", "formato de horas: lo redacta el padre"),
        ('- Máximo UNA llamada a `escalar_a_secretaria` por turno. Si escalás, enviá: "Le transmito su caso a la secretaria para que le responda a la brevedad en su horario de atención. ¡Muchas gracias!" y terminá.',
         "- Si escalás, terminá ahí; el mensaje de derivación lo escribe el orquestador.", "padre", "una sola derivación por mensaje y el texto de derivación: ahora viven en el padre (una vez, no en cada especialista)"),
        ('- Cierres y avisos de llegada ("ok", "gracias", "estoy llegando", "ya llegué"): Devolvé `[NO_REPLY]`.\n', "", "padre", "el silencio lo decide el padre (herramienta no_responder)"),
    ],
    "Sub-Agent Confirmar": [
        _ID,
        (NO_CONV_CC, "", "padre", "sin diagnóstico ni opiniones: regla transversal del padre"),
        ("No informes montos de tratamientos, cuotas ni retenedores (solo la secretaria). ", "", "eliminado", "duplicaba la política de montos de Información/General; el padre solo permite el precio de la consulta"),
        (MAX_ESC_CC, "- Si escalás, terminá ahí.\n", "padre", "una sola derivación por mensaje: regla del padre"),
        (CIERRES_CC, "", "padre", "el silencio lo decide el padre (no_responder)"),
        ('- Horas en formato 24 hs (ej: "15:30 hs"). NO inventes turnos.', "", "padre", "formato de horas y 'no inventes': el padre redacta y solo afirma lo que un especialista dijo"),
    ],
    "Sub-Agent Cancelar": [
        _ID,
        (NO_CONV_CC, "", "padre", "sin diagnóstico ni opiniones: regla transversal del padre"),
        (MAX_ESC_CC, "- Si escalás, terminá ahí.\n", "padre", "una sola derivación por mensaje: regla del padre"),
        (CIERRES_CC, "", "padre", "el silencio lo decide el padre (no_responder)"),
        ('- Horas en formato 24 hs (ej: "15:30 hs").', "", "padre", "formato de horas: lo redacta el padre"),
    ],
    "Sub-Agent Urgencia": [
        _ID,
        ("NO conversas, NO diagnosticas, NO das consejos (ni siquiera paliativos como cera o enjuagues), NO recomiendas medicación.\n", "", "padre", "prohibiciones médicas: transversales, ahora en el padre (incluye cera, enjuagues y medicación)"),
        ("\nPROHIBIDO ABSOLUTO:\n- Dar cualquier consejo médico u operativo.\n- Recomendar medicación, dosis o diagnósticos.\n- Conversar más allá del mensaje de derivación.\n"
         "- Máximo UNA sola llamada a `escalar_a_secretaria` por turno. Si el paciente insiste, devolvé `[NO_REPLY]`.", "", "padre",
         "el especialista ya no le habla al paciente: consejos, medicación y diagnóstico están prohibidos en el padre; una sola derivación y el silencio los decide el padre"),
    ],
    "Sub-Agent General": [
        _ID,
        ("NO conversas de temas personales, NO opinas, NO consuelas, NO interpretas síntomas clínicos, NO das diagnósticos ni indicaciones de medicación.\n", "", "padre", "sin diagnóstico ni opiniones: regla transversal del padre"),
        (' y responde al paciente:\n     "Le transmito su consulta a la secretaria para que le responda a la brevedad en su horario de atención. ¡Muchas gracias!"',
         " y terminá ahí (el mensaje de derivación a la secretaria lo escribe el orquestador).", "padre", "texto de derivación: ahora una sola vez, en el padre"),
        ("\n   - REGLA: Máximo UNA sola llamada a `escalar_a_secretaria` por turno de conversación.", "", "padre", "una sola derivación por mensaje: regla del padre"),
        ('\n\n6. AVISOS DE LLEGADA / EN CAMINO:\n   - Si el paciente avisa que está en camino ("estoy llegando", "ya llegué", "estoy abajo", "a dos cuadras"), responde brevemente confirmando o devolvé `[NO_REPLY]`.',
         "", "padre", "avisos de llegada: el silencio lo decide el padre (no_responder)"),
        (", el trato de usted ni", " ni", "padre", "trato de usted: regla del padre"),
        (": NO se informan por WhatsApp (pedido de la Dra., 16/10). Si los preguntan, NO des ningún monto: respondé", ": si los preguntan, respondé", "padre",
         "la política de montos (solo el precio de la consulta) vive ahora en el padre; acá queda la acción (qué responder y avisar)"),
        ('- Tono cordial, profesional y conciso (trato de usted).\n- Horas en formato 24 hs (ej: "8:00 hs", "15:30 hs").\n- NUNCA inventes turnos, direcciones fuera de Balcarce 37 ni prometas diagnósticos médicos.',
         "- Direcciones: solo Balcarce 37.", "padre", "tono, trato, formato de horas, 'no inventes turnos' y 'sin diagnósticos': reglas del padre; queda lo propio (la dirección)"),
    ],
}


def aplicar_edits(clave, texto):
    """Aplica EDITS[clave] y antepone el bloque. `texto` = systemMessage del v6 (empieza con '=': marca de expresión de n8n). Cada `viejo` tiene que estar UNA sola vez."""
    assert texto.startswith("="), clave
    cuerpo = texto[1:]
    for viejo, nuevo, _d, _r in EDITS[clave]:
        assert cuerpo.count(viejo) == 1, f"{clave}: el fragmento no está exactamente una vez: {viejo[:60]!r} ({cuerpo.count(viejo)})"
        cuerpo = cuerpo.replace(viejo, nuevo)
    return "=" + BLOQUE + "\n" + cuerpo


# ------------------------------------------------------------------------------------------------ herramientas que ESCRIBEN (sombra)
# nombre de la herramienta del v6 → (ejemplo de entrada, JS). Se conservan el nombre y la descripción originales; el modelo ve lo mismo y recibe un éxito falso con los mismos campos.
_Q = "const q = (typeof query === 'object' && query) ? query : {};\n"
SIMULADAS = {
    "reservar_turno": ({"id_paciente": 123, "fecha": "2026-11-10", "hora_inicio": "10:00", "comentario": "Primera consulta"},
                       _Q + "return JSON.stringify({ data: { id: 990000001, id_paciente: q.id_paciente, id_dentista: 1, id_sucursal: 1, id_sillon: 1, fecha: q.fecha, hora_inicio: q.hora_inicio, duracion: 40, id_estado: 2, estado_cita: 'Reservado', comentario: q.comentario || '', _simulado: true } });"),
    "cancelar_turno": ({"cita_id": 123},
                       _Q + "return JSON.stringify({ data: { id: q.cita_id, id_estado: 1, estado_cita: 'Anulado', _simulado: true } });"),
    "crear_paciente_dentalink": ({"nombre": "Ana", "apellidos": "Pérez", "celular": "5493880000000"},
                                 _Q + "return JSON.stringify({ data: { id: 990000002, nombre: q.nombre, apellidos: q.apellidos, celular: q.celular, _simulado: true } });"),
    "confirmar_turno": ({"cita_id": 123},
                        _Q + "return JSON.stringify({ data: { id: q.cita_id, id_estado: 18, estado_cita: 'Confirmado por whatsapp', _simulado: true } });"),
    "marcar_recordatorio_confirmado": ({"id_cita_dentalink": "eq.123"},
                                       _Q + "return JSON.stringify([{ id_cita_dentalink: String(q.id_cita_dentalink || '').replace('eq.', ''), confirmado_at: new Date().toISOString(), _simulado: true }]);"),
    "marcar_recordatorio_cancelado": ({"id_cita_dentalink": "eq.123"},
                                      _Q + "return JSON.stringify([{ id_cita_dentalink: String(q.id_cita_dentalink || '').replace('eq.', ''), cancelado_at: new Date().toISOString(), _simulado: true }]);"),
    "escalar_a_secretaria": ({"resumen": "Paciente consulta algo que no puedo resolver."},
                             _Q + "return JSON.stringify({ ok: true, enviado: true, resumen: q.resumen, _simulado: true });"),
}
LECTURA = ["ver_profesionales", "buscar_horarios", "buscar_paciente_dentalink", "ver_turnos_paciente", "obtener_historial_paciente", "consultar_recordatorios_abiertos", "buscar_conocimiento"]

# ------------------------------------------------------------------------------------------------ código de los nodos propios
JS_EDIT_FIELDS = """const e = $('Entrada').first().json;
const phone = String(e.phone || '');
return [{ json: { phone, phone_last10: phone.slice(-10), remoteJid: phone + '@s.whatsapp.net', name: e.pushName || '', pushName: e.pushName || '', text: String(e.texto || ''), instance: '' } }];"""
JS_PREPARAR = """const o = $('Edit Fields - Extraer Datos').first().json;
return [{ json: { phone: o.phone, remoteJid: o.remoteJid, name: o.name, key_id: '', instance: '', text: o.text } }];"""
JS_MENSAJE = """const ctx = $('Armar contexto').first().json;
const extra = [];
if (ctx.comprobante_marcado === true) extra.push('AVISO DEL SISTEMA: la imagen que mandó es un COMPROBANTE DE PAGO. Llamá a agente_confirmar (encargo: registrar el comprobante de pago que mandó).');
if (ctx.recordatorio_pendiente === true) extra.push('AVISO DEL SISTEMA: está respondiendo a un RECORDATORIO de turno (los turnos están en RECORDATORIOS YA ENVIADOS). Si su mensaje es una forma de sí, o el aviso o comprobante de pago de ese turno, llamá a agente_confirmar; si quiere cancelar o mover el turno, agente_cancelar.');
if (String($('Entrada').first().json.texto || '').toUpperCase().indexOf('[AUDIO]') >= 0 && ctx.audio_transcripto !== true) extra.push('AVISO DEL SISTEMA: mandó un audio que NO se pudo transcribir: pedile que lo escriba, con esta frase: ' + OrquestadorCore.TEXTOS.PEDIR_TEXTO);
if (ctx.staff_reciente === true) extra.push('AVISO DEL SISTEMA: el último mensaje que NO es del paciente lo escribió la clínica (STAFF) hace menos de 6 h: si el paciente solo le contesta a la clínica o no pide nada nuevo, llamá no_responder.');
return [{ json: { sistema: ctx.sistema_orq + '\\n\\nCONTEXTO DE ESTE MENSAJE (lo arma el sistema; es para vos: los especialistas NO lo ven, pasales en el encargo solo lo que necesiten):\\n' + ctx.contexto + (extra.length ? '\\n\\n' + extra.join('\\n\\n') : '') } }];"""
JS_VERIFICAR = """const r = (n) => { try { const x = $(n); return x.isExecuted ? (x.first().json || null) : null; } catch (y) { return null; } };
const e = $('Entrada').first().json;
const ctx = $('Armar contexto').first().json;
const v = V6Salida.verificar({ salida: r('""" + PADRE + """'), texto_paciente: e.texto, modo: e.modo, contexto: ctx.contexto, consulta: ctx.consulta,
  ctx: { staff_reciente: ctx.staff_reciente === true, charla_de_la_clinica: ctx.charla_de_la_clinica === true, comprobante_marcado: ctx.comprobante_marcado === true } });
return [{ json: v }];"""
JS_SALIDA = """const e = $('Entrada').first().json;
const v = $('Verificar salida').first().json;
const vivo = e.modo === 'vivo';   // solo avisa con modo 'vivo' EXPLÍCITO
if (vivo) for (const a of (v.avisos || [])) { try { await this.helpers.httpRequest({ method: 'POST', url: '""" + GRUPO + """', qs: { phone: e.phone, resumen: a.texto }, json: true }); } catch (x) { /* el aviso nunca rompe la respuesta */ } }
const texto = v.texto; const silencio = v.silencio === true || !texto;
return [{ json: { texto, enviar: !silencio, silencio, derivar_triaje: false, triaje: null, texto_original: null, modo: vivo ? 'vivo' : 'sombra', motivo_chequeo: v.motivo_verificador || null, motivo_banlist: null,
  fallo_agente: v.fallo_agente === true, modo_humano: false, descartar_propuesta: false, tools: v.traza || [], agentes: v.agentes || [], plan: v.plan || {}, avisos: v.avisos || [],
  motivo_verificador: v.motivo_verificador || null, usado_respaldo: v.usado_respaldo === true } }];"""

NO_RESPONDER_DESC = ("No responderle nada al paciente (silencio): agradece o se despide sin pedir nada, avisa que está llegando, manda solo un sticker o emoji, 'ok' sin nada pendiente, "
                     "o le habla a la clínica sin pedir nada nuevo. No la combines con otros especialistas.")


def _cargar_v6():
    w = json.loads(FUENTE_V6.read_text(encoding="utf-8"))
    nodos = {n["name"]: n for n in w["nodes"]}
    return w, nodos


def _tools_de(w, agente):
    return [src for src, v in w["connections"].items() for l in v.get("ai_tool", [[]]) for d in l if d["node"] == agente]


def _copiar(g, n, x, y, params=None):
    """Copia un nodo del v6 tal cual (parámetros, versión, credenciales, banderas) a la posición (x, y)."""
    extra = {k: copy.deepcopy(v) for k, v in n.items() if k in ("credentials", "onError", "alwaysOutputData", "continueOnFail", "executeOnce", "retryOnFail", "maxTries", "waitBetweenTries")}
    return g._nodo(n["name"], n["type"], n["typeVersion"], params if params is not None else copy.deepcopy(n["parameters"]), x, y, extra)


def _simulada(g, n, x, y):
    ejemplo, js = SIMULADAS[n["name"]]
    desc = n["parameters"]["toolDescription"]
    return g._nodo(n["name"], "@n8n/n8n-nodes-langchain.toolCode", 1.3, {
        "name": n["name"], "description": "[MODO SOMBRA: no escribe en ningún sistema] " + desc, "language": "javaScript", "jsCode": js,
        "specifyInputSchema": True, "schemaType": "fromJson", "jsonSchemaExample": json.dumps(ejemplo, ensure_ascii=False)}, x, y)


def wf_v6_orquestador(modo_sombra=False, esfuerzo=ESFUERZO):
    w6, nodos6 = _cargar_v6()
    g = Grafo(NOMBRE_SOMBRA if modo_sombra else NOMBRE_VIVO)
    # ---- plomería (la del cerebro actual)
    g.trigger({"phone": "5490000000651", "texto": "Hola", "pushName": "", "modo": "vivo", "historial_json": ""}, 0, 300)
    g.postgres("Historial", SQL_HISTORIAL, "$json.phone", 220, 300)
    g.postgres("Recordatorios", SQL_RECORDATORIOS, f"{E}.phone", 440, 300, una_vez=True)
    g.postgres("Primer mensaje", SQL_PRIMERO, f"{E}.phone", 550, 420, una_vez=True)
    g.postgres("Datos del consultorio", SQL_DATOS, "''", 660, 300, una_vez=True)
    g.subworkflow("Identificar paciente", "@@ID:ver_turnos@@", {"tel": f"{E}.phone", "exec_id_actual": "$execution.id"}, 770, 300)
    g.redis_get("Redis GET propuesta (entrada)", f"'propuesta:' + {E}.phone", "prop_entrada_raw", 825, 420)
    g._nodo("Armar contexto", "n8n-nodes-base.code", 2, {"jsCode": "const PROMPT_ORQ = " + json.dumps(PROMPT_PADRE, ensure_ascii=False) + ";\n"
            + "".join((V7 / f"{m}.js").read_text(encoding="utf-8").rstrip() + "\n" for m in ("historial_core", "agenda_core", "orquestador_core")) + JS_CONTEXTO}, 880, 300)
    g.si("¿Charla de la clínica?", f"{CTX}.charla_de_la_clinica === true", 1100, 300)
    # ---- nodos que las expresiones de los prompts del v6 necesitan (mismo nombre, mismos campos)
    g.code("Edit Fields - Extraer Datos", JS_EDIT_FIELDS, 1320, 400)
    kb = _copiar(g, nodos6["Get KB Horarios y Precio"], 1540, 400)
    g.nodos[-1]["executeOnce"] = True
    ex = copy.deepcopy(nodos6["Extraer Horarios y Precio"])
    viejo = "const original = $('Parse Intent').item.json;"
    assert ex["parameters"]["jsCode"].count(viejo) == 1
    ex["parameters"]["jsCode"] = ex["parameters"]["jsCode"].replace(viejo, "const original = $('Edit Fields - Extraer Datos').first().json;")
    _copiar(g, ex, 1760, 400)
    g.code("Preparar Mensaje Final", JS_PREPARAR, 1980, 400)
    _code_con(g, "Armar mensaje del padre", JS_MENSAJE, 2200, 400, ("orquestador_core",))
    # ---- el PADRE
    g.agente(PADRE, "$('Preparar Mensaje Final').first().json.text", "$('Armar mensaje del padre').first().json.sistema", 2420, 400, max_iter=MAX_ITER)
    g.modelo("Modelo " + PADRE, "gpt-5-mini", esfuerzo, 2420, 700)
    g.conectar_ai("Modelo " + PADRE, PADRE, "ai_languageModel")
    mem = copy.deepcopy(nodos6["Postgres Chat Memory"])
    # misma memoria que el v6 (sessionKey = teléfono). En la variante sombra, y en toda ejecución que no sea 'vivo', otra clave: no se mezcla con la memoria real del paciente.
    pref = "'sombra:' + " if modo_sombra else f"({E}.modo === 'vivo' ? '' : 'sombra:') + "
    mem["parameters"]["sessionKey"] = "={{ " + pref + "$('Preparar Mensaje Final').first().json.phone }}"
    _copiar(g, mem, 2420, 900, mem["parameters"])
    g.conectar_ai(mem["name"], PADRE, "ai_memory")
    g._nodo("no_responder", "@n8n/n8n-nodes-langchain.toolCode", 1.1, {"name": "no_responder", "language": "javaScript", "description": NO_RESPONDER_DESC,
            "jsCode": "return JSON.stringify({ ok: true, silencio: true });"}, 2640, 80)
    g.conectar_ai("no_responder", PADRE, "ai_tool")

    # ---- los 5 especialistas del v6, COPIADOS, como Agent Tool del padre
    herramientas_vistas = {}
    y = 120
    for orig, tool in ESPECIALISTAS.items():
        a6 = nodos6[orig]
        p = a6["parameters"]
        params = {"toolDescription": DESC[tool], "text": ENCARGO_FROMAI, "hasOutputParser": False,
                  "options": {"systemMessage": aplicar_edits(orig, p["options"]["systemMessage"])}}
        for k, v in p["options"].items():
            if k != "systemMessage":
                params["options"][k] = copy.deepcopy(v)
        g._nodo(tool, "@n8n/n8n-nodes-langchain.agentTool", 2.2, params, 2900, y, {"onError": "continueRegularOutput"})
        # modelo del especialista (el mismo del v6)
        lm = next(s for s, v in w6["connections"].items() if any(d["node"] == orig for l in v.get("ai_languageModel", [[]]) for d in l))
        _copiar(g, nodos6[lm], 3200, y)
        g.conectar_ai(lm, tool, "ai_languageModel")
        g.conectar_ai(tool, PADRE, "ai_tool")
        # herramientas del especialista (compartidas: un nodo por herramienta, conectado a cada agente que la usaba)
        for t in _tools_de(w6, orig):
            if t not in herramientas_vistas:
                n6 = nodos6[t]
                yy = 60 + 90 * len(herramientas_vistas)
                if modo_sombra and t in SIMULADAS:
                    _simulada(g, n6, 3500, yy)
                else:
                    assert (not modo_sombra) or t in LECTURA, "herramienta nueva en el v6 sin clasificar (¿escribe?): " + t
                    _copiar(g, n6, 3500, yy)
                herramientas_vistas[t] = True
            g.conectar_ai(t, tool, "ai_tool")
        y += 200
    if g.nodos:  # embeddings de buscar_conocimiento (vector store): lo usa General en el v6
        for s, v in w6["connections"].items():
            for d in [d for l in v.get("ai_embedding", [[]]) for d in l]:
                if d["node"] in herramientas_vistas and not any(m["name"] == s for m in g.nodos):
                    _copiar(g, nodos6[s], 3800, 700)
                    g.conectar_ai(s, d["node"], "ai_embedding")

    # ---- después del padre: verificación por código y salida
    _code_con(g, "Verificar salida", JS_VERIFICAR, 4100, 300, ("chequeo_salida", "orquestador_core", "verificador_core", "v6_salida_core"))
    g._nodo("Salida", "n8n-nodes-base.code", 2, {"jsCode": JS_SALIDA}, 4320, 300)
    for a, b, s_ in [("Entrada", "Historial", 0), ("Historial", "Recordatorios", 0), ("Recordatorios", "Primer mensaje", 0), ("Primer mensaje", "Datos del consultorio", 0),
                     ("Datos del consultorio", "Identificar paciente", 0), ("Identificar paciente", "Redis GET propuesta (entrada)", 0), ("Redis GET propuesta (entrada)", "Armar contexto", 0),
                     ("Armar contexto", "¿Charla de la clínica?", 0), ("¿Charla de la clínica?", "Verificar salida", 0), ("¿Charla de la clínica?", "Edit Fields - Extraer Datos", 1),
                     ("Edit Fields - Extraer Datos", kb, 0), (kb, "Extraer Horarios y Precio", 0), ("Extraer Horarios y Precio", "Preparar Mensaje Final", 0),
                     ("Preparar Mensaje Final", "Armar mensaje del padre", 0), ("Armar mensaje del padre", PADRE, 0), (PADRE, "Verificar salida", 0), ("Verificar salida", "Salida", 0)]:
        g.conectar(a, b, s_)
    wf = g.json()
    for n in wf["nodes"]:   # ids estables: el build no mete ruido en git
        n["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "v6-orquestador/" + wf["name"] + "/" + n["name"]))
        if n["type"].endswith(".if"):
            n["parameters"]["conditions"]["conditions"][0]["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, "v6-orquestador/cond/" + wf["name"] + "/" + n["name"]))
    return wf
