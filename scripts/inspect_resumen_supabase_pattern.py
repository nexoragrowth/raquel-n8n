"""
Lee el workflow de Resumen Clinico (BO1cdE8xmqln4IeO) para sacar el patron
exacto de como escribe a Supabase (cred id, headers, etc.) y reusarlo en
el cron de Recordatorios.
"""
import json
import sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json"}

wf = requests.get(f"{N8N}/api/v1/workflows/BO1cdE8xmqln4IeO", headers=H, timeout=30).json()
print(f"Workflow: {wf['name']}  nodes={len(wf['nodes'])}\n")

for n in wf["nodes"]:
    typ = n["type"].split(".")[-1]
    print(f"[{typ}] {n['name']}")
    creds = n.get("credentials", {})
    if creds:
        print(f"  credentials: {json.dumps(creds, ensure_ascii=False)}")
    if typ in ("httpRequest", "postgres", "supabase"):
        params = n.get("parameters", {})
        # Mostrar campos clave
        for k in ["url", "method", "table", "operation", "schema",
                  "authentication", "genericAuthType"]:
            if k in params:
                print(f"  {k}: {params[k]}")
        if "headerParameters" in params:
            print(f"  headers: {json.dumps(params.get('headerParameters'), ensure_ascii=False)[:300]}")
        if "bodyParameters" in params:
            print(f"  body: {json.dumps(params.get('bodyParameters'), ensure_ascii=False)[:300]}")
        if "jsonBody" in params:
            print(f"  jsonBody: {params.get('jsonBody')[:300]}")
    print()
