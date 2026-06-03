"""Test E2E del Reconcile Memory Post-Banlist:
1. INSERT fila mock simulando LangChain saveContext con output 'PROHIBIDO original'.
2. Ejecutar el UPDATE del nodo Reconcile (con phone + texto canned).
3. SELECT y verificar que content cambio a canned + additional_kwargs tiene source=wa_outbound + reconciled=true.
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

WEBHOOK_PATH = "test-reconcile-memory"
TEST_SESSION = "TEST-LUCAS-RECONCILE"
PROHIBIDO = "Venite ahora a Balcarce 37, los esperamos para una consulta!"  # output bot prohibido
CANNED_FINAL = "Recibimos su mensaje. Le envio la informacion a la secretaria, ella le respondera en su horario de atencion. Gracias!"

v6 = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
pg_node = next(n for n in v6["nodes"] if n["type"] == "n8n-nodes-base.postgres")
PG_CREDS = pg_node.get("credentials", {})

# Build test workflow: insertar mock + ejecutar UPDATE + SELECT
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
        "name": "Cleanup pre-test",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [400, 300],
        "parameters": {
            "operation": "executeQuery",
            "query": f"DELETE FROM n8n_chat_histories WHERE session_id = '{TEST_SESSION}'",
            "options": {},
        },
        "credentials": PG_CREDS,
    },
    {
        "name": "Build Mock Data",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [500, 300],
        "parameters": {"jsCode": (
            "return [{ json: {"
            f" session_id: '{TEST_SESSION}',"
            f" canned_final: '{CANNED_FINAL}',"
            " message_jsonb: JSON.stringify({"
            "   type: 'ai',"
            f"  content: '{PROHIBIDO}',"
            "   tool_calls: [],"
            "   additional_kwargs: {},"
            "   response_metadata: {},"
            "   invalid_tool_calls: []"
            " })"
            "} }];"
        )},
    },
    {
        "name": "Insert Mock Prohibido",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [700, 300],
        "parameters": {
            "operation": "executeQuery",
            "query": "INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb) RETURNING id",
            "options": {
                "queryReplacement": "={{ $json.session_id }}, ={{ $json.message_jsonb }}",
            },
        },
        "credentials": PG_CREDS,
    },
    {
        "name": "Reconcile UPDATE (TEST)",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [900, 300],
        "parameters": {
            "operation": "executeQuery",
            "query": (
                "UPDATE n8n_chat_histories "
                "SET message = jsonb_set("
                "jsonb_set(message, '{content}', to_jsonb($1::text)), "
                "'{additional_kwargs}', '{\"source\":\"wa_outbound\",\"reconciled\":true}'::jsonb) "
                "WHERE id = ("
                "SELECT id FROM n8n_chat_histories "
                "WHERE session_id = $2 "
                "AND message->>'type' = 'ai' "
                "AND (message->'additional_kwargs'->>'source') IS NULL "
                "ORDER BY id DESC LIMIT 1) "
                "RETURNING id, message"
            ),
            "options": {
                "queryReplacement": "={{ $('Build Mock Data').first().json.canned_final }}, ={{ $('Build Mock Data').first().json.session_id }}",
            },
        },
        "credentials": PG_CREDS,
    },
    {
        "name": "Verify SELECT",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [1000, 300],
        "parameters": {
            "operation": "executeQuery",
            "query": f"SELECT id, session_id, message::jsonb FROM n8n_chat_histories WHERE session_id = '{TEST_SESSION}' ORDER BY id DESC LIMIT 1",
            "options": {},
        },
        "credentials": PG_CREDS,
    },
]
connections = {
    "Webhook Trigger": {"main": [[{"node": "Cleanup pre-test", "type": "main", "index": 0}]]},
    "Cleanup pre-test": {"main": [[{"node": "Build Mock Data", "type": "main", "index": 0}]]},
    "Build Mock Data": {"main": [[{"node": "Insert Mock Prohibido", "type": "main", "index": 0}]]},
    "Insert Mock Prohibido": {"main": [[{"node": "Reconcile UPDATE (TEST)", "type": "main", "index": 0}]]},
    "Reconcile UPDATE (TEST)": {"main": [[{"node": "Verify SELECT", "type": "main", "index": 0}]]},
}

body = {"name": "TEST - Reconcile Memory Post-Banlist", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}

existing = requests.get(f"{BASE}/api/v1/workflows", headers=H, params={"name": body["name"]}, timeout=30).json()
test_wf = next((w for w in existing.get("data", []) if w.get("name") == body["name"]), None)
if test_wf:
    wid = test_wf["id"]; print(f"[1] reuso {wid}")
    requests.put(f"{BASE}/api/v1/workflows/{wid}", headers=H, json=body, timeout=40).raise_for_status()
else:
    r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=body, timeout=40)
    if not r.ok: print("FAIL", r.text[:300]); sys.exit(2)
    wid = r.json()["id"]; print(f"[1] creado {wid}")

requests.post(f"{BASE}/api/v1/workflows/{wid}/activate", headers=H, timeout=30)
print(f"[2] activado")
webhook_url = f"{BASE.replace('/api/v1','')}/webhook/{WEBHOOK_PATH}"
r = requests.post(webhook_url, json={}, timeout=30)
print(f"[3] webhook: {r.status_code}")
time.sleep(3)

ex = requests.get(f"{BASE}/api/v1/executions?workflowId={wid}&limit=2", headers=H, timeout=30).json()
if not ex.get("data"): print("!! no exec"); sys.exit(0)
exec_id = ex["data"][0]["id"]
print(f"[4] exec id: {exec_id} status: {ex['data'][0].get('status')}")
full = requests.get(f"{BASE}/api/v1/executions/{exec_id}?includeData=true", headers=H, timeout=30).json()
runs = full.get("data", {}).get("resultData", {}).get("runData", {})
print()
for nm in ["Cleanup pre-test", "Build Mock Data", "Insert Mock Prohibido", "Reconcile UPDATE (TEST)", "Verify SELECT"]:
    if nm in runs:
        st = runs[nm][0].get("executionStatus", "?")
        err = runs[nm][0].get("error", {}).get("message", "")
        out = runs[nm][0].get("data", {}).get("main", [[]])[0]
        print(f"  [{nm}] status={st} items={len(out)}" + (f" ERR={err[:120]}" if err else ""))
        if nm == "Verify SELECT" and out:
            j = out[0].get("json", {})
            msg = j.get("message", {})
            content_ok = msg.get("content", "") == CANNED_FINAL
            source_ok = (msg.get("additional_kwargs", {}) or {}).get("source") == "wa_outbound"
            recon_ok = (msg.get("additional_kwargs", {}) or {}).get("reconciled") == True
            print(f"     content == CANNED_FINAL: {content_ok}")
            print(f"     additional_kwargs.source == 'wa_outbound': {source_ok}")
            print(f"     additional_kwargs.reconciled == true: {recon_ok}")
            print(f"     RESULT: {'PASS' if (content_ok and source_ok and recon_ok) else 'FAIL'}")
    else:
        print(f"  [{nm}] NO EJECUTADO")
