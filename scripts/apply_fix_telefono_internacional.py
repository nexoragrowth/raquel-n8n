# -*- coding: utf-8 -*-
"""
apply_fix_telefono_internacional.py — arregla la normalización de celular del
workflow de Recordatorios (7RqTApkvVavRmq3R) para pacientes con número EXTRANJERO.

EL BUG (detectado 2026-07-22 leyendo la ejecución 237284):
    El nodo "Preparar mensaje" asume que TODO paciente es argentino. Su última rama
    dice "cualquier cosa que no empiece con 54 -> prepender 549". Con un número
    boliviano eso produce basura:

        Dentalink: "+59173327830"   (Bolivia, válido)
          -> replace(/[^0-9]/g,"")  -> "59173327830"
          -> no arranca con "54"    -> "549" + "59173327830"
          -> "54959173327830"       ❌ 14 dígitos, no existe

    Evolution devolvió {"error":"Erro ao enviar mensagem de texto"} y la paciente
    (Isabel Sanai, cita 8529 del 24/07) NO recibió su recordatorio. Jujuy limita con
    Bolivia: esto se repite con cualquier paciente extranjero, y en las DOS corridas
    (72h y 24h) de cada turno suyo.

EL FIX (2 inserciones, cero nodos nuevos, cero rewire):
    1. Antes de limpiar los símbolos, se recuerda si el número venía en formato
       internacional (arrancaba con "+"). Ese "+" es justamente la señal de que YA
       trae código de país, y hoy se pierde en el replace.
    2. Se agrega una rama ANTES del catch-all: si venía internacional y no es
       argentino, se deja TAL CUAL.

    Los argentinos no se tocan: "+5493883299947" sigue cayendo en la primera rama
    (startsWith 549 && len 13) como siempre. Solo cambia el caso que hoy ya está roto.

USO:
    # Preview (NO toca n8n): muestra el diff exacto del código del nodo.
    python scripts/apply_fix_telefono_internacional.py

    # Aplicar de verdad (GET live -> backup PRE -> PUT -> verifica).
    # Requiere N8N_API_BASE y N8N_API_KEY en el entorno.
    python scripts/apply_fix_telefono_internacional.py --apply

Regla del proyecto: NUNCA --apply sin OK explícito de Lucas + backup previo.
"""
import argparse
import difflib
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

WF_ID = os.environ.get("N8N_WF_RECORDATORIOS", "7RqTApkvVavRmq3R")
BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""
NODO = "Preparar mensaje"

# --- el PUT del API solo acepta estas keys (regla #4 del proyecto) ---
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}

# --- (1) recordar el formato internacional ANTES de perder el "+" ---
ANCLA_1 = '// === Normalización celular: SIEMPRE termina como 549XXXXXXXXXX (13 dígitos)\ncelular = celular.replace(/[^0-9]/g, "");'
NUEVO_1 = (
    '// === Normalización celular: SIEMPRE termina como 549XXXXXXXXXX (13 dígitos)\n'
    '// OJO: el "+" inicial es la señal de que el número YA trae código de país. Hay que\n'
    '// leerlo ANTES del replace, que lo borra (pacientes de Bolivia, Jujuy es frontera).\n'
    'const esInternacional = /^\\s*\\+/.test(celular);\n'
    'celular = celular.replace(/[^0-9]/g, "");'
)

# --- (2) rama nueva para el extranjero, ANTES del catch-all que hoy lo rompe ---
ANCLA_2 = '} else if (!celular.startsWith("54")) {\n  // cualquier otra cosa que no empiece con 54: prepender 549\n  celular = "549" + celular;\n}'
NUEVO_2 = (
    '} else if (esInternacional && !celular.startsWith("54")) {\n'
    '  // Número EXTRANJERO ya completo (ej. Bolivia +591…): se deja TAL CUAL.\n'
    '  // Prependerle 549 lo rompía y Evolution rechazaba el envío\n'
    '  // (caso Isabel Sanai 22/07/2026: +59173327830 -> 54959173327830 -> "Erro ao enviar").\n'
    '} else if (!celular.startsWith("54")) {\n'
    '  // cualquier otra cosa que no empiece con 54: prepender 549\n'
    '  celular = "549" + celular;\n'
    '}'
)


