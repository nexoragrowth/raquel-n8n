"""
Fallback Dentalink en Sub-Agent Confirmar/Cancelar.

ANTES: si no hay NOTA INTERNA -> escalar directo a Iri.
AHORA: si no hay NOTA INTERNA, buscar al paciente en Dentalink y filtrar
       turnos proximos. Si hay UN turno proximo -> usar ese. Si varios -> preguntar.
       Si ninguno -> escalar.

Caso real que resuelve: paciente dice "Confirmo" sin haber recibido recordatorio
del cron (porque su turno no esta en `addBusinessDays(hoy, 2)`). Hoy el bot
escala defensivamente. Con este fix, el bot infiere el turno desde Dentalink.
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

# === CONFIRMAR ===
CONF_OLD = (
    "1. Mira la memoria: deberia haber NOTA INTERNA con `cita_id` + fecha + hora del recordatorio reciente. USA esos datos, NO pidas que el paciente los repita.\n"
    "   - Si NO hay NOTA INTERNA y no podes identificar el turno -> `escalar_a_secretaria(\"Paciente confirma pero no encuentro contexto del turno\")` + canned cierre: \"Le paso a la secretaria Iri para verificar el turno.\""
)
CONF_NEW = (
    "1. IDENTIFICAR EL TURNO (en este orden):\n"
    "   1a. Si hay NOTA INTERNA reciente con `cita_id`/`id_paciente`/fecha/hora -> usar esos datos. Llamar `ver_turnos_paciente(id_paciente)` para validar que el `cita_id` siga vigente (id_estado != 1 y fecha futura). Si esta anulado o ya paso, tratar como si NO hubiera NOTA y pasar a 1b.\n"
    "   1b. Si NO hay NOTA INTERNA (o esta vieja): llamar `buscar_paciente_dentalink` con el celular del webhook. Si lo encuentra, llamar `ver_turnos_paciente(id_paciente)` y filtrar turnos en los proximos 7 dias con id_estado distinto de 1 (no anulado):\n"
    "       - EXACTAMENTE UN turno proximo -> usar ese como `cita_id`/fecha/hora y continuar a PASO 2.\n"
    "       - VARIOS turnos proximos -> responder: \"Veo que tiene varios turnos: [fecha1 hora1] y [fecha2 hora2]. ¿Cual quiere confirmar?\" y esperar respuesta del paciente. NO confirmar ninguno hasta que clarifique.\n"
    "       - NINGUN turno proximo -> `escalar_a_secretaria(\"Paciente confirma pero no tiene turno activo proximo\")` + canned: \"Le paso a la secretaria Iri para verificar el turno.\"\n"
    "   1c. Si `buscar_paciente_dentalink` no lo encuentra -> `escalar_a_secretaria(\"Confirma pero no esta en sistema\")` + canned cierre."
)

# === CANCELAR === (preservar indent de 3 espacios + linea de MULTIPLES turnos)
CANC_OLD = (
    "1. Identificar el turno a cancelar:\n"
    "   - Si hay NOTA INTERNA reciente con `cita_id` -> usar ese.\n"
    "   - Si no, llamar `ver_turnos_paciente` con `id_paciente` (de NOTA INTERNA o tras `buscar_paciente_dentalink` con phone).\n"
    "   - Si NO encontras turnos activos -> \"No encuentro un turno activo a su nombre. Le paso a la secretaria Irina para verificar.\" + `escalar_a_secretaria`.\n"
    "   - Si hay MULTIPLES turnos activos -> read-back: \"Tiene [N] turnos: [fecha1], [fecha2]. Cual quiere cancelar?\""
)
CANC_NEW = (
    "1. IDENTIFICAR EL TURNO A CANCELAR (en este orden):\n"
    "   1a. Si hay NOTA INTERNA reciente con `cita_id` -> validar con `ver_turnos_paciente` que siga vigente. Si esta anulado o ya paso, pasar a 1b.\n"
    "   1b. Si NO hay NOTA INTERNA: llamar `buscar_paciente_dentalink(celular)`. Si lo encuentra, `ver_turnos_paciente(id_paciente)` y filtrar turnos proximos (proximos 7 dias, id_estado != 1):\n"
    "       - EXACTAMENTE UN turno proximo -> usar ese.\n"
    "       - VARIOS -> responder: \"Veo varios turnos: [fecha1] y [fecha2]. ¿Cual quiere cancelar?\" y esperar.\n"
    "       - NINGUNO -> \"No encuentro un turno activo proximo. Le paso a la secretaria Iri para verificar.\" + `escalar_a_secretaria`.\n"
    "   1c. Si `buscar_paciente_dentalink` no encuentra al paciente -> escalar."
)

SUB_AGENTS_FIXES = [
    ('Sub-Agent Confirmar', CONF_OLD, CONF_NEW),
    ('Sub-Agent Cancelar', CANC_OLD, CANC_NEW),
]


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
    pre = f"workflows/history/v6_PRE_FALLBACK_DENTALINK_{stamp}.json"
    Path(pre).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  backup: {pre}")

    changes = []
    for nm, old, new in SUB_AGENTS_FIXES:
        n = next((x for x in wf['nodes'] if x['name'] == nm), None)
        if not n:
            print(f"  WARN: {nm} no existe")
            continue
        sm = n['parameters']['options']['systemMessage']
        if new in sm:
            print(f"  {nm}: ya aplicado, skip.")
            continue
        if old not in sm:
            print(f"  ERROR: en {nm} no encuentro el bloque OLD. Pre-condicion no se cumple.")
            print(f"  OLD esperado (primeros 200): {old[:200]}")
            sys.exit(1)
        new_sm = sm.replace(old, new)
        n['parameters']['options']['systemMessage'] = new_sm
        changes.append(nm)

    if not changes:
        print("  Nada que aplicar.")
        return

    print(f"\nSub-agents modificados: {changes}")

    if DRY_RUN:
        dry = f"workflows/history/v6_FALLBACK_DENTALINK_DRY_{stamp}.json"
        Path(dry).write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  DRY -> {dry}")
        return

    payload = strip_meta(dict(wf))
    print("Applying PUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  PUT: {status}")
    _, post_wf = http("GET", f"/workflows/{WF_ID}")
    post = f"workflows/history/v6_POST_FALLBACK_DENTALINK_{stamp}.json"
    Path(post).write_text(json.dumps(post_wf, ensure_ascii=False, indent=2), encoding="utf-8")
    for nm, old, new in SUB_AGENTS_FIXES:
        pn = next((x for x in post_wf['nodes'] if x['name'] == nm), None)
        if pn and new not in pn['parameters']['options']['systemMessage']:
            sys.exit(f"ERROR post: {nm} no quedo modificado")
    print("  OK: fallback Dentalink aplicado a Confirmar + Cancelar.")


if __name__ == "__main__":
    main()
