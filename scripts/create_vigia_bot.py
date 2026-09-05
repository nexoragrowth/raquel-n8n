# -*- coding: utf-8 -*-
"""
create_vigia_bot.py — crea "Áurea — Vigía (triaje + v6 + entrada)": cada 15 min revisa 3 cosas y,
si algo está mal, le avisa a Lucas por WhatsApp (una vez por hora por tipo de alerta, no spam).

Pedido de Lucas (5/9): "quiero que quede re contra funcional, sin caídas" → que cuando algo falle
se entere él primero, no en una demo. Complementa al Health Check (que solo mira 'connected').

  A) TRIAJE DEGRADADO: filas en triaje_urgencias_log de los últimos 20 min con razon
     error_llm* / config_no_disponible / envio_fallo* / NOTIFY_FALLO / sin_evaluacion /
     ruta_pre_desconocida → el triaje está cayendo al fallback (escala igual, pero algo falla).
  B) v6 CON ERRORES: ejecuciones del v6 con status error en los últimos 20 min (API de n8n).
  C) INSTANCIA SORDA: 0 mensajes entrantes (type human en n8n_chat_histories) en las últimas 3 h
     en horario de clínica (lun-vie 8-20 hs, sáb 8-13 hs ART) aunque Evolution diga 'connected'.

Dedupe de alertas con $getWorkflowStaticData (una alerta por clave cada 60 min). Nace INACTIVO.
La API key de n8n se copia del .env local al nodo en --apply (no queda en este archivo).

Uso: python scripts/create_vigia_bot.py [--apply] [--activate <id>] [--update <id>]
"""
import argparse, json, os, sys, urllib.request
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
PG_CRED = {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}
LUCAS = "5491161461034"

def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", data=json.dumps(payload).encode() if payload is not None else None,
                                 method=method, headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())

QUERY = """
SELECT
  (SELECT count(*) FROM triaje_urgencias_log
     WHERE created_at > NOW() - INTERVAL '20 minutes'
       AND (razon ILIKE 'error_llm%' OR razon ILIKE 'config_no_disponible%' OR razon ILIKE 'envio_fallo%'
            OR razon ILIKE '%NOTIFY_FALLO%' OR razon ILIKE 'sin_evaluacion%' OR razon ILIKE 'ruta_pre_desconocida%'
            OR razon ILIKE 'evaluar_run_mismatch%')) AS triaje_degradado,
  (SELECT string_agg(left(razon, 60), ' | ') FROM (SELECT razon FROM triaje_urgencias_log
     WHERE created_at > NOW() - INTERVAL '20 minutes'
       AND (razon ILIKE 'error_llm%' OR razon ILIKE 'config_no_disponible%' OR razon ILIKE 'envio_fallo%' OR razon ILIKE '%NOTIFY_FALLO%')
     ORDER BY id DESC LIMIT 3) t) AS triaje_razones,
  (SELECT count(*) FROM n8n_chat_histories WHERE message->>'type' = 'human' AND created_at > NOW() - INTERVAL '3 hours') AS entrantes_3h,
  (SELECT max(created_at) FROM n8n_chat_histories WHERE message->>'type' = 'human') AS ultimo_entrante,
  (SELECT activo FROM triaje_config WHERE id = 1) AS triaje_activo,
  (SELECT count(*) FROM triaje_videos WHERE activo) AS videos_activos,
  NOW() AS ahora
"""

EVAL_JS = r"""// Evalúa las 3 señales y decide qué alertas mandar (dedupe 60 min por clave con staticData).
const q = $('Query señales').first().json || {};
let execs = [];
try { execs = ($('Ejecuciones v6 con error').first().json || {}).data || []; } catch (e) { execs = []; }
const now = new Date();
const art = new Date(now.getTime() - 3 * 3600 * 1000);   // ART = UTC-3
const dow = art.getUTCDay(); const hora = art.getUTCHours();
const horarioClinica = (dow >= 1 && dow <= 5 && hora >= 8 && hora < 20) || (dow === 6 && hora >= 8 && hora < 13);
const alertas = [];
if (Number(q.triaje_degradado) > 0) {
  alertas.push({ clave: 'triaje_degradado', texto: `⚠️ Triaje degradado: ${q.triaje_degradado} caso(s) cayeron al fallback en los últimos 20 min (escalaron igual, pero algo falla).\nRazones: ${q.triaje_razones || 'ver triaje_urgencias_log'}` });
}
const errs20 = execs.filter(e => e.startedAt && (now - new Date(e.startedAt)) < 20 * 60 * 1000);
if (errs20.length > 0) {
  alertas.push({ clave: 'v6_errores', texto: `🚨 El bot (v6) tuvo ${errs20.length} ejecución(es) con ERROR en los últimos 20 min. IDs: ${errs20.slice(0, 3).map(e => e.id).join(', ')}. Revisar en n8n.` });
}
if (horarioClinica && Number(q.entrantes_3h) === 0) {
  const ult = q.ultimo_entrante ? new Date(q.ultimo_entrante).toISOString().slice(11, 16) + ' UTC' : 'nunca';
  alertas.push({ clave: 'instancia_sorda', texto: `🔇 Posible instancia sorda: 0 mensajes entrantes en 3 h dentro del horario de la clínica (último: ${ult}). Evolution puede decir 'connected' igual. Probar mandando un mensaje al número de la clínica.` });
}
if (q.triaje_activo === true && Number(q.videos_activos) === 0) {
  alertas.push({ clave: 'triaje_sin_videos', texto: '⚠️ triaje_config.activo=true pero no hay ningún video activo en triaje_videos: todo escala.' });
}
const st = $getWorkflowStaticData('global');
st.last = st.last || {};
const mandar = [];
for (const a of alertas) {
  const prev = st.last[a.clave] ? new Date(st.last[a.clave]).getTime() : 0;
  if (now.getTime() - prev > 60 * 60 * 1000) { mandar.push(a); st.last[a.clave] = now.toISOString(); }
}
if (!mandar.length) return [];
const texto = '👁️ *Vigía Asiri*\n\n' + mandar.map(a => a.texto).join('\n\n') + `\n\n(entrantes 3h: ${q.entrantes_3h}, triaje activo: ${q.triaje_activo}, videos activos: ${q.videos_activos})`;
return [{ json: { texto, numero: "__LUCAS__" } }];
"""

