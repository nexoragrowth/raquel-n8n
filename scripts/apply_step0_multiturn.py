"""Step 0 multi-turn detection para Sub-WF CancelarReprogramar.

PREPARADO pero NO aplica automáticamente. Lucas decide:
    python scripts/apply_step0_multiturn.py --apply

QUE HACE:
- Antes de Step 1 (buscar paciente), agregar Step 0 que lee el último mensaje
  del bot al paciente desde `n8n_chat_histories` (Postgres).
- Si el bot ya estaba en multi-turn (ofreció horarios o pidió confirmar cancelación),
  ramear a "ejecutar acción aceptada" en lugar de re-procesar desde cero.
- Detección por patrones del mensaje del bot:
  - "Te ofrezco:" / "Te puedo ofrecer:" / "tengo disponible:" → estado=oferta_horarios
  - "queda cancelado" → estado=cancelacion_ejecutada (no debería seguir)
  - "Para reprogramar" / "que dia o franja" → estado=esperando_fecha
  - otro → estado=conversacion_nueva

POR AHORA: Step 0 solo DETECTA el estado y lo deja en `multi_turn_state`. NO ramea
la decision todavía — eso es trabajo para iteración siguiente, donde mapeamos el
estado detectado al action_to_execute.

ROLLBACK:
    python scripts/apply_step0_multiturn.py --rollback
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path


def env(k):
    return re.search(rf'{k}=([^\r\n]+)', Path('.env').read_text()).group(1).strip()


API_KEY = env('N8N_API_KEY')
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
WID_SUB = Path('docs/sub_wf_cancelar_id.txt').read_text().strip()
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}
PG_CRED = 'xwvjww5Odcxiy1K9'

ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution',
           'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone',
           'executionOrder', 'callerPolicy', 'callerIds'}


def http(method, url, data=None):
    req = urllib.request.Request(url, method=method, headers=HEADERS,
                                 data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


STEP0_PG_NODE = {
    'parameters': {
        'operation': 'executeQuery',
        'query': (
            "SELECT id, message FROM n8n_chat_histories "
            "WHERE session_id = $1 "
            "ORDER BY id DESC LIMIT 6;"
        ),
        'options': {
            'queryReplacement': "={{ $('When called by v6').first().json.phone }}"
        },
    },
    'id': 'step0-pg',
    'name': 'Step 0a: Read Chat Memory',
    'type': 'n8n-nodes-base.postgres',
    'typeVersion': 2.5,
    'position': [340, 100],
    'credentials': {'postgres': {'id': PG_CRED, 'name': 'Postgres account'}},
    'continueOnFail': True,
    'alwaysOutputData': True
}

STEP0_CODE = """// Detect multi-turn state from last bot message
const msgs = $input.all().map(i => i.json);
const trigger = $('When called by v6').first().json;

// Mensajes vienen de la tabla n8n_chat_histories. message es JSON con shape LangChain.
// Buscar ultimo mensaje del bot (type=ai). Los msgs vienen desc por id.
let lastBotMsg = null;
let lastUserMsg = null;
for (const m of msgs) {
  const msgJson = typeof m.message === 'string' ? JSON.parse(m.message) : m.message;
  const isBot = msgJson?.type === 'ai' || msgJson?.id?.includes('AIMessage');
  const isUser = msgJson?.type === 'human' || msgJson?.id?.includes('HumanMessage');
  const content = msgJson?.data?.content || msgJson?.kwargs?.content || '';
  if (isBot && !lastBotMsg) lastBotMsg = content;
  if (isUser && !lastUserMsg) lastUserMsg = content;
  if (lastBotMsg && lastUserMsg) break;
}

const lower = (lastBotMsg || '').toLowerCase();

let multi_turn_state = 'conversacion_nueva';
if (/te ofrezco|te puedo ofrecer|tengo disponible|cual confirma|cual prefiere/i.test(lower)) {
  multi_turn_state = 'oferta_horarios';
} else if (/que dia.*viene mejor|para reprogramar.*que/i.test(lower)) {
  multi_turn_state = 'esperando_fecha';
} else if (/te confirmo.*cancelar/i.test(lower)) {
  multi_turn_state = 'esperando_confirmacion_cancelacion';
} else if (/queda cancelado/i.test(lower)) {
  multi_turn_state = 'cancelacion_ejecutada';
}

