"""
Continuar multi-confirm con la cita Lucas 8104 ya creada.
- Crear Jana lunes 1/6 15:00
- Insertar tabla
- Simular + verificar + cleanup
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
ID_JANA = 621
CITA_LUCAS = 8104  # ya creada (jueves 28/5 11:30)
FECHA_LUCAS = "2026-05-28"
HORA_LUCAS = "11:30"

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

def dt_post(path, body):
    wh = f"dtp-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"method":"POST","url":f"https://api.dentalink.healthatom.com/api/v1{path}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "sendBody":True,"specifyBody":"json","jsonBody":json.dumps(body),"options":{}},
         "id":"h","name":"Post","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Post","type":"main","index":0}]]}}
    return run_temp(f"dtp-{wh}", nodes, conns, wh)

def dt_put(path, body):
    wh = f"dtput-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"method":"PUT","url":f"https://api.dentalink.healthatom.com/api/v1{path}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "sendBody":True,"specifyBody":"json","jsonBody":json.dumps(body),"options":{}},
         "id":"h","name":"Put","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Put","type":"main","index":0}]]}}
    return run_temp(f"dtput-{wh}", nodes, conns, wh)

def dt_get(path):
    wh = f"dtget-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"url":f"https://api.dentalink.healthatom.com/api/v1{path}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "options":{}},
         "id":"h","name":"Get","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Get","type":"main","index":0}]]}}
    return run_temp(f"dtget-{wh}", nodes, conns, wh)

def sb_request(method, path, body=None):
    SBH = {"apikey": SR, "Authorization": f"Bearer {SR}", "Content-Type": "application/json",
           "Prefer": "return=representation"}
    url = f"{SB}/rest/v1/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, headers=SBH, method=method, data=data)
    try:
        return urllib.request.urlopen(req, timeout=20).read().decode()
    except Exception as e:
        return f"ERR: {e}"

# ==========================================
# STEP 1: Crear cita Jana - probar varios horarios
# ==========================================
candidatos = [
    ("2026-06-01", "15:00"),  # lunes 1/6
    ("2026-06-01", "15:30"),
    ("2026-06-01", "16:00"),
    ("2026-06-01", "17:00"),
    ("2026-06-01", "18:00"),
    ("2026-06-03", "15:00"),  # miercoles 3/6
    ("2026-06-03", "16:00"),
    ("2026-06-04", "08:00"),  # jueves 4/6 mañana
    ("2026-06-04", "09:00"),
    ("2026-06-04", "10:00"),
]
CITA_JANA = None
FECHA_JANA = None
HORA_JANA = None
print(f"STEP 1: Buscar slot libre Jana")
for fecha, hora in candidatos:
    print(f"  probando {fecha} {hora}...")
    body = dt_post('/citas', {
        'id_dentista': 1, 'id_sucursal': 1, 'id_sillon': 1,
        'id_paciente': ID_JANA, 'fecha': fecha, 'hora_inicio': hora,
        'duracion': 10, 'comentario': 'TEST multi-confirm Jana',
    })
    try:
        d = json.loads(body)
        if 'data' in d and 'id' in d['data']:
            CITA_JANA = d['data']['id']
            FECHA_JANA = fecha
            HORA_JANA = hora
            print(f"  OK cita Jana = {CITA_JANA} ({fecha} {hora})")
            break
        else:
            print(f"    no funciono: {str(d.get('error',{}).get('message','?'))[:80]}")
    except Exception as e:
        print(f"  parse err: {e}")

if not CITA_JANA:
    print("\nNo se pudo crear cita Jana, anulando Lucas")
    dt_put(f'/citas/{CITA_LUCAS}', {'id_estado': 1})
    sys.exit(1)

# ==========================================
# STEP 2: Insertar 2 filas tabla
# ==========================================
print(f"\nSTEP 2: Insertar recordatorios_enviados")
for cita_id, id_pac, fecha, hora in [(CITA_LUCAS, ID_LUCAS, FECHA_LUCAS, HORA_LUCAS),
                                      (CITA_JANA, ID_JANA, FECHA_JANA, HORA_JANA)]:
    row = {
        'id_cita_dentalink': cita_id,
        'id_paciente_dentalink': id_pac,
        'telefono': PHONE,
        'fecha': fecha,
        'hora': hora,
        'tipo': 'recordatorio_24h_TEST',
        'enviado_at': datetime.utcnow().isoformat() + 'Z',
    }
    resp = sb_request('POST', 'recordatorios_enviados', row)
    print(f"  cita={cita_id}: {resp[:200]}")

# ==========================================
# STEP 3: Reset estado
# ==========================================
print(f"\nSTEP 3: Reset label humano + ratelimit")
TOKEN = '1vwA3ihqX42MF29dXn9J5KEv'
CW = 'https://chat.raquelrodriguez.com.ar'
requests.post(f'{CW}/api/v1/accounts/1/conversations/10/labels',
              headers={'api_access_token': TOKEN, 'Content-Type': 'application/json'},
              json={'labels': []}, timeout=15)

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
print("  done")

# ==========================================
# STEP 4: Simular "Confirmados"
# ==========================================
print(f"\nSTEP 4: Simular 'Confirmados'")
sim_id = f"SIM_MC2_{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}"
payload = {
    'event': 'messages.upsert',
    'instance': 'raquel',
    'data': {
        'key': {'remoteJid': f'{PHONE}@s.whatsapp.net', 'fromMe': False, 'id': sim_id},
        'pushName': 'Lucas (SIM MC2)',
        'messageType': 'conversation',
        'message': {'conversation': 'Confirmados'},
        'messageTimestamp': int(time.time()),
    }
}
requests.post(f'{N8N_BASE}/webhook/evolution-v2', json=payload, timeout=30)
print(f"  sim_id: {sim_id}")
print(f"  esperando 50s...")
time.sleep(50)

# ==========================================
# STEP 5: Verificar exec
# ==========================================
print(f"\nSTEP 5: Verificar exec")
H_API = {"X-N8N-API-KEY": N8N_KEY, "Accept": "application/json"}
target = None
for tries in range(3):
    r = requests.get(f"{N8N_API}/executions",
                     headers=H_API, params={"workflowId": WF_V6, "limit": 25}, timeout=30)
    for e in r.json().get("data", []):
        eid = e["id"]
        r2 = requests.get(f"{N8N_API}/executions/{eid}",
                          headers=H_API, params={"includeData":"true"}, timeout=30)
        d = r2.json()
        rd = d.get("data", {}).get("resultData", {}).get("runData", {})
        if len(rd) < 10: continue
        wkh_k = [k for k in rd if 'ebhook' in k][:1]
        if not wkh_k: continue
        try:
            push = rd[wkh_k[0]][0]["data"]["main"][0][0]["json"].get("body", {}).get("data", {}).get("pushName", "")
        except: continue
        if "SIM MC2" in push:
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
                d_out = run.get("data", {}).get("ai_tool", [])
                if d_out:
                    try:
                        resp = d_out[0][0]["json"].get("response","")
                        print(f"    run {i}: {str(resp)[:200]}")
                    except: pass
    sm = rd.get("Split en Mensajes", [])
    if sm:
        for run in sm:
            main = run.get("data",{}).get("main",[])
            if main and main[0]:
                for it in main[0]:
                    m = it.get("json",{}).get("message","")
                    if m: print(f"\n  FINAL: {str(m)[:500]}")
else:
    print("  NO encontrado")

# ==========================================
# STEP 6: Estado final
# ==========================================
print(f"\nSTEP 6: Estado Dentalink final")
for cita_id, who in [(CITA_LUCAS, "Lucas"), (CITA_JANA, "Jana")]:
    body = dt_get(f'/citas/{cita_id}')
    try:
        d = json.loads(body)
        est = d.get('data', {}).get('id_estado')
        desc = d.get('data', {}).get('estado_cita')
        print(f"  {who} cita={cita_id}: id_estado={est} ({desc})")
    except: pass

# ==========================================
# STEP 7: CLEANUP
# ==========================================
print(f"\nSTEP 7: CLEANUP")
for cita_id, who in [(CITA_LUCAS, "Lucas"), (CITA_JANA, "Jana")]:
    b = dt_put(f'/citas/{cita_id}', {'id_estado': 1})
    print(f"  anular {who} {cita_id}: {b[:150]}")

resp = sb_request('DELETE', f'recordatorios_enviados?id_cita_dentalink=in.({CITA_LUCAS},{CITA_JANA})')
print(f"  delete filas tabla: {resp[:150]}")

print(f"\n[FIN] cita_lucas={CITA_LUCAS} cita_jana={CITA_JANA}")
