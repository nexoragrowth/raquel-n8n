"""
Aplica identidad 'Asiri' a todos los Sub-Agents del v6.

Cambio:
  "soy la asistente virtual de la Dra. Raquel" -> "soy Asiri, la asistente virtual de la Dra. Raquel"

Tambien busca variantes menos comunes:
  "Asistente virtual de la Dra. Raquel" -> "Asiri, asistente virtual de la Dra. Raquel"
  "la asistente virtual de la Dra Raquel" (sin punto) idem

Solo modifica system prompts de Sub-Agents. Cero toque a estructura.
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
(hist / f"v6_PRE_ASIRI_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_ASIRI_{ts}.json")

# Sub-agents a modificar
SUB_AGENTS = [
    "Sub-Agent Confirmar",
    "Sub-Agent Cancelar",
    "Sub-Agent Agendar",
    "Sub-Agent Urgencia",
    "Sub-Agent General",
]

# Reglas de reemplazo en orden (la primera que matchea cada anchor)
REPLACEMENTS = [
    # Casos canonicos
    ("soy la asistente virtual de la Dra. Raquel",
     "soy Asiri, la asistente virtual de la Dra. Raquel"),
    ("soy la asistente virtual de la Dra Raquel",  # sin punto
     "soy Asiri, la asistente virtual de la Dra Raquel"),
    # Variantes capitalizadas / parciales
    ("Soy la asistente virtual de la Dra. Raquel",
     "Soy Asiri, la asistente virtual de la Dra. Raquel"),
]

changes_total = 0
nodes_changed = []

for nm in SUB_AGENTS:
    n = next((x for x in wf["nodes"] if x["name"] == nm), None)
    if not n:
        print(f"  [skip] {nm} no encontrado")
        continue
    sys_msg = n.get("parameters", {}).get("options", {}).get("systemMessage", "")
    if not sys_msg:
        print(f"  [skip] {nm}: sin systemMessage")
        continue
    new_msg = sys_msg
    local_changes = 0
    for old, new in REPLACEMENTS:
        # Skip si ya tiene Asiri (idempotencia)
        if "Asiri" in new_msg and old in new_msg:
            # Si la nueva version ya esta presente, no aplicar otra vez
            if new in new_msg:
                continue
        count_before = new_msg.count(old)
        if count_before == 0:
            continue
        new_msg = new_msg.replace(old, new)
        local_changes += count_before
    if local_changes > 0:
        n["parameters"]["options"]["systemMessage"] = new_msg
        nodes_changed.append((nm, local_changes, len(sys_msg), len(new_msg)))
        changes_total += local_changes
        print(f"  [{nm}] {local_changes} reemplazo(s), prompt: {len(sys_msg)} -> {len(new_msg)} chars")
    else:
        print(f"  [{nm}] sin cambios (anchor no encontrado o ya tiene Asiri)")

if changes_total == 0:
    print("\n!! Cero cambios totales. Abortando PUT.")
    sys.exit(0)

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
(hist / f"v6_POST_ASIRI_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_ASIRI_{ts}.json")
print(f"v6 active: {wf_post.get('active')}")

# Verify Asiri esta en los prompts
print(f"\nVerify post-PUT:")
for nm in SUB_AGENTS:
    n = next((x for x in wf_post["nodes"] if x["name"] == nm), None)
    if n:
        sys_msg = n.get("parameters", {}).get("options", {}).get("systemMessage", "")
        has_asiri = "Asiri" in sys_msg
        old_count = sys_msg.count("soy la asistente virtual de la Dra")
        print(f"  {nm}: has_asiri={has_asiri}, old_anchors_remaining={old_count}")
