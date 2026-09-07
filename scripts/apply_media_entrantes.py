# -*- coding: utf-8 -*-
"""
apply_media_entrantes.py — el v6 guarda los ADJUNTOS del paciente (foto, audio, video, documento, sticker)
en Supabase Storage (bucket PRIVADO `pacientes-media`) y los registra en `media_entrantes`, para que el panel
muestre la imagen / el video / el audio / el documento en vez de un chip con la descripción del bot.

Diseño y contrato: docs/media-entrantes-2026-09-06.md · tabla y bucket: scripts/create_media_entrantes.py

QUÉ CAMBIA EN EL v6 (6 nodos nuevos con prefijo "Media: " + 6 conexiones existentes recableadas + Merge 5 -> 2 entradas):
  Set Marker Audio/Imagen/Documento/Otros  ──►  Media: Preparar (code)  ──►  Media: ¿Hay archivo? (if)
      [sí] ──► Media: Subir a Storage (httpRequest, cred supabaseApi) ──► Media: ¿Subida OK? (if)
                   [sí] ──► Media: Registrar (postgres insert defineBelow) ──► Media: Marcar (set) ──► Merge Multimedia[0]
                   [no] ──────────────────────────────────────────────────► Media: Marcar
      [no] ─────────────────────────────────────────────────────────────► Media: Marcar
  Set Passthrough Texto ──► Merge Multimedia[1]   (antes [4]; Merge pasa de numberInputs 5 a 2)

  "Media: Marcar" deja en `text` el marcador de siempre y le AGREGA ' [MEDIA:<id>]' SOLO si el INSERT devolvió la
  fila con ese id. Si algo falla (sin base64, Storage caído, tabla inexistente…) el texto sale idéntico a hoy y el
  bot sigue: todos los nodos nuevos que hablan con afuera llevan onError continueRegularOutput.

POR QUÉ Merge con 2 entradas y no 5 con 3 sueltas: en producción está probado (execs 271999, 270763, 270624, 269685…)
que Merge v3 append con executionOrder v1 emite cuando UNA sola de sus entradas CONECTADAS recibe datos; no hay
evidencia del caso "entrada declarada sin conexión", así que se reproduce exactamente el patrón probado.

SECRETOS: ninguno en este archivo. La URL del proyecto v3 se lee del nodo vivo `obtener_historial_paciente` (fallback
`consultar_recordatorios_abiertos`) y se cruza con V3_SUPABASE_URL del .env.local del panel / SUPABASE_V3_URL del .env;
las credenciales (supabaseApi H1PRagttKC5kxSzs, postgres TpYhZX4UT61xAKSV) se copian de nodos vivos y se verifica el id.

REGLAS DURAS que cumple: GET fresco, asserts de las conexiones esperadas (aborta si el cableado no es el conocido),
backup PRE/POST con timestamp, PUT solo con name/nodes/connections/settings/staticData y settings filtradas,
assert webhookId 'evo-webhook-v2', idempotente (re-correr reemplaza los nodos "Media: " conservando id/posición),
verificación post-PUT y chequeo de que NADA fuera de la rama multimedia cambió.

USO:
  python scripts/apply_media_entrantes.py [--dry-run]       # default: cambios + diff de conexiones/Merge, no toca n8n
  python scripts/apply_media_entrantes.py --apply           # backup PRE -> PUT -> backup POST -> verificación GET
  python scripts/apply_media_entrantes.py --rollback-wiring # vuelve al cableado de hoy (nodos "Media: " quedan huérfanos)
  python scripts/apply_media_entrantes.py --rollback <workflows/history/v6_PRE_media_entrantes_*.json>   # PUT del backup completo
"""
import argparse, copy, difflib, json, os, re, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
WF_ID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}
SUPABASE_CRED_ID = "H1PRagttKC5kxSzs"   # "Supabase account v3" (obtener_historial_paciente / consultar_recordatorios_abiertos)
PG_CRED_ID = "TpYhZX4UT61xAKSV"         # "Postgres Supabase Nexora v3" (Inbox Live)
BUCKET = "pacientes-media"
TABLA = "media_entrantes"
LABEL = "media_entrantes"

