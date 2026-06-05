"""Reporte Banlist Shadow Agent vs Regex.

Trae las ultimas N ejecuciones del v6 main que activaron el Banlist Shadow,
extrae las decisiones del agent (nano) y del regex, calcula agreement
y muestra casos de desacuerdo para revision.

Uso:
  python scripts/report_banlist_shadow.py            # ultimas 100 execs
  python scripts/report_banlist_shadow.py --limit 300
  python scripts/report_banlist_shadow.py --dump shadow_log.jsonl   # acumular en archivo local
"""
from __future__ import annotations
import argparse, json, os, sys, io
from collections import Counter
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
WF_ID = "O155MqHgOSaNZ9ye"


def fetch_executions(limit: int) -> list:
    rows = []
    cursor = None
    while len(rows) < limit:
        params = {"workflowId": WF_ID, "limit": min(100, limit - len(rows))}
        if cursor: params["cursor"] = cursor
        r = requests.get(f"{BASE}/api/v1/executions", headers=H, params=params, timeout=60).json()
        execs = r.get("data", [])
        if not execs: break
        rows.extend(execs)
        cursor = r.get("nextCursor")
        if not cursor: break
    return rows[:limit]


def extract_shadow(eid: str) -> dict | None:
    full = requests.get(f"{BASE}/api/v1/executions/{eid}?includeData=true", headers=H, timeout=30).json()
    runs = full.get("data", {}).get("resultData", {}).get("runData", {})
    if "Banlist Shadow - Log" not in runs: return None
    log_out = runs["Banlist Shadow - Log"][0].get("data", {}).get("main", [[]])[0]
    if not log_out: return None
    j = log_out[0].get("json", {})
    started = full.get("data", {}).get("startedAt", "")
    return {
        "exec_id": eid,
        "started_at": started,
        "phone": j.get("shadow_phone", "?"),
        "paciente_msg": (j.get("shadow_paciente_msg", "") or "")[:200],
        "bot_output": (j.get("shadow_bot_output", "") or "")[:300],
        "regex_decision": j.get("shadow_regex_decision", "?"),
        "agent_decision": j.get("shadow_agent_decision", "?"),
        "agent_razon": (j.get("shadow_agent_razon", "") or "")[:200],
        "agent_reemplazo": (j.get("shadow_agent_reemplazo", "") or "")[:200],
        "agreement": j.get("shadow_agreement", False),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--dump", default=None, help="Append rows a este archivo .jsonl (acumula entre runs)")
    ap.add_argument("--verbose", action="store_true", help="Mostrar TODOS los casos, no solo disagreement")
    args = ap.parse_args()

    print(f"Trayendo ultimas {args.limit} ejecuciones del v6 main...")
    execs = fetch_executions(args.limit)
    print(f"OK, {len(execs)} ejecuciones encontradas\n")

    rows = []
    for e in execs:
        try:
            row = extract_shadow(e["id"])
            if row: rows.append(row)
        except Exception as ex:
            print(f"  err exec={e['id']}: {ex}", file=sys.stderr)

    print(f"Con Banlist Shadow corrido: {len(rows)} ejecuciones\n")

    if not rows:
        print("(no hay data de shadow todavia. probablemente porque Banlist Shadow se activo recien)")
        return

    # === Tabla resumen ===
    matrix = Counter()
    for r in rows:
        key = (r["regex_decision"], r["agent_decision"])
        matrix[key] += 1
    total = len(rows)
    agree = sum(1 for r in rows if r["agreement"])
    print(f"{'='*60}")
    print(f"AGREEMENT: {agree}/{total} ({100*agree/total:.1f}%)")
    print(f"{'='*60}\n")
    print("Matriz regex x agent:")
    header = "regex / agent"
    print(f"  {header:<20s} {'ALLOW':>8s} {'BLOCK':>8s} {'OTHER':>8s}")
    for rd in ("ALLOW", "BLOCK"):
        row_str = f"  {rd:<20s}"
        for ad in ("ALLOW", "BLOCK"):
            row_str += f" {matrix.get((rd, ad), 0):>8d}"
        other = sum(v for (a, b), v in matrix.items() if a == rd and b not in ("ALLOW", "BLOCK"))
        row_str += f" {other:>8d}"
        print(row_str)
    print()

    # === Casos de desacuerdo ===
    disagree = [r for r in rows if not r["agreement"]]
    if disagree:
        print(f"\nDESACUERDOS ({len(disagree)}):")
        print("="*60)
        for r in disagree[:30]:
            print(f"\nexec={r['exec_id']} {r['started_at']}")
            print(f"  phone:        {r['phone']}")
            print(f"  paciente:     {r['paciente_msg'][:120]!r}")
            print(f"  bot_output:   {r['bot_output'][:150]!r}")
            print(f"  regex:        {r['regex_decision']}")
            print(f"  agent:        {r['agent_decision']} — {r['agent_razon'][:140]}")
            if r.get("agent_reemplazo"): print(f"  reemplazo:    {r['agent_reemplazo'][:140]}")
    elif args.verbose:
        print(f"\nTodos los casos (verbose):")
        for r in rows[:20]:
            print(f"  {r['started_at'][11:19]} {r['phone'][-10:]}  regex={r['regex_decision']:<5s} agent={r['agent_decision']:<5s}  msg={r['paciente_msg'][:60]!r}")
    else:
        print("Sin desacuerdos en esta tanda (regex y agent coincidieron en todos los casos).")

    # === Dump opcional ===
    if args.dump:
        with open(args.dump, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\n[dump] appended {len(rows)} rows a {args.dump}")


if __name__ == "__main__":
    main()
