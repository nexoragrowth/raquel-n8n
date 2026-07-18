"""
Mejora el Parse mensajes del Logger para filtrar:
- Outputs del Router LM (consulta_general, agendar_nuevo, etc.) — no son conversacion
- Mensajes vacios
- Mensajes con `additional_kwargs.source=router` o cuando el content es un intent label

Tambien limpia los rows ya insertados con esos contenidos.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

API_KEY = require('N8N_API_KEY')
API_BASE = f"{require('N8N_BASE_URL')}/api/v1"
WID = "xsXeHp7WLXnFQc3o"
SUPABASE_URL = require('SUPABASE_URL')
SUPABASE_KEY = require('SUPABASE_SERVICE_ROLE_KEY')

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}


def http(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        headers={"X-N8N-API-KEY": API_KEY, "Content-Type": "application/json", "Accept": "application/json"},
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


def strip_meta(wf):
    for k in ("id", "active", "createdAt", "updatedAt", "tags", "versionId", "triggerCount",
              "meta", "isArchived", "shared", "homeProject", "sharedWithProjects", "scopes",
              "description", "pinData", "activeVersionId", "versionCounter", "activeVersion"):
        wf.pop(k, None)
    s = wf.get("settings") or {}
    wf["settings"] = {k: v for k, v in s.items() if k in ALLOWED_SETTINGS}
    return wf


NEW_PARSE_CODE = """// Parsea n8n_chat_histories rows y filtra ruido del Router LM.
const ROUTER_INTENTS = new Set([
  'consulta_general', 'agendar_nuevo', 'consulta_confirmacion',
  'consulta_cancelacion', 'urgencia', 'cierre', 'autoresponder_externo',
  'multimedia', 'comando_admin', 'humano_takeover',
]);

const rows = $input.all();
const out = [];

for (const item of rows) {
  const r = item.json;
  const id = r.id;
  const phone = String(r.session_id || '').trim();
  if (!phone) continue;

  let msg = r.message;
  if (typeof msg === 'string') {
    try { msg = JSON.parse(msg); } catch (e) { continue; }
  }
  if (!msg || typeof msg !== 'object') continue;

  const type = msg.type || msg.kwargs?.type || '';
  const content = msg.content || msg.kwargs?.content || '';
  const addKw = msg.additional_kwargs || msg.kwargs?.additional_kwargs || {};
  const source = (addKw.source || '').toLowerCase();

  const trimmed = String(content || '').trim();
  if (!trimmed || trimmed === '[NO_REPLY]') continue;

  // Filtro Router: si el content es exactamente un intent label, skip
  if (ROUTER_INTENTS.has(trimmed.toLowerCase())) continue;

  // Filtro: si es muy corto (<3 chars) y no es saludo
  if (trimmed.length < 3) continue;

  let rol = 'user';
  let fuente = 'whatsapp';
  if (type === 'human') {
    if (source === 'wa_outbound' || source === 'human_takeover') {
      rol = 'human';
      fuente = 'whatsapp_secretaria';
    } else {
      rol = 'user';
      fuente = 'whatsapp';
    }
  } else if (type === 'ai') {
    if (source === 'reminder_note') {
      rol = 'system';
      fuente = 'bot_reminder';
    } else {
      rol = 'assistant';
      fuente = 'bot';
    }
  } else {
    rol = 'system';
    fuente = 'unknown';
  }

  const pushName = addKw.pushName || addKw.push_name || null;

  out.push({
    json: {
      chat_history_id: id,
      telefono: phone,
      rol,
      mensaje: trimmed,
      fuente,
      created_at: r.created_at,
      metadata: { source, pushName, type, chat_history_id: id },
      pushName,
    },
  });
}

return out;
"""


def main():
    print("Pulling Logger workflow...")
    _, wf = http("GET", f"/workflows/{WID}")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    Path("workflows/history").mkdir(parents=True, exist_ok=True)
    Path(f"workflows/history/logger_PRE_FILTER_{stamp}.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for n in wf["nodes"]:
        if n["name"] == "Parse mensajes":
            n["parameters"]["jsCode"] = NEW_PARSE_CODE
            break

    payload = strip_meta(dict(wf))
    print("PUT updated Parse with filter...")
    status, _ = http("PUT", f"/workflows/{WID}", payload)
    print(f"  status: {status}")

    # Cleanup: borrar los rows ya insertados con intent labels
    intents = ['consulta_general', 'agendar_nuevo', 'consulta_confirmacion',
               'consulta_cancelacion', 'urgencia', 'cierre', 'autoresponder_externo',
               'multimedia', 'comando_admin', 'humano_takeover']
    headers_sup = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    deleted_total = 0
    for intent in intents:
        del_req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/conversaciones?mensaje=eq.{intent}",
            method="DELETE",
            headers={**headers_sup, "Prefer": "return=minimal,count=exact"},
        )
        try:
            with urllib.request.urlopen(del_req, timeout=20) as r:
                cr = r.headers.get('Content-Range', '*/0')
                cnt = cr.split('/')[-1] if '/' in cr else '0'
                if cnt != '0':
                    print(f"  cleaned {cnt} rows with mensaje={intent!r}")
                    deleted_total += int(cnt)
        except Exception as e:
            print(f"  err deleting {intent}: {e}")

    print(f"\nTotal limpiado: {deleted_total} rows de ruido Router")


if __name__ == "__main__":
    main()
