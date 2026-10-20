# -*- coding: utf-8 -*-
"""test_webhook_prueba.py — (08/10) el webhook de prueba del v7 solo acepta el celular de Lucas o celulares sintéticos y siempre corre en sombra.
Pedido de Lucas después del incidente del 06/10 (la retrospectiva usaba el celular de cada paciente). uso: python tests/test_webhook_prueba.py"""
import importlib.util, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
spec = importlib.util.spec_from_file_location("crear", ROOT / "scripts" / "crear_v7_en_n8n.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
wf = m.wf_test({"cerebro": "X", "confirmar_turno": "Y"}, "ruta")
js = next(n for n in wf["nodes"] if n["name"] == "Despachar")["parameters"]["jsCode"]

CASOS = [
    ("W1 celular de Lucas → cerebro en sombra", {"phone": "5491161461034", "texto": "hola"}, "r.workflow_id === 'X' && r.modo === 'sombra'"),
    ("W2 celular sintético de paciente nuevo", {"phone": "5499990000123"}, "r.workflow_id === 'X'"),
    ("W3 celular sintético del arnés (Dana) → herramienta", {"destino": "confirmar_turno", "tel": "5490000000651"}, "r.workflow_id === 'Y'"),
    ("W4 celular de un PACIENTE → rechazado (cerebro)", {"phone": "5493880000000", "texto": "confirmo"}, "!!r.error && !r.workflow_id"),
    ("W5 celular de un PACIENTE → rechazado (confirmar_turno)", {"destino": "confirmar_turno", "tel": "5493880000000"}, "!!r.error && !r.workflow_id"),
    ("W6 celular de un PACIENTE → rechazado también el reinicio (borra claves de Redis)", {"destino": "reset", "tel": "5493880000000"}, "!!r.error && !r.reset"),
    ("W7 sin teléfono → rechazado", {"texto": "hola"}, "!!r.error"),
    ("W8 pedir modo vivo no sirve: siempre sombra", {"phone": "5491161461034", "modo": "vivo"}, "r.modo === 'sombra'"),
]
prog = "const js = " + json.dumps(js) + ";\nconst correr = (body) => new Function('$input', js)({ first: () => ({ json: { body } }) })[0].json;\nconst out = [];\n"
for nombre, body, cond in CASOS:
    prog += f"{{ const r = correr({json.dumps(body)}); out.push([{json.dumps(nombre)}, !!({cond}), r]); }}\n"
prog += "console.log(JSON.stringify(out));"
res = json.loads(subprocess.run(["node", "-e", prog], capture_output=True, text=True, encoding="utf-8").stdout)
fallas = 0
for nombre, ok, r in res:
    fallas += not ok
    print(f"  {'ok   ' if ok else 'FALLA'} {nombre}" + ("" if ok else f" → {json.dumps(r, ensure_ascii=False)[:200]}"))
print(f"\n{len(res) - fallas}/{len(res)} {'TODO OK' if not fallas else f'{fallas} FALLAS'}")
sys.exit(1 if fallas else 0)
