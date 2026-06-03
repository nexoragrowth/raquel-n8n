"""
Modificacion 2 al cron Recordatorios para test seguro:
- Fecha Manana: lee id_paciente_filter del body del webhook ademas de fecha_target
- GET Citas por fecha: incluye id_paciente.in:[...] al query si viene filter
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
(hist / f"recordatorios_PRE_PACFILTER_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

# ============================================================
# CAMBIO 1: Fecha Manana — agregar id_paciente_filter al output
# ============================================================
fm = next(n for n in wf["nodes"] if n["name"] == "Fecha Mañana")
orig = fm["parameters"]["jsCode"]

# El override ya esta. Modifico el return del override para incluir id_paciente_filter
# Patron actual:
#   return [{ json: { fecha_target: whBody.fecha_target, tipo_recordatorio: "manual_override" } }];
# Nuevo:
#   const filter = Array.isArray(whBody.id_paciente_filter) ? whBody.id_paciente_filter : [];
#   return [{ json: { fecha_target: whBody.fecha_target, tipo_recordatorio: "manual_override", id_paciente_filter: filter } }];

if "id_paciente_filter" in orig:
    print("Fecha Manana ya tiene id_paciente_filter — skip cambio 1")
else:
    old = 'return [{ json: { fecha_target: whBody.fecha_target, tipo_recordatorio: "manual_override" } }];'
    new = ('const filter = Array.isArray(whBody.id_paciente_filter) ? whBody.id_paciente_filter : [];\n'
           '  return [{ json: { fecha_target: whBody.fecha_target, tipo_recordatorio: "manual_override", id_paciente_filter: filter } }];')
    if old not in orig:
        print(f"  !! No encontre el return de override esperado — abortando")
        print(f"  jsCode actual:\n{orig[:600]}")
        sys.exit(1)
    fm["parameters"]["jsCode"] = orig.replace(old, new)
    # Tambien agregar id_paciente_filter al return ORIGINAL (cron normal) — vacio
    # Original return:
    # return [{ json: { fecha_target: formatDateYYYYMMDD(targetDate), tipo_recordatorio: "48h_habiles" } }];
    old2 = ('return [\n  {\n    json: {\n      fecha_target: formatDateYYYYMMDD(targetDate),\n'
            '      tipo_recordatorio: "48h_habiles"\n    }\n  }\n];')
    new2 = ('return [\n  {\n    json: {\n      fecha_target: formatDateYYYYMMDD(targetDate),\n'
            '      tipo_recordatorio: "48h_habiles",\n      id_paciente_filter: []\n    }\n  }\n];')
    if old2 in fm["parameters"]["jsCode"]:
        fm["parameters"]["jsCode"] = fm["parameters"]["jsCode"].replace(old2, new2)
        print("  cambio 1: override + cron normal ahora exponen id_paciente_filter")
    else:
        print("  !! return del cron normal no matcheo formato exacto — sigo igual (manual override OK)")
        # Buscar el patron mas flexible
        import re
        m = re.search(r'return\s*\[\s*\{\s*json\s*:\s*\{\s*fecha_target[^}]+\}\s*\}\s*\]\s*;', fm["parameters"]["jsCode"], re.DOTALL)
        if m:
            print(f"  return cron normal encontrado: {m.group(0)[:200]}")

# ============================================================
# CAMBIO 2: GET Citas por fecha — query condicional con id_paciente.in
# ============================================================
gc = next(n for n in wf["nodes"] if n["name"] == "GET Citas por fecha")
qp = gc["parameters"]["queryParameters"]["parameters"]
q_param = next(p for p in qp if p["name"] == "q")
print(f"\nQuery actual: {q_param['value']}")

# Reemplazar value por expresion n8n que construye el query con o sin filter
new_value = (
    '={{ JSON.stringify({'
    'fecha: {eq: $json.fecha_target}, '
    'id_estado: {neq: 1}, '
    '...($json.id_paciente_filter && $json.id_paciente_filter.length '
    '? {id_paciente: {in: $json.id_paciente_filter}} : {})'
    '}) }}'
)
q_param["value"] = new_value
print(f"Query nuevo: {new_value}")

# PUT
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
print(f"\nPUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:500])
    sys.exit(1)

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H, timeout=30).json()
(hist / f"recordatorios_POST_PACFILTER_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup -> recordatorios_POST_PACFILTER_{ts}.json")
print(f"active: {wf_post.get('active')}")
