# -*- coding: utf-8 -*-
"""
verify_production_workflows.py — Auditoría profunda de los 10 workflows de producción.
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

prod_workflows = [
    ("O155MqHgOSaNZ9ye", "Agente IA v6 (Main Bot)"),
    ("7RqTApkvVavRmq3R", "Recordatorio de Turno 48HS"),
    ("GuDQ9VmKWZvQnerV", "Sub-WF - Buscar Horarios Validado"),
    ("5cAWJxiWJ50hxEq3", "Sub-WF - CancelarReprogramar"),
    ("S5U6tSipzlgFHCkf", "Helper - Notify Grupo"),
    ("QsGBGkZdGu5gTdBf", "Daily Summary Recordatorios"),
    ("Yjl6kyLnALhIfbFX", "Health Check (Dentalink + Evolution)"),
    ("fosfga62zNaN0qrx", "Auto Reactivar Bot (1h sin humano)"),
    ("w7BBpZeEwZnpCX1q", "Human Takeover - Chatwoot"),
    ("xsXeHp7WLXnFQc3o", "Logger Conversaciones (Supabase)"),
]

print("=== REVISIÓN DE SALUD DE WORKFLOWS DE PRODUCCIÓN ===")
for wfid, name in prod_workflows:
    try:
        wf = json.loads(urllib.request.urlopen(urllib.request.Request(
            f"{BASE}/api/v1/workflows/{wfid}",
            headers={"X-N8N-API-KEY": KEY}
        )).read())
        
        is_active = wf.get("active", False)
        nodes = wf.get("nodes", [])
        disabled_nodes = [n["name"] for n in nodes if n.get("disabled")]
        old_evo_nodes = [n["name"] for n in nodes if n.get("type") == "n8n-nodes-evolution-api.evolutionApi"]
        
        status = "🟢 OK / ACTIVO" if is_active else "🔴 INACTIVO"
        print(f"\n📌 [{status}] Workflow: {name} ({wfid})")
        print(f"   - Total de nodos: {len(nodes)}")
        print(f"   - Nodos deshabilitados: {len(disabled_nodes)} {disabled_nodes if disabled_nodes else ''}")
        print(f"   - Nodos antiguos Evolution: {len(old_evo_nodes)} {old_evo_nodes if old_evo_nodes else '✓ Ninguno'}")
    except Exception as e:
        print(f"\n❌ Error leyendo workflow {name} ({wfid}): {e}")

