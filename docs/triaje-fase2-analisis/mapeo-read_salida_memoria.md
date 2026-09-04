# Mapa de SALIDA + memoria del v6 (`workflows/current/v6_LIVE.json`)

**Fuente verificada**: el snapshot local tiene `versionId 99e1e7aa-c397-4186-a7bd-8a760460cb76`, `updatedAt 2026-09-04T13:22:48Z`, 125 nodos — un GET read-only a la API de n8n (usando `.env`, valores no impresos) devolvió EXACTAMENTE el mismo versionId/updatedAt: el snapshot ES el v6 vivo (activo). El Logger vivo (`xsXeHp7WLXnFQc3o`) también se confirmó por GET: activo, 10 nodos (3 duplicados inertes), cron cada 5 min, versionId `905ca55b-…`, updatedAt 2026-08-06T01:17:42Z = la versión PRE del fix revertido (`workflows/history/logger_PRE_fix_no_ficha_falsa.json`, sin el nodo IF).

---

## 1) Camino de SALIDA (desde los sub-agents hasta WhatsApp)

### 1.0 Orden exacto del grafo (main connections)

```
Sub-Agent Confirmar [0] ─┐
Sub-Agent Cancelar  [0] ─┤   (Cancelar está desconectado del Switch: el Switch out 1 va a
Sub-Agent Agendar   [0] ─┤    'Execute Sub-WF Cancelar' → 'Format Sub-WF Output' [0] ─┐ )
Sub-Agent Urgencia  [0] ─┼──► Fallback Output ◄───────────────────────────────────────┘
Sub-Agent General   [0] ─┤          ▲
Set NO_REPLY        [0] ─┘          │ (7 entradas, todas a in 0)
                                    ▼
                          Canned Sidecar [0] ──► Gate Pago Tratamiento [0] ──► Banlist Validator
                                                                                    │ out 0 (dos destinos en paralelo)
                                     ┌──────────────────────────────────────────────┴───────────────┐
                                     ▼                                                              ▼
                              Re-check Humano [0] ──► Hay humano ahora? [0] ──► Humano aparecio?   Banlist Shadow - Prep [0] ──► Banlist Shadow - LLM [0] ──► Banlist Shadow - Log (fin, sin salida)
                                                                                 │ out 0 (true)  ──► Aviso humano tomo chat (FIN: no envía nada)
                                                                                 │ out 1 (false) ──► Necesita Formatting?
                                                                                                     │ out 0 (true)  ──► Formatting Agent - WhatsApp [0] ──► Split en Mensajes
                                                                                                     │ out 1 (false) ──► Split en Mensajes
                                                                                                                                   │ [0]
                                                                                                                                   ▼
                                                                                                                       Gate Error Tecnico [0] ──► Tiene respuesta?
                                                                                                                                   │ out 0 (message NO contiene [NO_REPLY]) ──► Loop Mensajes (in 0)
                                                                                                                                   │ out 1 ──► PG - Delete NO_REPLY [0] ──► Descartar [NO_REPLY] (fin)
Loop Mensajes (splitInBatches v3, batchSize 1)
   out 0 "done" ──► (SIN CONEXIÓN)
   out 1 "loop" ──► Evolution - Typing [0] ──► Gate Humano Final [0] ──► Evolution API - Enviar Mensaje [0] ──► Loop Mensajes (in 0)  ← vuelve al loop
```

**Código muerto**: `Es primer mensaje?` (IF sobre `$json.partIndex == 0`) NO tiene ninguna entrada; sus salidas van a `Evolution - Typing` (out 0) y `Delay Humano` (out 1, Wait `={{ Math.min(4, Math.max(1.2, ($json.message || '').length / 30)) }}` seg) → `Evolution - Typing`. Ambos son vestigio del flujo pre-loop; hoy nunca corren.

### 1.1 Forma del item en cada tramo
- Hasta `Split en Mensajes` (inclusive entrada): campo de texto = **`output`** (string). Flags que se van sumando: `_flow/_action/_label_humano/_debug` (solo camino Sub-WF Cancelar), `canned_sidecar` (Sidecar), `gate_pago_tratamiento` (Gate Pago), `banlist_triggered | banlist_original_output | escalate_to_human` (Banlist), `hasHumanoLabel` (Hay humano ahora?).
- Desde `Split en Mensajes` en adelante: **`{ message, remoteJid, phone, partIndex, totalParts }`** (+ `_gate_replaced` si Gate Error Tecnico reemplazó). El texto pasa a llamarse **`message`**.
- Datos del paciente en todo el tail se leen SIEMPRE de `$('Preparar Mensaje Final').first().json` → `{ phone, remoteJid, name, key_id, instance, text }` (`text` = mensajes del buffer unidos con `\n`).

### 1.2 Nodo por nodo (código/expresiones clave, citadas)

**`Fallback Output`** (Code) — `let output = it.json.output || ''; if (!output || output.trim() === '') output = '👍'; return { json: { ...it.json, output } }` (map sobre `$input.all()`).

**`Canned Sidecar`** (Code, 2026-09-02) — lee `pacienteMsg = $('Preparar Mensaje Final').first().json.text`; parte en oraciones; `PEDIDO` (interrogativo/imperativo) + `YA_HECHO`; reglas `pago` (enabled, `yaRespondido: /dra\.raquel\.aurea|\bCBU\b/i`), `precio` (enabled, `yaRespondido: /\$\s?\d/`, `supersededBy:'pago'`), `horarios` (`enabled:false`). **Passthrough explícito si `$('Parse Intent').first().json.intent === 'urgencia_dolor'`** y si `output` vacío o contiene `[NO_REPLY]`. Anexa con `output.trim() + '\n---\n' + aAnexar.join('\n---\n')` y setea `canned_sidecar`. Precio dinámico de `$('Extraer Horarios y Precio').first().json.precio_consulta` (fallback `'$50.000'`); alias/datos de cuenta hardcodeados (idénticos al prompt de General).

**`Gate Pago Tratamiento`** (Code, 2026-09-03) — mismo patrón por oraciones sobre el texto REAL del paciente; `PAGO = /\b(abon(ar|o|e|amos)?|pag(ar|o|u[eé]|amos)?|transfer(ir|encia|encias)?|deposit(ar|o)?|planes? de pago|se[ñn]a)\b/` y `TEMA_TRATAMIENTO = /\btratamientos?\b|\bcuotas?\b|\bbrackets?\b|\bortodoncia\b|\balineadores?\b|\binvisalign\b|\baparatos?\b|\bfrenillos?\b/`; si una oración matchea ambos → **REEMPLAZA** `output` por `'El pago del tratamiento lo coordina directamente la Dra. Raquel. Le paso su consulta para que se comunique con usted.'`, POST `https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo?phone=&resumen=…` y setea `gate_pago_tratamiento:true`. **Passthrough si intent === 'urgencia_dolor'**. OJO: `TEMA_TRATAMIENTO` incluye `brackets?` y `aparatos?` — solo se activa si en la misma oración hay verbo de pago, así que "se me soltó el bracket" NO dispara; igual, para el triaje, el bypass por intent lo cubre.

