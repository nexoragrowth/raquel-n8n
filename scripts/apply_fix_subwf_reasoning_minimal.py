"""Fix gpt-5 reasoning: agregar reasoning_effort=minimal en Step 3.0 y Step 3.5a.
gpt-5 con default consume tokens en reasoning y deja output vacio para parsers."""
import os, sys, json, requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
WF_ID = "5cAWJxiWJ50hxEq3"

wf = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(ROOT / "workflows" / "history" / f"subwf_cancelar_PRE_reasoning_minimal_{ts}.json").write_text(
    json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")

# Step 3.0
n = next(x for x in wf["nodes"] if x["name"] == "Step 3.0: Prep LLM Body")
js = n["parameters"]["jsCode"]
new_js = js.replace(
    "  max_completion_tokens: 250,\n  response_format: { type: 'json_object' }",
    "  max_completion_tokens: 800,\n  reasoning_effort: 'minimal',\n  response_format: { type: 'json_object' }"
)
if new_js == js: print("!! 3.0 anchor"); sys.exit(2)
n["parameters"]["jsCode"] = new_js
print(f"  3.0: {len(js)} -> {len(new_js)}")

# Step 3.5a
n = next(x for x in wf["nodes"] if x["name"] == "Step 3.5a: Prep Acceptance LLM")
js = n["parameters"]["jsCode"]
new_js = js.replace(
    "  max_completion_tokens: 200,\n  response_format: { type: 'json_object' }",
    "  max_completion_tokens: 600,\n  reasoning_effort: 'minimal',\n  response_format: { type: 'json_object' }"
)
if new_js == js: print("!! 3.5a anchor"); sys.exit(2)
n["parameters"]["jsCode"] = new_js
print(f"  3.5a: {len(js)} -> {len(new_js)}")

allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution","executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": settings, "staticData": wf.get("staticData")}
r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
print(f"PUT {r.status_code}")
