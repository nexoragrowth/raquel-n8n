"""
Fix raiz de escalar_a_secretaria (2026-05-23):

Diagnostico (auditoria hoy):
- El tool escalar_a_secretaria sigue declarando bloques Chatwoot que hacen
  `$('Preparar Mensaje Final').first().json.phone`. Esa expresion no funciona
  desde el contexto de un toolCode langchain (no tiene acceso a otros nodos).
- El catch que captura ese error revienta al hacer `e.name` o similar
  ("Cannot assign to read only property 'name'"). Eso aborta TODO el tool
  incluyendo el paso 1 (POST a notify-grupo). Resultado: ninguna escalacion
  del bot real llego al grupo desde Round 8.

Fix:
1. Reescribir el tool jsCode: solo POST al helper notify-grupo, todo
   wrapeado, recibe phone via $fromAI.
2. Extender el helper notify-grupo para: notify grupo + (si recibe phone)
   apply label humano + private note en Chatwoot.
3. Actualizar toolDescription para que el LLM pase phone como arg.
"""
import json
import re
import time
import urllib.request
from pathlib import Path

txt = Path('.env').read_text()
API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', txt).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
WID_V6 = 'O155MqHgOSaNZ9ye'
WID_HELPER = 'S5U6tSipzlgFHCkf'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution','saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder','callerPolicy','callerIds'}

EVO_CRED_ID = '4sAc6U57qV9jpeRy'
GROUP_JID = '120363407321448469@g.us'
CHATWOOT_BASE = 'https://chat.raquelrodriguez.com.ar'
CHATWOOT_TOKEN_FALLBACK = '1vwA3ihqX42MF29dXn9J5KEv'

# ============================================================
# NEW TOOL CODE
# ============================================================
NEW_TOOL_CODE = """// Escala al grupo de derivaciones via helper webhook (idempotente, seguro).
// El LLM pasa `query` (resumen) y `phone` (telefono del paciente, del contexto Round 6).
// El helper webhook se encarga de notify al grupo + label humano + private note en Chatwoot.

const query = $fromAI('query', 'Resumen breve del caso a escalar a la secretaria/doctora', 'string') || 'Caso escalado sin resumen.';
const phone = $fromAI('phone', 'Telefono del paciente formato 549XXXXXXXXXX (sin +), del contexto del paciente que escribe', 'string') || '';

try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
    headers: { 'Content-Type': 'application/json' },
    body: {
      text: '[ESCALADO BOT] ' + query,
      phone: phone
    },
    json: true
  });
  return 'Escalado al grupo correctamente.';
} catch (err) {
  // Log defensivo sin tocar props read-only del Error
  try { console.log('[escalar] notify-grupo fail:', String(err && err.message ? err.message : err)); } catch(_) {}
  return 'Escalacion intentada (fallo el envio al grupo).';
}
"""

NEW_TOOL_DESCRIPTION = """Escala el caso a la secretaria humana: deriva al grupo de WhatsApp del consultorio y aplica label humano + private note en Chatwoot para que el bot deje de responder.

ARGS REQUERIDOS:
- `query` (string): resumen breve del caso para que la secretaria/doctora entienda el contexto sin abrir la conversacion.
- `phone` (string): telefono del paciente formato 549XXXXXXXXXX (sin +). Esta en el bloque [CONTEXTO DEL PACIENTE QUE ESCRIBE] que recibis en el prompt.

USAR cuando: (a) urgencia medica o dental (dolor, sangrado, aparato salido, pieza caida, hinchazon, fiebre); (b) paciente insatisfecho, queja, reclamo, lenguaje agresivo; (c) consulta sobre obra social o convenios; (d) pregunta sobre tratamientos especificos que requieren evaluacion clinica; (e) cualquier consulta fuera de las 4 funciones del bot (agendar/confirmar/cancelar/info canned).

NO USAR para: (a) info canned (horarios, direccion, alias bancario, precio primera consulta = 40000); (b) confirmacion simple de turno post-recordatorio cuando id_estado=18 (responder canned y FIN); (c) cierres conversacionales sin pregunta abierta.
"""


