# -*- coding: utf-8 -*-
"""
apply_media_fromme.py — la MISMA cadena Media que ya guarda los adjuntos del paciente, pero para la rama STAFF
(`Es fromMe?`[0]: la doctora o la secretaria mandando una foto/audio/video/documento desde el celular o el WA Web
del consultorio). Hoy el panel muestra ahí el chip "Adjunto enviado desde el celular del consultorio" porque el
archivo se descarta; con este cambio se sube al bucket privado `pacientes-media`, se registra en `media_entrantes`
(from_me = true) y el content de la memoria termina en ' [MEDIA:<id>]', el mismo token que el panel ya resuelve.

Diseño y contrato: docs/media-entrantes-2026-09-06.md §8 · rama del paciente: apply_media_entrantes.py

QUÉ CAMBIA EN EL v6 (6 nodos nuevos "Media: * (staff)" + 1 conexión nueva + 1 nodo existente modificado):

  Es fromMe?[0] ─► Build fromMe AI memory ─► Postgres - Save fromMe ─► CW Search Contact ─► CW Extract Conv
                                                 (+ RETURNING id)      ─► CW Get Conversations ─► CW Pick Conv
                                                                       ─► CW Set Label humano   ← CALLA AL BOT
      └──────────────────────────────────────────────────────────────────────► Media: Preparar (staff)
             ─► Media: ¿Hay archivo? (staff)  [true] ─► Media: Subir a Storage (staff)
                    ─► Media: ¿Subida OK? (staff)  [true] ─► Media: Registrar (staff)
                           ─► Media: Actualizar memoria (staff)      (UPDATE del content ya escrito)
             las salidas [false] de los dos IF NO van a ningún lado: no hay nada que hacer.
  Es fromMe?[1] ─► Filtrar duplicados y basura   (rama del PACIENTE: NO se toca)

POR QUÉ LA CADENA MEDIA VA AL FINAL, DESPUÉS DEL LABEL (crítico, 2026-09-07): el label 'humano' de Chatwoot es el
ÚNICO mecanismo que calla al bot en la rama fromMe ("Verificar Label Humano", "Hay humano ahora?" y "Gate Humano
Final" lo leen; NO hay ningún nodo Redis ni SQL de humano en esta rama; NO existe ningún nodo "Check Humano
Reciente (DB)"). Si la subida quedara ANTES, una foto/video de 5 MB (o un Storage colgado: timeout 30 s) metería
hasta 30 s por delante del label, y el pipeline del paciente (Buffer 10-22 s + LLM + Delay Humano) termina en
~25-30 s: el bot podría escribir ENCIMA de la doctora — la clase de falla del incidente Mariela (2026-05-09).
Por eso la cadena entera de silenciamiento queda EXACTAMENTE como hoy (ni un nodo movido, ni una arista tocada)
y los 6 nodos nuevos cuelgan de la salida de "CW Set Label humano", que hoy no tiene ninguna.

Consecuencia aceptada (documentada en §8.3 R13): si "CW Extract Conv" o "CW Pick Conv" devuelven [] (el contacto
o la conversación no existen en Chatwoot), la cadena Media tampoco corre y el archivo no se archiva. La fila de
memoria y el intento de label son los de hoy: se prefiere no archivar un adjunto antes que demorar el silencio.

EL TOKEN LLEGA POR UN UPDATE, NO ARMANDO EL CONTENT: "Build fromMe AI memory" NO SE TOCA (su fila sigue siendo
byte a byte la de hoy, TAG y placeholder incluidos). Como el content se escribe ANTES de la subida, el token
' [MEDIA:<id>]' se agrega después con un UPDATE acotado a UNA fila — media/actualizar_memoria_staff.js.

EL ÚNICO NODO EXISTENTE MODIFICADO es "Postgres - Save fromMe", y solo su `query`: se le agrega ` RETURNING id`
para saber qué fila actualizar. Verificado en el v6 vivo: hoy ese nodo devuelve `{success: true}` y NINGÚN nodo
aguas abajo usa su `$json` ("CW Search Contact" pasa `$('Edit Fields - Extraer Datos').first().json.phone` en la
query; "CW Extract Conv" lee la respuesta HTTP de la búsqueda) ni hay una sola referencia `$('Postgres - Save
fromMe')` en los 153 nodos. Con RETURNING devuelve `{id: "<bigint como string>"}` — un item, igual que hoy. El
UPDATE igual tiene fallback por session_id + content exacto si el id no llegara.

Los 5 primeros nodos nuevos son COPIAS EXACTAS de los vivos de la rama del paciente (mismo typeVersion, mismos
parámetros, mismas credenciales, mismo onError, mismo timeout 30 s) salvo el nombre con sufijo ' (staff)', el id,
la posición y UNA desviación deliberada: las referencias `$('Media: Preparar')` de "Media: Registrar" pasan a
`$('Media: Preparar (staff)')` (si se copiaran literales, la fila del staff se escribiría con los datos del nodo
del paciente, que en esa ejecución ni ejecutó). Los guards de JID (grupo/estado/difusión/canal/LID) que la rama fromMe no tiene
(vive en "Filtrar duplicados y basura", colgado de `Es fromMe?`[1]) ya NO va en la IF: vive en media/preparar.js,
que comparten las dos ramas (no-op para el paciente, que ya viene filtrado aguas arriba).

SECRETOS: ninguno en este archivo. El host `https://<ref>.supabase.co` y las credenciales se copian EN CALIENTE de
los nodos vivos "Media: Subir a Storage" y "Media: Registrar" (la fuente más fiel: ya están en producción), con
fallback a `resolver_host_v3()` / los ids conocidos de scripts/apply_media_entrantes.py.

REGLAS DURAS que cumple: GET fresco, asserts del cableado esperado (aborta si no es el conocido ni el ya aplicado),
backup PRE/POST con timestamp, PUT solo con name/nodes/connections/settings/staticData y settings filtradas,
assert webhookId 'evo-webhook-v2', idempotente, verificación post-PUT y chequeo de que NADA fuera de la rama fromMe
cambió (la rama del paciente y su cadena Media cuentan como "fuera"; el único nodo existente que puede cambiar es
"Postgres - Save fromMe", y solo por el RETURNING id, que el chequeo declara y compara byte a byte).

USO:
  python scripts/apply_media_fromme.py [--dry-run]     # default: nodos nuevos + diff de conexiones, no toca n8n
  python scripts/apply_media_fromme.py --apply         # backup PRE -> PUT -> backup POST -> verificación GET
  python scripts/apply_media_fromme.py --rollback-wiring   # CW Set Label humano vuelve a ser hoja + query sin
                                                           # RETURNING (los 6 nodos quedan huérfanos)
  python scripts/apply_media_fromme.py --rollback <workflows/history/v6_PRE_media_fromme_*.json>   # PUT del backup
"""
import argparse, copy, difflib, json, os, sys, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apply_media_entrantes import (  # noqa: E402  (misma fuente de verdad que la rama del paciente)
    api, clean_settings, conn_list, C, diff_conns, host_de_url, if_bool, resolver_host_v3,
    PUT_KEYS, SETTINGS_OK, SUPABASE_CRED_ID, PG_CRED_ID, WF_ID, BUCKET, TABLA, PREPARAR_JS, SUBIDA_OK_EXPR,
    N_PREPARAR, N_HAY, N_SUBIR, N_SUBIDA_OK, N_REGISTRAR, WEBHOOK, EXTRAER,
)

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
LABEL = "media_fromme"

