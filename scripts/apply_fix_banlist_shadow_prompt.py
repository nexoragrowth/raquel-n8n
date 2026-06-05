"""Mejorar system prompt del Banlist Shadow Prep:
- Aclarar que [NO_REPLY] es silencio intencional -> ALLOW
- Aclarar que mensajes vacios o tokens internos no son output al paciente
"""
import os, sys, json, requests
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

NEW_JS = """// Banlist Shadow - Prep (gpt-5-nano)
// Arma payload para OpenAI nano. Logueamos pero NO actuamos.
const prev = $input.first().json;
const banlistResult = prev || {};
const originalOutput = (banlistResult.output_original || banlistResult.output || '').toString();
const regexDecision = banlistResult.banlist_action || (banlistResult.escalated ? 'BLOCK' : 'ALLOW');
const regexRazon = banlistResult.banlist_reason || banlistResult.why || '(sin razon regex)';

let pacienteMsg = '';
let phone = '';
try {
  pacienteMsg = ($('Preparar Mensaje Final').first().json.text || '').toString();
  phone = ($('Preparar Mensaje Final').first().json.phone || '').toString();
} catch(e) {}

const today = new Date().toISOString().slice(0, 10);

const systemPrompt = `Sos un validador de seguridad para los mensajes que un bot de WhatsApp de una clinica odontologica esta por enviar a un paciente real.

Tu tarea: leer el OUTPUT que el bot va a mandar + el MENSAJE del paciente que lo provoco, y decidir si el bot puede mandarlo o si hay que bloquearlo.

CASOS ESPECIALES (siempre ALLOW, NO son output al paciente):
- "[NO_REPLY]" exacto = silencio intencional del bot (no envia nada). ALLOW.
- output vacio o "" = bot decidio no responder. ALLOW.
- "[CONTEXTO ...]" o tokens internos entre corchetes = senal interna, no llega al paciente. ALLOW.

REGLAS DURAS (si el output infringe alguna, BLOCK):
1. NO debe invitar al paciente a venir ahora ("venite", "vengan", "los esperamos", "salgan ya", "dirijase al consultorio", "acerquese ahora", parafrasis similares).
2. NO debe dar instrucciones operativas/medicas ("guarda la pieza", "toma X", "aplica Y", "enjuaga con Z").
3. NO debe dar diagnostico ni opinion emocional ("no te preocupes", "no es nada grave", "que macana").
4. NO debe dar la direccion (Balcarce 37) como confirmacion de cita, EXCEPTO si el paciente la pidio explicitamente.

Si el output cumple TODO o cae en casos especiales -> ALLOW. Si infringe -> BLOCK + razon corta.

Responde SOLO JSON: {"decision":"ALLOW"|"BLOCK","razon":"breve","reemplazo":"opcional canned"}.
Hoy es ${today}.`;

const userPrompt = `MENSAJE DEL PACIENTE: ${pacienteMsg}

OUTPUT QUE EL BOT VA A ENVIAR:
${originalOutput}

ALLOW o BLOCK?`;

const body = {
  model: 'gpt-5-nano',
  messages: [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt }
  ],
  max_completion_tokens: 400,
  reasoning_effort: 'minimal',
  response_format: { type: 'json_object' }
};

return [{ json: {
  ...prev,
  shadow_openai_body: JSON.stringify(body),
  shadow_input_paciente: pacienteMsg,
  shadow_input_phone: phone,
  shadow_input_output: originalOutput,
  shadow_regex_decision: regexDecision,
  shadow_regex_razon: regexRazon,
}}];
"""

wf = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
n = next((x for x in wf["nodes"] if x["name"] == "Banlist Shadow - Prep"), None)
if not n: print("!! not found"); sys.exit(2)
n["parameters"]["jsCode"] = NEW_JS

allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution","executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": settings, "staticData": wf.get("staticData")}
r = requests.put(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, json=body, timeout=40)
print(f"PUT {r.status_code}")
