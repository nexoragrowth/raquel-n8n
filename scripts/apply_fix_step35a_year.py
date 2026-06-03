"""
Fix Step 3.5a: pasarle al LLM la fecha de hoy para evitar alucinacion de año.
"""
import json
import re
import time
import urllib.request
from pathlib import Path

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
SUB_WID = '5cAWJxiWJ50hxEq3'

NEW_CODE = r"""const prev = $input.first().json;
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
const today = new Date().toISOString().slice(0, 10);
const sysPrompt = "Sos un parser. El bot dental ofrecio horarios al paciente, y este respondio. Hoy es " + today + ". Determinar si el paciente acepta un slot ofrecido y cual. Responde SOLO JSON valido, formato exacto: {\"accepts\":true|false,\"slot_chosen\":{\"fecha\":\"YYYY-MM-DD\",\"hora_inicio\":\"HH:MM\"}|null,\"razon\":\"breve\"}. Reglas: (1) Si paciente dice si/dale/ok/perfecto sin especificar slot Y solo se ofrecio UN slot, accepts=true con ese slot. (2) Si se ofrecieron varios slots y paciente dice solo si, accepts=false. (3) Si paciente menciona una hora especifica (ej 8, 8:00, 8 de la manana, 15:10) o fecha, matcheala con uno de los slots ofrecidos. (4) Si paciente rechaza, accepts=false slot_chosen=null. (5) Si paciente cambia de tema, accepts=false slot_chosen=null. Para fecha: usa SIEMPRE el año actual (" + today.slice(0,4) + ") o el siguiente si la fecha mencionada ya paso este año. NUNCA uses años anteriores.";
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
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{SUB_WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/subwf_PRE_35a_YEAR_{int(time.time())}.json').write_text(
    json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

for n in wf['nodes']:
    if n['name'] == 'Step 3.5a: Prep Acceptance LLM':
        n['parameters']['jsCode'] = NEW_CODE
        print('Step 3.5a patched (year context)')
        break

safe = {k: wf[k] for k in ('name', 'nodes', 'connections', 'settings') if k in wf}
http('PUT', f'/workflows/{SUB_WID}', safe)
print('PUT 200')
