# Mapa de tablas y superficies de datos para el triaje de urgencias con video

Todo lo de abajo sale de lectura de archivos del repo (`c:/Users/not/Desktop/proyectos/raquel-n8n`) y del panel (`c:/Users/not/Desktop/proyectos/nexora-whatsapp-agent`). No se hizo ningún GET a la API de n8n ni escritura en ningún lado. Ningún valor de credencial se reproduce (varios aparecieron en greps: apikey de Evolution en `scripts/create_reportero_semanal.py` línea 42 y un token de Chatwoot embebido en el jsCode de `Gate Humano Final` del v6 — ambos omitidos acá).

Contexto de diseño vigente (leído antes de mapear): `memory/decisions.md` 2026-09-02 (3 decisiones: sin vision, aviso pasivo, rollout sombra→piloto→4 tipos; hosting en bucket público `urgencias-videos`) y **2026-09-04** (construir Fase 2 YA, piloto `alambre_pincha`, textos borrador en tabla de config editable `triaje_videos`, otros 3 tipos `activo=false`). `memory/current-state.md` cabecera 2026-09-04 confirma que el v6 cambió hoy 13:22 UTC y que `scripts/apply_triaje_fase2_piloto.py` debe trabajar sobre GET fresco.

---

## 1) DDL real en `scripts/rebuild_v3_schema.sql` (columnas exactas)

### `n8n_chat_histories` (sección 1, líneas 46-60)
```
id          BIGSERIAL PRIMARY KEY
session_id  VARCHAR(255) NOT NULL        -- teléfono 549XXXXXXXXXX
message     JSONB NOT NULL               -- {type, content, tool_calls, additional_kwargs:{source,...}}
created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
```
Índices: `idx_nch_session_id (session_id, id DESC)`, `idx_nch_session_created (session_id, created_at DESC)`. Escritores en el v6: el nodo LangChain `Postgres Chat Memory` (`memoryPostgresChat`, `sessionKey = {{ $('Preparar Mensaje Final').first().json.phone }}`, `contextWindowLength: 10`, conectado por `ai_memory` a los 5 sub-agents: Confirmar, Cancelar, Agendar, Urgencia, General) y el nodo `Postgres - Save fromMe` (`INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)`).

### `pacientes` (sección 2, líneas 66-80)
```
id                     BIGSERIAL PRIMARY KEY
telefono               TEXT NOT NULL UNIQUE
nombre                 TEXT DEFAULT 'Paciente WhatsApp'
human_takeover         BOOLEAN DEFAULT FALSE
resumen_clinico        TEXT
resumen_actualizado_at TIMESTAMPTZ
created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
```
Drift detectado: el panel selecciona `pacientes.panel_last_read_at` (`lib/conversaciones-data.ts` línea 16, tipo `V3Paciente`) y esa columna NO está en el DDL del repo.

### `conversaciones` (sección 3, líneas 91-104)
```
id          BIGSERIAL PRIMARY KEY
paciente_id BIGINT REFERENCES pacientes(id) ON DELETE SET NULL
telefono    TEXT NOT NULL
rol         TEXT NOT NULL      -- user | assistant | human | system (reales verificados 2/9: assistant/user/system)
mensaje     TEXT NOT NULL
fuente      TEXT               -- whatsapp | bot | whatsapp_secretaria | bot_reminder | unknown
"timestamp" TIMESTAMPTZ NOT NULL DEFAULT NOW()   -- viene del created_at de n8n_chat_histories
metadata    JSONB DEFAULT '{}'::jsonb            -- {source, pushName, type, chat_history_id}
```
Índices: `idx_conversaciones_telefono_ts (telefono, "timestamp" DESC)`, `idx_conversaciones_paciente (paciente_id)`.

### `escalaciones_log` (sección 7, líneas 172-181)
```
id         BIGSERIAL PRIMARY KEY
telefono   TEXT
motivo     TEXT
origen     TEXT DEFAULT 'bot'
exec_id    TEXT
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```
Índice `idx_escalaciones_created (created_at)`. Único escritor: nodo `Log Escalacion` (Postgres) en `Helper - Notify Grupo` (`S5U6tSipzlgFHCkf`), mapeo `telefono = query.phone || body.phone`, `motivo = query.resumen || body.text || 'sin resumen'`, `origen='bot'`, `exec_id={{ $execution.id }}`, `onError: continueRegularOutput` (`scripts/apply_escalaciones_logging.py` líneas 61-88).

### `triaje_urgencias_log` (sección 8b, líneas 215-235; creada 2/9 por `scripts/create_triaje_urgencias_log_table.py`, idéntica)
```
id                     BIGSERIAL PRIMARY KEY
escalacion_id          BIGINT UNIQUE REFERENCES escalaciones_log(id) ON DELETE SET NULL
telefono               TEXT
exec_id                TEXT
escalacion_created_at  TIMESTAMPTZ
motivo_bot             TEXT
mensaje_paciente       TEXT
gate_red_flags         JSONB NOT NULL DEFAULT '[]'::jsonb   -- ["gate:fiebre","llm:dolor intenso"]
gate_escala            BOOLEAN NOT NULL DEFAULT FALSE
tipo                   TEXT   -- red_flag | alambre_pincha | bracket_suelto | alambre_girado | ligadura_pincha | otra_urgencia | no_urgencia | error_llm
confianza              TEXT   -- alta | media | baja
razon                  TEXT
modelo                 TEXT
modo                   TEXT NOT NULL DEFAULT 'sombra'    -- sombra | piloto | live
accion                 TEXT NOT NULL DEFAULT 'escalado'  -- escalado | video
video_enviado          TEXT
created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
```
Índices: `idx_triaje_created (created_at)`, `idx_triaje_tipo (tipo)`. Hoy la escribe solo el satélite `Áurea — Triaje Urgencias (sombra)` (`Gm7ofyGohOJ2bI44`) con `modo='sombra', accion='escalado'`; `video_enviado` no se llena nunca todavía. Comentario del DDL: "Tabla propia para NO ensuciar /aprendizaje ni el reportero; el futuro scoring de urgencias del reportero lee de acá".

### `knowledge_base` (sección 5, líneas 140-152)
```
id         BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
categoria  TEXT NOT NULL
titulo     TEXT NOT NULL
contenido  TEXT NOT NULL
metadata   JSONB NOT NULL DEFAULT '{}'::jsonb   -- {tags:[], fuente:"..."}
embedding  extensions.vector(1536)
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```
Índice `idx_kb_embedding` hnsw cosine. RPC `match_documents(query_embedding, match_count, filter)` (líneas 283-310). Filas relevantes ya citadas en memoria: id=21 precio consulta (leída por `Extraer Horarios y Precio`), id=24 datos de cuenta (categoría `pagos`), id=20 horarios del médico.

