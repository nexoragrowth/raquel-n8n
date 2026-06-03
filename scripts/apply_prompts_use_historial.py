"""
Actualiza el systemMessage de los 4 sub-agents (Confirmar/Cancelar/Agendar/General)
para que sepan que tienen la tool `obtener_historial_paciente` disponible.

Nota: Phase B v5 (this) NO toca el flow estructural - solo agrega 1 oracion al
system message. La tool fue creada por Lucas en UI y conectada via API.
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

# Nota a agregar al final del systemMessage de cada sub-agent
SUFFIX = """

= MEMORIA HISTORICA EN SUPABASE =
Tenes la tool `obtener_historial_paciente(phone)` que trae los ultimos 20 mensajes del paciente (incluyendo lo que hablo con la secretaria/doctora). USAR cuando:
- La memoria reciente esta vacia o no encontras contexto del paciente.
- Sospechas que el paciente ya hablo antes (por ej, "como les comente la otra vez").
- Necesitas saber que tratamiento tiene o que turnos pidio antes.

CRITICO: lo que devuelve es CONTEXTO HISTORICO, no tu voz. Lo que dijo la secretaria/doctora NO sos vos. Sos siempre la asistente virtual. Si el paciente esperaba respuesta de la secretaria, usar escalar_a_secretaria. NUNCA continues una conversacion que era humana."""

MARKER = "= MEMORIA HISTORICA EN SUPABASE ="
SUB_AGENTS = ['Sub-Agent Confirmar', 'Sub-Agent Cancelar', 'Sub-Agent Agendar', 'Sub-Agent General']


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


print("Pulling v6...")
_, wf = http("GET", f"/workflows/{WID}")
stamp = time.strftime("%Y%m%d_%H%M%S")
Path("workflows/history").mkdir(parents=True, exist_ok=True)
Path(f"workflows/history/v6_PRE_PROMPTS_HIST_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)

modified = []
for nm in SUB_AGENTS:
    n = next((x for x in wf["nodes"] if x["name"] == nm), None)
    if not n: continue
    opts = n["parameters"].get("options", {})
    sm = opts.get("systemMessage", "")
    if MARKER in sm:
        print(f"  {nm}: ya aplicado")
        continue
    opts["systemMessage"] = sm + SUFFIX
    modified.append(nm)

print(f"Modificados: {modified}")
if not modified:
    print("Nada que hacer.")
    sys.exit(0)

if "--dry-run" in sys.argv:
    print("DRY RUN — no PUT.")
    sys.exit(0)

payload = strip_meta(dict(wf))
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"PUT: {status}")
print("done.")
