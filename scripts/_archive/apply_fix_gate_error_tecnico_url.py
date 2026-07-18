"""URGENTE - Gate Error Tecnico del v6 main: el bloque de escalacion HTTP tiene
url: '<EVOLUTION_URL>/message/sendText/raquel' — placeholder literal, NUNCA fue
reemplazado. Cada vez que el bot tira max iterations / agent stopped, el canned
SI se envia al paciente, pero el aviso a Lucas NUNCA llega porque el POST falla
con DNS lookup contra '<EVOLUTION_URL>'. El try/catch lo silencia.

Fix: reemplazar por POST al helper notify-grupo (mismo patron usado el 22/5 para
arreglar escalar_a_secretaria). El helper ya tiene cred Evolution real, envia al
grupo y aplica label humano.

Workflow: v6 main (O155MqHgOSaNZ9ye) / nodo Gate Error Tecnico.

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
WF_ID = "O155MqHgOSaNZ9ye"; H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
NODE = "Gate Error Tecnico"

OLD_BLOCK = """    try {
      await this.helpers.httpRequest({
        method: 'POST',
        url: '<EVOLUTION_URL>/message/sendText/raquel',
        headers: {
          'apikey': '4E2D1CE57F2F-471B-895E-EB2B8F427FAD',
          'Content-Type': 'application/json',
        },
        body: {
          number: '5491161461034',
          text: '[ESCALADO BOT] Bot tuvo error tecnico (max iterations / agent stopped), revisar conversacion. Phone: ' + phone,
        },
        json: true,
      });
    } catch (e) {
      // Best-effort: si falla la escalacion, el canned igual se envia al paciente
      console.log('[Gate Error Tecnico] escalation send failed:', e.message);
    }"""

NEW_BLOCK = """    // FIX 2026-06-02: url era '<EVOLUTION_URL>' placeholder literal -> escalacion JAMAS llegaba a Lucas.
    // Ahora via helper notify-grupo (mismo patron del fix Round 8 de escalar_a_secretaria).
    try {
      await this.helpers.httpRequest({
        method: 'POST',
        url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
        body: {
          phone: phone,
          resumen: 'Bot tuvo error tecnico (max iterations / agent stopped), revisar conversacion. Phone: ' + phone,
        },
        json: true,
      });
    } catch (e) {
      // Best-effort: si falla la escalacion, el canned igual se envia al paciente.
      console.log('[Gate Error Tecnico] escalation send failed:', e.message);
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
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:300], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()
    n = next((x for x in wf["nodes"] if x["name"] == NODE), None)
    if not n: print(f"!! nodo '{NODE}' no encontrado"); sys.exit(2)
    js = n["parameters"].get("jsCode", "")
    if "FIX 2026-06-02" in js and "notify-grupo" in js:
        print("!! ya aplicado"); sys.exit(3)
    cnt = js.count(OLD_BLOCK)
    if cnt != 1:
        print(f"!! anchor no match: count={cnt}. Aborto."); sys.exit(2)
    new_js = js.replace(OLD_BLOCK, NEW_BLOCK)
    print(f"{NODE}: {len(js)} -> {len(new_js)} chars (delta {len(new_js)-len(js):+d})")
    print(f"  url vieja: '<EVOLUTION_URL>/message/sendText/raquel'")
    print(f"  url nueva: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo'")
    if args.dry or not args.apply: print("\n[dry] no aplicado."); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_gate_error_url_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")
    n["parameters"]["jsCode"] = new_js
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(x for x in wf2["nodes"] if x["name"] == NODE)
    ok = ("FIX 2026-06-02" in n2["parameters"].get("jsCode", "")
          and "<EVOLUTION_URL>" not in n2["parameters"].get("jsCode", ""))
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
