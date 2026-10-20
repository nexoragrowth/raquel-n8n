# -*- coding: utf-8 -*-
"""
apply_dia1_segmentacion.py — 2026-10-14 · PUT-B "Día 1" de la segmentación de contactos en el v6 (O155MqHgOSaNZ9ye).
Plan: docs/plan-contactos-conversion-dentalink-2026-10-13.md §2.2, §2.5, §2.6. Requiere la migración (scripts/apply_migracion_contacto_tipos.py).

QUÉ HACE: Asiri deja de contestarles a los contactos con tipo vigente interno / colega / proveedor / no_paciente (public.contacto_ruta).
'dudoso' no es un tipo (no se carga) y 'prueba' no silencia. Un teléfono SIN tipo recorre EXACTAMENTE el mismo grafo que hoy.

  ENTRADA (después del kill-switch /bot off|on|status, del buffer y de "Buffer: Limpiar"; antes del modo humano, del v7 y del triaje):
    Buffer: Limpiar → Seg: Consultar Tipo (Postgres, contacto_ruta, 1 fila, continueOnFail) → Seg: Redis GET off (seg:off, fail-open)
      → Seg: ¿Silenciar? ─[no]→ Consultar Takeover Paciente (… el v6 de hoy, sin cambios)
                         └[sí]→ Seg: Red de seguridad → Seg: ¿Avisar? ─[sí]→ Seg: Avisar al grupo   (FIN, no responde)
    Seg: Consultar Tipo también → Seg: ¿Falló la consulta? ─[sí]→ Seg: Redis GET falla → Seg: Aviso técnico → Seg: Redis SET falla   (FIN)
      (rama terminal ubicada DEBAJO en el lienzo: con executionOrder v1 corre después del camino normal; el bot ya respondió como hoy)
  SALIDA (por acá sale también el v7):
    Loop Mensajes[1] → Seg: Tipo Salida (Postgres, misma consulta) → Evolution - Typing → Gate Humano Final (bloque Seg al principio) → Enviar

  · Silencio por tipo = igual que el modo humano hoy: el entrante queda en el panel (Inbox Live corre antes del buffer), no va a memoria,
    no se responde. NO prende el modo humano ni toca human_takeover.
  · Red de seguridad: SOLO colega/proveedor/no_paciente (interno nunca) con señales FUERTES de urgencia = copia textual de esUrgenciaFuerte
    del 'Parse Intent' vivo (sin regex nuevas). Aviso al grupo por notify-grupo con el texto en body.text (el Helper no prende el modo
    humano). SIN tope: "una urgencia fuerte avisa siempre" (plan §2.5); el buffer y el Rate Limit del v6 ya acotan la ráfaga.
  · Aviso técnico (plan §2.5): si contacto_ruta da error, el grupo se entera (1 aviso cada 6 h, seg:falla con TTL fijo escrito DESPUÉS
    de un POST exitoso). El bot sigue respondiendo como hoy (falla abierta).
  · Interruptor: si la clave Redis "seg:off" existe (cualquier valor), todo se comporta como hoy, sin PUT. Ojo: NO es el "seg:on" del PUT-D
    (ese elige la ruta nueva de contacto_ruta en noviembre); seg:off es el freno del Día 1 y debe seguir respetándose en el PUT-D.
  · FALLA ABIERTA: consulta del tipo con error / sin fila / Redis caído → no silencia (el bot responde como hoy).
EDITA 1 nodo del v6: Gate Humano Final (bloque insertado después de la línea `const phone = …`, ancla única; el resto idéntico).

USO (Lucas corre lo que escribe; por defecto SOLO LEE):
  python scripts/apply_dia1_segmentacion.py                    # simulación: GET v6 + helper, prerrequisitos, diff, invariantes, pruebas offline
  python scripts/apply_dia1_segmentacion.py --ver-codigo       # ídem + el código de los nodos nuevos
  python scripts/apply_dia1_segmentacion.py --offline DIR      # ídem desde workflows/current/dia1_segmentacion/ (sin red)
  python scripts/apply_dia1_segmentacion.py --apply            # contacto_ruta existe → test de la migración (PGlite) → check_triaje → re-GET
                                                               # (mismo versionId) → grafo de check_triaje sobre el NUEVO → backup PRE → PUT
                                                               # → GET → backup POST → verificación → check_triaje otra vez (ya sobre el nuevo)
  python scripts/apply_dia1_segmentacion.py --revertir [--apply]   # QUITA lo del Día 1 (nodos Seg, 2 arcos, bloque del Gate) sobre un GET
                                                               # NUEVO; conserva cualquier otro cambio posterior. Mismas guardas que el --apply.
  python scripts/apply_dia1_segmentacion.py --seg-off|--seg-on|--seg-status   # imprime cómo tocar el interruptor (no escribe nada)
  python scripts/apply_dia1_segmentacion.py --e2e-on [--apply]  # marca el celular de Lucas como proveedor (prueba_e2e) para la prueba E2E
     cierre en el MISMO turno: python scripts/limpiar_numero_demo.py --phone <tel> --seg --borrar-logs --apply
Despliegue sugerido: migración → PUT con la tabla vacía (o seg:off=1) → T0 sin tipo (igual que hoy) → --e2e-on → prueba de punta a punta +
limpieza con limpiar_numero_demo.py --seg (regla 9) → OK de la Dra. a la lista → cargar_lista_semilla.py --apply --ok-dra → DEL seg:off.
"""
import argparse, copy, difflib, json, re, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_v7_flag_lucas as A  # noqa: E402  (api, utilidades de grafo, copia de Parse Intent, harness)
from check_triaje_grafo import chequear_grafo  # noqa: E402  (los chequeos de grafo de check_triaje.py, sobre un dict)

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
DRY = ROOT / "workflows" / "current" / "dia1_segmentacion"      # ignorado por git (contiene el workflow vivo)
SRC = ROOT / "segmentacion" / "dia1"
V6, HELPER = A.V6, "S5U6tSipzlgFHCkf"

# ---------------------------------------------------------------------------------------------------------------- nombres
N_TIPO, N_OFF, N_SIL = "Seg: Consultar Tipo", "Seg: Redis GET off", "Seg: ¿Silenciar?"
N_RED, N_AVI, N_GRUPO = "Seg: Red de seguridad", "Seg: ¿Avisar?", "Seg: Avisar al grupo"
N_SAL = "Seg: Tipo Salida"
N_FALLO, N_FGET, N_TEC, N_FSET = "Seg: ¿Falló la consulta?", "Seg: Redis GET falla", "Seg: Aviso técnico", "Seg: Redis SET falla"
RED = [N_RED, N_AVI, N_GRUPO]
FALLA = [N_FALLO, N_FGET, N_TEC, N_FSET]
NUEVOS = [N_TIPO, N_OFF, N_SIL, N_SAL] + RED + FALLA
# Salida que sigue un teléfono que NO se silencia al pasar por un nodo nuevo. Con esto colapsado, el grafo tiene que ser el de hoy.
RAMA = {N_TIPO: 0, N_OFF: 0, N_SIL: 1, N_SAL: 0}
LIMPIAR, TAKEOVER, BOTACT, LOOP, TYPING, GATE, ENVIAR = ("Buffer: Limpiar", "Consultar Takeover Paciente", "Bot Activo?", "Loop Mensajes",
                                                        "Evolution - Typing", "Gate Humano Final", "Evolution API - Enviar Mensaje")
WEBHOOK, KILL, ESADMIN = "Webhook - Evolution API", "Kill-switch Check", "Es comando admin?"
EDITADOS = [GATE]
ANCLA = "const phone = ($('Preparar Mensaje Final').first().json.phone || '').toString();\n"

# La consulta de los 2 nodos Postgres: SIEMPRE exactamente 1 fila (un SELECT sobre una función escalar), aunque el teléfono no exista.
# contacto_ruta (sql/2026-10-14_contacto_tipos.sql) es STABLE y solo lee; con tipo null / dudoso / prueba → seg_silencia false.
SQL_TIPO = ("SELECT (r->>'tipo') AS seg_tipo, COALESCE((r->>'silencia')::boolean, false) AS seg_silencia, "
            "COALESCE((r->>'red')::boolean, false) AS seg_con_red, (r->>'fuente') AS seg_fuente, "
            "(r->>'desde') AS seg_desde, (r->>'puesto_por') AS seg_puesto_por "
            "FROM (SELECT public.contacto_ruta($1) AS r) s")
PHONE_EXPR = "={{ $('Preparar Mensaje Final').first().json.phone }}"
EXPR_SIL = (f"($json.seg_off === null || $json.seg_off === '') && "
            f"($('{N_TIPO}').isExecuted ? $('{N_TIPO}').first().json.seg_silencia === true : false)")
EXPR_AVI = "$json.avisar === true"
EXPR_FALLO = "($json.error !== undefined && $json.error !== null && $json.error !== '')"
TOPE_FALLA = 21600   # aviso técnico: 1 cada 6 h (ventana fija: SET con TTL después de un POST exitoso; no se renueva)


