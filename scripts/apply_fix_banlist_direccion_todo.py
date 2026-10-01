"""
Fix del 2026-10-01: el Banlist bloqueaba la direccion cuando el paciente contestaba "Todo" a un menu
que el propio bot le habia ofrecido (con "direccion" como una de las opciones), en vez de repetir la
palabra "direccion". Caso real: exec de session_id terminado en ...1991, 01/10 00:44, escalacion_log id
258. Nadie habia respondido al paciente cuando se detecto.

CAMBIO (unico nodo, unico campo): 'Banlist Validator' en el v6. Se agrega una SEGUNDA condicion para
`pacientePidioDireccion`, ademas de la ya existente (paciente escribe la palabra "direccion" o
equivalente): si el BOT ofrecio "direccion" en su turno INMEDIATO ANTERIOR (via el contexto que ya arma
'Build Router Context', que corre antes en la misma ejecucion) Y el paciente contesta con un "todo"
GENERICO Y CORTO (todo / todos / toda / las dos / ambas / etc).

DELIBERADAMENTE NO se agrega "si"/"dale"/"ok" sueltos a esta excepcion: esas son justo el tipo de
respuesta que aparecio en el incidente real de mayo (confirmacion de turno, no pedido de info) y
agregar una excepcion ahi reabriria exactamente ese riesgo. Esta excepcion es segura por construccion:
el bot NUNCA persiste en memoria un output que el propio Banlist bloqueo (la fila que queda es el
canned de escalacion), asi que 'Build Router Context' solo puede ver menciones de "direccion" que YA
pasaron el filtro antes (legitimas) — nunca el patron peligroso tipo "venite, Balcarce 37".

USO:
  python scripts/apply_fix_banlist_direccion_todo.py            # dry-run (default), no toca n8n
  python scripts/apply_fix_banlist_direccion_todo.py --apply    # backup PRE/POST + PUT + verificacion
  python scripts/apply_fix_banlist_direccion_todo.py --rollback workflows/history/<PRE>.json
"""
import argparse, difflib, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_media_entrantes import api, clean_settings, PUT_KEYS, WF_ID  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
LABEL = "banlist_direccion_todo"
NODO = "Banlist Validator"
WEBHOOK = "Webhook - Evolution API"

ANCLA = (
    "const pacientePidioDireccion = /\\b(d[oó]nde\\s*(es|queda|est[aá]n?|ubicad|esta\\s*ubicad)"
    "|a?\\s*d[oó]nde\\s+(voy|tengo\\s+que\\s+ir)|direcci[oó]n|ubicaci[oó]n|c[oó]mo\\s*lleg(ar|o|amos)?"
    "|en\\s*qu[eé]\\s*(direcci[oó]n|calle|piso)|qu[eé]\\s*direcci[oó]n|\\bubi\\b|\\bmaps\\b)"
    "\\b/i.test(pacienteMsg);"
)

# Reemplazamos la linea de ANCLA agregando el bloque de contexto antes y la condicion OR al final.
REEMPLAZO = (
    "// FIX 2026-10-01: si el BOT ofrecio \"direccion\" en su turno ANTERIOR (menu de info) y el\n"
    "// paciente contesta con un \"todo\" GENERICO (sin repetir la palabra), contarlo como pedido\n"
    "// explicito. Acotado a CATCH-ALLS CORTOS (todo/todos/ambas/las dos): \"si\"/\"dale\"/\"ok\" sueltos\n"
    "// quedan AFUERA a proposito — es el tipo de respuesta del incidente real de mayo (confirmacion de\n"
    "// turno, no pedido de info) y destrabarlos ahi reabriria ese riesgo. Seguro por construccion: la\n"
    "// memoria NUNCA guarda un output que el propio Banlist bloqueo (queda el canned de escalacion en\n"
    "// su lugar), asi que el contexto solo puede traer menciones de \"direccion\" ya legitimas.\n"
    "let botOfrecioDireccionAntes = false;\n"
    "try {\n"
    "  const ctx = ($('Build Router Context').first().json.ctx || '').toString();\n"
    "  const turnos = ctx.split(/\\n---\\n/);\n"
    "  const ultimoBot = [...turnos].reverse().find((t) => t.trim().toLowerCase().startsWith('bot:'));\n"
    "  botOfrecioDireccionAntes = !!(ultimoBot && /\\bdirecci[oó]n\\b/i.test(ultimoBot));\n"
    "} catch (e) { botOfrecioDireccionAntes = false; }\n"
    "const esRespuestaTodoGenerica = /^\\s*(todo|todos|toda|todas|las\\s+dos|ambas?|lo\\s+que\\s+sea"
    "|toda\\s+la\\s+informaci[oó]n)\\s*[.!]?\\s*$/i.test(pacienteMsg);\n\n"
    "const pacientePidioDireccion = /\\b(d[oó]nde\\s*(es|queda|est[aá]n?|ubicad|esta\\s*ubicad)"
    "|a?\\s*d[oó]nde\\s+(voy|tengo\\s+que\\s+ir)|direcci[oó]n|ubicaci[oó]n|c[oó]mo\\s*lleg(ar|o|amos)?"
    "|en\\s*qu[eé]\\s*(direcci[oó]n|calle|piso)|qu[eé]\\s*direcci[oó]n|\\bubi\\b|\\bmaps\\b)"
    "\\b/i.test(pacienteMsg)\n"
    "  || (esRespuestaTodoGenerica && botOfrecioDireccionAntes);"
)


