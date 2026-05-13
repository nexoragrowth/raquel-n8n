"""
Inserta nodo "Banlist Validator" entre 'Formatting Agent - WhatsApp' y 'Split en Mensajes'.

Si el output del Formatting Agent contiene CUALQUIERA de las frases prohibidas,
reescribe el output completo con la canned de escalacion.

Determinístico, no depende del LLM.
"""
import json, sys, requests
from pathlib import Path
from datetime import datetime

API = "https://n8n.raquelrodriguez.com.ar/api/v1"
import os
KEY = os.environ.get("N8N_API_KEY")
if not KEY:
    raise SystemExit("set N8N_API_KEY env var")
WF_ID = "O155MqHgOSaNZ9ye"

r = requests.get(f"{API}/workflows/{WF_ID}", headers={"X-N8N-API-KEY": KEY})
r.raise_for_status()
wf = r.json()

ts = datetime.now().strftime("%Y%m%d_%H%M")
Path(f"C:/Users/Lucas/.claude/n8n_backups/v6_PRE_BANLIST_{ts}.json").write_text(
    json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(f"Backup pre-banlist: v6_PRE_BANLIST_{ts}.json")
assert wf["active"] is False, "Workflow active, refuse PUT"

BANLIST_CODE = r"""// Banlist Validator - 2026-05-09
// Si el output del bot contiene frases prohibidas, lo reemplaza por escalacion.
// El bot SOLO debe agendar, recordar, pasar info de pago, confirmar/cancelar.
// Cualquier instruccion clinica/operativa o invitacion a la clinica = escalar.

const item = $input.first().json;
const output = (item.output || '').toString();

// Frases prohibidas (regex case-insensitive)
const BANLIST = [
  // Imperativos clinicos / venirse a la clinica
  { rx: /\bven[íi](te)?\b/i,                           why: 'venite/veni' },
  { rx: /\bveng(a|an|amos)\b/i,                        why: 'venga/vengan' },
  { rx: /\b(los|las|te|le|la|lo|los?\s+espera|las?\s+espera)\s*esperamos\b/i, why: 'los esperamos' },
  { rx: /\bte\s+esper(amos|amos\s+a|an)\b/i,           why: 'te esperamos' },
  { rx: /\b(la|lo)\s+esperamos\b/i,                    why: 'la/lo esperamos' },
  { rx: /\bsalgan?\s+(ya|ahora|para)\b/i,              why: 'salgan ya/para' },
  { rx: /\b(ven[íi]|vengan)\s+ahora\s+mismo\b/i,        why: 'veni/vengan ahora mismo' },
  { rx: /\bahora\s+mismo\b.{0,50}\b(cl[íi]nica|consultorio|aurea|áurea)\b/i, why: 'ahora mismo + clinica' },
  { rx: /\blo\s+antes\s+posible\b.{0,50}\b(cl[íi]nica|consultorio|aurea|áurea|venir)\b/i, why: 'lo antes posible + clinica' },
  // Instrucciones medicas / clinicas
  { rx: /\bguard(á|a|alo|enlo|en|amos|en\s+la)\s+/i,   why: 'guarda/guarden (instruccion)' },
  { rx: /\btraig(a|an|alo|anlo|amos|an\s+(el|la|los|las))\b/i, why: 'traigan (instruccion operativa)' },
  { rx: /\btra(é|e)\s+(el|la|los|las|tu)/i,             why: 'trae (instruccion)' },
  { rx: /\btom(á|a|alo|en|amos)\s+(\d|un|una|el|la|los|las|cada)/i, why: 'toma medicacion/dosis' },
  { rx: /\bsac(á|a|alo|en|amos)\s+(la|el)/i,            why: 'saca (instruccion)' },
  { rx: /\bdescans(á|a|en)\b/i,                         why: 'descansa (instruccion medica)' },
  { rx: /\bevit(á|a|en)\b/i,                            why: 'evita (instruccion medica)' },
  { rx: /\baplic(á|a|ate|en|ense)\b/i,                  why: 'aplica (instruccion medica)' },
  { rx: /\benjuag(á|a|ate|en|ense)\b/i,                 why: 'enjuaga (instruccion medica)' },
  // Diagnostico / opinion medica
  { rx: /\bno\s+te\s+preocup(es|és)\b/i,                why: 'no te preocupes (minimizar sintoma)' },
  { rx: /\bes\s+(totalmente\s+)?normal\b/i,             why: 'es normal (diagnostico)' },
  { rx: /\bno\s+es\s+(nada\s+)?grave\b/i,               why: 'no es grave (diagnostico)' },
  { rx: /\b(qu[ée]\s+macana|qu[ée]\s+embromado|qu[ée]\s+l[áa]stima)\b/i, why: 'opinion emocional' },
  // Direccion fisica como confirmacion de cita
  { rx: /\bbalcarce\s*(n[º°]?\s*)?37\b/i,               why: 'direccion Balcarce 37 (NO debe darse desde el bot fuera de info-direccion explicita)' },
];

// Excepciones: si el paciente pregunto por la direccion explicitamente, "Balcarce 37" si va.
// Esa logica la hara el sub-agente futuro. Por ahora: BAN absoluto sobre Balcarce 37.

let triggered = null;
for (const entry of BANLIST) {
  if (entry.rx.test(output)) {
    triggered = entry.why;
    break;
  }
}

if (triggered) {
  const CANNED = 'Recibimos tu mensaje. Estamos derivando tu caso a la Dra. Raquel para que te responda personalmente por este chat. Disculpa la demora.';
  console.log('[BANLIST TRIGGERED]', triggered, '|original:', output.slice(0, 300));
  return [{
    json: {
      ...item,
      output: CANNED,
      banlist_triggered: triggered,
      banlist_original_output: output,
      escalate_to_human: true,
    }
  }];
}

return [{ json: { ...item, banlist_triggered: null, escalate_to_human: false } }];
"""

# Crear nodo Banlist Validator
banlist_node = {
    "parameters": {
        "jsCode": BANLIST_CODE
    },
    "id": "banlist-validator-v1",
    "name": "Banlist Validator",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [5360, 288]
}

# Verificar que no exista ya
existing = next((n for n in wf["nodes"] if n["name"] == "Banlist Validator"), None)
if existing:
    print("Banlist Validator ya existe, sobreescribo jsCode")
    existing["parameters"]["jsCode"] = BANLIST_CODE
    existing["position"] = [5360, 288]
else:
    wf["nodes"].append(banlist_node)
    print("Banlist Validator agregado")

# Reconectar: Formatting Agent → Banlist Validator → Split en Mensajes
conns = wf["connections"]

# Reemplazar el destino de Formatting Agent - WhatsApp.main
fa_conns = conns.get("Formatting Agent - WhatsApp", {})
fa_main = fa_conns.get("main", [])
# Limpiar conexiones existentes que apunten directamente a Split
for branch in fa_main:
    branch[:] = [c for c in branch if c.get("node") != "Split en Mensajes"]
# Asegurar branch
if not fa_main:
    fa_main.append([])
# Agregar conexión a Banlist Validator
already = any(c.get("node") == "Banlist Validator" for branch in fa_main for c in branch)
if not already:
    fa_main[0].append({"node": "Banlist Validator", "type": "main", "index": 0})

conns.setdefault("Formatting Agent - WhatsApp", {})["main"] = fa_main

# Banlist Validator → Split en Mensajes
conns["Banlist Validator"] = {
    "main": [[{"node": "Split en Mensajes", "type": "main", "index": 0}]]
}

# Validar
print()
print("Connections post-update:")
print("  Formatting Agent - WhatsApp.main:", json.dumps(conns.get("Formatting Agent - WhatsApp", {}).get("main", []), ensure_ascii=False))
print("  Banlist Validator.main:", json.dumps(conns.get("Banlist Validator", {}).get("main", []), ensure_ascii=False))

# Strip
ALLOWED = ["name", "nodes", "connections", "settings", "staticData"]
ALLOWED_SETTINGS = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution","executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
payload = {k: wf[k] for k in ALLOWED if k in wf}
if "settings" in payload and isinstance(payload["settings"], dict):
    payload["settings"] = {k: v for k, v in payload["settings"].items() if k in ALLOWED_SETTINGS}

Path(f"C:/Users/Lucas/.claude/n8n_backups/v6_POST_BANLIST_payload_{ts}.json").write_text(
    json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
)

print()
print(f"PUT payload size: {len(json.dumps(payload))/1024:.0f} KB")
print(f"Total nodos post-banlist: {len(payload['nodes'])}")

print()
print("PUT ...")
r = requests.put(
    f"{API}/workflows/{WF_ID}",
    headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json"},
    json=payload,
    timeout=60,
)
print(f"PUT status: {r.status_code}")
if r.status_code >= 400:
    print(f"ERROR body: {r.text[:1500]}")
    sys.exit(1)
result = r.json()
print(f"OK. updatedAt: {result.get('updatedAt')}")
print(f"active: {result.get('active')}")

# Verificar nodo presente
bv = next((n for n in result["nodes"] if n["name"] == "Banlist Validator"), None)
print(f"Banlist Validator presente: {bv is not None}")
print(f"Banlist contains 'venite' regex: {bv and 'venite' in bv['parameters']['jsCode'].lower()}")

# Verificar conexion
fa_to_bv = any(c.get("node") == "Banlist Validator" for branch in result["connections"].get("Formatting Agent - WhatsApp", {}).get("main", []) for c in branch)
bv_to_split = any(c.get("node") == "Split en Mensajes" for branch in result["connections"].get("Banlist Validator", {}).get("main", []) for c in branch)
print(f"Formatting Agent -> Banlist: {fa_to_bv}")
print(f"Banlist -> Split en Mensajes: {bv_to_split}")

# Verificar que Formatting Agent ya NO conecta directo a Split
fa_to_split_direct = any(c.get("node") == "Split en Mensajes" for branch in result["connections"].get("Formatting Agent - WhatsApp", {}).get("main", []) for c in branch)
print(f"Formatting Agent direct->Split (debe ser False): {fa_to_split_direct}")

# Webhook id check
wh = next(n for n in result["nodes"] if n["type"] == "n8n-nodes-base.webhook")
print(f"webhookId post-PUT: {wh.get('webhookId')}")

print()
print("DONE.")
