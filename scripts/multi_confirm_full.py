"""
Multi-confirm full test:
1. Crear cita Lucas (id=608) jueves 28/5 11:00 dur 10min
2. Crear cita Jana (id=621) jueves 28/5 11:10 dur 10min
3. Insertar 2 filas en recordatorios_enviados (simular cron)
4. Quitar label humano + clear ratelimit
5. Simular "Confirmados" como Lucas
6. Esperar, traer exec
7. Verificar: ambas confirmadas en Dentalink + tabla + response consolidado
8. Cleanup: anular ambas citas + DELETE filas tabla
"""
import json, sys, time, urllib.request, urllib.parse, uuid
from datetime import datetime, timedelta
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

# Jueves 28 de mayo 2026
FECHA_LUCAS = "2026-05-28"  # jueves
HORA_LUCAS = "11:30"
FECHA_JANA = "2026-05-29"   # viernes
HORA_JANA = "09:00"
DURACION = 10  # minutos

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
            headers={"Content-Type": "application/json"}, data=b"{}"), timeout=timeout) as r:
            return r.read().decode()
    finally:
        try: urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}/deactivate", method="POST", headers=HEADERS), timeout=15)
        except: pass
        urllib.request.urlopen(urllib.request.Request(
            f"{N8N_API}/workflows/{WID}", method="DELETE", headers=HEADERS), timeout=15)

def dt_post(path, body):
    wh = f"dtpost-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"method":"POST",
                       "url":f"https://api.dentalink.healthatom.com/api/v1{path}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "sendBody":True,"specifyBody":"json","jsonBody":json.dumps(body),
                       "options":{}},
         "id":"h","name":"Post","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,
         "position":[460,300],
         "credentials":{"httpHeaderAuth":{"id":DT_CRED,"name":"Header Auth account 3"}},
         "continueOnFail":True,"alwaysOutputData":True}]
    conns = {"Webhook":{"main":[[{"node":"Post","type":"main","index":0}]]}}
    return run_temp(f"dtpost-{wh}", nodes, conns, wh)

