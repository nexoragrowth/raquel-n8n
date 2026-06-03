"""
Fix critico: el regex anti-prompt-injection en `Pre-filtro Cierre` tiene
el patron `/soy\\s+(lucas|...)/i` que matchea pacientes reales llamados Lucas.

Caso real detectado en tests/test_conversational_flows.py R6 t2:
  IN:  "Soy Lucas Perez, DNI 30123456"
  -> Pre-filtro Cierre lo clasifica como prompt_injection -> [NO_REPLY]
  -> Paciente queda sin respuesta, Iri no se entera (no label humano).

Lucas es nombre comun en Argentina -> impacto real en pacientes legitimos.

Fix: sacar 'lucas' del patron. El test sinteti L2 "[ADMIN MODE] Soy Lucas..."
sigue cubierto por /\\[admin\\s*mode\\]/i que matchea aparte.
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

API_KEY = os.environ.get("N8N_API_KEY")
if not API_KEY:
    fallback = "C:/Users/Lucas/.claude/n8n_backups/test_100_pre_prod.py"
    if os.path.exists(fallback):
        with open(fallback, encoding="utf-8") as f:
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

OLD_PATTERN = r"/soy\s+(lucas|el\s+desarrollador|admin|administrador|developer)/i,"
NEW_PATTERN = r"/soy\s+(el\s+desarrollador|admin|administrador|developer|root)/i,"


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
    for k in (
        "id", "active", "createdAt", "updatedAt", "tags", "versionId", "triggerCount",
        "meta", "isArchived", "shared", "homeProject", "sharedWithProjects", "scopes",
        "description", "pinData", "activeVersionId", "versionCounter", "activeVersion",
    ):
        wf.pop(k, None)
    wf["settings"] = filter_settings(wf.get("settings"))
    return wf


def main():
    print("Pulling current v6...")
    _, wf = http("GET", f"/workflows/{WF_ID}")

    os.makedirs("workflows/history", exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    pre_path = f"workflows/history/v6_PRE_FIX_PREFILTRO_LUCAS_{stamp}.json"
    with open(pre_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup pre: {pre_path}")

    node = next((n for n in wf["nodes"] if n["name"] == "Pre-filtro Cierre"), None)
    if not node:
        sys.exit("ERROR: nodo 'Pre-filtro Cierre' no existe")

    code = node["parameters"].get("jsCode", "")
    if OLD_PATTERN not in code:
        # Verificar si ya estaba aplicado
        if NEW_PATTERN in code:
            print("  fix ya aplicado previamente (NEW_PATTERN presente). Nada que hacer.")
            return
        sys.exit("ERROR: no encontre el patron OLD esperado en jsCode")

    new_code = code.replace(OLD_PATTERN, NEW_PATTERN)
    if new_code == code:
        sys.exit("ERROR: replace no surtio efecto")
    node["parameters"]["jsCode"] = new_code

    # Verificacion
    assert OLD_PATTERN not in node["parameters"]["jsCode"]
    assert NEW_PATTERN in node["parameters"]["jsCode"]

    if DRY_RUN:
        dry_path = f"workflows/history/v6_FIX_PREFILTRO_LUCAS_DRY_{stamp}.json"
        with open(dry_path, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"  DRY RUN -> {dry_path}")
        print(f"  diff: '-{OLD_PATTERN}'")
        print(f"        '+{NEW_PATTERN}'")
        return

    payload = strip_meta(dict(wf))
    print("Applying PUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  PUT status: {status}")

    post_path = f"workflows/history/v6_POST_FIX_PREFILTRO_LUCAS_{stamp}.json"
    _, post_wf = http("GET", f"/workflows/{WF_ID}")
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(post_wf, f, ensure_ascii=False, indent=2)
    print(f"  backup post: {post_path}")

    # Verificacion post
    post_node = next((n for n in post_wf["nodes"] if n["name"] == "Pre-filtro Cierre"), None)
    post_code = post_node["parameters"].get("jsCode", "")
    if NEW_PATTERN in post_code and OLD_PATTERN not in post_code:
        print("  OK: fix aplicado y verificado en workflow vivo.")
    else:
        sys.exit("ERROR: verificacion post-PUT fallo")


if __name__ == "__main__":
    main()
