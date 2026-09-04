# Triaje Fase 2 (piloto alambre_pincha): rama determinística "Triaje: *" entre Switch sobre Intent[2] y Sub-Agent Urgencia, con seguimiento por estado Redis chequeado antes del Switch

Se insertan 15 nodos con prefijo "Triaje: " en el v6. Dos van en el camino principal: `Triaje: Redis GET estado` (entre `Clear Old Memory` y `Pre-filtro Cierre`, lee `triaje:<phone>`) y `Triaje: Hay seguimiento?` (IF entre `Extraer Horarios y Precio` y `Switch sobre Intent`, desvía al triaje si hay estado vigente sin depender del Router). El resto forma UNA rama compartida: `Switch sobre Intent`[2] y `Hay seguimiento?`[0] entran a `Triaje: Preparar` (gate_red_flags.js embebido + arma body del clasificador) → `Triaje: Clasificar (gpt-5-mini)` (httpRequest OpenAI, neverError) → `Triaje: Get Config` (SELECT de `triaje_videos` ⋈ `triaje_config`) → `Triaje: Re-check Humano` (clon del Re-check existente) → `Triaje: Decidir` (Code puro: toda la lógica, fail-closed a `accion='escalar'`) → `Triaje: Log` (INSERT triaje_urgencias_log modo live, RETURNING id) → `Triaje: Switch Acción`. Acciones: video → `Triaje: Enviar Video` (/send/media, fullResponse+neverError) → `Triaje: Enviar Texto` (/send/text salida de emergencia) → `Triaje: Envío OK?` (statusCode 2xx) → `Triaje: PG Escribir` (CTE: 3 filas en n8n_chat_histories con shape idéntico a Postgres - Save fromMe + fila `[TRIAJE VIDEO]` en escalaciones_log origen='triaje' + UPDATE del log) → `Triaje: Redis SET estado` (TTL 7200/1800/1); texto (pregunta guiada o cierre) → mismo camino de envío/persistencia; persistir (cierre silencioso) → PG Escribir directo; normal → `Switch sobre Intent` (con intent forzado ≠ urgencia_dolor, sin loop); escalar / fallback / Envío OK?=false → `Triaje: Redis DEL estado` → `Sub-Agent Urgencia` (intacto, único input ahora es esa rama; su systemMessage recibe un bloque de contexto por expresión desde Decidir para que nunca devuelva [NO_REPLY] tras el triaje); silencio (humano apareció) → nodo existente `Humano Atendiendo (no hacer nada)`. Texto al paciente 100% canned de `triaje_videos`; el LLM solo clasifica JSON. Config editable (tabla + kill-switch `triaje_config.activo` + `telefonos_piloto`) permite apagar el piloto sin PUT. Aviso pasivo: NUNCA vía notify-grupo (aplica label humano y mata el flujo B); se hace con INSERT directo en escalaciones_log origen='triaje' + prefijo `[TRIAJE VIDEO]`, dedupeado con la sombra por escalacion_id, y requiere 2 líneas en `lib/escalaciones.ts` (o se desactiva con `aviso_pasivo=false`). Incluye DDL+seeds, procedimiento de limpieza del 5491161461034, guion de demo de 5 mensajes, tests E2E y rollback.

# Diseño Fase 2 — Triaje de urgencias con video (piloto `alambre_pincha`) en el v6 `O155MqHgOSaNZ9ye`

Verificado contra `workflows/current/v6_LIVE.json` (versionId 99e1e7aa…, updatedAt 2026-09-04T13:22:48Z, 125 nodos, active=true, webhookId `evo-webhook-v2` en `Webhook - Evolution API`). Todo lo que sigue es diseño; no se tocó n8n, Supabase, Redis ni WhatsApp. El script de aplicación (`scripts/apply_triaje_fase2_piloto.py`) DEBE trabajar sobre GET fresco y abortar si las conexiones esperadas no coinciden (patrón `apply_canned_sidecar.py::build`).

## 0. Principios que fijan la forma

1. **Un solo punto de bifurcación** para urgencias nuevas: `Switch sobre Intent` main[2] (`outputKey 'urgencia'`, condición `={{ $json.intent }} equals 'urgencia_dolor'`), hoy → `Sub-Agent Urgencia` (verificado: es su ÚNICO input main). Pasa a → `Triaje: Preparar`.
2. **Seguimiento sin depender del Router**: el estado Redis se lee temprano (`Triaje: Redis GET estado`, en el camino principal, después de `Clear Old Memory`) y se evalúa justo antes del Switch (`Triaje: Hay seguimiento?`). El Router corre igual (una llamada gpt-5-mini "de más" en seguimientos) porque `Extraer Horarios y Precio`/`Parse Intent` son referenciados con `.item`/`.first()` por los sub-agents y gates aguas abajo (Canned Sidecar, Gate Pago, Sub-Agent General); saltarlos rompería la escalación fail-closed. Es el precio de mínimo blast radius.
3. **Sub-Agent Urgencia intacto como fallback**: no se le cambian tools, LM, memoria ni `text`. Se le AÑADE un bloque al final del systemMessage (expresión) que le inyecta el contexto del triaje para que no devuelva `[NO_REPLY]` cuando el triaje ya validó la urgencia.
4. **Fail-closed en cada nodo nuevo**: HTTP con `neverError + fullResponse` y `onError: continueRegularOutput`; Postgres/Redis con `onError: continueRegularOutput` (+ `alwaysOutputData` donde corresponde); los dos Code nodes envuelven TODO en try/catch y ante error devuelven `accion:'escalar'`; `Triaje: Switch Acción` tiene `fallbackOutput` → escalar. Ningún camino termina sin: video+texto enviado, texto enviado, escalación (Sub-Agent Urgencia), flujo normal, o silencio deliberado por humano atendiendo (el mismo NoOp que usa el v6 hoy).
5. **Texto al paciente 100% canned** de `triaje_videos`. El LLM solo produce `{tipo, confianza, razon}`. Los textos canned NO pasan por `Formatting Agent - WhatsApp` (son enviados por nodos propios) — por eso el apply script corre los 20 regex del `Banlist Validator` (copiados del nodo vivo en el GET) sobre TODOS los textos de la tabla antes del PUT, y se recomienda que el panel reuse `chequearBanlist` al editar.
6. **Aviso pasivo NUNCA por `notify-grupo`** (ni con `silencioso=true`): el Helper aplica label `humano` siempre (`Chatwoot Apply`) → el bot quedaría mudo y el seguimiento B jamás llegaría. Se usa INSERT directo en `escalaciones_log` con `origen='triaje'` y prefijo `[TRIAJE VIDEO]`, dentro de la misma transacción CTE que persiste la memoria.

## 1. Dónde se bifurca (conexiones exactas)

| Cambio | Antes (verificado) | Después |
|---|---|---|
| A | `Clear Old Memory` main[0] → `Pre-filtro Cierre` | `Clear Old Memory` main[0] → **`Triaje: Redis GET estado`** main[0] → `Pre-filtro Cierre` |
| B | `Extraer Horarios y Precio` main[0] → `Switch sobre Intent` | `Extraer Horarios y Precio` main[0] → **`Triaje: Hay seguimiento?`**; IF[1 false] → `Switch sobre Intent`; IF[0 true] → `Triaje: Preparar` |
| C | `Switch sobre Intent` main[2] → `Sub-Agent Urgencia` | `Switch sobre Intent` main[2] → **`Triaje: Preparar`** |
| D | (nuevo) | `Triaje: Switch Acción`[normal] → `Switch sobre Intent` (segunda entrada al Switch; el item lleva `intent` ≠ `urgencia_dolor` garantizado por Decidir) |
| E | (nuevo) | `Triaje: Redis DEL estado` main[0] → `Sub-Agent Urgencia` (pasa a ser el ÚNICO input main del sub-agent) |
| F | (nuevo) | `Triaje: Switch Acción`[silencio] → `Humano Atendiendo (no hacer nada)` (NoOp existente, sin nodos nuevos) |

