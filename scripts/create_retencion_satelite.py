# -*- coding: utf-8 -*-
"""
create_retencion_satelite.py — crea "Áurea — Retención (archivos y bandeja)": un cron diario (04:30 Jujuy) que borra
lo único que puede crecer en serio en el Supabase v3 (plan free: 500 MB de base, 1 GB de Storage) y deja un log.

Pedido de Lucas (7/9 02:50): "dejame todo para que funcione y se autoregule". Diseño y operación:
docs/retencion-y-uso-2026-09-07.md. Alertas de uso (400 MB base / 800 MB storage): scripts/create_vigia_bot.py.

QUÉ BORRA (cada corrida, máximo LOTE objetos por bucket; si quedan más, sigue a la noche siguiente):
  1. Adjuntos del PACIENTE (bucket privado `pacientes-media`) con más de DIAS_MEDIA_PACIENTES días: SELECT en
     media_entrantes (borrado_at IS NULL) -> DELETE {host}/storage/v1/object/pacientes-media {prefixes:[paths]} con la
     credencial supabaseApi H1PRagttKC5kxSzs -> UPDATE media_entrantes SET borrado_at = now() (solo si el DELETE respondió
     200; un objeto ya inexistente NO es error: Storage devuelve solo los que borró). El panel muestra "Adjunto vencido".
  2. Adjuntos del STAFF (bucket público `panel-media`, imágenes/audios mandados desde el panel) con más de DIAS_PANEL_MEDIA
     días: se listan desde storage.objects (SELECT con la credencial postgres; NUNCA se borra por SQL, eso deja el blob
     huérfano en S3) y se borran por la misma API REST. La URL queda en la memoria; el panel pinta "Adjunto vencido".
  3. Filas de mensajes_entrantes_live (bandeja en vivo) con más de DIAS_INBOX_LIVE días.
  4. Una fila por bucket/tabla en retencion_log (bucket, borrados, fallidos, detalle) y aviso a Lucas por WhatsApp SOLO
     si algo falló o dejó advertencia (Storage no encontró NINGUNO de los paths pedidos: posible desfasaje entre
     media_entrantes.path y storage.objects.name; mismo nodo/headers que "Avisar a Lucas (WA)" del Vigía).
  El Vigía (create_vigia_bot.py) además avisa `retencion_no_corrio` si retencion_log no tiene una corrida en las últimas 26 h.

NO TOCA: n8n_chat_histories, conversaciones, pacientes, logs del bot, urgencias-videos (videos del triaje), ni Redis.

DDL (idempotente; lo corre el orquestador con --ddl, NO este script en --apply): media_entrantes.borrado_at TIMESTAMPTZ NULL
(+ índice parcial) y tabla retencion_log. También documentado en scripts/rebuild_v3_schema.sql §12/§13.

SECRETOS: ninguno en este archivo. Host del v3 y credencial supabaseApi copiados del nodo vivo `obtener_historial_paciente`
del v6 (patrón apply_media_entrantes.py); headers de Evolution GO del nodo `Evolution API - Enviar Mensaje`. Nace INACTIVO.

Fuente única del JS de los Code nodes: retencion/agrupar_lote.js, retencion/resumen.js, retencion/armar_aviso.js
(tests/test_retencion_y_staff.js corre esos mismos archivos).

USO:
  python scripts/create_retencion_satelite.py [--dry-run]   # (default) JSON resumido de nodos + cuántos objetos borraría HOY
                                                            #  por bucket/tabla + estado del DDL. Solo GET a n8n y SELECT a la base.
  python scripts/create_retencion_satelite.py --ddl         # aplica el DDL (borrado_at + retencion_log) por psycopg2. Idempotente.
  python scripts/create_retencion_satelite.py --apply       # crea el workflow INACTIVO (exige el DDL aplicado)
  python scripts/create_retencion_satelite.py --activate <id>
  python scripts/create_retencion_satelite.py --update <id> # PUT sobre el workflow existente (name/nodes/connections/settings)
  Prueba manual sin esperar a las 04:30: POST {n8n}/webhook/trigger-retencion-manual (body {"smoke": true} agrega un path
  inexistente al lote para ejercitar el DELETE de Storage sin borrar nada real).
"""
import argparse, copy, json, os, sys, urllib.request
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402
from apply_media_entrantes import resolver_host_v3, if_bool, SUPABASE_CRED_ID  # noqa: E402  (misma fuente que el v6)
from create_media_entrantes import db_conn  # noqa: E402  (psycopg2 con SUPABASE_DB_* del .env; solo --dry-run y --ddl)
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent

# ---------------- constantes de retención (cambiarlas acá y correr --update <id>) ----------------
DIAS_MEDIA_PACIENTES = 90   # adjuntos del paciente: filas de media_entrantes + objetos de pacientes-media
DIAS_PANEL_MEDIA = 90       # adjuntos del staff mandados desde el panel: objetos de panel-media
DIAS_INBOX_LIVE = 365       # filas de mensajes_entrantes_live (bandeja en vivo; la memoria/conversaciones NO se tocan)
LOTE = 200                  # objetos por corrida y por bucket (un DELETE REST por lote; lo que sobra sale a la noche siguiente)
CRON = "30 4 * * *"         # 04:30 en TZ (settings.timezone del workflow: el Schedule Trigger de n8n usa la del workflow)
TZ = "America/Argentina/Jujuy"
WEBHOOK_MANUAL = "trigger-retencion-manual"
LUCAS = "5491161461034"
PG_CRED = {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}
BUCKET_PACIENTES, BUCKET_PANEL, TABLA_LIVE = "pacientes-media", "panel-media", "mensajes_entrantes_live"
NOMBRE = "Áurea — Retención (archivos y bandeja)"

# ---------------- SQL de los nodos ----------------
# Solo filas del bucket que borra esta etapa: una fila de otro bucket nunca se marcaría y volvería cada noche (con ≥ LOTE de
# ellas más viejas que las reales, el lote se llenaría de omitidas y las reales no saldrían nunca). Hoy media_entrantes
# tiene DEFAULT 'pacientes-media' sin CHECK; agrupar_lote.js igual omite lo que no sea del bucket (defensa doble).
Q_PACIENTES = (f"SELECT id, bucket, path FROM media_entrantes WHERE created_at < now() - interval '{DIAS_MEDIA_PACIENTES} days' "
               f"AND borrado_at IS NULL AND bucket = '{BUCKET_PACIENTES}' ORDER BY created_at LIMIT {LOTE}")
# $1 = ids unidos por '|' (sin comas: n8n parte queryReplacement por coma DESPUÉS de evaluar, lección 5/9). Devuelve SIEMPRE 1 fila.
# Con ids vacío (smoke sin vencidos) el nodo recibe '-' (ver Q_MARCAR_PARAM): un queryReplacement '' hace que n8n no pushee
# ningún parámetro ("there is no parameter $1", verificado en n8n 2.9.4 con este mismo typeVersion) y la corrida avisaría en falso.
Q_MARCAR = ("WITH u AS (UPDATE media_entrantes SET borrado_at = now() WHERE borrado_at IS NULL AND id = ANY(string_to_array($1, '|')) "
            "RETURNING id) SELECT count(*)::int AS marcados FROM u")
Q_MARCAR_PARAM = "={{ $('Pacientes: agrupar lote').first().json.ids.join('|') || '-' }}"  # '-' no matchea ningún id (16 hex) → marcados 0
# storage.objects: `name` es el path completo (<tel>/<ts>-<uuid>-<file>); las carpetas virtuales tienen metadata NULL.
# is_delete_marker: versioning apagado hoy (siempre false); el filtro evita mandar a borrar marcadores si algún día se prende.
Q_PANEL = (f"SELECT name AS path, bucket_id AS bucket FROM storage.objects WHERE bucket_id = '{BUCKET_PANEL}' "
           f"AND created_at < now() - interval '{DIAS_PANEL_MEDIA} days' AND metadata IS NOT NULL AND is_delete_marker IS NOT TRUE "
           f"ORDER BY created_at LIMIT {LOTE}")
