"""
Aplica identidad 'Asiri' a los 5 Sub-Agents del v6. Toca los 3 lugares exactos
de cada uno (R0, IDENTIFICACION, REGLA DE ORO) sin afectar nada mas.

NO toca el bullet "Querias agendar un turno?" en Sub-Agent General (bug Vivi
queda para fix separado).

Backup pre + verify post.
"""
import json, sys
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
(hist / f"v6_PRE_ASIRI_V2_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_ASIRI_V2_{ts}.json")

SUB_AGENTS = ["Sub-Agent Confirmar", "Sub-Agent Cancelar", "Sub-Agent Agendar",
              "Sub-Agent Urgencia", "Sub-Agent General"]

# 3 reemplazos exactos (literales — no regex)
REPLACEMENTS = [
    # R0
    ("Sos la asistente virtual de la Dra. Raquel Rodriguez",
     "Sos Asiri, la asistente virtual de la Dra. Raquel Rodriguez"),
    # IDENTIFICACION (saludo al paciente, dentro de comillas)
    ('"Hola, soy la asistente virtual de la Dra. Raquel."',
     '"Hola, soy Asiri, la asistente virtual de la Dra. Raquel."'),
    # REGLA DE ORO (refuerzo de identidad)
    ("VOS sos SIEMPRE la asistente virtual de la Dra. Raquel,",
     "VOS sos SIEMPRE Asiri, la asistente virtual de la Dra. Raquel,"),
]

total_changes = 0
for nm in SUB_AGENTS:
    n = next((x for x in wf["nodes"] if x["name"] == nm), None)
    if not n:
        print(f"  [skip] {nm} no encontrado")
        continue
    sys_msg = n["parameters"]["options"]["systemMessage"]
    new_msg = sys_msg
    changes_node = 0
    detail = []
    for old, new in REPLACEMENTS:
        # Idempotencia: si ya tiene "Asiri" en la posicion, skip
        if new in new_msg:
            detail.append(f"  - ya tiene Asiri: {old[:50]!r}")
            continue
        count = new_msg.count(old)
        if count == 0:
            detail.append(f"  - anchor NO encontrado: {old[:50]!r}")
            continue
        new_msg = new_msg.replace(old, new)
        changes_node += count
        detail.append(f"  - {count} reemplazo(s): {old[:50]!r}")
    if changes_node > 0:
        n["parameters"]["options"]["systemMessage"] = new_msg
        total_changes += changes_node
        print(f"\n[{nm}] {changes_node} cambios, prompt: {len(sys_msg)} -> {len(new_msg)} chars")
        for d in detail: print(d)
    else:
        print(f"\n[{nm}] sin cambios")
        for d in detail: print(d)

if total_changes == 0:
    print("\n!! cero cambios totales. abortando PUT.")
    sys.exit(0)

print(f"\n=== Total cambios: {total_changes} ===")

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

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_ASIRI_V2_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_ASIRI_V2_{ts}.json")
print(f"v6 active: {wf_post.get('active')}")

print("\n=== Verify (Asiri presente en cada Sub-Agent) ===")
for nm in SUB_AGENTS:
    n = next((x for x in wf_post["nodes"] if x["name"] == nm), None)
    if n:
        sys_msg = n["parameters"]["options"]["systemMessage"]
        count_asiri = sys_msg.count("Asiri")
        # Verificar bloques originales intactos
        has_r0 = "R0. AGENTE FUNCIONAL" in sys_msg
        has_anti = "ANTI-INJECTION" in sys_msg
        print(f"  {nm}: Asiri x{count_asiri}, R0={'OK' if has_r0 else 'MISSING'}, ANTI-INJECTION={'OK' if has_anti else 'MISSING'}")
