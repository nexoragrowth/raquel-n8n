"""
Test agendar proactivo (2 turnos conversacionales).
Turno 1: "Hola quiero agendar un turno" -> bot debe pedir info o identificar.
Turno 2: respondemos identificandonos -> bot debe OFRECER slots concretos, NO preguntar abierto.
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
HEADERS = {"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"}
REDIS_CRED = "kdtSKwGbN1xAZeUh"
PHONE = "5491161461034"

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

def clear_ratelimit():
    wh = f"rrl-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"operation":"delete","key":f"ratelimit:{PHONE}"},
         "id":"r","name":"DelKey","type":"n8n-nodes-base.redis","typeVersion":1,
         "position":[460,300],
         "credentials":{"redis":{"id":REDIS_CRED,"name":"Redis account"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"DelKey","type":"main","index":0}]]}}
    run_temp(f"rrl-{wh}", nodes, conns, wh)

def clear_label():
    TOKEN = '1vwA3ihqX42MF29dXn9J5KEv'
    CW = 'https://chat.raquelrodriguez.com.ar'
    requests.post(f'{CW}/api/v1/accounts/1/conversations/10/labels',
                  headers={'api_access_token':TOKEN,'Content-Type':'application/json'},
                  json={'labels':[]}, timeout=15)

def send(text, tag):
    sim_id = f"SIM_{tag}_{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}"
    payload = {'event':'messages.upsert','instance':'raquel',
               'data':{'key':{'remoteJid':f'{PHONE}@s.whatsapp.net','fromMe':False,'id':sim_id},
                       'pushName':f'Lucas (TEST {tag})','messageType':'conversation',
                       'message':{'conversation':text},'messageTimestamp':int(time.time())}}
    requests.post(f'{N8N_BASE}/webhook/evolution-v2', json=payload, timeout=30)
    return sim_id

def find_exec_by_push(push_marker, max_wait=70):
    H_API = {"X-N8N-API-KEY": N8N_KEY, "Accept": "application/json"}
    target = None
    for tries in range(max_wait // 10):
        time.sleep(10)
        r = requests.get(f"{N8N_API}/executions",
                         headers=H_API, params={"workflowId":WF_V6,"limit":15}, timeout=30)
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
            if push_marker in push:
                target = (eid, e, rd)
                break
        if target: break
    return target

def show_exec(target, label):
    if not target:
        print(f"  [{label}] NO encontrado")
        return
    eid, e, rd = target
    print(f"  [{label}] exec {eid} status={e['status']}")
    # tools
    for tn in ['buscar_horarios','reservar_turno','buscar_paciente_dentalink',
               'crear_paciente_dentalink','escalar_a_secretaria']:
        if tn in rd:
            runs = rd[tn]
            print(f"    {tn}: {len(runs)} runs")
            for run in runs[:2]:
                io = run.get('inputOverride',{}).get('ai_tool',[])
                if io:
                    try: print(f"      in: {json.dumps(io[0][0]['json'], ensure_ascii=False)[:150]}")
                    except: pass
    # final msg
    sm = rd.get('Split en Mensajes', [])
    if sm:
        for run in sm:
            main = run.get('data',{}).get('main',[])
            if main and main[0]:
                for it in main[0]:
                    m = it.get('json',{}).get('message','')
                    if m: print(f"    >> {str(m)[:300]}")

# ========================================
print("[SETUP] clear label + ratelimit")
clear_label()
clear_ratelimit()
time.sleep(2)

print("\n[TURNO 1] mando: 'Hola, quiero agendar un turno'")
sim1 = send("Hola, quiero agendar un turno", "AGD1")
print(f"  sim_id={sim1}, esperando exec...")
target1 = find_exec_by_push("TEST AGD1", max_wait=70)
show_exec(target1, "T1")

print("\n[TURNO 2] reset ratelimit + mando: 'Soy Lucas Silva, quiero la primera consulta'")
clear_ratelimit()
time.sleep(2)
sim2 = send("Soy Lucas Silva, quiero la primera consulta lo antes posible", "AGD2")
print(f"  sim_id={sim2}, esperando exec...")
target2 = find_exec_by_push("TEST AGD2", max_wait=80)
show_exec(target2, "T2")

print("\n[FIN] revisar manualmente si T2 OFRECE slots o PREGUNTA abierto")
