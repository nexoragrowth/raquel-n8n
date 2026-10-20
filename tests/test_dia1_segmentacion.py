# -*- coding: utf-8 -*-
"""
test_dia1_segmentacion.py — 2026-10-14 · pruebas OFFLINE (sin red, sin escribir nada) de scripts/apply_dia1_segmentacion.py (PUT-B "Día 1").

Base: el v6 VIVO que bajó la última simulación (workflows/current/dia1_segmentacion/v6.json + helper.json, ignorados por git).
  1. Camino feliz: prerrequisitos, construcción, invariantes (sin tipo = grafo de hoy; kill-switch antes del silencio; red terminal y SIN
     tope; aviso técnico terminal y debajo; el v7 sale por el control final; grafo de check_triaje sobre el PROPUESTO) y el JS real de los
     nodos en tests/harness_code_node.mjs.
  2. Mutaciones: cada chequeo importante tiene que DETECTAR un cambio malo.
  3. Reversión quirúrgica: quitar_dia1(construir(v6)) == v6; conserva cambios posteriores; aborta si el Día 1 no está como se aplicó.
  4. Secuencia del --apply y del --revertir --apply con TODO simulado (api, check_triaje, test de la migración, base, backups):
     orden exacto check_triaje < re-GET (mismo versionId) < backup PRE < PUT < GET < backup POST < check_triaje; y que ante cualquier
     guarda en rojo NO hay PUT.
(La garantía de que 'dudoso'/'prueba'/sin tipo no silencian está en la base: tests/test_migracion_contacto_tipos.mjs, que el apply corre.)

Correr:  python scripts/apply_dia1_segmentacion.py   (una vez, solo GET, para bajar los JSON)  →  python tests/test_dia1_segmentacion.py
"""
import contextlib, copy, io, json, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import apply_dia1_segmentacion as S  # noqa: E402
import apply_v7_flag_lucas as A  # noqa: E402

fallos = 0


def check(nombre, cond, detalle=""):
    global fallos
    print(("OK   " if cond else "FAIL ") + nombre + ("" if cond else " — " + str(detalle)[:300]))
    if not cond:
        fallos += 1


ok_todos = lambda l: all(ok for ok, _ in l)
malos = lambda l: [t for ok, t in l if not ok]

if not (S.DRY / "v6.json").exists():
    sys.exit(f"Faltan los JSON vivos en {S.DRY}. Correr antes: python scripts/apply_dia1_segmentacion.py (simulación, solo GET).")
helper = json.loads((S.DRY / "helper.json").read_text(encoding="utf-8"))
v6 = json.loads((S.DRY / "v6.json").read_text(encoding="utf-8"))

# ---------------------------------------------------------------- 1. camino feliz
print(f"\n### base: vivo (versionId {str(v6.get('versionId'))[:8]}, {len(v6['nodes'])} nodos)")
pre = S.prerrequisitos(v6, helper)
check("prerrequisitos en verde", ok_todos(pre), malos(pre))
post = S.construir(v6)
inv = S.invariantes(v6, post)
check(f"invariantes en verde ({len(inv)})", ok_todos(inv), malos(inv))
pru = S.pruebas_offline(v6, post)
check(f"pruebas del JS real en verde ({len(pru)})", ok_todos(pru), malos(pru))
check("construir no toca el v6 de entrada (deepcopy)", not any(n["name"].startswith("Seg:") for n in v6["nodes"]))
check("construir es determinista", S.construir(v6) == post)
check("idempotencia: sobre el v6 ya aplicado, el prerrequisito 'sin nodos Seg' falla", not ok_todos(S.prerrequisitos(post, helper)))
check(f"11 nodos nuevos ({len(v6['nodes'])} → {len(post['nodes'])})", len(post["nodes"]) - len(v6["nodes"]) == len(S.NUEVOS) == 11)
body = S.cuerpo_put(post)
check("PUT: solo claves permitidas y settings filtrados", set(body) <= set(A.PUT_KEYS) and set(body["settings"]) <= A.SETTINGS_OK
      and "availableInMCP" not in body["settings"] and "binaryMode" not in body["settings"], sorted(body["settings"]))


def nodo(w, n):
    return next(x for x in w["nodes"] if x["name"] == n)


