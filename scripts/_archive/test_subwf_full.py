"""Test full Steps 1-4 con casos reales."""
import json
import urllib.request
import re
import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

wh_path = f'test-full-{int(time.time())}'
tw = {
    'name': 'TEMP-test-full',
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
WID_TEST = twf['id']
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_TEST}/activate', method='POST', headers=HEADERS), timeout=20)
time.sleep(2)

CASOS = [
    'cancelo el viernes 5 de junio',
    'podemos pasarlo a otro dia?',
    'reprogramar para la semana que viene',
    'tengo clases a esa hora, podemos pasarlo a otro dia?',
    'Lunes 29 de junio a hs 16. Puede ser?',
    'no voy a poder ir',
    'ay perdon, surgio algo, no voy a poder ir',
    'Hola buenas quisiera reprogramar el dia 04 de junio para la semana q sigue sibes posible',
    'que tal?',  # ambiguo
    'cancelo el lunes 15',  # fecha NO matcheable (no hay turno ese dia)
]

for caso in CASOS:
    try:
        req = urllib.request.Request(
            f'https://n8n.raquelrodriguez.com.ar/webhook/{wh_path}',
            method='POST', headers={'Content-Type': 'application/json'},
            data=json.dumps({'phone': '5491161461034', 'text': caso, 'pushName': 'Lucas'}).encode()
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
            intent = d.get('intent', {})
            dec = d.get('decision', {})
            tobj = d.get('turno_objetivo', {})
            print('\n>> ' + caso)
            print('   intent: accion=' + str(intent.get('accion')) + ' fobj=' + str(intent.get('fecha_objetivo')) + ' hobj=' + str(intent.get('hora_objetivo')) + ' fact=' + str(intent.get('fecha_actual_mencionada')))
            print('   decision: siguiente_paso=' + str(dec.get('siguiente_paso')) + ' razon=' + str(dec.get('razon')))
            if tobj:
                print('   turno_objetivo: cita ' + str(tobj.get('id')) + ' ' + str(tobj.get('fecha')) + ' ' + str(tobj.get('hora_inicio')))
    except Exception as ex:
        print('   ERR: ' + str(ex))

try:
    urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_TEST}/deactivate', method='POST', headers=HEADERS), timeout=15)
except Exception:
    pass
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_TEST}', method='DELETE', headers=HEADERS), timeout=15)
print('\ncleaned')
