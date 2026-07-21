# -*- coding: utf-8 -*-
"""
apply_prompt_formatting_datos.py — FIX: el bloque de datos de cuenta
(Titular/CUIT/CBU/NRO. CUENTA/Banco) no llegaba al paciente.

CAUSA RAÍZ: el "Formatting Agent - WhatsApp" tiene la REGLA #4 (split con ---) y su
ÚNICO ejemplo es de 2 partes (texto + alias). Cuando el sub-agente manda el canned de
3 partes (preámbulo / alias / datos de cuenta), el Formatting copia el patrón del
ejemplo y DESCARTA el 3er bloque. El nodo "Split en Mensajes" está OK: parte lo que le
llega — el problema es que le llega ya recortado.

FIX (2 reemplazos en el systemMessage del Formatting Agent):
  1. REGLA #4: agrega "NUNCA DESCARTES CONTENIDO" + que el bloque de datos va completo.
  2. Agrega un EJEMPLO de 3 partes con el bloque de datos, para que copie ese patrón.

USO (igual que los otros):
  python scripts/apply_prompt_formatting_datos.py            # preview
  python scripts/apply_prompt_formatting_datos.py --apply    # aplica (con env n8n)
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
NODO = "Formatting Agent - WhatsApp"

# --- Reemplazo 1: REGLA #4 ---
R4_VIEJO = (
    "REGLA #4 — SPLIT INTELIGENTE (con --- como separador):\n"
    "SOLO splitear cuando hay un dato para copiar (alias bancario, CBU, email, teléfono, dirección, link) "
    "-> ese dato va SOLO en su mensaje, sin texto extra. Máximo 3 partes.\n"
    "NO splitear: listas de turnos (van juntas), respuestas de 1-2 oraciones, oraciones conectadas."
)
R4_NUEVO = (
    "REGLA #4 — SPLIT INTELIGENTE (con --- como separador):\n"
    "SOLO splitear cuando hay un dato para copiar (alias bancario, CBU, email, teléfono, dirección, link) "
    "-> ese dato va SOLO en su mensaje, sin texto extra. Máximo 3 partes.\n"
    "NO splitear: listas de turnos (van juntas), respuestas de 1-2 oraciones, oraciones conectadas.\n"
    "NUNCA DESCARTES CONTENIDO: si la entrada trae el bloque de datos de cuenta "
    "(Titular / CUIT/CUIL / CBU / NRO. CUENTA / Banco), ese bloque SIEMPRE se envía COMPLETO "
    "como su propia parte. Está PROHIBIDO omitirlo o resumirlo. Si la entrada ya viene con 3 partes "
    "separadas por ---, devolvé las 3."
)

# --- Reemplazo 2: sumar un ejemplo de 3 partes ---
EJ_VIEJO = (
    'Entrada: "El valor de la consulta es $50.000. Puede transferir al alias dra.raquel.aurea."\n'
    "Salida:\n"
    "El valor de la consulta es $50.000. Puede transferir al alias.\n"
    "---\n"
    "dra.raquel.aurea"
)
EJ_NUEVO = (
    'Entrada: "El valor de la consulta es $50.000. Puede transferir al alias dra.raquel.aurea."\n'
    "Salida:\n"
    "El valor de la consulta es $50.000. Puede transferir al alias.\n"
    "---\n"
    "dra.raquel.aurea\n"
    "\n"
    'Entrada (alias + DATOS DE CUENTA): "Le envío alias y datos de cuenta de la Dra. En ese caso enviar comprobante por favor.\n'
    "---\n"
    "dra.raquel.aurea\n"
    "---\n"
    "Titular: Laura Raquel Rodríguez\n"
    "CUIT/CUIL: 27316870118\n"
    "CBU: 1430001713001112680016\n"
    "NRO. CUENTA: 1300111268001\n"
    'Banco: BRUBANK"\n'
    "Salida (3 partes — NUNCA descartes el bloque de datos):\n"
    "Le envío alias y datos de cuenta de la Dra. En ese caso enviar comprobante por favor.\n"
    "---\n"
    "dra.raquel.aurea\n"
    "---\n"
    "Titular: Laura Raquel Rodríguez\n"
    "CUIT/CUIL: 27316870118\n"
    "CBU: 1430001713001112680016\n"
    "NRO. CUENTA: 1300111268001\n"
    "Banco: BRUBANK"
)

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
    ap.add_argument("--base", help="archivo para preview")
    args = ap.parse_args()

    if args.apply:
        if not (BASE and KEY):
            print("!! Faltan N8N_API_BASE / N8N_API_KEY."); sys.exit(1)
        wf = api("GET", f"/workflows/{WF_ID}")
        json.dump(wf, open("workflows/history/v6_PRE_formatting_datos_LIVE.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        print("backup PRE -> workflows/history/v6_PRE_formatting_datos_LIVE.json")
    else:
        base = args.base or "workflows/history/v6_POST_a1_20260718_182612.json"
        print(f"[PREVIEW] sobre {base} (NO toca n8n)")
        wf = json.load(open(base, encoding="utf-8"))

    node = next((n for n in wf["nodes"] if n["name"] == NODO), None)
    if not node:
        print(f"!! No encontré '{NODO}'."); sys.exit(1)
    opts = node["parameters"].setdefault("options", {})
    sm = opts.get("systemMessage", "")

    cambios = 0
    if R4_VIEJO in sm:
        sm = sm.replace(R4_VIEJO, R4_NUEVO); cambios += 1
        print("✓ REGLA #4 actualizada (NUNCA DESCARTES CONTENIDO)")
    elif "NUNCA DESCARTES CONTENIDO" in sm:
        print("• REGLA #4 ya estaba aplicada")
    else:
        print("!! No encontré la REGLA #4 exacta -> abortar."); sys.exit(1)

    if EJ_VIEJO in sm:
        sm = sm.replace(EJ_VIEJO, EJ_NUEVO); cambios += 1
        print("✓ Ejemplo de 3 partes agregado (con bloque de datos)")
    elif "DATOS DE CUENTA" in sm:
        print("• Ejemplo ya estaba aplicado")
    else:
        print("!! No encontré el ejemplo del alias -> abortar."); sys.exit(1)

    if cambios == 0:
        print("\nNada para cambiar (ya está todo aplicado)."); return

    opts["systemMessage"] = sm

    if not args.apply:
        print(f"\n[PREVIEW] {cambios} cambio(s) listos. Para aplicar: --apply")
        return

    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED_SETTINGS}
    api("PUT", f"/workflows/{WF_ID}", {
        "name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
        "settings": settings, "staticData": wf.get("staticData"),
    })
    live = api("GET", f"/workflows/{WF_ID}")
    ln = next(n for n in live["nodes"] if n["name"] == NODO)
    lsm = (ln["parameters"].get("options", {}) or {}).get("systemMessage", "")
    ok = "NUNCA DESCARTES CONTENIDO" in lsm and "DATOS DE CUENTA" in lsm
    print("\nverificación post-PUT:", "OK ✅ Formatting Agent actualizado" if ok else "!! NO se ve el cambio")


if __name__ == "__main__":
    main()