**`Banlist Validator`** — ver sección 2.

**`Re-check Humano`** (HTTP GET) — `url: =https://chat.raquelrodriguez.com.ar/api/v1/accounts/1/contacts/{{ $('Existe paciente?').first().json.payload[0].id }}/conversations`, header `api_access_token` (valor omitido). Sin `onError` → si Chatwoot cae o `payload[0]` no existe, la ejecución falla acá (el paciente no recibe nada).

**`Hay humano ahora?`** (Code) — recorre `data.payload[]`, `hasHumanoLabel = conv.labels.includes('humano')`; devuelve `{ ...$('Banlist Validator').first().json, hasHumanoLabel }` (re-inyecta el item del Banlist, se pierde nada porque lee `.first()`).

**`Humano aparecio?`** (IF v2.2) — `={{ $json.hasHumanoLabel }}` boolean equals `true`. out 0 → `Aviso humano tomo chat`; out 1 → `Necesita Formatting?`.

**`Aviso humano tomo chat`** (Code, sin salida) — `output = $('Banlist Validator').first().json.output`; si no es vacío ni `[NO_REPLY]` → POST `notify-grupo` con `qs: { phone, resumen: 'El bot detecto que ya estas atendiendo este chat y no envio su respuesta automatica. Tenia listo: «' + output + '»', silencioso: 'true' }`. **No manda nada al paciente.** Nota: el mensaje AI ya quedó escrito en `n8n_chat_histories` por el sub-agent aunque no se haya enviado.

**`Necesita Formatting?`** (IF v2, typeValidation loose) — `c1: ={{ ($json.output || '').length }} > 80` AND `c2: ={{ $json.output }} notContains '[NO_REPLY]'`. true → Formatting Agent; false → Split directo. Es decir: **todo texto > 80 chars pasa por un LLM** (gpt-5-mini) antes de salir.

**`Formatting Agent - WhatsApp`** (LangChain agent v1.8, sin memoria, sin tools) — `promptType: define`, `text: ={{ $json.output }}`, LM = `OpenAI Chat Model1` (`gpt-5-mini`, `reasoningEffort: low`, cred `OpenAi account` id `nYujqfon7GGDnJUO`). System prompt: REGLA #0 `[NO_REPLY]` passthrough; #1 `**`→`*`, sacar `#`/código; #2 tono usted, sacar `¿¡`, max 1 emoji, prohibido "Dale"; #3 horas `HH:MM hs`, fechas "Jueves 18 de Junio"; **#4 split con `---` solo cuando hay dato copiable (alias/CBU/email/tel/dirección/link), máx 3 partes, "NUNCA DESCARTES CONTENIDO" del bloque de cuenta**. Salida: campo `output`.

**`Split en Mensajes`** (Code) — código clave:
```js
const formateado = ($input.first().json.output || '').toString();
let original = ''; try { original = ($('Banlist Validator').first().json.output || '').toString(); } catch (e) { original = ''; }
const perdioDatos = /\bCBU\b/i.test(original) && !/\bCBU\b/i.test(formateado);
const output = perdioDatos ? original : formateado;
const remoteJid = $('Preparar Mensaje Final').first().json.remoteJid;
const phone = $('Preparar Mensaje Final').first().json.phone;
const parts = output.split('---').map(p => p.trim()).filter(p => p.length > 0);
if (parts.length === 0) return [{ json: { message: output.trim(), remoteJid, phone, partIndex: 0, totalParts: 1 } }];
return parts.map((msg, i) => ({ json: { message: msg, remoteJid, phone, partIndex: i, totalParts: parts.length } }));
```
→ **Sí, separador `'---'`** (split literal, sin regex; un `---` dentro de un texto también parte). Solo usa `$input.first()` (asume 1 item de entrada). Guard determinístico: si el original del Banlist traía `CBU` y el formateado lo perdió, usa el original completo.

**`Gate Error Tecnico`** (Code, corre POR PARTE, después del split) — `ERROR_REGEX = /agent stopped|max iterations|cannot read property|NodeOperationError|undefined is not/i` sobre `item.json.message`; si matchea: `message = 'Hola! Soy Asiri🤗, la secretaria virtual de la Dra. Raquel Rodríguez. Le envío la información a la secretaria, ella le responderá en su horario de atención. Gracias!'`, `_gate_replaced = true`, y POST `https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo` con `qs: { phone, resumen: 'Bot tuvo error tecnico (max iterations / agent stopped), revisar conversacion. Phone: ' + phone }` (best-effort try/catch).

**`Tiene respuesta?`** (IF v2.2, strict) — `={{ $json.message }}` string **notContains** `[NO_REPLY]`. out 0 → `Loop Mensajes`; out 1 → `PG - Delete NO_REPLY`.

**`PG - Delete NO_REPLY`** (Postgres v2.5, cred `Postgres Supabase Nexora v3` id `TpYhZX4UT61xAKSV`, `onError: continueRegularOutput`) — `DELETE FROM n8n_chat_histories WHERE id IN (SELECT id FROM n8n_chat_histories WHERE session_id = $1 AND message::jsonb->>'type' = 'ai' AND message::jsonb->>'content' = '[NO_REPLY]' ORDER BY id DESC LIMIT 1)`, `queryReplacement: ={{ $('Preparar Mensaje Final').first().json.phone }}` → `Descartar [NO_REPLY]` (NoOp, fin). Esto es lo que evita que `[NO_REPLY]` persista en memoria.

**`Loop Mensajes`** (splitInBatches v3, `batchSize: 1`, `options: {}`) — recibe N partes de `Tiene respuesta?` (in 0) y el retorno de `Evolution API - Enviar Mensaje` (in 0). **out 1 ("loop") → `Evolution - Typing`; out 0 ("done") no está conectado a nada**. Cada vuelta emite 1 parte; `Typing` y `Enviar` leen `$('Loop Mensajes').first().json` = la parte actual. Razón documentada en commit `ceca3d7`: el nodo Evolution procesa solo 1 item por corrida.

**`Evolution - Typing`** (HTTP v4.2, `onError: continueRegularOutput`) — `POST https://evo.raquelrodriguez.com.ar/message/presence`, headers `apikey` (presente, valor omitido) + `Content-Type: application/json`. jsonBody EXACTO:
```
={
  "number": "{{ $('Loop Mensajes').first().json.remoteJid ? $('Loop Mensajes').first().json.remoteJid.replace(/[^0-9]/g, "") : "" }}",
  "state": "composing"
}
```

