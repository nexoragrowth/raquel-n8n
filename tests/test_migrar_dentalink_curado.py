# -*- coding: utf-8 -*-
"""
test_migrar_dentalink_curado.py — 2026-10-20 · pruebas OFFLINE (sin red, sin base) de las reglas de curado R1-R9 y de las guardas de
scripts/migrar_dentalink.py. Datos 100% ficticios: los celulares usan abonados que empiezan con 0 (388 000-xxxx), que no existen en
la numeración argentina, o la forma sintética del proyecto (5490000000xxx).

Correr:  python tests/test_migrar_dentalink_curado.py
La carga en una base (idempotencia, fases, permisos) la prueba node tests/test_migracion_dentalink_espejo.mjs (PGlite).
"""
import datetime as dt, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import migrar_dentalink as M  # noqa: E402

fallos = 0


def check(nombre, cond, detalle=""):
    global fallos
    print(("OK   " if cond else "FAIL ") + nombre + ("" if cond else " — " + str(detalle)[:300]))
    if not cond:
        fallos += 1


# ---------------------------------------------------------------------------------------------------------------- R1 celulares
CEL = [
    ("5493880000101", ("5493880000101", "ok")),
    ("+5493880000102", ("5493880000102", "ok")),
    ("+54 9 388 000-0103", ("5493880000103", "ok")),
    ("+543880000104", ("5493880000104", "normalizado")),          # sin el 9
    ("3880000105", ("5493880000105", "normalizado")),             # nacional
    ("0388 15 000-0106", ("5493880000106", "normalizado")),       # 0 troncal + 15
    ("388 15 0000107", ("5493880000107", "normalizado")),         # 15 sin 0
    ("11 15 0000-0108", ("5491100000108", "normalizado")),        # AMBA: área de 2 dígitos
    ("0054 9 388 0000109", ("5493880000109", "ok")),              # 00 internacional
    ("93880000110", ("5493880000110", "normalizado")),            # 9 + nacional
    ("3884 15 000110", ("5493884000110", "normalizado")),         # área de 4 dígitos
    ("0000111", (None, "sin_codigo_area")),
    ("4000112", (None, "sin_codigo_area")),
    ("", (None, "vacio")), (None, (None, "vacio")),
    ("123456789012345@lid", (None, "lid")),
    ("123456789012345", (None, "lid")),
    ("+591 70000113", ("59170000113", "extranjero")),
    ("1111111111", (None, "falso")), ("12345", (None, "falso")), ("1234567890", (None, "falso")),
    ("5490000000114", (None, "sintetico")),
    ("5499990000115", (None, "sintetico")),
    ("4880000116", (None, "invalido")),                           # 10 dígitos que no empiezan con 1/2/3
    ("38800001170", (None, "invalido")),
]
for crudo, esperado in CEL:
    check(f"R1 celular {crudo!r}", M.normalizar_celular(crudo) == esperado, M.normalizar_celular(crudo))
check("R1 teléfono fijo → 54 + nacional (sin el 9)", M.normalizar_telefono("0388 000-0118") == ("543880000118", "normalizado"), M.normalizar_telefono("0388 000-0118"))

# ---------------------------------------------------------------------------------------------------------------- R2 documento
DOC = [("30.000.001", None, 0, ("30000001", "ok")), ("3000002", None, 0, ("3000002", "ok")), ("  30 000 003 ", None, 0, ("30000003", "ok")),
       ("", None, 0, (None, "vacio")), ("11111111", None, 0, (None, "falso")), ("12345678", None, 0, (None, "falso")),
       ("300004", None, 0, ("300004", "dudoso")), ("300000005", None, 0, ("300000005", "dudoso")), ("3000", None, 0, (None, "invalido")),
       ("AB000006", None, 1, ("AB000006", "pasaporte_u_otro")), ("X-00007", None, 0, ("X00007", "pasaporte_u_otro"))]
for crudo, tipo, pas, esperado in DOC:
    check(f"R2 documento {crudo!r}", M.normalizar_documento(crudo, tipo, pas) == esperado, M.normalizar_documento(crudo, tipo, pas))

