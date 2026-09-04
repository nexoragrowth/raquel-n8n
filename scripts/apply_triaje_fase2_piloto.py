# -*- coding: utf-8 -*-
"""
apply_triaje_fase2_piloto.py — inserta el TRIAJE DE URGENCIAS CON VIDEO (Fase 2, piloto) en el v6.

Diseño: docs/triaje-fase2-diseno-2026-09-04.md · decisiones: memory/decisions.md 2026-09-02/04.

QUÉ CAMBIA EN EL v6 (2 conexiones existentes + 21 nodos nuevos con prefijo "Triaje: " + 1 párrafo en el Router):
  - `Es cierre?`[1]        → `Triaje: Redis GET estado` → `Triaje: ¿Seguimiento?` → [sí] columna triaje / [no] Router (idéntico a hoy)
  - `Switch sobre Intent`[2] (urgencia_dolor) → `Triaje: Cargar Config` (en vez de `Sub-Agent Urgencia`, que queda huérfano)
  Columna: Cargar Config → Evaluar (gate red flags + estado + regexes) → Ruta Pre → [Clasificar gpt-5-mini → Merge] → Decidir
           (re-check humano, payloads canned) → Ruta → video (/send/media) / pregunta / cierre (/send/text) → Persistir (memoria+log)
           → Redis SET estado; silencio → log; escalar → texto canned al paciente → notify-grupo → log → Redis SET.
  Todo texto al paciente sale de triaje_videos / triaje_config. El LLM solo clasifica (JSON). Cualquier error → escalar.

REGLAS DURAS que cumple: GET fresco, asserts de las 2 conexiones esperadas, backup PRE/POST con timestamp,
PUT solo con name/nodes/connections/settings/staticData y settings filtradas, assert webhookId 'evo-webhook-v2',
apikey de Evolution y token de Chatwoot copiados EN CALIENTE de nodos vivos (nunca en este archivo), idempotente.

USO:
  python scripts/apply_triaje_fase2_piloto.py                 # dry-run: cambios + diff de conexiones/prompt
  python scripts/apply_triaje_fase2_piloto.py --apply         # PUT (requiere tablas creadas: create_triaje_config_tables.py --apply)
  python scripts/apply_triaje_fase2_piloto.py --rollback-wiring   # restaura las 2 conexiones (nodos Triaje quedan huérfanos)
  python scripts/apply_triaje_fase2_piloto.py --rollback <backup_PRE.json>   # PUT del backup completo
"""
import argparse, copy, difflib, json, os, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
WF_ID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
PG_CRED = {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}
OPENAI_CRED = {"id": "nYujqfon7GGDnJUO", "name": "OpenAi account"}
REDIS_CRED = {"id": "kdtSKwGbN1xAZeUh", "name": "Redis account"}

# ---------------- fuentes únicas ----------------
GATE_JS = (ROOT / "triaje" / "gate_red_flags.js").read_text(encoding="utf-8")
PROMPT = (ROOT / "triaje" / "prompt_clasificador.md").read_text(encoding="utf-8")
EVALUAR_JS = GATE_JS + "\n\n" + (ROOT / "triaje" / "evaluar.js").read_text(encoding="utf-8").replace("__SYSTEM_PROMPT_JSON__", json.dumps(PROMPT, ensure_ascii=False))
DECIDIR_JS_TPL = (ROOT / "triaje" / "decidir.js").read_text(encoding="utf-8")
PREPARAR_JS = (ROOT / "triaje" / "preparar_escalada.js").read_text(encoding="utf-8")
ESCALAR_JS = (ROOT / "triaje" / "escalar_notify.js").read_text(encoding="utf-8")

