# -*- coding: utf-8 -*-
"""
test_v7_cerebro.py — v7 Cerebro como GRAFO de n8n (nodo por nodo, sin red). El agente (LLM) se simula con lo que "responde"; lo que se prueba es TODO lo que el código
hace alrededor: el contexto que ve Asiri, el chequeo de salida contra el libro de escrituras, el banlist, la marca de propuesta enviada, la memoria y los avisos.
Más: la ESTRUCTURA de las 10 herramientas (qué decide el modelo y qué decide el código).
USO:  python tests/test_v7_cerebro.py
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import build_v7_workflows as B  # noqa: E402

AHORA = "2026-10-05T12:36:00Z"   # lunes 09:36 en Jujuy
TEL = "5490000000651"
EXEC = "ex-C1"
total = fallas = 0


def chequear(nombre, cond, extra=None):
    global total, fallas
    total += 1
    if not cond:
        fallas += 1
        print(f"  FALLA {nombre}" + (f" → {json.dumps(extra, ensure_ascii=False)[:500]}" if extra else ""))
    else:
        print(f"  ok    {nombre}")


KB = [{"id": "20", "contenido": "La Dra. Raquel atiende martes y jueves de 8:00 a 12:00 hs, viernes de 8:30 a 12:00 hs, y lunes y miércoles de 15:00 a 19:00 hs."},
      {"id": "21", "contenido": "La primera consulta tiene un valor de $50.000 e incluye evaluación + diagnóstico presuntivo."},
      {"id": "24", "contenido": "Titular: Laura Raquel Rodríguez. Alias: dra.raquel.aurea. Al abonar, enviar el comprobante por favor."},
      {"id": "25", "contenido": "ÁUREA ODONTOLOGÍA ESTÉTICA — Balcarce Nº37, 2º piso."},
      {"id": "36", "contenido": "El valor de la cuota mensual del tratamiento ortodóncico es de $70.000."},
      {"id": "39", "contenido": "$50.000 (incluye control + refuerzo retenedor)."},
      {"id": "dir:notas_para_asiri", "contenido": ""}]
IDENT_UNA = {"ok": True, "varias_fichas": False, "ficha_elegida": True, "paciente_elegido": "Dana Yael", "turnos": ["viernes 16/10 a las 09:10"], "para_asiri": "..."}
IDENT_VARIAS = {"ok": True, "varias_fichas": True, "ficha_elegida": False, "paciente_elegido": None, "pacientes": ["Test - Jana", "Test - Lucas"], "turnos": [], "para_asiri": "..."}
IDENT_ERROR = {"ok": False, "motivo": "error_tecnico", "para_asiri": "No pude consultar la agenda"}
PG_BASE = {"Historial": [{}], "Recordatorios": [{}], "Datos del consultorio": KB, "Guardar en memoria": {}}
OFERTAS = json.dumps([{"fecha": "2026-10-22", "hora": "08:00"}, {"fecha": "2026-10-22", "hora": "09:20"}])
VISTOS = json.dumps([{"id": 9104, "id_paciente": 651, "fecha": "2026-10-16", "hora_inicio": "09:10", "id_estado": 15, "estado_anulacion": 0}])
BLOQUE = "Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n\nLe sirve alguno?"
RB = "Listo, quedó reprogramado su turno: anulé el del viernes 16/10 a las 09:10 y le reservé el jueves 22/10 a las 09:20."
TRIAJE = json.dumps({"motivo": "derivar_triaje", "cita": "Se me salió el alambre y me pincha"})
LIBRO_OK = json.dumps([{"ok": True, "parcial": False, "tipo": "cambio", "readback_text": RB}])


def esc(id_, agente, texto="Hola", redis=None, pg=None, modo="vivo", **extra):
    trig = {"phone": TEL, "texto": texto, "pushName": "CELE", "modo": modo, **(extra.pop("trigger", {}))}
    subwf = {"Identificar paciente": IDENT_UNA, **(extra.pop("subwf", {}))}
    return {"id": id_, "trigger": trig, "ahora": AHORA, "exec_id": EXEC, "redis": redis or {}, "pg": {**PG_BASE, **(pg or {})}, "subwf": subwf, "agente": agente, **extra}


def correr(wf, escenarios):
    with tempfile.TemporaryDirectory() as d:
        w, e = os.path.join(d, "wf.json"), os.path.join(d, "e.json")
        json.dump(wf, open(w, "w", encoding="utf-8"), ensure_ascii=True)
        json.dump(escenarios, open(e, "w", encoding="utf-8"), ensure_ascii=True)
        p = subprocess.run(["node", os.path.join(ROOT, "tests", "harness_grafo.mjs"), w, e], capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit("node fallo: " + p.stderr[-2500:])
        return {r["id"]: r for r in json.loads(p.stdout)}


def main():
    wf = B.wf_cerebro()
    HIST = [{"message": {"type": "ai", "content": "Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n\nLe sirve alguno?", "additional_kwargs": {"source": "wa_outbound"}}},
            {"message": {"type": "human", "content": "Buen dia me pude cambiar ese turno"}}]
    PROP = {"id": f"{TEL}-1", "tipo": "cambio", "estado": "pendiente", "creada_ms": 1, "exec_id": EXEC, "tel": TEL, "paciente_id": 651, "slot": {"fecha": "2026-10-22", "hora": "09:20"},
            "cita_vieja": {"id": 9104, "fecha": "2026-10-16", "hora": "09:10"}, "readback_text": "Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?"}
    base_redis = {f"ofertas:{TEL}": OFERTAS, f"turnos_vistos:{TEL}": VISTOS, f"bloque:{TEL}": BLOQUE}
    R = correr(wf, [
        esc("Z1 charla normal", {"output": "Hola! ¿En qué puedo ayudarle?"}),
        esc("Z2 sombra: no escribe nada afuera", {"output": "Hola! ¿En qué puedo ayudarle?"}, modo="sombra"),
        esc("Z3 afirma que reprogramó sin escritura ok", {"output": "Listo, quedó reprogramado su turno para el jueves 22/10 a las 09:20."}, redis=base_redis),
        esc("Z4 escritura ok y el texto la dice", {"output": "Perfecto. " + RB + " ¿Necesita algo más?"}, redis={**base_redis, f"escrituras:{TEL}:{EXEC}": LIBRO_OK}),
        esc("Z5 el agente se cae pero la agenda SÍ se escribió", {"error": {"message": "timeout"}}, redis={**base_redis, f"escrituras:{TEL}:{EXEC}": LIBRO_OK}),
        esc("Z6 el agente se cae y no hubo escritura", {"error": {"message": "Agent stopped due to max iterations"}}),
        esc("Z7 invita a ir ahora (filtro de seguridad)", {"output": "Acérquese ahora mismo a la clínica."}),
        esc("Z8 'los esperamos el día de su turno' (negocio funcionando)", {"output": "Quedó todo. Los esperamos el día de su turno, el jueves 22/10 a las 9:20."}, redis=base_redis),
        esc("Z9 propuesta de esta ejecución con su read-back en el mensaje", {"output": PROP["readback_text"]}, redis={**base_redis, f"propuesta:{TEL}": json.dumps(PROP)}),
        esc("Z9b propuesta pero el mensaje no trae el read-back", {"output": "Un momento por favor."}, redis={**base_redis, f"propuesta:{TEL}": json.dumps(PROP)}),
        esc("Z16 el modelo se saltea el bloque de horarios recién buscado", {"output": "Le quedan las fichas de Jana y Lucas. ¿Confirma?"}, redis={**base_redis, f"bloque_exec:{TEL}:{EXEC}": BLOQUE}),
        esc("Y1 'Si , gracias' tras confirmar el turno (caso real de Irina)", {"output": "NO DEBE LLAMARSE"}, texto="Si , gracias", pg={"Historial": [{"message": {"type": "ai", "content": "Listo, su turno del 6 de Octubre a las 08:00 hs queda confirmado. Cualquier consulta nos puede escribir por este medio.", "additional_kwargs": {"source": "wa_outbound"}}}]}),
        esc("Y2 'Muchas gracias 🫂' tras una respuesta de datos (caso real de Irina)", {"output": "NO DEBE LLAMARSE"}, texto="Muchas gracias 🫂", pg={"Historial": [{"message": {"type": "ai", "content": "La consulta inicial cuesta $50.000.", "additional_kwargs": {}}}]}),
        esc("Y3 'Bien\\nMuchas gracias Iris' (caso real)", {"output": "NO DEBE LLAMARSE"}, texto="Bien\nMuchas gracias Iris", pg={"Historial": [{"message": {"type": "ai", "content": "Quedó anotado, la clínica se comunica con usted.", "additional_kwargs": {}}}]}),
        esc("Y4 'Si, gracias' como respuesta al read-back (es una confirmación, NO un cierre)", {"output": "Perfecto."}, texto="Si, gracias", pg={"Historial": [{"message": {"type": "ai", "content": PROP["readback_text"], "additional_kwargs": {}}}]}),
        esc("Y5 'Gracias' con un recordatorio sin confirmar", {"output": "Perfecto."}, texto="Gracias", pg={"Historial": [{"message": {"type": "ai", "content": "Estimada Dana, le recordamos su turno. Le pedimos confirmar su asistencia.", "additional_kwargs": {"source": "reminder_note"}}}], "Recordatorios": [{"id_cita_dentalink": 9104, "fecha_turno": "2026-10-16", "hora_turno": "09:10:00"}]}),
        esc("Y6 'Gracias, ¿cuánto sale?' (agradece pero pregunta)", {"output": "La consulta cuesta $50.000."}, texto="Gracias, ¿cuánto sale?", pg={"Historial": [{"message": {"type": "ai", "content": "Listo, quedó confirmado.", "additional_kwargs": {}}}]}),
        esc("Z17 celular con varias fichas, sin elegir", {"output": "Ok"}, subwf={"Identificar paciente": IDENT_VARIAS}),
        esc("Z18 la agenda no responde al identificar", {"output": "Ok"}, subwf={"Identificar paciente": IDENT_ERROR}),
        esc("Z10 cierre sin nada pendiente", {"output": "[NO_REPLY]"}, texto="Gracias"),
        esc("Z11 contexto con historial y recordatorios", {"output": "Ok"}, pg={"Historial": HIST, "Recordatorios": [{"id_cita_dentalink": 9104, "fecha_turno": "2026-10-16", "hora_turno": "09:10:00"}]}),
        esc("Z12 con notas de la clínica", {"output": "Ok"}, pg={"Datos del consultorio": KB[:-1] + [{"id": "dir:notas_para_asiri", "contenido": "Este mes hay promoción en alineadores."}]}),
        esc("Z13 inventa un horario", {"output": "Tenemos el jueves 22/10 a las 11:40, ¿le sirve?"}, redis=base_redis),
        esc("Z14a da la dirección sin que la pidan", {"output": "Estamos en Balcarce 37, 2do piso."}, texto="Hola quiero un turno"),
        esc("Z14b da la dirección cuando la piden", {"output": "Estamos en Balcarce 37, 2do piso."}, texto="Dónde queda el consultorio?"),
        esc("Z15 historial_json (sombra retrospectiva)", {"output": "Ok"}, modo="sombra", trigger={"historial_json": json.dumps(HIST)}),
        esc("M1 el modelo antepone una frase interna al bloque", {"output": "Le copio el mensaje para que lo confirme:\n\n" + PROP["readback_text"]}, redis={**base_redis, f"propuesta:{TEL}": json.dumps(PROP)}),
        esc("M2 'Pegá este bloque TEXTUAL al paciente:' antes del bloque real", {"output": "Pegá este bloque TEXTUAL al paciente:\n" + BLOQUE}, redis=base_redis),
        esc("U1 urgencia derivada al triaje", {"output": "[NO_REPLY]"}, texto="Se me salió el alambre y me pincha", redis={f"triaje_v7:{TEL}:{EXEC}": TRIAJE}),
        esc("U2 urgencia derivada pero el modelo igual escribe", {"output": "Tranquila, póngase cera y venga mañana."}, texto="Se me salió el alambre y me pincha", redis={f"triaje_v7:{TEL}:{EXEC}": TRIAJE}),
        esc("U3 urgencia + cambio de agenda ok en el mismo mensaje", {"output": "Perfecto. " + RB}, texto="Sí, cámbielo. Ah, y se me salió el alambre", redis={**base_redis, f"escrituras:{TEL}:{EXEC}": LIBRO_OK, f"triaje_v7:{TEL}:{EXEC}": TRIAJE}),
        esc("U4 sombra: urgencia derivada", {"output": "[NO_REPLY]"}, modo="sombra", texto="me duele", redis={f"triaje_v7:{TEL}:{EXEC}": TRIAJE}),
        esc("U5 marca de triaje de OTRA ejecución no cuenta", {"output": "Hola! ¿En qué puedo ayudarle?"}, redis={f"triaje_v7:{TEL}:ex-viejo": TRIAJE}),
    ])

    print("CEREBRO (grafo real, agente simulado)")
    a = R["Z1 charla normal"]["reps"][0]; s = a["salida"]
    mem = next(p for p in a["pedidos"] if p["nodo"] == "Guardar en memoria")
    chequear("Z1 sin error del motor y texto intacto", a["error"] is None and s["texto"] == "Hola! ¿En qué puedo ayudarle?" and s["enviar"] is True, (a["error"], s))
    chequear("Z1 guarda la charla en memoria (paciente y Asiri) con el texto FINAL", mem["params"][0] == TEL and json.loads(mem["params"][1])["content"] == "Hola" and json.loads(mem["params"][2])["content"] == s["texto"] and json.loads(mem["params"][2])["additional_kwargs"]["source"] == "wa_outbound", mem)
    a = R["Z2 sombra: no escribe nada afuera"]["reps"][0]
    chequear("Z2 sombra: sin memoria, sin avisos, devuelve el texto y las herramientas usadas", not any(p["nodo"] == "Guardar en memoria" for p in a["pedidos"]) and not a["avisos"] and a["salida"]["texto"] and "tools" in a["salida"], (a["pedidos"], a["avisos"]))
    x = R["Z3 afirma que reprogramó sin escritura ok"]; a = x["reps"][0]; mem = next(p for p in a["pedidos"] if p["nodo"] == "Guardar en memoria")
    chequear("Z3 bloquea el 'quedó reprogramado' sin escritura y manda un mensaje honesto", a["salida"]["motivo_chequeo"] == "afirma_reprogramar_sin_ok" and "no quedó hecho" in a["salida"]["texto"] and "quedó reprogramado" not in a["salida"]["texto"], a["salida"])
    chequear("Z3 en memoria queda lo que REALMENTE se le dijo (no el texto bloqueado)", json.loads(mem["params"][2])["content"] == a["salida"]["texto"], mem)
    a = R["Z4 escritura ok y el texto la dice"]["reps"][0]
    chequear("Z4 escritura ok y el texto la dice: pasa sin tocar", a["salida"]["motivo_chequeo"] is None and a["salida"]["texto"].startswith("Perfecto.") and RB in a["salida"]["texto"], a["salida"])
    a = R["Z5 el agente se cae pero la agenda SÍ se escribió"]["reps"][0]
    chequear("Z5 el agente cae pero la agenda se escribió: la paciente igual recibe lo que pasó, sin aviso de error", a["salida"]["texto"] == RB and a["salida"]["fallo_agente"] is True and not a["avisos"], (a["salida"], a["avisos"]))
    a = R["Z6 el agente se cae y no hubo escritura"]["reps"][0]
    chequear("Z6 el agente cae sin escritura: mensaje honesto y aviso [ACCIÓN] a la clínica", "inconveniente" in a["salida"]["texto"] and len(a["avisos"]) == 1 and a["avisos"][0]["qs"]["resumen"].startswith("[ACCIÓN]") and a["avisos"][0]["qs"]["phone"] == TEL, (a["salida"], a["avisos"]))
    a = R["Z7 invita a ir ahora (filtro de seguridad)"]["reps"][0]
    chequear("Z7 'acérquese ahora mismo': reemplazado y avisado", a["salida"]["motivo_banlist"] == "invita a ir de inmediato" and "Acérquese" not in a["salida"]["texto"] and a["avisos"], (a["salida"], a["avisos"]))
    a = R["Z8 'los esperamos el día de su turno' (negocio funcionando)"]["reps"][0]
    chequear("Z8 'los esperamos el día de su turno' pasa (es el negocio)", a["salida"]["motivo_banlist"] is None and a["salida"]["motivo_chequeo"] is None and "esperamos" in a["salida"]["texto"], a["salida"])
    x = R["Z9 propuesta de esta ejecución con su read-back en el mensaje"]
    chequear("Z9 marca la propuesta como ENVIADA (así ejecutar_propuesta sabe que el paciente vio el read-back)", json.loads(x["redis_final"][f"propuesta:{TEL}"])["enviada"] is True, x["redis_final"])
    x = R["Z9b propuesta pero el mensaje no trae el read-back"]; a = x["reps"][0]
    chequear("Z9b si el modelo se saltea el read-back, el CÓDIGO lo manda (sin él la charla se traba) y recién entonces queda enviada", a["salida"]["motivo_chequeo"] == "falta_readback" and a["salida"]["texto"] == PROP["readback_text"] and json.loads(x["redis_final"][f"propuesta:{TEL}"]).get("enviada") is True, (a["salida"], x["redis_final"]))
    x = R["Z16 el modelo se saltea el bloque de horarios recién buscado"]; a = x["reps"][0]
    chequear("Z16 el modelo se saltea el bloque que buscó: el código lo manda tal cual", a["salida"]["motivo_chequeo"] == "falta_bloque" and a["salida"]["texto"] == BLOQUE, a["salida"])
    a = R["Z10 cierre sin nada pendiente"]["reps"][0]
    chequear("Z10 [NO_REPLY]: no se envía ni se guarda memoria", a["salida"]["enviar"] is False and not any(p["nodo"] == "Guardar en memoria" for p in a["pedidos"]), a["salida"])
    a = R["Z11 contexto con historial y recordatorios"]["reps"][0]
    ag = next(p for p in a["pedidos"] if p["nodo"] == "Asiri")["entradas"]
    chequear("Z11 el agente recibe fecha de Jujuy, el pushName, el recordatorio pendiente, la charla y el mensaje", "FECHA Y HORA ACTUAL (Jujuy): lunes 2026-10-05 09:36" in ag["text"] and "CELE" in ag["text"] and "viernes 16/10 a las 09:10" in ag["text"] and "PACIENTE: Buen dia me pude cambiar ese turno" in ag["text"] and ag["text"].endswith("MENSAJE ACTUAL DEL PACIENTE:\nHola"), ag["text"])
    chequear("Z11b el agente recibe ya resuelto quién es el paciente y sus turnos vigentes (sin tener que llamar ver_turnos)", "DATOS DE ESTE CELULAR EN LA AGENDA" in ag["text"] and "Paciente de este celular: Dana Yael. Turnos vigentes: viernes 16/10 a las 09:10." in ag["text"], ag["text"])
    agv = next(p for p in R["Z17 celular con varias fichas, sin elegir"]["reps"][0]["pedidos"] if p["nodo"] == "Asiri")["entradas"]["text"]
    chequear("Z17 varias fichas sin elegir: le dice que TODAVÍA no sabe para quién es y que use elegir_ficha", "Pacientes con este celular: Test - Jana, Test - Lucas" in agv and "TODAVÍA no sabés para quién es" in agv and "igual buscá y ofrecé horarios" in agv and "elegir_ficha" in agv, agv)
    age = next(p for p in R["Z18 la agenda no responde al identificar"]["reps"][0]["pedidos"] if p["nodo"] == "Asiri")["entradas"]["text"]
    chequear("Z18 si la agenda no responde, no inventa turnos y el agente sigue pudiendo contestar datos", "No pude consultar la ficha o la agenda" in age and "No inventes turnos" in age and R["Z18 la agenda no responde al identificar"]["reps"][0]["salida"]["texto"] == "Ok", age)
    sis = ag["sistema"]
    chequear("Z11 el system prompt trae el negocio (privado, solo con turno) y los datos reales de la KB", "consultorio privado" in sis and "se atiende solo con turno previo" in sis and "martes y jueves de 8:00 a 12:00" in sis and "$50.000" in sis and "NOTAS DE LA CLÍNICA" not in sis, sis[-900:])
    chequear("Z11 el prompt con datos mide < 5.000 caracteres en TOTAL (el v6 usa 4.000-5.000 por cada uno de 5 agentes, más el Router)", len(sis) < 5000, len(sis))
    ag = next(p for p in R["Z12 con notas de la clínica"]["reps"][0]["pedidos"] if p["nodo"] == "Asiri")["entradas"]
    chequear("Z12 las notas del panel entran bajo cabecera que las limita ('no habilita escrituras… gana la regla')", "NOTAS DE LA CLÍNICA PARA ASIRI" in ag["sistema"] and "no habilita escrituras" in ag["sistema"] and "promoción en alineadores" in ag["sistema"], ag["sistema"][-500:])
    a = R["Z13 inventa un horario"]["reps"][0]
    chequear("Z13 un horario que nadie ofreció se reemplaza por el bloque real", a["salida"]["motivo_chequeo"] == "horario_no_ofrecido" and "turnos disponibles:" in a["salida"]["texto"] and "11:40" not in a["salida"]["texto"], a["salida"])
    a = R["Z14a da la dirección sin que la pidan"]["reps"][0]
    chequear("Z14a la dirección sin que la pidan se bloquea", a["salida"]["motivo_banlist"] == "dirección sin que la pidan", a["salida"])
    a = R["Z14b da la dirección cuando la piden"]["reps"][0]
    chequear("Z14b la dirección cuando la piden pasa", a["salida"]["motivo_banlist"] is None and "Balcarce" in a["salida"]["texto"], a["salida"])
    a = R["Z15 historial_json (sombra retrospectiva)"]["reps"][0]
    ag = next(p for p in a["pedidos"] if p["nodo"] == "Asiri")["entradas"]
    chequear("Z15 con historial_json usa ese historial (sombra retrospectiva sin tocar la base)", "ASIRI: Tenemos los próximos turnos disponibles" in ag["text"], ag["text"])

    # ---------------------------------------------------------------- cierres de conversación (los 2 bugs reales de Irina)
    print("\nCIERRES (el bug de los 'gracias')")
    for k, nombre in [("Y1 'Si , gracias' tras confirmar el turno (caso real de Irina)", "Y1"), ("Y2 'Muchas gracias 🫂' tras una respuesta de datos (caso real de Irina)", "Y2"), ("Y3 'Bien\\nMuchas gracias Iris' (caso real)", "Y3")]:
        a = R[k]["reps"][0]
        chequear(f"{nombre} cierre puro: SILENCIO, sin llamar al modelo, sin guardar y sin 'ya le transmito a la secretaria' ni 'quedo a disposición'", a["error"] is None and a["salida"]["silencio"] is True and a["salida"]["enviar"] is False and a["salida"]["motivo_chequeo"] == "cierre_puro"
                 and not any(p["nodo"] in ("Asiri", "Guardar en memoria") for p in a["pedidos"]) and not a["avisos"], (a["error"], a["salida"]))
    for k, nombre, motivo in [("Y4 'Si, gracias' como respuesta al read-back (es una confirmación, NO un cierre)", "Y4", "era la respuesta al read-back"), ("Y5 'Gracias' con un recordatorio sin confirmar", "Y5", "hay un recordatorio sin confirmar"), ("Y6 'Gracias, ¿cuánto sale?' (agradece pero pregunta)", "Y6", "además hace una pregunta")]:
        a = R[k]["reps"][0]
        chequear(f"{nombre} NO es un cierre ({motivo}): el modelo SÍ interviene", any(p["nodo"] == "Asiri" for p in a["pedidos"]) and a["salida"]["silencio"] is False and a["salida"]["enviar"] is True, (a["salida"], [p["nodo"] for p in a["pedidos"]]))

    # ---------------------------------------------------------------- frases internas filtradas al paciente (examen 06/10)
    print("\nFRASES INTERNAS")
    a = R["M1 el modelo antepone una frase interna al bloque"]["reps"][0]
    chequear("M1 'Le copio el mensaje para que lo confirme:' se quita por código y queda solo el read-back", a["salida"]["texto"] == PROP["readback_text"] and a["salida"]["motivo_chequeo"] is None, a["salida"])
    a = R["M2 'Pegá este bloque TEXTUAL al paciente:' antes del bloque real"]["reps"][0]
    chequear("M2 'Pegá este bloque TEXTUAL al paciente:' se quita y el bloque pasa intacto", a["salida"]["texto"] == BLOQUE and a["salida"]["motivo_chequeo"] is None, a["salida"])

    # ---------------------------------------------------------------- urgencias → triaje del v6 (videos aprobados por la Dra.)
    print("\nURGENCIAS (derivar_triaje)")
    for k in ("U1 urgencia derivada al triaje", "U2 urgencia derivada pero el modelo igual escribe"):
        a = R[k]["reps"][0]; s_ = a["salida"]
        chequear(f"{k[:2]} devuelve derivar_triaje con la frase, NO envía texto de Asiri, NO guarda memoria (la guarda el triaje) y sin avisos propios",
                 a["error"] is None and s_["derivar_triaje"] is True and s_["triaje"]["cita"] == "Se me salió el alambre y me pincha" and s_["enviar"] is False and s_["texto"] is None
                 and not any(p["nodo"] == "Guardar en memoria" for p in a["pedidos"]) and not a["avisos"], (a["error"], s_, a["avisos"]))
    a = R["U3 urgencia + cambio de agenda ok en el mismo mensaje"]["reps"][0]
    chequear("U3 urgencia junto a una escritura ok: se cuenta el cambio (read-back) y la urgencia va al grupo como [ACCIÓN]; no se deriva",
             a["salida"]["derivar_triaje"] is False and RB in a["salida"]["texto"] and a["salida"]["enviar"] is True and any("urgencia" in v["qs"]["resumen"] and v["qs"]["resumen"].startswith("[ACCIÓN]") for v in a["avisos"]), (a["salida"], a["avisos"]))
    a = R["U4 sombra: urgencia derivada"]["reps"][0]
    chequear("U4 sombra: informa derivar_triaje (para medir) sin memoria ni avisos", a["salida"]["derivar_triaje"] is True and not a["avisos"] and not any(p["nodo"] == "Guardar en memoria" for p in a["pedidos"]), a["salida"])
    a = R["U5 marca de triaje de OTRA ejecución no cuenta"]["reps"][0]
    chequear("U5 una marca de otra ejecución no deriva este mensaje", a["salida"]["derivar_triaje"] is False and a["salida"]["enviar"] is True, a["salida"])
    a = R["Y1 'Si , gracias' tras confirmar el turno (caso real de Irina)"]["reps"][0]
    chequear("U6 el camino de cierre también devuelve derivar_triaje=false (el adaptador del v6 lee siempre el campo)", a["salida"]["derivar_triaje"] is False, a["salida"])
    sis = next(p for p in R["Z1 charla normal"]["reps"][0]["pedidos"] if p["nodo"] == "Asiri")["entradas"]["sistema"]
    chequear("U7 el prompt manda urgencias a derivar_triaje con [NO_REPLY] y ya no las pasa a una persona", "derivar_triaje" in sis and "URGENCIAS" in sis and "o hay una urgencia" not in sis, sis[sis.find("URGENCIAS"):sis.find("URGENCIAS") + 300])

    # ---------------------------------------------------------------- estructura de las herramientas
    print("\nHERRAMIENTAS DE ASIRI (qué decide el modelo y qué decide el código)")
    tools = [n for n in wf["nodes"] if n["type"].endswith("toolWorkflow")]
    chequear("S1 son 11 herramientas, todas conectadas al agente como ai_tool", len(tools) == 11 and all(any(x["node"] == "Asiri" for x in wf["connections"][n["name"]]["ai_tool"][0]) for n in tools), [n["name"] for n in tools])
    def campos(n):
        v = n["parameters"]["workflowInputs"]["value"]
        return {k: ("modelo" if "$fromAI" in x else "codigo") for k, x in v.items()}
    prohibidos = {"paciente_id", "id_paciente", "cita_id", "cita_vieja_id", "id", "propuesta", "propuesta_id", "enviada", "exec_id"}
    chequear("S2 NINGUNA herramienta deja que el modelo elija ids, paciente, cita ni propuesta", not any(prohibidos & set(campos(n)) for n in tools), {n["name"]: list(campos(n)) for n in tools})
    chequear("S3 teléfono, ejecución y modo SIEMPRE salen del código (nunca del modelo)", all(campos(n).get("tel") == "codigo" and campos(n).get("exec_id_actual") == "codigo" and campos(n).get("modo") == "codigo" for n in tools), [campos(n) for n in tools][:2])
    por_nombre = {n["name"]: n for n in tools}
    chequear("S4 ejecutar_propuesta no recibe NADA del modelo (la propuesta sale de Redis)", all(v == "codigo" for v in campos(por_nombre["ejecutar_propuesta"]).values()), campos(por_nombre["ejecutar_propuesta"]))
    chequear("S5 pasar_a_humano pide la frase literal y el texto del paciente lo pone el código (para verificarla)", campos(por_nombre["pasar_a_humano"]).get("cita_textual") == "modelo" and campos(por_nombre["pasar_a_humano"]).get("texto_paciente") == "codigo", campos(por_nombre["pasar_a_humano"]))
    chequear("S6 la acción de las herramientas de clínica es fija por herramienta (el modelo no puede cambiar 'aviso' por 'humano')", all(campos(por_nombre[k]).get("accion") == "codigo" for k in ("avisar_grupo", "pasar_a_humano", "registrar_pago", "lista_espera", "derivar_triaje")))
    chequear("S9 derivar_triaje: el modelo solo aporta la frase; acción 'triaje' fija; pasar_a_humano ya no ofrece 'urgencia'", set(campos(por_nombre["derivar_triaje"]).items()) >= {("accion", "codigo"), ("cita_textual", "modelo"), ("texto_paciente", "codigo")}
             and "triaje" in por_nombre["derivar_triaje"]["parameters"]["workflowInputs"]["value"]["accion"] and "urgencia" not in por_nombre["pasar_a_humano"]["parameters"]["workflowInputs"]["value"]["motivo"], campos(por_nombre["derivar_triaje"]))
    chequear("S7 el agente tiene tope de iteraciones y modelo mini con razonamiento bajo", next(n for n in wf["nodes"] if n["name"] == "Asiri")["parameters"]["options"]["maxIterations"] == 5 and next(n for n in wf["nodes"] if n["name"] == "Modelo Asiri")["parameters"]["options"]["reasoningEffort"] == "low")
    chequear("S8 ningún workflow generado lleva claves ni tokens escritos", not any(s in json.dumps([B.wf_cerebro(), B.wf_ejecutar(), B.wf_clinica(), B.wf_confirmar_turno()]) for s in ("sb_secret", "Bearer ", "apikey", "Token ")))

    print(f"\n{total - fallas}/{total} {'TODO OK' if not fallas else str(fallas) + ' FALLAS'}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
