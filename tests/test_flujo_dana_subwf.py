# -*- coding: utf-8 -*-
"""
test_flujo_dana_subwf.py — 2026-10-05

"Que esta vez SI lo haga": el caso real de la paciente que pidio cambiar su turno y termino derivada a la secretaria (ejecuciones v6
294718-294752), repetido con TODO su contexto real contra el codigo real de los nodos. Sin red y con el reloj fijo en el dia del caso.

  A. ESCENARIOS del sub-WF CancelarReprogramar (el unico que reserva el turno nuevo y anula el viejo): que escribe en la agenda y que le dice
     a la paciente en cada situacion, incluidas las malas (la agenda rechaza, el modelo se equivoca, dos fichas en el mismo celular).
  B. LA CHARLA REAL, TURNO POR TURNO: cada mensaje real, con el contexto y la memoria reales de ese momento y la salida real del Router,
     pasa por `Parse Intent` y, si le toca, por el sub-WF. Las salidas de los 2 parsers LLM del sub-WF son las reales: grabadas de la
     ejecucion cuando el turno paso por el sub-WF, o muestreadas con el modelo real (5 por prompt) cuando no.
  C. FIDELIDAD: en los 3 turnos que en la realidad atendio el sub-WF, el harness tiene que contestar EXACTAMENTE lo que contesto el bot.
  D. BANLIST: todo mensaje que arma el sub-WF pasa por el Banlist Validator vivo sin que lo bloquee.

Se corre en dos configuraciones: HOY (lo que esta vivo) y CON LOS ARREGLOS (scripts/apply_fix_subwf_reprogramar.py +
scripts/apply_fix_ruteo_consultas_cambio.py). El test falla si la configuracion CON LOS ARREGLOS no cumple.

QUE NO PRUEBA: las respuestas del agente de agenda (LLM, no se puede repetir sin llamarlo), el Formatting Agent, el envio por WhatsApp ni la
agenda real (simulada; el formato del POST/PUT es el mismo que la agenda acepto el 14/9). Eso es la prueba en vivo con la ficha de prueba.

USO:  python tests/test_flujo_dana_subwf.py [-v]
"""
import copy, itertools, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import apply_fix_subwf_reprogramar as F  # noqa: E402
import apply_fix_ruteo_consultas_cambio as R  # noqa: E402

FXD = os.path.join(ROOT, "tests", "fixtures")
FX = json.load(open(os.path.join(FXD, "dana_caso_real.json"), encoding="utf-8"))
SUBWF_HOY = json.load(open(os.path.join(FXD, "subwf_cancelar_reprogramar.json"), encoding="utf-8"))
PARSE_HOY = open(os.path.join(FXD, "parse_intent_vivo_2026-10-05.js"), encoding="utf-8").read()
BANLIST = open(os.path.join(FXD, "banlist_validator_vivo_2026-10-05.js"), encoding="utf-8").read()
SUBWF_FIX = F.transformar(SUBWF_HOY) if F.MARCA not in json.dumps(SUBWF_HOY) else SUBWF_HOY
PARSE_FIX = R.transformar_parse(PARSE_HOY) if R.MARCA not in PARSE_HOY else PARSE_HOY
VERBOSO = "-v" in sys.argv

SLOT = {"fecha": "2026-10-22", "hora_inicio": "09:20"}
ACEPTA = {"accepts": True, "slot_chosen": SLOT, "razon": "elige jueves 22 9:20"}
NO_ACEPTA = {"accepts": False, "slot_chosen": None, "razon": "no elige"}
INTENT_OK = {"accion": "reprogramar", "fecha_objetivo": "2026-10-22", "hora_objetivo": "09:20", "franja": None, "hora_minima": None,
             "insiste_horario": False, "fecha_actual_mencionada": None, "info_solicitada": None, "razon": "stub"}
INTENT_AMBIGUO = dict(INTENT_OK, accion="ambiguo", fecha_objetivo=None, hora_objetivo=None)
INTENT_INFO = dict(INTENT_OK, accion="consultar_info", fecha_objetivo=None, hora_objetivo=None, info_solicitada="cuando")
INTENT_FECHA_CRUZADA = dict(INTENT_OK, fecha_actual_mencionada="2026-10-22")   # variante REAL del modelo (1 de 5 en T7)
INTENT_CANCELAR = dict(INTENT_OK, accion="cancelar", fecha_objetivo=None, hora_objetivo=None, fecha_actual_mencionada="2026-10-16")
T = {t["n"]: t for t in FX["turnos"]}


