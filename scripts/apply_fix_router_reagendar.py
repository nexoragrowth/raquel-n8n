"""Fix Router: capturar 'volveria en X meses' (reagendar post-control) como agendar_nuevo.
Bajo riesgo: agrega senales adicionales a la regla #4, no cambia ninguna existente.

Modos: --dry / --apply (backup + PUT + verify)."""
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
NODE = "Router - Clasificar Intent"

OLD = """**4. agendar_nuevo**
"queria sacar un turno", "primera vez", "necesito una consulta", "se puede agendar".
**CONTINUACION**: solo si el flujo en curso ES agendar (ultimo AI en flujo agendar)."""

NEW = """**4. agendar_nuevo**
"queria sacar un turno", "primera vez", "necesito una consulta", "se puede agendar".
**REAGENDAR POST-CONTROL**: el paciente avisa que va a volver tras un control y/o quiere reservar el siguiente. Senales: "volveria en [X meses/semanas]", "vuelvo en [X]", "para el control de [X]", "el proximo control en [X]", "me dijo la doctora que vuelva en [X]", "para X meses", "agendame el control de X". Aunque no diga literal "quiero turno", el pedido implicito es reservar -> `agendar_nuevo` (el Sub-Agent Agendar le confirmara la intencion y le ofrecera slots).
**CONTINUACION**: solo si el flujo en curso ES agendar (ultimo AI en flujo agendar)."""


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
    node = next((n for n in wf["nodes"] if n["name"] == NODE), None)
    if not node: print("!! no encontre el Router"); sys.exit(2)
    msg = node["parameters"]["options"]["systemMessage"]
    if OLD not in msg:
        print("!! la regla #4 actual no coincide exacto con el OLD esperado. Abortando."); sys.exit(3)
    if "REAGENDAR POST-CONTROL" in msg:
        print("!! ya parece aplicado. Abortando para no duplicar."); sys.exit(4)
    new_msg = msg.replace(OLD, NEW, 1)
    print(f"Router systemMessage: {len(msg)} -> {len(new_msg)} chars (delta {len(new_msg)-len(msg):+d})")
    print("\n--- ANTES (regla #4) ---")
    print(OLD)
    print("\n--- DESPUES (regla #4) ---")
    print(NEW)

    if args.dry or not args.apply:
        print("\n[dry] no aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_fix_router_reagendar_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")
    node["parameters"]["options"]["systemMessage"] = new_msg
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(n for n in wf2["nodes"] if n["name"] == NODE)
    ok = "REAGENDAR POST-CONTROL" in n2["parameters"]["options"]["systemMessage"]
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
