"""
Reemplaza el nodo `buscar_horarios` del v6 (toolHttpRequest) por un toolWorkflow
que apunta al sub-WF "Buscar Horarios Validado" (GuDQ9VmKWZvQnerV).

Mantiene el MISMO nombre de nodo ("buscar_horarios") y posición para no romper
las conexiones al Sub-Agent Agendar (ai_tool connection).

El toolWorkflow expone `fecha` al LLM via $fromAI y la mapea al input del sub-WF.

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
SUBWF_ID = "GuDQ9VmKWZvQnerV"
HEADERS = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

TOOL_DESCRIPTION = (
    "Busca slots disponibles de la Dra. Raquel para UNA fecha concreta.\n\n"
    "PARAMETRO OBLIGATORIO: `fecha` en formato YYYY-MM-DD.\n"
    "- Paciente dice 'el 30 de junio' -> fecha='2026-06-30'\n"
    "- Paciente dice 'este viernes' -> calcula la fecha desde FECHA Y HORA ACTUAL\n\n"
    "Si no tenes una fecha concreta del paciente, NO llames esta tool: pedile primero que dia prefiere.\n"
    "Si el paciente pide una franja (mañana/tarde), pasa la fecha y filtra vos los slots devueltos por hora.\n\n"
    "La tool devuelve `resultado`: o bien la lista de turnos para esa fecha, o 'Sin turnos para [fecha]', "
    "o 'ERROR_FECHA' si la fecha es invalida (en ese caso pedile la fecha al paciente). "
    "NUNCA afirmes que no hay turnos para una fecha sin haber llamado esta tool con ESA fecha."
)


def get_workflow():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def backup(wf: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "workflows" / "history" / f"v6_PRE_BUSCAR_HORARIOS_TOOLWF_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def put_workflow(wf: dict) -> dict:
    allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
               "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
               "executionOrder", "callerPolicy", "callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, json=body, timeout=30)
    if not r.ok:
        print("PUT failed:", r.status_code, r.text[:800], file=sys.stderr)
        r.raise_for_status()
    return r.json()


def main():
    dry = "--dry" in sys.argv
    wf = get_workflow()
    print(f"GET v6 | active={wf.get('active')} nodes={len(wf['nodes'])}")

    out = backup(wf)
    print(f"backup -> {out}")

    # Find buscar_horarios node
    idx = None
    for i, n in enumerate(wf["nodes"]):
        if n["name"] == "buscar_horarios":
            idx = i
            break
    if idx is None:
        raise SystemExit("buscar_horarios node not found")

    old = wf["nodes"][idx]
    print(f"old type: {old['type']} v{old.get('typeVersion')}")

    # Build the new toolWorkflow node, preserving id/name/position
    new_node = {
        "parameters": {
            "description": TOOL_DESCRIPTION,
            "workflowId": {
                "__rl": True,
                "value": SUBWF_ID,
                "mode": "id",
            },
            "workflowInputs": {
                "mappingMode": "defineBelow",
                "value": {
                    "fecha": "={{ $fromAI('fecha', 'Fecha a buscar en formato YYYY-MM-DD (obligatoria, futura)', 'string') }}"
                },
                "matchingColumns": [],
                "schema": [
                    {
                        "id": "fecha",
                        "displayName": "fecha",
                        "required": False,
                        "defaultMatch": False,
                        "display": True,
                        "canBeUsedToMatch": True,
                        "type": "string",
                    }
                ],
                "attemptToConvertTypes": False,
                "convertFieldsToString": True,
            },
        },
        "id": old["id"],
        "name": "buscar_horarios",
        "type": "@n8n/n8n-nodes-langchain.toolWorkflow",
        "typeVersion": 2.2,
        "position": old["position"],
    }

    wf["nodes"][idx] = new_node

    if dry:
        print(json.dumps(new_node, indent=2, ensure_ascii=False))
        print("\n=== DRY RUN ===")
        return

    res = put_workflow(wf)
    print(f"PUT OK updatedAt={res.get('updatedAt')}")

    # Verify
    wf2 = get_workflow()
    for n in wf2["nodes"]:
        if n["name"] == "buscar_horarios":
            ok = n["type"] == "@n8n/n8n-nodes-langchain.toolWorkflow"
            print(f"[verify] type={n['type']} -> {'OK' if ok else 'FAIL'}")
            if not ok:
                sys.exit(2)


if __name__ == "__main__":
    main()
