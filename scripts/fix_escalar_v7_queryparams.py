"""
V7: escalar_a_secretaria como toolHttpRequest usando parametersQuery (mismo patron que
consultar_recordatorios_abiertos que YA FUNCIONA).

Cambia:
- v6 escalar_a_secretaria: toolHttpRequest con parametersQuery (no jsonBody)
- Helper Notify Grupo: lee query.resumen y query.phone en lugar de body
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
HELPER_ID = "S5U6tSipzlgFHCkf"
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"
ts = datetime.now().strftime("%Y%m%d_%H%M%S")

# ===========================================
# PARTE 1: v6 escalar_a_secretaria -> toolHttpRequest con parametersQuery
# ===========================================
wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_PRE_ESCALAR_V7_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup v6 -> v6_PRE_ESCALAR_V7_{ts}.json")

NEW_DESC = """Escala el caso a la secretaria humana: deriva al grupo de WhatsApp del consultorio.

USAR cuando: (a) urgencia medica o dental, (b) consulta clinica/diagnostico, (c) compras/pagos/comprobantes, (d) reprogramar turno (no soportado por flow), (e) pedido fuera de scope, (f) ambiguedad que requiere humano, (g) si no encontras turnos abiertos del paciente y no podes resolver con tools.

ARGS REQUERIDOS:
- resumen: 1-2 oraciones del caso para que la secretaria entienda sin abrir conversacion. Incluir nombre del paciente si lo conoces, motivo y accion concreta. Ejemplo: "Paciente Marcos pregunta por radiografia con Sancor, no tengo info del convenio. Verificar y responder".
- phone: telefono del paciente formato 549XXXXXXXXXX (sin +).

CRITICO: NUNCA llamar a esta tool sin pasar resumen no vacio."""

n = next(x for x in wf["nodes"] if x["name"] == "escalar_a_secretaria")
prev_id = n["id"]
prev_pos = n["position"]
n["type"] = "@n8n/n8n-nodes-langchain.toolHttpRequest"
n["typeVersion"] = 1.1
n["parameters"] = {
    "toolDescription": NEW_DESC,
    "method": "POST",
    "url": "https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo",
    "sendQuery": True,
    "parametersQuery": {"values": [{"name": "resumen"}, {"name": "phone"}]},
    "optimizeResponse": True,
}
n["id"] = prev_id
n["position"] = prev_pos

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
print(f"v6 PUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:400])
    sys.exit(1)

# ===========================================
# PARTE 2: Helper Notify Grupo -> leer query en lugar de body
# ===========================================
hf = requests.get(f"{N8N}/api/v1/workflows/{HELPER_ID}", headers=H, timeout=30).json()
(hist / f"helper_PRE_ESCALAR_V7_{ts}.json").write_text(
    json.dumps(hf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup helper -> helper_PRE_ESCALAR_V7_{ts}.json")

# Notify Grupo Send: messageText desde query.resumen
send = next(x for x in hf["nodes"] if x["name"] == "Notify Grupo Send")
old_text = send["parameters"].get("messageText", "")
new_text = "={{ '[ESCALADO BOT] ' + ($('Webhook').first().json.query.resumen || ($('Webhook').first().json.body && $('Webhook').first().json.body.text) || 'Caso escalado sin resumen.') }}"
send["parameters"]["messageText"] = new_text
print(f"messageText old: {old_text!r}")
print(f"messageText new: {new_text!r}")

# Chatwoot Apply: leer phone desde query (con fallback a body)
chatwoot = next(x for x in hf["nodes"] if x["name"] == "Chatwoot Apply")
new_js = chatwoot["parameters"]["jsCode"].replace(
    "const wh = $('Webhook').first().json.body || {};",
    "const _wh = $('Webhook').first().json; const wh = _wh.query || _wh.body || {};"
)
chatwoot["parameters"]["jsCode"] = new_js
print(f"Chatwoot Apply: updated to read query first, fallback body")

# PUT helper
helper_settings = {k: v for k, v in (hf.get("settings") or {}).items() if k in allowed}
hpayload = {"name": hf["name"], "nodes": hf["nodes"],
            "connections": hf["connections"], "settings": helper_settings}
if hf.get("staticData") is not None:
    hpayload["staticData"] = hf["staticData"]
r2 = requests.put(f"{N8N}/api/v1/workflows/{HELPER_ID}", headers=H,
                  data=json.dumps(hpayload, ensure_ascii=False).encode("utf-8"), timeout=60)
print(f"helper PUT: {r2.status_code}")
if r2.status_code >= 400:
    print(r2.text[:400])
    sys.exit(1)

print("\nV7 aplicado: v6 escalar usa parametersQuery + helper lee query")
