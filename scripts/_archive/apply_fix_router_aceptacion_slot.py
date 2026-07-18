"""URGENTE - Router: agregar senales explicitas de ACEPTACION DE SLOT en contexto
post-oferta de Sub-Agent Agendar. Caso real Valentino 03/06: bot ofrecio
"Martes 23 9:20 hs" -> paciente "dale, vamos con ese" -> Router clasifico como
consulta_general -> Sub-Agent General respondio "le paso con la agenda" sin
reservar. BUG.

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

OLD = """**4. agendar_nuevo**
"queria sacar un turno", "primera vez", "necesito una consulta", "se puede agendar".
**CONTINUACION**: solo si el flujo en curso ES agendar (ultimo AI en flujo agendar)."""

NEW = """**4. agendar_nuevo**
"queria sacar un turno", "primera vez", "necesito una consulta", "se puede agendar".
**CONTINUACION** (REGLA CRITICA, NUEVO 2026-06-03): si el flujo en curso ES agendar (ultimo AI fue Sub-Agent Agendar ofreciendo slot o haciendo read-back), TODO mensaje del paciente que sea aceptacion del slot, eleccion, confirmacion o info para registrar sigue siendo `agendar_nuevo`. Senales de ACEPTACION DE SLOT post-oferta (NO `consulta_general`):
- "dale", "dale vamos con ese", "dale ese", "vamos con ese", "ese", "ese mismo", "ese me sirve", "ese de las X", "el primero", "el de las X hs".
- "buenisimo", "buenisimo para ese dia", "perfecto", "perfecto ese", "joya", "listo".
- "si", "si por favor", "si dale", "ok", "okey", "claro", "ese si", "obvio".
- "confirmo", "confirmado", emoji solo 👍/✅/🙏 cuando hay slot ofrecido en memoria.
- "X a las HH" / "para ese dia entonces" / "queria ese de las X" / "el de manana" / "el de la tarde" (filtrando dentro de la oferta).
REGLA DE ORO: si el ultimo AI fue Sub-Agent Agendar y el paciente da CUALQUIER respuesta no-interrogativa, intent = `agendar_nuevo`. NO `consulta_general` salvo que el paciente cambie de tema explicito (precio, direccion, otra cosa no-turno)."""


def get_wf():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60); r.raise_for_status(); return r.json()


def put_wf(wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:500], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()
    n = next((x for x in wf["nodes"] if x["name"] == "Router - Clasificar Intent"), None)
    if not n: print("!! Router no encontrado"); sys.exit(2)
    sm = n["parameters"]["options"]["systemMessage"]
    if "ACEPTACION DE SLOT post-oferta" in sm:
        print("!! ya aplicado"); sys.exit(3)
    cnt = sm.count(OLD)
    if cnt != 1:
        print(f"!! anchor no match: count={cnt}. Abortando."); sys.exit(2)
    new_sm = sm.replace(OLD, NEW)
    print(f"Router systemMessage: {len(sm)} -> {len(new_sm)} chars (delta {len(new_sm)-len(sm):+d})")
    if args.dry or not args.apply: print("[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_router_aceptacion_slot_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")
    n["parameters"]["options"]["systemMessage"] = new_sm
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(x for x in wf2["nodes"] if x["name"] == "Router - Clasificar Intent")
    ok = "ACEPTACION DE SLOT post-oferta" in n2["parameters"]["options"]["systemMessage"]
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