Q_BANDEJA = (f"WITH d AS (DELETE FROM {TABLA_LIVE} WHERE created_at < now() - interval '{DIAS_INBOX_LIVE} days' RETURNING 1) "
             "SELECT count(*)::int AS borrados FROM d")

DDL = """
ALTER TABLE public.media_entrantes ADD COLUMN IF NOT EXISTS borrado_at TIMESTAMPTZ NULL;
CREATE INDEX IF NOT EXISTS idx_media_entrantes_vivos_created ON public.media_entrantes (created_at) WHERE borrado_at IS NULL;
CREATE TABLE IF NOT EXISTS public.retencion_log (
    id         SERIAL PRIMARY KEY,
    corrida_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bucket     TEXT,                       -- 'pacientes-media' | 'panel-media' | 'mensajes_entrantes_live'
    borrados   INT NOT NULL DEFAULT 0,
    fallidos   INT NOT NULL DEFAULT 0,
    detalle    TEXT
);
ALTER TABLE public.retencion_log ENABLE ROW LEVEL SECURITY;
"""

def js(nombre, **repl):
    code = (ROOT / "retencion" / nombre).read_text(encoding="utf-8")
    for k, v in repl.items(): code = code.replace(f"__{k}__", str(v))
    return code

def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    req = urllib.request.Request(f"{base}/api/v1{path}", data=json.dumps(payload).encode() if payload is not None else None,
                                 method=method, headers={"X-N8N-API-KEY": require("N8N_API_KEY"), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read().decode())

# ---------------- construcción del workflow ----------------
def pg_query(nid, name, pos, query, replacement=None):
    opts = {"queryReplacement": replacement} if replacement else {}
    return {"id": nid, "name": name, "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": pos,
            "parameters": {"operation": "executeQuery", "query": query, "options": opts},
            "credentials": {"postgres": PG_CRED}, "onError": "continueRegularOutput", "alwaysOutputData": True}

def storage_delete(nid, name, pos, host, sb_cred):
    # DELETE {host}/storage/v1/object/{bucket} body {"prefixes":[paths]} (= storage-js remove()). fullResponse -> {statusCode, headers, body};
    # body = SOLO los objetos que existían y se borraron (un path inexistente no es error). neverError: el IF decide por statusCode.
    return {"id": nid, "name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": pos,
            "parameters": {"method": "DELETE", "url": "=" + host + "/storage/v1/object/{{ $json.bucket }}",
                           "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
                           "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                           "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify({ prefixes: $json.paths }) }}",
                           "options": {"response": {"response": {"neverError": True, "fullResponse": True}}, "timeout": 60000}},
            "credentials": {"supabaseApi": sb_cred}, "onError": "continueRegularOutput"}

