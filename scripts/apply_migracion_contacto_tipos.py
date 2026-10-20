# -*- coding: utf-8 -*-
"""
apply_migracion_contacto_tipos.py — 2026-10-14 · corre la migración del "Día 1" de la segmentación de contactos
(sql/2026-10-14_contacto_tipos.sql) contra el Supabase v3. Plan: docs/plan-contactos-conversion-dentalink-2026-10-13.md §2.2, §2.5, §2.6,
Anexo A (modelo) y Anexo B (permisos).

QUÉ CREA (aditivo, idempotente, una sola transacción): contacto_roles (historial de tipos, inmutable: solo se cierra), contacto_roles_notas,
contacto_tel_normalizar(), contacto_ruta() (la ÚNICA función que decide si el bot habla: la lee el v6 a la entrada y a la salida),
contacto_tipo_poner() / contacto_tipo_cerrar(), permisos cerrados (anon/authenticated nada; service_role solo EXECUTE de contacto_ruta).
No altera ninguna tabla existente: solo agrega una FK nueva que APUNTA a pacientes(id) (ON DELETE RESTRICT).

POR QUÉ VA ANTES DEL PUT: scripts/apply_dia1_segmentacion.py (PUT-B) llama a public.contacto_ruta($1) y su --apply aborta si no existe.
Sin la función el v6 igual responde (falla abierta), pero cada mensaje registraría un error en "Seg: Consultar Tipo".

USO (Lucas corre el --apply; por defecto SOLO LEE):
  python scripts/apply_migracion_contacto_tipos.py              # simulación: resume el SQL y verifica en una sesión READ-ONLY qué existe hoy
  python scripts/apply_migracion_contacto_tipos.py --ver-sql    # ídem + imprime el SQL completo
  python scripts/apply_migracion_contacto_tipos.py --apply      # corre el SQL (begin…commit adentro del archivo) y verifica después
  python scripts/apply_migracion_contacto_tipos.py --down       # simulación de la vuelta atrás de la ESTRUCTURA (sql/…_DOWN.sql)
  python scripts/apply_migracion_contacto_tipos.py --down --apply   # SOLO si no hubo tipos reales: borra el historial. Deshacer normal =
                                                                    # scripts/cargar_lista_semilla.py --deshacer (cierra, no borra)
Prueba local sin base real: node tests/test_migracion_contacto_tipos.mjs (PGlite con roles de Supabase).
Antes: D1 del plan (Supabase Pro / backups) y "seg:off" puesto si el PUT-B ya estuviera aplicado.
"""
import argparse, json, re, sys, urllib.error, urllib.request
from pathlib import Path

import psycopg2

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
UP = ROOT / "sql" / "2026-10-14_contacto_tipos.sql"
DOWN = ROOT / "sql" / "2026-10-14_contacto_tipos_DOWN.sql"

TABLAS = ["public.contacto_roles", "public.contacto_roles_notas"]
FUNCIONES = ["contacto_tel_normalizar", "contacto_ruta", "contacto_tipo_poner", "contacto_tipo_cerrar",
             "contacto_roles_tg_inmutable", "contacto_roles_tg_no_truncate"]
FIRMAS = ["public.contacto_tel_normalizar(text)", "public.contacto_ruta(text)",
          "public.contacto_tipo_poner(text,text,text,text,text,text,text,uuid,boolean)", "public.contacto_tipo_cerrar(text,text,text,text,text,uuid)",
          "public.contacto_roles_tg_inmutable()", "public.contacto_roles_tg_no_truncate()"]
TEL_SINTETICO = "5490000000001"   # forma sintética del proyecto: nunca es un teléfono real


def clave_anon(env):
    return env.get("SUPABASE_ANON_KEY") or env.get("SUPABASE_V3_ANON_KEY") or env.get("SUPABASE_PUBLISHABLE_KEY")


