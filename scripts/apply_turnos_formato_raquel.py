# -*- coding: utf-8 -*-
"""
apply_turnos_formato_raquel.py — el bot ofrece los turnos como los pidió la Dra. Raquel (WhatsApp, 2026-09-07):
un BLOQUE con los turnos más próximos, 2 de mañana + 2 de tarde, sin nombrar el sistema de gestión, y SIN
preguntarle nunca al paciente qué día ni qué franja quiere.

    Tenemos los próximos turnos disponibles:
    Por la mañana:
    * Jueves 24 de septiembre 8:00 , 8:40
    * Martes 29 de septiembre 8:40 , 9:20

    Por la tarde:
    * Miércoles 30 de septiembre 16:20
    * Lunes 5 de octubre 15:00 , 15:40

    Le sirve alguno?

Diseño, pedido textual, cómo probar y cómo revertir: docs/turnos-formato-2026-09-07.md
Tests del jsCode nuevo: node tests/test_turnos_formato.js

TRES WORKFLOWS (los dos primeros son los que producen el texto, el tercero el que lo transporta):

 A) GuDQ9VmKWZvQnerV  "Sub-WF - Buscar Horarios Validado"  (ACTIVO, 6 nodos -> 22)
    - "Cuando llama Agendar": el schema pasa de {fecha} a {fecha, desde}; los dos OPCIONALES.
    - "Validar fecha": sin fecha (o con una inválida/pasada) busca desde HOY. Ya no se le pide la fecha
      al paciente nunca. Se deja de leer franja/hora_minima: NUNCA llegaron (la tool sólo mapea
      `workflowInputs`; el array `fields` con franja/hora_minima era residuo de la toolWorkflow tv 1.x —
      ejecuciones 272491 / 272461 / 270492: franja:null, hora_minima:null siempre).
    - "GET Horarios Dentalink": se le saca el `?q=...` inline de la URL, que duplicaba el query param `q`
      (los dos codificaban lo mismo). El nodo sigue igual en todo lo demás, misma credencial.
    - NUEVOS (16): la cadena de paginado por cursor con dedupe, hasta N_PAGINAS=6 llamadas:
      "Acumular P1" -> "Faltan turnos? P1" -[true]-> "GET Horarios P2" -> "Acumular P2" -> ... hasta
      "Acumular P6". Cada IF corta apenas hay 2 días con mañana Y 2 días con tarde, y todas las salidas
      `false` van directo a "Format Slots".
      POR QUÉ 6 Y NO 3 (medido el 07/09 con GET read-only contra la agenda real): juntar 2 mañanas + 2
      tardes consume 3 páginas arrancando en 5 de las 6 fechas probadas, y con la agenda algo más ocupada
      (3 días por franja) hacen falta 4 y hasta 5. Con el tope en 3 no quedaba margen y, al agotarse,
      "Format Slots" omite la sección "Por la tarde" entera: el paciente recibe sólo mañanas, que es
      exactamente la captura #2 que motivó el pedido. Cada página extra cuesta ~0.7 s contra un turno de
      agente del v6 de 20-34 s. Los "GET Horarios P2..P6" llevan retryOnFail (la agenda tira 429 en ráfaga).
    - "Format Slots": deja de llamar a la agenda y sólo arma el texto. **ACÁ SE VA EL TOKEN DE DENTALINK
      HARDCODEADO**: el escaneo día-por-día (hasta 91 llamadas HTTP con el token adentro del jsCode, y sin
      deduplicar: sumaba el MISMO turno 3 veces) lo reemplazan nodos httpRequest con la credencial
      "Header Auth account 3", la misma que ya usa "GET Horarios Dentalink".
    - "Output Error": mismo camino, otro texto — deja de pedirle una fecha al paciente.

 B) 5cAWJxiWJ50hxEq3  "Sub-WF - CancelarReprogramar"  (ACTIVO, 35 nodos, MISMA cantidad)
    ES EL WORKFLOW DE LAS DOS CAPTURAS QUE MANDÓ LA DRA. El intent `cancelar_o_reprogramar` del v6 NO va
    a "Sub-Agent Cancelar" (ese nodo está huérfano, sin ninguna conexión main de entrada): va a
    "Execute Sub-WF Cancelar" -> este workflow, que tiene su PROPIA búsqueda de agenda. Si el fix se
    aplicara sólo al v6 + Buscar Horarios, las dos capturas seguirían pasando igual.
    - "Step 5" (línea 100 del jsCode): "...que dia o franja le viene mejor? (manana / tarde / fecha
      concreta)" -> se borra la pregunta: reprogramar SIEMPRE ofrece el bloque.
    - "Step 6b-prep": ya no arma el `q` de un solo día; decide desde cuándo buscar.
    - "Step 6b: GET Agendas" -> se reemplaza por "Step 6b: Buscar Horarios (bloque)" (executeWorkflow al
      workflow A). Mismo lugar en el canvas, mismas dos aristas.
    - "Step 6b-out": el mensaje ES el bloque; se va "Tengo disponibles en <sistema> los siguientes turnos
      próximos: ... / ... / ...".
    - "Step 0b": el detector de `oferta_horarios` aprende la primera línea del bloque, `last_bot_msg` pasa
      de 300 a 600 chars y se agregan tres campos nuevos leídos del último mensaje del bot: `oferta_bloque`
      (el bloque entero), `oferta_siguiente_desde` (desde cuándo pedir el lote siguiente) y
      `bloques_ofrecidos` (cuántos lotes vio ya). SIN el slice de 600 el paciente elige un turno del bloque
      y el parser de aceptación (Step 3.5a) ni arranca: se perdía la elección. SIN los tres campos, el que
      rechaza el bloque recibe EL MISMO bloque para siempre, porque "Step 5" volvía a buscar desde HOY.
    - "Step 5" además: (a) si el paciente pide una franja sobre el bloque que acaba de recibir, se le
      repiten las opciones de ESA franja sacadas del bloque anterior (sin volver a tocar la agenda y sin
      preguntarle nada) — la captura #2; (b) después de DOS bloques rechazados no hay un tercero: escala.
    - "Step 6d-prep": la hora que elige el paciente se normaliza a HH:MM antes del POST de reserva. El
      bloque escribe "8:40" (sin cero adelante, así lo pidió la Dra.) y el parser de aceptación la copia
      de ahí; la agenda espera "08:40".

 C) O155MqHgOSaNZ9ye  v6 (ACTIVO, 159 nodos, MISMA cantidad, ni una conexión tocada)
    - `buscar_horarios` (toolWorkflow): description entera nueva (sin fecha obligatoria, prohibido
      preguntar franja/fecha, devuelve un bloque para pegar, `desde` para el siguiente lote), se mapea
      `desde` y se borra el array `fields` muerto.
    - "Sub-Agent Agendar" (10 parches, incluida la línea de "= TOOLS DISPONIBLES =" que seguía diciendo
      "Param `fecha` OBLIGATORIO" y contradecía todo lo demás) / "Sub-Agent Cancelar" / "Sub-Agent
      General": reemplazos quirúrgicos de bloque
      (nunca se reconstruye el prompt desde prompts/v6_partials/: están STALE, faltan meses de fixes).
      NO se tocan las reglas duras (Asiri, [NO_REPLY], anti-injection, no calcular el día de la semana,
      escalación única). "Sub-Agent Confirmar" NO se toca: no tiene preguntas de franja/fecha y sus
      menciones al sistema de gestión son razonamiento interno, nunca texto al paciente.
    - "Necesita Formatting?" + "Split en Mensajes" + "Formatting Agent - WhatsApp": LAS TRES CAPAS QUE
      EVITAN QUE EL BLOQUE SE REESCRIBA. El bloque mide ~230 chars (>80) y no trae [NO_REPLY], así que hoy
      pasaría SIEMPRE por el Formatting Agent (gpt-5-mini), cuya REGLA #3 ordena "Horas SIEMPRE en 24hs
      con hs" y "Fechas con día y mes capitalizados": le agregaría "hs" a "9:20 , 10:40" y capitalizaría
      "septiembre", justo lo contrario de lo que pidió la Dra. Se agrega una 3ra condición al IF (el
      bloque no pasa por el LLM), un guard determinístico en "Split en Mensajes" (si el original traía el
      bloque y el formateado no es idéntico, se manda el original) y una REGLA #0.b en el prompt del
      formateador. Determinístico primero, prompt último.

REGLAS DURAS que cumple: sólo GET antes de cada PUT; aborta si el `versionId` cambió entre el GET del
backup PRE y el PUT (el v6 lo está tocando otra sesión: 153 -> 159 nodos hoy mismo); backups PRE y POST de
CADA workflow en workflows/history/; PUT sólo con name/nodes/connections/settings/staticData y settings
filtradas a la allowlist (los tres traen `availableInMCP`, que no está permitida y da 400); assert del
webhookId 'evo-webhook-v2' en el v6; idempotente (re-correr no cambia nada); aborta si tocaría cualquier
nodo o conexión fuera de la lista declarada; verificación post-PUT con un GET nuevo.

SECRETOS: ninguno en este archivo ni en los que embebe. El token de Dentalink SE ELIMINA del jsCode; la
autenticación pasa a ser la credencial httpHeaderAuth que ya usan los nodos vivos.

USO:
  python scripts/apply_turnos_formato_raquel.py [--dry-run]   # default: GET + diff de cada campo, no toca n8n
  python scripts/apply_turnos_formato_raquel.py --apply       # PRE -> PUT -> POST -> verificación, los 3 workflows
  python scripts/apply_turnos_formato_raquel.py --rollback workflows/history/<PRE>.json [otro.json ...]
"""
import argparse, copy, difflib, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_media_entrantes import api, clean_settings, conn_list, C, PUT_KEYS, SETTINGS_OK, WF_ID  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
LABEL = "turnos_formato_raquel"

