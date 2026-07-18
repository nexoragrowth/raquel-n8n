"""Fix robusto del bug lk-last10:
1. Agrega campo phone_last10 al nodo "Edit Fields - Extraer Datos" (Set node).
2. La expresion n8n calcula los ultimos 10 digitos correctamente.

El partial paciente_context_runtime.md ya tiene que referenciar este campo.

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
NODE = "Edit Fields - Extraer Datos"

NEW_FIELD = {
    "id": "f-phone-last10",
    "name": "phone_last10",
    "type": "string",
    "value": "={{ $('Webhook - Evolution API').first().json.body.data.key.remoteJid.replace('@s.whatsapp.net', '').slice(-10) }}"
}


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
    if not n: print(f"!! {NODE} no encontrado"); sys.exit(2)
    assignments = n["parameters"]["assignments"]["assignments"]
    # idempotencia
    if any(a["name"] == "phone_last10" for a in assignments):
        print("!! phone_last10 ya existe"); sys.exit(3)
    # insertar despues de phone (para que quede ordenado)
    new_list = []
    for a in assignments:
        new_list.append(a)
        if a["name"] == "phone":
            new_list.append(NEW_FIELD)
    n["parameters"]["assignments"]["assignments"] = new_list
    print(f"Agregando field phone_last10 al Edit Fields - Extraer Datos")
    print(f"  expresion: {NEW_FIELD['value']}")
    if args.dry or not args.apply: print("[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_phone_last10_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(x for x in wf2["nodes"] if x["name"] == NODE)
    ok = any(a["name"] == "phone_last10" for a in n2["parameters"]["assignments"]["assignments"])
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
