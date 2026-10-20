# -*- coding: utf-8 -*-
"""
apply_panel_seguimientos_citas.py — 2026-10-20 · REC-05: crea public.panel_seguimientos_citas(p_desde date), la lectura de SOLO LECTURA del espejo
de la agenda (esquema agenda, no expuesto por PostgREST) que usa la pantalla Seguimientos del panel (lista "No vino"). Devuelve id de cita, fecha,
hora, categoría del estado y la hora de la última copia buena del espejo: ningún dato de la persona. Solo service_role la ejecuta.

USO:  python scripts/apply_panel_seguimientos_citas.py            # simulación: prerrequisitos (solo lectura)
      python scripts/apply_panel_seguimientos_citas.py --apply    # crea la función, recarga PostgREST y verifica permisos y resultado
      python scripts/apply_panel_seguimientos_citas.py --down --apply
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_migracion_contacto_tipos import conectar

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql" / "2026-10-20_panel_seguimientos_citas.sql"
DOWN = ROOT / "sql" / "2026-10-20_panel_seguimientos_citas_DOWN.sql"
FN = "public.panel_seguimientos_citas(date)"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--down", action="store_true"); a = ap.parse_args()
    c = conectar(); cur = c.cursor()
    cur.execute("select to_regclass('agenda.citas') is not null, to_regclass('agenda.estados_cita') is not null, to_regclass('agenda.sync_corridas') is not null")
    pre = cur.fetchone(); cur.execute("select to_regprocedure(%s) is not null", (FN,)); existe = cur.fetchone()[0]; c.close()
    print(f"espejo listo (citas, estados_cita, sync_corridas): {pre} · la función ya existe: {existe}")
    if not all(pre): sys.exit("ABORTO: falta el esquema agenda (sql/2026-10-20_dentalink_espejo.sql).")
    archivo = DOWN if a.down else SQL
    if not a.apply: print(f"[SIMULACIÓN] {archivo.name}. Para aplicar: --apply"); return
    c = conectar(solo_lectura=False); c.autocommit = True
    c.cursor().execute(archivo.read_text(encoding="utf-8"))
    c.cursor().execute("notify pgrst, 'reload schema'")
    c.close()
    c = conectar(); cur = c.cursor()
    cur.execute("select to_regprocedure(%s) is not null", (FN,)); existe = cur.fetchone()[0]
    if a.down:
        print("OK: función borrada" if not existe else "ATENCIÓN: sigue existiendo"); return
    cur.execute("select has_function_privilege('anon', %s, 'execute'), has_function_privilege('authenticated', %s, 'execute'), has_function_privilege('service_role', %s, 'execute')", (FN, FN, FN))
    anon, auth, srv = cur.fetchone()
    cur.execute("select count(*), count(*) filter (where categoria = 'no_asistio') from public.panel_seguimientos_citas((now() at time zone 'America/Argentina/Jujuy')::date - 60)")
    filas, faltas = cur.fetchone()
    ok = existe and not anon and not auth and srv and filas > 0
    print(("OK" if ok else "ATENCIÓN") + f": existe={existe} · anon={anon} authenticated={auth} service_role={srv} · 60 días: {filas} filas, {faltas} 'No asiste'")


if __name__ == "__main__":
    main()
