"""
Logging de escalaciones a Supabase (2026-07-14).

Contexto: reunion con la Dra (14/7) — el reportero v2 necesita una fuente de verdad
de escalaciones independiente de la retencion de ~72h de n8n. Se creo la tabla
`escalaciones_log` en Supabase Nexora v2.

Cambio: en 'Helper - Notify Grupo' (S5U6tSipzlgFHCkf), chokepoint de TODAS las
escalaciones (v6 escalar_a_secretaria + Sub-WF Step 6c), se inserta un nodo
Postgres 'Log Escalacion' entre el Webhook y el envio al grupo:

  Webhook -> Log Escalacion (onError: continue) -> Notify Grupo Send -> Chatwoot Apply

- responseMode=lastNode queda igual (ultimo nodo sigue siendo Chatwoot Apply).
- El insert usa la credencial 'Postgres Supabase Nexora v2' y mapea:
  telefono/motivo del payload del webhook (query o body), origen='bot',
  exec_id=$execution.id.
- onError=continueRegularOutput: si la DB falla, la escalacion se envia igual.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = "S5U6tSipzlgFHCkf"
HIST = Path(__file__).resolve().parents[1] / "workflows" / "history"
H = {"X-N8N-API-KEY": KEY, "accept": "application/json", "content-type": "application/json"}


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(N8N + path, method=method, headers=H, data=data)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def die(msg):
    print("ABORTADO: " + msg)
    sys.exit(1)


wf = api("GET", f"/api/v1/workflows/{WF}")
ts = time.strftime("%Y%m%d_%H%M%S")
(HIST / f"helper_notify_PRE_esclog_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

names = [n["name"] for n in wf["nodes"]]
if "Log Escalacion" in names:
    die("ya existe el nodo Log Escalacion (aplicado antes?)")
if not {"Webhook", "Notify Grupo Send", "Chatwoot Apply"} <= set(names):
    die(f"estructura inesperada: {names}")

TEL = ("={{ $('Webhook').first().json.query?.phone "
       "|| $('Webhook').first().json.body?.phone || '' }}")
MOT = ("={{ $('Webhook').first().json.query?.resumen "
       "|| $('Webhook').first().json.body?.text || 'sin resumen' }}")

log_node = {
    "parameters": {
        "schema": {"__rl": True, "value": "public", "mode": "list"},
        "table": {"__rl": True, "value": "escalaciones_log", "mode": "list"},
        "columns": {
            "mappingMode": "defineBelow",
            "value": {
                "telefono": TEL,
                "motivo": MOT,
                "origen": "bot",
                "exec_id": "={{ $execution.id }}",
            },
        },
        "options": {},
    },
    "id": "log-escalacion",
    "name": "Log Escalacion",
    "type": "n8n-nodes-base.postgres",
    "typeVersion": 2.5,
    "position": [400, 480],
    "onError": "continueRegularOutput",
    "credentials": {"postgres": {"id": "EWhpNhb6tkGg1OTp", "name": "Postgres Supabase Nexora v2"}},
}

wf["nodes"].append(log_node)
# Rewire: Webhook -> Log Escalacion -> Notify Grupo Send (resto igual)
conns = wf["connections"]
if conns.get("Webhook", {}).get("main", [[]])[0][0].get("node") != "Notify Grupo Send":
    die("conexion Webhook->Notify inesperada")
conns["Webhook"]["main"][0] = [{"node": "Log Escalacion", "type": "main", "index": 0}]
conns["Log Escalacion"] = {"main": [[{"node": "Notify Grupo Send", "type": "main", "index": 0}]]}

ALLOWED = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
res = api("PUT", f"/api/v1/workflows/{WF}",
          {"name": wf["name"], "nodes": wf["nodes"], "connections": conns,
           "settings": settings, "staticData": wf.get("staticData")})
(HIST / f"helper_notify_POST_esclog_{ts}.json").write_text(
    json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

v = api("GET", f"/api/v1/workflows/{WF}")
vn = [n["name"] for n in v["nodes"]]
chain_ok = (v["connections"]["Webhook"]["main"][0][0]["node"] == "Log Escalacion"
            and v["connections"]["Log Escalacion"]["main"][0][0]["node"] == "Notify Grupo Send")
print(f"nodos: {vn}")
print(f"cadena Webhook->Log->Send: {chain_ok}")
print(f"active: {v.get('active')}")
print("OK" if chain_ok and v.get("active") else "REVISAR")
