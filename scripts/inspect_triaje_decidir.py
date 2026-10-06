# inspect_triaje_decidir.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

for n in wf['nodes']:
    if n['name'] == 'Triaje: Decidir':
        code = n['parameters'].get('jsCode', '')
        for line in code.split('\n'):
            if 'Existe paciente?' in line:
                print("Línea en Triaje: Decidir:", line)
