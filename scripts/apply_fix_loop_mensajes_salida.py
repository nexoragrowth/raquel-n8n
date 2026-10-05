# -*- coding: utf-8 -*-
"""
apply_fix_loop_mensajes_salida.py — el bot genera la respuesta pero NO la envia (desde 2026-10-05 04:09Z).

CAUSA: scripts/apply_desacoplar_chatwoot.py, al limpiar conexiones de los nodos borrados, descarto
los grupos de salida vacios (`if filtered: new_groups.append(filtered)`). Eso corrio el indice de
salida de `Loop Mensajes` (splitInBatches v3: out0 = done, out1 = loop):

    antes:  Loop Mensajes  out0=[]                      out1=['Evolution - Typing']
    ahora:  Loop Mensajes  out0=['Evolution - Typing']  out1=(nada)

En la primera vuelta el item sale por out1 (loop), que no tiene nada conectado: la ejecucion termina
en "success" sin pasar por Evolution - Typing -> Gate Humano Final -> Evolution API - Enviar Mensaje.
Evidencia: execs 294444, 294445, 294447, 294448, 294465 (respuesta generada, 0 envios).
El triaje no se ve afectado (tiene sus propios nodos de envio).

FIX: restaurar la conexion tal como estaba (un solo cambio, en `connections["Loop Mensajes"]`).

USO:
    python scripts/apply_fix_loop_mensajes_salida.py            # simulacion (solo GET)
    python scripts/apply_fix_loop_mensajes_salida.py --apply    # backup PRE + PUT + verificacion + backup POST

Regla del proyecto: NUNCA --apply sin OK explicito de Lucas. Despues de aplicar, probar de punta a
punta con un mensaje real (regla 8) y limpiar los residuos del numero de prueba (regla 9).
"""
import argparse, copy, json, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
WF_ID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
LOOP, TYPING, WEBHOOK = "Loop Mensajes", "Evolution - Typing", "Webhook - Evolution API"


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"),
                                          "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def salidas(wf):
    return [[c["node"] for c in (g or [])] for g in wf["connections"].get(LOOP, {}).get("main", [])]


def backup(wf, label):
    HIST.mkdir(parents=True, exist_ok=True)
    dest = HIST / f"{WF_ID}_{label}_{int(time.time())}.json"
    dest.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  backup: workflows/history/{dest.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    wf = api(f"/workflows/{WF_ID}")
    nodes = {n["name"]: n for n in wf["nodes"]}
    print(f"v6 {WF_ID} | active={wf.get('active')} | {len(wf['nodes'])} nodos | updatedAt={wf.get('updatedAt')} | versionId={wf.get('versionId')}")

    if LOOP not in nodes or TYPING not in nodes:
        sys.exit(f"ABORTO: falta el nodo '{LOOP}' o '{TYPING}'. No toco nada.")
    if not nodes[LOOP]["type"].endswith("splitInBatches") or nodes[LOOP].get("typeVersion") != 3:
        sys.exit(f"ABORTO: '{LOOP}' no es splitInBatches v3 (out0=done, out1=loop). Revisar a mano.")

    actual = salidas(wf)
    print(f"  {LOOP} ahora:    out0={actual[0] if len(actual) > 0 else []}  out1={actual[1] if len(actual) > 1 else '(nada)'}")
    if len(actual) >= 2 and actual[0] == [] and actual[1] == [TYPING]:
        print("  Ya esta bien conectado (out1 -> Evolution - Typing). Nada que hacer.")
        return
    if actual != [[TYPING]]:
        sys.exit("ABORTO: el estado no es el esperado ([['Evolution - Typing']]). Otra sesion lo cambio: revisar a mano.")

    nuevo = copy.deepcopy(wf)
    nuevo["connections"][LOOP]["main"] = [[], [{"node": TYPING, "type": "main", "index": 0}]]
    print(f"  {LOOP} despues:  out0=[]  out1=['{TYPING}']")
    print("  Unico cambio: connections['Loop Mensajes'].main  (0 nodos tocados)")

    if not args.apply:
        print("\n[SIMULACION] No se aplico nada. Correr con --apply (con OK de Lucas).")
        return

    # otra sesion puede haber hecho un PUT entre el GET y ahora: re-chequear justo antes de escribir
    otra = api(f"/workflows/{WF_ID}")
    if otra.get("versionId") != wf.get("versionId"):
        sys.exit("ABORTO: el workflow cambio mientras preparaba el fix (otra sesion hizo un PUT). Volver a correr.")

    backup(wf, "PRE_fix_loop_salida")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = {k: v for k, v in (nuevo.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{WF_ID}", method="PUT", payload=body)

    post = api(f"/workflows/{WF_ID}")
    backup(post, "POST_fix_loop_salida")
    pnodes = {n["name"]: n for n in post["nodes"]}
    otras_pre = {k: v for k, v in wf["connections"].items() if k != LOOP}
    otras_post = {k: v for k, v in post["connections"].items() if k != LOOP}
    checks = {
        "Loop Mensajes out1 -> Evolution - Typing": salidas(post) == [[], [TYPING]],
        "misma cantidad de nodos": len(post["nodes"]) == len(wf["nodes"]),
        "webhookId evo-webhook-v2 intacto": pnodes.get(WEBHOOK, {}).get("webhookId") == "evo-webhook-v2",
        "workflow sigue activo": post.get("active") is True,
        "resto de las conexiones identico": otras_pre == otras_post,
        "parametros de nodos identicos": [n.get("parameters") for n in wf["nodes"]] == [n.get("parameters") for n in post["nodes"]],
    }
    for nombre, ok in checks.items():
        print(f"  {'OK   ' if ok else 'FALLA'} {nombre}")
    if not all(checks.values()):
        sys.exit("VERIFICACION FALLIDA: revisar ya. El backup PRE esta en workflows/history/.")
    print("\nAplicado. Falta la prueba real: mandar un mensaje desde el numero de prueba, confirmar que LLEGA la "
          "respuesta y que la ejecucion pasa por 'Evolution API - Enviar Mensaje'. Despues limpiar residuos "
          "(scripts/limpiar_numero_demo.py).")


if __name__ == "__main__":
    main()
