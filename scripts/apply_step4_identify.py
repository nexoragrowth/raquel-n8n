"""Step 4: Identificar turno objetivo + decidir siguiente accion."""
import json
import re
import urllib.request
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

wf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', headers=HEADERS), timeout=20).read())

STEP4_CODE = """// Identificar turno objetivo + decidir next step
const prev = $input.first().json;
const intent = prev.intent;
const turnos = prev.turnos_proximos || [];

// Caso 1: NO HAY turnos proximos
if (turnos.length === 0) {
  return [{ json: {
    ...prev,
    decision: {
      siguiente_paso: 'escalar',
      razon: 'paciente_sin_turnos_proximos',
      canned: 'No veo ningun turno activo a tu nombre. Le paso a la secretaria Iri para que lo coordine.'
    }
  }}];
}

// Caso 2: UN solo turno proximo
if (turnos.length === 1) {
  const turno = turnos[0];
  if (intent.accion === 'cancelar') {
    return [{ json: {
      ...prev,
      turno_objetivo: turno,
      decision: {
        siguiente_paso: 'confirmar_cancelacion',
        razon: 'turno_unico_proximo_a_cancelar'
      }
    }}];
  }
  if (intent.accion === 'reprogramar') {
    return [{ json: {
      ...prev,
      turno_objetivo: turno,
      decision: {
        siguiente_paso: intent.fecha_objetivo ? 'buscar_horarios_objetivo' : 'pedir_fecha_objetivo',
        razon: intent.fecha_objetivo ? 'reprogramar_con_fecha_propuesta' : 'reprogramar_sin_fecha'
      }
    }}];
  }
  // intent ambiguo con 1 turno -> preguntar
  return [{ json: {
    ...prev,
    turno_objetivo: turno,
    decision: {
      siguiente_paso: 'preguntar_intent',
      razon: 'intent_ambiguo_con_turno_unico'
    }
  }}];
}

// Caso 3: MULTIPLES turnos
// Si paciente menciono fecha_actual, intentar matchear
if (intent.fecha_actual_mencionada) {
  const match = turnos.find(t => t.fecha === intent.fecha_actual_mencionada);
  if (match) {
    return [{ json: {
      ...prev,
      turno_objetivo: match,
      decision: {
        siguiente_paso: intent.accion === 'cancelar' ? 'confirmar_cancelacion' :
                        (intent.accion === 'reprogramar' ?
                          (intent.fecha_objetivo ? 'buscar_horarios_objetivo' : 'pedir_fecha_objetivo')
                          : 'preguntar_intent'),
        razon: 'turno_matched_por_fecha_mencionada'
      }
    }}];
  }
}

// Multiples turnos sin matching claro -> preguntar cual
return [{ json: {
  ...prev,
  decision: {
    siguiente_paso: 'preguntar_cual_turno',
    razon: 'multiples_turnos_proximos_sin_match',
    turnos_para_ofrecer: turnos.slice(0, 5).map(t => ({
      id: t.id, fecha: t.fecha, hora: t.hora_inicio
    }))
  }
}}];"""

step4 = {
    'parameters': {'jsCode': STEP4_CODE},
    'id': 'step4', 'name': 'Step 4: Identificar Turno + Decision',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [1840, 300]
}

existing = {n['name'] for n in wf['nodes']}
if 'Step 4: Identificar Turno + Decision' not in existing:
    wf['nodes'].append(step4)

wf['connections']['Step 3b: Parse Intent'] = {'main': [[{'node': 'Step 4: Identificar Turno + Decision', 'type': 'main', 'index': 0}]]}

ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution', 'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone', 'executionOrder', 'callerPolicy', 'callerIds'}
put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
       'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', method='PUT', headers=HEADERS, data=json.dumps(put).encode()), timeout=30)
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}/activate', method='POST', headers=HEADERS), timeout=20)
print('Step 4 agregado')
