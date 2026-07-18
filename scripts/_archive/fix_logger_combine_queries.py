"""
Reemplaza los 2 nodos Postgres del Logger por UNO solo con CTE.
Asi se procesa correctamente per-item y queda atomico.
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
Path(f"workflows/history/logger_PRE_CTE_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)

# Quitar SB - Insert Conversacion (queda merged en el upsert via CTE)
wf["nodes"] = [n for n in wf["nodes"] if n["name"] != "SB - Insert Conversacion"]

# Reemplazar SB - Upsert Paciente por nodo combinado
for n in wf["nodes"]:
    if n["name"] == "SB - Upsert Paciente":
        n["name"] = "PG - Sync Conversacion"
        n["type"] = "n8n-nodes-base.postgres"
        n["typeVersion"] = 2.5
        n["parameters"] = {
            "operation": "executeQuery",
            "query": (
                "WITH upsert_pac AS ("
                "  INSERT INTO pacientes (telefono, nombre) "
                "  VALUES ($1, COALESCE(NULLIF($2, ''), 'Paciente WhatsApp')) "
                "  ON CONFLICT (telefono) DO UPDATE SET "
                "    nombre = COALESCE(NULLIF(EXCLUDED.nombre, 'Paciente WhatsApp'), pacientes.nombre), "
                "    updated_at = NOW() "
                "  RETURNING id"
                ") "
                "INSERT INTO conversaciones (paciente_id, telefono, rol, mensaje, fuente, \"timestamp\", metadata) "
                "SELECT id, $1, $3, $4, $5, $6::timestamptz, $7::jsonb FROM upsert_pac "
                "RETURNING id, paciente_id;"
            ),
            "options": {
                "queryReplacement": (
                    "={{ $json.telefono }},"
                    "={{ $json.pushName || '' }},"
                    "={{ $json.rol }},"
                    "={{ $json.mensaje }},"
                    "={{ $json.fuente }},"
                    "={{ $json.created_at }},"
                    "={{ JSON.stringify($json.metadata) }}"
                )
            },
        }
        n["credentials"] = {"postgres": CRED_POSTGRES}
        n["continueOnFail"] = True

# Reconectar: Parse mensajes -> PG - Sync Conversacion -> Update last_synced
new_conns = {}
for src, c in wf.get("connections", {}).items():
    new_conns[src] = c
# Reescribir las conexiones afectadas
new_conns["Parse mensajes"] = {"main": [[{"node": "PG - Sync Conversacion", "type": "main", "index": 0}]]}
new_conns["PG - Sync Conversacion"] = {"main": [[{"node": "Update last_synced", "type": "main", "index": 0}]]}
# Quitar conexiones que apuntaban a SB - Insert Conversacion (ya no existe)
new_conns.pop("SB - Upsert Paciente", None)
new_conns.pop("SB - Insert Conversacion", None)
wf["connections"] = new_conns

payload = strip_meta(dict(wf))
print("PUT update (CTE)...")
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"  status: {status}")

_, post_wf = http("GET", f"/workflows/{WID}")
Path("workflows/current/logger_conversaciones.json").write_text(
    json.dumps(post_wf, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("  done.")