# ---------------------------------------------------------------------------------------------------------------- R3 email
for crudo, esperado in [("Persona.Uno@Ejemplo.com ", ("persona.uno@ejemplo.com", "ok")), ("no@tiene.com", (None, "falso")),
                        ("sinmail@gmail.com", (None, "falso")), ("persona@", (None, "invalido")), ("", (None, "vacio"))]:
    check(f"R3 email {crudo!r}", M.normalizar_email(crudo) == esperado, M.normalizar_email(crudo))

# ---------------------------------------------------------------------------------------------------------------- curar() completo
HOY = dt.date(2026, 10, 20)
base = lambda **kw: {"id": 0, "nombre": "", "apellidos": "", "rut": "", "celular": "", "telefono": "", "email": "", "direccion": "",  # noqa: E731
                     "fecha_nacimiento": "", "fecha_afiliacion": "2026-01-10", "habilitado": 1, "tipo_documento": 0, "es_pasaporte": 0,
                     "observaciones": "", **kw}
pacientes = [
    base(id=1, nombre="Ana", apellidos="Prueba Uno", rut="30000001", celular="+5493880000201", email="a@ejemplo.com", direccion="Calle 1",
         fecha_nacimiento="2015-05-05"),
    base(id=2, nombre="Ana", apellidos="Prueba Uno", celular="5493880000201"),                                     # dup del 1 (v6, sin DNI)
    base(id=3, nombre="Beto", apellidos="Ficticio", rut="30000003", celular="+5493880000201", email="b@ejemplo.com", direccion="Calle 1",
         fecha_nacimiento="1980-01-02"),                                                                         # familia (mismo celular)
    base(id=4, nombre="Carla", apellidos="Inventada", rut="30000004", email="c@ejemplo.com", direccion="x", fecha_nacimiento="1900-01-01"),
    base(id=5, nombre="Carla", apellidos="Inventada", rut="30.000.004", email="c@ejemplo.com", direccion="x", habilitado=0),  # dup por DNI
    base(id=6, nombre="Dario", apellidos="Otro", rut="30000004", email="d@ejemplo.com", direccion="x"),            # DNI compartido, otro nombre
    base(id=7, nombre="Eva", apellidos="Nueva", rut="30000007", celular="5493880000207"),                         # alta del v7 (con DNI)
    base(id=8, nombre="Lid", apellidos="Oculto", celular="123456789012345@lid"),
    base(id=9, nombre="Test", apellidos="Sintetico", celular="5490000000209"),
]
citas = [
    # profesional 1 atiende lunes 15:00-19:20 cada 10 min (2026-10-19 es lunes)
    dict(id=101, id_paciente=1, id_estado=7, fecha="2026-10-26", hora_inicio="15:00:00", hora_fin="15:40:00", duracion=40, id_dentista=1, id_sillon=1,
         id_sucursal=1, id_tratamiento=0, tratamiento_sin_asignar=1, comentarios="Reservado por Asiri (WhatsApp)"),
    dict(id=102, id_paciente=3, id_estado=15, fecha="2026-10-26", hora_inicio="15:20:00", hora_fin="16:00:00", duracion=40, id_dentista=1, id_sillon=1,
         id_sucursal=1, id_tratamiento=0, tratamiento_sin_asignar=1, comentarios=""),                     # se pisa con 101
    dict(id=103, id_paciente=4, id_estado=1, fecha="2026-10-26", hora_inicio="15:20:00", hora_fin="16:00:00", duracion=40, id_dentista=1, id_sillon=1,
         id_sucursal=1, id_tratamiento=0, tratamiento_sin_asignar=1, comentarios=""),                     # anulada: no cuenta
    dict(id=104, id_paciente=999, id_estado=99, fecha="2026-10-24", hora_inicio="10:05:00", hora_fin="10:40:00", duracion=40, id_dentista=1,
         id_sillon=1, id_sucursal=1, id_tratamiento=55, tratamiento_sin_asignar=0, comentarios="cita de prueba"),   # sábado, todo mal
    dict(id=105, id_paciente=7, id_estado=18, fecha="2026-10-27", hora_inicio="08:00:00", hora_fin="08:40:00", duracion=40, id_dentista=1, id_sillon=1,
         id_sucursal=1, id_tratamiento=0, tratamiento_sin_asignar=1, comentarios="Agendado desde el panel"),
]
datos = {
    "sucursales": {"items": [{"id": 1, "nombre": "Sucursal ficticia", "habilitada": 1}], "completo": True},
    "dentistas": {"items": [{"id": 1, "nombre": "Profesional", "apellidos": "Ficticio", "intervalo": 10, "habilitado": 1, "id_sucursal": 1}], "completo": True},
    "sillones": {"items": [{"id": 1, "nombre": "Sillón 1"}], "completo": True},
    "estados_cita": {"items": [{"id": 1, "nombre": "Anulado", "anulacion": 1, "habilitado": 1}, {"id": 7, "nombre": "No confirmado", "anulacion": 0},
                               {"id": 15, "nombre": "Notificado por WhatsApp", "anulacion": 0}, {"id": 18, "nombre": "Confirmado por whatsapp ", "anulacion": 0}],
                     "completo": True},
    "horarios": {"items": [{"id_dentista": 1, "id_sucursal": 1, "intervalo": 10, "dias": [
        {"dia": 1, "hora_inicio": "15:00:00", "hora_fin": "19:20:00", "hora_inicio_break": "15:00:00", "hora_fin_break": "15:00:00", "sillones": 1, "id_box": 1},
        {"dia": 2, "hora_inicio": "08:00:00", "hora_fin": "11:40:00", "sillones": 1, "id_box": 1},
        {"dia": 6, "hora_inicio": "15:00:00", "hora_fin": "15:00:00", "sillones": 1, "id_box": 1}]}], "completo": True},
    "pacientes": {"items": pacientes, "completo": True},
    "citas": {"items": [M.redactar("citas", dict(c), False) for c in citas], "completo": True},
}
T = M.curar(datos, HOY)
F = {f["id"]: f for f in T["fichas"]}
check("R5 dup sin DNI del v6 → canónica la que tiene DNI", F[2]["duplicado_de"] == 1 and F[2]["duplicado_regla"] == "mismo_nombre_y_celular", F[2])
check("R5 canónica marcada tiene_duplicados y sin duplicado_de", F[1]["duplicado_de"] is None and "tiene_duplicados" in F[1]["calidad"])
check("R5 mismo DNI y mismo nombre → dup (canónica = habilitada, id más bajo)", F[5]["duplicado_de"] == 4 and F[5]["duplicado_regla"] == "mismo_documento", F[5])
check("R5 mismo DNI con otro nombre → NO se une, se marca", F[6]["duplicado_de"] is None and "documento_compartido_nombres_distintos" in F[6]["calidad"], F[6])
check("R5 familia en un celular no es duplicado", F[3]["duplicado_de"] is None and "celular_compartido" in F[3]["calidad"] and F[3]["celular_compartido_n"] == 3, F[3])
check("R4 01/01/1900 = relleno → NULL", F[4]["fecha_nacimiento"] is None and "nacimiento_relleno" in F[4]["calidad"], F[4])
check("R4 es_menor", F[1]["es_menor"] is True and F[3]["es_menor"] is False and F[2]["es_menor"] is None)
check("R6 origen bot_v6 (solo nombre/apellido/celular)", F[2]["origen_probable"] == "bot_v6", F[2]["origen_probable"])
check("R6 origen bot_v7 (con DNI, sin el resto)", F[7]["origen_probable"] == "bot_v7", F[7]["origen_probable"])
check("R6 staff", F[1]["origen_probable"] == "staff" and F[3]["origen_probable"] == "staff")
check("R1 @lid en la ficha", F[8]["celular_estado"] == "lid" and F[8]["celular_normalizado"] is None and F[8]["origen_probable"] == "bot_v6")
check("R6 sintético = posible_prueba", "posible_prueba" in F[9]["calidad"] and "posible_prueba" in F[1]["calidad"])  # "Prueba" en el apellido
Ci = {c["id"]: c for c in T["citas"]}
check("R7 solape entre 101 y 102 (no anuladas)", Ci[101]["_solape"] and Ci[102]["_solape"] and not Ci[103]["_solape"])
check("R7 origen inferido", Ci[101]["origen_inferido"] == "bot_v7" and Ci[105]["origen_inferido"] == "panel" and Ci[102]["origen_inferido"] == "staff_o_desconocido")
fl = set(Ci[104]["calidad"])
check("R7 cita con todo mal", {"estado_desconocido", "paciente_inexistente", "tratamiento_inexistente", "fuera_de_grilla", "fuera_de_horario",
                               "duracion_inconsistente", "posible_prueba"} <= fl and Ci[104]["ficha_id"] is None and Ci[104]["estado_id"] is None, fl)
