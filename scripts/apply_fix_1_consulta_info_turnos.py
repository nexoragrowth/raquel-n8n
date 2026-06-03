"""
Fix 1.1/1.2/1.3: consultas de INFO sobre turnos propios.

Casos:
- "Cuando es mi turno?" / "A que hora tengo el turno?" / "Que dia tengo turno?"
- "Tengo turno mañana?" / "Mañana es mi turno?"
- "Con que doctora tengo el turno?"

Cambios:
1. Step 3.0 LLM intent parser: agregar 'consultar_info' como accion posible.
2. Step 4: cuando intent.accion === 'consultar_info' -> decision responder_info
   con mensaje natural usando turno_objetivo si existe (info útil), o canned
   apropiado si no hay turnos.
3. Step 5: ya tiene branch responder_info (no se toca).
"""
import json
import re
import time
import urllib.request
from pathlib import Path

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
SUB_WID = '5cAWJxiWJ50hxEq3'
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}


STEP_3_0_NEW = r"""const prev = $input.first().json;
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
    { role: 'system', content: "Sos un parser de mensajes de pacientes sobre sus turnos dentales. Hoy es " + today + ". " + contextLine + " Tu tarea: extraer del mensaje del paciente la INTENT y campos relevantes. Responde SOLO con JSON valido, formato exacto: {\"accion\":\"cancelar\"|\"reprogramar\"|\"consultar_info\"|\"ambiguo\",\"fecha_objetivo\":\"YYYY-MM-DD\"|null,\"hora_objetivo\":\"HH:MM\"|null,\"fecha_actual_mencionada\":\"YYYY-MM-DD\"|null,\"info_solicitada\":\"cuando\"|\"donde\"|\"tratamiento\"|\"verificar_fecha\"|null,\"razon\":\"texto breve\"}. Reglas: (1) Si paciente dice 'cancelar el [fecha]' = cancelar + fecha_actual_mencionada. (2) Si dice 'reprogramar' o 'pasarlo a otro dia' o 'tengo clases' o 'no puedo a esa hora' = reprogramar. (3) Si dice 'cancelo' sin fecha = cancelar. (4) Si state=esperando_fecha, fecha mencionada es fecha_objetivo. (5) NUEVA REGLA - CONSULTA DE INFO: Si el paciente PREGUNTA sobre su turno sin querer accion, accion='consultar_info'. Ejemplos: 'tengo turno?' / 'cuando es mi turno?' / 'que dia tengo?' / 'a que hora?' / 'tengo turno manana?' / 'mi turno es presencial?' / 'que turno tengo?' -> accion='consultar_info'. Setea info_solicitada: 'cuando' (pregunta dia/hora del turno), 'donde' (pregunta direccion/lugar del turno), 'tratamiento' (pregunta tratamiento), 'verificar_fecha' (pregunta 'es el [fecha]?'). Para 'verificar_fecha', poner fecha_actual_mencionada con la fecha que pregunta. NO uses 'con_quien' como info_solicitada — la clinica es mono-doctora (Dra. Raquel) y esa pregunta debe rutearse afuera. Calcula año: si fecha mencionada ya pasó este año usa siguiente año. Nunca uses años anteriores." },
    { role: 'user', content: 'Mensaje del paciente: ' + text }
  ],
  max_tokens: 250,
  temperature: 0.1,
  response_format: { type: 'json_object' }
};
return [{ json: { ...prev, openai_body: JSON.stringify(body) } }];"""