return [{ json: {
  ...trigger,
  multi_turn_state,
  last_bot_msg: (lastBotMsg || '').slice(0, 300),
  last_user_msg: (lastUserMsg || '').slice(0, 200)
}}];"""

STEP0_DETECT_NODE = {
    'parameters': {'jsCode': STEP0_CODE},
    'id': 'step0-detect',
    'name': 'Step 0b: Detect Multi-Turn State',
    'type': 'n8n-nodes-base.code',
    'typeVersion': 2,
    'position': [440, 100]
}


def show_diff(wf):
    print('=== DIFF Step 0 multi-turn (sin aplicar) ===')
    print('Conexión actual:')
    print('  When called by v6 -> Step 1.0: Prep Query')
    print('\nConexión propuesta:')
    print('  When called by v6 -> Step 0a: Read Chat Memory -> Step 0b: Detect Multi-Turn -> Step 1.0: Prep Query')
    print('\nNodos nuevos:')
    print('  - Step 0a: Read Chat Memory (Postgres SELECT últimos 6 msgs)')
    print('  - Step 0b: Detect Multi-Turn State (Code, detecta patrones del último bot msg)')
    print('\nResultado downstream: cada nodo gana acceso a `$json.multi_turn_state` y `$json.last_bot_msg`.')
    print('NO se cambia lógica todavía — esto es solo DETECCIÓN. La rama por estado va en otra iteración.')


def apply(wf):
    bak = f'workflows/history/subwf_PRE_STEP0_{int(time.time())}.json'
    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    Path(bak).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup PRE: {bak}')

    existing = {n['name'] for n in wf['nodes']}
    if 'Step 0a: Read Chat Memory' not in existing:
        wf['nodes'].append(STEP0_PG_NODE)
    if 'Step 0b: Detect Multi-Turn State' not in existing:
        wf['nodes'].append(STEP0_DETECT_NODE)

    # Re-wire: When called by v6 -> Step 0a -> Step 0b -> Step 1.0
    wf['connections']['When called by v6'] = {
        'main': [[{'node': 'Step 0a: Read Chat Memory', 'type': 'main', 'index': 0}]]
    }
    wf['connections']['Step 0a: Read Chat Memory'] = {
        'main': [[{'node': 'Step 0b: Detect Multi-Turn State', 'type': 'main', 'index': 0}]]
    }
    wf['connections']['Step 0b: Detect Multi-Turn State'] = {
        'main': [[{'node': 'Step 1.0: Prep Query', 'type': 'main', 'index': 0}]]
    }

    put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
           'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
    http('PUT', f'{BASE}/workflows/{WID_SUB}', put)
    print('PUT: 200')
    try:
        http('POST', f'{BASE}/workflows/{WID_SUB}/activate')
    except Exception:
        pass

    wf2 = http('GET', f'{BASE}/workflows/{WID_SUB}')
    has_step0 = any(n['name'] == 'Step 0a: Read Chat Memory' for n in wf2['nodes'])
    print(f'VERIFY: Step 0a inserted = {has_step0}')


def rollback(wf):
    bak = f'workflows/history/subwf_PRE_ROLLBACK_STEP0_{int(time.time())}.json'
    Path(bak).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup: {bak}')

    wf['nodes'] = [n for n in wf['nodes'] if n['name'] not in ('Step 0a: Read Chat Memory', 'Step 0b: Detect Multi-Turn State')]
    wf['connections']['When called by v6'] = {
        'main': [[{'node': 'Step 1.0: Prep Query', 'type': 'main', 'index': 0}]]
    }
    wf['connections'].pop('Step 0a: Read Chat Memory', None)
    wf['connections'].pop('Step 0b: Detect Multi-Turn State', None)

    put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
           'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
    http('PUT', f'{BASE}/workflows/{WID_SUB}', put)
    print('ROLLBACK aplicado')


def main():
    wf = http('GET', f'{BASE}/workflows/{WID_SUB}')
    if '--apply' in sys.argv:
        apply(wf)
    elif '--rollback' in sys.argv:
        rollback(wf)
    else:
        show_diff(wf)
        print('\n(Dry-run, sin cambios. Correr con --apply para aplicar.)')


if __name__ == '__main__':
    main()