# ============================================================
# NEW HELPER WORKFLOW (Helper - Notify Grupo)
# ============================================================
CHATWOOT_CODE = """// Aplica label 'humano' + private note en Chatwoot para el paciente que escalo.
// Recibe phone del body del webhook. Si no hay phone, skip silenciosamente.

const phone = ($input.first().json.body.phone || '').replace(/^\\+/, '');
const text = $input.first().json.body.text || '';

if (!phone) {
  return [{ json: { skipped: true, reason: 'no phone provided' } }];
}

let chatwootToken;
try { chatwootToken = $env.CHATWOOT_TOKEN; } catch(e) {}
if (!chatwootToken) chatwootToken = '__CW_TOKEN__';

const chatwootBase = '__CW_BASE__';
const account = '1';

let contactId = null;
let convId = null;

// 1) Search contact by phone
try {
  const search = await this.helpers.httpRequest({
    method: 'GET',
    url: chatwootBase + '/api/v1/accounts/' + account + '/contacts/search?q=' + encodeURIComponent(phone),
    headers: { 'api_access_token': chatwootToken },
    json: true
  });
  if (search && search.payload && search.payload.length > 0) {
    contactId = search.payload[0].id;
  }
} catch (e) {
  try { console.log('[helper] cw search fail:', String(e && e.message ? e.message : e)); } catch(_) {}
}

if (!contactId) {
  return [{ json: { skipped: true, reason: 'contact not found', phone: phone } }];
}

// 2) Get conversations of contact
try {
  const convs = await this.helpers.httpRequest({
    method: 'GET',
    url: chatwootBase + '/api/v1/accounts/' + account + '/contacts/' + contactId + '/conversations',
    headers: { 'api_access_token': chatwootToken },
    json: true
  });
  if (convs && convs.payload && convs.payload.length > 0) {
    convId = convs.payload[0].id;
  }
} catch (e) {
  try { console.log('[helper] cw convs fail:', String(e && e.message ? e.message : e)); } catch(_) {}
}

if (!convId) {
  return [{ json: { skipped: true, reason: 'conversation not found', contactId: contactId } }];
}

// 3) Apply label 'humano'
try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: chatwootBase + '/api/v1/accounts/' + account + '/conversations/' + convId + '/labels',
    headers: { 'api_access_token': chatwootToken, 'Content-Type': 'application/json' },
    body: { labels: ['humano'] },
    json: true
  });
} catch (e) {
  try { console.log('[helper] cw label fail:', String(e && e.message ? e.message : e)); } catch(_) {}
}

// 4) Add private note with the escalation reason
try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: chatwootBase + '/api/v1/accounts/' + account + '/conversations/' + convId + '/messages',
    headers: { 'api_access_token': chatwootToken, 'Content-Type': 'application/json' },
    body: { content: text, private: true, message_type: 'outgoing' },
    json: true
  });
} catch (e) {
  try { console.log('[helper] cw note fail:', String(e && e.message ? e.message : e)); } catch(_) {}
}

return [{ json: { applied: true, phone: phone, contactId: contactId, convId: convId } }];
""".replace('__CW_TOKEN__', CHATWOOT_TOKEN_FALLBACK).replace('__CW_BASE__', CHATWOOT_BASE)


