"""
Agrega al workflow v6 (O155MqHgOSaNZ9ye) las 3 tools nuevas para que los
Sub-Agents Confirmar y Cancelar lean/escriban la tabla recordatorios_enviados:

- consultar_recordatorios_abiertos (GET Supabase PostgREST)
- marcar_recordatorio_confirmado (PATCH)
- marcar_recordatorio_cancelado (PATCH)

Y modifica los system prompts de ambos sub-agents para usar la tool nueva
como PASO 0 (antes que cualquier otra cosa).

Patron: toolHttpRequest con headers apikey + Bearer (Supabase service role).
Service role key se inyecta INLINE en headers (a futuro: cred httpHeaderAuth
dedicada para no exponer el JWT en el workflow JSON).
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
SB_URL = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
print(f"v6: '{wf['name']}'  nodes={len(wf['nodes'])}  active={wf.get('active')}")

ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_RECORDATORIOS_TOOLS_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_RECORDATORIOS_TOOLS_{ts}.json")

# Headers comunes para Supabase REST
sb_headers = {
    "parameters": [
        {"name": "apikey", "value": SR},
        {"name": "Authorization", "value": f"Bearer {SR}"},
        {"name": "Content-Type", "value": "application/json"},
        {"name": "Prefer", "value": "return=representation"},
    ]
}

# ============================================================
# Tool 1: consultar_recordatorios_abiertos
# ============================================================
TOOL_CONSULT = "consultar_recordatorios_abiertos"
node_consult = {
    "parameters": {
        "toolDescription": (
            "Consulta los recordatorios enviados al paciente que aun estan abiertos "
            "(sin confirmar ni cancelar) en los ultimos 7 dias. Usar SIEMPRE como "
            "PRIMER paso en Sub-Agent Confirmar y Cancelar para identificar que turnos "
            "el cron de recordatorios espera respuesta. Devuelve array con: "
            "id_cita_dentalink, id_paciente_dentalink, nombre_paciente, fecha_turno, "
            "hora_turno, tipo. Si devuelve >=1 filas, usar esos cita_ids directos. "
            "Si devuelve 0, recien ahi caer al flow legacy de buscar en Dentalink. "
            "El parametro phone es el celular del webhook en formato 549XXXXXXXXXX."
        ),
        "method": "GET",
        "url": f"{SB_URL}/rest/v1/recordatorios_enviados",
        "sendQuery": True,
        "specifyQuery": "keypair",
        "parametersQuery": {
            "values": [
                {"name": "select",
                 "value": "id_cita_dentalink,id_paciente_dentalink,nombre_paciente,fecha_turno,hora_turno,tipo,enviado_at"},
                {"name": "telefono",
                 "value": "=eq.{{ $fromAI('phone', 'celular del paciente formato 549XXXXXXXXXX, sin +', 'string') }}"},
                {"name": "confirmado_at", "value": "is.null"},
                {"name": "cancelado_at", "value": "is.null"},
                {"name": "enviado_at",
                 "value": "=gte.{{ $now.minus({days:7}).toISO() }}"},
                {"name": "order", "value": "fecha_turno,hora_turno"},
            ]
        },
        "sendHeaders": True,
        "specifyHeaders": "keypair",
        "parametersHeaders": {
            "values": [
                {"name": "apikey", "value": SR},
                {"name": "Authorization", "value": f"Bearer {SR}"},
            ]
        },
    },
    "type": "@n8n/n8n-nodes-langchain.toolHttpRequest",
    "typeVersion": 1.1,
    "position": [4800, -800],
    "id": "tool-consult-recordatorios-001",
    "name": TOOL_CONSULT,
}

# ============================================================
# Tool 2: marcar_recordatorio_confirmado
# ============================================================
TOOL_MARK_CONFIRMED = "marcar_recordatorio_confirmado"
node_mark_confirmed = {
    "parameters": {
        "toolDescription": (
            "Marca una fila en recordatorios_enviados como confirmada (confirmado_at=now()). "
            "Llamala DESPUES de confirmar_turno exitoso en Dentalink para cerrar el "
            "recordatorio en la tabla y evitar reprocesarlo. Parametro: id_cita_dentalink "
            "(integer) del turno confirmado."
        ),
        "method": "PATCH",
        "url": f"{SB_URL}/rest/v1/recordatorios_enviados",
        "sendQuery": True,
        "specifyQuery": "keypair",
        "parametersQuery": {
            "values": [
                {"name": "id_cita_dentalink",
                 "value": "=eq.{{ $fromAI('id_cita_dentalink', 'id_cita_dentalink (int) del turno que se acaba de confirmar', 'number') }}"},
                {"name": "confirmado_at", "value": "is.null"},
            ]
        },
        "sendHeaders": True,
        "specifyHeaders": "keypair",
        "parametersHeaders": {
            "values": [
                {"name": "apikey", "value": SR},
                {"name": "Authorization", "value": f"Bearer {SR}"},
                {"name": "Content-Type", "value": "application/json"},
                {"name": "Prefer", "value": "return=minimal"},
            ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={ "confirmado_at": "{{ $now.toISO() }}" }',
    },
    "type": "@n8n/n8n-nodes-langchain.toolHttpRequest",
    "typeVersion": 1.1,
    "position": [4800, -600],
    "id": "tool-mark-confirmed-001",
    "name": TOOL_MARK_CONFIRMED,
}

# ============================================================
# Tool 3: marcar_recordatorio_cancelado
# ============================================================
TOOL_MARK_CANCELLED = "marcar_recordatorio_cancelado"
node_mark_cancelled = {
    "parameters": {
        "toolDescription": (
            "Marca una fila en recordatorios_enviados como cancelada (cancelado_at=now()). "
            "Llamala DESPUES de cancelar_turno exitoso en Dentalink para cerrar el "
            "recordatorio. Parametro: id_cita_dentalink (integer) del turno cancelado."
        ),
        "method": "PATCH",
        "url": f"{SB_URL}/rest/v1/recordatorios_enviados",
        "sendQuery": True,
        "specifyQuery": "keypair",
        "parametersQuery": {
            "values": [
                {"name": "id_cita_dentalink",
                 "value": "=eq.{{ $fromAI('id_cita_dentalink', 'id_cita_dentalink (int) del turno que se acaba de cancelar', 'number') }}"},
                {"name": "cancelado_at", "value": "is.null"},
            ]
        },
        "sendHeaders": True,
        "specifyHeaders": "keypair",
        "parametersHeaders": {
            "values": [
                {"name": "apikey", "value": SR},
                {"name": "Authorization", "value": f"Bearer {SR}"},
                {"name": "Content-Type", "value": "application/json"},
                {"name": "Prefer", "value": "return=minimal"},
            ]
        },
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": '={ "cancelado_at": "{{ $now.toISO() }}" }',
    },
    "type": "@n8n/n8n-nodes-langchain.toolHttpRequest",
    "typeVersion": 1.1,
    "position": [4800, -400],
    "id": "tool-mark-cancelled-001",
    "name": TOOL_MARK_CANCELLED,
}

# Agregar nodos (skip si ya existen)
existing_names = {n["name"] for n in wf["nodes"]}
for n in (node_consult, node_mark_confirmed, node_mark_cancelled):
    if n["name"] in existing_names:
        print(f"  [skip] {n['name']} ya existe")
    else:
        wf["nodes"].append(n)
        print(f"  [add] {n['name']}")

# Wiring ai_tool
def add_tool_conn(tool_name, agent_name):
    conns = wf["connections"].setdefault(tool_name, {}).setdefault("ai_tool", [[]])
    if not conns:
        conns.append([])
    target = {"node": agent_name, "type": "ai_tool", "index": 0}
    if target not in conns[0]:
        conns[0].append(target)
        print(f"  [wire] {tool_name} --ai_tool--> {agent_name}")

add_tool_conn(TOOL_CONSULT, "Sub-Agent Confirmar")
add_tool_conn(TOOL_CONSULT, "Sub-Agent Cancelar")
add_tool_conn(TOOL_MARK_CONFIRMED, "Sub-Agent Confirmar")
add_tool_conn(TOOL_MARK_CANCELLED, "Sub-Agent Cancelar")

# ============================================================
# Modificar system prompt — Sub-Agent Confirmar
# ============================================================
PROMPT_BLOCK_CONFIRMAR = """
= PASO 0 — CONSULTAR TABLA RECORDATORIOS_ENVIADOS (SIEMPRE PRIMERO) =

