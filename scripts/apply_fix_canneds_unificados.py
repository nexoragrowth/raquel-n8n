"""Unifica los canned de fallback "no se que responder" en el v6 main:
- Gate Error Tecnico: const CANNED = 'Recibimos tu mensaje. Le paso a la secretaria...'
- Format Sub-WF Output: output: 'Le paso a la secretaria para que le ayude lo antes posible.'

Wording nuevo (pedido por la Dra el 2026-06-02):
"Hola! Soy Asiri🤗, la secretaria virtual de la Dra. Raquel Rodríguez. Le envío la
información a la secretaria, ella le responderá en su horario de atención. Gracias!"

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

NEW_CANNED = "Hola! Soy Asiri\U0001f917, la secretaria virtual de la Dra. Raquel Rodríguez. Le envío la información a la secretaria, ella le responderá en su horario de atención. Gracias!"

REPLACEMENTS = {
    "Gate Error Tecnico": [
        ("'Recibimos tu mensaje. Le paso a la secretaria para que coordine cuanto antes.'", f"'{NEW_CANNED}'"),
    ],
    "Format Sub-WF Output": [
        ("'Le paso a la secretaria para que le ayude lo antes posible.'", f"'{NEW_CANNED}'"),
    ],
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
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:300], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()
    changes = []
    for node_name, patterns in REPLACEMENTS.items():
        n = next((x for x in wf["nodes"] if x["name"] == node_name), None)
        if not n: print(f"!! {node_name} no encontrado"); continue
        js = n["parameters"].get("jsCode", "")
        new_js = js
        for old, new in patterns:
            cnt = new_js.count(old)
            if cnt == 0:
                print(f"[{node_name}] anchor no encontrado: {old[:80]}")
                continue
            new_js = new_js.replace(old, new)
            changes.append((node_name, cnt))
            print(f"[{node_name}] reemplazo OK x{cnt}: {old[:80]} -> {new[:80]}")
        if new_js != js:
            n["parameters"]["jsCode"] = new_js

    if not changes:
        print("\n!! nada que cambiar"); return
    if args.dry or not args.apply:
        print(f"\n[dry] {len(changes)} cambios listos. No aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_canneds_unificados_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_wf()
    all_ok = True
    for node_name, patterns in REPLACEMENTS.items():
        n2 = next(x for x in wf2["nodes"] if x["name"] == node_name)
        js2 = n2["parameters"].get("jsCode", "")
        for old, new in patterns:
            if old in js2 or new not in js2:
                print(f"[verify] FAIL {node_name}"); all_ok = False; break
        else:
            print(f"[verify] OK   {node_name}")
    sys.exit(0 if all_ok else 3)


if __name__ == "__main__":
    main()
