# inspect_node_details.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

nodes_dict = {n['name']: n for n in wf['nodes']}

targets = [
    'Existe paciente?',
    'Chatwoot - Buscar Conversacion',
    'Verificar Label Humano',
    'Bot Activo?',
    'Banlist Validator',
    'Re-check Humano',
    'Hay humano ahora?',
    'Humano aparecio?',
    'Aviso humano tomo chat',
    'Delay Humano',
    'Gate Humano Final',
    'Postgres - Save fromMe',
    'CW Search Contact',
    'CW Extract Conv',
    'CW Get Conversations',
    'CW Pick Conv',
    'CW Set Label humano',
    'Media: Preparar (staff)'
]

for name in targets:
    if name in nodes_dict:
        n = nodes_dict[name]
        print(f"==================================================")
        print(f"NODE: {name} ({n['type']})")
        print(json.dumps(n.get('parameters', {}), indent=2))
