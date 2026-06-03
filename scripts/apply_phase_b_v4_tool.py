"""
Phase B v4: tool nativa con URL inline placeholders (formato correcto, mismo
patron que ver_turnos_paciente).

Diferencia clave vs v3 (fallo): no usar sendQuery+queryParameters. Todo en la URL
con {phone} como placeholder.
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
        f"{API_BASE}{path}", method=method,
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


# Tool con URL completa inline (mismo patron que ver_turnos_paciente)
HIST_URL = (
    f"{SUPABASE_URL}/rest/v1/conversaciones"
    "?telefono=eq.{phone}"
    "&select=timestamp,rol,mensaje,fuente"
    "&order=timestamp.desc"
    "&limit=20"
)

HIST_TOOL = {
    "id": "obtener_historial_tool_v4",
    "name": "obtener_historial_paciente",
    "type": "@n8n/n8n-nodes-langchain.toolHttpRequest",
    "typeVersion": 1.1,
    "position": [13800, 1300],
    "parameters": {
        "toolDescription": (
            "Trae los ultimos 20 mensajes del paciente desde la base de conversaciones (Supabase). "
            "Incluye mensajes de TODOS los canales (paciente, bot, secretaria/doctora). "
            "USAR cuando: no tenes contexto en memoria, sospechas que el paciente ya hablo antes con vos "
            "o con la secretaria, queres saber que tratamiento tiene o que turnos pidio. "
            "Devuelve lista cronologica con: timestamp, rol (user/assistant/human/system), mensaje, fuente. "
            "CRITICO: lo que ves en el historial es CONTEXTO, no tu voz. Lo que dijo la secretaria/doctora NO sos vos. "
            "VOS siempre sos la asistente virtual de la Dra. Raquel - si el paciente esperaba respuesta de la "
            "secretaria/doctora, derivar con escalar_a_secretaria. NUNCA continuar una conversacion que era humana."
        ),
        "url": HIST_URL,
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "placeholderDefinitions": {
            "values": [
                {
                    "name": "phone",
                    "description": "telefono del paciente en formato 549XXXXXXXXXX (sin +), tal como viene en el webhook (`phone` del Edit Fields - Extraer Datos)",
                    "type": "string",
                }
            ]
        },
        "optimizeResponse": True,
    },
    "credentials": {"supabaseApi": CRED_SUPABASE},
}

SUB_AGENTS = ['Sub-Agent Confirmar', 'Sub-Agent Cancelar', 'Sub-Agent Agendar', 'Sub-Agent General']


def main():
    print("Pulling v6...")
    _, wf = http("GET", f"/workflows/{WID}")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    Path("workflows/history").mkdir(parents=True, exist_ok=True)
    Path(f"workflows/history/v6_PRE_PHASE_B_V4_{stamp}.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("  backup pre OK")

    existing_names = {n["name"] for n in wf["nodes"]}
    if "obtener_historial_paciente" not in existing_names:
        wf["nodes"].append(HIST_TOOL)
        print("  + tool obtener_historial_paciente")

    conns = wf.get("connections", {})
    if "obtener_historial_paciente" not in conns:
        conns["obtener_historial_paciente"] = {"ai_tool": [[]]}
    tool_branches = conns["obtener_historial_paciente"].get("ai_tool", [[]])
    if not tool_branches:
        tool_branches = [[]]
    for sa in SUB_AGENTS:
        if not any(c.get("node") == sa for c in tool_branches[0]):
            tool_branches[0].append({"node": sa, "type": "ai_tool", "index": 0})
            print(f"  connected to {sa}")
    conns["obtener_historial_paciente"]["ai_tool"] = tool_branches
    wf["connections"] = conns

    payload = strip_meta(dict(wf))
    if "--dry-run" in sys.argv:
        dry = f"workflows/history/v6_PHASE_B_V4_DRY_{stamp}.json"
        Path(dry).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  DRY -> {dry}")
        return

    print("PUT v4...")
    status, _ = http("PUT", f"/workflows/{WID}", payload)
    print(f"  status: {status}")


if __name__ == "__main__":
    main()
