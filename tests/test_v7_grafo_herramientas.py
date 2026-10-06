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
TRIG = {"tel": TEL, "exec_id_actual": "ex-2"}
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
        esc("P4 dos fichas sin elegir", CAMBIO, {**base, f"ficha:{TEL}": FICHA_2}),
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
    a = r["B7 pedido distinto con 2 bloques ya contados"]["reps"][0]
    chequear("B7 un pedido distinto sí cuenta: tercer bloque → límite", a["salida"]["motivo"] == "limite_de_bloques" and not any(p["metodo"] == "executeWorkflow" for p in a["pedidos"]), a["salida"])

    # ------------------------------------------------------------------ confirmar_turno
    ROW = {"id_cita_dentalink": 9104, "id_paciente_dentalink": 651, "nombre_paciente": "Dana", "fecha_turno": "2026-10-16", "hora_turno": "09:10:00"}
    ROW2 = {"id_cita_dentalink": 9300, "id_paciente_dentalink": 777, "nombre_paciente": "Martina", "fecha_turno": "2026-10-20", "hora_turno": "16:20:00"}
    CITA = {"data": {"id": 9104, "id_paciente": 651, "fecha": "2026-10-16", "hora_inicio": "09:10:00", "id_estado": 15, "estado_anulacion": 0}}
    PUT18 = {"data": {"id": 9104, "id_estado": 18}}
    r = correr(B.wf_confirmar_turno(), [
        esc("C1 un recordatorio abierto, todo ok", {"fecha": ""}, http={"GET cita": CITA, "PUT confirmar": PUT18}, pg={"Recordatorios abiertos": [ROW], "Marcar recordatorio": {}}),
        esc("C2 ya estaba confirmada", {"fecha": ""}, http={"GET cita": {"data": {**CITA["data"], "id_estado": 18}}}, pg={"Recordatorios abiertos": [ROW], "Marcar recordatorio": {}}),
        esc("C3 Dentalink dice 'igual al original'", {"fecha": ""}, http={"GET cita": CITA, "PUT confirmar": {"error": {"message": "400 - el nuevo estado es igual al original"}}}, pg={"Recordatorios abiertos": [ROW], "Marcar recordatorio": {}}),
        esc("C4 el PUT falla", {"fecha": ""}, http={"GET cita": CITA, "PUT confirmar": {"error": {"message": "500"}}}, pg={"Recordatorios abiertos": [ROW], "Marcar recordatorio": {}}),
        esc("C5 dos recordatorios sin decir cuál", {"fecha": ""}, pg={"Recordatorios abiertos": [ROW, ROW2]}),
        esc("C5b dos recordatorios, pide el de Martina", {"fecha": "2026-10-20"}, http={"GET cita": {"data": {"id": 9300, "id_paciente": 777, "fecha": "2026-10-20", "hora_inicio": "16:20:00", "id_estado": 15, "estado_anulacion": 0}}, "PUT confirmar": {"data": {"id": 9300, "id_estado": 18}}}, pg={"Recordatorios abiertos": [ROW, ROW2], "Marcar recordatorio": {}}),
        esc("C6 sin recordatorio ni fecha", {"fecha": ""}, pg={"Recordatorios abiertos": [{}]}),
        esc("C7 sin recordatorio pero con fecha y turno visto", {"fecha": "2026-10-16"}, {f"turnos_vistos:{TEL}": TURNOS}, http={"GET cita": CITA, "PUT confirmar": PUT18}, pg={"Recordatorios abiertos": [{}]}),
        esc("C8 la cita cambió de fecha", {"fecha": ""}, http={"GET cita": {"data": {**CITA["data"], "fecha": "2026-10-19"}}}, pg={"Recordatorios abiertos": [ROW]}),
        esc("C9 la cita está anulada", {"fecha": ""}, http={"GET cita": {"data": {**CITA["data"], "id_estado": 1, "estado_anulacion": 1}}}, pg={"Recordatorios abiertos": [ROW]}),
        esc("C10 la agenda no responde", {"fecha": ""}, http={"GET cita": {"__throw": True}}, pg={"Recordatorios abiertos": [ROW]}),
        esc("C11 la cita ahora es de otra ficha", {"fecha": ""}, http={"GET cita": {"data": {**CITA["data"], "id_paciente": 777}}}, pg={"Recordatorios abiertos": [ROW]}),
    ])
    print("\nconfirmar_turno")
    met = lambda a: [p["metodo"] + " " + (p["url"] or "").replace(D, "") for p in a["pedidos"] if p["metodo"] in ("GET", "PUT", "POST")]
    x = r["C1 un recordatorio abierto, todo ok"]; a = x["reps"][0]
    chequear("C1 GET → PUT (id_estado 18) y marca el recordatorio", a["error"] is None and met(a) == ["GET /citas/9104", "PUT /citas/9104"] and next(q for q in a["pedidos"] if q["nodo"] == "PUT confirmar")["body"] == {"id_estado": 18} and any(p["nodo"] == "Marcar recordatorio" for p in a["pedidos"]), (a["error"], a["pedidos"]))
    chequear("C1 el mensaje lo arma el código", a["salida"]["readback_text"] == "Listo, su turno del viernes 16/10 a las 09:10 quedó confirmado." and a["salida"]["ok"] is True, a["salida"])
    lib = json.loads(x["redis_final"][f"escrituras:{TEL}:ex-2"])
    chequear("C1 deja el libro (tipo confirmacion, ok)", lib[0]["tipo"] == "confirmacion" and lib[0]["ok"] is True and lib[0]["readback_text"] == a["salida"]["readback_text"], lib)
    x = r["C2 ya estaba confirmada"]; a = x["reps"][0]
    chequear("C2 ya confirmada: no hace PUT, lo dice y igual cierra el recordatorio", met(a) == ["GET /citas/9104"] and a["salida"]["ya_estaba_confirmada"] is True and "ya estaba confirmado" in a["salida"]["readback_text"] and any(p["nodo"] == "Marcar recordatorio" for p in a["pedidos"]), (met(a), a["salida"]))
    chequear("C2 sin escritura no hay libro", not any(k.startswith("escrituras:") for k in x["redis_final"]))
    a = r["C3 Dentalink dice 'igual al original'"]["reps"][0]
    chequear("C3 el 400 'igual al original' cuenta como éxito idempotente", a["salida"]["ok"] is True and a["salida"]["ya_estaba_confirmada"] is True, a["salida"])
    x = r["C4 el PUT falla"]; a = x["reps"][0]
    chequear("C4 PUT que falla: no confirma, no marca el recordatorio y avisa a Asiri", a["salida"]["motivo"] == "no_pude_confirmar" and not any(p["nodo"] == "Marcar recordatorio" for p in a["pedidos"]) and "avisar_grupo" in a["salida"]["para_asiri"], a["salida"])
    a = r["C5 dos recordatorios sin decir cuál"]["reps"][0]
    chequear("C5 dos recordatorios sin fecha: no confirma nada y devuelve las fechas", a["salida"]["motivo"] == "varios_recordatorios" and a["salida"]["fechas_iso"] == ["2026-10-16", "2026-10-20"] and not met(a), a["salida"])
    a = r["C5b dos recordatorios, pide el de Martina"]["reps"][0]
    chequear("C5b con fecha confirma SOLO esa cita (9300)", met(a) == ["GET /citas/9300", "PUT /citas/9300"] and a["salida"]["ok"] is True, (met(a), a["salida"]))
    a = r["C6 sin recordatorio ni fecha"]["reps"][0]
    chequear("C6 sin recordatorio: le dice a Asiri que mire ver_turnos", a["salida"]["motivo"] == "sin_recordatorio" and not met(a), a["salida"])
    a = r["C7 sin recordatorio pero con fecha y turno visto"]["reps"][0]
    chequear("C7 confirma un turno visto por fecha y NO toca recordatorios", a["salida"]["ok"] is True and met(a) == ["GET /citas/9104", "PUT /citas/9104"] and not any(p["nodo"] == "Marcar recordatorio" for p in a["pedidos"]), (met(a), a["pedidos"]))
    for k, motivo in [("C8 la cita cambió de fecha", "cita_cambio"), ("C9 la cita está anulada", "cita_no_vigente"), ("C10 la agenda no responde", "error_tecnico"), ("C11 la cita ahora es de otra ficha", "cita_cambio")]:
        a = r[k]["reps"][0]
        chequear(f"{k[:3].strip()} → {motivo}, no escribe", a["salida"]["motivo"] == motivo and not any(q["metodo"] == "PUT" for q in a["pedidos"]) and not any(q["nodo"] == "Marcar recordatorio" for q in a["pedidos"]), (a["salida"], met(a)))

    # ------------------------------------------------------------------ clinica
    ESTADO = {f"{k}:{TEL}": "x" for k in ("propuesta", "ofertas", "lotes", "turnos_vistos", "bloque")}
    base_c = {"modo": "vivo", "nivel": "", "texto": "", "motivo": "", "cita_textual": "", "texto_paciente": ""}
    r = correr(B.wf_clinica(), [
        esc("K1 avisar_grupo FYI", {**base_c, "accion": "aviso", "nivel": "FYI", "texto": "Preguntó por un presupuesto de alineadores"}, dict(ESTADO)),
        esc("K2 pasar_a_humano verificado", {**base_c, "accion": "humano", "motivo": "pidio_persona", "cita_textual": "quiero hablar con la secretaria", "texto_paciente": "Hola, quiero hablar con la secretaria"}, dict(ESTADO)),
        esc("K3 pasar_a_humano inventado", {**base_c, "accion": "humano", "motivo": "pidio_persona", "cita_textual": "quiero hablar con la secretaria", "texto_paciente": "Confirmo mi turno"}, dict(ESTADO)),
        esc("K4 primer comprobante", {**base_c, "accion": "pago"}, dict(ESTADO)),
        esc("K4b segundo comprobante en 15 min", {**base_c, "accion": "pago"}, {**ESTADO, f"pago:{TEL}": "1"}),
        esc("K5 sombra: pasar_a_humano", {**base_c, "modo": "sombra", "accion": "humano", "motivo": "pidio_persona", "cita_textual": "quiero hablar con la secretaria", "texto_paciente": "quiero hablar con la secretaria"}, dict(ESTADO)),
        esc("K6 el webhook del grupo está caído", {**base_c, "accion": "humano", "motivo": "pidio_persona", "cita_textual": "quiero hablar con la secretaria", "texto_paciente": "quiero hablar con la secretaria"}, dict(ESTADO), aviso_falla=True),
        esc("K7 lista de espera", {**base_c, "accion": "espera", "texto": "Quiere antes del 22/10"}, dict(ESTADO)),
        esc("K8 derivar_triaje", {**base_c, "accion": "triaje", "cita_textual": "se me salió el alambre", "texto_paciente": "se me salió el alambre"}, dict(ESTADO)),
        esc("K9 pasar_a_humano con urgencia", {**base_c, "accion": "humano", "motivo": "urgencia", "cita_textual": "me duele mucho", "texto_paciente": "me duele mucho"}, dict(ESTADO)),
    ])
    print("\nclinica")
    x = r["K1 avisar_grupo FYI"]; a = x["reps"][0]
    chequear("K1 avisa al grupo con [FYI], SIN pedir silencio, y deja el estado intacto", len(a["avisos"]) == 1 and a["avisos"][0]["qs"]["resumen"].startswith("[FYI]") and "tomar" not in a["avisos"][0]["qs"] and a["avisos"][0]["qs"]["phone"] == TEL and all(k in x["redis_final"] for k in ESTADO), (a["avisos"], list(x["redis_final"])))
    x = r["K2 pasar_a_humano verificado"]; a = x["reps"][0]
    chequear("K2 pasa a una persona: aviso con tomar=true", len(a["avisos"]) == 1 and a["avisos"][0]["qs"].get("tomar") == "true" and "pidió hablar con una persona" in a["avisos"][0]["qs"]["resumen"], a["avisos"])
    chequear("K2 borra propuesta, ofertas, lotes, turnos_vistos y bloque (el staff interviene: nada viejo se puede ejecutar)", not any(k in x["redis_final"] for k in ESTADO), list(x["redis_final"]))
    chequear("K2 le dice a Asiri que no siga con turnos", a["salida"]["ok"] is True and "no sigas" in a["salida"]["para_asiri"], a["salida"])
    x = r["K3 pasar_a_humano inventado"]; a = x["reps"][0]
    chequear("K3 el motivo no se verifica: NO silencia, NO borra estado, avisa ACCIÓN", len(a["avisos"]) == 1 and "tomar" not in a["avisos"][0]["qs"] and a["avisos"][0]["qs"]["resumen"].startswith("[ACCIÓN]") and all(k in x["redis_final"] for k in ESTADO) and a["salida"]["degradado"] is True, (a["avisos"], a["salida"]))
    x = r["K4 primer comprobante"]; a = x["reps"][0]
    chequear("K4 comprobante: aviso ACCIÓN sin silenciar y marca para no repetir", a["avisos"][0]["qs"]["resumen"].startswith("[ACCIÓN]") and "tomar" not in a["avisos"][0]["qs"] and x["redis_final"][f"pago:{TEL}"] == "1", (a["avisos"], x["redis_final"]))
    a = r["K4b segundo comprobante en 15 min"]["reps"][0]
    chequear("K4b segundo comprobante: no repite el aviso", not a["avisos"] and a["salida"]["ok"] is True, a["avisos"])
    x = r["K5 sombra: pasar_a_humano"]; a = x["reps"][0]
    chequear("K5 sombra: ni avisos ni borrado de estado", not a["avisos"] and all(k in x["redis_final"] for k in ESTADO) and a["salida"]["simulado"] is True, (a["avisos"], a["salida"]))
    a = r["K6 el webhook del grupo está caído"]["reps"][0]
    chequear("K6 si el aviso no sale, se lo dice a Asiri para que no afirme que ya avisó", a["salida"].get("aviso_no_enviado") is True and "no digas que ya les avisaste" in a["salida"]["para_asiri"], a["salida"])
    a = r["K7 lista de espera"]["reps"][0]
    chequear("K7 lista de espera: aviso FYI y prohíbe prometer", a["avisos"][0]["qs"]["resumen"].startswith("[FYI] Lista de espera") and "NO prometas" in a["salida"]["para_asiri"], (a["avisos"], a["salida"]))

    for k in ("K8 derivar_triaje", "K9 pasar_a_humano con urgencia"):
        x = r[k]; a = x["reps"][0]; clave = f"triaje_v7:{TEL}:{TRIG['exec_id_actual']}"
        marca = json.loads(x["redis_final"].get(clave) or "null")
        chequear(f"{k[:2]} deja la marca triaje_v7 de ESTA ejecución, sin aviso al grupo, sin silenciar y sin borrar estado",
                 marca and marca["cita"] and not a["avisos"] and all(c in x["redis_final"] for c in ESTADO) and a["salida"]["derivado_a_triaje"] is True, (x["redis_final"], a["avisos"], a["salida"]))
    x = r["K1 avisar_grupo FYI"]
    chequear("K10 las demás acciones NO dejan marca de triaje", not any(c.startswith("triaje_v7:") for c in x["redis_final"]), list(x["redis_final"]))

    print(f"\n{total - fallas}/{total} {'TODO OK' if not fallas else str(fallas) + ' FALLAS'}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
