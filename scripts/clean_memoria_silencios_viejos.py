# -*- coding: utf-8 -*-
"""
check_filas_silencio.py — Cuenta y corrige las filas viejas de n8n_chat_histories
que contienen la orden de silencio en la memoria.
"""
import argparse, psycopg2, sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    conn = psycopg2.connect(
        host=env("SUPABASE_V3_DB_HOST"),
        port=env("SUPABASE_V3_DB_PORT"),
        dbname=env("SUPABASE_V3_DB_NAME"),
        user=env("SUPABASE_V3_DB_USER"),
        password=env("SUPABASE_V3_DB_PASSWORD"),
        sslmode="require"
    )
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("""
        SELECT count(*) 
        FROM n8n_chat_histories 
        WHERE message->>'content' LIKE '%Mantente en silencio y NO respondas%';
    """)
    n = cur.fetchone()[0]
    print(f"Filas con orden de silencio en n8n_chat_histories: {n}")

    if args.apply and n > 0:
        cur.execute("""
            UPDATE n8n_chat_histories
            SET message = jsonb_set(
                message::jsonb, '{content}',
                to_jsonb(regexp_replace(
                    message->>'content',
                    ' NO es output tuyo, es un humano atendiendo este chat\\. Mantente en silencio y NO respondas en este chat hasta que un admin diga /bot on\\.',
                    ' Mensaje del staff, no es output tuyo.'
                ))
            )
            WHERE message->>'content' LIKE '%Mantente en silencio y NO respondas%';
        """)
        print(f"✅ Filas actualizadas: {cur.rowcount}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
