"""Test E2E del fix del cron de memoria EN N8N:
1. Crea un workflow test con: Webhook trigger -> Preparar mensaje (Set, datos mock) ->
   Guardar en Chat Memory (codigo NUEVO, mismo que el cron real) ->
   [Postgres - Insert Memory + Enviar WhatsApp a Lucas]
2. Activa el workflow.
3. Dispara con POST al webhook.
4. Lee la exec resultante y verifica que Guardar en Chat Memory + Postgres ejecutaron OK.

Solo manda WhatsApp a phone Lucas (5491161461034). Cero riesgo de tocar otros pacientes."""
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

# 1. Leer el codigo NUEVO del nodo 'Guardar en Chat Memory' del cron real
cron = requests.get(f"{BASE}/api/v1/workflows/7RqTApkvVavRmq3R", headers=H, timeout=60).json()
guardar_node = next(x for x in cron["nodes"] if x["name"] == "Guardar en Chat Memory")
JS_CODE_NEW = guardar_node["parameters"]["jsCode"]
print(f"[1] Codigo nuevo del nodo 'Guardar en Chat Memory': {len(JS_CODE_NEW)} chars")

# 2. Build workflow body
WEBHOOK_PATH = "test-memory-fix-lucas"
PHONE_LUCAS = "5491161461034"
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
        "name": "Preparar mensaje",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [400, 300],
        "parameters": {"jsCode": (
            "return [{ json: {"
            f" phone: '{PHONE_LUCAS}',"
            f" remoteJid: '{PHONE_LUCAS}@s.whatsapp.net',"
            " message: 'TEST cron memory fix - Lucas. Ignorar.',"
            " cita_id: 'TEST-CITA-123',"
            " fecha: '2026-06-04',"
            " hora: '10:00',"
            " tipo_recordatorio: 'TEST',"
            " nombre: 'Test Lucas Silva',"
            " dentista: 'Rodríguez Raquel',"
            " id_paciente: '608' "
            "} }];"
        )},
    },
    {
        "name": "Guardar en Chat Memory",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [600, 200],
        "parameters": {"jsCode": JS_CODE_NEW},
    },
    {
        "name": "Postgres - Insert Memory",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [800, 200],
        "parameters": {
            "operation": "executeQuery",
            "query": "INSERT INTO n8n_chat_histories (session_id, message) VALUES ('{{ $json.session_id }}', '{{ $json.message_json }}')",
            "options": {},
        },
        "credentials": {"postgres": {"id": "xwvjww5Odcxiy1K9", "name": "Postgres account"}},
    },
    {
        "name": "Enviar WhatsApp",
        "type": "n8n-nodes-evolution-api.evolutionApi",
        "typeVersion": 1,
        "position": [600, 400],
        "parameters": {
            "resource": "messages-api",
            "instanceName": "raquel",
            "remoteJid": "={{ $json.remoteJid }}",
            "messageText": "={{ $json.message }}",
            "options_message": {},
        },
        "credentials": {"evolutionApi": {"id": "4sAc6U57qV9jpeRy", "name": "Evolution account 2"}},
    },
]
connections = {
    "Webhook Trigger": {"main": [[{"node": "Preparar mensaje", "type": "main", "index": 0}]]},
    "Preparar mensaje": {"main": [[
        {"node": "Guardar en Chat Memory", "type": "main", "index": 0},
        {"node": "Enviar WhatsApp", "type": "main", "index": 0},
    ]]},
    "Guardar en Chat Memory": {"main": [[{"node": "Postgres - Insert Memory", "type": "main", "index": 0}]]},
}

body = {"name": "TEST - Cron Memory Save Fix (Lucas)", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}

# 3. Crear o reusar workflow
existing = requests.get(f"{BASE}/api/v1/workflows", headers=H, params={"name": body["name"]}, timeout=30).json()
test_wf = next((w for w in existing.get("data", []) if w.get("name") == body["name"]), None)

if test_wf:
    wid = test_wf["id"]
    print(f"[2] Workflow test ya existe: {wid}, lo actualizo")
    requests.put(f"{BASE}/api/v1/workflows/{wid}", headers=H, json=body, timeout=40).raise_for_status()
else:
    r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=body, timeout=40)
    if not r.ok:
        print("FAIL crear workflow:", r.status_code, r.text[:500]); sys.exit(2)
    wid = r.json()["id"]
    print(f"[2] Workflow test creado: {wid}")

# 4. Activar
r = requests.post(f"{BASE}/api/v1/workflows/{wid}/activate", headers=H, timeout=30)
print(f"[3] Activar workflow: {r.status_code}")

# 5. Disparar via webhook
webhook_url = f"{BASE.replace('/api/v1','')}/webhook/{WEBHOOK_PATH}"
print(f"[4] Disparando webhook: {webhook_url}")
r = requests.post(webhook_url, json={}, timeout=30)
print(f"   webhook response: {r.status_code}")

# 6. Esperar exec y verificar
print("[5] Esperando exec...")
time.sleep(4)
ex = requests.get(f"{BASE}/api/v1/executions?workflowId={wid}&limit=3", headers=H, timeout=30).json()
if not ex.get("data"):
    print("!! no encontre exec. revisar en UI."); sys.exit(0)

exec_id = ex["data"][0]["id"]
print(f"[6] Exec id: {exec_id}, status: {ex['data'][0].get('status')}")
full = requests.get(f"{BASE}/api/v1/executions/{exec_id}?includeData=true", headers=H, timeout=30).json()
runs = full.get("data", {}).get("resultData", {}).get("runData", {})
print("\\n=== Resultado por nodo ===")
for nm in ["Preparar mensaje", "Guardar en Chat Memory", "Postgres - Insert Memory", "Enviar WhatsApp"]:
    if nm in runs:
        r = runs[nm][0]
        status = r.get("executionStatus", "?")
        err = r.get("error", {}).get("message", "")
        # output
        try:
            out_count = len(r.get("data", {}).get("main", [[]])[0])
            print(f"  [{nm}] status={status} | items={out_count}" + (f" | ERROR: {err}" if err else ""))
            if nm in ("Guardar en Chat Memory", "Postgres - Insert Memory"):
                # mostrar output detalle
                outs = r.get("data", {}).get("main", [[]])[0]
                for i, item in enumerate(outs):
                    j = item.get("json", {})
                    print(f"     item{i}: {json.dumps(j, ensure_ascii=False)[:200]}")
        except Exception as e:
            print(f"  [{nm}] status={status} | parse error: {e}")
    else:
        print(f"  [{nm}] NO EJECUTADO")
