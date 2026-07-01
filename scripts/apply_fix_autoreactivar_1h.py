"""
Fix 2026-06-24 (pedido Dra Raquel): bajar el auto-reactivar del bot de 4h -> 1h.

Contexto: Round 9 (9/6) lo subio de 1h a 4h a pedido de Iri (secretaria). La doctora
ahora pide volverlo a 1h: con 4h el agente queda mudo demasiado tiempo cada vez que un
humano toca un chat -> poco "protagonismo". Riesgo bajo porque:
  - El auto-reactivar es por INACTIVIDAD (resetea con cada mensaje), no cutoff fijo:
    nunca pisa una conversacion humana ACTIVA, solo reactiva tras silencio total 1h.
  - La proteccion anti-pisada real son los gates deterministas del Round 9 (re-check +
    Gate Humano Final), que el timer NO toca.
  - El label `no_bot` sigue siendo override manual de Iri (el codigo lo saltea): chat con
    no_bot -> el bot no lo reactiva nunca, sin importar el timer.

Cambio: en el nodo "Filtrar > 1 hora inactivas", FOUR_HOURS (4*3600) -> ONE_HOUR (1*3600).
Autorizado por Lucas ("metele"). Backup pre/post + verificacion.
"""
import sys, json, datetime, urllib.request
sys.path.insert(0, 'scripts')
from lib_env import require

BASE = require('N8N_BASE_URL').rstrip('/')
KEY = require('N8N_API_KEY')
WID = 'fosfga62zNaN0qrx'   # Auto Reactivar Bot
TS = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution',
    'saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder',
    'callerPolicy','callerIds'}

def api(method, path, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(BASE+path, data=data, method=method,
        headers={'X-N8N-API-KEY':KEY,'Content-Type':'application/json','Accept':'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=120))

OLD_DECL = 'const FOUR_HOURS = 4 * 3600; // 2026-06-09: takeover 1h -> 4h'
NEW_DECL = 'const ONE_HOUR = 1 * 3600; // 2026-06-24: takeover 4h -> 1h (pedido Dra; gates R9 + label no_bot cubren anti-pisada)'
OLD_USE = 'secondsSinceActivity > FOUR_HOURS'
NEW_USE = 'secondsSinceActivity > ONE_HOUR'

def main():
    wf = api('GET', f'/api/v1/workflows/{WID}')
    node = next(n for n in wf['nodes'] if n['name'] == 'Filtrar > 1 hora inactivas')
    code = node['parameters']['jsCode']

    if 'ONE_HOUR' in code:
        print('Ya en 1h (idempotente). Nada que hacer.'); return
    assert code.count(OLD_DECL) == 1, f'decl anchor count={code.count(OLD_DECL)}'
    assert code.count(OLD_USE) == 1, f'use anchor count={code.count(OLD_USE)}'

    pre = f'workflows/history/autoreactivar_PRE_1H_{TS}.json'
    json.dump(wf, open(pre,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('backup pre ->', pre)

    node['parameters']['jsCode'] = code.replace(OLD_DECL, NEW_DECL, 1).replace(OLD_USE, NEW_USE, 1)

    settings = {k:v for k,v in (wf.get('settings') or {}).items() if k in ALLOWED}
    payload = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'], 'settings': settings}
    if wf.get('staticData') is not None:
        payload['staticData'] = wf['staticData']
    api('PUT', f'/api/v1/workflows/{WID}', payload)
    print('PUT OK')

    wf2 = api('GET', f'/api/v1/workflows/{WID}')
    post = f'workflows/history/autoreactivar_POST_1H_{TS}.json'
    json.dump(wf2, open(post,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('backup post ->', post)
    c2 = next(n for n in wf2['nodes'] if n['name']=='Filtrar > 1 hora inactivas')['parameters']['jsCode']
    print('VERIFICACION:')
    print('  ONE_HOUR presente:', 'const ONE_HOUR = 1 * 3600' in c2)
    print('  FOUR_HOURS eliminado:', 'FOUR_HOURS' not in c2)
    print('  usa > ONE_HOUR:', 'secondsSinceActivity > ONE_HOUR' in c2)
    print('  active:', wf2.get('active'), '| nodos:', len(wf2['nodes']))
    if wf2.get('active') is not True:
        print('  [!] OJO: quedó inactivo -> reactivando...')
        api('POST', f'/api/v1/workflows/{WID}/activate')
        print('  reactivado:', api('GET', f'/api/v1/workflows/{WID}').get('active'))

if __name__ == '__main__':
    main()
