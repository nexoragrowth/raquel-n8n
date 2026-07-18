"""Smoke test post-Step 0: validar que el sub-WF sigue funcionando."""
import json, urllib.request, re, io, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

wh_path = 'smoke-' + str(int(time.time()))
tw = {
    'name': 'TEMP-Smoke',
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

# Caso clásico que ya validamos: "podemos pasarlo a otro dia?"
req = urllib.request.Request(f'https://n8n.raquelrodriguez.com.ar/webhook/{wh_path}', method='POST', headers={'Content-Type': 'application/json'}, data=json.dumps({'phone': '5491161461034', 'text': 'podemos pasarlo a otro dia?', 'pushName': 'Lucas'}).encode())
with urllib.request.urlopen(req, timeout=40) as r:
    d = json.loads(r.read().decode())
    print('Caso "podemos pasarlo a otro dia?":')
    print('  action_executed: ' + str(d.get('action_executed')))
    print('  mensaje_final: ' + str(d.get('mensaje_final', ''))[:200])

# Verificar que el sub-WF ejecuto Step 0 + el resto
WID_SUB_str = WID_SUB
H = {'X-N8N-API-KEY': API_KEY}
data = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/executions?workflowId={WID_SUB_str}&limit=1', headers=H), timeout=20).read())
if data['data']:
    eid = data['data'][0]['id']
    det = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/executions/{eid}?includeData=true', headers=H), timeout=20).read())
    runs = det.get('data',{}).get('resultData',{}).get('runData',{})
    print('\nNodos ejecutados en sub-WF: ' + str(list(runs.keys())[:6]) + '...')
    if 'Step 0b: Detect Multi-Turn State' in runs:
        try:
            out = runs['Step 0b: Detect Multi-Turn State'][0]['data']['main'][0][0]['json']
            print('  Step 0b: multi_turn_state=' + str(out.get('multi_turn_state')))
            print('  Step 0b: last_bot_msg=' + repr(out.get('last_bot_msg', ''))[:100])
        except Exception as ex: print('  parse err: ' + str(ex))

try: urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID}/deactivate', method='POST', headers=HEADERS), timeout=15)
except: pass
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID}', method='DELETE', headers=HEADERS), timeout=15)
