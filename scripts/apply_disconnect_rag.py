"""
Desconecta el RAG `buscar_conocimiento` (#27).

Razon: la tabla `knowledge_base` apuntada esta contaminada (88 rows de
marketing Nexora, 0 docs clinicos). Vector dim mismatch (1536 vs 384) hace
que la RPC `match_knowledge` retorne 400 silencioso. La tool nunca devolvio
nada util pero el Sub-Agent General puede llamarla y eventualmente citar
basura si se "arregla" sin curar la base.

Cambios:
  - Remover nodo `buscar_conocimiento` (tipo vectorStoreSupabase)
  - Remover nodo `Embeddings OpenAI` (solo se usaba para alimentar al RAG)
  - Las conexiones se limpian (es ai_tool del Sub-Agent General y ai_embedding del RAG)
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

REMOVE = {"buscar_conocimiento", "Embeddings OpenAI"}


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
    backup_path = f"workflows/history/v6_PRE_DISCONNECT_RAG_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    before = len(wf["nodes"])
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in REMOVE]
    print(f"  removed {before - len(wf['nodes'])} nodes")

    conns = wf["connections"]
    for nm in list(conns.keys()):
        if nm in REMOVE:
            del conns[nm]
    for src, c in conns.items():
        for bt, branches in c.items():
            for i, b in enumerate(branches or []):
                if b:
                    c[bt][i] = [e for e in b if e.get("node") not in REMOVE]

    if DRY_RUN:
        out = f"workflows/history/v6_DISCONNECT_RAG_DRY_{ts}.json"
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
    for r in REMOVE:
        assert r not in names, f"FAIL: {r} todavia presente"
    print(f"  verified {len(REMOVE)} nodes removed")
    print(f"  final node count: {len(wf2['nodes'])}")

    post_path = f"workflows/history/v6_POST_DISCONNECT_RAG_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
