# -*- coding: utf-8 -*-
"""
create_panel_acciones_staff.py — crea el satélite n8n "Panel — acciones staff" que el panel
(nexora-whatsapp-agent) necesita para ENVIAR mensajes como staff y para el toggle bot/humano.

CONTEXTO (5/9): el panel tiene la UI y las server actions (`enviarMensajeAction`, `toggleBotAction`,
app/(app)/conversaciones/actions.ts) que POSTean a `{N8N_PANEL_WEBHOOK_BASE}/panel-send-human`
y `/panel-toggle-bot` con header `X-Panel-Secret` — pero esos webhooks NUNCA existieron en n8n y
el VPS no tenía las 2 variables, por eso siempre decía "El panel todavía no está conectado al
servidor del bot". Contrato del panel: 2xx = ok (ignora el body), 401/403 = "sin autorización",
otro = error genérico. Bodies: {telefono, mensaje} / {telefono, humano:boolean}.

QUÉ HACE:
  POST /webhook/panel-send-human  -> valida secreto -> /send/text por Evolution GO al paciente ->
      fila en n8n_chat_histories con el MISMO shape que la rama fromMe del v6 ([ATENCION HUMANA ...],
      source wa_outbound, from_panel true) -> label `humano` en Chatwoot -> 200 {ok:true}
  POST /webhook/panel-toggle-bot  -> valida secreto -> label `humano` (humano=true) o `bot` (false)
      en TODAS las conversaciones del contacto -> 200 {ok:true}
  Efecto: exactamente el mismo que si la Dra./Irina escribieran desde el WhatsApp del consultorio.
  Con media (imagen / AUDIO / video / documento subido por el panel a Storage `panel-media`): body {telefono, mensaje?,
      media_url (https), media_tipo: image|audio|video|document, filename, autor} -> /send/media type=media_tipo
      (verificado 7/9: 'audio' responde 200; 'ptt' no existe en Evolution GO) -> memoria "[imagen|audio|video|document] <url>\n<caption>".
  Respuestas: 200 ok · 401 secreto incorrecto · 400 pedido mal armado (telefono requerido / mensaje vacio / media_url
      invalida / media_tipo invalido: un tipo desconocido con URL NO cae a image, 7/9) · 502 Evolution no confirmó el envío.
  Compatibilidad: el cambio del 7/9 es hacia atrás compatible (el panel viejo siempre manda media_tipo 'image'), por eso
      el --update del satélite va ANTES del deploy del panel con audio (si no, un audio saldría como type 'image').

SECRETOS: el secreto del panel se genera en --apply, se embebe en el nodo y se escribe en
/opt/nexora-panel/.env.production del VPS por ssh (--write-env). Nunca se imprime ni se guarda acá.
apikey de Evolution y token de Chatwoot se copian EN CALIENTE de nodos vivos del v6.

USO:
  python scripts/create_panel_acciones_staff.py                 # preview
  python scripts/create_panel_acciones_staff.py --apply         # crea (inactivo) + genera secreto en .secret local temporal
  python scripts/create_panel_acciones_staff.py --activate <id>
  python scripts/create_panel_acciones_staff.py --write-env     # agrega N8N_PANEL_WEBHOOK_BASE/SECRET al VPS (usa el secreto generado)
  python scripts/create_panel_acciones_staff.py --recover-secret <id>  # si %TEMP% perdió el secreto: lo copia del nodo vivo (GET)
  python scripts/create_panel_acciones_staff.py --update <id>   # PUT (name/nodes/connections/settings) reusando el secreto local
"""
import argparse, copy, json, os, secrets, subprocess, sys, urllib.request
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
SECRET_FILE = Path(os.environ.get("TEMP", ".")) / "panel_webhook_secret.txt"  # fuera del repo
PG_CRED = {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}
N8N_PUBLIC = "https://n8n.raquelrodriguez.com.ar/webhook"

def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", data=json.dumps(payload).encode() if payload is not None else None,
                                 method=method, headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())

