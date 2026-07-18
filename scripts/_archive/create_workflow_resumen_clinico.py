"""
Crea (o actualiza) el workflow 'Cron - Resumen Clinico Pacientes' en n8n.

Diseño:
  Schedule Trigger (0 5 * * * UTC = 02:00 ARG, daily)
    → Postgres "Get Pacientes Activos"
        SELECT id, telefono, nombre, apellidos FROM pacientes
        WHERE (human_takeover IS NULL OR human_takeover = false)
          AND EXISTS(SELECT 1 FROM conversaciones c
                     WHERE c.telefono = pacientes.telefono
                       AND c.timestamp > NOW() - INTERVAL '30 days')
          AND (resumen_actualizado_at IS NULL
               OR resumen_actualizado_at < NOW() - INTERVAL '3 days')
        ORDER BY resumen_actualizado_at NULLS FIRST
        LIMIT 100
    → SplitInBatches (batch=1)
        → Postgres "Get Conversaciones" (ultimos 30 msgs del paciente)
        → Code "Format Mensajes" (string formateado para el LLM)
        → IF "Suficientes msgs?" (>= 5)
            → OpenAI Chat "Resumir Paciente" (gpt-5-mini)
            → Postgres "Update Paciente" (resumen + resumen_actualizado_at = NOW())
"""
import json
import re
import urllib.request
from pathlib import Path

txt = Path('.env').read_text()
API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', txt).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'}

PG_CRED_ID = 'xwvjww5Odcxiy1K9'
OPENAI_CRED_ID = 'nYujqfon7GGDnJUO'

ALLOWED_SETTINGS = {
    'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution',
    'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone',
    'executionOrder', 'callerPolicy', 'callerIds',
}


