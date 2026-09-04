# Triaje de urgencias con video — Fase 2 (piloto alambre_pincha) como producto configurable por tabla, con seguimiento determinístico por Redis y fail-closed a la escalación actual

Se inserta una "columna vertebral" de 18 nodos con prefijo `Triaje: ` en el v6, con DOS puntos de entrada que convergen en la misma cadena: (A) `Switch sobre Intent`[2] → `Triaje: Cargar Config` (mensaje nuevo con intent urgencia_dolor) y (B) `Es cierre?`[1] → `Triaje: Redis GET estado` → `Triaje: ¿Seguimiento?` (mensaje siguiente del mismo teléfono con estado `triaje:{phone}` vigente; si no hay estado sigue al Router exactamente como hoy). El seguimiento se decide ANTES del Router porque el relevamiento demostró que el Router no tiene ninguna regla de continuación para urgencia y manda "listo gracias" / "no tengo cera" / "y si no tengo pinza?" a consulta_general (riesgo clase Mariela vía Sub-Agent General + KB). Toda la config vive en 2 tablas Supabase (`triaje_config` singleton con kill-switch/modo/allow-list piloto/regexes/red flags extra/TTLs, y `triaje_videos` con tipo/opción/url/caption/pregunta/salida/activo); n8n las lee en UN SELECT por urgencia y 0 filas o `activo=false` = escalar como hoy. El LLM (gpt-5-mini vía httpRequest, JSON) solo clasifica tipo/confianza/razón; todo texto al paciente es canned de la tabla, enviado por `/send/media` y `/send/text` directos (no pasan por Formatting Agent), y se persiste a mano en `n8n_chat_histories` (fila human + fila ai con tag `[VIDEO ENVIADO — tipo, Opción N]`) para que Router, sub-agents, Logger y panel lo vean. Log rico en `triaje_urgencias_log` (modo/accion/tipo/confianza/opcion/video/exec_id) y aviso pasivo como fila en `escalaciones_log` con `origen='triaje_video'` insertada DIRECTO (nunca vía notify-grupo, que aplica label humano y silenciaría el seguimiento). Cualquier error (config, LLM, Evolution, Postgres, Redis) converge en `Triaje: Preparar Escalada` → `Triaje: Log Escalado` → `Sub-Agent Urgencia` sin cambios. Sub-Agent Urgencia queda intacto como destino de escalación; solo se le agrega un párrafo de prompt (segunda capa) y otro al Router. Incluye DDL + seeds, script de aplicación con GET fresco/diff/backup/assert webhookId, limpieza del número de Lucas, guion de demo de 5 mensajes y plan de tests E2E.

# Triaje de urgencias con video — Fase 2 (piloto) — Diseño a nivel de nodos n8n

Fuente verificada: `workflows/current/v6_LIVE.json` (`updatedAt 2026-09-04T13:22:48Z`, 125 nodos). Todo índice/expresión citado abajo fue chequeado contra ese JSON (Switch sobre Intent[2] → Sub-Agent Urgencia único input; Es cierre?[1] → Router único input del Router; Sub-Agent Urgencia[0] → Fallback Output; Redis cred `kdtSKwGbN1xAZeUh`; Postgres cred `TpYhZX4UT61xAKSV`; OpenAI cred `nYujqfon7GGDnJUO`; patrón httpRequest Evolution 4.2 con headers apikey (valor omitido) + Content-Type).

## 0. Principios (producto vendible)

1. **Config = datos, no n8n.** Prender/apagar el triaje, un tipo, una opción de video, cambiar textos, agregar red flags extra, limitar a teléfonos piloto: todo con UPDATE en Supabase. n8n lee en UN SELECT por urgencia.
2. **Fail-closed a lo que ya existe.** Cualquier cosa rara → `Sub-Agent Urgencia` como hoy (escala + canned). El paciente nunca queda sin respuesta.
3. **LLM solo clasifica (JSON).** Todo lo que ve el paciente en la rama nueva sale de `triaje_videos`/`triaje_config`. Nada de la rama nueva pasa por Formatting Agent (LLM). Lo que sí genera un LLM (Sub-Agent Urgencia) sigue por Fallback Output → Banlist → etc., intacto.
4. **Seguimiento determinístico.** Estado por teléfono en Redis (`triaje:{phone}`) con TTL; se chequea ANTES del Router; si no hay estado, el flujo es bit a bit el de hoy.
5. **Un solo punto de convergencia por salida**: video/pregunta → `Triaje: Persistir` (terminal); cierre → `Fallback Output`; escalar → `Triaje: Preparar Escalada` → `Sub-Agent Urgencia`.
6. **Nombres con prefijo `Triaje: `**, ids slug `triaje-*`, posiciones en una banda propia (y ≈ 900–1400) para que en la UI se vea como un bloque.

## 1. Dónde se bifurca (2 puntos, 1 columna vertebral)

| # | Conexión actual (verificada) | Nueva |
|---|---|---|
| A | `Switch sobre Intent` main[2] (outputKey `urgencia`, `$json.intent == 'urgencia_dolor'`) → `Sub-Agent Urgencia` in 0 | `Switch sobre Intent` main[2] → **`Triaje: Cargar Config`** in 0 |
| B | `Es cierre?` main[1] (skip=false) → `Router - Clasificar Intent` in 0 | `Es cierre?` main[1] → **`Triaje: Redis GET estado`** in 0 → `Triaje: ¿Seguimiento?` → [1 false] `Router - Clasificar Intent` (idéntico a hoy) / [0 true] `Triaje: Cargar Config` in 0 |
| — | `Sub-Agent Urgencia` in 0 recibe de Switch | `Sub-Agent Urgencia` in 0 recibe SOLO de **`Triaje: Log Escalado`** |

**Por qué B va antes del Router y no dentro del camino urgencia** (pedido explícito del objetivo): el relevamiento del Router muestra que no existe ninguna regla/few-shot de continuación para urgencia, que "cierres/post-escalación → consulta_general" y "ante DUDA → consulta_general" empujan en contra, y que "y si no tengo pinza?" cae por Regla 0 en consulta_general → Sub-Agent General PASO 3 → `buscar_conocimiento` → consejo LLM (el Banlist no cubre cera/pinza/colocá). Chequear Redis antes del Router hace que el seguimiento post-video sea 100% determinístico mientras el estado vive; el prompt del Router queda como segunda capa para cuando el TTL venció. Costo: 1 `GET` Redis por mensaje (Redis ya es requisito duro: `Rate Limit INCR` corre antes en todo mensaje) + 1 IF. Con key ausente el camino es exactamente el de hoy.

Los gates previos (kill-switch, Dentalink, rate limit, fromMe, buffer 22 s, `Bot Activo?` por label humano, stale memory, `Pre-filtro Cierre`) quedan intactos y corren ANTES de ambos puntos. En particular: si hay label `humano` el seguimiento muere en `Humano Atendiendo (no hacer nada)` como hoy (correcto: un humano tomó el chat).

## 2. Nodos nuevos (18) — nombre, tipo/typeVersion, parámetros, onError

Convención de expresiones: solo `$('Nodo').first().json.X` sobre nodos que están CONECTADOS aguas arriba en el mismo camino (lección "No path back"); referencias a nodos que pueden no haber corrido siempre dentro de `try/catch` en Code (patrón Canned Sidecar, en producción).

### 2.1 `Triaje: Redis GET estado` — `n8n-nodes-base.redis` v1, cred Redis `kdtSKwGbN1xAZeUh`
```json
{"operation":"get","propertyName":"triaje_estado","key":"={{ 'triaje:' + $('Preparar Mensaje Final').first().json.phone }}","keyType":"string","options":{}}
```
`onError: continueRegularOutput`, `alwaysOutputData: true`. Key ausente → `triaje_estado` null → camino normal. Redis caído → error tolerado → camino normal (el bot ya estaría muerto antes en `Rate Limit INCR`, así que en la práctica no cambia nada).

### 2.2 `Triaje: ¿Seguimiento?` — `n8n-nodes-base.if` v2 (typeValidation loose)
Condición: `={{ $json.triaje_estado || '' }}` string `notEmpty`. Out 0 (true) → `Triaje: Cargar Config`; out 1 (false) → `Router - Clasificar Intent`.

### 2.3 `Triaje: Cargar Config` — `n8n-nodes-base.postgres` v2.5, cred `TpYhZX4UT61xAKSV`
Dos entradas main (Switch[2] y ¿Seguimiento?[0]; n8n lo permite, como `Fallback Output` con 7). `onError: continueRegularOutput`, `alwaysOutputData: true`. Query literal (sin `=`):
```sql
SELECT c.activo AS triaje_activo, c.modo, c.telefonos_piloto, c.red_flags_extra,
       c.regex_no_sirvio, c.regex_cierre, c.texto_cierre, c.aviso_pasivo,
       c.ttl_video_seg, c.ttl_pregunta_seg, c.modelo,
       COALESCE((SELECT jsonb_agg(jsonb_build_object(
                  'id', v.id, 'tipo', v.tipo, 'opcion', v.opcion, 'url', v.url, 'filename', v.filename,
                  'caption', v.caption, 'pregunta_guiada', v.pregunta_guiada,
                  'texto_salida_emergencia', v.texto_salida_emergencia) ORDER BY v.tipo, v.opcion)
                 FROM triaje_videos v WHERE v.activo AND v.url IS NOT NULL), '[]'::jsonb) AS videos
FROM triaje_config c WHERE c.id = 1;
```
0 filas / error → `Triaje: Evaluar` ve `triaje_activo` ≠ true → escalar (modo nuevo) o defaults hardcodeados (modo seguimiento). Nota: `jsonb` vuelve como objeto JS ya parseado en el nodo Postgres v2.5; `Evaluar` acepta string u objeto (`typeof === 'string' ? JSON.parse : x`).

