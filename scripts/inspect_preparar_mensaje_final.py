# inspect_preparar_mensaje_final.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

for n in wf['nodes']:
    if n['name'] == 'Preparar Mensaje Final':
        print(json.dumps(n, indent=2))
