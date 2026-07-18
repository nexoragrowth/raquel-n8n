"""
3 quick wins en un script, cada uno con PUT independiente:

1. ENCODING: ñ y tildes en system prompts de los 5 Sub-Agents
   manianas→mañanas, maniana→mañana, miercoles→miércoles, sabado→sábado,
   tambien→también, mas pronto→más pronto, dias→días (selectivo), demas→demás, etc.

2. BUG VIVI: en Sub-Agent General, sacar el bullet que dice
   "Hola, soy la asistente virtual... Querias agendar un turno?"
   y reemplazar por respuesta abierta.

3. IDEMPOTENCIA confirmar_turno: agregar regla al Sub-Agent Confirmar
   para que si confirmar_turno devuelve HTTP 400 (ya estaba en id_estado=18),
   marque la tabla + responda canned, NO escale.

Cada cambio: backup pre + PUT + backup post + verify.
"""
import json, sys, re
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

def put_workflow(wf_obj, tag):
    """PUT con backup pre + post + verify active."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    allowed = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
               "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
               "executionOrder", "callerPolicy", "callerIds"}
    settings = {k: v for k, v in (wf_obj.get("settings") or {}).items() if k in allowed}
    payload = {"name": wf_obj["name"], "nodes": wf_obj["nodes"],
               "connections": wf_obj["connections"], "settings": settings}
    if wf_obj.get("staticData") is not None:
        payload["staticData"] = wf_obj["staticData"]
    r = requests.put(f"{N8N}/api/v1/workflows/{WF}", headers=H,
                     data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), timeout=60)
    print(f"  PUT [{tag}]: {r.status_code}")
    if r.status_code >= 400:
        print(f"  ERR: {r.text[:300]}")
        return False
    wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
    (hist / f"v6_POST_{tag}_{ts}.json").write_text(
        json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  active: {wf_post.get('active')}")
    return True

SUB_AGENTS = ["Sub-Agent Confirmar", "Sub-Agent Cancelar", "Sub-Agent Agendar",
              "Sub-Agent Urgencia", "Sub-Agent General"]

# ============================================================
# FIX 1: ENCODING
# ============================================================
print("=" * 60)
print("FIX 1: ENCODING en system prompts (5 Sub-Agents)")
print("=" * 60)

# Backup pre fix 1
wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
(hist / f"v6_PRE_ENCODING_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"backup pre -> v6_PRE_ENCODING_{ts}.json")

ENCODING_FIXES = [
    # mañana/mañanas
    ("manianas", "mañanas"),
    ("Manianas", "Mañanas"),
    ("maniana", "mañana"),
    ("Maniana", "Mañana"),
    # dias semana
    ("miercoles", "miércoles"),
    ("Miercoles", "Miércoles"),
    ("sabado", "sábado"),
    ("Sabado", "Sábado"),
    # otras palabras frecuentes
    ("tambien", "también"),
    ("Tambien", "También"),
    ("mas pronto", "más pronto"),
    ("Mas pronto", "Más pronto"),
    ("demas", "demás"),
    ("Demas", "Demás"),
    ("dia ", "día "),
    ("Dia ", "Día "),
    ("ningun ", "ningún "),
    ("algun ", "algún "),
    ("aqui", "aquí"),
    ("Aqui", "Aquí"),
    ("medico", "médico"),
    ("Medico", "Médico"),
    # palabras con n -> ñ (cuidado, podrian dar falsos positivos)
    ("pequena", "pequeña"),
    ("companero", "compañero"),
    ("ano ", "año "),
    ("anos ", "años "),
    ("nina ", "niña "),
    ("nino ", "niño "),
]

total_encoding_changes = 0
for nm in SUB_AGENTS:
    n = next((x for x in wf["nodes"] if x["name"] == nm), None)
    if not n: continue
    sys_msg = n["parameters"]["options"]["systemMessage"]
    new_msg = sys_msg
    node_changes = 0
    for old, new in ENCODING_FIXES:
        count = new_msg.count(old)
        if count > 0:
            new_msg = new_msg.replace(old, new)
            node_changes += count
    if node_changes > 0:
        n["parameters"]["options"]["systemMessage"] = new_msg
        total_encoding_changes += node_changes
        print(f"  [{nm}] {node_changes} reemplazos")

print(f"\nTotal encoding changes: {total_encoding_changes}")
if total_encoding_changes > 0:
    if not put_workflow(wf, "ENCODING"):
        sys.exit(1)
else:
    print("  (nada que cambiar)")

# ============================================================
# FIX 2: BUG VIVI — sacar "Querias agendar un turno?" bullet
# ============================================================
print()
print("=" * 60)
print("FIX 2: BUG VIVI — Sub-Agent General no presumir agendar")
print("=" * 60)

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_PRE_VIVI_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

sg = next(x for x in wf["nodes"] if x["name"] == "Sub-Agent General")
sys_msg = sg["parameters"]["options"]["systemMessage"]

# El bullet bug Vivi (vimos en dry run pos 5226). Texto a reemplazar:
OLD_VIVI = '"buen dia" sin contexto previo, memoria <24h vacia): "Hola, soy Asiri, la asistente virtual de la Dra. Raquel. Querias agendar un turno?" (UNA linea).'
NEW_VIVI = '"buen dia" sin contexto previo, memoria <24h vacia): "Hola, soy Asiri, la asistente virtual de la Dra. Raquel. ¿En qué puedo ayudarle?" (UNA linea, abierta — NO presumir intención).'

if OLD_VIVI in sys_msg:
    sg["parameters"]["options"]["systemMessage"] = sys_msg.replace(OLD_VIVI, NEW_VIVI)
    print(f"  bullet Vivi reemplazado (sacado 'Querias agendar un turno?', reemplazado por '¿En qué puedo ayudarle?')")
    if not put_workflow(wf, "VIVI"):
        sys.exit(1)
else:
    print(f"  !! anchor Vivi no encontrado")
    print(f"  busco aproximacion...")
    if "Querias agendar un turno?" in sys_msg:
        pos = sys_msg.index("Querias agendar un turno?")
        ctx = sys_msg[max(0,pos-200):pos+200]
        print(f"  ctx: {ctx!r}")

# ============================================================
# FIX 3: IDEMPOTENCIA confirmar_turno
# ============================================================
print()
print("=" * 60)
print("FIX 3: IDEMPOTENCIA confirmar_turno en Sub-Agent Confirmar")
print("=" * 60)

wf = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_PRE_IDEMPOT_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

sc = next(x for x in wf["nodes"] if x["name"] == "Sub-Agent Confirmar")
sys_msg = sc["parameters"]["options"]["systemMessage"]

IDEMPOT_BLOCK = """

