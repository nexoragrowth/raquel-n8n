"""Steps 5-7: Switch + Acciones (cancelar directo, ofrecer horarios, canned) + return final."""
import json
import re
import urllib.request
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
DT_CRED = 'TwN6eBWsydjMdsCM'
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

wf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', headers=HEADERS), timeout=20).read())

# ===========================================================================
# Step 5: Code que decide la accion FINAL (cancelar directo o devolver canned)
# Estrategia v1 (sin multi-turn complejo):
# - Si accion=cancelar Y hay turno_objetivo Y (fecha mencionada O turno unico): CANCELAR DIRECTO
# - Si accion=reprogramar Y hay fecha_objetivo: BUSCAR HORARIOS (Step 6) y OFRECER
# - Si accion=reprogramar SIN fecha_objetivo: pedir fecha
# - Si accion=ambigua: pedir clarificacion
# - Si no hay turno: escalar
# ===========================================================================
STEP5_CODE = """// Decide accion ejecutable
const prev = $input.first().json;
const dec = prev.decision || {};
const intent = prev.intent || {};
const turno = prev.turno_objetivo;

// Mapeo fecha YYYY-MM-DD -> texto natural
function fechaNatural(yyyyMmDd) {
  if (!yyyyMmDd) return '';
  const dias = ['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];
  const meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
  const d = new Date(yyyyMmDd + 'T00:00:00');
  if (isNaN(d.getTime())) return yyyyMmDd;
  return dias[d.getDay()] + ' ' + d.getDate() + ' de ' + meses[d.getMonth()];
}
function horaNatural(hhmmss) {
  if (!hhmmss) return '';
  const m = String(hhmmss).match(/^(\\d{1,2}):(\\d{2})/);
  if (!m) return hhmmss;
  const h = parseInt(m[1], 10);
  const mm = m[2];
  const sufijo = h < 12 ? 'de la mañana' : (h < 19 ? 'de la tarde' : 'de la noche');
  return h + (mm !== '00' ? ':' + mm : '') + ' ' + sufijo;
}

// Caso A: escalar
if (dec.siguiente_paso === 'escalar' || !turno) {
  return [{ json: {
    ...prev,
    action_to_execute: 'escalar',
    mensaje_final: dec.canned || 'No veo turno activo a tu nombre. Le paso a la secretaria Iri.'
  }}];
}

// Caso B: cancelar DIRECTO (paciente fue claro)
if (intent.accion === 'cancelar') {
  return [{ json: {
    ...prev,
    action_to_execute: 'cancelar_turno',
    cita_a_cancelar: turno.id,
    mensaje_final: 'Listo, su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + ' queda cancelado. Si quiere reprogramar avisame y le busco otro horario.'
  }}];
}

// Caso C: reprogramar con fecha objetivo -> buscar horarios
if (intent.accion === 'reprogramar' && intent.fecha_objetivo) {
  return [{ json: {
    ...prev,
    action_to_execute: 'buscar_horarios',
    fecha_objetivo: intent.fecha_objetivo,
    hora_objetivo: intent.hora_objetivo
  }}];
}

// Caso D: reprogramar sin fecha
if (intent.accion === 'reprogramar') {
  return [{ json: {
    ...prev,
    action_to_execute: 'ninguna',
    mensaje_final: 'Para reprogramar su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + ', que dia o franja le viene mejor? (manana / tarde / fecha concreta)'
  }}];
}

// Caso E: ambiguo
return [{ json: {
  ...prev,
  action_to_execute: 'ninguna',
  mensaje_final: 'Vi su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + '. Lo querias cancelar o reprogramar?'
}}];"""

step5 = {
    'parameters': {'jsCode': STEP5_CODE},
    'id': 'step5', 'name': 'Step 5: Decidir Accion Ejecutable',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [2040, 300]
}

