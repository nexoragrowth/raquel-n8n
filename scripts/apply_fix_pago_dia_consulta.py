# -*- coding: utf-8 -*-
"""
apply_fix_pago_dia_consulta.py — pedido REAL de la Dra. Raquel (19/8, WhatsApp a
Lucas): "Esto necesito que lo cambiemos por favor, cuando digan si pueden
abonar el día de la consulta hay que decirles 'Nosotros le enviamos un
recordatorio de su turno dos días hábiles antes, y para confirmar su
asistencia le solicitaremos abonar el valor de la consulta. Puede acercarce al
consultorio a abonar en efectivo o hacer una transferencia, cómo le resulte
más cómodo 😊.' Porque sino algunos no pagan y tampoco vienen."

Hoy, si el paciente pregunta especificamente si puede pagar el mismo dia / al
llegar / en el momento de la consulta, el bot cae en el canned generico de
"Alias / forma de pago" (Sub-Agent General) que solo dice "tambien aceptamos
efectivo en clinica" -- sin la logica de que el pago se pide DESPUES del
recordatorio, para asegurar que venga. Eso es justo lo que la Dra quiere
cambiar: el bot no debe sonar como si "pagar el dia de la consulta sin mas"
fuera la respuesta por defecto.

FIX: agregar un canned especifico (texto EXACTO de la Dra) para cuando la
pregunta es puntualmente sobre pagar el dia/al llegar/en el momento, ANTES del
canned generico de alias (que sigue existiendo para cuando piden el alias
directamente o ya estan en flow de PRE-reserva).

USO:
    python scripts/apply_fix_pago_dia_consulta.py            # preview
    python scripts/apply_fix_pago_dia_consulta.py --apply    # aplica

Regla del proyecto: NUNCA --apply sin OK explicito de Lucas + backup previo.
"""
import argparse
import copy
import difflib
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""
WF = os.environ.get("N8N_WF_BOT", "O155MqHgOSaNZ9ye")

PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}

NODE = "Sub-Agent General"

ANCLA = (
    '- **Alias / forma de pago** (cuando el paciente pide el alias, o cuando vos '
    "lo mencionas en flow de PRE-reserva): NUNCA mandes el alias solo y crudo."
)

NUEVO_BLOQUE = (
    "- **¿Puedo pagar el día de la consulta / al llegar / en el momento?** "
    "(NUEVO 2026-08-21, pedido Dra — evita que el paciente crea que puede pagar "
    "recien al llegar y despues falte sin avisar): si el paciente pregunta "
    "ESPECIFICAMENTE si puede pagar el mismo día, al llegar, o en el momento de "
    "la consulta (ANTES de tener turno reservado, o como pregunta suelta) -> "
    "responder LITERAL, SIN mencionar el alias todavia en esta respuesta:\n"
    '"Nosotros le enviamos un recordatorio de su turno dos días hábiles antes, '
    "y para confirmar su asistencia le solicitaremos abonar el valor de la "
    "consulta. Puede acercarse al consultorio a abonar en efectivo o hacer una "
    'transferencia, cómo le resulte más cómodo 😊."\n'
    "Esta respuesta reemplaza el canned generico de alias en este caso puntual "
    "— el alias/CBU se dan recien cuando el paciente ya tiene turno reservado o "
    "los pide explicitamente (ver bullet siguiente).\n\n"
    + ANCLA
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


def clean_settings(wf):
    s = wf.get("settings") or {}
    return {k: v for k, v in s.items() if k in SETTINGS_OK}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    print(f"GET workflow {WF} …")
    wf = api("GET", f"/workflows/{WF}")
    print(f"  {wf['name']} — {len(wf['nodes'])} nodos, activo={wf['active']}")
    wf_orig = copy.deepcopy(wf)

    n = next((x for x in wf["nodes"] if x["name"] == NODE), None)
    if not n:
        sys.exit(f"!! No encontré el nodo '{NODE}'.")
    opts = n["parameters"].get("options", {})
    old_sm = opts.get("systemMessage", n["parameters"].get("systemMessage", ""))

    count = old_sm.count(ANCLA)
    if count != 1:
        sys.exit(f"!! El ancla aparece {count} veces (esperaba 1), revisar a mano.")
    if "pagar el día de la consulta / al llegar" in old_sm:
        print(f"\n[{NODE}] ya tiene el fix.")
        return

    new_sm = old_sm.replace(ANCLA, NUEVO_BLOQUE, 1)

    print(f"\n=== DIFF: {NODE} (systemMessage) ===")
    for line in difflib.unified_diff(
        old_sm.splitlines(), new_sm.splitlines(), fromfile="ANTES", tofile="DESPUES", lineterm=""
    ):
        if line.startswith(("+", "-")):
            print(line[:220])

    if "options" in n["parameters"]:
        n["parameters"]["options"]["systemMessage"] = new_sm
    else:
        n["parameters"]["systemMessage"] = new_sm

    if not args.apply:
        print("\n(preview — no se tocó n8n). Para aplicar: --apply")
        return

    os.makedirs("workflows/history", exist_ok=True)
    pre = "workflows/history/v6_PRE_fix_pago_dia_consulta.json"
    json.dump(wf_orig, open(pre, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nbackup PRE -> {pre}")

    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = clean_settings(wf)
    print("PUT …")
    api("PUT", f"/workflows/{WF}", body)

    vivo = api("GET", f"/workflows/{WF}")
    post = "workflows/history/v6_POST_fix_pago_dia_consulta.json"
    json.dump(vivo, open(post, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"backup POST -> {post}")

    n2 = next((x for x in vivo["nodes"] if x["name"] == NODE), None)
    opts2 = n2["parameters"].get("options", {}) if n2 else {}
    sm2 = opts2.get("systemMessage", n2["parameters"].get("systemMessage", "") if n2 else "")
    ok = "pagar el día de la consulta / al llegar" in sm2
    print(f"\n[{NODE}]  {'OK ✅' if ok else '!! NO COINCIDE'}")


if __name__ == "__main__":
    main()
