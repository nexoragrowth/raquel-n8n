# Triaje de urgencias con video — Fase 2 piloto (alambre_pincha) vía Router + memoria, bifurcación única en Switch sobre Intent[2]

Se insertan 15 nodos con prefijo "Triaje: " EXCLUSIVAMENTE entre `Switch sobre Intent` (output 2, intent `urgencia_dolor`) y `Sub-Agent Urgencia`; nada antes del Router ni en la cadena de salida se toca. Primer mensaje: Redis GET estado → SELECT de config (`triaje_videos` + `triaje_config`) → Code con `triaje/gate_red_flags.js` embebido (gate determinístico + reconstrucción de estado desde Redis o desde el ctx del Router) → IF → clasificador gpt-5-mini (httpRequest, JSON) → Code Decidir → INSERT `triaje_urgencias_log` → Switch de acción: `escalar` (→ Sub-Agent Urgencia EXACTO como hoy), `video` (POST /send/media + texto de salida canned), `pregunta` (texto canned), `cerrar` (texto canned), `escalar_con_texto` (texto canned + Sub-Agent Urgencia). Todo envío exitoso persiste el turno del paciente + los mensajes AI con prefijo `[TRIAJE VIDEO tipo opcion N]` / `[TRIAJE PREGUNTA tipo]` / `[TRIAJE INFO]` / `[TRIAJE CIERRE]` / `[TRIAJE ESCALADO]` en `n8n_chat_histories` (mismo INSERT/shape que `Postgres - Save fromMe`) y guarda `triaje:{phone}` en Redis con TTL. El seguimiento se resuelve haciendo que el Router clasifique como `urgencia_dolor` cualquier mensaje mientras el último BOT del ctx empiece con `[TRIAJE VIDEO|PREGUNTA|INFO` (bloque nuevo + 4 few-shots en su prompt); dentro de la rama, el estado (Redis, confirmado/reconstruido desde la memoria) decide determinísticamente: red flag → escalar; regex "no sirvió" → Opción 2 o escalar; regex cierre → cerrar y limpiar; otra cosa → escalar (fail-closed). El texto que ve el paciente en la rama nueva es 100% tabla; el LLM solo clasifica. Cualquier error (config vacía, LLM caído/JSON inválido, Evolution GO sin `data.Info.ID`/`VideoMessage`, Postgres/Redis) cae a Sub-Agent Urgencia. Config editable sin n8n: `triaje_videos` (solo alambre_pincha activo, 2 opciones) + `triaje_config` (kill-switch, allow-list de teléfonos piloto, TTLs). Incluye DDL+seeds, script `apply_triaje_fase2_piloto.py` con GET fresco/backup PRE-POST/diff/asserts de webhookId, plan E2E, guion de demo desde 5491161461034 con procedimiento de limpieza, y rollback en 2 niveles (UPDATE triaje_config SET activo=false sin PUT; o PUT del backup PRE).

# Fase 2 — Triaje de urgencias con video (piloto `alambre_pincha`) — diseño a nivel de nodos n8n

Ángulo: **continuidad vía Router + memoria**. La bifurcación vive solo dentro del camino de urgencia; el seguimiento post-video llega a la rama porque (1) los mensajes AI del triaje quedan en `n8n_chat_histories` con prefijo `[TRIAJE …]`, (2) el prompt del Router recibe una regla explícita de continuación de triaje que lee ese prefijo en `BOT:` del ctx, y (3) el estado Redis `triaje:{phone}` confirma (y la memoria reconstruye si Redis expiró). Nada antes del Router ni en la cadena de salida cambia.

Verificado hoy contra `workflows/current/v6_LIVE.json` **y** por GET read-only a la API (mismo `updatedAt 2026-09-04T13:22:48.347Z`, 125 nodos): `connections['Switch sobre Intent']['main'][2] == [{node:'Sub-Agent Urgencia', type:'main', index:0}]`; `Sub-Agent Urgencia` tiene UN solo input main (ese) + `ai_languageModel` (`LM Sub-Agent Urgencia`), `ai_memory` (`Postgres Chat Memory`), `ai_tool` (`escalar_a_secretaria`); su salida main[0] → `Fallback Output`. `Evolution API - Enviar Mensaje` (httpRequest 4.2) tiene headers `apikey` (valor omitido) + `Content-Type`, sin `options`, `credentials: {}`. Respuesta real de `/send/text` (exec 270375): `{"data":{"Info":{"ID":"3EB0…","Type":"ExtendedTextMessage",…}}}`; `/send/media` probado 2/9: `data.Info.Type === "VideoMessage"` + `data.Info.ID`. `Postgres - Save fromMe`: `INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)` con `queryReplacement "={{ $json.session_id }}, ={{ $json.message }}"`, cred `{postgres:{id:'TpYhZX4UT61xAKSV', name:'Postgres Supabase Nexora v3'}}`. Redis cred `{redis:{id:'kdtSKwGbN1xAZeUh', name:'Redis account'}}`, typeVersion 1. OpenAI cred `{openAiApi:{id:'nYujqfon7GGDnJUO', name:'OpenAi account'}}`. Anclas de prompt: Router `Si la memoria esta vacia o el ultimo AI fue un saludo generico, clasificar segun el mensaje del paciente directamente.` (count 1), `- \`urgencia_dolor\` -> Sub-Agent Urgencia\n  Hace: UNICAMENTE escalar. Prohibido dar consejos, recomendar medicacion, diagnosticar.` (count 1); Urgencia `PASOS OBLIGATORIOS:\n1. Llamar \`escalar_a_secretaria\`` (count 1). Ambos systemMessage empiezan con `=` (expresión) — se conserva.

---

## 1. Dónde se bifurca (único punto)

- **Se corta** la conexión `Switch sobre Intent` main **[2]** (`outputKey 'urgencia'`, regla `={{ $json.intent }} equals 'urgencia_dolor'`) → `Sub-Agent Urgencia`.
- **Nueva** `Switch sobre Intent` main[2] → `Triaje: Redis GET estado` (index 0).
- `Sub-Agent Urgencia` pasa a recibir 4 entradas main (todas index 0): `Triaje: Switch Accion`[0], `Triaje: Video OK?`[1], `Triaje: Texto OK?`[1], `Triaje: Sigue a escalar?`[0]. Su salida main[0] → `Fallback Output` queda intacta, igual que sus conexiones ai_*.
- Item que llega a la rama (`$json`): `{output, intent:'urgencia_dolor', text, horarios, precio_consulta}`. Los nodos nuevos NO dependen de `$json`: leen `$('Preparar Mensaje Final').first().json.{phone,remoteJid,text,name}`, `$('Build Router Context').first().json.ctx`, `$('Edit Fields - Extraer Datos').first().json.pushName`, `$('Parse Intent').first().json.intent` — todos en el camino CONECTADO real aguas arriba (lección "No path back"), siempre con `.first()`.
- Los otros 5 outputs del Switch, `Pre-filtro Cierre`, `Bot Activo?`, kill-switch, rate limit, buffer, `Fallback Output → … → Evolution API - Enviar Mensaje`: **sin cambios**. `Canned Sidecar` y `Gate Pago Tratamiento` siguen haciendo passthrough porque `$('Parse Intent').first().json.intent === 'urgencia_dolor'` no cambia (no se crea ningún intent nuevo).

---

## 2. Nodos nuevos (15, prefijo `Triaje: `). Posiciones en una fila y=800 debajo de `Sub-Agent Urgencia` ([12352,544]); ids = slugs (`triaje-redis-get`, …), como `get-kb-horarios-precio`.

### 2.1 `Triaje: Redis GET estado` — `n8n-nodes-base.redis` v1
```json
{"operation":"get","propertyName":"triaje_estado","key":"={{ 'triaje:' + $('Preparar Mensaje Final').first().json.phone }}","options":{}}
```
`credentials: {redis:{id:'kdtSKwGbN1xAZeUh', name:'Redis account'}}`, `onError: "continueRegularOutput"`, `alwaysOutputData: true`. Key ausente → `triaje_estado` null/undefined = sin estado. Position [11900, 800].

