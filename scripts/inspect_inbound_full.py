# inspect_inbound_full.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

# Buscar que llega a "Existe paciente?" y que sale de "Bot Activo?"
conns = wf.get('connections', {})
for src, targets in conns.items():
    for otype, clist in targets.items():
        for group in clist:
            for c in group:
                if c['node'] in ['Existe paciente?', 'Bot Activo?', 'Verificar Label Humano']:
                    print(f"{src} -> {c['node']} ({otype})")
                if src in ['Existe paciente?', 'Bot Activo?', 'Verificar Label Humano']:
                    print(f"{src} -> {c['node']} ({otype})")
