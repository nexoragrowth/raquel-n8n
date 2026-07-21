# -*- coding: utf-8 -*-
"""
apply_fix_split_fallback.py — FIX DEFINITIVO del bloque de datos de cuenta que no llegaba.

DIAGNÓSTICO (con datos, no suposiciones):
  1. El SUB-AGENTE genera las 3 partes perfecto  → verificado en n8n_chat_histories
     (id 478: tiene los `---` y el CBU completo).
  2. El FORMATTING AGENT (un LLM) las reduce a 2 → descarta el bloque de datos de cuenta,
     incluso con la instrucción "NUNCA DESCARTES CONTENIDO" ya aplicada (verificado en vivo).
  3. El Split recibe ya solo 2 partes → por eso SIEMPRE llegaban 2 mensajes.
  (Mi hipótesis anterior del nodo Wait era ERRÓNEA: el Wait nunca fue el problema.)

FIX (2 cambios):
  A. "Split en Mensajes": GUARD determinístico. Si el texto ORIGINAL del agente traía el
     bloque de datos (CBU) y el texto FORMATEADO lo perdió, se usa el ORIGINAL. No depende
     de que el LLM se porte bien.
  B. Revierte mi cambio anterior: la salida false de "Es primer mensaje?" vuelve a pasar por
     "Delay Humano" (el Wait), que es lo que mantiene el ORDEN de los mensajes.

USO:
  python scripts/apply_fix_split_fallback.py            # preview
  python scripts/apply_fix_split_fallback.py --apply    # aplica (con env n8n)
"""
import argparse
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

WF_ID = os.environ.get("N8N_WF_BOT", "O155MqHgOSaNZ9ye")
BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""

SPLIT_NODE = "Split en Mensajes"
IF_NODE = "Es primer mensaje?"
WAIT_NODE = "Delay Humano"
TYPING = "Evolution - Typing"

LINEA_VIEJA = "const output = $input.first().json.output || '';"
LINEA_NUEVA = """// GUARD 2026-07-21: el Formatting Agent (LLM) a veces DESCARTA partes — típicamente el
// bloque de datos de cuenta (Titular/CUIT/CBU/...). Si el texto ORIGINAL del agente traía
// ese bloque y el formateado lo perdió, usamos el ORIGINAL. Determinístico: no depende de
// que el LLM obedezca.
const formateado = ($input.first().json.output || '').toString();
let original = '';
try { original = ($('Banlist Validator').first().json.output || '').toString(); } catch (e) { original = ''; }
const perdioDatos = /\\bCBU\\b/i.test(original) && !/\\bCBU\\b/i.test(formateado);
const output = perdioDatos ? original : formateado;"""

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": KEY, "accept": "application/json", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--base")
    args = ap.parse_args()

    if args.apply:
        if not (BASE and KEY):
            print("!! Faltan N8N_API_BASE / N8N_API_KEY."); sys.exit(1)
        wf = api("GET", f"/workflows/{WF_ID}")
        json.dump(wf, open("workflows/history/v6_PRE_split_fallback_LIVE.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("backup PRE -> workflows/history/v6_PRE_split_fallback_LIVE.json")
    else:
        base = args.base or "workflows/history/v6_POST_a1_20260718_182612.json"
        print(f"[PREVIEW] sobre {base} (NO toca n8n)")
        wf = json.load(open(base, encoding="utf-8"))

    cambios = 0

    # --- A. Guard en Split en Mensajes ---
    split = next((n for n in wf["nodes"] if n["name"] == SPLIT_NODE), None)
    if not split:
        print(f"!! No encontré '{SPLIT_NODE}'."); sys.exit(1)
    code = split["parameters"].get("jsCode", "")
    if "perdioDatos" in code:
        print("• A) El guard ya estaba aplicado")
    elif LINEA_VIEJA in code:
        split["parameters"]["jsCode"] = code.replace(LINEA_VIEJA, LINEA_NUEVA, 1)
        cambios += 1
        print("✓ A) Guard determinístico agregado en 'Split en Mensajes'")
    else:
        print("!! A) No encontré la línea esperada en el Split -> abortar."); sys.exit(1)

    # --- B. Revertir el Wait (recupera el ORDEN de los mensajes) ---
    falso = wf["connections"][IF_NODE]["main"][1]
    destinos = [l["node"] for l in falso]
    if destinos == [WAIT_NODE]:
        print("• B) El Wait ya estaba en su lugar")
    elif TYPING in destinos:
        wf["connections"][IF_NODE]["main"][1] = [
            {"node": WAIT_NODE, "type": "main", "index": 0} if l["node"] == TYPING else l for l in falso
        ]
        cambios += 1
        print(f"✓ B) Revertido: salida false vuelve a '{WAIT_NODE}' (mantiene el orden)")
    else:
        print(f"!! B) Destinos inesperados: {destinos} -> no toco esa conexión")

    if cambios == 0:
        print("\nNada para cambiar."); return
    if not args.apply:
        print(f"\n[PREVIEW] {cambios} cambio(s). Para aplicar: --apply")
        return

    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED_SETTINGS}
    api("PUT", f"/workflows/{WF_ID}", {
        "name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
        "settings": settings, "staticData": wf.get("staticData"),
    })
    live = api("GET", f"/workflows/{WF_ID}")
    lsplit = next(n for n in live["nodes"] if n["name"] == SPLIT_NODE)
    okA = "perdioDatos" in lsplit["parameters"].get("jsCode", "")
    okB = [l["node"] for l in live["connections"][IF_NODE]["main"][1]] == [WAIT_NODE]
    print(f"\nverificación post-PUT: guard={'OK ✅' if okA else '!!'}  orden/Wait={'OK ✅' if okB else '!!'}")


if __name__ == "__main__":
    main()
