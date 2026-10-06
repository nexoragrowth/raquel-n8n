# -*- coding: utf-8 -*-
"""
apply_fix_modo_humano_1h.py — 2026-10-06 · arregla el modo humano del v6 y deja la vuelta automatica al bot a la 1 hora sin que escriba una persona.

PROBLEMA 1 (medido 06/10): cuando la Dra. o la secretaria escriben desde el celular del consultorio, el bot NO queda en modo humano.
  El nodo `Activar Takeover (fromMe)` del v6 lee `$json.session_id`, pero desde el desacople de Chatwoot (05/10 01:09) su entrada es la salida de
  `Postgres - Save fromMe` (`RETURNING id`), que no trae session_id → "Query Parameters must be a string of comma-separated values or an array of values".
  Tiene continueOnFail, asi que la ejecucion figura "success". 182 de 182 ejecuciones fromMe fallaron desde el 05/10: el flag nunca se prende por este camino
  y el bot le sigue contestando al paciente mientras habla una persona.
PROBLEMA 2 (pedido de Lucas): "post 1 hora de waiting sin hablar un humano, que vuelva a modo bot; siempre sirvio". Esa vuelta la hacia el workflow
  `Auto Reactivar Bot (1h sin humano)` con labels de Chatwoot (apagado con Chatwoot). Desde el desacople la ventana quedo en 24 h.
ARREGLO (todo en terminos de la ventana: `human_takeover_at` se renueva con CADA mensaje del personal, asi que "1 h sin que hable un humano" sale sola):
  v6:     `Activar Takeover (fromMe)` toma el telefono de `Build fromMe AI memory`; `Consultar Takeover Paciente`, `Gate Humano Final` y `Triaje: Decidir`: 24 h → 1 h.
  Helper: `Activar Takeover Paciente` (aviso al grupo con pedido de persona/queja/urgencia): la ventana del CASE pasa de 24 h a 1 h (si no, un takeover vencido no se renueva).
  (El panel usa la misma ventana: lib/modo-humano.ts, HUMANO_MS. Se cambia aparte en el repo del panel.)
NO cambia: kill-switch admin (/bot off), banlist, nada del flujo de mensajes.

USO:  python scripts/apply_fix_modo_humano_1h.py            # simulacion: muestra el diff, no escribe nada
      python scripts/apply_fix_modo_humano_1h.py --apply    # backup PRE + PUT (v6 y Helper) + verificacion + backup POST
Regla del proyecto: NUNCA --apply sin OK de Lucas.
"""
import argparse, copy, difflib, json, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
V6 = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
HELPER = "S5U6tSipzlgFHCkf"
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

PARAM_VIEJO = "={{ $json.session_id }}"
PARAM_NUEVO = "={{ $('Build fromMe AI memory').first().json.session_id }}"
SQL_VIEJO = "> now() - interval '24 hours'"
SQL_NUEVO = "> now() - interval '1 hour'"
JS_VIEJO = "< 24 * 3600 * 1000)"
JS_NUEVO = "< 1 * 3600 * 1000)"


def una_vez(texto, viejo, nuevo, donde):
    if texto.count(viejo) != 1:
        sys.exit(f"ABORTO: en {donde} la cadena a reemplazar aparece {texto.count(viejo)} veces (esperaba 1). Otra sesion cambio el nodo.\n  cadena: {viejo!r}")
    return texto.replace(viejo, nuevo)


def cambiar_v6(nuevo):
    n = {x["name"]: x for x in nuevo["nodes"]}
    a = n["Activar Takeover (fromMe)"]["parameters"]["options"]
    if a.get("queryReplacement") != PARAM_VIEJO:
        sys.exit(f"ABORTO: 'Activar Takeover (fromMe)' ya no tiene el parametro esperado: {a.get('queryReplacement')!r}")
    a["queryReplacement"] = PARAM_NUEVO
    p = n["Consultar Takeover Paciente"]["parameters"]
    p["query"] = una_vez(p["query"], SQL_VIEJO, SQL_NUEVO, "'Consultar Takeover Paciente'")
    for nom in ("Gate Humano Final", "Triaje: Decidir"):
        pp = n[nom]["parameters"]
        pp["jsCode"] = una_vez(pp["jsCode"], JS_VIEJO, JS_NUEVO, f"'{nom}'")
    return ["Activar Takeover (fromMe)", "Consultar Takeover Paciente", "Gate Humano Final", "Triaje: Decidir"]


