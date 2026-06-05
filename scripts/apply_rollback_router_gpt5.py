"""ROLLBACK URGENTE: Router LM gpt-5-mini -> gpt-5.
mini fallo clasificando 'Hola buenas sii' como cancelar/reprogramar en lugar
de confirmar_post_recordatorio. Vuelta a gpt-5 manteniendo reasoning_effort=minimal.
"""
import os, sys, json, requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
WF_ID = "O155MqHgOSaNZ9ye"

wf = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(ROOT / "workflows" / "history" / f"v6_PRE_ROLLBACK_ROUTER_GPT5_{ts}.json").write_text(
    json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")

n = next(x for x in wf["nodes"] if x["name"] == "Router LM")
m = n["parameters"].get("model", {})
old = m.get("value", "?") if isinstance(m, dict) else str(m)
n["parameters"]["model"] = {"__rl": True, "value": "gpt-5", "mode": "list", "cachedResultName": "gpt-5"}
# keep reasoning_effort=minimal
opts = n["parameters"].get("options", {}) or {}
opts["reasoningEffort"] = "minimal"
n["parameters"]["options"] = opts
print(f"Router LM model: {old} -> gpt-5  reasoning_effort=minimal")

allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution","executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": settings, "staticData": wf.get("staticData")}
r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
print(f"PUT {r.status_code}")
if r.ok:
    wf2 = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60).json()
    n2 = next(x for x in wf2["nodes"] if x["name"] == "Router LM")
    m2 = n2["parameters"]["model"]
    print(f"verify: model={m2.get('value')} reasoning_effort={n2['parameters'].get('options',{}).get('reasoningEffort')}")
