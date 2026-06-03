"""Counts exactos por tipo de basura."""
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

COUNTS = [
    ("C1_agent_stopped",
     "SELECT count(*) AS cnt FROM n8n_chat_histories WHERE message->>'content' ILIKE '%Agent stopped%'"),
    ("C2_atencion_humana_prefix",
     "SELECT count(*) AS cnt FROM n8n_chat_histories WHERE message->>'content' LIKE '[ATENCION HUMANA%'"),
    ("C3_canned_escalar",
     "SELECT count(*) AS cnt FROM n8n_chat_histories WHERE message->>'content' = 'Le paso a la secretaria Irina para que le ayude lo antes posible.'"),
    ("C4_nota_interna_recordatorio",
     "SELECT count(*) AS cnt FROM n8n_chat_histories WHERE message->>'content' LIKE '[NOTA INTERNA%'"),
    ("C5_intent_tokens_total",
     "SELECT count(*) AS cnt FROM n8n_chat_histories WHERE message->>'type' = 'ai' AND message->>'content' IN ('agendar_nuevo','consulta_general','cancelar_o_reprogramar','confirmar_post_recordatorio','urgencia_dolor')"),
    ("C6_tipo_null",
     "SELECT id, session_id, message FROM n8n_chat_histories WHERE message->>'type' IS NULL LIMIT 3"),
    ("C7_human_with_atencion_prefix",
     "SELECT message->>'type' AS tipo, count(*) AS cnt FROM n8n_chat_histories WHERE message->>'content' LIKE '[ATENCION HUMANA%' GROUP BY 1"),
]

r = requests.get(f"{BASE}/api/v1/workflows/{WID}", headers=H, timeout=30).json()
PG_CREDS = None
for n in r["nodes"]:
    if n["type"] == "n8n-nodes-base.postgres":
        PG_CREDS = n.get("credentials")
        break

new_nodes = []
new_conns = {}
wh = next(n for n in r["nodes"] if n["type"] == "n8n-nodes-base.webhook")
wh["parameters"]["responseMode"] = "onReceived"
new_nodes.append(wh)
prev = "Webhook Trigger"
x = 400
for (name, q) in COUNTS:
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
requests.post(url, json={}, timeout=30)

# poll
for i in range(60):
    time.sleep(2)
    ex = requests.get(f"{BASE}/api/v1/executions?workflowId={WID}&status=success&limit=1", headers=H, timeout=15).json()
    if not ex.get("data"): continue
    eid = ex["data"][0]["id"]
    full = requests.get(f"{BASE}/api/v1/executions/{eid}?includeData=true", headers=H, timeout=60).json()
    runs = full.get("data", {}).get("resultData", {}).get("runData", {})
    if all(n in runs for n,_ in COUNTS):
        print(f"got exec {eid} after {i*2}s")
        break

print()
for (name, _) in COUNTS:
    if name not in runs:
        print(f"### {name}: NOT IN runs"); continue
    out = runs[name][0].get("data", {}).get("main", [[]])[0]
    items = [it.get("json", {}) for it in out]
    print(f"### {name}  ({len(items)} rows)")
    for it in items[:5]:
        print("  " + json.dumps(it, ensure_ascii=False)[:600])
    print()