check("R7 la cita conserva el id de Dentalink del paciente aunque no exista", Ci[104]["paciente_dentalink_id"] == 999)
check("R7 dentro de horario", not Ci[101]["fuera_de_horario"] and not Ci[105]["fuera_de_horario"])
check("R7 anulada copia la marca del estado", Ci[103]["anulada"] is True and Ci[101]["anulada"] is False)
check("Texto clínico redactado antes de guardar", Ci[101]["comentarios"] is None and datos["citas"]["items"][0]["comentarios"].get("_redactado") is True)
check("Estado 18 = confirmada, 15 = notificada", {e["id"]: e["categoria"] for e in T["estados_cita"]} == {1: "anulada", 7: "pendiente", 15: "notificada", 18: "confirmada"})
check("Horarios: 3 días, el sábado no atiende", len(T["horarios"]) == 3)

# ---------------------------------------------------------------------------------------------------------------- fases en el SQL
sql = "\n".join(M.sentencias_carga(T, datos, ["a"], "completa", "00000000-0000-4000-8000-000000000001", 0, {}))
check("Fase a: no carga fichas", "insert into agenda.fichas" not in sql)
ins_citas = [s for s in M.sentencias_carga(T, datos, ["a"], "completa", "00000000-0000-4000-8000-000000000001", 0, {}) if s.startswith("insert into agenda.citas")]
check("Fase a: citas sin ficha_id, paciente ni comentarios", ins_citas and all(("ficha_id" not in s and "paciente_dentalink_id" not in s and "comentarios" not in s) for s in ins_citas))
sql_b = "\n".join(M.sentencias_carga(T, datos, ["a", "b"], "completa", "00000000-0000-4000-8000-000000000002", 0, {}))
check("Fase b: fichas sin nombre ni documento", "insert into agenda.fichas" in sql_b and " nombre," not in sql_b.split("insert into agenda.fichas")[1].split("values")[0]
      and "documento" not in sql_b.split("insert into agenda.fichas")[1].split("values")[0])
