# -*- coding: utf-8 -*-
"""
apply_fix_cierres_v6.py — 2026-10-06 · aplica en el v6 vivo el arreglo de los "gracias" (el mismo texto que imprime parche_manual_cierres_v6.py).

PROBLEMA (casos reales 05-06/10): un cierre ("Si , gracias", "Ok, muchas gracias", "Gracias!") recibe una respuesta de mas:
  - el Sub-Agent Confirmar devuelve [NO_REPLY] y el nodo `Fallback Output` lo pisa con "Ya le transmito su consulta a la secretaria…"
  - el Sub-Agent General contesta "De nada. Quedo a disposicion para cualquier consulta o para reprogramar su turno…"
ARREGLO (2 nodos, nada mas):
  1. `Fallback Output`: la linea `const esCierrePuro = …` reconoce tambien cierres con "si", "bien", un nombre o emojis (si hay una pregunta o otra palabra, NO es cierre).
  2. `Sub-Agent General`: regla 7 de cierres (devolver exactamente [NO_REPLY]), a continuacion de la regla 6 y antes del bloque de instrucciones de la clinica.

USO:  python scripts/apply_fix_cierres_v6.py            # simulacion: prueba el codigo y muestra el diff, no escribe nada
      python scripts/apply_fix_cierres_v6.py --apply    # backup PRE + PUT + verificacion + backup POST
Regla del proyecto: NUNCA --apply sin OK de Lucas.
"""
import argparse, copy, difflib, json, os, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require
from parche_manual_cierres_v6 import LINEA_VIEJA, BLOQUE_NUEVO, REGLA_GENERAL

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
WID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
ANCLA_GENERAL = "{{ $('Extraer Horarios y Precio').item.json.dir_notas ?"
MARCA_GENERAL = "CIERRES (REGLA ABSOLUTA)"


def transformar_fallback(code):
    if "soloCierre" in code:
        sys.exit("ABORTO: 'Fallback Output' ya tiene el arreglo de cierres.")
    if code.count(LINEA_VIEJA) != 1:
        sys.exit(f"ABORTO: en 'Fallback Output' la linea a reemplazar aparece {code.count(LINEA_VIEJA)} veces (esperaba 1). Otra sesion cambio el nodo.")
    return code.replace(LINEA_VIEJA, BLOQUE_NUEVO)


def transformar_general(prompt):
    if MARCA_GENERAL in prompt:
        sys.exit("ABORTO: 'Sub-Agent General' ya tiene la regla de cierres.")
    if prompt.count(ANCLA_GENERAL) != 1:
        sys.exit(f"ABORTO: en 'Sub-Agent General' el ancla aparece {prompt.count(ANCLA_GENERAL)} veces (esperaba 1). Otra sesion cambio el prompt.")
    return prompt.replace(ANCLA_GENERAL, REGLA_GENERAL + "\n\n" + ANCLA_GENERAL)


