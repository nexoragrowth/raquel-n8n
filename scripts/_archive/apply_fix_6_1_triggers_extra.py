"""
Fix 6.1: agregar triggers argentinos faltantes al Router LM bloque cancelar_o_reprogramar.

Faltaban: "no me da", "no llegaria", "me queda lejos", "ahi no llego", "no me cierra ese dia".
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

OLD = '- Imposibilidad: "no puedo ir", "no voy a poder", "no llego", "no me da", "voy a faltar".'
NEW = '- Imposibilidad: "no puedo ir", "no voy a poder", "no llego", "no llegaria", "no me da", "no me da el tiempo", "voy a faltar", "ahi no llego", "no me cierra", "me queda lejos", "no me alcanza el tiempo".'


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/v6_PRE_FIX_6_1_{int(time.time())}.json').write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

router = next((n for n in wf['nodes'] if n['name'] == 'Router - Clasificar Intent'), None)
sm = router['parameters']['options']['systemMessage']
if OLD not in sm:
    print('OLD line not found, abort'); raise SystemExit(1)
router['parameters']['options']['systemMessage'] = sm.replace(OLD, NEW)
print(f'patched: +{len(NEW) - len(OLD)} chars en bloque cancelar_o_reprogramar')

safe = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED}
http('PUT', f'/workflows/{WID}', safe)
print('PUT 200')

Path(f'workflows/history/v6_POST_FIX_6_1_{int(time.time())}.json').write_text(json.dumps(http('GET', f'/workflows/{WID}'), indent=2, ensure_ascii=False), encoding='utf-8')
print('backup POST OK')
