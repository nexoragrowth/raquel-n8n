# -*- coding: utf-8 -*-
"""
apply_webhook_evolution.py — 2026-10-08 · vuelve a poner el webhook de la instancia `raquel` de Evolution GO hacia el v6.

POR QUÉ: desde el 06/10 ~10:00 (ART) no entra ningún mensaje a n8n. Evolution GO muestra la instancia conectada (se reconectó el 07/10 ~16:00 ART)
pero con `webhook: ""`. El lado n8n está sano (v6 activo, Webhook "evolution-v2", webhookId evo-webhook-v2). Causa probable: el manager de
Evolution GO manda webhookUrl:"" al reconectar con el campo en blanco y eso borra el webhook (ver PR #21 de evolution-go).

QUÉ HACE: POST /instance/connect con el webhook (endpoint oficial: https://docs.evolutionfoundation.com.br/evolution-go/webhooks), apikey global
(la toma del nodo "Check Evolution" del Health Check en n8n, sin imprimirla), header instanceId. Guarda el estado antes y después en
workflows/history/ (fuera de git). Por defecto SOLO MUESTRA el estado y lo que haría.

USO:  python scripts/apply_webhook_evolution.py           # muestra estado actual (solo lectura)
      python scripts/apply_webhook_evolution.py --apply   # pone el webhook y verifica
Después: mandar un WhatsApp de prueba al número de la clínica y correr `python scripts/apply_webhook_evolution.py --verificar-entrada`
(mira el último mensaje en mensajes_entrantes_live). Al terminar, limpiar el número de prueba (regla 9: scripts/limpiar_numero_demo.py).
"""
import argparse, datetime, json, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tiempos_v7 import api  # API de n8n (solo lectura acá)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
BASE = "https://evo.raquelrodriguez.com.ar"
INSTANCIA = "raquel"
WEBHOOK = "https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2"
EVENTOS = ["MESSAGE"]   # el mismo evento que tenía configurado la instancia
HEALTH_CHECK = "Yjl6kyLnALhIfbFX"


def clave():
    wf = api(f"/workflows/{HEALTH_CHECK}")
    n = next(n for n in wf["nodes"] if n["name"] == "Check Evolution")
    return next(h["value"] for h in n["parameters"]["headerParameters"]["parameters"] if h["name"] == "apikey")


def pedido(key, metodo, path, body=None, extra=None):
    h = {"apikey": key, "Content-Type": "application/json", **(extra or {})}
    r = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, method=metodo, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=60) as x:
            return x.status, json.loads(x.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


def estado(key, con_token=False):
    s, d = pedido(key, "GET", "/instance/all")
    if s != 200:
        raise SystemExit(f"GET /instance/all → {s}: {d}")
    i = next(x for x in d["data"] if x["name"] == INSTANCIA)
    e = {k: i.get(k) for k in ("id", "name", "webhook", "connected", "events", "jid", "disconnect_reason")}
    return (e, i.get("token")) if con_token else e   # el token de la instancia nunca se imprime ni se guarda


def guardar(nombre, datos):
    p = ROOT / "workflows" / "history" / f"evolution_{INSTANCIA}_{nombre}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return p.relative_to(ROOT)


def verificar_entrada():
    sys.path.insert(0, str(ROOT / "tests"))
    from retrospectiva_v7 import conectar
    cur = conectar().cursor()
    cur.execute("SELECT max(created_at) FROM mensajes_entrantes_live")
    print("último mensaje entrante registrado:", cur.fetchone()[0])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verificar-entrada", action="store_true")
    a = ap.parse_args()
    if a.verificar_entrada:
        return verificar_entrada()
    key = clave()
    antes, token = estado(key, con_token=True)
    print("ESTADO ACTUAL:", {**antes, "webhook": antes["webhook"] or "(VACÍO)"})
    if antes["webhook"] == WEBHOOK:
        return print("El webhook ya está bien puesto. Nada que hacer.")
    print(f"\nHaría: POST {BASE}/instance/connect  instanceId={antes['id']}  body={{webhookUrl: {WEBHOOK}, subscribe: {EVENTOS}}}")
    if not a.apply:
        return print("[SIMULACIÓN] agregar --apply")
    print("backup:", guardar("PRE", antes))
    # (08/10) Con la clave global devolvió 401 "not authorized": las operaciones sobre UNA instancia se autentican con el token de esa instancia.
    s, d = pedido(token, "POST", "/instance/connect", {"webhookUrl": WEBHOOK, "subscribe": EVENTOS}, {"instanceId": antes["id"]})
    print("POST /instance/connect (token de la instancia) →", s, (json.dumps(d, ensure_ascii=False) if not isinstance(d, str) else d)[:300])
    time.sleep(4)
    despues = estado(key)
    print("post:", guardar("POST", despues))
    print("ESTADO NUEVO:", {**despues, "webhook": despues["webhook"] or "(VACÍO)"})
    ok = despues["webhook"] == WEBHOOK and despues["connected"] is True
    print("\nTODO OK: webhook puesto y la instancia sigue conectada." if ok else "\nREVISAR: el webhook no quedó o la instancia no está conectada (no la desconectes; avisame).")
    print("Siguiente: mandá un WhatsApp de prueba al número de la clínica y corré:  python scripts/apply_webhook_evolution.py --verificar-entrada")


if __name__ == "__main__":
    main()
