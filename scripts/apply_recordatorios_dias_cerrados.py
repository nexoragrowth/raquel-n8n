# -*- coding: utf-8 -*-
"""
apply_recordatorios_dias_cerrados.py — (2026-11-19) "Días sin atención": la clínica carga feriados, puentes y vacaciones en el panel y el bot los respeta.

Por qué: el cálculo de los avisos es "hoy + 2 días hábiles lunes a viernes" y no sabe de feriados. Con el lunes 23/11 feriado, los turnos del martes salían
el viernes y la clínica tuvo que pedírselo a Lucas. Ahora el día cerrado se carga una vez y el jueves avisa solo el martes.

Qué cambia (SOLO esto, en el workflow "Recordatorio de Turno 48HS" 7RqTApkvVavRmq3R; ningún otro nodo, conexión ni credencial):
  1) columna recordatorios_config.dias_cerrados (aditiva; scripts/recordatorios_dias_cerrados.sql), ANTES del workflow;
  2) nodo "Gate - Leer config": además de las suspensiones de siempre, un día cerrado NO corre, y entrega la lista como texto 'YYYY-MM-DD'
     (recordatorios/gate_dias_cerrados.sql);
  3) nodo "Fecha Mañana": cuenta los 2 días hábiles salteando también los días cerrados (recordatorios/fecha_manana.js). Con la lista vacía es
     IDÉNTICO al de antes (tests/test_recordatorios_dias_cerrados.js: todos los días de 2026-2027).
Si el Gate falla (p. ej. falta la columna) el workflow sigue como hoy (el nodo falla abierto y Fecha Mañana usa lista vacía).

Frenos: el nodo vivo tiene que ser IGUAL al congelado del 19/11 (si alguien lo cambió, aborta); el SQL nuevo se prueba SIEMPRE contra una tabla temporal en una
transacción que se revierte; backup PRE/POST en workflows/history; el PUT pasa por guarda_vivo.

USO:  python scripts/apply_recordatorios_dias_cerrados.py            # simulación: verifica, prueba el SQL (revertido) y muestra el diff
      python scripts/apply_recordatorios_dias_cerrados.py --apply    # migración + backup PRE + PUT + verificación + backup POST
Vuelta atrás: scripts/restaurar_workflow.py con el backup PRE (workflows/history/7RqTApkvVavRmq3R_PRE_dias_cerrados_<ts>.json). La columna puede quedar (es inocua).
Regla del proyecto: NUNCA --apply sin el "desplegá" explícito de Lucas. Hacerlo en una ventana sin envíos (después de las 08:00 y antes de la corrida siguiente).
"""
import argparse, difflib, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crear_v7_en_n8n as D
import psycopg2

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = D.ROOT
HIST = ROOT / "workflows" / "history"
WID = "7RqTApkvVavRmq3R"
ETIQUETA = "dias_cerrados"
LEER = lambda p: (ROOT / p).read_text(encoding="utf-8")
norm = lambda s: str(s).replace("\r\n", "\n").strip()
NUEVO_JS, NUEVO_SQL = norm(LEER("recordatorios/fecha_manana.js")), norm(LEER("recordatorios/gate_dias_cerrados.sql"))
VIVO_JS, VIVO_SQL = norm(LEER("recordatorios/fecha_manana.vivo_2026-11-19.js")), norm(LEER("recordatorios/gate_leer_config.vivo_2026-11-19.sql"))
MIGRACION = LEER("scripts/recordatorios_dias_cerrados.sql")