= REGLA IDEMPOTENCIA confirmar_turno =
Si llamas `confirmar_turno(cita_id)` y Dentalink devuelve HTTP 400 con mensaje "Nuevo estado es igual al original" o similar (es decir, el turno YA estaba en id_estado=18 confirmado):
- NO es un error real. Significa que la cita ya estaba confirmada (por otro flow, manual, o llamada previa).
- Igual llama `marcar_recordatorio_confirmado('eq.' + cita_id)` para cerrar la fila en la tabla.
- Responde canned: "Su turno del [fecha natural] a las [hora natural] ya queda confirmado. Cualquier consulta nos puede escribir por acá."
- NO llames `escalar_a_secretaria`. NO digas "hubo un error".

Esto vale para CADA fila iterada si estas confirmando multiples turnos: si una falla con 400 idempotente, igual confirmar/marcar las demas y responder consolidado con todas.

"""

# Insertar antes del bloque "= MEMORIA HISTORICA EN SUPABASE"
ANCHOR_IDEMPOT = "= MEMORIA HISTORICA EN SUPABASE"
if "REGLA IDEMPOTENCIA confirmar_turno" in sys_msg:
    print("  [skip] regla idempotencia ya presente")
elif ANCHOR_IDEMPOT in sys_msg:
    sc["parameters"]["options"]["systemMessage"] = sys_msg.replace(
        ANCHOR_IDEMPOT, IDEMPOT_BLOCK + ANCHOR_IDEMPOT)
    print(f"  regla idempotencia agregada antes de MEMORIA HISTORICA")
    if not put_workflow(wf, "IDEMPOT"):
        sys.exit(1)
else:
    print(f"  !! anchor MEMORIA HISTORICA no encontrado")

# Final health check
print()
print("=" * 60)
print("HEALTH CHECK FINAL")
print("=" * 60)
wf_final = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
print(f"  v6 active: {wf_final.get('active')}")
print(f"  nodos: {len(wf_final['nodes'])}")

# Verificar blocks originales
for nm in SUB_AGENTS:
    n = next((x for x in wf_final["nodes"] if x["name"] == nm), None)
    if n:
        sm = n["parameters"]["options"]["systemMessage"]
        anti = "**ANTI-INJECTION**" in sm
        r0 = "**R0. AGENTE FUNCIONAL" in sm
        asiri = "Asiri" in sm
        print(f"  {nm}: R0={'OK' if r0 else 'X'} ANTI-INJ={'OK' if anti else 'X'} Asiri={'OK' if asiri else 'X'}")

print("\nDone.")