Nada más cambia: `Sub-Agent Urgencia` main[0] → `Fallback Output` queda igual; los outputs 0,1,3,4,5 del Switch quedan iguales; `Es cierre?`[0] → `Set NO_REPLY` sigue saltando todo (los emoji-only/injection nunca entran al triaje, correcto).

Por qué A está en `Clear Old Memory → Pre-filtro Cierre` y no justo antes del Switch: el nodo Redis v1 `get` emite un item NUEVO `{ triaje_estado }` (descarta los campos de entrada, como se ve en `Redis GET bot:status` → `Bot enabled?` y en `Rate Limit Eval` leyendo `Object.values(inp)[0]`). Si estuviera justo antes del Switch, `$json.intent` desaparecería y se romperían LOS 5 INTENTS. En ese tramo `Pre-filtro Cierre` lee `$('Preparar Mensaje Final')`, `Es cierre?` lee `$json.skip` (de Pre-filtro), Router/Parse Intent leen `$()`/`$input` propios → cero impacto. Ahí también corre para todos los mensajes ANTES del Router, que es lo que pide el ángulo ("no depender de cómo clasifica el Router").

## 2. Nodos nuevos (15; todos con prefijo `Triaje: `, ids slug, posiciones relativas a `Switch sobre Intent` [11808,272] / `Sub-Agent Urgencia` [12352,544])

Credenciales a reusar (ids del GET): Redis `{"redis": {"id":"kdtSKwGbN1xAZeUh","name":"Redis account"}}`, Postgres `{"postgres": {"id":"TpYhZX4UT61xAKSV","name":"Postgres Supabase Nexora v3"}}`, OpenAI `{"openAiApi": {"id":"nYujqfon7GGDnJUO","name":"OpenAi account"}}`. Headers Evolution (`apikey`, valor omitido) y Chatwoot (`api_access_token`, valor omitido) se copian con `copy.deepcopy(...headerParameters)` de `Evolution API - Enviar Mensaje` y `Re-check Humano` EN EL MOMENTO DEL APPLY — el script nunca contiene valores.

### 2.1 `Triaje: Redis GET estado` — `n8n-nodes-base.redis` v1
```json
{"parameters": {"operation": "get", "propertyName": "triaje_estado",
  "key": "={{ 'triaje:' + $('Preparar Mensaje Final').first().json.phone }}", "options": {}},
 "onError": "continueRegularOutput", "credentials": {"redis": REDIS_CRED}, "position": [10336, 544]}
```
Key ausente → `triaje_estado: null`. Redis caído → item con `error` → el IF evalúa false → flujo normal (Redis caído ya mata el bot antes en `Redis GET bot:status`, no se agrega riesgo). `Clear Old Memory` tiene `alwaysOutputData: true`, así que siempre hay 1 item de entrada.

### 2.2 `Triaje: Hay seguimiento?` — `n8n-nodes-base.if` v2.2
Condición boolean `true` (options `caseSensitive:true, typeValidation:'strict', version:2`):
```
={{ (() => { try { const s = $('Triaje: Redis GET estado').first().json.triaje_estado; if (!s || typeof s !== 'string' || !s.startsWith('{')) return false; const e = JSON.parse(s); return e && (e.paso === 'pregunta' || e.paso === 'video_enviado'); } catch (e) { return false; } })() }}
```
Salidas: [0 true] → `Triaje: Preparar`; [1 false] → `Switch sobre Intent`. El IF pasa el item de `Extraer Horarios y Precio` intacto (`output, intent, text, horarios, precio_consulta`). Posición [11600, 272]; mover `Switch sobre Intent` no es necesario (n8n no exige layout).

### 2.3 `Triaje: Preparar` — `n8n-nodes-base.code` v2 (inputs: `Switch sobre Intent`[2], `Triaje: Hay seguimiento?`[0])
`jsCode = GATE_JS + '\n\n' + WRAPPER` donde `GATE_JS` = contenido literal de `triaje/gate_red_flags.js` (fuente única, 29/29 tests; el `module.exports` guardado con `typeof module` ya está probado embebido en n8n, exec 269428). WRAPPER:
```js
const SYSTEM_PROMPT = <json.dumps(SYSTEM_PROMPT_TRIAJE)>; // ver 2.3.1
const MODELO = 'gpt-5-mini';
try {
  const pm = $('Preparar Mensaje Final').first().json;
  const texto = (pm.text || '').toString();
  const phone = (pm.phone || '').toString();
  let estado = null;
  try { const raw = $('Triaje: Redis GET estado').first().json.triaje_estado;
        if (raw && typeof raw === 'string' && raw.startsWith('{')) estado = JSON.parse(raw); } catch (e) { estado = null; }
  if (estado && estado.paso !== 'pregunta' && estado.paso !== 'video_enviado') estado = null;
  let ctx = ''; try { ctx = ($('Build Router Context').first().json.ctx || '').toString().slice(-1500); } catch (e) { ctx = ''; }
  let prefiltro_reason = ''; try { prefiltro_reason = ($('Pre-filtro Cierre').first().json.reason || '').toString(); } catch (e) {}
  let intent = ''; try { intent = ($('Parse Intent').first().json.intent || '').toString(); } catch (e) {}
  const modo = estado ? 'seguimiento' : 'nuevo';
  const gate = gateRedFlags(texto);
  let user;
  if (modo === 'seguimiento' && estado.paso === 'pregunta') {
    user = 'MENSAJE ORIGINAL DEL PACIENTE:\n' + (estado.texto_original || '') +
           '\n\nPREGUNTA QUE LE HIZO EL BOT:\n' + (estado.pregunta || '') +
           '\n\nRESPUESTA DEL PACIENTE:\n' + texto;
  } else {
    user = 'CONTEXTO RECIENTE DE LA CONVERSACION (puede estar vacio; lo mas nuevo al final):\n' + ctx +
           '\n\nMENSAJE ACTUAL DEL PACIENTE:\n' + texto;
  }
  const llm_body = JSON.stringify({ model: MODELO, reasoning_effort: 'low', max_completion_tokens: 400,
    response_format: { type: 'json_object' },
    messages: [{ role: 'system', content: SYSTEM_PROMPT }, { role: 'user', content: user }] });
  return [{ json: { modo, estado, texto, phone, intent, prefiltro_reason,
                    gate_escala: gate.escala, gate_red_flags: gate.flags, llm_body, modelo: MODELO },
            pairedItem: { item: 0 } }];
} catch (e) {
  // fail-closed: sin body valido el clasificador falla y Decidir escala
  return [{ json: { modo: 'error', estado: null, gate_escala: true, gate_red_flags: ['error_preparar'],
                    triaje_error: String(e && e.message || e), llm_body: '{}' }, pairedItem: { item: 0 } }];
}
```
2.3.1 `SYSTEM_PROMPT_TRIAJE` = el de `scripts/create_triaje_sombra.py` (7 categorías, salida `{"tipo","confianza","razon"}`) con dos líneas más al final: `Si el CONTEXTO muestra que el bot ya envio un video de triaje ("[VIDEO TRIAJE ENVIADO") y el paciente habla del MISMO problema, devolve el mismo tipo.` y `Se conservador: ante duda entre alambre_pincha y otro tipo, usa "otra_urgencia" con confianza "baja".` (el prompt se guarda en `prompts/triaje/clasificador_v1.md` y el script lo lee de ahí).

### 2.4 `Triaje: Clasificar (gpt-5-mini)` — `n8n-nodes-base.httpRequest` v4.2 (clon de `Banlist Shadow - LLM`)
```json
{"parameters": {"method": "POST", "url": "https://api.openai.com/v1/chat/completions",
  "authentication": "predefinedCredentialType", "nodeCredentialType": "openAiApi",
  "sendBody": true, "specifyBody": "json", "jsonBody": "={{ $json.llm_body }}",
  "options": {"response": {"response": {"neverError": true}}, "timeout": 20000}},
 "onError": "continueRegularOutput", "credentials": {"openAiApi": OPENAI_CRED}}
```
Timeout 20 s (no 60: un LLM colgado no debe dejar al paciente esperando; el timeout cae a escalación).

