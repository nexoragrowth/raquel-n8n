"""
Phase B v3: hidratacion como TOOL nativa del Sub-Agent, NO insertando nodos
al flow principal.

Cambios respecto a v1/v2 (que rompieron el flow):
- Cero modificaciones al flow del v6 entre nodos.
- Solo agrega 1 tool nueva (`obtener_historial_paciente`) y la conecta como
  ai_tool a Sub-Agent Confirmar, Cancelar, Agendar, General.
- El LLM decide cuando llamarla (cuando no tiene contexto en memoria).

Esto es CERO RIESGO al flow del v6 - mismo patron que ver_turnos_paciente.
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
SUPABASE_URL = require('SUPABASE_URL')
CRED_SUPABASE = {"id": "Thn3jgEbbxPFD7d9", "name": "Supabase account"}

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}


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


# Tool definition (igual estructura que ver_turnos_paciente pero apunta a Supabase REST)
HIST_TOOL = {
    "id": "obtener_historial_tool",
    "name": "obtener_historial_paciente",
    "type": "@n8n/n8n-nodes-langchain.toolHttpRequest",
    "typeVersion": 1.1,
    "position": [13800, 1300],
    "parameters": {
        "toolDescription": (
            "Trae los ultimos 20 mensajes del paciente desde Supabase (TODOS los canales: bot, paciente, "
            "secretaria/doctora). USAR cuando: (1) no tenes contexto en la memoria reciente, "
            "(2) sospechas que el paciente ya hablo antes (con vos o con la secretaria), "
            "(3) querer saber que tipo de tratamiento tiene o que turnos pidio antes. "
            "Parametro `phone`: el telefono del paciente (sin +, formato 549XXXXXXXXXX como viene en el webhook). "
            "Devuelve lista cronologica de mensajes con rol (user=paciente, assistant=bot, human=secretaria/doctora, system=recordatorio automatico). "
            "IMPORTANTE: lo que ves en el historial es CONTEXTO, no tu voz. Lo que dijo la secretaria o la doctora NO sos vos. "
            "VOS sos siempre la asistente virtual de la Dra. Raquel. NUNCA continues una conversacion que era de la secretaria - "
            "responde con tu identidad y derivar si el paciente espera una respuesta humana."
        ),
        "url": f"{SUPABASE_URL}/rest/v1/conversaciones",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "sendQuery": True,
        "specifyQuery": "keypair",
        "parametersQuery": {
            "values": [
                {"name": "telefono", "valueProvider": "modelRequired", "value": "=eq.{phone}"},
                {"name": "select", "valueProvider": "fieldValue", "value": "timestamp,rol,mensaje,fuente"},
                {"name": "order", "valueProvider": "fieldValue", "value": "timestamp.desc"},
                {"name": "limit", "valueProvider": "fieldValue", "value": "20"},
            ]
        },
        "placeholderDefinitions": {
            "values": [
                {
                    "name": "phone",
                    "description": "telefono del paciente (formato 549XXXXXXXXXX sin +)",
                    "type": "string",
                }
            ]
        },
        "optimizeResponse": True,
    },
    "credentials": {"supabaseApi": CRED_SUPABASE},
}

# Sub-agents que reciben la tool
SUB_AGENTS = ['Sub-Agent Confirmar', 'Sub-Agent Cancelar', 'Sub-Agent Agendar', 'Sub-Agent General']


def main():
    print("Pulling v6...")
    _, wf = http("GET", f"/workflows/{WID}")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    Path("workflows/history").mkdir(parents=True, exist_ok=True)
    Path(f"workflows/history/v6_PRE_PHASE_B_V3_{stamp}.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  backup pre OK")

    # Agregar la tool si no existe
    existing_names = {n["name"] for n in wf["nodes"]}
    if "obtener_historial_paciente" not in existing_names:
        wf["nodes"].append(HIST_TOOL)
        print("  + tool obtener_historial_paciente")
    else:
        print("  tool ya existe, skip add")

    # Conectar como ai_tool a los sub-agents
    conns = wf.get("connections", {})
    if "obtener_historial_paciente" not in conns:
        conns["obtener_historial_paciente"] = {"ai_tool": [[]]}

    tool_branches = conns["obtener_historial_paciente"].get("ai_tool", [[]])
    if not tool_branches:
        tool_branches = [[]]

    for sa in SUB_AGENTS:
        existing = any(c.get("node") == sa for c in tool_branches[0])
        if not existing:
            tool_branches[0].append({"node": sa, "type": "ai_tool", "index": 0})
            print(f"  connected to {sa}")

    conns["obtener_historial_paciente"]["ai_tool"] = tool_branches
    wf["connections"] = conns

    payload = strip_meta(dict(wf))
    if "--dry-run" in sys.argv:
        dry = f"workflows/history/v6_PHASE_B_V3_DRY_{stamp}.json"
        Path(dry).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  DRY -> {dry}")
        return

    print("PUT...")
    status, _ = http("PUT", f"/workflows/{WID}", payload)
    print(f"  status: {status}")
    print("done.")


if __name__ == "__main__":
    main()
