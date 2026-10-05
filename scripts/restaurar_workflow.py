# -*- coding: utf-8 -*-
"""
restaurar_workflow.py — vuelve un workflow de n8n a una version guardada en workflows/history/ (backup PRE de un cambio).

Hace un PUT con el contenido del backup (name, nodes, connections, settings filtrados, staticData). NO cambia si el workflow
esta activo o no. Antes de escribir guarda un backup del estado actual (label RESTORE_PRE).

USO:
    python scripts/restaurar_workflow.py workflows/history/O155MqHgOSaNZ9ye_PRE_directrices_1791190000.json            # simulacion
    python scripts/restaurar_workflow.py workflows/history/O155MqHgOSaNZ9ye_PRE_directrices_1791190000.json --apply    # restaura

Regla del proyecto: con OK de Lucas. Es la salida de emergencia si un cambio sale mal: queda como estaba antes del cambio.
"""
import argparse, json, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8")
HIST = Path(__file__).resolve().parent.parent / "workflows" / "history"
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("backup")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    bk = json.loads(Path(a.backup).read_text(encoding="utf-8"))
    wid = bk["id"]
    actual = api(f"/workflows/{wid}")
    na, nb = {n["name"] for n in actual["nodes"]}, {n["name"] for n in bk["nodes"]}
    print(f"workflow {wid} '{bk['name']}': backup de {str(bk.get('updatedAt'))[:19]} ({len(bk['nodes'])} nodos) -> actual {str(actual.get('updatedAt'))[:19]} ({len(actual['nodes'])} nodos)")
    print("  nodos que se van a quitar:", sorted(na - nb) or "ninguno", "| nodos que se van a volver a agregar:", sorted(nb - na) or "ninguno")
    if not a.apply:
        print("\n[SIMULACION] No se cambio nada. Correr con --apply (con OK de Lucas).")
        return
    HIST.mkdir(parents=True, exist_ok=True)
    dest = HIST / f"{wid}_RESTORE_PRE_{int(time.time())}.json"
    dest.write_text(json.dumps(actual, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  backup del estado actual: workflows/history/{dest.name}")
    body = {k: bk[k] for k in PUT_KEYS if k in bk}
    body["settings"] = {k: v for k, v in (bk.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{wid}", method="PUT", payload=body)
    post = api(f"/workflows/{wid}")
    ok = {n["name"]: n for n in post["nodes"]} == {n["name"]: n for n in bk["nodes"]} and post["connections"] == bk["connections"]
    print(f"  restaurado. nodos y conexiones identicos al backup: {ok} | activo: {post.get('active')}")
    if not ok:
        sys.exit("VERIFICACION FALLIDA: revisar a mano.")


if __name__ == "__main__":
    main()
