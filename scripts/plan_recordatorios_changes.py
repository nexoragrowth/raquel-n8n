"""
Lee el workflow vivo de Recordatorios, hace backup pre, y muestra el plan
de cambios: que nodos agregar + connections nuevas. NO modifica nada.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require, env

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF_ID = env("N8N_WORKFLOW_RECORDATORIOS_ID", "7RqTApkvVavRmq3R")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json"}

print(f"Fetching workflow {WF_ID}...")
wf = requests.get(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H, timeout=30).json()

# Backup pre
REPO = Path(__file__).resolve().parents[1]
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak = REPO / "workflows" / "history" / f"recordatorios_PRE_INSERT_TABLA_{ts}.json"
bak.parent.mkdir(parents=True, exist_ok=True)
bak.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Backup pre -> {bak.relative_to(REPO)}\n")

# Print nodos actuales + connections
print(f"=== Nodos actuales ({len(wf['nodes'])}) ===")
for n in wf["nodes"]:
    print(f"  [{n['type'].split('.')[-1]:20s}] {n['name']}")

print(f"\n=== Connections actuales ===")
for src, conn in wf.get("connections", {}).items():
    for kind, branches in conn.items():
        for i, br in enumerate(branches or []):
            for dest in br or []:
                print(f"  {src} --[{kind}/{i}]--> {dest['node']}")

# Buscar el nodo "Enviar WhatsApp" para insertar despues
target = None
for n in wf["nodes"]:
    if "enviar" in n["name"].lower() and "whatsapp" in n["name"].lower():
        target = n
        break

print(f"\n=== Nodo target post-send ===")
if target:
    print(f"  name: {target['name']}")
    print(f"  type: {target['type']}")
    print(f"  position: {target.get('position')}")
else:
    print("  !! No encontrado 'Enviar WhatsApp' — revisar nombres")

# Mostrar el nodo "Preparar mensaje" para ver que fields tiene disponibles
prep = next((n for n in wf["nodes"] if "preparar" in n["name"].lower()), None)
if prep:
    print(f"\n=== 'Preparar mensaje' jsCode (primeras 80 lineas) ===")
    code = prep.get("parameters", {}).get("jsCode", "")
    for i, line in enumerate(code.split("\n")[:80], 1):
        print(f"  {i:3d}  {line[:160]}")

# Buscar trigger schedule actual
trig = next((n for n in wf["nodes"] if "schedule" in n["type"].lower() or "cron" in n["name"].lower()), None)
print(f"\n=== Trigger actual ===")
if trig:
    print(f"  {trig['name']} ({trig['type']})")
    print(f"  params: {json.dumps(trig.get('parameters', {}), ensure_ascii=False, indent=2)[:400]}")

print(f"\n=== Credenciales Postgres existentes en este wf ===")
for n in wf["nodes"]:
    creds = n.get("credentials", {})
    if any("postgres" in k.lower() for k in creds.keys()):
        print(f"  {n['name']} -> {creds}")
