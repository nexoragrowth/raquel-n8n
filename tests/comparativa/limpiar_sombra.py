import re, sys, psycopg2
from pathlib import Path
TEL = "5491161461034"
env = {}
for l in (Path(__file__).resolve().parent.parent.parent / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
    m = re.match(r"\s*(SUPABASE_DB_[A-Z]+)\s*=\s*(.*)", l)
    if m: env[m.group(1)] = m.group(2).strip().strip("'\"")
c = psycopg2.connect(host=env["SUPABASE_DB_HOST"], port=env["SUPABASE_DB_PORT"], dbname=env["SUPABASE_DB_NAME"], user=env["SUPABASE_DB_USER"], password=env["SUPABASE_DB_PASSWORD"], sslmode="require")
cur = c.cursor()
cur.execute("DELETE FROM public.n8n_chat_histories WHERE session_id LIKE 'sombra:%'")   # también las claves con hash que arma el v6 orquestador
n = cur.rowcount
# el Logger copia las sesiones de sombra a conversaciones y crea contactos en pacientes: también se borran
cur.execute("DELETE FROM public.conversaciones WHERE telefono LIKE 'sombra:%'")
n += cur.rowcount
cur.execute("DELETE FROM public.pacientes WHERE telefono LIKE 'sombra:%'")
n += cur.rowcount
c.commit()
print("borradas", n, "filas de memoria de sombra")
