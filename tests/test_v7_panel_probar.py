# -*- coding: utf-8 -*-
"""test_v7_panel_probar.py — "v7 Panel - probar Información" (12/11): el panel prueba cómo contesta Información con el borrador de las notas.
Corre el workflow GENERADO nodo por nodo con tests/harness_grafo.mjs (sin red: la base y el agente están simulados). uso: python tests/test_v7_panel_probar.py"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import v7_workflow_panel_probar as P  # noqa: E402
import v7_workflow_cerebro as CER  # noqa: E402

SECRETO = "secreto-de-prueba-123"
fallas, total = 0, 0


def t(nombre, cond, extra=None):
    global fallas, total
    total += 1
    if cond:
        print(f"  ok    {nombre}")
    else:
        fallas += 1
        print(f"  FALLA {nombre}" + (f" → {json.dumps(extra, ensure_ascii=False)[:500]}" if extra is not None else ""))


KB = [{"id": "20", "contenido": "La Dra. atiende martes y jueves de 8:00 a 12:00 hs, y lunes y miércoles de 15:00 a 19:00 hs."},
      {"id": "21", "contenido": "La primera consulta tiene un valor de $50.000."},
      {"id": "dir:notas_para_asiri", "contenido": "NOTA GUARDADA: respondé breve."}]


def sal(estado="respondido", texto="", **x):
    b = {"agente": "informacion", "herramientas": [], "traza": [], "texto": texto, "estado": estado, "fuera_de_alcance": False, "urgencia": False,
         "derivar": None, "error_tecnico": False, "ofrece_primera": False}
    b.update(x)
    return b


def esc(id_, info=None, secreto=SECRETO, mensaje="¿Hasta qué hora atienden esta tarde?", notas="Usá siempre 'usted'.", kb=None):
    body = {"mensaje": mensaje} if notas == "__SIN__" else {"mensaje": mensaje, "notas": notas}
    return {"id": id_, "trigger": {"headers": {"x-panel-secret": secreto} if secreto is not None else {}, "body": body,
                                   "webhookUrl": "https://n8n.example/webhook/panel-probar-informacion"},
            "ahora": "2026-11-12T15:58:00Z", "exec_id": "777", "pg": {"Datos del consultorio": kb if kb is not None else KB},
            "subwf": {"Información": info if info is not None else sal(texto="Esta tarde no se atiende; los jueves la Dra. atiende de 8:00 a 12:00 hs. ¿Para quién es (nombre o DNI)?")}}


def correr(wf, escenarios):
    with tempfile.TemporaryDirectory() as d:
        w, e = os.path.join(d, "wf.json"), os.path.join(d, "e.json")
        json.dump(wf, open(w, "w", encoding="utf-8"), ensure_ascii=True)
        json.dump(escenarios, open(e, "w", encoding="utf-8"), ensure_ascii=True)
        p = subprocess.run(["node", os.path.join(ROOT, "tests", "harness_grafo.mjs"), w, e], capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit("node falló: " + p.stderr[-2500:])
        return {r["id"]: r["reps"][0] for r in json.loads(p.stdout)}


def llamada(a, nodo):
    return next((p for p in a["pedidos"] if p["nodo"] == nodo), None)


def main():
    print("ESTRUCTURA")
    repo = P.wf_panel_probar()
    nodos = {n["name"]: n for n in repo["nodes"]}
    validar = nodos["Validar"]["parameters"]["jsCode"]
    t("E1 en el repo el secreto es el marcador (el real se inyecta al desplegar)", 'const SECRET = "__PANEL_SECRET__";' in validar)
    t("E2 webhook POST en /panel-probar-informacion, responde por nodo", nodos["Webhook"]["parameters"]["path"] == "panel-probar-informacion" and nodos["Webhook"]["parameters"]["responseMode"] == "responseNode")
    t("E3 llama al agente de Información real (id al desplegar) en modo sombra",
      nodos["Información"]["parameters"]["workflowId"]["value"] == "@@ID:agente_informacion@@" and nodos["Información"]["parameters"]["workflowInputs"]["value"]["modo"] == "={{ 'sombra' }}")
    t("E4 misma consulta de DATOS que el cerebro", nodos["Datos del consultorio"]["parameters"]["query"] == CER.SQL_DATOS)
    armar = nodos["Armar"]["parameters"]["jsCode"]
    t("E5 mismo armado de DATOS que el cerebro (trozos copiados de JS_CONTEXTO)", all(tz in CER.JS_CONTEXTO and tz in armar for tz in (P.KB, P.DATOS, P.DATOS_INFO, P.MENSAJES)))
    t("E6 el agente no tiene herramientas: el probador no escribe nada ni avisa a nadie (solo base de lectura + agente + respuesta)",
      {n["type"].split(".")[-1] for n in repo["nodes"]} <= {"webhook", "code", "if", "respondToWebhook", "postgres", "executeWorkflow"})

    wf = P.wf_panel_probar(SECRETO)
    r = correr(wf, [
        esc("ok"),
        esc("secreto_mal", secreto="otro"),
        esc("sin_secreto", secreto=None),
        esc("vacio", mensaje="   "),
        esc("largo", mensaje="x" * 501),
        esc("notas_guardadas", notas=None),
        esc("notas_ausentes", notas="__SIN__"),
        esc("deriva_dato", info=sal("fuera_de_alcance", fuera_de_alcance=True, codigo="NO_ESTA_EN_DATOS", motivo_control="horas que no están en los DATOS: 18:00")),
        esc("deriva_msg", info=sal("fuera_de_alcance", fuera_de_alcance=True, codigo="FUERA_DE_ALCANCE"),
            kb=KB + [{"id": "dir:msg_DERIVA", "contenido": "Le paso con Irina, la secretaria, que le responde por acá."}]),
        esc("urgencia", info=sal("urgencia", urgencia=True, codigo="URGENCIA")),
        esc("nada", info=sal("no_reply", codigo="[NO_REPLY]")),
        esc("error", info={"error": {"message": "timeout"}}),
        esc("precio", mensaje="¿Cuánto sale la consulta?", info=sal(texto="La primera consulta tiene un valor de $50.000. ¿Quiere que le busque un turno para la primera consulta?")),
    ])

    print("\nSEGURIDAD Y PEDIDO")
    for k in ("secreto_mal", "sin_secreto"):
        t(f"S1 {k}: 401 y no corre el agente", r[k]["respuesta"]["codigo"] == 401 and llamada(r[k], "Información") is None, r[k]["respuesta"])
    t("S2 mensaje vacío: 400", r["vacio"]["respuesta"]["codigo"] == 400 and llamada(r["vacio"], "Información") is None, r["vacio"]["respuesta"])
    t("S3 mensaje de más de 500: 400", r["largo"]["respuesta"]["codigo"] == 400, r["largo"]["respuesta"])
    sin = correr(P.wf_panel_probar(), [esc("ph", secreto=P.SECRETO_PH)])["ph"]
    t("S4 sin secreto inyectado nadie entra (ni mandando el marcador)", sin["respuesta"]["codigo"] == 401, sin["respuesta"])

    print("\nLO QUE VE EL AGENTE")
    e = llamada(r["ok"], "Información")["entradas"]
    t("A1 modo sombra y celular sintético", e["modo"] == "sombra" and e["tel"] == "5490000000999", e)
    t("A2 los DATOS llevan el BORRADOR de las notas, no las guardadas", "NOTAS DE LA CLÍNICA" in e["datos"] and "Usá siempre 'usted'." in e["datos"] and "NOTA GUARDADA" not in e["datos"], e["datos"])
    t("A3 los DATOS llevan el Conocimiento con el mismo formato que el cerebro", "- Horarios de atención: La Dra. atiende martes y jueves de 8:00 a 12:00 hs" in e["datos"] and "- Primera consulta: La primera consulta tiene un valor de $50.000." in e["datos"], e["datos"])
    t("A4 contexto: paciente nuevo, primera vez, con el mensaje y la fecha de Jujuy", "Paciente NUEVO" in e["contexto"] and "MENSAJE ACTUAL DEL PACIENTE:\n¿Hasta qué hora atienden esta tarde?" in e["contexto"] and "jueves 2026-11-12 12:58" in e["contexto"], e["contexto"])
    t("A5 el pedido es el mensaje del paciente", e["pedido"] == "El paciente pregunta: «¿Hasta qué hora atienden esta tarde?»", e["pedido"])
    g = llamada(r["notas_guardadas"], "Información")["entradas"]["datos"]
    t("A6 notas en null = las guardadas", "NOTA GUARDADA: respondé breve." in g, g)
    g2 = llamada(r["notas_ausentes"], "Información")["entradas"]["datos"]
    t("A7 sin el campo notas = las guardadas", "NOTA GUARDADA: respondé breve." in g2, g2)
    vac = correr(wf, [esc("vacias", notas="  ")])["vacias"]
    t("A8 notas borradas en el borrador = sin notas", "NOTAS DE LA CLÍNICA" not in llamada(vac, "Información")["entradas"]["datos"])

    print("\nRESPUESTA AL PANEL")
    ok = r["ok"]["respuesta"]
    t("R1 responde: 200 con el texto que leería el paciente (sin la pregunta que el cerebro saca)",
      ok["codigo"] == 200 and ok["cuerpo"]["resultado"] == "responde" and ok["cuerpo"]["texto"].startswith("Esta tarde no se atiende") and "Para quién" not in ok["cuerpo"]["texto"], ok)
    pr = r["precio"]["respuesta"]["cuerpo"]
    t("R2 precio a un paciente nuevo: la oferta del turno queda (igual que en el cerebro)", pr["resultado"] == "responde" and "$50.000" in pr["texto"] and "¿Quiere que le busque un turno" in pr["texto"], pr)
    d = r["deriva_dato"]["respuesta"]["cuerpo"]
    t("R3 un dato que no está en Conocimiento: deriva, con el porqué", d["resultado"] == "deriva" and d["texto"] == "Le paso con la secretaria para que lo atienda." and "18:00" in (d["detalle"] or ""), d)
    dm = r["deriva_msg"]["respuesta"]["cuerpo"]
    t("R4 la derivación usa el mensaje fijo del panel", dm["resultado"] == "deriva" and dm["texto"] == "Le paso con Irina, la secretaria, que le responde por acá." and dm["detalle"] is None, dm)
    t("R5 urgencia", r["urgencia"]["respuesta"]["cuerpo"]["resultado"] == "urgencia")
    t("R6 [NO_REPLY]: nada", r["nada"]["respuesta"]["cuerpo"]["resultado"] == "nada")
    t("R7 el agente falló: error (200, el panel muestra 'probá de nuevo')", r["error"]["respuesta"]["codigo"] == 200 and r["error"]["respuesta"]["cuerpo"]["resultado"] == "error", r["error"]["respuesta"])
    t("R8 ningún escenario terminó con error de código", all(not x["error"] for x in r.values()), {k: x["error"] for k, x in r.items() if x["error"]})

    print(f"\n{total - fallas}/{total} {'FALLAS: ' + str(fallas) if fallas else 'TODO OK'}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
