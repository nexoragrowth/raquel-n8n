# Patrones de inserción/aplicación de cambios al v6 (base para `apply_triaje_fase2_piloto.py`)

Fuente: `c:/Users/not/Desktop/proyectos/raquel-n8n/workflows/current/v6_LIVE.json` (snapshot de HOY 2026-09-04 10:26 local, 125 nodos, `active=True`, bajado con `scripts/snapshot_v6_live.py`), scripts en `scripts/`, memoria en `memory/`. Todo solo lectura; ningún valor de apikey/token se copia acá.

---

## 0. Contexto que condiciona la Fase 2 (memoria)

- `memory/current-state.md` (sesión 2026-09-04, arriba de todo): "el v6 cambió hoy 13:22 UTC (otra sesión) — el script de aplicación debe trabajar sobre GET fresco". Es decir: el script NO debe partir de `v6_LIVE.json`, debe hacer `GET /workflows/O155MqHgOSaNZ9ye` en el momento de aplicar y validar las conexiones esperadas antes de reconectar (patrón `apply_canned_sidecar.py`).
- `memory/decisions.md` 2026-09-04: Fase 2 = piloto **alambre_pincha** con sus 2 videos reales; textos borrador en tabla de config editable **`triaje_videos`** (otros 3 tipos `activo=false`); reglas que NO cambian: "texto al paciente 100% canned, LLM solo clasifica, gate determinístico de red flags antes, fail-closed a la escalación actual, diff + backup antes del PUT, webhookId preservado". La tabla `triaje_videos` **NO tiene DDL en el repo todavía** (solo se menciona en `decisions.md`; `rebuild_v3_schema.sql` no la tiene).
- Decisiones 2026-09-02: sin vision (foto solo respaldo), aviso pasivo cuando resuelve con video, rollout sombra → piloto 1 tipo → 4 tipos; hosting Supabase Storage público, n8n pasa URL a `POST /send/media`.
- Sombra (Fase 1) ya activa como satélite `Áurea — Triaje Urgencias (sombra)` (`Gm7ofyGohOJ2bI44`), tabla `triaje_urgencias_log` creada, gate 29/29 tests.

---

## 1. Patrón GET → build → backup PRE → PUT → backup POST → verify

### 1.1 `scripts/apply_add_kb_horarios_precio_dinamico.py` (nodos nuevos + prompt) — código literal

Env y constantes (idénticas en todos los `apply_*.py` de agosto):
```python
BASE = (os.environ.get("N8N_API_BASE") or "").rstrip("/")
KEY = os.environ.get("N8N_API_KEY") or ""
WF = os.environ.get("N8N_WF_BOT", "O155MqHgOSaNZ9ye")

PUT_KEYS = ("name", "nodes", "connections", "settings", "staticData")
SETTINGS_OK = {
    "saveExecutionProgress", "saveManualExecutions", "saveDataErrorExecution",
    "saveDataSuccessExecution", "executionTimeout", "errorWorkflow", "timezone",
    "executionOrder", "callerPolicy", "callerIds",
}
PG_CRED = {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}
```
OJO env: el `.env` del repo define `N8N_BASE_URL`, `N8N_API_KEY`, `N8N_WORKFLOW_V6_ID` (NO `N8N_API_BASE` ni `N8N_WF_BOT`). Los scripts de agosto dependen de que `N8N_API_BASE` esté exportado en la shell. El patrón más nuevo y robusto es el de `apply_canned_sidecar.py` / `apply_gate_pago_tratamiento.py`:
```python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib_env import env, require   # scripts/lib_env.py: lee .env de la raíz del repo, fallback a os.environ
WF_ID = env("N8N_WORKFLOW_V6_ID", "O155MqHgOSaNZ9ye")
def api(path, method="GET", payload=None):
    base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
    key = require("N8N_API_KEY")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{base}/api/v1{path}", data=data, method=method,
        headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())
```
(Los satélites `create_*.py` usan en cambio un loader inline sobre `[".env", "panel/.env.local"]` con `os.environ.setdefault`, y `BASE = N8N_API_BASE or N8N_BASE_URL`.)

`api()` versión agosto:
```python
def api(method, path, body=None):
    if not BASE or not KEY:
        sys.exit("!! Faltan N8N_API_BASE / N8N_API_KEY en el entorno.")
    req = urllib.request.Request(
        f"{BASE}/api/v1{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json", "accept": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def clean_settings(wf):
    s = wf.get("settings") or {}
    return {k: v for k, v in s.items() if k in SETTINGS_OK}

def get_sm(node):
    opts = node["parameters"].get("options", {})
    return opts.get("systemMessage", node["parameters"].get("systemMessage", ""))

def set_sm(node, value):
    if "options" in node["parameters"]:
        node["parameters"]["options"]["systemMessage"] = value
    else:
        node["parameters"]["systemMessage"] = value
```

Flujo `main()`:
```python
wf = api("GET", f"/workflows/{WF}")
print(f"  {wf['name']} — {len(wf['nodes'])} nodos, activo={wf['active']}")
wf_orig = copy.deepcopy(wf)          # <- lo que se guarda como backup PRE
already = any(x["name"] == NODE_PG for x in wf["nodes"])   # idempotencia por nombre de nodo
... (edita prompts con count()==1, imprime diff +/-)
if not args.apply:
    print("\n(preview — no se tocó n8n). Para aplicar: --apply"); return
```
Nodos nuevos (ids = slugs legibles, NO uuid; n8n los acepta; posiciones a mano):
```python
pg_node = {
    "parameters": {"operation": "executeQuery", "query": QUERY, "options": {}},
    "id": "get-kb-horarios-precio",
    "name": NODE_PG,
    "type": "n8n-nodes-base.postgres",
    "typeVersion": 2.5,
    "position": [2320, 900],
    "credentials": {"postgres": PG_CRED},
}
code_node = {
    "parameters": {"jsCode": CODE},
    "id": "extraer-horarios-precio",
    "name": NODE_CODE,
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [2540, 900],
}
wf["nodes"].append(pg_node); wf["nodes"].append(code_node)
```
Wiring ORIGINAL de este script (rama paralela — **fue el bug**, ver §3):
```python
conns = wf["connections"]
src = "Edit Fields - Extraer Datos"
branch = conns[src]["main"][0]
branch.append({"node": NODE_PG, "type": "main", "index": 0})
conns[NODE_PG] = {"main": [[{"node": NODE_CODE, "type": "main", "index": 0}]]}
```
Backup PRE / PUT / backup POST / verify:
```python
os.makedirs("workflows/history", exist_ok=True)
pre = "workflows/history/v6_PRE_add_kb_horarios_precio_dinamico.json"
json.dump(wf_orig, open(pre, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

body = {k: wf[k] for k in PUT_KEYS if k in wf}
body["settings"] = clean_settings(wf)
api("PUT", f"/workflows/{WF}", body)

vivo = api("GET", f"/workflows/{WF}")
post = "workflows/history/v6_POST_add_kb_horarios_precio_dinamico.json"
json.dump(vivo, open(post, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"activo={vivo['active']}  nodos={len(vivo['nodes'])} (antes {len(wf_orig['nodes'])})")
ok_pg = any(x["name"] == NODE_PG for x in vivo["nodes"])
ag2 = next((x for x in vivo["nodes"] if x["name"] == "Sub-Agent Agendar"), None)
ok_ag = "DINAMICO desde Conocimiento" in get_sm(ag2)   # marcador único del fix
```
**Preservación de `webhookId`**: ningún script lo toca explícitamente — la garantía es que el PUT manda `wf["nodes"]` tal cual vino del GET (mutado in-place / deepcopy), nunca una lista de nodos reconstruida. En el snapshot: nodo `Webhook - Evolution API` = `{"id": "***UUID***", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "webhookId": "evo-webhook-v2", "parameters": {"httpMethod": "POST", "path": "evolution-v2", "options": {}}}`. Recomendación para Fase 2: agregar un assert explícito pre-PUT `next(n for n in body["nodes"] if n["name"]=="Webhook - Evolution API")["webhookId"] == "evo-webhook-v2"`.

