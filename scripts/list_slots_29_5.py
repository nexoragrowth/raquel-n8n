"""
Lista los slots ocupados del 29/5/2026 para identificar 2 horarios libres
contiguos donde la Dra atiende.
"""
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

FECHA = "2026-05-29"

wh = f"slots-{int(time.time())}"
wf = {
    "name": f"TEMP-Slots-{wh}",
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
                {"name": "q", "value": json.dumps({"fecha": {"eq": FECHA}})}
            ]},
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
        body = json.loads(r.read().decode())
finally:
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N}/workflows/{WID}/deactivate", method="POST", headers=H), timeout=15)
    except Exception:
        pass
    urllib.request.urlopen(urllib.request.Request(
        f"{N8N}/workflows/{WID}", method="DELETE", headers=H), timeout=15)

citas = body.get("data", [])
print(f"Total citas {FECHA}: {len(citas)}\n")
# Ordenar por hora_inicio
citas.sort(key=lambda c: c.get("hora_inicio", ""))
for c in citas:
    estado = c.get("estado_cita", "?")
    anul = c.get("estado_anulacion", 0)
    marker = " (ANULADA)" if anul == 1 else ""
    print(f"  {c.get('hora_inicio'):8s}  dur={c.get('duracion'):>3d}m  estado={estado}{marker}  pac={c.get('nombre_paciente'):30s} dentista={c.get('nombre_dentista','').strip()}")

# Inferir rango horario donde la Dra atiende (primera y ultima hora_inicio activa)
activos = [c for c in citas if c.get("estado_anulacion") != 1]
if activos:
    print(f"\nRango activo: {activos[0]['hora_inicio']} - {activos[-1]['hora_inicio']}")
