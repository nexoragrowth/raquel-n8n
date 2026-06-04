"""
Build system messages for the 5 sub-agents of v6 from partials in prompts/v6_partials/.

Each sub-agent has a RECIPE: list of partial filenames in order. The script
concatenates them and produces the final system message.

Modes:
  --check   : Compare assembled with current live v6. Report diffs.
  --apply   : PUT to v6 only if --check passes (or --force).
  --diff    : Show full diff for one agent (--agent Confirmar)

Normalization done (consolidated drift across agents):
  - MAYUSCULAS: Urgencia normalized to the longer V1 (4 of 5 agents).
  - SALIDA: Urgencia loses an extra `---\\n` trailing separator.
  - REGLA CRITICA: Cancelar gains the full Chatwoot/Iri mention (V1).
  - R0: General keeps its shorter version (deliberate — has SALUDOS specific).

Workflow: v6 main (O155MqHgOSaNZ9ye).
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
WF_ID = "O155MqHgOSaNZ9ye"
HEADERS = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

PARTIALS = ROOT / "prompts" / "v6_partials"


# === RECIPES: each list is concatenated with "\n\n" between partials ===
RECIPES = {
    "Sub-Agent Confirmar": [
        "r0_full.md",
        "header_common.md",
        "confirmar_paso0_recordatorios.md",
        "confirmar_funcion.md",
        "confirmar_tools.md",
        "regla_critica_escalacion.md",
        "confirmar_idempotencia.md",
        "memoria_historica.md",
        "paciente_context_runtime.md",
    ],
    "Sub-Agent Cancelar": [
        "r0_full.md",
        "header_common.md",
        "cancelar_paso0_recordatorios.md",
        "cancelar_funcion.md",
        "cancelar_tools.md",
        "regla_critica_escalacion.md",
        "memoria_historica.md",
        "paciente_context_runtime.md",
    ],
    "Sub-Agent Agendar": [
        "r0_full.md",
        "header_common.md",
        "agendar_funcion.md",
        "agendar_tools.md",
        "agendar_anti_alucinacion.md",
        "regla_critica_escalacion.md",
        "memoria_historica.md",
        "paciente_context_runtime.md",
    ],
    "Sub-Agent Urgencia": [
        "r0_full.md",
        "header_common.md",
        "urgencia_funcion.md",
        "regla_critica_escalacion.md",
        "paciente_context_runtime.md",
    ],
    "Sub-Agent General": [
        "r0_general.md",
        "saludos_solos.md",
        "confirmacion_pago.md",
        "header_common.md",
        "general_funcion.md",
        "general_preguntas_turnos.md",
        "general_preguntas_capacidad.md",
        "general_orden_decision.md",
        "regla_critica_escalacion.md",
        "memoria_historica.md",
        "paciente_context_runtime.md",
    ],
}


def read_partial(name: str) -> str:
    p = PARTIALS / name
    if not p.exists():
        raise SystemExit(f"partial missing: {name}")
    return p.read_text(encoding="utf-8").rstrip()


def assemble(agent: str) -> str:
    parts = [read_partial(n) for n in RECIPES[agent]]
    # FIX 2026-06-04: TODOS los sub-agents necesitan el prefijo "=" para que n8n
    # evalúe las expresiones {{ }} del systemMessage (sino llegan literales al LLM).
    body = "\n\n".join(parts)
    return "=" + body


def get_live() -> dict:
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def find_node(wf: dict, name: str) -> dict:
    for n in wf["nodes"]:
        if n["name"] == name:
            return n
    raise SystemExit(f"Node {name!r} not found in workflow")


def put_workflow(wf: dict) -> dict:
    allowed_settings = {
        "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
        "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
        "executionOrder", "callerPolicy", "callerIds",
    }
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed_settings}
    body = {
        "name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
        "settings": settings, "staticData": wf.get("staticData"),
    }
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=HEADERS, json=body, timeout=30)
    if not r.ok:
        print("PUT failed:", r.status_code, r.text[:500], file=sys.stderr)
        r.raise_for_status()
    return r.json()


def check(agent_filter: str | None = None, show_diff: bool = False) -> dict:
    """Returns {agent: {'live_len', 'built_len', 'identical', 'diff_chars'}}."""
    wf = get_live()
    results = {}
    for agent, recipe in RECIPES.items():
        if agent_filter and agent_filter not in agent:
            continue
        live = find_node(wf, agent)["parameters"]["options"]["systemMessage"]
        built = assemble(agent)
        identical = (live == built)
        results[agent] = {
            "live_len": len(live),
            "built_len": len(built),
            "identical": identical,
            "delta": len(built) - len(live),
        }
        status = "OK identical" if identical else f"DIFFERS ({len(built) - len(live):+d} chars)"
        print(f"  {agent:<25s} live={len(live):>6d} built={len(built):>6d}  {status}")
        if show_diff and not identical:
            diff = difflib.unified_diff(
                live.splitlines(keepends=True), built.splitlines(keepends=True),
                fromfile="LIVE", tofile="BUILT", n=2,
            )
            print("".join(diff))
    return results


def apply(force: bool = False) -> None:
    wf = get_live()
    # Backup
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "workflows" / "history" / f"v6_PRE_BUILD_PROMPTS_PARTIAL_SYSTEM_{ts}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup -> {backup}")

    # Check first
    print("\n[check] comparing assembled vs live...")
    results = check()
    fails = [a for a, r in results.items() if not r["identical"]]

    if fails and not force:
        print(f"\n[abort] {len(fails)} agent(s) differ. Use --force to apply anyway.")
        sys.exit(2)

    # Apply
    print("\n[apply] writing assembled to v6 nodes...")
    for agent in RECIPES.keys():
        node = find_node(wf, agent)
        node["parameters"]["options"]["systemMessage"] = assemble(agent)

    res = put_workflow(wf)
    print(f"PUT OK updatedAt={res.get('updatedAt')}")

    # Verify
    wf2 = get_live()
    all_ok = True
    for agent in RECIPES.keys():
        live = find_node(wf2, agent)["parameters"]["options"]["systemMessage"]
        built = assemble(agent)
        if live != built:
            print(f"[verify] FAIL {agent}")
            all_ok = False
        else:
            print(f"[verify] OK   {agent}")
    if not all_ok:
        sys.exit(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--diff", action="store_true", help="Show full diff (with --check)")
    ap.add_argument("--agent", default=None, help="Filter to one agent (substring match)")
    args = ap.parse_args()

    if args.apply:
        apply(force=args.force)
    elif args.check or args.diff:
        check(agent_filter=args.agent, show_diff=args.diff)
    else:
        # Just print built sizes
        for agent in RECIPES.keys():
            built = assemble(agent)
            print(f"  {agent:<25s} built={len(built):>6d} chars")


if __name__ == "__main__":
    main()
