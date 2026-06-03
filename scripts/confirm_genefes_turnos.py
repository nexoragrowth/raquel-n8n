"""
Confirma en Dentalink los turnos 7952 (Guillermina Jenefes 15:50) y 7953
(Manuel Jenefes 16:30) del 27/5/2026 — id_estado = 18 (Confirmada).

Lucas dio OK explicito. Usa patron temp workflow con cred httpHeaderAuth
de Dentalink. Verifica el cambio con GET post-PUT.
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

CITAS_A_CONFIRMAR = [
    {"id": 7952, "label": "Guillermina Jenefes (id_pac=102) 27/5 15:50 Invisalign"},
    {"id": 7953, "label": "Manuel Jenefes (id_pac=103) 27/5 16:30 Brackets"},
]
ID_ESTADO_CONFIRMADA = 18

def run_temp_wf(name, nodes, connections, hit_path):
    """Crear -> activar -> hit -> deactivate -> delete. Devuelve body decoded."""
    wf = {"name": name, "nodes": nodes, "connections": connections,
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

results = []

for cita in CITAS_A_CONFIRMAR:
    cid = cita["id"]
    print(f"\n>>> Confirmando cita {cid} ({cita['label']}) ...")
    wh_path = f"confirm-{cid}-{int(time.time())}"
    nodes = [
        {"parameters": {"httpMethod": "POST", "path": wh_path,
                        "responseMode": "lastNode", "options": {}},
         "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook",
         "typeVersion": 2, "position": [240, 300], "webhookId": wh_path},
        {"parameters": {
            "method": "PUT",
            "url": f"https://api.dentalink.healthatom.com/api/v1/citas/{cid}",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True, "specifyBody": "json",
            "jsonBody": json.dumps({"id_estado": ID_ESTADO_CONFIRMADA}),
            "options": {},
         },
         "id": "h", "name": "PutEstado", "type": "n8n-nodes-base.httpRequest",
         "typeVersion": 4.2, "position": [460, 300],
         "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
         "continueOnFail": True, "alwaysOutputData": True},
    ]
    connections = {"Webhook": {"main": [[{"node": "PutEstado", "type": "main", "index": 0}]]}}
    body = run_temp_wf(f"TEMP-Confirm-{cid}", nodes, connections, wh_path)
    print(f"  RESP body (first 500): {body[:500]}")
    try:
        parsed = json.loads(body)
        # Dentalink devuelve { links, data: {id, ..., id_estado, estado_cita, ...} }
        d = parsed.get("data") if isinstance(parsed, dict) else None
        if isinstance(d, dict):
            results.append({
                "cita_id": cid,
                "id_estado_post": d.get("id_estado"),
                "estado_cita_post": d.get("estado_cita"),
                "fecha": d.get("fecha"),
                "hora": d.get("hora_inicio"),
                "paciente": d.get("nombre_paciente"),
            })
        else:
            results.append({"cita_id": cid, "raw": str(parsed)[:300]})
    except Exception as ex:
        results.append({"cita_id": cid, "parse_err": str(ex), "body": body[:300]})

# Re-verificar con GET en Dentalink para confirmar el cambio
print("\n\n=== Verificacion (GET citas del 27/5 post-PUT) ===")
wh_path_v = f"verify-genefes-{int(time.time())}"
nodes_v = [
    {"parameters": {"httpMethod": "POST", "path": wh_path_v,
                    "responseMode": "lastNode", "options": {}},
     "id": "wh", "name": "Webhook", "type": "n8n-nodes-base.webhook",
     "typeVersion": 2, "position": [240, 300], "webhookId": wh_path_v},
    {"parameters": {
        "url": "https://api.dentalink.healthatom.com/api/v1/sucursales/1/citas",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "q", "value": json.dumps({"fecha": {"eq": "2026-05-27"}})}
        ]},
        "options": {},
     },
     "id": "h", "name": "GetCitas", "type": "n8n-nodes-base.httpRequest",
     "typeVersion": 4.2, "position": [460, 300],
     "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
     "continueOnFail": True, "alwaysOutputData": True},
]
conns_v = {"Webhook": {"main": [[{"node": "GetCitas", "type": "main", "index": 0}]]}}
vbody = run_temp_wf(f"TEMP-Verify-Genefes", nodes_v, conns_v, wh_path_v)
try:
    vparsed = json.loads(vbody)
    for c in vparsed.get("data", []):
        if c.get("id") in (7952, 7953):
            print(f"  cita_id={c.get('id')} pac={c.get('nombre_paciente')} hora={c.get('hora_inicio')} "
                  f"id_estado={c.get('id_estado')} ({c.get('estado_cita')})")
except Exception as ex:
    print(f"  verify parse err: {ex}")

print("\n=== Resultados PUT ===")
for r in results:
    print(f"  {json.dumps(r, ensure_ascii=False)}")
