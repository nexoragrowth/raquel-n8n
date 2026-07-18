import json, sys, requests
from pathlib import Path
from datetime import datetime

API = "https://n8n.raquelrodriguez.com.ar/api/v1"
import os
KEY = os.environ.get("N8N_API_KEY")
if not KEY:
    raise SystemExit("set N8N_API_KEY env var")
WF_ID = "O155MqHgOSaNZ9ye"

# 1. GET live
r = requests.get(f"{API}/workflows/{WF_ID}", headers={"X-N8N-API-KEY": KEY})
r.raise_for_status()
wf = r.json()

ts = datetime.now().strftime("%Y%m%d_%H%M")
Path(f"C:/Users/Lucas/.claude/n8n_backups/v6_PRE_4FIXES_{ts}.json").write_text(
    json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8"
)
print(f"Backup pre-fix: v6_PRE_4FIXES_{ts}.json")

assert wf["active"] is False, f"REFUSE PUT: workflow is active={wf['active']}"

wh_node = next(n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.webhook")
assert wh_node.get("webhookId") == "evo-webhook-v2", f"webhookId mismatch: {wh_node.get('webhookId')}"
assert wh_node["parameters"].get("path") == "evolution-v2", f"path mismatch: {wh_node['parameters'].get('path')}"
print(f"Webhook OK: path={wh_node['parameters']['path']}, webhookId={wh_node['webhookId']}")

# ============ FIX #1: Kill-switch Check ============
new_killswitch = """// Kill-switch: detecta comandos /bot off|on|status de admins.
// FIX 2026-05-09: aceptar comando si fromMe=true (admin escribiendo desde la app del consultorio).
const inp = $input.first().json || {};
const body = inp.body || {};
const k = body.data && body.data.key;
const remoteJid = (k && k.remoteJid) || '';
const phone = remoteJid.replace('@s.whatsapp.net', '').replace(/^\\+/, '');
const fromMe = !!(k && k.fromMe);
const msgConv = body.data && body.data.message && body.data.message.conversation;
const msgExt = body.data && body.data.message && body.data.message.extendedTextMessage && body.data.message.extendedTextMessage.text;
const text = (msgConv || msgExt || '').trim();

const ADMINS = {
  '5491161461034': 'Lucas',
  '5493885786946': 'Irina',
  '5493513976787': 'Dra. Raquel',
};

const cmd = text.toLowerCase().match(/^\\/bot\\s+(off|on|status)\\b/);

let isAdmin = false;
let adminLabel = null;

if (cmd) {
  if (!fromMe && ADMINS[phone]) {
    isAdmin = true;
    adminLabel = ADMINS[phone];
  } else if (fromMe) {
    isAdmin = true;
    adminLabel = 'Business User';
  }
}

if (isAdmin) {
  return [{ json: {
    isAdminCommand: true,
    action: cmd[1],
    adminPhone: phone,
    adminName: adminLabel,
    fromBusiness: fromMe,
    chatJid: remoteJid
  } }];
}

return [{ json: { isAdminCommand: false, body: inp.body, headers: inp.headers } }];
"""

# ============ FIX #2: Build fromMe AI memory ============
new_build_fromMe = """// Guardar mensaje saliente (Iri/doctora desde WA Web/app del consultorio) en memoria.
// FIX 2026-05-09: prefijar el content con tag explicito para que el LLM NO lo confunda con output propio.
const text = ($json.text || '').trim();
const phone = $json.phone;
if (!text || !phone) return [];

const TAG = '[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria desde el WhatsApp del consultorio. NO es output tuyo, es un humano atendiendo este chat. Mantente en silencio y NO respondas en este chat hasta que un admin diga /bot on.]: ';

const session_id = phone;
const message = {
  type: 'ai',
  content: TAG + text,
  additional_kwargs: { source: 'wa_outbound', from_iri_or_dra: true },
  response_metadata: {},
  tool_calls: [],
  invalid_tool_calls: []
};
return [{ json: { session_id, message: JSON.stringify(message) } }];
"""

# ============ FIX #4: HTTP Send Admin Confirm ============
new_admin_confirm_remote = "={{ $('Kill-switch Check').first().json.chatJid }}"

# ============ Aplicar cambios ============
fixes_applied = []
for n in wf["nodes"]:
    if n["name"] == "Kill-switch Check":
        n["parameters"]["jsCode"] = new_killswitch
        fixes_applied.append(f"#1 Kill-switch Check (jsCode {len(new_killswitch)} chars)")
    elif n["name"] == "Build fromMe AI memory":
        n["parameters"]["jsCode"] = new_build_fromMe
        fixes_applied.append(f"#2 Build fromMe AI memory (jsCode {len(new_build_fromMe)} chars)")
    elif n["name"] == "HTTP Send Admin Confirm":
        n["parameters"]["remoteJid"] = new_admin_confirm_remote
        fixes_applied.append(f"#4 HTTP Send Admin Confirm (remoteJid -> chatJid)")

# ============ FIX #3: Conectar Postgres Chat Memory.ai_memory -> Router ============
router_exists = any(n["name"] == "Router - Clasificar Intent" for n in wf["nodes"])
mem_exists = any(n["name"] == "Postgres Chat Memory" for n in wf["nodes"])
assert router_exists and mem_exists, "Router or Memory node not found"

conns = wf["connections"]
mem_conns = conns.setdefault("Postgres Chat Memory", {})
ai_mem_branches = mem_conns.setdefault("ai_memory", [])

if not ai_mem_branches:
    ai_mem_branches.append([])

existing = {c["node"] for c in ai_mem_branches[0]}
if "Router - Clasificar Intent" not in existing:
    ai_mem_branches[0].append({
        "node": "Router - Clasificar Intent",
        "type": "ai_memory",
        "index": 0
    })
    fixes_applied.append("#3 connection ai_memory -> Router - Clasificar Intent")
else:
    fixes_applied.append("#3 connection already exists, skipping")

print()
print("Cambios aplicados:")
for f in fixes_applied:
    print(f"  - {f}")
print()

# ============ Strip campos no permitidos ============
ALLOWED = ["name", "nodes", "connections", "settings", "staticData"]
ALLOWED_SETTINGS = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution","executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
payload = {k: wf[k] for k in ALLOWED if k in wf}
if "settings" in payload and isinstance(payload["settings"], dict):
    payload["settings"] = {k: v for k, v in payload["settings"].items() if k in ALLOWED_SETTINGS}
    print(f"settings filtered to: {list(payload['settings'].keys())}")
print(f"PUT payload keys: {list(payload.keys())}")
print(f"PUT payload size: {len(json.dumps(payload))/1024:.0f} KB")

Path(f"C:/Users/Lucas/.claude/n8n_backups/v6_POST_4FIXES_payload_{ts}.json").write_text(
    json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
)

# ============ PUT ============
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
print(f"active (post-PUT): {result.get('active')}")

wh_post = next(n for n in result["nodes"] if n["type"] == "n8n-nodes-base.webhook")
print(f"webhookId post-PUT: {wh_post.get('webhookId')}")
assert wh_post.get("webhookId") == "evo-webhook-v2", "webhookId LOST after PUT"

ks = next(n for n in result["nodes"] if n["name"] == "Kill-switch Check")
print(f"Kill-switch contains 'Business User': {'Business User' in ks['parameters']['jsCode']}")

bf = next(n for n in result["nodes"] if n["name"] == "Build fromMe AI memory")
print(f"Build fromMe contains 'ATENCION HUMANA': {'ATENCION HUMANA' in bf['parameters']['jsCode']}")

ac = next(n for n in result["nodes"] if n["name"] == "HTTP Send Admin Confirm")
print(f"Admin Confirm uses chatJid: {'chatJid' in ac['parameters'].get('remoteJid','')}")

mem_to_router = any(
    c["node"] == "Router - Clasificar Intent"
    for branch in result["connections"].get("Postgres Chat Memory", {}).get("ai_memory", [])
    for c in branch
)
print(f"Memory -> Router connection present: {mem_to_router}")

print()
print("DONE.")
