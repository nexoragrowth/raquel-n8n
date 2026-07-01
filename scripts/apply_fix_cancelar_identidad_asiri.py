"""
Fix 2026-06-22 (pedido recurrente Dra): el Sub-WF Cancelar (codigo deterministico)
NUNCA se presenta como Asiri. Es el flujo que mas confunde (cancel/reprogram/
"no tenes turnos"/read-backs de fecha) -> pacientes le dicen "que te fumaste" a la
secretaria HUMANA creyendo que es ella la que manda mensajes fuera de contexto.
(Casos: Catalina "Vi su turno del Viernes 19... cancelar o reprogramar?" / Agustin
"No te encuentro turnos activos...").

Causa: la regla de IDENTIFICACION vive solo en los sub-agents LLM (Confirmar/General).
El Cancelar es codigo y sus canned no incluyen identificacion (grep: 0 menciones de
"Asiri"/"asistente virtual"/"secretaria virtual").

Fix: en Step 7 (Output Final, unico chokepoint de mensaje_final), anteponer la
identificacion de Asiri SOLO cuando corresponde: saludo del paciente / post-recordatorio
/ post-humano / primer contacto. En continuaciones (el bot ya venia hablando) NO re-presenta.
Logica validada offline 7/7.

NO APLICADO TODAVIA por Claude (coordinar con Cogne que mete mano en el mismo WF).
Para aplicar: python scripts/apply_fix_cancelar_identidad_asiri.py
Backup pre/post + verificacion. PUT solo keys permitidas.
"""
import sys, json, datetime, urllib.request
sys.path.insert(0, 'scripts')
from lib_env import require

BASE = require('N8N_BASE_URL').rstrip('/')
KEY = require('N8N_API_KEY')
CWID = '5cAWJxiWJ50hxEq3'   # Sub-WF - CancelarReprogramar
TS = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution',
    'saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder',
    'callerPolicy','callerIds'}

def api(method, path, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(BASE+path, data=data, method=method,
        headers={'X-N8N-API-KEY':KEY,'Content-Type':'application/json','Accept':'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=120))

# Bloque de identificacion a insertar ANTES del `return [{ json: {` en Step 7.
ID_BLOCK = """// --- Identificacion Asiri (fix 2026-06-22, pedido recurrente Dra) ---
// El Cancelar es el flujo que mas confunde y nunca se presentaba -> pacientes le
// decian "que te fumaste" a la secretaria humana. Presentarse en primer contacto /
// saludo / post-recordatorio / post-humano; en continuaciones, ir directo.
const __trg = prev.trigger || fromStep5.trigger || {};
const __lastBot = String(__trg.last_bot_msg || '').trim();
const __pMsg = String(__trg.text || '').toLowerCase();
const __isGreeting = /(^|\\s)(hola+|buen[ao]s|buen dia|buenos dias|buenas tardes|buenas noches)(\\s|$|,|\\.|!)/.test(__pMsg);
const __lastReminder = /^\\s*aurea|recordamos su turno|le recordamos/i.test(__lastBot);
const __lastHumanOrEmpty = !__lastBot || /^\\[atencion humana/i.test(__lastBot);
const __shouldIdentify = __isGreeting || __lastReminder || __lastHumanOrEmpty;
const mfFinal = (__shouldIdentify && !/asiri/i.test(mf))
  ? 'Soy Asiri, la secretaria virtual de la Dra. Raquel \\ud83e\\udd17\\n\\n' + mf
  : mf;

"""

def main():
    wf = api('GET', f'/api/v1/workflows/{CWID}')
    nodes = wf['nodes']
    step7 = next(n for n in nodes if n['name'] == 'Step 7: Output Final')
    code = step7['parameters']['jsCode']

    if 'mfFinal' in code or 'Identificacion Asiri' in code:
        print('Ya aplicado (idempotente). Nada que hacer.'); return

    # backup pre
    pre = f'workflows/history/subwf_cancelar_PRE_IDENTIDAD_ASIRI_{TS}.json'
    json.dump(wf, open(pre,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('backup pre ->', pre)

    anchor_ret = 'return [{ json: {'
    anchor_mf = 'mensaje_final: mf,'
    assert code.count(anchor_ret) == 1, f'anchor return count={code.count(anchor_ret)}'
    assert code.count(anchor_mf) == 1, f'anchor mf count={code.count(anchor_mf)}'
    new_code = code.replace(anchor_ret, ID_BLOCK + anchor_ret, 1).replace(anchor_mf, 'mensaje_final: mfFinal,', 1)
    step7['parameters']['jsCode'] = new_code

    settings = {k:v for k,v in (wf.get('settings') or {}).items() if k in ALLOWED}
    payload = {'name': wf['name'], 'nodes': nodes, 'connections': wf['connections'], 'settings': settings}
    if wf.get('staticData') is not None:
        payload['staticData'] = wf['staticData']
    api('PUT', f'/api/v1/workflows/{CWID}', payload)
    print('PUT OK')

    wf2 = api('GET', f'/api/v1/workflows/{CWID}')
    post = f'workflows/history/subwf_cancelar_POST_IDENTIDAD_ASIRI_{TS}.json'
    json.dump(wf2, open(post,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('backup post ->', post)
    c2 = next(n for n in wf2['nodes'] if n['name']=='Step 7: Output Final')['parameters']['jsCode']
    print('VERIFICACION:')
    print('  mfFinal presente:', 'mfFinal' in c2)
    print('  prepend Asiri presente:', 'secretaria virtual de la Dra. Raquel' in c2)
    print('  nodos:', len(wf2['nodes']), '| active:', wf2.get('active'))

if __name__ == '__main__':
    main()
