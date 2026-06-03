"""
Fix v2 del leak Carmen Agostini.

El Round 3 (apply_fix_agendar_leak.py) saco el celular del system prompt del
Sub-Agent Agendar, pero quedo hardcoded en:

1. buscar_paciente_dentalink.toolDescription -> ejemplo del celular Carmen
   (5493886869400 y 543886869400) en 5+ menciones literales. Como esta tool
   esta wireada a Confirmar / Cancelar / Agendar / General, TODOS los sub-agents
   ven el celular cuando inspeccionan la tool y lo usan literal como si fuera
   el del paciente actual.

2. crear_paciente_dentalink.toolDescription -> "caso Carmen Agostini id=413 vs id=609".

3. Sub-Agent Agendar.systemMessage L37 -> idem.

Casos reales rotos (22/5):
- Ivan (tel 5493883343595): bot llamo obtener_historial_paciente con phone
  5493886869400 (Carmen), no encontro turnos y escalo aunque Ivan tenia
  recordatorio del dia (EXEC 23432).
- Mariela (tel 5493884040348): bot escalo a Iri usando "Paciente (tel
  5493886869400)" en vez de reservar el horario que la paciente eligio de
  los ofrecidos por Iri (EXEC 24339).

Fix: despersonalizar los ejemplos con celular sintetico (5491200099999) e
ids fantasma. La leccion tecnica (multi-formato + duplicado) se preserva.
"""
import json
import os
import re
import time
import urllib.request
from pathlib import Path


def get_api_key():
    p = Path('.env')
    m = re.search(r'N8N_API_KEY=([^\r\n]+)', p.read_text())
    return m.group(1).strip()


API_KEY = get_api_key()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
WID = 'O155MqHgOSaNZ9ye'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}

ALLOWED_SETTINGS = {
    'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution',
    'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone',
    'executionOrder', 'callerPolicy', 'callerIds',
}


def http_req(method, url, data=None):
    req = urllib.request.Request(url, method=method, headers=HEADERS,
                                 data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read()) if r.status != 204 else None


def strip_meta(wf):
    for k in ('id', 'active', 'createdAt', 'updatedAt', 'tags', 'versionId', 'triggerCount',
              'meta', 'isArchived', 'shared', 'homeProject', 'sharedWithProjects', 'scopes',
              'description', 'pinData', 'activeVersionId', 'versionCounter', 'activeVersion'):
        wf.pop(k, None)
    wf['settings'] = {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED_SETTINGS}
    return wf


def patch_buscar_paciente_desc(desc):
    """Reemplaza ejemplos con celular Carmen por celular sintetico."""
    desc = desc.replace('5493886869400', '5491200099999')
    desc = desc.replace('543886869400', '541200099999')
    desc = desc.replace(
        'EJEMPLO REAL: paciente Carmen Agostini con WA `5491200099999` esta guardada con celular `+541200099999` (sin el 9). Solo encontras el match en intento 2.',
        'EJEMPLO: si un paciente tiene WA `5491200099999`, en Dentalink puede estar guardado como `+541200099999` (sin el 9). En ese caso el match aparece en intento 2, no en intento 1.',
    )
    return desc


def patch_crear_paciente_desc(desc):
    return desc.replace(
        'Riesgo de duplicado (lecccion del caso Carmen Agostini id=413 vs id=609).',
        'Riesgo de duplicado: un mismo paciente puede quedar cargado con dos ids cuando el celular esta en formatos distintos. Si dudas, prefiere busqueda extra antes que crear.',
    )


def patch_agendar_sm(sm):
    return sm.replace(
        'CONTEXTO CRITICO: NO crear pacientes duplicados (BUG GRAVE conocido — caso Carmen Agostini id=413 vs id=609 duplicado por formato phone). Antes de crear, BUSCAR EXHAUSTIVAMENTE.',
        'CONTEXTO CRITICO: NO crear pacientes duplicados (BUG GRAVE: un mismo paciente puede quedar cargado con dos ids distintos cuando el celular esta en formatos distintos). Antes de crear, BUSCAR EXHAUSTIVAMENTE.',
    ).replace(
        'CONTEXTO CRITICO: NO crear pacientes duplicados (BUG GRAVE conocido - caso Carmen Agostini id=413 vs id=609 duplicado por formato phone). Antes de crear, BUSCAR EXHAUSTIVAMENTE.',
        'CONTEXTO CRITICO: NO crear pacientes duplicados (BUG GRAVE: un mismo paciente puede quedar cargado con dos ids distintos cuando el celular esta en formatos distintos). Antes de crear, BUSCAR EXHAUSTIVAMENTE.',
    )


def main():
    wf = http_req('GET', f'{BASE}/workflows/{WID}')
    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    bak = f'workflows/history/v6_PRE_FIX_CARMEN_v2_{int(time.time())}.json'
    Path(bak).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup PRE: {bak}')

    changes = []
    for n in wf['nodes']:
        nm = n['name']
        p = n.get('parameters', {})

        if nm == 'buscar_paciente_dentalink':
            old = p.get('toolDescription', '')
            new = patch_buscar_paciente_desc(old)
            if new != old:
                p['toolDescription'] = new
                changes.append((nm, 'toolDescription', len(old) - len(new)))

        elif nm == 'crear_paciente_dentalink':
            old = p.get('toolDescription', '')
            new = patch_crear_paciente_desc(old)
            if new != old:
                p['toolDescription'] = new
                changes.append((nm, 'toolDescription', len(old) - len(new)))

        elif nm == 'Sub-Agent Agendar':
            opts = p.get('options', {})
            old = opts.get('systemMessage', '')
            new = patch_agendar_sm(old)
            if new != old:
                opts['systemMessage'] = new
                p['options'] = opts
                changes.append((nm, 'systemMessage', len(old) - len(new)))

    print(f'\nChanges:')
    for c in changes:
        print(f'  {c[0]}.{c[1]}  delta={c[2]}')

    # Re-verify no leaks pre-PUT
    s = json.dumps(wf, ensure_ascii=False)
    for needle in ['5493886869400', '543886869400', 'Carmen Agostini', 'id=413', 'id=609']:
        cnt = s.count(needle)
        print(f'  post-patch {needle!r}: {cnt}')

    wf = strip_meta(wf)
    http_req('PUT', f'{BASE}/workflows/{WID}', wf)
    print('\nPUT v6: 200')

    # Backup POST
    wf2 = http_req('GET', f'{BASE}/workflows/{WID}')
    bak2 = f'workflows/history/v6_POST_FIX_CARMEN_v2_{int(time.time())}.json'
    Path(bak2).write_text(json.dumps(wf2, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup POST: {bak2}')


if __name__ == '__main__':
    main()