# ---------------------------------------------------------------- 2. mutaciones sobre el propuesto
def mut_post(desc, f, espera_en=None):
    p = copy.deepcopy(post)
    f(p)
    r = S.invariantes(v6, p) + S.pruebas_offline(v6, p)
    m = malos(r)
    check(f"mutación detectada: {desc}", m and (espera_en is None or any(espera_en in t for t in m)), m or "no se detectó")


def set_expr(p, n, expr):
    nodo(p, n)["parameters"]["conditions"]["conditions"][0]["leftValue"] = "={{ " + expr + " }}"


def edit_code(p, n, viejo, nuevo):
    c = nodo(p, n)["parameters"]["jsCode"]
    assert viejo in c, (n, viejo)
    nodo(p, n)["parameters"]["jsCode"] = c.replace(viejo, nuevo)


def meter_tope(p):
    """Re-agrega el tope que había: Redis INCR entre ¿Avisar? y Avisar al grupo."""
    x = copy.deepcopy(nodo(p, S.N_FGET))
    x.update(name="Seg: Redis INCR aviso", id="tope-x")
    x["parameters"] = {"operation": "incr", "key": "seg:aviso:x", "expire": True, "ttl": 600}
    p["nodes"].append(x)
    p["connections"][S.N_AVI]["main"][0] = [A.arco(x["name"])]
    p["connections"][x["name"]] = {"main": [[A.arco(S.N_GRUPO)]]}
    S.NUEVOS.append(x["name"])


print("\n### mutaciones")
mut_post("ramas de ¿Silenciar? invertidas", lambda p: p["connections"][S.N_SIL].__setitem__("main", list(reversed(p["connections"][S.N_SIL]["main"]))), "SIN TIPO")
mut_post("¿Silenciar? ignora seg:off", lambda p: set_expr(p, S.N_SIL, f"$('{S.N_TIPO}').first().json.seg_silencia === true"))
mut_post("¿Silenciar? silencia si la consulta falla (falla cerrada)", lambda p: set_expr(p, S.N_SIL, f"$json.seg_off === null && $('{S.N_TIPO}').first().json.seg_silencia !== false"))
mut_post("¿Silenciar? sin booleano estricto (devuelve el valor crudo)", lambda p: set_expr(p, S.N_SIL, f"$json.seg_off === null && $('{S.N_TIPO}').first().json.seg_silencia"))
mut_post("Consultar Tipo sin continueOnFail", lambda p: nodo(p, S.N_TIPO).pop("continueOnFail"), "fail-open")
mut_post("Consultar Tipo con SQL de N filas", lambda p: nodo(p, S.N_TIPO)["parameters"].__setitem__("query",
         "SELECT r.tipo AS seg_tipo, true AS seg_silencia FROM contacto_roles r JOIN pacientes p ON p.id = r.contacto_id WHERE p.telefono = $1"), "SQL de 1 fila")
mut_post("Tipo Salida sin alwaysOutputData", lambda p: nodo(p, S.N_SAL).pop("alwaysOutputData"), "Tipo Salida")
mut_post("Redis GET off sin onError", lambda p: nodo(p, S.N_OFF).pop("onError"), "seg:off")
mut_post("la red de seguridad conectada a Fallback Output", lambda p: p["connections"].__setitem__(S.N_GRUPO, {"main": [[A.arco("Fallback Output")]]}), "red de seguridad")
mut_post("la red de seguridad entra al triaje", lambda p: p["connections"][S.N_AVI]["main"].__setitem__(1, [A.arco("Triaje: Cargar Config")]), "red")
mut_post("interno con red (usa silencia en vez de con_red)", lambda p: edit_code(p, S.N_RED, "conRed === true && tipo !== 'interno' && ", ""), "interno NUNCA")
mut_post("red con regex inventada", lambda p: edit_code(p, S.N_RED, "fiebre|", "fiebre|urgente|"), "copia textual")
mut_post("aviso con resumen en la query (prende el modo humano)", lambda p: edit_code(p, S.N_GRUPO, "qs: { phone: phone }", "qs: { phone: phone, resumen: resumen }"), "body.text")
mut_post("aviso con tomar=true", lambda p: edit_code(p, S.N_GRUPO, "json: true,", "json: true, qs2: { tomar: 'true' },"), "human_takeover")
nuevos0 = list(S.NUEVOS)
mut_post("vuelve el tope de la urgencia (Redis INCR entre ¿Avisar? y Avisar)", meter_tope, "SIN TOPE")
S.NUEVOS[:] = nuevos0
mut_post("Avisar al grupo descarta por contador (2.ª urgencia sin aviso)", lambda p: edit_code(
    p, S.N_GRUPO, "if (!phone) return",
    "const __n = parseInt(Object.values($input.first().json || {}).find(v => typeof v === 'number'), 10);\n"
    "if (__n > 1) return [{ json: { avisado: false, tope: true } }];\nif (!phone) return"), "SIN TOPE")
