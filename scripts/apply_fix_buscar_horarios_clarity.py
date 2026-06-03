"""
Fix buscar_horarios — clarificar toolDescription + reforzar PASO 5 del Agendar.

Bug 27/05 18:26 (paciente Andres Quispe):
  Bot dijo "Para el martes 30 de junio no tengo turnos disponibles."
  PERO en realidad llamo `buscar_horarios` con query VACIO ({}).
  Dentalink devolvio los 8 proximos slots cronologicos (todos hasta 18/06).
  El 30/06 nunca se consulto. Alucinacion confirmada.

Causa:
  1. toolDescription decia "q es JSON con id_sucursal, fecha, duracion, id_dentista..."
     Pero la URL del nodo solo admite `fecha` via $fromAI. Resto hardcoded.
     El LLM se confundio y paso q={}.
  2. PASO 5 del prompt Agendar dice "NUNCA con query vacio" pero el LLM lo ignoro
     porque el toolDescription no enfatiza que `fecha` es OBLIGATORIA.

Fix:
  A) Reescribir toolDescription: dejar claro que el unico arg es `fecha` YYYY-MM-DD.
     id_sucursal, duracion, id_dentista estan hardcoded — no los pase el LLM.
     Si paciente quiere franja, el LLM filtra los slots devueltos.
  B) Reforzar PASO 5 del Sub-Agent Agendar con regla explicita:
     - Si paciente menciono fecha -> pasarla
     - Si no hay fecha -> preguntar antes de llamar
     - Si Dentalink devuelve vacio para esa fecha -> recien ahi decir "no hay para [fecha]"
     - PROHIBIDO afirmar "no hay para X" sin haber buscado X especificamente

Workflow: v6 main (O155MqHgOSaNZ9ye)
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
WF_ID = "O155MqHgOSaNZ9ye"

HEADERS = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}


NEW_TOOL_DESCRIPTION = (
    "Busca slots disponibles de la Dra. Raquel para UNA fecha especifica.\n\n"
    "UNICO PARAMETRO: `fecha` en formato YYYY-MM-DD.\n"
    "Los demas (id_sucursal=1, duracion=40, id_dentista=1) estan HARDCODED en el tool, NO los pases.\n\n"
    "USO CORRECTO:\n"
    "  - El paciente menciono el martes 30 de junio -> pasa fecha=\"2026-06-30\"\n"
    "  - El paciente quiere \"este viernes\" -> calcula la fecha YYYY-MM-DD desde FECHA Y HORA ACTUAL\n\n"
    "REGLA CRITICA: el campo `fecha` es OBLIGATORIO. NUNCA llames esta tool sin una fecha concreta.\n"
    "Si no tenes una fecha clara, primero PEDISELA al paciente. No llames la tool a ciegas.\n\n"
    "FRANJA HORARIA: si el paciente pide \"tarde\" o \"mañana\", llamas la tool con la fecha y DESPUES filtras los slots devueltos por hora (mañana: hora_inicio < 12:00 / tarde: hora_inicio >= 14:00).\n"
    "NO afirmar \"no hay turnos para [fecha]\" sin haber llamado la tool con ESA fecha y recibido array vacio.\n\n"
    "RESPUESTA DE LA TOOL: array JSON con objetos {fecha, hora_inicio, hora_fin, duracion, id_dentista, id_recurso}.\n"
    "Si el array esta vacio para la fecha pedida -> recien entonces podes ofrecer alternativas (buscando otra fecha proxima)."
)


PASO_5_NEW = """PASO 5 — BUSCAR HORARIOS:
- `buscar_horarios(fecha)`. El argumento `fecha` (YYYY-MM-DD) es OBLIGATORIO.
- NUNCA llamar con `fecha` vacia o sin pasarla. Si no tenes una fecha del paciente, PIDESELA antes (PASO 4).
- Si paciente menciono fecha explicita ("el 30 de junio", "este viernes", "el martes que viene") -> calcular YYYY-MM-DD y pasarla.
- Si paciente menciono franja ("tarde", "mañana", "despues de las 17") -> pasar la fecha y DESPUES filtrar los slots devueltos por hora (mañana < 12:00 / tarde >= 14:00).
- Si paciente menciono varias fechas a probar ("el 29 o el 30") -> llamar la tool UNA VEZ POR CADA fecha. Acumular resultados.
- NO ofrecer horarios pasados (compara con FECHA Y HORA ACTUAL del header).
- Si la fecha pedida devuelve array vacio -> recien ahi decir "Para el [fecha natural] no tengo turnos" + ofrecer 2-3 alternativas cercanas (llamando la tool con esas fechas).

