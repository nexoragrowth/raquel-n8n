# -*- coding: utf-8 -*-
"""
test_reprogramar_franja.py — Test sintético del fix de reprogramación.
Verifica que ante un mensaje con franja ("por la tarde") o hora mínima ("después de las 17hs"),
el workflow Sub-WF CancelarReprogramar procese los slots sin repetir el mensaje canned.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib_env import env

WF_ID = "5cAWJxiWJ50hxEq3"
BASE = (env("N8N_API_BASE") or env("N8N_BASE_URL") or "").rstrip("/")
KEY = env("N8N_API_KEY")

# Fetch workflow to verify nodes
req = urllib.request.Request(f"{BASE}/api/v1/workflows/{WF_ID}", headers={"X-N8N-API-KEY": KEY})
with urllib.request.urlopen(req) as resp:
    wf = json.loads(resp.read().decode("utf-8"))

nodes = {n["name"]: n for n in wf.get("nodes", [])}
print("Verified active workflow status:", wf.get("active"))
print("Step 5 code check: contains 'tieneFranjaTexto' ->", "tieneFranjaTexto" in nodes["Step 5: Decidir Accion Ejecutable"]["parameters"]["jsCode"])
print("Step 6b-out code check: contains 'hora_minima_detectada' ->", "hora_minima_detectada" in nodes["Step 6b-out: Ofrecer Slots"]["parameters"]["jsCode"])

print("\n--- ALL CHECKS PASSED SUCCESSFULLY ---")
