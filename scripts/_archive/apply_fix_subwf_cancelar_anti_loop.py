"""
Fix Sub-WF Cancelar — anti-loop / anti-canned-repeat.

Bug visible 27/05 (caso Julieta Irene Rueda):
  - Paciente: "Ya cancele el turno ayer"
  - Bot:    "No te encuentro turnos activos en este momento. Si queres coordinar uno nuevo avisame y te lo paso a la secretaria Iri."
  - Paciente: "No entiendo. Ya cancele ese turno no asistiré"
  - Bot:    (MISMA canned)
  - Paciente: "Repito no asistiré al turno"
  - Bot:    (MISMA canned)

Causa: Step 4 decide siguiente_paso='responder_info' cuando turnos.length===0,
sin mirar si el bot YA dijo lo mismo antes. Step 0b ya construye conversation_history
pero no detecta repeticiones.

Fix (2 capas defensivas):
  Step 0b — agregar deteccion deterministica:
    - loop_no_turnos: el bot dijo "no encuentro turnos activos" 2+ veces seguidas
    - is_frustrated: paciente dijo "repito", "ya te dije", "no entiendo", etc.
  Step 4 — al inicio, si loop_no_turnos || is_frustrated -> forzar escalar.

Workflow: Sub-WF CancelarReprogramar (5cAWJxiWJ50hxEq3)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
WF_ID = "5cAWJxiWJ50hxEq3"  # Sub-WF CancelarReprogramar

HEADERS = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}


# --- Bloque a insertar en Step 0b (antes del return final) ---
STEP_0B_INSERT = r"""// === Deteccion anti-loop / anti-frustracion (27/05) ===
// Anti-pattern: caso Julieta - bot repitio "No te encuentro turnos activos" 3 veces.
// Detectar dos señales independientes y propagarlas a Step 4 que decide.
const fraseLoop = /no te encuentro turnos activos|no veo turno activo|no tenes turnos activos|por el momento no tenes turnos/i;
const botMsgsRecientes = historyPairs.filter(h => h.role === 'bot').slice(-3);
const repeticionesBot = botMsgsRecientes.filter(h => fraseLoop.test(h.content)).length;
const loop_no_turnos = repeticionesBot >= 2;

const fraseFrustracion = /(^|\s)(repito|ya te dije|ya dije|reitero|como te dije|otra vez te digo|no entiendo|no me entend[eé]s|insisto|cuantas veces)([\s,.!?]|$)/i;
const userText = String(trigger.text || '').toLowerCase();
const is_frustrated = fraseFrustracion.test(userText);

"""


# --- Bloque a insertar al INICIO de Step 4 ---
STEP_4_INSERT = r"""// === Anti-loop / anti-frustracion (27/05) ===
// Si el bot ya repitio la canned 2+ veces o el paciente esta frustrado,
// cortar el loop y escalar a humano directo. Step 0b setea los flags.
const loopNoTurnos = prev.trigger?.loop_no_turnos === true;
const isFrustrated = prev.trigger?.is_frustrated === true;
if (loopNoTurnos || isFrustrated) {
  return [{ json: {
    ...prev,
    decision: {
      siguiente_paso: 'escalar',
      razon: loopNoTurnos && isFrustrated ? 'loop_canned_y_frustracion'
           : loopNoTurnos ? 'loop_canned_repetida_2x'
           : 'paciente_pide_ayuda_explicita',
      canned: 'Le paso a la secretaria Iri para que pueda ayudarle con esto.'
    }
  }}];
}

