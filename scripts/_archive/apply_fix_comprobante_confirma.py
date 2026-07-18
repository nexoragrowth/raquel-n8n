"""
Fix comprobante: el bot debe CONFIRMAR el turno cuando recibe un comprobante (no solo escalar).

Dos cambios en un solo PUT al v6 (O155MqHgOSaNZ9ye):
1. Router - Clasificar Intent: la linea COMPROBANTE de la regla #2 ahora gana sobre
   la regla de continuacion (un comprobante SIEMPRE -> confirmar_post_recordatorio,
   incluso viniendo de flujo agendar/cancelar). Asi el comprobante siempre cae en el
   Sub-Agent Confirmar, que es donde vive la logica.
2. Sub-Agent Confirmar: systemMessage = assemble desde partials (incluye el nuevo PASO 0
   que confirma el turno + escala, en vez de solo escalar).

Modos:
  --dry   : muestra los diffs, NO aplica.
  --apply : backup pre + PUT + backup post + verify.
"""
from __future__ import annotations
import argparse, json, os, sys, io
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from build_prompts_v6 import assemble, find_node, put_workflow  # reuse

BASE = os.environ["N8N_BASE_URL"].rstrip("/")
KEY = os.environ["N8N_API_KEY"]
WF_ID = "O155MqHgOSaNZ9ye"
H = {"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}

ROUTER_NODE = "Router - Clasificar Intent"
CONFIRMAR_NODE = "Sub-Agent Confirmar"

OLD_COMPROBANTE = '- COMPROBANTE: [DOCUMENTO] o [IMAGEN] con palabras "comprobante", "transferencia", "monto", "BBVA", "Macro", "alias", "ARS $".'
NEW_COMPROBANTE = '- COMPROBANTE (PRIORIDAD sobre la regla de continuacion): [DOCUMENTO] o [IMAGEN] que contenga "TIPO: COMPROBANTE" o las palabras "comprobante", "transferencia", "monto", "BBVA", "Macro", "alias", "ARS $" -> SIEMPRE confirmar_post_recordatorio, INCLUSO si venis de un flujo agendar o cancelar. Un comprobante confirma un turno PRE-reservado; lo maneja el Sub-Agent Confirmar.'


def get_live() -> dict:
    r = requests.get(f"{BASE}/api/v1/workflows/{WF_ID}", headers=H, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    wf = get_live()

    # --- Cambio 1: Router ---
    router = find_node(wf, ROUTER_NODE)
    rmsg = router["parameters"]["options"]["systemMessage"]
    if OLD_COMPROBANTE not in rmsg:
        print("!! NO encontre la linea COMPROBANTE exacta en el Router. Abortando.")
        print("   (el prompt vivo puede haber cambiado; revisar manualmente)")
        sys.exit(2)
    new_rmsg = rmsg.replace(OLD_COMPROBANTE, NEW_COMPROBANTE)
    print("=== CAMBIO 1: Router - linea COMPROBANTE (regla #2) ===")
    print("--- ANTES ---")
    print(OLD_COMPROBANTE)
    print("--- DESPUES ---")
    print(NEW_COMPROBANTE)
    print(f"\n(Router systemMessage: {len(rmsg)} -> {len(new_rmsg)} chars)")

    # --- Cambio 2: Confirmar ---
    confirmar = find_node(wf, CONFIRMAR_NODE)
    cmsg = confirmar["parameters"]["options"]["systemMessage"]
    new_cmsg = assemble(CONFIRMAR_NODE)
    print(f"\n=== CAMBIO 2: Sub-Agent Confirmar (PASO 0 nuevo) ===")
    print(f"(Confirmar systemMessage: {len(cmsg)} -> {len(new_cmsg)} chars, delta {len(new_cmsg)-len(cmsg):+d})")

    if args.dry or not args.apply:
        print("\n[dry] no se aplico nada. Correr con --apply para PUT.")
        return

    # backup pre
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre = ROOT / "workflows" / "history" / f"v6_PRE_fix_comprobante_{ts}.json"
    pre.parent.mkdir(parents=True, exist_ok=True)
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nbackup pre -> {pre}")

    router["parameters"]["options"]["systemMessage"] = new_rmsg
    confirmar["parameters"]["options"]["systemMessage"] = new_cmsg

    res = put_workflow(wf)
    print(f"PUT OK updatedAt={res.get('updatedAt')}")

    # verify
    wf2 = get_live()
    r_ok = NEW_COMPROBANTE in find_node(wf2, ROUTER_NODE)["parameters"]["options"]["systemMessage"]
    c_ok = find_node(wf2, CONFIRMAR_NODE)["parameters"]["options"]["systemMessage"] == new_cmsg
    print(f"[verify] Router: {'OK' if r_ok else 'FAIL'} | Confirmar: {'OK' if c_ok else 'FAIL'}")

    post = ROOT / "workflows" / "history" / f"v6_POST_fix_comprobante_{ts}.json"
    post.write_text(json.dumps(wf2, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"backup post -> {post}")
    if not (r_ok and c_ok):
        sys.exit(3)


if __name__ == "__main__":
    main()
