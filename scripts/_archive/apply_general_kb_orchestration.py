"""
Reordena el prompt del Sub-Agent General para que el LLM use el Vector Store
`buscar_conocimiento` correctamente.

Cambios en el bloque "= TU FUNCION ESPECIFICA":
  1. Mover ORDEN DE DECISION al PRINCIPIO (antes de INFO CANNED).
  2. Agregar descripcion explicita de la KB (que hay adentro).
  3. Aclarar item de tratamientos: PRIMERO buscar_conocimiento, despues
     decidir responder o escalar.
  4. Separar ESCALAR DIRECTO (sin KB) de ESCALAR POST-KB.

El bloque comun (R0, IDENTIFICACION, MEMORIA, etc.) NO se toca.
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

SPLIT_MARKER = "= TU FUNCION ESPECIFICA: INFO CANNED o ESCALAR ="

NEW_SPECIFIC_BLOCK = """= TU FUNCION ESPECIFICA: INFO CANNED + KB o ESCALAR =

Tenes una tool **`buscar_conocimiento`** (Vector Store sobre la BD de la clinica) con 23 docs curados:
- FAQ pacientes: edad primera consulta, dolor brackets, deporte con brackets, faltar a turno, alineadores vs brackets, ninos, documentacion
- Tratamientos: Invisalign, ASIRI, Keep Smiling, brackets metalicos, brackets zafiro, ortopedia facial, consulta inicial, control de retencion
- Pagos: medios aceptados, politica de sena obligatoria
- Horarios y secretaria
- Info general clinica/doctora

**ORDEN DE DECISION (seguir SIEMPRE, en este orden):**

1. ¿La pregunta encaja DIRECTAMENTE en INFO CANNED de abajo? -> responder LITERAL del canned. NO llames la KB.

2. ¿Es queja / hostilidad / pedido humano / factura / disponibilidad especifica / otra cosa de "ESCALAR DIRECTO"? -> `escalar_a_secretaria` con canned. NO consultes la KB.

3. ¿Es pregunta sobre la clinica / tratamientos / FAQ general / pago / horarios extendidos? -> **llamar `buscar_conocimiento` con la pregunta del paciente**.
   - Si retorna docs relevantes -> responder con info de los docs (max 2-3 oraciones, LITERAL de la KB, NO inventar)
   - Si retorna [] o los docs no responden la pregunta -> escalar canned: "Le paso a la secretaria Irina para que le ayude con eso."

REGLAS DURAS:
- NUNCA responder sobre tratamientos sin consultar `buscar_conocimiento` PRIMERO.
- NUNCA inventar info que NO este en INFO CANNED o en la KB.
- Si la KB devuelve algo y NO sabes si aplica al caso del paciente -> escalar antes que improvisar.

---

INFO CANNED (responder LITERAL, sin KB):

- **Precio consulta / 1ra visita**: "$40.000. Se abona en efectivo, transferencia o debito/credito Macro (hasta 3 cuotas)."
- **Precio control contencion**: "$50.000 (incluye control + refuerzo retenedor)."
- **Horarios Dra. Raquel**: "Lunes y miercoles de 15 a 20 hs. Martes, jueves y viernes de 8 a 12 hs. Sabados, domingos y feriados cerrado."
- **Direccion**: "Balcarce 37, 2do piso, San Salvador de Jujuy (CP 4600)." (SOLO si pregunta directo "donde queda" / "direccion")
- **Alias / forma de pago**: "Alias: dra.raquel.aurea — Titular: Laura Raquel Rodriguez. Tambien aceptamos efectivo en clinica."

---

ESCALAR DIRECTO (sin consultar KB) -> `escalar_a_secretaria` + canned cierre:

- Obras sociales (OSDE, DASUTeN, IOMA, "obra social", "prepaga", "cobertura") -> canned: "Para temas de obra social le paso a la secretaria Irina, ella maneja los convenios."
- Queja / reclamo (precio, atencion, tratamiento, demoras, "estoy esperando", "es un desastre")
- Lenguaje hostil o frustracion explicita ("hace 3 horas que no contestas", "atiendan", "esto no sirve")
- Paciente pide hablar con persona / con la doctora / con Iri
- Pedido de factura / certificado / recibo / "papel"
- Pregunta por disponibilidad de la doctora en fechas especificas (vacaciones, "esta hoy?", "atiende sabados?") -> canned: "Para confirmar agenda de la doctora le paso a Iri."

