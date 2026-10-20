# -*- coding: utf-8 -*-
"""
v7_global.py — 2026-10-19 · prende / apaga / consulta la llave GLOBAL `v7:global` que hace que TODOS los pacientes los atienda el cerebro v7
(requiere scripts/apply_v7_para_todos.py aplicado en el v6). Con la llave apagada, cada número vuelve a lo que diga su marca (flag_v7.py).

Mismo mecanismo que flag_v7.py: workflow TEMPORAL de n8n con la credencial de Redis del bot, clave y valor FIJOS adentro, se llama una vez y se
borra. La llave global NO vence sola (es un cambio de producción, no una prueba): se apaga con --off.

Para dejar a UN número en el v6 con la global prendida:  --excluir <tel>  (pone v7:tel:<tel> = 'off', 30 días)  ·  --incluir <tel> lo saca.

USO:  python scripts/v7_global.py --estado
      python scripts/v7_global.py --on
      python scripts/v7_global.py --off
      python scripts/v7_global.py --excluir 5493880000000
"""
import argparse, json, re, secrets, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flag_v7 import api, llamar, CLINICA
from v7_lib import Grafo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
V6 = "O155MqHgOSaNZ9ye"
CLAVE = "v7:global"


def workflow(accion, clave, valor, ttl, ruta):
    g = Grafo("TMP v7 global (se borra solo)")
    g._nodo("Webhook", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": ruta, "responseMode": "lastNode", "options": {}}, 0, 0, {"webhookId": secrets.token_hex(8)})
    ultimo = "Webhook"
    if accion == "set":
        p = {"operation": "set", "key": "={{ " + json.dumps(clave) + " }}", "value": "={{ " + json.dumps(valor) + " }}", "keyType": "string",
             "expire": bool(ttl)}
        if ttl:
            p["ttl"] = ttl
        n = g.redis_set("Redis SET", json.dumps(clave), json.dumps(valor), ttl or 60, 220, 0)
        next(x for x in g.nodos if x["name"] == n)["parameters"] = p
        g.conectar(ultimo, "Redis SET"); ultimo = "Redis SET"
    elif accion == "del":
        g.redis_del("Redis DEL", json.dumps(clave), 220, 0); g.conectar(ultimo, "Redis DEL"); ultimo = "Redis DEL"
    g.redis_get("Redis GET", json.dumps(clave), "valor", 440, 0); g.conectar(ultimo, "Redis GET")
    g.code("Resultado", f"return [{{ json: {{ clave: {json.dumps(clave)}, valor: $input.first().json.valor ?? null }} }}];", 660, 0)
    g.conectar("Redis GET", "Resultado")
    wf = g.json()
    wf["settings"] = {"executionOrder": "v1"}
    return wf


def correr(accion, clave, valor=None, ttl=0):
    ruta = "tmp-v7g-" + secrets.token_hex(12)
    wid = None
    try:
        wid = api("/workflows", "POST", workflow(accion, clave, valor, ttl, ruta))["id"]
        api(f"/workflows/{wid}/activate", "POST")
        r = llamar(ruta)
    finally:
        if wid:
            for paso, f in (("desactivar", lambda: api(f"/workflows/{wid}/deactivate", "POST")), ("borrar", lambda: api(f"/workflows/{wid}", "DELETE"))):
                try:
                    f()
                except BaseException as e:
                    print(f"  AVISO: no pude {paso} el workflow temporal {wid}: {e}. Borralo a mano en n8n.")
    if not isinstance(r, dict) or "valor" not in r:
        raise SystemExit(f"Respuesta inesperada: {json.dumps(r, ensure_ascii=False)[:500]}")
    return r["valor"]


def tel_ok(t):
    t = re.sub(r"\D", "", t)
    if not re.fullmatch(r"549\d{10}", t) or t == CLINICA:
        raise SystemExit(f"Número inválido: {t}")
    return t


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--on", action="store_true"); g.add_argument("--off", action="store_true"); g.add_argument("--estado", action="store_true")
    g.add_argument("--excluir"); g.add_argument("--incluir")
    a = ap.parse_args()
    if a.excluir or a.incluir:
        t = tel_ok(a.excluir or a.incluir)
        v = correr("set", f"v7:tel:{t}", "off", 30 * 86400) if a.excluir else correr("del", f"v7:tel:{t}")
        print(f"{t}: v7:tel = {v!r} → " + ("queda en el v6 aunque la global esté prendida (30 días)." if v == "off" else "sigue la regla general."))
        return
    if a.on:
        w = api(f"/workflows/{V6}")
        if not any(n["name"] == "V7: Redis GET global" for n in w["nodes"]):
            raise SystemExit("El v6 no lee la llave global todavía: primero python scripts/apply_v7_para_todos.py --apply")
        if w.get("active") is not True:
            raise SystemExit("El v6 no está activo: no prendo nada.")
    v = correr("set", CLAVE, "vivo") if a.on else correr("del", CLAVE) if a.off else correr("get", CLAVE)
    if a.on:
        print("OK: v7 para TODOS los pacientes desde el próximo mensaje." if v == "vivo" else f"FALLÓ: la llave quedó en {v!r}")
    elif a.off:
        print("OK: llave global apagada; cada número vuelve a su marca (sin marca = v6)." if v in (None, "") else f"FALLÓ: sigue en {v!r}")
    else:
        print(f"v7:global = {v!r} → " + ("v7 para TODOS" if v == "vivo" else "solo los números marcados con flag_v7.py"))


if __name__ == "__main__":
    main()
