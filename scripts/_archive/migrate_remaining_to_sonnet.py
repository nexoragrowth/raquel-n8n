"""
Migra LM Sub-Agent Cancelar + Confirmar + Agendar a Anthropic Sonnet 4-5.
1 PUT con los 3 cambios. Mantiene id, name, position, wirings.
Backup pre + verify post.
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

TARGETS = ["LM Sub-Agent Cancelar", "LM Sub-Agent Confirmar", "LM Sub-Agent Agendar"]
NEW_MODEL = "claude-sonnet-4-5"
CRED = {"id": "hzTsaydprTYUdbHb", "name": "Anthropic account (Haiku 4.5)"}

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_3LMS_SONNET_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_3LMS_SONNET_{ts}.json")

for nm in TARGETS:
    n = next(x for x in wf["nodes"] if x["name"] == nm)
    print(f"\n[{nm}]")
    print(f"  before: type={n['type']}, model={n['parameters']['model']['value']}")
    if "Anthropic" in n["type"] and n["parameters"]["model"]["value"] == NEW_MODEL:
        print(f"  [skip] ya migrado")
        continue
    new_node = {
        "parameters": {
            "model": {"__rl": True, "value": NEW_MODEL, "mode": "list", "cachedResultName": NEW_MODEL},
            "options": {},
        },
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
        "typeVersion": 1.3,
        "position": n["position"],
        "id": n["id"],
        "name": n["name"],
        "credentials": {"anthropicApi": CRED},
    }
    idx = wf["nodes"].index(n)
    wf["nodes"][idx] = new_node
    print(f"  after:  type={new_node['type']}, model={new_node['parameters']['model']['value']}")
    # Verify wirings
    wires = wf["connections"].get(nm, {}).get("ai_languageModel", [])
    print(f"  ai_languageModel wirings: {wires}")

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

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_3LMS_SONNET_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nverify:")
for nm in TARGETS + ["LM Sub-Agent General"]:
    n_post = next(x for x in wf_post["nodes"] if x["name"] == nm)
    print(f"  {nm}: {n_post['type'].split('.')[-1]} / {n_post['parameters']['model']['value']}")
print(f"v6 active: {wf_post.get('active')}")