mut_post("Avisar al grupo nombra a Lucas", lambda p: edit_code(p, S.N_GRUPO, "contestale vos", "avisá a Lucas o contestale vos"), "Lucas")
mut_post("aviso técnico: la rama vuelve al v6", lambda p: p["connections"].__setitem__(S.N_FSET, {"main": [[A.arco(S.TAKEOVER)]]}), "aviso técnico")
mut_post("aviso técnico ARRIBA del camino normal (lo demoraría)", lambda p: nodo(p, S.N_FALLO).__setitem__("position", [7744, 100]), "debajo")
mut_post("aviso técnico: SET del tope ANTES del POST", lambda p: (p["connections"][S.N_FGET].__setitem__("main", [[A.arco(S.N_FSET)]]),
                                                                p["connections"].__setitem__(S.N_FSET, {"main": [[A.arco(S.N_TEC)]]}),
                                                                p["connections"][S.N_TEC].__setitem__("main", [[]])), "DESPUÉS del POST")
mut_post("aviso técnico ignora seg:falla (sin tope)", lambda p: edit_code(p, S.N_TEC, "if (ya !== null && ya !== '') {", "if (false) {"), "ya se avisó")
mut_post("aviso técnico con el teléfono del contacto", lambda p: edit_code(p, S.N_TEC, "body: { text: texto },", "qs: { phone: '1' }, body: { text: texto },"), "sin teléfono")
mut_post("aviso técnico marca el tope aunque el POST falle", lambda p: edit_code(p, S.N_TEC, "  return [];\n}\nreturn [{ json: { aviso_tecnico", "}\nreturn [{ json: { aviso_tecnico"), "helper caído")
mut_post("¿Falló la consulta? siempre true", lambda p: set_expr(p, S.N_FALLO, "true"), "solo con error")
mut_post("aviso técnico con TTL que se renueva (INCR)", lambda p: nodo(p, S.N_FSET)["parameters"].__setitem__("operation", "incr"), "tope fijo")
mut_post("Gate sin el bloque Seg", lambda p: nodo(p, S.GATE)["parameters"].__setitem__("jsCode", nodo(v6, S.GATE)["parameters"]["jsCode"]), "Gate")
mut_post("Gate cierra si la consulta falla", lambda p: edit_code(p, S.GATE, "} catch (e) { segSilencia = false; }", "} catch (e) { segSilencia = true; }"), "nuevo == viejo")
mut_post("Gate ignora seg:off", lambda p: edit_code(p, S.GATE, "(off === null || off === '') && ", ""), "silencia_seg_off")
mut_post("Gate avisa al grupo al bloquear", lambda p: edit_code(p, S.GATE, "  return [];\n}\nlet hasHumano",
         "  await this.helpers.httpRequest({ method: 'POST', url: 'x' });\n  return [];\n}\nlet hasHumano"), "no avisa")
mut_post("Tipo Salida antes del Loop (multiplica envíos)", lambda p: (p["connections"]["Tiene respuesta?"]["main"].__setitem__(0, [A.arco(S.N_SAL)]),
                                                                       p["connections"][S.N_SAL].__setitem__("main", [[A.arco(S.LOOP)]]),
                                                                       p["connections"][S.LOOP]["main"].__setitem__(1, [A.arco(S.TYPING)])), "2 arcos")
mut_post("silencio ANTES del kill-switch (los /bot de la Dra. dejarían de andar)", lambda p: (
    p["connections"]["Kill-switch Check"]["main"].__setitem__(0, [A.arco(S.N_TIPO)]),), "KILL-SWITCH")
