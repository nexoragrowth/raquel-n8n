"""
Single-confirm test: 1 sola cita Lucas, "Confirmados" -> debe confirmar la unica cita.
Verifica que el flow single sigue andando despues del multi-confirm.
"""
import json, sys, time, urllib.request, uuid
from datetime import datetime
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N_BASE = require("N8N_BASE_URL").rstrip("/")
N8N_API = N8N_BASE + "/api/v1"
N8N_KEY = require("N8N_API_KEY")
WF_V6 = require("N8N_WORKFLOW_V6_ID")
SB = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
HEADERS = {"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"}
DT_CRED = "TwN6eBWsydjMdsCM"
REDIS_CRED = "kdtSKwGbN1xAZeUh"

PHONE = "5491161461034"
ID_LUCAS = 608
FECHA = "2026-06-05"
HORA = "11:20"  # otro slot del viernes

def run_temp(name, nodes, conns, hit_path, timeout=30):
    wf = {"name": name, "nodes": nodes, "connections": conns,
          "settings": {"executionOrder": "v1"}}
    req = urllib.request.Request(f"{N8N_API}/workflows", method="POST", headers=HEADERS,
                                  data=json.dumps(wf).encode())
    twf = json.loads(urllib.request.urlopen(req, timeout=30).read())
    WID = twf["id"]
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}/activate", method="POST", headers=HEADERS), timeout=20)
        time.sleep(2)
        with urllib.request.urlopen(urllib.request.Request(
            f"{N8N_BASE}/webhook/{hit_path}", method="POST",
            headers={"Content-Type":"application/json"}, data=b"{}"), timeout=timeout) as r:
            return r.read().decode()
    finally:
        try: urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}/deactivate", method="POST", headers=HEADERS), timeout=15)
        except: pass
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}", method="DELETE", headers=HEADERS), timeout=15)

def dt_op(method, path, body=None):
    wh = f"dt-{int(time.time()*1000)%100000}"
    params = {"method":method,"url":f"https://api.dentalink.healthatom.com/api/v1{path}",
              "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth","options":{}}
    if body is not None:
        params["sendBody"] = True
        params["specifyBody"] = "json"
        params["jsonBody"] = json.dumps(body)
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":params,
         "id":"h","name":"Op","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Op","type":"main","index":0}]]}}
    return run_temp(f"dt-{wh}", nodes, conns, wh)

def sb_request(method, path, body=None):
    SBH = {"apikey": SR, "Authorization": f"Bearer {SR}", "Content-Type": "application/json",
           "Prefer": "return=representation"}
    url = f"{SB}/rest/v1/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, headers=SBH, method=method, data=data)
    try: return urllib.request.urlopen(req, timeout=20).read().decode()
    except Exception as e: return f"ERR: {e}"

print(f"[STEP 1] Crear UNA cita Lucas {FECHA} {HORA}")
b = dt_op('POST', '/citas', {'id_dentista':1,'id_sucursal':1,'id_sillon':1,'id_paciente':ID_LUCAS,
                              'fecha':FECHA,'hora_inicio':HORA,'duracion':10,'comentario':'TEST single'})
try:
    d = json.loads(b)
    CITA = d['data']['id']
    print(f"  cita = {CITA}")
except Exception as e:
    print(f"  ERR: {b[:300]}")
    sys.exit(1)

print(f"\n[STEP 2] Insert recordatorios_enviados (1 fila)")
row = {
    'telefono': PHONE,
    'chat_remote_jid': f'{PHONE}@s.whatsapp.net',
    'id_cita_dentalink': CITA,
    'id_paciente_dentalink': ID_LUCAS,
    'nombre_paciente': 'Test - Lucas Silva',
    'fecha_turno': FECHA,
    'hora_turno': HORA + ':00',
    'tipo': '24h',
    'enviado_at': datetime.utcnow().isoformat()+'Z',
}
resp = sb_request('POST', 'recordatorios_enviados', row)
print(f"  insert: {resp[:200]}")

print(f"\n[STEP 3] Reset label + ratelimit")
TOKEN = '1vwA3ihqX42MF29dXn9J5KEv'
CW = 'https://chat.raquelrodriguez.com.ar'
requests.post(f'{CW}/api/v1/accounts/1/conversations/10/labels',
              headers={'api_access_token':TOKEN,'Content-Type':'application/json'},
              json={'labels':[]}, timeout=15)
