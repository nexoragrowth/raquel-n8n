# -*- coding: utf-8 -*-
"""
apply_fix_helper_label_diferido.py — arregla el auto-silencio post-escalación (bug preexistente,
6/6 casos desde el 30/8, encontrado en el mapeo del 4/9).

CAUSA: `Helper - Notify Grupo` (S5U6tSipzlgFHCkf) aplica el label `humano` en Chatwoot en forma
SINCRÓNICA (webhook responseMode=lastNode → la tool `escalar_a_secretaria` bloquea hasta que el
label está puesto). 1.4 s después, `Re-check Humano` del v6 ve el label y suprime la respuesta del
sub-agent: el paciente escalado nunca recibe "Recibimos tu mensaje…".

FIX (solo en el Helper, 0 cambios en el v6):
  1. Webhook responseMode: lastNode → onReceived (responde al instante; los callers ignoran el body).
  2. Nodo nuevo `Esperar respuesta del bot (20s)` (Wait) antes de `Chatwoot Apply`, en ambas ramas
     (silenciosa y no silenciosa). El aviso al grupo sigue siendo inmediato; el label llega 20 s
     después, cuando la respuesta del bot ya salió. Después el bot queda en silencio como siempre.

Uso: python scripts/apply_fix_helper_label_diferido.py [--apply] [--segundos 20] [--rollback <PRE.json>]
"""
import argparse, copy, json, os, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HELPER_ID = "S5U6tSipzlgFHCkf"
WAIT_NAME = "Esperar respuesta del bot (20s)"
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", data=json.dumps(payload).encode() if payload is not None else None,
                                 method=method, headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())

def put(wf, label):
    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{HELPER_ID}", "PUT", body)
    after = api(f"/workflows/{HELPER_ID}")
    p = ROOT / "workflows" / "history" / f"helper_notify_grupo_POST_{label}_{time.strftime('%Y%m%d_%H%M%S')}.json"
    p.write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    print("POST backup ->", p)
    return after

def build(wf, segundos):
    new = copy.deepcopy(wf); nodes = new["nodes"]; conns = new["connections"]; names = {n["name"]: n for n in nodes}
    cambios = []
    for req in ("Webhook", "Notify Grupo Send", "Chatwoot Apply", "Silencioso?"):
        if req not in names: sys.exit(f"ERROR: falta {req!r} en el Helper")
    wh = names["Webhook"]
    if wh["parameters"].get("responseMode") != "onReceived":
        wh["parameters"]["responseMode"] = "onReceived"; cambios.append("Webhook.responseMode: lastNode -> onReceived")
    else:
        cambios.append("Webhook.responseMode ya es onReceived (idempotente)")
    ca = names["Chatwoot Apply"]
    if WAIT_NAME not in names:
        nodes.append({"id": "helper-wait-label", "name": WAIT_NAME, "type": "n8n-nodes-base.wait", "typeVersion": 1.1,
                      "position": [ca["position"][0] - 260, ca["position"][1] + 200], "webhookId": "helper-wait-label",
                      "parameters": {"amount": segundos, "unit": "seconds"}})
        cambios.append(f"AGREGA Wait {segundos}s antes de Chatwoot Apply")
    else:
        names[WAIT_NAME]["parameters"]["amount"] = segundos; cambios.append("Wait ya existe (actualiza segundos)")
    # rewire: Notify Grupo Send -> Wait ; Silencioso?[1] -> Wait ; Wait -> Chatwoot Apply
    def targets(name, idx):
        try: return [c["node"] for c in conns[name]["main"][idx]]
        except (KeyError, IndexError): return None
    if targets("Notify Grupo Send", 0) == ["Chatwoot Apply"]:
        conns["Notify Grupo Send"]["main"][0] = [{"node": WAIT_NAME, "type": "main", "index": 0}]; cambios.append("REWIRE Notify Grupo Send -> Wait")
    elif targets("Notify Grupo Send", 0) != [WAIT_NAME]:
        sys.exit(f"ERROR: Notify Grupo Send apunta a {targets('Notify Grupo Send', 0)!r}")
    if targets("Silencioso?", 1) == ["Chatwoot Apply"]:
        conns["Silencioso?"]["main"][1] = [{"node": WAIT_NAME, "type": "main", "index": 0}]; cambios.append("REWIRE Silencioso?[1] -> Wait")
    elif targets("Silencioso?", 1) != [WAIT_NAME]:
        sys.exit(f"ERROR: Silencioso?[1] apunta a {targets('Silencioso?', 1)!r}")
    conns[WAIT_NAME] = {"main": [[{"node": "Chatwoot Apply", "type": "main", "index": 0}]]}
    return new, cambios

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--segundos", type=int, default=20); ap.add_argument("--rollback")
    args = ap.parse_args()
    wf = api(f"/workflows/{HELPER_ID}")
    print(f"{wf['name']} | {len(wf['nodes'])} nodos | active={wf['active']} | updatedAt={wf.get('updatedAt')}")
    (ROOT / "workflows" / "history").mkdir(parents=True, exist_ok=True)
    if args.rollback:
        bk = json.loads(Path(args.rollback).read_text(encoding="utf-8"))
        pre = ROOT / "workflows" / "history" / f"helper_notify_grupo_PRE_rollback_{time.strftime('%Y%m%d_%H%M%S')}.json"
        pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        after = put(bk, "rollback"); print("rollback OK:", len(after["nodes"]), "nodos"); return
    new, cambios = build(wf, args.segundos)
    print("CAMBIOS:"); [print("  -", c) for c in cambios]
    if not args.apply:
        print("[DRY-RUN] no se tocó n8n. Para aplicar: --apply"); return
    pre = ROOT / "workflows" / "history" / f"helper_notify_grupo_PRE_label_diferido_{time.strftime('%Y%m%d_%H%M%S')}.json"
    pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"); print("PRE backup ->", pre)
    after = put(new, "label_diferido")
    names = {n["name"]: n for n in after["nodes"]}
    ok = (names["Webhook"]["parameters"].get("responseMode") == "onReceived" and WAIT_NAME in names
          and [c["node"] for c in after["connections"][WAIT_NAME]["main"][0]] == ["Chatwoot Apply"]
          and [c["node"] for c in after["connections"]["Notify Grupo Send"]["main"][0]] == [WAIT_NAME])
    print("verificación:", "OK" if ok else "FALLÓ (rollback: --rollback " + str(pre) + ")")
    if not ok: sys.exit(1)
    print(f"✅ Helper actualizado: el label humano se aplica {args.segundos}s después del aviso; el aviso al grupo sigue inmediato.")

if __name__ == "__main__":
    main()
