"""Step 3.5: Acceptance parser (LLM) cuando multi_turn_state=oferta_horarios.

Si el bot ya ofreció slots y el paciente respondió, este step usa gpt-4o-mini para:
- Determinar si el paciente está aceptando un slot
- Extraer fecha + hora del slot elegido
- Output: acceptance_intent = {accepts: bool, slot_chosen: {fecha, hora}|null, razon}

Pasos:
- Step 3.5a: Prep LLM body (Code) — solo arma si multi_turn_state aplica
- Step 3.5b: HTTP LLM call (skip implícito si body no se preparó)
- Step 3.5c: Parse response (Code)
"""
import json, re, urllib.request, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
OPENAI_CRED = 'nYujqfon7GGDnJUO'
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

SYS_ACCEPT = (
    "Sos un parser. El bot dental ofrecio horarios al paciente, y este respondio. "
    "Tu trabajo: determinar si el paciente acepta un slot ofrecido y cual. "
    "Responde SOLO JSON valido, formato exacto: "
    '{"accepts":true|false,"slot_chosen":{"fecha":"YYYY-MM-DD","hora_inicio":"HH:MM"}|null,"razon":"breve"}. '
    "Si paciente dice 'si'/'dale'/'ok' sin especificar slot Y solo se ofrecio UN slot, accepts=true con ese slot. "
    "Si se ofrecieron varios slots y paciente solo dice 'si', accepts=false (ambiguo, no se cual). "
    "Si paciente dice una hora especifica (ej '8:00', '15:10') o fecha, matcheala con uno de los slots ofrecidos. "
    "Si paciente rechaza ('no', 'otro dia', 'ninguno me sirve'), accepts=false slot_chosen=null. "
    "Si paciente pide otra cosa (cambio de tema), accepts=false slot_chosen=null."
)

STEP3_5A_CODE = (
    "const prev = $input.first().json;\n"
    "const state = prev.multi_turn_state || 'conversacion_nueva';\n"
    "// Si NO estamos en oferta_horarios, hacer pass-through (no llamar LLM)\n"
    "if (state !== 'oferta_horarios') {\n"
    "  return [{ json: { ...prev, _skip_acceptance: true } }];\n"
    "}\n"
    "const lastBot = prev.last_bot_msg || '';\n"
    "const text = prev.trigger?.text || '';\n"
    "const body = {\n"
    "  model: 'gpt-4o-mini',\n"
    "  messages: [\n"
    "    { role: 'system', content: " + json.dumps(SYS_ACCEPT) + " },\n"
    "    { role: 'user', content: 'Slots ofrecidos por el bot: ' + lastBot + '\\n\\nRespuesta del paciente: ' + text }\n"
    "  ],\n"
    "  max_tokens: 200,\n"
    "  temperature: 0.1,\n"
    "  response_format: { type: 'json_object' }\n"
    "};\n"
    "return [{ json: { ...prev, accept_openai_body: JSON.stringify(body), _skip_acceptance: false } }];"
)

step3_5a = {
    'parameters': {'jsCode': STEP3_5A_CODE},
    'id': 'step3-5a', 'name': 'Step 3.5a: Prep Acceptance LLM',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [1740, 300]
}

step3_5b_http = {
    'parameters': {
        'method': 'POST',
        'url': 'https://api.openai.com/v1/chat/completions',
        'authentication': 'predefinedCredentialType',
        'nodeCredentialType': 'openAiApi',
        'sendBody': True,
        'specifyBody': 'json',
        'jsonBody': '={{ $json.accept_openai_body || "{\\"skip\\":true}" }}',
        'options': {}
    },
    'id': 'step3-5b', 'name': 'Step 3.5b: LLM Acceptance',
    'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
    'position': [1940, 300],
    'credentials': {'openAiApi': {'id': OPENAI_CRED, 'name': 'OpenAi account'}},
    'continueOnFail': True, 'alwaysOutputData': True
}

