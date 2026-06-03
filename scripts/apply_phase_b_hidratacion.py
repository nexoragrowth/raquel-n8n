"""
Fase B: hidratacion de contexto historico desde Supabase en el v6.

Inserta 2 nodos entre 'Clear Old Memory' y 'Pre-filtro Cierre':
1. SB - Get Historial (HTTP GET): trae ultimos 30 mensajes del paciente
2. Format Historial (Code): formatea como string legible

Modifica el systemMessage de los 5 sub-agents para que incluyan referencia
al historial cuando esta disponible.

Si la query falla, el flow sigue sin historial (continueOnFail).
"""
import json
import sys
import time
import urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

API_KEY = require('N8N_API_KEY')
API_BASE = f"{require('N8N_BASE_URL')}/api/v1"
WID = require('N8N_WORKFLOW_V6_ID')
SUPABASE_URL = require('SUPABASE_URL')
CRED_SUPABASE = {"id": "Thn3jgEbbxPFD7d9", "name": "Supabase account"}

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}


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


FORMAT_CODE = """// Formatea la respuesta de Supabase como texto legible para el LLM.
const raw = $input.first().json;
// HTTP node devuelve un array de filas o un objeto si hay error
let rows = [];
if (Array.isArray(raw)) {
  rows = raw;
} else if (Array.isArray(raw.body)) {
  rows = raw.body;
} else if (raw.message) {
  // Error del HTTP, dejar historial vacio
  return [{ json: { ...$('Pre-filtro Cierre' in $('Edit Fields - Extraer Datos').params ? 'Edit Fields - Extraer Datos' : 'Edit Fields - Extraer Datos').first().json, historial: '' } }];
}

// Ordenar ASC por timestamp (mas viejo primero) para presentar al LLM cronologicamente
rows.sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));

// Limitar a ultimos 30 (ya viene ordenado del query)
const recent = rows.slice(-30);

const lines = [];
for (const r of recent) {
  const ts = (r.timestamp || '').substring(0, 16).replace('T', ' ');
  const rol = r.rol || '?';
  const msg = String(r.mensaje || '').replace(/\\s+/g, ' ').trim().substring(0, 200);
  if (!msg) continue;
  let prefix;
  if (rol === 'user') prefix = 'PACIENTE';
  else if (rol === 'assistant') prefix = 'BOT';
  else if (rol === 'human') prefix = 'SECRETARIA';
  else if (rol === 'system') prefix = 'SISTEMA';
  else prefix = rol.toUpperCase();
  lines.push(`[${ts}] ${prefix}: ${msg}`);
}

const historial = lines.length > 0 ? lines.join('\\n') : '';

// Devolver el item original con el nuevo campo `historial`
const prev = $('Edit Fields - Extraer Datos').first().json;
return [{ json: { ...prev, historial, historial_count: lines.length } }];
"""

NEW_HIDRATAR_NODES = [
    {
        "id": "sb_hidratar",
        "name": "SB - Get Historial",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [3000, 700],
        "parameters": {
            "method": "GET",
            "url": f"{SUPABASE_URL}/rest/v1/conversaciones",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "supabaseApi",
            "sendQuery": True,
            "queryParameters": {
                "parameters": [
                    {"name": "telefono", "value": "=eq.{{ $json.phone }}"},
                    {"name": "select", "value": "timestamp,rol,mensaje,fuente"},
                    {"name": "order", "value": "timestamp.desc"},
                    {"name": "limit", "value": "30"},
                ]
            },
            "options": {"response": {"response": {"responseFormat": "json"}}},
        },
        "credentials": {"supabaseApi": CRED_SUPABASE},
        "continueOnFail": True,
        "notesInFlow": True,
        "notes": "Trae ultimos 30 mensajes del paciente para hidratar contexto",
    },
    {
        "id": "format_historial",
        "name": "Format Historial",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [3220, 700],
        "parameters": {"jsCode": FORMAT_CODE},
        "continueOnFail": True,
    },
]

