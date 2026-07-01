"""
Fix 2026-06-22 (robustez): error tecnico (red/DNS/Dentalink caido) -> ESCALAR,
NO decir "no tenes turnos activos".

Caso real (Agustin Calisaya, 22/6 10:43): blip de DNS (getaddrinfo EAI_AGAIN) ->
buscar_paciente fallo -> id_paciente undefined -> ver-turnos reviento ("URL parameter
must be a string") -> el Sub-WF Cancelar respondio "No te encuentro turnos activos"
a un paciente que SI tiene cita hoy 15:00. Mentirle a un paciente con turno real es
lo mas grave (leccion #4: fallo silencioso tratado como dato vacio).

Causa: un error de transporte llega como {error:{...}} (continueOnFail), NO como
{data:[]}. Nada downstream lo distingue de "no encontrado" -> cae en el canned de
"no tenes turnos".

Fix (3 nodos, reusa la decision de escalado que YA existe en el anti-loop):
  - Step 1b: si lookupRaw es {error} -> {ok:false, step:'error_tecnico', tech_error:true}
  - Step 2b: si turnosRaw es {error} o Step 1b tuvo tech_error -> tech_error:true en output
  - Step 4 (top, antes del anti-loop): si tech_error -> decision escalar con canned tecnico
Deteccion validada offline 6/6 (distingue error de "sin turnos" genuino).

NO APLICADO por Claude (coordinar con Cogne en el mismo WF). Para aplicar:
  python scripts/apply_fix_cancelar_error_escalar.py
Backup pre/post + verificacion.
"""
import sys, json, datetime, urllib.request
sys.path.insert(0, 'scripts')
from lib_env import require

BASE = require('N8N_BASE_URL').rstrip('/')
KEY = require('N8N_API_KEY')
CWID = '5cAWJxiWJ50hxEq3'
TS = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution',
    'saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder',
    'callerPolicy','callerIds'}