QUERY_CONFIG = """SELECT c.activo AS triaje_activo, c.modo, c.telefonos_piloto, c.red_flags_extra,
       c.regex_no_sirvio, c.regex_cierre, c.regex_nuevo_problema, c.regex_aparato,
       jsonb_build_object('texto_escalada', c.texto_escalada, 'texto_cierre', c.texto_cierre) AS textos,
       c.aviso_pasivo, c.ttl_video_seg, c.ttl_pregunta_seg, c.modelo,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('id', v.id, 'tipo', v.tipo, 'opcion', v.opcion, 'url', v.url,
                  'filename', v.filename, 'caption', v.caption, 'pregunta_guiada', v.pregunta_guiada,
                  'texto_salida_emergencia', v.texto_salida_emergencia) ORDER BY v.tipo, v.opcion)
                 FROM triaje_videos v WHERE v.activo AND v.url IS NOT NULL), '[]'::jsonb) AS videos
FROM triaje_config c WHERE c.id = 1"""

ROUTER_ANCLA = ('- AI previo: "lo paso a la secretaria Irina" -> respuesta corta del paciente ("ok", "gracias", "te veo el jueves") -> '
                "intent = `consulta_general` (donde el sub-agent decide NO_REPLY).")
ROUTER_MARCADOR = "CONTINUACION DE URGENCIA CON VIDEO"
ROUTER_BLOQUE = ROUTER_ANCLA + "\n\n" + (
    "- **CONTINUACION DE URGENCIA CON VIDEO (NUEVO 2026-09-04)**: si en el contexto el ultimo BOT empieza con "
    "\"[VIDEO ENVIADO —\" o \"[TRIAJE — PREGUNTA GUIADA\" (el sistema de triaje le mando un video o una pregunta canned por una "
    "urgencia de aparato), entonces: (a) si el paciente responde la pregunta, dice que sigue igual / no le sirvio / sigue pinchando / "
    "se sale / no tiene cera o pinza, o menciona cualquier molestia o duda sobre el aparato -> intent = `urgencia_dolor` "
    "(continuacion del flujo urgencia; NUNCA `consulta_general` aunque no diga la palabra \"dolor\" y aunque sea una pregunta). "
    "(b) Si SOLO agradece o cierra (\"listo\", \"gracias\", \"ya me la puse\", \"ya esta\") -> `consulta_general`."
)

# ---------------- helpers API ----------------
def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    key = require("N8N_API_KEY")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": key, "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

def clean_settings(wf):
    return {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}

def get_sm(node):
    opts = node["parameters"].get("options", {})
    return opts.get("systemMessage", node["parameters"].get("systemMessage", ""))

def set_sm(node, value):
    if "options" in node["parameters"]:
        node["parameters"]["options"]["systemMessage"] = value
    else:
        node["parameters"]["systemMessage"] = value

def conn_list(conns, name, idx):
    try:
        return [{"node": c["node"], "type": c["type"], "index": c["index"]} for c in conns[name]["main"][idx]]
    except (KeyError, IndexError):
        return None

# ---------------- constructores de nodos ----------------
def if_bool(nid, name, pos, expr, loose=False):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": pos,
            "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose" if loose else "strict", "version": 2},
                                          "conditions": [{"id": nid + "-c", "leftValue": expr, "rightValue": True,
                                                          "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                          "combinator": "and"}, "options": {}}}

def switch_eq(nid, name, pos, field_expr, keys):
    rules = []
    for i, k in enumerate(keys):
        rules.append({"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                     "conditions": [{"id": f"{nid}-r{i}", "leftValue": field_expr, "rightValue": k,
                                                     "operator": {"type": "string", "operation": "equals"}}],
                                     "combinator": "and"}, "renameOutput": True, "outputKey": k})
    return {"id": nid, "name": name, "type": "n8n-nodes-base.switch", "typeVersion": 3.2, "position": pos,
            "parameters": {"rules": {"values": rules}, "options": {"fallbackOutput": "extra", "renameFallbackOutput": "fallback"}}}

def code(nid, name, pos, js):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": pos,
            "parameters": {"jsCode": js}}

