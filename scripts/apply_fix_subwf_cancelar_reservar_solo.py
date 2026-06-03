"""URGENTE - Sub-WF CancelarReprogramar Step 5: el path 'reservar_solo' creaba
ghost appointments. El Switch del Step 6 NO tiene case para 'reservar_solo' (solo
cancelar_turno / buscar_horarios / escalar / reservar_y_cancelar). Cuando el
paciente aceptaba un slot ofrecido SIN tener turno previo para cancelar, Step 5
seteaba action_to_execute='reservar_solo' + mensaje "Listo, reservando el X a
las Y" pero el Switch no enrutaba a ningun nodo HTTP -> Dentalink jamas creaba
la cita. Paciente cree que tiene turno, llega a la clinica y no esta.

Fix SAFE (no auto-reserva todavia, requiere agregar nodo HTTP nuevo): cambiar
el path a action_to_execute='escalar' con canned correcto, asi la secretaria
confirma manualmente y el paciente NO recibe confirmacion falsa.

Workflow: Sub-WF CancelarReprogramar (5cAWJxiWJ50hxEq3) / nodo Step 5: Decidir
Accion Ejecutable.

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
WF_ID = "5cAWJxiWJ50hxEq3"; H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
NODE = "Step 5: Decidir Accion Ejecutable"

OLD_LINE = "    return [{ json: { ...prev, action_to_execute: 'reservar_solo', slot_a_reservar: accept.slot_chosen, mensaje_final: 'Listo, reservando el ' + fechaNatural(accept.slot_chosen.fecha) + ' a las ' + horaNatural(accept.slot_chosen.hora_inicio) + '.' }}];"

NEW_LINE = "    // FIX 2026-06-02: el Switch no tenia case 'reservar_solo' -> ghost appointment. Hasta tener nodo HTTP de reserva, escalamos para confirmacion humana.\n    return [{ json: { ...prev, action_to_execute: 'escalar', mensaje_final: 'Para confirmar la reserva del ' + fechaNatural(accept.slot_chosen.fecha) + ' a las ' + horaNatural(accept.slot_chosen.hora_inicio) + ', le paso a la secretaria, que en su horario de atención (Lun y Mié 15 a 20 hs / Mar, Jue y Vie 8 a 13 hs) se lo confirma.' }}];"


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
    if not n: print(f"!! nodo '{NODE}' no encontrado"); sys.exit(2)
    js = n["parameters"].get("jsCode", "")
    if "FIX 2026-06-02" in js:
        print("!! ya aplicado"); sys.exit(3)
    cnt = js.count(OLD_LINE)
    if cnt != 1:
        print(f"!! anchor no match: count={cnt}. Abortando."); sys.exit(2)
    new_js = js.replace(OLD_LINE, NEW_LINE)
    print(f"{NODE}: {len(js)} -> {len(new_js)} chars (delta {len(new_js)-len(js):+d})")
    print("\n--- DIFF ---")
    print("- " + OLD_LINE[:200])
    print("+ " + NEW_LINE.replace("\n", "\\n")[:300])
    if args.dry or not args.apply: print("\n[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"subwf_cancelar_PRE_reservar_solo_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")
    n["parameters"]["jsCode"] = new_js
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(x for x in wf2["nodes"] if x["name"] == NODE)
    ok = "FIX 2026-06-02" in n2["parameters"].get("jsCode", "") and "'reservar_solo'" not in n2["parameters"].get("jsCode", "")
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