### 1.2 `scripts/apply_fix_kb_dinamico_wiring.py` — inserción EN LÍNEA entre `Parse Intent` y `Switch sobre Intent` (código literal)
```python
conns = wf["connections"]
# 1. Sacar la rama muerta
src_dead = "Edit Fields - Extraer Datos"
branch = conns[src_dead]["main"][0]
conns[src_dead]["main"][0] = [e for e in branch if e["node"] != NODE_PG]

# 2. Insertar en linea: Parse Intent -> NODE_PG -> NODE_CODE -> Switch sobre Intent
target_branch = conns["Parse Intent"]["main"][0]
targets = [e["node"] for e in target_branch]
if targets == [NODE_PG]:
    print("Parse Intent ya apunta a la cadena nueva, no toco esa conexión.")
elif "Switch sobre Intent" in targets:
    conns["Parse Intent"]["main"][0] = [{"node": NODE_PG, "type": "main", "index": 0}]
    conns[NODE_PG] = {"main": [[{"node": NODE_CODE, "type": "main", "index": 0}]]}
    conns[NODE_CODE] = {"main": [[{"node": "Switch sobre Intent", "type": "main", "index": 0}]]}
else:
    sys.exit(f"!! 'Parse Intent' no apunta a 'Switch sobre Intent' como se esperaba (apunta a {targets}), revisar a mano.")

# 3. Code node con merge explícito
NEW_CODE = """const rows = $input.all().map(i => i.json);
const original = $('Parse Intent').item.json;
...
return [{ json: { ...original, horarios, precio_consulta } }];
"""
```
Verificación post-PUT (chequea la cadena por índice):
```python
vconns = vivo["connections"]
ok1 = vconns.get("Parse Intent", {}).get("main", [[]])[0][0]["node"] == NODE_PG
ok2 = vconns.get(NODE_PG, {}).get("main", [[]])[0][0]["node"] == NODE_CODE
ok3 = vconns.get(NODE_CODE, {}).get("main", [[]])[0][0]["node"] == "Switch sobre Intent"
ok4 = "$('Parse Intent')" in code2["parameters"].get("jsCode", "")
```
Hubo un tercer script de seguimiento (`v6_PRE/POST_fix_kb_dinamico_id_string.json`): el nodo Postgres devuelve `id` como STRING → `String(r.id) === '20'` (comparar con número caía al fallback en silencio).

### 1.3 `scripts/apply_canned_sidecar.py` y `scripts/apply_gate_pago_tratamiento.py` (2-3/9) — el patrón MÁS RECIENTE y más defensivo (copiar este)
`build(wf)` puro (no muta, devuelve `(new, cambios)`), nodo posicionado relativo a upstream/downstream, idempotente por nombre, y **falla si la conexión esperada no es exactamente la que asume**:
```python
NODE_NAME = "Canned Sidecar"; UPSTREAM = "Fallback Output"; DOWNSTREAM = "Banlist Validator"
def build(wf):
    new = copy.deepcopy(wf); nodes = new["nodes"]; names = [n["name"] for n in nodes]; cambios = []
    if UPSTREAM not in names or DOWNSTREAM not in names:
        sys.exit(f"ERROR: falta {UPSTREAM!r} o {DOWNSTREAM!r} en el workflow")
    up = next(n for n in nodes if n["name"] == UPSTREAM); down = next(n for n in nodes if n["name"] == DOWNSTREAM)
    node = {"parameters": {"jsCode": SIDECAR_JS}, "id": "canned-sidecar-v1", "name": NODE_NAME,
            "type": "n8n-nodes-base.code", "typeVersion": 2,
            "position": [int((up["position"][0] + down["position"][0]) / 2), int(down["position"][1]) + 180]}
    if NODE_NAME in names:      # re-aplicar = solo actualizar jsCode, conservar id/position
        idx = names.index(NODE_NAME); prev = nodes[idx]
        node["position"] = prev.get("position", node["position"]); node["id"] = prev.get("id", node["id"]); nodes[idx] = node
        cambios.append(f"ACTUALIZA nodo existente {NODE_NAME!r} (solo el jsCode)")
    else:
        nodes.append(node); cambios.append(f"AGREGA nodo {NODE_NAME!r} (Code) en {node['position']}")
    conns = new["connections"]
    esperado = [{"node": DOWNSTREAM, "type": "main", "index": 0}]
    actual = conns.get(UPSTREAM, {}).get("main", [[]])[0]
    if [{"node": c["node"], "type": c["type"], "index": c["index"]} for c in actual] == esperado:
        conns[UPSTREAM]["main"][0] = [{"node": NODE_NAME, "type": "main", "index": 0}]
        conns[NODE_NAME] = {"main": [[{"node": DOWNSTREAM, "type": "main", "index": 0}]]}
        cambios.append(f"REWIRE {UPSTREAM} -> {NODE_NAME} -> {DOWNSTREAM}")
    elif conns.get(NODE_NAME):
        cambios.append("REWIRE ya estaba hecho (idempotente, no se toca)")
    else:
        sys.exit(f"ERROR: conexiones de {UPSTREAM!r} inesperadas: {actual!r}")
    return new, cambios
```
main(): GET → `build` → imprime CAMBIOS + `difflib.unified_diff` de `connections` filtradas a `(UPSTREAM, NODE_NAME)` → sin `--apply` = `[DRY-RUN]` → con `--apply`: backup PRE **con timestamp** `workflows/history/v6_PRE_canned_sidecar_{YYYYmmdd_HHMMSS}.json` (guarda `wf` original) → `payload = {k: new[k] for k in PUT_KEYS if k in new}; payload["settings"] = {k:v ... if k in SETTINGS_OK}` → `api(f"/workflows/{WF_ID}", method="PUT", payload=payload)` → GET `after` → backup POST `v6_POST_canned_sidecar_{ts}.json` → verificación:
```python
ok_node = any(n["name"] == NODE_NAME for n in after["nodes"])
ok_wire = after["connections"].get(UPSTREAM, {}).get("main", [[{}]])[0][0].get("node") == NODE_NAME
ok_down = after["connections"].get(NODE_NAME, {}).get("main", [[{}]])[0][0].get("node") == DOWNSTREAM
if not (ok_node and ok_wire and ok_down): sys.exit("ERROR: la verificacion post-PUT fallo — revisar en la UI")
```
`apply_gate_pago_tratamiento.py::build` hace lo mismo y ADEMÁS la edición de prompt en la misma función (capa 1 prompt + capa 2 nodo), con `position ... - 180` (arriba) en vez de `+ 180`. Nombres de backup reales en `workflows/history/`: `v6_PRE_gate_pago_tratamiento_20260904_102248.json` / `v6_POST_...` (170 archivos en total; convención `v6_PRE_<slug>[_ts].json` / `v6_POST_<slug>[_ts].json`; satélites: `triaje_sombra_CREADO_<id>.json`, `test_triaje_CREADO_<id>.json` con apikey redactado a `***REDACTED***`).

Tests del JS de nodos (fuente única): `tests/test_canned_sidecar.py` y `tests/test_gate_pago_tratamiento.py` importan `SIDECAR_JS`/`GATE_JS` del script `apply_*.py` y lo corren con `node` real vía un HARNESS que mockea `$input` (`{all, first}`), `$` (`(nombre) => ({first: () => ({json}), item: {json}})`, lanzando `No path back to referenced node` para nodos en `nodos_faltantes`) y `console`; usa `new AsyncFunction('$input', '$', 'console', body)`.

---

## 2. Patrón de edición de `systemMessage` (`apply_fix_router_continuacion_multi_pedido.py`, `apply_fix_subagent_general_os_carveout.py`)