# ---------------- fuentes únicas (mismos archivos que corre tests/test_media_nodos.js) ----------------
PREPARAR_JS = (ROOT / "media" / "preparar.js").read_text(encoding="utf-8")
MARCAR_EXPR = (ROOT / "media" / "marcar_expr.js").read_text(encoding="utf-8").strip()
SUBIDA_OK_EXPR = (ROOT / "media" / "subida_ok_expr.js").read_text(encoding="utf-8").strip()

N_PREPARAR, N_HAY, N_SUBIR, N_SUBIDA_OK, N_REGISTRAR, N_MARCAR = (
    "Media: Preparar", "Media: ¿Hay archivo?", "Media: Subir a Storage", "Media: ¿Subida OK?", "Media: Registrar", "Media: Marcar")
NODOS_MEDIA = [N_PREPARAR, N_HAY, N_SUBIR, N_SUBIDA_OK, N_REGISTRAR, N_MARCAR]
MERGE, PASSTHROUGH, WEBHOOK, EXTRAER = "Merge Multimedia", "Set Passthrough Texto", "Webhook - Evolution API", "Edit Fields - Extraer Datos"
# Set Marker -> índice de entrada del Merge que usa HOY (cableado esperado antes del cambio)
SET_MARKERS = {"Set Marker Audio": 0, "Set Marker Imagen": 1, "Set Marker Documento": 2, "Set Marker Otros": 3}
PASSTHROUGH_IDX_ANTES, PASSTHROUGH_IDX_DESPUES = 4, 1
AFECTADOS = list(SET_MARKERS) + [PASSTHROUGH] + NODOS_MEDIA   # claves de `connections` que este script puede tocar

# ---------------- helpers API ----------------
def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    key = require("N8N_API_KEY")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": key, "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

def clean_settings(wf):
    return {k: v for k, v in (wf.get("settings") or {}).items() if k in SETTINGS_OK}

def conn_list(conns, name, idx):
    try:
        return [{"node": c["node"], "type": c["type"], "index": c["index"]} for c in conns[name]["main"][idx]]
    except (KeyError, IndexError):
        return None

def C(name, idx=0): return {"node": name, "type": "main", "index": idx}

def leer_env_var(path, key):
    p = Path(path)
    if not p.exists(): return None
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        if k.strip() == key: return v.strip().strip('"').strip("'") or None
    return None

def host_de_url(url):
    m = re.match(r"^=?\s*(https://[a-z0-9-]+\.supabase\.co)", str(url or ""))
    return m.group(1) if m else None

def resolver_host_v3(names):
    """Host https://<ref>.supabase.co del proyecto v3. Fuente primaria: nodo vivo; se cruza con los .env (sin imprimir secretos)."""
    fuentes = []
    for nodo in ("obtener_historial_paciente", "consultar_recordatorios_abiertos"):
        if nodo in names:
            h = host_de_url(names[nodo].get("parameters", {}).get("url"))
            if h: fuentes.append((f"nodo vivo {nodo!r}", h))
    for etiqueta, path, key in (("panel .env.local V3_SUPABASE_URL", ROOT / "panel" / ".env.local", "V3_SUPABASE_URL"),
                                ("panel .env.local V3_SUPABASE_URL", ROOT.parent / "nexora-whatsapp-agent" / ".env.local", "V3_SUPABASE_URL"),
                                ("raquel .env SUPABASE_V3_URL", ROOT / ".env", "SUPABASE_V3_URL")):
        h = host_de_url(leer_env_var(path, key))
        if h and (etiqueta, h) not in fuentes: fuentes.append((etiqueta, h))
    if not fuentes:
        sys.exit("ERROR: no pude resolver el host del Supabase v3 (ni nodo vivo ni env)")
    hosts = {h for _, h in fuentes}
    if len(hosts) != 1:
        sys.exit(f"ERROR: los hosts del v3 no coinciden entre fuentes: {fuentes!r}")
    return fuentes[0][1], fuentes