Otras tablas del archivo: `recordatorios_enviados` (sección 4), `documents` (6, vacía), `urgencias_log` (8, **borrada el 18/7 por vacía pero el DDL sigue en el archivo** — si se re-corre entero, la recrea), `peticiones` (9, deducida, sin escritores), `servicios` (10, deducida, sin escritores — `lib/servicios.ts` del panel dice explícitamente "NO hay tabla servicios: un servicio es una entrada de knowledge_base").

### ¿Hay otra tabla de config editable desde el panel además de `knowledge_base`? SÍ, dos, y una es el patrón exacto a copiar:

1. **`recordatorios_config`** (`scripts/recordatorios_config.sql`, NO está en `rebuild_v3_schema.sql`): fila única.
```
id                smallint PRIMARY KEY DEFAULT 1   CHECK (id = 1)
activo            boolean NOT NULL DEFAULT true
hora_envio        smallint NOT NULL DEFAULT 8
dias_suspendidos  date[] NOT NULL DEFAULT '{}'
suspender_desde   date
suspender_hasta   date
updated_at        timestamptz NOT NULL DEFAULT now()
updated_by        text
```
RLS on (service_role del panel y usuario del pooler de n8n bypassean). Panel: `lib/recordatorios-config.ts` — `getRecordatoriosConfig()` (`.from("recordatorios_config").select(...).eq("id",1).maybeSingle()`, devuelve `disponible=false` + defaults si la tabla no existe) y `patch()` (`upsert({id:1, ...fields, updated_at, updated_by}, {onConflict:"id"})`). El workflow de Recordatorios la lee UNA vez por corrida con un gate fail-open (`coalesce(bool_and(...), true) as debe_correr`). **Principio documentado en el SQL: "el calendario es DATO evaluado durante la corrida que YA ocurre, no un scheduler nuevo".** Es el molde para `triaje_videos`/`triaje_config`.

2. **`agente_prompt_log`** (`scripts/agente_prompt_log.sql`): `id identity, node_name text NOT NULL, prompt_anterior text NOT NULL, prompt_nuevo text NOT NULL, autor text, created_at`. Es historial insert-only para revert; el "config" real es el `systemMessage` del nodo en n8n vía PUT (`lib/n8n.setSubAgentePrompt`) en `app/(app)/agente/prompt-actions.ts`, que ANTES de guardar corre `chequearBanlist(texto)` de `lib/agente-guardrails` y bloquea si hay frases prohibidas — **ese mismo guard hay que reusarlo para los captions editables del triaje.**

3. Menor: `pacientes.human_takeover` lo togglea el panel (`toggleBotAction`) y `pacientes.panel_last_read_at` lo escribe el panel.

---

## 2) Panel

### (a) Cómo clasifica `/aprendizaje` un motivo `"[Triaje] Urgencia resuelta con video (alambre_pincha, Opción 1) — tel …"`

`lib/escalaciones.ts` (código exacto):
```ts
const RE_RUIDO = /el bot detect[oó] que ya est[aá]s atendiendo/i;
const RE_OPERATIVO = /comprobante\s+(de\s+pago|por|de\s+\$)|envi[oó]\s+comprobante|verificar que el pago/i;
const TEMAS = [
  { tema: "Urgencias y dolor", re: /\bdolor|molesti|urgen|sangr|hinch|fiebre|inflam/i },
  { tema: "Aparatología", re: /bracket|topecito|alambre|\btubo\b|aparatolog|se le sali/i },
  ...
];
export function tipoEscalacion(motivo) { if (RE_RUIDO.test(t)) return "ruido"; if (RE_OPERATIVO.test(t)) return "operativo"; return "senal"; }
```
- `tipoEscalacion` → **`senal`** (no matchea ni ruido ni operativo).
- `temaEscalacion` → **"Urgencias y dolor"** (la palabra "Urgencia" matchea `urgen`; si no estuviera, "alambre" lo mandaría a "Aparatología").
- `limpiarMotivo`: `t.replace(/^\[[^\]]{0,40}\]\s*:?\s*/, "")` borra `[Triaje] `; `/\b(phone|tel\.?|tel[eé]fono)\s*:?\s*\+?\d[\d\s-]{5,}/gi` borra "tel 549…" solo si detrás vienen ≥6 dígitos. Queda listado en la página como **"Urgencia resuelta con video (alambre_pincha, Opción 1) —"** bajo el encabezado "Cada caso de acá es algo que Asiri todavía no sabe resolver" (`aprendizaje/page.tsx` líneas 161-170) y suma en `totalSenal` ("Casos para revisar") y en el delta semanal (`semana.senal.length - previa.senal.length`).

Impacto en las OTRAS 3 superficies que leen `escalaciones_log` con la misma o ninguna clasificación:
- **`app/(app)/dashboard/page.tsx`** líneas 115-126: KPI "escalaciones" = `count exact` de TODAS las filas del rango (sin clasificar) y `escaladosDistintos` = teléfonos distintos → `autonomia = 1 - escalados/activos` (líneas 163-166). Una fila "resuelta con video" **sube escalaciones y baja el % de autonomía**, al revés de lo que representa.
- **Reportero semanal** (`scripts/create_reportero_semanal.py`, `CLASIFICAR_CODE`): regex copiadas 1:1 de `lib/escalaciones.ts` ("si se edita un lado, editar el otro") → también `senal` → se lo pasa a `LLM Síntesis` (gpt-5-nano) como "caso que el bot escaló porque no supo resolverlo" → sugerencia de KB espuria en el WhatsApp del lunes.
- **Satélite sombra `Gm7ofyGohOJ2bI44`**, nodo `Query Urgencias Nuevas` (`scripts/create_triaje_sombra.py` líneas 50-77):
```sql
... FROM escalaciones_log e
WHERE e.created_at BETWEEN NOW() - INTERVAL '{{ $json.horas }} hours' AND NOW() - INTERVAL '{{ $json.min_edad }} minutes'
  AND e.motivo !~* 'el bot detect[oó] que ya est[aá]s atendiendo'
  AND e.motivo !~* 'comprobante\s+(de\s+pago|por|de\s+\$)|envi[oó]\s+comprobante|verificar que el pago'
  AND (e.motivo ~* '\mdolor|molesti|urgen|sangr|hinch|fiebre|inflam'
       OR e.motivo ~* 'bracket|topecito|alambre|\mtubo\y|aparatolog|se le sali')
  AND NOT EXISTS (SELECT 1 FROM triaje_urgencias_log t WHERE t.escalacion_id = e.id)
```
  Una fila `[Triaje] … alambre_pincha` matchea `urgen` y `alambre`; si el v6 no inserta ANTES una fila hermana en `triaje_urgencias_log` con ese `escalacion_id`, la sombra la reprocesa 10-15 min después (gasto gpt-5-mini + fila duplicada `modo='sombra'` para un caso que fue `piloto`). **Loop de realimentación.**

