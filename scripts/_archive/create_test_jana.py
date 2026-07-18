"""
Crea paciente "Test - Jana" en Dentalink con el mismo celular que
"Test - Lucas Silva" (5491161461034) para reproducir el caso
multi-paciente / mismo phone en los tests con Lucas + Jana.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N_BASE = require("N8N_BASE_URL").rstrip("/") + "/api/v1"
N8N_KEY = require("N8N_API_KEY")
HEADERS = {"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"}
DT_CRED = "TwN6eBWsydjMdsCM"

PHONE_TEST = "5491161461034"

# Cuerpo minimo — replicando el shape del campo "nombre" de Test-Lucas-Silva
body_create = {
    "nombre": "Test - Jana",
    "apellidos": "Test",
    "celular": PHONE_TEST,
}

def run_temp(name, nodes, conns, hit_path):
    wf = {"name": name, "nodes": nodes, "connections": conns,
          "settings": {"executionOrder": "v1"}}
    req = urllib.request.Request(
        f"{N8N_BASE}/workflows", method="POST", headers=HEADERS,
        data=json.dumps(wf).encode())
    twf = json.loads(urllib.request.urlopen(req, timeout=30).read())
    WID = twf["id"]
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_BASE}/workflows/{WID}/activate", method="POST", headers=HEADERS
        ), timeout=20)
        time.sleep(2)
        hit = urllib.request.Request(
            f"https://n8n.raquelrodriguez.com.ar/webhook/{hit_path}",
            method="POST", headers={"Content-Type": "application/json"}, data=b"{}")
        with urllib.request.urlopen(hit, timeout=30) as r:
            return r.read().decode()
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"{N8N_BASE}/workflows/{WID}/deactivate", method="POST", headers=HEADERS
            ), timeout=15)
        except Exception:
            pass
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_BASE}/workflows/{WID}", method="DELETE", headers=HEADERS
        ), timeout=15)

# Step 1: POST /pacientes
wh = f"create-jana-{int(time.time())}"
nodes = [
    {"parameters": {"httpMethod": "POST", "path": wh,
                    "responseMode": "lastNode", "options": {}},
     "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook",
     "typeVersion": 2, "position": [240, 300], "webhookId": wh},
    {"parameters": {
        "method": "POST",
        "url": "https://api.dentalink.healthatom.com/api/v1/pacientes",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": True, "specifyBody": "json",
        "jsonBody": json.dumps(body_create),
        "options": {},
     },
     "id": "h", "name": "CreateJana", "type": "n8n-nodes-base.httpRequest",
     "typeVersion": 4.2, "position": [460, 300],
     "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
     "continueOnFail": True, "alwaysOutputData": True},
]
conns = {"Webhook": {"main": [[{"node": "CreateJana", "type": "main", "index": 0}]]}}

print(f"Body POST: {json.dumps(body_create, ensure_ascii=False)}")
body = run_temp("TEMP-Create-Jana", nodes, conns, wh)
print(f"\nRESP (first 1000):\n{body[:1000]}")

try:
    parsed = json.loads(body)
    if isinstance(parsed, dict) and parsed.get("data"):
        d = parsed["data"]
        print(f"\n=== CREADO ===")
        print(f"  id={d.get('id')}  nombre={d.get('nombre')} apellidos={d.get('apellidos')}")
        print(f"  celular={d.get('celular')}")
    else:
        print(f"\n(estructura inesperada): {parsed}")
except Exception as ex:
    print(f"\nparse err: {ex}")
