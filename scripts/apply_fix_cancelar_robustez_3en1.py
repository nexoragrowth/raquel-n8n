"""
Fix 2026-07-01 (autorizado Lucas "si hay que arreglar algo que sea ya", se va a Italia):
3 fixes al Sub-WF CancelarReprogramar en UN solo PUT atomico (menos ventana de
conflicto con Cogne). Backup pre/post + verificacion. Auto-test offline de la
logica multi-fichas antes de tocar prod (si falla, aborta sin PUT).

FIX A — multi-fichas turno_objetivo (el mas impactante, caso Luis Augusto 1/7):
  Cuando el paciente desambigua por DNI/contexto, Step 4 resuelve la ficha pero
  devolvia decision:null SIN setear turno_objetivo -> Step 5 (const turno=prev.turno_objetivo)
  ve vacio -> escala "No veo turno activo" con "sin razon", aun teniendo turno valido.
  Fix: helper __pickTurno engancha el turno de forma CONSERVADORA (solo si los turnos
  ya fetcheados pertenecen a la ficha resuelta; exige match de fecha si el paciente la
  menciono; si no puede con seguridad -> escala CON razon clara). Cero riesgo de
  reprogramar el turno equivocado.

FIX B — error tecnico -> escalar (Steps 1b/2b/4): error de red/DNS deja de traducirse
  en "no tenes turnos". Validado 6/6.

FIX C — identidad Asiri (Step 7): el Cancelar se presenta como asistente virtual en
  primer contacto / saludo / post-recordatorio / post-humano. Validado 7/7.
"""
import sys, json, datetime, urllib.request, re
sys.path.insert(0, 'scripts')
from lib_env import require

BASE = require('N8N_BASE_URL').rstrip('/'); KEY = require('N8N_API_KEY')
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

# ===== FIX A: multi-fichas =====
PICK_DEF = """const pacientesAll = step1b.pacientes_all || [];
  // FIX 2026-07-01: tras resolver ficha (DNI/contexto) enganchar el turno para NO dead-endear.
  // Conservador: solo si los turnos ya fetcheados pertenecen a la ficha resuelta
  // (turnos_proximos se traen para pacientesAll[0]); exige match de fecha si el paciente la menciono.
  const __pickTurno = (rid) => {
    try {
      if (!(pacientesAll[0] && pacientesAll[0].id === rid)) return null;
      const tp = prev.turnos_proximos || [];
      if (!tp.length) return null;
      const fm = (intent && intent.fecha_actual_mencionada) || null;
      if (fm) return tp.find(t => t.fecha === fm) || null;
      return tp.length === 1 ? tp[0] : null;
    } catch (e) { return null; }
  };"""
DNI_OLD = "return [{ json: { ...prev, paciente_resuelto: byDni[0], paciente: byDni[0], multi_fichas_resolved_by: 'dni_match', decision: null } }];"
DNI_NEW = "return [{ json: { ...prev, paciente_resuelto: byDni[0], paciente: byDni[0], turno_objetivo: __pickTurno(byDni[0].id), multi_fichas_resolved_by: 'dni_match', decision: __pickTurno(byDni[0].id) ? null : { siguiente_paso: 'escalar', razon: 'reprograma: identificado por DNI pero no se pudo enganchar el turno (coordinar a mano)', canned: 'Le paso a la secretaria para coordinar su reprogramacion.' } } }];"
CTX_OLD = "      multi_fichas_resolved_by: 'context_match',\n      decision: null,"
CTX_NEW = "      turno_objetivo: __pickTurno(matched[0].id),\n      multi_fichas_resolved_by: 'context_match',\n      decision: __pickTurno(matched[0].id) ? null : { siguiente_paso: 'escalar', razon: 'reprograma: identificado por contexto pero no se pudo enganchar el turno (coordinar a mano)', canned: 'Le paso a la secretaria para coordinar su reprogramacion.' },"

