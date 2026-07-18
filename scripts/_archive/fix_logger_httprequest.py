"""
Reemplaza el Code 'Sync to Supabase' por DOS nodos HTTP Request nativos.
Usan auth predefinida (`supabaseApi` cred ya existente) - n8n setea el
apikey/Authorization automaticamente.

Sin $helpers, sin Code complejo, todo nodos nativos.
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


# Code que actualiza staticData al final (sin HTTP, solo update)
UPDATE_STATIC_CODE = """// Avanza last_synced_ts con el max(created_at) de los items procesados.
const rows = $('Parse mensajes').all();
let maxTs = '';
for (const r of rows) {
  const ts = r.json.created_at;
  if (ts && ts > maxTs) maxTs = ts;
}
if (maxTs) {
  const sd = $getWorkflowStaticData('global');
  if (!sd.last_synced_ts || maxTs > sd.last_synced_ts) sd.last_synced_ts = maxTs;
}
return [{ json: { synced_count: rows.length, max_ts: maxTs } }];
"""

print("Pulling workflow...")
_, wf = http("GET", f"/workflows/{WID}")

stamp = time.strftime("%Y%m%d_%H%M%S")
Path("workflows/history").mkdir(parents=True, exist_ok=True)
Path(f"workflows/history/logger_PRE_HTTPREQ_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)

# Quitar nodos viejos
wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in ("Sync to Supabase",)]

# Nodo 1: HTTP Upsert Paciente
upsert_pac = {
    "id": "http_upsert",
    "name": "HTTP - Upsert Paciente",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [1140, 300],
    "parameters": {
        "method": "POST",
        "url": f"{SUPABASE_URL}/rest/v1/pacientes",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "sendQuery": True,
        "queryParameters": {
            "parameters": [
                {"name": "on_conflict", "value": "telefono"},
            ]
        },
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [
                {"name": "Prefer", "value": "resolution=merge-duplicates,return=representation"},
                {"name": "Content-Type", "value": "application/json"},
            ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={\n  "telefono": "{{ $json.telefono }}",\n  "nombre": "{{ ($json.pushName || \'Paciente WhatsApp\').replace(/"/g, \'\\\\"\') }}"\n}',
        "options": {"response": {"response": {"responseFormat": "json"}}},
    },
    "credentials": {"supabaseApi": CRED_SUPABASE},
    "continueOnFail": True,
}

# Nodo 2: HTTP Insert Conversacion
insert_conv = {
    "id": "http_insert",
    "name": "HTTP - Insert Conversacion",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [1380, 300],
    "parameters": {
        "method": "POST",
        "url": f"{SUPABASE_URL}/rest/v1/conversaciones",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "supabaseApi",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [
                {"name": "Content-Type", "value": "application/json"},
                {"name": "Prefer", "value": "return=minimal"},
            ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": (
            '={\n'
            '  "paciente_id": "{{ $json.id || ($json[0] && $json[0].id) }}",\n'
            '  "telefono": "{{ $(\'Parse mensajes\').item.json.telefono }}",\n'
            '  "rol": "{{ $(\'Parse mensajes\').item.json.rol }}",\n'
            '  "mensaje": {{ JSON.stringify($(\'Parse mensajes\').item.json.mensaje) }},\n'
            '  "fuente": "{{ $(\'Parse mensajes\').item.json.fuente }}",\n'
            '  "timestamp": "{{ $(\'Parse mensajes\').item.json.created_at }}",\n'
            '  "metadata": {{ JSON.stringify($(\'Parse mensajes\').item.json.metadata) }}\n'
            '}'
        ),
        "options": {},
    },
    "credentials": {"supabaseApi": CRED_SUPABASE},
    "continueOnFail": True,
}

# Nodo 3: Code update staticData
update_static = {
    "id": "code_upd",
    "name": "Update last_synced",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [1620, 300],
    "parameters": {"jsCode": UPDATE_STATIC_CODE},
}

wf["nodes"].extend([upsert_pac, insert_conv, update_static])

# Conexiones
new_conns = {}
for src, c in wf.get("connections", {}).items():
    if src in ("Sync to Supabase",):
        continue
    new_conns[src] = c
new_conns["Parse mensajes"] = {"main": [[{"node": "HTTP - Upsert Paciente", "type": "main", "index": 0}]]}
new_conns["HTTP - Upsert Paciente"] = {"main": [[{"node": "HTTP - Insert Conversacion", "type": "main", "index": 0}]]}
new_conns["HTTP - Insert Conversacion"] = {"main": [[{"node": "Update last_synced", "type": "main", "index": 0}]]}
wf["connections"] = new_conns

# Active a true
print("PUT with HTTP nodes...")
payload = strip_meta(dict(wf))
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"  status: {status}")

# Reactivar workflow (estaba en pausa)
print("Activating workflow...")
import urllib.error
try:
    req = urllib.request.Request(f"{API_BASE}/workflows/{WID}/activate", method="POST",
                                  headers={"X-N8N-API-KEY": API_KEY})
    with urllib.request.urlopen(req, timeout=20) as r:
        print(f"  activate: {r.status}")
except urllib.error.HTTPError as e:
    print(f"  activate err: {e.code}")

print("done.")
