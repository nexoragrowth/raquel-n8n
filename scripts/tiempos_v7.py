# -*- coding: utf-8 -*-
"""
tiempos_v7.py — SOLO LECTURA. Lee las últimas ejecuciones del cerebro v7 en n8n y muestra dónde se va el tiempo de cada respuesta
(nodo por nodo, y dentro del agente cuánto tardan el modelo y cada herramienta). Sirve para atacar la latencia con datos, no a ojo.

USO:  python scripts/tiempos_v7.py            # últimas 15 ejecuciones del cerebro
      python scripts/tiempos_v7.py --n 40
"""
import argparse, json, sys, urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probar_v7 import env, require  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent


def api(path):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=15); a = ap.parse_args()
    wid = json.loads((ROOT / "v7" / "ids.json").read_text(encoding="utf-8"))["cerebro"]
    lista = api(f"/executions?workflowId={wid}&limit={a.n}").get("data", [])
    por_nodo = defaultdict(list); totales = []
    for ex in lista:
        det = api(f"/executions/{ex['id']}?includeData=true")
        runs = ((det.get("data") or {}).get("resultData") or {}).get("runData") or {}
        filas = []
        for nodo, rs in runs.items():
            ms = sum(int(r.get("executionTime") or 0) for r in rs)
            filas.append((ms, nodo, len(rs)))
            por_nodo[nodo].append(ms)
        total = sum(m for m, nodo, _n in filas if not nodo.startswith("Modelo"))
        inicio, fin = det.get("startedAt"), det.get("stoppedAt")
        totales.append(total)
        print(f"\n== ejecución {ex['id']} · {inicio} → {fin}")
        for ms, nodo, n in sorted(filas, reverse=True)[:8]:
            print(f"   {ms / 1000:6.2f} s  {nodo}" + (f"  (×{n})" if n > 1 else ""))
    print("\n==== PROMEDIO POR NODO (s) en", len(lista), "ejecuciones")
    for nodo, v in sorted(por_nodo.items(), key=lambda kv: -sum(kv[1]) / len(kv[1]))[:15]:
        print(f"   {sum(v) / len(v) / 1000:6.2f} s  máx {max(v) / 1000:6.2f}  {nodo}  ({len(v)} veces)")


if __name__ == "__main__":
    main()
