# -*- coding: utf-8 -*-
"""
apply_v7_flag_lucas.py — 2026-10-09 · conecta el cerebro v7 (ORQUESTADOR + sub-agentes) al v6 vivo SOLO para los teléfonos con la clave Redis
`v7:tel:{tel}` == 'vivo' (hoy: el celular de Lucas). Todos los demás siguen por el v6 exactamente como hoy.

Base: docs/plan-conexion-v7-celular-lucas-2026-10-06.md (sección "Actualización 09/10 (orquestador)" = lo que vale).

PUNTO DE INSERCIÓN (09/10): DESPUÉS de toda la infraestructura que aplica a todos (Webhook Validator → Kill-switch /bot off → Bot enabled? →
Dentalink up? → Rate Limit → Es fromMe? (staff → memoria + modo humano) → Filtrar duplicados → multimedia → Buffer → Preparar Mensaje Final →
Build Router Context → Consultar Takeover/Bot Activo? (modo humano 1 h) → Check Session Age/Handle Stale Session/Clear Old Memory) y ANTES de las
regex del v6 que juzgan intención ('Pre-filtro Cierre', 'Gate Canned Directo'/'Es Canned Directo?', 'Es cierre?'):

  Clear Old Memory → V7: Redis GET modo → V7: ¿Vivo? ─[no]→ Pre-filtro Cierre (… el v6 de hoy, sin cambios)
                                                    └[sí]→ Triaje: Redis GET estado → Triaje: ¿Seguimiento? ─[hay triaje en curso]→ Triaje: Cargar Config (igual que hoy)
                                                                                                           └[no]→ V7: ¿Ruta v7?
  Triaje: Ruta Pre[normal] → V7: ¿Ruta v7? ─[no: v6, o el v7 ya derivó en esta ejecución]→ Router - Clasificar Intent (igual que hoy)
                                           └[sí]→ V7: Pre-Triaje Regex → V7: ¿Urgencia regex? ─[sí]→ V7: Derivar a Triaje → Triaje: Cargar Config
                                                                                              └[no]→ V7: Cerebro → V7: Adaptador → V7: ¿Deriva a triaje? ─[sí]→ V7: Derivar a Triaje
                                                                                                                                                    └[no]→ Fallback Output → … envío del v6

EDITA 5 nodos del v6 (guardas que son no-op para todo item sin _flow === 'v7'): Fallback Output, Canned Sidecar, Gate Pago Tratamiento,
Necesita Formatting? (sin Formatting Agent para v7) y Triaje: Evaluar (modo 'nuevo' si corrió 'V7: Derivar a Triaje'; fuente única triaje/evaluar.js).
Banlist Validator NO se toca: desde el 07/10 es un paso sin control para todos (apply_quitar_banlist_v6.py); el script verifica que siga así.

USO (Lucas corre todo lo que escribe; este script por defecto SOLO LEE):
  python scripts/apply_v7_flag_lucas.py                       # simulación: GET v6 + cerebro, prerrequisitos, diff, invariantes, pruebas offline
  python scripts/apply_v7_flag_lucas.py --ver-codigo          # ídem + el código completo de los nodos nuevos
  python scripts/apply_v7_flag_lucas.py --offline DIR         # ídem desde los JSON guardados por una simulación (sin red)
  python scripts/apply_v7_flag_lucas.py --apply               # check_triaje → re-GET + versionId → backup PRE → PUT → GET → backup POST → verificación
  python scripts/apply_v7_flag_lucas.py --flag-on [TEL] [--ttl SEG]   # imprime cómo prender el flag en Redis (no escribe nada)
  python scripts/apply_v7_flag_lucas.py --flag-off [TEL]      # imprime cómo apagarlo
  python scripts/apply_v7_flag_lucas.py --flag-status [TEL]   # imprime cómo verlo + lo que vio el v6 en sus últimas ejecuciones (solo GET)
VOLVER ATRÁS:  sin PUT → borrar la clave (`--flag-off`); con PUT → python scripts/restaurar_workflow.py workflows/history/<backup PRE> --apply
"""
import argparse, copy, difflib, json, os, re, subprocess, sys, tempfile, time, urllib.request, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
DRY = ROOT / "workflows" / "current" / "v7_flag"          # ignorado por git (contiene el workflow vivo)
CONEXION = ROOT / "v7" / "v6_conexion"
V6 = "O155MqHgOSaNZ9ye"
TEL_LUCAS = "5491161461034"
REDIS_CONTENEDOR = "redis-rwlw-redis-1"
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

# ---------------------------------------------------------------------------------------------------------------- nombres
N_GET, N_VIVO, N_RUTA = "V7: Redis GET modo", "V7: ¿Vivo?", "V7: ¿Ruta v7?"
N_REGEX, N_URG, N_CER, N_ADA, N_DERIF, N_DER = ("V7: Pre-Triaje Regex", "V7: ¿Urgencia regex?", "V7: Cerebro", "V7: Adaptador",
                                                 "V7: ¿Deriva a triaje?", "V7: Derivar a Triaje")
NUEVOS = [N_GET, N_VIVO, N_RUTA, N_REGEX, N_URG, N_CER, N_ADA, N_DERIF, N_DER]
# Salida que sigue un item de un teléfono SIN flag al pasar por un nodo nuevo (la "rama v6"). Un teléfono sin flag solo toca estos 3 nodos nuevos.
RAMA_V6 = {N_GET: 0, N_VIVO: 1, N_RUTA: 1}
CLEAR, PREFILTRO, TGET, SEGUI, RUTAPRE, ROUTER = ("Clear Old Memory", "Pre-filtro Cierre", "Triaje: Redis GET estado", "Triaje: ¿Seguimiento?",
                                                   "Triaje: Ruta Pre", "Router - Clasificar Intent")
CARGAR, FALLBACK, SIDECAR, GATEPAGO, NECFMT, EVALUAR, BANLIST = ("Triaje: Cargar Config", "Fallback Output", "Canned Sidecar", "Gate Pago Tratamiento",
                                                                  "Necesita Formatting?", "Triaje: Evaluar", "Banlist Validator")
EDITADOS = sorted([FALLBACK, SIDECAR, GATEPAGO, NECFMT, EVALUAR])

# ---------------------------------------------------------------------------------------------------------------- copia de Parse Intent
# Líneas 10 y 17-19 del jsCode VIVO de 'Parse Intent' (09/10). El script las extrae del nodo vivo y ABORTA si no son estas (si alguien cambió el
# criterio de urgencia del v6, hay que revisar a conciencia antes de copiarlo al camino v7).
PARSE_TEXTONORM = r"""const textoNorm = (text || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();"""
PARSE_URGENCIA = r"""const esUrgenciaFuerte = (/\b(dolor\w*|duele\w*|sangr\w*|hinchaz\w*|hinchad[oa]|fiebre|pincha\w*|lastima\w*)\b/.test(textoNorm) ||
  /\bse (me |le )?(salio|desprendio|despego|rompio|solto|cayo)\b.{0,40}\b(bracket|brackets|alambre|aparato|arco|banda|ligadura|expansor)/.test(textoNorm)) &&
  !/\b(sin dolor|no (me |le )?(duele|dolio)|no (tengo|tiene|siento|siente) (ningun |nada de )?(dolor|molestia)\w*|sin molestias)\b/.test(textoNorm);"""
MARCA_COPIA = "/*__COPIA_PARSE_INTENT__*/"