WF_V6 = WF_ID                      # O155MqHgOSaNZ9ye
WF_BH = "GuDQ9VmKWZvQnerV"         # Sub-WF - Buscar Horarios Validado
WF_CANREP = "5cAWJxiWJ50hxEq3"     # Sub-WF - CancelarReprogramar
WEBHOOK = "Webhook - Evolution API"

# La primera línea del bloque. Es la marca que usan las tres capas anti-reescritura del v6.
MARCA_BLOQUE = "turnos disponibles:"

# ---------------- fuentes únicas (los mismos archivos que corre tests/test_turnos_formato.js) ----------------
def leer(*partes):
    # rstrip del salto final: los jsCode vivos de n8n no terminan en '\n' y un diff por eso solo es ruido.
    return (ROOT.joinpath(*partes)).read_text(encoding="utf-8").rstrip("\n")

JS_VALIDAR = leer("turnos", "validar_fecha.js")
JS_ACUMULAR = leer("turnos", "acumular_slots.js")
JS_FORMAT = leer("turnos", "format_slots.js")
JS_OUTPUT_ERROR = leer("turnos", "output_error.js")
JS_SPLIT = leer("turnos", "split_en_mensajes.js")
JS_CANREP_PREP = leer("turnos", "canrep_6b_prep.js")
JS_CANREP_OUT = leer("turnos", "canrep_6b_out.js")

# El mismo archivo alimenta los 3 nodos "Acumular": el marcador se reemplaza por el nombre del nodo
# anterior. Tiene que aparecer UNA sola vez o el .replace() de abajo pisaría otra cosa.
MARCA_PREVIO = "__NODO_PREVIO__"
if JS_ACUMULAR.count(MARCA_PREVIO) != 1:
    sys.exit(f"ERROR: turnos/acumular_slots.js tiene {JS_ACUMULAR.count(MARCA_PREVIO)} marcadores "
             f"{MARCA_PREVIO} (tiene que haber exactamente 1)")