mut_post("el admin pasa por Seg", lambda p: p["connections"][S.ESADMIN]["main"][0].append(A.arco(S.N_TIPO)), "bot off")
mut_post("Inbox Live movido detrás del silencio", lambda p: p["connections"][S.N_SIL]["main"][0].append(A.arco("Inbox Live")), "Inbox Live")
mut_post("el v7 saltea el control final", lambda p: p["connections"]["V7: Adaptador"]["main"][0].append(A.arco(S.ENVIAR)), "v7")
mut_post("se perdió el webhookId", lambda p: [n.pop("webhookId", None) for n in p["nodes"]], "webhookId")
mut_post("otro nodo del v6 cambió", lambda p: nodo(p, "Consultar Takeover Paciente")["parameters"].__setitem__("query", "SELECT false AS \"hasHumanoLabel\""), "solo cambia")
mut_post("check_triaje: Switch[2] tocado", lambda p: p["connections"]["Switch sobre Intent"]["main"].__setitem__(2, [A.arco("Sub-Agent General")]), "Switch")


# ---------------------------------------------------------------- 3. mutaciones de los prerrequisitos
def mut_pre(desc, fv=None, fh=None):
    v, h = copy.deepcopy(v6), copy.deepcopy(helper)
    if fv:
        fv(v)
    if fh:
        fh(h)
    try:
        r = S.prerrequisitos(v, h)
        check(f"prerrequisito detecta: {desc}", not ok_todos(r), "no se detectó")
    except (SystemExit, StopIteration, KeyError) as e:
        check(f"prerrequisito detecta: {desc}", True, e)


mut_pre("Parse Intent cambió el criterio de urgencia", fv=lambda v: nodo(v, "Parse Intent")["parameters"].__setitem__(
    "jsCode", nodo(v, "Parse Intent")["parameters"]["jsCode"].replace("fiebre|", "")))
mut_pre("Gate Humano Final sin el ancla (p. ej. PUT-A la reescribió)", fv=lambda v: nodo(v, S.GATE)["parameters"].__setitem__(
    "jsCode", nodo(v, S.GATE)["parameters"]["jsCode"].replace("const phone = (", "const phone = String(")))
mut_pre("Typing pasa a leer $json", fv=lambda v: nodo(v, S.TYPING)["parameters"].__setitem__("jsonBody", "={{ $json.x }}"))
mut_pre("Buffer: Limpiar ya no va a Consultar Takeover", fv=lambda v: v["connections"][S.LIMPIAR]["main"].__setitem__(0, [A.arco("Bot Activo?")]))
mut_pre("helper: Decidir Takeover mira body.text", fh=lambda h: nodo(h, "Decidir Takeover")["parameters"].__setitem__(
    "jsCode", nodo(h, "Decidir Takeover")["parameters"]["jsCode"].replace("q.resumen ?? b.resumen", "q.resumen ?? b.text")))
mut_pre("helper inactivo", fh=lambda h: h.__setitem__("active", False))
mut_pre("v6 sin webhookId evo-webhook-v2", fv=lambda v: [n.pop("webhookId", None) for n in v["nodes"]])

# ---------------------------------------------------------------- 4. reversión quirúrgica
print("\n### reversión quirúrgica")
q, prob = S.quitar_dia1(post)
check("quitar_dia1(construir(v6)) sin problemas", not prob, prob)
check("quitar_dia1(construir(v6)) == v6 (nodos y conexiones)", q is not None and S.norm(q) == S.norm(v6)
      and A.arcos(q["connections"]) == A.arcos(v6["connections"]))
check("verificar_quitado en verde", q is not None and ok_todos(S.verificar_quitado(post, q)), q and malos(S.verificar_quitado(post, q)))
# un cambio POSTERIOR al Día 1 en otro nodo (p. ej. PUT-A rota la clave del Gate o se corrige el triaje) se CONSERVA
p2 = copy.deepcopy(post)
nodo(p2, "Triaje: Decidir")["parameters"]["jsCode"] += "\n// cambio posterior"
nodo(p2, S.GATE)["parameters"]["jsCode"] = nodo(p2, S.GATE)["parameters"]["jsCode"].replace("let hasHumano = false;", "let hasHumano = false; // clave rotada")
q2, prob2 = S.quitar_dia1(p2)
check("revertir conserva cambios posteriores (Triaje: Decidir y la parte del Gate fuera del bloque)", not prob2 and q2
      and nodo(q2, "Triaje: Decidir")["parameters"]["jsCode"].endswith("// cambio posterior")
      and "// clave rotada" in nodo(q2, S.GATE)["parameters"]["jsCode"] and "Seg:" not in nodo(q2, S.GATE)["parameters"]["jsCode"], prob2)