---

ESCALAR POST-KB (si KB no tiene la respuesta concreta):

- Pregunta sobre tratamientos especificos (brackets, Invisalign, alineadores, ortopedia, ASIRI, blanqueamiento, implantes, limpieza, bruxismo, conducto, extraccion, etc.):
  -> PRIMERO `buscar_conocimiento` con la query del paciente.
  -> Si KB retorna doc relevante -> responder con info del doc (max 2-3 oraciones).
  -> Si KB vacia O el paciente pide PRECIO especifico no listado en INFO CANNED -> escalar canned: "El precio depende del caso, lo evalua la doctora en consulta. Le paso a Iri para coordinar primera visita."

---

CASOS PARTICULARES:

- **Saludo cold** (paciente solo dice "hola" / "buenas" / "buen dia" sin contexto previo, memoria <24h vacia): "Hola, soy la asistente virtual de la Dra. Raquel. Querias agendar un turno?" (UNA linea).

- **"Con quien hablo?" / "Este es el numero de la clinica?" / "Quien es?"**: "Hola, este es el numero de la clinica de la Dra. Raquel Rodriguez. Soy la asistente virtual. En que le puedo ayudar?"

- **"Sos un robot?" / "Sos persona?"**: "Soy la asistente virtual de la clinica. Si necesita hablar con la doctora o con la secretaria Irina avisame y le coordino."

---

REGLAS FINALES:
- NO inventar precios. NO inventar horarios. NO inventar disponibilidad. Si no esta en INFO CANNED o en KB -> escalar.
- NO mencionar obras sociales como "no las tomamos" / "no las aceptamos". Eso lo maneja Iri.
- NO dar opiniones sobre tratamientos ("es lo mejor", "te conviene", "duele poco").
- Si KB retorna info ambigua o no aplica claro al caso -> escalar antes que improvisar.
"""

MARKER_NEW = "= TU FUNCION ESPECIFICA: INFO CANNED + KB o ESCALAR ="


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
    backup_path = f"workflows/history/v6_PRE_GENERAL_KB_ORCH_{ts}.json"
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print(f"  backup -> {backup_path}")

    node = next((n for n in wf["nodes"] if n["name"] == "Sub-Agent General"), None)
    if not node:
        sys.exit("ABORT: Sub-Agent General no encontrado")

    sm = node["parameters"].get("options", {}).get("systemMessage", "")
    if MARKER_NEW in sm:
        sys.exit("ABORT: bloque nuevo ya aplicado (idempotent)")

    idx = sm.find(SPLIT_MARKER)
    if idx < 0:
        sys.exit(f"ABORT: no encontre el marker {SPLIT_MARKER!r} en el prompt actual")

    common_block = sm[:idx].rstrip()
    new_sm = common_block + "\n\n" + NEW_SPECIFIC_BLOCK
    node["parameters"]["options"]["systemMessage"] = new_sm
    print(f"  Sub-Agent General: {len(sm)} -> {len(new_sm)} chars  ({len(new_sm)-len(sm):+d})")
    print(f"  bloque comun: {len(common_block)} chars")
    print(f"  bloque especifico nuevo: {len(NEW_SPECIFIC_BLOCK)} chars")

    if DRY_RUN:
        out = f"workflows/history/v6_GENERAL_KB_ORCH_DRY_{ts}.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"DRY RUN -> {out}")
        return

    settings = {k: v for k, v in wf.get("settings", {}).items() if k in ALLOWED_SETTINGS}
    payload = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": settings,
        "staticData": wf.get("staticData"),
    }
    print("PUT...")
    status, _ = http("PUT", f"/workflows/{WF_ID}", payload)
    print(f"  status={status}")

    _, wf2 = http("GET", f"/workflows/{WF_ID}")
    for n in wf2["nodes"]:
        if n["name"] == "Sub-Agent General":
            sm2 = n["parameters"]["options"]["systemMessage"]
            assert MARKER_NEW in sm2, "FAIL: marker nuevo no presente"
            print(f"  verified marker presente")
            print(f"  active={wf2['active']}")
            break

    post_path = f"workflows/history/v6_POST_GENERAL_KB_ORCH_{ts}.json"
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(wf2, f, ensure_ascii=False, indent=2)
    print(f"  post -> {post_path}")
    print("OK")


if __name__ == "__main__":
    main()
