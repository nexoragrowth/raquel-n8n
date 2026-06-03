"""
Fix raiz del leak Carmen: inyectar phone + pushName del webhook al LLM como
contexto explicito en el `text` input de cada Sub-Agent.

Diagnostico (22/5):
- Sub-Agent Agendar tenia text: {{ $('Preparar Mensaje Final').first().json.text }}
- Eso le pasa SOLO el mensaje del paciente al LLM.
- El LLM tiene que llamar tools que requieren phone (buscar_paciente_dentalink,
  obtener_historial_paciente). Pero el LLM NUNCA ve el phone del webhook.
- Resultado: el LLM aluciona un celular (casualmente el de Carmen Agostini)
  y leakea su identidad a pacientes no relacionados (Ivan, Mariela).
- Las reglas del prompt ("NUNCA inventes celular, viene del webhook") son
  ignoradas porque el LLM NO TIENE el dato.

Fix: cambiar el `text` de cada Sub-Agent a un template que incluya:
  - phone (del Edit Fields - Extraer Datos)
  - pushName (del mismo)
  - el mensaje del paciente (como antes)

Tambien: limpiar el ultimo residuo de Carmen (3886869400 sin codigo pais)
en buscar_paciente_dentalink.toolDescription.

Aplica a: Sub-Agent Agendar / Confirmar / Cancelar / General / Urgencia.
"""
import json
import re
import time
import urllib.request
from pathlib import Path


def get_api_key():
    return re.search(r'N8N_API_KEY=([^\r\n]+)', Path('.env').read_text()).group(1).strip()


API_KEY = get_api_key()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
WID = 'O155MqHgOSaNZ9ye'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}
ALLOWED_SETTINGS = {
    'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution',
    'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone',
    'executionOrder', 'callerPolicy', 'callerIds',
}

NEW_TEXT = (
    "=[CONTEXTO DEL PACIENTE QUE ESCRIBE]\n"
    "phone: {{ $('Edit Fields - Extraer Datos').first().json.phone }}\n"
    "pushName: {{ $('Edit Fields - Extraer Datos').first().json.pushName }}\n"
    "\n"
    "[MENSAJE]\n"
    "{{ $('Preparar Mensaje Final').first().json.text }}"
)

SUB_AGENTS = [
    'Sub-Agent Agendar', 'Sub-Agent Confirmar', 'Sub-Agent Cancelar',
    'Sub-Agent General', 'Sub-Agent Urgencia',
]


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


def main():
    wf = http_req('GET', f'{BASE}/workflows/{WID}')
    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    bak = f'workflows/history/v6_PRE_FIX_PHONE_CTX_{int(time.time())}.json'
    Path(bak).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup PRE: {bak}')

    changes = []

    # 1) Limpiar el residuo 3886869400 en buscar_paciente_dentalink description
    for n in wf['nodes']:
        if n['name'] == 'buscar_paciente_dentalink':
            old = n['parameters'].get('toolDescription', '')
            new = old.replace('"lk":"3886869400"', '"lk":"1200099999"')
            new = new.replace('"lk":"+5491200099999"', '"lk":"+5491200099999"')  # ya OK
            if new != old:
                n['parameters']['toolDescription'] = new
                changes.append(('buscar_paciente_dentalink.toolDescription', 'residuo 3886869400'))

    # 2) Inyectar contexto phone+pushName en cada Sub-Agent
    for n in wf['nodes']:
        if n['name'] in SUB_AGENTS:
            old = n['parameters'].get('text', '')
            if old == NEW_TEXT:
                print(f'  {n["name"]}: ya esta con NEW_TEXT, skip')
                continue
            n['parameters']['text'] = NEW_TEXT
            n['parameters']['promptType'] = 'define'
            changes.append((f'{n["name"]}.text', f'old_len={len(old)} -> new_len={len(NEW_TEXT)}'))

    print('\nChanges:')
    for c in changes:
        print(f'  {c[0]}: {c[1]}')

    wf = strip_meta(wf)
    http_req('PUT', f'{BASE}/workflows/{WID}', wf)
    print('\nPUT: 200')

    wf2 = http_req('GET', f'{BASE}/workflows/{WID}')
    bak2 = f'workflows/history/v6_POST_FIX_PHONE_CTX_{int(time.time())}.json'
    Path(bak2).write_text(json.dumps(wf2, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup POST: {bak2}')

    # Verificar leaks
    s = json.dumps(wf2, ensure_ascii=False)
    print()
    for needle in ['5493886869400', '543886869400', '3886869400', 'Carmen', 'Agostini']:
        print(f'  workflow vivo cuenta {needle!r}: {s.count(needle)}')


if __name__ == '__main__':
    main()