### 2.2 `Triaje: Config` — `n8n-nodes-base.postgres` v2.5 (cred `TpYhZX4UT61xAKSV`)
```sql
SELECT v.tipo, v.opcion, v.url, v.filename, v.caption, v.pregunta_guiada,
       v.texto_salida_emergencia, v.texto_cierre, v.texto_no_resuelto,
       c.activo AS triaje_activo, c.modo, c.telefonos_piloto,
       c.ttl_video_seg, c.ttl_pregunta_seg, c.aviso_escalaciones_log
FROM public.triaje_videos v CROSS JOIN public.triaje_config c
WHERE c.id = 1 AND v.activo = true AND v.url IS NOT NULL
ORDER BY v.tipo, v.opcion;
```
`operation: executeQuery`, `options: {}`, `onError: "continueRegularOutput"`, `alwaysOutputData: true`. 0 filas / error / tabla inexistente ⇒ el Code siguiente decide `escalar` (fail-closed). Position [12120, 800].

### 2.3 `Triaje: Gate + Preparar` — `n8n-nodes-base.code` v2 (runOnceForAllItems)
`jsCode = GATE_JS + '\n\n' + WRAPPER` donde `GATE_JS` es `triaje/gate_red_flags.js` textual (exporta `gateRedFlags(texto) → {escala, flags}`; termina en `if (typeof module !== "undefined") module.exports = …`, ya probado embebido en la sombra). WRAPPER (esbozo completo):
```js
const SYSTEM_PROMPT = <json.dumps(SYSTEM_PROMPT_TRIAJE)>;   // ver 2.5
const MODELO = 'gpt-5-mini';
const NO_ESTADO = { paso: null };
const pm = $('Preparar Mensaje Final').first().json;
const phone = String(pm.phone || '');
const text  = String(pm.text || '').trim();
let ctx = ''; try { ctx = String($('Build Router Context').first().json.ctx || ''); } catch (e) { ctx = ''; }

// --- config (fail-closed) ---
const rows = $input.all().map(i => i.json).filter(r => r && r.tipo && r.url);
const cfgRow = rows[0] || null;
const errCfg = $input.first().json && $input.first().json.error;
const cfg = {};                       // tipo -> { opciones:[{opcion,url,caption,filename}], pregunta, salida, cierre, no_resuelto }
for (const r of rows) {
  cfg[r.tipo] = cfg[r.tipo] || { opciones: [], pregunta: r.pregunta_guiada || '', salida: r.texto_salida_emergencia || '', cierre: r.texto_cierre || '', no_resuelto: r.texto_no_resuelto || '' };
  cfg[r.tipo].opciones.push({ opcion: Number(r.opcion), url: r.url, caption: r.caption || '', filename: r.filename || ('triaje_' + r.tipo + '_op' + r.opcion + '.mp4') });
}
for (const t of Object.keys(cfg)) cfg[t].opciones.sort((a, b) => a.opcion - b.opcion);
let piloto = cfgRow ? cfgRow.telefonos_piloto : [];
if (typeof piloto === 'string') piloto = piloto.replace(/[{}"]/g, '').split(',').map(s => s.trim()).filter(Boolean);
const permitido = !!cfgRow && cfgRow.triaje_activo === true && !errCfg && (piloto.length === 0 || piloto.includes(phone));
const modo = cfgRow ? (cfgRow.modo || 'piloto') : 'piloto';
const ttl_video = cfgRow && cfgRow.ttl_video_seg ? Number(cfgRow.ttl_video_seg) : 7200;
const ttl_pregunta = cfgRow && cfgRow.ttl_pregunta_seg ? Number(cfgRow.ttl_pregunta_seg) : 1800;

// --- estado: Redis (primario) o reconstruido del ctx del Router (confirmación/fallback) ---
let estado = null; let estado_origen = 'ninguno';
try {
  const raw = $('Triaje: Redis GET estado').first().json.triaje_estado;
  if (raw) { const e = JSON.parse(String(raw)); if (e && e.paso && !['cerrado','escalado'].includes(e.paso)) {
    const edad = (Date.now() - Number(e.ts || 0)) / 1000;
    const max = e.paso === 'pregunta' ? ttl_pregunta : ttl_video;
    if (edad <= max) { estado = e; estado_origen = 'redis'; }
  } }
} catch (e) { estado = null; }
if (!estado && ctx) {
  // entradas 'PACIENTE: …' / 'BOT: …' separadas por '\n---\n' (Build Router Context, ORDER BY id ASC)
  const entradas = ctx.split('\n---\n');
  let st = null, ultimoPaciente = '';
  for (const en of entradas) {
    if (en.startsWith('PACIENTE: ')) { ultimoPaciente = en.slice(10).trim(); continue; }
    if (!en.startsWith('BOT: ')) continue;
    const b = en.slice(5);
    let m;
    if ((m = b.match(/^\[TRIAJE VIDEO ([a-z_]+) opcion (\d)\]/))) st = { paso: 'video_enviado', tipo: m[1], opcion: Number(m[2]), texto_original: ultimoPaciente };
    else if ((m = b.match(/^\[TRIAJE PREGUNTA ([a-z_]+)\] ?(.*)$/s))) st = { paso: 'pregunta', tipo: m[1], pregunta: m[2].trim(), texto_original: ultimoPaciente };
    else if (/^\[TRIAJE INFO\]/.test(b)) { /* no cambia el estado */ }
    else st = null;   // [TRIAJE CIERRE], [TRIAJE ESCALADO], canned de Urgencia, [ATENCION HUMANA …], cualquier otro BOT => triaje terminado
  }
  if (st) { estado = st; estado_origen = 'memoria'; }
}

// --- gate determinístico (siempre, en cualquier paso) ---
const gate = gateRedFlags(text);

// --- regex de seguimiento (límites Unicode como el gate, sin \b) ---
const B0 = '(?<![\\p{L}\\p{N}])', B1 = '(?![\\p{L}\\p{N}])';
const RE_NO_SIRVIO = new RegExp(B0 + '(no\\s+(me\\s+)?(sirv\\w*|funcion\\w*|ayud\\w*|alcanz\\w*|result\\w*|pude|puedo|consigo|consegu\\w*|tengo\\s+(la\\s+)?(cera|pinza))|sigue\\w*|igual|peor|todav[ií]a|a[uú]n\\s+(pincha|duele|molesta)|se\\s+(volvi[oó]|sali[oó])\\s+(a\\s+salir|de\\s+nuevo|otra\\s+vez)|otra\\s+vez|de\\s+nuevo|no\\s+hay\\s+caso|no\\s+se\\s+puede|no\\s+entra|no\\s+queda)' + B1, 'iu');
const RE_CIERRE = new RegExp('^\\s*(ok|okey|dale|listo|gracias|muchas\\s+gracias|mil\\s+gracias|perfecto|genial|joya|buen[ií]simo|b[aá]rbaro|ya\\s+(me\\s+)?(la\\s+|lo\\s+)?(puse|coloqu[eé]|pude|logr[eé]|hice)|ya\\s+est[aá]|me\\s+sirvi[oó]|funcion[oó]|me\\s+ayud[oó]|solucionad[oa]|resuelto|qued[oó]\\s+bien)' + B1, 'iu');
const esNoSirvio = RE_NO_SIRVIO.test(text);
const esCierre = !esNoSirvio && RE_CIERRE.test(text);

// --- decisión previa al LLM ---
let decision, motivo, reclasificacion = false, user = '';
if (!permitido) { decision = 'escalar'; motivo = errCfg ? 'config_error' : (!cfgRow ? 'config_vacia' : (cfgRow.triaje_activo !== true ? 'config_inactiva' : 'fuera_de_piloto')); }
else if (gate.escala) { decision = 'escalar'; motivo = 'gate_red_flags' + (estado ? '_post_' + estado.paso : ''); }
else if (estado && estado.paso === 'video_enviado') {
  if (esNoSirvio) decision = 'seguir';       // Decidir elige opción N+1 o escalar_con_texto
  else if (esCierre) decision = 'cerrar';
  else decision = 'escalar_con_texto';       // fail-closed: seguimiento no reconocido tras video
  motivo = 'post_video_' + decision;
} else if (estado && estado.paso === 'pregunta') {
  decision = 'clasificar'; reclasificacion = true; motivo = 'respuesta_pregunta';
  user = 'MENSAJE ORIGINAL DEL PACIENTE:\n' + (estado.texto_original || '(no disponible)') + '\n\nPREGUNTA GUIADA QUE LE HIZO EL BOT:\n' + (estado.pregunta || '') + '\n\nRESPUESTA DEL PACIENTE:\n' + text;
} else {
  decision = 'clasificar'; motivo = 'nuevo';
  user = 'CONTEXTO RECIENTE (puede estar vacio):\n' + (ctx || '(sin contexto)') + '\n\nMENSAJE ACTUAL DEL PACIENTE:\n' + text;
}
const llm_body = decision === 'clasificar' ? JSON.stringify({ model: MODELO, messages: [{ role: 'system', content: SYSTEM_PROMPT }, { role: 'user', content: user }], response_format: { type: 'json_object' } }) : '';
return [{ json: { phone, text, decision, motivo, reclasificacion, permitido, modo, cfg, estado, estado_origen, gate_escala: gate.escala, gate_flags: gate.flags, es_no_sirvio: esNoSirvio, es_cierre: esCierre, ttl_video, ttl_pregunta, aviso_escalaciones_log: !!(cfgRow && cfgRow.aviso_escalaciones_log), llm_body } }];
```
Position [12340, 800].

