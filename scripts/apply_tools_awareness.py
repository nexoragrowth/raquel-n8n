"""
Tools awareness — 3 cambios complementarios para que el LLM use mejor sus
herramientas durante el cutover. NO toca el flag `disabled` de los nodos
(las tools de escritura siguen disabled en shadow).

Cambios:
1) Llenar 4 toolDescription vacias:
   - ver_profesionales
   - reservar_turno
   - cancelar_turno
   - crear_paciente_dentalink

2) Agregar bloque "TOOLS DISPONIBLES" al inicio del bloque especifico de
   Confirmar / Cancelar / Agendar.

3) Agregar bloque "SUB-AGENTS DISPONIBLES Y SUS RESPONSABILIDADES" al Router
   para que clasifique con contexto de QUE puede hacer cada sub-agent.
"""
import json
import os
import sys
import time
import urllib.request

WF_ID = "O155MqHgOSaNZ9ye"
API_BASE = "https://n8n.raquelrodriguez.com.ar/api/v1"
API_KEY = os.environ.get("N8N_API_KEY")
DRY_RUN = "--dry-run" in sys.argv

if not API_KEY:
    sys.exit("ERROR: N8N_API_KEY")

ALLOWED_SETTINGS = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow",
    "timezone", "executionOrder", "callerPolicy", "callerIds",
}

# === 1) TOOL DESCRIPTIONS NUEVAS ===
NEW_DESCRIPTIONS = {
    "ver_profesionales": (
        "Lista los profesionales (dentistas) activos en Dentalink de la clinica. "
        "No requiere parametros. Devuelve array con id, nombre, especialidad. "
        "Usar cuando necesites el id_dentista para pasarselo a buscar_horarios o "
        "reservar_turno, o cuando el paciente mencione un profesional distinto a "
        "la Dra. Raquel. Para la Dra. Raquel el id habitual es 1 (verificar igual)."
    ),
    "reservar_turno": (
        "Reserva un turno en Dentalink (POST /citas). Body requerido (JSON): "
        "{\"id_sucursal\":1, \"id_dentista\":<number>, \"id_paciente\":<number>, "
        "\"fecha\":\"YYYY-MM-DD\", \"hora_inicio\":\"HH:MM\", \"duracion\":\"40\", "
        "\"id_estado\":2, \"nota\":\"Reservado por bot WhatsApp\"}. "
        "Llamar SOLO despues de read-back confirmado por el paciente. Idempotencia "
        "estricta: nunca reservar 2 veces el mismo turno en el mismo turno LLM. "
        "Si Dentalink retorna 400 verificar disponibilidad con buscar_horarios primero."
    ),
    "cancelar_turno": (
        "Anula un turno en Dentalink (PUT /citas/{id}). LECCION CRITICA: el body "
        "SOLO acepta {\"id_estado\": 1}. Cualquier otro parametro extra (ej "
        "comentario_anulacion) devuelve HTTP 400 \"Parametro X no existe\". "
        "Confirmar el id_cita exacto antes de llamar (con ver_turnos_paciente "
        "o desde la NOTA INTERNA del recordatorio). Una sola llamada por turno: "
        "si falla 2 veces, escalar."
    ),
    "crear_paciente_dentalink": (
        "Crea un paciente nuevo en Dentalink (POST /pacientes). SOLO usar despues "
        "de que buscar_paciente_dentalink fallo con las 5 variantes de celular "
        "+ fallback por apellido. Body requerido (JSON): "
        "{\"nombre\":\"<nombre>\", \"apellidos\":\"<apellido>\", "
        "\"celular\":\"<phone limpio, formato 549XXXXXXXXXX>\", "
        "\"documento\":\"<DNI>\", \"id_sucursal\":1}. NUNCA crear sin DNI "
        "confirmado por el paciente. Riesgo de duplicado (lecccion del caso "
        "Carmen Agostini id=413 vs id=609)."
    ),
}

