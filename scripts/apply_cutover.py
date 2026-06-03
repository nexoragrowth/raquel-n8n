"""
Cutover: pasa el v6 de shadow a produccion.

Cambios:
1) Re-activa `Evolution API - Enviar Mensaje` (estaba disabled en shadow).
2) Re-activa `Evolution - Typing` (estaba disabled en shadow).
3) Re-activa `HTTP Send Admin Confirm` (estaba disabled en shadow).
4) Confirma path webhook = `evolution-v2` (path prod).
5) Confirma 4 write tools Dentalink enabled.
6) Confirma fixes previos aplicados (regex prefiltro lucas + GUARD Agendar).

ANTES de correr:
- Verifica que la suite tests/test_conversational_flows.py pase >= 9/10.
- Verifica E2E real validado (cita reservar->confirmar->cancelar).
- Iri y la doctora avisadas del cutover.
- Plan de monitoreo activo: alguien mirando Chatwoot las primeras 6h.

DESPUES de correr:
- Mandar mensaje de test desde tu celular al numero de la clinica para
  confirmar que el bot responde de verdad (no solo procesa).
- Monitorear executions en n8n las primeras 2 horas.

Rollback: si algo sale mal, correr `python scripts/apply_cutover.py --rollback`
(re-disable Send/Typing/Admin Confirm = vuelve a shadow).

Uso:
    python scripts/apply_cutover.py --dry-run
    python scripts/apply_cutover.py
    python scripts/apply_cutover.py --rollback
"""
import json
import os
import re
import sys
import time
import urllib.request

WF_ID = "O155MqHgOSaNZ9ye"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
DRY_RUN = "--dry-run" in sys.argv
ROLLBACK = "--rollback" in sys.argv

API_KEY = os.environ.get("N8N_API_KEY")
if not API_KEY:
    fb = "C:/Users/Lucas/.claude/n8n_backups/test_100_pre_prod.py"
    if os.path.exists(fb):
        with open(fb, encoding="utf-8") as f:
            m = re.search(r'API_KEY\s*=\s*"([^"]+)"', f.read())
            if m:
                API_KEY = m.group(1)
if not API_KEY:
    sys.exit("ERROR: N8N_API_KEY")

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}

NODES_TO_TOGGLE = [
    "Evolution API - Enviar Mensaje",
    "Evolution - Typing",
    "HTTP Send Admin Confirm",
]
WRITE_TOOLS = ["confirmar_turno", "cancelar_turno", "reservar_turno", "crear_paciente_dentalink"]


def http(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        headers={
            "X-N8N-API-KEY": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


def filter_settings(s):
    return {k: v for k, v in (s or {}).items() if k in ALLOWED_SETTINGS}


def strip_meta(wf):
    for k in ("id", "active", "createdAt", "updatedAt", "tags", "versionId", "triggerCount",
              "meta", "isArchived", "shared", "homeProject", "sharedWithProjects", "scopes",
              "description", "pinData", "activeVersionId", "versionCounter", "activeVersion"):
        wf.pop(k, None)
    wf["settings"] = filter_settings(wf.get("settings"))
    return wf


def main():
    mode = "ROLLBACK (shadow)" if ROLLBACK else "CUTOVER (prod)"
    print(f"=== {mode} ===")
    print("Pulling current v6...")
    _, wf = http("GET", f"/workflows/{WF_ID}")

    os.makedirs("workflows/history", exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    label = "ROLLBACK" if ROLLBACK else "CUTOVER"
    pre_path = f"workflows/history/v6_PRE_{label}_{stamp}.json"
    with open(pre_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup pre: {pre_path}")

    # Verificaciones previas
    wh = next((n for n in wf["nodes"]
               if n["type"] == "n8n-nodes-base.webhook" and n["name"].startswith("Webhook")),
              None)
    if not wh:
        sys.exit("ERROR: webhook node no existe")
    if wh["parameters"].get("path") != "evolution-v2":
        sys.exit(f"ERROR: webhook path es '{wh['parameters'].get('path')}' (debe ser 'evolution-v2')")
    if wh.get("webhookId") != "evo-webhook-v2":
        sys.exit(f"ERROR: webhookId es '{wh.get('webhookId')}' (debe ser 'evo-webhook-v2')")

    # Confirmar write tools enabled (deben estar ya enabled de antes)
    if not ROLLBACK:
        for nm in WRITE_TOOLS:
            n = next((x for x in wf["nodes"] if x["name"] == nm), None)
            if not n:
                print(f"  WARN: tool '{nm}' no existe")
                continue
            if n.get("disabled"):
                print(f"  !! AVISO: write tool '{nm}' esta disabled. Cutover requiere todas habilitadas.")
                sys.exit("ERROR: aborting. Habilita las 4 write tools antes de cutover.")

    # Toggle Send/Typing/Admin Confirm
    changes = []
    for nm in NODES_TO_TOGGLE:
        n = next((x for x in wf["nodes"] if x["name"] == nm), None)
        if not n:
            print(f"  WARN: nodo '{nm}' no existe")
            continue
        target = True if ROLLBACK else False  # cutover -> not disabled; rollback -> disabled
        current = n.get("disabled", False)
        if current == target:
            print(f"  {nm}: ya en estado deseado (disabled={current})")
            continue
        n["disabled"] = target
        changes.append((nm, current, target))

    if not changes:
        print("  Nada que cambiar. Salida.")
        return

    print(f"\nCambios ({len(changes)}):")
    for nm, c, t in changes:
        action = "DISABLE" if t else "ENABLE"
        print(f"  {action}: {nm}  (disabled: {c} -> {t})")

    if DRY_RUN:
        dry = f"workflows/history/v6_{label}_DRY_{stamp}.json"
        with open(dry, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"\nDRY RUN -> {dry}")
        return

    payload = strip_meta(dict(wf))
    print("\nApplying PUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  PUT: {status}")

    post_path = f"workflows/history/v6_POST_{label}_{stamp}.json"
    _, post_wf = http("GET", f"/workflows/{WF_ID}")
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(post_wf, f, ensure_ascii=False, indent=2)
    print(f"  backup post: {post_path}")

    # Verificacion
    for nm, c, t in changes:
        n = next((x for x in post_wf["nodes"] if x["name"] == nm), None)
        if n.get("disabled", False) != t:
            sys.exit(f"ERROR: '{nm}' no quedo en disabled={t}")
    print("\n  OK: cambios aplicados y verificados.")
    if not ROLLBACK:
        print("\n  >>> El bot ahora RESPONDE a pacientes reales.")
        print("  >>> Mira las executions en https://n8n.raquelrodriguez.com.ar/workflow/" + WF_ID + "/executions")
        print("  >>> Mandate un test desde otro celular para validar.")
    else:
        print("\n  >>> Volvio a SHADOW. Bot recibe mensajes pero NO responde.")


if __name__ == "__main__":
    main()
