"""Check ultima execution del workflow audit creado."""
from __future__ import annotations
import os, sys, io, json, time
import requests
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

WID = "vmku7s93ksPNcQ5g"

QUERY_NAMES = [
    "Q1_tokens_intent_puros",
    "Q2_outputs_prohibidos",
    "Q3_no_reply_count",
    "Q4_filas_por_tipo",
    "Q5_top_contents_repetidos",
    "Q6_total_filas",
    "Q7_samples_no_reply",
    "Q8_errores_tecnicos_extra",
    "Q9_tool_call_traces",
]

ex = requests.get(f"{BASE}/api/v1/executions?workflowId={WID}&limit=3", headers=H, timeout=30).json()
print(f"executions found: {len(ex.get('data', []))}")
for e in ex.get("data", []):
    print(f"  id={e['id']} status={e.get('status')} stoppedAt={e.get('stoppedAt')}")

if not ex.get("data"):
    sys.exit(0)

exec_id = ex["data"][0]["id"]
print(f"\n[*] usando exec_id={exec_id}\n")

full = requests.get(f"{BASE}/api/v1/executions/{exec_id}?includeData=true", headers=H, timeout=120).json()
runs = full.get("data", {}).get("resultData", {}).get("runData", {})
print(f"runs keys: {list(runs.keys())}\n")

results = {}
for name in QUERY_NAMES:
    if name not in runs:
        print(f"### {name}: NO EJECUTADO\n")
        results[name] = None
        continue
    out = runs[name][0].get("data", {}).get("main", [[]])[0]
    items = [it.get("json", {}) for it in out]
    results[name] = items
    print(f"### {name}  ({len(items)} rows)")
    for it in items[:30]:
        print("  " + json.dumps(it, ensure_ascii=False)[:700])
    print()

dump_path = ROOT / "audit_basura_chat_histories.json"
with open(dump_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print(f"[done] dump -> {dump_path}")
