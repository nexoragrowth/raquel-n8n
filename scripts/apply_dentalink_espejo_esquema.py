# -*- coding: utf-8 -*-
"""
apply_dentalink_espejo_esquema.py — 2026-10-20 · aplica sql/2026-10-20_dentalink_espejo.sql (esquema `agenda`, espejo de Dentalink) en el
Supabase v3. Plan: docs/plan-migracion-dentalink-2026-10-20.md §3. NO carga datos: eso es scripts/migrar_dentalink.py --apply.

QUÉ CREA (aditivo, idempotente, una transacción): esquema agenda con 27 tablas (RLS sin policies), 2 funciones, 1 trigger y 1 vista.
anon/authenticated: nada (ni USAGE del esquema). service_role: SELECT/INSERT/UPDATE, sin DELETE. No toca ninguna tabla existente.

USO (por defecto SOLO LEE):
  python scripts/apply_dentalink_espejo_esquema.py           # simulación: corre la prueba PGlite y mira en sesión READ-ONLY qué existe
  python scripts/apply_dentalink_espejo_esquema.py --apply   # corre el SQL y verifica (tablas, RLS, permisos, versión)
Antes: backup de la base (Supabase Pro, D1). La prueba local tiene que estar en verde (el --apply la exige).
Vuelta atrás (solo si todavía no hay datos que importen): drop schema agenda cascade; — no toca nada del bot.
"""
import argparse, subprocess, sys
from pathlib import Path

import psycopg2

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql" / "2026-10-20_dentalink_espejo.sql"
TEST = ROOT / "tests" / "test_migracion_dentalink_espejo.mjs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env  # noqa: E402


def conectar(solo_lectura):
    c = psycopg2.connect(host=env("SUPABASE_DB_HOST"), port=env("SUPABASE_DB_PORT"), dbname=env("SUPABASE_DB_NAME"),
                         user=env("SUPABASE_DB_USER"), password=env("SUPABASE_DB_PASSWORD"), sslmode="require", connect_timeout=15)
    if solo_lectura:
        c.set_session(readonly=True, autocommit=True)
    else:
        c.autocommit = True  # begin/commit los pone el propio SQL
    return c


def estado(cur):
    cur.execute("select to_regnamespace('agenda') is not null")
    if not cur.fetchone()[0]:
        return {"esquema": False}
    cur.execute("""select count(*) filter (where c.relkind = 'r'), count(*) filter (where c.relkind = 'r' and not c.relrowsecurity),
                          count(*) filter (where c.relkind = 'v')
                     from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'agenda'""")
    tablas, sin_rls, vistas = cur.fetchone()
    cur.execute("select count(*) from pg_policies where schemaname = 'agenda'")
    pol = cur.fetchone()[0]
    cur.execute("select has_schema_privilege('anon', 'agenda', 'usage'), has_schema_privilege('authenticated', 'agenda', 'usage'), "
                "has_schema_privilege('service_role', 'agenda', 'usage')")
    u_anon, u_auth, u_sr = cur.fetchone()
    cur.execute("select count(*) from information_schema.role_table_grants where table_schema = 'agenda' and grantee = 'service_role' and privilege_type in ('DELETE','TRUNCATE')")
    del_sr = cur.fetchone()[0]
    cur.execute("select coalesce(array_agg(version order by version), '{}') from agenda.esquema_version") if tablas else None
    versiones = cur.fetchone()[0] if tablas else []
    return {"esquema": True, "tablas": tablas, "tablas_sin_rls": sin_rls, "vistas": vistas, "policies": pol, "anon_usage": u_anon,
            "authenticated_usage": u_auth, "service_role_usage": u_sr, "service_role_delete": del_sr, "versiones": versiones}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    print(f"SQL: {SQL.relative_to(ROOT)} ({len(SQL.read_text(encoding='utf-8').splitlines())} líneas)")
    r = subprocess.run(["node", str(TEST)], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    ultima = (r.stdout.strip().splitlines() or ["(sin salida)"])[-1]
    print(f"Prueba PGlite: {ultima}")
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit("ERROR: la prueba local no está en verde: no se aplica")
    con = conectar(True)
    antes = estado(con.cursor())
    con.close()
    print("Hoy en el v3:", antes)
    if not a.apply:
        print("SIMULACIÓN: no se aplicó nada. Para aplicar: --apply")
        return
    con = conectar(False)
    cur = con.cursor()
    try:
        cur.execute(SQL.read_text(encoding="utf-8"))
    except Exception as e:
        try:
            cur.execute("rollback")
        except Exception:
            pass
        sys.exit(f"ERROR (rollback, no quedó nada): {str(e)[:400]}")
    despues = estado(cur)
    con.close()
    print("Después:", despues)
    ok = (despues.get("esquema") and despues["tablas"] >= 27 and despues["tablas_sin_rls"] == 0 and despues["policies"] == 0
          and not despues["anon_usage"] and not despues["authenticated_usage"] and despues["service_role_usage"]
          and despues["service_role_delete"] == 0 and "2026-10-20" in despues["versiones"])
    print("VERIFICACIÓN:", "OK" if ok else "FALLA (revisar arriba)")
    if ok:
        print("Siguiente: python scripts/migrar_dentalink.py --apply   (fase ocupacion, sin datos de pacientes; verifica sola al terminar)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
