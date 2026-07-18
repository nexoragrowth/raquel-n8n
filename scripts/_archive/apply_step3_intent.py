"""Aplica Step 2b fix + Step 3 (LLM intent extract) al Sub-WF CancelarReprogramar."""
import json
import re
import urllib.request
import io
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
DT_CRED = 'TwN6eBWsydjMdsCM'
OPENAI_CRED = 'nYujqfon7GGDnJUO'
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

wf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', headers=HEADERS), timeout=20).read())

NEW_2B = """const turnosRaw = $input.first().json;
const paciente = $('Step 1b: Procesar resultado').first().json.paciente;
const trigger = $('Step 1b: Procesar resultado').first().json.trigger;

let turnos = [];
if (Array.isArray(turnosRaw)) turnos = turnosRaw[0]?.data || [];
else turnos = turnosRaw?.data || [];

const hoy = new Date();
hoy.setHours(0,0,0,0);
const proximos = turnos
  .filter(t => t.id_estado !== 1)
  .filter(t => {
    if (!t.fecha) return false;
    const f = new Date(t.fecha + 'T00:00:00');
    return f >= hoy;
  })
  .map(t => ({
    id: t.id,
    fecha: t.fecha,
    hora_inicio: t.hora_inicio,
    hora_fin: t.hora_fin,
    id_estado: t.id_estado,
    id_dentista: t.id_dentista,
    comentario: t.comentario || '',
    nombre_estado: t.nombre_estado || ''
  }))
  .sort((a, b) => String(a.fecha + ' ' + (a.hora_inicio || '')).localeCompare(String(b.fecha + ' ' + (b.hora_inicio || ''))));

return [{ json: {
  ok: proximos.length > 0,
  paciente,
  trigger,
  turnos_proximos: proximos,
  count: proximos.length
}}];"""

STEP3A_SYS = (
    "Sos un parser de mensajes de pacientes que quieren cancelar o reprogramar su turno dental. "
    "Tu tarea: extraer del mensaje del paciente la INTENT (cancelar o reprogramar) "
    "y si menciona fecha/hora objetivo (para reprogramar) o fecha actual (para identificar el turno). "
    "Responde SOLO con JSON valido, sin texto antes ni despues, formato exacto: "
    '{"accion":"cancelar"|"reprogramar"|"ambiguo","fecha_objetivo":"YYYY-MM-DD"|null,"hora_objetivo":"HH:MM"|null,"fecha_actual_mencionada":"YYYY-MM-DD"|null,"razon":"texto breve"}. '
    "Hoy es 2026-05-24 (domingo). Si paciente dice 'la semana que viene' calcula fecha aproximada (lunes siguiente). "
    "Si dice 'cancelar el [fecha]' = accion cancelar + fecha_actual_mencionada. "
    "Si dice 'reprogramar' o 'pasarlo a otro dia' o 'tengo clases' o 'no puedo a esa hora' = accion reprogramar. "
    "Si dice solo 'no voy a poder ir' o 'cancelo' sin fecha = accion cancelar."
)

JSON_BODY_3A = (
    '={{ JSON.stringify({model:"gpt-4o-mini", messages:[{role:"system",content:'
    + json.dumps(STEP3A_SYS)
    + '},{role:"user",content:"Mensaje del paciente: " + $json.trigger.text}], max_tokens:200, temperature:0.1, response_format:{type:"json_object"}}) }}'
)

step3a = {
    'parameters': {
        'method': 'POST',
        'url': 'https://api.openai.com/v1/chat/completions',
        'authentication': 'predefinedCredentialType',
        'nodeCredentialType': 'openAiApi',
        'sendBody': True,
        'specifyBody': 'json',
        'jsonBody': JSON_BODY_3A,
        'options': {}
    },
    'id': 'step3a', 'name': 'Step 3a: LLM Extract Intent',
    'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
    'position': [1440, 300],
    'credentials': {'openAiApi': {'id': OPENAI_CRED, 'name': 'OpenAi account'}},
    'continueOnFail': True, 'alwaysOutputData': True
}

STEP3B_CODE = """const llmResp = $input.first().json;
const prev = $('Step 2b: Filtrar Turnos Proximos').first().json;

let parsed = { accion: 'ambiguo', fecha_objetivo: null, hora_objetivo: null, fecha_actual_mencionada: null, razon: 'sin parse' };
try {
  const content = llmResp?.choices?.[0]?.message?.content || '{}';
  parsed = JSON.parse(content);
} catch (e) {
  parsed.razon = 'json parse fail: ' + String(e?.message || e);
}

return [{ json: {
  paciente: prev.paciente,
  trigger: prev.trigger,
  turnos_proximos: prev.turnos_proximos,
  count: prev.count,
  intent: parsed,
  step: 'intent_extracted'
}}];"""

step3b = {
    'parameters': {'jsCode': STEP3B_CODE},
    'id': 'step3b', 'name': 'Step 3b: Parse Intent',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [1640, 300]
}

for n in wf['nodes']:
    if n['name'] == 'Step 2b: Filtrar Turnos Proximos':
        n['parameters']['jsCode'] = NEW_2B

existing = {n['name'] for n in wf['nodes']}
if 'Step 3a: LLM Extract Intent' not in existing:
    wf['nodes'].append(step3a)
if 'Step 3b: Parse Intent' not in existing:
    wf['nodes'].append(step3b)

wf['connections']['Step 2b: Filtrar Turnos Proximos'] = {'main': [[{'node': 'Step 3a: LLM Extract Intent', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 3a: LLM Extract Intent'] = {'main': [[{'node': 'Step 3b: Parse Intent', 'type': 'main', 'index': 0}]]}

ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution', 'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone', 'executionOrder', 'callerPolicy', 'callerIds'}
put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
       'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', method='PUT', headers=HEADERS, data=json.dumps(put).encode()), timeout=30)
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}/activate', method='POST', headers=HEADERS), timeout=20)
print('Step 2b fixeado + Step 3 (LLM extract) agregado')
