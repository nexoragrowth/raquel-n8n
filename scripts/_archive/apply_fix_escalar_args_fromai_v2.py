"""
Fix escalar_a_secretaria args extraction (2026-05-26).

Diagnostico:
- El nodo toolCode actualmente lee args con `$input.first()?.json.query/phone`,
  pero los args del LLM en un langchain.toolCode v1 NO llegan por ese path.
  Llegan por `inputOverride.ai_tool[0][0].json`. Resultado: el codigo siempre
  cae en defaults y manda al grupo "[ESCALADO BOT] Caso escalado sin resumen."
  con phone vacio.
- Las 6 escalaciones del 2026-05-26 (4 tests madrugada por bug 401 Dentalink,
  2 reales mañana) llegaron asi al grupo, sin contexto. Ademas, como phone=""
  el helper hace skip de Chatwoot label/note -> el bot sigue respondiendo
  despues de escalar.

Causa raiz historica:
- El 23/5 (apply_fix_escalar_destino_y_canned.py) se habia puesto $fromAI()
  correctamente. Entre el 23/5 y el 26/5 alguien reemplazo el codigo por la
  version $input.first() con un comentario que dice "NO usar $fromAI
  (revienta con 'No execution data available')" — probable que falle al
  testear node manualmente sin agent upstream, pero en runtime real desde el
  agent SI funciona.

Fix:
- Volver a $fromAI('query',...) y $fromAI('phone',...) como path principal.
- Agregar fallback: si phone llega vacio pero query trae 549\\d{10}, extraerlo.
- Ambos $fromAI envueltos en try/catch para no romper en edge cases.
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
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution','saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder','callerPolicy','callerIds'}

NEW_CODE = """// Escala al grupo de derivaciones via helper webhook.
// Lee args del LLM via $fromAI (path correcto para langchain.toolCode v1).
// El helper notify-grupo se encarga de: notify al grupo + (si hay phone) label humano + private note en Chatwoot.

let query = 'Caso escalado sin resumen.';
let phone = '';

// 1) Path principal: args del LLM via $fromAI
try {
  const q = $fromAI('query', 'Resumen breve del caso a escalar (quien escribe, que pide, por que escalar)', 'string');
  if (q && typeof q === 'string' && q.trim()) query = q.trim();
} catch (_) { /* $fromAI puede no estar disponible en contexto manual */ }

try {
  const p = $fromAI('phone', 'Telefono del paciente formato 549XXXXXXXXXX sin +', 'string');
  if (p && typeof p === 'string' && p.trim()) phone = p.trim().replace(/^\\+/, '');
} catch (_) {}

// 2) Fallback: si phone quedo vacio, extraerlo del query si esta embebido
if (!phone) {
  const m = String(query).match(/549\\d{10}/);
  if (m) phone = m[0];
}

try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
    headers: { 'Content-Type': 'application/json' },
    body: { text: '[ESCALADO BOT] ' + query, phone: phone },
    json: true
  });
  return 'Escalado al grupo correctamente.';
} catch (err) {
  try { console.log('[escalar] notify-grupo fail:', String(err && err.message ? err.message : err)); } catch(_) {}
  return 'Escalacion intentada (fallo el envio al grupo).';
}
"""


def http_req(method, url, data=None):
    req = urllib.request.Request(url, method=method, headers=HEADERS,
                                 data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


def main():
    print('--- Fetch v6 ---')
    wf = http_req('GET', f'{BASE}/workflows/{WID_V6}')

    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    ts = time.strftime('%Y%m%d_%H%M%S')
    bak_pre = f'workflows/history/v6_PRE_ESCALAR_ARGS_FIX_{ts}.json'
    Path(bak_pre).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup PRE: {bak_pre}')

    found = False
    for n in wf['nodes']:
        if n['name'] == 'escalar_a_secretaria':
            old = n['parameters'].get('jsCode','')
            n['parameters']['jsCode'] = NEW_CODE
            found = True
            print(f'patched jsCode (old {len(old)} chars -> new {len(NEW_CODE)} chars)')
            break

    if not found:
        raise SystemExit('escalar_a_secretaria node NOT FOUND')

    put = {
        'name': wf['name'],
        'nodes': wf['nodes'],
        'connections': wf['connections'],
        'settings': {k:v for k,v in (wf.get('settings') or {}).items() if k in ALLOWED},
    }
    http_req('PUT', f'{BASE}/workflows/{WID_V6}', put)
    print('PUT 200')

    try:
        http_req('POST', f'{BASE}/workflows/{WID_V6}/activate')
        print('v6 reactivated')
    except Exception as e:
        print(f'activate skip: {e}')

    wf2 = http_req('GET', f'{BASE}/workflows/{WID_V6}')
    bak_post = f'workflows/history/v6_POST_ESCALAR_ARGS_FIX_{ts}.json'
    Path(bak_post).write_text(json.dumps(wf2, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup POST: {bak_post}')

    # Verify the patch landed
    for n in wf2['nodes']:
        if n['name'] == 'escalar_a_secretaria':
            code = n['parameters'].get('jsCode','')
            no_cmt = re.sub(r'//.*?\n', '\n', code)
            assert "$fromAI('query'" in no_cmt, 'fromAI(query) not in code after PUT'
            assert "$fromAI('phone'" in no_cmt, 'fromAI(phone) not in code after PUT'
            print('verify: $fromAI(query) + $fromAI(phone) present in live code')
            break

    print('\n=== DONE ===')


if __name__ == '__main__':
    main()
