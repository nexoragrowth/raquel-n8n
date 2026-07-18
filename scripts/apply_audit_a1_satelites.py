"""
apply_audit_a1_satelites.py — Track A1 de la auditoría 18/7: patches BAJO riesgo a los
4 workflows satélite (Helper, Sub-WF Cancelar, Buscar Horarios, Recordatorios).
Solo texto de query/jsCode/params, cero cambios de grafo. Backup PRE/POST por workflow.

Patches (todos con anchor exacto verificado contra el live 18/7):
  Helper Notify (S5U6tSipzlgFHCkf):
    - Chatwoot Apply: fix del BUG FUNCIONAL #1 (query {} truthy pisaba el body → label
      humano jamás se aplicaba en escalaciones de cancelar → bot no se silenciaba).
    - Notify Grupo Send: retryOnFail 3x/2s (no perder el único aviso al grupo).
  Sub-WF Cancelar (5cAWJxiWJ50hxEq3):
    - Step 0b: parse tolerante a no-JSON (cierra el crash 16-17/7 que dejó sin respuesta).
    - Step 0a: LIMIT 30 → 20 (0b usa máx 10 pares).
  Buscar Horarios (GuDQ9VmKWZvQnerV):
    - Validar fecha: comparación en TZ Jujuy (elimina ERROR_FECHA espurio 19-24h ART).
    - Output Error: fix mojibake "1 año".
  Recordatorios (7RqTApkvVavRmq3R):
    - Postgres - Insert Memory: INSERT parametrizado (apóstrofe D'Angelo ya no mata el batch).
    - Guardar en Chat Memory: no empujar el item saved:false (jsonb inválido mataba el día).
    - Webhook Manual Recordatorios: responseMode onReceived (no filtrar datos de pacientes).
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


def repl(node, param, old, new):
    v = node["parameters"].get(param, "")
    if old not in v:
        die(f"anchor no encontrado en {node['name']}.{param}: {old[:60]!r}")
    node["parameters"][param] = v.replace(old, new, 1)


def put(wf, tag):
    # guardas
    wh_pre = sorted(n.get("webhookId", "") for n in wf["nodes"] if n.get("webhookId"))
    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
    res = api("PUT", f"/api/v1/workflows/{wf['id']}",
              {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
               "settings": settings, "staticData": wf.get("staticData")})
    v = api("GET", f"/api/v1/workflows/{wf['id']}")
    wh_post = sorted(n.get("webhookId", "") for n in v["nodes"] if n.get("webhookId"))
    if wh_pre != wh_post:
        die(f"{tag}: set de webhookId cambió")
    if len(v["nodes"]) != len(wf["nodes"]):
        die(f"{tag}: cambió el número de nodos")
    (HIST / f"{tag}_POST_a1_{TS}.json").write_text(
        json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{tag}] PUT OK + verificado (active={v.get('active')})")


def load(wid, tag):
    wf = api("GET", f"/api/v1/workflows/{wid}")
    (HIST / f"{tag}_PRE_a1_{TS}.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    return wf


# ── PUT-5 Helper Notify ────────────────────────────────────────────────────
wf = load("S5U6tSipzlgFHCkf", "Helper")
repl(node(wf, "Chatwoot Apply"), "jsCode",
     "const _wh = $('Webhook').first().json; const wh = _wh.query || _wh.body || {};",
     "const _wh = $('Webhook').first().json; const q = _wh.query || {}; const b = _wh.body || {}; const wh = (q.phone ? q : b);")
ng = node(wf, "Notify Grupo Send")
ng["retryOnFail"] = True; ng["maxTries"] = 3; ng["waitBetweenTries"] = 2000
put(wf, "Helper")

# ── PUT-2 Sub-WF Cancelar ──────────────────────────────────────────────────
wf = load("5cAWJxiWJ50hxEq3", "SubWFCancelar")
repl(node(wf, "Step 0b: Detect Multi-Turn State"), "jsCode",
     "  const msgJson = typeof m.message === 'string' ? JSON.parse(m.message) : m.message;\n  if (!msgJson) continue;",
     "  if (m.error) continue;\n  let msgJson = m.message;\n  if (typeof msgJson === 'string') { try { msgJson = JSON.parse(msgJson); } catch (e) { continue; } }\n  if (!msgJson || typeof msgJson !== 'object') continue;")
repl(node(wf, "Step 0a: Read Chat Memory"), "query",
     "ORDER BY id DESC LIMIT 30;", "ORDER BY id DESC LIMIT 20;")
put(wf, "SubWFCancelar")

# ── PUT-3 Buscar Horarios ──────────────────────────────────────────────────
wf = load("GuDQ9VmKWZvQnerV", "BuscarHorarios")
repl(node(wf, "Validar fecha"), "jsCode",
     "  const d = new Date(fecha + 'T00:00:00');\n  const hoy = new Date(); hoy.setHours(0, 0, 0, 0);\n  const limite = new Date(hoy); limite.setFullYear(limite.getFullYear() + 1);\n  esRazonable = !isNaN(d.getTime()) && d >= hoy && d <= limite;",
     "  const hoyStr = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Argentina/Jujuy' }).format(new Date());\n  const lim = new Date(hoyStr + 'T00:00:00'); lim.setFullYear(lim.getFullYear() + 1);\n  const limStr = lim.toISOString().slice(0, 10);\n  esRazonable = fecha >= hoyStr && fecha <= limStr;")
repl(node(wf, "Output Error"), "jsCode",
     "futura y dentro de 1 año.", "futura y dentro de los proximos 12 meses.")
put(wf, "BuscarHorarios")

# ── PUT-4 Recordatorios ────────────────────────────────────────────────────
wf = load("7RqTApkvVavRmq3R", "Recordatorio")
im = node(wf, "Postgres - Insert Memory")
im["parameters"]["query"] = "INSERT INTO n8n_chat_histories (session_id, message) VALUES ($1, $2::jsonb)"
im["parameters"]["options"] = {"queryReplacement": "={{ $json.session_id }},={{ $json.message_json }}"}
repl(node(wf, "Guardar en Chat Memory"), "jsCode",
     "    results.push({ json: { saved: false, reason: 'no phone or message', skipped_phone: phone || null } });\n    continue;",
     "    continue;")
node(wf, "Webhook Manual Recordatorios")["parameters"]["responseMode"] = "onReceived"
put(wf, "Recordatorio")

print(f"\nA1 satélites OK. Backups en workflows/history/*_a1_{TS}.json")
