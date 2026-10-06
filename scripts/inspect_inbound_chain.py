# inspect_inbound_chain.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

nodes_dict = {n['name']: n for n in wf['nodes']}

inbound_nodes = [
    'Existe paciente?',
    'Chatwoot - Buscar Conversacion',
    'Verificar Label Humano',
    'Bot Activo?',
    'Humano Atendiendo (no hacer nada)',
    'Re-check Humano',
    'Hay humano ahora?',
    'Humano aparecio?',
    'Aviso humano tomo chat',
    'Delay Humano',
    'Gate Humano Final'
]

for name in inbound_nodes:
    if name in nodes_dict:
        n = nodes_dict[name]
        print(f"=== NODE: {name} ({n['type']}) ===")
        print("Parameters:")
        print(json.dumps(n.get('parameters', {}), indent=2))
        print("-" * 50)
