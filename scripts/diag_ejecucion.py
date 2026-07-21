# -*- coding: utf-8 -*-
"""
diag_ejecucion.py — LEE LA ÚLTIMA EJECUCIÓN REAL del v6 y muestra, nodo por nodo,
cuántos items salieron y qué contenían. Solo LECTURA (GET), no toca nada.

Sirve para ver EXACTAMENTE dónde se pierde el 3er mensaje (el bloque de datos de cuenta):
si el Formatting lo recorta, si el Split arma 2 o 3, o si el Wait/envío se come uno.

USO:
  cd c:\\Users\\not\\Desktop\\proyectos\\raquel-n8n
  gc ..\\nexora-whatsapp-agent\\.env.local | ? { $_ -match '^N8N_API_(BASE|KEY)=' } | % { $p = $_ -split '=',2; Set-Item "env:$($p[0])" $p[1].Trim('"') }
  python scripts\\diag_ejecucion.py
"""
import json
import os
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

WF_ID = os.environ.get("N8N_WF_BOT", "O155MqHgOSaNZ9ye")
BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""

# Nodos del camino de respuesta, en orden.
INTERES = [
    "Banlist Validator",
    "Necesita Formatting?",
    "Formatting Agent - WhatsApp",
    "Split en Mensajes",
    "Gate Error Tecnico",
    "Tiene respuesta?",
    "Es primer mensaje?",
    "Delay Humano",
    "Evolution - Typing",
    "Gate Humano Final",
    "Evolution API - Enviar Mensaje",
]


def api(path):
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}",
        headers={"X-N8N-API-KEY": KEY, "accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def corto(v, n=110):
    s = str(v).replace("\n", "\\n")
    return s[:n] + ("…" if len(s) > n else "")


def main():
    if not (BASE and KEY):
        print("!! Faltan N8N_API_BASE / N8N_API_KEY en el entorno."); sys.exit(1)

    # Muchas ejecuciones son ACKs de WhatsApp (no responden nada). Buscamos la más
    # reciente que REALMENTE haya corrido el camino de respuesta (tiene el Split).
    q = urllib.parse.urlencode({"workflowId": WF_ID, "limit": 30})
    lista = api(f"/executions?{q}").get("data", [])
    if not lista:
        print("!! No hay ejecuciones."); sys.exit(1)

    run = None
    ex_id = None
    for e in lista:
        try:
            full = api(f"/executions/{e.get('id')}?includeData=true")
        except Exception:
            continue
        r = (((full.get("data") or {}).get("resultData") or {}).get("runData")) or {}
        if "Split en Mensajes" in r:
            run, ex_id = r, e.get("id")
            print(f"=== Ejecución con RESPUESTA: id={ex_id}  {e.get('startedAt','')[:19]} ===\n")
            break
    if run is None:
        print("!! Ninguna de las últimas 30 ejecuciones corrió el camino de respuesta.")
        print("   Mandale un mensaje al bot (ej: 'precio') y volvé a correr esto.")
        sys.exit(1)

    for nodo in INTERES:
        if nodo not in run:
            print(f"— {nodo}: (no se ejecutó)")
            continue
        for corrida in run[nodo]:
            salidas = ((corrida.get("data") or {}).get("main")) or []
            total = sum(len(s or []) for s in salidas)
            detalle = " | ".join(f"salida[{i}]={len(s or [])}" for i, s in enumerate(salidas))
            print(f"➤ {nodo}: {total} item(s)   [{detalle}]")
            # mostrar contenido util
            for i, s in enumerate(salidas):
                for j, item in enumerate(s or []):
                    j2 = (item or {}).get("json") or {}
                    txt = j2.get("message") or j2.get("output") or ""
                    if txt:
                        marca = " ★TIENE-CBU" if "CBU" in str(txt) else ""
                        print(f"     [{i}][{j}] {corto(txt)}{marca}")
        print()

    print("LECTURA: buscá dónde el número de items BAJA (ahí se pierde el mensaje),")
    print("y si el texto con ★TIENE-CBU deja de aparecer en algún paso.")


if __name__ == "__main__":
    main()
