"""
Mejora Sub-Agent General: darle acceso a ver_turnos_paciente para que pueda
responder consultas tipo "cuando era mi turno?" mid-conversation sin que el
Router tenga que ser perfecto.

Cambios (atómicos, respetando lo existente):
1. Get Paciente Context query: agregar paciente_id_dentalink al SELECT.
2. Sub-Agent General prompt (text): agregar paciente_id_dentalink al contexto.
3. ver_turnos_paciente toolDescription: aclarar usar paciente_id del contexto.
4. Connections: agregar Sub-Agent General como target ai_tool de ver_turnos_paciente
   (sin tocar las conexiones existentes a Sub-Agent Cancelar/Confirmar).
"""
import json
import re
import time
import urllib.request
from pathlib import Path

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
WID = re.search(r'N8N_WORKFLOW_V6_ID=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution','saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder','callerPolicy','callerIds'}


OLD_QUERY = "SELECT COALESCE(nombre,'') as nombre, COALESCE(resumen_clinico,'') as resumen_clinico, COALESCE(resumen_actualizado_at::text,'') as resumen_actualizado_at FROM pacientes WHERE telefono = $1 LIMIT 1;"
NEW_QUERY = "SELECT COALESCE(nombre,'') as nombre, COALESCE(resumen_clinico,'') as resumen_clinico, COALESCE(resumen_actualizado_at::text,'') as resumen_actualizado_at, COALESCE(paciente_id_dentalink::text,'') as paciente_id_dentalink FROM pacientes WHERE telefono = $1 LIMIT 1;"

OLD_PROMPT = """=[CONTEXTO DEL PACIENTE QUE ESCRIBE]
phone: {{ $('Edit Fields - Extraer Datos').first().json.phone }}
pushName: {{ $('Edit Fields - Extraer Datos').first().json.pushName }}
resumen historial: {{ $('Get Paciente Context').first().json.resumen_clinico || 'Sin historial registrado todavia.' }}

[MENSAJE]
{{ $('Preparar Mensaje Final').first().json.text }}"""

NEW_PROMPT = """=[CONTEXTO DEL PACIENTE QUE ESCRIBE]
phone: {{ $('Edit Fields - Extraer Datos').first().json.phone }}
pushName: {{ $('Edit Fields - Extraer Datos').first().json.pushName }}
paciente_id_dentalink: {{ $('Get Paciente Context').first().json.paciente_id_dentalink || '' }}
resumen historial: {{ $('Get Paciente Context').first().json.resumen_clinico || 'Sin historial registrado todavia.' }}

[MENSAJE]
{{ $('Preparar Mensaje Final').first().json.text }}"""

OLD_TOOL_DESC = "Obtiene citas de un paciente. El parametro q es un JSON string con filtro, ejemplo: q={\"id_paciente\":{\"eq\":123}}"
NEW_TOOL_DESC = "Obtiene citas de un paciente desde Dentalink. Param: id_paciente (numero). Si el contexto del prompt trae paciente_id_dentalink, usalo directo (no llames a buscar_paciente_dentalink antes). Util para responder 'cuando es mi turno?', 'tengo turno?', 'a que hora?', 'tengo turno el [fecha]?'."


def http(method, path, body=None):
    req = urllib.request.Request(f'{BASE}{path}', method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        if r.status == 204: return None
        return json.loads(r.read())


wf = http('GET', f'/workflows/{WID}')
Path('workflows/history').mkdir(parents=True, exist_ok=True)
Path(f'workflows/history/v6_PRE_SAG_VER_TURNOS_{int(time.time())}.json').write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding='utf-8')

# 1. Get Paciente Context query
gpc = next((n for n in wf['nodes'] if n['name'] == 'Get Paciente Context'), None)
if gpc and gpc['parameters'].get('query') == OLD_QUERY:
    gpc['parameters']['query'] = NEW_QUERY
    print('1. Get Paciente Context query: paciente_id_dentalink agregado')
else:
    print('1. Get Paciente Context query NOT exact match, abort'); raise SystemExit(1)

# 2. Sub-Agent General prompt
sag = next((n for n in wf['nodes'] if n['name'] == 'Sub-Agent General'), None)
if sag and sag['parameters'].get('text') == OLD_PROMPT:
    sag['parameters']['text'] = NEW_PROMPT
    print('2. Sub-Agent General prompt: paciente_id_dentalink agregado al contexto')
else:
    print('2. Sub-Agent General prompt NOT exact match, abort'); raise SystemExit(1)

# 3. ver_turnos_paciente toolDescription
vt = next((n for n in wf['nodes'] if n['name'] == 'ver_turnos_paciente'), None)
if vt and OLD_TOOL_DESC in vt['parameters'].get('toolDescription', ''):
    vt['parameters']['toolDescription'] = NEW_TOOL_DESC
    print('3. ver_turnos_paciente toolDescription actualizado')
else:
    print('3. tool desc no exact match, sigo igual con cambio')
    if vt:
        vt['parameters']['toolDescription'] = NEW_TOOL_DESC

# 4. Connection ver_turnos_paciente -> Sub-Agent General (preservar existentes)
conns = wf['connections'].setdefault('ver_turnos_paciente', {}).setdefault('ai_tool', [[]])
targets = conns[0]
already = any(t.get('node') == 'Sub-Agent General' for t in targets)
if not already:
    targets.append({'node': 'Sub-Agent General', 'type': 'ai_tool', 'index': 0})
    print(f'4. ver_turnos_paciente ai_tool -> Sub-Agent General agregado. Targets ahora: {[t["node"] for t in targets]}')
else:
    print('4. ya estaba conectado a Sub-Agent General')

safe = {k: wf[k] for k in ('name','nodes','connections','settings') if k in wf}
safe['settings'] = {k: v for k, v in safe.get('settings', {}).items() if k in ALLOWED}
http('PUT', f'/workflows/{WID}', safe)
print('PUT 200')

Path(f'workflows/history/v6_POST_SAG_VER_TURNOS_{int(time.time())}.json').write_text(json.dumps(http('GET', f'/workflows/{WID}'), indent=2, ensure_ascii=False), encoding='utf-8')
print('backup POST OK')