### 2.4 `Triaje: Necesita LLM?` — `n8n-nodes-base.if` v2.2
`={{ $json.decision }}` string equals `clasificar` (typeValidation strict). [0 true] → `Triaje: Clasificar (gpt-5-mini)`; [1 false] → `Triaje: Decidir`. Position [12560, 800].

### 2.5 `Triaje: Clasificar (gpt-5-mini)` — `n8n-nodes-base.httpRequest` v4.2 (patrón exacto del sombra `Clasificar (gpt-5-mini)`)
```json
{"method":"POST","url":"https://api.openai.com/v1/chat/completions","authentication":"predefinedCredentialType","nodeCredentialType":"openAiApi","sendBody":true,"specifyBody":"json","jsonBody":"={{ $json.llm_body }}","options":{"response":{"response":{"neverError":true}},"timeout":20000}}
```
`credentials: {openAiApi:{id:'nYujqfon7GGDnJUO', name:'OpenAi account'}}`, `onError: "continueRegularOutput"`. Position [12780, 700].
SYSTEM_PROMPT_TRIAJE (= el de `scripts/create_test_triaje_webhook.py` con 3 líneas extra):
```
Sos un clasificador de urgencias de ORTODONCIA para un triaje automático de una clínica (Dra. Raquel, Jujuy).
Recibís el contexto reciente y el mensaje actual de un paciente. Clasificá el problema ACTUAL en UNA categoría:
- "red_flag": trauma/golpe/caída, sangrado abundante, pieza tragada, hinchazón/dificultad para respirar-tragar, fiebre, dolor intenso que no cede.
- "alambre_pincha": el alambre principal (arco) se salió del tubo/bracket o sobresale y pincha mejilla/encía.
- "bracket_suelto": un bracket se despegó del diente.
- "alambre_girado": el arco se corrió hacia un costado (sobra de un lado, corto del otro).
- "ligadura_pincha": una ligadura (alambrecito finito o gomita de un solo bracket) pincha.
- "otra_urgencia": urgencia real que no cae en los 4 tipos (contención rota, Invisalign, dolor sin causa clara, etc.).
- "no_urgencia": no es una urgencia clínica.
Sé conservador: si la información no alcanza para distinguir el tipo, usá "otra_urgencia" o confianza "baja". Si el paciente respondió una PREGUNTA GUIADA, usá la respuesta para subir o bajar la confianza del tipo preguntado. Si hay CUALQUIER señal de red flag, devolvé "red_flag".
Respondé SOLO JSON: {"tipo": "...", "confianza": "alta|media|baja", "razon": "una oración"}
```

### 2.6 `Triaje: Decidir` — Code v2. Entrada: respuesta OpenAI (vía 2.5) o el item de Gate (vía IF false). Siempre lee `$('Triaje: Gate + Preparar').first().json`.
```js
const g = $('Triaje: Gate + Preparar').first().json;
const pm = $('Preparar Mensaje Final').first().json;
const phone = g.phone, remoteJid = pm.remoteJid || '';
let pushName = ''; try { pushName = String($('Edit Fields - Extraer Datos').first().json.pushName || ''); } catch (e) {}
const esc = v => (v === null || v === undefined) ? 'NULL' : "'" + String(v).replace(/'/g, "''") + "'";
const memRow = (type, content, kw) => esc(JSON.stringify({ type, content, additional_kwargs: kw, response_metadata: {}, tool_calls: [], invalid_tool_calls: [] })) + '::jsonb';
let tipo = null, confianza = null, razon = null, modelo = null;
let accion, opcion = null, video = null, texto_envio = '', tag = '';
let motivo = g.motivo;
const cfgTipo = t => (g.cfg && g.cfg[t]) || null;

if (g.decision === 'clasificar') {
  modelo = 'gpt-5-mini';
  try {
    const content = $input.first().json.choices[0].message.content;
    const p = JSON.parse(String(content).replace(/^```(json)?|```$/gm, '').trim());
    tipo = String(p.tipo || 'error_llm'); confianza = String(p.confianza || 'baja'); razon = String(p.razon || '').slice(0, 300);
  } catch (e) { tipo = 'error_llm'; confianza = 'baja'; razon = 'parse: ' + String(e).slice(0, 120); }
  const c = cfgTipo(tipo);
  if (tipo === 'red_flag' || tipo === 'error_llm' || !c || c.opciones.length === 0) { accion = 'escalar'; motivo = !c ? 'tipo_sin_video:' + tipo : 'tipo_' + tipo; }
  else if (confianza === 'alta') { accion = 'video'; opcion = 1; video = c.opciones[0]; }
  else if (!g.reclasificacion && c.pregunta) { accion = 'pregunta'; texto_envio = c.pregunta; }
  else { accion = 'escalar'; motivo = g.reclasificacion ? 'reclasificacion_no_alta' : 'sin_pregunta_guiada'; }
} else if (g.decision === 'seguir') {
  tipo = g.estado.tipo; const c = cfgTipo(tipo);
  const sig = c ? c.opciones.find(o => o.opcion === Number(g.estado.opcion) + 1) : null;
  if (sig) { accion = 'video'; opcion = sig.opcion; video = sig; }
  else { accion = 'escalar_con_texto'; motivo = 'sin_mas_opciones'; texto_envio = (c && c.no_resuelto) || 'Entendido. Le pasamos a la doctora para que le coordine lo antes posible.'; }
} else if (g.decision === 'cerrar') {
  tipo = g.estado.tipo; const c = cfgTipo(tipo); accion = 'cerrar';
  texto_envio = (c && c.cierre) || 'Perfecto, gracias por avisar. Cualquier cosa, escribinos por acá.';
} else if (g.decision === 'escalar_con_texto') {
  tipo = g.estado.tipo; const c = cfgTipo(tipo); accion = 'escalar_con_texto';
  texto_envio = (c && c.no_resuelto) || 'Entendido. Le pasamos a la doctora para que le coordine lo antes posible.';
} else { accion = 'escalar'; tipo = g.estado ? g.estado.tipo : null; }

// --- payloads de envío ---
let caption = '', video_url = '', filename = '', texto_salida = '';
if (accion === 'video') { const c = cfgTipo(tipo); caption = video.caption; video_url = video.url; filename = video.filename; texto_salida = c.salida || ''; texto_envio = texto_salida; }

// --- estado Redis ---
const ts = Date.now();
let estado_json = '', estado_ttl = 60;
if (accion === 'video') { estado_json = JSON.stringify({ tipo, opcion, paso: 'video_enviado', ts, texto_original: g.estado && g.estado.texto_original ? g.estado.texto_original : g.text }); estado_ttl = g.ttl_video; }
else if (accion === 'pregunta') { estado_json = JSON.stringify({ tipo, opcion: null, paso: 'pregunta', ts, pregunta: texto_envio, texto_original: g.text }); estado_ttl = g.ttl_pregunta; }
else if (accion === 'cerrar') { estado_json = JSON.stringify({ tipo, paso: 'cerrado', ts }); estado_ttl = 60; }
else if (accion === 'escalar_con_texto') { estado_json = JSON.stringify({ tipo, paso: 'escalado', ts }); estado_ttl = 60; }

// --- SQL log (INSERT antes de actuar; envio_ok se marca después) ---
const accionLog = { escalar: 'escalado', escalar_con_texto: 'escalado', video: 'video', pregunta: 'pregunta', cerrar: 'cerrado' }[accion];
const flags = JSON.stringify(g.gate_flags.map(f => 'gate:' + f));
const cols = `telefono, exec_id, mensaje_paciente, gate_red_flags, gate_escala, tipo, confianza, razon, modelo, modo, accion, video_enviado, opcion_enviada, paso_previo, estado_origen, motivo_decision, foto_recibida, envio_ok`;
const vals = `${esc(phone)}, ${esc($execution.id)}, ${esc(g.text)}, ${esc(flags)}::jsonb, ${g.gate_escala ? 'true' : 'false'}, ${esc(tipo)}, ${esc(confianza)}, ${esc(razon)}, ${esc(modelo)}, ${esc(g.modo)}, ${esc(accionLog)}, ${esc(video_url || null)}, ${opcion === null ? 'NULL' : opcion}, ${esc(g.estado ? g.estado.paso : null)}, ${esc(g.estado_origen)}, ${esc(motivo)}, ${/\[IMAGEN\]/.test(g.text) ? 'true' : 'false'}, false`;
let sql_log;
if (accion === 'video' && g.aviso_escalaciones_log) {
  sql_log = `WITH e AS (INSERT INTO escalaciones_log(telefono, motivo, origen, exec_id) VALUES (${esc(phone)}, ${esc('[TRIAJE VIDEO] Urgencia atendida con video (' + tipo + ', Opcion ' + opcion + ') — sin intervencion humana. Tel ' + phone)}, 'triaje', ${esc($execution.id)}) RETURNING id) INSERT INTO triaje_urgencias_log(escalacion_id, ${cols}) SELECT e.id, ${vals} FROM e RETURNING id`;
} else { sql_log = `INSERT INTO triaje_urgencias_log(${cols}) VALUES (${vals}) RETURNING id`; }

// --- SQL memoria (se ejecuta SOLO tras envío exitoso; $1 = id del log) ---
const kwBase = { source: 'triaje', tipo, opcion, pushName, exec_id: $execution.id };
const rowsMem = [];
if (accion !== 'escalar_con_texto') rowsMem.push(`(${esc(phone)}, ${memRow('human', g.text, { source: 'triaje', pushName })})`);
if (accion === 'video') {
  rowsMem.push(`(${esc(phone)}, ${memRow('ai', '[TRIAJE VIDEO ' + tipo + ' opcion ' + opcion + '] ' + caption, { ...kwBase, source: 'triaje_video', video_url })})`);
  if (texto_salida) rowsMem.push(`(${esc(phone)}, ${memRow('ai', '[TRIAJE INFO] ' + texto_salida, { ...kwBase, source: 'triaje_video' })})`);
} else if (accion === 'pregunta') rowsMem.push(`(${esc(phone)}, ${memRow('ai', '[TRIAJE PREGUNTA ' + tipo + '] ' + texto_envio, { ...kwBase, source: 'triaje_pregunta' })})`);
else if (accion === 'cerrar') rowsMem.push(`(${esc(phone)}, ${memRow('ai', '[TRIAJE CIERRE] ' + texto_envio, { ...kwBase, source: 'triaje_cierre' })})`);
else if (accion === 'escalar_con_texto') rowsMem.push(`(${esc(phone)}, ${memRow('ai', '[TRIAJE ESCALADO] ' + texto_envio, { ...kwBase, source: 'triaje_escalado' })})`);
const sql_mem = rowsMem.length ? `WITH m AS (INSERT INTO n8n_chat_histories(session_id, message) VALUES ${rowsMem.join(', ')} RETURNING id) UPDATE triaje_urgencias_log SET envio_ok = true, chat_history_id = (SELECT max(id) FROM m) WHERE id = $1::bigint` : `UPDATE triaje_urgencias_log SET envio_ok = true WHERE id = $1::bigint`;

console.log('[TRIAJE]', JSON.stringify({ phone, accion, tipo, confianza, opcion, motivo, estado_origen: g.estado_origen, gate: g.gate_flags }));
return [{ json: { phone, remoteJid, accion, tipo, confianza, razon, opcion, motivo, caption, video_url, filename, texto_envio, estado_key: 'triaje:' + phone, estado_json, estado_ttl, sql_log, sql_mem } }];
```
Position [13000, 800].

