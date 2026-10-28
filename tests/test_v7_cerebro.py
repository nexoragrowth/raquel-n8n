# -*- coding: utf-8 -*-
"""
test_v7_cerebro.py — v7 Cerebro con ORQUESTADOR + SUB-AGENTES (08/10) como GRAFO de n8n (nodo por nodo, sin red).
El orquestador (LLM) se simula con su JSON; los sub-agentes (workflows) con lo que devuelven. Se prueba TODO lo que hace el código alrededor:
el contexto, el despacho (qué sub-agente se llama, con qué datos, una vez), el ruteo por estado del "sí", urgencias, fuera de alcance, modo humano,
la composición (orden fijo, read-back al final, datos bancarios por código), el chequeo de salida, la marca de propuesta enviada, memoria, avisos y sombra.
(La suite del agente único quedó en v7/_retirados/test_v7_cerebro_agente_unico.py.txt; sus casos Z/U/S se portaron acá cuando aplican.)
USO:  python tests/test_v7_cerebro.py
"""
import json, os, re, subprocess, sys, tempfile, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import build_v7_workflows as B  # noqa: E402
import v7_workflow_cerebro as C  # noqa: E402

AHORA = "2026-10-05T12:36:00Z"   # lunes 09:36 en Jujuy
TEL = "5490000000651"
EXEC = "ex-C1"
total = fallas = 0


def chequear(nombre, cond, extra=None):
    global total, fallas
    total += 1
    if not cond:
        fallas += 1
        print(f"  FALLA {nombre}" + (f" → {json.dumps(extra, ensure_ascii=False)[:600]}" if extra is not None else ""))
    else:
        print(f"  ok    {nombre}")


KB = [{"id": "20", "contenido": "La Dra. Raquel atiende martes y jueves de 8:00 a 12:00 hs, viernes de 8:30 a 12:00 hs, y lunes y miércoles de 15:00 a 19:00 hs."},
      {"id": "21", "contenido": "La primera consulta tiene un valor de $50.000 e incluye evaluación + diagnóstico presuntivo."},
      {"id": "24", "contenido": "Titular: Laura Raquel Rodríguez. Alias: dra.raquel.aurea. Al abonar, enviar el comprobante por favor."},
      {"id": "25", "contenido": "ÁUREA ODONTOLOGÍA ESTÉTICA — Balcarce Nº37, 2º piso."},
      {"id": "22", "contenido": "No trabajamos con ninguna obra social, solo de forma particular, con turnos programados."},
      {"id": "dir:notas_para_asiri", "contenido": "Hablar con calidez."},
      {"id": "dir:menu_bienvenida", "contenido": "Hola! Soy Asiri 🤗\n\nEn qué puedo ayudarle hoy?\n1. Turnos\n4. Precios y formas de pago (Valor de consulta, cuotas, alias)"}]
IDENT = {"ok": True, "varias_fichas": False, "ficha_elegida": True, "paciente_elegido": "Dana Yael", "turnos": ["viernes 16/10 a las 09:10"], "para_asiri": "..."}
RECIENTE = "2026-10-05T12:20:00Z"
RB = "Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?"
EXITO = "Listo, quedó reprogramado su turno: anulé el del viernes 16/10 a las 09:10 y le reservé el jueves 22/10 a las 09:20."
BLOQUE = "Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n\nLe sirve alguno?"
OFERTAS = json.dumps([{"fecha": "2026-10-22", "hora": "08:00"}, {"fecha": "2026-10-22", "hora": "09:20"}])
VISTOS = json.dumps([{"id": 9104, "id_paciente": 651, "fecha": "2026-10-16", "hora_inicio": "09:10", "id_estado": 15, "estado_anulacion": 0}])
LIBRO_OK = json.dumps([{"ok": True, "parcial": False, "tipo": "cambio", "readback_text": EXITO}])
TRIAJE = json.dumps({"motivo": "derivar_triaje", "cita": "la nena tiene el alambre q le pincha"})
DERIVA = "Le paso con la secretaria para que lo atienda."
MS = lambda iso: int(datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)
PROP_VIEJA = {"id": f"{TEL}-1", "tipo": "cambio", "estado": "pendiente", "creada_ms": MS("2026-10-05T12:30:00Z"), "exec_id": "ex-anterior", "tel": TEL, "paciente_id": 651,
              "slot": {"fecha": "2026-10-22", "hora": "09:20"}, "cita_vieja": {"id": 9104, "fecha": "2026-10-16", "hora": "09:10"}, "readback_text": RB, "enviada": True}
H_RB = [{"message": {"type": "ai", "content": RB, "additional_kwargs": {"source": "asiri_v7"}}, "created_at": "2026-10-05T12:30:00Z"}]


def orq(*pasos):
    return {"text": json.dumps({"pasos": list(pasos)}, ensure_ascii=False)}


def sub(agente, texto="", estado="respondido", **x):
    base = {"agente": agente, "texto": texto, "estado": estado, "codigo": "[LISTO]", "herramientas": [], "traza": [], "fuera_de_alcance": False, "urgencia": False, "derivar": None, "error_tecnico": False}
    base.update(x)
    return base


T_RB = sub("turnos", RB, "readback_pendiente", readback=True, traza=[{"tool": "gestionar_turno", "input": {"tipo": "cambio"}, "obs": "{\"etapa\":\"confirmacion\"}"}])
T_OK = sub("turnos", EXITO, "escrito_ok", traza=[{"tool": "gestionar_turno", "input": {"confirma": "true"}, "obs": "{\"etapa\":\"ejecutado\",\"ok\":true}"}])
P_DAT = sub("pagos", "Le paso los datos para transferir:", "datos_enviados", datos_pago=True)
I_PRECIO = sub("informacion", "La primera consulta tiene un valor de $50.000.")
U_OK = sub("urgencias", "", "derivado", codigo="[NO_REPLY]")


def esc(id_, orquestador, texto="Hola", redis=None, pg=None, modo="vivo", subwf=None, **extra):
    trig = {"phone": TEL, "texto": texto, "pushName": "CELE", "modo": modo, "historial_json": "", **(extra.pop("trigger", {}))}
    sw = {"Identificar paciente": IDENT, "Derivar a secretaria": {"ok": True, "derivado": True, "texto_para_el_paciente": DERIVA},
          "Pasar a humano": {"ok": True, "humano": True, "texto_para_el_paciente": DERIVA}, **(subwf or {})}
    pg_ = {"Historial": [{}], "Recordatorios": [{}], "Primer mensaje": [{}], "Datos del consultorio": KB, "Guardar en memoria": {}, **(pg or {})}
    return {"id": id_, "trigger": trig, "ahora": AHORA, "exec_id": EXEC, "redis": redis or {}, "pg": pg_, "subwf": sw, "llm": {"Orquestador": orquestador}, **extra}