check("Ningún nombre de paciente en el SQL de fases a,b", "Inventada" not in sql_b and "Ficticio" not in sql_b.split("insert into agenda.fichas")[1])
check("Guarda de extracción incompleta presente", "se aborta (extracción incompleta)" in sql)
check("Solapes recalculados en la base", "select agenda.recalcular_solapes();" in sql)

# ---------------------------------------------------------------------------------------------------------------- guardas
src = (ROOT / "scripts" / "migrar_dentalink.py").read_text(encoding="utf-8")
check("Cliente: ningún método de escritura en el código", not re.search(r"method\s*=\s*['\"](POST|PUT|PATCH|DELETE)", src) and 'metodo = "GET"' in src)
cli = M.DentalinkSoloLectura("x", pausa=0, respetar_ventanas=False)
try:
    cli._pedir("https://evil.example.com/api/v1/pacientes")
    check("Cliente: rechaza URL fuera de la API", False)
except ValueError:
    check("Cliente: rechaza URL fuera de la API", True)
class ClienteFalso:  # sin red: para probar qué pediría la extracción incremental
    def __init__(self):
        self.rutas = []

    def paginar(self, ruta, q=None, max_paginas=None):
        self.rutas.append((ruta, q))
        if ruta == "/tratamientos":
            return ([{"id": 1, "total": 100, "total_realizado": 0, "abonado": 0, "deuda": 100, "finalizado": 0},
                     {"id": 2, "total": 50, "total_realizado": 0, "abonado": 10, "deuda": 40, "finalizado": 0}], True, 200)
        return ([], True, 200)


from types import SimpleNamespace  # noqa: E402
cf = ClienteFalso()
d = M.extraer(cf, SimpleNamespace(desde="2026-10-19 00:00:00", solo="citas,tratamientos,tratamiento_detalles", max_paginas=None, incluir_clinico=False,
                                  sin_detalles=False, totales_planes={1: (100.0, 0.0, 0.0, 100.0, False), 2: (50.0, 0.0, 0.0, 50.0, False)}, contrato_firmado=True), log=lambda *a: None)
