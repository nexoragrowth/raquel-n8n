"""
Refuerza la regla de idempotencia en Sub-Agent Confirmar:
cuando ver_turnos_paciente devuelve id_estado=18 (ya confirmado),
DEBE responder canned 'ya quedo confirmado', NO escalar.

Caso real validado 22/5: 4 pacientes (MARTA, Graciela, Victoria, Noelia)
confirmaron post-recordatorio, todas tenian id_estado=18, el bot escalo
a Iri en vez de responder canned. Eso genera trabajo extra para la secretaria.
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
WID = require('N8N_WORKFLOW_V6_ID')

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


OLD = """   - `id_estado == 18` (ya confirmado): NO llamar `confirmar_turno` de nuevo. Responder: "Su turno del [fecha natural] ya quedo confirmado. Cualquier cosa nos puede escribir."
   - `id_estado == 1` (anulado): "Veo que su turno del [fecha] aparece anulado. Le paso a la secretaria Irina para que coordine." + `escalar_a_secretaria`."""

NEW = """   - `id_estado == 18` (YA CONFIRMADO): **REGLA ABSOLUTA — NO ESCALAR**. Responder EXACTAMENTE este canned y TERMINAR el turno:
     `"Su turno del [fecha natural] a las [hora natural] ya queda confirmado. Cualquier consulta nos puede escribir por aca."`
     NO llamar `confirmar_turno` (ya esta). NO llamar `escalar_a_secretaria` (no hay nada que escalar — el paciente ya esta confirmado en sistema, solo nos esta reafirmando su asistencia). NO llamar `obtener_historial_paciente` (es ruido innecesario). NO inventar mas tools. SOLO responder el canned y FIN.
   - `id_estado == 1` (anulado): "Veo que su turno del [fecha] aparece anulado. Le paso a la secretaria Iri para que coordine." + `escalar_a_secretaria`."""


print("Pulling v6...")
_, wf = http("GET", f"/workflows/{WID}")

stamp = time.strftime("%Y%m%d_%H%M%S")
Path("workflows/history").mkdir(parents=True, exist_ok=True)
Path(f"workflows/history/v6_PRE_CONFIRMAR_IDEMPOTENCIA_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)

n = next((x for x in wf["nodes"] if x["name"] == "Sub-Agent Confirmar"), None)
if not n:
    sys.exit("ERROR: Sub-Agent Confirmar no existe")
sm = n["parameters"]["options"]["systemMessage"]

if NEW in sm:
    print("  Ya aplicado, nada que hacer.")
    sys.exit(0)
if OLD not in sm:
    sys.exit("ERROR: no encontre el bloque OLD en el prompt del Sub-Agent Confirmar")

new_sm = sm.replace(OLD, NEW)
n["parameters"]["options"]["systemMessage"] = new_sm

print(f"  Reemplazo aplicado (chars {len(OLD)} -> {len(NEW)})")

if "--dry-run" in sys.argv:
    print("DRY RUN")
    sys.exit(0)

payload = strip_meta(dict(wf))
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"  PUT: {status}")

# Verify
_, post_wf = http("GET", f"/workflows/{WID}")
post_n = next((x for x in post_wf["nodes"] if x["name"] == "Sub-Agent Confirmar"), None)
if NEW in post_n["parameters"]["options"]["systemMessage"]:
    print("  OK: regla de idempotencia reforzada en Sub-Agent Confirmar.")
else:
    sys.exit("ERROR post-verify: no quedo el cambio")
