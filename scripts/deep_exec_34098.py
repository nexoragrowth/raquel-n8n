"""
Inspeccion profunda de exec 34098 — caso Genefes Confirmados.
Vuelca:
- Input/output reales de cada tool call
- intermediateSteps si existen
- system prompt visible
- Mensaje a Dentalink y respuesta
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N_BASE_URL = require("N8N_BASE_URL").rstrip("/")
N8N_API_KEY = require("N8N_API_KEY")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Accept": "application/json"}

EID = 34098
print(f"Fetching exec {EID}...")
d = requests.get(f"{N8N_BASE_URL}/api/v1/executions/{EID}?includeData=true",
                 headers=HEADERS, timeout=30).json()

rd = d.get("data", {}).get("resultData", {}).get("runData", {})
print(f"Total nodes ejecutados: {len(rd)}")

# Volcar TODO el detalle de los nodos del sub-agent y tools
interesting = []
for k in rd.keys():
    kl = k.lower()
    if any(x in kl for x in [
        "sub-agent confirmar", "subagent confirmar", "confirmar_turno",
        "ver_turnos", "buscar_paciente", "escalar_", "get paciente",
        "edit fields", "router", "memoria", "memory"
    ]):
        interesting.append(k)

print(f"\nNodos de interes: {len(interesting)}\n")

OUT = Path(__file__).resolve().parents[1] / "tests" / f"deep_exec_{EID}.json"
dump = {}
for n in interesting:
    dump[n] = rd[n]
OUT.write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"JSON volcado en: {OUT.relative_to(Path(__file__).resolve().parents[1])}")
print(f"Tamano: {OUT.stat().st_size} bytes\n")

# Imprimir cada nodo con su data principal
for n in interesting:
    runs = rd[n]
    print(f"\n{'=' * 80}")
    print(f"NODO: {n}  ({len(runs)} runs)")
    print('=' * 80)
    for i, run in enumerate(runs):
        print(f"\n--- run {i} ---")
        data = run.get("data", {})
        # Input
        # Output principal
        main = data.get("main", [])
        if main and main[0]:
            for j, item in enumerate(main[0][:3]):  # primeros 3 items
                ij = item.get("json", {})
                print(f"  out[{j}] keys: {list(ij.keys())[:15]}")
                # Volcar contenido relevante
                for key, val in ij.items():
                    sval = json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val
                    safe = sval.encode("ascii", "replace").decode("ascii")
                    if len(safe) > 800:
                        safe = safe[:800] + "...[TRUNC]"
                    print(f"    {key}: {safe}")
        # AI tool data (langchain pone los tool calls en ai_languageModel / ai_tool)
        for ai_key in ["ai_languageModel", "ai_tool", "ai_memory", "ai_outputParser"]:
            if ai_key in data:
                print(f"  {ai_key}: {len(data[ai_key])} entries")
                for ent in data[ai_key][:3]:
                    print(f"    {json.dumps(ent, ensure_ascii=False)[:600].encode('ascii','replace').decode('ascii')}")