# ---------------- fuentes únicas (los mismos archivos que corre tests/test_media_fromme.js) ----------------
ACTUALIZAR_EXPR = (ROOT / "media" / "actualizar_memoria_staff.js").read_text(encoding="utf-8").strip()

SUF = " (staff)"
S_PREPARAR, S_HAY, S_SUBIR, S_SUBIDA_OK, S_REGISTRAR = (n + SUF for n in (N_PREPARAR, N_HAY, N_SUBIR, N_SUBIDA_OK, N_REGISTRAR))
S_ACTUALIZAR = "Media: Actualizar memoria" + SUF
CLONES_STAFF = [S_PREPARAR, S_HAY, S_SUBIR, S_SUBIDA_OK, S_REGISTRAR]      # copias exactas del paciente
NODOS_STAFF = CLONES_STAFF + [S_ACTUALIZAR]                                # + el nodo nuevo de verdad
IDS_STAFF = {S_PREPARAR: "media-preparar-staff", S_HAY: "media-hay-archivo-staff", S_SUBIR: "media-subir-staff",
             S_SUBIDA_OK: "media-subida-ok-staff", S_REGISTRAR: "media-registrar-staff",
             S_ACTUALIZAR: "media-actualizar-memoria-staff"}

FROMME_IF, FROMME_MEM, FROMME_PG = "Es fromMe?", "Build fromMe AI memory", "Postgres - Save fromMe"
# Cadena de Chatwoot que pone el label 'humano' (lo único que calla al bot en esta rama). NO se toca NADA de
# ella: el último nodo, que hoy no tiene salida, pasa a arrastrar la cadena Media.
CW_CADENA = ["CW Search Contact", "CW Extract Conv", "CW Get Conversations", "CW Pick Conv", "CW Set Label humano"]
CW_ULTIMO = CW_CADENA[-1]

# `query` de "Postgres - Save fromMe": lo de hoy y lo único que se le agrega.
PG_QUERY_PREVIA = "INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)"
PG_QUERY_NUEVA = PG_QUERY_PREVIA + " RETURNING id"

# claves de `connections` que este script puede tocar; TODO lo demás (rama paciente + su cadena Media +
# TODA la cadena de silenciamiento) es "fuera" y aborta el script
AFECTADOS = [CW_ULTIMO] + NODOS_STAFF
# nodos que este script puede agregar/modificar (FROMME_PG solo por el RETURNING, ver assert_solo_returning)
TOCABLES = NODOS_STAFF + [FROMME_PG]

HAY_EXPR = "={{ $json.hay_archivo === true }}"          # la del nodo VIVO del paciente (lo que se clona)
SUBIDA_OK_FULL = "={{ " + SUBIDA_OK_EXPR + " }}"
ACTUALIZAR_FULL = "={{ " + ACTUALIZAR_EXPR + " }}"
REF_PRE, REF_PRE_STAFF = "$('" + N_PREPARAR + "')", "$('" + S_PREPARAR + "')"


# ---------------- helpers ----------------
def expr_de_if(nodo):
    try:
        return nodo["parameters"]["conditions"]["conditions"][0]["leftValue"]
    except (KeyError, IndexError, TypeError):
        return None


def reemplazar_pre(nodo):
    """Las referencias `$('Media: Preparar')` del clon pasan a `$('Media: Preparar (staff)')`. Devuelve (nodo, n)."""
    crudo = json.dumps(nodo, ensure_ascii=False)
    n = crudo.count(REF_PRE)
    return json.loads(crudo.replace(REF_PRE, REF_PRE_STAFF)), n


