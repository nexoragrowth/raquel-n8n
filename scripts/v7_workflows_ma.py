# -*- coding: utf-8 -*-
"""v7_workflows_ma.py — SUB-AGENTES del v7 con orquestador (08/10, orden de Lucas: "ponele bien los puntos y los límites a los sub agentes; 0 conversaciones").

Cada sub-agente es un workflow: Entrada → su modelo (con SUS herramientas de código, o ninguna) → "Armar salida" (código: OrquestadorCore.salida*).
  - Turnos      (AI Agent): ver_turnos, elegir_ficha, buscar_horarios, gestionar_turno (+confirma), confirmar_turno, lista_espera. Devuelve un CÓDIGO.
  - Pagos       (AI Agent): registrar_pago, datos_pago (moneda). Devuelve un CÓDIGO. No ve los DATOS (ni el alias ni el CBU).
  - Información (LLM sin herramientas): el único que redacta, 1 a 3 frases y solo con los DATOS (sin la KB 24 bancaria).
  - Urgencias   (AI Agent): derivar_triaje (la cita la pone el código con el mensaje completo). Devuelve un CÓDIGO.
El texto que ve el paciente lo arma el código con lo que devolvieron las herramientas (nunca el texto libre del modelo, salvo Información).
Contrato de entrada (todo lo pone el cerebro; el modelo solo decide lo de $fromAI): tel, exec_id_actual (la ejecución del CEREBRO: de ella dependen las claves de
Redis), modo, texto_paciente, ultimo_asiri, textos_paciente (JSON: mensajes del paciente de las últimas 12 h), turnos_json, contexto, datos, pedido.
Salida: {agente, texto, estado, codigo, herramientas, traza, fuera_de_alcance, urgencia, derivar, error_tecnico, ...}."""
import json

from v7_lib import V7, Grafo

PROMPTS = {k: (V7 / f"prompt_sub_{k}.md").read_text(encoding="utf-8").strip() for k in ("turnos", "pagos", "informacion", "urgencias")}

ENT = "$('Entrada').first().json"
EJEMPLO = {"tel": "5490000000651", "exec_id_actual": "0", "modo": "sombra", "texto_paciente": "Hola", "ultimo_asiri": "", "textos_paciente": "[]", "turnos_json": "[]",
           "contexto": "", "datos": "", "pedido": "", "propuesta_staff": ""}
F = {k: f"{ENT}.{k}" for k in ("tel", "exec_id_actual", "modo", "texto_paciente", "ultimo_asiri", "textos_paciente")}
AGENDA = {k: F[k] for k in ("tel", "exec_id_actual")}
ESCRIBE = {k: F[k] for k in ("tel", "exec_id_actual", "modo")}
CLINICA = {k: F[k] for k in ("tel", "exec_id_actual", "modo", "texto_paciente")}