### 2.7 `Triaje: Log` — Postgres v2.5 (cred `TpYhZX4UT61xAKSV`)
`{"operation":"executeQuery","query":"={{ $json.sql_log }}","options":{}}`, `onError: "continueRegularOutput"`, `alwaysOutputData: true`. Output `{id}`. Si falla, el flujo sigue (el paciente nunca se queda sin respuesta por un log). Position [13220, 800].

### 2.8 `Triaje: Switch Accion` — `n8n-nodes-base.switch` v3.2, `typeValidation strict`, sin fallback (`fallbackOutput: "none"`)
Reglas sobre `={{ $('Triaje: Decidir').first().json.accion }}` equals: **0** `escalar` → `Sub-Agent Urgencia`; **1** `video` → `Triaje: Enviar Video`; **2** `pregunta` → `Triaje: Enviar Texto`; **3** `cerrar` → `Triaje: Enviar Texto`; **4** `escalar_con_texto` → `Triaje: Enviar Texto`. (Decidir garantiza uno de los 5 valores; igual, `fallbackOutput: "extra"` → `Sub-Agent Urgencia` como cinturón: output 5.) Position [13440, 800].

### 2.9 `Triaje: Enviar Video` — httpRequest v4.2, `credentials: {}`
`method POST`, `url https://evo.raquelrodriguez.com.ar/send/media` (derivada en el script como `enviar['parameters']['url'].split('/send/')[0] + '/send/media'`), `sendHeaders true`, `headerParameters = copy.deepcopy(<'Evolution API - Enviar Mensaje'>['parameters']['headerParameters'])` del GET fresco (apikey nunca en el script), `sendBody true`, `specifyBody json`, `jsonBody`:
```
={
  "number": {{ JSON.stringify(($('Preparar Mensaje Final').first().json.remoteJid || '').replace(/[^0-9]/g, '')) }},
  "type": "video",
  "url": {{ JSON.stringify($('Triaje: Decidir').first().json.video_url) }},
  "caption": {{ JSON.stringify($('Triaje: Decidir').first().json.caption) }},
  "filename": {{ JSON.stringify($('Triaje: Decidir').first().json.filename || 'video.mp4') }}
}
```
`options: {"response":{"response":{"neverError":true}},"timeout":90000}`, `onError: "continueRegularOutput"`. Position [13660, 700].

### 2.10 `Triaje: Video OK?` — IF v2.2 strict
`={{ String((($json.data || {}).Info || {}).Type || '') }}` string equals `VideoMessage` AND `={{ !!((($json.data || {}).Info || {}).ID) }}` boolean true. [0] → `Triaje: Enviar Texto` (manda el texto de salida de emergencia); [1] → `Sub-Agent Urgencia` (fail-closed: el paciente recibe la escalación de hoy). Position [13880, 700].

### 2.11 `Triaje: Enviar Texto` — httpRequest v4.2 (clon de `Evolution API - Enviar Mensaje`)
`url https://evo.raquelrodriguez.com.ar/send/text`, mismos headers clonados, `jsonBody`:
```
={
  "number": {{ JSON.stringify(($('Preparar Mensaje Final').first().json.remoteJid || '').replace(/[^0-9]/g, '')) }},
  "text": {{ JSON.stringify($('Triaje: Decidir').first().json.texto_envio) }}
}
```
`options: {"response":{"response":{"neverError":true}},"timeout":30000}`, `onError: "continueRegularOutput"`. Entradas: `Triaje: Video OK?`[0], `Triaje: Switch Accion`[2],[3],[4]. Position [14100, 800].

