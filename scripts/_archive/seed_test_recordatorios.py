"""
Insertar 2 filas test en recordatorios_enviados simulando el caso Genefes
(multi-paciente mismo phone). Phone hardcodeado al de Lucas para poder testear.
Cita_ids = 7952 y 7953 (Genefes reales ya en id_estado=18, idempotente).
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

SB = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
H = {"apikey": SR, "Authorization": f"Bearer {SR}",
     "Content-Type": "application/json", "Prefer": "return=representation"}

PHONE_LUCAS = "5491161461034"
ROWS = [
    {
        "telefono": PHONE_LUCAS,
        "chat_remote_jid": f"{PHONE_LUCAS}@s.whatsapp.net",
        "id_cita_dentalink": 7952,
        "id_paciente_dentalink": 102,
        "nombre_paciente": "Guillermina Jenefes",
        "fecha_turno": "2026-05-27",
        "hora_turno": "15:50:00",
        "tipo": "24h",
        "workflow_execution_id": "TEST-SEED-001",
        "metadata": {"test_seed": True, "note": "Test multi-paciente desde Lucas, idempotente con 7952 ya confirmado"},
    },
    {
        "telefono": PHONE_LUCAS,
        "chat_remote_jid": f"{PHONE_LUCAS}@s.whatsapp.net",
        "id_cita_dentalink": 7953,
        "id_paciente_dentalink": 103,
        "nombre_paciente": "Manuel Jenefes",
        "fecha_turno": "2026-05-27",
        "hora_turno": "16:30:00",
        "tipo": "24h",
        "workflow_execution_id": "TEST-SEED-001",
        "metadata": {"test_seed": True, "note": "Test multi-paciente desde Lucas, idempotente con 7953 ya confirmado"},
    },
]

# Primero limpiar cualquier seed previa para Lucas (workflow_execution_id like TEST-SEED-%)
del_url = f"{SB}/rest/v1/recordatorios_enviados?telefono=eq.{PHONE_LUCAS}&workflow_execution_id=like.TEST-SEED-*"
try:
    req = urllib.request.Request(del_url, headers=H, method="DELETE")
    with urllib.request.urlopen(req, timeout=15) as r:
        print(f"Cleanup previous TEST-SEED rows for Lucas: {r.status}")
except urllib.error.HTTPError as e:
    print(f"Cleanup: HTTP {e.code} {e.read().decode()[:200]}")

# Insert
data = json.dumps(ROWS).encode()
req = urllib.request.Request(f"{SB}/rest/v1/recordatorios_enviados",
                              headers=H, method="POST", data=data)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        inserted = json.loads(r.read().decode())
        print(f"\nInserted {len(inserted)} rows:")
        for row in inserted:
            print(f"  id={row['id']}")
            print(f"    telefono={row['telefono']}")
            print(f"    id_cita={row['id_cita_dentalink']}  paciente={row['nombre_paciente']}")
            print(f"    fecha={row['fecha_turno']} hora={row['hora_turno']}  tipo={row['tipo']}")
            print(f"    enviado_at={row['enviado_at']}")
except urllib.error.HTTPError as e:
    print(f"!! HTTP {e.code}: {e.read().decode()[:500]}")

# Verify via GET (mismo query que va a hacer el bot)
print("\n=== Verify via SELECT (query del bot) ===")
verify_url = (f"{SB}/rest/v1/recordatorios_enviados?"
              f"telefono=eq.{PHONE_LUCAS}&confirmado_at=is.null&cancelado_at=is.null"
              f"&select=id_cita_dentalink,id_paciente_dentalink,nombre_paciente,fecha_turno,hora_turno,tipo,enviado_at"
              f"&order=fecha_turno,hora_turno")
req = urllib.request.Request(verify_url, headers=H)
with urllib.request.urlopen(req, timeout=15) as r:
    rows = json.loads(r.read().decode())
print(f"  open rows for {PHONE_LUCAS}: {len(rows)}")
for r in rows:
    print(f"  {json.dumps(r, ensure_ascii=False)}")