### 2.5 `Triaje: Get Config` — `n8n-nodes-base.postgres` v2.5
```json
{"parameters": {"operation": "executeQuery", "options": {},
  "query": "SELECT v.id, v.tipo, v.opcion, v.url, v.filename, v.caption, v.pregunta_guiada, v.texto_salida_emergencia, v.texto_cierre, c.telefonos_piloto, c.aviso_pasivo, c.modo FROM triaje_videos v CROSS JOIN triaje_config c WHERE c.id = 1 AND c.activo = true AND v.activo = true AND v.url IS NOT NULL ORDER BY v.tipo, v.opcion"},
 "alwaysOutputData": true, "onError": "continueRegularOutput", "credentials": {"postgres": PG_CRED}}
```
0 filas (tabla ausente, `triaje_config.activo=false`, tipo inactivo, error) → Decidir escala. Es el kill-switch sin PUT.

### 2.6 `Triaje: Re-check Humano` — `n8n-nodes-base.httpRequest` v4.2 (clon exacto de `Re-check Humano`: misma `url` `=https://chat.raquelrodriguez.com.ar/api/v1/accounts/1/contacts/{{ $('Existe paciente?').first().json.payload[0].id }}/conversations`, mismos `headerParameters` copiados del GET, `continueOnFail: true`, `onError: "continueRegularOutput"`). Cubre la ventana Router+clasificador (~6-10 s) igual que el Re-check original cubre la del sub-agent. Fail-open (como `Hay humano ahora?`).

