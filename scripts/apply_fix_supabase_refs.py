"""
Fix urgente: remover las referencias a `Supabase - Buscar Paciente` y a campos
de `Handle Stale Session` que dejaron de existir cuando desconectamos los 5
nodos Supabase (#29 del round 2). El system message de los 5 sub-agents
intentaba evaluar `{{ $('Supabase - Buscar Paciente').first().json.nombre }}`
y fallaba en runtime.

Cambios: borrar el bloque `= PACIENTE =` con las refs muertas y reemplazarlo
por una version simplificada que solo usa lo que viene del flow actual.
"""
import json
import os
import re
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

SUB_AGENTS = {
    "Sub-Agent Confirmar",
    "Sub-Agent Cancelar",
    "Sub-Agent Agendar",
    "Sub-Agent Urgencia",
    "Sub-Agent General",
}

NEW_PACIENTE_BLOCK = """= PACIENTE =
Tel: {{ $('Preparar Mensaje Final').first().json.phone }}
Nombre WA: {{ $('Preparar Mensaje Final').first().json.name }} (es nombre de WhatsApp, puede ser apodo/emoji - NO lo uses como nombre real sin confirmar)
"""


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


def patch_system_message(sm: str) -> str:
    """
    Reemplaza el bloque `= PACIENTE =` viejo (con refs a Supabase + Handle Stale)
    por uno simplificado que solo usa Preparar Mensaje Final.
    """
    pattern = re.compile(
        r"= PACIENTE =\n.*?(?=\n= DATOS CLINICA =)",
        re.DOTALL,
    )
    new_sm, count = pattern.subn(NEW_PACIENTE_BLOCK + "\n", sm, count=1)
    return new_sm, count


def main():
    print(f"GET workflow {WF_ID}...")
    _, wf = http("GET", f"/workflows/{WF_ID}")
    print(f"  active={wf['active']} nodes={len(wf['nodes'])}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_FIX_SB_REFS_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    patched = 0
    skipped = 0
    for n in wf["nodes"]:
        if n["name"] not in SUB_AGENTS:
            continue
        opt = n.get("parameters", {}).get("options", {})
        sm = opt.get("systemMessage", "")
        new_sm, count = patch_system_message(sm)
        if count == 0:
            print(f"  SKIP {n['name']}: bloque = PACIENTE = no encontrado o ya patchado")
            skipped += 1
            continue
        n["parameters"]["options"]["systemMessage"] = new_sm
        print(f"  patched {n['name']} ({len(sm)} -> {len(new_sm)} chars)")
        patched += 1

    if patched == 0:
        sys.exit("ABORT: nada que patchar")

    if DRY_RUN:
        out = f"workflows/history/v6_FIX_SB_REFS_DRY_{ts}.json"
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
        if n["name"] in SUB_AGENTS:
            sm = n["parameters"]["options"]["systemMessage"]
            assert "Supabase - Buscar Paciente" not in sm, f"FAIL: {n['name']} todavia referencia Supabase"
    print(f"  verified: 0 referencias a 'Supabase - Buscar Paciente' en {patched} sub-agents")

    post_path = f"workflows/history/v6_POST_FIX_SB_REFS_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
