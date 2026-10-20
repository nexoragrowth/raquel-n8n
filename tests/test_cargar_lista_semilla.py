# -*- coding: utf-8 -*-
"""
test_cargar_lista_semilla.py — 2026-10-14 · pruebas OFFLINE de scripts/cargar_lista_semilla.py con listas SINTÉTICAS (sin base, sin red).

  · Solo se cargan los que confirmó una persona: quien=Lucas → precarga_confirmada; una propuesta solo con "ok": true en la revisión de
    Lucas → precarga_propuesta_revisada; sin revisar → NO se carga (plan §2.4 "siempre lo decide una persona").
  · 'dudoso' y 'prueba' no se cargan nunca.
  · La revisión no puede aprobar algo que no es propuesta ni cambiar el tipo.
  · --apply sin --ok-dra aborta ANTES de abrir una conexión de escritura; --confirmo-ficha exige el teléfono completo.
Correr: python tests/test_cargar_lista_semilla.py
"""
import contextlib, io, json, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import cargar_lista_semilla as C  # noqa: E402

fallos = 0


def check(nombre, cond, detalle=""):
    global fallos
    print(("OK   " if cond else "FAIL ") + nombre + ("" if cond else " — " + str(detalle)[:300]))
    if not cond:
        fallos += 1


T = {k: "54900000001%02d" % i for i, k in enumerate(["dra", "prov_l", "col_l", "prov_p", "nop_p", "dud", "dev", "prov_p2"])}
LISTA = {"contactos": [
    {"tel": T["dra"], "tipo": "interno", "quien": "Lucas", "nombre": "x", "motivo": "x"},
    {"tel": T["prov_l"], "tipo": "proveedor", "quien": "Lucas", "nombre": "x", "motivo": "x"},
    {"tel": T["col_l"], "tipo": "colega", "quien": "lucas", "nombre": "x", "motivo": "x"},
    {"tel": T["prov_p"], "tipo": "proveedor", "quien": "propuesta (por nombre y pistas, sin leer mensajes)", "nombre": "x", "motivo": "x"},
    {"tel": T["nop_p"], "tipo": "no_paciente", "quien": "propuesta (por nombre y pistas, sin leer mensajes)", "nombre": "x", "motivo": "x"},
    {"tel": T["prov_p2"], "tipo": "proveedor", "quien": "propuesta (por nombre y pistas, sin leer mensajes)", "nombre": "x", "motivo": "x"},
    {"tel": T["dud"], "tipo": "dudoso", "quien": "Lucas", "nombre": "x", "motivo": "x"},
    {"tel": T["dev"], "tipo": "prueba", "quien": "Lucas", "nombre": "x", "motivo": "x"},
]}
tmp = Path(tempfile.mkdtemp(prefix="semilla_"))
lista = tmp / "lista.json"
lista.write_text(json.dumps(LISTA), encoding="utf-8")


def rev(props, quien="lucas"):
    f = tmp / f"rev_{len(list(tmp.iterdir()))}.json"
    f.write_text(json.dumps({"revisado_por": quien, "propuestas": props}), encoding="utf-8")
    return f


# sin revisión: solo los de Lucas
r, e = C.leer_revision(tmp / "no_existe.json")
altas, pend, salt, err = C.leer_lista(lista, r)
check("sin revisión: se cargan solo los 3 confirmados por Lucas", sorted(a["tel"] for a in altas) == sorted([T["dra"], T["prov_l"], T["col_l"]])
      and all(a["motivo"] == "precarga_confirmada" for a in altas), altas)
check("sin revisión: las 3 propuestas quedan pendientes (no se cargan)", sorted(p["tel"] for p in pend) == sorted([T["prov_p"], T["nop_p"], T["prov_p2"]]))
check("dudoso y prueba no se cargan", dict(salt) == {"dudoso": 1, "prueba": 1} and not err, (salt, err))
# revisión: aprueba 1 de 3
r, e = C.leer_revision(rev([{"tel": T["prov_p"], "tipo": "proveedor", "ok": True}, {"tel": T["nop_p"], "tipo": "no_paciente", "ok": False}]))
altas, pend, salt, err = C.leer_lista(lista, r)
m = {a["tel"]: a["motivo"] for a in altas}
check("revisión: la aprobada entra como precarga_propuesta_revisada; las demás siguen pendientes",
      m.get(T["prov_p"]) == "precarga_propuesta_revisada" and T["nop_p"] not in m and T["prov_p2"] not in m and len(pend) == 2 and not e and not err, (m, e, err))
# revisión inválida
r, e = C.leer_revision(rev([{"tel": T["dra"], "tipo": "interno", "ok": True}]))
check("revisión que aprueba algo que no es propuesta → error", any("no es una propuesta" in x for x in C.leer_lista(lista, r)[3]))
r, e = C.leer_revision(rev([{"tel": T["prov_p"], "tipo": "colega", "ok": True}]))
check("revisión que cambia el tipo → error (se corrige la lista)", any("corregir la lista" in x for x in C.leer_lista(lista, r)[3]))
r, e = C.leer_revision(rev([{"tel": T["prov_p"], "tipo": "proveedor", "ok": True}], quien="claude"))
check("revisión firmada por otro que no es Lucas → error", bool(e))


# main: guardas antes de escribir
class Abort(Exception):
    pass


conexiones = []


def conectar_falso(solo_lectura=True):
    conexiones.append(solo_lectura)
    if not solo_lectura:
        raise Abort("intentó abrir una conexión de ESCRITURA")

    class Cur:
        def execute(self, *a):
            self.q = a[0]

        def fetchone(self):
            return (True, True) if "to_regclass" in self.q else (1,) if "from public.pacientes" in self.q else (False,) if "exists" in self.q else (None,)

        def fetchall(self):
            return []

    class Con:
        def cursor(self):
            return Cur()

        def close(self):
            pass
    return Con()


orig = C.conectar
C.conectar = conectar_falso


def correr(argv):
    conexiones.clear()
    out, code = io.StringIO(), None
    try:
        with contextlib.redirect_stdout(out):
            C.main(argv + ["--lista", str(lista), "--revision", str(tmp / "no_existe.json")])
    except SystemExit as ex:
        code = ex.code
    except Abort as ex:
        code = "ESCRIBIÓ: " + str(ex)
    return code, out.getvalue()


code, out = correr(["--apply"])
check("--apply sin --ok-dra aborta sin abrir conexión de escritura", isinstance(code, str) and "--ok-dra" in code and False not in conexiones, (code, conexiones))
code, out = correr(["--confirmo-ficha", T["dra"][-4:]])
check("--confirmo-ficha con los últimos 4 dígitos → rechazado (se pide el teléfono completo)", isinstance(code, str) and "completo" in code, code)
code, out = correr([])
check("simulación: solo conexión de lectura, nombres no impresos", code is None and conexiones == [True] and "propuesta (por nombre" not in out, (code, conexiones))
C.conectar = orig

print(f"\n{'✅' if fallos == 0 else '❌'} fallos: {fallos}")
sys.exit(1 if fallos else 0)
