# -*- coding: utf-8 -*-
"""
apply_agente_directrices_n8n.py — el bot lee las "directrices" editables desde el panel (2026-10-05).

Requiere que ya exista la tabla (scripts/apply_agente_directrices_db.py --apply): en --apply aborta si no esta,
porque la consulta nueva del bot la lee y fallaria para TODOS los pacientes.

QUE CAMBIA EN EL v6 (un solo PUT; 6 nodos editados + 2 nuevos):
 1. `Get KB Horarios y Precio` y `Get KB Datos Pago`: la consulta suma las filas `dir:<clave>` de agente_directrices.
 2. `Extraer Horarios y Precio`: expone `dir_menu_bienvenida` y `dir_notas` (con valor por defecto si faltan).
 3. `Gate Canned Directo`: un saludo solo ("hola", "buenas tardes"...) en una conversacion NUEVA se responde con el
    texto de `menu_bienvenida` tal cual, sin modelo (deterministico: lo que la Dra. escribe en el panel es lo que
    recibe el paciente). Si hay conversacion previa o no hay texto, sigue el camino de siempre (agente General).
 4. `Necesita Formatting?`: las respuestas fijas del anuncio y del menu NO pasan por el Formatting Agent (hoy lo
    reescribe y el texto enviado deja de ser el de la base: execs 294587, 294600, 294615).
 5. NODOS NUEVOS `Armar filas canned` + `Guardar canned en memoria` (rama lateral de `Es Canned Directo?`): las
    respuestas fijas (anuncio, menu, alias, baja) ahora se guardan en la memoria del chat. Antes no se guardaban:
    el panel no las mostraba y, si el paciente contestaba "2" al menu, el bot no sabia que se lo habia mandado.
    Falla en silencio (onError continuar) para no afectar nunca el envio.
 6. `Sub-Agent General`: la regla 1 usa `dir_menu_bienvenida` (mismo texto en el camino del modelo) y agrega el
    bloque "INSTRUCCIONES ADICIONALES DE LA CLINICA" cuando hay notas.

NO toca: credenciales, el resto de nodos, ni datos.

USO:
    python scripts/apply_agente_directrices_n8n.py            # simulacion (solo GET): muestra el diff
    python scripts/apply_agente_directrices_n8n.py --apply    # backup PRE + PUT + verificacion + backup POST

Regla del proyecto: NUNCA --apply sin OK explicito de Lucas. Despues: prueba real (saludo solo desde el numero de
prueba) y limpiar el numero (scripts/limpiar_numero_demo.py).
"""
import argparse, copy, difflib, json, re, sys, time, urllib.request, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env, require
from directrices_def import MENU_DEFAULT

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "workflows" / "history"
WF_ID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {"saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone", "executionOrder", "callerPolicy", "callerIds"}

# ---------------------------------------------------------------- consultas
Q_HORARIOS_VIEJA = "SELECT id, contenido FROM knowledge_base WHERE id IN (20, 21, 24, 25, 36, 39) ORDER BY id;"
Q_HORARIOS_NUEVA = ("SELECT id::text AS id, contenido FROM knowledge_base WHERE id IN (20, 21, 24, 25, 36, 39) "
                    "UNION ALL SELECT 'dir:' || clave AS id, valor AS contenido FROM agente_directrices "
                    "WHERE clave IN ('menu_bienvenida', 'notas_para_asiri') ORDER BY 1;")
Q_PAGO_VIEJA = "SELECT id, contenido FROM knowledge_base WHERE id IN (24, 40) ORDER BY id;"
Q_PAGO_NUEVA = ("SELECT id::text AS id, contenido FROM knowledge_base WHERE id IN (24, 40) "
                "UNION ALL SELECT 'dir:' || clave AS id, valor AS contenido FROM agente_directrices "
                "WHERE clave = 'menu_bienvenida' ORDER BY 1;")

# ---------------------------------------------------------------- Extraer Horarios y Precio
EXTRAER_RETURN_VIEJO = "pago_cuenta, pago_banco } }];"
EXTRAER_RETURN_NUEVO = "pago_cuenta, pago_banco, dir_menu_bienvenida, dir_notas } }];"
EXTRAER_MARCA = "\nreturn [{ json: { ...original, horarios,"
EXTRAER_SNIPPET = (
    "\n// Directrices editables desde el panel (tabla agente_directrices -> filas 'dir:<clave>'). Si faltan: valor por defecto.\n"
    "const DEFAULT_MENU = " + json.dumps(MENU_DEFAULT, ensure_ascii=False) + ";\n"
    "function dir(clave, fallback) {\n"
    "  const r = porId('dir:' + clave);\n"
    "  const v = r && r.contenido != null ? String(r.contenido).trim() : '';\n"
    "  return v || fallback;\n"
    "}\n"
    "const dir_menu_bienvenida = dir('menu_bienvenida', DEFAULT_MENU);\n"
    "const dir_notas = dir('notas_para_asiri', '');\n"
)

