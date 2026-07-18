"""Banlist Agent shadow mode (2026-06-04):
Inserta 2 nodos despues del Banlist Validator (regex):
1. Banlist Shadow - Prep (Code): arma payload OpenAI nano + captura inputs
2. Banlist Shadow - LLM (HTTP): llama gpt-5-nano + reasoning_effort=minimal

NO altera el flujo: el output del Banlist Validator pasa intacto al
"Necesita Formatting?" downstream. Los 2 nodos shadow corren en serie despues,
en una rama hija que loguea pero no afecta el resultado.

Approach: dejo el Banlist Validator -> Necesita Formatting? igual (rama principal).
Agrego desde el Banlist Validator una segunda salida hacia el shadow que termina
en un Edit Fields que solo loguea. La execution data guarda todo. Despues
extraigo con script las decisiones para comparar regex vs agent.

Modo: --dry / --apply
"""
from __future__ import annotations
import argparse, json, os, sys, io
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
WF_ID = "O155MqHgOSaNZ9ye"


PREP_JS = """// Banlist Shadow - Prep (gpt-5-nano)
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

REGLAS DURAS (si el output infringe alguna, BLOCK):
1. NO debe invitar al paciente a venir ahora ("venite", "vengan", "los esperamos", "salgan ya", "diríjase al consultorio", "acerquese ahora", paráfrasis similares).
2. NO debe dar instrucciones operativas/médicas ("guardá la pieza", "tomá X", "aplicá Y", "enjuagá con Z").
3. NO debe dar diagnóstico ni opinión emocional ("no te preocupes", "no es nada grave", "qué macana").
4. NO debe dar la direccion (Balcarce 37) como confirmacion de cita, EXCEPTO si el paciente la pidio explicitamente.

Si el output cumple TODO -> ALLOW. Si infringe -> BLOCK + razon corta.

Responde SOLO JSON: {"decision":"ALLOW"|"BLOCK","razon":"breve","reemplazo":"opcional canned"}.
Hoy es ${today}.`;

const userPrompt = `MENSAJE DEL PACIENTE: ${pacienteMsg}

OUTPUT QUE EL BOT VA A ENVIAR:
${originalOutput}

¿ALLOW o BLOCK?`;

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


LOG_JS = """// Banlist Shadow - Log
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


def get_wf():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60); r.raise_for_status(); return r.json()


def put_wf(wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
    if not r.ok:
        print("PUT FAIL", r.status_code, r.text[:1500], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()

    # Localizar Banlist Validator
    ban = next((n for n in wf["nodes"] if n["name"] == "Banlist Validator"), None)
    if not ban:
        print("!! Banlist Validator no found"); sys.exit(2)
    bx, by = ban["position"]

    # Check si ya existe
    existing = [n["name"] for n in wf["nodes"]]
    if any("Banlist Shadow" in n for n in existing):
        print("!! ya hay nodos Banlist Shadow, abort para no duplicar")
        for n in existing:
            if "Banlist Shadow" in n: print(f"  - {n}")
        sys.exit(3)

    # Nuevos nodos
    prep_node = {
        "parameters": {"jsCode": PREP_JS},
        "id": "banlist-shadow-prep",
        "name": "Banlist Shadow - Prep",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [bx + 260, by + 200],
    }
    llm_node = {
        "parameters": {
            "method": "POST",
            "url": "https://api.openai.com/v1/chat/completions",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "openAiApi",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ $json.shadow_openai_body }}",
            "options": {"response": {"response": {"neverError": True}}}
        },
        "id": "banlist-shadow-llm",
        "name": "Banlist Shadow - LLM",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [bx + 520, by + 200],
        "credentials": {},
    }
    # Capturar credenciales OpenAI (mismo ID usado por LangChain LM nodes en v6)
    OPENAI_CRED = {"openAiApi": {"id": "nYujqfon7GGDnJUO", "name": "OpenAi account"}}
    llm_node["credentials"] = OPENAI_CRED

    log_node = {
        "parameters": {"jsCode": LOG_JS},
        "id": "banlist-shadow-log",
        "name": "Banlist Shadow - Log",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [bx + 780, by + 200],
    }

    # Insertar nodos
    wf["nodes"].extend([prep_node, llm_node, log_node])

    # Conectar: Banlist Validator (main[0]) -> Banlist Shadow Prep
    # Banlist Validator ya tiene main -> "Necesita Formatting?". Lo dejamos.
    # Agregamos UN segundo array en main para abrir rama shadow.
    # NOTA: en n8n, multiple outputs en main = un solo array con multiple entries en arr[0]
    conns = wf["connections"]
    ban_conns = conns.get("Banlist Validator", {})
    main_conns = ban_conns.get("main", [[]])
    # main[0] tiene la lista de successors normales. Agregamos uno mas.
    if not main_conns: main_conns = [[]]
    if not any(c.get("node") == "Banlist Shadow - Prep" for c in main_conns[0]):
        main_conns[0].append({"node": "Banlist Shadow - Prep", "type": "main", "index": 0})
    ban_conns["main"] = main_conns
    conns["Banlist Validator"] = ban_conns

    # Prep -> LLM -> Log (cadena lineal, NO conecta a nada mas downstream)
    conns["Banlist Shadow - Prep"] = {"main": [[{"node": "Banlist Shadow - LLM", "type": "main", "index": 0}]]}
    conns["Banlist Shadow - LLM"] = {"main": [[{"node": "Banlist Shadow - Log", "type": "main", "index": 0}]]}
    # Log no conecta a nada - es terminal de la rama shadow

    print("CAMBIOS:")
    print(f"  + Banlist Shadow - Prep en [{prep_node['position']}]")
    print(f"  + Banlist Shadow - LLM en [{llm_node['position']}]  cred={list(llm_node['credentials'].keys()) or 'NONE'}")
    print(f"  + Banlist Shadow - Log en [{log_node['position']}]")
    print(f"  conexiones: Banlist Validator -> Prep -> LLM -> Log (rama shadow, NO afecta flow principal)")

    if args.dry or not args.apply:
        print("\n[dry] no aplicado."); return

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_BANLIST_SHADOW_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")

    res = put_wf(wf); print(f"\nPUT OK updatedAt={res.get('updatedAt')}")

    # Verify
    wf2 = get_wf()
    for nm in ("Banlist Shadow - Prep", "Banlist Shadow - LLM", "Banlist Shadow - Log"):
        ok = any(n["name"] == nm for n in wf2["nodes"])
        print(f"  {'OK' if ok else 'FAIL'} {nm} exists")
    conns2 = wf2["connections"].get("Banlist Validator", {}).get("main", [[]])
    linked = any(c.get("node") == "Banlist Shadow - Prep" for c in conns2[0])
    print(f"  {'OK' if linked else 'FAIL'} Banlist Validator -> Banlist Shadow - Prep")


if __name__ == "__main__":
    main()
