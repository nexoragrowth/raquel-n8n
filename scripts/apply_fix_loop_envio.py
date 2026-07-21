# -*- coding: utf-8 -*-
"""
apply_fix_loop_envio.py — FIX DEFINITIVO: enviar TODOS los mensajes, uno por uno.

EVIDENCIA (ejecución 236863, leída de n8n):
    Tiene respuesta? ......... 3 items  ✅ (las 3 partes, con CBU)
    Evolution - Typing ....... 1 item   ❌  <-- entran 3, sale 1
    Enviar Mensaje ........... 1 item   ❌

CAUSA RAÍZ: el nodo de Evolution API procesa SOLO UN item por corrida (ignora el resto
de la entrada). Por eso el diseño original bifurcaba con IF+Wait: generaba 2 corridas
separadas → 2 mensajes. Nunca podía mandar 3, sin importar el prompt.

FIX: meter un "Loop Mensajes" (Split In Batches, de a 1) que fuerza UNA CORRIDA POR
MENSAJE:
    Tiene respuesta? -> Loop Mensajes
                        Loop Mensajes (salida "loop") -> Evolution - Typing
                                                       -> Gate Humano Final
                                                       -> Enviar Mensaje
                        Enviar Mensaje -> (vuelve a) Loop Mensajes
Cada vuelta manda 1 mensaje y sigue con el siguiente, EN ORDEN. Con 3 partes → 3 mensajes.
Los nodos "Es primer mensaje?" y "Delay Humano" quedan desconectados (revertible).

USO:
  python scripts/apply_fix_loop_envio.py            # preview
  python scripts/apply_fix_loop_envio.py --apply    # aplica
"""
import argparse
import json
import os
import sys
import urllib.request
import uuid

sys.stdout.reconfigure(encoding="utf-8")

WF_ID = os.environ.get("N8N_WF_BOT", "O155MqHgOSaNZ9ye")
BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""

LOOP = "Loop Mensajes"
ORIGEN = "Tiene respuesta?"
TYPING = "Evolution - Typing"
ENVIAR = "Evolution API - Enviar Mensaje"

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
    with urllib.request.urlopen(req, timeout=45) as r:
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
        json.dump(wf, open("workflows/history/v6_PRE_loop_envio_LIVE.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("backup PRE -> workflows/history/v6_PRE_loop_envio_LIVE.json")
    else:
        base = args.base or "workflows/history/v6_POST_a1_20260718_182612.json"
        print(f"[PREVIEW] sobre {base} (NO toca n8n)")
        wf = json.load(open(base, encoding="utf-8"))

    nombres = {n["name"] for n in wf["nodes"]}
    if LOOP in nombres:
        print(f"• '{LOOP}' ya existe. Nada que hacer."); return
    for req in (ORIGEN, TYPING, ENVIAR):
        if req not in nombres:
            print(f"!! Falta el nodo '{req}'. Abortar."); sys.exit(1)

    # Nodo nuevo: Split In Batches de a 1 (una corrida por mensaje).
    wf["nodes"].append({
        "id": str(uuid.uuid4()),
        "name": LOOP,
        "type": "n8n-nodes-base.splitInBatches",
        "typeVersion": 3,
        "position": [15220, 384],
        "parameters": {"batchSize": 1, "options": {}},
    })
    print(f"✓ nodo '{LOOP}' agregado (Split In Batches, de a 1)")

    conns = wf["connections"]
    # 1) Tiene respuesta? (true) -> Loop
    salida_true = conns[ORIGEN]["main"][0]
    conns[ORIGEN]["main"][0] = [{"node": LOOP, "type": "main", "index": 0}] + [
        l for l in salida_true if l["node"] not in (TYPING, "Es primer mensaje?")
    ]
    print(f"✓ '{ORIGEN}' (true) -> {[l['node'] for l in conns[ORIGEN]['main'][0]]}")

    # 2) Loop: salida 0 = "done" (nada) | salida 1 = "loop" -> Typing
    conns[LOOP] = {"main": [[], [{"node": TYPING, "type": "main", "index": 0}]]}
    print(f"✓ '{LOOP}' out[0]=done(vacío)  out[1]=loop -> {TYPING}")

    # 3) Enviar Mensaje -> vuelve al Loop (siguiente mensaje)
    conns[ENVIAR] = {"main": [[{"node": LOOP, "type": "main", "index": 0}]]}
    print(f"✓ '{ENVIAR}' -> {LOOP}  (cierra el ciclo)")

    if not args.apply:
        print("\n[PREVIEW] listo. Para aplicar: --apply")
        return

    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED_SETTINGS}
    api("PUT", f"/workflows/{WF_ID}", {
        "name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
        "settings": settings, "staticData": wf.get("staticData"),
    })
    live = api("GET", f"/workflows/{WF_ID}")
    lc = live["connections"]
    ok = (
        any(n["name"] == LOOP for n in live["nodes"])
        and [l["node"] for l in lc[ORIGEN]["main"][0]][0] == LOOP
        and [l["node"] for l in lc[LOOP]["main"][1]] == [TYPING]
        and [l["node"] for l in lc[ENVIAR]["main"][0]] == [LOOP]
    )
    print("\nverificación post-PUT:", "OK ✅ loop de envío armado" if ok else "!! revisar, quedó incompleto")


if __name__ == "__main__":
    main()
