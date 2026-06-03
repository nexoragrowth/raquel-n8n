"""
Refactor arquitectural: separar READ (Sub-Agent General) de WRITE (sub-WF).

Modelo nuevo (propuesto por Lucas):
- PREGUNTA (signo ? o palabras interrogativas) -> SIEMPRE consulta_general.
  Sub-Agent General responde con info + invita a confirmar accion.
- AFIRMACION (sin pregunta) -> sub-WF Cancelar/Reprogramar ejecuta.

Cambios:
1. Router: mover "consulta info sobre turnos propios" de cancelar_o_reprogramar
   a consulta_general. Hacer explicita la regla: pregunta -> consulta_general.
2. Sub-Agent General prompt: agregar seccion "preguntas de capacidad" para
   responder "puedo X?" / "se puede X?" sin actuar.
3. Sub-WF Step 3.0: quitar el guard de pregunta del prompt (ya no recibe
   preguntas — el Router las desvia antes).
"""
import json
import re
import time
import urllib.request
from pathlib import Path

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
WID = re.search(r'N8N_WORKFLOW_V6_ID=([^\r\n]+)', open('.env').read()).group(1).strip()
SUB_WID = '5cAWJxiWJ50hxEq3'
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution','saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder','callerPolicy','callerIds'}


# === Router fix: pregunta -> consulta_general ===

OLD_ROUTER_BLOCK = '- Pregunta sobre cambio: "se puede cambiar?", "habria forma de pasarlo?", "puedo moverlo?".'

NEW_ROUTER_BLOCK = """- Pregunta sobre cambio: "se puede cambiar?", "habria forma de pasarlo?", "puedo moverlo?".

**IMPORTANTE**: este intent (cancelar_o_reprogramar) es SOLO para AFIRMACIONES claras de intencion de accion ("cancelo", "reprogramo", "lo paso para el [fecha]"). Cualquier mensaje con "?" o palabras interrogativas (puedo, podria, se puede, hay forma, cuando, que dia, etc) -> consulta_general (NO cancelar_o_reprogramar). El paciente tiene que afirmar sin pregunta para que ejecutemos accion."""

OLD_ROUTER_5 = """**5. consulta_general (fallback)**
Precios, direccion, horarios, alias bancario, info, preguntas generales. Tambien para cierres/agradecimientos cuando el bot ya escalo a la secretaria Irina."""

NEW_ROUTER_5 = """**5. consulta_general (fallback Y preguntas)**
- Precios, direccion, horarios, alias bancario, info general de la clinica.
- TODAS las PREGUNTAS sobre turnos propios del paciente: "tengo turno?", "cuando es mi turno?", "que dia tengo?", "a que hora?", "tengo turno manana?", "es presencial?", "mi turno es el [fecha]?", "que turno tengo?".
- TODAS las PREGUNTAS de capacidad: "puedo cancelar?", "se puede mover?", "podria reprogramar?", "hay forma de cambiarlo?", "puedo agendar?".
- Preguntas generales sobre tratamientos / FAQ.
- Cierres / agradecimientos / mensajes post-escalacion.

El Sub-Agent General tiene tools de LECTURA (ver_turnos_paciente, buscar_conocimiento, obtener_historial_paciente). Para preguntas que requieren accion, responde confirmando capacidad e invita al paciente a afirmar sin pregunta."""


# === Sub-Agent General prompt: agregar regla preguntas de capacidad ===

OLD_SAG_RULES = """REGLAS:
- NO inventar precios. NO inventar horarios. NO inventar disponibilidad. Si no esta en INFO CANNED -> escalar.
- NO mencionar obras sociales como "no las tomamos" / "no las aceptamos". Eso lo maneja Iri.
- NO dar opiniones sobre tratamientos ("es lo mejor", "te conviene", "duele poco")."""

NEW_SAG_RULES = """REGLAS:
- NO inventar precios. NO inventar horarios. NO inventar disponibilidad. Si no esta en INFO CANNED -> escalar.
- NO mencionar obras sociales como "no las tomamos" / "no las aceptamos". Eso lo maneja Iri.
- NO dar opiniones sobre tratamientos ("es lo mejor", "te conviene", "duele poco").

**PREGUNTAS SOBRE TURNOS PROPIOS** (paciente pregunta sobre SU turno):
Si el paciente pregunta "tengo turno?" / "cuando es?" / "tengo turno el [fecha]?" / "que turno tengo?":
- Llamar `ver_turnos_paciente` con paciente_id_dentalink del contexto.
- Responder con info real del turno (fecha natural + hora natural).
- Si no tiene turnos activos, decir "Por el momento no tenes turnos activos. Si queres agendar uno avisame."
- NO ejecutes accion. Solo informas.

**PREGUNTAS DE CAPACIDAD** (paciente pregunta "puedo X?" / "se puede X?"):
Si el paciente pregunta "puedo cancelar?" / "se puede mover el turno?" / "podria reprogramar?":
- Responder confirmando que SI se puede + invitar al paciente a tirar la accion sin pregunta para ejecutar.
- Ejemplos:
  - "puedo cancelar mi turno?" -> "Si, puedo cancelar tu turno del [fecha]. Si queres cancelarlo, decime 'cancelo' y lo proceso. O si preferis reprogramarlo decime 'lo paso a [otro dia]'."
  - "se puede mover?" -> "Si, podemos moverlo. Decime que dia o franja te viene mejor y te ofrezco horarios."
  - "puedo agendar un turno nuevo?" -> "Si, podes agendar. Decime que dia o franja preferis y te muestro disponibilidad."
- NUNCA ejecutes la accion en respuesta a la pregunta. Espera a que el paciente afirme sin pregunta.

REGLA ABSOLUTA SOBRE ACCIONES: El Sub-Agent General es de SOLO LECTURA. Nunca llama tools de Dentalink que modifican estado (cancelar/confirmar/reservar). Solo lee (ver_turnos_paciente, buscar_conocimiento, obtener_historial_paciente). Si el paciente AFIRMA sin pregunta que quiere accion ("cancelo", "confirmo", "agenda para el viernes"), el flow del Router lo dirige a otro sub-agent que ejecuta. Vos solo informas."""


