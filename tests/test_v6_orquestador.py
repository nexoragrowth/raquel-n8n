# -*- coding: utf-8 -*-
"""
test_v6_orquestador.py — "v6 Orquestador": agente PADRE con los 5 especialistas del v6 como Agent Tool. Grafo nodo por nodo, sin red, con el agente SIMULADO.
Estructura: padre + 5 agentTool, cada especialista con su modelo, su prompt (el del v6 + lo listado en EDITS) y sus herramientas; variante sombra sin herramientas de
escritura reales; mismas salidas que el cerebro actual. Prompts: delegación con contexto y encargo puntual, reglas transversales sin duplicar, nada del v6 perdido sin
estar declarado. Casos con el agente simulado: silencio, respuesta normal, respaldo por basura/caída, comprobante forzado, staff reciente, charla de la clínica, etc.
USO:  python tests/test_v6_orquestador.py
"""
import copy, json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.stdout.reconfigure(encoding="utf-8")
import build_v7_workflows as B  # noqa: E402
import v6_workflow_orquestador as V6  # noqa: E402
import test_v7_cerebro as T  # noqa: E402  (datos de escenario y el harness: no corre su main)

PADRE = V6.PADRE
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
    return {"action": {"tool": tool, "toolInput": entrada or {}}, "observation": obs if isinstance(obs, str) else json.dumps(obs, ensure_ascii=False)}


def ag(texto, *pasos):
    return {"output": texto, "intermediateSteps": list(pasos)}


def esc(id_, agente, texto="Hola", **kw):
    e = T.esc(id_, None, texto=texto, **kw)
    e["llm"] = {PADRE: agente}
    e["pg"]["Get KB Horarios y Precio"] = T.KB
    return e


