# Mapa Redis + estado por conversación + gate "humano atendiendo" — v6 (`O155MqHgOSaNZ9ye`)

Fuente: `c:/Users/not/Desktop/proyectos/raquel-n8n/workflows/current/v6_LIVE.json` (125 nodos). Verifiqué por GET a la API que el archivo local es **idéntico** al workflow vivo (mismo `updatedAt` 2026-09-04T13:22:48Z, mismos 125 nodos, mismos parámetros y conexiones). Todo lo de abajo fue solo lectura; no se tocó n8n, Supabase, Redis, Chatwoot ni WhatsApp.

---

## 1) Redis — los 7 nodos (todos `n8n-nodes-base.redis` v1, credencial única `Redis account` id `kdtSKwGbN1xAZeUh`)

| Nodo | Operación | Key (expresión exacta) | TTL | Detalle |
|---|---|---|---|---|
| `Buffer: Push Mensaje` | `push` (`tail: true` = RPUSH) | `={{ 'chat_buffer:' + $('Edit Fields - Extraer Datos').first().json.phone }}` | **ninguno** | `messageData` = `={{ JSON.stringify({key_id: $('Edit Fields - Extraer Datos').first().json.key_id, text: $json.text \|\| ''}) }}`. Entra desde `Merge Multimedia:main[0]`; **no tiene outputs** (rama terminal; en paralelo `Merge Multimedia` → `Buffer: Wait 10s`). |
| `Buffer: Leer Lista` | `get` con `keyType: list`, `propertyName: messages` | misma key `chat_buffer:<phone>` | — | Sale a `Soy el ultimo?`: `JSON.parse($json.messages.last()).key_id` **equals** `$('Edit Fields - Extraer Datos').first().json.key_id` → true `Preparar Mensaje Final` / false `Descartar (no soy ultimo)`. |
| `Buffer: Limpiar` | `delete` | misma key `chat_buffer:<phone>` | — | Corre **después** de `Build Router Context` y antes de `Existe paciente?`. Al no haber TTL, si la ejecución "última" muere antes de este nodo la lista queda huérfana y `Preparar Mensaje Final` la concatena al próximo mensaje del mismo phone. |
| `Redis SET bot:status` | `set` | literal `bot:status` | ninguno (persistente) | `value` = `={{ $('Build Redis Cmd').first().json.newStatus }}` → `'disabled'` o `'enabled'`. Entra desde `Es off u on?:main[0]`, sale a `HTTP Send Admin Confirm`. |
| `Redis GET bot:status` | `get` → `propertyName: botStatus` | literal `bot:status` | — | Entra desde `Es comando admin?:main[1]` (todo mensaje NO-comando). Sale a `Bot enabled?`: `{{ $json.botStatus }}` **notEquals** `'disabled'` → true `Redis GET dentalink:status` / false `Bot Disabled (NoOp)`. Key ausente = habilitado. |
| `Redis GET dentalink:status` | `get` → `propertyName: dentalinkStatus` | literal `dentalink:status` | — | Sale a `Dentalink up?`: `{{ $json.dentalinkStatus }}` **notEquals** `'down'` → true `Rate Limit Prep` / false `Bot Disabled (NoOp)`. El v6 solo LEE esta key (la escribe presumiblemente el Health Check `Yjl6kyLnALhIfbFX`, no verificado). **Si vale `down`, el bot entero se calla, urgencias incluidas.** |
| `Rate Limit INCR` | `incr` | `={{ $json.rateLimitKey }}` (= `'ratelimit:' + phone`) | `expire: true, ttl: 900` (15 min, re-aplicado en **cada** INCR → ventana deslizante desde el último mensaje) | `Rate Limit Eval`: `count = parseInt(Object.values(inp)[0])`, `ok = bypass \|\| count <= 10` → `Rate Limit OK?` (`{{ $json.ok }}` true) → true `Edit Fields - Extraer Datos` / false `Rate Limit Excedido (NoOp)` (descarte **silencioso**, mensaje 11+ en 15 min). |

`Buffer: Wait 10s` (n8n-nodes-base.wait v1.1) tiene `amount: 22` → **espera 22 segundos**, no 10 (el nombre miente).

**`Rate Limit Prep` (código relevante):**
```js
const info = body.data && body.data.Info || {};
const remoteJid = info.Chat || '';
const phone = remoteJid.replace('@s.whatsapp.net','').replace(/^\+/,'').replace('@g.us','');
const source = (body.data && body.data.source) || '';
if (source === 'test_e2e_suite') { return [{ json: { phone, rateLimitKey: 'ratelimit:test:' + Date.now() + ':' + Math.random(), bypass: true } }]; }
if (!phone) { return [{ json: { phone: '', rateLimitKey: 'ratelimit:bypass:' + Date.now() + ':' + Math.random(), bypass: true } }]; }
return [{ json: { phone, rateLimitKey: 'ratelimit:' + phone, bypass: false } }];
```
Nota: acá el phone sale SOLO de `Info.Chat` (no es LID-safe, distinto al algoritmo de `Edit Fields - Extraer Datos`); inofensivo (un chat LID rate-limita bajo su LID).

**Convención de keys deducida**: `<namespace>:<phone>` para estado por conversación (`chat_buffer:`, `ratelimit:`) y `<recurso>:status` para estado global (`bot:status`, `dentalink:status`). **NO existe ninguna key Redis de "humano"/"silence" por teléfono en el v6 vivo.** La hubo (`silence:<phone>` con `EX 7200`, nodos `Redis SET silence`/`Redis GET silence`/`Silenced?`, ver `scripts/_archive/apply_silence_flag.py`) y fue **reemplazada por el label `humano` de Chatwoot** (`scripts/_archive/apply_chatwoot_label_fromme.py`). La "silence flag Redis" que menciona la regla 7 del CLAUDE.md ya no está en el workflow.

**Cómo se arma el identificador de teléfono** (`Edit Fields - Extraer Datos`, campo `phone`):
```js
={{ (() => { const info = $('Webhook - Evolution API').first().json.body.data.Info || {};
  for (const c of [info.Chat, info.Sender, info.RecipientAlt, info.SenderAlt]) {
    if (typeof c === 'string' && c.endsWith('@s.whatsapp.net')) return c.split('@')[0].split(':')[0]; }
  return (info.Chat || '').replace('@s.whatsapp.net', ''); })() }}
```
Resultado: solo dígitos, sin `+`, con código de país y sin sufijo de dispositivo (ej. `5491161461034`; `5493885786946:70@s.whatsapp.net` → `5493885786946`). Cuando el chat llega por LID (`remoteJid` = `223871026389070@lid`, típico de mensajes `fromMe` desde el celular de la Dra), el phone sale de `Sender`/`RecipientAlt`. **Ese mismo string es**: `session_id` en `n8n_chat_histories` (`Postgres Chat Memory` `sessionKey` = `$('Preparar Mensaje Final').first().json.phone`, `contextWindowLength: 10`), `q` de búsqueda en Chatwoot (`Existe paciente?`, `CW Search Contact`), `phone` en el querystring de `notify-grupo`, `telefono` en `escalaciones_log`, `telefono` en `pacientes` (`Get Paciente Context`). También hay `phone_last10` (últimos 10 dígitos) pero no se usa en keys.