# ================================================================================================================ lectura
def red(s):
    """Redacta secretos de los nodos (PUT-A pendiente: hay sb_secret y apikeys escritas en el v6)."""
    s = re.sub(r"sb_secret_[A-Za-z0-9_\-]+", "<SB_SECRET>", s)
    s = re.sub(r"https://[a-z0-9]{12,}\.supabase\.co", "https://<PROYECTO>.supabase.co", s)
    s = re.sub(r"(CW_TOKEN\s*=\s*['\"])[^'\"]+", r"\1<REDACT>", s)
    return s


def leer(offline=None):
    if offline:
        d = Path(offline)
        return json.loads((d / "v6.json").read_text(encoding="utf-8")), json.loads((d / "helper.json").read_text(encoding="utf-8"))
    return A.api(f"/workflows/{V6}"), A.api(f"/workflows/{HELPER}")


def src(nombre):
    return (SRC / nombre).read_text(encoding="utf-8").rstrip() + "\n"


def main_de(c, s, i):
    salidas = (c.get(s) or {}).get("main") or []
    return [(x["node"], x.get("index", 0)) for x in (salidas[i] or [])] if len(salidas) > i else []


def entradas(c, d):
    return sorted((s, t, i) for (s, t, i, dd, _x) in A.arcos(c) if dd == d)


# ================================================================================================================ prerrequisitos
def prerrequisitos(v6, helper, db=None):
    r = []
    chk = lambda ok, txt: r.append([bool(ok), txt])
    n, c = A.por_nombre(v6), v6["connections"]
    chk(v6.get("active"), f"v6 activo (versionId {str(v6.get('versionId'))[:8]}, {len(v6['nodes'])} nodos)")
    chk(any(x.get("webhookId") == "evo-webhook-v2" for x in v6["nodes"]), "v6 conserva webhookId evo-webhook-v2")
    chk(not any(k.startswith("Seg:") for k in n), "el v6 todavía no tiene nodos 'Seg:' (no está aplicado)")
    faltan = [k for k in (LIMPIAR, TAKEOVER, BOTACT, LOOP, TYPING, GATE, ENVIAR, WEBHOOK, KILL, ESADMIN, "Preparar Mensaje Final",
                          "Parse Intent", "V7: Redis GET modo", "Inbox Live") if k not in n]
    chk(not faltan, "nodos del v6 que se usan existen" + (f" — FALTAN {faltan}" if faltan else ""))
    if faltan:
        return r
    chk(main_de(c, LIMPIAR, 0) == [(TAKEOVER, 0)] and entradas(c, TAKEOVER) == [(LIMPIAR, "main", 0)],
        "Buffer: Limpiar → Consultar Takeover Paciente (arco que se redirige; única entrada)")
    chk(main_de(c, TAKEOVER, 0) == [(BOTACT, 0)], "Consultar Takeover Paciente → Bot Activo? (siguen pegados)")
    chk(main_de(c, LOOP, 1) == [(TYPING, 0)] and main_de(c, TYPING, 0) == [(GATE, 0)] and main_de(c, GATE, 0) == [(ENVIAR, 0)]
        and entradas(c, ENVIAR) == [(GATE, "main", 0)], "Loop Mensajes[1] → Typing → Gate Humano Final → Enviar (única entrada de Enviar)")
    chk(main_de(c, ESADMIN, 0) and main_de(c, ESADMIN, 1) == [("Redis GET bot:status", 0)], "kill-switch: Es comando admin?[no] → Redis GET bot:status")
    tk = n[TAKEOVER]
    chk(tk["type"] == "n8n-nodes-base.postgres" and tk.get("continueOnFail") and tk.get("alwaysOutputData") and (tk.get("credentials") or {}).get("postgres")
        and not re.search(r"\$json|\$input", json.dumps(tk["parameters"])), "Consultar Takeover: postgres fail-open que NO lee $json (cambiar su item de entrada no lo afecta)")
    lee_json = [k for k in (TYPING, ENVIAR) if re.search(r"\$json|\$input", json.dumps(n[k]["parameters"]))]
    chk(not lee_json and all("$('Loop Mensajes')" in json.dumps(n[k]["parameters"]) for k in (TYPING, ENVIAR)),
        "Typing y Enviar leen $('Loop Mensajes'), no $json (Seg: Tipo Salida antes de Typing no los afecta)")
    g = n[GATE]["parameters"].get("jsCode", "")
    chk(g.count(ANCLA) == 1 and "const items = $input.all();" in g and "Seg:" not in g, "Gate Humano Final: ancla `const phone = …` única y sin bloque Seg previo")
    rg = n["V7: Redis GET modo"]
    chk(rg["type"] == "n8n-nodes-base.redis" and (rg.get("credentials") or {}).get("redis") and rg.get("onError") == "continueRegularOutput",
        "V7: Redis GET modo es el molde redis fail-open (credencial a copiar)")
    copia, err = A.copia_parse_intent(n)
    chk(copia, "Parse Intent: textoNorm + esUrgenciaFuerte iguales a la copia fijada" + (f" — {err}" if err else ""))
    refs = [k for k, x in n.items() if "Seg: " in json.dumps(x.get("parameters", {}), ensure_ascii=False)]
    chk(not refs, f"ningún nodo nombra un nodo 'Seg: ' ({refs})")
    # ---- helper notify-grupo: el texto en body.text llega al grupo y NO prende el modo humano ----
    hn = A.por_nombre(helper)
    dec = (hn.get("Decidir Takeover") or {}).get("parameters", {}).get("jsCode", "")
    send = json.dumps((hn.get("Notify Grupo Send") or {}).get("parameters", {}), ensure_ascii=False)
    wh = (hn.get("Webhook") or {}).get("parameters", {})
    chk(helper.get("active") and wh.get("path") == "notify-grupo" and wh.get("responseMode") == "onReceived", "Helper notify-grupo activo, POST /webhook/notify-grupo, responde al recibir")
    chk("json.body.text" in send and "query.phone" in send, "Helper: manda al grupo query.resumen || body.text, con el link de query.phone")
    chk("q.resumen ?? b.resumen" in dec and "q.tomar ?? b.tomar" in dec and ".text" not in dec,
        "Helper: Decidir Takeover mira solo resumen/tomar (body.text no prende el modo humano)")
    if db is not None:
        chk(db.get("ruta_ok"), f"base: public.contacto_ruta existe y la consulta de los nodos da 1 fila ({db.get('detalle')})")
    return r


def estado_db():
    """Solo lectura: ¿está la migración? (requisito del --apply)."""
    from apply_migracion_contacto_tipos import conectar
    try:
        c = conectar(solo_lectura=True)
        cur = c.cursor()
        cur.execute("select to_regprocedure('public.contacto_ruta(text)') is not null")
        if not cur.fetchone()[0]:
            c.close()
            return {"ruta_ok": False, "detalle": "no existe: correr antes scripts/apply_migracion_contacto_tipos.py --apply"}
        cur.execute(SQL_TIPO.replace("$1", "%s"), ("5490000000001",))
        filas = cur.fetchall()
        c.close()
        return {"ruta_ok": len(filas) == 1 and filas[0][1] is False, "detalle": f"{len(filas)} fila(s) para un sintético"}
    except Exception as e:
        return {"ruta_ok": False, "detalle": f"error de lectura: {str(e)[:120]}"}


