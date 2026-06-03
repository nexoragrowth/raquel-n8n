"""
DRY RUN: muestra los reemplazos exactos que se harian para aplicar 'Asiri'
en los Sub-Agents. NO hace PUT al workflow.
"""
import json, sys, re
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json"}

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()

SUB_AGENTS = ["Sub-Agent Confirmar", "Sub-Agent Cancelar", "Sub-Agent Agendar",
              "Sub-Agent Urgencia", "Sub-Agent General"]

# Patrones a buscar — los muestro TODOS antes de proponer reemplazo
search_patterns = [
    r"soy la asistente virtual de la Dra\.?\s*Raquel\.?",
    r"Soy la asistente virtual de la Dra\.?\s*Raquel\.?",
    r"la asistente virtual de la Dra\.?\s*Raquel",
    r"asistente virtual",
    r"Asiri",  # por si ya esta aplicado
]

print("DRY RUN — busqueda de patrones en system prompts\n")
for nm in SUB_AGENTS:
    n = next((x for x in wf["nodes"] if x["name"] == nm), None)
    if not n:
        print(f"[skip] {nm} no encontrado\n")
        continue
    sys_msg = n.get("parameters", {}).get("options", {}).get("systemMessage", "")
    if not sys_msg:
        print(f"[skip] {nm} sin systemMessage\n")
        continue
    print(f"=== {nm} (prompt: {len(sys_msg)} chars) ===")
    for pat in search_patterns:
        matches = list(re.finditer(pat, sys_msg))
        if matches:
            print(f"  pattern: {pat!r} — {len(matches)} match(es)")
            for m in matches:
                # Contexto: 60 chars antes y 60 despues
                start = max(0, m.start() - 60)
                end = min(len(sys_msg), m.end() + 60)
                ctx = sys_msg[start:end].replace("\n", " | ")
                print(f"    pos={m.start()} match={m.group()!r}")
                print(f"    ctx: ...{ctx}...")
        else:
            pass
    print()

print("\n=== Reemplazo PROPUESTO ===")
print("  'soy la asistente virtual de la Dra. Raquel'")
print("  -> 'soy Asiri, la asistente virtual de la Dra. Raquel'")
print()
print("  (mantengo 'asistente virtual' porque la Dra lo usa con pacientes;")
print("   agrego 'Asiri' como nombre propio antes)")
print()
print("Variantes consideradas (en orden de prioridad):")
print("  1. 'soy la asistente virtual de la Dra. Raquel' (canonico)")
print("  2. 'soy la asistente virtual de la Dra Raquel' (sin punto)")
print("  3. 'Soy la asistente virtual de la Dra. Raquel' (capitalizado)")
print()
print("CAMBIOS QUE SE HARIAN: solo los listados arriba. NO se toca otra ocurrencia.")