# Agregar al final del systemMessage de Sub-Agents una referencia al historial
HIDRATACION_SUFFIX = """

= HISTORIAL PREVIO DEL PACIENTE (Supabase, ultimos 30 mensajes) =
Si hay historial abajo, USALO como contexto. Si el paciente ya hablo de algo
(turnos, tratamiento, problemas), tenelo en cuenta. NO repitas preguntas que
ya estan respondidas en el historial.

{{ $('Format Historial').first().json.historial || 'Sin historial previo en Supabase.' }}
"""

HIDRATACION_MARKER = "= HISTORIAL PREVIO DEL PACIENTE (Supabase"

SUB_AGENTS = ['Sub-Agent Confirmar', 'Sub-Agent Cancelar', 'Sub-Agent Agendar', 'Sub-Agent Urgencia', 'Sub-Agent General']


def main():
    print("Pulling v6...")
    _, wf = http("GET", f"/workflows/{WID}")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    Path("workflows/history").mkdir(parents=True, exist_ok=True)
    Path(f"workflows/history/v6_PRE_PHASE_B_{stamp}.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  backup pre saved")

    # 1. Agregar los 2 nodos si no existen
    existing_names = {n["name"] for n in wf["nodes"]}
    for node_def in NEW_HIDRATAR_NODES:
        if node_def["name"] not in existing_names:
            wf["nodes"].append(node_def)
            print(f"  + nodo nuevo: {node_def['name']}")

    # 2. Reconectar el flow: Clear Old Memory -> SB - Get Historial -> Format Historial -> Pre-filtro Cierre
    conns = wf.get("connections", {})
    # Quitar conexion existente Clear Old Memory -> Pre-filtro Cierre
    if "Clear Old Memory" in conns:
        new_branches = []
        for branch in conns["Clear Old Memory"].get("main", []):
            new_branch = [c for c in branch if c.get("node") != "Pre-filtro Cierre"]
            new_branches.append(new_branch)
        conns["Clear Old Memory"]["main"] = new_branches
        # Agregar nueva conexion Clear Old Memory -> SB - Get Historial
        conns["Clear Old Memory"]["main"][0].append({"node": "SB - Get Historial", "type": "main", "index": 0})

    conns["SB - Get Historial"] = {"main": [[{"node": "Format Historial", "type": "main", "index": 0}]]}
    conns["Format Historial"] = {"main": [[{"node": "Pre-filtro Cierre", "type": "main", "index": 0}]]}
    wf["connections"] = conns
    print(f"  conexiones reescritas")

    # 3. Agregar al systemMessage de cada sub-agent la referencia al historial (idempotente)
    modified_agents = []
    for nm in SUB_AGENTS:
        n = next((x for x in wf["nodes"] if x["name"] == nm), None)
        if not n:
            continue
        opts = n["parameters"].get("options", {})
        sm = opts.get("systemMessage", "")
        if HIDRATACION_MARKER in sm:
            continue
        opts["systemMessage"] = sm + HIDRATACION_SUFFIX
        modified_agents.append(nm)
    print(f"  sub-agents modificados: {modified_agents}")

    payload = strip_meta(dict(wf))
    print("\nPUT Phase B...")
    if "--dry-run" in sys.argv:
        dry = f"workflows/history/v6_PHASE_B_DRY_{stamp}.json"
        Path(dry).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  DRY -> {dry}")
        return
    status, _ = http("PUT", f"/workflows/{WID}", payload)
    print(f"  status: {status}")

    _, post_wf = http("GET", f"/workflows/{WID}")
    Path(f"workflows/history/v6_POST_PHASE_B_{stamp}.json").write_text(
        json.dumps(post_wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("  backup post saved.")

    # Verify: nodos existen y conexiones
    post_names = {n["name"] for n in post_wf["nodes"]}
    if "SB - Get Historial" not in post_names or "Format Historial" not in post_names:
        sys.exit("ERROR post: nodos no quedaron")
    # Verify sub-agents tienen suffix
    for nm in SUB_AGENTS:
        n = next((x for x in post_wf["nodes"] if x["name"] == nm), None)
        if n and HIDRATACION_MARKER not in n["parameters"]["options"]["systemMessage"]:
            print(f"  WARN: {nm} no quedo con HIDRATACION_MARKER")
    print("  OK: Phase B aplicada.")


if __name__ == "__main__":
    main()
