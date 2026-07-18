"""
Filtra [NO_REPLY] de la memoria post-hoc (#25).

Razon: LangChain Postgres Chat Memory auto-persiste el output del agent,
incluyendo cuando el output es la string literal [NO_REPLY]. Esa string queda
como AIMessage en `n8n_chat_histories` y al hidratar memoria el LLM la ve
("yo dije [NO_REPLY] antes?"), ensucia el contexto.

Como el persist es automatico de LangChain (no hay nodo intermedio), aplicamos
cleanup post-hoc: cuando el flow detecta `[NO_REPLY]` en el output (rama FALSE
de "Tiene respuesta?"), borramos el ultimo AIMessage con ese content para
esa session.

Cambios:
  - Crear nodo "PG - Delete NO_REPLY" (Postgres executeQuery)
  - Reconectar: Tiene respuesta? FALSE -> PG - Delete NO_REPLY -> Descartar [NO_REPLY]
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

PG_CRED = {"postgres": {"id": "xwvjww5Odcxiy1K9", "name": "Postgres account"}}
NEW_NODE = "PG - Delete NO_REPLY"

DELETE_SQL = (
    "DELETE FROM n8n_chat_histories WHERE id IN ("
    "SELECT id FROM n8n_chat_histories "
    "WHERE session_id = $1 "
    "AND message::jsonb->>'type' = 'ai' "
    "AND message::jsonb->>'content' = '[NO_REPLY]' "
    "ORDER BY id DESC LIMIT 1)"
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
    print(f"  active={wf['active']} nodes={len(wf['nodes'])}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_FILTER_NOREPLY_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    existing = {n["name"] for n in wf["nodes"]}
    if NEW_NODE in existing:
        sys.exit(f"ABORT: {NEW_NODE} ya existe")

    descartar = next((n for n in wf["nodes"] if n["name"] == "Descartar [NO_REPLY]"), None)
    if descartar is None:
        sys.exit("ABORT: nodo Descartar [NO_REPLY] no encontrado")
    dx, dy = descartar["position"]

    # Nodo nuevo: PG - Delete NO_REPLY
    new_node = {
        "parameters": {
            "operation": "executeQuery",
            "query": DELETE_SQL,
            "options": {
                "queryReplacement": "={{ $('Preparar Mensaje Final').first().json.phone }}"
            },
        },
        "id": "pg-del-noreply-001",
        "name": NEW_NODE,
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [dx - 260, dy],
        "credentials": PG_CRED,
        "onError": "continueRegularOutput",
    }
    wf["nodes"].append(new_node)

    # Reconectar: Tiene respuesta? FALSE (branch 1) -> PG - Delete NO_REPLY -> Descartar [NO_REPLY]
    conns = wf["connections"]
    tr = conns.get("Tiene respuesta?", {}).get("main", [])
    if len(tr) < 2:
        sys.exit("ABORT: Tiene respuesta? no tiene 2 branches")
    false_branch = tr[1]
    if not any(e.get("node") == "Descartar [NO_REPLY]" for e in false_branch):
        sys.exit(f"ABORT: Tiene respuesta? FALSE no apunta a Descartar [NO_REPLY]. Actual: {false_branch}")
    new_false = [
        {"node": NEW_NODE, "type": "main", "index": 0}
        if e.get("node") == "Descartar [NO_REPLY]" else e
        for e in false_branch
    ]
    conns["Tiene respuesta?"]["main"][1] = new_false

    conns[NEW_NODE] = {
        "main": [[{"node": "Descartar [NO_REPLY]", "type": "main", "index": 0}]]
    }

    if DRY_RUN:
        out = f"workflows/history/v6_FILTER_NOREPLY_DRY_{ts}.json"
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
    names = {n["name"] for n in wf2["nodes"]}
    assert NEW_NODE in names, "FAIL: nodo no se creo"
    print(f"  verified {NEW_NODE!r} present")

    post_path = f"workflows/history/v6_POST_FILTER_NOREPLY_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
