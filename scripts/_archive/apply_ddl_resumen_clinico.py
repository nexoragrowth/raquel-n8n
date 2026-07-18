"""
One-shot: agrega columnas resumen_clinico + resumen_actualizado_at a tabla pacientes
de Supabase, ejecutando DDL via un workflow n8n temporal que usa el credential
Postgres existente (xwvjww5Odcxiy1K9 = mismo Postgres del Supabase de la clinica).

Pasos: crear wf temporal -> activate -> trigger via execute endpoint -> verificar
schema via Supabase REST -> borrar wf temporal.
"""
import json
import re
import time
import urllib.request
from pathlib import Path

txt = Path('.env').read_text()
API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', txt).group(1).strip()
SUP = re.search(r'SUPABASE_URL=([^\r\n]+)', txt).group(1).strip()
SUP_KEY = re.search(r'SUPABASE_SERVICE_ROLE_KEY=([^\r\n]+)', txt).group(1).strip()

BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
PG_CRED_ID = 'xwvjww5Odcxiy1K9'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}


def http_req(method, url, data=None):
    req = urllib.request.Request(url, method=method, headers=HEADERS,
                                 data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


def schema_has_col(table, col):
    h = {'apikey': SUP_KEY, 'Authorization': f'Bearer {SUP_KEY}'}
    req = urllib.request.Request(f'{SUP}/rest/v1/', headers=h)
    with urllib.request.urlopen(req, timeout=15) as r:
        s = json.loads(r.read())
    return col in s.get('definitions', {}).get(table, {}).get('properties', {})


def main():
    print('Pre-check: columnas existen?')
    for c in ['resumen_clinico', 'resumen_actualizado_at']:
        print(f'  pacientes.{c}: {schema_has_col("pacientes", c)}')

    sql = """
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS resumen_clinico TEXT;
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS resumen_actualizado_at TIMESTAMPTZ;
""".strip()

    wf_def = {
        'name': 'TEMP - DDL resumen_clinico',
        'nodes': [
            {
                'parameters': {},
                'id': 'manual-trigger',
                'name': 'When clicking Execute workflow',
                'type': 'n8n-nodes-base.manualTrigger',
                'typeVersion': 1,
                'position': [240, 300],
            },
            {
                'parameters': {
                    'operation': 'executeQuery',
                    'query': sql,
                    'options': {},
                },
                'id': 'ddl-node',
                'name': 'Execute DDL',
                'type': 'n8n-nodes-base.postgres',
                'typeVersion': 2.5,
                'position': [460, 300],
                'credentials': {'postgres': {'id': PG_CRED_ID, 'name': 'Postgres account'}},
            },
        ],
        'connections': {
            'When clicking Execute workflow': {
                'main': [[{'node': 'Execute DDL', 'type': 'main', 'index': 0}]]
            }
        },
        'settings': {'executionOrder': 'v1'},
    }

    print('\nCreando workflow temporal...')
    wf = http_req('POST', f'{BASE}/workflows', wf_def)
    wid = wf['id']
    print(f'  wf id: {wid}')

    print('Activando workflow...')
    try:
        http_req('POST', f'{BASE}/workflows/{wid}/activate')
    except Exception as ex:
        print(f'  activate skip: {ex}')

    # n8n API publico no tiene endpoint /execute para wfs. Usamos webhook trigger
    # alternativo: trigger manual via internal? Mejor cambiar a webhook trigger.
    # PATCH approach: cambiar a webhook trigger y postear.

    # Actualizar wf: cambiar manual trigger por webhook
    wh_path = f'ddl-{int(time.time())}'
    wf2 = {
        'name': 'TEMP - DDL resumen_clinico',
        'nodes': [
            {
                'parameters': {
                    'httpMethod': 'POST',
                    'path': wh_path,
                    'options': {},
                },
                'id': 'webhook-trigger',
                'name': 'Webhook',
                'type': 'n8n-nodes-base.webhook',
                'typeVersion': 2,
                'position': [240, 300],
                'webhookId': wh_path,
            },
            {
                'parameters': {
                    'operation': 'executeQuery',
                    'query': sql,
                    'options': {},
                },
                'id': 'ddl-node',
                'name': 'Execute DDL',
                'type': 'n8n-nodes-base.postgres',
                'typeVersion': 2.5,
                'position': [460, 300],
                'credentials': {'postgres': {'id': PG_CRED_ID, 'name': 'Postgres account'}},
            },
        ],
        'connections': {
            'Webhook': {
                'main': [[{'node': 'Execute DDL', 'type': 'main', 'index': 0}]]
            }
        },
        'settings': {'executionOrder': 'v1'},
    }
    print('Actualizando wf a webhook trigger...')
    http_req('PUT', f'{BASE}/workflows/{wid}', wf2)

    print('Activando...')
    try:
        http_req('POST', f'{BASE}/workflows/{wid}/deactivate')
    except Exception:
        pass
    time.sleep(1)
    http_req('POST', f'{BASE}/workflows/{wid}/activate')
    time.sleep(2)

    print(f'Disparando webhook https://n8n.raquelrodriguez.com.ar/webhook/{wh_path}...')
    req = urllib.request.Request(
        f'https://n8n.raquelrodriguez.com.ar/webhook/{wh_path}',
        method='POST', headers={'Content-Type': 'application/json'},
        data=b'{}'
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f'  webhook resp: {r.read().decode()[:300]}')
    except Exception as ex:
        print(f'  webhook err: {ex}')

    time.sleep(2)
    print('\nPost-check: columnas existen?')
    for c in ['resumen_clinico', 'resumen_actualizado_at']:
        ok = schema_has_col('pacientes', c)
        print(f'  pacientes.{c}: {ok}')

    print('\nLimpiando: deactivate + delete workflow temporal...')
    try:
        http_req('POST', f'{BASE}/workflows/{wid}/deactivate')
    except Exception:
        pass
    http_req('DELETE', f'{BASE}/workflows/{wid}')
    print('  OK, wf borrado')


if __name__ == '__main__':
    main()
