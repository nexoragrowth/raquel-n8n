"""Test: cancelar real con cita fresca + verificar Dentalink."""
import json
import re
import urllib.request
import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
DT_CRED = 'TwN6eBWsydjMdsCM'

# === Step 1: Reservar cita test nueva (16/6 8:00 Lucas) ===
wh_path_res = 'reserve-iter3-' + str(int(time.time()))
RES_BODY = {'id_dentista': 1, 'id_sucursal': 1, 'id_sillon': 1, 'id_paciente': 608,
            'fecha': '2026-06-16', 'hora_inicio': '08:00', 'duracion': 40,
            'comentario': 'TEST iter3 cancelar real'}

res_wf = {
    'name': 'TEMP-Iter3-Reserve',
    'nodes': [
        {'parameters': {'httpMethod': 'POST', 'path': wh_path_res, 'responseMode': 'lastNode', 'options': {}},
         'id': 'wh', 'name': 'Webhook', 'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
         'position': [240, 300], 'webhookId': wh_path_res},
        {'parameters': {
            'method': 'POST',
            'url': 'https://api.dentalink.healthatom.com/api/v1/citas/',
            'authentication': 'genericCredentialType',
            'genericAuthType': 'httpHeaderAuth',
            'sendBody': True, 'specifyBody': 'json', 'jsonBody': json.dumps(RES_BODY),
            'options': {}
         },
         'id': 'h', 'name': 'Reservar', 'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
         'position': [460, 300],
         'credentials': {'httpHeaderAuth': {'id': DT_CRED, 'name': 'Header Auth account 3'}},
         'continueOnFail': True, 'alwaysOutputData': True}
    ],
    'connections': {'Webhook': {'main': [[{'node': 'Reservar', 'type': 'main', 'index': 0}]]}},
    'settings': {'executionOrder': 'v1'}
}

twf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows', method='POST', headers=HEADERS, data=json.dumps(res_wf).encode()), timeout=30).read())
WID_R = twf['id']
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_R}/activate', method='POST', headers=HEADERS), timeout=20)
time.sleep(2)

req = urllib.request.Request('https://n8n.raquelrodriguez.com.ar/webhook/' + wh_path_res, method='POST', headers={'Content-Type': 'application/json'}, data=b'{}')
with urllib.request.urlopen(req, timeout=20) as r:
    d = json.loads(r.read().decode())

if d.get('error'):
    print('RESERVA ERR: ' + str(d.get('error'))[:200])
    try:
        urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_R}/deactivate', method='POST', headers=HEADERS), timeout=15)
    except Exception:
        pass
    urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_R}', method='DELETE', headers=HEADERS), timeout=15)
    sys.exit(1)

if isinstance(d, list):
    d = d[0] if d else {}
cita_data = d.get('data', d)
cita_new = cita_data.get('id')
print('Cita NUEVA: id=' + str(cita_new) + ' fecha=16/6 8:00 estado=' + str(cita_data.get('id_estado')))

try:
    urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_R}/deactivate', method='POST', headers=HEADERS), timeout=15)
except Exception:
    pass
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_R}', method='DELETE', headers=HEADERS), timeout=15)

# === Step 2: Ejecutar sub-WF con "cancelo el 16 de junio 8:00" ===
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()
wh_path_run = 'run-sub-iter3-' + str(int(time.time()))
run_wf = {
    'name': 'TEMP-Iter3-Run',
    'nodes': [
        {'parameters': {'httpMethod': 'POST', 'path': wh_path_run, 'responseMode': 'lastNode', 'options': {}},
         'id': 'wh', 'name': 'Webhook', 'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
         'position': [240, 300], 'webhookId': wh_path_run},
        {'parameters': {
            'workflowId': {'__rl': True, 'value': WID_SUB, 'mode': 'id'},
            'workflowInputs': {'mappingMode': 'defineBelow', 'value': {
                'phone': '={{ $json.body.phone }}', 'text': '={{ $json.body.text }}', 'pushName': '={{ $json.body.pushName }}'
            }, 'matchingColumns': [], 'schema': []}
         },
         'id': 'exec', 'name': 'Exec', 'type': 'n8n-nodes-base.executeWorkflow', 'typeVersion': 1.2,
         'position': [460, 300]}
    ],
    'connections': {'Webhook': {'main': [[{'node': 'Exec', 'type': 'main', 'index': 0}]]}},
    'settings': {'executionOrder': 'v1'}
}
twf2 = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows', method='POST', headers=HEADERS, data=json.dumps(run_wf).encode()), timeout=30).read())
WID_RUN = twf2['id']
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_RUN}/activate', method='POST', headers=HEADERS), timeout=20)
time.sleep(2)