# ===== FIX B: error -> escalar =====
S1B_ANCHOR = "const trigger = $('Step 1.0: Prep Query').first().json.trigger;"
S1B_INSERT = S1B_ANCHOR + """
const __err1 = Array.isArray(lookupRaw) ? (lookupRaw[0] && lookupRaw[0].error) : (lookupRaw && lookupRaw.error);
if (__err1) { return [{ json: { ok:false, step:'error_tecnico', tech_error:true, raw:lookupRaw, trigger } }]; }"""
S2B_ANCHOR = "const trigger = $('Step 1b: Procesar resultado').first().json.trigger;"
S2B_INSERT = S2B_ANCHOR + """
const __err2 = Array.isArray(turnosRaw) ? (turnosRaw[0] && turnosRaw[0].error) : (turnosRaw && turnosRaw.error);
const __tech2b = !!__err2 || ($('Step 1b: Procesar resultado').first().json.tech_error === true);"""
S2B_RET_OLD = "return [{ json: {\n  ok: proximos.length > 0,"
S2B_RET_NEW = "return [{ json: {\n  tech_error: __tech2b,\n  ok: proximos.length > 0,"
S4_TECH_ANCHOR = "const turnos = prev.turnos_proximos || [];"
S4_TECH_INSERT = S4_TECH_ANCHOR + """

// FIX 2026-07-01: error tecnico en lookup/ver-turnos -> escalar (no mentir "no tenes turnos").
let __techErr = false;
try { if ($('Step 1b: Procesar resultado').first().json.tech_error === true) __techErr = true; } catch(e){}
try { if ($('Step 2b: Filtrar Turnos Proximos').first().json.tech_error === true) __techErr = true; } catch(e){}
if (__techErr) {
  return [{ json: { ...prev, decision: {
    siguiente_paso: 'escalar', razon: 'error_tecnico_dentalink',
    canned: 'Disculpe, tuve un inconveniente tecnico para acceder a la agenda en este momento. Le paso a la secretaria, que la coordina en su horario de atencion (Lun y Mie 15 a 20 hs / Mar, Jue y Vie 8 a 13 hs).'
  } }}];
}"""

