# -*- coding: utf-8 -*-
"""
apply_paciente_fotos.py — 2026-10-21 · Fase 2 (fotos de perfil del panel): crea public.paciente_fotos (URL de la foto de WhatsApp + vencimiento), fuera de Realtime.

USO:  python scripts/apply_paciente_fotos.py            # simulación
      python scripts/apply_paciente_fotos.py --apply    # crea la tabla y verifica permisos
      python scripts/apply_paciente_fotos.py --down --apply
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_migracion_contacto_tipos import conectar

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql" / "2026-10-21_paciente_fotos.sql"
DOWN = ROOT / "sql" / "2026-10-21_paciente_fotos_DOWN.sql"
TABLA = "public.paciente_fotos"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--down", action="store_true"); a = ap.parse_args()
    c = conectar(); cur = c.cursor()
    cur.execute("select to_regclass(%s) is not null", (TABLA,)); existe = cur.fetchone()[0]; c.close()
    print(f"la tabla ya existe: {existe}")
    archivo = DOWN if a.down else SQL
    if not a.apply:
        print(f"[SIMULACIÓN] {archivo.name}. Para aplicar: --apply"); return
    c = conectar(solo_lectura=False); c.autocommit = True
    c.cursor().execute(archivo.read_text(encoding="utf-8"))
    c.cursor().execute("notify pgrst, 'reload schema'")
    c.close()
    c = conectar(); cur = c.cursor()
    cur.execute("select to_regclass(%s) is not null", (TABLA,)); existe = cur.fetchone()[0]
    if a.down:
        print("OK: tabla borrada" if not existe else "ATENCIÓN: sigue existiendo"); return
    cur.execute("select has_table_privilege('anon', %s, 'select'), has_table_privilege('authenticated', %s, 'select'), has_table_privilege('service_role', %s, 'select')", (TABLA, TABLA, TABLA))
    anon, auth, srv = cur.fetchone()
    cur.execute("select exists(select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'paciente_fotos')"); en_realtime = cur.fetchone()[0]
    ok = existe and not anon and not auth and srv and not en_realtime
    print(("OK" if ok else "ATENCIÓN") + f": existe={existe} · anon={anon} authenticated={auth} service_role={srv} · en Realtime={en_realtime} (debe ser False)")


if __name__ == "__main__":
    main()
