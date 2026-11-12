# -*- coding: utf-8 -*-
"""
apply_quitar_banlist_v6.py — 2026-10-07 · saca la banlist del v6 (decisión de Lucas: "el banlist es bullshit, lo controlamos con prompt").

QUÉ HACE
  - `Banlist Validator` queda como PASO SIN CONTROL: mismo nombre y la misma salida que hoy cuando no bloquea ({...item, banlist_triggered: null,
    escalate_to_human: false}). No se borra porque `Split en Mensajes`, `Hay humano ahora?` y `Gate Humano Final` leen $('Banlist Validator').first().json:
    borrarlo los rompería.
  - La rama `Banlist Shadow` (Prep → LLM → Log: una segunda opinión de un modelo que solo deja registro) se desconecta y sus 3 nodos quedan deshabilitados.
NO TOCA: triaje, gates de pago/humano/error técnico, Formatting Agent, kill-switch, nada más.
VOLVER ATRÁS: python scripts/restaurar_workflow.py workflows/history/<backup PRE> --apply

USO:  python scripts/apply_quitar_banlist_v6.py            # simulación: muestra el diff, no escribe nada
      python scripts/apply_quitar_banlist_v6.py --apply    # check_triaje → backup PRE → PUT → verificación → backup POST
Regla del proyecto: el --apply lo corre Lucas.
"""
import argparse, copy, json, subprocess, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
V6 = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
VALIDATOR = "Banlist Validator"
SHADOW = ["Banlist Shadow - Prep", "Banlist Shadow - LLM", "Banlist Shadow - Log"]
PASO = """// Banlist Validator — SACADO el 2026-10-07 por decisión de Lucas ("lo controlamos con prompt"): en las pruebas del v7 la banlist frenó solo mensajes
// inocentes ("no se preocupe" de cortesía, "pase por favor su DNI") y el reemplazo genérico confundía al paciente. Queda como paso SIN CONTROL con el mismo
// nombre y la misma salida de "no bloqueó", porque Split en Mensajes, Hay humano ahora? y Gate Humano Final leen $('Banlist Validator').first().json.
// Volver atrás: restaurar el backup PRE de workflows/history/ (apply_quitar_banlist_v6.py).
const item = $input.first().json;
return [{ json: { ...item, banlist_triggered: null, escalate_to_human: false } }];"""


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())
import guarda_vivo  # noqa: E402  (12/11) freno: no pisar en n8n cambios que este repo no conoce (scripts/guarda_vivo.py)
api = guarda_vivo.envolver(api)


def cambiar(wf):
    n = {x["name"]: x for x in wf["nodes"]}
    if VALIDATOR not in n or any(s not in n for s in SHADOW):
        sys.exit("ABORTO: no encuentro los nodos de la banlist con los nombres esperados (¿otra sesión los cambió?).")
    codigo = n[VALIDATOR]["parameters"].get("jsCode", "")
    if "SACADO el 2026-10-07" in codigo:
        sys.exit("Nada que hacer: la banlist del v6 ya está sacada.")
    if "Banlist Validator - 2026-05-09" not in codigo:
        sys.exit("ABORTO: el código de 'Banlist Validator' no es el esperado (¿otra sesión lo cambió?). Revisar a mano.")
    n[VALIDATOR]["parameters"]["jsCode"] = PASO
    for s in SHADOW:
        n[s]["disabled"] = True
    salidas = wf["connections"].get(VALIDATOR, {}).get("main", [])
    antes = sum(len(o) for o in salidas)
    wf["connections"][VALIDATOR]["main"] = [[c for c in o if c.get("node") != SHADOW[0]] for o in salidas]
    despues = sum(len(c) for c in wf["connections"][VALIDATOR]["main"])
    if antes - despues != 1:
        sys.exit(f"ABORTO: esperaba sacar 1 conexión ({VALIDATOR} → {SHADOW[0]}) y saqué {antes - despues}.")
    return codigo


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); apply = ap.parse_args().apply
    wf = api(f"/workflows/{V6}"); nuevo = copy.deepcopy(wf); viejo_codigo = cambiar(nuevo)
    print(f"v6 active={wf.get('active')} nodos={len(wf['nodes'])} versionId={str(wf.get('versionId'))[:8]}\n")
    print(f"--- {VALIDATOR}: {len(viejo_codigo)} caracteres de reglas → paso sin control:\n" + "\n".join("    + " + l for l in PASO.splitlines()))
    print(f"--- conexión que se saca: {VALIDATOR} → {SHADOW[0]}   (sigue: {VALIDATOR} → {[c['node'] for o in nuevo['connections'][VALIDATOR]['main'] for c in o]})")
    print(f"--- nodos deshabilitados: {SHADOW}")
    if not apply:
        print("\n[SIMULACION] No se aplicó nada. Para aplicar: python scripts/apply_quitar_banlist_v6.py --apply")
        return
    print("\n1) check_triaje (regla del proyecto: antes de cualquier PUT al v6)")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], cwd=ROOT)
    if r.returncode != 0:
        sys.exit("ABORTO: check_triaje no dio sano. No se tocó nada.")
    HIST.mkdir(parents=True, exist_ok=True)
    pre = HIST / f"{V6}_PRE_quitar_banlist_{int(time.time())}.json"
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print("2) backup:", pre.name)
    if api(f"/workflows/{V6}").get("versionId") != wf.get("versionId"):
        sys.exit("ABORTO: el v6 cambió mientras preparaba el PUT. No se tocó nada.")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = {k: v for k, v in (nuevo.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{V6}", method="PUT", payload=body)
    post = api(f"/workflows/{V6}")
    (HIST / f"{V6}_POST_quitar_banlist_{int(time.time())}.json").write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
    pn = {x["name"]: x for x in post["nodes"]}
    viejos = {x["name"]: x for x in wf["nodes"]}
    cambiados = sorted(x["name"] for x in post["nodes"] if viejos.get(x["name"]) != x)
    ok = (pn[VALIDATOR]["parameters"].get("jsCode") == PASO and all(pn[s].get("disabled") is True for s in SHADOW)
          and post["connections"] == nuevo["connections"] and len(post["nodes"]) == len(wf["nodes"]) and post.get("active")
          and any(x.get("webhookId") == "evo-webhook-v2" for x in post["nodes"]) and cambiados == sorted([VALIDATOR] + SHADOW))
    print(f"3) verificación: nodos que cambiaron {cambiados} | activo {post.get('active')} | webhookId evo-webhook-v2 conservado | conexiones = las esperadas: {post['connections'] == nuevo['connections']}")
    if not ok:
        sys.exit(f"ATENCION: la verificación no dio lo esperado. Restaurar con: python scripts/restaurar_workflow.py workflows/history/{pre.name} --apply")
    print("Aplicado: la banlist del v6 quedó sacada.")


if __name__ == "__main__":
    main()