# === 2) BLOQUE "TOOLS DISPONIBLES" PARA SUB-AGENTS ===
TOOLS_BLOCKS = {
    "Sub-Agent Confirmar": (
        "\n\n= TOOLS DISPONIBLES =\n"
        "- `ver_turnos_paciente`: chequear id_estado del turno (idempotencia).\n"
        "- `confirmar_turno`: marcar id_estado=18 (Confirmado por WhatsApp). Solo despues de PASO 2.\n"
        "- `escalar_a_secretaria`: derivar a Iri (comprobante, ya anulado, sin contexto, fallas).\n"
    ),
    "Sub-Agent Cancelar": (
        "\n\n= TOOLS DISPONIBLES =\n"
        "- `ver_turnos_paciente`: localizar el turno activo a cancelar.\n"
        "- `cancelar_turno`: anular con {id_estado:1}. SOLO despues de read-back del paciente.\n"
        "- `escalar_a_secretaria`: derivar a Iri si no encuentra turno o si tools fallan.\n"
    ),
    "Sub-Agent Agendar": (
        "\n\n= TOOLS DISPONIBLES =\n"
        "- `buscar_paciente_dentalink`: buscar paciente por phone (5 variantes) o apellido. SIEMPRE primero.\n"
        "- `crear_paciente_dentalink`: solo si las busquedas fallaron Y tenes DNI confirmado.\n"
        "- `ver_profesionales`: obtener id_dentista (1 = Dra. Raquel).\n"
        "- `buscar_horarios`: disponibilidad para una fecha.\n"
        "- `ver_turnos_paciente`: chequear doble-booking antes de reservar.\n"
        "- `reservar_turno`: PRE-reservar el turno. SOLO despues de read-back y confirmacion del paciente.\n"
        "- `escalar_a_secretaria`: caso fuera de scope, fallo tools, paciente problema.\n"
    ),
}

TOOLS_MARKER = "= TOOLS DISPONIBLES ="

# === 3) BLOQUE DE SUB-AGENTS PARA ROUTER ===
ROUTER_SUBAGENTS_BLOCK = """

---

SUB-AGENTS DISPONIBLES Y SUS RESPONSABILIDADES:

Cada intent que devolves se rutea a un sub-agent. Saber QUE puede hacer cada uno te ayuda a clasificar mejor.

- `confirmar_post_recordatorio` -> Sub-Agent Confirmar
  Hace: confirmar turnos (tras recordatorio). Tools Dentalink: ver_turnos_paciente, confirmar_turno.
  Detecta comprobantes y escala. Output: canned tras exito, o escalar.

- `cancelar_o_reprogramar` -> Sub-Agent Cancelar
  Hace: cancelar turnos con read-back. Tools: ver_turnos_paciente, cancelar_turno.
  Si quiere reprogramar, deriva a Agendar en proximo turno. Output: canned o escalar.

- `agendar_nuevo` -> Sub-Agent Agendar
  Hace: busqueda exhaustiva de paciente (5 variantes phone + apellido), crear si nuevo,
  buscar horarios, reservar. Tools: 6 de Dentalink. Output: turno PRE-reservado + mensaje pago.

- `urgencia_dolor` -> Sub-Agent Urgencia
  Hace: UNICAMENTE escalar. Prohibido dar consejos, recomendar medicacion, diagnosticar.
  Tool: escalar_a_secretaria. Output: canned escalacion.

- `consulta_general` -> Sub-Agent General
  Hace: info canned (precio/horario/direccion/alias), FAQ via Vector Store
  (23 docs sobre tratamientos/pagos/clinica), o escalar.
  Tools: buscar_conocimiento (KB), escalar_a_secretaria.

Tu decision de routing afecta que tools y conocimiento estan disponibles para responder
al paciente. Si dudas entre consulta_general y otro intent operativo claro -> elegi consulta_general.
"""

ROUTER_SUBAGENTS_MARKER = "SUB-AGENTS DISPONIBLES Y SUS RESPONSABILIDADES"


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


