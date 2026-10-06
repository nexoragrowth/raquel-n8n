# -*- coding: utf-8 -*-
"""
test_v7_grafo.py — v7: corre los workflows de n8n GENERADOS (v7/workflows/*.json), nodo por nodo y sin red, y comprueba lo que escribirian en la agenda,
en Redis y en el grupo. Es la prueba de que el grafo (nodos + conexiones + IF) hace lo mismo que el codigo probado en tests/test_agenda_core.mjs.
USO:  python tests/test_v7_grafo.py     (primero:  python scripts/build_v7_workflows.py)
"""
import copy, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
import build_v7_workflows as B  # noqa: E402

AHORA = "2026-10-05T12:36:00Z"
TEL = "5490000000651"
D = "https://api.dentalink.healthatom.com/api/v1"


def node_json(codigo):
    p = subprocess.run(["node", "-e", f"const C=require('./v7/agenda_core.js');process.stdout.write(JSON.stringify({codigo}))"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        sys.exit("node fallo: " + p.stderr[-800:])
    return json.loads(p.stdout)


T_VIEJO = {"id": 9104, "id_paciente": 651, "fecha": "2026-10-16", "hora_inicio": "09:10:00", "id_estado": 15, "estado_anulacion": 0}
OFERTAS = [{"fecha": "2026-10-22", "hora": "08:00"}, {"fecha": "2026-10-22", "hora": "9:20"}]
ESTADO = {"tel": TEL, "exec_id": "ex-1", "ficha": {"fichas": [{"id": 651, "nombre": "Dana"}], "elegida": None}, "turnos_vistos": [T_VIEJO], "ofertas": OFERTAS}
ahora_ms = node_json(f"Date.parse('{AHORA}')")


def propuesta(entrada, estado=None, **cambios):
    r = node_json(f"C.proponer({json.dumps(entrada)}, {json.dumps(estado or ESTADO)}, '{AHORA}')")
    assert r["ok"], r
    p = r["propuesta"]
    p["creada_ms"] = ahora_ms - 60_000
    p["enviada"] = True
    p.update(cambios)
    return p


CAMBIO = {"tipo": "cambio", "fecha": "2026-10-22", "hora": "9:20", "fecha_turno_viejo": "2026-10-16"}
P = propuesta(CAMBIO)
CITA_OK = {"data": dict(T_VIEJO)}
POST_OK = {"data": {"id": 99001, "id_estado": 7}}
PUT_OK = {"data": {"id": 9104, "id_estado": 1}}
ERR = {"error": {"message": "400"}}
THROW = {"__throw": True}
TRIG = {"tel": TEL, "exec_id_actual": "ex-2", "modo": "vivo"}


def esc(id_, redis_p=None, http=None, trigger=None, rep=1, **x):
    redis = {} if redis_p is None else {f"propuesta:{TEL}": json.dumps(redis_p)}
    return {"id": id_, "trigger": trigger or TRIG, "ahora": AHORA, "redis": redis, "http": http or {}, "repeticiones": rep, **x}


def metodos(r):
    return [p["metodo"] + " " + p["url"].replace(D, "") for p in r["pedidos"]]


def chequear(nombre, cond, extra=None):
    global total, fallas
    total += 1
    if not cond:
        fallas += 1
        print(f"  FALLA {nombre}" + (f" → {json.dumps(extra, ensure_ascii=False)[:400]}" if extra else ""))
    else:
        print(f"  ok    {nombre}")


total = fallas = 0


def main():
    wf = B.wf_ejecutar()
    escenarios = [
        esc("G01 cambio feliz", P, {"GET cita vieja": CITA_OK, "POST reserva": POST_OK, "PUT anular": PUT_OK}),
        esc("G02 doble ejecución (mismo Redis): la segunda no escribe", P, {"GET cita vieja": CITA_OK, "POST reserva": POST_OK, "PUT anular": PUT_OK}, rep=2),
        esc("G03 propuesta de la MISMA ejecución", P, trigger={**TRIG, "exec_id_actual": "ex-1"}),
        esc("G04 el read-back no salió (enviada falta)", {k: v for k, v in P.items() if k != "enviada"}),
        esc("G05 la agenda rechaza la reserva", P, {"GET cita vieja": CITA_OK, "POST reserva": ERR}),
        esc("G05b la red falla en el POST", P, {"GET cita vieja": CITA_OK, "POST reserva": THROW}),
        esc("G06 reserva ok pero no anula", P, {"GET cita vieja": CITA_OK, "POST reserva": POST_OK, "PUT anular": ERR}),
        esc("G07 la cita vieja cambió de fecha", P, {"GET cita vieja": {"data": {**T_VIEJO, "fecha": "2026-10-19"}}}),
        esc("G08 la agenda no responde al verificar", P, {"GET cita vieja": THROW}),
        esc("G09 no hay propuesta en Redis", None),
        esc("G10 Redis falla al consumir (INCR)", P, {"GET cita vieja": CITA_OK}, redis_falla="incr"),
        esc("G11 cancelación feliz", propuesta({"tipo": "cancelacion", "fecha_turno_viejo": "2026-10-16"}), {"GET cita vieja": CITA_OK, "PUT anular": PUT_OK}),
        esc("G11b cancelación que la agenda rechaza", propuesta({"tipo": "cancelacion", "fecha_turno_viejo": "2026-10-16"}), {"GET cita vieja": CITA_OK, "PUT anular": ERR}),
        esc("G12 reserva simple (sin cita vieja): sin GET ni PUT", propuesta({"tipo": "reserva", "fecha": "2026-10-22", "hora": "9:20"}, {**ESTADO, "turnos_vistos": []}), {"POST reserva": POST_OK}),
        esc("G13 modo sombra", P, trigger={**TRIG, "modo": "sombra"}),
        esc("G14 propuesta vencida", {**P, "creada_ms": ahora_ms - 31 * 60_000}),
        esc("G15 familia: reserva para la ficha elegida (777)", propuesta(CAMBIO, {**ESTADO, "ficha": {"fichas": [{"id": 651, "nombre": "Dana"}, {"id": 777, "nombre": "Martina"}], "elegida": 777}, "turnos_vistos": [{**T_VIEJO, "id_paciente": 777}]}),
            {"GET cita vieja": {"data": {**T_VIEJO, "id_paciente": 777}}, "POST reserva": POST_OK, "PUT anular": PUT_OK}),
    ]
    with tempfile.TemporaryDirectory() as d:
        w, e = os.path.join(d, "wf.json"), os.path.join(d, "e.json")
        json.dump(wf, open(w, "w", encoding="utf-8"), ensure_ascii=True)
        json.dump(escenarios, open(e, "w", encoding="utf-8"), ensure_ascii=True)
        p = subprocess.run(["node", os.path.join(ROOT, "tests", "harness_grafo.mjs"), w, e], capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit("node fallo: " + p.stderr[-2500:])
        R = {r["id"]: r for r in json.loads(p.stdout)}

    print("workflow v7 Tool - ejecutar_propuesta (grafo real, sin red)")
    r = R["G01 cambio feliz"]["reps"][0]; s = r["salida"]
    chequear("G01 sin error del motor", r["error"] is None, r["error"])
    chequear("G01 GET → POST → PUT, en ese orden", metodos(r) == ["GET /citas/9104", "POST /citas/", "PUT /citas/9104"], metodos(r))
    chequear("G01 cuerpo del POST exacto", r["pedidos"][1]["body"] == {"id_dentista": 1, "id_sucursal": 1, "id_sillon": 1, "id_paciente": 651, "fecha": "2026-10-22", "hora_inicio": "09:20", "duracion": 40, "comentario": "Reprogramado por Asiri (WhatsApp), reemplaza cita #9104"}, r["pedidos"][1]["body"])
    chequear("G01 el PUT anula con {id_estado:1}", r["pedidos"][2]["body"] == {"id_estado": 1}, r["pedidos"][2]["body"])
    chequear("G01 resultado ok con el mensaje del código", s["ok"] is True and s["readback_text"] == "Listo, quedó reprogramado su turno: anulé el del viernes 16/10 a las 09:10 y le reservé el jueves 22/10 a las 09:20.", s)
    libro = json.loads(R["G01 cambio feliz"]["redis_final"][f"escrituras:{TEL}:ex-2"])
    chequear("G01 deja el libro de escrituras (lista) en Redis: ok, tipo cambio, mensaje", isinstance(libro, list) and len(libro) == 1 and libro[0]["ok"] is True and libro[0]["tipo"] == "cambio" and libro[0]["readback_text"] == s["readback_text"], libro)
    chequear("G01 avisa al grupo como FYI (una vez)", len(r["avisos"]) == 1 and r["avisos"][0]["qs"]["resumen"].startswith("[FYI]") and r["avisos"][0]["qs"]["phone"] == TEL, r["avisos"])
    chequear("G01 consumió la propuesta (INCR = 1)", R["G01 cambio feliz"]["redis_final"][f"ejecutando:{P['id']}"] == 1)

    rr = R["G02 doble ejecución (mismo Redis): la segunda no escribe"]["reps"]
    chequear("G02 la primera ok y la segunda 'ya_ejecutada'", rr[0]["salida"]["ok"] is True and rr[1]["salida"]["motivo"] == "ya_ejecutada", [x["salida"] for x in rr])
    chequear("G02 una sola reserva en total", sum(1 for x in rr for q in x["pedidos"] if q["metodo"] == "POST") == 1)

    for k, motivo in [("G03 propuesta de la MISMA ejecución", "readback_no_visto"), ("G04 el read-back no salió (enviada falta)", "readback_no_visto"), ("G09 no hay propuesta en Redis", "sin_propuesta"), ("G14 propuesta vencida", "vencida")]:
        r = R[k]["reps"][0]
        chequear(f"{k[:3]} → {motivo}, cero pedidos a la agenda y cero avisos", r["salida"]["motivo"] == motivo and not r["pedidos"] and not r["avisos"] and r["error"] is None, (r["salida"], r["error"]))
    r = R["G05 la agenda rechaza la reserva"]["reps"][0]
    chequear("G05 reserva_rechazada: NO anula y dice que el turno sigue vigente", r["salida"]["motivo"] == "reserva_rechazada" and not any(p["metodo"] == "PUT" for p in r["pedidos"]) and "sigue vigente" in r["salida"]["para_asiri"], r["salida"])
    chequear("G05 no avisa al grupo (Asiri se lo cuenta a la paciente)", not r["avisos"], r["avisos"])
    r = R["G05b la red falla en el POST"]["reps"][0]
    chequear("G05b falla de red en el POST: igual no anula", r["salida"]["motivo"] == "reserva_rechazada" and not any(p["metodo"] == "PUT" for p in r["pedidos"]))
    r = R["G06 reserva ok pero no anula"]["reps"][0]
    chequear("G06 parcial: lo dice, devuelve la cita nueva y avisa ACCIÓN", r["salida"]["parcial"] is True and r["salida"]["nueva_cita"] == 99001 and r["avisos"] and r["avisos"][0]["qs"]["resumen"].startswith("[ACCIÓN]"), (r["salida"], r["avisos"]))
    r = R["G07 la cita vieja cambió de fecha"]["reps"][0]
    chequear("G07 cita_cambio y no escribe", r["salida"]["motivo"] == "cita_cambio" and not any(p["metodo"] in ("POST", "PUT") for p in r["pedidos"]), r["salida"])
    r = R["G08 la agenda no responde al verificar"]["reps"][0]
    chequear("G08 error_tecnico y no escribe", r["salida"]["motivo"] == "error_tecnico" and not any(p["metodo"] in ("POST", "PUT") for p in r["pedidos"]), r["salida"])
    r = R["G10 Redis falla al consumir (INCR)"]["reps"][0]
    chequear("G10 Redis caído: error_tecnico y no escribe", r["salida"]["motivo"] == "error_tecnico" and not r["pedidos"], (r["salida"], r["pedidos"]))
    r = R["G11 cancelación feliz"]["reps"][0]
    chequear("G11 solo GET y PUT; mensaje de cancelación", metodos(r) == ["GET /citas/9104", "PUT /citas/9104"] and "quedó cancelado" in r["salida"]["readback_text"], (metodos(r), r["salida"]))
    r = R["G11b cancelación que la agenda rechaza"]["reps"][0]
    chequear("G11b no dice cancelado, avisa ACCIÓN", r["salida"]["motivo"] == "no_pude_cancelar" and "quedó cancelado" not in (r["salida"]["readback_text"] or "") and r["avisos"][0]["qs"]["resumen"].startswith("[ACCIÓN]"), (r["salida"], r["avisos"]))
    r = R["G12 reserva simple (sin cita vieja): sin GET ni PUT"]["reps"][0]
    chequear("G12 solo POST", metodos(r) == ["POST /citas/"] and r["salida"]["ok"] is True, (metodos(r), r["salida"]))
    r = R["G13 modo sombra"]["reps"][0]
    chequear("G13 sombra: cero pedidos a la agenda, cero avisos y devuelve el mensaje de éxito real marcado simulado", not r["pedidos"] and not r["avisos"] and r["salida"]["simulado"] is True and r["salida"]["readback_text"] == "Listo, quedó reprogramado su turno: anulé el del viernes 16/10 a las 09:10 y le reservé el jueves 22/10 a las 09:20.", (r["salida"], r["pedidos"]))
    libro = json.loads(R["G13 modo sombra"]["redis_final"][f"escrituras:{TEL}:ex-2"])
    chequear("G13 sombra: el libro queda (marcado simulado) para que el chequeo de salida se pruebe completo", libro[0]["simulado"] is True and libro[0]["ok"] is True and libro[0]["tipo"] == "cambio", libro)
    r = R["G15 familia: reserva para la ficha elegida (777)"]["reps"][0]
    chequear("G15 la reserva es para la ficha 777", r["pedidos"][1]["body"]["id_paciente"] == 777 and r["salida"]["ok"] is True, r["pedidos"])

    print(f"\n{total - fallas}/{total} {'TODO OK' if not fallas else str(fallas) + ' FALLAS'}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
