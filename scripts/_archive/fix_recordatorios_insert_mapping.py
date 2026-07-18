"""
Fix de 2 bugs introducidos por apply_recordatorios_insert.py:

1. Revertir el cambio al jsCode de 'Preparar mensaje' (TDZ en skip path).
   Restaura el bloque jsCode al estado pre-apply (sin los fields aux).

2. Cambiar el mapping del INSERT node para usar los fields que YA
   existen en el return original del nodo:
     - telefono           <- phone
     - chat_remote_jid    <- remoteJid (no chat_remote_jid)
     - id_cita_dentalink  <- cita_id
     - id_paciente_dentalink <- id_paciente
     - nombre_paciente    <- nombre
     - fecha_turno        <- fecha (no fecha_turno)
     - hora_turno         <- hora (no hora_turno)
     - tipo               <- tipo_recordatorio

Usa el backup pre-apply para sacar el jsCode original.
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

# Sacar el jsCode ORIGINAL del backup pre
backups_pre = sorted(hist.glob("recordatorios_PRE_APPLY_*.json"))
assert backups_pre, "No encontre backup pre-apply para sacar jsCode original"
wf_pre = json.loads(backups_pre[-1].read_text(encoding="utf-8"))
js_original = next(n for n in wf_pre["nodes"] if n["name"] == "Preparar mensaje")["parameters"]["jsCode"]
print(f"jsCode original recuperado de {backups_pre[-1].name} ({len(js_original)} chars)")

# GET workflow actual
wf = requests.get(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H, timeout=30).json()
print(f"GET wf actual: {len(wf['nodes'])} nodes")

# Backup pre-fix
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"recordatorios_PRE_FIX_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre-fix -> recordatorios_PRE_FIX_{ts}.json")

# ============================================================
# FIX 1: revertir jsCode de Preparar mensaje
# ============================================================
prep = next(n for n in wf["nodes"] if n["name"] == "Preparar mensaje")
prep["parameters"]["jsCode"] = js_original
print(f"\n[FIX 1] jsCode revertido a original ({len(js_original)} chars)")

# ============================================================
# FIX 2: corregir mapping del INSERT
# ============================================================
insert_node = next(n for n in wf["nodes"] if n["name"] == "Insert recordatorios_enviados")
new_mapping = {
    "telefono": "={{ $('Preparar mensaje').item.json.phone }}",
    "chat_remote_jid": "={{ $('Preparar mensaje').item.json.remoteJid }}",
    "id_cita_dentalink": "={{ $('Preparar mensaje').item.json.cita_id }}",
    "id_paciente_dentalink": "={{ $('Preparar mensaje').item.json.id_paciente }}",
    "nombre_paciente": "={{ $('Preparar mensaje').item.json.nombre }}",
    "fecha_turno": "={{ $('Preparar mensaje').item.json.fecha }}",
    "hora_turno": "={{ $('Preparar mensaje').item.json.hora }}",
    "tipo": "={{ $('Preparar mensaje').item.json.tipo_recordatorio }}",
    "workflow_execution_id": "={{ $execution.id }}",
}
insert_node["parameters"]["columns"]["value"] = new_mapping
print(f"\n[FIX 2] mapping INSERT corregido ({len(new_mapping)} columnas)")
for k, v in new_mapping.items():
    print(f"  {k} <- {v}")

# ============================================================
# PUT
# ============================================================
allowed = {"saveExecutionProgress", "saveManualExecutions",
           "saveDataErrorExecution", "saveDataSuccessExecution",
           "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
payload = {
    "name": wf["name"], "nodes": wf["nodes"],
    "connections": wf["connections"], "settings": settings,
}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]

print(f"\nPUT /workflows/{WF_ID} ...")
r = requests.put(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
if r.status_code >= 400:
    print(f"!! HTTP {r.status_code}: {r.text[:500]}")
    sys.exit(1)
print(f"ok ({r.status_code})")

# Verify
wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H, timeout=30).json()
(hist / f"recordatorios_POST_FIX_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post-fix -> recordatorios_POST_FIX_{ts}.json")

prep_post = next(n for n in wf_post["nodes"] if n["name"] == "Preparar mensaje")
ins_post = next(n for n in wf_post["nodes"] if n["name"] == "Insert recordatorios_enviados")
print(f"\nverify:")
print(f"  Preparar mensaje jsCode len = {len(prep_post['parameters']['jsCode'])}")
print(f"  Insert columns: {list(ins_post['parameters']['columns']['value'].keys())}")
print(f"  active: {wf_post.get('active')}")
