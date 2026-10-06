# inspect_cw.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

cw_names = {
    'Chatwoot - Buscar Conversacion', 'Verificar Label Humano',
    'Humano Atendiendo (no hacer nada)', 'Delay Humano',
    'CW Search Contact', 'CW Extract Conv', 'CW Get Conversations',
    'CW Pick Conv', 'CW Set Label humano', 'Re-check Humano',
    'Hay humano ahora?', 'Humano aparecio?', 'Aviso humano tomo chat',
    'Gate Humano Final'
}

print("=== NODOS RELEVANTES ===")
for n in wf['nodes']:
    if n['name'] in cw_names:
        print(f"[{n['name']}] (type: {n['type']})")

print("\n=== CONEXIONES INBOUND Y OUTBOUND ===")
for src, targets in wf.get('connections', {}).items():
    for output_type, conns in targets.items():
        for group in conns:
            for c in group:
                target_node = c.get('node')
                if src in cw_names or target_node in cw_names:
                    print(f"  {src} -> {target_node} ({output_type})")
