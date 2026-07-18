"""
Cambia el modelo de un nodo LLM en el v6.

Soporta:
- OpenAI: lmChatOpenAi  -> simplemente cambia parameters.model.value
- Anthropic: cambia tipo del nodo de lmChatOpenAi -> lmChatAnthropic + adapta params + cred

Uso:
    python scripts/rotar_modelo_nodo.py "LM Sub-Agent General" gpt-4o-mini
    python scripts/rotar_modelo_nodo.py "LM Sub-Agent General" claude-haiku-4-5
    python scripts/rotar_modelo_nodo.py "LM Sub-Agent General" gemini-2.5-flash
    python scripts/rotar_modelo_nodo.py "LM Sub-Agent General" --restore        # restaura desde backup mas reciente
"""
import argparse
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

ALLOWED_SETTINGS = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution',
    'saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone',
    'executionOrder','callerPolicy','callerIds'}

# Provider mapping by model name prefix
PROVIDERS = {
    # OpenAI
    'gpt-': ('openai', '@n8n/n8n-nodes-langchain.lmChatOpenAi', 'openAiApi', 'nYujqfon7GGDnJUO', 'OpenAi account'),
    # Anthropic — necesita cred propia, agregar al .env y crear en n8n primero
    'claude-': ('anthropic', '@n8n/n8n-nodes-langchain.lmChatAnthropic', 'anthropicApi', None, 'Anthropic account'),
    # Google Gemini
    'gemini-': ('google', '@n8n/n8n-nodes-langchain.lmChatGoogleGemini', 'googlePalmApi', None, 'Google account'),
}


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


def find_provider(model):
    for prefix, info in PROVIDERS.items():
        if model.startswith(prefix):
            return info
    raise ValueError(f'Modelo desconocido: {model}. Soportados: {list(PROVIDERS.keys())}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('node_name', help='Nombre del nodo LLM en el v6 (ej "LM Sub-Agent General")')
    ap.add_argument('model', nargs='?', help='Nombre del modelo a setear (ej gpt-4o-mini, claude-haiku-4-5)')
    ap.add_argument('--restore', action='store_true', help='Restaurar desde backup PRE mas reciente')
    args = ap.parse_args()

    print(f'=== ROTAR MODELO ===')
    print(f'  node: {args.node_name!r}')

    wf = http('GET', f'/workflows/{WID}')

    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r'\W+', '_', args.node_name)
    pre = Path(f'workflows/history/v6_PRE_MODEL_{safe_name}_{int(time.time())}.json')
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  backup PRE: {pre}')

    if args.restore:
        # Find latest PRE_MODEL_<safe_name>_*.json
        backups = sorted(Path('workflows/history').glob(f'v6_PRE_MODEL_{safe_name}_*.json'))
        if len(backups) < 2:
            print('No previous backup to restore from'); sys.exit(1)
        # The PRE just saved is backups[-1]; restore from backups[-2]
        prev = backups[-2]
        print(f'  restore source: {prev}')
        wf_prev = json.loads(prev.read_text(encoding='utf-8'))
        node_prev = next((n for n in wf_prev['nodes'] if n['name'] == args.node_name), None)
        node_curr_idx = next((i for i,n in enumerate(wf['nodes']) if n['name'] == args.node_name), None)
        if node_prev is None or node_curr_idx is None:
            print('node not found'); sys.exit(1)
        wf['nodes'][node_curr_idx] = node_prev
        print(f'  node restored from {prev.name}')
    else:
        if not args.model:
            print('model required (or use --restore)'); sys.exit(1)
        provider, ntype, cred_key, cred_id, cred_name = find_provider(args.model)
        print(f'  provider: {provider} ({ntype})')
        print(f'  new model: {args.model}')

        node = next((n for n in wf['nodes'] if n['name'] == args.node_name), None)
        if not node:
            print(f'Node {args.node_name!r} not found. Available LLM nodes:')
            for n in wf['nodes']:
                if 'lmChat' in n.get('type', ''):
                    cur_model = n.get('parameters', {}).get('model', {})
                    if isinstance(cur_model, dict): cur_model = cur_model.get('value', '?')
                    print(f'  - {n["name"]} ({n["type"]}) model={cur_model}')
            sys.exit(1)

        old_type = node['type']
        old_model = node.get('parameters', {}).get('model', {})
        if isinstance(old_model, dict): old_model = old_model.get('value', '?')
        print(f'  old: {old_type} model={old_model}')

        # Set new type if changing provider
        if old_type != ntype:
            node['type'] = ntype
            print(f'  changed type: {old_type} -> {ntype}')

        # Set model field
        if provider == 'openai':
            node['parameters']['model'] = {
                '__rl': True, 'value': args.model, 'mode': 'list', 'cachedResultName': args.model
            }
        elif provider == 'anthropic':
            node['parameters']['model'] = {
                '__rl': True, 'value': args.model, 'mode': 'list', 'cachedResultName': args.model
            }
        elif provider == 'google':
            node['parameters']['modelName'] = f'models/{args.model}'

        # Set creds
        if cred_id:
            node['credentials'] = {cred_key: {'id': cred_id, 'name': cred_name}}
        else:
            # Mantain existing if provider changed only model
            existing = node.get('credentials', {})
            if cred_key not in existing:
                print(f'  WARN: cred for {cred_key} not pre-configured. Falta crear en n8n.')
                print(f'  Skipping cred update — vas a tener que setearla a mano en la UI.')

    safe = {k: wf[k] for k in ('name', 'nodes', 'connections', 'settings') if k in wf}
    safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED_SETTINGS}

    print('=== PUT ===')
    http('PUT', f'/workflows/{WID}', safe)
    print('  PUT 200')

    after = http('GET', f'/workflows/{WID}')
    node_after = next((n for n in after['nodes'] if n['name'] == args.node_name), {})
    m = node_after.get('parameters', {}).get('model', {}) or node_after.get('parameters', {}).get('modelName')
    if isinstance(m, dict): m = m.get('value', '?')
    print(f'  verify: type={node_after.get("type")} model={m}')
    post = Path(f'workflows/history/v6_POST_MODEL_{safe_name}_{int(time.time())}.json')
    post.write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  backup POST: {post}')


if __name__ == '__main__':
    main()