---

## 2) Kill-switch (`/bot off|on|status`)

Cadena: `Webhook - Evolution API` (POST `/webhook/evolution-v2`) → `Webhook Validator` → `Kill-switch Check` → `Es comando admin?` → [true] `Build Redis Cmd` → `Es off u on?` → [true] `Redis SET bot:status` → `HTTP Send Admin Confirm`; [false = status] `HTTP Send Admin Confirm` directo. `Es comando admin?` [false] → `Redis GET bot:status` → … flujo normal.

**`Kill-switch Check` (código completo):**
```js
// Kill-switch: detecta comandos /bot off|on|status SOLO desde phone admin escribiendo al numero del consultorio.
// 2026-05-09 V2 - estricto: ignora fromMe=true (alguien usando multi-device del consultorio NO puede apagar el bot).
const inp = $input.first().json || {};
const body = inp.body || {};
const info = body.data && body.data.Info || {};
const msg = body.data && body.data.Message || {};
const remoteJid = info.Chat || '';
let phone = '';
for (const c of [info.Chat, info.Sender, info.RecipientAlt, info.SenderAlt]) {
  if (typeof c === 'string' && c.endsWith('@s.whatsapp.net')) { phone = c.split('@')[0].split(':')[0]; break; }
}
if (!phone) phone = remoteJid.replace('@s.whatsapp.net', '').replace(/^\+/, '');
const fromMe = !!info.IsFromMe;
const msgConv = typeof msg.conversation === 'string' ? msg.conversation : '';
const msgExt = msg.extendedTextMessage && msg.extendedTextMessage.text;
const text = (msgConv || msgExt || '').trim();
const ADMINS = {
  '5491161461034': 'Lucas',
  '5493885786946': 'Irina',
  '5493513976787': 'Dra. Raquel',
};
if (!fromMe && ADMINS[phone]) {
  const cmd = text.toLowerCase().match(/^\/bot\s+(off|on|status)\b/);
  if (cmd) {
    return [{ json: { isAdminCommand: true, action: cmd[1], adminPhone: phone, adminName: ADMINS[phone], fromBusiness: false, chatJid: remoteJid } }];
  }
}
return [{ json: { isAdminCommand: false, body: inp.body, headers: inp.headers } }];
```
**`Es comando admin?`**: `{{ $json.isAdminCommand }}` boolean true.
**`Build Redis Cmd` (código completo):**
```js
const j = $input.first().json;
const action = j.action; const adminPhone = j.adminPhone; const adminName = j.adminName;
let newStatus, confirmText;
if (action === 'off') {
  newStatus = 'disabled';
  confirmText = '✓ Bot apagado.\nLos mensajes que lleguen ahora los responden ustedes manualmente.\nPara reactivar: /bot on';
} else if (action === 'on') {
  newStatus = 'enabled';
  confirmText = '✓ Bot reactivado.\nLos pacientes vuelven a recibir respuestas automaticas.';
} else if (action === 'status') {
  newStatus = '__status__'; // sentinel: el siguiente nodo NO debe escribir
  confirmText = 'Hola ' + adminName + ', usa /bot off para apagar o /bot on para prender.';
}
return [{ json: { action, adminPhone, adminName, newStatus, confirmText } }];
```
**`Es off u on?`**: `{{ $json.newStatus }}` string **notEquals** `'__status__'`.
**`HTTP Send Admin Confirm`**: POST `https://evo.raquelrodriguez.com.ar/send/text`, header `apikey` presente (valor omitido), body `{"number": <chatJid solo dígitos>, "text": <confirmText>}`.

Respuestas exactas:
- **No hay ningún comando admin por chat.** Los únicos comandos son globales (`bot:status`). No existe "/bot off para este paciente" ni nada que toque el label `humano` o memoria.
- **Los admin phones están hardcodeados** en el jsCode (`ADMINS` con 3 entradas: Lucas, Irina, Dra. Raquel). Solo valen con `fromMe=false` (el admin escribe desde su propio celu al número del consultorio). Los mensajes normales (no `/bot ...`) de un admin siguen el flujo de paciente común (por eso Lucas puede hacer demos con su número).
- `/bot status` **no lee Redis ni informa el estado real**: responde un texto fijo de ayuda.
- `/bot on` solo escribe `bot:status=enabled`; **no** quita labels `humano` ni borra memoria, aunque el tag `[ATENCION HUMANA …]` guardado en memoria le dice al LLM "hasta que un admin diga /bot on".

---

## 3) Gate humano — mecanismo exacto

### 3a. Rama `fromMe` (lo que MARCA humano desde WhatsApp del consultorio)
`Edit Fields - Extraer Datos` → `Es fromMe?` (`{{ $json.fromMe }}` true; `fromMe` = `Info.IsFromMe`) → [true] `Build fromMe AI memory` → `Postgres - Save fromMe` → `CW Search Contact` → `CW Extract Conv` → `CW Get Conversations` → `CW Pick Conv` → `CW Set Label humano`. [false] → `Filtrar duplicados y basura` (que además descarta `fromMe`, `@g.us`, `status@broadcast`, vacíos).

**`Build fromMe AI memory`** (esencial): si no hay `phone` → `[]`. `content = text || '[mensaje multimedia enviado por la doctora/secretaria - sin texto adjunto]'`. Guarda `type:'ai'`, `content: '[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria desde el WhatsApp del consultorio. NO es output tuyo, es un humano atendiendo este chat. Mantente en silencio y NO respondas en este chat hasta que un admin diga /bot on.]: ' + content`, `additional_kwargs: { source: 'wa_outbound', from_iri_or_dra: true, was_multimedia: !text }`, `session_id = phone`.
**`Postgres - Save fromMe`**: `INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)` (credencial `Postgres Supabase Nexora v3` id `TpYhZX4UT61xAKSV`).
**`CW Search Contact`**: GET `https://chat.raquelrodriguez.com.ar/api/v1/accounts/1/contacts/search?q=<phone>&include=contact_inboxes` (header `api_access_token`, valor omitido; `onError: continueRegularOutput`).
**`CW Extract Conv`**: `contactId = payload[0].id`, `accountId: 1`; vacío si no hay contacto.
**`CW Get Conversations`**: GET `/api/v1/accounts/{{accountId}}/contacts/{{contactId}}/conversations`.
**`CW Pick Conv`**: `const open = convs.find(c => c.status === 'open'); const conv = open || convs[0];` → `{ accountId: 1, conversationId: conv.id, action: 'humano' }`.
**`CW Set Label humano`**: POST `/api/v1/accounts/{{accountId}}/conversations/{{conversationId}}/labels` body `{"labels":["humano"]}` (**reemplaza** el set de labels).

