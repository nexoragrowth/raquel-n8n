"""
Fix #26: Clear Old Memory selectivo + cleanup de Handle Stale Session.

Bugs actuales:
  1) Handle Stale Session referencia $('Supabase - Buscar Paciente') que ya
     no existe (lo desconectamos). Va a romper en runtime.
  2) Clear Old Memory borra TODO si is_stale_session=true. No preserva las
     "notas internas" del recordatorio (additional_kwargs.source =
     reminder_note/wa_outbound/human_takeover). Resultado: paciente responde
     al recordatorio 4 dias despues -> bot pide DNI desde cero.
  3) SQL con string interpolation en lugar de params bound (SQL injection
     prone, ademas el campo is_stale_session llegaba como string).

Cambios:
  - Handle Stale Session: quitar ref a Supabase - Buscar Paciente.
  - Clear Old Memory: nueva query con SQL params bound + WHERE que excluye
    sources protegidas. Tambien usa $2::boolean en lugar de comparar strings.
"""
import json
import os
import sys
import time
import urllib.request

WF_ID = "O155MqHgOSaNZ9ye"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
API_KEY = os.environ.get("N8N_API_KEY")
DRY_RUN = "--dry-run" in sys.argv

if not API_KEY:
    sys.exit("ERROR: N8N_API_KEY")

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow",
    "timezone", "executionOrder", "callerPolicy", "callerIds",
}

NEW_HANDLE_STALE_JS = """const result = $input.first().json;
const phone = $('Preparar Mensaje Final').first().json.phone;

let isStale = false;
const hasHistory = result.id !== null && result.id !== undefined && !result.error && !result.message;

if (hasHistory && result.created_at) {
  const lastMsg = new Date(result.created_at);
  const now = new Date();
  const diffDays = (now - lastMsg) / (1000 * 60 * 60 * 24);
  isStale = diffDays > 3;
}

return [{
  json: {
    ...$('Preparar Mensaje Final').first().json,
    has_history: hasHistory,
    is_stale_session: isStale,
    session_phone: phone
  }
}];
"""

NEW_CLEAR_MEMORY_SQL = (
    "DELETE FROM n8n_chat_histories "
    "WHERE session_id = $1 "
    "AND $2::boolean = true "
    "AND COALESCE(message::jsonb->'additional_kwargs'->>'source', '') "
    "NOT IN ('wa_outbound', 'human_takeover', 'reminder_note') "
    "RETURNING id"
)
NEW_CLEAR_MEMORY_REPLACEMENT = (
    "={{ $json.session_phone }}, ={{ $json.is_stale_session }}"
)


def http(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        headers={
            "X-N8N-API-KEY": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


def main():
    print(f"GET workflow {WF_ID}...")
    _, wf = http("GET", f"/workflows/{WF_ID}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_CLEAR_MEM_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    hs = next((n for n in wf["nodes"] if n["name"] == "Handle Stale Session"), None)
    cm = next((n for n in wf["nodes"] if n["name"] == "Clear Old Memory"), None)
    if not hs:
        sys.exit("ABORT: Handle Stale Session not found")
    if not cm:
        sys.exit("ABORT: Clear Old Memory not found")

    old_js = hs["parameters"].get("jsCode", "")
    if "Supabase - Buscar Paciente" not in old_js:
        print("  WARN: Handle Stale Session ya no referencia Supabase - Buscar Paciente, idempotent")
    hs["parameters"]["jsCode"] = NEW_HANDLE_STALE_JS
    print(f"  Handle Stale Session jsCode updated ({len(old_js)} -> {len(NEW_HANDLE_STALE_JS)} chars)")

    old_query = cm["parameters"].get("query", "")
    cm["parameters"]["query"] = NEW_CLEAR_MEMORY_SQL
    cm["parameters"]["options"] = {"queryReplacement": NEW_CLEAR_MEMORY_REPLACEMENT}
    print(f"  Clear Old Memory query updated")
    print(f"    old: {old_query[:150]}...")
    print(f"    new: {NEW_CLEAR_MEMORY_SQL[:150]}...")

    if DRY_RUN:
        out = f"workflows/history/v6_CLEAR_MEM_DRY_{ts}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"DRY RUN -> {out}")
        return

    settings = {k: v for k, v in wf.get("settings", {}).items() if k in ALLOWED_SETTINGS}
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": settings,
        "staticData": wf.get("staticData"),
    }
    print("PUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  status={status}")

    _, wf2 = http("GET", f"/workflows/{WF_ID}")
    for n in wf2["nodes"]:
        if n["name"] == "Handle Stale Session":
            assert "Supabase - Buscar Paciente" not in n["parameters"]["jsCode"]
        if n["name"] == "Clear Old Memory":
            assert "additional_kwargs" in n["parameters"]["query"]
    print("  verified")

    post_path = f"workflows/history/v6_POST_CLEAR_MEM_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
