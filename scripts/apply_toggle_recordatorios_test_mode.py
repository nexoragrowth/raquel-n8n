# -*- coding: utf-8 -*-
"""
apply_toggle_recordatorios_test_mode.py — prende/apaga el flag TEST_MODE dentro del
nodo "Preparar mensaje" del workflow "Recordatorio de Turno 48HS - Dra. Raquel"
(7RqTApkvVavRmq3R). Con TEST_MODE=true, TODOS los recordatorios de la corrida se
redirigen al TEST_PHONE (numero de Lucas) en vez de a los pacientes reales, con un
prefijo "[TEST 24h/72h] Para: <nombre> (<celular real>)" — permite disparar el
workflow completo (webhook manual `trigger-recordatorios-manual`) sin mandarle nada
a un paciente real.

USO (transitorio — SIEMPRE volver a --off después de probar):
    python scripts/apply_toggle_recordatorios_test_mode.py --on     # preview
    python scripts/apply_toggle_recordatorios_test_mode.py --on --apply
    python scripts/apply_toggle_recordatorios_test_mode.py --off --apply

Regla del proyecto: NUNCA --apply sin OK explicito de Lucas + backup previo.
"""
import argparse
import copy
import difflib
import json
import os
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""
WF = os.environ.get("N8N_WF_RECORDATORIOS", "7RqTApkvVavRmq3R")

PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}

NODE = "Preparar mensaje"
RE_FLAG = re.compile(r"const TEST_MODE = (true|false);")


def api(method, path, body=None):
    if not BASE or not KEY:
        sys.exit("!! Faltan N8N_API_BASE / N8N_API_KEY en el entorno.")
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "accept": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def clean_settings(wf):
    s = wf.get("settings") or {}
    return {k: v for k, v in s.items() if k in SETTINGS_OK}


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--on", action="store_true")
    g.add_argument("--off", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    target = "true" if args.on else "false"

    print(f"GET workflow {WF} …")
    wf = api("GET", f"/workflows/{WF}")
    print(f"  {wf['name']} — {len(wf['nodes'])} nodos, activo={wf['active']}")
    wf_orig = copy.deepcopy(wf)

    n = next((x for x in wf["nodes"] if x["name"] == NODE), None)
    if not n:
        sys.exit(f"!! No encontré el nodo '{NODE}'.")
    code = n["parameters"].get("jsCode", "")
    m = RE_FLAG.search(code)
    if not m:
        sys.exit("!! No encontré 'const TEST_MODE = true/false;' en el código.")
    actual = m.group(1)
    if actual == target:
        print(f"\nTEST_MODE ya está en {target}, no hay nada que hacer.")
        return

    nuevo_code = RE_FLAG.sub(f"const TEST_MODE = {target};", code, count=1)
    print(f"\n=== DIFF: {NODE} ===")
    for line in difflib.unified_diff(
        code.splitlines(), nuevo_code.splitlines(), fromfile="ANTES", tofile="DESPUES", lineterm=""
    ):
        if line.startswith(("+", "-")) and "TEST_MODE" in line:
            print(line)
    n["parameters"]["jsCode"] = nuevo_code

    print("Sin cambios de conexiones, credenciales, ni ningún otro nodo.")

    if not args.apply:
        print("\n(preview — no se tocó n8n). Para aplicar: --apply")
        return

    os.makedirs("workflows/history", exist_ok=True)
    tag = "on" if args.on else "off"
    pre = f"workflows/history/recordatorios_PRE_test_mode_{tag}.json"
    json.dump(wf_orig, open(pre, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nbackup PRE -> {pre}")

    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = clean_settings(wf)
    print("PUT …")
    api("PUT", f"/workflows/{WF}", body)

    vivo = api("GET", f"/workflows/{WF}")
    post = f"workflows/history/recordatorios_POST_test_mode_{tag}.json"
    json.dump(vivo, open(post, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"backup POST -> {post}")

    n2 = next((x for x in vivo["nodes"] if x["name"] == NODE), None)
    real_code = n2["parameters"].get("jsCode", "") if n2 else ""
    m2 = RE_FLAG.search(real_code)
    ok = bool(m2) and m2.group(1) == target
    print(f"\nTEST_MODE={target}  {'OK ✅' if ok else '!! NO COINCIDE'}")


if __name__ == "__main__":
    main()
