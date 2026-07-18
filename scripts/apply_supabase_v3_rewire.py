"""
Recableado completo a Supabase Nexora v3 (preparado 2026-07-17 — NO EJECUTADO).

Contexto: el proyecto Supabase v2 (ujfyapjwrdhnvqdvsjwp, creado 2026-07-08 tras el
borrado del original dchztroesbpwxxkfywwu) murio en crash-loop irrecuperable
(ECIRCUITBREAKER en el pooler, DNS de db.* sin resolver, REST 503 — ver
memory/current-state.md 17/7). Se crea un proyecto v3 nuevo y este script recablea
n8n contra el, adaptando el runbook probado de scripts/apply_supabase_v2_rewire.py.

QUE HACE (lado n8n; lo unico que toca este script):
  1. Crea la credencial Postgres nueva "Postgres Supabase Nexora v3" via
     POST /api/v1/credentials (shape verificado contra GET /credentials/schema/postgres).
     Si preferis crearla a mano en la UI, pega su id en NEW_PG_CRED_ID y se saltea.
  2. Crea la credencial supabaseApi nueva "Supabase account v3" (host + service_role).
     NOTA: el API publico de n8n NO permite editar credenciales (solo POST/DELETE/schema),
     por eso se crea una nueva y se repuntean los nodos. Alternativa manual: editar
     "Supabase account" (Thn3jgEbbxPFD7d9) en la UI con el host/key de v3 y poner
     UPDATE_SUPA_CRED_IN_UI = True (entonces NO se crea ni repuntea supabaseApi;
     buscar_conocimiento y las tools quedan cubiertas por la credencial editada).
  3. Repunta TODOS los nodos Postgres (cred EWhpNhb6tkGg1OTp, y defensivo tambien la
     prehistorica xwvjww5Odcxiy1K9) en los 8 workflows afectados. Son 19 nodos
     esperados — los 18 del runbook v2 MAS "Log Escalacion" en Helper Notify Grupo
     (agregado 14/7 por apply_escalaciones_logging.py, no existia en el rewire v2).
  4. Repunta los 9 nodos con credencial supabaseApi (5 en v6: obtener_historial_paciente,
     buscar_conocimiento, y las 3 tools de recordatorios; 4 en Logger: HTTP - Upsert
     Paciente x2 y HTTP - Insert Conversacion x2 — el Logger tiene nodos con id duplicado,
     se patchean todos).
  5. Swap de ref en URLs *.supabase.co (v2 → v3) en todos los parameters de todos los
     nodos (cubre las 4 tools httpRequest del v6 y los 4 httpRequest del Logger).
     Defensivo: tambien limpia cualquier apikey= embebido que reaparezca en esas URLs.
  6. Backup PRE/POST por workflow en workflows/history/ con timestamp.
  7. Imprime el staticData del Logger (cursor last_synced_chat_id) — decidir su valor
     a mano segun como se restauren los datos (ver checklist al final).

QUE NO HACE (lado base de datos — hacer ANTES de correr esto en real, via SQL editor
del dashboard v3 o el patron run_sql de scripts/recovery_backfill.py):
  a. Restaurar datos (conversaciones, pacientes, n8n_chat_histories, knowledge_base).
  b. Crear tablas que no vengan del restore: recordatorios_enviados + las fundacionales
     del 15/7 (escalaciones_log, peticiones, urgencias_log, servicios).
  c. RESETEAR SECUENCIAS a max(id)+1 (leccion clave del 8/7: el restore deja las
     secuencias en 1 y revientan los INSERT). En v2 fue: conversaciones, pacientes,
     n8n_chat_histories (memoria), kb identity.
  d. Recrear match_documents() apuntando a knowledge_base (contenido→content, 1536 dims).
  e. Borrar la(s) fila(s) envenenada(s) de n8n_chat_histories con message = texto plano
     "The servic..." (rompe el JSON.parse del Sub-WF Cancelar Step 0b).

GUARDAS (patron v2): backup pre/post, conteo de nodos invariante, cero referencias a
refs viejos tras el patch, cero credenciales viejas, set de webhookId invariante
(preserva evo-webhook-v2), PUT solo con name/nodes/connections/settings/staticData,
settings filtrado a la whitelist del API. Verificacion post-PUT con re-GET.

MODO DE USO:
  1. Crear el proyecto v3 en el dashboard de Supabase. Anotar ref, password de DB,
     service_role key y HOST REAL DEL POOLER (Settings → Database → connection pooling.
     v1 era us-west-2, v2 era aws-1-us-west-2 — el default de abajo es un supuesto,
     VERIFICAR SIEMPRE). Anotar tambien el puerto: 5432 session / 6543 transaction
     (v2 usaba 5432 session).
  2. Completar los CHANGEME de abajo (o exportar SUPABASE_V3_* en el entorno / .env).
  3. Hacer los pasos de base de datos (a-e de arriba).
  4. python scripts/apply_supabase_v3_rewire.py          → DRY RUN, muestra el diff.
  5. Revisar el diff CON LUCAS. Cambiar DRY_RUN = False. Correr de nuevo.
  6. Seguir el checklist que imprime al final (env, cursor Logger, backfill, E2E).

Regla dura del proyecto: NUNCA correr con DRY_RUN=False sin mostrar el diff a Lucas.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent))
from lib_env import env, require

# ────────────────────────────────────────────────────────────────────────────
# PARAMETROS DEL PROYECTO v3 — completar antes de correr (o via .env / entorno)
# ────────────────────────────────────────────────────────────────────────────
NEW_REF = env("SUPABASE_V3_REF", "CHANGEME")                  # ref del proyecto v3
NEW_DB_PASSWORD = env("SUPABASE_V3_DB_PASSWORD", "CHANGEME")  # password de la DB v3
NEW_SERVICE_ROLE_KEY = env("SUPABASE_V3_SERVICE_ROLE_KEY", "CHANGEME")  # service_role JWT v3
# ⚠ VERIFICAR el host del pooler al crear el proyecto (Settings → Database):
#   v1 fue aws-0-us-west-2 y v2 fue aws-1-us-west-2 — el default sa-east-1 es un SUPUESTO.
NEW_POOLER_HOST = env("SUPABASE_V3_POOLER_HOST", "aws-0-sa-east-1.pooler.supabase.com")
NEW_DB_PORT = int(env("SUPABASE_V3_DB_PORT", "5432"))         # 5432 session / 6543 transaction
NEW_DB_USER = f"postgres.{NEW_REF}"                           # user del pooler (Supavisor)

# Si las credenciales ya se crearon a mano en la UI de n8n, pegar sus ids aca y el
# script NO las crea via API (solo repunta los nodos hacia ellas):
NEW_PG_CRED_ID = env("N8N_V3_PG_CRED_ID", "")       # ej "AbCdEf123..." — vacio = crear via POST
NEW_SUPA_CRED_ID = env("N8N_V3_SUPA_CRED_ID", "")   # idem para la supabaseApi

NEW_PG_CRED_NAME = "Postgres Supabase Nexora v3"
NEW_SUPA_CRED_NAME = "Supabase account v3"

# True = NO tocar la credencial supabaseApi en este pase (o porque Lucas la edito en la
# UI, o porque la sb_secret v3 aun no llego y los 9 nodos REST se repuntean en un
# segundo pase con UPDATE_SUPA_CRED_IN_UI=0 + NEW_SUPA_CRED_ID/key reales).
UPDATE_SUPA_CRED_IN_UI = env("UPDATE_SUPA_CRED_IN_UI", "0") == "1"

DRY_RUN = env("REWIRE_DRY_RUN", "1") != "0"   # ← default seguro: solo muestra el diff

# ────────────────────────────────────────────────────────────────────────────
# CONSTANTES (estado conocido al 2026-07-17 — fuente: runbook v2 + backups history/)
# ────────────────────────────────────────────────────────────────────────────
N8N = require("N8N_BASE_URL").rstrip("/")
KEY = require("N8N_API_KEY")
HIST = Path(__file__).resolve().parents[1] / "workflows" / "history"
H = {"X-N8N-API-KEY": KEY, "accept": "application/json", "content-type": "application/json"}

# refs viejos a purgar de URLs/parameters (v2 muerto + v1 borrado, defensivo)
OLD_REFS = ["ujfyapjwrdhnvqdvsjwp", "dchztroesbpwxxkfywwu"]
# credenciales postgres viejas a repuntear (v2 + la prehistorica del proyecto v1)
OLD_PG_CRED_IDS = {"EWhpNhb6tkGg1OTp", "xwvjww5Odcxiy1K9"}
OLD_SUPA_CRED_ID = "Thn3jgEbbxPFD7d9"   # "Supabase account" (apuntaba a v2)

# (workflow_id, tag, nodos postgres esperados) — el conteo es un warning, no aborta,
# por si un workflow evoluciono desde este snapshot.
WFS = [
    ("O155MqHgOSaNZ9ye", "v6", 7),             # + 5 nodos supabaseApi + 4 URLs
    ("5cAWJxiWJ50hxEq3", "SubWF", 3),
    ("xsXeHp7WLXnFQc3o", "Logger", 1),          # + 4 httpRequest supabaseApi con URL (ids duplicados)
    ("7RqTApkvVavRmq3R", "Recordatorio", 2),
    ("BO1cdE8xmqln4IeO", "ResumenClinico", 3),  # hoy DESACTIVADO — repuntear igual, NO activar
    ("En0A5lXd3Whb5yFy", "Cleanup", 1),
    ("w7BBpZeEwZnpCX1q", "HumanTakeover", 1),
    ("S5U6tSipzlgFHCkf", "HelperNotify", 1),    # "Log Escalacion" (14/7) — NO estaba en el rewire v2
]
# total esperado: 19 nodos postgres (los 18 del v2 + Log Escalacion)

ALLOWED = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
           "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
           "executionOrder", "callerPolicy", "callerIds"}


def api(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(N8N + path, method=method, headers=H, data=data)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def die(msg):
    print("ABORTADO: " + msg)
    sys.exit(1)


def mask(s):
    s = str(s)
    return s[:6] + "…" + s[-4:] if len(s) > 14 else "***"


# ────────────────────────────────────────────────────────────────────────────
# 0) sanity de parametros
# ────────────────────────────────────────────────────────────────────────────
print(f"=== Rewire Supabase v3 — {'DRY RUN (no toca nada)' if DRY_RUN else '*** MODO REAL ***'} ===\n")
placeholders = [k for k, v in [("NEW_REF", NEW_REF), ("NEW_DB_PASSWORD", NEW_DB_PASSWORD),
                               ("NEW_SERVICE_ROLE_KEY", NEW_SERVICE_ROLE_KEY)] if v == "CHANGEME"]
if placeholders:
    if DRY_RUN:
        print(f"AVISO: parametros sin completar {placeholders} — el diff usara placeholders.\n")
    else:
        die(f"parametros sin completar: {placeholders} (modo real requiere valores v3)")
if not DRY_RUN and NEW_REF in OLD_REFS:
    die("NEW_REF es un ref viejo — completar con el ref del proyecto v3")
if "sa-east-1" in NEW_POOLER_HOST:
    print("⚠ NEW_POOLER_HOST es el default sa-east-1 — VERIFICAR contra el dashboard v3")
    print("  (v2 era aws-1-us-west-2.pooler.supabase.com; si esta mal, todos los nodos PG caen)\n")

# ────────────────────────────────────────────────────────────────────────────
# 1+2) credenciales nuevas (POST /api/v1/credentials — probado el 8/7, ver
#      scripts/create_supabase_cred.py; el API NO permite editar, solo crear/borrar)
# ────────────────────────────────────────────────────────────────────────────
pg_cred_body = {
    "name": NEW_PG_CRED_NAME,
    "type": "postgres",
    "data": {
        "host": NEW_POOLER_HOST,
        "database": "postgres",
        "user": NEW_DB_USER,
        "password": NEW_DB_PASSWORD,
        "port": NEW_DB_PORT,
        "ssl": "require",            # el pooler de Supabase acepta TLS; v2 andaba asi
        "allowUnauthorizedCerts": False,
    },
}
supa_cred_body = {
    "name": NEW_SUPA_CRED_NAME,
    "type": "supabaseApi",
    "data": {
        "host": f"https://{NEW_REF}.supabase.co",
        "serviceRole": NEW_SERVICE_ROLE_KEY,
    },
}


def create_cred(body, existing_id, label):
    """Crea la credencial si no vino un id manual. Devuelve el id a usar en los nodos."""
    if existing_id:
        print(f"[{label}] usando credencial ya creada a mano: {existing_id}")
        return existing_id
    if DRY_RUN:
        shown = dict(body, data={k: (mask(v) if k in ("password", "serviceRole") else v)
                                 for k, v in body["data"].items()})
        print(f"[{label}] DRY RUN — se crearia: {json.dumps(shown, ensure_ascii=False)}")
        return f"<NEW_{label}_CRED>"
    # el schema publicado ayuda a detectar drift de campos entre versiones de n8n
    try:
        schema = api("GET", f"/api/v1/credentials/schema/{body['type']}")
        known = set((schema or {}).get("properties", {}).keys())
        extra = set(body["data"]) - known if known else set()
        if extra:
            print(f"[{label}] ⚠ campos fuera del schema {sorted(known)}: {sorted(extra)} — se intenta igual")
    except Exception as e:
        print(f"[{label}] (schema no disponible: {e})")
    try:
        res = api("POST", "/api/v1/credentials", body)
    except urllib.error.HTTPError as e:
        print(f"[{label}] POST fallo: HTTP {e.code} — {e.read().decode()[:300]}")
        die(f"crear la credencial '{body['name']}' A MANO en la UI de n8n "
            f"(tipo {body['type']}) y re-correr con su id en NEW_{label}_CRED_ID")
    cid = res.get("id")
    if not cid:
        die(f"{label}: POST no devolvio id: {json.dumps(res)[:300]}")
    print(f"[{label}] credencial creada: id={cid} name={res.get('name')!r}  ← ANOTAR en memory/")
    return cid


new_pg_id = create_cred(pg_cred_body, NEW_PG_CRED_ID, "PG")
if UPDATE_SUPA_CRED_IN_UI:
    new_supa_id = OLD_SUPA_CRED_ID   # se sigue usando la existente, editada en la UI
    print("[SUPA] modo UI: se asume 'Supabase account' ya editada hacia v3 — no se crea ni repuntea")
else:
    new_supa_id = create_cred(supa_cred_body, NEW_SUPA_CRED_ID, "SUPA")
print()

NEW_PG_CRED = {"id": new_pg_id, "name": NEW_PG_CRED_NAME}
NEW_SUPA_CRED = {"id": new_supa_id, "name": NEW_SUPA_CRED_NAME}

# ────────────────────────────────────────────────────────────────────────────
# 3+4+5) patch de workflows
# ────────────────────────────────────────────────────────────────────────────
ts = time.strftime("%Y%m%d_%H%M%S")
suffix = f"supav3_DRYRUN_{ts}" if DRY_RUN else f"supav3_{ts}"
resumen = []
total_pg = total_supa = total_url = 0

for wid, tag, expected_pg in WFS:
    wf = api("GET", f"/api/v1/workflows/{wid}")
    before = json.loads(json.dumps(wf))   # deep copy inmutable para guardas/diff
    (HIST / f"{tag}_PRE_{suffix}.json").write_text(
        json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

    cambios = []
    n_pg = 0
    for n in wf["nodes"]:
        creds = n.get("credentials") or {}
        # (3) repuntar credencial postgres
        pg = creds.get("postgres")
        if pg and pg.get("id") in OLD_PG_CRED_IDS:
            creds["postgres"] = dict(NEW_PG_CRED)
            n["credentials"] = creds
            cambios.append(("cred-pg", n["name"], pg["id"], new_pg_id))
            n_pg += 1
        # (4) repuntar credencial supabaseApi (si no se edito en la UI)
        sup = creds.get("supabaseApi")
        if not UPDATE_SUPA_CRED_IN_UI and sup and sup.get("id") == OLD_SUPA_CRED_ID:
            creds["supabaseApi"] = dict(NEW_SUPA_CRED)
            n["credentials"] = creds
            cambios.append(("cred-supa", n["name"], sup["id"], new_supa_id))
        # (5) swap de refs viejos en TODOS los parameters del nodo (cubre url, query,
        #     headers, SQL — el ref es un string unico de 20 chars, replace es seguro)
        p = n.get("parameters")
        if p:
            pj = json.dumps(p, ensure_ascii=False)
            npj = pj
            for old in OLD_REFS:
                npj = npj.replace(old, NEW_REF)
            if npj != pj:
                n["parameters"] = json.loads(npj)
                p = n["parameters"]
                cambios.append(("ref-url", n["name"], "v2/v1-ref", NEW_REF))
            # defensivo (patron v2): jamas dejar un apikey embebido en la URL
            url = p.get("url")
            if isinstance(url, str) and "apikey=" in url:
                clean = re.sub(r"apikey=[^&]*&", "", url)
                clean = re.sub(r"[?&]apikey=[^&]*$", "", clean)
                p["url"] = clean
                cambios.append(("strip-apikey", n["name"], "apikey embebido", "removido"))

    if expected_pg != n_pg:
        print(f"[{tag}] ⚠ nodos postgres repunteados={n_pg}, esperados={expected_pg} "
              f"(el workflow evoluciono? revisar antes del modo real)")

    if not cambios:
        print(f"[{tag}] sin cambios (¿ya migrado?) — skip")
        continue

    # ── guardas (patron v2, generalizadas a todos los workflows) ──
    nodes_json = json.dumps(wf["nodes"], ensure_ascii=False)
    if len(wf["nodes"]) != len(before["nodes"]):
        die(f"{tag}: cambio el numero de nodos")
    for old in OLD_REFS:
        if old in nodes_json:
            die(f"{tag}: quedo una referencia al ref viejo {old}")
    for old_id in OLD_PG_CRED_IDS:
        if old_id in nodes_json:
            die(f"{tag}: quedo un nodo con la credencial pg vieja {old_id}")
    if not UPDATE_SUPA_CRED_IN_UI and OLD_SUPA_CRED_ID in nodes_json:
        die(f"{tag}: quedo un nodo con la credencial supabaseApi vieja")
    # set de webhookIds invariante (preserva evo-webhook-v2 y el resto de webhooks)
    wh_pre = sorted(n.get("webhookId", "") for n in before["nodes"] if n.get("webhookId"))
    wh_post = sorted(n.get("webhookId", "") for n in wf["nodes"] if n.get("webhookId"))
    if wh_pre != wh_post:
        die(f"{tag}: set de webhookId alterado ({wh_pre} → {wh_post})")
    if tag == "v6" and "evo-webhook-v2" not in nodes_json:
        die("v6: se perdio el webhookId evo-webhook-v2")

    total_pg += sum(1 for c in cambios if c[0] == "cred-pg")
    total_supa += sum(1 for c in cambios if c[0] == "cred-supa")
    total_url += sum(1 for c in cambios if c[0] == "ref-url")

    print(f"[{tag}] {len(cambios)} cambios{' (DRY RUN, no aplicado)' if DRY_RUN else ''}:")
    for kind, node, old, new in cambios:
        print(f"    {kind:12} {node:35} {old} → {new}")

    if DRY_RUN:
        resumen.append((tag, len(cambios), "dry"))
        continue

    settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
    body = {"name": wf["name"], "nodes": wf["nodes"], "connections": wf["connections"],
            "settings": settings, "staticData": wf.get("staticData")}
    res = api("PUT", f"/api/v1/workflows/{wid}", body)
    (HIST / f"{tag}_POST_{suffix}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    # verificacion post-PUT con re-GET
    v = api("GET", f"/api/v1/workflows/{wid}")
    vj = json.dumps(v.get("nodes", []), ensure_ascii=False)
    for old in OLD_REFS:
        if old in vj:
            die(f"{tag}: POST-VERIFY fallo — ref viejo {old} sigue en el servidor")
    if any(old_id in vj for old_id in OLD_PG_CRED_IDS):
        die(f"{tag}: POST-VERIFY fallo — cred pg vieja sigue en el servidor")
    if tag == "v6" and "evo-webhook-v2" not in vj:
        die("v6: POST-VERIFY fallo — evo-webhook-v2 no esta en el servidor")
    print(f"[{tag}] PUT OK + verificado (active={v.get('active')})")
    resumen.append((tag, len(cambios), "ok"))

# ────────────────────────────────────────────────────────────────────────────
# 7) cursor del Logger (solo lectura — decidir a mano)
# ────────────────────────────────────────────────────────────────────────────
print("\nCursor del Logger (staticData — NO se toca automaticamente):")
lg = api("GET", "/api/v1/workflows/xsXeHp7WLXnFQc3o")
sd = lg.get("staticData")
print("  ", json.dumps(sd, ensure_ascii=False)[:400] if sd else "(vacio)")
print("  → si se restauro n8n_chat_histories en v3, setear last_synced_chat_id = max(id)")
print("    restaurado (en v2 fue 154) para evitar re-sync duplicado. Ver fix_logger_last_synced.py")

print(f"\nRESUMEN: {resumen}")
print(f"  nodos pg repunteados: {total_pg} (esperados 19) | supabaseApi: {total_supa} "
      f"(esperados {'0 — modo UI' if UPDATE_SUPA_CRED_IN_UI else '9'}) | nodos con swap de URL/ref: {total_url}")
print(f"Backups en workflows/history/ con tag {suffix}")

# ────────────────────────────────────────────────────────────────────────────
# checklist post-rewire (imprime siempre; nada de esto lo hace el script)
# ────────────────────────────────────────────────────────────────────────────
print("""
CHECKLIST POST-REWIRE (manual, en orden):
  1. .env del repo: actualizar SUPABASE_URL / SUPABASE_PROJECT_REF / SUPABASE_DB_HOST /
     SUPABASE_DB_PORT / SUPABASE_DB_USER / SUPABASE_DB_PASSWORD y ANOTAR
     SUPABASE_SERVICE_ROLE_KEY (en v2 nunca quedo anotada — no repetir).
  2. DB v3 lista? (si no se hizo antes): tablas + secuencias max(id)+1 + match_documents
     → knowledge_base 1536 dims + tablas del 15/7 (escalaciones_log, peticiones,
     urgencias_log, servicios) + borrar fila envenenada "The servic..." de
     n8n_chat_histories (Sub-WF Cancelar Step 0b).
  3. Cursor del Logger: setear last_synced_chat_id (ver arriba).
  4. Smoke DB: python scripts/test_conexion_fresca.py (contra credencial v3).
  5. Backfill recordatorios: python scripts/recovery_backfill.py cubre el 16/7 (exec
     230100); ADAPTARLO para el 17/7 (exec 231766) — ambos enviaron WhatsApp sin loguear.
     OJO: retencion de executions ~72h — si pasaron mas de 3 dias los datos ya no estan.
  6. Reactivar (con OK de Lucas): Logger xsXeHp7WLXnFQc3o (quedo a 5 min) y Cleanup
     En0A5lXd3Whb5yFy (quedo 1x/dia) — POST /api/v1/workflows/{id}/activate, body {}.
     ResumenClinico BO1cdE8xmqln4IeO queda como este (hoy desactivado).
  7. Ping E2E: patron scripts/sim_and_wait.py "Cuanto sale la consulta?" → bot responde
     $50.000 y la memoria escribe filas nuevas en v3.
  8. Higiene diferida: borrar credenciales huerfanas (Postgres v1 xwvjww5Odcxiy1K9,
     'Postgres Supabase Nexora v2' EWhpNhb6tkGg1OTp, y 'Supabase account' Thn3jgEbbxPFD7d9
     si se creo la v3 nueva) + anotar ids nuevos en memory/decisions.md.
  9. Fondo (decision con Lucas): esto repite la fragilidad free-tier — el candidato era
     migrar Postgres al VPS Hostinger. v3 puede ser puente, no destino final.
""")