def preparar_vivo_vs_archivo(vivo_js):
    """El nodo VIVO del paciente todavía corre media/preparar.js SIN los guards de JID (ese bloque se agregó
    el 7/9 y su PUT es el de la rama del paciente, aparte). El clon del staff SÍ tiene que llevar el archivo
    del repo: es la única defensa de esta rama contra los JID que no son un chat 1:1 — grupo (@g.us),
    estado/lista de difusión (@broadcast), canal (@newsletter) y LID (@lid) — o sea, R1.

    Para poder hacer esa desviación sin volar a ciegas, se exige que el jsCode vivo sea el archivo del repo
    MENOS líneas agregadas: solo opcodes 'equal'/'insert' (nada borrado ni reemplazado) y entre lo insertado
    tienen que estar LOS DOS guards: el motivo 'grupo_o_estado' (blacklist, las dos ramas) y el whitelist del
    staff (`ED.fromMe` + '@s.whatsapp.net'), que es el que cierra la familia entera. Si alguien editó el nodo
    vivo a mano, aparece un 'delete' o un 'replace' y el script aborta. Devuelve (estado, líneas_agregadas)."""
    if vivo_js == PREPARAR_JS:
        return "igual", 0
    a, b = vivo_js.splitlines(keepends=True), PREPARAR_JS.splitlines(keepends=True)
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    agregadas = sum(o[4] - o[3] for o in ops if o[0] == "insert")
    insertado = "".join("".join(b[o[3]:o[4]]) for o in ops if o[0] == "insert")
    guards = ("grupo_o_estado" in insertado
              and "ED.fromMe" in insertado and "@s.whatsapp.net" in insertado)
    if all(o[0] == "insert" for o in ops) and guards:
        return "superset", agregadas
    return "distinto", agregadas


def clonar(vivo, nombre, nid, pos):
    n = copy.deepcopy(vivo)
    n["name"], n["id"], n["position"] = nombre, nid, pos
    n.pop("webhookId", None)
    for c in ((n.get("parameters") or {}).get("conditions") or {}).get("conditions", []) or []:
        c["id"] = nid + "-c"          # id interno de la condición: propio, para no duplicar el del original
    return n


def nodo_actualizar(pg_cred, pos):
    """El único nodo NUEVO de verdad: UPDATE acotado que agrega ' [MEDIA:<id>]' a la fila ya escrita."""
    return {"id": IDS_STAFF[S_ACTUALIZAR], "name": S_ACTUALIZAR, "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5, "position": pos,
            "parameters": {"operation": "executeQuery", "query": ACTUALIZAR_FULL, "options": {}},
            "credentials": {"postgres": pg_cred}, "onError": "continueRegularOutput"}


def desde_cero(host, sb_cred, pg_cred, P):
    """Fallback si la cadena Media del paciente no estuviera viva: mismo patrón que apply_media_entrantes.build()."""
    PRE = REF_PRE_STAFF + ".first().json"
    return [
        {"id": IDS_STAFF[S_PREPARAR], "name": S_PREPARAR, "type": "n8n-nodes-base.code", "typeVersion": 2,
         "position": P(0), "parameters": {"jsCode": PREPARAR_JS}, "onError": "continueRegularOutput"},
        if_bool(IDS_STAFF[S_HAY], S_HAY, P(1), HAY_EXPR),
        {"id": IDS_STAFF[S_SUBIR], "name": S_SUBIR, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
         "position": P(2),
         "parameters": {"method": "POST", "url": "=" + host + "/storage/v1/object/" + BUCKET + "/{{ $json.path }}",
                        "authentication": "predefinedCredentialType", "nodeCredentialType": "supabaseApi",
                        "sendHeaders": True,
                        "headerParameters": {"parameters": [{"name": "Content-Type", "value": "={{ $json.mime }}"},
                                                            {"name": "x-upsert", "value": "true"},
                                                            {"name": "cache-control", "value": "max-age=3600"}]},
                        "sendBody": True, "contentType": "binaryData", "inputDataFieldName": "data",
                        "options": {"response": {"response": {"neverError": True, "fullResponse": True}}, "timeout": 30000}},
         "credentials": {"supabaseApi": sb_cred}, "onError": "continueRegularOutput"},
        if_bool(IDS_STAFF[S_SUBIDA_OK], S_SUBIDA_OK, P(3), SUBIDA_OK_FULL),
        {"id": IDS_STAFF[S_REGISTRAR], "name": S_REGISTRAR, "type": "n8n-nodes-base.postgres", "typeVersion": 2.5,
         "position": P(4),
         "parameters": {"schema": {"__rl": True, "value": "public", "mode": "list"},
                        "table": {"__rl": True, "value": TABLA, "mode": "list"},
                        "columns": {"mappingMode": "defineBelow", "value": {
                            "id": "={{ " + PRE + ".id }}", "key_id": "={{ " + PRE + ".key_id || null }}",
                            "telefono": "={{ " + PRE + ".telefono }}", "from_me": "={{ !!" + PRE + ".from_me }}",
                            "tipo": "={{ " + PRE + ".tipo }}", "mime": "={{ " + PRE + ".mime || null }}",
                            "bucket": BUCKET, "path": "={{ " + PRE + ".path }}", "bytes": "={{ " + PRE + ".bytes }}",
                            "filename": "={{ " + PRE + ".filename || null }}", "caption": "={{ " + PRE + ".caption || null }}"}},
                        "options": {}},
         "credentials": {"postgres": pg_cred}, "onError": "continueRegularOutput"},
    ]


def fila_libre(nodes, xs, y_ini):
    """Primera y >= y_ini donde ninguno de los xs choca con un nodo existente (margen 200 x 130)."""
    otros = [n for n in nodes if n["name"] not in NODOS_STAFF]
    y = y_ini
    for _ in range(20):
        if not any(abs(n["position"][0] - x) < 200 and abs(n["position"][1] - y) < 130 for n in otros for x in xs):
            return y
        y += 210
    sys.exit("ERROR: no encontré una fila libre en el canvas para la cadena staff")


