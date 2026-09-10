# -*- coding: utf-8 -*-
"""
Pedido de Lucas (2026-09-10): adoptar el modelo de handoff humano->bot estandar de
Intercom/Podium para clinicas: (1) cuando un humano toma la conversacion, el bot queda
pausado SIN reloj corto; (2) red de seguridad: si el chat lleva 24 h sin actividad, el
bot lo retoma solo. Hoy "Auto Reactivar Bot (1h sin humano)" devuelve el chat al bot a
la hora (ver comentario viejo en el nodo: "2026-06-24: takeover 4h -> 1h"). Este script
lo sube a 24 h para alinearlo con ese estandar.

QUE CAMBIA: un solo literal, `ONE_HOUR` en el nodo `Filtrar > 1 hora inactivas` del
workflow "Auto Reactivar Bot (1h sin humano)" (fosfga62zNaN0qrx) — de `1 * 3600` a
`24 * 3600` — mas el comentario en el codigo (fecha + motivo). Nada mas: mismos 4 nodos,
mismo cron "Cada 15 min", mismas URLs de Chatwoot, el label `no_bot` sigue siendo la
via de escape (skip-condition intacta).

NO renombra el workflow (el nombre "(1h sin humano)" queda desactualizado tras el
--apply; renombrarlo es una decision de producto aparte que no toca este script para
no mezclar dos cambios en un mismo PUT).

RIESGO A CONFIRMAR CON LUCAS ANTES DE --apply (ver docs/handoff-humano-24h-2026-09-10.md):
la tool `escalar_a_secretaria` aplica el label 'humano' de forma SINCRONICA sobre la
MISMA conversacion que el bot esta por responder (ver docs/triaje-fase2-analisis/
mapeo-read_redis_humano.md:247-266) — o sea, hoy este cron tambien destraba
auto-escalaciones del propio bot, no solo handoffs humanos reales. Pasar a 24h implica
que una auto-escalacion (no solo un humano tipeando) deja al paciente sin bot hasta 24h
salvo intervencion manual.

USO:
  python scripts/apply_auto_reactivar_24h.py             # default: dry-run (GET + diff, no toca n8n)
  python scripts/apply_auto_reactivar_24h.py --apply      # PRE -> PUT -> POST -> verificacion
  python scripts/apply_auto_reactivar_24h.py --rollback workflows/history/<PRE>.json
"""
import argparse, difflib, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_media_entrantes import api, clean_settings, PUT_KEYS  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
LABEL = "auto_reactivar_24h"

WF_ID = "fosfga62zNaN0qrx"  # "Auto Reactivar Bot (1h sin humano)" — NO el v6
NODO = "Filtrar > 1 hora inactivas"
CRON_NODE = "Cada 15 min"
NODOS_ESPERADOS = {"Cada 15 min", "Chatwoot - Convs Humano", "Filtrar > 1 hora inactivas", "Chatwoot - Label Bot"}

# Ancla: literal vivo hoy (confirmado por GET fresco 2026-09-10).
ANCLA = "const ONE_HOUR = 1 * 3600; // 2026-06-24: takeover 4h -> 1h (pedido Dra; gates R9 + label no_bot cubren anti-pisada)"
NUEVO = (
    "const ONE_HOUR = 24 * 3600; // 2026-09-10: takeover 1h -> 24h (pedido Lucas; estandar "
    "Intercom/Podium: handoff humano sin reloj corto + red de seguridad de 24h; gates R9 + "
    "label no_bot cubren anti-pisada)"
)


def mostrar_diff(antes, despues):
    a, b = antes.splitlines(), despues.splitlines()
    for linea in difflib.unified_diff(a, b, lineterm="", n=2):
        if linea.startswith(("---", "+++")):
            continue
        print("  " + linea[:190])