p3 = copy.deepcopy(post)
nodo(p3, S.GATE)["parameters"]["jsCode"] = nodo(p3, S.GATE)["parameters"]["jsCode"].replace("[SEG] salida bloqueada", "[SEG] bloqueada")
check("revertir aborta si el bloque del Gate no está como se aplicó", S.quitar_dia1(p3)[0] is None)
check("revertir aborta sobre un v6 sin Día 1", S.quitar_dia1(v6)[0] is None)
p4 = copy.deepcopy(post)
p4["connections"][S.N_SIL]["main"][1].append(A.arco("Bot Activo?"))
check("revertir aborta si de lo nuevo sale un arco que no es del Día 1", S.quitar_dia1(p4)[0] is None)


# ---------------------------------------------------------------- 5. secuencia del --apply / --revertir --apply (todo simulado)
class Mundo:
    """n8n + check_triaje + test de la migración + base + backups, en memoria. Registra el orden de los eventos."""

    def __init__(self, check_ok=True, mig_ok=True, ruta_ok=True, cambia_version=False, helper_cambia=False, vivo=None):
        self.ev, self.vivo, self.helper = [], copy.deepcopy(vivo or v6), copy.deepcopy(helper)
        self.check_ok, self.mig_ok, self.ruta_ok, self.cambia_version, self.helper_cambia = check_ok, mig_ok, ruta_ok, cambia_version, helper_cambia
        self.gets = 0

    def api(self, path, method="GET", payload=None):
        if method == "PUT":
            self.ev.append(("PUT", None))
            nuevo = copy.deepcopy(payload)
            nuevo.update(active=True, versionId="post-put")
            self.vivo = nuevo
            return {}
        if path.endswith(S.HELPER):
            self.gets += 1
            h = copy.deepcopy(self.helper)
            if self.helper_cambia and self.gets > 1:
                h["active"] = False
            return h
        self.ev.append(("GET", self.vivo.get("versionId")))
        if self.cambia_version and sum(1 for e in self.ev if e[0] == "GET") == 2:
            self.vivo = dict(self.vivo, versionId="otra-version")
            self.ev[-1] = ("GET", "otra-version")
        return copy.deepcopy(self.vivo)

    def guardar(self, ruta, obj):
        self.ev.append(("BACKUP", Path(ruta).name.split("_")[1] + "_" + Path(ruta).name.split("_")[2], obj.get("versionId")))

    def correr_check_triaje(self):
        self.ev.append(("CHECK", None))
        return self.check_ok

    def correr_test_migracion(self):
        self.ev.append(("MIG", None))
        return self.mig_ok, "simulado"

    def estado_db(self):
        return {"ruta_ok": self.ruta_ok, "detalle": "simulado"}


def correr(mundo, argv, fn="main"):
    orig = (A.api, S.guardar, S.correr_check_triaje, S.correr_test_migracion, S.estado_db, S.DRY, S.HIST)
    tmp = Path(tempfile.mkdtemp(prefix="dia1_"))
    A.api, S.guardar, S.correr_check_triaje, S.correr_test_migracion, S.estado_db = (mundo.api, mundo.guardar, mundo.correr_check_triaje,
                                                                                     mundo.correr_test_migracion, mundo.estado_db)
    S.DRY, S.HIST = tmp / "dry", tmp / "hist"
    salida, codigo = io.StringIO(), None
    try:
        with contextlib.redirect_stdout(salida):
            if fn == "main":
                S.main(argv)
            else:
                S.revertir(*argv)
    except SystemExit as e:
        codigo = e.code
    finally:
        A.api, S.guardar, S.correr_check_triaje, S.correr_test_migracion, S.estado_db, S.DRY, S.HIST = orig
    return codigo, salida.getvalue()


def idx(ev, pred):
    return next((i for i, e in enumerate(ev) if pred(e)), None)


