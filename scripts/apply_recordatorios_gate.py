# -*- coding: utf-8 -*-
"""
apply_recordatorios_gate.py — agrega el GATE de suspensiones al workflow de
Recordatorios (7RqTApkvVavRmq3R), sin tocar nada del camino de envío.

QUÉ HACE (2 nodos nuevos + rewire de 1 conexión):
    Trigger "Diario 9AM Arg"
        -> [NUEVO] Postgres "Gate - Leer config"   (1 SELECT/corrida a recordatorios_config)
        -> [NUEVO] IF       "Gate - ¿Suspendido hoy?"
              · true  -> [NUEVO] NoOp "Suspendido hoy" (fin, no envía)
              · false -> "Fecha Mañana"  (sigue el flujo NORMAL de siempre)

DISEÑO ESCALABLE: cero timers nuevos. La suspensión es DATO leído una vez por la
corrida diaria que YA ocurre. Suspender un día = fecha en dias_suspendidos; al día
siguiente ya no está -> corre solo (auto-resume).

FAIL-OPEN (no regresa confiabilidad): la query devuelve `suspender` (true SOLO si
está explícitamente suspendido). Fila faltante -> bool_or vacío -> NULL -> coalesce
false -> corre. El nodo PG va con onError=continueRegularOutput: si la base no
responde, el item no trae `suspender` -> el IF (typeValidation loose) lo toma falsy
-> corre igual. Nunca se cortan los recordatorios por un problema de config/red.

USO:
    # Preview (NO toca n8n): genera el POST propuesto + resume el diff.
    python scripts/apply_recordatorios_gate.py --base workflows/history/Recordatorio_POST_a1_20260718_182340.json

    # Aplicar de verdad (GET live -> backup PRE -> PUT -> verifica). Requiere:
    #   N8N_API_BASE, N8N_API_KEY  (los del panel .env.local)
    python scripts/apply_recordatorios_gate.py --apply

Regla del proyecto: NUNCA --apply sin OK explícito de Lucas + backup previo.
"""
import argparse
import json
import os
import sys
import urllib.request
import uuid

sys.stdout.reconfigure(encoding="utf-8")

WF_ID = os.environ.get("N8N_WF_RECORDATORIOS", "7RqTApkvVavRmq3R")
BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""

PG_CRED = {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}
TRIGGER_NAME = "Diario 9AM Arg (cron 0 14 UTC)"
DOWNSTREAM = "Fecha Mañana"  # a donde iba el trigger; ahora cuelga del IF (rama false)

GATE_SQL = (
    "SELECT COALESCE(bool_or(\n"
    "    (NOT c.activo)\n"
    "    OR ((now() AT TIME ZONE 'America/Argentina/Jujuy')::date = ANY(c.dias_suspendidos))\n"
    "    OR (c.suspender_desde IS NOT NULL\n"
    "        AND (now() AT TIME ZONE 'America/Argentina/Jujuy')::date\n"
    "            BETWEEN c.suspender_desde AND c.suspender_hasta)\n"
    "  ), false) AS suspender\n"
    "FROM public.recordatorios_config c\n"
    "WHERE c.id = 1;"
)

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": KEY, "accept": "application/json",
                 "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def build_nodes():
    pg = {
        "id": str(uuid.uuid4()),
        "name": "Gate - Leer config",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [208, 192],
        "parameters": {"operation": "executeQuery", "query": GATE_SQL, "options": {}},
        "credentials": {"postgres": PG_CRED},
        "onError": "continueRegularOutput",  # PG caído -> no aborta -> fail-open
    }
    iff = {
        "id": str(uuid.uuid4()),
        "name": "Gate - ¿Suspendido hoy?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [432, 192],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [{
                    "id": "gate-suspender",
                    "leftValue": "={{ $json.suspender }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }],
                "combinator": "and",
            },
            "options": {},
        },
    }
    noop = {
        "id": str(uuid.uuid4()),
        "name": "Suspendido hoy",
        "type": "n8n-nodes-base.noOp",
        "typeVersion": 1,
        "position": [656, 320],
        "parameters": {},
    }
    return pg, iff, noop


def patch(wf):
    names = {n["name"] for n in wf["nodes"]}
    if "Gate - Leer config" in names:
        print("!! El gate ya está aplicado (nodo 'Gate - Leer config' existe). Nada que hacer.")
        return None
    if TRIGGER_NAME not in names or DOWNSTREAM not in names:
        print(f"!! No encuentro '{TRIGGER_NAME}' o '{DOWNSTREAM}'. Aborto.")
        return None

    pg, iff, noop = build_nodes()
    wf["nodes"].extend([pg, iff, noop])

    conns = wf["connections"]
    # trigger -> Gate PG  (antes: trigger -> Fecha Mañana)
    conns[TRIGGER_NAME] = {"main": [[{"node": "Gate - Leer config", "type": "main", "index": 0}]]}
    # Gate PG -> Gate IF
    conns["Gate - Leer config"] = {"main": [[{"node": "Gate - ¿Suspendido hoy?", "type": "main", "index": 0}]]}
    # Gate IF: true -> Suspendido hoy | false -> Fecha Mañana (flujo normal)
    conns["Gate - ¿Suspendido hoy?"] = {"main": [
        [{"node": "Suspendido hoy", "type": "main", "index": 0}],
        [{"node": DOWNSTREAM, "type": "main", "index": 0}],
    ]}
    return wf


def clean_settings(wf):
    return {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED_SETTINGS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="hace el PUT real (requiere OK de Lucas)")
    ap.add_argument("--base", help="archivo backup a parchear en modo preview")
    args = ap.parse_args()

    if args.apply:
        if not (BASE and KEY):
            print("!! Faltan N8N_API_BASE / N8N_API_KEY en el entorno."); sys.exit(1)
        print(f"GET live workflow {WF_ID} ...")
        wf = api("GET", f"/workflows/{WF_ID}")
        pre = f"workflows/history/Recordatorio_PRE_gate_LIVE.json"
        json.dump(wf, open(pre, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"backup PRE -> {pre}")
    else:
        base = args.base or "workflows/history/Recordatorio_POST_a1_20260718_182340.json"
        print(f"[PREVIEW] parcheando sobre {base} (NO toca n8n)")
        wf = json.load(open(base, encoding="utf-8"))

    n_before = len(wf["nodes"])
    wf = patch(wf)
    if wf is None:
        sys.exit(0)

    post = "workflows/history/Recordatorio_POST_gate_PROPUESTA.json"
    json.dump(wf, open(post, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n--- DIFF ---")
    print(f"nodos: {n_before} -> {len(wf['nodes'])} (+3: Gate PG, Gate IF, NoOp Suspendido hoy)")
    print(f"conexión: '{TRIGGER_NAME}' -> ahora entra al gate; rama false del IF -> '{DOWNSTREAM}' (flujo normal intacto)")
    print(f"POST propuesto -> {post}")

    if not args.apply:
        print("\n[PREVIEW] listo. Revisá el POST. Para aplicar: --apply (con OK).")
        return

    body = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": clean_settings(wf),
        "staticData": wf.get("staticData"),
    }
    print("\nPUT ...")
    api("PUT", f"/workflows/{WF_ID}", body)
    live = api("GET", f"/workflows/{WF_ID}")
    ok = any(n["name"] == "Gate - Leer config" for n in live["nodes"])
    print("verificación post-PUT:", "OK ✅ gate presente" if ok else "!! NO se ve el gate")


if __name__ == "__main__":
    main()
