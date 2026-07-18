"""Borra la key ratelimit:5491161461034 en Redis via temp workflow."""
import json, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N_BASE = require("N8N_BASE_URL").rstrip("/") + "/api/v1"
N8N_KEY = require("N8N_API_KEY")
HEADERS = {"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"}
REDIS_CRED = "kdtSKwGbN1xAZeUh"  # Redis account

wh = f"reset-rl-{int(time.time())}"
wf = {
    "name": f"TEMP-Reset-RL",
    "nodes": [
        {"parameters": {"httpMethod": "POST", "path": wh,
                        "responseMode": "lastNode", "options": {}},
         "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook",
         "typeVersion": 2, "position": [240, 300], "webhookId": wh},
        {"parameters": {
            "operation": "delete",
            "key": "ratelimit:5491161461034",
        },
         "id": "r", "name": "DelKey",
         "type": "n8n-nodes-base.redis",
         "typeVersion": 1,
         "position": [460, 300],
         "credentials": {"redis": {"id": REDIS_CRED, "name": "Redis account"}},
         "continueOnFail": True, "alwaysOutputData": True},
    ],
    "connections": {"Webhook": {"main": [[{"node": "DelKey", "type": "main", "index": 0}]]}},
    "settings": {"executionOrder": "v1"},
}
req = urllib.request.Request(f"{N8N_BASE}/workflows", method="POST", headers=HEADERS,
                              data=json.dumps(wf).encode())
twf = json.loads(urllib.request.urlopen(req, timeout=30).read())
WID = twf["id"]
try:
    urllib.request.urlopen(urllib.request.Request(
        f"{N8N_BASE}/workflows/{WID}/activate", method="POST", headers=HEADERS
    ), timeout=20)
    time.sleep(2)
    hit = urllib.request.Request(
        f"https://n8n.raquelrodriguez.com.ar/webhook/{wh}",
        method="POST", headers={"Content-Type": "application/json"}, data=b"{}")
    with urllib.request.urlopen(hit, timeout=30) as r:
        print(f"DEL response: {r.read().decode()[:200]}")
finally:
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_BASE}/workflows/{WID}/deactivate", method="POST", headers=HEADERS
        ), timeout=15)
    except: pass
    urllib.request.urlopen(urllib.request.Request(
        f"{N8N_BASE}/workflows/{WID}", method="DELETE", headers=HEADERS
    ), timeout=15)
print("Done — rate limit key borrada.")