ANTES de cualquier otro PASO o tool, SIEMPRE llamar `consultar_recordatorios_abiertos` con el `phone` del paciente. Esta es la SOURCE OF TRUTH de que turnos el cron espera confirmacion.

- Si devuelve **0 filas**: significa que no hay recordatorios abiertos (puede ser que el cron no los envio o ya se cerraron). Caer al flow PASO 1 normal (NOTA INTERNA + buscar en Dentalink).

- Si devuelve **>= 1 filas**: estas son las cita_ids EXACTAS que el paciente puede confirmar/cancelar. Esto resuelve el problema de multi-paciente con mismo phone (caso Genefes). No hay que adivinar.

  Comportamiento segun el mensaje del paciente:

  - **Afirmativo generico** ("confirmo", "confirmados", "si", "dale", "voy", "ahi estare", emoji 👍): confirmar TODAS las filas devueltas. Por cada una: llamar `confirmar_turno(cita_id)` y despues `marcar_recordatorio_confirmado(id_cita_dentalink)`. Responder un canned consolidado:
    - 1 fila: "Listo, su turno del [fecha natural] a las [hora natural] queda confirmado. Cualquier consulta nos puede escribir por aca."
    - >=2 filas: "Listo, confirmados los [N] turnos: [nombre1] [hora1 natural] y [nombre2] [hora2 natural]. Cualquier consulta nos puede escribir por aca."

  - **Mencion explicita de UN paciente** ("confirmo el de Jana", "solo Lucas", "el mio"): matchear `nombre_paciente` (parcial, case-insensitive) contra el texto. Confirmar SOLO esa fila. Si no podes desambiguar (ej: dos pacientes con mismo nombre), preguntar "Veo turnos para [nombre1] y [nombre2]. Cual queres confirmar?" y esperar.

  - **Mixto (confirmar + cancelar)** ("confirmo el mio pero cancelo el de Jana"): procesa cada accion. Para la cancelacion, escala al Sub-Agent Cancelar via `escalar_a_secretaria("paciente quiere confirmar X y cancelar Y, dividir flow")` — NO intentes cancelar desde aca (no tenes la tool).

  - **Negativo / no puede ir** ("no voy", "no puedo", "cancelar"): no es confirmacion. Caer al flow PASO 1 normal o dejar que el router lo enrute a Sub-Agent Cancelar.