# Switch: segun action_to_execute
step6_switch = {
    'parameters': {
        'rules': {
            'values': [
                {'conditions': {'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict'},
                  'conditions': [{'leftValue': '={{ $json.action_to_execute }}', 'rightValue': 'cancelar_turno', 'operator': {'type': 'string', 'operation': 'equals'}}],
                  'combinator': 'and'},
                  'renameOutput': True, 'outputKey': 'cancelar'},
                {'conditions': {'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict'},
                  'conditions': [{'leftValue': '={{ $json.action_to_execute }}', 'rightValue': 'buscar_horarios', 'operator': {'type': 'string', 'operation': 'equals'}}],
                  'combinator': 'and'},
                  'renameOutput': True, 'outputKey': 'buscar_horarios'},
                {'conditions': {'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict'},
                  'conditions': [{'leftValue': '={{ $json.action_to_execute }}', 'rightValue': 'escalar', 'operator': {'type': 'string', 'operation': 'equals'}}],
                  'combinator': 'and'},
                  'renameOutput': True, 'outputKey': 'escalar'},
            ],
        },
        'options': {'fallbackOutput': 'extra', 'renameFallbackOutput': 'sin_accion'}
    },
    'id': 'step6-switch', 'name': 'Step 6: Switch por Accion',
    'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
    'position': [2240, 300]
}

# Step 6a: HTTP PUT cancelar_turno (id_estado=1)
step6a = {
    'parameters': {
        'method': 'PUT',
        'url': '={{ "https://api.dentalink.healthatom.com/api/v1/citas/" + $json.cita_a_cancelar }}',
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpHeaderAuth',
        'sendBody': True,
        'specifyBody': 'json',
        'jsonBody': '={{ JSON.stringify({id_estado: 1}) }}',
        'options': {}
    },
    'id': 'step6a', 'name': 'Step 6a: Cancelar en Dentalink',
    'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
    'position': [2440, 100],
    'credentials': {'httpHeaderAuth': {'id': DT_CRED, 'name': 'Header Auth account 3'}},
    'continueOnFail': True, 'alwaysOutputData': True
}

# Step 6a-out: consolidar resultado de cancelar
STEP6A_OUT_CODE = """const cancelResp = $input.first().json;
const prev = $('Step 5: Decidir Accion Ejecutable').first().json;

const success = cancelResp?.data?.id_estado === 1 || (Array.isArray(cancelResp) && cancelResp[0]?.data?.id_estado === 1);

return [{ json: {
  ...prev,
  cancel_success: success,
  cancel_raw: cancelResp,
  mensaje_final: success ? prev.mensaje_final : 'No pude cancelar el turno en el sistema. Le paso a la secretaria Iri para que lo coordine.',
  apply_label_humano: !success
}}];"""

step6a_out = {
    'parameters': {'jsCode': STEP6A_OUT_CODE},
    'id': 'step6a-out', 'name': 'Step 6a-out: Resultado Cancelar',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [2640, 100]
}

# Step 6b: Buscar Horarios - Prep query
STEP6B_PREP_CODE = """const prev = $input.first().json;
const q = JSON.stringify({id_sucursal:{eq:1},fecha:{eq:prev.fecha_objetivo},duracion:{eq:40},id_dentista:{eq:1}});
return [{ json: { ...prev, q_horarios: q } }];"""

step6b_prep = {
    'parameters': {'jsCode': STEP6B_PREP_CODE},
    'id': 'step6b-prep', 'name': 'Step 6b-prep: Prep Query Horarios',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [2440, 300]
}

step6b_http = {
    'parameters': {
        'method': 'GET',
        'url': 'https://api.dentalink.healthatom.com/api/v1/agendas/',
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpHeaderAuth',
        'sendQuery': True,
        'queryParameters': {'parameters': [{'name': 'q', 'value': '={{ $json.q_horarios }}'}]},
        'options': {}
    },
    'id': 'step6b-http', 'name': 'Step 6b: GET Agendas',
    'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
    'position': [2640, 300],
    'credentials': {'httpHeaderAuth': {'id': DT_CRED, 'name': 'Header Auth account 3'}},
    'continueOnFail': True, 'alwaysOutputData': True
}

