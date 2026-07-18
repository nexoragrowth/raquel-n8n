"""
Gate deterministico 'humano reciente' (2026-07-15) — caso Esteban.

Problema: el staff pregunta algo manual (fromMe) -> label humano se aplica, pero
'Auto Reactivar Bot' lo quita a la hora. Si el paciente responde DESPUES de esa
hora, el gate Chatwoot ya esta abierto y el bot contesta (caso real 15/7: salto
el saludo frio en una conversacion iniciada por el staff). La instruccion
[ATENCION HUMANA] en memoria es solo prompt-layer y el LLM la violo una vez.

Fix (2da capa deterministica): nuevo nodo Postgres 'Check Humano Reciente (DB)'
entre 'Verificar Label Humano' y 'Bot Activo?': consulta si el ULTIMO mensaje de
la sesion (excluyendo reminder_notes) es un mensaje humano del staff
(source wa_outbound o human_takeover) de las ultimas 24h. 'Bot Activo?' pasa a
ser OR: label humano Chatwoot O humano_reciente en DB -> rama 'Humano Atendiendo'.

Semantica: la respuesta de un paciente a un mensaje manual del staff pertenece
al staff. El bot vuelve a hablar cuando el mismo bot fue el ultimo en hablar,
o pasadas 24h del ultimo mensaje humano.

onError=continueRegularOutput en el nodo nuevo: si la DB falla, humano_reciente
queda indefinido -> false -> comportamiento previo (fail-open, consistente).
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
WF = "O155MqHgOSaNZ9ye"
HIST = Path(__file__).resolve().parents[1] / "workflows" / "history"
H = {"X-N8N-API-KEY": KEY, "accept": "application/json", "content-type": "application/json"}


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(N8N + path, method=method, headers=H, data=data)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def die(msg):
    print("ABORTADO: " + msg)
    sys.exit(1)


wf = api("GET", f"/api/v1/workflows/{WF}")
raw_before = json.dumps(wf, ensure_ascii=False)
ts = time.strftime("%Y%m%d_%H%M%S")
(HIST / f"v6_PRE_gate_humano_reciente_{ts}.json").write_text(
    json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

names = {n["name"] for n in wf["nodes"]}
if "Check Humano Reciente (DB)" in names:
    die("ya aplicado")
for req_node in ("Verificar Label Humano", "Bot Activo?", "Humano Atendiendo (no hacer nada)",
                 "Build fromMe AI memory", "Preparar Mensaje Final"):
    if req_node not in names:
        die(f"falta nodo esperado: {req_node}")

# guard: los markers de source existen en el save de fromMe
fm = next(n for n in wf["nodes"] if n["name"] == "Build fromMe AI memory")
if "wa_outbound" not in json.dumps(fm.get("parameters", {})):
    die("Build fromMe AI memory no usa source wa_outbound (verificar markers)")

# guard: conexion actual Verificar -> Bot Activo?
conns = wf["connections"]
if conns.get("Verificar Label Humano", {}).get("main", [[]])[0][0].get("node") != "Bot Activo?":
    die("conexion Verificar->Bot Activo? inesperada")

QUERY = (
    "SELECT COALESCE((\n"
    "  SELECT COALESCE(message::jsonb->'additional_kwargs'->>'source','')\n"
    "         IN ('wa_outbound','human_takeover')\n"
    "     AND created_at > NOW() - INTERVAL '24 hours'\n"
    "  FROM n8n_chat_histories\n"
    "  WHERE session_id = '{{ $(\"Preparar Mensaje Final\").first().json.phone }}'\n"
    "    AND COALESCE(message::jsonb->'additional_kwargs'->>'source','') <> 'reminder_note'\n"
    "  ORDER BY id DESC LIMIT 1\n"
    "), false) AS humano_reciente"
)

check_node = {
    "parameters": {"operation": "executeQuery", "query": QUERY, "options": {}},
    "id": "check-humano-reciente",
    "name": "Check Humano Reciente (DB)",
    "type": "n8n-nodes-base.postgres",
    "typeVersion": 2.5,
    "position": [0, 0],
    "onError": "continueRegularOutput",
    "credentials": {"postgres": {"id": "EWhpNhb6tkGg1OTp", "name": "Postgres Supabase Nexora v2"}},
}
# posicion: cerca de Bot Activo?
ba = next(n for n in wf["nodes"] if n["name"] == "Bot Activo?")
check_node["position"] = [ba["position"][0] - 180, ba["position"][1] + 120]
wf["nodes"].append(check_node)

# rewire: Verificar -> Check -> Bot Activo?
conns["Verificar Label Humano"]["main"][0] = [
    {"node": "Check Humano Reciente (DB)", "type": "main", "index": 0}]
conns["Check Humano Reciente (DB)"] = {"main": [[{"node": "Bot Activo?", "type": "main", "index": 0}]]}

# Bot Activo?: OR de label chatwoot + humano_reciente
ba["parameters"]["conditions"]["combinator"] = "or"
ba["parameters"]["conditions"]["conditions"] = [
    {"id": "bot-check-condition",
     "leftValue": "={{ $('Verificar Label Humano').first().json.hasHumanoLabel }}",
     "rightValue": True,
     "operator": {"type": "boolean", "operation": "equals"}},
    {"id": "bot-check-humano-reciente",
     "leftValue": "={{ $json.humano_reciente === true }}",
     "rightValue": True,
     "operator": {"type": "boolean", "operation": "equals"}},
]

# guardas finales
before_obj = json.loads(raw_before)
if len(wf["nodes"]) != len(before_obj["nodes"]) + 1:
    die("conteo de nodos inesperado")
nodes_json = json.dumps(wf["nodes"], ensure_ascii=False)
wb = json.dumps(before_obj["nodes"], ensure_ascii=False).count("evo-webhook-v2")
if nodes_json.count("evo-webhook-v2") != wb:
    die("webhookId alterado")

ALLOWED = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
res = api("PUT", f"/api/v1/workflows/{WF}",
          {"name": wf["name"], "nodes": wf["nodes"], "connections": conns,
           "settings": settings, "staticData": wf.get("staticData")})
(HIST / f"v6_POST_gate_humano_reciente_{ts}.json").write_text(
    json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

v = api("GET", f"/api/v1/workflows/{WF}")
c = v["connections"]
ok = (c["Verificar Label Humano"]["main"][0][0]["node"] == "Check Humano Reciente (DB)"
      and c["Check Humano Reciente (DB)"]["main"][0][0]["node"] == "Bot Activo?"
      and v.get("active"))
vba = next(n for n in v["nodes"] if n["name"] == "Bot Activo?")
print(f"cadena: Verificar -> Check DB -> Bot Activo?: {ok}")
print(f"Bot Activo? combinator: {vba['parameters']['conditions']['combinator']} "
      f"({len(vba['parameters']['conditions']['conditions'])} condiciones)")
print(f"active: {v.get('active')} nodos: {len(v['nodes'])}")
print("OK" if ok else "REVISAR")
