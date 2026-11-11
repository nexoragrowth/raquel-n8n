# -*- coding: utf-8 -*-
"""
test_v7_cerebro_agente.py — "v7 Cerebro Agente": el orquestador es un AGENTE de n8n con los sub-agentes como HERRAMIENTAS. Grafo nodo por nodo, sin red.
El agente (IA) se simula con su salida ({output, intermediateSteps}); los sub-workflows forzados por código, con lo que devuelven. Se prueba TODO lo que hace el código
alrededor: estructura (herramientas conectadas ai_tool, mismas salidas que el cerebro actual, nada que escriba la agenda fuera de las herramientas), silencio, respuesta
normal, respaldo, comprobante forzado, confirmación pendiente por estado, staff reciente, charla de la clínica, urgencias, sombra y memoria.
Estilo y asserts como tests/test_v7_cerebro.py (del que se reusan los datos de escenario).
USO:  python tests/test_v7_cerebro_agente.py
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.stdout.reconfigure(encoding="utf-8")
import build_v7_workflows as B  # noqa: E402
import v7_workflow_cerebro_agente as CA  # noqa: E402
import test_v7_cerebro as T  # noqa: E402  (datos de escenario y el harness: no corre su main)

AGENTE = CA.AGENTE
total = fallas = 0


def chequear(nombre, cond, extra=None):
    global total, fallas
    total += 1
    if not cond:
        fallas += 1
        print(f"  FALLA {nombre}" + (f" → {json.dumps(extra, ensure_ascii=False)[:700]}" if extra is not None else ""))
    else:
        print(f"  ok    {nombre}")


def paso(tool, obs, entrada=None):
    return {"action": {"tool": tool, "toolInput": entrada or {}}, "observation": json.dumps(obs, ensure_ascii=False)}


def ag(texto, *pasos):
    return {"output": texto, "intermediateSteps": list(pasos)}


def sub(agente, texto="", estado="respondido", **x):
    return T.sub(agente, texto, estado, **x)


def esc(id_, agente, texto="Hola", **kw):
    """Escenario del cerebro agente: lo mismo que T.esc, pero el modelo simulado es el nodo 'Orquestador Agente'."""
    e = T.esc(id_, None, texto=texto, **kw)
    e["llm"] = {AGENTE: agente}
    return e


def llamados(a, nodo):
    return T.llamados(a, nodo)


PAGO_REC = sub("pagos", "Recibido. Dejé anotado su aviso de pago.", "pago_anotado")
DERIVAR_OK = {"ok": True, "derivado": True, "texto_para_el_paciente": T.DERIVA}
FILA_STAFF = lambda iso: [{"message": {"type": "ai", "content": "Hola! Ya te dejé reservado el jueves a las 10.", "additional_kwargs": {"source": "wa_outbound"}}, "created_at": iso}]
COMPROB = T.COMPROB if hasattr(T, "COMPROB") else "[IMAGEN] TIPO: COMPROBANTE | MONTO: 50000 | DESTINATARIO: Laura Raquel Rodriguez | FECHA: 27/10/2026 | HORA: 09:17 | DESCRIPCION: Comprobante de transferencia"


def main():
    wf = B.wf_cerebro_agente()
    nodos = {n["name"]: n for n in wf["nodes"]}
    txt = json.dumps(wf, ensure_ascii=False)
    viejo = B.wf_cerebro()

    print("ESTRUCTURA")
    chequear("E1 nombre del workflow y registro en el build (genera cerebro_agente.json)", wf["name"] == "v7 Cerebro Agente" and "cerebro_agente" in B.WORKFLOWS, wf["name"])
    chequear("E1b cerebro_agente.json generado en v7/workflows (mismos nodos que el generador)", os.path.exists(os.path.join(ROOT, "v7", "workflows", "cerebro_agente.json"))
             and [n["name"] for n in json.load(open(os.path.join(ROOT, "v7", "workflows", "cerebro_agente.json"), encoding="utf-8"))["nodes"]] == [n["name"] for n in wf["nodes"]])
    chequear("E1c el despliegue en n8n NO lo hace este cambio: cerebro_agente no está en crear_v7_en_n8n.py", "cerebro_agente" not in open(os.path.join(ROOT, "scripts", "crear_v7_en_n8n.py"), encoding="utf-8").read())
    ag_n = nodos[AGENTE]
    chequear("E2 'Orquestador Agente' es un AGENTE de n8n (con herramientas), no una cadena de una llamada", ag_n["type"].endswith(".agent") and ag_n["parameters"]["options"]["returnIntermediateSteps"] is True, ag_n["type"])
    herr = {k for k, v in wf["connections"].items() if any(d["node"] == AGENTE for d in v.get("ai_tool", [[]])[0])}
    chequear("E3 herramientas conectadas ai_tool al agente: turnos, pagos, informacion, urgencias, derivar_secretaria, pasar_a_humano, no_responder",
             herr == {"turnos", "pagos", "informacion", "urgencias", "derivar_secretaria", "pasar_a_humano", "no_responder"}, sorted(herr))
    chequear("E3b todas existen como nodos y son toolWorkflow (salvo no_responder, que es una herramienta de código que no toca nada)",
             all(nodos[h]["type"].endswith("toolWorkflow") for h in herr - {"no_responder"}) and nodos["no_responder"]["type"].endswith("toolCode") and "silencio" in nodos["no_responder"]["parameters"]["jsCode"]
             and not re.search(r"fetch|http|redis|require", nodos["no_responder"]["parameters"]["jsCode"], re.I))
    mod = nodos["Modelo Orquestador Agente"]["parameters"]
    chequear("E4 el modelo del generador (CA.MODELO) con razonamiento medio, conectado como ai_languageModel", mod["model"]["value"] == CA.MODELO and mod["options"]["reasoningEffort"] == "medium"
             and any(d["node"] == AGENTE for d in wf["connections"]["Modelo Orquestador Agente"]["ai_languageModel"][0]))
    chequear("E4b el agente tiene tope de vueltas (latencia y costo acotados)", ag_n["parameters"]["options"]["maxIterations"] == CA.MAX_ITER and CA.MAX_ITER <= 8, ag_n["parameters"]["options"])
    ids = set(re.findall(r"@@ID:([a-z_]+)@@", txt))
    chequear("E5 ids a resolver: los 4 sub-agentes, clinica y ver_turnos (los mismos que el cerebro actual; nada de Dentalink directo)", ids == {"ver_turnos", "clinica", "agente_turnos", "agente_pagos", "agente_informacion", "agente_urgencias"}
             and ids <= set(json.load(open(os.path.join(ROOT, "v7", "ids.json"), encoding="utf-8"))), sorted(ids))
    for clave in ("turnos", "pagos", "informacion", "urgencias"):
        n = nodos[clave]["parameters"]; v = n["workflowInputs"]["value"]
        chequear(f"E6 herramienta {clave}: llama a su sub-workflow, y teléfono / ejecución del CEREBRO / modo / mensaje / contexto son FIJOS (código); solo el pedido lo decide el agente",
                 n["workflowId"]["value"] == f"@@ID:agente_{clave}@@" and v["exec_id_actual"] == "={{ $execution.id }}" and "phone" in v["tel"] and "'vivo' : 'sombra'" in v["modo"]
                 and all(k in v for k in ("texto_paciente", "ultimo_asiri", "textos_paciente", "turnos_json", "contexto", "datos")) and "$fromAI('pedido'" in v["pedido"]
                 and ("datos_info" in v["datos"]) == (clave == "informacion"), v)
    for h, accion in (("derivar_secretaria", "derivar"), ("pasar_a_humano", "humano")):
        n = nodos[h]["parameters"]; v = n["workflowInputs"]["value"]
        chequear(f"E7 {h}: workflow clinica con acción fija '{accion}', modo explícito; cita y motivo del modelo", n["workflowId"]["value"] == "@@ID:clinica@@" and v["accion"] == "={{ '" + accion + "' }}"
                 and "'vivo' : 'sombra'" in v["modo"] and "$fromAI('cita_textual'" in v["cita_textual"] and "$fromAI('motivo'" in v["motivo"], v)
    chequear("E7b derivar_secretaria con la clínica reciente (< 6 h) corre en SOMBRA: no avisa al grupo ni silencia el chat", "staff_reciente === true ? 'sombra'" in nodos["derivar_secretaria"]["parameters"]["workflowInputs"]["value"]["modo"])
    chequear("E8 el agente NO tiene herramientas que escriban la agenda: ninguna llama a ejecutar_propuesta, gestionar_turno, confirmar_*, proponer ni a un http", not any(
        n["type"].endswith("httpRequest") or (n["type"].endswith(("executeWorkflow", "toolWorkflow")) and re.search(r"ejecutar_propuesta|gestionar_turno|confirmar_|proponer|buscar_horarios|elegir_ficha", json.dumps(n["parameters"]["workflowId"]))) for n in wf["nodes"]))
    chequear("E8b la única forma de escribir en la agenda sigue siendo dentro de los sub-agentes (en este grafo todo executeWorkflow/toolWorkflow va a los ids permitidos)", all(
        n["parameters"]["workflowId"]["value"].replace("@@", "").split(":")[1] in ("ver_turnos", "clinica", "agente_turnos", "agente_pagos", "agente_informacion", "agente_urgencias")
        for n in wf["nodes"] if n["type"].endswith(("executeWorkflow", "toolWorkflow"))))
    chequear("E8c las únicas escrituras de Redis/Postgres del cerebro son las del actual: hechos, propuesta enviada, borrar propuesta y guardar en memoria",
             {n["name"] for n in wf["nodes"] if (n["type"].endswith("redis") and n["parameters"]["operation"] in ("set", "delete", "incr", "push")) or (n["type"].endswith("postgres") and "INSERT" in n["parameters"]["query"].upper())}
             == {"Redis SET hechos", "Redis SET propuesta enviada", "Redis DEL propuesta", "Guardar en memoria"})
    chequear("E9 ningún workflow generado lleva claves ni tokens escritos", not any(s in txt for s in ("sb_secret", "Bearer ", "apikey", "Token ")))
    chequear("E10 mismo disparador y mismas entradas que el cerebro actual", nodos["Entrada"]["parameters"] == {n["name"]: n for n in viejo["nodes"]}["Entrada"]["parameters"])
    viejos = {n["name"]: n for n in viejo["nodes"]}
    for nombre in ("Historial", "Recordatorios", "Primer mensaje", "Datos del consultorio", "Identificar paciente", "Redis GET propuesta (entrada)", "Redis GET libro", "Redis GET hechos", "Redis SET hechos", "Guardar en memoria", "Redis DEL propuesta", "Redis SET propuesta enviada"):
        chequear(f"E11 nodo '{nombre}' idéntico al del cerebro actual (importado, no reescrito)", {k: v for k, v in nodos[nombre].items() if k not in ("id", "position")} == {k: v for k, v in viejos[nombre].items() if k not in ("id", "position")})
    ctx_js = nodos["Armar contexto"]["parameters"]["jsCode"]; ctx_viejo = viejos["Armar contexto"]["parameters"]["jsCode"]
    chequear("E12 'Armar contexto' es el mismo código que el actual (contexto, 6 h de staff, comprobante marcado, mensajes fijos, corte de bucle); solo cambia el prompt", ctx_js.split("\n", 1)[1] == ctx_viejo.split("\n", 1)[1] and json.dumps(CA.PROMPT_AGENTE, ensure_ascii=False) in ctx_js and "Sos el ORQUESTADOR" not in ctx_js)
    chequear("E13 el prompt del agente tiene ≤ 3.500 caracteres, trata de usted, y conserva las prohibiciones", len(CA.PROMPT_AGENTE) <= 3500 and "USTED" in CA.PROMPT_AGENTE and "NUNCA" in CA.PROMPT_AGENTE and all(k in CA.PROMPT_AGENTE for k in ("cuotas", "dólares", "STAFF", "sticker", "Diagnosticar", "no_responder", "derivar_secretaria", "pasar_a_humano")), len(CA.PROMPT_AGENTE))
    chequear("E14 'Verificar salida' lleva el módulo verificador_core (probado aparte) y corre DESPUÉS del agente y de las lecturas de Redis", "const VerificadorCore" in nodos["Verificar salida"]["parameters"]["jsCode"]
             and wf["connections"]["Redis GET hechos"]["main"][0][0]["node"] == "Verificar salida" and wf["connections"][AGENTE]["main"][0][0]["node"] == "Redis GET libro")
    chequear("E15 el cerebro actual no cambió: su orquestador sigue siendo UNA llamada sin herramientas", viejos["Orquestador"]["type"].endswith("chainLlm"))

    R = T.correr(wf, [
        esc("A1 silencio: gracias", ag("", paso("no_responder", {"ok": True, "silencio": True})), texto="gracias", pg={"Historial": [{"message": {"type": "ai", "content": "Su turno es el viernes 16/10 a las 09:10."}, "created_at": T.RECIENTE}]}),
        esc("A2 respuesta normal: precio", ag(T.I_PRECIO["texto"], paso("informacion", T.I_PRECIO, {"pedido": "precio de la consulta"})), texto="cuanto sale la consulta"),
        esc("A2b sombra: precio", ag(T.I_PRECIO["texto"], paso("informacion", T.I_PRECIO, {"pedido": "precio"})), texto="cuanto sale la consulta", modo="sombra"),
        esc("A3 el agente devuelve basura pero llamó a Turnos", ag('{"pasos": [{"a": "turnos"}]}', paso("turnos", sub("turnos", T.BLOQUE, "bloque_ofrecido"), {"pedido": "turno pal jueves"})), texto="turno pal jueves",
            redis={f"ofertas:{T.TEL}": T.OFERTAS, f"bloque:{T.TEL}": T.BLOQUE, f"bloque_exec:{T.TEL}:{T.EXEC}": T.BLOQUE}),
        esc("A4 el agente se cae", {"error": {"message": "timeout"}}, texto="quiero turno"),
        esc("A4b el agente devuelve vacío, sin herramientas", ag(""), texto="asdf qwe"),
        esc("A5 comprobante marcado: Pagos se llama por código aunque el agente no lo elija", ag("Listo, recibimos su comprobante, gracias."), texto=COMPROB, subwf={"Pagos forzado": PAGO_REC}),
        esc("A5b comprobante forzado y el agente devuelve vacío", ag(""), texto=COMPROB, subwf={"Pagos forzado": PAGO_REC}),
        esc("A5c texto normal: no se fuerza nada", ag(T.I_PRECIO["texto"], paso("informacion", T.I_PRECIO, {"pedido": "precio"})), texto="cuanto sale la consulta"),
        esc("A6 staff hace 2 h y el agente solo deriva", ag(T.DERIVA, paso("derivar_secretaria", DERIVAR_OK, {"cita_textual": "ya le mande los estudios por mail", "motivo": "estudios"})), texto="dale, ya le mande los estudios por mail",
            pg={"Historial": FILA_STAFF("2026-10-05T10:36:00Z")}),
        esc("A6b staff hace 7 h y el agente deriva", ag(T.DERIVA, paso("derivar_secretaria", DERIVAR_OK, {"cita_textual": "ya le mande los estudios por mail", "motivo": "estudios"})), texto="dale, ya le mande los estudios por mail",
            pg={"Historial": FILA_STAFF("2026-10-05T05:30:00Z")}),
        esc("A7 'ya' con confirmación pendiente: Turnos se llama por estado y el éxito llega", ag("", paso("no_responder", {"ok": True})), texto="ya", subwf={"Turnos forzado": T.T_OK},
            redis={f"propuesta:{T.TEL}": json.dumps(T.PROP_VIEJA), f"escrituras:{T.TEL}:{T.EXEC}": T.LIBRO_OK, f"turnos_vistos:{T.TEL}": T.VISTOS}, pg={"Historial": T.H_RB}),
        esc("A7b 'ok, lo pienso' con confirmación pendiente", ag("", paso("no_responder", {"ok": True})), texto="ok, lo pienso", subwf={"Turnos forzado": sub("turnos", "", "no_reply", codigo="[NO_REPLY]")},
            redis={f"propuesta:{T.TEL}": json.dumps(T.PROP_VIEJA)}, pg={"Historial": T.H_RB}),
        esc("A8 read-back que el agente no pegó", ag("Perfecto, ya lo dejo armado.", paso("turnos", T.T_RB, {"pedido": "cambiar el turno al jueves 22 9:20"}), paso("pagos", T.P_DAT, {"pedido": "pide el alias"})),
            texto="kiero pasar el turno al jueves 22 9:20 y pasame el alia", redis={f"ofertas:{T.TEL}": T.OFERTAS, f"turnos_vistos:{T.TEL}": T.VISTOS, f"propuesta:{T.TEL}": json.dumps({**T.PROP_VIEJA, "exec_id": T.EXEC, "enviada": False})}),
        esc("A9 charla de la clínica con un contacto sin ficha", ag("Hola, ¿cómo le va?"), texto="Yo por la tarde puedo pasar", subwf={"Identificar paciente": {"ok": False, "motivo": "sin_ficha"}}, pg={"Primer mensaje": [{"fuente": "wa_outbound", "tipo": "ai"}]}),
        esc("A10 urgencia: Urgencias derivó", ag("", paso("urgencias", T.U_OK, {"pedido": "a la hija le pincha el alambre"})), texto="la nena tiene el alambre q le pincha", redis={f"triaje_v7:{T.TEL}:{T.EXEC}": T.TRIAJE}),
        esc("A11 alias escrito por el agente", ag("Transfiera al alias dra.raquel.aurea", paso("pagos", T.P_DAT, {"pedido": "alias"})), texto="pasame el alias"),
        esc("A12 saludo en conversación nueva: el agente pega el menú", ag("Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel Rodríguez (Áurea Odontología Estética)."), texto="hola buenas"),
        esc("A13 derivar y avisar al grupo en vivo", ag("Esa consulta la ve la secretaria.", paso("derivar_secretaria", DERIVAR_OK, {"cita_textual": "cuanto sale en dolares", "motivo": "dólares"})), texto="cuanto sale en dolares el tratamiento"),
        esc("A14 el agente inventa un horario sin herramientas", ag("Tengo el jueves 22 de octubre a las 10:00. ¿Le sirve?"), texto="quiero turno pal jueves"),
        esc("A15 historial_json + sombra", ag(T.I_PRECIO["texto"], paso("informacion", T.I_PRECIO, {"pedido": "precio"})), texto="cuanto sale la consulta", modo="sombra",
            trigger={"historial_json": json.dumps([{"message": {"type": "human", "content": "Hola, mi DNI es 35.123.456"}}, {"message": {"type": "ai", "content": "Hola"}}])}),
    ])

    print("\nSILENCIO y RESPUESTA NORMAL")
    a = R["A1 silencio: gracias"]["reps"][0]; s = a["salida"]
    chequear("A1 'gracias' → el agente llama no_responder: silencio, sin memoria, sin avisos, sin llamar a ningún sub-agente", a["error"] is None and s["silencio"] is True and s["enviar"] is False and not s["texto"] and not llamados(a, "Guardar en memoria") and not a["avisos"]
             and not any(p["nodo"].endswith("forzado") for p in a["pedidos"]), (a["error"], s))
    a = R["A2 respuesta normal: precio"]["reps"][0]; s = a["salida"]
    chequear("A2 el agente escribe la respuesta con lo que devolvió Información: sale tal cual (presentación por código, conversación nueva)", s["texto"] == "Soy Asiri, la secretaria virtual de la Dra. Raquel.\n\nLa primera consulta tiene un valor de $50.000." and s["usado_respaldo"] is False and s["motivo_verificador"] is None, s)
    h, ai = T.mem(a)
    chequear("A2b vivo: memoria con el texto final y source asiri_v7 (un solo mensaje de Asiri)", h and h["content"] == "cuanto sale la consulta" and ai["content"] == s["texto"] and ai["additional_kwargs"]["source"] == "asiri_v7" and ai["additional_kwargs"]["agentes"] == ["informacion"], (h, ai))
    o = llamados(a, AGENTE)[0]["entradas"]
    chequear("A2c el agente recibe el contexto + el MENÚ, su prompt NUEVO, y nada de datos bancarios", "FECHA Y HORA ACTUAL (Jujuy): lunes 2026-10-05 09:36" in o["text"] and "MENÚ (si saluda solo" in o["text"] and o["text"].count("MENSAJE ACTUAL DEL PACIENTE:\ncuanto sale la consulta") == 1
             and o["sistema"] == CA.PROMPT_AGENTE and "dra.raquel.aurea" not in json.dumps(o) and "Laura Raquel" not in json.dumps(o), o["text"][-400:])
    a = R["A2b sombra: precio"]["reps"][0]
    chequear("A2d sombra: igual devuelve el texto pero sin memoria ni avisos; modo 'sombra'", not llamados(a, "Guardar en memoria") and not a["avisos"] and a["salida"]["texto"] and a["salida"]["modo"] == "sombra", (a["pedidos"], a["avisos"]))
    a = R["A5c texto normal: no se fuerza nada"]["reps"][0]
    chequear("A5c sin comprobante ni confirmación pendiente ni recordatorio: no se fuerza ningún sub-agente", not any(p["nodo"].endswith("forzado") for p in a["pedidos"]), [p["nodo"] for p in a["pedidos"]])

    print("\nRESPALDO")
    a = R["A3 el agente devuelve basura pero llamó a Turnos"]["reps"][0]; s = a["salida"]
    chequear("A3 el agente devuelve JSON/basura: sale el RESPALDO (el bloque que armó la herramienta) y queda el motivo", s["usado_respaldo"] is True and s["motivo_verificador"] == "forma_invalida" and T.BLOQUE in s["texto"] and "pasos" not in s["texto"], s)
    a = R["A4 el agente se cae"]["reps"][0]; s = a["salida"]
    chequear("A4 el agente se cae (error/timeout): texto honesto + [ACCIÓN] al grupo, fallo_agente", s["fallo_agente"] is True and "inconveniente" in s["texto"] and s["usado_respaldo"] is True and any(v["qs"]["resumen"].startswith("[ACCIÓN]") for v in a["avisos"]), (s, a["avisos"]))
    a = R["A4b el agente devuelve vacío, sin herramientas"]["reps"][0]
    chequear("A4b vacío y sin herramientas: «no le entendí» (nunca silencio ni texto inventado)", "no le entendí" in a["salida"]["texto"] and a["salida"]["motivo_verificador"] == "vacio", a["salida"])
    a = R["A11 alias escrito por el agente"]["reps"][0]; s = a["salida"]
    chequear("A11 el agente escribió el alias: se descarta; los datos salen UNA vez y los pega el código (respaldo)", s["motivo_verificador"] == "datos_pago_escritos_por_el_agente" and s["texto"].count("dra.raquel.aurea") == 1 and "Alias: dra.raquel.aurea" in s["texto"], s["texto"])
    a = R["A14 el agente inventa un horario sin herramientas"]["reps"][0]
    chequear("A14 horario inventado sin herramientas: no llega al paciente", "10:00" not in a["salida"]["texto"] and a["salida"]["usado_respaldo"] is True, a["salida"])
    a = R["A8 read-back que el agente no pegó"]["reps"][0]; x = R["A8 read-back que el agente no pegó"]; s = a["salida"]
    chequear("A8 el read-back de la herramienta se agrega textual y va AL FINAL; los datos bancarios los pega el código antes", s["usado_respaldo"] is False and s["texto"].endswith(T.RB) and s["texto"].index("Alias: dra.raquel.aurea") < s["texto"].index("Le confirmo") and s["texto"].count("Le confirmo") == 1, s)
    chequear("A8b la propuesta de ESTA ejecución queda 'enviada' (su read-back va en el mensaje)", json.loads(x["redis_final"][f"propuesta:{T.TEL}"])["enviada"] is True, x["redis_final"].get(f"propuesta:{T.TEL}"))
    chequear("A8c la traza trae el agente y las herramientas con su resultado", s["tools"][0]["tool"] == "orquestador_agente" and any(t.get("tool") == "turnos" for t in s["tools"]) and any(t.get("tool") == "pagos" for t in s["tools"]), s["tools"])

    print("\nCOMPROBANTE FORZADO y CONFIRMACIÓN PENDIENTE POR ESTADO")
    a = R["A5 comprobante marcado: Pagos se llama por código aunque el agente no lo elija"]["reps"][0]; s = a["salida"]
    p = llamados(a, "Pagos forzado")
    chequear("A5 comprobante marcado: Pagos se llama UNA vez por código ANTES del agente, con exec del cerebro y modo explícito", len(p) == 1 and p[0]["entradas"]["exec_id_actual"] == T.EXEC and p[0]["entradas"]["modo"] == "vivo" and "comprobante" in p[0]["entradas"]["pedido"]
             and a["recorrido"].index("Pagos forzado") < a["recorrido"].index(AGENTE), (p, a["recorrido"]))
    ent = llamados(a, AGENTE)[0]["entradas"]["text"]
    chequear("A5b el agente recibe el resultado de Pagos en su mensaje y la orden de no volver a llamarla; el texto sale", "RESULTADO DE «pagos»" in ent and "NO la vuelvas a llamar" in ent and "Recibido. Dejé anotado" in ent and "recibimos su comprobante" in s["texto"], (ent[-500:], s["texto"]))
    chequear("A5c la traza marca la herramienta forzada", any(t.get("tool") == "pagos" and t.get("forzado") is True for t in s["tools"]), s["tools"])
    a = R["A5b comprobante forzado y el agente devuelve vacío"]["reps"][0]
    chequear("A5d comprobante + agente vacío: el respaldo es lo que armó Pagos (el pago queda registrado y el paciente lo sabe)", "Recibido" in a["salida"]["texto"] and a["salida"]["usado_respaldo"] is True, a["salida"])
    a = R["A7 'ya' con confirmación pendiente: Turnos se llama por estado y el éxito llega"]["reps"][0]; s = a["salida"]
    t = llamados(a, "Turnos forzado")
    chequear("A7 confirmación pendiente VISTA: Turnos se llama por código con el mensaje actual aunque el agente diga no_responder; el paciente recibe el éxito", len(t) == 1 and t[0]["entradas"]["pedido"] == "responde a la confirmación pendiente" and s["texto"] == T.EXITO and s["silencio"] is False, (t, s))
    chequear("A7b el contexto de Turnos trae la CONFIRMACIÓN PENDIENTE; el 'sí' que se ejecutó no dispara el descarte", "CONFIRMACIÓN PENDIENTE" in t[0]["entradas"]["contexto"] and s["descartar_propuesta"] is False, t[0]["entradas"]["contexto"][-300:])
    x = R["A7b 'ok, lo pienso' con confirmación pendiente"]; a = x["reps"][0]
    chequear("A7c 'ok, lo pienso': el agente calla pero hay confirmación pendiente → «no cambié nada» y la propuesta se descarta", a["salida"]["texto"] == "Perfecto, no cambié nada: su turno queda como estaba." and a["salida"]["descartar_propuesta"] is True and f"propuesta:{T.TEL}" not in x["redis_final"], (a["salida"], x["redis_final"]))

    print("\nSTAFF RECIENTE, CHARLA DE LA CLÍNICA, URGENCIAS, AVISOS")
    a = R["A6 staff hace 2 h y el agente solo deriva"]["reps"][0]
    chequear("A6 staff reciente (2 h) y el agente solo derivó: silencio y sin aviso al grupo", a["salida"]["silencio"] is True and not a["avisos"] and a["salida"]["motivo_verificador"] == "contesta_al_staff", (a["salida"], a["avisos"]))
    a = R["A6b staff hace 7 h y el agente deriva"]["reps"][0]
    chequear("A6b pasadas las 6 h deriva como siempre (texto de la derivación)", a["salida"]["silencio"] is False and T.DERIVA in a["salida"]["texto"], a["salida"])
    a = R["A9 charla de la clínica con un contacto sin ficha"]["reps"][0]
    chequear("A9 charla que inició la clínica con un contacto sin ficha: silencio y NO se llama ni al agente ni a las herramientas", a["salida"]["silencio"] is True and not llamados(a, AGENTE) and not a["avisos"] and not llamados(a, "Pagos forzado"), (a["salida"], a["recorrido"]))
    a = R["A10 urgencia: Urgencias derivó"]["reps"][0]; s = a["salida"]
    chequear("A10 urgencia derivada al triaje: v7 en silencio, derivar_triaje con la cita, sin memoria", s["derivar_triaje"] is True and s["triaje"]["cita"] == "la nena tiene el alambre q le pincha" and s["enviar"] is False and not s["texto"] and not llamados(a, "Guardar en memoria"), s)
    a = R["A13 derivar y avisar al grupo en vivo"]["reps"][0]
    chequear("A13 la derivación sale con el texto fijo y, vivo, la memoria se guarda; sin aviso extra si la herramienta respondió ok", a["salida"]["texto"].endswith(T.DERIVA) and bool(llamados(a, "Guardar en memoria")) and not a["avisos"], (a["salida"], a["avisos"]))
    a = R["A12 saludo en conversación nueva: el agente pega el menú"]["reps"][0]
    chequear("A12 saludo: el agente pega el menú y no se duplica la presentación", a["salida"]["texto"].startswith("Hola! Soy Asiri") and a["salida"]["texto"].count("Soy Asiri") == 1, a["salida"])
    a = R["A15 historial_json + sombra"]["reps"][0]
    o = llamados(a, AGENTE)[0]["entradas"]["text"]
    chequear("A15 con historial_json usa ese historial (sombra retrospectiva)", "PACIENTE: Hola, mi DNI es 35.123.456" in o, o[-400:])

    print("\nMISMAS SALIDAS QUE EL CEREBRO ACTUAL")
    V = T.correr(viejo, [T.esc("V1 precio", T.orq({"a": "informacion", "pedido": "precio"}), texto="cuanto sale la consulta", subwf={"Agente Información": T.I_PRECIO})])["V1 precio"]["reps"][0]["salida"]
    N = R["A2 respuesta normal: precio"]["reps"][0]["salida"]
    chequear("S1 la salida del cerebro agente trae TODOS los campos de la del cerebro actual (el Adaptador de la entrada no cambia)", set(V) <= set(N), sorted(set(V) - set(N)))
    chequear("S1b campos nuevos solo aditivos: motivo_verificador y usado_respaldo", sorted(set(N) - set(V)) == ["motivo_verificador", "usado_respaldo"], sorted(set(N) - set(V)))
    chequear("S1c los tipos coinciden en los campos que consume el Adaptador (texto, enviar, silencio, derivar_triaje, modo_humano, avisos, descartar_propuesta)",
             all(type(N[k]) == type(V[k]) for k in ("texto", "enviar", "silencio", "derivar_triaje", "modo", "modo_humano", "avisos", "descartar_propuesta", "tools", "agentes")), {k: (type(N[k]).__name__, type(V[k]).__name__) for k in ("texto", "enviar", "silencio", "derivar_triaje", "modo", "modo_humano", "avisos", "descartar_propuesta", "tools", "agentes")})
    SN = R["A1 silencio: gracias"]["reps"][0]["salida"]
    chequear("S2 el silencio también trae todos los campos (texto null, enviar false)", set(V) <= set(SN) and SN["texto"] is None and SN["enviar"] is False, sorted(set(V) - set(SN)))

    print(f"\n{total - fallas}/{total} {'TODO OK' if not fallas else str(fallas) + ' FALLAS'}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
