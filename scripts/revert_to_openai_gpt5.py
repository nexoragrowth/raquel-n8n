"""
Revierte los 4 Sub-Agent LMs de Anthropic a OpenAI:
- Confirmar/Cancelar/Agendar -> gpt-5 (main) [UPGRADE desde mini]
- General -> gpt-5-mini

Cred OpenAi account: nYujqfon7GGDnJUO
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

OPENAI_CRED = {"id": "nYujqfon7GGDnJUO", "name": "OpenAi account"}

# Mapping nodo -> nuevo modelo
MAPPING = {
    "LM Sub-Agent Confirmar": "gpt-5",
    "LM Sub-Agent Cancelar":  "gpt-5",
    "LM Sub-Agent Agendar":   "gpt-5",
    "LM Sub-Agent General":   "gpt-5-mini",
}

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_REVERT_OPENAI_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_REVERT_OPENAI_{ts}.json")

for nm, new_model in MAPPING.items():
    n = next(x for x in wf["nodes"] if x["name"] == nm)
    print(f"\n[{nm}]")
    print(f"  before: type={n['type'].split('.')[-1]}, model={n['parameters']['model']['value']}")
    new_node = {
        "parameters": {
            "model": {
                "__rl": True,
                "value": new_model,
                "mode": "list",
                "cachedResultName": new_model,
            },
            "options": {},
        },
        "type": "@n8n/n8n-nodes-langchain.lmChatOpenAi",
        "typeVersion": 1.2,
        "position": n["position"],
        "id": n["id"],
        "name": n["name"],
        "credentials": {"openAiApi": OPENAI_CRED},
    }
    idx = wf["nodes"].index(n)
    wf["nodes"][idx] = new_node
    print(f"  after:  type={new_node['type'].split('.')[-1]}, model={new_node['parameters']['model']['value']}")

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
(hist / f"v6_POST_REVERT_OPENAI_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"\nverify (todos los LM nodes):")
for n in wf_post["nodes"]:
    if "lmChat" in n["type"]:
        prov = "Anthropic" if "Anthropic" in n["type"] else "OpenAI"
        model = n["parameters"]["model"]["value"]
        print(f"  [{prov}] {n['name']:30s} model={model}")
print(f"\nv6 active: {wf_post.get('active')}")