**Recomendación**: para los casos resueltos con video, **NO escribir en `escalaciones_log`**. Escribir solo `triaje_urgencias_log` (`modo='piloto'`, `accion='video'`, `tipo`, `video_enviado`, `escalacion_id NULL`) — es literalmente el motivo por el que se creó la tabla el 2/9. La "Decisión 2 — aviso pasivo" se cumple con el reportero leyendo `triaje_urgencias_log` (punto 4), no con una fila en la tabla de escalaciones. Si de todos modos se quiere una fila en `escalaciones_log` (ej. para que el dashboard la cuente), entonces sí conviene un prefijo canónico y hay que tocar **4 lugares**: (1) `lib/escalaciones.ts` agregar `const RE_TRIAJE = /^\[triaje\]/i;` y en `tipoEscalacion` devolverlo como `operativo` ANTES de `RE_OPERATIVO` (un 4to tipo `resuelto` obliga a tocar `Record<TipoEscalacion,…>` y el copy de `page.tsx` líneas 150-154 que dice "fueron comprobantes de pago"); (2) `create_reportero_semanal.py` `CLASIFICAR_CODE` (y redeploy del workflow ya creado); (3) `create_triaje_sombra.py` `QUERY_NUEVAS` → `AND e.motivo !~* '^\[triaje\]'`; (4) `scripts/analisis_retrospectivo_urgencias.py`. Y NUNCA loguearlo vía `POST /webhook/notify-grupo?silencioso=true`: en `Helper - Notify Grupo` el IF `Silencioso?` solo saltea `Notify Grupo Send`; `Log Escalacion` **y `Chatwoot Apply` corren SIEMPRE** (`apply_fix_ruido_notify_grupo.py` líneas 16-23: "aplica el label 'humano' que usa el propio gate — es funcional") → el bot se silenciaría para ese paciente. El camino es un nodo Postgres con INSERT directo (credencial `Postgres Supabase Nexora v3`, id `TpYhZX4UT61xAKSV`, la misma del sombra y del reportero).

### (b) ¿Un video mandado por el bot fuera del LLM aparece en el chat del panel?

**Sí, si y solo si queda una fila en `n8n_chat_histories`** — el envío por `/send/media` en sí no deja rastro en ninguna tabla. Dos lectores:

**Lector en vivo** — `lib/chat-data.ts` `getChatData()` líneas 117-138 y 172-188: lee `conversaciones` (`select("id, rol, mensaje, fuente, timestamp, metadata").eq("telefono").neq("rol","system").order(timestamp desc).limit(200)`) y el tail de `n8n_chat_histories` (`select("id, message, created_at").eq("session_id", telefono).order(id asc).limit(60)`), dedup por timestamp en ms. Para cada fila nch: `content = message.content` (string), descarta `esMensajeInterno(content)` (`c === "" || c === "[NO_REPLY]" || /^\[\s*nota interna/i`), exige `message.type ∈ {'human','ai'}`, y arma `{ rol: type==='human'?'user':'assistant', fuente: type==='human'?'whatsapp':'bot', metadata: null }`. **En vivo el chat NO ve `additional_kwargs`** (metadata null).

**Lector diferido — Logger `Logger Conversaciones (Supabase)` (`xsXeHp7WLXnFQc3o`)**, snapshot `workflows/history/Logger_POST_supav3_20260718_141034.json` + fix `scripts/apply_fix_logger_no_ficha_falsa.py`. Grafo: `Cron 30s` → `Get last_synced` (staticData `last_synced_chat_id`) → `PG - SELECT nuevos` (`SELECT id, session_id, message::text AS message, created_at FROM n8n_chat_histories WHERE id > $1::bigint ORDER BY id ASC LIMIT 200`) → `Parse mensajes` → `IF - Es Mensaje Entrante (rol=user)` → [true] `HTTP - Upsert Paciente` (POST `/rest/v1/pacientes?on_conflict=telefono`, body `{telefono, nombre: pushName||'Paciente WhatsApp'}`) → `HTTP - Insert Conversacion`; [false] → `HTTP - Insert Conversacion` directo → `Update last_synced`. Código de `Parse mensajes` (fragmento textual):
```js
const type = msg.type || msg.kwargs?.type || '';
const content = msg.content || msg.kwargs?.content || '';
const addKw = msg.additional_kwargs || msg.kwargs?.additional_kwargs || {};
const source = (addKw.source || '').toLowerCase();
const trimmed = String(content || '').trim();
if (!trimmed || trimmed === '[NO_REPLY]') continue;
if (ROUTER_INTENTS.has(trimmed.toLowerCase())) continue;
if (trimmed.length < 3) continue;
let rol = 'user'; let fuente = 'whatsapp';
if (type === 'human') { if (source === 'wa_outbound' || source === 'human_takeover') { rol='human'; fuente='whatsapp_secretaria'; } else { rol='user'; fuente='whatsapp'; } }
else if (type === 'ai') { if (source === 'reminder_note') { rol='system'; fuente='bot_reminder'; } else { rol='assistant'; fuente='bot'; } }
else { rol='system'; fuente='unknown'; }
out.push({ json: { chat_history_id: id, telefono: phone, rol, mensaje: trimmed, fuente, created_at: r.created_at,
  metadata: { source, pushName, type, chat_history_id: id }, pushName } });
```
`HTTP - Insert Conversacion` body: `{ paciente_id: $json[0].id, telefono, rol, mensaje: JSON.stringify(...), fuente, timestamp: created_at, metadata: JSON.stringify(metadata) }`.

