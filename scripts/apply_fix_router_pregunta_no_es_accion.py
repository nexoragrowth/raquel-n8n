"""
Fix CRITICO: el Router clasificaba preguntas tipo "tengo turno el [fecha]?" como
confirmar_post_recordatorio Y el Sub-Agent Confirmar ejecutaba `confirmar_turno`
en Dentalink. El paciente solo preguntaba, no quería confirmar.

Esto es peligroso porque la misma lógica permitiría que:
- "puedo cancelar?" → cancele real
- "podría reprogramar?" → reprograme
- "se confirma?" → confirme (lo que pasó)

Regla absoluta nueva: si el mensaje es una PREGUNTA (signo ? o palabras
interrogativas), NUNCA clasificar como accion ejecutable. Siempre consulta de
informacion.
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


OLD = """REGLAS DE PRIORIDAD:

**1. urgencia_dolor — MAXIMA PRIORIDAD**"""

NEW = """REGLAS DE PRIORIDAD:

**0. REGLA ABSOLUTA — PREGUNTA != ACCION (LEELA ANTES QUE TODO LO DEMAS):**
Si el mensaje del paciente es una PREGUNTA, NUNCA lo clasifiques como accion ejecutable (confirmar/cancelar/reprogramar/agendar). Las preguntas son consultas de informacion.

Senales de pregunta:
- Termina con "?" o "¿".
- Empieza con palabra interrogativa: cuando, cuándo, que, qué, a que hora, dónde, donde, como, cómo, cual, cuál, quien, quién.
- Frases tipo: "tengo turno el [fecha]?", "es el [fecha]?", "puedo cancelar?", "se puede mover?", "podria reprogramar?", "hay forma de pasarlo?".

Para preguntas sobre turnos propios del paciente -> `cancelar_o_reprogramar` (el sub-WF las maneja como consulta_info, NO ejecuta accion).
Para preguntas sobre info de la clinica/tratamientos -> `consulta_general`.

ATENCION ESPECIAL — discriminar "tengo turno" segun forma:
- "tengo turno el viernes" (afirmativo, sin ?) -> puede ser confirmar (paciente confirmando)
- "tengo turno el viernes?" (con ? o tono pregunta) -> consulta_info -> `cancelar_o_reprogramar`
- "¿tengo turno?" (pregunta) -> consulta_info -> `cancelar_o_reprogramar`

**1. urgencia_dolor — MAXIMA PRIORIDAD**"""


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/v6_PRE_PREGUNTA_NO_ACCION_{int(time.time())}.json').write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

router = next((n for n in wf['nodes'] if n['name'] == 'Router - Clasificar Intent'), None)
sm = router['parameters']['options']['systemMessage']
if OLD not in sm:
    print('OLD line not found'); raise SystemExit(1)
router['parameters']['options']['systemMessage'] = sm.replace(OLD, NEW)
print(f'patched Router (+{len(NEW)-len(OLD)} chars): regla absoluta pregunta != accion')

safe = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED}
http('PUT', f'/workflows/{WID}', safe)
print('PUT 200')

Path(f'workflows/history/v6_POST_PREGUNTA_NO_ACCION_{int(time.time())}.json').write_text(json.dumps(http('GET', f'/workflows/{WID}'), indent=2, ensure_ascii=False), encoding='utf-8')
print('backup POST OK')
