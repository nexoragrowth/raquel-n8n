"""Fix: Step 4 maneja correctamente el caso paciente menciona fecha que NO matchea ningún turno.

Antes: si paciente decía "cancelo el [X]" y había UN solo turno (en otra fecha),
el bot cancelaba ese turno único — riesgo de cancelar equivocado.

Después: si paciente mencionó fecha_actual Y NO matchea con NINGÚN turno próximo,
pedir clarificación en lugar de asumir.
"""
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

NEW_STEP4_CODE = """// Identificar turno objetivo + decidir next step
const prev = $input.first().json;
const intent = prev.intent || {};
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

// Si paciente menciono fecha actual, verificar si matchea con algun turno
const fechaMencionada = intent.fecha_actual_mencionada;
const match = fechaMencionada ? turnos.find(t => t.fecha === fechaMencionada) : null;

// Caso especial: paciente menciono fecha pero NO matchea (proteger de cancelar equivocado)
if (fechaMencionada && !match) {
  return [{ json: {
    ...prev,
    decision: {
      siguiente_paso: 'preguntar_cual_turno',
      razon: 'fecha_mencionada_no_matchea_ningun_turno',
      turnos_para_ofrecer: turnos.slice(0, 5).map(t => ({ id: t.id, fecha: t.fecha, hora: t.hora_inicio }))
    }
  }}];
}

// Si matcheo con la fecha mencionada, usar ese turno
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

// Caso 2: UN solo turno proximo (sin fecha mencionada o ya manejado)
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
  return [{ json: {
    ...prev,
    turno_objetivo: turno,
    decision: {
      siguiente_paso: 'preguntar_intent',
      razon: 'intent_ambiguo_con_turno_unico'
    }
  }}];
}

// Caso 3: MULTIPLES turnos sin fecha mencionada -> preguntar
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

wf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', headers=HEADERS), timeout=20).read())

for n in wf['nodes']:
    if n['name'] == 'Step 4: Identificar Turno + Decision':
        n['parameters']['jsCode'] = NEW_STEP4_CODE
        break

ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution', 'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone', 'executionOrder', 'callerPolicy', 'callerIds'}
put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
       'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', method='PUT', headers=HEADERS, data=json.dumps(put).encode()), timeout=30)
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}/activate', method='POST', headers=HEADERS), timeout=20)
print('Step 4 fixeado: si fecha mencionada NO matchea ningun turno, NO cancela')
