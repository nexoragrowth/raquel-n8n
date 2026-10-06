# -*- coding: utf-8 -*-
"""
medir_latencia_v6.py — 2026-10-06 · linea base del v6 para el diseño v7 (puerta 0). SOLO LECTURA (GET /executions).

Por cada ejecucion reciente del v6 que llego a `Parse Intent`: intent, tramos (entrada hasta Parse Intent / modelo+herramientas / salida),
cuantas llamadas a modelos hubo (nodos lmChatOpenAi / openAi ejecutados) y total. Imprime p50/p95 por intent y por tramo.

USO:  python scripts/medir_latencia_v6.py [--n 150]
"""
import argparse, json, statistics, sys, urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
WID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
MODELO = ("Router LM", "Router LM1", "OpenAI Chat Model1", "LM Sub-Agent Confirmar", "LM Sub-Agent Cancelar", "LM Sub-Agent Agendar",
          "LM Sub-Agent General", "LM Sub-Agent Urgencia", "Banlist Shadow - LLM", "Triaje: Evaluar")
SUBWF = ("Execute Sub-WF Cancelar",)
ENVIO = ("Evolution API - Enviar Mensaje", "Split en Mensajes")


def api(path):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", headers={"X-N8N-API-KEY": require("N8N_API_KEY")})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round(p / 100 * (len(xs) - 1))))
    return xs[k]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    n = ap.parse_args().n
    ids, cur = [], None
    while len(ids) < n:
        r = api(f"/executions?workflowId={WID}&limit=100" + (f"&cursor={cur}" if cur else ""))
        ids += [e["id"] for e in r["data"]]
        cur = r.get("nextCursor")
        if not cur:
            break
    filas = []
    for eid in ids[:n]:
        d = api(f"/executions/{eid}?includeData=true")
        runs = (d.get("data") or {}).get("resultData", {}).get("runData", {})
        if "Parse Intent" not in runs or "Split en Mensajes" not in runs:
            continue
        t0 = runs["Webhook - Evolution API"][0]["startTime"] if "Webhook - Evolution API" in runs else None
        if not t0:
            continue
        def fin(nm):
            rr = runs.get(nm)
            return (rr[-1]["startTime"] + rr[-1]["executionTime"]) if rr else None
        t_parse = fin("Parse Intent"); t_split = fin("Split en Mensajes"); t_env = fin("Evolution API - Enviar Mensaje") or t_split
        intent = runs["Parse Intent"][0]["data"]["main"][0][0]["json"].get("intent")
        llamadas = sum(len(runs[m]) for m in MODELO if m in runs)
        buffer_ms = sum(r_["executionTime"] for r_ in runs.get("Buffer: Wait 10s", []))
        filas.append({"id": eid, "intent": intent, "entrada": t_parse - t0 - buffer_ms, "buffer": buffer_ms, "agente": (t_split - t_parse),
                      "salida": (t_env - t_split), "total_sin_buffer": (t_env - t0 - buffer_ms), "llamadas_modelo": llamadas,
                      "subwf": any(s in runs for s in SUBWF)})
    print(f"ejecuciones con respuesta: {len(filas)} de {len(ids[:n])} revisadas\n")
    por = defaultdict(list)
    for f in filas:
        por[f["intent"]].append(f)
    print(f"{'intent':28} {'n':>3} {'p50 total':>10} {'p95 total':>10} {'p50 entr':>9} {'p50 agente':>11} {'p95 agente':>11} {'p50 salida':>11} {'llam.modelo p50/max':>20}")
    for intent, fs in sorted(por.items(), key=lambda kv: -len(kv[1])):
        tot = [x["total_sin_buffer"] / 1000 for x in fs]; ag = [x["agente"] / 1000 for x in fs]; en = [x["entrada"] / 1000 for x in fs]; sa = [x["salida"] / 1000 for x in fs]
        ll = [x["llamadas_modelo"] for x in fs]
        print(f"{str(intent):28} {len(fs):>3} {pct(tot,50):>9.1f}s {pct(tot,95):>9.1f}s {pct(en,50):>8.1f}s {pct(ag,50):>10.1f}s {pct(ag,95):>10.1f}s {pct(sa,50):>10.1f}s {statistics.median(ll):>9.0f} / {max(ll):<6}")
    tot = [x["total_sin_buffer"] / 1000 for x in filas]
    print(f"\nTOTAL (sin buffer) p50 {pct(tot,50):.1f}s · p95 {pct(tot,95):.1f}s · buffer p50 {pct([x['buffer']/1000 for x in filas],50):.1f}s · llamadas a modelo por mensaje: mediana {statistics.median([x['llamadas_modelo'] for x in filas]):.0f}, max {max(x['llamadas_modelo'] for x in filas)}")


if __name__ == "__main__":
    main()