# ---------------- constructores ----------------
def if_bool(nid, name, pos, expr):
    return {"id": nid, "name": name, "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": pos,
            "parameters": {"conditions": {"options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                                          "conditions": [{"id": nid + "-c", "leftValue": expr, "rightValue": True,
                                                          "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                                          "combinator": "and"}, "options": {}}}

def build(wf):
    new = copy.deepcopy(wf)
    nodes = new["nodes"]; conns = new["connections"]
    names = {n["name"]: n for n in nodes}
    cambios = []

    for req in list(SET_MARKERS) + [PASSTHROUGH, MERGE, WEBHOOK, EXTRAER, "Buffer: Push Mensaje", "Buffer: Wait 10s", "Inbox Live"]:
        if req not in names:
            sys.exit(f"ERROR: falta el nodo {req!r} en el v6")

    # credenciales copiadas EN CALIENTE de nodos vivos (se verifica el id conocido)
    sb_node = names.get("obtener_historial_paciente") or names.get("consultar_recordatorios_abiertos")
    sb_cred = copy.deepcopy((sb_node or {}).get("credentials", {}).get("supabaseApi"))
    if not sb_cred or sb_cred.get("id") != SUPABASE_CRED_ID:
        sys.exit(f"ERROR: credencial supabaseApi inesperada en el nodo vivo: {sb_cred!r} (esperaba id {SUPABASE_CRED_ID})")
    pg_cred = copy.deepcopy(names["Inbox Live"].get("credentials", {}).get("postgres"))
    if not pg_cred or pg_cred.get("id") != PG_CRED_ID:
        sys.exit(f"ERROR: credencial postgres inesperada en Inbox Live: {pg_cred!r} (esperaba id {PG_CRED_ID})")
    host, fuentes_host = resolver_host_v3(names)

    # posiciones: fila propia debajo de la rama multimedia (banda libre: nada debajo de y=944 entre x 5400 y 7400)
    x0 = names["Set Marker Documento"]["position"][0]
    y0 = max(n["position"][1] for n in nodes if x0 - 200 <= n["position"][0] <= x0 + 6 * 288 + 200 and not n["name"].startswith("Media: ")) + 206
    P = lambda col: [x0 + col * 288, y0]

    PRE = "$('Media: Preparar').first().json"
    nuevos = [
        {"id": "media-preparar", "name": N_PREPARAR, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": P(0),
         "parameters": {"jsCode": PREPARAR_JS}, "onError": "continueRegularOutput"},
        if_bool("media-hay-archivo", N_HAY, P(1), "={{ $json.hay_archivo === true }}"),
        {"id": "media-subir", "name": N_SUBIR, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": P(2),
         "parameters": {"method": "POST", "url": "=" + host + "/storage/v1/object/" + BUCKET + "/{{ $json.path }}",
                        "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
                        "sendHeaders": True,
                        # cache-control: Storage lo guarda como metadata del objeto y lo sirve en la URL firmada; sin él
                        # responde `no-cache` y cada remount de <img>/<video> en el panel revalida (mismo valor que usa el
                        # panel para panel-media: cacheControl '3600', y que la firma dura 1 h).
                        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "={{ $json.mime }}"},
                                                            {"name": "x-upsert", "value": "true"},
                                                            {"name": "cache-control", "value": "max-age=3600"}]},
                        "sendBody": True, "contentType": "binaryData", "inputDataFieldName": "data",
                        "options": {"response": {"response": {"neverError": True, "fullResponse": True}}, "timeout": 30000}},
         "credentials": {"supabaseApi": sb_cred}, "onError": "continueRegularOutput"},
        if_bool("media-subida-ok", N_SUBIDA_OK, P(3), "={{ " + SUBIDA_OK_EXPR + " }}"),
        # INSERT parametrizado por el nodo (mappingMode defineBelow), MISMO patrón que `Inbox Live`. NO executeQuery+queryReplacement
        # (n8n parte los parámetros por coma después de evaluar: un caption con coma rompería). Devuelve la fila (RETURNING *).
        {"id": "media-registrar", "name": N_REGISTRAR, "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": P(4),
         "parameters": {"schema": {"__rl": True, "value": "public", "mode": "list"},
                        "table": {"__rl": True, "value": TABLA, "mode": "list"},
                        "columns": {"mappingMode": "defineBelow", "value": {
                            "id": "={{ " + PRE + ".id }}",
                            "key_id": "={{ " + PRE + ".key_id || null }}",
                            "telefono": "={{ " + PRE + ".telefono }}",
                            "from_me": "={{ !!" + PRE + ".from_me }}",
                            "tipo": "={{ " + PRE + ".tipo }}",
                            "mime": "={{ " + PRE + ".mime || null }}",
                            "bucket": BUCKET,
                            "path": "={{ " + PRE + ".path }}",
                            "bytes": "={{ " + PRE + ".bytes }}",
                            "filename": "={{ " + PRE + ".filename || null }}",
                            "caption": "={{ " + PRE + ".caption || null }}"}},
                        "options": {}},
         "credentials": {"postgres": pg_cred}, "onError": "continueRegularOutput"},
        {"id": "media-marcar", "name": N_MARCAR, "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": P(5),
         "parameters": {"assignments": {"assignments": [{"id": "a-text", "name": "text", "type": "string",
                                                         "value": "={{ " + MARCAR_EXPR + " }}"}]}, "options": {}}},
    ]

    # idempotencia: si existen, se reemplazan conservando id/position
    for n in nuevos:
        if n["name"] in names:
            prev = names[n["name"]]
            n["position"] = prev.get("position", n["position"]); n["id"] = prev.get("id", n["id"])
            nodes[nodes.index(prev)] = n
            cambios.append(f"ACTUALIZA {n['name']!r}")
        else:
            nodes.append(n)
            cambios.append(f"AGREGA {n['name']!r} ({n['type'].split('.')[-1]} v{n['typeVersion']}"
                           + (f", cred {list(n['credentials'].values())[0]['name']!r}" if n.get("credentials") else "")
                           + (f", onError={n['onError']}" if n.get("onError") else "") + ")")
        names[n["name"]] = n

    # ---- conexiones existentes: solo si el cableado es el conocido (o ya está aplicado) ----
    for sm, idx in SET_MARKERS.items():
        act = conn_list(conns, sm, 0)
        if act == [C(MERGE, idx)]:
            conns[sm]["main"][0] = [C(N_PREPARAR)]
            cambios.append(f"REWIRE {sm}[0]: {MERGE}[{idx}] -> {N_PREPARAR}")
        elif act == [C(N_PREPARAR)]:
            cambios.append(f"{sm}[0] ya apunta a {N_PREPARAR} (idempotente)")
        else:
            sys.exit(f"ERROR: {sm}[0] inesperado: {act!r}")
    act = conn_list(conns, PASSTHROUGH, 0)
    if act == [C(MERGE, PASSTHROUGH_IDX_ANTES)]:
        conns[PASSTHROUGH]["main"][0] = [C(MERGE, PASSTHROUGH_IDX_DESPUES)]
        cambios.append(f"REWIRE {PASSTHROUGH}[0]: {MERGE}[{PASSTHROUGH_IDX_ANTES}] -> {MERGE}[{PASSTHROUGH_IDX_DESPUES}]")
    elif act == [C(MERGE, PASSTHROUGH_IDX_DESPUES)]:
        cambios.append(f"{PASSTHROUGH}[0] ya apunta a {MERGE}[{PASSTHROUGH_IDX_DESPUES}] (idempotente)")
    else:
        sys.exit(f"ERROR: {PASSTHROUGH}[0] inesperado: {act!r}")
    merge = names[MERGE]
    if merge["typeVersion"] != 3 or (merge["parameters"].get("mode", "append") != "append"):
        sys.exit(f"ERROR: {MERGE} inesperado: v{merge['typeVersion']} {merge['parameters']!r}")
    ni = merge["parameters"].get("numberInputs")
    if ni == 5:
        merge["parameters"]["numberInputs"] = 2
        cambios.append(f"{MERGE}: numberInputs 5 -> 2 (entrada 0 = {N_MARCAR}, entrada 1 = {PASSTHROUGH})")
    elif ni == 2:
        cambios.append(f"{MERGE}: numberInputs ya es 2 (idempotente)")
    else:
        sys.exit(f"ERROR: {MERGE}.numberInputs inesperado: {ni!r}")

    # ---- conexiones de la cadena nueva ----
    conns[N_PREPARAR] = {"main": [[C(N_HAY)]]}
    conns[N_HAY] = {"main": [[C(N_SUBIR)], [C(N_MARCAR)]]}
    conns[N_SUBIR] = {"main": [[C(N_SUBIDA_OK)]]}
    conns[N_SUBIDA_OK] = {"main": [[C(N_REGISTRAR)], [C(N_MARCAR)]]}
    conns[N_REGISTRAR] = {"main": [[C(N_MARCAR)]]}
    conns[N_MARCAR] = {"main": [[C(MERGE, 0)]]}
    cambios.append("CONEXIONES de la cadena Media escritas (6 nodos)")
    return new, cambios, {"host": host, "fuentes_host": fuentes_host, "y0": y0}

