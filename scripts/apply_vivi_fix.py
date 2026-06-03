"""
Fix bug Vivi: sacar bullet del Sub-Agent General que hace que el bot
presuma agendar al saludo cold.
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
(hist / f"v6_PRE_VIVI_FIX_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

sg = next(x for x in wf["nodes"] if x["name"] == "Sub-Agent General")
sys_msg = sg["parameters"]["options"]["systemMessage"]

# Anchor exacto del bullet bug Vivi (sin Asiri, como esta actualmente)
OLD = '"buen dia" sin contexto previo, memoria <24h vacia): "Hola, soy la asistente virtual de la Dra. Raquel. Querias agendar un turno?" (UNA linea).'
NEW = '"buen dia" sin contexto previo, memoria <24h vacia): "Hola, soy Asiri, la asistente virtual de la Dra. Raquel. ¿En qué puedo ayudarle?" (UNA linea, abierta — NO presumir intención).'

if OLD in sys_msg:
    sg["parameters"]["options"]["systemMessage"] = sys_msg.replace(OLD, NEW)
    print(f"  reemplazo OK: bullet Vivi corregido")
elif NEW in sys_msg:
    print(f"  [skip] ya aplicado previamente")
    sys.exit(0)
else:
    print(f"  !! anchor OLD no encontrado")
    if "Querias agendar un turno?" in sys_msg:
        pos = sys_msg.index("Querias agendar un turno?")
        print(f"  ctx alrededor: {sys_msg[max(0,pos-180):pos+100]!r}")
    sys.exit(1)

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
print(f"PUT: {r.status_code}")
if r.status_code >= 400:
    print(r.text[:500]); sys.exit(1)
wf_post = requests.get(f"{N8N}/api/v1/workflows/{WF}", headers=H, timeout=30).json()
(hist / f"v6_POST_VIVI_FIX_{ts}.json").write_text(
    json.dumps(wf_post, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"v6 active: {wf_post.get('active')}")

# Verify
sg_post = next(x for x in wf_post["nodes"] if x["name"] == "Sub-Agent General")
sm = sg_post["parameters"]["options"]["systemMessage"]
print(f"\nVerify:")
print(f"  bullet nuevo presente: {'OK' if 'En qué puedo ayudarle?' in sm else 'MISSING'}")
print(f"  bullet viejo presente (deberia estar ausente): {'X (queda)' if 'Querias agendar un turno?' in sm else 'OK (sacado)'}")
print(f"  ANTI-INJECTION intacto: {'OK' if '**ANTI-INJECTION**' in sm else 'MISSING'}")
print(f"  Asiri presente: {'OK' if 'Asiri' in sm else 'MISSING'}")