def pg(nid, name, pos, query, always=True):
    n = {"id": nid, "name": name, "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": pos,
         "parameters": {"operation": "executeQuery", "query": query, "options": {}}, "credentials": {"postgres": PG_CRED},
         "onError": "continueRegularOutput"}
    if always: n["alwaysOutputData"] = True
    return n

def redis_get(nid, name, pos, key_expr, prop):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.redis", "typeVersion": 1, "position": pos,
            "parameters": {"operation": "get", "propertyName": prop, "key": key_expr, "keyType": "string", "options": {}},
            "credentials": {"redis": REDIS_CRED}, "onError": "continueRegularOutput", "alwaysOutputData": True}

def redis_set(nid, name, pos, key_expr, value_expr, ttl_expr):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.redis", "typeVersion": 1, "position": pos,
            "parameters": {"operation": "set", "key": key_expr, "value": value_expr, "keyType": "string", "expire": True, "ttl": ttl_expr},
            "credentials": {"redis": REDIS_CRED}, "onError": "continueRegularOutput"}

def http_evo(nid, name, pos, headers, url, json_body, timeout):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
            "parameters": {"method": "POST", "url": url, "sendHeaders": True, "headerParameters": copy.deepcopy(headers),
                           "sendBody": True, "specifyBody": "json", "jsonBody": json_body,
                           "options": {"response": {"response": {"neverError": True}}, "timeout": timeout}},
            "credentials": {}, "onError": "continueRegularOutput"}

EVO_OK = "={{ !!($json.data && $json.data.Info && $json.data.Info.ID) }}"
EVO_OK_TOLERANTE = "={{ !!($json.data && $json.data.Info && $json.data.Info.ID) || ['video','cerrar'].includes($('Triaje: Decidir').first().json.ruta) }}"

