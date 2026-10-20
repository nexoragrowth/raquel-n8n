# -*- coding: utf-8 -*-
"""
apply_health_check_autoreparable.py — 2026-10-08 · el Health Check ("Yjl6kyLnALhIfbFX") pasa a DETECTAR y AUTO-REPARAR el webhook de Evolution.

POR QUÉ (incidente 06-08/10/2026): la instancia `raquel` de Evolution GO quedó conectada con `webhook: ""` → 2 días sin que entre un mensaje a n8n.
El Health Check solo miraba `connected`, así que con la instancia reconectada dijo "healthy". Y mientras estuvo DESCONECTADA (06/10 21:30 → 07/10 18:30 UTC)
sí detectó el problema 43 veces, pero la alerta sale por el MISMO WhatsApp desconectado: Evolution respondió 500 "client is nil" y nadie se enteró.
Causa raíz probable: el banner de reconexión del panel (nexora-whatsapp-agent/lib/evolution.ts) hacía POST /instance/connect con body {} y Connect de
Evolution GO pisa el webhook con "" (corregido en el panel el 08/10, pendiente de deploy).
Lucas: "no puede volver a pasar; el sistema se vendió con soporte hasta febrero, en febrero la doctora queda sola".

QUÉ CAMBIA (la decisión vive en v7/health_core.js, probada offline con tests/test_health_core.mjs):
  1. WEBHOOK + EVENTOS: instancia conectada con webhook != .../webhook/evolution-v2 o sin el evento MESSAGE → POST /instance/connect con el token de la
     instancia + instanceId y body {webhookUrl, subscribe, rabbitmqEnable, websocketEnable, natsEnable} armado con lo que la instancia YA tenía
     (Connect pisa esos 5 campos), espera 5 s, relee /instance/all y alerta "[AUTO-REPARADO] …" o "[ACCIÓN] … no se pudo reparar …".
     Corte de reintentos: 3 fallas seguidas → 1 intento cada 2 h y 1 alerta cada 6 h. 2+ reparaciones en 24 h → "[ACCIÓN] algo lo está borrando".
     Si Evolution cambia el formato (falta `webhook`/`events`) → NO repara a ciegas; 1 alerta cada 6 h.
  2. DESCONEXIÓN: "[ACCIÓN] WhatsApp desconectado: hay que escanear el QR en el panel …" (sin reconectar solo).
  3. SIN TRÁFICO: lun-vie 09-20 (Jujuy), sin feriados, ≥ 6 h HÁBILES sin filas nuevas en mensajes_entrantes_live → "[ACCIÓN] No entra ningún mensaje …"
     (1 cada 6 h). Si la consulta falla 4 veces seguidas → "[AVISO]" 1 vez por día (para que esa red no quede apagada en silencio).
  4. ROBUSTEZ: Check Dentalink / Check Evolution / Re-check siguen de largo ante timeout/DNS/ECONNREFUSED (onError continueRegularOutput +
     alwaysOutputData): antes un timeout cortaba la ejecución sin avisar. Evaluar/Verificar con try/catch: un bug propio sale como alerta "[FALLO TECNICO]".
     Send WA Alert Lucas reintenta 3 veces. executionTimeout 300 s.
  5. OPCIONAL (--mail-a): si el WhatsApp de alerta no sale (el caso del incidente: WhatsApp desconectado), manda la misma alerta por mail con la
     credencial "SMTP account" (nexora.srv@gmail.com) a las direcciones dadas. Sin --mail-a no se agrega (lo decide Lucas).
  Nodos nuevos: Ultimo Entrante (Postgres), Reparar Webhook? (IF), Reparar Webhook (Code), Esperar 5 s (Wait), Re-check Evolution (HTTP, copia de
  Check Evolution con su misma clave, tomada del vivo: no queda en este archivo), Verificar Reparación (Code) [+ Avisar por Mail].
  Modificados: Evaluar Health, Check Dentalink, Check Evolution, Send WA Alert Lucas. Iguales: Cada 30 min, Skip Alert?, Healthy NoOp.
  No se manda staticData en el PUT (para no pisar el estado anti-spam ni el del trigger).
OJO: la URL del webhook está fija en v7/health_core.js (WEBHOOK). Si se cambia la URL a propósito, cambiar ahí PRIMERO y re-aplicar este script;
     si no, el Health Check la vuelve a poner en ≤ 30 min.
VOLVER ATRÁS: python scripts/restaurar_workflow.py workflows/history/<backup PRE> --apply

USO:  python scripts/apply_health_check_autoreparable.py                       # simulación: GET del vivo, diff, corre los Code nodes nuevos con datos reales
      python scripts/apply_health_check_autoreparable.py --apply               # lo mismo + backup PRE → PUT → re-GET y verificación → backup POST
      python scripts/apply_health_check_autoreparable.py --apply --mail-a lucas@x.com,doctora@y.com    # + canal de mail si falla el WhatsApp
Regla del proyecto: el --apply lo corre Lucas.
"""
import argparse, copy, difflib, json, re, subprocess, sys, time, urllib.request, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require
from v7_lib import CRED_POSTGRES, core

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
HC = "Yjl6kyLnALhIfbFX"
PUT_KEYS = ("name", "nodes", "connections", "settings")   # staticData NO: guarda el anti-spam y el estado del trigger
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
EXECUTION_TIMEOUT = 300
EXISTENTES = ["Cada 30 min", "Check Dentalink", "Check Evolution", "Evaluar Health", "Skip Alert?", "Send WA Alert Lucas", "Healthy NoOp"]
MODIFICADOS = ["Evaluar Health", "Check Dentalink", "Check Evolution", "Send WA Alert Lucas"]
MARCA_VIEJA = "Evolution GO: GET /instance/all -> {data: [{name, connected: bool, ...}]}"
MARCA_NUEVA = "Health Check auto-reparable (08/10/2026)"
NUEVOS = ["Ultimo Entrante", "Reparar Webhook?", "Reparar Webhook", "Esperar 5 s", "Re-check Evolution", "Verificar Reparación"]
MAIL = "Avisar por Mail"
CRED_SMTP = {"smtp": {"id": "mCTKWsjC4QAORquq", "name": "SMTP account"}}   # la que usa "[NEXORA-DEMO] Guía Nutri" (s76M7cgmbXDZgqAN)
MAIL_DE = "nexora.srv@gmail.com"
SEGUIR = {"onError": "continueRegularOutput", "alwaysOutputData": True}   # timeout/DNS/ECONNREFUSED → item {error}, la ejecución sigue
CAMPOS_NODO = ("type", "typeVersion", "parameters", "credentials", "onError", "alwaysOutputData", "retryOnFail", "maxTries", "waitBetweenTries")

