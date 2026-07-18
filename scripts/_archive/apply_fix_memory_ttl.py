"""
Extender TTL de memoria stale de 3 dias a 7 dias.

El nodo `Handle Stale Session` decide si limpiar memoria vieja con
`isStale = diffDays > 3`. Lo paso a `> 7`. Asi los pacientes pueden
responder a recordatorios hasta 1 semana despues sin perder contexto.

Nota: los mensajes con source=reminder_note, wa_outbound o human_takeover
NO se borran nunca (los preserva el Clear Old Memory aparte).
"""
import json
import sys
import time
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

API_KEY = require('N8N_API_KEY')
WF_ID = require('N8N_WORKFLOW_V6_ID')
API_BASE = f"{require('N8N_BASE_URL')}/api/v1"
DRY_RUN = "--dry-run" in sys.argv

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}

OLD = "isStale = diffDays > 3;"
NEW = "isStale = diffDays > 7;"


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


def main():
    print("Pulling current v6...")
    _, wf = http("GET", f"/workflows/{WF_ID}")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    Path("workflows/history").mkdir(parents=True, exist_ok=True)
    pre = f"workflows/history/v6_PRE_MEMORY_TTL_{stamp}.json"
    Path(pre).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  backup: {pre}")

    node = next((n for n in wf["nodes"] if n["name"] == "Handle Stale Session"), None)
    if not node:
        sys.exit("ERROR: Handle Stale Session no existe")
    code = node["parameters"].get("jsCode", "")
    if NEW in code and OLD not in code:
        print("  ya esta en 7d, nada que hacer.")
        return
    if OLD not in code:
        sys.exit(f"ERROR: no encuentro '{OLD}' en el codigo")
    new_code = code.replace(OLD, NEW)
    node["parameters"]["jsCode"] = new_code

    print(f"  Diff: '{OLD}' -> '{NEW}'")

    if DRY_RUN:
        dry = f"workflows/history/v6_MEMORY_TTL_DRY_{stamp}.json"
        Path(dry).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  DRY -> {dry}")
        return

    payload = strip_meta(dict(wf))
    print("Applying PUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  PUT: {status}")
    _, post_wf = http("GET", f"/workflows/{WF_ID}")
    post = f"workflows/history/v6_POST_MEMORY_TTL_{stamp}.json"
    Path(post).write_text(json.dumps(post_wf, ensure_ascii=False, indent=2), encoding="utf-8")
    post_node = next((n for n in post_wf["nodes"] if n["name"] == "Handle Stale Session"), None)
    if NEW not in post_node["parameters"]["jsCode"]:
        sys.exit("ERROR post: cambio no quedo")
    print("  OK: TTL extendido a 7d.")


if __name__ == "__main__":
    main()
