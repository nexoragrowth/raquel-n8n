# -*- coding: utf-8 -*-
"""
test_gate_pago_tratamiento.py — 2026-09-03

Corre el JS REAL del nodo `Gate Pago Tratamiento` (importado de
scripts/apply_gate_pago_tratamiento.py :: GATE_JS) con node, mockeando el entorno
de n8n. Fuente unica, sin drift posible entre test y produccion.

Caso 1 es el mensaje REAL que fallo en produccion (`conversaciones` id=5944, exec
269717, 3/9 — Carla preguntando por el tratamiento de Tadeo).

USO:
    python tests/test_gate_pago_tratamiento.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from apply_gate_pago_tratamiento import GATE_JS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

HARNESS = r"""
import fs from 'node:fs';

const body = fs.readFileSync(process.argv[2], 'utf8');
const casos = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const fn = new AsyncFunction('$input', '$', 'console', body);

const salida = [];
for (const c of casos) {
  const items = c.outputs.map(o => ({ json: { output: o, otro_campo: 'preservar' } }));
  const $input = { all: () => items, first: () => items[0] };
  const $ = (nombre) => {
    const data = {
      'Preparar Mensaje Final': { text: c.paciente, phone: c.phone || '549000', remoteJid: 'x@s.whatsapp.net' },
      'Parse Intent': { intent: c.intent || 'consulta_general' },
    }[nombre];
    if (!data) throw new Error(`nodo desconocido ${nombre}`);
    return { first: () => ({ json: data }), item: { json: data } };
  };
  const logs = [];
  const consola = { log: (...a) => logs.push(a.map(String).join(' ')) };
  const httpCalls = [];
  const thisCtx = {
    helpers: {
      httpRequest: async (opts) => { httpCalls.push(opts); return {}; },
    },
  };
  try {
    const res = await fn.call(thisCtx, $input, $, consola);
    salida.push({
      nombre: c.nombre,
      outputs: res.map(r => (r.json.output || '').toString()),
      flag: res.map(r => r.json.gate_pago_tratamiento || false),
      preserva: res.every(r => r.json.otro_campo === 'preservar'),
      httpCalls,
      logs,
    });
  } catch (e) {
    salida.push({ nombre: c.nombre, error: String(e && e.message || e) });
  }
}
process.stdout.write(JSON.stringify(salida));
"""

GENERICO = ("Nosotros le enviamos un recordatorio de su turno dos días hábiles antes, y para "
            "confirmar su asistencia le solicitaremos abonar el valor de la consulta. Puede "
            "acercarse al consultorio a abonar en efectivo o hacer una transferencia, cómo le "
            "resulte más cómodo 😊.")

PRECIO_TRATAMIENTO_CANNED = ("El precio de brackets se evalúa en la primera consulta (vale "
                              "$50.000). ¿Querés que te coordine un turno?")

CASOS = [
    # ---- el mensaje REAL que fallo en produccion ----
    dict(nombre="REAL 3/9 Carla (abonar tratamiento de Tadeo)",
         paciente="Por otro lado tb queria saber si puedo ese lunes abonar el tratamiento de Tadeo ?",
         outputs=[GENERICO], intent="consulta_general",
         espera=dict(override=True, escala=True,
                     contiene=["Dra. Raquel", "tratamiento"],
                     no_contiene=["valor de la consulta"])),

    # ---- negativos: pago de CONSULTA (el canned original debe seguir andando) ----
    dict(nombre="NEG pago de consulta (sin tratamiento)",
         paciente="Puedo pagar el mismo dia de la consulta?", outputs=[GENERICO],
         espera=dict(override=False)),
    dict(nombre="NEG pregunta de turno sin pago",
         paciente="tiene turno el lunes?", outputs=["Le busco disponibilidad."],
         espera=dict(override=False)),
    dict(nombre="NEG 'tratamiento' sin palabra de pago",
         paciente="cuanto dura el tratamiento de Tadeo?", outputs=["Depende del caso."],
         espera=dict(override=False)),
    dict(nombre="NEG 'pago' sin tratamiento (otra oracion)",
         paciente="El tratamiento le va muy bien.\nPuedo pagar la consulta el lunes?",
         outputs=[GENERICO], espera=dict(override=False)),  # palabras en oraciones distintas

    # ---- dedup: SOLO salta si el output es EXACTO el canned que el gate produciria
    #      (senal de que la Capa 1 -- el prompt -- ya lo resolvio bien). Cualquier
    #      otra respuesta (incluida esta, un canned real que NO menciona la palabra
    #      "tratamiento" porque sustituye el nombre real) SI dispara override --
    #      a proposito, ver comentario en GATE_JS. ----
    dict(nombre="NO-DEDUP: canned real de precio (no es escalacion, debe overridear)",
         paciente="puedo abonar el tratamiento el lunes?", outputs=[PRECIO_TRATAMIENTO_CANNED],
         espera=dict(override=True, escala=True)),
    dict(nombre="DEDUP: capa 1 ya devolvio el canned exacto del gate -> no duplicar",
         paciente="puedo abonar el tratamiento el lunes?",
         outputs=["El pago del tratamiento lo coordina directamente la Dra. Raquel. Le paso su consulta para que se comunique con usted."],
         espera=dict(override=False)),
    dict(nombre="DEDUP REAL (exec 270379): capa 1 con saludo adelante -> no duplicar ni perder el saludo",
         paciente="Hola, queria saber si puedo el lunes abonar el tratamiento de mi hijo?",
         outputs=["Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel 🤗  \nEl pago del tratamiento lo coordina directamente la Dra. Raquel. Le paso su consulta para que se comunique con usted."],
         espera=dict(override=False)),

    # ---- passthrough ----
    dict(nombre="PASSTHROUGH [NO_REPLY]",
         paciente="puedo abonar el tratamiento el lunes?", outputs=["[NO_REPLY]"],
         espera=dict(override=False)),
    dict(nombre="PASSTHROUGH urgencia",
         paciente="me duele mucho, puedo pagar el tratamiento despues?", intent="urgencia_dolor",
         outputs=["Le paso con la secretaria."], espera=dict(override=False)),

    # ---- variantes de fraseo (cobertura del regex) ----
    dict(nombre="VARIANTE 'quiero pagar el tratamiento'",
         paciente="Quiero pagar el tratamiento de mi hijo, se puede en cuotas?", outputs=[GENERICO],
         espera=dict(override=True, escala=True)),
    dict(nombre="VARIANTE 'transferir el tratamiento'",
         paciente="Como hago para transferir lo del tratamiento?", outputs=[GENERICO],
         espera=dict(override=True, escala=True)),
    dict(nombre="VARIANTE con acento 'está pague'",
         paciente="Si pague el tratamiento este mes, alcanza?", outputs=[GENERICO],
         espera=dict(override=True, escala=True)),

    # ---- "cuota" (los pacientes confunden con "tratamiento", REGLA DESAMBIGUACION
    #      CUOTA del 7/8) debe disparar igual, y nombres especificos de tratamiento ----
    dict(nombre="VARIANTE 'puedo pagar la cuota el lunes'",
         paciente="Puedo pagar la cuota el lunes?", outputs=[GENERICO],
         espera=dict(override=True, escala=True)),
    dict(nombre="VARIANTE nombre especifico 'pagar los brackets'",
         paciente="Queria saber si puedo abonar los brackets este viernes", outputs=[GENERICO],
         espera=dict(override=True, escala=True)),
    dict(nombre="NEG 'cuanto sale la cuota' (pregunta de PRECIO, no de pago-timing, ya la maneja REGLA DESAMBIGUACION CUOTA)",
         paciente="Cuanto sale la cuota mensual?", outputs=["El valor de la cuota mensual es de $70.000."],
         espera=dict(override=False)),

    # ---- robustez ----
    dict(nombre="ROBUSTEZ multi-item",
         paciente="puedo abonar el tratamiento el lunes?", outputs=[GENERICO, "Otra parte."],
         espera=dict(override=True, todos=True)),
    dict(nombre="ROBUSTEZ texto vacio (item sin output)",
         paciente="puedo abonar el tratamiento el lunes?", outputs=[""],
         espera=dict(override=False)),
]


def main():
    tmp = tempfile.mkdtemp(prefix="gate_test_")
    js_path = os.path.join(tmp, "gate.js")
    casos_path = os.path.join(tmp, "casos.json")
    harness_path = os.path.join(tmp, "harness.mjs")

    open(js_path, "w", encoding="utf-8").write(GATE_JS)
    open(harness_path, "w", encoding="utf-8").write(HARNESS)
    open(casos_path, "w", encoding="utf-8").write(json.dumps(CASOS, ensure_ascii=False))

    r = subprocess.run(["node", harness_path, js_path, casos_path],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print("ERROR corriendo node:\n", r.stderr)
        sys.exit(1)

    res = {x["nombre"]: x for x in json.loads(r.stdout)}
    fallos = []

    for caso in CASOS:
        nombre = caso["nombre"]
        got = res[nombre]
        esp = caso["espera"]
        orig = caso["outputs"][0]

        if got.get("error"):
            fallos.append(f"{nombre}: EXCEPCION {got['error']}")
            print(f"  ✗ {nombre}: EXCEPCION {got['error']}")
            continue

        out = got["outputs"][0]
        cambio = out != orig

        problemas = []
        if esp.get("override") and not cambio:
            problemas.append("esperaba override y no lo hizo")
        if not esp.get("override") and cambio:
            problemas.append(f"NO debia hacer override pero lo hizo: {out[:150]!r}")
        if cambio and esp.get("override"):
            for s in esp.get("contiene", []):
                if s not in out:
                    problemas.append(f"falta {s!r} en el override")
            for s in esp.get("no_contiene", []):
                if s in out:
                    problemas.append(f"no debia contener {s!r}")
            n_calls = len(got.get("httpCalls", []))
            if esp.get("escala") and n_calls != 1:
                problemas.append(f"esperaba 1 llamada de escalacion, hubo {n_calls}")
        else:
            if got.get("httpCalls"):
                problemas.append(f"escalo sin hacer override (httpCalls={got['httpCalls']})")
        if esp.get("todos") and not all(o != c for o, c in zip(got["outputs"], caso["outputs"])):
            problemas.append("no hizo override en todos los items")
        if not got.get("preserva", True):
            problemas.append("perdio campos del item (otro_campo)")

        if problemas:
            fallos.append(f"{nombre}: " + "; ".join(problemas))
            print(f"  ✗ {nombre}: " + "; ".join(problemas))
        else:
            marca = " [OVERRIDE]" if cambio else " [passthrough]"
            print(f"  ✓ {nombre}{marca}")

    print()
    if fallos:
        print(f"FALLARON {len(fallos)}/{len(CASOS)}")
        sys.exit(1)
    print(f"OK — {len(CASOS)}/{len(CASOS)} casos pasan")

    print("\n=== Preview del caso REAL 3/9 (lo que hubiera recibido Carla) ===")
    real = res["REAL 3/9 Carla (abonar tratamiento de Tadeo)"]
    print(f"  respuesta: {real['outputs'][0]}")
    print(f"  escalacion disparada: {real['httpCalls']}")


if __name__ == "__main__":
    main()