# ---------------- build ----------------
def build(wf):
    new = copy.deepcopy(wf)
    nodes, conns = new["nodes"], new["connections"]
    names = {n["name"]: n for n in nodes}
    cambios, notas = [], []

    for req in [FROMME_IF, FROMME_MEM, FROMME_PG, WEBHOOK, EXTRAER] + CW_CADENA:
        if req not in names:
            sys.exit(f"ERROR: falta el nodo {req!r} en el v6")
    # ---- la cadena de silenciamiento tiene que estar EXACTAMENTE como se probó (no se toca ninguna arista) ----
    if conn_list(conns, FROMME_IF, 0) != [C(FROMME_MEM)]:
        sys.exit(f"ERROR: {FROMME_IF}[0] inesperado: {conn_list(conns, FROMME_IF, 0)!r} (esperaba [{FROMME_MEM}])")
    if conn_list(conns, FROMME_IF, 1) != [C("Filtrar duplicados y basura")]:
        sys.exit(f"ERROR: {FROMME_IF}[1] (rama del paciente) inesperado: {conn_list(conns, FROMME_IF, 1)!r}")
    if conn_list(conns, FROMME_MEM, 0) != [C(FROMME_PG)]:
        sys.exit(f"ERROR: {FROMME_MEM}[0] inesperado: {conn_list(conns, FROMME_MEM, 0)!r}")
    if conn_list(conns, FROMME_PG, 0) != [C(CW_CADENA[0])]:
        sys.exit(f"ERROR: {FROMME_PG}[0] inesperado: {conn_list(conns, FROMME_PG, 0)!r} (esperaba [{CW_CADENA[0]}])")
    for a, b in zip(CW_CADENA, CW_CADENA[1:]):
        if conn_list(conns, a, 0) != [C(b)]:
            sys.exit(f"ERROR: la cadena de Chatwoot no es la conocida: {a!r}[0] = {conn_list(conns, a, 0)!r} (esperaba {b!r})")

    # ---- host y credenciales: de los nodos vivos de la cadena del paciente (fuente más fiel), con fallback ----
    vivos = {n: names.get(n) for n in (N_PREPARAR, N_HAY, N_SUBIR, N_SUBIDA_OK, N_REGISTRAR)}
    clonar_de_vivos = all(vivos.values())
    host = host_de_url((vivos[N_SUBIR] or {}).get("parameters", {}).get("url")) if clonar_de_vivos else None
    fuente_host = f"nodo vivo {N_SUBIR!r}"
    if not host:
        host, fuentes = resolver_host_v3(names)
        fuente_host = "fallback resolver_host_v3: " + ", ".join(f for f, _ in fuentes)
    sb_cred = copy.deepcopy(((vivos[N_SUBIR] or {}).get("credentials") or {}).get("supabaseApi")) if clonar_de_vivos else None
    if not sb_cred:
        sb_node = names.get("obtener_historial_paciente") or names.get("consultar_recordatorios_abiertos") or {}
        sb_cred = copy.deepcopy((sb_node.get("credentials") or {}).get("supabaseApi"))
    if not sb_cred or sb_cred.get("id") != SUPABASE_CRED_ID:
        sys.exit(f"ERROR: credencial supabaseApi inesperada: {sb_cred!r} (esperaba id {SUPABASE_CRED_ID})")
    pg_cred = copy.deepcopy(((vivos[N_REGISTRAR] or {}).get("credentials") or {}).get("postgres")) if clonar_de_vivos else None
    if not pg_cred:
        pg_cred = copy.deepcopy((names.get(FROMME_PG, {}).get("credentials") or {}).get("postgres"))
    if not pg_cred or pg_cred.get("id") != PG_CRED_ID:
        sys.exit(f"ERROR: credencial postgres inesperada: {pg_cred!r} (esperaba id {PG_CRED_ID})")

    # ---- posiciones: fila propia libre, a la derecha del último nodo de la cadena de Chatwoot ----
    # Acá el orden de ejecución NO depende de la posición (hay una sola rama y es serial): las posiciones
    # son cosméticas, solo tienen que no pisar nada.
    # La separación con la cadena Media del PACIENTE es de 3 filas (630 px) y no de una: las dos cadenas
    # comparten el prefijo "Media: " y columnas x, y pegadas una debajo de la otra es fácil confundirlas
    # al leer una ejecución en el canvas. No afecta la ejecución (rama serial única), solo la lectura.
    cw = names[CW_ULTIMO]["position"]
    y_base = max((vivos[N_PREPARAR]["position"][1] if clonar_de_vivos else 1150) + 630, cw[1] + 420)
    x0 = cw[0] + 288
    xs = [x0 + i * 288 for i in range(6)]
    y = fila_libre(nodes, xs, y_base)
    P = lambda col: [xs[col], y]

    # ---- los 5 clones ----
    if clonar_de_vivos:
        nuevos = [clonar(vivos[orig], nombre, IDS_STAFF[nombre], P(i))
                  for i, (orig, nombre) in enumerate(zip((N_PREPARAR, N_HAY, N_SUBIR, N_SUBIDA_OK, N_REGISTRAR), CLONES_STAFF))]
        nuevos[4], refs = reemplazar_pre(nuevos[4])
        if refs == 0:
            sys.exit(f"ERROR: {N_REGISTRAR!r} no referencia {REF_PRE} — el clon quedaría apuntando a otro nodo")
        notas.append(f"clonados de los nodos vivos de la rama del paciente; {refs} referencias {REF_PRE} -> {REF_PRE_STAFF} en {S_REGISTRAR!r}")
    else:
        nuevos = desde_cero(host, sb_cred, pg_cred, P)
        notas.append("la cadena Media del paciente NO está viva: nodos construidos con el patrón de apply_media_entrantes.py")

    # ---- asserts de fidelidad (que el clon sea el nodo probado, no otro) ----
    prep, hay, subir, ok, reg = nuevos
    fallas = []
    if prep["type"] != "n8n-nodes-base.code" or prep["typeVersion"] != 2 or prep.get("onError") != "continueRegularOutput":
        fallas.append(f"{S_PREPARAR}: tipo/versión/onError inesperados")
    estado_js, agregadas = preparar_vivo_vs_archivo(prep["parameters"].get("jsCode") or "")
    if estado_js == "distinto":
        fallas.append(f"{S_PREPARAR}: el jsCode vivo de {N_PREPARAR!r} NO es media/preparar.js ni una versión "
                      f"anterior de ese archivo (hay líneas borradas o cambiadas, no solo agregadas). "
                      f"Alguien lo editó en la UI: revisar el diff antes de seguir.")
    else:
        # Desviación deliberada: el clon lleva el archivo del repo, no el jsCode vivo.
        prep["parameters"]["jsCode"] = PREPARAR_JS
    if expr_de_if(hay) != HAY_EXPR:
        fallas.append(f"{S_HAY}: expresión inesperada {expr_de_if(hay)!r} (esperaba la del paciente, {HAY_EXPR!r})")
    if expr_de_if(ok) != SUBIDA_OK_FULL:
        fallas.append(f"{S_SUBIDA_OK}: la expresión viva NO coincide con media/subida_ok_expr.js")
    if subir["typeVersion"] != 4.2 or subir.get("onError") != "continueRegularOutput" \
            or subir["parameters"].get("options", {}).get("timeout") != 30000 \
            or not str(subir["parameters"].get("url", "")).startswith("=" + host + "/storage/v1/object/" + BUCKET + "/"):
        fallas.append(f"{S_SUBIR}: url/timeout/onError inesperados")
    if (subir.get("credentials") or {}).get("supabaseApi", {}).get("id") != SUPABASE_CRED_ID:
        fallas.append(f"{S_SUBIR}: credencial supabaseApi inesperada")
    if reg["typeVersion"] != 2.5 or reg.get("onError") != "continueRegularOutput" \
            or (reg["parameters"].get("table") or {}).get("value") != TABLA \
            or (reg.get("credentials") or {}).get("postgres", {}).get("id") != PG_CRED_ID:
        fallas.append(f"{S_REGISTRAR}: tabla/credencial/onError inesperados")
    crudo_reg = json.dumps(reg, ensure_ascii=False)
    if REF_PRE + "." in crudo_reg or crudo_reg.count(REF_PRE_STAFF) < 10:
        fallas.append(f"{S_REGISTRAR}: quedaron referencias al {N_PREPARAR!r} del paciente o faltan las del staff")
    # la expresión del UPDATE va DENTRO de ={{ … }}: unas llaves dobles la cerrarían antes de tiempo
    if "}}" in ACTUALIZAR_EXPR or "{{" in ACTUALIZAR_EXPR:
        fallas.append("media/actualizar_memoria_staff.js tiene llaves dobles: rompería la expresión de n8n")
    if fallas:
        sys.exit("ERROR de fidelidad del clon:\n  - " + "\n  - ".join(fallas))

    if estado_js == "superset":
        notas.append(f"{S_PREPARAR}: jsCode = media/preparar.js del repo ({len(PREPARAR_JS)} ch), NO el del nodo "
                     f"vivo del paciente ({len(vivos[N_PREPARAR]['parameters']['jsCode'])} ch). El archivo tiene "
                     f"{agregadas} líneas más — SOLO agregadas — que son los guards de JID (motivo "
                     f"'grupo_o_estado'): blacklist @g.us/@broadcast/@newsletter + whitelist del staff "
                     f"(fromMe exige un Info.Chat '@s.whatsapp.net', lo que cierra también @lid y cualquier "
                     f"familia futura) + largo 8-15 dígitos. Es la única defensa de esta rama (R1) y en la del "
                     f"paciente es no-op. El nodo del paciente NO se toca acá; queda para un PUT aparte de "
                     f"apply_media_entrantes.py, con su propio OK.")

    nuevos.append(nodo_actualizar(pg_cred, P(5)))
    notas.append(f"{S_ACTUALIZAR}: postgres 2.5 executeQuery, query = media/actualizar_memoria_staff.js "
                 f"({len(ACTUALIZAR_EXPR)} ch), sin queryReplacement (escapa los valores adentro), "
                 f"onError=continueRegularOutput")

    # ---- idempotencia: si ya existen, se reemplazan conservando id/posición ----
    for n in nuevos:
        if n["name"] in names:
            prev = names[n["name"]]
            n["position"] = prev.get("position", n["position"])
            n["id"] = prev.get("id", n["id"])
            nodes[nodes.index(prev)] = n
            cambios.append(f"ACTUALIZA {n['name']!r}" + (" (sin cambios)" if prev == n else ""))
        else:
            nodes.append(n)
            cred = list((n.get("credentials") or {}).values())
            cambios.append(f"AGREGA {n['name']!r} ({n['type'].split('.')[-1]} v{n['typeVersion']}"
                           + (f", cred {cred[0]['name']!r}" if cred else "")
                           + (f", onError={n['onError']}" if n.get("onError") else "") + ")")
        names[n["name"]] = n

    # ---- único nodo existente modificado: "Postgres - Save fromMe" gana ` RETURNING id` ----
    pg = names[FROMME_PG]
    actual = pg["parameters"].get("query")
    if actual == PG_QUERY_NUEVA:
        cambios.append(f"{FROMME_PG}: la query ya tiene RETURNING id (idempotente)")
    elif actual == PG_QUERY_PREVIA:
        pg["parameters"]["query"] = PG_QUERY_NUEVA
        cambios.append(f"{FROMME_PG}: query + ' RETURNING id' (mismo nodo, mismo queryReplacement, misma credencial)")
    else:
        sys.exit(f"ERROR: la query viva de {FROMME_PG!r} no es la conocida:\n  vive:    {actual!r}\n  esperaba: {PG_QUERY_PREVIA!r}")

    # ---- conexiones nuevas ----
    # "CW Set Label humano" hoy no tiene salida (no está en `connections`): pasa a arrastrar la cadena Media.
    act = conn_list(conns, CW_ULTIMO, 0)
    if act in (None, []):
        conns[CW_ULTIMO] = {"main": [[C(S_PREPARAR)]]}
        cambios.append(f"CONECTA {CW_ULTIMO}[0] -> {S_PREPARAR} (antes: hoja, sin salida)")
    elif act == [C(S_PREPARAR)]:
        cambios.append(f"{CW_ULTIMO}[0] ya apunta a {S_PREPARAR} (idempotente)")
    else:
        sys.exit(f"ERROR: {CW_ULTIMO}[0] inesperado: {act!r} (esperaba ninguna salida)")

    # Las salidas [false] de los dos IF quedan VACÍAS a propósito: no hay nada que hacer con un mensaje sin
    # archivo o con una subida fallida (la fila de memoria y el label ya se escribieron aguas arriba).
    conns[S_PREPARAR] = {"main": [[C(S_HAY)]]}
    conns[S_HAY] = {"main": [[C(S_SUBIR)], []]}
    conns[S_SUBIR] = {"main": [[C(S_SUBIDA_OK)]]}
    conns[S_SUBIDA_OK] = {"main": [[C(S_REGISTRAR)], []]}
    conns[S_REGISTRAR] = {"main": [[C(S_ACTUALIZAR)]]}
    conns.pop(S_ACTUALIZAR, None)          # hoja: n8n representa "sin salida" como ausencia de la clave
    cambios.append("CONEXIONES de la cadena Media (staff) escritas (6 nodos, las 2 salidas [false] vacías)")
    return new, cambios, {"host": host, "fuente_host": fuente_host, "y": y, "xs": xs, "notas": notas}


