# inspect_existe_usage.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

for n in wf['nodes']:
    s = json.dumps(n)
    if 'Existe paciente?' in s:
        print(f"Node referencing 'Existe paciente?': {n['name']}")
