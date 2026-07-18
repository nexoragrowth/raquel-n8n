"""Corre 1 batch de queries (paso N) reusando el workflow audit."""
from __future__ import annotations
import os, sys, io, json, time, requests
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
WID = "vmku7s93ksPNcQ5g"

ALL_QUERIES = [
    ("Q3_no_reply_count",
     "SELECT count(*) AS total_no_reply "
     "FROM n8n_chat_histories WHERE message->>'content' = '[NO_REPLY]'"),
    ("Q4_filas_por_tipo",
     "SELECT message->>'type' AS tipo, count(*) AS cnt "
     "FROM n8n_chat_histories GROUP BY 1 ORDER BY cnt DESC"),
    ("Q1_tokens_intent_puros",
     "SELECT id, session_id, message->>'content' AS content "
     "FROM n8n_chat_histories "
     "WHERE message->>'type' = 'ai' "
     "AND message->>'content' IN ('agendar_nuevo','consulta_general','cancelar_o_reprogramar','confirmar_post_recordatorio','urgencia_dolor') "
     "LIMIT 20"),
    ("Q5_top_contents_repetidos",
     "SELECT message->>'content' AS c, count(*) AS cnt "
     "FROM n8n_chat_histories GROUP BY 1 ORDER BY cnt DESC LIMIT 10"),
    ("Q2_outputs_prohibidos",
     "SELECT id, session_id, message->>'content' AS content "
     "FROM n8n_chat_histories "
     "WHERE message->>'type' = 'ai' "
     "AND (message->>'content' ILIKE '%venite%' "
     "OR message->>'content' ILIKE '%los esperamos%' "
     "OR message->>'content' ILIKE '%agent stopped%' "
     "OR message->>'content' ILIKE '%max iterations%') "
     "LIMIT 20"),
    ("Q7_samples_no_reply",
     "SELECT id, session_id, message->>'type' AS tipo, message->>'content' AS content "
     "FROM n8n_chat_histories WHERE message->>'content' = '[NO_REPLY]' LIMIT 5"),
    ("Q8_errores_tecnicos_extra",
     "SELECT id, session_id, message->>'content' AS content "
     "FROM n8n_chat_histories WHERE message->>'type' = 'ai' "
     "AND (message->>'content' ILIKE '%error%' "
     "OR message->>'content' ILIKE '%undefined%' "
     "OR message->>'content' ILIKE '%econnrefused%' "
     "OR message->>'content' ILIKE '%timeout%' "
     "OR message->>'content' ILIKE '%agent stopped%') "
     "LIMIT 20"),
    ("Q9_tool_call_traces",
     "SELECT id, session_id, message->>'content' AS content "
     "FROM n8n_chat_histories WHERE message->>'type' = 'ai' "
     "AND (message->>'content' ILIKE '%tool_call%' "
     "OR message->>'content' ILIKE '%function_call%') "
     "LIMIT 10"),
    ("Q10_sample_top_content",
     "SELECT id, session_id, message->>'type' AS tipo, message->>'content' AS content "
     "FROM n8n_chat_histories WHERE message->>'type' = 'ai' "
     "AND length(message->>'content') < 50 "
     "ORDER BY id DESC LIMIT 30"),
]

START = int(sys.argv[1]) if len(sys.argv) > 1 else 0
SIZE = int(sys.argv[2]) if len(sys.argv) > 2 else 3
BATCH = ALL_QUERIES[START:START+SIZE]
print(f"running batch [{START}..{START+len(BATCH)}): {[n for n,_ in BATCH]}")

r = requests.get(f"{BASE}/api/v1/workflows/{WID}", headers=H, timeout=30).json()
PG_CREDS = None
for n in r["nodes"]:
    if n["type"] == "n8n-nodes-base.postgres":
        PG_CREDS = n.get("credentials")
        break

# Build new wf con webhook + batch en cadena
new_nodes = []
new_conns = {}
wh = next(n for n in r["nodes"] if n["type"] == "n8n-nodes-base.webhook")
wh["parameters"]["responseMode"] = "onReceived"
new_nodes.append(wh)
prev = "Webhook Trigger"
x = 400
for (name, q) in BATCH:
    new_nodes.append({
        "name": name,
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [x, 300],
        "parameters": {"operation": "executeQuery", "query": q, "options": {}},
        "credentials": PG_CREDS,
    })
    new_conns[prev] = {"main": [[{"node": name, "type": "main", "index": 0}]]}
    prev = name
    x += 200

body = {"name": r["name"], "nodes": new_nodes, "connections": new_conns, "settings": {"executionOrder": "v1"}}
requests.put(f"{BASE}/api/v1/workflows/{WID}", headers=H, json=body, timeout=60).raise_for_status()
requests.post(f"{BASE}/api/v1/workflows/{WID}/activate", headers=H, timeout=30)

url = f"{BASE.replace('/api/v1','')}/webhook/audit-basura-chat-hist"
t0 = time.time()
rr = requests.post(url, json={}, timeout=30)
print("triggered", rr.status_code, "in", round(time.time()-t0,2), "s")

# wait
for i in range(120):
    time.sleep(2)
    ex = requests.get(f"{BASE}/api/v1/executions?workflowId={WID}&status=success&limit=1", headers=H, timeout=15).json()
    if ex.get("data") and ex["data"][0]["startedAt"] > "2026-06-03T22:15":
        # newer than last
        eid = ex["data"][0]["id"]
        if int(eid) > 71161 - START * 0:  # we just want newest
            full = requests.get(f"{BASE}/api/v1/executions/{eid}?includeData=true", headers=H, timeout=60).json()
            runs = full.get("data", {}).get("resultData", {}).get("runData", {})
            if any(n in runs for n,_ in BATCH):
                print(f"got exec {eid} after {i*2}s")
                break

print()
results = {}
for (name, _) in BATCH:
    if name not in runs:
        print(f"### {name}: NOT IN runs")
        continue
    out = runs[name][0].get("data", {}).get("main", [[]])[0]
    items = [it.get("json", {}) for it in out]
    results[name] = items
    print(f"### {name}  ({len(items)} rows)")
    for it in items[:30]:
        print("  " + json.dumps(it, ensure_ascii=False)[:700])
    print()

dump_path = ROOT / f"audit_basura_batch_{START}.json"
with open(dump_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"dump -> {dump_path}")
