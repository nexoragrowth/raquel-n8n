"""
Fix sintaxis de headers en las 3 tools nuevas del v6:
de  parametersHeaders.values
a   headerParameters.parameters
para que toolHttpRequest realmente envie los headers apikey + Bearer.

Lo mismo para parametersQuery (probable).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_FIXHDRS_{ts}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_FIXHDRS_{ts}.json")

TARGET_NAMES = ["consultar_recordatorios_abiertos",
                "marcar_recordatorio_confirmado",
                "marcar_recordatorio_cancelado"]

for nm in TARGET_NAMES:
    n = next((x for x in wf["nodes"] if x["name"] == nm), None)
    if not n:
        print(f"  !! {nm} no encontrado")
        continue
    p = n["parameters"]
    # Move parametersHeaders.values -> headerParameters.parameters
    if "parametersHeaders" in p:
        old = p.pop("parametersHeaders")
        vals = old.get("values", [])
        p["headerParameters"] = {"parameters": vals}
        print(f"  [{nm}] migrated parametersHeaders -> headerParameters ({len(vals)} headers)")
    # Move parametersQuery.values -> queryParameters.parameters
    if "parametersQuery" in p:
        old = p.pop("parametersQuery")
        vals = old.get("values", [])
        p["queryParameters"] = {"parameters": vals}
        print(f"  [{nm}] migrated parametersQuery -> queryParameters ({len(vals)} params)")
    # specifyHeaders/specifyQuery: removerlos si quedaron (sintaxis vieja)
    p.pop("specifyHeaders", None)
    p.pop("specifyQuery", None)
    p.pop("specifyBody", None)
    # sendBody: ok dejarlo

# PUT
allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
payload = {"name": wf["name"], "nodes": wf["nodes"],
           "connections": wf["connections"], "settings": settings}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]

r = requests.put(f"{N8N}/api/v1/workflows/{WF}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
print(f"\nPUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:500])
    sys.exit(1)

# Verify
wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_FIXHDRS_{ts}.json").write_text(json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_FIXHDRS_{ts}.json")

for nm in TARGET_NAMES:
    n = next((x for x in wf_post["nodes"] if x["name"] == nm), None)
    if n:
        p = n["parameters"]
        hdr = p.get("headerParameters", {}).get("parameters", [])
        qp = p.get("queryParameters", {}).get("parameters", [])
        print(f"  {nm}: headerParameters={len(hdr)} queryParameters={len(qp)}")
