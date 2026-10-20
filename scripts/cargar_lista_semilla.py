# -*- coding: utf-8 -*-
"""
cargar_lista_semilla.py — 2026-10-14 · carga en contacto_roles la LISTA SEMILLA del Día 1 de la segmentación
(docs/plan-contactos-conversion-dentalink-2026-10-13.md §2.4, §2.6 y §2.7): los contactos que NO son pacientes (la Dra. y el equipo,
colegas, proveedores, no pacientes) para que Asiri deje de contestarles.

Fuente: data/contactos/lista_semilla_final_2026-10-14.json (data/ está en .gitignore: tiene teléfonos y nombres reales).
  · interno / colega / proveedor / no_paciente → se cargan SOLO si una persona los confirmó (plan §2.4: "siempre lo decide una persona"):
      - quien = "Lucas" en la lista             → motivo 'precarga_confirmada'
      - propuesta (por nombre, sin leer mensajes) → NO se carga mientras Lucas no la apruebe UNA POR UNA en
        data/contactos/revisadas_por_lucas.json ("ok": true) → motivo 'precarga_propuesta_revisada'. Las no aprobadas quedan como hoy
        (el bot les responde) y van a la cola de Irina del 02/11.
  · dudoso → NO se carga (no es un tipo).  · prueba → NO se carga: la marca de prueba va en pacientes.es_prueba (Anexo A, 02/11);
    un teléfono sin tipo no silencia, que es lo que hace falta el Día 1.
origen 'precarga', puesto_por 'lucas' (quien confirmó). NO se guarda el nombre ni el motivo libre del JSON.

El --apply exige además --ok-dra: el mensaje al grupo le pide a la Dra. el OK a esta lista antes del 19/10. Sin ese OK no se silencia a nadie.

Escribe SOLO con public.contacto_tipo_poner / contacto_tipo_cerrar (la migración sql/2026-10-14_contacto_tipos.sql tiene que estar aplicada).
Idempotente: cada alta lleva una clave uuid5 fija (precarga-2026-10-14|tel|tipo) → re-correr da "repetido" y no duplica.
Si un tipo que silencia cae sobre alguien con ficha (hasta el espejo de Dentalink la ficha se conoce por recordatorios_enviados, Anexo A),
la función devuelve TIENE_FICHA: el script NO lo fuerza salvo --confirmo-ficha <TELÉFONO COMPLETO> (con OK de Lucas).

Privacidad: por defecto nunca imprime nombres ni mensajes; los teléfonos salen enmascarados (…1234). --ver-nombres muestra, SOLO en la
consola de Lucas, nombre y motivo de las propuestas para poder revisarlas (no correrlo donde la salida quede guardada).

USO (Lucas corre los --apply; por defecto SOLO LEE):
  python scripts/cargar_lista_semilla.py                          # simulación: qué insertaría (sesión READ-ONLY)
  python scripts/cargar_lista_semilla.py --ver-nombres            # ídem + nombre y motivo de las propuestas (solo consola)
  python scripts/cargar_lista_semilla.py --plantilla-revision     # crea data/contactos/revisadas_por_lucas.json con las propuestas en
                                                                  # "ok": false (no pisa uno existente); Lucas pone true a las que aprueba
  python scripts/cargar_lista_semilla.py --apply --ok-dra         # inserta todo en UNA transacción (si una falla, no queda ninguna)
  python scripts/cargar_lista_semilla.py --deshacer [--apply]     # cierra los tipos cargados por ESTA precarga (motivo_baja 'deshacer_precarga')
Lo inmediato para volver al bot de hoy NO es esto: es `seg:off` en Redis (ver scripts/apply_dia1_segmentacion.py --seg-off).
"""
import argparse, json, sys, uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_migracion_contacto_tipos import conectar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
LISTA = ROOT / "data" / "contactos" / "lista_semilla_final_2026-10-14.json"
REVISION = ROOT / "data" / "contactos" / "revisadas_por_lucas.json"
NS = uuid.uuid5(uuid.NAMESPACE_URL, "raquel-n8n/contacto_roles/precarga-2026-10-14")
SILENCIAN = ("interno", "colega", "proveedor", "no_paciente")
ACTOR = "lucas"


def mask(tel):
    return "…" + str(tel)[-4:]


def clave(tel, tipo, baja=False):
    return str(uuid.uuid5(NS, f"{'baja|' if baja else ''}{tel}|{tipo}"))


def tel_valido(tel):
    return tel.isdigit() and 10 <= len(tel) <= 15


