# -*- coding: utf-8 -*-
"""
test_v7_ma.py — SUB-AGENTES del v7 con orquestador (08/10), sin red. Prueba:
  A) la ESTRUCTURA: qué herramientas tiene cada sub-agente (ninguna fuera de su lista), qué decide el modelo (nunca identificadores ni el modo),
     que todo lo fijo salga de la Entrada del sub-agente (la ejecución del CEREBRO, no la del sub-workflow), modo explícito en lo que escribe,
     los disparadores declaran todo lo que les llega, largo y límites de los prompts, y que ningún modelo vea los datos bancarios;
  B) cada sub-agente como GRAFO con el modelo simulado: el texto para el paciente sale de las herramientas (el modelo no redacta, salvo Información).
USO:  python tests/test_v7_ma.py
"""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import build_v7_workflows as B  # noqa: E402
import v7_workflow_cerebro as C  # noqa: E402
import v7_workflows_ma as M  # noqa: E402

TEL = "5490000000651"
EXEC = "ex-CEREBRO"
total = fallas = 0
RB = "Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?"


def chequear(nombre, cond, extra=None):
    global total, fallas
    total += 1
    if not cond:
        fallas += 1
        print(f"  FALLA {nombre}" + (f" → {json.dumps(extra, ensure_ascii=False)[:500]}" if extra is not None else ""))
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


def tools_de(wf):
    return {n["name"]: n for n in wf["nodes"] if n["type"] == "@n8n/n8n-nodes-langchain.toolWorkflow"}


def valores(n):
    return n["parameters"]["workflowInputs"]["value"]


def campos_trigger(wf):
    return set(json.loads(next(n for n in wf["nodes"] if n["type"].endswith("executeWorkflowTrigger"))["parameters"]["jsonExample"]))


PROHIBIDO = {"tel", "phone", "exec_id_actual", "modo", "id_paciente", "paciente_id", "cita_id", "id_cita", "texto_paciente", "textos_paciente", "ultimo_asiri", "accion", "contexto", "datos", "propuesta", "id"}
ESCRIBEN = {"gestionar_turno", "confirmar_turno", "lista_espera", "registrar_pago", "datos_pago", "derivar_triaje"}