VALIDAR_JS = r"""// Valida el secreto del panel y normaliza el pedido. Header: X-Panel-Secret (n8n lo entrega en minúsculas).
const SECRET = "__PANEL_SECRET__";
const j = $input.first().json || {};
const headers = j.headers || {};
const body = j.body || {};
const url = String(j.webhookUrl || "");
const accion = url.includes("panel-toggle-bot") ? "toggle" : "send";
const ok = !!SECRET && String(headers["x-panel-secret"] || "") === SECRET;
const telefono = String(body.telefono || "").replace(/[^0-9]/g, "");
const mensaje = String(body.mensaje || "").trim();
const humano = body.humano === true || body.humano === "true";
// Media (imagen / audio / video / documento subido desde el panel a Supabase Storage) — opcional. El tipo va tal cual a
// /send/media de Evolution GO (7/9: 'audio' = nota de voz/archivo de audio, 200 OK; 'ptt' no existe). Un tipo desconocido
// con URL es error 400 ('media_tipo invalido'): el panel SIEMPRE manda image|audio, y caer a 'image' mandaría a Evolution
// una URL que no es imagen hacia un paciente real (antes del 7/9 caía a image; ya no protege a nadie).
const TIPOS_MEDIA = ["image", "audio", "document", "video"];
const media_url = String(body.media_url || "").trim();
const media_tipo = !media_url ? "" : (TIPOS_MEDIA.includes(String(body.media_tipo || "")) ? String(body.media_tipo) : "");
// filename saneado a [A-Za-z0-9._-], máximo 80 chars CONSERVANDO la extensión (WhatsApp/Evolution la usan para el mime del audio/documento).
const fnRaw = String(body.filename || "").replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 200);
const fnExt = (fnRaw.match(/\.[A-Za-z0-9]{1,5}$/) || [""])[0];
const filename = (fnRaw.slice(0, fnRaw.length - fnExt.length).slice(0, 80 - fnExt.length) + fnExt) || (media_tipo ? "archivo" : "");
// Autor = usuario logueado en el panel (lucas / irina / raquel); se muestra en la burbuja.
const autorRaw = String(body.autor || "").trim().slice(0, 40);
const autor = autorRaw ? (autorRaw.toLowerCase() === "raquel" ? "Dra. Raquel" : autorRaw.charAt(0).toUpperCase() + autorRaw.slice(1).toLowerCase()) : "la doctora o la secretaria";
let error = null;
if (!ok) error = "unauthorized";
else if (!telefono) error = "telefono requerido";
else if (accion === "send" && !mensaje && !media_url) error = "mensaje vacio";
else if (media_url && !/^https:\/\//.test(media_url)) error = "media_url invalida";
else if (media_url && !media_tipo) error = "media_tipo invalido";
return [{ json: { ok: !error, error, accion, telefono, mensaje, humano, number: telefono, media_url, media_tipo, filename, autor, autor_raw: autorRaw } }];
"""

MEMORIA_JS = r"""// Misma fila que la rama fromMe del v6 (Build fromMe AI memory): el LLM sabe que no es su voz y se calla.
// Con media: el content lleva "[imagen] <url>" / "[audio] <url>" / "[video] <url>" / "[document] <url>" (+ '\n' + caption si hay)
// para que el panel lo renderice como imagen/audio/video/documento también cuando la fila llega vía Logger (que no
// copia additional_kwargs.media_url). Solo 'image' se traduce a 'imagen'; los demás tipos van tal cual (PANEL_MEDIA_RE del panel).
const p = $('Validar secreto').first().json;
const TAG = '[ATENCION HUMANA - mensaje enviado por ' + p.autor + ' desde el PANEL. NO es output tuyo, es un humano atendiendo este chat. Mantente en silencio y NO respondas en este chat hasta que un admin diga /bot on.]: ';
const cuerpo = p.media_url ? ('[' + (p.media_tipo === 'image' ? 'imagen' : p.media_tipo) + '] ' + p.media_url + (p.mensaje ? '\n' + p.mensaje : '')) : p.mensaje;
const message = { type: 'ai', content: TAG + cuerpo, additional_kwargs: { source: 'wa_outbound', from_iri_or_dra: true, from_panel: true, autor: p.autor_raw || null, was_multimedia: !!p.media_url, media_url: p.media_url || null, media_tipo: p.media_tipo || null }, response_metadata: {}, tool_calls: [], invalid_tool_calls: [] };
return [{ json: { session_id: p.telefono, message: JSON.stringify(message) } }];
"""

