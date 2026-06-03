"""
Crea el workflow 'Logger Conversaciones' en n8n. Sincroniza periodicamente
las nuevas filas de `n8n_chat_histories` -> `conversaciones` + `pacientes`
en Supabase clinica.

Diseño:
  Schedule (30s) -> Code lee last_synced -> Postgres SELECT nuevos
    -> Code parse mensajes -> Loop:
       -> Supabase upsert paciente
       -> Supabase insert conversacion
    -> Code actualiza last_synced (staticData)

Cero impacto al v6 vivo. Toda la sincronizacion es post-hoc, max 30s de lag.
"""
import json
import sys
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

API_KEY = require('N8N_API_KEY')
API_BASE = f"{require('N8N_BASE_URL')}/api/v1"
DRY_RUN = "--dry-run" in sys.argv

# Credentials existentes en n8n
CRED_POSTGRES = {"id": "xwvjww5Odcxiy1K9", "name": "Postgres account"}
CRED_SUPABASE = {"id": "Thn3jgEbbxPFD7d9", "name": "Supabase account"}


def http(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        headers={"X-N8N-API-KEY": API_KEY, "Content-Type": "application/json", "Accept": "application/json"},
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


# ============================================================
# Workflow definition
# ============================================================

CODE_GET_LAST_SYNCED = """// Lee el ultimo id sincronizado desde staticData del workflow.
const sd = $getWorkflowStaticData('global');
const last = sd.last_synced_chat_id || 0;
return [{ json: { last } }];
"""

CODE_PARSE_MESSAGES = """// Parsea cada row de n8n_chat_histories en payload listo para Supabase.
// Mapea type/source -> rol y fuente.
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

  // Skip mensajes vacios o NO_REPLY
  const trimmed = String(content || '').trim();
  if (!trimmed || trimmed === '[NO_REPLY]') continue;

  // Mapeo rol
  let rol = 'user';
  let fuente = 'whatsapp';
  if (type === 'human') {
    // human puede ser paciente o secretaria (si source=wa_outbound)
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
    // type desconocido, default
    rol = 'system';
    fuente = 'unknown';
  }

  // Extract pushName si esta en metadata
  const pushName = addKw.pushName || addKw.push_name || null;

  out.push({
    json: {
      chat_history_id: id,
      telefono: phone,
      rol,
      mensaje: trimmed,
      fuente,
      created_at: r.created_at,
      metadata: { source, pushName, type, addKw },
      pushName,
    },
  });
}

return out;
"""

CODE_UPDATE_LAST_SYNCED = """// Toma el max chat_history_id procesado y lo guarda en staticData.
const rows = $input.all();
if (rows.length === 0) return [];
let max = 0;
for (const r of rows) {
  const id = r.json.chat_history_id || 0;
  if (id > max) max = id;
}
const sd = $getWorkflowStaticData('global');
const prev = sd.last_synced_chat_id || 0;
if (max > prev) {
  sd.last_synced_chat_id = max;
}
return [{ json: { previous: prev, new: max, total_synced: rows.length } }];
"""

WF = {
    "name": "Logger Conversaciones (Supabase)",
    "nodes": [
        {
            "id": "trg",
            "name": "Cron 30s",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.1,
            "position": [240, 300],
            "parameters": {
                "rule": {"interval": [{"field": "seconds", "secondsInterval": 30}]}
            },
        },
        {
            "id": "code_last",
            "name": "Get last_synced",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [460, 300],
            "parameters": {"jsCode": CODE_GET_LAST_SYNCED},
        },
        {
            "id": "pg_select",
            "name": "PG - SELECT nuevos",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [680, 300],
            "parameters": {
                "operation": "executeQuery",
                "query": "SELECT id, session_id, message::text AS message, created_at FROM n8n_chat_histories WHERE id > $1 ORDER BY id ASC LIMIT 200",
                "options": {"queryReplacement": "={{ $json.last }}"},
            },
            "credentials": {"postgres": CRED_POSTGRES},
        },
        {
            "id": "code_parse",
            "name": "Parse mensajes",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [900, 300],
            "parameters": {"jsCode": CODE_PARSE_MESSAGES},
        },
        {
            "id": "sb_upsert_pac",
            "name": "SB - Upsert Paciente",
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [1140, 300],
            "parameters": {
                "operation": "upsert",
                "tableId": "pacientes",
                "matchingColumns": ["telefono"],
                "fieldsUi": {
                    "fieldValues": [
                        {"fieldId": "telefono", "fieldValue": "={{ $json.telefono }}"},
                        {"fieldId": "nombre", "fieldValue": "={{ $json.pushName || 'Paciente WhatsApp' }}"},
                    ]
                },
            },
            "credentials": {"supabaseApi": CRED_SUPABASE},
            "continueOnFail": True,
        },
        {
            "id": "sb_insert_conv",
            "name": "SB - Insert Conversacion",
            "type": "n8n-nodes-base.supabase",
            "typeVersion": 1,
            "position": [1380, 300],
            "parameters": {
                "operation": "create",
                "tableId": "conversaciones",
                "fieldsUi": {
                    "fieldValues": [
                        {"fieldId": "paciente_id", "fieldValue": "={{ $('SB - Upsert Paciente').item.json.id }}"},
                        {"fieldId": "telefono", "fieldValue": "={{ $('Parse mensajes').item.json.telefono }}"},
                        {"fieldId": "rol", "fieldValue": "={{ $('Parse mensajes').item.json.rol }}"},
                        {"fieldId": "mensaje", "fieldValue": "={{ $('Parse mensajes').item.json.mensaje }}"},
                        {"fieldId": "fuente", "fieldValue": "={{ $('Parse mensajes').item.json.fuente }}"},
                        {"fieldId": "timestamp", "fieldValue": "={{ $('Parse mensajes').item.json.created_at }}"},
                        {"fieldId": "metadata", "fieldValue": "={{ JSON.stringify($('Parse mensajes').item.json.metadata) }}"},
                    ]
                },
            },
            "credentials": {"supabaseApi": CRED_SUPABASE},
            "continueOnFail": True,
        },
        {
            "id": "code_update",
            "name": "Update last_synced",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1620, 300],
            "parameters": {"jsCode": CODE_UPDATE_LAST_SYNCED},
        },
    ],
    "connections": {
        "Cron 30s": {"main": [[{"node": "Get last_synced", "type": "main", "index": 0}]]},
        "Get last_synced": {"main": [[{"node": "PG - SELECT nuevos", "type": "main", "index": 0}]]},
        "PG - SELECT nuevos": {"main": [[{"node": "Parse mensajes", "type": "main", "index": 0}]]},
        "Parse mensajes": {"main": [[{"node": "SB - Upsert Paciente", "type": "main", "index": 0}]]},
        "SB - Upsert Paciente": {"main": [[{"node": "SB - Insert Conversacion", "type": "main", "index": 0}]]},
        "SB - Insert Conversacion": {"main": [[{"node": "Update last_synced", "type": "main", "index": 0}]]},
    },
    "settings": {
        "executionOrder": "v1",
        "timezone": "America/Argentina/Buenos_Aires",
        "saveExecutionProgress": True,
        "saveManualExecutions": True,
        "saveDataErrorExecution": "all",
        "saveDataSuccessExecution": "all",
    },
}


def main():
    if DRY_RUN:
        Path("workflows/history").mkdir(parents=True, exist_ok=True)
        dry = "workflows/history/logger_conversaciones_DRY.json"
        Path(dry).write_text(json.dumps(WF, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"DRY -> {dry}")
        return

    print("Creating workflow...")
    status, resp = http("POST", "/workflows", WF)
    print(f"  POST: {status}")
    wid = resp.get("id")
    print(f"  workflow id: {wid}")
    Path("workflows/current").mkdir(parents=True, exist_ok=True)
    Path("workflows/current/logger_conversaciones.json").write_text(
        json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  saved to workflows/current/logger_conversaciones.json")
    print(f"\nNOT activated yet. Activate manually after review:")
    print(f"  python -c \"import urllib.request,json; r=urllib.request.Request('{API_BASE}/workflows/{wid}/activate',method='POST',headers={{'X-N8N-API-KEY':'<key>'}}); urllib.request.urlopen(r)\"")


if __name__ == "__main__":
    main()