# ---------------------------------------------------------------- Gate Canned Directo
GATE_MARCA = "const mencionaAlias ="
GATE_SNIPPET = r"""// Saludo solo en una conversacion NUEVA -> menu de bienvenida editable desde el panel (agente_directrices).
// Deterministico: sale el texto tal cual, sin modelo ni reescritor. Con conversacion previa, o si la fila falta, sigue el flujo normal.
const SALUDOS_SOLOS = ['hola','holaa','holaaa','holis','buenas','buen dia','buenos dias','buenas tardes','buenas noches','que tal','como va','como andas','que onda'];
const tSaludo = t.replace(/[^a-z ]/g, ' ').replace(/\s+/g, ' ').trim();
let ctxPrevio = 'no-se';
try { ctxPrevio = String($('Build Router Context').first().json.ctx || '').trim(); } catch (e) { ctxPrevio = 'no-se'; }
const conversacionNueva = ctxPrevio === '' || ctxPrevio === '(sin contexto)';
if (SALUDOS_SOLOS.includes(tSaludo) && conversacionNueva) {
  const menuRow = $input.all().map(i => i.json).find(r => String(r.id) === 'dir:menu_bienvenida');
  if (menuRow && menuRow.contenido && String(menuRow.contenido).trim()) {
    return [{ json: {
      ...item.json,
      direct_canned: true,
      reason: 'menu_bienvenida',
      output: String(menuRow.contenido).trim()
    }}];
  }
}

"""

# ---------------------------------------------------------------- nodos nuevos
ARMAR_JS = r"""// Rama lateral de 'Es Canned Directo?': arma las 2 filas de memoria (paciente + respuesta fija) en formato LangChain.
const salida = $input.first().json;
const pm = $('Preparar Mensaje Final').first().json;
const respuesta = String(salida.output || '');
if (!pm.phone || !respuesta) return [];
return [{ json: {
  session_id: String(pm.phone),
  human_msg: JSON.stringify({ type: 'human', content: String(pm.text || ''), additional_kwargs: {}, response_metadata: {} }),
  ai_msg: JSON.stringify({ type: 'ai', content: respuesta, tool_calls: [], additional_kwargs: { source: 'canned', reason: String(salida.reason || '') }, response_metadata: {}, invalid_tool_calls: [] })
} }];
"""
GUARDAR_Q = "INSERT INTO n8n_chat_histories (session_id, message) VALUES ($1, $2::jsonb), ($1, $3::jsonb)"
GUARDAR_REPL = "={{ $json.session_id }}, ={{ $json.human_msg }}, ={{ $json.ai_msg }}"

# ---------------------------------------------------------------- Necesita Formatting?
COND_C4 = {
    "id": "c4-respuesta-fija-sin-reescritor",
    "leftValue": "={{ $('Gate Canned Directo').isExecuted && ['anuncio_instagram_kb40', 'menu_bienvenida'].includes($('Gate Canned Directo').first().json.reason) }}",
    "rightValue": "",
    "operator": {"type": "boolean", "operation": "false", "singleValue": True},
}

# ---------------------------------------------------------------- prompt del General
GENERAL_REGLA1_VIEJA = (
    'responde cordial brindando el menú de opciones (NUNCA escalar un saludo solo):\n'
    '   "¡Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel Rodríguez (Áurea Odontología Estética) 🤗\n\n'
    '¿En qué puedo ayudarte hoy? Podés elegir una opción:\n'
    '🦷 1. Información de tratamientos (Ortodoncia con brackets o alineadores invisibles, ortopedia facial)\n'
    '📅 2. Agendar un turno (Primera consulta o control)\n'
    '🔄 3. Consultar o reprogramar tu turno\n'
    '💳 4. Precios y formas de pago (Valor de consulta, cuotas, alias)\n'
    '📍 5. Ubicación y horarios de atención"\n\n'
)
GENERAL_REGLA1_NUEVA = (
    'responde con EXACTAMENTE este mensaje de bienvenida, sin cambiar nada (NUNCA escalar un saludo solo):\n'
    '   "{{ $(\'Extraer Horarios y Precio\').item.json.dir_menu_bienvenida }}"\n\n'
)
GENERAL_ESTILO_VIEJO = "\nESTILO Y TONO:\n"
GENERAL_ESTILO_NUEVO = (
    "\n{{ $('Extraer Horarios y Precio').item.json.dir_notas ? 'INSTRUCCIONES ADICIONALES DE LA CLÍNICA "
    "(nunca contradicen los límites médicos, el trato de usted ni las reglas anteriores):\\n' + "
    "$('Extraer Horarios y Precio').item.json.dir_notas + '\\n\\n' : '' }}ESTILO Y TONO:\n"
)

