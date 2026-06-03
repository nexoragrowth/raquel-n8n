"""
Refuerza el system prompt del Sub-Agent Confirmar para que procese TODAS
las filas devueltas por consultar_recordatorios_abiertos, no solo la primera.

Reemplaza la sección "Afirmativo generico" del PASO 0 con instrucciones
mas explícitas sobre iteración.
"""
import json, sys
from datetime import datetime
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_PROMPT_ITERATE_{ts}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_PROMPT_ITERATE_{ts}.json")

sub = next(n for n in wf["nodes"] if n["name"] == "Sub-Agent Confirmar")
sys_msg = sub["parameters"]["options"]["systemMessage"]

# Texto original que vamos a reemplazar (el bullet "Afirmativo generico")
OLD = (
    "  - **Afirmativo generico** (\"confirmo\", \"confirmados\", \"si\", \"dale\", \"voy\", \"ahi estare\", emoji 👍): "
    "confirmar TODAS las filas devueltas. Por cada una: llamar `confirmar_turno(cita_id)` y despues "
    "`marcar_recordatorio_confirmado(id_cita_dentalink)`. Responder un canned consolidado:\n"
    "    - 1 fila: \"Listo, su turno del [fecha natural] a las [hora natural] queda confirmado. Cualquier consulta nos puede escribir por aca.\"\n"
    "    - >=2 filas: \"Listo, confirmados los [N] turnos: [nombre1] [hora1 natural] y [nombre2] [hora2 natural]. Cualquier consulta nos puede escribir por aca.\""
)

NEW = (
    "  - **Afirmativo generico** (\"confirmo\", \"confirmados\", \"si\", \"dale\", \"voy\", \"ahi estare\", emoji 👍): "
    "**ITERAR Y CONFIRMAR TODAS LAS FILAS, NO SOLO LA PRIMERA**.\n\n"
    "    REGLA OBLIGATORIA: si `consultar_recordatorios_abiertos` te devolvio N filas (N puede ser 1, 2, 3+), "
    "tenes que ejecutar `confirmar_turno` y `marcar_recordatorio_confirmado` UNA VEZ POR CADA FILA, "
    "antes de armar la respuesta final. NO armes el output ni te detengas hasta haber procesado las N filas.\n\n"
    "    Algoritmo explicito (segui paso a paso):\n"
    "    1. Recibis el array de N filas desde consultar_recordatorios_abiertos.\n"
    "    2. PARA fila 1: confirmar_turno(fila1.id_cita_dentalink) -> marcar_recordatorio_confirmado('eq.'+fila1.id_cita_dentalink).\n"
    "    3. PARA fila 2 (si N>=2): confirmar_turno(fila2.id_cita_dentalink) -> marcar_recordatorio_confirmado('eq.'+fila2.id_cita_dentalink).\n"
    "    4. PARA fila 3 (si N>=3): repetir.\n"
    "    5. RECIEN AHORA, despues de procesar TODAS las filas, armar la respuesta consolidada mencionando todos los turnos confirmados.\n\n"
    "    Idempotencia: si `confirmar_turno` devuelve HTTP 400 ('ya estaba en id_estado 18' o similar), igual llamar "
    "`marcar_recordatorio_confirmado` para cerrar la fila en la tabla, NO escalar.\n\n"
    "    Formato del output consolidado:\n"
    "    - 1 fila confirmada: \"Listo, su turno del [fecha natural] a las [hora natural] queda confirmado. Cualquier consulta nos puede escribir por aca.\"\n"
    "    - 2 filas confirmadas: \"Listo, confirmados los 2 turnos: [nombre1] [fecha natural] a las [hora1 natural] y [nombre2] a las [hora2 natural]. Cualquier consulta nos puede escribir por aca.\"\n"
    "    - 3+ filas: similar, listando cada uno separado por coma."
)

if OLD in sys_msg:
    new_sys = sys_msg.replace(OLD, NEW)
    sub["parameters"]["options"]["systemMessage"] = new_sys
    print(f"  prompt reforzado: {len(sys_msg)} -> {len(new_sys)} chars")
else:
    print(f"  !! anchor OLD no encontrado — abortando")
    print(f"  sys_msg sample (3000-4000):")
    print(sys_msg[3000:4000])
    sys.exit(1)

# PUT
allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
payload = {"name": wf["name"], "nodes": wf["nodes"],
           "connections": wf["connections"], "settings": settings}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]
r = requests.put(f"{N8N}/api/v1/workflows/{WF}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
print(f"PUT: {r.status_code}")
if r.status_code >= 400: print(r.text[:500]); sys.exit(1)
print("Done.")