**Atribución en `components/conversaciones/chat-view.tsx` `Bubble` (líneas 698-708)**:
```ts
const esStaffManual = message.metadata?.source === "wa_outbound" || message.mensaje.startsWith("[ATENCION HUMANA");
const outgoing = message.rol !== "user";
const isHuman = message.rol === "human" || esStaffManual;
const isBot = outgoing && !isHuman;          // → label "Asiri", burbuja verde chat-bubble-out
const isReminder = message.fuente === "bot_reminder";   // badge "Recordatorio"
```
Tipo `ChatMessage.metadata?: { type?, url?, mediaUrl?, caption?, [k]: unknown } | null`. Detección de media (`detectMedia`, líneas 904-998): (1) marcadores `[IMAGEN] TIPO:…` / `[DOCUMENTO: …]` (adjuntos del paciente); (2) `metadata.type` matcheando `/video|v[íi]deo/` → kind `video`; (3) el mensaje ENTERO `^\[\s*([^\]]+?)\s*\]$` con marker `video|vídeo|un video` → kind `video`. URL: `metaUrl(meta)` busca `url|mediaUrl|media_url|fileUrl|link` en metadata, si no `firstUrl(raw)` (primera `https?://` del texto). Render (`MediaBlock` líneas 1064-1076): chip "Video" con `<a href={media.fileUrl} target="_blank">` si hay URL, chip sin link si no. El texto plano NO se linkifica (`highlight()` solo resalta la búsqueda).

**Shape mínimo que funciona hoy sin tocar Logger ni panel** — copiar el patrón de `Build fromMe AI memory` + `Postgres - Save fromMe` del v6:
```js
const message = {
  type: 'ai',
  content: '[VIDEO ENVIADO — alambre_pincha, Opción 1] ' + caption,   // texto legible; ≥3 chars; no "[nota interna"; no un intent label
  additional_kwargs: { source: 'triaje_video', tipo: 'alambre_pincha', opcion: 1,
                       video_url: 'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion1.mp4',
                       triaje_log_id: <id de triaje_urgencias_log> },
  response_metadata: {}, tool_calls: [], invalid_tool_calls: []
};
// INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)   queryReplacement: phone, JSON.stringify(message)
```
Resultado: en vivo → burbuja verde "Asiri" con el texto del caption (a los ~4s); tras el Logger → `conversaciones` con `rol='assistant'`, `fuente='bot'`, `metadata={source:'triaje_video', pushName:null, type:'ai', chat_history_id}` → misma burbuja "Asiri". **Se ve como texto, no como chip de video**: `metadata.type` llega como `'ai'` (el Logger copia el type LangChain, no un media type) y el content no es exactamente `[video]`. Para chip con link hacen falta 2 cambios chicos: (i) `Parse mensajes`: `metadata: { source, pushName, type, chat_history_id, ...(addKw.video_url ? { media: 'video', url: addKw.video_url } : {}) }` y (ii) `detectMedia`: considerar `meta.media` además de `meta.type` (o que `chat-data.ts` copie `additional_kwargs` al `metadata` de las filas nch, hoy `null`). No es bloqueante para el piloto.

**Por qué NO reusar `source:'reminder_note'`** (el precedente más cercano de "mensaje del bot fuera del LLM", `scripts/repoblar_reminder_notes_03_06.py` líneas 89-94): el Logger lo mapea a `rol='system'` y el chat filtra `.neq("rol","system")` → desaparece del chat en cuanto sale del tail de 60 filas.

**Efectos colaterales de la fila en memoria (verificados en el v6)**:
- `Build Router Context` (Postgres): concatena `BOT: <content>` de las últimas 6 filas (excluye intents, `[CONTEXTO%`, `[NO_REPLY]`) → el Router y los sub-agents VEN que se mandó el video en el turno siguiente. Es deseable para "no funcionó → reescalar" y "mismo problema, segundo mensaje" (hallazgo de la retrospectiva: 4 familias re-escalaron). Por eso el prefijo explícito `[VIDEO ENVIADO — …]` (misma técnica que el TAG `[ATENCION HUMANA …]` del fromMe) importa: el prompt vivo de Sub-Agent Urgencia prohíbe "consejos como cera" y sin tag podría leer el caption como output propio contradictorio.
- `Check Humano Reciente (DB)` (gate "Bot Activo?", `scripts/apply_fix_gate_humano_reciente.py` líneas 78-84): mira el `source` de la ÚLTIMA fila de la sesión excluyendo `reminder_note`; una fila `triaje_video` tapa un `wa_outbound` anterior. Como el triaje corre dentro del camino normal del v6 (después de ese gate) no debería pasar, pero si alguna vez se escribe desde un satélite, agregar `'triaje_video'` a la exclusión.
- `Clear Old Memory`: `DELETE … WHERE source NOT IN ('wa_outbound','human_takeover','reminder_note')` → la fila del video se borra con el TTL de memoria; no hace falta preservarla (el registro duradero es `triaje_urgencias_log`).
- `Postgres Chat Memory` con `contextWindowLength: 10`: la fila entra al contexto de los sub-agents en los próximos turnos.

---

## 3) Propuesta: config editable `triaje_videos` (+ `triaje_tipos` + `triaje_config`)

Diseño: tres tablas con el molde de `recordatorios_config` (dato, no n8n; RLS on; `updated_at/updated_by`), más una vista que n8n lee en **UN SELECT por urgencia**, fail-closed (0 filas / `activo=false` / sin videos → escalar como hoy). `tipo` usa exactamente los valores que ya devuelve el clasificador de la sombra y que guarda `triaje_urgencias_log.tipo`. Los captions son canned (nunca LLM), se anexa `salida_emergencia` al final de cada caption, y el panel debe validar con `chequearBanlist` al guardar (como `guardarPromptAction`). Los textos se escribieron chequeados a mano contra los 22 patrones del `Banlist Validator` (ver riesgo: `guard…amos`, `aplic…`, `sac…`, `tom…`, `venite`, `esperamos`, `lo antes posible + clínica/venir` están prohibidos — por eso los captions dicen "colocar" y no "aplicá", y "queda para la doctora" y no "la guardamos").

Sobre el "texto EXACTO de Raquel del 28/8": lo único citado en `memory/current-state.md` (líneas 64-72 hoy) es la descripción de los dos videos: **"Opción 1 = colocar cera de ortodoncia en la punta del alambre; Opción 2 = intentar reinsertar el alambre al tubo/bracket con una pinza de alicate o de cejas, para probar si la Opción 1 no alcanza."** Los captions de abajo usan ese texto literal como núcleo; el fraseo de preguntas guiadas NO está en el repo (open-questions.md solo tiene la lista borrador de red flags y los casos límite) — van marcados `BORRADOR` para que Raquel los reemplace desde el panel.

