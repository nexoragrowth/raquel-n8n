"""WIRING v6 -> Sub-WF CancelarReprogramar.

PREPARADO pero NO aplica automáticamente. Lucas debe correr manualmente:
    python scripts/apply_wiring_v6_subwf.py --apply

Sin --apply: solo muestra el diff.

CAMBIO:
- En el v6 (O155MqHgOSaNZ9ye), el Switch sobre Intent rama "cancelar" actualmente
  va a Sub-Agent Cancelar (LLM langchain con tools).
- Lo reemplazamos por: Execute Workflow → Sub-WF CancelarReprogramar (procedural)
  → Format Output (mapea output del sub-WF al formato esperado por Fallback Output).
- continueOnFail en Execute Workflow: si crashea, va al fallback escalatorio.
- Sub-Agent Cancelar viejo NO se borra (queda como backup; si rollback necesario,
  re-conectar Switch directo a el).

ROLLBACK:
    python scripts/apply_wiring_v6_subwf.py --rollback
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path


def env(k):
    return re.search(rf'{k}=([^\r\n]+)', Path('.env').read_text()).group(1).strip()


API_KEY = env('N8N_API_KEY')
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
WID_V6 = 'O155MqHgOSaNZ9ye'
WID_SUB = Path('docs/sub_wf_cancelar_id.txt').read_text().strip()
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}
ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution',
           'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone',
           'executionOrder', 'callerPolicy', 'callerIds'}


def http(method, url, data=None):
    req = urllib.request.Request(url, method=method, headers=HEADERS,
                                 data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


EXEC_SUB_NODE = {
    'parameters': {
        'workflowId': {'__rl': True, 'value': WID_SUB, 'mode': 'id'},
        'workflowInputs': {
            'mappingMode': 'defineBelow',
            'value': {
                'phone': "={{ $('Edit Fields - Extraer Datos').first().json.phone }}",
                'text': "={{ $('Preparar Mensaje Final').first().json.text }}",
                'pushName': "={{ $('Edit Fields - Extraer Datos').first().json.pushName }}"
            },
            'matchingColumns': [], 'schema': []
        }
    },
    'id': 'exec-subwf-cancelar',
    'name': 'Execute Sub-WF Cancelar',
    'type': 'n8n-nodes-base.executeWorkflow',
    'typeVersion': 1.2,
    'position': [3200, 800],
    'continueOnFail': True,
    'alwaysOutputData': True
}

FORMAT_OUTPUT_NODE = {
    'parameters': {
        'jsCode': """// Adapta el output del sub-WF al formato que espera Fallback Output del v6.
// El v6 normalmente espera un campo `output` (texto del agent).
const subOut = $input.first().json;

// Si el sub-WF crasheo (continueOnFail) viene con error, hacer fallback escalatorio.
if (subOut?.error || (!subOut?.mensaje_final && !subOut?.output)) {
  return [{ json: {
    output: 'Le paso a la secretaria Irina para que le ayude lo antes posible.',
    _flow: 'cancelar_subwf_fallback',
    _sub_wf_error: subOut?.error?.message || 'sin mensaje_final'
  }}];
}

