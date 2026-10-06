# -*- coding: utf-8 -*-
"""
escenarios_turnos.py — 2026-10-05

Escenarios COMPLETOS (varios mensajes) de gestion de turnos, armados con frases reales de los ultimos 30/60/90 dias y con la charla de la
paciente de las ejecuciones 294718-294752 ("Dana") + variantes. Sirven en dos capas:

  CAPA A (offline, corre ahora, sin red): "replay de ruteo". En cada paso se arma el contexto con las respuestas del bot que dicta el escenario y se
  corre el `Parse Intent` REAL (con la continuidad de flujo) contra TODAS las salidas posibles del Router (el Router es un modelo: puede
  equivocarse). El paso pasa si el flujo elegido es el que puede CERRAR la accion en CADA una de esas salidas.
  CAPA B (en vivo, con OK de Lucas, numero de prueba y ficha de prueba): cada escenario trae `exito` = el resultado esperado en la agenda y en el chat.
  Se exporta a tests/escenarios/turnos.json para cualquier runner (el de Gemini o uno nuevo).

USO:
    python tests/escenarios_turnos.py             # replay de ruteo (capa A) e informe
    python tests/escenarios_turnos.py --json      # ademas exporta tests/escenarios/turnos.json
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import apply_fix_continuidad_flujo as A  # noqa: E402
import apply_politica_modo_humano as P  # noqa: E402
import apply_fix_ruteo_consultas_cambio as R  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

CAN, AGE, CON, GEN, URG = "cancelar_o_reprogramar", "agendar_nuevo", "confirmar_post_recordatorio", "consulta_general", "urgencia_dolor"

# ---------------------------------------------------------------- respuestas tipicas del bot (texto real o muy cercano)
SLOTS = ("Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n* Viernes 23 de octubre 9:10\n\n"
         "Por la tarde:\n* Lunes 2 de noviembre 16:20\n* Miércoles 4 de noviembre 15:00 , 15:40\n\nLe sirve alguno?")
BOT = {
    "SLOTS": SLOTS,
    "SLOTS_NO_DISP": "Ese horario ya no está disponible.\n" + SLOTS,
    "BUSQUEDA": "Esta semana no tenemos turnos disponibles, disculpe. ¿Quiere que le busque las fechas más próximas?",
    "SIN_FRANJA": "La Dra. atiende por la tarde solo lunes y miércoles. No veo turnos disponibles ese día. ¿Le busco otra fecha?",
    "CAMBIAR_O_SUMAR": "Perfecto, anoto Jueves 22 de octubre a las 09:20. Veo que ya tiene un turno reservado el viernes 16/10 a las 09:10. ¿Desea cambiar ese por el del 22/10 o sumar otro?",
    "RB_REEMPLAZO": "Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?",
    "RB_RESERVA": "Le confirmo: Martes 20 de octubre a las 8:40 hs con la Dra. Raquel. ¿Procedo con la reserva?",
    "PIDE_DATOS": "Perfecto. Para registrarla necesito su nombre completo y DNI, por favor.",
    "PARA_QUIEN": "Con este número tengo registradas a Martina y Lucas. ¿Para quién es el turno?",
    "CONFIRMADO": "Listo, su turno del jueves 22 de octubre a las 09:20 hs quedó reprogramado. Cualquier consulta nos puede escribir por este medio.",
    "PRE_RESERVA": "Listo, le queda PRE-reservado para el martes 20 de octubre a las 8:40 hs. Para confirmarlo necesitamos el pago de la consulta hasta 72 hs antes.",
    "CANCEL_RB": "¿Le confirmo que desea cancelar el turno del viernes 16 de octubre a las 09:10 hs?",
    "CANCELADO": "Listo, su turno del viernes 16 de octubre quedó cancelado. Si desea reprogramar, avíseme y le busco otro horario.",
    "RECORDATORIO": "Estimada Paciente, Le recordamos su turno con la Dra. Rodríguez Raquel: Viernes 16 de octubre 09:10 hs. Le pedimos confirmar su asistencia respondiendo este mensaje.",
    "RECORDATORIO2": "Estimada Paciente, Le recordamos el turno de Luis con la Dra. Rodríguez Raquel: Viernes 16 de octubre 09:50 hs. Le pedimos confirmar su asistencia.",
    "PRECIO": "El valor de la consulta es de $50.000. Puede abonar en efectivo o por transferencia.",
    "TRIAJE": "Recibimos su mensaje. Le avisamos a la Dra. Raquel para que le coordine en su horario de atención.",
    "NINGUNA": None,   # el bot no responde (cierre)
}


def paso(p, router, espera, bot=None):
    """p = mensaje del paciente; router = salidas posibles del Router (peor caso); espera = flujo que puede cerrar la accion; bot = respuesta que sigue."""
    return {"p": p, "router": router if isinstance(router, list) else [router], "espera": espera, "bot": bot}


ESCENARIOS = [
    # ------------------------------------------------------------ DANA (real) y variantes de cambio de turno
    {"id": "DANA-01", "origen": "REAL exec 294718-294752", "funcion": "reprogramar",
     "exito": "turno 16/10 anulado y 22/10 9:20 reservado por el bot; la paciente recibe la confirmacion; sin modo humano; sin pasar por la secretaria",
     "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("Buen dia me pude cambiar ese turno", [CAN], CAN, "SLOTS"),
         paso("No podré tenia otro turno se me olvido", [CAN], CAN, "SLOTS"),
         # Estos dos los atiende el agente de agenda (2026-10-05): el sub-WF de cambios ejecuta pero no conversa — con el modelo real, 5/5 muestras,
         # contesta "Tu proximo turno es el viernes 16..." a la pregunta y al "Si" (tests/test_flujo_dana_subwf.py, turnos T3 y T4). La eleccion (paso 5) vuelve al sub-WF.
         paso("En esta semana écepto el 8 de octubre que fecha tendrá disponible por la tarde o por la mañana?", [AGE, CAN], AGE, "BUSQUEDA"),
         paso("Si", [AGE, CON], AGE, "SLOTS"),
         paso("Jueves 22 de octubre 9y20 \nSi se llegara suspender algu turno antes de esta fecha me anotaria por favor", [AGE], CAN, "CAMBIAR_O_SUMAR"),
         paso("Si cambio el turno del 16 de octubre por el turno del 22 de octubre", [CAN, AGE], CAN, "SLOTS"),
         paso("El turno 22 de octubre  alas  9y20", [AGE], CAN, "RB_REEMPLAZO"),
         paso("Si\nGracias", [CON, AGE], CAN, "CONFIRMADO"),
         paso("Gracias", [GEN], GEN, None),
     ]},
    {"id": "DANA-02", "origen": "variante limpia", "funcion": "reprogramar",
     "exito": "turno cambiado en 4 mensajes", "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("Quiero cambiar mi turno del 16/10", [CAN], CAN, "SLOTS"),
         paso("El jueves 22 a las 9:20", [AGE], CAN, "RB_REEMPLAZO"),
         paso("Si", [CON, AGE], CAN, "CONFIRMADO"),
     ]},
    {"id": "DANA-03", "origen": "variante: 'Si' y 'Gracias' en mensajes separados", "funcion": "reprogramar",
     "exito": "turno cambiado; el 'Gracias' no reabre nada", "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("Necesito pasar el turno para otro dia", [CAN], CAN, "SLOTS"),
         paso("Jueves 22 9y20", [AGE], CAN, "RB_REEMPLAZO"),
         paso("Si", [CON, AGE], CAN, "CONFIRMADO"),
         paso("Gracias", [GEN], GEN, None),
     ]},
    {"id": "DANA-04", "origen": "variante: todo en una frase", "funcion": "reprogramar",
     "exito": "el bot entiende el cambio completo y pide solo la confirmacion", "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("cambio el turno del 16 por el jueves 22 a las 9:20", [CAN, AGE], CAN, "RB_REEMPLAZO"),
         paso("Si", [CON, AGE], CAN, "CONFIRMADO"),
     ]},
    {"id": "DANA-05", "origen": "variante: el horario elegido ya no esta", "funcion": "reprogramar",
     "exito": "ofrece alternativas y termina cambiando a otro horario", "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("Quiero cambiar el turno", [CAN], CAN, "SLOTS_NO_DISP"),
         paso("El viernes 23 a las 9:10", [AGE], CAN, "RB_REEMPLAZO"),
         paso("Dale", [CON, AGE], CAN, "CONFIRMADO"),
     ]},
    {"id": "DANA-06", "origen": "variante: prefiere sumar otro turno, no cambiar", "funcion": "agendar",
     "exito": "queda con DOS turnos (no reemplaza)", "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("Jueves 22 a las 9:20", [AGE], AGE, "CAMBIAR_O_SUMAR"),
         paso("No, mejor sumar otro, no cambiar", [AGE], AGE, "RB_RESERVA"),
         paso("Si", [CON, AGE], AGE, "PRE_RESERVA"),
     ]},
    {"id": "DANA-07", "origen": "variante: celular con dos fichas (familia)", "funcion": "reprogramar",
     "exito": "pregunta de quien es el turno una sola vez y lo cambia", "inicio": [("B", "RECORDATORIO"), ("B", "RECORDATORIO2")],
     "pasos": [
         paso("Quiero cambiar el turno", [CAN], CAN, "PARA_QUIEN"),
         paso("El de Martina", [GEN, AGE, CAN], CAN, "SLOTS"),
         paso("El jueves 22 a las 9:20", [AGE], CAN, "RB_REEMPLAZO"),
         paso("Si", [CON, AGE], CAN, "CONFIRMADO"),
     ]},
    {"id": "DANA-08", "origen": "variante: se arrepiente y cancela", "funcion": "cancelar",
     "exito": "turno cancelado con read-back; ofrece reprogramar", "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("Quiero cambiar mi turno", [CAN], CAN, "SLOTS"),
         paso("Mejor lo cancelo, no puedo ir ninguno de esos dias", [CAN, GEN], CAN, "CANCEL_RB"),
         paso("Si", [CON, AGE], CAN, "CANCELADO"),
     ]},
    {"id": "DANA-09", "origen": "variante: pregunta el precio en medio del cambio", "funcion": "reprogramar",
     "exito": "responde el precio y retoma el cambio hasta cerrarlo", "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("Quiero cambiar el turno", [CAN], CAN, "SLOTS"),
         paso("¿Cuánto sale la consulta?", [GEN], GEN, "PRECIO"),
         paso("Ok. Entonces el jueves 22 a las 9:20", [AGE], CAN, "RB_REEMPLAZO"),
         paso("Si", [CON, AGE], CAN, "CONFIRMADO"),
     ]},
    {"id": "DANA-10", "origen": "variante: aparece una urgencia en medio del cambio", "funcion": "urgencia",
     "exito": "el triaje toma el mensaje; el bot se silencia solo por urgencia", "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("Quiero cambiar el turno", [CAN], CAN, "SLOTS"),
         paso("Me duele mucho una muela y me sangra", [URG, GEN, AGE], URG, "TRIAJE"),
     ]},
    # ------------------------------------------------------------ AGENDAR (frases reales 30/60/90 dias)
    {"id": "AGE-01", "origen": "REAL: primera consulta, paciente nueva", "funcion": "agendar",
     "exito": "ficha creada, turno pre-reservado, alias enviado", "inicio": [],
     "pasos": [
         paso("Buen dia, necesito un turno para consultar por una ortodoncia", [AGE], AGE, "SLOTS"),
         paso("Martes 20 de Octubre 8.40hs", [AGE], AGE, "PIDE_DATOS"),
         paso("Camila Perez DNI 40123456", [GEN, AGE], AGE, "RB_RESERVA"),
         paso("Si por favor", [CON, AGE], AGE, "PRE_RESERVA"),
         paso("Gracias!", [GEN], GEN, None),
     ]},
    {"id": "AGE-02", "origen": "REAL: restriccion horaria 'solo puedo a las 17'", "funcion": "agendar",
     "exito": "explica lo que hay, ofrece lo mas cercano y reserva", "inicio": [("B", "SLOTS")],
     "pasos": [
         paso("Solo puedo a las 17hs", [AGE, GEN], AGE, "SIN_FRANJA"),
         paso("Si", [CON, AGE], AGE, "SLOTS"),
         paso("El lunes 2 de noviembre a las 16:20", [AGE], AGE, "RB_RESERVA"),
         paso("Si", [CON, AGE], AGE, "PRE_RESERVA"),
     ]},
    {"id": "AGE-03", "origen": "REAL: 'a las 9 y 10' tras el bloque de horarios", "funcion": "agendar",
     "exito": "reserva el 9:10", "inicio": [("B", "SLOTS")],
     "pasos": [
         paso("A las 9 y 10", [AGE, GEN], AGE, "RB_RESERVA"),
         paso("Si", [CON, AGE], AGE, "PRE_RESERVA"),
     ]},
    {"id": "AGE-04", "origen": "REAL: pide turno y pregunta el pago en el mismo flujo", "funcion": "agendar",
     "exito": "responde el pago y sigue agendando", "inicio": [],
     "pasos": [
         paso("Quiero sacar un turno", [AGE], AGE, "SLOTS"),
         paso("¿Puedo abonar el día de la consulta?", [GEN], GEN, "PRECIO"),
         paso("Perfecto, el miércoles 4 a las 15:00", [AGE], AGE, "RB_RESERVA"),
         paso("Si", [CON, AGE], AGE, "PRE_RESERVA"),
     ]},
    {"id": "AGE-05", "origen": "REAL: 'la semana que viene cualquier día después de las 17'", "funcion": "agendar",
     "exito": "busca esa ventana y reserva", "inicio": [("B", "SLOTS")],
     "pasos": [
         paso("La semana que viene cualquier día después de las 17", [AGE], AGE, "SIN_FRANJA"),
         paso("Si", [CON, AGE], AGE, "SLOTS"),
         paso("El miércoles 4 a las 15:40", [AGE], AGE, "RB_RESERVA"),
         paso("Dale", [CON, AGE], AGE, "PRE_RESERVA"),
     ]},
    {"id": "AGE-06", "origen": "REAL: 'quería un turno antes del que me toca'", "funcion": "reprogramar",
     "exito": "ofrece horarios anteriores y adelanta el turno", "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("Quería un turno antes del que me toca", [AGE, CAN], CAN, "SLOTS"),
         paso("El jueves 22 a las 8:00", [AGE], CAN, "RB_REEMPLAZO"),
         paso("Si", [CON, AGE], CAN, "CONFIRMADO"),
     ]},
    {"id": "AGE-07", "origen": "inventado: ninguno de los horarios sirve", "funcion": "agendar",
     "exito": "no queda en bucle: busca otra ventana o deriva con aviso, sin silenciarse", "inicio": [("B", "SLOTS")],
     "pasos": [
         paso("Ninguno me sirve", [GEN, AGE], None, None),
     ]},
    # ------------------------------------------------------------ CONFIRMAR
    {"id": "CON-01", "origen": "REAL: 'Confirmo' (19 veces en 90 dias)", "funcion": "confirmar",
     "exito": "turno confirmado en la agenda y recordatorio cerrado", "inicio": [("B", "RECORDATORIO")],
     "pasos": [paso("Confirmo", [CON], CON, None)]},
    {"id": "CON-02", "origen": "REAL: lo confirma un familiar", "funcion": "confirmar",
     "exito": "confirma el turno", "inicio": [("B", "RECORDATORIO")],
     "pasos": [paso("Buen día. Ahí estará Valentina presente en el turno.. gracias", [CON], CON, None)]},
    {"id": "CON-03", "origen": "REAL: 'Hola!! Confirmo 💫'", "funcion": "confirmar",
     "exito": "confirma el turno", "inicio": [("B", "RECORDATORIO")],
     "pasos": [paso("Hola !! Confirmo 💫", [CON], CON, None)]},
    {"id": "CON-04", "origen": "inventado: familia con dos recordatorios", "funcion": "confirmar",
     "exito": "confirma los dos turnos y los nombra", "inicio": [("B", "RECORDATORIO"), ("B", "RECORDATORIO2")],
     "pasos": [paso("Confirmo los dos", [CON], CON, None)]},
    {"id": "CON-05", "origen": "REAL: tras el recordatorio no puede ese dia", "funcion": "reprogramar",
     "exito": "ofrece horarios y reprograma", "inicio": [("B", "RECORDATORIO")],
     "pasos": [
         paso("Buen dia. Podria pasar el turno para otro dia? Ese dia no podré", [CAN], CAN, "SLOTS"),
         paso("El miércoles 4 a las 15:00", [AGE], CAN, "RB_REEMPLAZO"),
         paso("Si", [CON, AGE], CAN, "CONFIRMADO"),
     ]},
    {"id": "CON-06", "origen": "REAL: 'No podré asistir' sin pedir nada", "funcion": "reprogramar",
     "exito": "pregunta una vez si lo reprogramamos y sigue", "inicio": [("B", "RECORDATORIO")],
     "pasos": [paso("Buenos días. Informo que no podré asistir dicha fecha a control", [CAN, GEN], CAN, None)]},
    # ------------------------------------------------------------ PAGOS
    {"id": "PAG-01", "origen": "REAL: comprobante de la seña", "funcion": "pagos",
     "exito": "acusa recibo, avisa a la secretaria, el bot sigue disponible (sin modo humano)", "inicio": [("B", "PRE_RESERVA")],
     "pasos": [paso("[IMAGEN] TIPO: COMPROBANTE MONTO: 50000 DESTINATARIO: Rodriguez Laura Raquel", [CON, GEN], [CON, GEN], None)]},
    {"id": "PAG-02", "origen": "REAL: 'Ya transferí'", "funcion": "pagos",
     "exito": "pide/acusa comprobante sin validar el pago", "inicio": [("B", "PRE_RESERVA")],
     "pasos": [paso("Ya transferí", [CON, GEN], [CON, GEN], None)]},
]


def construir_ctx(hist):
    return "\n---\n".join(("PACIENTE: " if q == "P" else "BOT: ") + t for q, t in hist[-6:]) if hist else "(sin mensajes previos)"


def armar_casos():
    codigo = R.transformar_parse(P.transformar_parse_busqueda(A.transformar_parse(open(os.path.join(ROOT, "tests", "fixtures", "parse_intent_antes.js"), encoding="utf-8").read())))
    casos, indice = [], []
    for e in ESCENARIOS:
        hist = [(q, BOT[k]) for q, k in e.get("inicio", [])]
        for i, st in enumerate(e["pasos"]):
            for r in st["router"]:
                casos.append({"nombre": f"{e['id']}#{i+1}/{r}", "codigo": codigo, "texto": st["p"], "router": r, "ctx": construir_ctx(hist)})
                indice.append((e["id"], i + 1, r))
            hist.append(("P", st["p"]))
            if st["bot"] and BOT[st["bot"]]:
                hist.append(("B", BOT[st["bot"]]))
    return casos, indice


HARNESS = r"""
import fs from 'node:fs';
const casos = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const salida = [];
for (const c of casos) {
  const fn = new AsyncFunction('$input', '$', 'console', c.codigo);
  const $input = { first: () => ({ json: { output: c.router } }) };
  const $ = (n) => {
    if (n === 'Preparar Mensaje Final') return { first: () => ({ json: { text: c.texto } }) };
    if (n === 'Build Router Context') return { first: () => ({ json: { ctx: c.ctx } }) };
    throw new Error('nodo desconocido ' + n);
  };
  try { const r = await fn($input, $, { log() {} }); salida.push({ nombre: c.nombre, intent: r[0].json.intent, continuidad: r[0].json.continuidad ?? null }); }
  catch (e) { salida.push({ nombre: c.nombre, error: String(e.message || e) }); }
}
process.stdout.write(JSON.stringify(salida));
"""


def correr():
    casos, indice = armar_casos()
    with tempfile.TemporaryDirectory() as d:
        h, c = os.path.join(d, "h.mjs"), os.path.join(d, "c.json")
        open(h, "w", encoding="utf-8").write(HARNESS)
        json.dump(casos, open(c, "w", encoding="utf-8"), ensure_ascii=False)
        p = subprocess.run(["node", h, c], capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit("node fallo:\n" + p.stderr)
        res = {r["nombre"]: r for r in json.loads(p.stdout)}
    return res


def main():
    res = correr()
    total_pasos = ok_pasos = 0
    escenarios_ok = 0
    fallos = []
    print("REPLAY DE RUTEO — por escenario (cada paso se prueba contra TODAS las salidas posibles del Router)\n")
    for e in ESCENARIOS:
        pasos_mal = []
        for i, st in enumerate(e["pasos"]):
            if st["espera"] is None:
                continue
            total_pasos += 1
            salidas = {r: res[f"{e['id']}#{i+1}/{r}"].get("intent") for r in st["router"]}
            ok_set = st["espera"] if isinstance(st["espera"], (list, tuple)) else [st["espera"]]
            if all(v in ok_set for v in salidas.values()):
                ok_pasos += 1
            else:
                pasos_mal.append((i + 1, st["p"][:60], st["espera"], salidas))
        if not pasos_mal:
            escenarios_ok += 1
        print(f"  {'OK   ' if not pasos_mal else 'FALLA'} {e['id']:<8} {e['funcion']:<11} {e['origen'][:52]}")
        for n, txt, esp, sal in pasos_mal:
            print(f"        paso {n}: «{txt}» esperaba {esp}; con Router {sal}")
            fallos.append((e["id"], n, txt, esp, sal))
    print(f"\nPasos: {ok_pasos}/{total_pasos} · Escenarios completos: {escenarios_ok}/{len(ESCENARIOS)}")
    if "--json" in sys.argv:
        os.makedirs(os.path.join(ROOT, "tests", "escenarios"), exist_ok=True)
        json.dump({"bot_textos": BOT, "escenarios": ESCENARIOS}, open(os.path.join(ROOT, "tests", "escenarios", "turnos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("exportado tests/escenarios/turnos.json")
    return fallos


if __name__ == "__main__":
    f = main()
    sys.exit(1 if f else 0)
