# inspect_media_preparar_staff_utf8.py
import json, re

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

for n in wf['nodes']:
    if n['name'] == 'Media: Preparar (staff)':
        code = n['parameters']['jsCode']
        # Busquemos referencias a otros nodos en code
        refs = re.findall(r"\$\(['\"]([^'\"]+)['\"]\)", code)
        print("Referencias a nodos en Media: Preparar (staff):", set(refs))