**`Gate Humano Final`** (Code, corre POR PARTE dentro del loop) — `phone = $('Preparar Mensaje Final').first().json.phone`; `contactId = $('Existe paciente?').first().json.payload[0].id`; GET `https://chat.raquelrodriguez.com.ar/api/v1/accounts/1/contacts/<contactId>/conversations` con header `api_access_token` **hardcodeado inline en el código** (valor omitido; no usa credencial n8n); fail-open (`catch → hasHumano = false`). Si no hay label `humano` → `return items` (pairedItem intacto). Si hay → POST `notify-grupo` `qs: { phone, resumen: 'El bot detecto que ya estas atendiendo este chat y no envio su respuesta automatica (lo tomaste mientras escribia). Tenia listo: «' + output + '»', silencioso: 'true' }` (output = `$('Banlist Validator').first().json.output`, el texto ENTERO pre-split) y `return []` → corta el loop (no se envía esta parte ni las siguientes).

**`Evolution API - Enviar Mensaje`** (HTTP v4.2, sin onError, sin credencial n8n) — `POST https://evo.raquelrodriguez.com.ar/send/text`, headers `apikey` (presente, valor omitido) + `Content-Type: application/json`. jsonBody EXACTO:
```
={
  "number": {{ JSON.stringify($('Loop Mensajes').first().json.remoteJid ? $('Loop Mensajes').first().json.remoteJid.replace(/[^0-9]/g, "") : "") }},
  "text": {{ JSON.stringify($('Loop Mensajes').first().json.message) }}
}
```
→ `number` = `remoteJid` de `Preparar Mensaje Final` (vía Split→Loop) con todo lo no numérico removido; `text` = `message` de la parte actual. Sin campo `instance` (Evolution GO: instancia implícita por apikey). Salida → vuelve a `Loop Mensajes`. **Solo texto**: no existe hoy ningún nodo que use `/send/media`; para el video hay que agregar uno (body `{number, type:"video", url, caption, filename}`, ver decisions 2/9).

**`Banlist Shadow - Prep`** (Code) — arma body `gpt-5-nano` (`max_completion_tokens: 400`, `reasoning_effort: 'minimal'`, `response_format: json_object`) con system prompt de validador (4 reglas duras) y `userPrompt = 'MENSAJE DEL PACIENTE: …\n\nOUTPUT QUE EL BOT VA A ENVIAR:\n…'`; `return []` si output vacío o `[NO_REPLY]`. **Bug de contrato**: lee `banlistResult.output_original || .output`, `banlist_action`, `escalated`, `banlist_reason`, `why` — campos que el Banlist NO produce (produce `banlist_triggered`, `banlist_original_output`, `escalate_to_human`) → `shadow_regex_decision` es SIEMPRE `'ALLOW'` y el output evaluado es el post-reemplazo. **`Banlist Shadow - LLM`** (HTTP `https://api.openai.com/v1/chat/completions`, cred `openAiApi` `OpenAi account`, `neverError: true`, `jsonBody: ={{ $json.shadow_openai_body }}`). **`Banlist Shadow - Log`** (Code, sin salida): parsea `choices[0].message.content` JSON `{decision, razon, reemplazo}` y hace `console.log('[BANLIST_SHADOW]', …)`; **no persiste en ninguna tabla ni afecta el flujo** (rama paralela, dead-end). Costo: 1 llamada nano por respuesta.

**`Pre-filtro Cierre`** (Code, antes del Router; entrada desde `Clear Old Memory`) — sobre `$('Preparar Mensaje Final').first().json.text`; devuelve `{ skip, reason, text, output? }`. `skip:true` (+ `output:'[NO_REPLY]'`) solo para `prompt_injection:*`, `autoresponder_externo:*`, `emoji_only`. Fast-path `skip:false` con `reason` en `afirmacion_negacion_corta`, `saludo_inicial`, **`urgencia`** (lista `urgenciaWords = ['dolor','duele','duela','muela','alambre','bracket','arco','sangrado','hinchazon','hinchada','no aguanto','urgent','infeccion','fiebre','golpe','accidente','rompi','pincha','pinchando','medicacion','que tomo','que tomar','que pastilla','pastilla','pastillas','ibuprofeno','paracetamol','antibio']`, `t.includes(w)` sobre texto normalizado sin acentos), `multimedia_marker`, `tiene_pregunta`, `confirmacion_post_recordatorio`, `default_pass`. **`Es cierre?`** (IF v2): `={{ $json.skip }}` is true → out 0 `Set NO_REPLY` (Set `output = '[NO_REPLY]'`) → `Fallback Output`; out 1 → `Router - Clasificar Intent`. (El nombre es legacy; ya no detecta cierres.)

**Contexto Router/Switch (para saber dónde entra el triaje)**: `Router - Clasificar Intent` (text = `CONTEXTO DE LA CONVERSACION… {{ $('Build Router Context').first().json.ctx }} … MENSAJE ACTUAL… {{ $('Preparar Mensaje Final').first().json.text }}`; su prompt: "**1. urgencia_dolor — MAXIMA PRIORIDAD** Cualquier mencion de: dolor, muela, alambre, brackets, sangrado, hinchazon, pedido de medicacion"). `Parse Intent`: `valid = ['confirmar_post_recordatorio','cancelar_o_reprogramar','urgencia_dolor','agendar_nuevo','consulta_general']`, `intent` = primer valid contenido en `output.toLowerCase()`, default `consulta_general`; propaga `text`. → `Get KB Horarios y Precio` → `Extraer Horarios y Precio` → `Switch sobre Intent` (`={{ $json.intent }}` equals): out 0 `confirmar_post_recordatorio`→Sub-Agent Confirmar; out 1 `cancelar_o_reprogramar`→Execute Sub-WF Cancelar; **out 2 `urgencia_dolor`→Sub-Agent Urgencia**; out 3 `agendar_nuevo`→Sub-Agent Agendar; out 4 `consulta_general`→General; out 5 fallback→General.

**`Sub-Agent Urgencia`** (agent v2.2, `promptType define`, `text: ={{ $('Preparar Mensaje Final').first().json.text }}`; LM `LM Sub-Agent Urgencia` gpt-5-mini reasoningEffort low; tools: solo `escalar_a_secretaria`; memoria: `Postgres Chat Memory`). Prompt (9024 chars) = base común + bloque "**Sub-Agent Urgencia — funcion unica: ESCALAR** … 1. Llamar `escalar_a_secretaria` … 2. Responder al paciente EXACTAMENTE: "Recibimos tu mensaje. Le pasamos a la doctora para que le coordine lo antes posible." PROHIBIDO ABSOLUTO: Dar cualquier consejo médico u operativo (cera, enjuagues, "evita masticar") …" + "UNA SOLA ESCALACION POR TURNO". `escalar_a_secretaria` (toolHttpRequest): `POST =https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo?phone={{ $('Edit Fields - Extraer Datos').first().json.phone }}` + query `resumen` (lo llena el LLM); la descripción dice que además aplica label `humano` en Chatwoot (lo hace el satélite notify-grupo).

