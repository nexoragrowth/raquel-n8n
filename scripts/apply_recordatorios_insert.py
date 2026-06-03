"""
Aplica al cron de Recordatorios (7RqTApkvVavRmq3R) los 3 cambios:

1. Modifica 'Preparar mensaje' jsCode: agrega 4 fields al return
   (id_paciente, fecha_turno, hora_turno, chat_remote_jid) para usar
   en el INSERT a recordatorios_enviados.

2. Agrega nodo 'Insert recordatorios_enviados' (Postgres -> Supabase,
   cred xwvjww5Odcxiy1K9) entre 'Enviar WhatsApp' y 'Guardar en Chat Memory'.

3. Agrega nodo 'Webhook Manual Recordatorios' (path trigger-recordatorios-manual)
   conectado a 'Fecha Manana' para triggerear el cron on-demand.

Backup pre ya tomado (recordatorios_PRE_INSERT_TABLA_20260525_224235.json).
Hace backup post + GET de verificacion post-PUT.
"""
import json
import re
import sys
import copy
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require, env

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF_ID = env("N8N_WORKFLOW_RECORDATORIOS_ID", "7RqTApkvVavRmq3R")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}
PG_CRED_ID = "xwvjww5Odcxiy1K9"

REPO = Path(__file__).resolve().parents[1]

print(f"GET workflow {WF_ID} ...")
wf = requests.get(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H, timeout=30).json()
print(f"  '{wf['name']}'  nodes={len(wf['nodes'])}  active={wf.get('active')}")

# Sanity: el backup pre ya esta hecho. Re-tomo otro para esta corrida especifica.
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
bak_pre = REPO / "workflows" / "history" / f"recordatorios_PRE_APPLY_{ts}.json"
bak_pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  backup pre (this run) -> {bak_pre.relative_to(REPO)}")

# ============================================================
# CAMBIO 1: Modificar 'Preparar mensaje' jsCode
# ============================================================
prep = next(n for n in wf["nodes"] if n["name"] == "Preparar mensaje")
js = prep["parameters"]["jsCode"]
print(f"\n[CAMBIO 1] 'Preparar mensaje' jsCode (orig {len(js)} chars)")

if "id_paciente, fecha_turno, hora_turno, chat_remote_jid" in js:
    print("  (already patched — skipping field additions)")
else:
    # Insertar vars auxiliares antes de "TEMPLATES OFICIALES" o al final si no encuentra el anchor
    additions = (
        "\n// === FIELDS para recordatorios_enviados ===\n"
        "const id_paciente = (pData && pData.id) ? pData.id : null;\n"
        "const fecha_turno = fecha || null;\n"
        "const hora_turno = cita.hora_inicio || null;\n"
        "const chat_remote_jid = celular ? celular + \"@s.whatsapp.net\" : \"\";\n"
    )
    anchor = "// === TEMPLATES OFICIALES ==="
    if anchor in js:
        js = js.replace(anchor, additions + "\n" + anchor)
        print("  insertado bloque de fields antes de TEMPLATES OFICIALES")
    else:
        # Fallback: agregar al principio (mejor que romper)
        js = additions + "\n" + js
        print("  insertado bloque de fields al principio (anchor TEMPLATES no encontrado)")

    # Modificar cada return { json: {...tipo_recordatorio} } agregando los 4 fields
    def patch_return(m):
        block = m.group(0)
        if "id_paciente" in block:
            return block
        # tipo_recordatorio puede ser ultima key sin coma, agregamos con coma despues
        return block.replace(
            "tipo_recordatorio",
            "tipo_recordatorio, id_paciente, fecha_turno, hora_turno, chat_remote_jid",
        )

    patched = re.sub(
        r"return\s*\{\s*json\s*:\s*\{[^}]+\}\s*\}\s*;?",
        patch_return, js, flags=re.DOTALL,
    )
    if patched == js:
        print("  !! NO se patcheo ningun return — abortando para no dejar a medias")
        sys.exit(1)
    js = patched
    print("  returns patcheados con los 4 fields nuevos")

prep["parameters"]["jsCode"] = js

