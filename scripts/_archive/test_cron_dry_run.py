"""
Dry-run del cron Recordatorios para validar todo el flow SIN enviar WhatsApp.

Pasos:
1. Disable temporal del nodo 'Enviar WhatsApp' (sigue activo, pero saltea send)
2. Hit del webhook manual con {fecha_target: '2026-06-04', id_paciente_filter: [608, 621]}
3. Espera unos segundos
4. Verify: lee la ultima execution del cron + chequea filas en recordatorios_enviados
5. Re-enable del 'Enviar WhatsApp'

Si algo falla, el re-enable corre igual (finally).
"""
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require, env

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = env("N8N_WORKFLOW_RECORDATORIOS_ID", "7RqTApkvVavRmq3R")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}
SB = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
SBH = {"apikey": SR, "Authorization": f"Bearer {SR}"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

def put_workflow(wf_obj):
    """Mantiene solo keys permitidas para PUT."""
    allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
               "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
               "executionOrder", "callerPolicy", "callerIds"}
    settings = {k: v for k, v in (wf_obj.get("settings") or {}).items() if k in allowed}
    payload = {"name": wf_obj["name"], "nodes": wf_obj["nodes"],
               "connections": wf_obj["connections"], "settings": settings}
    if wf_obj.get("staticData") is not None:
        payload["staticData"] = wf_obj["staticData"]
    r = requests.put(f"{N8N}/api/v1/workflows/{WF}", headers=H,
                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
    return r.status_code, r.text

def set_send_disabled(disabled):
    wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
    send = next(n for n in wf["nodes"] if n["name"] == "Enviar WhatsApp")
    if disabled:
        send["disabled"] = True
    else:
        send.pop("disabled", None)
    code, txt = put_workflow(wf)
    print(f"  set 'Enviar WhatsApp' disabled={disabled} -> PUT {code}")
    if code >= 400:
        print(f"  {txt[:300]}")
    return code

# Backup pre
wf_pre = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"recordatorios_PRE_DRYRUN_{ts}.json").write_text(
    json.dumps(wf_pre, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> recordatorios_PRE_DRYRUN_{ts}.json\n")

# Clean cualquier fila previa de los pacientes test antes del run
print("[cleanup] borrando filas previas test (608/621) de recordatorios_enviados ...")
for pid in (608, 621):
    url = f"{SB}/rest/v1/recordatorios_enviados?id_paciente_dentalink=eq.{pid}"
    try:
        req = urllib.request.Request(url, headers={**SBH, "Content-Type": "application/json"}, method="DELETE")
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"  pid={pid}: DELETE status {r.status}")
    except Exception as ex:
        print(f"  pid={pid}: err {ex}")

# Tambien borrar las TEST-SEED de Lucas para no confundirnos
print("[cleanup] borrando filas TEST-SEED previas ...")
url = f"{SB}/rest/v1/recordatorios_enviados?workflow_execution_id=like.TEST-SEED*"
try:
    req = urllib.request.Request(url, headers={**SBH, "Content-Type": "application/json"}, method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as r:
        print(f"  TEST-SEED: DELETE status {r.status}")
except Exception as ex:
    print(f"  err {ex}")

try:
    print("\n[1/3] Disabling 'Enviar WhatsApp' ...")
    if set_send_disabled(True) >= 400:
        sys.exit(1)
    time.sleep(2)

    print("\n[2/3] Hit webhook trigger-recordatorios-manual ...")
    body = json.dumps({"fecha_target": "2026-06-04",
                       "id_paciente_filter": [608, 621]}).encode()
    hit_req = urllib.request.Request(
        "https://n8n.raquelrodriguez.com.ar/webhook/trigger-recordatorios-manual",
        method="POST", headers={"Content-Type": "application/json"}, data=body)
    try:
        with urllib.request.urlopen(hit_req, timeout=60) as r:
            resp = r.read().decode()
            print(f"  webhook status: {r.status}")
            print(f"  webhook body (300): {resp[:300]}")
    except urllib.error.HTTPError as e:
        print(f"  webhook HTTP {e.code}: {e.read().decode()[:300]}")
    except Exception as ex:
        print(f"  webhook err: {ex}")

    time.sleep(4)

    print("\n[3/3] Verify ...")
    # Verify rows en recordatorios_enviados
    url = (f"{SB}/rest/v1/recordatorios_enviados?id_paciente_dentalink=in.(608,621)"
           f"&select=*&order=enviado_at.desc")
    req = urllib.request.Request(url, headers=SBH)
    with urllib.request.urlopen(req, timeout=15) as r:
        rows = json.loads(r.read().decode())
    print(f"  Filas en recordatorios_enviados para pid in (608,621): {len(rows)}")
    for row in rows:
        print(f"    cita_id={row['id_cita_dentalink']} pac={row['nombre_paciente']} "
              f"fecha={row['fecha_turno']} hora={row['hora_turno']} "
              f"enviado_at={row['enviado_at']} wf_exec_id={row.get('workflow_execution_id')}")

    # Verify ultima execution del cron
    print("\n  Ultima execution del cron Recordatorios:")
    r = requests.get(f"{N8N}/api/v1/executions?workflowId={WF}&limit=3",
                     headers=H, timeout=30).json()
    for e in r.get("data", [])[:3]:
        print(f"    exec={e['id']} status={e.get('status')} startedAt={e.get('startedAt')}")
        # Detalle de la ultima
    if r.get("data"):
        eid = r["data"][0]["id"]
        d = requests.get(f"{N8N}/api/v1/executions/{eid}?includeData=true",
                         headers=H, timeout=30).json()
        last = d.get("data", {}).get("resultData", {}).get("lastNodeExecuted", "?")
        rdata = d.get("data", {}).get("resultData", {}).get("runData", {})
        print(f"    exec {eid} last_node: {last}")
        print(f"    nodos ejecutados ({len(rdata)}):")
        for nname in list(rdata.keys())[:30]:
            print(f"      - {nname}")
        # Si hay error
        err = d.get("data", {}).get("resultData", {}).get("error")
        if err:
            print(f"    ERROR: {json.dumps(err, ensure_ascii=False)[:400]}")

finally:
    print("\n[cleanup] Re-enabling 'Enviar WhatsApp' ...")
    set_send_disabled(False)
    print("Done.")
