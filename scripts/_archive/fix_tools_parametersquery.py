"""
Re-fix tools nuevas: usar parametersQuery pattern (como buscar_paciente_dentalink)
en vez de placeholders en URL. El LLM rellena el value del param y le pedimos
en toolDescription que prefije con eq. para PostgREST.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
SB = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_PQFIX_{ts}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_PQFIX_{ts}.json")

SB_HEADERS_GET = [
    {"name": "apikey", "value": SR},
    {"name": "Authorization", "value": f"Bearer {SR}"},
]
SB_HEADERS_PATCH = SB_HEADERS_GET + [
    {"name": "Content-Type", "value": "application/json"},
    {"name": "Prefer", "value": "return=minimal"},
]

# ============================================================
# consultar_recordatorios_abiertos
# ============================================================
n = next(x for x in wf["nodes"] if x["name"] == "consultar_recordatorios_abiertos")
n["parameters"] = {
    "toolDescription": (
        "PRIMER paso obligatorio en Sub-Agent Confirmar/Cancelar. Lee la tabla "
        "Supabase 'recordatorios_enviados' filtrando por el celular del paciente "
        "para identificar que turnos del cron esperan respuesta. Devuelve un "
        "array JSON con: id_cita_dentalink, id_paciente_dentalink, nombre_paciente, "
        "fecha_turno, hora_turno, tipo. Si devuelve >=1 filas, usalas directo "
        "como cita_ids a confirmar. Si devuelve 0, fallback al flow legacy.\n\n"
        "PARAMETROS:\n"
        "- `telefono`: el celular del paciente, formato PostgREST: 'eq.5491200099999' "
        "(prefijo 'eq.' seguido del celular completo 549XXXXXXXXXX sin +). "
        "EJEMPLO: si el paciente tiene phone 5491161461034, pasar telefono='eq.5491161461034'."
    ),
    "method": "GET",
    "url": f"{SB}/rest/v1/recordatorios_enviados",
    "sendHeaders": True,
    "headerParameters": {"parameters": SB_HEADERS_GET},
    "sendQuery": True,
    "queryParameters": {"parameters": [
        {"name": "select",
         "value": "id_cita_dentalink,id_paciente_dentalink,nombre_paciente,fecha_turno,hora_turno,tipo,enviado_at"},
        {"name": "telefono"},  # SIN value — LLM rellena
        {"name": "confirmado_at", "value": "is.null"},
        {"name": "cancelado_at", "value": "is.null"},
        {"name": "order", "value": "fecha_turno,hora_turno"},
    ]},
    "optimizeResponse": True,
}

# ============================================================
# marcar_recordatorio_confirmado
# ============================================================
n = next(x for x in wf["nodes"] if x["name"] == "marcar_recordatorio_confirmado")
n["parameters"] = {
    "toolDescription": (
        "Marca una fila en recordatorios_enviados como confirmada "
        "(confirmado_at=now()). Llamala DESPUES de confirmar_turno exitoso en "
        "Dentalink, para cerrar el recordatorio en la tabla.\n\n"
        "PARAMETROS:\n"
        "- `id_cita_dentalink`: id del turno confirmado, formato PostgREST: "
        "'eq.8095' (prefijo 'eq.' seguido del id_cita_dentalink). "
        "EJEMPLO: para cerrar el recordatorio del cita 8095, pasar id_cita_dentalink='eq.8095'."
    ),
    "method": "PATCH",
    "url": f"{SB}/rest/v1/recordatorios_enviados",
    "sendHeaders": True,
    "headerParameters": {"parameters": SB_HEADERS_PATCH},
    "sendQuery": True,
    "queryParameters": {"parameters": [
        {"name": "id_cita_dentalink"},  # LLM rellena
        {"name": "confirmado_at", "value": "is.null"},
    ]},
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": '={ "confirmado_at": "{{ $now.toISO() }}" }',
    "optimizeResponse": True,
}

# ============================================================
# marcar_recordatorio_cancelado
# ============================================================
n = next(x for x in wf["nodes"] if x["name"] == "marcar_recordatorio_cancelado")
n["parameters"] = {
    "toolDescription": (
        "Marca una fila en recordatorios_enviados como cancelada "
        "(cancelado_at=now()). Llamala DESPUES de cancelar_turno exitoso en "
        "Dentalink.\n\n"
        "PARAMETROS:\n"
        "- `id_cita_dentalink`: id del turno cancelado, formato PostgREST: "
        "'eq.8095' (prefijo 'eq.' seguido del id_cita_dentalink). "
        "EJEMPLO: para cerrar el recordatorio del cita 8095, pasar id_cita_dentalink='eq.8095'."
    ),
    "method": "PATCH",
    "url": f"{SB}/rest/v1/recordatorios_enviados",
    "sendHeaders": True,
    "headerParameters": {"parameters": SB_HEADERS_PATCH},
    "sendQuery": True,
    "queryParameters": {"parameters": [
        {"name": "id_cita_dentalink"},
        {"name": "cancelado_at", "value": "is.null"},
    ]},
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": '={ "cancelado_at": "{{ $now.toISO() }}" }',
    "optimizeResponse": True,
}

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
(hist / f"v6_POST_PQFIX_{ts}.json").write_text(json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_PQFIX_{ts}.json")

for nm in ["consultar_recordatorios_abiertos","marcar_recordatorio_confirmado","marcar_recordatorio_cancelado"]:
    n = next(x for x in wf_post["nodes"] if x["name"] == nm)
    qp = n["parameters"].get("queryParameters",{}).get("parameters",[])
    llm_params = [p["name"] for p in qp if "value" not in p]
    print(f"  {nm}: LLM-fillable params = {llm_params}")