def V6S(nombre, *args):
    """Llama a una función (o lee una constante) de v7/v6_salida_core.js con node; los argumentos van como JSON."""
    js = "const V=require(process.argv[1]);const x=V[process.argv[2]];const a=JSON.parse(process.argv[3]);process.stdout.write(JSON.stringify(typeof x==='function'?x(...a):x));"
    r = subprocess.run(["node", "-e", js, os.path.join(ROOT, "v7", "v6_salida_core.js"), nombre, json.dumps(list(args))], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        sys.exit("node fallo: " + r.stderr[-800:])
    return json.loads(r.stdout)


def cfg(wf):
    return {n["name"]: n for n in wf["nodes"]}


def conectados(wf, destino, tipo):
    return {s for s, v in wf["connections"].items() for l in v.get(tipo, [[]]) for d in l if d["node"] == destino}


COMPROB = "[IMAGEN] TIPO: COMPROBANTE | MONTO: 50000 | DESTINATARIO: Laura Raquel Rodriguez | FECHA: 27/10/2026 | HORA: 09:17 | DESCRIPCION: Comprobante de transferencia"
PRECIO = "HICE: consulté los datos del consultorio.\nDATOS: La primera consulta tiene un valor de $50.000."
BLOQ = "TEXTO_FIJO: Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n\nLe sirve alguno?"
SALIDAS_CEREBRO = ["texto", "enviar", "silencio", "derivar_triaje", "triaje", "texto_original", "modo", "motivo_chequeo", "motivo_banlist", "fallo_agente", "modo_humano", "descartar_propuesta", "tools", "agentes", "plan", "avisos"]

# Reglas transversales: cada una tiene que vivir en UN solo prompt (el padre). (nombre, regex)
TRANSVERSALES = [
    ("nunca 'venite' / 'los esperamos' / 'ahora mismo'", r"venite|los esperamos|ahora mismo"),
    ("sin diagnóstico", r"diagn[oó]stic"),
    ("trato de usted", r"trato de usted|\bde usted\b"),
    ("horas en formato 24 hs", r"24 hs"),
    ("silencio con [NO_REPLY]", r"NO_REPLY"),
    ("una sola derivación a la secretaria por mensaje", r"M[aá]ximo UNA|UNA sola llamada|una sola vez por mensaje"),
    ("texto de derivación a la secretaria", r"Le paso con la secretaria para que lo atienda"),
    ("identidad: Sos Asiri, la secretaria virtual", r"Sos Asiri"),
    ("no conversar de temas personales", r"temas personales"),
    ("no opinar", r"NO opinas|opinar de salud"),
    ("no inventar turnos ni datos", r"inventes|inventar"),
    ("política de montos (solo la consulta)", r"solo el de la primera consulta|no se informan por whatsapp|no des ning[uú]n monto|No informes montos"),
    ("no preguntar mañana o tarde como regla general", r"\"?¿mañana o tarde\?\"? nunca"),
]


def fragmentos_v6(original, edits):
    """Texto del v6 sin lo declarado en EDITS: lo que queda (en pedazos) tiene que seguir contenido en el prompt nuevo."""
    cuerpo = original[1:]
    for viejo, _n, _d, _r in edits:
        cuerpo = cuerpo.replace(viejo, "\x00")
    return [f for f in cuerpo.split("\x00") if f.strip()]


def main():
    w6, n6 = V6._cargar_v6()
    wf = B.WORKFLOWS["v6_orquestador"]()
    ws = B.WORKFLOWS["v6_orquestador_sombra"]()
    nodos, nodos_s = cfg(wf), cfg(ws)
    txt = json.dumps(wf, ensure_ascii=False)
    cerebro = cfg(B.wf_cerebro())

    print("ESTRUCTURA")
    chequear("E1 nombres de los dos workflows y registro en el build", wf["name"] == "v6 Orquestador" and ws["name"] == "v6 Orquestador (sombra)" and {"v6_orquestador", "v6_orquestador_sombra"} <= set(B.WORKFLOWS))
    for clave, w in (("v6_orquestador", wf), ("v6_orquestador_sombra", ws)):
        ruta = os.path.join(ROOT, "v7", "workflows", clave + ".json")
        chequear(f"E1b {clave}.json generado y igual al generador (nodos y conexiones)", os.path.exists(ruta) and json.load(open(ruta, encoding="utf-8")) == json.loads(json.dumps(w, ensure_ascii=False)))
    chequear("E1c el despliegue NO lo hace este cambio: no está en crear_v7_en_n8n.py", "v6_orquestador" not in open(os.path.join(ROOT, "scripts", "crear_v7_en_n8n.py"), encoding="utf-8").read())

    padre = nodos[PADRE]
    chequear("E2 el PADRE es un AGENTE de n8n con herramientas (devuelve pasos intermedios, tope de vueltas)", padre["type"].endswith(".agent") and padre["parameters"]["options"]["returnIntermediateSteps"] is True
             and padre["parameters"]["options"]["maxIterations"] == V6.MAX_ITER)
    herr = conectados(wf, PADRE, "ai_tool")
    chequear("E3 el padre tiene como herramientas los 5 agentTool del v6 (+ no_responder + datos_pago)", herr == set(V6.HERRAMIENTAS_PADRE) | {"no_responder", "datos_pago"} and all(nodos[h]["type"].endswith(".agentTool") for h in V6.HERRAMIENTAS_PADRE), sorted(herr))
    chequear("E3b no_responder es de código y no toca nada", nodos["no_responder"]["type"].endswith("toolCode") and not re.search(r"fetch|http|redis|require", nodos["no_responder"]["parameters"]["jsCode"], re.I))
    dp = nodos["datos_pago"]
    chequear("E3c datos_pago es de código, SIN modelo ni red, y devuelve solo el marcador (nunca un dato bancario)", dp["type"].endswith("toolCode") and "datos_pago" not in conectados(wf, "datos_pago", "ai_languageModel")
             and not re.search(r"fetch|http|redis|require|alias|cbu|cuit", dp["parameters"]["jsCode"].replace(V6.MARC, ""), re.I) and V6.MARC in dp["parameters"]["jsCode"] and V6.MARC in dp["parameters"]["description"])
    mod = nodos["Modelo " + PADRE]["parameters"]
    chequear("E4 el padre usa gpt-5-mini (ai_languageModel)", mod["model"]["value"] == "gpt-5-mini" and PADRE in {d["node"] for l in wf["connections"]["Modelo " + PADRE]["ai_languageModel"] for d in l})
    mem = nodos["Postgres Chat Memory"]
    chequear("E5 memoria Postgres Chat Memory del v6 (misma ventana y credencial), conectada al padre; clave = teléfono", mem["type"].endswith("memoryPostgresChat") and PADRE in {d["node"] for l in wf["connections"]["Postgres Chat Memory"]["ai_memory"] for d in l}
             and mem["parameters"]["contextWindowLength"] == n6["Postgres Chat Memory"]["parameters"]["contextWindowLength"] and mem["credentials"] == n6["Postgres Chat Memory"]["credentials"]
             and "Sesión de memoria" in mem["parameters"]["sessionKey"] and "sesion_memoria" in mem["parameters"]["sessionKey"])
    chequear("E5b la clave de memoria la arma el nodo «Sesión de memoria» (al inicio): la variante sombra SIEMPRE con prefijo 'sombra:', la viva solo si modo != 'vivo'",
             "const SIEMPRE_SOMBRA = true;" in nodos_s["Sesión de memoria"]["parameters"]["jsCode"] and "const SIEMPRE_SOMBRA = false;" in nodos["Sesión de memoria"]["parameters"]["jsCode"]
             and conectados(wf, "Historial", "main") == {"Sesión de memoria"} and conectados(wf, "Sesión de memoria", "main") == {"Entrada"})

    print("ESPECIALISTAS (copiados del v6)")
    for orig, tool in V6.ESPECIALISTAS.items():
        a6 = n6[orig]; at = nodos[tool]
        lm6 = next(s for s, v in w6["connections"].items() if any(d["node"] == orig for l in v.get("ai_languageModel", [[]]) for d in l))
        lm_nuevo = conectados(wf, tool, "ai_languageModel")
        chequear(f"E6 {tool}: modelo idéntico al del v6 ({lm6})", lm_nuevo == {lm6} and nodos[lm6]["parameters"] == n6[lm6]["parameters"] and nodos[lm6].get("credentials") == n6[lm6].get("credentials"), sorted(lm_nuevo))
        t6 = {s for s, v in w6["connections"].items() for l in v.get("ai_tool", [[]]) for d in l if d["node"] == orig} - set(V6.SIN_COPIAR)
        chequear(f"E7 {tool}: mismas herramientas que {orig} en el v6 salvo buscar_conocimiento ({len(t6)})", conectados(wf, tool, "ai_tool") == t6 and conectados(ws, tool, "ai_tool") == t6, sorted(conectados(wf, tool, "ai_tool")))
        chequear(f"E7b {tool}: es un nodo agentTool con encargo por $fromAI y la descripción del Router", at["type"].endswith(".agentTool") and "$fromAI('encargo'" in at["parameters"]["text"] and at["parameters"]["toolDescription"] == V6.DESC[tool]
                 and re.search(r"intent \w+", at["parameters"]["toolDescription"]) is not None)
        nuevo = at["parameters"]["options"]["systemMessage"]
        chequear(f"E8 {tool}: el prompt del v6 sigue contenido salvo lo declarado en EDITS ({len(V6.EDITS[orig])} cambios)", all(f in nuevo for f in fragmentos_v6(a6["parameters"]["options"]["systemMessage"], V6.EDITS[orig])),
                 [f[:80] for f in fragmentos_v6(a6["parameters"]["options"]["systemMessage"], V6.EDITS[orig]) if f not in nuevo])
        chequear(f"E8b {tool}: lo declarado como sacado ya no está, y el bloque 'Qué recibís...' va al principio", all(v not in nuevo for v, n, _d, _r in V6.EDITS[orig] if n == "") and nuevo.startswith("=" + V6.BLOQUE)
                 and "NO le redactás al paciente" in nuevo)
        chequear(f"E8c {tool}: cada cambio declara destino y razón", all(d in ("padre", "eliminado", "reemplazado") and len(r) > 10 for _v, _n, d, r in V6.EDITS[orig]))
    tools6 = [n for n in w6["nodes"] if n["name"] in {s for v in [w6["connections"][k] for k in w6["connections"]] for _ in [0] for s in []}]
    # herramientas: en el vivo, cada nodo de herramienta es IDÉNTICO al del v6
    usadas = {s for orig in V6.ESPECIALISTAS for s in {s for s, v in w6["connections"].items() for l in v.get("ai_tool", [[]]) for d in l if d["node"] == orig}} - set(V6.SIN_COPIAR)
    chequear("E9a buscar_conocimiento (RAG que trae la entrada 24 con alias y CBU) y sus embeddings NO están en ningún workflow", not any(n in nodos or n in nodos_s for n in V6.SIN_COPIAR))
    chequear("E9 variante VIVO: las %d herramientas son idénticas a las del v6 (parámetros, credenciales, versión)" % len(usadas),
             all(nodos[t]["parameters"] == n6[t]["parameters"] and nodos[t]["type"] == n6[t]["type"] and nodos[t]["typeVersion"] == n6[t]["typeVersion"] and nodos[t].get("credentials") == n6[t].get("credentials") for t in usadas))
    escriben = {t for t in usadas if n6[t]["type"].endswith("toolHttpRequest") and (n6[t]["parameters"].get("method") in ("POST", "PUT", "PATCH", "DELETE") or t == "escalar_a_secretaria")}
    chequear("E10 las herramientas que escriben en el v6 son exactamente las que se simulan en sombra", escriben == set(V6.SIMULADAS), sorted(escriben ^ set(V6.SIMULADAS)))
    chequear("E10b variante SOMBRA: ninguna herramienta de escritura real (todas toolCode), y las simuladas conservan nombre y descripción", all(nodos_s[t]["type"].endswith("toolCode") and nodos_s[t]["parameters"]["description"].endswith(n6[t]["parameters"]["toolDescription"])
             and nodos_s[t]["parameters"]["name"] == t for t in V6.SIMULADAS) and not any(n["type"].endswith("toolHttpRequest") and (n["parameters"].get("method") in ("POST", "PUT", "PATCH", "DELETE") or n["name"] == "escalar_a_secretaria") for n in ws["nodes"]))
    lectura = usadas - set(V6.SIMULADAS)
    chequear("E10c sombra: las de solo lectura quedan reales e idénticas (%s)" % ", ".join(sorted(lectura)), all(nodos_s[t]["parameters"] == n6[t]["parameters"] and nodos_s[t]["type"] == n6[t]["type"] for t in lectura) and lectura == set(V6.LECTURA) & usadas)
    chequear("E10d vivo: los únicos toolCode son no_responder y datos_pago", sorted(n["name"] for n in wf["nodes"] if n["type"].endswith("toolCode")) == ["datos_pago", "no_responder"])
    chequear("E10e las simulaciones devuelven los mismos campos que Dentalink (id, estado) y marcan _simulado", all("_simulado" in V6.SIMULADAS[t][1] for t in V6.SIMULADAS)
             and all(k in V6.SIMULADAS["reservar_turno"][1] for k in ("id_paciente", "fecha", "hora_inicio", "id_estado")) and "id_estado: 1" in V6.SIMULADAS["cancelar_turno"][1] and "id_estado: 18" in V6.SIMULADAS["confirmar_turno"][1])
    # sin escrituras en el grafo principal: ni http, ni Redis/Postgres de escritura salvo la memoria del padre
    for nom, w in (("vivo", wf), ("sombra", ws)):
        chequear(f"E11 {nom}: el grafo principal no escribe en Dentalink, Supabase, Redis ni Evolution (sin httpRequest/redis set/postgres INSERT; solo el aviso al grupo del nodo Salida)",
                 not any(n["type"].endswith(".httpRequest") or (n["type"].endswith("redis") and n["parameters"]["operation"] != "get") or (n["type"].endswith("postgres") and not n["parameters"]["query"].lstrip().upper().startswith("SELECT")) for n in w["nodes"]))
    ids = set(re.findall(r"@@ID:([a-z_]+)@@", txt))
    chequear("E12 ids a resolver al crear: solo ver_turnos (lectura); ni un sub-workflow v7 que escriba", ids == {"ver_turnos"} and ids <= set(json.load(open(os.path.join(ROOT, "v7", "ids.json"), encoding="utf-8"))), sorted(ids))
    chequear("E12b buscar_horarios es el mismo sub-workflow de lectura del v6", nodos["buscar_horarios"]["parameters"]["workflowId"]["value"] == "GuDQ9VmKWZvQnerV")
    chequear("E13 ningún workflow generado lleva claves ni tokens escritos", not any(s in txt + json.dumps(ws) for s in ("sb_secret", "Bearer ", "eyJ")))
    # expresiones de los prompts y herramientas del v6: todos los nodos que mencionan existen con el mismo nombre
    refs = set(re.findall(r"\$\('([^']+)'\)", json.dumps([n["parameters"] for n in wf["nodes"]], ensure_ascii=False)))
    chequear("E14 todo nodo al que apuntan las expresiones (prompts, herramientas, memoria) existe", refs <= set(nodos), sorted(refs - set(nodos)))
    ex_v6 = n6["Extraer Horarios y Precio"]["parameters"]["jsCode"]; ex_n = nodos["Extraer Horarios y Precio"]["parameters"]["jsCode"]
    chequear("E15 'Extraer Horarios y Precio' es el del v6 salvo una línea (la fuente de `original`) y sin los datos bancarios", V6.sin_pago_extraer(ex_n.replace("$('Edit Fields - Extraer Datos').first().json", "$('Parse Intent').item.json")) == V6.sin_pago_extraer(ex_v6)
             and not re.search(r"pago_|cbu|cuit|1430001|dra[.]raquel[.]aurea", ex_n, re.I) and re.search(r"pago_|cbu", ex_v6, re.I))
    q6, qn = n6["Get KB Horarios y Precio"]["parameters"]["query"], nodos["Get KB Horarios y Precio"]["parameters"]["query"]
    chequear("E15b 'Get KB Horarios y Precio' es el del v6 (misma credencial) sin la entrada 24 en la consulta", " 24," in q6 and " 24," not in qn and qn == q6.replace("20, 21, 24, 25", "20, 21, 25")
             and {k: v for k, v in nodos["Get KB Horarios y Precio"]["parameters"].items() if k != "query"} == {k: v for k, v in n6["Get KB Horarios y Precio"]["parameters"].items() if k != "query"}
             and nodos["Get KB Horarios y Precio"]["credentials"] == n6["Get KB Horarios y Precio"]["credentials"])
    chequear("E16 mismo disparador y plomería que el cerebro actual (Entrada, Historial, Recordatorios, Primer mensaje, Datos del consultorio, Identificar paciente)",
             all({k: v for k, v in nodos[n].items() if k not in ("id", "position")} == {k: v for k, v in cerebro[n].items() if k not in ("id", "position")} for n in ("Historial", "Recordatorios", "Primer mensaje", "Datos del consultorio", "Identificar paciente", "Redis GET propuesta (entrada)"))
             and json.loads(nodos["Entrada"]["parameters"]["jsonExample"]) == {**json.loads(cerebro["Entrada"]["parameters"]["jsonExample"]), "sesion_sombra": ""})
    cj, cv = nodos["Armar contexto"]["parameters"]["jsCode"], cerebro["Armar contexto"]["parameters"]["jsCode"]
    chequear("E17 'Armar contexto' es el mismo código que el del cerebro actual; solo cambia el prompt", cj.split("\n", 1)[1] == cv.split("\n", 1)[1] and json.dumps(V6.PROMPT_PADRE, ensure_ascii=False) in cj.split("\n", 1)[0])
    chequear("E18 el Router del v6 no está: no hay clasificador de una llamada ni Parse Intent", not any("Router" in n or n == "Parse Intent" for n in nodos))
    chequear("E19 la salida lleva los mismos campos que el cerebro actual", "Devolver" in cerebro and all(k in nodos["Salida"]["parameters"]["jsCode"] for k in SALIDAS_CEREBRO))

    print("PROMPTS")
    p = V6.PROMPT_PADRE
    chequear("P1 prompt del padre ≤ 3.300 caracteres, de usted, castellano rioplatense", len(p) <= 3300 and "de usted" in p and "Redactá" in p, len(p))
    chequear("P2 el padre ordena DELEGAR CON CONTEXTO Y ENCARGO PUNTUAL: encargo explícito y completo, una sola tarea, frase textual, contexto del especialista (ficha, turnos, recordatorios, horarios ofrecidos, confirmación pendiente, paciente nuevo, datos que ya dio), restricciones",
             all(k in p for k in ("ENCARGO explícito y completo", "UNA sola tarea", "frase textual", "ficha o familiar elegido", "turnos vigentes y recordatorios abiertos", "horarios ya ofrecidos", "confirmación pendiente", "si es paciente nuevo", "datos que ya dio", "restricciones")))
    chequear("P2b no le pasa todo el historial a todos; lee cada resultado antes de llamar al siguiente; redacta él la respuesta final", "nunca el historial entero" in p.lower() and "ANTES de llamar al siguiente" in p and "Redactá vos la respuesta" in p and "UN solo mensaje" in p)
    chequear("P2c la herramienta pide el encargo por $fromAI y las descripciones repiten cómo armarlo", all("encargo" in V6.DESC[t] and "una sola tarea" in V6.DESC[t] for t in V6.DESC) and V6.ENCARGO_FROMAI.count("$fromAI('encargo'") == 1 and "una sola tarea" in V6.ENCARGO_FROMAI)
    chequear("P3 el padre nombra a los 5 especialistas y conserva las reglas duras (urgencias primero, sin diagnóstico, sin 'venite', sin indicaciones, solo el precio de la consulta, políticas)", all(t in p for t in V6.HERRAMIENTAS_PADRE)
             and all(k in p for k in ("urgencia", "Diagnosticar", "venite", "indicaciones", "solo el de la primera consulta", "ahora mismo", "no_responder")))
    padres_texto = {"padre": p}
    todos = {**padres_texto, **{t: nodos[t]["parameters"]["options"]["systemMessage"] for t in V6.HERRAMIENTAS_PADRE}}
    for nombre, rx in TRANSVERSALES:
        donde = [k for k, v in todos.items() if re.search(rx, v if k == "padre" else v.replace(V6.BLOQUE, ""), re.I)]
        chequear(f"P4 regla transversal '{nombre}' vive en UN solo prompt", len(donde) <= 1, donde)
    chequear("P4b las reglas transversales importantes están en el padre", all(re.search(rx, p, re.I) for n, rx in TRANSVERSALES if n.split()[0] in ("nunca", "sin", "trato", "silencio", "identidad:", "política")))
    chequear("P5 ningún especialista conserva una instrucción que choque con el nuevo reparto (hablarle al paciente, 'respondé EXACTAMENTE' sin TEXTO_FIJO en el bloque)", all("TEXTO_FIJO" in todos[t] for t in V6.HERRAMIENTAS_PADRE))
    chequear("P6 el prompt del padre se guarda también como archivo y es el que usa el workflow", V6.PROMPT_PADRE == open(os.path.join(ROOT, "v7", "prompt_orquestador_v6.md"), encoding="utf-8").read().strip())

    print("CASOS (agente simulado)")
    SIS = lambda r: next(x for x in r["pedidos"] if x["nodo"] == PADRE)["entradas"]
    R = T.correr(wf, [
        esc("A1 silencio: gracias", ag("[NO_REPLY]", paso("no_responder", {"ok": True, "silencio": True})), texto="gracias"),
        esc("A2 respuesta normal: precio", ag("La primera consulta tiene un valor de $50.000.", paso("agente_general", PRECIO, {"encargo": "precio de la consulta"})), texto="cuanto sale la consulta"),
        esc("A2b sombra: no avisa", ag("La primera consulta tiene un valor de $50.000.", paso("agente_general", PRECIO)), texto="cuanto sale la consulta", modo="sombra"),
        esc("A3 basura (JSON) pero llamó a Agendar", ag('{"pasos": [{"a": "turnos"}]}', paso("agente_agendar", BLOQ, {"encargo": "turno pal jueves"})), texto="turno pal jueves"),
        esc("A3b etiqueta interna filtrada al paciente", ag("HICE: busqué horarios", paso("agente_agendar", BLOQ)), texto="turno"),
        esc("A4 el agente se cae", {"error": {"message": "timeout"}}, texto="quiero turno"),
        esc("A4b vacío, sin herramientas", ag(""), texto="asdf qwe"),
        esc("A5 comprobante marcado y el padre NO llamó a Confirmar", ag("Listo, recibimos su comprobante, gracias."), texto=COMPROB),
        esc("A5b comprobante marcado y Confirmar sí se llamó", ag("Recibimos su comprobante. Le informo a la secretaria, que verificará el pago en su horario de atención. ¡Muchas gracias!",
            paso("agente_confirmar", "HICE: escalé a la secretaria.\nESCALÓ: comprobante de pago\nTEXTO_FIJO: Recibimos su comprobante. Le informo a la secretaria, que verificará el pago en su horario de atención. ¡Muchas gracias!")), texto=COMPROB),
        esc("A5c comprobante y el padre calla", ag("[NO_REPLY]", paso("no_responder", {"ok": True})), texto=COMPROB),
        esc("A6 staff hace 2 h: el padre calla", ag("[NO_REPLY]", paso("no_responder", {"ok": True})), texto="dale, ya le mande los estudios por mail", pg={"Historial": [{"message": {"type": "ai", "content": "Hola! Ya te dejé reservado el jueves a las 10.", "additional_kwargs": {"source": "wa_outbound"}}, "created_at": "2026-10-05T10:36:00Z"}]}),
        esc("A6b staff hace 7 h", ag("Gracias.", paso("agente_general", "DATOS: ok")), texto="gracias doctora", pg={"Historial": [{"message": {"type": "ai", "content": "Hola!", "additional_kwargs": {"source": "wa_outbound"}}, "created_at": "2026-10-05T05:30:00Z"}]}),
        esc("A7 charla de la clínica: ni se llama al agente", ag("no debería correr"), texto="si, mañana paso a ver la canilla", pg={"Primer mensaje": [{"fuente": "wa_outbound", "tipo": "ai"}]}, subwf={"Identificar paciente": {"ok": False, "motivo": "sin_ficha"}}),
        esc("A8 frase del incidente", ag("Venite ahora mismo a la clínica, los esperamos.", paso("agente_general", "DATOS: ok")), texto="me duele"),
        esc("A9 horario inventado", ag("Lo espero el jueves a las 17:45.", paso("agente_agendar", BLOQ)), texto="turno"),
        esc("A9b horario que sí salió del especialista", ag("Tenemos el jueves 22 a las 9:20.", paso("agente_agendar", BLOQ)), texto="turno"),
        esc("A10 monto inventado", ag("La cuota mensual es $70.000.", paso("agente_general", PRECIO)), texto="cuanto sale"),
        esc("A11 silencio pero había resultado de Agendar (TEXTO_FIJO)", ag("[NO_REPLY]", paso("agente_agendar", BLOQ), paso("no_responder", {"ok": True})), texto="turno"),
        esc("A12 recordatorio pendiente", ag("Listo, su turno queda confirmado.", paso("agente_confirmar", "HICE: confirmé\nTEXTO_FIJO: Listo, su turno queda confirmado.")), texto="dale gracias", pg={"Recordatorios": [{"id_cita_dentalink": 9104, "fecha_turno": "2026-10-16", "hora_turno": "09:10:00"}],
            "Historial": [{"message": {"type": "ai", "content": "Recordatorio de su turno", "additional_kwargs": {"source": "reminder_note"}}, "created_at": "2026-10-05T11:00:00Z"}]}),
        esc("A13 audio sin transcribir", ag("Disculpe, no pude escuchar bien su audio. ¿Me lo puede escribir, por favor?"), texto="[AUDIO]"),
    ])
    a = R["A1 silencio: gracias"]["reps"][0]
    chequear("A1 silencio: [NO_REPLY] + no_responder → no se envía nada", a["error"] is None and a["salida"]["silencio"] is True and a["salida"]["enviar"] is False and not a["salida"]["texto"], a)
    a = R["A2 respuesta normal: precio"]["reps"][0]; s = a["salida"]
    chequear("A2 respuesta normal: el texto del padre sale tal cual, sin respaldo, mismo contrato que el cerebro", a["error"] is None and s["texto"] == "La primera consulta tiene un valor de $50.000." and s["enviar"] is True and s["usado_respaldo"] is False
             and all(k in s for k in SALIDAS_CEREBRO) and s["modo"] == "vivo", s)
    chequear("A2b el padre recibe SOLO el mensaje del paciente como texto y el sistema = prompt + contexto (los prompts de los especialistas no viajan)", SIS(a)["text"] == "cuanto sale la consulta" and SIS(a)["sistema"].startswith(V6.PROMPT_PADRE)
             and "CONTEXTO DE ESTE MENSAJE" in SIS(a)["sistema"] and "MENSAJE ACTUAL DEL PACIENTE" in SIS(a)["sistema"] and "R0. AGENTE FUNCIONAL" not in SIS(a)["sistema"], SIS(a)["sistema"][-300:])
    chequear("A2c la traza lleva qué especialista se llamó", [t["tool"] for t in s["tools"]] == ["agente_general"] and s["agentes"][0]["agente"] == "agente_general" and s["plan"]["llamados"] == ["agente_general"], s["tools"])
    a = R["A2b sombra: no avisa"]["reps"][0]
    chequear("A2d modo sombra de la entrada: sale el mismo texto, modo 'sombra' y no se manda ningún aviso al grupo", a["salida"]["texto"] and a["salida"]["modo"] == "sombra" and a["avisos"] == [])
    a = R["A3 basura (JSON) pero llamó a Agendar"]["reps"][0]; s = a["salida"]
    chequear("A3 respaldo por basura: sale el TEXTO_FIJO que devolvió Agendar, con aviso al grupo", s["usado_respaldo"] is True and s["motivo_verificador"] == "forma_invalida" and "Tenemos los próximos turnos" in s["texto"] and len(a["avisos"]) == 1 and "respaldo" in a["avisos"][0]["qs"]["resumen"], s)
    a = R["A3b etiqueta interna filtrada al paciente"]["reps"][0]
    chequear("A3b una etiqueta interna (HICE:) en la respuesta es basura → respaldo", a["salida"]["usado_respaldo"] is True and a["salida"]["motivo_verificador"] == "forma_invalida" and "HICE" not in a["salida"]["texto"])
    a = R["A4 el agente se cae"]["reps"][0]; s = a["salida"]
    chequear("A4 el agente se cae: texto de error + aviso 'ACCIÓN' al grupo, fallo_agente", s["usado_respaldo"] is True and s["fallo_agente"] is True and s["texto"] == V6.__dict__.get("X", s["texto"]) and "inconveniente" in s["texto"] and len(a["avisos"]) == 1 and "[ACCIÓN]" in a["avisos"][0]["qs"]["resumen"], s)
    a = R["A4b vacío, sin herramientas"]["reps"][0]; s = a["salida"]
    chequear("A4b vacío y sin herramientas: 'no le entendí' (el de hoy)", s["usado_respaldo"] is True and s["motivo_verificador"] == "vacio" and "no le entendí" in s["texto"], s)
    a = R["A5 comprobante marcado y el padre NO llamó a Confirmar"]["reps"][0]; s = a["salida"]
    chequear("A5 comprobante forzado: el sistema le avisa al padre que llame a Confirmar y, si no lo hizo, sale la recepción + aviso al grupo", "COMPROBANTE DE PAGO" in SIS(a)["sistema"] and "agente_confirmar" in SIS(a)["sistema"]
             and s["motivo_verificador"] == "comprobante_sin_confirmar" and s["texto"].startswith("Recibimos su comprobante") and any("comprobante" in v["qs"]["resumen"] for v in a["avisos"]), s)
    a = R["A5b comprobante marcado y Confirmar sí se llamó"]["reps"][0]; s = a["salida"]
    chequear("A5b comprobante con Confirmar llamado: sale el texto del padre sin respaldo", s["usado_respaldo"] is False and s["texto"].startswith("Recibimos su comprobante") and a["avisos"] == [], s)
    a = R["A5c comprobante y el padre calla"]["reps"][0]
    chequear("A5c un comprobante nunca queda en silencio", a["salida"]["silencio"] is False and a["salida"]["texto"].startswith("Recibimos su comprobante"), a["salida"])
    a = R["A6 staff hace 2 h: el padre calla"]["reps"][0]
    chequear("A6 staff reciente (< 6 h): el padre ve el aviso y, si calla, silencio sin aviso", "hace menos de 6 h" in SIS(a)["sistema"] and a["salida"]["silencio"] is True and a["avisos"] == [])
    a = R["A6b staff hace 7 h"]["reps"][0]
    chequear("A6b staff hace más de 6 h: el aviso del sistema no aparece", "hace menos de 6 h" not in SIS(a)["sistema"] and a["salida"]["texto"] == "Gracias.")
    a = R["A7 charla de la clínica: ni se llama al agente"]["reps"][0]
    chequear("A7 charla que inició la clínica con un contacto sin ficha: silencio y NO se llama al padre", a["error"] is None and a["salida"]["silencio"] is True and a["salida"]["motivo_verificador"] == "charla_de_la_clinica" and PADRE not in a["recorrido"] and a["avisos"] == [], a["recorrido"])
    a = R["A8 frase del incidente"]["reps"][0]
    chequear("A8 frase del incidente del 9/5 → respaldo (no sale 'venite ahora mismo')", a["salida"]["usado_respaldo"] is True and a["salida"]["motivo_verificador"].startswith("frase_del_incidente") and "enite" not in a["salida"]["texto"])
    a = R["A9 horario inventado"]["reps"][0]
    chequear("A9 un horario que no salió de un especialista → respaldo", a["salida"]["motivo_verificador"] == "horario_no_respaldado:17:45" and "17:45" not in a["salida"]["texto"], a["salida"])
    a = R["A9b horario que sí salió del especialista"]["reps"][0]
    chequear("A9b un horario que sí salió del especialista sale", a["salida"]["usado_respaldo"] is False and "9:20" in a["salida"]["texto"], a["salida"])
    a = R["A10 monto inventado"]["reps"][0]
    chequear("A10 un monto que no es la consulta ni salió de un especialista → respaldo", a["salida"]["motivo_verificador"].startswith("monto_no_respaldado"), a["salida"])
    a = R["A11 silencio pero había resultado de Agendar (TEXTO_FIJO)"]["reps"][0]
    chequear("A11 el padre calla pero Agendar había devuelto un texto fijo: no se pierde, sale el respaldo", a["salida"]["silencio"] is False and "Tenemos los próximos turnos" in a["salida"]["texto"], a["salida"])
    a = R["A12 recordatorio pendiente"]["reps"][0]
    chequear("A12 recordatorio pendiente: el padre recibe el aviso de llamar a Confirmar", "RECORDATORIO de turno" in SIS(a)["sistema"] and a["salida"]["texto"] == "Listo, su turno queda confirmado.")
    a = R["A13 audio sin transcribir"]["reps"][0]
    chequear("A13 audio sin transcribir: el padre recibe la frase fija para pedir el texto", "NO se pudo transcribir" in SIS(a)["sistema"] and "no pude escuchar" in SIS(a)["sistema"])
    chequear("A14 en ningún caso el grafo principal llamó a Dentalink, Redis (escritura) ni sub-workflows v7 que escriban",
             all(r["reps"][0]["error"] is None for r in R.values()) and all(set(p["nodo"] for p in r["reps"][0]["pedidos"]) <= {PADRE, "Historial", "Recordatorios", "Primer mensaje", "Datos del consultorio", "Identificar paciente", "Get KB Horarios y Precio"} for r in R.values()))
    # ------------------------------------------------------------------------------------------------ (nov) los 4 arreglos de la prueba en sombra
    print("1) DATOS BANCARIOS POR CÓDIGO")
    ALIAS, CBU, CUIT, CUENTA = "dra.raquel.aurea", "1430001713001112680016", "27316870118", "1300111268001"
    KB24 = {"id": "24", "contenido": f"Titular: Laura Raquel Rodríguez. CUIT/CUIL: {CUIT}. Alias: {ALIAS}. CBU: {CBU}. Nro. de cuenta: {CUENTA}. Banco: BRUBANK. Al abonar, enviar el comprobante."}
    KB_PAGO = [k for k in T.KB if k["id"] != "24"] + [KB24]
    PG_PAGO = {"Datos del consultorio": KB_PAGO}
    DATOS = f"Alias: {ALIAS}\nTitular: Laura Raquel Rodríguez\nCUIT/CUIL: {CUIT}\nCBU: {CBU}\nNro. de cuenta: {CUENTA}\nBanco: BRUBANK"
    MARC = V6.MARC
    GENERAL_PIDE = "HICE: consulté los datos.\nDATOS: pide datos para transferir."
    todo_wf = json.dumps([wf, ws], ensure_ascii=False)
    chequear("D1 ni el alias, ni el CBU, ni el CUIT, ni la cuenta reales están escritos en ningún nodo de los dos workflows (los lee el código de la base)", not any(x in todo_wf for x in (ALIAS, CBU, CUIT, CUENTA, "BRUBANK")))
    esp = {t: nodos[t]["parameters"]["options"]["systemMessage"] + nodos[t]["parameters"]["toolDescription"] for t in V6.HERRAMIENTAS_PADRE}
    chequear("D2 ningún prompt de especialista ni del padre tiene una expresión de pago_* ni valores bancarios; solo el marcador", not any(re.search(r"pago_(?:alias|cbu|cuit|titular|banco|cuenta)|Extraer Horarios y Precio'\).item.json.pago", v) for v in esp.values())
             and not re.search(r"pago_(?:alias|cbu|cuit)", p) and MARC in esp["agente_agendar"] and MARC in esp["agente_confirmar"] and "datos_pago" in p and MARC in p, [k for k, v in esp.items() if "pago_" in v])
    chequear("D3 la herramienta buscar_conocimiento (que trae la entrada 24 completa) no está conectada a nadie", not any("buscar_conocimiento" in conectados(w_, t, "ai_tool") for w_ in (wf, ws) for t in V6.HERRAMIENTAS_PADRE))
    Rp = T.correr(wf, [
        esc("D4 pide el alias: datos_pago + marcador", ag("Con gusto, le paso los datos:\n" + MARC, paso("agente_general", GENERAL_PIDE, {"encargo": "pide datos para transferir"}), paso("datos_pago", {"ok": True, "marcador": MARC})),
            texto="me pasa el alias para transferir?", pg=PG_PAGO),
        esc("D5 marcador SIN haber llamado la herramienta", ag("Con gusto:\n" + MARC, paso("agente_general", "DATOS: ok")), texto="cuanto sale la consulta", pg=PG_PAGO),
        esc("D6 alias INVENTADO sin herramienta", ag("Claro, el alias es consultorio.aurea.pagos"), texto="me pasa el alias?", pg=PG_PAGO),
        esc("D6b alias REAL escrito a mano sin herramienta", ag(f"Claro, el alias es {ALIAS}"), texto="me pasa el alias?", pg=PG_PAGO),
        esc("D6c CBU escrito a mano (23 dígitos) sin herramienta", ag(f"Transfiera al {CBU[:7]} {CBU[7:]}"), texto="a donde transfiero?", pg=PG_PAGO),
        esc("D6d número inventado de 11 dígitos", ag("Puede llamar al 03884123456 para más datos."), texto="como me comunico?", pg=PG_PAGO),
        esc("D7 llamó datos_pago pero escribió el alias a mano: se corrige con los datos exactos", ag(f"Listo, alias: {ALIAS}x", paso("datos_pago", {"ok": True, "marcador": MARC})), texto="alias?", pg=PG_PAGO),
        esc("D8 llamó datos_pago y no escribió el marcador: el código pega los datos igual", ag("Con gusto, ahí se los paso.", paso("datos_pago", {"ok": True, "marcador": MARC})), texto="alias?", pg=PG_PAGO),
        esc("D9 el paciente escribió un número largo y el padre lo repite", ag("Anoté su número 3884123456."), texto="mi cel es 3884123456", pg=PG_PAGO),
        esc("D10 el especialista Agendar trae el marcador en su TEXTO_FIJO (pago de la consulta al reservar)", ag("Listo, le queda PRE-reservado.\n---\n" + MARC, paso("agente_agendar", "HICE: reservé\nTEXTO_FIJO: Listo, le queda PRE-reservado.\n---\n" + MARC)), texto="si, dale", pg=PG_PAGO),
        esc("D11 la KB 24 no existe: el marcador no se puede completar", ag("Aquí:\n" + MARC, paso("datos_pago", {"ok": True})), texto="alias?", pg={"Datos del consultorio": [k for k in T.KB if k["id"] != "24"]}),
    ])
    a = Rp["D4 pide el alias: datos_pago + marcador"]["reps"][0]; s = a["salida"]
    chequear("D4 el marcador se reemplaza por el texto EXACTO armado por el código (alias, titular, CUIT/CUIL, CBU, cuenta, banco) y no queda el marcador", s["usado_respaldo"] is False and DATOS in s["texto"] and MARC not in s["texto"] and s["texto"].startswith("Con gusto"), s)
    chequear("D4b el padre y los especialistas nunca recibieron los datos: no están en el sistema del padre", not any(x in SIS(a)["sistema"] for x in (ALIAS, CBU, CUIT, CUENTA)), SIS(a)["sistema"][-200:])
    s = Rp["D5 marcador SIN haber llamado la herramienta"]["reps"][0]["salida"]
    chequear("D5 marcador sin herramienta → respaldo, sin datos", s["motivo_verificador"] == "marcador_datos_pago_sin_herramienta" and s["usado_respaldo"] is True and MARC not in s["texto"] and ALIAS not in s["texto"], s)
    for k, mot in (("D6 alias INVENTADO sin herramienta", "alias inventado"), ("D6b alias REAL escrito a mano sin herramienta", "alias real"), ("D6c CBU escrito a mano (23 dígitos) sin herramienta", "CBU"), ("D6d número inventado de 11 dígitos", "11 dígitos")):
        a = Rp[k]["reps"][0]; s = a["salida"]
        chequear(f"{k[:3]} {mot} escrito por el modelo → respaldo (no sale) + aviso al grupo", s["motivo_verificador"] == "datos_pago_escritos_por_el_agente" and s["usado_respaldo"] is True and not re.search(r"consultorio.aurea|03884123456|1430001", s["texto"]) and ALIAS not in s["texto"] and len(a["avisos"]) == 1, s)
    s = Rp["D7 llamó datos_pago pero escribió el alias a mano: se corrige con los datos exactos"]["reps"][0]["salida"]
    chequear("D7 con la herramienta llamada pero el alias escrito a mano → sale la versión corregida: los datos exactos del código, sin el texto del modelo", s["motivo_verificador"] == "datos_pago_escritos_por_el_agente" and s["texto"] == "Le paso los datos para transferir:\n" + DATOS, s)
    s = Rp["D8 llamó datos_pago y no escribió el marcador: el código pega los datos igual"]["reps"][0]["salida"]
    chequear("D8 herramienta llamada sin marcador: el código agrega los datos al final", s["usado_respaldo"] is False and s["texto"] == "Con gusto, ahí se los paso.\n" + DATOS and s["datos_pago_agregados"] == "pedido", s)
    s = Rp["D9 el paciente escribió un número largo y el padre lo repite"]["reps"][0]["salida"]
    chequear("D9 un número de 10 dígitos que el paciente mismo escribió no es dato bancario", s["usado_respaldo"] is False and "3884123456" in s["texto"], s)
    s = Rp["D10 el especialista Agendar trae el marcador en su TEXTO_FIJO (pago de la consulta al reservar)"]["reps"][0]["salida"]
    chequear("D10 el marcador que viene del texto fijo del especialista Agendar también lo completa el código", s["usado_respaldo"] is False and DATOS in s["texto"] and MARC not in s["texto"], s)
    s = Rp["D11 la KB 24 no existe: el marcador no se puede completar"]["reps"][0]["salida"]
    chequear("D11 marcador sin datos en la base → respaldo, nunca un marcador pelado al paciente", s["motivo_verificador"] == "datos_pago_sin_datos" and MARC not in s["texto"], s)
    chequear("D12 un monto o un horario normal no se toma por dato bancario (DNI de 8 dígitos, horas, $50.000, fecha)", not V6S("datosPagoEscritos", "Su DNI 12345678, turno 22/10/2026 a las 09:20, $50.000", DATOS, "") and V6S("datosPagoEscritos", "Transfiera a 14300017130011126", DATOS, ""))

    print("2) URGENCIAS → TRIAJE")
    FRASE = "me duele mucho la muela y tengo la cara hinchada " + "x" * 400
    Ru = T.correr(wf, [
        esc("U1 el padre llamó a Urgencia", ag("Ya le aviso a la doctora, quédese tranquilo.", paso("agente_urgencia", "HICE: escalé\nTEXTO_FIJO: Recibimos su mensaje. Ya le aviso a la doctora para que lo revise lo antes posible.", {"encargo": "dolor"})), texto=FRASE),
        esc("U1b sombra: lo mismo", ag("Ya aviso.", paso("agente_urgencia", "HICE: escalé")), texto="se me salio el alambre", modo="sombra"),
        esc("U2 el paciente habla de dolor pero el padre NO llamó a Urgencia: no hay triaje por regex", ag("Disculpe, ¿me cuenta mejor?", paso("agente_general", "DATOS: nada")), texto="me duele la muela, que hago"),
        esc("U3 Urgencia más otro pedido", ag("Anotado.", paso("agente_urgencia", "HICE: escalé"), paso("agente_general", "DATOS: $50.000")), texto="me duele la muela y cuanto sale la consulta"),
        esc("U4 silencio no_responder pero también llamó a Urgencia: gana el triaje", ag("[NO_REPLY]", paso("agente_urgencia", "HICE: escalé"), paso("no_responder", {"ok": True})), texto="sangra la encía"),
    ])
    a = Ru["U1 el padre llamó a Urgencia"]["reps"][0]; s = a["salida"]
    chequear("U1 llamó a Urgencia → derivar_triaje=true, triaje={motivo:'derivar_triaje', cita recortada a 300}, texto suprimido (silencio, no se envía)", s["derivar_triaje"] is True and s["triaje"] == {"motivo": "derivar_triaje", "cita": FRASE[:300]} and len(s["triaje"]["cita"]) == 300
             and s["silencio"] is True and s["enviar"] is False and not s["texto"] and s["motivo_verificador"] == "urgencia_a_triaje" and s["usado_respaldo"] is False, s)
    chequear("U1b el formato es el del cerebro actual (mismas claves que el triaje del v7)", set(s["triaje"]) == {"motivo", "cita"} and s["triaje"]["motivo"] == json.loads(T.TRIAJE)["motivo"])
    s = Ru["U1b sombra: lo mismo"]["reps"][0]["salida"]
    chequear("U1c en sombra también lleva derivar_triaje (el que ejecuta el triaje es la entrada, no este workflow)", s["derivar_triaje"] is True and s["modo"] == "sombra" and s["silencio"] is True)
    s = Ru["U2 el paciente habla de dolor pero el padre NO llamó a Urgencia: no hay triaje por regex"]["reps"][0]["salida"]
    chequear("U2 la decisión es del código sobre la herramienta llamada, nunca por regex sobre lo que escribió el paciente", s["derivar_triaje"] is False and s["triaje"] is None and bool(s["texto"]), s)
    a = Ru["U3 Urgencia más otro pedido"]["reps"][0]; s = a["salida"]
    chequear("U3 Urgencia + otro pedido: igual triaje, el texto se suprime y queda un [FYI] para la clínica", s["derivar_triaje"] is True and not s["texto"] and any("[FYI]" in v["qs"]["resumen"] for v in a["avisos"]), (s, a["avisos"]))
    s = Ru["U4 silencio no_responder pero también llamó a Urgencia: gana el triaje"]["reps"][0]["salida"]
    chequear("U4 aunque el padre haya callado, si llamó a Urgencia se deriva al triaje", s["derivar_triaje"] is True and s["triaje"]["cita"] == "sangra la encía")
    chequear("U5 la salida normal NO deriva al triaje (campos presentes y en falso)", R["A2 respuesta normal: precio"]["reps"][0]["salida"]["derivar_triaje"] is False and R["A2 respuesta normal: precio"]["reps"][0]["salida"]["triaje"] is None)

    print("3) RESPUESTAS CORTAS Y SIN DUPLICADOS")
    DERIVA = "Le paso con la secretaria para que lo atienda."
    LARGO = "Con gusto le cuento. " + "La clínica atiende con turnos programados y trabaja de forma particular, con distintas modalidades de pago para cada tratamiento. " * 6
    LISTA = "Tenemos los próximos turnos disponibles:\n" + "\n".join(f"* Día {d} de octubre 8:00 , 9:20, 10:40, 11:20, 15:00, 15:40, 16:20, 17:00" for d in range(1, 12)) + "\n\nLe sirve alguno?"
    LISTA_OBS = "TEXTO_FIJO: " + LISTA
    Rb = T.correr(wf, [
        esc("B1 derivación duplicada", ag(DERIVA + " Gracias por escribir. " + DERIVA), texto="quiero hablar con alguien"),
        esc("B1b derivación duplicada con la frase vieja del v6 y la nueva", ag("Le transmito su consulta a la secretaria para que le responda a la brevedad en su horario de atención. ¡Muchas gracias!\n\n" + DERIVA), texto="quiero hablar con alguien"),
        esc("B1c una sola derivación: queda igual", ag("Esa consulta la ve la secretaria. " + DERIVA), texto="presupuesto?"),
        esc("B2 texto largo que no es lista de horarios", ag(LARGO, paso("agente_general", "TEXTO_FIJO: Hola")), texto="como trabajan?"),
        esc("B2b lista de horarios larga (más de 700 caracteres) sí sale", ag(LISTA, paso("agente_agendar", LISTA_OBS)), texto="turno"),
        esc("B2c mensaje de 700 caracteres justos", ag("a" * 700), texto="hola"),
        esc("B2d mensaje de 701 caracteres", ag("a" * 701), texto="hola"),
    ])
    s = Rb["B1 derivación duplicada"]["reps"][0]["salida"]
    chequear("B1 la frase de derivación aparece UNA sola vez", s["texto"].count(DERIVA) == 1 and "Gracias por escribir" in s["texto"] and s["usado_respaldo"] is False, s)
    s = Rb["B1b derivación duplicada con la frase vieja del v6 y la nueva"]["reps"][0]["salida"]
    chequear("B1b la derivación del v6 más la fija: queda una sola", len(re.findall(r"secretaria para que (?:le responda|lo atienda)", s["texto"])) == 1, s["texto"])
    s = Rb["B1c una sola derivación: queda igual"]["reps"][0]["salida"]
    chequear("B1c una derivación sola no se toca", s["texto"] == "Esa consulta la ve la secretaria. " + DERIVA)
    a = Rb["B2 texto largo que no es lista de horarios"]["reps"][0]; s = a["salida"]
    chequear("B2 más de 700 caracteres sin ser lista de horarios → respaldo", len(LARGO) > 700 and s["motivo_verificador"] == "texto_largo" and s["usado_respaldo"] is True and len(s["texto"]) < 700, s)
    s = Rb["B2b lista de horarios larga (más de 700 caracteres) sí sale"]["reps"][0]["salida"]
    chequear("B2b la lista de horarios (con varias horas) no se corta aunque supere los 700", len(LISTA) > 700 and s["usado_respaldo"] is False and s["texto"] == LISTA, s)
    chequear("B2c/d el límite es 700: 700 sale, 701 no", Rb["B2c mensaje de 700 caracteres justos"]["reps"][0]["salida"]["usado_respaldo"] is False and Rb["B2d mensaje de 701 caracteres"]["reps"][0]["salida"]["motivo_verificador"] == "texto_largo")
    chequear("B3 el prompt del padre: un solo mensaje breve (4 líneas), sin saludar de nuevo, la frase fija de derivación una vez, sin explicar de más ni preguntar para quién si no hace falta",
             all(k in p for k in ("hasta 4 líneas", "no saludes de nuevo", DERIVA, "una sola vez por mensaje", "sin explicar de más", "no pida datos", "para quién")), p[-1500:])
    chequear("B3b la frase fija del prompt es la misma del código (OrquestadorCore.TEXTOS.DERIVA y V6Salida.TEXTOS.DERIVA)", re.search(r"DERIVA: '([^']+)'", open(os.path.join(ROOT, "v7", "orquestador_core.js"), encoding="utf-8").read()).group(1) == DERIVA
             and V6S("TEXTOS")["DERIVA"] == DERIVA)

    print("4) MEMORIA DE SOMBRA SIN CONTAMINAR")
    H1 = json.dumps([{"message": {"type": "human", "content": "hola"}, "created_at": "2026-10-05T10:00:00Z"}])
    H2 = json.dumps([{"message": {"type": "human", "content": "quiero cancelar"}, "created_at": "2026-10-05T10:00:00Z"}])
    Rm = T.correr(wf, [
        esc("M1 sombra con historial 1", ag("Hola."), texto="hola", modo="sombra", trigger={"historial_json": H1}),
        esc("M2 sombra con historial 2 (mismo teléfono)", ag("Hola."), texto="hola", modo="sombra", trigger={"historial_json": H2}),
        esc("M3 sombra con historial 1 y otro texto", ag("Hola."), texto="buenas", modo="sombra", trigger={"historial_json": H1}),
        esc("M4 sombra con historial 1 de nuevo (misma prueba repetida)", ag("Hola."), texto="hola", modo="sombra", trigger={"historial_json": H1}),
        esc("M5 sombra con sesion_sombra explícita", ag("Hola."), texto="hola", modo="sombra", trigger={"historial_json": H1, "sesion_sombra": "caso-17"}),
        esc("M6 sombra sin historial_json (tráfico real en espejo)", ag("Hola."), texto="hola", modo="sombra"),
        esc("M7 vivo", ag("Hola."), texto="hola"),
        esc("M8 vivo aunque traiga historial_json: la memoria real no se toca", ag("Hola."), texto="hola", trigger={"historial_json": H1}),
    ])
    ses = {k: v["reps"][0]["salida"]["sesion_memoria"] for k, v in Rm.items()}
    chequear("M1 dos pruebas de sombra con distinto historial_json NO comparten clave de memoria", ses["M1 sombra con historial 1"] != ses["M2 sombra con historial 2 (mismo teléfono)"] and ses["M1 sombra con historial 1"] != ses["M3 sombra con historial 1 y otro texto"], ses)
    chequear("M1b todas llevan 'sombra:' y el teléfono (limpiables por prefijo); la misma prueba repetida da la misma clave", all(ses[k].startswith("sombra:") and ses[k].endswith(":" + T.TEL) for k in ses if k.startswith(("M1", "M2", "M3", "M4", "M5")))
             and ses["M1 sombra con historial 1"] == ses["M4 sombra con historial 1 de nuevo (misma prueba repetida)"], ses)
    chequear("M2 sesion_sombra explícita manda sobre el hash", ses["M5 sombra con sesion_sombra explícita"] == "sombra:caso-17:" + T.TEL, ses["M5 sombra con sesion_sombra explícita"])
    chequear("M3 sombra sin historial_json: 'sombra:<tel>' (continuidad del espejo, nunca la clave real)", ses["M6 sombra sin historial_json (tráfico real en espejo)"] == "sombra:" + T.TEL)
    chequear("M4 vivo: el teléfono, como el v6, aunque venga historial_json", ses["M7 vivo"] == T.TEL and ses["M8 vivo aunque traiga historial_json: la memoria real no se toca"] == T.TEL)
    RmS = T.correr(ws, [esc("MS vivo en la variante sombra", ag("Hola."), texto="hola")])
    chequear("M5 la variante sombra del workflow NUNCA usa la clave real, ni con modo 'vivo'", RmS["MS vivo en la variante sombra"]["reps"][0]["salida"]["sesion_memoria"] == "sombra:" + T.TEL)
    chequear("M6 la memoria Postgres lee la clave del nodo «Sesión de memoria» (que es el primero después de la entrada)", "$('Sesión de memoria').first().json.sesion_memoria" in nodos["Postgres Chat Memory"]["parameters"]["sessionKey"])

    # misma salida desde la variante sombra
    RS = T.correr(ws, [esc("S1", ag("La primera consulta tiene un valor de $50.000.", paso("agente_general", PRECIO)), texto="cuanto sale la consulta")])
    chequear("A15 la variante sombra devuelve lo mismo que la viva", RS["S1"]["reps"][0]["salida"]["texto"] == R["A2 respuesta normal: precio"]["reps"][0]["salida"]["texto"] and RS["S1"]["reps"][0]["error"] is None)

    print(f"\n{total - fallas}/{total} OK")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
