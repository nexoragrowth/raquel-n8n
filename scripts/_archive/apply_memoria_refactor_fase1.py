"""REFACTOR MEMORIA FASE 1+2+3 — limpieza histórica + cron protectivo + filtro Router.

PROBLEMA (auditoría 03/06):
- LangChain auto-save mete a memoria: intent tokens crudos del Router ("agendar_nuevo",
  "consulta_general", etc.), templates "[CONTEXTO DEL PACIENTE QUE ESCRIBE]\\nphone:..."
  como human messages, outputs prohibidos pre-Banlist, [NO_REPLY] markers.
- Cada turno deja ~4 filas (2 humans + 2 ais), 50% basura. Ventana LLM desperdiciada.

CAMBIOS:
1. CLEANUP HISTÓRICO: DELETE filas con contenido basura.
2. CRON LIMPIEZA: workflow nuevo que corre cada 30 min y borra basura nueva.
3. BUILD ROUTER CONTEXT: actualizar query para filtrar más tipos de basura.

Modo: --apply / --dry
"""
from __future__ import annotations
import argparse, json, os, sys, io, time
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
V6_ID = "O155MqHgOSaNZ9ye"
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

INTENT_TOKENS = ['agendar_nuevo','consulta_general','cancelar_o_reprogramar','confirmar_post_recordatorio','urgencia_dolor']
INTENT_SQL_LIST = "(" + ", ".join(f"'{t}'" for t in INTENT_TOKENS) + ")"

# Patrón "[CONTEXTO DEL PACIENTE QUE ESCRIBE]" + similares
CLEANUP_QUERY = f"""
DELETE FROM n8n_chat_histories
WHERE
  -- intent tokens crudos (basura del Router auto-save)
  (message->>'type' = 'ai' AND message->>'content' IN {INTENT_SQL_LIST})
  OR
  -- [CONTEXTO DEL PACIENTE QUE ESCRIBE]... templates inflados como human
  (message->>'type' = 'human' AND message->>'content' LIKE '[CONTEXTO%')
  OR
  -- [NO_REPLY] markers huerfanos
  (message->>'type' = 'ai' AND message->>'content' = '[NO_REPLY]')
RETURNING id, session_id, message->>'type' as tipo, LEFT(message->>'content', 80) as preview
"""

# Workflow CRON: borrar basura cada 30 min
CRON_WF_NAME = "[ADMIN] Cron Cleanup Memoria Basura"

def get_pg_creds():
    v6 = requests.get(f"{BASE}/api/v1/workflows/{V6_ID}", headers=H, timeout=60).json()
    pg = next(n for n in v6["nodes"] if n["type"] == "n8n-nodes-base.postgres")
    return pg.get("credentials", {})


def cleanup_historic(apply_real):
    """Borra basura histórica de n8n_chat_histories."""
    pg_creds = get_pg_creds()
    nodes = [
        {"name": "WH", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [200, 300],
         "parameters": {"path": "cleanup-historic", "httpMethod": "POST", "responseMode": "lastNode"}, "webhookId": "cleanup-historic"},
        {"name": "DELETE Basura", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": [400, 300],
         "parameters": {"operation": "executeQuery", "query": CLEANUP_QUERY, "options": {}},
         "credentials": pg_creds},
    ]
    conns = {"WH": {"main": [[{"node": "DELETE Basura", "type": "main", "index": 0}]]}}
    body = {"name": "TEST Cleanup Basura Historica", "nodes": nodes, "connections": conns, "settings": {"executionOrder": "v1"}}
    existing = requests.get(f"{BASE}/api/v1/workflows", headers=H, params={"name": body["name"]}, timeout=30).json()
    test_wf = next((w for w in existing.get("data", []) if w.get("name") == body["name"]), None)
    if test_wf:
        wid = test_wf["id"]; requests.put(f"{BASE}/api/v1/workflows/{wid}", headers=H, json=body, timeout=40).raise_for_status()
    else:
        r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=body, timeout=40); wid = r.json()["id"]
    requests.post(f"{BASE}/api/v1/workflows/{wid}/activate", headers=H, timeout=30)
    if not apply_real:
        print("[1] cleanup workflow listo pero NO disparado (dry-run)"); return
    print("[1] disparando cleanup historico...")
    r = requests.post(f"{BASE.replace('/api/v1','')}/webhook/cleanup-historic", json={}, timeout=60)
    print(f"   response: {r.status_code}")
    time.sleep(3)
    ex = requests.get(f"{BASE}/api/v1/executions?workflowId={wid}&limit=1", headers=H, timeout=30).json()
    eid = ex["data"][0]["id"]
    full = requests.get(f"{BASE}/api/v1/executions/{eid}?includeData=true", headers=H, timeout=30).json()
    out = full.get("data", {}).get("resultData", {}).get("runData", {}).get("DELETE Basura", [{}])[0].get("data", {}).get("main", [[]])[0]
    print(f"[1] filas borradas: {len(out)}")
    # Sample
    if out:
        print(f"   sample (primeras 5):")
        for it in out[:5]:
            j = it.get("json", {})
            print(f"     id={j.get('id')} session_id={j.get('session_id')} tipo={j.get('tipo')} preview={j.get('preview','')[:60]!r}")


