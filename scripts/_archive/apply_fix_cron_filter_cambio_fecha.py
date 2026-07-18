"""URGENTE - Cron recordatorios: el IF 'Solo citas activas' (en ambas ramas
24h y 72h) NO excluye id_estado=14 (Cambio de fecha). Resultado: pacientes con
turnos fantasma (que tienen un turno NUEVO + uno viejo en estado 14) reciben
recordatorios DOBLE — uno legitimo y uno del fantasma.

Caso real Pilar Latronico (03/06): tenia 16:10 hs (id_estado=7, real) y
16:20 hs (id_estado=14, fantasma). El bot le ofrecio confirmar/cancelar
LOS DOS.

Fix: agregar una condicion mas al combinator 'and' de cada IF 'Solo citas
activas': id_estado != 14.

NO se toca la query Dentalink (sigue trayendo TODOS los estados != 1) por
si la API no soporta 'nin'. El filtro queda en el IF en n8n.

Workflow: cron recordatorios (7RqTApkvVavRmq3R).

Modo: --dry / --apply
"""
from __future__ import annotations
import argparse, json, os, sys, io, copy
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
WF_ID = "7RqTApkvVavRmq3R"; H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}


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

    NEW_COND = {
        "id": "condition-3-skip-cambio-fecha",
        "leftValue": "={{ $json.id_estado }}",
        "rightValue": 14,
        "operator": {"type": "number", "operation": "notEquals"},
    }

    targets = [n for n in wf["nodes"] if n["name"] == "Solo citas activas" and n["type"] == "n8n-nodes-base.if"]
    print(f"IFs 'Solo citas activas' encontrados: {len(targets)}")
    changes = 0
    for n in targets:
        conds = n["parameters"]["conditions"]["conditions"]
        # idempotency: ya tiene id_estado != 14?
        already = any(
            "id_estado" in (c.get("leftValue", "") or "") and c.get("rightValue") == 14 and c.get("operator", {}).get("operation") == "notEquals"
            for c in conds
        )
        if already:
            print(f"  [{n.get('id', '?')}] ya tiene id_estado != 14, skip")
            continue
        print(f"  [{n.get('id', '?')}] agregando id_estado != 14 (de {len(conds)} a {len(conds)+1} conds)")
        conds.append(copy.deepcopy(NEW_COND))
        changes += 1

    if changes == 0:
        print("\n!! nada que cambiar (probable ya aplicado)"); return
    if args.dry or not args.apply:
        print(f"\n[dry] {changes} cambios listos. No aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"cron_recordatorios_PRE_filter_id14_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_wf()
    all_ok = True
    for n in [x for x in wf2["nodes"] if x["name"] == "Solo citas activas"]:
        conds = n["parameters"]["conditions"]["conditions"]
        ok = any(
            "id_estado" in (c.get("leftValue", "") or "") and c.get("rightValue") == 14 and c.get("operator", {}).get("operation") == "notEquals"
            for c in conds
        )
        if not ok: all_ok = False
        print(f"  [verify] {n.get('id','?')}: id_estado != 14 = {ok}")
    print(f"[verify] {'OK' if all_ok else 'FAIL'}")


if __name__ == "__main__":
    main()
