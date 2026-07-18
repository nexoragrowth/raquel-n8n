"""Ad hoc: ejecutar SELECT a n8n_chat_histories para phone=5493878641044, hoy 03/06/2026."""
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

WEBHOOK_PATH = "test-check-memory-5493878641044"
TARGET_SESSION = "5493878641044"

# Reusar credentials Postgres del v6 main
v6 = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
pg_node = next(n for n in v6["nodes"] if n["type"] == "n8n-nodes-base.postgres")
PG_CREDS = pg_node.get("credentials", {})

SELECT_Q = (
    "SELECT id, message::jsonb AS message, created_at "
    "FROM n8n_chat_histories "
    f"WHERE session_id = '{TARGET_SESSION}' "
    "AND created_at >= '2026-06-03T00:00:00Z' "
    "ORDER BY id DESC LIMIT 20"
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

body = {"name": "TEST - Check Memory 5493878641044", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}

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
rows_payload = []
for nm in ["Run SELECT"]:
    if nm in runs:
        st = runs[nm][0].get("executionStatus", "?")
        err = runs[nm][0].get("error", {}).get("message", "")
        out = runs[nm][0].get("data", {}).get("main", [[]])[0]
        print(f"  [{nm}] status={st} items={len(out)}" + (f" ERR={err}" if err else ""))
        for it in out:
            j = it.get("json", {})
            rows_payload.append(j)
    else:
        print(f"  [{nm}] NO EJECUTADO")

print("\n=== FILAS ENCONTRADAS ===")
print(f"Total filas: {len(rows_payload)}")
for i, row in enumerate(rows_payload):
    print(f"\n--- fila {i+1} (id={row.get('id')}, created_at={row.get('created_at')}) ---")
    msg = row.get("message", {})
    if isinstance(msg, str):
        try:
            msg = json.loads(msg)
        except Exception:
            pass
    if isinstance(msg, dict):
        t = msg.get("type", "?")
        content = msg.get("content", "")
        ak = msg.get("additional_kwargs", {})
        src = ak.get("source", "?") if isinstance(ak, dict) else "?"
        print(f"  type={t}  source={src}")
        print(f"  content[:200]: {content[:200]!r}")
    else:
        print(f"  raw: {json.dumps(msg, ensure_ascii=False)[:300]}")

# Output JSON for parsing
print("\n=== JSON_PAYLOAD_START ===")
print(json.dumps(rows_payload, ensure_ascii=False, default=str))
print("=== JSON_PAYLOAD_END ===")