check("Incremental: citas filtradas por fecha_actualizacion", ("/citas", {"fecha_actualizacion": {"gte": "2026-10-19 00:00:00"}}) in cf.rutas, cf.rutas)
check("Incremental: detalles solo del plan que cambió", [r for r, _ in cf.rutas if "detalles" in r] == ["/tratamientos/2/detalles"], cf.rutas)
class ClienteCajas(ClienteFalso):
    def paginar(self, ruta, q=None, max_paginas=None):
        self.rutas.append((ruta, q))
        if ruta == "/cajas":
            return ([{"id": 1, "fecha_cierre": "2026-08-10 20:00:00"}, {"id": 2, "fecha_cierre": ""}, {"id": 3, "fecha_cierre": "2026-10-19 20:00:00"}], True, 200)
        return ([], True, 200)


cc = ClienteCajas()
dc = M.extraer(cc, SimpleNamespace(desde="2026-10-19 00:00:00", solo="cajas,devoluciones", max_paginas=None, incluir_clinico=False, sin_detalles=True, contrato_firmado=True), log=lambda *a: None)
check("Incremental: devoluciones solo de cajas abiertas o cerradas desde la última corrida",
      [r for r, _ in cc.rutas if "devoluciones" in r] == ["/cajas/2/devoluciones", "/cajas/3/devoluciones"] and dc["devoluciones"]["completo"] is False, cc.rutas)
check("Incremental: no marca desaparecidos", d["citas"]["completo"] is False and d["tratamiento_detalles"]["completo"] is False and d["tratamientos"]["completo"] is True)
class ClienteArchivos(ClienteFalso):
    def paginar(self, ruta, q=None, max_paginas=None):
        self.rutas.append((ruta, q))
        if ruta == "/pacientes":
            return ([{"id": 1, "nombre": "A"}, {"id": 2, "nombre": "B"}], True, 200)
        if ruta == "/pacientes/1/archivos":
            return ([{"id": 77, "nombre": "estudio ficticio.pdf", "url": "https://ejemplo.invalid/x"}], True, 200)
        if ruta == "/pacientes/2/archivos":
            return ([], False, 404)
        if ruta.endswith("/adicionales"):
            return ([{"nombre": "Cómo nos conoció", "valor": "x"}, {"nombre": "Obra social", "valor": "y"}], True, 200)
        return ([], True, 200)


ca = ClienteArchivos()
d = M.extraer(ca, SimpleNamespace(desde=None, solo="pacientes", max_paginas=None, incluir_clinico=False, sin_detalles=True, con_archivos=True, contrato_firmado=True),
              log=lambda *a: None)
arch, adic = d["paciente_archivos"]["items"], d["paciente_adicionales"]["items"]
check("Archivos: 404 = la ficha no tiene (sigue completo)", d["paciente_archivos"]["completo"] is True and len(arch) == 1)
check("Archivos sin --incluir-clinico: solo id y nombres de campos", arch[0] == {"id": 77, "_padre_id": 1, "_campos": ["id", "nombre", "url"]}, arch)
check("Adicionales: id estable ficha*1000+posición", sorted(x["id"] for x in adic) == [1000, 1001, 2000, 2001], adic)
T2 = M.curar({**d, "estados_cita": {"items": []}}, HOY)
check("Archivos y adicionales van a dentalink_otros (fases d y c)", {(o["entidad"], o["fase"]) for o in T2["dentalink_otros"]} == {("paciente_archivos", "d"), ("paciente_adicionales", "c")}
      and len(T2["dentalink_otros"]) == 5, T2["dentalink_otros"])
# (20/10) SIN contrato: no se piden pagos/cajas/evoluciones/recetas/detalles/devoluciones y de fichas y planes queda solo el id.
class ClienteTodo(ClienteFalso):
    def paginar(self, ruta, q=None, max_paginas=None):
        self.rutas.append((ruta, q))
        if ruta == "/pacientes":
            return ([{"id": 1, "nombre": "Nombre Ficticio", "rut": "30000001", "celular": "5493880000101"}], True, 200)
        if ruta == "/tratamientos":
            return ([{"id": 9, "nombre": "Plan", "id_paciente": 1, "total": 1000}], True, 200)
        return ([], True, 200)