wh = f"rrl-{int(time.time()*1000)%100000}"
nodes_rrl = [
    {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
     "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
     "position":[240,300],"webhookId":wh},
    {"parameters":{"operation":"delete","key":f"ratelimit:{PHONE}"},
     "id":"r","name":"DelKey","type":"n8n-nodes-base.redis","typeVersion":1,
     "position":[460,300],
     "credentials":{"redis":{"id":REDIS_CRED,"name":"Redis account"}},
     "continueOnFail":True,"alwaysOutputData":True}]
run_temp(f"rrl-{wh}", nodes_rrl, {"Webhook":{"main":[[{"node":"DelKey","type":"main","index":0}]]}}, wh)

print(f"\n[STEP 4] Simular 'Confirmados'")
sim_id = f"SIM_SC_{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}"
payload = {'event':'messages.upsert','instance':'raquel',
           'data':{'key':{'remoteJid':f'{PHONE}@s.whatsapp.net','fromMe':False,'id':sim_id},
                   'pushName':'Lucas (SIM SINGLE)','messageType':'conversation',
                   'message':{'conversation':'Confirmados'},'messageTimestamp':int(time.time())}}
requests.post(f'{N8N_BASE}/webhook/evolution-v2', json=payload, timeout=30)
print(f"  sim_id={sim_id}")
print(f"  esperando 55s...")
time.sleep(55)

print(f"\n[STEP 5] Verificar exec")
H_API = {"X-N8N-API-KEY": N8N_KEY, "Accept": "application/json"}
target = None
for tries in range(4):
    r = requests.get(f"{N8N_API}/executions",
                     headers=H_API, params={"workflowId":WF_V6,"limit":30}, timeout=30)
    for e in r.json().get("data", []):
        eid = e["id"]
        r2 = requests.get(f"{N8N_API}/executions/{eid}",
                          headers=H_API, params={"includeData":"true"}, timeout=30)
        d = r2.json()
        rd = d.get("data",{}).get("resultData",{}).get("runData",{})
        if len(rd) < 10: continue
        wkh_k = [k for k in rd if 'ebhook' in k][:1]
        if not wkh_k: continue
        try:
            push = rd[wkh_k[0]][0]["data"]["main"][0][0]["json"].get("body",{}).get("data",{}).get("pushName","")
        except: continue
        if "SIM SINGLE" in push:
            target = (eid, e, rd)
            break
    if target: break
    time.sleep(15)

if target:
    eid, e, rd = target
    print(f"  exec {eid} status={e['status']}")
    for tn in ['consultar_recordatorios_abiertos','confirmar_turno',
               'marcar_recordatorio_confirmado','escalar_a_secretaria']:
        if tn in rd:
            runs = rd[tn]
            print(f"  {tn}: {len(runs)} runs")
            for i, run in enumerate(runs):
                io = run.get('inputOverride',{}).get('ai_tool',[])
                if io:
                    try: print(f"    in: {json.dumps(io[0][0]['json'], ensure_ascii=False)[:200]}")
                    except: pass
    sm = rd.get("Split en Mensajes", [])
    if sm:
        for run in sm:
            main = run.get("data",{}).get("main",[])
            if main and main[0]:
                for it in main[0]:
                    m = it.get("json",{}).get("message","")
                    if m: print(f"\n  FINAL: {str(m)[:400]}")
else:
    print("  NO exec encontrada")

print(f"\n[STEP 6] Estado Dentalink + tabla")
b = dt_op('GET', f'/citas/{CITA}')
try:
    d = json.loads(b)
    est = d.get('data',{}).get('id_estado')
    desc = d.get('data',{}).get('estado_cita')
    print(f"  cita {CITA}: id_estado={est} ({desc})")
except: pass
r = sb_request('GET', f'recordatorios_enviados?id_cita_dentalink=eq.{CITA}&select=id_cita_dentalink,confirmado_at')
print(f"  tabla: {r[:200]}")

print(f"\n[STEP 7] CLEANUP")
b = dt_op('PUT', f'/citas/{CITA}', {'id_estado':1})
print(f"  anular: {b[:120]}")
r = sb_request('DELETE', f'recordatorios_enviados?id_cita_dentalink=eq.{CITA}')
print(f"  delete fila: {r[:150]}")

print(f"\n[FIN] cita={CITA}")