QUERY = "SELECT max(created_at) AS ultimo, now() AS ahora FROM mensajes_entrantes_live"

EVALUAR_JS = f"""// {MARCA_NUEVA}. Decide HealthCore (v7/health_core.js, test offline tests/test_health_core.mjs). Aplicado por scripts/apply_health_check_autoreparable.py.
// Sale por "Reparar Webhook?": reparar=true → POST /instance/connect y verificación; reparar=false → el item de siempre {{healthy, skip_alert, alert_message, remoteJid}}.
const sd = $getWorkflowStaticData('global');
let token = '';
try {{
  let ultimo = null, consultaOk = false;
  try {{ const q = $('Ultimo Entrante').first().json || {{}}; consultaOk = q.ahora !== undefined && !q.error; ultimo = q.ultimo || null; }} catch (e) {{ consultaOk = false; }}
  const evo = $('Check Evolution').first().json;
  try {{ token = String(((evo && Array.isArray(evo.data) ? evo.data : []).find((i) => i && i.name === HealthCore.INSTANCIA) || {{}}).token || ''); }} catch (e) {{}}
  const r = HealthCore.evaluar({{ dentalink: $('Check Dentalink').first().json, evolution: evo, ultimo, consultaOk, ahora: Date.now(), estado: {{ ...sd }} }});
  Object.assign(sd, r.estado);   // anti-spam, corte de reintentos y contador de la consulta
  if (r.reparar) return [{{ json: {{ reparar: true, lineas: r.lineas, cuerpo: r.cuerpo }} }}];
  return [{{ json: {{ reparar: false, ...HealthCore.salida(r.lineas, Date.now()) }} }}];
}} catch (e) {{
  const msg = String((e && (e.stack || e.message)) || e).slice(0, 300);
  return [{{ json: {{ reparar: false, ...HealthCore.salida(['[FALLO TECNICO] El Health Check falló por dentro (Evaluar Health): ' + (token ? msg.split(token).join('***') : msg) + '. Revisar el workflow en n8n.'], Date.now()) }} }}];
}}"""