### 2.7 `Triaje: Decidir` — `n8n-nodes-base.code` v2 (toda la lógica; NUNCA genera texto, solo elige textos de la tabla)
```js
try {
  const p = $('Triaje: Preparar').first().json;
  const base = (() => { try { return $('Extraer Horarios y Precio').first().json; } catch (e) { return {}; } })();
  const pm = $('Preparar Mensaje Final').first().json;
  const phone = (pm.phone || '').toString();
  const texto = (pm.text || '').toString();
  const estado = p.estado || null;
  const exec = $execution.id;
  // --- humano apareció durante Router+clasificador (fail-open como Hay humano ahora?)
  let humano = false;
  try { const r = $('Triaje: Re-check Humano').first().json;
        if (!(r.error || r.statusCode >= 400)) for (const c of (r.payload || [])) if (Array.isArray(c.labels) && c.labels.includes('humano')) { humano = true; break; } } catch (e) { humano = false; }
  // --- clasificación
  let cls = { tipo: 'error_llm', confianza: 'baja', razon: 'sin respuesta' };
  try { const r = $('Triaje: Clasificar (gpt-5-mini)').first().json;
        const content = r.choices[0].message.content;
        cls = JSON.parse(String(content).replace(/^```(json)?|```$/gm, '').trim());
        if (!cls.tipo) throw new Error('sin tipo'); } catch (e) { cls = { tipo: 'error_llm', confianza: 'baja', razon: 'error_llm: ' + String(e && e.message || e) }; }
  // --- config
  let rows = []; try { rows = $('Triaje: Get Config').all().map(i => i.json).filter(r => r && r.tipo && r.url); } catch (e) { rows = []; }
  const pilotos = (rows[0] && Array.isArray(rows[0].telefonos_piloto)) ? rows[0].telefonos_piloto : [];
  if (pilotos.length && !pilotos.includes(phone)) rows = [];          // allow-list del piloto
  const avisoPasivo = !!(rows[0] && rows[0].aviso_pasivo);
  const cfg = (t) => rows.filter(r => r.tipo === t).sort((a, b) => a.opcion - b.opcion);
  // --- regex determinísticas (Unicode-safe, sin \b)
  const B0 = '(?<![\\p{L}\\p{N}])', B1 = '(?![\\p{L}\\p{N}])';
  const W = (alts) => new RegExp(B0 + '(?:' + alts + ')' + B1, 'iu');
  const NO_SIRVIO = W('no (?:me )?(?:sirvi[oó]|funcion[oó]|ayud[oó]|result[oó]|pude|puedo|sale|me sale|lo logr\\p{L}*|consigo|tengo cera|hay cera|conseguí cera|encuentro cera|tengo pinza|hay pinza)|sigue|siguen|igual|peor|todav[ií]a|a[uú]n|se (?:me )?(?:volvi[oó]|vuelve) a|otra vez|de nuevo|no (?:me )?(?:qued[oó]|anda|agarra|pega|entra|entr[oó])|no pas[oó] nada|nada');
  const CIERRE = new RegExp('^\\s*(?:ok|oka|okey|dale|listo|gracias|muchas gracias|mil gracias|genial|perfecto|joya|buen[ií]simo|ya est[aá]|ya (?:me |le |se )?(?:puse|coloqu[eé]|coloque|pude|acomod[eé])|ya (?:lo )?(?:hice|resolv[ií]|solucion[eé]|arregl[eé])|me sirvi[oó]|funcion[oó]|mejor[oó]|ya no (?:me )?(?:pincha|molesta|duele))[\\s\\S]{0,80}$', 'iu');
  const SI = /^\s*(s[ií]|sip|dale|claro|exacto|eso|correcto|as[ií] es|tal cual)(?![\p{L}])/iu;
  const NO = /^\s*(no|nop|nope|para nada|nada que ver)(?![\p{L}])/iu;
  const URG_KW = p.prefiltro_reason === 'urgencia' || W('cera|pinza|alambre|bracket|pincha\\p{L}*|duele|dolor|sangr\\p{L}*').test(texto);
  const flagsAll = [...(p.gate_red_flags || []).map(f => 'gate:' + f), ...(cls.tipo === 'red_flag' ? ['llm:red_flag'] : [])];
  // --- decisión
  let d = { accion: 'escalar', motivo_bot: 'default', tipo: cls.tipo, confianza: cls.confianza, razon: cls.razon, opcion: null, video: null };
  const escalar = (m) => { d.accion = 'escalar'; d.motivo_bot = m; };
  const video = (row, m) => { d.accion = 'video'; d.motivo_bot = m; d.opcion = row.opcion; d.video = row; };
  if (humano) { d.accion = 'silencio'; d.motivo_bot = 'humano_atendiendo_recheck'; }
  else if (p.modo === 'error') escalar('error_preparar');
  else if (p.gate_escala) escalar('gate:' + (p.gate_red_flags || []).join(','));
  else if (cls.tipo === 'red_flag') escalar('llm:red_flag');
  else if (p.modo === 'nuevo') {
    const c = cfg(cls.tipo);
    if (!c.length) escalar('tipo_sin_video_activo:' + cls.tipo);
    else if (cls.confianza === 'alta') video(c[0], 'nuevo:confianza_alta');
    else if (c[0].pregunta_guiada) { d.accion = 'texto'; d.motivo_bot = 'nuevo:confianza_' + cls.confianza + ':pregunta'; d.tipo = cls.tipo; d.texto = c[0].pregunta_guiada; d.paso_nuevo = 'pregunta'; }
    else escalar('sin_pregunta_guiada:' + cls.tipo);
  }
  else if (estado.paso === 'pregunta') {
    const c = cfg(estado.tipo);
    if (SI.test(texto) && c.length) video(c[0], 'pregunta:confirma_regex');
    else if (NO.test(texto)) escalar('pregunta:niega_regex');
    else if (cls.confianza === 'alta' && cfg(cls.tipo).length) video(cfg(cls.tipo)[0], 'pregunta:llm_alta:' + cls.tipo);
    else escalar('pregunta:sin_confirmacion:' + cls.tipo + '/' + cls.confianza);
  }
  else { // estado.paso === 'video_enviado'
    d.tipo = estado.tipo;
    const c = cfg(estado.tipo);
    if (NO_SIRVIO.test(texto) || URG_KW) {
      const next = c.find(r => r.opcion === (Number(estado.opcion) || 1) + 1);
      if (next && !CIERRE.test(texto)) video(next, 'video_enviado:no_sirvio->opcion' + next.opcion);
      else escalar('video_enviado:no_sirvio_sin_mas_opciones');
    } else if (CIERRE.test(texto)) {
      const cierre = (c[0] && c[0].texto_cierre) ? c[0].texto_cierre : '';
      d.accion = cierre ? 'texto' : 'persistir'; d.motivo_bot = 'video_enviado:cierre'; d.texto = cierre; d.cerrar = true;
    } else if ((p.intent || base.intent) === 'urgencia_dolor') escalar('video_enviado:router_urgencia_sin_regex');
    else { d.accion = 'normal'; d.motivo_bot = 'video_enviado:otro_tema:' + (base.intent || ''); }
  }
  // --- payload de envío (todo canned de la tabla)
  const prefijoTag = (row) => '[VIDEO TRIAJE ENVIADO — ' + row.tipo + ', Opción ' + row.opcion + ']: ';
  if (d.accion === 'video') { d.video_url = d.video.url; d.filename = d.video.filename || (d.video.tipo + '_opcion' + d.video.opcion + '.mp4'); d.caption = d.video.caption; d.texto = d.video.texto_salida_emergencia || ''; }
  // --- estado Redis
  const nowIso = new Date().toISOString();
  d.redis_key = 'triaje:' + phone;
  if (d.accion === 'video') { d.redis_value = JSON.stringify({ tipo: d.video.tipo, opcion: d.video.opcion, paso: 'video_enviado', ts: nowIso, exec, texto_original: (estado && estado.texto_original) || texto }); d.redis_ttl = 7200; }
  else if (d.accion === 'texto' && d.paso_nuevo === 'pregunta') { d.redis_value = JSON.stringify({ tipo: d.tipo, opcion: 0, paso: 'pregunta', ts: nowIso, exec, texto_original: texto, pregunta: d.texto }); d.redis_ttl = 1800; }
  else { d.redis_value = JSON.stringify({ paso: 'cerrado', ts: nowIso }); d.redis_ttl = 1; } // ttl 1 s == borrar
  // --- SQL: log de la decisión (corre SIEMPRE, antes del envío)
  const esc = (v) => (v === null || v === undefined) ? 'NULL' : "'" + String(v).replace(/'/g, "''") + "'";
  const modoLog = (rows[0] && rows[0].modo) ? rows[0].modo : 'live';
  const accionLog = ({ video: 'video', texto: d.cerrar ? 'cerrado' : 'pregunta', persistir: 'cerrado', escalar: 'escalado', normal: 'normal', silencio: 'silencio_humano' })[d.accion] || 'escalado';
  d.log_sql = 'INSERT INTO triaje_urgencias_log (telefono, exec_id, mensaje_paciente, gate_red_flags, gate_escala, tipo, confianza, razon, modelo, modo, accion, video_enviado, opcion_enviada, paso, motivo_bot) VALUES (' +
    [esc(phone), esc(exec), esc(texto.slice(0, 2000)), esc(JSON.stringify(flagsAll)) + '::jsonb', p.gate_escala ? 'true' : 'false', esc(d.tipo), esc(d.confianza), esc(d.razon), esc(p.modelo || 'gpt-5-mini'), esc(modoLog), esc(accionLog), esc(d.video_url || null), d.opcion === null ? 'NULL' : String(d.opcion), esc(p.modo === 'nuevo' ? 'nuevo' : estado.paso), esc(d.motivo_bot)].join(', ') + ') RETURNING id';
  // --- SQL: persistencia post-envío (memoria + aviso pasivo + update del log) en UNA transacción
  const msg = (type, content, extra) => esc(JSON.stringify({ type, content, additional_kwargs: Object.assign({ source: 'triaje', pushName: (() => { try { return $('Edit Fields - Extraer Datos').first().json.pushName || ''; } catch (e) { return ''; } })() }, extra || {}), response_metadata: {}, tool_calls: [], invalid_tool_calls: [] })) + '::jsonb';
  const filas = [ '(' + esc(phone) + ', ' + msg('human', texto, {}) + ')' ];
  if (d.accion === 'video') { filas.push('(' + esc(phone) + ', ' + msg('ai', prefijoTag(d.video) + d.caption, { source: 'triaje_video', tipo: d.video.tipo, opcion: d.video.opcion, video_url: d.video_url }) + ')');
                              if (d.texto) filas.push('(' + esc(phone) + ', ' + msg('ai', d.texto, { source: 'triaje_video' }) + ')'); }
  else if (d.accion === 'texto') filas.push('(' + esc(phone) + ', ' + msg('ai', (d.cerrar ? '' : '[PREGUNTA TRIAJE]: ') + d.texto, { source: 'triaje_texto' }) + ')');
  let sql = 'WITH mem AS (INSERT INTO n8n_chat_histories (session_id, message) VALUES ' + filas.join(', ') + ' RETURNING id)';
  if (d.accion === 'video' && avisoPasivo) sql += ', avi AS (INSERT INTO escalaciones_log (telefono, motivo, origen, exec_id) VALUES (' + esc(phone) + ', ' + esc('[TRIAJE VIDEO] ' + d.video.tipo + ' Opción ' + d.video.opcion + ' enviada por el bot (resuelto con video, sin acción requerida salvo que el paciente vuelva a escribir)') + ", 'triaje', " + esc(exec) + ') RETURNING id)';
  sql += ' UPDATE triaje_urgencias_log t SET enviado_ok = true, chat_history_id = (SELECT max(id) FROM mem)' + ((d.accion === 'video' && avisoPasivo) ? ', escalacion_id = (SELECT id FROM avi)' : '') + ' WHERE t.exec_id = ' + esc(exec) + ' AND t.telefono = ' + esc(phone) + ' RETURNING t.id';
  d.persist_sql = sql;
  return [{ json: Object.assign({}, base, d, { phone, texto, modo: p.modo, estado, gate_escala: p.gate_escala, gate_red_flags: p.gate_red_flags, intent: (d.accion === 'normal') ? (base.intent === 'urgencia_dolor' ? 'consulta_general' : base.intent) : base.intent }), pairedItem: { item: 0 } }];
} catch (e) {
  const pm2 = (() => { try { return $('Preparar Mensaje Final').first().json; } catch (x) { return {}; } })();
  return [{ json: { accion: 'escalar', motivo_bot: 'error_decidir', triaje_error: String(e && e.message || e), phone: pm2.phone || '', redis_key: 'triaje:' + (pm2.phone || ''), redis_value: '{}', redis_ttl: 1, log_sql: "INSERT INTO triaje_urgencias_log (telefono, exec_id, modo, accion, motivo_bot) VALUES ('" + String(pm2.phone || '').replace(/'/g, "''") + "', '" + $execution.id + "', 'live', 'escalado', 'error_decidir') RETURNING id" }, pairedItem: { item: 0 } }];
}
```
Notas: (a) `intent` del item se fuerza a `consulta_general` cuando `accion='normal'` y el Router había dicho `urgencia_dolor` — pero ese caso ya fue convertido en `escalar` arriba, la asignación es solo cinturón: garantiza que `Switch sobre Intent`[2] NUNCA dispare desde la segunda entrada (sin loop, `Triaje: Preparar` corre una sola vez por ejecución). (b) `URG_KW` en `video_enviado` hace que "gracias, ya puse la cera" sea evaluado como CIERRE (la rama `!CIERRE.test` protege) y "no tengo cera" / "sigue pinchando" / "se me volvió a salir el alambre" vayan a Opción 2 o escalación. (c) Ninguna string enviada al paciente se construye en código: `caption`, `texto_salida_emergencia`, `pregunta_guiada`, `texto_cierre` vienen de la fila.

