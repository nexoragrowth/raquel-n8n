# -*- coding: utf-8 -*-
"""
apply_prompt_precio_general.py — pedido de la secretaria (2026-07-21):
Cambia el CANNED de "Precio consulta" en el prompt del Sub-Agent General del v6:
  - responde con el valor + los datos de pago (alias/CBU) para que el paciente vaya abonando
  - QUITA el "Desea agendar un turno?" (no ofrecer agendar cuando ya reservó)

Cambia SOLO esa línea del systemMessage de ESE nodo; todo lo demás queda intacto.
Patrón GATE-0: GET live -> backup PRE -> reemplazo exacto -> chequeo banlist -> PUT -> verifica.

USO (igual que el gate):
  # Preview (NO toca n8n): muestra el antes/después.
  python scripts/apply_prompt_precio_general.py

  # Aplicar de verdad (requiere N8N_API_BASE / N8N_API_KEY, los del panel .env.local):
  #   PowerShell:
  #   cd c:\\Users\\not\\Desktop\\proyectos\\raquel-n8n
  #   gc ..\\nexora-whatsapp-agent\\.env.local | ? { $_ -match '^N8N_API_(BASE|KEY)=' } | % { $p = $_ -split '=',2; Set-Item "env:$($p[0])" $p[1].Trim('"') }
  #   python scripts\\apply_prompt_precio_general.py --apply
"""
import argparse
import json
import os
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

WF_ID = os.environ.get("N8N_WF_BOT", "O155MqHgOSaNZ9ye")
BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""
NODO = "Sub-Agent General"

# --- El canned ACTUAL (v2, aplicado el 21/7) que hay que reemplazar ---
VIEJO = (
    "- **Precio consulta / 1ra visita**: cuando pregunten el PRECIO de la consulta, responder con "
    "el valor y los datos de pago COMPLETOS, todo en UN SOLO mensaje, SIN usar el formato de `---` "
    "(no lo dividas ni lo cortes, mandá el bloque entero). Texto exacto:\n"
    '"El valor de la consulta es de $50.000. Si desea ir abonando, puede hacerlo al siguiente alias:\n'
    "dra.raquel.aurea\n"
    "Titular: Laura Raquel Rodríguez\n"
    "CUIT/CUIL: 27316870118\n"
    "CBU: 1430001713001112680016\n"
    "NRO. CUENTA: 1300111268001\n"
    'Banco: BRUBANK"'
)

# --- v3: 3 PARTES con `---` (texto / alias solo para copiar / datos de cuenta).
# v2 pedía "un solo mensaje sin ---" y el Formatting igual partía y descartaba el resto.
# Con los `---` explícitos, el Split manda 3 mensajes y no se pierde nada. ---
NUEVO = (
    "- **Precio consulta / 1ra visita**: cuando pregunten el PRECIO de la consulta, responder con "
    "el valor y los datos de pago COMPLETOS, en 3 PARTES separadas por `---` (el alias va SOLO en "
    "su parte, para que lo puedan copiar). Texto exacto, incluidos los `---`:\n"
    '"El valor de la consulta es de $50.000. Si desea ir abonando, puede hacerlo al siguiente alias:\n'
    "---\n"
    "dra.raquel.aurea\n"
    "---\n"
    "Titular: Laura Raquel Rodríguez\n"
    "CUIT/CUIL: 27316870118\n"
    "CBU: 1430001713001112680016\n"
    "NRO. CUENTA: 1300111268001\n"
    'Banco: BRUBANK"\n'
    "NUNCA omitas la TERCERA parte (los datos de cuenta): las 3 partes van siempre."
)

