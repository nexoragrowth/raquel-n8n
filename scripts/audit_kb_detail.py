# -*- coding: utf-8 -*-
"""
audit_kb_detail.py — Revisa en detalle las filas de knowledge_base en Supabase v3
para preparar el saneamiento.
"""
import sys, psycopg2
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env

def main():
    host = env("SUPABASE_V3_DB_HOST")
    port = env("SUPABASE_V3_DB_PORT")
    db = env("SUPABASE_V3_DB_NAME")
    user = env("SUPABASE_V3_DB_USER")
    pwd = env("SUPABASE_V3_DB_PASSWORD")

    conn = psycopg2.connect(host=host, port=port, dbname=db, user=user, password=pwd, sslmode="require")
    cur = conn.cursor()

    cur.execute("SELECT id, categoria, titulo, contenido FROM knowledge_base ORDER BY id;")
    rows = cur.fetchall()
    print(f"Total registros en knowledge_base: {len(rows)}\n")

    for r in rows:
        kb_id, cat, tit, cont = r
        lower = (tit + " " + cont).lower()
        flags = []
        if "asiri" in lower and kb_id != 19 and kb_id != 40:
            flags.append("ASIRI en medicina")
        if "dentalink" in lower:
            flags.append("dentalink interno")
        if any(c in lower for c in ["amarillo", "flúor", "fluor", "morado", "punto verde", "punto negro"]):
            flags.append("colores operativos de agenda")
        if "bot off" in lower or "/bot" in lower:
            flags.append("comando bot interno")
        if "1 año" in lower or "un anio" in lower or "un año" in lower:
            flags.append("reserva a 1 año")

        if flags:
            print(f"[{' | '.join(flags)}] ID {kb_id} | {tit}")
            print(f"   -> {cont}\n")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