# ================================================================================================================ construcción
def construir(v6):
    wf = copy.deepcopy(v6)
    n, c = A.por_nombre(wf), wf["connections"]
    copia, err = A.copia_parse_intent(n)
    if err:
        raise SystemExit("ABORTO: " + err)
    red_js = src("red_de_seguridad.js")
    if red_js.count(A.MARCA_COPIA) != 1:
        raise SystemExit("ABORTO: segmentacion/dia1/red_de_seguridad.js no tiene el marcador de la copia de Parse Intent.")
    red_js = red_js.replace(A.MARCA_COPIA, copia)
    cred_pg = copy.deepcopy(n[TAKEOVER]["credentials"])
    cred_redis = copy.deepcopy(n["V7: Redis GET modo"]["credentials"])
    pg = lambda nombre, x, y: A.nodo(nombre, "n8n-nodes-base.postgres", 2.5, {"operation": "executeQuery", "query": SQL_TIPO,
                                                                           "options": {"queryReplacement": PHONE_EXPR}},
                                     x, y, credentials=copy.deepcopy(cred_pg), alwaysOutputData=True, continueOnFail=True)
    y, yr, yf = 816, 1040, 1264
    wf["nodes"].extend([
        pg(N_TIPO, 7520, y),
        A.nodo(N_OFF, "n8n-nodes-base.redis", 1, {"operation": "get", "propertyName": "seg_off", "key": "seg:off", "keyType": "string", "options": {}},
               7744, y, credentials=copy.deepcopy(cred_redis), alwaysOutputData=True, onError="continueRegularOutput"),
        A.nodo(N_SIL, "n8n-nodes-base.if", 2.2, A.if_bool(EXPR_SIL, "seg-silenciar-c"), 7968, y),
        A.nodo(N_RED, "n8n-nodes-base.code", 2, {"jsCode": red_js}, 8192, yr),
        A.nodo(N_AVI, "n8n-nodes-base.if", 2.2, A.if_bool(EXPR_AVI, "seg-avisar-c"), 8416, yr),
        A.nodo(N_GRUPO, "n8n-nodes-base.code", 2, {"jsCode": src("avisar_al_grupo.js")}, 8640, yr),
        pg(N_SAL, 15424, 576),
        # aviso técnico: rama terminal DEBAJO de todo (y mayor → con executionOrder v1 corre después del camino normal)
        A.nodo(N_FALLO, "n8n-nodes-base.if", 2.2, A.if_bool(EXPR_FALLO, "seg-fallo-c"), 7744, yf, onError="continueRegularOutput"),
        A.nodo(N_FGET, "n8n-nodes-base.redis", 1, {"operation": "get", "propertyName": "seg_falla", "key": "seg:falla", "keyType": "string", "options": {}},
               7968, yf, credentials=copy.deepcopy(cred_redis), alwaysOutputData=True, onError="continueRegularOutput"),
        A.nodo(N_TEC, "n8n-nodes-base.code", 2, {"jsCode": src("aviso_tecnico.js")}, 8192, yf, onError="continueRegularOutput"),
        A.nodo(N_FSET, "n8n-nodes-base.redis", 1, {"operation": "set", "key": "seg:falla", "value": "1", "keyType": "string",
                                                   "expire": True, "ttl": TOPE_FALLA},
               8416, yf, credentials=copy.deepcopy(cred_redis), onError="continueRegularOutput"),
    ])
    c[LIMPIAR]["main"][0] = [A.arco(N_TIPO)]
    c[LOOP]["main"][1] = [A.arco(N_SAL)]
    c[N_TIPO] = {"main": [[A.arco(N_OFF), A.arco(N_FALLO)]]}
    c[N_OFF] = {"main": [[A.arco(N_SIL)]]}
    c[N_SIL] = {"main": [[A.arco(N_RED)], [A.arco(TAKEOVER)]]}
    c[N_RED] = {"main": [[A.arco(N_AVI)]]}
    c[N_AVI] = {"main": [[A.arco(N_GRUPO)], []]}
    c[N_SAL] = {"main": [[A.arco(TYPING)]]}
    c[N_FALLO] = {"main": [[A.arco(N_FGET)], []]}
    c[N_FGET] = {"main": [[A.arco(N_TEC)]]}
    c[N_TEC] = {"main": [[A.arco(N_FSET)]]}
    code = n[GATE]["parameters"]["jsCode"]
    if code.count(ANCLA) != 1:
        raise SystemExit("ABORTO: el ancla de Gate Humano Final no es única (¿PUT-A u otra sesión la cambió?). Volver a mirar.")
    n[GATE]["parameters"]["jsCode"] = code.replace(ANCLA, ANCLA + src("gate_humano_final_bloque.js"))
    return wf


# ================================================================================================================ invariantes (sin red)
def colapsar(conns):
    """Arcos que ve un teléfono que NO se silencia: cada nodo nuevo se reemplaza por la salida RAMA que sigue su item."""
    res = set()
    for (s, t, i, d, idx) in A.arcos(conns):
        if s in NUEVOS:
            continue
        vistos = 0
        while d in NUEVOS:
            if d not in RAMA:
                d = "!!rama-silencio:" + d
                break
            sig = ((conns.get(d) or {}).get("main") or [])
            sig = sig[RAMA[d]] if len(sig) > RAMA[d] else []
            sig = [x for x in sig if x["node"] not in FALLA]   # la rama del aviso técnico es terminal (se verifica aparte)
            if len(sig) != 1:
                d = f"!!{d}-con-{len(sig)}-destinos"
                break
            d, idx = sig[0]["node"], sig[0].get("index", 0)
            vistos += 1
            if vistos > 10:
                d = "!!ciclo"
                break
        res.add((s, t, i, d, idx))
    return res


def alcanzables(conns, desde, sin_nodo=None, sin_arco=None):
    """Nodos alcanzables por arcos 'main' desde `desde` (opcional: quitando un nodo o un arco (origen, salida))."""
    vis, pila = set(), [desde]
    while pila:
        x = pila.pop()
        if x in vis or x == sin_nodo:
            continue
        vis.add(x)
        for i, lista in enumerate((conns.get(x) or {}).get("main") or []):
            if sin_arco == (x, i):
                continue
            pila.extend(t["node"] for t in (lista or []))
    return vis


