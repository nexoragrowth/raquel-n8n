"""
Fix sub-WF CancelarReprogramar (5cAWJxiWJ50hxEq3):

1. Step 0b: ignorar mensajes ai del Router LLM que solo contienen
   labels de clasificación (ej "cancelar_o_reprogramar"), no son
   respuestas reales al paciente.

2. Agregar Step 8a/8b después de Step 7:
   - Step 8a: INSERT en n8n_chat_histories del user msg (type=human, source=wa_inbound)
   - Step 8b: INSERT en n8n_chat_histories del mensaje_final del bot
              (type=ai, source=wa_outbound)

Sin esto, la próxima invocación del sub-WF no ve el último mensaje del bot
(ej oferta de slots) y multi-turn detection rompe.

Backup pre/post + verify.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
SUB_WID = '5cAWJxiWJ50hxEq3'
PG_CRED = 'xwvjww5Odcxiy1K9'

HIST = Path('workflows/history')
HIST.mkdir(parents=True, exist_ok=True)


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204:
            return None
        return json.loads(r.read())


STEP_0B_CODE_NEW = r"""// Detect multi-turn state from last bot message in n8n_chat_histories
// Format real: row.message = { type: 'ai'|'human', content: '...', additional_kwargs: {source: ...}, ... }
const msgs = $input.all().map(i => i.json);
const trigger = $('When called by v6').first().json;

// Labels que tira el Router LLM (NO son respuestas reales al paciente)
const ROUTER_LABELS = new Set([
  'cancelar_o_reprogramar', 'confirmar', 'agendar', 'urgencia',
  'consulta_general', 'general', 'pago', 'derivar', 'silencio', 'no_reply',
  'cancelar', 'reprogramar'
]);

