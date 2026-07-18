"""Test: paciente menciona fecha que NO matchea ningún turno → bot NO debe cancelar."""
import json, re, urllib.request, io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

wh_path = 'edge-' + str(int(time.time()))
tw = {
    'name': 'TEMP-Edge',
    'nodes': [
        {'parameters': {'httpMethod': 'POST', 'path': wh_path, 'responseMode': 'lastNode', 'options': {}},
         'id': 'wh', 'name': 'Webhook', 'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
         'position': [240, 300], 'webhookId': wh_path},
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
twf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows', method='POST', headers=HEADERS, data=json.dumps(tw).encode()), timeout=30).read())
WID = twf['id']
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID}/activate', method='POST', headers=HEADERS), timeout=20)
time.sleep(2)

# Lucas tiene cita 8083 (5/6 11:00). Mensaje: "cancelo el lunes 7 de julio" (fecha que NO matchea)
CASOS = [
    ('cancelo el lunes 7 de julio', 'fecha NO matchea, debe NO cancelar'),
    ('cancelo el viernes 5 de junio', 'fecha matchea con 8083, debe NO cancelar real (es test pero el sub-WF intentaria!)'),
]

# OJO: solo dispar el primero, el segundo CANCELARIA 8083
caso, expectativa = CASOS[0]
print('Test: ' + caso)
print('Expectativa: ' + expectativa)
req = urllib.request.Request('https://n8n.raquelrodriguez.com.ar/webhook/' + wh_path, method='POST', headers={'Content-Type': 'application/json'}, data=json.dumps({'phone': '5491161461034', 'text': caso, 'pushName': 'Lucas'}).encode())
with urllib.request.urlopen(req, timeout=30) as r:
    d = json.loads(r.read().decode())
    print('\nResultado:')
    print('  action_executed: ' + str(d.get('action_executed')))
    print('  mensaje_final: ' + str(d.get('mensaje_final'))[:300])
    print('  cita_id (cancelada?): ' + str(d.get('cita_id')))
    debug = d.get('debug', {})
    decision = debug.get('decision', {})
    print('  decision.siguiente_paso: ' + str(decision.get('siguiente_paso')))
    print('  decision.razon: ' + str(decision.get('razon')))

# Verificar 8083 sigue intacta
import urllib.request as u
DT_CRED = 'TwN6eBWsydjMdsCM'
wh2 = 'chk-' + str(int(time.time()))
tw2 = {
    'name': 'TMP', 'nodes': [
        {'parameters': {'httpMethod': 'POST', 'path': wh2, 'responseMode': 'lastNode', 'options': {}}, 'id': 'wh', 'name': 'Webhook', 'type': 'n8n-nodes-base.webhook', 'typeVersion': 2, 'position': [240, 300], 'webhookId': wh2},
        {'parameters': {'method': 'GET', 'url': 'https://api.dentalink.healthatom.com/api/v1/citas/8083', 'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth', 'options': {}}, 'id': 'h', 'name': 'G', 'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2, 'position': [460, 300], 'credentials': {'httpHeaderAuth': {'id': DT_CRED, 'name': 'Header Auth account 3'}}, 'continueOnFail': True, 'alwaysOutputData': True}
    ], 'connections': {'Webhook': {'main': [[{'node': 'G', 'type': 'main', 'index': 0}]]}}, 'settings': {'executionOrder': 'v1'}
}
twf2 = json.loads(u.urlopen(u.Request(f'{BASE}/workflows', method='POST', headers=HEADERS, data=json.dumps(tw2).encode()), timeout=30).read())
WID2 = twf2['id']
u.urlopen(u.Request(f'{BASE}/workflows/{WID2}/activate', method='POST', headers=HEADERS), timeout=20)
time.sleep(2)
with u.urlopen(u.Request(f'https://n8n.raquelrodriguez.com.ar/webhook/{wh2}', method='POST', headers={'Content-Type':'application/json'}, data=b'{}'), timeout=15) as r:
    d2 = json.loads(r.read().decode())
    if isinstance(d2, list): d2 = d2[0] if d2 else {}
    data = d2.get('data', d2)
    print('\nVerify cita 8083 (debe seguir estado=7): estado=' + str(data.get('id_estado')))
try: u.urlopen(u.Request(f'{BASE}/workflows/{WID2}/deactivate', method='POST', headers=HEADERS), timeout=15)
except: pass
u.urlopen(u.Request(f'{BASE}/workflows/{WID2}', method='DELETE', headers=HEADERS), timeout=15)

try: u.urlopen(u.Request(f'{BASE}/workflows/{WID}/deactivate', method='POST', headers=HEADERS), timeout=15)
except: pass
u.urlopen(u.Request(f'{BASE}/workflows/{WID}', method='DELETE', headers=HEADERS), timeout=15)
