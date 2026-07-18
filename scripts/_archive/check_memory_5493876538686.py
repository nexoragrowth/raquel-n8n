"""Ad-hoc: revisar n8n_chat_histories del paciente 5493876538686 para el dia 2026-06-03.
Reusa pattern de test_subwf_writeback.py. Crea workflow ad-hoc con un SELECT y lo ejecuta.
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

WEBHOOK_PATH = "check-memory-5493876538686"
TARGET_SESSION = "5493876538686"

# Reusar credentials Postgres del v6 main
v6 = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
pg_node = next(n for n in v6["nodes"] if n["type"] == "n8n-nodes-base.postgres")
PG_CREDS = pg_node.get("credentials", {})

SELECT_Q = (
    f"SELECT id, message::text AS message_text, created_at "
    f"FROM n8n_chat_histories "
    f"WHERE session_id = '{TARGET_SESSION}' "
    f"AND created_at >= '2026-06-03T00:00:00Z' "
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
        "name": "Run SELECT",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [400, 300],
        "parameters": {
            "operation": "executeQuery",
            "query": SELECT_Q,
            "options": {},
        },
        "credentials": PG_CREDS,
    },
]
connections = {
    "Webhook Trigger": {"main": [[{"node": "Run SELECT", "type": "main", "index": 0}]]},
}

body = {"name": "TEST - Check Memory 5493876538686", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}

existing = requests.get(f"{BASE}/api/v1/workflows", headers=H, params={"name": body["name"]}, timeout=30).json()
test_wf = next((w for w in existing.get("data", []) if w.get("name") == body["name"]), None)

if test_wf:
    wid = test_wf["id"]
    print(f"[1] reuso workflow {wid}")
    requests.put(f"{BASE}/api/v1/workflows/{wid}", headers=H, json=body, timeout=40).raise_for_status()
else:
    r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=body, timeout=40)
    if not r.ok:
        print("FAIL crear", r.status_code, r.text[:500]); sys.exit(2)
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
if not ex.get("data"):
    print("!! no exec"); sys.exit(0)
exec_id = ex["data"][0]["id"]
print(f"[4] exec id: {exec_id} status: {ex['data'][0].get('status')}")
full = requests.get(f"{BASE}/api/v1/executions/{exec_id}?includeData=true", headers=H, timeout=30).json()
runs = full.get("data", {}).get("resultData", {}).get("runData", {})
print()
if "Run SELECT" in runs:
    node_run = runs["Run SELECT"][0]
    st = node_run.get("executionStatus", "?")
    err = node_run.get("error", {}).get("message", "")
    out = node_run.get("data", {}).get("main", [[]])[0]
    print(f"  [Run SELECT] status={st} items={len(out)}" + (f" ERR={err}" if err else ""))
    print(f"  ROWS:")
    for i, item in enumerate(out):
        j = item.get("json", {})
        print(f"   --- row {i} ---")
        print(f"   id={j.get('id')}  created_at={j.get('created_at')}")
        msg_text = j.get("message_text") or ""
        print(f"   message: {msg_text[:600]}")
else:
    print("[Run SELECT] NO EJECUTADO")
    print("runs keys:", list(runs.keys()))
