# Plan de conexión del v7 al v6 — solo celular de Lucas (flag Redis `v7:tel:{tel}`)

> Generado 2026-10-06 (noche) por 5 agentes sobre el v6 VIVO (`workflows/current/v6_LIVE_2026-10-06.json`, versionId 883a552b) y el v7 del repo; verificado por un revisor escéptico (sus objeciones están al final y MANDAN sobre el plan). NADA aplicado. Implementación: `scripts/apply_v7_flag_lucas.py` con dry-run/diff/backup PRE-POST y OK de Lucas antes del PUT.


> **Nota de la sesión nube (después de generado el plan):** el prerrequisito 0 (cerebro con `derivar_triaje`, clínica con `Redis SET triaje`) **ya se cumple**: Lucas desplegó el v7 de hoy a las 16:45 UTC. Pero el repo quedó DESPUÉS con más arreglos (chequeo de salida, ficha, notas internas, `texto_original`), así que antes del PUT al v6 hay que volver a correr `python scripts/crear_v7_en_n8n.py --aplicar` (re-PUTea los 9 workflows v7 y regraba `data/v7_test_ruta.txt`). El script `apply_v7_flag_lucas.py` debe verificar por API los 3 puntos que pide el revisor (nodo `Redis GET triaje`, `Devolver` con `derivar_triaje`, tool `derivar_triaje` conectada por `ai_tool`, y `Redis SET triaje` en la clínica) y abortar si falta alguno. Los 4 "faltantes" del revisor van incorporados al script: test de no-regresión de urgencia SIN flag, memoria del canned de fallo del cerebro, y la referencia correcta es §7 punto 3 del diseño.

## Resumen

PLAN para conectar el v7 (cerebro NBHzj8ar2XuSvyIY) al v6 vivo (O155MqHgOSaNZ9ye, snapshot workflows/current/v6_LIVE_2026-10-06.json, versionId 883a552b, 155 nodos) SOLO para teléfonos con clave Redis `v7:tel:{tel}` = 'vivo' (hoy: 5491161461034). Verifiqué en el JSON vivo: `Router - Clasificar Intent` recibe main únicamente desde `Triaje: ¿Seguimiento?` main[1] y `Triaje: Ruta Pre` main[2] (ambos index 0) y NO lee $json (su `parameters.text` usa $('Build Router Context') y $('Preparar Mensaje Final')); 0 nodos referencian $('Router - Clasificar Intent'); `_flow` solo lo emite `Format Sub-WF Output` y nadie lo lee. Por eso el fork se inserta redirigiendo esos DOS arcos a 8 nodos nuevos con prefijo `V7: `, en una fila libre (y=1680; no hay nodos con y>1450 en x 10400-13200):

`Triaje: ¿Seguimiento?`[1] y `Triaje: Ruta Pre`[2] → `V7: Redis GET modo` (clon de `Triaje: Redis GET estado`: fail-open) → `V7: ¿Vivo?` → [1] `Router - Clasificar Intent` (idéntico a hoy para todos los demás) / [0] `V7: Pre-Triaje Regex` (esUrgenciaFuerte copiado TEXTUAL de `Parse Intent` líneas 10,17-19) → `V7: ¿Urgencia regex?` → [0] `V7: Derivar a Triaje` → `Triaje: Cargar Config` / [1] `V7: Cerebro` (executeWorkflow v1.2 a NBHzj8ar2XuSvyIY con {phone, texto, pushName, modo:'vivo'}, espera, continueOnFail) → `V7: Adaptador` (Code: texto→output; enviar=false→'[NO_REPLY]'; derivar_triaje→flag; {error}/vacío→canned seguro + aviso [ACCIÓN]) → `V7: ¿Deriva a triaje?` → [0] `V7: Derivar a Triaje` / [1] `Fallback Output` con `{output, _flow:'v7', _v7}`.

Guardas de salida (edición de jsCode/condición, NUNCA recableo porque `Split en Mensajes` l.40 y `Gate Humano Final` l.28 hacen $('Banlist Validator').first()): `Fallback Output` (respeta [NO_REPLY] v7), `Canned Sidecar`, `Gate Pago Tratamiento` (return items), `Banlist Validator` (OPCIÓN A recomendada: passthrough total para _flow='v7', porque el cerebro ya corrió BanlistUsted+ChequeoSalida y la lista v6 en voseo bloquea 'Lo esperamos el día de su turno' (reglas l.45/47) y bloquearía 'le aviso ahora mismo a la clínica' (l.50/51), con canned en voseo + aviso al grupo), `Necesita Formatting?` (condición c5 `($json._flow || '') !== 'v7'` → sin Formatting Agent, que reescribe a vos/hs y pierde _flow). `Triaje: Evaluar` + fuente triaje/evaluar.js líneas 67-69: `modo_entrada='nuevo'` también si corrió `V7: Derivar a Triaje` (sin eso, una derivación del cerebro entra como 'seguimiento' y con estado null/escalado devuelve ruta_pre 'normal' → Ruta Pre[2] → fork → cerebro otra vez o Router). Probado offline: 46/46 tests + 29/29 gate siguen en verde con el parche, 7 casos de modo_entrada OK; harness diferencial viejo-vs-nuevo de los 4 Code guardados: IGUAL para todos los items v6 (`_flow` undefined/'cancelar_subwf'), difiere solo con `_flow:'v7'` donde debe; los 3 Code nuevos corren en tests/harness_code_node.mjs (15 casos).

Memoria sin duplicados: en el camino v7 no corre ningún Sub-Agent → `Postgres Chat Memory` (ai_memory, sessionKey = Preparar Mensaje Final.phone) no escribe; escribe solo `Guardar en memoria` del cerebro (2 filas, guardar = vivo && !silencio) con el MISMO session_id (phone de Preparar Mensaje Final); el adaptador no escribe ni reenvía `avisos`; en derivar_triaje el cerebro pone silencio=true (no guarda, no avisa) y la memoria/aviso quedan en `Triaje: Persistir` / `Triaje: Escalar (notify-grupo)`; los canned directos (`Armar filas canned`) están antes del fork. PREREQUISITO DURO (orden 0): el cerebro VIVO (workflows/current/v7/cerebro_NBHzj8ar2XuSvyIY.json, versionId 59001df9, 12:18) NO tiene `Redis GET triaje` ni devuelve `derivar_triaje`: si Asiri llama derivar_triaje hoy, Salida da silencio y el paciente con urgencia NO recibe nada. Redeployar el cerebro con scripts/v7_workflow_cerebro.py (crear_v7_en_n8n.py --aplicar) ANTES del PUT; el apply lo verifica por API y aborta si falta. Rollback sin PUT: `DEL v7:tel:5491161461034`; si Redis cae, el GET fail-open manda al Router (v6 intacto). Todo lo previo al fork (/bot off, rate limit 10/15min, fromMe, buffer 22 s, modo humano 1 h, Pre-filtro Cierre, Gate Canned Directo, seguimiento de triaje) sigue aplicando igual al celular de Lucas. Script: `scripts/apply_v7_flag_lucas.py` (esqueleto de apply_fix_continuidad_flujo.py: GET → diff → --apply → versionId recheck → backup PRE → PUT con PUT_KEYS/SETTINGS_OK → GET → backup POST → verificación → snapshot).

## Cambios (en orden)

### 0. [parametro_editar] v7 Cerebro NBHzj8ar2XuSvyIY (workflow APARTE, no entra en el PUT del v6) — nodos 'Redis GET triaje', 'Salida', 'Devolver'

PREREQUISITO antes del PUT al v6: re-deployar el cerebro desde scripts/v7_workflow_cerebro.py (python scripts/crear_v7_en_n8n.py --aplicar, actualiza por nombre con PUT_KEYS). El snapshot vivo workflows/current/v7/cerebro_NBHzj8ar2XuSvyIY.json (updatedAt 2026-10-06T12:18:19Z, versionId 59001df9, 32 nodos) NO tiene el nodo 'Redis GET triaje' (lista de nodos: ... 'Redis GET bloque_exec', 'Salida' ...), su 'Salida' no calcula derivar_triaje y su 'Devolver' devuelve {texto, enviar, silencio, modo, motivo_chequeo, motivo_banlist, fallo_agente, tools, avisos} sin derivar_triaje/triaje. El script sí lo tiene (v7_workflow_cerebro.py: redis_get 'Redis GET triaje' key 'triaje_v7:'+tel+':'+$execution.id; JS_SALIDA `if (triaje && !hayOk) { derivar_triaje = true; silencio = true; texto = null; }`; Devolver con `derivar_triaje: s.derivar_triaje === true, triaje: s.triaje || null`). El apply del v6 hace GET /workflows/NBHzj8ar2XuSvyIY y ABORTA si no existe el nodo 'Redis GET triaje' o si el jsCode de 'Devolver' no contiene 'derivar_triaje'.

**Por qué:** Con el cerebro vivo actual, si Asiri llama la tool derivar_triaje (v7 Tool - clinica deja la marca triaje_v7:{tel}:{exec}) y responde [NO_REPLY], 'Salida' lo trata como silencio puro (texto === '[NO_REPLY]' && !hayOk → silencio=true) → el adaptador manda '[NO_REPLY]' → el paciente con una urgencia NO recibe nada y el triaje del v6 nunca se entera. Es exactamente el agujero del incidente Mariela con otro disfraz.

**Riesgo:** Bajo para el v6 (no lo toca). El re-deploy del cerebro es un PUT a un workflow del v7 que hoy no atiende a nadie (solo se llama desde el webhook de prueba inactivo).

### 1. [nodo_nuevo] V7: Redis GET modo

Clon de 'Triaje: Redis GET estado' (id triaje-redis-get). {"name":"V7: Redis GET modo","type":"n8n-nodes-base.redis","typeVersion":1,"position":[10816,1680],"parameters":{"operation":"get","propertyName":"v7_modo","key":"={{ 'v7:tel:' + $('Preparar Mensaje Final').first().json.phone }}","keyType":"string","options":{}},"credentials":{"redis":{"id":"kdtSKwGbN1xAZeUh","name":"Redis account"}},"alwaysOutputData":true,"onError":"continueRegularOutput"}. Es lo mismo que genera Grafo.redis_get en scripts/v7_lib.py. Emite un item NUEVO {v7_modo: 'vivo'|null} (Redis v1 get descarta el item de entrada: los campos de Triaje: Evaluar o {triaje_estado:null} se pierden, nadie los lee después por $json).

**Por qué:** Es el único punto de decisión v6/v7 y tiene que ser fail-open: si Redis falla, el item sale sin v7_modo (o con {error}) y el IF manda al Router (v6 completo). El phone es el LID-safe de Edit Fields - Extraer Datos (vía Preparar Mensaje Final), el mismo que Kill-switch Check usa para reconocer a Lucas como admin y el mismo session_id de la memoria.

**Riesgo:** Una llamada Redis extra por mensaje para TODOS los teléfonos (~1 ms, mismo Redis del buffer). Si la clave tuviera otro valor ('sombra', basura) → Router (v6).

### 2. [nodo_nuevo] V7: ¿Vivo?

Clon de 'Triaje: ¿Seguimiento?' (if v2.2). {"name":"V7: ¿Vivo?","type":"n8n-nodes-base.if","typeVersion":2.2,"position":[11120,1680],"parameters":{"conditions":{"options":{"caseSensitive":true,"leftValue":"","typeValidation":"loose","version":2},"conditions":[{"id":"v7-vivo-c","leftValue":"={{ $json.v7_modo || '' }}","rightValue":"vivo","operator":{"type":"string","operation":"equals"}}],"combinator":"and"},"options":{}}}. Salida [0] (true) → V7: Pre-Triaje Regex; salida [1] (false) → Router - Clasificar Intent index 0.