NODOS_EDITADOS = ["Get KB Horarios y Precio", "Get KB Datos Pago", "Extraer Horarios y Precio", "Gate Canned Directo",
                  "Necesita Formatting?", "Sub-Agent General"]
NODOS_NUEVOS = ["Armar filas canned", "Guardar canned en memoria"]
CONEXIONES_ESPERADAS = {"Es Canned Directo?", "Armar filas canned"}


def reemplazar_unico(texto, viejo, nuevo, donde):
    if texto.count(viejo) != 1:
        sys.exit(f"ABORTO: en {donde} la cadena a reemplazar aparece {texto.count(viejo)} veces (esperaba 1). "
                 "Otra sesion cambio el nodo: revisar a mano.")
    return texto.replace(viejo, nuevo)


def transformar_extraer(code):
    if "dir_menu_bienvenida" in code:
        sys.exit("ABORTO: 'Extraer Horarios y Precio' ya tiene las directrices (¿se aplico antes?).")
    code = reemplazar_unico(code, EXTRAER_RETURN_VIEJO, EXTRAER_RETURN_NUEVO, "Extraer Horarios y Precio")
    return reemplazar_unico(code, EXTRAER_MARCA, EXTRAER_SNIPPET + EXTRAER_MARCA, "Extraer Horarios y Precio")


def transformar_gate(code):
    if "SALUDOS_SOLOS" in code:
        sys.exit("ABORTO: 'Gate Canned Directo' ya tiene la regla del menu (¿se aplico antes?).")
    if "const item =" not in code or "const t = norm(text)" not in code:
        sys.exit("ABORTO: 'Gate Canned Directo' no tiene la estructura esperada (item / t). Revisar a mano.")
    return reemplazar_unico(code, GATE_MARCA, GATE_SNIPPET + GATE_MARCA, "Gate Canned Directo")