def conectar(escritura=False):
    env = {}
    for l in (ROOT / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\s*(SUPABASE_DB_[A-Z]+)\s*=\s*(.*)", l)
        if m:
            env[m.group(1)] = m.group(2).strip().strip("'\"")
    c = psycopg2.connect(host=env["SUPABASE_DB_HOST"], port=env["SUPABASE_DB_PORT"], dbname=env["SUPABASE_DB_NAME"], user=env["SUPABASE_DB_USER"],
                         password=env["SUPABASE_DB_PASSWORD"], sslmode="require")
    c.set_session(readonly=not escritura)
    return c


def probar_sql_en_tabla_temporal():
    """El Gate NUEVO contra una copia temporal de la tabla (con la columna), en una transacción que SE REVIERTE. No toca la tabla real."""
    sql = NUEVO_SQL.replace("public.recordatorios_config", "pg_temp.recordatorios_config")
    assert "pg_temp.recordatorios_config" in sql and "public.recordatorios_config" not in sql
    HOY = "(now() at time zone 'America/Argentina/Jujuy')::date"
    casos = [
        ("lista vacía y todo prendido → NO suspende, lista vacía", "activo=true", "'{}'", "'{}'", "null,null", (False, [])),
        ("hoy está cerrado → suspende (no corre)", "activo=true", "'{}'", f"array[{HOY}]", "null,null", (True, None)),
        ("un día futuro cerrado → NO suspende hoy y entrega la lista como texto", "activo=true", "'{}'", f"array[{HOY} + 4, {HOY} + 10]", "null,null", (False, "dos_dias_futuros")),
        ("hoy suspendido a mano → suspende (como antes)", "activo=true", f"array[{HOY}]", "'{}'", "null,null", (True, [])),
        ("apagado → suspende (como antes)", "activo=false", "'{}'", "'{}'", "null,null", (True, [])),
        ("rango de vacaciones que incluye hoy → suspende (como antes)", "activo=true", "'{}'", "'{}'", f"{HOY} - 1, {HOY} + 1", (True, [])),
        ("rango de vacaciones futuro → NO suspende", "activo=true", "'{}'", "'{}'", f"{HOY} + 5, {HOY} + 9", (False, [])),
    ]
    c = conectar(escritura=True)   # solo para crear una tabla TEMPORAL; se revierte todo
    cur = c.cursor()
    resultados = []
    try:
        cur.execute("create temp table recordatorios_config (id smallint primary key default 1, activo boolean not null default true, hora_envio smallint not null default 8, "
                    "dias_suspendidos date[] not null default '{}', dias_cerrados date[] not null default '{}', suspender_desde date, suspender_hasta date, "
                    "updated_at timestamptz default now(), updated_by text)")
        for nombre, activo, susp, cerr, rango, esperado in casos:
            cur.execute("delete from pg_temp.recordatorios_config")
            cur.execute(f"insert into pg_temp.recordatorios_config (id, {activo.split('=')[0]}, dias_suspendidos, dias_cerrados, suspender_desde, suspender_hasta) "
                        f"values (1, {activo.split('=')[1]}, {susp}::date[], {cerr}::date[], {rango})")
            cur.execute(sql)
            fila = cur.fetchone()
            suspender, lista = bool(fila[0]), list(fila[1])
            ok = suspender == esperado[0]
            if esperado[1] == "dos_dias_futuros":
                ok = ok and len(lista) == 2 and all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", x) for x in lista) and lista == sorted(lista)
            elif esperado[1] is not None:
                ok = ok and lista == esperado[1] or (esperado[1] == [] and lista == [])
            else:
                ok = ok and len(lista) == 1
            resultados.append((nombre, ok, fila))
        # tabla SIN fila → el Gate no falla ni suspende (fail-open, como antes)
        cur.execute("delete from pg_temp.recordatorios_config"); cur.execute(sql); fila = cur.fetchone()
        resultados.append(("tabla sin la fila 1 → no suspende y lista vacía", bool(fila[0]) is False and list(fila[1]) == [], fila))
    finally:
        c.rollback(); c.close()
    return resultados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    vivo = D.api(f"/workflows/{WID}")
    nodos = {n["name"]: n for n in vivo["nodes"]}
    gate, fecha = nodos["Gate - Leer config"], nodos["Fecha Mañana"]
    print(f"== {vivo['name']} ({WID}) activo={vivo.get('active')} · zona={(vivo.get('settings') or {}).get('timezone')}")
    # 1) el vivo tiene que ser el que conocemos
    if norm(gate["parameters"]["query"]) == NUEVO_SQL and norm(fecha["parameters"]["jsCode"]) == NUEVO_JS:
        print("YA ESTÁ APLICADO: los dos nodos son los nuevos. No hay nada que hacer."); return
    for nombre, actual, congelado in (("Gate - Leer config", norm(gate["parameters"]["query"]), VIVO_SQL), ("Fecha Mañana", norm(fecha["parameters"]["jsCode"]), VIVO_JS)):
        if actual != congelado:
            print(f"ABORTO: «{nombre}» en n8n NO es el que conocemos (alguien lo cambió). Diferencias:")
            print("\n".join(list(difflib.unified_diff(congelado.splitlines(), actual.splitlines(), "congelado 19/11", "vivo hoy", lineterm=""))[:40]))
            sys.exit(2)
    print("   ok: los dos nodos vivos son idénticos a los congelados del 19/11")
    # 2) el SQL nuevo, probado en una tabla temporal (se revierte)
    todo_ok = True
    for nombre, ok, fila in probar_sql_en_tabla_temporal():
        todo_ok &= ok
        print(f"   {'ok ' if ok else 'MAL'}  SQL: {nombre}")
    if not todo_ok:
        sys.exit("el SQL nuevo no se comporta como se espera: no se aplica nada")
    # 3) estado de la columna
    c = conectar(); cur = c.cursor()
    cur.execute("select count(*) from information_schema.columns where table_schema='public' and table_name='recordatorios_config' and column_name='dias_cerrados'")
    existe = cur.fetchone()[0] == 1
    cur.execute("select dias_suspendidos from public.recordatorios_config where id = 1"); susp = [str(x) for x in (cur.fetchone() or [[]])[0]]
    c.close()
    print(f"   columna dias_cerrados: {'ya existe' if existe else 'FALTA (la crea --apply, aditiva)'} · días suspendidos hoy: {susp or 'ninguno'}")
    # 4) diff
    print("\n   ~ «Gate - Leer config» query:")
    for l in difflib.unified_diff(VIVO_SQL.splitlines(), NUEVO_SQL.splitlines(), lineterm="", n=0):
        if l[:1] in "+-" and l[:3] not in ("+++", "---"):
            print("      " + l)
    print("   ~ «Fecha Mañana» jsCode: " + str(sum(1 for l in difflib.unified_diff(VIVO_JS.splitlines(), NUEVO_JS.splitlines(), lineterm="", n=0) if l[:1] in "+-" and l[:3] not in ("+++", "---"))) + " líneas distintas (lectura de la lista y salto de días cerrados; el resto igual)")
    if not a.apply:
        print("\n(simulación: nada se cambió. --apply con el \"desplegá\" de Lucas, en una ventana sin envíos)")
        return
    # 5) aplicar: columna → backup → PUT → verificar
    if not existe:
        c = conectar(escritura=True); cur = c.cursor(); cur.execute(MIGRACION); c.commit(); c.close()
        c = conectar(); cur = c.cursor()
        cur.execute("select data_type, udt_name from information_schema.columns where table_schema='public' and table_name='recordatorios_config' and column_name='dias_cerrados'")
        print("   columna creada:", cur.fetchone()); c.close()
    ts = int(time.time())
    (HIST / f"{WID}_PRE_{ETIQUETA}_{ts}.json").write_text(json.dumps(vivo, ensure_ascii=False, indent=1), encoding="utf-8")
    gate["parameters"]["query"] = NUEVO_SQL
    fecha["parameters"]["jsCode"] = NUEVO_JS
    D.api(f"/workflows/{WID}", "PUT", {"name": vivo["name"], "nodes": vivo["nodes"], "connections": vivo["connections"],
                                        "settings": {k: v for k, v in (vivo.get("settings") or {}).items() if k in D.SETTINGS_OK}})
    post = D.api(f"/workflows/{WID}")
    (HIST / f"{WID}_POST_{ETIQUETA}_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    pn = {n["name"]: n for n in post["nodes"]}
    ok = (norm(pn["Gate - Leer config"]["parameters"]["query"]) == NUEVO_SQL and norm(pn["Fecha Mañana"]["parameters"]["jsCode"]) == NUEVO_JS
          and post.get("active") == vivo.get("active") and json.dumps(post["connections"], sort_keys=True) == json.dumps(vivo["connections"], sort_keys=True))
    print(f"   {'ok' if ok else '¡NO COINCIDE!'} · activo={post.get('active')} · backups en workflows/history (*_{ts}.json)")
    if not ok:
        sys.exit("verificación falló: restaurar con el backup PRE")
    # 6) el Gate nuevo contra la tabla REAL (solo lectura)
    c = conectar(); cur = c.cursor(); cur.execute(NUEVO_SQL); fila = cur.fetchone(); c.close()
    print(f"   Gate nuevo contra la tabla real: suspender={fila[0]} · dias_cerrados={list(fila[1])}")
    print("\nListo. Commit + push de workflows/vivo_huellas.json. Verificar en la PRIMERA corrida real (próximo día hábil 08:00): ejecución del workflow en success,")
    print("fecha_target = hoy + 2 días hábiles (igual que antes mientras no haya días cerrados) y 'Gate - Leer config' con dias_cerrados = [].")


if __name__ == "__main__":
    main()