def leer_revision(ruta=REVISION):
    """{tel: tipo} de las propuestas que Lucas aprobó ("ok": true). Archivo ausente = ninguna aprobada."""
    ruta = Path(ruta)
    if not ruta.exists():
        return {}, []
    d = json.loads(ruta.read_text(encoding="utf-8"))
    errores = []
    if (d.get("revisado_por") or "").strip().lower() != ACTOR:
        errores.append(f"{ruta.name}: falta \"revisado_por\": \"lucas\"")
    ok = {}
    for p in d.get("propuestas", []):
        if p.get("ok") is True:
            ok[str(p.get("tel", "")).strip()] = (p.get("tipo") or "").strip()
    return ok, errores


def leer_lista(ruta=LISTA, revisadas=None):
    """Devuelve (altas, pendientes, saltados, errores). altas = lo que se carga; pendientes = propuestas sin aprobar (no se cargan)."""
    revisadas = revisadas or {}
    d = json.loads(Path(ruta).read_text(encoding="utf-8"))
    altas, pendientes, saltados, errores = [], [], Counter(), []
    vistos, propuestas = set(), {}
    for c in d.get("contactos", []):
        tel, tipo = str(c.get("tel", "")).strip(), (c.get("tipo") or "").strip()
        if not tel_valido(tel):
            errores.append(f"teléfono con forma rara ({mask(tel)})")
            continue
        if tipo not in SILENCIAN:
            saltados[tipo or "(vacío)"] += 1
            continue
        if tel in vistos:
            errores.append(f"repetido en la lista: {mask(tel)}")
            continue
        vistos.add(tel)
        fila = {"tel": tel, "tipo": tipo, "subtipo": None, "clave": clave(tel, tipo), "nombre": c.get("nombre") or "", "motivo_libre": c.get("motivo") or ""}
        if (c.get("quien") or "").strip().lower() == ACTOR:
            altas.append(dict(fila, motivo="precarga_confirmada"))
            continue
        propuestas[tel] = tipo
        if revisadas.get(tel) == tipo:
            altas.append(dict(fila, motivo="precarga_propuesta_revisada"))
        else:
            pendientes.append(dict(fila, motivo="(sin revisar: no se carga)"))
    for tel, tipo in revisadas.items():
        if tel not in propuestas:
            errores.append(f"la revisión aprueba {mask(tel)}, que no es una propuesta de la lista")
        elif propuestas[tel] != tipo:
            errores.append(f"la revisión aprueba {mask(tel)} como {tipo!r} pero la lista dice {propuestas[tel]!r}: corregir la lista")
    return altas, pendientes, saltados, errores


def prever(cur, altas):
    """Solo lectura: por cada alta, qué pasaría (sin escribir)."""
    cur.execute("select to_regclass('public.contacto_roles') is not null, "
                "exists (select 1 from pg_proc where proname = 'contacto_tipo_poner' and pronamespace = 'public'::regnamespace)")
    hay_tabla, hay_fn = cur.fetchone()
    filas = []
    for a in altas:
        cur.execute("select id from public.pacientes where telefono = %s", (a["tel"],))
        pid = (cur.fetchone() or [None])[0]
        cur.execute("select exists (select 1 from public.recordatorios_enviados where telefono = %s)", (a["tel"],))
        ficha = cur.fetchone()[0]
        vig, por_clave = [], None
        if hay_tabla and pid:
            cur.execute("select tipo from public.contacto_roles where contacto_id = %s and hasta is null order by tipo", (pid,))
            vig = [x[0] for x in cur.fetchall()]
            cur.execute("select hasta is null from public.contacto_roles where clave = %s", (a["clave"],))
            por_clave = (cur.fetchone() or [None])[0]
        if not pid:
            res = "ERROR CONTACTO_NO_EXISTE (no tiene fila en pacientes)"
        elif por_clave is not None:
            res = "repetido (ya cargado por esta precarga" + ("" if por_clave else ", hoy CERRADO") + ")"
        elif a["tipo"] in vig:
            res = "ya_estaba (tipo vigente puesto por otro camino)"
        elif a["tipo"] in SILENCIAN and ficha:
            res = "ERROR TIENE_FICHA (tiene recordatorios; requiere --confirmo-ficha con el teléfono completo)"
        else:
            res = "alta"
        filas.append(dict(a, pid=pid, ficha=ficha, vigentes=vig, prevision=res))
    return hay_tabla, hay_fn, filas


