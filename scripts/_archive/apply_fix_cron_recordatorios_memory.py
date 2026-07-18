"""URGENTE: Cron Recordatorios NO escribia a memoria.

Bug encontrado el 2026-06-05 a partir del caso Ivan:
- Cron mandaba recordatorio 8 AM, paciente respondia 'sii' a las 8:02
- Router NO veia el recordatorio en memoria -> clasificaba mal el intent
- Sub-Agent Cancelar pedia clarificar 'cancelar o reprogramar?' a una confirmacion

Root cause: el flow conectaba Insert recordatorios_enviados -> Guardar en Chat Memory.
El output del Insert tiene `telefono`, `nombre_paciente`, `fecha_turno` (campos
diferentes), pero el codigo del nodo Guardar busca `phone`, `message`, `nombre`, etc.
Resultado: `if (!phone || !message)` siempre true -> saved=False para los 6+ items
del dia. Memoria nunca se llenaba.

Fix: reconectar Preparar mensaje -> Guardar en Chat Memory (donde si estan los campos
correctos). Insert recordatorios_enviados queda como nodo terminal (solo trackeo).
"""
import os, sys, json, requests
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
WF_ID = "7RqTApkvVavRmq3R"

wf = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(ROOT / "workflows" / "history" / f"cron_recordatorios_PRE_FIX_MEMORY_{ts}.json").write_text(
    json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")

conns = wf["connections"]

# 1) Quitar: Insert recordatorios_enviados -> Guardar en Chat Memory
ins_conns = conns.get("Insert recordatorios_enviados", {})
main_arr = ins_conns.get("main", [[]])
new_main = []
removed = 0
for arr in main_arr:
    new_arr = [c for c in arr if c.get("node") != "Guardar en Chat Memory"]
    if len(new_arr) != len(arr): removed += len(arr) - len(new_arr)
    new_main.append(new_arr)
ins_conns["main"] = new_main
conns["Insert recordatorios_enviados"] = ins_conns
print(f"Removed {removed} link(s): Insert recordatorios_enviados -> Guardar en Chat Memory")

# 2) Agregar: Preparar mensaje -> Guardar en Chat Memory (en main[0], junto con 'Tiene celular?')
prep_conns = conns.get("Preparar mensaje", {})
prep_main = prep_conns.get("main", [[]])
if not prep_main: prep_main = [[]]
already = any(c.get("node") == "Guardar en Chat Memory" for c in prep_main[0])
if not already:
    prep_main[0].append({"node": "Guardar en Chat Memory", "type": "main", "index": 0})
    print(f"Added link: Preparar mensaje -> Guardar en Chat Memory")
prep_conns["main"] = prep_main
conns["Preparar mensaje"] = prep_conns

# PUT
allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution","executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
body = {"name": wf["name"], "nodes": wf["nodes"], "connections": conns, "settings": settings, "staticData": wf.get("staticData")}
r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
print(f"PUT {r.status_code}")
if r.ok:
    wf2 = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60).json()
    c2 = wf2["connections"]
    p2 = c2.get("Preparar mensaje", {}).get("main", [[]])[0]
    i2 = c2.get("Insert recordatorios_enviados", {}).get("main", [[]])
    ok_added = any(c.get("node") == "Guardar en Chat Memory" for c in p2)
    ok_removed = not any(c.get("node") == "Guardar en Chat Memory" for arr in i2 for c in arr)
    print(f"verify: Preparar mensaje -> Guardar OK={ok_added}  Insert -> Guardar removed OK={ok_removed}")