### 2.12 `Triaje: Texto OK?` — IF v2.2
`={{ !!((($json.data || {}).Info || {}).ID) || ['video','cerrar'].includes($('Triaje: Decidir').first().json.accion) }}` boolean true. (Tras un video exitoso o en un cierre, una falla del texto secundario NO escala: el paciente ya recibió lo importante.) [0] → `Triaje: Memoria + Log OK`; [1] → `Sub-Agent Urgencia` (pregunta o texto pre-escalación no entregados ⇒ escalar como hoy). Position [14320, 800].

### 2.13 `Triaje: Memoria + Log OK` — Postgres v2.5 (cred `TpYhZX4UT61xAKSV`)
`query: ={{ $('Triaje: Decidir').first().json.sql_mem }}`, `options.queryReplacement: ={{ $('Triaje: Log').first().json.id || 0 }}`, `onError: "continueRegularOutput"`, `alwaysOutputData: true`. Inserta `human` (texto del paciente) + `ai` con prefijo `[TRIAJE …]` con el MISMO shape que `Build fromMe AI memory` (`type, content, additional_kwargs, response_metadata, tool_calls, invalid_tool_calls`), y marca `envio_ok=true, chat_history_id` en el log. Position [14540, 800].

### 2.14 `Triaje: Redis SET estado` — Redis v1
`{"operation":"set","key":"={{ $('Triaje: Decidir').first().json.estado_key }}","value":"={{ $('Triaje: Decidir').first().json.estado_json }}","keyType":"string","expire":true,"ttl":"={{ $('Triaje: Decidir').first().json.estado_ttl }}"}` (mismo `expire/ttl` que usa `Rate Limit INCR`), `onError: "continueRegularOutput"`. Si `expire/ttl` no estuviera disponible en `set` de esta versión, el estado igual se auto-expira: el JSON lleva `ts` y `Gate + Preparar` descarta estados más viejos que el TTL. Position [14760, 800].

### 2.15 `Triaje: Sigue a escalar?` — IF v2.2
`={{ $('Triaje: Decidir').first().json.accion }}` string equals `escalar_con_texto`. [0] → `Sub-Agent Urgencia` (escala + grupo + label humano, como hoy; el paciente YA recibió `texto_no_resuelto`); [1] → sin conexión (fin de la rama: video/pregunta/cierre no envían nada más — "cortar la rama"). Position [14980, 800].

**Total: 15 nodos.** Sin NoOp final (Redis SET / IF false terminan la rama).

---

## 3. Conexiones (nuevas y modificadas, con índices)

Modificada:
- `Switch sobre Intent`.main[2]: `[{Sub-Agent Urgencia,0}]` → `[{node:'Triaje: Redis GET estado', type:'main', index:0}]` (assert previo: debe ser exactamente el valor viejo).

Nuevas (`conns[src] = {main: [[...out0], [...out1], …]}`):
- `Triaje: Redis GET estado`.main[0] → `Triaje: Config`(0)
- `Triaje: Config`.main[0] → `Triaje: Gate + Preparar`(0)
- `Triaje: Gate + Preparar`.main[0] → `Triaje: Necesita LLM?`(0)
- `Triaje: Necesita LLM?`.main[0] → `Triaje: Clasificar (gpt-5-mini)`(0); .main[1] → `Triaje: Decidir`(0)
- `Triaje: Clasificar (gpt-5-mini)`.main[0] → `Triaje: Decidir`(0)
- `Triaje: Decidir`.main[0] → `Triaje: Log`(0)
- `Triaje: Log`.main[0] → `Triaje: Switch Accion`(0)
- `Triaje: Switch Accion`.main[0] → `Sub-Agent Urgencia`(0); [1] → `Triaje: Enviar Video`(0); [2] → `Triaje: Enviar Texto`(0); [3] → `Triaje: Enviar Texto`(0); [4] → `Triaje: Enviar Texto`(0); [5 fallback] → `Sub-Agent Urgencia`(0)
- `Triaje: Enviar Video`.main[0] → `Triaje: Video OK?`(0)
- `Triaje: Video OK?`.main[0] → `Triaje: Enviar Texto`(0); .main[1] → `Sub-Agent Urgencia`(0)
- `Triaje: Enviar Texto`.main[0] → `Triaje: Texto OK?`(0)
- `Triaje: Texto OK?`.main[0] → `Triaje: Memoria + Log OK`(0); .main[1] → `Sub-Agent Urgencia`(0)
- `Triaje: Memoria + Log OK`.main[0] → `Triaje: Redis SET estado`(0)
- `Triaje: Redis SET estado`.main[0] → `Triaje: Sigue a escalar?`(0)
- `Triaje: Sigue a escalar?`.main[0] → `Sub-Agent Urgencia`(0); .main[1] → `[]`

Intactas: `Sub-Agent Urgencia`.main[0] → `Fallback Output`; `LM Sub-Agent Urgencia`/`Postgres Chat Memory`/`escalar_a_secretaria` → `Sub-Agent Urgencia`; todo lo demás.

---

## 4. Estado Redis

- Key: `triaje:{phone}` (`phone` = `$('Preparar Mensaje Final').first().json.phone`, mismo string que `chat_buffer:`/`ratelimit:`/session_id). Cred `Redis account` (`kdtSKwGbN1xAZeUh`).
- Value (string JSON): `{"tipo":"alambre_pincha","opcion":1,"paso":"video_enviado","ts":1788600000000,"texto_original":"se me salió el alambre y pincha"}` · pregunta: `{"tipo","opcion":null,"paso":"pregunta","ts","pregunta":"…","texto_original":"…"}` · terminales: `{"tipo","paso":"cerrado","ts"}` / `{"tipo","paso":"escalado","ts"}` (TTL 60 s; `Gate + Preparar` los trata como "sin estado").
- TTL: `video_enviado` = `triaje_config.ttl_video_seg` (7200), `pregunta` = `ttl_pregunta_seg` (1800). Doble expiración: EXPIRE de Redis + chequeo de `ts` en el Code.
- Precedencia: Redis (si existe y no expiró) > reconstrucción desde `Build Router Context`.ctx (último marcador `BOT: [TRIAJE VIDEO tipo opcion N]` / `[TRIAJE PREGUNTA tipo] …` sin un `[TRIAJE CIERRE]`/`[TRIAJE ESCALADO]`/BOT no-triaje posterior). Así "mismo problema, segundo mensaje" al día siguiente sigue reconociéndose (memoria = fuente de continuidad, Redis = confirmación rápida), y nunca se re-manda la Opción 1 al mismo caso.
- Limpieza: SET terminal con TTL 60 (no hay nodo DEL). `Clear Old Memory` borra las filas `[TRIAJE …]` a los 7 días (sources `triaje*` no están en su NOT IN — correcto).

---

## 5. Tabla de config (DDL + seeds; correr ANTES del PUT con psycopg2 y `SUPABASE_DB_*` como `scripts/create_triaje_urgencias_log_table.py`)