def build(wf):
    new = copy.deepcopy(wf)
    nodes = new["nodes"]; conns = new["connections"]
    names = {n["name"]: n for n in nodes}
    cambios = []

    for req in ("Es cierre?", "Router - Clasificar Intent", "Switch sobre Intent", "Sub-Agent Urgencia", "Evolution API - Enviar Mensaje",
                "Re-check Humano", "Preparar Mensaje Final", "Existe paciente?", "Webhook - Evolution API"):
        if req not in names:
            sys.exit(f"ERROR: falta el nodo {req!r} en el v6")

    # secretos en caliente (nunca en el repo)
    enviar = names["Evolution API - Enviar Mensaje"]
    evo_headers = copy.deepcopy(enviar["parameters"]["headerParameters"])
    evo_base = enviar["parameters"]["url"].split("/send/")[0]
    cw_token = next(h["value"] for h in names["Re-check Humano"]["parameters"]["headerParameters"]["parameters"] if h["name"] == "api_access_token")
    decidir_js = DECIDIR_JS_TPL.replace("__CW_TOKEN__", cw_token)

    # posiciones: banda propia debajo del Router/Switch
    sx, sy = names["Switch sobre Intent"]["position"]
    X0, Y0 = sx - 1000, sy + 1100
    P = lambda col, fila: [X0 + col * 300, Y0 + fila * 220]

    D = "$('Triaje: Decidir').first().json"
    E = "$('Triaje: Preparar Escalada').first().json"
    PM = "$('Preparar Mensaje Final').first().json"
    def body(fields):
        return "={\n" + ",\n".join(f'  "{k}": {v}' for k, v in fields) + "\n}"

    nuevos = [
        redis_get("triaje-redis-get", "Triaje: Redis GET estado", P(0, 0), "={{ 'triaje:' + " + PM + ".phone }}", "triaje_estado"),
        {**if_bool("triaje-seguimiento", "Triaje: ¿Seguimiento?", P(1, 0), "={{ !!($json.triaje_estado) }}", loose=True)},
        pg("triaje-cargar-config", "Triaje: Cargar Config", P(2, 0), QUERY_CONFIG),
        code("triaje-evaluar", "Triaje: Evaluar", P(3, 0), EVALUAR_JS),
        switch_eq("triaje-ruta-pre", "Triaje: Ruta Pre", P(4, 0), "={{ $json.ruta_pre }}", ["clasificar", "decidido", "normal"]),
        {"id": "triaje-clasificar", "name": "Triaje: Clasificar (gpt-5-mini)", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": P(5, 0),
         "parameters": {"method": "POST", "url": "https://api.openai.com/v1/chat/completions", "authentication": "predefinedCredentialType",
                        "nodeCredentialType": "openAiApi", "sendBody": True, "specifyBody": "json", "jsonBody": "={{ $json.llm_body }}",
                        "options": {"response": {"response": {"neverError": True}}, "timeout": 30000}},
         "credentials": {"openAiApi": OPENAI_CRED}, "onError": "continueRegularOutput"},
        {"id": "triaje-merge", "name": "Triaje: Merge Clasificación", "type": "n8n-nodes-base.merge", "typeVersion": 3, "position": P(6, 0),
         "parameters": {"mode": "combine", "combineBy": "combineByPosition", "options": {}}},
        code("triaje-decidir", "Triaje: Decidir", P(7, 0), decidir_js),
        switch_eq("triaje-ruta", "Triaje: Ruta", P(8, 0), "={{ $json.ruta }}", ["video", "pregunta", "cerrar", "silencio", "escalar"]),
        http_evo("triaje-enviar-video", "Triaje: Enviar Video", P(9, -1), evo_headers, evo_base + "/send/media",
                 body([("number", "{{ JSON.stringify(" + D + ".send.number) }}"), ("type", '"video"'),
                       ("url", "{{ JSON.stringify(" + D + ".send.url) }}"), ("caption", "{{ JSON.stringify(" + D + ".send.caption) }}"),
                       ("filename", "{{ JSON.stringify(" + D + ".send.filename) }}")]), 45000),
        if_bool("triaje-video-ok", "Triaje: ¿Video OK?", P(10, -1), EVO_OK),
        http_evo("triaje-enviar-texto", "Triaje: Enviar Texto Canned", P(11, 0), evo_headers, evo_base + "/send/text",
                 body([("number", "{{ JSON.stringify(" + D + ".send.number) }}"), ("text", "{{ JSON.stringify(" + D + ".send.text) }}")]), 30000),
        if_bool("triaje-texto-ok", "Triaje: ¿Texto OK?", P(12, 0), EVO_OK_TOLERANTE),
        pg("triaje-persistir", "Triaje: Persistir", P(13, 0), "={{ " + D + ".sql_persistir }}"),
        redis_set("triaje-redis-set", "Triaje: Redis SET estado", P(14, 0), "={{ 'triaje:' + " + PM + ".phone }}",
                  "={{ " + D + ".estado_json }}", "={{ " + D + ".estado_ttl }}"),
        pg("triaje-log-silencio", "Triaje: Log Silencio", P(9, 1), "={{ $json.sql_silencio }}"),
        code("triaje-preparar-escalada", "Triaje: Preparar Escalada", P(9, 2), PREPARAR_JS),
        http_evo("triaje-enviar-texto-escalada", "Triaje: Enviar Texto Escalada", P(10, 2), evo_headers, evo_base + "/send/text",
                 body([("number", "{{ JSON.stringify(" + E + ".send.number) }}"), ("text", "{{ JSON.stringify(" + E + ".send.text) }}")]), 30000),
        code("triaje-escalar", "Triaje: Escalar (notify-grupo)", P(11, 2), ESCALAR_JS),
        pg("triaje-log-escalado", "Triaje: Log Escalado", P(12, 2), "={{ $json.sql }}"),
        redis_set("triaje-redis-set-escalado", "Triaje: Redis SET escalado", P(13, 2), "={{ 'triaje:' + " + PM + ".phone }}",
                  "={{ " + E + ".estado_json }}", "={{ " + E + ".estado_ttl }}"),
    ]
    # ¿Seguimiento? (IF v2 loose, notEmpty string) — construido aparte para usar operador string
    nuevos[1] = {"id": "triaje-seguimiento", "name": "Triaje: ¿Seguimiento?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": P(1, 0),
                 "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                                               "conditions": [{"id": "triaje-seg-c", "leftValue": "={{ $json.triaje_estado || '' }}", "rightValue": "",
                                                               "operator": {"type": "string", "operation": "notEmpty", "singleValue": True}}],
                                               "combinator": "and"}, "options": {}}}

    # idempotencia: si existen, se actualizan parámetros conservando id/position
    for n in nuevos:
        if n["name"] in names:
            prev = names[n["name"]]
            n["position"] = prev.get("position", n["position"]); n["id"] = prev.get("id", n["id"])
            nodes[nodes.index(prev)] = n
            cambios.append(f"ACTUALIZA {n['name']!r}")
        else:
            nodes.append(n)
            cambios.append(f"AGREGA {n['name']!r} ({n['type'].split('.')[-1]})")
        names[n["name"]] = n

    # ---- conexiones ----
    def C(name, idx=0): return {"node": name, "type": "main", "index": idx}
    esperado_switch = [C("Sub-Agent Urgencia")]
    esperado_cierre = [C("Router - Clasificar Intent")]
    act_switch = conn_list(conns, "Switch sobre Intent", 2)
    act_cierre = conn_list(conns, "Es cierre?", 1)
    if act_switch == esperado_switch:
        conns["Switch sobre Intent"]["main"][2] = [C("Triaje: Cargar Config")]
        cambios.append("REWIRE Switch sobre Intent[2]: Sub-Agent Urgencia -> Triaje: Cargar Config")
    elif act_switch == [C("Triaje: Cargar Config")]:
        cambios.append("Switch sobre Intent[2] ya apunta al triaje (idempotente)")
    else:
        sys.exit(f"ERROR: Switch sobre Intent[2] inesperado: {act_switch!r}")
    if act_cierre == esperado_cierre:
        conns["Es cierre?"]["main"][1] = [C("Triaje: Redis GET estado")]
        cambios.append("REWIRE Es cierre?[1]: Router -> Triaje: Redis GET estado")
    elif act_cierre == [C("Triaje: Redis GET estado")]:
        cambios.append("Es cierre?[1] ya apunta al triaje (idempotente)")
    else:
        sys.exit(f"ERROR: Es cierre?[1] inesperado: {act_cierre!r}")

    conns["Triaje: Redis GET estado"] = {"main": [[C("Triaje: ¿Seguimiento?")]]}
    conns["Triaje: ¿Seguimiento?"] = {"main": [[C("Triaje: Cargar Config")], [C("Router - Clasificar Intent")]]}
    conns["Triaje: Cargar Config"] = {"main": [[C("Triaje: Evaluar")]]}
    conns["Triaje: Evaluar"] = {"main": [[C("Triaje: Ruta Pre")]]}
    conns["Triaje: Ruta Pre"] = {"main": [
        [C("Triaje: Clasificar (gpt-5-mini)"), C("Triaje: Merge Clasificación", 0)],   # clasificar: al LLM y al Merge (in 0)
        [C("Triaje: Decidir")],                                                            # decidido
        [C("Router - Clasificar Intent")],                                                 # normal
        [C("Triaje: Preparar Escalada")],                                                  # fallback
    ]}
    conns["Triaje: Clasificar (gpt-5-mini)"] = {"main": [[C("Triaje: Merge Clasificación", 1)]]}
    conns["Triaje: Merge Clasificación"] = {"main": [[C("Triaje: Decidir")]]}
    conns["Triaje: Decidir"] = {"main": [[C("Triaje: Ruta")]]}
    conns["Triaje: Ruta"] = {"main": [
        [C("Triaje: Enviar Video")],            # video
        [C("Triaje: Enviar Texto Canned")],     # pregunta
        [C("Triaje: Enviar Texto Canned")],     # cerrar
        [C("Triaje: Log Silencio")],            # silencio
        [C("Triaje: Preparar Escalada")],       # escalar
        [C("Triaje: Preparar Escalada")],       # fallback
    ]}
    conns["Triaje: Enviar Video"] = {"main": [[C("Triaje: ¿Video OK?")]]}
    conns["Triaje: ¿Video OK?"] = {"main": [[C("Triaje: Enviar Texto Canned")], [C("Triaje: Preparar Escalada")]]}
    conns["Triaje: Enviar Texto Canned"] = {"main": [[C("Triaje: ¿Texto OK?")]]}
    conns["Triaje: ¿Texto OK?"] = {"main": [[C("Triaje: Persistir")], [C("Triaje: Preparar Escalada")]]}
    conns["Triaje: Persistir"] = {"main": [[C("Triaje: Redis SET estado")]]}
    conns["Triaje: Preparar Escalada"] = {"main": [[C("Triaje: Enviar Texto Escalada")]]}
    conns["Triaje: Enviar Texto Escalada"] = {"main": [[C("Triaje: Escalar (notify-grupo)")]]}
    conns["Triaje: Escalar (notify-grupo)"] = {"main": [[C("Triaje: Log Escalado")]]}
    conns["Triaje: Log Escalado"] = {"main": [[C("Triaje: Redis SET escalado")]]}
    cambios.append("CONEXIONES del bloque Triaje escritas (21 nodos)")

    # ---- prompt del Router (2ª capa para cuando el estado Redis venció) ----
    router = names["Router - Clasificar Intent"]
    sm = get_sm(router)
    if ROUTER_MARCADOR in sm:
        cambios.append("Router: bloque de continuación ya presente (idempotente)")
    else:
        cnt = sm.count(ROUTER_ANCLA)
        if cnt != 1:
            sys.exit(f"ERROR: el ancla del Router aparece {cnt} veces (esperaba 1)")
        set_sm(router, sm.replace(ROUTER_ANCLA, ROUTER_BLOQUE, 1))
        cambios.append("Router - Clasificar Intent: +bloque CONTINUACION DE URGENCIA CON VIDEO")
    return new, cambios

