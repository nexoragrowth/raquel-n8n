"""Dump full content of guardrail/critical nodes + exec error details to file (avoids stdout encoding)."""
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
TS = datetime.now().strftime("%Y%m%d_%H%M%S")

audits = sorted((REPO / "workflows" / "current").glob("v6_AUDIT_*.json"))
LIVE = audits[-1]
wf = json.loads(LIVE.read_text(encoding="utf-8"))
nodes = wf.get("nodes", [])

GUARDRAIL_TARGETS = [
    "Filtrar duplicados y basura",
    "Pre-filtro Cierre",
    "Banlist Validator",
    "Kill-switch Check",
    "Es comando admin?",
    "Es fromMe?",
    "Webhook Validator",
    "Descartar [NO_REPLY]",
    "Set NO_REPLY",
    "Build fromMe AI memory",
    "Clear Old Memory",
    "Existe paciente?",
    "Get Paciente Context",
    "Preparar Mensaje Final",
]

out_file = REPO / "tests" / f"audit_guardrails_{TS}.md"
lines = [f"# Audit guardrails — {TS}", f"Live workflow: {LIVE.name}\n"]

by_name = {n["name"]: n for n in nodes}
for name in GUARDRAIL_TARGETS:
    n = by_name.get(name)
    if not n:
        lines.append(f"## MISSING: {name}\n")
        continue
    lines.append(f"## {name}  [{n.get('type')}]")
    p = n.get("parameters", {})
    lines.append("```json")
    try:
        lines.append(json.dumps(p, ensure_ascii=False, indent=2))
    except Exception as e:
        lines.append(f"<<dump error: {e}>>")
    lines.append("```\n")

# Also: dump all CODE nodes (jsCode) — anywhere transformation happens
lines.append("# All code nodes (jsCode) — for full inspection\n")
for n in nodes:
    if n.get("type") == "n8n-nodes-base.code":
        p = n.get("parameters", {})
        code = p.get("jsCode") or p.get("functionCode") or ""
        lines.append(f"## CODE: {n['name']}")
        lines.append("```javascript")
        lines.append(code)
        lines.append("```\n")

# All IF nodes (conditions)
lines.append("# All IF nodes — conditions\n")
for n in nodes:
    if n.get("type") == "n8n-nodes-base.if":
        p = n.get("parameters", {})
        lines.append(f"## IF: {n['name']}")
        lines.append("```json")
        lines.append(json.dumps(p, ensure_ascii=False, indent=2))
        lines.append("```\n")

# Switch nodes
lines.append("# All SWITCH nodes\n")
for n in nodes:
    if n.get("type") == "n8n-nodes-base.switch":
        p = n.get("parameters", {})
        lines.append(f"## SWITCH: {n['name']}")
        lines.append("```json")
        lines.append(json.dumps(p, ensure_ascii=False, indent=2))
        lines.append("```\n")

out_file.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {out_file.relative_to(REPO)}  ({out_file.stat().st_size} bytes)")

# --- Exec errors ---
EXEC_IDS = ["24985", "24975", "24958"]
err_out = REPO / "tests" / f"audit_exec_errors_{TS}.md"
elines = [f"# Audit exec errors — {TS}\n"]
for eid in EXEC_IDS:
    url = f"{N8N_BASE_URL}/api/v1/executions/{eid}?includeData=true"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        elines.append(f"## exec {eid}: HTTP ERR {e}\n")
        continue
    rdata = data.get("data", {})
    result = rdata.get("resultData", {})
    err = result.get("error") or {}
    elines.append(f"## exec {eid}")
    elines.append(f"- status: {data.get('status')}")
    elines.append(f"- startedAt: {data.get('startedAt')}")
    elines.append(f"- stoppedAt: {data.get('stoppedAt')}")
    elines.append(f"- lastNodeExecuted: {result.get('lastNodeExecuted')}")
    node = err.get("node") if isinstance(err.get("node"), dict) else None
    elines.append(f"- error node: {node.get('name') if node else err.get('node')}")
    elines.append(f"- error message: {err.get('message')}")
    elines.append(f"- error description: {err.get('description')}")
    elines.append("- error stack (first 1200):")
    elines.append("```")
    elines.append(str(err.get("stack") or "")[:1200])
    elines.append("```")
    # Dump first input data of node that errored — to see WHAT triggered it
    run_data = result.get("runData", {})
    if node and node.get("name") in run_data:
        runs = run_data[node["name"]]
        if runs:
            last_run = runs[-1]
            elines.append(f"- error node lastRun keys: {list(last_run.keys())[:10]}")
            err_obj = last_run.get("error") or {}
            elines.append(f"- error node msg: {err_obj.get('message')}")
    # Save full
    full = REPO / "tests" / f"exec_error_{eid}.json"
    full.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    elines.append(f"- full -> tests/{full.name}\n")

err_out.write_text("\n".join(elines), encoding="utf-8")
print(f"Wrote {err_out.relative_to(REPO)}")
