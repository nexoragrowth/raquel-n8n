"""
Cambia la estrategia del Logger: en vez de last_synced_chat_id (que falla
si hay gaps en los IDs), usa last_synced_timestamp. Procesa cronologicamente.
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


GET_TS_CODE = """// Lee el ultimo timestamp sincronizado (created_at).
// Reset: si static.reset === true, vuelve a 2020-01-01.
const sd = $getWorkflowStaticData('global');
if (sd.reset) {
  sd.last_synced_ts = '2020-01-01T00:00:00Z';
  sd.reset = false;
}
const last_ts = sd.last_synced_ts || '2020-01-01T00:00:00Z';
return [{ json: { last_ts } }];
"""

SYNC_CODE = (
    "// Sync via Supabase REST API.\n"
    "const SUPABASE_URL = " + json.dumps(SUPABASE_URL) + ";\n"
    "const SUPABASE_KEY = " + json.dumps(SUPABASE_KEY) + ";\n"
    "const items = $input.all();\n"
    "let synced = 0, errors = 0, maxTs = '';\n"
    "const errSamples = [];\n"
    "\n"
    "for (const item of items) {\n"
    "  const d = item.json;\n"
    "  if (!d.telefono) continue;\n"
    "  try {\n"
    "    // Upsert paciente\n"
    "    const pacRes = await $helpers.httpRequest({\n"
    "      method: 'POST',\n"
    "      url: SUPABASE_URL + '/rest/v1/pacientes?on_conflict=telefono',\n"
    "      headers: {\n"
    "        apikey: SUPABASE_KEY,\n"
    "        Authorization: 'Bearer ' + SUPABASE_KEY,\n"
    "        'Content-Type': 'application/json',\n"
    "        Prefer: 'resolution=merge-duplicates,return=representation',\n"
    "      },\n"
    "      body: { telefono: d.telefono, nombre: d.pushName || 'Paciente WhatsApp' },\n"
    "      json: true,\n"
    "    });\n"
    "    const pacienteId = Array.isArray(pacRes) ? pacRes[0]?.id : pacRes?.id;\n"
    "    if (!pacienteId) { errors++; if (errSamples.length < 3) errSamples.push({phase: 'no_id', res: pacRes}); continue; }\n"
    "    \n"
    "    await $helpers.httpRequest({\n"
    "      method: 'POST',\n"
    "      url: SUPABASE_URL + '/rest/v1/conversaciones',\n"
    "      headers: {\n"
    "        apikey: SUPABASE_KEY,\n"
    "        Authorization: 'Bearer ' + SUPABASE_KEY,\n"
    "        'Content-Type': 'application/json',\n"
    "      },\n"
    "      body: {\n"
    "        paciente_id: pacienteId,\n"
    "        telefono: d.telefono,\n"
    "        rol: d.rol,\n"
    "        mensaje: d.mensaje,\n"
    "        fuente: d.fuente,\n"
    "        timestamp: d.created_at,\n"
    "        metadata: d.metadata || {},\n"
    "      },\n"
    "      json: true,\n"
    "    });\n"
    "    synced++;\n"
    "    if (d.created_at > maxTs) maxTs = d.created_at;\n"
    "  } catch (e) {\n"
    "    errors++;\n"
    "    if (errSamples.length < 3) errSamples.push({ phase: 'request', error: String(e), tel: d.telefono });\n"
    "  }\n"
    "}\n"
    "\n"
    "if (maxTs) {\n"
    "  const sd = $getWorkflowStaticData('global');\n"
    "  if (!sd.last_synced_ts || maxTs > sd.last_synced_ts) sd.last_synced_ts = maxTs;\n"
    "}\n"
    "\n"
    "return [{ json: { input: items.length, synced, errors, max_ts: maxTs, err_samples: errSamples } }];\n"
)


print("Pulling workflow...")
_, wf = http("GET", f"/workflows/{WID}")

stamp = time.strftime("%Y%m%d_%H%M%S")
Path("workflows/history").mkdir(parents=True, exist_ok=True)
Path(f"workflows/history/logger_PRE_TS_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)

# Update nodos
for n in wf["nodes"]:
    if n["name"] == "Get last_synced":
        n["parameters"]["jsCode"] = GET_TS_CODE
    elif n["name"] == "PG - SELECT nuevos":
        n["parameters"]["query"] = (
            "SELECT id, session_id, message::text AS message, created_at "
            "FROM n8n_chat_histories "
            "WHERE created_at > $1::timestamptz "
            "ORDER BY created_at ASC LIMIT 200"
        )
        n["parameters"]["options"]["queryReplacement"] = "={{ $json.last_ts }}"
    elif n["name"] == "Sync to Supabase":
        n["parameters"]["jsCode"] = SYNC_CODE

payload = strip_meta(dict(wf))
print("PUT timestamp-based logger...")
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"  status: {status}")
print("done.")
