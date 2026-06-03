"""
Auditoria profunda — extrae:
- detalle de executions con error
- nodos criticos del v6 vivo (kill-switch, fromMe, banlist, prefiltro, send+typing)
- prompts vigentes de cada agente
- guardrails post-output
"""
import json
import sys
from pathlib import Path
from datetime import datetime

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require  # noqa: E402

N8N_BASE_URL = require("N8N_BASE_URL").rstrip("/")
N8N_API_KEY = require("N8N_API_KEY")
HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Accept": "application/json"}

REPO = Path(__file__).resolve().parents[1]
EXEC_IDS = sys.argv[1:] if len(sys.argv) > 1 else []

# Find latest v6 AUDIT snapshot
audits = sorted((REPO / "workflows" / "current").glob("v6_AUDIT_*.json"))
if not audits:
    sys.exit("No v6_AUDIT_*.json found - run audit_live.py first")
LIVE = audits[-1]
print(f"Live workflow: {LIVE.name}\n")
wf = json.loads(LIVE.read_text(encoding="utf-8"))
nodes = wf.get("nodes", [])
by_name = {n["name"]: n for n in nodes}


def short(s, n=400):
    if not s:
        return ""
    s = str(s).replace("\r", "")
    if len(s) <= n:
        return s
    return s[:n] + f"... [+{len(s)-n} chars]"


# --- 1. Critical nodes presence ---
print("=" * 70)
print("1. NODOS CRITICOS (presencia)")
print("=" * 70)

critical_keywords = {
    "Kill-switch / admin /bot": ["/bot", "kill", "admin", "/bot off"],
    "fromMe filter": ["fromMe", "fromme", "from_me"],
    "Pre-filtro / NO_REPLY": ["pre-filtro", "prefiltro", "no_reply", "no-reply"],
    "Banlist / regex post-output": ["banlist", "ban list", "venite", "pos-output", "post-output", "post_output"],
    "Send (Evolution)": [],
    "Typing": ["typing", "presence"],
    "Webhook entry": ["webhook"],
    "Broadcast filter": ["broadcast"],
    "Silence flag": ["silence", "silenc"],
    "Memoria Postgres": ["postgres", "memory"],
    "Logger conversaciones": ["log", "conversacion"],
    "Get Paciente Context": ["paciente"],
}

for label, kws in critical_keywords.items():
    hits = []
    for n in nodes:
        nm = n["name"].lower()
        if any(k.lower() in nm for k in kws):
            hits.append(n["name"])
    if not hits and label == "Send (Evolution)":
        # Use type
        hits = [n["name"] for n in nodes if "evolution" in n.get("type", "").lower()]
    print(f"  {label}: {len(hits)}")
    for h in hits[:8]:
        print(f"    - {h}")

# --- 2. Extract prompts from agents ---
print("\n" + "=" * 70)
print("2. PROMPTS DE AGENTES (system messages + descriptions)")
print("=" * 70)
agent_nodes = [n for n in nodes if n.get("type") == "@n8n/n8n-nodes-langchain.agent"]
for n in agent_nodes:
    name = n["name"]
    params = n.get("parameters", {})
    options = params.get("options", {}) or {}
    sysmsg = options.get("systemMessage") or params.get("systemMessage") or params.get("text", "")
    print(f"\n--- AGENT: {name} ---")
    print(f"  type: {n.get('type')}")
    print(f"  promptType: {params.get('promptType')}")
    print(f"  text (first 200): {short(params.get('text'), 200)}")
    print(f"  systemMessage length: {len(sysmsg or '')} chars")
    if sysmsg:
        out = REPO / "prompts" / "v6_actuales" / f"{name.replace('/', '_').replace(' ', '_')}_LIVE_{datetime.now().strftime('%Y%m%d')}.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(sysmsg, encoding="utf-8")
        print(f"  -> dumped to {out.relative_to(REPO)}")

# --- 3. Banlist / guardrail nodes content ---
print("\n" + "=" * 70)
print("3. NODOS GUARDRAIL (banlist, pre-filtro, fromMe, kill-switch)")
print("=" * 70)
suspects = []
for n in nodes:
    nm = n["name"].lower()
    if any(k in nm for k in ("ban", "filtr", "kill", "pre-filt", "prefiltro", "fromme", "no_reply", "broadcast", "silence", "post-output", "guardrail")):
        suspects.append(n)

for n in suspects:
    print(f"\n--- {n['name']}  [{n.get('type')}] ---")
    p = n.get("parameters", {})
    # Try common content fields
    for fld in ("jsCode", "functionCode", "value1", "rules", "conditions", "values", "command", "query"):
        if fld in p:
            print(f"  {fld}: {short(json.dumps(p[fld], ensure_ascii=False), 500)}")
    if "operation" in p:
        print(f"  operation: {p['operation']}")

# --- 4. Pull execution data for errors ---
print("\n" + "=" * 70)
print("4. EXECUTIONS CON ERROR (detalle)")
print("=" * 70)
if not EXEC_IDS:
    print("  (no exec IDs passed — re-run with: python audit_deep.py <id1> <id2> ...)")
else:
    for eid in EXEC_IDS:
        url = f"{N8N_BASE_URL}/api/v1/executions/{eid}?includeData=true"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  [ERR] {eid}: {e}")
            continue
        print(f"\n--- exec {eid} ---")
        print(f"  status: {data.get('status')}")
        print(f"  startedAt: {data.get('startedAt')}")
        print(f"  stoppedAt: {data.get('stoppedAt')}")
        rdata = data.get("data", {})
        result = rdata.get("resultData", {})
        last = result.get("lastNodeExecuted")
        print(f"  lastNodeExecuted: {last}")
        err = result.get("error")
        if err:
            print(f"  ERROR message: {short(err.get('message'), 600)}")
            print(f"  ERROR node: {err.get('node', {}).get('name') if isinstance(err.get('node'), dict) else err.get('node')}")
            print(f"  ERROR description: {short(err.get('description'), 400)}")
            print(f"  ERROR stack: {short(err.get('stack'), 400)}")
        # Save full
        out = REPO / "tests" / f"exec_error_{eid}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  -> saved {out.relative_to(REPO)}")

print("\n=== DONE ===")
