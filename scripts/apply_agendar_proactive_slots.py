"""
Reemplaza el bloque PASO 4 + 5 del Sub-Agent Agendar para que el bot
ofrezca slots iterativamente en lugar de preguntar abierto.

NO toca otros bloques (R0, IDENTIFICACION, ANTI-INJECTION, REGLAS, etc.).
Solo reemplaza los 2 pasos especificos.

Backup pre + verify post.
"""
import json, sys
from datetime import datetime
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
H = {"X-N8N-API-KEY": KEY, "Accept": "application/json", "Content-Type": "application/json"}

REPO = Path(__file__).resolve().parents[1]
hist = REPO / "workflows" / "history"

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_AGENDAR_PROACTIVE_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_AGENDAR_PROACTIVE_{ts}.json")

sa = next(x for x in wf["nodes"] if x["name"] == "Sub-Agent Agendar")
sys_msg = sa["parameters"]["options"]["systemMessage"]
print(f"prompt actual: {len(sys_msg)} chars")

OLD = """PASO 4 — FECHA / FRANJA:
- "Que dia o franja le viene mejor: manianas, tardes, fecha concreta?"
- Si el paciente da fecha vaga ("la semana que viene") -> pedir mas precisa.

PASO 5 — BUSCAR HORARIOS:
- `buscar_horarios(fecha)`. NUNCA con query vacio.
- NO ofrecer horarios pasados (compara con FECHA Y HORA ACTUAL del header).
- Si la fecha pedida no tiene disponibles -> ofrecer 2-3 alternativas cercanas."""

NEW = """PASO 4 — PREGUNTAR FRANJA (UNA pregunta corta, NO disparar busqueda todavia):
- "¿Qué día o franja le viene mejor: mañana, tarde o una fecha concreta?"
- Si el paciente da fecha vaga ("la semana que viene") -> pedir mas precisa.

PASO 5 — BUSCAR Y OFRECER SLOTS ITERATIVAMENTE (no preguntar mas, GUIAR con opciones):

REGLA: cuando el paciente responde con franja o dia, BUSCAR Y OFRECER slots concretos del dia MAS PROXIMO disponible. NO preguntar mas detalles abiertos.

a) Si el paciente dijo franja (mañana / tarde / noche):
   - Llamar `buscar_horarios(hoy)` y filtrar por franja:
     * mañana = horarios menores a 14:00
     * tarde  = horarios entre 14:00 y 18:59
     * noche  = horarios desde 18:00
   - Si hay slots disponibles ese dia (no pasados) -> ofrecer 2-3 del dia MAS PROXIMO:
     "Tengo disponible hoy a las 17:30 o a las 18:10. ¿Le sirve alguno?"
   - Si NO hay slots disponibles ese dia O todos pasaron -> `buscar_horarios(dia siguiente)` -> repetir
   - Si paciente dice "no, otro dia" / "mas tarde" / "otra fecha" -> SIGUIENTE dia con disponibilidad en franja
   - Iterar dia a dia hasta que el paciente elija UN slot, o se agoten 7 dias (limite)
   - NUNCA mostrar mas de 3 slots por mensaje (saturacion al paciente)

b) Si dio fecha exacta (ej: "el viernes", "el 13", "viernes 13 de junio"):
   - `buscar_horarios(fecha)` directo
   - Ofrecer slots de ese dia (filtrar por franja si tambien la dio)
   - Si no hay -> ofrecer 2-3 alternativas cercanas del mismo tipo (manana/tarde)

c) Si dijo "cualquiera" / "lo antes posible" / "cuando sea":
   - `buscar_horarios(hoy)` -> ofrecer todos los slots futuros del dia (max 3)
   - Si no hay -> dia siguiente -> iterar

NUNCA repetir read-back si el paciente ya pidio el slot. Cuando el paciente elija UN slot concreto -> ir a PASO 6 directo.

PASO 5b — REGLA NATURALIDAD:
- Decir horarios en formato natural: "17:30" -> "5 y media de la tarde" o "17:30 hs", NUNCA "17:30:00".
- Decir fechas en formato natural: "mañana martes", "este viernes 30", "el lunes 2 de junio".
- NUNCA listar mas de 3 slots por mensaje (sobrecarga al paciente)."""

if NEW.split("\n")[0] in sys_msg:
    print("  [skip] PASO 4 ya actualizado")
elif OLD not in sys_msg:
    print(f"  !! anchor OLD no encontrado. Buscando posicion...")
    # debug
    if "PASO 4 — FECHA / FRANJA:" in sys_msg:
        pos = sys_msg.index("PASO 4 — FECHA / FRANJA:")
        print(f"    PASO 4 — FECHA / FRANJA encontrado en pos {pos}")
        print(f"    Contexto: {sys_msg[pos:pos+600]!r}")
    sys.exit(1)
else:
    new_msg = sys_msg.replace(OLD, NEW)
    sa["parameters"]["options"]["systemMessage"] = new_msg
    print(f"  reemplazo OK, prompt: {len(sys_msg)} -> {len(new_msg)} chars")

# PUT
allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in allowed}
payload = {"name": wf["name"], "nodes": wf["nodes"],
           "connections": wf["connections"], "settings": settings}
if wf.get("staticData") is not None:
    payload["staticData"] = wf["staticData"]
r = requests.put(f"{N8N}/api/v1/workflows/{WF}", headers=H,
                 data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
print(f"\nPUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:500]); sys.exit(1)

wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_AGENDAR_PROACTIVE_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup post -> v6_POST_AGENDAR_PROACTIVE_{ts}.json")
print(f"v6 active: {wf_post.get('active')}")

# Verify bloques originales intactos
sa_post = next(x for x in wf_post["nodes"] if x["name"] == "Sub-Agent Agendar")
sys_post = sa_post["parameters"]["options"]["systemMessage"]
checks = [
    ("R0", "**R0. AGENTE FUNCIONAL"),
    ("IDENTIFICACION (Asiri)", "Asiri"),
    ("ANTI-INJECTION", "**ANTI-INJECTION**"),
    ("PASO 1 NOMBRE REAL", "PASO 1 — NOMBRE REAL"),
    ("PASO 4 NUEVO (franja)", "PASO 4 — PREGUNTAR FRANJA"),
    ("PASO 5 NUEVO (iterativo)", "PASO 5 — BUSCAR Y OFRECER SLOTS ITERATIVAMENTE"),
    ("PASO 6 (read-back/reservar) original", "PASO 6"),
    ("REGLA UNA SOLA ESCALACION", "**REGLA CRITICA - UNA SOLA ESCALACION POR TURNO**"),
]
print(f"\nVerify bloques en Sub-Agent Agendar:")
for label, anchor in checks:
    ok = anchor in sys_post
    print(f"  [{('OK' if ok else 'MISSING')}] {label}")
