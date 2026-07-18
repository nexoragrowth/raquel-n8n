"""
Fix 2 sintaxis de tools nuevas en v6:
- Usar URL con {placeholder} + placeholderDefinitions (no $fromAI)
- Mantener headerParameters.parameters para apikey + Bearer
- Hardcodear params estaticos en la URL (no parametersQuery)
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
(hist / f"v6_PRE_FIXPLACE_{ts}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_FIXPLACE_{ts}.json")

# Headers comunes Supabase REST
SB_HEADERS = [
    {"name": "apikey", "value": SR},
    {"name": "Authorization", "value": f"Bearer {SR}"},
    {"name": "Content-Type", "value": "application/json"},
]

# ============================================================
# consultar_recordatorios_abiertos
# ============================================================
n = next(x for x in wf["nodes"] if x["name"] == "consultar_recordatorios_abiertos")
select_cols = "id_cita_dentalink,id_paciente_dentalink,nombre_paciente,fecha_turno,hora_turno,tipo,enviado_at"
n["parameters"] = {
    "toolDescription": (
        "PRIMER paso siempre en Sub-Agent Confirmar/Cancelar. Lee la tabla "
        "recordatorios_enviados de Supabase para identificar que turnos del cron "
        "esperan respuesta. Devuelve array JSON con: id_cita_dentalink, "
        "id_paciente_dentalink, nombre_paciente, fecha_turno, hora_turno, tipo, "
        "enviado_at. Si devuelve >=1 filas, usalas directo (ya estan filtradas: "
        "solo recordatorios abiertos para ese phone). Si devuelve 0, recien ahi "
        "caer al flow legacy de buscar en Dentalink. El parametro phone es el "
        "celular del paciente en formato 549XXXXXXXXXX (sin +)."
    ),
    "method": "GET",
    "url": (f"{SB}/rest/v1/recordatorios_enviados?"
            f"select={select_cols}&"
            "telefono=eq.{phone}&"
            "confirmado_at=is.null&"
            "cancelado_at=is.null&"
            "order=fecha_turno,hora_turno"),
    "sendHeaders": True,
    "headerParameters": {"parameters": [
        {"name": "apikey", "value": SR},
        {"name": "Authorization", "value": f"Bearer {SR}"},
    ]},
    "placeholderDefinitions": {"values": [
        {"name": "phone",
         "description": "Celular del paciente en formato 549XXXXXXXXXX (13 digitos, sin +)",
         "type": "string"},
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
        "Dentalink, para cerrar el recordatorio en la tabla. Parametro: "
        "id_cita_dentalink (int) del turno recien confirmado."
    ),
    "method": "PATCH",
    "url": (f"{SB}/rest/v1/recordatorios_enviados?"
            "id_cita_dentalink=eq.{id_cita_dentalink}&"
            "confirmado_at=is.null"),
    "sendHeaders": True,
    "headerParameters": {"parameters": [
        {"name": "apikey", "value": SR},
        {"name": "Authorization", "value": f"Bearer {SR}"},
        {"name": "Content-Type", "value": "application/json"},
        {"name": "Prefer", "value": "return=minimal"},
    ]},
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": '={ "confirmado_at": "{{ $now.toISO() }}" }',
    "placeholderDefinitions": {"values": [
        {"name": "id_cita_dentalink",
         "description": "id_cita_dentalink (int) del turno que se acaba de confirmar en Dentalink",
         "type": "number"},
    ]},
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
        "Dentalink. Parametro: id_cita_dentalink (int) del turno cancelado."
    ),
    "method": "PATCH",
    "url": (f"{SB}/rest/v1/recordatorios_enviados?"
            "id_cita_dentalink=eq.{id_cita_dentalink}&"
            "cancelado_at=is.null"),
    "sendHeaders": True,
    "headerParameters": {"parameters": [
        {"name": "apikey", "value": SR},
        {"name": "Authorization", "value": f"Bearer {SR}"},
        {"name": "Content-Type", "value": "application/json"},
        {"name": "Prefer", "value": "return=minimal"},
    ]},
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": '={ "cancelado_at": "{{ $now.toISO() }}" }',
    "placeholderDefinitions": {"values": [
        {"name": "id_cita_dentalink",
         "description": "id_cita_dentalink (int) del turno que se acaba de cancelar en Dentalink",
         "type": "number"},
    ]},
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
(hist / f"v6_POST_FIXPLACE_{ts}.json").write_text(json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_FIXPLACE_{ts}.json")
for nm in ["consultar_recordatorios_abiertos","marcar_recordatorio_confirmado","marcar_recordatorio_cancelado"]:
    n = next(x for x in wf_post["nodes"] if x["name"] == nm)
    pd = n["parameters"].get("placeholderDefinitions", {}).get("values", [])
    print(f"  {nm}: placeholders={[p['name'] for p in pd]}")