# ---------------------------------------------------------------------------------------------------------------- guardas (reemplazo único)
GUARDAS = {
    FALLBACK: ("return items.map(it => {\n  let output = (it.json.output || '').trim();",
               "return items.map(it => {\n  if (it.json._flow === 'v7') return it;   // v7 (apply_v7_flag_lucas.py): el orquestador ya decidió texto o silencio ([NO_REPLY]); no convertir en CANNED_SECRETARIA\n  let output = (it.json.output || '').trim();"),
    SIDECAR: ("const items = $input.all();\n\n// --- 1. texto REAL del paciente",
              "const items = $input.all();\nif (items.length && items[0].json._flow === 'v7') return items;   // v7 (apply_v7_flag_lucas.py): los datos de pago los pega el código del cerebro; Parse Intent no corrió\n\n// --- 1. texto REAL del paciente"),
    GATEPAGO: ("const items = $input.all();\n\nlet pacienteMsg = '';",
               "const items = $input.all();\nif (items.length && items[0].json._flow === 'v7') return items;   // v7 (apply_v7_flag_lucas.py): el pago de tratamiento lo deriva el cerebro; evita pisar la respuesta y el aviso doble\n\nlet pacienteMsg = '';"),
}
C5 = {"id": "c5-sin-reescritor-v7", "leftValue": "={{ ($json._flow || '') !== 'v7' }}", "rightValue": "",
      "operator": {"type": "boolean", "operation": "true", "singleValue": True}}
NECFMT_IDS = ["c1", "c2", "c3-bloque-turnos", "c4-respuesta-fija-sin-reescritor"]

# Triaje: Evaluar (fuente única triaje/evaluar.js): bloque viejo → nuevo. El script verifica drift cero contra el repo antes y después.
EVAL_VIEJO = """// Modo de entrada: si el Router/Parse Intent corrió en esta ejecución, venimos del Switch (nuevo).
let modo_entrada = "seguimiento";
try { if ($('Parse Intent').isExecuted) modo_entrada = "nuevo"; } catch (e) { modo_entrada = estado ? "seguimiento" : "nuevo"; }"""
EVAL_NUEVO = """// Modo de entrada: "nuevo" si corrió el Router/Parse Intent (Switch sobre Intent[2]) o si el item vino del v7 por 'V7: Derivar a Triaje'
// (regex antes del orquestador o derivar_triaje del orquestador). corrio() devuelve null si el nodo no existe en este workflow (p. ej. la sombra):
// ahí se mantiene el criterio viejo (hay estado → seguimiento, si no → nuevo). Sin esto una derivación del v7 entraría como "seguimiento",
// volvería como ruta_pre 'normal' y el v7 la recibiría otra vez (bucle) o el paciente se quedaría sin respuesta.
const corrio = (n) => { try { return $(n).isExecuted === true; } catch (e) { return null; } };
const corrioParse = corrio('Parse Intent');
let modo_entrada = (corrioParse === true || corrio('V7: Derivar a Triaje') === true) ? "nuevo" : (corrioParse === null ? (estado ? "seguimiento" : "nuevo") : "seguimiento");"""


# ================================================================================================================ API (solo GET salvo --apply)
def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())
import guarda_vivo  # noqa: E402  (12/11) freno: no pisar en n8n cambios que este repo no conoce (scripts/guarda_vivo.py)
api = guarda_vivo.envolver(api)


def ids_v7():
    return json.loads((ROOT / "v7" / "ids.json").read_text(encoding="utf-8"))


def leer_vivos(offline=None):
    """v6, cerebro, clínica y agente de urgencias: GET al n8n (o JSON guardados con --offline)."""
    ids = ids_v7()
    claves = {"v6": V6, "cerebro": ids["cerebro"], "clinica": ids["clinica"], "agente_urgencias": ids["agente_urgencias"]}
    if offline:
        d = Path(offline)
        return {k: json.loads((d / f"{k}.json").read_text(encoding="utf-8")) for k in claves}, ids
    return {k: api(f"/workflows/{wid}") for k, wid in claves.items()}, ids


# ================================================================================================================ utilidades de grafo
def por_nombre(wf):
    return {n["name"]: n for n in wf["nodes"]}


def arcos(conns):
    """Conjunto de arcos (origen, tipo, salida, destino, entrada) de un dict de connections de n8n."""
    out = set()
    for src, tipos in (conns or {}).items():
        for tipo, salidas in (tipos or {}).items():
            for i, lista in enumerate(salidas or []):
                for c in lista or []:
                    out.add((src, tipo, i, c["node"], c.get("index", 0)))
    return out


def colapsar(conns):
    """Arcos que ve un teléfono SIN flag: los nodos nuevos se reemplazan por la salida 'rama v6' que sigue su item (RAMA_V6).
    Si el resultado == arcos del PRE, el camino de todo teléfono sin flag es idéntico al de hoy (mismos orígenes, salidas y destinos)."""
    res = set()
    for (src, tipo, i, dst, idx) in arcos(conns):
        if src in NUEVOS:
            continue
        vistos = 0
        while dst in NUEVOS:
            if dst not in RAMA_V6:
                dst = "!!camino-v7:" + dst
                break
            sig = ((conns.get(dst) or {}).get("main") or [])
            sig = sig[RAMA_V6[dst]] if len(sig) > RAMA_V6[dst] else []
            if len(sig) != 1:
                dst = f"!!rama-v6-de-{dst}-con-{len(sig)}-destinos"
                break
            dst, idx = sig[0]["node"], sig[0].get("index", 0)
            vistos += 1
            if vistos > 10:
                dst = "!!ciclo"
                break
        res.add((src, tipo, i, dst, idx))
    return res


def arco(nodo):
    return {"node": nodo, "type": "main", "index": 0}