def invariantes(pre, post):
    r = []
    chk = lambda ok, txt: r.append([bool(ok), txt])
    pn, qn = A.por_nombre(pre), A.por_nombre(post)
    c = post["connections"]
    chk(sorted(set(qn) - set(pn)) == sorted(NUEVOS) and set(pn) <= set(qn), f"nodos: {len(pn)} → {len(qn)}; los nuevos son exactamente los {len(NUEVOS)} 'Seg: '")
    claves = ("type", "typeVersion", "credentials", "position", "disabled", "webhookId", "alwaysOutputData", "onError", "continueOnFail", "id")
    cambiados = sorted(k for k in pn if any(pn[k].get(x) != qn[k].get(x) for x in claves) or pn[k].get("parameters") != qn[k].get("parameters"))
    chk(cambiados == EDITADOS, f"solo cambia Gate Humano Final (cambiados: {cambiados})")
    g_pre, g_post = pn[GATE]["parameters"]["jsCode"], qn[GATE]["parameters"]["jsCode"]
    chk(g_post == g_pre.replace(ANCLA, ANCLA + src("gate_humano_final_bloque.js")) and all(pn[GATE].get(x) == qn[GATE].get(x) for x in claves),
        "Gate Humano Final = el de hoy + el bloque Seg después de `const phone = …` (nada más)")
    a_pre, a_post = A.arcos(pre["connections"]), A.arcos(c)
    col = colapsar(c)
    chk(col == a_pre, "TELÉFONO SIN TIPO (o que no se silencia): con los nodos nuevos colapsados, el grafo es IDÉNTICO al de hoy"
        + ("" if col == a_pre else f" — sobran {sorted(col - a_pre)[:4]} faltan {sorted(a_pre - col)[:4]}"))
    quitados, agregados = a_pre - a_post, a_post - a_pre
    chk(quitados == {(LIMPIAR, "main", 0, TAKEOVER, 0), (LOOP, "main", 1, TYPING, 0)},
        f"se redirigen exactamente 2 arcos (Buffer: Limpiar→Consultar Takeover, Loop Mensajes[1]→Typing): {sorted(quitados)}")
    chk({a for a in agregados if a[0] not in NUEVOS} == {(LIMPIAR, "main", 0, N_TIPO, 0), (LOOP, "main", 1, N_SAL, 0)}, "a lo nuevo solo se entra por esos 2 arcos")
    chk({a for a in agregados if a[0] in NUEVOS and a[3] not in NUEVOS} == {(N_SIL, "main", 1, TAKEOVER, 0), (N_SAL, "main", 0, TYPING, 0)},
        "de lo nuevo al v6 solo salen ¿Silenciar?[no]→Consultar Takeover y Tipo Salida→Typing")
    # red de seguridad: cerrada, terminal, solo desde ¿Silenciar?[sí]
    desde_red = alcanzables(c, N_RED)
    chk(desde_red == set(RED), f"la red de seguridad no llega a NINGÚN nodo del v6 (ni respuesta ni triaje): alcanza {sorted(desde_red)}")
    ent_red = {(s, i) for (s, t, i, d, _x) in a_post if d in RED and s not in RED}
    chk(ent_red == {(N_SIL, 0)}, f"a la red solo se entra por Seg: ¿Silenciar?[sí] ({sorted(ent_red)})")
    chk(not any(o for o in (c.get(N_GRUPO) or {}).get("main") or []) and main_de(c, N_AVI, 1) == [], "Avisar al grupo y ¿Avisar?[no] no tienen salida")
    chk(main_de(c, N_AVI, 0) == [(N_GRUPO, 0)] and not any(qn[k]["type"].endswith(".redis") for k in RED),
        "SIN TOPE en la urgencia fuerte (plan §2.5): ¿Avisar?[sí] → Avisar al grupo directo, sin contador Redis en la red")
    # aviso técnico: rama cerrada y terminal, solo desde Seg: Consultar Tipo, debajo del camino normal
    desde_f = alcanzables(c, N_FALLO)
    chk(desde_f == set(FALLA), f"aviso técnico: la rama no llega a NINGÚN nodo del v6 (alcanza {sorted(desde_f)})")
    ent_f = {(s, i) for (s, t, i, d, _x) in a_post if d in FALLA and s not in FALLA}
    chk(ent_f == {(N_TIPO, 0)} and sorted(x for x, _ in main_de(c, N_TIPO, 0)) == sorted([N_OFF, N_FALLO]),
        f"aviso técnico: se entra solo por Seg: Consultar Tipo, en paralelo con Seg: Redis GET off ({sorted(ent_f)})")
    chk(qn[N_FALLO]["position"][1] > qn[N_OFF]["position"][1],
        "aviso técnico debajo de Seg: Redis GET off en el lienzo (executionOrder v1: corre DESPUÉS del camino normal, no lo demora)")
    chk(main_de(c, N_FALLO, 0) == [(N_FGET, 0)] and main_de(c, N_FALLO, 1) == [] and main_de(c, N_FGET, 0) == [(N_TEC, 0)]
        and main_de(c, N_TEC, 0) == [(N_FSET, 0)] and not any(o for o in (c.get(N_FSET) or {}).get("main") or []),
        "aviso técnico: ¿Falló?[sí] → GET seg:falla → Aviso técnico → SET seg:falla (el tope se escribe DESPUÉS del POST)")
    chk(all(qn[k].get("onError") == "continueRegularOutput" for k in FALLA), "aviso técnico: todos sus nodos fallan abierto (onError continueRegularOutput)")
    fs_ = qn[N_FSET]["parameters"]
    chk(fs_.get("operation") == "set" and fs_.get("key") == "seg:falla" and fs_.get("expire") is True and fs_.get("ttl") == TOPE_FALLA
        and qn[N_FGET]["parameters"].get("key") == "seg:falla" and qn[N_FGET].get("alwaysOutputData") is True,
        f"aviso técnico: tope fijo seg:falla TTL {TOPE_FALLA} s (SET, no INCR: no se renueva)")
    chk(A.expr_de(qn[N_FALLO]) == EXPR_FALLO and qn[N_FALLO]["parameters"]["conditions"]["options"]["typeValidation"] == "strict",
        "¿Falló la consulta?: expresión fijada (siempre booleana)")
    # orden: kill-switch antes del silencio; nadie llega a Consultar Takeover ni a Enviar sin pasar por los controles
    alc = alcanzables(c, WEBHOOK)
    chk(N_TIPO in alc and N_TIPO not in alcanzables(c, WEBHOOK, sin_arco=(ESADMIN, 1)),
        "KILL-SWITCH ANTES DEL SILENCIO: a Seg: Consultar Tipo solo se llega por Es comando admin?[no]")
    admin = set()
    for t in main_de(c, ESADMIN, 0):
        admin |= alcanzables(c, t[0])
    chk(not (admin & set(NUEVOS)), "los /bot off|on|status (Es comando admin?[sí]) no pasan por ningún nodo Seg")
    chk(TAKEOVER not in alcanzables(c, WEBHOOK, sin_nodo=N_SIL), "a Consultar Takeover (modo humano, v7, triaje, v6) solo se llega por Seg: ¿Silenciar?")
    chk(ENVIAR not in alcanzables(c, WEBHOOK, sin_nodo=GATE) and ENVIAR not in alcanzables(c, WEBHOOK, sin_nodo=N_SAL),
        "a Enviar Mensaje solo se llega por Seg: Tipo Salida y Gate Humano Final")
    chk(ENVIAR in alcanzables(c, "V7: Adaptador") and ENVIAR not in alcanzables(c, "V7: Adaptador", sin_nodo=GATE),
        "el v7 (V7: Adaptador) sale por el control final (Gate Humano Final)")
    # inbox live (panel) y health check: siguen antes de todo esto
    chk("Inbox Live" not in alcanzables(c, N_TIPO) and "Inbox Live" in alc, "Inbox Live sigue antes del silencio (el entrante del silenciado llega al panel)")
    # nodos nuevos: forma
    for k in (N_TIPO, N_SAL):
        x = qn[k]
        chk(x["type"] == "n8n-nodes-base.postgres" and x.get("continueOnFail") is True and x.get("alwaysOutputData") is True
            and x.get("credentials") == pn[TAKEOVER].get("credentials") and x["parameters"].get("query") == SQL_TIPO
            and x["parameters"].get("options", {}).get("queryReplacement") == PHONE_EXPR, f"{k}: postgres fail-open, credencial de Consultar Takeover, SQL de 1 fila")
    chk(re.fullmatch(r"SELECT .* FROM \(SELECT public\.contacto_ruta\(\$1\) AS r\) s", SQL_TIPO) is not None, "SQL_TIPO: un SELECT sobre una llamada escalar → siempre 1 fila")
    for k, prop, key in ((N_OFF, "seg_off", "seg:off"),):
        x = qn[k]
        chk(x.get("alwaysOutputData") is True and x.get("onError") == "continueRegularOutput" and x["parameters"].get("key") == key
            and x["parameters"].get("propertyName") == prop and x["parameters"].get("operation") == "get"
            and x.get("credentials") == pn["V7: Redis GET modo"].get("credentials"), f"{k}: GET {key} fail-open")
    chk(A.expr_de(qn[N_SIL]) == EXPR_SIL and qn[N_SIL]["parameters"]["conditions"]["options"]["typeValidation"] == "strict", "¿Silenciar?: expresión fijada (siempre booleana)")
    chk(A.expr_de(qn[N_AVI]) == EXPR_AVI, "¿Avisar?: $json.avisar === true")
    rj = qn[N_RED]["parameters"]["jsCode"]
    chk(A.PARSE_URGENCIA in rj and A.PARSE_TEXTONORM in rj and A.MARCA_COPIA not in rj, "Red de seguridad: copia textual de esUrgenciaFuerte del Parse Intent vivo")
    for k in (N_RED, N_GRUPO, N_TEC):
        code = chr(10).join(l for l in qn[k]["parameters"]["jsCode"].splitlines() if not l.lstrip().startswith("//"))   # sin comentarios
        chk(not re.search(r"INSERT|UPDATE|n8n_chat_histories|human_takeover|tomar|silencioso|/send/|evolution|Loop Mensajes", code, re.I),
            f"{k}: no escribe memoria, no toca human_takeover, no le manda nada al contacto")
    gj = qn[N_GRUPO]["parameters"]["jsCode"]
    chk("webhook/notify-grupo" in gj and "qs: { phone: phone }" in gj and "body: { text: resumen }" in gj and "resumen:" not in gj.split("qs:")[1].split("}")[0],
        "Avisar al grupo: POST notify-grupo con qs {phone} y el texto en body.text (sin resumen ni tomar en la query)")
    tj = qn[N_TEC]["parameters"]["jsCode"]
    chk("webhook/notify-grupo" in tj and "qs:" not in tj and "body: { text: texto }" in tj and "Preparar Mensaje Final" not in tj,
        "Aviso técnico: POST notify-grupo con el texto en body.text, sin teléfono ni texto del contacto")
    chk(any(x.get("webhookId") == "evo-webhook-v2" for x in post["nodes"])
        and {x["name"]: x.get("webhookId") for x in pre["nodes"] if x.get("webhookId")} == {x["name"]: x.get("webhookId") for x in post["nodes"] if x.get("webhookId")},
        "webhookIds conservados (evo-webhook-v2 incluido)")
    # los chequeos de grafo de check_triaje.py (misma función, no una copia): sobre el v6 PROPUESTO
    for ok_, t in chequear_grafo(post):
        chk(ok_, "check_triaje (grafo del propuesto): " + t)
    return r


# ================================================================================================================ pruebas offline (harness)
def envolver_http(codigo, respuesta=None, falla=False):
    """Envuelve el jsCode con un mock de this.helpers.httpRequest que registra las llamadas (tests/harness_code_node.mjs pasa helpers: {})."""
    return ("const __ll = [];\n"
            f"this.helpers.httpRequest = async (o) => {{ __ll.push(JSON.parse(JSON.stringify(o))); if ({'true' if falla else 'false'}) throw new Error('caido'); "
            f"return (o.method || 'GET') === 'GET' ? {json.dumps(respuesta if respuesta is not None else [])} : {{}}; }};\n"
            "const __r = await (async () => {\n" + codigo + "\n})();\n"
            "return [{ json: { n: __r ? __r.length : 0, first: __r && __r[0] ? __r[0].json : null, llamadas: __ll } }];")


