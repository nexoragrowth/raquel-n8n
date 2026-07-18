"""
Integra el `resumen_clinico` del paciente al v6:

1. Backup pre del v6 vivo.
2. Inserta un nodo Postgres "Get Paciente Context" entre `Edit Fields - Extraer Datos`
   y `Es fromMe?` con query SELECT nombre, resumen_clinico WHERE telefono = $1.
3. Modifica el `text` input de los 5 sub-agents para incluir el resumen como
   parte del bloque [CONTEXTO DEL PACIENTE QUE ESCRIBE].
4. PUT + backup post + verificacion.

Si el paciente no esta en `pacientes` o no tiene resumen aun, el campo se
renderiza como "Sin historial registrado" para que el LLM no se confunda.
"""
import json
import re
import time
import urllib.request
from pathlib import Path

txt = Path('.env').read_text()
API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', txt).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
WID = 'O155MqHgOSaNZ9ye'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}

PG_CRED_ID = 'xwvjww5Odcxiy1K9'
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution','saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder','callerPolicy','callerIds'}

NEW_TEXT_TEMPLATE = (
    "=[CONTEXTO DEL PACIENTE QUE ESCRIBE]\n"
    "phone: {{ $('Edit Fields - Extraer Datos').first().json.phone }}\n"
    "pushName: {{ $('Edit Fields - Extraer Datos').first().json.pushName }}\n"
    "resumen historial: {{ $('Get Paciente Context').first().json.resumen_clinico || 'Sin historial registrado todavia.' }}\n"
    "\n"
    "[MENSAJE]\n"
    "{{ $('Preparar Mensaje Final').first().json.text }}"
)

SUB_AGENTS = ['Sub-Agent Agendar', 'Sub-Agent Confirmar', 'Sub-Agent Cancelar',
              'Sub-Agent General', 'Sub-Agent Urgencia']


def http_req(method, url, data=None):
    req = urllib.request.Request(url, method=method, headers=HEADERS,
                                 data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


def main():
    wf = http_req('GET', f'{BASE}/workflows/{WID}')
    Path('workflows/history').mkdir(parents=True, exist_ok=True)
    bak = f'workflows/history/v6_PRE_INYECTAR_RESUMEN_{int(time.time())}.json'
    Path(bak).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup PRE: {bak}')

    # 1) Buscar posicion del Edit Fields y de Es fromMe?
    ef = next(n for n in wf['nodes'] if n['name'] == 'Edit Fields - Extraer Datos')
    fm = next(n for n in wf['nodes'] if n['name'] == 'Es fromMe?')
    ef_pos = ef.get('position', [0, 0])
    new_x = ef_pos[0] + 220
    new_y = ef_pos[1]

    # 2) Crear nodo Get Paciente Context
    pc_node = {
        'parameters': {
            'operation': 'executeQuery',
            'query': (
                "SELECT COALESCE(nombre,'') as nombre, "
                "COALESCE(resumen_clinico,'') as resumen_clinico, "
                "COALESCE(resumen_actualizado_at::text,'') as resumen_actualizado_at "
                "FROM pacientes WHERE telefono = $1 LIMIT 1;"
            ),
            'options': {
                'queryReplacement': "={{ $('Edit Fields - Extraer Datos').item.json.phone }}"
            },
        },
        'id': 'get-paciente-context',
        'name': 'Get Paciente Context',
        'type': 'n8n-nodes-base.postgres',
        'typeVersion': 2.5,
        'position': [new_x, new_y],
        'credentials': {'postgres': {'id': PG_CRED_ID, 'name': 'Postgres account'}},
        'continueOnFail': True,  # si el paciente no existe, no rompe el flow
        'alwaysOutputData': True,
    }

    # No insertar si ya existe
    if any(n['name'] == 'Get Paciente Context' for n in wf['nodes']):
        print('  Get Paciente Context ya existe, skip insercion')
    else:
        # Reposicionar Es fromMe? mas a la derecha
        fm['position'] = [new_x + 220, fm.get('position', [0, 0])[1]]
        wf['nodes'].append(pc_node)
        # Reconectar: Edit Fields -> Get Paciente Context -> Es fromMe?
        conns = wf['connections']
        # Edit Fields tenia conexion a Es fromMe?
        if 'Edit Fields - Extraer Datos' in conns:
            conns['Edit Fields - Extraer Datos'] = {'main': [[{'node': 'Get Paciente Context', 'type': 'main', 'index': 0}]]}
        conns['Get Paciente Context'] = {'main': [[{'node': 'Es fromMe?', 'type': 'main', 'index': 0}]]}
        print('  Get Paciente Context insertado entre Edit Fields y Es fromMe?')

    # 3) Modificar `text` de cada Sub-Agent
    for n in wf['nodes']:
        if n['name'] in SUB_AGENTS:
            old = n['parameters'].get('text', '')
            if 'resumen historial' in old:
                print(f'  {n["name"]}: ya tiene resumen, skip')
                continue
            n['parameters']['text'] = NEW_TEXT_TEMPLATE
            print(f'  {n["name"]}: text actualizado (+{len(NEW_TEXT_TEMPLATE) - len(old)} chars)')

    # 4) PUT
    put_wf = {
        'name': wf['name'],
        'nodes': wf['nodes'],
        'connections': wf['connections'],
        'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED},
    }
    http_req('PUT', f'{BASE}/workflows/{WID}', put_wf)
    print('\nPUT v6: 200')

    # Activar
    try:
        http_req('POST', f'{BASE}/workflows/{WID}/activate')
        print('activated')
    except Exception as e:
        print(f'activate skip: {e}')

    # backup POST
    wf2 = http_req('GET', f'{BASE}/workflows/{WID}')
    bak2 = f'workflows/history/v6_POST_INYECTAR_RESUMEN_{int(time.time())}.json'
    Path(bak2).write_text(json.dumps(wf2, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'backup POST: {bak2}')

    # Verificar
    has_pc = any(n['name'] == 'Get Paciente Context' for n in wf2['nodes'])
    has_resumen_in_subs = all('resumen historial' in next((n['parameters'].get('text','') for n in wf2['nodes'] if n['name']==sa), '') for sa in SUB_AGENTS)
    print(f'\nVERIFICACION:')
    print(f'  Get Paciente Context node: {has_pc}')
    print(f'  resumen en los 5 sub-agents: {has_resumen_in_subs}')
    print(f'  v6 active: {wf2.get("active")}')


if __name__ == '__main__':
    main()