def cambiar_helper(nuevo):
    n = {x["name"]: x for x in nuevo["nodes"]}
    p = n["Activar Takeover Paciente"]["parameters"]
    p["query"] = una_vez(p["query"], "human_takeover_at > now() - interval '24 hours'", "human_takeover_at > now() - interval '1 hour'", "Helper 'Activar Takeover Paciente'")
    return ["Activar Takeover Paciente"]


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def texto_nodo(n):
    p = n["parameters"]
    return "\n".join([str(p.get("query", "")), str(p.get("jsCode", "")), str((p.get("options") or {}).get("queryReplacement", ""))])


def mostrar_diff(viejo, nuevo, nombres):
    old = {x["name"]: x for x in viejo["nodes"]}
    new = {x["name"]: x for x in nuevo["nodes"]}
    for nom in nombres:
        print(f"--- {viejo['name'][:40]} · {nom}")
        for l in difflib.unified_diff(texto_nodo(old[nom]).splitlines(), texto_nodo(new[nom]).splitlines(), lineterm="", n=0):
            if not l.startswith(("---", "+++", "@@")):
                print("   ", l[:230])


def aplicar(wid, wf, nuevo, nombres, etiqueta):
    pre = HIST / f"{wid}_PRE_{etiqueta}_{int(time.time())}.json"
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print("  backup:", pre.name)
    if api(f"/workflows/{wid}").get("versionId") != wf.get("versionId"):
        sys.exit(f"ABORTO: {wf['name']} cambio mientras preparaba el PUT.")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = {k: v for k, v in (nuevo.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{wid}", method="PUT", payload=body)
    post = api(f"/workflows/{wid}")
    (HIST / f"{wid}_POST_{etiqueta}_{int(time.time())}.json").write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
    viejos = {n["name"]: n for n in wf["nodes"]}
    cambiados = sorted(n["name"] for n in post["nodes"] if viejos.get(n["name"]) != n)
    nuevos = {n["name"]: n for n in nuevo["nodes"]}
    codigo_ok = all(texto_nodo(n) == texto_nodo(nuevos[n["name"]]) for n in post["nodes"] if n["name"] in nombres)
    webhook = any(n.get("webhookId") == "evo-webhook-v2" for n in post["nodes"]) if wid == V6 else True
    print(f"  nodos que cambiaron: {cambiados} | vivo == probado: {codigo_ok} | activo: {post.get('active')} | webhookId evo-webhook-v2: {webhook} | mismas conexiones: {wf['connections'] == post['connections']} | nodos: {len(post['nodes'])}")
    if cambiados != sorted(nombres) or not codigo_ok or not post.get("active") or not webhook or wf["connections"] != post["connections"] or len(wf["nodes"]) != len(post["nodes"]):
        sys.exit(f"ATENCION: la verificacion de {wf['name']} no dio lo esperado. Restaurar con: python scripts/restaurar_workflow.py workflows/history/{pre.name} --apply")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    apply = ap.parse_args().apply
    v6 = api(f"/workflows/{V6}"); v6n = copy.deepcopy(v6); nom6 = cambiar_v6(v6n)
    hp = api(f"/workflows/{HELPER}"); hpn = copy.deepcopy(hp); nomh = cambiar_helper(hpn)
    print(f"v6 active={v6.get('active')} nodos={len(v6['nodes'])} v={v6.get('versionId')[:8]} | Helper active={hp.get('active')} nodos={len(hp['nodes'])} v={hp.get('versionId')[:8]}\n")
    mostrar_diff(v6, v6n, nom6)
    mostrar_diff(hp, hpn, nomh)
    if not apply:
        print("\n[SIMULACION] No se aplico nada. Correr con --apply (con OK de Lucas).")
        return
    HIST.mkdir(parents=True, exist_ok=True)
    print("\nAplicando Helper primero (cambio chico), despues v6:")
    aplicar(HELPER, hp, hpn, nomh, "modo_humano_1h")
    aplicar(V6, v6, v6n, nom6, "modo_humano_1h")
    print("Aplicado.")


if __name__ == "__main__":
    main()
