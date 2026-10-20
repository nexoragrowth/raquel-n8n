# -*- coding: utf-8 -*-
"""
apply_v6_token_webhook.py — 2026-10-20 · SEG-06 (parte 1): cierra la puerta trasera del webhook del v6 sin tocar Evolution ni el VPS.

PROBLEMA: /webhook/evolution-v2 no autentica: cualquiera que conozca la URL puede inyectar mensajes (o un "/bot off" haciéndose pasar por un
admin: misma clase de falla que la causa 1 del incidente Mariela) y saltear el límite de mensajes con `source: 'test_e2e_suite'`.

SOLUCIÓN: cada evento real de Evolution GO trae `instanceToken` (el token de la instancia, que solo tiene Evolution): verificado el 20/10 en 100 de
100 ejecuciones reales, siempre el mismo valor. "Webhook Validator" pasa a exigirlo (fail-closed). Y "Rate Limit Prep" deja de aceptar el atajo
`test_e2e_suite`. El token se lee de la última ejecución real y se inyecta en el nodo; este script nunca lo imprime ni lo escribe en el repo
(los backups van a workflows/history/, que está en .gitignore).

RIESGO Y VUELTA ATRÁS: si se RECREA la instancia de Evolution cambia el token y el bot queda sordo. Arreglo en 1 comando:
  python scripts/apply_v6_token_webhook.py --actualizar-token --apply   (toma el token del último mensaje rechazado y lo vuelve a poner)
El Health Check además avisa a Lucas si no entra nada en 6 h hábiles. Revertir todo: --revertir --apply (último backup PRE).

USO:  python scripts/apply_v6_token_webhook.py                 # simulación
      python scripts/apply_v6_token_webhook.py --apply
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flag_v7 import api

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
V6 = "O155MqHgOSaNZ9ye"
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution", "executionTimeout",
               "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
VAL, RL = "Webhook Validator", "Rate Limit Prep"
ANCLA_VAL = "// 2) Shape check: debe ser payload Evolution GO (whatsmeow)"
MARCA = "// 1b) (20/10, SEG-06) instanceToken"
BLOQUE_VAL = MARCA + """: solo Evolution conoce el token de la instancia. Sin él (o con otro) se descarta: nadie puede inyectar
//     mensajes ni un "/bot off" falso aunque conozca la URL. Si se RECREA la instancia, actualizar con scripts/apply_v6_token_webhook.py --actualizar-token.
const TOKEN_INSTANCIA = '@@TOKEN@@';
if ((body.instanceToken || '') !== TOKEN_INSTANCIA) {
  console.log('[SECURITY] Webhook rejected: instanceToken ausente o distinto');
  return [];
}