def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
                                 headers={"X-N8N-API-KEY": require("N8N_API_KEY"),
                                          "Content-Type": "application/json", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def backup(wf, label):
    HIST.mkdir(parents=True, exist_ok=True)
    dest = HIST / f"{WF_ID}_{label}_{int(time.time())}.json"
    dest.write_text(json.dumps(wf, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  backup: workflows/history/{dest.name}")


def redactar(s):
    return re.sub(r"(sb_secret_|eyJ)[A-Za-z0-9_\-\.]+", "<RED>", s)


def mostrar_diff(titulo, a, b, max_lineas=40):
    print(f"\n--- {titulo}")
    n = 0
    for l in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
        if l.startswith(("---", "+++", "@@")):
            continue
        n += 1
        if n <= max_lineas:
            print("   ", redactar(l)[:260])
    if n > max_lineas:
        print(f"    … ({n - max_lineas} lineas mas)")


def nodo(wf, nombre):
    n = next((n for n in wf["nodes"] if n["name"] == nombre), None)
    if not n:
        sys.exit(f"ABORTO: falta el nodo '{nombre}'.")
    return n


def preparar(wf):
    nuevo = copy.deepcopy(wf)
    # 1. consultas
    n = nodo(nuevo, "Get KB Horarios y Precio")
    if n["parameters"].get("query") != Q_HORARIOS_VIEJA:
        sys.exit("ABORTO: la consulta de 'Get KB Horarios y Precio' no es la esperada. Revisar a mano.")
    n["parameters"]["query"] = Q_HORARIOS_NUEVA
    mostrar_diff("1a · Get KB Horarios y Precio (consulta)", Q_HORARIOS_VIEJA, Q_HORARIOS_NUEVA)
    n = nodo(nuevo, "Get KB Datos Pago")
    if n["parameters"].get("query") != Q_PAGO_VIEJA:
        sys.exit("ABORTO: la consulta de 'Get KB Datos Pago' no es la esperada. Revisar a mano.")
    n["parameters"]["query"] = Q_PAGO_NUEVA
    mostrar_diff("1b · Get KB Datos Pago (consulta)", Q_PAGO_VIEJA, Q_PAGO_NUEVA)
    # 2. Extraer
    n = nodo(nuevo, "Extraer Horarios y Precio")
    viejo = n["parameters"]["jsCode"]
    n["parameters"]["jsCode"] = transformar_extraer(viejo)
    mostrar_diff("2 · Extraer Horarios y Precio", viejo, n["parameters"]["jsCode"])
    # 3. Gate
    n = nodo(nuevo, "Gate Canned Directo")
    viejo = n["parameters"]["jsCode"]
    n["parameters"]["jsCode"] = transformar_gate(viejo)
    mostrar_diff("3 · Gate Canned Directo", viejo, n["parameters"]["jsCode"], 30)
    # 4. Formatting
    n = nodo(nuevo, "Necesita Formatting?")
    conds = n["parameters"]["conditions"]["conditions"]
    if any(c.get("id") == COND_C4["id"] for c in conds):
        sys.exit("ABORTO: 'Necesita Formatting?' ya tiene la condicion nueva.")
    conds.append(COND_C4)
    print("\n--- 4 · Necesita Formatting? (condicion nueva, se suma con AND a las 3 existentes)\n    + " + COND_C4["leftValue"])
    # 5. nodos nuevos
    ref = nodo(nuevo, "Es Canned Directo?")
    cred = copy.deepcopy(nodo(nuevo, "Postgres - Save fromMe").get("credentials"))
    x, y = ref["position"]
    nuevo["nodes"].append({
        "id": str(uuid.uuid4()), "name": "Armar filas canned", "type": "n8n-nodes-base.code", "typeVersion": 2,
        "position": [x, y + 300], "parameters": {"jsCode": ARMAR_JS}, "onError": "continueRegularOutput",
    })
    nuevo["nodes"].append({
        "id": str(uuid.uuid4()), "name": "Guardar canned en memoria", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5,
        "position": [x + 260, y + 300], "credentials": cred, "onError": "continueRegularOutput",
        "parameters": {"operation": "executeQuery", "query": GUARDAR_Q, "options": {"queryReplacement": GUARDAR_REPL}},
    })
    c = nuevo["connections"]
    rama = c["Es Canned Directo?"]["main"][0]
    if any(t["node"] == "Armar filas canned" for t in rama):
        sys.exit("ABORTO: la rama lateral ya existe.")
    rama.append({"node": "Armar filas canned", "type": "main", "index": 0})
    c["Armar filas canned"] = {"main": [[{"node": "Guardar canned en memoria", "type": "main", "index": 0}]]}
    print("\n--- 5 · nodos nuevos (rama lateral, onError=continuar)")
    print(f"    Es Canned Directo? out0: {[t['node'] for t in rama]}")
    print("    Armar filas canned → Guardar canned en memoria")
    print(f"    SQL: {GUARDAR_Q}")
    # 6. prompt del General
    n = nodo(nuevo, "Sub-Agent General")
    viejo = n["parameters"]["options"]["systemMessage"]
    nv = reemplazar_unico(viejo, GENERAL_REGLA1_VIEJA, GENERAL_REGLA1_NUEVA, "Sub-Agent General (regla 1)")
    nv = reemplazar_unico(nv, GENERAL_ESTILO_VIEJO, GENERAL_ESTILO_NUEVO, "Sub-Agent General (estilo)")
    n["parameters"]["options"]["systemMessage"] = nv
    mostrar_diff("6 · prompt de Sub-Agent General", viejo, nv, 30)
    return nuevo


def verificar(antes, despues):
    a, d = {n["name"]: n for n in antes["nodes"]}, {n["name"]: n for n in despues["nodes"]}
    cambiados = sorted(k for k in a if a[k] != d.get(k))
    nuevos = sorted(set(d) - set(a))
    conex = sorted(k for k in set(antes["connections"]) | set(despues["connections"])
                   if antes["connections"].get(k) != despues["connections"].get(k))
    chequeos = {
        "solo cambiaron los 6 nodos previstos": cambiados == sorted(NODOS_EDITADOS),
        "solo se agregaron los 2 nodos nuevos": nuevos == sorted(NODOS_NUEVOS),
        "solo cambiaron las conexiones previstas": set(conex) == CONEXIONES_ESPERADAS,
        "no se quito ningun nodo": not (set(a) - set(d)),
        "webhookId evo-webhook-v2 intacto": d["Webhook - Evolution API"].get("webhookId") == "evo-webhook-v2",
        "workflow sigue activo": despues.get("active") is True,
        "arreglos del 05/10 siguen (Loop Mensajes / ver_turnos_paciente / gate 24h)": (
            despues["connections"]["Loop Mensajes"]["main"] == [[], [{"node": "Evolution - Typing", "type": "main", "index": 0}]]
            and any(c["node"] == "Sub-Agent Agendar" for c in despues["connections"]["ver_turnos_paciente"]["ai_tool"][0])
            and "human_takeover_at" in d["Gate Humano Final"]["parameters"]["jsCode"]),
    }
    ok = True
    for k, v in chequeos.items():
        print(f"  {'OK   ' if v else 'FALLA'} {k}" + ("" if v else f"  (cambiados={cambiados} nuevos={nuevos} conex={conex})"))
        ok &= v
    return ok


def tabla_existe():
    import psycopg2
    conn = psycopg2.connect(host=env("SUPABASE_V3_DB_HOST"), port=env("SUPABASE_V3_DB_PORT"), dbname=env("SUPABASE_V3_DB_NAME"),
                            user=env("SUPABASE_V3_DB_USER"), password=env("SUPABASE_V3_DB_PASSWORD"), sslmode="require", connect_timeout=10)
    try:
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('public.agente_directrices') IS NOT NULL")
        if not cur.fetchone()[0]:
            return False
        cur.execute("SELECT count(*) FROM public.agente_directrices WHERE clave IN ('menu_bienvenida','notas_para_asiri')")
        if cur.fetchone()[0] != 2:
            return False
        # Prueba de lectura (solo SELECT) de las DOS consultas nuevas: si alguna fallara, el bot fallaria con todos.
        cur.execute(Q_HORARIOS_NUEVA)
        ids_h = {str(r[0]) for r in cur.fetchall()}
        cur.execute(Q_PAGO_NUEVA)
        ids_p = {str(r[0]) for r in cur.fetchall()}
        if not {"20", "21", "24", "dir:menu_bienvenida", "dir:notas_para_asiri"} <= ids_h or not {"24", "40", "dir:menu_bienvenida"} <= ids_p:
            print(f"  consultas nuevas: ids devueltos horarios={sorted(ids_h)} pago={sorted(ids_p)}")
            return False
        print(f"  consultas nuevas OK: horarios={sorted(ids_h)} pago={sorted(ids_p)}")
        return True
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    wf = api(f"/workflows/{WF_ID}")
    print(f"v6 {WF_ID} | active={wf.get('active')} | {len(wf['nodes'])} nodos | versionId={wf.get('versionId')}")
    nuevo = preparar(wf)

    if not args.apply:
        print("\n[SIMULACION] No se aplico nada (ni se consulto la base). Correr con --apply (con OK de Lucas), "
              "DESPUES de scripts/apply_agente_directrices_db.py --apply.")
        return

    if not tabla_existe():
        sys.exit("ABORTO: la tabla agente_directrices no existe o le faltan filas. Correr primero "
                 "scripts/apply_agente_directrices_db.py --apply (si no, el bot falla para todos los pacientes).")
    if api(f"/workflows/{WF_ID}").get("versionId") != wf.get("versionId"):
        sys.exit("ABORTO: el workflow cambio mientras preparaba el fix (otra sesion hizo un PUT). Volver a correr.")

    backup(wf, "PRE_directrices")
    body = {k: nuevo[k] for k in PUT_KEYS if k in nuevo}
    body["settings"] = {k: v for k, v in (nuevo.get("settings") or {}).items() if k in SETTINGS_OK}
    api(f"/workflows/{WF_ID}", method="PUT", payload=body)
    post = api(f"/workflows/{WF_ID}")
    backup(post, "POST_directrices")
    if not verificar(wf, post):
        sys.exit("VERIFICACION FALLIDA: revisar ya. El backup PRE esta en workflows/history/ (restaurar con PUT).")
    print("\nAplicado. Falta la prueba real: un 'hola' desde el numero de prueba (conversacion nueva) debe devolver el "
          "texto de la directriz, sin pasar por el Formatting Agent, y quedar guardado en la memoria.")


if __name__ == "__main__":
    main()