Ojo: `Es fromMe?` no distingue tipo de mensaje: **una reacción (emoji) o multimedia enviada desde el celu de la Dra también marca humano** (caso real 2/9 19:37Z, exec `269185`: `message_type: "reaction"`, `remoteJid: 223871026389070@lid`, `pushName: "Dra Raquel Rodriguez Ortodoncia"`, `text: ""` → fila `[ATENCION HUMANA …]: [mensaje multimedia …]` + label `humano` en conv 272).

### 3b. Pre-gate (antes del LLM)
`Buffer: Limpiar` → `Existe paciente?` (nodo `n8n-nodes-chatwoot.chatwoot`, `contactSearch`, `contactSearchQuery` = `$('Preparar Mensaje Final').first().json.phone`, accountId 1, **sin continueOnFail** → si Chatwoot cae, la ejecución falla y el bot queda mudo) → `Chatwoot - Buscar Conversacion` (GET `/api/v1/accounts/1/contacts/{{ $('Existe paciente?').first().json.payload[0].id }}/conversations`, `continueOnFail: true`) → `Verificar Label Humano` → `Bot Activo?` (`{{ $json.hasHumanoLabel }}` equals true) → [true] `Humano Atendiendo (no hacer nada)` (NoOp terminal) / [false] `Check Session Age` → `Handle Stale Session` → `Clear Old Memory` → `Pre-filtro Cierre` → … Router.

**`Verificar Label Humano` (código completo):**
```js
// Get conversations from contacts/{id}/conversations endpoint
const data = $input.first().json;
// If the HTTP request failed (continueOnFail), default to bot mode
if (data.error || data.statusCode >= 400) {
  return [{ json: { hasHumanoLabel: false } }];
}
const conversations = data.payload || [];
let hasHumanoLabel = false;
try {
  for (const conv of conversations) {
    if (conv.labels && Array.isArray(conv.labels) && conv.labels.includes('humano')) {
      hasHumanoLabel = true;
      break;
    }
  }
} catch (e) {
  hasHumanoLabel = false;
}
return [{ json: { hasHumanoLabel } }];
```
Mira **todas** las conversaciones del contacto (cualquier status, no solo `open`). Fail-open si falla el HTTP.

### 3c. Post-output re-check #1
`Banlist Validator` → `Re-check Humano` (mismo GET, `continueOnFail: true`) → `Hay humano ahora?` → `Humano aparecio?` (`{{ $json.hasHumanoLabel }}` equals true) → [true] `Aviso humano tomo chat` (**terminal: la respuesta no se envía**) / [false] `Necesita Formatting?` → (`Formatting Agent - WhatsApp` |) `Split en Mensajes` → `Gate Error Tecnico` → `Tiene respuesta?` → `Loop Mensajes` …

**`Hay humano ahora?` (código completo):**
```js
const data = $input.first().json;
let hasHumanoLabel = false;
if (!(data.error || data.statusCode >= 400)) {
  const conversations = data.payload || [];
  try {
    for (const conv of conversations) {
      if (conv.labels && Array.isArray(conv.labels) && conv.labels.includes('humano')) {
        hasHumanoLabel = true;
        break;
      }
    }
  } catch (e) { hasHumanoLabel = false; }
}
const original = $('Banlist Validator').first().json;
return [{ json: { ...original, hasHumanoLabel } }];
```
**`Aviso humano tomo chat` (código completo):**
```js
const phone = ($('Preparar Mensaje Final').first().json.phone || '').toString();
const output = ($('Banlist Validator').first().json.output || '').toString().trim();
// Solo avisar si el bot tenia una respuesta real para enviar (no NO_REPLY/vacio)
if (!output || output === '[NO_REPLY]') {
  return $input.all();
}
const resumen = 'El bot detecto que ya estas atendiendo este chat y no envio su respuesta automatica. Tenia listo: «' + output + '»';
try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
    qs: { phone: phone, resumen: resumen, silencioso: 'true' },
    json: true,
  });
} catch (e) {
  console.log('aviso humano tomo chat fail:', e.message);
}
return $input.all();
```

### 3d. Post-output re-check #2 (por cada parte del mensaje)
`Loop Mensajes` (splitInBatches, batchSize 1; `main[1]` → `Evolution - Typing`) → `Evolution - Typing` (POST `https://evo.raquelrodriguez.com.ar/message/presence`, `state: composing`, `onError: continueRegularOutput`) → `Gate Humano Final` → `Evolution API - Enviar Mensaje` (POST `https://evo.raquelrodriguez.com.ar/send/text`, body `{"number": <remoteJid dígitos>, "text": $('Loop Mensajes').first().json.message}`, header `apikey` presente, valor omitido) → vuelve a `Loop Mensajes`. (`Es primer mensaje?` y `Delay Humano` están **desconectados** de entrada — no reciben nada; `Evolution - Typing` recibe de `Loop Mensajes:main[1]`.)

**`Gate Humano Final` (código completo; token omitido):**
```js
// Gate Humano Final (2026-06-09): segundo re-check JUSTO antes de enviar.
// Cubre el tail (~11s: Formatting+Typing+Delay) que el primer re-check no alcanza.
const items = $input.all();
const phone = ($('Preparar Mensaje Final').first().json.phone || '').toString();
let hasHumano = false;
try {
  const contactId = $('Existe paciente?').first().json.payload[0].id;
  const convs = await this.helpers.httpRequest({
    method: 'GET',
    url: 'https://chat.raquelrodriguez.com.ar/api/v1/accounts/1/contacts/' + contactId + '/conversations',
    headers: { 'api_access_token': '<TOKEN CHATWOOT HARDCODEADO EN EL jsCode — valor omitido>' },
    json: true,
  });
  const list = (convs && convs.payload) || [];
  for (const c of list) {
    if (c.labels && Array.isArray(c.labels) && c.labels.includes('humano')) { hasHumano = true; break; }
  }
} catch (e) {
  hasHumano = false; // fail-open: enviar
}
if (!hasHumano) {
  return items; // sin humano -> enviar normal (pairedItem intacto)
}
// humano tomo durante el tail -> NO enviar + avisar al grupo
const output = ($('Banlist Validator').first().json.output || '').toString().trim();
if (output && output !== '[NO_REPLY]') {
  try {
    await this.helpers.httpRequest({
      method: 'POST',
      url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
      qs: { phone: phone, resumen: 'El bot detecto que ya estas atendiendo este chat y no envio su respuesta automatica (lo tomaste mientras escribia). Tenia listo: «' + output + '»' , silencioso: 'true' },
      json: true,
    });
  } catch (e) {
    console.log('gate humano final aviso fail:', e.message);
  }
}
return [];
```

