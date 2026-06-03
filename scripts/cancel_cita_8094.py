"""Anula la cita 8094 (Test - Lucas Silva jueves 28 11:30) en Dentalink — limpieza."""
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

CITA = 8094
wh_path = f"cancel-8094-{int(time.time())}"
wf = {
    "name": f"TEMP-Cancel-{CITA}",
    "nodes": [
        {"parameters": {"httpMethod": "POST", "path": wh_path,
                        "responseMode": "lastNode", "options": {}},
         "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook",
         "typeVersion": 2, "position": [240, 300], "webhookId": wh_path},
        {"parameters": {
            "method": "PUT",
            "url": f"https://api.dentalink.healthatom.com/api/v1/citas/{CITA}",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True, "specifyBody": "json",
            "jsonBody": json.dumps({"id_estado": 1}),
            "options": {},
         },
         "id": "h", "name": "Cancel", "type": "n8n-nodes-base.httpRequest",
         "typeVersion": 4.2, "position": [460, 300],
         "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
         "continueOnFail": True, "alwaysOutputData": True},
    ],
    "connections": {"Webhook": {"main": [[{"node": "Cancel", "type": "main", "index": 0}]]}},
    "settings": {"executionOrder": "v1"},
}
req = urllib.request.Request(f"{N8N_BASE}/workflows", method="POST",
                              headers=HEADERS, data=json.dumps(wf).encode())
twf = json.loads(urllib.request.urlopen(req, timeout=30).read())
WID = twf["id"]
try:
    urllib.request.urlopen(urllib.request.Request(
        f"{N8N_BASE}/workflows/{WID}/activate", method="POST", headers=HEADERS), timeout=20)
    time.sleep(2)
    hit = urllib.request.Request(
        f"https://n8n.raquelrodriguez.com.ar/webhook/{wh_path}",
        method="POST", headers={"Content-Type": "application/json"}, data=b"{}")
    with urllib.request.urlopen(hit, timeout=30) as r:
        body = r.read().decode()
    print(f"RESP cancel cita {CITA}: {body[:400]}")
finally:
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_BASE}/workflows/{WID}/deactivate", method="POST", headers=HEADERS), timeout=15)
    except Exception:
        pass
    urllib.request.urlopen(urllib.request.Request(
        f"{N8N_BASE}/workflows/{WID}", method="DELETE", headers=HEADERS), timeout=15)