def build(host, sb_cred, evo_headers, evo_base):
    def C(name, idx=0): return {"node": name, "type": "main", "index": idx}
    N = {"cron": "Diario 04:30 Jujuy", "wh": "Webhook Manual Retención",
         "pac_sel": "Pacientes: listar vencidos", "pac_agr": "Pacientes: agrupar lote", "pac_if": "Pacientes: ¿hay lote?",
         "pac_del": "Pacientes: borrar en Storage", "pac_ok": "Pacientes: ¿borrado OK?", "pac_upd": "Pacientes: marcar borrado_at",
         "pan_sel": "Panel: listar vencidos", "pan_agr": "Panel: agrupar lote", "pan_if": "Panel: ¿hay lote?", "pan_del": "Panel: borrar en Storage",
         "ban": "Bandeja: purgar", "res": "Resumen", "log": "Registrar retencion_log", "aviso": "Armar aviso", "wa": "Avisar a Lucas (WA)"}
    nodes = [
        {"id": "cron", "name": N["cron"], "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [180, 300],
         "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": CRON}]}}},
        {"id": "wh", "name": N["wh"], "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [180, 480],
         "webhookId": WEBHOOK_MANUAL, "parameters": {"httpMethod": "POST", "path": WEBHOOK_MANUAL, "responseMode": "onReceived", "options": {}}},
        # --- 1. adjuntos del paciente ---
        pg_query("pac-sel", N["pac_sel"], [440, 380], Q_PACIENTES),
        {"id": "pac-agr", "name": N["pac_agr"], "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [680, 380],
         "parameters": {"jsCode": js("agrupar_lote.js", BUCKET=BUCKET_PACIENTES)}},
        if_bool("pac-if", N["pac_if"], [920, 380], "={{ $json.n > 0 }}"),
        storage_delete("pac-del", N["pac_del"], [1160, 260], host, sb_cred),
        if_bool("pac-ok", N["pac_ok"], [1400, 260], "={{ $json.statusCode === 200 }}"),
        pg_query("pac-upd", N["pac_upd"], [1640, 200], Q_MARCAR, Q_MARCAR_PARAM),
        # --- 2. adjuntos del staff (panel-media) ---
        pg_query("pan-sel", N["pan_sel"], [1900, 380], Q_PANEL),
        {"id": "pan-agr", "name": N["pan_agr"], "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [2140, 380],
         "parameters": {"jsCode": js("agrupar_lote.js", BUCKET=BUCKET_PANEL)}},
        if_bool("pan-if", N["pan_if"], [2380, 380], "={{ $json.n > 0 }}"),
        storage_delete("pan-del", N["pan_del"], [2620, 260], host, sb_cred),
        # --- 3. bandeja en vivo ---
        pg_query("ban", N["ban"], [2880, 380], Q_BANDEJA),
        # --- 4. log + aviso solo si falló ---
        {"id": "res", "name": N["res"], "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [3120, 380],
         "parameters": {"jsCode": js("resumen.js", DIAS_MEDIA_PACIENTES=DIAS_MEDIA_PACIENTES, DIAS_PANEL_MEDIA=DIAS_PANEL_MEDIA, DIAS_INBOX_LIVE=DIAS_INBOX_LIVE)}},
        # INSERT parametrizado por el nodo (defineBelow, mismo patrón que "Media: Registrar"): `detalle` puede traer comas.
        {"id": "log", "name": N["log"], "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": [3360, 380],
         "parameters": {"schema": {"__rl": True, "value": "public", "mode": "list"}, "table": {"__rl": True, "value": "retencion_log", "mode": "list"},
                        "columns": {"mappingMode": "defineBelow", "value": {"bucket": "={{ $json.bucket }}", "borrados": "={{ $json.borrados }}",
                                                                           "fallidos": "={{ $json.fallidos }}", "detalle": "={{ $json.detalle }}"}},
                        "options": {}},
         "credentials": {"postgres": PG_CRED}, "onError": "continueRegularOutput", "alwaysOutputData": True},
        {"id": "aviso", "name": N["aviso"], "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [3600, 380],
         "parameters": {"jsCode": js("armar_aviso.js", LUCAS=LUCAS)}},
        {"id": "wa", "name": N["wa"], "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [3840, 380],
         "parameters": {"method": "POST", "url": evo_base + "/send/text", "sendHeaders": True, "headerParameters": copy.deepcopy(evo_headers),
                        "sendBody": True, "specifyBody": "json",
                        "jsonBody": "={\n  \"number\": {{ JSON.stringify($json.numero) }},\n  \"text\": {{ JSON.stringify($json.texto) }}\n}",
                        "options": {"response": {"response": {"neverError": True}}}}, "credentials": {}, "onError": "continueRegularOutput"},
    ]
    connections = {
        N["cron"]: {"main": [[C(N["pac_sel"])]]},
        N["wh"]: {"main": [[C(N["pac_sel"])]]},
        N["pac_sel"]: {"main": [[C(N["pac_agr"])]]},
        N["pac_agr"]: {"main": [[C(N["pac_if"])]]},
        N["pac_if"]: {"main": [[C(N["pac_del"])], [C(N["pan_sel"])]]},
        N["pac_del"]: {"main": [[C(N["pac_ok"])]]},
        N["pac_ok"]: {"main": [[C(N["pac_upd"])], [C(N["pan_sel"])]]},
        N["pac_upd"]: {"main": [[C(N["pan_sel"])]]},
        N["pan_sel"]: {"main": [[C(N["pan_agr"])]]},
        N["pan_agr"]: {"main": [[C(N["pan_if"])]]},
        N["pan_if"]: {"main": [[C(N["pan_del"])], [C(N["ban"])]]},
        N["pan_del"]: {"main": [[C(N["ban"])]]},
        N["ban"]: {"main": [[C(N["res"])]]},
        N["res"]: {"main": [[C(N["log"])]]},
        N["log"]: {"main": [[C(N["aviso"])]]},
        N["aviso"]: {"main": [[C(N["wa"])]]},
    }
    # settings: solo claves de la allowlist del PUT (regla dura 4). timezone: el Schedule Trigger la usa para el cron.
    return {"name": NOMBRE, "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1", "timezone": TZ}}