### 3e. RESPUESTA EXACTA: ¿qué hace que un chat quede en "humano atendiendo"?
**Única fuente de verdad determinística: el label `humano` en CUALQUIER conversación de Chatwoot (cuenta 1) del contacto cuyo `phone` matchea.** Se evalúa 3 veces por ejecución (pre-LLM `Verificar Label Humano`, post-output `Hay humano ahora?`, pre-envío `Gate Humano Final`).
- **NO es un flag Redis** (no existe key alguna por teléfono para esto).
- **NO es la fecha del último `fromMe` en `n8n_chat_histories`**: el nodo `Check Humano Reciente (DB)` (24 h, sources `wa_outbound`/`human_takeover`, `scripts/apply_fix_gate_humano_reciente.py`, 15/7) estuvo en el v6 solo entre `v6_POST_gate_humano_reciente_20260716_105637.json` y `v6_PRE_supav3_DRYRUN_20260718_130238.json` (ya no está) y `Bot Activo?` hoy tiene una sola condición (`hasHumanoLabel`). Las filas `[ATENCION HUMANA …]` de esa tabla hoy solo actúan en **capa prompt**: entran al Router vía `Build Router Context` (últimos 6 mensajes de `n8n_chat_histories` del `session_id`, excluyendo `[CONTEXTO%`, `[NO_REPLY]` e intents) y a los sub-agents vía `Postgres Chat Memory` (ventana 10), con la instrucción "Mantente en silencio … hasta que un admin diga /bot on" → el LLM *puede* devolver `[NO_REPLY]`, pero nada lo obliga (en exec `270010` no lo hizo).

**Quién APLICA el label `humano`** (3 escritores):
1. v6 rama `fromMe` (`CW Set Label humano`) — cualquier saliente del número del consultorio que llegue como webhook con `IsFromMe`, texto, media o **reacción**.
2. `Human Takeover - Chatwoot` (`w7BBpZeEwZnpCX1q`, webhook `/webhook/chatwoot-takeover`): evento `message_created` outgoing de `sender.type === 'user'` sin `source_id` → `Chatwoot - Set Label` `{"labels":["humano"]}` + reenvía el texto a WA (`Evolution API - Enviar a WA`) + guarda en `n8n_chat_histories` con `source: 'human_takeover'` (`PG - Save Human Msg`). Evento `conversation_status_changed` a `resolved` → `{"labels":["bot"]}`.
3. **`Helper - Notify Grupo` (`S5U6tSipzlgFHCkf`), nodo `Chatwoot Apply`: corre en TODA llamada a `/webhook/notify-grupo`, silenciosa o no** (ver sección 4). Es decir: **cada escalación del propio bot marca el chat como "humano atendiendo".**

**Cuánto dura**: hasta que alguien lo saque. Los limpiadores son:
- `Auto Reactivar Bot (1h sin humano)` (`fosfga62zNaN0qrx`, cron cada 15 min): GET `/api/v1/accounts/1/conversations?labels[]=humano&status=open`; `Filtrar > 1 hora inactivas`: `ONE_HOUR = 3600`; salta las que tienen label `no_bot`; `now - conv.last_activity_at > 3600` → `Chatwoot - Label Bot` POST `/conversations/{id}/labels` `{"labels":["bot"]}`. En la práctica **60–75 min desde la última actividad de cualquiera de las partes** (paciente incluido: si el paciente sigue escribiendo, el reloj se reinicia). **Solo conversaciones `open`**: un `humano` en una conversación `resolved`/`pending` no se limpia nunca por esta vía, y `Verificar Label Humano` sí lo ve.
- Resolver la conversación en Chatwoot (Human Takeover → `bot`).
- Manual: POST labels sin `humano` (p.ej. `scripts/remove_humano_label.py`, que ya apunta a `5491161461034` — ojo: tiene el token Chatwoot hardcodeado).
- `/bot on` **no** lo limpia.

### 3f. CASO REAL 5491161461034 — 3/9 21:48Z (verificado con la API de ejecuciones)
Ejecución v6 = **`270010`** (21:47:41.372Z → 21:48:17.601Z, phone `5491161461034`, texto "buenas sabes que se me salió el bracket y pincha", 55 nodos). Timeline UTC:
- 21:48:03.9 `Chatwoot - Buscar Conversacion` (contact id **1**, `+5491161461034`, 9 `contact_inboxes`) → 21:48:05.99 `Verificar Label Humano` → **`{"hasHumanoLabel": false}`** → `Bot Activo?` → rama false (bot activo). **El label del 2/9 ya no estaba.**
- `Check Session Age` → última fila de memoria: id **5912**, `created_at 2026-09-02T19:37:34Z` (la `[ATENCION HUMANA …]` de la reacción fromMe; no es stale, <7 días).
- 21:48:08.2 `Router - Clasificar Intent` → `Parse Intent` `intent: "urgencia_dolor"` → `Sub-Agent Urgencia` (21:48:08.222 → +6636 ms).
- 21:48:11.389 tool **`escalar_a_secretaria`** (2131 ms) → Helper exec **`270011`** (21:48:11.428 → 21:48:13.509): `Log Escalacion` → **escalaciones_log id 189** (`telefono 5491161461034`, `motivo "Paciente informa que se le salió un bracket que pincha; solicita coordinación urgente."`, `origen bot`, `exec_id 270011`) → `Silencioso?` out[0] (no silencioso) → `Notify Grupo Send` (WhatsApp `[ESCALADO BOT] …` al grupo `120363407321448469@g.us`, Evolution respondió `success`, enviado como `5493885786946:70` = número del consultorio) → **`Chatwoot Apply` → `{"applied_label_only": true, "contactId": 1, "convId": 272}`** (label `humano` puesto en conv 272 ~21:48:12–13.5). La duración de la tool (2131 ms) ≈ duración del Helper (2081 ms): el webhook del Helper tiene `responseMode: lastNode`, o sea **la tool bloquea hasta que el label ya está aplicado**.
- 21:48:14.858 `Sub-Agent Urgencia` devuelve el canned `"Recibimos tu mensaje. Le pasamos a la doctora para que le coordine lo antes posible."` → `Fallback Output` → `Canned Sidecar` → `Gate Pago Tratamiento` → 21:48:14.886 `Banlist Validator` (`banlist_triggered: null`, `escalate_to_human: false`).
- 21:48:14.914 `Re-check Humano` (629 ms) → `Hay humano ahora?` → **`hasHumanoLabel: true`** → `Humano aparecio?` out[0] → 21:48:15.555 `Aviso humano tomo chat` → Helper exec **`270012`** (21:48:15.760): `Log Escalacion` → **id 190** (`motivo "El bot detecto que ya estas atendiendo este chat y no envio su respuesta automatica. Tenia listo: «Recibimos tu mensaje. Le pasamos a la doctora para que le coordine lo antes posible.»"`, header `user-agent: n8n`) → `Silencioso?` out[1] (silencioso=true) → sin WhatsApp → `Chatwoot Apply` de nuevo (conv 272). **La respuesta al paciente nunca se envió** (`Evolution API - Enviar Mensaje` no corrió; `Gate Humano Final` tampoco).
- 23:00:53Z `Auto Reactivar` exec `270042`: `{"conversationId": 272, "lastActivity": 1788472093, "minutesInactive": 73}` → `Chatwoot - Label Bot` → `{"payload": ["bot"]}`. **Desde ahí el label `humano` de conv 272 está limpio** (salvo que algo lo haya re-aplicado después; no consulté Chatwoot en vivo).

