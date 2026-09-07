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
  D) USO DE SUPABASE (7/9, plan free: 500 MB base / 1 GB storage): `supabase_db_alto` si pg_database_size > 400 MB y
     `supabase_storage_alto` si la suma de storage.objects > 800 MB (umbrales DB_ALTO_MB / STORAGE_ALTO_MB al inicio de
     EVAL_JS). Dedupe de 24 h (ventanaMin propia por alerta). Lo que se borra solo: scripts/create_retencion_satelite.py.
  E) VIGÍA CIEGO: si `Query señales` no devolvió nada (`ahora` undefined: permisos, columna, base caída) avisa
     `vigia_query_rota` (24 h), porque en ese estado NINGUNA de las otras alertas puede dispararse.
  F) RETENCIÓN QUE NO CORRIÓ (7/9): `retencion_no_corrio` (24 h) si existe la tabla retencion_log y no tiene una fila
     de las últimas RETENCION_MAX_H (26) horas o está vacía. Cubre Code node roto, satélite inactivo y cron a otra hora.
     Leído con query_to_xml para que la query no rompa mientras la tabla no exista (ver comentario bajo QUERY).

Dedupe de alertas con $getWorkflowStaticData: cada alerta trae su ventanaMin (default 60 min; uso de Supabase 1440).
Nace INACTIVO. La API key de n8n se copia del .env local al nodo en --apply (no queda en este archivo).
Cambios en QUERY/EVAL_JS se aplican al vivo con --update <id> (no toca secretos ni archivos locales).

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
  pg_database_size(current_database()) AS db_bytes,
  (SELECT coalesce(sum((metadata->>'size')::bigint), 0) FROM storage.objects WHERE metadata IS NOT NULL) AS storage_bytes,
  (SELECT coalesce(sum((metadata->>'size')::bigint), 0) FROM storage.objects WHERE bucket_id = 'pacientes-media' AND metadata IS NOT NULL) AS storage_pacientes_bytes,
  to_regclass('public.retencion_log') IS NOT NULL AS retencion_tabla,
  CASE WHEN to_regclass('public.retencion_log') IS NULL THEN NULL
       ELSE (xpath('/row/min/text()', query_to_xml('SELECT extract(epoch FROM now() - max(corrida_at))/60 AS min FROM public.retencion_log', false, true, '')))[1]::text
  END AS retencion_min,
  NOW() AS ahora
"""
# storage.objects.metadata es NULL en las "carpetas" virtuales (por eso el filtro). bigint llega como string: Number() en el JS.
# retencion_min = minutos desde la última fila de retencion_log (create_retencion_satelite.py), o NULL si la tabla no existe
# o está vacía. Va por query_to_xml (SQL dinámico) a propósito: un subselect directo a retencion_log haría fallar TODA la
# query mientras la tabla no exista (Postgres resuelve las tablas al parsear, aunque el CASE no entre) y el Vigía quedaría
# ciego. Verificado 7/9 con SELECT real: tabla ausente → (NULL, false); tabla con filas → '89.07…'; max NULL → NULL.

EVAL_JS = r"""// Evalúa las señales y decide qué alertas mandar. Dedupe por clave con staticData: cada alerta trae su propia
// ventana (ventanaMin, default 60 min); las de uso de Supabase avisan como mucho una vez por día (1440).
const DB_ALTO_MB = 400, DB_PLAN_MB = 500, STORAGE_ALTO_MB = 800, STORAGE_PLAN_MB = 1024;   // plan free de Supabase (7/9)
const RETENCION_MAX_H = 26;   // la retención corre todos los días 04:30 ART: más de 26 h sin fila en retencion_log = no corrió
const MB = 1024 * 1024;
const mb = (v) => (isFinite(v) ? v.toFixed(0) + ' MB' : '?');
const q = $('Query señales').first().json || {};
let execs = [];
try { execs = ($('Ejecuciones v6 con error').first().json || {}).data || []; } catch (e) { execs = []; }
const now = new Date();
const art = new Date(now.getTime() - 3 * 3600 * 1000);   // ART = UTC-3
const dow = art.getUTCDay(); const hora = art.getUTCHours();
const horarioClinica = (dow >= 1 && dow <= 5 && hora >= 8 && hora < 20) || (dow === 6 && hora >= 8 && hora < 13);
const alertas = [];
if (q.ahora === undefined) {
  // La query es una sola: si falla (permiso sobre storage.objects, columna, base caída) NINGUNA otra alerta puede salir.
  alertas.push({ clave: 'vigia_query_rota', ventanaMin: 1440, texto: `🛠️ El Vigía no pudo leer sus señales (Query señales devolvió ${JSON.stringify(q).slice(0, 160)}). Hasta que se arregle no va a avisar de nada más.` });
}
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
const dbMb = Number(q.db_bytes) / MB, stMb = Number(q.storage_bytes) / MB, stPacMb = Number(q.storage_pacientes_bytes) / MB;
if (dbMb > DB_ALTO_MB) {
  alertas.push({ clave: 'supabase_db_alto', ventanaMin: 1440, texto: `📦 La base de Supabase está en ${dbMb.toFixed(0)} MB de ${DB_PLAN_MB} (plan free): hay que subir de plan o limpiar` });
}
if (stMb > STORAGE_ALTO_MB) {
  alertas.push({ clave: 'supabase_storage_alto', ventanaMin: 1440, texto: `📦 El Storage de Supabase está en ${stMb.toFixed(0)} MB de ${STORAGE_PLAN_MB} (plan free): hay que subir de plan o limpiar (pacientes-media: ${mb(stPacMb)})` });
}
// Retención nocturna (satélite "Áurea — Retención"): si sus Code nodes tiran, si está inactiva o si el cron quedó en otra
// hora, no hay fila en retencion_log ni WhatsApp: se apagaría en silencio hasta que salte supabase_storage_alto. Solo se
// evalúa cuando la tabla existe (después del --ddl); vacía = "nunca corrió" (el smoke del alta deja filas antes del --activate).
if (q.retencion_tabla === true) {
  const retMin = (q.retencion_min === null || q.retencion_min === undefined || q.retencion_min === '') ? null : Number(q.retencion_min);
  if (retMin === null || !isFinite(retMin) || retMin > RETENCION_MAX_H * 60) {
    const hace = retMin === null || !isFinite(retMin) ? 'nunca corrió (retencion_log vacía)' : `última corrida hace ${(retMin / 60).toFixed(0)} h`;
    alertas.push({ clave: 'retencion_no_corrio', ventanaMin: 1440, texto: `🧹 La retención nocturna (workflow "Áurea — Retención", 04:30 ART) no dejó registro en retencion_log: ${hace}. ¿Está activa en n8n? Revisar sus ejecuciones.` });
  }
}
const st = $getWorkflowStaticData('global');
st.last = st.last || {};
const mandar = [];
for (const a of alertas) {
  const ventana = (Number(a.ventanaMin) || 60) * 60 * 1000;
  const prev = st.last[a.clave] ? new Date(st.last[a.clave]).getTime() : 0;
  if (now.getTime() - prev > ventana) { mandar.push(a); st.last[a.clave] = now.toISOString(); }
}
if (!mandar.length) return [];
const texto = '👁️ *Vigía Asiri*\n\n' + mandar.map(a => a.texto).join('\n\n') + `\n\n(entrantes 3h: ${q.entrantes_3h}, triaje activo: ${q.triaje_activo}, videos activos: ${q.videos_activos}, base: ${mb(dbMb)}, storage: ${mb(stMb)})`;
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