```sql
-- =============================================================================
-- Triaje de urgencias con video — configuración editable desde el panel
-- Supabase v3 (eoizfjsyejixjzwgzwkt). Idempotente. Mismo patrón que
-- recordatorios_config: es DATO leído por n8n en la corrida que ya ocurre.
-- =============================================================================

-- 0. Switch global (fila única) — equivalente al TEST_MODE del Reportero/Recordatorios
CREATE TABLE IF NOT EXISTS public.triaje_config (
  id                smallint     PRIMARY KEY DEFAULT 1,
  activo            boolean      NOT NULL DEFAULT false,   -- kill-switch maestro: false => TODO escala como hoy
  modo              text         NOT NULL DEFAULT 'piloto', -- sombra | piloto | live (se copia a triaje_urgencias_log.modo)
  telefonos_piloto  text[]       NOT NULL DEFAULT '{}',    -- allow-list en piloto (E2E con tel de prueba); vacío = todos
  texto_pedido_foto text         NOT NULL DEFAULT 'Si podés, mandanos una foto de la zona para que la vea la doctora.',
  texto_escalado    text         NOT NULL DEFAULT 'Recibimos tu mensaje. Le pasamos a la doctora para que le coordine lo antes posible.',
  updated_at        timestamptz  NOT NULL DEFAULT now(),
  updated_by        text,
  CONSTRAINT triaje_config_singleton CHECK (id = 1),
  CONSTRAINT triaje_config_modo_chk  CHECK (modo IN ('sombra','piloto','live'))
);
INSERT INTO public.triaje_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- 1. Un tipo de urgencia por fila: pregunta guiada + salida de emergencia + activo por tipo
CREATE TABLE IF NOT EXISTS public.triaje_tipos (
  tipo                text         PRIMARY KEY,             -- = triaje_urgencias_log.tipo y salida del clasificador
  label               text         NOT NULL,
  activo              boolean      NOT NULL DEFAULT false,  -- false => ese tipo escala como hoy aunque tenga videos
  orden               smallint     NOT NULL DEFAULT 100,
  pregunta_guiada     text,                                 -- canned; NULL = no preguntar (video directo si confianza alta)
  respuesta_confirma  text         NOT NULL DEFAULT '^\s*(s[ií]|dale|claro|exacto|eso|correcto)\b',  -- regex determinística (flag i en JS)
  salida_emergencia   text         NOT NULL,                -- se ANEXA a cada caption
  texto_no_resuelto   text         NOT NULL,                -- "no funcionó" y no quedan opciones -> acompaña la escalación
  updated_at          timestamptz  NOT NULL DEFAULT now(),
  updated_by          text,
  CONSTRAINT triaje_tipos_tipo_chk CHECK (tipo ~ '^[a-z_]+$')
);

-- 2. Videos: N opciones ordenadas por tipo (alambre_pincha ya trajo 2 secuenciales)
CREATE TABLE IF NOT EXISTS public.triaje_videos (
  id            bigint       GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
  tipo          text         NOT NULL REFERENCES public.triaje_tipos(tipo) ON DELETE CASCADE,
  opcion        smallint     NOT NULL,                      -- 1 = se manda primero; 2 = si el paciente dice que no resolvió
  titulo        text         NOT NULL,
  url           text,                                       -- pública del bucket urgencias-videos; NULL hasta que llegue el video
  filename      text,                                       -- nombre que muestra WhatsApp (/send/media.filename)
  caption       text         NOT NULL,                      -- canned, NO LLM; el panel valida banlist al guardar
  activo        boolean      NOT NULL DEFAULT false,
  duracion_seg  smallint,                                   -- informativo
  tamano_bytes  bigint,                                     -- informativo (WhatsApp ~16MB)
  updated_at    timestamptz  NOT NULL DEFAULT now(),
  updated_by    text,
  CONSTRAINT triaje_videos_tipo_opcion_uq  UNIQUE (tipo, opcion),
  CONSTRAINT triaje_videos_opcion_chk      CHECK (opcion BETWEEN 1 AND 9),
  CONSTRAINT triaje_videos_url_https_chk   CHECK (url IS NULL OR url ~ '^https://'),
  CONSTRAINT triaje_videos_activo_con_url  CHECK (activo = false OR url IS NOT NULL)   -- no se puede prender sin video
);
CREATE INDEX IF NOT EXISTS idx_triaje_videos_tipo ON public.triaje_videos (tipo, opcion);

-- 3. Vista que lee n8n en UN SELECT por urgencia (fail-closed: 0 filas => escalar como hoy)
CREATE OR REPLACE VIEW public.v_triaje_config AS
SELECT t.tipo, t.label, t.activo, t.orden, t.pregunta_guiada, t.respuesta_confirma,
       t.salida_emergencia, t.texto_no_resuelto,
       COALESCE(
         jsonb_agg(jsonb_build_object('id', v.id, 'opcion', v.opcion, 'url', v.url,
                                      'caption', v.caption, 'filename', v.filename)
                   ORDER BY v.opcion)
           FILTER (WHERE v.activo AND v.url IS NOT NULL),
         '[]'::jsonb) AS videos,
       c.activo AS triaje_activo, c.modo, c.telefonos_piloto, c.texto_pedido_foto, c.texto_escalado
FROM public.triaje_tipos t
LEFT JOIN public.triaje_videos v ON v.tipo = t.tipo
CROSS JOIN public.triaje_config c
WHERE c.id = 1
GROUP BY t.tipo, t.label, t.activo, t.orden, t.pregunta_guiada, t.respuesta_confirma,
         t.salida_emergencia, t.texto_no_resuelto,
         c.activo, c.modo, c.telefonos_piloto, c.texto_pedido_foto, c.texto_escalado;
-- n8n: SELECT * FROM v_triaje_config WHERE tipo = $1 AND activo AND triaje_activo AND jsonb_array_length(videos) > 0;

-- 4. Seeds — tipos (los 3 sin video quedan activo=false y siguen escalando)
INSERT INTO public.triaje_tipos (tipo, label, activo, orden, pregunta_guiada, salida_emergencia, texto_no_resuelto) VALUES
 ('alambre_pincha', 'Alambre que pincha / se salió', true, 10,
  '[BORRADOR] Para orientarte mejor: ¿el alambre se salió del último bracket o tubito de atrás y te pincha el cachete? Respondé SÍ o NO. Si podés, mandanos una foto de la zona: queda para la doctora.',
  'Si no mejora, si el dolor es fuerte o hay sangrado, respondé este mensaje y le pasamos a la doctora.',
  'Entendido. Le pasamos a la doctora para que le coordine lo antes posible.'),
 ('bracket_suelto', 'Bracket suelto / se salió', false, 20,
  '[BORRADOR] ¿El bracket se despegó del diente pero sigue enganchado en el alambre, o se salió del todo? Respondé cuál de las dos.',
  'Si no mejora, si el dolor es fuerte o hay sangrado, respondé este mensaje y le pasamos a la doctora.',
  'Entendido. Le pasamos a la doctora para que le coordine lo antes posible.'),
 ('alambre_girado', 'Alambre girado', false, 30,
  '[BORRADOR] ¿El alambre se corrió hacia un costado y sobresale más de un lado que del otro? Respondé SÍ o NO.',
  'Si no mejora, si el dolor es fuerte o hay sangrado, respondé este mensaje y le pasamos a la doctora.',
  'Entendido. Le pasamos a la doctora para que le coordine lo antes posible.'),
 ('ligadura_pincha', 'Ligadura que pincha', false, 40,
  '[BORRADOR] ¿Lo que pincha es el alambre finito o la gomita que rodea el bracket? Respondé "alambre finito" o "gomita".',
  'Si no mejora, si el dolor es fuerte o hay sangrado, respondé este mensaje y le pasamos a la doctora.',
  'Entendido. Le pasamos a la doctora para que le coordine lo antes posible.')
ON CONFLICT (tipo) DO NOTHING;

-- 5. Seeds — videos (URLs reales del bucket público urgencias-videos, subidas el 2/9)
INSERT INTO public.triaje_videos (tipo, opcion, titulo, url, filename, caption, activo, tamano_bytes) VALUES
 ('alambre_pincha', 1, 'Opción 1 — cera de ortodoncia',
  'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion1.mp4',
  'alambre_pincha_opcion1.mp4',
  'Opción 1: colocar cera de ortodoncia en la punta del alambre, como muestra el video. Si con eso no alcanza, avisanos y te mandamos la Opción 2.',
  true, 3900000),
 ('alambre_pincha', 2, 'Opción 2 — reinsertar el alambre con pinza',
  'https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion2.mp4',
  'alambre_pincha_opcion2.mp4',
  'Opción 2: intentar reinsertar el alambre al tubo/bracket con una pinza de alicate o de cejas, como muestra el video. Es para probar si la Opción 1 no alcanza.',
  true, 5100000),
 ('bracket_suelto',  1, 'Opción 1 (video pendiente)', NULL, NULL, '[PENDIENTE] Caption a definir cuando llegue el video de bracket suelto.', false, NULL),
 ('alambre_girado',  1, 'Opción 1 (video pendiente)', NULL, NULL, '[PENDIENTE] Caption a definir cuando llegue el video de alambre girado.', false, NULL),
 ('ligadura_pincha', 1, 'Opción 1 (video pendiente)', NULL, NULL, '[PENDIENTE] Caption a definir cuando llegue el video de ligadura que pincha.', false, NULL)
ON CONFLICT (tipo, opcion) DO NOTHING;

-- 6. RLS como el resto de v3 (service_role del panel y usuario del pooler de n8n bypassean)
ALTER TABLE public.triaje_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.triaje_tipos  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.triaje_videos ENABLE ROW LEVEL SECURITY;

-- 7. Extensión de triaje_urgencias_log para el piloto (ADD COLUMN IF NOT EXISTS, no rompe la sombra)
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS video_id       bigint REFERENCES public.triaje_videos(id) ON DELETE SET NULL;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS opcion_enviada smallint;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS foto_recibida  boolean NOT NULL DEFAULT false;
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS reescalado_at  timestamptz;   -- "no funcionó" después del video
ALTER TABLE public.triaje_urgencias_log ADD COLUMN IF NOT EXISTS chat_history_id bigint;       -- fila de n8n_chat_histories del caption
CREATE INDEX IF NOT EXISTS idx_triaje_telefono_created ON public.triaje_urgencias_log (telefono, created_at DESC);  -- "mismo problema, 2do mensaje"
```

