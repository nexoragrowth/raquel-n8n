"""
Patch temporal del helper notify-grupo (S5U6tSipzlgFHCkf):
Durante tests E2E, redirige cualquier escalación al phone Lucas (5491161461034)
en lugar del grupo de la clínica (120363407321448469@g.us).

Uso:
    python scripts/patch_helper_safe_test.py --apply       # redirige a Lucas
    python scripts/patch_helper_safe_test.py --restore     # vuelve al grupo

Backup:
    workflows/history/helper_notify_grupo_ORIGINAL.json (se crea solo si no existe)
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
HELPER_ID = 'S5U6tSipzlgFHCkf'

LUCAS_JID = '5491161461034@s.whatsapp.net'
CLINIC_JID = '120363407321448469@g.us'

BACKUP_ORIGINAL = Path('workflows/history/helper_notify_grupo_ORIGINAL.json')


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204:
            return None
        return json.loads(r.read())


def get_helper():
    return http('GET', f'/workflows/{HELPER_ID}')


def update_helper(wf):
    safe = {k: wf[k] for k in ('name', 'nodes', 'connections', 'settings') if k in wf}
    return http('PUT', f'/workflows/{HELPER_ID}', safe)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--apply', action='store_true', help='Redirigir escalaciones a Lucas')
    g.add_argument('--restore', action='store_true', help='Volver al grupo clínica')
    args = ap.parse_args()

    wf = get_helper()
    print(f'helper: {wf["name"]} (active={wf["active"]})')

    if args.apply:
        if not BACKUP_ORIGINAL.exists():
            BACKUP_ORIGINAL.parent.mkdir(parents=True, exist_ok=True)
            BACKUP_ORIGINAL.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')
            print(f'  backup ORIGINAL guardado: {BACKUP_ORIGINAL}')
        target_jid = LUCAS_JID
        action = 'REDIRECT_TO_LUCAS'
    else:
        if not BACKUP_ORIGINAL.exists():
            print('NO backup found, abort')
            sys.exit(1)
        target_jid = CLINIC_JID
        action = 'RESTORE_TO_CLINIC'

    sent_node = next((n for n in wf['nodes'] if n['name'] == 'Notify Grupo Send'), None)
    if not sent_node:
        print('NO Notify Grupo Send node found')
        sys.exit(1)

    current = sent_node['parameters'].get('remoteJid')
    print(f'  remoteJid actual: {current}')
    sent_node['parameters']['remoteJid'] = target_jid
    print(f'  remoteJid nuevo:  {target_jid}  ({action})')

    backup_path = Path(f'workflows/history/helper_notify_grupo_{int(time.time())}.json')
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

    update_helper(wf)

    after = get_helper()
    after_jid = next((n for n in after['nodes'] if n['name'] == 'Notify Grupo Send'), {}).get('parameters', {}).get('remoteJid')
    print(f'  verify remoteJid post-PUT: {after_jid}')
    print('OK' if after_jid == target_jid else 'MISMATCH')


if __name__ == '__main__':
    main()
