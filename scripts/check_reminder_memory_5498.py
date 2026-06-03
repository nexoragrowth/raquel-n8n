"""Ad hoc: SELECT n8n_chat_histories for phone 5493884175498 today (2026-06-03).
Verifica si llegaron el reminder_note (mensaje al paciente) y el [NOTA INTERNA] del cron.
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

WEBHOOK_PATH = "test-select-reminder-5498"
TARGET_SESSION = "5493884175498"

# Reusar credentials Postgres del v6 main
v6 = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
pg_node = next(n for n in v6["nodes"] if n["type"] == "n8n-nodes-base.postgres")
PG_CREDS = pg_node.get("credentials", {})

QUERY = (
    f"SELECT id, message::jsonb AS message FROM n8n_chat_histories "
    f"WHERE session_id = '{TARGET_SESSION}' "
    f"ORDER BY id DESC LIMIT 20"
)

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
        "name": "SELECT Memory",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [400, 300],
        "parameters": {
            "operation": "executeQuery",
            "query": QUERY,
            "options": {},
        },
        "credentials": PG_CREDS,
    },
]
connections = {
    "Webhook Trigger": {"main": [[{"node": "SELECT Memory", "type": "main", "index": 0}]]},
}

body = {"name": "TEST - SELECT Reminder 5498", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}

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

if "SELECT Memory" in runs:
    out = runs["SELECT Memory"][0].get("data", {}).get("main", [[]])[0]
    print(f"\n[5] FILAS DEVUELTAS: {len(out)}")
    print("="*80)
    for i, item in enumerate(out):
        j = item.get("json", {})
        msg = j.get("message", {})
        msg_type = msg.get("type", "?")
        content = msg.get("content", "")[:200] if isinstance(msg.get("content"), str) else str(msg.get("content"))[:200]
        ak = msg.get("additional_kwargs", {}) or {}
        source = ak.get("source", "")
        print(f"\n--- ROW {i} id={j.get('id')} type={msg_type} source={source}")
        print(f"    content[:200]: {content}")
else:
    print("!! SELECT Memory no ejecutado")
    print(json.dumps(runs, indent=2)[:1000])