# Step 6b-out: filtrar slots por fecha objetivo + ofrecer
STEP6B_OUT_CODE = """const horariosRaw = $input.first().json;
const prev = $('Step 6b-prep: Prep Query Horarios').first().json;
const fechaObjetivo = prev.fecha_objetivo;
const horaObjetivo = prev.hora_objetivo;

let slots = [];
if (Array.isArray(horariosRaw)) slots = horariosRaw[0]?.data || [];
else slots = horariosRaw?.data || [];

// API devuelve DD/MM/YYYY, convertir a YYYY-MM-DD para comparar
function ddmm_to_iso(s) {
  if (!s) return '';
  const m = String(s).match(/^(\\d{2})\\/(\\d{2})\\/(\\d{4})$/);
  if (!m) return s;
  return m[3] + '-' + m[2] + '-' + m[1];
}

const slotsIso = slots.map(s => ({...s, fecha_iso: ddmm_to_iso(s.fecha)}));
const matchExacto = slotsIso.find(s => s.fecha_iso === fechaObjetivo);
const matchesMismaFecha = slotsIso.filter(s => s.fecha_iso === fechaObjetivo);
const proximosSinMatch = slotsIso.slice(0, 6);

function fechaNatural(yyyyMmDd) {
  if (!yyyyMmDd) return '';
  const dias = ['domingo','lunes','martes','miercoles','jueves','viernes','sabado'];
  const meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
  const d = new Date(yyyyMmDd + 'T00:00:00');
  if (isNaN(d.getTime())) return yyyyMmDd;
  return dias[d.getDay()] + ' ' + d.getDate() + ' de ' + meses[d.getMonth()];
}
function horaNatural(hhmmss) {
  if (!hhmmss) return '';
  const m = String(hhmmss).match(/^(\\d{1,2}):(\\d{2})/);
  if (!m) return hhmmss;
  const h = parseInt(m[1], 10);
  const mm = m[2];
  return h + (mm !== '00' ? ':' + mm : '') + (h < 12 ? ' de la mañana' : ' de la tarde');
}

let mensaje;
if (matchesMismaFecha.length > 0) {
  const opts = matchesMismaFecha.slice(0, 3).map(s => horaNatural(s.hora_inicio)).join(' / ');
  mensaje = 'Para el ' + fechaNatural(fechaObjetivo) + ' tengo disponible: ' + opts + '. Cual confirma?';
} else if (proximosSinMatch.length > 0) {
  const opts = proximosSinMatch.slice(0, 3).map(s => fechaNatural(s.fecha_iso) + ' a las ' + horaNatural(s.hora_inicio)).join(' / ');
  mensaje = 'Para el ' + fechaNatural(fechaObjetivo) + ' no tengo turnos disponibles. Te puedo ofrecer: ' + opts + '. Te sirve alguno?';
} else {
  mensaje = 'No tengo turnos disponibles en las proximas fechas. Le paso a la secretaria Iri para coordinar.';
}

return [{ json: {
  ...prev,
  slots_match: matchesMismaFecha,
  slots_alternativos: proximosSinMatch,
  mensaje_final: mensaje,
  apply_label_humano: matchesMismaFecha.length === 0 && proximosSinMatch.length === 0
}}];"""

step6b_out = {
    'parameters': {'jsCode': STEP6B_OUT_CODE},
    'id': 'step6b-out', 'name': 'Step 6b-out: Ofrecer Slots',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [2840, 300]
}

# Step 6c: escalar via helper notify-grupo
STEP6C_PREP_CODE = """const prev = $input.first().json;
const trigger = prev.trigger || {};
const text = trigger.text || '';
const phone = trigger.phone || '';
const resumen = '[CancelarReprogramar] phone ' + phone + ', mensaje: ' + text + '. Razon: ' + (prev.decision?.razon || 'sin razon');
return [{ json: { ...prev, escalate_body: { text: resumen, phone } } }];"""