def live_v6():
    """GET al v6: host del v3 + credencial supabaseApi (nodo obtener_historial_paciente) + headers/base de Evolution GO."""
    v6 = api(f"/workflows/{env('N8N_WORKFLOW_V6_ID', 'O155MqHgOSaNZ9ye')}")
    names = {n["name"]: n for n in v6["nodes"]}
    sb_node = names.get("obtener_historial_paciente") or names.get("consultar_recordatorios_abiertos")
    sb_cred = copy.deepcopy((sb_node or {}).get("credentials", {}).get("supabaseApi"))
    if not sb_cred or sb_cred.get("id") != SUPABASE_CRED_ID:
        sys.exit(f"ERROR: credencial supabaseApi inesperada en el nodo vivo: {sb_cred!r} (esperaba id {SUPABASE_CRED_ID})")
    host, fuentes = resolver_host_v3(names)
    enviar = names["Evolution API - Enviar Mensaje"]
    return host, fuentes, sb_cred, enviar["parameters"]["headerParameters"], enviar["parameters"]["url"].split("/send/")[0]

# ---------------- base: estado del DDL y conteos (solo SELECT) ----------------
def ddl_estado(cur):
    cur.execute("SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='media_entrantes' AND column_name='borrado_at'")
    col = cur.fetchone() is not None
    cur.execute("SELECT to_regclass('public.retencion_log')")
    tabla = cur.fetchone()[0] is not None
    cur.execute("SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname='idx_media_entrantes_vivos_created'")
    idx = cur.fetchone() is not None
    return {"borrado_at": col, "retencion_log": tabla, "indice": idx}

