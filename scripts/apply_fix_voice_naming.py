"""
Fix de voz/naming en outputs canned. Pacientes nuevos no saben quien es "Iri"
sin contexto. "imputar" es jerga contable. "la doctora" sola es ambigua.

Reemplazos solo en system messages de sub-agents.
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

# Reemplazos textuales en system messages. (old, new)
# Solo en frases que son OUTPUTS canned (lo que el bot le dice al paciente).
# NO en reglas internas tipo "deriva a Iri si pasa X".
REPLACEMENTS = [
    # imputar -> registrar (jerga contable)
    ('Le paso a Iri para que verifique e impute.',
     'Le paso a la secretaria Iri para que verifique el comprobante y lo registre.'),
    # "Le paso a Iri" canned solo (en contextos de respuesta al paciente)
    ('Le paso a Iri para verificar el turno.',
     'Le paso a la secretaria Iri para verificar el turno.'),
    ('"Le paso a Iri para verificar el turno."',
     '"Le paso a la secretaria Iri para verificar el turno."'),
    # "Para confirmar agenda de la doctora le paso a Iri" -> con rol
    ('Para confirmar agenda de la doctora le paso a Iri.',
     'Para confirmar agenda de la doctora le paso a la secretaria Iri.'),
    # la doctora -> la Dra. Raquel cuando es primera mencion en canned
    ('Eso lo evalua la doctora en consulta.',
     'Eso lo evalua la Dra. Raquel en consulta.'),
    # canned de primera consulta - escalacion
    ('"Eso lo evalua la doctora en consulta. Le paso a la secretaria Irina para coordinarle una primera visita."',
     '"Eso lo evalua la Dra. Raquel en consulta. Le paso a la secretaria Iri para coordinarle una primera visita."'),
]

SUB_AGENTS = ['Sub-Agent Confirmar', 'Sub-Agent Cancelar', 'Sub-Agent Agendar', 'Sub-Agent Urgencia', 'Sub-Agent General']


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
    pre = f"workflows/history/v6_PRE_VOICE_NAMING_{stamp}.json"
    Path(pre).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  backup: {pre}")

    total_replacements = 0
    per_agent = {}
    for nm in SUB_AGENTS:
        n = next((x for x in wf['nodes'] if x['name'] == nm), None)
        if not n:
            continue
        opts = n['parameters'].get('options', {})
        sm = opts.get('systemMessage', '')
        if not sm:
            continue
        new_sm = sm
        cnt = 0
        for old, new in REPLACEMENTS:
            occurrences = new_sm.count(old)
            if occurrences:
                new_sm = new_sm.replace(old, new)
                cnt += occurrences
        if cnt:
            opts['systemMessage'] = new_sm
            per_agent[nm] = cnt
            total_replacements += cnt

    if not total_replacements:
        print("  Nada que cambiar (ya estaba todo aplicado o patterns no matchean).")
        return

    print(f"\nReemplazos por sub-agent: {per_agent}")
    print(f"Total: {total_replacements}")

    if DRY_RUN:
        dry = f"workflows/history/v6_VOICE_NAMING_DRY_{stamp}.json"
        Path(dry).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  DRY -> {dry}")
        return

    payload = strip_meta(dict(wf))
    print("Applying PUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  PUT: {status}")
    _, post_wf = http("GET", f"/workflows/{WF_ID}")
    post = f"workflows/history/v6_POST_VOICE_NAMING_{stamp}.json"
    Path(post).write_text(json.dumps(post_wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  OK: cambios aplicados.")


if __name__ == "__main__":
    main()
