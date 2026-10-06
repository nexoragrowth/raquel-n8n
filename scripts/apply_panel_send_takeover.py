# -*- coding: utf-8 -*-
"""
apply_panel_send_takeover.py — 2026-10-05

Satelite "Panel — acciones staff" (jzxb5zUKCaJcvCgp). Nodo `Validar secreto`: `humano` sale de body.humano, que el panel
solo manda en el toggle. En panel-send-human llega undefined → humano=false → `Sincronizar Takeover Supabase` ejecuta
human_takeover=false, human_takeover_at=NULL DESPUES de mandar el mensaje del staff: el staff escribe y el bot queda activo
(y puede contestarle encima). Fix de 1 linea: si la accion es "send", humano = true (escribe una persona = modo humano,
igual que la rama fromMe del v6).

USO:  python scripts/apply_panel_send_takeover.py            # simulacion: muestra el diff
      python scripts/apply_panel_send_takeover.py --apply    # backup PRE + PUT + verificacion + backup POST
"""
import argparse, copy, json, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
WID = "jzxb5zUKCaJcvCgp"
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

VIEJO = 'const humano = body.humano === true || body.humano === "true";'
NUEVO = ('// Un mensaje mandado desde el panel lo escribe una persona → modo humano (igual que la rama fromMe del v6). Solo el toggle manda humano explicito.\n'
         'const humano = accion === "send" ? true : (body.humano === true || body.humano === "true");')


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
    n = next(n for n in wf["nodes"] if n["name"] == "Validar secreto")
    code = n["parameters"]["jsCode"]
    if code.count(VIEJO) != 1:
        sys.exit(f"ABORTO: la linea a cambiar aparece {code.count(VIEJO)} veces (esperaba 1). Ya aplicado o cambiado a mano.")
    # `accion` se declara ANTES de `humano` en el nodo: verificarlo para no referenciarla antes de definirla.
    if code.index("const accion") > code.index(VIEJO):
        sys.exit("ABORTO: `accion` se define despues de `humano`.")
    nuevo = copy.deepcopy(wf)
    next(m for m in nuevo["nodes"] if m["name"] == "Validar secreto")["parameters"]["jsCode"] = code.replace(VIEJO, NUEVO)
    print("--- Validar secreto (satelite Panel — acciones staff)\n    - " + VIEJO + "\n    + " + NUEVO.replace("\n", "\n    + "))
    if not apply:
        print("\n[SIMULACION] No se aplico nada. Correr con --apply.")
        return
    HIST.mkdir(parents=True, exist_ok=True)
    pre = HIST / f"{WID}_PRE_panel_send_takeover_{int(time.time())}.json"
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print("  backup:", pre.name)
    if api(f"/workflows/{WID}").get("versionId") != wf.get("versionId"):
        sys.exit("ABORTO: el workflow cambio mientras preparaba el PUT.")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = {k: v for k, v in (nuevo.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{WID}", method="PUT", payload=body)
    post = api(f"/workflows/{WID}")
    (HIST / f"{WID}_POST_panel_send_takeover_{int(time.time())}.json").write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
    cambiados = [a["name"] for a, b in zip(wf["nodes"], post["nodes"]) if a != b]
    print("  nodos que cambiaron:", cambiados, "| activo:", post.get("active"), "| mismos nodos:", len(wf["nodes"]) == len(post["nodes"]))
    if cambiados != ["Validar secreto"] or not post.get("active"):
        sys.exit("ATENCION: la verificacion no dio lo esperado. Restaurar con scripts/restaurar_workflow.py " + pre.name)
    print("Aplicado.")


if __name__ == "__main__":
    main()
