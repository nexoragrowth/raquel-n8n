# -*- coding: utf-8 -*-
"""
snapshot_v6_live.py — baja el v6 vivo (O155MqHgOSaNZ9ye) por la API de n8n a
workflows/current/v6_LIVE.json (y opcionalmente a otra ruta). Imprime solo nombres de
nodos y conteos — nunca valores de credenciales.

Uso: python scripts/snapshot_v6_live.py [--out <ruta>]
"""
import argparse, json, os, sys, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
for p in [".env", "panel/.env.local"]:
    ep = Path(p)
    if ep.exists():
        for line in ep.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

BASE = (os.environ.get("N8N_API_BASE") or os.environ.get("N8N_BASE_URL") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""
V6 = "O155MqHgOSaNZ9ye"

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="workflows/current/v6_LIVE.json")
args = ap.parse_args()

req = urllib.request.Request(f"{BASE}/api/v1/workflows/{V6}", headers={"X-N8N-API-KEY": KEY})
with urllib.request.urlopen(req, timeout=30) as r:
    wf = json.loads(r.read().decode())

Path(args.out).parent.mkdir(parents=True, exist_ok=True)
Path(args.out).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
nodes = wf.get("nodes", [])
print(f"{wf.get('name')} | active={wf.get('active')} | updatedAt={wf.get('updatedAt')} | {len(nodes)} nodos -> {args.out}")
for n in nodes:
    print(f"  - {n.get('name')} | {n.get('type')}")