def correr(wf, escenarios):
    with tempfile.TemporaryDirectory() as d:
        w, e = os.path.join(d, "wf.json"), os.path.join(d, "e.json")
        json.dump(wf, open(w, "w", encoding="utf-8"), ensure_ascii=True)
        json.dump(escenarios, open(e, "w", encoding="utf-8"), ensure_ascii=True)
        p = subprocess.run(["node", os.path.join(ROOT, "tests", "harness_grafo.mjs"), w, e], capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit("node fallo: " + p.stderr[-2500:])
        return {r["id"]: r for r in json.loads(p.stdout)}


def llamados(a, nodo):
    return [p for p in a["pedidos"] if p["nodo"] == nodo]


def mem(a):
    m = llamados(a, "Guardar en memoria")
    return (json.loads(m[0]["params"][1]), json.loads(m[0]["params"][2])) if m else (None, None)


def main():
    wf = B.wf_cerebro()
    nodos = {n["name"]: n for n in wf["nodes"]}
    txt = json.dumps(wf, ensure_ascii=False)

    print("ESTRUCTURA")
    chequear("E1 sin desvíos por regex: no hay IF de cierre, de 'sí directo' ni de bienvenida, ni nodos 'Bienvenida' / 'Sí directo' / 'Cierre'",
             not any(k in nodos for k in ("¿Es un cierre?", "¿Sí a la confirmación?", "¿Es una bienvenida?", "Bienvenida", "Sí directo", "Gestionar (sí directo)", "Cierre sin respuesta")), list(nodos))
    chequear("E2 (estático) ninguna función de juicio de intención vuelve al cerebro: esAfirmacion, siDirecto, esCierre, esSaludo, esPedidoInfo, ultimoPideRespuesta, VERIF, veto de dólares sobre el texto",
             not re.search(r"esAfirmacion|siDirecto|siALaConfirmacion|esCierre|esSaludo|esPedidoInfo|ultimoPideRespuesta|VERIF\.|test\(String\(e\.texto|DIJO_AVISO|RE_PRESENTA|RE_DECILE", txt))
    orq_n = nodos["Orquestador"]
    chequear("E3 el ORQUESTADOR es UNA llamada al modelo (sin herramientas): no puede tocar la agenda ni escribirle al paciente",
             orq_n["type"].endswith("chainLlm") and not any("Orquestador" in [d["node"] for d in v.get("ai_tool", [[]])[0]] for v in wf["connections"].values()), orq_n["type"])
    chequear("E4 el orquestador usa gpt-5-mini con razonamiento medio (20/10: con 'low' ruteaba mal pedidos múltiples en vivo)", nodos["Modelo Orquestador"]["parameters"]["model"]["value"] == "gpt-5-mini" and nodos["Modelo Orquestador"]["parameters"]["options"]["reasoningEffort"] == "medium")
    for clave, nodo in C.SUBAGENTES:
        v = nodos[nodo]["parameters"]["workflowInputs"]["value"]
        chequear(f"E5 {nodo}: recibe la ejecución del CEREBRO, teléfono, modo explícito, mensaje, último Asiri, mensajes del paciente, contexto y pedido (lo pone el código)",
                 v["exec_id_actual"] == "={{ $execution.id }}" and "phone" in v["tel"] and "'vivo' : 'sombra'" in v["modo"] and all(k in v for k in ("texto_paciente", "ultimo_asiri", "textos_paciente", "contexto", "pedido")), v)
        chequear(f"E6 {nodo}: los DATOS del consultorio solo van a Información", ("datos_info" in v["datos"]) == (clave == "informacion"), v["datos"])
        chequear(f"E6b {nodo}: llama a su workflow por id a resolver (@@ID:agente_{clave}@@)", nodos[nodo]["parameters"]["workflowId"]["value"] == f"@@ID:agente_{clave}@@")
    for n in ("Derivar a secretaria", "Pasar a humano"):
        v = nodos[n]["parameters"]["workflowInputs"]["value"]
        chequear(f"E7 {n}: acción fija por código y modo explícito (C10/C11)", v["accion"] in ("={{ 'derivar' }}", "={{ 'humano' }}") and "'vivo' : 'sombra'" in v["modo"], v)
    ids = set(re.findall(r"@@ID:([a-z_]+)@@", txt))
    chequear("E8 ids a resolver: ver_turnos, clinica y los 4 sub-agentes (nada de Dentalink directo)", ids == {"ver_turnos", "clinica", "agente_turnos", "agente_pagos", "agente_informacion", "agente_urgencias"}, sorted(ids))
    chequear("E9 ningún workflow generado lleva claves ni tokens escritos", not any(s in txt for s in ("sb_secret", "Bearer ", "apikey", "Token ")))

    R = correr(wf, [
        esc("Z1 saludo en conversación nueva", orq({"a": "menu_bienvenida"}), texto="hola doc buenas tardes q tal"),
        esc("Z2 sombra: saludo", orq({"a": "menu_bienvenida"}), texto="Hola", modo="sombra"),
        esc("Z3 'ola kiero turno pal jueves'", orq({"a": "turnos", "pedido": "quiere turno para el jueves 8/10"}), texto="ola kiero turno pal jueves", subwf={"Agente Turnos": sub("turnos", BLOQUE, "bloque_ofrecido")},
            redis={f"ofertas:{TEL}": OFERTAS, f"bloque:{TEL}": BLOQUE, f"bloque_exec:{TEL}:{EXEC}": BLOQUE}),
        esc("Z4 cambiar turno y pasame el alias (multi-pedido)", orq({"a": "turnos", "pedido": "cambiar el turno del jueves 22 a las 9:20"}, {"a": "pagos", "pedido": "pide el alias"}),
            texto="kiero pasar el turno al jueves 22 9:20 y pasame el alia", subwf={"Agente Turnos": T_RB, "Agente Pagos": P_DAT},
            redis={f"ofertas:{TEL}": OFERTAS, f"turnos_vistos:{TEL}": VISTOS, f"propuesta:{TEL}": json.dumps({**PROP_VIEJA, "exec_id": EXEC, "enviada": False})}),
        esc("Z5 'ya' con confirmación pendiente; el orquestador dice no_reply", orq({"a": "no_reply"}), texto="ya", subwf={"Agente Turnos": T_OK},
            redis={f"propuesta:{TEL}": json.dumps(PROP_VIEJA), f"escrituras:{TEL}:{EXEC}": LIBRO_OK, f"turnos_vistos:{TEL}": VISTOS}, pg={"Historial": H_RB}),
        esc("Z6 'ok, lo pienso' con confirmación pendiente", orq({"a": "turnos", "pedido": "responde a la confirmación pendiente"}), texto="ok, lo pienso", subwf={"Agente Turnos": sub("turnos", "", "no_reply", codigo="[NO_REPLY]")},
            redis={f"propuesta:{TEL}": json.dumps(PROP_VIEJA)}, pg={"Historial": H_RB}),
        esc("Z7 la nena tiene el alambre q le pincha", orq({"a": "urgencias", "pedido": "a la hija le pincha el alambre"}), texto="la nena tiene el alambre q le pincha", subwf={"Agente Urgencias": U_OK},
            redis={f"triaje_v7:{TEL}:{EXEC}": TRIAJE}),
        esc("Z8 (U3) sí, cámbielo; ah y se me salió el alambre", orq({"a": "urgencias", "pedido": "se le salió el alambre"}, {"a": "turnos", "pedido": "responde a la confirmación pendiente"}), texto="si cambielo. ah y se me salio el alambre",
            subwf={"Agente Urgencias": U_OK, "Agente Turnos": T_OK}, redis={f"propuesta:{TEL}": json.dumps(PROP_VIEJA), f"escrituras:{TEL}:{EXEC}": LIBRO_OK, f"triaje_v7:{TEL}:{EXEC}": TRIAJE}, pg={"Historial": H_RB}),
        esc("Z9 Turnos ve una urgencia que el orquestador no vio", orq({"a": "turnos", "pedido": "quiere cambiar el turno"}), texto="mi hija esta incomoda, no come, quiero cambiar el turno",
            subwf={"Agente Turnos": sub("turnos", "", "nada", codigo="URGENCIA", urgencia=True), "Agente Urgencias": U_OK}, redis={f"triaje_v7:{TEL}:{EXEC}": json.dumps({"motivo": "derivar_triaje", "cita": "mi hija esta incomoda, no come"})}),
        esc("Z10 fuera de alcance: presupuesto en dólares", orq({"a": "derivar_secretaria", "cita": "cuanto sale en dolares", "motivo": "presupuesto en dólares"}), texto="cuanto sale en dolares el tratamiento"),
        esc("Z11 Información devuelve FUERA_DE_ALCANCE", orq({"a": "informacion", "pedido": "presupuesto de su caso"}), texto="cuanto me sale lo mio",
            subwf={"Agente Información": sub("informacion", "", "fuera_de_alcance", fuera_de_alcance=True, codigo="FUERA_DE_ALCANCE")}),
        esc("Z12 que me atienda la seño", orq({"a": "pasar_a_humano", "cita": "que me atienda la seño"}), texto="que me atienda la seño"),
        esc("Z13 el orquestador escribe texto libre", {"text": "Hola! Claro, ya le agendo el jueves a las 10 😊"}, texto="quiero turno"),
        esc("Z14 2.º no_entendi seguido", orq({"a": "no_entendi"}), texto="asdf qwe", redis={f"noentendi:{TEL}": "1"}),
        esc("Z15 1.er no_entendi", orq({"a": "no_entendi"}), texto="asdf qwe"),
        esc("Z16 gracias (cierre)", orq({"a": "no_reply"}), texto="gracias mañana", pg={"Historial": [{"message": {"type": "ai", "content": "Su turno es el viernes 16/10 a las 09:10."}, "created_at": RECIENTE}]}),
        esc("Z17 Turnos se cae DESPUÉS de escribir (B7)", orq({"a": "turnos", "pedido": "responde a la confirmación pendiente"}), texto="dale", subwf={"Agente Turnos": {"error": {"message": "max iterations"}}},
            redis={f"propuesta:{TEL}": json.dumps(PROP_VIEJA), f"escrituras:{TEL}:{EXEC}": LIBRO_OK}, pg={"Historial": H_RB}),
        esc("Z18 historial_json + recordatorio (sombra retrospectiva)", orq({"a": "informacion", "pedido": "precio"}), texto="cuanto sale la consulta", modo="sombra", subwf={"Agente Información": I_PRECIO},
            trigger={"historial_json": json.dumps([{"message": {"type": "human", "content": "Hola, mi DNI es 35.123.456"}}, {"message": {"type": "ai", "content": "Hola"}}])},
            pg={"Recordatorios": [{"id_cita_dentalink": 9104, "fecha_turno": "2026-10-16", "hora_turno": "09:10:00"}]}),
        esc("Z19 sombra: derivar y no_entendi van a claves v7s:", orq({"a": "no_entendi"}), texto="?", modo="sombra", redis={f"v7s:noentendi:{TEL}": "1"}),
        esc("Z20 confirmación guardada pero el último mensaje de Asiri es otro (no la vio)", orq({"a": "no_reply"}), texto="ok", redis={f"propuesta:{TEL}": json.dumps(PROP_VIEJA)},
            pg={"Historial": [{"message": {"type": "ai", "content": "Su turno es el viernes 16/10 a las 09:10."}, "created_at": RECIENTE}]}),
        esc("Z21 precio en conversación nueva", orq({"a": "informacion", "pedido": "precio de la consulta"}), texto="cuanto sale la consulta", subwf={"Agente Información": I_PRECIO}),
        esc("Z22 reserva hecha en este mensaje", orq({"a": "turnos", "pedido": "responde a la confirmación pendiente"}), texto="sisi porfa",
            subwf={"Agente Turnos": sub("turnos", "Listo, le reservé el jueves 22/10 a las 09:20.", "escrito_ok")}, pg={"Historial": H_RB},
            redis={f"propuesta:{TEL}": json.dumps({**PROP_VIEJA, "tipo": "reserva"}), f"escrituras:{TEL}:{EXEC}": json.dumps([{"ok": True, "tipo": "reserva", "primera_consulta": True, "readback_text": "Listo, le reservé el jueves 22/10 a las 09:20."}])}),
        esc("Z23 Turnos (por error) afirma algo sin escritura", orq({"a": "turnos", "pedido": "cambiar"}), texto="cambielo", subwf={"Agente Turnos": sub("turnos", "Listo, quedó reprogramado su turno para el jueves 22/10 a las 09:20.")},
            redis={f"ofertas:{TEL}": OFERTAS, f"turnos_vistos:{TEL}": VISTOS}),
        esc("Z24 urgencia que no se pudo derivar", orq({"a": "urgencias", "pedido": "dolor"}), texto="me duele mucho la muela", subwf={"Agente Urgencias": sub("urgencias", "", "derivar_fallo", codigo=None)}),
        esc("Z25 audio", orq({"a": "pedir_texto"}), texto="[audio]"),
        # (21/10) respuesta a un recordatorio que el orquestador tomó por cierre ("dale gracias 👍"): Turnos igual la ve por ESTADO
        esc("Z28 'dale gracias' a un recordatorio", orq({"a": "no_reply"}), texto="dale gracias 👍",
            subwf={"Agente Turnos": sub("turnos", "Perfecto, quedaron confirmados sus turnos del viernes 23/10 a las 09:50 (Pedro) y viernes 23/10 a las 10:30 (Hilario).", "confirmado")},
            pg={"Historial": [{"message": json.dumps({"type": "ai", "content": "✨ ÁUREA ✨ Le recordamos su turno… responda CONFIRMO.", "additional_kwargs": {"source": "reminder_note"}}), "created_at": "2026-10-05T11:30:00Z"}],
                "Recordatorios": [{"id_cita_dentalink": 9116, "fecha_turno": "2026-10-23", "hora_turno": "09:50:00"}, {"id_cita_dentalink": 9120, "fecha_turno": "2026-10-23", "hora_turno": "10:30:00"}]}),
        esc("Z28b 'gracias' sin recordatorio de por medio", orq({"a": "no_reply"}), texto="gracias"),
        # (20/10, panel Conocimiento) una entrada que la clínica marcó "Asiri puede decírselo a los pacientes" le llega a Información
        esc("Z27 entrada marcada por la clínica", orq({"a": "informacion", "pedido": "hacen blanqueamiento?"}), texto="hacen blanqueamiento?", subwf={"Agente Información": I_PRECIO},
            pg={"Datos del consultorio": KB + [{"id": "asiri:50", "contenido": "La clínica hace blanqueamiento dental con turno previo."}]}),
        # (20/10, D3) charla que inició la clínica con un contacto SIN ficha (plomero de las escalaciones 384/385)
        esc("Z26 charla de la clínica, sin ficha", orq({"a": "derivar_secretaria", "cita": "Yo por la tarde puedo pasar", "motivo": "proveedor: grifo"}), texto="Yo por la tarde puedo pasar",
            subwf={"Identificar paciente": {"ok": False, "motivo": "sin_ficha"}}, pg={"Primer mensaje": [{"fuente": "wa_outbound", "tipo": "ai"}]}),
        esc("Z26b sin ficha pero escribió él primero", orq({"a": "derivar_secretaria", "cita": "Yo por la tarde puedo pasar", "motivo": "proveedor: grifo"}), texto="Yo por la tarde puedo pasar",
            subwf={"Identificar paciente": {"ok": False, "motivo": "sin_ficha"}}, pg={"Primer mensaje": [{"fuente": "wa_inbound", "tipo": "human"}]}),
        esc("Z26c la clínica escribió primero pero el contacto TIENE ficha", orq({"a": "derivar_secretaria", "cita": "x", "motivo": "x"}), texto="x",
            pg={"Primer mensaje": [{"fuente": "wa_outbound", "tipo": "ai"}]}),
    ])

    print("\nSALUDO, MENÚ y SOMBRA")
    a = R["Z1 saludo en conversación nueva"]["reps"][0]; s = a["salida"]
    O_MENU = None
    chequear("Z1 saludo → el menú (el del panel no respeta el alcance: va el de las funciones), sin llamar a ningún sub-agente", a["error"] is None and s["texto"].startswith("Hola! Soy Asiri") and "cuotas" not in s["texto"] and "Escriba el número" in s["texto"]
             and not any(p["nodo"].startswith("Agente ") for p in a["pedidos"]), (a["error"], s))
    h, ai = mem(a)
    chequear("Z1b memoria: un solo mensaje de Asiri con el texto final y source asiri_v7 (§3.2)", h and h["content"] == "hola doc buenas tardes q tal" and ai["content"] == s["texto"] and ai["additional_kwargs"]["source"] == "asiri_v7", (h, ai))
    orq_p = llamados(a, "Orquestador")[0]["entradas"]
    chequear("Z1c el orquestador recibe el contexto (fecha de Jujuy, pushName, CONVERSACIÓN NUEVA: sí, mensaje actual) y su prompt; NADA de datos bancarios",
             "FECHA Y HORA ACTUAL (Jujuy): lunes 2026-10-05 09:36" in orq_p["text"] and "CELE" in orq_p["text"] and "CONVERSACIÓN NUEVA (12 h sin mensajes): sí" in orq_p["text"] and orq_p["text"].endswith("MENSAJE ACTUAL DEL PACIENTE:\nhola doc buenas tardes q tal")
             and orq_p["sistema"] == C.PROMPT_ORQ and "dra.raquel.aurea" not in json.dumps(orq_p) and "Laura Raquel" not in json.dumps(orq_p), orq_p)
    a = R["Z2 sombra: saludo"]["reps"][0]
    chequear("Z2 sombra: sin memoria y sin avisos, igual devuelve el texto", not llamados(a, "Guardar en memoria") and not a["avisos"] and a["salida"]["texto"] and a["salida"]["modo"] == "sombra", (a["pedidos"], a["avisos"]))

    print("\nRUTEO y DESPACHO")
    a = R["Z3 'ola kiero turno pal jueves'"]["reps"][0]
    t = llamados(a, "Agente Turnos")
    chequear("Z3 turno → SOLO Turnos, una vez, con el pedido del orquestador, la ejecución del cerebro y modo explícito", len(t) == 1 and t[0]["entradas"]["pedido"] == "quiere turno para el jueves 8/10" and t[0]["entradas"]["exec_id_actual"] == EXEC
             and t[0]["entradas"]["modo"] == "vivo" and t[0]["entradas"]["tel"] == TEL and not llamados(a, "Agente Pagos") and not llamados(a, "Agente Información"), t)
    chequear("Z3b el paciente recibe el bloque de la herramienta tal cual (con presentación: conversación nueva)", a["salida"]["texto"].endswith(BLOQUE) and a["salida"]["motivo_chequeo"] is None, a["salida"])
    chequear("Z3c Turnos recibe los mensajes del paciente (para verificar el DNI) y los turnos del celular", json.loads(t[0]["entradas"]["textos_paciente"])[-1] == "ola kiero turno pal jueves" and json.loads(t[0]["entradas"]["turnos_json"]) == ["viernes 16/10 a las 09:10"], t[0]["entradas"])
    x = R["Z4 cambiar turno y pasame el alias (multi-pedido)"]; a = x["reps"][0]; s = a["salida"]
    chequear("Z4 multi-pedido: Turnos y Pagos, uno cada uno", len(llamados(a, "Agente Turnos")) == 1 and len(llamados(a, "Agente Pagos")) == 1, [p["nodo"] for p in a["pedidos"]])
    chequear("Z4b orden fijo: Pagos (+ datos de la KB 24 pegados por código) antes, read-back de Turnos AL FINAL", s["texto"].endswith(RB) and s["texto"].index("Alias: dra.raquel.aurea") < s["texto"].index("Le confirmo") and "Titular: Laura Raquel Rodríguez" in s["texto"], s["texto"])
    chequear("Z4c la propuesta de ESTA ejecución queda 'enviada' (su read-back va en el mensaje)", json.loads(x["redis_final"][f"propuesta:{TEL}"])["enviada"] is True, x["redis_final"].get(f"propuesta:{TEL}"))
    chequear("Z4d la traza para el examen trae la decisión del orquestador y las herramientas de cada sub-agente", s["tools"][0]["tool"] == "orquestador" and any(tl.get("tool") == "gestionar_turno" and tl.get("agente") == "turnos" for tl in s["tools"]), s["tools"])

    print("\nEL 'SÍ' (B3: lo decide Turnos con el mensaje actual; llega a Turnos por ESTADO)")
    a = R["Z5 'ya' con confirmación pendiente; el orquestador dice no_reply"]["reps"][0]
    t = llamados(a, "Agente Turnos")
    chequear("Z5 confirmación pendiente vista: Turnos SÍ ve el mensaje aunque el orquestador dijo no_reply, y el paciente recibe el éxito", len(t) == 1 and t[0]["entradas"]["pedido"] == "responde a la confirmación pendiente" and a["salida"]["texto"] == EXITO, (t, a["salida"]))
    chequear("Z5b el contexto de Turnos trae la CONFIRMACIÓN PENDIENTE y el mensaje actual", "CONFIRMACIÓN PENDIENTE" in t[0]["entradas"]["contexto"] and "hace 6 min" in t[0]["entradas"]["contexto"] and t[0]["entradas"]["contexto"].endswith("MENSAJE ACTUAL DEL PACIENTE:\nya") and t[0]["entradas"]["ultimo_asiri"] == RB, t[0]["entradas"]["contexto"][-500:])
    x = R["Z6 'ok, lo pienso' con confirmación pendiente"]; a = x["reps"][0]
    # (20/10, BOT-01) antes: silencio. Ahora el paciente sabe que no se tocó nada (la propuesta se descarta igual, Z6c).
    chequear("Z6 'ok, lo pienso': Turnos no confirma → «no cambié nada: su turno queda como estaba» (sin escribir nada)",
             a["salida"]["silencio"] is False and a["salida"]["texto"] == "Perfecto, no cambié nada: su turno queda como estaba." and a["salida"]["descartar_propuesta"] is True, a["salida"])
    chequear("Z6c (15/10) la confirmación pendiente que no se ejecutó se DESCARTA: el próximo pedido vuelve a preguntar", a["salida"].get("descartar_propuesta") is True and f"propuesta:{TEL}" not in x["redis_final"], x["redis_final"].get(f"propuesta:{TEL}"))
    x5 = R["Z5 'ya' con confirmación pendiente; el orquestador dice no_reply"]
    chequear("Z5c el 'sí' que SÍ se ejecutó no dispara el descarte", x5["reps"][0]["salida"].get("descartar_propuesta") is False, x5["reps"][0]["salida"].get("descartar_propuesta"))
    x20 = R["Z20 confirmación guardada pero el último mensaje de Asiri es otro (no la vio)"]
    chequear("Z20b confirmación que el paciente NO vio: no se toca", x20["reps"][0]["salida"].get("descartar_propuesta") is False and f"propuesta:{TEL}" in x20["redis_final"], x20["redis_final"].get(f"propuesta:{TEL}"))
    a = R["Z20 confirmación guardada pero el último mensaje de Asiri es otro (no la vio)"]["reps"][0]
    chequear("Z20 confirmación guardada que el paciente NO vio: no se fuerza Turnos (el ruteo por estado exige que la haya visto)", not llamados(a, "Agente Turnos") and a["salida"]["silencio"] is True, [p["nodo"] for p in a["pedidos"]])

    print("\nURGENCIAS")
    a = R["Z7 la nena tiene el alambre q le pincha"]["reps"][0]; s = a["salida"]
    chequear("Z7 urgencia: Urgencias derivó → v7 en silencio, derivar_triaje con la cita, sin memoria (la guarda el triaje) ni avisos propios", s["derivar_triaje"] is True and s["triaje"]["cita"] == "la nena tiene el alambre q le pincha" and s["enviar"] is False and s["texto"] is None and not llamados(a, "Guardar en memoria") and not a["avisos"], s)
    a = R["Z8 (U3) sí, cámbielo; ah y se me salió el alambre"]["reps"][0]; s = a["salida"]
    chequear("Z8 (U3) urgencia + cambio ok en el mismo mensaje: se cuenta el cambio y la urgencia va al grupo como [ACCIÓN URGENTE]", s["derivar_triaje"] is False and s["texto"] == EXITO and s["enviar"] is True and any(v["qs"]["resumen"].startswith("[ACCIÓN URGENTE]") for v in a["avisos"]), (s, a["avisos"]))
    a = R["Z9 Turnos ve una urgencia que el orquestador no vio"]["reps"][0]
    u = llamados(a, "Agente Urgencias")
    chequear("Z9 (B4 capa b) Turnos marcó URGENCIA → el código llama a Urgencias aunque el orquestador no lo hizo; caso Mariela", len(u) == 1 and "turnos" in u[0]["entradas"]["pedido"] and a["salida"]["derivar_triaje"] is True, (u, a["salida"]))
    a = R["Z24 urgencia que no se pudo derivar"]["reps"][0]
    chequear("Z24 urgencia sin derivar: frase fija «Le paso su mensaje a la doctora…» + [ACCIÓN URGENTE]", a["salida"]["texto"].endswith("Le paso su mensaje a la doctora para que lo vea.") and any(v["qs"]["resumen"].startswith("[ACCIÓN URGENTE]") for v in a["avisos"]), (a["salida"], a["avisos"]))

    print("\nFUERA DE ALCANCE, PERSONA, NO ENTENDÍ, AUDIO")
    a = R["Z10 fuera de alcance: presupuesto en dólares"]["reps"][0]
    d = llamados(a, "Derivar a secretaria")
    chequear("Z10 derivar_secretaria: la herramienta de clínica con acción 'derivar', la frase del paciente y modo vivo; el texto fijo", len(d) == 1 and d[0]["entradas"]["accion"] == "derivar" and d[0]["entradas"]["cita_textual"] == "cuanto sale en dolares" and d[0]["entradas"]["modo"] == "vivo"
             and a["salida"]["texto"].endswith(DERIVA) and not any(p["nodo"].startswith("Agente ") for p in a["pedidos"]), (d, a["salida"]))
    a = R["Z11 Información devuelve FUERA_DE_ALCANCE"]["reps"][0]
    d = llamados(a, "Derivar a secretaria")
    chequear("Z11 un sub-agente FUERA_DE_ALCANCE → el código deriva (una vez), con la frase del paciente; no sale nada del sub-agente", len(d) == 1 and d[0]["entradas"]["cita_textual"] == "cuanto me sale lo mio" and a["salida"]["texto"].endswith(DERIVA), (d, a["salida"]))
    a = R["Z12 que me atienda la seño"]["reps"][0]
    hh = llamados(a, "Pasar a humano")
    chequear("Z12 pidió una persona: 'humano' con la cita; texto fijo; ningún sub-agente", len(hh) == 1 and hh[0]["entradas"]["accion"] == "humano" and hh[0]["entradas"]["cita_textual"] == "que me atienda la seño" and a["salida"]["texto"].endswith(DERIVA) and not any(p["nodo"].startswith("Agente ") for p in a["pedidos"]), (hh, a["salida"]))
    a = R["Z13 el orquestador escribe texto libre"]["reps"][0]
    chequear("Z13 el texto libre del orquestador se descarta: sale el texto honesto + [ACCIÓN]; nada de 'le agendo el jueves'", "agendo" not in a["salida"]["texto"] and "inconveniente" in a["salida"]["texto"] and a["salida"]["fallo_agente"] is True and any(v["qs"]["resumen"].startswith("[ACCIÓN]") for v in a["avisos"]), (a["salida"], a["avisos"]))
    x = R["Z15 1.er no_entendi"]; a = x["reps"][0]
    chequear("Z15 1.er no_entendi: repregunta fija (sin ofrecer urgencias) y cuenta noentendi:{tel}", "no le entendí" in a["salida"]["texto"] and "urgencia" not in a["salida"]["texto"] and str(x["redis_final"].get(f"noentendi:{TEL}")) == "1" and not llamados(a, "Derivar a secretaria"), (a["salida"], x["redis_final"]))
    a = R["Z14 2.º no_entendi seguido"]["reps"][0]
    chequear("Z14 2.º no_entendi en 30 min → derivar a la secretaria", len(llamados(a, "Derivar a secretaria")) == 1 and a["salida"]["texto"].endswith(DERIVA), a["salida"])
    x = R["Z19 sombra: derivar y no_entendi van a claves v7s:"]; a = x["reps"][0]
    d = llamados(a, "Derivar a secretaria")
    chequear("Z19 sombra: el contador va a v7s:noentendi: (no a la clave de vivo) y la derivación recibe modo sombra (no silencia el chat real)", str(x["redis_final"].get(f"v7s:noentendi:{TEL}")) == "2" and f"noentendi:{TEL}" not in x["redis_final"] and len(d) == 1 and d[0]["entradas"]["modo"] == "sombra" and not a["avisos"], (x["redis_final"], d))
    a = R["Z25 audio"]["reps"][0]
    chequear("Z25 (B5) audio → frase fija pidiendo que lo escriba", a["salida"]["texto"].endswith("¿Me lo puede escribir, por favor?"), a["salida"])

    print("\nCIERRE, FALLAS, PRESENTACIÓN, DATOS DE PAGO, CHEQUEO")
    a = R["Z16 gracias (cierre)"]["reps"][0]
    chequear("Z16 'gracias' → silencio (lo decidió el orquestador), sin memoria", a["salida"]["silencio"] is True and a["salida"]["enviar"] is False and not llamados(a, "Guardar en memoria"), a["salida"])
    a = R["Z17 Turnos se cae DESPUÉS de escribir (B7)"]["reps"][0]
    chequear("Z17 (B7) Turnos se cayó después de escribir: el paciente recibe el éxito del libro, no un error", a["salida"]["texto"] == EXITO and "inconveniente" not in a["salida"]["texto"], a["salida"])
    a = R["Z18 historial_json + recordatorio (sombra retrospectiva)"]["reps"][0]
    o = llamados(a, "Orquestador")[0]["entradas"]["text"]; i = llamados(a, "Agente Información")[0]["entradas"]
    chequear("Z18 con historial_json usa ese historial; el recordatorio entra sin pedir confirmación", "PACIENTE: Hola, mi DNI es 35.123.456" in o and "RECORDATORIOS YA ENVIADOS (sin respuesta; NO le pidas que confirme" in o, o)
    chequear("Z18b los mensajes del paciente (para verificar el DNI) salen del MISMO historial (historial_json), no de la base", "Hola, mi DNI es 35.123.456" in json.loads(i["textos_paciente"]), i["textos_paciente"])
    chequear("Z18c Información recibe los DATOS (precio, obra social) SIN los datos bancarios, y las notas del panel solo como tono", "$50.000" in i["datos"] and "No trabajamos con ninguna obra social" in i["datos"] and "dra.raquel.aurea" not in i["datos"] and "Laura Raquel" not in i["datos"] and "nunca agregan temas" in i["datos"] and "Hablar con calidez" in i["datos"], i["datos"])
    a = R["Z21 precio en conversación nueva"]["reps"][0]
    chequear("Z21 Información en conversación nueva: se antepone «Soy Asiri…» por código", a["salida"]["texto"] == "Soy Asiri, la secretaria virtual de la Dra. Raquel.\n\nLa primera consulta tiene un valor de $50.000.", a["salida"]["texto"])
    a = R["Z22 reserva hecha en este mensaje"]["reps"][0]
    chequear("Z22 reserva de PRIMERA CONSULTA → pedido de pago + datos (como el v6), una sola vez", a["salida"]["texto"].startswith("Listo, le reservé") and "Para confirmarlo definitivamente" in a["salida"]["texto"] and a["salida"]["texto"].count("Alias:") == 1, a["salida"]["texto"])
    a = R["Z23 Turnos (por error) afirma algo sin escritura"]["reps"][0]
    chequear("Z23 el chequeo de salida corre sobre la parte de Turnos: una afirmación sin escritura se reemplaza por el texto honesto", a["salida"]["motivo_chequeo"] == "afirma_reprogramar_sin_ok" and "no quedó hecho" in a["salida"]["texto"], a["salida"])
    a = R["Z28 'dale gracias' a un recordatorio"]["reps"][0]
    tt = llamados(a, "Agente Turnos")
    chequear("Z28 respuesta a un recordatorio que el orquestador tomó por cierre: Turnos la ve (pedido 'responde al recordatorio') y el paciente recibe la confirmación",
             len(tt) == 1 and tt[0]["entradas"]["pedido"].startswith("responde al recordatorio") and "quedaron confirmados" in (a["salida"]["texto"] or ""), (tt[0]["entradas"]["pedido"] if tt else tt, a["salida"].get("texto")))
    a = R["Z28b 'gracias' sin recordatorio de por medio"]["reps"][0]
    chequear("Z28b sin recordatorio pendiente un 'gracias' sigue en silencio y no llama a Turnos", a["salida"]["silencio"] is True and not llamados(a, "Agente Turnos"), a["salida"])
    a = R["Z27 entrada marcada por la clínica"]["reps"][0]
    ti = llamados(a, "Agente Información")
    chequear("Z27 la entrada marcada en el panel (metadata.asiri) llega a Información como DATO del consultorio",
             len(ti) == 1 and "- La clínica hace blanqueamiento dental con turno previo." in ti[0]["entradas"]["datos"], ti[0]["entradas"]["datos"][-300:] if ti else ti)
    a = R["Z26 charla de la clínica, sin ficha"]["reps"][0]
    chequear("Z26 charla que inició la clínica con un contacto sin ficha: silencio, NO llama a Derivar a secretaria (sin aviso al grupo)",
             a["salida"]["silencio"] is True and not a["salida"]["texto"] and not llamados(a, "Derivar a secretaria"), (a["salida"], llamados(a, "Derivar a secretaria")))
    a = R["Z26b sin ficha pero escribió él primero"]["reps"][0]
    chequear("Z26b si el contacto escribió primero (lead nuevo), se atiende como siempre: deriva", bool(llamados(a, "Derivar a secretaria")) and a["salida"]["texto"], a["salida"])
    a = R["Z26c la clínica escribió primero pero el contacto TIENE ficha"]["reps"][0]
    chequear("Z26c paciente con ficha: aunque la clínica haya escrito primero, se atiende como siempre", bool(llamados(a, "Derivar a secretaria")), a["salida"])

    # (28/10) AUDIOS. Caso real 27/10 12:18: audio transcripto ("…la tomografía con o sin braquets?") y Asiri contestó "no puedo escuchar audios".
    print("AUDIOS")
    AUD = "[AUDIO] Hola Iris, ¿le puede preguntar a la doctora si la tomografía la tengo que hacer con o sin los braquets? [MEDIA:633cc86]"
    AU = correr(wf, [
        esc("AU-G1 audio transcripto y el orquestador pide texto", orq({"a": "pedir_texto"}), texto=AUD),
        esc("AU-G2 audio SIN transcripción (solo el marcador de media)", orq({"a": "pedir_texto"}), texto="[AUDIO] [MEDIA:633cc86]"),
        esc("AU-G3 audio con el orquestador bien ruteado", orq({"a": "derivar_secretaria", "cita": "pregunta por la tomografía con o sin braquets", "motivo": "consulta clínica"}), texto=AUD),
    ])
    a = AU["AU-G1 audio transcripto y el orquestador pide texto"]["reps"][0]
    chequear("AU-G1 se deriva (no le dice que no puede escuchar) y la secretaria recibe lo que dijo", bool(llamados(a, "Derivar a secretaria")) and "escuchar" not in a["salida"]["texto"]
             and "tomograf" in json.dumps(llamados(a, "Derivar a secretaria"), ensure_ascii=False).lower(), (a["salida"]["texto"], llamados(a, "Derivar a secretaria")))
    a = AU["AU-G2 audio SIN transcripción (solo el marcador de media)"]["reps"][0]
    chequear("AU-G2 si no hubo transcripción, pide que lo escriba (y no deriva)", "audio" in a["salida"]["texto"].lower() and not llamados(a, "Derivar a secretaria"), a["salida"]["texto"])
    a = AU["AU-G3 audio con el orquestador bien ruteado"]["reps"][0]
    chequear("AU-G3 si el orquestador ya derivó bien, sigue igual (una sola derivación)", len(llamados(a, "Derivar a secretaria")) == 1 and "escuchar" not in a["salida"]["texto"], a["salida"]["texto"])

    # (28/10) Auditoría v6->v7: audio con texto escrito ANTES (buffer de 22 s), comprobante forzado a Pagos y agente "payments".
    print("AUDITORIA v6->v7")
    COMPROB = "[IMAGEN] TIPO: COMPROBANTE | MONTO: 50000 | DESTINATARIO: Laura Raquel Rodriguez | FECHA: 27/10/2026 | HORA: 09:17 | DESCRIPCION: Comprobante de transferencia"
    P_COMP = sub("pagos", "Recibido. Dejé anotado su aviso de pago.", "pago_registrado")
    AX = correr(wf, [
        esc("AX-1 audio con texto antes y el orquestador pide texto", orq({"a": "pedir_texto"}), texto="hola buenas\n" + AUD),
        esc("AX-2 comprobante: el orquestador manda solo a Turnos", orq({"a": "turnos", "pedido": "responde al recordatorio"}), texto=COMPROB,
            subwf={"Agente Turnos": sub("turnos", "", "no_reply", codigo="[NO_REPLY]"), "Agente Pagos": P_COMP}),
        esc("AX-3 el orquestador devuelve el agente payments", orq({"a": "payments", "pedido": "comprobante de pago"}), texto=COMPROB, subwf={"Agente Pagos": P_COMP}),
        esc("AX-4 texto normal: no se fuerza Pagos", orq({"a": "informacion", "pedido": "precio"}), texto="cuanto sale la consulta", subwf={"Agente Información": I_PRECIO}),
    ])
    a = AX["AX-1 audio con texto antes y el orquestador pide texto"]["reps"][0]
    chequear("AX-1 un audio transcripto detrás de un texto previo también se deriva (no 'no pude escuchar')", bool(llamados(a, "Derivar a secretaria")) and "escuchar" not in a["salida"]["texto"], a["salida"]["texto"])
    a = AX["AX-2 comprobante: el orquestador manda solo a Turnos"]["reps"][0]
    chequear("AX-2 el comprobante marcado entra a Pagos por código aunque el orquestador solo eligió Turnos", len(llamados(a, "Agente Pagos")) == 1 and "Recibido" in a["salida"]["texto"], (a["salida"]["texto"], len(llamados(a, "Agente Pagos"))))
    a = AX["AX-3 el orquestador devuelve el agente payments"]["reps"][0]
    chequear("AX-3 'payments' llega al agente Pagos (una sola vez)", len(llamados(a, "Agente Pagos")) == 1 and "Recibido" in a["salida"]["texto"], (a["salida"]["texto"], len(llamados(a, "Agente Pagos"))))
    a = AX["AX-4 texto normal: no se fuerza Pagos"]["reps"][0]
    chequear("AX-4 un mensaje sin comprobante no llama a Pagos", len(llamados(a, "Agente Pagos")) == 0, len(llamados(a, "Agente Pagos")))

    # (28/10) MENSAJES FIJOS EDITABLES desde el panel: filas dir:msg_<CLAVE> de agente_directrices → el paciente lee las palabras de la clínica.
    print("MENSAJES FIJOS EDITABLES")
    NE_NUEVO = "Perdón, no logré entender. ¿Podría escribirlo con otras palabras? Le ayudo con turnos, pagos o información."
    PRES_NUEVA = "Hola, soy Asiri, la asistente virtual de la Dra. Raquel."
    DERIVA_NUEVA = "Enseguida le aviso a la secretaria para que se comunique con usted."
    kb_msg = lambda **m: KB + [{"id": f"dir:msg_{k}", "contenido": v} for k, v in m.items()]
    M = correr(wf, [
        esc("MF-A no entendí + presentación editados", orq({"a": "no_entendi"}), texto="asdf qwe", pg={"Datos del consultorio": kb_msg(NO_ENTENDI=NE_NUEVO, PRESENTACION=PRES_NUEVA)}),
        esc("MF-B mensaje inválido en la base", orq({"a": "no_entendi"}), texto="asdf qwe", pg={"Datos del consultorio": kb_msg(NO_ENTENDI="ok")}),
        esc("MF-C mensaje vacío en la base", orq({"a": "no_entendi"}), texto="asdf qwe", pg={"Datos del consultorio": kb_msg(NO_ENTENDI="")}),
        esc("MF-D derivación editada", orq({"a": "derivar_secretaria", "cita": "cuanto sale en dolares", "motivo": "presupuesto en dólares"}), texto="cuanto sale en dolares el tratamiento",
            pg={"Datos del consultorio": kb_msg(DERIVA=DERIVA_NUEVA)}),
        esc("MF-E sin ninguna fila msg_", orq({"a": "no_entendi"}), texto="asdf qwe"),
    ])
    a = M["MF-A no entendí + presentación editados"]["reps"][0]
    chequear("MF-A el paciente lee la presentación y el 'no entendí' de la clínica (no los estándar)", a["salida"]["texto"] == PRES_NUEVA + "\n\n" + NE_NUEVO, a["salida"]["texto"])
    chequear("MF-A2 lo que se guarda en memoria es lo que el paciente vio (así el corte de bucle compara bien la próxima vez)", mem(a)[1] is not None and mem(a)[1]["content"] == a["salida"]["texto"], mem(a))
    a = M["MF-B mensaje inválido en la base"]["reps"][0]
    chequear("MF-B un texto inválido se ignora: sale el estándar y no se rompe nada", "Disculpe, no le entendí bien" in a["salida"]["texto"] and "ok" != a["salida"]["texto"].strip(), a["salida"]["texto"])
    a = M["MF-C mensaje vacío en la base"]["reps"][0]
    chequear("MF-C una fila vacía = usar el estándar", "Disculpe, no le entendí bien" in a["salida"]["texto"], a["salida"]["texto"])
    a = M["MF-D derivación editada"]["reps"][0]
    chequear("MF-D la derivación que arma la herramienta de clínica sale con las palabras de la clínica", DERIVA_NUEVA in a["salida"]["texto"] and DERIVA not in a["salida"]["texto"], a["salida"]["texto"])
    a = M["MF-E sin ninguna fila msg_"]["reps"][0]
    chequear("MF-E sin filas msg_ (hoy, en producción) todo sale exactamente igual que antes", "Disculpe, no le entendí bien" in a["salida"]["texto"] and "Soy Asiri, la secretaria virtual de la Dra. Raquel." in a["salida"]["texto"], a["salida"]["texto"])
    chequear("MF-F el cerebro lee las filas msg_ de la base (consulta SQL) y las pasa al armado final", "left(clave, 4) = 'msg_'" in txt and "mensajes: ctx.mensajes" in txt)

    print(f"\n{total - fallas}/{total} {'TODO OK' if not fallas else str(fallas) + ' FALLAS'}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
