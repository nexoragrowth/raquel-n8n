"""
Test ciclo productivo del sub-WF CancelarReprogramar via v6 vivo.

Cada ciclo:
- Asegura 1 cita activa en Dentalink para paciente 608 (Lucas)
- Tira N mensajes al webhook v6
- Verifica respuesta (matchea regex esperado)
- Reporta resultado

Bordes:
- TODO va al phone Lucas (5491161461034)
- Sin tocar el grupo de la clinica
- Cita test puede mutar entre ciclos (refrescamos al inicio)
"""
import json
import re
import sys
import time
import urllib.request
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
WID_V6 = re.search(r'N8N_WORKFLOW_V6_ID=([^\r\n]+)', open('.env').read()).group(1).strip()
WEBHOOK = 'https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
DT_CRED = 'TwN6eBWsydjMdsCM'
LUCAS = '5491161461034'


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


def temp_dentalink_call(name, method, url, body=None):
    """Run one Dentalink call via a temp workflow with cred attached."""
    wh = f'tmp-{name}-' + str(int(time.time()))
    node_http = {
        'method': method,
        'url': url,
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpHeaderAuth',
        'options': {}
    }
    if body is not None:
        node_http['sendBody'] = True
        node_http['specifyBody'] = 'json'
        node_http['jsonBody'] = json.dumps(body)
    wf = {
        'name': f'TMP-{name}',
        'nodes': [
            {'parameters': {'httpMethod':'POST','path':wh,'responseMode':'lastNode','options':{}},
             'id':'wh','name':'Webhook','type':'n8n-nodes-base.webhook','typeVersion':2,
             'position':[240,300],'webhookId':wh},
            {'parameters': node_http,
             'id':'h','name':'Call','type':'n8n-nodes-base.httpRequest','typeVersion':4.2,
             'position':[460,300],
             'credentials':{'httpHeaderAuth':{'id':DT_CRED,'name':'Header Auth account 3'}},
             'continueOnFail':True,'alwaysOutputData':True}
        ],
        'connections':{'Webhook':{'main':[[{'node':'Call','type':'main','index':0}]]}},
        'settings':{'executionOrder':'v1'}
    }
    r = http('POST', '/workflows', wf)
    WID = r['id']
    http('POST', f'/workflows/{WID}/activate')
    time.sleep(2)
    try:
        resp = urllib.request.urlopen(urllib.request.Request(
            f'https://n8n.raquelrodriguez.com.ar/webhook/{wh}', method='POST',
            headers={'Content-Type':'application/json'}, data=b'{}'), timeout=20)
        return json.loads(resp.read().decode())
    finally:
        http('POST', f'/workflows/{WID}/deactivate')
        http('DELETE', f'/workflows/{WID}')


def get_active_citas_lucas():
    """List Lucas's active future citas."""
    today = time.strftime('%Y-%m-%d')
    # Use search endpoint - method POST with q={id_paciente, fecha_desde}
    # We saw 405 on /citas/buscar so we GET each known cita id. Simplest: fetch by listing
    # Alternative: GET /pacientes/608/citas — that gave 400 earlier requiring JSON body.
    # We'll use search: POST /citas/ with q parameter — actually that's reserve. Skip.
    # Pragmatic: try /pacientes/608/citas with a query string:
    res = temp_dentalink_call('list-citas', 'GET',
        f'https://api.dentalink.healthatom.com/api/v1/pacientes/608/citas')
    if isinstance(res, dict) and res.get('error'):
        return None
    if isinstance(res, dict) and 'data' in res:
        # Filter active (id_estado not in cancelled/anulado states)
        ANUL = {1}  # estado 1 = Anulado per earlier verify
        active = [c for c in res['data'] if c.get('id_estado') not in ANUL and c.get('fecha') >= today]
        return active
    return res


def reservar_cita(fecha, hora='11:00', duracion=40, comentario='TEST cycle base'):
    body = {'id_dentista': 1, 'id_sucursal': 1, 'id_sillon': 1, 'id_paciente': 608,
            'fecha': fecha, 'hora_inicio': hora, 'duracion': duracion, 'comentario': comentario}
    res = temp_dentalink_call('reservar', 'POST',
        'https://api.dentalink.healthatom.com/api/v1/citas/', body=body)
    return res


def send_msg_to_bot(text, key_id=None):
    if key_id is None:
        key_id = f'CICLO_{int(time.time())}_{int(time.time() * 1000) % 10000}'
    payload = {'data': {
        'key': {'id': key_id, 'remoteJid': f'{LUCAS}@s.whatsapp.net', 'fromMe': False},
        'pushName': 'Lucas Test E2E',
        'message': {'conversation': text},
        'messageTimestamp': int(time.time()),
    }}
    req = urllib.request.Request(WEBHOOK, method='POST',
        headers={'Content-Type':'application/json'}, data=json.dumps(payload).encode())
    with urllib.request.urlopen(req, timeout=20) as r:
        r.read()
    return key_id