REGLA CRITICA: si PASO 0 devolvio >=1 filas y vos las confirmaste, NO ejecutes PASO 1/2/3. Ya esta. Solo responder y FIN.
"""

PROMPT_BLOCK_CANCELAR = """
= PASO 0 — CONSULTAR TABLA RECORDATORIOS_ENVIADOS (SIEMPRE PRIMERO) =

ANTES de cualquier otro PASO o tool, SIEMPRE llamar `consultar_recordatorios_abiertos` con el `phone` del paciente. Devuelve los turnos abiertos del cron.

- Si devuelve **0 filas**: caer al flow PASO 1 normal (NOTA INTERNA + buscar Dentalink).

- Si devuelve **>=1 filas**: el paciente probablemente esta cancelando alguno de esos. Pero **a diferencia de Confirmar, NO cancelar sin read-back**.

  - Si devuelve 1 fila: read-back: "Le confirmo que quiere cancelar el turno del [fecha natural] a las [hora natural]?". Si confirma con si/dale -> `cancelar_turno(cita_id)` + `marcar_recordatorio_cancelado(id_cita_dentalink)`.

  - Si devuelve >=2 filas y el paciente NO especifico cual: "Veo [N] turnos pendientes: [nombre1] [hora1] y [nombre2] [hora2]. Cual quiere cancelar?" Esperar respuesta.

  - Si el paciente especifica cual ("cancelo el de Jana"): matchear `nombre_paciente`, read-back, despues cancelar.

  - Para cancelar TODOS ("cancelo los dos"): read-back "Le confirmo que quiere cancelar los [N] turnos del [fecha]: [nombres]?" y proceder.