# (nombre, clave del workflow, descripción para el modelo, campos fijos (código), campos que decide el modelo)
HERRAMIENTAS = [
    ("ver_turnos", "ver_turnos", "Refresca los turnos vigentes del celular (de todas las fichas). Los del contexto ya están consultados: usala solo si cambió algo. Sin ids.", AGENDA, {}),
    ("elegir_ficha", "elegir_ficha", "Fija para quién es el turno cuando el celular tiene varias fichas. Pasá el nombre o el DNI que dijo el paciente; el código lo verifica contra las fichas reales.",
     AGENDA, {"nombre": "Nombre y/o apellido del paciente tal como lo dijo, o vacío si dio el DNI.", "dni": "DNI del paciente si lo dio, o vacío."}),
    ("buscar_horarios", "buscar_horarios", "Busca los turnos disponibles; el sistema le muestra el bloque al paciente. Solo se puede reservar lo que esta herramienta ofreció. Día puntual: desde = hasta = esa fecha. Si ninguno le sirve: desde = el día siguiente al último ofrecido (máximo dos bloques por conversación).",
     AGENDA, {"desde": "Opcional. Fecha YYYY-MM-DD desde la que buscar.", "hasta": "Opcional. Fecha límite inclusiva YYYY-MM-DD (para un día puntual, la misma que desde)."}),
    ("gestionar_turno", "gestionar_turno", "Reserva, suma, cambia o cancela un turno en dos pasos. 1.º: con los datos, devuelve la confirmación que el sistema le muestra al paciente (no escribe nada). 2.º: si en su PRÓXIMO mensaje el paciente la acepta, llamala con confirma=\"si\": el código verifica que vio esa confirmación y recién ahí escribe en la agenda. Tipos: cambio, reserva, sumar, cancelacion. Paciente nuevo: tipo reserva + nuevo_nombre, nuevo_apellido y nuevo_dni.",
     {**F}, {"tipo": "cambio | reserva | sumar | cancelacion", "fecha": "Fecha YYYY-MM-DD del turno nuevo (vacío si es cancelacion). De buscar_horarios.", "hora": "Hora HH:MM del turno nuevo (vacío si es cancelacion). De buscar_horarios.",
                      "fecha_turno_viejo": "Fecha YYYY-MM-DD del turno que se cambia o cancela. Vacío si es reserva o sumar.",
                      "nuevo_nombre": "Solo paciente nuevo (sin ficha): su nombre, tal como lo escribió. Si no, vacío.", "nuevo_apellido": "Solo paciente nuevo: su apellido, tal como lo escribió. Si no, vacío.",
                      "nuevo_dni": "Solo paciente nuevo: su DNI, tal como lo escribió. Si no, vacío.",
                      "confirma": "si | vacío. Escribí si SOLO cuando el MENSAJE ACTUAL del paciente acepta la CONFIRMACIÓN PENDIENTE; en cualquier otro caso dejalo vacío."}),
    # (05/11, incidente José 331596) El paciente acepta un CAMBIO que le propuso la clínica a mano. El modelo COPIA del mensaje de la clínica (entiende "8 y 40",
    # "6 de la tarde", "este jueves"); el código verifica cada dato contra el mensaje crudo del staff (propuesta_staff, lo pone el cerebro) y contra la agenda.
    # Todo texto (nada booleano): el esquema string no tiene cómo romperse.
    ("aceptar_propuesta_clinica", "gestionar_turno", "El paciente ACEPTA la PROPUESTA DE LA CLÍNICA (mover su turno a otro día u horario que le ofreció el staff). Copiá los datos del mensaje de la clínica; el código los verifica contra ese mensaje y la agenda: si ya está cargado se lo confirma, si no le muestra la confirmación del cambio. Una vez.",
     {**F, "accion": "'propuesta_staff'", "propuesta_staff": f"{ENT}.propuesta_staff"},
     {"fecha": "Fecha YYYY-MM-DD del turno NUEVO que propone la clínica (\"ese mismo día\" = la del turno que se mueve).", "hora": "Hora HH:MM del turno NUEVO, en 24 h (\"8 y 40\" = 08:40; \"6 de la tarde\" = 18:00).",
      "fecha_turno_viejo": "Fecha YYYY-MM-DD del turno que tiene y se mueve (de los turnos vigentes del contexto).", "para": "Nombre del paciente si el mensaje de la clínica lo nombra; si no, vacío."}),
    # (21/10, incidente familia con dos turnos el mismo día) UNA llamada confirma todos los que correspondan: sin datos = todos los recordatorios
    # pendientes (lo que hacía el v6 con "Confirmo"); con fecha / hora / nombre = solo los que coinciden.
    # (21/10, Lucas) Cualquier forma de "sí" a un recordatorio confirma TODO: "Confirmo", "hola siii vamos a ir con martin", "ahí estaremos", "dale 👍".
    # Solo se limita si el paciente dice EXPLÍCITAMENTE que confirma uno solo o que otro no va. Nombrar con quién va NO limita.
    ("confirmar_turno", "confirmar_turno", "Confirma la asistencia cuando el paciente responde a un recordatorio con cualquier forma de sí (\"Confirmo\", \"hola siii vamos a ir con martin\", \"ahí estaremos\", \"dale 👍\", \"Pedro 9:50 e Hilario 10:30\"). UNA sola llamada y VACÍA: confirma TODOS sus recordatorios pendientes. Pasá fecha/hora/nombre SOLO si dice explícitamente que confirma uno solo o que otro no va (\"solo el de Pedro\", \"Hilario no puede\"); nombrar con quién va NO limita.",
     ESCRIBE, {"fecha": "Vacío casi siempre. Solo si el paciente dice que confirma UNO solo: su fecha YYYY-MM-DD.", "hora": "Vacío casi siempre. Solo si confirma UNO solo de dos el mismo día: su hora HH:MM.",
               "nombre": "Vacío casi siempre. Solo si dice que confirma el turno de UNO solo (\"solo el de Pedro\"): ese nombre. Nombrar con quién va NO cuenta."}),
    # (12/11, espejo real r017) sin turno vigente y sin haber visto horarios, el código no anota nada y pide buscar_horarios (v7/clinica_core.js).
    ("lista_espera", "clinica", "Anota para la clínica que el paciente quiere un turno antes si se libera uno: para adelantar el suyo, o cuando ninguno de los horarios que vio le sirve. Si no tiene turno vigente y todavía no vio horarios, primero buscar_horarios. Una vez por pedido.",
     {**CLINICA, "accion": "'espera'", "turnos_json": f"{ENT}.turnos_json", "ultimo_asiri": F["ultimo_asiri"]}, {"texto": "Opcional: hasta qué fecha o qué horarios le sirven."}),
    ("registrar_pago", "clinica", "Registra que el paciente avisó un pago o mandó un comprobante (la secretaria lo verifica). No valida montos.", {**CLINICA, "accion": "'pago'"}, {}),
    ("datos_pago", "clinica", "El paciente pide los datos para pagar o transferir (alias, CBU, la cuenta). El sistema pega los datos exactos.",
     {**CLINICA, "accion": "'datos_pago'"}, {"moneda": "pesos | otra (otra = dólares u otra moneda)"}),
    ("derivar_triaje", "clinica", "Pasa el mensaje del paciente al protocolo de urgencias de la clínica, que le responde por su cuenta. Una vez.", {**CLINICA, "accion": "'triaje'"}, {}),
]
POR_NOMBRE = {h[0]: h for h in HERRAMIENTAS}
TOOLS = {
    "turnos": ["ver_turnos", "elegir_ficha", "buscar_horarios", "gestionar_turno", "aceptar_propuesta_clinica", "confirmar_turno", "lista_espera"],
    "pagos": ["registrar_pago", "datos_pago"],
    "informacion": [],
    "urgencias": ["derivar_triaje"],
}
NOMBRES = {"turnos": "v7 Agente Turnos", "pagos": "v7 Agente Pagos", "informacion": "v7 Agente Informacion", "urgencias": "v7 Agente Urgencias"}
MAX_ITER = {"turnos": 6, "pagos": 4, "urgencias": 3}