REPARAR_JS = """// Repone el webhook de la instancia (mismo pedido que scripts/apply_webhook_evolution.py, 08/10/2026). Con la clave global da 401: va el TOKEN de la instancia.
// El body lo arma HealthCore.cuerpoReparacion con lo que la instancia ya tenía (Connect de Evolution GO pisa webhook/events/rabbitmq/websocket/nats).
// El token se lee de la salida de "Check Evolution" y NUNCA se devuelve ni se loguea (si aparece en un error, se tapa).
const ev = $('Check Evolution').first().json || {};
const inst = (Array.isArray(ev.data) ? ev.data : []).find((i) => i && i.name === HealthCore.INSTANCIA) || {};
const token = String(inst.token || '');
const tapar = (s) => (token ? String(s).split(token).join('***') : String(s));
const cuerpo = $input.first().json.cuerpo || HealthCore.cuerpoReparacion(inst);
let reparacion;
if (!token || !inst.id) reparacion = { status: 0, error: 'la instancia no trae token o id' };
else {
  try {
    const r = await this.helpers.httpRequest({
      method: 'POST', url: 'https://evo.raquelrodriguez.com.ar/instance/connect',
      headers: { apikey: token, instanceId: inst.id, 'Content-Type': 'application/json' },
      body: cuerpo, json: true, returnFullResponse: true, timeout: 20000,
    });
    reparacion = { status: Number(r && r.statusCode) || 200 };
  } catch (e) {
    reparacion = { status: Number(e.httpCode) || Number(e.response && e.response.status) || 0, error: tapar(e.description || e.message || e).slice(0, 200) };
  }
}
return [{ json: { reparacion } }];"""

VERIFICAR_JS = """// Relee /instance/all (nodo "Re-check Evolution") y arma la alerta: [AUTO-REPARADO] o [ACCIÓN]. Sale al mismo "Skip Alert?" de siempre.
// Las líneas previas (p. ej. Dentalink caído) se leen de "Evaluar Health", así no se pierden si "Reparar Webhook" tiró error.
const sd = $getWorkflowStaticData('global');
let previas = [];
try { previas = $('Evaluar Health').first().json.lineas || []; } catch (e) { previas = []; }
try {
  let rep = {};
  try { rep = $('Reparar Webhook').first().json || {}; } catch (e) { rep = {}; }
  const v = HealthCore.verificar({
    reparacion: rep.reparacion || { status: 0, error: rep.error ? String(rep.error).slice(0, 200) : 'el nodo Reparar Webhook falló' },
    recheck: $input.first().json, estado: { ...sd }, ahora: Date.now(),
  });
  Object.assign(sd, v.estado);
  return [{ json: HealthCore.salida([...previas, ...v.lineas], Date.now()) }];
} catch (e) {
  return [{ json: HealthCore.salida([...previas, '[FALLO TECNICO] El Health Check falló por dentro (Verificar Reparación): ' + String((e && e.message) || e).slice(0, 200) + '. Revisar el workflow en n8n.'], Date.now()) }];
}"""


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def nodo(nombre, tipo, version, params, pos, **extra):
    return {"parameters": params, "id": str(uuid.uuid4()), "name": nombre, "type": tipo, "typeVersion": version, "position": pos, **extra}


def salidas(con, nombre):
    return [[d["node"] for d in o] for o in con.get(nombre, {}).get("main", [])]


