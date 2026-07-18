"""
Fix Sub-Agent General — cortesia en primera respuesta + canned menos cortantes.

Caso 27/05 (paciente "Sil"):
  Paciente: "Hola buenas tardes, una consulta... atienden con medife?"
  Bot:     "Para temas de obra social le paso a la secretaria Irina, ella maneja los convenios."

Bug: el LLM siguio la canned hardcoded sin saludar ni presentarse. La regla
IDENTIFICACION ya existe pero solo dispara con saludo solo, no cuando saludo
viene combinado con pregunta concreta.

Fix:
1. Agregar regla UNIVERSAL "CORTESIA EN PRIMERA RESPUESTA" antes de SALUDOS_SOLOS,
   con ejemplos explicitos de saludo + presentacion + canned integrado.
2. Suavizar las canned hardcoded (obras sociales, tratamientos) para que sean
   menos cortantes — fluyen mejor en una frase educada.

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


CORTESIA_BLOCK = """**CORTESIA EN PRIMERA RESPUESTA — REGLA UNIVERSAL** (aplica antes que cualquier otra regla de respuesta)

Si es la PRIMERA vez que respondes en esta conversacion (no hay mensajes AI previos en memoria reciente / ultimas 24h), abri SIEMPRE asi, sin importar si el paciente saludo o vino directo con una pregunta:

1. Saludo segun la hora actual (mira FECHA Y HORA ACTUAL mas abajo):
   - 06:00-12:00 -> "Hola, buen dia."
   - 12:00-20:00 -> "Hola, buenas tardes."
   - 20:00-06:00 -> "Hola, buenas noches."
2. Presentacion: " Soy Asiri, la asistente virtual de la Dra. Raquel."
3. Despues integras la respuesta (canned, info, accion o escalacion) en la misma respuesta, no como mensaje aparte.

EJEMPLOS REALES:

- Paciente: "Hola buenas tardes, una consulta... atienden con medife?"
  Vos: "Hola, buenas tardes. Soy Asiri, la asistente virtual de la Dra. Raquel. Para temas de obra social le paso a Irina, la secretaria, que es quien maneja los convenios. En un momento le responde."

- Paciente: "Cuanto sale la consulta?"
  Vos: "Hola, buen dia. Soy Asiri, la asistente virtual de la Dra. Raquel. El valor de la consulta es de $40.000. Se abona en efectivo, transferencia o debito/credito Macro (hasta 3 cuotas)."

- Paciente (segunda interaccion ya con AI previo en memoria): "Y aceptan transferencia?"
  Vos: "Si, aceptamos transferencia. Alias: dra.raquel.aurea — Titular: Laura Raquel Rodriguez."
  (NO repetir saludo ni presentacion cuando ya hubo respuesta tuya antes en la conversacion)

CRITICAL: la canned hardcoded de mas abajo NO es lo unico que respondes. La canned se INTEGRA en la frase educada cuando es primera respuesta. NO mandes la canned cortante sola si todavia no saludaste ni te presentaste en esta conversacion.

"""


# Canned hardcoded a suavizar
CANNED_REPLACEMENTS = [
    (
        "canned: \"Para temas de obra social le paso a la secretaria Irina, ella maneja los convenios.\"",
        "canned: \"Para temas de obra social le paso a Irina, la secretaria, que es quien maneja los convenios. En un momento le responde.\"",
    ),
    (
        "canned: \"Eso lo evalua la Dra. Raquel en consulta. Le paso a la secretaria Irina para coordinarle una primera visita.\"",
        "canned: \"Eso es algo que la Dra. Raquel le evalua en consulta. Le paso a Irina, la secretaria, para coordinarle una primera visita.\"",
    ),
    (
        "canned: \"Le paso tu consulta a la secretaria lo más pronto posible.\"",
        "canned: \"Le paso su consulta a Irina, la secretaria, que en un momento le responde.\"",
    ),
    (
        "canned: \"Le paso a la secretaria Irina para que le ayude lo antes posible.\"",
        "canned: \"Le paso a Irina, la secretaria, para que le ayude lo antes posible.\"",
    ),
    (
        "canned: \"Por privacidad necesito que lo coordinemos con la secretaria. Le paso a Iri.\"",
        "canned: \"Por privacidad necesito que esto lo coordinemos con la secretaria. Le paso a Irina, en un momento le responde.\"",
    ),
]


def get_workflow():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def backup(wf: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "workflows" / "history" / f"v6_PRE_GENERAL_CORTESIA_{ts}.json"
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

    print(f"[1/5] GET workflow {WF_ID}")
    wf = get_workflow()

    print("[2/5] Backup")
    out = backup(wf)
    print(f"      -> {out}")

    print("[3/5] Patch Sub-Agent General prompt")
    node = find_node(wf, "Sub-Agent General")
    sm_old = node["parameters"]["options"]["systemMessage"]

    if "CORTESIA EN PRIMERA RESPUESTA" in sm_old:
        raise SystemExit("Already patched")

    marker = "**SALUDOS SOLOS NUNCA ESCALAN**"
    if marker not in sm_old:
        raise SystemExit(f"Marker not found: {marker!r}")

    sm_new = sm_old.replace(marker, CORTESIA_BLOCK + marker, 1)

    # Replace canneds
    replaced = []
    for old, new in CANNED_REPLACEMENTS:
        if old in sm_new:
            sm_new = sm_new.replace(old, new, 1)
            replaced.append(old[:60])
        else:
            print(f"      [warn] canned not found: {old[:60]}...")

    print(f"      old={len(sm_old)}ch new={len(sm_new)}ch delta={len(sm_new)-len(sm_old):+d}ch")
    print(f"      canneds replaced: {len(replaced)}/{len(CANNED_REPLACEMENTS)}")
    print(f"      cortesia block inserted: {'CORTESIA EN PRIMERA RESPUESTA' in sm_new}")

    if dry:
        print("\n=== DRY RUN ===")
        return

    node["parameters"]["options"]["systemMessage"] = sm_new

    print("[4/5] PUT workflow")
    res = put_workflow(wf)
    print(f"      OK updatedAt={res.get('updatedAt')}")

    print("[5/5] Verify")
    wf2 = get_workflow()
    n2 = find_node(wf2, "Sub-Agent General")
    live = n2["parameters"]["options"]["systemMessage"]
    if "CORTESIA EN PRIMERA RESPUESTA" in live and "Irina, la secretaria" in live:
        print("[verify] OK")
    else:
        print("[verify] FAIL")
        sys.exit(2)


if __name__ == "__main__":
    main()
