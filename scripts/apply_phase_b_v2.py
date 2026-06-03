"""
Fase B v2: hidratacion de contexto historico desde Supabase.

Cambios vs v1 (que rompio el flow):
- Format Historial ahora SIEMPRE devuelve un item valido, aunque el HTTP falle.
- Recupera el item original de 'Edit Fields - Extraer Datos' explicitamente.
- Try/catch en todo. No referencias a $('X').params (sintaxis invalida).
- HTTP node con continueOnFail, asi flow nunca se corta por error de red.
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


# Code robusto: siempre devuelve item valido, captura errores
FORMAT_CODE = """// Format Historial: SIEMPRE devuelve el item original + campo `historial`.
// Si algo falla, historial = '' pero el flow no se corta.

let historial = '';
try {
  const httpResp = $input.first()?.json;
  let rows = [];
  if (Array.isArray(httpResp)) rows = httpResp;
  else if (httpResp && Array.isArray(httpResp.body)) rows = httpResp.body;

  if (rows.length > 0) {
    rows.sort((a, b) => (a.timestamp || '').localeCompare(b.timestamp || ''));
    const lines = [];
    for (const r of rows.slice(-30)) {
      const ts = String(r.timestamp || '').substring(0, 16).replace('T', ' ');
      const rol = r.rol || '?';
      const msg = String(r.mensaje || '').replace(/\\s+/g, ' ').trim().substring(0, 200);
      if (!msg) continue;
      let prefix;
      if (rol === 'user') prefix = 'PACIENTE';
      else if (rol === 'assistant') prefix = 'BOT';
      else if (rol === 'human') prefix = 'SECRETARIA';
      else if (rol === 'system') prefix = 'SISTEMA';
      else prefix = String(rol).toUpperCase();
      lines.push('[' + ts + '] ' + prefix + ': ' + msg);
    }
    historial = lines.join('\\n');
  }
} catch (e) {
  historial = '';
}

// CRITICO: recuperar item original del flow para no romper nodos posteriores
let origItem = {};
try {
  origItem = $('Edit Fields - Extraer Datos').first().json || {};
} catch (e) {
  origItem = {};
}

return [{ json: { ...origItem, historial } }];
"""

# Suffix solo para Sub-Agent Confirmar y Cancelar (los que mas necesitan contexto)
# Si funciona ahi, despues agregar a Agendar y General.
HIDRATACION_SUFFIX = """

= HISTORIAL PREVIO DEL PACIENTE =
Si el paciente ya hablo de algo, USA este contexto. NO repitas preguntas que estan respondidas:

{{ $('Format Historial').first().json.historial || '(sin historial previo en Supabase)' }}
"""

HIDRATACION_MARKER = "= HISTORIAL PREVIO DEL PACIENTE ="

# Empezar conservador: solo Confirmar y Cancelar
SUB_AGENTS = ['Sub-Agent Confirmar', 'Sub-Agent Cancelar']

NEW_HIDRATAR_NODES = [
    {
        "id": "sb_hidratar_v2",
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
            "options": {
                "response": {"response": {"responseFormat": "json"}},
                "timeout": 5000,
            },
        },
        "credentials": {"supabaseApi": CRED_SUPABASE},
        "continueOnFail": True,
        "onError": "continueRegularOutput",
    },
    {
        "id": "format_historial_v2",
        "name": "Format Historial",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [3220, 700],
        "parameters": {"jsCode": FORMAT_CODE},
        "continueOnFail": True,
        "onError": "continueRegularOutput",
    },
]


def main():
    print("Pulling v6...")
    _, wf = http("GET", f"/workflows/{WID}")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    Path("workflows/history").mkdir(parents=True, exist_ok=True)
    Path(f"workflows/history/v6_PRE_PHASE_B_V2_{stamp}.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  backup pre OK")

    existing_names = {n["name"] for n in wf["nodes"]}
    for nd in NEW_HIDRATAR_NODES:
        if nd["name"] not in existing_names:
            wf["nodes"].append(nd)
            print(f"  + {nd['name']}")

    # Reconectar Clear Old Memory -> SB - Get Historial -> Format Historial -> Pre-filtro Cierre
    conns = wf.get("connections", {})
    if "Clear Old Memory" in conns:
        new_branches = []
        for branch in conns["Clear Old Memory"].get("main", []):
            new_branch = [c for c in branch if c.get("node") != "Pre-filtro Cierre"]
            new_branches.append(new_branch)
        conns["Clear Old Memory"]["main"] = new_branches
        conns["Clear Old Memory"]["main"][0].append({"node": "SB - Get Historial", "type": "main", "index": 0})

    conns["SB - Get Historial"] = {"main": [[{"node": "Format Historial", "type": "main", "index": 0}]]}
    conns["Format Historial"] = {"main": [[{"node": "Pre-filtro Cierre", "type": "main", "index": 0}]]}
    wf["connections"] = conns

    # Modificar systemMessage solo de Confirmar y Cancelar (conservador)
    modified = []
    for nm in SUB_AGENTS:
        n = next((x for x in wf["nodes"] if x["name"] == nm), None)
        if not n: continue
        opts = n["parameters"].get("options", {})
        sm = opts.get("systemMessage", "")
        if HIDRATACION_MARKER in sm: continue
        opts["systemMessage"] = sm + HIDRATACION_SUFFIX
        modified.append(nm)
    print(f"  modified: {modified}")

    payload = strip_meta(dict(wf))
    if "--dry-run" in sys.argv:
        dry = f"workflows/history/v6_PHASE_B_V2_DRY_{stamp}.json"
        Path(dry).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  DRY -> {dry}")
        return

    print("PUT Phase B v2...")
    status, _ = http("PUT", f"/workflows/{WID}", payload)
    print(f"  status: {status}")


if __name__ == "__main__":
    main()