```sql
-- kill-switch global + allow-list piloto (fila única, molde recordatorios_config)
CREATE TABLE IF NOT EXISTS public.triaje_config (
  id                     smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  activo                 boolean NOT NULL DEFAULT false,          -- false => TODO escala como hoy (no requiere PUT)
  modo                   text    NOT NULL DEFAULT 'piloto' CHECK (modo IN ('sombra','piloto','live')),
  telefonos_piloto       text[]  NOT NULL DEFAULT '{}',           -- vacío = todos; en piloto: '{5491161461034}'
  ttl_video_seg          integer NOT NULL DEFAULT 7200,
  ttl_pregunta_seg       integer NOT NULL DEFAULT 1800,
  aviso_escalaciones_log boolean NOT NULL DEFAULT false,          -- true => además fila '[TRIAJE VIDEO] …' en escalaciones_log (ver §7)
  updated_at             timestamptz NOT NULL DEFAULT now(),
  updated_by             text
);
INSERT INTO public.triaje_config (id, activo, telefonos_piloto) VALUES (1, false, '{}') ON CONFLICT (id) DO NOTHING;

-- una fila por (tipo, opcion); pregunta/salida/cierre/no_resuelto se leen de la fila opcion=1 (tabla única, como pide C)
CREATE TABLE IF NOT EXISTS public.triaje_videos (
  id                      bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  tipo                    text NOT NULL CHECK (tipo ~ '^[a-z_]+$'),   -- = salida del clasificador y triaje_urgencias_log.tipo
  opcion                  smallint NOT NULL CHECK (opcion BETWEEN 1 AND 9),
  url                     text CHECK (url IS NULL OR url ~ '^https://'),
  filename                text,
  caption                 text NOT NULL,          -- canned, texto de la Dra.; NUNCA LLM
  pregunta_guiada         text,                   -- NULL => no preguntar (media/baja => escalar)
  texto_salida_emergencia text NOT NULL,          -- se manda como texto aparte después del video
  texto_cierre            text NOT NULL,          -- respuesta a "listo gracias"
  texto_no_resuelto       text NOT NULL,          -- "no sirvió" sin más opciones, antes de escalar
  activo                  boolean NOT NULL DEFAULT false,
  updated_at              timestamptz NOT NULL DEFAULT now(),
  updated_by              text,
  CONSTRAINT triaje_videos_tipo_opcion_uq UNIQUE (tipo, opcion),
  CONSTRAINT triaje_videos_activo_con_url CHECK (activo = false OR url IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_triaje_videos_tipo ON public.triaje_videos (tipo, opcion);

-- columnas nuevas en el log existente (no rompen la sombra)
ALTER TABLE public.triaje_urgencias_log
  ADD COLUMN IF NOT EXISTS opcion_enviada  smallint,
  ADD COLUMN IF NOT EXISTS paso_previo     text,
  ADD COLUMN IF NOT EXISTS estado_origen   text,
  ADD COLUMN IF NOT EXISTS motivo_decision text,
  ADD COLUMN IF NOT EXISTS foto_recibida   boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS envio_ok        boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS chat_history_id bigint;
CREATE INDEX IF NOT EXISTS idx_triaje_telefono_created ON public.triaje_urgencias_log (telefono, created_at DESC);

-- seeds (textos = descripción de Raquel del 28/8 como núcleo; editables desde la tabla; todos verificados contra los 20 regex del Banlist: sin aplicá/guardá/sacá/tomá/enjuagá/venite/esperamos/'lo antes posible'+clínica/no te preocupes)
INSERT INTO public.triaje_videos (tipo, opcion, url, filename, caption, pregunta_guiada, texto_salida_emergencia, texto_cierre, texto_no_resuelto, activo) VALUES
('alambre_pincha', 1,
 'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion1.mp4',
 'alambre_pincha_opcion1.mp4',
 'Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel. Le envío un video de la doctora para esta situación (alambre que se salió y pincha).

Opción 1: colocar cera de ortodoncia en la punta del alambre, como muestra el video, para aliviar la molestia hasta el control.

Si con eso no alcanza, respondé este mensaje con "no me sirvió" y le envío la Opción 2.',
 'Para orientarlo mejor: ¿el alambre se salió del último bracket o tubito de atrás y le pincha el cachete? Respondé SÍ o NO. Si puede, mándenos una foto de la zona: queda para la doctora.',
 'Si el dolor es fuerte, hay sangrado, hinchazón o no mejora, respondé por acá y le pasamos el caso a la Dra. Raquel para que lo coordine.',
 'Perfecto, gracias por avisar. Cualquier cosa, escríbanos por acá.',
 'Entendido. Le pasamos a la doctora para que le coordine lo antes posible.',
 true),
('alambre_pincha', 2,
 'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion2.mp4',
 'alambre_pincha_opcion2.mp4',
 'Opción 2: intentar reinsertar el alambre en el tubo o bracket de donde se soltó, con ayuda de una pinza de alicate o de cejas, como muestra el video.

Si tampoco resulta, respondé "no me sirvió" y le pasamos el caso a la doctora.',
 NULL,
 'Si el dolor es fuerte, hay sangrado, hinchazón o no mejora, respondé por acá y le pasamos el caso a la Dra. Raquel para que lo coordine.',
 'Perfecto, gracias por avisar. Cualquier cosa, escríbanos por acá.',
 'Entendido. Le pasamos a la doctora para que le coordine lo antes posible.',
 true),
('bracket_suelto',  1, NULL, NULL, '[PENDIENTE video de la Dra.]', NULL, '-', '-', '-', false),
('alambre_girado',  1, NULL, NULL, '[PENDIENTE video de la Dra.]', NULL, '-', '-', '-', false),
('ligadura_pincha', 1, NULL, NULL, '[PENDIENTE video de la Dra.]', NULL, '-', '-', '-', false)
ON CONFLICT (tipo, opcion) DO NOTHING;

ALTER TABLE public.triaje_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.triaje_videos ENABLE ROW LEVEL SECURITY;
```
Cuando Raquel mande otro video: `scripts/upload_urgencia_video_supabase.py "<mp4>" "<tipo>/opcion1.mp4"` → `UPDATE triaje_videos SET url=…, caption=…, activo=true WHERE tipo=… AND opcion=1` (el CHECK impide activar sin URL). Cero PUT. Guardrail: cualquier UI del panel que edite estas columnas debe pasar `chequearBanlist` (`lib/agente-guardrails.ts`) como hace `guardarPromptAction`; `tests/test_triaje_textos_banlist.py` corre el JS real del `Banlist Validator` (extraído del workflow) sobre todas las columnas de texto de los seeds y falla si alguna dispara.

Nota: la segunda parte de la Opción 1 dice "respondé este mensaje con 'no me sirvió'": es a propósito, fija el vocabulario que matchea `RE_NO_SIRVIO`.

---

## 6. Persistencia en memoria (query exacta que genera `Decidir` y ejecuta `Triaje: Memoria + Log OK`)

Ejemplo real para accion `video`, opcion 1, phone 5491161461034 (`$1` = `$('Triaje: Log').first().json.id`):
```sql
WITH m AS (
  INSERT INTO n8n_chat_histories(session_id, message) VALUES
  ('5491161461034', '{"type":"human","content":"se me salió el alambre de atrás y me pincha","additional_kwargs":{"source":"triaje","pushName":"Lucas"},"response_metadata":{},"tool_calls":[],"invalid_tool_calls":[]}'::jsonb),
  ('5491161461034', '{"type":"ai","content":"[TRIAJE VIDEO alambre_pincha opcion 1] Hola! Soy Asiri… Opción 1: colocar cera…","additional_kwargs":{"source":"triaje_video","tipo":"alambre_pincha","opcion":1,"pushName":"Lucas","exec_id":"270999","video_url":"https://…/opcion1.mp4"},"response_metadata":{},"tool_calls":[],"invalid_tool_calls":[]}'::jsonb),
  ('5491161461034', '{"type":"ai","content":"[TRIAJE INFO] Si el dolor es fuerte, hay sangrado…","additional_kwargs":{"source":"triaje_video","tipo":"alambre_pincha","opcion":1,…},"response_metadata":{},"tool_calls":[],"invalid_tool_calls":[]}'::jsonb)
  RETURNING id
)
UPDATE triaje_urgencias_log SET envio_ok = true, chat_history_id = (SELECT max(id) FROM m) WHERE id = $1::bigint
```
Efectos verificados sobre los lectores existentes: `Build Router Context` muestra `PACIENTE: …` / `BOT: [TRIAJE VIDEO …]` / `BOT: [TRIAJE INFO] …` (últimas 6) → el Router ve el estado; `Postgres Chat Memory` (window 10) se lo muestra a los sub-agents; Logger `Parse mensajes`: `human` + source `triaje` → `rol user / fuente whatsapp`; `ai` + source `triaje_*` (≠ reminder_note/wa_outbound) → `rol assistant / fuente bot` → el panel lo pinta como burbuja "Asiri" (`isBot`), al instante por el tail en vivo (≤1.5 s) y en ≤5 min vía `conversaciones`. Content ≥3 chars, no empieza con `[NOTA INTERNA`/`[ATENCION HUMANA`, no es label de intent → no se filtra. El prefijo `[TRIAJE …]` se ve en el panel (como `[ATENCION HUMANA …]`); chip "Video" con link = 2 cambios chicos en `Parse mensajes` + `detectMedia`, post-piloto. `PG - Delete NO_REPLY` no toca estas filas (content ≠ `[NO_REPLY]`).

Para `escalar_con_texto` NO se inserta la fila `human`: `Sub-Agent Urgencia` corre después y la memoria LangChain escribe el par human/ai (evita duplicado). Solo se inserta `[TRIAJE ESCALADO] <texto_no_resuelto>`.

