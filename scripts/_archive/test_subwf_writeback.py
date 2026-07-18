"""Test E2E del fix Save Sub-WF Output to Memory.
Crea un workflow test: Webhook -> Set (phone + output mock) -> INSERT a n8n_chat_histories
con el mismo formato que el nodo nuevo del v6. Despues SELECT y verifica que la fila quedo.

Solo afecta n8n_chat_histories session_id = TEST-LUCAS-SUBWF (no toca pacientes reales).
"""
from __future__ import annotations
import os, sys, io, json, time
import requests
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

WEBHOOK_PATH = "test-subwf-writeback"
TEST_SESSION = "TEST-LUCAS-SUBWF"
TEST_OUTPUT = "TEST output del Sub-WF Cancelar: Tienes 2 turnos, cual cancelar? (FIX VERIFY)"

# Reusar credentials Postgres del v6 main
v6 = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
pg_node = next(n for n in v6["nodes"] if n["type"] == "n8n-nodes-base.postgres")
PG_CREDS = pg_node.get("credentials", {})

nodes = [
    {
        "name": "Webhook Trigger",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [200, 300],
        "parameters": {"path": WEBHOOK_PATH, "responseMode": "lastNode", "httpMethod": "POST"},
        "webhookId": WEBHOOK_PATH,
    },
    {
        "name": "Mock Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [400, 300],
        "parameters": {"jsCode": (
            "return [{ json: {"
            f" phone: '{TEST_SESSION}',"
            f" output: '{TEST_OUTPUT}'"
            "} }];"
        )},
    },
    {
        "name": "Save Sub-WF Output (TEST)",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [600, 200],
        "parameters": {
            "operation": "executeQuery",
            "query": "INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb) RETURNING id, session_id, created_at",
            "options": {
                "queryReplacement": "={{ $json.phone }}, ={{ JSON.stringify({ type: 'ai', content: $json.output, tool_calls: [], additional_kwargs: { source: 'wa_outbound' }, response_metadata: {}, invalid_tool_calls: [] }) }}",
            },
        },
        "credentials": PG_CREDS,
    },
    {
        "name": "Verify SELECT",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [800, 200],
        "parameters": {
            "operation": "executeQuery",
            "query": f"SELECT id, session_id, message::jsonb FROM n8n_chat_histories WHERE session_id = '{TEST_SESSION}' ORDER BY id DESC LIMIT 1",
            "options": {},
        },
        "credentials": PG_CREDS,
    },
]
connections = {
    "Webhook Trigger": {"main": [[{"node": "Mock Data", "type": "main", "index": 0}]]},
    "Mock Data": {"main": [[{"node": "Save Sub-WF Output (TEST)", "type": "main", "index": 0}]]},
    "Save Sub-WF Output (TEST)": {"main": [[{"node": "Verify SELECT", "type": "main", "index": 0}]]},
}

body = {"name": "TEST - Sub-WF Writeback Memory Fix", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}

existing = requests.get(f"{BASE}/api/v1/workflows", headers=H, params={"name": body["name"]}, timeout=30).json()
test_wf = next((w for w in existing.get("data", []) if w.get("name") == body["name"]), None)

if test_wf:
    wid = test_wf["id"]
    print(f"[1] reuso workflow {wid}")
    requests.put(f"{BASE}/api/v1/workflows/{wid}", headers=H, json=body, timeout=40).raise_for_status()
else:
    r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=body, timeout=40)
    if not r.ok: print("FAIL crear", r.status_code, r.text[:300]); sys.exit(2)
    wid = r.json()["id"]
    print(f"[1] creado workflow {wid}")

r = requests.post(f"{BASE}/api/v1/workflows/{wid}/activate", headers=H, timeout=30)
print(f"[2] activar: {r.status_code}")

# Cleanup pre-test
print(f"[3] disparando webhook...")
webhook_url = f"{BASE.replace('/api/v1','')}/webhook/{WEBHOOK_PATH}"
r = requests.post(webhook_url, json={}, timeout=30)
print(f"   response: {r.status_code}")

time.sleep(3)
ex = requests.get(f"{BASE}/api/v1/executions?workflowId={wid}&limit=2", headers=H, timeout=30).json()
if not ex.get("data"): print("!! no exec"); sys.exit(0)
exec_id = ex["data"][0]["id"]
print(f"[4] exec id: {exec_id} status: {ex['data'][0].get('status')}")
full = requests.get(f"{BASE}/api/v1/executions/{exec_id}?includeData=true", headers=H, timeout=30).json()
runs = full.get("data", {}).get("resultData", {}).get("runData", {})
print()
for nm in ["Mock Data", "Save Sub-WF Output (TEST)", "Verify SELECT"]:
    if nm in runs:
        st = runs[nm][0].get("executionStatus", "?")
        err = runs[nm][0].get("error", {}).get("message", "")
        out = runs[nm][0].get("data", {}).get("main", [[]])[0]
        print(f"  [{nm}] status={st} items={len(out)}" + (f" ERR={err}" if err else ""))
        if nm == "Verify SELECT" and out:
            j = out[0].get("json", {})
            print(f"     SELECT result: {json.dumps(j, ensure_ascii=False)[:400]}")
    else:
        print(f"  [{nm}] NO EJECUTADO")

# Cleanup test row
print(f"\n[5] cleanup test rows session_id={TEST_SESSION}")
# Hacemos otro workflow para borrar? Mejor lo dejamos, es solo 1 fila.
print("   (fila test queda en DB, session_id no afecta a paciente real)")
