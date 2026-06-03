"""Fix audio fromMe: el codigo de 'Build fromMe AI memory' descartaba mensajes sin texto
(audios/imagenes/docs de Iri/Dra). Resultado: el bot no se enteraba de que el humano estaba
atendiendo y retomaba la conversacion. Ahora usa placeholder generico si no hay texto.

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
WF_ID = "O155MqHgOSaNZ9ye"; H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}
NODE = "Build fromMe AI memory"

NEW_CODE = """// Guardar mensaje saliente (Iri/doctora desde WA Web/app del consultorio) en memoria.
// FIX 2026-05-09 V1: prefijar el content con tag explicito para que el LLM NO lo confunda con output propio.
// FIX 2026-06-02 V2: si no hay texto (audio/imagen/documento), igual marcar atencion humana con placeholder.
//   Antes: si text estaba vacio, return [] -> el bot no se enteraba que la Dra/Iri atendio en audio/imagen,
//   y retomaba la conversacion. Caso real: 1/6 Lucas respondio al audio de la Dra y el bot le contesto.
const text = ($json.text || '').trim();
const phone = $json.phone;
if (!phone) return [];

const content = text || '[mensaje multimedia enviado por la doctora/secretaria - sin texto adjunto]';

const TAG = '[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria desde el WhatsApp del consultorio. NO es output tuyo, es un humano atendiendo este chat. Mantente en silencio y NO respondas en este chat hasta que un admin diga /bot on.]: ';

const session_id = phone;
const message = {
  type: 'ai',
  content: TAG + content,
  additional_kwargs: { source: 'wa_outbound', from_iri_or_dra: true, was_multimedia: !text },
  response_metadata: {},
  tool_calls: [],
  invalid_tool_calls: []
};
return [{ json: { session_id, message: JSON.stringify(message) } }];
"""


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
    if not n: print("!! no encontre el nodo"); sys.exit(2)
    old = n["parameters"].get("jsCode", "")
    if "was_multimedia" in old or "FIX 2026-06-02 V2" in old:
        print("!! ya aplicado"); sys.exit(3)
    print(f"{NODE}: {len(old)} -> {len(NEW_CODE)} chars (delta {len(NEW_CODE)-len(old):+d})")

    if args.dry or not args.apply:
        print("\n--- CODIGO NUEVO ---\n" + NEW_CODE); print("\n[dry] no aplicado."); return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_fix_fromme_multimedia_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")
    n["parameters"]["jsCode"] = NEW_CODE
    res = put_wf(wf); print(f"PUT OK updatedAt={res.get('updatedAt')}")
    wf2 = get_wf()
    n2 = next(x for x in wf2["nodes"] if x["name"] == NODE)
    ok = "was_multimedia" in n2["parameters"].get("jsCode", "")
    print(f"[verify] {'OK' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