def probar_fallback(codigo):
    """Corre el codigo REAL del nodo (ya transformado) con el harness: cierres → silencio; no cierres → como antes."""
    cierres = ["Si , gracias", "Bien gracias", "Bien\nMuchas gracias Iris", "Muchas gracias 🫂", "Gracias", "Gracias Iris!", "Ok gracias", "Dale, gracias", "Ok, muchas gracias", "Gracias!"]
    no_cierres = ["Gracias, ¿cuánto sale?", "Quiero cambiar el turno", "Mi hijo tiene dolor", "No puedo ir el jueves", "Gracias pero quiero cambiar el turno", "Ok el jueves a las 9"]
    casos = [{"id": "C|" + t, "codigo": codigo, "input": {"output": "[NO_REPLY]"}, "nodos": {"Preparar Mensaje Final": {"text": t}}} for t in cierres + no_cierres]
    with tempfile.TemporaryDirectory() as d:
        c = os.path.join(d, "c.json")
        json.dump(casos, open(c, "w", encoding="utf-8"), ensure_ascii=False)
        p = subprocess.run(["node", str(ROOT / "tests" / "harness_code_node.mjs"), c], capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit("ABORTO: el harness fallo:\n" + p.stderr[-1200:])
        res = {r["id"]: (r.get("json") or {}).get("output") for r in json.loads(p.stdout)}
    fallas = [t for t in cierres if res["C|" + t] != "[NO_REPLY]"] + [t for t in no_cierres if not str(res["C|" + t] or "").startswith("Hola! Ya le transmito")]
    print(f"  pruebas del Fallback Output sobre el codigo vivo: {len(cierres)} cierres → silencio, {len(no_cierres)} no cierres → igual que antes: {'OK' if not fallas else 'FALLAS ' + repr(fallas)}")
    if fallas:
        sys.exit("ABORTO: las pruebas no pasan con el codigo vivo.")


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    wf = api(f"/workflows/{WID}")
    nuevo = copy.deepcopy(wf)
    fo_old = next(n for n in wf["nodes"] if n["name"] == "Fallback Output")
    fo_new = next(n for n in nuevo["nodes"] if n["name"] == "Fallback Output")
    ge_old = next(n for n in wf["nodes"] if n["name"] == "Sub-Agent General")
    ge_new = next(n for n in nuevo["nodes"] if n["name"] == "Sub-Agent General")
    fo_new["parameters"]["jsCode"] = transformar_fallback(fo_old["parameters"]["jsCode"])
    ge_new["parameters"]["options"]["systemMessage"] = transformar_general(ge_old["parameters"]["options"]["systemMessage"])
    print(f"v6 active={wf.get('active')} nodos={len(wf['nodes'])} v={wf.get('versionId')[:8]}")
    probar_fallback(fo_new["parameters"]["jsCode"])
    print("\n--- v6 · Fallback Output")
    for l in difflib.unified_diff(fo_old["parameters"]["jsCode"].splitlines(), fo_new["parameters"]["jsCode"].splitlines(), lineterm="", n=0):
        if not l.startswith(("---", "+++", "@@")):
            print("   ", l[:200])
    print("\n--- v6 · Sub-Agent General (prompt)")
    for l in difflib.unified_diff(ge_old["parameters"]["options"]["systemMessage"].splitlines(), ge_new["parameters"]["options"]["systemMessage"].splitlines(), lineterm="", n=0):
        if not l.startswith(("---", "+++", "@@")):
            print("   ", l[:200])
    if not apply:
        print("\n[SIMULACION] No se aplico nada. Correr con --apply (con OK de Lucas).")
        return
    HIST.mkdir(parents=True, exist_ok=True)
    pre = HIST / f"{WID}_PRE_cierres_{int(time.time())}.json"
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n  backup:", pre.name)
    if api(f"/workflows/{WID}").get("versionId") != wf.get("versionId"):
        sys.exit("ABORTO: el v6 cambio mientras preparaba el PUT.")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = {k: v for k, v in (nuevo.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{WID}", method="PUT", payload=body)
    post = api(f"/workflows/{WID}")
    (HIST / f"{WID}_POST_cierres_{int(time.time())}.json").write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
    viejos = {n["name"]: n for n in wf["nodes"]}
    cambiados = sorted(n["name"] for n in post["nodes"] if viejos.get(n["name"]) != n)
    webhook = next((n for n in post["nodes"] if n.get("webhookId") == "evo-webhook-v2"), None)
    p_fo = next(n for n in post["nodes"] if n["name"] == "Fallback Output")["parameters"]["jsCode"]
    p_ge = next(n for n in post["nodes"] if n["name"] == "Sub-Agent General")["parameters"]["options"]["systemMessage"]
    codigo_ok = p_fo == fo_new["parameters"]["jsCode"] and p_ge == ge_new["parameters"]["options"]["systemMessage"]
    print("  nodos que cambiaron:", cambiados, "| codigo vivo == codigo probado:", codigo_ok, "| activo:", post.get("active"),
          "| webhookId evo-webhook-v2:", bool(webhook), "| mismas conexiones:", wf["connections"] == post["connections"], "| nodos:", len(post["nodes"]))
    if cambiados != ["Fallback Output", "Sub-Agent General"] or not codigo_ok or not post.get("active") or not webhook or wf["connections"] != post["connections"] or len(wf["nodes"]) != len(post["nodes"]):
        sys.exit("ATENCION: la verificacion no dio lo esperado. Restaurar con: python scripts/restaurar_workflow.py workflows/history/" + pre.name + " --apply")
    print("Aplicado.")


if __name__ == "__main__":
    main()
