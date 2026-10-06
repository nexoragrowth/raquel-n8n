# -*- coding: utf-8 -*-
"""
apply_fix_banlist_ubicacion.py — Elimina el baneo absurdo de la ubicación en Banlist Validator.

CAUSA RAÍZ DIAGNOSTICADA (Exec #294253):
El bot ofreció un menú de opciones donde una opción era "Ubicación y horarios de atención".
El paciente respondió con el número de la opción o preguntó la ubicación.
Sub-Agent General respondió correctamente con la dirección oficial (Balcarce 37).
PERO 'Banlist Validator' tenía una regla que consideraba "Balcarce 37" como frase prohibida,
bloqueó la respuesta y escaló a la secretaria con:
"Recibimos su mensaje. Estamos derivando su caso a la Dra. Raquel..."

SOLUCIÓN:
Eliminar la regla de baneo de Balcarce 37 del BANLIST.
La dirección oficial de la clínica NO es una frase prohibida; lo que está prohibido es invitar
a venir sin turno ("venite ya", "los esperamos ahora mismo"), lo cual ya está 100% cubierto
por las otras reglas del banlist.

USO:
  python scripts/apply_fix_banlist_ubicacion.py            # dry-run
  python scripts/apply_fix_banlist_ubicacion.py --apply    # aplica a produccion
"""
import argparse, difflib, json, os, sys, time, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_media_entrantes import api, clean_settings, PUT_KEYS, WF_ID

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
LABEL = "fix_banlist_ubicacion"
WEBHOOK = "Webhook - Evolution API"
NODO = "Banlist Validator"

def build(wf):
    nodo = next((n for n in wf["nodes"] if n["name"] == NODO), None)
    if not nodo:
        sys.exit(f"ERROR: No se encontró el nodo {NODO}")
    
    code = nodo["parameters"]["jsCode"]
    antes = code
    
    # Eliminar la regla de Balcarce 37 de la lista BANLIST
    # Buscamos la linea que contiene rx: /\bbalcarce
    lineas = code.splitlines()
    nuevas_lineas = []
    eliminado = False
    for l in lineas:
        if "balcarce" in l.lower() and "rx:" in l:
            eliminado = True
            continue # Salteamos la linea del baneo de Balcarce 37
        nuevas_lineas.append(l)
    
    if not eliminado:
        sys.exit("ERROR: No se encontró la regla de baneo de Balcarce 37 en Banlist Validator.")
    
    despues = "\n".join(nuevas_lineas)
    nodo["parameters"]["jsCode"] = despues
    return wf, antes, despues

def verify(wf):
    nodo = next((n for n in wf["nodes"] if n["name"] == NODO), None)
    code = nodo["parameters"]["jsCode"]
    # Verificar que las reglas de 'venite' sigan vivas pero que NO exista la regla de baneo de Balcarce
    tiene_venite = "venite" in code.lower() or "venga" in code.lower()
    tiene_balcarce_en_banlist = any("balcarce" in l.lower() and "rx:" in l for l in code.splitlines())
    return {
        "nodo_presente": nodo is not None,
        "banlist_venite_intacto": tiene_venite,
        "balcarce_eliminado_de_banlist": not tiene_balcarce_en_banlist
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    wf = api(f"/workflows/{WF_ID}")
    version = wf.get("versionId")
    total_nodos = len(wf["nodes"])
    print(f"Workflow vivo v6: {total_nodos} nodos, activo={wf['active']}, versionId={version}")

    wf, antes, despues = build(wf)
    
    print(f"\n── {NODO} · Eliminando regla de baneo de Balcarce 37 ──")
    print(f"Líneas antes: {len(antes.splitlines())} -> después: {len(despues.splitlines())}")

    v_pre = verify(wf)
    print(json.dumps(v_pre, indent=2, ensure_ascii=False))
    if not all(v_pre.values()):
        sys.exit("ERROR: La verificación previa falló.")

    if not args.apply:
        print("\n[DRY-RUN] Todo verificado. Ejecutá con --apply para aplicar a producción.")
        return 0

    ts = time.strftime("%Y%m%d_%H%M%S")
    actual = api(f"/workflows/{WF_ID}")
    if actual.get("versionId") != version:
        sys.exit("ERROR: El workflow en n8n cambió entre el GET y el PUT. Abortando por seguridad.")

    # Guardar snapshot PRE
    (HIST / f"v6_PRE_{LABEL}_{ts}.json").write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")

    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = clean_settings(wf)
    wh = next(n for n in body["nodes"] if n["name"] == WEBHOOK)
    assert wh.get("webhookId") == "evo-webhook-v2", "webhookId perdido — abortando para proteger webhook"

    api(f"/workflows/{WF_ID}", method="PUT", payload=body)

    after = api(f"/workflows/{WF_ID}")
    # Guardar snapshot POST
    (HIST / f"v6_POST_{LABEL}_{ts}.json").write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")

    v_post = verify(after)
    print("\n── Verificación post-PUT en vivo ──")
    print(json.dumps(v_post, indent=2, ensure_ascii=False))
    if not all(v_post.values()) or len(after["nodes"]) != total_nodos:
        sys.exit("ERROR: Verificación post-PUT no cumplió los requisitos.")

    print("\n✅ ¡APLICADO CON ÉXITO EN PRODUCCIÓN!")
    print(f"Backup PRE guardado en: workflows/history/v6_PRE_{LABEL}_{ts}.json")
    print(f"Backup POST guardado en: workflows/history/v6_POST_{LABEL}_{ts}.json")
    return 0

if __name__ == "__main__":
    sys.exit(main())