def mostrar_diff(antes, despues):
    for linea in difflib.unified_diff(antes.splitlines(), despues.splitlines(), lineterm="", n=2):
        if linea.startswith(("---", "+++")):
            continue
        print("  " + linea[:200])


def build(wf):
    nodo = next((n for n in wf["nodes"] if n["name"] == NODO), None)
    if nodo is None:
        sys.exit(f"ERROR: no encontré el nodo {NODO!r} en el v6.")
    antes = nodo["parameters"]["jsCode"]
    if "botOfrecioDireccionAntes" in antes:
        print("  (ya aplicado: el fix ya está en el jsCode vivo)")
        return wf, antes, antes
    if antes.count(ANCLA) != 1:
        sys.exit(f"ERROR: el ancla de pacientePidioDireccion aparece {antes.count(ANCLA)} veces (esperaba 1).")
    despues = antes.replace(ANCLA, REEMPLAZO)
    nodo["parameters"]["jsCode"] = despues
    return wf, antes, despues


def verify(wf):
    code = next(n for n in wf["nodes"] if n["name"] == NODO)["parameters"]["jsCode"]
    # El regex de catch-all (línea con "esRespuestaTodoGenerica =") es la única parte nueva que
    # decide la excepción; "sí"/"dale"/"ok" sueltos NO deben estar en esa lista de alternativas.
    i = code.find("esRespuestaTodoGenerica = /")
    regex_catchall = code[i: code.find(";", i)] if i != -1 else ""
    return {
        "fix_presente": "botOfrecioDireccionAntes" in code and "esRespuestaTodoGenerica" in code,
        "exencion_original_intacta": "d[oó]nde\\s*(es|queda" in code,
        "balcarce_banlist_intacto": "balcarce" in code.lower(),
        "catchall_no_incluye_si_dale_ok": not re.search(r"\b(s[ií]|dale|ok|listo|bueno)\b", regex_catchall, re.I),
        "banlist_otros_patrones_intactos": "venite/veni" in code and "los esperamos" in code,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback", metavar="PRE.json")
    args = ap.parse_args()

    if args.rollback:
        import json
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

    print(f"\n── {NODO} · jsCode  ({len(antes)} -> {len(despues)} chars)")
    mostrar_diff(antes, despues)
    print(f"\nnodos: {len(wf['nodes'])} (sin cambios) · conexiones: sin cambios")
    print(f"verificación: {verify(wf)}")

    if not args.apply:
        print("\n[DRY-RUN] no se tocó n8n. Para aplicar: --apply")
        return 0

    import json
    ts = time.strftime("%Y%m%d_%H%M%S")
    actual = api(f"/workflows/{WF_ID}")
    if actual.get("versionId") != version:
        sys.exit("ERROR: el v6 cambió entre el GET y el PUT. Volvé a correr el dry-run.")
    (HIST / f"v6_PRE_{LABEL}_{ts}.json").write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PRE backup -> {HIST / f'v6_PRE_{LABEL}_{ts}.json'}")

    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = clean_settings(wf)
    wh = next(n for n in body["nodes"] if n["name"] == WEBHOOK)
    assert wh.get("webhookId") == "evo-webhook-v2", "webhookId perdido — abortado"
    api(f"/workflows/{WF_ID}", method="PUT", payload=body)

    after = api(f"/workflows/{WF_ID}")
    (HIST / f"v6_POST_{LABEL}_{ts}.json").write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    v = verify(after)
    print(f"POST backup -> {HIST / f'v6_POST_{LABEL}_{ts}.json'}")
    print(f"verificación post-PUT: {v}")
    if not all(v.values()):
        sys.exit("ERROR: la verificación post-PUT falló. Revisar / rollback.")
    print(f"✅ aplicado: {len(after['nodes'])} nodos, activo={after['active']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
