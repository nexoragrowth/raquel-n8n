"""
Simulate + wait correctly: dispara POST, espera hasta que aparezca una exec nueva
con SIM_ key_id mayor al last_id_seen. Despues inspecciona detalle.
"""
import json, sys, time, uuid, urllib.request
from datetime import datetime
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json"}

MSG = sys.argv[1] if len(sys.argv) > 1 else "Confirmados"
PHONE = "5491161461034"
SIM_ID = f"SIM_{uuid.uuid4().hex[:16].upper()}"
print(f"SIM_ID que voy a buscar: {SIM_ID}")

# Snapshot ultimo id
last = requests.get(f"{N8N}/api/v1/executions?workflowId={WF}&limit=1", headers=H, timeout=30).json().get("data", [])
last_id = int(last[0]["id"]) if last else 0
print(f"last_id snapshot: {last_id}")

# POST
body = {
    "event": "messages.upsert", "instance": "raquel",
    "data": {
        "key": {"remoteJid": f"{PHONE}@s.whatsapp.net", "fromMe": False, "id": SIM_ID},
        "pushName": "Lucas (SIM)",
        "message": {"conversation": MSG},
        "messageType": "conversation",
        "messageTimestamp": int(time.time()),
    },
    "destination": f"{N8N}/webhook/evolution-v2",
    "date_time": datetime.utcnow().isoformat(),
    "sender": f"{PHONE}@s.whatsapp.net",
}
req = urllib.request.Request(f"{N8N}/webhook/evolution-v2", method="POST",
                              headers={"Content-Type": "application/json"},
                              data=json.dumps(body).encode())
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        print(f"webhook: {r.status} {r.read().decode()[:120]}")
except Exception as e:
    print(f"webhook err: {e}")

# Espera hasta 40s a que aparezca una exec con nuestro SIM_ID
print("Esperando exec nueva...")
target = None
for i in range(20):
    time.sleep(2)
    execs = requests.get(f"{N8N}/api/v1/executions?workflowId={WF}&limit=10", headers=H, timeout=30).json().get("data", [])
    for e in execs:
        if int(e["id"]) <= last_id: continue
        d = requests.get(f"{N8N}/api/v1/executions/{e['id']}?includeData=true", headers=H, timeout=30).json()
        ef = d.get("data",{}).get("resultData",{}).get("runData",{}).get("Edit Fields - Extraer Datos", [])
        if ef:
            try:
                kid = ef[0]["data"]["main"][0][0]["json"].get("key_id","")
                if kid == SIM_ID:
                    target = e["id"]
                    break
            except: pass
    if target:
        print(f"  encontrado exec {target} (tras {(i+1)*2}s)")
        break
else:
    print(f"  NO encontrado en 40s. Ultimas execs:")
    for e in execs[:5]: print(f"    {e['id']} {e.get('startedAt')}")
    sys.exit(1)

# Inspeccionar
d = requests.get(f"{N8N}/api/v1/executions/{target}?includeData=true", headers=H, timeout=30).json()
rd = d["data"]["resultData"]["runData"]
last_node = d["data"]["resultData"]["lastNodeExecuted"]
err = d.get("data",{}).get("resultData",{}).get("error", {})
print(f"\nstatus: {d.get('status')} last_node: {last_node}")
if err:
    print(f"ERROR: {err.get('message','')[:300]}")
print(f"nodos: {len(rd)}")
# Resumen de tools
print("\nTools llamadas:")
for nm in ('consultar_recordatorios_abiertos','confirmar_turno','marcar_recordatorio_confirmado','marcar_recordatorio_cancelado','escalar_a_secretaria'):
    runs = rd.get(nm, [])
    print(f"  {nm}: {len(runs)} runs")
    for run in runs[:2]:
        ait = run.get('data',{}).get('ai_tool',[])
        if ait:
            for ent in (ait[0] if isinstance(ait[0],list) else ait)[:1]:
                if isinstance(ent,list): ent = ent[0] if ent else {}
                js = ent.get('json',{}) if isinstance(ent,dict) else {}
                print(f"    resp: {str(js.get('response',''))[:300]}")
# Mensaje final
sm = rd.get("Split en Mensajes", [])
if sm:
    main = sm[0].get('data',{}).get('main',[])
    if main and main[0]:
        for it in main[0][:2]:
            print(f"\nFINAL message: {str(it.get('json',{}).get('message',''))[:400]}")
