"""
v6 Patch: reforzar Sub-Agent General para que SIEMPRE consulte buscar_conocimiento
antes de escalar en preguntas sobre tratamientos/dudas/cuidado.

Problema observado (test 'puedo hacer deporte con brackets?'):
- KB tiene la respuesta exacta como FAQ
- Sub-Agent General escaló sin llamar buscar_conocimiento
- LLM ignoró la regla "NUNCA responder sobre tratamientos sin consultar buscar_conocimiento primero"

Fix: inyectar al inicio del systemMessage un bloque OBLIGATORIO con ejemplos
concretos de queries que requieren KB antes de escalar.

Riesgo: bajo. Solo amplía la cobertura de KB lookups. Si KB no tiene info,
escala igual (regla actual). No introduce nuevos paths ni cambia tools.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
WID = re.search(r'N8N_WORKFLOW_V6_ID=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}

ALLOWED_SETTINGS = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution',
    'saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone',
    'executionOrder','callerPolicy','callerIds'}

# Patron pivot: ubicar el bloque "**ORDEN DE DECISION**" y reemplazar las 3 reglas
OLD_ORDEN = (
    "**ORDEN DE DECISION** (seguir SIEMPRE):\n"
    "\n"
    "1. ¿La pregunta encaja en INFO CANNED de abajo? → responder LITERAL del canned.\n"
    "\n"
    "2. Si NO, ¿es pregunta sobre la clinica/tratamientos/FAQ general? \n"
    "   → llamar `buscar_conocimiento` con la pregunta del paciente.\n"
    "   - Si retorna docs relevantes → responder con esa info (max 2-3 oraciones, \n"
    "     LITERAL de los docs, NO inventar)\n"
    "   - Si retorna [] o irrelevante → escalar.\n"
    "\n"
    "3. Si la pregunta es queja/hostilidad/urgencia/factura/disponibilidad/\n"
    "   personal → escalar directo (NO consultar KB para estos casos).\n"
    "\n"
    "NUNCA responder sobre tratamientos sin consultar `buscar_conocimiento` primero.\n"
    "NUNCA inventar info. Si la KB no la tiene → escalar."
)

NEW_ORDEN = '''**ORDEN DE DECISION** (seguir SIEMPRE — esto NO es sugerencia):

PASO 1. ¿La pregunta encaja LITERAL en INFO CANNED de abajo (precio consulta, horarios, dirección, alias, precio contención)? → responder el canned LITERAL. Fin.

PASO 2. ¿Es escalación DIRECTA sin pasar por KB? (queja/hostilidad/urgencia/factura/disponibilidad de doctora/personal/obra social). → `escalar_a_secretaria` + canned. Fin.

PASO 3. CUALQUIER OTRA pregunta sobre la clínica, tratamientos, cuidados, recomendaciones, dudas, edades, materiales, procedimientos, dolor, alimentación, deportes, higiene → **OBLIGATORIO PRIMERO**: llamar `buscar_conocimiento` con la pregunta del paciente. NO escalar antes de llamar la tool. NO asumir que la KB no tiene la info.
   - Si la tool retorna docs relevantes → responder con esa info (máx 2-3 oraciones, parafraseando los docs, NO inventar). Fin.
   - Si la tool retorna [] o nada relevante → recién ahí escalar con canned: "Eso lo evalúa la Dra. Raquel en consulta. Le paso a la secretaria Irina."

EJEMPLOS REALES de preguntas que DEBEN ir a buscar_conocimiento (NO escalar antes):
- "puedo hacer deporte con brackets?" → KB tiene FAQ deporte con brackets.
- "duele ponerse brackets?" → KB tiene FAQ dolor.
- "a qué edad empieza ortodoncia?" → KB tiene FAQ edad primera consulta.
- "puedo agendar para mi hijo?" → KB tiene FAQ menores.
- "qué papeles llevo a la primera consulta?" → KB tiene FAQ documentación.
- "cómo se cuidan los brackets?" → KB tiene protocolo higiene.
- "qué pasa si falto?" → KB tiene FAQ ausencia.
- "los alineadores son tan efectivos como brackets?" → KB tiene FAQ alineadores.
- "cómo se pagan las cuotas?" → KB tiene FAQ pagos.

REGLA ABSOLUTA: ANTES DE LLAMAR `escalar_a_secretaria` sobre tema clínico/tratamiento/cuidado, SIEMPRE llamar `buscar_conocimiento` primero. Si saltás este paso, fallas el protocolo. La KB tiene 50+ docs, probablemente la respuesta está ahí.

NUNCA inventar info. Si la KB no la tiene → escalar.'''


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


def main():
    print('=== FETCH v6 ===')
    wf = http('GET', f'/workflows/{WID}')

    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    pre = Path(f'workflows/history/v6_PRE_SUBAGENT_GENERAL_KB_{int(time.time())}.json')
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  backup PRE: {pre}')

    sa = next((n for n in wf['nodes'] if n['name'] == 'Sub-Agent General'), None)
    if not sa:
        print('NO Sub-Agent General found'); sys.exit(1)

    sm = sa['parameters'].get('options', {}).get('systemMessage', '')
    if OLD_ORDEN not in sm:
        idx = sm.find('**ORDEN DE DECISION**')
        print(f'OLD ORDEN block not found exact. Showing actual block at offset {idx}:')
        print(repr(sm[idx:idx+800]))
        sys.exit(1)

    new_sm = sm.replace(OLD_ORDEN, NEW_ORDEN)
    if new_sm == sm:
        print('Replace had no effect'); sys.exit(1)

    sa['parameters']['options']['systemMessage'] = new_sm
    print(f'  systemMessage diff: {len(new_sm) - len(sm):+d} chars')

    safe = {k: wf[k] for k in ('name', 'nodes', 'connections', 'settings') if k in wf}
    safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED_SETTINGS}

    print('=== PUT ===')
    http('PUT', f'/workflows/{WID}', safe)
    print('  PUT 200')

    after = http('GET', f'/workflows/{WID}')
    sa_after = next((n for n in after['nodes'] if n['name'] == 'Sub-Agent General'), {})
    sm_after = sa_after.get('parameters', {}).get('options', {}).get('systemMessage', '')
    print(f'  verify NEW ORDEN present: {NEW_ORDEN[:60] in sm_after}')
    print(f'  verify OLD ORDEN removed: {OLD_ORDEN[:60] not in sm_after}')

    post = Path(f'workflows/history/v6_POST_SUBAGENT_GENERAL_KB_{int(time.time())}.json')
    post.write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'  backup POST: {post}')


if __name__ == '__main__':
    main()
