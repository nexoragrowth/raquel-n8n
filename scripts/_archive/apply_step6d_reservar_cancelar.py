"""Step 6d: rama Switch 'reservar_y_cancelar' del Sub-WF.

Orden seguro:
1. POST reservar nuevo
2. Si reserva OK → PUT cancelar viejo
3. Si reserva falla → escalar (NO cancelar viejo, evitar dejar paciente sin turno)
4. Si cancelar falla post-reserva → escalar (doble booking, requiere intervención)

Nodos a agregar:
- Step 6d-1: HTTP POST Reservar (Dentalink)
- Step 6d-2: IF "reserva OK?"
- Step 6d-3a: HTTP PUT Cancelar (rama true)
- Step 6d-3b: Code "Escalar reserva fallida" (rama false)
- Step 6d-4: Code consolida output final
"""
import json, re, urllib.request, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = re.search(r'N8N_API_KEY=([^\r\n]+)', open('.env').read()).group(1).strip()
BASE = 'https://n8n.raquelrodriguez.com.ar/api/v1'
HEADERS = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
DT_CRED = 'TwN6eBWsydjMdsCM'
WID_SUB = open('docs/sub_wf_cancelar_id.txt').read().strip()

# Step 6d-prep: prepara body POST reserva en JSON string (evita curly braces en expressions)
STEP6D_PREP_CODE = """const prev = $input.first().json;
const slot = prev.slot_a_reservar || {};
const paciente = prev.paciente || {};

const body = {
  id_dentista: 1,
  id_sucursal: 1,
  id_sillon: 1,
  id_paciente: paciente.id,
  fecha: slot.fecha,
  hora_inicio: slot.hora_inicio,
  duracion: 40,
  comentario: 'Reprogramado por bot (sub-WF)'
};

return [{ json: { ...prev, reserva_body: JSON.stringify(body) } }];"""

step6d_prep = {
    'parameters': {'jsCode': STEP6D_PREP_CODE},
    'id': 'step6d-prep', 'name': 'Step 6d-prep: Build Reserva Body',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [2440, 700]
}

# Step 6d-1: HTTP POST Reservar
step6d_1 = {
    'parameters': {
        'method': 'POST',
        'url': 'https://api.dentalink.healthatom.com/api/v1/citas/',
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpHeaderAuth',
        'sendBody': True, 'specifyBody': 'json',
        'jsonBody': '={{ $json.reserva_body }}',
        'options': {}
    },
    'id': 'step6d-1', 'name': 'Step 6d-1: POST Reservar',
    'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
    'position': [2640, 700],
    'credentials': {'httpHeaderAuth': {'id': DT_CRED, 'name': 'Header Auth account 3'}},
    'continueOnFail': True, 'alwaysOutputData': True
}

# Step 6d-2: IF reserva OK?
step6d_2 = {
    'parameters': {
        'conditions': {
            'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict'},
            'conditions': [{
                'leftValue': '={{ $json?.data?.id_estado || $json[0]?.data?.id_estado || 0 }}',
                'rightValue': 0,
                'operator': {'type': 'number', 'operation': 'gt'}
            }],
            'combinator': 'and'
        },
        'options': {}
    },
    'id': 'step6d-2', 'name': 'Step 6d-2: Reserva OK?',
    'type': 'n8n-nodes-base.if', 'typeVersion': 2.2,
    'position': [2840, 700]
}

# Step 6d-3a (rama TRUE): HTTP PUT cancelar viejo
step6d_3a = {
    'parameters': {
        'method': 'PUT',
        'url': '={{ "https://api.dentalink.healthatom.com/api/v1/citas/" + $(\'Step 6d-prep: Build Reserva Body\').first().json.cita_a_cancelar }}',
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpHeaderAuth',
        'sendBody': True, 'specifyBody': 'json',
        'jsonBody': '={{ JSON.stringify({id_estado: 1}) }}',
        'options': {}
    },
    'id': 'step6d-3a', 'name': 'Step 6d-3a: PUT Cancelar Viejo',
    'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
    'position': [3040, 600],
    'credentials': {'httpHeaderAuth': {'id': DT_CRED, 'name': 'Header Auth account 3'}},
    'continueOnFail': True, 'alwaysOutputData': True
}

# Step 6d-3b (rama FALSE): Code escalar (reserva fallida)
STEP6D_3B_CODE = """const prev = $('Step 6d-prep: Build Reserva Body').first().json;
const reservaResp = $('Step 6d-1: POST Reservar').first().json;
return [{ json: {
  ...prev,
  reserva_status: 'fail',
  reserva_resp: reservaResp,
  mensaje_final: 'No pude reservar el horario que elegiste. Le paso a la secretaria Iri para que lo coordine manualmente.',
  apply_label_humano: true,
  flow: 'reservar_y_cancelar_fail_at_reserve'
}}];"""

step6d_3b = {
    'parameters': {'jsCode': STEP6D_3B_CODE},
    'id': 'step6d-3b', 'name': 'Step 6d-3b: Escalar Reserva Falla',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [3040, 800]
}