"""
ATAJO_RL = """if (source === 'test_e2e_suite') {
  return [{ json: { phone, rateLimitKey: 'ratelimit:test:' + Date.now() + ':' + Math.random(), bypass: true } }];
}"""
SIN_ATAJO_RL = "// (20/10, SEG-06) Sin atajo de pruebas: cualquiera podía mandar source 'test_e2e_suite' y saltear el límite."


def token_real(rechazados=False):
    """instanceToken de la ejecución real más reciente del v6 (si rechazados=True, también de las que el validador descartó)."""
    for e in api(f"/executions?workflowId={V6}&limit=30").get("data", []):
        try:
            rd = api(f"/executions/{e['id']}?includeData=true")["data"]["resultData"]["runData"]
            b = rd["Webhook - Evolution API"][0]["data"]["main"][0][0]["json"].get("body", {})
        except Exception:
            continue
        paso = "Rate Limit Prep" in rd or "Kill-switch Check" in rd
        if b.get("event") == "Message" and b.get("instanceToken") and (rechazados or paso):
            return b["instanceToken"]
    raise SystemExit("No encontré una ejecución real reciente con instanceToken.")


def put(w):
    api(f"/workflows/{V6}", "PUT", {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
                                     "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in SETTINGS_OK}, "staticData": w.get("staticData")})


def check_triaje():
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], cwd=ROOT).returncode == 0


def guardar(w, etiqueta, ts):
    HIST.mkdir(parents=True, exist_ok=True)
    (HIST / f"{V6}_{etiqueta}_token_webhook_{ts}.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")


def verificar(post, token):
    v = next(x for x in post["nodes"] if x["name"] == VAL)["parameters"]["jsCode"]
    r = next(x for x in post["nodes"] if x["name"] == RL)["parameters"]["jsCode"]
    return (MARCA in v and token in v and v.index(MARCA) < v.index(ANCLA_VAL) and "test_e2e_suite' ) {" not in r and ATAJO_RL not in r
            and post.get("active") is True and any(x.get("webhookId") == "evo-webhook-v2" for x in post["nodes"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--actualizar-token", action="store_true"); ap.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    w = api(f"/workflows/{V6}")
    val = next(x for x in w["nodes"] if x["name"] == VAL); rl = next(x for x in w["nodes"] if x["name"] == RL)
    vc, rc = val["parameters"]["jsCode"], rl["parameters"]["jsCode"]
    if a.revertir:
        pres = sorted(HIST.glob(f"{V6}_PRE_token_webhook_*.json"))
        if not pres: raise SystemExit("No hay backup PRE de este cambio.")
        pre = json.loads(pres[-1].read_text(encoding="utf-8"))
        print(f"Revertir a {pres[-1].name}")
        if not a.apply: print("[SIMULACIÓN] --revertir --apply"); return
        if not check_triaje(): raise SystemExit("ABORTO: check_triaje no dio sano.")
        put(pre); print("OK revertido:", api(f"/workflows/{V6}").get("versionId")); return
    if a.actualizar_token:
        if MARCA not in vc: raise SystemExit("El validador no tiene la verificación del token: correr primero sin --actualizar-token.")
        nuevo_tok = token_real(rechazados=True)
        import re
        actual = re.search(r"const TOKEN_INSTANCIA = '([^']*)';", vc)
        if actual and actual.group(1) == nuevo_tok: print("El token del validador ya es el de la instancia actual: nada que hacer."); return
        print("Token de la instancia distinto del del validador: se actualiza.")
        if not a.apply: print("[SIMULACIÓN] --actualizar-token --apply"); return
        ts = int(time.time()); guardar(w, "PRE_actualizar", ts)
        val["parameters"]["jsCode"] = re.sub(r"const TOKEN_INSTANCIA = '[^']*';", "const TOKEN_INSTANCIA = '" + nuevo_tok + "';", vc)
        put(w); post = api(f"/workflows/{V6}"); guardar(post, "POST_actualizar", ts)
        print("OK" if verificar(post, nuevo_tok) else "ATENCIÓN", "· versionId", post.get("versionId")); return
    if MARCA in vc: raise SystemExit("Ya está aplicado.")
    if vc.count(ANCLA_VAL) != 1: raise SystemExit("El validador no tiene la forma esperada: no toco nada.")
    if rc.count(ATAJO_RL) != 1: raise SystemExit("Rate Limit Prep no tiene el atajo esperado: no toco nada.")
    tok = token_real()
    print(f"v6 versionId {w.get('versionId')} · token de la instancia leído de la última ejecución real ({len(tok)} caracteres, no se muestra).")
    print(f"«{VAL}»: se agrega la verificación del instanceToken antes del chequeo de forma (fail-closed).")
    print(f"«{RL}»: se quita el atajo source='test_e2e_suite'.")
    if not a.apply: print("[SIMULACIÓN] Para aplicar: --apply"); return
    print("check_triaje (regla del proyecto: antes de cualquier PUT al v6)")
    if not check_triaje(): raise SystemExit("ABORTO: check_triaje no dio sano. No se tocó nada.")
    w2 = api(f"/workflows/{V6}")
    if w2.get("versionId") != w.get("versionId"): raise SystemExit("El v6 cambió mientras tanto: no hago PUT.")
    if not any(x.get("webhookId") == "evo-webhook-v2" for x in w["nodes"]): raise SystemExit("Falta webhookId evo-webhook-v2: no hago PUT.")
    ts = int(time.time()); guardar(w, "PRE", ts)
    val["parameters"]["jsCode"] = vc.replace(ANCLA_VAL, BLOQUE_VAL.replace("@@TOKEN@@", tok) + ANCLA_VAL)
    rl["parameters"]["jsCode"] = rc.replace(ATAJO_RL, SIN_ATAJO_RL)
    put(w)
    post = api(f"/workflows/{V6}"); guardar(post, "POST", ts)
    ok = verificar(post, tok) and len(post["nodes"]) == len(w["nodes"])
    print(("OK" if ok else "ATENCIÓN") + f": versionId {post.get('versionId')} · nodos {len(post['nodes'])} · activo {post.get('active')} · backups _{ts}")
    print("Verificar con el próximo mensaje real (tiene que pasar el validador) y con un POST sin token (tiene que descartarse).")


if __name__ == "__main__":
    main()