ct = ClienteTodo()
dt_ = M.extraer(ct, SimpleNamespace(desde=None, solo=None, max_paginas=None, incluir_clinico=False, sin_detalles=False, contrato_firmado=False), log=lambda *a: None)
pedidas = {r for r, _ in ct.rutas}
check("Sin contrato: NO pide pagos, cajas, evoluciones, recetas, convenios, detalles ni devoluciones",
      not ({"/pagos", "/cajas", "/evoluciones", "/recetas", "/convenios"} & pedidas) and not any("detalles" in r or "devoluciones" in r for r in pedidas), sorted(pedidas))
check("Sin contrato: de fichas y planes queda SOLO el id", dt_["pacientes"]["items"] == [{"id": 1}] and dt_["tratamientos"]["items"] == [{"id": 9}], [dt_["pacientes"], dt_["tratamientos"]])
check("Sin contrato: las citas igual se piden (fase ocupación)", "/citas" in pedidas)
ct2 = ClienteTodo()
dc2 = M.extraer(ct2, SimpleNamespace(desde=None, solo=None, max_paginas=None, incluir_clinico=False, sin_detalles=True, contrato_firmado=True), log=lambda *a: None)
check("Con contrato: pide todo y conserva la ficha completa", "/pagos" in {r for r, _ in ct2.rutas} and dc2["pacientes"]["items"][0].get("rut") == "30000001")
import os, subprocess  # noqa: E402  — las guardas cortan ANTES de pedir nada a Dentalink o conectarse a la base


VACIA = Path(__import__("tempfile").mkdtemp(prefix="espejo_vacio_"))


def corre(*a, cache=None):
    """SIEMPRE con --usar-cache sobre una carpeta vacía y DENTALINK_TOKEN inválido: si una guarda fallara, el script termina con
    "no hay extracciones" y nunca llega a la red (no compite con el bot)."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "migrar_dentalink.py"), *a, "--usar-cache", "--cache-dir", str(cache or VACIA)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                       env={**os.environ, "PYTHONIOENCODING": "utf-8", "DENTALINK_TOKEN": "token-invalido-de-test"})
    return r.returncode, (r.stdout + r.stderr)


rc, out = corre("--apply", "--fase", "pacientes")
check("Guarda: --fase pacientes --apply sin --contrato-firmado se niega", rc != 0 and "exige --contrato-firmado" in out, out[-300:])
rc, out = corre("--apply", "--fase", "ficha_minima")
check("Guarda: --fase ficha_minima --apply sin --contrato-firmado se niega", rc != 0 and "exige --contrato-firmado" in out, out[-300:])
rc, out = corre("--apply", "--fase", "clinica", "--contrato-firmado")
check("Guarda: --fase clinica sin --incluir-clinico se niega", rc != 0 and "exige --incluir-clinico" in out, out[-300:])
rc, out = corre("--apply", "--solo", "citas")
check("Guarda: --apply con --solo se niega", rc != 0 and "son para pruebas" in out, out[-300:])
rc, out = corre("--verificar", "--incremental")
check("Guarda: --verificar no se mezcla con incremental", rc != 0 and "--verificar compara" in out, out[-300:])
rc, out = corre("--fase", "pacientes", cache=ROOT / "tmp_cache")
check("Guarda: la caché no puede estar dentro del repo", rc != 0 and "dentro del repo" in out, out[-300:])
rc, out = corre("--fase", "ocupacion")
check("Sin caché: termina sin ir a la red", rc != 0 and "no hay extracciones" in out, out[-300:])
rc, out = corre("--con-archivos")
check("Guarda: --con-archivos sin contrato se niega (archivos de cada ficha)", rc != 0 and "--con-archivos" in out and "contrato" in out, out[-300:])
check("lit escapa comillas y NUL", M.lit("O'Brien\x00", "t") == "'O''Brien'" and M.lit(["a'b"], "a") == "array['a''b']::text[]")
check("lit tipos", M.lit(None, "i") == "null" and M.lit(True, "b") == "true" and M.lit("2026-10-20", "d") == "'2026-10-20'::date")

print(f"\n{'TODO OK' if not fallos else f'{fallos} FALLAS'}")
sys.exit(1 if fallos else 0)
