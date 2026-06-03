"""
Inyecta la knowledge base (23 docs safe) al system prompt del Sub-Agent General.

Filtros:
  - Excluye categoria=urgencia (5 docs) — tienen instrucciones operativas
  - Excluye categoria=protocolo (5 docs) — instrucciones médicas
  - Excluye 'Urgencias — política general' del bloque tratamiento

Resultado:
  - Sub-Agent General puede responder FAQ y temas frecuentes con info real
  - Reduce escalaciones innecesarias por consultas comunes
  - Mantiene escalación para urgencias / queja / casos especiales

Fuente: Supabase clinico https://dchztroesbpwxxkfywwu.supabase.co/rest/v1/knowledge_base
"""
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict

WF_ID = "O155MqHgOSaNZ9ye"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
API_KEY = os.environ.get("N8N_API_KEY")
SUPABASE_URL = "https://dchztroesbpwxxkfywwu.supabase.co"
SUPABASE_KEY = os.environ.get("SUPABASE_AUREA_KEY")
DRY_RUN = "--dry-run" in sys.argv

if not API_KEY:
    sys.exit("ERROR: N8N_API_KEY")
if not SUPABASE_KEY:
    sys.exit("ERROR: SUPABASE_AUREA_KEY (service_role del proyecto clinico)")

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow",
    "timezone", "executionOrder", "callerPolicy", "callerIds",
}

EXCLUDE_CATS = {"urgencia", "protocolo"}
EXCLUDE_TITLES = {"Urgencias — política general"}

MARKER = "= BASE DE CONOCIMIENTO (responder si la pregunta encaja"


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


def fetch_kb():
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/knowledge_base?select=id,categoria,titulo,contenido,metadata&order=categoria,titulo",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def build_block(docs):
    safe = [d for d in docs if d["categoria"] not in EXCLUDE_CATS and d["titulo"] not in EXCLUDE_TITLES]
    by_cat = defaultdict(list)
    for d in safe:
        by_cat[d["categoria"]].append(d)

    block = "\n\n= BASE DE CONOCIMIENTO (responder si la pregunta encaja, sino escalar) =\n"
    block += "Estos son los temas que SI podes responder al paciente con la info de abajo. "
    block += "Si la consulta del paciente encaja con alguno -> responder con la info concreta. "
    block += "Si NO encaja con ninguno O hay duda -> `escalar_a_secretaria`.\n"
    block += "NUNCA inventes info que no este en estos docs. Si no esta -> escalar.\n"
    for cat in sorted(by_cat.keys()):
        block += f"\n--- {cat.upper()} ---\n"
        for d in by_cat[cat]:
            content = (d["contenido"] or "").strip()
            block += f"\n**{d['titulo']}**\n{content}\n"
    return block, len(safe), len(docs) - len(safe)


def main():
    print("Fetch knowledge_base Supabase...")
    docs = fetch_kb()
    print(f"  {len(docs)} docs totales en BD")

    block, n_safe, n_excluded = build_block(docs)
    print(f"  {n_safe} safe (inyectar) + {n_excluded} excluidos (urgencia/protocolo)")
    print(f"  bloque KB: {len(block)} chars")

    print(f"\nGET workflow {WF_ID}...")
    _, wf = http("GET", f"/workflows/{WF_ID}")
    print(f"  active={wf['active']} nodes={len(wf['nodes'])}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_KB_GENERAL_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    node = next((n for n in wf["nodes"] if n["name"] == "Sub-Agent General"), None)
    if not node:
        sys.exit("ABORT: Sub-Agent General no encontrado")
    sm = node["parameters"].get("options", {}).get("systemMessage", "")
    if MARKER in sm:
        sys.exit("ABORT: KB ya inyectada (idempotent skip)")

    new_sm = sm.rstrip() + block
    node["parameters"]["options"]["systemMessage"] = new_sm
    print(f"  Sub-Agent General: {len(sm)} -> {len(new_sm)} chars (+{len(new_sm)-len(sm)})")

    if DRY_RUN:
        out = f"workflows/history/v6_KB_GENERAL_DRY_{ts}.json"
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
        if n["name"] == "Sub-Agent General":
            assert MARKER in n["parameters"]["options"]["systemMessage"]
            print(f"  verified KB present (active={wf2['active']})")
            break

    post_path = f"workflows/history/v6_POST_KB_GENERAL_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
