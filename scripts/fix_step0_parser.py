"""Fix Step 0b: parsear correctamente n8n_chat_histories format."""
import json, re, urllib.request, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

NEW_STEP0B_CODE = """// Detect multi-turn state from last bot message in n8n_chat_histories
// Format real: row.message = { type: 'ai'|'human', content: '...', additional_kwargs: {source: ...}, ... }
const msgs = $input.all().map(i => i.json);
const trigger = $('When called by v6').first().json;

let lastBotMsg = null;
let lastUserMsg = null;
for (const m of msgs) {
  const msgJson = typeof m.message === 'string' ? JSON.parse(m.message) : m.message;
  if (!msgJson) continue;
  const type = msgJson.type;
  // El content esta en .content directo (formato real n8n_chat_histories)
  // Fallback a data.content o kwargs.content por compatibilidad
  const content = msgJson.content || msgJson?.data?.content || msgJson?.kwargs?.content || '';
  if (type === 'ai' && !lastBotMsg) lastBotMsg = String(content);
  if (type === 'human' && !lastUserMsg) lastUserMsg = String(content);
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

wf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', headers=HEADERS), timeout=20).read())
for n in wf['nodes']:
    if n['name'] == 'Step 0b: Detect Multi-Turn State':
        n['parameters']['jsCode'] = NEW_STEP0B_CODE
        break

ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution', 'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone', 'executionOrder', 'callerPolicy', 'callerIds'}
put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
       'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', method='PUT', headers=HEADERS, data=json.dumps(put).encode()), timeout=30)
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}/activate', method='POST', headers=HEADERS), timeout=20)
print('Step 0b parser fixeado: lee content directo del message')