# --- Banlist (mismos patrones que el Banlist Validator del v6) — red de seguridad ---
BANLIST = [
    (r"\bven[íi](te)?\b", "venite/vení"),
    (r"\bveng(a|an|amos)\b", "venga/vengan"),
    (r"\b(los|las|te|le|la|lo)\s*esperamos\b", "los/te esperamos"),
    (r"\bsalgan?\s+(ya|ahora|para)\b", "salgan ya/para"),
    (r"\bguard(á|a|alo|enlo|en|amos)\s+", "guardá/guarden"),
    (r"\btraig(a|an|alo|anlo|amos)\b", "traigan"),
    (r"\btom(á|a|alo|en|amos)\s+(\d|un|una|el|la|los|las|cada)", "tomá dosis"),
    (r"\baplic(á|a|ate|en|ense)\b", "aplicá (médico)"),
    (r"\bno\s+te\s+preocup(es|és)\b", "no te preocupes"),
    (r"\bbalcarce\s*(n[º°]?\s*)?37\b", "dirección Balcarce 37"),
]


def chequear_banlist(texto):
    hits = []
    # Excluimos la sección de dirección legítima (la línea de Direccion tiene Balcarce a propósito).
    for rx, why in BANLIST:
        for m in re.finditer(rx, texto, re.I):
            hits.append((m.group(0), why))
    return hits


def api(method, path, body=None):
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": KEY, "accept": "application/json", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="hace el PUT real")
    ap.add_argument("--base", help="archivo backup a usar en preview")
    args = ap.parse_args()

    if args.apply:
        if not (BASE and KEY):
            print("!! Faltan N8N_API_BASE / N8N_API_KEY en el entorno."); sys.exit(1)
        wf = api("GET", f"/workflows/{WF_ID}")
        json.dump(wf, open("workflows/history/v6_PRE_prompt_precio_LIVE.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("backup PRE -> workflows/history/v6_PRE_prompt_precio_LIVE.json")
    else:
        base = args.base or "workflows/history/v6_POST_a1_20260718_182612.json"
        print(f"[PREVIEW] sobre {base} (NO toca n8n)")
        wf = json.load(open(base, encoding="utf-8"))

    node = next((n for n in wf["nodes"] if n["name"] == NODO and n["type"].endswith("langchain.agent")), None)
    if not node:
        print(f"!! No encontré el nodo '{NODO}'."); sys.exit(1)
    opts = node["parameters"].setdefault("options", {})
    sm = opts.get("systemMessage", "")

    if VIEJO not in sm:
        print("!! No encontré el canned viejo EXACTO en el prompt (quizás ya se cambió o difiere).")
        print("   Reviso si el nuevo ya está:", "SÍ ya aplicado." if NUEVO in sm else "tampoco. Abortar y avisar a Claude.")
        sys.exit(1)

    nuevo_sm = sm.replace(VIEJO, NUEVO)

    # Chequeo banlist SOBRE EL CAMBIO (el bloque nuevo), no todo el prompt (que ya tiene
    # la dirección legítima). Si el texto nuevo tuviera algo prohibido, abortamos.
    hits = chequear_banlist(NUEVO)
    print("\n--- CHEQUEO BANLIST del texto nuevo ---")
    if hits:
        print("!! El texto nuevo dispara el banlist -> ABORTO:", hits); sys.exit(1)
    print("OK limpio (0 frases prohibidas).")

    print("\n--- DIFF ---")
    print("VIEJO:\n" + VIEJO)
    print("\nNUEVO:\n" + NUEVO)

    opts["systemMessage"] = nuevo_sm

    if not args.apply:
        print("\n[PREVIEW] listo. Para aplicar: --apply (con las env de n8n).")
        return

    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED_SETTINGS}
    api("PUT", f"/workflows/{WF_ID}", {
        "name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
        "settings": settings, "staticData": wf.get("staticData"),
    })
    live = api("GET", f"/workflows/{WF_ID}")
    ln = next(n for n in live["nodes"] if n["name"] == NODO)
    ok = NUEVO in (ln["parameters"].get("options", {}) or {}).get("systemMessage", "")
    print("\nverificación post-PUT:", "OK ✅ canned nuevo presente" if ok else "!! NO se ve el cambio")


if __name__ == "__main__":
    main()
