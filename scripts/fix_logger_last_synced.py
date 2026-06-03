"""
Fix: el Code 'Update last_synced' lee de $input que viene del Postgres node,
el cual NO propaga chat_history_id. Cambio para leer de $('Parse mensajes').all()
directamente, que es donde esta el dato.
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


NEW_UPDATE_CODE = """// Lee chat_history_ids desde Parse mensajes (no desde el Postgres node que no los propaga).
const rows = $('Parse mensajes').all();
if (rows.length === 0) return [{ json: { skipped: true } }];
let max = 0;
for (const r of rows) {
  const id = r.json.chat_history_id || 0;
  if (id > max) max = id;
}
const sd = $getWorkflowStaticData('global');
const prev = sd.last_synced_chat_id || 0;
if (max > prev) {
  sd.last_synced_chat_id = max;
}
return [{ json: { previous: prev, new: max, total_synced: rows.length } }];
"""


print("Pulling workflow...")
_, wf = http("GET", f"/workflows/{WID}")

stamp = time.strftime("%Y%m%d_%H%M%S")
Path("workflows/history").mkdir(parents=True, exist_ok=True)
Path(f"workflows/history/logger_PRE_FIX_LASTSYNCED_{stamp}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
)

for n in wf["nodes"]:
    if n["name"] == "Update last_synced":
        n["parameters"]["jsCode"] = NEW_UPDATE_CODE
        break

payload = strip_meta(dict(wf))
print("PUT update...")
status, _ = http("PUT", f"/workflows/{WID}", payload)
print(f"  status: {status}")
print("Listo.")
