"""
Fix: Pre-filtro Cierre estaba descartando mensajes tipo
  "Confirmamos turno para esa hora, gracias"
porque caian en la regla `termina_gracias` (tLen<=50, sin digitos).

La whitelist de confirmaciones era exact-match y no captura formas verbales
como "confirmamos", "asistiremos", "vamos a ir", "voy hoy a abonar, gracias".

Fix: agregar bloque regex de verbos de confirmacion ANTES del filtro
`termina_gracias` y `cierres exactos`. Respeta negaciones.

Aplica al workflow v6 main (O155MqHgOSaNZ9ye).
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

INSERT_BLOCK = """// === Verbo de confirmacion/asistencia explicito — pasar al Router ===
// Captura formas verbales que la whitelist exacta no toma:
//   "Confirmamos turno para esa hora, gracias"
//   "Confirme el turno", "Asistiremos", "Vamos a ir", "Voy hoy a abonar, gracias"
// Excluye negaciones: "no confirmo", "no asisto", "no voy", "no vamos".
const negacionConfirm = /\\bno\\s+(confirm|asist|voy|vamos|ir[eé]?)/;
const confirmVerbo = /\\b(confirm[ao]m?(os|s|n)?|confirm[éeoó]|confirm(ar|amos|aron|are|aremos)|asist[oei](mos|re|remos|r[ée])?|ir[eé]|iremos|vamos|voy)\\b/;
if (!negacionConfirm.test(t) && confirmVerbo.test(t)) {
  return [{ json: { skip: false, reason: 'confirmacion_verbo', text } }];
}

"""


def get_workflow():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def backup(wf: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "workflows" / "history" / f"v6_PRE_FIX_PREFILTRO_CONFIRM_VERBO_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def find_node(wf: dict, name: str) -> dict:
    for n in wf["nodes"]:
        if n["name"] == name:
            return n
    raise SystemExit(f"Node {name!r} not found")


def patch_node(node: dict, insert_block: str) -> tuple[str, str]:
    """Returns (old_code, new_code). Inserts INSERT_BLOCK right before the
    '// === Emoji-only — descartar ===' comment (so it runs before
    termina_gracias / cierres exactos)."""
    code = node["parameters"]["jsCode"]
    marker = "// === Emoji-only — descartar ==="
    if marker not in code:
        raise SystemExit(f"Marker {marker!r} not found in node code — manual review needed")
    if "confirmacion_verbo" in code:
        raise SystemExit("Block already applied (found 'confirmacion_verbo')")
    new_code = code.replace(marker, insert_block + marker, 1)
    return code, new_code


def put_workflow(wf: dict) -> dict:
    allowed_settings = {
        "saveExecutionProgress",
        "saveManualExecutions",
        "saveDataErrorExecution",
        "saveDataSuccessExecution",
        "executionTimeout",
        "errorWorkflow",
        "timezone",
        "executionOrder",
        "callerPolicy",
        "callerIds",
    }
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed_settings}
    body = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": settings,
        "staticData": wf.get("staticData"),
    }
    r = requests.put(
        f"{BASE}/api/v1/workflows/{WF_ID}",
        headers=HEADERS,
        json=body,
        timeout=30,
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

    print("[3/4] Patch Pre-filtro Cierre")
    node = find_node(wf, "Pre-filtro Cierre")
    old, new = patch_node(node, INSERT_BLOCK)
    delta_lines = new.count("\n") - old.count("\n")
    print(f"      +{delta_lines} lines | old={len(old)}ch new={len(new)}ch")

    if dry:
        print("\n=== DRY RUN: showing diff snippet ===")
        # Print 6 lines around the insertion
        new_lines = new.splitlines()
        for i, ln in enumerate(new_lines):
            if "confirmacion_verbo" in ln or "negacionConfirm" in ln:
                start = max(0, i - 1)
                end = min(len(new_lines), i + 12)
                for j in range(start, end):
                    print(f"  {j:3d} | {new_lines[j]}")
                break
        print("\n(dry run — not PUTting. Re-run without --dry to apply.)")
        return

    node["parameters"]["jsCode"] = new

    print("[4/4] PUT workflow")
    res = put_workflow(wf)
    print(f"      OK active={res.get('active')} updatedAt={res.get('updatedAt')}")

    # Verify
    wf2 = get_workflow()
    node2 = find_node(wf2, "Pre-filtro Cierre")
    if "confirmacion_verbo" in node2["parameters"]["jsCode"]:
        print("[verify] OK — confirmacion_verbo block present in live workflow")
    else:
        print("[verify] FAIL — block not present after PUT")
        sys.exit(2)


if __name__ == "__main__":
    main()