**Conclusión exacta**: el fromMe del 2/9 19:37Z **NO fue la causa** (su label lo quitó `Auto Reactivar` exec `269239` el 2/9 20:45:53Z: conv 272, 68 min inactiva; y `Verificar Label Humano` dio `false` el 3/9). **La causa es el propio bot: `escalar_a_secretaria` → `Chatwoot Apply` aplica `humano` sincrónicamente → `Re-check Humano` lo detecta 1.4 s después → suprime la respuesta y loguea la escalación 190 "silenciosa".** No es un caso aislado: escaneé las 790 ejecuciones del v6 desde el 30/8 — 8 llamaron `escalar_a_secretaria`; **6/6 con contacto existente en Chatwoot fueron suprimidas** (`preLabel=false → postLabel=true → Aviso humano tomo chat`, `enviado=false`: execs 267708, 267736, 267938, 269215, 269595, 270010, incluidos 2 comprobantes y 3 urgencias reales), y las únicas 2 que sí se enviaron (270375, 270379, ambas 4/9) fueron porque `Chatwoot Apply` devolvió `{"skipped": true, "reason": "contact not found"}`. En el Helper, 7 de 11 escalaciones no silenciosas desde el 28/8 tienen su gemela `silencioso=true` 2–8 s después (ids 177/178, 179/180, 181/182, 183/184, 185/186, 187/188, 189/190). Consistente con la decisión del 4/8 ("49 de 98 escalaciones eran 'ya estás atendiendo'"): esa mitad es el bot bloqueándose a sí mismo, y el canned de cierre que el prompt del Sub-Agent Urgencia exige ("Responder al paciente EXACTAMENTE: 'Recibimos tu mensaje…'") **no le llega a ningún paciente que exista en Chatwoot**.

### 3g. Cómo dejar `5491161461034` limpio para una demo
1. **Chatwoot (lo único que bloquea de forma determinística)**: contacto id `1` (`+5491161461034`), conversación `272` (la que usa el Helper: `payload[0]`; el contacto tiene 9 `contact_inboxes`, puede tener más de una conversación). Verificar `GET /api/v1/accounts/1/contacts/1/conversations` y que **ninguna** conversación (de cualquier status) tenga `humano`; si alguna lo tiene, `POST /api/v1/accounts/1/conversations/<id>/labels` con `{"labels":["bot"]}` (o correr `scripts/remove_humano_label.py`). Estado conocido: limpio desde el 3/9 23:00:53Z por `Auto Reactivar`. **No** poner `no_bot` (Auto Reactivar lo respeta y nunca reactivaría).
2. **`n8n_chat_histories` (Supabase v3, credencial `Postgres Supabase Nexora v3`)**, `session_id = '5491161461034'`: fila **id 5912** (`source: wa_outbound`, placeholder de la reacción del 2/9) + recordatorios `[TEST 72h]` de Salvador/Tianna + notas internas (se ven en `Build Router Context` de exec 270010). No bloquean determinísticamente, pero contaminan el contexto del Router/sub-agents y el tag pide silencio. Recomendado: `DELETE FROM n8n_chat_histories WHERE session_id = '5491161461034'`; mínimo: `… AND message->'additional_kwargs'->>'source' IN ('wa_outbound','human_takeover')`. Importante: `Clear Old Memory` **jamás** borra esas dos sources aunque la sesión esté stale (>7 días), así que no se limpian solas.
3. **Redis**: no hay key de humano. Conviene `DEL chat_buffer:5491161461034` (por si quedó huérfano) y **`DEL ratelimit:5491161461034`** antes de la demo (límite 10 mensajes / 15 min deslizante; el 11.º se descarta en silencio). Chequear `GET bot:status` ≠ `disabled` y `GET dentalink:status` ≠ `down`.
4. `escalaciones_log` ids 189/190 y `triaje_urgencias_log` (la sombra ya los pudo haber procesado): solo registro/métricas, no afectan el gate. Borrar opcionalmente para no ensuciar el reportero.
5. Durante la demo: nadie escribe ni **reacciona** desde el celu del consultorio ni desde Chatwoot en ese chat (1 h de silencio + fila en memoria). Y, por el mecanismo de 3f, **si el bot escala durante la demo, su respuesta/caption se suprime**: el video de triaje debe salir por un camino que no dependa del re-check, o la escalación no debe aplicar el label en ese caso.

---

## 4) Patrón `escalar_a_secretaria` y Helper Notify Grupo

