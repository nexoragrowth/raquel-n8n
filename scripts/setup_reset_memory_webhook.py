"""Crea/actualiza un workflow n8n con un webhook que borra la memoria
(n8n_chat_histories) de un phone especifico. Whitelist: solo Lucas + Valentino
para que nadie pueda accidentalmente borrar memoria de pacientes reales.

URL: https://n8n.raquelrodriguez.com.ar/webhook/reset-memory
Body: {"phone": "5491161461034"} (Lucas) o {"phone": "5492216145776"} (Valentino)

Despues de correr este script, podes disparar el reset con:
  curl -X POST https://n8n.raquelrodriguez.com.ar/webhook/reset-memory \\
    -H "Content-Type: application/json" \\
    -d '{"phone":"5491161461034"}'

O con Python:
  requests.post("https://.../webhook/reset-memory", json={"phone":"5491161461034"})

Devuelve {deleted: N, phone: X} con N = cantidad de filas borradas.
"""
from __future__ import annotations
import os, sys, io, json
import requests
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

WEBHOOK_PATH = "reset-memory"
WORKFLOW_NAME = "[ADMIN] Reset Memory (Lucas + Valentino)"

# Reusar credentials Postgres del v6 main
v6 = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
pg_node = next(n for n in v6["nodes"] if n["type"] == "n8n-nodes-base.postgres")
PG_CREDS = pg_node.get("credentials", {})

VALIDATE_CODE = """// Whitelist: solo Lucas + Valentino
const ALLOWED = {
  '5491161461034': 'Lucas',
  '5492216145776': 'Valentino',
};
const body = $input.first().json.body || $input.first().json;
const phone = String(body.phone || '').trim();
if (!ALLOWED[phone]) {
  return [{ json: {
    error: 'phone not in whitelist',
    phone: phone,
    allowed: Object.keys(ALLOWED),
    status: 403
  }}];
}
return [{ json: { phone: phone, name: ALLOWED[phone], allowed: true } }];
"""

nodes = [
    {
        "id": "wh-trigger",
        "name": "Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [200, 300],
        "parameters": {
            "path": WEBHOOK_PATH,
            "httpMethod": "POST",
            "responseMode": "lastNode",
        },
        "webhookId": WEBHOOK_PATH,
    },
    {
        "id": "validate",
        "name": "Validate Whitelist",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [400, 300],
        "parameters": {"jsCode": VALIDATE_CODE},
    },
    {
        "id": "check-allowed",
        "name": "Allowed?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [600, 300],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [
                    {
                        "leftValue": "={{ $json.allowed }}",
                        "rightValue": True,
                        "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                    }
                ],
                "combinator": "and",
            },
        },
    },
    {
        "id": "delete-mem",
        "name": "DELETE chat_histories",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [800, 200],
        "parameters": {
            "operation": "executeQuery",
            "query": "DELETE FROM n8n_chat_histories WHERE session_id = '{{ $json.phone }}' RETURNING id",
            "options": {},
        },
        "credentials": PG_CREDS,
    },
    {
        "id": "respond-ok",
        "name": "Respond OK",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1000, 200],
        "parameters": {
            "jsCode": "const deleted = items.length; const phone = $('Validate Whitelist').first().json.phone; const name = $('Validate Whitelist').first().json.name; return [{ json: { status: 'ok', phone, name, deleted, message: `Memoria de ${name} (${phone}) borrada: ${deleted} filas` } }];"
        },
    },
    {
        "id": "respond-deny",
        "name": "Respond Denied",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [800, 400],
        "parameters": {
            "jsCode": "return [{ json: { status: 'denied', error: $json.error, allowed_phones: $json.allowed, hint: 'Solo Lucas (5491161461034) o Valentino (5492216145776)' } }];"
        },
    },
]

connections = {
    "Webhook": {"main": [[{"node": "Validate Whitelist", "type": "main", "index": 0}]]},
    "Validate Whitelist": {"main": [[{"node": "Allowed?", "type": "main", "index": 0}]]},
    "Allowed?": {"main": [
        [{"node": "DELETE chat_histories", "type": "main", "index": 0}],
        [{"node": "Respond Denied", "type": "main", "index": 0}],
    ]},
    "DELETE chat_histories": {"main": [[{"node": "Respond OK", "type": "main", "index": 0}]]},
}

body = {"name": WORKFLOW_NAME, "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}

existing = requests.get(f"{BASE}/api/v1/workflows", headers=H, params={"name": WORKFLOW_NAME}, timeout=30).json()
test_wf = next((w for w in existing.get("data", []) if w.get("name") == WORKFLOW_NAME), None)
if test_wf:
    wid = test_wf["id"]
    print(f"[1] reuso workflow {wid}")
    requests.put(f"{BASE}/api/v1/workflows/{wid}", headers=H, json=body, timeout=40).raise_for_status()
else:
    r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=body, timeout=40)
    if not r.ok: print("FAIL", r.text[:500]); sys.exit(2)
    wid = r.json()["id"]
    print(f"[1] creado workflow {wid}")

r = requests.post(f"{BASE}/api/v1/workflows/{wid}/activate", headers=H, timeout=30)
print(f"[2] activar: {r.status_code}")

webhook_url = f"{BASE.replace('/api/v1','')}/webhook/{WEBHOOK_PATH}"
print(f"\n=== BOTON LISTO ===")
print(f"URL: {webhook_url}")
print(f"\nPara borrar memoria Lucas:")
print(f'  curl -X POST {webhook_url} -H "Content-Type: application/json" -d \'{{"phone":"5491161461034"}}\'')
print(f"\nPara borrar memoria Valentino:")
print(f'  curl -X POST {webhook_url} -H "Content-Type: application/json" -d \'{{"phone":"5492216145776"}}\'')
print(f"\nResponse esperado: {{status:'ok',phone,name,deleted,message}}")
