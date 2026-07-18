"""
Auto-layout del workflow v6 usando dagre (la misma libreria que usa n8n).

Pipeline:
  1. GET workflow
  2. Pasar JSON a scripts/layout_dagre.js via stdin
  3. Recibir {positions, stickyBoxes}
  4. Aplicar y PUT

Uso:
  N8N_API_KEY=... python scripts/apply_layout_v6_dagre.py [--dry-run]
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

WF_ID = "O155MqHgOSaNZ9ye"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
API_KEY = os.environ.get("N8N_API_KEY")
DRY_RUN = "--dry-run" in sys.argv

if not API_KEY:
    print("ERROR: set N8N_API_KEY env var")
    sys.exit(1)

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow",
    "timezone", "executionOrder", "callerPolicy", "callerIds",
}


def http(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        headers={
            "X-N8N-API-KEY": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


def main():
    print(f"GET workflow {WF_ID}...")
    status, wf = http("GET", f"/workflows/{WF_ID}")
    print(f"  status={status} active={wf['active']} nodes={len(wf['nodes'])}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_DAGRE_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    print("Running dagre layout (node scripts/layout_dagre.js)...")
    proc = subprocess.run(
        ["node", "scripts/layout_dagre.js"],
        input=json.dumps(wf).encode(),
        capture_output=True,
        check=True,
    )
    layout = json.loads(proc.stdout.decode())
    positions = layout["positions"]
    sticky_boxes = layout["stickyBoxes"]
    print(f"  computed positions for {len(positions)} nodes")
    print(f"  computed boxes for {sum(1 for v in sticky_boxes.values() if v)} stickies")

    moved = 0
    for n in wf["nodes"]:
        name = n["name"]
        if name in positions:
            new = positions[name]
            if n["position"] != new:
                n["position"] = new
                moved += 1
    # stickies untouched: dejamos el layout dagre puro, sin reabrazar grupos
    print(f"  moved {moved} nodes (stickies untouched)")

    if DRY_RUN:
        out = f"workflows/history/v6_LAYOUT_DAGRE_DRY_{ts}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"DRY RUN -> {out}")
        return

    settings = {k: v for k, v in wf.get("settings", {}).items() if k in ALLOWED_SETTINGS}
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": settings,
        "staticData": wf.get("staticData"),
    }
    print(f"PUT workflow {WF_ID}...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  status={status}")

    status2, wf2 = http("GET", f"/workflows/{WF_ID}")
    post_path = f"workflows/history/v6_POST_DAGRE_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  active={wf2['active']} post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