---

## 2) `Banlist Validator` — patrones completos y comportamiento

Code v2. Solo procesa **`$input.first().json`** (1 item). `output = item.output`. Excepción de dirección: `pacientePidioDireccion = /\b(d[oó]nde\s*(queda|est[aá]n?|ubicad|esta\s*ubicad)|direcci[oó]n|ubicaci[oó]n|c[oó]mo\s*llegar|en\s*qu[eé]\s*(direcci[oó]n|calle)|qu[eé]\s*direcci[oó]n)\b/i` sobre `$('Preparar Mensaje Final').first().json.text.toLowerCase()`.

Los **20 patrones** (todos `/i`, orden de evaluación, corta en el primero):
1. `/\bven[íi](te)?\b/` — 'venite/veni'
2. `/\bveng(a|an|amos)\b/` — 'venga/vengan'
3. `/\b(los|las|te|le|la|lo|los?\s+espera|las?\s+espera)\s*esperamos\b/` — 'los esperamos'
4. `/\bte\s+esper(amos|amos\s+a|an)\b/` — 'te esperamos'
5. `/\b(la|lo)\s+esperamos\b/` — 'la/lo esperamos'
6. `/\bsalgan?\s+(ya|ahora|para)\b/` — 'salgan ya/para'
7. `/\b(ven[íi]|vengan)\s+ahora\s+mismo\b/` — 'veni/vengan ahora mismo'
8. `/\bahora\s+mismo\b.{0,50}\b(cl[íi]nica|consultorio|aurea|áurea)\b/` — 'ahora mismo + clinica'
9. `/\blo\s+antes\s+posible\b.{0,50}\b(cl[íi]nica|consultorio|aurea|áurea|venir)\b/` — 'lo antes posible + clinica'
10. `/\bguard(á|a|alo|enlo|en|amos|en\s+la)\s+/` — 'guarda/guarden (instruccion)'
11. `/\btraig(a|an|alo|anlo|amos|an\s+(el|la|los|las))\b/` — 'traigan (instruccion operativa)'
12. `/\btra(é|e)\s+(el|la|los|las|tu)/` — 'trae (instruccion)'
13. `/\btom(á|a|alo|en|amos)\s+(\d|un|una|el|la|los|las|cada)/` — 'toma medicacion/dosis'
14. `/\bsac(á|a|alo|en|amos)\s+(la|el)/` — 'saca (instruccion)'
15. `/\baplic(á|a|ate|en|ense)\b/` — 'aplica (instruccion medica)'
16. `/\benjuag(á|a|ate|en|ense)\b/` — 'enjuaga (instruccion medica)'
17. `/\bno\s+te\s+preocup(es|és)\b/` — 'no te preocupes (minimizar sintoma)'
18. `/\bno\s+es\s+(nada\s+)?grave\b/` — 'no es grave (diagnostico)'
19. `/\b(qu[ée]\s+macana|qu[ée]\s+embromado|qu[ée]\s+l[áa]stima)\b/` — 'opinion emocional'
20. `/\bbalcarce\s*(n[º°]?\s*)?37\b/` con `skip_if_paciente_pidio_direccion: true` — 'direccion Balcarce 37'

(El comentario del código dice "22 patrones"; hay 20.)

**Qué hace al matchear**: NO escala, NO llama a notify-grupo, NO aplica label. **REEMPLAZA** el output por `CANNED = 'Recibimos tu mensaje. Estamos derivando tu caso a la Dra. Raquel para que te responda personalmente por este chat. Disculpa la demora.'` y devuelve `{ ...item, output: CANNED, banlist_triggered: <why>, banlist_original_output: <original>, escalate_to_human: true }` + `console.log('[BANLIST TRIGGERED]', …)`. Sin match: `{ ...item, banlist_triggered: null, escalate_to_human: false }`. **Ningún nodo aguas abajo lee `escalate_to_human` ni `banlist_triggered`** (verificado por grep sobre los 125 nodos: solo aparecen en el propio Banlist) → el flag es decorativo; la "escalación" real la hizo (o no) el sub-agent con su tool antes. Además el texto baneado YA quedó escrito en `n8n_chat_histories` por el agente (el Banlist no toca la memoria).