# ---------------- diff / verificación ----------------
def assert_solo_returning(wf, new):
    """El ÚNICO nodo existente que se puede modificar es "Postgres - Save fromMe", y SOLO su query, y solo
    agregándole ' RETURNING id'. Cualquier otra diferencia (credencial, queryReplacement, typeVersion,
    posición) aborta."""
    a = next((n for n in wf["nodes"] if n["name"] == FROMME_PG), None)
    b = next((n for n in new["nodes"] if n["name"] == FROMME_PG), None)
    if a is None or b is None:
        sys.exit(f"ERROR: falta {FROMME_PG!r} antes o después del cambio")
    qa, qb = copy.deepcopy(a), copy.deepcopy(b)
    qa["parameters"] = {k: v for k, v in qa["parameters"].items() if k != "query"}
    qb["parameters"] = {k: v for k, v in qb["parameters"].items() if k != "query"}
    if qa != qb:
        sys.exit(f"ERROR: {FROMME_PG!r} cambió en algo que NO es la query — abortado")
    if a["parameters"].get("query") not in (PG_QUERY_PREVIA, PG_QUERY_NUEVA) or b["parameters"].get("query") != PG_QUERY_NUEVA:
        sys.exit(f"ERROR: la query de {FROMME_PG!r} no es la esperada — abortado")
    return a["parameters"].get("query"), b["parameters"].get("query")