"""


def get_workflow():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def backup(wf: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "workflows" / "history" / f"subwf_cancelar_PRE_ANTI_LOOP_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def find_node(wf: dict, name: str) -> dict:
    for n in wf["nodes"]:
        if n["name"] == name:
            return n
    raise SystemExit(f"Node {name!r} not found")


def patch_step_0b(wf: dict) -> tuple[str, str]:
    node = find_node(wf, "Step 0b: Detect Multi-Turn State")
    code = node["parameters"]["jsCode"]
    if "loop_no_turnos" in code:
        raise SystemExit("Step 0b already patched (found 'loop_no_turnos')")
    # Insert BEFORE the final `return [{ json: {`. Use the marker.
    marker = "return [{ json: {\n  ...trigger,"
    if marker not in code:
        raise SystemExit(f"Marker not found in Step 0b: {marker!r}")
    new_code = code.replace(marker, STEP_0B_INSERT + marker, 1)
    # Also add the flags to the returned object (top-level alongside multi_turn_state)
    flag_marker = "  conversation_history\n}}];"
    if flag_marker not in new_code:
        raise SystemExit(f"flag_marker not found in Step 0b: {flag_marker!r}")
    new_code = new_code.replace(
        flag_marker,
        "  conversation_history,\n  loop_no_turnos,\n  is_frustrated\n}}];",
        1,
    )
    node["parameters"]["jsCode"] = new_code
    return code, new_code


def patch_step_4(wf: dict) -> tuple[str, str]:
    node = find_node(wf, "Step 4: Identificar Turno + Decision")
    code = node["parameters"]["jsCode"]
    if "loop_canned_repetida" in code:
        raise SystemExit("Step 4 already patched (found 'loop_canned_repetida')")
    # Insert right after the initial 3 lines (const prev/intent/turnos)
    marker = "const turnos = prev.turnos_proximos || [];\n\n"
    if marker not in code:
        raise SystemExit(f"Marker not found in Step 4: {marker!r}")
    new_code = code.replace(marker, marker + STEP_4_INSERT, 1)
    node["parameters"]["jsCode"] = new_code
    return code, new_code


def put_workflow(wf: dict) -> dict:
    allowed_settings = {
        "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
        "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
        "executionOrder", "callerPolicy", "callerIds",
    }
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed_settings}
    body = {
        "name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
        "settings": settings, "staticData": wf.get("staticData"),
    }
    r = requests.put(
        f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, json=body, timeout=30,
    )
    if not r.ok:
        print("PUT failed:", r.status_code, r.text[:500], file=sys.stderr)
        r.raise_for_status()
    return r.json()


def main():
    dry = "--dry" in sys.argv

    print(f"[1/5] GET workflow {WF_ID}")
    wf = get_workflow()
    print(f"      name={wf['name']!r} active={wf.get('active')}")

    print("[2/5] Backup")
    out = backup(wf)
    print(f"      -> {out}")

    print("[3/5] Patch Step 0b")
    old0b, new0b = patch_step_0b(wf)
    print(f"      delta={len(new0b)-len(old0b):+d}ch")
    print(f"      contains 'loop_no_turnos' in new: {'loop_no_turnos' in new0b}")
    print(f"      contains 'is_frustrated' in new: {'is_frustrated' in new0b}")

    print("[4/5] Patch Step 4")
    old4, new4 = patch_step_4(wf)
    print(f"      delta={len(new4)-len(old4):+d}ch")
    print(f"      contains 'loop_canned_repetida' in new: {'loop_canned_repetida' in new4}")

    if dry:
        print("\n=== DRY RUN — not PUTting ===")
        return

    print("[5/5] PUT workflow")
    res = put_workflow(wf)
    print(f"      OK active={res.get('active')} updatedAt={res.get('updatedAt')}")

    wf2 = get_workflow()
    n0b = find_node(wf2, "Step 0b: Detect Multi-Turn State")
    n4 = find_node(wf2, "Step 4: Identificar Turno + Decision")
    ok = (
        "loop_no_turnos" in n0b["parameters"]["jsCode"]
        and "is_frustrated" in n0b["parameters"]["jsCode"]
        and "loop_canned_repetida" in n4["parameters"]["jsCode"]
    )
    if ok:
        print("[verify] OK — both patches present in live workflow")
    else:
        print("[verify] FAIL — patches missing in live workflow")
        sys.exit(2)


if __name__ == "__main__":
    main()
