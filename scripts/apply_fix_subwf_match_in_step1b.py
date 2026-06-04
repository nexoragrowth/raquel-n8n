"""Mover el match por contexto a Step 1b (antes de ver_turnos).
Si multiple_fichas + match único en chat history => paciente = ficha matched.
"""
import os, sys, json, requests, time
from dotenv import load_dotenv
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

wf = requests.get(f"{BASE}/api/v1/workflows/5cAWJxiWJ50hxEq3", headers=H, timeout=60).json()

# === Step 1b: agregar matcheo si multiple ===
s1b = next(x for x in wf["nodes"] if x["name"] == "Step 1b: Procesar resultado")
js1b = s1b["parameters"]["jsCode"]

OLD_S1B = "if (data.length > 0) {\n  return [{ json: {\n    ok: true,\n    step: 'paciente_encontrado',\n    paciente: data[0],\n    multiple_fichas: data.length > 1,\n    pacientes_all: data,\n    variant_used: 'celular_completo',\n    trigger\n  }}];\n}"

NEW_S1B = """if (data.length > 0) {
  // FIX 2026-06-04: si multiple_fichas, intentar match por contexto del chat history
  let pacienteResuelto = data[0];
  let resolvedBy = null;
  if (data.length > 1) {
    try {
      const chMem = $('Step 0a: Read Chat Memory').all() || [];
      const isMultiList = (txt) => /tengo\\s+registrad[ao]s?\\s+a\\b|con\\s+este\\s+n[u\\u00fa]mero\\s+(figura|tengo|tiene)/i.test(txt);
      const chatHistoryText = chMem.map(it => {
        const m = it.json && it.json.message ? it.json.message : {};
        const c = (m.content || '').toString();
        if (isMultiList(c)) return '';
        return c;
      }).filter(Boolean).join('\\n').toLowerCase();
      const msgPaciente = (trigger && trigger.text || '').toLowerCase();
      const searchPool = msgPaciente + '\\n' + chatHistoryText;
      const STOP_TOKENS = new Set(['test','prueba','paciente','el','la','los','las','de','del','dr','dra','sr','sra']);
      const tokenizar = (s) => (s || '').toLowerCase()
        .replace(/[^a-z\\u00e1\\u00e9\\u00ed\\u00f3\\u00fa\\u00f10-9\\s]/gi, ' ')
        .split(/\\s+/)
        .filter(t => t.length >= 3 && !STOP_TOKENS.has(t));
      const matched = data.filter(p => {
        const tokens = [...tokenizar(p.nombre || ''), ...tokenizar(p.apellidos || p.apellido || '')];
        return tokens.length > 0 && tokens.some(t => searchPool.includes(t));
      });
      if (matched.length === 1) {
        pacienteResuelto = matched[0];
        resolvedBy = 'context_match';
      }
    } catch(e) { /* fallback a data[0] */ }
  }
  return [{ json: {
    ok: true,
    step: 'paciente_encontrado',
    paciente: pacienteResuelto,
    multiple_fichas: data.length > 1 && !resolvedBy,  // si resolved, ya no es ambiguo
    multi_fichas_resolved_by: resolvedBy,
    pacientes_all: data,
    variant_used: 'celular_completo',
    trigger
  }}];
}"""

if OLD_S1B not in js1b:
    print("!! Step 1b anchor no found"); sys.exit(2)
s1b["parameters"]["jsCode"] = js1b.replace(OLD_S1B, NEW_S1B)

allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution","executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": settings, "staticData": wf.get("staticData")}
r = requests.put(f"{BASE}/api/v1/workflows/5cAWJxiWJ50hxEq3", headers=H, json=body, timeout=40)
print(f"PUT {r.status_code}")
