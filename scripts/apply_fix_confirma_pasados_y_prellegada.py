"""
Fix 2026-06-19 (autorizado por Lucas via WhatsApp "metele... robusto y testeado"):

BUG CRITICO: el bot confirma turnos PASADOS.
  Causa raiz: el tool `consultar_recordatorios_abiertos` (PASO 0 del Sub-Agent
  Confirmar) lee `recordatorios_enviados` con filtro
  `confirmado_at=is.null&cancelado_at=is.null` SIN filtro de fecha futura.
  Devuelve filas viejas que nunca se cerraron (paciente nunca confirmo/cancelo
  en su momento). Cuando el paciente ahora dice "confirmo", el agente itera y
  confirma TODAS las filas abiertas, incluido el turno ya pasado -> lo marca
  id_estado=18 en Dentalink y se lo recita al paciente.
  Casos reales 19/6: Delfina (3 jun + 23 jun), Geronimo (8 jun + 23 jun).

BUG CATALINA: "Estoy llegando" -> el Router clasifica confirmar/cancelar (con
  recordatorio reciente en memoria) en vez de silenciar. El Sub-WF Cancelar es
  codigo deterministico sin LLM -> no puede auto-silenciar. La regla pre-llegada
  vive solo en los Sub-Agents (General/Confirmar), nunca en el Router.

FIXES (3, un solo PUT):
  1. [DETERMINISTICO] consultar_recordatorios_abiertos.url -> agrega
     &fecha_turno=gte.<hoy ARG> (URL pasa a expresion n8n con $now).
  2. [PROMPT, defensa en profundidad] Sub-Agent Confirmar PASO 0 -> regla
     "NUNCA confirmes turnos pasados".
  3. [PROMPT] Router -> regla 1.5 "AVISO DE LLEGADA -> consulta_general".

Backup pre/post en workflows/history/. Verificacion post via GET fresco.
"""
import sys, json, datetime, urllib.request, copy
sys.path.insert(0, 'scripts')
from lib_env import require

BASE = require('N8N_BASE_URL').rstrip('/')
KEY = require('N8N_API_KEY')
WID = 'O155MqHgOSaNZ9ye'
TS = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
ALLOWED_SETTINGS = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution',
    'saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder',
    'callerPolicy','callerIds'}

