"""
Fix: Recordatorios duplicados a pacientes del martes.

Bug: el cron del workflow 'Recordatorio de Turno 48HS' (7RqTApkvVavRmq3R) corre
todos los dias. El nodo 'Fecha Manana' calcula addBusinessDays(hoy, 2), que
saltea sab+dom en el conteo. Resultado: viernes, sabado y domingo convergen
los tres al MISMO martes. Pacientes del martes reciben 3 recordatorios.

Evidencia (ejecuciones):
  vie 8/5 11:00 UTC -> fecha_target 2026-05-12 (6 enviados)
  sab 9/5 11:00 UTC -> fecha_target 2026-05-12 (6 enviados)
  dom 10/5 11:00 UTC -> fecha_target 2026-05-12 (6 enviados)
  lun 11/5 11:00 UTC -> fecha_target 2026-05-13 (9 enviados)

Fix: cambiar cron de '0 13 * * *' (todos los dias) a '0 13 * * 1-5' (solo
lunes-viernes). Cada paciente recibe UN recordatorio el dia habil
correspondiente.

Uso:
  python scripts/apply_cron_recordatorios_fix.py
"""
import json
import os
import sys
import time
import urllib.request

WORKFLOW_ID = "7RqTApkvVavRmq3R"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
API_KEY = os.environ.get("N8N_API_KEY")

if not API_KEY:
    print("ERROR: set N8N_API_KEY env var")
    sys.exit(1)

OLD_CRON = "0 13 * * *"
NEW_CRON = "0 13 * * 1-5"

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow",
    "timezone", "executionOrder", "callerPolicy", "callerIds",
}


def http(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        headers={
            "X-N8N-API-KEY": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


print(f"GET workflow {WORKFLOW_ID}...")
status, wf = http("GET", f"/workflows/{WORKFLOW_ID}")
print(f"  status={status} name={wf['name']!r} active={wf['active']}")

ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
backup_path = f"workflows/history/recordatorios_PRE_CRON_FIX_API_{ts}.json"
with open(backup_path, "w", encoding="utf-8") as f:
    json.dump(wf, f, ensure_ascii=False, indent=2)
print(f"  backup -> {backup_path}")

cron_node = None
for n in wf["nodes"]:
    if n["type"] == "n8n-nodes-base.scheduleTrigger":
        cron_node = n
        break

if not cron_node:
    print("ERROR: no scheduleTrigger node found")
    sys.exit(1)

current_expr = cron_node["parameters"]["rule"]["interval"][0]["expression"]
print(f"  current cron: {current_expr!r}")

if current_expr != OLD_CRON:
    print(f"WARN: expected {OLD_CRON!r}, found {current_expr!r}. Aborting (manual check needed).")
    sys.exit(1)

cron_node["parameters"]["rule"]["interval"][0]["expression"] = NEW_CRON
print(f"  new cron: {NEW_CRON!r}")

settings = {k: v for k, v in wf.get("settings", {}).items() if k in ALLOWED_SETTINGS}

payload = {
    "name": wf["name"],
    "nodes": wf["nodes"],
    "connections": wf["connections"],
    "settings": settings,
    "staticData": wf.get("staticData"),
}

print(f"PUT workflow {WORKFLOW_ID}...")
status, resp = http("PUT", f"/workflows/{WORKFLOW_ID}", payload)
print(f"  status={status}")

status2, wf2 = http("GET", f"/workflows/{WORKFLOW_ID}")
for n in wf2["nodes"]:
    if n["type"] == "n8n-nodes-base.scheduleTrigger":
        post_expr = n["parameters"]["rule"]["interval"][0]["expression"]
        print(f"  verified cron post-PUT: {post_expr!r}")
        assert post_expr == NEW_CRON, "FAIL: cron not persisted"
        break

post_path = f"workflows/history/recordatorios_POST_CRON_FIX_{ts}.json"
with open(post_path, "w", encoding="utf-8") as f:
    json.dump(wf2, f, ensure_ascii=False, indent=2)
print(f"  post-fix snapshot -> {post_path}")
print("OK")
