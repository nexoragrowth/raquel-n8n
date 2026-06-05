"""REPOBLAR MEMORIA de los 6 pacientes que recibieron recordatorio HOY (5/6).

Bug: el cron de hoy NO escribio memoria (saved=False en 100% de items por
mismatch de campos). Fix aplicado pero los recordatorios YA enviados no
quedaron en memoria -> si esos pacientes responden hoy, el Router/Sub-Agent
los va a malinterpretar.

Approach:
1. Desconectar temporalmente Tiene celular? -> Enviar WhatsApp en el cron
   (asi no re-envia WhatsApp duplicado)
2. Disparar webhook 'trigger-recordatorios-manual' con id_paciente_filter
   de los 6 + fecha_target = 2026-06-09
3. El flow corre Preparar mensaje -> Guardar en Chat Memory -> Postgres Insert
   pero NO Enviar WhatsApp ni Insert recordatorios_enviados (porque corto la rama)
4. Re-conectar Tiene celular? -> Enviar WhatsApp
"""
import os, sys, json, requests, time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
WF_ID = "7RqTApkvVavRmq3R"

IDS = [60, 438, 460, 490, 515, 524]
FECHA = "2026-06-09"


def get_wf(): return requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60).json()


def put_wf(wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution","executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:500]); raise SystemExit(2)


# 1) Backup
wf = get_wf()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(ROOT / "workflows" / "history" / f"cron_PRE_REPOBLAR_{ts}.json").write_text(
    json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"backup pre")

# 2) Snapshot del link Tiene celular? -> Enviar WhatsApp para poder restaurar
conns = wf["connections"]
tc = conns.get("Tiene celular?", {})
tc_main = tc.get("main", [[]])
# Buscar y guardar el link a Enviar WhatsApp
enviar_idx = None
for arr_idx, arr in enumerate(tc_main):
    for c_idx, c in enumerate(arr):
        if c.get("node") == "Enviar WhatsApp":
            enviar_idx = (arr_idx, c_idx, c)
            break
    if enviar_idx: break

if not enviar_idx:
    print("!! no encontre link Tiene celular? -> Enviar WhatsApp, abort")
    sys.exit(2)

# Quitar el link
arr_idx, c_idx, link_data = enviar_idx
tc_main[arr_idx].pop(c_idx)
tc["main"] = tc_main
conns["Tiene celular?"] = tc
print(f"disconnect: Tiene celular? -> Enviar WhatsApp")
put_wf(wf)
time.sleep(2)

# 3) Trigger webhook manual
url = "https://n8n.raquelrodriguez.com.ar/webhook/trigger-recordatorios-manual"
payload = {"fecha_target": FECHA, "id_paciente_filter": IDS, "_motivo": "repoblar_memoria_5_6"}
print(f"\nPOST {url}")
print(f"  payload: {payload}")
r = requests.post(url, json=payload, timeout=60)
print(f"  status: {r.status_code}")
print(f"  body: {r.text[:300]}")

# 4) Esperar a que ejecute
time.sleep(15)

# 5) Re-conectar
wf2 = get_wf()
tc2 = wf2["connections"].get("Tiene celular?", {})
tc_main2 = tc2.get("main", [[]])
# Asegurar que main[0] existe
while len(tc_main2) <= arr_idx: tc_main2.append([])
# Re-agregar
already = any(c.get("node") == "Enviar WhatsApp" for c in tc_main2[arr_idx])
if not already:
    tc_main2[arr_idx].append(link_data)
tc2["main"] = tc_main2
wf2["connections"]["Tiene celular?"] = tc2
put_wf(wf2)
print(f"\nreconnect: Tiene celular? -> Enviar WhatsApp restaurado")

# 6) Verificar exec
time.sleep(2)
r = requests.get(f"{BASE}/api/v1/executions", headers=H, params={"workflowId": WF_ID, "limit": 3}, timeout=60).json()
print(f"\nlast execs:")
for e in r.get("data", [])[:3]:
    eid = e["id"]
    full = requests.get(f"{BASE}/api/v1/executions/{eid}?includeData=true", headers=H, timeout=30).json()
    runs = full.get("data", {}).get("resultData", {}).get("runData", {})
    if "Guardar en Chat Memory" in runs:
        out = runs["Guardar en Chat Memory"][0].get("data", {}).get("main", [[]])[0]
        if out:
            saved_count = sum(1 for it in out if it.get("json", {}).get("saved"))
            print(f"  exec={eid} {e.get('startedAt')[11:19]} status={e.get('status')}  saved={saved_count}/{len(out)}")
            for it in out[:6]:
                j = it.get("json", {})
                if j.get("saved"):
                    print(f"    saved sid={j.get('session_id')}")
