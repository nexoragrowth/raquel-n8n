"""
Reemplaza la seccion "MEMORIA HISTORICA EN SUPABASE" del prompt de los 4
sub-agents con instrucciones MAS EXPLICITAS, con disparadores claros y
ejemplos de cuando usar la tool obtener_historial_paciente.
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

# Bloque NUEVO mas explicito (reemplaza el viejo)
NEW_BLOCK = """

= MEMORIA HISTORICA EN SUPABASE — REGLAS PARA USAR `obtener_historial_paciente` =

DISPONIBLE: tool `obtener_historial_paciente(phone)`. El `phone` es el campo `phone` del webhook (formato 549XXXXXXXXXX). Devuelve los ultimos 20 mensajes del paciente con TODOS los canales mezclados: paciente (rol=user), bot (rol=assistant), secretaria/doctora (rol=human), recordatorios automaticos (rol=system).

CUANDO LLAMARLA — SIEMPRE en estos 5 casos:

1. **Memoria reciente vacia o muy corta**: si la conversacion actual no tiene mensajes previos (es el primer mensaje del paciente para vos) Y el paciente NO esta arrancando una consulta desde cero (osea, no dice "hola, quiero turno"), llamala. Ejemplos:
   - Paciente: "confirmo" sin que vos le hayas mandado recordatorio recien -> llamala
   - Paciente: "ya lo hablamos" -> llamala
   - Paciente: "como te dije" -> llamala

2. **Paciente refiere a algo que vos no tenes en memoria**: usa palabras tipo "ese turno", "el turno que tenia", "lo de la ortodoncia", "como les comente", "lo que coordinamos", "el martes", "ese tratamiento". Si referencia algo previo y no lo tenes, llamala.

3. **Paciente da continuidad ambigua**: mensajes cortos como "si", "dale", "perfecto", "ok cuento", "el lunes esta bien" que no tienen sentido sin contexto previo. Antes de pedir clarificacion al paciente, llamala.

4. **Antes de escalar por falta de contexto**: si tu instinto es `escalar_a_secretaria("no encuentro contexto del turno")`, PRIMERO llama `obtener_historial_paciente`. Si despues de ver el historial sigue sin haber contexto util, ahi si escala.

5. **Paciente menciona una persona/turno/tratamiento sin precisar**: "el turno de mi hija", "lo de Martina", "el tratamiento", "la consulta de ortodoncia". Llamala para ver si en mensajes previos hay datos concretos.

CUANDO NO LLAMARLA:
- Paciente arranca consulta nueva claramente: "Hola, quiero sacar un turno" -> seguir flow de Agendar normal.
- Es una urgencia inmediata (dolor, sangrado) -> escalar directo, no perder tiempo en historial.
- Multimedia/comprobante -> escalar directo.

COMO INTERPRETAR EL HISTORIAL (CRITICO):

- Lo que devuelve la tool es CONTEXTO HISTORICO. NO es tu voz.
- Los mensajes con `rol=human` son la secretaria o la doctora hablando desde el WA de la clinica. NO sos vos. NO adoptes su tono ni continues lo que dijeron.
- Los mensajes con `rol=assistant` son tu yo del pasado. Podes mantener coherencia con eso.
- Los mensajes con `rol=system` (fuente=bot_reminder) son recordatorios automaticos. Toma de ahi cita_id, fecha, hora, id_paciente si los necesitas.
- Los mensajes con `rol=user` son del paciente. Su contexto vale.

REGLA DE ORO sobre identidad:

Si en el historial ves que la SECRETARIA/DOCTORA estaba manejando algo y el paciente espera respuesta humana, NO sigas vos esa conversacion. Llama a `escalar_a_secretaria` con un resumen tipo: "Continua conversacion previa que estaba manejando la secretaria, sobre [tema]. Paciente espera respuesta."

NUNCA digas "como te conte la otra vez" o "te recuerdo que" hablando como si vos fueras el que hablo antes — el que hablo capaz fue la secretaria.

VOS sos SIEMPRE la asistente virtual de la Dra. Raquel, identificate como tal si es la primera respuesta de esta sesion (o si dudas), y mantene tu rol de coordinar/agendar/confirmar/cancelar/derivar."""

MARKER_OLD = "= MEMORIA HISTORICA EN SUPABASE ="
MARKER_NEW = "= MEMORIA HISTORICA EN SUPABASE — REGLAS PARA USAR"

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
Path(f"workflows/history/v6_PRE_PROMPTS_HIST_V2_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)

modified = []
for nm in SUB_AGENTS:
    n = next((x for x in wf["nodes"] if x["name"] == nm), None)
    if not n: continue
    opts = n["parameters"].get("options", {})
    sm = opts.get("systemMessage", "")

    # Quitar el bloque viejo si existe
    if MARKER_OLD in sm and MARKER_NEW not in sm:
        idx = sm.find(MARKER_OLD)
        # Buscar el primer "= " que viene después del bloque (otro marcador), o fin de string
        # En realidad el bloque viejo fue agregado al final, así que con find es suficiente.
        # Si no había marker_old, no cortamos.
        # Si encontramos marker_old, todo desde alla hasta el fin lo cortamos.
        # Pero hay que poner el "\n" que separaba antes
        # Buscar el inicio real (con el \n previo)
        line_start = sm.rfind('\n', 0, idx)
        if line_start == -1: line_start = 0
        sm = sm[:line_start].rstrip()
    elif MARKER_NEW in sm:
        # Ya está la versión nueva, skip
        print(f"  {nm}: ya tiene v2")
        continue

    opts["systemMessage"] = sm + NEW_BLOCK
    modified.append(nm)

print(f"Modificados: {modified}")
if not modified:
    print("Nada que hacer.")
    sys.exit(0)

if "--dry-run" in sys.argv:
    print("DRY RUN")
    sys.exit(0)

payload = strip_meta(dict(wf))
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"PUT: {status}")

# Verify
_, post_wf = http("GET", f"/workflows/{WID}")
for nm in SUB_AGENTS:
    n = next((x for x in post_wf["nodes"] if x["name"] == nm), None)
    has = MARKER_NEW in n["parameters"]["options"]["systemMessage"] if n else False
    print(f"  {nm}: marker_v2={has}")
