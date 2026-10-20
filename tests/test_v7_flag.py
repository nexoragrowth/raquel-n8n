# -*- coding: utf-8 -*-
"""
test_v7_flag.py — pruebas OFFLINE (sin red) de scripts/apply_v7_flag_lucas.py sobre los JSON vivos que guardó la última simulación
(workflows/current/v7_flag/: v6, cerebro, clinica, agente_urgencias — ignorados por git porque tienen el workflow vivo).

  1. El camino feliz: prerrequisitos, construcción, invariantes y pruebas del JS real (harness) en verde.
  2. Mutaciones: cada invariante/prerrequisito importante tiene que DETECTAR un cambio malo (si no, el chequeo no sirve).

Correr:  python scripts/apply_v7_flag_lucas.py      (una vez, para bajar los JSON)  →  python tests/test_v7_flag.py
"""
import copy, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import apply_v7_flag_lucas as A  # noqa: E402

fallos = 0


def check(nombre, cond, detalle=""):
    global fallos
    print(("OK   " if cond else "FAIL ") + nombre + ("" if cond else " — " + str(detalle)[:300]))
    if not cond:
        fallos += 1


def todos_ok(lista):
    return all(ok for ok, _ in lista)


def malos(lista):
    return [t for ok, t in lista if not ok]


if not (A.DRY / "v6.json").exists():
    sys.exit(f"Faltan los JSON vivos en {A.DRY}. Correr antes: python scripts/apply_v7_flag_lucas.py (simulación, solo GET).")
viv, ids = A.leer_vivos(A.DRY)
v6 = viv["v6"]

# ---------------------------------------------------------------- 1. camino feliz
pre = A.prerrequisitos(viv, ids)
check("prerrequisitos en verde", todos_ok(pre), malos(pre))
post = A.construir(v6, ids)
inv = A.invariantes(v6, post, ids)
check("invariantes en verde", todos_ok(inv), malos(inv))
pru = A.pruebas_offline(v6, post)
check("pruebas del JS real en verde", todos_ok(pru), malos(pru))
check("la construcción no toca el v6 de entrada (deepcopy)", not any(n["name"].startswith("V7:") for n in v6["nodes"]))
check("construir es determinista (mismos ids de nodo en dos corridas)", A.construir(v6, ids) == post)
viv_post = dict(viv, v6=post)
check("idempotencia: sobre el v6 ya aplicado el prerrequisito 'sin nodos V7' falla", not todos_ok(A.prerrequisitos(viv_post, ids)))


# ---------------------------------------------------------------- 2. mutaciones (los chequeos tienen que fallar)
def mut_post(desc, f, espera_en=None):
    p = copy.deepcopy(post)
    f(p)
    r = A.invariantes(v6, p, ids)
    m = malos(r)
    check(f"mutación detectada por invariantes: {desc}", m and (espera_en is None or any(espera_en in t for t in m)), m or "no se detectó")


def mut_viv(desc, f):
    v = copy.deepcopy(viv)
    f(v)
    try:
        r = A.prerrequisitos(v, ids)
        check(f"mutación detectada por prerrequisitos: {desc}", not todos_ok(r), "no se detectó")
    except SystemExit as e:
        check(f"mutación detectada por prerrequisitos: {desc}", True, e)


def nodo(w, nombre):
    return next(n for n in w["nodes"] if n["name"] == nombre)