def main():
    print(f"GET workflow {WF_ID}...")
    _, wf = http("GET", f"/workflows/{WF_ID}")
    print(f"  active={wf['active']} nodes={len(wf['nodes'])}")

    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    backup_path = f"workflows/history/v6_PRE_TOOLS_AWARENESS_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    # === 1. Llenar toolDescription ===
    print("\n=== 1. Llenar toolDescription vacias ===")
    filled = 0
    for n in wf["nodes"]:
        if n["name"] in NEW_DESCRIPTIONS:
            cur = n["parameters"].get("toolDescription") or n["parameters"].get("description") or ""
            if len(cur) > 50:
                print(f"  SKIP {n['name']} (ya tiene {len(cur)} chars)")
                continue
            n["parameters"]["toolDescription"] = NEW_DESCRIPTIONS[n["name"]]
            filled += 1
            print(f"  + {n['name']}: {len(NEW_DESCRIPTIONS[n['name']])} chars")
    print(f"  total: {filled} descriptions agregadas")

    # === 2. Bloque TOOLS DISPONIBLES en sub-agents ===
    print("\n=== 2. Bloque TOOLS DISPONIBLES en sub-agents ===")
    for name, block in TOOLS_BLOCKS.items():
        node = next((n for n in wf["nodes"] if n["name"] == name), None)
        if not node:
            print(f"  WARN: {name} no encontrado")
            continue
        sm = node["parameters"].get("options", {}).get("systemMessage", "")
        if TOOLS_MARKER in sm:
            print(f"  SKIP {name} (ya tiene el bloque)")
            continue
        # Insertar despues del header "= TU FUNCION ESPECIFICA"
        marker = "= TU FUNCION ESPECIFICA"
        idx = sm.find(marker)
        if idx < 0:
            print(f"  WARN {name}: no encontre marker {marker!r}")
            continue
        # Encontrar fin de la linea del marker
        end_line = sm.find("\n", idx)
        new_sm = sm[: end_line + 1] + block + sm[end_line + 1 :]
        node["parameters"]["options"]["systemMessage"] = new_sm
        print(f"  + {name}: {len(sm)} -> {len(new_sm)} chars")

    # === 3. Bloque SUB-AGENTS para Router ===
    print("\n=== 3. Bloque SUB-AGENTS en Router ===")
    router = next((n for n in wf["nodes"] if n["name"] == "Router - Clasificar Intent"), None)
    if router:
        sm = router["parameters"].get("options", {}).get("systemMessage", "")
        if ROUTER_SUBAGENTS_MARKER in sm:
            print(f"  SKIP (ya tiene el bloque)")
        else:
            new_sm = sm.rstrip() + ROUTER_SUBAGENTS_BLOCK
            router["parameters"]["options"]["systemMessage"] = new_sm
            print(f"  + Router: {len(sm)} -> {len(new_sm)} chars")
    else:
        print("  WARN: Router - Clasificar Intent no encontrado")

    if DRY_RUN:
        out = f"workflows/history/v6_TOOLS_AWARENESS_DRY_{ts}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"\nDRY RUN -> {out}")
        return

    settings = {k: v for k, v in wf.get("settings", {}).items() if k in ALLOWED_SETTINGS}
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": settings,
        "staticData": wf.get("staticData"),
    }
    print("\nPUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  status={status}")

    _, wf2 = http("GET", f"/workflows/{WF_ID}")
    print(f"  active={wf2['active']} nodes={len(wf2['nodes'])}")
    # Verify
    for tool_name in NEW_DESCRIPTIONS:
        n = next((x for x in wf2["nodes"] if x["name"] == tool_name), None)
        if n:
            d = n["parameters"].get("toolDescription") or ""
            assert len(d) > 50, f"FAIL: {tool_name} description vacia post-PUT"
    print("  verified all 4 toolDescription filled")

    post_path = f"workflows/history/v6_POST_TOOLS_AWARENESS_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
