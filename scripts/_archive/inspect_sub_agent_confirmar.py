"""
Lee detalles del Sub-Agent Confirmar y Cancelar:
- system prompt completo
- tools wireadas
- text input
Para diseñar la modificacion con consultar_recordatorios_abiertos.
"""
import json
import io
import sys
from pathlib import Path

import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json"}

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()

for target in ("Sub-Agent Confirmar", "Sub-Agent Cancelar"):
    n = next((x for x in wf["nodes"] if x["name"] == target), None)
    if not n:
        print(f"NOT FOUND: {target}")
        continue
    print(f"\n{'='*80}\n{target}\n{'='*80}")
    p = n.get("parameters", {})
    # Mostrar text input
    text = p.get("text", "")
    print(f"\n[TEXT INPUT]:\n{text[:1000]}")
    # System prompt
    opts = p.get("options", {})
    sysmsg = opts.get("systemMessage", "")
    print(f"\n[SYSTEM PROMPT] ({len(sysmsg)} chars):\n{sysmsg}")

# Listar conexiones AI Tool de cada Sub-Agent
print(f"\n{'='*80}\nTools wireadas a cada Sub-Agent (ai_tool connections)\n{'='*80}")
for src, conn in wf.get("connections", {}).items():
    for kind, branches in conn.items():
        if kind != "ai_tool": continue
        for br in branches or []:
            for dest in br or []:
                print(f"  {src} --[ai_tool]--> {dest['node']}")

# Ver el nodo confirmar_turno y cancelar_turno
for tname in ("confirmar_turno", "cancelar_turno"):
    n = next((x for x in wf["nodes"] if x["name"] == tname), None)
    if not n: continue
    print(f"\n{'='*80}\n{tname}\n{'='*80}")
    p = n.get("parameters", {})
    print(f"toolDescription: {p.get('toolDescription', '')[:500]}")
    print(f"url: {p.get('url', '')}")
    print(f"method: {p.get('method', '')}")
    print(f"headerParameters: {json.dumps(p.get('headerParameters', {}), ensure_ascii=False)[:300]}")
    print(f"sendBody: {p.get('sendBody')}")
    print(f"bodyParameters: {json.dumps(p.get('bodyParameters', {}), ensure_ascii=False)[:300]}")
    creds = n.get("credentials", {})
    print(f"credentials: {creds}")

# Tambien ver: Edit Fields (input al Sub-Agent) — para saber que vars tiene disponibles
n = next((x for x in wf["nodes"] if x["name"] == "Get Paciente Context"), None)
if n:
    print(f"\n{'='*80}\nGet Paciente Context (rama de hidratacion)\n{'='*80}")
    print(json.dumps(n.get("parameters", {}), ensure_ascii=False, indent=2)[:800])