# ============================================================
# CAMBIO 2: Agregar nodo 'Insert recordatorios_enviados'
# ============================================================
INSERT_NODE_NAME = "Insert recordatorios_enviados"
# Position: justo despues de Enviar WhatsApp ([1808, -208]) — un poco a la derecha
insert_node = {
    "parameters": {
        "operation": "insert",
        "schema": {"__rl": True, "value": "public", "mode": "list"},
        "table": {"__rl": True, "value": "recordatorios_enviados", "mode": "list"},
        "columns": {
            "mappingMode": "defineBelow",
            "value": {
                "telefono": "={{ $('Preparar mensaje').item.json.phone }}",
                "chat_remote_jid": "={{ $('Preparar mensaje').item.json.chat_remote_jid }}",
                "id_cita_dentalink": "={{ $('Preparar mensaje').item.json.cita_id }}",
                "id_paciente_dentalink": "={{ $('Preparar mensaje').item.json.id_paciente }}",
                "nombre_paciente": "={{ $('Preparar mensaje').item.json.nombre }}",
                "fecha_turno": "={{ $('Preparar mensaje').item.json.fecha_turno }}",
                "hora_turno": "={{ $('Preparar mensaje').item.json.hora_turno }}",
                "tipo": "={{ $('Preparar mensaje').item.json.tipo_recordatorio }}",
                "workflow_execution_id": "={{ $execution.id }}",
            },
            "matchingColumns": [],
            "schema": [
                {"id": "telefono", "displayName": "telefono", "required": True, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                {"id": "chat_remote_jid", "displayName": "chat_remote_jid", "required": True, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                {"id": "id_cita_dentalink", "displayName": "id_cita_dentalink", "required": True, "defaultMatch": False, "display": True, "type": "number", "canBeUsedToMatch": True},
                {"id": "id_paciente_dentalink", "displayName": "id_paciente_dentalink", "required": True, "defaultMatch": False, "display": True, "type": "number", "canBeUsedToMatch": True},
                {"id": "nombre_paciente", "displayName": "nombre_paciente", "required": True, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                {"id": "fecha_turno", "displayName": "fecha_turno", "required": True, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                {"id": "hora_turno", "displayName": "hora_turno", "required": True, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                {"id": "tipo", "displayName": "tipo", "required": True, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
                {"id": "workflow_execution_id", "displayName": "workflow_execution_id", "required": False, "defaultMatch": False, "display": True, "type": "string", "canBeUsedToMatch": True},
            ],
        },
        "options": {},
    },
    "type": "n8n-nodes-base.postgres",
    "typeVersion": 2.6,
    "position": [2032, -208],
    "id": "insert-recordatorios-uuid-001",
    "name": INSERT_NODE_NAME,
    "credentials": {"postgres": {"id": PG_CRED_ID, "name": "Postgres account"}},
}

# Solo agregar si no existe
if not any(n["name"] == INSERT_NODE_NAME for n in wf["nodes"]):
    wf["nodes"].append(insert_node)
    print(f"\n[CAMBIO 2] '{INSERT_NODE_NAME}' agregado")
else:
    print(f"\n[CAMBIO 2] '{INSERT_NODE_NAME}' ya existe — skip add")

# ============================================================
# CAMBIO 3: Agregar 'Webhook Manual Recordatorios'
# ============================================================
WH_NODE_NAME = "Webhook Manual Recordatorios"
wh_path = "trigger-recordatorios-manual"
wh_node = {
    "parameters": {
        "httpMethod": "POST",
        "path": wh_path,
        "responseMode": "lastNode",
        "options": {},
    },
    "type": "n8n-nodes-base.webhook",
    "typeVersion": 2,
    "position": [-176, 32],
    "id": "wh-manual-recordatorios-001",
    "name": WH_NODE_NAME,
    "webhookId": wh_path,
}
if not any(n["name"] == WH_NODE_NAME for n in wf["nodes"]):
    wf["nodes"].append(wh_node)
    print(f"[CAMBIO 3] '{WH_NODE_NAME}' agregado (path /{wh_path})")
else:
    print(f"[CAMBIO 3] '{WH_NODE_NAME}' ya existe — skip add")

# ============================================================
# RECONNECT
# ============================================================
print(f"\n[CONNECTIONS] reconectando ...")
conns = wf["connections"]

# Remover: Enviar WhatsApp -> Guardar en Chat Memory (si existe)
if "Enviar WhatsApp" in conns:
    new_branches = []
    for branch in conns["Enviar WhatsApp"].get("main", []):
        new_branch = [c for c in (branch or []) if c["node"] != "Guardar en Chat Memory"]
        new_branches.append(new_branch)
    conns["Enviar WhatsApp"]["main"] = new_branches

# Agregar: Enviar WhatsApp -> Insert recordatorios_enviados
conns.setdefault("Enviar WhatsApp", {}).setdefault("main", [[]])
if not conns["Enviar WhatsApp"]["main"]:
    conns["Enviar WhatsApp"]["main"] = [[]]
# Asegurar que existe el branch 0
while len(conns["Enviar WhatsApp"]["main"]) < 1:
    conns["Enviar WhatsApp"]["main"].append([])
# Append si no esta
target_insert = {"node": INSERT_NODE_NAME, "type": "main", "index": 0}
if target_insert not in conns["Enviar WhatsApp"]["main"][0]:
    conns["Enviar WhatsApp"]["main"][0].append(target_insert)

# Agregar: Insert recordatorios_enviados -> Guardar en Chat Memory
conns.setdefault(INSERT_NODE_NAME, {})["main"] = [[
    {"node": "Guardar en Chat Memory", "type": "main", "index": 0}
]]

# Agregar: Webhook Manual Recordatorios -> Fecha Manana
fm_name = next((n["name"] for n in wf["nodes"] if "fecha" in n["name"].lower() and "mañana" in n["name"].lower() or "mana" in n["name"].lower().replace("ñ", "n")), None)
if not fm_name:
    # try direct
    fm_name = next((n["name"] for n in wf["nodes"] if "fecha" in n["name"].lower()), None)
print(f"  Fecha Manana node detectado como: {fm_name!r}")
if fm_name:
    conns.setdefault(WH_NODE_NAME, {})["main"] = [[
        {"node": fm_name, "type": "main", "index": 0}
    ]]
else:
    print("  !! No encontre el nodo 'Fecha Mañana' — webhook manual NO conectado, abortando")
    sys.exit(1)

# ============================================================
# PUT al API (solo keys permitidas)
# ============================================================
allowed_settings_keys = {"saveExecutionProgress", "saveManualExecutions",
                         "saveDataErrorExecution", "saveDataSuccessExecution",
                         "executionTimeout", "errorWorkflow", "timezone",
                         "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed_settings_keys}

payload = {
    "name": wf["name"],
    "nodes": wf["nodes"],
    "connections": wf["connections"],
    "settings": settings,
}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]

print(f"\nPUT /workflows/{WF_ID} (payload size ~{len(json.dumps(payload))} chars) ...")
r = requests.put(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
if r.status_code >= 400:
    print(f"  !! HTTP {r.status_code}: {r.text[:500]}")
    sys.exit(1)
print(f"  ok ({r.status_code})")

# Re-fetch para backup post
wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF_ID}", headers=H, timeout=30).json()
ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
bak_post = REPO / "workflows" / "history" / f"recordatorios_POST_APPLY_{ts2}.json"
bak_post.write_text(json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nbackup post -> {bak_post.relative_to(REPO)}")

# Verificacion estructural
print(f"\n=== Verificacion post-PUT ===")
print(f"  total nodos: {len(wf_post['nodes'])}")
for n in wf_post["nodes"]:
    marker = ""
    if n["name"] in (INSERT_NODE_NAME, WH_NODE_NAME):
        marker = "  [NUEVO]"
    print(f"  {n['name']}{marker}")
print(f"\n  Conexiones de Enviar WhatsApp -> {[c['node'] for c in wf_post['connections'].get('Enviar WhatsApp', {}).get('main', [[]])[0]]}")
print(f"  Conexiones de {INSERT_NODE_NAME} -> {[c['node'] for c in wf_post['connections'].get(INSERT_NODE_NAME, {}).get('main', [[]])[0]]}")
print(f"  Conexiones de {WH_NODE_NAME} -> {[c['node'] for c in wf_post['connections'].get(WH_NODE_NAME, {}).get('main', [[]])[0]]}")
print(f"\nactive: {wf_post.get('active')}")
print(f"\nWEBHOOK MANUAL URL: {N8N}/webhook/{wh_path}")
print(f"  (curl -XPOST -H 'Content-Type: application/json' -d '{{}}' {N8N}/webhook/{wh_path})")
print(f"\nROLLBACK: python scripts/rollback_recordatorios.py")