mut_post("la rama v6 de '¿Vivo?' va a otro nodo", lambda p: p["connections"][A.N_VIVO]["main"].__setitem__(1, [A.arco("Gate Canned Directo")]), "SIN FLAG")
mut_post("'¿Ruta v7?'[no] ya no va al Router", lambda p: p["connections"][A.N_RUTA]["main"].__setitem__(1, [A.arco("Sub-Agent General")]), "SIN FLAG")
mut_post("ramas de '¿Vivo?' invertidas", lambda p: p["connections"][A.N_VIVO].__setitem__("main", list(reversed(p["connections"][A.N_VIVO]["main"]))), "SIN FLAG")
mut_post("un nodo del v6 cambió un parámetro", lambda p: nodo(p, "Pre-filtro Cierre")["parameters"].__setitem__("jsCode", "return [];"), "solo cambian")
mut_post("un arco nuevo del camino v7 a otro nodo del v6", lambda p: p["connections"][A.N_ADA]["main"][0].append(A.arco("Split en Mensajes")), "del camino v7")
mut_post("Redis GET sin fail-open", lambda p: nodo(p, A.N_GET).pop("onError"), "fail-open")
mut_post("el cerebro en modo sombra", lambda p: nodo(p, A.N_CER)["parameters"]["workflowInputs"]["value"].__setitem__("modo", "sombra"), "modo literal")
mut_post("el adaptador escribe memoria", lambda p: nodo(p, A.N_ADA)["parameters"].__setitem__("jsCode", nodo(p, A.N_ADA)["parameters"]["jsCode"] + "\n// INSERT INTO n8n_chat_histories"), "no escribe memoria")
mut_post("se perdió el webhookId", lambda p: [n.pop("webhookId", None) for n in p["nodes"]], "webhookId")
mut_post("Necesita Formatting? perdió una condición vieja", lambda p: nodo(p, A.NECFMT)["parameters"]["conditions"]["conditions"].pop(0), "Necesita Formatting")
mut_post("Banlist Validator tocado", lambda p: nodo(p, A.BANLIST)["parameters"].__setitem__("jsCode", "return $input.all();"), "solo cambian")

mut_viv("Parse Intent cambió el criterio de urgencia", lambda v: nodo(v["v6"], "Parse Intent")["parameters"].__setitem__(
    "jsCode", nodo(v["v6"], "Parse Intent")["parameters"]["jsCode"].replace("fiebre|", "")))
mut_viv("Triaje: Evaluar con drift respecto del repo", lambda v: nodo(v["v6"], A.EVALUAR)["parameters"].__setitem__(
    "jsCode", nodo(v["v6"], A.EVALUAR)["parameters"]["jsCode"] + "\n// cambio hecho en n8n"))
mut_viv("banlist del v6 restaurada", lambda v: nodo(v["v6"], A.BANLIST)["parameters"].__setitem__("jsCode", "const re = new RegExp('esperamos');\nreturn $input.all();"))
mut_viv("cerebro sin derivar_triaje en Devolver", lambda v: nodo(v["cerebro"], "Devolver")["parameters"].__setitem__(
    "jsCode", nodo(v["cerebro"], "Devolver")["parameters"]["jsCode"].replace("derivar_triaje:", "x:")))
mut_viv("cerebro viejo de agente único (sin Orquestador)", lambda v: [n.__setitem__("name", "Asiri") for n in v["cerebro"]["nodes"] if n["name"] == "Orquestador"])
mut_viv("clínica sin 'Redis SET triaje'", lambda v: [n.__setitem__("name", "otro") for n in v["clinica"]["nodes"] if n["name"] == "Redis SET triaje"])
mut_viv("Urgencias sin la tool derivar_triaje conectada", lambda v: v["agente_urgencias"]["connections"].pop("derivar_triaje"))
mut_viv("sub-agente sin id resuelto", lambda v: nodo(v["cerebro"], "Agente Pagos")["parameters"]["workflowId"].__setitem__("value", "PENDIENTE_crear_v7_en_n8n"))
mut_viv("el Router recibe otro arco", lambda v: v["v6"]["connections"]["Set NO_REPLY"]["main"][0].append(A.arco(A.ROUTER)))
mut_viv("Clear Old Memory ya no va a Pre-filtro Cierre", lambda v: v["v6"]["connections"][A.CLEAR]["main"].__setitem__(0, [A.arco("Get KB Datos Pago")]))

print(f"\n{'✅' if fallos == 0 else '❌'} fallos: {fallos}")
sys.exit(1 if fallos else 0)
