# -*- coding: utf-8 -*-
"""
apply_v6_descartar_atrasados.py — 2026-11-11 · el v6 deja de procesar mensajes que llegan con más de 15 min de atraso.

Incidente 11/11: Evolution GO quedó trabado en el offline sync (stream:error <ack class="status" .../> cada ~50 min, la cola
offline nunca se vacía: 283 mensajes pendientes). Cada tanto se colaban mensajes de días atrás y el bot los contestaba como nuevos:
el comprobante de un paciente del 09/11 11:40 se contestó el 11/11 a la 1:25 ("Recibido. Dejé anotado su aviso de pago…") y
"Me lo cambiaron para el 20 de noviembre" (09/11 09:02) se contestó a las 0:34 con "¿Cuál de estos turnos?". Al destrabar la cola
iban a entrar ~283 mensajes viejos de golpe.

QUÉ CAMBIA: un paso 4 en el nodo "Webhook Validator" (el primero después del webhook): si body.data.Info.Timestamp tiene más de
15 minutos, return [] → no corre nada (ni respuesta, ni modo humano por fromMe, ni comandos /bot, ni Inbox Live). Esos mensajes ya
los recibió el celular de la clínica en su momento. Sin Timestamp o ilegible → sigue como hoy (falla abierta). La ejecución queda
registrada en n8n (Webhook Validator sin salida) y en el log del nodo ("[ATRASADO]").

USO:  python scripts/apply_v6_descartar_atrasados.py            # muestra el diff del nodo (no escribe)
      python scripts/apply_v6_descartar_atrasados.py --apply    # backup PRE → PUT → GET → backup POST → verificación
"""
import argparse, difflib, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crear_v7_en_n8n import api, SETTINGS_OK, ROOT

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
V6 = "O155MqHgOSaNZ9ye"
NODO = "Webhook Validator"
HIST = ROOT / "workflows" / "history"
ANCLA = "// OK\nreturn [{ json: inp }];"
MARCA = "// 4) (11/11) Mensaje ATRASADO"
PASO4 = """// 4) (11/11) Mensaje ATRASADO: Evolution GO, al destrabarse/reconectar, puede entregar de golpe mensajes de días atrás
//    (incidente 11/11: el comprobante de un paciente del 09/11 se contestó el 11/11 a la 1:25). Con más de 15 min de atraso NO se
//    procesa (ni respuesta, ni modo humano, ni comandos /bot, ni Inbox Live): el celular de la clínica ya lo recibió en su momento.
//    Sin Timestamp o ilegible → sigue como siempre (falla abierta). scripts/apply_v6_descartar_atrasados.py
const MAX_ATRASO_MS = 15 * 60 * 1000;
const tsMsg = Date.parse(String(info.Timestamp || ''));
if (!isNaN(tsMsg) && Date.now() - tsMsg > MAX_ATRASO_MS) {
  console.log('[ATRASADO] descartado ' + info.ID + ' escrito ' + info.Timestamp + ' (' + Math.round((Date.now() - tsMsg) / 60000) + ' min de atraso)');
  return [];
}

"""


def nuevo_codigo(code):
    if MARCA in code:
        return None
    if code.count(ANCLA) != 1:
        raise SystemExit(f"No encuentro una sola vez el final esperado del {NODO} (¿cambió el nodo?). No toco nada.")
    return code.replace(ANCLA, PASO4 + ANCLA)


def probar(code):
    r = subprocess.run(["node", str(ROOT / "tests" / "test_v6_descartar_atrasados.mjs")], input=code, capture_output=True, text=True, encoding="utf-8")
    print(r.stdout.strip())
    if r.returncode != 0:
        raise SystemExit("Tests del nodo nuevo fallan: no hago PUT.\n" + r.stderr[-800:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    w = api(f"/workflows/{V6}")
    nodo = next(n for n in w["nodes"] if n["name"] == NODO)
    viejo = nodo["parameters"]["jsCode"]
    nuevo = nuevo_codigo(viejo)
    if nuevo is None:
        print("El v6 ya tiene el paso 4 (mensajes atrasados). Nada que hacer.")
        return
    print("".join(difflib.unified_diff(viejo.splitlines(True), nuevo.splitlines(True), f"{NODO} (vivo)", f"{NODO} (nuevo)")))
    probar(nuevo)
    if not a.apply:
        print("[SIMULACIÓN] No se escribió nada. Correr con --apply (con OK de Lucas).")
        return
    if not any(x.get("webhookId") == "evo-webhook-v2" for x in w["nodes"]):
        raise SystemExit("Falta webhookId evo-webhook-v2: no hago PUT.")
    w2 = api(f"/workflows/{V6}")
    if w2.get("versionId") != w.get("versionId"):
        raise SystemExit("El v6 cambió mientras tanto: no hago PUT.")
    ts = time.strftime("%Y%m%d_%H%M%S")
    HIST.mkdir(parents=True, exist_ok=True)
    pre = HIST / f"{V6}_PRE_descartar_atrasados_{ts}.json"
    pre.write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
    print("backup PRE:", pre)
    nodo["parameters"]["jsCode"] = nuevo
    api(f"/workflows/{V6}", "PUT", {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
                                     "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in SETTINGS_OK},
                                     "staticData": w.get("staticData")})
    post = api(f"/workflows/{V6}")
    (HIST / f"{V6}_POST_descartar_atrasados_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    np = next(n for n in post["nodes"] if n["name"] == NODO)
    otros_iguales = all(json.dumps(x, sort_keys=True) == json.dumps(y, sort_keys=True)
                        for x, y in zip(sorted((n for n in w["nodes"] if n["name"] != NODO), key=lambda n: n["name"]),
                                        sorted((n for n in post["nodes"] if n["name"] != NODO), key=lambda n: n["name"])))
    checks = {
        "nodo nuevo == esperado": np["parameters"]["jsCode"] == nuevo,
        "resto de nodos intactos": otros_iguales and len(post["nodes"]) == len(w["nodes"]),
        "conexiones intactas": json.dumps(post["connections"], sort_keys=True) == json.dumps(w["connections"], sort_keys=True),
        "activo": post.get("active") is True,
        "webhookId evo-webhook-v2": any(x.get("webhookId") == "evo-webhook-v2" for x in post["nodes"]),
        "settings conservados": all(post.get("settings", {}).get(k) == v for k, v in (w.get("settings") or {}).items()),
    }
    for k, v in checks.items():
        print(f"  {'OK ' if v else 'MAL'} {k}")
    if not all(checks.values()):
        print(f"\nAlgo no quedó como se esperaba. Vuelta atrás: python scripts/restaurar_workflow.py {pre.relative_to(ROOT).as_posix()} --apply")
        raise SystemExit(1)
    print(f"\nListo. Vuelta atrás si hiciera falta: python scripts/restaurar_workflow.py {pre.relative_to(ROOT).as_posix()} --apply")


if __name__ == "__main__":
    main()
