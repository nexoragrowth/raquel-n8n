"""
Iteracion autonoma: reset (Dentalink + tabla + ratelimit) -> simular "Confirmados"
-> esperar -> inspeccionar -> reportar.

Devuelve por stdout structured report:
- estado_tabla
- estado_dentalink
- exec_id, last_node, tools_llamadas, output
- veredicto: SUCCESS si ambas confirmadas / PARCIAL si solo una / FAIL si ninguna
"""
import json, sys, time, uuid, urllib.request
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
CITAS = [8095, 8096]

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
        hit = urllib.request.Request(f"{N8N_BASE}/webhook/{hit_path}",
                                      method="POST", headers={"Content-Type":"application/json"},
                                      data=b"{}")
        with urllib.request.urlopen(hit, timeout=timeout) as r:
            return r.read().decode()
    finally:
        try: urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}/deactivate", method="POST", headers=HEADERS), timeout=15)
        except: pass
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}", method="DELETE", headers=HEADERS), timeout=15)

def reset_dentalink(cid):
    wh = f"reset-{cid}-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"method":"PUT","url":f"https://api.dentalink.healthatom.com/api/v1/citas/{cid}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "sendBody":True,"specifyBody":"json","jsonBody":json.dumps({"id_estado":7}),
                       "options":{}},
         "id":"h","name":"Put","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Put","type":"main","index":0}]]}}
    return run_temp(f"r-{cid}", nodes, conns, wh)

def reset_table():
    SBH = {"apikey":SR, "Authorization":f"Bearer {SR}", "Content-Type":"application/json"}
    for cid in CITAS:
        url = f"{SB}/rest/v1/recordatorios_enviados?id_cita_dentalink=eq.{cid}"
        data = json.dumps({"confirmado_at": None, "cancelado_at": None}).encode()
        req = urllib.request.Request(url, headers=SBH, method="PATCH", data=data)
        try: urllib.request.urlopen(req, timeout=15).read()
        except: pass

def reset_ratelimit():
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
    return run_temp(f"rrl", nodes, conns, wh)

def simulate_msg(text="Confirmados"):
    sim_id = f"SIM_AUTO_{uuid.uuid4().hex[:12].upper()}"
    body = {"event":"messages.upsert","instance":"raquel",
            "data":{"key":{"remoteJid":f"{PHONE}@s.whatsapp.net","fromMe":False,"id":sim_id},
                    "pushName":"Lucas SIM","message":{"conversation":text},
                    "messageType":"conversation","messageTimestamp":int(time.time())}}
    req = urllib.request.Request(f"{N8N_BASE}/webhook/evolution-v2", method="POST",
                                  headers={"Content-Type":"application/json"},
                                  data=json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=60) as r:
        return sim_id, r.read().decode()

def find_exec_by_sim(sim_id, max_wait=60):
    for i in range(max_wait // 3):
        time.sleep(3)
        execs = requests.get(f"{N8N_API}/executions?workflowId={WF_V6}&limit=10",
                             headers={"X-N8N-API-KEY":N8N_KEY,"Accept":"application/json"},
                             timeout=30).json().get("data", [])
        for e in execs:
            if e.get("status") == "running": continue
            d = requests.get(f"{N8N_API}/executions/{e['id']}?includeData=true",
                             headers={"X-N8N-API-KEY":N8N_KEY,"Accept":"application/json"},
                             timeout=30).json()
            ef = d.get("data",{}).get("resultData",{}).get("runData",{}).get("Edit Fields - Extraer Datos", [])
            if ef:
                try:
                    kid = ef[0]["data"]["main"][0][0]["json"].get("key_id","")
                    if kid == sim_id:
                        return e["id"], d
                except: pass
    return None, None

def get_tabla_state():
    url = f"{SB}/rest/v1/recordatorios_enviados?id_cita_dentalink=in.(8095,8096)&select=id_cita_dentalink,confirmado_at"
    req = urllib.request.Request(url, headers={"apikey":SR,"Authorization":f"Bearer {SR}"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())

def get_dentalink_state(cid):
    wh = f"st-{cid}-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"url":f"https://api.dentalink.healthatom.com/api/v1/citas/{cid}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "options":{}},
         "id":"h","name":"Get","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Get","type":"main","index":0}]]}}
    body = run_temp(f"st-{cid}", nodes, conns, wh)
    try:
        d = json.loads(body)["data"]
        return d["id_estado"], d["estado_cita"]
    except:
        return None, None

# ===========================================
# ITERATION
# ===========================================
print(f"\n========== ITERATION at {datetime.now().isoformat()} ==========")

print("[reset] Dentalink + table + ratelimit ...")
for cid in CITAS:
    body = reset_dentalink(cid)
    try:
        d = json.loads(body)
        if "data" in d:
            print(f"  cita={cid} reset OK id_estado={d['data']['id_estado']}")
        else:
            print(f"  cita={cid} reset: {str(d)[:100]}")
    except: print(f"  cita={cid} parse err")
reset_table()
reset_ratelimit()
print("[reset] done")

print("\n[sim] Sending 'Confirmados' ...")
sim_id, resp = simulate_msg("Confirmados")
print(f"  sim_id: {sim_id}")
print(f"  webhook resp: {resp[:120]}")

print("\n[wait] Polling for exec (max 60s) ...")
eid, d = find_exec_by_sim(sim_id, max_wait=60)
if not eid:
    print("  NO exec found in 60s — abort")
    sys.exit(2)
print(f"  found: exec {eid}")

# Inspect exec
rd = d["data"]["resultData"]["runData"]
last_node = d["data"]["resultData"]["lastNodeExecuted"]
err = d.get("data",{}).get("resultData",{}).get("error",{})
print(f"\n[inspect] last_node: {last_node}")
if err: print(f"  ERROR: {err.get('message','')[:200]}")

# Tools counts
for nm in ("consultar_recordatorios_abiertos","confirmar_turno","marcar_recordatorio_confirmado","escalar_a_secretaria"):
    runs = rd.get(nm, [])
    print(f"  {nm}: {len(runs)} runs")
    for run in runs:
        ait = run.get("data",{}).get("ai_tool",[])
        if ait:
            for ent in (ait[0] if isinstance(ait[0],list) else ait)[:1]:
                if isinstance(ent,list): ent = ent[0] if ent else {}
                js = ent.get("json",{}) if isinstance(ent,dict) else {}
                resp_text = str(js.get("response",""))[:150]
                print(f"    resp: {resp_text}")

# Final message
sm = rd.get("Split en Mensajes", [])
if sm:
    for run in sm:
        main = run.get("data",{}).get("main",[])
        if main and main[0]:
            for it in main[0]:
                m = it.get("json",{}).get("message","")
                if m: print(f"\n  FINAL OUT: {str(m)[:300]}")

# State checks
print("\n[verify] Tabla state:")
for r in get_tabla_state():
    print(f"  cita={r['id_cita_dentalink']} conf={r['confirmado_at']}")

print("\n[verify] Dentalink state:")
results = {}
for cid in CITAS:
    estado, descripcion = get_dentalink_state(cid)
    print(f"  cita={cid} id_estado={estado} ({descripcion})")
    results[cid] = estado

# Veredicto
print("\n========== VEREDICTO ==========")
ok_8095 = results.get(8095) == 18
ok_8096 = results.get(8096) == 18
if ok_8095 and ok_8096:
    print("✅ SUCCESS — ambas citas confirmadas en Dentalink")
elif ok_8095 or ok_8096:
    print(f"⚠️  PARCIAL — solo {'8095' if ok_8095 else '8096'} confirmada")
else:
    print("❌ FAIL — ninguna confirmada")
