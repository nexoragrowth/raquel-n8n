# -*- coding: utf-8 -*-
"""
apply_v6_confirmar_con_alias.py — 2026-10-19 · el "Sub-Agent Confirmar" del v6 pasa los datos para transferir cuando el paciente, en el
mismo mensaje en que confirma, pregunta cómo pagar o pide el alias (antes derivaba a la secretaria aunque el dato está cargado).

CASO REAL: 19/10 17:03, "Emma está yendo solo. Puedo abonar con transferencia?" → el v6 confirmó el turno y derivó lo del pago
(escalación 375); la secretaria tuvo que mandar el alias a mano 3 min después. Es el límite del v6 (un asistente por mensaje); el v7 lo
resuelve con el coordinador. Mientras el v6 atienda (hasta el 16/11), este parche cubre el caso más común.

QUÉ CAMBIA: solo el systemMessage de "Sub-Agent Confirmar": se agrega un bloque "DATOS PARA TRANSFERIR" (los mismos campos dinámicos de
"Extraer Horarios y Precio" que ya usa el Sub-Agent General) con la regla de pasarlos en la misma respuesta, después de la confirmación.
Los comprobantes siguen yendo a la secretaria (no se valida ningún pago). Formas de pago: efectivo y transferencia (decisión de la Dra. 16/10).

USO:  python scripts/apply_v6_confirmar_con_alias.py [--apply]
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flag_v7 import api

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
V6 = "O155MqHgOSaNZ9ye"
NODO = "Sub-Agent Confirmar"
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution", "executionTimeout",
               "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
ANCLA = "PASO 0 — COMPROBANTES DE PAGO:"
X = "$('Extraer Horarios y Precio').item.json"
BLOQUE = f"""DATOS PARA TRANSFERIR (19/10): si en el MISMO mensaje el paciente pregunta cómo pagar, si puede transferir o pide el alias, después de resolver la confirmación agregá en la misma respuesta, sin derivar a la secretaria por eso:
"Puede abonar en efectivo o por transferencia. Datos para transferir:
Alias: {{{{ {X}.pago_alias }}}}
Titular: {{{{ {X}.pago_titular }}}}
CUIT/CUIL: {{{{ {X}.pago_cuit }}}}
CBU: {{{{ {X}.pago_cbu }}}}
Banco: {{{{ {X}.pago_banco }}}}
Si transfiere, nos envía el comprobante por este medio, por favor."
No informes montos de tratamientos, cuotas ni retenedores (solo la secretaria). Los comprobantes siguen el PASO 0.

"""


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); a = ap.parse_args()
    w = api(f"/workflows/{V6}")
    n = next((x for x in w["nodes"] if x["name"] == NODO), None)
    if not n: raise SystemExit(f"No encontré «{NODO}».")
    sm = n["parameters"]["options"]["systemMessage"]
    if "DATOS PARA TRANSFERIR (19/10)" in sm: raise SystemExit("Ya está aplicado.")
    if sm.count(ANCLA) != 1: raise SystemExit("El ancla del PASO 0 no aparece exactamente 1 vez: no toco nada.")
    for campo in ("pago_alias", "pago_titular", "pago_cuit", "pago_cbu", "pago_banco"):
        ext = next(x for x in w["nodes"] if x["name"] == "Extraer Horarios y Precio")
        if campo not in json.dumps(ext["parameters"]): raise SystemExit(f"«Extraer Horarios y Precio» no arma {campo}: no toco nada.")
    print(f"v6 versionId {w.get('versionId')} · se agrega el bloque de datos para transferir a «{NODO}» antes del PASO 0.\n" + BLOQUE)
    if not a.apply: print("[SIMULACIÓN] Para aplicar: --apply"); return
    ts = int(time.time()); hist = ROOT / "workflows" / "history"; hist.mkdir(parents=True, exist_ok=True)
    (hist / f"{V6}_PRE_confirmar_con_alias_{ts}.json").write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
    n["parameters"]["options"]["systemMessage"] = sm.replace(ANCLA, BLOQUE + ANCLA)
    if not any(x.get("webhookId") == "evo-webhook-v2" for x in w["nodes"]): raise SystemExit("Falta webhookId evo-webhook-v2: no hago PUT.")
    if api(f"/workflows/{V6}").get("versionId") != w.get("versionId"): raise SystemExit("El v6 cambió mientras tanto: no hago PUT.")
    api(f"/workflows/{V6}", "PUT", {"name": w["name"], "nodes": w["nodes"], "connections": w["connections"],
                                     "settings": {k: v for k, v in (w.get("settings") or {}).items() if k in SETTINGS_OK}, "staticData": w.get("staticData")})
    post = api(f"/workflows/{V6}")
    (hist / f"{V6}_POST_confirmar_con_alias_{ts}.json").write_text(json.dumps(post, ensure_ascii=False, indent=1), encoding="utf-8")
    sm2 = next(x for x in post["nodes"] if x["name"] == NODO)["parameters"]["options"]["systemMessage"]
    ok = "DATOS PARA TRANSFERIR (19/10)" in sm2 and len(post["nodes"]) == len(w["nodes"]) and post.get("active") is True and any(x.get("webhookId") == "evo-webhook-v2" for x in post["nodes"])
    print(("OK" if ok else "ATENCIÓN") + f": versionId {post.get('versionId')} · nodos {len(post['nodes'])} · activo {post.get('active')} · backups _{ts}")


if __name__ == "__main__":
    main()