# Step 6d-4 (consolidar OK path): si reserva OK + cancelar OK = mensaje exito; si cancelar falla = warning
STEP6D_4_CODE = """const cancelResp = $input.first().json;
const prev = $('Step 6d-prep: Build Reserva Body').first().json;
const reservaResp = $('Step 6d-1: POST Reservar').first().json;

// reserva OK garantizado (vino por rama TRUE)
const cancelOk = cancelResp?.data?.id_estado === 1 || (Array.isArray(cancelResp) && cancelResp[0]?.data?.id_estado === 1);

let mensaje;
if (cancelOk) {
  mensaje = prev.mensaje_final; // ya viene armado del Step 5
} else {
  // Reservo OK pero no canceló viejo. Doble booking → escalar
  mensaje = 'Te reserve el nuevo turno, pero no logre cancelar el anterior automaticamente. Le paso a la secretaria Iri para que ajuste.';
}

return [{ json: {
  ...prev,
  reserva_ok: true,
  cancel_ok: cancelOk,
  reserva_resp: reservaResp,
  cancel_resp: cancelResp,
  mensaje_final: mensaje,
  apply_label_humano: !cancelOk,
  flow: 'reservar_y_cancelar'
}}];"""

step6d_4 = {
    'parameters': {'jsCode': STEP6D_4_CODE},
    'id': 'step6d-4', 'name': 'Step 6d-4: Consolidar Resultado',
    'type': 'n8n-nodes-base.code', 'typeVersion': 2,
    'position': [3240, 600]
}

wf = json.loads(urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', headers=HEADERS), timeout=20).read())

# Agregar nodos
new_nodes = [step6d_prep, step6d_1, step6d_2, step6d_3a, step6d_3b, step6d_4]
existing = {n['name'] for n in wf['nodes']}
for n in new_nodes:
    if n['name'] not in existing:
        wf['nodes'].append(n)

# Agregar caso al Switch existente: 'reservar_y_cancelar' como rama nueva
for n in wf['nodes']:
    if n['name'] == 'Step 6: Switch por Accion':
        rules = n['parameters'].get('rules', {}).get('values', [])
        already_has = any(r.get('outputKey') == 'reservar_y_cancelar' for r in rules)
        if not already_has:
            rules.append({
                'conditions': {'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'strict'},
                  'conditions': [{'leftValue': '={{ $json.action_to_execute }}', 'rightValue': 'reservar_y_cancelar', 'operator': {'type': 'string', 'operation': 'equals'}}],
                  'combinator': 'and'},
                'renameOutput': True, 'outputKey': 'reservar_y_cancelar'
            })
            n['parameters']['rules']['values'] = rules
        break

# Conexiones: Switch nueva rama → Step 6d-prep → Step 6d-1 → Step 6d-2 → (TRUE: 3a→4 / FALSE: 3b) → Step 7
# Reconstruir conexiones del Switch
SWITCH_CONNS = wf['connections'].get('Step 6: Switch por Accion', {'main': []})
new_switch_main = []
output_keys_order = ['cancelar', 'buscar_horarios', 'escalar', 'reservar_y_cancelar', 'sin_accion']
existing_branches = SWITCH_CONNS.get('main', [])
# Mantener primeras 3 ramas existentes (cancelar, buscar_horarios, escalar) + agregar reservar_y_cancelar + fallback
# Mejor: reconstruir desde cero según el orden de las rules
# Esto requiere conocer en qué orden quedaron las rules
# Más seguro: simplemente APPENDEAR la rama nueva (rule 4 = reservar_y_cancelar)
while len(existing_branches) < 4:
    existing_branches.append([])
# Mantener fallback (índice 4 si existe)
if len(existing_branches) > 4:
    fallback = existing_branches[-1]
    existing_branches = existing_branches[:4]
    existing_branches.append(fallback)
existing_branches[3] = [{'node': 'Step 6d-prep: Build Reserva Body', 'type': 'main', 'index': 0}]
SWITCH_CONNS['main'] = existing_branches
wf['connections']['Step 6: Switch por Accion'] = SWITCH_CONNS

# Conexiones internas Step 6d
wf['connections']['Step 6d-prep: Build Reserva Body'] = {'main': [[{'node': 'Step 6d-1: POST Reservar', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6d-1: POST Reservar'] = {'main': [[{'node': 'Step 6d-2: Reserva OK?', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6d-2: Reserva OK?'] = {'main': [
    [{'node': 'Step 6d-3a: PUT Cancelar Viejo', 'type': 'main', 'index': 0}],  # TRUE
    [{'node': 'Step 6d-3b: Escalar Reserva Falla', 'type': 'main', 'index': 0}]  # FALSE
]}
wf['connections']['Step 6d-3a: PUT Cancelar Viejo'] = {'main': [[{'node': 'Step 6d-4: Consolidar Resultado', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6d-4: Consolidar Resultado'] = {'main': [[{'node': 'Step 7: Output Final', 'type': 'main', 'index': 0}]]}
wf['connections']['Step 6d-3b: Escalar Reserva Falla'] = {'main': [[{'node': 'Step 7: Output Final', 'type': 'main', 'index': 0}]]}

ALLOWED = {'saveExecutionProgress', 'saveManualExecutions', 'saveDataErrorExecution', 'saveDataSuccessExecution', 'executionTimeout', 'errorWorkflow', 'timezone', 'executionOrder', 'callerPolicy', 'callerIds'}
put = {'name': wf['name'], 'nodes': wf['nodes'], 'connections': wf['connections'],
       'settings': {k: v for k, v in (wf.get('settings') or {}).items() if k in ALLOWED}}
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}', method='PUT', headers=HEADERS, data=json.dumps(put).encode()), timeout=30)
urllib.request.urlopen(urllib.request.Request(f'{BASE}/workflows/{WID_SUB}/activate', method='POST', headers=HEADERS), timeout=20)
print('Step 6d agregado: rama reservar_y_cancelar al Switch')