def setup_cron_cleanup(apply_real):
    """Crea o actualiza el workflow CRON que limpia basura cada 30 min."""
    pg_creds = get_pg_creds()
    nodes = [
        {"name": "Cron 30 min", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [200, 300],
         "parameters": {"rule": {"interval": [{"field": "minutes", "minutesInterval": 30}]}}},
        {"name": "DELETE Basura", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": [400, 300],
         "parameters": {"operation": "executeQuery", "query": CLEANUP_QUERY, "options": {}},
         "credentials": pg_creds},
    ]
    conns = {"Cron 30 min": {"main": [[{"node": "DELETE Basura", "type": "main", "index": 0}]]}}
    body = {"name": CRON_WF_NAME, "nodes": nodes, "connections": conns, "settings": {"executionOrder": "v1"}}
    existing = requests.get(f"{BASE}/api/v1/workflows", headers=H, params={"name": CRON_WF_NAME}, timeout=30).json()
    test_wf = next((w for w in existing.get("data", []) if w.get("name") == CRON_WF_NAME), None)
    if test_wf:
        wid = test_wf["id"]; print(f"[2] reuso cron {wid}")
        if apply_real: requests.put(f"{BASE}/api/v1/workflows/{wid}", headers=H, json=body, timeout=40).raise_for_status()
    elif apply_real:
        r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=body, timeout=40); wid = r.json()["id"]
        print(f"[2] cron creado {wid}")
    else:
        print("[2] cron listo pero no creado (dry)"); return
    requests.post(f"{BASE}/api/v1/workflows/{wid}/activate", headers=H, timeout=30)
    print(f"[2] cron activado (corre cada 30 min)")


def update_build_router_context(apply_real):
    """Mejora el SQL de 'Build Router Context' para filtrar más basura."""
    wf = requests.get(f"{BASE}/api/v1/workflows/{V6_ID}", headers=H, timeout=60).json()
    n = next((x for x in wf["nodes"] if x["name"] == "Build Router Context"), None)
    if not n:
        print("[3] !! Build Router Context no existe (probable Fase 0 no aplicada)"); return
    NEW_QUERY = (
        "SELECT COALESCE(string_agg("
        "  CASE message->>'type' "
        "    WHEN 'human' THEN 'PACIENTE: ' "
        "    WHEN 'ai' THEN 'BOT: ' "
        "    ELSE 'SYSTEM: ' "
        "  END || (message->>'content'), "
        "  E'\\n---\\n' ORDER BY id ASC"
        "), '(sin mensajes previos)') AS ctx "
        "FROM ("
        "  SELECT id, message FROM n8n_chat_histories "
        "  WHERE session_id = '{{ $json.phone }}' "
        # Filtrar intent tokens
        f"  AND (message->>'content') NOT IN {INTENT_SQL_LIST} "
        # Filtrar templates contexto inflado
        "  AND (message->>'content') NOT LIKE '[CONTEXTO%' "
        # Filtrar NO_REPLY huerfanos
        "  AND (message->>'content') != '[NO_REPLY]' "
        "  ORDER BY id DESC LIMIT 6"
        ") recent"
    )
    n["parameters"]["query"] = NEW_QUERY
    if not apply_real:
        print("[3] Build Router Context update listo (dry)"); return
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{V6_ID}", headers=H, json=body, timeout=40)
    if not r.ok: print("[3] PUT FAIL", r.status_code, r.text[:200]); return
    print(f"[3] Build Router Context query actualizada (filtra intent_tokens + [CONTEXTO + [NO_REPLY])")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    apply_real = args.apply

    print(f"=== REFACTOR MEMORIA FASE 1+2+3 ({'APPLY' if apply_real else 'DRY'}) ===\n")
    cleanup_historic(apply_real)
    print()
    setup_cron_cleanup(apply_real)
    print()
    update_build_router_context(apply_real)
    print(f"\n{'✅ APLICADO' if apply_real else '[dry] no aplicado'}")


if __name__ == "__main__":
    main()
