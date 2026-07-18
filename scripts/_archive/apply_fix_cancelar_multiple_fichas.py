"""Fix A defensivo en Sub-WF Cancelar (5cAWJxiWJ50hxEq3):
ante VARIAS fichas con el mismo celular (familia), NO cancelar a ciegas la primera -> escalar.

- Step 1b: agrega flag `multiple_fichas: data.length > 1`.
- Step 4: al inicio (junto a loop/frustracion), si multiple_fichas -> decision = escalar.
  Asi Step 6 rutea a escalado (6c), NUNCA a cancelar (6a). El caso normal (1 ficha) NO cambia.

Modos: --dry / --apply (backup + PUT + verify)."""
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

STEP1B = "Step 1b: Procesar resultado"
STEP4 = "Step 4: Identificar Turno + Decision"

S1B_OLD = "    paciente: data[0],\n    variant_used: 'celular_completo',"
S1B_NEW = "    paciente: data[0],\n    multiple_fichas: data.length > 1,\n    variant_used: 'celular_completo',"

S4_ANCHOR = "function fechaNatural(yyyyMmDd) {"
S4_BLOCK = """// === Fix A: celular compartido por varias fichas (familia) -> NO cancelar a ciegas, escalar ===
const multipleFichas = $('Step 1b: Procesar resultado').first().json.multiple_fichas === true;
if (multipleFichas) {
  return [{ json: {
    ...prev,
    decision: {
      siguiente_paso: 'escalar',
      razon: 'multiple_fichas_mismo_celular',
      canned: 'Con este numero figuran varias personas registradas. Le paso a la secretaria Irina para coordinar la cancelacion de forma segura. En un momento le responde.'
    }
  }}];
}

"""


def get_wf():
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=40); r.raise_for_status(); return r.json()

def put_wf(wf):
    allowed = {"saveExecutionProgress","saveManualExecutions","saveDataErrorExecution","saveDataSuccessExecution",
               "executionTimeout","errorWorkflow","timezone","executionOrder","callerPolicy","callerIds"}
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    r = requests.put(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, json=body, timeout=40)
    if not r.ok: print("PUT FAIL", r.status_code, r.text[:400], file=sys.stderr); r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    wf = get_wf()
    n1b = next((n for n in wf["nodes"] if n["name"] == STEP1B), None)
    n4 = next((n for n in wf["nodes"] if n["name"] == STEP4), None)
    if not n1b or not n4: print("!! falta algun step"); sys.exit(2)

    c1b = n1b["parameters"]["jsCode"]; c4 = n4["parameters"]["jsCode"]
    if S1B_OLD not in c1b:
        print("!! anchor Step 1b no encontrado. Abortando."); sys.exit(3)
    if S4_ANCHOR not in c4:
        print("!! anchor Step 4 no encontrado. Abortando."); sys.exit(3)
    if "multiple_fichas" in c1b or "multiple_fichas" in c4:
        print("!! ya parece aplicado (multiple_fichas presente). Abortando para no duplicar."); sys.exit(4)

    new_c1b = c1b.replace(S1B_OLD, S1B_NEW)
    new_c4 = c4.replace(S4_ANCHOR, S4_BLOCK + S4_ANCHOR, 1)

    print(f"Step 1b: {len(c1b)} -> {len(new_c1b)} chars")
    print(f"Step 4 : {len(c4)} -> {len(new_c4)} chars")
    if args.dry or not args.apply:
        print("\n--- Step 4 insertara este bloque ---\n" + S4_BLOCK); print("[dry] no aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"cancelar_PRE_fix_multiple_fichas_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup pre -> {pre}")

    n1b["parameters"]["jsCode"] = new_c1b
    n4["parameters"]["jsCode"] = new_c4
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")

    wf2 = get_wf()
    v1b = next(n for n in wf2["nodes"] if n["name"] == STEP1B)["parameters"]["jsCode"]
    v4 = next(n for n in wf2["nodes"] if n["name"] == STEP4)["parameters"]["jsCode"]
    print("[verify] Step1b:", "OK" if "multiple_fichas: data.length > 1" in v1b else "FAIL",
          "| Step4:", "OK" if "multiple_fichas_mismo_celular" in v4 else "FAIL")


if __name__ == "__main__":
    main()
