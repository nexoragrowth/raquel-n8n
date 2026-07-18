"""
Fix critico al Sub-Agent Agendar: el prompt usa el celular de Carmen Agostini
(5493886869400) como EJEMPLO de formato en los pasos 2a/2b/2d. Cuando el LLM
no tiene el celular del paciente real, agarra ese ejemplo literal y lo usa,
revelando el nombre de Carmen al paciente que escribe.

Caso confirmado en E2E (2026-05-21):
  IN:  "Hola, querria un turno para primera consulta para el jueves 18..."
  -> LLM llama buscar_paciente_dentalink(celular=5493886869400)
  -> Dentalink devuelve Maria del Carmen Agostini (id=609)
  -> bot responde "Veo su registro como Maria del Carmen Agostini" al paciente.

Fixes:
  1) Reemplazar el celular real por placeholders sinteticos.
  2) Agregar guard antes del PASO 2: NUNCA inventar celular, NUNCA usar el
     del ejemplo. El celular viene del `phone` del webhook.
"""
import json
import os
import re
import sys
import time
import urllib.request

WF_ID = "O155MqHgOSaNZ9ye"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
DRY_RUN = "--dry-run" in sys.argv

API_KEY = os.environ.get("N8N_API_KEY")
if not API_KEY:
    fb = "C:/Users/Lucas/.claude/n8n_backups/test_100_pre_prod.py"
    if os.path.exists(fb):
        with open(fb, encoding="utf-8") as f:
            m = re.search(r'API_KEY\s*=\s*"([^"]+)"', f.read())
            if m:
                API_KEY = m.group(1)
if not API_KEY:
    sys.exit("ERROR: N8N_API_KEY")

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}

# === Reemplazos del celular hardcodeado ===
REPLACEMENTS = [
    # (old, new)
    ("`5493886869400`", "el `phone` del paciente, formato `549XXXXXXXXXX` (13 digitos con prefijo 549)"),
    ("`+543886869400`", "el `phone` sin el 9 movil, formato `+54XXXXXXXXXX`"),
    ("`543886869400`", "el `phone` sin '+', formato `54XXXXXXXXXX`"),
    ("`3886869400`", "el `phone` sin codigo pais, 10 digitos"),
]

# === Guard a insertar antes del PASO 2 ===
# IMPORTANTE: NO incluir ningun numero real en el texto del guard (el LLM
# puede usarlo como dato literal). Solo placeholders.
GUARD_BLOCK = """GUARD CRITICO ANTES DE BUSCAR — El celular del paciente viene SIEMPRE del campo `phone` de los datos del webhook (esta en la conversacion como contexto del paciente). Si no tenes ese phone (caso raro), PIDISELO antes de llamar `buscar_paciente_dentalink`. NUNCA inventes un celular, NUNCA uses el numero de un ejemplo o placeholder como si fuera del paciente real. Llamar la tool con un celular inventado leakea datos de OTRO paciente real (bug grave de privacidad).

"""

GUARD_MARKER = "GUARD CRITICO ANTES DE BUSCAR"
INSERT_BEFORE = "PASO 2 — BUSQUEDA"


def http(method, path, body=None):
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        method=method,
        headers={
            "X-N8N-API-KEY": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        data=json.dumps(body).encode() if body else None,
    )
    with urllib.request.urlopen(req) as r:
        return r.status, json.loads(r.read())


def filter_settings(s):
    return {k: v for k, v in (s or {}).items() if k in ALLOWED_SETTINGS}


def strip_meta(wf):
    for k in ("id", "active", "createdAt", "updatedAt", "tags", "versionId", "triggerCount",
              "meta", "isArchived", "shared", "homeProject", "sharedWithProjects", "scopes",
              "description", "pinData", "activeVersionId", "versionCounter", "activeVersion"):
        wf.pop(k, None)
    wf["settings"] = filter_settings(wf.get("settings"))
    return wf