**`escalar_a_secretaria`** (`@n8n/n8n-nodes-langchain.toolHttpRequest` v1.1, `ai_tool` hacia los 5 sub-agents `Sub-Agent Confirmar/Cancelar/Agendar/Urgencia/General`):
- `method: POST`, `url`: `=https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo?phone={{ $('Edit Fields - Extraer Datos').first().json.phone }}` (host n8n propio, path `/webhook/notify-grupo`, **sin auth**).
- `sendQuery: true`, `parametersQuery.values: [{ name: "resumen" }]` → el LLM solo aporta `resumen` (el prompt del Sub-Agent Urgencia lo llama `query`); `phone` va fijo en la URL; **no manda `silencioso`** (→ WhatsApp al grupo). `optimizeResponse: true`, sin body.
- `toolDescription` textual: "Escala el caso a la secretaria humana: deriva al grupo de WhatsApp del consultorio Y aplica el label 'humano' en Chatwoot (el bot se silencia y deja de responder hasta que un humano atienda). … El telefono del paciente se adjunta AUTOMATICAMENTE, no lo pases vos. CRITICO: NUNCA llamar a esta tool sin pasar resumen no vacio. UNA sola vez por turno."

Otros llamadores del mismo webhook en el v6 (todos `this.helpers.httpRequest` POST con `qs`): `Aviso humano tomo chat` (`{ phone, resumen, silencioso: 'true' }`), `Gate Humano Final` (`{ phone, resumen: '…(lo tomaste mientras escribia)…', silencioso: 'true' }`), `Gate Error Tecnico` (`{ phone, resumen: 'Bot tuvo error tecnico (max iterations / agent stopped)…' }`, sin silencioso), `Gate Pago Tratamiento` (`{ phone, resumen: 'Paciente pregunta si puede abonar TRATAMIENTO (no consulta)…' }`, sin silencioso). También lo usa el Sub-WF Cancelar (no mapeado acá).

**`Helper - Notify Grupo`** (`S5U6tSipzlgFHCkf`, activo, `updatedAt` 2026-08-06): `Webhook` (POST `notify-grupo`, **`responseMode: lastNode`** → el caller espera el workflow completo) → `Log Escalacion` → `Silencioso?` → [out0 = NO silencioso] `Notify Grupo Send` → `Chatwoot Apply`; [out1 = silencioso] `Chatwoot Apply` directo.
- **`Log Escalacion`** (Postgres insert, credencial `Postgres Supabase Nexora v3`): tabla `public.escalaciones_log`, columnas `telefono` = `{{ $('Webhook').first().json.query?.phone || …body?.phone || '' }}`, `motivo` = `{{ …query?.resumen || …body?.text || 'sin resumen' }}`, `origen` = `'bot'` (literal), `exec_id` = `{{ $execution.id }}` (el id de la ejecución del Helper, no del v6). Devuelve `id`, `created_at`. **Siempre corre, también en el caso silencioso** (por eso existen 190, 178, 180…).
- **`Silencioso?`**: `{{ (query.silencioso) || (body.silencioso) || '' }}` string **notEquals** `'true'` (typeValidation loose).
- **`Notify Grupo Send`** = **quien manda el WhatsApp al grupo**: POST `https://evo.raquelrodriguez.com.ar/send/text`, header `apikey` presente (valor omitido), body `{"number": "120363407321448469@g.us", "text": '[ESCALADO BOT] ' + (query.resumen || body.text || 'Caso escalado sin resumen.')}`.
- **`Chatwoot Apply`** (Code): `phone = (query.phone || body.phone).replace(/^\+/,'')`; token = `$env.CHATWOOT_TOKEN` con **fallback hardcodeado en el jsCode (valor omitido)**; `GET /contacts/search?q=<phone>` → `contactId = payload[0].id`; `GET /contacts/<id>/conversations` → `convId = payload[0].id` (**la primera, no la `open`**, a diferencia de `CW Pick Conv`); `POST /conversations/<convId>/labels` body `{ labels: ['humano'] }`. Devuelve `{ applied_label_only: true, phone, contactId, convId }` o `{ skipped: true, reason: 'contact not found' | 'conv not found' }`. Comentario del nodo: "SOLO label humano. NO mas private notes hasta resolver el bug".

Resumen del contrato: **`escalaciones_log` lo escribe siempre el Helper (`Log Escalacion`); el WhatsApp al grupo lo manda solo el Helper (`Notify Grupo Send`) y solo si `silencioso !== 'true'`; el label `humano` lo aplica siempre el Helper (`Chatwoot Apply`), silencioso o no.** El v6 nunca escribe en `escalaciones_log` ni manda al grupo directo.

---

## 5) Otros hallazgos relevantes para insertar el triaje
- Evidencia de que los envíos del propio bot **no** rebotan como `fromMe`: tras exec `270375` (respuesta enviada a `…6256` a las 13:16Z del 4/9) no apareció ninguna ejecución `fromMe` para ese phone en la ventana 13:15–13:30Z (solo 270375, 270379 sintética y 270383 = mensaje humano real de la Dra a otro paciente, `remoteJid …@lid`). Un solo muestreo y solo `/send/text`; conviene confirmar para `/send/media`.
- `Sub-Agent Urgencia`: `text` = `$('Preparar Mensaje Final').first().json.text`; systemMessage (9024 chars) exige "1. Llamar `escalar_a_secretaria` … 2. Responder al paciente EXACTAMENTE: 'Recibimos tu mensaje. Le pasamos a la doctora…'", "Si el paciente insiste tras escalar -> el label humaño ya esta aplicado. Devolver `[NO_REPLY]`", y "La tool ya aplico el label humaño en Chatwoot". El prompt asume que el canned se entrega; el pipeline lo suprime.
- Flags de error: `Existe paciente?` sin continueOnFail (Chatwoot caído = bot mudo, fail-closed); `Chatwoot - Buscar Conversacion` y `Re-check Humano` `continueOnFail: true` (fail-open); `Gate Humano Final` try/catch fail-open; nodos Redis sin continueOnFail (Redis caído = ejecución en error = bot mudo); `Postgres - Save fromMe` sin continueOnFail.
- Tokens hardcodeados: Chatwoot `api_access_token` en el jsCode de `Gate Humano Final`, en el fallback de `Chatwoot Apply` (Helper) y en `scripts/remove_humano_label.py`; `apikey` Evolution en headers de `Evolution API - Enviar Mensaje`, `Evolution - Typing`, `HTTP Send Admin Confirm`, `Notify Grupo Send`, `Evolution API - Enviar a WA`. Valores omitidos.
- Settings del v6: `executionOrder v1`, `callerPolicy workflowsFromSameOwner`.

