# -*- coding: utf-8 -*-
"""
test_directrices_nodos.py — 2026-10-05

Corre con node el JS REAL que agrega scripts/apply_agente_directrices_n8n.py (mismas constantes que se suben a n8n),
mockeando $input / $() / console. Sin red, sin base. Cubre:
  - Gate Canned Directo: saludo solo en conversacion nueva -> texto de la directriz; con conversacion previa, sin fila,
    con pedido ("hola, quiero un turno") o si el contexto falla -> NO responde (sigue el flujo normal).
  - Extraer Horarios y Precio: expone dir_menu_bienvenida / dir_notas, con valor por defecto si la fila falta o esta vacia.
  - Armar filas canned: dos filas LangChain validas (human + ai) y [] si no hay respuesta.
  - Prompt del General: la expresion de notas devuelve '' sin notas y el bloque completo con notas.
  - Los reemplazos se niegan a aplicarse dos veces o sobre codigo inesperado.

USO:
    python tests/test_directrices_nodos.py
"""
import json, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import apply_agente_directrices_n8n as A  # noqa: E402
from directrices_def import MENU_DEFAULT  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

HARNESS = r"""
import fs from 'node:fs';
const casos = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const salida = [];
for (const c of casos) {
  const fn = new AsyncFunction('$input', '$', 'console', c.codigo);
  const items = (c.items || []).map(j => ({ json: j }));
  const $input = { all: () => items, first: () => items[0] };
  const $ = (nombre) => {
    const d = c.nodos && c.nodos[nombre];
    if (d === undefined) throw new Error(`nodo desconocido ${nombre}`);
    if (d === '__error__') throw new Error(`No path back to referenced node '${nombre}'`);
    return { first: () => ({ json: d }), item: { json: d }, isExecuted: true };
  };
  try {
    const res = await fn($input, $, { log() {} });
    salida.push({ nombre: c.nombre, res: res === undefined ? null : res.map(r => r.json) });
  } catch (e) { salida.push({ nombre: c.nombre, error: String(e && e.message || e) }); }
}
process.stdout.write(JSON.stringify(salida));
"""

PRELUDIO_GATE = (
    "const item = { json: { skip: false, reason: 'default_pass' } };\n"
    "const text = ($('Preparar Mensaje Final').first().json.text || '').toString().trim();\n"
    "const norm = s => s.normalize('NFD').replace(/\\p{Diacritic}/gu, '').toLowerCase();\n"
    "const t = norm(text);\n"
)
CIERRE_GATE = "\nreturn [{ json: { ...item.json, direct_canned: false, siguio_flujo: true } }];\n"
MENU_PANEL = "Hola! Soy Asiri 🤗\n\nEste es el menú que escribió la Dra.\n1. Turnos\n2. Precios"
ROW_MENU = {"id": "dir:menu_bienvenida", "contenido": MENU_PANEL}
ROW_ALIAS = {"id": "24", "contenido": "Alias: dra.raquel.aurea."}

BASE_EXTRAER = r"""const rows = $input.all().map(i => i.json);
const original = { intent: 'consulta_general', text: 'hola' };
function porId(id) { return rows.find(r => String(r.id) === String(id)); }
const horarios = 'h', precio_consulta = '$1', direccion = 'd', cuota_mensual = '$2', precio_contencion = '$3';
const pago_titular = 't', pago_cuit = 'c', pago_alias = 'a', pago_cbu = 'b', pago_cuenta = 'n', pago_banco = 'x';

return [{ json: { ...original, horarios, precio_consulta, direccion, cuota_mensual, precio_contencion, pago_titular, pago_cuit, pago_alias, pago_cbu, pago_cuenta, pago_banco } }];
"""


