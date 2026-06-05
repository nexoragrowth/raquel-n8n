"""URGENTE - Banlist Validator bloqueaba "Balcarce 37" SIEMPRE, incluso cuando
el paciente preguntaba EXPLICITAMENTE por la direccion.

Caso real 03/06 22:00 PM ARG: Pichón llegó de pauta paga preguntando
"Si dónde queda y precio está la consulta". El bot respondió bien con precio +
Balcarce 37. El Banlist lo reemplazó por canned escalación → LEAD PAGADO PERDIDO.

Fix: agregar excepción al match de Balcarce 37 — si el mensaje del paciente
incluye palabras de pregunta de dirección (donde, queda, ubicación, dirección,
dónde están, ubicados), el match Balcarce 37 NO triggea.

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
NODE = "Banlist Validator"

OLD_CODE_START = "const item = $input.first().json;\nconst output = (item.output || '').toString();"

NEW_CODE_START = """const item = $input.first().json;
const output = (item.output || '').toString();

// FIX 2026-06-04: detectar si el paciente pregunto direccion explicitamente -> NO banear Balcarce 37
let pacienteMsg = '';
try {
  pacienteMsg = ($('Preparar Mensaje Final').first().json.text || '').toString().toLowerCase();
} catch(e) { pacienteMsg = ''; }
const pacientePidioDireccion = /\\b(d[oó]nde\\s*(queda|est[aá]n?|ubicad|esta\\s*ubicad)|direcci[oó]n|ubicaci[oó]n|c[oó]mo\\s*llegar|en\\s*qu[eé]\\s*(direcci[oó]n|calle)|qu[eé]\\s*direcci[oó]n)\\b/i.test(pacienteMsg);"""

# Cambiar el comentario que decía "BAN absoluto" + actualizar el regex match
OLD_BALCARCE = """  // Direccion fisica como confirmacion de cita
  { rx: /\\bbalcarce\\s*(n[º°]?\\s*)?37\\b/i,               why: 'direccion Balcarce 37 (NO debe darse desde el bot fuera de info-direccion explicita)' },"""

NEW_BALCARCE = """  // Direccion fisica como confirmacion de cita.
  // FIX 2026-06-04: si paciente preguntó explícitamente la dirección, NO banear.
  { rx: /\\bbalcarce\\s*(n[º°]?\\s*)?37\\b/i, skip_if_paciente_pidio_direccion: true, why: 'direccion Balcarce 37 (NO debe darse desde el bot fuera de info-direccion explicita)' },"""

# El loop de checking del banlist necesita respetar skip_if_paciente_pidio_direccion
# Buscar el loop existente
OLD_LOOP = """let triggered = null;
for (const entry of BANLIST) {
  if (entry.rx.test(output)) {
    triggered = entry.why;
    break;
  }
}"""

NEW_LOOP = """let triggered = null;
for (const entry of BANLIST) {
  if (entry.skip_if_paciente_pidio_direccion && pacientePidioDireccion) continue;
  if (entry.rx.test(output)) {
    triggered = entry.why;
    break;
  }
}"""


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
    n = next((x for x in wf["nodes"] if x["name"] == NODE), None)
    if not n: print("!! Banlist Validator no encontrado"); sys.exit(2)
    js = n["parameters"]["jsCode"]
    if "FIX 2026-06-04" in js:
        print("!! ya aplicado"); sys.exit(3)
    if OLD_CODE_START not in js:
        print("!! anchor inicial no match"); sys.exit(2)
    if OLD_BALCARCE not in js:
        print("!! anchor balcarce no match"); sys.exit(2)
    if OLD_LOOP not in js:
        print("!! anchor loop no match"); sys.exit(2)
    new_js = js.replace(OLD_CODE_START, NEW_CODE_START)
    new_js = new_js.replace(OLD_BALCARCE, NEW_BALCARCE)
    new_js = new_js.replace(OLD_LOOP, NEW_LOOP)
    print(f"Banlist Validator: {len(js)} -> {len(new_js)} chars (+{len(new_js)-len(js)})")
    if args.dry or not args.apply: print("[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_banlist_direccion_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")
    n["parameters"]["jsCode"] = new_js
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(x for x in wf2["nodes"] if x["name"] == NODE)
    ok = "FIX 2026-06-04" in n2["parameters"]["jsCode"]
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
