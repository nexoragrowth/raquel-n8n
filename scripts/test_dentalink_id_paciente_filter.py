"""Probar varios formatos de filter id_paciente en query Dentalink."""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/") + "/api/v1"
KEY = require("N8N_API_KEY")
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
DT_CRED = "TwN6eBWsydjMdsCM"

FECHA = "2026-06-04"

QUERIES = [
    # 1. Solo fecha (control - debe devolver al menos los 2 test + otros)
    {"label": "fecha only",
     "q": {"fecha": {"eq": FECHA}}},
    # 2. fecha + id_paciente.in
    {"label": "fecha + id_paciente in",
     "q": {"fecha": {"eq": FECHA}, "id_paciente": {"in": [608, 621]}}},
    # 3. fecha + id_paciente.eq single
    {"label": "fecha + id_paciente eq 608",
     "q": {"fecha": {"eq": FECHA}, "id_paciente": {"eq": 608}}},
    # 4. id_paciente.in con strings
    {"label": "fecha + id_paciente in strings",
     "q": {"fecha": {"eq": FECHA}, "id_paciente": {"in": ["608", "621"]}}},
]

def run_get(q_obj):
    wh = f"chk-{int(time.time()*1000)%100000}"
    wf = {"name": f"TEMP-{wh}", "settings": {"executionOrder": "v1"},
          "nodes": [
              {"parameters": {"httpMethod": "POST", "path": wh,
                              "responseMode": "lastNode", "options": {}},
               "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook",
               "typeVersion": 2, "position": [240, 300], "webhookId": wh},
              {"parameters": {
                  "url": "https://api.dentalink.healthatom.com/api/v1/sucursales/1/citas",
                  "authentication": "genericCredentialType",
                  "genericAuthType": "httpHeaderAuth",
                  "sendQuery": True,
                  "queryParameters": {"parameters": [
                      {"name": "q", "value": json.dumps(q_obj)}
                  ]},
                  "options": {}},
               "id": "h", "name": "Get", "type": "n8n-nodes-base.httpRequest",
               "typeVersion": 4.2, "position": [460, 300],
               "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
               "continueOnFail": True, "alwaysOutputData": True}],
          "connections": {"Webhook": {"main": [[{"node": "Get", "type": "main", "index": 0}]]}}}
    req = urllib.request.Request(f"{N8N}/workflows", method="POST", headers=H,
                                  data=json.dumps(wf).encode())
    twf = json.loads(urllib.request.urlopen(req, timeout=30).read())
    WID = twf["id"]
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N}/workflows/{WID}/activate", method="POST", headers=H), timeout=20)
        time.sleep(2)
        hit = urllib.request.Request(
            f"https://n8n.raquelrodriguez.com.ar/webhook/{wh}",
            method="POST", headers={"Content-Type": "application/json"}, data=b"{}")
        with urllib.request.urlopen(hit, timeout=30) as r:
            return r.read().decode()
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"{N8N}/workflows/{WID}/deactivate", method="POST", headers=H), timeout=15)
        except Exception: pass
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N}/workflows/{WID}", method="DELETE", headers=H), timeout=15)

for tc in QUERIES:
    print(f"\n=== {tc['label']} ===")
    print(f"  q = {json.dumps(tc['q'])}")
    try:
        body = run_get(tc["q"])
        parsed = json.loads(body)
        if isinstance(parsed, dict) and "data" in parsed:
            citas = parsed["data"]
            print(f"  -> {len(citas)} citas")
            for c in citas[:5]:
                print(f"     cita={c.get('id')} pac={c.get('id_paciente')} {c.get('nombre_paciente'):30s} hora={c.get('hora_inicio')}")
        else:
            print(f"  -> raw: {body[:300]}")
    except Exception as ex:
        print(f"  -> err: {ex}")
