"""
Fix Pre-filtro Cierre: "si" / "no" / "ese" se silenciaban como short_closing.
Pero son respuestas afirmativas a preguntas del bot ("Era ese el que querias
cancelar?" -> "si").

Agregar lista de afirmaciones/negaciones cortas que SIEMPRE pasan al Router
(skip:false), antes de cualquier short_closing.
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


OLD = """// === SALUDOS — pasar ===
const saludos = ['hola','holaa','holaaa','holis','buenas','buen dia','buenos dias','buenas tardes','buenas noches','que tal','como va','como andas','que onda'];"""

NEW = """// === AFIRMACIONES/NEGACIONES CORTAS — pasar (respuesta a pregunta del bot) ===
// "si" / "no" / "ese" / "exacto" no son cierres conversacionales. Cuando el bot
// pregunta ("Era ese el turno?" / "Confirmas la cancelacion?"), el paciente
// responde con palabra corta. NUNCA silenciarlas — Router decide via CONTINUACION.
const afirmaciones_cortas = [
  'si','sí','sii','siii','sis','sip','sipi','si si','sí sí','sip sip',
  'no','nop','nope','nono','no no',
  'claro','claro que si','claro que sí','obvio','obvio si','obvio sí',
  'exacto','correcto','asi es','así es','tal cual eso','tal cual ese',
  'ese','ese mismo','ese si','ese sí','ese era','ese mismo si','ese mismo sí',
  'eso','eso es','eso mismo','eso era',
  'si confirmo','sí confirmo','confirmo eso','confirmo ese',
  'no era','no era ese','ese no','no ese'
];
if (afirmaciones_cortas.includes(t)) {
  return [{ json: { skip: false, reason: 'afirmacion_negacion_corta', text } }];
}

// === SALUDOS — pasar ===
const saludos = ['hola','holaa','holaaa','holis','buenas','buen dia','buenos dias','buenas tardes','buenas noches','que tal','como va','como andas','que onda'];"""


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/v6_PRE_PREFILTRO_AFIRMACIONES_{int(time.time())}.json').write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

pfc = next(n for n in wf['nodes'] if n['name'] == 'Pre-filtro Cierre')
code = pfc['parameters']['jsCode']
if OLD not in code:
    print('OLD section not found in Pre-filtro Cierre'); raise SystemExit(1)
pfc['parameters']['jsCode'] = code.replace(OLD, NEW)
print(f'patched Pre-filtro Cierre: +{len(NEW)-len(OLD)} chars (afirmaciones cortas exception)')

safe = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED}
http('PUT', f'/workflows/{WID}', safe)
print('PUT 200')

Path(f'workflows/history/v6_POST_PREFILTRO_AFIRMACIONES_{int(time.time())}.json').write_text(json.dumps(http('GET', f'/workflows/{WID}'), indent=2, ensure_ascii=False), encoding='utf-8')
print('backup POST OK')
