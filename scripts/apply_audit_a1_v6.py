"""
apply_audit_a1_v6.py — Track A1 al v6 (O155MqHgOSaNZ9ye), 4 patches BAJO riesgo.
Solo texto de query/jsCode/description/placeholder; cero cambios de grafo.
Workflow INCIDENTE-SENSIBLE: guardas extra (node count, evo-webhook-v2, solo estos 4 nodos).
Backup PRE/POST. Las sticky notes cosméticas se dejan para otro pase (mínima superficie).

1. Check Session Age: quitar el guard DDL (DO $$ ALTER TABLE $$) que corre POR MENSAJE —
   created_at ya existe en v3; queda solo el SELECT. ~29ms/mensaje.
2. Banlist Shadow - Prep: early return [] cuando el output es vacío/[NO_REPLY] — su propio
   prompt lo define ALLOW; hoy gasta 1 request gpt-5-nano por cada mensaje silenciado.
3. buscar_horarios (description que lee el LLM): la tool devuelve próximos slots DESDE la
   fecha; llamarla UNA vez, no sondear varias fechas en paralelo (de 4-10 GETs Dentalink a 1-2).
4. confirmar_turno placeholder: "cita a cancelar" → "cita a CONFIRMAR" (copy-paste que
   confunde al tool-calling del LLM).
"""
import json, sys, time, urllib.request
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
H = {"X-N8N-API-KEY": require("N8N_API_KEY"), "accept": "application/json",
     "content-type": "application/json"}
HIST = Path(__file__).resolve().parents[1] / "workflows" / "history"
TS = time.strftime("%Y%m%d_%H%M%S")
WID = "O155MqHgOSaNZ9ye"
ALLOWED = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(N8N + path, method=method, headers=H, data=data)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def die(m):
    print("ABORTADO:", m); sys.exit(1)


def node(wf, name):
    for n in wf["nodes"]:
        if n["name"] == name:
            return n
    die(f"nodo '{name}' no encontrado")


wf = api("GET", f"/api/v1/workflows/{WID}")
n_pre = len(wf["nodes"])
(HIST / f"v6_PRE_a1_{TS}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"v6: {n_pre} nodos, active={wf.get('active')} — backup PRE guardado")

# 1) Check Session Age — quitar prefijo DDL
csa = node(wf, "Check Session Age")
q = csa["parameters"]["query"]
PREFIX = ("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM information_schema.columns "
          "WHERE table_name = 'n8n_chat_histories' AND column_name = 'created_at') "
          "THEN ALTER TABLE n8n_chat_histories ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW(); "
          "END IF; END $$; ")
if PREFIX not in q:
    die("anchor DDL de Check Session Age no encontrado")
csa["parameters"]["query"] = q.replace(PREFIX, "", 1)

# 2) Banlist Shadow - Prep — early return
bsp = node(wf, "Banlist Shadow - Prep")
js = bsp["parameters"]["jsCode"]
ANCHOR = "const originalOutput = (banlistResult.output_original || banlistResult.output || '').toString();"
if ANCHOR not in js:
    die("anchor originalOutput de Banlist Shadow no encontrado")
bsp["parameters"]["jsCode"] = js.replace(
    ANCHOR,
    ANCHOR + "\nif (!originalOutput.trim() || originalOutput.trim() === '[NO_REPLY]') { return []; }",
    1)

# 3) buscar_horarios — description anti-sondeo
bh = node(wf, "buscar_horarios")
d = bh["parameters"]["description"]
OLD = "NUNCA afirmes que no hay turnos para una fecha sin haber llamado esta tool con ESA fecha."
NEW = ("La respuesta SIEMPRE incluye los proximos turnos disponibles DESDE esa fecha en adelante "
       "(aunque esa fecha puntual no tenga cupos). Por eso llamala UNA SOLA VEZ por turno de "
       "conversacion, con la fecha preferida del paciente. NO la llames con varias fechas distintas "
       "en paralelo: con una sola llamada ya obtenes los proximos slots.")
if OLD not in d:
    die("anchor description de buscar_horarios no encontrado")
bh["parameters"]["description"] = d.replace(OLD, NEW, 1)

# 4) confirmar_turno — placeholder
ct = node(wf, "confirmar_turno")
pd = ct["parameters"]["placeholderDefinitions"]["values"][0]
if "cancelar" not in pd["description"]:
    die("placeholder confirmar_turno no dice 'cancelar' (¿ya parcheado?)")
pd["description"] = pd["description"].replace("cita a cancelar", "cita a CONFIRMAR")

# ── guardas ──
nodes_json = json.dumps(wf["nodes"], ensure_ascii=False)
if len(wf["nodes"]) != n_pre:
    die("cambió el número de nodos")
if "evo-webhook-v2" not in nodes_json:
    die("se perdió evo-webhook-v2")
if "DO $$" in csa["parameters"]["query"]:
    die("el DDL sigue en Check Session Age")

settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
api("PUT", f"/api/v1/workflows/{WID}",
    {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
     "settings": settings, "staticData": wf.get("staticData")})

v = api("GET", f"/api/v1/workflows/{WID}")
vj = json.dumps(v["nodes"], ensure_ascii=False)
if "evo-webhook-v2" not in vj:
    die("POST-VERIFY: evo-webhook-v2 no está")
if "DO $$" in vj:
    die("POST-VERIFY: DDL sigue presente")
if "cita a CONFIRMAR" not in vj:
    die("POST-VERIFY: placeholder no quedó")
(HIST / f"v6_POST_a1_{TS}.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"v6 PUT OK + verificado (active={v.get('active')}, nodos={len(v['nodes'])})")
print(f"Backups workflows/history/v6_PRE|POST_a1_{TS}.json")