def api(method, path, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = urllib.request.Request(BASE+path, data=data, method=method,
        headers={'X-N8N-API-KEY':KEY,'Content-Type':'application/json','Accept':'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=120))

# ---- Edit 1: Step 1b — detectar error de transporte ----
S1B_ANCHOR = "const trigger = $('Step 1.0: Prep Query').first().json.trigger;"
S1B_INSERT = S1B_ANCHOR + """
// Fix 2026-06-22: error de transporte (red/DNS/HTTP) llega como {error:{...}} (continueOnFail),
// NO como {data:[]}. Distinguirlo de "no encontrado" para poder escalar en vez de mentir.
const __err1 = Array.isArray(lookupRaw) ? (lookupRaw[0] && lookupRaw[0].error) : (lookupRaw && lookupRaw.error);
if (__err1) {
  return [{ json: { ok:false, step:'error_tecnico', tech_error:true, raw:lookupRaw, trigger } }];
}"""

# ---- Edit 2: Step 2b — propagar tech_error ----
S2B_ANCHOR = "const trigger = $('Step 1b: Procesar resultado').first().json.trigger;"
S2B_INSERT = S2B_ANCHOR + """
// Fix 2026-06-22: error tecnico en ver-turnos (o heredado de Step 1b) -> flag para escalar.
const __err2 = Array.isArray(turnosRaw) ? (turnosRaw[0] && turnosRaw[0].error) : (turnosRaw && turnosRaw.error);
const __tech2b = !!__err2 || ($('Step 1b: Procesar resultado').first().json.tech_error === true);"""
S2B_RET_ANCHOR = "return [{ json: {\n  ok: proximos.length > 0,"
S2B_RET_INSERT = "return [{ json: {\n  tech_error: __tech2b,\n  ok: proximos.length > 0,"

# ---- Edit 3: Step 4 — al tope, escalar si error tecnico ----
S4_ANCHOR = "const turnos = prev.turnos_proximos || [];"
S4_INSERT = S4_ANCHOR + """

// Fix 2026-06-22 (robustez, caso Agustin): si hubo error tecnico en lookup/ver-turnos
// (red/DNS/Dentalink caido), NO decir "no tenes turnos" (mentira a un paciente con turno real).
// Escalar a la secretaria. Reusa el shape de decision del anti-loop (probado en prod).
let __techErr = false;
try { if ($('Step 1b: Procesar resultado').first().json.tech_error === true) __techErr = true; } catch(e){}
try { if ($('Step 2b: Filtrar Turnos Proximos').first().json.tech_error === true) __techErr = true; } catch(e){}
if (__techErr) {
  return [{ json: { ...prev, decision: {
    siguiente_paso: 'escalar',
    razon: 'error_tecnico_dentalink',
    canned: 'Disculpe, tuve un inconveniente tecnico para acceder a la agenda en este momento. Le paso a la secretaria, que la coordina en su horario de atencion (Lun y Mie 15 a 20 hs / Mar, Jue y Vie 8 a 13 hs).'
  } }}];
}"""

def main():
    wf = api('GET', f'/api/v1/workflows/{CWID}')
    nodes = wf['nodes']
    def node(n): return next(x for x in nodes if x['name'] == n)
    s1b = node('Step 1b: Procesar resultado'); c1 = s1b['parameters']['jsCode']
    s2b = node('Step 2b: Filtrar Turnos Proximos'); c2 = s2b['parameters']['jsCode']
    s4 = node('Step 4: Identificar Turno + Decision'); c4 = s4['parameters']['jsCode']

    if all('Fix 2026-06-22' in c and 'error_tecnico' in c for c in [c1]) and 'tech_error' in c2 and 'error_tecnico_dentalink' in c4:
        print('Ya aplicado (idempotente).'); return

    # asserts de anchors
    assert c1.count(S1B_ANCHOR) == 1, 'S1B anchor'
    assert c2.count(S2B_ANCHOR) == 1, 'S2B anchor'
    assert c2.count(S2B_RET_ANCHOR) == 1, f'S2B return anchor ({c2.count(S2B_RET_ANCHOR)})'
    assert c4.count(S4_ANCHOR) == 1, 'S4 anchor'

    # backup pre
    pre = f'workflows/history/subwf_cancelar_PRE_ERROR_ESCALAR_{TS}.json'
    json.dump(wf, open(pre,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('backup pre ->', pre)

    s1b['parameters']['jsCode'] = c1.replace(S1B_ANCHOR, S1B_INSERT, 1)
    s2b['parameters']['jsCode'] = c2.replace(S2B_ANCHOR, S2B_INSERT, 1).replace(S2B_RET_ANCHOR, S2B_RET_INSERT, 1)
    s4['parameters']['jsCode'] = c4.replace(S4_ANCHOR, S4_INSERT, 1)

    settings = {k:v for k,v in (wf.get('settings') or {}).items() if k in ALLOWED}
    payload = {'name': wf['name'], 'nodes': nodes, 'connections': wf['connections'], 'settings': settings}
    if wf.get('staticData') is not None:
        payload['staticData'] = wf['staticData']
    api('PUT', f'/api/v1/workflows/{CWID}', payload)
    print('PUT OK')

    wf2 = api('GET', f'/api/v1/workflows/{CWID}')
    post = f'workflows/history/subwf_cancelar_POST_ERROR_ESCALAR_{TS}.json'
    json.dump(wf2, open(post,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('backup post ->', post)
    def gc(n): return next(x for x in wf2['nodes'] if x['name']==n)['parameters']['jsCode']
    print('VERIFICACION:')
    print('  Step 1b tech_error:', "step:'error_tecnico'" in gc('Step 1b: Procesar resultado'))
    print('  Step 2b tech_error:', 'tech_error: __tech2b' in gc('Step 2b: Filtrar Turnos Proximos'))
    print('  Step 4 escalar:', 'error_tecnico_dentalink' in gc('Step 4: Identificar Turno + Decision'))
    print('  nodos:', len(wf2['nodes']), '| active:', wf2.get('active'))

if __name__ == '__main__':
    main()
