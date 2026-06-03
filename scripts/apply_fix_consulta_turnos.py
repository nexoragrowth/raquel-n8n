"""
Sub-WF CancelarReprogramar fixes:

1. Step 4: caso "0 turnos" ya no escala — responde con info (apto para consulta
   pura tipo "tengo algun turno?")

2. Step 5: cuando decision='escalar' por sin_turnos, mapear a 'responder_info'
   (no llamar al helper, solo responder).

3. Step 7: leer mensaje_final del Step 5 directo (no del HTTP output del helper
   que sobreescribe el contexto).

Bug observado: paciente preguntó "tengo algun turno?", bot escaló con "Le paso
a la secretaria." cuando debería responder "No tenés turnos activos. ¿Querés
agendar uno?".
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
SUB_WID = '5cAWJxiWJ50hxEq3'
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}


STEP_4_NEW = '''// Identificar turno objetivo + decidir next step
const prev = $input.first().json;
const intent = prev.intent || {};
const turnos = prev.turnos_proximos || [];

// Caso 1: NO HAY turnos proximos
if (turnos.length === 0) {
  // Si paciente queria accion (cancelar/reprogramar), responder amable sin escalar
  if (intent.accion === 'cancelar' || intent.accion === 'reprogramar') {
    return [{ json: {
      ...prev,
      decision: {
        siguiente_paso: 'responder_info',
        razon: 'paciente_sin_turnos_para_accion',
        canned: 'No te encuentro turnos activos en este momento. Si queres coordinar uno nuevo avisame y te lo paso a la secretaria Iri.'
      }
    }}];
  }
  // Consulta pura (intent ambiguo: "tengo algun turno?", "que turnos tengo?")
  return [{ json: {
    ...prev,
    decision: {
      siguiente_paso: 'responder_info',
      razon: 'consulta_turnos_sin_turnos_activos',
      canned: 'Por el momento no tenes turnos activos a tu nombre. Si queres agendar uno avisame y te lo coordino.'
    }
  }}];
}

// Si paciente menciono fecha actual, verificar si matchea con algun turno
const fechaMencionada = intent.fecha_actual_mencionada;
const match = fechaMencionada ? turnos.find(t => t.fecha === fechaMencionada) : null;

// Caso especial: paciente menciono fecha pero NO matchea
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

// Si matcheo con la fecha mencionada
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

// Caso 2: UN solo turno proximo
if (turnos.length === 1) {
  const turno = turnos[0];
  if (intent.accion === 'cancelar') {
    return [{ json: {
      ...prev,
      turno_objetivo: turno,
      decision: { siguiente_paso: 'confirmar_cancelacion', razon: 'turno_unico_proximo_a_cancelar' }
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
  // Intent ambiguo + turno unico: si paciente esta consultando "tengo algun turno?", responder con info
  return [{ json: {
    ...prev,
    turno_objetivo: turno,
    decision: { siguiente_paso: 'preguntar_intent', razon: 'intent_ambiguo_con_turno_unico' }
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
}}];'''


# Step 5: agregar branch responder_info ANTES del branch escalar
STEP_5_NEW = '''// Decide accion ejecutable
const prev = $input.first().json;
const dec = prev.decision || {};
const intent = prev.intent || {};
const turno = prev.turno_objetivo;
const turnos = prev.turnos_proximos || [];
const accept = prev.acceptance_intent || { accepts: null, slot_chosen: null };

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

// NUEVO: responder con info sin escalar
if (dec.siguiente_paso === 'responder_info') {
  return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: dec.canned || 'No tenes turnos activos en este momento.' } }];
}

// Paciente acepta slot ofrecido (multi-turn)
if (accept.accepts === true && accept.slot_chosen && accept.slot_chosen.fecha) {
  if (turnos.length === 0) {
    return [{ json: { ...prev, action_to_execute: 'reservar_solo', slot_a_reservar: accept.slot_chosen, mensaje_final: 'Listo, reservando el ' + fechaNatural(accept.slot_chosen.fecha) + ' a las ' + horaNatural(accept.slot_chosen.hora_inicio) + '.' }}];
  }
  const tCancelar = turnos[0];
  return [{ json: {
    ...prev,
    action_to_execute: 'reservar_y_cancelar',
    slot_a_reservar: accept.slot_chosen,
    cita_a_cancelar: tCancelar.id,
    cita_vieja_info: { fecha: tCancelar.fecha, hora: tCancelar.hora_inicio },
    mensaje_final: 'Listo, reprogramado: cancele el ' + fechaNatural(tCancelar.fecha) + ' a las ' + horaNatural(tCancelar.hora_inicio) + ' y te reserve el ' + fechaNatural(accept.slot_chosen.fecha) + ' a las ' + horaNatural(accept.slot_chosen.hora_inicio) + '. Cualquier consulta nos escribis.'
  }}];
}

if (prev.multi_turn_state === 'oferta_horarios' && accept.accepts === false) {
  return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: 'Cual de los horarios que te pase te viene mejor? Sino, decime que dia y franja preferis y busco otros.' } }];
}

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

if (dec.siguiente_paso === 'escalar') {
  return [{ json: { ...prev, action_to_execute: 'escalar', mensaje_final: dec.canned || 'No veo turno activo. Le paso a la secretaria Iri.' } }];
}

if (!turno) {
  return [{ json: { ...prev, action_to_execute: 'escalar', mensaje_final: 'No veo turno activo. Le paso a la secretaria Iri.' } }];
}

if (intent.accion === 'cancelar') {
  return [{ json: {
    ...prev,
    action_to_execute: 'cancelar_turno',
    cita_a_cancelar: turno.id,
    mensaje_final: 'Listo, su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + ' queda cancelado. Si quiere reprogramar avisame y le busco otro horario.'
  }}];
}

if (intent.accion === 'reprogramar' && intent.fecha_objetivo) {
  return [{ json: { ...prev, action_to_execute: 'buscar_horarios', fecha_objetivo: intent.fecha_objetivo, hora_objetivo: intent.hora_objetivo } }];
}

if (intent.accion === 'reprogramar') {
  return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: 'Para reprogramar su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + ', que dia o franja le viene mejor? (manana / tarde / fecha concreta)' } }];
}

return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: 'Vi su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + '. Lo querias cancelar o reprogramar?' } }];'''


# Step 7: leer mensaje_final del Step 5 directamente
STEP_7_NEW = '''// Consolidar mensaje final + side effects que el v6 tiene que aplicar
// Bug fix: leer mensaje_final del Step 5 directo (el HTTP del Step 6c
// sobreescribe el contexto, se pierde mensaje_final si solo usamos $input).
const fromStep5 = $('Step 5: Decidir Accion Ejecutable').first().json;
const prev = $input.first().json;
const mf = fromStep5.mensaje_final || prev.mensaje_final || 'Le paso a la secretaria.';
const action = fromStep5.action_to_execute || prev.action_to_execute;
return [{ json: {
  mensaje_final: mf,
  apply_label_humano: fromStep5.apply_label_humano === true || action === 'escalar',
  flow: 'cancelar_reprogramar',
  action_executed: action,
  paciente_id: fromStep5.paciente?.id || prev.paciente?.id || null,
  cita_id: fromStep5.cita_a_cancelar || prev.cita_a_cancelar || null,
  debug: {
    decision: fromStep5.decision,
    intent: fromStep5.intent,
    cancel_success: prev.cancel_success,
    slots_match: fromStep5.slots_match?.length || 0,
    slots_alternativos: fromStep5.slots_alternativos?.length || 0
  }
}}];'''


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{SUB_WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
pre = Path(f'workflows/history/subwf_PRE_CONSULTA_TURNOS_{int(time.time())}.json')
pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'backup PRE: {pre}')

patches = {
    'Step 4: Identificar Turno + Decision': STEP_4_NEW,
    'Step 5: Decidir Accion Ejecutable': STEP_5_NEW,
    'Step 7: Output Final': STEP_7_NEW,
}

for n in wf['nodes']:
    if n['name'] in patches:
        old_len = len(n['parameters'].get('jsCode', ''))
        n['parameters']['jsCode'] = patches[n['name']]
        new_len = len(n['parameters']['jsCode'])
        print(f'patched [{n["name"]}]: {old_len} -> {new_len} chars')

safe = {k: wf[k] for k in ('name', 'nodes', 'connections', 'settings') if k in wf}
http('PUT', f'/workflows/{SUB_WID}', safe)
print('PUT 200')

post = Path(f'workflows/history/subwf_POST_CONSULTA_TURNOS_{int(time.time())}.json')
after = http('GET', f'/workflows/{SUB_WID}')
post.write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'backup POST: {post}')
