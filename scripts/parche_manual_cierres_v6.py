# -*- coding: utf-8 -*-
"""
parche_manual_cierres_v6.py — 2026-10-06 · el parche MANUAL (para pegar en el editor de n8n) del bug de los "gracias" del v6, probado contra el código vivo del nodo.

Qué arregla (casos reales de Irina, 05-06/10): "Si , gracias" / "Bien gracias" / "Bien\\nMuchas gracias Iris" → el Sub-Agent Confirmar devuelve [NO_REPLY] (bien) pero el nodo
"Fallback Output" lo pisa con "Ya le transmito su consulta a la secretaria…" porque su lista de cierres solo conoce palabras sueltas. El parche amplía qué cuenta como cierre
(agradecimientos/despedidas con "si", "bien", un nombre o emojis); si el mensaje trae una pregunta o cualquier otra palabra, sigue como antes.

USO:  python scripts/parche_manual_cierres_v6.py          # corre las pruebas y muestra el código a pegar
No toca n8n. (No arregla el "De nada! Quedo a disposición…" del Sub-Agent General: ese se arregla con la regla de prompt que se imprime al final.)
"""
import json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

LINEA_VIEJA = "const esCierrePuro = CIERRES.includes(norm) || norm.length === 0;"
BLOQUE_NUEVO = """// FIX 2026-10-06: el cierre ya no es solo una palabra suelta. "Si , gracias", "Bien gracias", "Muchas gracias Iris", "Muchas gracias 🫂", "Ok gracias" también son cierres:
// si el agente devolvió [NO_REPLY] para eso, se respeta el silencio (antes salía "Ya le transmito su consulta a la secretaria…"). Si trae una pregunta u otra palabra, NO es cierre.
const CIERRE_PALABRAS = ['gracias', 'ok', 'oka', 'okey', 'dale', 'listo', 'perfecto', 'genial', 'buenisimo', 'excelente', 'joya', 'barbaro', 'entendido', 'chau', 'adios', 'saludos', 'abrazo', 'igualmente'];
const CIERRE_RELLENO = ['si', 'sii', 'bien', 'muy', 'muchas', 'muchisimas', 'mil', 'de', 'nada', 'acuerdo', 'a', 'usted', 'todo', 'un', 'que', 'tenga', 'buen', 'buena', 'dia', 'tarde', 'noche', 'hasta', 'luego'];
const toks = norm.replace(/[\\p{Extended_Pictographic}\\u200d\\ufe0f]/gu, ' ').replace(/[^a-z\\s]/g, ' ').replace(/\\s+/g, ' ').trim().split(' ').filter(Boolean);
const soloCierre = !/[?¿]/.test(text) && toks.length > 0 && toks.length <= 8 && toks.some((w) => CIERRE_PALABRAS.includes(w)) &&
  toks.filter((w) => !CIERRE_PALABRAS.includes(w) && !CIERRE_RELLENO.includes(w)).length <= (toks.includes('gracias') ? 1 : 0);   // a lo sumo un nombre ("Gracias Iris")
const esCierrePuro = CIERRES.includes(norm) || norm.length === 0 || soloCierre;"""

REGLA_GENERAL = """7. CIERRES (REGLA ABSOLUTA): si el mensaje es solo un agradecimiento o una despedida ("gracias", "muchas gracias", "ok", "listo", "si gracias", "bien gracias", un emoji de agradecimiento) y no hay una pregunta
   pendiente, devolvé EXACTAMENTE [NO_REPLY]. NUNCA respondas "de nada", "quedo a disposición", ni ofrezcas ayuda, turnos o controles después de un agradecimiento."""


def main():
    sc = os.path.join(ROOT, "tests", "fixtures", "fallback_output_vivo_2026-10-06.js")
    vivo = open(sc, encoding="utf-8").read()
    assert vivo.count(LINEA_VIEJA) == 1, "el Fallback Output vivo cambió: revisar a mano"
    nuevo = vivo.replace(LINEA_VIEJA, BLOQUE_NUEVO)

    casos = []
    CIERRES = ["Si , gracias", "Bien gracias", "Bien\nMuchas gracias Iris", "Muchas gracias 🫂", "Gracias", "Gracias Iris!", "Ok gracias", "Dale, gracias", "Perfecto, muchas gracias!!", "Gracias 🙏🏻", "ok", "Muchas gracias"]
    NO_CIERRES = ["Gracias, ¿cuánto sale?", "Quiero cambiar el turno", "Mi hijo tiene dolor", "No puedo ir el jueves", "Gracias pero quiero cambiar el turno", "Si quiero cambiarlo para el lunes", "Hola", "Ok el jueves a las 9"]
    for t in CIERRES:
        casos.append({"id": "C|" + t, "codigo": nuevo, "input": {"output": "[NO_REPLY]"}, "nodos": {"Preparar Mensaje Final": {"text": t}}})
    for t in NO_CIERRES:
        casos.append({"id": "N|" + t, "codigo": nuevo, "input": {"output": "[NO_REPLY]"}, "nodos": {"Preparar Mensaje Final": {"text": t}}})
    casos.append({"id": "V|viejo Si , gracias", "codigo": vivo, "input": {"output": "[NO_REPLY]"}, "nodos": {"Preparar Mensaje Final": {"text": "Si , gracias"}}})
    with tempfile.TemporaryDirectory() as d:
        c = os.path.join(d, "c.json")
        json.dump(casos, open(c, "w", encoding="utf-8"), ensure_ascii=False)
        p = subprocess.run(["node", os.path.join(ROOT, "tests", "harness_code_node.mjs"), c], capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit(p.stderr[-1500:])
        res = {r["id"]: r for r in json.loads(p.stdout)}
    fallas = 0
    print("Con el parche (agente devolvió [NO_REPLY]):")
    for t in CIERRES:
        r = res["C|" + t]
        sal = (r.get("json") or {}).get("output")
        ok = sal == "[NO_REPLY]"
        fallas += not ok
        print(f"  {'ok   ' if ok else 'FALLA'} cierre   {t!r:42} → {'silencio' if ok else sal!r}")
    for t in NO_CIERRES:
        r = res["N|" + t]
        sal = (r.get("json") or {}).get("output") or ""
        ok = sal.startswith("Hola! Ya le transmito")
        fallas += not ok
        print(f"  {'ok   ' if ok else 'FALLA'} no cierre {t!r:42} → {'aviso a la secretaria (como antes)' if ok else sal!r}")
    viejo = (res["V|viejo Si , gracias"].get("json") or {}).get("output") or ""
    print(f"  (sin el parche, 'Si , gracias' → {viejo[:60]!r})")
    print("\nTODO OK" if not fallas else f"\n{fallas} FALLAS")
    if "--imprimir" in sys.argv or not fallas:
        print("\n" + "=" * 100 + "\nPASO 1 · n8n → workflow «Agente IA v6» → nodo «Fallback Output»: BORRAR esta línea:\n\n    " + LINEA_VIEJA + "\n\ny en su lugar PEGAR:\n\n" + BLOQUE_NUEVO)
        print("\n" + "=" * 100 + "\nPASO 2 · Sub-Agent General (n8n o panel → El Agente → editor de prompts): pegar esta regla justo ANTES de «ESTILO Y TONO:»:\n\n" + REGLA_GENERAL)
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
