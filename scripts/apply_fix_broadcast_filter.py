"""
Agrega 2 regex al Pre-filtro Cierre para detectar reenvio del propio broadcast
de la clinica (Instagram od.rodriguezraquel). Sin esto, pacientes que reenvian
la promo terminan en el LLM, que escala a Iri o procesa innecesariamente.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

API_KEY = require('N8N_API_KEY')
WF_ID = require('N8N_WORKFLOW_V6_ID')
API_BASE = f"{require('N8N_BASE_URL')}/api/v1"
DRY_RUN = "--dry-run" in sys.argv

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}

# Patterns nuevos a agregar al autoresponderPatterns
NEW_PATTERNS = [
    r"/instagram\.com\/od\.rodriguezraquel/i,",
    r"/te\s+invitamos\s+a\s+seguirnos\s+en\s+instagram/i,",
]

INSERT_BEFORE = "];\nfor (const pat of autoresponderPatterns) {"
# Si no encuentra ese marker exacto, probar variantes:
INSERT_BEFORE_ALT = "];\nfor (const pat of autoresponderPatterns)"


def http(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        headers={"X-N8N-API-KEY": API_KEY, "Content-Type": "application/json", "Accept": "application/json"},
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


def strip_meta(wf):
    for k in ("id", "active", "createdAt", "updatedAt", "tags", "versionId", "triggerCount",
              "meta", "isArchived", "shared", "homeProject", "sharedWithProjects", "scopes",
              "description", "pinData", "activeVersionId", "versionCounter", "activeVersion"):
        wf.pop(k, None)
    s = wf.get("settings") or {}
    wf["settings"] = {k: v for k, v in s.items() if k in ALLOWED_SETTINGS}
    return wf


def main():
    print("Pulling current v6...")
    _, wf = http("GET", f"/workflows/{WF_ID}")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    Path("workflows/history").mkdir(parents=True, exist_ok=True)
    pre = f"workflows/history/v6_PRE_BROADCAST_FILTER_{stamp}.json"
    Path(pre).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  backup: {pre}")

    node = next((n for n in wf["nodes"] if n["name"] == "Pre-filtro Cierre"), None)
    if not node:
        sys.exit("ERROR: Pre-filtro Cierre no existe")
    code = node["parameters"]["jsCode"]

    # Check si ya estan
    if all(p in code for p in NEW_PATTERNS):
        print("  patterns ya presentes, nada que hacer.")
        return

    # Encontrar la lista autoresponderPatterns y agregar al final antes del ]
    # Marker: cierre del array
    end_marker = "];"
    autorespond_section = code.find("const autoresponderPatterns = [")
    if autorespond_section == -1:
        sys.exit("ERROR: no encuentro 'const autoresponderPatterns ='")
    end_idx = code.find(end_marker, autorespond_section)
    if end_idx == -1:
        sys.exit("ERROR: no encuentro fin del array")

    insertion = "\n  " + "\n  ".join(NEW_PATTERNS) + "\n"
    new_code = code[:end_idx] + insertion + code[end_idx:]

    # Verificar que las nuevas estan
    for p in NEW_PATTERNS:
        if p not in new_code:
            sys.exit(f"ERROR: pattern {p[:40]} no quedo insertado")

    node["parameters"]["jsCode"] = new_code

    if DRY_RUN:
        dry = f"workflows/history/v6_BROADCAST_FILTER_DRY_{stamp}.json"
        Path(dry).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  DRY -> {dry}")
        print("  Inserted patterns:")
        for p in NEW_PATTERNS: print(f"    {p}")
        return

    payload = strip_meta(dict(wf))
    print("Applying PUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  PUT: {status}")
    _, post_wf = http("GET", f"/workflows/{WF_ID}")
    post = f"workflows/history/v6_POST_BROADCAST_FILTER_{stamp}.json"
    Path(post).write_text(json.dumps(post_wf, ensure_ascii=False, indent=2), encoding="utf-8")
    # Verify
    post_node = next((n for n in post_wf["nodes"] if n["name"] == "Pre-filtro Cierre"), None)
    for p in NEW_PATTERNS:
        if p not in post_node["parameters"]["jsCode"]:
            sys.exit(f"ERROR post: pattern {p[:40]} no quedo en live")
    print("  OK: patterns aplicados y verificados.")


if __name__ == "__main__":
    main()