**Por qué:** `$json.v7_modo || ''` cubre null (clave inexistente), undefined (item {error} por Redis caído) y '' → siempre false → Router. Solo el literal 'vivo' entra al v7 ('sombra' queda para una fase posterior, doc §7 punto 3, fuera de alcance 'solo Lucas').

**Riesgo:** Ninguno para los demás teléfonos: la rama [1] reproduce el arco actual (Router index 0).

### 3. [nodo_nuevo] V7: Pre-Triaje Regex

n8n-nodes-base.code v2, position [11408,1680]. jsCode COMPLETO:
// V7: Pre-Triaje Regex — red determinística ANTES de Asiri (solo corre para teléfonos con v7:tel:{tel} = 'vivo').
// Copia TEXTUAL de esUrgenciaFuerte del nodo 'Parse Intent' (jsCode líneas 10 y 17-19): es el mismo criterio que hoy manda al triaje
// a TODOS los teléfonos (Parse Intent línea 26 → Switch sobre Intent[2] → Triaje: Cargar Config). Si cambia allá, cambiar acá (apply lo verifica).
// NO incluye gateRedFlags: corre igual dentro de 'Triaje: Evaluar' una vez que el mensaje entra al triaje (triaje/gate_red_flags.js
// líneas 12-14: sobre todos los mensajes da falsos positivos, caso real #17).
let text = '';
try { text = ($('Preparar Mensaje Final').first().json.text || '').toString(); } catch (e) { text = ''; }
const textoNorm = (text || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
const esUrgenciaFuerte = (/\b(dolor\w*|duele\w*|sangr\w*|hinchaz\w*|hinchad[oa]|fiebre|pincha\w*|lastima\w*)\b/.test(textoNorm) ||
  /\bse (me |le )?(salio|desprendio|despego|rompio|solto|cayo)\b.{0,40}\b(bracket|brackets|alambre|aparato|arco|banda|ligadura|expansor)/.test(textoNorm)) &&
  !/\b(sin dolor|no (me |le )?(duele|dolio)|no (tengo|tiene|siento|siente) (ningun |nada de )?(dolor|molestia)\w*|sin molestias)\b/.test(textoNorm);
console.log('[V7] pre-triaje regex:', esUrgenciaFuerte ? 'URGENCIA -> triaje (sin pasar por Asiri)' : 'no', '|', text.slice(0, 120));
return [{ json: { _flow: 'v7', urgencia_regex: esUrgenciaFuerte === true } }];

Probado offline (tests/harness_code_node.mjs): 'se me salió un bracket y me duele' → true; 'quiero cambiar el turno, sin dolor' → false; 'no va porque tiene fiebre' → true (paridad: hoy Parse Intent también lo manda al triaje); 'hola, quiero sacar un turno' → false; 'Mi hija esta incomoda, no come desde ayer con el aparato' → false (ese caso lo cubre Asiri con derivar_triaje, por eso el prerequisito 0). El apply extrae las líneas 17-19 del jsCode VIVO de Parse Intent y aborta si no están byte a byte dentro del jsCode nuevo (fuente única de facto).

**Por qué:** Pedido explícito: una urgencia fuerte tiene que ir al triaje ANTES de Asiri, sin depender del LLM (regla dura #5, lección Mariela). Se copia SOLO esUrgenciaFuerte (ya tiene guarda de negación) y NO gateRedFlags: (a) paridad exacta con lo que hoy manda al triaje a cualquier teléfono; (b) la cabecera de triaje/gate_red_flags.js líneas 12-14 prohíbe correrlo sobre todos los mensajes (trauma/'accidente'/'no aguanto'/'calmantes' sobre 'tuve un accidente, necesito cambiar el turno' → escalada + takeover 1 h falsos); (c) gateRedFlags corre igual en Triaje: Evaluar sobre lo que sí entra. Tampoco se reusa urgenciaWords de Pre-filtro Cierre (línea 96: 'arco', 'pastilla', 'que tomo'). El item que emite no lo lee nadie por $json salvo el IF siguiente y V7: Derivar a Triaje.

**Riesgo:** Si se quisiera sumar red flags pre-fork (duda para Lucas), el apply tendría un flag --red-flags-pre-fork que embebe triaje/gate_red_flags.js y suma `|| gateRedFlags(text).escala`; recomendado NO por ahora.

### 4. [nodo_nuevo] V7: ¿Urgencia regex?

if v2.2 patrón Grafo.si (scripts/v7_lib.py). {"name":"V7: ¿Urgencia regex?","type":"n8n-nodes-base.if","typeVersion":2.2,"position":[11712,1680],"parameters":{"conditions":{"options":{"caseSensitive":true,"leftValue":"","typeValidation":"strict"},"conditions":[{"id":"v7-urg-c","leftValue":"={{ $json.urgencia_regex === true }}","rightValue":"","operator":{"type":"boolean","operation":"true","singleValue":true}}],"combinator":"and"},"options":{}}}. [0] → V7: Derivar a Triaje; [1] → V7: Cerebro.

**Por qué:** Separa el camino determinístico (triaje sin LLM) del camino Asiri. Expresión booleana explícita para no depender de coerción.

**Riesgo:** Ninguno fuera del camino v7.

### 5. [nodo_nuevo] V7: Cerebro

Clon de 'Execute Sub-WF Cancelar' (id exec-subwf-cancelar). {"name":"V7: Cerebro","type":"n8n-nodes-base.executeWorkflow","typeVersion":1.2,"position":[12016,1680],"parameters":{"workflowId":{"__rl":true,"value":"NBHzj8ar2XuSvyIY","mode":"id"},"workflowInputs":{"mappingMode":"defineBelow","value":{"phone":"={{ $('Preparar Mensaje Final').first().json.phone }}","texto":"={{ $('Preparar Mensaje Final').first().json.text }}","pushName":"={{ $('Edit Fields - Extraer Datos').first().json.pushName }}","modo":"vivo"},"matchingColumns":[],"schema":[]},"options":{}},"alwaysOutputData":true,"continueOnFail":true}. El id sale de v7/ids.json ('cerebro': 'NBHzj8ar2XuSvyIY'; el apply lo lee de ahí, no lo hardcodea). El trigger del cerebro es executeWorkflowTrigger v1.1 jsonExample {phone, texto, pushName, modo, historial_json} (v7_workflow_cerebro.py: g.trigger(...)); historial_json no se manda (Armar contexto lo trata como opcional). options {} = waitForSubWorkflow por defecto (espera el resultado). El v6 tiene settings.callerPolicy 'workflowsFromSameOwner' y el cerebro también: mismo owner, permitido.

**Por qué:** La clave es 'texto' (no 'text'): el cerebro lee e.texto. phone desde Preparar Mensaje Final garantiza que el session_id que escribe 'Guardar en memoria' ($('Salida').first().json.phone) es el mismo que lee Build Router Context (`session_id = '{{ $json.phone }}'`) y el sessionKey de Postgres Chat Memory. pushName igual que Execute Sub-WF Cancelar. modo literal 'vivo' (el IF ya lo garantizó; evita que una clave 'sombra' futura entre acá por error).

**Riesgo:** Latencia: el cerebro (Identificar paciente → Dentalink 8 s timeout, Asiri maxIterations 5) puede tardar 10-30 s además de los 22 s del buffer; el v6 no tiene executionTimeout. Un crash del sub-workflow llega como item {error} (continueOnFail) y lo cubre el adaptador.

### 6. [nodo_nuevo] V7: Adaptador

n8n-nodes-base.code v2, position [12320,1680]. jsCode COMPLETO:
// V7: Adaptador — traduce la salida del cerebro v7 (NBHzj8ar2XuSvyIY, nodo 'Devolver': {texto, enviar, silencio, derivar_triaje, triaje, modo,
// motivo_chequeo, motivo_banlist, fallo_agente, tools, avisos}) al contrato de 'Fallback Output': { output, _flow }.
// El cerebro YA guardó la memoria (n8n_chat_histories, solo si vivo && !silencio) y YA mandó sus avisos al grupo: acá no se escribe ni se reenvía nada.
// El item se arma DESDE CERO (sin spread de $json): con continueOnFail un crash del sub-workflow llega como { error }.
const CANNED_FALLO = 'Hola! Soy Asiri🤗, la secretaria virtual de la Dra. Raquel Rodríguez. Le envío la información a la secretaria, ella le responderá en su horario de atención. Gracias!';
let r = {};
try { r = $input.first().json || {}; } catch (e) { r = {}; }
let phone = '';
try { phone = ($('Preparar Mensaje Final').first().json.phone || '').toString(); } catch (e) { phone = ''; }

const errorSubWf = r.error ? String((r.error && r.error.message) || r.error) : null;
const texto = typeof r.texto === 'string' ? r.texto.trim() : '';
const derivar = r.derivar_triaje === true && r.modo !== 'sombra';   // en sombra la derivación es solo log: el triaje respondería dos veces

let output, caso;
if (derivar) {
  output = '[NO_REPLY]'; caso = 'derivar_triaje';                    // el IF siguiente lo manda a 'Triaje: Cargar Config', no a Fallback Output
} else if (errorSubWf || (r.enviar !== false && !texto)) {
  // Crash del sub-workflow o contrato roto (el cerebro solo cubre el error del agente, no el suyo): canned seguro + aviso [ACCIÓN]. Sin tomar: no silencia al bot.
  output = CANNED_FALLO; caso = errorSubWf ? 'error_subworkflow' : 'sin_texto';
  try {
    await this.helpers.httpRequest({ method: 'POST', url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo', json: true,
      qs: { phone, resumen: '[ACCIÓN] v7: el cerebro no devolvió respuesta (' + String(errorSubWf || 'sin texto').slice(0, 200) + '). Se mandó el canned de secretaria: revisar y contestar a mano.' } });
  } catch (e) { /* el aviso nunca rompe la respuesta */ }
} else if (r.enviar === false) {
  output = '[NO_REPLY]'; caso = 'silencio';                          // Fallback Output lo respeta por _flow; termina en PG - Delete NO_REPLY → Descartar
} else {
  output = texto; caso = 'texto';
}
const tools = (Array.isArray(r.tools) ? r.tools : []).map((t) => t && t.tool).filter(Boolean);
console.log('[V7] adaptador:', JSON.stringify({ caso, phone, enviar: r.enviar, silencio: r.silencio, fallo_agente: r.fallo_agente, motivo_chequeo: r.motivo_chequeo, motivo_banlist: r.motivo_banlist, tools, error: errorSubWf, len: output.length }));
return [{ json: { output, _flow: 'v7', derivar_triaje: derivar,
  _v7: { caso, fallo_agente: r.fallo_agente === true, motivo_chequeo: r.motivo_chequeo || null, motivo_banlist: r.motivo_banlist || null, tools, error: errorSubWf } } }];

Probado offline (harness) con 7 entradas: texto normal → output texto; {derivar_triaje:true, modo:'vivo'} → '[NO_REPLY]' + derivar_triaje true; {derivar_triaje:true, modo:'sombra'} → silencio (no deriva); cierre del cerebro vivo actual ({texto:null, enviar:false, silencio:true} sin derivar_triaje) → '[NO_REPLY]'; {error:{message:'boom'}}, {} y {texto:'', enviar:true} → CANNED_FALLO (caso error_subworkflow / sin_texto). CANNED_FALLO es el mismo texto que usan Format Sub-WF Output y Gate Error Tecnico.

**Por qué:** Mapeo enviar=false → '[NO_REPLY]': es el mecanismo de descarte del v6 (Necesita Formatting? c2 false → Split en Mensajes {message:'[NO_REPLY]'} → Tiene respuesta? false → PG - Delete NO_REPLY → Descartar [NO_REPLY]); requiere la guarda de Fallback Output (orden 21) para que no lo convierta en CANNED_SECRETARIA. derivar_triaje=true NO va a Fallback Output: el IF siguiente lo manda al triaje. Nunca spread del $json de entrada (sería el item del Execute Workflow o {error}). No reenvía `avisos` (el cerebro ya los POSTea en modo vivo, JS_SALIDA `if (vivo) for (const a of avisos) ...`) ni escribe memoria.

**Riesgo:** PG - Delete NO_REPLY (ORDER BY id DESC LIMIT 1 sin filtro de fecha) en un silencio v7 no encuentra fila de este turno (el cerebro no guarda en silencio) y podría borrar una '[NO_REPLY]' vieja de la era v6 del mismo teléfono: inocuo (Build Router Context ya excluye '[NO_REPLY]'); no se toca.

### 7. [nodo_nuevo] V7: ¿Deriva a triaje?

if v2.2 patrón Grafo.si. {"name":"V7: ¿Deriva a triaje?","type":"n8n-nodes-base.if","typeVersion":2.2,"position":[12624,1680],"parameters":{"conditions":{"options":{"caseSensitive":true,"leftValue":"","typeValidation":"strict"},"conditions":[{"id":"v7-deriva-c","leftValue":"={{ $json.derivar_triaje === true }}","rightValue":"","operator":{"type":"boolean","operation":"true","singleValue":true}}],"combinator":"and"},"options":{}}}. [0] → V7: Derivar a Triaje; [1] → Fallback Output index 0.

**Por qué:** Separa el camino triaje del camino Fallback Output; el item que entra a Fallback Output es {output, _flow:'v7', derivar_triaje:false, _v7} (mismo contrato que ya usan Es Canned Directo?[0] y Set NO_REPLY: items sin Router/Parse Intent).

**Riesgo:** Ninguno fuera del camino v7.

### 8. [nodo_nuevo] V7: Derivar a Triaje

n8n-nodes-base.code v2, position [11712,1904]. jsCode COMPLETO:
// V7: Derivar a Triaje — ÚNICO punto por el que un teléfono en v7 entra al triaje del v6 (regex pre-fork o derivar_triaje del cerebro).
// 'Triaje: Evaluar' lo detecta con $('V7: Derivar a Triaje').isExecuted para entrar en modo 'nuevo' (triaje/evaluar.js). 'Triaje: Cargar Config'
// ignora el item de entrada (query estática), así que acá no hace falta armar nada: solo dejar rastro de por dónde vino.
let via = 'cerebro';
try { if ($('V7: Pre-Triaje Regex').first().json.urgencia_regex === true) via = 'regex'; } catch (e) { via = 'cerebro'; }
console.log('[V7] derivar a triaje via', via);
return [{ json: { _flow: 'v7', via } }];

Salida [0] → Triaje: Cargar Config (index 0; tercera fuente junto a Switch sobre Intent[2] y Triaje: ¿Seguimiento?[0]). Probado offline: via 'regex' / 'cerebro' / 'cerebro' si el nodo regex no corrió.

**Por qué:** Hace falta UN nodo de convergencia con nombre fijo para el isExecuted de Triaje: Evaluar (orden 26): por él pasan tanto la regex pre-fork como la derivación del cerebro. Triaje: Cargar Config no lee $json ni $() (SELECT estático de triaje_config + triaje_videos), y toda la rama Triaje:* lee $('Preparar Mensaje Final'), $('Build Router Context') y $('Triaje: Redis GET estado'), que ya corrieron antes del fork (scan de los 21 nodos Triaje:*: ninguno lee $('Parse Intent') salvo el isExecuted, ni $('Extraer Horarios y Precio') ni $('Router - Clasificar Intent')). NO conectar a Triaje: Evaluar directo (necesita la fila de config en $input), ni a Switch sobre Intent, ni a Sub-Agent Urgencia (sin entrada main, LLM muerto).

**Riesgo:** evaluar.js líneas 161-162: si triaje_config.telefonos_piloto no está vacío y no incluye 5491161461034 → escalar 'fuera_piloto' (verificar con check_triaje.py que imprime piloto=).

### 9. [conexion_quitar] Triaje: ¿Seguimiento?

connections['Triaje: ¿Seguimiento?'].main[1]: quitar {node:'Router - Clasificar Intent', type:'main', index:0} (ARCO A del fork). main[0] → Triaje: Cargar Config queda intacto.

**Por qué:** Es una de las dos únicas entradas main del Router (verificado en connections del JSON vivo). El item que viaja es {triaje_estado: null} y nadie lo lee aguas abajo por $json.

**Riesgo:** Si el apply fallara a mitad, el PUT es atómico (todo el workflow): no hay estado intermedio.

### 10. [conexion_agregar] Triaje: ¿Seguimiento?

connections['Triaje: ¿Seguimiento?'].main[1] = [{node:'V7: Redis GET modo', type:'main', index:0}].

**Por qué:** Redirige el arco A al fork.

**Riesgo:** —

### 11. [conexion_quitar] Triaje: Ruta Pre

connections['Triaje: Ruta Pre'].main[2] (outputKey 'normal'): quitar {node:'Router - Clasificar Intent', type:'main', index:0} (ARCO B). main[0] (clasificar → Triaje: Clasificar + Merge), main[1] (decidido → Triaje: Decidir) y main[3] (fallback → Triaje: Preparar Escalada) intactos.

**Por qué:** Segunda y última entrada main del Router. Por acá pasan solo los ruta_pre 'normal' (estado escalado/cerrado/sin paso, o video_enviado con texto de otro tema): es lo mismo que hoy llega al Router.

**Riesgo:** —

### 12. [conexion_agregar] Triaje: Ruta Pre

connections['Triaje: Ruta Pre'].main[2] = [{node:'V7: Redis GET modo', type:'main', index:0}].

**Por qué:** Redirige el arco B al fork. El item de Triaje: Evaluar (triaje:true, ruta_pre:'normal', cfg...) muere en el Redis GET (emite item nuevo): el adaptador nunca hace spread de él.

**Riesgo:** —

### 13. [conexion_agregar] V7: Redis GET modo

connections['V7: Redis GET modo'] = {main: [[{node:'V7: ¿Vivo?', type:'main', index:0}]]}.

**Por qué:** Cadena del fork.

**Riesgo:** —

### 14. [conexion_agregar] V7: ¿Vivo?

connections['V7: ¿Vivo?'] = {main: [[{node:'V7: Pre-Triaje Regex', type:'main', index:0}], [{node:'Router - Clasificar Intent', type:'main', index:0}]]}. Tras esto, 'Router - Clasificar Intent' recibe main EXACTAMENTE desde V7: ¿Vivo?[1] (más Router LM por ai_languageModel, sin cambios).

**Por qué:** La salida false reproduce byte a byte el destino actual de los dos arcos (Router, index 0).

**Riesgo:** —

### 15. [conexion_agregar] V7: Pre-Triaje Regex

connections['V7: Pre-Triaje Regex'] = {main: [[{node:'V7: ¿Urgencia regex?', type:'main', index:0}]]}.

**Por qué:** Cadena del fork.

**Riesgo:** —

### 16. [conexion_agregar] V7: ¿Urgencia regex?

connections['V7: ¿Urgencia regex?'] = {main: [[{node:'V7: Derivar a Triaje', type:'main', index:0}], [{node:'V7: Cerebro', type:'main', index:0}]]}.

**Por qué:** Urgencia fuerte → triaje sin pasar por Asiri; si no → cerebro.

**Riesgo:** —

### 17. [conexion_agregar] V7: Cerebro

connections['V7: Cerebro'] = {main: [[{node:'V7: Adaptador', type:'main', index:0}]]}.

**Por qué:** Cadena del fork.

**Riesgo:** —

### 18. [conexion_agregar] V7: Adaptador

connections['V7: Adaptador'] = {main: [[{node:'V7: ¿Deriva a triaje?', type:'main', index:0}]]}.

**Por qué:** Cadena del fork.

**Riesgo:** —

### 19. [conexion_agregar] V7: ¿Deriva a triaje?

connections['V7: ¿Deriva a triaje?'] = {main: [[{node:'V7: Derivar a Triaje', type:'main', index:0}], [{node:'Fallback Output', type:'main', index:0}]]}. Fallback Output pasa de 8 fuentes main (Sub-Agent Confirmar/Cancelar/Agendar/Urgencia/General, Set NO_REPLY, Format Sub-WF Output, Es Canned Directo?[0]) a 9.

**Por qué:** Camino derivar_triaje=true → triaje; resto → cadena de salida del v6 (Fallback Output → Canned Sidecar → Gate Pago Tratamiento → Banlist Validator → Necesita Formatting? → Split en Mensajes → Gate Error Tecnico → Tiene respuesta? → Loop Mensajes → Evolution - Typing → Gate Humano Final → Evolution API - Enviar Mensaje).

**Riesgo:** —

### 20. [conexion_agregar] V7: Derivar a Triaje

connections['V7: Derivar a Triaje'] = {main: [[{node:'Triaje: Cargar Config', type:'main', index:0}]]}.

**Por qué:** Destino exacto de una urgencia v7 (regex o cerebro). check_triaje.py debe sumar este assert junto al existente `conns['Switch sobre Intent']['main'][2][0]['node'] == 'Triaje: Cargar Config'`.

**Riesgo:** —

### 21. [parametro_editar] Fallback Output

parameters.jsCode, reemplazo único (count==1) de la ancla `return items.map(it => {\n  let output = (it.json.output || '').trim();` por `return items.map(it => {\n  if (it.json._flow === 'v7') return it;   // v7: el cerebro ya decidió texto o silencio ([NO_REPLY]); no convertir en CANNED_SECRETARIA\n  let output = (it.json.output || '').trim();`. Resto del nodo (CANNED_SECRETARIA, CIERRES línea 12, esCierrePuro línea 13, `return { json: { ...it.json, output } }` línea 27) intacto.

**Por qué:** Líneas 20-22: si output es '' o '[NO_REPLY]' y el texto del paciente no está en SU lista CIERRES (ok, dale, gracias, muchas gracias, listo, perfecto, joya, genial, de nada, chau, adios, buenisimo) lo reemplaza por 'Hola! Ya le transmito su consulta a la secretaria...'. El cerebro decide silencio con HistorialCore.esCierre (más amplia: 'gracias doctora', 'buenisimo gracias') o con [NO_REPLY] del agente: sin la guarda el paciente v7 recibiría un canned que el v7 decidió no mandar. Diferencial offline: items v6 ({output}, {output:'[NO_REPLY]'}, {_flow:'cancelar_subwf'}) → salida IDÉNTICA viejo/nuevo; solo cambia {output:'[NO_REPLY]', _flow:'v7'} (queda '[NO_REPLY]').

**Riesgo:** Nulo para v6: ningún item v6 trae _flow==='v7' (único emisor de _flow hoy: Format Sub-WF Output con 'cancelar_subwf'/'cancelar_subwf_fallback').

### 22. [parametro_editar] Canned Sidecar

parameters.jsCode, reemplazo único de `const items = $input.all();\n\n// --- 1. texto REAL del paciente` por `const items = $input.all();\nif (items.length && items[0].json._flow === 'v7') return items;   // v7: la INFO (alias/precio) la resuelve el cerebro por código; Parse Intent no corrió\n\n// --- 1. texto REAL del paciente` (línea 15).

**Por qué:** Doc §7 punto 3 lo pide. En el camino v7 $('Parse Intent') tira (try/catch línea 88 → intent '' → sin freno por urgencia) y el nodo ANEXARÍA el alias/precio hardcodeados en 'vos' (TEXTOS líneas 94-95, BRUBANK) a una respuesta que Asiri ya resolvió desde knowledge_base (verificado en el diferencial: con el texto del paciente 'quiero saber el alias...' el código viejo anexaba el canned a un output v7; el nuevo lo deja pasar). Items v6 idénticos viejo/nuevo.

**Riesgo:** Nulo para v6.

### 23. [parametro_editar] Gate Pago Tratamiento

parameters.jsCode, reemplazo único de `const items = $input.all();\n\nlet pacienteMsg = '';` por `const items = $input.all();\nif (items.length && items[0].json._flow === 'v7') return items;   // v7: pago de tratamiento lo maneja el cerebro (prompt + avisar_grupo); evitar pisar la respuesta y el aviso doble\n\nlet pacienteMsg = '';` (líneas 12-14).

**Por qué:** Doc §7 punto 3. Este gate REEMPLAZA el output por su canned y hace POST a notify-grupo (líneas 77-86) si el paciente habla de pagar tratamiento/cuota/brackets: en v7 pisaría la respuesta de Asiri y duplicaría el aviso que el cerebro ya mandó por avisar_grupo/registrar_pago. Items v6 idénticos viejo/nuevo (diferencial).

**Riesgo:** Nulo para v6.

### 24. [parametro_editar] Banlist Validator

OPCIÓN A (recomendada): passthrough total para _flow='v7'. parameters.jsCode, reemplazo único de `const item = $input.first().json;\nconst output = (item.output || '').toString();` (líneas 6-7) por:
const item = $input.first().json;
const output = (item.output || '').toString();
if (item._flow === 'v7') {   // v7: BanlistUsted + ChequeoSalida ya corrieron en el cerebro (v7/banlist_usted.js); esta lista es voseo y bloquea 'lo esperamos el día de su turno'
  console.log('[BANLIST] passthrough v7');
  return [{ json: { ...item, banlist_triggered: null, escalate_to_human: false } }];
}
Las 19 reglas (líneas 43-63), el CANNED voseo (línea 82) y el POST notify-grupo (89-96) quedan intactos para el v6. El nodo SIGUE EJECUTANDO en v7 (passthrough, no bypass) y emite la misma forma que el camino sin bloqueo (línea 112), así Banlist Shadow - Prep lee banlist_triggered/escalate_to_human como siempre. Opción B descartada: marcar reglas 43-47 con skip_if_v7 + canned en usted; se descarta porque las reglas 'duras' que quedarían también dan falsos positivos en usted (línea 50 `ahora mismo ... clínica` y 51 `lo antes posible ... clínica|venir` bloquearían 'Le aviso ahora mismo a la clínica' / 'Les aviso lo antes posible'), con canned en voseo + aviso al grupo. Diferencial offline: v6 idéntico; v7 'Su turno es el jueves 22/10 a las 09:20. Lo esperamos el día de su turno.' pasa (antes: bloqueo 'los esperamos' + escalate_to_human true).

**Por qué:** El cerebro ya corre, por código y sobre el mismo texto, v7/banlist_usted.js (instrucciones en usted y voseo: guárdela/traiga/tome/saque/aplique/enjuague/coloque/ponga/evite; diagnóstico: no se preocupe/no es grave/es normal; opinión: qué macana; invitación bloqueada si INMEDIATO o sin TURNO_CONCRETO; dirección sin que la pidan; 'le aviso si se libera') + ChequeoSalida, con tests (tests/test_banlist_usted.mjs líneas 31-35 fijan como PERMITIDAS 'Los esperamos el día de su consulta', 'Lo esperamos.' tras turno con fecha). Son dos capas (prompt sin ejemplos contrarios + código) → regla dura #5 cumplida. La lista v6 (voseo) bloquea lo legítimo del v7 (regla 45 `(los|las|te|le|la|lo...)\s*esperamos`, 47 `(la|lo)\s+esperamos`, 44 `venga`) y responde con 'Recibimos tu mensaje... Disculpa la demora' (voseo) + aviso al grupo: falsas escaladas en el piloto que tapan señales reales. No se desconecta porque Split en Mensajes (línea 40) y Gate Humano Final (línea 28, FUERA de try/catch) hacen $('Banlist Validator').first(). Banlist Shadow - Prep/LLM/Log se dejan como están: una llamada gpt-5-nano por mensaje v7 que compara regex vs agente = observación gratis del piloto.

**Riesgo:** Se pierde la tercera capa regex del v6 sobre el texto de Asiri. Mitiga: BanlistUsted es la última línea en el cerebro (misma filosofía), Banlist Shadow sigue logueando, Gate Error Tecnico sigue corriendo, y el piloto es un solo teléfono (Lucas).

### 25. [parametro_editar] Necesita Formatting?

parameters.conditions.conditions (if v2, typeValidation loose, combinator and): APPEND una 5ª condición sin tocar c1/c2/c3-bloque-turnos/c4-respuesta-fija-sin-reescritor: {"id":"c5-sin-reescritor-v7","leftValue":"={{ ($json._flow || '') !== 'v7' }}","rightValue":"","operator":{"type":"boolean","operation":"true","singleValue":true}} (misma forma boolean/singleValue que la c4 existente). Con _flow='v7' → false → salida [1] → Split en Mensajes directo. Con _flow undefined o 'cancelar_subwf' → true → el AND queda igual que hoy.

**Por qué:** Doc §7 punto 3. Formatting Agent - WhatsApp (agent v1.8, gpt-5-mini) reescribe a 'vos'/'hs', puede alterar o partir el read-back que ChequeoSalida verificó contra el libro de escrituras, y devuelve solo {output} (pierde _flow). Asiri ya escribe en usted y separa partes con '---' (Split en Mensajes las corta igual).

**Riesgo:** Nulo para v6 (expresión evalúa true para cualquier _flow distinto de 'v7'). El apply asserta que las 4 condiciones previas quedan byte a byte iguales.

### 26. [parametro_editar] Triaje: Evaluar (+ fuente única triaje/evaluar.js líneas 67-69, + tests/test_triaje_nodos.js)

El jsCode vivo es EXACTAMENTE gate_red_flags.js + '\n\n' + evaluar.js con __SYSTEM_PROMPT_JSON__ → json.dumps(prompt_clasificador.md, ensure_ascii=False) (verificado: 16.590 chars, match con '\n\n'; con '\n' o '' no). La ancla aparece 1 vez en el vivo (líneas 132-134) y 1 vez en el repo (67-69). Cambio en triaje/evaluar.js — VIEJO:
// Modo de entrada: si el Router/Parse Intent corrió en esta ejecución, venimos del Switch (nuevo).
let modo_entrada = "seguimiento";
try { if ($('Parse Intent').isExecuted) modo_entrada = "nuevo"; } catch (e) { modo_entrada = estado ? "seguimiento" : "nuevo"; }
NUEVO:
// Modo de entrada: "nuevo" si corrió el Router/Parse Intent (Switch sobre Intent[2]) o si el item vino del v7 por 'V7: Derivar a Triaje'
// (regex pre-fork o derivar_triaje del cerebro). corrio() devuelve null si el nodo no existe en este workflow (p. ej. la sombra): ahí se
// mantiene el criterio viejo (hay estado → seguimiento, si no → nuevo).
const corrio = (n) => { try { return $(n).isExecuted === true; } catch (e) { return null; } };
const corrioParse = corrio('Parse Intent');
let modo_entrada = (corrioParse === true || corrio('V7: Derivar a Triaje') === true) ? "nuevo" : (corrioParse === null ? (estado ? "seguimiento" : "nuevo") : "seguimiento");
El apply: (1) GET → asserta drift cero (jsCode vivo == GATE+'\n\n'+evaluar_repo_HEAD con prompt) y aborta si no; (2) aplica el reemplazo único sobre el vivo; (3) asserta que el resultado == GATE+'\n\n'+evaluar_repo_PARCHEADO (fuente única); (4) exige antes `node tests/test_triaje_nodos.js` y `node triaje/test_gate.js` en verde. Probado offline con el parche (scratch): 46/46 tests existentes OK, gate 29/29, y 7 casos: v6 Switch[2] sin estado → nuevo/clasificar (igual que hoy); v7 derivó sin estado → nuevo/clasificar; v7 derivó con estado 'escalado' → nuevo/clasificar; seguimiento real video_enviado con el nodo V7 existente sin correr → seguimiento/decidido; ídem con el nodo inexistente → seguimiento/decidido; sin Parse Intent ni V7 (sombra) sin estado → nuevo; con estado → seguimiento (= criterio viejo). Sumar a tests/test_triaje_nodos.js los 2 casos nuevos (mkDollar necesita un parámetro v7Executed para el nombre 'V7: Derivar a Triaje'; hoy tira 'nodo desconocido' para nombres no listados, lo que corrio() traduce a null). NO tocar 'Triaje: Decidir': el vivo difiere del repo (Supabase vs Chatwoot muerto).

**Por qué:** Sin esto, cualquier derivación del v7 entra como 'seguimiento' ($('Parse Intent').isExecuted es false porque el Router no corrió): con estado null (línea ~111) o paso 'escalado'/'cerrado' (línea 153) devuelve ruta_pre 'normal' → Triaje: Ruta Pre[2] → fork → Redis 'vivo' → cerebro OTRA VEZ (segunda llamada LLM, doble memoria) y la urgencia se pierde. El modo 'nuevo' nunca devuelve 'normal' (líneas 157-167): sin loop aunque Evaluar corra dos veces en la misma ejecución ($('X').first() lee la última corrida, igual que hoy con Ruta Pre[2] → Switch[2]).

**Riesgo:** Es el único cambio en un nodo del triaje. Mitigado por drift-check, reconstrucción desde la fuente única y tests offline; check_triaje.py corre los mismos tests antes del PUT (regla 9).

## Invariantes para los teléfonos SIN flag (el script apply las verifica por código)

- Para todo teléfono sin clave v7:tel = 'vivo', el camino es el de hoy: … → Triaje: ¿Seguimiento?[1] / Triaje: Ruta Pre[2] → V7: Redis GET modo (item {v7_modo:null}) → V7: ¿Vivo?[1] → Router - Clasificar Intent index 0 → Parse Intent → …, con Router/Parse Intent leyendo solo $('Build Router Context') y $('Preparar Mensaje Final'). CHECK apply (post-PUT, sobre el GET): connections['V7: ¿Vivo?'].main[1] == [{node:'Router - Clasificar Intent', type:'main', index:0}]; el conjunto de arcos main que ENTRAN a 'Router - Clasificar Intent' == {('V7: ¿Vivo?',1)} y la entrada ai_languageModel desde 'Router LM' sigue igual; connections['Triaje: ¿Seguimiento?'].main[0] y connections['Triaje: Ruta Pre'].main[0],[1],[3] byte a byte iguales al PRE.
- Topología: nodes PRE (155) ⊂ nodes POST (163) con id/type/typeVersion/credentials/position iguales; solo cambian parameters de exactamente 6 nodos: `sorted(cambiados) == ['Banlist Validator','Canned Sidecar','Fallback Output','Gate Pago Tratamiento','Necesita Formatting?','Triaje: Evaluar']` (patrón de apply_fix_continuidad_flujo.py: `a[k] != d.get(k)`); los 8 nuevos empiezan con 'V7: ' y ningún otro nodo contiene 'V7:' en sus parameters. CHECK: `connections_POST` menos las claves 'V7: *' y con main[1] de 'Triaje: ¿Seguimiento?' y main[2] de 'Triaje: Ruta Pre' reemplazados por el Router == `connections_PRE` (igualdad de dict completa: cubre Switch sobre Intent[2] → Triaje: Cargar Config, las 8 entradas previas de Fallback Output, Banlist → Necesita Formatting? + Banlist Shadow - Prep, etc.). Además `conns['Switch sobre Intent']['main'][2][0]['node'] == 'Triaje: Cargar Config'` (check_triaje.py) y entradas de 'Triaje: Cargar Config' == {('Switch sobre Intent',2), ('Triaje: ¿Seguimiento?',0), ('V7: Derivar a Triaje',0)}.
- Fail-open del fork: si Redis no responde, los demás teléfonos (y Lucas) siguen por el v6. CHECK apply: nodo 'V7: Redis GET modo' con alwaysOutputData === true, onError === 'continueRegularOutput', credentials.redis.id === 'kdtSKwGbN1xAZeUh' (mismos que 'Triaje: Redis GET estado'), parameters == {operation:'get', propertyName:'v7_modo', key:"={{ 'v7:tel:' + $('Preparar Mensaje Final').first().json.phone }}", keyType:'string', options:{}}; y 'V7: ¿Vivo?' con leftValue "={{ $json.v7_modo || '' }}", operator string equals, rightValue 'vivo', typeValidation 'loose'.
- Las 4 guardas de jsCode son no-op para items v6. CHECK apply (offline, antes del PUT, con tests/harness_code_node.mjs): para cada uno de Fallback Output, Canned Sidecar, Gate Pago Tratamiento, Banlist Validator correr jsCode VIVO vs jsCode NUEVO con entradas {output:'texto'}, {output:'[NO_REPLY]'}, {output:'texto', _flow:'cancelar_subwf'} (nodos simulados: Preparar Mensaje Final, Build Router Context; Parse Intent/Extraer Horarios ausentes) y exigir salida IDÉNTICA; con _flow:'v7' exigir passthrough (Fallback deja '[NO_REPLY]'; Sidecar/Gate devuelven items; Banlist deja 'Lo esperamos el día de su turno' con escalate_to_human false). Ya ejecutado hoy sobre el snapshot: 24 pares, IGUAL en todos los v6, DIFIERE solo en 3 casos v7 esperados. Cada reemplazo con `reemplazar_unico` (count == 1, aborta si 0 o >1) y aborta si la guarda ya existe ('_flow === \'v7\'' presente).
- Necesita Formatting?: las 4 condiciones existentes (c1, c2, c3-bloque-turnos, c4-respuesta-fija-sin-reescritor) quedan byte a byte iguales y solo se agrega c5-sin-reescritor-v7; combinator sigue 'and' y options.typeValidation 'loose'. CHECK apply: `nuevo.conditions[:4] == viejo.conditions` y `len == 5`.
- Triaje: Evaluar: el jsCode vivo PRE == gate_red_flags.js + '\n\n' + evaluar.js(HEAD, prompt json.dumps ensure_ascii=False) (drift cero; aborta si no, para no pisar un cambio hecho en n8n); el POST == misma construcción con evaluar.js parcheado; la ancla vieja aparece exactamente 1 vez. `node tests/test_triaje_nodos.js` (46 + 2 nuevos) y `node triaje/test_gate.js` (29) en verde antes del PUT; `python scripts/check_triaje.py` en verde (regla 9) y su salida piloto= vacío o incluye 5491161461034. 'Triaje: Decidir' no se toca (CHECK: jsCode PRE == POST).
- Memoria: en el camino v7 ningún Sub-Agent corre, así que 'Postgres Chat Memory' (ai_memory de Sub-Agent Confirmar/Cancelar/Agendar/Urgencia/General, sessionKey $('Preparar Mensaje Final').first().json.phone) no escribe; la única escritura es 'Guardar en memoria' del cerebro (2 filas si vivo && !silencio) con session_id = mismo phone; el adaptador no inserta ni reenvía avisos; canned directo escribe antes del fork; derivación → escribe el triaje (Persistir/Escalar). CHECK apply: el jsCode de 'V7: Adaptador' y 'V7: Derivar a Triaje' no contiene 'INSERT', 'n8n_chat_histories' ni 'avisos' en una llamada http (grep), y las conexiones ai_memory de 'Postgres Chat Memory' en POST == PRE. CHECK en prueba: después de un turno v7 con respuesta, `SELECT count(*) FROM n8n_chat_histories WHERE session_id='5491161461034' AND id > <max_id_previo>` == 2 (sources wa_inbound/wa_outbound); tras un silencio v7 == 0.
- Regla dura #3 y PUT limpio: `Webhook - Evolution API`.webhookId === 'evo-webhook-v2' en POST; body del PUT solo con PUT_KEYS (name, nodes, connections, settings, staticData) y settings filtrados por SETTINGS_OK (se preserva errorWorkflow yop6TIVoKiWUxfEn, executionOrder v1, callerPolicy workflowsFromSameOwner); `active` sigue true; abort si versionId del GET previo al PUT != versionId del GET inicial (otra sesión tocó el workflow); backup PRE y POST en workflows/history/ (crear la carpeta: no existe en este checkout) y refrescar workflows/current con snapshot_v6_live.py.
- Prerequisito verificado por código: GET /workflows/NBHzj8ar2XuSvyIY debe tener un nodo 'Redis GET triaje' y el jsCode de 'Devolver' debe contener 'derivar_triaje'; si no, el apply aborta ANTES de mostrar el diff (hoy el vivo NO lo tiene: versionId 59001df9). También asserta que v7/ids.json['cerebro'] == workflowId.value del nodo 'V7: Cerebro' y que las líneas 17-19 del jsCode vivo de 'Parse Intent' (esUrgenciaFuerte) aparecen textuales dentro del jsCode de 'V7: Pre-Triaje Regex'.
- Nada cambia antes del fork ni en la cadena de envío: Kill-switch Check (ADMINS incluye 5491161461034), Bot enabled?, Dentalink up?, Rate Limit (10/15 min), Es fromMe?, Buffer (22 s), Bot Activo? (takeover 1 h), Check Session Age/Clear Old Memory, Pre-filtro Cierre, Gate Canned Directo/Es Canned Directo?, Es cierre?, Triaje: Redis GET estado/¿Seguimiento?[0], Split en Mensajes, Gate Error Tecnico, Tiene respuesta?, Loop Mensajes, Evolution - Typing, Gate Humano Final, Evolution API - Enviar Mensaje, PG - Delete NO_REPLY: todos con parameters PRE == POST (cubierto por el check de 'solo 6 nodos cambiados').

## Pruebas tras el PUT (celular de Lucas) y teardown

1. PRE-0 (sin red desde acá; en la máquina de Lucas): `python scripts/check_triaje.py` en verde y anotar `piloto=` (debe ser vacío o incluir 5491161161034… corregir: 5491161461034). Confirmar que el cerebro vivo ya tiene 'Redis GET triaje' (re-deploy con `python scripts/crear_v7_en_n8n.py --aplicar` si no; luego `python scripts/snapshot_v6_live.py` no aplica al cerebro: guardar GET del cerebro en workflows/current/v7/). Correr `node tests/test_triaje_nodos.js`, `node triaje/test_gate.js`, `node tests/test_banlist_usted.mjs`, `python tests/test_v7_cerebro.py`, y las suites que tocan los nodos editados: tests/test_canned_sidecar.py, tests/test_gate_pago_tratamiento.py, tests/test_e2e_bateria.py, tests/test_matriz_casos.py. Arreglar ANTES scripts/limpiar_numero_demo.py: lee el token de Chatwoot del nodo 'Re-check Humano', que YA NO EXISTE en el v6 (Chatwoot eliminado 05/10) → hoy crashea; reemplazar esa parte por el wipe de tests/test_runner_aislado.py líneas 158-160 (DELETE n8n_chat_histories por session_id + UPDATE pacientes SET human_takeover=false, human_takeover_at=NULL) y sumar el DEL de claves Redis (vía SSH al VPS: `docker exec redis-rwlw-redis-1 redis-cli DEL triaje:5491161461034 v7:tel:5491161461034` + `python scripts/probar_v7.py --activar` → `--destino reset --campo tel=5491161461034` → `--desactivar`, que borra ficha/turnos_vistos/ofertas/lotes/bloque/bloque_req/propuesta/pago).
2. PRE-1 limpieza del celular de Lucas (regla 9): limpiar_numero_demo.py --phone 5491161461034 --apply --borrar-logs (ya arreglado); verificar que NO existe `v7:tel:5491161461034` ni `triaje:5491161461034` en Redis (`redis-cli EXISTS ...` → 0) y que pacientes.human_takeover=false para ese teléfono. Anotar `SELECT max(id) FROM n8n_chat_histories` como marca.
3. PUT: `python scripts/apply_v7_flag_lucas.py` (simulación: muestra diff de los 6 nodos editados, los 8 nodos nuevos y la tabla de conexiones quitadas/agregadas) → OK explícito de Lucas → `--apply` (backup PRE, PUT, GET, backup POST, verificaciones de los invariantes, snapshot_v6_live.py). Si una verificación falla: `python scripts/restaurar_workflow.py workflows/history/O155MqHgOSaNZ9ye_PRE_v7_flag_lucas_<ts>.json --apply`.
4. T0 SIN FLAG (demuestra que el PUT no cambió nada): desde el celular de Lucas mandar 'Hola' → menú de bienvenida (Gate Canned Directo, antes del fork). Mandar 'Quiero saber los horarios de atención' → en la ejecución de n8n: 'V7: Redis GET modo' ejecutado con v7_modo null, 'V7: ¿Vivo?' por la salida false, 'Router - Clasificar Intent' y 'Parse Intent' ejecutados, ningún 'V7: Cerebro'; la respuesta es la del v6 (vos/hs, Formatting Agent ejecutado). Esperar ≥25 s entre mensajes (buffer 22 s) y contar: máximo 10 mensajes por 15 min (Rate Limit) — el 11º se descarta en silencio en 'Rate Limit Excedido (NoOp)' y parece que 'el v7 no contestó'.
5. T1 ACTIVAR FLAG: en el VPS `docker exec redis-rwlw-redis-1 redis-cli SET v7:tel:5491161461034 vivo` (doc §4 tabla: sin TTL; para el piloto se puede usar `EX 86400` como autorollback — ver dudas). Mandar 'Buen día, ¿cuánto sale la primera consulta?' → ejecución: 'V7: ¿Vivo?' true, 'V7: Pre-Triaje Regex' urgencia_regex false, 'V7: Cerebro' ejecutado, 'Router - Clasificar Intent' NO ejecutado, 'V7: Adaptador' caso 'texto', 'Fallback Output' passthrough, log '[BANLIST] passthrough v7', 'Necesita Formatting?' por la salida false (Formatting Agent NO ejecutado), mensaje enviado en usted; verificar que el texto recibido en WhatsApp == texto que devolvió 'Devolver' (sin reescritura ni canned anexado); DB: exactamente 2 filas nuevas en n8n_chat_histories para 5491161461034 (human 'wa_inbound' + ai 'wa_outbound') y ninguna otra; grupo: sin avisos.
6. T2 SILENCIO: mandar 'Muchas gracias, buenísimo!' (no está en CIERRES de Fallback Output pero sí es cierre para HistorialCore.esCierre) → cerebro '¿Es un cierre?' true → 'Cierre sin respuesta' → adaptador caso 'silencio' → ejecución termina en 'PG - Delete NO_REPLY' → 'Descartar [NO_REPLY]'; NO llega 'Ya le transmito su consulta a la secretaria'; 0 filas nuevas en memoria.
7. T3 URGENCIA POR REGEX (triaje antes de Asiri): mandar 'Se me salió un bracket y me duele' → 'V7: Pre-Triaje Regex' true → 'V7: Derivar a Triaje' via 'regex' → 'Triaje: Cargar Config' → 'Triaje: Evaluar' con modo_entrada 'nuevo' (ver output del nodo) → ruta_pre 'clasificar' → video/pregunta/escalada según triaje_config; 'V7: Cerebro' NO ejecutado; UNA sola respuesta al paciente (la del triaje); memoria escrita por 'Triaje: Persistir' (source triaje_*). Si escala: un solo aviso [TRIAJE] en el grupo y 'triaje:5491161461034' = paso 'escalado' TTL 3600. Luego mandar 'Listo, ya está, gracias' → entra por 'Triaje: ¿Seguimiento?'[0] (antes del fork): lo cierra el triaje, Asiri no participa. Antes de seguir: `redis-cli DEL triaje:5491161461034` (o esperar el TTL).
8. T4 URGENCIA SIN PALABRA CLAVE (Asiri deriva; caso Mariela): mandar 'Mi hija está incómoda con el aparato y no come desde ayer' (regex pre-fork da false, verificado offline) → 'V7: Cerebro' → Asiri llama derivar_triaje → 'Devolver' con derivar_triaje true → 'V7: Adaptador' caso 'derivar_triaje' → 'V7: ¿Deriva a triaje?' true → 'V7: Derivar a Triaje' via 'cerebro' → 'Triaje: Cargar Config' → Evaluar modo 'nuevo' → respuesta del triaje; verificar: Asiri NO contestó nada (0 envíos desde Evolution API - Enviar Mensaje), una sola respuesta del triaje, la memoria la escribió el triaje (0 filas 'wa_outbound' nuevas), ningún aviso duplicado. Si en cambio el adaptador loguea caso 'silencio' con enviar=false y el paciente no recibe nada → el cerebro vivo no tiene el contrato derivar_triaje (prerequisito 0 incumplido): DEL flag inmediato.
9. T5 AGENDA CON LA FICHA DE PRUEBA ('Test - Lucas'): 'Quiero cambiar mi turno' → ver_turnos → buscar_horarios → el bloque 'Tenemos los próximos turnos disponibles:' llega TEXTUAL (sin Formatting Agent; Split en Mensajes lo deja: original == formateado) → elegir uno → read-back → 'Sí' en el mensaje siguiente → ejecutar_propuesta → verificar en Dentalink la cita nueva y la vieja anulada, un aviso [FYI/ACCIÓN] en el grupo desde el cerebro y NINGUNO desde Gate Pago Tratamiento/Banlist; p95 observado desde que llega el último mensaje hasta el envío (restar 22 s de buffer). Teardown de agenda al terminar (patrón tests/examen_v7.py: anular toda cita viva de la ficha de prueba, borrar sus recordatorios_enviados; comentario 'TEST v7').
10. T6 PAGO/HUMANO (interacciones con la cadena de salida): 'Quiero pagar la cuota del tratamiento, ¿cómo hago?' → respuesta de Asiri intacta (Gate Pago Tratamiento NO la pisa), un solo aviso del cerebro si corresponde. 'Quiero hablar con la secretaria' → pasar_a_humano (motivo pidio_persona verificado) → Helper notify-grupo con tomar=true; verificar que la despedida de Asiri SÍ se envió (Gate Humano Final lee pacientes.human_takeover; el Helper espera ~20 s antes de activar el takeover, memory/current-state.md 05/10) y que el siguiente mensaje de Lucas lo frena 'Bot Activo?' (antes del fork). Luego UPDATE pacientes SET human_takeover=false para seguir.
11. T7 ROLLBACK SIN PUT: `redis-cli DEL v7:tel:5491161461034` → mandar 'Quiero sacar un turno' → ejecución por 'V7: ¿Vivo?' false → Router → v6 contesta como siempre. (Opcional T8, con flag puesto: desactivar temporalmente nada; para probar el camino {error} usar el harness offline, no producción.)
12. TEARDOWN OBLIGATORIO (mismo turno, regla 9): `redis-cli DEL v7:tel:5491161461034 triaje:5491161461034`; `python scripts/probar_v7.py --activar` → `--destino reset --campo tel=5491161461034` → `--desactivar` (8 claves v7 del teléfono); `python scripts/limpiar_numero_demo.py --phone 5491161461034 --apply --borrar-logs` (memoria n8n_chat_histories, pacientes.human_takeover=false, triaje_urgencias_log/escalaciones_log de prueba); anular en Dentalink las citas de prueba creadas en T5 y borrar sus recordatorios_enviados; borrar las filas de mensajes_entrantes_live del teléfono si se usan para métricas; dejar constancia en el sessions log del vault (no en el repo) de los ids de ejecución de T1-T7 y de que el flag quedó borrado (`redis-cli EXISTS v7:tel:5491161461034` → 0).

## Dudas para Lucas

- PREREQUISITO: el cerebro VIVO (NBHzj8ar2XuSvyIY, versionId 59001df9, 12:18) no tiene 'Redis GET triaje' ni devuelve derivar_triaje. ¿OK para re-deployarlo con `crear_v7_en_n8n.py --aplicar` (actualiza por nombre, también las herramientas) antes del PUT al v6? Sin eso, una urgencia que Asiri derive termina en silencio para el paciente. El apply del v6 lo verifica y aborta si falta.
- Red flags pre-fork: recomiendo NO (solo esUrgenciaFuerte, paridad exacta con lo que hoy manda al triaje a todos; gate_red_flags.js líneas 12-14 avisa falsos positivos sobre todos los mensajes: 'tuve un accidente, necesito cambiar el turno' escalaría + takeover 1 h). ¿Confirmás, o preferís el flag --red-flags-pre-fork sabiendo el costo?
- Banlist Validator: ¿confirmás la Opción A (passthrough total para _flow='v7', el cerebro ya corrió BanlistUsted + ChequeoSalida)? La alternativa B (skip solo de las reglas 43-47 + canned en usted) deja las reglas 50/51 ('ahora mismo'/'lo antes posible' + clínica) que bloquearían frases legítimas de Asiri como 'Le aviso ahora mismo a la clínica'.
- Cómo y quién setea la clave Redis: propongo `docker exec redis-rwlw-redis-1 redis-cli SET v7:tel:5491161461034 vivo` por SSH al VPS (el Redis del bot no es accesible desde afuera: limpiar_numero_demo.py lo dice). ¿Querés TTL para el piloto (p. ej. EX 86400 = autorollback si nos olvidamos) aunque el doc §4 diga 'sin TTL'? ¿O sumar un `destino: 'v7_flag'` al workflow 'v7 Test' para hacerlo desde scripts/probar_v7.py?
- triaje_config.telefonos_piloto: ¿está vacío (triaje abierto desde 2026-09-10) o incluye 5491161461034? Si no, cualquier urgencia de Lucas en v7 escala con razón 'fuera_piloto' (evaluar.js 161-162). check_triaje.py lo imprime.
- Memoria del v7: la fila ai usa additional_kwargs.source 'wa_outbound' (JS_SALIDA), el mismo source que 'Build fromMe AI memory' (staff) y que 'Clear Old Memory' excluye del borrado por sesión vieja (`NOT IN ('wa_outbound','human_takeover','reminder_note')`) → las respuestas del bot v7 nunca se limpiarían como stale. ¿Cambiamos el source a 'bot_v7' en el cerebro en el mismo re-deploy? (Build Router Context no filtra por source: sin efecto en el contexto.)
- Gate Humano Final × pasar_a_humano: si el Helper activa human_takeover en la misma ejecución (hoy espera ~20 s, 'Esperar respuesta del bot (20s)'), la despedida de Asiri podría suprimirse con aviso 'no envió su respuesta'. La política de modo humano (apply_politica_modo_humano.py, nodo 'Decidir Takeover' en el Helper, tomar=true) figuraba 'SIN aplicar' el 05/10 11:30: ¿se aplicó después? El JSON del Helper S5U6tSipzlgFHCkf y de 'v7 Tool - clinica' no están en el repo para verificarlo.
- scripts/limpiar_numero_demo.py está roto desde que se eliminó Chatwoot (lee el token del nodo 'Re-check Humano', que ya no existe en el v6: StopIteration). Hay que arreglarlo (Supabase pacientes + n8n_chat_histories + Redis) ANTES de las pruebas o la regla 9 no se puede cumplir. ¿Lo hago en el mismo PR?
- Latencia/typing: durante los 22 s de buffer + el tiempo del cerebro (Dentalink 8 s de timeout × llamadas, Asiri hasta 5 iteraciones) el paciente no ve 'escribiendo…' (Evolution - Typing corre recién en la salida). ¿Aceptable para el piloto de Lucas, o sumamos un presence temprano antes de 'V7: Cerebro' (nodo HTTP más, fuera de este alcance)? El v6 no tiene executionTimeout.
- Banlist Shadow - Prep/LLM/Log: lo dejo corriendo también para v7 (una llamada gpt-5-nano por mensaje; loguea regex vs agente y sirve de observación del piloto). ¿OK, o lo salteo con `if (prev._flow === 'v7') return [];`?
- Modo 'sombra' (Router Y v7 sin esperar) queda explícitamente fuera: el IF solo acepta 'vivo'. ¿Confirmás que no hace falta para esta etapa (doc §7 punto 3 lo contempla; necesitaría un segundo Execute Workflow con waitForSubWorkflow:false)?
- Scripts nuevos a dejar en el repo: scripts/apply_v7_flag_lucas.py (diff + backup PRE/POST + verificaciones), tests/test_v7_fork_v6.py (harness diferencial de las guardas + los 3 Code nuevos, los casos ya corridos hoy) y los 2 casos nuevos en tests/test_triaje_nodos.js; check_triaje.py suma los asserts del fork. ¿Nombres OK?

## Verificación del revisor escéptico

- **#0** ✅ sostiene — Verificado contra workflows/current/v7/cerebro_NBHzj8ar2XuSvyIY.json (versionId 59001df9, updatedAt 2026-10-06T12:18:19Z, 32 nodos): la lista de nodos es '... Redis GET bloque, Redis GET bloque_exec, Salida ...' sin 'Redis GET triaje'; el jsCode de 'Devolver' devuelve {texto, enviar, silencio, modo, motivo_chequeo, motivo_banlist, fallo_agente, tools...} sin derivar_triaje; el string 'derivar_triaje' aparece 0 veces en TODO el JSON vivo (o sea Asiri ni siquiera tiene la tool). En 'Salida' vivo línea 177 `if (texto === '[NO_REPLY]' && !hayOk) silencio = true;` → el adaptador mandaría '[NO_REPLY]' y el paciente queda sin respuesta: el agujero es real. scripts/v7_workflow_cerebro.py sí lo tiene (l.83 pj('Redis GET triaje'...), l.101 `if (triaje && !hayOk) { derivar_triaje = true; silencio = true; texto = null; }`, l.153 g.redis_get('Redis GET triaje', 'triaje_v7:'+tel+':'+$execution.id), l.159 Devolver con derivar_triaje/triaje). También confirmé que 'Cierre sin respuesta' es terminal (connections: ¿Es un cierre?[0] → Cierre sin respuesta → nada) y ya devuelve derivar_triaje:false, así que el Execute Workflow recibe ese item sin pasar por Devolver. **Corrección:** El check del apply queda corto: la tool viva 'v7 Tool - clinica' (workflows/current/v7/clinica_1vMZN7MMPicq0h0v.json, versionId 59073f3d) TAMPOCO tiene 'Redis SET triaje' (0 ocurrencias de 'triaje_v7'; la marca la pone scripts/v7_workflow_clinica.py l.18). Si alguien redeployara solo el cerebro, derivar_triaje no dejaría marca → Salida ve triaje null → silencio otra vez. El apply debe hacer GET también de ids.json['clinica'] y abortar si falta el nodo 'Redis SET triaje', y verificar que el cerebro tenga una tool llamada derivar_triaje conectada a Asiri (ai_tool). Aclarar además que crear_v7_en_n8n.py --aplicar re-PUTea los 9 workflows v7 (7 tools + cerebro + 'v7 Test (sombra)'), no solo el cerebro; todos sin puerta de entrada activa, pero decirlo.
- **#1** ✅ sostiene — 'Triaje: Redis GET estado' vivo: type n8n-nodes-base.redis typeVersion 1, parameters {operation:'get', propertyName:'triaje_estado', key:"={{ 'triaje:' + $('Preparar Mensaje Final').first().json.phone }}", keyType:'string', options:{}}, credentials.redis.id 'kdtSKwGbN1xAZeUh', alwaysOutputData true, onError 'continueRegularOutput' — el clon propuesto es idéntico salvo propertyName/key. Posición [10816,1680] libre: en x 10400-13200 el nodo más bajo es 'Triaje: Decidir'/'Triaje: Ruta Pre' en y=1376; con y>1400 solo hay Triaje: Log Silencio (13520,1600), la fila de escalada (y=1824, x≥13520) y Media staff (x≤7568). 'Preparar Mensaje Final' corre antes (es la fuente de Build Router Context) y su phone = $('Edit Fields - Extraer Datos').first().json.phone (línea 19 del nodo), el mismo que usa Kill-switch Check (ADMINS l.22-26) y el sessionKey de 'Postgres Chat Memory'.
- **#2** ✅ sostiene — 'Triaje: ¿Seguimiento?' vivo es if 2.2 con options {caseSensitive:true, leftValue:'', typeValidation:'loose', version:2} y condición `={{ $json.triaje_estado || '' }}` notEmpty: el clon con string equals 'vivo' respeta la forma. Con Redis caído el item es {error} (onError continueRegularOutput) → `$json.v7_modo || ''` = '' → false → salida [1] → Router. Hoy el Router recibe exactamente ('Triaje: ¿Seguimiento?', main[1]) y ('Triaje: Ruta Pre', main[2]), ambos index 0 (connections del JSON vivo), más 'Router LM' por ai_languageModel; el Router no lee $json (parameters.text usa $('Build Router Context') y $('Preparar Mensaje Final')) y Parse Intent lee $input.first().json.output del agente, así que cambiar el item de entrada por {v7_modo:null} no afecta a nadie.
- **#3** ✅ sostiene — Las líneas 17-19 del jsCode vivo de 'Parse Intent' (esUrgenciaFuerte con la guarda de negación) están byte a byte dentro del jsCode propuesto (comprobado con Python: `l17_19 in pre` → True). Corrí el código con tests/harness_code_node.mjs: 'se me salió un bracket y me duele'→true, 'quiero cambiar el turno, sin dolor'→false, 'no va porque tiene fiebre'→true, 'hola, quiero sacar un turno'→false, 'Mi hija esta incomoda, no come desde ayer con el aparato'→false, 'se le cayo el aparato'→true. Paridad con Parse Intent l.26 (`if (esUrgenciaFuerte) intent = 'urgencia_dolor'`) → Switch sobre Intent[2] (rule outputKey 'urgencia' = 'urgencia_dolor') → Triaje: Cargar Config. La cabecera de triaje/gate_red_flags.js l.12-14 efectivamente prohíbe correrlo sobre todos los mensajes. Posición [11408,1680] libre.
- **#4** ✅ sostiene — Misma forma que Grafo.si en scripts/v7_lib.py l.44-49 (if 2.2, typeValidation strict, operator boolean/true/singleValue) y que 'Es cierre?' vivo (`={{ $json.skip }}` boolean true). El item de entrada {_flow:'v7', urgencia_regex:bool} lo emite el nodo anterior; [0]=true → Derivar, [1]=false → Cerebro.
- **#5** ✅ sostiene — 'Execute Sub-WF Cancelar' vivo: executeWorkflow 1.2, workflowId {__rl, value, mode:'id'}, workflowInputs {mappingMode:'defineBelow', value:{phone,text,pushName}, matchingColumns:[], schema:[]}, options {}, alwaysOutputData true, continueOnFail true — el clon respeta la forma (ojo: el original usa $('Edit Fields - Extraer Datos').phone; el propuesto usa Preparar Mensaje Final.phone, que es el mismo valor por la línea 19 de ese nodo). El trigger vivo del cerebro es 'Entrada' executeWorkflowTrigger 1.1 inputSource jsonExample {phone, texto, pushName, modo, historial_json}; 'Armar contexto' l.91 trata historial_json como opcional (try/parse). 'Edit Fields - Extraer Datos' sí tiene pushName. v7/ids.json cerebro = NBHzj8ar2XuSvyIY. El cerebro no manda WhatsApp por su cuenta (0 ocurrencias de sendText/Evolution en su JSON): devuelve texto. Settings del cerebro callerPolicy 'workflowsFromSameOwner' (mismo owner). Nota: en v1.2 defineBelow n8n mergea el item de entrada con los valores definidos ({...item.json, ...values}), así que Entrada recibe también {_flow:'v7', urgencia_regex:false}: inocuo.
- **#6** ✅ sostiene — Sintaxis y comportamiento verificados con tests/harness_code_node.mjs (7 entradas): texto normal → caso 'texto'; {derivar_triaje:true, modo:'vivo'} → '[NO_REPLY]' + derivar_triaje:true; {derivar_triaje:true, modo:'sombra'} → 'silencio'; {texto:null, enviar:false, silencio:true} (cierre del cerebro vivo) → '[NO_REPLY]'; {error:{message:'boom'}}, {} y {texto:'', enviar:true} → CANNED_FALLO (el helpers.httpRequest ausente cae en el try/catch). CANNED_FALLO es byte a byte el de 'Format Sub-WF Output' l.8 y 'Gate Error Tecnico' l.3. La cadena de descarte existe: 'Necesita Formatting?' c2 notContains '[NO_REPLY]' → [1] 'Split en Mensajes' → 'Gate Error Tecnico' → 'Tiene respuesta?' notContains → [1] 'PG - Delete NO_REPLY' (ORDER BY id DESC LIMIT 1, sin fecha) → 'Descartar [NO_REPLY]'. 'Banlist Shadow - Prep' l.9 devuelve [] con '[NO_REPLY]'. **Corrección:** Gap menor a documentar: en los casos 'error_subworkflow'/'sin_texto' el CANNED_FALLO se envía pero NO queda en n8n_chat_histories (el cerebro no guardó y el v6 no guarda en el camino v7; 'Postgres Chat Memory' solo cuelga por ai_memory de los 5 Sub-Agents), así que el turno siguiente de Asiri no ve ese intercambio. Aceptable para el piloto, pero anotarlo.
- **#7** ✅ sostiene — Misma forma Grafo.si. El item que llega a 'Fallback Output' por [1] es {output, _flow:'v7', derivar_triaje:false, _v7}; 'Fallback Output' hoy ya recibe items sin Router/Parse Intent desde 'Es Canned Directo?'[0] y 'Set NO_REPLY' (connections vivas), y ningún nodo aguas abajo referencia $('Parse Intent') fuera de try/catch (Canned Sidecar l.88, Gate Pago l.23) ni $('Router - Clasificar Intent') (0 referencias en los 155 nodos).
- **#8** ✅ sostiene — Harness: via 'regex' con urgencia_regex:true, 'cerebro' con false y 'cerebro' si el nodo no corrió (throw atajado). En el camino cerebro 'V7: Pre-Triaje Regex' SÍ corrió (está antes de '¿Urgencia regex?'), así que $() no tira. 'Triaje: Cargar Config' vivo es postgres 2.5 executeQuery estático (SELECT ... FROM triaje_config c WHERE c.id = 1), alwaysOutputData, sin $json ni $(): el item de entrada no importa. Entradas actuales de Cargar Config: ('Switch sobre Intent',2) y ('Triaje: ¿Seguimiento?',0). Scan de los 21 nodos 'Triaje:*': el único uso de $('Parse Intent') es el isExecuted de 'Triaje: Evaluar'; el resto lee Preparar Mensaje Final / Build Router Context / Triaje: Redis GET estado / nodos Triaje previos. Ningún nodo (ni decidir.js, preparar_escalada.js, escalar_notify.js) lee modo_entrada aguas abajo. telefonos_piloto: evaluar.js l.161-162 (vivo l.226-227) → razón 'fuera_piloto'; check_triaje.py l.41-42 imprime piloto=. Posición [11712,1904] libre.
- **#9** ✅ sostiene — connections['Triaje: ¿Seguimiento?'] vivo = main[0] → Triaje: Cargar Config; main[1] → Router - Clasificar Intent index 0. El item por [1] es {triaje_estado:null} (Redis v1 get emite item nuevo) y nadie lo lee por $json aguas abajo.
- **#10** ✅ sostiene — Redirección válida; 'V7: Redis GET modo' acepta cualquier item (no lee $json).
- **#11** ✅ sostiene — 'Triaje: Ruta Pre' vivo (switch 3.2): rules [0] 'clasificar' → Triaje: Clasificar (gpt-5-mini) + Triaje: Merge Clasificación, [1] 'decidido' → Triaje: Decidir, [2] 'normal' → Router - Clasificar Intent index 0, options.fallbackOutput 'extra' → main[3] → Triaje: Preparar Escalada. Coincide con el plan.
- **#12** ✅ sostiene — El item de Evaluar (triaje:true, ruta_pre:'normal', cfg, estado...) se pierde en el Redis GET (emite item nuevo); el adaptador no hace spread de $json y los nodos V7 no lo leen.
- **#13** ✅ sostiene — Cadena interna del fork; nodo nuevo, sin colisión de nombre ('V7: ' no existe en el vivo).
- **#14** ✅ sostiene — Tras el cambio las entradas main del Router serían solo ('V7: ¿Vivo?',1); 'Router LM' sigue por ai_languageModel. La salida false reproduce el destino actual (Router, index 0).
- **#15** ✅ sostiene — Cadena interna.
- **#16** ✅ sostiene — [0]=true (urgencia) → Derivar; [1]=false → Cerebro. Coherente con la semántica del IF v2.2 (salida 0 verdadero).
- **#17** ✅ sostiene — Cadena interna.
- **#18** ✅ sostiene — Cadena interna.
- **#19** ✅ sostiene — Entradas main actuales de 'Fallback Output' (8, verificadas): Sub-Agent Confirmar/Cancelar/Agendar/Urgencia/General, Set NO_REPLY, Format Sub-WF Output, Es Canned Directo?[0]. Cadena de salida verificada en connections: Fallback Output → Canned Sidecar → Gate Pago Tratamiento → Banlist Validator → (Necesita Formatting? + Banlist Shadow - Prep) → Split en Mensajes → Gate Error Tecnico → Tiene respuesta? → Loop Mensajes → Evolution - Typing → Gate Humano Final → Evolution API - Enviar Mensaje.
- **#20** ✅ sostiene — check_triaje.py l.65 ya asserta conns['Switch sobre Intent']['main'][2][0]['node'] == 'Triaje: Cargar Config'; sumar el del fork es coherente. Sin loop: desde Cargar Config, Evaluar en modo 'nuevo' nunca devuelve ruta_pre 'normal' (evaluar.js l.157-167: config_no_disponible/triaje_inactivo/fuera_piloto → decidido, si no clasificar), así que Ruta Pre[2] no vuelve a dispararse.
- **#21** ✅ sostiene — Ancla `return items.map(it => {\n  let output = (it.json.output || '').trim();` aparece 1 vez en el jsCode vivo (l.16-17); CIERRES l.12, esCierrePuro l.13, canned l.20-22, `return { json: { ...it.json, output } }` l.27: todo coincide. Diferencial corrido con el harness: {output:'texto'}, {output:'[NO_REPLY]'}, {output:'texto', _flow:'cancelar_subwf'} → IGUAL viejo/nuevo; solo {output:'[NO_REPLY]', _flow:'v7'} cambia (viejo: canned secretaria; nuevo: '[NO_REPLY]'). Único emisor actual de _flow: 'Format Sub-WF Output' ('cancelar_subwf' / 'cancelar_subwf_fallback').
- **#22** ✅ sostiene — Ancla `const items = $input.all();\n\n// --- 1. texto REAL del paciente` única (l.15-17). $('Parse Intent') en try/catch l.88 → intent '' (sin freno por urgencia); TEXTOS l.107-108 con precio/pago hardcodeados l.94-95 (BRUBANK). Diferencial: con texto del paciente 'quiero saber el alias para pagar la cuota...' el viejo ANEXA el canned de pago a un output v7; el nuevo lo deja pasar; los 3 items v6 idénticos.
- **#23** ✅ sostiene — Ancla `const items = $input.all();\n\nlet pacienteMsg = '';` única (l.12-14). El gate REEMPLAZA el output por CANNED (l.51, l.73) y hace POST a notify-grupo (l.77-86). Diferencial: con 'pagar la cuota del tratamiento' el viejo pisa el output v7 por el canned + gate_pago_tratamiento:true; el nuevo deja el item; v6 idéntico.
- **#24** ✅ sostiene — Ancla `const item = $input.first().json;\nconst output = (item.output || '').toString();` única (l.6-7). 19 reglas en l.43-63 (9 invitaciones/imperativos l.43-51, 7 instrucciones l.53-59, 3 diagnóstico l.61-63); CANNED voseo l.82; POST l.89-96; retorno sin bloqueo l.112 `{ ...item, banlist_triggered: null, escalate_to_human: false }` = la forma que emite el passthrough. Regla l.45 `(los|las|te|le|la|lo|...)\s*esperamos` y l.47 `(la|lo)\s+esperamos` bloquean 'Lo esperamos el día de su turno' (diferencial: viejo → canned 'Recibimos tu mensaje...' + escalate_to_human:true; nuevo → passthrough); l.50 `ahora mismo .{0,50} clínica` y l.51 `lo antes posible .{0,50} clínica|venir` bloquearían 'Le aviso ahora mismo a la clínica'. No se puede desconectar: 'Split en Mensajes' l.40 y 'Gate Humano Final' l.28 (fuera de try) hacen $('Banlist Validator').first(). v7/banlist_usted.js l.29-41: INVITA incluye `(los|las|lo|la|te|le|les)\s+esperamos` y bloquea solo con INMEDIATO o sin TURNO_CONCRETO; tests/test_banlist_usted.mjs l.31-35 fijan como permitidas 'Lo esperamos.' tras turno con fecha y 'Los esperamos el día de su consulta.'. 'Banlist Shadow - Prep' lee escalate_to_human/banlist_triggered (l.10-11) y sigue funcionando.
- **#25** ✅ sostiene — 'Necesita Formatting?' vivo es if typeVersion 2, options {caseSensitive:true, typeValidation:'loose'} (sin key version), combinator 'and', 4 condiciones con ids c1, c2, c3-bloque-turnos, c4-respuesta-fija-sin-reescritor (c4 boolean/false/singleValue, mismo molde que la c5 propuesta). Para items v6 `($json._flow || '') !== 'v7'` evalúa true y el AND queda igual; para v7 → false → salida [1] → Split en Mensajes (connections vivas: [0] Formatting Agent - WhatsApp agent 1.8, [1] Split en Mensajes). _flow sobrevive hasta acá: Fallback devuelve it, Sidecar/Gate devuelven items, Banlist hace {...item}. c4 usa $('Gate Canned Directo').isExecuted, que corre antes del fork en todos los caminos.
- **#26** ✅ sostiene — Verificado: jsCode vivo de 'Triaje: Evaluar' (16.590 chars) == gate_red_flags.js + '\n\n' + evaluar.js con __SYSTEM_PROMPT_JSON__ → json.dumps(prompt_clasificador.md, ensure_ascii=False) (match True). La ancla aparece 1 vez en el vivo (l.132-134) y 1 vez en triaje/evaluar.js (l.67-69). Apliqué el parche en una copia (scratchpad) y `node tests/test_triaje_nodos.js` sigue en verde (fallos: 0; baseline también 0; test_gate 29/29). mkDollar (tests/test_triaje_nodos.js l.30-43) tira 'nodo desconocido' para nombres no listados → corrio() devuelve null → criterio viejo, por eso no rompe; y como l.43 devuelve isExecuted:true para cualquier nombre ≠ 'Parse Intent', al sumar 'V7: Derivar a Triaje' al mock hace falta sí o sí el parámetro v7Executed (si no, todos los casos de seguimiento pasarían a 'nuevo'). Sin el parche, la derivación v7 entra en modo seguimiento y con estado null (l.111 `if (!estado || !estado.paso) return ... ruta_pre 'normal'`) o paso escalado/cerrado (l.153) vuelve a Ruta Pre[2] → fork: el loop descripto es real. Modo nuevo l.157-167 nunca devuelve 'normal'. 'Triaje: Decidir' vivo ≠ repo (comprobado), no tocarlo.

### Faltantes señalados

Lo que le falta al plan (todo lo demás lo verifiqué contra workflows/current/v6_LIVE_2026-10-06.json y el repo; las 155 referencias, índices, anclas y posiciones sostienen):

1. PREREQUISITO INCOMPLETO (lo más importante). El apply solo chequea el cerebro, pero la tool viva 'v7 Tool - clinica' (1vMZN7MMPicq0h0v, versionId 59073f3d) tampoco tiene 'Redis SET triaje' (0 ocurrencias de 'triaje_v7' en su JSON) y en el cerebro vivo el string 'derivar_triaje' aparece 0 veces (Asiri ni tiene la tool). El apply debe: GET de ids.json['clinica'] → exigir nodo 'Redis SET triaje'; GET del cerebro → exigir 'Redis GET triaje', que 'Devolver' contenga 'derivar_triaje' Y que exista una tool 'derivar_triaje' conectada por ai_tool a 'Asiri'. Y decir explícito que `crear_v7_en_n8n.py --aplicar` re-PUTea los 9 workflows v7 (7 tools + cerebro + 'v7 Test (sombra)', que además regraba data/v7_test_ruta.txt), no "un workflow".

2. Test ofensivo de no-regresión del Router que falta: el plan nunca prueba que un teléfono SIN flag con urgencia siga llegando al triaje por el camino viejo (T0 solo prueba 'Hola' y horarios). Sumar a T0 un mensaje tipo 'me duele la muela' desde un número sin flag (o el de Lucas antes de T1) y verificar 'V7: ¿Vivo?' false → Router → Parse Intent → Switch[2] → Triaje: Cargar Config → Evaluar con modo_entrada 'nuevo' (es justamente el nodo que se edita).

3. Memoria en el caso fallo del cerebro: con caso 'error_subworkflow'/'sin_texto' el CANNED_FALLO se envía pero nadie lo guarda en n8n_chat_histories (el cerebro no llegó a 'Guardar en memoria' y en el camino v7 'Postgres Chat Memory' no corre). Decidir si el adaptador inserta las 2 filas en ese caso o se acepta el hueco (anotarlo en el sessions log).

4. Doc referenciado mal: no existe §7.3 en docs/v7-arquitectura-agente-asiri.md; es §7 punto 3 (l.122-132). Ese punto NO menciona el passthrough del Banlist Validator (el doc §5 dice que el banlist se reescribe en usted dentro del cerebro) — la Opción A es una decisión nueva, dejarla explícita para Lucas (ya está en dudas, pero el detalle del cambio 24 la presenta como 'doc lo pide').

5. Limpieza de Redis sin SSH: limpiar_numero_demo.py l.8/l.90 dice que Redis no es accesible desde afuera; el teardown del plan depende de `docker exec redis-rwlw-redis-1 redis-cli DEL ...`. Si Lucas no quiere SSH en cada prueba, conviene sumar el `destino 'v7_flag'`/'reset' al workflow 'v7 Test (sombra)' (ya borra 8 claves por 'reset', scripts/crear_v7_en_n8n.py l.46-55) para SET/DEL de `v7:tel:{tel}` y `triaje:{tel}` desde probar_v7.py. Y arreglar limpiar_numero_demo.py ANTES (l.36 `next(... if n['name'] == 'Re-check Humano')` → StopIteration: el nodo no existe en el vivo; el único nodo con 'chatwoot' hoy es 'Triaje: Decidir').

6. Verificar en el apply que el PUT filtra `availableInMCP` y `binaryMode` (están en settings del GET vivo y NO en SETTINGS_OK → 400 si se mandan); el esqueleto apply_fix_continuidad_flujo.py l.168-169 ya lo hace, confirmar que se copia tal cual.

7. check_triaje.py: además del assert nuevo de 'V7: Derivar a Triaje' → 'Triaje: Cargar Config', agregar el assert de que el Router sigue recibiendo main solo desde 'V7: ¿Vivo?'[1] y que 'V7: ¿Vivo?'.rightValue == 'vivo' (los invariantes del plan lo piden en el apply, pero el check recurrente de la regla 9 también debería cubrirlo).

8. Observación de riesgo no listada: en el camino derivar_triaje se pagan DOS LLM por mensaje (Asiri + Triaje: Clasificar gpt-5-mini) y el paciente espera buffer 22 s + cerebro (Identificar paciente → Dentalink 8 s timeout) + clasificador antes de la primera respuesta del triaje; medir ese p95 en T4 además del de T5.

9. T5 toca Dentalink real con modo 'vivo' para la ficha 'Test - Lucas': confirmar antes que la ficha existe y que `Identificar paciente` la resuelve por el phone 5491161461034 (si el celular está asociado a otra ficha real, ejecutar_propuesta escribiría sobre una cita real).