## KEY FACTS
- Redis en el v6: 7 nodos, credencial única 'Redis account' (kdtSKwGbN1xAZeUh). Keys: chat_buffer:<phone> (push/get list/delete, sin TTL), ratelimit:<phone> (INCR, expire true, ttl 900, límite count<=10), bot:status (SET/GET global, sin TTL) y dentalink:status (solo GET). NO existe ninguna key Redis de 'humano'/'silence' por teléfono (la silence:<phone> EX 7200 fue reemplazada por el label de Chatwoot).
- phone = primer JID de [Info.Chat, Info.Sender, Info.RecipientAlt, Info.SenderAlt] terminado en @s.whatsapp.net, split('@')[0].split(':')[0] → dígitos con país, sin '+' ni sufijo de dispositivo (5491161461034). Es el mismo string en Redis keys, session_id de n8n_chat_histories, q de Chatwoot, phone de notify-grupo y telefono de escalaciones_log.
- 'Buffer: Wait 10s' espera 22 segundos (amount: 22). 'Soy el ultimo?' compara el key_id del último elemento de la lista con el de la ejecución; solo esa sigue. 'Buffer: Limpiar' hace DEL después de Build Router Context.
- Kill-switch: solo global (bot:status). Comandos /bot off|on|status vía regex ^\/bot\s+(off|on|status)\b, solo si fromMe=false y phone ∈ ADMINS hardcodeados {5491161461034 Lucas, 5493885786946 Irina, 5493513976787 Dra. Raquel}. No hay comando por chat. /bot status no lee Redis. /bot on no quita labels ni memoria.
- El modo 'humano atendiendo' es EXCLUSIVAMENTE el label 'humano' en cualquier conversación de Chatwoot (cuenta 1) del contacto con ese phone, chequeado 3 veces por ejecución: 'Verificar Label Humano' (pre-LLM, → 'Bot Activo?' → 'Humano Atendiendo (no hacer nada)'), 'Hay humano ahora?' (post-output, → 'Aviso humano tomo chat', terminal) y 'Gate Humano Final' (pre-envío, return []). Todos fail-open si Chatwoot falla; pero 'Existe paciente?' no tiene continueOnFail (Chatwoot caído = bot mudo).
- No hay gate determinístico sobre n8n_chat_histories hoy: 'Check Humano Reciente (DB)' (24h, sources wa_outbound/human_takeover) existió solo entre el 16/7 y el 18/7 y 'Bot Activo?' tiene una única condición (hasHumanoLabel). Las filas [ATENCION HUMANA …] solo actúan en capa prompt (Build Router Context últimos 6 + Postgres Chat Memory ventana 10) y Clear Old Memory NUNCA las borra.
- Tres escritores del label humano: (1) rama fromMe del v6 (CW Set Label humano) — incluye reacciones y multimedia salientes del consultorio; (2) Human Takeover (w7BBpZeEwZnpCX1q) por mensajes de agente en Chatwoot; (3) Helper - Notify Grupo 'Chatwoot Apply' en TODA llamada a /webhook/notify-grupo, silenciosa o no → cada escalación del bot marca humano.
- Duración: hasta que Auto Reactivar Bot (fosfga62zNaN0qrx, cada 15 min) ponga labels ['bot'] en conversaciones OPEN con humano y last_activity_at > 3600 s (sin no_bot) → efectivo 60–75 min desde la última actividad de cualquiera; o resolución de la conversación (Human Takeover → bot); o remoción manual. Labels humano en conversaciones no-open nunca se limpian solas y sí bloquean. **[2026-09-10] Este corte de 3600s/60-75min pasa a 24h (86400s) — pedido de Lucas, ver `docs/handoff-humano-24h-2026-09-10.md`; el efecto de auto-silencio post-escalación descripto en el caso real de abajo se agrava con ese cambio (queda hasta 24h en vez de 60-75 min salvo intervención manual).**
- CASO REAL 3/9 21:48Z (v6 exec 270010): Verificar Label Humano = false (el label del fromMe del 2/9 ya lo había quitado Auto Reactivar exec 269239 a las 20:45:53Z del 2/9). Sub-Agent Urgencia llamó escalar_a_secretaria → Helper exec 270011 (escalaciones_log 189, WhatsApp al grupo, Chatwoot Apply label humano en conv 272 del contacto id 1, sincrónico por responseMode lastNode) → 1.4 s después Re-check Humano vio el label → Aviso humano tomo chat → Helper exec 270012 (id 190, silencioso=true) → la respuesta 'Recibimos tu mensaje…' nunca se envió. Auto Reactivar exec 270042 limpió conv 272 (→ ['bot']) el 3/9 23:00:53Z.
- El auto-bloqueo post-escalación es sistemático: de 790 ejecuciones del v6 desde el 30/8, 8 llamaron escalar_a_secretaria; 6/6 con contacto en Chatwoot fueron suprimidas (postLabel=true, enviado=false); las 2 enviadas fueron porque Chatwoot Apply devolvió 'contact not found'. En el Helper, 7 de 11 escalaciones no silenciosas desde el 28/8 tienen gemela silenciosa 2–8 s después (177/178 … 189/190). El canned de cierre del Sub-Agent Urgencia no le llega a ningún paciente con contacto en Chatwoot.
- escalar_a_secretaria: toolHttpRequest POST https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo?phone={{ $('Edit Fields - Extraer Datos').first().json.phone }}, query param 'resumen' (único que aporta el LLM), sin 'silencioso', sin auth, conectada como ai_tool a los 5 sub-agents. 'Aviso humano tomo chat' y 'Gate Humano Final' llaman al mismo webhook con this.helpers.httpRequest y qs { phone, resumen, silencioso: 'true' }.
- Helper - Notify Grupo (S5U6tSipzlgFHCkf): Webhook (responseMode lastNode) → Log Escalacion (INSERT escalaciones_log: telefono, motivo, origen 'bot', exec_id del Helper; SIEMPRE) → Silencioso? (silencioso notEquals 'true') → [no] Notify Grupo Send (POST evo /send/text a 120363407321448469@g.us con '[ESCALADO BOT] '+resumen) → Chatwoot Apply; [sí] Chatwoot Apply directo. Solo el Helper escribe escalaciones_log y manda al grupo.
- Para dejar 5491161461034 limpio: (1) Chatwoot contacto id 1 / conv 272 — asegurar que ninguna conversación (cualquier status) tenga 'humano' (POST labels ['bot'] o scripts/remove_humano_label.py); estado conocido: limpio desde 3/9 23:00:53Z. (2) DELETE FROM n8n_chat_histories WHERE session_id='5491161461034' (mínimo las filas con source wa_outbound/human_takeover, ej. id 5912 del 2/9 19:37Z, creada por una REACCIÓN fromMe). (3) Redis: DEL chat_buffer:5491161461034 y DEL ratelimit:5491161461034; bot:status ≠ disabled, dentalink:status ≠ down. (4) escalaciones_log 189/190 son solo registro.
- Los envíos del propio bot no rebotan como fromMe (tras exec 270375 no hubo ejecución fromMe para ese phone); muestra única y solo /send/text.
- Tokens hardcodeados (valores omitidos): Chatwoot api_access_token en el jsCode de Gate Humano Final, en el fallback de Chatwoot Apply del Helper y en scripts/remove_humano_label.py; apikey Evolution en headers de Enviar Mensaje, Typing, HTTP Send Admin Confirm, Notify Grupo Send y Enviar a WA.
- v6_LIVE.json local == workflow vivo (updatedAt 2026-09-04T13:22:48Z, 125 nodos, parámetros y conexiones idénticos).

