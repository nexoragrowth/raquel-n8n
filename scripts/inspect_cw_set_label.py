# inspect_cw_set_label.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

for n in wf['nodes']:
    if n['name'] == 'CW Set Label humano':
        print("Node CW Set Label humano:")
        print(json.dumps(n, indent=2))
