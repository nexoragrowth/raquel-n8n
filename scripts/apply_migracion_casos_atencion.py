# -*- coding: utf-8 -*-
"""
apply_migracion_casos_atencion.py — 2026-10-20 · ATE-02: aplica sql/2026-10-20_casos_atencion.sql (tabla `casos` de la bandeja de Atención +
triggers FAIL-SAFE sobre escalaciones_log y triaje_urgencias_log) contra el Supabase v3. Mismo patrón que apply_migracion_contacto_tipos.py.

Por defecto SOLO LEE: prerrequisitos (migración del 14/10, columnas de los logs que leen los triggers, otros triggers de esas tablas) + el test
offline con PGlite. Con --apply corre el SQL (una transacción, se autoverifica y aborta si algo no cuadra) y después prueba el trigger DE VERDAD
dentro de una transacción que se DESHACE: inserta un aviso falso del número de prueba en escalaciones_log, mira que nazca el caso y hace
ROLLBACK (sin residuos, sin aviso al grupo: el aviso al grupo lo manda n8n, no la base).

USO:  python scripts/apply_migracion_casos_atencion.py              # simulación (solo lectura)
      python scripts/apply_migracion_casos_atencion.py --apply
      python scripts/apply_migracion_casos_atencion.py --verificar  # solo la prueba del trigger con ROLLBACK
      python scripts/apply_migracion_casos_atencion.py --down --apply   # vuelta atrás (sql/…_DOWN.sql)
Apagado rápido sin borrar: alter table public.escalaciones_log disable trigger casos_desde_escalacion_trg; (ídem triaje_urgencias_log).
"""
import argparse, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_migracion_contacto_tipos import conectar

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql" / "2026-10-20_casos_atencion.sql"
DOWN = ROOT / "sql" / "2026-10-20_casos_atencion_DOWN.sql"
TEST = ROOT / "tests" / "test_migracion_casos_atencion.mjs"
TEL_PRUEBA = "5491161461034"
COLUMNAS = {"escalaciones_log": {"id", "telefono", "origen", "motivo", "exec_id", "created_at"},
            "triaje_urgencias_log": {"id", "telefono", "accion", "modo", "tipo", "mensaje_paciente", "exec_id", "created_at", "confianza", "gate_escala"}}


def prerrequisitos(cur):
    ok = True
    cur.execute("select to_regprocedure('public.contacto_tel_normalizar(text)') is not null")
    t = cur.fetchone()[0]; ok &= t; print(("  ok   " if t else "  MAL  ") + "migración del 14/10 (contacto_tel_normalizar)")
    for tabla, cols in COLUMNAS.items():
        cur.execute("select column_name from information_schema.columns where table_schema='public' and table_name=%s", (tabla,))
        hay = {r[0] for r in cur.fetchall()}
        falta = cols - hay
        ok &= not falta
        print(("  ok   " if not falta else "  MAL  ") + f"{tabla}: columnas que leen los triggers" + (f" — faltan {sorted(falta)}" if falta else ""))
        cur.execute("select tgname from pg_trigger where tgrelid = %s::regclass and not tgisinternal", (f"public.{tabla}",))
        print(f"       triggers que ya tiene {tabla}: {[r[0] for r in cur.fetchall()] or 'ninguno'}")
    cur.execute("select to_regclass('public.casos') is not null")
    print(f"       public.casos ya existe: {cur.fetchone()[0]}")
    return ok


def test_offline():
    p = subprocess.run(["node", str(TEST)], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    ultima = (p.stdout.strip().splitlines() or ["(sin salida)"])[-1]
    print(f"  test PGlite: {ultima}")
    return p.returncode == 0


def probar_trigger():
    """Aviso falso del número de prueba → caso creado → ROLLBACK. Devuelve True si el caso nació y nada quedó."""
    c = conectar(solo_lectura=False)
    try:
        cur = c.cursor()
        cur.execute("insert into public.escalaciones_log (telefono, motivo, origen) values (%s, %s, %s) returning id",
                    (TEL_PRUEBA, "[FYI] prueba del trigger de la bandeja (se deshace)", "prueba_trigger"))
        lid = cur.fetchone()[0]
        cur.execute("select c.id, c.tipo, c.estado from public.casos c join public.casos_eventos e on e.caso_id = c.id "
                    "where e.ref_tabla = 'escalaciones_log' and e.ref_id = %s", (lid,))
        caso = cur.fetchone()
        print(f"  insert en escalaciones_log id={lid} → caso {caso if caso else 'NO NACIÓ'}")
    finally:
        c.rollback(); c.close()
    c = conectar()
    cur = c.cursor()
    cur.execute("select count(*) from public.escalaciones_log where origen = 'prueba_trigger'")
    resto = cur.fetchone()[0]
    c.close()
    print(f"  después del ROLLBACK: filas de prueba que quedaron = {resto}")
    return bool(caso) and resto == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--down", action="store_true"); ap.add_argument("--verificar", action="store_true")
    a = ap.parse_args()
    if a.verificar:
        sys.exit(0 if probar_trigger() else 1)
    if a.down:
        print(f"Vuelta atrás: {DOWN.name}")
        if not a.apply:
            print("[SIMULACIÓN] Para correrla: --down --apply"); return
        c = conectar(solo_lectura=False); c.autocommit = True
        c.cursor().execute(DOWN.read_text(encoding="utf-8")); c.close()
        print("OK: vuelta atrás aplicada."); return
    print("PRERREQUISITOS (solo lectura)")
    c = conectar(); ok = prerrequisitos(c.cursor()); c.close()
    print("TEST OFFLINE")
    ok &= test_offline()
    if not ok:
        sys.exit("ABORTO: prerrequisitos o test en rojo. No se tocó nada.")
    if not a.apply:
        print("\n[SIMULACIÓN] Todo verde. Para aplicar: --apply"); return
    print("\nAPLICANDO (una transacción; el SQL se autoverifica)")
    c = conectar(solo_lectura=False); c.autocommit = True   # el archivo trae su propio begin/commit
    cur = c.cursor(); cur.execute(SQL.read_text(encoding="utf-8"))
    for n in c.notices[-10:]:
        print("  aviso de postgres:", n.strip()[:200])
    c.close()
    c = conectar(); cur = c.cursor()
    cur.execute("select count(*), count(*) filter (where estado <> 'resuelto') from public.casos")
    tot, abiertos = cur.fetchone()
    cur.execute("select tipo, count(*) from public.casos where estado <> 'resuelto' group by tipo order by 2 desc")
    print(f"  casos cargados de las últimas 72 h: {tot} ({abiertos} abiertos) por tipo: {cur.fetchall()}")
    c.close()
    print("PRUEBA DEL TRIGGER (con ROLLBACK)")
    print("OK" if probar_trigger() else "ATENCIÓN: el trigger no creó el caso (el insert del bot igual entra: revisar el WARNING en los logs de Postgres)")


if __name__ == "__main__":
    main()