def construir(wf, mail_a=None):
    n = {x["name"]: x for x in wf["nodes"]}
    if any(x in n for x in NUEVOS) or MARCA_NUEVA in n.get("Evaluar Health", {}).get("parameters", {}).get("jsCode", ""):
        sys.exit("Nada que hacer: el Health Check ya es auto-reparable.")
    faltan = [x for x in EXISTENTES if x not in n]
    if faltan or len(wf["nodes"]) != len(EXISTENTES):
        sys.exit(f"ABORTO: el Health Check no tiene los nodos esperados (faltan {faltan}, total {len(wf['nodes'])}). ¿Otra sesión lo cambió?")
    if MARCA_VIEJA not in n["Evaluar Health"]["parameters"].get("jsCode", ""):
        sys.exit("ABORTO: el código de 'Evaluar Health' no es el esperado. Revisar a mano.")
    esperadas = {"Cada 30 min": [["Check Dentalink"]], "Check Dentalink": [["Check Evolution"]], "Check Evolution": [["Evaluar Health"]],
                 "Evaluar Health": [["Skip Alert?"]], "Skip Alert?": [["Healthy NoOp"], ["Send WA Alert Lucas"]]}
    for a, bs in esperadas.items():
        if salidas(wf["connections"], a) != bs:
            sys.exit(f"ABORTO: la conexión de '{a}' no es la esperada ({salidas(wf['connections'], a)} != {bs}).")
    ce = n["Check Evolution"]["parameters"]
    if ce.get("url") != "https://evo.raquelrodriguez.com.ar/instance/all" or not any(
            h.get("name") == "apikey" and h.get("value") for h in ce.get("headerParameters", {}).get("parameters", [])):
        sys.exit("ABORTO: 'Check Evolution' ya no es GET /instance/all con header apikey (Re-check Evolution se copia de él).")
    if "$json.skip_alert" not in json.dumps(n["Skip Alert?"]["parameters"]):
        sys.exit("ABORTO: 'Skip Alert?' ya no decide por $json.skip_alert.")

    nuevo = copy.deepcopy(wf)
    m = {x["name"]: x for x in nuevo["nodes"]}
    hc = core("health_core")
    m["Evaluar Health"]["parameters"]["jsCode"] = hc + EVALUAR_JS
    m["Check Dentalink"].update(SEGUIR)
    m["Check Evolution"].update(SEGUIR)
    m["Send WA Alert Lucas"].update({"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 5000})
    skip = m["Skip Alert?"]["parameters"]
    recheck = copy.deepcopy(m["Check Evolution"])   # misma URL y misma clave global (del vivo), ya con SEGUIR
    recheck.update({"id": str(uuid.uuid4()), "name": "Re-check Evolution", "position": [1520, 620]})
    nuevo["nodes"] += [
        nodo("Ultimo Entrante", "n8n-nodes-base.postgres", 2.5, {"operation": "executeQuery", "query": QUERY, "options": {}}, [530, 520],
             credentials=CRED_POSTGRES, **SEGUIR),
        nodo("Reparar Webhook?", "n8n-nodes-base.if", 2, {
            "conditions": {"options": copy.deepcopy(skip["conditions"]["options"]), "combinator": "and", "conditions": [{
                "id": "r1", "leftValue": "={{ $json.reparar }}", "rightValue": True,
                "operator": {"type": "boolean", "operation": "true", "singleValue": True}}]}, "options": {}}, [750, 520]),
        nodo("Reparar Webhook", "n8n-nodes-base.code", 2, {"jsCode": hc + REPARAR_JS}, [970, 620], onError="continueRegularOutput"),
        nodo("Esperar 5 s", "n8n-nodes-base.wait", 1.1, {"amount": 5, "unit": "seconds"}, [1190, 620], webhookId=str(uuid.uuid4())),
        recheck,
        nodo("Verificar Reparación", "n8n-nodes-base.code", 2, {"jsCode": hc + VERIFICAR_JS}, [1740, 620]),
    ]
    c = nuevo["connections"]
    link = lambda *dst: {"main": [[{"node": d, "type": "main", "index": 0} for d in o] for o in dst]}
    c["Check Evolution"] = link(["Ultimo Entrante"])
    c["Ultimo Entrante"] = link(["Evaluar Health"])
    c["Evaluar Health"] = link(["Reparar Webhook?"])
    c["Reparar Webhook?"] = link(["Reparar Webhook"], ["Skip Alert?"])   # salida 0 = true, salida 1 = false
    c["Reparar Webhook"] = link(["Esperar 5 s"])
    c["Esperar 5 s"] = link(["Re-check Evolution"])
    c["Re-check Evolution"] = link(["Verificar Reparación"])
    c["Verificar Reparación"] = link(["Skip Alert?"])
    if mail_a:
        # Segundo canal: si el WhatsApp de alerta no sale (después de 3 intentos), la misma alerta va por mail. Salida 1 de Send WA = error.
        m["Send WA Alert Lucas"]["onError"] = "continueErrorOutput"
        nuevo["nodes"].append(nodo(MAIL, "n8n-nodes-base.emailSend", 2.1, {
            "fromEmail": MAIL_DE, "toEmail": mail_a,
            "subject": "Áurea (Dra. Raquel) — alerta del Health Check del bot de WhatsApp",
            "emailFormat": "text",
            "text": "={{ 'Esta alerta no se pudo mandar por WhatsApp (lo más probable: el WhatsApp de la clínica está desconectado; "
                    "hay que escanear el QR en el panel, Conversaciones -> banner de WhatsApp).\\n\\n' + $('Skip Alert?').item.json.alert_message }}",
            "options": {"appendAttribution": False}}, [1300, 500], credentials=CRED_SMTP, onError="continueRegularOutput"))
        c["Send WA Alert Lucas"] = link([], [MAIL])
    nuevo.setdefault("settings", {})["executionTimeout"] = EXECUTION_TIMEOUT
    return nuevo


def aristas(con):
    return sorted(f"{a} [{i}] → {d['node']}" for a, v in con.items() for i, o in enumerate(v.get("main", [])) for d in o)


def settings_put(wf):
    return {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}


def diff(wf, nuevo):
    viejos = {x["name"]: x for x in wf["nodes"]}
    print(f"Health Check active={wf.get('active')} nodos {len(wf['nodes'])} → {len(nuevo['nodes'])} versionId={str(wf.get('versionId'))[:8]}\n")
    for x in nuevo["nodes"]:
        v = viejos.get(x["name"])
        estado = "NUEVO     " if v is None else ("MODIFICADO" if v != x else "igual     ")
        extra = {k: x[k] for k in ("onError", "alwaysOutputData", "retryOnFail", "maxTries", "credentials") if k in x and (v is None or v.get(k) != x[k])}
        print(f"  {estado} {x['name']:<22} {x['type'].split('.')[-1]:<13} {json.dumps(extra, ensure_ascii=False) if extra else ''}")
    a, b = aristas(wf["connections"]), aristas(nuevo["connections"])
    print("\n--- conexiones")
    for l in difflib.unified_diff(a, b, "antes", "después", lineterm="", n=0):
        if not l.startswith("@@"): print("  " + l)
    hc = core("health_core")
    print(f"\n--- Evaluar Health: el código viejo ({len(viejos['Evaluar Health']['parameters']['jsCode'])} car.) se reemplaza por "
          f"health_core.js ({hc.count(chr(10))} líneas, inlineado) + este pegamento:")
    print("\n".join("    + " + l for l in EVALUAR_JS.splitlines()))
    print("\n--- Reparar Webhook (Code, health_core.js + ):\n" + "\n".join("    + " + l for l in REPARAR_JS.splitlines()))
    print("\n--- Verificar Reparación (Code, health_core.js + ):\n" + "\n".join("    + " + l for l in VERIFICAR_JS.splitlines()))
    print(f"\n--- Ultimo Entrante (Postgres {CRED_POSTGRES['postgres']['name']}): {QUERY}")
    mail = next((x for x in nuevo["nodes"] if x["name"] == MAIL), None)
    print(f"--- {MAIL}: " + (f"a {mail['parameters']['toEmail']} desde {MAIL_DE} (SMTP account) cuando Send WA Alert Lucas falla 3 veces" if mail
                         else "NO se agrega (sin --mail-a): si WhatsApp está desconectado, la alerta sigue sin poder salir"))
    s_old = wf.get("settings") or {}
    s_new = settings_put(nuevo)
    print(f"--- settings que viajan en el PUT: {s_new}  (se descartan por la whitelist: {sorted(set(s_old) - set(s_new))})  · staticData: no se envía")


# Corre los 3 Code nodes NUEVOS tal cual quedan en el workflow, con stubs de n8n ($, $input, $getWorkflowStaticData, this.helpers) y SIN red.
# Entradas reales: la última ejecución del Health Check (Check Dentalink / Check Evolution) + max(created_at) de mensajes_entrantes_live.
# Solo imprime booleanos sobre el token (nunca su valor). `checks` son las condiciones que tienen que dar true para que se permita el PUT.
HARNESS = r"""
const fs = require('fs');
const D = JSON.parse(fs.readFileSync(0, 'utf8'));
const AF = Object.getPrototypeOf(async function () {}).constructor;
async function correr(codigo, nodos, input, sd, helpers) {
  const $ = (n) => { if (!(n in nodos)) throw new Error('unexecuted ' + n); return { first: () => ({ json: nodos[n] }) }; };
  const items = [{ json: input }];
  const fn = new AF('$', '$input', '$getWorkflowStaticData', 'console', codigo);
  return (await fn.call({ helpers }, $, { first: () => items[0], all: () => items }, () => sd, { log() {} }))[0].json;
}
const cl = (x) => JSON.parse(JSON.stringify(x));
(async () => {
  const out = {}; const k = {};
  const token = ((D.evo.data || []).find((i) => i.name === 'raquel') || {}).token || '';
  const limpio = (x) => !token || !JSON.stringify(x).includes(token);
  const base = { 'Check Dentalink': D.dentalink, 'Check Evolution': D.evo, 'Ultimo Entrante': D.ultimo };
  const real = (D.evo.data || []).find((i) => i.name === 'raquel') || {};
  // A) estado real de ahora (se espera sano: si no, el PUT igual es válido pero hay que mirar por qué)
  const sd = {};
  out.real = await correr(D.evaluar, base, {}, sd, {});
  out.real_staticData = sd;
  k.real_sin_reparar = out.real.reparar === false;
  // B) el incidente: webhook vacío → repara → verificación con re-lectura OK y con re-lectura todavía vacía
  const roto = cl(D.evo); const ri = roto.data.find((i) => i.name === 'raquel'); const bien = ri.webhook; ri.webhook = '';
  const nb = { ...base, 'Check Evolution': roto };
  const sdB = {};
  const e = await correr(D.evaluar, nb, {}, sdB, {});
  let pedido = null;
  const helpers = { httpRequest: async (o) => { pedido = o; return { statusCode: 200, body: {} }; } };
  const rep = await correr(D.reparar, nb, e, {}, helpers);
  out.incidente = { evaluar: e, reparar_salida: rep, pedido: pedido && { method: pedido.method, url: pedido.url, body: pedido.body,
    header_apikey_es_token_instancia: pedido.headers.apikey === ri.token, header_instanceId_ok: pedido.headers.instanceId === ri.id } };
  k.incidente_repara = e.reparar === true;
  k.incidente_pedido_ok = !!pedido && pedido.method === 'POST' && pedido.url === 'https://evo.raquelrodriguez.com.ar/instance/connect'
    && pedido.headers.apikey === ri.token && pedido.headers.instanceId === ri.id && pedido.body.webhookUrl === bien
    && Array.isArray(pedido.body.subscribe) && pedido.body.subscribe.includes('MESSAGE')
    && String(real.events || '').split(',').filter(Boolean).every((x) => pedido.body.subscribe.includes(x.trim().toUpperCase()))
    && ['rabbitmqEnable', 'websocketEnable', 'natsEnable'].every((x) => pedido.body[x] === String(real[x] == null ? '' : real[x]));
  const okRe = cl(roto); okRe.data.find((i) => i.name === 'raquel').webhook = bien;
  const nv = { ...nb, 'Evaluar Health': e, 'Reparar Webhook': rep };
  const sdOk = { repFallas: 2 };
  out.verificar_ok = await correr(D.verificar, nv, okRe, sdOk, {});
  k.verificar_ok_sano = out.verificar_ok.healthy === true && out.verificar_ok.skip_alert === false && /AUTO-REPARADO/.test(out.verificar_ok.alert_message) && sdOk.repFallas === 0;
  const sdF = {};
  out.verificar_falla = await correr(D.verificar, nv, roto, sdF, {});
  k.verificar_falla_alerta = out.verificar_falla.healthy === false && /\[ACCIÓN\] Webhook de WhatsApp roto/.test(out.verificar_falla.alert_message) && sdF.repFallas === 1;
  // C) la reparación tira error con el token en el mensaje → se tapa
  const rep2 = await correr(D.reparar, nb, e, {}, { httpRequest: async () => { const x = new Error('401 not authorized ' + token); x.httpCode = '401'; throw x; } });
  out.reparar_error = { status: rep2.reparacion.status, tapado: limpio(rep2) };
  k.reparar_error_tapado = rep2.reparacion.status === 401 && limpio(rep2);
  // D) events vacío con webhook bien → repara con MESSAGE
  const sinEv = cl(D.evo); sinEv.data.find((i) => i.name === 'raquel').events = '';
  const eEv = await correr(D.evaluar, { ...base, 'Check Evolution': sinEv }, {}, {}, {});
  k.events_vacio_repara = eEv.reparar === true && eEv.cuerpo.subscribe.includes('MESSAGE');
  // E) timeout de Check Evolution / Dentalink (onError → item {error}) → alerta, no se cae
  const eTo = await correr(D.evaluar, { ...base, 'Check Evolution': { error: 'timeout of 10000ms exceeded' }, 'Check Dentalink': { error: 'ETIMEDOUT' } }, {}, {}, {});
  k.timeout_alerta = eTo.reparar === false && eTo.skip_alert === false && /Evolution \(WhatsApp\) no responde/.test(eTo.alert_message) && /Dentalink/.test(eTo.alert_message);
  // F) "Reparar Webhook" tiró error (salida {error}) + Dentalink caído → la línea de Dentalink NO se pierde
  const eDl = await correr(D.evaluar, { ...nb, 'Check Dentalink': { error: 'ETIMEDOUT' } }, {}, {}, {});
  const vDl = await correr(D.verificar, { ...nb, 'Evaluar Health': eDl, 'Reparar Webhook': { error: 'boom' } }, okRe, {}, {});
  k.lineas_previas_conservadas = /Dentalink/.test(vDl.alert_message) && /AUTO-REPARADO/.test(vDl.alert_message);
  // G) Evaluar con una entrada que lo hace explotar → [FALLO TECNICO], no una ejecución muerta
  const eBoom = await correr(D.evaluar, { ...base, 'Check Evolution': { get data() { throw new Error('boom'); } } }, {}, {}, {});
  k.bug_interno_alerta = eBoom.skip_alert === false && /FALLO TECNICO/.test(eBoom.alert_message);
  out.todo_sin_token = limpio(out);
  k.todo_sin_token = out.todo_sin_token;
  out.checks = k;
  console.log(JSON.stringify(out, null, 1));
})().catch((e) => { console.log('ERROR HARNESS', e.stack); process.exit(1); });
"""


def simular_con_datos_reales(nuevo):
    """Devuelve el dict de checks (todos tienen que ser True) o None si no se pudo simular."""
    ex = api(f"/executions?workflowId={HC}&limit=1&status=success").get("data", [])
    if not ex:
        print("(no hay ejecución exitosa reciente para simular)")
        return None
    det = api(f"/executions/{ex[0]['id']}?includeData=true")
    rd = det["data"]["resultData"]["runData"]
    j = lambda n: rd[n][0]["data"]["main"][0][0]["json"]
    try:
        sys.path.insert(0, str(ROOT / "tests"))
        from retrospectiva_v7 import conectar
        cur = conectar().cursor()
        cur.execute(QUERY)
        u, a = cur.fetchone()
        ultimo = {"ultimo": u.isoformat() if u else None, "ahora": a.isoformat()}
    except Exception as e:  # noqa: BLE001
        ultimo = {"error": f"no pude consultar la base local: {e}"[:200]}
    m = {x["name"]: x for x in nuevo["nodes"]}
    datos = {"dentalink": j("Check Dentalink"), "evo": j("Check Evolution"), "ultimo": ultimo,
             "evaluar": m["Evaluar Health"]["parameters"]["jsCode"], "reparar": m["Reparar Webhook"]["parameters"]["jsCode"],
             "verificar": m["Verificar Reparación"]["parameters"]["jsCode"]}
    print(f"\n=== Simulación de los Code nodes nuevos con datos reales (ejecución {ex[0]['id']} de {ex[0]['startedAt']}; último entrante: {ultimo})")
    r = subprocess.run(["node", "-e", HARNESS], input=json.dumps(datos), capture_output=True, text=True, encoding="utf-8")
    print(r.stdout or r.stderr)
    try:
        return json.loads(r.stdout)["checks"]
    except Exception:  # noqa: BLE001
        return None


def comparar_nodo(esperado, real):
    return [k for k in CAMPOS_NODO if esperado.get(k) != real.get(k)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--mail-a", default="", help="direcciones separadas por coma para el canal de mail si falla el WhatsApp (opcional)")
    a = ap.parse_args()
    mail_a = ",".join(x.strip() for x in a.mail_a.split(",") if x.strip())
    if mail_a and not all(re.fullmatch(r"[^@\s,]+@[^@\s,]+\.[^@\s,]+", x) for x in mail_a.split(",")):
        sys.exit(f"ABORTO: --mail-a no parece una lista de mails: {mail_a}")
    t = subprocess.run(["node", str(ROOT / "tests" / "test_health_core.mjs")], capture_output=True, text=True, encoding="utf-8")
    print("test offline health_core:", (t.stdout.strip().splitlines() or ["?"])[-1])
    if t.returncode != 0:
        sys.exit(t.stdout + t.stderr + "\nABORTO: tests/test_health_core.mjs falla.")
    wf = api(f"/workflows/{HC}")
    nuevo = construir(wf, mail_a)
    diff(wf, nuevo)
    checks = simular_con_datos_reales(nuevo)
    malos = ["(no se pudo simular)"] if checks is None else [k for k, v in checks.items() if v is not True]
    print("=== checks de la simulación:", "TODOS OK" if not malos else f"FALLAN {malos}")
    if not a.apply:
        print("\n[SIMULACION] No se aplicó nada. Para aplicar: python scripts/apply_health_check_autoreparable.py --apply [--mail-a a@x.com,b@y.com]")
        return
    if malos:
        sys.exit("ABORTO: la simulación de los Code nodes con datos reales no dio lo esperado. No se tocó nada.")
    HIST.mkdir(parents=True, exist_ok=True)
    pre = HIST / f"{HC}_PRE_health_autoreparable_{int(time.time())}.json"
    pre.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n1) backup:", pre.relative_to(ROOT))
    if api(f"/workflows/{HC}").get("versionId") != wf.get("versionId"):
        sys.exit("ABORTO: el Health Check cambió mientras preparaba el PUT. No se tocó nada.")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = settings_put(nuevo)
    api(f"/workflows/{HC}", method="PUT", payload=body)
    post = api(f"/workflows/{HC}")
    post_f = HIST / f"{HC}_POST_health_autoreparable_{int(time.time())}.json"
    post_f.write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
    pn = {x["name"]: x for x in post["nodes"]}
    esperados = {x["name"]: x for x in nuevo["nodes"]}
    difieren = {nm: comparar_nodo(x, pn[nm]) for nm, x in esperados.items() if nm in pn and comparar_nodo(x, pn[nm])}
    con_ok = aristas(post["connections"]) == aristas(nuevo["connections"])
    ok = (sorted(pn) == sorted(esperados) and not difieren and con_ok and post.get("active") is True
          and MARCA_NUEVA in pn["Evaluar Health"]["parameters"]["jsCode"]
          and (post.get("settings") or {}).get("executionTimeout") == EXECUTION_TIMEOUT)
    print(f"2) verificación: nodos {len(pn)} (esperados {len(esperados)}) | activo {post.get('active')} | conexiones = las esperadas: {con_ok} | "
          f"executionTimeout {(post.get('settings') or {}).get('executionTimeout')} | campos distintos de lo enviado: {difieren or 'ninguno'}")
    print("   backup POST:", post_f.relative_to(ROOT))
    if not ok:
        sys.exit(f"ATENCION: la verificación no dio lo esperado (ver arriba qué difiere). Si es grave, restaurar con:\n"
                 f"  python scripts/restaurar_workflow.py {pre.relative_to(ROOT).as_posix()} --apply")
    print("Aplicado OK. Corre solo cada 30 min; para verlo ya: 'Execute workflow' en la UI de n8n y mirar la ejecución "
          "(con todo sano termina en Healthy NoOp y no manda nada).")


if __name__ == "__main__":
    main()
