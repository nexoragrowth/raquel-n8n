"""URGENTE - Sub-WF Cancelar: 2 bugs descubiertos en test E2E noche 03/06.

1. Step 4 match multi-fichas: el matcheo busca nombre COMPLETO ('Test - Lucas')
   en memoria. Pero memoria dice 'Lucas Silva' (sin 'Test -'). Fix: tokenizar
   nombre del paciente y matchear AL MENOS UN token (>=3 chars).

2. Step 5 NO maneja siguiente_paso === 'preguntar_nombre_paciente'. Cae al
   fallback 'No veo turno activo. Le paso a la secretaria.'. Fix: agregar case.

Modo: --dry / --apply
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

# === Step 4 — mejorar match por tokens ===
OLD_STEP4_MATCH = """  // Intentar matchear UNA ficha por nombre/apellido
  const matched = pacientesAll.filter(p => {
    const nombre = (p.nombre || '').toLowerCase().trim();
    const apellido = (p.apellido || '').toLowerCase().trim();
    if (!nombre && !apellido) return false;
    // Match si nombre Y apellido aparecen, o si nombre+apellido juntos en searchPool
    const full = (nombre + ' ' + apellido).trim();
    if (nombre && searchPool.includes(nombre)) return true;
    if (full && searchPool.includes(full)) return true;
    return false;
  });"""

NEW_STEP4_MATCH = """  // FIX 2026-06-04 (token match): el matcheo anterior buscaba 'Test - Lucas' literal,
  // pero memoria dice 'Lucas Silva' (sin 'Test -'). Ahora tokenizamos y matchamos
  // si AL MENOS UN token relevante (>=3 chars, alfanumerico) coincide.
  const STOP_TOKENS = new Set(['test','prueba','paciente','el','la','los','las','de','del','dr','dra','sr','sra']);
  const tokenizar = (s) => (s || '').toLowerCase()
    .replace(/[^a-záéíóúñ0-9\\s]/gi, ' ')
    .split(/\\s+/)
    .filter(t => t.length >= 3 && !STOP_TOKENS.has(t));
  const matched = pacientesAll.filter(p => {
    const nombre = (p.nombre || '').toLowerCase().trim();
    const apellido = (p.apellido || '').toLowerCase().trim();
    if (!nombre && !apellido) return false;
    const tokens = [...tokenizar(nombre), ...tokenizar(apellido)];
    if (tokens.length === 0) return false;
    // Match si AL MENOS UN token aparece en searchPool
    return tokens.some(t => searchPool.includes(t));
  });"""

# === Step 5 — agregar case preguntar_nombre_paciente ===
OLD_STEP5_FALLBACK = """if (dec.siguiente_paso === 'escalar') {
  return [{ json: { ...prev, action_to_execute: 'escalar', mensaje_final: dec.canned || 'No veo turno activo. Le paso a la secretaria.' } }];
}"""

NEW_STEP5_FALLBACK = """if (dec.siguiente_paso === 'escalar') {
  return [{ json: { ...prev, action_to_execute: 'escalar', mensaje_final: dec.canned || 'No veo turno activo. Le paso a la secretaria.' } }];
}

// FIX 2026-06-04: nuevo case desde Step 4 cuando hay multi-fichas y no matcheo.
if (dec.siguiente_paso === 'preguntar_nombre_paciente') {
  return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: dec.canned || 'Con este numero figuran varias personas. Para quien es la cancelacion? Pasame nombre y apellido.' } }];
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

    s4 = next((n for n in wf["nodes"] if n["name"] == "Step 4: Identificar Turno + Decision"), None)
    s5 = next((n for n in wf["nodes"] if n["name"] == "Step 5: Decidir Accion Ejecutable"), None)
    if not s4 or not s5:
        print("!! nodos no encontrados"); sys.exit(2)
    js4 = s4["parameters"]["jsCode"]
    js5 = s5["parameters"]["jsCode"]

    if "FIX 2026-06-04 (token match)" in js4 and "FIX 2026-06-04: nuevo case" in js5:
        print("!! ya aplicado"); sys.exit(3)
    if OLD_STEP4_MATCH not in js4:
        print("!! Step 4 anchor no match"); sys.exit(2)
    if OLD_STEP5_FALLBACK not in js5:
        print("!! Step 5 anchor no match"); sys.exit(2)
    new_js4 = js4.replace(OLD_STEP4_MATCH, NEW_STEP4_MATCH)
    new_js5 = js5.replace(OLD_STEP5_FALLBACK, NEW_STEP5_FALLBACK)

    print(f"Step 4: {len(js4)} -> {len(new_js4)} chars (+{len(new_js4)-len(js4)})")
    print(f"Step 5: {len(js5)} -> {len(new_js5)} chars (+{len(new_js5)-len(js5)})")

    if args.dry or not args.apply: print("[dry] no aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"subwf_cancelar_PRE_match_tokens_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(get_wf(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")

    s4["parameters"]["jsCode"] = new_js4
    s5["parameters"]["jsCode"] = new_js5
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_wf()
    n4_2 = next(n for n in wf2["nodes"] if n["name"] == "Step 4: Identificar Turno + Decision")
    n5_2 = next(n for n in wf2["nodes"] if n["name"] == "Step 5: Decidir Accion Ejecutable")
    ok = "FIX 2026-06-04 (token match)" in n4_2["parameters"]["jsCode"] and "FIX 2026-06-04: nuevo case" in n5_2["parameters"]["jsCode"]
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