def correr(casos):
    with tempfile.TemporaryDirectory() as d:
        h, c = os.path.join(d, "h.mjs"), os.path.join(d, "c.json")
        open(h, "w", encoding="utf-8").write(HARNESS)
        json.dump(casos, open(c, "w", encoding="utf-8"), ensure_ascii=False)
        p = subprocess.run(["node", h, c], capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit("node fallo:\n" + p.stderr)
        return {r["nombre"]: r for r in json.loads(p.stdout)}


def gate(nombre, texto, ctx, items, ctx_falla=False):
    nodos = {"Preparar Mensaje Final": {"text": texto}, "Build Router Context": "__error__" if ctx_falla else {"ctx": ctx}}
    return {"nombre": nombre, "codigo": PRELUDIO_GATE + A.GATE_SNIPPET + CIERRE_GATE, "items": items, "nodos": nodos}


def main():
    casos = [
        gate("saludo nuevo", "Hola", "", [ROW_ALIAS, ROW_MENU]),
        gate("saludo con signos y emoji", "¡Buenas tardes! 👋", "(sin contexto)", [ROW_ALIAS, ROW_MENU]),
        gate("buen dia sin tilde", "buen dia", "", [ROW_MENU]),
        gate("saludo con conversacion previa", "Hola", "PACIENTE: hola\n---\nBOT: menu", [ROW_MENU]),
        gate("contexto falla", "Hola", "", [ROW_MENU], ctx_falla=True),
        gate("sin fila de menu", "Hola", "", [ROW_ALIAS]),
        gate("fila de menu vacia", "Hola", "", [{"id": "dir:menu_bienvenida", "contenido": "  "}]),
        gate("saludo con pedido", "Hola, quiero un turno", "", [ROW_MENU]),
        gate("pregunta de precio", "Cuanto sale la consulta", "", [ROW_MENU]),
        {"nombre": "extraer con directrices", "codigo": A.transformar_extraer(BASE_EXTRAER),
         "items": [{"id": "dir:menu_bienvenida", "contenido": "  Menu del panel  "}, {"id": "dir:notas_para_asiri", "contenido": "Hablar de Invisalign solo en consulta."}]},
        {"nombre": "extraer sin filas", "codigo": A.transformar_extraer(BASE_EXTRAER), "items": [{"id": "20", "contenido": "x"}]},
        {"nombre": "extraer con filas vacias", "codigo": A.transformar_extraer(BASE_EXTRAER),
         "items": [{"id": "dir:menu_bienvenida", "contenido": ""}, {"id": "dir:notas_para_asiri", "contenido": "   "}]},
        {"nombre": "armar ok", "codigo": A.ARMAR_JS, "items": [{"output": "Hola! texto fijo, con comas", "reason": "menu_bienvenida"}],
         "nodos": {"Preparar Mensaje Final": {"phone": "549111", "text": "Hola"}}},
        {"nombre": "armar sin respuesta", "codigo": A.ARMAR_JS, "items": [{"output": ""}],
         "nodos": {"Preparar Mensaje Final": {"phone": "549111", "text": "Hola"}}},
    ]
    # expresion de notas del prompt del General (se evalua el cuerpo de {{ ... }})
    expr = A.GENERAL_ESTILO_NUEVO.split("{{ ")[1].split(" }}")[0]
    casos.append({"nombre": "notas vacias", "codigo": f"return [{{ json: {{ v: ({expr}) }} }}];", "nodos": {"Extraer Horarios y Precio": {"dir_notas": ""}}})
    casos.append({"nombre": "notas con texto", "codigo": f"return [{{ json: {{ v: ({expr}) }} }}];", "nodos": {"Extraer Horarios y Precio": {"dir_notas": "Pauta X"}}})
    r = correr(casos)

    fallas = []

    def ok(cond, msg):
        print(f"  {'OK   ' if cond else 'FALLA'} {msg}")
        if not cond:
            fallas.append(msg)

    print("Gate Canned Directo — menu de bienvenida")
    for nom in ("saludo nuevo", "saludo con signos y emoji", "buen dia sin tilde"):
        x = r[nom]["res"][0]
        ok(x.get("direct_canned") is True and x.get("reason") == "menu_bienvenida" and x.get("output") == MENU_PANEL, f"{nom}: responde el texto de la directriz tal cual")
    for nom in ("saludo con conversacion previa", "contexto falla", "sin fila de menu", "fila de menu vacia", "saludo con pedido", "pregunta de precio"):
        x = r[nom]["res"][0]
        ok(x.get("siguio_flujo") is True and not x.get("output"), f"{nom}: NO responde, sigue el flujo normal")

    print("Extraer Horarios y Precio")
    x = r["extraer con directrices"]["res"][0]
    ok(x["dir_menu_bienvenida"] == "Menu del panel" and x["dir_notas"] == "Hablar de Invisalign solo en consulta.", "con filas: toma los valores (sin espacios sobrantes)")
    ok(x["horarios"] == "h" and x["precio_consulta"] == "$1" and x["intent"] == "consulta_general", "no pisa los campos existentes")
    for nom in ("extraer sin filas", "extraer con filas vacias"):
        x = r[nom]["res"][0]
        ok(x["dir_menu_bienvenida"] == MENU_DEFAULT and x["dir_notas"] == "", f"{nom}: valor por defecto (nunca vacio)")

    print("Guardar canned en memoria")
    x = r["armar ok"]["res"][0]
    h, a = json.loads(x["human_msg"]), json.loads(x["ai_msg"])
    ok(x["session_id"] == "549111" and h["type"] == "human" and h["content"] == "Hola", "fila del paciente en formato LangChain")
    ok(a["type"] == "ai" and a["content"] == "Hola! texto fijo, con comas" and a["additional_kwargs"]["source"] == "canned" and a["tool_calls"] == [], "fila del bot en formato LangChain (source=canned)")
    ok("," not in x["session_id"] + "", "session_id sin comas (el parametro de n8n se separa por comas)")
    ok(r["armar sin respuesta"]["res"] == [], "sin respuesta: no escribe nada")

    print("Prompt del General")
    ok(r["notas vacias"]["res"][0]["v"] == "", "sin notas: el bloque no aparece")
    v = r["notas con texto"]["res"][0]["v"]
    ok(v.startswith("INSTRUCCIONES ADICIONALES DE LA CLÍNICA") and "Pauta X" in v and v.endswith("\n\n"), "con notas: bloque completo")

    print("Salvaguardas de los reemplazos")
    for nom, fn, arg in (("extraer ya aplicado", A.transformar_extraer, A.transformar_extraer(BASE_EXTRAER)),
                         ("gate ya aplicado", A.transformar_gate, PRELUDIO_GATE + A.GATE_SNIPPET + "const mencionaAlias = 1;"),
                         ("extraer inesperado", A.transformar_extraer, "return [];"),
                         ("gate inesperado", A.transformar_gate, "return [];")):
        try:
            fn(arg)
            ok(False, f"{nom}: debia abortar")
        except SystemExit:
            ok(True, f"{nom}: aborta")

    print(f"\n{'TODO OK' if not fallas else str(len(fallas)) + ' FALLAS'}")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
