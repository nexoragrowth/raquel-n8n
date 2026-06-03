"""Fix Step 5: manejar preguntar_cual_turno con mensaje natural."""
import json, re, urllib.request, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

NEW_STEP5_CODE = """// Decide accion ejecutable
const prev = $input.first().json;
const dec = prev.decision || {};
const intent = prev.intent || {};
const turno = prev.turno_objetivo;
const turnos = prev.turnos_proximos || [];

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

// Caso preguntar_cual_turno: paciente menciono fecha que no matchea, o hay multiples turnos
if (dec.siguiente_paso === 'preguntar_cual_turno') {
  const fechaMencionada = intent.fecha_actual_mencionada;
  const turnosLista = turnos.slice(0, 5).map(t => fechaNatural(t.fecha) + ' a las ' + horaNatural(t.hora_inicio)).join(' / ');
  let mensaje;
  if (fechaMencionada && turnos.length === 1) {
    const t = turnos[0];
    mensaje = 'No veo turno tuyo el ' + fechaNatural(fechaMencionada) + '. Vi este: ' + fechaNatural(t.fecha) + ' a las ' + horaNatural(t.hora_inicio) + '. Era ese el que querias cancelar?';
  } else if (fechaMencionada) {
    mensaje = 'No veo turno tuyo el ' + fechaNatural(fechaMencionada) + '. Tenes estos turnos proximos: ' + turnosLista + '. Cual queres cancelar?';
  } else {
    mensaje = 'Tenes varios turnos proximos: ' + turnosLista + '. Cual queres cancelar?';
  }
  return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: mensaje } }];
}

// Caso escalar (real)
if (dec.siguiente_paso === 'escalar') {
  return [{ json: { ...prev, action_to_execute: 'escalar', mensaje_final: dec.canned || 'No veo turno activo. Le paso a la secretaria Iri.' } }];
}

if (!turno) {
  return [{ json: { ...prev, action_to_execute: 'escalar', mensaje_final: 'No veo turno activo. Le paso a la secretaria Iri.' } }];
}

// Cancelar directo
if (intent.accion === 'cancelar') {
  return [{ json: {
    ...prev,
    action_to_execute: 'cancelar_turno',
    cita_a_cancelar: turno.id,
    mensaje_final: 'Listo, su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + ' queda cancelado. Si quiere reprogramar avisame y le busco otro horario.'
  }}];
}

// Reprogramar con fecha objetivo
if (intent.accion === 'reprogramar' && intent.fecha_objetivo) {
  return [{ json: { ...prev, action_to_execute: 'buscar_horarios', fecha_objetivo: intent.fecha_objetivo, hora_objetivo: intent.hora_objetivo } }];
}

// Reprogramar sin fecha
if (intent.accion === 'reprogramar') {
  return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: 'Para reprogramar su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + ', que dia o franja le viene mejor? (manana / tarde / fecha concreta)' } }];
}

// Ambiguo
return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: 'Vi su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + '. Lo querias cancelar o reprogramar?' } }];"""

wf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', headers=HEADERS), timeout=20).read())
for n in wf['nodes']:
    if n['name'] == 'Step 5: Decidir Accion Ejecutable':
        n['parameters']['jsCode'] = NEW_STEP5_CODE
        break

ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution', 'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone', 'executionOrder', 'callerPolicy', 'callerIds'}
put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'], 'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', method='PUT', headers=HEADERS, data=json.dumps(put).encode()), timeout=30)
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}/activate', method='POST', headers=HEADERS), timeout=20)
print('Step 5 fixeado: maneja preguntar_cual_turno con mensaje natural')