LABEL_JS = r"""// Label humano/bot en Chatwoot. REGLA (aprendida 5/9): el gate del v6 (Verificar Label Humano) mira
// TODAS las conversaciones del contacto y Auto Reactivar solo limpia las ABIERTAS → un `humano` en una
// conversación resuelta silencia al bot para siempre. Por eso: humano → SOLO la conversación abierta
// (o la más reciente si no hay abierta, igual que CW Pick Conv del v6); bot → se quita humano de TODAS.
const p = $('Validar secreto').first().json;
const TOKEN = "__CW_TOKEN__";
const base = 'https://chat.raquelrodriguez.com.ar/api/v1/accounts/1';
const aHumano = !(p.accion === 'toggle' && p.humano === false);
let contactId = null, convs = [], applied = 0, error = null;
try {
  const s = await this.helpers.httpRequest({ method: 'GET', url: base + '/contacts/search?q=' + p.telefono, headers: { api_access_token: TOKEN }, json: true });
  const c = (s.payload || []).find(x => String(x.phone_number || '').replace(/[^0-9]/g, '').endsWith(p.telefono.slice(-10)));
  if (c) {
    contactId = c.id;
    const r = await this.helpers.httpRequest({ method: 'GET', url: base + '/contacts/' + contactId + '/conversations', headers: { api_access_token: TOKEN }, json: true });
    convs = r.payload || [];
    const post = async (conv, nuevas) => { await this.helpers.httpRequest({ method: 'POST', url: base + '/conversations/' + conv.id + '/labels', headers: { api_access_token: TOKEN, 'Content-Type': 'application/json' }, body: { labels: nuevas }, json: true }); applied++; };
    if (aHumano) {
      const abierta = convs.find(x => x.status === 'open') || convs.slice().sort((a, b) => (b.last_activity_at || 0) - (a.last_activity_at || 0))[0];
      if (abierta) await post(abierta, Array.from(new Set([...(abierta.labels || []).filter(l => l !== 'bot'), 'humano'])));
    } else {
      for (const conv of convs) {
        const actuales = conv.labels || [];
        if (!actuales.includes('humano')) continue;
        await post(conv, actuales.filter(l => l !== 'humano').concat(actuales.includes('bot') ? [] : ['bot']));
      }
    }
  } else { error = 'contact not found'; }
} catch (e) { error = String((e && e.message) || e).slice(0, 200); }
return [{ json: { ok: true, accion: p.accion, telefono: p.telefono, humano: aHumano, contactId, conversaciones: convs.length, applied, error } }];
"""