```python
NODE = "Router - Clasificar Intent"          # o "Sub-Agent General"
ANCLA = ('- AI previo: "Que dia preferis?" en flujo CANCELAR -> "el viernes" -> ' "intent = `cancelar_o_reprogramar` (continuacion legitima).")
NUEVO_BLOQUE = ANCLA + "\n\n" + ("**EXCEPCION A LA EXCEPCION (NUEVO 2026-08-21, ...")

n = next((x for x in wf["nodes"] if x["name"] == NODE), None)
if not n: sys.exit(f"!! No encontré el nodo '{NODE}'.")
opts = n["parameters"].get("options", {})
old_sm = opts.get("systemMessage", n["parameters"].get("systemMessage", ""))

count = old_sm.count(ANCLA)
if count != 1:
    sys.exit(f"!! El ancla aparece {count} veces (esperaba 1), revisar a mano.")
if "EXCEPCION A LA EXCEPCION" in old_sm:          # marcador de idempotencia
    print(f"\n[{NODE}] ya tiene el fix."); return
new_sm = old_sm.replace(ANCLA, NUEVO_BLOQUE, 1)

for line in difflib.unified_diff(old_sm.splitlines(), new_sm.splitlines(), fromfile="ANTES", tofile="DESPUES", lineterm=""):
    if line.startswith(("+", "-")): print(line[:220])

if "options" in n["parameters"]: n["parameters"]["options"]["systemMessage"] = new_sm
else: n["parameters"]["systemMessage"] = new_sm
# ... --apply: backup PRE → PUT → GET → backup POST → verify: ok = "EXCEPCION A LA EXCEPCION" in sm2
```
Variante "reemplazo" (no append): `sm.replace(OLD, NEW, 1)` con `count == 0 and NEW in sm → ya aplicado`, `count != 1 → sys.exit` (`apply_gate_pago_tratamiento.py::build`, `apply_add_kb...` con lista `GENERAL_FIXES = [(old,new),...]`).

Detalles del prompt vivo que importan al reemplazar:
- Todos los agentes tienen `parameters.promptType = "define"`, `parameters.text = "={{ $('Preparar Mensaje Final').first().json.text }}"` (Router: `"=CONTEXTO DE LA CONVERSACION ...{{ $('Build Router Context').first().json.ctx || '(sin contexto)' }}\n\nMENSAJE ACTUAL DEL PACIENTE:\n{{ $('Preparar Mensaje Final').first().json.text }}"`), y `parameters.options.systemMessage` que **empieza con `=`** (es expresión; contiene `{{ $now.setZone('America/Argentina/Buenos_Aires')... }}`, `{{ $('Extraer Horarios y Precio').item.json.horarios }}`, `{{ $('Get Paciente Context').first().json.resumen_clinico || '...' }}`). Al reemplazar texto, conservar el `=` inicial y no romper `{{ }}`.
- `Sub-Agent Urgencia` systemMessage (len 9024) = header común (R0, IDENTIFICACION, MEMORIA, ..., VALIDACION DE DESTINO) + bloque final literal:
  ```
  **Sub-Agent Urgencia — funcion unica: ESCALAR**

  Tu unica funcion es derivar el caso a la doctora. No conversas, no diagnosticas, no das consejos (ni siquiera paliativos como cera o enjuagues), no recomendas medicacion.

  PASOS OBLIGATORIOS:
  1. Llamar `escalar_a_secretaria` con `query` = resumen breve (1-2 oraciones) del caso. Ej: "Paciente con dolor muela superior, pide medicacion. Coordinar turno urgente."
  2. Responder al paciente EXACTAMENTE:
     "Recibimos tu mensaje. Le pasamos a la doctora para que le coordine lo antes posible."

  PROHIBIDO ABSOLUTO:
  - Dar cualquier consejo médico u operativo (cera, enjuagues, "evita masticar")
  ...
  Si el paciente insiste tras escalar -> el label humaño ya esta aplicado. Devolver `[NO_REPLY]`.

  **REGLA CRITICA - UNA SOLA ESCALACION POR TURNO**: ... Responde el canned y FIN.
  ```
  Ese bloque es idéntico a `prompts/v6_partials/urgencia_funcion.md`. `scripts/build_prompts_v6.py --check` compara partials ensamblados vs vivo: si Fase 2 edita el prompt de Urgencia en n8n, hay que editar también el partial o `--check` reporta drift (y un `--apply` futuro lo pisaría).

---

## 3. Lecciones de `memory/current-state.md` que aplican a insertar una rama nueva

1. **"No path back to referenced node"** (sesión 2026-08-21 cont., líneas 336-345): el primer intento conectó los 2 nodos KB como rama paralela muerta desde `Edit Fields - Extraer Datos` "asumiendo que 'ejecutó antes en la misma corrida' alcanza para que `$('NodeName')` funcione desde otro nodo. NO alcanza: n8n necesita un camino CONECTADO real (pairedItem lineage). Confirmado con 2 ejecuciones reales que fallaron justo así (nodeCause: Extraer Horarios y Precio, lastNodeExecuted: Sub-Agent General)". Fix: insertar EN LÍNEA en un punto compartido por todos los sub-agents antes de bifurcar, con merge `{...$('Parse Intent').item.json, horarios, precio_consulta}` para no perder `intent`/`text`/`output` que el Switch necesita.
   - Matiz verificado en el snapshot: las referencias que fallaron usaban **`.item`** (`$('Extraer Horarios y Precio').item.json.horarios`, 14 refs). En cambio `Get Paciente Context` ES una rama muerta (`OUT: null`, entra solo desde `Edit Fields - Extraer Datos`) y `$('Get Paciente Context').first().json.resumen_clinico` se usa en producción desde los prompts de Sub-Agent Confirmar/Cancelar/Agendar (con `continueOnFail: true` + `alwaysOutputData: true` en el nodo). Regla segura para Fase 2: **insertar en línea Y referenciar con `.first()`** (es lo que usa el 90% del v6: `$('Preparar Mensaje Final').first().json.text/phone/remoteJid`, `$('Parse Intent').first().json.intent`, `$('Loop Mensajes').first().json.message`). El flujo es de 1 item por ejecución hasta `Split en Mensajes`.
