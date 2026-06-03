"""
Aplica la REGLA CRITICA - UNA SOLA ESCALACION POR TURNO al Sub-Agent General.

Mismo patron que Confirmar, Cancelar, Urgencia, Agendar. Defensa en profundidad
contra retry-loop si el LLM decide escalar y reintenta la tool.
"""
import json
import os
import sys
import time
import urllib.request

WF_ID = "O155MqHgOSaNZ9ye"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
API_KEY = os.environ.get("N8N_API_KEY")
DRY_RUN = "--dry-run" in sys.argv

if not API_KEY:
    sys.exit("ERROR: N8N_API_KEY")

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow",
    "timezone", "executionOrder", "callerPolicy", "callerIds",
}

NEW_RULE = """

**REGLA CRITICA - UNA SOLA ESCALACION POR TURNO**:
Si ya llamaste `escalar_a_secretaria` UNA vez en este turno (cualquier paso) -> INMEDIATAMENTE responder con el canned cierre y TERMINAR. NUNCA llamar la tool dos veces en el mismo turno. NUNCA seguir intentando otras tools despues de escalar. La tool ya aplico el label humano en Chatwoot y notifico a Iri por WhatsApp. Tu trabajo termino. Responde el canned y FIN.
"""

MARKER = "UNA SOLA ESCALACION POR TURNO"


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


def main():
    print(f"GET workflow {WF_ID}...")
    _, wf = http("GET", f"/workflows/{WF_ID}")
    print(f"  active={wf['active']} nodes={len(wf['nodes'])}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_FIX_GENERAL_RETRY_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    node = next((n for n in wf["nodes"] if n["name"] == "Sub-Agent General"), None)
    if not node:
        sys.exit("ABORT: Sub-Agent General no encontrado")

    sm = node["parameters"].get("options", {}).get("systemMessage", "")
    if MARKER in sm:
        sys.exit("ABORT: regla ya aplicada (idempotent skip)")

    new_sm = sm.rstrip() + NEW_RULE
    node["parameters"]["options"]["systemMessage"] = new_sm
    print(f"  Sub-Agent General: {len(sm)} -> {len(new_sm)} chars (+{len(new_sm)-len(sm)})")

    if DRY_RUN:
        out = f"workflows/history/v6_FIX_GENERAL_RETRY_DRY_{ts}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"DRY RUN -> {out}")
        return

    settings = {k: v for k, v in wf.get("settings", {}).items() if k in ALLOWED_SETTINGS}
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": settings,
        "staticData": wf.get("staticData"),
    }
    print("PUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  status={status}")

    _, wf2 = http("GET", f"/workflows/{WF_ID}")
    for n in wf2["nodes"]:
        if n["name"] == "Sub-Agent General":
            assert MARKER in n["parameters"]["options"]["systemMessage"]
            print(f"  verified (active={wf2['active']})")
            break

    post_path = f"workflows/history/v6_POST_FIX_GENERAL_RETRY_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
