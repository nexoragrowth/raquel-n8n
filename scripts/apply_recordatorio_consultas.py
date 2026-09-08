# -*- coding: utf-8 -*-
"""
apply_recordatorio_consultas.py — recordatorio DISTINTO para las CONSULTAS (primera visita) en el workflow
"Recordatorio de Turno 48HS - Dra. Raquel" (7RqTApkvVavRmq3R). Pedido textual de la Dra. Raquel
(WhatsApp 2026-09-08 09:20): "los turnos que tienen un puntito amarillo son consultas (o sea pacientes que
vienen por primera vez). Necesito que a todos ellos el agente le envie un mensaje en particular como
recordatorio del turno (...) Lo que quiero lograr es que sepan que la confirmacion es si o si con el pago".

Diseño y contrato: docs/recordatorio-consultas-2026-09-08.md · tests: node tests/test_recordatorio_consultas.js

QUÉ CAMBIA (3 nodos, 0 conexiones, 0 nodos nuevos, settings/trigger/webhook intactos):
  1. 'Preparar mensaje' (code, runOnceForEachItem) — jsCode = recordatorios/preparar_mensaje.js:
       es_consulta = /^consulta\b/i.test(trim(cita.motivo_atencion))  (único marcador confiable en Dentalink:
       tratamiento_sin_asignar es 0 en todas las citas; ANCLADO al inicio para que "Control post consulta" o
       "Consultar precio" no pidan el pago). Consulta + 72h -> bloque textual de la Dra. con el
       precio dinámico; consulta + 24h -> template corto de hoy + frase final; NO consulta -> los dos templates
       BYTE A BYTE como hoy (tests contra el snapshot vivo recordatorios/preparar_mensaje.vivo_2026-09-08.js).
       Suma motivo_atencion (string) y es_consulta (boolean) a la salida.
  2. 'Gate - Leer config' (postgres) — query = recordatorios/gate_leer_config.sql: la misma query de hoy más
       una subconsulta `(SELECT contenido FROM knowledge_base WHERE id = 21) AS precio_contenido`. La columna
       `suspender` queda idéntica ('Gate - ¿Suspendido hoy?' solo lee $json.suspender: verificado acá).
       Por qué en el Gate y no en un nodo nuevo: 'Preparar mensaje' empareja la cita por
       $("Solo citas activas").all()[$itemIndex] -> NO se puede insertar nada entre esos dos nodos.
       El camino MANUAL (webhook) no pasa por el Gate: 'Preparar mensaje' lo lee con try/catch y cae al
       fallback '$50.000' sin romper.
  3. 'Insert recordatorios_enviados' (postgres v2.6, defineBelow) — dos columnas nuevas en columns.value y
       en columns.schema: motivo_atencion (string) y es_consulta (boolean).

ORDEN OBLIGATORIO (R1): `--ddl` ANTES de `--apply`. El nodo Postgres v2.6 valida las columnas contra la TABLA
VIVA (no contra columns.schema) y el Insert corre DESPUÉS de 'Enviar WhatsApp': sin las columnas, el próximo
cron manda los WhatsApps y explota en el Insert (0 filas -> el bot no encuentra el turno cuando el paciente
responde "confirmo"). `--apply` se niega a correr si las columnas no existen.

REGLAS DURAS que cumple: GET fresco; dry-run default con diff textual SOLO de jsCode/query/columns (nunca se
imprime 'Enviar WhatsApp', que lleva la apikey inline); aborta si el nodo vivo no es ni el snapshot conocido ni
el ya-aplicado (target movido); aborta si cambió CUALQUIER cosa fuera de los 3 nodos declarados; backup PRE/POST
con timestamp en workflows/history/; PUT solo con name/nodes/connections/settings/staticData y settings filtradas
(quita availableInMCP/binaryMode; NO agrega timezone: el cron vivo '0 13 * * 1-5' sin tz corre 08:00 ART y un
timezone lo movería); assert webhookId 'trigger-recordatorios-manual' y expresión del cron; conserva el valor
vivo de `const TEST_MODE = ...;` (no cambia el modo de prueba de costado); idempotente; verificación post-PUT
contra lo que n8n REALMENTE guardó; `--rollback` solo acepta un PRE (nombre con `_PRE_` y 'Preparar mensaje' igual al
snapshot vivo): un POST re-aplicaría el cambio en vez de revertirlo.

USO:
  python scripts/apply_recordatorio_consultas.py             # default: dry-run (GET + diff + estado de la tabla)
  python scripts/apply_recordatorio_consultas.py --ddl       # ALTER TABLE ... ADD COLUMN IF NOT EXISTS (x2) + verificación
  python scripts/apply_recordatorio_consultas.py --apply     # PRE -> PUT -> POST -> verificación (exige --ddl hecho)
  python scripts/apply_recordatorio_consultas.py --rollback workflows/history/Recordatorio_PRE_consultas_<ts>.json

Regla del proyecto: NUNCA --apply sin OK explícito de Lucas. Antes del PUT: node tests/test_recordatorio_consultas.js
y python scripts/check_triaje.py. Después de la prueba real: scripts/limpiar_numero_demo.py (regla dura 9).
"""
import argparse
import copy
import difflib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_media_entrantes import api, clean_settings, PUT_KEYS  # noqa: E402  (NO importar WF_ID: ese es el v6)
from lib_env import env  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
WF_ID = env("N8N_WF_RECORDATORIOS", "7RqTApkvVavRmq3R")
LABEL = "consultas"

