"""
Busca a Lucas en Dentalink:
- Por phone 5491161461034 (admin Lucas del CLAUDE.md)
- Por nombre/apellido "Lucas"
Muestra registros encontrados + sus turnos (si hay).
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

LUCAS_PHONE = "5491161461034"
LUCAS_PHONE_PLUS = "+5491161161034"  # variante con plus, por las dudas

def run_temp_get(name, url, query_params, hit_path):
    wf = {
        "name": name,
        "nodes": [
            {"parameters": {"httpMethod": "POST", "path": hit_path,
                            "responseMode": "lastNode", "options": {}},
             "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook",
             "typeVersion": 2, "position": [240, 300], "webhookId": hit_path},
            {"parameters": {
                "url": url,
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendQuery": True,
                "queryParameters": {"parameters": query_params},
                "options": {},
             },
             "id": "h", "name": "Get", "type": "n8n-nodes-base.httpRequest",
             "typeVersion": 4.2, "position": [460, 300],
             "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
             "continueOnFail": True, "alwaysOutputData": True},
        ],
        "connections": {"Webhook": {"main": [[{"node": "Get", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1"},
    }
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

def print_paciente(p):
    print(f"  id={p.get('id')}  {p.get('nombre')} {p.get('apellidos')}")
    print(f"    celular={p.get('celular')}  email={p.get('email')}")
    print(f"    rut={p.get('rut')}  fecha_nac={p.get('fecha_nacimiento')}")
    print(f"    fecha_alta={p.get('fecha_afiliacion')}")
    notas = p.get('observaciones') or p.get('notas') or ''
    if notas: print(f"    notas={str(notas)[:200]}")

# 1) Por celular (varias variantes — Dentalink suele guardar con +)
for phone_q in [LUCAS_PHONE, "+" + LUCAS_PHONE, "+5491161461034"]:
    print(f"\n=== Search pacientes por celular like '{phone_q}' ===")
    wh = f"lucas-phone-{int(time.time()*1000)%100000}"
    body = run_temp_get(
        f"TEMP-Lucas-{wh}",
        "https://api.dentalink.healthatom.com/api/v1/pacientes",
        [{"name": "q", "value": json.dumps({"celular": {"lk": phone_q}})}],
        wh,
    )
    try:
        parsed = json.loads(body)
        pacientes = parsed.get("data", [])
        print(f"  encontrados: {len(pacientes)}")
        for p in pacientes:
            print_paciente(p)
    except Exception as ex:
        print(f"  parse err: {ex} body={body[:300]}")

# 2) Por nombre Lucas
print(f"\n=== Search pacientes por nombre = 'Lucas' ===")
wh = f"lucas-name-{int(time.time()*1000)%100000}"
body = run_temp_get(
    f"TEMP-LucasName-{wh}",
    "https://api.dentalink.healthatom.com/api/v1/pacientes",
    [{"name": "q", "value": json.dumps({"nombre": {"lk": "Lucas"}})}],
    wh,
)
try:
    parsed = json.loads(body)
    pacientes = parsed.get("data", [])
    print(f"  encontrados: {len(pacientes)}")
    for p in pacientes[:20]:
        print_paciente(p)
except Exception as ex:
    print(f"  parse err: {ex} body={body[:300]}")
