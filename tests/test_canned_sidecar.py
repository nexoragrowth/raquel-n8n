# -*- coding: utf-8 -*-
"""
test_canned_sidecar.py — 2026-09-02

Corre el JS REAL del nodo `Canned Sidecar` (importado de
scripts/apply_canned_sidecar.py :: SIDECAR_JS) con node, mockeando el entorno de
n8n ($input / $() / console). Fuente unica: si alguien edita el nodo, el test corre
el codigo editado — no una reimplementacion que puede divergir.

Casos 1 y 2 son los DOS mensajes reales de produccion que fallaron
(`conversaciones` id=5747 del 2/9 y id=5406 del 28/8).

USO:
    python tests/test_canned_sidecar.py
"""
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from apply_canned_sidecar import SIDECAR_JS  # noqa: E402

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
    if (c.nodos_faltantes && c.nodos_faltantes.includes(nombre)) {
      throw new Error(`No path back to referenced node '${nombre}'`);
    }
    const data = {
      'Preparar Mensaje Final': { text: c.paciente, phone: '549000', remoteJid: 'x@s.whatsapp.net' },
      'Parse Intent': { intent: c.intent || 'confirmar_post_recordatorio' },
      'Extraer Horarios y Precio': { precio_consulta: c.precio || '$50.000', horarios: 'martes y jueves de 8 a 12' },
    }[nombre];
    if (!data) throw new Error(`nodo desconocido ${nombre}`);
    return { first: () => ({ json: data }), item: { json: data } };
  };
  const logs = [];
  const consola = { log: (...a) => logs.push(a.map(String).join(' ')) };
  try {
    const res = await fn($input, $, consola);
    salida.push({
      nombre: c.nombre,
      outputs: res.map(r => (r.json.output || '').toString()),
      sidecar: res.map(r => r.json.canned_sidecar || null),
      preserva: res.every(r => r.json.otro_campo === 'preservar'),
      logs,
    });
  } catch (e) {
    salida.push({ nombre: c.nombre, error: String(e && e.message || e) });
  }
}
process.stdout.write(JSON.stringify(salida));
"""

CONF = ("Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel 🤗\n"
        "Listo, su turno del 4 de Septiembre a las 11:10 hs queda confirmado. "
        "Cualquier consulta nos puede escribir por este medio.")

ALIAS_YA = ("El valor de la consulta es de $50.000. Si desea ir abonando, puede hacerlo al siguiente alias:\n"
            "---\ndra.raquel.aurea\n---\nTitular: Laura Raquel Rodríguez\nCBU: 1430001713001112680016")

CASOS = [
    # ---- los 2 mensajes REALES que fallaron en produccion ----
    dict(nombre="REAL 2/9 Paulina (confirmo + alias)",
         paciente="Confirmo\nPor favor pásame el alias para que te transfiera el costo de la primera consulta",
         outputs=[CONF],
         espera=dict(anexa=True, contiene=["dra.raquel.aurea", "CBU", "$50.000"], sidecar="pago",
                     conserva_original=True, no_contiene=["El valor de la consulta es de $50.000."] and [])),
    dict(nombre="REAL 28/8 (comprobante + donde transfiero + que alias)",
         paciente="Buenas tardes ahora le mando el comprobante\nA donde le hago la transferencia?\nQue alias?",
         outputs=["Recibimos su comprobante.\nLe informo a la secretaria, que verificará el pago."],
         espera=dict(anexa=True, contiene=["dra.raquel.aurea"], sidecar="pago")),

    # ---- negativos: mencion, no pedido ----
    dict(nombre="NEG mencion 'el alias sigue siendo ese'",
         paciente="El alias sigue siendo ese", outputs=[CONF], espera=dict(anexa=False)),
    dict(nombre="NEG 'Confirmo' solo",
         paciente="Confirmo", outputs=[CONF], espera=dict(anexa=False)),
    dict(nombre="NEG ya transfirio",
         paciente="ya transferí, te paso el comprobante", outputs=[CONF], espera=dict(anexa=False)),
    dict(nombre="NEG pregunta sin tema canned",
         paciente="hay turnos a la tarde?", outputs=["Le busco disponibilidad."], espera=dict(anexa=False)),
    dict(nombre="NEG cierre cortes",
         paciente="Perfecto, gracias", outputs=[CONF], espera=dict(anexa=False)),

    # ---- dedup / passthrough ----
    dict(nombre="DEDUP General ya respondio el alias",
         paciente="pasame el alias por favor", outputs=[ALIAS_YA], espera=dict(anexa=False)),
    dict(nombre="PASSTHROUGH [NO_REPLY]",
         paciente="pasame el alias", outputs=["[NO_REPLY]"], espera=dict(anexa=False)),
    dict(nombre="PASSTHROUGH urgencia",
         paciente="me duele mucho, cuanto sale la consulta?", intent="urgencia_dolor",
         outputs=["Le paso con la secretaria."], espera=dict(anexa=False)),

    # ---- precio solo, y supersede ----
    dict(nombre="PRECIO solo (sin alias)",
         paciente="cuanto sale la consulta?", outputs=["Le confirmo."],
         espera=dict(anexa=True, contiene=["El valor de la consulta es de $50.000."],
                     no_contiene=["dra.raquel.aurea", "CBU"], sidecar="precio")),
    dict(nombre="SUPERSEDE precio+alias -> solo pago",
         paciente="Confirmo. Cuánto sale? Y el alias?", outputs=[CONF],
         espera=dict(anexa=True, sidecar="pago", contiene=["dra.raquel.aurea"])),

    # ---- robustez ----
    dict(nombre="PRECIO DINAMICO desde KB (id=21)",
         paciente="pasame el alias", outputs=[CONF], precio="$99.999",
         espera=dict(anexa=True, contiene=["$99.999"])),
    dict(nombre="ROBUSTEZ nodo Extraer no corrio (camino Set NO_REPLY)",
         paciente="pasame el alias", outputs=[CONF], nodos_faltantes=["Extraer Horarios y Precio"],
         espera=dict(anexa=True, contiene=["$50.000", "dra.raquel.aurea"])),
    dict(nombre="ROBUSTEZ Preparar Mensaje Final no corrio",
         paciente="pasame el alias", outputs=[CONF], nodos_faltantes=["Preparar Mensaje Final"],
         espera=dict(anexa=False)),
    dict(nombre="ROBUSTEZ multi-item",
         paciente="pasame el alias", outputs=[CONF, "Otra parte."],
         espera=dict(anexa=True, todos=True)),
    dict(nombre="HORARIOS sigue apagado (enabled:false)",
         paciente="cuales son los horarios?", outputs=[CONF], espera=dict(anexa=False)),
]


def main():
    tmp = tempfile.mkdtemp(prefix="sidecar_test_")
    js_path = os.path.join(tmp, "sidecar.js")
    casos_path = os.path.join(tmp, "casos.json")
    harness_path = os.path.join(tmp, "harness.mjs")

    open(js_path, "w", encoding="utf-8").write(SIDECAR_JS)
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
        anexo = out != orig

        problemas = []
        if esp.get("anexa") and not anexo:
            problemas.append("esperaba anexar y no anexo")
        if not esp.get("anexa") and anexo:
            problemas.append(f"NO debia anexar pero anexo: {out[len(orig):][:120]!r}")
        if anexo and esp.get("anexa"):
            if not out.startswith(orig.strip()):
                problemas.append("no conserva intacto el texto del sub-agent")
            for s in esp.get("contiene", []):
                if s not in out:
                    problemas.append(f"falta {s!r}")
            for s in esp.get("no_contiene", []):
                if s in out:
                    problemas.append(f"no debia contener {s!r}")
            if esp.get("sidecar") and got["sidecar"][0] != esp["sidecar"]:
                problemas.append(f"sidecar={got['sidecar'][0]!r} esperaba {esp['sidecar']!r}")
            if out.count("dra.raquel.aurea") > 1:
                problemas.append("alias duplicado")
        if esp.get("todos") and not all(o != c for o, c in zip(got["outputs"], caso["outputs"])):
            problemas.append("no anexo en todos los items")
        if not got.get("preserva", True):
            problemas.append("perdio campos del item (otro_campo)")

        if problemas:
            fallos.append(f"{nombre}: " + "; ".join(problemas))
            print(f"  ✗ {nombre}: " + "; ".join(problemas))
        else:
            extra = f" [+{len(out) - len(orig)} chars]" if anexo else " [sin cambios]"
            print(f"  ✓ {nombre}{extra}")

    print()
    if fallos:
        print(f"FALLARON {len(fallos)}/{len(CASOS)}")
        sys.exit(1)
    print(f"OK — {len(CASOS)}/{len(CASOS)} casos pasan")

    print("\n=== Preview del caso REAL 2/9 (lo que hubiera recibido Paulina) ===")
    real = res["REAL 2/9 Paulina (confirmo + alias)"]["outputs"][0]
    for i, parte in enumerate([p.strip() for p in real.split("---") if p.strip()], 1):
        print(f"  [msg {i}] {parte}")


if __name__ == "__main__":
    main()