def build(n8n_key, evo_headers, evo_base):
    import copy
    def C(name, idx=0): return {"node": name, "type": "main", "index": idx}
    nodes = [
        {"id": "cron", "name": "Cada 15 min", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [180, 300],
         "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "*/15 * * * *"}]}}},
        {"id": "wh", "name": "Webhook Manual Vigía", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [180, 480],
         "webhookId": "trigger-vigia-manual", "parameters": {"httpMethod": "POST", "path": "trigger-vigia-manual", "responseMode": "onReceived", "options": {}}},
        {"id": "q", "name": "Query señales", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": [440, 380],
         "parameters": {"operation": "executeQuery", "query": QUERY.strip(), "options": {}}, "credentials": {"postgres": PG_CRED},
         "onError": "continueRegularOutput", "alwaysOutputData": True},
        {"id": "ex", "name": "Ejecuciones v6 con error", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [700, 380],
         "parameters": {"method": "GET", "url": "https://n8n.raquelrodriguez.com.ar/api/v1/executions?workflowId=O155MqHgOSaNZ9ye&status=error&limit=10",
                        "sendHeaders": True, "headerParameters": {"parameters": [{"name": "X-N8N-API-KEY", "value": n8n_key}]},
                        "options": {"response": {"response": {"neverError": True}}, "timeout": 20000}}, "credentials": {}, "onError": "continueRegularOutput"},
        {"id": "eval", "name": "Evaluar y deduplicar", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [960, 380],
         "parameters": {"jsCode": EVAL_JS.replace("__LUCAS__", LUCAS)}},
        {"id": "send", "name": "Avisar a Lucas (WA)", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1220, 380],
         "parameters": {"method": "POST", "url": evo_base + "/send/text", "sendHeaders": True, "headerParameters": copy.deepcopy(evo_headers),
                        "sendBody": True, "specifyBody": "json",
                        "jsonBody": "={\n  \"number\": {{ JSON.stringify($json.numero) }},\n  \"text\": {{ JSON.stringify($json.texto) }}\n}",
                        "options": {"response": {"response": {"neverError": True}}}}, "credentials": {}, "onError": "continueRegularOutput"},
    ]
    connections = {
        "Cada 15 min": {"main": [[C("Query señales")]]},
        "Webhook Manual Vigía": {"main": [[C("Query señales")]]},
        "Query señales": {"main": [[C("Ejecuciones v6 con error")]]},
        "Ejecuciones v6 con error": {"main": [[C("Evaluar y deduplicar")]]},
        "Evaluar y deduplicar": {"main": [[C("Avisar a Lucas (WA)")]]},
    }
    return {"name": "Áurea — Vigía (triaje + v6 + entrada)", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1"}}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--activate"); ap.add_argument("--update")
    args = ap.parse_args()
    if args.activate:
        r = api(f"/workflows/{args.activate}/activate", "POST"); print(f"activado: {r.get('id')} active={r.get('active')}"); return
    v6 = api(f"/workflows/{env('N8N_WORKFLOW_V6_ID', 'O155MqHgOSaNZ9ye')}")
    enviar = next(n for n in v6["nodes"] if n["name"] == "Evolution API - Enviar Mensaje")
    wf = build(require("N8N_API_KEY"), enviar["parameters"]["headerParameters"], enviar["parameters"]["url"].split("/send/")[0])
    print(f"Workflow: '{wf['name']}' — {len(wf['nodes'])} nodos"); [print("  -", n["name"]) for n in wf["nodes"]]
    if args.update:
        r = api(f"/workflows/{args.update}", "PUT", wf); print(f"actualizado: {r.get('id')} active={r.get('active')}"); return
    if not args.apply: print("(preview — nada creado). --apply crea el workflow inactivo."); return
    creado = api("/workflows", "POST", wf)
    print(f"Creado OK -> id={creado['id']} (activo={creado.get('active')}). Siguiente: --activate {creado['id']}; prueba manual: POST /webhook/trigger-vigia-manual")

if __name__ == "__main__":
    main()