def http_req(method, url, data=None):
    req = urllib.request.Request(url, method=method, headers=HEADERS,
                                 data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


def update_v6_tool():
    print('--- Updating v6 escalar_a_secretaria tool ---')
    wf = http_req('GET', f'{BASE}/workflows/{WID_V6}')
    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    bak = f'workflows/history/v6_PRE_FIX_ESCALAR_TOOL_{int(time.time())}.json'
    Path(bak).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'  backup PRE: {bak}')

    for n in wf['nodes']:
        if n['name'] == 'escalar_a_secretaria':
            n['parameters']['jsCode'] = NEW_TOOL_CODE
            n['parameters']['description'] = NEW_TOOL_DESCRIPTION
            print('  jsCode + description updated')
            break

    put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
           'settings': {k:v for k,v in (wf.get('settings') or {}).items() if k in ALLOWED}}
    http_req('PUT', f'{BASE}/workflows/{WID_V6}', put)
    print('  PUT 200')
    try:
        http_req('POST', f'{BASE}/workflows/{WID_V6}/activate')
        print('  v6 reactivated')
    except Exception as e:
        print(f'  activate skip: {e}')

    bak2 = f'workflows/history/v6_POST_FIX_ESCALAR_TOOL_{int(time.time())}.json'
    wf2 = http_req('GET', f'{BASE}/workflows/{WID_V6}')
    Path(bak2).write_text(json.dumps(wf2, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'  backup POST: {bak2}')


def update_helper():
    print('\n--- Updating Helper - Notify Grupo (agregar Chatwoot label/note) ---')
    helper = http_req('GET', f'{BASE}/workflows/{WID_HELPER}')
    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    bak = f'workflows/history/helper_notify_PRE_{int(time.time())}.json'
    Path(bak).write_text(json.dumps(helper, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'  backup PRE: {bak}')

    nodes = helper['nodes']
    # Verificar si ya existe el nodo Chatwoot Apply
    if any(n['name'] == 'Chatwoot Apply' for n in nodes):
        print('  Chatwoot Apply node already exists, updating code only')
        for n in nodes:
            if n['name'] == 'Chatwoot Apply':
                n['parameters']['jsCode'] = CHATWOOT_CODE
    else:
        # Find Evo Send node position
        evo_node = next((n for n in nodes if n['name'] == 'Notify Grupo Send'), None)
        x = (evo_node['position'][0] if evo_node else 460) + 240
        y = (evo_node['position'][1] if evo_node else 300)
        new_node = {
            'parameters': {'jsCode': CHATWOOT_CODE},
            'id': 'chatwoot-apply',
            'name': 'Chatwoot Apply',
            'type': 'n8n-nodes-base.code',
            'typeVersion': 2,
            'position': [x, y],
            'continueOnFail': True,
            'alwaysOutputData': True
        }
        nodes.append(new_node)
        # Wire: Notify Grupo Send -> Chatwoot Apply
        helper['connections'].setdefault('Notify Grupo Send', {'main': [[]]})
        existing = helper['connections']['Notify Grupo Send']['main'][0]
        if not any(c.get('node') == 'Chatwoot Apply' for c in existing):
            existing.append({'node': 'Chatwoot Apply', 'type': 'main', 'index': 0})
        print('  added Chatwoot Apply node + wired after Notify Grupo Send')

    put = {'name': helper['name'], 'nodes': nodes, 'connections': helper['connections'],
           'settings': {k:v for k,v in (helper.get('settings') or {}).items() if k in ALLOWED}}
    http_req('PUT', f'{BASE}/workflows/{WID_HELPER}', put)
    print('  PUT 200')

    try:
        http_req('POST', f'{BASE}/workflows/{WID_HELPER}/activate')
        print('  helper reactivated')
    except Exception as e:
        print(f'  activate skip: {e}')

    bak2 = f'workflows/history/helper_notify_POST_{int(time.time())}.json'
    h2 = http_req('GET', f'{BASE}/workflows/{WID_HELPER}')
    Path(bak2).write_text(json.dumps(h2, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'  backup POST: {bak2}')


def main():
    update_v6_tool()
    update_helper()
    print('\n=== DONE ===')
    print('Helper webhook: https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo')
    print('  Body: { text: str, phone?: str }  -> notify group + (si phone) cw label humano + private note')


if __name__ == '__main__':
    main()