N_PREP, N_GATE, N_INSERT = "Preparar mensaje", "Gate - Leer config", "Insert recordatorios_enviados"
TOCABLES = {N_PREP, N_GATE, N_INSERT}
N_GATE_IF, N_WEBHOOK, N_TRIGGER = "Gate - ¿Suspendido hoy?", "Webhook Manual Recordatorios", "Diario 9AM Arg (cron 0 14 UTC)"
WEBHOOK_ID = "trigger-recordatorios-manual"
TRIGGER_EXPR = "0 13 * * 1-5"

# ---------------- fuentes únicas (las mismas que corre tests/test_recordatorio_consultas.js) ----------------
PREPARAR_JS = (ROOT / "recordatorios" / "preparar_mensaje.js").read_text(encoding="utf-8")
PREPARAR_JS_VIVO = (ROOT / "recordatorios" / "preparar_mensaje.vivo_2026-09-08.js").read_text(encoding="utf-8")
GATE_SQL = (ROOT / "recordatorios" / "gate_leer_config.sql").read_text(encoding="utf-8").strip()
GATE_SQL_VIVO = (
    "SELECT COALESCE(bool_or(\n"
    "    (NOT c.activo)\n"
    "    OR ((now() AT TIME ZONE 'America/Argentina/Jujuy')::date = ANY(c.dias_suspendidos))\n"
    "    OR (c.suspender_desde IS NOT NULL\n"
    "        AND (now() AT TIME ZONE 'America/Argentina/Jujuy')::date\n"
    "            BETWEEN c.suspender_desde AND c.suspender_hasta)\n"
    "  ), false) AS suspender\n"
    "FROM public.recordatorios_config c\n"
    "WHERE c.id = 1;"
)
RE_FLAG = re.compile(r"const TEST_MODE = (true|false);")  # la misma que apply_toggle_recordatorios_test_mode.py
# Lo ÚNICO que se agrega a la query del Gate. Sanity de las fuentes: el .sql tiene que ser la query viva + esta subconsulta.
SUBQ_PRECIO = " AS suspender,\n  (SELECT kb.contenido FROM public.knowledge_base kb WHERE kb.id = 21) AS precio_contenido\n"
assert GATE_SQL.replace(SUBQ_PRECIO, " AS suspender\n") == GATE_SQL_VIVO, \
    "recordatorios/gate_leer_config.sql no es la query viva del Gate + la subconsulta precio_contenido"

# Columnas HOY del Insert (el orden importa: se comparan las keys).
COLS_VIVAS = ["telefono", "chat_remote_jid", "id_cita_dentalink", "id_paciente_dentalink", "nombre_paciente",
              "fecha_turno", "hora_turno", "tipo", "workflow_execution_id"]