def contar(cur, est):
    """Cuántos objetos/filas borraría HOY cada etapa (mismos criterios que los nodos) + tamaños. Solo SELECT."""
    out = {}
    q = (f"SELECT count(*), coalesce(sum(bytes),0) FROM media_entrantes WHERE created_at < now() - make_interval(days => %s) AND bucket = %s"
         + (" AND borrado_at IS NULL" if est["borrado_at"] else ""))
    cur.execute(q, (DIAS_MEDIA_PACIENTES, BUCKET_PACIENTES)); n, b = cur.fetchone()
    out[BUCKET_PACIENTES] = {"borraria": int(n), "mb": round(int(b) / 1048576, 2), "nota": None if est["borrado_at"] else "sin filtro borrado_at (columna aún no existe: --ddl)"}
    cur.execute("SELECT count(*), coalesce(sum((metadata->>'size')::bigint),0) FROM storage.objects WHERE bucket_id=%s AND created_at < now() - make_interval(days => %s) "
                "AND metadata IS NOT NULL AND is_delete_marker IS NOT TRUE", (BUCKET_PANEL, DIAS_PANEL_MEDIA)); n, b = cur.fetchone()
    out[BUCKET_PANEL] = {"borraria": int(n), "mb": round(int(b) / 1048576, 2)}
    cur.execute(f"SELECT count(*) FROM {TABLA_LIVE} WHERE created_at < now() - make_interval(days => %s)", (DIAS_INBOX_LIVE,))
    out[TABLA_LIVE] = {"borraria": int(cur.fetchone()[0])}
    cur.execute("SELECT pg_database_size(current_database())"); out["db_mb"] = round(cur.fetchone()[0] / 1048576, 1)
    cur.execute("SELECT bucket_id, count(*), coalesce(sum((metadata->>'size')::bigint),0) FROM storage.objects WHERE metadata IS NOT NULL GROUP BY 1 ORDER BY 1")
    out["storage"] = {r[0]: {"objetos": int(r[1]), "mb": round(int(r[2]) / 1048576, 2)} for r in cur.fetchall()}
    if est["retencion_log"]:
        cur.execute("SELECT corrida_at, bucket, borrados, fallidos, left(detalle, 80) FROM retencion_log ORDER BY id DESC LIMIT 6")
        out["ultimas_corridas"] = [(str(r[0])[:16], r[1], r[2], r[3], r[4]) for r in cur.fetchall()]
    return out

