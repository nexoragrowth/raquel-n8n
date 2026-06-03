"""Sub-tool obtener_historial_paciente: toolDescription dice "VOS sos siempre la
asistente virtual" — contradice la nueva identidad "secretaria virtual" que el
resto del bot usa desde 2026-06-02. El LLM lo lee en cada evaluacion de uso del
tool. Cambio aislado de la toolDescription.

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
NODE = "obtener_historial_paciente"


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
    n = next((x for x in wf["nodes"] if x["name"] == NODE), None)
    if not n: print(f"!! '{NODE}' no encontrado"); sys.exit(2)
    td = n["parameters"].get("toolDescription", "")
    cnt = td.count("asistente virtual")
    if cnt == 0: print("!! 'asistente virtual' no aparece, no hay nada que cambiar"); sys.exit(3)
    new_td = td.replace("asistente virtual", "secretaria virtual")
    print(f"{NODE}.toolDescription: {len(td)} -> {len(new_td)} chars, replacements: {cnt}")
    # Mostrar contexto
    idx = td.find("asistente virtual")
    print(f"  Contexto: ...{td[max(0,idx-40):idx+50]!r}...")
    if args.dry or not args.apply: print("\n[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_obtener_historial_toolDesc_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")
    n["parameters"]["toolDescription"] = new_td
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(x for x in wf2["nodes"] if x["name"] == NODE)
    ok = "asistente virtual" not in n2["parameters"].get("toolDescription", "")
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