### 2.8 `Triaje: Log` — `n8n-nodes-base.postgres` v2.5
`{"operation":"executeQuery","query":"={{ $json.log_sql }}","options":{}}`, `onError: continueRegularOutput`, `alwaysOutputData: true`. Devuelve `id` (RETURNING). Loguea TODAS las decisiones (incluida `normal`, `silencio_humano` y las escaladas) con `modo` de la tabla (`live` por defecto), ANTES del envío; `enviado_ok` lo pone el UPDATE de 2.13 solo si el envío salió.

### 2.9 `Triaje: Switch Acción` — `n8n-nodes-base.switch` v3.2 (reglas `={{ $('Triaje: Decidir').first().json.accion }}` string equals; `options: {fallbackOutput:'extra', renameFallbackOutput:'fallback'}`)
| out | outputKey | valor | destino |
|---|---|---|---|
| 0 | `video` | `video` | `Triaje: Enviar Video` |
| 1 | `texto` | `texto` | `Triaje: Enviar Texto` |
| 2 | `persistir` | `persistir` | `Triaje: PG Escribir` |
| 3 | `normal` | `normal` | `Switch sobre Intent` |
| 4 | `escalar` | `escalar` | `Triaje: Redis DEL estado` |
| 5 | `silencio` | `silencio` | `Humano Atendiendo (no hacer nada)` |
| 6 | `fallback` | — | `Triaje: Redis DEL estado` |
Se usa `$('Triaje: Decidir')` y no `$json` para no depender del shape del row que devuelve `Triaje: Log` (patrón Loop Mensajes → Typing).

### 2.10 `Triaje: Enviar Video` — `n8n-nodes-base.httpRequest` v4.2 (clon de `Evolution API - Enviar Mensaje`, url `/send/media`)
```
"jsonBody": "={\n  \"number\": {{ JSON.stringify(($('Preparar Mensaje Final').first().json.remoteJid || '').replace(/[^0-9]/g, '')) }},\n  \"type\": \"video\",\n  \"url\": {{ JSON.stringify($('Triaje: Decidir').first().json.video_url) }},\n  \"caption\": {{ JSON.stringify($('Triaje: Decidir').first().json.caption) }},\n  \"filename\": {{ JSON.stringify($('Triaje: Decidir').first().json.filename) }}\n}"
"options": {"response": {"response": {"fullResponse": true, "neverError": true}}, "timeout": 60000}
"onError": "continueRegularOutput"
```
Headers: deepcopy de `Evolution API - Enviar Mensaje.parameters.headerParameters` (apikey + Content-Type). Base URL = `params.url.split('/send/')[0]` del GET (`https://evo.raquelrodriguez.com.ar`). Patrón JSON.stringify POR CAMPO (lección tildes). `fullResponse` → `$json.statusCode` disponible independientemente del shape del body (probado: 200 con `data.Info.Type == 'VideoMessage'`).

### 2.11 `Triaje: Enviar Texto` — `n8n-nodes-base.httpRequest` v4.2 (clon de `Evolution API - Enviar Mensaje`, `/send/text`) — inputs: `Triaje: Enviar Video`[0] y `Triaje: Switch Acción`[1]
```
"jsonBody": "={\n  \"number\": {{ JSON.stringify(($('Preparar Mensaje Final').first().json.remoteJid || '').replace(/[^0-9]/g, '')) }},\n  \"text\": {{ JSON.stringify($('Triaje: Decidir').first().json.texto || '') }}\n}"
```
Mismas options/onError que 2.10. Si `texto` está vacío (tipo sin `texto_salida_emergencia`), Evolution devuelve 4xx → `Envío OK?` false → escalación (por eso el seed exige texto no vacío y el DDL lo hace NOT NULL).

### 2.12 `Triaje: Envío OK?` — `n8n-nodes-base.if` v2.2, boolean true:
```
={{ (() => { const ok = (r) => { const j = r || {}; return !j.error && Number(j.statusCode) >= 200 && Number(j.statusCode) < 300; }; try { const d = $('Triaje: Decidir').first().json; if (!ok($('Triaje: Enviar Texto').first().json)) return false; if (d.accion !== 'video') return true; return ok($('Triaje: Enviar Video').first().json); } catch (e) { return false; } })() }}
```
[0 true] → `Triaje: PG Escribir`; [1 false] → `Triaje: Redis DEL estado` (→ Sub-Agent Urgencia). Si falló el video pero salió el texto de salida, igual se escala: el paciente recibe "si no mejora… le pasamos a la doctora" + la escalación real; nunca queda sin respuesta.

### 2.13 `Triaje: PG Escribir` — `n8n-nodes-base.postgres` v2.5 — inputs: `Envío OK?`[0], `Switch Acción`[2]
`{"operation":"executeQuery","query":"={{ $('Triaje: Decidir').first().json.persist_sql }}","options":{}}`, `onError: continueRegularOutput`, `alwaysOutputData: true`. Un solo statement (CTE) = atómico: memoria + aviso pasivo + `UPDATE triaje_urgencias_log`. Si falla, el paciente YA recibió el video (correcto: lo importante fue enviado); queda el log con `enviado_ok NULL` y el Redis SET igual corre (siguiente nodo), así el seguimiento funciona aunque la memoria no tenga el turno.

### 2.14 `Triaje: Redis SET estado` — `n8n-nodes-base.redis` v1
`{"operation":"set","key":"={{ $('Triaje: Decidir').first().json.redis_key }}","value":"={{ $('Triaje: Decidir').first().json.redis_value }}","expire":true,"ttl":"={{ $('Triaje: Decidir').first().json.redis_ttl }}"}`, `onError: continueRegularOutput`. Terminal (fin de la rama video/texto/cierre). TTL 7200 (video), 1800 (pregunta), 1 (cierre = borrar).

### 2.15 `Triaje: Redis DEL estado` — `n8n-nodes-base.redis` v1 — inputs: `Switch Acción`[4], `[6]`, `Envío OK?`[1]
`{"operation":"delete","key":"={{ 'triaje:' + $('Preparar Mensaje Final').first().json.phone }}"}`, `onError: continueRegularOutput` → `Sub-Agent Urgencia`. Motivo: tras escalar, el label humano dura ~60-75 min; si quedara `paso:'video_enviado'` (TTL 2 h), un "sigue igual" post-reactivación mandaría la Opción 2 en vez de re-escalar.

Sticky note opcional `Triaje (Fase 2 — piloto alambre_pincha)` con el mapa. Total: 15 nodos funcionales.

## 3. Estado Redis
- Key: `triaje:<phone>` (misma convención `<namespace>:<phone>` que `chat_buffer:`/`ratelimit:`; `phone` = `$('Preparar Mensaje Final').first().json.phone`, o sea el mismo string que `session_id`).
- Shape (JSON string): `{ tipo, opcion (0 en pregunta / 1 / 2), paso: 'pregunta' | 'video_enviado', ts, exec, texto_original, pregunta? }`.
- TTL: `video_enviado` 7200 s (2 h: cubre "lo probé y no funcionó" realista), `pregunta` 1800 s, cierre → SET con ttl 1 (equivale a DEL sin nodo extra), escalación → DEL explícito.
- Solo lo lee `Triaje: Redis GET estado`; nada del resto del v6 lo conoce.