req = urllib.request.Request('https://n8n.raquelrodriguez.com.ar/webhook/' + wh_path_run, method='POST', headers={'Content-Type': 'application/json'},
                             data=json.dumps({'phone': '5491161461034', 'text': 'cancelo el 16 de junio 8:00', 'pushName': 'Lucas'}).encode())
with urllib.request.urlopen(req, timeout=40) as r:
    res = json.loads(r.read().decode())

print('\nSub-WF response:')
print('  action_executed: ' + str(res.get('action_executed')))
print('  mensaje_final: ' + str(res.get('mensaje_final', ''))[:250])
print('  cita_id (canceled by sub-WF): ' + str(res.get('cita_id')))

try:
    urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_RUN}/deactivate', method='POST', headers=HEADERS), timeout=15)
except Exception:
    pass
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_RUN}', method='DELETE', headers=HEADERS), timeout=15)

# === Step 3: Verificar Dentalink: cita 8083 y cita_new ===
wh_path_chk = 'check-iter3-' + str(int(time.time()))
chk_wf = {
    'name': 'TEMP-Iter3-Check',
    'nodes': [
        {'parameters': {'httpMethod': 'POST', 'path': wh_path_chk, 'responseMode': 'lastNode', 'options': {}},
         'id': 'wh', 'name': 'Webhook', 'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
         'position': [240, 300], 'webhookId': wh_path_chk},
        {'parameters': {
            'method': 'GET',
            'url': '={{ "https://api.dentalink.healthatom.com/api/v1/citas/" + $json.body.cita_id }}',
            'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth',
            'options': {}
         },
         'id': 'h', 'name': 'Get', 'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
         'position': [460, 300],
         'credentials': {'httpHeaderAuth': {'id': DT_CRED, 'name': 'Header Auth account 3'}},
         'continueOnFail': True, 'alwaysOutputData': True}
    ],
    'connections': {'Webhook': {'main': [[{'node': 'Get', 'type': 'main', 'index': 0}]]}},
    'settings': {'executionOrder': 'v1'}
}
twf3 = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows', method='POST', headers=HEADERS, data=json.dumps(chk_wf).encode()), timeout=30).read())
WID_CHK = twf3['id']
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_CHK}/activate', method='POST', headers=HEADERS), timeout=20)
time.sleep(2)

print('\n--- Verify Dentalink ---')
for cita_id in [8083, cita_new]:
    req = urllib.request.Request('https://n8n.raquelrodriguez.com.ar/webhook/' + wh_path_chk, method='POST', headers={'Content-Type': 'application/json'}, data=json.dumps({'cita_id': cita_id}).encode())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode())
            if isinstance(d, list):
                d = d[0] if d else {}
            data = d.get('data', d)
            print('  cita ' + str(cita_id) + ': estado=' + str(data.get('id_estado')) + ' fecha=' + str(data.get('fecha')) + ' hora=' + str(data.get('hora_inicio')))
    except Exception as ex:
        print('  cita ' + str(cita_id) + ': err ' + str(ex))

try:
    urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_CHK}/deactivate', method='POST', headers=HEADERS), timeout=15)
except Exception:
    pass
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_CHK}', method='DELETE', headers=HEADERS), timeout=15)
