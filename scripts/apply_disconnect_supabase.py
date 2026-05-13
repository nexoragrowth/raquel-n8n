"""
Desconecta los 5 nodos Supabase rotos (tablas no existen, 404 silencioso):

INPUT chain (lead/paciente check):
  - Supabase - Buscar Paciente
  - Existe Paciente?
  - Supabase - Crear Paciente
  Re-conexion: Bot Activo? FALSE -> Check Session Age (directo)
  Logica futura: el sub-agent Agendar maneja lead vs paciente via Dentalink tools.

OUTPUT chain (loggers):
  - Supabase - Guardar Msg Usuario
  - Supabase - Guardar Msg Asistente
  No tienen sucesores. La memoria real vive en Postgres n8n_chat_histories.

NO se tocan los 5 nodos. Solo se remueven del workflow.
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

REMOVE = {
    "Supabase - Buscar Paciente",
    "Existe Paciente?",
    "Supabase - Crear Paciente",
    "Supabase - Guardar Msg Usuario",
    "Supabase - Guardar Msg Asistente",
}


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
    backup_path = f"workflows/history/v6_PRE_DISCONNECT_SB_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    # 1) Remover nodos
    before = len(wf["nodes"])
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in REMOVE]
    removed_count = before - len(wf["nodes"])
    print(f"  removed {removed_count} nodes")

    # 2) Re-cablear: Bot Activo? branch FALSE (index 1) que apuntaba a "Supabase - Buscar Paciente"
    #    ahora apunta a "Check Session Age"
    conns = wf["connections"]
    bot_activo = conns.get("Bot Activo?", {}).get("main", [])
    if len(bot_activo) >= 2:
        false_branch = bot_activo[1] or []
        new_false = []
        for e in false_branch:
            if e.get("node") == "Supabase - Buscar Paciente":
                new_false.append({"node": "Check Session Age", "type": "main", "index": 0})
            elif e.get("node") in REMOVE:
                continue
            else:
                new_false.append(e)
        conns["Bot Activo?"]["main"][1] = new_false
        print(f"  Bot Activo? FALSE -> {[e['node'] for e in new_false]}")
    else:
        print("  WARN: Bot Activo? has <2 branches")

    # 3) Remover entries de los nodos eliminados como SOURCE
    for nm in list(conns.keys()):
        if nm in REMOVE:
            del conns[nm]

    # 4) Quitar referencias a los nodos removidos como TARGET (cualquier branch)
    for src, c in conns.items():
        for bt, branches in c.items():
            for i, b in enumerate(branches or []):
                if b:
                    c[bt][i] = [e for e in b if e.get("node") not in REMOVE]

    # 5) Sanity check: verificar que ya no quedan referencias
    orphans = []
    for src, c in conns.items():
        for bt, branches in c.items():
            for b in branches or []:
                for e in b or []:
                    if e.get("node") in REMOVE:
                        orphans.append((src, e["node"]))
    if orphans:
        print(f"  WARN: orphan refs still found: {orphans}")

    if DRY_RUN:
        out = f"workflows/history/v6_DISCONNECT_SB_DRY_{ts}.json"
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

    post_path = f"workflows/history/v6_POST_DISCONNECT_SB_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
