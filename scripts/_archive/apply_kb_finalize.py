"""
Finaliza la integracion KB Vector Store:

  1. Agrega Option `queryName = 'buscar_conocimiento'` al nodo Supabase Vector
     Store. Sin esto, por default busca la RPC `match_documents` que no
     existe en la BD clinica.

  2. Saca el bloque KB del system prompt del Sub-Agent General (los ~9KB
     inyectados previamente). El Vector Store ahora cumple esa funcion como
     tool, asi que tener la KB tambien en el prompt seria duplicado.

Antes de aplicar:
  - El nodo Supabase Vector Store debe estar conectado al Sub-Agent General
  - Los 23 docs safe deben tener embedding != NULL
"""
import json
import os
import re
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

KB_BLOCK_MARKER = "= BASE DE CONOCIMIENTO (responder si la pregunta encaja"


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
    backup_path = f"workflows/history/v6_PRE_KB_FINALIZE_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    # === FIX 1: Agregar queryName al Vector Store ===
    vs_node = next(
        (n for n in wf["nodes"] if n["type"] == "@n8n/n8n-nodes-langchain.vectorStoreSupabase"),
        None,
    )
    if not vs_node:
        sys.exit("ABORT: Supabase Vector Store node no encontrado")

    p = vs_node["parameters"]
    opts = p.get("options")
    if isinstance(opts, list):
        opts = {}  # n8n a veces serializa [] cuando esta vacio
    elif opts is None:
        opts = {}
    if opts.get("queryName") == "buscar_conocimiento":
        print(f"  Vector Store queryName ya OK: {opts.get('queryName')!r}")
    else:
        opts["queryName"] = "buscar_conocimiento"
        p["options"] = opts
        print(f"  Vector Store: queryName -> 'buscar_conocimiento'")

    # === FIX 2: Sacar el bloque KB del prompt del Sub-Agent General ===
    gen_node = next((n for n in wf["nodes"] if n["name"] == "Sub-Agent General"), None)
    if not gen_node:
        sys.exit("ABORT: Sub-Agent General no encontrado")

    sm = gen_node["parameters"].get("options", {}).get("systemMessage", "")
    if KB_BLOCK_MARKER not in sm:
        print(f"  Sub-Agent General: no tiene bloque KB inyectado (idempotent)")
    else:
        idx = sm.find(KB_BLOCK_MARKER)
        # Buscar el inicio real del bloque (que empieza con dos newlines + el titulo)
        # El bloque arranca con "\n\n= BASE DE CONOCIMIENTO..."
        start = sm.rfind("\n\n= BASE DE CONOCIMIENTO", 0, idx + 100)
        if start < 0:
            start = idx
        new_sm = sm[:start].rstrip() + "\n"
        gen_node["parameters"]["options"]["systemMessage"] = new_sm
        print(f"  Sub-Agent General: {len(sm)} -> {len(new_sm)} chars ({len(sm)-len(new_sm)} chars removidos)")

    if DRY_RUN:
        out = f"workflows/history/v6_KB_FINALIZE_DRY_{ts}.json"
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
    # Verify
    for n in wf2["nodes"]:
        if n["type"] == "@n8n/n8n-nodes-langchain.vectorStoreSupabase":
            qn = n["parameters"].get("options", {}).get("queryName")
            assert qn == "buscar_conocimiento", f"FAIL: queryName quedo {qn!r}"
            print(f"  verified queryName='buscar_conocimiento'")
        if n["name"] == "Sub-Agent General":
            sm2 = n["parameters"]["options"]["systemMessage"]
            assert KB_BLOCK_MARKER not in sm2, "FAIL: bloque KB todavia en el prompt"
            print(f"  verified KB block removed from Sub-Agent General prompt")
    print(f"  active={wf2['active']}")

    post_path = f"workflows/history/v6_POST_KB_FINALIZE_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