---

## 7. Logging y aviso pasivo

- **Siempre** (todas las acciones, incluido `escalar` por gate/config/LLM): fila en `triaje_urgencias_log` con `modo` (de `triaje_config.modo`, 'piloto'), `accion` ∈ `escalado|video|pregunta|cerrado`, `tipo`, `confianza`, `razon`, `modelo`, `gate_red_flags` (`["gate:…"]`), `gate_escala`, `video_enviado` (URL), `opcion_enviada`, `paso_previo`, `estado_origen` (redis|memoria|ninguno), `motivo_decision` (`gate_red_flags`, `tipo_sin_video:bracket_suelto`, `sin_mas_opciones`, `post_video_cerrar`, `config_inactiva`, `fuera_de_piloto`, `reclasificacion_no_alta`, …), `exec_id` = id de la ejecución del v6, `envio_ok` (se marca true solo tras entrega confirmada), `chat_history_id`. `escalacion_id` queda NULL en las escalaciones vía sub-agent (el Helper escribe su propia fila después; correlación por `telefono + created_at`, como hace la sombra).
- **Aviso pasivo (decisión 2 del 2/9)**: NO se usa `POST /webhook/notify-grupo?silencioso=true` — verificado que en `Helper - Notify Grupo` `Chatwoot Apply` corre SIEMPRE (label `humano`) y eso silenciaría al bot justo cuando necesita recibir "no me sirvió". El aviso pasivo es la fila `accion='video'` en `triaje_urgencias_log` (base del scoring semanal del Reportero: nodo `Query Triaje Semana` + `Resumir Urgencias`, pendiente) y, opcionalmente, con `triaje_config.aviso_escalaciones_log=true`, una fila en `escalaciones_log` `origen='triaje'`, motivo `[TRIAJE VIDEO] Urgencia atendida con video (alambre_pincha, Opcion 1) — sin intervencion humana. Tel …` **enlazada** por `escalacion_id` (CTE), lo que evita que el satélite sombra la reprocese (su `NOT EXISTS … escalacion_id = e.id`). Default **false** en el piloto porque `/aprendizaje` la clasificaría como `senal` y `/dashboard` la contaría como escalación; activar solo junto con `lib/escalaciones.ts` (`RE_TRIAJE = /^\[triaje/i` → tipo propio) y `create_reportero_semanal.py::CLASIFICAR_CODE`.
- `console.log('[TRIAJE] …')` en `Decidir` para rastrear en la ejecución (patrón `[BANLIST TRIGGERED]`).

---

## 8. Manejo de errores / fail-closed (qué recibe el paciente)

| Falla | Nodo | Qué pasa |
|---|---|---|
| Redis GET falla | `Triaje: Redis GET estado` (continueRegularOutput) | estado = reconstrucción desde ctx o "nuevo"; si el estado real era video_enviado, la memoria lo reconstruye. (Redis caído mata la ejecución antes, en `Buffer: Push Mensaje`.) |
| Tabla ausente / SELECT falla / 0 filas / `activo=false` / teléfono fuera de `telefonos_piloto` | `Triaje: Config` → Gate | `decision='escalar'` → `Sub-Agent Urgencia` exacto como hoy; log `motivo_decision=config_*`. |
| Gate detecta red flag (cualquier paso) | Gate | `escalar` sin LLM → Sub-Agent Urgencia. |
| OpenAI 5xx / timeout 20 s / JSON inválido / `choices` vacío | `Clasificar` (neverError+continueRegularOutput) → Decidir | `tipo='error_llm'` → `escalar`. |
| Tipo sin video activo (`bracket_suelto`, `otra_urgencia`, `no_urgencia`, `red_flag`) | Decidir | `escalar` → Sub-Agent Urgencia (comportamiento de hoy). |
| `/send/media` devuelve error, 200 sin `VideoMessage`, timeout 90 s | `Triaje: Video OK?`[1] | Sub-Agent Urgencia escala; log queda `accion='video', envio_ok=false` (visible para revisar); no se escribe memoria ni Redis. |
| `/send/text` (pregunta / texto pre-escalación) falla | `Triaje: Texto OK?`[1] | Sub-Agent Urgencia escala. |
| `/send/text` del texto de salida falla tras video OK, o del cierre | `Texto OK?` tolera (`accion in video,cerrar`) | Se persiste igual (el paciente ya tiene el video / no necesita más); el caption del video ya contiene la instrucción "respondé no me sirvió". |
| INSERT log falla | `Triaje: Log` (continueRegularOutput) | Flujo sigue; `Memoria + Log OK` recibe `$1=0` (UPDATE sin efecto). |
| INSERT memoria falla | `Memoria + Log OK` (continueRegularOutput) | Redis igual se setea; el seguimiento se reconoce por Redis (2 h) aunque el Router no vea el marcador (riesgo: Router → consulta_general → General/[NO_REPLY]; ver failure_modes). |
| Redis SET falla | continueRegularOutput | Estado vive en memoria (reconstrucción). |
| Seguimiento post-video no reconocido por regex | Gate → `escalar_con_texto` | Paciente recibe `texto_no_resuelto` y el caso escala (fail-closed, nunca silencio). |
| Router manda un seguimiento a `consulta_general` | fuera de la rama | Comportamiento de hoy (Sub-Agent General: cierres → `[NO_REPLY]`; preguntas → KB). Mitigado por prompt + marcadores; NO hay capa determinística antes del Router por decisión de blast radius. |
| Label `humano` presente (escalación previa <1 h, reacción de la Dra.) | `Bot Activo?` (antes del Router) | Mensaje muere en `Humano Atendiendo (no hacer nada)`: sin video, como hoy. |

Sub-Agent Urgencia, cuando escala tras el triaje, ve en memoria `[TRIAJE VIDEO …]` y por el bloque nuevo de su prompt incluye "ya se le envió el video de Opción N" en el `resumen` del grupo; su canned de cierre sigue sujeto al bug preexistente de auto-silencio (§11).

---

## 9. Script `scripts/apply_triaje_fase2_piloto.py` (patrón `apply_canned_sidecar.py`)

1. `from lib_env import env, require`; `api()` con `N8N_API_BASE|N8N_BASE_URL` + `N8N_API_KEY`; `WF_ID = env('N8N_WORKFLOW_V6_ID','O155MqHgOSaNZ9ye')`.
2. `--sql` (o paso previo `scripts/create_triaje_config_tables.py`): DDL+seeds de §5 vía psycopg2; verifica `SELECT count(*) FROM triaje_videos WHERE activo` = 2.
3. `wf = api(GET /workflows/{WF_ID})` **fresco**; `wf_orig = deepcopy(wf)`.
4. `build(wf)` puro: asserts `conns['Switch sobre Intent']['main'][2] == [{'node':'Sub-Agent Urgencia','type':'main','index':0}]`, `Sub-Agent Urgencia` con exactamente 1 input main, existen `Evolution API - Enviar Mensaje`, `Preparar Mensaje Final`, `Build Router Context`, `Parse Intent`; idempotente por nombre (re-aplicar = actualizar `jsCode`/params conservando id/position). `GATE_JS = open('triaje/gate_red_flags.js').read()`; headers `deepcopy` del nodo Enviar Mensaje. Edición de prompts con ancla `count()==1` + marcador de idempotencia (`CONTINUACION DE TRIAJE DE URGENCIA`, `MENSAJES DE TRIAJE EN TU MEMORIA`) + `difflib` de líneas ±.
5. Preview: lista de nodos nuevos, `unified_diff` de `connections` filtradas a `Switch sobre Intent` + `Triaje: *` + `Sub-Agent Urgencia`, diffs de prompts. Sin `--apply` termina.
6. `--apply`: backup `workflows/history/v6_PRE_triaje_fase2_piloto_<ts>.json` (wf_orig) → assert `next(n for n in new['nodes'] if n['name']=='Webhook - Evolution API')['webhookId']=='evo-webhook-v2'` → `payload = {k: new[k] for k in ('name','nodes','connections','settings','staticData') if k in new}`; `payload['settings'] = {k:v for k,v in new['settings'].items() if k in SETTINGS_OK}` (filtra `availableInMCP`, `binaryMode`) → PUT → GET → backup POST → verificación: 15 nodos `Triaje: *` presentes, `Switch sobre Intent`.main[2][0].node == `Triaje: Redis GET estado`, `Triaje: Switch Accion`.main[0][0].node == `Sub-Agent Urgencia`, marcadores en ambos prompts, `webhookId` preservado, `active == True`; `sys.exit` si falla.
7. Actualizar `prompts/v6_partials/urgencia_funcion.md` con el bloque nuevo (si no, `build_prompts_v6.py --check` reporta drift y un `--apply` futuro lo pisa).
8. `triaje_config.activo` queda **false** tras el PUT: se prende con `UPDATE triaje_config SET activo=true, telefonos_piloto='{5491161461034}'` cuando Lucas dé el OK a la demo.

