"""Verificar QUE LA MEMORIA DE IVAN tiene el recordatorio + nota interna,
post-fix del cron y post-repoblacion.

Approach: crear workflow temporal con Postgres SELECT a n8n_chat_histories
WHERE session_id = phone_ivan ORDER BY id DESC LIMIT 20.
Ejecutar, leer resultado, eliminar workflow temporal.
"""
import os, sys, json, requests, time
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

POSTGRES_CRED_ID = "xwvjww5Odcxiy1K9"
PHONE_IVAN = "5493885174354"
PHONE_MATIAS = "5493883446415"

# Workflow temporal: Manual Trigger -> Postgres SELECT
wf_def = {
    "name": f"_TEMP_verify_memory_{int(time.time())}",
    "nodes": [
        {
            "parameters": {},
            "id": "trigger",
            "name": "Manual Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [0, 0]
        },
        {
            "parameters": {
                "operation": "executeQuery",
                "query": f"SELECT id, session_id, message FROM n8n_chat_histories WHERE session_id IN ('{PHONE_IVAN}', '{PHONE_MATIAS}') ORDER BY id DESC LIMIT 30",
                "options": {}
            },
            "id": "query",
            "name": "Postgres Query",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [300, 0],
            "credentials": {"postgres": {"id": POSTGRES_CRED_ID, "name": "Postgres account"}}
        }
    ],
    "connections": {
        "Manual Trigger": {"main": [[{"node": "Postgres Query", "type": "main", "index": 0}]]}
    },
    "settings": {}
}

# 1) Crear workflow
r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=wf_def, timeout=30)
if not r.ok: print("FAIL create:", r.status_code, r.text[:500]); sys.exit(2)
new_wf = r.json()
wf_id = new_wf.get("id")
print(f"Created temp workflow: {wf_id}")

try:
    # 2) Ejecutar manualmente. n8n API: POST /workflows/{id}/run? No existe. Hay que usar el webhook o manualTrigger fire.
    # Alternativa: activar el workflow + esperar trigger.
    # Mejor: ejecutar via /executions POST? Tampoco. n8n no permite ejecutar workflow desde API sin webhook.
    # Solucion: cambiar trigger a webhook.
    print("Need to fire via webhook. Recreating with webhook trigger...")
    requests.delete(f"{BASE}/api/v1/workflows/{wf_id}", headers=H, timeout=30)

    wf_def["nodes"][0] = {
        "parameters": {"httpMethod": "POST", "path": "verify-mem-once", "responseMode": "lastNode", "options": {}},
        "id": "trigger",
        "name": "Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [0, 0],
        "webhookId": "verify-mem-once-12345"
    }
    wf_def["connections"] = {"Webhook": {"main": [[{"node": "Postgres Query", "type": "main", "index": 0}]]}}
    r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=wf_def, timeout=30)
    if not r.ok: print("FAIL create v2:", r.status_code, r.text[:500]); sys.exit(2)
    new_wf = r.json()
    wf_id = new_wf.get("id")
    print(f"Created webhook-trigger workflow: {wf_id}")

    # 3) Activar
    r = requests.post(f"{BASE}/api/v1/workflows/{wf_id}/activate", headers=H, timeout=30)
    print(f"activate: {r.status_code}")

    # 4) Fire webhook
    time.sleep(2)
    r = requests.post(f"{BASE}/webhook/verify-mem-once", json={}, timeout=30)
    print(f"webhook fire: {r.status_code}")
    if r.ok:
        try:
            data = r.json()
            # Result puede ser una lista de rows o {data: [...]}
            rows = data if isinstance(data, list) else data.get("data", [data])
            if not isinstance(rows, list): rows = [rows]
            print(f"\n=== {len(rows)} rows de n8n_chat_histories ===\n")
            for row in rows:
                sid = row.get("session_id", "?")
                rid = row.get("id", "?")
                m = row.get("message", {})
                if isinstance(m, str):
                    try: m = json.loads(m)
                    except: pass
                typ = m.get("type", "?") if isinstance(m, dict) else "?"
                content = m.get("content", "")[:200] if isinstance(m, dict) else str(m)[:200]
                ak = m.get("additional_kwargs", {}) if isinstance(m, dict) else {}
                src = ak.get("source", "") if isinstance(ak, dict) else ""
                print(f"  id={rid} sid={sid} type={typ} source={src!r}")
                print(f"    content: {content!r}")
                print()
        except Exception as e:
            print(f"parse err: {e}\nraw: {r.text[:1500]}")

finally:
    # 5) Cleanup
    try:
        requests.post(f"{BASE}/api/v1/workflows/{wf_id}/deactivate", headers=H, timeout=30)
        d = requests.delete(f"{BASE}/api/v1/workflows/{wf_id}", headers=H, timeout=30)
        print(f"\ncleanup delete: {d.status_code}")
    except Exception as e:
        print(f"cleanup err: {e}")
