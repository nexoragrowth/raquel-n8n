"""
Query READ-ONLY a Dentalink para encontrar los turnos del 27/5/2026
correspondientes a los pacientes 102, 103, 325 (todos con phone +543884321326).

Usa el patron de temp workflow para reusar la credencial httpHeaderAuth de
Dentalink (id TwN6eBWsydjMdsCM, "Header Auth account 3").

NO HACE PUT — solo muestra que turnos hay para que Lucas confirme antes
de marcar id_estado=18.
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
DT_CRED = "TwN6eBWsydjMdsCM"  # Header Auth account 3

FECHA = "2026-05-27"
PHONE_NORMALIZED = "+543884321326"   # como aparece en Dentalink
PHONE_ALT = "+5493884321326"          # variante con 9
PACIENTE_IDS = [102, 103, 325]

wh_path = f"genefes-check-{int(time.time())}"

temp_wf = {
    "name": f"TEMP-Check-Genefes-{int(time.time())}",
    "nodes": [
        {
            "parameters": {
                "httpMethod": "POST", "path": wh_path,
                "responseMode": "lastNode", "options": {}
            },
            "id": "wh", "name": "Webhook",
            "type": "n8n-nodes-base.webhook", "typeVersion": 2,
            "position": [240, 300], "webhookId": wh_path,
        },
        {
            "parameters": {
                "url": f"https://api.dentalink.healthatom.com/api/v1/sucursales/1/citas",
                "authentication": "genericCredentialType",
                "genericAuthType": "httpHeaderAuth",
                "sendQuery": True,
                "queryParameters": {
                    "parameters": [
                        {"name": "q", "value": json.dumps({"fecha": {"eq": FECHA}})}
                    ]
                },
                "options": {},
            },
            "id": "h", "name": "GetCitas",
            "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": [460, 300],
            "credentials": {"httpHeaderAuth": {"id": DT_CRED, "name": "Header Auth account 3"}},
            "continueOnFail": True, "alwaysOutputData": True,
        },
    ],
    "connections": {"Webhook": {"main": [[{"node": "GetCitas", "type": "main", "index": 0}]]}},
    "settings": {"executionOrder": "v1"},
}

print(f"Creando temp workflow para GET citas {FECHA}...")
req = urllib.request.Request(
    f"{N8N_BASE}/workflows", method="POST", headers=HEADERS,
    data=json.dumps(temp_wf).encode()
)
twf = json.loads(urllib.request.urlopen(req, timeout=30).read())
WID = twf["id"]
print(f"  workflow id: {WID}")

try:
    urllib.request.urlopen(urllib.request.Request(
        f"{N8N_BASE}/workflows/{WID}/activate", method="POST", headers=HEADERS
    ), timeout=20)
    time.sleep(2)

    print(f"Hitting webhook https://n8n.raquelrodriguez.com.ar/webhook/{wh_path} ...")
    hit = urllib.request.Request(
        f"https://n8n.raquelrodriguez.com.ar/webhook/{wh_path}",
        method="POST", headers={"Content-Type": "application/json"}, data=b"{}"
    )
    with urllib.request.urlopen(hit, timeout=30) as r:
        body = r.read().decode()
    resp = json.loads(body)
    citas = resp.get("data", [])
    print(f"\n=== Citas {FECHA} en sucursal 1 (total: {len(citas)}) ===\n")

    # Filtrar por pacientes target (102/103/325) y/o phone
    matches = []
    for c in citas:
        pid = c.get("id_paciente")
        cel = c.get("celular_paciente") or ""
        if pid in PACIENTE_IDS or PHONE_NORMALIZED in cel or PHONE_ALT in cel:
            matches.append(c)

    print(f"Matches para pacientes {PACIENTE_IDS} o phone {PHONE_NORMALIZED}: {len(matches)}\n")
    for c in matches:
        print(f"  cita_id={c.get('id')}")
        print(f"    id_paciente={c.get('id_paciente')} ({c.get('nombre_paciente')})")
        print(f"    fecha={c.get('fecha')} hora={c.get('hora_inicio')} dur={c.get('duracion')}")
        print(f"    id_estado={c.get('id_estado')} ({c.get('estado_cita')})")
        print(f"    estado_anulacion={c.get('estado_anulacion')}")
        print(f"    tratamiento={c.get('nombre_tratamiento')}")
        print(f"    celular={c.get('celular_paciente')}")
        print(f"    dentista={c.get('nombre_dentista')}")
        print()

    # Si no hubo matches por id_paciente, buscar tambien por celular en TODAS las citas del dia
    if not matches:
        print("Sin matches directos. Listando primeras 30 citas del dia con su celular:")
        for c in citas[:30]:
            print(f"  cita={c.get('id')} pac={c.get('id_paciente')} {c.get('nombre_paciente')[:30]:30s} cel={c.get('celular_paciente'):20s} hora={c.get('hora_inicio')}")

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
    print(f"\nTemp workflow {WID} eliminado.")