### 2.4 `Triaje: Evaluar` — `n8n-nodes-base.code` v2
Único Code que corre en los dos modos. Embebe `triaje/gate_red_flags.js` tal cual (fuente única, 29/29 tests) + wrapper. Esbozo:
```js
// ===== GATE_JS (contenido literal de triaje/gate_red_flags.js, con su module.exports guard) =====
const SYSTEM_PROMPT = /* json.dumps del prompt de clasificación, ver 2.6 */;
const DEFAULTS = {
  regex_no_sirvio: "(no\\s+(me\\s+)?(sirvi[oó]|funcion[oó]|ayud[oó]|result[oó]|pude|puedo|tengo|consegu[ií]|anda|entra|queda)|sigue|igual|peor|todav[ií]a|a[uú]n|no\\s+mejor|no\\s+alcanz|sin\\s+cera|no\\s+hay\\s+cera|se\\s+vuelve\\s+a\\s+salir|se\\s+sale)",
  regex_cierre: "^\\s*(listo|ok|oka|dale|gracias|graci|perfecto|buen[ií]simo|genial|joya|excelente|ya\\s+(me\\s+)?(la\\s+)?puse|ya\\s+est[aá]|ya\\s+(me\\s+)?qued[oó]|mejor[oó]|me\\s+sirvi[oó]|funcion[oó]|solucion|resuelto|muchas\\s+gracias|mil\\s+gracias)",
  ttl_video_seg: 7200, ttl_pregunta_seg: 1800, modelo: 'gpt-5-mini', texto_cierre: '[NO_REPLY]'
};
const row = $input.first().json || {};
const parseJ = (x, d) => { try { return typeof x === 'string' ? JSON.parse(x) : (x ?? d); } catch (e) { return d; } };
const cfg = {
  activo: row.triaje_activo === true, modo: row.modo || 'piloto',
  telefonos_piloto: parseJ(row.telefonos_piloto, []) || [],
  red_flags_extra: parseJ(row.red_flags_extra, []) || [],
  regex_no_sirvio: row.regex_no_sirvio || DEFAULTS.regex_no_sirvio,
  regex_cierre: row.regex_cierre || DEFAULTS.regex_cierre,
  texto_cierre: row.texto_cierre || DEFAULTS.texto_cierre,
  aviso_pasivo: row.aviso_pasivo !== false,
  ttl_video_seg: Number(row.ttl_video_seg) || DEFAULTS.ttl_video_seg,
  ttl_pregunta_seg: Number(row.ttl_pregunta_seg) || DEFAULTS.ttl_pregunta_seg,
  modelo: row.modelo || DEFAULTS.modelo,
  videos: parseJ(row.videos, []) || [],
};
const pm = $('Preparar Mensaje Final').first().json;               // siempre conectado aguas arriba
const text = (pm.text || '').trim();
let ctx = ''; try { ctx = $('Build Router Context').first().json.ctx || ''; } catch (e) {}
let estado = null; try { estado = parseJ($('Triaje: Redis GET estado').first().json.triaje_estado, null); } catch (e) {}
let modo_entrada = 'nuevo'; try { void $('Parse Intent').first().json.intent; } catch (e) { modo_entrada = 'seguimiento'; }
const videosDe = (tipo) => cfg.videos.filter(v => v.tipo === tipo).sort((a, b) => a.opcion - b.opcion);
const safeRe = (src, flags) => { try { return new RegExp(src, flags); } catch (e) { return null; } };
const base = { modo_entrada, phone: pm.phone, remoteJid: pm.remoteJid, text, ctx, estado, cfg, exec_id: $execution.id, gate_flags: [], gate_escala: false };
// Capa 0/3: gate determinístico SIEMPRE, en ambos modos (re-evaluación en seguimientos)
const gate = gateRedFlags(text);
for (const src of cfg.red_flags_extra) { const re = safeRe(src, 'iu'); if (re && re.test(text)) gate.flags.push('extra:' + src.slice(0, 24)); }
if (gate.flags.length) return [{ json: { ...base, gate_flags: gate.flags, gate_escala: true, ruta_pre: 'decidido', ruta: 'escalar', razon: 'gate_red_flags' } }];
if (modo_entrada === 'seguimiento') {
  if (!estado || !estado.paso) return [{ json: { ...base, ruta_pre: 'normal' } }];
  const noSirvio = safeRe(cfg.regex_no_sirvio, 'iu') || safeRe(DEFAULTS.regex_no_sirvio, 'iu');
  const cierre = safeRe(cfg.regex_cierre, 'iu') || safeRe(DEFAULTS.regex_cierre, 'iu');
  if (estado.paso === 'pregunta') {
    const user = 'CONTEXTO PREVIO:\n' + ctx + '\n\nMENSAJE ORIGINAL DEL PACIENTE:\n' + (estado.texto_original || '') + '\n\nPREGUNTA GUIADA QUE LE HICIMOS:\n' + (estado.pregunta || '') + '\n\nRESPUESTA DEL PACIENTE:\n' + text;
    const llm_body = JSON.stringify({ model: cfg.modelo, messages: [{ role: 'system', content: SYSTEM_PROMPT }, { role: 'user', content: user }], response_format: { type: 'json_object' } });
    return [{ json: { ...base, ruta_pre: 'clasificar', reclasifica: true, tipo_hint: estado.tipo || null, llm_body } }];
  }
  if (estado.paso === 'video_enviado') {
    if (noSirvio.test(text)) {
      const next = cfg.activo ? videosDe(estado.tipo).find(v => v.opcion === (Number(estado.opcion) || 1) + 1) : null;
      if (next) return [{ json: { ...base, ruta_pre: 'decidido', ruta: 'video', tipo: estado.tipo, confianza: 'alta', video: next, razon: 'no_sirvio_opcion_' + estado.opcion } }];
      return [{ json: { ...base, ruta_pre: 'decidido', ruta: 'escalar', tipo: estado.tipo, razon: 'no_sirvio_sin_mas_opciones' } }];
    }
    if (cierre.test(text)) return [{ json: { ...base, ruta_pre: 'decidido', ruta: 'cerrar', tipo: estado.tipo, razon: 'cierre_post_video' } }];
    return [{ json: { ...base, ruta_pre: 'normal' } }];   // cualquier otra cosa → Router (flujo normal)
  }
  return [{ json: { ...base, ruta_pre: 'normal' } }];
}
// modo nuevo (viene de Switch sobre Intent[2], intent urgencia_dolor)
if (!cfg.activo || cfg.videos.length === 0) return [{ json: { ...base, ruta_pre: 'decidido', ruta: 'escalar', razon: 'triaje_inactivo' } }];
if (cfg.telefonos_piloto.length && !cfg.telefonos_piloto.includes(String(pm.phone))) return [{ json: { ...base, ruta_pre: 'decidido', ruta: 'escalar', razon: 'fuera_piloto' } }];
const user = 'CONTEXTO PREVIO (últimos turnos, puede estar vacío):\n' + (ctx || '(sin contexto)') + '\n\nMENSAJE ACTUAL DEL PACIENTE:\n' + text;
const llm_body = JSON.stringify({ model: cfg.modelo, messages: [{ role: 'system', content: SYSTEM_PROMPT }, { role: 'user', content: user }], response_format: { type: 'json_object' } });
return [{ json: { ...base, ruta_pre: 'clasificar', reclasifica: false, llm_body } }];
```
Notas: el gate corre sobre el `text` mergeado del buffer (varias burbujas en 22 s = un texto) y también en seguimientos (Capa 3). En modo nuevo con estado vigente del mismo tipo (paciente vino por Router porque escribió algo que no matcheó no_sirvio/cierre), `Decidir` escala en vez de re-mandar el mismo video (ver 2.7).

### 2.5 `Triaje: Ruta Pre` — `n8n-nodes-base.switch` v3.2 (strict, `={{ $json.ruta_pre }}` equals)
| out | outputKey | valor | destino |
|---|---|---|---|
| 0 | `clasificar` | `clasificar` | `Triaje: Clasificar (gpt-5-mini)` |
| 1 | `decidido` | `decidido` | `Triaje: Decidir` |
| 2 | `normal` | `normal` | `Router - Clasificar Intent` |
`options.fallbackOutput: "extra"`, `renameFallbackOutput: "fallback"` → out 3 → `Triaje: Preparar Escalada` (fail-closed si Evaluar devolviera algo raro).

### 2.6 `Triaje: Clasificar (gpt-5-mini)` — `n8n-nodes-base.httpRequest` v4.2
Copia exacta del patrón `Banlist Shadow - LLM` (probado en el v6) y del satélite sombra:
```json
{"method":"POST","url":"https://api.openai.com/v1/chat/completions","authentication":"predefinedCredentialType","nodeCredentialType":"openAiApi","sendBody":true,"specifyBody":"json","jsonBody":"={{ $json.llm_body }}","options":{"response":{"response":{"neverError":true}},"timeout":30000}}
```
`credentials: {"openAiApi": {"id":"nYujqfon7GGDnJUO","name":"OpenAi account"}}`, `onError: continueRegularOutput`. `SYSTEM_PROMPT` = el de `scripts/create_test_triaje_webhook.py` con 2 agregados: (a) "Podés recibir CONTEXTO PREVIO de la conversación; usalo solo para entender de qué aparato/problema habla. Si el contexto muestra que YA se le envió un video por el mismo problema, clasificá igual el tipo real." (b) para reclasificación: "Si recibís PREGUNTA GUIADA + RESPUESTA, clasificá combinando el mensaje original y la respuesta; si la respuesta contradice el tipo o es ambigua, bajá la confianza." Categorías y salida `{"tipo","confianza","razon"}` sin cambios.

