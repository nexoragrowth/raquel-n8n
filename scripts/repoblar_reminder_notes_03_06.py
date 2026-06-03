"""URGENTE - Repoblar reminder_notes que el cron del 03/06 NO grabo en
n8n_chat_histories por el bug del nodo iterar (1 de 5 grabados).

Datos extraidos del exec 68033 nodo 'Preparar mensaje'. Pacientes faltantes:
  - Brenda 5493878641044, cita 8033, 2026-06-05 10:20 hs, id_paciente=378
  - Samanta de los Ángeles 5493883299947, cita 8032, 2026-06-05 09:40 hs, id_paciente=128
  - Helena Sofía 5493884175498, cita 8027, 2026-06-05 09:00 hs, id_paciente=618
  - Benjamin 5493884175498, cita 8000, 2026-06-05 08:30 hs, id_paciente=55

Inserta SOLO en n8n_chat_histories (NO toca Evolution, NO re-manda WhatsApp).
Por cada paciente, 2 filas: el mensaje recordatorio AUREA + la NOTA INTERNA.

Modo: --apply
"""
from __future__ import annotations
import os, sys, io, json, time
import requests
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

# Datos exactos del exec 68033 (los 4 faltantes)
PACIENTES = [
    {
        "phone": "5493878641044", "nombre": "Brenda", "cita_id": "8033",
        "fecha": "2026-06-05", "hora": "10:20", "id_paciente": "378",
        "tipo": "72h",
        "msg_recordatorio": "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\nEstimada Brenda,\nLe recordamos su turno con la Dra. Rodríguez Raquel:\n\n📅 Viernes 5 de junio de 2026\n🕔 10:20 hs\n📍 Balcarce Nº37, 2º piso\n\nLe pedimos confirmar su asistencia respondiendo a este mensaje para conservar su turno.\n\n⚠️ Importante:\n• Si su turno está confirmado y no asiste al mismo, de igual manera deberá abonar el control.\n• Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.\n\nEsperamos su confirmación, gracias por elegirnos 💙",
    },
    {
        "phone": "5493883299947", "nombre": "Samanta de los Ángeles", "cita_id": "8032",
        "fecha": "2026-06-05", "hora": "09:40", "id_paciente": "128",
        "tipo": "72h",
        "msg_recordatorio": "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\nEstimada Samanta de los Ángeles,\nLe recordamos su turno con la Dra. Rodríguez Raquel:\n\n📅 Viernes 5 de junio de 2026\n🕔 09:40 hs\n📍 Balcarce Nº37, 2º piso\n\nLe pedimos confirmar su asistencia respondiendo a este mensaje para conservar su turno.\n\n⚠️ Importante:\n• Si su turno está confirmado y no asiste al mismo, de igual manera deberá abonar el control.\n• Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.\n\nEsperamos su confirmación, gracias por elegirnos 💙",
    },
    {
        "phone": "5493884175498", "nombre": "Helena Sofía", "cita_id": "8027",
        "fecha": "2026-06-05", "hora": "09:00", "id_paciente": "618",
        "tipo": "72h",
        "msg_recordatorio": "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\nEstimada Helena Sofía,\nLe recordamos su turno con la Dra. Rodríguez Raquel:\n\n📅 Viernes 5 de junio de 2026\n🕔 09:00 hs\n📍 Balcarce Nº37, 2º piso\n\nLe pedimos confirmar su asistencia respondiendo a este mensaje para conservar su turno.\n\n⚠️ Importante:\n• Si su turno está confirmado y no asiste al mismo, de igual manera deberá abonar el control.\n• Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.\n\nEsperamos su confirmación, gracias por elegirnos 💙",
    },
    {
        "phone": "5493884175498", "nombre": "Benjamin", "cita_id": "8000",
        "fecha": "2026-06-05", "hora": "08:30", "id_paciente": "55",
        "tipo": "72h",
        "msg_recordatorio": "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\nEstimado/a Benjamin,\nLe recordamos su turno con la Dra. Rodríguez Raquel:\n\n📅 Viernes 5 de junio de 2026\n🕔 08:30 hs\n📍 Balcarce Nº37, 2º piso\n\nLe pedimos confirmar su asistencia respondiendo a este mensaje para conservar su turno.\n\n⚠️ Importante:\n• Si su turno está confirmado y no asiste al mismo, de igual manera deberá abonar el control.\n• Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.\n\nEsperamos su confirmación, gracias por elegirnos 💙",
    },
]


