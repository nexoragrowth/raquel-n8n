"""
Re-fix con sintaxis EXACTA de buscar_paciente_dentalink (que funciona):
- parametersQuery.values con {name: 'X'} SIN value para el LLM-fillable
- URL hardcodea los demas params estaticos
- parametersHeaders.values con SR JWT inline (auth)
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
(hist / f"v6_PRE_OLDSYN_{ts}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_OLDSYN_{ts}.json")

select_cols = "id_cita_dentalink,id_paciente_dentalink,nombre_paciente,fecha_turno,hora_turno,tipo,enviado_at"

# ============================================================
# consultar_recordatorios_abiertos
# URL con params estaticos + parametersQuery.values con [{name: 'telefono'}] LLM-fillable
# ============================================================
n = next(x for x in wf["nodes"] if x["name"] == "consultar_recordatorios_abiertos")
n["parameters"] = {
    "toolDescription": (
        "PRIMER paso obligatorio en Sub-Agent Confirmar/Cancelar. Consulta Supabase "
        "'recordatorios_enviados' filtrando por el celular del paciente. Devuelve "
        "array JSON con: id_cita_dentalink, id_paciente_dentalink, nombre_paciente, "
        "fecha_turno, hora_turno, tipo. Si devuelve >=1 filas, usalas directo "
        "como cita_ids. Si devuelve 0, fallback al flow legacy.\n\n"
        "PARAMETRO: `telefono` debe pasarse en formato PostgREST como 'eq.<phone>'. "
        "EJEMPLO: si el paciente tiene phone 5491161461034, pasar telefono='eq.5491161461034'."
    ),
    "method": "GET",
    "url": (f"{SB}/rest/v1/recordatorios_enviados?"
            f"select={select_cols}&"
            "confirmado_at=is.null&"
            "cancelado_at=is.null&"
            "order=fecha_turno,hora_turno"),
    "sendQuery": True,
    "specifyQuery": "keypair",
    "parametersQuery": {"values": [
        {"name": "telefono"},  # LLM rellena. n8n lo agrega como &telefono=<value>
    ]},
    "sendHeaders": True,
    "specifyHeaders": "keypair",
    "parametersHeaders": {"values": [
        {"name": "apikey", "value": SR},
        {"name": "Authorization", "value": f"Bearer {SR}"},
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
        "(confirmado_at=now()). Llamala DESPUES de confirmar_turno exitoso.\n\n"
        "PARAMETRO: `id_cita_dentalink` en formato PostgREST 'eq.<id>'. "
        "EJEMPLO: para cita 8095, pasar id_cita_dentalink='eq.8095'."
    ),
    "method": "PATCH",
    "url": (f"{SB}/rest/v1/recordatorios_enviados?"
            "confirmado_at=is.null"),
    "sendQuery": True,
    "specifyQuery": "keypair",
    "parametersQuery": {"values": [
        {"name": "id_cita_dentalink"},  # LLM rellena
    ]},
    "sendHeaders": True,
    "specifyHeaders": "keypair",
    "parametersHeaders": {"values": [
        {"name": "apikey", "value": SR},
        {"name": "Authorization", "value": f"Bearer {SR}"},
        {"name": "Content-Type", "value": "application/json"},
        {"name": "Prefer", "value": "return=minimal"},
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
        "(cancelado_at=now()). Llamala DESPUES de cancelar_turno exitoso.\n\n"
        "PARAMETRO: `id_cita_dentalink` en formato PostgREST 'eq.<id>'. "
        "EJEMPLO: para cita 8095, pasar id_cita_dentalink='eq.8095'."
    ),
    "method": "PATCH",
    "url": (f"{SB}/rest/v1/recordatorios_enviados?"
            "cancelado_at=is.null"),
    "sendQuery": True,
    "specifyQuery": "keypair",
    "parametersQuery": {"values": [
        {"name": "id_cita_dentalink"},
    ]},
    "sendHeaders": True,
    "specifyHeaders": "keypair",
    "parametersHeaders": {"values": [
        {"name": "apikey", "value": SR},
        {"name": "Authorization", "value": f"Bearer {SR}"},
        {"name": "Content-Type", "value": "application/json"},
        {"name": "Prefer", "value": "return=minimal"},
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
(hist / f"v6_POST_OLDSYN_{ts}.json").write_text(json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_OLDSYN_{ts}.json")