return [{ json: {
  output: subOut.mensaje_final,
  _flow: 'cancelar_subwf',
  _action: subOut.action_executed,
  _label_humano: subOut.apply_label_humano,
  _debug: subOut.debug
}}];"""
    },
    'id': 'format-subwf-output',
    'name': 'Format Sub-WF Output',
    'type': 'n8n-nodes-base.code',
    'typeVersion': 2,
    'position': [3400, 800]
}


def show_diff(wf):
    """Muestra qué cambiaría sin aplicar."""
    print('=== DIFF (sin aplicar) ===')
    # Find Switch sobre Intent connection a Sub-Agent Cancelar
    print('Conexión actual:')
    src_conn = wf['connections'].get('Switch sobre Intent', {}).get('main', [])
    for i, branch in enumerate(src_conn):
        for c in branch:
            if c.get('node') == 'Sub-Agent Cancelar':
                print(f'  Switch sobre Intent[branch {i}] -> Sub-Agent Cancelar')

    print('\nConexión propuesta:')
    print('  Switch sobre Intent[branch 1] -> Execute Sub-WF Cancelar')
    print('  Execute Sub-WF Cancelar -> Format Sub-WF Output')
    print('  Format Sub-WF Output -> Fallback Output')
    print('\nNodos nuevos a agregar:')
    print(f'  - Execute Sub-WF Cancelar (n8n-nodes-base.executeWorkflow) -> Sub-WF {WID_SUB}')
    print(f'  - Format Sub-WF Output (Code node)')
    print('\nSub-Agent Cancelar NO se elimina (queda colgado como backup para rollback).')


def apply(wf):
    """Aplica el wiring."""
    # Backup pre
    bak = f'workflows/history/v6_PRE_WIRING_SUBWF_{int(time.time())}.json'
    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    Path(bak).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup PRE: {bak}')

    # Agregar nodos si no existen
    existing = {n['name'] for n in wf['nodes']}
    if 'Execute Sub-WF Cancelar' not in existing:
        wf['nodes'].append(EXEC_SUB_NODE)
    if 'Format Sub-WF Output' not in existing:
        wf['nodes'].append(FORMAT_OUTPUT_NODE)

    # Cambiar la conexión del Switch sobre Intent rama "cancelar"
    # Switch sobre Intent rama 1 = cancelar (confirmado por audit anterior)
    switch_conns = wf['connections'].get('Switch sobre Intent', {}).get('main', [])
    # Replace branch que apunta a Sub-Agent Cancelar
    new_branches = []
    for i, branch in enumerate(switch_conns):
        new_branch = []
        for c in branch:
            if c.get('node') == 'Sub-Agent Cancelar':
                new_branch.append({'node': 'Execute Sub-WF Cancelar', 'type': 'main', 'index': 0})
            else:
                new_branch.append(c)
        new_branches.append(new_branch)
    wf['connections']['Switch sobre Intent']['main'] = new_branches

    # Conexión Execute Sub-WF -> Format Output -> Fallback Output
    wf['connections']['Execute Sub-WF Cancelar'] = {
        'main': [[{'node': 'Format Sub-WF Output', 'type': 'main', 'index': 0}]]
    }
    wf['connections']['Format Sub-WF Output'] = {
        'main': [[{'node': 'Fallback Output', 'type': 'main', 'index': 0}]]
    }

    # PUT
    put = {
        'name': wf['name'],
        'nodes': wf['nodes'],
        'connections': wf['connections'],
        'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}
    }
    http('PUT', f'{BASE}/workflows/{WID_V6}', put)
    print(f'PUT: 200')

    try:
        http('POST', f'{BASE}/workflows/{WID_V6}/activate')
    except Exception as e:
        print(f'activate skip: {e}')

    # Backup post
    wf2 = http('GET', f'{BASE}/workflows/{WID_V6}')
    bak2 = f'workflows/history/v6_POST_WIRING_SUBWF_{int(time.time())}.json'
    Path(bak2).write_text(json.dumps(wf2, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup POST: {bak2}')

    # Verificación
    has_exec = any(n['name'] == 'Execute Sub-WF Cancelar' for n in wf2['nodes'])
    has_format = any(n['name'] == 'Format Sub-WF Output' for n in wf2['nodes'])
    print(f'\nVERIFY: Execute Sub-WF Cancelar node={has_exec}, Format Output node={has_format}')


def rollback(wf):
    """Reverte: vuelve a conectar Switch -> Sub-Agent Cancelar."""
    bak = f'workflows/history/v6_PRE_ROLLBACK_{int(time.time())}.json'
    Path(bak).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup PRE rollback: {bak}')

    # Revertir conexión
    switch_conns = wf['connections'].get('Switch sobre Intent', {}).get('main', [])
    new_branches = []
    for branch in switch_conns:
        new_branch = []
        for c in branch:
            if c.get('node') == 'Execute Sub-WF Cancelar':
                new_branch.append({'node': 'Sub-Agent Cancelar', 'type': 'main', 'index': 0})
            else:
                new_branch.append(c)
        new_branches.append(new_branch)
    wf['connections']['Switch sobre Intent']['main'] = new_branches

    # Eliminar conexiones huérfanas
    wf['connections'].pop('Execute Sub-WF Cancelar', None)
    wf['connections'].pop('Format Sub-WF Output', None)

    # Eliminar nodos nuevos
    wf['nodes'] = [n for n in wf['nodes'] if n['name'] not in ('Execute Sub-WF Cancelar', 'Format Sub-WF Output')]

    put = {
        'name': wf['name'],
        'nodes': wf['nodes'],
        'connections': wf['connections'],
        'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}
    }
    http('PUT', f'{BASE}/workflows/{WID_V6}', put)
    print('ROLLBACK aplicado')


def main():
    wf = http('GET', f'{BASE}/workflows/{WID_V6}')

    if '--apply' in sys.argv:
        apply(wf)
    elif '--rollback' in sys.argv:
        rollback(wf)
    else:
        show_diff(wf)
        print('\n(Dry-run, sin cambios. Correr con --apply para aplicar.)')


if __name__ == '__main__':
    main()
