"""
Fix: Dentalink no permite filtrar por id_paciente en query string.
- Revertir GET Citas por fecha al query original (solo fecha + id_estado.neq:1)
- Agregar al IF 'Solo citas activas' una condicion adicional que filtra
  por id_paciente cuando $('Fecha Manana').json.id_paciente_filter no esta vacio
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
WF = env("N8N_WORKFLOW_RECORDATORIOS_ID", "7RqTApkvVavRmq3R")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"recordatorios_PRE_FIXFILTER_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> recordatorios_PRE_FIXFILTER_{ts}.json")

# 1) GET Citas por fecha — query original
gc = next(n for n in wf["nodes"] if n["name"] == "GET Citas por fecha")
qp = gc["parameters"]["queryParameters"]["parameters"]
q_param = next(p for p in qp if p["name"] == "q")
old_q = q_param["value"]
new_q = '={"fecha":{"eq":"{{ $json.fecha_target }}"},"id_estado":{"neq":1}}'
q_param["value"] = new_q
print(f"\nQuery revertido:")
print(f"  old: {old_q}")
print(f"  new: {new_q}")

# 2) IF Solo citas activas — agregar condition de filter
ifn = next(n for n in wf["nodes"] if n["name"] == "Solo citas activas")
conds = ifn["parameters"]["conditions"]["conditions"]

# Limpiar previas con id_paciente_filter (idempotencia)
conds = [c for c in conds if "id_paciente_filter" not in str(c)]

# Agregar nueva condicion: id_paciente_filter vacio OR id_paciente in filter
# n8n IF expression: leftValue es expresion booleana, rightValue true
new_cond = {
    "id": "condition-3-paciente-filter",
    "leftValue": ("={{ ($('Fecha Mañana').first().json.id_paciente_filter || []).length === 0 "
                  "|| ($('Fecha Mañana').first().json.id_paciente_filter || []).includes($json.id_paciente) }}"),
    "rightValue": True,
    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
}
conds.append(new_cond)
ifn["parameters"]["conditions"]["conditions"] = conds

print(f"\nIF 'Solo citas activas' conditions ({len(conds)}):")
for c in conds:
    print(f"  - id={c['id']} left={str(c.get('leftValue'))[:150]}")

# PUT
allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
payload = {"name": wf["name"], "nodes": wf["nodes"],
           "connections": wf["connections"], "settings": settings}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]

r = requests.put(f"{N8N}/api/v1/workflows/{WF}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
print(f"\nPUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:500])
    sys.exit(1)

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"recordatorios_POST_FIXFILTER_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> recordatorios_POST_FIXFILTER_{ts}.json")
print(f"active: {wf_post.get('active')}")