STEP3_5C_CODE = (
    "const llmResp = $input.first().json;\n"
    "const prev = $('Step 3.5a: Prep Acceptance LLM').first().json;\n"
    "\n"
    "// Si skipeamos LLM (no era oferta_horarios), pasar accepts=null\n"
    "if (prev._skip_acceptance === true) {\n"
    "  return [{ json: { ...prev, acceptance_intent: { accepts: null, slot_chosen: null, razon: 'no_aplica' } } }];\n"
    "}\n"
    "\n"
    "let parsed = { accepts: false, slot_chosen: null, razon: 'sin parse' };\n"
    "try {\n"
    "  const content = llmResp?.choices?.[0]?.message?.content || '{}';\n"
    "  parsed = JSON.parse(content);\n"
    "} catch (e) { parsed.razon = 'parse fail: ' + String(e?.message || e); }\n"
    "\n"
    "return [{ json: { ...prev, acceptance_intent: parsed } }];"
)

step3_5c = {
    'parameters': {'jsCode': STEP3_5C_CODE},
    'id': 'step3-5c', 'name': 'Step 3.5c: Parse Acceptance',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [2140, 300]
}

# Step 5 modificado: agregar caso "paciente acepta slot"
NEW_STEP5_CODE = """// Decide accion ejecutable
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

// NUEVO Caso: paciente acepta slot ofrecido (multi-turn)
if (accept.accepts === true && accept.slot_chosen && accept.slot_chosen.fecha) {
  // Necesitamos saber CUAL turno cancelar. Si hay 1 solo proximo, ese. Sino, escalar.
  if (turnos.length === 0) {
    return [{ json: { ...prev, action_to_execute: 'reservar_solo', slot_a_reservar: accept.slot_chosen, mensaje_final: 'Listo, reservando el ' + fechaNatural(accept.slot_chosen.fecha) + ' a las ' + horaNatural(accept.slot_chosen.hora_inicio) + '.' }}];
  }
  // 1+ turno: cancelar el primero + reservar nuevo
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

// Paciente rechazo / ambiguo en oferta_horarios -> volver a ofrecer o pedir clarificacion
if (prev.multi_turn_state === 'oferta_horarios' && accept.accepts === false) {
  return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: 'Cual de los horarios que te pase te viene mejor? Sino, decime que dia y franja preferis y busco otros.' } }];
}

// Caso preguntar_cual_turno (existente)
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

return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: 'Vi su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + '. Lo querias cancelar o reprogramar?' } }];"""

wf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', headers=HEADERS), timeout=20).read())

existing = {n['name'] for n in wf['nodes']}
if 'Step 3.5a: Prep Acceptance LLM' not in existing:
    wf['nodes'].append(step3_5a)
if 'Step 3.5b: LLM Acceptance' not in existing:
    wf['nodes'].append(step3_5b_http)
if 'Step 3.5c: Parse Acceptance' not in existing:
    wf['nodes'].append(step3_5c)

# Update Step 5
for n in wf['nodes']:
    if n['name'] == 'Step 5: Decidir Accion Ejecutable':
        n['parameters']['jsCode'] = NEW_STEP5_CODE

# Re-wire: Step 3b -> Step 3.5a -> 3.5b -> 3.5c -> Step 4
wf['connections']['Step 3b: Parse Intent'] = {'main': [[{'node': 'Step 3.5a: Prep Acceptance LLM', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 3.5a: Prep Acceptance LLM'] = {'main': [[{'node': 'Step 3.5b: LLM Acceptance', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 3.5b: LLM Acceptance'] = {'main': [[{'node': 'Step 3.5c: Parse Acceptance', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 3.5c: Parse Acceptance'] = {'main': [[{'node': 'Step 4: Identificar Turno + Decision', 'type': 'main', 'index': 0}]]}

ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution', 'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone', 'executionOrder', 'callerPolicy', 'callerIds'}
put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
       'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', method='PUT', headers=HEADERS, data=json.dumps(put).encode()), timeout=30)
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}/activate', method='POST', headers=HEADERS), timeout=20)
print('Step 3.5 (a/b/c) agregado + Step 5 modificado')