def diff_conns(a, b, keys):
    def f(c): return json.dumps({k: c.get(k) for k in keys if k in c}, ensure_ascii=False, indent=1, sort_keys=True).splitlines()
    return list(difflib.unified_diff(f(a), f(b), fromfile="ANTES", tofile="DESPUES", lineterm=""))

def verify(after):
    conns = after["connections"]; names = {n["name"] for n in after["nodes"]}
    faltan = [n for n in ("Triaje: Redis GET estado", "Triaje: Evaluar", "Triaje: Decidir", "Triaje: Enviar Video", "Triaje: Persistir",
                          "Triaje: Preparar Escalada", "Triaje: Escalar (notify-grupo)", "Triaje: Redis SET escalado") if n not in names]
    ok1 = conn_list(conns, "Switch sobre Intent", 2) == [{"node": "Triaje: Cargar Config", "type": "main", "index": 0}]
    ok2 = conn_list(conns, "Es cierre?", 1) == [{"node": "Triaje: Redis GET estado", "type": "main", "index": 0}]
    wh = next(n for n in after["nodes"] if n["name"] == "Webhook - Evolution API")
    ok3 = wh.get("webhookId") == "evo-webhook-v2"
    router = next(n for n in after["nodes"] if n["name"] == "Router - Clasificar Intent")
    ok4 = ROUTER_MARCADOR in get_sm(router)
    return (not faltan) and ok1 and ok2 and ok3 and ok4, {"faltan": faltan, "switch": ok1, "cierre": ok2, "webhookId": ok3, "router": ok4}