## 4. Config: DDL + seeds (`scripts/sql/triaje_videos.sql`, aplicar con psycopg2 vía `SUPABASE_DB_*` ANTES del PUT; idempotente)
```sql
CREATE TABLE IF NOT EXISTS public.triaje_config (
  id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  activo boolean NOT NULL DEFAULT false,            -- kill-switch maestro: false => todo escala como hoy (sin PUT)
  modo text NOT NULL DEFAULT 'live' CHECK (modo IN ('piloto','live')),
  telefonos_piloto text[] NOT NULL DEFAULT '{}',    -- vacío = todos; para la demo: '{5491161461034}'
  aviso_pasivo boolean NOT NULL DEFAULT true,       -- fila [TRIAJE VIDEO] en escalaciones_log (origen 'triaje')
  updated_at timestamptz NOT NULL DEFAULT now(), updated_by text);
INSERT INTO public.triaje_config (id, activo) VALUES (1, false) ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.triaje_videos (
  id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  tipo text NOT NULL CHECK (tipo ~ '^[a-z_]+$'),    -- = salida del clasificador y triaje_urgencias_log.tipo
  opcion smallint NOT NULL CHECK (opcion BETWEEN 1 AND 9),
  url text CHECK (url IS NULL OR url ~ '^https://'),
  filename text,
  caption text NOT NULL,                            -- canned, nunca LLM; el panel valida banlist al guardar
  pregunta_guiada text,                             -- se usa desde la fila opcion=1 cuando confianza media/baja
  texto_salida_emergencia text NOT NULL,            -- 2do mensaje de texto tras el video
  texto_cierre text,                                -- NULL = cierre silencioso
  activo boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(), updated_by text,
  CONSTRAINT triaje_videos_tipo_opcion_uq UNIQUE (tipo, opcion),
  CONSTRAINT triaje_videos_activo_con_url CHECK (activo = false OR url IS NOT NULL));
CREATE INDEX IF NOT EXISTS idx_triaje_videos_tipo ON public.triaje_videos (tipo, opcion);

INSERT INTO public.triaje_videos (tipo, opcion, url, filename, caption, pregunta_guiada, texto_salida_emergencia, texto_cierre, activo) VALUES
 ('alambre_pincha', 1,
  'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion1.mp4',
  'alambre_pincha_opcion1.mp4',
  'Situación: el alambre se salió y está pinchando. Opción 1: colocar cera de ortodoncia en la punta del alambre, como muestra el video, para aliviar la molestia hasta el control con la Dra. Raquel.',
  '[BORRADOR] Para orientarlo mejor: ¿el alambre se salió del último bracket o tubito de atrás y le pincha el cachete? Responda SÍ o NO.',
  'Si no mejora, si el dolor es fuerte o si hay sangrado, responda este mensaje y le pasamos el caso a la doctora.',
  'Recibido. Ante cualquier molestia nueva, escríbanos y le avisamos a la doctora.',
  true),
 ('alambre_pincha', 2,
  'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion2.mp4',
  'alambre_pincha_opcion2.mp4',
  'Opción 2: intentar colocar el alambre nuevamente en el tubo o bracket de donde se soltó, con ayuda de una pinza de alicate o de cejas, como muestra el video.',
  NULL,
  'Si no lo logra o la molestia continúa, responda este mensaje y le pasamos el caso a la doctora.',
  NULL, true),
 ('bracket_suelto',  1, NULL, NULL, '[PENDIENTE] caption cuando llegue el video', NULL, '[PENDIENTE]', NULL, false),
 ('alambre_girado',  1, NULL, NULL, '[PENDIENTE] caption cuando llegue el video', NULL, '[PENDIENTE]', NULL, false),
 ('ligadura_pincha', 1, NULL, NULL, '[PENDIENTE] caption cuando llegue el video', NULL, '[PENDIENTE]', NULL, false)
ON CONFLICT (tipo, opcion) DO NOTHING;

ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS enviado_ok boolean;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS opcion_enviada smallint;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS paso text;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS chat_history_id bigint;
CREATE INDEX IF NOT EXISTS idx_triaje_telefono_created ON public.triaje_urgencias_log (telefono, created_at DESC);
ALTER TABLE public.triaje_config ENABLE ROW LEVEL SECURITY; ALTER TABLE public.triaje_videos ENABLE ROW LEVEL SECURITY;
-- Prender el piloto (después del PUT y del E2E): UPDATE triaje_config SET activo = true, telefonos_piloto = '{}' WHERE id = 1;
```
Textos seed chequeados a mano contra los 20 regex del Banlist vivo (sin "aplicá/sacá/guardá/tomá/enjuagá/venite/esperamos/lo antes posible+clínica/no te preocupes/no es grave/Balcarce 37"): pasan. El apply script lo re-verifica con `node` sobre el array BANLIST extraído del nodo `Banlist Validator` del GET (mismo harness de `tests/test_canned_sidecar.py`), y falla si algún texto activo matchea. `triaje_urgencias_log.accion/modo` no tienen CHECK (verificado en `rebuild_v3_schema.sql` §8b) → los valores nuevos (`pregunta|cerrado|normal|silencio_humano`, `live`) entran sin ALTER.

## 5. Persistencia en memoria (query exacta que arma Decidir, ejemplo camino video)
```sql
WITH mem AS (
  INSERT INTO n8n_chat_histories (session_id, message) VALUES
   ('5491161461034', '{"type":"human","content":"<texto paciente>","additional_kwargs":{"source":"triaje","pushName":"Lucas"},"response_metadata":{},"tool_calls":[],"invalid_tool_calls":[]}'::jsonb),
   ('5491161461034', '{"type":"ai","content":"[VIDEO TRIAJE ENVIADO — alambre_pincha, Opción 1]: <caption>","additional_kwargs":{"source":"triaje_video","pushName":"Lucas","tipo":"alambre_pincha","opcion":1,"video_url":"https://…/opcion1.mp4"},"response_metadata":{},"tool_calls":[],"invalid_tool_calls":[]}'::jsonb),
   ('5491161461034', '{"type":"ai","content":"<texto_salida_emergencia>","additional_kwargs":{"source":"triaje_video","pushName":"Lucas"},"response_metadata":{},"tool_calls":[],"invalid_tool_calls":[]}'::jsonb)
  RETURNING id),
avi AS (
  INSERT INTO escalaciones_log (telefono, motivo, origen, exec_id)
  VALUES ('5491161461034', '[TRIAJE VIDEO] alambre_pincha Opción 1 enviada por el bot (resuelto con video, sin acción requerida salvo que el paciente vuelva a escribir)', 'triaje', '<exec_id>')
  RETURNING id)
UPDATE triaje_urgencias_log t SET enviado_ok = true, chat_history_id = (SELECT max(id) FROM mem), escalacion_id = (SELECT id FROM avi)
 WHERE t.exec_id = '<exec_id>' AND t.telefono = '5491161461034' RETURNING t.id;
```
Shape del `message` = idéntico al de `Build fromMe AI memory` / `Postgres - Save fromMe` (type, content, additional_kwargs, response_metadata, tool_calls, invalid_tool_calls). Efectos verificados: `Build Router Context` mostrará `PACIENTE: <texto>` / `BOT: [VIDEO TRIAJE ENVIADO — …]` en el turno siguiente; `Postgres Chat Memory` (window 10) se lo da a los sub-agents; el Logger (`Parse mensajes`) mapea human+source `triaje` → `rol='user', fuente='whatsapp'` y ai+source `triaje_video|triaje_texto` → `rol='assistant', fuente='bot'` → el panel muestra el mensaje del paciente y dos burbujas verdes "Asiri" (como texto; el chip "Video" con link es un cambio chico posterior en `Parse mensajes` + `detectMedia`, no bloqueante). `Clear Old Memory` borra estas filas con la sesión stale (>7 días) — correcto, el registro duradero es `triaje_urgencias_log`. `PG - Delete NO_REPLY` no las toca (content ≠ `[NO_REPLY]`). Contenidos ≥3 chars, sin prefijo `[NOTA INTERNA`/`[ATENCION HUMANA`, no son labels de intent → el Logger no los descarta. El `human` con source `triaje` NO es `wa_outbound|human_takeover` → no se interpreta como staff.