def build(secret, evo_headers, evo_base, cw_token):
    def C(name, idx=0): return {"node": name, "type": "main", "index": idx}
    def respond(nid, name, pos, code, body):
        return {"id": nid, "name": name, "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1.3, "position": pos,
                "parameters": {"respondWith": "json", "responseBody": body, "options": {"responseCode": code}}}
    nodes = [
        {"id": "wh-send", "name": "Webhook panel-send-human", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [180, 200],
         "webhookId": "panel-send-human", "parameters": {"httpMethod": "POST", "path": "panel-send-human", "responseMode": "responseNode", "options": {}}},
        {"id": "wh-toggle", "name": "Webhook panel-toggle-bot", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [180, 440],
         "webhookId": "panel-toggle-bot", "parameters": {"httpMethod": "POST", "path": "panel-toggle-bot", "responseMode": "responseNode", "options": {}}},
        {"id": "validar", "name": "Validar secreto", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [440, 320],
         "parameters": {"jsCode": VALIDAR_JS.replace("__PANEL_SECRET__", secret)}},
        {"id": "if-ok", "name": "¿Autorizado?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [680, 320],
         "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                       "conditions": [{"id": "c1", "leftValue": "={{ $json.ok }}", "rightValue": True, "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                       "combinator": "and"}, "options": {}}},
        # Secreto incorrecto -> 401 (el panel lo muestra como "sin autorización"); pedido mal armado (teléfono, mensaje vacío,
        # media_url http, media_tipo desconocido) -> 400 con el error en el body (el panel lo muestra como error genérico + detalle).
        {"id": "if-secreto", "name": "¿Sin secreto?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [920, 560],
         "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                       "conditions": [{"id": "c5", "leftValue": "={{ $json.error }}", "rightValue": "unauthorized", "operator": {"type": "string", "operation": "equals"}}],
                                       "combinator": "and"}, "options": {}}},
        respond("resp-401", "Responder 401", [1160, 480], 401, '={{ JSON.stringify({ ok: false, error: $json.error }) }}'),
        respond("resp-400", "Responder 400", [1160, 640], 400, '={{ JSON.stringify({ ok: false, error: $json.error }) }}'),
        {"id": "if-send", "name": "¿Es envío?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [920, 200],
         "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                       "conditions": [{"id": "c2", "leftValue": "={{ $json.accion }}", "rightValue": "send", "operator": {"type": "string", "operation": "equals"}}],
                                       "combinator": "and"}, "options": {}}},
        {"id": "if-media", "name": "¿Con media?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [1160, 200],
         "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                       "conditions": [{"id": "c4", "leftValue": "={{ !!$json.media_url }}", "rightValue": True, "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                       "combinator": "and"}, "options": {}}},
        {"id": "enviar-media", "name": "Enviar Media (staff)", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1400, -60],
         "parameters": {"method": "POST", "url": evo_base + "/send/media", "sendHeaders": True, "headerParameters": copy.deepcopy(evo_headers),
                        "sendBody": True, "specifyBody": "json",
                        "jsonBody": ("={\n  \"number\": {{ JSON.stringify($('Validar secreto').first().json.number) }},\n"
                                     "  \"type\": {{ JSON.stringify($('Validar secreto').first().json.media_tipo) }},\n"
                                     "  \"url\": {{ JSON.stringify($('Validar secreto').first().json.media_url) }},\n"
                                     "  \"caption\": {{ JSON.stringify($('Validar secreto').first().json.mensaje) }},\n"
                                     "  \"filename\": {{ JSON.stringify($('Validar secreto').first().json.filename) }}\n}"),
                        "options": {"response": {"response": {"neverError": True}}, "timeout": 60000}}, "credentials": {}, "onError": "continueRegularOutput"},
        {"id": "enviar", "name": "Enviar WhatsApp (staff)", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1400, 80],
         "parameters": {"method": "POST", "url": evo_base + "/send/text", "sendHeaders": True, "headerParameters": copy.deepcopy(evo_headers),
                        "sendBody": True, "specifyBody": "json",
                        "jsonBody": "={\n  \"number\": {{ JSON.stringify($('Validar secreto').first().json.number) }},\n  \"text\": {{ JSON.stringify($('Validar secreto').first().json.mensaje) }}\n}",
                        "options": {"response": {"response": {"neverError": True}}, "timeout": 30000}}, "credentials": {}, "onError": "continueRegularOutput"},
        {"id": "if-enviado", "name": "¿Enviado?", "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [1640, 20],
         "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                       "conditions": [{"id": "c3", "leftValue": "={{ !!($json.data && $json.data.Info && $json.data.Info.ID) }}", "rightValue": True, "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                       "combinator": "and"}, "options": {}}},
        respond("resp-502", "Responder 502", [1880, 320], 502, '={{ JSON.stringify({ ok: false, error: "evolution_send_failed" }) }}'),
        {"id": "memoria", "name": "Armar fila memoria", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1880, 80], "parameters": {"jsCode": MEMORIA_JS}},
        {"id": "pg", "name": "Guardar en memoria", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": [2120, 80],
         "parameters": {"operation": "executeQuery", "query": "INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)",
                        "options": {"queryReplacement": "={{ $json.session_id }}, ={{ $json.message }}"}},
         "credentials": {"postgres": PG_CRED}, "onError": "continueRegularOutput", "alwaysOutputData": True},
        {"id": "label", "name": "Label Chatwoot", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [2360, 200], "parameters": {"jsCode": LABEL_JS.replace("__CW_TOKEN__", cw_token)}},
        respond("resp-200", "Responder 200", [2600, 200], 200, '={{ JSON.stringify($json) }}'),
    ]
    connections = {
        "Webhook panel-send-human": {"main": [[C("Validar secreto")]]},
        "Webhook panel-toggle-bot": {"main": [[C("Validar secreto")]]},
        "Validar secreto": {"main": [[C("¿Autorizado?")]]},
        "¿Autorizado?": {"main": [[C("¿Es envío?")], [C("¿Sin secreto?")]]},
        "¿Sin secreto?": {"main": [[C("Responder 401")], [C("Responder 400")]]},
        "¿Es envío?": {"main": [[C("¿Con media?")], [C("Label Chatwoot")]]},
        "¿Con media?": {"main": [[C("Enviar Media (staff)")], [C("Enviar WhatsApp (staff)")]]},
        "Enviar Media (staff)": {"main": [[C("¿Enviado?")]]},
        "Enviar WhatsApp (staff)": {"main": [[C("¿Enviado?")]]},
        "¿Enviado?": {"main": [[C("Armar fila memoria")], [C("Responder 502")]]},
        "Armar fila memoria": {"main": [[C("Guardar en memoria")]]},
        "Guardar en memoria": {"main": [[C("Label Chatwoot")]]},
        "Label Chatwoot": {"main": [[C("Responder 200")]]},
    }
    return {"name": "Panel — acciones staff (send-human / toggle-bot)", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}