def mem(corte):
    return [m for m in FX["memoria"] if int(m["id"]) <= corte][:20]


def con_ultimo_bot(corte, texto):
    filas = copy.deepcopy(mem(corte))
    filas.insert(0, {"id": str(corte + 1), "message": {"type": "ai", "content": texto, "additional_kwargs": {}}})
    return filas[:20]


def esc(id_, texto, corte=None, memoria=None, intent=None, acepta=None, **extra):
    return {"id": id_, "trigger": {"phone": FX["phone"], "text": texto, "pushName": "CELE"},
            "memoria": memoria if memoria is not None else mem(corte), "dentalink": extra.pop("dentalink", FX["dentalink"]),
            "bloques": FX["bloques"], "ahora": FX["ahora_fijo"], "llm_intent": intent or INTENT_OK, "llm_aceptacion": acepta, **extra}


def citas_con(**cambios):
    d = copy.deepcopy(FX["dentalink"])
    d["citas"]["data"][0].update(cambios)
    return d


def dos_fichas(segunda_rut=""):
    d = copy.deepcopy(FX["dentalink"])
    d["paciente"]["data"] = [{"id": 651, "nombre": "Sofia", "apellidos": "B.", "rut": "", "habilitado": 1},
                             {"id": 777, "nombre": "Martina", "apellidos": "B.", "rut": segunda_rut, "habilitado": 1}]
    return d


# --------------------------------------------------------------------------------------------- A. escenarios del sub-WF
CAMBIA = {"reserva": ("2026-10-22", "09:20"), "anula": 9104, "si": [r"reprogramado", r"22 de octubre", r"9:20"], "no": [r"secretaria"]}
NADA = {"reserva": None, "anula": None, "no": [r"reprogramado", r"queda cancelado"]}
ELIGE_T5, ELIGE_T7 = T[5]["texto"], T[7]["texto"]
PLAIN_RB = "Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel. ¿Procedo con la reserva?"

