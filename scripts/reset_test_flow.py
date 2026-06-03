"""
Resetea el flow de test:
1. PUT cita 8095 y 8096 a Dentalink con id_estado=7 (No confirmado) — volver al estado pre-confirmacion
2. UPDATE recordatorios_enviados: confirmado_at=NULL, cancelado_at=NULL para 8095 y 8096
3. Listo, Lucas puede mandar 'Confirmados' otra vez y repetir flujo limpio

Tambien: verifica el estado en Dentalink antes y despues para entender por que 8095 dio 400.
"""
import json, sys, time, urllib.request
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N_BASE = require("N8N_BASE_URL").rstrip("/") + "/api/v1"
N8N_KEY = require("N8N_API_KEY")
SB = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
HEADERS = {"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"}
DT_CRED = "TwN6eBWsydjMdsCM"

def run_temp(name, nodes, conns, hit_path):
    wf = {"name": name, "nodes": nodes, "connections": conns,
          "settings": {"executionOrder": "v1"}}
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
            f"https://n8n.raquelrodriguez.com.ar/webhook/{hit_path}",
            method="POST", headers={"Content-Type": "application/json"}, data=b"{}")
        with urllib.request.urlopen(hit, timeout=30) as r:
            return r.read().decode()
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"{N8N_BASE}/workflows/{WID}/deactivate", method="POST", headers=HEADERS
            ), timeout=15)
        except: pass
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_BASE}/workflows/{WID}", method="DELETE", headers=HEADERS
        ), timeout=15)

# 1. GET estados actuales 8095 y 8096
print("=== Estados actuales en Dentalink ===")
for cid in [8095, 8096]:
    wh = f"check-{cid}-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters": {"httpMethod": "POST", "path": wh, "responseMode": "lastNode", "options": {}},
         "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook",
         "typeVersion": 2, "position": [240, 300], "webhookId": wh},
        {"parameters": {
            "url": f"https://api.dentalink.healthatom.com/api/v1/citas/{cid}",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "options": {}},
         "id": "h", "name": "Get", "type": "n8n-nodes-base.httpRequest",
         "typeVersion": 4.2, "position": [460, 300],
         "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
         "continueOnFail": True, "alwaysOutputData": True},
    ]
    conns = {"Webhook": {"main": [[{"node": "Get", "type": "main", "index": 0}]]}}
    body = run_temp(f"chk-{cid}", nodes, conns, wh)
    try:
        d = json.loads(body)["data"]
        print(f"  cita={d['id']} estado={d['id_estado']} ({d['estado_cita']}) anul={d['estado_anulacion']}")
    except Exception as e:
        print(f"  cita={cid}: parse err {e} body={body[:200]}")

# 2. PUT id_estado=7 (No confirmado) para ambas
print("\n=== Reset a id_estado=7 en Dentalink ===")
for cid in [8095, 8096]:
    wh = f"reset-{cid}-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters": {"httpMethod": "POST", "path": wh, "responseMode": "lastNode", "options": {}},
         "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook",
         "typeVersion": 2, "position": [240, 300], "webhookId": wh},
        {"parameters": {
            "method": "PUT",
            "url": f"https://api.dentalink.healthatom.com/api/v1/citas/{cid}",
            "authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth",
            "sendBody": True, "specifyBody": "json",
            "jsonBody": json.dumps({"id_estado": 7}),
            "options": {}},
         "id": "h", "name": "Put", "type": "n8n-nodes-base.httpRequest",
         "typeVersion": 4.2, "position": [460, 300],
         "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
         "continueOnFail": True, "alwaysOutputData": True},
    ]
    conns = {"Webhook": {"main": [[{"node": "Put", "type": "main", "index": 0}]]}}
    body = run_temp(f"reset-{cid}", nodes, conns, wh)
    try:
        d = json.loads(body)
        if "data" in d:
            print(f"  cita={d['data']['id']} -> id_estado={d['data']['id_estado']} ({d['data']['estado_cita']})")
        elif "error" in d:
            print(f"  cita={cid}: ERR {d['error'].get('message','')[:300]}")
    except: print(f"  cita={cid}: parse err body={body[:200]}")

# 3. UPDATE recordatorios_enviados confirmado_at=NULL, cancelado_at=NULL
print("\n=== Reset Supabase recordatorios_enviados ===")
SBH = {"apikey": SR, "Authorization": f"Bearer {SR}",
       "Content-Type": "application/json", "Prefer": "return=representation"}
for cid in [8095, 8096]:
    url = f"{SB}/rest/v1/recordatorios_enviados?id_cita_dentalink=eq.{cid}"
    data = json.dumps({"confirmado_at": None, "cancelado_at": None}).encode()
    req = urllib.request.Request(url, headers=SBH, method="PATCH", data=data)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            rows = json.loads(r.read().decode())
            for row in rows:
                print(f"  cita={row['id_cita_dentalink']} conf_at={row['confirmado_at']} canc_at={row['cancelado_at']}")
    except urllib.error.HTTPError as e:
        print(f"  cita={cid}: HTTP {e.code} {e.read().decode()[:200]}")

print("\nDone. Listo para que Lucas mande 'Confirmados' otra vez.")
