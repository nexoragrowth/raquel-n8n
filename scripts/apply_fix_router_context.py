"""URGENTE - Router ciego al contexto: hoy mismo desconecte el Router del Postgres
Chat Memory para frenar contaminacion con tokens de intent. Eso lo dejo SIN ver
los mensajes anteriores -> "genial si" sin contexto se clasifica como
consulta_general -> Sub-Agent General devuelve [NO_REPLY] -> paciente queda colgado.

Fix: agregar nodo Postgres "Build Router Context" que selecciona las ultimas 6
filas de n8n_chat_histories y las formatea como string. Pasarlas al Router como
parte del text input (NO via ai_memory edge, asi no escribe basura en memoria).

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
WF_ID = "O155MqHgOSaNZ9ye"; H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

NEW_NODE_NAME = "Build Router Context"

# Query: trae las ultimas 6 filas y las formatea
# Filtra NOTA INTERNA (additional_kwargs.source = 'reminder_note' Y content empieza con [NOTA INTERNA])
# Esas las dejamos pasar igual porque dan contexto.
QUERY = (
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
    "  AND (message->>'content') NOT IN ('agendar_nuevo','consulta_general','cancelar_o_reprogramar','confirmar_post_recordatorio','urgencia_dolor') "
    "  ORDER BY id DESC LIMIT 6"
    ") recent"
)


def get_wf():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60); r.raise_for_status(); return r.json()


def put_wf(wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:500], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()
    nodes_by_name = {n["name"]: n for n in wf["nodes"]}
    conn = wf["connections"]

    if NEW_NODE_NAME in nodes_by_name:
        print("!! ya aplicado"); sys.exit(3)

    prep = nodes_by_name.get("Preparar Mensaje Final")
    router = nodes_by_name.get("Router - Clasificar Intent")
    if not prep or not router:
        print("!! Preparar Mensaje Final o Router no encontrados"); sys.exit(2)

    pg_ref = next((n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.postgres"), None)
    creds = pg_ref.get("credentials", {}) if pg_ref else {}

    # 1. Crear el nodo
    new_node = {
        "id": "build-router-ctx",
        "name": NEW_NODE_NAME,
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [prep["position"][0] + 220, prep["position"][1]],
        "parameters": {
            "operation": "executeQuery",
            "query": QUERY,
            "options": {},
        },
        "credentials": creds,
        "onError": "continueRegularOutput",  # si falla SELECT, no frenamos el flow
    }
    wf["nodes"].append(new_node)

    # 2. Rewire: Preparar Mensaje Final -> Build Router Context -> (lo que Preparar apuntaba antes)
    prep_outs = conn.get("Preparar Mensaje Final", {}).get("main", [[]])[0]
    original_targets = list(prep_outs)
    conn["Preparar Mensaje Final"] = {"main": [[{"node": NEW_NODE_NAME, "type": "main", "index": 0}]]}
    conn[NEW_NODE_NAME] = {"main": [original_targets]}

    print(f"Agregado '{NEW_NODE_NAME}' entre Preparar Mensaje Final y {[t['node'] for t in original_targets]}")

    # 3. Modificar el text input del Router para incluir contexto
    old_text = router["parameters"]["text"]
    new_text = (
        "=CONTEXTO DE LA CONVERSACION (ultimos turnos, mas recientes al final):\n"
        "{{ $('Build Router Context').first().json.ctx || '(sin contexto)' }}\n\n"
        "MENSAJE ACTUAL DEL PACIENTE:\n"
        "{{ $('Preparar Mensaje Final').first().json.text }}"
    )
    router["parameters"]["text"] = new_text
    print(f"Router text input modificado: incluye CONTEXTO + MENSAJE ACTUAL")

    if args.dry or not args.apply: print("[dry] no aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_router_context_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_wf()
    nm2 = {n["name"]: n for n in wf2["nodes"]}
    ok = NEW_NODE_NAME in nm2 and "CONTEXTO DE LA CONVERSACION" in nm2["Router - Clasificar Intent"]["parameters"]["text"]
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