COLS_NUEVAS = [("motivo_atencion", "string"), ("es_consulta", "boolean")]
VALUE_NUEVO = {c: "={{ $('Preparar mensaje').item.json." + c + " }}" for c, _ in COLS_NUEVAS}
SCHEMA_NUEVO = [{"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True, "type": t,
                 "canBeUsedToMatch": True} for c, t in COLS_NUEVAS]

DDL = [
    "ALTER TABLE public.recordatorios_enviados ADD COLUMN IF NOT EXISTS motivo_atencion TEXT",
    "ALTER TABLE public.recordatorios_enviados ADD COLUMN IF NOT EXISTS es_consulta BOOLEAN",
]
SQL_COLS = ("SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'recordatorios_enviados' "
            "AND column_name IN ('motivo_atencion', 'es_consulta') ORDER BY column_name")


# ---------------- helpers ----------------
def enmascarar(s):
    """Nunca imprimir teléfonos completos: 10-13 dígitos seguidos -> 4 + *** + 3."""
    return re.sub(r"\d{10,13}", lambda m: m.group(0)[:4] + "*****" + m.group(0)[-3:], s)


def mostrar_diff(antes, despues, titulo):
    print(f"\n── {titulo}  ({len(antes)} -> {len(despues)} chars)")
    if antes == despues:
        print("  (sin cambios)")
        return
    for linea in difflib.unified_diff(antes.splitlines(), despues.splitlines(), lineterm="", n=2):
        if linea.startswith(("---", "+++")):
            continue
        print("  " + enmascarar(linea[:200]))


def nodo(wf, name):
    n = next((n for n in wf["nodes"] if n["name"] == name), None)
    if n is None:
        sys.exit(f"ERROR: no encontré el nodo {name!r} en el workflow {WF_ID}.")
    return n


def js_con_flag(js, flag):
    return RE_FLAG.sub(f"const TEST_MODE = {flag};", js, count=1)


def flag_vivo(wf):
    """Valor VIVO de `const TEST_MODE = ...;` en 'Preparar mensaje' ('true'|'false'). Aborta con mensaje claro si falta."""
    js_live = nodo(wf, N_PREP)["parameters"].get("jsCode", "")
    m = RE_FLAG.search(js_live)
    if not m:
        sys.exit(f"ERROR: {N_PREP!r} no tiene 'const TEST_MODE = true/false;' — abortado")
    return m.group(1)


def db_conn():
    """psycopg2 al Supabase v3 (SUPABASE_DB_* del .env, == SUPABASE_V3_DB_*). Mismo patrón que create_media_entrantes.py."""
    import psycopg2
    faltan = [k for k in ("SUPABASE_DB_HOST", "SUPABASE_DB_USER", "SUPABASE_DB_PASSWORD") if not env(k)]
    if faltan:
        sys.exit(f"ERROR: faltan en .env: {faltan}")
    conn = psycopg2.connect(host=env("SUPABASE_DB_HOST"), port=env("SUPABASE_DB_PORT", "5432"),
                            dbname=env("SUPABASE_DB_NAME", "postgres"), user=env("SUPABASE_DB_USER"),
                            password=env("SUPABASE_DB_PASSWORD"), sslmode="require", connect_timeout=20)
    conn.autocommit = True
    return conn


def columnas_en_tabla():
    """{'motivo_atencion': 'text', 'es_consulta': 'boolean'} según la tabla VIVA (solo SELECT). None si la base no responde."""
    try:
        with db_conn() as conn, conn.cursor() as cur:
            cur.execute(SQL_COLS)
            return {r[0]: r[1] for r in cur.fetchall()}
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"  (no pude consultar la tabla: {type(e).__name__}: {str(e)[:120]})")
        return None