def put(wf_body, label):
    body = {k: wf_body[k] for k in PUT_KEYS if k in wf_body}
    body["settings"] = clean_settings(wf_body)
    wh = next(n for n in body["nodes"] if n["name"] == "Webhook - Evolution API")
    assert wh.get("webhookId") == "evo-webhook-v2", "webhookId perdido — abortado"
    api(f"/workflows/{WF_ID}", method="PUT", payload=body)
    after = api(f"/workflows/{WF_ID}")
    ts = time.strftime("%Y%m%d_%H%M%S")
    post = ROOT / "workflows" / "history" / f"v6_POST_{label}_{ts}.json"
    post.write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"POST backup -> {post}")
    return after

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback-wiring", action="store_true")
    ap.add_argument("--rollback", metavar="BACKUP_JSON")
    args = ap.parse_args()

    wf = api(f"/workflows/{WF_ID}")
    print(f"v6 vivo: {wf['name']} — {len(wf['nodes'])} nodos, activo={wf['active']}, updatedAt={wf.get('updatedAt')}")
    (ROOT / "workflows" / "history").mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    if args.rollback:
        bk = json.loads(Path(args.rollback).read_text(encoding="utf-8"))
        pre = ROOT / "workflows" / "history" / f"v6_PRE_rollback_total_{ts}.json"
        pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        after = put(bk, "rollback_total")
        print(f"rollback total OK: {len(after['nodes'])} nodos")
        return

    if args.rollback_wiring:
        new = copy.deepcopy(wf); conns = new["connections"]
        conns["Switch sobre Intent"]["main"][2] = [{"node": "Sub-Agent Urgencia", "type": "main", "index": 0}]
        conns["Es cierre?"]["main"][1] = [{"node": "Router - Clasificar Intent", "type": "main", "index": 0}]
        pre = ROOT / "workflows" / "history" / f"v6_PRE_rollback_wiring_{ts}.json"
        pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        after = put(new, "rollback_wiring")
        print("rollback de cableado OK: Switch[2] -> Sub-Agent Urgencia, Es cierre?[1] -> Router (nodos Triaje huérfanos)")
        return

    new, cambios = build(wf)
    print("\nCAMBIOS:"); [print("  -", c) for c in cambios]
    print("\nDIFF conexiones (Es cierre?, Switch sobre Intent):")
    for line in diff_conns(wf["connections"], new["connections"], ["Es cierre?", "Switch sobre Intent"]):
        print("  " + line)
    print("\nDIFF prompt Router (solo líneas +/-):")
    r0 = get_sm(next(n for n in wf["nodes"] if n["name"] == "Router - Clasificar Intent"))
    r1 = get_sm(next(n for n in new["nodes"] if n["name"] == "Router - Clasificar Intent"))
    for line in difflib.unified_diff(r0.splitlines(), r1.splitlines(), fromfile="ANTES", tofile="DESPUES", lineterm=""):
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")): print("  " + line[:300])
    print(f"\nNodos: {len(wf['nodes'])} -> {len(new['nodes'])}")

    if not args.apply:
        print("\n[DRY-RUN] no se tocó n8n. Para aplicar: --apply")
        return

    pre = ROOT / "workflows" / "history" / f"v6_PRE_triaje_fase2_{ts}.json"
    pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PRE backup -> {pre}")
    after = put(new, "triaje_fase2")
    ok, det = verify(after)
    print("verificación post-PUT:", det)
    if not ok:
        sys.exit("ERROR: la verificación post-PUT falló — revisar en la UI (rollback: --rollback " + str(pre) + ")")
    print(f"✅ Fase 2 aplicada: {len(after['nodes'])} nodos, activo={after['active']}. El triaje queda INACTIVO por dato hasta "
          f"`create_triaje_config_tables.py --activar --piloto <tel>`.")

if __name__ == "__main__":
    main()