## 6. Logging (`triaje_urgencias_log`, modo `live`)
Una fila por ejecución que entra al triaje (INSERT en `Triaje: Log`, antes del envío): `telefono, exec_id ($execution.id del v6, no del Helper), mensaje_paciente, gate_red_flags ['gate:fiebre','llm:red_flag'], gate_escala, tipo, confianza, razon, modelo, modo, accion ∈ {escalado, video, pregunta, cerrado, normal, silencio_humano}, video_enviado (url), opcion_enviada, paso ∈ {nuevo, pregunta, video_enviado}, motivo_bot (razón determinística, p. ej. 'gate:hinchazon', 'nuevo:confianza_alta', 'video_enviado:no_sirvio->opcion2', 'tipo_sin_video_activo:bracket_suelto')`. Tras envío OK: `enviado_ok=true, chat_history_id, escalacion_id` (UPDATE por `exec_id`). Escalaciones vía Sub-Agent Urgencia quedan además en `escalaciones_log` por el Helper como hoy (sin escalacion_id enlazado; se correlaciona por teléfono+created_at como hace la sombra). `python scripts/ver_triaje_sombra.py --dias 7` sirve tal cual (agregar filtro `modo`).

## 7. Aviso pasivo
- Mecanismo: fila `escalaciones_log` con `origen='triaje'`, `motivo` prefijado `[TRIAJE VIDEO] …`, insertada en la CTE de `Triaje: PG Escribir` y enlazada a `triaje_urgencias_log.escalacion_id` → el satélite sombra (`NOT EXISTS … escalacion_id`) NO la reprocesa. Sin WhatsApp al grupo, sin label humano (decisión 2/9).
- Consumidores a ajustar (fuera del PUT, en el panel): `lib/escalaciones.ts` → `const RE_TRIAJE = /^\[triaje\b/i;` y en `tipoEscalacion` devolver `'operativo'` si matchea (antes de `RE_OPERATIVO`); opcional `dashboard/page.tsx` `.neq('origen','triaje')` en el KPI de escalaciones; `create_reportero_semanal.py::CLASIFICAR_CODE` misma regex (redeploy del reportero). Hasta que se toquen, un caso resuelto con video aparece en `/aprendizaje` como "señal" tema "Urgencias y dolor" y suma al KPI. Si Lucas prefiere cero cambios en el panel para la demo: `UPDATE triaje_config SET aviso_pasivo=false` → solo queda `triaje_urgencias_log`.
- Explícitamente descartado: `POST /webhook/notify-grupo?silencioso=true` (aplica label humano siempre → mata el flujo B; verificado 6/6 casos suprimidos post-escalación).

## 8. Errores / fail-closed — qué recibe el paciente
| Falla | Nodo que la absorbe | Resultado para el paciente |
|---|---|---|
| Redis caído al leer estado | `Triaje: Redis GET estado` (onError) → IF false | flujo normal (hoy Redis caído ya corta antes en `Redis GET bot:status`) |
| Bug/excepción en Preparar | try/catch → `modo:'error', gate_escala:true` | Decidir → escalar → Sub-Agent Urgencia (como hoy) |
| OpenAI caído / timeout 20 s / JSON inválido | `Clasificar` neverError+onError; Decidir → `tipo:'error_llm'` | escalar (como hoy) |
| Tabla config ausente / `triaje_config.activo=false` / tipo inactivo / phone fuera de `telefonos_piloto` | Get Config 0 filas | escalar (como hoy) |
| Chatwoot caído en Re-check | continueOnFail → `humano=false` | fail-open, sigue (igual que `Hay humano ahora?`) |
| Humano tomó el chat durante Router+clasificador | Decidir `silencio` | nada (mismo NoOp que `Bot Activo?`), fila `silencio_humano` en log |
| Bug en Decidir | try/catch → `accion:'escalar'` + log mínimo | escalar |
| `Triaje: Log` falla (Postgres) | onError + alwaysOutputData | sigue; se pierde la fila de log, no el envío |
| `/send/media` 4xx/5xx/timeout 60 s | fullResponse+neverError → `Envío OK?` false | Redis DEL → Sub-Agent Urgencia → canned de escalación + grupo (como hoy). Si el texto de salida sí salió, el paciente recibe ambos: "si no mejora…" + escalación |
| `/send/text` falla (pregunta/cierre/salida) | idem | escalar |
| `PG Escribir` falla | onError | paciente ya tiene el video; Redis SET corre igual → seguimiento funciona; memoria/panel sin el turno; log con `enviado_ok NULL` (alerta en `ver_triaje_sombra.py`) |
| `Redis SET` falla | onError, terminal | paciente tiene el video; el siguiente mensaje entra como urgencia nueva → Router → Switch[2] → Preparar ve `estado=null` → clasifica → si confianza alta manda Opción 1 OTRA VEZ (único caso de duplicado; requiere Redis fallando solo en ese SET) |
| Sub-Agent Urgencia devuelve [NO_REPLY] | bloque de prompt §9 lo prohíbe cuando Decidir escaló | queda el riesgo prompt-only (hoy existe igual); mitigación 2ª capa opcional: Gate Error Tecnico ya no aplica; se registra en log `accion=escalado` para auditar |
| Canned de escalación suprimido por label humano (bug sistémico 3f) | fuera de alcance | igual que hoy: el grupo recibe `[ESCALADO BOT]`, el paciente puede no recibir el canned |
| Rate limit 10 msg/15 min | `Rate Limit OK?` | descarte silencioso (existente); en la demo no superar 8 mensajes en 15 min |

## 9. Prompts editados
1. `Sub-Agent Urgencia`.`parameters.options.systemMessage` (expresión, empieza con `=`): APPEND al final (ancla = último párrafo `…Responde el canned y FIN.`, `count()==1`, marcador de idempotencia `TRIAJE DETERMINISTICO (2026-09-04)`):
```
\n\n**TRIAJE DETERMINISTICO (2026-09-04)**: {{ (() => { try { const d = $('Triaje: Decidir').first().json; if (!d || !d.accion) return 'sin datos de triaje: aplica las reglas normales.'; return 'Este mensaje YA fue evaluado por el triaje deterministico de urgencias y la decision fue ESCALAR (motivo: ' + (d.motivo_bot || 'n/d') + '; tipo estimado: ' + (d.tipo || 'n/d') + (d.estado && d.estado.paso === 'video_enviado' ? '; el paciente YA RECIBIO el video de autoayuda Opcion ' + d.estado.opcion + ' y reporta que no le sirvio' : '') + (d.estado && d.estado.paso === 'pregunta' ? '; el bot le habia hecho una pregunta guiada y la respuesta no permite resolverlo con video' : '') + '). La senal de urgencia ya esta validada: NO devuelvas [NO_REPLY] por falta de senales claras. Llama escalar_a_secretaria UNA sola vez incluyendo ese contexto en el resumen y responde EXACTAMENTE el canned.'; } catch (e) { return 'sin datos de triaje: aplica las reglas normales.'; } })() }}
```
   Actualizar también `prompts/v6_partials/urgencia_funcion.md` (o `build_prompts_v6.py --check` reporta drift).
2. `Router - Clasificar Intent`.`parameters.options.systemMessage`, ancla `**1. urgencia_dolor — MAXIMA PRIORIDAD**\nCualquier mencion de: dolor, muela, alambre, brackets, sangrado, hinchazon, pedido de medicacion ("que tomo", "que pastilla").` → agregar debajo:
```
CONTINUACION DE URGENCIA (NUEVO 2026-09-04, triaje con video): si en el CONTEXTO hay un mensaje BOT que empieza con "[VIDEO TRIAJE ENVIADO" o "[PREGUNTA TRIAJE" y el paciente responde sobre ese mismo problema (sigue/no funciono/peor/no tengo cera/no pude/contesta la pregunta), intent = `urgencia_dolor`. Solo si cambia de tema claro (precio, turno, alias) usa el intent que corresponda; los cierres ("listo gracias", "ya me puse la cera") -> `consulta_general`.
```
   Es segunda capa: la primera es determinística (Decidir corre antes del Switch). Opcional; se puede omitir sin cambiar el comportamiento del piloto.

