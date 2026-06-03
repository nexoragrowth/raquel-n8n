"""
Crea credencial httpHeaderAuth 'Supabase API Key' en n8n via API,
con header `apikey: <SR>`. Supabase REST acepta solo apikey (sin Authorization).
"""
import json, sys
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
SR = require("SUPABASE_SERVICE_ROLE_KEY")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

# Listar creds existentes
print("Creds existentes:")
try:
    r = requests.get(f"{N8N}/api/v1/credentials", headers=H, timeout=30)
    creds = r.json()
    if isinstance(creds, dict) and "data" in creds: creds = creds["data"]
    for c in creds[:30]:
        print(f"  id={c.get('id')} name={c.get('name')!r} type={c.get('type')}")
except Exception as e:
    print(f"  GET err: {e}")

# Crear cred Supabase
body = {
    "name": "Supabase API Key (apikey header)",
    "type": "httpHeaderAuth",
    "data": {"name": "apikey", "value": SR},
}
print(f"\nCreando cred httpHeaderAuth ...")
r = requests.post(f"{N8N}/api/v1/credentials", headers=H,
                  data=json.dumps(body).encode(), timeout=30)
print(f"  status: {r.status_code}")
print(f"  body: {r.text[:500]}")