# ---------------- construcción ----------------
def build(wf):
    """Devuelve (new, cambios, detalle). Idempotente: si los 3 nodos ya están, cambios = []."""
    new = copy.deepcopy(wf)
    cambios, detalle = [], {}

    # 1) Preparar mensaje: conservar el valor VIVO de TEST_MODE (este cambio no toca el modo de prueba)
    prep = nodo(new, N_PREP)
    if prep["parameters"].get("mode") != "runOnceForEachItem":
        sys.exit(f"ERROR: {N_PREP!r} no está en runOnceForEachItem (mode={prep['parameters'].get('mode')!r}) — abortado")
    js_live = prep["parameters"].get("jsCode", "")
    flag = flag_vivo(new)
    js_nuevo = js_con_flag(PREPARAR_JS, flag)
    if flag == "true":
        print(f"  ⚠️  TEST_MODE está en true en el nodo vivo: se conserva (apagalo con apply_toggle_recordatorios_test_mode.py --off).")
    if js_live == js_nuevo:
        detalle[N_PREP] = "ya aplicado"
    elif js_live == js_con_flag(PREPARAR_JS_VIVO, flag):
        prep["parameters"]["jsCode"] = js_nuevo
        cambios.append(N_PREP)
        detalle[N_PREP] = (js_live, js_nuevo)
    else:
        sys.exit(f"ERROR: el jsCode vivo de {N_PREP!r} no coincide ni con el snapshot del 2026-09-08 ni con el nuevo: "
                 "alguien lo cambió. Bajalo por GET, actualizá recordatorios/preparar_mensaje.vivo_*.js y revisá el diff.")

    # 2) Gate - Leer config: la misma query + precio_contenido
    gate = nodo(new, N_GATE)
    q_live = gate["parameters"].get("query", "")
    if q_live.strip() == GATE_SQL:
        detalle[N_GATE] = "ya aplicado"
    elif q_live.strip() == GATE_SQL_VIVO:
        gate["parameters"]["query"] = GATE_SQL
        cambios.append(N_GATE)
        detalle[N_GATE] = (q_live, GATE_SQL)
    else:
        sys.exit(f"ERROR: la query viva de {N_GATE!r} no es la conocida — abortado")
    if gate.get("onError") != "continueRegularOutput":
        sys.exit(f"ERROR: {N_GATE!r} perdió onError=continueRegularOutput (fail-open del gate) — abortado")

    # 3) Insert recordatorios_enviados: 2 columnas más en value + schema
    ins = nodo(new, N_INSERT)
    cols = ins["parameters"].get("columns", {})
    if cols.get("mappingMode") != "defineBelow" or ins.get("typeVersion") != 2.6:
        sys.exit(f"ERROR: {N_INSERT!r} no es postgres v2.6 defineBelow — abortado")
    value, schema = cols.get("value", {}), cols.get("schema", [])
    keys, ids = list(value.keys()), [s.get("id") for s in schema]
    esperado_keys, esperado_ids = COLS_VIVAS + [c for c, _ in COLS_NUEVAS], COLS_VIVAS + [c for c, _ in COLS_NUEVAS]
    if keys == esperado_keys and ids == esperado_ids and all(value[c] == VALUE_NUEVO[c] for c, _ in COLS_NUEVAS):
        detalle[N_INSERT] = "ya aplicado"
    elif keys == COLS_VIVAS and ids == COLS_VIVAS:
        antes = json.dumps({"value": value, "schema": schema}, ensure_ascii=False, indent=1)
        value.update(VALUE_NUEVO)
        schema.extend(copy.deepcopy(SCHEMA_NUEVO))
        cambios.append(N_INSERT)
        detalle[N_INSERT] = (antes, json.dumps({"value": value, "schema": schema}, ensure_ascii=False, indent=1))
    else:
        sys.exit(f"ERROR: las columnas vivas de {N_INSERT!r} no son las conocidas: {keys} / {ids} — abortado")

    return new, cambios, detalle


def fuera_de_alcance(wf, new):
    """Nodos (fuera de los 3 declarados) y conexiones que difieren. Este script NO toca conexiones: cualquier diff aborta."""
    a = {n["name"]: n for n in wf["nodes"]}
    b = {n["name"]: n for n in new["nodes"]}
    nodos = sorted(k for k in set(a) | set(b) if k not in TOCABLES and a.get(k) != b.get(k))
    conexiones = sorted(k for k in set(wf["connections"]) | set(new["connections"])
                        if wf["connections"].get(k) != new["connections"].get(k))
    return nodos, conexiones