## 10. Limpieza del número de Lucas (5491161461034) para la demo
1. **Chatwoot** (única causa determinística del "humano atendiendo"): contacto id 1 (+5491161461034), conv 272 (y cualquier otra: el contacto tiene 9 contact_inboxes). `GET /api/v1/accounts/1/contacts/1/conversations` → para toda conversación de CUALQUIER status con label `humano`: `POST /api/v1/accounts/1/conversations/<id>/labels {"labels":["bot"]}` (`scripts/remove_humano_label.py`; no usar `no_bot`). Último estado conocido: limpio desde 3/9 23:00:53Z (Auto Reactivar exec 270042) — verificar en vivo justo antes.
2. **Memoria**: `DELETE FROM n8n_chat_histories WHERE session_id = '5491161461034';` (mínimo: `… AND message->'additional_kwargs'->>'source' IN ('wa_outbound','human_takeover')`, incluye la fila 5912 de la REACCIÓN fromMe del 2/9 que `Clear Old Memory` nunca borra y que le pide silencio al LLM).
3. **Redis**: `DEL chat_buffer:5491161461034`, `DEL ratelimit:5491161461034`, `DEL triaje:5491161461034`; `GET bot:status` ≠ `disabled`; `GET dentalink:status` ≠ `down`.
4. **Panel/logs** (opcional): borrar `escalaciones_log` 189/190 y `conversaciones` 6006/6009 (pendiente de permisos), `DELETE FROM triaje_urgencias_log WHERE telefono='5491161461034'`.
5. Durante la demo nadie escribe ni REACCIONA desde el celular del consultorio ni desde Chatwoot en ese chat (fromMe → label humano 1 h + fila [ATENCION HUMANA]). Lucas es admin pero sus mensajes que no empiezan con `/bot` van por el camino de paciente (verificado en `Kill-switch Check`).
6. `UPDATE triaje_config SET activo=true, telefonos_piloto='{5491161461034}'` para que SOLO Lucas entre al piloto durante la demo; después `telefonos_piloto='{}'`.
Alternativa: usar un número no-admin de un colaborador (misma limpieza de Chatwoot/memoria si ya existe como contacto).

## 11. Plan de tests
**Unitarios (sin n8n, antes del PUT)**: `tests/test_triaje_decidir.py` corre el JS real de `Triaje: Preparar` y `Triaje: Decidir` con el harness de `tests/test_canned_sidecar.py` (mock de `$`, `$input`, `$execution`) sobre una matriz: nuevo/alta → video op1; nuevo/media → pregunta; nuevo/red_flag (gate `fiebre`) → escalar (sin mirar el LLM); tipo inactivo → escalar; config vacía → escalar; LLM error → escalar; humano → silencio; seguimiento pregunta "sí" → video; "no" → escalar; video_enviado + "no me sirvió, sigue pinchando" → video op2; op2 + "sigue igual" → escalar; "listo gracias ya me puse la cera" → texto cierre + ttl 1; "cuánto sale la consulta?" con estado → normal; video_enviado + Router urgencia sin regex → escalar; `node triaje/test_gate.js` 29/29; banlist sobre los 6 textos del seed.
**E2E (bot real, teléfono limpio, `telefonos_piloto` = ese número; cada respuesta tarda ~30-45 s por el buffer de 22 s + 2 LLM + descarga del mp4; máx 8 mensajes/15 min)**:
1. "Buenas, se me salió el alambre del último bracket y me pincha el cachete" → recibe VIDEO opción 1 con caption + texto de salida; `triaje_urgencias_log` fila `accion=video, opcion_enviada=1, enviado_ok=true`; `n8n_chat_histories` 3 filas (human + 2 ai); Redis `triaje:<phone>` paso `video_enviado`; `escalaciones_log` fila `[TRIAJE VIDEO]` origen `triaje`; NO WhatsApp al grupo; panel muestra las 3 burbujas.
2. "no tengo cera, sigue pinchando" → VIDEO opción 2 + su texto de salida; log `video_enviado:no_sirvio->opcion2`; Redis opcion 2.
3. "listo, lo pude acomodar con la pinza, gracias" → texto de cierre; Redis borrado; log `accion=cerrado`.
4. "me molesta algo del aparato atrás, no sé qué es" → (confianza media/baja esperada) pregunta guiada; Redis paso `pregunta` TTL 30 min. Si el LLM devuelve alta → video 1 (aceptable; anotar).
5. "sí, se salió y me pincha" → VIDEO opción 1 (regex SI).
6. (final, opcional) "ahora me sangra mucho y me duele muchísimo" → gate `sangrado_abundante`/`dolor_intenso` → `[ESCALADO BOT]` en el grupo con resumen que menciona el video enviado; log `accion=escalado, motivo_bot=gate:…`; Redis borrado. Aviso: tras esto el chat queda con label humano ~1 h (repetir paso 10.1 para seguir probando) y el canned al paciente puede no llegar (bug sistémico 3f, preexistente).
7. Regresión de los otros intents (`tests/test_e2e_bateria.py`): "quiero un turno", "cuánto sale la consulta", "confirmo", "cancelar mi turno" → mismas respuestas que antes del PUT (verifica que `Redis GET estado` en el camino principal no rompió nada). Kill-switch `/bot off|on` sigue respondiendo.
8. Apagado sin PUT: `UPDATE triaje_config SET activo=false` → repetir msg 1 → escalación como hoy.

## 12. Script de aplicación y rollback
`scripts/apply_triaje_fase2_piloto.py` (patrón `apply_canned_sidecar.py`): `lib_env` → GET fresco → `build(wf)` puro e idempotente por nombre de nodo; aborta si `conns['Switch sobre Intent']['main'][2] != [{Sub-Agent Urgencia}]`, si `conns['Extraer Horarios y Precio']['main'][0] != [{Switch sobre Intent}]` o `conns['Clear Old Memory']['main'][0] != [{Pre-filtro Cierre}]`; copia headers de `Evolution API - Enviar Mensaje` y `Re-check Humano`; embebe `triaje/gate_red_flags.js` y `prompts/triaje/clasificador_v1.md`; corre el Banlist del GET sobre los textos de la tabla (lee la tabla vía psycopg2) y aborta si matchea; imprime diff (nodos nuevos, conexiones cambiadas, `+/-` de los 2 prompts); sin `--apply` = dry-run. Con `--apply`: assert `webhookId == 'evo-webhook-v2'` en `Webhook - Evolution API`; backup `workflows/history/v6_PRE_triaje_fase2_<ts>.json`; PUT con `{name, nodes, connections, settings, staticData}` y `settings` filtrado a la allowlist (quita `availableInMCP`, `binaryMode`); GET → `v6_POST_triaje_fase2_<ts>.json`; verificación por índice de las 6 conexiones de §1 y presencia de los 15 nodos; `sys.exit` si falla.
Rollback en 3 niveles: (1) **sin PUT, inmediato**: `UPDATE triaje_config SET activo=false` → 0 filas de config → todo escala como hoy (los 2 nodos del camino principal quedan pero son inertes) + `redis-cli --scan --pattern 'triaje:*' | xargs redis-cli DEL`. (2) **PUT de reversión**: `scripts/apply_triaje_fase2_piloto.py --rollback` restaura las 3 conexiones originales (Switch[2] → Sub-Agent Urgencia, Extraer → Switch, Clear Old Memory → Pre-filtro), elimina los 15 nodos y quita los bloques de prompt (por marcador), con backup PRE/POST. (3) **restore total**: PUT del `v6_PRE_triaje_fase2_<ts>.json` (name/nodes/connections/settings filtrados), solo si (2) falla. Las tablas y las filas de memoria no se revierten (no afectan al v6 sin los nodos).