def dt_put(path, body):
    wh = f"dtput-{int(time.time()*1000)%100000}"
    nodes = [
        {"parameters":{"httpMethod":"POST","path":wh,"responseMode":"lastNode","options":{}},
         "id":"wh","name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,
         "position":[240,300],"webhookId":wh},
        {"parameters":{"method":"PUT",
                       "url":f"https://api.dentalink.healthatom.com/api/v1{path}",
                       "authentication":"genericCredentialType","genericAuthType":"httpHeaderAuth",
                       "sendBody":True,"specifyBody":"json","jsonBody":json.dumps(body),
                       "options":{}},
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
    """Supabase REST request."""
    SBH = {"apikey": SR, "Authorization": f"Bearer {SR}", "Content-Type": "application/json",
           "Prefer": "return=representation"}
    url = f"{SB}/rest/v1/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, headers=SBH, method=method, data=data)
    return urllib.request.urlopen(req, timeout=20).read().decode()

# =====================================================
# STEP 1: CREAR CITA LUCAS
# =====================================================
print(f"\n{'='*60}\nSTEP 1: Crear cita Lucas (id=608) {FECHA_LUCAS} {HORA_LUCAS} ({DURACION}min)")
print('='*60)
body_lucas = dt_post('/citas', {
    'id_dentista': 1,
    'id_sucursal': 1,
    'id_sillon': 1,
    'id_paciente': ID_LUCAS,
    'fecha': FECHA_LUCAS,
    'hora_inicio': HORA_LUCAS,
    'duracion': DURACION,
    'comentario': 'TEST multi-confirm Lucas',
})
print(f"resp: {body_lucas[:400]}")
try:
    d = json.loads(body_lucas)
    if 'data' in d:
        CITA_LUCAS = d['data']['id']
        print(f"  cita_id Lucas = {CITA_LUCAS}")
    else:
        print(f"  ERROR: {d}")
        sys.exit(1)
except Exception as e:
    print(f"  parse err: {e}")
    sys.exit(1)

# =====================================================
# STEP 2: CREAR CITA JANA
# =====================================================
print(f"\n{'='*60}\nSTEP 2: Crear cita Jana (id=621) {FECHA_JANA} {HORA_JANA} ({DURACION}min)")
print('='*60)
body_jana = dt_post('/citas', {
    'id_dentista': 1,
    'id_sucursal': 1,
    'id_sillon': 1,
    'id_paciente': ID_JANA,
    'fecha': FECHA_JANA,
    'hora_inicio': HORA_JANA,
    'duracion': DURACION,
    'comentario': 'TEST multi-confirm Jana',
})
print(f"resp: {body_jana[:400]}")
try:
    d = json.loads(body_jana)
    if 'data' in d:
        CITA_JANA = d['data']['id']
        print(f"  cita_id Jana = {CITA_JANA}")
    else:
        print(f"  ERROR: {d}")
        # cleanup Lucas
        print("  cleanup Lucas cita...")
        dt_put(f'/citas/{CITA_LUCAS}', {'id_estado': 1})
        sys.exit(1)
except Exception as e:
    print(f"  parse err: {e}")
    dt_put(f'/citas/{CITA_LUCAS}', {'id_estado': 1})
    sys.exit(1)

# =====================================================
# STEP 3: Insertar 2 filas en recordatorios_enviados
# =====================================================
print(f"\n{'='*60}\nSTEP 3: Insertar filas en recordatorios_enviados")
print('='*60)
for cita_id, id_pac, fecha, hora in [(CITA_LUCAS, ID_LUCAS, FECHA_LUCAS, HORA_LUCAS), (CITA_JANA, ID_JANA, FECHA_JANA, HORA_JANA)]:
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
    print(f"  insert cita={cita_id}: {resp[:200]}")

# =====================================================
# STEP 4: Quitar label humano + clear ratelimit
# =====================================================
print(f"\n{'='*60}\nSTEP 4: Reset estado (label humano + ratelimit)")
print('='*60)
# label humano
TOKEN = '1vwA3ihqX42MF29dXn9J5KEv'
CW = 'https://chat.raquelrodriguez.com.ar'
rq = requests.post(f'{CW}/api/v1/accounts/1/conversations/10/labels',
                   headers={'api_access_token': TOKEN, 'Content-Type': 'application/json'},
                   json={'labels': []}, timeout=15)
print(f"  Chatwoot labels clear: {rq.status_code}")

# ratelimit
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
print(f"  Redis ratelimit cleared")

# Tambien limpiar Postgres chat memory para que no haya contexto previo confundiendo
# (TTL stale=3d ya lo hace pero por seguridad)

# =====================================================
# STEP 5: Simular "Confirmados"
# =====================================================
print(f"\n{'='*60}\nSTEP 5: Simular 'Confirmados'")
print('='*60)
sim_id = f"SIM_MC_{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:6]}"
payload = {
    'event': 'messages.upsert',
    'instance': 'raquel',
    'data': {
        'key': {'remoteJid': f'{PHONE}@s.whatsapp.net', 'fromMe': False, 'id': sim_id},
        'pushName': 'Lucas (SIM MULTI-CONFIRM)',
        'messageType': 'conversation',
        'message': {'conversation': 'Confirmados'},
        'messageTimestamp': int(time.time()),
    }
}
rq2 = requests.post(f'{N8N_BASE}/webhook/evolution-v2', json=payload, timeout=30)
print(f"  POST: {rq2.status_code}")
print(f"  sim_id: {sim_id}")
print(f"  esperando 45s...")
time.sleep(45)

# =====================================================
# STEP 6: Buscar exec y inspeccionar
# =====================================================
print(f"\n{'='*60}\nSTEP 6: Verificar exec")
print('='*60)
H_API = {"X-N8N-API-KEY": N8N_KEY, "Accept": "application/json"}
target_exec = None
for tries in range(3):
    r = requests.get(f"{N8N_API}/executions",
                     headers=H_API, params={"workflowId": WF_V6, "limit": 20}, timeout=30)
    for e in r.json().get("data", []):
        eid = e["id"]
        r2 = requests.get(f"{N8N_API}/executions/{eid}",
                          headers=H_API, params={"includeData": "true"}, timeout=30)
        d = r2.json()
        rd = d.get("data", {}).get("resultData", {}).get("runData", {})
        if len(rd) < 10: continue
        wkh_k = [k for k in rd if 'ebhook' in k][:1]
        if not wkh_k: continue
        try:
            body = rd[wkh_k[0]][0]["data"]["main"][0][0]["json"].get("body", {}).get("data", {})
            push = body.get("pushName", "")
        except: continue
        if "SIM MULTI" in push:
            target_exec = (eid, e, rd)
            break
    if target_exec: break
    print(f"  no encontrado todavia, esperando 15s mas...")
    time.sleep(15)

if not target_exec:
    print("  ERROR: no se encontro exec. cleanup")
    dt_put(f'/citas/{CITA_LUCAS}', {'id_estado': 1})
    dt_put(f'/citas/{CITA_JANA}', {'id_estado': 1})
    sb_request('DELETE', f'recordatorios_enviados?id_cita_dentalink=in.({CITA_LUCAS},{CITA_JANA})')
    sys.exit(1)

eid, e, rd = target_exec
print(f"  exec {eid} status={e['status']}")

# Tools llamadas
for tn in ['consultar_recordatorios_abiertos', 'confirmar_turno',
           'marcar_recordatorio_confirmado', 'escalar_a_secretaria']:
    if tn in rd:
        runs = rd[tn]
        print(f"  {tn}: {len(runs)} runs")
        for i, r_run in enumerate(runs):
            d_out = r_run.get("data", {}).get("ai_tool", [])
            if d_out:
                try:
                    resp = d_out[0][0]["json"].get("response", "")
                    print(f"    run {i} resp: {str(resp)[:150]}")
                except: pass

# Mensaje final
sm = rd.get("Split en Mensajes", [])
if sm:
    for run in sm:
        main = run.get("data", {}).get("main", [])
        if main and main[0]:
            for it in main[0]:
                m = it.get("json", {}).get("message", "")
                if m: print(f"\n  FINAL OUT: {str(m)[:400]}")

# =====================================================
# STEP 7: Verificar estado Dentalink + tabla
# =====================================================
print(f"\n{'='*60}\nSTEP 7: Verificar estado final")
print('='*60)
for cita_id, who in [(CITA_LUCAS, "Lucas"), (CITA_JANA, "Jana")]:
    body = dt_get(f'/citas/{cita_id}')
    try:
        d = json.loads(body)
        estado = d.get('data', {}).get('id_estado')
        desc = d.get('data', {}).get('estado_cita')
        print(f"  cita {who} (id={cita_id}): id_estado={estado} ({desc})")
    except: pass

# tabla
resp = sb_request('GET', f'recordatorios_enviados?id_cita_dentalink=in.({CITA_LUCAS},{CITA_JANA})&select=id_cita_dentalink,confirmado_at')
print(f"  tabla recordatorios: {resp[:300]}")

# =====================================================
# STEP 8: CLEANUP
# =====================================================
print(f"\n{'='*60}\nSTEP 8: CLEANUP (anular citas + borrar filas)")
print('='*60)
for cita_id, who in [(CITA_LUCAS, "Lucas"), (CITA_JANA, "Jana")]:
    body = dt_put(f'/citas/{cita_id}', {'id_estado': 1})
    print(f"  anular cita {who} {cita_id}: {body[:150]}")

resp = sb_request('DELETE', f'recordatorios_enviados?id_cita_dentalink=in.({CITA_LUCAS},{CITA_JANA})')
print(f"  delete tabla: {resp[:150]}")

print(f"\n[FIN] cita_lucas={CITA_LUCAS} cita_jana={CITA_JANA}")