Notas de diseño: (a) el gate de red flags NO se mueve a tabla — `triaje/gate_red_flags.js` es fuente única con 29/29 tests (`node triaje/test_gate.js`); pasarlo a datos rompería la garantía de tests salvo que los tests lean la misma tabla. (b) `respuesta_confirma` es regex y no LLM por defensa en profundidad; si Raquel no la va a editar, se puede hardcodear en el nodo. (c) `telefonos_piloto` permite el E2E con teléfono sintético y un rollout gradual sin tocar n8n. (d) El panel que edite estas tablas debe reusar `chequearBanlist` (`lib/agente-guardrails.ts`) sobre `caption`, `pregunta_guiada`, `salida_emergencia`, `texto_no_resuelto`; y la vista `/servicios` (`lib/servicios.ts`) NO sirve de molde porque agrupa `knowledge_base` por categoría, no otra tabla.

---

## 4) Reportero semanal (`scripts/create_reportero_semanal.py`, workflow `Áurea — Reportero Semanal`)

Lee de **`escalaciones_log` únicamente**: nodo `Query Escalaciones Semana` (Postgres, credencial `Postgres Supabase Nexora v3`): `SELECT motivo, created_at FROM escalaciones_log WHERE created_at >= NOW() - INTERVAL '7 days' ORDER BY created_at DESC`. Grafo: `Lunes 10AM Arg (cron hora Berlin)` (`0 15 * * 1`) / `Webhook Manual Reportero` (`POST /webhook/trigger-reportero-manual`) → `Query Escalaciones Semana` → `Clasificar y Agrupar` (Code, regex 1:1 de `lib/escalaciones.ts`, devuelve `{total, senal, ruido, operativo, hay_senal, temas, temas_texto_llm}`) → `¿Hay señal?` (IF `$json.hay_senal`) → [true] `Prep LLM Body` (gpt-5-nano, T=0.3) → `LLM Síntesis` → `Build Mensaje Con Señal`; [false] `Build Mensaje Sin Señal` → `Prep Envío (test mode)` (`TEST_MODE=true` → Lucas `5491161461034`, si no grupo `120363407321448469@g.us`) → `Enviar WA`. Pedido original del scoring: `docs/reunion-2026-08-15-dra-raquel.md` sección "A. Reportero semanal → agregar scoring de urgencias".