"""

# Insertar al INICIO del system prompt (despues del R0)
sub_confirmar = next(n for n in wf["nodes"] if n["name"] == "Sub-Agent Confirmar")
sys_msg = sub_confirmar["parameters"]["options"]["systemMessage"]
if "= PASO 0 — CONSULTAR TABLA RECORDATORIOS_ENVIADOS" not in sys_msg:
    # Insertar antes de "= TU FUNCION ESPECIFICA"
    anchor = "= TU FUNCION ESPECIFICA: CONFIRMAR TURNO POST-RECORDATORIO ="
    if anchor in sys_msg:
        sub_confirmar["parameters"]["options"]["systemMessage"] = sys_msg.replace(
            anchor, PROMPT_BLOCK_CONFIRMAR + "\n\n" + anchor
        )
        print(f"  [prompt] Sub-Agent Confirmar: bloque PASO 0 insertado")
    else:
        print(f"  !! anchor no encontrado en Sub-Agent Confirmar — abortando")
        sys.exit(1)
else:
    print(f"  [skip] Sub-Agent Confirmar ya tiene PASO 0")

# Tambien agregar tools al listado dentro del prompt
old_tools_block = (
    "= TOOLS DISPONIBLES =\n"
    "- `ver_turnos_paciente`: chequear id_estado del turno (idempotencia).\n"
    "- `confirmar_turno`: marcar id_estado=18 (Confirmado por WhatsApp). Solo despues de PASO 2.\n"
    "- `escalar_a_secretaria`: derivar a Iri (comprobante, ya anulado, sin contexto, fallas)."
)
new_tools_block = (
    "= TOOLS DISPONIBLES =\n"
    "- `consultar_recordatorios_abiertos`: **SIEMPRE PRIMERA**. Lee la tabla de recordatorios enviados por el cron. Source of truth de que turnos esperan respuesta.\n"
    "- `ver_turnos_paciente`: chequear id_estado del turno (idempotencia, fallback).\n"
    "- `confirmar_turno`: marcar id_estado=18 en Dentalink (Confirmado por WhatsApp).\n"
    "- `marcar_recordatorio_confirmado`: cerrar la fila en recordatorios_enviados (confirmado_at). Llamar DESPUES de confirmar_turno OK.\n"
    "- `escalar_a_secretaria`: derivar a Iri (comprobante, ya anulado, sin contexto, fallas)."
)
sys_msg_now = sub_confirmar["parameters"]["options"]["systemMessage"]
if old_tools_block in sys_msg_now:
    sub_confirmar["parameters"]["options"]["systemMessage"] = sys_msg_now.replace(old_tools_block, new_tools_block)
    print(f"  [prompt] Sub-Agent Confirmar: tools block actualizado")
else:
    print(f"  [warn] Sub-Agent Confirmar: tools block original no encontrado — manual review needed")

# ============================================================
# Modificar system prompt — Sub-Agent Cancelar
# ============================================================
sub_cancelar = next(n for n in wf["nodes"] if n["name"] == "Sub-Agent Cancelar")
sys_msg_c = sub_cancelar["parameters"]["options"]["systemMessage"]
if "= PASO 0 — CONSULTAR TABLA RECORDATORIOS_ENVIADOS" not in sys_msg_c:
    anchor = "= TU FUNCION ESPECIFICA: CANCELAR TURNO ="
    if anchor in sys_msg_c:
        sub_cancelar["parameters"]["options"]["systemMessage"] = sys_msg_c.replace(
            anchor, PROMPT_BLOCK_CANCELAR + "\n\n" + anchor
        )
        print(f"  [prompt] Sub-Agent Cancelar: bloque PASO 0 insertado")
    else:
        print(f"  !! anchor no encontrado en Sub-Agent Cancelar")
        sys.exit(1)
else:
    print(f"  [skip] Sub-Agent Cancelar ya tiene PASO 0")

old_tools_cancelar = (
    "= TOOLS DISPONIBLES =\n"
    "- `ver_turnos_paciente`: localizar el turno activo a cancelar.\n"
    "- `cancelar_turno`: anular con {id_estado:1}. SOLO despues de read-back del paciente.\n"
    "- `escalar_a_secretaria`: derivar a Iri si no encuentra turno o si tools fallan."
)
new_tools_cancelar = (
    "= TOOLS DISPONIBLES =\n"
    "- `consultar_recordatorios_abiertos`: **SIEMPRE PRIMERA**. Lee recordatorios abiertos para identificar el turno a cancelar sin adivinar.\n"
    "- `ver_turnos_paciente`: localizar el turno activo (fallback si la tabla no tiene nada).\n"
    "- `cancelar_turno`: anular con {id_estado:1}. SOLO despues de read-back del paciente.\n"
    "- `marcar_recordatorio_cancelado`: cerrar la fila en recordatorios_enviados (cancelado_at). Llamar DESPUES de cancelar_turno OK.\n"
    "- `escalar_a_secretaria`: derivar a Iri si no encuentra turno o si tools fallan."
)
sys_msg_c_now = sub_cancelar["parameters"]["options"]["systemMessage"]
if old_tools_cancelar in sys_msg_c_now:
    sub_cancelar["parameters"]["options"]["systemMessage"] = sys_msg_c_now.replace(old_tools_cancelar, new_tools_cancelar)
    print(f"  [prompt] Sub-Agent Cancelar: tools block actualizado")
else:
    print(f"  [warn] Sub-Agent Cancelar: tools block original no encontrado")

# ============================================================
# PUT
# ============================================================
allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
payload = {"name": wf["name"], "nodes": wf["nodes"],
           "connections": wf["connections"], "settings": settings}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]

print(f"\nPUT /workflows/{WF} (size ~{len(json.dumps(payload))} chars) ...")
r = requests.put(f"{N8N}/api/v1/workflows/{WF}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
print(f"  status: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:800])
    sys.exit(1)

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_RECORDATORIOS_TOOLS_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_RECORDATORIOS_TOOLS_{ts}.json")

# Verify
print(f"\n=== VERIFY ===")
print(f"  total nodos: {len(wf_post['nodes'])}")
for tname in (TOOL_CONSULT, TOOL_MARK_CONFIRMED, TOOL_MARK_CANCELLED):
    found = next((n for n in wf_post["nodes"] if n["name"] == tname), None)
    print(f"  {tname}: {'OK' if found else 'MISSING'}")
print(f"\n  ai_tool conexiones nuevas:")
for src in (TOOL_CONSULT, TOOL_MARK_CONFIRMED, TOOL_MARK_CANCELLED):
    conn = wf_post["connections"].get(src, {}).get("ai_tool", [[]])
    if conn:
        targets = [t["node"] for t in conn[0]]
        print(f"    {src} --> {targets}")
print(f"\nactive: {wf_post.get('active')}")
print(f"\nROLLBACK: python -c \"import requests, json; ...\"  o restore desde v6_PRE_RECORDATORIOS_TOOLS_{ts}.json")
