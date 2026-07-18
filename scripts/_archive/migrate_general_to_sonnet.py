"""
Migrar LM Sub-Agent General de lmChatOpenAi/gpt-5-mini a lmChatAnthropic/sonnet-4-5.

Cambios en el nodo:
- type: @n8n/n8n-nodes-langchain.lmChatOpenAi -> @n8n/n8n-nodes-langchain.lmChatAnthropic
- typeVersion: 1.2 -> 1.3
- parameters.model: {value: 'gpt-5-mini', ...} -> {value: 'claude-sonnet-4-5', ...}
- credentials: openAiApi -> anthropicApi (cred id hzTsaydprTYUdbHb)
- mantiene: name, id, position (para que wirings ai_languageModel sigan apuntando)

Backup pre + PUT + verify wirings intactos.
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

TARGET = "LM Sub-Agent General"
NEW_MODEL = "claude-sonnet-4-5"
ANTHROPIC_CRED_ID = "hzTsaydprTYUdbHb"
ANTHROPIC_CRED_NAME = "Anthropic account (Haiku 4.5)"

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_GENERAL_SONNET_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_GENERAL_SONNET_{ts}.json")

n = next(x for x in wf["nodes"] if x["name"] == TARGET)
print(f"\n  current: type={n['type']}, model={n['parameters']['model']['value']}")

# Preservar identidad del nodo (name, id, position) para que wirings ai_languageModel sigan
new_node = {
    "parameters": {
        "model": {
            "__rl": True,
            "value": NEW_MODEL,
            "mode": "list",
            "cachedResultName": NEW_MODEL,
        },
        "options": {},
    },
    "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic",
    "typeVersion": 1.3,
    "position": n["position"],
    "id": n["id"],
    "name": n["name"],
    "credentials": {
        "anthropicApi": {"id": ANTHROPIC_CRED_ID, "name": ANTHROPIC_CRED_NAME},
    },
}

# Reemplazar in-place
idx = wf["nodes"].index(n)
wf["nodes"][idx] = new_node
print(f"  new: type={new_node['type']}, model={new_node['parameters']['model']['value']}")

# Verify wirings ai_languageModel a Sub-Agent General se mantienen
ai_wirings = wf["connections"].get(TARGET, {}).get("ai_languageModel", [])
print(f"  ai_languageModel wirings desde {TARGET}: {ai_wirings}")
if not ai_wirings:
    print(f"  WARN: no se detectaron wirings desde {TARGET}, verificar a mano")

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
(hist / f"v6_POST_GENERAL_SONNET_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_GENERAL_SONNET_{ts}.json")

n_post = next(x for x in wf_post["nodes"] if x["name"] == TARGET)
print(f"\nverify: type={n_post['type']}")
print(f"        model={n_post['parameters']['model']['value']}")
print(f"        cred={n_post.get('credentials',{}).get('anthropicApi')}")
print(f"v6 active: {wf_post.get('active')}")

# Verify wirings post-PUT
ai_wirings_post = wf_post["connections"].get(TARGET, {}).get("ai_languageModel", [])
print(f"  ai_languageModel wirings post: {ai_wirings_post}")
