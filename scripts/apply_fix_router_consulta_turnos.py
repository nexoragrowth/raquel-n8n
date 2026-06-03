"""
Fix: el Router clasificaba "cuando es mi turno?" como consulta_general (Sub-Agent
General que no ve Dentalink). Resultado: bot inventaba "no tienes turnos" sin
verificar. Solución: agregar al bloque cancelar_o_reprogramar los triggers de
CONSULTA DE INFO sobre turnos propios, para que el sub-WF (que ya soporta
intent.accion='consultar_info' tras el fix 1.1/1.2) los maneje.
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

OLD = '- Pregunta sobre cambio: "se puede cambiar?", "habria forma de pasarlo?", "puedo moverlo?".'
NEW = '''- Pregunta sobre cambio: "se puede cambiar?", "habria forma de pasarlo?", "puedo moverlo?".
- CONSULTA DE INFO sobre turnos propios (el paciente quiere saber, no actuar): "tengo turno?", "cuando es mi turno?", "que dia tengo?", "a que hora tengo el turno?", "tengo turno manana?", "es presencial?", "mi turno es el [fecha]?", "que turno tengo?". El sub-WF resuelve estas consultas con info de Dentalink, no son consulta_general.'''


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/v6_PRE_FIX_ROUTER_CONSULTA_TURNOS_{int(time.time())}.json').write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

router = next((n for n in wf['nodes'] if n['name'] == 'Router - Clasificar Intent'), None)
sm = router['parameters']['options']['systemMessage']
if OLD not in sm:
    print('OLD line not found in Router systemMessage'); raise SystemExit(1)
router['parameters']['options']['systemMessage'] = sm.replace(OLD, NEW)
print(f'patched Router (+{len(NEW)-len(OLD)} chars): consulta de info sobre turnos -> cancelar_o_reprogramar')

safe = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED}
http('PUT', f'/workflows/{WID}', safe)
print('PUT 200')

Path(f'workflows/history/v6_POST_FIX_ROUTER_CONSULTA_TURNOS_{int(time.time())}.json').write_text(json.dumps(http('GET', f'/workflows/{WID}'), indent=2, ensure_ascii=False), encoding='utf-8')
print('backup POST OK')
