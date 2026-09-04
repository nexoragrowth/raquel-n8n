# -*- coding: utf-8 -*-
"""
test_e2e_triaje.py — E2E REAL del triaje de urgencias con video contra el webhook público del v6.

Manda un mensaje con el shape de Evolution GO (whatsmeow) que exige `Webhook Validator`, con
`data.source = 'test_e2e_suite'` (bypass del rate limit). El bot procesa como un mensaje real:
si el triaje decide video, el VIDEO LLEGA AL WHATSAPP del teléfono indicado (usar un número de
prueba/admin, nunca un paciente). Espera ~40 s (buffer 22 s + LLM + envío) y muestra lo que
quedó en triaje_urgencias_log y n8n_chat_histories para ese teléfono.

Uso:
  python tests/test_e2e_triaje.py --phone 5491161461034 --texto "se me salió el alambre y me pincha"
  python tests/test_e2e_triaje.py --phone 5491161461034 --texto "no me sirvió, sigue pinchando" --esperar 45
"""
import argparse, json, sys, time, uuid, urllib.request, psycopg2
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--phone", required=True)
ap.add_argument("--texto", required=True)
ap.add_argument("--esperar", type=int, default=40)
ap.add_argument("--webhook", default="https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2")
args = ap.parse_args()

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
cur = conn.cursor()
cur.execute("SELECT COALESCE(max(id),0) FROM triaje_urgencias_log"); log0 = cur.fetchone()[0]
cur.execute("SELECT COALESCE(max(id),0) FROM n8n_chat_histories WHERE session_id=%s", (args.phone,)); mem0 = cur.fetchone()[0]

msg_id = "E2E" + uuid.uuid4().hex[:16].upper()
payload = {"instanceName": "raquel", "event": "message",
           "data": {"source": "test_e2e_suite",
                    "Info": {"ID": msg_id, "Chat": f"{args.phone}@s.whatsapp.net", "Sender": f"{args.phone}@s.whatsapp.net",
                             "PushName": "Test E2E", "IsFromMe": False, "Type": "text", "MediaType": ""},
                    "Message": {"conversation": args.texto}}}
req = urllib.request.Request(args.webhook, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=30) as r:
    print(f"webhook -> HTTP {r.status} | msg_id={msg_id} | texto=«{args.texto}»")
print(f"esperando {args.esperar}s (buffer 22s + clasificador + envío)...")
time.sleep(args.esperar)

cur.execute("""SELECT id, tipo, confianza, accion, razon, gate_red_flags, video_enviado, modo, created_at FROM triaje_urgencias_log
               WHERE id > %s AND telefono=%s ORDER BY id""", (log0, args.phone))
rows = cur.fetchall()
print(f"\ntriaje_urgencias_log nuevas: {len(rows)}")
for r in rows: print("  ", r)
cur.execute("""SELECT id, message->>'type', left(message->>'content', 110), message->'additional_kwargs'->>'source' FROM n8n_chat_histories
               WHERE session_id=%s AND id > %s ORDER BY id""", (args.phone, mem0))
rows = cur.fetchall()
print(f"n8n_chat_histories nuevas: {len(rows)}")
for r in rows: print("  ", r)
cur.execute("""SELECT id, left(motivo, 120), origen, created_at FROM escalaciones_log WHERE telefono=%s AND created_at > NOW() - INTERVAL '3 minutes' ORDER BY id""", (args.phone,))
rows = cur.fetchall()
print(f"escalaciones_log (últimos 3 min): {len(rows)}")
for r in rows: print("  ", r)
cur.close(); conn.close()