SALIDA_JS = {
    "turnos": "let t = []; try { t = JSON.parse($('Entrada').first().json.turnos_json || '[]'); } catch (x) { t = []; }\nreturn [{ json: OrquestadorCore.salidaTurnos($('Agente').first().json || {}, { turnos: Array.isArray(t) ? t : [] }) }];",
    "pagos": "return [{ json: OrquestadorCore.salidaPagos($('Agente').first().json || {}) }];",
    # (12/11, r007) control por código: horas y montos que no están en los DATOS no salen (v7/info_core.js).
    "informacion": "const s = OrquestadorCore.salidaInformacion($('Agente').first().json || {});\nreturn [{ json: InfoCore.verificar(s, $('Entrada').first().json.datos || '') }];",
    "urgencias": "return [{ json: OrquestadorCore.salidaUrgencias($('Agente').first().json || {}) }];",
}


def wf_subagente(clave):
    g = Grafo(NOMBRES[clave])
    g.trigger(EJEMPLO, 0, 300)
    texto = ENT + ".contexto + '\\n\\nPEDIDO DEL ORQUESTADOR: ' + " + ENT + ".pedido"
    sistema = json.dumps(PROMPTS[clave], ensure_ascii=False) + (" + '\\n\\n' + " + ENT + ".datos" if clave == "informacion" else "")
    if clave == "informacion":
        g.cadena("Agente", texto, sistema, 300, 300)
    else:
        g.agente("Agente", texto, sistema, 300, 300, max_iter=MAX_ITER[clave])
    g.modelo("Modelo", "gpt-5-mini", "low", 300, 560)
    g.conectar_ai("Modelo", "Agente", "ai_languageModel")
    y = 80
    for t in TOOLS[clave]:
        n, wf_clave, desc, fijos, del_modelo = POR_NOMBRE[t]
        g.herramienta(n, desc, f"@@ID:{wf_clave}@@", fijos, del_modelo, 640, y)
        g.conectar_ai(n, "Agente", "ai_tool")
        y += 90
    g.code("Armar salida", SALIDA_JS[clave], 620, 300, usar=("orquestador_core", "info_core") if clave == "informacion" else ("orquestador_core",))
    g.conectar("Entrada", "Agente", 0)
    g.conectar("Agente", "Armar salida", 0)
    return g.json()


def wf_agente_turnos():
    return wf_subagente("turnos")


def wf_agente_pagos():
    return wf_subagente("pagos")


def wf_agente_informacion():
    return wf_subagente("informacion")


def wf_agente_urgencias():
    return wf_subagente("urgencias")
