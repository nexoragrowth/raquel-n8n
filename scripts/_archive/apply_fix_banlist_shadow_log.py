"""Fix LOG_JS del Banlist Shadow Log node:
Lee shadow_* desde Prep, no desde input directo (que es del LLM).
"""
import os, sys, json, requests
from pathlib import Path
from dotenv import load_dotenv
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

NEW_JS = """// Banlist Shadow - Log
// Parsea respuesta del LLM nano + loguea comparacion regex vs agent.
// Devuelve passthrough (no toca el flujo principal).
const llmResp = $input.first().json;
const prepData = $('Banlist Shadow - Prep').first().json || {};
let agentDecision = 'ERROR';
let agentRazon = '';
let agentReemplazo = '';

try {
  const choices = llmResp.choices || [];
  if (choices.length > 0) {
    const content = choices[0].message?.content || '{}';
    const parsed = JSON.parse(content);
    agentDecision = parsed.decision || 'UNKNOWN';
    agentRazon = parsed.razon || '';
    agentReemplazo = parsed.reemplazo || '';
  } else if (llmResp.error) {
    agentRazon = 'llm_error: ' + (llmResp.error.message || llmResp.error.description || 'unknown');
  }
} catch(e) {
  agentRazon = 'parse_error: ' + e.message;
}

const regexDecision = prepData.shadow_regex_decision || '?';
const phone = prepData.shadow_input_phone || '?';
const pacienteMsg = prepData.shadow_input_paciente || '';
const botOutput = prepData.shadow_input_output || '';
const agreement = (regexDecision === 'ALLOW' && agentDecision === 'ALLOW') ||
                  (regexDecision !== 'ALLOW' && agentDecision === 'BLOCK');

console.log('[BANLIST_SHADOW]', JSON.stringify({
  phone,
  paciente: pacienteMsg.slice(0, 80),
  output: botOutput.slice(0, 120),
  regex: regexDecision,
  agent: agentDecision,
  agent_razon: agentRazon,
  agreement,
  ts: new Date().toISOString()
}));

return [{ json: {
  shadow_phone: phone,
  shadow_paciente_msg: pacienteMsg,
  shadow_bot_output: botOutput,
  shadow_regex_decision: regexDecision,
  shadow_agent_decision: agentDecision,
  shadow_agent_razon: agentRazon,
  shadow_agent_reemplazo: agentReemplazo,
  shadow_agreement: agreement,
}}];
"""

wf = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
n = next((x for x in wf["nodes"] if x["name"] == "Banlist Shadow - Log"), None)
if not n: print("!! not found"); sys.exit(2)
n["parameters"]["jsCode"] = NEW_JS

allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution","executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": settings, "staticData": wf.get("staticData")}
r = requests.put(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, json=body, timeout=40)
print(f"PUT {r.status_code}")
