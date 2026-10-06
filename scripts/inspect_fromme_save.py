# inspect_fromme_save.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

for n in wf['nodes']:
    if n['name'] == 'Postgres - Save fromMe':
        print(json.dumps(n, indent=2))
