"""
Fix 4.1: cambio de tema mid-conversación. Si en medio de un flow operativo (ej
reprogramar) el paciente pregunta INFO CANNED (alias / horarios / dirección /
precio), abandonar la continuación y devolver consulta_general.

Esto evita que el sub-WF Cancelar reciba mensajes que no le corresponden y se
rompa intentando parsearlos como fecha o intent.
"""
import json
import re
import time
import urllib.request
from pathlib import Path

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
WID = re.search(r'N8N_WORKFLOW_V6_ID=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution','saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder','callerPolicy','callerIds'}

OLD = '''REGLA DE ORO DE CONTINUACION:
**Si tu ultimo AI estaba en flujo X y pediste info al paciente, la respuesta del paciente con esa info SIGUE estando en flujo X. NO cambies de intent.**'''

NEW = '''REGLA DE ORO DE CONTINUACION:
**Si tu ultimo AI estaba en flujo X y pediste info al paciente, la respuesta del paciente con esa info SIGUE estando en flujo X. NO cambies de intent.**

EXCEPCION A LA CONTINUACION (CAMBIO DE TEMA):
Si en medio de un flujo operativo el paciente pregunta sobre INFO CANNED basica (alias bancario, horarios de la clinica, direccion, precio de consulta, forma de pago) -> ABANDONAR la continuacion y devolver `consulta_general`. El paciente cambio de tema, no esta respondiendo a tu pregunta del flujo anterior.

Ejemplos:
- AI previo: "Que dia preferis para reprogramar?" en flujo CANCELAR -> "antes de eso, me pasas el alias?" -> intent = `consulta_general` (NO cancelar_o_reprogramar).
- AI previo: "Para reservar necesito tu DNI" en flujo AGENDAR -> "donde queda la clinica?" -> intent = `consulta_general`.
- AI previo: "Que dia preferis?" en flujo CANCELAR -> "el viernes" -> intent = `cancelar_o_reprogramar` (continuacion legitima).'''


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/v6_PRE_FIX_4_1_{int(time.time())}.json').write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

router = next((n for n in wf['nodes'] if n['name'] == 'Router - Clasificar Intent'), None)
sm = router['parameters']['options']['systemMessage']
if OLD not in sm:
    print('OLD not found'); raise SystemExit(1)
router['parameters']['options']['systemMessage'] = sm.replace(OLD, NEW)
print(f'patched: +{len(NEW) - len(OLD)} chars (excepcion cambio de tema)')

safe = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED}
http('PUT', f'/workflows/{WID}', safe)
print('PUT 200')

Path(f'workflows/history/v6_POST_FIX_4_1_{int(time.time())}.json').write_text(json.dumps(http('GET', f'/workflows/{WID}'), indent=2, ensure_ascii=False), encoding='utf-8')
print('backup POST OK')
