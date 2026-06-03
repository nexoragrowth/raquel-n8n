"""
Inyecta un mensaje de recordatorio en la memoria del bot (n8n_chat_histories)
para el phone Lucas, simulando que el cron mando un recordatorio recien.
Asi cuando se simule 'Confirmados', el Router tiene contexto y clasifica
como confirmar_post_recordatorio.

n8n_chat_histories esquema:
- id (int, autoincrement)
- session_id (text) — phone como string
- message (jsonb) — formato langchain: {type: 'ai|human|system', data: {content, additional_kwargs, ...}}
"""
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

SB = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
H = {"apikey": SR, "Authorization": f"Bearer {SR}",
     "Content-Type": "application/json", "Prefer": "return=representation"}

PHONE = "5491161461034"

# Primero borrar TEST_SIM previo de la memoria de Lucas para no acumular
print("[cleanup] borrando previos TEST_SIM_REMINDER de la memoria de Lucas ...")
url = f"{SB}/rest/v1/n8n_chat_histories?session_id=eq.{PHONE}&message->data->>content=like.*TEST_SIM_REMINDER*"
req = urllib.request.Request(url, headers=H, method="DELETE")
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        print(f"  status: {r.status}")
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code}: {e.read().decode()[:200]}")

# Mensaje recordatorio formato Aurea
# (similar al output del cron Preparar mensaje con tipo 72h o 24h)
reminder_text = (
    "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\n"
    "Estimado Lucas,\n"
    "Le recordamos su turno con la Dra. Rodríguez Raquel:\n\n"
    "📅 Jueves 4 de junio de 2026\n"
    "🕔 11:20 hs\n"
    "📍 Balcarce Nº37, 2º piso\n\n"
    "[TEST_SIM_REMINDER - inyectado para test]\n\n"
    "Le pedimos confirmar su asistencia respondiendo a este mensaje para conservar su turno."
)

# Mensaje en formato LangChain memory
# El v6 preserva mensajes con metadata.source IN (wa_outbound, human_takeover, reminder_note)
# Vamos a usar source=bot_reminder para que matchee el patron real del cron
msg = {
    "type": "ai",
    "data": {
        "content": reminder_text,
        "additional_kwargs": {
            "source": "bot_reminder",
            "tipo_recordatorio": "24h",
            "cita_id": 8095,  # cita_id real del turno test Lucas
            "fecha": "2026-06-04",
            "hora": "11:20",
            "id_paciente": 608,
        },
        "response_metadata": {},
        "name": None,
        "id": None,
        "example": False,
    },
}

# Insert
row = {"session_id": PHONE, "message": msg}
data = json.dumps(row).encode()
req = urllib.request.Request(f"{SB}/rest/v1/n8n_chat_histories",
                              headers=H, method="POST", data=data)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        inserted = json.loads(r.read().decode())
        print(f"\nINSERT ok:")
        for r in inserted:
            print(f"  id={r['id']} session_id={r['session_id']}")
            print(f"  content (200): {r['message']['data']['content'][:200]}")
            print(f"  metadata: {json.dumps(r['message']['data'].get('additional_kwargs', {}), ensure_ascii=False)}")
except urllib.error.HTTPError as e:
    print(f"!! HTTP {e.code}: {e.read().decode()[:500]}")

# Tambien insertar uno tipo Lucas-test-Jana para que el bot tenga AMBOS recordatorios
msg2 = {
    "type": "ai",
    "data": {
        "content": (
            "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\n"
            "Estimada Jana,\n"
            "Le recordamos su turno con la Dra. Rodríguez Raquel:\n\n"
            "📅 Jueves 4 de junio de 2026\n"
            "🕔 11:30 hs\n"
            "📍 Balcarce Nº37, 2º piso\n\n"
            "[TEST_SIM_REMINDER - inyectado para test]\n\n"
            "Le pedimos confirmar su asistencia respondiendo a este mensaje para conservar su turno."
        ),
        "additional_kwargs": {
            "source": "bot_reminder",
            "tipo_recordatorio": "24h",
            "cita_id": 8096,
            "fecha": "2026-06-04",
            "hora": "11:30",
            "id_paciente": 621,
        },
        "response_metadata": {},
        "name": None,
        "id": None,
        "example": False,
    },
}
row2 = {"session_id": PHONE, "message": msg2}
req2 = urllib.request.Request(f"{SB}/rest/v1/n8n_chat_histories",
                               headers=H, method="POST",
                               data=json.dumps(row2).encode())
try:
    with urllib.request.urlopen(req2, timeout=15) as r:
        inserted = json.loads(r.read().decode())
        for r in inserted:
            print(f"\nINSERT 2 ok: id={r['id']} cita_id=8096 paciente Jana")
except urllib.error.HTTPError as e:
    print(f"!! HTTP {e.code}: {e.read().decode()[:500]}")
