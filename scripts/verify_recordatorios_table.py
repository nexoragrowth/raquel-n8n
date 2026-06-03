"""
Verifica que recordatorios_enviados existe con el schema esperado.
Hace un SELECT a la tabla via PostgREST + describe via OPTIONS.
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

SB_URL = require("SUPABASE_URL").rstrip("/")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
H = {"apikey": SR, "Authorization": f"Bearer {SR}", "Accept": "application/json"}

# 1) SELECT vacio para validar que existe y columnas matchean
url = f"{SB_URL}/rest/v1/recordatorios_enviados?select=*&limit=0"
req = urllib.request.Request(url, headers=H)
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode()
        print(f"SELECT status: {r.status}")
        print(f"body: {body[:200]}")
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()[:300]}")

# 2) PostgREST devuelve el schema OpenAPI via /rest/v1/
url2 = f"{SB_URL}/rest/v1/"
req2 = urllib.request.Request(url2, headers=H)
with urllib.request.urlopen(req2, timeout=15) as r:
    spec = json.loads(r.read().decode())

if "definitions" in spec:
    table = spec["definitions"].get("recordatorios_enviados")
    if table:
        props = table.get("properties", {})
        required = set(table.get("required", []))
        print(f"\nSchema recordatorios_enviados — {len(props)} columnas:")
        for col, meta in props.items():
            req_marker = " (NOT NULL)" if col in required else ""
            print(f"  {col}: {meta.get('type', '?')} {meta.get('format', '')}{req_marker}")
    else:
        print("\n!! No se encontro recordatorios_enviados en el spec OpenAPI")

# 3) Sanity write — INSERT + DELETE de prueba
print("\n=== INSERT de prueba (despues DELETE) ===")
test_row = {
    "telefono": "5491100000000",
    "chat_remote_jid": "5491100000000@s.whatsapp.net",
    "id_cita_dentalink": -1,
    "id_paciente_dentalink": -1,
    "nombre_paciente": "SANITY TEST",
    "fecha_turno": "2099-01-01",
    "hora_turno": "00:00:00",
    "tipo": "24h",
}
data = json.dumps(test_row).encode()
ins_req = urllib.request.Request(
    f"{SB_URL}/rest/v1/recordatorios_enviados",
    headers={**H, "Content-Type": "application/json", "Prefer": "return=representation"},
    method="POST", data=data,
)
try:
    with urllib.request.urlopen(ins_req, timeout=15) as r:
        inserted = json.loads(r.read().decode())
        new_id = inserted[0]["id"]
        print(f"  INSERT ok, id={new_id}")
        # cleanup
        del_req = urllib.request.Request(
            f"{SB_URL}/rest/v1/recordatorios_enviados?id=eq.{new_id}",
            headers=H, method="DELETE",
        )
        with urllib.request.urlopen(del_req, timeout=15) as r2:
            print(f"  DELETE status: {r2.status}")
except urllib.error.HTTPError as e:
    print(f"  HTTP {e.code}: {e.read().decode()[:400]}")
