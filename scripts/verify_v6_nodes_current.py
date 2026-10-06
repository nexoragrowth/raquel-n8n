# -*- coding: utf-8 -*-
"""
verify_v6_nodes_current.py — Verifica el tipo de nodo actual de 'HTTP Send Admin Confirm' y 'Evolution API - Enviar Mensaje' en v6.
"""
import sys, os, urllib.request, json
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

wf = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye",
    headers={"X-N8N-API-KEY": KEY}
)).read())

for n in wf.get("nodes", []):
    if n["name"] in ["HTTP Send Admin Confirm", "Evolution API - Enviar Mensaje", "Evolution - Typing"]:
        print(f"Node '{n['name']}':")
        print(f"  Type: {n['type']}")
        print(f"  Parameters: {json.dumps(n.get('parameters', {}), ensure_ascii=False)[:250]}")
        print()
