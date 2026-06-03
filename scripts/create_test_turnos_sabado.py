"""
Crea 2 turnos test en Dentalink para sabado 30/5/2026:
- 10:00 — Test - Lucas Silva (id 608)
- 11:00 — Test - Jana Test (id 621)

Ambos con mismo celular 5491161461034 (para reproducir caso multi-paciente).
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

# Jueves 4/6 — Tatiana 10:40 tope hasta ~11:10/11:20. Probamos slots mas tarde
TURNOS = [
    {"id_paciente": 608, "hora_inicio": "11:20", "duracion": 10, "label": "Lucas 11:20"},
    {"id_paciente": 621, "hora_inicio": "11:30", "duracion": 10, "label": "Jana 11:30"},
    {"id_paciente": 608, "hora_inicio": "11:30", "duracion": 10, "label": "Lucas 11:30"},
    {"id_paciente": 621, "hora_inicio": "11:40", "duracion": 10, "label": "Jana 11:40"},
]
FECHA = "2026-06-04"

def create_cita(id_pac, hora, dur, label):
    wh_path = f"create-cita-{id_pac}-{int(time.time())}"
    body = {
        "id_dentista": 1,
        "id_sucursal": 1,
        "id_sillon": 1,
        "id_paciente": id_pac,
        "fecha": FECHA,
        "hora_inicio": hora,
        "duracion": dur,
        "comentario": f"TEST flujo confirmar via WA — {label}",
    }
    wf = {
        "name": f"TEMP-CreateCita-{id_pac}",
        "nodes": [
            {"parameters": {"httpMethod": "POST", "path": wh_path,
                            "responseMode": "lastNode", "options": {}},
             "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook",
             "typeVersion": 2, "position": [240, 300], "webhookId": wh_path},
            {"parameters": {
                "method": "POST",
                "url": "https://api.dentalink.healthatom.com/api/v1/citas/",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendBody": True, "specifyBody": "json",
                "jsonBody": json.dumps(body),
                "options": {},
             },
             "id": "h", "name": "Create", "type": "n8n-nodes-base.httpRequest",
             "typeVersion": 4.2, "position": [460, 300],
             "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
             "continueOnFail": True, "alwaysOutputData": True},
        ],
        "connections": {"Webhook": {"main": [[{"node": "Create", "type": "main", "index": 0}]]}},
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
            f"https://n8n.raquelrodriguez.com.ar/webhook/{wh_path}",
            method="POST", headers={"Content-Type": "application/json"}, data=b"{}")
        with urllib.request.urlopen(hit, timeout=30) as r:
            return r.read().decode()
    finally:
        try:
            urllib.request.urlopen(urllib.request.Request(
                f"{N8N}/workflows/{WID}/deactivate", method="POST", headers=H), timeout=15)
        except Exception:
            pass
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N}/workflows/{WID}", method="DELETE", headers=H), timeout=15)

resultados = []
for t in TURNOS:
    print(f"\n>>> Creando turno {t['label']} ({FECHA} {t['hora_inicio']}) ...")
    body = create_cita(t["id_paciente"], t["hora_inicio"], t["duracion"], t["label"])
    print(f"  RESP: {body[:500]}")
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict) and parsed.get("data"):
            d = parsed["data"]
            resultados.append({
                "cita_id": d.get("id"),
                "id_paciente": d.get("id_paciente"),
                "nombre_paciente": d.get("nombre_paciente"),
                "fecha": d.get("fecha"),
                "hora": d.get("hora_inicio"),
                "id_estado": d.get("id_estado"),
                "estado_cita": d.get("estado_cita"),
            })
        else:
            err = parsed.get("error") if isinstance(parsed, dict) else None
            resultados.append({"label": t["label"], "ERR": err or parsed})
    except Exception as ex:
        resultados.append({"label": t["label"], "parse_err": str(ex)})

print(f"\n=== Resultados ===")
for r in resultados:
    print(f"  {json.dumps(r, ensure_ascii=False)}")