def live_secrets():
    wf = api(f"/workflows/{env('N8N_WORKFLOW_V6_ID', 'O155MqHgOSaNZ9ye')}")
    names = {n["name"]: n for n in wf["nodes"]}
    enviar = names["Evolution API - Enviar Mensaje"]
    cw = next(h["value"] for h in names["Re-check Humano"]["parameters"]["headerParameters"]["parameters"] if h["name"] == "api_access_token")
    return enviar["parameters"]["headerParameters"], enviar["parameters"]["url"].split("/send/")[0], cw

def recover_secret(wf_id):
    """Copia el secreto del nodo vivo `Validar secreto` (const SECRET = "...") a SECRET_FILE, sin imprimirlo. Solo GET.
    Para cuando %TEMP% se limpió y hay que correr --update sin regenerar el secreto (que obligaría a tocar el env del VPS)."""
    import re
    wf = api(f"/workflows/{wf_id}")
    nodo = next((n for n in wf["nodes"] if n["name"] == "Validar secreto"), None)
    m = re.search(r'const SECRET = "([^"]+)"', (nodo or {}).get("parameters", {}).get("jsCode", ""))
    if not m or m.group(1) in ("", "__PANEL_SECRET__", "***PREVIEW***"): sys.exit("no encontré un secreto válido en el nodo vivo 'Validar secreto'")
    SECRET_FILE.write_text(m.group(1))
    print(f"secreto recuperado del workflow {wf_id} ({len(m.group(1))} chars) -> {SECRET_FILE}. Ahora sí: --update {wf_id}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--activate", metavar="WF_ID"); ap.add_argument("--write-env", action="store_true")
    ap.add_argument("--update", metavar="WF_ID", help="PUT sobre el workflow existente reusando el secreto ya generado")
    ap.add_argument("--recover-secret", metavar="WF_ID", help="copia el secreto del nodo vivo a %%TEMP%%/panel_webhook_secret.txt (GET; no lo imprime)")
    args = ap.parse_args()
    if args.activate:
        r = api(f"/workflows/{args.activate}/activate", "POST"); print(f"activado: {r.get('id')} active={r.get('active')}"); return
    if args.recover_secret:
        recover_secret(args.recover_secret); return
    if args.update:
        if not SECRET_FILE.exists(): sys.exit(f"no hay secreto generado localmente: correr --recover-secret {args.update} (lo copia del nodo vivo) y repetir")
        secret = SECRET_FILE.read_text().strip()
        evo_headers, evo_base, cw_token = live_secrets()
        wf = build(secret, evo_headers, evo_base, cw_token)
        r = api(f"/workflows/{args.update}", "PUT", {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": wf["settings"]})
        print(f"actualizado: {r.get('id')} active={r.get('active')} nodos={len(r.get('nodes', []))}"); return
    if args.write_env:
        if not SECRET_FILE.exists(): sys.exit("no hay secreto generado (correr --apply primero)")
        secret = SECRET_FILE.read_text().strip()
        cmd = (f"grep -q '^N8N_PANEL_WEBHOOK_BASE=' /opt/nexora-panel/.env.production || echo 'N8N_PANEL_WEBHOOK_BASE={N8N_PUBLIC}' >> /opt/nexora-panel/.env.production; "
               f"grep -q '^N8N_PANEL_WEBHOOK_SECRET=' /opt/nexora-panel/.env.production || echo 'N8N_PANEL_WEBHOOK_SECRET={secret}' >> /opt/nexora-panel/.env.production; "
               "grep -cE '^N8N_PANEL_WEBHOOK_(BASE|SECRET)=' /opt/nexora-panel/.env.production")
        r = subprocess.run(["ssh", "-i", os.path.expanduser("~/.ssh/raquel_vps"), "-o", "BatchMode=yes", "root@187.127.0.110", cmd], capture_output=True, text=True)
        print("variables N8N_PANEL_* en el VPS:", r.stdout.strip(), r.stderr.strip()[:200]); return
    evo_headers, evo_base, cw_token = live_secrets()
    secret = secrets.token_urlsafe(32)
    wf = build(secret if args.apply else "***PREVIEW***", evo_headers, evo_base, cw_token)
    print(f"Workflow: '{wf['name']}' — {len(wf['nodes'])} nodos"); [print("  -", n["name"], "|", n["type"].split(".")[-1]) for n in wf["nodes"]]
    if not args.apply: print("(preview — nada creado). --apply crea el workflow y genera el secreto."); return
    creado = api("/workflows", "POST", wf)
    SECRET_FILE.write_text(secret)
    red = json.loads(json.dumps(creado))
    for n in red["nodes"]:
        if "jsCode" in n.get("parameters", {}): n["parameters"]["jsCode"] = n["parameters"]["jsCode"].replace(secret, "***SECRET***").replace(cw_token, "***CW_TOKEN***")
        for h in (n.get("parameters", {}).get("headerParameters", {}) or {}).get("parameters", []) or []:
            if h.get("name", "").lower() == "apikey": h["value"] = "***"
    (ROOT / "workflows" / "history").mkdir(parents=True, exist_ok=True)
    (ROOT / "workflows" / "history" / f"panel_acciones_staff_CREADO_{creado['id']}.json").write_text(json.dumps(red, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nCreado OK -> id={creado['id']} (activo={creado.get('active')}). Secreto guardado (fuera del repo) en {SECRET_FILE}")
    print(f"Siguiente: --activate {creado['id']}  y  --write-env  y recrear el container del panel.")

if __name__ == "__main__":
    main()