ESCENARIOS = [
    (esc("A01 REAL T5: elige '22 9y20' tras el bloque (y pide lista de espera)", ELIGE_T5, 10491, acepta=ACEPTA), CAMBIA),
    (esc("A02 REAL T7: 'El turno 22 de octubre alas 9y20' tras el bloque", ELIGE_T7, 10495, acepta=ACEPTA), CAMBIA),
    (esc("A03 igual, pero el parser de intencion dice 'ambiguo'", ELIGE_T7, 10495, intent=INTENT_AMBIGUO, acepta=ACEPTA), CAMBIA),
    (esc("A04 igual, con la variante real del modelo que cruza las fechas", ELIGE_T7, 10495, intent=INTENT_FECHA_CRUZADA, acepta=ACEPTA), CAMBIA),
    (esc("A05 el parser de aceptacion NO acepta: no se escribe a ciegas", ELIGE_T7, 10495, acepta=NO_ACEPTA), NADA),
    (esc("A06 la agenda RECHAZA la reserva: no anula el viejo y NO dice 'listo'", ELIGE_T7, 10495, acepta=ACEPTA, dentalink_rechaza_reserva=True),
     {"reserva": ("2026-10-22", "09:20"), "anula": None, "si": [r"No pude reservar", r"sigue vigente"], "no": [r"reprogramado", r"\bListo\b"], "aviso": True}),
    (esc("A07 reserva OK pero la agenda no deja anular el viejo: lo dice y avisa", ELIGE_T7, 10495, acepta=ACEPTA, dentalink_rechaza_cancel=True),
     {"reserva": ("2026-10-22", "09:20"), "anula": 9104, "si": [r"no pude anular el anterior"], "no": [r"qued[oó] reprogramado", r"\bListo\b"], "aviso": True}),
    (esc("A08 REAL T8: 'Si / Gracias' al read-back de reemplazo", T[8]["texto"], 10497, intent=dict(INTENT_OK, fecha_actual_mencionada="2026-10-16")), CAMBIA),
    (esc("A09 igual, parser de intencion 'ambiguo'", T[8]["texto"], 10497, intent=INTENT_AMBIGUO), CAMBIA),
    (esc("A10 igual, parser de intencion 'consultar_info' (peor caso)", T[8]["texto"], 10497, intent=INTENT_INFO), CAMBIA),
    (esc("A11 read-back + 'Si, pero mejor a las 8': no es una afirmacion pura", "Si, pero mejor a las 8", 10497, acepta=NO_ACEPTA), NADA),
    (esc("A12 read-back cuyo turno viejo ya no esta en la agenda (16/10 → 19/10)", "Si", 10497, dentalink=citas_con(fecha="2026-10-19")), NADA),
    (esc("A13 read-back cuyo turno viejo tiene otra hora (09:10 → 11:00)", "Si", 10497, dentalink=citas_con(hora_inicio="11:00:00", hora_fin="11:40:00")), NADA),
    (esc("A14 read-back de RESERVA NUEVA (sin 'reemplazando') + 'Si': jamas anula el otro turno", "Si", memoria=con_ultimo_bot(10495, PLAIN_RB)), NADA),
    (esc("A15 el modelo acepta un horario que el bot NUNCA ofrecio (22/10 10:00)", ELIGE_T7, 10495,
         acepta={"accepts": True, "slot_chosen": {"fecha": "2026-10-22", "hora_inicio": "10:00"}, "razon": "alucina"}), NADA),
    (esc("A16 el modelo acepta con el año equivocado (2027-10-22 09:20)", ELIGE_T7, 10495,
         acepta={"accepts": True, "slot_chosen": {"fecha": "2027-10-22", "hora_inicio": "09:20"}, "razon": "alucina"}), NADA),
    (esc("A17 el modelo devuelve la hora sin cero ('9:20'): igual vale", ELIGE_T7, 10495,
         acepta={"accepts": True, "slot_chosen": {"fecha": "2026-10-22", "hora_inicio": "9:20"}, "razon": "ok"}), CAMBIA),
    (esc("A18 dos fichas en el celular SIN identificar + acepta horario: pide DNI, no escribe", "El jueves 22 a las 9:20", 10495,
         acepta=ACEPTA, dentalink=dos_fichas()), dict(NADA, si=[r"DNI"])),
    (esc("A19 dos fichas: el DNI es de la SEGUNDA y el turno traido es de la primera: no cruza pacientes", "El jueves 22 a las 9:20, DNI 50111222", 10495,
         acepta=ACEPTA, dentalink=dos_fichas("50111222")), NADA),
    (esc("A20 CANCELAR: la agenda rechaza el PUT: no dice 'queda cancelado'", "No voy a poder ir, cancelame el turno por favor", 8932,
         intent=INTENT_CANCELAR, dentalink_rechaza_cancel=True),
     {"reserva": None, "anula": 9104, "si": [r"No pude cancelar", r"sigue vigente"], "no": [r"queda cancelado", r"\bListo\b"], "aviso": True}),
    (esc("A21 CANCELAR bien: anula y lo dice (regresion)", "No voy a poder ir, cancelame el turno por favor", 8932, intent=INTENT_CANCELAR),
     {"reserva": None, "anula": 9104, "si": [r"queda cancelado"], "no": []}),
    (esc("A22 pedido de cambio inicial: ofrece el bloque (regresion)", T[1]["texto"], 8932, intent=dict(INTENT_OK, fecha_objetivo=None, hora_objetivo=None)),
     dict(NADA, si=[r"turnos disponibles:"])),
    (esc("A23 agenda caida al buscar la ficha: escala sin inventar (regresion)", T[1]["texto"], 8932, dentalink_caido=True), dict(NADA, si=[r"inconveniente tecnico"])),
    (esc("A24 sin memoria previa: no se rompe (regresion)", T[1]["texto"], memoria=[], intent=dict(INTENT_OK, fecha_objetivo=None, hora_objetivo=None)),
     dict(NADA, si=[r"turnos disponibles:"])),
]