# description nueva de la tool `buscar_horarios` del v6 (contrato C)
TOOL_DESC = (
    "Devuelve los PROXIMOS TURNOS DISPONIBLES de la Dra. Raquel, ya escritos como un bloque de texto listo "
    "para mandarle al paciente (turnos de mañana Y de tarde, los mas proximos).\n\n"
    "CUANDO LLAMARLA: SIEMPRE que el paciente quiere un turno, quiere cambiarlo o pregunta que hay "
    "disponible. Llamala DE UNA, sin preguntarle nada antes.\n\n"
    "PARAMETROS: ninguno es obligatorio.\n"
    "- `desde` (YYYY-MM-DD, opcional): SOLO para pedir el SIGUIENTE lote cuando el paciente ya rechazo "
    "todos los turnos que le ofreciste. Usa la fecha que te indica el `resultado` de la llamada anterior. "
    "En la primera llamada del turno de conversacion mandalo vacio.\n\n"
    "COMO SE USA LA RESPUESTA: `resultado` trae una instruccion corta y, al final, el MENSAJE EXACTO para "
    "el paciente (el mismo texto que viene en `bloque`). Pegalo TAL CUAL: sin reescribirlo, sin "
    "reordenarlo, sin agregar ni quitar turnos, sin agregarle 'hs', sin cambiar mayusculas ni acentos, sin "
    "partirlo en varios mensajes y sin nombrarle al paciente el sistema de gestion de la clinica.\n\n"
    "PROHIBIDO (pedido textual de la Dra. Raquel, 2026-09-07): preguntarle al paciente que franja de "
    "horario le viene bien o en que fecha concreta quiere el turno. La clinica atiende dias y horarios "
    "especificos: nosotros ofrecemos y el paciente elige de esas opciones.\n\n"
    "Llamala UNA sola vez por turno de conversacion. Si el `resultado` dice SIN TURNOS o ERROR_TECNICO, no "
    "inventes horarios y no le pidas una fecha: segui la instruccion que trae (escalar)."
)
# 4to argumento ('' como defaultValue): sin el, createNodeAsTool marca `desde` como REQUERIDO en el schema
# de la tool y el modelo tiene que mandarlo en TODAS las llamadas (tool-call invalido / reintento si lo omite).
TOOL_DESDE_EXPR = ("={{ $fromAI('desde', 'Opcional. Fecha YYYY-MM-DD desde la que buscar el SIGUIENTE lote "
                   "de turnos, solo si el paciente ya rechazo los que le ofreciste. Vacio en la primera "
                   "llamada.', 'string', '') }}")
TRIGGER_JSON_EXAMPLE = '{"fecha": "", "desde": ""}'