def imprimir(filas, ver_nombres=False):
    print(f"\n  {'tel':7s} {'tipo':12s} {'motivo':28s} {'ficha':5s} {'vigentes hoy':18s} resultado previsto")
    for f in filas:
        print(f"  {mask(f['tel']):7s} {f['tipo']:12s} {f['motivo']:28s} {'sí' if f['ficha'] else 'no':5s} {','.join(f['vigentes']) or '-':18s} {f['prevision']}"
              + (f"\n          {f['nombre']} — {f['motivo_libre']}" if ver_nombres and f["motivo"] != "precarga_confirmada" else ""))


def plantilla(pendientes, ruta=REVISION):
    if Path(ruta).exists():
        sys.exit(f"Ya existe {Path(ruta).name}: editarlo a mano (no se pisa).")
    d = {"instrucciones": "Poner \"ok\": true SOLO en las propuestas que confirmás una por una (el bot les deja de contestar). "
                          "Si el tipo está mal, corregilo en la lista, no acá. Archivo local: data/ no va al repo.",
         "revisado_por": ACTOR, "fecha": None,
         "propuestas": [{"tel": p["tel"], "tipo": p["tipo"], "nombre": p["nombre"], "motivo": p["motivo_libre"], "ok": False} for p in pendientes]}
    Path(ruta).write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Creado {Path(ruta).relative_to(ROOT)} con {len(pendientes)} propuestas en \"ok\": false.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Carga (o deshace) la lista semilla del Día 1 en contacto_roles. Por defecto solo lee.")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ok-dra", action="store_true", help="la Dra. ya dio el OK a la lista (lo pide el mensaje al grupo, antes del 19/10)")
    ap.add_argument("--deshacer", action="store_true", help="cierra los tipos cargados por esta precarga (motivo_baja deshacer_precarga)")
    ap.add_argument("--confirmo-ficha", nargs="*", default=[], metavar="TEL",
                    help="teléfonos COMPLETOS con ficha que Lucas confirmó que igual silencian (doble confirmación del plan §2.2)")
    ap.add_argument("--ver-nombres", action="store_true", help="muestra nombre y motivo de las propuestas (solo consola local)")
    ap.add_argument("--plantilla-revision", action="store_true")
    ap.add_argument("--lista", default=str(LISTA))
    ap.add_argument("--revision", default=str(REVISION))
    a = ap.parse_args(argv)

    revisadas, err_rev = leer_revision(a.revision)
    altas, pendientes, saltados, errores = leer_lista(a.lista, revisadas)
    errores = err_rev + errores
    cuenta = Counter(x["tipo"] for x in altas)
    print(f"Lista: {Path(a.lista).name} → {len(altas)} altas {dict(cuenta)} · no se cargan: {dict(saltados)}")
    print(f"  motivos: {dict(Counter(x['motivo'] for x in altas))} · propuestas SIN revisar (no se cargan): {len(pendientes)} "
          f"{dict(Counter(x['tipo'] for x in pendientes))}")
    if errores:
        sys.exit("ABORTO: la lista o la revisión tienen problemas: " + "; ".join(errores))
    if a.plantilla_revision:
        return plantilla(pendientes, a.revision)
    confirmadas = set()
    for t in a.confirmo_ficha:
        if not tel_valido(t) or t not in {x["tel"] for x in altas}:
            sys.exit(f"--confirmo-ficha: {mask(t)} no es un teléfono completo de las altas de la lista (se pide el número entero, no los últimos 4).")
        confirmadas.add(t)

    c = conectar(solo_lectura=True)
    cur = c.cursor()
    hay_tabla, hay_fn, filas = prever(cur, altas + (pendientes if a.deshacer else []))
    c.close()
    if not (hay_tabla and hay_fn):
        print("\n  ⚠ La migración NO está aplicada (falta public.contacto_roles / contacto_tipo_poner). Primero: "
              "python scripts/apply_migracion_contacto_tipos.py --apply")

    if a.deshacer:
        cerrar = [f for f in filas if f["prevision"].startswith("repetido") and "CERRADO" not in f["prevision"]]
        print(f"\nDESHACER: se cerrarían {len(cerrar)} tipos cargados por esta precarga (los puestos por otro camino no se tocan).")
        for f in cerrar:
            print(f"  {mask(f['tel'])} {f['tipo']}")
        if not a.apply:
            print("\n[SIMULACION] No se escribió nada. Para cerrar (Lucas): python scripts/cargar_lista_semilla.py --deshacer --apply")
            return
        if not cerrar:
            print("Nada para cerrar.")
            return
        c = conectar(solo_lectura=False)
        try:
            with c:
                with c.cursor() as cur:
                    for f in cerrar:
                        # cerrar SOLO si la fila vigente es la de esta precarga (otra alta del mismo tipo no se toca)
                        cur.execute("select 1 from public.contacto_roles where clave = %s and hasta is null", (f["clave"],))
                        if not cur.fetchone():
                            print(f"  {mask(f['tel'])} {f['tipo']}: ya no está vigente (salteado)")
                            continue
                        cur.execute("select public.contacto_tipo_cerrar(%s, %s, 'deshacer_precarga', %s, null, %s::uuid)",
                                    (f["tel"], f["tipo"], ACTOR, clave(f["tel"], f["tipo"], baja=True)))
                        r = cur.fetchone()[0]
                        if not r.get("ok"):
                            raise RuntimeError(f"{mask(f['tel'])} {f['tipo']}: {r.get('error')}")
                        print(f"  {mask(f['tel'])} {f['tipo']}: cerrado → silencia={r.get('ruta', {}).get('silencia')}")
        except Exception as ex:
            sys.exit(f"FALLÓ (rollback, no se cerró ninguno): {ex}")
        finally:
            c.close()
        print("Listo. Los tipos quedan en el historial con hasta/quitado_por/motivo_baja.")
        return

    imprimir(filas, a.ver_nombres)
    if pendientes:
        print(f"\n  {len(pendientes)} propuesta(s) SIN revisar no se cargan (el bot les sigue respondiendo como hoy): "
              + ", ".join(f"{mask(p['tel'])} {p['tipo']}" for p in pendientes))
        print("  Para revisarlas: --ver-nombres (consola) y --plantilla-revision → poner \"ok\": true en data/contactos/revisadas_por_lucas.json")
    prev = Counter(f["prevision"].split(" (")[0] for f in filas)
    print(f"\n  Resumen previsto: {dict(prev)}")
    bloquean = [f for f in filas if f["prevision"].startswith("ERROR") and not (f["prevision"].startswith("ERROR TIENE_FICHA") and f["tel"] in confirmadas)]
    if not a.apply:
        print("\n[SIMULACION] No se escribió nada. Para cargar (Lucas, con el OK de la Dra.): python scripts/cargar_lista_semilla.py --apply --ok-dra")
        return
    if not a.ok_dra:
        sys.exit("ABORTO: falta --ok-dra. El mensaje al grupo le pide a la Dra. el OK a esta lista antes del 19/10; sin ese OK no se carga.")
    if not (hay_tabla and hay_fn):
        sys.exit("ABORTO: falta la migración.")
    if bloquean:
        sys.exit(f"ABORTO: {len(bloquean)} alta(s) darían error (ver tabla). No se escribió nada.")
    if not filas:
        sys.exit("Nada para cargar.")

    c = conectar(solo_lectura=False)
    resultados = Counter()
    try:
        with c:   # una transacción: si una falla, no queda ninguna
            with c.cursor() as cur:
                for f in filas:
                    cur.execute("select public.contacto_tipo_poner(%s, %s, %s, %s, 'precarga', %s, null, %s::uuid, %s)",
                                (f["tel"], f["tipo"], f["motivo"], ACTOR, f["subtipo"], f["clave"], f["tel"] in confirmadas))
                    r = cur.fetchone()[0]
                    if not r.get("ok"):
                        raise RuntimeError(f"{mask(f['tel'])} {f['tipo']}: {r.get('error')}")
                    estado = "repetido" if r.get("repetido") else "ya_estaba" if r.get("ya_estaba") else "alta"
                    resultados[estado] += 1
                    ruta = r.get("ruta") or {}
                    print(f"  {mask(f['tel'])} {f['tipo']:12s} {estado:9s}" + (f" → silencia={ruta.get('silencia')} red={ruta.get('red')}" if ruta else ""))
                # verificación dentro de la misma transacción: lo que va a leer el v6
                cur.execute("select count(*) filter (where (public.contacto_ruta(t)->>'silencia')::boolean) from unnest(%s::text[]) t",
                            ([f["tel"] for f in filas],))
                n_sil = cur.fetchone()[0]
                if n_sil != len(filas):
                    raise RuntimeError(f"contacto_ruta silencia {n_sil} de {len(filas)}: no cierra, se deshace todo")
    except Exception as ex:
        sys.exit(f"FALLÓ (rollback, no se cargó ninguno): {ex}")
    finally:
        c.close()
    print(f"\nListo: {dict(resultados)}. contacto_ruta silencia a los {len(filas)} cargados.")
    print("Hasta el PUT-B (scripts/apply_dia1_segmentacion.py) el bot NO lee esta tabla: nada cambia para nadie.")


if __name__ == "__main__":
    main()
