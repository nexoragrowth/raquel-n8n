"""
v6 Patch: expandir triggers de cancelar_o_reprogramar en Router LM.

Motivacion: el Router solo listaba "no puedo ir / necesito cancelar / voy a faltar /
queria reprogramar". Wording natural como "tengo clases ese dia", "se me complico",
"podemos pasarlo a otro dia" cae en consulta_general -> escala todo.

Cambios:
- Solo modifica el bloque "**3. cancelar_o_reprogramar**" del systemMessage del
  nodo "Router - Clasificar Intent" en el v6 (O155MqHgOSaNZ9ye).
- Mantiene el resto del prompt intacto.
- Backup pre/post + verify por replace exact match.
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

OLD = '''**3. cancelar_o_reprogramar**
"no puedo ir", "necesito cancelar", "voy a faltar", "queria reprogramar".
**CONTINUACION**: si el ultimo AI estaba en flujo cancelar y el paciente confirma o da info.'''

NEW = '''**3. cancelar_o_reprogramar**
Cualquier indicio de que el paciente quiere mover, cambiar, posponer o no asistir a un turno existente:
- Explicitos: "cancelar", "reprogramar", "anular", "suspender".
- Imposibilidad: "no puedo ir", "no voy a poder", "no llego", "no me da", "voy a faltar".
- Cambio: "podemos pasarlo", "lo podemos mover", "lo podemos cambiar", "moverlo a otro dia", "pasarlo a otro dia/horario", "lo necesito mover".
- Conflicto de agenda: "tengo clases", "tengo trabajo", "tengo otro compromiso", "se me complico", "me surgio algo", "tengo que viajar".
- Pregunta sobre cambio: "se puede cambiar?", "habria forma de pasarlo?", "puedo moverlo?".
**CONTINUACION**: si el ultimo AI estaba en flujo cancelar/reprogramar y el paciente confirma, da fecha, elige slot, rechaza slot, o aclara cual turno -> sigue siendo cancelar_o_reprogramar.'''


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


def main():
    print('=== FETCH v6 ===')
    wf = http('GET', f'/workflows/{WID}')
    print(f'  v6 nodes: {len(wf["nodes"])}')

    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    pre = Path(f'workflows/history/v6_PRE_ROUTER_EXPAND_{int(time.time())}.json')
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  backup PRE: {pre}')

    router = next((n for n in wf['nodes'] if n['name'] == 'Router - Clasificar Intent'), None)
    if not router:
        print('NO Router node found'); sys.exit(1)

    sm = router['parameters'].get('options', {}).get('systemMessage', '')
    if OLD not in sm:
        print('NO OLD pattern found in systemMessage. Abort.')
        # Show where it diverges
        idx = sm.find('**3.')
        if idx >= 0:
            print(f'  found "**3." at offset {idx}:')
            print(f'  ... {sm[idx:idx+400]!r} ...')
        sys.exit(1)

    new_sm = sm.replace(OLD, NEW)
    if new_sm == sm:
        print('Replace had no effect'); sys.exit(1)
    if OLD in new_sm:
        print('OLD still present, abort'); sys.exit(1)

    router['parameters']['options']['systemMessage'] = new_sm
    print('  systemMessage patched (+{} chars)'.format(len(new_sm) - len(sm)))

    ALLOWED_SETTINGS = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution',
        'saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone',
        'executionOrder','callerPolicy','callerIds'}
    safe = {k: wf[k] for k in ('name', 'nodes', 'connections', 'settings') if k in wf}
    safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED_SETTINGS}
    print(f'  settings sent: {list(safe["settings"].keys())}')
    print('=== PUT ===')
    http('PUT', f'/workflows/{WID}', safe)
    print('  PUT 200')

    after = http('GET', f'/workflows/{WID}')
    router_after = next((n for n in after['nodes'] if n['name'] == 'Router - Clasificar Intent'), {})
    sm_after = router_after.get('parameters', {}).get('options', {}).get('systemMessage', '')
    print(f'  verify NEW in systemMessage: {NEW[:60]!r}... -> {NEW in sm_after}')
    post = Path(f'workflows/history/v6_POST_ROUTER_EXPAND_{int(time.time())}.json')
    post.write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  backup POST: {post}')


if __name__ == '__main__':
    main()