### 2.7 `Triaje: Decidir` — `n8n-nodes-base.code` v2 (2 entradas: Clasificar[0] y Ruta Pre[1])
```js
const ev = $('Triaje: Evaluar').first().json;               // siempre aguas arriba
const inp = $input.first().json || {};
const cfg = ev.cfg; const d = { ...ev, modelo: cfg.modelo };
const videosDe = (tipo) => (cfg.videos || []).filter(v => v.tipo === tipo).sort((a, b) => a.opcion - b.opcion);
if (ev.ruta_pre === 'clasificar') {
  let tipo = 'error_llm', confianza = 'baja', razon = '';
  try {
    const content = inp.choices[0].message.content;
    const p = JSON.parse(String(content).replace(/^```(json)?|```$/gm, '').trim());
    tipo = String(p.tipo || 'error_llm'); confianza = String(p.confianza || 'baja'); razon = String(p.razon || '').slice(0, 300);
  } catch (e) { razon = 'error_llm: ' + String((inp.error && inp.error.message) || inp.statusCode || e.message).slice(0, 200); }
  Object.assign(d, { tipo, confianza, razon });
  const vids = videosDe(tipo);
  if (['red_flag', 'otra_urgencia', 'no_urgencia', 'error_llm'].includes(tipo) || vids.length === 0) d.ruta = 'escalar';
  else if (ev.estado && ev.estado.paso === 'video_enviado' && ev.estado.tipo === tipo) { d.ruta = 'escalar'; d.razon = 'mismo_problema_post_video'; }
  else if (confianza === 'alta') { d.ruta = 'video'; d.video = vids[0]; }
  else if (!ev.reclasifica && vids[0].pregunta_guiada) { d.ruta = 'pregunta'; d.pregunta = vids[0].pregunta_guiada; }
  else { d.ruta = 'escalar'; d.razon = 'confianza_' + confianza + (ev.reclasifica ? '_post_pregunta' : '_sin_pregunta'); }
}
// ---- payloads canned (texto 100% de tabla) ----
const num = String(ev.remoteJid || '').replace(/[^0-9]/g, '');
const esc = (v) => v === null || v === undefined ? 'NULL' : "'" + String(v).replace(/'/g, "''") + "'";
const memRow = (type, content, kw) => JSON.stringify({ type, content, additional_kwargs: kw, response_metadata: {}, tool_calls: [], invalid_tool_calls: [] });
const humanRow = memRow('human', ev.text, { source: 'triaje_paciente' });
d.send = { number: num };
if (d.ruta === 'video') {
  const v = d.video;
  d.send.url = v.url; d.send.caption = v.caption; d.send.filename = v.filename || (d.tipo + '_opcion' + v.opcion + '.mp4');
  d.send.text = v.texto_salida_emergencia || '';
  d.estado_json = JSON.stringify({ tipo: d.tipo, opcion: v.opcion, paso: 'video_enviado', ts: Date.now(), exec_id: ev.exec_id });
  d.estado_ttl = cfg.ttl_video_seg;
  d.mem_ai = memRow('ai', '[VIDEO ENVIADO — ' + d.tipo + ', Opción ' + v.opcion + '] ' + v.caption + (d.send.text ? '\n' + d.send.text : ''), { source: 'triaje_video', tipo: d.tipo, opcion: v.opcion, video_url: v.url, video_id: v.id });
  d.accion = 'video'; d.video_enviado = d.tipo + '/opcion' + v.opcion; d.opcion_enviada = v.opcion;
  d.motivo_aviso = '[TRIAJE VIDEO] ' + d.tipo + ' Opción ' + v.opcion + ' — atendido con video canned, sin escalar. Paciente: «' + ev.text.slice(0, 160) + '»';
}
if (d.ruta === 'pregunta') {
  d.send.text = d.pregunta;
  d.estado_json = JSON.stringify({ tipo: d.tipo, paso: 'pregunta', pregunta: d.pregunta, texto_original: ev.text, ts: Date.now(), exec_id: ev.exec_id });
  d.estado_ttl = cfg.ttl_pregunta_seg;
  d.mem_ai = memRow('ai', '[TRIAJE — PREGUNTA GUIADA (' + d.tipo + ')] ' + d.pregunta, { source: 'triaje_pregunta', tipo: d.tipo });
  d.accion = 'pregunta'; d.video_enviado = null; d.opcion_enviada = null; d.motivo_aviso = null;
}
if (d.ruta === 'cerrar') {
  d.output_cierre = cfg.texto_cierre || '[NO_REPLY]';
  d.sql_cerrar = "WITH h AS (INSERT INTO n8n_chat_histories(session_id, message) VALUES (" + esc(ev.phone) + ", " + esc(humanRow) + "::jsonb) RETURNING id) " +
    "UPDATE triaje_urgencias_log SET resuelto_at = NOW(), razon_cierre = " + esc(ev.text.slice(0, 200)) + " WHERE id = (SELECT id FROM triaje_urgencias_log WHERE telefono = " + esc(ev.phone) + " AND accion = 'video' AND resuelto_at IS NULL ORDER BY id DESC LIMIT 1) RETURNING id";
}
const flags = JSON.stringify((ev.gate_flags || []).map(f => 'gate:' + f));
const withAviso = d.ruta === 'video' && cfg.aviso_pasivo;
d.sql_persistir =
  "WITH h AS (INSERT INTO n8n_chat_histories(session_id, message) VALUES (" + esc(ev.phone) + ", " + esc(humanRow) + "::jsonb) RETURNING id), " +
  "a AS (INSERT INTO n8n_chat_histories(session_id, message) VALUES (" + esc(ev.phone) + ", " + esc(d.mem_ai || '') + "::jsonb) RETURNING id), " +
  "e AS (INSERT INTO escalaciones_log(telefono, motivo, origen, exec_id) SELECT " + esc(ev.phone) + ", " + esc(d.motivo_aviso) + ", 'triaje_video', " + esc(ev.exec_id) + " WHERE " + (withAviso ? 'true' : 'false') + " RETURNING id) " +
  "INSERT INTO triaje_urgencias_log(escalacion_id, telefono, exec_id, mensaje_paciente, gate_red_flags, gate_escala, tipo, confianza, razon, modelo, modo, accion, video_enviado, opcion_enviada, chat_history_id) " +
  "SELECT (SELECT id FROM e), " + esc(ev.phone) + ", " + esc(ev.exec_id) + ", " + esc(ev.text) + ", " + esc(flags) + "::jsonb, false, " + esc(d.tipo) + ", " + esc(d.confianza) + ", " + esc(d.razon) + ", " + esc(d.modelo) + ", " + esc(cfg.modo) + ", " + esc(d.accion) + ", " + esc(d.video_enviado) + ", " + (d.opcion_enviada ? d.opcion_enviada : 'NULL') + ", (SELECT id FROM a) RETURNING id AS triaje_log_id";
return [{ json: d }];
```
Política de reclasificación (paso pregunta): `alta` → video (3); cualquier otra → escalar (5). Nunca segunda pregunta (spec B).

### 2.8 `Triaje: Ruta` — `n8n-nodes-base.switch` v3.2 (`={{ $json.ruta }}` equals, strict)
| out | outputKey | destino |
|---|---|---|
| 0 | `video` | `Triaje: Enviar Video` |
| 1 | `pregunta` | `Triaje: Enviar Texto Canned` |
| 2 | `cerrar` | `Triaje: Marcar Resuelto` |
| 3 | `fallback` (extra) | `Triaje: Preparar Escalada` ← incluye `ruta:'escalar'` y cualquier valor inesperado |

### 2.9 `Triaje: Enviar Video` — `n8n-nodes-base.httpRequest` v4.2
Clon de `Evolution API - Enviar Mensaje` (el script copia `headerParameters` con `copy.deepcopy` del GET fresco: apikey presente, valor omitido; `credentials: {}`); URL = `params['url'].split('/send/')[0] + '/send/media'`. Body por campo (patrón probado E2E en `ahJzS48esjdmD4GH`):
```
={
  "number": {{ JSON.stringify($('Triaje: Decidir').first().json.send.number) }},
  "type": "video",
  "url": {{ JSON.stringify($('Triaje: Decidir').first().json.send.url) }},
  "caption": {{ JSON.stringify($('Triaje: Decidir').first().json.send.caption) }},
  "filename": {{ JSON.stringify($('Triaje: Decidir').first().json.send.filename) }}
}
```
`options.response.response.neverError: true`, `timeout: 45000`, `onError: continueRegularOutput`. Nunca `continueOnFail` a secas sin chequeo (lección: esconde fallas).

### 2.10 `Triaje: ¿Video OK?` — `n8n-nodes-base.if` v2.2 (strict)
Condición boolean true: `={{ !!($json && $json.data && $json.data.Info && $json.data.Info.ID) }}` (respuesta OK de Evolution GO = `200` con `data.Info.ID`, `data.Info.Type == "VideoMessage"`; confirmar el shape exacto con una respuesta real del test webhook antes del PUT — está guardada en las ejecuciones de `ahJzS48esjdmD4GH`). Out 0 → `Triaje: Enviar Texto Canned`; out 1 → `Triaje: Preparar Escalada`.

### 2.11 `Triaje: Enviar Texto Canned` — `n8n-nodes-base.httpRequest` v4.2 (2 entradas: ¿Video OK?[0], Ruta[1])
Clon de `Evolution API - Enviar Mensaje` (`/send/text`), body:
```
={
  "number": {{ JSON.stringify($('Triaje: Decidir').first().json.send.number) }},
  "text": {{ JSON.stringify($('Triaje: Decidir').first().json.send.text) }}
}
```
En ruta video = `texto_salida_emergencia`; en ruta pregunta = `pregunta_guiada`. `neverError: true`, `timeout: 30000`, `onError: continueRegularOutput`. Va directo (no por `Loop Mensajes`): 1 item, 1 corrida.

