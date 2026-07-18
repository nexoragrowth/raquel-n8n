"""
Test ciclo productivo v2 — usa subprocess de probar_bot_e2e.py que sabemos que anda.

Cubre paths criticos del sub-WF CancelarReprogramar:
- A: reprogramar abierto (sin fecha)
- B: respuesta con fecha (multi-turn)
- C: aceptar slot ofrecido
- D: cancelar directo
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
DT_CRED = 'TwN6eBWsydjMdsCM'


def run_msg(text):
    """Send message via probar_bot_e2e.py and return final bot reply."""
    proc = subprocess.run([sys.executable, 'scripts/probar_bot_e2e.py', text],
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=180)
    out = proc.stdout or ''
    # Parse "MENSAJE QUE LE LLEGA AL PACIENTE:" section
    m = re.search(r'MENSAJE QUE LE LLEGA AL PACIENTE:\s*\n\s*(.+?)(?:\n\n|\Z)', out, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def assert_match(label, msg, pattern):
    ok = bool(re.search(pattern, msg or '', re.IGNORECASE))
    mark = 'PASS' if ok else 'FAIL'
    print(f'  [{mark}] {label}')
    print(f'      msg: {msg!r}')
    if not ok:
        print(f'      expected: {pattern!r}')
    return ok


def temp_dentalink(method, url, body=None, name='dt'):
    wh = f'tmp-{name}-' + str(int(time.time()))
    node_http = {
        'method': method, 'url': url,
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpHeaderAuth',
        'options': {}
    }
    if body is not None:
        node_http.update({'sendBody': True, 'specifyBody': 'json', 'jsonBody': json.dumps(body)})
    wf = {
        'name': f'TMP-{name}',
        'nodes': [
            {'parameters':{'httpMethod':'POST','path':wh,'responseMode':'lastNode','options':{}},
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
    r = urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows', method='POST',
        headers=HEADERS, data=json.dumps(wf).encode()), timeout=30)
    WID = json.loads(r.read())['id']
    urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID}/activate', method='POST', headers=HEADERS), timeout=20)
    time.sleep(2)
    try:
        resp = urllib.request.urlopen(urllib.request.Request(
            f'https://n8n.raquelrodriguez.com.ar/webhook/{wh}', method='POST',
            headers={'Content-Type':'application/json'}, data=b'{}'), timeout=30)
        return json.loads(resp.read().decode())
    finally:
        urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID}/deactivate', method='POST', headers=HEADERS), timeout=15)
        urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID}', method='DELETE', headers=HEADERS), timeout=15)


def get_active_citas():
    today = time.strftime('%Y-%m-%d')
    res = temp_dentalink('GET', 'https://api.dentalink.healthatom.com/api/v1/pacientes/608/citas', name='list')
    if not isinstance(res, dict) or 'data' not in res:
        return []
    return [c for c in res['data'] if c.get('id_estado') not in (1,) and c.get('fecha', '0000') >= today]


def reservar(fecha, hora='11:00'):
    return temp_dentalink('POST', 'https://api.dentalink.healthatom.com/api/v1/citas/',
        body={'id_dentista':1,'id_sucursal':1,'id_sillon':1,'id_paciente':608,
              'fecha':fecha,'hora_inicio':hora,'duracion':40,'comentario':'TEST ciclo v2'},
        name='res')


def ensure_cita(fallback_fecha='2026-06-12'):
    actives = get_active_citas()
    if actives:
        c = sorted(actives, key=lambda x: (x['fecha'], x['hora_inicio']))[0]
        print(f'  cita activa: id={c["id"]} {c["fecha"]} {c["hora_inicio"]}')
        return c
    print(f'  no hay cita activa, reservando base {fallback_fecha} 11:00')
    r = reservar(fallback_fecha, '11:00')
    if isinstance(r, dict):
        d = r.get('data', r)
        print(f'  reservada id={d.get("id")}')
        return d
    return None


def main():
    print('=== TEST CICLO PRODUCTIVO V2 ===\n')

    results = []

    # CICLO A: reprogramar abierto
    print('CICLO A: "podemos pasarlo a otro dia?"')
    cita = ensure_cita()
    if not cita: print('  SKIP — no cita'); results.append(('A', False)); return
    msg = run_msg('podemos pasarlo a otro dia?')
    results.append(('A', assert_match('bot pregunta dia', msg, r'qu[eé] d[ií]a|franja|viene mejor')))
    time.sleep(3)

    # CICLO B: multi-turn fecha
    print('\nCICLO B: "el viernes 19 de junio"')
    msg = run_msg('el viernes 19 de junio')
    results.append(('B', assert_match('bot ofrece slots', msg, r'tengo disponible|cu[aá]l confirma')))
    time.sleep(3)

    # CICLO C: aceptar slot
    print('\nCICLO C: "el primero"')
    msg = run_msg('el primero')
    results.append(('C', assert_match('bot confirma reprogramado', msg, r'reprogramad|te reserv|cancel.*reserv')))
    time.sleep(3)

    # CICLO D: cancelar directo
    print('\nCICLO D: "cancelo el [fecha activa]"')
    cita2 = ensure_cita()
    if cita2:
        msg = run_msg(f'cancelo el {cita2["fecha"]}')
        results.append(('D', assert_match('bot confirma cancelacion', msg, r'cancelad|queda cancelad|listo')))
    else:
        results.append(('D', False))

    print('\n=== RESUMEN ===')
    for k, v in results:
        print(f'  CICLO {k}: {"PASS" if v else "FAIL"}')
    print(f'\n  {sum(v for _,v in results)}/{len(results)} PASS')


if __name__ == '__main__':
    main()
