"""
Rollback: restaura el cron de Recordatorios desde el ultimo backup PRE_APPLY.
Uso: python scripts/rollback_recordatorios.py [backup_filename]

Sin argumento: usa el ultimo recordatorios_PRE_APPLY_*.json
Con argumento: usa el archivo especificado en workflows/history/
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require, env

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF_ID = env("N8N_WORKFLOW_RECORDATORIOS_ID", "7RqTApkvVavRmq3R")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist_dir = REPO / "workflows" / "history"

if len(sys.argv) > 1:
    bak_path = hist_dir / sys.argv[1]
else:
    candidates = sorted(hist_dir.glob("recordatorios_PRE_APPLY_*.json"))
    if not candidates:
        candidates = sorted(hist_dir.glob("recordatorios_PRE_INSERT_TABLA_*.json"))
    if not candidates:
        print("No backups encontrados (recordatorios_PRE_*)")
        sys.exit(1)
    bak_path = candidates[-1]

print(f"Restaurando desde: {bak_path.relative_to(REPO)}")
wf = json.loads(bak_path.read_text(encoding="utf-8"))

allowed = {"saveExecutionProgress", "saveManualExecutions",
           "saveDataErrorExecution", "saveDataSuccessExecution",
           "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}

payload = {
    "name": wf["name"],
    "nodes": wf["nodes"],
    "connections": wf["connections"],
    "settings": settings,
}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]

print(f"PUT /workflows/{WF_ID} ...")
r = requests.put(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
if r.status_code >= 400:
    print(f"!! HTTP {r.status_code}: {r.text[:500]}")
    sys.exit(1)
print(f"ok ({r.status_code}). Rollback completo.")
