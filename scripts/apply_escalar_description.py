"""
Actualiza la description de la tool escalar_a_secretaria (#23).

Razon: la description actual dice "consultas de precios/presupuestos" pero el
prompt prohibe escalar precios (deben venir del header LITERAL). El LLM puede
escalar precios innecesariamente y genera ruido a Iri.

Cambio: nueva description que aclara cuando SI y cuando NO usar la tool.
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

NEW_DESC = (
    "Escala el caso a la secretaria humana (deriva al grupo de WhatsApp del consultorio "
    "y aplica label humano en Chatwoot para que el bot NO siga respondiendo). "
    "Usa esta tool cuando: "
    "(a) urgencia medica o dental (dolor, sangrado, aparato salido, pieza caida, hinchazon, fiebre); "
    "(b) paciente insatisfecho, queja o reclamo; "
    "(c) consulta sobre obras sociales o cobertura; "
    "(d) paciente pide hablar con una persona; "
    "(e) cualquier consulta que NO encaje en agendar/confirmar/cancelar/info canned. "
    "NO uses esta tool para: precios de consulta (usa el valor LITERAL del header), "
    "horarios, direccion o alias bancario (todos son info canned del header). "
    "Argumento `query`: resumen de 1-2 oraciones del motivo de escalacion."
)


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

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_ESCALAR_DESC_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    node = next((n for n in wf["nodes"] if n["name"] == "escalar_a_secretaria"), None)
    if node is None:
        sys.exit("ABORT: nodo escalar_a_secretaria no encontrado")

    old_desc = node["parameters"].get("description", "")
    print(f"  old desc ({len(old_desc)} chars): {old_desc[:120]}...")
    node["parameters"]["description"] = NEW_DESC
    print(f"  new desc ({len(NEW_DESC)} chars): {NEW_DESC[:120]}...")

    if DRY_RUN:
        out = f"workflows/history/v6_ESCALAR_DESC_DRY_{ts}.json"
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
        if n["name"] == "escalar_a_secretaria":
            assert n["parameters"].get("description") == NEW_DESC, "FAIL: description no actualizada"
            print(f"  verified")
            break

    post_path = f"workflows/history/v6_POST_ESCALAR_DESC_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
