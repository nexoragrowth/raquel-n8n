"""
Modifica 'Fecha Manana' del cron Recordatorios para aceptar un override
de fecha_target desde el body del webhook manual. Cron normal sin cambios.

Si el webhook trae { fecha_target: "YYYY-MM-DD" }, usa esa fecha en lugar
de la calculada por addBusinessDays(now, 2).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require, env

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF_ID = env("N8N_WORKFLOW_RECORDATORIOS_ID", "7RqTApkvVavRmq3R")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

wf = requests.get(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"recordatorios_PRE_OVERRIDE_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> recordatorios_PRE_OVERRIDE_{ts}.json")

fm = next(n for n in wf["nodes"] if n["name"] == "Fecha Mañana")
orig = fm["parameters"]["jsCode"]

if "manual_override" in orig:
    print("ya tiene override — skip")
    sys.exit(0)

# Insertar al PRINCIPIO un bloque que chequea el webhook body y short-circuits
override_block = '''// === Override desde Webhook Manual Recordatorios ===
let whBody = null;
try {
  const whItems = $('Webhook Manual Recordatorios').all();
  if (whItems && whItems.length > 0) {
    whBody = whItems[0].json?.body || whItems[0].json;
  }
} catch (e) {
  // El nodo Webhook Manual no se ejecuto en esta corrida (vino del cron)
}
if (whBody && whBody.fecha_target) {
  return [{ json: { fecha_target: whBody.fecha_target, tipo_recordatorio: "manual_override" } }];
}

'''

new_js = override_block + orig
fm["parameters"]["jsCode"] = new_js
print(f"jsCode: {len(orig)} -> {len(new_js)} chars")

allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
payload = {"name": wf["name"], "nodes": wf["nodes"],
           "connections": wf["connections"], "settings": settings}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]

r = requests.put(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
print(f"PUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:500])
    sys.exit(1)

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H, timeout=30).json()
(hist / f"recordatorios_POST_OVERRIDE_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> recordatorios_POST_OVERRIDE_{ts}.json")
print(f"active: {wf_post.get('active')}")
