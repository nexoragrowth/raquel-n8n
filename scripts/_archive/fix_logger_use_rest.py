"""
Approach final: reemplaza los 2 nodos Postgres por UN solo Code node que
usa $helpers.httpRequest para escribir via Supabase REST API. Mas limpio,
sin problemas de parsing CSV.

La service_role key va inline en el Code (los workflows estan protegidos
por la n8n API key).
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
WID = "xsXeHp7WLXnFQc3o"
SUPABASE_URL = require('SUPABASE_URL')
SUPABASE_KEY = require('SUPABASE_SERVICE_ROLE_KEY')

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


# Code que hace upsert+insert via REST per item
SYNC_CODE = (
    "// Sincroniza items a Supabase via REST API.\n"
    "const SUPABASE_URL = " + json.dumps(SUPABASE_URL) + ";\n"
    "const SUPABASE_KEY = " + json.dumps(SUPABASE_KEY) + ";\n"
    "const items = $input.all();\n"
    "const results = [];\n"
    "let synced = 0, errors = 0, maxChatId = 0;\n"
    "\n"
    "for (const item of items) {\n"
    "  const d = item.json;\n"
    "  if (!d.telefono) continue;\n"
    "  try {\n"
    "    // 1. Upsert paciente\n"
    "    const pacUrl = SUPABASE_URL + '/rest/v1/pacientes?on_conflict=telefono';\n"
    "    const pacBody = {\n"
    "      telefono: d.telefono,\n"
    "      nombre: d.pushName || 'Paciente WhatsApp',\n"
    "    };\n"
    "    const pacRes = await $helpers.httpRequest({\n"
    "      method: 'POST', url: pacUrl,\n"
    "      headers: {\n"
    "        apikey: SUPABASE_KEY,\n"
    "        Authorization: 'Bearer ' + SUPABASE_KEY,\n"
    "        'Content-Type': 'application/json',\n"
    "        Prefer: 'resolution=merge-duplicates,return=representation',\n"
    "      },\n"
    "      body: pacBody, json: true,\n"
    "    });\n"
    "    const pacienteId = Array.isArray(pacRes) ? pacRes[0]?.id : pacRes?.id;\n"
    "    if (!pacienteId) { errors++; continue; }\n"
    "    \n"
    "    // 2. Insert conversacion\n"
    "    const convBody = {\n"
    "      paciente_id: pacienteId,\n"
    "      telefono: d.telefono,\n"
    "      rol: d.rol,\n"
    "      mensaje: d.mensaje,\n"
    "      fuente: d.fuente,\n"
    "      timestamp: d.created_at,\n"
    "      metadata: d.metadata || {},\n"
    "    };\n"
    "    await $helpers.httpRequest({\n"
    "      method: 'POST', url: SUPABASE_URL + '/rest/v1/conversaciones',\n"
    "      headers: {\n"
    "        apikey: SUPABASE_KEY,\n"
    "        Authorization: 'Bearer ' + SUPABASE_KEY,\n"
    "        'Content-Type': 'application/json',\n"
    "      },\n"
    "      body: convBody, json: true,\n"
    "    });\n"
    "    synced++;\n"
    "    if ((d.chat_history_id || 0) > maxChatId) maxChatId = d.chat_history_id;\n"
    "  } catch (e) {\n"
    "    errors++;\n"
    "    results.push({ json: { error: String(e), item_phone: d.telefono } });\n"
    "  }\n"
    "}\n"
    "\n"
    "// Update staticData with last_synced\n"
    "if (maxChatId > 0) {\n"
    "  const sd = $getWorkflowStaticData('global');\n"
    "  if ((sd.last_synced_chat_id || 0) < maxChatId) {\n"
    "    sd.last_synced_chat_id = maxChatId;\n"
    "  }\n"
    "}\n"
    "\n"
    "return [{ json: { synced, errors, max_chat_id: maxChatId, total_input: items.length } }];\n"
)


print("Pulling workflow...")
_, wf = http("GET", f"/workflows/{WID}")
stamp = time.strftime("%Y%m%d_%H%M%S")
Path("workflows/history").mkdir(parents=True, exist_ok=True)
Path(f"workflows/history/logger_PRE_REST_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)

# Quitar nodos viejos
wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in (
    "PG - Upsert Paciente", "PG - Insert Conversacion", "PG - Sync Conversacion",
    "Update last_synced",
)]

# Agregar nodo nuevo combinado
sync_node = {
    "id": "code_sync",
    "name": "Sync to Supabase",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [1140, 300],
    "parameters": {"jsCode": SYNC_CODE},
}
wf["nodes"].append(sync_node)

# Conexiones
new_conns = {}
for src, c in wf.get("connections", {}).items():
    if src in ("PG - Upsert Paciente", "PG - Insert Conversacion", "PG - Sync Conversacion", "Update last_synced"):
        continue
    new_conns[src] = c
new_conns["Parse mensajes"] = {"main": [[{"node": "Sync to Supabase", "type": "main", "index": 0}]]}
wf["connections"] = new_conns

payload = strip_meta(dict(wf))
print("PUT with single Code node using REST...")
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"  status: {status}")
print("done.")