def pruebas_offline(pre, post):
    pn, qn = A.por_nombre(pre), A.por_nombre(post)
    r = []
    chk = lambda ok, txt: r.append([bool(ok), txt])
    TEL = "5490000000001"
    PM = lambda t: {"Preparar Mensaje Final": {"text": t, "phone": TEL, "remoteJid": TEL + "@s.whatsapp.net"}}
    TIPO = lambda tipo, sil, red_: {"seg_tipo": tipo, "seg_silencia": sil, "seg_con_red": red_, "seg_fuente": "tipo" if tipo else "sin_tipo",
                                    "seg_desde": "2026-10-20T02:30:00+00:00" if tipo else None, "seg_puesto_por": "irina" if tipo else None}
    casos = []

    def ex(cid, nodo_if, entrada, nodos=None, no_ej=None):
        casos.append({"id": cid, "codigo": "return [{ json: { v: (" + A.expr_de(nodo_if) + ") } }];", "input": entrada, "nodos": nodos or {}, "noEjecutados": no_ej or []})

    # --- 1) Seg: ¿Silenciar? ---
    sil = [("proveedor_sin_off", {"seg_off": None}, {N_TIPO: TIPO("proveedor", True, True)}, None, True),
           ("interno_sin_off", {"seg_off": None}, {N_TIPO: TIPO("interno", True, False)}, None, True),
           ("seg_off_1", {"seg_off": "1"}, {N_TIPO: TIPO("proveedor", True, True)}, None, False),
           ("seg_off_cualquiera", {"seg_off": "si"}, {N_TIPO: TIPO("interno", True, False)}, None, False),
           ("redis_caido", {"error": "ECONNREFUSED"}, {N_TIPO: TIPO("proveedor", True, True)}, None, False),
           ("sin_tipo", {"seg_off": None}, {N_TIPO: TIPO(None, False, False)}, None, False),
           # La base devuelve silencia=false para todo contacto sin un tipo que silencie ('dudoso' no se carga y 'prueba' ya no es un tipo):
           # eso lo garantiza tests/test_migracion_contacto_tipos.mjs, que el --apply corre. Aca solo se prueba que el IF respeta ese valor.
           ("base_dice_no_silencia", {"seg_off": None}, {N_TIPO: TIPO("paciente", False, False)}, None, False),
           ("paciente", {"seg_off": None}, {N_TIPO: TIPO("paciente", False, False)}, None, False),
           ("consulta_vacia", {"seg_off": None}, {N_TIPO: {}}, None, False),
           ("consulta_error", {"seg_off": None}, {N_TIPO: {"error": "function public.contacto_ruta(unknown) does not exist"}}, None, False),
           ("silencia_string", {"seg_off": None}, {N_TIPO: {"seg_silencia": "true"}}, None, False),
           ("tipo_no_corrio", {"seg_off": None}, {}, [N_TIPO], False)]
    for cid, ent, nodos, no_ej, _e in sil:
        ex("sil|" + cid, qn[N_SIL], ent, nodos, no_ej)
    # --- 2) Seg: Red de seguridad ---
    redc = [("proveedor_dolor", "proveedor", True, "hola, me duele mucho la muela desde ayer", True),
            ("colega_bracket", "colega", True, "a la paciente se le salió el bracket de abajo", True),
            ("no_paciente_sangra", "no_paciente", True, "me sangra la encía", True),
            ("proveedor_factura", "proveedor", True, "te mando la factura del pedido", False),
            ("proveedor_sin_dolor", "proveedor", True, "el trabajo quedó listo, sin dolor para la paciente", False),
            ("interno_dolor", "interno", False, "la paciente de las 10 tiene dolor, la atiendo yo", False),
            ("interno_con_red_por_error", "interno", True, "tiene mucho dolor", False),
            ("audio_proveedor", "proveedor", True, "[AUDIO] hola, tengo fiebre y me duele", True)]
    for cid, tipo, conred, t, _e in redc:
        casos.append({"id": "red|" + cid, "codigo": qn[N_RED]["parameters"]["jsCode"], "input": {"seg_off": None}, "nodos": dict(PM(t), **{N_TIPO: TIPO(tipo, True, conred)})})
    casos.append({"id": "red|sin_nodos", "codigo": qn[N_RED]["parameters"]["jsCode"], "input": {}, "nodos": {}})
    # --- 3) ¿Avisar? ---
    for j, e in enumerate([{"avisar": True}, {"avisar": False}, {}, {"avisar": "true"}]):
        ex(f"avi|{j}", qn[N_AVI], e)
    # --- 4) Seg: Avisar al grupo (con mock de httpRequest). SIN tope: la 2.a y 3.a urgencia seguidas tambien avisan; si el 1.o fallo, el 2.o sale ---
    largo = "me duele " + "muchísimo " * 40
    grp = [("primero", {"avisar": True}, "me duele mucho", False),
           ("segunda_urgencia_6_min", {"avisar": True, "seg:aviso:" + TEL: 2}, "le sangra mucho, qué hago", False),
           ("tercera_urgencia_12_min", {"avisar": True, "seg:aviso:" + TEL: 3}, "sigue sangrando", False),
           ("helper_caido", {"avisar": True}, "me duele mucho", True),
           ("despues_de_falla", {"avisar": True, "seg:aviso:" + TEL: 2, "avisado": False}, "me duele mucho", False),
           ("largo", {"avisar": True}, largo, False)]
    for cid, ent, t, falla in grp:
        casos.append({"id": "grp|" + cid, "codigo": envolver_http(qn[N_GRUPO]["parameters"]["jsCode"], falla=falla), "input": ent,
                      "nodos": dict(PM(t), **{N_TIPO: TIPO("proveedor", True, True)})})
    # --- 5) Gate Humano Final: viejo vs nuevo ---
    reciente = "2026-10-05T12:20:00Z"   # el harness fija Date.now() en 2026-10-05T12:36:00Z → 16 min
    humano = [{"human_takeover": True, "human_takeover_at": reciente}]
    BL = {"Banlist Validator": {"output": "Hola, le paso los horarios."}}
    gate = [  # (id, nodos Seg, noEjecutados, respuesta PostgREST, se espera que el nuevo bloquee)
        ("sin_tipo", {N_OFF: {"seg_off": None}, N_SAL: TIPO(None, False, False)}, [], [], False),
        ("base_dice_no_silencia", {N_OFF: {"seg_off": None}, N_SAL: TIPO("paciente", False, False)}, [], [], False),
        ("silencia", {N_OFF: {"seg_off": None}, N_SAL: TIPO("proveedor", True, True)}, [], [], True),
        ("silencia_interno", {N_OFF: {"seg_off": None}, N_SAL: TIPO("interno", True, False)}, [], [], True),
        ("silencia_seg_off", {N_OFF: {"seg_off": "1"}, N_SAL: TIPO("proveedor", True, True)}, [], [], False),
        ("salida_error", {N_OFF: {"seg_off": None}, N_SAL: {"error": "boom"}}, [], [], False),
        ("salida_vacia", {N_OFF: {"seg_off": None}, N_SAL: {}}, [], [], False),
        ("redis_caido", {N_OFF: {"error": "x"}, N_SAL: TIPO("proveedor", True, True)}, [], [], False),
        ("salida_no_corrio", {N_OFF: {"seg_off": None}}, [N_SAL], [], False),
        ("off_no_corrio", {N_SAL: TIPO("proveedor", True, True)}, [N_OFF], [], False),
        ("nodos_inexistentes", {}, [], [], False),
        ("humano_sin_tipo", {N_OFF: {"seg_off": None}, N_SAL: TIPO(None, False, False)}, [], humano, False),
    ]
    for cid, segn, noej, resp, _b in gate:
        for lado, wf in (("viejo", pn), ("nuevo", qn)):
            casos.append({"id": f"gate|{cid}|{lado}", "codigo": envolver_http(wf[GATE]["parameters"]["jsCode"], respuesta=resp),
                          "input": {"ok": True}, "nodos": dict(PM("hola"), **BL, **segn), "noEjecutados": noej})
    res = A.correr_harness(casos)
    v = lambda cid: (res[cid].get("json") or {}).get("v", "ERROR " + str(res[cid].get("error")))
    j = lambda cid: res[cid].get("json") or {"error": res[cid].get("error")}
    # --- veredictos ---
    malos = [cid for cid, _a, _b, _c, e in sil if v("sil|" + cid) is not e]
    chk(not malos, f"¿Silenciar?: {len(sil)} casos (silencia solo con tipo que silencia y sin seg:off; Redis caído / consulta con error / vacía / no corrió → NO silencia)"
        + (f" — FALLAN {[(m, v('sil|' + m)) for m in malos]}" if malos else ""))
    chk(all(isinstance(v("sil|" + cid), bool) for cid, *_ in sil), "¿Silenciar?: siempre devuelve booleano (IF strict no rompe la ejecución)")
    malos = [cid for cid, _t, _c, _x, e in redc if j("red|" + cid).get("avisar") is not e]
    chk(not malos, f"Red de seguridad: {len(redc)} casos (proveedor/colega/no_paciente + urgencia fuerte → aviso; sin urgencia → silencio; interno NUNCA)"
        + (f" — FALLAN {malos}" if malos else ""))
    chk(j("red|sin_nodos").get("avisar") is False and res["red|sin_nodos"].get("n") == 1, "Red de seguridad: sin datos no rompe y no avisa (1 item)")
    chk(all(res["red|" + cid].get("n") == 1 for cid, *_ in redc), "Red de seguridad: siempre 1 item")
    chk([v(f"avi|{i}") for i in range(4)] == [True, False, False, False], "¿Avisar?: booleano estricto")
    g = {cid: (j("grp|" + cid).get("first") or {}, j("grp|" + cid).get("llamadas") or []) for cid, *_ in grp}
    p0 = g["primero"][1][0] if g["primero"][1] else {}
    t0 = p0.get("body", {}).get("text", "")
    chk(g["primero"][0].get("avisado") is True and len(g["primero"][1]) == 1 and p0.get("method") == "POST"
        and p0.get("url", "").endswith("/webhook/notify-grupo") and p0.get("qs") == {"phone": TEL}
        and t0.startswith("Contacto silenciado (proveedor, desde el 19/10, lo marcó Irina) escribió: «me duele mucho». El bot NO le respondió."),
        f"Avisar al grupo: 1 POST a notify-grupo, qs solo phone, texto en body.text con tipo, desde (hora AR) y quién ({t0[:110]})")
    chk("Lucas" not in t0 and "contestale vos" in t0 and "quiten la marca de proveedor" in t0,
        "Avisar al grupo: indica una acción que la clínica hace sola (no nombra a Lucas: desde febrero no está)")
    chk(not any(k in (p0.get("qs") or {}) for k in ("resumen", "tomar", "silencioso")), "Avisar al grupo: sin resumen/tomar/silencioso en la query (no prende el modo humano)")
    chk(all(g[k][0].get("avisado") is True and len(g[k][1]) == 1 for k in ("segunda_urgencia_6_min", "tercera_urgencia_12_min")),
        "Avisar al grupo SIN TOPE: 2.ª y 3.ª urgencia del mismo contacto a los 6 y 12 min → avisan las dos (plan §2.5)")
    chk(g["despues_de_falla"][0].get("avisado") is True and len(g["despues_de_falla"][1]) == 1,
        "Avisar al grupo: si el aviso anterior falló, el siguiente sale igual (no hay contador que lo descarte)")
    chk(g["helper_caido"][0].get("avisado") is False and g["helper_caido"][0].get("aviso_error") and res["grp|helper_caido"]["json"]["n"] == 1,
        "Avisar al grupo: helper caído → no rompe, deja aviso_error")
    tl = (g["largo"][1][0].get("body") or {}).get("text", "") if g["largo"][1] else ""
    cita = tl.split("«", 1)[-1].split("»", 1)[0]
    chk(0 < len(cita) <= 221 and cita.endswith("…") and len(tl) < 600, f"Avisar al grupo: mensaje del contacto recortado a 220 caracteres ({len(cita)}; total {len(tl)})")
    # --- 6) aviso técnico (contacto_ruta con error) ---
    casos2 = []
    fal = [(f"fal|{k}", e) for k, e in (("error", {"error": "function public.contacto_ruta(unknown) does not exist"}), ("ok", TIPO("proveedor", True, True)),
                                        ("sin_tipo", TIPO(None, False, False)), ("vacio", {}), ("error_vacio", {"error": ""}))]
    for cid, ent in fal:
        casos2.append({"id": cid, "codigo": "return [{ json: { v: (" + A.expr_de(qn[N_FALLO]) + ") } }];", "input": ent, "nodos": {}})
    ERR = {"error": "permission denied for function contacto_ruta 5491100000000"}
    tec = (("primera", {"seg_falla": None}, False), ("ya_avisado", {"seg_falla": "1"}, False),
           ("redis_caido", {"error": "ECONNREFUSED"}, False), ("helper_caido", {"seg_falla": None}, True))
    for cid, ent, falla in tec:
        casos2.append({"id": "tec|" + cid, "codigo": envolver_http(qn[N_TEC]["parameters"]["jsCode"], falla=falla), "input": dict(ERR, **ent),
                       "nodos": {N_TIPO: ERR}})
    res2 = A.correr_harness(casos2)
    v2 = lambda cid: (res2[cid].get("json") or {}).get("v", "ERROR " + str(res2[cid].get("error")))
    chk([v2(c_) for c_, _ in fal] == [True, False, False, False, False], f"¿Falló la consulta?: solo con error ({[v2(c_) for c_, _ in fal]})")
    t = {cid: (res2["tec|" + cid].get("json") or {"error": res2["tec|" + cid].get("error")}) for cid, *_ in tec}
    l1 = t["primera"].get("llamadas") or []
    txt = ((l1[0] if l1 else {}).get("body") or {}).get("text", "")
    chk(t["primera"].get("n") == 1 and len(l1) == 1 and l1[0].get("url", "").endswith("/webhook/notify-grupo") and "qs" not in l1[0]
        and txt.startswith("Aviso técnico de Asiri") and "5491100000000" not in txt,
        f"Aviso técnico: 1 POST al grupo sin teléfono ni números largos del error, y 1 item para el SET del tope ({txt[:90]})")
    chk(t["ya_avisado"].get("n") == 0 and not t["ya_avisado"].get("llamadas"), "Aviso técnico: seg:falla presente (ya se avisó en 6 h) → no llama")
    chk(t["redis_caido"].get("n") == 1 and len(t["redis_caido"].get("llamadas") or []) == 1, "Aviso técnico: Redis caído → avisa igual (lado seguro)")
    chk(t["helper_caido"].get("n") == 0 and len(t["helper_caido"].get("llamadas") or []) == 1,
        "Aviso técnico: helper caído → devuelve [] (no marca el tope: reintenta con el próximo mensaje)")
    for cid, _s, _n, _r, bloquea in gate:
        vj, nj = j(f"gate|{cid}|viejo"), j(f"gate|{cid}|nuevo")
        if bloquea:
            chk(nj.get("n") == 0 and not nj.get("llamadas") and vj.get("n") == 1, f"Gate Humano Final [{cid}]: el nuevo NO envía (devuelve []) y no avisa; el viejo enviaba")
        else:
            chk(vj == nj and "error" not in nj, f"Gate Humano Final [{cid}]: nuevo == viejo (misma salida y mismas llamadas)")
    chk(j("gate|humano_sin_tipo|viejo").get("n") == 0 and len(j("gate|humano_sin_tipo|viejo").get("llamadas") or []) == 2,
        "  (control) el modo humano de hoy sigue bloqueando y avisando en silencioso")
    return r


