"""
Fix final auth para tools Supabase:
- Crear nueva cred httpHeaderAuth con Authorization: Bearer <SR>
- URL hardcodea apikey=<SR> como query param + filters estaticos
- LLM rellena solo el filter dinamico (telefono o id_cita_dentalink)
- Borrar cred apikey vieja (JT0D38dLlhoCEJGn no sirve por RLS)
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
SB = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

# 1. Crear cred Bearer
print("Creando cred Supabase Bearer ...")
body = {
    "name": "Supabase Bearer (service_role)",
    "type": "httpHeaderAuth",
    "data": {"name": "Authorization", "value": f"Bearer {SR}", "allowedDomains": "*"},
}
r = requests.post(f"{N8N}/api/v1/credentials", headers=H,
                  data=json.dumps(body).encode(), timeout=30)
print(f"  status: {r.status_code} body: {r.text[:300]}")
if r.status_code >= 400: sys.exit(1)
cred_id = r.json()["id"]
print(f"  cred id: {cred_id}")
SB_CRED = {"id": cred_id, "name": body["name"]}

# 2. Update v6 tools
wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_FINAL_AUTH_{ts}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

select_cols = "id_cita_dentalink,id_paciente_dentalink,nombre_paciente,fecha_turno,hora_turno,tipo,enviado_at"

# consultar
n = next(x for x in wf["nodes"] if x["name"] == "consultar_recordatorios_abiertos")
n["parameters"] = {
    "toolDescription": (
        "PRIMER paso obligatorio en Sub-Agent Confirmar/Cancelar. Consulta Supabase "
        "'recordatorios_enviados' filtrando por el celular del paciente. Devuelve "
        "array JSON con: id_cita_dentalink, id_paciente_dentalink, nombre_paciente, "
        "fecha_turno, hora_turno, tipo, enviado_at. Si devuelve >=1 filas, usalas "
        "directo como cita_ids. Si devuelve 0, fallback al flow legacy.\n\n"
        "PARAMETRO: `telefono` en formato PostgREST 'eq.<phone>'. "
        "EJEMPLO: para phone 5491161461034, pasar telefono='eq.5491161461034'."
    ),
    "method": "GET",
    "url": (f"{SB}/rest/v1/recordatorios_enviados?"
            f"apikey={SR}&"
            f"select={select_cols}&"
            "confirmado_at=is.null&"
            "cancelado_at=is.null&"
            "order=fecha_turno,hora_turno"),
    "authentication": "genericCredentialType",
    "genericAuthType": "httpHeaderAuth",
    "sendQuery": True,
    "specifyQuery": "keypair",
    "parametersQuery": {"values": [{"name": "telefono"}]},  # LLM rellena
    "optimizeResponse": True,
}
n["credentials"] = {"httpHeaderAuth": SB_CRED}

# marcar_confirmado
n = next(x for x in wf["nodes"] if x["name"] == "marcar_recordatorio_confirmado")
n["parameters"] = {
    "toolDescription": (
        "Marca fila en recordatorios_enviados como confirmada (confirmado_at=now()). "
        "Llamala DESPUES de confirmar_turno exitoso en Dentalink.\n\n"
        "PARAMETRO: `id_cita_dentalink` formato PostgREST 'eq.<id>'. "
        "EJEMPLO: para cita 8095, pasar id_cita_dentalink='eq.8095'."
    ),
    "method": "PATCH",
    "url": (f"{SB}/rest/v1/recordatorios_enviados?"
            f"apikey={SR}&"
            "confirmado_at=is.null"),
    "authentication": "genericCredentialType",
    "genericAuthType": "httpHeaderAuth",
    "sendQuery": True,
    "specifyQuery": "keypair",
    "parametersQuery": {"values": [{"name": "id_cita_dentalink"}]},
    "sendHeaders": True,
    "specifyHeaders": "keypair",
    "parametersHeaders": {"values": [
        {"name": "Content-Type", "value": "application/json"},
        {"name": "Prefer", "value": "return=minimal"},
    ]},
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": '={ "confirmado_at": "{{ $now.toISO() }}" }',
    "optimizeResponse": True,
}
n["credentials"] = {"httpHeaderAuth": SB_CRED}

# marcar_cancelado
n = next(x for x in wf["nodes"] if x["name"] == "marcar_recordatorio_cancelado")
n["parameters"] = {
    "toolDescription": (
        "Marca fila en recordatorios_enviados como cancelada (cancelado_at=now()). "
        "Llamala DESPUES de cancelar_turno exitoso en Dentalink.\n\n"
        "PARAMETRO: `id_cita_dentalink` formato PostgREST 'eq.<id>'. "
        "EJEMPLO: para cita 8095, pasar id_cita_dentalink='eq.8095'."
    ),
    "method": "PATCH",
    "url": (f"{SB}/rest/v1/recordatorios_enviados?"
            f"apikey={SR}&"
            "cancelado_at=is.null"),
    "authentication": "genericCredentialType",
    "genericAuthType": "httpHeaderAuth",
    "sendQuery": True,
    "specifyQuery": "keypair",
    "parametersQuery": {"values": [{"name": "id_cita_dentalink"}]},
    "sendHeaders": True,
    "specifyHeaders": "keypair",
    "parametersHeaders": {"values": [
        {"name": "Content-Type", "value": "application/json"},
        {"name": "Prefer", "value": "return=minimal"},
    ]},
    "sendBody": True,
    "specifyBody": "json",
    "jsonBody": '={ "cancelado_at": "{{ $now.toISO() }}" }',
    "optimizeResponse": True,
}
n["credentials"] = {"httpHeaderAuth": SB_CRED}

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
if r.status_code >= 400: print(r.text[:500]); sys.exit(1)

# Borrar cred apikey vieja
print(f"\nBorrando cred apikey vieja JT0D38dLlhoCEJGn ...")
r = requests.delete(f"{N8N}/api/v1/credentials/JT0D38dLlhoCEJGn", headers=H, timeout=30)
print(f"  status: {r.status_code}")

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_FINAL_AUTH_{ts}.json").write_text(json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup -> v6_POST_FINAL_AUTH_{ts}.json")
