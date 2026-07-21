# -*- coding: utf-8 -*-
"""
apply_fix_envio_lineal.py — FIX del 3er mensaje que no llegaba, con EVIDENCIA de la
ejecución real (id 236847), no hipótesis.

QUÉ MOSTRÓ LA EJECUCIÓN (items por nodo):
    Banlist Validator ......... 1  ★tiene CBU
    Formatting Agent .......... 1  ★tiene CBU   (NO lo recortaba)
    Split en Mensajes ......... 3  ✅ las 3 partes
    Gate Error Tecnico ........ 3  ✅
    Tiene respuesta? .......... 3  ✅
    Es primer mensaje? ........ 1 + 2  ✅ (bifurca)
    Delay Humano .............. 2  ✅
    Evolution - Typing ........ 1 + 1 = 2  ❌  <-- se pierde uno acá
    Enviar Mensaje ............ 2  ❌

O sea: la cadena LINEAL propaga 3 items sin problema; lo que rompe es la BIFURCACIÓN
(IF "Es primer mensaje?" + nodo Wait): la rama que lleva 2 items termina enviando 1.

FIX (1 conexión): "Tiene respuesta?" (salida true) va DIRECTO a "Evolution - Typing",
salteando el IF y el Wait. Los 3 items viajan por una sola cadena lineal:
    Split -> Gate Error -> Tiene respuesta? -> Typing -> Gate Humano Final -> Enviar
El orden se mantiene (n8n procesa los items en orden en una cadena lineal) y el ritmo
"humano" lo sigue dando el presence de "Evolution - Typing" (su delay es proporcional
al largo del mensaje). Los nodos "Es primer mensaje?" y "Delay Humano" quedan en el
canvas pero desconectados → revertible.

USO:
  python scripts/apply_fix_envio_lineal.py            # preview
  python scripts/apply_fix_envio_lineal.py --apply    # aplica
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

ORIGEN = "Tiene respuesta?"
VIEJO_DEST = "Es primer mensaje?"
NUEVO_DEST = "Evolution - Typing"

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
        json.dump(wf, open("workflows/history/v6_PRE_envio_lineal_LIVE.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("backup PRE -> workflows/history/v6_PRE_envio_lineal_LIVE.json")
    else:
        base = args.base or "workflows/history/v6_POST_a1_20260718_182612.json"
        print(f"[PREVIEW] sobre {base} (NO toca n8n)")
        wf = json.load(open(base, encoding="utf-8"))

    conns = wf["connections"]
    if ORIGEN not in conns:
        print(f"!! No encontré '{ORIGEN}'."); sys.exit(1)

    salida_true = conns[ORIGEN]["main"][0]
    destinos = [l["node"] for l in salida_true]
    print(f"\nsalida TRUE de '{ORIGEN}' actualmente -> {destinos}")

    if NUEVO_DEST in destinos:
        print("• Ya estaba aplicado. Nada que hacer."); return
    if VIEJO_DEST not in destinos:
        print(f"!! Esperaba '{VIEJO_DEST}' ahí. Abortar para no romper nada."); sys.exit(1)

    conns[ORIGEN]["main"][0] = [
        {"node": NUEVO_DEST, "type": "main", "index": 0} if l["node"] == VIEJO_DEST else l
        for l in salida_true
    ]
    print(f"salida TRUE pasa a  -> {[l['node'] for l in conns[ORIGEN]['main'][0]]}")
    print("   (los 3 items viajan por una sola cadena lineal, sin IF ni Wait)")

    if not args.apply:
        print("\n[PREVIEW] listo. Para aplicar: --apply")
        return

    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED_SETTINGS}
    api("PUT", f"/workflows/{WF_ID}", {
        "name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
        "settings": settings, "staticData": wf.get("staticData"),
    })
    live = api("GET", f"/workflows/{WF_ID}")
    dest = [l["node"] for l in live["connections"][ORIGEN]["main"][0]]
    print("\nverificación post-PUT:", f"OK ✅ -> {dest}" if NUEVO_DEST in dest else f"!! quedó {dest}")


if __name__ == "__main__":
    main()
