"""
Asigna la credencial Supabase httpHeaderAuth (id JT0D38dLlhoCEJGn) a las 3 tools
nuevas y quita los parametersHeaders/headerParameters inline (la cred los maneja).

Tambien borra la cred duplicada I20hLfTxMcj4xMmX.
"""
import json, sys
from datetime import datetime
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

SB_CRED = {"id": "JT0D38dLlhoCEJGn", "name": "Supabase API Key (apikey header)"}

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_CRED_{ts}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_CRED_{ts}.json")

TARGETS = ["consultar_recordatorios_abiertos",
           "marcar_recordatorio_confirmado",
           "marcar_recordatorio_cancelado"]

for nm in TARGETS:
    n = next(x for x in wf["nodes"] if x["name"] == nm)
    p = n["parameters"]
    # Quitar headers inline
    p.pop("parametersHeaders", None)
    p.pop("headerParameters", None)
    p.pop("specifyHeaders", None)
    # Setear auth via cred
    p["authentication"] = "genericCredentialType"
    p["genericAuthType"] = "httpHeaderAuth"
    p["sendHeaders"] = False  # no headers extras desde el nodo
    # Asignar cred al nodo
    n["credentials"] = {"httpHeaderAuth": SB_CRED}
    print(f"  [{nm}] credentials set, headers inline removed")

# PUT
allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
payload = {"name": wf["name"], "nodes": wf["nodes"],
           "connections": wf["connections"], "settings": settings}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]

r = requests.put(f"{N8N}/api/v1/workflows/{WF}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
print(f"\nPUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:500]); sys.exit(1)

# Borrar cred duplicada
print(f"\nBorrando cred duplicada I20hLfTxMcj4xMmX ...")
r = requests.delete(f"{N8N}/api/v1/credentials/I20hLfTxMcj4xMmX", headers=H, timeout=30)
print(f"  status: {r.status_code}")

# Verify
wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_CRED_{ts}.json").write_text(json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_CRED_{ts}.json")
for nm in TARGETS:
    n = next(x for x in wf_post["nodes"] if x["name"] == nm)
    print(f"  {nm}: credentials={n.get('credentials',{})}")