# ---------------- diff / verificación ----------------
def diff_conns(a, b, keys):
    def f(c): return json.dumps({k: c.get(k) for k in keys if k in c}, ensure_ascii=False, indent=1, sort_keys=True).splitlines()
    return list(difflib.unified_diff(f(a), f(b), fromfile="ANTES", tofile="DESPUES", lineterm=""))

def fuera_de_alcance(wf, new):
    """Nodos/conexiones que cambiaron y NO son de la rama multimedia (debe dar vacío)."""
    a = {n["name"]: n for n in wf["nodes"]}; b = {n["name"]: n for n in new["nodes"]}
    nodos = [k for k in set(a) | set(b) if k not in NODOS_MEDIA and k != MERGE and a.get(k) != b.get(k)]
    ca, cb = wf["connections"], new["connections"]
    conexiones = [k for k in set(ca) | set(cb) if k not in AFECTADOS and ca.get(k) != cb.get(k)]
    return sorted(nodos), sorted(conexiones)

def verify(after):
    conns = after["connections"]; names = {n["name"]: n for n in after["nodes"]}
    det = {"faltan": [n for n in NODOS_MEDIA if n not in names]}
    det["set_markers"] = all(conn_list(conns, sm, 0) == [C(N_PREPARAR)] for sm in SET_MARKERS)
    det["passthrough"] = conn_list(conns, PASSTHROUGH, 0) == [C(MERGE, PASSTHROUGH_IDX_DESPUES)]
    det["marcar->merge0"] = conn_list(conns, N_MARCAR, 0) == [C(MERGE, 0)]
    det["merge_inputs_2"] = MERGE in names and names[MERGE]["parameters"].get("numberInputs") == 2
    det["merge_salidas_intactas"] = conn_list(conns, MERGE, 0) == [C("Buffer: Push Mensaje"), C("Buffer: Wait 10s")]
    det["webhookId"] = names.get(WEBHOOK, {}).get("webhookId") == "evo-webhook-v2"
    det["preparar_js_embebido"] = N_PREPARAR in names and names[N_PREPARAR]["parameters"].get("jsCode") == PREPARAR_JS
    ok = not det["faltan"] and all(v for k, v in det.items() if k != "faltan")
    return ok, det

