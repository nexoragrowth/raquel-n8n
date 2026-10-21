# -*- coding: utf-8 -*-
"""
test_v7_grafo_herramientas.py — v7: ver_turnos, elegir_ficha, proponer y buscar_horarios, ejecutados como GRAFOS de n8n (nodo por nodo, sin red).
USO:  python tests/test_v7_grafo_herramientas.py
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import build_v7_workflows as B  # noqa: E402

AHORA = "2026-10-05T12:36:00Z"
TEL = "5490000000651"
D = "https://api.dentalink.healthatom.com/api/v1"
TRIG = {"tel": TEL, "exec_id_actual": "ex-2", "modo": "vivo"}   # (08/10) las herramientas solo escriben con modo "vivo" explícito
total = fallas = 0


def chequear(nombre, cond, extra=None):
    global total, fallas
    total += 1
    if not cond:
        fallas += 1
        print(f"  FALLA {nombre}" + (f" → {json.dumps(extra, ensure_ascii=False)[:500]}" if extra else ""))
    else:
        print(f"  ok    {nombre}")


def correr(wf, escenarios):
    with tempfile.TemporaryDirectory() as d:
        w, e = os.path.join(d, "wf.json"), os.path.join(d, "e.json")
        json.dump(wf, open(w, "w", encoding="utf-8"), ensure_ascii=True)
        json.dump(escenarios, open(e, "w", encoding="utf-8"), ensure_ascii=True)
        p = subprocess.run(["node", os.path.join(ROOT, "tests", "harness_grafo.mjs"), w, e], capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit("node fallo: " + p.stderr[-2500:])
        return {r["id"]: r for r in json.loads(p.stdout)}


def esc(id_, trigger=None, redis=None, http=None, subwf=None, **x):
    return {"id": id_, "trigger": {**TRIG, **(trigger or {})}, "ahora": AHORA, "redis": redis or {}, "http": http or {}, "subwf": subwf or {}, **x}


R1 = {"data": [{"id": 651, "nombre": "Dana Yael", "apellidos": "Barro", "rut": "49966117", "habilitado": 1}]}
R2 = {"data": [{"id": 651, "nombre": "Dana Yael", "apellidos": "Barro", "rut": "49966117", "habilitado": 1}, {"id": 777, "nombre": "Martina", "apellidos": "Barro", "rut": "51234567", "habilitado": 1}]}
C651 = {"data": [{"id": 9104, "id_paciente": 651, "fecha": "2026-10-16", "hora_inicio": "09:10:00", "id_estado": 15, "estado_anulacion": 0}]}
C777 = {"data": [{"id": 9300, "id_paciente": 777, "fecha": "2026-10-20", "hora_inicio": "16:20:00", "id_estado": 15, "estado_anulacion": 0}]}
ERR = {"error": {"message": "500"}}
FICHA_1 = json.dumps({"fichas": [{"id": 651, "nombre": "Dana Yael", "apellidos": "Barro", "rut": "49966117"}], "elegida": 651})
FICHA_2 = json.dumps({"fichas": [{"id": 651, "nombre": "Dana Yael", "apellidos": "Barro", "rut": "49966117"}, {"id": 777, "nombre": "Martina", "apellidos": "Barro", "rut": "51234567"}], "elegida": None})
TURNOS = json.dumps([{"id": 9104, "id_paciente": 651, "fecha": "2026-10-16", "hora_inicio": "09:10", "id_estado": 15, "estado_anulacion": 0}])
OFERTAS = json.dumps([{"fecha": "2026-10-22", "hora": "08:00"}, {"fecha": "2026-10-22", "hora": "09:20"}])
BLOQUE = "Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n* Viernes 23 de octubre 9:10\n\nPor la tarde:\n* Lunes 2 de noviembre 16:20\n* Miércoles 4 de noviembre 15:00 , 15:40\n\nLe sirve alguno?"


def main():
    # ------------------------------------------------------------------ ver_turnos
    r = correr(B.wf_ver_turnos(), [
        esc("V1 primera vez, una ficha", http={"GET fichas del celular": R1, "GET citas por ficha": C651}),
        esc("V2 familia (2 fichas)", http={"GET fichas del celular": R2, "GET citas por ficha": [C651, C777]}),
        esc("V3 la ficha ya está en Redis", redis={f"ficha:{TEL}": FICHA_1}, http={"GET citas por ficha": C651}),
        esc("V4 el celular no tiene ficha", http={"GET fichas del celular": {"data": []}}),
        esc("V5 la agenda no responde al buscar la ficha", http={"GET fichas del celular": ERR}),
        esc("V6 error al traer los turnos de una ficha", http={"GET fichas del celular": R2, "GET citas por ficha": [C651, ERR]}),
    ])
    print("ver_turnos")
    x = r["V1 primera vez, una ficha"]; a = x["reps"][0]; s = a["salida"]
    chequear("V1 sin error del motor", a["error"] is None, a["error"])
    chequear("V1 busca la ficha por los últimos 10 dígitos del celular", a["pedidos"][0]["query"] == {"q": json.dumps({"celular": {"lk": "0000000651"}}, separators=(",", ":"))}, a["pedidos"][0])
    chequear("V1 pide las citas desde HOY (hora de Jujuy)", a["pedidos"][1]["query"] == {"q": json.dumps({"fecha": {"gte": "2026-10-05"}}, separators=(",", ":"))}, a["pedidos"][1])
    chequear("V1 guarda la ficha elegida (una sola) y los turnos vistos en Redis", json.loads(x["redis_final"][f"ficha:{TEL}"])["elegida"] == 651 and json.loads(x["redis_final"][f"turnos_vistos:{TEL}"])[0]["id"] == 9104, x["redis_final"])
    chequear("V1 le devuelve a Asiri texto, no ids", s["ok"] is True and s["turnos"] == ["viernes 16/10 a las 09:10"] and "9104" not in json.dumps(s) and s["ficha_elegida"] is True, s)
    x = r["V2 familia (2 fichas)"]; a = x["reps"][0]; s = a["salida"]
    chequear("V2 familia: trae los turnos de las DOS fichas, con el nombre de cada paciente", s["turnos"] == ["viernes 16/10 a las 09:10 (Dana Yael)", "martes 20/10 a las 16:20 (Martina)"], s)
    chequear("V2 familia: ninguna elegida y le dice a Asiri que pregunte para quién es", s["ficha_elegida"] is False and "elegir_ficha" in s["para_asiri"] and json.loads(x["redis_final"][f"ficha:{TEL}"])["elegida"] is None, s)
    chequear("V2 una consulta de citas por ficha", sum(1 for p in a["pedidos"] if "/citas" in p["url"]) == 2, a["pedidos"])
    a = r["V3 la ficha ya está en Redis"]["reps"][0]
    chequear("V3 no vuelve a buscar la ficha", not any(p["url"].endswith("/pacientes") for p in a["pedidos"]) and a["salida"]["ok"] is True, a["pedidos"])
    a = r["V4 el celular no tiene ficha"]["reps"][0]
    chequear("V4 sin ficha: lo dice y no inventa turnos ni toca Redis", a["salida"]["motivo"] == "sin_ficha" and not any(k.startswith("turnos_vistos") for k in r["V4 el celular no tiene ficha"]["redis_final"]), a["salida"])
    a = r["V5 la agenda no responde al buscar la ficha"]["reps"][0]
    chequear("V5 error_tecnico con instrucción de avisar a la clínica", a["salida"]["motivo"] == "error_tecnico" and "avisar_grupo" in a["salida"]["para_asiri"], a["salida"])
    x = r["V6 error al traer los turnos de una ficha"]; a = x["reps"][0]
    chequear("V6 un error en una ficha NO deja turnos a medias en Redis", a["salida"]["motivo"] == "error_tecnico" and f"turnos_vistos:{TEL}" not in x["redis_final"], a["salida"])

    # ------------------------------------------------------------------ elegir_ficha
    r = correr(B.wf_elegir_ficha(), [
        esc("E1 por nombre", {"nombre": "es para Martina", "dni": ""}, {f"ficha:{TEL}": FICHA_2}),
        esc("E2 por DNI", {"nombre": "", "dni": "49.966.117"}, {f"ficha:{TEL}": FICHA_2}),
        esc("E3 apellido común: ambiguo", {"nombre": "Barro", "dni": ""}, {f"ficha:{TEL}": FICHA_2}),
        esc("E4 sin ver_turnos antes", {"nombre": "Martina", "dni": ""}),
        esc("E5 DNI de otra persona", {"nombre": "", "dni": "11222333"}, {f"ficha:{TEL}": FICHA_2}),
    ])
    print("\nelegir_ficha")
    x = r["E1 por nombre"]; chequear("E1 'es para Martina' elige la 777 y la guarda 20 min", json.loads(x["redis_final"][f"ficha:{TEL}"])["elegida"] == 777 and x["reps"][0]["salida"]["ok"] is True, x["reps"][0]["salida"])
    x = r["E2 por DNI"]; chequear("E2 DNI con puntos elige la 651", json.loads(x["redis_final"][f"ficha:{TEL}"])["elegida"] == 651, x["redis_final"])
    x = r["E3 apellido común: ambiguo"]; chequear("E3 'Barro' es ambiguo: pide DNI y NO elige", x["reps"][0]["salida"]["motivo"] == "ambiguo" and json.loads(x["redis_final"][f"ficha:{TEL}"])["elegida"] is None, x["reps"][0]["salida"])
    x = r["E4 sin ver_turnos antes"]; chequear("E4 sin ficha en Redis: pide ver_turnos primero", x["reps"][0]["salida"]["motivo"] == "sin_ficha", x["reps"][0]["salida"])
    x = r["E5 DNI de otra persona"]; chequear("E5 DNI que no es de ninguna ficha: no elige", x["reps"][0]["salida"]["motivo"] == "dni_no_coincide" and json.loads(x["redis_final"][f"ficha:{TEL}"])["elegida"] is None, x["reps"][0]["salida"])

    # ------------------------------------------------------------------ proponer
    base = {f"ficha:{TEL}": FICHA_1, f"turnos_vistos:{TEL}": TURNOS, f"ofertas:{TEL}": OFERTAS}
    CAMBIO = {"tipo": "cambio", "fecha": "2026-10-22", "hora": "9:20", "fecha_turno_viejo": "2026-10-16"}
    r = correr(B.wf_proponer(), [
        esc("P1 cambio feliz", CAMBIO, base),
        esc("P2 horario que nadie ofreció", {**CAMBIO, "hora": "10:00"}, base),
        esc("P3 sin ver_turnos antes", CAMBIO, {k: v for k, v in base.items() if not k.startswith("turnos_vistos")}),
        esc("P4 dos fichas sin elegir", CAMBIO, {**base, f"ficha:{TEL}": FICHA_2, f"turnos_vistos:{TEL}": json.dumps(json.loads(TURNOS) + [{**json.loads(TURNOS)[0], "id": 9300, "id_paciente": 777}])}),   # las dos con turno ese día: ambiguo
        esc("P5 turno en menos de 48 h", {**CAMBIO, "fecha_turno_viejo": "2026-10-06"}, {**base, f"turnos_vistos:{TEL}": json.dumps([{"id": 9, "id_paciente": 651, "fecha": "2026-10-06", "hora_inicio": "09:10", "id_estado": 15, "estado_anulacion": 0}])}),
        esc("P6 el modelo intenta colar un paciente_id", {**CAMBIO, "paciente_id": 777}, base),
    ])
    print("\nproponer")
    x = r["P1 cambio feliz"]; s = x["reps"][0]["salida"]; prop = json.loads(x["redis_final"][f"propuesta:{TEL}"])
    chequear("P1 el read-back es EXACTAMENTE el que el bot real mandó el 05/10", s["texto_para_el_paciente"] == "Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?", s)
    chequear("P1 guarda la propuesta con la ficha del estado, la cita vista y el exec_id actual", prop["paciente_id"] == 651 and prop["cita_vieja"]["id"] == 9104 and prop["exec_id"] == "ex-2" and prop["estado"] == "pendiente", prop)
    for k, motivo in [("P2 horario que nadie ofreció", "no_ofrecido"), ("P3 sin ver_turnos antes", "ver_turnos_primero"), ("P4 dos fichas sin elegir", "ficha_no_elegida"), ("P5 turno en menos de 48 h", "menos_48h")]:
        x = r[k]; chequear(f"{k[:2]} → {motivo} y NO guarda propuesta", x["reps"][0]["salida"]["motivo"] == motivo and f"propuesta:{TEL}" not in x["redis_final"], x["reps"][0]["salida"])
    x = r["P6 el modelo intenta colar un paciente_id"]; chequear("P6 el paciente_id del modelo se ignora: la propuesta usa la ficha del estado (651)", json.loads(x["redis_final"][f"propuesta:{TEL}"])["paciente_id"] == 651)

    # ------------------------------------------------------------------ buscar_horarios
    r = correr(B.wf_buscar_horarios(), [
        esc("B1 primer bloque", {"desde": "", "hasta": ""}, {}, subwf={"Buscar horarios (sub-WF)": {"bloque": BLOQUE, "total_manana": 3, "total_tarde": 3}}),
        esc("B2 tercer pedido: límite", {"desde": "", "hasta": ""}, {f"lotes:{TEL}": 2, f"ofertas:{TEL}": OFERTAS}, subwf={"Buscar horarios (sub-WF)": {"bloque": BLOQUE}}),
        esc("B3 sin turnos", {"desde": "", "hasta": ""}, {}, subwf={"Buscar horarios (sub-WF)": {"resultado": "SIN TURNOS"}}),
        esc("B4 la agenda falla", {"desde": "", "hasta": ""}, {}, subwf={"Buscar horarios (sub-WF)": {"error": {"message": "x"}}}),
        esc("B5 segundo bloque: se suma a lo ya ofrecido", {"desde": "2026-10-24", "hasta": ""}, {f"lotes:{TEL}": 1, f"ofertas:{TEL}": json.dumps([{"fecha": "2026-10-22", "hora": "09:20"}])}, subwf={"Buscar horarios (sub-WF)": {"bloque": "Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Martes 27 de octubre 8:00 , 10:40\n\nLe sirve alguno?"}}),
        esc("B6 el modelo pide lo MISMO dos veces", {"desde": "", "hasta": ""}, {f"lotes:{TEL}": 2, f"bloque:{TEL}": BLOQUE, f"bloque_req:{TEL}": "|", f"ofertas:{TEL}": OFERTAS}, subwf={"Buscar horarios (sub-WF)": {"bloque": "NO DEBE LLAMARSE"}}),
        esc("B8 pide otra ventana y vuelve el MISMO bloque (sin horarios nuevos)", {"desde": "2026-10-08", "hasta": ""}, {f"lotes:{TEL}": 1, f"bloque:{TEL}": BLOQUE, f"bloque_req:{TEL}": "|",
            f"ofertas:{TEL}": json.dumps([{"fecha": "2026-10-22", "hora": h} for h in ("08:00", "09:20")] + [{"fecha": "2026-10-23", "hora": "09:10"}, {"fecha": "2026-11-02", "hora": "16:20"}] + [{"fecha": "2026-11-04", "hora": h} for h in ("15:00", "15:40")])},
            subwf={"Buscar horarios (sub-WF)": {"bloque": BLOQUE}}),
        esc("B9 el bloque vino en un formato que no se puede leer", {"desde": "", "hasta": ""}, {f"ofertas:{TEL}": OFERTAS}, subwf={"Buscar horarios (sub-WF)": {"bloque": "Turnos: consultar"}}),
        esc("B7 pedido distinto con 2 bloques ya contados", {"desde": "2026-11-10", "hasta": ""}, {f"lotes:{TEL}": 2, f"bloque:{TEL}": BLOQUE, f"bloque_req:{TEL}": "|", f"ofertas:{TEL}": OFERTAS}, subwf={"Buscar horarios (sub-WF)": {"bloque": "NO DEBE LLAMARSE"}}),
    ])
    print("\nbuscar_horarios")
    x = r["B1 primer bloque"]; a = x["reps"][0]
    ofertas = json.loads(x["redis_final"][f"ofertas:{TEL}"])
    chequear("B1 devuelve el bloque de la clínica tal cual y la nota para Asiri es interna (no parece un mensaje al paciente)", a["salida"]["bloque"] == BLOQUE and a["salida"]["para_asiri"].startswith("[Nota interna") and "tal cual" in a["salida"]["para_asiri"], a["salida"])
    chequear("B1 registra los 6 horarios ofrecidos con fecha ISO (lo único reservable)", len(ofertas) == 6 and ofertas[1] == {"fecha": "2026-10-22", "hora": "09:20"}, ofertas)
    chequear("B1 guarda el bloque, el pedido, cuenta el lote y marca el bloque de ESTA ejecución (el código lo exige pegado)", x["redis_final"][f"bloque:{TEL}"] == BLOQUE and x["redis_final"][f"lotes:{TEL}"] == 1 and x["redis_final"][f"bloque_req:{TEL}"] == "|" and x["redis_final"][f"bloque_exec:{TEL}:ex-2"] == BLOQUE, x["redis_final"])
    x = r["B2 tercer pedido: límite"]; a = x["reps"][0]
    chequear("B2 el tercer bloque no se busca (regla de la Dra.) y se avisa a Asiri qué hacer", a["salida"]["motivo"] == "limite_de_bloques" and not any(p["metodo"] == "executeWorkflow" for p in a["pedidos"]) and "FYI" in a["salida"]["para_asiri"], a["salida"])
    x = r["B3 sin turnos"]; chequear("B3 sin turnos: no inventa y no guarda ofertas", x["reps"][0]["salida"]["motivo"] == "sin_turnos" and f"ofertas:{TEL}" not in x["redis_final"], x["reps"][0]["salida"])
    x = r["B4 la agenda falla"]; chequear("B4 error_tecnico", x["reps"][0]["salida"]["motivo"] == "error_tecnico", x["reps"][0]["salida"])
    x = r["B5 segundo bloque: se suma a lo ya ofrecido"]; of = json.loads(x["redis_final"][f"ofertas:{TEL}"])
    chequear("B5 las ofertas se SUMAN (puede elegir del bloque anterior)", {"fecha": "2026-10-22", "hora": "09:20"} in of and {"fecha": "2026-10-27", "hora": "10:40"} in of and len(of) == 3, of)
    chequear("B5 el sub-WF recibió el 'desde' que pidió Asiri", x["reps"][0]["pedidos"][0]["entradas"]["desde"] == "2026-10-24", x["reps"][0]["pedidos"])
    x = r["B6 el modelo pide lo MISMO dos veces"]; a = x["reps"][0]
    chequear("B6 devuelve el bloque cacheado, NO llama al sub-WF y NO suma lote", a["salida"]["bloque"] == BLOQUE and a["salida"]["repetido"] is True and not any(p["metodo"] == "executeWorkflow" for p in a["pedidos"]) and x["redis_final"][f"lotes:{TEL}"] == 2, (a["salida"], x["redis_final"]))
    chequear("B6 NO marca el bloque como de esta ejecución (si el paciente ya eligió, no se lo vuelve a forzar)", f"bloque_exec:{TEL}:ex-2" not in x["redis_final"], list(x["redis_final"]))
    x = r["B5 segundo bloque: se suma a lo ya ofrecido"]
    chequear("B5b un bloque con horarios nuevos SÍ cuenta (lotes 1 → 2) y trae siguiente_desde = día después del último ofrecido", x["redis_final"][f"lotes:{TEL}"] == 2 and x["reps"][0]["salida"].get("siguiente_desde") == "2026-10-28", (x["redis_final"].get(f"lotes:{TEL}"), x["reps"][0]["salida"].get("siguiente_desde")))
    x = r["B8 pide otra ventana y vuelve el MISMO bloque (sin horarios nuevos)"]; a = x["reps"][0]
    chequear("B8 sin horarios nuevos: NO cuenta como bloque (lotes sigue en 1), NO se marca para pegar y la nota dice nombrar lo más cercano de lo ya ofrecido",
             a["error"] is None and x["redis_final"][f"lotes:{TEL}"] == 1 and f"bloque_exec:{TEL}:ex-2" not in x["redis_final"] and a["salida"].get("sin_horarios_nuevos") is True
             and "bloque" not in {k for k in a["salida"] if k == "bloque"}, (a["error"], x["redis_final"].get(f"lotes:{TEL}"), a["salida"]))
    chequear("B8b (auditoría 21/10, real 320042) devuelve lo que la agenda dio AHORA en ese rango y ya se le había ofrecido (sigue libre): el texto lo nombra en vez de 'no hay'",
             a["salida"].get("ya_ofrecidos_en_rango") and {"fecha": "2026-10-22", "hora": "09:20"} in a["salida"]["ya_ofrecidos_en_rango"] and "ya_ofrecidos_en_rango" in a["salida"]["para_asiri"], a["salida"])
    a = r["B9 el bloque vino en un formato que no se puede leer"]["reps"][0]
    chequear("B9 un bloque que no se puede leer es error técnico (no 'no hay' ni 'nada nuevo') y no se guarda", a["salida"].get("motivo") == "error_tecnico" and f"bloque_exec:{TEL}:ex-2" not in r["B9 el bloque vino en un formato que no se puede leer"]["redis_final"], a["salida"])
    a = r["B7 pedido distinto con 2 bloques ya contados"]["reps"][0]
    chequear("B7 un pedido distinto sí cuenta: tercer bloque → límite", a["salida"]["motivo"] == "limite_de_bloques" and not any(p["metodo"] == "executeWorkflow" for p in a["pedidos"]), a["salida"])

    # ------------------------------------------------------------------ confirmar_una (21/10: la cadena de UNA cita, con la agenda simulada)
    ROW = {"id_cita_dentalink": 9104, "id_paciente_dentalink": 651, "nombre_paciente": "Dana", "fecha_turno": "2026-10-16", "hora_turno": "09:10:00"}
    ROW2 = {"id_cita_dentalink": 9300, "id_paciente_dentalink": 777, "nombre_paciente": "Martina", "fecha_turno": "2026-10-20", "hora_turno": "16:20:00"}
    CITA = {"data": {"id": 9104, "id_paciente": 651, "fecha": "2026-10-16", "hora_inicio": "09:10:00", "id_estado": 15, "estado_anulacion": 0}}
    PUT18 = {"data": {"id": 9104, "id_estado": 18}}
    CAND = {"cita_id": 9104, "paciente_id": 651, "fecha": "2026-10-16", "hora": "09:10", "nombre": "Dana", "origen": "recordatorio"}
    CAND_AG = {**CAND, "nombre": "", "origen": "agenda"}

    def una(id_, cand, modo="vivo", **kw):
        return esc(id_, {"cand_json": json.dumps(cand), "modo": modo}, **kw)

    r = correr(B.wf_confirmar_una(), [
        una("U10 SOMBRA: verifica pero no confirma ni marca el recordatorio (incidente 06/10)", CAND, "sombra", http={"GET cita": CITA, "PUT confirmar": PUT18}, pg={"Marcar recordatorio": {}}),
        una("U11 SIN modo: tampoco escribe (solo con 'vivo' explícito)", CAND, "", http={"GET cita": CITA, "PUT confirmar": PUT18}, pg={"Marcar recordatorio": {}}),
        una("U1 todo ok", CAND, http={"GET cita": CITA, "PUT confirmar": PUT18}, pg={"Marcar recordatorio": {}}),
        una("U2 ya estaba confirmada", CAND, http={"GET cita": {"data": {**CITA["data"], "id_estado": 18}}}, pg={"Marcar recordatorio": {}}),
        una("U3 Dentalink dice 'igual al original'", CAND, http={"GET cita": CITA, "PUT confirmar": {"error": {"message": "400 - el nuevo estado es igual al original"}}}, pg={"Marcar recordatorio": {}}),
        una("U4 el PUT falla", CAND, http={"GET cita": CITA, "PUT confirmar": {"error": {"message": "500"}}}, pg={"Marcar recordatorio": {}}),
        una("U7 turno visto (sin recordatorio)", CAND_AG, http={"GET cita": CITA, "PUT confirmar": PUT18}, pg={"Marcar recordatorio": {}}),
        una("U8 la cita cambió de fecha", CAND, http={"GET cita": {"data": {**CITA["data"], "fecha": "2026-10-19"}}}),
        una("U9 la cita está anulada", CAND, http={"GET cita": {"data": {**CITA["data"], "id_estado": 1, "estado_anulacion": 1}}}),
        una("U12 la agenda no responde", CAND, http={"GET cita": {"__throw": True}}),
        una("U13 la cita ahora es de otra ficha", CAND, http={"GET cita": {"data": {**CITA["data"], "id_paciente": 777}}}),
        esc("U14 sin turno (cand_json vacío)", {"cand_json": "", "modo": "vivo"}),
    ])
    print("\nconfirmar_una")
    met = lambda a: [p["metodo"] + " " + (p["url"] or "").replace(D, "") for p in a["pedidos"] if p["metodo"] in ("GET", "PUT", "POST")]
    for k in ("U10 SOMBRA: verifica pero no confirma ni marca el recordatorio (incidente 06/10)", "U11 SIN modo: tampoco escribe (solo con 'vivo' explícito)"):
        a = r[k]["reps"][0]
        chequear(k[:3] + " ningún PUT a Dentalink ni UPDATE del recordatorio; ok marcado simulado", met(a) == ["GET /citas/9104"] and not any(p["nodo"] == "Marcar recordatorio" for p in a["pedidos"]) and a["salida"].get("simulado") is True and a["salida"]["ok"] is True, (met(a), a["salida"]))
    a = r["U1 todo ok"]["reps"][0]
    chequear("U1 GET → PUT (id_estado 18) y marca el recordatorio; devuelve ok + escribio + la cita", a["error"] is None and met(a) == ["GET /citas/9104", "PUT /citas/9104"] and next(q for q in a["pedidos"] if q["nodo"] == "PUT confirmar")["body"] == {"id_estado": 18}
             and any(p["nodo"] == "Marcar recordatorio" for p in a["pedidos"]) and a["salida"]["ok"] is True and a["salida"]["escribio"] is True and a["salida"]["cand"]["cita_id"] == 9104, (a["error"], a["pedidos"], a["salida"]))
    a = r["U2 ya estaba confirmada"]["reps"][0]
    chequear("U2 ya confirmada: no hace PUT, ok + ya y cierra el recordatorio", met(a) == ["GET /citas/9104"] and a["salida"]["ok"] is True and a["salida"]["ya"] is True and any(p["nodo"] == "Marcar recordatorio" for p in a["pedidos"]), (met(a), a["salida"]))
    a = r["U3 Dentalink dice 'igual al original'"]["reps"][0]
    chequear("U3 el 400 'igual al original' cuenta como éxito idempotente", a["salida"]["ok"] is True and a["salida"]["ya"] is True, a["salida"])
    a = r["U4 el PUT falla"]["reps"][0]
    chequear("U4 PUT que falla: ok false (no_pude_confirmar), no marca el recordatorio, con instrucción de avisar", a["salida"]["ok"] is False and a["salida"]["motivo"] == "no_pude_confirmar" and not any(p["nodo"] == "Marcar recordatorio" for p in a["pedidos"]) and "avisar_grupo" in (a["salida"]["para_asiri"] or ""), a["salida"])
    a = r["U7 turno visto (sin recordatorio)"]["reps"][0]
    chequear("U7 turno visto: confirma y NO toca recordatorios", a["salida"]["ok"] is True and met(a) == ["GET /citas/9104", "PUT /citas/9104"] and not any(p["nodo"] == "Marcar recordatorio" for p in a["pedidos"]), (met(a), a["pedidos"]))
    for k, motivo in [("U8 la cita cambió de fecha", "cita_cambio"), ("U9 la cita está anulada", "cita_no_vigente"), ("U12 la agenda no responde", "error_tecnico"), ("U13 la cita ahora es de otra ficha", "cita_cambio")]:
        a = r[k]["reps"][0]
        chequear(f"{k[:3].strip()} → {motivo}, no escribe", a["salida"]["ok"] is False and a["salida"]["motivo"] == motivo and not any(q["metodo"] == "PUT" for q in a["pedidos"]) and not any(q["nodo"] == "Marcar recordatorio" for q in a["pedidos"]), (a["salida"], met(a)))
    a = r["U14 sin turno (cand_json vacío)"]["reps"][0]
    chequear("U14 sin turno: no consulta la agenda", a["salida"]["ok"] is False and not met(a), a["salida"])

    # ------------------------------------------------------------------ confirmar_turno (21/10: elige TODOS los que correspondan, confirmar_una por cada uno, un solo mensaje)
    PEDRO = {"id_cita_dentalink": 9116, "id_paciente_dentalink": 501, "nombre_paciente": "Pedro Gómez", "fecha_turno": "2026-10-23", "hora_turno": "09:50:00"}
    HILARIO = {"id_cita_dentalink": 9120, "id_paciente_dentalink": 502, "nombre_paciente": "Hilario Gómez", "fecha_turno": "2026-10-23", "hora_turno": "10:30:00"}

    def cand_de(row):
        return {"cita_id": row["id_cita_dentalink"], "fecha": row["fecha_turno"], "hora": row["hora_turno"][:5], "nombre": row["nombre_paciente"].split()[0], "origen": "recordatorio"}

    def r_ok(row, ya=False):
        return {"ok": True, "ya": ya, "escribio": True, "motivo": None, "para_asiri": None, "cand": cand_de(row)}

    def r_mal(row, motivo="no_pude_confirmar"):
        return {"ok": False, "ya": False, "escribio": False, "motivo": motivo, "para_asiri": "No pude confirmar el turno en la agenda: sigue como estaba. Decíselo y avisá a la clínica con avisar_grupo (ACCION).", "cand": cand_de(row)}

    r = correr(B.wf_confirmar_turno(), [
        esc("C1 un recordatorio abierto, todo ok", {"fecha": ""}, pg={"Recordatorios abiertos": [ROW]}, subwf={"Confirmar cada una": r_ok(ROW)}),
        esc("C2 ya estaba confirmada", {"fecha": ""}, pg={"Recordatorios abiertos": [ROW]}, subwf={"Confirmar cada una": r_ok(ROW, ya=True)}),
        esc("C4 confirmar_una falla", {"fecha": ""}, pg={"Recordatorios abiertos": [ROW]}, subwf={"Confirmar cada una": r_mal(ROW)}),
        esc("C5 dos recordatorios sin decir cuál (fechas distintas): confirma los dos", {"fecha": ""}, pg={"Recordatorios abiertos": [ROW, ROW2]}, subwf={"Confirmar cada una": [r_ok(ROW), r_ok(ROW2)]}),
        esc("C5b dos recordatorios, pide el de Martina por fecha", {"fecha": "2026-10-20"}, pg={"Recordatorios abiertos": [ROW, ROW2]}, subwf={"Confirmar cada una": r_ok(ROW2)}),
        esc("C6 sin recordatorio ni fecha", {"fecha": ""}, pg={"Recordatorios abiertos": [{}]}, subwf={"Confirmar cada una": r_ok(ROW)}),
        esc("C7 sin recordatorio pero con fecha y turno visto", {"fecha": "2026-10-16"}, {f"turnos_vistos:{TEL}": TURNOS}, pg={"Recordatorios abiertos": [{}]}, subwf={"Confirmar cada una": r_ok(ROW)}),
        esc("C9 'confirmo' y el modelo pasa una fecha equivocada (10/12 leído como 12/10): con UN recordatorio abierto, confirma ese", {"fecha": "2026-10-12"}, pg={"Recordatorios abiertos": [ROW]}, subwf={"Confirmar cada una": r_ok(ROW)}),
        esc("C12 INCIDENTE 21/10: dos hermanos el MISMO día, 'Confirmo'", {"fecha": ""}, pg={"Recordatorios abiertos": [PEDRO, HILARIO]}, subwf={"Confirmar cada una": [r_ok(PEDRO), r_ok(HILARIO)]}),
        esc("C12b mismo día, el modelo pasa solo la fecha ('Pedro 9:50 e Hilario 10:30')", {"fecha": "2026-10-23"}, pg={"Recordatorios abiertos": [PEDRO, HILARIO]}, subwf={"Confirmar cada una": [r_ok(PEDRO), r_ok(HILARIO)]}),
        esc("C12c mismo día, confirma solo el de las 10:30", {"fecha": "2026-10-23", "hora": "10:30"}, pg={"Recordatorios abiertos": [PEDRO, HILARIO]}, subwf={"Confirmar cada una": r_ok(HILARIO)}),
        esc("C12d mismo día, confirma solo el de Pedro (por nombre, sin tilde ni mayúscula)", {"fecha": "", "nombre": "pedro"}, pg={"Recordatorios abiertos": [PEDRO, HILARIO]}, subwf={"Confirmar cada una": r_ok(PEDRO)}),
        esc("C12e hora que no coincide con ninguno: no achica (confirma los dos)", {"fecha": "2026-10-23", "hora": "11:00"}, pg={"Recordatorios abiertos": [PEDRO, HILARIO]}, subwf={"Confirmar cada una": [r_ok(PEDRO), r_ok(HILARIO)]}),
        esc("C13 dos turnos, uno se confirma y el otro falla", {"fecha": ""}, pg={"Recordatorios abiertos": [PEDRO, HILARIO]}, subwf={"Confirmar cada una": [r_ok(PEDRO), r_mal(HILARIO)]}),
        esc("C14 el sub-workflow se cae en uno ({error})", {"fecha": ""}, pg={"Recordatorios abiertos": [PEDRO, HILARIO]}, subwf={"Confirmar cada una": [r_ok(PEDRO), {"error": "timeout"}]}),
        esc("C15 SOMBRA con dos turnos: no avisa al grupo aunque uno falle", {"fecha": "", "modo": "sombra"}, pg={"Recordatorios abiertos": [PEDRO, HILARIO]}, subwf={"Confirmar cada una": [{**r_ok(PEDRO), "simulado": True}, r_mal(HILARIO)]}),
        esc("C16 dos recordatorios y la clínica ya anuló uno", {"fecha": ""}, pg={"Recordatorios abiertos": [PEDRO, HILARIO]}, subwf={"Confirmar cada una": [r_ok(PEDRO), r_mal(HILARIO, "cita_no_vigente")]}),
    ])
    print("\nconfirmar_turno")
    llamados_ = lambda a: [q["entradas"] for q in a["pedidos"] if q["nodo"] == "Confirmar cada una"]
    cids = lambda a: [json.loads(e["cand_json"])["cita_id"] for e in llamados_(a)]
    x = r["C1 un recordatorio abierto, todo ok"]; a = x["reps"][0]
    chequear("C1 un llamado a confirmar_una con la cita del recordatorio y el modo/tel del pedido", cids(a) == [9104] and llamados_(a)[0]["modo"] == "vivo" and llamados_(a)[0]["tel"] == TEL, llamados_(a))
    chequear("C1 el mensaje lo arma el código", a["salida"]["readback_text"] == "Perfecto, su turno del viernes 16/10 a las 09:10 está confirmado." and a["salida"]["ok"] is True, a["salida"])
    lib = json.loads(x["redis_final"][f"escrituras:{TEL}:ex-2"])
    chequear("C1 deja el libro (tipo confirmacion, ok)", lib[0]["tipo"] == "confirmacion" and lib[0]["ok"] is True and lib[0]["readback_text"] == a["salida"]["readback_text"], lib)
    x = r["C2 ya estaba confirmada"]; a = x["reps"][0]
    lib2 = json.loads(x["redis_final"].get(f"escrituras:{TEL}:{TRIG['exec_id_actual']}") or "null")
    chequear("C2 ya confirmada: mismo texto que si se confirmara recién, ya_estaba_confirmada y queda en el libro (para el chequeo de salida)",
             a["salida"]["ya_estaba_confirmada"] is True and a["salida"]["readback_text"] == "Perfecto, su turno del viernes 16/10 a las 09:10 está confirmado." and isinstance(lib2, list) and lib2[0]["ok"] is True and len(lib2) == 1, (a["salida"], lib2))
    x = r["C4 confirmar_una falla"]; a = x["reps"][0]
    chequear("C4 si no se pudo confirmar: ok false, motivo de la cita y la instrucción de avisar; sin libro", a["salida"]["ok"] is False and a["salida"]["motivo"] == "no_pude_confirmar" and "avisar_grupo" in a["salida"]["para_asiri"] and f"escrituras:{TEL}:ex-2" not in x["redis_final"], a["salida"])
    a = r["C5 dos recordatorios sin decir cuál (fechas distintas): confirma los dos"]["reps"][0]
    chequear("C5 'Confirmo' con dos recordatorios: confirma LOS DOS (como el v6) y un solo mensaje con los dos nombres",
             cids(a) == [9104, 9300] and a["salida"]["ok"] is True and a["salida"]["readback_text"] == "Perfecto, quedaron confirmados sus turnos del viernes 16/10 a las 09:10 (Dana) y martes 20/10 a las 16:20 (Martina)." and a["salida"]["confirmados"] == 2, (cids(a), a["salida"]))
    a = r["C5b dos recordatorios, pide el de Martina por fecha"]["reps"][0]
    chequear("C5b con fecha confirma SOLO esa cita (9300)", cids(a) == [9300] and a["salida"]["ok"] is True, (cids(a), a["salida"]))
    a = r["C6 sin recordatorio ni fecha"]["reps"][0]
    chequear("C6 sin recordatorio: le dice a Asiri que mire ver_turnos, sin llamar a confirmar_una", a["salida"]["motivo"] == "sin_recordatorio" and not cids(a), a["salida"])
    a = r["C7 sin recordatorio pero con fecha y turno visto"]["reps"][0]
    chequear("C7 turno visto por fecha: confirmar_una con origen agenda (no toca recordatorios)", cids(a) == [9104] and json.loads(llamados_(a)[0]["cand_json"])["origen"] == "agenda", llamados_(a))
    a = r["C9 'confirmo' y el modelo pasa una fecha equivocada (10/12 leído como 12/10): con UN recordatorio abierto, confirma ese"]["reps"][0]
    chequear("C9 fecha equivocada + un solo recordatorio → confirma ese (07/10, escenarios reales REAL-14/15)", cids(a) == [9104] and a["salida"]["ok"] is True, (cids(a), a["salida"]))
    a = r["C12 INCIDENTE 21/10: dos hermanos el MISMO día, 'Confirmo'"]["reps"][0]
    chequear("C12 INCIDENTE: 'Confirmo' con dos turnos el MISMO día → confirma los dos, sin preguntar, un mensaje con los nombres",
             cids(a) == [9116, 9120] and a["salida"]["ok"] is True and a["salida"]["readback_text"] == "Perfecto, quedaron confirmados sus turnos del viernes 23/10 a las 09:50 (Pedro) y viernes 23/10 a las 10:30 (Hilario)." and a["salida"]["motivo"] is None, (cids(a), a["salida"]))
    a = r["C12b mismo día, el modelo pasa solo la fecha ('Pedro 9:50 e Hilario 10:30')"]["reps"][0]
    chequear("C12b con solo la fecha de un día con dos turnos: confirma los dos (antes: 'varios_recordatorios' en bucle)", cids(a) == [9116, 9120] and a["salida"]["ok"] is True, (cids(a), a["salida"]))
    a = r["C12c mismo día, confirma solo el de las 10:30"]["reps"][0]
    chequear("C12c fecha + hora: SOLO esa cita", cids(a) == [9120] and a["salida"]["readback_text"] == "Perfecto, su turno del viernes 23/10 a las 10:30 está confirmado.", (cids(a), a["salida"]))
    a = r["C12d mismo día, confirma solo el de Pedro (por nombre, sin tilde ni mayúscula)"]["reps"][0]
    chequear("C12d por nombre: SOLO la de Pedro", cids(a) == [9116], cids(a))
    a = r["C12e hora que no coincide con ninguno: no achica (confirma los dos)"]["reps"][0]
    chequear("C12e un dato que no coincide con nada no deja al paciente sin confirmar", cids(a) == [9116, 9120], cids(a))
    x = r["C13 dos turnos, uno se confirma y el otro falla"]; a = x["reps"][0]
    chequear("C13 a medias: confirma el que pudo, dice con sinceridad cuál no y avisa a la clínica [ACCIÓN]",
             a["salida"]["ok"] is True and a["salida"]["readback_text"].startswith("Perfecto, su turno del viernes 23/10 a las 09:50 está confirmado.") and "No pude confirmar el del viernes 23/10 a las 10:30 (Hilario): la secretaria lo revisa." in a["salida"]["readback_text"]
             and any("[ACCIÓN] Confirmación a medias" in str((v.get("qs") or {}).get("resumen", "")) for v in a["avisos"]), (a["salida"], a["avisos"]))
    lib3 = json.loads(x["redis_final"][f"escrituras:{TEL}:ex-2"])
    chequear("C13b el libro queda ok y marcado parcial", lib3[0]["ok"] is True and lib3[0]["parcial"] is True, lib3)
    a = r["C14 el sub-workflow se cae en uno ({error})"]["reps"][0]
    chequear("C14 un sub-workflow caído cuenta como falla de ESE turno (no rompe el otro)", a["salida"]["ok"] is True and "No pude confirmar el del viernes 23/10 a las 10:30" in a["salida"]["readback_text"], a["salida"])
    a = r["C15 SOMBRA con dos turnos: no avisa al grupo aunque uno falle"]["reps"][0]
    chequear("C15 sombra: ningún aviso al grupo y la salida marcada simulado", not a["avisos"] and a["salida"].get("simulado") is True, (a["avisos"], a["salida"]))
    a = r["C16 dos recordatorios y la clínica ya anuló uno"]["reps"][0]
    chequear("C16 (auditoría 21/10) recordatorio de un turno anulado: al paciente solo el confirmado (sin 'no pude'), la clínica recibe un FYI y no queda parcial",
             a["salida"]["readback_text"] == "Perfecto, su turno del viernes 23/10 a las 09:50 está confirmado." and any("[FYI]" in str((v.get("qs") or {}).get("resumen", "")) for v in a["avisos"])
             and not any("[ACCIÓN]" in str((v.get("qs") or {}).get("resumen", "")) for v in a["avisos"]), (a["salida"], a["avisos"]))

    # ------------------------------------------------------------------ clinica (08/10: derivar / humano / pago / datos_pago / espera / triaje; textos fijos por código)
    ESTADO = {f"{k}:{TEL}": "x" for k in ("propuesta", "ofertas", "lotes", "turnos_vistos", "bloque")}
    base_c = {"modo": "vivo", "nivel": "", "texto": "", "motivo": "", "cita_textual": "", "texto_paciente": "", "moneda": ""}
    r = correr(B.wf_clinica(), [
        esc("K1 avisar_grupo FYI", {**base_c, "accion": "aviso", "nivel": "FYI", "texto": "Preguntó por un presupuesto de alineadores"}, dict(ESTADO)),
        esc("K2 pasar_a_humano verificado", {**base_c, "accion": "humano", "cita_textual": "quiero hablar con la secretaria", "texto_paciente": "Hola, quiero hablar con la secretaria"}, dict(ESTADO)),
        esc("K3 pasar_a_humano inventado", {**base_c, "accion": "humano", "cita_textual": "quiero hablar con la secretaria", "texto_paciente": "Confirmo mi turno"}, dict(ESTADO)),
        esc("K4 primer comprobante", {**base_c, "accion": "pago"}, dict(ESTADO)),
        esc("K4b segundo comprobante en 15 min", {**base_c, "accion": "pago"}, {**ESTADO, f"pago:{TEL}": "1"}),
        esc("K5 sombra: pasar_a_humano", {**base_c, "modo": "sombra", "accion": "humano", "cita_textual": "quiero hablar con la secretaria", "texto_paciente": "quiero hablar con la secretaria"}, dict(ESTADO)),
        esc("K6 el webhook del grupo está caído", {**base_c, "accion": "humano", "cita_textual": "quiero hablar con la secretaria", "texto_paciente": "quiero hablar con la secretaria"}, dict(ESTADO), aviso_falla=True),
        esc("K7 lista de espera", {**base_c, "accion": "espera", "texto": "Quiere antes del 22/10"}, dict(ESTADO)),
        esc("K8 derivar_triaje", {**base_c, "accion": "triaje", "texto_paciente": "se me salió el alambre"}, dict(ESTADO)),
        esc("K10 avisar_grupo en SOMBRA", {**base_c, "accion": "aviso", "nivel": "FYI", "texto": "El paciente consulta por su presupuesto", "modo": "sombra"}, dict(ESTADO)),
        esc("K12 derivar 1.ª vez", {**base_c, "accion": "derivar", "cita_textual": "presupuesto en dólares?", "motivo": "presupuesto en dólares", "texto_paciente": "presupuesto en dólares?"}, dict(ESTADO)),
        esc("K13 derivar: insiste (2.ª en 30 min)", {**base_c, "accion": "derivar", "cita_textual": "y en dólares?", "texto_paciente": "y en dólares?"}, {**ESTADO, f"deriva:{TEL}": "1"}),
        esc("K14 derivar en SOMBRA con insistencia", {**base_c, "modo": "sombra", "accion": "derivar", "cita_textual": "y en dólares?", "texto_paciente": "y en dólares?"}, {**ESTADO, f"v7s:deriva:{TEL}": "1"}),
        esc("K15 un aviso técnico previo NO cuenta como insistencia", {**base_c, "accion": "derivar", "cita_textual": "x", "texto_paciente": "presupuesto"}, {**ESTADO, f"avisos:{TEL}": "1"}),
        esc("K16 datos_pago en dólares", {**base_c, "accion": "datos_pago", "moneda": "otra"}, dict(ESTADO)),
        esc("K17 datos_pago en pesos", {**base_c, "accion": "datos_pago", "moneda": "pesos"}, dict(ESTADO)),
        esc("K18 sin modo (campo que no llega) = sombra", {**base_c, "modo": "", "accion": "derivar", "cita_textual": "x", "texto_paciente": "x"}, {**ESTADO, f"v7s:deriva:{TEL}": "1"}),
    ])
    print("\nclinica")
    x = r["K1 avisar_grupo FYI"]; a = x["reps"][0]
    chequear("K1 avisa al grupo con [FYI], SIN pedir silencio, y deja el estado intacto", len(a["avisos"]) == 1 and a["avisos"][0]["qs"]["resumen"].startswith("[FYI]") and "tomar" not in a["avisos"][0]["qs"] and a["avisos"][0]["qs"]["phone"] == TEL and all(k in x["redis_final"] for k in ESTADO), (a["avisos"], list(x["redis_final"])))
    chequear("K1b cuenta el aviso para el límite de 2 cada 30 min (avisos:{tel} = 1)", str(x["redis_final"].get(f"avisos:{TEL}")) == "1", x["redis_final"].get(f"avisos:{TEL}"))
    x = r["K10 avisar_grupo en SOMBRA"]; a = x["reps"][0]
    chequear("K10 en sombra no avisa a nadie pero cuenta el aviso en la clave de sombra (v7s:avisos:), no en la de vivo", a["avisos"] == [] and str(x["redis_final"].get(f"v7s:avisos:{TEL}")) == "1" and f"avisos:{TEL}" not in x["redis_final"], (a["avisos"], {k: v for k, v in x["redis_final"].items() if "avisos" in k}))
    x = r["K12 derivar 1.ª vez"]; a = x["reps"][0]
    chequear("K12 derivar: texto fijo, aviso [ACCIÓN] con la frase textual, sin silenciar, y cuenta deriva:{tel} = 1", a["salida"].get("texto_para_el_paciente") == "Le paso con la secretaria para que lo atienda." and len(a["avisos"]) == 1 and a["avisos"][0]["qs"]["resumen"].startswith("[ACCIÓN]") and "«presupuesto en dólares?»" in a["avisos"][0]["qs"]["resumen"] and "tomar" not in a["avisos"][0]["qs"] and str(x["redis_final"].get(f"deriva:{TEL}")) == "1" and all(k in x["redis_final"] for k in ESTADO), (a["salida"], a["avisos"], x["redis_final"].get(f"deriva:{TEL}")))
    x = r["K13 derivar: insiste (2.ª en 30 min)"]; a = x["reps"][0]
    chequear("K13 (Lucas: 'si insiste, modo humano') 2.ª derivación en 30 min: aviso con tomar=true, se limpia el estado y texto de insistencia", a["salida"].get("modo_humano") is True and len(a["avisos"]) == 1 and a["avisos"][0]["qs"].get("tomar") == "true" and not any(k in x["redis_final"] for k in ESTADO) and a["salida"].get("texto_para_el_paciente", "").startswith("Ya le pasé su consulta"), (a["salida"], a["avisos"]))
    x = r["K14 derivar en SOMBRA con insistencia"]; a = x["reps"][0]
    chequear("K14 sombra: modo humano simulado, sin avisar ni silenciar el chat real (no llama al webhook), sin tocar el estado; el contador va a v7s:deriva:", a["salida"].get("modo_humano") is True and a["salida"].get("simulado") is True and a["avisos"] == [] and all(k in x["redis_final"] for k in ESTADO) and str(x["redis_final"].get(f"v7s:deriva:{TEL}")) == "2" and f"deriva:{TEL}" not in x["redis_final"], (a["salida"], a["avisos"], x["redis_final"]))
    a = r["K15 un aviso técnico previo NO cuenta como insistencia"]["reps"][0]
    chequear("K15 contadores separados: un aviso técnico (avisos:) no convierte la 1.ª derivación en modo humano", a["salida"].get("modo_humano") is None and a["salida"].get("derivado") is True, a["salida"])
    a = r["K18 sin modo (campo que no llega) = sombra"]["reps"][0]
    chequear("K18 (decisión 08/10) sin modo es sombra: ni avisos ni silencio aunque insista", a["avisos"] == [] and a["salida"].get("simulado") is True, (a["salida"], a["avisos"]))
    x = r["K2 pasar_a_humano verificado"]; a = x["reps"][0]
    chequear("K2 pasa a una persona: aviso con tomar=true y texto fijo", len(a["avisos"]) == 1 and a["avisos"][0]["qs"].get("tomar") == "true" and "pidió hablar con una persona" in a["avisos"][0]["qs"]["resumen"] and a["salida"].get("texto_para_el_paciente") == "Le paso con la secretaria para que lo atienda.", (a["avisos"], a["salida"]))
    chequear("K2 borra propuesta, ofertas, lotes, turnos_vistos y bloque (una persona toma el chat: nada viejo se puede ejecutar)", not any(k in x["redis_final"] for k in ESTADO), list(x["redis_final"]))
    x = r["K3 pasar_a_humano inventado"]; a = x["reps"][0]
    chequear("K3 la cita no está en el mensaje: NO silencia, NO borra estado, deriva con aviso ACCIÓN", len(a["avisos"]) == 1 and "tomar" not in a["avisos"][0]["qs"] and a["avisos"][0]["qs"]["resumen"].startswith("[ACCIÓN]") and all(k in x["redis_final"] for k in ESTADO) and a["salida"]["degradado"] is True, (a["avisos"], a["salida"]))
    x = r["K4 primer comprobante"]; a = x["reps"][0]
    chequear("K4 comprobante: aviso ACCIÓN sin silenciar, marca para no repetir y texto fijo de recepción", a["avisos"][0]["qs"]["resumen"].startswith("[ACCIÓN]") and "tomar" not in a["avisos"][0]["qs"] and x["redis_final"][f"pago:{TEL}"] == "1" and a["salida"].get("texto_para_el_paciente", "").startswith("Recibido."), (a["avisos"], x["redis_final"], a["salida"]))
    a = r["K4b segundo comprobante en 15 min"]["reps"][0]
    chequear("K4b segundo comprobante: no repite el aviso", not a["avisos"] and a["salida"]["ok"] is True and a["salida"].get("texto_para_el_paciente") == "Recibido, gracias.", a)
    x = r["K5 sombra: pasar_a_humano"]; a = x["reps"][0]
    chequear("K5 sombra: ni avisos ni borrado de estado", not a["avisos"] and all(k in x["redis_final"] for k in ESTADO) and a["salida"]["simulado"] is True, (a["avisos"], a["salida"]))
    a = r["K6 el webhook del grupo está caído"]["reps"][0]
    chequear("K6 si el aviso no sale, se marca (el cerebro avisa por su lado)", a["salida"].get("aviso_no_enviado") is True, a["salida"])
    a = r["K7 lista de espera"]["reps"][0]
    chequear("K7 lista de espera: aviso FYI y texto fijo que no promete", a["avisos"][0]["qs"]["resumen"].startswith("[FYI] Lista de espera") and a["salida"].get("texto_para_el_paciente", "").startswith("Le dejo anotado"), (a["avisos"], a["salida"]))
    a = r["K16 datos_pago en dólares"]["reps"][0]
    chequear("K16 datos_pago con moneda=otra: fuera de alcance, sin datos ni aviso", a["salida"].get("fuera_de_alcance") is True and a["salida"]["ok"] is False and not a["avisos"], a["salida"])
    a = r["K17 datos_pago en pesos"]["reps"][0]
    chequear("K17 datos_pago en pesos: ok, marca datos_pago y el texto fijo (los datos los pega el cerebro)", a["salida"].get("datos_pago") is True and a["salida"].get("texto_para_el_paciente") == "Le paso los datos para transferir:" and not a["avisos"], a["salida"])
    x = r["K8 derivar_triaje"]; a = x["reps"][0]; clave = f"triaje_v7:{TEL}:{TRIG['exec_id_actual']}"
    marca = json.loads(x["redis_final"].get(clave) or "null")
    chequear("K8 derivar_triaje deja la marca triaje_v7 de ESTA ejecución con el mensaje completo, sin aviso al grupo, sin silenciar y sin borrar estado",
             marca and marca["cita"] == "se me salió el alambre" and not a["avisos"] and all(c in x["redis_final"] for c in ESTADO) and a["salida"]["derivado_a_triaje"] is True, (x["redis_final"], a["avisos"], a["salida"]))
    x = r["K1 avisar_grupo FYI"]
    chequear("K9 las demás acciones NO dejan marca de triaje", not any(c.startswith("triaje_v7:") for c in x["redis_final"]), list(x["redis_final"]))

    # ------------------------------------------------------------------ gestionar_turno (herramienta única de agenda, 06/10)
    base = {f"ficha:{TEL}": FICHA_1, f"turnos_vistos:{TEL}": TURNOS, f"ofertas:{TEL}": OFERTAS}
    RB = "Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?"
    PEDIDO = {"modo": "sombra", "tipo": "cambio", "fecha": "2026-10-22", "hora": "9:20", "fecha_turno_viejo": "2026-10-16"}
    EJEC = {"ok": True, "simulado": True, "readback_text": "Listo, quedó reprogramado su turno: anulé el del viernes 16/10 a las 09:10 y le reservé el jueves 22/10 a las 09:20."}
    NUEVO_SIN_DATOS = {"modo": "sombra", "tipo": "reserva", "fecha": "2026-10-22", "hora": "9:20"}
    RB_SUMA = "Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, además de su turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?"
    GUARDADA = {"id": f"{TEL}-1", "tipo": "sumar", "estado": "pendiente", "creada_ms": int(__import__("datetime").datetime(2026, 10, 5, 12, 30, tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000),
                "exec_id": "ex-1", "tel": TEL, "paciente_id": 651, "slot": {"fecha": "2026-10-22", "hora": "09:20"}, "cita_vieja": None, "readback_text": RB_SUMA, "enviada": True}
    NUEVO = {**NUEVO_SIN_DATOS, "nuevo_nombre": "Juan", "nuevo_apellido": "Pérez", "nuevo_dni": "40.123.456"}
    RBN = "Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, a nombre de Juan Pérez (DNI 40.123.456), como paciente nuevo. ¿Procedo con la reserva?"
    # (08/10) El "sí" ejecuta la confirmación GUARDADA que vio el paciente, cuando el agente de Turnos pone confirma=true (ya no hay regex de "sí").
    GUARDADA_C = {**GUARDADA, "tipo": "cambio", "cita_vieja": {"id": 9104, "fecha": "2026-10-16", "hora": "09:10"}, "readback_text": RB}
    GUARDADA_N = {**GUARDADA, "tipo": "reserva", "paciente_id": None, "readback_text": RBN, "paciente_nuevo": {"nombre": "Juan", "apellidos": "Pérez", "dni": "40123456"}}
    r = correr(B.wf_gestionar_turno(), [
        esc("GT1 primera llamada", {**PEDIDO, "ultimo_asiri": "Tenemos los próximos turnos disponibles…", "texto_paciente": "el jueves 22 a las 9:20"}, base),
        esc("GT2 el paciente vio el read-back y Turnos puso confirma", {**PEDIDO, "confirma": "true", "ultimo_asiri": RB, "texto_paciente": "ya"}, {**base, f"propuesta:{TEL}": json.dumps(GUARDADA_C)}, subwf={"Ejecutar": EJEC}),
        esc("GT3 sin confirma no ejecuta (aunque diga 'Sí')", {**PEDIDO, "ultimo_asiri": RB, "texto_paciente": "Sí, pero mejor el viernes"}, {**base, f"propuesta:{TEL}": json.dumps(GUARDADA_C)}, subwf={"Ejecutar": EJEC}),
        esc("GT4 horario no ofrecido", {**PEDIDO, "hora": "10:00", "ultimo_asiri": RB, "texto_paciente": "Sí"}, base, subwf={"Ejecutar": EJEC}),
        esc("GT8 'Sí' y el modelo cambia el pedido en la 2.ª llamada (sumar → reserva)", {**PEDIDO, "tipo": "reserva", "fecha_turno_viejo": "", "confirma": "true", "ultimo_asiri": RB_SUMA, "texto_paciente": "Sí."},
            {**base, f"propuesta:{TEL}": json.dumps(GUARDADA)}, subwf={"Ejecutar": EJEC}),
        esc("GT5 paciente nuevo sin datos", {**NUEVO_SIN_DATOS, "ultimo_asiri": "…", "texto_paciente": "el jueves 22 a las 9:20"}, {f"ofertas:{TEL}": OFERTAS}),
        esc("GT6 paciente nuevo con datos", {**NUEVO, "ultimo_asiri": "…", "texto_paciente": "Juan Pérez 40123456"}, {f"ofertas:{TEL}": OFERTAS}),
        esc("GT7 paciente nuevo: vio el read-back y Turnos puso confirma", {**NUEVO, "confirma": "true", "ultimo_asiri": RBN, "texto_paciente": "Sí"}, {f"ofertas:{TEL}": OFERTAS, f"propuesta:{TEL}": json.dumps(GUARDADA_N)}, subwf={"Ejecutar": EJEC}),
        esc("GT9 DNI que el paciente no escribió", {**NUEVO, "nuevo_dni": "41123456", "ultimo_asiri": "…", "texto_paciente": "Juan Pérez 40.123.456", "textos_paciente": json.dumps(["quiero turno", "Juan Pérez 40.123.456"])}, {f"ofertas:{TEL}": OFERTAS}),
        esc("GT10 DNI con espacios en el mensaje", {**NUEVO, "ultimo_asiri": "…", "texto_paciente": "40 123 456", "textos_paciente": json.dumps(["Juan Pérez", "40 123 456"])}, {f"ofertas:{TEL}": OFERTAS}),
    ])
    print("\ngestionar_turno")
    x = r["GT1 primera llamada"]; a = x["reps"][0]; prop = json.loads(x["redis_final"][f"propuesta:{TEL}"])
    chequear("GT1 primera llamada: devuelve el read-back del código, guarda la propuesta con la ejecución actual y NO llama a la ejecución",
             a["salida"]["etapa"] == "confirmacion" and a["salida"]["texto_para_el_paciente"] == RB and prop["exec_id"] == "ex-2" and not any(p["nodo"] == "Ejecutar" for p in a["pedidos"]), a["salida"])
    x = r["GT2 el paciente vio el read-back y Turnos puso confirma"]; a = x["reps"][0]; prop = json.loads(x["redis_final"][f"propuesta:{TEL}"])
    ej = next((p for p in a["pedidos"] if p["nodo"] == "Ejecutar"), None)
    chequear("GT2 vio el read-back y Turnos puso confirma: guarda la propuesta CONFIRMADA (id estable) y corre la ejecución con el teléfono, la ejecución y el modo del código",
             prop["enviada"] is True and prop["exec_id"] == "confirmada" and prop["id"].startswith("h-" + TEL) and ej is not None and ej["entradas"] == {"tel": TEL, "exec_id_actual": "ex-2", "modo": "sombra"}, (prop, ej))
    chequear("GT2 devuelve el resultado de la ejecución con etapa 'ejecutado' primero (el examen y el chequeo lo leen)", list(a["salida"])[0] == "etapa" and a["salida"]["etapa"] == "ejecutado" and a["salida"]["ok"] is True, a["salida"])
    chequear("GT2b el mensaje final va como texto_para_el_paciente (no readback_text) con la instrucción de mandarlo solo (examen AGE-01, 07/10)",
             a["salida"].get("texto_para_el_paciente") == EJEC["readback_text"] and "readback_text" not in a["salida"] and "tal cual y sola" in (a["salida"].get("para_asiri") or ""), a["salida"])
    a = r["GT3 sin confirma no ejecuta (aunque diga 'Sí')"]["reps"][0]
    chequear("GT3 sin confirma NO ejecuta (el código no lee el 'sí'): vuelve a mostrar la confirmación", a["salida"]["etapa"] == "confirmacion" and not any(p["nodo"] == "Ejecutar" for p in a["pedidos"]), a["salida"])
    x = r["GT4 horario no ofrecido"]; a = x["reps"][0]
    chequear("GT4 horario no ofrecido: error del código, ni propuesta guardada ni ejecución", a["salida"]["etapa"] == "error" and a["salida"]["motivo"] == "no_ofrecido" and f"propuesta:{TEL}" not in x["redis_final"] and not any(p["nodo"] == "Ejecutar" for p in a["pedidos"]), a["salida"])
    x = r["GT8 'Sí' y el modelo cambia el pedido en la 2.ª llamada (sumar → reserva)"]; a = x["reps"][0]; prop = json.loads(x["redis_final"][f"propuesta:{TEL}"])
    chequear("GT8 ejecuta la confirmación GUARDADA (sumar, la que vio el paciente) aunque el modelo mandó 'reserva' (caso de la captura de Lucas, 07/10)",
             a["error"] is None and any(p["nodo"] == "Ejecutar" for p in a["pedidos"]) and prop["tipo"] == "sumar" and prop["exec_id"] == "confirmada" and a["salida"]["etapa"] == "ejecutado", (a["error"], prop, a["salida"]))
    a = r["GT5 paciente nuevo sin datos"]["reps"][0]
    chequear("GT5 celular sin ficha y sin datos: pide nombre, apellido y DNI (no deriva)", a["error"] is None and a["salida"]["motivo"] == "sin_ficha" and "nombre, apellido y DNI" in a["salida"]["para_asiri"], (a["error"], a["salida"]))
    x = r["GT6 paciente nuevo con datos"]; a = x["reps"][0]
    chequear("GT6 con los datos: read-back de paciente nuevo y propuesta guardada con el alta", a["salida"].get("texto_para_el_paciente") == RBN and json.loads(x["redis_final"][f"propuesta:{TEL}"])["paciente_nuevo"]["dni"] == "40123456", a["salida"])
    x = r["GT7 paciente nuevo: vio el read-back y Turnos puso confirma"]; a = x["reps"][0]; prop = json.loads(x["redis_final"][f"propuesta:{TEL}"])
    chequear("GT7 confirma al read-back de paciente nuevo: corre la ejecución con la propuesta confirmada (sin ficha, con los datos del alta)", any(p["nodo"] == "Ejecutar" for p in a["pedidos"]) and prop["exec_id"] == "confirmada" and prop["paciente_id"] is None and prop["paciente_nuevo"]["apellidos"] == "Pérez", (prop, a["salida"]))
    a = r["GT9 DNI que el paciente no escribió"]["reps"][0]
    chequear("GT9 (I3) el DNI que copió el modelo no está en lo que escribió el paciente: no hay read-back, se pide el DNI (texto fijo)", a["salida"].get("motivo") == "dni_no_escrito" and a["salida"].get("texto_para_el_paciente") == "Para registrarlo me falta el DNI del paciente.", a["salida"])
    a = r["GT10 DNI con espacios en el mensaje"]["reps"][0]
    chequear("GT10 (I3) '40 123 456' en el mensaje y '40.123.456' en la copia del modelo: vale (solo dígitos de los dos lados)", a["salida"].get("texto_para_el_paciente") == RBN, a["salida"])

    print(f"\n{total - fallas}/{total} {'TODO OK' if not fallas else str(fallas) + ' FALLAS'}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
