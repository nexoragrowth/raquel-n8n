"""
Fix definitivo: reemplaza el unico nodo PG con CTE+queryReplacement por
2 nodos Postgres separados que usan op `insert` (sin parsing CSV problematico).

1. PG - Upsert Paciente: operation=executeQuery con 2 params simples (telefono, nombre).
   Devuelve paciente_id.
2. PG - Insert Conversacion: operation=insert con columnas mapeadas (n8n maneja
   internamente el quoting y escaping).
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
CRED_POSTGRES = {"id": "xwvjww5Odcxiy1K9", "name": "Postgres account"}

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


print("Pulling workflow...")
_, wf = http("GET", f"/workflows/{WID}")

stamp = time.strftime("%Y%m%d_%H%M%S")
Path("workflows/history").mkdir(parents=True, exist_ok=True)
Path(f"workflows/history/logger_PRE_SPLIT_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)

# Sacar el nodo PG - Sync Conversacion (que tenia el CTE roto)
wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "PG - Sync Conversacion"]

# Agregar 2 nodos nuevos
upsert_node = {
    "id": "pg_upsert",
    "name": "PG - Upsert Paciente",
    "type": "n8n-nodes-base.postgres",
    "typeVersion": 2.5,
    "position": [1140, 300],
    "parameters": {
        "operation": "executeQuery",
        "query": (
            "INSERT INTO pacientes (telefono, nombre) "
            "VALUES ($1, COALESCE(NULLIF($2, ''), 'Paciente WhatsApp')) "
            "ON CONFLICT (telefono) DO UPDATE SET "
            "  nombre = COALESCE(NULLIF(EXCLUDED.nombre, 'Paciente WhatsApp'), pacientes.nombre), "
            "  updated_at = NOW() "
            "RETURNING id, telefono;"
        ),
        "options": {
            "queryReplacement": "={{ $json.telefono }},={{ $json.pushName || '' }}"
        },
    },
    "credentials": {"postgres": CRED_POSTGRES},
    "continueOnFail": True,
}

insert_node = {
    "id": "pg_insert_conv",
    "name": "PG - Insert Conversacion",
    "type": "n8n-nodes-base.postgres",
    "typeVersion": 2.5,
    "position": [1380, 300],
    "parameters": {
        "operation": "insert",
        "schema": {"__rl": True, "mode": "list", "value": "public"},
        "table": {"__rl": True, "mode": "list", "value": "conversaciones"},
        "columns": {
            "mappingMode": "defineBelow",
            "value": {
                "paciente_id": "={{ $json.id }}",
                "telefono": "={{ $('Parse mensajes').item.json.telefono }}",
                "rol": "={{ $('Parse mensajes').item.json.rol }}",
                "mensaje": "={{ $('Parse mensajes').item.json.mensaje }}",
                "fuente": "={{ $('Parse mensajes').item.json.fuente }}",
                "timestamp": "={{ $('Parse mensajes').item.json.created_at }}",
                "metadata": "={{ JSON.stringify($('Parse mensajes').item.json.metadata) }}",
            },
        },
        "options": {},
    },
    "credentials": {"postgres": CRED_POSTGRES},
    "continueOnFail": True,
}

wf["nodes"].append(upsert_node)
wf["nodes"].append(insert_node)

# Conexiones: Parse -> PG Upsert -> PG Insert -> Update last_synced
new_conns = {}
for src, c in wf.get("connections", {}).items():
    if src in ("PG - Sync Conversacion",):
        continue
    new_conns[src] = c
new_conns["Parse mensajes"] = {"main": [[{"node": "PG - Upsert Paciente", "type": "main", "index": 0}]]}
new_conns["PG - Upsert Paciente"] = {"main": [[{"node": "PG - Insert Conversacion", "type": "main", "index": 0}]]}
new_conns["PG - Insert Conversacion"] = {"main": [[{"node": "Update last_synced", "type": "main", "index": 0}]]}
wf["connections"] = new_conns

payload = strip_meta(dict(wf))
print("PUT split queries...")
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"  status: {status}")

_, post_wf = http("GET", f"/workflows/{WID}")
Path("workflows/current/logger_conversaciones.json").write_text(
    json.dumps(post_wf, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("done.")