Cómo agregar el scoring desde `triaje_urgencias_log` (solo diseño):
1. Nuevo nodo Postgres `Query Triaje Semana` en paralelo a `Query Escalaciones Semana`: `SELECT tipo, accion, modo, gate_escala, gate_red_flags, confianza, opcion_enviada, reescalado_at, telefono, created_at FROM triaje_urgencias_log WHERE created_at >= NOW() - INTERVAL '7 days'`.
2. Nodo Code `Resumir Urgencias`: agrupa tipo × accion, cuenta red flags por flag (`gate_red_flags` es array `gate:`/`llm:`), % resueltas con video, re-escalaciones (`reescalado_at IS NOT NULL` o mismo `telefono` con 2+ filas en 7 días), y `tipo='otra_urgencia'` repetido (candidato a video nuevo: contención rota / Invisalign).
3. Un nodo Merge (o `$('Resumir Urgencias').first().json` dentro de ambos `Build Mensaje …`) para anexar al `mensaje_final` un bloque `*Urgencias de la semana:* N (X con video, Y escaladas, red flags: dolor_intenso×2)` — en el camino con señal Y en el sin señal.
4. Opcional: pasar ese bloque a `Prep LLM Body` para que `LLM Síntesis` sugiera "video nuevo" cuando un sub-tema sin video se repite.
5. Consecuencia del punto 2a: los casos resueltos con video se cuentan SOLO desde `triaje_urgencias_log` (no están en `escalaciones_log`), así el bloque de escalaciones "señal" sigue limpio. El workflow ya existe en n8n: el cambio va por script con GET fresco + backup PRE/POST, mismo protocolo.