def api(method, path, body=None):
    if not BASE or not KEY:
        sys.exit("!! Faltan N8N_API_BASE / N8N_API_KEY en el entorno.")
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "accept": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def parchear_codigo(code):
    """Aplica las 2 inserciones. Devuelve (nuevo_codigo, [errores])."""
    errores = []
    if "esInternacional" in code:
        errores.append("El fix YA parece aplicado (aparece 'esInternacional').")
        return code, errores
    if ANCLA_1 not in code:
        errores.append("No encontré el bloque de normalización (ancla 1). ¿Cambió el nodo?")
    if ANCLA_2 not in code:
        errores.append("No encontré el catch-all !startsWith('54') (ancla 2). ¿Cambió el nodo?")
    if errores:
        return code, errores
    return code.replace(ANCLA_1, NUEVO_1, 1).replace(ANCLA_2, NUEVO_2, 1), []


def clean_settings(wf):
    s = wf.get("settings") or {}
    return {k: v for k, v in s.items() if k in SETTINGS_OK}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="hace el PUT real (requiere OK de Lucas)")
    args = ap.parse_args()

    print(f"GET workflow {WF_ID} …")
    wf = api("GET", f"/workflows/{WF_ID}")
    print(f"  {wf['name']} — {len(wf['nodes'])} nodos")

    nodo = next((n for n in wf["nodes"] if n["name"] == NODO), None)
    if not nodo:
        sys.exit(f"!! No existe el nodo '{NODO}'.")

    viejo = nodo["parameters"].get("jsCode", "")
    nuevo, errores = parchear_codigo(viejo)
    if errores:
        for e in errores:
            print(f"!! {e}")
        sys.exit(1)

    print("\n=== DIFF del nodo 'Preparar mensaje' ===")
    for line in difflib.unified_diff(
        viejo.splitlines(), nuevo.splitlines(),
        fromfile="ANTES", tofile="DESPUES", lineterm="", n=3,
    ):
        print(line)

    # Simulación con los números reales de la corrida que falló.
    print("\n=== Simulación (los 5 de la ejecución 237284) ===")
    for crudo, quien in [
        ("+59173327830", "Isabel Sanai (Bolivia)"),
        ("+5493883299947", "Samanta (AR)"),
        ("+5493884800028", "Hilario/Pedro (AR)"),
        ("+5493884071404", "Agustin (AR)"),
    ]:
        es_intl = crudo.strip().startswith("+")
        d = "".join(c for c in crudo if c.isdigit())
        if d.startswith("549") and len(d) == 13:
            out = d
        elif d.startswith("54") and len(d) == 12:
            out = "549" + d[2:]
        elif len(d) == 10:
            out = "549" + d
        elif len(d) == 11 and d.startswith("15"):
            out = "549" + d[2:]
        elif es_intl and not d.startswith("54"):
            out = d                      # <-- rama NUEVA
        elif not d.startswith("54"):
            out = "549" + d
        else:
            out = d
        antes = ("549" + d) if (not d.startswith("54") and not (len(d) == 10)) else out
        marca = "  <-- ARREGLADO" if antes != out else ""
        print(f"  {quien:<26} {crudo:<16} antes={antes:<15} ahora={out}{marca}")

    nodo["parameters"]["jsCode"] = nuevo

    if not args.apply:
        print("\n(preview — no se tocó n8n). Para aplicar: --apply")
        return

    pre = "workflows/history/Recordatorio_PRE_fix_telefono_intl.json"
    os.makedirs("workflows/history", exist_ok=True)
    json.dump(api("GET", f"/workflows/{WF_ID}"), open(pre, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nbackup PRE -> {pre}")

    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = clean_settings(wf)
    print("PUT …")
    api("PUT", f"/workflows/{WF_ID}", body)

    vivo = api("GET", f"/workflows/{WF_ID}")
    n2 = next((n for n in vivo["nodes"] if n["name"] == NODO), None)
    ok = n2 and "esInternacional" in (n2["parameters"].get("jsCode") or "")
    post = "workflows/history/Recordatorio_POST_fix_telefono_intl.json"
    json.dump(vivo, open(post, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"backup POST -> {post}")
    print("verificación post-PUT:", "OK ✅ fix presente" if ok else "!! NO se ve el fix")
    print(f"nodos: {len(vivo['nodes'])} (antes {len(wf['nodes'])})")


if __name__ == "__main__":
    main()
