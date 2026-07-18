"""Fix Step 3a: armar body LLM en Code node previo + HTTP Request lo lee como string."""
import json
import re
import urllib.request
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
OPENAI_CRED = 'nYujqfon7GGDnJUO'
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

wf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', headers=HEADERS), timeout=20).read())

# Inserto Step 3.0 (Prep LLM Body) ANTES de Step 3a
SYSTEM_PROMPT = (
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

PREP_CODE = (
    "const prev = $input.first().json;\n"
    "const text = prev.trigger?.text || '';\n"
    "const body = {\n"
    "  model: 'gpt-4o-mini',\n"
    "  messages: [\n"
    "    { role: 'system', content: " + json.dumps(SYSTEM_PROMPT) + " },\n"
    "    { role: 'user', content: 'Mensaje del paciente: ' + text }\n"
    "  ],\n"
    "  max_tokens: 200,\n"
    "  temperature: 0.1,\n"
    "  response_format: { type: 'json_object' }\n"
    "};\n"
    "return [{ json: { ...prev, openai_body: JSON.stringify(body) } }];"
)

step3_prep = {
    'parameters': {'jsCode': PREP_CODE},
    'id': 'step3-prep', 'name': 'Step 3.0: Prep LLM Body',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [1340, 300]
}

# Update Step 3a a usar el body preparado
for n in wf['nodes']:
    if n['name'] == 'Step 3a: LLM Extract Intent':
        n['parameters']['jsonBody'] = '={{ $json.openai_body }}'

# Insert prep node if missing
existing = {n['name'] for n in wf['nodes']}
if 'Step 3.0: Prep LLM Body' not in existing:
    wf['nodes'].append(step3_prep)

# Re-wire: Step 2b -> Step 3.0 -> Step 3a -> Step 3b
wf['connections']['Step 2b: Filtrar Turnos Proximos'] = {'main': [[{'node': 'Step 3.0: Prep LLM Body', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 3.0: Prep LLM Body'] = {'main': [[{'node': 'Step 3a: LLM Extract Intent', 'type': 'main', 'index': 0}]]}

ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution', 'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone', 'executionOrder', 'callerPolicy', 'callerIds'}
put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
       'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', method='PUT', headers=HEADERS, data=json.dumps(put).encode()), timeout=30)
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}/activate', method='POST', headers=HEADERS), timeout=20)
print('Step 3.0 (Prep LLM Body) insertado + Step 3a apunta a $json.openai_body')
