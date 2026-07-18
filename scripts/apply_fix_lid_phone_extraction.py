"""
Fix LID-safe phone extraction (2026-07-06).

Problema: "Edit Fields - Extraer Datos" deriva phone/phone_last10 con
remoteJid.replace('@s.whatsapp.net','') a ciegas. Si el remoteJid llega como
@lid crudo (Evolution #1872: pasa cuando el mapeo lid->pn no esta cacheado,
"symptoms persist on v2.3.7"), phone queda basura -> paciente invisible en
Dentalink/Supabase/recordatorios, y el human-takeover de Chatwoot queda
fail-open. En grupos, phone sale '...@g.us' aunque participantAlt traiga el
numero real.

Fix (evidencia: forense de 527 execs + codigo Evolution 2.3.7 + doc Baileys v7):
1. phone / phone_last10: primer candidato que termine en '@s.whatsapp.net'
   entre key.remoteJid -> remoteJidAlt -> senderPn -> participantAlt ->
   participant; se recorta device suffix ':NN' y dominio. Si ninguno es
   telefono: comportamiento previo EXACTO (fallback identico, cero regresion).
2. Nuevo campo pushName en el extractor: los sub-agents inyectan
   {{ ...json.pushName }} pero el extractor guardaba el valor como 'name'
   -> pushName llegaba vacio SIEMPRE. Se agrega sin tocar 'name'.
3. Kill-switch Check: misma cadena de candidatos pero SOLO DM
   (remoteJid/remoteJidAlt/senderPn; sin participant* para no habilitar
   /bot desde grupos). Un admin escribiendo desde chat @lid recupera
   /bot off|on|status (hoy se ignoraban en silencio).

NO se toca: Rate Limit Prep (guard seguro existente), envio (usa remoteJid
crudo, correcto), webhookId, conexiones, demas nodos.
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
    print("ABORTADO (no se hizo PUT): " + msg)
    sys.exit(1)


# ---------- Expresiones nuevas ----------
CAND_CHAIN = ("[k.remoteJid, k.remoteJidAlt, k.senderPn, k.participantAlt, k.participant]")

PHONE_NEW = (
    "={{ (() => { const k = $('Webhook - Evolution API').first().json.body.data.key || {}; "
    f"for (const c of {CAND_CHAIN}) "
    "{ if (typeof c === 'string' && c.endsWith('@s.whatsapp.net')) return c.split('@')[0].split(':')[0]; } "
    "return (k.remoteJid || '').replace('@s.whatsapp.net', ''); })() }}"
)
PHONE10_NEW = (
    "={{ (() => { const k = $('Webhook - Evolution API').first().json.body.data.key || {}; "
    f"for (const c of {CAND_CHAIN}) "
    "{ if (typeof c === 'string' && c.endsWith('@s.whatsapp.net')) return c.split('@')[0].split(':')[0].slice(-10); } "
    "return (k.remoteJid || '').replace('@s.whatsapp.net', '').slice(-10); })() }}"
)

PHONE_OLD = "={{ $('Webhook - Evolution API').first().json.body.data.key.remoteJid.replace('@s.whatsapp.net', '') }}"
PHONE10_OLD = "={{ $('Webhook - Evolution API').first().json.body.data.key.remoteJid.replace('@s.whatsapp.net', '').slice(-10) }}"

KILL_OLD = "const phone = remoteJid.replace('@s.whatsapp.net', '').replace(/^\\+/, '');"
KILL_NEW = (
    "// LID-safe (2026-07-06): primer JID telefono real; SOLO DM (sin participant*, /bot no aplica en grupos)\n"
    "let phone = '';\n"
    "for (const c of [k && k.remoteJid, k && k.remoteJidAlt, k && k.senderPn]) {\n"
    "  if (typeof c === 'string' && c.endsWith('@s.whatsapp.net')) { phone = c.split('@')[0].split(':')[0]; break; }\n"
    "}\n"
    "if (!phone) phone = remoteJid.replace('@s.whatsapp.net', '').replace(/^\\+/, '');"
)

# ---------- 1. Fetch fresco ----------
live = api("GET", f"/api/v1/workflows/{WF}")
raw_before = json.dumps(live, ensure_ascii=False)
print(f"Fetch OK. nodos={len(live['nodes'])} active={live.get('active')}")

# ---------- 2. Backup PRE ----------
ts = time.strftime("%Y%m%d_%H%M%S")
pre = HIST / f"v6_PRE_lid_phone_fix_{ts}.json"
pre.write_text(json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Backup PRE: {pre.name}")

# ---------- 3. Patch ----------
n_edit = next((n for n in live["nodes"] if n["name"] == "Edit Fields - Extraer Datos"), None)
n_kill = next((n for n in live["nodes"] if n["name"] == "Kill-switch Check"), None)
if not n_edit or not n_kill:
    die("no encuentro los nodos objetivo")

assigns = n_edit["parameters"]["assignments"]["assignments"]
a_phone = next((a for a in assigns if a["id"] == "f-phone"), None)
a_ph10 = next((a for a in assigns if a["id"] == "f-phone-last10"), None)
a_name = next((a for a in assigns if a["id"] == "f-name"), None)
if not a_phone or not a_ph10 or not a_name:
    die("assignments f-phone/f-phone-last10/f-name no encontrados")
if a_phone["value"] != PHONE_OLD:
    die(f"f-phone drifteo, no coincide con lo esperado:\n{a_phone['value']}")
if a_ph10["value"] != PHONE10_OLD:
    die(f"f-phone-last10 drifteo:\n{a_ph10['value']}")
if any(a.get("name") == "pushName" for a in assigns):
    die("pushName ya existe en el extractor (ya aplicado?)")
if KILL_OLD not in n_kill["parameters"]["jsCode"]:
    die("linea de phone del Kill-switch no coincide (drift)")

a_phone["value"] = PHONE_NEW
a_ph10["value"] = PHONE10_NEW
assigns.append({"id": "f-pushname", "name": "pushName", "type": "string",
                "value": a_name["value"]})
n_kill["parameters"]["jsCode"] = n_kill["parameters"]["jsCode"].replace(KILL_OLD, KILL_NEW, 1)

print("\n== Cambios ==")
print("  [Edit Fields - Extraer Datos] f-phone -> cadena LID-safe")
print("  [Edit Fields - Extraer Datos] f-phone-last10 -> cadena LID-safe")
print("  [Edit Fields - Extraer Datos] + campo pushName (fix inyeccion vacia en sub-agents)")
print("  [Kill-switch Check] phone -> cadena LID-safe solo-DM")

# ---------- 4. Verificaciones pre-PUT ----------
nodes_after = json.dumps(live["nodes"], ensure_ascii=False)
before_obj = json.loads(raw_before)


def node_map(nodes):
    return {n["name"]: json.dumps(n, ensure_ascii=False, sort_keys=True) for n in nodes}


bm, am = node_map(before_obj["nodes"]), node_map(live["nodes"])
changed = sorted(k for k in bm if bm[k] != am.get(k))
print(f"nodos modificados: {changed}")
if set(changed) != {"Edit Fields - Extraer Datos", "Kill-switch Check"}:
    die(f"nodos inesperados modificados: {changed}")
if set(bm) != set(am):
    die("cambio la lista de nodos")
wh_b = json.dumps(before_obj["nodes"], ensure_ascii=False).count("evo-webhook-v2")
if nodes_after.count("evo-webhook-v2") != wh_b:
    die("webhookId evo-webhook-v2 alterado!")
if "@lid" in json.dumps(before_obj["nodes"], ensure_ascii=False):
    print("  (aviso: ya habia logica @lid previa)")

# ---------- 5. PUT ----------
ALLOWED = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}
settings = {k: v for k, v in (live.get("settings") or {}).items() if k in ALLOWED}
body = {"name": live["name"], "nodes": live["nodes"], "connections": live["connections"],
        "settings": settings, "staticData": live.get("staticData")}
print("\nPUT ...")
res = api("PUT", f"/api/v1/workflows/{WF}", body)
print(f"PUT OK. updatedAt={res.get('updatedAt')} active={res.get('active')}")

# ---------- 6. Backup POST + verificacion ----------
post = HIST / f"v6_POST_lid_phone_fix_{ts}.json"
post.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
verify = api("GET", f"/api/v1/workflows/{WF}")
v_edit = next(n for n in verify["nodes"] if n["name"] == "Edit Fields - Extraer Datos")
v_assign = v_edit["parameters"]["assignments"]["assignments"]
v_kill = next(n for n in verify["nodes"] if n["name"] == "Kill-switch Check")
ok_phone = any(a["id"] == "f-phone" and "remoteJidAlt" in a["value"] for a in v_assign)
ok_push = any(a.get("name") == "pushName" for a in v_assign)
ok_kill = "remoteJidAlt" in v_kill["parameters"]["jsCode"]
print("\n== Verificacion post-PUT (vivo) ==")
print(f"  f-phone LID-safe: {ok_phone}")
print(f"  pushName presente: {ok_push}")
print(f"  kill-switch LID-safe: {ok_kill}")
print(f"  active: {verify.get('active')}  nodos: {len(verify['nodes'])}")
print(f"  webhookId count: {json.dumps(verify['nodes'], ensure_ascii=False).count('evo-webhook-v2')}")
print(f"  Backup POST: {post.name}")
if not (ok_phone and ok_push and ok_kill and verify.get("active")):
    print("ATENCION: alguna verificacion fallo — revisar/rollback con el backup PRE")
    sys.exit(1)
print("\nOK - fix LID aplicado en produccion.")