let lastBotMsg = null;
let lastUserMsg = null;
for (const m of msgs) {
  const msgJson = typeof m.message === 'string' ? JSON.parse(m.message) : m.message;
  if (!msgJson) continue;
  const type = msgJson.type;
  const content = msgJson.content || msgJson?.data?.content || msgJson?.kwargs?.content || '';
  const trimmed = String(content).trim().toLowerCase();
  // Saltear labels del Router (clasificacion, no respuesta real)
  if (type === 'ai' && ROUTER_LABELS.has(trimmed)) continue;
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
}}];
"""


STEP_8A_CODE = r"""// Step 8a: Prep INSERT human msg
const out = $('Step 7: Output Final').first().json;
const trigger = $('When called by v6').first().json;
const phone = String(trigger?.phone || '');
const userText = String(trigger?.text || '');
const humanMsg = {
  type: 'human',
  content: userText,
  additional_kwargs: { source: 'wa_inbound' },
  response_metadata: {},
  tool_calls: [],
  invalid_tool_calls: []
};
return [{ json: {
  session_id: phone,
  message_json: JSON.stringify(humanMsg),
  ai_message_json: JSON.stringify({
    type: 'ai',
    content: String(out.mensaje_final || ''),
    additional_kwargs: { source: 'wa_outbound' },
    response_metadata: {},
    tool_calls: [],
    invalid_tool_calls: []
  }),
  // Forward for return
  out
} }];
"""


def main():
    print('=== FETCH sub-WF ===')
    wf = http('GET', f'/workflows/{SUB_WID}')

    pre_path = HIST / f'subwf_PRE_CHAT_WRITEBACK_{int(time.time())}.json'
    pre_path.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  backup PRE: {pre_path}')

    nodes_by_name = {n['name']: n for n in wf['nodes']}

    # === FIX 1: update Step 0b code ===
    n0b = nodes_by_name.get('Step 0b: Detect Multi-Turn State')
    if not n0b:
        print('NO Step 0b found, abort')
        sys.exit(1)
    n0b['parameters']['jsCode'] = STEP_0B_CODE_NEW
    print('  Step 0b code updated (ignora Router labels)')

    # === FIX 2: add Step 8a (prep) + Step 8b INSERT human + 8c INSERT ai ===
    # Step 7: Output Final position
    step7 = nodes_by_name.get('Step 7: Output Final')
    if not step7:
        print('NO Step 7 found, abort')
        sys.exit(1)
    sx, sy = step7['position']

    # Remove pre-existing chat-writeback nodes if any (re-runnable)
    wf['nodes'] = [n for n in wf['nodes'] if not n['name'].startswith('Step 8')]
    nodes_by_name = {n['name']: n for n in wf['nodes']}
    # Also clean old connections from Step 7 → 8a
    if 'Step 7: Output Final' in wf['connections']:
        # We'll re-wire below
        pass

    step8a = {
        'parameters': {'jsCode': STEP_8A_CODE},
        'id': 'step8a-prep',
        'name': 'Step 8a: Prep Memory Writeback',
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [sx + 240, sy]
    }

    # Use Postgres node insert with named columns
    pg_creds = {'postgres': {'id': PG_CRED, 'name': 'Postgres account'}}
    step8b = {
        'parameters': {
            'operation': 'executeQuery',
            'query': "INSERT INTO n8n_chat_histories (session_id, message) VALUES ($1, $2::jsonb)",
            'options': {
                'queryReplacement': '={{ $json.session_id }},={{ $json.message_json }}'
            }
        },
        'id': 'step8b-pg-human',
        'name': 'Step 8b: INSERT human msg',
        'type': 'n8n-nodes-base.postgres',
        'typeVersion': 2.5,
        'position': [sx + 480, sy - 80],
        'credentials': pg_creds,
        'continueOnFail': True,
        'alwaysOutputData': True
    }
    step8c = {
        'parameters': {
            'operation': 'executeQuery',
            'query': "INSERT INTO n8n_chat_histories (session_id, message) VALUES ($1, $2::jsonb)",
            'options': {
                'queryReplacement': '={{ $json.session_id }},={{ $json.ai_message_json }}'
            }
        },
        'id': 'step8c-pg-ai',
        'name': 'Step 8c: INSERT ai msg',
        'type': 'n8n-nodes-base.postgres',
        'typeVersion': 2.5,
        'position': [sx + 480, sy + 80],
        'credentials': pg_creds,
        'continueOnFail': True,
        'alwaysOutputData': True
    }
    # Final return node - simply forwards Step 7 output via "Step 8a" json.out
    step8d = {
        'parameters': {
            'jsCode': "return $('Step 8a: Prep Memory Writeback').first().json.out ? [{json: $('Step 8a: Prep Memory Writeback').first().json.out}] : [{json:{}}];"
        },
        'id': 'step8d-return',
        'name': 'Step 8d: Return Output',
        'type': 'n8n-nodes-base.code',
        'typeVersion': 2,
        'position': [sx + 720, sy]
    }

    wf['nodes'].extend([step8a, step8b, step8c, step8d])

    # Wire connections:
    # Step 7 → Step 8a → (Step 8b parallel + Step 8c parallel) — actually serial: 8a → 8b → 8c → 8d
    # Serial is simpler and avoids race. Both INSERTs run; if any fails (continueOnFail) we still return.
    wf['connections']['Step 7: Output Final'] = {
        'main': [[{'node': 'Step 8a: Prep Memory Writeback', 'type': 'main', 'index': 0}]]
    }
    wf['connections']['Step 8a: Prep Memory Writeback'] = {
        'main': [[{'node': 'Step 8b: INSERT human msg', 'type': 'main', 'index': 0}]]
    }
    wf['connections']['Step 8b: INSERT human msg'] = {
        'main': [[{'node': 'Step 8c: INSERT ai msg', 'type': 'main', 'index': 0}]]
    }
    wf['connections']['Step 8c: INSERT ai msg'] = {
        'main': [[{'node': 'Step 8d: Return Output', 'type': 'main', 'index': 0}]]
    }

    # PUT
    safe = {k: wf[k] for k in ('name', 'nodes', 'connections', 'settings') if k in wf}
    print('=== PUT ===')
    http('PUT', f'/workflows/{SUB_WID}', safe)
    print('  PUT 200')

    # VERIFY
    after = http('GET', f'/workflows/{SUB_WID}')
    names = {n['name'] for n in after['nodes']}
    print(f'  verify Step 8a: {"Step 8a: Prep Memory Writeback" in names}')
    print(f'  verify Step 8b: {"Step 8b: INSERT human msg" in names}')
    print(f'  verify Step 8c: {"Step 8c: INSERT ai msg" in names}')
    print(f'  verify Step 8d: {"Step 8d: Return Output" in names}')

    post_path = HIST / f'subwf_POST_CHAT_WRITEBACK_{int(time.time())}.json'
    post_path.write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  backup POST: {post_path}')


if __name__ == '__main__':
    main()