def verificar_anon_http(env=None):
    """Anexo B punto 5: con la clave ANON (la que está en el navegador del panel), cada objeto nuevo por PostgREST tiene que ser
    RECHAZADO (401/403/404). Solo lectura: las RPC de escritura se llaman con un teléfono sintético y, si no las rechazara, la
    función devolvería CONTACTO_NO_EXISTE sin escribir (el sintético no tiene fila en pacientes)."""
    env = env or leer_env()
    url, key = (env.get("SUPABASE_URL") or "").rstrip("/"), clave_anon(env)
    if not (url and key):
        return [(False, "PostgREST con la clave anon: falta SUPABASE_URL o SUPABASE_ANON_KEY en el .env (es la clave pública del panel)")]
    r = []
    llamadas = [("GET", "/rest/v1/contacto_roles?select=id&limit=1", None), ("GET", "/rest/v1/contacto_roles_notas?select=id&limit=1", None),
                ("POST", "/rest/v1/rpc/contacto_ruta", {"p_telefono": TEL_SINTETICO}),
                ("POST", "/rest/v1/rpc/contacto_tel_normalizar", {"p_telefono": TEL_SINTETICO}),
                ("POST", "/rest/v1/rpc/contacto_tipo_poner", {"p_telefono": "5490000009999", "p_tipo": "proveedor", "p_motivo": "correccion", "p_puesto_por": "anon"}),
                ("POST", "/rest/v1/rpc/contacto_tipo_cerrar", {"p_telefono": "5490000009999", "p_tipo": "proveedor", "p_motivo_baja": "otro", "p_quitado_por": "anon"})]
    for metodo, ruta, cuerpo in llamadas:
        req = urllib.request.Request(url + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                     headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                st = resp.status
        except urllib.error.HTTPError as e:
            st = e.code
        except Exception as e:
            st = f"error de red: {str(e)[:60]}"
        r.append((st in (401, 403, 404), f"anon {metodo} {ruta.split('?')[0]} → {st} (se espera rechazo 401/403/404)"))
    return r


def leer_env():
    env = {}
    for l in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in l and not l.strip().startswith("#"):
            k, v = l.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def conectar(solo_lectura=True):
    """Mismo patrón que scripts/lista_semilla_contactos.py: .env del repo; sesión read-only salvo --apply."""
    env = leer_env()
    c = psycopg2.connect(host=env["SUPABASE_DB_HOST"], port=env["SUPABASE_DB_PORT"], dbname=env["SUPABASE_DB_NAME"],
                         user=env["SUPABASE_DB_USER"], password=env["SUPABASE_DB_PASSWORD"], sslmode="require")
    if solo_lectura:
        c.set_session(readonly=True)
    return c


def resumen_sql(sql):
    """Lista los objetos que crea/borra el archivo (sin ejecutar nada)."""
    pat = re.compile(r"^\s*(create (?:table if not exists|unique index if not exists|index if not exists|or replace function|or replace trigger)"
                     r"|drop (?:table|function) if exists|alter default privileges[^;]*|grant [^;]*|revoke all on (?:table|function)[^;]*)\s*([^\s(]*)",
                     re.I | re.M)
    for m in pat.finditer(sql):
        print(f"    · {m.group(1).strip()[:90]} {m.group(2)}")
    print(f"    ({len(sql.splitlines())} líneas; begin/commit propios: {'sí' if re.search(r'^begin;', sql, re.M) and re.search(r'^commit;', sql, re.M) else 'NO'})")


def estado(cur):
    """Solo lectura: qué existe hoy y con qué usuario entramos. Devuelve dict."""
    e = {}
    cur.execute("select current_user, (select rolsuper from pg_roles where rolname = current_user), "
                "(select pg_get_userbyid(relowner) from pg_class where oid = 'public.pacientes'::regclass), version()")
    e["usuario"], e["super"], e["duenio_pacientes"], e["version"] = cur.fetchone()
    for t in TABLAS:
        cur.execute("select to_regclass(%s) is not null", (t,))
        e[t] = cur.fetchone()[0]
    cur.execute("select proname, count(*) from pg_proc where pronamespace = 'public'::regnamespace and proname = any(%s) group by proname",
                (FUNCIONES,))
    e["funciones"] = dict(cur.fetchall())
    cur.execute("select data_type from information_schema.columns where table_schema='public' and table_name='pacientes' and column_name='id'")
    e["pacientes_id"] = (cur.fetchone() or [None])[0]
    cur.execute("select count(*) from pg_indexes where schemaname='public' and tablename='pacientes' and indexdef ilike '%unique%(telefono)%'")
    e["telefono_unico"] = cur.fetchone()[0] > 0
    cur.execute("select to_regclass('public.recordatorios_enviados') is not null")
    e["recordatorios"] = cur.fetchone()[0]
    cur.execute("select count(*) from pg_roles where rolname in ('anon', 'authenticated', 'service_role')")
    e["roles_supabase"] = cur.fetchone()[0] == 3
    if e["public.contacto_roles"]:
        cur.execute("select count(*), count(*) filter (where hasta is null) from public.contacto_roles")
        e["filas"], e["vigentes"] = cur.fetchone()
    return e


def imprimir_estado(e):
    print(f"  usuario: {e['usuario']} (superusuario: {e['super']}); dueño de pacientes: {e['duenio_pacientes']}")
    print(f"  motor: {e['version'].split(' on ')[0]}")
    print(f"  pacientes.id: {e['pacientes_id']} · telefono único: {e['telefono_unico']} · recordatorios_enviados: {e['recordatorios']} · roles Supabase: {e['roles_supabase']}")
    for t in TABLAS:
        print(f"  {t}: {'YA EXISTE' if e[t] else 'no existe'}")
    print(f"  funciones con esos nombres: {e['funciones'] or 'ninguna'}")
    if "filas" in e:
        print(f"  contacto_roles: {e['filas']} filas ({e['vigentes']} vigentes)")


def verificar_post(cur):
    """Después del --apply (o para --verificar): forma, permisos y una llamada de lectura con un teléfono sintético."""
    r = []
    cur.execute("select public.contacto_ruta(%s)", (TEL_SINTETICO,))
    ruta = cur.fetchone()[0]
    r.append((ruta.get("silencia") is False and ruta.get("tipo") is None and ruta.get("fuente") == "sin_tipo",
              f"contacto_ruta(sintético) = sin tipo, no silencia ({ruta})"))
    cur.execute("select public.contacto_ruta(null)")
    ruta = cur.fetchone()[0]
    r.append((ruta.get("silencia") is False and ruta.get("error") == "telefono_vacio", "contacto_ruta(null) no silencia (telefono_vacio)"))
    # Anexo B: TODOS los objetos nuevos × anon / authenticated / service_role (service_role: solo EXECUTE de contacto_ruta)
    cur.execute("""select rol, obj, priv from unnest(array['anon', 'authenticated', 'service_role']) rol,
                          unnest(%s::text[]) obj, unnest(array['select', 'insert', 'update', 'delete', 'truncate', 'references', 'trigger']) priv
                    where has_table_privilege(rol, obj, priv)""", (TABLAS,))
    abiertas = cur.fetchall()
    r.append((not abiertas, f"tablas nuevas: ningún privilegio para anon/authenticated/service_role ({abiertas[:6]})"))
    cur.execute("""select rol, fn from unnest(array['anon', 'authenticated', 'service_role']) rol, unnest(%s::text[]) fn
                    where has_function_privilege(rol, fn, 'execute')""", (FIRMAS,))
    ejec = sorted(cur.fetchall())
    r.append((ejec == [("service_role", "public.contacto_ruta(text)")], f"funciones nuevas: solo service_role ejecuta contacto_ruta ({ejec})"))
    cur.execute("select bool_and(relrowsecurity) from pg_class where oid = any(%s::regclass[])", (TABLAS,))
    r.append((cur.fetchone()[0] is True, "RLS activo en contacto_roles y contacto_roles_notas"))
    # el SQL EXACTO que usan los nodos "Seg: Consultar Tipo" / "Seg: Tipo Salida" del PUT-B: siempre 1 fila
    sys.path.insert(0, str(ROOT / "scripts"))
    from apply_dia1_segmentacion import SQL_TIPO  # noqa: E402
    cur.execute(SQL_TIPO.replace("$1", "%s"), (TEL_SINTETICO,))
    filas = cur.fetchall()
    r.append((len(filas) == 1 and filas[0][1] is False, f"SQL de los nodos Seg (1 fila, seg_silencia false para un sintético): {filas}"))
    r.extend(verificar_anon_http())
    return r


def main():
    ap = argparse.ArgumentParser(description="Migración Día 1 (contacto_roles + contacto_ruta). Por defecto solo lee.")
    ap.add_argument("--apply", action="store_true", help="corre el SQL (Lucas)")
    ap.add_argument("--down", action="store_true", help="la vuelta atrás de la estructura (borra el historial: solo si no hubo tipos reales)")
    ap.add_argument("--ver-sql", action="store_true")
    ap.add_argument("--verificar", action="store_true", help="solo los chequeos posteriores (read-only)")
    a = ap.parse_args()

    archivo = DOWN if a.down else UP
    sql = archivo.read_text(encoding="utf-8")
    print(f"Archivo: {archivo.relative_to(ROOT)}")
    resumen_sql(sql)
    if a.ver_sql:
        print("\n" + sql)

    c = conectar(solo_lectura=True)
    cur = c.cursor()
    print("\nEstado actual (sesión READ-ONLY):")
    e = estado(cur)
    imprimir_estado(e)
    print(f"  clave anon en el .env (la verificación posterior la usa contra PostgREST, Anexo B.5): {'sí' if clave_anon(leer_env()) else 'NO — agregar SUPABASE_ANON_KEY'}")
    if a.verificar:
        if not e["public.contacto_roles"]:
            c.close()
            sys.exit("La migración no está aplicada (no existe public.contacto_roles).")
        lista = verificar_post(cur)
        c.close()
        for v, t in lista:
            print(("  ✅ " if v else "  ❌ ") + t)
        sys.exit(0 if all(v for v, _ in lista) else 1)
    c.close()

    problemas = []
    if e["super"]:
        problemas.append("se conecta como superusuario: el plan asume 'postgres' de Supabase (no superusuario)")
    if e["duenio_pacientes"] != e["usuario"]:
        problemas.append(f"el usuario ({e['usuario']}) no es dueño de pacientes ({e['duenio_pacientes']}): la FK y los defaults pueden fallar")
    if e["pacientes_id"] != "bigint" or not e["telefono_unico"] or not e["recordatorios"] or not e["roles_supabase"]:
        problemas.append("el esquema base no es el esperado (pacientes.id bigint, telefono único, recordatorios_enviados, roles de Supabase)")
    if a.down and e.get("filas"):
        problemas.append(f"contacto_roles tiene {e['filas']} filas: el DOWN BORRA ese historial. Deshacer normal = cargar_lista_semilla.py --deshacer")
    ya = [t for t in TABLAS if e[t]] + sorted(e["funciones"])
    if not a.down and ya:
        print(f"\n  Nota: ya existen {ya}. La migración es idempotente (create if not exists / or replace) y su autochequeo aborta "
              "si la tabla existe con otra forma.")
    for p in problemas:
        print("  ⚠ " + p)

    if not a.apply:
        print(f"\n[SIMULACION] No se escribió nada. Para aplicar (Lucas): python scripts/apply_migracion_contacto_tipos.py {'--down ' if a.down else ''}--apply")
        return
    if problemas and not a.down:
        sys.exit("ABORTO: revisar los avisos de arriba antes de migrar. No se tocó nada.")
    if a.down and e.get("filas"):
        sys.exit("ABORTO: hay tipos cargados; el DOWN borraría el historial. No se tocó nada.")

    print("\nAplicando (el archivo trae su propio begin/commit; si algo falla no queda nada)…")
    c = conectar(solo_lectura=False)
    c.autocommit = True
    cur = c.cursor()
    try:
        cur.execute(sql)
    except Exception as ex:
        try:
            cur.execute("rollback")
        except Exception:
            pass
        c.close()
        sys.exit(f"FALLÓ la migración (rollback): {ex}")
    print("  OK")
    if a.down:
        c.close()
        print("Estructura del Día 1 quitada.")
        return
    lista = verificar_post(cur)
    c.close()
    malos = [t for v, t in lista if not v]
    for v, t in lista:
        print(("  ✅ " if v else "  ❌ ") + t)
    if malos:
        sys.exit("ATENCION: la verificación posterior no dio lo esperado (ver arriba).")
    print("\nSiguiente: python scripts/cargar_lista_semilla.py (simulación) → PUT-B: python scripts/apply_dia1_segmentacion.py")


if __name__ == "__main__":
    main()