**REGLA ANTI-ALUCINACION**: PROHIBIDO afirmar "no tengo turnos para [fecha X]" si no llamaste `buscar_horarios(fecha=X)` y recibiste array vacio. Una llamada con query generico/vacio NO te dice nada sobre [fecha X] especificamente. Caso real 27/05: bot dijo "para el 30/06 no tengo" sin haberlo consultado -> alucinacion. NO repetirlo.

"""


def get_workflow():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def backup(wf: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "workflows" / "history" / f"v6_PRE_BUSCAR_HORARIOS_CLARITY_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def find_node(wf: dict, name: str) -> dict:
    for n in wf["nodes"]:
        if n["name"] == name:
            return n
    raise SystemExit(f"Node {name!r} not found")


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

    wf = get_workflow()
    print(f"GET workflow | active={wf.get('active')}")

    out = backup(wf)
    print(f"backup -> {out}")

    # === A) toolDescription de buscar_horarios ===
    bh = find_node(wf, "buscar_horarios")
    old_td = bh["parameters"].get("toolDescription", "")
    new_td = NEW_TOOL_DESCRIPTION
    print(f"[buscar_horarios.toolDescription] {len(old_td)}ch -> {len(new_td)}ch ({len(new_td)-len(old_td):+d})")

    # === B) PASO 5 del Sub-Agent Agendar ===
    ag = find_node(wf, "Sub-Agent Agendar")
    sm_old = ag["parameters"]["options"]["systemMessage"]

    # Find old PASO 5 block (from "PASO 5 — BUSCAR HORARIOS:" up to "PASO 6 —")
    paso5_start = sm_old.find("PASO 5 — BUSCAR HORARIOS:")
    paso6_start = sm_old.find("PASO 6 —")
    if paso5_start < 0 or paso6_start < 0:
        raise SystemExit("PASO 5 / PASO 6 markers not found")

    old_paso5 = sm_old[paso5_start:paso6_start]
    if "REGLA ANTI-ALUCINACION" in old_paso5:
        raise SystemExit("Already patched (REGLA ANTI-ALUCINACION present)")

    sm_new = sm_old.replace(old_paso5, PASO_5_NEW, 1)
    print(f"[Sub-Agent Agendar.systemMessage] {len(sm_old)}ch -> {len(sm_new)}ch ({len(sm_new)-len(sm_old):+d})")
    print(f"  PASO 5 old: {len(old_paso5)}ch -> new: {len(PASO_5_NEW)}ch")
    print(f"  REGLA ANTI-ALUCINACION present: {'REGLA ANTI-ALUCINACION' in sm_new}")

    if dry:
        print("\n=== DRY RUN ===")
        print("\n--- NEW toolDescription ---")
        print(new_td)
        print("\n--- NEW PASO 5 ---")
        print(PASO_5_NEW)
        return

    bh["parameters"]["toolDescription"] = new_td
    ag["parameters"]["options"]["systemMessage"] = sm_new

    res = put_workflow(wf)
    print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_workflow()
    bh2 = find_node(wf2, "buscar_horarios")
    ag2 = find_node(wf2, "Sub-Agent Agendar")
    ok = (
        "UNICO PARAMETRO" in bh2["parameters"]["toolDescription"]
        and "REGLA ANTI-ALUCINACION" in ag2["parameters"]["options"]["systemMessage"]
    )
    print("[verify]", "OK" if ok else "FAIL")
    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
