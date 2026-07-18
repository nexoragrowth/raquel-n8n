"""
apply_audit_a2_get_paciente.py — Track A2, patch estrella MEDIO al v6.
"Get Paciente Context" es una query Postgres que corre por CADA webhook (antes de los
filtros fromMe/basura/buffer) y devuelve resumen_clinico vacío garantizado (su único
escritor, el Cron Resumen Clinico, está apagado desde 17/7). Ahorra ~100-200 queries/día.

PUT atómico (CONTRADICCION 5 resuelta): reemplazar la expresión en los 3 systemMessage que
la referencian (Sub-Agent Confirmar/Cancelar/Agendar) por el texto estático de fallback +
deshabilitar el nodo. Como no queda NINGUNA referencia al nodo apagado, es un no-op leaf
seguro (el nodo ya no tenía conexiones de salida). Reversible: reactivar nodo + restaurar
expresión si algún día se reactiva el Cron Resumen.
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
EXPR = "{{ $('Get Paciente Context').first().json.resumen_clinico || 'Sin historial registrado todavia.' }}"
STATIC = "Sin historial registrado todavia."
SUBAGENTS = ["Sub-Agent Confirmar", "Sub-Agent Cancelar", "Sub-Agent Agendar"]


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(N8N + path, method=method, headers=H, data=data)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def die(m):
    print("ABORTADO:", m); sys.exit(1)


wf = api("GET", f"/api/v1/workflows/{WID}")
n_pre = len(wf["nodes"])
(HIST / f"v6_PRE_a2_getpaciente_{TS}.json").write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

replaced = 0
for n in wf["nodes"]:
    if n["name"] in SUBAGENTS:
        opts = n["parameters"].get("options", {})
        sm = opts.get("systemMessage", "")
        if EXPR in sm:
            opts["systemMessage"] = sm.replace(EXPR, STATIC)
            n["parameters"]["options"] = opts
            replaced += 1
            print(f"  [{n['name']}] expresión reemplazada por texto estático")
        else:
            print(f"  [{n['name']}] ⚠ no tenía la expresión (¿ya parcheado?)")
    if n["name"] == "Get Paciente Context":
        n["disabled"] = True
        print("  [Get Paciente Context] disabled=True")

if replaced != 3:
    die(f"esperaba reemplazar 3 systemMessage, reemplacé {replaced}")

# guardas
nodes_json = json.dumps(wf["nodes"], ensure_ascii=False)
if len(wf["nodes"]) != n_pre:
    die("cambió el número de nodos")
if "evo-webhook-v2" not in nodes_json:
    die("se perdió evo-webhook-v2")
if "$('Get Paciente Context')" in nodes_json:
    die("quedó una referencia viva a Get Paciente Context")

settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
api("PUT", f"/api/v1/workflows/{WID}",
    {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
     "settings": settings, "staticData": wf.get("staticData")})

v = api("GET", f"/api/v1/workflows/{WID}")
vj = json.dumps(v["nodes"], ensure_ascii=False)
if "$('Get Paciente Context')" in vj:
    die("POST-VERIFY: referencia viva sigue presente")
if "evo-webhook-v2" not in vj:
    die("POST-VERIFY: evo-webhook-v2 no está")
gpc = next(n for n in v["nodes"] if n["name"] == "Get Paciente Context")
if not gpc.get("disabled"):
    die("POST-VERIFY: Get Paciente Context no quedó disabled")
(HIST / f"v6_POST_a2_getpaciente_{TS}.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"v6 A2 PUT OK + verificado (active={v.get('active')}, nodos={len(v['nodes'])}, GPC disabled)")
print(f"Backups workflows/history/v6_*_a2_getpaciente_{TS}.json")
