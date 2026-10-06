# inspect_satellites.py
import json
from pathlib import Path
from lib_env import env
from apply_media_entrantes import api

workflows_to_check = [
    ("Human Takeover", "w7BBpZeEwZnpCX1q"),
    ("Auto Reactivar", "fosfga62zNaN0qrx"),
    ("Panel Acciones Staff", "jzxb5zUKCaJcvCgp")
]

for name, wid in workflows_to_check:
    print(f"================ {name} ({wid}) ================")
    try:
        wf = api(f"/workflows/{wid}")
        print(f"Activo: {wf.get('active')}")
        for n in wf.get('nodes', []):
            if any(k in n['name'].lower() for k in ['chatwoot', 'cw', 'takeover', 'humano', 'label', 'postgres', 'supabase']):
                print(f"  Node: {n['name']} ({n['type']})")
    except Exception as e:
        print(f"Error fetching {wid}: {e}")