def verify(wf, flag):
    """Booleans sobre un workflow (el construido o el que devolvió n8n tras el PUT)."""
    names = {n["name"]: n for n in wf["nodes"]}
    prep, gate, ins = names.get(N_PREP, {}), names.get(N_GATE, {}), names.get(N_INSERT, {})
    js = prep.get("parameters", {}).get("jsCode", "")
    cols = ins.get("parameters", {}).get("columns", {})
    value, schema = cols.get("value", {}), cols.get("schema", [])
    gate_if = names.get(N_GATE_IF, {}).get("parameters", {}).get("conditions", {}).get("conditions", [{}])
    trig = names.get(N_TRIGGER, {}).get("parameters", {}).get("rule", {}).get("interval", [{}])[0]
    det = {
        "preparar_jsCode_igual_fuente": js == js_con_flag(PREPARAR_JS, flag),
        "preparar_test_mode_conservado": f"const TEST_MODE = {flag};" in js,
        "preparar_templates_vivos_verbatim": all(l in js for l in _lineas_template_vivo()),
        "preparar_bloque_dra": "Para confirmar su asistencia le solicitamos abonar el valor de la consulta (" in js
                               and "* Si su turno ya está abonado, solo responda a este mensaje con un \\\"confirmo\\\"." in js,
        "preparar_gate_en_try_catch": bool(re.search(r"try \{[\s\S]*\$\('Gate - Leer config'\)\.first\(\)\.json[\s\S]*\} catch", js)),
        "preparar_mode_each_item": prep.get("parameters", {}).get("mode") == "runOnceForEachItem",
        "gate_query_igual_fuente": gate.get("parameters", {}).get("query", "").strip() == GATE_SQL,
        # Sobre la query REAL del nodo (no sobre las constantes): sin la subconsulta tiene que quedar la query viva exacta.
        "gate_suspender_intacto": gate.get("parameters", {}).get("query", "").strip().replace(SUBQ_PRECIO, " AS suspender\n") == GATE_SQL_VIVO,
        "gate_onError_fail_open": gate.get("onError") == "continueRegularOutput",
        "gate_if_lee_suspender": gate_if[0].get("leftValue") == "={{ $json.suspender }}",
        "insert_value_nuevas": all(value.get(c) == VALUE_NUEVO[c] for c, _ in COLS_NUEVAS),
        "insert_schema_nuevas": [s for s in schema if s.get("id") in VALUE_NUEVO] == SCHEMA_NUEVO,
        "insert_columnas_viejas_intactas": list(value.keys())[:9] == COLS_VIVAS and [s.get("id") for s in schema][:9] == COLS_VIVAS,
        "webhookId": names.get(N_WEBHOOK, {}).get("webhookId") == WEBHOOK_ID,
        "trigger_cron_intacto": trig.get("expression") == TRIGGER_EXPR,
        "settings_sin_timezone": "timezone" not in (wf.get("settings") or {}),
        "21_nodos": len(wf["nodes"]) == 21,
    }
    return all(det.values()), det


def _lineas_template_vivo():
    sec = PREPARAR_JS_VIVO.split("=== TEMPLATES OFICIALES ===")[1].split("const finalPhone")[0]
    return [l for l in sec.splitlines() if l.strip().startswith('"')]


def body_para_put(wf):
    body = {k: wf[k] for k in PUT_KEYS if k in wf}
    body["settings"] = clean_settings(wf)
    wh = next(n for n in body["nodes"] if n["name"] == N_WEBHOOK)
    assert wh.get("webhookId") == WEBHOOK_ID, "webhookId del webhook manual perdido — abortado"
    trig = next(n for n in body["nodes"] if n["name"] == N_TRIGGER)
    assert trig["parameters"]["rule"]["interval"][0]["expression"] == TRIGGER_EXPR, "expresión del cron cambiada — abortado"
    assert "timezone" not in body["settings"], "settings.timezone apareció (movería el cron) — abortado"
    return body


