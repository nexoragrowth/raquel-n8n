# -*- coding: utf-8 -*-
"""
apply_fix_wait_pierde_mensajes.py — FIX: se perdía el 3er mensaje (datos de cuenta).

CAUSA RAÍZ (verificada con datos, no con suposiciones):
  - El agente genera las 3 partes PERFECTO (verificado en n8n_chat_histories id 478:
    tiene los `---` y el bloque completo con CBU). O sea el prompt está bien.
  - La pérdida es en el ENVÍO. La cadena es:
        Split en Mensajes (3 items)
          -> Gate Error Tecnico (pasa los 3)
          -> Tiene respuesta?
          -> IF "Es primer mensaje?" (partIndex === 0)
               true  (parte 1)      -> Evolution - Typing -> enviar   ✅
               false (partes 2 y 3) -> "Delay Humano" (WAIT) -> Typing -> enviar
  - El nodo WAIT con MÚLTIPLES items no los propaga todos: entran 2 (partes 2 y 3) y
    sale 1. Por eso SIEMPRE llegan exactamente 2 mensajes y falta el último.

FIX (1 sola conexión):
  La salida FALSE de "Es primer mensaje?" pasa a ir DIRECTO a "Evolution - Typing",
  salteando el Wait. El ritmo humano se mantiene porque "Evolution - Typing" ya manda
  el presence "escribiendo…" con delay proporcional al largo del mensaje.
  El nodo "Delay Humano" queda en el canvas pero desconectado (revertible).

USO:
  python scripts/apply_fix_wait_pierde_mensajes.py            # preview
  python scripts/apply_fix_wait_pierde_mensajes.py --apply    # aplica (con env n8n)
"""
import argparse
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

WF_ID = os.environ.get("N8N_WF_BOT", "O155MqHgOSaNZ9ye")
BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""

IF_NODE = "Es primer mensaje?"
WAIT_NODE = "Delay Humano"
DESTINO = "Evolution - Typing"

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": KEY, "accept": "application/json", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--base")
    args = ap.parse_args()

    if args.apply:
        if not (BASE and KEY):
            print("!! Faltan N8N_API_BASE / N8N_API_KEY."); sys.exit(1)
        wf = api("GET", f"/workflows/{WF_ID}")
        json.dump(wf, open("workflows/history/v6_PRE_fix_wait_LIVE.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("backup PRE -> workflows/history/v6_PRE_fix_wait_LIVE.json")
    else:
        base = args.base or "workflows/history/v6_POST_a1_20260718_182612.json"
        print(f"[PREVIEW] sobre {base} (NO toca n8n)")
        wf = json.load(open(base, encoding="utf-8"))

    conns = wf["connections"]
    if IF_NODE not in conns:
        print(f"!! No encontré conexiones de '{IF_NODE}'."); sys.exit(1)

    main_out = conns[IF_NODE].get("main", [])
    if len(main_out) < 2:
        print(f"!! '{IF_NODE}' no tiene salida false."); sys.exit(1)

    falso = main_out[1]
    destinos = [l["node"] for l in falso]
    print(f"\nsalida FALSE de '{IF_NODE}' actualmente -> {destinos}")

    if destinos == [DESTINO]:
        print("• Ya estaba aplicado (va directo al Typing). Nada que hacer."); return
    if WAIT_NODE not in destinos:
        print(f"!! Esperaba encontrar '{WAIT_NODE}' ahí. Abortar para no romper nada."); sys.exit(1)

    # Reemplazar el Wait por el destino directo, preservando el resto de la lista.
    nuevo = [{"node": DESTINO, "type": "main", "index": 0} if l["node"] == WAIT_NODE else l for l in falso]
    conns[IF_NODE]["main"][1] = nuevo
    print(f"salida FALSE pasa a  -> {[l['node'] for l in nuevo]}   (saltea el WAIT)")

    if not args.apply:
        print("\n[PREVIEW] listo. Para aplicar: --apply")
        return

    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED_SETTINGS}
    api("PUT", f"/workflows/{WF_ID}", {
        "name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
        "settings": settings, "staticData": wf.get("staticData"),
    })
    live = api("GET", f"/workflows/{WF_ID}")
    dest_live = [l["node"] for l in live["connections"][IF_NODE]["main"][1]]
    ok = dest_live == [DESTINO]
    print("\nverificación post-PUT:", f"OK ✅ ahora va directo a {DESTINO}" if ok else f"!! quedó {dest_live}")


if __name__ == "__main__":
    main()