# ================================================================================================================ diff legible
def imprimir_diff(pre, post, ver_codigo=False):
    pn, qn = A.por_nombre(pre), A.por_nombre(post)
    print(f"\n=== NODOS NUEVOS ({len(NUEVOS)}) ===")
    for k in NUEVOS:
        x, p = qn[k], qn[k]["parameters"]
        if "jsCode" in p:
            det = f"Code, {len(p['jsCode'].splitlines())} líneas (segmentacion/dia1/)"
        elif x["type"].endswith(".if"):
            det = "IF  " + A.expr_de(x)
        elif x["type"].endswith(".redis"):
            det = f"Redis {p['operation'].upper()} {p['key']}" + (f" → {p['propertyName']}" if p.get("propertyName") else f" (TTL {p.get('ttl')})") + " (fail-open)"
        else:
            det = f"Postgres (continueOnFail, alwaysOutputData) $1={p['options']['queryReplacement']}\n      SQL: {p['query']}"
        print(f"  + {k:24s} {det}")
        if ver_codigo and "jsCode" in p:
            print("\n".join("      | " + l for l in red(p["jsCode"]).splitlines()))
    print(f"\n=== NODOS EDITADOS ({len(EDITADOS)}) — código antes/después (secretos redactados) ===")
    for k in EDITADOS:
        d = difflib.unified_diff(red(pn[k]["parameters"]["jsCode"]).splitlines(), red(qn[k]["parameters"]["jsCode"]).splitlines(), lineterm="", n=2)
        print(f"  ~ {k}")
        for l in list(d)[2:]:
            print("      " + l)
    a_pre, a_post = A.arcos(pre["connections"]), A.arcos(post["connections"])
    fmt = lambda a: f"{a[0]} [{a[1]}:{a[2]}] → {a[3]}" + (f" ({a[4]})" if a[4] else "")
    print("\n=== CONEXIONES QUITADAS ===")
    for a in sorted(a_pre - a_post):
        print("  - " + fmt(a))
    print("=== CONEXIONES AGREGADAS ===")
    for a in sorted(a_post - a_pre, key=lambda a: (NUEVOS.index(a[0]) if a[0] in NUEVOS else -1, a[2])):
        print("  + " + fmt(a))


# ================================================================================================================ PUT / revertir
def cuerpo_put(wf):
    body = {k: wf[k] for k in A.PUT_KEYS if k in wf}
    body["settings"] = {k: v for k, v in (wf.get("settings") or {}).items() if k in A.SETTINGS_OK}
    return body


def norm(w):
    return {x["name"]: {k: x.get(k) for k in ("parameters", "type", "typeVersion", "credentials", "position", "disabled", "webhookId")} for x in w["nodes"]}


def guardar(ruta, obj):
    """ÚNICO punto que escribe backups en workflows/history/ (tests/test_dia1_segmentacion.py lo reemplaza para verificar el orden)."""
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    Path(ruta).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def correr_check_triaje():
    """check_triaje.py completo (regla 9: antes de cualquier PUT). True si dio sano."""
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "check_triaje.py")], cwd=ROOT).returncode == 0


def correr_test_migracion():
    """tests/test_migracion_contacto_tipos.mjs (PGlite, sin base real): la garantía de que 'prueba'/'dudoso'/sin tipo NO silencian,
    de que interno no tiene red y de que el SQL de los nodos da siempre 1 fila. Devuelve (ok, detalle)."""
    try:
        p = subprocess.run(["node", str(ROOT / "tests" / "test_migracion_contacto_tipos.mjs")], cwd=ROOT, capture_output=True,
                           text=True, encoding="utf-8", timeout=600)
    except Exception as e:
        return False, f"no se pudo correr: {str(e)[:160]}"
    ult = (p.stdout.strip().splitlines() or [""])[-1]
    if p.returncode == 0:
        return True, ult
    if re.search(r"\d+ OK, \d+ fallas", ult):
        return False, ult
    err = (p.stderr.strip().splitlines() or ["?"])[-1]
    return False, "no corrió (¿falta `npm install`? @electric-sql/pglite es devDependency): " + err[:160]


