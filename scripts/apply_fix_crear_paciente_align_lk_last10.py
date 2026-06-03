"""
Alinear la toolDescription de `crear_paciente_dentalink` con lk-last10.

Antes: "SOLO usar despues de que buscar_paciente_dentalink fallo con las 5 variantes
de celular + fallback por apellido."

Despues: "SOLO usar despues de que buscar_paciente_dentalink fallo con lk-last10
+ fallback por apellido."

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


def get_workflow():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def backup(wf: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "workflows" / "history" / f"v6_PRE_CREAR_PACIENTE_ALIGN_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


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
    out = backup(wf)
    print(f"backup -> {out}")

    node = None
    for n in wf["nodes"]:
        if n["name"] == "crear_paciente_dentalink":
            node = n
            break
    if not node:
        raise SystemExit("crear_paciente_dentalink not found")

    old = node["parameters"]["toolDescription"]
    new = old.replace(
        "fallo con las 5 variantes de celular + fallback por apellido",
        "fallo con lk-last10 (ultimos 10 digitos del celular usando operador `lk`) Y fallback por apellido",
    )
    if old == new:
        print("Nothing to change (string not found)")
        return

    print(f"delta={len(new)-len(old):+d}ch")
    print("NEW description:")
    print(new[:600])

    if dry:
        print("\n=== DRY RUN — not PUTting ===")
        return

    node["parameters"]["toolDescription"] = new
    res = put_workflow(wf)
    print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_workflow()
    for n in wf2["nodes"]:
        if n["name"] == "crear_paciente_dentalink":
            if "lk-last10" in n["parameters"]["toolDescription"] and "5 variantes" not in n["parameters"]["toolDescription"]:
                print("[verify] OK")
            else:
                print("[verify] FAIL")
                sys.exit(2)


if __name__ == "__main__":
    main()
