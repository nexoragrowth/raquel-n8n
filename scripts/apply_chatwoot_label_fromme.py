"""
Reemplaza el silence-flag Redis por aplicar label "humano" en Chatwoot
cuando llega fromMe=true desde WA Web/Mobile.

Resultado: el v6 detecta el label humano via "Verificar Label Humano"
(que ya existe en el flow main, post-buffer). Single source of truth.

Cambios:
  - Remover nodos: "Redis SET silence", "Redis GET silence", "Silenced?"
  - Restore conexion: Es fromMe? FALSE -> Filtrar duplicados y basura
  - Quitar edge: Postgres - Save fromMe -> Redis SET silence
  - Crear nodos: "CW Search Contact", "CW Extract Conv", "CW Set Label humano"
  - Conexion nueva: Postgres - Save fromMe -> CW Search Contact -> CW Extract Conv -> CW Set Label humano

continueOnFail=True en los HTTP por si Chatwoot esta caido o el paciente
no tiene conversation aun.
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

CW_TOKEN = os.environ.get("CHATWOOT_TOKEN")
if not CW_TOKEN:
    sys.exit("set CHATWOOT_TOKEN env var")
CW_BASE = "https://chat.raquelrodriguez.com.ar"

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
    backup_path = f"workflows/history/v6_PRE_CW_LABEL_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    # === FASE A: remover nodos Redis silence ===
    REMOVE_NAMES = {"Redis SET silence", "Redis GET silence", "Silenced?"}
    wf["nodes"] = [n for n in wf["nodes"] if n["name"] not in REMOVE_NAMES]

    conns = wf["connections"]
    # Quitar entries de los nodos removidos como SOURCE
    for nm in list(conns.keys()):
        if nm in REMOVE_NAMES:
            del conns[nm]
    # Quitar referencias a esos nodos como TARGET
    def clean_targets(d):
        for src, c in d.items():
            for bt, branches in c.items():
                for i, b in enumerate(branches or []):
                    if b:
                        c[bt][i] = [e for e in b if e.get("node") not in REMOVE_NAMES]
    clean_targets(conns)

    # Restore: Es fromMe? FALSE -> Filtrar duplicados y basura
    es_fromme = conns.get("Es fromMe?", {}).get("main", [])
    if len(es_fromme) >= 2:
        already = any(e.get("node") == "Filtrar duplicados y basura" for e in es_fromme[1])
        if not already:
            conns["Es fromMe?"]["main"][1].append(
                {"node": "Filtrar duplicados y basura", "type": "main", "index": 0}
            )

    # === FASE B: crear nodos Chatwoot ===
    existing = {n["name"] for n in wf["nodes"]}
    NEW = ["CW Search Contact", "CW Extract Conv", "CW Set Label humano"]
    for nm in NEW:
        if nm in existing:
            sys.exit(f"ABORT: nodo {nm!r} ya existe")

    new_nodes = [
        {
            "parameters": {
                "url": "=" + CW_BASE + "/api/v1/accounts/1/contacts/search",
                "sendQuery": True,
                "queryParameters": {
                    "parameters": [
                        {
                            "name": "q",
                            "value": "={{ $('Edit Fields - Extraer Datos').first().json.phone }}",
                        },
                        {"name": "include", "value": "contact_inboxes"},
                    ]
                },
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "api_access_token", "value": CW_TOKEN},
                    ]
                },
                "options": {},
            },
            "id": "cw-search-001",
            "name": "CW Search Contact",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [4680, 610],
            "onError": "continueRegularOutput",
        },
        {
            "parameters": {
                "jsCode": (
                    "// Extrae conversationId del primer contact que matchee el phone\n"
                    "const data = $input.first().json || {};\n"
                    "if (data.error || data.statusCode >= 400) return [];\n"
                    "const payload = data.payload || [];\n"
                    "if (!payload.length) return [];\n"
                    "const contact = payload[0];\n"
                    "const contactId = contact.id;\n"
                    "// Necesitamos las conversations de ese contact\n"
                    "return [{ json: { contactId, accountId: 1 } }];"
                )
            },
            "id": "cw-extract-001",
            "name": "CW Extract Conv",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [4970, 610],
        },
        {
            "parameters": {
                "url": "=" + CW_BASE + "/api/v1/accounts/{{ $json.accountId }}/contacts/{{ $json.contactId }}/conversations",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "api_access_token", "value": CW_TOKEN},
                    ]
                },
                "options": {},
            },
            "id": "cw-getconv-001",
            "name": "CW Get Conversations",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [5260, 610],
            "onError": "continueRegularOutput",
        },
        {
            "parameters": {
                "jsCode": (
                    "// Tomar la primer conversation activa\n"
                    "const data = $input.first().json || {};\n"
                    "if (data.error || data.statusCode >= 400) return [];\n"
                    "const convs = data.payload || [];\n"
                    "if (!convs.length) return [];\n"
                    "// Preferir la conversation 'open', sino la primera\n"
                    "const open = convs.find(c => c.status === 'open');\n"
                    "const conv = open || convs[0];\n"
                    "return [{ json: { accountId: 1, conversationId: conv.id, action: 'humano' } }];"
                )
            },
            "id": "cw-pickconv-001",
            "name": "CW Pick Conv",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [5550, 610],
        },
        {
            "parameters": {
                "method": "POST",
                "url": "=" + CW_BASE + "/api/v1/accounts/{{ $json.accountId }}/conversations/{{ $json.conversationId }}/labels",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "api_access_token", "value": CW_TOKEN},
                        {"name": "Content-Type", "value": "application/json"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '={"labels":["humano"]}',
                "options": {},
            },
            "id": "cw-label-001",
            "name": "CW Set Label humano",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [5840, 610],
            "onError": "continueRegularOutput",
        },
    ]
    wf["nodes"].extend(new_nodes)
    NEW = ["CW Search Contact", "CW Extract Conv", "CW Get Conversations", "CW Pick Conv", "CW Set Label humano"]

    # === FASE C: conexiones nuevas ===
    # Postgres - Save fromMe -> CW Search Contact (asegurar la edge)
    psm = conns.setdefault("Postgres - Save fromMe", {}).setdefault("main", [[]])
    if not psm:
        conns["Postgres - Save fromMe"]["main"] = [[]]
    if not conns["Postgres - Save fromMe"]["main"][0]:
        conns["Postgres - Save fromMe"]["main"][0] = []
    # Quitar cualquier edge previa (la de Redis SET silence ya quedó limpia)
    conns["Postgres - Save fromMe"]["main"][0] = [
        e for e in conns["Postgres - Save fromMe"]["main"][0]
        if e.get("node") not in REMOVE_NAMES
    ]
    conns["Postgres - Save fromMe"]["main"][0].append(
        {"node": "CW Search Contact", "type": "main", "index": 0}
    )
    # Chain
    conns["CW Search Contact"] = {"main": [[{"node": "CW Extract Conv", "type": "main", "index": 0}]]}
    conns["CW Extract Conv"] = {"main": [[{"node": "CW Get Conversations", "type": "main", "index": 0}]]}
    conns["CW Get Conversations"] = {"main": [[{"node": "CW Pick Conv", "type": "main", "index": 0}]]}
    conns["CW Pick Conv"] = {"main": [[{"node": "CW Set Label humano", "type": "main", "index": 0}]]}

    if DRY_RUN:
        out = f"workflows/history/v6_CW_LABEL_DRY_{ts}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"DRY RUN -> {out}")
        print(f"  total nodes after patch: {len(wf['nodes'])}")
        # sanity: Es fromMe? FALSE pointing donde?
        for e in conns.get("Es fromMe?", {}).get("main", [[], []])[1]:
            print(f"  Es fromMe? FALSE -> {e.get('node')}")
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
    for r in REMOVE_NAMES:
        assert r not in names, f"FAIL: {r} sigue presente"
    for n_ in NEW:
        assert n_ in names, f"FAIL: {n_} no se creo"
    print(f"  removed {sorted(REMOVE_NAMES)}")
    print(f"  added   {NEW}")

    post_path = f"workflows/history/v6_POST_CW_LABEL_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