### 2.12 `Triaje: ¿Texto OK?` — `n8n-nodes-base.if` v2.2
Misma condición que 2.10. Out 0 → `Triaje: Persistir`; out 1 → `Triaje: Preparar Escalada` (si es ruta video, el paciente ya tiene el video; la escalación le agrega el canned de Urgencia y avisa al grupo: seguro).

### 2.13 `Triaje: Persistir` — `n8n-nodes-base.postgres` v2.5, cred `TpYhZX4UT61xAKSV`
`query: ={{ $('Triaje: Decidir').first().json.sql_persistir }}`, `onError: continueRegularOutput`, `alwaysOutputData: true`. Un solo statement atómico (CTE): fila `human` + fila `ai` en `n8n_chat_histories`, fila de aviso pasivo en `escalaciones_log` (solo video y si `aviso_pasivo`), fila en `triaje_urgencias_log` con `escalacion_id` apuntando al aviso (así el satélite sombra la ve como ya procesada por su `NOT EXISTS`). Devuelve `triaje_log_id`.

### 2.14 `Triaje: Redis SET estado` — `n8n-nodes-base.redis` v1 (terminal)
```json
{"operation":"set","key":"={{ 'triaje:' + $('Preparar Mensaje Final').first().json.phone }}","value":"={{ (() => { const e = JSON.parse($('Triaje: Decidir').first().json.estado_json); e.log_id = $json.triaje_log_id || null; return JSON.stringify(e); })() }}","keyType":"string","expire":true,"ttl":"={{ $('Triaje: Decidir').first().json.estado_ttl }}"}
```
`onError: continueRegularOutput` (si Redis falla, el seguimiento cae en la segunda capa: el Router con la fila `[VIDEO ENVIADO —` en ctx + regla nueva del prompt). Va DESPUÉS de Persistir para poder guardar `log_id`.

### 2.15 `Triaje: Marcar Resuelto` — `n8n-nodes-base.postgres` v2.5
`query: ={{ $('Triaje: Decidir').first().json.sql_cerrar }}` (CTE: guarda el mensaje del paciente en memoria + `UPDATE triaje_urgencias_log SET resuelto_at ... RETURNING id`), `onError: continueRegularOutput`, `alwaysOutputData: true`.

### 2.16 `Triaje: Cerrar` — `n8n-nodes-base.set` v3.4 → `Fallback Output` in 0
`assignments: [{name:'output', type:'string', value: "={{ $json.id ? $('Triaje: Decidir').first().json.output_cierre : '[NO_REPLY]' }}"}]`. Si ya estaba resuelto (UPDATE 0 filas) → `[NO_REPLY]` (no repetir el canned de cierre ante "gracias" x3). Hereda toda la cola actual (Sidecar/Gate Pago passthrough por try/catch → intent '', Banlist, Re-check Humano, Formatting si >80 chars — el texto_cierre seed tiene <80 chars y no lleva `---`, Gate Humano Final, `PG - Delete NO_REPLY`). El estado Redis NO se borra a propósito: si 10 min después dice "sigue pinchando", va a Opción 2; expira por TTL.

### 2.17 `Triaje: Preparar Escalada` — `n8n-nodes-base.code` v2 (entradas: Ruta[3], ¿Video OK?[1], ¿Texto OK?[1], Ruta Pre[3])
```js
let d = null; try { d = $('Triaje: Decidir').first().json; } catch (e) {}
let ev = null; try { ev = $('Triaje: Evaluar').first().json; } catch (e) {}
const src = d || ev || {};
const pm = $('Preparar Mensaje Final').first().json;
const inp = $input.first().json || {};
let razon = src.razon || 'sin_razon';
if (src.ruta === 'video' || src.ruta === 'pregunta') razon = 'envio_fallo_' + src.ruta + ': ' + String((inp.error && inp.error.message) || inp.message || inp.statusCode || JSON.stringify(inp)).slice(0, 150);
const cfg = src.cfg || {}; const esc = (v) => v == null ? 'NULL' : "'" + String(v).replace(/'/g, "''") + "'";
const flags = JSON.stringify((src.gate_flags || []).map(f => 'gate:' + f));
const sql = "INSERT INTO triaje_urgencias_log(telefono, exec_id, mensaje_paciente, gate_red_flags, gate_escala, tipo, confianza, razon, modelo, modo, accion, video_enviado, opcion_enviada) VALUES (" +
  [esc(pm.phone), esc($execution.id), esc(pm.text), esc(flags) + '::jsonb', src.gate_escala ? 'true' : 'false', esc(src.tipo || null), esc(src.confianza || null), esc(razon), esc(src.modelo || null), esc(cfg.modo || 'live'), "'escalado'", esc((src.estado && src.estado.tipo) ? src.estado.tipo + '/opcion' + (src.estado.opcion || '') : null), (src.estado && src.estado.opcion) ? src.estado.opcion : 'NULL'].join(', ') + ") RETURNING id";
console.log('[TRIAJE] escalar', pm.phone, razon);
return [{ json: { triaje_escalada: true, razon_escalada: razon, sql } }];
```

### 2.18 `Triaje: Log Escalado` — `n8n-nodes-base.postgres` v2.5 → `Sub-Agent Urgencia` in 0
`query: ={{ $json.sql }}`, `onError: continueRegularOutput`, `alwaysOutputData: true`. Pase lo que pase, `Sub-Agent Urgencia` corre (su `text` es `$('Preparar Mensaje Final').first().json.text`, no depende del item que recibe).

## 3. Conexiones (nuevas y modificadas, con índices)

Modificadas:
- `Es cierre?`.main[1]: `[{Router - Clasificar Intent,0}]` → `[{Triaje: Redis GET estado,0}]`
- `Switch sobre Intent`.main[2]: `[{Sub-Agent Urgencia,0}]` → `[{Triaje: Cargar Config,0}]`

Nuevas:
```
Triaje: Redis GET estado.main[0]   → Triaje: ¿Seguimiento? (0)
Triaje: ¿Seguimiento?.main[0]      → Triaje: Cargar Config (0)
Triaje: ¿Seguimiento?.main[1]      → Router - Clasificar Intent (0)
Triaje: Cargar Config.main[0]      → Triaje: Evaluar (0)
Triaje: Evaluar.main[0]            → Triaje: Ruta Pre (0)
Triaje: Ruta Pre.main[0] clasificar→ Triaje: Clasificar (gpt-5-mini) (0)
Triaje: Ruta Pre.main[1] decidido  → Triaje: Decidir (0)
Triaje: Ruta Pre.main[2] normal    → Router - Clasificar Intent (0)
Triaje: Ruta Pre.main[3] fallback  → Triaje: Preparar Escalada (0)
Triaje: Clasificar (gpt-5-mini).main[0] → Triaje: Decidir (0)
Triaje: Decidir.main[0]            → Triaje: Ruta (0)
Triaje: Ruta.main[0] video         → Triaje: Enviar Video (0)
Triaje: Ruta.main[1] pregunta      → Triaje: Enviar Texto Canned (0)
Triaje: Ruta.main[2] cerrar        → Triaje: Marcar Resuelto (0)
Triaje: Ruta.main[3] fallback      → Triaje: Preparar Escalada (0)
Triaje: Enviar Video.main[0]       → Triaje: ¿Video OK? (0)
Triaje: ¿Video OK?.main[0]         → Triaje: Enviar Texto Canned (0)
Triaje: ¿Video OK?.main[1]         → Triaje: Preparar Escalada (0)
Triaje: Enviar Texto Canned.main[0]→ Triaje: ¿Texto OK? (0)
Triaje: ¿Texto OK?.main[0]         → Triaje: Persistir (0)
Triaje: ¿Texto OK?.main[1]         → Triaje: Preparar Escalada (0)
Triaje: Persistir.main[0]          → Triaje: Redis SET estado (0)      [terminal]
Triaje: Marcar Resuelto.main[0]    → Triaje: Cerrar (0)
Triaje: Cerrar.main[0]             → Fallback Output (0)
Triaje: Preparar Escalada.main[0]  → Triaje: Log Escalado (0)
Triaje: Log Escalado.main[0]       → Sub-Agent Urgencia (0)
```
Sin tocar: conexiones `ai_languageModel`/`ai_tool`/`ai_memory` de `Sub-Agent Urgencia`; `Sub-Agent Urgencia`.main[0] → `Fallback Output`; todo lo demás.

Nota de ejecución: en el camino `Ruta Pre[normal] → Router → ... → Switch[2] → Cargar Config`, `Triaje: Cargar Config`/`Evaluar` corren 2 veces en la misma ejecución; `$('Triaje: Evaluar').first()` devuelve la corrida más reciente (n8n usa el último runIndex por defecto). `Evaluar` detecta `modo_entrada` por `$('Parse Intent')` (solo existe si pasó por Router), así que la 2ª corrida es modo nuevo, y `Decidir` escala si el tipo coincide con un `video_enviado` vigente (no re-manda el mismo video).

## 4. Estado Redis

- Key: `triaje:{phone}` (mismo `phone` LID-safe de `Preparar Mensaje Final` = session_id de memoria = telefono de los logs). Convención `<namespace>:<phone>` como `chat_buffer:`/`ratelimit:`.
- Shape (string JSON): `{"tipo":"alambre_pincha","opcion":1,"paso":"video_enviado","ts":1788500000000,"exec_id":"270999","log_id":123}` o `{"tipo":"alambre_pincha","paso":"pregunta","pregunta":"…","texto_original":"…","ts":…,"exec_id":…,"log_id":…}`.
- TTL: `ttl_video_seg` (seed 7200 = 2 h) / `ttl_pregunta_seg` (seed 1800 = 30 min). Cada SET pisa el anterior (Opción 2 renueva 2 h).
- Transiciones: `pregunta` → (reclasifica alta) `video_enviado/1` | (otra) sin estado nuevo → escalar (queda hasta TTL; inofensivo: label humano bloquea antes). `video_enviado/1` → no_sirvio → `video_enviado/2` | cierre → estado intacto + `resuelto_at` en DB | otra → Router. `video_enviado/2` → no_sirvio → escalar; cierre → cerrar; otra → Router.
- Limpieza manual: `DEL triaje:5491161461034`. Kill-switch de datos: `UPDATE triaje_config SET activo=false` (los seguimientos con estado siguen resolviéndose: no_sirvio → escalar porque `cfg.activo=false` anula Opción 2).