print("\n### secuencia del --apply (simulado)")
m = Mundo()
cod, out = correr(m, ["--apply"])
ev = m.ev
i_chk, i_pre, i_put = idx(ev, lambda e: e[0] == "CHECK"), idx(ev, lambda e: e[0] == "BACKUP" and e[1] == "PRE_dia1"), idx(ev, lambda e: e[0] == "PUT")
i_post = idx(ev, lambda e: e[0] == "BACKUP" and e[1] == "POST_dia1")
i_reget = idx(ev[i_chk + 1:] if i_chk is not None else [], lambda e: e[0] == "GET")
check("--apply feliz: termina sin error", cod is None, (cod, out[-400:]))
check("--apply: test de la migración < check_triaje < re-GET (mismo versionId) < backup PRE < PUT < GET < backup POST < check_triaje",
      None not in (i_chk, i_pre, i_put, i_post, i_reget) and idx(ev, lambda e: e[0] == "MIG") < i_chk < i_chk + 1 + i_reget < i_pre < i_put < i_post
      and ev[i_chk + 1 + i_reget][1] == v6.get("versionId") and ev[i_pre][2] == v6.get("versionId")
      and ev[i_put + 1][0] == "GET" and [e[0] for e in ev[i_post + 1:]] == ["CHECK"], ev)
check("--apply: un solo PUT y con el cuerpo filtrado", sum(1 for e in ev if e[0] == "PUT") == 1)
for desc, kw in (("check_triaje no da sano", {"check_ok": False}), ("el test de la migración (PGlite) falla", {"mig_ok": False}),
                 ("contacto_ruta no existe", {"ruta_ok": False}), ("el v6 cambió entre la simulación y el PUT", {"cambia_version": True}),
                 ("el helper cambió (inactivo) entre la simulación y el PUT", {"helper_cambia": True})):
    m = Mundo(**kw)
    cod, out = correr(m, ["--apply"])
    check(f"--apply SIN PUT ni backup si {desc}", cod and not any(e[0] in ("PUT", "BACKUP") for e in m.ev), (cod, m.ev))
m = Mundo()
cod, out = correr(m, [])
check("simulación (sin --apply): ni PUT, ni backup, ni check_triaje", cod is None and not any(e[0] in ("PUT", "BACKUP", "CHECK") for e in m.ev), m.ev)

print("\n### secuencia del --revertir (simulado)")
aplicado = dict(copy.deepcopy(post), active=True, versionId="aplicado")
m = Mundo(vivo=aplicado)
cod, out = correr(m, [False], fn="revertir")
check("--revertir sin --apply: no hace PUT ni backup", cod is None and not any(e[0] in ("PUT", "BACKUP") for e in m.ev), (cod, m.ev, out[-300:]))
m = Mundo(vivo=aplicado)
cod, out = correr(m, [True], fn="revertir")
ev = m.ev
i_chk, i_pre, i_put = idx(ev, lambda e: e[0] == "CHECK"), idx(ev, lambda e: e[0] == "BACKUP" and e[1] == "PRE_revertir"), idx(ev, lambda e: e[0] == "PUT")
check("--revertir --apply: check_triaje < re-GET < backup PRE_revertir < PUT < GET < backup POST_revertir",
      None not in (i_chk, i_pre, i_put) and i_chk < i_pre < i_put and ev[i_chk + 1][0] == "GET" and ev[i_pre][2] == "aplicado"
      and [e[0] for e in ev[i_put:]] == ["PUT", "GET", "BACKUP"], (cod, ev, out[-300:]))
check("--revertir --apply: lo que queda vivo es el v6 sin el Día 1", S.norm(m.vivo) == S.norm(v6) and A.arcos(m.vivo["connections"]) == A.arcos(v6["connections"]))
for desc, kw in (("check_triaje no da sano", {"check_ok": False}), ("el v6 cambió entre el GET y el PUT", {"cambia_version": True})):
    m = Mundo(vivo=aplicado, **kw)
    cod, out = correr(m, [True], fn="revertir")
    check(f"--revertir --apply SIN PUT si {desc}", cod and not any(e[0] in ("PUT", "BACKUP") for e in m.ev), (cod, m.ev))
m = Mundo(vivo=aplicado, check_ok=False)
cod, out = correr(m, [True, True], fn="revertir")
check("--revertir --apply --sin-check-triaje: revierte aunque check_triaje falle (decisión explícita de Lucas)", cod is None
      and any(e[0] == "PUT" for e in m.ev) and not any(e[0] == "CHECK" for e in m.ev), (cod, m.ev))

print(f"\n{'✅' if fallos == 0 else '❌'} fallos: {fallos}")
sys.exit(1 if fallos else 0)
