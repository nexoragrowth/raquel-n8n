"""Fix Router: extender EXCEPCION SECUNDARIA para cubrir 'pregunta clarificatoria sobre lo que el bot acaba de pedir'.
Caso real: 1/6 Lucas - bot (Agendar) pregunta 'para quien es el turno?', paciente responde 'A que personas?',
Router lo clasifica como consulta_general -> General -> escala (en vez de mantener Agendar que tiene las fichas en memoria).

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

ANCHOR = "- **Flow CONFIRMAR activo** + paciente pregunta sobre el turno (\"a que hora era?\", \"que dia es?\") -> intent = `confirmar_post_recordatorio` (CONTINUACION)."

INSERT_AFTER = """

- **CLARIFICACION SOBRE LO QUE EL BOT ACABA DE PEDIR (caso comun, NO mandar a consulta_general)**: si el ultimo AI fue un sub-agent operativo (Agendar/Cancelar/Confirmar) PIDIENDOLE INFO al paciente (ej "para quien es el turno?", "DNI?", "que dia preferis?", "a nombre de quien?", "que turno cancela?") y el paciente devuelve una PREGUNTA CLARIFICATORIA en vez de la info pedida (ej "a que personas?", "que opciones?", "que dias hay?", "como?", "cuales son?", "no entiendo"), MANTENE el mismo intent del flow activo. El sub-agent operativo es quien tiene las tools + el contexto en memoria (las fichas devueltas, los slots ofrecidos, etc.) para responder esa clarificacion. Si lo mandas a consulta_general no tiene como responder y termina escalando.

Ejemplo real (1/6): bot (Agendar) "Con este numero tengo registrada a mas de una persona. Para quien es el turno? Paseme nombre y apellido del paciente." + paciente "A que personas?" -> intent = `agendar_nuevo` (CONTINUACION clarificatoria). El Sub-Agent Agendar lista las fichas devueltas por buscar_paciente_dentalink."""


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
    if not node: print("!! no encontre Router"); sys.exit(2)
    msg = node["parameters"]["options"]["systemMessage"]
    if ANCHOR not in msg: print("!! anchor no encontrado"); sys.exit(3)
    if "CLARIFICACION SOBRE LO QUE EL BOT" in msg: print("!! ya aplicado"); sys.exit(4)
    new_msg = msg.replace(ANCHOR, ANCHOR + INSERT_AFTER, 1)
    print(f"Router: {len(msg)} -> {len(new_msg)} chars (delta {len(new_msg)-len(msg):+d})")
    if args.dry or not args.apply:
        print("\n--- INSERCION ---\n" + INSERT_AFTER); print("\n[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_fix_router_clarificacion_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")
    node["parameters"]["options"]["systemMessage"] = new_msg
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(n for n in wf2["nodes"] if n["name"] == NODE)
    ok = "CLARIFICACION SOBRE LO QUE EL BOT" in n2["parameters"]["options"]["systemMessage"]
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
