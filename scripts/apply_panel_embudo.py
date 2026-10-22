# -*- coding: utf-8 -*-
"""
apply_panel_embudo.py — 2026-10-22 · Home comercial del panel: tabla embudo_mapa_motivos + funciones panel_embudo() y panel_leads_nuevos() (solo agregados, sin datos de pacientes).

USO:  python scripts/apply_panel_embudo.py            # simulación
      python scripts/apply_panel_embudo.py --apply    # crea y verifica
      python scripts/apply_panel_embudo.py --down --apply
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_migracion_contacto_tipos import conectar

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql" / "2026-10-22_panel_embudo.sql"
DOWN = ROOT / "sql" / "2026-10-22_panel_embudo_DOWN.sql"
TABLA = "public.embudo_mapa_motivos"


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
    cur.execute("select exists(select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'embudo_mapa_motivos')"); en_realtime = cur.fetchone()[0]
    ok = existe and not anon and not auth and srv and not en_realtime
    cur.execute("select etapa, periodo, total, atendidas, perdidas, reprogramadas, vigentes, sin_confirmar_7d from public.panel_embudo(90) where etapa = 'consulta' order by periodo")
    for f in cur.fetchall(): print("  embudo consulta:", f)
    cur.execute("select count(*) from public.panel_leads_nuevos(7, 60)"); print("  leads nuevos 7d:", cur.fetchone()[0])
    print(("OK" if ok else "ATENCIÓN") + f": existe={existe} · anon={anon} authenticated={auth} service_role={srv} · en Realtime={en_realtime} (debe ser False)")


if __name__ == "__main__":
    main()
