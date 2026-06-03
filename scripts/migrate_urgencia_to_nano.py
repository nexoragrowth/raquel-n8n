"""
Migrar LM Sub-Agent Urgencia: gpt-5-mini -> gpt-5-nano.
Cambio minimo: solo el campo model.value (+cachedResultName).
Mismo provider (OpenAI), misma credential, mismo tipo de nodo.

Backup pre + PUT + verify.
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

NEW_MODEL = "gpt-5-nano"
TARGET_NODE = "LM Sub-Agent Urgencia"

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_URGENCIA_NANO_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_URGENCIA_NANO_{ts}.json")

n = next(x for x in wf["nodes"] if x["name"] == TARGET_NODE)
current = n["parameters"]["model"]["value"]
print(f"  current model: {current}")
if current == NEW_MODEL:
    print("  [skip] ya esta en nano")
    sys.exit(0)
n["parameters"]["model"]["value"] = NEW_MODEL
n["parameters"]["model"]["cachedResultName"] = NEW_MODEL
print(f"  new model: {NEW_MODEL}")

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
print(f"PUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:500]); sys.exit(1)

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_URGENCIA_NANO_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_URGENCIA_NANO_{ts}.json")
n_post = next(x for x in wf_post["nodes"] if x["name"] == TARGET_NODE)
print(f"verify model: {n_post['parameters']['model']['value']}")
print(f"v6 active: {wf_post.get('active')}")
