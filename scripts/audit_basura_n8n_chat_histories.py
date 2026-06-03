"""Audit ad-hoc: tipos de basura en n8n_chat_histories.

Crea/reusa workflow test con queries SELECT contra n8n_chat_histories y
captura el resultado de cada query via execution data.

Solo READ-ONLY.
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

WEBHOOK_PATH = "audit-basura-chat-hist"

# Reusar credentials Postgres del v6 main
v6 = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
pg_node = next(n for n in v6["nodes"] if n["type"] == "n8n-nodes-base.postgres")
PG_CREDS = pg_node.get("credentials", {})

QUERIES = [
    ("Q1_tokens_intent_puros",
     "SELECT id, session_id, message->>'content' AS content "
     "FROM n8n_chat_histories "
     "WHERE message->>'type' = 'ai' "
     "AND message->>'content' IN ('agendar_nuevo','consulta_general','cancelar_o_reprogramar','confirmar_post_recordatorio','urgencia_dolor') "
     "LIMIT 20"),
    ("Q2_outputs_prohibidos",
     "SELECT id, session_id, message->>'content' AS content "
     "FROM n8n_chat_histories "
     "WHERE message->>'type' = 'ai' "
     "AND (message->>'content' ILIKE '%venite%' "
     "OR message->>'content' ILIKE '%los esperamos%' "
     "OR message->>'content' ILIKE '%agent stopped%' "
     "OR message->>'content' ILIKE '%max iterations%') "
     "LIMIT 20"),
    ("Q3_no_reply_count",
     "SELECT count(*) AS total_no_reply "
     "FROM n8n_chat_histories WHERE message->>'content' = '[NO_REPLY]'"),
    ("Q4_filas_por_tipo",
     "SELECT message->>'type' AS tipo, count(*) AS cnt "
     "FROM n8n_chat_histories GROUP BY 1 ORDER BY cnt DESC"),
    ("Q5_top_contents_repetidos",
     "SELECT message->>'content' AS c, count(*) AS cnt "
     "FROM n8n_chat_histories GROUP BY 1 ORDER BY cnt DESC LIMIT 10"),
    ("Q6_total_filas",
     "SELECT count(*) AS total FROM n8n_chat_histories"),
    ("Q7_samples_no_reply",
     "SELECT id, session_id, message->>'type' AS tipo, message->>'content' AS content "
     "FROM n8n_chat_histories WHERE message->>'content' = '[NO_REPLY]' LIMIT 5"),
    ("Q8_errores_tecnicos_extra",
     "SELECT id, session_id, message->>'content' AS content "
     "FROM n8n_chat_histories WHERE message->>'type' = 'ai' "
     "AND (message->>'content' ILIKE '%error%' "
     "OR message->>'content' ILIKE '%undefined%' "
     "OR message->>'content' ILIKE '%null%' "
     "OR message->>'content' ILIKE '%500%' "
     "OR message->>'content' ILIKE '%econnrefused%' "
     "OR message->>'content' ILIKE '%timeout%' "
     "OR message->>'content' ILIKE '%fail%') "
     "LIMIT 20"),
    ("Q9_tool_call_traces",
     "SELECT id, session_id, message->>'content' AS content "
     "FROM n8n_chat_histories WHERE message->>'type' = 'ai' "
     "AND (message->>'content' ILIKE '%tool_call%' "
     "OR message->>'content' ILIKE '%tool_calls%' "
     "OR message->>'content' ILIKE '%function_call%') "
     "LIMIT 10"),
]

nodes = [
    {
        "name": "Webhook Trigger",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [200, 300],
        "parameters": {"path": WEBHOOK_PATH, "responseMode": "lastNode", "httpMethod": "POST"},
        "webhookId": WEBHOOK_PATH,
    },
]
connections = {"Webhook Trigger": {"main": [[]]}}

prev = "Webhook Trigger"
x = 400
for (name, q) in QUERIES:
    nodes.append({
        "name": name,
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [x, 300],
        "parameters": {
            "operation": "executeQuery",
            "query": q,
            "options": {},
        },
        "credentials": PG_CREDS,
    })
    connections[prev] = {"main": [[{"node": name, "type": "main", "index": 0}]]}
    prev = name
    x += 200

body = {
    "name": "AUDIT - basura n8n_chat_histories",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
}

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
r = requests.post(webhook_url, json={}, timeout=60)
print(f"   response: {r.status_code}")

time.sleep(4)
ex = requests.get(f"{BASE}/api/v1/executions?workflowId={wid}&limit=2", headers=H, timeout=30).json()
if not ex.get("data"):
    print("!! no exec"); sys.exit(0)
exec_id = ex["data"][0]["id"]
print(f"[4] exec id: {exec_id} status: {ex['data'][0].get('status')}\n")

full = requests.get(f"{BASE}/api/v1/executions/{exec_id}?includeData=true", headers=H, timeout=60).json()
runs = full.get("data", {}).get("resultData", {}).get("runData", {})

results = {}
for (name, q) in QUERIES:
    if name not in runs:
        print(f"### {name}: NO EJECUTADO\n")
        results[name] = None
        continue
    out = runs[name][0].get("data", {}).get("main", [[]])[0]
    items = [it.get("json", {}) for it in out]
    results[name] = items
    print(f"### {name}  ({len(items)} rows)")
    for it in items[:25]:
        print("  " + json.dumps(it, ensure_ascii=False)[:600])
    print()

# Save dump for grepping
dump_path = ROOT / "audit_basura_chat_histories.json"
with open(dump_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"\n[5] dump completo: {dump_path}")