def backup(wf, tag, ts):
    HIST.mkdir(parents=True, exist_ok=True)
    p = HIST / f"Recordatorio_{tag}_{LABEL}_{ts}.json"
    p.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{tag} backup -> {p}")
    return p


# ---------------- comandos ----------------
def cmd_ddl():
    print("DDL (idempotente) sobre public.recordatorios_enviados:")
    with db_conn() as conn, conn.cursor() as cur:
        antes = columnas_en_tabla() or {}
        for stmt in DDL:
            print("  " + stmt)
            cur.execute(stmt)
        cur.execute(SQL_COLS)
        despues = {r[0]: r[1] for r in cur.fetchall()}
    ok = despues == {"motivo_atencion": "text", "es_consulta": "boolean"}
    print(f"  antes: {antes or 'ninguna'} -> después: {despues}  {'✅' if ok else '!! NO COINCIDE'}")
    return 0 if ok else 1


def cmd_rollback(path):
    pre = json.loads(Path(path).read_text(encoding="utf-8"))
    if pre.get("id") not in (None, WF_ID):
        sys.exit(f"ERROR: {path} es del workflow {pre.get('id')}, no de {WF_ID}")
    # Solo se acepta un PRE de verdad: nombre con '_PRE_' Y 'Preparar mensaje' igual al snapshot VIVO conocido. Un
    # Recordatorio_POST_*.json (o un PRE_rollback) también trae el id del WF pero con el jsCode NUEVO: "revertir" desde
    # ahí RE-APLICARÍA el cambio.
    js_pre = nodo(pre, N_PREP)["parameters"].get("jsCode", "")
    m = RE_FLAG.search(js_pre)
    flag_pre = m.group(1) if m else "false"
    if js_pre == js_con_flag(PREPARAR_JS, flag_pre):
        sys.exit(f"ERROR: {path} ya trae el jsCode NUEVO de {N_PREP!r} (es un POST o un PRE_rollback): un rollback desde acá "
                 "RE-APLICARÍA el cambio. Usá workflows/history/Recordatorio_PRE_consultas_<ts>.json.")
    problemas = []
    if "_PRE_" not in Path(path).name:
        problemas.append("el nombre no contiene '_PRE_'")
    if js_pre != js_con_flag(PREPARAR_JS_VIVO, flag_pre):
        problemas.append(f"el jsCode de {N_PREP!r} no es el snapshot vivo (recordatorios/preparar_mensaje.vivo_2026-09-08.js)")
    if problemas:
        sys.exit(f"ERROR: {path} no es un PRE conocido: {'; '.join(problemas)} — abortado")
    actual = api(f"/workflows/{WF_ID}")
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup(actual, "PRE_rollback", ts)  # por si el rollback mismo hay que deshacerlo
    api(f"/workflows/{WF_ID}", method="PUT", payload=body_para_put(pre))
    after = api(f"/workflows/{WF_ID}")
    backup(after, "POST_rollback", ts)
    js = nodo(after, N_PREP)["parameters"]["jsCode"]
    gate_ok = nodo(after, N_GATE)["parameters"].get("query", "").strip() == GATE_SQL_VIVO
    ins_ok = list(nodo(after, N_INSERT)["parameters"].get("columns", {}).get("value", {}).keys()) == COLS_VIVAS
    print(f"↩️  rollback aplicado desde {path}: {len(after['nodes'])} nodos, activo={after['active']}, "
          f"Preparar mensaje == backup: {js == nodo(pre, N_PREP)['parameters']['jsCode']}, Gate == vivo: {gate_ok}, "
          f"Insert == columnas vivas: {ins_ok}")
    print("Las columnas motivo_atencion/es_consulta quedan en la tabla (inocuas: nullable, nadie las exige).")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="(default) GET + diff, no toca n8n ni la base")
    ap.add_argument("--ddl", action="store_true", help="agrega las 2 columnas a recordatorios_enviados (ANTES del --apply)")
    ap.add_argument("--apply", action="store_true", help="PRE -> PUT -> POST -> verificación")
    ap.add_argument("--rollback", metavar="PRE.json")
    args = ap.parse_args()

    if args.rollback:
        return cmd_rollback(args.rollback)
    if args.ddl:
        return cmd_ddl()

    wf = api(f"/workflows/{WF_ID}")
    version = wf.get("versionId")
    print(f"{wf['name']}: {len(wf['nodes'])} nodos, activo={wf['active']}, updatedAt={wf.get('updatedAt')}, versionId={version}")
    flag = flag_vivo(wf)
    new, cambios, detalle = build(wf)

    nodos_fuera, conns_fuera = fuera_de_alcance(wf, new)
    if nodos_fuera or conns_fuera:
        sys.exit(f"ERROR: el build tocó algo fuera de los 3 nodos declarados: nodos={nodos_fuera} conexiones={conns_fuera}")

    if not cambios:
        print("\n(ya aplicado: los 3 nodos están como en la fuente; nada que hacer)")
        ok, det = verify(wf, flag)
        print(f"verificación del vivo: {det}")
        return 0 if ok else 1

    for name in (N_PREP, N_GATE, N_INSERT):
        d = detalle[name]
        if d == "ya aplicado":
            print(f"\n── {name}: ya aplicado")
        else:
            campo = {N_PREP: "jsCode", N_GATE: "query", N_INSERT: "columns.value + columns.schema"}[name]
            mostrar_diff(d[0], d[1], f"{name} · {campo}")

    print(f"\nnodos: {len(new['nodes'])} (sin cambios) · conexiones: sin cambios · nodos modificados: {cambios}")
    print(f"settings que van en el PUT: {clean_settings(new)}  (se filtran {sorted(set(wf.get('settings') or {}) - set(clean_settings(wf)))})")
    ok, det = verify(new, flag)
    print(f"verificación del build: {'OK' if ok else 'FALLA'} {det}")
    if not ok:
        sys.exit("ERROR: el build no pasa la verificación — abortado")

    print("\nTabla recordatorios_enviados (SELECT information_schema):")
    cols = columnas_en_tabla()
    ddl_ok = cols == {"motivo_atencion": "text", "es_consulta": "boolean"}
    print(f"  columnas nuevas presentes: {cols if cols else 'NINGUNA'}  -> {'OK' if ddl_ok else 'FALTA --ddl (R1)'}")

    if not args.apply:
        print("\n[DRY-RUN] no se tocó n8n. Antes de --apply: node tests/test_recordatorio_consultas.js · "
              "python scripts/check_triaje.py · (si falta) --ddl")
        return 0

    if not ddl_ok:
        sys.exit("ERROR: las columnas motivo_atencion/es_consulta NO existen en la tabla viva. Corré --ddl primero (R1): "
                 "el Insert corre después del envío y explotaría en el próximo cron.")

    ts = time.strftime("%Y%m%d_%H%M%S")
    actual = api(f"/workflows/{WF_ID}")
    if actual.get("versionId") != version:
        sys.exit("ERROR: el workflow cambió entre el GET y el PUT. Volvé a correr el dry-run.")
    backup(actual, "PRE", ts)

    api(f"/workflows/{WF_ID}", method="PUT", payload=body_para_put(new))

    after = api(f"/workflows/{WF_ID}")
    backup(after, "POST", ts)
    ok, det = verify(after, flag)
    nodos_fuera, conns_fuera = fuera_de_alcance(wf, after)
    print(f"verificación post-PUT: {'OK' if ok else 'FALLA'} {det}")
    print(f"fuera de alcance post-PUT: nodos={nodos_fuera} conexiones={conns_fuera}")
    if not ok or nodos_fuera or conns_fuera:
        sys.exit(f"ERROR: la verificación post-PUT falló. Rollback: --rollback {HIST / f'Recordatorio_PRE_{LABEL}_{ts}.json'}")
    print(f"✅ aplicado: {len(after['nodes'])} nodos, activo={after['active']}, versionId={after.get('versionId')}")
    print("Siguiente: prueba real por el webhook manual (docs/recordatorio-consultas-2026-09-08.md §6) y limpieza (regla 9).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