def correr_subwf(wf, escenarios, tmp):
    w, e = os.path.join(tmp, "wf.json"), os.path.join(tmp, "esc.json")
    json.dump(wf, open(w, "w", encoding="utf-8"), ensure_ascii=True)
    json.dump(escenarios, open(e, "w", encoding="utf-8"), ensure_ascii=True)
    p = subprocess.run(["node", os.path.join(ROOT, "tests", "harness_subwf.mjs"), w, e], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        sys.exit("node (sub-WF) fallo: " + p.stderr[-2500:])
    return {r["id"]: r for r in json.loads(p.stdout)}


def correr_nodo(casos, tmp):
    c = os.path.join(tmp, "casos.json")
    json.dump(casos, open(c, "w", encoding="utf-8"), ensure_ascii=True)
    p = subprocess.run(["node", os.path.join(ROOT, "tests", "harness_code_node.mjs"), c], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        sys.exit("node (nodo) fallo: " + p.stderr[-2500:])
    return {r["id"]: r for r in json.loads(p.stdout)}


def escrituras_agenda(r):
    pst = [w for w in r["escrituras"] if w["tipo"] == "POST /citas"]
    put = [w for w in r["escrituras"] if w["tipo"].startswith("PUT /citas/")]
    return pst, put


def evaluar(r, exp):
    """Lista de incumplimientos (vacia = cumple)."""
    mal = []
    if r["error"]:
        return ["el flujo tiro error: " + r["error"][:200]]
    pst, put = escrituras_agenda(r)
    msg = r["mensaje"] or ""
    if exp.get("reserva"):
        f, h = exp["reserva"]
        if not (len(pst) == 1 and pst[0]["body"].get("fecha") == f and pst[0]["body"].get("hora_inicio") == h
                and pst[0]["body"].get("id_paciente") == 651 and pst[0]["body"].get("id_dentista") == 1 and pst[0]["body"].get("duracion") == 40):
            mal.append(f"esperaba 1 reserva {f} {h} para la ficha 651; hizo {[w['body'] for w in pst]}")
    elif pst:
        mal.append(f"NO debia reservar; hizo {[w['body'] for w in pst]}")
    if exp.get("anula"):
        if not (len(put) == 1 and put[0]["tipo"] == f"PUT /citas/{exp['anula']}" and put[0]["body"] == {"id_estado": 1}):
            mal.append(f"esperaba anular la cita {exp['anula']}; hizo {[w['tipo'] for w in put]}")
    elif put:
        mal.append(f"NO debia anular nada; hizo {[w['tipo'] for w in put]}")
    if exp.get("reserva") and exp.get("anula") and pst and put:
        orden = [w["tipo"].split(" ")[0] for w in r["escrituras"] if w["tipo"].startswith(("POST /citas", "PUT /citas"))]
        if orden != ["POST", "PUT"]:
            mal.append(f"el orden tiene que ser reservar y recien despues anular; fue {orden}")
    for rx in exp.get("si", []):
        if not re.search(rx, msg, re.I):
            mal.append(f"el mensaje tenia que decir /{rx}/")
    for rx in exp.get("no", []):
        if re.search(rx, msg, re.I):
            mal.append(f"el mensaje NO podia decir /{rx}/")
    if exp.get("aviso") and not any(w["tipo"].startswith("aviso-grupo") for w in r["escrituras"]):
        mal.append("tenia que avisar al grupo de la clinica")
    if not msg.strip():
        mal.append("no armo ningun mensaje para la paciente")
    return mal


# --------------------------------------------------------------------------------------------- B. la charla real turno por turno
def parse_intent(codigo, casos, tmp):
    res = correr_nodo([{"id": str(k), "codigo": codigo, "input": {"output": c["router"]},
                        "nodos": {"Preparar Mensaje Final": {"text": c["texto"]}, "Build Router Context": {"ctx": c["ctx"]}}} for k, c in casos.items()], tmp)
    return {int(k): (v.get("json") or {}) for k, v in res.items()}


def llm_del_turno(t):
    """Combinaciones (intent, aceptacion) REALES para ese turno: grabadas de la ejecucion o muestreadas con el modelo real."""
    if t.get("subwf_real"):
        return [(t["subwf_real"]["llm_intent"], t["subwf_real"]["llm_aceptacion"])], "grabado de la ejecucion real"
    m = t.get("llm_modelo_real") or {}
    ints = m.get("intent") or [INTENT_AMBIGUO]
    aces = m.get("aceptacion") or [None]
    return list(itertools.product(ints, aces)), f"modelo real, {sum(i.get('_veces', 0) for i in ints)} muestras"


#   turno: (quien lo tiene que atender CON LOS ARREGLOS, expectativa si lo atiende el sub-WF)
ESPERADO_CHARLA = {
    1: ("cancelar_o_reprogramar", dict(NADA, si=[r"turnos disponibles:"])),
    2: ("cancelar_o_reprogramar", dict(NADA, si=[r"turnos disponibles:"])),
    3: ("agendar_nuevo", None),      # pregunta abierta de disponibilidad → agente de agenda (como en la realidad, que respondio bien)
    4: ("agendar_nuevo", None),      # "Si" a la pregunta del agente de agenda → agente de agenda
    5: ("cancelar_o_reprogramar", CAMBIA),   # ← aca se habria hecho el cambio
    6: ("cancelar_o_reprogramar", dict(NADA, si=[r"turnos disponibles:"])),
    7: ("cancelar_o_reprogramar", CAMBIA),   # ← y aca
    8: ("cancelar_o_reprogramar", CAMBIA),   # ← y aca (en la realidad: "le paso su consulta a la secretaria")
}
RESPUESTA_REAL_MEMORIA = {1: "10481", 2: "10483", 6: "10495"}   # fila de memoria con lo que contesto el bot real en esos turnos


def charla(parse_codigo, subwf, tmp):
    intents = parse_intent(parse_codigo, {t["n"]: {"router": t["router_real"], "texto": t["texto"], "ctx": t["ctx_real"]} for t in FX["turnos"]}, tmp)
    escs, meta = [], {}
    for t in FX["turnos"]:
        n = t["n"]
        if intents[n].get("intent") != "cancelar_o_reprogramar":
            continue
        combos, origen = llm_del_turno(t)
        meta[n] = (len(combos), origen)
        for i, (it, ac) in enumerate(combos):
            escs.append(esc(f"T{n}#{i}", t["texto"], t["memoria_corte_id"], intent={k: v for k, v in (it or {}).items() if k != "_veces"},
                            acepta=({k: v for k, v in ac.items() if k != "_veces"} if ac else None)))
    res = correr_subwf(subwf, escs, tmp) if escs else {}
    return intents, res, meta


def main():
    fallas = []
    with tempfile.TemporaryDirectory() as tmp:
        hoy = correr_subwf(SUBWF_HOY, [e for e, _ in ESCENARIOS], tmp)
        fix = correr_subwf(SUBWF_FIX, [e for e, _ in ESCENARIOS], tmp)
        print("A. ESCENARIOS DEL SUB-WF (que escribe en la agenda y que le dice a la paciente)\n")
        print("   HOY  ARREGLO  escenario")
        mensajes = {}
        for e, exp in ESCENARIOS:
            m_hoy, m_fix = evaluar(hoy[e["id"]], exp), evaluar(fix[e["id"]], exp)
            print(f"   {'ok  ' if not m_hoy else 'MAL '} {'ok     ' if not m_fix else 'MAL    '}  {e['id']}")
            if m_hoy:
                print(f"        hoy: {m_hoy[0][:150]}")
            for m in m_fix:
                print(f"        ARREGLO NO CUMPLE: {m}")
                fallas.append(f"{e['id']}: {m}")
            if VERBOSO:
                r = fix[e["id"]]
                print(f"        estado={r['estado']} accion={r['accion']} descarte={r['descarte']} escribe={[w['tipo'] for w in r['escrituras']]}\n        mensaje: {r['mensaje']!r}")
            mensajes[e["id"]] = (e["trigger"]["text"], fix[e["id"]]["mensaje"])

        print("\nB. LA CHARLA REAL, TURNO POR TURNO (texto, contexto, memoria y Router reales de cada momento)\n")
        i_hoy, r_hoy, _ = charla(PARSE_HOY, SUBWF_HOY, tmp)
        i_fix, r_fix, meta = charla(PARSE_FIX, SUBWF_FIX, tmp)

        def describir(n, intents, res):
            destino = intents[n].get("intent")
            if destino != "cancelar_o_reprogramar":
                return f"→ {destino}", []
            rs = [v for k, v in res.items() if k.startswith(f"T{n}#")]
            vistos = []
            for r in rs:
                pst, put = escrituras_agenda(r)
                d = ("RESERVA " + pst[0]["body"]["fecha"] + " " + pst[0]["body"]["hora_inicio"] if pst else "") + (" + ANULA " + put[0]["tipo"].split("/")[-1] if put else "")
                d = d or ("ofrece bloque de horarios" if re.search("turnos disponibles:", r["mensaje"] or "") else "responde: " + (r["mensaje"] or "")[:95].replace("\n", " "))
                if d not in vistos:
                    vistos.append(d)
            return "→ sub-WF: " + " | ".join(vistos), rs

        for t in FX["turnos"]:
            n = t["n"]
            d_hoy, _ = describir(n, i_hoy, r_hoy)
            d_fix, rs = describir(n, i_fix, r_fix)
            print(f"  T{n} «{t['texto'][:78].replace(chr(10), ' / ')}»")
            print(f"       en la realidad : {t['atendio_real']} → {(t['respuesta_real'] or '')[:100].replace(chr(10), ' ')}")
            print(f"       bot de HOY     : {d_hoy}")
            print(f"       con ARREGLOS   : {d_fix}" + (f"   [{meta[n][0]} combinacion(es) LLM: {meta[n][1]}]" if n in meta else ""))
            destino_esp, exp = ESPERADO_CHARLA[n]
            if i_fix[n].get("intent") != destino_esp:
                fallas.append(f"T{n}: tenia que ir a {destino_esp} y fue a {i_fix[n].get('intent')}")
                print(f"       ARREGLO NO CUMPLE: tenia que ir a {destino_esp}")
            elif exp is not None:
                for r in rs:
                    for m in evaluar(r, exp):
                        fallas.append(f"T{n} ({r['id']}): {m}")
                        print(f"       ARREGLO NO CUMPLE ({r['id']}): {m}")
            for r in rs:
                mensajes[r["id"]] = (t["texto"], r["mensaje"])

        print("\nC. FIDELIDAD DEL HARNESS (turnos que en la realidad atendio el sub-WF: tiene que contestar lo mismo que contesto el bot)\n")
        for n, fila in RESPUESTA_REAL_MEMORIA.items():
            real = next(m for m in FX["memoria"] if m["id"] == fila)["message"]["content"]
            r = r_hoy.get(f"T{n}#0")
            igual = bool(r) and r["mensaje"] == real
            print(f"   {'ok ' if igual else 'MAL'} T{n}: la respuesta del harness es identica a la del bot real ({len(real)} caracteres)")
            if not igual:
                fallas.append(f"fidelidad T{n}: el harness no reproduce la respuesta real")
                if r:
                    print(f"        harness: {r['mensaje']!r}\n        real   : {real!r}")

        print("\nD. BANLIST VIVO sobre todo mensaje armado por el sub-WF con los arreglos\n")
        casos = [{"id": k, "codigo": BANLIST, "input": {"output": msg}, "nodos": {"Preparar Mensaje Final": {"text": txt, "phone": FX["phone"]},
                                                                                "Build Router Context": {"ctx": ""}}} for k, (txt, msg) in mensajes.items() if msg]
        ban = correr_nodo(casos, tmp)
        bloqueados = [(k, (v.get("json") or {}).get("banlist_triggered"), v.get("error")) for k, v in ban.items() if v.get("error") or (v.get("json") or {}).get("banlist_triggered")]
        print(f"   {'ok ' if not bloqueados else 'MAL'} {len(casos)} mensajes pasan el Banlist sin bloqueo" + (f" — BLOQUEADOS: {bloqueados}" if bloqueados else ""))
        fallas += [f"banlist: {b}" for b in bloqueados]

    print("\nTODO OK (con los arreglos)" if not fallas else f"\n{len(fallas)} INCUMPLIMIENTOS CON LOS ARREGLOS:\n  - " + "\n  - ".join(fallas))
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
