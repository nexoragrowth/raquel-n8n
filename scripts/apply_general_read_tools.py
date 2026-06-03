"""Fix #2: agregar Sub-Agent General como destino ai_tool a 3 tools de LECTURA:
- ver_turnos_paciente
- buscar_horarios
- buscar_paciente_dentalink

Asi el Sub-Agent General puede consultar turnos del paciente, disponibilidad de slots
e identificar al paciente, sin escalar para casos de consulta personal.

Las tools de ESCRITURA (reservar_turno, cancelar_turno, confirmar_turno, crear_paciente)
quedan exclusivas de los sub-agents de accion. Read si, write no.

Modos: --dry / --apply"""
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

TOOLS_TO_ADD = ["ver_turnos_paciente", "buscar_horarios", "buscar_paciente_dentalink"]
TARGET_AGENT = "Sub-Agent General"


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
    conns = wf["connections"]
    changes = []
    for tool in TOOLS_TO_ADD:
        if tool not in conns:
            print(f"  !! {tool}: nodo sin connections salientes"); continue
        ai = conns[tool].get("ai_tool", [])
        if not ai or not ai[0]:
            print(f"  !! {tool}: sin ai_tool conexiones"); continue
        existing = [c["node"] for c in ai[0]]
        if TARGET_AGENT in existing:
            print(f"  ya conectado: {tool} -> {existing}"); continue
        print(f"  agregar: {tool} -> {existing + [TARGET_AGENT]}")
        ai[0].append({"node": TARGET_AGENT, "type": "ai_tool", "index": 0})
        changes.append(tool)

    if not changes:
        print("\n[nada que cambiar]"); return

    if args.dry or not args.apply:
        print(f"\n[dry] {len(changes)} cambios pendientes. Con --apply se aplican."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_general_read_tools_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_wf()
    print("\n[verify]")
    for tool in changes:
        ai = wf2["connections"].get(tool, {}).get("ai_tool", [])
        dests = [c["node"] for c in (ai[0] or [])]
        ok = TARGET_AGENT in dests
        print(f"  {tool} -> {dests} {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
