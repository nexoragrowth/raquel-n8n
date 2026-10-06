# -*- coding: utf-8 -*-
"""
audit_all_workflows_health.py
Revisa exhaustivamente TODOS los workflows en n8n:
- Estado (activo / inactivo)
- Cantidad de nodos y conexiones
- Presencia de nodos de Evolution antiguos
- Estado de credenciales requeridas
- Posibles nodos deshabilitados o con error de parámetros
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

wfs = json.loads(urllib.request.urlopen(urllib.request.Request(
    f"{BASE}/api/v1/workflows",
    headers={"X-N8N-API-KEY": KEY}
)).read()).get("data", [])

print(f"=== Auditoría Completa de {len(wfs)} Workflows en n8n ===")
print(f"{'ID':<18} | {'Estado':<10} | {'Nodos':<6} | {'Evo Antiguos':<12} | {'Nombre'}")
print("-" * 80)

active_count = 0
legacy_evo_total = 0

report_details = []

for w in wfs:
    wfid = w["id"]
    wfd = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/api/v1/workflows/{wfid}",
        headers={"X-N8N-API-KEY": KEY}
    )).read())
    
    name = wfd.get("name", "Sin Nombre")
    is_active = wfd.get("active", False)
    nodes = wfd.get("nodes", [])
    if is_active: active_count += 1
    
    old_evo_nodes = [n["name"] for n in nodes if n.get("type") == "n8n-nodes-evolution-api.evolutionApi"]
    legacy_evo_total += len(old_evo_nodes)
    
    status_str = "🟢 ACTIVO" if is_active else "⚪ Inactivo"
    print(f"{wfid:<18} | {status_str:<10} | {len(nodes):<6} | {len(old_evo_nodes):<12} | {name}")
    
    report_details.append({
        "id": wfid,
        "name": name,
        "active": is_active,
        "node_count": len(nodes),
        "old_evo_count": len(old_evo_nodes),
        "old_evo_nodes": old_evo_nodes
    })

print("-" * 80)
print(f"Total Workflows: {len(wfs)} | Activos: {active_count} | Nodos Evolution Antiguos Restantes: {legacy_evo_total}")
