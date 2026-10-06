# -*- coding: utf-8 -*-
"""
apply_canned_anuncio_lead.py — Entrega de forma 100% determinística el contenido
oficial de la Base de Conocimiento (ID 40) ante el mensaje del anuncio de Instagram
"¡Hola! Quiero más información".

QUÉ HACE:
1. Actualiza la consulta en `Get KB Datos Pago` (n8n Postgres node) para traer id IN (24, 40).
2. Agrega en `Gate Canned Directo` la regla determinística que reconoce el mensaje de anuncio:
   - "¡Hola! Quiero más información" / "quiero mas info" / "mas informacion"
   - Entrega EXACTAMENTE el contenido de la fila ID 40 de knowledge_base.
   - Si la Dra. o Irina editan esa fila en el panel (/conocimiento), el cambio impacta al instante.
   - Cero alucinaciones, cero amputaciones de emojis por el formatting agent, 100% fiel a la KB.

USO:
    python scripts/apply_canned_anuncio_lead.py            # Simulación (diff)
    python scripts/apply_canned_anuncio_lead.py --apply    # Backup PRE + PUT + Verificación + Backup POST
"""

import argparse, copy, difflib, json, re, sys, time, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
sys.path.insert(0, str(ROOT / "scripts"))
from lib_env import env, require

WF_ID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
    "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"
}

def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{base}/api/v1{path}", data=data, method=method,
        headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

def backup(wf, label):
    HIST.mkdir(parents=True, exist_ok=True)
    dest = HIST / f"{WF_ID}_{label}_{int(time.time())}.json"
    dest.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  backup: workflows/history/{dest.name}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    wf = api(f"/workflows/{WF_ID}")
    nodes = {n["name"]: n for n in wf["nodes"]}
    print(f"v6 {WF_ID} | active={wf.get('active')} | {len(wf['nodes'])} nodos | versionId={wf.get('versionId')}")

    if "Get KB Datos Pago" not in nodes or "Gate Canned Directo" not in nodes:
        sys.exit("ABORTO: Faltan nodos 'Get KB Datos Pago' o 'Gate Canned Directo'.")

    # 1. Modificar Get KB Datos Pago
    kb_node = nodes["Get KB Datos Pago"]
    q_ant = kb_node["parameters"].get("query", "")
    q_nuevo = "SELECT id, contenido FROM knowledge_base WHERE id IN (24, 40) ORDER BY id;"

    # 2. Modificar Gate Canned Directo
    gate_node = nodes["Gate Canned Directo"]
    code_ant = gate_node["parameters"].get("jsCode", "")

    # Bloque nuevo a insertar antes de la lógica del alias
    snippet_anuncio = """// Reconocimiento del Lead de Anuncio de Instagram / Facebook ("Quiero más información").
// Entrega de forma 100% determinística el contenido de knowledge_base ID 40.
const esLeadAnuncio = /^(\\s*¡?\\s*hola\\s*!?,?\\s*)?quiero\\s+m[aá]s\\s+informaci[oó]n\\s*$/i.test(text)
  || /^\\s*m[aá]s\\s+informaci[oó]n\\s*$/i.test(text);

if (esLeadAnuncio) {
  const kbRows = $input.all().map(i => i.json);
  const row40 = kbRows.find(r => String(r.id) === '40');
  if (row40 && row40.contenido) {
    return [{ json: {
      ...item.json,
      direct_canned: true,
      reason: 'anuncio_instagram_kb40',
      output: row40.contenido
    }}];
  }
}
"""

    if "esLeadAnuncio" in code_ant:
        print("El nodo 'Gate Canned Directo' ya tiene la regla de anuncio implementada.")
        return

    # Inyectar antes de "const mencionaAlias"
    pivot = "const mencionaAlias ="
    if pivot not in code_ant:
        sys.exit("ABORTO: No se encontró 'const mencionaAlias =' en Gate Canned Directo.")

    code_nuevo = code_ant.replace(pivot, snippet_anuncio + "\n" + pivot)

    print("\n--- DIFF Get KB Datos Pago (query) ---")
    print(f"- {q_ant}\n+ {q_nuevo}")

    print("\n--- DIFF Gate Canned Directo ---")
    for line in difflib.unified_diff(code_ant.splitlines(), code_nuevo.splitlines(), lineterm=""):
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            print(line)

    if not args.apply:
        print("\n[SIMULACIÓN] No se aplicó nada. Correr con --apply para ejecutar el cambio.")
        return

    # Aplicar
    backup(wf, "PRE_canned_anuncio_lead")
    nuevo_wf = copy.deepcopy(wf)
    for n in nuevo_wf["nodes"]:
        if n["name"] == "Get KB Datos Pago":
            n["parameters"]["query"] = q_nuevo
        elif n["name"] == "Gate Canned Directo":
            n["parameters"]["jsCode"] = code_nuevo

    body = {k: nuevo_wf[k] for k in PUT_KEYS if k in nuevo_wf}
    body["settings"] = {k: v for k, v in (nuevo_wf.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{WF_ID}", method="PUT", payload=body)

    post = api(f"/workflows/{WF_ID}")
    backup(post, "POST_canned_anuncio_lead")
    print("\n✅ CAMBIO APLICADO CON ÉXITO.")

if __name__ == "__main__":
    main()