## RISKS
- Auto-silencio post-escalación: cualquier POST a /webhook/notify-grupo (con o sin silencioso) aplica label humano vía Chatwoot Apply; como 'Re-check Humano' y 'Gate Humano Final' corren después, toda respuesta/caption generada en el mismo turno que una escalación se suprime si el paciente existe en Chatwoot (6/6 casos desde el 30/8). Si el triaje escala por red flag y además quiere mandar un canned de contención, no llega; si manda video y escala en el mismo turno, el video solo sale si se envía desde un punto anterior al Re-check (p.ej. una tool dentro del sub-agent) o si la escalación no aplica label en ese caso.
- El video de triaje enviado en el pipeline de salida (después de Banlist Validator) queda sujeto a los mismos 2 re-checks: cualquier label humano (por fromMe previo, escalación previa dentro de la hora, o takeover) lo bloquea silenciosamente y solo deja una fila 'silenciosa' en escalaciones_log.
- Rate limit 10 mensajes / 15 min deslizante por phone (TTL renovado en cada INCR): las preguntas guiadas del triaje + fotos + respuestas cortas del paciente pueden llegar al 11.º mensaje y descartarse en silencio (Rate Limit Excedido (NoOp)). Igual en una demo con Lucas escribiendo rápido.
- Buffer de 22 s ('Buffer: Wait 10s' amount 22): las respuestas a preguntas guiadas se agrupan y la reacción del bot tarda ≥22 s; si el paciente manda foto + texto separados, entran como un solo mensaje concatenado. Si una ejecución muere antes de 'Buffer: Limpiar', el buffer huérfano se pega al próximo mensaje (sin TTL).
- dentalink:status='down' silencia TODO el bot (Bot Disabled (NoOp)), incluidas urgencias y el triaje: la caída de la agenda apaga la contención de urgencias.
- Chatwoot caído: 'Existe paciente?' no tiene continueOnFail → la ejecución falla antes del Router y el bot queda mudo (fail-closed) para todo, urgencias incluidas; los otros chequeos son fail-open (Re-check continueOnFail, Gate Humano Final try/catch).
- 'Verificar Label Humano' mira todas las conversaciones del contacto sin importar status, pero Auto Reactivar solo limpia status=open: un label humano en una conversación resuelta/pending bloquea al bot indefinidamente. Además 'Chatwoot Apply' del Helper etiqueta payload[0] (no la open), inconsistente con 'CW Pick Conv'.
- Cualquier reacción/emoji o multimedia enviado desde el celular del consultorio (fromMe, incluso por LID) marca humano 1 h y deja una fila [ATENCION HUMANA] permanente (Clear Old Memory la preserva) que le pide silencio al LLM 'hasta que un admin diga /bot on' — y /bot on no la limpia. En una demo, una reacción de la Dra al chat de Lucas apaga el bot para ese chat.
- Los ADMINS y el número de la clínica están hardcodeados en 'Kill-switch Check'; los mensajes normales de un admin se tratan como paciente (bien para demos, pero la demo del admin comparte contacto Chatwoot id 1 con 9 contact_inboxes y conv 272 con historial real).
- Tokens hardcodeados en jsCode (Gate Humano Final, Chatwoot Apply fallback) y en scripts: cualquier nodo nuevo del triaje que copie el patrón repite la fuga; usar $env/credenciales.
- El campo exec_id de escalaciones_log guarda el id de ejecución del Helper, no del v6: para correlacionar un caso del triaje con la ejecución del v6 hay que buscar por telefono+created_at (como hizo la sombra), no por exec_id.
- Inserción del triaje entre Router y Sub-Agent Urgencia: el gate de red flags debe correr solo en el camino urgencia_dolor (Gate Pago Tratamiento ya excluye ese intent); tocar 'Bot Activo?' o los re-checks cambia el comportamiento de los 5 sub-agents a la vez.
- La instrucción del Sub-Agent Urgencia ('Si el paciente insiste tras escalar -> el label humaño ya esta aplicado. Devolver [NO_REPLY]') se basa en que el label persiste; con Auto Reactivar a 1 h, el 'segundo mensaje del mismo problema' (patrón real de re-escalación) vuelve a entrar al bot sin memoria determinística del caso.

## OPEN QUESTIONS
- ¿El auto-silencio post-escalación es intencional? La toolDescription dice 'el bot se silencia', pero el prompt del Sub-Agent Urgencia y los otros canneds de escalación asumen que el mensaje de cierre le llega al paciente. Hoy no le llega a nadie con contacto en Chatwoot (verificado 6/6 desde el 30/8). Decidir antes del piloto: ¿Chatwoot Apply debe saltarse cuando el que escala es el propio bot en el mismo turno, o el Re-check debe ignorar labels aplicados por su propia ejecución?
- ¿Evolution GO emite webhook fromMe para mensajes enviados por API /send/media? Solo verifiqué un caso de /send/text (no rebota). Si /send/media rebotara, cada video marcaría humano 1 h y guardaría [ATENCION HUMANA] en memoria.
- Estado en vivo de los labels de las conversaciones del contacto Chatwoot id 1 (+5491161461034): no consulté Chatwoot (fuera del alcance solo-lectura acordado); la última evidencia es Auto Reactivar exec 270042 poniendo ['bot'] en conv 272 el 3/9 23:00:53Z. Verificar antes de la demo, incluyendo conversaciones no-open.
- ¿Quién escribe dentalink:status y qué valores usa (solo 'down'/otro)? El v6 solo lo lee; asumo Health Check (Yjl6kyLnALhIfbFX), no mapeado.
- ¿Se quiere restituir un gate determinístico por memoria (el 'Check Humano Reciente (DB)' del 15/7 desapareció entre el 16/7 y el 18/7 sin registro en memory/)? Hoy la única defensa contra 'paciente responde al staff después de 1 h' es prompt-layer.
- ¿Qué hacer con el rate limit (10/15 min) para el flujo de preguntas guiadas del triaje: bypass por intent urgencia, subir el límite, o contar solo turnos procesados?