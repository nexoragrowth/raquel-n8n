"""
Fix Step 3.0: incluir multi_turn_state como contexto al LLM intent parser.
Si el bot esta esperando_fecha (acaba de preguntar "que dia"), cualquier
fecha que mencione el paciente es fecha_objetivo + accion=reprogramar
(no fecha_actual_mencionada).
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
const text = prev.trigger?.text || '';
const state = prev.trigger?.multi_turn_state || 'conversacion_nueva';
const lastBot = prev.trigger?.last_bot_msg || '';
const today = new Date().toISOString().slice(0,10);

const contextLine = (state === 'esperando_fecha')
  ? "CONTEXTO IMPORTANTE: El bot acaba de preguntar al paciente qué día prefiere para reprogramar. Si el paciente menciona CUALQUIER fecha en su respuesta, esa fecha es SIEMPRE fecha_objetivo (no fecha_actual_mencionada) y accion='reprogramar'. Mensaje previo del bot: " + lastBot
  : (state === 'oferta_horarios')
  ? "CONTEXTO: El bot acaba de ofrecer horarios al paciente. Si el paciente acepta uno, accion='reprogramar'."
  : "";

const body = {
  model: 'gpt-4o-mini',
  messages: [
    { role: 'system', content: "Sos un parser de mensajes de pacientes que quieren cancelar o reprogramar su turno dental. Hoy es " + today + ". " + contextLine + " Tu tarea: extraer del mensaje del paciente la INTENT (cancelar o reprogramar) y si menciona fecha/hora objetivo (para reprogramar) o fecha actual (para identificar el turno). Responde SOLO con JSON valido, sin texto antes ni despues, formato exacto: {\"accion\":\"cancelar\"|\"reprogramar\"|\"ambiguo\",\"fecha_objetivo\":\"YYYY-MM-DD\"|null,\"hora_objetivo\":\"HH:MM\"|null,\"fecha_actual_mencionada\":\"YYYY-MM-DD\"|null,\"razon\":\"texto breve\"}. Reglas: (1) Si paciente dice 'cancelar el [fecha]' = accion cancelar + fecha_actual_mencionada. (2) Si dice 'reprogramar' o 'pasarlo a otro dia' o 'tengo clases' o 'no puedo a esa hora' = accion reprogramar. (3) Si dice 'cancelo' o 'no voy a poder ir' sin fecha = accion cancelar. (4) Si state=esperando_fecha, fecha mencionada es fecha_objetivo. Calcula año: si fecha mencionada ya pasó este año usa siguiente año. Nunca uses años anteriores." },
    { role: 'user', content: 'Mensaje del paciente: ' + text }
  ],
  max_tokens: 200,
  temperature: 0.1,
  response_format: { type: 'json_object' }
};
return [{ json: { ...prev, openai_body: JSON.stringify(body) } }];
"""


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{SUB_WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/subwf_PRE_step3_multiturn_{int(time.time())}.json').write_text(
    json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

for n in wf['nodes']:
    if n['name'] == 'Step 3.0: Prep LLM Body':
        n['parameters']['jsCode'] = NEW_CODE
        print('Step 3.0 patched (multi_turn_state context)')
        break

safe = {k: wf[k] for k in ('name', 'nodes', 'connections', 'settings') if k in wf}
http('PUT', f'/workflows/{SUB_WID}', safe)
print('PUT 200')