# === Sub-WF Step 3.0: quitar el guard de pregunta (ya no llegan) ===

# El guard fue agregado con texto especifico. Lo identifico y removerlo.
GUARD_TEXT = 'REGLA ABSOLUTA ANTES DE TODO: Si el mensaje del paciente es una PREGUNTA (termina con ? o ¿, o empieza con: puedo, podria, podría, se puede, hay forma, habria, habría, cuando, cuándo, que dia, qué día, a que hora, a qué hora, donde, dónde, como, cómo, tengo turno) -> accion="consultar_info" SIEMPRE. NUNCA cancelar/reprogramar para preguntas. El paciente PREGUNTA si puede hacer X, NO te pide que lo hagas. Recien si el paciente afirma sin pregunta ("cancelo", "quiero cancelar", "cancela mi turno"), accion puede ser cancelar/reprogramar. '


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


# === Apply v6 changes ===
print('=== v6 patches ===')
wf = http('GET', f'/workflows/{WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/v6_PRE_SPLIT_READ_WRITE_{int(time.time())}.json').write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

router = next(n for n in wf['nodes'] if n['name'] == 'Router - Clasificar Intent')
sm = router['parameters']['options']['systemMessage']

if OLD_ROUTER_BLOCK not in sm:
    print('OLD_ROUTER_BLOCK not found'); raise SystemExit(1)
sm = sm.replace(OLD_ROUTER_BLOCK, NEW_ROUTER_BLOCK)
print('1. Router: bloque consulta info turnos REMOVIDO del cancelar_o_reprogramar')

if OLD_ROUTER_5 not in sm:
    print('OLD_ROUTER_5 not found'); raise SystemExit(1)
sm = sm.replace(OLD_ROUTER_5, NEW_ROUTER_5)
print('2. Router: bloque consulta_general AMPLIADO con preguntas + capacidad')

router['parameters']['options']['systemMessage'] = sm

# Sub-Agent General
sag = next(n for n in wf['nodes'] if n['name'] == 'Sub-Agent General')
sag_sm = sag['parameters']['options']['systemMessage']
if OLD_SAG_RULES not in sag_sm:
    print('OLD_SAG_RULES not found in Sub-Agent General prompt'); raise SystemExit(1)
sag['parameters']['options']['systemMessage'] = sag_sm.replace(OLD_SAG_RULES, NEW_SAG_RULES)
print('3. Sub-Agent General: agregada seccion preguntas turnos + capacidad + REGLA SOLO LECTURA')

safe = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED}
http('PUT', f'/workflows/{WID}', safe)
print('PUT v6 200')
Path(f'workflows/history/v6_POST_SPLIT_READ_WRITE_{int(time.time())}.json').write_text(json.dumps(http('GET', f'/workflows/{WID}'), indent=2, ensure_ascii=False), encoding='utf-8')

# === Sub-WF: remover guard pregunta ===
print('\n=== sub-WF patch ===')
swf = http('GET', f'/workflows/{SUB_WID}')
Path(f'workflows/history/subwf_PRE_SPLIT_READ_WRITE_{int(time.time())}.json').write_text(json.dumps(swf, indent=2, ensure_ascii=False), encoding='utf-8')

step3 = next(n for n in swf['nodes'] if n['name'] == 'Step 3.0: Prep LLM Body')
code = step3['parameters']['jsCode']
guard_escaped = GUARD_TEXT.replace('"', '\\"')
if guard_escaped in code:
    code = code.replace(guard_escaped, '')
    step3['parameters']['jsCode'] = code
    print('4. Sub-WF Step 3.0: guard de pregunta REMOVIDO (Router ya las desvia)')
else:
    print('4. Sub-WF Step 3.0: guard no encontrado exact (puede que ya este sin guard)')

safe_swf = {k: swf[k] for k in ('name','nodes','connections','settings') if k in swf}
http('PUT', f'/workflows/{SUB_WID}', safe_swf)
print('PUT sub-WF 200')
Path(f'workflows/history/subwf_POST_SPLIT_READ_WRITE_{int(time.time())}.json').write_text(json.dumps(http('GET', f'/workflows/{SUB_WID}'), indent=2, ensure_ascii=False), encoding='utf-8')

print('\nOK split read/write applied')