def ultimo_backup(tipo):
    cands = sorted(HIST.glob(f"{V6}_{tipo}_dia1_segmentacion_*.json"))
    return cands[-1] if cands else None


def bloque_gate_de_backups():
    """El bloque Seg tal como se aplicó, sacado del par PRE/POST del --apply (por si segmentacion/dia1/ cambió después)."""
    pre_f, post_f = ultimo_backup("PRE"), ultimo_backup("POST")
    if not (pre_f and post_f):
        return None
    try:
        g0 = A.por_nombre(json.loads(pre_f.read_text(encoding="utf-8")))[GATE]["parameters"]["jsCode"]
        g1 = A.por_nombre(json.loads(post_f.read_text(encoding="utf-8")))[GATE]["parameters"]["jsCode"]
        i = g0.index(ANCLA) + len(ANCLA)
        x = g1[i:i + len(g1) - len(g0)]
        return x if g0[:i] + x + g0[i:] == g1 and x else None
    except Exception:
        return None


def quitar_dia1(vivo, bloque=None):
    """Inversa QUIRÚRGICA de construir() sobre el workflow que esté vivo: saca los nodos Seg, devuelve los 2 arcos a su lugar y quita el
    bloque del Gate. Todo lo demás (cambios posteriores a otros nodos: v7, triaje, claves rotadas por PUT-A) queda como está.
    Devuelve (workflow, problemas); si hay problemas no devuelve workflow."""
    wf = copy.deepcopy(vivo)
    n, c = A.por_nombre(wf), wf["connections"]
    prob = []
    faltan = [k for k in NUEVOS if k not in n]
    if faltan:
        prob.append(f"faltan nodos del Día 1: {faltan}")
    for k in (LIMPIAR, LOOP, TAKEOVER, TYPING, GATE):
        if k not in n:
            prob.append(f"falta {k}")
    if prob:
        return None, prob
    entran = sorted((s_, i) for (s_, _t, i, d, _x) in A.arcos(c) if d in NUEVOS and s_ not in NUEVOS)
    if entran != sorted([(LIMPIAR, 0), (LOOP, 1)]) or main_de(c, LIMPIAR, 0) != [(N_TIPO, 0)] or main_de(c, LOOP, 1) != [(N_SAL, 0)]:
        prob.append(f"a lo nuevo no se entra solo por Buffer: Limpiar[0] y Loop Mensajes[1] ({entran})")
    salen = {(s_, d) for (s_, _t, _i, d, _x) in A.arcos(c) if s_ in NUEVOS and d not in NUEVOS}
    if salen != {(N_SIL, TAKEOVER), (N_SAL, TYPING)}:
        prob.append(f"de lo nuevo al v6 salen arcos distintos de los del Día 1 ({sorted(salen)})")
    g = n[GATE]["parameters"].get("jsCode", "")
    cands = [b for b in (src("gate_humano_final_bloque.js"), bloque) if b and g.count(ANCLA + b) == 1]
    if not cands:
        prob.append("Gate Humano Final no tiene el bloque Seg tal como se aplicó (¿otro PUT lo tocó?)")
    if prob:
        return None, prob
    n[GATE]["parameters"]["jsCode"] = g.replace(ANCLA + cands[0], ANCLA)
    wf["nodes"] = [x for x in wf["nodes"] if x["name"] not in NUEVOS]
    for k in NUEVOS:
        c.pop(k, None)
    c[LIMPIAR]["main"][0] = [A.arco(TAKEOVER)]
    c[LOOP]["main"][1] = [A.arco(TYPING)]
    refs = [x["name"] for x in wf["nodes"] if "Seg: " in json.dumps(x.get("parameters", {}), ensure_ascii=False)
            or "seg:off" in json.dumps(x.get("parameters", {}), ensure_ascii=False)]
    if refs:
        return None, [f"después de quitar, estos nodos todavía nombran la segmentación: {refs}"]
    return wf, []


def verificar_quitado(vivo, quitado):
    r = []
    chk = lambda ok, txt: r.append([bool(ok), txt])
    vn, qn = A.por_nombre(vivo), A.por_nombre(quitado)
    chk(not any(k.startswith("Seg:") for k in qn), "sin nodos 'Seg:'")
    chk(set(vn) - set(qn) == set(NUEVOS) and set(qn) <= set(vn), f"se quitan exactamente los {len(NUEVOS)} nodos del Día 1")
    cambiados = sorted(k for k in qn if norm({"nodes": [qn[k]]}) != norm({"nodes": [vn[k]]}))
    chk(cambiados == [GATE], f"de los nodos que quedan solo cambia Gate Humano Final (cambiados: {cambiados})")
    chk(colapsar(vivo["connections"]) == A.arcos(quitado["connections"]),
        "las conexiones resultantes son las del vivo con los nodos Seg colapsados (el camino de un teléfono sin tipo, intacto)")
    chk(any(x.get("webhookId") == "evo-webhook-v2" for x in quitado["nodes"])
        and {x["name"]: x.get("webhookId") for x in quitado["nodes"] if x.get("webhookId")}
        == {x["name"]: x.get("webhookId") for x in vivo["nodes"] if x.get("webhookId") and x["name"] not in NUEVOS},
        "webhookIds conservados (evo-webhook-v2 incluido)")
    for ok_, t in chequear_grafo(quitado):
        chk(ok_, "check_triaje (grafo del revertido): " + t)
    return r


def revertir(aplicar, sin_check=False):
    vivo = A.api(f"/workflows/{V6}")
    print(f"v6 vivo: {len(vivo['nodes'])} nodos, versionId {str(vivo.get('versionId'))[:8]}")
    quitado, prob = quitar_dia1(vivo, bloque_gate_de_backups())
    if prob:
        sys.exit("ABORTO: el vivo no tiene el Día 1 tal como lo dejó este script: " + "; ".join(prob)
                 + "\n  Lo inmediato y sin PUT: --seg-off. Después revisar a mano.")
    if not resumen("REVERTIR (quirúrgico, sobre el GET de recién)", verificar_quitado(vivo, quitado)):
        sys.exit("ABORTO: la reversión propuesta no pasa sus chequeos. No se tocó nada.")
    pre_f = ultimo_backup("PRE")
    if pre_f:
        pre = json.loads(pre_f.read_text(encoding="utf-8"))
        dif = sorted(set(norm(quitado)) ^ set(norm(pre)) | {k for k in set(norm(quitado)) & set(norm(pre)) if norm(quitado)[k] != norm(pre)[k]})
        mismas = A.arcos(quitado["connections"]) == A.arcos(pre["connections"])
        print(f"\nContra el backup {pre_f.name}: " + ("IDÉNTICO (no hubo otros cambios después del Día 1)" if not dif and mismas else
              f"se CONSERVAN cambios posteriores al Día 1 en {dif[:12]}{' y en conexiones' if not mismas else ''} (no se pisan)"))
    if not aplicar:
        print("\n[SIMULACION] No se escribió nada. Para revertir (Lucas): python scripts/apply_dia1_segmentacion.py --revertir --apply"
              "\n  Más rápido y sin PUT: el interruptor seg:off (--seg-off).")
        return
    if not sin_check and not correr_check_triaje():
        sys.exit("ABORTO: check_triaje no dio sano (regla 9). Lo inmediato es seg:off (--seg-off). Si lo que falla es justamente el Día 1 y"
                 " Lucas lo decide: --revertir --apply --sin-check-triaje.")
    vivo2 = A.api(f"/workflows/{V6}")
    if vivo2.get("versionId") != vivo.get("versionId"):
        sys.exit("ABORTO: el v6 cambió mientras preparaba la reversión (versionId distinto). Volver a correr. No se tocó nada.")
    ts = int(time.time())
    guardar(HIST / f"{V6}_PRE_revertir_dia1_{ts}.json", vivo2)
    A.api(f"/workflows/{V6}", method="PUT", payload=cuerpo_put(quitado))
    post = A.api(f"/workflows/{V6}")
    guardar(HIST / f"{V6}_POST_revertir_dia1_{ts}.json", post)
    ok = norm(post) == norm(quitado) and A.arcos(post["connections"]) == A.arcos(quitado["connections"]) and post.get("active") is True
    print(("✅ revertido: nodos y conexiones == lo propuesto, v6 activo" if ok else "❌ el GET posterior no coincide con lo propuesto: revisar YA"))


