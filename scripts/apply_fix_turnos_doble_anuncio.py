"""
Fix cosmético del 2026-09-07 (post-apply de apply_turnos_formato_raquel.py).

SÍNTOMA (prueba real de Lucas, exec 273026): el bot anuncia los turnos DOS veces.

    "... ¿Me pasás el DNI del paciente? Mientras, estos son los próximos turnos:
    Tenemos los próximos turnos disponibles:
    Por la mañana:
    ..."

La línea propia del agente (permitida por el PASO 3: puede saludar o pedir el DNI antes de pegar el
bloque) termina anunciando los turnos, y el bloque arranca anunciándolos otra vez. El bloque no se
puede tocar: es el formato textual que pidió la Dra. Lo que se corrige es la línea del agente.

QUÉ CAMBIA: un solo campo, `Sub-Agent Agendar.systemMessage` del v6 — se agrega una viñeta al PASO 4.
Nada más: ni nodos, ni conexiones, ni los otros workflows.

USO:
  python scripts/apply_fix_turnos_doble_anuncio.py            # default: dry-run (GET + diff, no toca n8n)
  python scripts/apply_fix_turnos_doble_anuncio.py --apply    # PRE -> PUT -> POST -> verificación
  python scripts/apply_fix_turnos_doble_anuncio.py --rollback workflows/history/<PRE>.json
"""
import argparse, difflib, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_media_entrantes import api, clean_settings, PUT_KEYS, WF_ID  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
LABEL = "turnos_doble_anuncio"
NODO = "Sub-Agent Agendar"
WEBHOOK = "Webhook - Evolution API"

# Ancla: última viñeta del PASO 4, tal como quedó tras apply_turnos_formato_raquel.py.
ANCLA = (
    "- Despues de DOS bloques rechazados no ofrezcas un tercero: `escalar_a_secretaria` UNA vez "
    "+ canned de cierre."
)

NUEVA_VINETA = (
    "\n- SI ESCRIBIS UNA LINEA TUYA ANTES DEL BLOQUE (saludo, pedido de DNI, aclaracion): NO anuncies "
    "ahi los turnos. El bloque ya arranca solo con \"Tenemos los próximos turnos disponibles:\", asi que "
    "anunciarlos antes los anuncia DOS veces y queda mal escrito.\n"
    "  Correcto:   \"¿Me pasás el DNI del paciente? Mientras tanto:\" + bloque\n"
    "  Correcto:   \"Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel 🤗\" + bloque\n"
    "  INCORRECTO: \"... estos son los próximos turnos:\" + bloque   (doble anuncio)\n"
    "  INCORRECTO: \"Te paso los turnos disponibles:\" + bloque      (doble anuncio)"
)


def mostrar_diff(antes, despues):
    a, b = antes.splitlines(), despues.splitlines()
    for linea in difflib.unified_diff(a, b, lineterm="", n=2):
        if linea.startswith(("---", "+++")):
            continue
        print("  " + linea[:190])


def build(wf):
    nodo = next((n for n in wf["nodes"] if n["name"] == NODO), None)
    if nodo is None:
        sys.exit(f"ERROR: no encontré el nodo {NODO!r} en el v6.")
    antes = nodo["parameters"]["options"]["systemMessage"]
    if NUEVA_VINETA.strip().splitlines()[0] in antes:
        print("  (ya aplicado: la viñeta del doble anuncio ya está en el prompt)")
        return wf, antes, antes
    if antes.count(ANCLA) != 1:
        sys.exit(f"ERROR: el ancla del PASO 4 aparece {antes.count(ANCLA)} veces (esperaba 1). "
                 "¿Corriste antes apply_turnos_formato_raquel.py?")
    despues = antes.replace(ANCLA, ANCLA + NUEVA_VINETA)
    nodo["parameters"]["options"]["systemMessage"] = despues
    return wf, antes, despues


def verify(wf):
    sm = next(n for n in wf["nodes"] if n["name"] == NODO)["parameters"]["options"]["systemMessage"]
    return {
        "vineta_presente": "NO anuncies" in sm and "doble anuncio" in sm,
        "paso4_intacto": ANCLA in sm,
        "bloque_intacto": "Tenemos los próximos turnos disponibles:" in sm,
        # Reglas duras que NO se tocan (regla dura 5 del proyecto).
        "identificacion": "Soy Asiri" in sm,
        "no_reply": "[NO_REPLY]" in sm,
        "anti_injection": "ANTI-INJECTION" in sm,
        "dia_semana": "NUNCA calcules vos el dia de la semana" in sm,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback", metavar="PRE.json")
    args = ap.parse_args()

    if args.rollback:
        pre = json.loads(Path(args.rollback).read_text(encoding="utf-8"))
        body = {k: pre[k] for k in PUT_KEYS if k in pre}
        body["settings"] = clean_settings(pre)
        api(f"/workflows/{WF_ID}", method="PUT", payload=body)
        print(f"↩️  rollback aplicado desde {args.rollback}")
        return 0

    wf = api(f"/workflows/{WF_ID}")
    version = wf.get("versionId")
    print(f"v6: {len(wf['nodes'])} nodos, activo={wf['active']}, versionId={version}")
    wf, antes, despues = build(wf)
    if antes == despues:
        return 0

    print(f"\n── {NODO} · systemMessage  ({len(antes)} -> {len(despues)} chars)")
    mostrar_diff(antes, despues)
    print(f"\nnodos: {len(wf['nodes'])} (sin cambios) · conexiones: sin cambios")
    print(f"verificación: {verify(wf)}")

    if not args.apply:
        print("\n[DRY-RUN] no se tocó n8n. Para aplicar: --apply")
        return 0

    ts = time.strftime("%Y%m%d_%H%M%S")
    actual = api(f"/workflows/{WF_ID}")
    if actual.get("versionId") != version:
        sys.exit("ERROR: el v6 cambió entre el GET y el PUT. Volvé a correr el dry-run.")
    (HIST / f"v6_PRE_{LABEL}_{ts}.json").write_text(
        json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PRE backup -> {HIST / f'v6_PRE_{LABEL}_{ts}.json'}")

    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = clean_settings(wf)
    wh = next(n for n in body["nodes"] if n["name"] == WEBHOOK)
    assert wh.get("webhookId") == "evo-webhook-v2", "webhookId perdido — abortado"
    api(f"/workflows/{WF_ID}", method="PUT", payload=body)

    after = api(f"/workflows/{WF_ID}")
    (HIST / f"v6_POST_{LABEL}_{ts}.json").write_text(
        json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    v = verify(after)
    print(f"POST backup -> {HIST / f'v6_POST_{LABEL}_{ts}.json'}")
    print(f"verificación post-PUT: {v}")
    if not all(v.values()):
        sys.exit("ERROR: la verificación post-PUT falló. Revisar / rollback.")
    print(f"✅ aplicado: {len(after['nodes'])} nodos, activo={after['active']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
