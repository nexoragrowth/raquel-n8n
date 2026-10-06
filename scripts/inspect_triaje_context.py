# inspect_triaje_context.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

for n in wf['nodes']:
    if n['name'] == 'Triaje: Decidir':
        code = n['parameters'].get('jsCode', '')
        lines = code.split('\n')
        for i, line in enumerate(lines):
            if 'Existe paciente?' in line or 'contactId' in line or 'chatwoot' in line.lower():
                start = max(0, i-5)
                end = min(len(lines), i+15)
                print("\n".join(lines[start:end]))
                print("="*40)
