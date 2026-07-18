"""
Fix Step 3.5a: leer multi_turn_state de prev.trigger (anidado) en lugar de prev directo.

Causa: en el sub-WF, Step 0b output se acumula como `trigger` field dentro de los
siguientes pasos, entonces multi_turn_state queda en prev.trigger.multi_turn_state,
no en prev.multi_turn_state.

Antes: state defaulteaba a 'conversacion_nueva' → _skip_acceptance=true → no LLM
Después: state se lee correcto → si es oferta_horarios → corre LLM acceptance
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

NEW_CODE = r"""const prev = $input.first().json;
// multi_turn_state viene anidado dentro de prev.trigger (stringified) en pasos posteriores
let trig = prev.trigger;
if (typeof trig === 'string') {
  try { trig = JSON.parse(trig); } catch(e) { trig = {}; }
}
trig = trig || {};
const state = trig.multi_turn_state || prev.multi_turn_state || 'conversacion_nueva';
if (state !== 'oferta_horarios') {
  return [{ json: { ...prev, _skip_acceptance: true } }];
}
const lastBot = trig.last_bot_msg || prev.last_bot_msg || '';
const text = trig.text || prev.text || '';
const sysPrompt = "Sos un parser. El bot dental ofrecio horarios al paciente, y este respondio. Tu trabajo: determinar si el paciente acepta un slot ofrecido y cual. Responde SOLO JSON valido, formato exacto: {\"accepts\":true|false,\"slot_chosen\":{\"fecha\":\"YYYY-MM-DD\",\"hora_inicio\":\"HH:MM\"}|null,\"razon\":\"breve\"}. Reglas: (1) Si paciente dice si/dale/ok/perfecto sin especificar slot Y solo se ofrecio UN slot, accepts=true con ese slot. (2) Si se ofrecieron varios slots y paciente dice solo si, accepts=false, razon ambiguo. (3) Si paciente menciona una hora especifica (ej 8, 8:00, 8 de la manana, 15:10) o fecha, matcheala con uno de los slots ofrecidos. (4) Si paciente rechaza (no, otro dia, ninguno me sirve), accepts=false slot_chosen=null. (5) Si paciente cambia de tema, accepts=false slot_chosen=null. Importante: extrae fecha del mensaje del bot (formato comun: 'Para el martes 16 de junio tengo disponible: 8 de la manana / 9:20 de la manana'). Calcula YYYY-MM-DD asumiendo año actual o proximo.";
const body = {
  model: 'gpt-4o-mini',
  messages: [
    { role: 'system', content: sysPrompt },
    { role: 'user', content: 'Slots ofrecidos por el bot: ' + lastBot + '\n\nRespuesta del paciente: ' + text }
  ],
  max_tokens: 200,
  temperature: 0.1,
  response_format: { type: 'json_object' }
};
return [{ json: { ...prev, accept_openai_body: JSON.stringify(body), _skip_acceptance: false } }];
"""


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204:
            return None
        return json.loads(r.read())


def main():
    wf = http('GET', f'/workflows/{SUB_WID}')
    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    pre = Path(f'workflows/history/subwf_PRE_35a_NESTED_{int(time.time())}.json')
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'backup PRE: {pre}')

    found = False
    for n in wf['nodes']:
        if n['name'] == 'Step 3.5a: Prep Acceptance LLM':
            n['parameters']['jsCode'] = NEW_CODE
            found = True
            break
    if not found:
        print('NO Step 3.5a found'); sys.exit(1)

    safe = {k: wf[k] for k in ('name', 'nodes', 'connections', 'settings') if k in wf}
    http('PUT', f'/workflows/{SUB_WID}', safe)
    print('PUT 200')

    after = http('GET', f'/workflows/{SUB_WID}')
    for n in after['nodes']:
        if n['name'] == 'Step 3.5a: Prep Acceptance LLM':
            code = n['parameters']['jsCode']
            print('verify code starts with:', code[:100])
            break

    post = Path(f'workflows/history/subwf_POST_35a_NESTED_{int(time.time())}.json')
    post.write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'backup POST: {post}')


if __name__ == '__main__':
    main()