def fuera_de_alcance(wf, new):
    """Nodos/conexiones que cambiaron y NO son de la rama fromMe. La rama del PACIENTE y su cadena Media
    cuentan como 'fuera', igual que la cadena de silenciamiento (Es fromMe? / Build fromMe / los 5 CW):
    si aparecen acá, el script aborta. "Postgres - Save fromMe" es la única excepción declarada y su
    diferencia se compara aparte en assert_solo_returning()."""
    a = {n["name"]: n for n in wf["nodes"]}
    b = {n["name"]: n for n in new["nodes"]}
    nodos = [k for k in set(a) | set(b) if k not in TOCABLES and a.get(k) != b.get(k)]
    ca, cb = wf["connections"], new["connections"]
    conexiones = [k for k in set(ca) | set(cb) if k not in AFECTADOS and ca.get(k) != cb.get(k)]
    return sorted(nodos), sorted(conexiones)


def verify_post_put(wf, after):
    """Cierra el círculo DESPUÉS del PUT (regla dura 5: defensa en profundidad). Hasta acá la garantía de
    "no se tocó nada más" venía de comparar el body que MANDAMOS (fuera_de_alcance(wf, new)) — o sea,
    dependía de que n8n devolviera los nodos verbatim. Esto lo verifica contra lo que n8n REALMENTE guardó:

      1. el mismo fuera_de_alcance, ahora contra `after` (0 nodos y 0 conexiones fuera de la rama fromMe);
      2. comparación BYTE A BYTE de los nodos que este cambio promete no tocar y que además son los que
         callan al bot: "Build fromMe AI memory" y los 5 nodos CW de la cadena de silenciamiento.

    Devuelve (ok, detalle). Si falla, main() aborta y sugiere el rollback."""
    nodos_fuera, conns_fuera = fuera_de_alcance(wf, after)
    a = {n["name"]: n for n in wf["nodes"]}
    b = {n["name"]: n for n in after["nodes"]}
    distintos = [n for n in [FROMME_MEM] + CW_CADENA if a.get(n) != b.get(n)]
    det = {"nodos_fuera": nodos_fuera, "conexiones_fuera": conns_fuera,
           "silenciamiento_byte_a_byte": not distintos, "nodos_distintos": distintos}
    return (not nodos_fuera and not conns_fuera and not distintos), det