# ---------------- parches de texto (ancla exacta -> reemplazo), todos en archivos del repo ----------------
def par(carpeta, slug, ext):
    """Devuelve (ANTES, DESPUES) de un parche. El ANTES se extrajo del workflow VIVO, asi que el reemplazo
    es byte a byte o el script aborta: nunca se reconstruye un prompt entero desde los partials."""
    a = ROOT / carpeta / f"{slug}.antes.{ext}"
    b = ROOT / carpeta / f"{slug}.despues.{ext}"
    return (a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8"))


PROMPTS_DIR = "prompts/v6_partials/turnos"
PARCHES_DIR = "turnos/parches"

# v6: (nodo, campo, [slugs...]) — el campo es el systemMessage del agent
PARCHES_PROMPT = {
    "Sub-Agent Agendar": ["agendar_regla_franja", "agendar_formato_horas", "agendar_dia_semana_ej",
                          "agendar_tools_buscar_horarios", "agendar_paso3", "agendar_paso4", "agendar_paso5",
                          "agendar_anti_alucinacion", "agendar_paso7b", "agendar_regla_17hs"],
    "Sub-Agent Cancelar": ["cancelar_reprogramar"],
    "Sub-Agent General": ["general_hay_turnos", "general_capacidad"],
    "Formatting Agent - WhatsApp": ["fmt_regla0", "fmt_ejemplo"],
}
# canrep: (nodo, [slugs...]) — el campo es el jsCode
PARCHES_CANREP = {
    "Step 5: Decidir Accion Ejecutable": ["canrep_step5_reprogramar"],
    # el orden importa: `lote` mete el calculo ANTES del return y `slice` agrega los campos AL return.
    "Step 0b: Detect Multi-Turn State": ["canrep_step0b_oferta", "canrep_step0b_lote", "canrep_step0b_slice"],
    "Step 6d-prep: Build Reserva Body": ["canrep_step6d_hora"],
}

# ---------------- nodos declarados (tocar algo fuera de acá = abortar) ----------------
# N_PAGINAS: cuantas llamadas GET como MUCHO hace la busqueda. Tiene que coincidir con MAX_PAGINAS de
# turnos/acumular_slots.js (se verifica abajo) porque una es el codigo y la otra el cableado.
# POR QUE 6 (medido el 2026-09-07 con GET read-only contra la agenda real, no elegido a ojo): juntar 2 dias
# de manana + 2 de tarde -el minimo que pidio la Dra.- consume 3 paginas arrancando en 5 de las 6 fechas
# probadas (2026-11-01, 2026-10-20, 2026-12-15, 2027-01-05 y 2027-03-01; solo desde hoy alcanzan 2), y con
# la agenda algo mas ocupada (3 dias por franja) el mismo barrido pide 4 y hasta 5 paginas. Con el tope en 3
# NO quedaba margen: al agotarse, "Format Slots" omite la seccion "Por la tarde" entera y el paciente recibe
# solo mananas - la captura que motivo el pedido. Cada pagina extra cuesta ~0.7 s (medido) contra un turno
# de agente del v6 de 20-34 s. El corte real casi siempre lo da `completo`, no el tope.
N_PAGINAS = 6

BH_NUEVOS = ["Acumular P1"] + [n for p in range(1, N_PAGINAS)
                               for n in (f"Faltan turnos? P{p}", f"GET Horarios P{p + 1}", f"Acumular P{p + 1}")]
BH_TOCABLES = ["Cuando llama Agendar", "Validar fecha", "GET Horarios Dentalink", "Format Slots",
               "Output Error"] + BH_NUEVOS
CANREP_VIEJO_6B = "Step 6b: GET Agendas"
CANREP_NUEVO_6B = "Step 6b: Buscar Horarios (bloque)"
CANREP_TOCABLES = ["Step 0b: Detect Multi-Turn State", "Step 5: Decidir Accion Ejecutable",
                   "Step 6b-prep: Prep Query Horarios", CANREP_VIEJO_6B, CANREP_NUEVO_6B,
                   "Step 6b-out: Ofrecer Slots", "Step 6d-prep: Build Reserva Body"]
V6_TOCABLES = ["buscar_horarios", "Sub-Agent Agendar", "Sub-Agent Cancelar", "Sub-Agent General",
               "Formatting Agent - WhatsApp", "Necesita Formatting?", "Split en Mensajes"]

IDS = {CANREP_NUEVO_6B: "step6b-buscar-horarios"}
for _p in range(1, N_PAGINAS + 1):
    IDS[f"Acumular P{_p}"] = f"acum-p{_p}"
    IDS[f"Faltan turnos? P{_p}"] = f"faltan-p{_p}"
    IDS[f"GET Horarios P{_p}"] = f"get-horarios-p{_p}"

# el jsCode y el cableado tienen que declarar el MISMO tope o el ultimo IF mandaria a un nodo inexistente
if f"const MAX_PAGINAS = {N_PAGINAS};" not in JS_ACUMULAR:
    sys.exit(f"ERROR: turnos/acumular_slots.js no declara MAX_PAGINAS = {N_PAGINAS} "
             f"(el script cablea {N_PAGINAS} paginas). Se ajustan los dos juntos.")

DENTALINK_URL = "https://api.dentalink.healthatom.com/api/v1/agendas/"


# ---------------- helpers ----------------
def reemplazar(texto, antes, despues, etiqueta, cambios):
    """Reemplazo quirúrgico sobre el texto VIVO. Idempotente: si ya está aplicado, no toca nada.
    Aborta si el ancla no aparece (alguien editó el nodo en la UI) o si aparece más de una vez."""
    # El DESPUES se chequea PRIMERO a propósito: varios reemplazos CONSERVAN el texto viejo y le agregan
    # algo (p. ej. la regla del "hs" de Agendar, que suma la excepción del bloque al final de la misma
    # línea). Si se mirara el ANTES primero, re-correr el script volvería a aplicar el parche encima.
    if despues in texto:
        return texto, False                      # ya aplicado
    if antes in texto:
        if texto.count(antes) != 1:
            sys.exit(f"ERROR: el ancla de {etiqueta} aparece {texto.count(antes)} veces — abortado")
        cambios.append(f"{etiqueta}: {len(antes)} -> {len(despues)} chars")
        return texto.replace(antes, despues), True
    sys.exit(f"ERROR: no encontré el ancla de {etiqueta} en el texto vivo (ni el reemplazo ya aplicado).\n"
             f"       Alguien editó ese nodo en la UI: revisá el diff antes de seguir.\n"
             f"       Primeras líneas del ancla esperada:\n         "
             + "\n         ".join(antes.split("\n")[:3]))


def poner_js(nodo, js_nuevo, etiqueta, cambios, diffs):
    viejo = nodo["parameters"].get("jsCode", "")
    if viejo == js_nuevo:
        return False
    nodo["parameters"]["jsCode"] = js_nuevo
    cambios.append(f"{etiqueta}: jsCode {len(viejo)} -> {len(js_nuevo)} chars")
    diffs.append((etiqueta + " · jsCode", viejo, js_nuevo))
    return True


def http_dentalink(nombre, pos, cred, cursor_de):
    """Clon de 'GET Horarios Dentalink' para las páginas 2 y 3. Mismo tipo, misma credencial, mismo
    query param; lo único distinto es la fecha, que sale del cursor del Acumular anterior."""
    q = ("={{ JSON.stringify({ id_sucursal: { eq: 1 }, fecha: { eq: $('" + cursor_de +
         "').first().json.cursor }, duracion: { eq: 40 }, id_dentista: { eq: 1 } }) }}")
    # retryOnFail: durante el sondeo del 07/09 la agenda devolvio 429 tras una rafaga, y este diseno pasa de
    # 1 a hasta N_PAGINAS llamadas por turno de paciente, conviviendo con los otros nodos Dentalink del v6 y
    # con el workflow de recordatorios. Un 429 no rompe (continueOnFail + "Acumular" sigue con lo que haya)
    # pero degrada el bloque a solo-manana en silencio: un reintento con 2 s de espera lo evita.
    return {"id": IDS[nombre], "name": nombre, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": pos, "alwaysOutputData": True, "continueOnFail": True,
            "retryOnFail": True, "maxTries": 2, "waitBetweenTries": 2000,
            "parameters": {"url": DENTALINK_URL, "authentication": "genericCredentialType",
                           "genericAuthType": "httpHeaderAuth", "options": {}, "sendQuery": True,
                           "specifyQuery": "keypair",
                           "queryParameters": {"parameters": [{"name": "q", "value": q}]}},
            "credentials": {"httpHeaderAuth": copy.deepcopy(cred)}}


def if_seguir(nombre, pos, modelo):
    """IF booleano con la MISMA forma que el 'Fecha valida?' que ya vive en este workflow."""
    n = copy.deepcopy(modelo)
    n["id"], n["name"], n["position"] = IDS[nombre], nombre, pos
    cond = n["parameters"]["conditions"]["conditions"][0]
    cond["id"] = IDS[nombre] + "-c"
    cond["leftValue"] = "={{ $json.seguir }}"
    return n


def code_node(nombre, pos, js):
    return {"id": IDS[nombre], "name": nombre, "type": "n8n-nodes-base.code", "typeVersion": 2,
            "position": pos, "parameters": {"jsCode": js}}


def poner_nodo(nodes, nuevo):
    """Agrega o reemplaza por nombre conservando id/posición si el nodo ya existía (idempotencia)."""
    for i, n in enumerate(nodes):
        if n["name"] == nuevo["name"]:
            nuevo = copy.deepcopy(nuevo)
            nuevo["id"], nuevo["position"] = n["id"], n["position"]
            nodes[i] = nuevo
            return "reemplazado"
    nodes.append(nuevo)
    return "nuevo"


def mostrar_diff(etiqueta, antes, despues, contexto=1, max_linea=190):
    print(f"\n  ── {etiqueta}  ({len(antes)} -> {len(despues)} chars)")
    if antes == despues:
        print("     (sin cambios)")
        return
    corta = lambda s: (s[:max_linea] + " …") if len(s) > max_linea else s
    for line in difflib.unified_diff(antes.split("\n"), despues.split("\n"), lineterm="", n=contexto):
        if line.startswith(("---", "+++")):
            continue
        print("     " + corta(line))


def fuera_de_alcance(antes, despues, tocables, conns_afectadas):
    a = {n["name"]: n for n in antes["nodes"]}
    b = {n["name"]: n for n in despues["nodes"]}
    nodos = sorted((set(a) | set(b)) - set(tocables))
    nodos = [n for n in nodos if a.get(n) != b.get(n)]
    conns = sorted(set(antes["connections"]) | set(despues["connections"]))
    conns = [k for k in conns if k not in conns_afectadas
             and antes["connections"].get(k) != despues["connections"].get(k)]
    return nodos, conns


# ---------------- A) Sub-WF - Buscar Horarios Validado ----------------
def build_bh(wf):
    new = copy.deepcopy(wf)
    nodes, conns = new["nodes"], new["connections"]
    names = {n["name"]: n for n in nodes}
    cambios, diffs = [], []

    for req in ["Cuando llama Agendar", "Validar fecha", "Fecha valida?", "GET Horarios Dentalink",
                "Format Slots", "Output Error"]:
        if req not in names:
            sys.exit(f"ERROR: falta el nodo {req!r} en {WF_BH}")
    if conn_list(conns, "Fecha valida?", 0) != [C("GET Horarios Dentalink")] or \
       conn_list(conns, "Fecha valida?", 1) != [C("Output Error")]:
        sys.exit(f"ERROR: el cableado de 'Fecha valida?' no es el conocido: {conns.get('Fecha valida?')!r}")

    getdent = names["GET Horarios Dentalink"]
    cred = (getdent.get("credentials") or {}).get("httpHeaderAuth")
    if not cred or cred.get("id") != "TwN6eBWsydjMdsCM":
        sys.exit(f"ERROR: credencial httpHeaderAuth inesperada en 'GET Horarios Dentalink': {cred!r}")

    # trigger: fecha + desde, los dos opcionales
    trg = names["Cuando llama Agendar"]["parameters"]
    if trg.get("jsonExample") != TRIGGER_JSON_EXAMPLE:
        diffs.append(("Cuando llama Agendar · jsonExample", trg.get("jsonExample", ""), TRIGGER_JSON_EXAMPLE))
        cambios.append("Cuando llama Agendar: jsonExample declara {fecha, desde}")
        trg["jsonExample"] = TRIGGER_JSON_EXAMPLE

    poner_js(names["Validar fecha"], JS_VALIDAR, "Validar fecha", cambios, diffs)
    poner_js(names["Format Slots"], JS_FORMAT, "Format Slots", cambios, diffs)
    poner_js(names["Output Error"], JS_OUTPUT_ERROR, "Output Error", cambios, diffs)

    # el `?q=` inline duplicaba el query param `q` (los dos codifican lo mismo)
    if getdent["parameters"].get("url") != DENTALINK_URL:
        diffs.append(("GET Horarios Dentalink · url", getdent["parameters"].get("url", ""), DENTALINK_URL))
        cambios.append("GET Horarios Dentalink: URL sin el ?q= inline duplicado")
        getdent["parameters"]["url"] = DENTALINK_URL

    # los nodos del paginado, en una fila:
    #   GET Horarios Dentalink -> Acumular P1 -> Faltan turnos? P1 -[true]-> GET Horarios P2 -> Acumular P2 -> ...
    # y cada salida `false` (ya hay 2 dias de manana + 2 de tarde) va derecho a "Format Slots".
    y = getdent["position"][1]
    x = getdent["position"][0]
    paso = 220
    plan, i = [], 1
    for pag in range(1, N_PAGINAS + 1):
        previo = "" if pag == 1 else f"Acumular P{pag - 1}"
        plan.append(code_node(f"Acumular P{pag}", [x + paso * i, y], JS_ACUMULAR.replace(MARCA_PREVIO, previo)))
        i += 1
        if pag < N_PAGINAS:
            plan.append(if_seguir(f"Faltan turnos? P{pag}", [x + paso * i, y], names["Fecha valida?"]))
            i += 1
            plan.append(http_dentalink(f"GET Horarios P{pag + 1}", [x + paso * i, y], cred, f"Acumular P{pag}"))
            i += 1
    for nodo in plan:
        if poner_nodo(nodes, nodo) == "nuevo":
            cambios.append(f"nodo NUEVO {nodo['name']!r} ({nodo['type'].split('.')[-1]} v{nodo['typeVersion']})")
    # "Format Slots" se corre al final de la fila (cosmético: el orden lo dan las conexiones)
    pos_format = [x + paso * i, y]
    if names["Format Slots"]["position"] != pos_format:
        cambios.append(f"Format Slots: posición {names['Format Slots']['position']} -> {pos_format} (cosmético)")
        names["Format Slots"]["position"] = pos_format

    # cableado nuevo
    conns["GET Horarios Dentalink"] = {"main": [[C("Acumular P1")]]}
    for pag in range(1, N_PAGINAS + 1):
        if pag < N_PAGINAS:
            conns[f"Acumular P{pag}"] = {"main": [[C(f"Faltan turnos? P{pag}")]]}
            conns[f"Faltan turnos? P{pag}"] = {"main": [[C(f"GET Horarios P{pag + 1}")], [C("Format Slots")]]}
            conns[f"GET Horarios P{pag + 1}"] = {"main": [[C(f"Acumular P{pag + 1}")]]}
        else:
            conns[f"Acumular P{pag}"] = {"main": [[C("Format Slots")]]}   # ultima pagina: no hay otro GET
    return new, cambios, diffs


# ---------------- B) Sub-WF - CancelarReprogramar ----------------
def build_canrep(wf):
    new = copy.deepcopy(wf)
    nodes, conns = new["nodes"], new["connections"]
    names = {n["name"]: n for n in nodes}
    cambios, diffs = [], []

    for req in ["Step 0b: Detect Multi-Turn State", "Step 5: Decidir Accion Ejecutable",
                "Step 6b-prep: Prep Query Horarios", "Step 6b-out: Ofrecer Slots"]:
        if req not in names:
            sys.exit(f"ERROR: falta el nodo {req!r} en {WF_CANREP}")
    viejo = names.get(CANREP_VIEJO_6B)
    nuevo_ya = names.get(CANREP_NUEVO_6B)
    if not viejo and not nuevo_ya:
        sys.exit(f"ERROR: no está ni {CANREP_VIEJO_6B!r} ni {CANREP_NUEVO_6B!r} en {WF_CANREP}")
    if viejo and conn_list(conns, "Step 6b-prep: Prep Query Horarios", 0) != [C(CANREP_VIEJO_6B)]:
        sys.exit("ERROR: 'Step 6b-prep' no apunta a 'Step 6b: GET Agendas' — cableado inesperado")

    # parches quirúrgicos de jsCode
    for nodo, slugs in PARCHES_CANREP.items():
        js = names[nodo]["parameters"]["jsCode"]
        original = js
        for slug in slugs:
            antes, despues = par(PARCHES_DIR, slug, "js")
            js, _ = reemplazar(js, antes, despues, f"{nodo} · {slug}", cambios)
        if js != original:
            names[nodo]["parameters"]["jsCode"] = js
            diffs.append((nodo + " · jsCode", original, js))

    poner_js(names["Step 6b-prep: Prep Query Horarios"], JS_CANREP_PREP, "Step 6b-prep", cambios, diffs)
    poner_js(names["Step 6b-out: Ofrecer Slots"], JS_CANREP_OUT, "Step 6b-out", cambios, diffs)

    # GET Agendas (1 día) -> Execute Workflow al Sub-WF que arma el bloque
    ref = viejo or nuevo_ya
    llamada = {"id": nuevo_ya["id"] if nuevo_ya else IDS[CANREP_NUEVO_6B], "name": CANREP_NUEVO_6B,
               "type": "n8n-nodes-base.executeWorkflow", "typeVersion": 1.2, "position": ref["position"],
               "alwaysOutputData": True, "continueOnFail": True,
               "parameters": {"workflowId": {"__rl": True, "value": WF_BH, "mode": "id"},
                              "workflowInputs": {"mappingMode": "defineBelow",
                                                 "value": {"fecha": "", "desde": "={{ $json.desde }}"},
                                                 "matchingColumns": [], "schema": []},
                              "options": {}}}
    if viejo:
        nodes[[i for i, n in enumerate(nodes) if n["name"] == CANREP_VIEJO_6B][0]] = llamada
        cambios.append(f"{CANREP_VIEJO_6B!r} (httpRequest, 1 día de agenda) -> {CANREP_NUEVO_6B!r} "
                       f"(executeWorkflow -> {WF_BH})")
        diffs.append((f"{CANREP_VIEJO_6B} -> {CANREP_NUEVO_6B}",
                      json.dumps(viejo, ensure_ascii=False, indent=1), json.dumps(llamada, ensure_ascii=False, indent=1)))
    else:
        poner_nodo(nodes, llamada)
    conns.pop(CANREP_VIEJO_6B, None)
    conns["Step 6b-prep: Prep Query Horarios"] = {"main": [[C(CANREP_NUEVO_6B)]]}
    conns[CANREP_NUEVO_6B] = {"main": [[C("Step 6b-out: Ofrecer Slots")]]}
    return new, cambios, diffs


# ---------------- C) v6 ----------------
def build_v6(wf):
    new = copy.deepcopy(wf)
    nodes = new["nodes"]
    names = {n["name"]: n for n in nodes}
    cambios, diffs = [], []
    for req in V6_TOCABLES:
        if req not in names:
            sys.exit(f"ERROR: falta el nodo {req!r} en el v6")

    # 1) tool buscar_horarios
    tool = names["buscar_horarios"]["parameters"]
    if tool.get("description") != TOOL_DESC:
        diffs.append(("buscar_horarios · description", tool.get("description", ""), TOOL_DESC))
        cambios.append(f"buscar_horarios: description {len(tool.get('description',''))} -> {len(TOOL_DESC)} chars")
        tool["description"] = TOOL_DESC
    wi = tool.setdefault("workflowInputs", {})
    valor = {"fecha": "", "desde": TOOL_DESDE_EXPR}
    if wi.get("value") != valor:
        diffs.append(("buscar_horarios · workflowInputs.value",
                      json.dumps(wi.get("value", {}), ensure_ascii=False, indent=1),
                      json.dumps(valor, ensure_ascii=False, indent=1)))
        cambios.append("buscar_horarios: la fecha deja de ser obligatoria; se mapea `desde` para el siguiente lote")
        wi["value"] = valor
    campo = lambda n: {"id": n, "displayName": n, "required": False, "defaultMatch": False,
                       "display": True, "canBeUsedToMatch": True, "type": "string"}
    wi["schema"] = [campo("fecha"), campo("desde")]
    wi["mappingMode"] = "defineBelow"
    wi.setdefault("matchingColumns", [])
    wi["attemptToConvertTypes"] = False
    wi["convertFieldsToString"] = True
    if "fields" in tool:
        cambios.append("buscar_horarios: se borra el array `fields` muerto (franja/hora_minima nunca llegaron)")
        tool.pop("fields")

    # 2) prompts (reemplazos quirúrgicos sobre el vivo)
    for nodo, slugs in PARCHES_PROMPT.items():
        sm = names[nodo]["parameters"]["options"]["systemMessage"]
        original = sm
        for slug in slugs:
            antes, despues = par(PROMPTS_DIR, slug, "md")
            sm, _ = reemplazar(sm, antes, despues, f"{nodo} · {slug}", cambios)
        if sm != original:
            names[nodo]["parameters"]["options"]["systemMessage"] = sm
            diffs.append((nodo + " · systemMessage", original, sm))

    # 3) el bloque no pasa por el Formatting Agent (3ra condición del IF)
    cond = names["Necesita Formatting?"]["parameters"]["conditions"]
    ids = [c.get("id") for c in cond["conditions"]]
    if "c3-bloque-turnos" not in ids:
        antes = json.dumps(cond, ensure_ascii=False, indent=1)
        cond["conditions"].append({
            "id": "c3-bloque-turnos",
            "leftValue": "={{ $json.output }}",
            "rightValue": MARCA_BLOQUE,
            "operator": {"type": "string", "operation": "notContains"}})
        diffs.append(("Necesita Formatting? · conditions", antes, json.dumps(cond, ensure_ascii=False, indent=1)))
        cambios.append("Necesita Formatting?: 3ra condición AND — el bloque de turnos NO pasa por el LLM formateador")

    # 4) guard determinístico en Split en Mensajes
    poner_js(names["Split en Mensajes"], JS_SPLIT, "Split en Mensajes", cambios, diffs)
    return new, cambios, diffs


# ---------------- verificación ----------------
def verify_bh(wf):
    names = {n["name"]: n for n in wf["nodes"]}
    conns = wf["connections"]
    det = {"faltan": [n for n in BH_TOCABLES if n not in names]}
    det["validar_fecha_js"] = names.get("Validar fecha", {}).get("parameters", {}).get("jsCode") == JS_VALIDAR
    det["format_slots_js"] = names.get("Format Slots", {}).get("parameters", {}).get("jsCode") == JS_FORMAT
    det["output_error_js"] = names.get("Output Error", {}).get("parameters", {}).get("jsCode") == JS_OUTPUT_ERROR
    det["sin_token_en_jscode"] = all("Authorization" not in (n.get("parameters", {}).get("jsCode") or "")
                                     for n in wf["nodes"])
    det["sin_httprequest_en_code"] = all("helpers.httpRequest" not in (n.get("parameters", {}).get("jsCode") or "")
                                         for n in wf["nodes"])
    cadena = [conn_list(conns, "GET Horarios Dentalink", 0) == [C("Acumular P1")]]
    for pag in range(1, N_PAGINAS + 1):
        if pag < N_PAGINAS:
            cadena += [conn_list(conns, f"Acumular P{pag}", 0) == [C(f"Faltan turnos? P{pag}")],
                       conn_list(conns, f"Faltan turnos? P{pag}", 0) == [C(f"GET Horarios P{pag + 1}")],
                       conn_list(conns, f"Faltan turnos? P{pag}", 1) == [C("Format Slots")],
                       conn_list(conns, f"GET Horarios P{pag + 1}", 0) == [C(f"Acumular P{pag + 1}")]]
        else:
            cadena.append(conn_list(conns, f"Acumular P{pag}", 0) == [C("Format Slots")])
    det["cadena"] = all(cadena)
    det["credenciales_http"] = all((names.get(n, {}).get("credentials") or {}).get("httpHeaderAuth", {}).get("id")
                                   == "TwN6eBWsydjMdsCM"
                                   for n in ["GET Horarios Dentalink"] + [f"GET Horarios P{p}" for p in range(2, N_PAGINAS + 1)])
    det["fecha_valida_intacta"] = (conn_list(conns, "Fecha valida?", 0) == [C("GET Horarios Dentalink")]
                                   and conn_list(conns, "Fecha valida?", 1) == [C("Output Error")])
    return not det["faltan"] and all(v for k, v in det.items() if k != "faltan"), det


def verify_canrep(wf):
    names = {n["name"]: n for n in wf["nodes"]}
    conns = wf["connections"]
    det = {"nodo_llamada": CANREP_NUEVO_6B in names, "viejo_fuera": CANREP_VIEJO_6B not in names}
    llamada = names.get(CANREP_NUEVO_6B, {})
    det["llama_al_subwf"] = (llamada.get("type") == "n8n-nodes-base.executeWorkflow"
                             and llamada.get("parameters", {}).get("workflowId", {}).get("value") == WF_BH)
    det["cableado"] = (conn_list(conns, "Step 6b-prep: Prep Query Horarios", 0) == [C(CANREP_NUEVO_6B)]
                       and conn_list(conns, CANREP_NUEVO_6B, 0) == [C("Step 6b-out: Ofrecer Slots")]
                       and conn_list(conns, "Step 6b-out: Ofrecer Slots", 0) == [C("Step 7: Output Final")])
    det["6b_out_js"] = names.get("Step 6b-out: Ofrecer Slots", {}).get("parameters", {}).get("jsCode") == JS_CANREP_OUT
    det["6b_prep_js"] = names.get("Step 6b-prep: Prep Query Horarios", {}).get("parameters", {}).get("jsCode") == JS_CANREP_PREP
    js5 = names.get("Step 5: Decidir Accion Ejecutable", {}).get("parameters", {}).get("jsCode", "")
    det["step5_sin_pregunta"] = "que dia o franja le viene mejor" not in js5
    js0 = names.get("Step 0b: Detect Multi-Turn State", {}).get("parameters", {}).get("jsCode", "")
    det["step0b_marca"] = MARCA_BLOQUE in js0 and "slice(0, 600)" in js0
    det["step0b_lote"] = all(k in js0 for k in ("oferta_bloque", "oferta_siguiente_desde", "bloques_ofrecidos"))
    det["step5_arrastra_lote"] = "oferta_siguiente_desde" in js5 and "bloquesOfrecidos >= 2" in js5
    js6d = names.get("Step 6d-prep: Build Reserva Body", {}).get("parameters", {}).get("jsCode", "")
    det["step6d_hora_hhmm"] = "padStart(2, '0')" in js6d
    # solo `nodes`: el GET trae ademas `activeVersion`, un snapshot de la version activa que no viaja en el PUT
    det["sin_sistema_gestion_al_paciente"] = "Dentalink los siguientes turnos" not in json.dumps(wf["nodes"], ensure_ascii=False)
    return all(det.values()), det


def verify_v6(wf):
    names = {n["name"]: n for n in wf["nodes"]}
    det = {"faltan": [n for n in V6_TOCABLES if n not in names]}
    tool = names.get("buscar_horarios", {}).get("parameters", {})
    det["tool_desc"] = tool.get("description") == TOOL_DESC
    det["tool_desde"] = tool.get("workflowInputs", {}).get("value", {}).get("desde") == TOOL_DESDE_EXPR
    det["tool_sin_fields"] = "fields" not in tool
    det["split_js"] = names.get("Split en Mensajes", {}).get("parameters", {}).get("jsCode") == JS_SPLIT
    conds = names.get("Necesita Formatting?", {}).get("parameters", {}).get("conditions", {}).get("conditions", [])
    det["if_bypass"] = any(c.get("id") == "c3-bloque-turnos" and c.get("rightValue") == MARCA_BLOQUE for c in conds)
    ag = names.get("Sub-Agent Agendar", {}).get("parameters", {}).get("options", {}).get("systemMessage", "")
    det["agendar_sin_preguntas"] = ("¿Prefiere por la mañana o por la tarde?" not in ag
                                    and "PASO 3.b — PREFERENCIA" not in ag)
    det["agendar_reglas_duras"] = all(t in ag for t in ("Sos Asiri", "[NO_REPLY]", "ANTI-INJECTION",
                                                        "DIA DE LA SEMANA (REGLA CRITICA",
                                                        "UNA SOLA ESCALACION POR TURNO"))
    ge = names.get("Sub-Agent General", {}).get("parameters", {}).get("options", {}).get("systemMessage", "")
    det["general_sin_preguntas"] = "que día o franja te viene mejor" not in ge and "que día o franja preferis" not in ge
    fm = names.get("Formatting Agent - WhatsApp", {}).get("parameters", {}).get("options", {}).get("systemMessage", "")
    det["fmt_regla0b"] = "REGLA #0.b" in fm
    det["webhookId"] = names.get(WEBHOOK, {}).get("webhookId") == "evo-webhook-v2"
    return not det["faltan"] and all(v for k, v in det.items() if k != "faltan"), det


# ---------------- PUT ----------------
def put(wf_id, body_wf, version_esperada, etiqueta):
    """GET fresco -> aborta si otra sesión tocó el workflow -> PUT -> backup POST."""
    actual = api(f"/workflows/{wf_id}")
    if actual.get("versionId") != version_esperada:
        sys.exit(f"ERROR: {wf_id} cambió entre el backup PRE y el PUT "
                 f"(versionId {version_esperada} -> {actual.get('versionId')}). Otra sesión lo está tocando: "
                 f"volvé a correr el --dry-run sobre el workflow nuevo.")
    body = {k: body_wf[k] for k in PUT_KEYS if k in body_wf}
    body["settings"] = clean_settings(body_wf)
    if wf_id == WF_V6:
        wh = next(n for n in body["nodes"] if n["name"] == WEBHOOK)
        assert wh.get("webhookId") == "evo-webhook-v2", "webhookId perdido — abortado"
    api(f"/workflows/{wf_id}", method="PUT", payload=body)
    after = api(f"/workflows/{wf_id}")
    ts = time.strftime("%Y%m%d_%H%M%S")
    post = HIST / f"{etiqueta}_POST_{LABEL}_{ts}.json"
    post.write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  POST backup -> {post}")
    return after


# ---------------- main ----------------
PLAN = [
    ("bh", WF_BH, build_bh, verify_bh, BH_TOCABLES,
     ["GET Horarios Dentalink"] + BH_NUEVOS),
    ("canrep", WF_CANREP, build_canrep, verify_canrep, CANREP_TOCABLES,
     ["Step 6b-prep: Prep Query Horarios", CANREP_VIEJO_6B, CANREP_NUEVO_6B]),
    ("v6", WF_V6, build_v6, verify_v6, V6_TOCABLES, []),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="(default) GET + diff, no toca n8n")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback", nargs="+", metavar="BACKUP_PRE_JSON",
                    help="PUT de uno o más backups PRE (cada archivo sabe a qué workflow pertenece)")
    args = ap.parse_args()
    HIST.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    if args.rollback:
        for ruta in args.rollback:
            bk = json.loads(Path(ruta).read_text(encoding="utf-8"))
            wf_id = bk.get("id")
            if wf_id not in (WF_V6, WF_BH, WF_CANREP):
                sys.exit(f"ERROR: {ruta} no es un backup de ninguno de los 3 workflows (id={wf_id!r})")
            etiqueta = {WF_V6: "v6", WF_BH: "bh", WF_CANREP: "canrep"}[wf_id]
            vivo = api(f"/workflows/{wf_id}")
            pre = HIST / f"{etiqueta}_PRE_rollback_{LABEL}_{ts}.json"
            pre.write_text(json.dumps(vivo, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"rollback {etiqueta}: PRE de este rollback -> {pre}")
            after = put(wf_id, bk, vivo.get("versionId"), f"{etiqueta}_rollback")
            print(f"  ✅ {etiqueta} restaurado: {len(after['nodes'])} nodos, activo={after['active']}")
        return

    estado = []
    for etiqueta, wf_id, build, verify, tocables, conns_afectadas in PLAN:
        wf = api(f"/workflows/{wf_id}")
        print("=" * 110)
        print(f"{etiqueta.upper()}  {wf['name']!r} ({wf_id}) — {len(wf['nodes'])} nodos, activo={wf['active']}, "
              f"updatedAt={wf.get('updatedAt')}, versionId={wf.get('versionId')}")
        new, cambios, diffs = build(wf)
        nodos_fuera, conns_fuera = fuera_de_alcance(wf, new, tocables, conns_afectadas)
        print(f"\nCAMBIOS ({len(cambios)}):")
        for c in cambios or ["  (ninguno: ya está aplicado)"]:
            print("  - " + c if cambios else c)
        for et, a, b in diffs:
            mostrar_diff(et, a, b)
        print(f"\n  nodos: {len(wf['nodes'])} -> {len(new['nodes'])}")
        print(f"  fuera de la lista declarada: {len(nodos_fuera)} nodos {nodos_fuera}, "
              f"{len(conns_fuera)} conexiones {conns_fuera}")
        print(f"  settings que irían en el PUT: {clean_settings(new)} "
              f"(se filtran: {sorted(set((new.get('settings') or {}).keys()) - SETTINGS_OK)})")
        if nodos_fuera or conns_fuera:
            sys.exit(f"ERROR: el cambio tocaría algo fuera de lo declarado en {etiqueta} — abortado")
        estado.append((etiqueta, wf_id, wf, new, verify, bool(cambios)))

    if not args.apply:
        print("\n" + "=" * 110)
        print("[DRY-RUN] no se tocó n8n. Antes de --apply: `node tests/test_turnos_formato.js` (y el resto de "
              "tests/*.js). Para aplicar: --apply")
        return

    for etiqueta, wf_id, wf, new, verify, hubo_cambios in estado:
        print("=" * 110)
        if not hubo_cambios:
            print(f"{etiqueta}: sin cambios (idempotente), no se hace PUT")
            continue
        pre = HIST / f"{etiqueta}_PRE_{LABEL}_{ts}.json"
        pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{etiqueta}: PRE backup -> {pre}")
        after = put(wf_id, new, wf.get("versionId"), etiqueta)
        ok, det = verify(after)
        print(f"  verificación post-PUT: {det}")
        if not ok:
            sys.exit(f"ERROR: la verificación de {etiqueta} falló — revisar en la UI "
                     f"(rollback: --rollback {pre})")
        print(f"  ✅ {etiqueta} aplicado: {len(after['nodes'])} nodos, activo={after['active']}")
    print("\nPRIMERA PRUEBA (obligatoria, regla dura 8): desde un teléfono de prueba pedir un turno y "
          "verificar que llega UN solo mensaje con el bloque, sin 'hs' adentro, mes en minúscula y con las "
          "dos franjas; después pedir reprogramar (pasa por el Sub-WF CancelarReprogramar) y verificar el "
          "mismo bloque; después contestar 'a la tarde' y 'ninguno me sirve' para ver el recorte por franja "
          "y el lote siguiente. Al terminar: scripts/limpiar_numero_demo.py (regla dura 9).")
    print("OJO al leer el diff: el parche de 'Sub-Agent Cancelar' (cancelar_reprogramar) es CÓDIGO MUERTO — "
          "ese nodo no tiene ninguna conexión main de entrada en el v6 vivo. Las tres capturas que mandó la "
          "Dra. salen del Sub-WF CancelarReprogramar (Step 5 / Step 6b-out), que sí está parcheado. El "
          "parche del sub-agent queda por si algún día se lo vuelve a cablear.")


if __name__ == "__main__":
    main()