## 5. Tablas de configuración (DDL + seeds) — `scripts/create_triaje_config_tables.py` (psycopg2, mismo patrón que `create_triaje_urgencias_log_table.py`, idempotente, correr ANTES del PUT)

```sql
-- Config global (fila única). Molde: recordatorios_config. RLS on (service_role/pooler bypassean).
CREATE TABLE IF NOT EXISTS public.triaje_config (
  id               smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  activo           boolean NOT NULL DEFAULT false,          -- kill-switch maestro: false => todo escala como hoy
  modo             text NOT NULL DEFAULT 'piloto' CHECK (modo IN ('sombra','piloto','live')),  -- se copia a triaje_urgencias_log.modo
  telefonos_piloto text[] NOT NULL DEFAULT '{}',            -- allow-list; vacío = todos los pacientes
  red_flags_extra  text[] NOT NULL DEFAULT '{}',            -- regex extra (flags iu) que se suman al gate_red_flags.js
  regex_no_sirvio  text NOT NULL DEFAULT '(no\s+(me\s+)?(sirvi[oó]|funcion[oó]|ayud[oó]|result[oó]|pude|puedo|tengo|consegu[ií]|anda|entra|queda)|sigue|igual|peor|todav[ií]a|a[uú]n|no\s+mejor|no\s+alcanz|sin\s+cera|no\s+hay\s+cera|se\s+vuelve\s+a\s+salir|se\s+sale)',
  regex_cierre     text NOT NULL DEFAULT '^\s*(listo|ok|oka|dale|gracias|graci|perfecto|buen[ií]simo|genial|joya|excelente|ya\s+(me\s+)?(la\s+)?puse|ya\s+est[aá]|ya\s+(me\s+)?qued[oó]|mejor[oó]|me\s+sirvi[oó]|funcion[oó]|solucion|resuelto|muchas\s+gracias|mil\s+gracias)',
  texto_cierre     text NOT NULL DEFAULT 'Buenísimo, gracias por avisar. Si vuelve a molestar, escríbanos por acá.',
  aviso_pasivo     boolean NOT NULL DEFAULT true,           -- fila en escalaciones_log (origen triaje_video) por cada video enviado
  ttl_video_seg    integer NOT NULL DEFAULT 7200,
  ttl_pregunta_seg integer NOT NULL DEFAULT 1800,
  modelo           text NOT NULL DEFAULT 'gpt-5-mini',
  updated_at       timestamptz NOT NULL DEFAULT now(),
  updated_by       text
);
INSERT INTO public.triaje_config (id, updated_by) VALUES (1, 'seed_fase2') ON CONFLICT (id) DO NOTHING;

-- Videos y textos por tipo/opción (tipo = salida del clasificador = triaje_urgencias_log.tipo)
CREATE TABLE IF NOT EXISTS public.triaje_videos (
  id                      bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  tipo                    text NOT NULL CHECK (tipo ~ '^[a-z_]+$'),
  opcion                  smallint NOT NULL CHECK (opcion BETWEEN 1 AND 9),
  titulo                  text NOT NULL,
  url                     text CHECK (url IS NULL OR url ~ '^https://'),
  filename                text,
  caption                 text NOT NULL,                     -- canned; NUNCA LLM
  pregunta_guiada         text,                              -- se lee de la fila opcion=1; NULL = sin pregunta (media/baja => escalar)
  texto_salida_emergencia text NOT NULL,                     -- 2º mensaje tras el video
  activo                  boolean NOT NULL DEFAULT false,
  tamano_bytes            bigint,
  updated_at              timestamptz NOT NULL DEFAULT now(),
  updated_by              text,
  CONSTRAINT triaje_videos_tipo_opcion_uq UNIQUE (tipo, opcion),
  CONSTRAINT triaje_videos_activo_con_url CHECK (activo = false OR url IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_triaje_videos_tipo ON public.triaje_videos (tipo, opcion);
ALTER TABLE public.triaje_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.triaje_videos ENABLE ROW LEVEL SECURITY;

-- Seeds (textos = borradores basados en la descripción de Raquel del 28/8; chequeados a mano contra los 20 regex del Banlist: sin aplicá/sacá/tomá/guardá/enjuagá/venite/esperamos/no te preocupes/no es grave/lo antes posible+clínica)
INSERT INTO public.triaje_videos (tipo, opcion, titulo, url, filename, caption, pregunta_guiada, texto_salida_emergencia, activo, tamano_bytes, updated_by) VALUES
 ('alambre_pincha', 1, 'Opción 1 — cera de ortodoncia',
  'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion1.mp4', 'alambre_pincha_opcion1.mp4',
  'Opción 1: colocar cera de ortodoncia en la punta del alambre que pincha, como muestra el video. Si con eso no alcanza, avisanos por acá y te mandamos la Opción 2.',
  '¿El alambre se salió del último bracket o tubito de atrás y te pincha el cachete? Respondé SÍ o NO. Si podés, mandanos una foto de la zona: queda para la doctora.',
  'Si no mejora, si el dolor es fuerte o hay sangrado, respondé este mensaje y le pasamos a la doctora.',
  true, 3900000, 'seed_fase2_borrador'),
 ('alambre_pincha', 2, 'Opción 2 — reinsertar con pinza',
  'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion2.mp4', 'alambre_pincha_opcion2.mp4',
  'Opción 2: intentar reinsertar el alambre en el tubo o bracket con una pinza de alicate o de cejas, como muestra el video. Si tampoco funciona, avisanos por acá y le pasamos a la doctora.',
  NULL,
  'Si no mejora, si el dolor es fuerte o hay sangrado, respondé este mensaje y le pasamos a la doctora.',
  true, 5100000, 'seed_fase2_borrador'),
 ('bracket_suelto',  1, 'Opción 1 (video pendiente)', NULL, NULL, '[PENDIENTE] Caption a definir cuando llegue el video.', NULL, 'Si no mejora, si el dolor es fuerte o hay sangrado, respondé este mensaje y le pasamos a la doctora.', false, NULL, 'seed_fase2'),
 ('alambre_girado',  1, 'Opción 1 (video pendiente)', NULL, NULL, '[PENDIENTE] Caption a definir cuando llegue el video.', NULL, 'Si no mejora, si el dolor es fuerte o hay sangrado, respondé este mensaje y le pasamos a la doctora.', false, NULL, 'seed_fase2'),
 ('ligadura_pincha', 1, 'Opción 1 (video pendiente)', NULL, NULL, '[PENDIENTE] Caption a definir cuando llegue el video.', NULL, 'Si no mejora, si el dolor es fuerte o hay sangrado, respondé este mensaje y le pasamos a la doctora.', false, NULL, 'seed_fase2')
ON CONFLICT (tipo, opcion) DO NOTHING;

-- Extensión del log (ADD COLUMN IF NOT EXISTS: no rompe la sombra)
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS opcion_enviada  smallint;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS chat_history_id bigint;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS resuelto_at     timestamptz;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS razon_cierre    text;
CREATE INDEX IF NOT EXISTS idx_triaje_telefono_created ON public.triaje_urgencias_log (telefono, created_at DESC);
```
Cuando lleguen los otros videos: `scripts/upload_urgencia_video_supabase.py "<mp4>" "bracket_suelto/opcion1.mp4"` + `UPDATE triaje_videos SET url=..., caption=..., activo=true WHERE tipo='bracket_suelto' AND opcion=1`. Sin tocar n8n. Para la demo: `UPDATE triaje_config SET activo=true, telefonos_piloto='{5491161461034}'`; para abrir a todos: `telefonos_piloto='{}'`.

