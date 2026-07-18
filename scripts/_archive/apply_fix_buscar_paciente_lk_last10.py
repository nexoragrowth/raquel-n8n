"""
Fix `buscar_paciente_dentalink` tool del v6: estrategia lk-last10.

Antes: toolDescription le pedia al LLM probar HASTA 5 variantes de celular en
serie (con/sin 9, con/sin +, sin codigo pais). Funcionaba a veces, pero
dependiendo del LLM iterar. Y a veces se rendia en la variante 1 (caso Julieta).

Ahora: UNA SOLA llamada usando `lk` (LIKE de Dentalink) contra los ULTIMOS 10
DIGITOS del celular. Esos 10 digitos estan en TODOS los formatos posibles
(con/sin 9, con/sin +, sin codigo pais), entonces matchea siempre.

  WA `5493884884432` (13 digitos) -> last10 = `3884884432`
  q={"celular":{"lk":"3884884432"}}

Matchea contra Dentalink guardado como:
  +5493884884432, +543884884432, 5493884884432, 3884884432

Mismo principio que se aplico hoy en el Sub-WF CancelarReprogramar
(scripts/apply_fix_*).

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
WF_ID = os.environ.get("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")

HEADERS = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}


NEW_TOOL_DESCRIPTION = (
    "Busca pacientes en Dentalink. Param q es JSON string con filtro.\n\n"
    "ESTRATEGIA OBLIGATORIA cuando buscas por celular:\n"
    "Usa SIEMPRE el operador `lk` (LIKE) contra los ULTIMOS 10 DIGITOS del celular del paciente.\n"
    "Esos 10 digitos finales aparecen en TODOS los formatos posibles en Dentalink (con/sin +, con/sin 9 movil, con/sin codigo pais), entonces una sola llamada los captura a todos.\n\n"
    "Para celular WA `5493884884432` (13 digitos):\n"
    "  - Tomar los ultimos 10 = `3884884432`\n"
    "  - q={\"celular\":{\"lk\":\"3884884432\"}}\n\n"
    "Esa UNICA llamada matchea contra Dentalink guardado como `+5493884884432`, `+543884884432`, `5493884884432`, `3884884432`, etc.\n\n"
    "BUSQUEDA POR NOMBRE como fallback SOLO si lk-last10 devuelve vacio:\n"
    "  q={\"nombre\":{\"lk\":\"<apellido o nombre exacto>\"}}\n\n"
    "REGLA: NUNCA crees un paciente nuevo sin haber probado primero lk-last10 Y la busqueda por nombre/apellido. Es un BUG GRAVE crear duplicados."
)


def get_workflow():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def backup(wf: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "workflows" / "history" / f"v6_PRE_BUSCAR_PACIENTE_LK_LAST10_{ts}.json"
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

    print(f"[1/4] GET workflow {WF_ID}")
    wf = get_workflow()
    print(f"      name={wf['name']!r} nodes={len(wf['nodes'])} active={wf.get('active')}")

    print("[2/4] Backup")
    out = backup(wf)
    print(f"      -> {out}")

    print("[3/4] Patch buscar_paciente_dentalink toolDescription")
    node = find_node(wf, "buscar_paciente_dentalink")
    old = node["parameters"].get("toolDescription", "")
    new = NEW_TOOL_DESCRIPTION
    print(f"      old={len(old)}ch new={len(new)}ch delta={len(new)-len(old):+d}ch")
    print(f"      contains 'lk-last10' in new: {'lk-last10' in new}")
    print(f"      contains '5 variantes' in new: {'5 variantes' in new}")

    if dry:
        print("\n=== DRY RUN — not PUTting ===")
        print("\n--- NEW toolDescription ---")
        print(new)
        return

    node["parameters"]["toolDescription"] = new

    print("[4/4] PUT workflow")
    res = put_workflow(wf)
    print(f"      OK active={res.get('active')} updatedAt={res.get('updatedAt')}")

    wf2 = get_workflow()
    node2 = find_node(wf2, "buscar_paciente_dentalink")
    live = node2["parameters"].get("toolDescription", "")
    if "ULTIMOS 10 DIGITOS" in live and "5 variantes" not in live:
        print("[verify] OK — lk-last10 strategy live, 5-variantes wording removed")
    else:
        print("[verify] FAIL — live toolDescription not as expected")
        print(live[:500])
        sys.exit(2)


if __name__ == "__main__":
    main()