step6c_prep = {
    'parameters': {'jsCode': STEP6C_PREP_CODE},
    'id': 'step6c-prep', 'name': 'Step 6c-prep: Prep Escalado',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [2440, 500]
}

step6c_http = {
    'parameters': {
        'method': 'POST',
        'url': 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
        'sendBody': True,
        'specifyBody': 'json',
        'jsonBody': '={{ JSON.stringify($json.escalate_body) }}',
        'options': {}
    },
    'id': 'step6c-http', 'name': 'Step 6c: POST Helper',
    'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
    'position': [2640, 500],
    'continueOnFail': True, 'alwaysOutputData': True
}

# Step 7: consolidar output final - lo que se devuelve al v6
STEP7_CODE = """// Consolidar mensaje final + side effects que el v6 tiene que aplicar
const prev = $input.first().json;
return [{ json: {
  mensaje_final: prev.mensaje_final || 'Le paso a la secretaria.',
  apply_label_humano: prev.apply_label_humano === true || prev.action_to_execute === 'escalar',
  flow: 'cancelar_reprogramar',
  action_executed: prev.action_to_execute,
  paciente_id: prev.paciente?.id || null,
  cita_id: prev.cita_a_cancelar || null,
  debug: {
    decision: prev.decision,
    intent: prev.intent,
    cancel_success: prev.cancel_success,
    slots_match: prev.slots_match?.length || 0,
    slots_alternativos: prev.slots_alternativos?.length || 0
  }
}}];"""

step7 = {
    'parameters': {'jsCode': STEP7_CODE},
    'id': 'step7', 'name': 'Step 7: Output Final',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [3040, 300]
}

# Agregar todos los nodos
new_nodes = [step5, step6_switch, step6a, step6a_out, step6b_prep, step6b_http, step6b_out, step6c_prep, step6c_http, step7]
existing = {n['name'] for n in wf['nodes']}
for n in new_nodes:
    if n['name'] not in existing:
        wf['nodes'].append(n)

# Conexiones
wf['connections']['Step 4: Identificar Turno + Decision'] = {'main': [[{'node': 'Step 5: Decidir Accion Ejecutable', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 5: Decidir Accion Ejecutable'] = {'main': [[{'node': 'Step 6: Switch por Accion', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6: Switch por Accion'] = {'main': [
    [{'node': 'Step 6a: Cancelar en Dentalink', 'type': 'main', 'index': 0}],   # cancelar
    [{'node': 'Step 6b-prep: Prep Query Horarios', 'type': 'main', 'index': 0}],  # buscar_horarios
    [{'node': 'Step 6c-prep: Prep Escalado', 'type': 'main', 'index': 0}],         # escalar
    [{'node': 'Step 7: Output Final', 'type': 'main', 'index': 0}],                # fallback (sin_accion)
]}
wf['connections']['Step 6a: Cancelar en Dentalink'] = {'main': [[{'node': 'Step 6a-out: Resultado Cancelar', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6a-out: Resultado Cancelar'] = {'main': [[{'node': 'Step 7: Output Final', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6b-prep: Prep Query Horarios'] = {'main': [[{'node': 'Step 6b: GET Agendas', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6b: GET Agendas'] = {'main': [[{'node': 'Step 6b-out: Ofrecer Slots', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6b-out: Ofrecer Slots'] = {'main': [[{'node': 'Step 7: Output Final', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6c-prep: Prep Escalado'] = {'main': [[{'node': 'Step 6c: POST Helper', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6c: POST Helper'] = {'main': [[{'node': 'Step 7: Output Final', 'type': 'main', 'index': 0}]]}

ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution', 'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone', 'executionOrder', 'callerPolicy', 'callerIds'}
put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
       'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', method='PUT', headers=HEADERS, data=json.dumps(put).encode()), timeout=30)
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}/activate', method='POST', headers=HEADERS), timeout=20)
print('Steps 5-7 agregados (Switch, cancelar directo, buscar horarios + ofrecer, escalar, output final)')
