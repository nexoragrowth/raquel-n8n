"""URGENTE — v6 main: el output del Sub-WF Cancelar (mensaje al paciente)
NUNCA se grababa a n8n_chat_histories. Cada vez que el bot respondia via
Sub-WF Cancelar, la siguiente exec NO tenia constancia y el bot reevaluaba
desde cero -> ofrecia el mismo "varios turnos" repetidamente (caso Pilar 03/06).

Patron analogo al bug del cron de memoria (fix 02/06): 'silencio invisible'.

Fix: agregar nodo Postgres - Save Sub-WF Output que escriba el output como
AI message con source='wa_outbound'. Conectar:
  Format Sub-WF Output --> [Save Sub-WF Output to Memory] --> Fallback Output

El path original de Format Sub-WF Output -> Fallback Output se MANTIENE,
pero pasa por el nuevo nodo INSERT primero.

Source 'wa_outbound' es el que Clear Old Memory preserva (no se limpia).

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

NEW_NODE_NAME = "Save Sub-WF Output to Memory"

# message JSON LangChain format: { type: 'ai', content: <output>, additional_kwargs: { source: 'wa_outbound' }, ... }
# Para Postgres usamos queryReplacement con phone + jsonb stringified.
NEW_NODE = {
    "name": NEW_NODE_NAME,
    "type": "n8n-nodes-base.postgres",
    "typeVersion": 2.5,
    "position": [0, 0],  # se setea programatically post-clone
    "parameters": {
        "operation": "executeQuery",
        "query": "INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)",
        "options": {
            "queryReplacement": "={{ $('Edit Fields - Extraer Datos').first().json.phone }}, ={{ JSON.stringify({ type: 'ai', content: $json.output, tool_calls: [], additional_kwargs: { source: 'wa_outbound' }, response_metadata: {}, invalid_tool_calls: [] }) }}",
        },
    },
}


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

    # idempotency
    if any(n["name"] == NEW_NODE_NAME for n in wf["nodes"]):
        print(f"!! '{NEW_NODE_NAME}' ya existe, abortando"); sys.exit(3)

    # find Format Sub-WF Output + actual outgoing connection
    fsw = next((n for n in wf["nodes"] if n["name"] == "Format Sub-WF Output"), None)
    if not fsw: print("!! 'Format Sub-WF Output' no encontrado"); sys.exit(2)
    fsw_pos = fsw.get("position", [0, 0])

    # Find credentials of an existing postgres node (reuse same cred)
    pg_ref = next((n for n in wf["nodes"] if n["type"] == "n8n-nodes-base.postgres"), None)
    if not pg_ref: print("!! no encontre nodo postgres existente para reusar credentials"); sys.exit(2)
    creds = pg_ref.get("credentials", {})

    # Position new node next to FSW
    new_node = dict(NEW_NODE)
    new_node["position"] = [fsw_pos[0] + 220, fsw_pos[1]]
    new_node["credentials"] = creds
    # add stable id
    new_node["id"] = "save-subwf-output-memory"

    # Add the node
    wf["nodes"].append(new_node)

    # Rewire connection: Format Sub-WF Output -> Save Sub-WF Output to Memory -> Fallback Output
    conn = wf["connections"]
    fsw_outs = conn.get("Format Sub-WF Output", {}).get("main", [])
    if not fsw_outs or not fsw_outs[0]:
        print("!! Format Sub-WF Output no tiene outgoing connection"); sys.exit(2)
    original_targets = list(fsw_outs[0])  # ej: [{node: 'Fallback Output', type: 'main', index: 0}]

    # Format Sub-WF Output ahora apunta a Save Sub-WF Output to Memory
    conn["Format Sub-WF Output"]["main"][0] = [{"node": NEW_NODE_NAME, "type": "main", "index": 0}]
    # Save Sub-WF Output to Memory -> original_targets
    conn[NEW_NODE_NAME] = {"main": [original_targets]}

    print(f"Agregado nodo '{NEW_NODE_NAME}'")
    print(f"  conexion vieja: Format Sub-WF Output -> {[t['node'] for t in original_targets]}")
    print(f"  conexion nueva: Format Sub-WF Output -> {NEW_NODE_NAME} -> {[t['node'] for t in original_targets]}")
    print(f"  credentials: {creds.get('postgres', {}).get('name', '?')}")
    print(f"  position: {new_node['position']}")

    if args.dry or not args.apply: print("\n[dry] no aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_subwf_writeback_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_wf()
    n2 = next((x for x in wf2["nodes"] if x["name"] == NEW_NODE_NAME), None)
    ok = bool(n2) and conn[NEW_NODE_NAME]["main"][0][0]["node"] in [t["node"] for t in original_targets]
    print(f"[verify] {'OK' if n2 else 'FAIL'} nodo creado")


if __name__ == "__main__":
    main()