def http_req(method, url, data=None):
    req = urllib.request.Request(url, method=method, headers=HEADERS,
                                 data=json.dumps(data).encode() if data else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read()
        return json.loads(body) if body else None


GET_PACIENTES_SQL = """
SELECT id, telefono, nombre, apellidos
FROM pacientes
WHERE (human_takeover IS NULL OR human_takeover = false)
  AND EXISTS (
    SELECT 1 FROM conversaciones c
    WHERE c.telefono = pacientes.telefono
      AND c.timestamp > NOW() - INTERVAL '30 days'
  )
  AND (resumen_actualizado_at IS NULL
       OR resumen_actualizado_at < NOW() - INTERVAL '3 days')
ORDER BY resumen_actualizado_at NULLS FIRST
LIMIT 100;
""".strip()

GET_CONVERSACIONES_SQL = """
SELECT timestamp, rol, mensaje
FROM conversaciones
WHERE telefono = $1
ORDER BY timestamp DESC
LIMIT 30;
""".strip()

UPDATE_PACIENTE_SQL = """
UPDATE pacientes
SET resumen_clinico = $1,
    resumen_actualizado_at = NOW()
WHERE id = $2::uuid;
""".strip()

FORMAT_CODE = """
// Recibe items con {timestamp, rol, mensaje}. Devuelve un string formateado.
const rows = $input.all().map(i => i.json);
if (rows.length === 0) return [{ json: { num_msgs: 0, formatted: '' } }];
rows.sort((a, b) => String(a.timestamp).localeCompare(String(b.timestamp)));
const lines = rows.map(r => {
  const rol = r.rol === 'user' ? 'paciente' :
              r.rol === 'assistant' ? 'bot' :
              r.rol === 'human' ? 'secretaria/doctora' :
              r.rol === 'system' ? 'recordatorio' : r.rol;
  const msg = String(r.mensaje || '').replace(/\\s+/g, ' ').slice(0, 300);
  return `[${rol}] ${msg}`;
});
const paciente_id = $('Loop Pacientes').item.json.id;
const nombre = ($('Loop Pacientes').item.json.nombre || '') + ' ' +
               ($('Loop Pacientes').item.json.apellidos || '');
return [{ json: {
  paciente_id,
  nombre: nombre.trim(),
  num_msgs: lines.length,
  formatted: lines.join('\\n')
}}];
""".strip()

RESUMEN_PROMPT_SYSTEM = """Sos un asistente clinico de Aurea Odontologia (Dra. Raquel Rodriguez).
Tu tarea: leer los ultimos mensajes entre un paciente y la clinica y generar un resumen breve para que la asistente virtual tenga contexto en proximas conversaciones.

INSTRUCCIONES:
- 1 a 3 frases, prose llana, max 280 caracteres total.
- Incluir si surge: tratamiento actual (ortodoncia, expansor, limpieza, etc), estado de turnos (proximo turno fecha/hora, confirmaciones recientes, cancelaciones), preferencias (horario, profesional), actitud relevante (frustrado, conforme).
- NO usar emojis, NO usar bullets, NO usar headings, NO mencionar al bot/secretaria/doctora como sujetos del resumen (es sobre el PACIENTE).
- Si no hay info clinica relevante (solo saludos, autoresponders, mensajes administrativos), responder EXACTAMENTE: "Sin historial clinico relevante."

EJEMPLOS DE BUEN RESUMEN:
- "Paciente en tratamiento de ortodoncia. Confirmo turno del 26 de mayo a las 10:00. Prefiere horarios de manana."
- "Mama de Martina (paciente menor, expansor maxilar). Consulto por molestia leve, derivo a secretaria."
- "Paciente nuevo. Consulto precio de primera consulta el 18 de mayo, sin turno reservado todavia."

SOLO devolve el resumen, nada mas."""

WF_NAME = 'Cron - Resumen Clinico Pacientes'


def build_workflow():
    return {
        'name': WF_NAME,
        'nodes': [
            {
                'parameters': {
                    'rule': {'interval': [{'field': 'cronExpression', 'expression': '0 5 * * *'}]},
                },
                'id': 'cron',
                'name': 'Cron 02:00 ARG',
                'type': 'n8n-nodes-base.scheduleTrigger',
                'typeVersion': 1.2,
                'position': [240, 300],
            },
            {
                'parameters': {
                    'operation': 'executeQuery',
                    'query': GET_PACIENTES_SQL,
                    'options': {},
                },
                'id': 'get-pacientes',
                'name': 'Get Pacientes Activos',
                'type': 'n8n-nodes-base.postgres',
                'typeVersion': 2.5,
                'position': [460, 300],
                'credentials': {'postgres': {'id': PG_CRED_ID, 'name': 'Postgres account'}},
            },
            {
                'parameters': {
                    'batchSize': 1,
                    'options': {},
                },
                'id': 'loop-pacientes',
                'name': 'Loop Pacientes',
                'type': 'n8n-nodes-base.splitInBatches',
                'typeVersion': 3,
                'position': [680, 300],
            },
            {
                'parameters': {
                    'operation': 'executeQuery',
                    'query': GET_CONVERSACIONES_SQL,
                    'options': {'queryReplacement': "={{ $('Loop Pacientes').item.json.telefono }}"},
                },
                'id': 'get-conversaciones',
                'name': 'Get Conversaciones',
                'type': 'n8n-nodes-base.postgres',
                'typeVersion': 2.5,
                'position': [900, 200],
                'credentials': {'postgres': {'id': PG_CRED_ID, 'name': 'Postgres account'}},
            },
            {
                'parameters': {
                    'jsCode': FORMAT_CODE,
                },
                'id': 'format-msgs',
                'name': 'Format Mensajes',
                'type': 'n8n-nodes-base.code',
                'typeVersion': 2,
                'position': [1120, 200],
            },
            {
                'parameters': {
                    'conditions': {
                        'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict'},
                        'conditions': [{
                            'leftValue': '={{ $json.num_msgs }}',
                            'rightValue': 5,
                            'operator': {'type': 'number', 'operation': 'gte'}
                        }],
                        'combinator': 'and'
                    },
                    'options': {},
                },
                'id': 'if-suficientes',
                'name': 'Suficientes msgs?',
                'type': 'n8n-nodes-base.if',
                'typeVersion': 2.2,
                'position': [1340, 200],
            },
            {
                'parameters': {
                    'modelId': {'__rl': True, 'value': 'gpt-5-mini', 'mode': 'list'},
                    'messages': {
                        'values': [
                            {'role': 'system', 'content': RESUMEN_PROMPT_SYSTEM},
                            {'role': 'user', 'content': "=Paciente: {{ $('Format Mensajes').item.json.nombre }}\n\nUltimos mensajes (cronologico):\n{{ $('Format Mensajes').item.json.formatted }}"},
                        ],
                    },
                    'options': {'temperature': 0.2, 'maxTokens': 200},
                },
                'id': 'llm-resumir',
                'name': 'LLM Resumir',
                'type': '@n8n/n8n-nodes-langchain.openAi',
                'typeVersion': 1.8,
                'position': [1560, 100],
                'credentials': {'openAiApi': {'id': OPENAI_CRED_ID, 'name': 'OpenAi account'}},
            },
            {
                'parameters': {
                    'operation': 'executeQuery',
                    'query': UPDATE_PACIENTE_SQL,
                    'options': {
                        'queryReplacement': "={{ $('LLM Resumir').item.json.message.content }},{{ $('Loop Pacientes').item.json.id }}"
                    },
                },
                'id': 'update-paciente',
                'name': 'Update Paciente',
                'type': 'n8n-nodes-base.postgres',
                'typeVersion': 2.5,
                'position': [1780, 100],
                'credentials': {'postgres': {'id': PG_CRED_ID, 'name': 'Postgres account'}},
            },
        ],
        'connections': {
            'Cron 02:00 ARG': {'main': [[{'node': 'Get Pacientes Activos', 'type': 'main', 'index': 0}]]},
            'Get Pacientes Activos': {'main': [[{'node': 'Loop Pacientes', 'type': 'main', 'index': 0}]]},
            'Loop Pacientes': {'main': [
                [],
                [{'node': 'Get Conversaciones', 'type': 'main', 'index': 0}]
            ]},
            'Get Conversaciones': {'main': [[{'node': 'Format Mensajes', 'type': 'main', 'index': 0}]]},
            'Format Mensajes': {'main': [[{'node': 'Suficientes msgs?', 'type': 'main', 'index': 0}]]},
            'Suficientes msgs?': {'main': [
                [{'node': 'LLM Resumir', 'type': 'main', 'index': 0}],
                [{'node': 'Loop Pacientes', 'type': 'main', 'index': 0}]
            ]},
            'LLM Resumir': {'main': [[{'node': 'Update Paciente', 'type': 'main', 'index': 0}]]},
            'Update Paciente': {'main': [[{'node': 'Loop Pacientes', 'type': 'main', 'index': 0}]]},
        },
        'settings': {'executionOrder': 'v1', 'timezone': 'America/Argentina/Buenos_Aires'},
    }