2. **Referenciar nodos aguas arriba EXPLÍCITOS, no `$json` posicional** (sesión 2026-08-05/06, línea 891-894): `Evolution - Typing` y `Evolution API - Enviar Mensaje` leen `$('Loop Mensajes').first().json.X` "en vez de `$json.X` — no importa qué haga el nodo intermedio con su propio output". Idem `Gate Humano Final` lee `$('Preparar Mensaje Final')`/`$('Banlist Validator')`.
3. **`continueOnFail` / `onError` esconden fallas** (líneas 511-519 y 660-671): "Con `continueOnFail: true`, esto fallaría en silencio: el workflow reportaría 'success' pero CERO recordatorios saldrían" (jsonBody roto). Mapeo: 37 nodos con continueOnFail en 8 workflows; riesgo latente "el bot podría confirmarle un turno a un paciente que nunca se creó". Para el nodo `/send/media` de Fase 2: no fiarse de continueOnFail; usar `options.response.response.neverError: true` + inspeccionar la respuesta (`data.Info.Type === "VideoMessage"`) y hacer fail-closed a la escalación si no vino.
4. **JSON body** (líneas 660-671 + comentario en `create_test_triaje_webhook.py`): `{{ JSON.stringify($json.message) }}` **sin comillas propias** alrededor (saltos de línea reales rompen el JSON); JSON.stringify POR CAMPO dentro de un template armado a mano, no un `JSON.stringify({...})` del objeto entero ("ese patron corrompia tildes (Ã³ en vez de ó)").
5. **El nodo de envío Evolution procesa 1 solo item por corrida** (`decisions.md` 2026-07-21, commit 1886650): por eso existe `Loop Mensajes` (splitInBatches v3, `batchSize: 1`) con ciclo `Evolution API - Enviar Mensaje → Loop Mensajes`. "Cualquier nodo de Evolution API que deba procesar N items necesita un loop de a 1". `Es primer mensaje?` y `Delay Humano` quedaron **huérfanos** (IN: None) y n8n lo tolera.
6. **Heurística sobre datos que no son lo que dijo el paciente = falsos positivos** (lección "blindaje tarde" 18/8, guardrails del sidecar): inspeccionar `$('Preparar Mensaje Final').first().json.text` real, por oración, solo pedido explícito; `[NO_REPLY]` y `intent === 'urgencia_dolor'` → passthrough.
7. **El gate de red flags solo dentro del camino de urgencias** (`triaje/gate_red_flags.js` header + retrospectiva): "fiebre" apareció en una cancelación (#17) → corriendo global daría falsos positivos.
8. **Postgres devuelve ids como string** → `String(r.id) === '20'`.
9. **Verificar con la prueba que importa, no con el diff** (21/8): cambiar valor en KB y ver que el bot lo dice; datos de prueba limpiados de `n8n_chat_histories`/`conversaciones`/`pacientes`. Para Fase 2: E2E con teléfono de prueba (`tests/test_e2e_bateria.py` manda desde el admin Lucas `5491161461034` y espera regexes).

---

## 4. Configuración exacta de nodos existentes (para clonar)

### 4.1 httpRequest → Evolution GO (typeVersion **4.2** los 3)
**`Evolution API - Enviar Mensaje`** (id `***UUID***`, pos `[15920, 304]`, sin `onError`/`continueOnFail`, **sin key `options`**, `"credentials": {}`):
```json
"parameters": {
  "method": "POST",
  "url": "https://evo.raquelrodriguez.com.ar/send/text",
  "sendHeaders": true,
  "headerParameters": {"parameters": [
    {"name": "apikey", "value": "<apikey presente, valor omitido>"},
    {"name": "Content-Type", "value": "application/json"}
  ]},
  "sendBody": true,
  "specifyBody": "json",
  "jsonBody": "={\n  \"number\": {{ JSON.stringify($('Loop Mensajes').first().json.remoteJid ? $('Loop Mensajes').first().json.remoteJid.replace(/[^0-9]/g, \"\") : \"\") }},\n  \"text\": {{ JSON.stringify($('Loop Mensajes').first().json.message) }}\n}"
}
```
**`HTTP Send Admin Confirm`** (id `http-send-admin`, pos `[2080, 352]`): idéntico salvo `jsonBody` = `"={\n  \"number\": {{ JSON.stringify($('Kill-switch Check').first().json.chatJid ? $('Kill-switch Check').first().json.chatJid.replace(/[^0-9]/g, \"\") : \"\") }},\n  \"text\": {{ JSON.stringify($('Build Redis Cmd').first().json.confirmText) }}\n}"`. Sin options, `credentials: {}`.
**`Evolution - Typing`** (id `078d3fc0-ccf2-41e5-af61-`, pos `[15632, 304]`, **`"continueOnFail": true, "onError": "continueRegularOutput"`** a nivel nodo): `url` `https://evo.raquelrodriguez.com.ar/message/presence`, mismos headers, `jsonBody` = `"={\n  \"number\": \"{{ $('Loop Mensajes').first().json.remoteJid ? $('Loop Mensajes').first().json.remoteJid.replace(/[^0-9]/g, \"\") : \"\" }}\",\n  \"state\": \"composing\"\n}"` (patrón viejo con comillas; sirve porque number no tiene saltos de línea).

Sin campo `instance` en el body: la instancia va implícita por el `apikey` (token por-instancia). Cómo obtener el apikey sin hardcodear (patrón `create_test_triaje_webhook.py::get_apikey_and_base` y `upload_urgencia_video_supabase.py`):
```python
node = next(n for n in wf["nodes"] if n.get("name") == "Evolution API - Enviar Mensaje")
params = node["parameters"]
apikey = next(h["value"] for h in params["headerParameters"]["parameters"] if h["name"].lower() == "apikey")
evo_base = params["url"].split("/send/")[0]     # -> https://evo.raquelrodriguez.com.ar
```
Para el nodo nuevo `/send/media` dentro del v6: `copy.deepcopy(enviar["parameters"]["headerParameters"])` del GET fresco → el script nunca contiene la clave y sigue la rotación. Patrón de body probado E2E (nodo `Enviar Video Real` del test webhook, workflow `ahJzS48esjdmD4GH`):
```python
"parameters": {
  "method": "POST", "url": "https://evo.raquelrodriguez.com.ar/send/media",
  "sendHeaders": True, "headerParameters": {"parameters": [...apikey, Content-Type...]},
  "sendBody": True, "specifyBody": "json",
  "jsonBody": ("={\n"
      '  "number": {{ JSON.stringify($json.numero) }},\n'
      '  "type": "video",\n'
      '  "url": {{ JSON.stringify($json.video_url) }},\n'
      '  "caption": {{ JSON.stringify($json.caption) }},\n'
      '  "filename": "test_triaje.mp4"\n'
      "}"),
  "options": {"response": {"response": {"neverError": True}}},
}
```
Respuesta OK: `200`, `data.Info.Type == "VideoMessage"`, `data.Info.ID`. Otros httpRequest del v6 con `options`: `Banlist Shadow - LLM` (OpenAI) `{"response": {"response": {"neverError": true}}}`; Chatwoot (`CW Search Contact`, `CW Get Conversations`, `CW Set Label humano`) `onError: "continueRegularOutput"`; `Chatwoot - Buscar Conversacion`/`Re-check Humano` `continueOnFail: true`.

### 4.2 Postgres (typeVersion **2.5**, credencial `{"postgres": {"id": "TpYhZX4UT61xAKSV", "name": "Postgres Supabase Nexora v3"}}` en los 7)
- `Get KB Horarios y Precio`: `{"operation": "executeQuery", "query": "SELECT id, contenido FROM knowledge_base WHERE id IN (20, 21) ORDER BY id;", "options": {}}` (query literal, sin `=`), sin flags.
- `Get Paciente Context`: `{"operation": "executeQuery", "query": "SELECT COALESCE(nombre,'') as nombre, COALESCE(resumen_clinico,'') as resumen_clinico, COALESCE(resumen_actualizado_at::text,'') as resumen_actualizado_at FROM pacientes WHERE telefono = $1 LIMIT 1;", "options": {"queryReplacement": "={{ $('Edit Fields - Extraer Datos').item.json.phone }}"}}` + `"alwaysOutputData": true, "continueOnFail": true`.
- Multi-parámetro: `Clear Old Memory` `queryReplacement: "={{ $json.session_phone }}, ={{ $json.is_stale_session }}"`; `Postgres - Save fromMe` `query: "INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)"`, `queryReplacement: "={{ $json.session_id }}, ={{ $json.message }}"` (**único patrón existente para escribir un turno AI a mano en la memoria** — `Build fromMe AI memory` arma `message = JSON.stringify({type:'ai', content, additional_kwargs:{source:'wa_outbound',...}, response_metadata:{}, tool_calls:[], invalid_tool_calls:[]})`).
- Query como expresión (satélite): `"query": "=" + SQL` con `{{ $json.horas }}` adentro; `"query": "={{ $json.sql }}"` para INSERT armado en Code.
- `PG - Delete NO_REPLY`: `onError: "continueRegularOutput"`, `queryReplacement: "={{ $('Preparar Mensaje Final').first().json.phone }}"`.

### 4.3 Code (typeVersion **2**, 27 nodos; ninguno declara `mode` en el v6 → default runOnceForAllItems; los satélites ponen `"mode": "runOnceForAllItems"` explícito)
Convenciones: `const items = $input.all();` / `$input.first().json`; `try { ... = $('Nodo').first().json.x } catch (e) { fallback }` cuando el nodo puede no haber corrido (camino `Set NO_REPLY`); `await this.helpers.httpRequest({method:'POST', url:'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo', qs:{phone, resumen[, silencioso:'true']}, json:true})` para escalar desde un Code (`Gate Error Tecnico`, `Gate Pago Tratamiento`, `Aviso humano tomo chat`, `Gate Humano Final`); `console.log('[TAG] ...')` para rastrear en la ejecución; devolver `{ json: { ...it.json, output: nuevo, marca: true } }` preservando campos.

### 4.4 IF / Switch / Set
- IF v2.2 (boolean): `{"conditions": {"options": {"caseSensitive": true, "leftValue": "", "typeValidation": "strict", "version": 2}, "conditions": [{"id": "c1", "leftValue": "={{ $json.gate_escala }}", "rightValue": true, "operator": {"type": "boolean", "operation": "true", "singleValue": true}}], "combinator": "and"}, "options": {}}`; string equals: `operator {"type": "string", "operation": "equals"}`. Salidas: index 0 = true, 1 = false. (IF v2 también presente: `Es cierre?`, `Necesita Formatting?` con `typeValidation: "loose"`.)
- `Switch sobre Intent` v3.2: 5 reglas `={{ $json.intent }}` equals → outputKey `confirmar`(0) / `cancelar`(1) / `urgencia`(2, `rightValue: "urgencia_dolor"`) / `agendar`(3) / `general`(4); `options: {"fallbackOutput": "extra", "renameFallbackOutput": "fallback"}` → salida 5 → `Sub-Agent General`.
- Set v3.4: `{"assignments": {"assignments": [{"id": "out", "name": "output", "value": "[NO_REPLY]", "type": "string"}]}, "options": {}}` (`Set NO_REPLY`).
- Redis v1 (cred `{"redis": {"id": "kdtSKwGbN1xAZeUh", "name": "Redis account"}}`): `get` con `propertyName` + `key`; `set` `key`/`value`; `incr` con `expire: true, ttl: 900`; `push` a lista `chat_buffer:<phone>` con `tail: true`.
- OpenAI cred: `{"openAiApi": {"id": "nYujqfon7GGDnJUO", "name": "OpenAi account"}}`; LMs: Router / Urgencia / General / Formatting = `gpt-5-mini` `{"reasoningEffort": "low"}`; Confirmar / Cancelar / Agendar = `gpt-5`.

---

## 5. typeVersions presentes, settings, webhookId

Top-level keys del GET: `updatedAt, createdAt, id, name, description, active, isArchived, nodes, connections, settings, staticData, meta, pinData, versionId, activeVersionId, versionCounter, triggerCount, shared, tags, activeVersion`. `name` = `Agente IA v6 — Multi-agent (Dra. Raquel)`, `staticData: null`, `meta: {"templateCredsSetupCompleted": true}`, `pinData: {}`, `tags: []`.

`settings` vivo: `{"executionOrder": "v1", "callerPolicy": "workflowsFromSameOwner", "availableInMCP": false, "binaryMode": "separate"}` → tras `clean_settings` queda `{"executionOrder": "v1", "callerPolicy": "workflowsFromSameOwner"}` (`availableInMCP` y `binaryMode` NO están en la allowlist y darían 400). **No hay `timezone`** en settings: los prompts usan `$now.setZone('America/Argentina/Buenos_Aires')`.

typeVersion por tipo (usar estas para nodos nuevos):
- `n8n-nodes-base.code` v2 (27) · `n8n-nodes-base.httpRequest` v4.2 (9) · `n8n-nodes-base.postgres` v2.5 (7) · `n8n-nodes-base.if` v2 (7) y v2.2 (6) · `n8n-nodes-base.set` v3.4 (9) · `n8n-nodes-base.switch` v3.2 (2) · `n8n-nodes-base.redis` v1 (7) · `n8n-nodes-base.noOp` v1 (5) · `n8n-nodes-base.merge` v3 (1) · `n8n-nodes-base.splitInBatches` v3 (1) · `n8n-nodes-base.wait` v1.1 (2) · `n8n-nodes-base.webhook` v2 (1) · `n8n-nodes-base.convertToFile` v1.1 (2) · `n8n-nodes-base.executeWorkflow` v1.2 (1) · `n8n-nodes-base.stickyNote` v1 (5) · `n8n-nodes-chatwoot.chatwoot` v1 (1)
- `@n8n/n8n-nodes-langchain.agent` v2.2 (6: Router + 5 sub-agents) y v1.8 (1: Formatting Agent) · `lmChatOpenAi` v1.2 (7) · `memoryPostgresChat` v1.3 (1) · `toolHttpRequest` v1.1 (12) · `toolWorkflow` v2.2 (1) · `openAi` v1.8 (2) · `embeddingsOpenAi` v1.2 (1) · `vectorStoreSupabase` v1.3 (1)
- Satélites creados el 3/9 usan además: `scheduleTrigger` v1.2, `respondToWebhook` v1.3.

`Webhook - Evolution API`: `webhookId: "evo-webhook-v2"`, `path: "evolution-v2"`, `httpMethod: POST`, typeVersion 2, id `***UUID***`, pos `[48, 464]`.

Flags a nivel nodo presentes: `continueOnFail` (Evolution API - Obtener Media/Imagen, Chatwoot - Buscar Conversacion, Check Session Age, Clear Old Memory, Get Paciente Context, Execute Sub-WF Cancelar, Re-check Humano), `alwaysOutputData: true` (Check Session Age, Clear Old Memory, Get Paciente Context, Execute Sub-WF Cancelar), `onError: "continueRegularOutput"` (Evolution - Typing, CW Search Contact, CW Get Conversations, CW Set Label humano, PG - Delete NO_REPLY, Build Router Context).

---

## 6. Código reutilizable tal cual para Fase 2

### 6.1 Gate — `triaje/gate_red_flags.js`
Exporta `gateRedFlags(texto) → {escala: boolean, flags: string[]}`; flags: `trauma, sangrado_abundante, tragado, hinchazon, respirar_tragar, fiebre, dolor_intenso`; límites Unicode `B0 = "(?<![\\p{L}\\p{N}])"`, `B1 = "(?![\\p{L}\\p{N}])"`, flag `iu` (no `\b`); `.normalize("NFC")`. Termina en `if (typeof module !== "undefined") module.exports = { gateRedFlags, RED_FLAGS };` — ya embebido así en n8n con éxito (exec 269428). Embebido: `GATE_NODE_CODE = GATE_JS + "\n\n" + wrapper` donde el wrapper es:
```js
const SYSTEM_PROMPT = <json.dumps(SYSTEM_PROMPT)>; const MODELO = "gpt-5-mini";
const gate = gateRedFlags(texto);
const llm_body = JSON.stringify({ model: MODELO, messages: [{role:'system', content: SYSTEM_PROMPT}, {role:'user', content: user}], response_format: { type: 'json_object' } });
return [{ json: { ...j, gate_escala: gate.escala, gate_red_flags: gate.flags, llm_body } }];
```
Tests: `node triaje/test_gate.js` (29/29). Regla: editar el .js y redesplegar, nunca editar en n8n.

### 6.2 Clasificador (httpRequest a OpenAI, no LangChain)
Nodo `Clasificar (gpt-5-mini)`: `{"method": "POST", "url": "https://api.openai.com/v1/chat/completions", "authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi", "sendBody": true, "specifyBody": "json", "jsonBody": "={{ $json.llm_body }}", "options": {"response": {"response": {"neverError": true}}, "timeout": 60000}}`, `credentials: {"openAiApi": OPENAI_CRED}`, typeVersion 4.2. SYSTEM_PROMPT (versión sombra, `create_triaje_sombra.py`): categorías `red_flag | alambre_pincha | bracket_suelto | alambre_girado | ligadura_pincha | otra_urgencia | no_urgencia`, "Sé conservador: si la información no alcanza ... usá 'otra_urgencia'", salida `{"tipo": "...", "red_flags": ["..."], "confianza": "alta|media|baja", "razon": "una oración"}`. La versión del test webhook (mensaje único, sin historial) omite `red_flags`. Parseo robusto: `JSON.parse(content.replace(/^```(json)?|```$/gm, '').trim())` con try/catch → `tipo = 'error_llm'`. En Fase 2 el input al LLM debería ser `$('Preparar Mensaje Final').first().json.text` (+ opcional `$('Build Router Context').first().json.ctx` para "mismo problema, segundo mensaje").

### 6.3 Decisión / mapping de video (`DECIDIR_CODE` del test webhook)
```js
const VIDEOS = { alambre_pincha: 'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion1.mp4' };
if (tipo === 'red_flag') → escalar; if (VIDEOS[tipo]) → { accion:'video', video_url, caption }; else → sin_video (en vivo ESCALA)
```
Caption borrador probado: `'Situación en el que un alambre se salió y está pinchando.\n\nOpción 1: colocate cera de ortodoncia en la punta del alambre para aliviar la molestia hasta coordinar un control.\n\n[PRUEBA — respondé "no funcionó" para ver la Opción 2]'`. Por decisión 4/9, en Fase 2 estos textos/URLs deben salir de la tabla `triaje_videos` (a crear) con `activo` por tipo.

### 6.4 Tabla `triaje_urgencias_log` (Supabase v3, DDL en `rebuild_v3_schema.sql` §8b y `scripts/create_triaje_urgencias_log_table.py`, conexión psycopg2 con `SUPABASE_DB_*` del `.env`)
Columnas: `id BIGSERIAL PK, escalacion_id BIGINT UNIQUE REFERENCES escalaciones_log(id) ON DELETE SET NULL (nullable), telefono, exec_id, escalacion_created_at TIMESTAMPTZ, motivo_bot, mensaje_paciente, gate_red_flags JSONB DEFAULT '[]', gate_escala BOOLEAN DEFAULT FALSE, tipo, confianza, razon, modelo, modo TEXT DEFAULT 'sombra' (sombra|piloto|live), accion TEXT DEFAULT 'escalado' (escalado|video), video_enviado TEXT, created_at DEFAULT NOW()`; índices `idx_triaje_created`, `idx_triaje_tipo`. INSERT reutilizable (`INSERT_CODE`): helper `const esc = (v) => v === null || v === undefined ? 'NULL' : "'" + String(v).replace(/'/g, "''") + "'";`, flags unidas `[...gate.map(f=>'gate:'+f), ...llm.map(f=>'llm:'+f)]`, `${esc(JSON.stringify(flags))}::jsonb`, `ON CONFLICT (escalacion_id) DO NOTHING`; nodo Postgres `"query": "={{ $json.sql }}"`. Para Fase 2 en línea: `escalacion_id` NULL cuando se manda video (UNIQUE permite múltiples NULL; el ON CONFLICT no aplica), `modo='piloto'`, `accion='video'`, `video_enviado=<url o 'alambre_pincha/opcion1'>`, `exec_id={{ $execution.id }}`. Lectura: `python scripts/ver_triaje_sombra.py --dias 7`.

### 6.5 Bucket y URLs
Bucket público `urgencias-videos` (Supabase Storage v3, proyecto `eoizfjsyejixjzwgzwkt`). Subidos y verificados (HEAD 200 + envío real 200 `VideoMessage`):
- `https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion1.mp4` (cera de ortodoncia, 3.9MB, H.264/AAC 720x1280)
- `https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion2.mp4` (reinsertar alambre con pinza, 5.1MB)
`scripts/upload_urgencia_video_supabase.py "<mp4>" "<tipo>/opcionN.mp4" [--send <numero>] [--caption]` (lee `V3_SUPABASE_URL`/`V3_SUPABASE_SERVICE_KEY` — nombres que NO coinciden con el `.env` del repo (`SUPABASE_V3_URL`/`SUPABASE_V3_SERVICE_ROLE_KEY`); vienen de `panel/.env.local`). Upload: `POST {SB_URL}/storage/v1/object/{BUCKET}/{path}` con `x-upsert: true`; bucket idempotente vía `GET/POST /storage/v1/bucket`.

### 6.6 Envío de video de prueba sin tocar el v6
`scripts/test_evo_go_send_video.py "<mp4>" "<numero>" ["caption"]` (base64 crudo en `url`) y `create_test_triaje_webhook.py` (workflow `Áurea — TEST Triaje (webhook aislado)`, id `ahJzS48esjdmD4GH`, `POST /webhook/test-triaje {"mensaje","numero"}`, `--update <id>` para re-PUT).

---

## 7. Mapa del camino de urgencia en el v6 vivo (dónde insertar)

```
Router - Clasificar Intent ──main[0]──> Parse Intent ──> Get KB Horarios y Precio ──> Extraer Horarios y Precio ──> Switch sobre Intent
Switch sobre Intent main[2] ("urgencia", intent == 'urgencia_dolor') ──> Sub-Agent Urgencia ──main[0]──> Fallback Output
Fallback Output ──> Canned Sidecar ──> Gate Pago Tratamiento ──> Banlist Validator ──main[0]──> [Re-check Humano, Banlist Shadow - Prep]
Re-check Humano ──> Hay humano ahora? ──> Humano aparecio? ──[0 true]──> Aviso humano tomo chat (fin) / ──[1 false]──> Necesita Formatting?
Necesita Formatting? ──[0 >80 chars y no NO_REPLY]──> Formatting Agent - WhatsApp ──> Split en Mensajes / ──[1]──> Split en Mensajes
Split en Mensajes ──> Gate Error Tecnico ──> Tiene respuesta? ──[0]──> Loop Mensajes ──main[1]──> Evolution - Typing ──> Gate Humano Final ──> Evolution API - Enviar Mensaje ──> Loop Mensajes
Tiene respuesta? ──[1 contiene NO_REPLY]──> PG - Delete NO_REPLY ──> Descartar [NO_REPLY]
```
- `Sub-Agent Urgencia` entradas: `Switch sobre Intent` main[2]; `LM Sub-Agent Urgencia` (ai_languageModel, gpt-5-mini); `Postgres Chat Memory` (ai_memory, `sessionKey = $('Preparar Mensaje Final').first().json.phone`, contextWindowLength 10); `escalar_a_secretaria` (ai_tool, toolHttpRequest POST `=https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo?phone={{ $('Edit Fields - Extraer Datos').first().json.phone }}` + query `resumen`). Salida: `Fallback Output` (7 entradas convergen ahí: 5 sub-agents + `Set NO_REPLY` + `Format Sub-WF Output`).
- `Parse Intent` jsCode: `const valid = ['confirmar_post_recordatorio','cancelar_o_reprogramar','urgencia_dolor','agendar_nuevo','consulta_general']; ... const text = $('Preparar Mensaje Final').first().json.text; return [{ json: { ...$input.first().json, intent, text } }];` → el item que llega a `Switch sobre Intent` (vía `Extraer Horarios y Precio`) trae `{output (del router), intent, text, horarios, precio_consulta}`.
- `Preparar Mensaje Final` produce `{phone, remoteJid, name, key_id, instance, text}` (text = mensajes del buffer unidos con `\n`). `Edit Fields - Extraer Datos` expone además `phone_last10, pushName, image_url ('image'|''), video_url ('video'|''), document_*, sticker_present, message_type, fromMe`.
- Contrato de salida que espera `Split en Mensajes`: item con `json.output` (string; `---` separa mensajes); él mismo arma `{message, remoteJid, phone, partIndex, totalParts}` leyendo `$('Preparar Mensaje Final')` y `$('Banlist Validator')`.
- Escalación/registro: `Helper - Notify Grupo` (`S5U6tSipzlgFHCkf`), webhook `notify-grupo` con qs `phone`, `resumen`, `silencioso` — `Log Escalacion` (escribe `escalaciones_log`) corre SIEMPRE; `Notify Grupo Send` se saltea si `silencioso=true` (decisions 2026-08-04). Eso implementa "aviso pasivo" sin nodos nuevos: POST con `silencioso:'true'` deja registro visible en `/aprendizaje` sin WhatsApp al grupo. `escalaciones_log` la lee la sombra por `e.telefono, e.motivo, e.exec_id, e.created_at`.
- Banlist (última línea): patrones relevantes para un caption canned: `/\baplic(á|a|ate|en|ense)\b/`, `/\bguard(á|a|alo|enlo|en|amos|en\s+la)\s+/`, `/\bsac(á|a|alo|en|amos)\s+(la|el)/`, `/\btom(á|a|alo|en|amos)\s+(\d|un|una|el|la|los|las|cada)/`, `/\benjuag(á|a|ate|en|ense)\b/`, `/\bno\s+te\s+preocup(es|és)\b/`, `/\bno\s+es\s+(nada\s+)?grave\b/`, `/\blo\s+antes\s+posible\b.{0,50}\b(cl[íi]nica|consultorio|aurea|áurea|venir)\b/`, `/\bbalcarce\s*(n[º°]?\s*)?37\b/`. El caption borrador ("colocate cera ... hasta coordinar un control") NO matchea ninguno; "aplicá cera", "sacá el alambre", "tomá un analgésico" SÍ serían baneados. Si el texto pasa por el pipeline normal, el Banlist lo reemplaza por el canned de derivación y marca `escalate_to_human: true`.

## KEY FACTS
- Snapshot v6_LIVE.json es de HOY (2026-09-04 10:26 local), 125 nodos, active=True; pero memoria dice que el v6 cambió hoy 13:22 UTC desde otra sesión: el script de Fase 2 debe hacer GET fresco y validar conexiones esperadas antes de reconectar (patrón apply_canned_sidecar.py build()).
- Patrón canónico de aplicación: GET -> copy.deepcopy(wf_orig) -> build (idempotente por nombre de nodo + marcador en prompt) -> diff/preview sin --apply -> backup PRE workflows/history/v6_PRE_<slug>_<YYYYmmdd_HHMMSS>.json -> PUT body={name,nodes,connections,settings,staticData} con settings filtrados por SETTINGS_OK -> GET -> backup POST -> verificación por nombre de nodo y por índice de conexión -> sys.exit si falla.
- settings vivo = {executionOrder:'v1', callerPolicy:'workflowsFromSameOwner', availableInMCP:false, binaryMode:'separate'}; availableInMCP y binaryMode deben filtrarse (no están en la allowlist del API). No hay timezone; staticData es null.
- webhookId 'evo-webhook-v2' vive en el nodo 'Webhook - Evolution API' (id ***UUID***, path evolution-v2); se preserva porque los scripts mutan wf['nodes'] del GET y nunca reconstruyen la lista — conviene agregar un assert explícito pre-PUT.
- Inserción EN LÍNEA (apply_fix_kb_dinamico_wiring.py): reemplazar conns[UP]['main'][idx] = [{node: NUEVO, type:'main', index:0}] y conns[NUEVO] = {'main': [[{node: DOWN, type:'main', index:0}]]}; el Code nuevo hace merge {...$('Parse Intent').item.json, campos} para no perder intent/text/output que el Switch necesita. Rama paralela muerta + referencia con .item -> 'No path back to referenced node' (2 ejecuciones reales fallidas).
- Matiz verificado: $('Get Paciente Context').first() se usa en producción desde 3 sub-agents aunque ese nodo es rama muerta (OUT null, continueOnFail+alwaysOutputData). Regla segura: insertar en línea Y referenciar con .first() (el 90% del v6 usa .first(); el flujo es 1 item hasta Split en Mensajes).
- Edición de systemMessage: leer con opts.get('systemMessage', parameters.get('systemMessage')), exigir ANCLA.count()==1, marcador de idempotencia, replace(ANCLA, NUEVO, 1), difflib de líneas +/-, escribir en parameters.options.systemMessage; el prompt vivo empieza con '=' (expresión) y contiene {{ }} — no romperlos. Si se edita Urgencia en n8n, actualizar también prompts/v6_partials/urgencia_funcion.md (build_prompts_v6.py --check detecta drift).
- Punto de inserción del triaje: 'Switch sobre Intent' main[2] (outputKey 'urgencia', rightValue 'urgencia_dolor') -> 'Sub-Agent Urgencia' -> 'Fallback Output'. El item en ese punto trae {output(router), intent, text, horarios, precio_consulta}. Texto real del paciente: $('Preparar Mensaje Final').first().json.text; phone/remoteJid del mismo nodo; contexto previo: $('Build Router Context').first().json.ctx.
- Nodos httpRequest Evolution GO: typeVersion 4.2, method POST, sendHeaders true, headerParameters [{apikey (valor omitido)}, {Content-Type: application/json}], sendBody true, specifyBody 'json', jsonBody template a mano con JSON.stringify POR CAMPO sin comillas alrededor, referencias explícitas $('Nodo').first().json.X, sin campo instance, credentials {}. 'Evolution API - Enviar Mensaje' no tiene options ni onError; 'Evolution - Typing' tiene continueOnFail:true + onError:'continueRegularOutput'.
- Para /send/media en el v6: clonar headerParameters de 'Evolution API - Enviar Mensaje' del GET fresco (deepcopy) — el apikey se extrae en caliente con next(h['value'] for h in params['headerParameters']['parameters'] if h['name'].lower()=='apikey'); base URL = params['url'].split('/send/')[0]. Body {number, type:'video', url:<https pública>, caption, filename}; respuesta OK data.Info.Type=='VideoMessage'. Usar options.response.response.neverError:true e inspeccionar la respuesta (fail-closed a escalación).
- Postgres v2.5 cred {id:'TpYhZX4UT61xAKSV', name:'Postgres Supabase Nexora v3'}; executeQuery; parámetros con $1 + options.queryReplacement '={{ ... }}, ={{ ... }}'; query como expresión '=' + SQL o '={{ $json.sql }}'; ids numéricos vuelven como string.
- Code v2 sin 'mode' en el v6 (satélites usan mode:'runOnceForAllItems'); escalación desde Code: await this.helpers.httpRequest({method:'POST', url:'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo', qs:{phone, resumen[, silencioso:'true']}, json:true}). 'Helper - Notify Grupo' (S5U6tSipzlgFHCkf) SIEMPRE loguea en escalaciones_log y solo salta el WhatsApp al grupo si silencioso=true -> mecanismo listo para el 'aviso pasivo' de la decisión 2 del 2/9.
- El nodo de envío Evolution procesa 1 item por corrida (lección 21/7): existe 'Loop Mensajes' (splitInBatches v3 batchSize 1) con ciclo Enviar -> Loop. 'Es primer mensaje?' y 'Delay Humano' son nodos huérfanos tolerados.
- IF v2.2 boolean: options {caseSensitive:true, leftValue:'', typeValidation:'strict', version:2}, operator {type:'boolean', operation:'true', singleValue:true}; salida 0=true, 1=false. Switch v3.2 con renameOutput/outputKey y fallbackOutput 'extra'.
- typeVersions disponibles: code 2, httpRequest 4.2, postgres 2.5, if 2/2.2, set 3.4, switch 3.2, redis 1, noOp 1, merge 3, splitInBatches 3, wait 1.1, webhook 2, agent 2.2 (Formatting 1.8), lmChatOpenAi 1.2, memoryPostgresChat 1.3, toolHttpRequest 1.1; satélites: scheduleTrigger 1.2, respondToWebhook 1.3. OpenAI cred {id:'nYujqfon7GGDnJUO', name:'OpenAi account'}; Redis cred {id:'kdtSKwGbN1xAZeUh', name:'Redis account'}.
- Reutilizable tal cual: triaje/gate_red_flags.js (gateRedFlags(texto) -> {escala, flags}; embebido como GATE_JS + wrapper; tests node triaje/test_gate.js 29/29), SYSTEM_PROMPT del clasificador de create_triaje_sombra.py (7 categorías, JSON {tipo, red_flags, confianza, razon}), nodo httpRequest OpenAI (authentication predefinedCredentialType, nodeCredentialType openAiApi, jsonBody ={{ $json.llm_body }}, neverError, timeout 60000), parseo JSON.parse(content.replace(/^```(json)?|```$/gm,'').trim()), INSERT_CODE con esc() y ::jsonb.
- Tabla triaje_urgencias_log ya existe (escalacion_id UNIQUE nullable FK, modo sombra|piloto|live, accion escalado|video, video_enviado TEXT). Tabla triaje_videos (decisión 4/9: textos/URLs editables, activo por tipo) NO tiene DDL en el repo todavía.
- Videos hospedados y verificados E2E: https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion1.mp4 (cera) y .../alambre_pincha/opcion2.mp4 (reinsertar con pinza); bucket público urgencias-videos. Caption borrador probado no dispara el Banlist; 'aplicá'/'sacá'/'tomá'/'enjuagá'/'guardá' sí.
- Router: intent urgencia_dolor es 'MAXIMA PRIORIDAD' y se asigna por palabras concretas (dolor específico, alambre/bracket roto, sangrado, hinchazón). 'Sub-Agent Urgencia' hoy prohíbe explícitamente 'cera' y solo escala; su prompt = prompts/v6_partials/urgencia_funcion.md.
- Memoria LangChain (n8n_chat_histories, sessionKey = phone) solo registra turnos de agentes: un video enviado por httpRequest no queda en memoria ni en 'conversaciones' (Logger lee de n8n_chat_histories) salvo que se inserte a mano con el patrón 'Postgres - Save fromMe' (INSERT ... VALUES ($1, $2::jsonb)).

## RISKS
- Trabajar sobre v6_LIVE.json en vez de GET fresco: el v6 cambió hoy 13:22 UTC desde otra sesión; un PUT con nodos viejos pisaría cambios ajenos. Exigir GET en el momento y abortar si las conexiones de 'Switch sobre Intent' main[2] / 'Sub-Agent Urgencia' no son exactamente las esperadas.
- Rama paralela muerta + referencia .item = 'No path back to referenced node' (ya pasó 2 veces). Insertar en línea entre Switch main[2] y Sub-Agent Urgencia (o entre Sub-Agent Urgencia y Fallback Output) y referenciar con .first().
- Si el camino de video NO converge a 'Fallback Output', se saltea Canned Sidecar, Gate Pago, Banlist Validator, Re-check Humano, Gate Humano Final y Postgres Chat Memory: el bot podría mandar video a un chat con label humano, y la memoria/Router no sabrían que se envió un video ('no funcionó' del paciente no tendría contexto). Si SÍ converge y el caption va como output, pasa por Banlist/Formatting/Split -> el caption se manda como /send/text y el video necesita un /send/media aparte (2 envíos, 1 item por corrida cada uno).
- Contradicción de capas: el prompt vivo de Sub-Agent Urgencia prohíbe cera/consejos; si el video se dispara antes del agente pero el agente igual corre, se duplica (canned 'Le pasamos a la doctora' + video) o se escala igual. Definir explícitamente si el agente corre en el camino video (probablemente no) y qué se persiste en memoria.
- Gate de red flags debe correr SOLO si intent === 'urgencia_dolor' (fiebre en cancelaciones = falso positivo real #17).
- continueOnFail/onError silencian fallas: un jsonBody roto en /send/media reportaría success sin enviar nada. Usar neverError + chequear data.Info.Type==='VideoMessage' y hacer fail-closed a la escalación normal (escalar_a_secretaria / notify-grupo) si falla.
- Banlist como última línea: cualquier caption/texto canned nuevo debe pasar por él o testearse contra sus regex (aplicá/sacá/tomá/enjuagá/guardá/no te preocupes/lo antes posible+clínica/balcarce 37). Si el texto pasa y matchea, se reemplaza por el canned de derivación (comportamiento correcto pero el video ya habría salido si se mandó antes).
- Settings: mandar availableInMCP/binaryMode en el PUT da 400 — filtrar con SETTINGS_OK. Cualquier key extra top-level también.
- Preservar webhookId 'evo-webhook-v2': no reconstruir la lista de nodos; assert explícito antes del PUT.
- Higiene de secretos: el apikey de Evolution vive en headerParameters de 3 nodos (copiar del GET, nunca hardcodear); el jsCode de 'Gate Humano Final' tiene un token de Chatwoot hardcodeado (no copiar ese patrón); los backups PRE/POST en workflows/history contienen esas claves (el repo ya lo hace así; el snapshot del test webhook los redacta a ***REDACTED*** — replicar la redacción si se agregan snapshots nuevos).
- Drift de prompts: si se edita el systemMessage de Sub-Agent Urgencia vía script, actualizar prompts/v6_partials/urgencia_funcion.md o build_prompts_v6.py --check reportará diferencia y un --apply futuro revertiría el cambio.
- Tabla triaje_videos no existe: el script de Fase 2 necesita DDL + seed (alambre_pincha activo con 2 URLs y caption; otros 3 tipos activo=false) ANTES del PUT, o el nodo Postgres que la lee fallará (y con continueOnFail fallaría en silencio).
- El camino 'Set NO_REPLY' llega a Fallback Output sin que corran Parse Intent/Extraer Horarios y Precio: cualquier nodo nuevo aguas abajo de Fallback Output debe envolver esas referencias en try/catch (patrón Canned Sidecar).
- Test E2E real manda WhatsApp al número admin (5491161461034) y deja filas en escalaciones_log/conversaciones/n8n_chat_histories que hay que limpiar con OK de Lucas (ya hay 4 filas pendientes de borrar: escalaciones_log 189/190, conversaciones 6006/6009).

## OPEN QUESTIONS
- ¿Dónde exactamente insertar el triaje: entre 'Switch sobre Intent' main[2] y 'Sub-Agent Urgencia' (gate + clasificador antes del agente, agente solo en rama escalar), o como reemplazo del agente para el tipo activo? La memoria pide 'fail-closed a la escalación actual', lo que sugiere la primera opción con IF: escala -> Sub-Agent Urgencia (sin cambios); video -> rama nueva.
- ¿Cómo se registra el envío de video en la memoria LangChain para que el Router entienda 'no funcionó' como continuación (Capa 5)? Única opción existente: INSERT manual en n8n_chat_histories (patrón 'Postgres - Save fromMe') con un content tipo '[VIDEO ENVIADO: alambre_pincha opcion1] <caption>'. ¿Y en triaje_urgencias_log con escalacion_id NULL?
- ¿La rama video converge a 'Fallback Output' (para heredar Re-check Humano / Gate Humano Final / Banlist) devolviendo output='[NO_REPLY]' después de mandar el media, o devuelve el caption como output y el video se manda aparte? Nota: output '[NO_REPLY]' dispara 'PG - Delete NO_REPLY' (borra el último AI '[NO_REPLY]' de la memoria — inofensivo si no existe).
- Estado del label humano: ¿el video debe respetar 'Humano aparecio?'/'Gate Humano Final' (label 'humano' en Chatwoot)? Si la rama es independiente hay que replicar el chequeo (o reusar $('Verificar Label Humano')/'Bot Activo?' que ya corrió aguas arriba).
- Opción 2 (reinsertar con pinza): ¿se manda solo si el paciente dice 'no funcionó' (requiere estado por teléfono: Redis key tipo triaje:<phone> o lectura de triaje_urgencias_log) o nunca en el piloto?
- ¿Aviso pasivo = POST a notify-grupo con silencioso:'true' (queda en escalaciones_log y en /aprendizaje, sin WhatsApp) además de la fila en triaje_urgencias_log? Eso reusa el helper existente sin nodos nuevos.
- Fraseo definitivo de preguntas guiadas y lista de red flags siguen pendientes de Raquel (open-questions.md); la decisión 4/9 usa borradores en triaje_videos — confirmar el esquema de esa tabla (tipo, activo, video_url_1/2, caption_1/2, pregunta_guiada, updated_at) antes de escribir el script.
- ¿Se deja el clasificador como httpRequest a OpenAI (determinístico, patrón sombra) o como nodo LangChain agent? El satélite ya probó httpRequest + response_format json_object con éxito.