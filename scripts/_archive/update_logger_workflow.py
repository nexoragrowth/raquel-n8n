"""
Reemplaza los nodos Supabase del Logger por nodos Postgres directos.
La cred Postgres `xwvjww5Odcxiy1K9` apunta al mismo Supabase (los datos
estan en la misma BD).

Cambios:
- `SB - Upsert Paciente` (Supabase op=upsert)  ->  Postgres SQL upsert con RETURNING id
- `SB - Insert Conversacion` (Supabase op=create)  ->  Postgres SQL insert
"""
import json
import sys
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


print("Pulling current Logger...")
_, wf = http("GET", f"/workflows/{WID}")

# Backup
Path("workflows/history").mkdir(parents=True, exist_ok=True)
import time
stamp = time.strftime("%Y%m%d_%H%M%S")
Path(f"workflows/history/logger_PRE_PG_REWRITE_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)

# Reemplazar SB - Upsert Paciente
for n in wf["nodes"]:
    if n["name"] == "SB - Upsert Paciente":
        n["type"] = "n8n-nodes-base.postgres"
        n["typeVersion"] = 2.5
        n["parameters"] = {
            "operation": "executeQuery",
            "query": (
                "INSERT INTO pacientes (telefono, nombre) "
                "VALUES ($1, COALESCE(NULLIF($2, ''), 'Paciente WhatsApp')) "
                "ON CONFLICT (telefono) DO UPDATE SET "
                "  nombre = COALESCE(NULLIF(EXCLUDED.nombre, 'Paciente WhatsApp'), pacientes.nombre), "
                "  updated_at = NOW() "
                "RETURNING id;"
            ),
            "options": {
                "queryReplacement": "={{ $json.telefono }},={{ $json.pushName || '' }}"
            },
        }
        n["credentials"] = {"postgres": CRED_POSTGRES}
        n["continueOnFail"] = True

    elif n["name"] == "SB - Insert Conversacion":
        n["type"] = "n8n-nodes-base.postgres"
        n["typeVersion"] = 2.5
        n["parameters"] = {
            "operation": "executeQuery",
            "query": (
                "INSERT INTO conversaciones (paciente_id, telefono, rol, mensaje, fuente, \"timestamp\", metadata) "
                "VALUES ($1::uuid, $2, $3, $4, $5, $6::timestamptz, $7::jsonb) "
                "RETURNING id;"
            ),
            "options": {
                "queryReplacement": (
                    "={{ $('SB - Upsert Paciente').item.json.id }},"
                    "={{ $('Parse mensajes').item.json.telefono }},"
                    "={{ $('Parse mensajes').item.json.rol }},"
                    "={{ $('Parse mensajes').item.json.mensaje }},"
                    "={{ $('Parse mensajes').item.json.fuente }},"
                    "={{ $('Parse mensajes').item.json.created_at }},"
                    "={{ JSON.stringify($('Parse mensajes').item.json.metadata) }}"
                )
            },
        }
        n["credentials"] = {"postgres": CRED_POSTGRES}
        n["continueOnFail"] = True

payload = strip_meta(dict(wf))
print("PUT update...")
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"  status: {status}")

# Save post
_, post_wf = http("GET", f"/workflows/{WID}")
Path("workflows/current/logger_conversaciones.json").write_text(
    json.dumps(post_wf, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("  saved post snapshot.")
print("\nWorkflow ya esta activo - el proximo cron va a usar la nueva config.")
