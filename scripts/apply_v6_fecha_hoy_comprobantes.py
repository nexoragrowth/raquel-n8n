# -*- coding: utf-8 -*-
"""
apply_v6_fecha_hoy_comprobantes.py — 2026-10-20 · el nodo "OpenAI - Analizar Imagen" del v6 (lee las fotos de comprobantes antes de que las vea el
v6 o el v7) tiene la regla "si la fecha NO es de hoy o ayer, marcala (COMPROBANTE VIEJO)", pero nunca le dice al modelo qué día es hoy: adivina.

CASO REAL: escalación 387 (20/10 16:16): transferencia de $80.000 del 20/10/2026 a las 15:02 → "FECHA: 20/10/2026 (COMPROBANTE VIEJO)". El aviso
llega así al grupo y la secretaria puede dudar de un pago real.

QUÉ CAMBIA (solo ese nodo, solo el parámetro `text`): se convierte en expresión de n8n (prefijo "=") y antes de la regla de la fecha se agrega
"- Hoy es {{ fecha de hoy en Argentina }} (hora de Argentina). Hoy y ayer NO son comprobante viejo." con Luxon ($now.setZone('America/Argentina/Jujuy')).
Antes de convertir verifica que el texto no tenga "{{" ni "}}" propios (n8n los evaluaría).

USO:  python scripts/apply_v6_fecha_hoy_comprobantes.py [--apply]
"""
import argparse, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flag_v7 import api

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
V6 = "O155MqHgOSaNZ9ye"
NODO = "OpenAI - Analizar Imagen"
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution", "executionTimeout",
               "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
ANCLA = "- Si la fecha NO es de hoy o ayer (maximo 48hs)"
HOY = "- Hoy es {{ $now.setZone('America/Argentina/Jujuy').toFormat('dd/MM/yyyy') }} (hora de Argentina). Una fecha de hoy o de ayer NO es comprobante viejo.\n"
MARCA = "Hoy es {{ $now.setZone('America/Argentina/Jujuy')"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); a = ap.parse_args()
    w = api(f"/workflows/{V6}")
    n = next((x for x in w["nodes"] if x["name"] == NODO), None)
    if not n: raise SystemExit(f"No encontré «{NODO}».")
    t = n["parameters"].get("text", "")
    if MARCA in t: raise SystemExit("Ya está aplicado.")
    if t.startswith("="): raise SystemExit("El texto ya es una expresión: revisar a mano antes de tocarlo.")
    if "{{" in t or "}}" in t: raise SystemExit("El texto trae llaves {{ }} propias: convertirlo en expresión las evaluaría. No toco nada.")
    if t.count(ANCLA) != 1: raise SystemExit("La regla de la fecha no aparece exactamente 1 vez: no toco nada.")
    nuevo = "=" + t.replace(ANCLA, HOY + ANCLA)
    print(f"v6 versionId {w.get('versionId')} · «{NODO}»: se agrega antes de la regla de la fecha:\n  {HOY.strip()}")
    if not a.apply: print("[SIMULACIÓN] Para aplicar: --apply"); return
    print("check_triaje (regla del proyecto: antes de cualquier PUT al v6)")
    if subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], cwd=ROOT).returncode != 0:
        raise SystemExit("ABORTO: check_triaje no dio sano. No se tocó nada.")
    if api(f"/workflows/{V6}").get("versionId") != w.get("versionId"): raise SystemExit("El v6 cambió mientras tanto: no hago PUT.")
    if not any(x.get("webhookId") == "evo-webhook-v2" for x in w["nodes"]): raise SystemExit("Falta webhookId evo-webhook-v2: no hago PUT.")
    ts = int(time.time()); hist = ROOT / "workflows" / "history"; hist.mkdir(parents=True, exist_ok=True)
    (hist / f"{V6}_PRE_fecha_hoy_comprobantes_{ts}.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
    n["parameters"]["text"] = nuevo
    api(f"/workflows/{V6}", "PUT", {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
                                     "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in SETTINGS_OK}, "staticData": w.get("staticData")})
    post = api(f"/workflows/{V6}")
    (hist / f"{V6}_POST_fecha_hoy_comprobantes_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    t2 = next(x for x in post["nodes"] if x["name"] == NODO)["parameters"]["text"]
    ok = t2 == nuevo and len(post["nodes"]) == len(w["nodes"]) and post.get("active") is True and any(x.get("webhookId") == "evo-webhook-v2" for x in post["nodes"])
    print(("OK" if ok else "ATENCIÓN") + f": versionId {post.get('versionId')} · nodos {len(post['nodes'])} · activo {post.get('active')} · backups _{ts}")


if __name__ == "__main__":
    main()
