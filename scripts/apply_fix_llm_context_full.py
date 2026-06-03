"""
Fix correcto: pasar al Step 3 LLM los últimos N mensajes de la conversacion
(no solo last_bot_msg + multi_turn_state enum). El LLM razona con contexto real.

Cambios:
1. Step 0b: armar `conversation_history` string con los últimos 5 turnos formateados.
2. Step 3.0: usar `conversation_history` como contexto del LLM system prompt.
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


STEP_0B_NEW = r'''// Detect multi-turn state from last bot message in n8n_chat_histories
const msgs = $input.all().map(i => i.json);
const trigger = $('When called by v6').first().json;

const ROUTER_LABELS = new Set([
  'cancelar_o_reprogramar', 'confirmar', 'agendar', 'urgencia',
  'consulta_general', 'general', 'pago', 'derivar', 'silencio', 'no_reply',
  'cancelar', 'reprogramar'
]);

let lastBotMsg = null;
let lastUserMsg = null;
// NUEVO: armar conversation_history con los ultimos 10 mensajes utiles
// (filtrando labels del Router). Formato: "ai: ... / user: ... / ai: ..."
const historyPairs = [];
for (const m of msgs) {
  const msgJson = typeof m.message === 'string' ? JSON.parse(m.message) : m.message;
  if (!msgJson) continue;
  const type = msgJson.type;
  const content = msgJson.content || msgJson?.data?.content || msgJson?.kwargs?.content || '';
  const trimmed = String(content).trim().toLowerCase();
  if (type === 'ai' && ROUTER_LABELS.has(trimmed)) continue;
  if (type === 'ai' && !lastBotMsg) lastBotMsg = String(content);
  if (type === 'human' && !lastUserMsg) lastUserMsg = String(content);
  // Add to history (most recent first)
  if (historyPairs.length < 10) {
    historyPairs.push({ role: type === 'ai' ? 'bot' : 'paciente', content: String(content).slice(0, 300) });
  }
}

// Reverse para tener cronologico (oldest first)
historyPairs.reverse();
const conversation_history = historyPairs.map(h => h.role + ': ' + h.content).join('\n');

const lower = (lastBotMsg || '').toLowerCase();

let multi_turn_state = 'conversacion_nueva';
if (/te ofrezco|te puedo ofrecer|tengo disponible|cual confirma|cual prefiere/i.test(lower)) {
  multi_turn_state = 'oferta_horarios';
} else if (/que dia.*viene mejor|para reprogramar.*que/i.test(lower)) {
  multi_turn_state = 'esperando_fecha';
} else if (/te confirmo.*cancelar/i.test(lower)) {
  multi_turn_state = 'esperando_confirmacion_cancelacion';
} else if (/queda cancelado/i.test(lower)) {
  multi_turn_state = 'cancelacion_ejecutada';
} else if (/era ese el que querias cancelar|vi este.*era ese|no veo turno tuyo.*vi este/i.test(lower)) {
  multi_turn_state = 'esperando_confirmacion_clarificacion';
}

return [{ json: {
  ...trigger,
  multi_turn_state,
  last_bot_msg: (lastBotMsg || '').slice(0, 300),
  last_user_msg: (lastUserMsg || '').slice(0, 200),
  conversation_history
}}];
'''


STEP_3_0_NEW = r'''const prev = $input.first().json;
const text = prev.trigger?.text || '';
const state = prev.trigger?.multi_turn_state || 'conversacion_nueva';
const lastBot = prev.trigger?.last_bot_msg || '';
const convHistory = prev.trigger?.conversation_history || '';
const today = new Date().toISOString().slice(0,10);

// Contexto conversacional COMPLETO al LLM. Que razone como un humano,
// no como un enum hardcoded.
const conversationContext = convHistory
  ? "HISTORIAL DE CONVERSACION RECIENTE (mas reciente abajo):\n" + convHistory + "\n\nEl mensaje del paciente que tenes que parsear AHORA es: \"" + text + "\". Razona con el historial: si el bot acaba de preguntar algo y el paciente responde con palabra corta (si, no, ese, eso, dale), conecta los puntos. Ejemplos: bot dice 'Era ese el turno del [fecha]?' + paciente 'si' -> accion=cancelar + fecha_actual_mencionada=fecha. Bot ofrece slots + paciente 'el de las X' -> accion=reprogramar (Step 3.5 captura aceptacion). Bot 'que dia preferis?' + paciente da fecha -> esa fecha es fecha_objetivo + accion=reprogramar. No respondas en base solo al mensaje del paciente: tene en cuenta el flujo completo de la conversacion."
  : "";

const body = {
  model: 'gpt-4o-mini',
  messages: [
    { role: 'system', content: "Sos un parser de mensajes de pacientes sobre sus turnos dentales. Hoy es " + today + ". " + conversationContext + " Tu tarea: extraer del mensaje del paciente (en contexto del historial conversacional) la INTENT y campos relevantes. Responde SOLO con JSON valido, formato exacto: {\"accion\":\"cancelar\"|\"reprogramar\"|\"consultar_info\"|\"ambiguo\",\"fecha_objetivo\":\"YYYY-MM-DD\"|null,\"hora_objetivo\":\"HH:MM\"|null,\"fecha_actual_mencionada\":\"YYYY-MM-DD\"|null,\"info_solicitada\":\"cuando\"|\"donde\"|\"tratamiento\"|\"verificar_fecha\"|null,\"razon\":\"texto breve\"}. Reglas: (1) Si paciente dice 'cancelar el [fecha]' = cancelar + fecha_actual_mencionada. (2) Si dice 'reprogramar' o 'pasarlo a otro dia' o 'tengo clases' = reprogramar. (3) Si dice 'cancelo' sin fecha = cancelar (turno objetivo se decide despues en base a turnos activos). (4) CONSULTA DE INFO: si paciente PREGUNTA sin querer accion ('tengo turno?', 'cuando es?', 'a que hora?') -> accion='consultar_info'. (5) IMPORTANTE: si el historial muestra que el bot pregunto algo y el paciente responde con palabra corta afirmativa/negativa (si/no/ese/eso), la accion es la que el bot estaba preguntando confirmar. No respondas 'ambiguo' si el historial deja claro a que se refiere el paciente. NO uses con_quien (clinica mono-doctora). Calcula año: si fecha mencionada ya paso este año usa siguiente año." },
    { role: 'user', content: 'Mensaje del paciente: ' + text }
  ],
  max_tokens: 250,
  temperature: 0.1,
  response_format: { type: 'json_object' }
};
return [{ json: { ...prev, openai_body: JSON.stringify(body) } }];
'''


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{SUB_WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/subwf_PRE_LLM_CONTEXT_FULL_{int(time.time())}.json').write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

n0b = next(n for n in wf['nodes'] if n['name'] == 'Step 0b: Detect Multi-Turn State')
n0b['parameters']['jsCode'] = STEP_0B_NEW
print(f'Step 0b: ahora arma conversation_history con ultimos 10 mensajes')

n30 = next(n for n in wf['nodes'] if n['name'] == 'Step 3.0: Prep LLM Body')
n30['parameters']['jsCode'] = STEP_3_0_NEW
print(f'Step 3.0: ahora usa conversation_history en system prompt')

ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution','saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder','callerPolicy','callerIds'}
safe = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED}
http('PUT', f'/workflows/{SUB_WID}', safe)
print('PUT 200')

Path(f'workflows/history/subwf_POST_LLM_CONTEXT_FULL_{int(time.time())}.json').write_text(json.dumps(http('GET', f'/workflows/{SUB_WID}'), indent=2, ensure_ascii=False), encoding='utf-8')
print('backup POST OK')