def put(wf_body, label):
    body = {k: wf_body[k] for k in PUT_KEYS if k in wf_body}
    body["settings"] = clean_settings(wf_body)
    wh = next(n for n in body["nodes"] if n["name"] == WEBHOOK)
    assert wh.get("webhookId") == "evo-webhook-v2", "webhookId perdido — abortado"
    api(f"/workflows/{WF_ID}", method="PUT", payload=body)
    after = api(f"/workflows/{WF_ID}")
    ts = time.strftime("%Y%m%d_%H%M%S")
    post = ROOT / "workflows" / "history" / f"v6_POST_{label}_{ts}.json"
    post.write_text(json.dumps(after, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"POST backup -> {post}")
    return after

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="(default) mostrar cambios sin tocar n8n")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rollback-wiring", action="store_true")
    ap.add_argument("--rollback", metavar="BACKUP_PRE_JSON")
    args = ap.parse_args()

    wf = api(f"/workflows/{WF_ID}")
    print(f"v6 vivo: {wf['name']} — {len(wf['nodes'])} nodos, activo={wf['active']}, updatedAt={wf.get('updatedAt')}, versionId={wf.get('versionId')}")
    hist = ROOT / "workflows" / "history"; hist.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    if args.rollback:
        bk = json.loads(Path(args.rollback).read_text(encoding="utf-8"))
        pre = hist / f"v6_PRE_rollback_total_{ts}.json"
        pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        after = put(bk, "rollback_total")
        print(f"rollback total OK: {len(after['nodes'])} nodos (PRE de este rollback -> {pre})")
        return

    if args.rollback_wiring:
        new = copy.deepcopy(wf); conns = new["connections"]; names = {n["name"]: n for n in new["nodes"]}
        for sm, idx in SET_MARKERS.items():
            conns[sm]["main"][0] = [C(MERGE, idx)]
        conns[PASSTHROUGH]["main"][0] = [C(MERGE, PASSTHROUGH_IDX_ANTES)]
        names[MERGE]["parameters"]["numberInputs"] = 5
        if N_MARCAR in conns: conns[N_MARCAR] = {"main": [[]]}
        pre = hist / f"v6_PRE_rollback_wiring_{LABEL}_{ts}.json"
        pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        after = put(new, f"rollback_wiring_{LABEL}")
        ok = all(conn_list(after["connections"], sm, 0) == [C(MERGE, idx)] for sm, idx in SET_MARKERS.items()) \
            and conn_list(after["connections"], PASSTHROUGH, 0) == [C(MERGE, PASSTHROUGH_IDX_ANTES)]
        print("rollback de cableado", "OK" if ok else "FALLÓ — revisar en la UI",
              ": Set Marker * -> Merge[0..3], Passthrough -> Merge[4], numberInputs 5 (nodos 'Media: ' huérfanos)")
        return

    new, cambios, info = build(wf)
    print(f"\nHost Supabase v3 para Storage: {info['host']}  (fuentes coincidentes: {[f for f, _ in info['fuentes_host']]})")
    print(f"Fila de los nodos nuevos: y={info['y0']} (x desde {next(n for n in new['nodes'] if n['name'] == N_PREPARAR)['position'][0]}, paso 288)")
    print("\nCAMBIOS:"); [print("  -", c) for c in cambios]
    print("\nNODOS NUEVOS (tipo / versión / credencial / onError / posición):")
    for n in new["nodes"]:
        if n["name"] in NODOS_MEDIA:
            cred = ", ".join(f"{k}={v['id']}:{v['name']}" for k, v in (n.get("credentials") or {}).items()) or "-"
            print(f"  - {n['name']:<24} {n['type'].split('.')[-1]:<12} v{n['typeVersion']:<4} cred[{cred}] onError={n.get('onError', '-')} pos={n['position']}")
    print("\nDIFF conexiones (Set Marker *, Set Passthrough Texto, Media: *):")
    for line in diff_conns(wf["connections"], new["connections"], AFECTADOS):
        print("  " + line)
    m0 = next(n for n in wf["nodes"] if n["name"] == MERGE)["parameters"]; m1 = next(n for n in new["nodes"] if n["name"] == MERGE)["parameters"]
    print(f"\n{MERGE}.parameters: {json.dumps(m0)} -> {json.dumps(m1)}   (salidas del Merge intactas: {conn_list(new['connections'], MERGE, 0) == conn_list(wf['connections'], MERGE, 0)})")
    nodos_fuera, conns_fuera = fuera_de_alcance(wf, new)
    print(f"\nFuera de la rama multimedia: {len(nodos_fuera)} nodos cambiados {nodos_fuera}, {len(conns_fuera)} conexiones cambiadas {conns_fuera}")
    wh = next(n for n in new["nodes"] if n["name"] == WEBHOOK)
    print(f"webhookId preservado: {wh.get('webhookId') == 'evo-webhook-v2'} ({wh.get('webhookId')})")
    print(f"settings que irían en el PUT: {clean_settings(new)} (se filtran: {sorted(set((new.get('settings') or {}).keys()) - SETTINGS_OK)})")
    print(f"Nodos: {len(wf['nodes'])} -> {len(new['nodes'])}")
    if nodos_fuera or conns_fuera:
        sys.exit("ERROR: el cambio tocaría algo fuera de la rama multimedia — abortado")

    if not args.apply:
        print("\n[DRY-RUN] no se tocó n8n. Antes de --apply: `python scripts/create_media_entrantes.py --apply` (bucket + tabla) "
              "y `node tests/test_media_nodos.js`. Para aplicar: --apply")
        return

    pre = hist / f"v6_PRE_{LABEL}_{ts}.json"
    pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    # además del PRE completo, el cableado previo exacto de la rama (R9) para auditoría rápida
    wiring = {k: wf["connections"].get(k) for k in AFECTADOS if k in wf["connections"]}
    wiring["__merge_parameters"] = m0
    (hist / f"v6_PRE_{LABEL}_wiring_{ts}.json").write_text(json.dumps(wiring, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PRE backup -> {pre}")
    after = put(new, LABEL)
    ok, det = verify(after)
    print("verificación post-PUT:", det)
    if not ok:
        sys.exit("ERROR: la verificación post-PUT falló — revisar en la UI (rollback: --rollback " + str(pre) + ")")
    print(f"✅ media_entrantes aplicado: {len(after['nodes'])} nodos, activo={after['active']}. Probar con una foto desde el "
          f"celular de Lucas y limpiar con scripts/limpiar_numero_demo.py (regla dura 9).")

if __name__ == "__main__":
    main()