def verify(after):
    conns, names = after["connections"], {n["name"]: n for n in after["nodes"]}
    det = {"faltan": [n for n in NODOS_STAFF if n not in names]}
    # 1) el silenciamiento quedó EXACTAMENTE como estaba
    det["silenciamiento_intacto"] = (conn_list(conns, FROMME_IF, 0) == [C(FROMME_MEM)]
                                     and conn_list(conns, FROMME_MEM, 0) == [C(FROMME_PG)]
                                     and conn_list(conns, FROMME_PG, 0) == [C(CW_CADENA[0])]
                                     and all(conn_list(conns, a, 0) == [C(b)] for a, b in zip(CW_CADENA, CW_CADENA[1:])))
    det["fromme_if[1]_paciente_intacto"] = conn_list(conns, FROMME_IF, 1) == [C("Filtrar duplicados y basura")]
    # 2) la cadena Media del staff cuelga DESPUÉS del label y en el orden correcto
    det["label->preparar_staff"] = conn_list(conns, CW_ULTIMO, 0) == [C(S_PREPARAR)]
    det["cadena_staff"] = (conn_list(conns, S_PREPARAR, 0) == [C(S_HAY)]
                           and conn_list(conns, S_HAY, 0) == [C(S_SUBIR)] and conn_list(conns, S_HAY, 1) == []
                           and conn_list(conns, S_SUBIR, 0) == [C(S_SUBIDA_OK)]
                           and conn_list(conns, S_SUBIDA_OK, 0) == [C(S_REGISTRAR)] and conn_list(conns, S_SUBIDA_OK, 1) == []
                           and conn_list(conns, S_REGISTRAR, 0) == [C(S_ACTUALIZAR)]
                           and conn_list(conns, S_ACTUALIZAR, 0) in (None, []))
    # 3) contenido de los nodos
    det["save_fromme_returning"] = names.get(FROMME_PG, {}).get("parameters", {}).get("query") == PG_QUERY_NUEVA
    det["build_fromme_presente"] = FROMME_MEM in names  # el contenido se compara byte a byte en verify_post_put()
    det["preparar_staff_js"] = names.get(S_PREPARAR, {}).get("parameters", {}).get("jsCode") == PREPARAR_JS
    det["hay_archivo_staff_igual_paciente"] = expr_de_if(names.get(S_HAY, {})) == HAY_EXPR
    det["hay_archivo_paciente_intacto"] = N_HAY not in names or expr_de_if(names[N_HAY]) == HAY_EXPR
    det["actualizar_query"] = names.get(S_ACTUALIZAR, {}).get("parameters", {}).get("query") == ACTUALIZAR_FULL
    det["actualizar_onerror"] = names.get(S_ACTUALIZAR, {}).get("onError") == "continueRegularOutput"
    det["registrar_staff_ref"] = S_REGISTRAR in names and REF_PRE + "." not in json.dumps(names[S_REGISTRAR], ensure_ascii=False)
    # 4) la cadena del paciente tal cual (si no existiera, este script corrió por el camino de fallback)
    det["cadena_paciente_intacta"] = N_REGISTRAR not in names or conn_list(conns, N_REGISTRAR, 0) == [C("Media: Marcar")]
    det["webhookId"] = names.get(WEBHOOK, {}).get("webhookId") == "evo-webhook-v2"
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
    hist = ROOT / "workflows" / "history"
    hist.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    if args.rollback:
        bk = json.loads(Path(args.rollback).read_text(encoding="utf-8"))
        pre = hist / f"v6_PRE_rollback_total_{LABEL}_{ts}.json"
        pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        after = put(bk, f"rollback_total_{LABEL}")
        print(f"rollback total OK: {len(after['nodes'])} nodos (PRE de este rollback -> {pre})")
        return

    if args.rollback_wiring:
        new = copy.deepcopy(wf)
        conns, names = new["connections"], {n["name"]: n for n in new["nodes"]}
        conns.pop(CW_ULTIMO, None)                                   # vuelve a ser hoja
        if FROMME_PG in names:
            names[FROMME_PG]["parameters"]["query"] = PG_QUERY_PREVIA
        for n in NODOS_STAFF:
            if n in conns:
                conns[n] = {"main": [[] for _ in conns[n]["main"]]}
        pre = hist / f"v6_PRE_rollback_wiring_{LABEL}_{ts}.json"
        pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
        after = put(new, f"rollback_wiring_{LABEL}")
        an = {x["name"]: x for x in after["nodes"]}
        ok = (conn_list(after["connections"], CW_ULTIMO, 0) in (None, [])
              and an[FROMME_PG]["parameters"]["query"] == PG_QUERY_PREVIA)
        print("rollback de cableado", "OK" if ok else "FALLÓ — revisar en la UI",
              f": {CW_ULTIMO} vuelve a ser hoja y {FROMME_PG} vuelve a la query sin RETURNING "
              f"(los 6 nodos 'Media: * (staff)' quedan huérfanos). El silenciamiento no se tocó nunca.")
        return

    new, cambios, info = build(wf)
    q_antes, q_despues = assert_solo_returning(wf, new)
    print(f"\nHost Supabase v3 para Storage: {info['host']}  (fuente: {info['fuente_host']})")
    print(f"Fila de los nodos nuevos: y={info['y']} (x {info['xs'][0]} -> {info['xs'][-1]}, paso 288)")
    for n in info["notas"]:
        print(f"Nota: {n}")
    print("\nCAMBIOS:")
    for c in cambios:
        print("  -", c)
    print("\nNODOS NUEVOS (tipo / versión / credencial / onError / posición):")
    for n in new["nodes"]:
        if n["name"] in NODOS_STAFF:
            cred = ", ".join(f"{k}={v['id']}:{v['name']}" for k, v in (n.get("credentials") or {}).items()) or "-"
            print(f"  - {n['name']:<34} {n['type'].split('.')[-1]:<12} v{n['typeVersion']:<4} cred[{cred}] onError={n.get('onError', '-')} pos={n['position']}")
    print(f"\nNODO EXISTENTE MODIFICADO (1 y solo 1): {FROMME_PG!r} — postgres v2.5 executeQuery, misma credencial,")
    print(f"    mismo queryReplacement; SOLO cambia `query`:")
    print(f"      antes:   {q_antes}")
    print(f"      después: {q_despues}")
    print(f"    ({FROMME_MEM!r} NO se toca: la fila de memoria sigue siendo byte a byte la de hoy)")
    print("\nSILENCIAMIENTO (lo que calla al bot en esta rama = el label 'humano' de Chatwoot): NO SE TOCA.")
    print(f"  sigue: {FROMME_IF}[0] -> {FROMME_MEM} -> {FROMME_PG} -> " + " -> ".join(CW_CADENA))
    print(f"  nuevo: {CW_ULTIMO} -> {S_PREPARAR} -> {S_HAY} -[true]-> {S_SUBIR} -> {S_SUBIDA_OK} "
          f"-[true]-> {S_REGISTRAR} -> {S_ACTUALIZAR}")
    print(f"  la subida a Storage (timeout 30 s) queda DESPUÉS del label: no puede demorarlo ni un ms.")
    print("\nARISTAS que cambian (antes -> después). Todo lo que no está acá queda intacto:")
    for k in AFECTADOS:
        antes, despues = wf["connections"].get(k), new["connections"].get(k)
        if antes == despues:
            continue
        f = lambda c: ("(sin salida)" if c in (None, {}) else
                       " | ".join(f"[{i}]->" + (", ".join(x["node"] for x in (o or [])) or "(nada)")
                                  for i, o in enumerate(c.get("main", []))))
        print(f"  {k}:\n      antes:   {f(antes)}\n      después: {f(despues)}")
    print("\nDIFF conexiones, JSON crudo (CW Set Label humano + Media: * (staff)):")
    for line in diff_conns(wf["connections"], new["connections"], AFECTADOS):
        print("  " + line)
    nodos_fuera, conns_fuera = fuera_de_alcance(wf, new)
    print(f"\nFuera de la rama fromMe: {len(nodos_fuera)} nodos cambiados {nodos_fuera}, "
          f"{len(conns_fuera)} conexiones cambiadas {conns_fuera}")
    print(f"  (TOCABLES = {NODOS_STAFF + [FROMME_PG]}; todo lo demás — rama del paciente, su cadena Media y la "
          f"cadena de silenciamiento — cuenta como 'fuera' y aborta)")
    wh = next(n for n in new["nodes"] if n["name"] == WEBHOOK)
    print(f"webhookId preservado: {wh.get('webhookId') == 'evo-webhook-v2'} ({wh.get('webhookId')})")
    print(f"settings que irían en el PUT: {clean_settings(new)} (se filtran: {sorted(set((new.get('settings') or {}).keys()) - SETTINGS_OK)})")
    print(f"Nodos: {len(wf['nodes'])} -> {len(new['nodes'])}")
    if nodos_fuera or conns_fuera:
        sys.exit("ERROR: el cambio tocaría algo fuera de la rama fromMe — abortado")

    if not args.apply:
        print("\n[DRY-RUN] no se tocó n8n. Antes de --apply: `node tests/test_media_fromme.js` y "
              "`node tests/test_media_nodos.js` (la tabla y el bucket ya existen desde la rama del paciente). "
              "Para aplicar: --apply")
        return

    pre = hist / f"v6_PRE_{LABEL}_{ts}.json"
    pre.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")
    wiring = {k: wf["connections"].get(k) for k in AFECTADOS if k in wf["connections"]}
    wiring["__save_fromMe_query"] = q_antes
    (hist / f"v6_PRE_{LABEL}_wiring_{ts}.json").write_text(json.dumps(wiring, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PRE backup -> {pre}")
    after = put(new, LABEL)
    ok, det = verify(after)
    print("verificación post-PUT (estructura):", det)
    ok2, det2 = verify_post_put(wf, after)
    print("verificación post-PUT (nada fuera de alcance, contra lo que n8n guardó):", det2)
    if not ok or not ok2:
        sys.exit(f"ERROR: la verificación post-PUT falló — revisar en la UI (rollback: --rollback {pre})")
    print(f"✅ media_fromme aplicado: {len(after['nodes'])} nodos, activo={after['active']}.\n"
          f"   PRIMERA PRUEBA (obligatoria, doc §8.4 punto 5): con el bot encendido, el teléfono de prueba escribe algo "
          f"y ~5 s después la doctora contesta con una FOTO desde el celular del consultorio. En la ejecución de n8n, "
          f"'CW Set Label humano' tiene que correr ANTES de 'Media: Subir a Storage (staff)' (ahora es imposible que "
          f"no pase: está aguas arriba) y el bot NO debe contestar.\n"
          f"   Después: verificar la fila en media_entrantes y el ' [MEDIA:<id>]' en n8n_chat_histories (lo agrega "
          f"'Media: Actualizar memoria (staff)' unos segundos después del INSERT), y limpiar con "
          f"scripts/limpiar_numero_demo.py + borrar las filas/objetos de prueba (regla dura 9).")


if __name__ == "__main__":
    main()
