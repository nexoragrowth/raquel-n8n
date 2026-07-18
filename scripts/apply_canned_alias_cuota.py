"""
Canned alias completo + cuota mensual $70.000 (pedido Dra. Raquel 2026-07-08 22:16-22:21,
aprobado por Lucas "Barbaro si").

1. Alias: reemplaza el bloque de formato por la version con datos bancarios completos
   (titular, CUIT, CBU, cuenta, banco Brubank) en 3 mensajes (splits con ---), para que
   el paciente pueda verificar el titular antes de transferir.
2. Cuota mensual: nuevo canned $70.000 + regla de desambiguacion (los pacientes le dicen
   "consulta" o "control" a la cuota mensual; caso real Valentina Vilca 08/07: pregunto
   por "la cuota que pagamos cada vez que vamos a control" y el bot respondio el canned
   de contencion $50.000 por matchear "control").

Solo toca el systemMessage del Sub-Agent General. Backup pre/post, anchors exactos.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import require

N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
WF = require("N8N_WORKFLOW_V6_ID")
HIST = Path(__file__).resolve().parents[1] / "workflows" / "history"
H = {"X-N8N-API-KEY": KEY, "accept": "application/json", "content-type": "application/json"}


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(N8N + path, method=method, headers=H, data=data)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def die(msg):
    print("ABORTADO (sin PUT): " + msg)
    sys.exit(1)


live = api("GET", f"/api/v1/workflows/{WF}")
raw_before = json.dumps(live, ensure_ascii=False)
ts = time.strftime("%Y%m%d_%H%M%S")
(HIST / f"v6_PRE_alias_cuota_{ts}.json").write_text(
    json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Backup PRE OK. nodos={len(live['nodes'])} active={live.get('active')}")

gen = next((n for n in live["nodes"] if n["name"] == "Sub-Agent General"), None)
if not gen:
    die("Sub-Agent General no encontrado")
sm = gen["parameters"]["options"]["systemMessage"]

# ---- 1) bloque alias: localizar el fence que contiene dra.raquel.aurea
import re
m = re.search(r"```\n?[^`]*dra\.raquel\.aurea[^`]*```", sm)
if not m:
    die("no encuentro el bloque de formato del alias (fence con dra.raquel.aurea)")
old_block = m.group(0)
print("\nBLOQUE ALIAS VIEJO:\n" + old_block[:400])

NEW_BLOCK = """```
Si, ahora le envío alias y datos de cuenta de la Dra. En ese caso enviar comprobante por favor.
---
dra.raquel.aurea
---
Titular: Laura Raquel Rodríguez
CUIT/CUIL: 27316870118
Alias: dra.raquel.aurea
CBU: 1430001713001112680016
NRO. CUENTA: 1300111268001
Banco: BRUBANK
```"""
sm = sm.replace(old_block, NEW_BLOCK, 1)

# actualizar la nota del preambulo si menciona la version vieja
sm = sm.replace("(NUEVO 2026-06-03 pedido Dra)",
                "(ACTUALIZADO 2026-07-08 pedido Dra: datos completos para verificar titular antes de transferir)", 1)

# ---- 2) canned cuota mensual + regla de desambiguacion
ANCHOR = 'incluye control + refuerzo retenedor)."'
if ANCHOR not in sm:
    die("no encuentro el canned de contencion como anchor")
CUOTA = ANCHOR + """
- **Cuota mensual del tratamiento ortodóncico**: "El valor de la cuota mensual es de $70.000." (NUEVO 2026-07-08 pedido Dra)
- **REGLA DESAMBIGUACIÓN CUOTA (NUEVO 2026-07-08 pedido Dra, caso real 08/07)**: los pacientes confunden "consulta", "cuota" y "control". Si preguntan cuánto cuesta "la cuota", o hablan de lo que pagan "cada vez que van a control" o "todos los meses", NO asumas. Preguntá EXACTO: "¿Usted se refiere a la cuota mensual del tratamiento ortodóncico?". Si responde que sí → "El valor de la cuota mensual es de $70.000." Si dice que no o que es su primera visita → canned de precio consulta. El canned de contención ($50.000) es SOLO cuando mencionan explícitamente "contención" o "retenedor" (paciente que YA terminó el tratamiento) — NUNCA lo uses para la cuota mensual de un tratamiento activo."""
sm = sm.replace(ANCHOR, CUOTA, 1)

gen["parameters"]["options"]["systemMessage"] = sm

# ---- guardas
before_obj = json.loads(raw_before)
if len(live["nodes"]) != len(before_obj["nodes"]):
    die("cambio numero de nodos")
changed = [n["name"] for n, o in zip(live["nodes"], before_obj["nodes"])
           if json.dumps(n, ensure_ascii=False, sort_keys=True) != json.dumps(o, ensure_ascii=False, sort_keys=True)]
if changed != ["Sub-Agent General"]:
    die(f"nodos inesperados modificados: {changed}")
nodes_json = json.dumps(live["nodes"], ensure_ascii=False)
wb = json.dumps(before_obj["nodes"], ensure_ascii=False).count("evo-webhook-v2")
if nodes_json.count("evo-webhook-v2") != wb:
    die("webhookId alterado")
for token in ("BRUBANK", "70.000", "27316870118", "1430001713001112680016"):
    if token not in nodes_json:
        die(f"falta {token} tras el patch")

ALLOWED = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (live.get("settings") or {}).items() if k in ALLOWED}
print("\nPUT ...")
res = api("PUT", f"/api/v1/workflows/{WF}",
          {"name": live["name"], "nodes": live["nodes"], "connections": live["connections"],
           "settings": settings, "staticData": live.get("staticData")})
(HIST / f"v6_POST_alias_cuota_{ts}.json").write_text(
    json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

verify = api("GET", f"/api/v1/workflows/{WF}")
v = json.dumps(verify["nodes"], ensure_ascii=False)
print("== Verificacion post-PUT ==")
print(f"  BRUBANK: {'BRUBANK' in v} | cuota 70.000: {'70.000' in v} | CBU: {'1430001713001112680016' in v}")
print(f"  active: {verify.get('active')} | nodos: {len(verify['nodes'])}")
print("\nOK - canneds actualizados en produccion.")
