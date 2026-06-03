"""
Busca en los proximos 10 dias una fecha con 0 turnos en Dentalink,
para usarla como dia 'limpio' para los tests con Lucas + Jana.
"""
import json
import sys
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/") + "/api/v1"
KEY = require("N8N_API_KEY")
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
DT_CRED = "TwN6eBWsydjMdsCM"

def get_citas(fecha_str):
    wh = f"chk-empty-{fecha_str.replace('-','')}-{int(time.time()*1000)%10000}"
    wf = {
        "name": f"TEMP-Empty-{wh}",
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
                    {"name": "q", "value": json.dumps({"fecha": {"eq": fecha_str}})}
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
    req = urllib.request.Request(
        f"{N8N}/workflows", method="POST", headers=H,
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
        # Solo contar citas no anuladas
        citas = body.get("data", [])
        activas = [c for c in citas if c.get("estado_anulacion") != 1]
        return len(activas), len(citas)
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"{N8N}/workflows/{WID}/deactivate", method="POST", headers=H), timeout=15)
        except Exception:
            pass
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N}/workflows/{WID}", method="DELETE", headers=H), timeout=15)

dias_es = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
hoy = date.today()
print(f"Hoy: {hoy.isoformat()} ({dias_es[hoy.weekday()]})\n")
print(f"{'Fecha':12s}  {'Dia':10s}  {'Activos':>8s}  {'Total':>6s}")
print("-" * 45)
candidatos = []
for d in range(1, 11):
    f = hoy + timedelta(days=d)
    try:
        activas, total = get_citas(f.isoformat())
    except Exception as ex:
        print(f"{f.isoformat()}  ERR: {ex}")
        continue
    nombre_dia = dias_es[f.weekday()]
    marker = ""
    if activas == 0:
        marker = "  <-- LIBRE"
        candidatos.append((f, nombre_dia))
    print(f"{f.isoformat()}  {nombre_dia:10s}  {activas:>8d}  {total:>6d}{marker}")

if candidatos:
    print(f"\nCandidatos para test ({len(candidatos)}):")
    for f, n in candidatos:
        print(f"  {f.isoformat()} ({n})")
else:
    print("\nNo se encontraron dias con 0 turnos activos. Habria que usar el de menos turnos + filtro.")