def seg_cmd(accion):
    rc = f"docker exec {A.REDIS_CONTENEDOR} redis-cli"
    print("El Redis del bot no es accesible desde afuera: se hace en el VPS (SSH), a mano. No hace falta PUT.\n")
    if accion == "off":
        print(f"  {rc} SET seg:off 1        # TODOS vuelven al comportamiento de hoy (sin silencio por tipo, sin red, sin bloqueo en la salida)")
        print(f"  {rc} GET seg:off          # debe decir \"1\"")
    elif accion == "on":
        print(f"  {rc} DEL seg:off          # la segmentación vuelve a regir (los tipos vigentes de contacto_roles silencian)")
        print(f"  {rc} EXISTS seg:off       # debe decir 0")
    else:
        print(f"  {rc} GET seg:off\n  {rc} TTL seg:falla        # >0: hubo un aviso técnico (contacto_ruta con error) en las últimas 6 h")
    print("\nseg:off NO es /bot off: /bot off apaga el bot para todos; seg:off solo desactiva la segmentación del Día 1.")


def e2e_on(tel, aplicar, permitir_otro=False):
    """Prueba de punta a punta (plan §2.6.4): marca el teléfono (por defecto SOLO el de Lucas) como proveedor con motivo prueba_e2e.
    p_confirmo_ficha=true porque su número tiene recordatorios. El cierre va en el MISMO turno con limpiar_numero_demo.py --seg."""
    tel = A.tel_ok(tel, permitir_otro)
    from apply_migracion_contacto_tipos import conectar
    c = conectar(solo_lectura=not aplicar)
    try:
        cur = c.cursor()
        cur.execute("select to_regprocedure('public.contacto_tipo_poner(text,text,text,text,text,text,text,uuid,boolean)') is not null")
        if not cur.fetchone()[0]:
            sys.exit("La migración no está aplicada (falta contacto_tipo_poner).")
        cur.execute("select public.contacto_ruta(%s)", (tel,))
        print(f"antes: {cur.fetchone()[0]}")
        if not aplicar:
            print("[SIMULACION] No se escribió nada. Para marcar (Lucas): python scripts/apply_dia1_segmentacion.py --e2e-on --apply")
            return
        cur.execute("select public.contacto_tipo_poner(%s, 'proveedor', 'prueba_e2e', 'lucas', 'script', null, 'Prueba E2E Dia 1', null, true)", (tel,))
        r = cur.fetchone()[0]
        c.commit()
        print(f"después: {r}")
    finally:
        c.close()
    print(f"\nCIERRE en el mismo turno (regla 9): python scripts/limpiar_numero_demo.py --phone {tel} --seg --borrar-logs --apply")


# ================================================================================================================ main
def resumen(titulo, lista):
    return A.resumen(titulo, lista)


def main(argv=None):
    ap = argparse.ArgumentParser(description="PUT-B Día 1: silencio por tipo de contacto + red de seguridad + seg:off en el v6.")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--ver-codigo", action="store_true")
    ap.add_argument("--revertir", action="store_true", help="quita lo del Día 1 sobre un GET nuevo (conserva cambios posteriores)")
    ap.add_argument("--sin-check-triaje", action="store_true", help="solo con --revertir --apply y si lo que falla es el Día 1 (decisión de Lucas)")
    ap.add_argument("--seg-off", action="store_true")
    ap.add_argument("--seg-on", action="store_true")
    ap.add_argument("--seg-status", action="store_true")
    ap.add_argument("--e2e-on", action="store_true", help="marca el celular de Lucas como proveedor (prueba_e2e)")
    ap.add_argument("--phone", default=A.TEL_LUCAS)
    ap.add_argument("--permitir-otro", action="store_true")
    a = ap.parse_args(argv)

    if a.seg_off or a.seg_on or a.seg_status:
        return seg_cmd("off" if a.seg_off else "on" if a.seg_on else "status")
    if a.e2e_on:
        return e2e_on(a.phone, a.apply, a.permitir_otro)
    if a.revertir:
        return revertir(a.apply, a.sin_check_triaje)

    v6, helper = leer(a.offline)
    print(f"v6 {V6}: active={v6.get('active')} nodos={len(v6['nodes'])} versionId={str(v6.get('versionId'))[:8]} updatedAt={v6.get('updatedAt')}")
    if not a.offline:
        DRY.mkdir(parents=True, exist_ok=True)
        (DRY / "v6.json").write_text(json.dumps(v6, indent=1, ensure_ascii=False), encoding="utf-8")
        (DRY / "helper.json").write_text(json.dumps(helper, indent=1, ensure_ascii=False), encoding="utf-8")
    db = None if a.offline else estado_db()
    pre_ok = prerrequisitos(v6, helper)
    if db is not None:
        print(f"\nBase (solo lectura): contacto_ruta {'OK' if db['ruta_ok'] else 'NO LISTA'} — {db['detalle']}"
              + ("" if db["ruta_ok"] else "\n  (para simular alcanza; el --apply la exige)"))
    if not resumen("PRERREQUISITOS (v6 vivo + helper notify-grupo)", pre_ok):
        sys.exit("ABORTO: falta un prerrequisito. No se construyó nada.")
    nuevo = construir(v6)
    if not a.offline:
        (DRY / "v6_POST_propuesto.json").write_text(json.dumps(nuevo, indent=1, ensure_ascii=False), encoding="utf-8")
    imprimir_diff(v6, nuevo, a.ver_codigo)
    ok_inv = resumen("INVARIANTES (sin tipo = v6 de hoy; incluye el grafo de check_triaje sobre el PROPUESTO)", invariantes(v6, nuevo))
    ok_pru = resumen("PRUEBAS OFFLINE (JS real de los nodos en tests/harness_code_node.mjs)", pruebas_offline(v6, nuevo))
    ok_mig, det_mig = correr_test_migracion()
    print(f"\n=== TEST DE LA MIGRACIÓN (PGlite): {'✅' if ok_mig else '❌'} {det_mig} ===")
    if not (ok_inv and ok_pru):
        sys.exit("ABORTO: invariantes o pruebas en rojo. No se aplica.")
    if not a.apply:
        print(f"\n[SIMULACION] No se escribió nada en n8n. JSON vivo y propuesto en {DRY.relative_to(ROOT) if DRY.is_relative_to(ROOT) else DRY}/ (ignorado por git).")
        print("Para aplicar (Lucas, después de la migración): python scripts/apply_dia1_segmentacion.py --apply")
        return
    if a.offline:
        sys.exit("--apply no se puede con --offline.")
    if not (db and db["ruta_ok"]):
        sys.exit("ABORTO: public.contacto_ruta no existe o no responde. Primero: python scripts/apply_migracion_contacto_tipos.py --apply")
    if not ok_mig:
        sys.exit("ABORTO: el test de la migración (PGlite) no dio verde. No se tocó nada.")
    print("\n1) check_triaje (regla del proyecto: antes de cualquier PUT al v6)")
    if not correr_check_triaje():
        sys.exit("ABORTO: check_triaje no dio sano. No se tocó nada.")
    print("2) re-GET: el v6 no cambió desde la simulación")
    v6b, helperb = leer()
    if v6b.get("versionId") != v6.get("versionId") or not all(ok for ok, _ in prerrequisitos(v6b, helperb)):
        sys.exit("ABORTO: el v6 o el helper cambiaron mientras preparaba el PUT. Volver a simular. No se tocó nada.")
    if not all(ok for ok, _ in chequear_grafo(nuevo)):
        sys.exit("ABORTO: el grafo PROPUESTO no pasa los chequeos de check_triaje. No se tocó nada.")
    ts = int(time.time())
    pre = HIST / f"{V6}_PRE_dia1_segmentacion_{ts}.json"
    guardar(pre, v6b)
    print(f"3) backup PRE: workflows/history/{pre.name}")
    A.api(f"/workflows/{V6}", method="PUT", payload=cuerpo_put(nuevo))
    print("4) PUT hecho")
    post = A.api(f"/workflows/{V6}")
    guardar(HIST / f"{V6}_POST_dia1_segmentacion_{ts}.json", post)
    print(f"5) backup POST: workflows/history/{V6}_POST_dia1_segmentacion_{ts}.json")
    lista = invariantes(v6b, post)
    lista.append([norm(post) == norm(nuevo), "nodos del GET POST == nodos propuestos"])
    lista.append([A.arcos(post["connections"]) == A.arcos(nuevo["connections"]), "conexiones del GET POST == propuestas"])
    lista.append([post.get("active") is True, "v6 sigue activo"])
    if not resumen("6) VERIFICACIÓN POST-PUT", lista):
        sys.exit("ATENCION: la verificación no dio lo esperado. Lo inmediato: --seg-off. Revertir: python scripts/apply_dia1_segmentacion.py --revertir --apply")
    print("\n7) check_triaje otra vez, ahora sobre el v6 NUEVO (grafo, contacto_ruta y ejecuciones con error)")
    if not correr_check_triaje():
        sys.exit("ATENCION: check_triaje no da sano con el v6 nuevo. Lo inmediato: --seg-off. Revertir: --revertir --apply")
    print("\nAplicado. Con contacto_roles vacía nada cambia para nadie. Siguiente: T0 sin tipo; --e2e-on y prueba de punta a punta;"
          " limpieza con limpiar_numero_demo.py --seg en el mismo turno; correr check_triaje de nuevo después de T0.")
    print("Volver atrás: sin PUT → --seg-off ; con PUT → --revertir --apply")


if __name__ == "__main__":
    main()
