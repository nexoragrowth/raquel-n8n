# -*- coding: utf-8 -*-
"""
test_continuidad_flujo.py — 2026-10-05

Corre con node el JS REAL de `Parse Intent` (fixture tests/fixtures/parse_intent_antes.js = el codigo vivo antes del cambio) con la
continuidad de flujo de scripts/apply_fix_continuidad_flujo.py, mockeando $input / $() . Sin red.
Casos 1-4 = la charla REAL de la paciente de las ejecuciones 294718-294752 (cambio de turno que termino en "Si / Gracias" → Confirmar).

USO:  python tests/test_continuidad_flujo.py
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import apply_fix_continuidad_flujo as A  # noqa: E402
import apply_politica_modo_humano as P  # noqa: E402
import apply_fix_ruteo_consultas_cambio as R  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

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
    if (n === 'Build Router Context') {
      if (c.ctx_falla) throw new Error("No path back to referenced node");
      return { first: () => ({ json: { ctx: c.ctx } }) };
    }
    throw new Error('nodo desconocido ' + n);
  };
  try {
    const r = await fn($input, $, { log() {} });
    salida.push({ nombre: c.nombre, intent: r[0].json.intent, continuidad: r[0].json.continuidad ?? null });
  } catch (e) { salida.push({ nombre: c.nombre, error: String(e.message || e) }); }
}
process.stdout.write(JSON.stringify(salida));
"""

BASE = open(os.path.join(ROOT, "tests", "fixtures", "parse_intent_antes.js"), encoding="utf-8").read()
NUEVO = R.transformar_parse(P.transformar_parse_busqueda(A.transformar_parse(BASE)))   # la cadena completa = lo que queda vivo


def ctx(*t):
    return "\n---\n".join(("PACIENTE: " if q == "P" else "BOT: ") + x for q, x in t)


SLOTS = ("Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n* Viernes 23 de octubre 9:10\n\n"
         "Por la tarde:\n* Lunes 2 de noviembre 16:20\n\nLe sirve alguno?")
RB_REEMPLAZO = ("Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. "
                "¿Procedo con la reserva?")
RB_RESERVA = "Le confirmo: Martes 20 de octubre a las 8:40 hs con la Dra. Raquel. ¿Procedo con la reserva?"
CAMBIO = [("P", "Buen dia me pude cambiar ese turno"), ("B", SLOTS), ("P", "No podré tenia otro turno se me olvido"), ("B", SLOTS)]