def main():
    print("Pulling current v6...")
    _, wf = http("GET", f"/workflows/{WF_ID}")

    os.makedirs("workflows/history", exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    pre_path = f"workflows/history/v6_PRE_FIX_AGENDAR_LEAK_{stamp}.json"
    with open(pre_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup pre: {pre_path}")

    node = next((n for n in wf["nodes"] if n["name"] == "Sub-Agent Agendar"), None)
    if not node:
        sys.exit("ERROR: nodo 'Sub-Agent Agendar' no existe")

    sm = node["parameters"].get("options", {}).get("systemMessage", "")
    if not sm:
        sys.exit("ERROR: systemMessage vacio")

    # Aplicar reemplazos
    changes = []
    new_sm = sm
    for old, new in REPLACEMENTS:
        cnt = new_sm.count(old)
        if cnt:
            new_sm = new_sm.replace(old, new)
            changes.append((old, new, cnt))

    # Si el GUARD ya fue insertado previamente con la version vieja que tenia
    # el numero adentro, lo reescribimos.
    if "GUARD CRITICO ANTES DE BUSCAR" in new_sm:
        idx = new_sm.find("GUARD CRITICO ANTES DE BUSCAR")
        end_idx = new_sm.find("PASO 2 — BUSQUEDA", idx)
        if idx >= 0 and end_idx > idx:
            old_guard = new_sm[idx:end_idx]
            if old_guard.strip() != GUARD_BLOCK.strip():
                new_sm = new_sm[:idx] + GUARD_BLOCK + new_sm[end_idx:]
                changes.append(("(rewrite GUARD)", GUARD_MARKER, 1))
            else:
                print("  GUARD ya presente y limpio, skip.")
    else:
        if INSERT_BEFORE not in new_sm:
            sys.exit(f"ERROR: no encontre marcador '{INSERT_BEFORE}' en prompt")
        new_sm = new_sm.replace(INSERT_BEFORE, GUARD_BLOCK + INSERT_BEFORE, 1)
        changes.append(("(insert)", GUARD_MARKER, 1))

    # Verificar AHORA que el prompt final no tiene numeros hardcoded
    forbidden = ["5493886869400", "543886869400", "3886869400"]
    leftover = [f for f in forbidden if f in new_sm]
    if leftover:
        sys.exit(f"ERROR: numeros leftover despues de cambios: {leftover}")

    if new_sm == sm:
        print("  Nada que cambiar. Salida.")
        return

    node["parameters"]["options"]["systemMessage"] = new_sm

    print(f"\nCambios:")
    for old, new, cnt in changes:
        print(f"  -{old[:60]}{'...' if len(old)>60 else ''}  (x{cnt})")
        print(f"  +{new[:60]}{'...' if len(new)>60 else ''}")

    if DRY_RUN:
        dry = f"workflows/history/v6_FIX_AGENDAR_LEAK_DRY_{stamp}.json"
        with open(dry, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"\nDRY RUN -> {dry}")
        return

    payload = strip_meta(dict(wf))
    print("\nApplying PUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  PUT: {status}")

    post_path = f"workflows/history/v6_POST_FIX_AGENDAR_LEAK_{stamp}.json"
    _, post_wf = http("GET", f"/workflows/{WF_ID}")
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(post_wf, f, ensure_ascii=False, indent=2)

    # Verificacion
    post_node = next((n for n in post_wf["nodes"] if n["name"] == "Sub-Agent Agendar"), None)
    post_sm = post_node["parameters"]["options"]["systemMessage"]
    leftover_post = [f for f in forbidden if f in post_sm]
    has_guard = GUARD_MARKER in post_sm
    if leftover_post or not has_guard:
        sys.exit(f"ERROR post: leftover={leftover_post} guard={has_guard}")
    print(f"  backup post: {post_path}")
    print("  OK: fix aplicado y verificado.")


if __name__ == "__main__":
    main()