def main():
    subs = {k: getattr(M, f"wf_agente_{k}")() for k in ("turnos", "pagos", "informacion", "urgencias")}
    herramientas_wf = {"ver_turnos": B.wf_ver_turnos(), "elegir_ficha": B.wf_elegir_ficha(), "buscar_horarios": B.wf_buscar_horarios(), "gestionar_turno": B.wf_gestionar_turno(),
                       "confirmar_turno": B.wf_confirmar_turno(), "clinica": B.wf_clinica()}
    cerebro = B.wf_cerebro()

    print("A. Estructura de los sub-agentes")
    esperado = {"turnos": {"ver_turnos", "elegir_ficha", "buscar_horarios", "gestionar_turno", "confirmar_turno", "lista_espera"}, "pagos": {"registrar_pago", "datos_pago"},
                "informacion": set(), "urgencias": {"derivar_triaje"}}
    for k, wf in subs.items():
        chequear(f"A1 {k}: tiene EXACTAMENTE sus herramientas (ninguna fuera de su lista)", set(tools_de(wf)) == esperado[k], sorted(tools_de(wf)))
    chequear("A1b Turnos sin registrar_pago ni derivar_triaje; Pagos sin herramientas de agenda; Urgencias sin agenda ni pagos",
             "registrar_pago" not in tools_de(subs["turnos"]) and not ({"gestionar_turno", "buscar_horarios"} & set(tools_de(subs["pagos"]))) and set(tools_de(subs["urgencias"])) == {"derivar_triaje"})
    todas = {(k, n): t for k, wf in subs.items() for n, t in tools_de(wf).items()}
    mal = [(k, n, c) for (k, n), t in todas.items() for c, v in valores(t).items() if "$fromAI" in str(v) and c in PROHIBIDO]
    chequear("A2 en ningún sub-agente el modelo decide teléfono, ejecución, modo, ids, acción, mensajes del paciente ni último Asiri", not mal, mal)
    for (k, n), t in todas.items():
        v = valores(t)
        chequear(f"A3 {k}/{n}: lo fijo sale de la Entrada del sub-agente (la ejecución del CEREBRO), nunca de $execution del sub-workflow",
                 all("$('Entrada').first().json." in str(v[c]) for c in ("tel", "exec_id_actual", "modo") if c in v) and "$execution" not in json.dumps(v), v)
        if n in ESCRIBEN:
            chequear(f"A4 {k}/{n} escribe afuera: modo fijo desde la Entrada (decisión 08/10: sin modo = sombra)", "modo" in v and "$fromAI" not in v["modo"], v)
        wf_h = herramientas_wf[t["parameters"]["workflowId"]["value"].strip("@").replace("ID:", "")]
        chequear(f"A5 {k}/{n}: el disparador de la herramienta declara todos los campos que le llegan (n8n descarta los demás)", set(v) <= campos_trigger(wf_h), sorted(set(v) - campos_trigger(wf_h)))
    gt = valores(tools_de(subs["turnos"])["gestionar_turno"])
    chequear("A6 gestionar_turno: el modelo aporta confirma (y tipo/fecha/hora/turno viejo/datos del nuevo); el código pone mensaje, último Asiri y mensajes del paciente",
             {c for c, v in gt.items() if "$fromAI" in v} == {"tipo", "fecha", "hora", "fecha_turno_viejo", "nuevo_nombre", "nuevo_apellido", "nuevo_dni", "confirma"} and all("$fromAI" not in gt[c] for c in ("texto_paciente", "ultimo_asiri", "textos_paciente")), gt)
    chequear("A6b la descripción de confirma dice MENSAJE ACTUAL (B3)", "MENSAJE ACTUAL" in gt["confirma"], gt["confirma"])
    dp = valores(tools_de(subs["pagos"])["datos_pago"])
    chequear("A6c datos_pago: el modelo decide la moneda (reemplaza el veto por regex de 'dólar')", "$fromAI('moneda'" in dp["moneda"] and "'datos_pago'" in dp["accion"], dp)
    dt = valores(tools_de(subs["urgencias"])["derivar_triaje"])
    chequear("A6d derivar_triaje: el modelo no aporta la cita (la pone el código con el mensaje completo)", not any("$fromAI" in v for v in dt.values()), dt)
    for k, wf in subs.items():
        ag = next(n for n in wf["nodes"] if n["name"] == "Agente")
        mo = next(n for n in wf["nodes"] if n["name"] == "Modelo")
        chequear(f"A7 {k}: gpt-5-mini con razonamiento bajo" + ("" if k == "informacion" else " y tope de iteraciones (Turnos 6, otros ≤ 4)"), mo["parameters"]["model"]["value"] == "gpt-5-mini" and mo["parameters"]["options"]["reasoningEffort"] == "low"
                 and (k == "informacion" or ag["parameters"]["options"]["maxIterations"] <= (6 if k == "turnos" else 4)) and ag.get("onError") == "continueRegularOutput")
        chequear(f"A8 {k}: el disparador declara todo lo que manda el cerebro", set(valores(next(n for n in cerebro["nodes"] if n["name"] == dict(C.SUBAGENTES)[k]))) <= campos_trigger(wf))
    chequear("A9 Información es UNA llamada sin herramientas (no puede tocar nada) y es la única que recibe los DATOS", next(n for n in subs["informacion"]["nodes"] if n["name"] == "Agente")["type"].endswith("chainLlm")
             and all(".datos" not in next(n for n in subs[k]["nodes"] if n["name"] == "Agente")["parameters"]["options"]["systemMessage"] for k in ("turnos", "pagos", "urgencias")))
    prompts = {"orquestador": C.PROMPT_ORQ, **M.PROMPTS}
    for k, p in prompts.items():
        tope = 2900 if k == "orquestador" else 2500   # (08/10) +derivar cuando INFORMA algo y no_reply tras derivar (REAL-05/08); (20/10) +lo que NUNCA se deriva (vivo 318965); sigue ~8× más chico que los 22 k del v6
        chequear(f"A10 prompt {k}: < {tope} caracteres ({len(p)})", len(p) < tope, len(p))
        chequear(f"A11 prompt {k}: sin 'Te esperamos', 'venite', 'ahora mismo' ni pedir que confirme la asistencia (control de texto NUESTRO)",
                 not re.search(r"te esperamos|los esperamos|lo esperamos|venite|ahora mismo|confirme su asistencia|pida confirmaci", p, re.I), p[:200])
        chequear(f"A12 prompt {k}: ningún modelo ve alias ni CBU", not re.search(r"dra\.raquel\.aurea|\bCBU\s*:", p))
    chequear("A13 Turnos decide confirma SOLO con el MENSAJE ACTUAL; el orquestador NO decide si acepta (B3)", "SOLO con el MENSAJE ACTUAL" in M.PROMPTS["turnos"] and "NO decidas si acepta" in C.PROMPT_ORQ)
    chequear("A14 el orquestador no nombra herramientas de agenda (solo elige agentes) y responde SOLO JSON", not re.search(r"gestionar_turno|buscar_horarios|elegir_ficha|confirmar_turno|ejecutar_propuesta", C.PROMPT_ORQ) and "RESPONDÉ SOLO ESTE JSON" in C.PROMPT_ORQ)
    chequear("A15 los sub-agentes con herramientas devuelven solo CÓDIGOS (no redactan)", all("Nunca escribas otro texto" in M.PROMPTS[k] for k in ("turnos", "pagos", "urgencias")))
    chequear("A16 Información con lista CERRADA de temas y las notas del panel no amplían el alcance (B2)", "lista cerrada" in M.PROMPTS["informacion"] and "aunque esté en los DATOS o en las NOTAS" in M.PROMPTS["informacion"])
    chequear("A17 Urgencias limitada a boca, dientes, encías o aparato (I6)", "boca, los dientes, las encías o el aparato" in M.PROMPTS["urgencias"])
    js_todo = json.dumps([subs, herramientas_wf, cerebro], ensure_ascii=False)
    chequear("A18 (estático) ninguna regex de intención en los workflows: sin esAfirmacion, siDirecto, VERIF, pidio_persona por regex ni listas de queja/baja",
             not re.search(r"esAfirmacion|siDirecto|VERIF[\.\[]|pidio_persona:\s*/|baja_de_datos:\s*/", js_todo))
    clin = open(os.path.join(ROOT, "v7", "clinica_core.js"), encoding="utf-8").read()
    chequear("A19 (estático) clinica_core sin VERIF ni motivos queja/baja", "VERIF" not in clin and "queja:" not in clin and "baja_de_datos:" not in clin)
    chequear("A20 ningún workflow de los sub-agentes lleva claves ni tokens escritos", not re.search(r"sk-[A-Za-z0-9]{10}|sb_secret|Bearer [A-Za-z0-9]{12}|apikey", json.dumps(subs)))

    print("B. Cada sub-agente como grafo (modelo simulado)")
    ent = {"tel": TEL, "exec_id_actual": EXEC, "modo": "sombra", "texto_paciente": "dale", "ultimo_asiri": RB, "textos_paciente": "[]", "turnos_json": json.dumps(["viernes 16/10 a las 09:10"]),
           "contexto": "CONTEXTO X", "datos": "DATOS DEL CONSULTORIO\n- Primera consulta: $50.000", "pedido": "responde a la confirmación pendiente"}
    paso = lambda tool, obs: {"action": {"tool": tool, "toolInput": {}}, "observation": json.dumps(obs, ensure_ascii=False)}
    R = correr(subs["turnos"], [
        {"id": "B1", "trigger": ent, "agente": {"output": "¡Perfecto! " + RB + " Avíseme cualquier cosa 😊", "intermediateSteps": [paso("gestionar_turno", {"etapa": "confirmacion", "ok": True, "texto_para_el_paciente": RB})]}},
        {"id": "B2", "trigger": ent, "agente": {"error": "Agent stopped due to max iterations"}},
        {"id": "B3", "trigger": ent, "agente": {"output": "PREGUNTA_CUAL_TURNO", "intermediateSteps": []}},
    ])
    a = R["B1"]["reps"][0]
    ag = next(p for p in a["pedidos"] if p["nodo"] == "Agente")["entradas"]
    chequear("B1 Turnos: el texto para el paciente es el read-back de la herramienta (la paráfrasis del modelo se descarta)", a["error"] is None and a["salida"]["texto"] == RB and a["salida"]["estado"] == "readback_pendiente" and a["salida"]["texto_libre_descartado"], (a["error"], a["salida"]))
    chequear("B1b Turnos recibe CONTEXTO + PEDIDO DEL ORQUESTADOR; su system es su prompt (sin DATOS)", ag["text"] == "CONTEXTO X\n\nPEDIDO DEL ORQUESTADOR: responde a la confirmación pendiente" and ag["sistema"] == M.PROMPTS["turnos"], ag)
    chequear("B2 Turnos se cae: error técnico, sin texto (el cerebro decide con el libro)", R["B2"]["reps"][0]["salida"]["error_tecnico"] is True and not R["B2"]["reps"][0]["salida"]["texto"], R["B2"]["reps"][0]["salida"])
    chequear("B3 PREGUNTA_CUAL_TURNO → la lista de turnos armada por código", R["B3"]["reps"][0]["salida"]["texto"] == "¿Cuál de estos turnos?\n- viernes 16/10 a las 09:10", R["B3"]["reps"][0]["salida"])
    R = correr(subs["pagos"], [{"id": "B4", "trigger": {**ent, "texto_paciente": "ya le gire lo d la consulta", "pedido": "avisa que pagó"},
                                "agente": {"output": "Gracias! ¿Para quién era el pago?", "intermediateSteps": [paso("registrar_pago", {"ok": True, "texto_para_el_paciente": "Recibido. Dejé anotado su aviso de pago; la secretaria lo verifica en su horario de atención."})]}}])
    a = R["B4"]["reps"][0]
    chequear("B4 Pagos ('ya le gire lo d la consulta'): recepción fija, SIN la pregunta que escribió el modelo", a["salida"]["texto"].startswith("Recibido.") and "?" not in a["salida"]["texto"], a["salida"])
    R = correr(subs["informacion"], [{"id": "B5", "trigger": {**ent, "pedido": "precio de la consulta"}, "llm": {"Agente": {"text": "La primera consulta tiene un valor de $50.000."}}}])
    a = R["B5"]["reps"][0]
    ag = next(p for p in a["pedidos"] if p["nodo"] == "Agente")["entradas"]
    chequear("B5 Información: redacta con los DATOS, que recibe en el system (debajo de su prompt)", a["salida"]["texto"] == "La primera consulta tiene un valor de $50.000." and ag["sistema"].startswith(M.PROMPTS["informacion"]) and "Primera consulta: $50.000" in ag["sistema"], (a["salida"], ag["sistema"][-200:]))
    R = correr(subs["urgencias"], [{"id": "B6", "trigger": {**ent, "texto_paciente": "la nena tiene el alambre q le pincha", "pedido": "le pincha el alambre"},
                                    "agente": {"output": "[NO_REPLY]", "intermediateSteps": [paso("derivar_triaje", {"ok": True, "derivado_a_triaje": True})]}}])
    chequear("B6 Urgencias: derivó al triaje y no escribe nada", R["B6"]["reps"][0]["salida"]["estado"] == "derivado" and not R["B6"]["reps"][0]["salida"]["texto"], R["B6"]["reps"][0]["salida"])

    print(f"\n{total - fallas}/{total} " + ("TODO OK" if not fallas else f"{fallas} FALLAS"))
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