def build_internal_note(p):
    # mismo formato que el cron actualizado
    dias = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"]
    meses = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"]
    from datetime import datetime
    f = datetime.strptime(p["fecha"], "%Y-%m-%d")
    # python weekday: 0=lunes, datetime.weekday()
    # dias array: 0=domingo  -> ajuste
    weekday = (f.weekday() + 1) % 7  # 0=domingo
    fecha_natural = f"{dias[weekday]} {f.day} de {meses[f.month-1]} de {f.year}"
    return (
        f"[NOTA INTERNA - contexto del último recordatorio enviado, NO mencionar al paciente]\n"
        f"Acabo de enviar un recordatorio {p['tipo']} del siguiente turno:\n"
        f"- Cita Dentalink ID: {p['cita_id']}\n"
        f"- ID Paciente: {p['id_paciente']}\n"
        f"- Paciente: {p['nombre']}\n"
        f"- Fecha: {fecha_natural}\n"
        f"- Hora: {p['hora']}\n"
        f"- Profesional: Dra. Rodríguez Raquel\n"
        f"Si el paciente responde sobre este turno, ya conocés todos los datos. NO le pidas que repita fecha/hora/profesional."
    )


# Build workflow ad-hoc: solo INSERT, sin Evolution
v6 = requests.get(f"{BASE}/api/v1/workflows/O155MqHgOSaNZ9ye", headers=H, timeout=60).json()
pg_node = next(n for n in v6["nodes"] if n["type"] == "n8n-nodes-base.postgres")
PG_CREDS = pg_node.get("credentials", {})

# Construir array de items: 8 inserts (4 pacientes x 2 msgs c/u)
items_data = []
for p in PACIENTES:
    msg_rec = {
        "type": "ai", "content": p["msg_recordatorio"],
        "tool_calls": [], "additional_kwargs": {"source": "reminder_note"},
        "response_metadata": {}, "invalid_tool_calls": []
    }
    msg_int = {
        "type": "ai", "content": build_internal_note(p),
        "tool_calls": [], "additional_kwargs": {"source": "reminder_note"},
        "response_metadata": {}, "invalid_tool_calls": []
    }
    items_data.append({"session_id": p["phone"], "message_json": json.dumps(msg_rec, ensure_ascii=False)})
    items_data.append({"session_id": p["phone"], "message_json": json.dumps(msg_int, ensure_ascii=False)})

# Workflow test que solo hace INSERT
WEBHOOK_PATH = "test-repoblar-reminders"
nodes = [
    {"name": "Webhook", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [200, 300],
     "parameters": {"path": WEBHOOK_PATH, "httpMethod": "POST", "responseMode": "lastNode"}, "webhookId": WEBHOOK_PATH},
    {"name": "Build Items", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [400, 300],
     "parameters": {"jsCode": f"return {json.dumps([{'json': it} for it in items_data], ensure_ascii=False)};"}},
    {"name": "INSERT to chat_histories", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": [600, 300],
     "parameters": {
         "operation": "executeQuery",
         "query": "INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb) RETURNING id, session_id",
         "options": {"queryReplacement": "={{ $json.session_id }}, ={{ $json.message_json }}"},
     },
     "credentials": PG_CREDS},
]
connections = {
    "Webhook": {"main": [[{"node": "Build Items", "type": "main", "index": 0}]]},
    "Build Items": {"main": [[{"node": "INSERT to chat_histories", "type": "main", "index": 0}]]},
}

body = {"name": "TEST - Repoblar Reminders 03-06", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}

existing = requests.get(f"{BASE}/api/v1/workflows", headers=H, params={"name": body["name"]}, timeout=30).json()
test_wf = next((w for w in existing.get("data", []) if w.get("name") == body["name"]), None)
if test_wf:
    wid = test_wf["id"]
    print(f"[1] reuso {wid}")
    requests.put(f"{BASE}/api/v1/workflows/{wid}", headers=H, json=body, timeout=40).raise_for_status()
else:
    r = requests.post(f"{BASE}/api/v1/workflows", headers=H, json=body, timeout=40)
    if not r.ok: print("FAIL", r.text[:300]); sys.exit(2)
    wid = r.json()["id"]
    print(f"[1] creado {wid}")

requests.post(f"{BASE}/api/v1/workflows/{wid}/activate", headers=H, timeout=30)
print(f"[2] activado")
r = requests.post(f"{BASE.replace('/api/v1','')}/webhook/{WEBHOOK_PATH}", json={}, timeout=30)
print(f"[3] webhook: {r.status_code}")
time.sleep(3)

ex = requests.get(f"{BASE}/api/v1/executions?workflowId={wid}&limit=1", headers=H, timeout=30).json()
if not ex.get("data"): print("!! no exec"); sys.exit(0)
exec_id = ex["data"][0]["id"]
print(f"[4] exec id: {exec_id} status: {ex['data'][0].get('status')}")
full = requests.get(f"{BASE}/api/v1/executions/{exec_id}?includeData=true", headers=H, timeout=30).json()
runs = full.get("data", {}).get("resultData", {}).get("runData", {})
out = runs.get("INSERT to chat_histories", [{}])[0].get("data", {}).get("main", [[]])[0]
err = runs.get("INSERT to chat_histories", [{}])[0].get("error", {}).get("message", "")
print(f"\n[5] INSERT items: {len(out)} (esperados: 8) err={err[:120] if err else ''}")
for it in out:
    j = it.get("json", {})
    print(f"   id={j.get('id')} session_id={j.get('session_id')}")
