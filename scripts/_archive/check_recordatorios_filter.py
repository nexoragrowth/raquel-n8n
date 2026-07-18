"""
Chequea que el workflow de Recordatorios (7RqTApkvVavRmq3R) tenga el filtro
id_estado != 18 (skip confirmados) — Round 4 fix del 22/5.
"""
import sys
import json
import re
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require, env

N8N_BASE_URL = require("N8N_BASE_URL").rstrip("/")
N8N_API_KEY = require("N8N_API_KEY")
WF_ID = env("N8N_WORKFLOW_RECORDATORIOS_ID", "7RqTApkvVavRmq3R")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Accept": "application/json"}

print(f"Fetching workflow {WF_ID}...")
r = requests.get(f"{N8N_BASE_URL}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
r.raise_for_status()
wf = r.json()
print(f"Workflow: {wf.get('name')}  active={wf.get('active')}  nodes={len(wf.get('nodes', []))}")

# Buscar patrones del filtro
serialized = json.dumps(wf, ensure_ascii=False)

patterns = {
    "filtro id_estado != 18 (literal)": r"id_estado[^,}\"]*?!?=\s*[\"']?18",
    "estado 18 (en condiciones)": r"\b18\b",
    "skip confirmados (texto)": r"confirma",
    "estado en query Dentalink": r"estado",
}

print("\n--- Patrones encontrados ---")
for name, pat in patterns.items():
    matches = re.findall(pat, serialized, re.IGNORECASE)
    print(f"  {name}: {len(matches)} matches")

# Mostrar nodos clave + sus parametros relevantes
print("\n--- Nodos del workflow ---")
for n in wf.get("nodes", []):
    name = n.get("name", "")
    typ = n.get("type", "").split(".")[-1]
    params = n.get("parameters", {})
    print(f"  [{typ}] {name}")

# Buscar nodos IF / Filter / Code que mencionen estado/18/confirmado
print("\n--- Nodos con logica de filtrado ---")
for n in wf.get("nodes", []):
    name = n.get("name", "")
    typ = n.get("type", "").split(".")[-1]
    params_str = json.dumps(n.get("parameters", {}), ensure_ascii=False)
    if (re.search(r"\b18\b", params_str) or
        re.search(r"id_estado", params_str, re.IGNORECASE) or
        re.search(r"confirma", params_str, re.IGNORECASE) or
        re.search(r"estado", params_str, re.IGNORECASE)):
        print(f"\n  >>> {name} ({typ}) <<<")
        # Imprimir solo lo relevante (truncado)
        for k, v in n.get("parameters", {}).items():
            v_str = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            if (re.search(r"\b18\b", v_str) or
                re.search(r"id_estado", v_str, re.IGNORECASE) or
                re.search(r"estado", v_str, re.IGNORECASE) or
                re.search(r"confirma", v_str, re.IGNORECASE)):
                print(f"    {k}:")
                # Limitar largo
                lines = v_str.split("\n") if isinstance(v_str, str) else [v_str]
                for line in lines[:30]:
                    print(f"      {line[:300]}")