## KEY FACTS
- escalaciones_log tiene solo 6 columnas (id, telefono, motivo, origen, exec_id, created_at) y un único escritor: nodo 'Log Escalacion' de Helper - Notify Grupo, que corre SIEMPRE junto con 'Chatwoot Apply' (label humano) aunque silencioso='true'; no sirve para loguear 'resuelto con video' sin silenciar al bot.
- triaje_urgencias_log ya existe (2/9) con escalacion_id UNIQUE FK, gate_red_flags jsonb, tipo, confianza, modo (sombra|piloto|live), accion (escalado|video), video_enviado; hoy solo la escribe el satélite sombra Gm7ofyGohOJ2bI44 con modo='sombra'.
- Un motivo '[Triaje] Urgencia resuelta con video (alambre_pincha, Opción 1) — tel …' en escalaciones_log se clasifica como tipo 'senal' y tema 'Urgencias y dolor' en /aprendizaje (lib/escalaciones.ts), se muestra como 'caso que Asiri no supo resolver' con el prefijo [Triaje] borrado por limpiarMotivo, infla el KPI de escalaciones y baja la autonomía en /dashboard (que cuenta todas las filas sin clasificar), y el satélite sombra lo reprocesaría (matchea 'urgen' y 'alambre') salvo que exista fila hermana en triaje_urgencias_log con ese escalacion_id.
- Además de knowledge_base, el panel edita recordatorios_config (fila única id=1, scripts/recordatorios_config.sql, lib/recordatorios-config.ts, gate fail-open en el workflow) y usa agente_prompt_log como historial de prompts (el prompt vive en n8n; se valida con chequearBanlist de lib/agente-guardrails antes del PUT). recordatorios_config es el molde para triaje_config/triaje_tipos/triaje_videos.
- Un video mandado por /send/media no deja rastro en ninguna tabla; aparece en el chat del panel solo si se inserta una fila en n8n_chat_histories con message {type:'ai', content:<caption>, additional_kwargs:{source:'triaje_video', ...}} (mismo INSERT que 'Postgres - Save fromMe'); el Logger la copia a conversaciones como rol='assistant', fuente='bot', metadata {source, pushName, type:'ai', chat_history_id} y chat-view la muestra como burbuja verde 'Asiri' (isBot = rol!=='user' && !(metadata.source==='wa_outbound' || mensaje startsWith '[ATENCION HUMANA')).
- El chip 'Video' con link en chat-view requiere metadata.type que matchee /video/ o que el mensaje entero sea '[video]'; el Logger pone metadata.type='ai' (type LangChain) y no copia URLs, así que hoy el caption se ve como texto plano (URL no linkificada). Chip con link = 2 cambios chicos (Parse mensajes + detectMedia/chat-data), no bloqueante.
- No reusar source 'reminder_note' para la fila del video: el Logger la mapea a rol='system' y el chat filtra .neq('rol','system') → desaparece cuando sale del tail de 60 filas de n8n_chat_histories.
- La fila en memoria del video entra a Build Router Context (últimas 6 como 'BOT: ...') y al contexto de los 5 sub-agents (contextWindowLength 10): útil para 'no funcionó → reescalar' y 'mismo problema, 2do mensaje', por eso conviene el tag explícito '[VIDEO ENVIADO — tipo, Opción N]' como el TAG del fromMe.
- El único texto de Raquel del 28/8 citado en el repo (memory/current-state.md) es: 'Opción 1 = colocar cera de ortodoncia en la punta del alambre; Opción 2 = intentar reinsertar el alambre al tubo/bracket con una pinza de alicate o de cejas, para probar si la Opción 1 no alcanza.' El fraseo de preguntas guiadas NO existe en el repo (open-questions.md solo tiene red flags borrador y casos límite).
- URLs reales del bucket público: https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/alambre_pincha/opcion1.mp4 (3.9MB, WhatsApp Video 2026-08-28 at 11.57.38 AM.mp4) y .../alambre_pincha/opcion2.mp4 (5.1MB, ...12.06.23 PM.mp4). /send/media body {number, type:'video', url, caption, filename}, mismo host y apikey que 'Evolution API - Enviar Mensaje' (https://evo.raquelrodriguez.com.ar).
- El reportero semanal lee SOLO escalaciones_log (nodo 'Query Escalaciones Semana', 7 días) y copia las regex del panel 1:1; el scoring de urgencias se agrega con un 2do Postgres 'Query Triaje Semana' sobre triaje_urgencias_log + Code 'Resumir Urgencias' + bloque extra en ambos Build Mensaje.
- Banlist Validator prohíbe formas que un caption ingenuo usaría: guard(a|amos|...)+espacio ('la guardamos' dispara), aplic(á|a|ate|en|ense), sac(a..)+(la|el), tom(a..)+(dosis/artículo), venite/venga, te/los esperamos, 'lo antes posible' seguido en 50 chars de clínica/consultorio/venir, 'no te preocupes', 'no es grave'. Los captions propuestos ya evitan todas.
- Drift de esquema: pacientes.panel_last_read_at es usada por el panel y no está en rebuild_v3_schema.sql; urgencias_log (borrada 18/7) sigue con CREATE TABLE IF NOT EXISTS en el archivo; recordatorios_config y agente_prompt_log viven en SQLs sueltos fuera del rebuild.
- memory/current-state.md y decisions.md se están editando en paralelo durante esta sesión (los números de línea cambiaron ~20 líneas entre dos lecturas); la cabecera 2026-09-04 dice que el v6 cambió hoy 13:22 UTC y que apply_triaje_fase2_piloto.py debe partir de un GET fresco.

## RISKS
- Loguear el caso 'resuelto con video' en escalaciones_log (con o sin prefijo) contamina 4 consumidores a la vez: /aprendizaje (senal → 'Asiri no supo resolver'), /dashboard (KPI escalaciones ↑, autonomía ↓), reportero semanal (sugerencia de KB espuria vía LLM) y el satélite sombra (reprocesa la fila con gpt-5-mini y duplica en triaje_urgencias_log si no hay fila hermana con escalacion_id). Mitigación: escribir solo triaje_urgencias_log (accion='video'); si igual se loguea, prefijo '^\[triaje\]' como 'operativo' replicado en lib/escalaciones.ts, create_reportero_semanal.py, create_triaje_sombra.py y analisis_retrospectivo_urgencias.py.
- Usar POST /webhook/notify-grupo?silencioso=true para 'aviso pasivo' aplica igual el label 'humano' en Chatwoot ('Chatwoot Apply' corre siempre) → el bot se silencia para ese paciente y no puede seguir el flujo Opción 1 → Opción 2 → reescalar.
- El caption/pregunta guiada/salida de emergencia editables desde el panel salen por /send/media, fuera de Fallback Output → Canned Sidecar → Banlist Validator: la regla dura #5 (cada regla crítica en ≥2 capas) obliga a validar con las mismas regex al guardar (chequearBanlist en el panel) Y/O a pasar el caption por el Banlist en n8n. Sin eso, Raquel podría guardar 'aplicá cera y venite' y se enviaría.
- Escribir la fila del video en n8n_chat_histories con source='reminder_note' o content vacío/'[nota interna…'/<3 chars o igual a un intent label hace que el Logger o el chat la descarten (no se vería en el panel o quedaría rol=system).
- Si la fila del video se escribe desde fuera del camino normal del v6 (p.ej. un satélite), 'Check Humano Reciente (DB)' mira solo la ÚLTIMA fila de la sesión: una fila 'triaje_video' posterior a un 'wa_outbound' oculta la atención humana y el bot podría reactivarse. Agregar 'triaje_video' a la lista de exclusión de ese query si aplica.
- Fail-open vs fail-closed: recordatorios_config es fail-open por diseño; para el triaje debe ser FAIL-CLOSED (tabla ausente, tipo inactivo, videos vacíos, error de /send/media → escalar como hoy). El CHECK 'activo = false OR url IS NOT NULL' evita prender un tipo sin video, pero el nodo n8n debe tratar 0 filas como 'escalar'.
- Multi-pedido en el mismo mensaje (patrón Salvador Mayans / Paulina Villanueva): un mensaje que trae urgencia + pedido de alias/precio pasa por Canned Sidecar con passthrough en urgencias; si la respuesta del triaje sale por otro nodo, el sidecar no anexa nada → pedido perdido. Definir dónde converge la salida del triaje.
- Sub-Agent Urgencia prohíbe explícitamente 'cera' y verá el caption en su memoria (contextWindowLength 10) en turnos siguientes; sin el tag '[VIDEO ENVIADO …]' puede interpretar la fila como output propio contradictorio y comportarse raro (p.ej. reescalar de más o disculparse).
- Clear Old Memory borra la fila del video con el TTL (no está en la lista preservada): el contexto 'ya mandé el video' se pierde; el registro duradero para 'mismo problema, 2do mensaje' debe ser triaje_urgencias_log (índice telefono, created_at propuesto), no la memoria.
- Pruebas E2E dejan filas reales: el 3/9 Lucas escribió al número real y quedaron escalaciones_log 189/190 y conversaciones 6006/6009 pendientes de borrar (bloqueado por permisos). El triaje agrega 3 superficies más a limpiar por prueba: triaje_urgencias_log, n8n_chat_histories y conversaciones.
- Higiene de credenciales: scripts/create_reportero_semanal.py línea 42 hardcodea el apikey de Evolution (EVO_TOKEN) y el jsCode de 'Gate Humano Final' / 'Aviso humano tomo chat' del v6 embebe el token de Chatwoot; cualquier snapshot del v6 en workflows/current los contiene. No copiar esos nodos a scripts nuevos con valores literales.
- Los captions con 'colocar cera' son consejo paliativo por diseño (decisión 2/9 y 4/9), pero el DDL/seed no puede evitar que un editor del panel agregue instrucciones médicas nuevas (dosis, enjuagues): el guard del panel debe cubrir también triaje_tipos.pregunta_guiada y salida_emergencia, no solo caption.

## OPEN QUESTIONS
- ¿Se quiere de verdad una fila en escalaciones_log por caso resuelto con video (para que /dashboard lo cuente), o alcanza con triaje_urgencias_log + bloque en el reportero (recomendado)? Si es lo primero, hay que decidir el prefijo canónico y tocar los 4 consumidores en la misma pasada.
- ¿Existe el texto VERBATIM de WhatsApp de Raquel del 28/8 (fuera del repo, p.ej. en el vault) para reemplazar la paráfrasis de current-state.md en los captions de los seeds?
- ¿Quién y con qué UI edita triaje_videos/triaje_tipos en el panel? No hay vista hoy; /servicios y /conocimiento son vistas sobre knowledge_base y no sirven de molde directo. ¿Se reusa chequearBanlist de lib/agente-guardrails al guardar?
- ¿La 'salida de emergencia' es global (triaje_config) o por tipo (triaje_tipos.salida_emergencia como propuse)? Propuse por tipo con el mismo texto seed para los 4.
- ¿La confirmación de la pregunta guiada se resuelve con regex determinística (respuesta_confirma) o con el clasificador LLM? Propuse regex por defensa en profundidad; queda por validar con casos reales de la sombra.
- ¿Se cambia Parse mensajes del Logger y detectMedia del panel para mostrar el chip 'Video' con link (2 cambios chicos), o alcanza con el caption como texto en el piloto?
- ¿Se agrega 'triaje_video' a la exclusión de 'Check Humano Reciente (DB)' y a la lista preservada de 'Clear Old Memory', o el triaje solo escribe memoria desde el camino normal del v6 (donde no hace falta)?
- Cuando lleguen los otros 3 videos: ¿el patrón Opción 1/Opción 2 se repite (columna opcion ya lo soporta) o alguno trae un solo video?
- Fraseo de preguntas guiadas y lista final de red flags siguen pendientes de Raquel (open-questions.md desde 15/8); los seeds van marcados [BORRADOR] y las red flags quedan en triaje/gate_red_flags.js (no en tabla) para no perder los 29 tests.