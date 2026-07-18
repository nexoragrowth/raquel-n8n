"""URGENTE - Sub-WF Cancelar: cuando hay multiples fichas con el mismo celular
(familia compartiendo phone), el bot escalaba SIN intentar identificar al paciente
por contexto.

Fix:
1. Step 1b devuelve `pacientes_all` (array completo de fichas) en lugar de solo data[0].
2. Step 4 nuevo comportamiento ante multiple_fichas:
   - Buscar match por nombre en (a) texto actual del paciente o (b) chat_history reciente
     (busca "para X" / "es para X" / "para mi hijo X" / etc.).
   - Si encuentra match con una ficha -> usar esa, no preguntar.
   - Si no encuentra -> PREGUNTAR listando nombres+apellidos, NO escalar.

Modo: --apply / --dry
"""
from __future__ import annotations
import argparse, json, os, sys, io
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
BASE = os.environ["N8N_BASE_URL"].rstrip("/"); KEY = os.environ["N8N_API_KEY"]
WF_ID = "5cAWJxiWJ50hxEq3"; H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

# Step 1b - cambio: incluir pacientes_all
OLD_STEP_1B = """if (data.length > 0) {
  return [{ json: {
    ok: true,
    step: 'paciente_encontrado',
    paciente: data[0],
    multiple_fichas: data.length > 1,
    variant_used: 'celular_completo',
    trigger
  }}];
}"""

NEW_STEP_1B = """if (data.length > 0) {
  return [{ json: {
    ok: true,
    step: 'paciente_encontrado',
    paciente: data[0],
    multiple_fichas: data.length > 1,
    pacientes_all: data,
    variant_used: 'celular_completo',
    trigger
  }}];
}"""

# Step 4 - cambio: reemplazar bloque escalar por logica de match-o-preguntar
OLD_STEP_4 = """// === Fix A: celular compartido por varias fichas (familia) -> NO cancelar a ciegas, escalar ===
const multipleFichas = $('Step 1b: Procesar resultado').first().json.multiple_fichas === true;
if (multipleFichas) {
  return [{ json: {
    ...prev,
    decision: {
      siguiente_paso: 'escalar',
      razon: 'multiple_fichas_mismo_celular',
      canned: 'Con este numero figuran varias personas registradas. Le paso a la secretaria para coordinar la cancelacion de forma segura. En un momento le responde.'
    }
  }}];
}"""

NEW_STEP_4 = """// === Fix B 2026-06-03: celular compartido por varias fichas (familia) -> PREGUNTAR (o usar contexto), NO escalar ===
const step1b = $('Step 1b: Procesar resultado').first().json;
const multipleFichas = step1b.multiple_fichas === true;
if (multipleFichas) {
  const pacientesAll = step1b.pacientes_all || [];
  // Construir texto a buscar: mensaje actual del paciente + chat_history reciente
  const msgPaciente = (prev.trigger && prev.trigger.text) || '';
  let chatHistoryText = '';
  try {
    const chMem = $('Step 0a: Read Chat Memory').all() || [];
    chatHistoryText = chMem.map(it => {
      const m = it.json && it.json.message ? it.json.message : {};
      return (m.content || '').toString();
    }).join('\\n').toLowerCase();
  } catch(e) { chatHistoryText = ''; }
  const searchPool = (msgPaciente + '\\n' + chatHistoryText).toLowerCase();

  // Intentar matchear UNA ficha por nombre/apellido
  const matched = pacientesAll.filter(p => {
    const nombre = (p.nombre || '').toLowerCase().trim();
    const apellido = (p.apellido || '').toLowerCase().trim();
    if (!nombre && !apellido) return false;
    // Match si nombre Y apellido aparecen, o si nombre+apellido juntos en searchPool
    const full = (nombre + ' ' + apellido).trim();
    if (nombre && searchPool.includes(nombre)) return true;
    if (full && searchPool.includes(full)) return true;
    return false;
  });

  if (matched.length === 1) {
    // Match exacto unico -> usar esa ficha y continuar
    return [{ json: {
      ...prev,
      paciente_resuelto: matched[0],
      paciente: matched[0],
      multi_fichas_resolved_by: 'context_match',
      decision: null  // dejar que el resto del Step 4 procese normal
    }}];
  }

  // No hay match unico -> preguntar listando los nombres
  const lista = pacientesAll.slice(0, 6).map(p => {
    const n = (p.nombre || '').trim();
    const a = (p.apellido || '').trim();
    return (n + ' ' + a).trim() || '(sin nombre)';
  });
  return [{ json: {
    ...prev,
    decision: {
      siguiente_paso: 'preguntar_nombre_paciente',
      razon: 'multiple_fichas_pedir_clarificacion',
      canned: 'Con este numero tengo registradas a ' + lista.slice(0,-1).join(', ') + (lista.length > 1 ? ' y ' + lista[lista.length-1] : lista[0]) + '. ¿Para quién es la cancelación? Pasame nombre y apellido.'
    }
  }}];
}"""


def get_wf():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60); r.raise_for_status(); return r.json()


def put_wf(wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:500], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()

    nodes_by_name = {n["name"]: n for n in wf["nodes"]}
    step1b = nodes_by_name.get("Step 1b: Procesar resultado")
    step4 = nodes_by_name.get("Step 4: Identificar Turno + Decision")
    if not step1b or not step4:
        print("!! nodos no encontrados"); sys.exit(2)

    js1b = step1b["parameters"]["jsCode"]
    js4 = step4["parameters"]["jsCode"]

    if "pacientes_all: data" in js1b and "Fix B 2026-06-03" in js4:
        print("!! ya aplicado"); sys.exit(3)

    if OLD_STEP_1B not in js1b:
        print("!! Step 1b anchor no match"); sys.exit(2)
    if OLD_STEP_4 not in js4:
        print("!! Step 4 anchor no match"); sys.exit(2)

    new_js1b = js1b.replace(OLD_STEP_1B, NEW_STEP_1B)
    new_js4 = js4.replace(OLD_STEP_4, NEW_STEP_4)

    print(f"Step 1b: {len(js1b)} -> {len(new_js1b)} chars (+{len(new_js1b)-len(js1b)})")
    print(f"Step 4: {len(js4)} -> {len(new_js4)} chars (+{len(new_js4)-len(js4)})")

    if args.dry or not args.apply: print("[dry] no aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"subwf_cancelar_PRE_multiples_fichas_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")

    step1b["parameters"]["jsCode"] = new_js1b
    step4["parameters"]["jsCode"] = new_js4
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_wf()
    nm2 = {n["name"]: n for n in wf2["nodes"]}
    ok = "pacientes_all: data" in nm2["Step 1b: Procesar resultado"]["parameters"]["jsCode"] and "Fix B 2026-06-03" in nm2["Step 4: Identificar Turno + Decision"]["parameters"]["jsCode"]
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
