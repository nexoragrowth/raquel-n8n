"""
Probar el bot en producción enviando un mensaje simulado al webhook real.

USO:
  python scripts/probar_bot_e2e.py "tu mensaje aca"
  python scripts/probar_bot_e2e.py --phone 5491161461034 "Hola querria un turno"

QUE HACE:
- Postea al webhook de prod del v6 (evolution-v2) un payload con el formato real
  que manda Evolution API.
- Usa por default el phone de Lucas (ADMIN_LUCAS_PHONE del .env).
- El bot procesa el mensaje y te responde por WhatsApp REAL.
- Monitor en vivo: imprime la exec que matchea y muestra que tools llamo,
  con que args, y el output final.

USAR CUANDO:
- Validar que un fix nuevo funciona end-to-end con tu propio numero.
- Reproducir un caso real sin esperar al cron de mañana.

NO USAR PARA:
- Mandar mensajes a pacientes reales (siempre se manda el output al phone que pones).
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request
from pathlib import Path


def env(key, default=None):
    txt = Path('.env').read_text()
    m = re.search(rf'{key}=([^\r\n]+)', txt)
    return m.group(1).strip() if m else default


API_KEY = env('N8N_API_KEY')
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
WID = env('N8N_WORKFLOW_V6_ID')
WEBHOOK = 'https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2'
DEFAULT_PHONE = env('ADMIN_LUCAS_PHONE', '5491161461034')
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}

SUB_AGENTS = [
    'Sub-Agent Confirmar', 'Sub-Agent Cancelar', 'Sub-Agent Agendar',
    'Sub-Agent Urgencia', 'Sub-Agent General',
]
TOOL_NAMES = [
    'buscar_paciente_dentalink', 'ver_turnos_paciente', 'confirmar_turno',
    'reservar_turno', 'buscar_horarios', 'cancelar_turno', 'ver_profesionales',
    'escalar_a_secretaria', 'obtener_historial_paciente', 'crear_paciente_dentalink',
    'buscar_conocimiento',
]


def http_req(method, url, data=None):
    req = urllib.request.Request(url, method=method, headers=HEADERS,
                                 data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()) if r.status != 204 else None


def post_webhook(url, payload):
    req = urllib.request.Request(url, method='POST',
                                 headers={'Content-Type': 'application/json'},
                                 data=json.dumps(payload).encode())
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode()


def find_exec_by_key(key_id, phone, max_wait=90):
    print(f'  esperando exec del bot (max {max_wait}s)...')
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            data = http_req('GET', f'{BASE}/executions?workflowId={WID}&limit=20')
            for e in data['data']:
                detail = http_req('GET', f'{BASE}/executions/{e["id"]}?includeData=true')
                runs = detail.get('data', {}).get('resultData', {}).get('runData', {})
                ef = runs.get('Edit Fields - Extraer Datos', [])
                if not ef:
                    continue
                try:
                    j = ef[0]['data']['main'][0][0]['json']
                    kid = j.get('key_id', '')
                except Exception:
                    continue
                if kid != key_id:
                    continue
                if any(s in runs for s in SUB_AGENTS) or 'Pre-filtro Cierre' in runs:
                    return e['id'], runs, j
        except Exception:
            pass
        time.sleep(3)
    return None, None, None


def show_result(eid, runs, j):
    print(f'\n{"="*70}')
    print(f'EXEC {eid}')
    print(f'{"="*70}')
    print(f'phone webhook: {j.get("phone")!r}')
    print(f'pushName:      {j.get("pushName")!r}')
    print(f'msg:           {j.get("mensaje")!r}')

    pre = runs.get('Pre-filtro Cierre', [])
    if pre:
        try:
            print(f'pre-filtro:    {pre[0]["data"]["main"][0][0]["json"]}')
        except Exception:
            pass

    sub_used = next((s for s in SUB_AGENTS if s in runs), None)
    print(f'sub-agent:     {sub_used}')

    print(f'\nTOOLS llamadas:')
    for t in TOOL_NAMES:
        if t not in runs:
            continue
        for run in runs[t]:
            try:
                ai = run['data']['ai_tool'][0][0]['json']
                args = ai.get('toolCallParams', run.get('inputOverride', {}).get('ai_tool', [[{}]])[0][0].get('json', {}).get('query', {}))
                resp = str(ai.get('response', ''))[:200]
                print(f'  {t}')
                print(f'    args: {args}')
                print(f'    resp: {resp!r}')
            except Exception as ex:
                print(f'  {t}: parse_err {ex}')

    split = runs.get('Split en Mensajes', [])
    final = ''
    if split:
        try:
            final = ' || '.join(it['json'].get('message', '') for it in split[0]['data']['main'][0])
        except Exception:
            pass
    print(f'\nMENSAJE QUE LE LLEGA AL PACIENTE:')
    print(f'  {final or "(silencio / NO_REPLY)"}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mensaje', help='Mensaje que vas a mandar como paciente')
    ap.add_argument('--phone', default=DEFAULT_PHONE, help=f'Phone (default {DEFAULT_PHONE})')
    ap.add_argument('--push', default='Lucas Test E2E', help='pushName WA')
    args = ap.parse_args()

    key_id = f'E2E_{int(time.time())}_{random.randint(1000,9999)}'
    print(f'phone={args.phone}  pushName={args.push!r}  key_id={key_id}')
    print(f'>>> {args.mensaje!r}')

    payload = {'data': {
        'key': {'id': key_id, 'remoteJid': f'{args.phone}@s.whatsapp.net', 'fromMe': False},
        'pushName': args.push,
        'message': {'conversation': args.mensaje},
        'messageTimestamp': int(time.time()),
    }}
    post_webhook(WEBHOOK, payload)
    print('  webhook 200')

    eid, runs, j = find_exec_by_key(key_id, args.phone, max_wait=120)
    if not eid:
        print('  NO_EXEC (timeout)')
        return

    show_result(eid, runs, j)


if __name__ == '__main__':
    main()
