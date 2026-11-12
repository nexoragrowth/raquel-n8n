# -*- coding: utf-8 -*-
"""
crear_cita_prueba_examen.py — 2026-10-06 · crea UNA cita real de prueba en Dentalink para la ficha "Test - Lucas" (id 608), que el examen del v7 necesita para
evaluar reprogramar / cancelar / confirmar (hoy esa ficha no tiene turno vigente).

POR QUE ASI: el agente v7 no puede escribir (su webhook de prueba fuerza el modo sombra por codigo, a proposito) y el .env local no tiene la clave de Dentalink
(vive cifrada en las credenciales de n8n). Este script arma un workflow TEMPORAL de n8n que usa esa credencial (la misma que usa el bot) para hacer UN POST,
lo llama una vez y lo borra. No toca el v6 ni los workflows v7.

USO:  python scripts/crear_cita_prueba_examen.py --fecha 2026-10-16 --hora 10:30            # simulacion: muestra el cuerpo del POST y no escribe nada
      python scripts/crear_cita_prueba_examen.py --fecha 2026-10-16 --hora 10:30 --apply    # crea la cita (workflow temporal: crear, activar, llamar, desactivar, borrar)
Despues:  python tests/seed_examen_v7.py --sembrar --cita <id> --fecha <fecha> --hora <hora>
Al terminar el examen: anular la cita en Dentalink (o con --anular <id> --apply, que hace PUT {"id_estado": 1}).
Dentalink rechaza un horario ocupado: si el POST falla, se imprime la respuesta y no queda nada creado.
"""
import argparse, json, secrets, sys, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require
from v7_lib import Grafo, DENTALINK

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
PACIENTE_TEST = 608            # "Test - Lucas"
SETTINGS_MIN = {"executionOrder": "v1"}


def base():
    return (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")


def api(path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base()}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode() or "{}")
import guarda_vivo  # noqa: E402  (12/11) freno: no pisar en n8n cambios que este repo no conoce (scripts/guarda_vivo.py)
api = guarda_vivo.envolver(api)


def llamar_webhook(ruta):
    req = urllib.request.Request(f"{base()}/webhook/{ruta}", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return {"error_http": e.code, "cuerpo": e.read().decode()[:800]}


def workflow_temporal(metodo, url, body, ruta):
    g = Grafo("TMP crear cita prueba examen v7 (se borra solo)")
    g._nodo("Webhook", "n8n-nodes-base.webhook", 2, {"httpMethod": "POST", "path": ruta, "responseMode": "lastNode", "options": {}}, 0, 0, {"webhookId": secrets.token_hex(8)})
    g.dentalink("Dentalink", metodo, f"'{url}'", "JSON.stringify(" + json.dumps(body, ensure_ascii=False) + ")", 240, 0)
    g.conectar("Webhook", "Dentalink")
    wf = g.json()
    wf["settings"] = dict(SETTINGS_MIN)
    return wf


def ejecutar_una_vez(metodo, url, body):
    ruta = "tmp-" + secrets.token_hex(12)
    wid = None
    try:
        wid = api("/workflows", "POST", workflow_temporal(metodo, url, body, ruta))["id"]
        api(f"/workflows/{wid}/activate", "POST")
        return llamar_webhook(ruta)
    finally:
        if wid:
            for paso, f in (("desactivar", lambda: api(f"/workflows/{wid}/deactivate", "POST")), ("borrar", lambda: api(f"/workflows/{wid}", "DELETE"))):
                try:
                    f()
                except Exception as e:
                    print(f"  AVISO: no pude {paso} el workflow temporal {wid}: {e}. Borralo a mano en n8n.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fecha"); ap.add_argument("--hora"); ap.add_argument("--anular", type=int); ap.add_argument("--apply", action="store_true")
    # (07/10) La nota vieja decía "(anular al terminar)" y la clínica la anuló (probablemente leyendo eso). Ahora pide explícitamente que no la toquen.
    ap.add_argument("--comentario", default="PRUEBA DEL BOT DE LUCAS - NO ANULAR NI MOVER (la anula Lucas cuando terminen las pruebas)")
    a = ap.parse_args()
    if a.anular:
        print(f"Anular la cita {a.anular}: PUT {DENTALINK}/citas/{a.anular}/ {{\"id_estado\": 1}}")
        if not a.apply:
            return print("[SIMULACION] agregar --apply")
        print(json.dumps(ejecutar_una_vez("PUT", f"{DENTALINK}/citas/{a.anular}/", {"id_estado": 1}), ensure_ascii=False, indent=1)[:1500])
        return
    if not (a.fecha and a.hora):
        sys.exit("Falta --fecha YYYY-MM-DD y --hora HH:MM")
    body = {"id_dentista": 1, "id_sucursal": 1, "id_sillon": 1, "id_paciente": PACIENTE_TEST, "fecha": a.fecha, "hora_inicio": a.hora, "duracion": 40,
            "comentario": a.comentario}
    print("POST", f"{DENTALINK}/citas/", "\n" + json.dumps(body, ensure_ascii=False, indent=1))
    if not a.apply:
        return print("\n[SIMULACION] No se creo nada. Agregar --apply.")
    r = ejecutar_una_vez("POST", f"{DENTALINK}/citas/", body)
    item = r[0] if isinstance(r, list) and r else r
    print("\nRespuesta de Dentalink:\n" + json.dumps(item, ensure_ascii=False, indent=1)[:1800])
    data = (item or {}).get("data") if isinstance(item, dict) else None
    if isinstance(data, dict) and data.get("id"):
        out = {"id_cita": data["id"], "fecha": a.fecha, "hora": a.hora, "id_paciente": PACIENTE_TEST}
        (ROOT / "data").mkdir(exist_ok=True)
        (ROOT / "data" / "cita_prueba_examen.json").write_text(json.dumps(out), encoding="utf-8")
        print(f"\nCITA CREADA: id {data['id']} el {a.fecha} a las {a.hora}.\nSiguiente: python tests/seed_examen_v7.py --sembrar --cita {data['id']} --fecha {a.fecha} --hora {a.hora}")
    else:
        print("\nNO se creo la cita (ver la respuesta de arriba). Probá otro horario libre.")


if __name__ == "__main__":
    main()
