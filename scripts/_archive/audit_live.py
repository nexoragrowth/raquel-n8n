"""
Auditoria del bot Dra. Raquel v6 — estado vivo + drift detection.

Pull workflow v6 vivo + executions ultimas 48h.
Guarda snapshot y emite reporte resumido.
"""
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require, env  # noqa: E402

N8N_BASE_URL = require("N8N_BASE_URL").rstrip("/")
N8N_API_KEY = require("N8N_API_KEY")
WF_V6 = require("N8N_WORKFLOW_V6_ID")
WF_REC = env("N8N_WORKFLOW_RECORDATORIOS_ID", "")
WF_REAC = env("N8N_WORKFLOW_AUTO_REACTIVAR_ID", "")
WF_HT = env("N8N_WORKFLOW_HUMAN_TAKEOVER_ID", "")

HEADERS = {"X-N8N-API-KEY": N8N_API_KEY, "Accept": "application/json"}
REPO = Path(__file__).resolve().parents[1]
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT_DIR = REPO / "workflows" / "current"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def get(url, **params):
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def pull_workflow(wf_id, label):
    url = f"{N8N_BASE_URL}/api/v1/workflows/{wf_id}"
    data = get(url)
    out = OUT_DIR / f"{label}_AUDIT_{TS}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data, out


def summarize_workflow(data):
    nodes = data.get("nodes", [])
    by_type = {}
    by_name = {}
    for n in nodes:
        t = n.get("type", "?")
        by_type[t] = by_type.get(t, 0) + 1
        by_name[n.get("name", "?")] = t
    return {
        "name": data.get("name"),
        "active": data.get("active"),
        "node_count": len(nodes),
        "by_type": by_type,
        "node_names": sorted(by_name.keys()),
        "updated_at": data.get("updatedAt"),
        "version_id": data.get("versionId"),
    }


def list_executions(wf_id, hours=48, limit=250):
    """Pull recent executions for a workflow."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    url = f"{N8N_BASE_URL}/api/v1/executions"
    out = []
    cursor = None
    while True:
        params = {"workflowId": wf_id, "limit": 250, "includeData": "false"}
        if cursor:
            params["cursor"] = cursor
        try:
            data = get(url, **params)
        except requests.HTTPError as e:
            return out, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        items = data.get("data", [])
        for it in items:
            started = it.get("startedAt") or it.get("createdAt")
            if started:
                try:
                    dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    if dt < cutoff:
                        return out, None
                except Exception:
                    pass
            out.append(it)
            if len(out) >= limit:
                return out, None
        cursor = data.get("nextCursor")
        if not cursor:
            break
    return out, None


def main():
    print(f"=== Auditoria v6 — {TS} ===\n")

    # --- Pull workflows ---
    targets = [(WF_V6, "v6"), (WF_REC, "recordatorios"), (WF_REAC, "auto_reactivar"), (WF_HT, "human_takeover")]
    summaries = {}
    paths = {}
    for wf_id, label in targets:
        if not wf_id:
            continue
        try:
            data, p = pull_workflow(wf_id, label)
            summaries[label] = summarize_workflow(data)
            paths[label] = p
            print(f"[OK] {label} ({wf_id}) -> {p.name}")
            print(f"     active={summaries[label]['active']} nodes={summaries[label]['node_count']} updated={summaries[label]['updated_at']}")
        except Exception as e:
            print(f"[ERR] {label} ({wf_id}): {e}")

    print("\n--- Tipos de nodos v6 ---")
    for t, c in sorted(summaries.get("v6", {}).get("by_type", {}).items(), key=lambda x: -x[1]):
        print(f"  {c:3d}  {t}")

    # --- Executions v6 last 48h ---
    print("\n--- Executions v6 ultimas 48h ---")
    execs, err = list_executions(WF_V6, hours=48, limit=500)
    if err:
        print(f"[ERR] {err}")
    else:
        total = len(execs)
        by_status = {}
        by_mode = {}
        errors = []
        for e in execs:
            st = e.get("status") or ("error" if e.get("stoppedAt") and e.get("finished") is False else "success")
            by_status[st] = by_status.get(st, 0) + 1
            mode = e.get("mode", "?")
            by_mode[mode] = by_mode.get(mode, 0) + 1
            if st in ("error", "crashed"):
                errors.append({
                    "id": e.get("id"),
                    "startedAt": e.get("startedAt"),
                    "mode": mode,
                    "finished": e.get("finished"),
                })
        print(f"Total: {total}")
        print(f"By status: {by_status}")
        print(f"By mode: {by_mode}")
        print(f"Errors/crashes: {len(errors)}")
        for er in errors[:15]:
            print(f"  - id={er['id']} at={er['startedAt']} mode={er['mode']}")

        # Save full list for downstream
        execs_path = REPO / "tests" / f"audit_executions_v6_{TS}.json"
        execs_path.write_text(json.dumps({"execs": execs, "errors": errors}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nFull executions saved -> {execs_path.relative_to(REPO)}")

    # --- Drift detection vs post-cutover snapshot ---
    print("\n--- Drift detection v6 (vs post-cutover snapshot) ---")
    candidates = sorted((REPO / "workflows" / "history").glob("v6_POST_*.json"))
    if not candidates:
        print("  (no historical snapshots found)")
    else:
        latest = candidates[-1]
        cutover = REPO / "workflows" / "history" / "v6_POST_CUTOVER_20260521_015027.json"
        ref = cutover if cutover.exists() else latest
        print(f"  Reference: {ref.name}")
        try:
            ref_data = json.loads(ref.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [ERR] reading ref: {e}")
            ref_data = None
        if ref_data:
            ref_names = {n["name"]: n for n in ref_data.get("nodes", [])}
            live_names = {n["name"]: n for n in summaries.get("v6") and (paths.get("v6") and json.loads(paths["v6"].read_text(encoding="utf-8")).get("nodes", []))}
            added = sorted(set(live_names) - set(ref_names))
            removed = sorted(set(ref_names) - set(live_names))
            print(f"  Nodes added since ref: {len(added)}")
            for n in added:
                print(f"    + {n}  [{live_names[n].get('type')}]")
            print(f"  Nodes removed since ref: {len(removed)}")
            for n in removed:
                print(f"    - {n}  [{ref_names[n].get('type')}]")
        # Latest post-anything
        print(f"\n  Latest POST_* snapshot: {latest.name}")

    print("\n=== DONE ===")


if __name__ == "__main__":
    main()