def find_response(key_id, max_wait=90):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            data = http('GET', f'/executions?workflowId={WID_V6}&limit=10')
            for e in data['data']:
                detail = http('GET', f'/executions/{e["id"]}?includeData=true')
                runs = detail.get('data', {}).get('resultData', {}).get('runData', {})
                ef = runs.get('Edit Fields - Extraer Datos', [])
                if not ef: continue
                try:
                    j = ef[0]['data']['main'][0][0]['json']
                    kid = j.get('key_id', '')
                except Exception:
                    continue
                if kid != key_id:
                    continue
                # extract message
                split = runs.get('Split en Mensajes', [])
                final = ''
                if split:
                    try:
                        final = ' || '.join(it['json'].get('message', '') for it in split[0]['data']['main'][0])
                    except Exception:
                        pass
                return e['id'], final
        except Exception:
            pass
        time.sleep(3)
    return None, None


def assert_match(label, msg, pattern):
    ok = bool(re.search(pattern, msg or '', re.IGNORECASE))
    mark = '✓' if ok else '✗'
    print(f'  {mark} {label}')
    print(f'      msg: {msg!r}')
    print(f'      expected match: {pattern!r}')
    return ok


def ensure_cita_base(fecha='2026-06-12', hora='11:00'):
    """Ensure paciente 608 has at least one active cita on or after today."""
    active = get_active_citas_lucas()
    if active:
        # Use the next active one
        c = sorted(active, key=lambda x: (x['fecha'], x['hora_inicio']))[0]
        print(f'  cita activa existente: id={c["id"]} {c["fecha"]} {c["hora_inicio"]}')
        return c
    print(f'  reservando cita base nueva: {fecha} {hora}')
    r = reservar_cita(fecha, hora)
    if isinstance(r, dict) and r.get('id'):
        print(f'  reservada id={r["id"]}')
        return r
    # response may be {data: {...}}
    if isinstance(r, dict) and r.get('data'):
        print(f'  reservada id={r["data"].get("id")}')
        return r['data']
    print(f'  ERR reservar: {str(r)[:200]}')
    return None


def ciclo_A_reprogramar_abierto():
    print('\n=== CICLO A: reprogramar abierto (sin fecha) ===')
    c = ensure_cita_base()
    if not c: return False
    kid = send_msg_to_bot('podemos pasarlo a otro dia?')
    eid, msg = find_response(kid)
    if not eid: print('  NO EXEC'); return False
    return assert_match('bot pregunta dia/franja', msg, r'qu[eé] d[ií]a.*viene mejor|qu[eé] d[ií]a.*prefiere|franja')


def ciclo_B_multi_turn_fecha():
    print('\n=== CICLO B: respuesta con fecha tras pregunta ===')
    # State should be from ciclo A: bot is "esperando_fecha"
    kid = send_msg_to_bot('el viernes 19 de junio')
    eid, msg = find_response(kid)
    if not eid: print('  NO EXEC'); return False
    return assert_match('bot ofrece slots', msg, r'tengo disponible|cu[aá]l confirma|cu[aá]l prefiere')


def ciclo_C_accept_slot():
    print('\n=== CICLO C: aceptar slot ofrecido ===')
    kid = send_msg_to_bot('el primero')
    eid, msg = find_response(kid)
    if not eid: print('  NO EXEC'); return False
    return assert_match('bot confirma reprogramado', msg, r'reprogramad|cancele.*reserv|te reserv')


def ciclo_D_cancelar_directo():
    print('\n=== CICLO D: cancelar directo (post-reprogramar) ===')
    # Ahora deberia haber una cita en 19 junio. Probar cancelacion directa
    c = ensure_cita_base()
    if not c: return False
    print(f'  cita actual: {c["fecha"]} {c["hora_inicio"]}')
    kid = send_msg_to_bot(f'cancelo el {c["fecha"]}')
    eid, msg = find_response(kid)
    if not eid: print('  NO EXEC'); return False
    return assert_match('bot confirma cancelacion', msg, r'cancelad|queda cancelad|listo.*cancel')


def main():
    print('=== TEST CICLO PRODUCTIVO (v6 + sub-WF Cancelar/Reprogramar) ===')
    print(f'phone Lucas: {LUCAS}')
    print(f'helper notify-grupo: REDIRECTED to Lucas (safety net)\n')

    results = {}
    results['A'] = ciclo_A_reprogramar_abierto()
    time.sleep(5)
    results['B'] = ciclo_B_multi_turn_fecha()
    time.sleep(5)
    results['C'] = ciclo_C_accept_slot()
    time.sleep(5)
    results['D'] = ciclo_D_cancelar_directo()

    print('\n=== RESUMEN ===')
    for k, v in results.items():
        print(f'  CICLO {k}: {"PASS" if v else "FAIL"}')
    print(f'\n  Pasaron {sum(results.values())}/{len(results)}')


if __name__ == '__main__':
    main()