# ===== FIX C: identidad Asiri (Step 7) =====
ID_BLOCK = """const __trg = prev.trigger || fromStep5.trigger || {};
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

def offline_test_pickturno():
    # replica en python de __pickTurno sobre el caso real + edge cases
    def pick(pacientesAll, turnos_proximos, fm, rid):
        if not (pacientesAll and pacientesAll[0].get('id') == rid): return None
        tp = turnos_proximos or []
        if not tp: return None
        if fm: return next((t for t in tp if t.get('fecha')==fm), None)
        return tp[0] if len(tp)==1 else None
    pa=[{'id':298},{'id':246}]; tp=[{'id':8163,'fecha':'2026-07-03'}]
    assert pick(pa, tp, '2026-07-03', 298) == tp[0], 'caso real: debe enganchar 8163'
    assert pick(pa, tp, '2026-07-03', 246) is None, 'ficha != data[0]: no engancha'
    assert pick(pa, tp, '2026-07-09', 298) is None, 'fecha mencionada sin match: no engancha (escala)'
    assert pick(pa, tp, None, 298) == tp[0], 'sin fecha + 1 turno: engancha'
    assert pick(pa, [{'id':1,'fecha':'x'},{'id':2,'fecha':'y'}], None, 298) is None, 'sin fecha + 2 turnos: no engancha'
    assert pick(pa, [], None, 298) is None, 'sin turnos: no engancha'
    print('  [offline] __pickTurno 6/6 OK')

def main():
    offline_test_pickturno()
    wf = api('GET', f'/api/v1/workflows/{CWID}')
    def node(n): return next(x for x in wf['nodes'] if x['name'] == n)
    c1 = node('Step 1b: Procesar resultado')['parameters']['jsCode']
    c2 = node('Step 2b: Filtrar Turnos Proximos')['parameters']['jsCode']
    c4 = node('Step 4: Identificar Turno + Decision')['parameters']['jsCode']
    c7 = node('Step 7: Output Final')['parameters']['jsCode']

    if 'turno_objetivo: __pickTurno' in c4 and 'error_tecnico' in c1 and 'mfFinal' in c7:
        print('Ya aplicado (idempotente).'); return

    # asserts de anchors (todos deben existir 1 vez)
    for txt, code, name in [
        (DNI_OLD, c4, 'DNI'), (CTX_OLD, c4, 'CTX'), ('const pacientesAll = step1b.pacientes_all || [];', c4, 'pacientesAll'),
        (S4_TECH_ANCHOR, c4, 'S4tech'), (S1B_ANCHOR, c1, 'S1B'), (S2B_ANCHOR, c2, 'S2B'),
        (S2B_RET_OLD, c2, 'S2Bret'), ('mensaje_final: mf,', c7, 'S7mf'), ('return [{ json: {', c7, 'S7ret')]:
        assert code.count(txt) == 1, f'anchor {name} count={code.count(txt)}'

    pre = f'workflows/history/subwf_cancelar_PRE_ROBUSTEZ3_{TS}.json'
    json.dump(wf, open(pre,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('backup pre ->', pre)

    # Step 1b
    node('Step 1b: Procesar resultado')['parameters']['jsCode'] = c1.replace(S1B_ANCHOR, S1B_INSERT, 1)
    # Step 2b
    node('Step 2b: Filtrar Turnos Proximos')['parameters']['jsCode'] = c2.replace(S2B_ANCHOR, S2B_INSERT, 1).replace(S2B_RET_OLD, S2B_RET_NEW, 1)
    # Step 4: tech-error (top) + pickTurno def + DNI + CTX
    c4n = (c4.replace(S4_TECH_ANCHOR, S4_TECH_INSERT, 1)
             .replace('const pacientesAll = step1b.pacientes_all || [];', PICK_DEF, 1)
             .replace(DNI_OLD, DNI_NEW, 1)
             .replace(CTX_OLD, CTX_NEW, 1))
    node('Step 4: Identificar Turno + Decision')['parameters']['jsCode'] = c4n
    # Step 7: identidad
    node('Step 7: Output Final')['parameters']['jsCode'] = c7.replace('return [{ json: {', ID_BLOCK + 'return [{ json: {', 1).replace('mensaje_final: mf,', 'mensaje_final: mfFinal,', 1)

    settings = {k:v for k,v in (wf.get('settings') or {}).items() if k in ALLOWED}
    payload = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'], 'settings': settings}
    if wf.get('staticData') is not None: payload['staticData'] = wf['staticData']
    api('PUT', f'/api/v1/workflows/{CWID}', payload)
    print('PUT OK')

    wf2 = api('GET', f'/api/v1/workflows/{CWID}')
    post = f'workflows/history/subwf_cancelar_POST_ROBUSTEZ3_{TS}.json'
    json.dump(wf2, open(post,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('backup post ->', post)
    def gc(n): return next(x for x in wf2['nodes'] if x['name']==n)['parameters']['jsCode']
    checks = {
      'A multi-fichas (Step4 pickTurno)': 'turno_objetivo: __pickTurno' in gc('Step 4: Identificar Turno + Decision'),
      'A DNI branch': "turno_objetivo: __pickTurno(byDni[0].id)" in gc('Step 4: Identificar Turno + Decision'),
      'B error->escalar (1b)': "step:'error_tecnico'" in gc('Step 1b: Procesar resultado'),
      'B error->escalar (2b)': 'tech_error: __tech2b' in gc('Step 2b: Filtrar Turnos Proximos'),
      'B error->escalar (4)': 'error_tecnico_dentalink' in gc('Step 4: Identificar Turno + Decision'),
      'C identidad Asiri (7)': 'mfFinal' in gc('Step 7: Output Final'),
    }
    print('VERIFICACION:')
    for k,v in checks.items(): print(f'  [{"OK" if v else "XX"}] {k}')
    print('  nodos:', len(wf2['nodes']), '| active:', wf2.get('active'))
    print('\n', 'TODO OK' if all(checks.values()) else 'XX ALGO FALLO')

if __name__ == '__main__':
    main()
