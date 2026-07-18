"""
Fix: el workflow Recordatorios mandaba recordatorio a pacientes YA confirmados
(id_estado=18 'Confirmado por whatsapp'), generando doble recordatorio y molestia.

Cambio en el filtro 'Solo citas activas':
  ANTES: estado_anulacion != 1
  AHORA: estado_anulacion != 1 AND id_estado != 18

Reportado por la doctora 22/5/2026:
- 8 turnos para lunes 26
- 6 estaban id_estado=18 (verde fluor en agenda Dentalink = paciente ya confirmo)
- Bot les envio recordatorio igual -> molestia
- 2 estaban id_estado=14 (cambio de fecha) -> esos SI necesitan recordatorio
"""
import json
import sys
import time
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

API_KEY = require('N8N_API_KEY')
API_BASE = f"{require('N8N_BASE_URL')}/api/v1"
WID = require('N8N_WORKFLOW_RECORDATORIOS_ID')

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}


def http(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        headers={"X-N8N-API-KEY": API_KEY, "Content-Type": "application/json", "Accept": "application/json"},
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


def strip_meta(wf):
    for k in ("id", "active", "createdAt", "updatedAt", "tags", "versionId", "triggerCount",
              "meta", "isArchived", "shared", "homeProject", "sharedWithProjects", "scopes",
              "description", "pinData", "activeVersionId", "versionCounter", "activeVersion"):
        wf.pop(k, None)
    s = wf.get("settings") or {}
    wf["settings"] = {k: v for k, v in s.items() if k in ALLOWED_SETTINGS}
    return wf


print("Pulling Recordatorios workflow...")
_, wf = http("GET", f"/workflows/{WID}")

stamp = time.strftime("%Y%m%d_%H%M%S")
Path("workflows/history").mkdir(parents=True, exist_ok=True)
Path(f"workflows/history/recordatorios_PRE_SKIP_CONFIRMADOS_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(f"  backup OK")

n = next((x for x in wf["nodes"] if x["name"] == "Solo citas activas"), None)
if not n:
    sys.exit("ERROR: nodo 'Solo citas activas' no existe")

# Agregar nueva condicion: id_estado != 18 (Confirmado por whatsapp)
conds = n["parameters"]["conditions"]["conditions"]
already = any(
    c.get("leftValue") == "={{ $json.id_estado }}"
    for c in conds
)
if already:
    print("  Fix ya aplicado, nothing to do.")
    sys.exit(0)

new_cond = {
    "id": "condition-2-skip-confirmados",
    "leftValue": "={{ $json.id_estado }}",
    "rightValue": 18,
    "operator": {"type": "number", "operation": "notEquals"},
}
conds.append(new_cond)
n["parameters"]["conditions"]["combinator"] = "and"

print(f"  Conditions ahora:")
for c in conds:
    print(f"    {c.get('leftValue')} {c.get('operator',{}).get('operation')} {c.get('rightValue')}")

if "--dry-run" in sys.argv:
    Path(f"workflows/history/recordatorios_FIX_DRY_{stamp}.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("  DRY RUN")
    sys.exit(0)

payload = strip_meta(dict(wf))
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"  PUT: {status}")
Path(f"workflows/history/recordatorios_POST_SKIP_CONFIRMADOS_{stamp}.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("  OK. Proxima ejecucion (lunes 25/5 10:00 ARG) ya respeta el nuevo filtro.")