def build(wf):
    if len(wf["nodes"]) != 4:
        sys.exit(f"ERROR: el workflow tiene {len(wf['nodes'])} nodos (esperaba 4). Abortado.")
    nombres = {n["name"] for n in wf["nodes"]}
    if nombres != NODOS_ESPERADOS:
        sys.exit(f"ERROR: los nodos no son los esperados. Vivo: {sorted(nombres)}")
    cron = next(n for n in wf["nodes"] if n["name"] == CRON_NODE)
    if cron["type"] != "n8n-nodes-base.scheduleTrigger":
        sys.exit(f"ERROR: {CRON_NODE!r} no es scheduleTrigger (es {cron['type']!r}). Abortado.")

    nodo = next((n for n in wf["nodes"] if n["name"] == NODO), None)
    if nodo is None:
        sys.exit(f"ERROR: no encontré el nodo {NODO!r}.")
    antes = nodo["parameters"]["jsCode"]
    if "ONE_HOUR = 24 * 3600" in antes:
        print("  (ya aplicado: ONE_HOUR ya está en 24h)")
        return wf, antes, antes
    if antes.count(ANCLA) != 1:
        sys.exit(f"ERROR: el ancla del literal ONE_HOUR aparece {antes.count(ANCLA)} veces "
                 "(esperaba 1). El código del nodo cambió respecto a lo esperado — revisar a mano.")
    despues = antes.replace(ANCLA, NUEVO)
    nodo["parameters"]["jsCode"] = despues
    return wf, antes, despues


def verify(wf):
    nodo = next(n for n in wf["nodes"] if n["name"] == NODO)
    js = nodo["parameters"]["jsCode"]
    cron = next(n for n in wf["nodes"] if n["name"] == CRON_NODE)
    convs = next(n for n in wf["nodes"] if n["name"] == "Chatwoot - Convs Humano")
    label = next(n for n in wf["nodes"] if n["name"] == "Chatwoot - Label Bot")
    return {
        "one_hour_en_24h": "ONE_HOUR = 24 * 3600" in js,
        "comentario_fecha_motivo": "2026-09-10" in js and "Lucas" in js,
        # Reglas duras que NO se deben romper con este cambio.
        "cuatro_nodos": len(wf["nodes"]) == 4,
        "mismos_nodos": {n["name"] for n in wf["nodes"]} == NODOS_ESPERADOS,
        "cron_intacto": cron["type"] == "n8n-nodes-base.scheduleTrigger"
                         and cron["parameters"]["rule"]["interval"][0]["minutesInterval"] == 15,
        "no_bot_sigue_siendo_skip": "no_bot" in js and "continue" in js,
        "get_url_intacta": convs["parameters"].get("url", "").endswith(
            "conversations?labels[]=humano&status=open"),
        "post_label_bot_intacto": label["parameters"].get("url", "").endswith("/labels")
                                   and '"labels":["bot"]' in label["parameters"].get("jsonBody", ""),
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
        # Paridad con --apply (revisión 2026-09-10): antes esto no verificaba nada después del
        # PUT — un rollback que silenciosamente no tomó (versionId no cambió, o el PUT devolvió
        # 200 pero el nodo quedó igual) pasaba desapercibido justo en el camino de emergencia.
        after = api(f"/workflows/{WF_ID}")
        v = verify(after)
        print(f"↩️  rollback aplicado desde {args.rollback}")
        print(f"verificación post-rollback: {v}")
        if v["one_hour_en_24h"]:
            sys.exit("ERROR: el rollback no volvió a 1h — ONE_HOUR sigue en 24h. Revisar a mano.")
        return 0

    wf = api(f"/workflows/{WF_ID}")
    version = wf.get("versionId")
    print(f"Auto Reactivar Bot: {len(wf['nodes'])} nodos, activo={wf['active']}, versionId={version}")
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

    ts = time.strftime("%Y%m%d_%H%M%S")
    actual = api(f"/workflows/{WF_ID}")
    if actual.get("versionId") != version:
        sys.exit("ERROR: el workflow cambió entre el GET y el PUT. Volvé a correr el dry-run.")
    (HIST / f"auto_reactivar_PRE_{LABEL}_{ts}.json").write_text(
        json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PRE backup -> {HIST / f'auto_reactivar_PRE_{LABEL}_{ts}.json'}")

    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = clean_settings(wf)
    if len(body["nodes"]) != 4:
        sys.exit("ERROR: el body a PUTear no tiene 4 nodos — abortado antes de tocar n8n.")
    api(f"/workflows/{WF_ID}", method="PUT", payload=body)

    after = api(f"/workflows/{WF_ID}")
    (HIST / f"auto_reactivar_POST_{LABEL}_{ts}.json").write_text(
        json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    v = verify(after)
    print(f"POST backup -> {HIST / f'auto_reactivar_POST_{LABEL}_{ts}.json'}")
    print(f"verificación post-PUT: {v}")
    if not all(v.values()):
        sys.exit("ERROR: la verificación post-PUT falló. Revisar / rollback.")
    print(f"✅ aplicado: {len(after['nodes'])} nodos, activo={after['active']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