def api(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE+path, data=data, method=method,
        headers={'X-N8N-API-KEY':KEY,'Content-Type':'application/json','Accept':'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=120))

def node(nodes, name):
    for n in nodes:
        if n['name']==name: return n
    raise SystemExit(f'node not found: {name}')

# ---------- The three edits (as pure string transforms, idempotent) ----------
DATE_FILTER = "&fecha_turno=gte.{{ $now.setZone('America/Argentina/Buenos_Aires').toFormat('yyyy-MM-dd') }}"

CONFIRMAR_ANCHOR = "Esta es la SOURCE OF TRUTH de que turnos el cron espera confirmacion.\n\n"
CONFIRMAR_RULE = (
    "**REGLA FECHA - NUNCA CONFIRMES TURNOS PASADOS (CRITICO 2026-06-19, caso Delfina/Geronimo)**: "
    "solo confirmas/recitas turnos con `fecha_turno` de HOY o posterior. La tool "
    "`consultar_recordatorios_abiertos` ya filtra y devuelve SOLO turnos de hoy en adelante; "
    "pero si por cualquier motivo vieras una fila con `fecha_turno` ANTERIOR a hoy, IGNORALA por "
    "completo: no la confirmes, no la menciones, no la recites. Si tras descartar las pasadas no "
    "queda ninguna fila, trata como 0 filas (cae al flow PASO 1 normal). JAMAS armes un output tipo "
    "\"confirmados los 2 turnos: [fecha pasada] y [fecha futura]\" - el turno de fecha pasada ya "
    "ocurrio y confirmarlo ensucia la agenda real de la doctora.\n\n"
)

ROUTER_ANCHOR = "**2. confirmar_post_recordatorio**"
ROUTER_RULE = (
    "**1.5. AVISO DE LLEGADA / EN CAMINO (PRIORIDAD ALTA - pedido Dra 2026-06-19, caso Catalina) -> consulta_general:**\n"
    "Si el paciente avisa que esta YENDO o YA LLEGO al consultorio (no pide nada, solo informa que "
    "esta en camino, cerca o en la puerta), clasifica SIEMPRE `consulta_general` (el Sub-Agent "
    "General lo silencia con [NO_REPLY]). NUNCA `cancelar_o_reprogramar` ni `confirmar_post_recordatorio`.\n"
    "Frases gatillo (lista abierta, usa criterio): \"estoy llegando\", \"llegando\", \"ya llegue\", "
    "\"ya llego\", \"ya estoy aca/aqui/ahi\", \"estoy en la puerta\", \"estoy abajo\", \"subiendo\", "
    "\"en camino\", \"voy en camino\", \"estoy yendo\", \"yendo para alla\", \"estoy a [N] cuadras\", "
    "\"a dos cuadras\", \"ya estoy cerca\", \"estoy cerca\".\n"
    "Esta regla MANDA sobre los emojis de confirmacion: \"Estoy llegando \U0001f64f\" -> "
    "`consulta_general` (NO confirmar, aunque traiga \U0001f64f/\U0001f44d).\n"
    "EXCEPCION (NO confundir con confirmacion de asistencia futura): \"voy\", \"ahi voy\", "
    "\"ahi estare\", \"alli estare\", \"voy a ir\" SIN \"en camino\"/\"llegando\"/\"ya estoy\" en "
    "respuesta a un recordatorio = confirmacion -> `confirmar_post_recordatorio`. Solo es aviso de "
    "llegada cuando el paciente esta FISICAMENTE yendo/llegando AHORA. Si hay dolor/urgencia, "
    "urgencia_dolor manda.\n\n"
)

def main():
    wf = api('GET', f'/api/v1/workflows/{WID}')
    nodes = wf['nodes']
    # backup pre
    pre = f'workflows/history/v6_PRE_FIX_PASADOS_PRELLEGADA_{TS}.json'
    json.dump(wf, open(pre,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('backup pre ->', pre)

    changes = []

    # --- Fix 1: date filter on consultar_recordatorios_abiertos ---
    ct = node(nodes, 'consultar_recordatorios_abiertos')
    url = ct['parameters']['url']
    if 'fecha_turno=gte' in url:
        print('  [1] date filter YA presente, skip')
    else:
        assert '&order=fecha_turno,hora_turno' in url, 'order anchor missing in url'
        new_url = url.replace('&order=fecha_turno,hora_turno',
                              DATE_FILTER + '&order=fecha_turno,hora_turno', 1)
        if not new_url.startswith('='):
            new_url = '=' + new_url      # marcar como expresion n8n
        ct['parameters']['url'] = new_url
        changes.append('1: consultar_recordatorios_abiertos +fecha_turno=gte hoy (expr)')

    # --- Fix 2: anti-past rule in Sub-Agent Confirmar PASO 0 ---
    sa = node(nodes, 'Sub-Agent Confirmar')
    sm = sa['parameters']['options']['systemMessage']
    if 'NUNCA CONFIRMES TURNOS PASADOS' in sm:
        print('  [2] regla anti-pasados YA presente, skip')
    else:
        assert sm.count(CONFIRMAR_ANCHOR)==1, f'confirmar anchor count={sm.count(CONFIRMAR_ANCHOR)}'
        sa['parameters']['options']['systemMessage'] = sm.replace(
            CONFIRMAR_ANCHOR, CONFIRMAR_ANCHOR + CONFIRMAR_RULE, 1)
        changes.append('2: Sub-Agent Confirmar PASO 0 regla anti-turnos-pasados')

    # --- Fix 3: pre-llegada rule in Router ---
    rt = node(nodes, 'Router - Clasificar Intent')
    rsm = rt['parameters']['options']['systemMessage']
    if 'AVISO DE LLEGADA / EN CAMINO' in rsm:
        print('  [3] regla pre-llegada Router YA presente, skip')
    else:
        assert rsm.count(ROUTER_ANCHOR)==1, f'router anchor count={rsm.count(ROUTER_ANCHOR)}'
        rt['parameters']['options']['systemMessage'] = rsm.replace(
            ROUTER_ANCHOR, ROUTER_RULE + ROUTER_ANCHOR, 1)
        changes.append('3: Router regla 1.5 aviso-de-llegada -> consulta_general')

    if not changes:
        print('Nada que aplicar (todo idempotente).'); return

    # --- PUT (solo keys permitidas; patron probado: staticData solo si no es None) ---
    settings = {k:v for k,v in (wf.get('settings') or {}).items() if k in ALLOWED_SETTINGS}
    payload = {'name': wf['name'], 'nodes': nodes, 'connections': wf['connections'],
               'settings': settings}
    if wf.get('staticData') is not None:
        payload['staticData'] = wf['staticData']
    print('\nAplicando:')
    for c in changes: print('  -', c)
    api('PUT', f'/api/v1/workflows/{WID}', payload)
    print('PUT OK')

    # --- backup post + verificacion ---
    wf2 = api('GET', f'/api/v1/workflows/{WID}')
    post = f'workflows/history/v6_POST_FIX_PASADOS_PRELLEGADA_{TS}.json'
    json.dump(wf2, open(post,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('backup post ->', post)
    n2 = wf2['nodes']
    url2 = node(n2,'consultar_recordatorios_abiertos')['parameters']['url']
    sm2 = node(n2,'Sub-Agent Confirmar')['parameters']['options']['systemMessage']
    rsm2 = node(n2,'Router - Clasificar Intent')['parameters']['options']['systemMessage']
    print('\nVERIFICACION (GET fresco):')
    print('  fecha_turno=gte en consultar:', 'fecha_turno=gte' in url2)
    print('  url es expresion (= prefix):', url2.startswith('='))
    print('  regla anti-pasados en Confirmar:', 'NUNCA CONFIRMES TURNOS PASADOS' in sm2)
    print('  regla pre-llegada en Router:', 'AVISO DE LLEGADA / EN CAMINO' in rsm2)
    print('  nodes:', len(n2), '| active:', wf2.get('active'))
    # webhook preservado
    wh=[n for n in n2 if n.get('type','').endswith('webhook')]
    for w in wh:
        print('  webhookId:', w.get('webhookId'), '| path:', w['parameters'].get('path'))
    ok = ('fecha_turno=gte' in url2 and url2.startswith('=') and
          'NUNCA CONFIRMES TURNOS PASADOS' in sm2 and 'AVISO DE LLEGADA / EN CAMINO' in rsm2)
    print('\n', 'TODOS LOS FIXES VERIFICADOS OK' if ok else 'XX VERIFICACION FALLO')

if __name__=='__main__':
    main()
