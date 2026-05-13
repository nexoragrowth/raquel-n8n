"""
Aplica la regla R0 (Agente funcional, NO conversacional) al TOP del system
message de los 5 sub-agents. Refuerza al LLM contra el modo conversador
y reduce el riesgo de macanas/parloteo.

Regla complementa al Banlist Validator (red de seguridad post-output) y al
Chatwoot label (silencia el bot cuando humano interviene).
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

SUB_AGENTS = {
    "Sub-Agent Confirmar",
    "Sub-Agent Cancelar",
    "Sub-Agent Agendar",
    "Sub-Agent Urgencia",
    "Sub-Agent General",
}

R0_BLOCK = """**R0. AGENTE FUNCIONAL, NO CONVERSACIONAL - REGLA ABSOLUTA**

NO sos un chatbot. Sos un agente que cumple 4 funciones especificas:

1. AGENDAR turnos (usar tools Dentalink)
2. CONFIRMAR / CANCELAR turnos post-recordatorio
3. INFO CANNED (precio consulta, horarios, direccion, alias bancario - usar LITERAL los valores del header de info)
4. ESCALAR a la secretaria (cualquier otra cosa via tool `escalar_a_secretaria`)

PROHIBIDO desviarte de estas 4 funciones. Si lo que dice el paciente NO encaja en ninguna, llama `escalar_a_secretaria` o devolve `[NO_REPLY]`. NO inventes una 5ta funcion.

NO conversas. NO opinas. NO consolas. NO sugeris. NO recomendas. NO interpretas sintomas. NO das diagnosticos. NO das instrucciones operativas ("guarda", "trae", "toma", "no comas", etc.). NO improvisas. NO haces small talk extendido.

EJEMPLOS PROHIBIDOS (cualquiera de estos = escalar):
- "No te preocupes" / "es normal" / "que macana"
- "Te recomendaria" / "te sugiero que"
- "Mira, esto suele pasar cuando..."
- Parrafos de 2+ oraciones explicando algo medico/operativo
- Responder a sintomas/dolor/sangrado SIN escalar

Saludo del paciente -> respuesta UNA linea + invitar a agendar O `[NO_REPLY]` si memoria reciente. NUNCA parrafos.

Si dudas entre responder o escalar -> ESCALAR. El costo de escalar de mas es minimo. El costo de hablar pavadas es alto.

---

"""

MARKER = "**R0. AGENTE FUNCIONAL"


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
    backup_path = f"workflows/history/v6_PRE_R0_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    modified = 0
    skipped = 0
    for n in wf["nodes"]:
        if n["name"] not in SUB_AGENTS:
            continue
        opt = n.get("parameters", {}).get("options", {})
        sm = opt.get("systemMessage", "")
        if MARKER in sm:
            print(f"  SKIP {n['name']} (R0 already present)")
            skipped += 1
            continue
        new_sm = R0_BLOCK + sm
        n["parameters"]["options"]["systemMessage"] = new_sm
        modified += 1
        print(f"  + R0 prepended to {n['name']} ({len(sm)} -> {len(new_sm)} chars)")

    if modified == 0 and skipped == 0:
        sys.exit("ABORT: no sub-agents found")
    if modified == 0:
        print("Nothing to do (all already patched). Exiting.")
        return

    if DRY_RUN:
        out = f"workflows/history/v6_R0_DRY_{ts}.json"
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
    ok = 0
    for n in wf2["nodes"]:
        if n["name"] in SUB_AGENTS:
            sm = n.get("parameters", {}).get("options", {}).get("systemMessage", "")
            if MARKER in sm:
                ok += 1
    assert ok == len(SUB_AGENTS), f"FAIL: solo {ok}/{len(SUB_AGENTS)} sub-agents tienen R0"
    print(f"  verified R0 present in {ok}/{len(SUB_AGENTS)} sub-agents")

    post_path = f"workflows/history/v6_POST_R0_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
