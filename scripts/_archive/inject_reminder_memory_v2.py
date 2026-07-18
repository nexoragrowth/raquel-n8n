"""
Inyecta 4 mensajes en n8n_chat_histories simulando lo que el cron real escribe:
- Por cada turno (Lucas+Jana): 1 mensaje recordatorio + 1 nota interna
Total: 4 filas.

Formato exacto LangChain v0.3 (flat, sin wrapper 'data') con
source='reminder_note' para que pase el filter de Clear Old Memory.
"""
import io
import json
import sys
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
TURNOS = [
    {"cita_id": 8095, "id_paciente": 608, "nombre": "Lucas Silva",
     "fecha": "2026-06-04", "hora": "11:20",
     "fecha_natural": "jueves 4 de junio de 2026", "tipo": "24h",
     "tratamiento": "Estimado"},
    {"cita_id": 8096, "id_paciente": 621, "nombre": "Jana Test",
     "fecha": "2026-06-04", "hora": "11:30",
     "fecha_natural": "jueves 4 de junio de 2026", "tipo": "24h",
     "tratamiento": "Estimada"},
]

# Cleanup previos test injects (cualquier fila con [TEST_SIM_REMINDER] o cita_id en 8095/8096)
print("[cleanup] borrando inyecciones previas para Lucas ...")
url = f"{SB}/rest/v1/n8n_chat_histories?session_id=eq.{PHONE}&message->>content=like.*TEST_SIM*"
try:
    req = urllib.request.Request(url, headers=H, method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as r:
        print(f"  status: {r.status}")
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code}: {e.read().decode()[:200]}")

# Tambien borrar id 6162 y 6163 si existen
url = f"{SB}/rest/v1/n8n_chat_histories?id=in.(6162,6163)"
try:
    req = urllib.request.Request(url, headers=H, method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as r:
        print(f"  status (6162/6163): {r.status}")
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code}")

rows_to_insert = []
for t in TURNOS:
    # Mensaje recordatorio (lo que se "mando" al paciente)
    recordatorio = (
        "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\n"
        f"{t['tratamiento']} {t['nombre']},\n"
        "Le recordamos su turno con la Dra. Rodríguez Raquel:\n\n"
        f"📅 {t['fecha_natural'].capitalize()}\n"
        f"🕔 {t['hora']} hs\n"
        "📍 Balcarce Nº37, 2º piso\n\n"
        "[TEST_SIM - inyectado para test]\n\n"
        "Le pedimos confirmar su asistencia respondiendo a este mensaje."
    )
    rows_to_insert.append({
        "session_id": PHONE,
        "message": {
            "type": "ai",
            "content": recordatorio,
            "tool_calls": [],
            "additional_kwargs": {"source": "reminder_note"},
            "response_metadata": {},
            "invalid_tool_calls": [],
        }
    })
    # Nota interna con datos del turno (formato exacto del cron real)
    nota = (
        "[NOTA INTERNA - contexto del último recordatorio enviado, NO mencionar al paciente]\n"
        f"Acabo de enviar un recordatorio {t['tipo']} del siguiente turno:\n"
        f"- Cita Dentalink ID: {t['cita_id']}\n"
        f"- ID Paciente: {t['id_paciente']}\n"
        f"- Paciente: {t['nombre']}\n"
        f"- Fecha: {t['fecha_natural']}\n"
        f"- Hora: {t['hora']}\n"
        f"- Profesional: Dra. Rodríguez Raquel\n"
        "Si el paciente responde sobre este turno, ya conocés todos los datos. "
        "NO le pidas que repita fecha/hora/profesional."
    )
    rows_to_insert.append({
        "session_id": PHONE,
        "message": {
            "type": "ai",
            "content": nota,
            "tool_calls": [],
            "additional_kwargs": {"source": "reminder_note"},
            "response_metadata": {},
            "invalid_tool_calls": [],
        }
    })

# Bulk insert
data = json.dumps(rows_to_insert).encode()
req = urllib.request.Request(f"{SB}/rest/v1/n8n_chat_histories",
                              headers=H, method="POST", data=data)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        inserted = json.loads(r.read().decode())
        print(f"\nInserted {len(inserted)} rows:")
        for r in inserted:
            content = r["message"]["content"][:80].replace("\n", " | ")
            print(f"  id={r['id']} type={r['message']['type']} content[:80]: {content}")
except urllib.error.HTTPError as e:
    print(f"!! HTTP {e.code}: {e.read().decode()[:500]}")
