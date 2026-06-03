"""
Fix Router — clasificacion de preguntas DENTRO de flow operativo activo.

Bug visible 27/05 18:26 (paciente Ale / Andres Quispe Doria Medina):
  - Flow Agendar activo (bot ya ofreció slots dos veces)
  - Paciente: "O dígame qué fechas tiene disponibles por la tarde?"
  - Router clasificó como `consulta_general` (regla "PREGUNTA != ACCION")
  - Sub-Agent General no tiene tool buscar_horarios -> escaló a Iri

Causa: la regla "PREGUNTA != ACCION" del Router toma precedencia sobre la
regla de CONTINUACION cuando la pregunta es sobre el dominio del sub-agent
actualmente activo. La pregunta sobre "disponibilidad de slots" es parte del
flow Agendar, no consulta general.

Fix: insertar una excepcion secundaria con ejemplos concretos del caso real,
para que preguntas sobre disponibilidad/fechas dentro de un flow agendar (o
cancelar/confirmar) sigan en ese flow.

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


CONTINUACION_BLOCK = """**EXCEPCION SECUNDARIA — PREGUNTAS DENTRO DEL MISMO FLOW OPERATIVO:**

La regla "PREGUNTA != ACCION" (mas abajo, regla 0) NO aplica cuando la pregunta es CONTINUACION del flow ya activo. Si el ultimo AI fue una respuesta de un sub-agent operativo (Agendar/Cancelar/Confirmar) y el paciente pregunta sobre algo del MISMO dominio, sigue siendo el mismo intent.

Casos concretos:

- **Flow AGENDAR activo** (ultimo AI: ofrecio slots / pidio fecha-franja / pidio DNI / confirmo pre-reserva) + paciente pregunta sobre **disponibilidad de horarios o fechas** ("que fechas tenes disponibles?", "hay para la tarde?", "tienen para manana?", "que horarios hay el [dia]?", "se puede el [fecha]?", "hay alguno mas tarde?", "que tenes para mas adelante?") -> intent = `agendar_nuevo` (CONTINUACION, NO consulta_general).

- **Flow CANCELAR activo** (ultimo AI: ofrecio slots de reprogramacion / pregunto que turno cancelar) + paciente pregunta sobre **fechas o disponibilidad** ("que dia tenes libre?", "hay para martes?") -> intent = `cancelar_o_reprogramar` (CONTINUACION).

- **Flow CONFIRMAR activo** + paciente pregunta sobre el turno ("a que hora era?", "que dia es?") -> intent = `confirmar_post_recordatorio` (CONTINUACION).

EJEMPLOS REALES (incidente 27/05 18:26):
- AI previo (Agendar): "Los proximos cupos: 4 de junio a las 10 de la manana, 18 de junio a las 10..." + paciente: "El 30 de junio?" -> `agendar_nuevo` (continuacion).
- AI previo (Agendar): "Para el martes 30 de junio no tengo turnos. Los mas cercanos: 18 jun 10AM, 19 jun 10:30AM..." + paciente: "O digame que fechas tiene disponibles por la tarde?" -> `agendar_nuevo` (continuacion — pregunta sobre slots dentro de flow agendar, NO consulta_general).
- AI previo (Agendar): "Le confirmo: martes 4 de junio a las 10. Procedo?" + paciente: "Si" -> `agendar_nuevo`.

CLAVE: las PREGUNTAS QUE SON DEL DOMINIO DEL SUB-AGENT ACTIVO siguen en su flow. Solo cambia a consulta_general si la pregunta es sobre INFO CANNED (alias, horarios de la clinica, direccion, precio de consulta, forma de pago) o un tema completamente fuera del flow.

"""


def get_workflow():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def backup(wf: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "workflows" / "history" / f"v6_PRE_ROUTER_CONTINUACION_PREGUNTA_{ts}.json"
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
    print(f"GET workflow {WF_ID} | active={wf.get('active')}")

    out = backup(wf)
    print(f"backup -> {out}")

    node = find_node(wf, "Router - Clasificar Intent")
    sm_old = node["parameters"]["options"]["systemMessage"]

    if "EXCEPCION SECUNDARIA" in sm_old:
        raise SystemExit("Already patched")

    # Insert AFTER the "Si la memoria esta vacia..." paragraph and BEFORE "5 INTENTS posibles"
    marker = "5 INTENTS posibles:"
    if marker not in sm_old:
        raise SystemExit(f"Marker not found: {marker!r}")

    sm_new = sm_old.replace(marker, CONTINUACION_BLOCK + marker, 1)

    print(f"old={len(sm_old)}ch new={len(sm_new)}ch delta={len(sm_new)-len(sm_old):+d}ch")
    print(f"block inserted: {'EXCEPCION SECUNDARIA' in sm_new}")

    if dry:
        print("=== DRY RUN ===")
        return

    node["parameters"]["options"]["systemMessage"] = sm_new

    res = put_workflow(wf)
    print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_workflow()
    n2 = find_node(wf2, "Router - Clasificar Intent")
    live = n2["parameters"]["options"]["systemMessage"]
    if "EXCEPCION SECUNDARIA" in live and "incidente 27/05 18:26" in live:
        print("[verify] OK — Router patched live")
    else:
        print("[verify] FAIL")
        sys.exit(2)


if __name__ == "__main__":
    main()