def resumen_nodos(wf):
    print(f"Workflow: '{wf['name']}' — {len(wf['nodes'])} nodos · settings={json.dumps(wf['settings'])}")
    for n in wf["nodes"]:
        extra = ""
        p = n.get("parameters", {})
        if n["type"].endswith(".postgres"): extra = " | " + (p.get("query") or f"INSERT {p.get('table', {}).get('value')}")[:110]
        elif n["type"].endswith(".httpRequest"): extra = " | " + p["method"] + " " + p["url"].lstrip("=")[:96]
        elif n["type"].endswith(".scheduleTrigger"): extra = " | cron " + p["rule"]["interval"][0]["expression"]
        elif n["type"].endswith(".if"): extra = " | " + p["conditions"]["conditions"][0]["leftValue"]
        elif n["type"].endswith(".webhook"): extra = " | POST /webhook/" + p["path"]
        print(f"  - {n['name']} [{n['type'].split('.')[-1]}]{extra}")
    print("  conexiones:", ", ".join(f"{a}->{'/'.join(c[0]['node'] for c in b['main'] if c)}" for a, b in wf["connections"].items()))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--ddl", action="store_true"); ap.add_argument("--apply", action="store_true")
    ap.add_argument("--activate", metavar="WF_ID"); ap.add_argument("--update", metavar="WF_ID")
    args = ap.parse_args()
    if args.activate:
        r = api(f"/workflows/{args.activate}/activate", "POST"); print(f"activado: {r.get('id')} active={r.get('active')}"); return
    if args.ddl:
        conn = db_conn(); cur = conn.cursor()
        antes = ddl_estado(cur); cur.execute(DDL); despues = ddl_estado(cur)
        print(f"DDL aplicado. antes={antes} después={despues}"); cur.close(); conn.close()
        return sys.exit(0 if all(despues.values()) else 1)

    # El objetivo del dry-run ("nunca borrar sin haber confirmado la lista") no depende de n8n: si el GET al v6 falla
    # (VPS caído, timeout) se informa y se sigue con los conteos. --apply / --update sí lo necesitan (credencial + host).
    wf = None
    try:
        host, fuentes, sb_cred, evo_headers, evo_base = live_v6()
        wf = build(host, sb_cred, evo_headers, evo_base)
        print(f"host v3: {host} (fuentes: {', '.join(f for f, _ in fuentes)}) · supabaseApi {sb_cred['id']} · postgres {PG_CRED['id']}")
        resumen_nodos(wf)
    except SystemExit: raise
    except Exception as e:
        if args.apply or args.update: raise
        print(f"(no pude leer el v6 en n8n para armar el preview de nodos: {type(e).__name__}: {str(e)[:160]}; sigo con los conteos)")
    if args.update:
        r = api(f"/workflows/{args.update}", "PUT", {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"], "settings": wf["settings"]})
        print(f"actualizado: {r.get('id')} active={r.get('active')} nodos={len(r.get('nodes', []))}"); return

    # estado del DDL + conteos (solo SELECT). Si la base no responde, se informa y se sigue (el preview de nodos ya salió).
    est = None
    try:
        conn = db_conn(); cur = conn.cursor()
        est = ddl_estado(cur); c = contar(cur, est); cur.close(); conn.close()
        print(f"\nDDL: borrado_at={est['borrado_at']} retencion_log={est['retencion_log']} índice={est['indice']}" + ("" if all(est.values()) else "  -> falta: correr --ddl"))
        print(f"Base: {c['db_mb']} MB de 500 (plan free) · Storage: " + ", ".join(f"{b} {v['objetos']} obj {v['mb']} MB" for b, v in c["storage"].items()))
        print("Borraría HOY:")
        print(f"  - {BUCKET_PACIENTES}: {c[BUCKET_PACIENTES]['borraria']} adjunto(s) de paciente > {DIAS_MEDIA_PACIENTES} días ({c[BUCKET_PACIENTES]['mb']} MB)" + (f"  [{c[BUCKET_PACIENTES]['nota']}]" if c[BUCKET_PACIENTES]["nota"] else ""))
        print(f"  - {BUCKET_PANEL}: {c[BUCKET_PANEL]['borraria']} adjunto(s) del staff > {DIAS_PANEL_MEDIA} días ({c[BUCKET_PANEL]['mb']} MB)")
        print(f"  - {TABLA_LIVE}: {c[TABLA_LIVE]['borraria']} fila(s) > {DIAS_INBOX_LIVE} días")
        if c.get("ultimas_corridas"): print("  últimas corridas (retencion_log):", *c["ultimas_corridas"], sep="\n    ")
    except SystemExit: raise
    except Exception as e:
        print(f"\n(no pude consultar la base para contar: {type(e).__name__}: {str(e)[:160]})")

    if not args.apply:
        print("\n(dry-run — nada creado ni borrado). --ddl aplica el DDL; --apply crea el workflow inactivo."); return
    if not est or not all(est.values()):
        sys.exit("ERROR: falta el DDL (borrado_at / retencion_log / índice). Correr --ddl antes de --apply.")
    creado = api("/workflows", "POST", wf)
    red = json.loads(json.dumps(creado))
    for n in red["nodes"]:
        for h in (n.get("parameters", {}).get("headerParameters", {}) or {}).get("parameters", []) or []:
            if h.get("name", "").lower() == "apikey": h["value"] = "***"
    (ROOT / "workflows" / "history").mkdir(parents=True, exist_ok=True)
    (ROOT / "workflows" / "history" / f"retencion_CREADO_{creado['id']}.json").write_text(json.dumps(red, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nCreado OK -> id={creado['id']} (activo={creado.get('active')}). Siguiente: --activate {creado['id']}; "
          f"prueba manual: POST /webhook/{WEBHOOK_MANUAL} (body {{\"smoke\": true}} para ejercitar el DELETE sin borrar nada real).")

if __name__ == "__main__":
    main()
