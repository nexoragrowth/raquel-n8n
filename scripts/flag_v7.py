# -*- coding: utf-8 -*-
"""
flag_v7.py — 2026-10-14 · prende / apaga / consulta la marca que hace que un número sea atendido por el CEREBRO v7 (orquestador) en vez del v6.

CÓMO FUNCIONA: el v6 (O155MqHgOSaNZ9ye) lee la clave Redis `v7:tel:<número de quien escribe>` en el nodo "V7: Redis GET modo"; si vale 'vivo',
el mensaje lo atiende el v7 (ver scripts/apply_v7_flag_lucas.py). La marca va en el número del PACIENTE que escribe, nunca en el de la clínica.

POR QUÉ ASÍ: el Redis del bot no es accesible desde afuera del VPS. Igual que crear_cita_prueba_examen.py, este script arma un workflow TEMPORAL
de n8n con la credencial de Redis del bot, lo llama una vez y lo borra. La clave y el valor van FIJOS dentro del workflow temporal (no los recibe
del pedido): ese webhook no puede escribir otra cosa.

USO:  python scripts/flag_v7.py --estado 5491161461034            # solo lee la marca
      python scripts/flag_v7.py --on 5491161461034                # prende el v7 para ese número (se apaga sola en 24 h)
      python scripts/flag_v7.py --on 5491161461034 --horas 4      # con otra duración
      python scripts/flag_v7.py --off 5491161461034               # apaga (vuelve al v6 desde el próximo mensaje)
"""
import argparse, json, re, secrets, sys, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require
from v7_lib import Grafo

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CLINICA = "5493885786946"   # el número de la clínica nunca lleva la marca (no es remitente de mensajes de pacientes)


def base():
    return (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")


def api(path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base()}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"n8n respondió {e.code} a {method} {path}: {e.read().decode()[:600]}")


def llamar(ruta):
    req = urllib.request.Request(f"{base()}/webhook/{ruta}", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return {"error_http": e.code, "cuerpo": e.read().decode()[:500]}


def workflow(accion, tel, ttl, ruta):
    clave = f"v7:tel:{tel}"
    g = Grafo("TMP flag v7 (se borra solo)")
    g._nodo("Webhook", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": ruta, "responseMode": "lastNode", "options": {}}, 0, 0, {"webhookId": secrets.token_hex(8)})
    ultimo = "Webhook"
    if accion == "on":
        g.redis_set("Redis SET", json.dumps(clave), json.dumps("vivo"), ttl, 220, 0); g.conectar(ultimo, "Redis SET"); ultimo = "Redis SET"
    elif accion == "off":
        g.redis_del("Redis DEL", json.dumps(clave), 220, 0); g.conectar(ultimo, "Redis DEL"); ultimo = "Redis DEL"
    g.redis_get("Redis GET", json.dumps(clave), "valor", 440, 0); g.conectar(ultimo, "Redis GET")
    g.code("Resultado", f"return [{{ json: {{ clave: {json.dumps(clave)}, valor: $input.first().json.valor ?? null }} }}];", 660, 0)
    g.conectar("Redis GET", "Resultado")
    wf = g.json()
    wf["settings"] = {"executionOrder": "v1"}
    return wf


def correr(accion, tel, ttl):
    ruta = "tmp-flag-" + secrets.token_hex(12)
    wid = None
    try:
        wid = api("/workflows", "POST", workflow(accion, tel, ttl, ruta))["id"]
        api(f"/workflows/{wid}/activate", "POST")
        return llamar(ruta)
    finally:
        if wid:
            for paso, f in (("desactivar", lambda: api(f"/workflows/{wid}/deactivate", "POST")), ("borrar", lambda: api(f"/workflows/{wid}", "DELETE"))):
                try:
                    f()
                except BaseException as e:
                    print(f"  AVISO: no pude {paso} el workflow temporal {wid}: {e}. Borralo a mano en n8n.")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--on"); g.add_argument("--off"); g.add_argument("--estado")
    ap.add_argument("--horas", type=float, default=24)
    a = ap.parse_args()
    accion = "on" if a.on else "off" if a.off else "estado"
    tel = re.sub(r"\D", "", a.on or a.off or a.estado)
    if not re.fullmatch(r"549\d{10}", tel):
        raise SystemExit(f"Número inválido: {tel} (formato 549 + 10 dígitos, ej. 5491161461034)")
    if tel == CLINICA:
        raise SystemExit("Ese es el número de la clínica: la marca va en el número de QUIEN ESCRIBE (un paciente o vos), no en el de la clínica.")
    ttl = max(60, int(a.horas * 3600))
    r = correr(accion, tel, ttl)
    if not isinstance(r, dict) or "valor" not in r:
        raise SystemExit(f"Respuesta inesperada: {json.dumps(r, ensure_ascii=False)[:500]}")
    v = r["valor"]
    if accion == "on":
        print(("OK: el v7 atiende a " + tel + f" (se apaga sola en {a.horas:g} h). Escribile al número de la clínica desde ese celular.") if v == "vivo" else f"FALLÓ: la clave quedó en {v!r}")
    elif accion == "off":
        print(("OK: marca apagada; " + tel + " vuelve al v6 desde el próximo mensaje.") if v in (None, "") else f"FALLÓ: la clave sigue en {v!r}")
    else:
        print(f"{tel}: {'ATENDIDO POR EL v7' if v == 'vivo' else 'atendido por el v6 (sin marca)'}  (clave v7:tel:{tel} = {v!r})")


if __name__ == "__main__":
    main()
