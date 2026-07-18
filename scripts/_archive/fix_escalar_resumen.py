"""
Fix bug: el tool escalar_a_secretaria pierde el 'query' que el LLM le pasa.
$fromAI() falla silenciosamente y cae al default 'Caso escalado sin resumen.'

Fix: agregar fallback usando $input.item.json.query (sintaxis estandar
n8n toolCode) ademas de $fromAI. Si ambos fallan, recien ahi default.

Backup pre + verify post.
"""
import json, sys
from datetime import datetime
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_ESCALAR_FIX_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_ESCALAR_FIX_{ts}.json")

n = next(x for x in wf["nodes"] if x["name"] == "escalar_a_secretaria")
old_code = n["parameters"]["jsCode"]
print(f"jsCode actual: {len(old_code)} chars")

# Nuevo codigo con fallback robusto
NEW_CODE = """// Escala al grupo de derivaciones via helper webhook.
// FIX: lee args del LLM con multiples metodos para evitar perder el resumen
// cuando $fromAI falla silenciosamente.

function tryGetArg(name) {
  // 1) $fromAI (sintaxis langchain v1)
  try {
    const v = $fromAI(name, '', 'string');
    if (v && typeof v === 'string' && v.trim()) return v.trim();
  } catch (_) {}
  // 2) $input.item.json[name] (sintaxis estandar n8n toolCode)
  try {
    const ji = $input && $input.item && $input.item.json;
    if (ji && ji[name] && typeof ji[name] === 'string' && ji[name].trim()) {
      return ji[name].trim();
    }
  } catch (_) {}
  // 3) $input.all()[0].json[name]
  try {
    const all = $input && $input.all && $input.all();
    if (all && all.length && all[0].json && all[0].json[name]) {
      const v = all[0].json[name];
      if (typeof v === 'string' && v.trim()) return v.trim();
    }
  } catch (_) {}
  return '';
}

let query = tryGetArg('query');
let phone = tryGetArg('phone');

// Fallback default solo si NADA funciono
if (!query) {
  query = 'Caso escalado sin resumen.';
  try { console.log('[escalar] WARNING: query NO recibido del LLM, usando default'); } catch (_) {}
}

// Normalizar phone (quitar +)
if (phone) phone = phone.replace(/^\\+/, '');

// Fallback: si phone quedo vacio, extraerlo del query si esta embebido
if (!phone) {
  const m = String(query).match(/549\\d{10}/);
  if (m) phone = m[0];
}

try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
    headers: { 'Content-Type': 'application/json' },
    body: { text: '[ESCALADO BOT] ' + query, phone: phone },
    json: true
  });
  return 'Escalado al grupo correctamente.';
} catch (err) {
  try { console.log('[escalar] notify-grupo fail:', String(err && err.message ? err.message : err)); } catch(_) {}
  return 'Escalacion intentada (fallo el envio al grupo).';
}"""

if "tryGetArg" in old_code:
    print("  [skip] ya tiene tryGetArg, no aplico")
    sys.exit(0)

n["parameters"]["jsCode"] = NEW_CODE
print(f"  jsCode reemplazado, {len(old_code)} -> {len(NEW_CODE)} chars")

# PUT
allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
payload = {"name": wf["name"], "nodes": wf["nodes"],
           "connections": wf["connections"], "settings": settings}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]
r = requests.put(f"{N8N}/api/v1/workflows/{WF}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
print(f"\nPUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:500]); sys.exit(1)

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_ESCALAR_FIX_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_ESCALAR_FIX_{ts}.json")
print(f"v6 active: {wf_post.get('active')}")
n_post = next(x for x in wf_post["nodes"] if x["name"] == "escalar_a_secretaria")
print(f"verify tryGetArg presente: {'tryGetArg' in n_post['parameters']['jsCode']}")
