# inspect_cw_details_exact.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

nodes = {n['name']: n for n in wf['nodes']}

print("--- Hay humano ahora? ---")
print(nodes['Hay humano ahora?']['parameters']['jsCode'])

print("--- Humano aparecio? ---")
print(json.dumps(nodes['Humano aparecio?']['parameters'], indent=2))

print("--- Aviso humano tomo chat ---")
print(nodes['Aviso humano tomo chat']['parameters']['jsCode'])

print("--- Gate Humano Final ---")
print(nodes['Gate Humano Final']['parameters']['jsCode'])
