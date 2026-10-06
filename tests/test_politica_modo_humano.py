# -*- coding: utf-8 -*-
"""
test_politica_modo_humano.py — 2026-10-05

Corre con node el JS REAL de scripts/apply_politica_modo_humano.py (mockeando $input / $()). Sin red. Cubre:
  - `Decidir Takeover` (Helper): cuando una escalacion SILENCIA al bot y cuando solo avisa.
  - `Parse Intent`: "¿Quiere que le busque las fechas mas proximas?" + "Si" (caso real) y que lo anterior sigue igual.
  - La descripcion nueva de `escalar_a_secretaria`: ya no promete silenciar ni nombra Chatwoot.

PRUEBA EN VIVO (despues de aplicar), desde el numero de prueba, con la ficha de prueba y SIN tocar el turno real de la paciente (jueves 22/10 9:20):
  1. Un pago: mandar "Ya transferi, te paso el comprobante" → el grupo recibe el aviso y el bot SIGUE respondiendo (no queda en modo humano).
  2. "Quiero hablar con una persona" → el bot avisa y queda en modo humano.
  3. Un cambio de turno completo (pedir cambio → elegir horario → "Si") → termina reprogramado sin pasar a la secretaria. Anular lo que quede reservado.

USO:  python tests/test_politica_modo_humano.py
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import apply_politica_modo_humano as P  # noqa: E402
import apply_fix_continuidad_flujo as A  # noqa: E402
import apply_fix_ruteo_consultas_cambio as R  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

HARNESS = r"""
import fs from 'node:fs';
const casos = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const salida = [];
for (const c of casos) {
  const fn = new AsyncFunction('$input', '$', 'console', c.codigo);
  const items = [{ json: { pasa: 'si' } }];
  const $input = c.router !== undefined ? { first: () => ({ json: { output: c.router } }) } : { first: () => items[0], all: () => items };
  const $ = (n) => {
    if (n === 'Webhook') return { first: () => ({ json: c.webhook }) };
    if (n === 'Preparar Mensaje Final') return { first: () => ({ json: { text: c.texto } }) };
    if (n === 'Build Router Context') return { first: () => ({ json: { ctx: c.ctx } }) };
    throw new Error('nodo desconocido ' + n);
  };
  try { const r = await fn($input, $, { log() {} }); salida.push({ nombre: c.nombre, n: r.length, intent: r[0] && r[0].json.intent, continuidad: r[0] && (r[0].json.continuidad ?? null) }); }
  catch (e) { salida.push({ nombre: c.nombre, error: String(e.message || e) }); }
}
process.stdout.write(JSON.stringify(salida));
"""

BASE = open(os.path.join(ROOT, "tests", "fixtures", "parse_intent_antes.js"), encoding="utf-8").read()
PARSE = R.transformar_parse(P.transformar_parse_busqueda(A.transformar_parse(BASE)))


def ctx(*t):
    return "\n---\n".join(("PACIENTE: " if q == "P" else "BOT: ") + x for q, x in t)


BUSQUEDA = "Esta semana no tenemos turnos disponibles, disculpe. ¿Quiere que le busque las fechas más próximas?"


def takeover(nombre, esperado, **wh):
    return (nombre, esperado, {"nombre": nombre, "codigo": P.DECIDIR_TAKEOVER_JS, "webhook": wh})


def main():
    take = [
        takeover("tomar=true del triaje (query)", 1, query={"phone": "549", "resumen": "Urgencia: bracket suelto", "tomar": "true"}),
        takeover("tomar=true aunque el resumen no diga nada", 1, query={"resumen": "x", "tomar": "true"}),
        takeover("pidio hablar con una persona", 1, query={"resumen": "Paciente pidio hablar con una persona"}),
        takeover("quiere hablar con la secretaria (acentos)", 1, query={"resumen": "El paciente quiere hablar con la secretaria"}),
        takeover("queja", 1, query={"resumen": "Queja por la demora en la atencion"}),
        takeover("baja de datos", 1, query={"resumen": "Paciente pidio baja de datos / no ser contactado (Ley 25.326)"}),
        takeover("dolor / urgencia en el resumen del modelo", 1, query={"resumen": "Paciente con dolor agudo, requiere atencion prioritaria"}),
        takeover("viene en body en lugar de query", 1, body={"resumen": "Urgencia con sangrado", "tomar": "true"}),
        takeover("comprobante de pago: SOLO aviso", 0, query={"resumen": "Paciente envio comprobante de pago para verificar e imputar al turno"}),
        takeover("lista de espera: SOLO aviso", 0, query={"resumen": "Lista de espera: quiere adelantar si se libera un turno antes del 22/10"}),
        takeover("no pude resolver: SOLO aviso", 0, query={"resumen": "Paciente confirma pero no tiene turno activo en agenda"}),
        takeover("error tecnico: SOLO aviso", 0, query={"resumen": "Bot tuvo error tecnico (max iterations / agent stopped)"}),
        takeover("banlist bloqueo: SOLO aviso", 0, query={"resumen": "Banlist bloqueo una respuesta del bot (venite). Revisar conversacion"}),
        takeover("gate humano final (silencioso): no re-silencia", 0, query={"resumen": "El bot detecto que el chat esta en Modo Humano y no envio su respuesta", "silencioso": "true"}),
        takeover("sin parametros: SOLO aviso", 0, query={}),
    ]
    parse = [
        # 2026-10-05: la pregunta "¿le busco las fechas mas proximas?" la hace el agente de agenda → el "Si" vuelve a el (el sub-WF contestaba
        # "Tu proximo turno es..."; medido con el modelo real en tests/test_flujo_dana_subwf.py, turno T4).
        ("P1 REAL: 'Si' a '¿le busco las fechas mas proximas?' en un cambio → agente de agenda", "agendar_nuevo",
         {"nombre": "P1", "codigo": PARSE, "router": "agendar_nuevo", "texto": "Si",
          "ctx": ctx(("P", "Buen dia me pude cambiar ese turno"), ("B", "Tenemos los próximos turnos disponibles: * Jueves 22 8:00"), ("P", "En esta semana excepto el 8 que fecha"), ("B", BUSQUEDA))}),
        ("P2: 'Si' a la misma pregunta pero en una reserva nueva", "agendar_nuevo",
         {"nombre": "P2", "codigo": PARSE, "router": "confirmar_post_recordatorio", "texto": "Si",
          "ctx": ctx(("P", "Quiero sacar un turno"), ("B", BUSQUEDA))}),
        ("P3: 'Ninguno me sirve' no se pisa", "consulta_general",
         {"nombre": "P3", "codigo": PARSE, "router": "consulta_general", "texto": "Ninguno me sirve", "ctx": ctx(("P", "Quiero un turno"), ("B", BUSQUEDA))}),
        ("P4: recordatorio + 'Confirmo' sigue en Confirmar", "confirmar_post_recordatorio",
         {"nombre": "P4", "codigo": PARSE, "router": "confirmar_post_recordatorio", "texto": "Confirmo",
          "ctx": ctx(("B", "Estimada Paciente, Le recordamos su turno con la Dra. Rodríguez Raquel. Le pedimos confirmar su asistencia."))}),
    ]
    casos = [c for _n, _e, c in take] + [c for _n, _e, c in parse]
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

    print("Decidir Takeover (Helper)")
    for nombre, esperado, _c in take:
        r = res[nombre]
        ok(r.get("n") == esperado, f"{nombre} → {'SILENCIA al bot' if r.get('n') == 1 else 'solo avisa'}")
    print("Parse Intent")
    for nombre, esperado, c in parse:
        r = res[c["nombre"]]
        ok(r.get("intent") == esperado, f"{nombre} → {r.get('intent')} ({r.get('continuidad')})")
    print("Descripcion de escalar_a_secretaria")
    d = P.TOOL_DESC_NUEVA.lower()
    ok("chatwoot" not in d and "label" not in d, "ya no nombra Chatwoot ni el label")
    ok("no silencia al bot" in d, "dice que NO silencia al bot")
    ok("pidio hablar con una persona" in d and "queja" in d and "urgencia" in d, "explica las frases que silencian")
    ok("resumen" in d and "una sola vez por turno" in d, "conserva el argumento resumen y el limite de una llamada por turno")
    print("\nTODO OK" if not fallas else f"\n{len(fallas)} FALLAS")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
