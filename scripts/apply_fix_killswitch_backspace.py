"""
Fix CRITICO: regex del Kill-switch rota por backspace literal (2026-07-06).

El jsCode de "Kill-switch Check" contiene un caracter BACKSPACE real (U+0008)
donde deberia haber un word-boundary de regex (\\b). Causa: el codigo se cargo
via JSON y "\\b" en JSON = backspace, no regex \\b.

Efecto: la regex /^\\/bot\\s+(off|on|status)<BS>/ NO matchea NUNCA
-> /bot off|on|status silenciosamente rotos para LOS 3 ADMINS desde 2026-05-09.
Mismo modo de falla (kill-switch mudo) del incidente Mariela.

Detectado por el test T4 de scripts/test_lid_fix_e2e.py (el fix LID del nodo
estaba bien; fallaba por este bug subyacente).

Fix: reemplazar U+0008 -> los dos caracteres '\\' + 'b' (word boundary real).
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


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        N8N + path, data=data, method=method,
        headers={"X-N8N-API-KEY": KEY, "accept": "application/json",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def die(msg):
    print("ABORTADO (sin PUT): " + msg)
    sys.exit(1)


live = api("GET", f"/api/v1/workflows/{WF}")
raw_before = json.dumps(live, ensure_ascii=False)
print(f"Fetch OK. nodos={len(live['nodes'])} active={live.get('active')}")

ts = time.strftime("%Y%m%d_%H%M%S")
pre = HIST / f"v6_PRE_killswitch_backspace_{ts}.json"
pre.write_text(json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Backup PRE: {pre.name}")

n_kill = next((n for n in live["nodes"] if n["name"] == "Kill-switch Check"), None)
if not n_kill:
    die("nodo Kill-switch Check no encontrado")
js = n_kill["parameters"]["jsCode"]
count = js.count("\x08")
print(f"backspaces U+0008 en jsCode: {count}")
if count != 1:
    die(f"esperaba exactamente 1 backspace, hay {count}")
if "(off|on|status)\x08" not in js:
    die("el backspace no esta donde se esperaba (tras el grupo de la regex)")

n_kill["parameters"]["jsCode"] = js.replace("(off|on|status)\x08", "(off|on|status)\\b")

# verificaciones
before_obj = json.loads(raw_before)


def node_map(nodes):
    return {n["name"]: json.dumps(n, ensure_ascii=False, sort_keys=True) for n in nodes}


bm, am = node_map(before_obj["nodes"]), node_map(live["nodes"])
changed = sorted(k for k in bm if bm[k] != am.get(k))
print(f"nodos modificados: {changed}")
if changed != ["Kill-switch Check"]:
    die(f"nodos inesperados: {changed}")
new_js = n_kill["parameters"]["jsCode"]
if "\x08" in new_js:
    die("sigue habiendo backspace")
if "(off|on|status)\\b" not in new_js:
    die("word boundary no quedo bien")

ALLOWED = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (live.get("settings") or {}).items() if k in ALLOWED}
body = {"name": live["name"], "nodes": live["nodes"], "connections": live["connections"],
        "settings": settings, "staticData": live.get("staticData")}
print("PUT ...")
res = api("PUT", f"/api/v1/workflows/{WF}", body)
print(f"PUT OK. updatedAt={res.get('updatedAt')} active={res.get('active')}")

post = HIST / f"v6_POST_killswitch_backspace_{ts}.json"
post.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

verify = api("GET", f"/api/v1/workflows/{WF}")
v_js = next(n for n in verify["nodes"] if n["name"] == "Kill-switch Check")["parameters"]["jsCode"]
print("\n== Verificacion post-PUT ==")
print(f"  backspaces: {v_js.count(chr(8))} (esperado 0)")
print(f"  word boundary correcto: {'(off|on|status)' + chr(92) + 'b' in v_js}")
print(f"  active: {verify.get('active')}  nodos: {len(verify['nodes'])}")
if v_js.count("\x08") == 0 and "(off|on|status)\\b" in v_js and verify.get("active"):
    print("\nOK - regex del kill-switch reparada en produccion.")
else:
    print("ATENCION: verificacion fallo — rollback con backup PRE")
    sys.exit(1)
