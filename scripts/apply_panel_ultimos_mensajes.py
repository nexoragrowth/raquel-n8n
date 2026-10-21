# -*- coding: utf-8 -*-
"""
apply_panel_ultimos_mensajes.py — 2026-10-21 · Fase 1A (fluidez del panel): crea public.panel_ultimos_mensajes(), que devuelve el último mensaje y los
no leídos de CADA chat desde la base (antes el panel traía 2000 filas completas y lo calculaba en memoria). Solo lectura, solo service_role.

USO:  python scripts/apply_panel_ultimos_mensajes.py            # simulación: muestra qué haría y mide la función en una transacción de solo lectura
      python scripts/apply_panel_ultimos_mensajes.py --apply    # crea la función, recarga PostgREST y verifica permisos y resultado
      python scripts/apply_panel_ultimos_mensajes.py --down --apply
"""
import argparse, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_migracion_contacto_tipos import conectar

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql" / "2026-10-21_panel_ultimos_mensajes.sql"
DOWN = ROOT / "sql" / "2026-10-21_panel_ultimos_mensajes_DOWN.sql"
FN = "public.panel_ultimos_mensajes(integer, integer, integer)"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--down", action="store_true"); a = ap.parse_args()
    c = conectar(); cur = c.cursor()
    cur.execute("select to_regprocedure(%s) is not null", (FN,)); existe = cur.fetchone()[0]; c.close()
    print(f"la función ya existe: {existe}")
    archivo = DOWN if a.down else SQL
    if not a.apply:
        print(f"[SIMULACIÓN] {archivo.name}. Para aplicar: --apply"); return
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
    t0 = time.perf_counter()
    cur.execute("select count(*), count(*) filter (where es_ultimo), coalesce(sum(no_leidos), 0) from public.panel_ultimos_mensajes()")
    filas, chats, nl = cur.fetchone()
    ms = round((time.perf_counter() - t0) * 1000)
    ok = existe and not anon and not auth and srv and chats > 0
    print(("OK" if ok else "ATENCIÓN") + f": existe={existe} · anon={anon} authenticated={auth} service_role={srv} · {chats} chats, {filas - chats} mensajes recientes, {nl} no leídos · {ms} ms")


if __name__ == "__main__":
    main()