Tests previos al PUT: `node triaje/test_gate.js` (29/29); `tests/test_triaje_gate_preparar.py` y `tests/test_triaje_decidir.py` (harness `AsyncFunction` con mocks de `$input`/`$()`/`$execution`, mismo patrón que `tests/test_canned_sidecar.py`) cubriendo: nuevo+alta→video1; nuevo+media→pregunta; pregunta+"sí"+alta→video1; video1+"sigue pinchando"→video2; video2+"no sirvió"→escalar_con_texto; video1+"listo gracias"→cerrar; video1+"me golpeé y sangra mucho"→escalar (gate); sin Redis pero ctx con marcador→estado reconstruido; ctx con `[TRIAJE CIERRE]` después→sin estado; config vacía→escalar; teléfono fuera de piloto→escalar; `error_llm`→escalar; `tests/test_triaje_textos_banlist.py`.

---

## 10. Cómo dejar limpio el número de Lucas (5491161461034) para la demo

Estado conocido: Chatwoot contacto id 1 / conv 272 quedó en `['bot']` el 3/9 23:00:53Z (Auto Reactivar exec 270042); memoria con fila 5912 (`wa_outbound`, reacción de la Dra. 2/9) + recordatorios de prueba; escalaciones_log 189/190.
1. **Chatwoot** (lo único que bloquea determinísticamente): `GET /api/v1/accounts/1/contacts/1/conversations` → toda conversación (cualquier status) con label `humano` → `POST /api/v1/accounts/1/conversations/<id>/labels {"labels":["bot"]}` (o `python scripts/remove_humano_label.py`). No poner `no_bot`.
2. **Memoria** (con OK de Lucas): `DELETE FROM n8n_chat_histories WHERE session_id = '5491161461034';` — mínimo las filas `source IN ('wa_outbound','human_takeover')` (id 5912), que `Clear Old Memory` nunca borra y cuyo TAG pide silencio al LLM. Opcional para el panel: `DELETE FROM conversaciones WHERE telefono='5491161461034'`.
3. **Redis**: `DEL chat_buffer:5491161461034`, `DEL ratelimit:5491161461034`, `DEL triaje:5491161461034`; verificar `GET bot:status` ≠ `disabled` y `GET dentalink:status` ≠ `down`.
4. **Config**: `UPDATE triaje_config SET activo=true, telefonos_piloto='{5491161461034}';`
5. **Durante la demo**: nadie escribe ni **reacciona** desde el celular del consultorio ni desde Chatwoot en ese chat (una reacción = label humano 1 h + fila en memoria); mensajes de Lucas separados ≥25 s (buffer de 22 s) y ≤10 en 15 min; escribir desde el celular de Lucas al número de la clínica (fromMe=false; los admins solo son especiales para `/bot …`).
6. **Después de cada escalación en la demo** (mensaje 3 abajo): el Helper aplica label `humano` → repetir paso 1 y `DEL triaje:5491161461034` antes de seguir. Limpieza post-demo: filas de `triaje_urgencias_log`, `escalaciones_log`, `n8n_chat_histories`, `conversaciones` del teléfono.
7. Alternativa: cualquier otro número real (Irina 5493885786946 o un chip de prueba) agregado a `telefonos_piloto`; mismo checklist.

### Guion de demo (5 mensajes)
1. "hola, se me salió el alambre de atrás y me pincha el cachete" → ~25 s después: **video Opción 1** con caption canned + texto de salida. Panel: 3 burbujas nuevas (user + 2 Asiri). `triaje_urgencias_log`: `accion=video, opcion_enviada=1, envio_ok=true`. Redis `triaje:549…` paso video_enviado.
2. "sigue pinchando igual" → Router `urgencia_dolor` (regla de continuación) → Gate: estado video_enviado + `RE_NO_SIRVIO` → **video Opción 2** + salida. Log `opcion_enviada=2`.
3. "no, sigue igual, no hay caso" → `escalar_con_texto`: paciente recibe `texto_no_resuelto`; `Sub-Agent Urgencia` escala (WhatsApp `[ESCALADO BOT] …ya se le envió el video de Opción 2…` al grupo `120363407321448469@g.us`, label humano). Log `accion=escalado, motivo_decision=sin_mas_opciones`. (Limpiar label + Redis antes del 4.)
4. "se me volvió a salir el alambre y pincha" → video Opción 1 (caso nuevo: memoria terminó en `[TRIAJE ESCALADO]`/canned → sin estado).
5. "listo gracias, ya me puse la cera" → Router `urgencia_dolor` (few-shot de cierre) → Gate: `RE_CIERRE` → **texto de cierre** canned, `[TRIAJE CIERRE]` en memoria, Redis paso cerrado, log `accion=cerrado`. Después de esto, "hola, cuánto sale la consulta?" → Router `consulta_general` normal (último BOT = `[TRIAJE CIERRE]`).
Extras si sobra tiempo: "me golpeé la boca y me sangra mucho" → escalación directa por gate (sin LLM, sin video); "creo que algo del aparato me molesta" → pregunta guiada → "sí, el de atrás" → video Opción 1.

---

## 11. Rollback

- **Nivel 0 (sin PUT, <10 s)**: `UPDATE triaje_config SET activo=false;` → `Gate + Preparar` devuelve `escalar` para todo (`motivo config_inactiva`) → `Sub-Agent Urgencia` como hoy. Solo quedan 2 lecturas baratas (Redis GET + SELECT) delante del sub-agent.
- **Nivel 1 (PUT)**: `python scripts/apply_triaje_fase2_piloto.py --rollback workflows/history/v6_PRE_triaje_fase2_piloto_<ts>.json` → GET fresco → reemplaza `nodes`/`connections`/prompts por los del backup PRE (assert `webhookId`, settings filtrados) → PUT → backup POST. Deja las tablas (inofensivas) y las filas `[TRIAJE …]` en memoria (se van a los 7 días; si molestan: `DELETE FROM n8n_chat_histories WHERE message->'additional_kwargs'->>'source' LIKE 'triaje%'`).
- Ambos niveles no tocan `Recordatorios`, satélites ni el Logger.

---

## 12. Cambios fuera del v6 que este diseño deja anotados (no bloqueantes del piloto)
- Bug preexistente **auto-silencio post-escalación** (6/6 desde el 30/8): el canned de `Sub-Agent Urgencia` no llega a pacientes con contacto en Chatwoot porque `escalar_a_secretaria` aplica el label y `Re-check Humano` lo detecta 1.4 s después. El triaje lo esquiva en sus propios casos (`texto_no_resuelto` sale ANTES de escalar), pero las escalaciones de primer mensaje (red flag, tipos sin video) siguen igual que hoy. Fix aparte P1: ignorar en `Hay humano ahora?`/`Gate Humano Final` el label aplicado por la propia ejecución.
- Satélite sombra: agregar a `QUERY_NUEVAS` `AND NOT EXISTS (SELECT 1 FROM triaje_urgencias_log t WHERE t.telefono = e.telefono AND t.modo <> 'sombra' AND t.created_at BETWEEN e.created_at - interval '3 min' AND e.created_at + interval '3 min')` para no duplicar en modo sombra los casos ya triados en vivo.
- Reportero: `Query Triaje Semana` + `Resumir Urgencias` (scoring pedido el 15/8).
- Panel: chip de video (`Parse mensajes` + `detectMedia`), vista para editar `triaje_videos` con `chequearBanlist`, y `RE_TRIAJE` en `lib/escalaciones.ts` antes de activar `aviso_escalaciones_log`.