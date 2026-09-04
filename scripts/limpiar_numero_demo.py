# -*- coding: utf-8 -*-
"""
limpiar_numero_demo.py — deja un teléfono limpio para probar/demostrar el triaje desde un WhatsApp real.

Qué frena al bot para un teléfono (relevado 4/9): (1) label `humano` en CUALQUIER conversación de
Chatwoot del contacto (única traba determinística); (2) memoria en n8n_chat_histories (filas
[ATENCION HUMANA]/[TEST 72h] contaminan el contexto y piden silencio al LLM); (3) estado
`triaje:{phone}` en Redis (no accesible desde acá: expira por TTL ≤2 h, o se pisa al escalar/cerrar).

Solo con --apply borra. Sin --apply muestra qué haría. El token de Chatwoot se copia EN CALIENTE
del nodo vivo "Re-check Humano" del v6 (nunca en este archivo).

Uso: python scripts/limpiar_numero_demo.py --phone 5491161461034 [--apply] [--solo-label] [--borrar-logs]
"""
import argparse, json, os, sys, urllib.request, psycopg2
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--phone", required=True)
ap.add_argument("--apply", action="store_true")
ap.add_argument("--solo-label", action="store_true", help="solo quitar el label humano en Chatwoot")
ap.add_argument("--borrar-logs", action="store_true", help="además borrar sus filas de escalaciones_log/triaje_urgencias_log/conversaciones de prueba (últimos 7 días)")
args = ap.parse_args()
PHONE = args.phone.strip()

def n8n(path):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", headers={"X-N8N-API-KEY": require("N8N_API_KEY")})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())

wf = n8n(f"/workflows/{env('N8N_WORKFLOW_V6_ID', 'O155MqHgOSaNZ9ye')}")
cw_token = next(h["value"] for n in wf["nodes"] if n["name"] == "Re-check Humano"
                for h in n["parameters"]["headerParameters"]["parameters"] if h["name"] == "api_access_token")

def cw(path, method="GET", body=None):
    req = urllib.request.Request("https://chat.raquelrodriguez.com.ar/api/v1/accounts/1" + path,
                                 data=json.dumps(body).encode() if body else None, method=method,
                                 headers={"api_access_token": cw_token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r: return json.loads(r.read().decode())

# 1) Chatwoot
search = cw(f"/contacts/search?q={PHONE}")
contacts = [c for c in search.get("payload", []) if PHONE in str(c.get("phone_number", "")).replace("+", "")]
print(f"Chatwoot: {len(contacts)} contacto(s) para {PHONE}")
for c in contacts:
    convs = cw(f"/contacts/{c['id']}/conversations").get("payload", [])
    for conv in convs:
        labels = conv.get("labels", [])
        flag = "humano" in labels
        print(f"  conv {conv['id']} status={conv.get('status')} labels={labels}{'  <-- BLOQUEA' if flag else ''}")
        if flag and args.apply:
            r = cw(f"/conversations/{conv['id']}/labels", "POST", {"labels": [l for l in labels if l != "humano"] or ["bot"]})
            print(f"     -> label humano quitado, ahora {r.get('payload')}")
if args.solo_label:
    sys.exit(0)

# 2) memoria + logs
def load_env(path, keys):
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        if k in keys: out[k] = v.strip().strip('"').strip("'")
    return out
db = load_env(str(ROOT / ".env"), {"SUPABASE_DB_HOST","SUPABASE_DB_PORT","SUPABASE_DB_NAME","SUPABASE_DB_USER","SUPABASE_DB_PASSWORD"})
conn = psycopg2.connect(host=db["SUPABASE_DB_HOST"], port=db["SUPABASE_DB_PORT"], dbname=db["SUPABASE_DB_NAME"], user=db["SUPABASE_DB_USER"], password=db["SUPABASE_DB_PASSWORD"], sslmode="require")
conn.autocommit = True; cur = conn.cursor()
cur.execute("SELECT count(*) FROM n8n_chat_histories WHERE session_id=%s", (PHONE,))
n_mem = cur.fetchone()[0]
print(f"n8n_chat_histories: {n_mem} filas de la sesión {PHONE}")
if args.apply:
    cur.execute("DELETE FROM n8n_chat_histories WHERE session_id=%s", (PHONE,))
    print(f"  -> borradas {cur.rowcount} (memoria limpia; el Router arranca sin contexto)")
if args.borrar_logs:
    for tabla, col in (("escalaciones_log", "telefono"), ("triaje_urgencias_log", "telefono")):
        cur.execute(f"SELECT count(*) FROM {tabla} WHERE {col}=%s AND created_at > NOW() - INTERVAL '7 days'", (PHONE,))
        n = cur.fetchone()[0]; print(f"{tabla}: {n} filas de los últimos 7 días")
        if args.apply and n:
            cur.execute(f"DELETE FROM {tabla} WHERE {col}=%s AND created_at > NOW() - INTERVAL '7 days'", (PHONE,)); print(f"  -> borradas {cur.rowcount}")
    cur.execute("SELECT count(*) FROM conversaciones WHERE telefono=%s AND \"timestamp\" > NOW() - INTERVAL '7 days'", (PHONE,))
    n = cur.fetchone()[0]; print(f"conversaciones: {n} filas de los últimos 7 días")
    if args.apply and n:
        cur.execute("DELETE FROM conversaciones WHERE telefono=%s AND \"timestamp\" > NOW() - INTERVAL '7 days'", (PHONE,)); print(f"  -> borradas {cur.rowcount}")
cur.close(); conn.close()
print("Redis: el estado triaje:{phone} no se puede borrar desde acá (expira ≤2 h; se pisa al escalar/cerrar). ratelimit: 10 msgs/15 min.")
if not args.apply: print("\n[DRY-RUN] nada borrado. Para aplicar: --apply")
