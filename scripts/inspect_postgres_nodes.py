# inspect_postgres_nodes.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

for n in wf['nodes']:
    if 'postgres' in n['type'].lower() or 'supabase' in n['type'].lower() or 'existe paciente' in n['name'].lower() or 'guardar' in n['name'].lower() or 'fromme' in n['name'].lower():
        print(f"NODE: {n['name']} | TYPE: {n['type']}")
        print(f"CREDENTIALS: {n.get('credentials')}")
        print(f"PARAMS: {json.dumps(n.get('parameters', {}), indent=2)}")
        print("-" * 50)