def if_bool(expr, cid):
    return {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                           "conditions": [{"id": cid, "leftValue": "={{ " + expr + " }}", "rightValue": "",
                                           "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                           "combinator": "and"}, "options": {}}


def nodo(nombre, tipo, version, params, x, y, **extra):
    return {"parameters": params, "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "raquel-n8n/v6/" + nombre)), "name": nombre, "type": tipo,
            "typeVersion": version, "position": [x, y], **extra}


def js(nombre):
    return (CONEXION / nombre).read_text(encoding="utf-8").rstrip() + "\n"


def evaluar_desde_repo(nuevo=True):
    """jsCode de 'Triaje: Evaluar' armado desde la fuente única (gate_red_flags.js + '\\n\\n' + evaluar.js con el prompt), con el bloque nuevo o el viejo."""
    gate = (ROOT / "triaje" / "gate_red_flags.js").read_text(encoding="utf-8")
    ev = (ROOT / "triaje" / "evaluar.js").read_text(encoding="utf-8")
    prompt = (ROOT / "triaje" / "prompt_clasificador.md").read_text(encoding="utf-8")
    if ev.count(EVAL_NUEVO) != 1 and ev.count(EVAL_VIEJO) != 1:
        raise SystemExit("ABORTO: triaje/evaluar.js no tiene ni el bloque viejo ni el nuevo de modo_entrada (¿lo cambió otra sesión?).")
    if nuevo and EVAL_NUEVO not in ev:
        ev = ev.replace(EVAL_VIEJO, EVAL_NUEVO)
    if not nuevo and EVAL_VIEJO not in ev:
        ev = ev.replace(EVAL_NUEVO, EVAL_VIEJO)
    return gate + "\n\n" + ev.replace("__SYSTEM_PROMPT_JSON__", json.dumps(prompt, ensure_ascii=False))


def copia_parse_intent(v6n):
    """Extrae del 'Parse Intent' VIVO la línea de textoNorm y el bloque esUrgenciaFuerte (3 líneas). Devuelve (texto, error)."""
    lineas = v6n["Parse Intent"]["parameters"].get("jsCode", "").split("\n")
    tn = [l for l in lineas if l.startswith("const textoNorm = ")]
    i = next((k for k, l in enumerate(lineas) if l.startswith("const esUrgenciaFuerte = ")), None)
    if len(tn) != 1 or i is None:
        return None, "no encuentro 'const textoNorm' / 'const esUrgenciaFuerte' en Parse Intent"
    j = next((k for k in range(i, min(i + 6, len(lineas))) if lineas[k].rstrip().endswith(".test(textoNorm);")), None)
    if j is None:
        return None, "no encuentro el fin del bloque esUrgenciaFuerte en Parse Intent"
    bloque = "\n".join(lineas[i:j + 1])
    if tn[0] != PARSE_TEXTONORM or bloque != PARSE_URGENCIA:
        return None, "el criterio de urgencia de Parse Intent CAMBIÓ respecto de la copia fijada en este script: revisar a mano antes de copiarlo"
    return tn[0] + "\n" + bloque, None


# ================================================================================================================ prerrequisitos
def prerrequisitos(viv, ids):
    """Devuelve (lista de [ok, texto]) — cualquier False aborta antes del diff."""
    v6, cer, cli, urg = viv["v6"], viv["cerebro"], viv["clinica"], viv["agente_urgencias"]
    n, c = por_nombre(v6), v6["connections"]
    r = []
    chk = lambda ok, txt: r.append([bool(ok), txt])
    chk(v6.get("active"), f"v6 activo (versionId {str(v6.get('versionId'))[:8]}, {len(v6['nodes'])} nodos)")
    chk(any(x.get("webhookId") == "evo-webhook-v2" for x in v6["nodes"]), "v6 conserva webhookId evo-webhook-v2")
    chk(not any(k.startswith("V7:") for k in n), "el v6 todavía no tiene nodos 'V7:' (no está aplicado)")
    faltan = [k for k in (CLEAR, PREFILTRO, TGET, SEGUI, RUTAPRE, ROUTER, CARGAR, FALLBACK, SIDECAR, GATEPAGO, NECFMT, EVALUAR, BANLIST, "Parse Intent",
                          "Es cierre?", "Preparar Mensaje Final", "Edit Fields - Extraer Datos", "Bot Activo?", "Check Session Age", "Handle Stale Session") if k not in n]
    chk(not faltan, "nodos del v6 que se usan existen" + (f" — FALTAN {faltan}" if faltan else ""))
    if faltan:
        return r
    def main(s, i):
        salidas = (c.get(s) or {}).get("main") or []
        return [(x["node"], x.get("index", 0)) for x in (salidas[i] or [])] if len(salidas) > i else []
    chk(main("Bot Activo?", 1) == [("Check Session Age", 0)] and main("Check Session Age", 0) == [("Handle Stale Session", 0)]
        and main("Handle Stale Session", 0) == [(CLEAR, 0)], "infraestructura antes del fork: Bot Activo?[no humano] → Check Session Age → Handle Stale Session → Clear Old Memory")
    chk(main(CLEAR, 0) == [(PREFILTRO, 0)], "Clear Old Memory → Pre-filtro Cierre (arco que se redirige al fork)")
    chk(main("Es cierre?", 1) == [(TGET, 0)] and main(TGET, 0) == [(SEGUI, 0)] and main(SEGUI, 0) == [(CARGAR, 0)], "Es cierre?[1] → Triaje: Redis GET estado → ¿Seguimiento?[0] → Cargar Config")
    chk(main(SEGUI, 1) == [(ROUTER, 0)] and main(RUTAPRE, 2) == [(ROUTER, 0)], "¿Seguimiento?[1] y Ruta Pre[2] → Router (arcos que se redirigen)")
    ent_router = sorted((s, t, i) for (s, t, i, d, _x) in arcos(c) if d == ROUTER)
    chk(ent_router == sorted([(SEGUI, "main", 1), (RUTAPRE, "main", 2), ("Router LM", "ai_languageModel", 0)]),
        f"el Router recibe solo esos 2 arcos main + Router LM (hoy: {ent_router})")
    refs_router = [k for k, x in n.items() if f"$('{ROUTER}')" in json.dumps(x.get("parameters", {}), ensure_ascii=False)]
    chk(not refs_router, "ningún nodo lee $('Router - Clasificar Intent')")
    lee_json = [k for k in (PREFILTRO, ROUTER) if re.search(r"\$json|\$input", json.dumps(n[k].get("parameters", {}), ensure_ascii=False))]
    chk(not lee_json, "Pre-filtro Cierre y el Router no leen $json/$input (el GET de Redis cambia el item que les llega)")
    chk(n[TGET]["type"] == "n8n-nodes-base.redis" and n[TGET].get("alwaysOutputData") and n[TGET].get("onError") == "continueRegularOutput"
        and (n[TGET].get("credentials") or {}).get("redis"), "Triaje: Redis GET estado es el molde fail-open (redis v1, alwaysOutputData, continueRegularOutput)")
    copia, err = copia_parse_intent(n)
    chk(copia, "Parse Intent: textoNorm + esUrgenciaFuerte iguales a la copia fijada" + (f" — {err}" if err else ""))
    bl = n[BANLIST]["parameters"].get("jsCode", "")
    chk("SACADO el 2026-10-07" in bl and "RegExp" not in bl and "test(" not in bl, "Banlist Validator sigue siendo paso sin control (apply_quitar_banlist_v6.py)")
    for k, (viejo, nuevo) in GUARDAS.items():
        code = n[k]["parameters"].get("jsCode", "")
        chk(code.count(viejo) == 1 and "_flow === 'v7'" not in code, f"{k}: ancla única y sin guarda v7 previa")
    conds = n[NECFMT]["parameters"]["conditions"]["conditions"]
    chk([x.get("id") for x in conds] == NECFMT_IDS and n[NECFMT]["parameters"]["conditions"].get("combinator") == "and", "Necesita Formatting?: las 4 condiciones esperadas, combinador 'and'")
    ev_vivo = n[EVALUAR]["parameters"].get("jsCode", "")
    chk(ev_vivo == evaluar_desde_repo(nuevo=False), "Triaje: Evaluar vivo == triaje/gate_red_flags.js + evaluar.js (drift cero, bloque modo_entrada viejo)")
    chk(n["Edit Fields - Extraer Datos"]["type"].endswith(".set"), "Edit Fields - Extraer Datos existe (pushName)")
    # ---- cerebro v7 (orquestador) ----
    cn = por_nombre(cer)
    chk(cer.get("id") == ids["cerebro"], f"cerebro = v7/ids.json['cerebro'] ({ids['cerebro']}), versionId {str(cer.get('versionId'))[:8]}, {len(cer['nodes'])} nodos")
    for k in ("Entrada", "Orquestador", "Despacho", "Reunir", "Salida", "Redis GET triaje", "Agente Urgencias", "Guardar en memoria", "Devolver"):
        chk(k in cn, f"cerebro tiene el nodo '{k}' (orquestador 08/10)")
    if all(k in cn for k in ("Entrada", "Salida", "Devolver", "Redis GET triaje", "Agente Urgencias", "Guardar en memoria")):
        ent = cn["Entrada"]
        ej = {}
        try:
            ej = json.loads(ent["parameters"].get("jsonExample") or "{}")
        except Exception:
            pass
        chk(ent["type"] == "n8n-nodes-base.executeWorkflowTrigger" and all(x in ej for x in ("phone", "texto", "pushName", "modo")),
            "cerebro.Entrada recibe {phone, texto, pushName, modo}")
        dv = cn["Devolver"]["parameters"].get("jsCode", "")
        faltan_dv = [x for x in ("texto:", "enviar:", "silencio:", "derivar_triaje:", "modo:", "modo_humano:", "tools:") if x not in dv]
        chk(not faltan_dv, "cerebro.Devolver devuelve texto/enviar/silencio/derivar_triaje/modo/modo_humano/tools" + (f" — FALTAN {faltan_dv}" if faltan_dv else ""))
        sal = cn["Salida"]["parameters"].get("jsCode", "")
        chk("e.modo === 'vivo'" in sal and "derivar_triaje" in sal and "guardar: vivo && !silencio" in sal,
            "cerebro.Salida: avisos/memoria solo con modo 'vivo' explícito y calcula derivar_triaje")
        chk("triaje_v7:" in json.dumps(cn["Redis GET triaje"]["parameters"]) and "$execution.id" in json.dumps(cn["Redis GET triaje"]["parameters"]),
            "cerebro.Redis GET triaje lee triaje_v7:{tel}:{exec}")
        chk("session_id" in cn["Guardar en memoria"]["parameters"].get("query", "") and "Salida" in json.dumps(cn["Guardar en memoria"]["parameters"]),
            "cerebro guarda su propia memoria (Guardar en memoria → n8n_chat_histories)")
        sin_id = [x["name"] for x in cer["nodes"] if x["type"] == "n8n-nodes-base.executeWorkflow"
                  and re.search(r"@@ID|PENDIENTE", json.dumps(x["parameters"].get("workflowId")))]
        chk(not sin_id, "cerebro: todos los sub-workflows con id resuelto" + (f" — SIN ID {sin_id}" if sin_id else ""))
        chk(cn["Agente Urgencias"]["parameters"]["workflowId"].get("value") == ids["agente_urgencias"], "cerebro.Agente Urgencias → v7/ids.json['agente_urgencias']")
        sal_main = {s for s, d in cer["connections"].items() if any(o for o in (d.get("main") or []))}
        en_main = {t["node"] for d in cer["connections"].values() for o in (d.get("main") or []) for t in (o or [])}
        term = sorted(x for x in en_main | sal_main if x not in sal_main)
        chk(term == ["Devolver"], f"cerebro: todo camino termina en 'Devolver' (terminales: {term})")
    # ---- herramienta de triaje del v7 ----
    un = por_nombre(urg)
    tool = un.get("derivar_triaje")
    chk(tool and any(t["node"] == "Agente" for o in (urg["connections"].get("derivar_triaje", {}).get("ai_tool") or []) for t in o)
        and json.dumps(tool["parameters"]).find(ids["clinica"]) >= 0, "v7 Agente Urgencias: tool derivar_triaje conectada (ai_tool) → v7 Tool - clinica")
    ln = por_nombre(cli)
    chk("Redis SET triaje" in ln and "triaje_v7:" in json.dumps(ln.get("Redis SET triaje", {}).get("parameters", {})), "v7 Tool - clinica: 'Redis SET triaje' deja la marca triaje_v7:{tel}:{exec}")
    return r


# ================================================================================================================ construcción
def construir(v6, ids):
    """Devuelve el workflow nuevo (copia) con los 9 nodos V7, 3 arcos redirigidos y 5 guardas. No toca nada en n8n."""
    wf = copy.deepcopy(v6)
    n, c = por_nombre(wf), wf["connections"]
    copia, err = copia_parse_intent(n)
    if err:
        raise SystemExit("ABORTO: " + err)
    cred_redis = copy.deepcopy(n[TGET]["credentials"])
    regex_js = js("pre_triaje_regex.js")
    if regex_js.count(MARCA_COPIA) != 1:
        raise SystemExit("ABORTO: v7/v6_conexion/pre_triaje_regex.js no tiene el marcador de la copia de Parse Intent.")
    regex_js = regex_js.replace(MARCA_COPIA, copia)
    y, y2 = 1648, 1872
    nuevos = [
        nodo(N_GET, "n8n-nodes-base.redis", 1, {"operation": "get", "propertyName": "v7_modo",
             "key": "={{ 'v7:tel:' + $('Preparar Mensaje Final').first().json.phone }}", "keyType": "string", "options": {}},
             10192, y, credentials=cred_redis, alwaysOutputData=True, onError="continueRegularOutput"),
        nodo(N_VIVO, "n8n-nodes-base.if", 2.2, if_bool("($json.v7_modo || '') === 'vivo'", "v7-vivo-c"), 10480, y),
        nodo(N_RUTA, "n8n-nodes-base.if", 2.2, if_bool(
            f"($('{N_GET}').isExecuted ? ($('{N_GET}').first().json.v7_modo || '') : '') === 'vivo' && !$('{N_DER}').isExecuted", "v7-ruta-c"), 11360, y),
        nodo(N_REGEX, "n8n-nodes-base.code", 2, {"jsCode": regex_js}, 11648, y),
        nodo(N_URG, "n8n-nodes-base.if", 2.2, if_bool("$json.urgencia_regex === true", "v7-urg-c"), 11936, y),
        nodo(N_CER, "n8n-nodes-base.executeWorkflow", 1.2, {
            "workflowId": {"__rl": True, "value": ids["cerebro"], "mode": "id"},
            "workflowInputs": {"mappingMode": "defineBelow", "value": {
                "phone": "={{ $('Preparar Mensaje Final').first().json.phone }}",
                "texto": "={{ $('Preparar Mensaje Final').first().json.text }}",
                "pushName": "={{ $('Edit Fields - Extraer Datos').first().json.pushName }}",
                "modo": "vivo"}, "matchingColumns": [], "schema": []},
            "options": {}}, 12224, y, alwaysOutputData=True, continueOnFail=True),
        nodo(N_ADA, "n8n-nodes-base.code", 2, {"jsCode": js("adaptador.js")}, 12512, y),
        nodo(N_DERIF, "n8n-nodes-base.if", 2.2, if_bool("$json.derivar_triaje === true", "v7-deriva-c"), 12800, y),
        nodo(N_DER, "n8n-nodes-base.code", 2, {"jsCode": js("derivar_a_triaje.js")}, 11936, y2),
    ]
    wf["nodes"].extend(nuevos)
    # --- arcos redirigidos (mismo índice de salida, nuevo destino) ---
    c[CLEAR]["main"][0] = [arco(N_GET)]
    c[SEGUI]["main"][1] = [arco(N_RUTA)]
    c[RUTAPRE]["main"][2] = [arco(N_RUTA)]
    # --- cadena nueva ---
    c[N_GET] = {"main": [[arco(N_VIVO)]]}
    c[N_VIVO] = {"main": [[arco(TGET)], [arco(PREFILTRO)]]}
    c[N_RUTA] = {"main": [[arco(N_REGEX)], [arco(ROUTER)]]}
    c[N_REGEX] = {"main": [[arco(N_URG)]]}
    c[N_URG] = {"main": [[arco(N_DER)], [arco(N_CER)]]}
    c[N_CER] = {"main": [[arco(N_ADA)]]}
    c[N_ADA] = {"main": [[arco(N_DERIF)]]}
    c[N_DERIF] = {"main": [[arco(N_DER)], [arco(FALLBACK)]]}
    c[N_DER] = {"main": [[arco(CARGAR)]]}
    # --- guardas ---
    for k, (viejo, nuevo) in GUARDAS.items():
        code = n[k]["parameters"]["jsCode"]
        if code.count(viejo) != 1:
            raise SystemExit(f"ABORTO: ancla de {k} no es única.")
        n[k]["parameters"]["jsCode"] = code.replace(viejo, nuevo)
    n[NECFMT]["parameters"]["conditions"]["conditions"].append(copy.deepcopy(C5))
    viejo_ev = n[EVALUAR]["parameters"]["jsCode"]
    if viejo_ev.count(EVAL_VIEJO) != 1:
        raise SystemExit("ABORTO: el bloque modo_entrada de Triaje: Evaluar no es único en el nodo vivo.")
    n[EVALUAR]["parameters"]["jsCode"] = viejo_ev.replace(EVAL_VIEJO, EVAL_NUEVO)
    return wf


# ================================================================================================================ invariantes (sin red)
ESPERADOS_V7_A_V6 = {(N_VIVO, "main", 0, TGET, 0), (N_VIVO, "main", 1, PREFILTRO, 0), (N_RUTA, "main", 1, ROUTER, 0),
                     (N_DERIF, "main", 1, FALLBACK, 0), (N_DER, "main", 0, CARGAR, 0)}


def invariantes(pre, post, ids):
    """Lista de [ok, texto]. Compara el v6 de hoy (pre) con el propuesto/aplicado (post)."""
    r = []
    chk = lambda ok, txt: r.append([bool(ok), txt])
    pn, qn = por_nombre(pre), por_nombre(post)
    chk(sorted(set(qn) - set(pn)) == sorted(NUEVOS) and set(pn) <= set(qn), f"nodos: {len(pn)} → {len(qn)}; los nuevos son exactamente los 9 'V7: '")
    claves = ("type", "typeVersion", "credentials", "position", "disabled", "webhookId", "alwaysOutputData", "onError", "continueOnFail", "id")
    cambiados = sorted(k for k in pn if any(pn[k].get(x) != qn[k].get(x) for x in claves) or pn[k].get("parameters") != qn[k].get("parameters"))
    chk(cambiados == EDITADOS, f"solo cambian parameters de {EDITADOS} (cambiados: {cambiados})")
    solo_params = all(all(pn[k].get(x) == qn[k].get(x) for x in claves) for k in EDITADOS if k in qn)
    chk(solo_params, "en los 5 editados solo cambia 'parameters' (id/tipo/versión/credenciales/posición iguales)")
    a_pre, a_post = arcos(pre["connections"]), arcos(post["connections"])
    col = colapsar(post["connections"])
    chk(col == a_pre, "TELÉFONO SIN FLAG: con los nodos nuevos colapsados por su rama v6, el grafo es IDÉNTICO al de hoy"
        + ("" if col == a_pre else f" — sobran {sorted(col - a_pre)[:5]} faltan {sorted(a_pre - col)[:5]}"))
    quitados, agregados = a_pre - a_post, a_post - a_pre
    chk(quitados == {(CLEAR, "main", 0, PREFILTRO, 0), (SEGUI, "main", 1, ROUTER, 0), (RUTAPRE, "main", 2, ROUTER, 0)},
        f"se redirigen exactamente 3 arcos (Clear Old Memory→Pre-filtro, ¿Seguimiento?[1]→Router, Ruta Pre[2]→Router): {sorted(quitados)}")
    v7_a_v6 = {a for a in agregados if a[0] in NUEVOS and a[3] not in NUEVOS}
    chk(v7_a_v6 == ESPERADOS_V7_A_V6, f"del camino v7 al v6 solo salen: ¿Vivo?→Triaje GET estado/Pre-filtro, ¿Ruta v7?[no]→Router, ¿Deriva?[no]→Fallback, Derivar→Cargar Config")
    desde_v6 = {a for a in agregados if a[0] not in NUEVOS}
    chk(desde_v6 == {(CLEAR, "main", 0, N_GET, 0), (SEGUI, "main", 1, N_RUTA, 0), (RUTAPRE, "main", 2, N_RUTA, 0)}, "al camino v7 solo se entra por los 3 arcos redirigidos")
    ent_router = {(s, t, i) for (s, t, i, d, _x) in a_post if d == ROUTER}
    chk(ent_router == {(N_RUTA, "main", 1), ("Router LM", "ai_languageModel", 0)}, "el Router recibe main SOLO desde 'V7: ¿Ruta v7?'[no] (+ Router LM)")
    ent_cargar = {(s, i) for (s, t, i, d, _x) in a_post if d == CARGAR and t == "main"}
    chk(ent_cargar == {("Switch sobre Intent", 2), (SEGUI, 0), (N_DER, 0)}, f"Triaje: Cargar Config entra por Switch[2], ¿Seguimiento?[0] y V7: Derivar a Triaje ({sorted(ent_cargar)})")
    g = qn.get(N_GET, {})
    chk(g.get("alwaysOutputData") is True and g.get("onError") == "continueRegularOutput" and g.get("credentials") == pn[TGET].get("credentials")
        and g.get("parameters", {}).get("key") == "={{ 'v7:tel:' + $('Preparar Mensaje Final').first().json.phone }}",
        "V7: Redis GET modo es fail-open (Redis caído → rama v6) con la credencial de Triaje: Redis GET estado")
    ce = qn.get(N_CER, {}).get("parameters", {})
    chk(ce.get("workflowId", {}).get("value") == ids["cerebro"] and ce.get("workflowInputs", {}).get("value", {}).get("modo") == "vivo"
        and qn.get(N_CER, {}).get("continueOnFail") is True, "V7: Cerebro → v7/ids.json['cerebro'], modo literal 'vivo', continueOnFail")
    rx = qn.get(N_REGEX, {}).get("parameters", {}).get("jsCode", "")
    chk(PARSE_URGENCIA in rx and PARSE_TEXTONORM in rx and MARCA_COPIA not in rx, "V7: Pre-Triaje Regex contiene la copia textual de esUrgenciaFuerte del Parse Intent vivo")
    for k in (N_ADA, N_DER, N_REGEX):
        code = qn.get(k, {}).get("parameters", {}).get("jsCode", "")
        chk(not re.search(r"INSERT|n8n_chat_histories|chat_histor|r\.avisos|postgres", code, re.I), f"{k} no escribe memoria ni reenvía los avisos del cerebro")
    conds = qn[NECFMT]["parameters"]["conditions"]["conditions"]
    chk(conds[:4] == pn[NECFMT]["parameters"]["conditions"]["conditions"] and len(conds) == 5 and conds[4] == C5, "Necesita Formatting?: 4 condiciones intactas + c5 (sin Formatting Agent para v7)")
    chk(qn[EVALUAR]["parameters"]["jsCode"] == evaluar_desde_repo(nuevo=True), "Triaje: Evaluar == fuente única parcheada (triaje/evaluar.js)")
    con_v7 = sorted(k for k, x in qn.items() if k not in NUEVOS and "V7:" in json.dumps(x.get("parameters", {}), ensure_ascii=False))
    chk(con_v7 == [EVALUAR], f"fuera de los nodos nuevos solo 'Triaje: Evaluar' nombra un nodo V7 ({con_v7})")
    chk(any(x.get("webhookId") == "evo-webhook-v2" for x in post["nodes"]), "webhookId evo-webhook-v2 conservado")
    for k in ("Postgres Chat Memory", "Formatting Agent - WhatsApp", BANLIST, "Gate Humano Final", "Split en Mensajes", "Gate Error Tecnico", "Armar filas canned"):
        chk(pn[k] == qn[k], f"'{k}' intacto")
    return r


# ================================================================================================================ pruebas offline (harness)
def correr_harness(casos):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(casos, f, ensure_ascii=False)
        ruta = f.name
    try:
        p = subprocess.run(["node", str(ROOT / "tests" / "harness_code_node.mjs"), ruta], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        if p.returncode != 0:
            raise SystemExit("harness falló: " + p.stderr[-800:])
        return {x["id"]: x for x in json.loads(p.stdout)}
    finally:
        os.unlink(ruta)


def expr_de(nodo_if, i=0):
    lv = nodo_if["parameters"]["conditions"]["conditions"][i]["leftValue"]
    assert lv.startswith("={{") and lv.endswith("}}"), lv
    return lv[3:-2].strip()


def pruebas_offline(pre, post):
    """Corre el JS REAL de los nodos (nuevos y guardas) con tests/harness_code_node.mjs. Devuelve lista de [ok, texto]."""
    pn, qn = por_nombre(pre), por_nombre(post)
    r = []
    chk = lambda ok, txt: r.append([bool(ok), txt])
    PM = lambda t: {"Preparar Mensaje Final": {"text": t, "phone": TEL_LUCAS, "remoteJid": TEL_LUCAS + "@s.whatsapp.net"}}
    casos = []
    # --- 1) guardas: viejo (vivo) vs nuevo, items v6 idénticos; items v7 pasan sin tocar ---
    v6_items = [("confirmo", {"output": "Su turno quedó confirmado para el jueves."}), ("cuanto sale la consulta?", {"output": "[NO_REPLY]"}),
                ("me pasás el alias por favor?", {"output": "Claro, ya le paso.", "_flow": "cancelar_subwf"}), ("ok", {"output": ""}),
                ("puedo pagar la cuota del tratamiento?", {"output": "Le cuento cómo es el pago."}), ("gracias", {"output": "[NO_REPLY]"})]
    v7_items = [("muchas gracias doctora, buenísimo", {"output": "[NO_REPLY]", "_flow": "v7", "derivar_triaje": False}),
                ("me pasás el alias por favor?", {"output": "Le paso los datos para transferir:\nAlias: x", "_flow": "v7"}),
                ("quiero pagar la cuota del tratamiento", {"output": "Le paso su consulta a la secretaria.", "_flow": "v7"})]
    for k in GUARDAS:
        for j, (t, it) in enumerate(v6_items + v7_items):
            for lado, wf in (("viejo", pn), ("nuevo", qn)):
                casos.append({"id": f"g|{k}|{j}|{lado}", "codigo": wf[k]["parameters"]["jsCode"], "input": it, "nodos": PM(t)})
    # --- 2) V7: Pre-Triaje Regex ---
    rx = [("se me salió un bracket y me duele", True), ("quiero cambiar el turno, sin dolor", False), ("no va porque tiene fiebre", True),
          ("hola, quiero sacar un turno", False), ("Mi hija esta incomoda, no come desde ayer con el aparato", False), ("se le cayó el aparato", True),
          ("me sangra la encía", True), ("no me duele nada, solo quiero el precio", False)]
    for j, (t, _e) in enumerate(rx):
        casos.append({"id": f"rx|{j}", "codigo": qn[N_REGEX]["parameters"]["jsCode"], "input": {}, "nodos": PM(t)})
    # --- 3) V7: Adaptador ---
    ada = {
        "texto": {"texto": "La primera consulta cuesta $50.000.", "enviar": True, "silencio": False, "derivar_triaje": False, "modo": "vivo", "tools": [{"tool": "orquestador"}]},
        "menu": {"texto": "Hola! Soy Asiri…\n1. Sacar un turno\n2. …\nEscriba el número de la opción o lo que necesita.", "enviar": True, "silencio": False, "modo": "vivo"},
        "humano": {"texto": "Le paso con la secretaria; le responde por este chat.", "enviar": True, "silencio": False, "modo": "vivo", "modo_humano": True},
        "silencio": {"texto": None, "enviar": False, "silencio": True, "derivar_triaje": False, "modo": "vivo"},
        "derivar": {"texto": None, "enviar": False, "silencio": True, "derivar_triaje": True, "triaje": {"motivo": "derivar_triaje"}, "modo": "vivo"},
        "derivar_sombra": {"texto": None, "enviar": False, "silencio": True, "derivar_triaje": True, "modo": "sombra"},
        "texto_sombra": {"texto": "Listo, le reservé el turno.", "enviar": True, "silencio": False, "modo": "sombra"},
        "error": {"error": {"message": "boom"}},
        "vacio": {},
        "sin_texto": {"texto": "", "enviar": True, "silencio": False, "modo": "vivo"},
    }
    for k, entrada in ada.items():
        casos.append({"id": f"ada|{k}", "codigo": qn[N_ADA]["parameters"]["jsCode"], "input": entrada, "nodos": PM("x")})
    # --- 4) V7: Derivar a Triaje ---
    casos.append({"id": "der|regex", "codigo": qn[N_DER]["parameters"]["jsCode"], "nodos": {N_REGEX: {"urgencia_regex": True}}})
    casos.append({"id": "der|cerebro", "codigo": qn[N_DER]["parameters"]["jsCode"], "nodos": {N_REGEX: {"urgencia_regex": False}}})
    casos.append({"id": "der|sin_regex", "codigo": qn[N_DER]["parameters"]["jsCode"], "nodos": {}})
    # --- 5) expresiones de los IF (n8n: salida 0 = verdadero) ---
    def ex(cid, nodo_if, entrada, nodos=None, no_ej=None, i=0):
        casos.append({"id": cid, "codigo": "return [{ json: { v: (" + expr_de(nodo_if, i) + ") } }];", "input": entrada, "nodos": nodos or {}, "noEjecutados": no_ej or []})
    for j, e in enumerate([{"v7_modo": "vivo"}, {"v7_modo": None}, {}, {"error": {"message": "redis caído"}}, {"v7_modo": "sombra"}, {"v7_modo": "VIVO"}]):
        ex(f"vivo|{j}", qn[N_VIVO], e)
    ex("ruta|vivo", qn[N_RUTA], {}, {N_GET: {"v7_modo": "vivo"}}, [N_DER])
    ex("ruta|vivo_ya_derivo", qn[N_RUTA], {}, {N_GET: {"v7_modo": "vivo"}, N_DER: {"_flow": "v7"}})
    ex("ruta|sin_flag", qn[N_RUTA], {}, {N_GET: {"v7_modo": None}}, [N_DER])
    ex("ruta|redis_caido", qn[N_RUTA], {}, {N_GET: {"error": "x"}}, [N_DER])
    ex("ruta|get_no_corrio", qn[N_RUTA], {}, {}, [N_GET, N_DER])
    for j, e in enumerate([{"urgencia_regex": True}, {"urgencia_regex": False}, {}]):
        ex(f"urg|{j}", qn[N_URG], e)
    for j, e in enumerate([{"derivar_triaje": True}, {"derivar_triaje": False}, {"output": "x"}]):
        ex(f"deriva|{j}", qn[N_DERIF], e)
    for j, e in enumerate([{"output": "x"}, {"output": "x", "_flow": "cancelar_subwf"}, {"output": "x", "_flow": "v7"}]):
        ex(f"c5|{j}", qn[NECFMT], e, i=4)
    ex("c4|camino_v7", qn[NECFMT], {"output": "x", "_flow": "v7"}, {}, ["Gate Canned Directo"], i=3)
    res = correr_harness(casos)
    # --- veredictos ---
    j7 = len(v6_items)
    for k in GUARDAS:
        iguales = all(res[f"g|{k}|{j}|viejo"].get("json") == res[f"g|{k}|{j}|nuevo"].get("json") and res[f"g|{k}|{j}|viejo"].get("n") == res[f"g|{k}|{j}|nuevo"].get("n")
                      and "error" not in res[f"g|{k}|{j}|nuevo"] for j in range(j7))
        chk(iguales, f"{k}: {j7} items v6 → salida IDÉNTICA viejo/nuevo")
        pasa = all(res[f"g|{k}|{j}|nuevo"].get("json") == (v6_items + v7_items)[j][1] for j in range(j7, j7 + len(v7_items)))
        chk(pasa, f"{k}: items _flow 'v7' pasan sin tocar")
    chk(res[f"g|{FALLBACK}|{j7}|viejo"]["json"]["output"] != "[NO_REPLY]", "  (control) sin la guarda, Fallback Output convertía el silencio v7 en CANNED_SECRETARIA")
    malos = [t for j, (t, e) in enumerate(rx) if res[f"rx|{j}"].get("json", {}).get("urgencia_regex") is not e]
    chk(not malos, f"V7: Pre-Triaje Regex: {len(rx)} casos (paridad con Parse Intent)" + (f" — FALLAN {malos}" if malos else ""))
    o = {k: res[f"ada|{k}"].get("json") or {"error": res[f"ada|{k}"].get("error")} for k in ada}
    canned = "Le envío la información a la secretaria"
    chk(o["texto"]["output"] == ada["texto"]["texto"] and o["texto"]["_flow"] == "v7" and o["texto"]["derivar_triaje"] is False, "Adaptador: texto → output tal cual, _flow v7")
    chk(o["menu"]["output"] == ada["menu"]["texto"] and o["humano"]["output"] == ada["humano"]["texto"] and o["humano"]["_v7"]["modo_humano"] is True, "Adaptador: menú y pasar a humano → su texto tal cual")
    chk(o["silencio"]["output"] == "[NO_REPLY]" and o["silencio"]["derivar_triaje"] is False, "Adaptador: silencio → [NO_REPLY]")
    chk(o["derivar"]["output"] == "[NO_REPLY]" and o["derivar"]["derivar_triaje"] is True, "Adaptador: derivar_triaje (vivo) → al triaje del v6")
    chk(all(canned in o[k]["output"] and o[k]["derivar_triaje"] is False and o[k]["_v7"]["caso"] == "fallo" for k in ("derivar_sombra", "texto_sombra", "error", "vacio", "sin_texto")),
        "Adaptador: error del sub-workflow / vacío / sin texto / modo≠vivo → canned de secretaria + aviso [ACCIÓN] (nunca un texto de sombra)")
    chk(all(res[f"ada|{k}"].get("n") == 1 for k in ada), "Adaptador: siempre exactamente 1 item")
    chk([res[x]["json"]["via"] for x in ("der|regex", "der|cerebro", "der|sin_regex")] == ["regex", "cerebro", "cerebro"], "V7: Derivar a Triaje: via regex / cerebro / cerebro")
    v = lambda cid: (res[cid].get("json") or {}).get("v", res[cid].get("error"))
    chk([v(f"vivo|{j}") for j in range(6)] == [True, False, False, False, False, False], "V7: ¿Vivo?: solo el literal 'vivo' entra; null / sin clave / Redis caído / 'sombra' → v6")
    chk([v(x) for x in ("ruta|vivo", "ruta|vivo_ya_derivo", "ruta|sin_flag", "ruta|redis_caido", "ruta|get_no_corrio")] == [True, False, False, False, False],
        "V7: ¿Ruta v7?: vivo → v7; si el v7 ya derivó en esta ejecución → Router (sin bucle); sin flag / Redis caído → Router")
    chk([v(f"urg|{j}") for j in range(3)] == [True, False, False] and [v(f"deriva|{j}") for j in range(3)] == [True, False, False], "IF ¿Urgencia regex? y ¿Deriva a triaje?: booleano estricto")
    chk([v(f"c5|{j}") for j in range(3)] == [True, True, False], "Necesita Formatting? c5: v6 / cancelar_subwf → igual que hoy; v7 → sin Formatting Agent")
    chk(v("c4|camino_v7") is False, "Necesita Formatting? c4 en el camino v7 (Gate Canned Directo no corrió) evalúa false sin romper")
    # --- 6) suites del triaje (corren triaje/evaluar.js del repo) ---
    for cmd in (["node", "tests/test_triaje_nodos.js"], ["node", "triaje/test_gate.js"]):
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        chk(p.returncode == 0, " ".join(cmd[1:]) + ": " + (p.stdout.strip().splitlines() or ["?"])[-1])
    return r


# ================================================================================================================ diff legible
def imprimir_diff(pre, post, ver_codigo=False):
    pn, qn = por_nombre(pre), por_nombre(post)
    print("\n=== NODOS NUEVOS (9) ===")
    for k in NUEVOS:
        x = qn[k]
        p = x["parameters"]
        if "jsCode" in p:
            det = f"Code, {len(p['jsCode'].splitlines())} líneas (v7/v6_conexion/)"
        elif x["type"].endswith(".if"):
            det = "IF  " + expr_de(x)
        elif x["type"].endswith(".redis"):
            det = f"Redis GET {p['key']} → {p['propertyName']} (alwaysOutputData, onError continuar)"
        else:
            det = f"Execute Workflow {p['workflowId']['value']} con {json.dumps(p['workflowInputs']['value'], ensure_ascii=False)}"
        print(f"  + {k:24s} {det}")
        if ver_codigo and "jsCode" in p:
            print("\n".join("      | " + l for l in p["jsCode"].splitlines()))
    print("\n=== NODOS EDITADOS (5) ===")
    for k in EDITADOS:
        a, b = pn[k]["parameters"], qn[k]["parameters"]
        if "jsCode" in a:
            d = difflib.unified_diff(a["jsCode"].splitlines(), b["jsCode"].splitlines(), lineterm="", n=1)
        else:
            d = difflib.unified_diff(json.dumps(a, indent=1, ensure_ascii=False).splitlines(), json.dumps(b, indent=1, ensure_ascii=False).splitlines(), lineterm="", n=1)
        print(f"  ~ {k}")
        for l in list(d)[2:]:
            print("      " + l)
    a_pre, a_post = arcos(pre["connections"]), arcos(post["connections"])
    fmt = lambda a: f"{a[0]} [{a[1]}:{a[2]}] → {a[3]}" + (f" ({a[4]})" if a[4] else "")
    print("\n=== CONEXIONES QUITADAS ===")
    for a in sorted(a_pre - a_post):
        print("  - " + fmt(a))
    print("=== CONEXIONES AGREGADAS ===")
    for a in sorted(a_post - a_pre, key=lambda a: (NUEVOS.index(a[0]) if a[0] in NUEVOS else -1, a[2])):
        print("  + " + fmt(a))


def resumen(titulo, lista):
    malos = [t for ok, t in lista if not ok]
    print(f"\n=== {titulo}: {len(lista) - len(malos)}/{len(lista)} OK ===")
    for ok, t in lista:
        print(("  ✅ " if ok else "  ❌ ") + t)
    return not malos


# ================================================================================================================ flag (solo imprime)
def tel_ok(tel, permitir_otro):
    if not re.fullmatch(r"\d{10,15}", tel or ""):
        raise SystemExit(f"Teléfono inválido: {tel!r} (solo dígitos, con 549…).")
    if tel != TEL_LUCAS and not permitir_otro:
        raise SystemExit(f"En esta etapa el flag es SOLO para el celular de Lucas ({TEL_LUCAS}). Otro teléfono: agregar --permitir-otro (con OK de Lucas).")
    return tel


def flag_cmd(accion, tel, ttl):
    clave = f"v7:tel:{tel}"
    rc = f"docker exec {REDIS_CONTENEDOR} redis-cli"
    print(f"No hay endpoint en n8n para escribir esta clave y el Redis del bot no es accesible desde afuera: se hace en el VPS (SSH), a mano.\n")
    if accion == "on":
        print(f"  {rc} SET {clave} vivo" + (f" EX {ttl}" if ttl else "") + ("   # con TTL: se apaga sola" if ttl else "   # SIN TTL: queda hasta --flag-off"))
        print(f"  {rc} GET {clave}            # debe decir \"vivo\"")
        print("\nAntes: el apply ya tiene que estar aplicado (si no, la clave no hace nada). Rate limit: 10 mensajes / 15 min; esperar ~25 s entre mensajes (buffer).")
    elif accion == "off":
        print(f"  {rc} DEL {clave} triaje:{tel}")
        print(f"  {rc} EXISTS {clave}         # debe decir 0")
        print("\nCon la clave borrada ese teléfono vuelve al v6 en el MENSAJE SIGUIENTE (sin PUT). Limpieza (regla 9): "
              f"python scripts/limpiar_numero_demo.py --phone {tel} --apply --borrar-logs (ver estado del script en docs).")
    else:
        print(f"  {rc} GET {clave}\n  {rc} TTL {clave}")


def flag_status_observado(tel, n=15):
    """Solo GET: busca en las últimas ejecuciones del v6 qué leyó 'V7: Redis GET modo' para ese teléfono y si corrió el cerebro."""
    print(f"\nLo que vio el v6 en sus últimas {n} ejecuciones para {tel} (solo lectura):")
    vistos = 0
    for ex in api(f"/executions?workflowId={V6}&limit={n}").get("data", []):
        det = api(f"/executions/{ex['id']}?includeData=true")
        rd = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        try:
            ph = rd["Preparar Mensaje Final"][0]["data"]["main"][0][0]["json"].get("phone")
        except Exception:
            continue
        if ph != tel:
            continue
        vistos += 1
        try:
            modo = rd[N_GET][0]["data"]["main"][0][0]["json"].get("v7_modo")
        except Exception:
            modo = "(el nodo no corrió / no existe)"
        print(f"  ejecución {ex['id']} {str(ex.get('startedAt'))[:19]}  v7_modo={modo!r}  cerebro={'sí' if N_CER in rd else 'no'}  router={'sí' if ROUTER in rd else 'no'}"
              f"  triaje={'sí' if CARGAR in rd else 'no'}")
    if not vistos:
        print("  (ninguna ejecución de ese teléfono en el rango)")


# ================================================================================================================ main
def main():
    ap = argparse.ArgumentParser(description="Conexión del v7 (orquestador) al v6 solo para teléfonos con v7:tel:{tel} = 'vivo'.")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--offline", metavar="DIR", help="leer v6/cerebro/clinica/agente_urgencias desde JSON guardados (sin red)")
    ap.add_argument("--ver-codigo", action="store_true")
    ap.add_argument("--flag-on", nargs="?", const=TEL_LUCAS, metavar="TEL")
    ap.add_argument("--flag-off", nargs="?", const=TEL_LUCAS, metavar="TEL")
    ap.add_argument("--flag-status", nargs="?", const=TEL_LUCAS, metavar="TEL")
    ap.add_argument("--ttl", type=int, default=86400, help="segundos de vida de la clave al prenderla (0 = sin TTL). Default 86400 = se apaga sola en 24 h")
    ap.add_argument("--permitir-otro", action="store_true")
    a = ap.parse_args()

    if a.flag_on or a.flag_off or a.flag_status:
        tel = tel_ok(a.flag_on or a.flag_off or a.flag_status, a.permitir_otro or bool(a.flag_off or a.flag_status))
        flag_cmd("on" if a.flag_on else "off" if a.flag_off else "status", tel, a.ttl)
        if a.flag_status:
            flag_status_observado(tel)
        return

    viv, ids = leer_vivos(a.offline)
    v6 = viv["v6"]
    print(f"v6 {V6}: active={v6.get('active')} nodos={len(v6['nodes'])} versionId={str(v6.get('versionId'))[:8]} updatedAt={v6.get('updatedAt')}")
    print(f"cerebro {ids['cerebro']}: nodos={len(viv['cerebro']['nodes'])} versionId={str(viv['cerebro'].get('versionId'))[:8]} updatedAt={viv['cerebro'].get('updatedAt')}")
    if not a.offline:
        DRY.mkdir(parents=True, exist_ok=True)
        for k, w in viv.items():
            (DRY / f"{k}.json").write_text(json.dumps(w, indent=1, ensure_ascii=False), encoding="utf-8")
    if not resumen("PRERREQUISITOS (v6 vivo + cerebro orquestador vivo)", prerrequisitos(viv, ids)):
        sys.exit("ABORTO: falta un prerrequisito. No se construyó nada.")
    nuevo = construir(v6, ids)
    if not a.offline:
        (DRY / "v6_POST_propuesto.json").write_text(json.dumps(nuevo, indent=1, ensure_ascii=False), encoding="utf-8")
    imprimir_diff(v6, nuevo, a.ver_codigo)
    ok_inv = resumen("INVARIANTES (teléfonos sin flag = v6 de hoy)", invariantes(v6, nuevo, ids))
    ok_pru = resumen("PRUEBAS OFFLINE (JS real de los nodos en tests/harness_code_node.mjs)", pruebas_offline(v6, nuevo))
    if not (ok_inv and ok_pru):
        sys.exit("ABORTO: invariantes o pruebas en rojo. No se aplica.")
    if not a.apply:
        print(f"\n[SIMULACION] No se escribió nada en n8n. JSON vivo y propuesto en {DRY.relative_to(ROOT)}/ (ignorado por git).")
        print("Para aplicar (Lucas): python scripts/apply_v7_flag_lucas.py --apply")
        return
    if a.offline:
        sys.exit("--apply no se puede con --offline.")
    print("\n1) check_triaje (regla del proyecto: antes de cualquier PUT al v6)")
    if subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], cwd=ROOT).returncode != 0:
        sys.exit("ABORTO: check_triaje no dio sano. No se tocó nada.")
    print("2) re-GET: el v6 y el cerebro no cambiaron desde la simulación")
    viv2, _ = leer_vivos()
    if viv2["v6"].get("versionId") != v6.get("versionId"):
        sys.exit("ABORTO: el v6 cambió mientras preparaba el PUT (otra sesión). Volver a simular. No se tocó nada.")
    if not all(ok for ok, _ in prerrequisitos(viv2, ids)):
        sys.exit("ABORTO: los prerrequisitos del cerebro ya no se cumplen en el re-GET. No se tocó nada.")
    HIST.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    pre = HIST / f"{V6}_PRE_v7_flag_lucas_{ts}.json"
    pre.write_text(json.dumps(viv2["v6"], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"3) backup PRE: workflows/history/{pre.name}")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = {k: v for k, v in (nuevo.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{V6}", method="PUT", payload=body)
    print("4) PUT hecho")
    post = api(f"/workflows/{V6}")
    (HIST / f"{V6}_POST_v7_flag_lucas_{ts}.json").write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"5) backup POST: workflows/history/{V6}_POST_v7_flag_lucas_{ts}.json")
    norm = lambda w: {x["name"]: {k: x.get(k) for k in ("parameters", "type", "typeVersion", "credentials", "position", "disabled", "webhookId")} for x in w["nodes"]}
    lista = invariantes(viv2["v6"], post, ids)
    lista.append([norm(post) == norm(nuevo), "nodos del GET POST == nodos propuestos"])
    lista.append([arcos(post["connections"]) == arcos(nuevo["connections"]), "conexiones del GET POST == propuestas"])
    lista.append([post.get("active") is True, "v6 sigue activo"])
    rollback = f"python scripts/restaurar_workflow.py workflows/history/{pre.name} --apply"
    if not resumen("6) VERIFICACIÓN POST-PUT", lista):
        sys.exit(f"ATENCION: la verificación no dio lo esperado. Restaurar YA con:\n  {rollback}")
    print(f"\nAplicado. Ningún teléfono cambia hasta prender el flag:  python scripts/apply_v7_flag_lucas.py --flag-on")
    print(f"Volver atrás: sin PUT → --flag-off ; con PUT → {rollback}")
    print("Refrescar la foto local: python scripts/snapshot_v6_live.py")


if __name__ == "__main__":
    main()