STEP_4_NEW = r"""// Identificar turno objetivo + decidir next step
const prev = $input.first().json;
const intent = prev.intent || {};
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
  const m = String(hhmmss).match(/^(\d{1,2}):(\d{2})/);
  if (!m) return hhmmss;
  const h = parseInt(m[1], 10);
  const mm = m[2];
  const sufijo = h < 12 ? 'de la mañana' : (h < 19 ? 'de la tarde' : 'de la noche');
  return h + (mm !== '00' ? ':' + mm : '') + ' ' + sufijo;
}

// NUEVO: consultar_info — responder con info sin escalar
if (intent.accion === 'consultar_info') {
  if (turnos.length === 0) {
    return [{ json: {
      ...prev,
      decision: {
        siguiente_paso: 'responder_info',
        razon: 'consulta_info_sin_turnos_activos',
        canned: 'Por el momento no tenes turnos activos a tu nombre. Si queres agendar uno avisame y te lo coordino.'
      }
    }}];
  }

  const info = intent.info_solicitada || 'cuando';

  // Caso verificar_fecha: paciente pregunta "tengo turno [tal dia]?"
  if (info === 'verificar_fecha' && intent.fecha_actual_mencionada) {
    const match = turnos.find(t => t.fecha === intent.fecha_actual_mencionada);
    let canned;
    if (match) {
      canned = 'Si, tenes turno el ' + fechaNatural(match.fecha) + ' a las ' + horaNatural(match.hora_inicio) + '.';
    } else {
      const proxLista = turnos.slice(0, 3).map(t => fechaNatural(t.fecha) + ' a las ' + horaNatural(t.hora_inicio)).join(' / ');
      canned = 'No, no tenes turno el ' + fechaNatural(intent.fecha_actual_mencionada) + '. Tu proximo turno es: ' + proxLista + '.';
    }
    return [{ json: { ...prev, decision: { siguiente_paso: 'responder_info', razon: 'verificar_fecha', canned } } }];
  }

  // Caso cuando / con_quien / donde / tratamiento — todos con turno_objetivo (1+)
  const turnosStr = turnos.length === 1
    ? fechaNatural(turnos[0].fecha) + ' a las ' + horaNatural(turnos[0].hora_inicio)
    : turnos.slice(0, 3).map(t => fechaNatural(t.fecha) + ' a las ' + horaNatural(t.hora_inicio)).join(' / ');

  let canned;
  if (info === 'cuando') {
    canned = turnos.length === 1
      ? 'Tu proximo turno es el ' + turnosStr + '.'
      : 'Tenes ' + turnos.length + ' turnos proximos: ' + turnosStr + '.';
  } else if (info === 'donde') {
    canned = 'Tu turno es presencial en Balcarce 37, 2do piso, San Salvador de Jujuy. Fecha: ' + turnosStr + '.';
  } else if (info === 'tratamiento') {
    // No tenemos el campo de tratamiento por turno desde Dentalink en este flow.
    canned = 'Para ver el detalle del tratamiento de tu proximo turno (' + turnosStr + ') te paso a la secretaria Iri que tiene la ficha clinica.';
  } else {
    // Fallback consulta_info generica
    canned = turnos.length === 1
      ? 'Tu proximo turno es el ' + turnosStr + '.'
      : 'Tenes ' + turnos.length + ' turnos proximos: ' + turnosStr + '.';
  }
  return [{ json: { ...prev, decision: { siguiente_paso: 'responder_info', razon: 'consulta_info_turno', canned } } }];
}

// Caso 1: NO HAY turnos proximos
if (turnos.length === 0) {
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
  return [{ json: {
    ...prev,
    turno_objetivo: turno,
    decision: { siguiente_paso: 'preguntar_intent', razon: 'intent_ambiguo_con_turno_unico' }
  }}];
}

// Caso 3: MULTIPLES turnos sin fecha mencionada
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


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{SUB_WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/subwf_PRE_FIX_1_CONSULTA_INFO_{int(time.time())}.json').write_text(
    json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

patches = {
    'Step 3.0: Prep LLM Body': STEP_3_0_NEW,
    'Step 4: Identificar Turno + Decision': STEP_4_NEW,
}
for n in wf['nodes']:
    if n['name'] in patches:
        old_len = len(n['parameters'].get('jsCode', ''))
        n['parameters']['jsCode'] = patches[n['name']]
        print(f'patched [{n["name"]}]: {old_len} -> {len(n["parameters"]["jsCode"])}')

safe = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
http('PUT', f'/workflows/{SUB_WID}', safe)
print('PUT 200')

Path(f'workflows/history/subwf_POST_FIX_1_CONSULTA_INFO_{int(time.time())}.json').write_text(
    json.dumps(http('GET', f'/workflows/{SUB_WID}'), indent=2, ensure_ascii=False), encoding='utf-8')
print('backup POST OK')
