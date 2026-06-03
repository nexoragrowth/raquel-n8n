"""
Manda al grupo de derivaciones (120363407321448469@g.us) un mensaje
consolidado con las escalaciones reales del bot de HOY que no fueron
notificadas a Iri/Dra (el bot mandaba a Lucas personal hasta el fix de hoy).

Como Evolution API esta en VPS interno (http://187.127.0.110:65302), no
accesible desde local, creamos un workflow n8n temporal con un HTTP Request
que corre dentro de la VPS y borra al terminar.

USO:
    python scripts/dispatch_escalaciones_hoy.py
"""
import io
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def env(k):
    return re.search(rf'{k}=([^\r\n]+)', Path('.env').read_text()).group(1).strip()


API_KEY = env('N8N_API_KEY')
GROUP_JID = env('WHATSAPP_DERIVACIONES_GROUP_JID')
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}
EVO_INSTANCE = 'raquel'
EVO_BASE = 'http://187.127.0.110:65302'
EVO_APIKEY = '4E2D1CE57F2F-471B-895E-EB2B8F427FAD'


def http_req(method, url, data=None):
    req = urllib.request.Request(url, method=method, headers=HEADERS,
                                 data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


def collect_today_escalations():
    all_execs = []
    cursor = None
    for _ in range(10):
        url = f'{BASE}/executions?workflowId=O155MqHgOSaNZ9ye&limit=100'
        if cursor:
            url += f'&cursor={cursor}'
        d = http_req('GET', url)
        all_execs.extend(d['data'])
        cursor = d.get('nextCursor')
        if not cursor:
            break
        if d['data'] and d['data'][-1].get('startedAt', '') < '2026-05-22T00':
            break

    today = [e for e in all_execs if e.get('startedAt', '').startswith('2026-05-22')]
    print(f'Total execs hoy: {len(today)}')

    casos = {}
    for e in today:
        try:
            d = http_req('GET', f'{BASE}/executions/{e["id"]}?includeData=true')
            runs = d.get('data', {}).get('resultData', {}).get('runData', {})
            if 'escalar_a_secretaria' not in runs:
                continue
            ef = runs.get('Edit Fields - Extraer Datos', [])
            if not ef:
                continue
            j = ef[0]['data']['main'][0][0]['json']
            phone = j.get('phone', '?')
            # filtrar phones sinteticos (mis tests)
            if phone.startswith('5491200') or phone.startswith('5491100') or phone == '5491161461034':
                continue
            push = j.get('name') or j.get('pushName') or '?'
            text = j.get('text', '')
            try:
                args = runs['escalar_a_secretaria'][0]['data']['ai_tool'][0][0]['json'].get('query', '')
                if isinstance(args, dict):
                    args = args.get('query', '') or str(args)
            except Exception:
                args = ''
            sub = next((s for s in runs if 'Sub-Agent' in s and 'LM' not in s), '?')

            # dedupe por phone, mantener mas tarde
            cur = casos.get(phone)
            if cur and cur['startedAt'] > e['startedAt']:
                continue
            casos[phone] = {
                'startedAt': e['startedAt'],
                'phone': phone,
                'pushName': push,
                'text': text,
                'sub': sub,
                'query': str(args)
            }
        except Exception:
            pass
    return list(casos.values())


def format_message(casos):
    if not casos:
        return None
    lines = []
    lines.append('🤖 BACKLOG DEL BOT - ESCALACIONES PENDIENTES DE HOY')
    lines.append('')
    lines.append('Hasta ahora estas escalaciones se mandaban solo al numero personal de Lucas, no a este grupo. Acabamos de fixearlo. Estos son los casos REALES de hoy que necesitan atencion:')
    lines.append('')
    for i, c in enumerate(casos, 1):
        # convertir UTC a ARG
        dt_utc = datetime.fromisoformat(c['startedAt'].replace('Z', '').split('.')[0])
        dt_arg = dt_utc - timedelta(hours=3)
        arg_str = dt_arg.strftime('%H:%M')
        sub_clean = c['sub'].replace('Sub-Agent ', '')
        text_clean = c['text'].replace('\n', ' ')[:120]
        query_clean = c['query'].replace('\n', ' ')[:200]
        lines.append(f'{i}. [{arg_str} - {sub_clean}] {c["pushName"]!r} ({c["phone"]})')
        lines.append(f'   Paciente dijo: {text_clean!r}')
        if query_clean and query_clean != text_clean:
            lines.append(f'   Bot resumen: {query_clean!r}')
        lines.append('')
    lines.append('Desde el proximo escalado el bot manda directo aqui al grupo.')
    return '\n'.join(lines)


def create_temp_workflow_for_send():
    wh_path = f'send-group-{int(time.time())}'
    wf_def = {
        'name': 'TEMP - Send Group Backlog',
        'nodes': [
            {
                'parameters': {
                    'httpMethod': 'POST',
                    'path': wh_path,
                    'options': {'responseData': 'allEntries'}
                },
                'id': 'webhook',
                'name': 'Webhook',
                'type': 'n8n-nodes-base.webhook',
                'typeVersion': 2,
                'position': [240, 300],
                'webhookId': wh_path
            },
            {
                'parameters': {
                    'method': 'POST',
                    'url': f'{EVO_BASE}/message/sendText/{EVO_INSTANCE}',
                    'sendHeaders': True,
                    'headerParameters': {
                        'parameters': [
                            {'name': 'apikey', 'value': EVO_APIKEY},
                            {'name': 'Content-Type', 'value': 'application/json'}
                        ]
                    },
                    'sendBody': True,
                    'specifyBody': 'json',
                    'jsonBody': '={{ JSON.stringify({number: $json.body.number, text: $json.body.text}) }}',
                    'options': {}
                },
                'id': 'http',
                'name': 'Evolution Send',
                'type': 'n8n-nodes-base.httpRequest',
                'typeVersion': 4.2,
                'position': [460, 300]
            }
        ],
        'connections': {
            'Webhook': {'main': [[{'node': 'Evolution Send', 'type': 'main', 'index': 0}]]}
        },
        'settings': {'executionOrder': 'v1'}
    }
    wf = http_req('POST', f'{BASE}/workflows', wf_def)
    wid = wf['id']
    try:
        http_req('POST', f'{BASE}/workflows/{wid}/activate')
    except Exception as e:
        print(f'activate skip: {e}')
    return wid, wh_path


def send_to_group(wh_path, message):
    url = f'https://n8n.raquelrodriguez.com.ar/webhook/{wh_path}'
    payload = {'number': GROUP_JID, 'text': message}
    req = urllib.request.Request(url, method='POST',
                                 headers={'Content-Type': 'application/json'},
                                 data=json.dumps(payload).encode())
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode()


def cleanup_workflow(wid):
    try:
        http_req('POST', f'{BASE}/workflows/{wid}/deactivate')
    except Exception:
        pass
    http_req('DELETE', f'{BASE}/workflows/{wid}')


def main():
    print('Recolectando escalaciones reales de hoy...')
    casos = collect_today_escalations()
    casos.sort(key=lambda x: x['startedAt'])
    print(f'\nEscalaciones unicas (pacientes reales): {len(casos)}')
    for c in casos:
        dt_utc = datetime.fromisoformat(c['startedAt'].replace('Z', '').split('.')[0])
        dt_arg = dt_utc - timedelta(hours=3)
        arg_str = dt_arg.strftime('%H:%M')
        print(f'  {arg_str} {c["phone"]} {c["pushName"]!r} sub={c["sub"]}')

    if not casos:
        print('No hay escalaciones reales hoy. Nada que dispatchar.')
        return

    msg = format_message(casos)
    print(f'\nMensaje a enviar al grupo ({len(msg)} chars):')
    print('-' * 60)
    print(msg)
    print('-' * 60)

    import sys
    if '--yes' not in sys.argv:
        confirm = input('\nEnviar al grupo? [y/N] ').strip().lower()
        if confirm != 'y':
            print('Cancelado')
            return

    print('\nCreando workflow temporal...')
    wid, wh_path = create_temp_workflow_for_send()
    print(f'  wf={wid} wh_path={wh_path}')

    time.sleep(2)
    print(f'\nEnviando al grupo {GROUP_JID}...')
    try:
        resp = send_to_group(wh_path, msg)
        print(f'  resp: {resp[:300]}')
    except Exception as e:
        print(f'  ERR: {e}')

    print('\nLimpiando workflow temporal...')
    cleanup_workflow(wid)
    print('  done')


if __name__ == '__main__':
    main()
