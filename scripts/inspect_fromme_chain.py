# inspect_fromme_chain.py
import json

with open("workflows/current/v6_LIVE.json", "r", encoding="utf-8") as f:
    wf = json.load(f)

for src, targets in wf['connections'].items():
    if any(k in src.lower() for k in ['fromme', 'cw search', 'cw extract', 'cw get', 'cw pick', 'cw set', 'staff']):
        for otype, conns in targets.items():
            for g in conns:
                for c in g:
                    print(f"{src} -> {c['node']}")