**Evaluación de los canned de la doctora** (ejecutado con Node sobre el array `BANLIST` extraído textualmente del nodo, con `pacientePidioDireccion=false`):
- `"colocarte una cera de ortodoncia en la punta del alambre"` → **PASA** (ningún patrón: "colocar/colocarte", "cera", "alambre" no están en la lista).
- `"Intentar colocar el alambre nuevamente al tubo o bracket de donde se soltó, con ayuda de una pinza de alicate o de cejas"` → **PASA** ("intentar", "colocar", "pinza", "soltó" no están).
- Variantes probadas que también PASAN: "Puede colocarse cera…", "Colocá cera…", "Coloque cera", "Intente colocar el alambre… con ayuda de una pinza de cejas", "Con ayuda de una pinza… tome el alambre y colóquelo en el tubo", "Tome un ibuprofeno cada 8 horas" (usted), "Saque el alambre", "Guarde la pieza", "Guardar el bracket", "Enjuague con agua", "Puede venir a la clinica", "Recibimos tu mensaje. Le pasamos a la doctora para que le coordine lo antes posible." (canned actual de Urgencia), "Si no mejora, escríbanos y le pasamos el caso a la Dra. Raquel para que lo vea lo antes posible." (no hay clinica/consultorio/venir a ≤50 chars).
- Variantes que BLOQUEAN: "Guarda la pieza"/"Guardá la pieza" (#10), "Toma un ibuprofeno"/"Tomá un…" (#13), "Saca/Sacá el alambre" (#14), "Aplica cera" (#15), "Enjuaga con agua" (#16), "venga/vengan/venite" (#1/#2), "Le/Lo/La/Te esperamos" (#3), "ahora mismo a la clinica" (#8), "…lo antes posible en el consultorio" (#9), "No te preocupes" (#17), "No es grave" (#18).
- **Bug de acentos confirmado (mismo que se arregló en `triaje/gate_red_flags.js`)**: los regex usan `\b` sin flag `u`, y "á/é" no cuentan como letra → `\b` después del acento no cierra. Resultado: **"Aplicá cera", "Enjuagá con agua", "Tráigalo" PASAN** mientras "Aplica cera", "Enjuaga…", "Traigalo" bloquean. Las formas de usted ("Aplique", "Apliquese", "Guarde", "Tome", "Saque", "Coloque") NO están cubiertas en absoluto. Conclusión práctica: el Banlist es voseo-céntrico y NO bloquea instrucciones formales ni las de "colocar cera / pinza"; para el caption canned del video no molesta, pero tampoco protege — la protección tiene que ser que el caption sea canned (nunca LLM), como ya dice el diseño (Capa 5).

---

## 3) Memoria (`n8n_chat_histories`)

**Tabla** (`scripts/rebuild_v3_schema.sql` §1): `n8n_chat_histories(id BIGSERIAL PK, session_id VARCHAR(255) NOT NULL, message JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`; índices `(session_id, id DESC)` y `(session_id, created_at DESC)`. `session_id` = teléfono `549…` sin `@s.whatsapp.net`.

**`Postgres Chat Memory`** (`@n8n/n8n-nodes-langchain.memoryPostgresChat` v1.3) — cred `postgres` id **`TpYhZX4UT61xAKSV`** "Postgres Supabase Nexora v3"; `sessionIdType: customKey`; `sessionKey: ={{ $('Preparar Mensaje Final').first().json.phone }}`; `contextWindowLength: 10`; sin `tableName` → default `n8n_chat_histories`. Conectada por `ai_memory` a los 5 sub-agents (Confirmar, Cancelar, Agendar, Urgencia, General). **NO** está conectada al Router ni al Formatting Agent. Lo que escribe el agente: fila `human` = su `text` de entrada (`Preparar Mensaje Final.text`), fila `ai` = el `output` CRUDO del sub-agent (antes de Sidecar/Gate Pago/Banlist/Formatting/Split). Consecuencia: si un nodo determinístico aguas abajo reemplaza o anexa texto, la memoria y lo enviado divergen (hoy pasa con Banlist, Gate Pago y Sidecar; el panel lo tapa porque el Logger copia el crudo y el chat muestra "texto CRUDO del agente").

**Patrón para escribir un mensaje AI a mano** (rama `Es fromMe?` out 0, `={{ $json.fromMe }}` boolean true):
`Build fromMe AI memory` (Code):
```js
const text = ($json.text || '').trim();
const phone = $json.phone;
if (!phone) return [];
const content = text || '[mensaje multimedia enviado por la doctora/secretaria - sin texto adjunto]';
const TAG = '[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria desde el WhatsApp del consultorio. NO es output tuyo, es un humano atendiendo este chat. Mantente en silencio y NO respondas en este chat hasta que un admin diga /bot on.]: ';
const session_id = phone;
const message = {
  type: 'ai',
  content: TAG + content,
  additional_kwargs: { source: 'wa_outbound', from_iri_or_dra: true, was_multimedia: !text },
  response_metadata: {},
  tool_calls: [],
  invalid_tool_calls: []
};
return [{ json: { session_id, message: JSON.stringify(message) } }];
```
`Postgres - Save fromMe` (Postgres v2.5 executeQuery, misma cred `TpYhZX4UT61xAKSV`):
`INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)` con `queryReplacement: ={{ $json.session_id }}, ={{ $json.message }}` → luego `CW Search Contact → CW Extract Conv → CW Get Conversations → CW Pick Conv → CW Set Label humano`.
→ **Formato JSON de `message` confirmado**: `{ type:'ai'|'human', content, additional_kwargs:{ source, … }, response_metadata:{}, tool_calls:[], invalid_tool_calls:[] }`. `created_at` lo pone el DEFAULT. Para el triaje: mismo INSERT con `type:'ai'`, `content:<caption canned>`, `additional_kwargs:{ source:'triaje_video', tipo, opcion }` (cualquier `source` que NO sea `wa_outbound|human_takeover|reminder_note`, ver abajo).

**Otros lectores/escritores de la memoria que hay que respetar**:
- `Build Router Context` (Postgres, `onError: continueRegularOutput`, corre en cada mensaje): `SELECT COALESCE(string_agg(CASE message->>'type' WHEN 'human' THEN 'PACIENTE: ' WHEN 'ai' THEN 'BOT: ' ELSE 'SYSTEM: ' END || (message->>'content'), E'\n---\n' ORDER BY id ASC), '(sin mensajes previos)') AS ctx FROM (SELECT id, message FROM n8n_chat_histories WHERE session_id = '{{ $json.phone }}' AND (message->>'content') NOT IN ('agendar_nuevo','consulta_general','cancelar_o_reprogramar','confirmar_post_recordatorio','urgencia_dolor') AND (message->>'content') NOT LIKE '[CONTEXTO%' AND (message->>'content') != '[NO_REPLY]' ORDER BY id DESC LIMIT 6) recent` → un `ai` insertado a mano aparece como `BOT: <content>` en el contexto del Router al turno siguiente (útil para "no funcionó / sigue mal" → re-escalar).
- `Check Session Age` (Postgres, `alwaysOutputData: true`): `SELECT id, session_id, created_at FROM n8n_chat_histories WHERE session_id = '{{ $("Preparar Mensaje Final").first().json.phone }}' ORDER BY id DESC LIMIT 1` (interpolación directa, no parametrizada). `Handle Stale Session` (Code): `hasHistory = result.id != null && !result.error && !result.message`; `isStale = ((now - created_at) / 86400000) > 7` → **sesión vieja = último registro de la sesión (cualquier tipo/source) con más de 7 días**; devuelve `{ ...Preparar Mensaje Final, has_history, is_stale_session, session_phone }`. `Clear Old Memory` (Postgres, `alwaysOutputData: true`): `DELETE FROM n8n_chat_histories WHERE session_id = $1 AND $2::boolean = true AND COALESCE(message::jsonb->'additional_kwargs'->>'source', '') NOT IN ('wa_outbound', 'human_takeover', 'reminder_note') RETURNING id` con `={{ $json.session_phone }}, ={{ $json.is_stale_session }}` → borra TODA la memoria de esa sesión (salvo los 3 sources protegidos) y sigue a `Pre-filtro Cierre`. Un `source:'triaje_video'` se borraría con la sesión vieja (correcto: no queremos que el bot "recuerde" un video de hace 2 meses; si se quisiera conservar, agregarlo al NOT IN).
- `PG - Delete NO_REPLY` (ver 1.2) borra solo el último `ai` con content `[NO_REPLY]`.
- Sources conocidos en producción: `wa_outbound` (staff desde el WhatsApp del consultorio; único emisor: `Build fromMe AI memory`), `human_takeover` (satélite Human Takeover), `reminder_note` (Recordatorios; el Logger lo mapea a `rol=system/fuente=bot_reminder`).

---

## 4) Logger → `conversaciones` → panel

**Logger `Logger Conversaciones (Supabase)` (`xsXeHp7WLXnFQc3o`)**, activo, cron 5 min (nodo se llama `Cron 30s` pero `rule.interval[0] = {field:'minutes', minutesInterval:5}`). Cadena: `Cron 30s → Get last_synced → PG - SELECT nuevos → Parse mensajes → HTTP - Upsert Paciente → HTTP - Insert Conversacion → Update last_synced` (los 3 nodos duplicados por id son copias inertes sin conexiones; el nodo `IF - Es Mensaje Entrante (rol=user)` del snapshot POST fue REVERTIDO — no está en el vivo, confirmado por GET: 10 nodos, lista sin el IF).
- `Get last_synced`: lee `$getWorkflowStaticData('global').last_synced_chat_id` (vestigial, vale 0 en vivo; NO se usa para filtrar).
- `PG - SELECT nuevos` (cred `TpYhZX4UT61xAKSV`): `SELECT id, session_id, message::text AS message, created_at FROM n8n_chat_histories WHERE id > (SELECT COALESCE(MAX(chat_history_id), 0) FROM conversaciones) ORDER BY id ASC LIMIT 200` → **el cursor real es `MAX(chat_history_id)` de `conversaciones`**.
- `Parse mensajes` (Code): parsea `message`; `type = msg.type || msg.kwargs?.type`, `content`, `source = additional_kwargs.source.toLowerCase()`. **Descarta**: content vacío, `[NO_REPLY]`, content igual a un label de intent (`consulta_general, agendar_nuevo, consulta_confirmacion, consulta_cancelacion, urgencia, cierre, autoresponder_externo, multimedia, comando_admin, humano_takeover`), y `trimmed.length < 3`. Mapeo: `human` + source `wa_outbound|human_takeover` → `rol='human', fuente='whatsapp_secretaria'`; `human` otro → `rol='user', fuente='whatsapp'`; **`ai` + source `reminder_note` → `rol='system', fuente='bot_reminder'`; `ai` cualquier otro source (incluido ninguno, o `wa_outbound`, o uno nuevo) → `rol='assistant', fuente='bot'`**; otro type → `system/unknown`. Emite `{ chat_history_id: id, telefono, rol, mensaje, fuente, created_at, metadata: { source, pushName, type, chat_history_id }, pushName }`.
- `HTTP - Upsert Paciente`: `POST https://eoizfjsyejixjzwgzwkt.supabase.co/rest/v1/pacientes?on_conflict=telefono`, `Prefer: resolution=merge-duplicates,return=representation`, body `{ telefono, nombre: pushName || 'Paciente WhatsApp' }` (cred `supabaseApi` `Supabase account v3` id `H1PRagttKC5kxSzs`). Corre para TODOS los items (también los `ai`).
- `HTTP - Insert Conversacion`: `POST …/rest/v1/conversaciones?on_conflict=chat_history_id`, `Prefer: resolution=ignore-duplicates,return=minimal`, body `{ chat_history_id: {{ $('Parse mensajes').item.json.chat_history_id }}, paciente_id: "{{ $json.id || ($json[0] && $json[0].id) }}", telefono, rol, mensaje: {{ JSON.stringify(...mensaje) }}, fuente, timestamp: "{{ ...created_at }}", metadata: {{ JSON.stringify(...metadata) }} }`.
- Esquema `conversaciones(id, paciente_id, telefono, rol, mensaje, fuente, "timestamp" ← created_at de nch, metadata JSONB {source,pushName,type,chat_history_id})` + columna `chat_history_id` (UNIQUE, cursor).

**Panel (`nexora-whatsapp-agent`)** — lee DIRECTO el Supabase v3, dos fuentes fusionadas:
- `lib/chat-data.ts::getChatData(telefono)`: `conversaciones` (`.eq('telefono')`, `.neq('rol','system')`, desc, limit 200) + **tail EN VIVO de `n8n_chat_histories`** (`.eq('session_id', telefono)`, order id asc, limit 60); dedup por `created_at` en ms contra `timestamp` de conversaciones; filtra `esMensajeInterno(content)` = vacío, `[NO_REPLY]`, o `/^\[\s*nota interna/i`; solo `type` `human`|`ai`; mapea **`ai` → `{ rol:'assistant', fuente:'bot', metadata:null, id: 2_000_000_000 + row.id }`**. Polling del chat cada 1.5 s (pestaña visible).
- `lib/conversaciones-data.ts::getConversacionesList`: mismo merge con los últimos 200 de `n8n_chat_histories` (todas las sesiones); una conversación se lista solo si el teléfono está en `conversaciones` o tiene un `human` en el tail.
- `components/conversaciones/chat-view.tsx` (líneas 689-747): `esStaffManual = metadata?.source === 'wa_outbound' || mensaje.startsWith('[ATENCION HUMANA')`; `outgoing = rol !== 'user'`; `isHuman = rol === 'human' || esStaffManual`; `isBot = outgoing && !isHuman` → burbuja verde etiqueta **"Asiri"**; humano → azul **"Dra. Raquel"**; `isReminder = fuente === 'bot_reminder'`. `detectMedia`: renderiza chip de video solo si el mensaje ENTERO es un marcador bracketeado `[video]`/`[vídeo]`/`[un video]` o `metadata.type` matchea `/video/` (el Logger pone `metadata.type='ai'`, no sirve); una URL `.mp4` en el texto NO se detecta (solo `IMG_RE`/`AUD_RE`).

**Respuesta directa**: **SÍ** — un `INSERT INTO n8n_chat_histories(session_id, message)` con `message = {type:'ai', content:'<caption>', additional_kwargs:{source:'triaje_video',…}, response_metadata:{}, tool_calls:[], invalid_tool_calls:[]}` aparece en el panel como mensaje del bot ("Asiri", verde): (a) al instante vía el tail en vivo (≤1.5 s, mientras esté entre las últimas 60 filas de esa sesión), y (b) en ≤5 min el Logger lo copia a `conversaciones` como `rol='assistant', fuente='bot', metadata.source='triaje_video'`. Condiciones: `content` ≥ 3 chars, no vacío, no `[NO_REPLY]`, no empezar con `[NOTA INTERNA` ni `[ATENCION HUMANA`, no ser exactamente un label de intent, y `source` ≠ `reminder_note` (sería `system` y el panel lo excluye con `.neq('rol','system')`) ni `wa_outbound`/`human_takeover` (se mostraría como "Dra. Raquel"). Para que se vea como VIDEO en el chat habría que insertar una fila aparte cuyo content sea exactamente `[video]` (chip "Video" sin URL) o extender `detectMedia`/`metaUrl` en el panel; con el caption en la misma fila se ve como texto.

## KEY FACTS
- El snapshot local v6_LIVE.json (versionId 99e1e7aa-…, updatedAt 2026-09-04T13:22:48Z, 125 nodos) coincide EXACTAMENTE con el v6 vivo (verificado por GET read-only a la API).
- Orden real del tail: Fallback Output → Canned Sidecar → Gate Pago Tratamiento → Banlist Validator → (Re-check Humano → Hay humano ahora? → Humano aparecio?) → Necesita Formatting? → [Formatting Agent - WhatsApp] → Split en Mensajes → Gate Error Tecnico → Tiene respuesta? → Loop Mensajes (out 1) → Evolution - Typing → Gate Humano Final → Evolution API - Enviar Mensaje → Loop Mensajes. Banlist Shadow es una rama paralela dead-end (solo console.log).
- El campo de texto se llama `output` hasta Split en Mensajes y `message` después; el item post-split es {message, remoteJid, phone, partIndex, totalParts}; phone/remoteJid siempre salen de $('Preparar Mensaje Final').first().json.
- Evolution API - Enviar Mensaje: POST https://evo.raquelrodriguez.com.ar/send/text con jsonBody {"number": JSON.stringify(remoteJid sin no-dígitos), "text": JSON.stringify($('Loop Mensajes').first().json.message)}, header apikey inline (valor omitido), sin `instance`, sin onError. Evolution - Typing: POST …/message/presence {number, state:'composing'}, onError continueRegularOutput. NO existe ningún nodo /send/media en el v6.
- Split en Mensajes parte por el literal '---' (output.split('---')), trim + filtra vacíos; guard determinístico: si $('Banlist Validator').first().json.output contiene CBU y el formateado no, usa el original. Solo procesa $input.first().
- Loop Mensajes es splitInBatches v3 batchSize 1: out 1 (loop) → Typing; out 0 (done) sin conexión. Gate Humano Final y Gate Error Tecnico corren POR PARTE.
- Necesita Formatting?: cualquier output > 80 chars que no contenga [NO_REPLY] pasa por gpt-5-mini (Formatting Agent) — un caption canned largo sería re-escrito por un LLM si va por el camino de texto.
- Banlist Validator: 20 regex (no 22), case-insensitive, corta al primer match; al matchear REEMPLAZA output por canned de derivación y setea escalate_to_human/banlist_triggered — flags que NINGÚN nodo aguas abajo lee; no escala ni avisa al grupo; no toca la memoria (el texto baneado ya quedó en n8n_chat_histories).
- Los dos canned de la doctora PASAN el Banlist sin match (probado con Node sobre el array extraído del nodo): 'colocarte una cera de ortodoncia en la punta del alambre' y 'Intentar colocar el alambre nuevamente al tubo o bracket… con ayuda de una pinza de alicate o de cejas'. También pasan 'Puede colocarse cera…', 'Coloque cera', 'Intente colocar…', 'Tome un ibuprofeno', 'Guarde la pieza', 'Saque el alambre', 'Enjuague…' (formas de usted no cubiertas).
- Bug de acentos en el Banlist (mismo que se corrigió en triaje/gate_red_flags.js): \b sin flag u → 'Aplicá cera', 'Enjuagá', 'Tráigalo' PASAN mientras 'Aplica cera', 'Enjuaga', 'Traigalo' bloquean. Bloquean: venga/vengan/venite, Le/Lo/La/Te esperamos, 'ahora mismo'+clinica, 'lo antes posible'+clinica/consultorio/venir (≤50 chars), Guarda/Guardá, Toma/Tomá + dosis, Saca/Sacá, No te preocupes, No es grave.
- Canned Sidecar y Gate Pago Tratamiento hacen passthrough explícito cuando $('Parse Intent').first().json.intent === 'urgencia_dolor'.
- Postgres Chat Memory: memoryPostgresChat v1.3, cred postgres id TpYhZX4UT61xAKSV ('Postgres Supabase Nexora v3'), sessionKey ={{ $('Preparar Mensaje Final').first().json.phone }}, contextWindowLength 10, tabla default n8n_chat_histories; conectada solo a los 5 sub-agents (no al Router ni al Formatting Agent). Escribe el output CRUDO del sub-agent (pre Sidecar/Banlist/Formatting).
- Formato de message confirmado (Build fromMe AI memory): {type:'ai', content, additional_kwargs:{source:'wa_outbound', from_iri_or_dra:true, was_multimedia}, response_metadata:{}, tool_calls:[], invalid_tool_calls:[]}; insert: INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb) con queryReplacement ={{ $json.session_id }}, ={{ $json.message }}.
- Sesión vieja = última fila de la sesión (cualquier tipo) con más de 7 días (Handle Stale Session); Clear Old Memory borra toda la sesión salvo sources wa_outbound/human_takeover/reminder_note. PG - Delete NO_REPLY borra solo el último ai '[NO_REPLY]'.
- Build Router Context muestra al Router los últimos 6 mensajes como 'PACIENTE: / BOT: / SYSTEM:' (excluye labels de intent, '[CONTEXTO%' y '[NO_REPLY]') → un ai insertado a mano aparece como 'BOT: …' en el turno siguiente.
- Logger xsXeHp7WLXnFQc3o (vivo: activo, 10 nodos con 3 duplicados inertes, cron 5 min, IF 'rol=user' revertido): cursor = MAX(chat_history_id) de conversaciones; Parse mensajes mapea type 'ai' sin source 'reminder_note' → rol 'assistant', fuente 'bot', metadata {source,pushName,type,chat_history_id}; descarta vacío/[NO_REPLY]/labels de intent/<3 chars.
- Panel: chat-data.ts y conversaciones-data.ts leen conversaciones (rol != system) + tail EN VIVO de n8n_chat_histories (60 por sesión / 200 globales), type 'ai' → rol 'assistant', fuente 'bot'; chat-view.tsx etiqueta 'Asiri' (verde) si rol != user y no es humano (rol 'human' | metadata.source==='wa_outbound' | mensaje empieza con '[ATENCION HUMANA'); esMensajeInterno filtra vacío, [NO_REPLY] y /^\[\s*nota interna/i.
- SÍ: un INSERT manual en n8n_chat_histories con type 'ai' (content ≥3 chars, sin prefijos internos, source ≠ reminder_note/wa_outbound/human_takeover) aparece en el panel como mensaje de Asiri al instante (tail en vivo, polling 1.5 s) y en ≤5 min vía Logger en conversaciones como rol assistant / fuente bot.
- Para que el panel muestre un chip de VIDEO, el mensaje entero debe ser exactamente '[video]'/'[vídeo]'/'[un video]' o metadata.type matchear /video/ (el Logger escribe metadata.type='ai'); una URL .mp4 en el texto no se detecta (solo imágenes/audio).

## RISKS
- Divergencia memoria vs. enviado: el sub-agent escribe su output CRUDO en n8n_chat_histories al terminar; si el triaje reemplaza la respuesta (video+caption en vez del canned de Urgencia), la memoria y el panel dirán 'Recibimos tu mensaje. Le pasamos a la doctora…' mientras el paciente recibió el video. Hay que borrar la última fila ai del sub-agent (patrón PG - Delete NO_REPLY con content = canned de Urgencia) e insertar el caption a mano (patrón Postgres - Save fromMe), o bien hacer el triaje ANTES del Sub-Agent Urgencia para que ese nodo nunca escriba.
- Sub-Agent Urgencia SIEMPRE llama escalar_a_secretaria (notify-grupo → aviso al grupo + label 'humano' en Chatwoot) antes de responder. Si el triaje se inserta DESPUÉS del sub-agent, el grupo ya recibió la escalación y el label humano ya silencia al bot para el turno siguiente (Re-check Humano/Gate Humano Final/Bot Activo?) — el 'no funcionó → reescalar' nunca llegaría al bot. El punto de inserción lógico es entre Switch sobre Intent (out 2) y Sub-Agent Urgencia, o reemplazar la entrada al sub-agent.
- No existe nodo /send/media en el v6: el tail actual (Split → Loop → Typing → Gate Humano Final → /send/text) es solo texto y Loop Mensajes procesa 1 item por vuelta. Un video requiere un nodo HTTP nuevo (POST /send/media {number, type:'video', url, caption, filename}) y decidir si pasa por Gate Humano Final (recomendado replicar el chequeo de label humano antes de enviar).
- Necesita Formatting? manda a gpt-5-mini todo output > 80 chars: si el caption canned viaja por el camino de texto normal, un LLM lo reescribe (viola Capa 5 'caption canned, no generado por LLM'). Hay que bypassear el Formatting Agent (o mandar el caption dentro de /send/media y no por /send/text).
- Split en Mensajes parte por el literal '---': si el caption contiene '---' se fragmenta en varios envíos.
- Banlist no cubre formas de usted (Aplique/Guarde/Tome/Saque/Coloque) ni 'colocar cera'/'pinza', y tiene el bug de \b + acentos (Aplicá/Enjuagá/Tráigalo pasan). No protege del contenido del caption; tampoco lo bloquea. La seguridad tiene que venir de que el caption sea canned fijo. Si se agregan patrones nuevos, replicar el fix de límites Unicode de triaje/gate_red_flags.js.
- Banlist Validator, Hay humano ahora?, Split en Mensajes y Gate Humano Final usan $input.first()/$('Banlist Validator').first(): el tail asume UN solo item entre Fallback Output y Split. Si el triaje emite 2 items (texto + video) por el mismo camino, el segundo se pierde silenciosamente.
- Canned Sidecar y Gate Pago Tratamiento dependen de $('Parse Intent').first().json.intent === 'urgencia_dolor' para el passthrough; si el triaje corre fuera del intent urgencia_dolor (p.ej. sombra desde General) o en un camino donde Parse Intent no corrió, el Sidecar podría anexar el alias a un caption de urgencia ('cuanto…?' en el mensaje del paciente) y Gate Pago podría reemplazarlo si el paciente menciona 'bracket' + 'pagar' en la misma oración.
- Re-check Humano no tiene onError y depende de $('Existe paciente?').first().json.payload[0].id: si Chatwoot cae o el contacto no existe, la ejecución falla y el paciente no recibe nada (ni video ni escalación). Gate Humano Final es fail-open pero tiene el token de Chatwoot hardcodeado en el código (deuda de higiene, no tocar sin backup).
- Clear Old Memory borra cualquier source no protegido cuando la sesión tiene >7 días: una fila 'triaje_video' se pierde (aceptable), pero si se quiere que el bot recuerde 'ya mandé la opción 1' entre sesiones hay que agregar el source al NOT IN o persistirlo en triaje_urgencias_log (mejor).
- El Logger crea ficha en pacientes para CUALQUIER fila (también ai) — un INSERT manual con session_id nuevo (p.ej. tests con teléfono sintético) crea 'Paciente WhatsApp' falso; usar solo teléfonos reales o limpiar después. Y descarta contents < 3 chars o iguales a labels de intent.
- Banlist Shadow lee campos que el Banlist no produce (output_original/banlist_action/escalated) → su comparación regex-vs-LLM está sesgada (siempre ALLOW y evalúa el output post-reemplazo); no usarlo como evidencia de que el banlist 'está de acuerdo' con el LLM. Además agrega 1 llamada gpt-5-nano por respuesta, incluido el caption del video si pasa por el Banlist.
- Es primer mensaje? / Delay Humano son código muerto (sin entradas): no confundirlos como punto de inserción; el envío real arranca en Loop Mensajes out 1.

## OPEN QUESTIONS
- ¿El triaje se inserta ANTES de Sub-Agent Urgencia (entre Switch sobre Intent out 2 y el agente, evitando que escale y escriba memoria) o se reemplaza el sub-agent por un Code determinístico + video? La primera opción respeta 'Capa 4: sin match claro → escalar' delegando al sub-agent actual.
- ¿Cómo se manda el video: nodo /send/media nuevo colgado de Gate Humano Final (dentro del loop, con el caption como `caption` del media) o un mini-tail aparte (re-check humano propio → /send/media → INSERT en memoria)? Con la primera hay que resolver que Split/Loop asumen texto y 1 item.
- ¿Qué content exacto se persiste en n8n_chat_histories para el turno de video: solo el caption, o caption + marcador '[video]' en una fila separada para que el panel muestre el chip? El detectMedia del panel solo reconoce el marcador bracketeado si es el mensaje ENTERO.
- ¿Se agrega el source del triaje (p.ej. 'triaje_video') al NOT IN de Clear Old Memory, o se acepta que se borre a los 7 días y la 'memoria' del triaje vive en triaje_urgencias_log?
- Los canned de la doctora son texto de video (voz), no del caption: ¿el caption canned va a reutilizar esas frases ('colocar cera…', 'con ayuda de una pinza…') o solo 'Le envío un video… si no mejora, escríbanos'? Ambas pasan el Banlist hoy, pero el prompt vivo de Urgencia las tiene como PROHIBIDO ABSOLUTO — si el caption lo emite un nodo determinístico no aplica, si lo emite el LLM sí.
- ¿Conviene corregir el bug de \b+acentos del Banlist y sumar formas de usted en el mismo PR del triaje, o dejarlo como P2 aparte para no mezclar riesgos en el diff del v6?