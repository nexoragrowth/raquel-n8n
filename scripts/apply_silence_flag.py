"""
Aplica silence-flag Redis al v6.

Bug: cuando la doctora/Iri habla desde WA Web o WA Mobile (no Chatwoot),
fromMe=true se persiste en memoria pero el siguiente mensaje del paciente
(fromMe=false) sigue al flow main. El bot puede responder igual.

Fix: setear `silence:<phone>=1 EX 7200` cuando llega fromMe=true. En la rama
fromMe=false, chequear el flag antes del flow main; si existe, NoOp.

Cambios:
  + Nodo "Redis SET silence"  (despues de Postgres - Save fromMe)
  + Nodo "Redis GET silence"  (Es fromMe? FALSE -> aqui en vez de Filtrar)
  + Nodo "Silenced?"          (IF)
  Connections:
    Postgres - Save fromMe -> Redis SET silence
    Es fromMe? FALSE: re-route a Redis GET silence (antes iba a Filtrar)
    Redis GET silence -> Silenced?
    Silenced? TRUE  -> Humano Atendiendo (no hacer nada)  [reuso]
    Silenced? FALSE -> Filtrar duplicados y basura
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

REDIS_CRED = {"redis": {"id": "kdtSKwGbN1xAZeUh", "name": "Redis account"}}

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow",
    "timezone", "executionOrder", "callerPolicy", "callerIds",
}


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
    status, wf = http("GET", f"/workflows/{WF_ID}")
    print(f"  active={wf['active']} nodes={len(wf['nodes'])}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_SILENCE_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    # Idempotency: si ya existen, abortar
    existing_names = {n["name"] for n in wf["nodes"]}
    for new_name in ["Redis SET silence", "Redis GET silence", "Silenced?"]:
        if new_name in existing_names:
            sys.exit(f"ABORT: node {new_name!r} ya existe (parche ya aplicado)")

    # Crear 3 nodos nuevos
    new_nodes = [
        {
            "parameters": {
                "operation": "set",
                "key": "=silence:{{ $('Edit Fields - Extraer Datos').first().json.phone }}",
                "value": "1",
                "keyTtl": 7200,
                "expire": True,
                "ttl": 7200,
            },
            "id": "silence-set-001",
            "name": "Redis SET silence",
            "type": "n8n-nodes-base.redis",
            "typeVersion": 1,
            "position": [4680, 610],
            "credentials": REDIS_CRED,
        },
        {
            "parameters": {
                "operation": "get",
                "propertyName": "silence_flag",
                "key": "=silence:{{ $('Edit Fields - Extraer Datos').first().json.phone }}",
                "keyType": "automatic",
            },
            "id": "silence-get-001",
            "name": "Redis GET silence",
            "type": "n8n-nodes-base.redis",
            "typeVersion": 1,
            "position": [4100, 380],
            "credentials": REDIS_CRED,
        },
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "typeValidation": "loose",
                        "version": 2,
                    },
                    "conditions": [
                        {
                            "id": "silence-check",
                            "leftValue": "={{ $json.silence_flag }}",
                            "rightValue": "",
                            "operator": {
                                "type": "string",
                                "operation": "notEmpty",
                                "singleValue": True,
                            },
                        }
                    ],
                    "combinator": "and",
                },
                "options": {},
            },
            "id": "silence-if-001",
            "name": "Silenced?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [4390, 380],
        },
    ]
    wf["nodes"].extend(new_nodes)

    # Modificar conexiones
    conns = wf["connections"]

    # 1. "Postgres - Save fromMe" -> "Redis SET silence" (nueva)
    conns.setdefault("Postgres - Save fromMe", {}).setdefault("main", [[]])
    if not conns["Postgres - Save fromMe"]["main"]:
        conns["Postgres - Save fromMe"]["main"] = [[]]
    if not conns["Postgres - Save fromMe"]["main"][0]:
        conns["Postgres - Save fromMe"]["main"][0] = []
    conns["Postgres - Save fromMe"]["main"][0].append({
        "node": "Redis SET silence", "type": "main", "index": 0
    })

    # 2. "Es fromMe?" FALSE: re-route a Redis GET silence
    # Estructura: branches[0] = TRUE, branches[1] = FALSE
    es_fromme = conns.get("Es fromMe?", {}).get("main", [])
    if len(es_fromme) < 2:
        sys.exit("ABORT: Es fromMe? no tiene 2 branches")
    # Verificar que FALSE actualmente apunta a "Filtrar duplicados y basura"
    false_branch = es_fromme[1]
    found_filtrar = any(e.get("node") == "Filtrar duplicados y basura" for e in false_branch)
    if not found_filtrar:
        sys.exit(f"ABORT: Es fromMe? FALSE no apunta a 'Filtrar duplicados y basura'. Actual: {false_branch}")
    # Reemplazar
    new_false_branch = [
        {"node": "Redis GET silence", "type": "main", "index": 0}
        if e.get("node") == "Filtrar duplicados y basura" else e
        for e in false_branch
    ]
    conns["Es fromMe?"]["main"][1] = new_false_branch

    # 3. "Redis GET silence" -> "Silenced?"
    conns["Redis GET silence"] = {
        "main": [[{"node": "Silenced?", "type": "main", "index": 0}]]
    }

    # 4. "Silenced?" TRUE -> "Humano Atendiendo (no hacer nada)"  [reuso]
    #    "Silenced?" FALSE -> "Filtrar duplicados y basura"
    conns["Silenced?"] = {
        "main": [
            [{"node": "Humano Atendiendo (no hacer nada)", "type": "main", "index": 0}],  # TRUE
            [{"node": "Filtrar duplicados y basura", "type": "main", "index": 0}],         # FALSE
        ]
    }

    if DRY_RUN:
        out = f"workflows/history/v6_SILENCE_DRY_{ts}.json"
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

    status2, wf2 = http("GET", f"/workflows/{WF_ID}")
    names = {n["name"] for n in wf2["nodes"]}
    for new_name in ["Redis SET silence", "Redis GET silence", "Silenced?"]:
        assert new_name in names, f"FAIL: {new_name} not in workflow after PUT"
        print(f"  verified {new_name!r} present")

    post_path = f"workflows/history/v6_POST_SILENCE_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
