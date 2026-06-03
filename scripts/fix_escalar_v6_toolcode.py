"""
Re-convertir escalar_a_secretaria a toolCode con $fromAI explicito.
Razon: toolHttpRequest no manda body al helper (body llega None).
toolCode con httpRequest desde JS es controlable.
"""
import json
import sys
import requests
from datetime import datetime
from pathlib import Path

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
(hist / f"v6_PRE_ESCALAR_V6_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup -> v6_PRE_ESCALAR_V6_{ts}.json")

NEW_JS = r"""// Escala al grupo via helper webhook notify-grupo.
// V6: toolCode + $fromAI con descripcion explicita.
// El helper notify-grupo funciona perfecto cuando recibe body bien (validado test directo 5:47 PM).
// El problema previo era toolHttpRequest no enviando body, ahora hacemos POST directo desde JS.

const resumen = $fromAI(
  'resumen',
  'Resumen breve (1-2 oraciones) del caso para que la secretaria entienda sin abrir la conversacion. Incluir nombre del paciente si lo conoces, motivo de la escalacion y accion concreta que necesita Iri o la doctora.',
  'string'
) || 'Caso escalado sin resumen.';

const phoneRaw = $fromAI(
  'phone',
  'Telefono del paciente formato 549XXXXXXXXXX (sin +). Esta en el bloque [CONTEXTO DEL PACIENTE QUE ESCRIBE] que recibis en el prompt.',
  'string'
) || '';

const phone = String(phoneRaw).replace(/^\+/, '');

try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
    headers: { 'Content-Type': 'application/json' },
    body: { text: '[ESCALADO BOT] ' + resumen, phone: phone },
    json: true
  });
  return 'Escalado al grupo correctamente.';
} catch (err) {
  const msg = String(err && err.message ? err.message : err).slice(0, 150);
  try { console.log('[escalar] notify-grupo fail:', msg); } catch(_) {}
  return 'Escalacion intentada (fallo el envio al grupo): ' + msg;
}
"""

NEW_DESC = """Escala el caso a la secretaria humana: deriva al grupo de WhatsApp del consultorio.

USAR cuando: (a) urgencia medica o dental, (b) consulta clinica/diagnostico, (c) compras/pagos/comprobantes, (d) reprogramar turno (no soportado por flow), (e) pedido fuera de scope, (f) ambiguedad que requiere humano, (g) si no encontras turnos abiertos del paciente y no podes resolver con tools.

ARGS REQUERIDOS:
- resumen (string, OBLIGATORIO): 1-2 oraciones del caso para que la secretaria entienda sin abrir conversacion. Incluir nombre del paciente si lo conoces, motivo y accion concreta. Ejemplo: "Paciente Marcos pregunta por radiografia con Sancor, no tengo info del convenio. Verificar y responder".
- phone (string, OBLIGATORIO): telefono del paciente formato 549XXXXXXXXXX (sin +).

CRITICO: NUNCA llamar a esta tool sin pasar resumen no vacio. Sin resumen, la secretaria no puede atender el caso."""

n = next(x for x in wf["nodes"] if x["name"] == "escalar_a_secretaria")
prev_id = n["id"]
prev_pos = n["position"]

n["type"] = "@n8n/n8n-nodes-langchain.toolCode"
n["typeVersion"] = 1
n["parameters"] = {
    "name": "escalar_a_secretaria",
    "description": NEW_DESC,
    "jsCode": NEW_JS,
}
n["id"] = prev_id
n["position"] = prev_pos

print(f"Re-convertido a toolCode V6")

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
if r.status_code >= 400:
    print(r.text[:400])
    sys.exit(1)

# Verify
wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
n_post = next(x for x in wf_post["nodes"] if x["name"] == "escalar_a_secretaria")
print(f"verify type: {n_post['type']}")
print(f"verify typeVersion: {n_post['typeVersion']}")
print(f"active: {wf_post.get('active')}")
