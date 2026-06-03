"""
Agrega whitelist 'respuestas_agenda' al Pre-filtro Cierre para que palabras
cortas como 'Hoy', 'Lunes', 'Tarde', 'Mañana', etc. NO se descarten como NO_REPLY
cuando son respuestas a preguntas del bot sobre dia/hora.

Inserta el bloque ANTES del bloque short_closing existente.
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
(hist / f"v6_PRE_PREFILTER_AGENDA_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_PREFILTER_AGENDA_{ts}.json")

pf = next(x for x in wf["nodes"] if x["name"] == "Pre-filtro Cierre")
code = pf["parameters"]["jsCode"]
print(f"jsCode actual: {len(code)} chars")

# Anchor: insertar ANTES del bloque "Cierres exactos"
ANCHOR = "// === Cierres exactos ==="
NEW_BLOCK = """// === Respuestas de agenda — pasar (respuesta a pregunta del bot sobre dia/hora) ===
const respuestas_agenda = [
  'hoy','manana','mañana','pasado','pasado manana','pasado mañana',
  'lunes','martes','miercoles','miércoles','jueves','viernes','sabado','sábado','domingo',
  'el lunes','el martes','el miercoles','el miércoles','el jueves','el viernes','el sabado','el sábado','el domingo',
  'la mañana','la tarde','la noche','manana','tarde','noche',
  'temprano','mediodia','mediodía',
  'a la mañana','a la tarde','a la noche','a la manana',
  'manana temprano','manana tarde','manana noche',
  'cualquiera','cuando sea','no me importa','el que sea','lo antes posible','urgente','urgentemente'
];
if (respuestas_agenda.includes(t)) {
  return [{ json: { skip: false, reason: 'respuesta_agenda', text } }];
}

"""

if "respuestas_agenda" in code:
    print("  [skip] ya tiene whitelist respuestas_agenda")
elif ANCHOR not in code:
    print(f"  !! anchor '{ANCHOR}' no encontrado")
    sys.exit(1)
else:
    new_code = code.replace(ANCHOR, NEW_BLOCK + ANCHOR)
    pf["parameters"]["jsCode"] = new_code
    print(f"  whitelist agregada, jsCode: {len(code)} -> {len(new_code)} chars")

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
print(f"\nPUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:500]); sys.exit(1)

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_PREFILTER_AGENDA_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_PREFILTER_AGENDA_{ts}.json")
print(f"v6 active: {wf_post.get('active')}")

# Verify
pf_post = next(x for x in wf_post["nodes"] if x["name"] == "Pre-filtro Cierre")
code_post = pf_post["parameters"]["jsCode"]
print(f"\nVerify:")
print(f"  whitelist respuestas_agenda: {'OK' if 'respuestas_agenda' in code_post else 'MISSING'}")
print(f"  short_closing intacto: {'OK' if 'short_closing' in code_post else 'MISSING'}")
print(f"  injection patterns intactos: {'OK' if 'injectionPatterns' in code_post else 'MISSING'}")
print(f"  confirmaciones intactas: {'OK' if 'confirmacion_post_recordatorio' in code_post else 'MISSING'}")
