"""
v6 Patch: refinar Banlist Validator para no dar falsos positivos en outputs del KB.

Quita 3 reglas demasiado amplias que disparaban contra FAQ legítima:
- "es normal" - aparece en FAQ dolor: "es normal sentir molestia los primeros dias"
- "evita" - aparece en FAQ higiene/dolor: "evita alimentos duros"
- "descansa" - aparece en FAQ post-tratamiento

Mantiene TODAS las reglas críticas:
- Venir a la clinica (venite, vengan, te esperamos, ahora mismo+clinica)
- Direccion Balcarce 37 como confirmacion
- Diagnostico minimizante ("no te preocupes")
- Instrucciones medicas con dosis ("toma X cada Y")
- Imperativos clinicos especificos (guarda, traé, sacá, aplicá, enjuagá)

Backup pre/post + verify.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
WID = re.search(r'N8N_WORKFLOW_V6_ID=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution','saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder','callerPolicy','callerIds'}

# Lines to remove from Banlist (exactly)
LINES_TO_REMOVE = [
    "  { rx: /\\bdescans(á|a|en)\\b/i,                         why: 'descansa (instruccion medica)' },",
    "  { rx: /\\bevit(á|a|en)\\b/i,                            why: 'evita (instruccion medica)' },",
    "  { rx: /\\bes\\s+(totalmente\\s+)?normal\\b/i,             why: 'es normal (diagnostico)' },",
]


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


def main():
    print('=== FETCH v6 ===')
    wf = http('GET', f'/workflows/{WID}')
    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    pre = Path(f'workflows/history/v6_PRE_BANLIST_REFINE_{int(time.time())}.json')
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  backup PRE: {pre}')

    bl = next((n for n in wf['nodes'] if n['name'] == 'Banlist Validator'), None)
    if not bl:
        print('NO Banlist Validator found'); sys.exit(1)

    code = bl['parameters'].get('jsCode', '')
    removed = []
    for line in LINES_TO_REMOVE:
        if line in code:
            # Remove the line plus its trailing newline if present
            code = code.replace(line + '\n', '')
            removed.append(line[:60])
        else:
            print(f'  WARN line not found exact: {line[:60]}...')

    if not removed:
        print('No lines removed. Aborting'); sys.exit(1)

    print(f'  removed {len(removed)} reglas:')
    for r2 in removed:
        print(f'    - {r2}')

    bl['parameters']['jsCode'] = code

    safe = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
    safe['settings'] = {k:v for k,v in safe.get('settings',{}).items() if k in ALLOWED}
    print('=== PUT ===')
    http('PUT', f'/workflows/{WID}', safe)
    print('  PUT 200')

    after = http('GET', f'/workflows/{WID}')
    bl_after = next((n for n in after['nodes'] if n['name'] == 'Banlist Validator'), {})
    code_after = bl_after.get('parameters', {}).get('jsCode', '')
    still_present = [l for l in LINES_TO_REMOVE if l in code_after]
    print(f'  verify removed: still_present={len(still_present)}')

    post = Path(f'workflows/history/v6_POST_BANLIST_REFINE_{int(time.time())}.json')
    post.write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  backup POST: {post}')


if __name__ == '__main__':
    main()
