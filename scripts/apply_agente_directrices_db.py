# -*- coding: utf-8 -*-
"""
apply_agente_directrices_db.py — crea en Supabase v3 las tablas de las directrices editables desde el panel
(`agente_directrices` + `agente_directrices_log`) y siembra los valores iniciales. Idempotente: no pisa lo que ya
exista (ON CONFLICT DO NOTHING). Solo agrega tablas nuevas; no toca ninguna tabla existente.

Las tablas quedan con RLS activado y sin policies (igual que el resto de v3): solo las lee el service role del
panel y la conexion Postgres de n8n.

ORDEN: este script va PRIMERO. Despues scripts/apply_agente_directrices_n8n.py (aborta si las tablas no existen,
porque la consulta nueva del bot las lee y fallaria para todos los pacientes).

USO:
    python scripts/apply_agente_directrices_db.py            # simulacion: muestra el SQL y las filas (sin conectar)
    python scripts/apply_agente_directrices_db.py --apply    # ejecuta en una transaccion y verifica
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env
from directrices_def import DDL, DIRECTRICES

sys.stdout.reconfigure(encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    print("--- DDL (tablas nuevas) ---" + DDL)
    print("--- Filas iniciales (ON CONFLICT DO NOTHING) ---")
    for d in DIRECTRICES:
        v = d["valor"].replace("\n", " ⏎ ")
        print(f"  {d['clave']:<18} max {d['max_largo']:>4} | {d['titulo']} | valor: {v[:110]}{'…' if len(v) > 110 else ''}")

    if not args.apply:
        print("\n[SIMULACION] No se conecto a la base. Correr con --apply (con OK de Lucas).")
        return

    import psycopg2
    conn = psycopg2.connect(host=env("SUPABASE_V3_DB_HOST"), port=env("SUPABASE_V3_DB_PORT"),
                            dbname=env("SUPABASE_V3_DB_NAME"), user=env("SUPABASE_V3_DB_USER"),
                            password=env("SUPABASE_V3_DB_PASSWORD"), sslmode="require", connect_timeout=10)
    try:
        with conn:  # una transaccion: o queda todo o nada
            cur = conn.cursor()
            cur.execute(DDL)
            for d in DIRECTRICES:
                cur.execute(
                    "INSERT INTO public.agente_directrices (clave, titulo, ayuda, valor, max_largo, updated_by) "
                    "VALUES (%s, %s, %s, %s, %s, 'seed') ON CONFLICT (clave) DO NOTHING",
                    (d["clave"], d["titulo"], d["ayuda"], d["valor"], d["max_largo"]))
            cur.execute("SELECT clave, length(valor) FROM public.agente_directrices ORDER BY clave")
            filas = cur.fetchall()
            cur.execute("SELECT relrowsecurity FROM pg_class WHERE oid = 'public.agente_directrices'::regclass")
            rls = cur.fetchone()[0]
        print("\nOK. Filas:", filas, "| RLS activado:", rls)
        esperadas = {d["clave"] for d in DIRECTRICES}
        if not esperadas <= {f[0] for f in filas} or not rls:
            sys.exit("VERIFICACION FALLIDA: faltan filas o RLS.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
