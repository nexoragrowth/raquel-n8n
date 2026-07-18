"""
Prep / Restore del v6 para correr tests sinteticos en modo shadow.

PREP (activar modo test):
  1. Backup completo del v6 + estado de helpers
  2. Disable 4 nodos que tocan APIs externas:
     - Evolution API - Enviar Mensaje
     - Evolution - Typing
     - HTTP Send Admin Confirm
  3. Disable 4 tools Dentalink de ESCRITURA:
     - reservar_turno, cancelar_turno, confirmar_turno, crear_paciente_dentalink
     (las de lectura quedan activas: buscar_horarios, ver_turnos_paciente, ver_profesionales, buscar_paciente_dentalink)
  4. escalar_a_secretaria: cambiar secretaryPhone hardcoded a Lucas
  5. Webhook path: 'evolution-v2' -> 'evolution-v6-test' (NO cambia webhookId)
  6. Activar workflows helpers (cleanup + seed) y v6

RESTORE (volver a producción):
  Aplica el backup pre-prep tal cual y desactiva helpers + v6.

Uso:
  N8N_API_KEY=... python scripts/test_prep_restore.py --prep
  N8N_API_KEY=... python scripts/test_prep_restore.py --restore <backup_path>
"""
import json
import os
import sys
import time
import urllib.request

V6 = "O155MqHgOSaNZ9ye"
HELPER_CLEANUP = "iarl7CSBk4fzdgm4"
HELPER_SEED = "JgFfQT38VWSfIUQv"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
API_KEY = os.environ.get("N8N_API_KEY")
MODE_PREP = "--prep" in sys.argv
MODE_RESTORE = "--restore" in sys.argv

if not API_KEY:
    sys.exit("ERROR: N8N_API_KEY")
if not (MODE_PREP or MODE_RESTORE):
    sys.exit("usage: --prep | --restore <backup_path>")

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow",
    "timezone", "executionOrder", "callerPolicy", "callerIds",
}

DISABLE_NODES = {
    "Evolution API - Enviar Mensaje",
    "Evolution - Typing",
    "HTTP Send Admin Confirm",
    "reservar_turno",
    "cancelar_turno",
    "confirmar_turno",
    "crear_paciente_dentalink",
}

LUCAS_PHONE = "5491161461034"
IRINA_PHONE_LITERAL = "'5493885786946'"


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


def put_workflow(wf):
    settings = {k: v for k, v in wf.get("settings", {}).items() if k in ALLOWED_SETTINGS}
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": settings,
        "staticData": wf.get("staticData"),
    }
    return http("PUT", f"/workflows/{wf['id']}", payload)


def activate(wid, active):
    return http("POST" if active else "POST", f"/workflows/{wid}/{'activate' if active else 'deactivate'}")


def prep():
    print(f"GET v6 {V6}...")
    _, wf = http("GET", f"/workflows/{V6}")
    print(f"  active={wf['active']} nodes={len(wf['nodes'])}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_TEST_PREP_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")
    print(f"  USAR ESTE BACKUP PARA RESTORE:")
    print(f"    python scripts/test_prep_restore.py --restore {backup_path}")
    print()

    disabled = 0
    for n in wf["nodes"]:
        if n["name"] in DISABLE_NODES:
            n["disabled"] = True
            disabled += 1
            print(f"  disabled: {n['name']}")
    print(f"  total disabled: {disabled}/{len(DISABLE_NODES)}")

    escalar_node = next((n for n in wf["nodes"] if n["name"] == "escalar_a_secretaria"), None)
    if escalar_node:
        js = escalar_node["parameters"].get("jsCode", "")
        if IRINA_PHONE_LITERAL in js:
            new_js = js.replace(IRINA_PHONE_LITERAL, f"'{LUCAS_PHONE}'")
            escalar_node["parameters"]["jsCode"] = new_js
            print(f"  escalar_a_secretaria: secretaryPhone -> {LUCAS_PHONE} (Lucas)")
        else:
            print(f"  WARN: no encontre la literal {IRINA_PHONE_LITERAL} en escalar_a_secretaria")

    webhook = next((n for n in wf["nodes"] if n["name"] == "Webhook - Evolution API"), None)
    if webhook:
        old_path = webhook["parameters"].get("path")
        webhook["parameters"]["path"] = "evolution-v6-test"
        print(f"  webhook path: {old_path!r} -> 'evolution-v6-test' (webhookId intacto)")
    else:
        sys.exit("ABORT: Webhook - Evolution API node not found")

    print("PUT v6...")
    status, _ = put_workflow(wf)
    print(f"  status={status}")

    print("Activating helpers...")
    for hid, hname in [(HELPER_CLEANUP, "cleanup"), (HELPER_SEED, "seed")]:
        try:
            s, _ = http("POST", f"/workflows/{hid}/activate")
            print(f"  activate {hname} ({hid}): status={s}")
        except urllib.error.HTTPError as e:
            print(f"  activate {hname}: ERR {e.code}")

    print("Activating v6...")
    s, _ = http("POST", f"/workflows/{V6}/activate")
    print(f"  v6 activate: status={s}")

    _, wf2 = http("GET", f"/workflows/{V6}")
    print(f"  verified v6 active={wf2['active']}")
    print()
    print("OK — listo para correr tests contra https://n8n.raquelrodriguez.com.ar/webhook/evolution-v6-test")


def restore(backup_path):
    if not os.path.exists(backup_path):
        sys.exit(f"ERROR: backup no encontrado: {backup_path}")
    print(f"Loading backup: {backup_path}")
    with open(backup_path, encoding="utf-8") as f:
        wf = json.load(f)
    print(f"  backup name={wf['name']!r} pre_active={wf['active']}")

    print("Deactivating v6...")
    try:
        http("POST", f"/workflows/{V6}/deactivate")
    except urllib.error.HTTPError as e:
        print(f"  v6 deactivate warn: {e.code}")

    print("Deactivating helpers...")
    for hid, hname in [(HELPER_CLEANUP, "cleanup"), (HELPER_SEED, "seed")]:
        try:
            http("POST", f"/workflows/{hid}/deactivate")
        except urllib.error.HTTPError as e:
            print(f"  deactivate {hname}: warn {e.code}")

    print("PUT v6 with backup content...")
    status, _ = put_workflow(wf)
    print(f"  status={status}")

    _, wf2 = http("GET", f"/workflows/{V6}")
    print(f"  verified v6 active={wf2['active']} nodes={len(wf2['nodes'])}")
    webhook = next((n for n in wf2["nodes"] if n["name"] == "Webhook - Evolution API"), None)
    print(f"  webhook path: {webhook['parameters'].get('path')!r}")
    disabled = [n["name"] for n in wf2["nodes"] if n.get("disabled")]
    print(f"  nodes disabled: {disabled if disabled else 'none'}")

    print()
    print("OK — v6 restaurado a estado pre-test")


if __name__ == "__main__":
    import urllib.error
    if MODE_PREP:
        prep()
    else:
        idx = sys.argv.index("--restore")
        if idx + 1 >= len(sys.argv):
            sys.exit("usage: --restore <backup_path>")
        restore(sys.argv[idx + 1])