Guard de contenido (regla dura #5): los textos de la tabla NO pasan por `Banlist Validator` (salen por /send/*). Segunda capa obligatoria: (a) `tests/test_triaje_textos_banlist.py` corre los 20 regex del Banlist (extraídos del nodo vivo) sobre TODAS las filas activas de `triaje_videos` + `texto_cierre` y falla el PUT si algo matchea; (b) cuando el panel tenga UI para editar la tabla, reusar `chequearBanlist` de `lib/agente-guardrails.ts` al guardar (mismo patrón que `guardarPromptAction`).

## 6. Persistencia en memoria (query exacta) y efecto en Router/panel

INSERT dentro del CTE de `Triaje: Persistir` (ver 2.7 `sql_persistir`), mismo shape que `Build fromMe AI memory`/`Postgres - Save fromMe` (`INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)`):
```json
{"type":"human","content":"<text del paciente>","additional_kwargs":{"source":"triaje_paciente"},"response_metadata":{},"tool_calls":[],"invalid_tool_calls":[]}
{"type":"ai","content":"[VIDEO ENVIADO — alambre_pincha, Opción 1] <caption>\n<texto_salida_emergencia>","additional_kwargs":{"source":"triaje_video","tipo":"alambre_pincha","opcion":1,"video_url":"https://…/opcion1.mp4","video_id":1},"response_metadata":{},"tool_calls":[],"invalid_tool_calls":[]}
```
Consecuencias verificadas: `Build Router Context` muestra `PACIENTE: …` / `BOT: [VIDEO ENVIADO — …]` al turno siguiente; `Postgres Chat Memory` (window 10) lo da a los 5 sub-agents; el Logger (`type ai`, source ≠ reminder_note/wa_outbound) lo copia a `conversaciones` como `rol='assistant', fuente='bot'`; el panel lo muestra como burbuja "Asiri" al instante (tail en vivo). `Clear Old Memory` lo borra a los 7 días (correcto; el registro duradero es `triaje_urgencias_log`). `PG - Delete NO_REPLY` no lo toca. `source 'triaje_paciente'` en la fila human → el Logger la mapea a `rol='user'` (cualquier source que no sea wa_outbound/human_takeover). Para chip "Video" con link en el panel: cambio opcional en `Parse mensajes` del Logger (`metadata.media='video', url=addKw.video_url`) + `detectMedia` — no bloqueante.

## 7. Logging (`triaje_urgencias_log`)

| Camino | escalacion_id | modo | accion | tipo/confianza/razon | video_enviado / opcion_enviada | resuelto_at |
|---|---|---|---|---|---|---|
| gate red flag (nuevo o seguimiento) | NULL | cfg.modo | `escalado` | tipo NULL / razon `gate_red_flags`, `gate_red_flags` = `["gate:hinchazon"]`, `gate_escala` true | NULL | — |
| triaje inactivo / fuera piloto / LLM error / tipo sin video / confianza baja | NULL | cfg.modo (o `live` si no hubo config) | `escalado` | tipo/confianza del LLM, razon explícita (`triaje_inactivo`, `fuera_piloto`, `error_llm: …`, `confianza_media_sin_pregunta`) | NULL | — |
| video op1/op2 | id de la fila de aviso pasivo (o NULL si `aviso_pasivo=false`) | cfg.modo | `video` | tipo/alta/razon | `alambre_pincha/opcion1`, 1 | se llena al cerrar |
| pregunta guiada | NULL | cfg.modo | `pregunta` | tipo/media | NULL | — |
| envío falló | NULL | cfg.modo | `escalado` | razon `envio_fallo_video: <error>` | estado previo si existía | — |
| no sirvió sin más opciones | NULL | cfg.modo | `escalado` | razon `no_sirvio_sin_mas_opciones`, `video_enviado` = `alambre_pincha/opcion2` (del estado) | | |
`exec_id` = `$execution.id` del v6 (a diferencia de `escalaciones_log.exec_id`, que es del Helper). `chat_history_id` = id de la fila ai del caption. Lectura: extender `scripts/ver_triaje_sombra.py --modo piloto`. Reportero: 2º Postgres `Query Triaje Semana` sobre esta tabla (diseño del lector data-and-panel §4). **Sombra**: al activar el piloto, desactivar el satélite `Gm7ofyGohOJ2bI44` (o agregar a su `NOT EXISTS` una ventana `telefono` ± 2 min) para no duplicar filas `modo=sombra` de los casos que el piloto escaló con `escalacion_id NULL`.

## 8. Aviso pasivo (visible en /aprendizaje)

- **NUNCA** vía `POST /webhook/notify-grupo` (ni con `silencioso=true`): el Helper corre `Chatwoot Apply` siempre → label `humano` → el seguimiento moriría en `Bot Activo?` y no habría Opción 2 ni re-escalación. Verificado en el mapeo (6/6 escalaciones recientes suprimidas por su propio label).
- Implementación: INSERT directo en `escalaciones_log(telefono, motivo, origen='triaje_video', exec_id)` dentro del CTE de `Triaje: Persistir`, motivo `[TRIAJE VIDEO] alambre_pincha Opción 1 — atendido con video canned, sin escalar. Paciente: «…»`. Sin WhatsApp al grupo, sin label. `triaje_urgencias_log.escalacion_id` apunta a esa fila → la sombra la salta.
- Efecto en el panel HOY (sin tocar código): aparece en `/aprendizaje` como tema "Urgencias y dolor", tipo `senal` (texto "Urgencia … con video"), cuenta en el KPI de escalaciones del dashboard. **Cambio acompañante recomendado en el panel (repo `nexora-whatsapp-agent`, 3 líneas)**: en `lib/escalaciones.ts` agregar `RE_TRIAJE = /^\[triaje video\]/i` y devolver un tipo nuevo `resuelto` (badge "Resuelto con video") o `operativo`; en `dashboard/page.tsx` excluir `origen = 'triaje_video'` del conteo de escalaciones; en `scripts/create_reportero_semanal.py` replicar la regex (regla existente: "si se edita un lado, editar el otro"). Hasta ese cambio, `aviso_pasivo=false` es una alternativa válida por config.

## 9. Errores / fail-closed (qué recibe el paciente)

| Falla | Nodo que la ve | Resultado |
|---|---|---|
| Postgres caído / tabla ausente en `Cargar Config` | `onError continue` + `alwaysOutputData` → Evaluar ve cfg vacío | modo nuevo: `escalar (triaje_inactivo)` → Sub-Agent Urgencia como hoy. Seguimiento: regexes DEFAULT; no_sirvio → escalar (no hay Opción 2 sin config); cierre → cerrar; otro → Router |
| OpenAI caído / 5xx / JSON inválido | `neverError` → Decidir `error_llm` | escalar. Paciente: canned de Urgencia + aviso al grupo |
| Evolution GO 500/timeout en `/send/media` | `¿Video OK?` false | escalar. Paciente: canned de Urgencia (no vio video) |
| `/send/text` de salida falla tras video OK | `¿Texto OK?` false | escalar. Paciente: video con caption + canned de Urgencia; log `escalado` con razon `envio_fallo_video` |
| `/send/text` de pregunta falla | idem | escalar; paciente nunca queda sin respuesta |
| `Persistir` falla (Postgres) | `onError continue` | paciente ya tiene video; memoria/log perdidos; Redis SET igual se ejecuta (log_id null); seguimiento sigue funcionando. Sub-Agent Urgencia en una futura escalación no verá el video en memoria → el resumen al grupo no lo menciona (aceptado) |
| Redis SET falla | `onError continue` | sin estado; seguimiento cae en Router + regla nueva del prompt (2ª capa) |
| Redis GET falla | `onError continue` | flujo idéntico a hoy |
| Ruta desconocida / Evaluar devuelve algo raro | fallback de ambos Switch | escalar |
| Label `humano` en Chatwoot | `Bot Activo?` (antes de todo) | silencio, como hoy |
| Paciente escribe 11+ msgs en 15 min | `Rate Limit OK?` | descarte silencioso, como hoy (documentar; subir límite es cambio aparte) |
| Texto de tabla contiene frase prohibida | test pre-PUT + guard del panel | no llega a producción; en runtime no hay Banlist en la rama (decisión consciente: la capa es el test + el guard al editar) |
| Escalación tras video: canned de Urgencia suprimido por el label que el propio Helper aplica (bug preexistente, 6/6 casos) | `Re-check Humano` | el grupo SÍ recibe el aviso; el paciente puede no recibir "Le pasamos a la doctora". No lo introduce este diseño; fix aparte recomendado (que `Chatwoot Apply` no se aplique en la misma ejecución que escala o que Re-check ignore labels propios) |

## 10. Cómo se limpia el número de Lucas (5491161461034) para la demo

Ejecutar en este orden (script propuesto `scripts/limpiar_numero_demo.py --phone 5491161461034 --apply`, solo con OK de Lucas; cada paso imprime antes/después):
1. **Chatwoot** (único bloqueo determinístico): `GET /api/v1/accounts/1/contacts/1/conversations` → para CADA conversación (cualquier status) con label `humano`: `POST /api/v1/accounts/1/conversations/<id>/labels {"labels":["bot"]}` (`scripts/remove_humano_label.py` ya lo hace para conv 272; extenderlo a todas). No usar `no_bot`. Verificar `Verificar Label Humano` = false con un GET.
2. **Memoria**: `DELETE FROM n8n_chat_histories WHERE session_id='5491161461034'` (incluye id 5912 `[ATENCION HUMANA…]` source wa_outbound que `Clear Old Memory` nunca borra y que le pide silencio al LLM; y los `[TEST 72h]`). Mínimo aceptable: `… AND COALESCE(message->'additional_kwargs'->>'source','') IN ('wa_outbound','human_takeover')`.
3. **Redis**: `DEL chat_buffer:5491161461034`, `DEL ratelimit:5491161461034`, `DEL triaje:5491161461034`; `GET bot:status` ≠ `disabled`; `GET dentalink:status` ≠ `down`.
4. **Logs de prueba**: `escalaciones_log` 189/190, `conversaciones` 6006/6009 (pendientes con OK de Lucas) y cualquier `triaje_urgencias_log WHERE telefono='5491161461034'`.
5. **Config**: `UPDATE triaje_config SET activo=true, modo='piloto', telefonos_piloto='{5491161461034}'`.
6. **Durante la demo**: nadie escribe ni REACCIONA desde el celular del consultorio ni desde Chatwoot en ese chat (una reacción = fromMe = label humano 1 h + fila en memoria). Entre el mensaje 4 (escalación) y el 5 hay que repetir el paso 1 (la escalación aplica label humano). Alternativa más limpia: usar un segundo número que no sea admin ni tenga contacto en Chatwoot (evita el bug de auto-supresión del canned).

## 11. Guion de demo (5 mensajes desde el teléfono real de Lucas; ~30–40 s por respuesta por el buffer de 22 s)

| # | Lucas escribe | Camino | Lo que recibe |
|---|---|---|---|
| 1 | "hola, algo me pincha atrás en la boca, creo que es del aparato" | Router urgencia_dolor → Switch[2] → gate no → LLM alambre_pincha **media** → pregunta | Texto: pregunta guiada canned. Estado `paso:pregunta` (30 min). Log accion `pregunta`. (Si el LLM devuelve alta: recibe directo el video de la fila 2 y el guion sigue desde 3.) |
| 2 | "sí, es el alambre del último bracket y me lastima el cachete" | Redis estado → ¿Seguimiento? → Evaluar reclasifica (original+pregunta+respuesta) → alta → video op1 | **Video Opción 1** con caption + 2º mensaje de salida de emergencia. Panel: burbuja Asiri `[VIDEO ENVIADO — alambre_pincha, Opción 1] …`. `/aprendizaje`: fila `[TRIAJE VIDEO] …`. Estado `video_enviado/1`. |
| 3 | "me puse la cera pero se sale y sigue pinchando igual" | seguimiento → regex no_sirvio → Opción 2 activa → video op2 (sin LLM) | **Video Opción 2** + salida de emergencia. Estado `video_enviado/2`. |
| 4 | "no lo pude meter con la pinza, sigue igual" | seguimiento → no_sirvio → sin más opciones → Preparar Escalada → Log Escalado → Sub-Agent Urgencia | Grupo WhatsApp recibe `[ESCALADO BOT] Paciente ya recibió videos alambre_pincha Opción 1 y 2, sigue pinchando…` (gracias al párrafo nuevo del prompt + memoria). Lucas recibe "Recibimos tu mensaje. Le pasamos a la doctora…" (salvo bug preexistente de auto-label, ver §9). |
| 5 | (tras quitar el label humano, o desde otro número) "se me hinchó la cara y me cuesta tragar" | Switch[2] → gate red flags (`hinchazon`, `respirar_tragar`) → escalar sin LLM ni video | Escalación inmediata al grupo; log `gate_escala=true, gate_red_flags=[gate:hinchazon, gate:respirar_tragar]`, `accion=escalado`, tipo NULL. Muestra que las red flags mandan sobre todo. |
Bonus para vender "config sin n8n": antes del mensaje 3, `UPDATE triaje_videos SET activo=false WHERE opcion=2` → el mensaje 3 escala en vez de mandar Opción 2.

## 12. Plan de tests E2E (`tests/test_e2e_triaje.py`, extiende `tests/test_e2e_bateria.py`)

Payload: shape Evolution GO (whatsmeow) que exige `Webhook Validator`: `{"instanceName":"raquel","data":{"source":"test_e2e_suite","Info":{"ID":"<sim_id>","Chat":"5491161461034@s.whatsapp.net","Sender":"5491161461034@s.whatsapp.net","PushName":"Lucas (SIM)","IsFromMe":false,"Type":"text"},"Message":{"conversation":"<texto>"}}}` (el harness actual usa el shape viejo `data.key.remoteJid` y hoy sería descartado). `source: test_e2e_suite` bypassea el rate limit. Cada caso: POST al webhook → esperar la ejecución → assert sobre nodos ejecutados (`Triaje: Ruta` output), `triaje_urgencias_log`, `n8n_chat_histories`, Redis `triaje:<phone>`. Limpiar todo al final (memoria/logs/Redis/labels) con OK.

| # | Mensaje(s) | Esperado |
|---|---|---|
| T1 | "se me salió el alambre de atrás y me pincha el cachete" | Ruta video; `/send/media` 200 Info.ID; 2 mensajes en WA; 2 filas memoria; log accion video opcion 1; escalaciones_log origen triaje_video; Redis paso video_enviado opcion 1 TTL≈7200; Sub-Agent Urgencia NO ejecutado |
| T2 | (post T1) "no me sirvió, sigue pinchando" | Ruta video opcion 2, sin nodo Clasificar ejecutado; Redis opcion 2 |
| T3 | (post T2) "sigue igual" | Preparar Escalada (razon no_sirvio_sin_mas_opciones) → Sub-Agent Urgencia ejecutado → Helper notify-grupo llamado; log accion escalado con video_enviado alambre_pincha/opcion2 |
| T4 | (limpio) T1 + "listo gracias ya me puse la cera" | Ruta cerrar; WA recibe texto_cierre; `resuelto_at` no NULL; `Fallback Output` ejecutado; estado Redis intacto |
| T5 | (post T4) "gracias!!" | Cerrar → `[NO_REPLY]` (UPDATE 0 filas) → PG - Delete NO_REPLY; nada enviado |
| T6 | (post T4) "hola, quería sacar un turno para mi hija" | Ruta Pre normal → Router → agendar_nuevo (flujo normal; estado no interfiere) |
| T7 | "me golpeé y se me salió el bracket, sangra mucho" | gate → escalar sin Clasificar; log gate_escala true flags [trauma, sangrado_abundante] |
| T8 | "algo me molesta del aparato" (confianza media esperada) + "sí, atrás" | pregunta → reclasifica; si alta video, si no escalar; en ambos casos sin segunda pregunta |
| T9 | `UPDATE triaje_config SET activo=false` + T1 | escalar razon triaje_inactivo; Sub-Agent Urgencia idéntico a hoy |
| T10 | `telefonos_piloto='{5490000000000}'` + T1 | escalar razon fuera_piloto |
| T11 | fila opcion 1 con `url` a un host inexistente | ¿Video OK? false → escalar razon envio_fallo_video; paciente recibe canned de Urgencia |
| T12 | (post T1) "me duele mucho y se me hinchó" | seguimiento → gate red flag → escalar (Capa 3) |
| T13 | mensaje con tildes/ñ en el texto del paciente y caption con "ó" | memoria y WA sin `Ã³` (corrupción de encoding) |
| T14 | `node triaje/test_gate.js` (29/29) + `tests/test_triaje_evaluar_decidir.py` (harness `AsyncFunction` con `$input`/`$`/`$execution` mockeados, igual que `test_canned_sidecar.py`) sobre `EVALUAR_JS`/`DECIDIR_JS`/`PREPARAR_ESCALADA_JS` importados del script de apply: 20+ casos de ruteo determinístico | verde antes del PUT |
| T15 | `tests/test_triaje_textos_banlist.py`: regex del Banlist vivo sobre todas las filas activas de `triaje_videos` + `texto_cierre` | 0 matches |
Shadow/cutover: correr T1–T13 con `telefonos_piloto` = solo Lucas durante 24–48 h; luego `telefonos_piloto='{}'`.

## 13. Script de aplicación y rollback

`scripts/apply_triaje_fase2_piloto.py` (patrón `apply_canned_sidecar.py`, `lib_env`): `GET /workflows/O155MqHgOSaNZ9ye` fresco → `build(wf)` puro e idempotente (por nombre `Triaje: *`; re-aplicar = solo actualizar parámetros) → **asserts duros** antes de reconectar: `conns['Switch sobre Intent']['main'][2] == [{Sub-Agent Urgencia}]` y `conns['Es cierre?']['main'][1] == [{Router - Clasificar Intent}]` (si no, `sys.exit`) → clona `headerParameters` de `Evolution API - Enviar Mensaje` y base URL en caliente (nunca hardcodea apikey) → embebe `triaje/gate_red_flags.js` → edita los 2 prompts con ancla `count()==1` + marcador de idempotencia → imprime CAMBIOS (nodos nuevos, conexiones antes/después, `difflib` de prompts) → sin `--apply` = dry-run. Con `--apply`: pre-checks (tablas existen: `SELECT 1 FROM triaje_config`; T14/T15 verdes) → backup `workflows/history/v6_PRE_triaje_fase2_<ts>.json` → `assert webhookId == 'evo-webhook-v2'` en `Webhook - Evolution API` → PUT con `{name,nodes,connections,settings,staticData}` y settings filtradas a la allowlist (saca `availableInMCP`/`binaryMode`) → GET → backup POST → verificación por índice de las 2 conexiones modificadas + 18 nodos presentes + prompts con marcador. Actualizar `prompts/v6_partials/urgencia_funcion.md` y el partial del Router en el mismo commit (`build_prompts_v6.py --check` limpio).

Rollback (3 niveles, del más barato al total):
1. **Datos, 0 PUT, instantáneo**: `UPDATE triaje_config SET activo=false` → todo mensaje nuevo escala como hoy; `DEL triaje:*` (o esperar TTL ≤2 h) para cortar seguimientos.
2. **Reconexión mínima**: `apply_triaje_fase2_piloto.py --rollback-wiring` restaura `Switch sobre Intent`[2] → `Sub-Agent Urgencia` y `Es cierre?`[1] → `Router` dejando los nodos huérfanos (n8n tolera nodos sin input, como `Es primer mensaje?`).
3. **Total**: `--rollback <workflows/history/v6_PRE_triaje_fase2_<ts>.json>` = PUT del backup PRE (misma allowlist de settings, mismo assert de webhookId). Las tablas nuevas y las columnas agregadas se dejan (no rompen nada).

## prompts_edited
[
 "Sub-Agent Urgencia (parameters.options.systemMessage, expresión que empieza con '='; ancla = línea 'Si el paciente insiste tras escalar -> el label humaño ya esta aplicado. Devolver `[NO_REPLY]`.' count==1; marcador de idempotencia 'MEMORIA DEL TRIAJE CON VIDEO'). Se INSERTA inmediatamente después del ancla, sin tocar nada más:\n\n**MEMORIA DEL TRIAJE CON VIDEO (NUEVO 2026-09-04)**: si en tu memoria ves un mensaje AI que empieza con \"[VIDEO ENVIADO —\" o \"[TRIAJE — PREGUNTA GUIADA\", NO es un consejo tuyo ni una contradicción: es un video/pregunta CANNED aprobado por la Dra. Raquel que el sistema envió automáticamente en un turno anterior. Tu función no cambia: seguís los PASOS OBLIGATORIOS igual (escalar + canned). Lo único distinto: en el `resumen` de `escalar_a_secretaria` indicá que el paciente YA recibió ese video (tipo y opción) y qué dijo después (ej: \"Ya recibió video alambre_pincha Opción 1 y 2, dice que sigue pinchando. Coordinar control.\"). NUNCA repitas, parafrasees ni amplíes el contenido del video al paciente (cera, pinza, etc. siguen PROHIBIDOS para vos).\n\nMismo bloque agregado a prompts/v6_partials/urgencia_funcion.md para que build_prompts_v6.py --check no reporte drift.",
 "Router - Clasificar Intent (parameters.options.systemMessage; ancla = línea '- AI previo: \"lo paso a la secretaria Irina\" -> respuesta corta del paciente (\"ok\", \"gracias\", \"te veo el jueves\") -> intent = `consulta_general` (donde el sub-agent decide NO_REPLY).' count==1; marcador 'CONTINUACION DE URGENCIA CON VIDEO'). Se INSERTA después del ancla (segunda capa: solo actúa cuando el estado Redis ya venció o falló; mientras hay estado el seguimiento no llega al Router):\n\n- **CONTINUACION DE URGENCIA CON VIDEO (NUEVO 2026-09-04)**: si el ultimo BOT del contexto empieza con \"[VIDEO ENVIADO —\" o \"[TRIAJE — PREGUNTA GUIADA\" (el sistema de triaje mando un video o una pregunta canned por una urgencia de aparato), entonces: (a) si el paciente responde la pregunta, dice que sigue igual / no le sirvio / sigue pinchando / se sale / no tiene cera o pinza, o menciona cualquier molestia del aparato -> intent = `urgencia_dolor` (continuacion del flujo urgencia; NUNCA `consulta_general` aunque no diga la palabra \"dolor\" y aunque sea una pregunta). (b) Si SOLO agradece o cierra (\"listo\", \"gracias\", \"ya me la puse\", \"ya esta\") -> `consulta_general`.\n\nMismo bloque agregado al partial del Router en prompts/v6_partials/ (drift check)."
]

## failure_modes
- Postgres caído o tabla triaje_config ausente en 'Triaje: Cargar Config' (onError continueRegularOutput + alwaysOutputData): en mensaje nuevo Evaluar ve cfg.activo=false → ruta escalar razon 'triaje_inactivo' → Sub-Agent Urgencia como hoy (paciente recibe canned de escalación, grupo avisado). En seguimiento: regexes DEFAULT hardcodeadas; 'no sirvió' → escalar (sin config no hay Opción 2); cierre → cerrar; otro → Router.
- OpenAI caído / 5xx / respuesta no-JSON en 'Triaje: Clasificar' (neverError): Decidir marca tipo 'error_llm' → escalar. Paciente: canned de Urgencia + aviso al grupo; log accion escalado razon 'error_llm: …'.
- Evolution GO 500/timeout/JSON roto en '/send/media' ('Triaje: ¿Video OK?' false): escalar; paciente no vio video, recibe canned de Urgencia; log razon 'envio_fallo_video: …'. Nunca se confía en continueOnFail sin inspeccionar data.Info.ID.
- '/send/text' de la salida de emergencia falla después de un video OK ('Triaje: ¿Texto OK?' false): escalar; paciente ya tiene el video con caption y además recibe el canned de Urgencia y el grupo es avisado (redundante pero seguro); memoria/log del video no se persisten (Persistir no corre).
- '/send/text' de la pregunta guiada falla: escalar; el paciente nunca queda sin respuesta; no se guarda estado 'pregunta' en Redis.
- 'Triaje: Persistir' falla (Postgres): paciente ya tiene el video; se pierden fila de memoria, log y aviso pasivo; Redis SET igual corre (log_id null) y el seguimiento determinístico sigue funcionando; una escalación posterior no verá el video en memoria (el resumen al grupo no lo menciona).
- 'Triaje: Redis SET estado' falla: no hay estado; el seguimiento cae en la segunda capa (Router con 'BOT: [VIDEO ENVIADO —…]' en ctx + regla nueva del prompt). Si el Router falla la continuación, 'no me sirvió' puede ir a Sub-Agent General (riesgo residual documentado, mitigado por la fila de memoria).
- 'Triaje: Redis GET estado' falla: flujo idéntico a hoy (Router). En la práctica Redis caído ya mata el bot antes en 'Rate Limit INCR'.
- Evaluar/Decidir devuelven una ruta inesperada: fallbackOutput de 'Triaje: Ruta Pre' y 'Triaje: Ruta' → 'Triaje: Preparar Escalada' → Sub-Agent Urgencia.
- Label 'humano' en Chatwoot (por escalación previa, fromMe, reacción de la Dra, takeover): el mensaje muere en 'Bot Activo?' antes de cualquier nodo Triaje, como hoy; el estado Redis queda hasta el TTL (2 h video / 30 min pregunta) y no interfiere.
- Estado 'video_enviado' vigente y el paciente escribe algo que no matchea no_sirvio ni cierre (ej. 'me duele otra muela'): Ruta Pre 'normal' → Router; si vuelve a urgencia_dolor, Evaluar (modo nuevo) + Decidir: si el LLM clasifica el MISMO tipo → escalar (razon 'mismo_problema_post_video', no se re-manda el video); si es otro tipo → flujo normal del triaje (hoy: escalar porque solo alambre_pincha tiene video).
- Paciente responde con emoji solo o prompt injection tras el video: 'Pre-filtro Cierre' skip → Set NO_REPLY (como hoy); el estado Redis sigue vigente.
- Rate limit 10 msgs/15 min: mensajes 11+ se descartan en silencio (comportamiento actual, sin cambio); riesgo bajo en el flujo pregunta→video→opción 2 (≤4 mensajes).
- Texto editable con frase prohibida guardado en la tabla: no existe Banlist en runtime en la rama nueva; la defensa es el test pre-PUT (regex del Banlist vivo sobre filas activas) + guard chequearBanlist en el panel al editar. Si alguien edita por SQL sin test, el texto sale tal cual (documentado como límite; alternativa futura: nodo 'Triaje: Banlist' reutilizando el mismo array).
- Escalación después de video (bug PREEXISTENTE, no introducido acá): el Helper aplica label 'humano' sincrónicamente y 'Re-check Humano' 1.4 s después suprime el canned de Urgencia para pacientes con contacto en Chatwoot (6/6 casos desde 30/8); el grupo SÍ recibe el aviso. Impacta la demo (mensaje 4). Fix aparte recomendado.
- Sombra activa en paralelo (Gm7ofyGohOJ2bI44): los casos que el piloto escaló con escalacion_id NULL serían reprocesados por la sombra (fila duplicada modo=sombra, costo gpt-5-mini). Mitigación: desactivar la sombra al activar el piloto o agregar ventana telefono ±2 min a su NOT EXISTS.
- Panel /aprendizaje y dashboard sin el cambio acompañante: la fila de aviso pasivo (origen 'triaje_video') se muestra como 'senal' e infla el KPI de escalaciones. Mitigación inmediata: aviso_pasivo=false en triaje_config hasta desplegar las 3 líneas del panel.
- Buffer de 22 s: si el paciente manda 'no me sirvió' y 5 s después 'ah no, ya está', llegan como un solo texto; no_sirvio se evalúa antes que cierre → manda Opción 2 (error de UX, no de seguridad; el paciente puede ignorarla o cerrar después).
- Clear Old Memory borra las filas triaje_* a los 7 días junto con el resto de la sesión (correcto): el registro duradero es triaje_urgencias_log.

## tradeoffs
1) Dos puntos de inserción (Switch[2] y antes del Router) en vez de uno: el pedido decía 'un solo punto de bifurcación claro', pero el relevamiento del Router demostró que dejar el seguimiento post-video en manos del LLM (sin ninguna regla de continuación para urgencia, con 'ante DUDA → consulta_general' y con 'y si no tengo pinza?' cayendo por Regla 0 en Sub-Agent General + KB) reproduce exactamente la clase de falla del incidente Mariela. Se paga 1 GET Redis + 1 IF por mensaje; con key ausente el flujo es bit a bit el actual. Ambos puntos convergen en la misma columna vertebral (Cargar Config → Evaluar), así que el bloque sigue siendo uno. 2) 18 nodos nuevos, más que 'mínimo': se prefirió nodos explícitos con onError + IF de chequeo (fail-closed verificable en la UI) a Code monolíticos con this.helpers.httpRequest que esconden fallas; cada nodo es un paso auditable para un cliente nuevo. Se ahorraron nodos fusionando memoria+log+aviso en un solo INSERT CTE atómico y compartiendo el envío de texto (salida de emergencia / pregunta) y el punto de escalación. 3) Aviso pasivo por INSERT directo en escalaciones_log (origen 'triaje_video') en vez de notify-grupo silencioso: notify-grupo aplica SIEMPRE el label humano y mataría Opción 2 y la re-escalación; el costo es un cambio de 3 líneas en el panel/reportero para que no cuente como 'Asiri no supo resolver' (o aviso_pasivo=false mientras tanto). 4) Los textos canned de la rama nueva NO pasan por Banlist Validator ni Formatting Agent en runtime (salen por /send/* directos, 100% de tabla): se gana determinismo y se cumple 'caption canned'; la segunda capa es el test pre-PUT sobre las filas activas + guard en el panel. 5) Estado Redis no se borra al cerrar ('listo gracias'): permite que 'sigue pinchando' 10 min después vaya a Opción 2 en vez de al Router; el cierre se registra en DB (resuelto_at) y el estado expira por TTL. 6) Reclasificación tras la pregunta guiada: alta → video, cualquier otra → escalar (nunca segunda pregunta): más escalaciones que un diálogo largo, pero menos superficie de error y cero LLM generativo. 7) Piloto por fila + allow-list de teléfonos + kill-switch en triaje_config: rollback de datos sin PUT, a costa de una tabla más que mantener. 8) El bug preexistente de auto-supresión del canned de Urgencia (label humano propio) no se arregla acá para no mezclar riesgos en el diff; se documenta porque afecta el mensaje 4 de la demo.