def main():
    # buscar si ya existe
    wfs = http_req('GET', f'{BASE}/workflows?limit=100')
    existing = next((w for w in wfs['data'] if w.get('name') == WF_NAME), None)

    wf = build_workflow()
    if existing:
        print(f'Workflow ya existe (id={existing["id"]}), actualizando via PUT...')
        try:
            http_req('POST', f'{BASE}/workflows/{existing["id"]}/deactivate')
        except Exception:
            pass
        # strip meta para PUT
        for k in ('id','active','createdAt','updatedAt'):
            wf.pop(k, None)
        http_req('PUT', f'{BASE}/workflows/{existing["id"]}', wf)
        wid = existing['id']
    else:
        print('Creando workflow nuevo...')
        created = http_req('POST', f'{BASE}/workflows', wf)
        wid = created['id']
        print(f'  id: {wid}')

    print(f'Activando workflow {wid}...')
    try:
        http_req('POST', f'{BASE}/workflows/{wid}/activate')
        print('  active: True')
    except Exception as ex:
        print(f'  activate FAIL: {ex}')

    print(f'\nWorkflow URL: https://n8n.raquelrodriguez.com.ar/workflow/{wid}')
    Path('docs/resumen_clinico_workflow_id.txt').write_text(wid, encoding='utf-8')


if __name__ == '__main__':
    main()
