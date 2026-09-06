"""
Habilita Supabase Realtime (postgres_changes) en las tablas que el panel escucha en vivo.

Contexto (2026-09-06): la publicación `supabase_realtime` del v3 existía pero SIN tablas, así que
Realtime no emitía nada. El panel (nexora-whatsapp-agent) se suscribe server-side con la service
key a estas 3 tablas y empuja los cambios al navegador por SSE (/api/live):
  - mensajes_entrantes_live (INSERT)  → mensaje del paciente / staff desde el celular
  - n8n_chat_histories     (INSERT)  → respuestas del bot, staff desde el panel, triaje
  - pacientes              (UPDATE)  → modo bot/humano, alias, leído/no-leído

Idempotente: agrega solo las que faltan. `--estado` muestra sin cambiar. `--quitar` las saca.
Usa SUPABASE_DB_* del .env (Postgres directo, psycopg2).
"""
import os
import sys

import psycopg2
from dotenv import load_dotenv

TABLAS = ["mensajes_entrantes_live", "n8n_chat_histories", "pacientes"]


def conectar():
    load_dotenv(".env")
    return psycopg2.connect(
        host=os.environ["SUPABASE_DB_HOST"],
        port=os.environ.get("SUPABASE_DB_PORT", "5432"),
        dbname=os.environ.get("SUPABASE_DB_NAME", "postgres"),
        user=os.environ["SUPABASE_DB_USER"],
        password=os.environ["SUPABASE_DB_PASSWORD"],
        sslmode="require",
    )


def publicadas(cur):
    cur.execute("select tablename from pg_publication_tables where pubname='supabase_realtime' and schemaname='public'")
    return {r[0] for r in cur.fetchall()}


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "--aplicar"
    conn = conectar()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("show wal_level")
    wal = cur.fetchone()[0]
    cur.execute("select count(*) from pg_replication_slots where active")
    slots = cur.fetchone()[0]
    actuales = publicadas(cur)
    print(f"wal_level={wal} slots_activos={slots} publicadas={sorted(actuales)}")
    if modo == "--estado":
        faltan = [t for t in TABLAS if t not in actuales]
        print("OK: todas publicadas" if not faltan else f"FALTAN: {faltan}")
        return 0 if not faltan else 1
    if modo == "--quitar":
        presentes = [t for t in TABLAS if t in actuales]
        if presentes:
            cur.execute("alter publication supabase_realtime drop table " + ", ".join(f"public.{t}" for t in presentes))
        print(f"quitadas: {presentes}")
        return 0
    faltan = [t for t in TABLAS if t not in actuales]
    if faltan:
        cur.execute("alter publication supabase_realtime add table " + ", ".join(f"public.{t}" for t in faltan))
        print(f"agregadas: {faltan}")
    else:
        print("nada que hacer")
    print(f"publicadas ahora={sorted(publicadas(cur))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