# nombre, texto del paciente, intent que devolvio el Router, contexto, intent esperado, ¿debe marcar continuidad?
CASOS = [
    ("1 REAL 294752: 'Si Gracias' tras read-back de reemplazo", "Si\nGracias", "confirmar_post_recordatorio",
     ctx(("P", "Si cambio el turno del 16 de octubre por el turno del 22 de octubre"), ("B", SLOTS),
         ("P", "El turno 22 de octubre alas 9y20"), ("B", RB_REEMPLAZO)), "cancelar_o_reprogramar", True),
    ("2 REAL 294748: elige horario en un cambio en curso", "El turno 22 de octubre  alas  9y20", "agendar_nuevo",
     ctx(("P", "No podré tenia otro turno se me olvido"), ("B", SLOTS),
         ("P", "Si cambio el turno del 16 de octubre por el turno del 22"), ("B", SLOTS)), "cancelar_o_reprogramar", True),
    ("3 REAL 294738: 'Jueves 22 9y20' tras horarios de un cambio", "Jueves 22 de octubre 9y20 \nSi se llegara suspender algun turno me anotaria", "agendar_nuevo",
     ctx(("P", "No podré tenia otro turno se me olvido"), ("B", SLOTS),
         ("P", "En esta semana excepto el 8 que fecha tendra disponible"),
         ("B", "Esta semana no tenemos turnos disponibles. ¿Quiere que le busque las fechas más próximas?"),
         ("P", "Si"), ("B", SLOTS)), "cancelar_o_reprogramar", True),
    # 2026-10-05: una pregunta ABIERTA de disponibilidad en medio de un cambio la responde el agente de agenda (el sub-WF la lee como "consulta de info"
    # y contesta "Tu proximo turno es..."; medido con el modelo real en tests/test_flujo_dana_subwf.py, turno T3). Se prueba con las dos salidas del Router.
    ("4 REAL 294727: pregunta abierta de disponibilidad en un cambio → agente de agenda", "En esta semana écepto el 8 de octubre que fecha tendrá disponible por la tarde o por la mañana?",
     "agendar_nuevo", ctx(*CAMBIO), "agendar_nuevo", True),
    ("4b igual, aunque el Router diga cancelar_o_reprogramar", "En esta semana écepto el 8 de octubre que fecha tendrá disponible por la tarde o por la mañana?",
     "cancelar_o_reprogramar", ctx(*CAMBIO), "agendar_nuevo", True),
    ("4c 'otro dia' tras el bloque en un cambio: sigue en el sub-WF (logica de siguiente lote)", "Esos no puedo, tiene otro dia?",
     "agendar_nuevo", ctx(*CAMBIO), "cancelar_o_reprogramar", True),
    ("4d 'por la tarde' tras el bloque en un cambio: sigue en el sub-WF (logica de franja)", "Por la tarde",
     "agendar_nuevo", ctx(*CAMBIO), "cancelar_o_reprogramar", True),
    ("4e 'Si' pelado tras un bloque con varias opciones en un cambio → agente de agenda (pregunta cual)", "Si",
     "confirmar_post_recordatorio", ctx(*CAMBIO), "agendar_nuevo", True),
    ("4f eleccion con signo de pregunta ('¿puede ser el jueves 22 a las 9:20?') en un cambio: es una eleccion → sub-WF", "Puede ser el jueves 22 a las 9:20?",
     "agendar_nuevo", ctx(*CAMBIO), "cancelar_o_reprogramar", True),
    ("4g pregunta abierta tras un bloque SIN cambio de por medio (reserva nueva): agente de agenda, como siempre", "Que dia tiene disponible la semana que viene?",
     "consulta_general", ctx(("P", "Quiero sacar un turno"), ("B", SLOTS)), "agendar_nuevo", True),
    ("5 agendar puro: elige horario", "El martes 20 a las 8", "agendar_nuevo", ctx(("P", "Quiero sacar un turno"), ("B", SLOTS)), "agendar_nuevo", True),
    ("6 agendar puro: 'Si' tras read-back (nunca Confirmar)", "Si", "confirmar_post_recordatorio", ctx(("B", RB_RESERVA)), "agendar_nuevo", True),
    ("7 recordatorio: 'Confirmo' sigue en Confirmar", "Confirmo", "confirmar_post_recordatorio",
     ctx(("B", "Estimada Paciente, Le recordamos su turno con la Dra. Rodríguez Raquel: Miércoles 7 de octubre 17:00 hs. Le pedimos confirmar su asistencia.")),
     "confirmar_post_recordatorio", False),
    ("8 urgencia no se pisa", "Se me salió el bracket y me sangra", "urgencia_dolor", ctx(("B", RB_RESERVA)), "urgencia_dolor", False),
    ("9 pregunta de precio no se pisa", "Cuánto sale la consulta?", "consulta_general", ctx(("B", RB_RESERVA)), "consulta_general", False),
    ("10 ultimo turno del staff: no hace nada", "Si", "confirmar_post_recordatorio",
     ctx(("B", "[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria. Mensaje del staff, no es output tuyo.]: Hola, la esperamos")),
     "confirmar_post_recordatorio", False),
    ("11 'gracias' sola tras read-back: no cambia", "Gracias", "consulta_general", ctx(("B", RB_RESERVA)), "consulta_general", False),
    ("12 cancelacion: 'Dale' tras read-back de cancelar", "Dale", "confirmar_post_recordatorio",
     ctx(("B", "¿Le confirmo que desea cancelar el turno del jueves 8 a las 10:00 hs?")), "cancelar_o_reprogramar", True),
    ("13 override existente sigue andando", "Quiero cambiar el turno para la tarde", "consulta_general", "(sin mensajes previos)", "cancelar_o_reprogramar", False),
    ("14 contexto vacio real + 'Si': sigue el Router", "Si", "confirmar_post_recordatorio", "(sin mensajes previos)", "confirmar_post_recordatorio", False),
    ("15 'otro horario' tras read-back de reserva: sigue agendando", "No, mejor otro horario", "consulta_general", ctx(("B", RB_RESERVA)), "agendar_nuevo", True),
    ("16 'ninguno me sirve' tras horarios: sigue el Router", "Ninguno me sirve", "consulta_general", ctx(("P", "Quiero un turno"), ("B", SLOTS)), "consulta_general", False),
]


def main():
    casos = [{"nombre": n, "texto": t, "router": r, "ctx": c, "codigo": NUEVO} for n, t, r, c, _e, _k in CASOS]
    casos.append({"nombre": "17 contexto falla: sigue el Router", "texto": "Si", "router": "confirmar_post_recordatorio", "ctx": "", "ctx_falla": True, "codigo": NUEVO})
    casos.append({"nombre": "18 SIN el cambio: el bug original", "texto": "Si\nGracias", "router": "confirmar_post_recordatorio", "ctx": CASOS[0][3], "codigo": BASE})
    with tempfile.TemporaryDirectory() as d:
        h, c = os.path.join(d, "h.mjs"), os.path.join(d, "c.json")
        open(h, "w", encoding="utf-8").write(HARNESS)
        json.dump(casos, open(c, "w", encoding="utf-8"), ensure_ascii=False)
        p = subprocess.run(["node", h, c], capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit("node fallo:\n" + p.stderr)
        res = {r["nombre"]: r for r in json.loads(p.stdout)}

    fallas = []

    def ok(cond, msg):
        print(f"  {'OK   ' if cond else 'FALLA'} {msg}")
        if not cond:
            fallas.append(msg)

    for n, _t, _r, _c, esperado, con_cont in CASOS:
        r = res[n]
        bien = r.get("intent") == esperado and (r.get("continuidad") is not None) == con_cont
        ok(bien, f"{n} → {r.get('intent')} ({r.get('continuidad')}){'' if bien else '   <<< esperaba ' + esperado}")
    r = res["17 contexto falla: sigue el Router"]
    ok(r.get("intent") == "confirmar_post_recordatorio" and not r.get("continuidad"), "17 contexto falla: sigue el Router")
    r = res["18 SIN el cambio: el bug original"]
    ok(r.get("intent") == "confirmar_post_recordatorio", "18 sin el cambio se reproduce el bug (→ confirmar_post_recordatorio)")
    print("\nTODO OK" if not fallas else f"\n{len(fallas)} FALLAS")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
