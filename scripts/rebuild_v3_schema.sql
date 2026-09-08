-- ============================================================================
-- rebuild_v3_schema.sql — Reconstrucción del esquema en Supabase v3 (2026-07-17)
--
-- Contexto: el proyecto Supabase v2 (ujfyapjwrdhnvqdvsjwp) murió en crash-loop
-- irrecuperable (SQLSTATE 53100, pg_xact dañado). Este DDL recrea el esquema
-- completo en el proyecto v3 NUEVO. Idempotente: se puede correr N veces.
--
-- Fuentes de verdad usadas para deducir cada tabla (todo en este repo):
--   * scripts/apply_supabase_v2_rewire.py        (runbook migración 8/7)
--   * scripts/fix_logger_combine_queries.py       (INSERT pacientes + conversaciones)
--   * workflows/history/Logger_POST_supav2_*.json (REST upsert pacientes / insert conversaciones)
--   * workflows/history/Recordatorio_POST_supav2_*.json (insert recordatorios_enviados)
--   * workflows/current/v6_LIVE.json              (queries de memoria, tools REST, vector store)
--   * workflows/current/cron_resumen_clinico_*.json (pacientes.resumen_clinico / human_takeover)
--   * workflows/current/subwf_cancelar_reprogramar_LIVE.json (n8n_chat_histories)
--   * scripts/apply_ddl_resumen_clinico.py        (resumen_clinico / resumen_actualizado_at)
--   * scripts/apply_escalaciones_logging.py       (escalaciones_log)
--   * scripts/recovery_backfill.py                (columnas recordatorios_enviados)
--   * scripts/apply_kb_lucas_programador.py + embed_knowledge_base.py (knowledge_base)
--   * docs/handoff-conversacion-completa-2026-07.md (tablas fundacionales 15/7)
--
-- NO incluye resets de secuencia (base nueva, arranca de 1).
-- NO incluye RLS: el bot accede vía service_role (bypass RLS) y vía Postgres
--   directo con el usuario del pooler, igual que en v2. Si se quiere exponer
--   algo al anon key, habilitar RLS por tabla en ese momento.
-- Cómo correrlo: SQL Editor del dashboard Supabase v3 (todo el archivo de una),
--   o psql contra el pooler del proyecto nuevo.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. Extensión pgvector (Supabase la instala en el schema extensions).
--    El CREATE SCHEMA hace el archivo portable al plan B (Postgres en el VPS
--    Hostinger, donde "extensions" no existe de fábrica).
-- ----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- ----------------------------------------------------------------------------
-- 1. n8n_chat_histories — memoria LangChain (Postgres Chat Memory del v6)
--    Estructura base la crea solo el nodo memoryPostgresChat de n8n
--    (id SERIAL, session_id, message). created_at la agregó "Check Session Age"
--    del v6 con ALTER dinámico; acá nace incluida para que ese DO $$ sea no-op.
--    session_id = teléfono del paciente (549XXXXXXXXXX).
--    message = JSON LangChain {type, content, tool_calls, additional_kwargs:{source,...}}.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS n8n_chat_histories (
    id          BIGSERIAL PRIMARY KEY,
    session_id  VARCHAR(255) NOT NULL,
    message     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Por si la tabla ya existía creada por n8n sin created_at (mismo guard que el v6):
ALTER TABLE n8n_chat_histories ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();

-- Patrones de acceso reales: WHERE session_id = $1 ORDER BY id DESC LIMIT n
-- (Step 0a Sub-WF, Build Router Context, Clear Old Memory) y el gate humano
-- (session_id + source + created_at > NOW()-24h).
CREATE INDEX IF NOT EXISTS idx_nch_session_id      ON n8n_chat_histories (session_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_nch_session_created ON n8n_chat_histories (session_id, created_at DESC);

-- ----------------------------------------------------------------------------
-- 2. pacientes — upsert por telefono desde el Logger; leída por
--    "Get Paciente Context" (v6) y el Cron Resumen Clinico.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pacientes (
    id                     BIGSERIAL PRIMARY KEY,
    telefono               TEXT NOT NULL UNIQUE,          -- requerido por ON CONFLICT (telefono) del Logger
    nombre                 TEXT DEFAULT 'Paciente WhatsApp',
    human_takeover         BOOLEAN DEFAULT FALSE,         -- filtro del Cron Resumen Clinico
    resumen_clinico        TEXT,                          -- lo escribe el Cron Resumen Clinico (LLM)
    resumen_actualizado_at TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- DEDUCIDA (no aparece en queries; estándar del patrón)
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()   -- el Logger hace SET updated_at = NOW() en el upsert
);

-- Guard por si la tabla llega restaurada sin las columnas del cron:
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS resumen_clinico TEXT;
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS resumen_actualizado_at TIMESTAMPTZ;
ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS human_takeover BOOLEAN DEFAULT FALSE;

-- (el UNIQUE de telefono ya crea el índice de lookup principal)

-- ----------------------------------------------------------------------------
-- 3. conversaciones — log legible de la conversación (lo llena el Logger
--    desde n8n_chat_histories; lo lee obtener_historial_paciente vía REST y
--    el Cron Resumen Clinico). En v2 llegó a 202k filas.
--    rol: user | assistant | human | system · fuente: whatsapp | bot |
--    whatsapp_secretaria | bot_reminder | unknown  (Parse mensajes del Logger)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS conversaciones (
    id          BIGSERIAL PRIMARY KEY,
    paciente_id BIGINT REFERENCES pacientes(id) ON DELETE SET NULL,
    telefono    TEXT NOT NULL,
    rol         TEXT NOT NULL,
    mensaje     TEXT NOT NULL,
    fuente      TEXT,
    "timestamp" TIMESTAMPTZ NOT NULL DEFAULT NOW(),   -- viene del created_at de n8n_chat_histories
    metadata    JSONB DEFAULT '{}'::jsonb             -- {source, pushName, type, chat_history_id}
);

-- Patrones: REST telefono=eq.X order=timestamp.desc limit 20 · cron: telefono + timestamp > NOW()-30d
CREATE INDEX IF NOT EXISTS idx_conversaciones_telefono_ts ON conversaciones (telefono, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_conversaciones_paciente    ON conversaciones (paciente_id);

-- ----------------------------------------------------------------------------
-- 4. recordatorios_enviados — la escribe el WF Recordatorio 48HS; la leen las
--    3 tools REST del v6 (consultar_recordatorios_abiertos, marcar_*).
--    Columnas confirmadas por el nodo "Insert recordatorios_enviados", las
--    URLs PostgREST del v6 y scripts/recovery_backfill.py.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recordatorios_enviados (
    id                    BIGSERIAL PRIMARY KEY,
    telefono              TEXT NOT NULL,
    chat_remote_jid       TEXT,                -- 549...@s.whatsapp.net
    id_cita_dentalink     BIGINT,              -- number en el nodo n8n
    id_paciente_dentalink BIGINT,
    nombre_paciente       TEXT,
    fecha_turno           DATE,                -- llega 'yyyy-MM-dd'; REST filtra fecha_turno=gte.<date>
    hora_turno            TEXT,                -- llega 'HH:mm' (texto, no time: formato libre del cron)
    tipo                  TEXT,                -- '48h' (default del backfill) / '24h' / '72h'
    workflow_execution_id TEXT,                -- $execution.id (o '230100-backfill')
    enviado_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- lo selecciona consultar_recordatorios_abiertos
    confirmado_at         TIMESTAMPTZ,         -- marcar_recordatorio_confirmado (PATCH, filtro is.null)
    cancelado_at          TIMESTAMPTZ          -- marcar_recordatorio_cancelado
);

CREATE INDEX IF NOT EXISTS idx_recordatorios_telefono   ON recordatorios_enviados (telefono);
CREATE INDEX IF NOT EXISTS idx_recordatorios_cita_fecha ON recordatorios_enviados (id_cita_dentalink, fecha_turno);

-- Consultas (2026-09-08, pedido de la Dra. Raquel): las citas cuyo motivo_atencion EMPIEZA con "consulta" (/^consulta\b/i)
-- (primera visita, "puntito amarillo" en Dentalink) reciben un recordatorio distinto que exige el pago para
-- confirmar. El WF guarda el motivo tal cual (trim) y el flag para trazabilidad y para el panel. Filas
-- anteriores quedan NULL (= desconocido; NO backfillear como false: 5 de las últimas 57 eran consultas).
-- Mismo DDL que scripts/apply_recordatorio_consultas.py --ddl (idempotente; correr ANTES del --apply:
-- el nodo Postgres v2.6 valida las columnas contra la tabla viva y el Insert corre DESPUÉS del envío).
ALTER TABLE recordatorios_enviados ADD COLUMN IF NOT EXISTS motivo_atencion TEXT;
ALTER TABLE recordatorios_enviados ADD COLUMN IF NOT EXISTS es_consulta     BOOLEAN;

-- ----------------------------------------------------------------------------
-- 5. knowledge_base — KB curada de la clínica (35 docs en v2). La consume el
--    nodo Supabase Vector Store del v6 (retrieve-as-tool `buscar_conocimiento`,
--    queryName match_documents). El embedding lo genera
--    scripts/embed_knowledge_base.py (text-embedding-3-small, 1536 dims) sobre
--    el texto "categoria | titulo\ncontenido".
--    id: identity (v2 usaba identity, ver nota "kb identity→36" del runbook).
--    GENERATED BY DEFAULT (no ALWAYS) para permitir restores con id explícito.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS knowledge_base (
    id         BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    categoria  TEXT NOT NULL,
    titulo     TEXT NOT NULL,
    contenido  TEXT NOT NULL,
    metadata   JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {tags:[], fuente:"..."}
    embedding  extensions.vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()    -- DEDUCIDA (ninguna query la usa)
);

-- Con ~35 docs Postgres va a seq-scanear igual; el índice queda para cuando crezca.
CREATE INDEX IF NOT EXISTS idx_kb_embedding
    ON knowledge_base USING hnsw (embedding extensions.vector_cosine_ops);

-- ----------------------------------------------------------------------------
-- 6. documents — tabla estándar LangChain/Supabase. En v2 se creó VACÍA y no
--    la usa el vector store (que apunta a knowledge_base); se recrea igual
--    para no romper nada que la referencie por nombre.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id        BIGSERIAL PRIMARY KEY,
    content   TEXT,
    metadata  JSONB DEFAULT '{}'::jsonb,
    embedding extensions.vector(1536)
);

-- ----------------------------------------------------------------------------
-- 7. escalaciones_log — fuente de verdad de escalaciones para el reportero v2
--    (independiente de la retención ~72h de n8n). La escribe "Log Escalacion"
--    en Helper - Notify Grupo (scripts/apply_escalaciones_logging.py):
--    columnas insertadas: telefono, motivo, origen='bot', exec_id.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS escalaciones_log (
    id         BIGSERIAL PRIMARY KEY,
    telefono   TEXT,
    motivo     TEXT,
    origen     TEXT DEFAULT 'bot',
    exec_id    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()   -- DEDUCIDA: necesaria para "escalaciones de la semana"
);

CREATE INDEX IF NOT EXISTS idx_escalaciones_created ON escalaciones_log (created_at);

-- ----------------------------------------------------------------------------
-- 8. urgencias_log — tabla fundacional creada el 15/7 para el triaje de
--    urgencias + reportero semanal (docs/handoff-conversacion-completa-2026-07.md
--    y docs/reunion-2026-07-14-dra-raquel.md).
--    ⚠️ SCHEMA 100% DEDUCIDO: el DDL original se corrió en la sesión externa a
--    este repo y no quedó registrado. Ningún workflow la escribe todavía
--    (feature bloqueada esperando videos + fraseo de la Dra), así que este
--    diseño se puede ajustar sin romper nada. Diseñada espejo de
--    escalaciones_log + campos del triaje pactado (tipo, severidad).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS urgencias_log (
    id          BIGSERIAL PRIMARY KEY,
    telefono    TEXT,
    tipo        TEXT,               -- alambre_pincha | bracket_suelto | alambre_girado | ligadura | otro
    descripcion TEXT,               -- lo que relató el paciente / resumen del bot
    severidad   TEXT,               -- scoring del triaje (leve|media|grave) — pendiente de definición
    origen      TEXT DEFAULT 'bot',
    exec_id     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_urgencias_created ON urgencias_log (created_at);

-- ----------------------------------------------------------------------------
-- 8b. triaje_urgencias_log — creada el 2026-09-02 (scripts/create_triaje_urgencias_log_table.py)
--     Reemplaza en la práctica a urgencias_log (borrada el 18/7 por vacía). Una fila por
--     urgencia evaluada por el triaje: salida del gate determinístico de red flags
--     (triaje/gate_red_flags.js), clasificación del LLM y acción tomada. Fase 1 (sombra):
--     la escribe el satélite "Áurea — Triaje Urgencias (sombra)" leyendo escalaciones_log;
--     después la escribe el v6 en línea. Tabla propia para NO ensuciar /aprendizaje ni el
--     reportero; el futuro "scoring de urgencias" del reportero lee de acá.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS triaje_urgencias_log (
    id                     BIGSERIAL PRIMARY KEY,
    escalacion_id          BIGINT UNIQUE REFERENCES escalaciones_log(id) ON DELETE SET NULL,
    telefono               TEXT,
    exec_id                TEXT,
    escalacion_created_at  TIMESTAMPTZ,
    motivo_bot             TEXT,
    mensaje_paciente       TEXT,
    gate_red_flags         JSONB NOT NULL DEFAULT '[]'::jsonb,   -- ["gate:fiebre","llm:dolor intenso",...]
    gate_escala            BOOLEAN NOT NULL DEFAULT FALSE,
    tipo                   TEXT,        -- red_flag | alambre_pincha | bracket_suelto | alambre_girado | ligadura_pincha | otra_urgencia | no_urgencia | error_llm
    confianza              TEXT,        -- alta | media | baja
    razon                  TEXT,
    modelo                 TEXT,
    modo                   TEXT NOT NULL DEFAULT 'sombra',    -- sombra | piloto | live
    accion                 TEXT NOT NULL DEFAULT 'escalado',  -- escalado | video
    video_enviado          TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_triaje_created ON triaje_urgencias_log (created_at);
CREATE INDEX IF NOT EXISTS idx_triaje_tipo    ON triaje_urgencias_log (tipo);

-- ----------------------------------------------------------------------------
-- 9. peticiones — tabla fundacional 15/7: pedidos del staff/dashboard con
--    SLA 24hs (docs/handoff: "deje peticiones con SLA 24hs").
--    ⚠️ SCHEMA 100% DEDUCIDO (mismo caso que urgencias_log: sin DDL registrado,
--    sin escritores aún — el puente dashboard↔n8n no existe todavía).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS peticiones (
    id           BIGSERIAL PRIMARY KEY,
    telefono     TEXT,                                  -- paciente relacionado, si aplica
    solicitante  TEXT,                                  -- quién la dejó (iri | raquel | dashboard | bot)
    descripcion  TEXT NOT NULL,
    estado       TEXT NOT NULL DEFAULT 'pendiente',     -- pendiente | en_curso | resuelta
    sla_vence_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours',
    resuelta_at  TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_peticiones_estado ON peticiones (estado, sla_vence_at);

-- ----------------------------------------------------------------------------
-- 10. servicios — tabla fundacional 15/7: servicios/precios editables desde el
--     dashboard, futura fuente de verdad que alimenta la KB real del bot
--     (docs/reunion-2026-07-14: "servicios/KB editables desde la UI").
--     ⚠️ SCHEMA 100% DEDUCIDO (sin DDL registrado, sin escritores aún).
--     Precios estáticos conocidos hoy: consulta $50.000, cuota mensual $70.000.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS servicios (
    id               BIGSERIAL PRIMARY KEY,
    nombre           TEXT NOT NULL,          -- p.ej. 'Primera consulta', 'Cuota mensual ortodoncia'
    descripcion      TEXT,
    precio           NUMERIC(12,2),          -- NULL = "se evalúa en consulta" (tratamientos: NUNCA dar precio)
    moneda           TEXT DEFAULT 'ARS',
    duracion_minutos INTEGER,                -- tipos de turno: primera consulta variable, control 30/40 min
    activo           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 11. match_documents — RPC que usa el Supabase Vector Store de n8n
--     (options.queryName = 'match_documents') contra knowledge_base.
--     Firma estándar LangChain: (query_embedding, match_count, filter).
--     content se arma igual que el texto embebido por embed_knowledge_base.py:
--     "categoria | titulo\ncontenido" (así lo que matchea = lo que se embebió).
--     similarity = 1 - distancia coseno.
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding extensions.vector(1536),
    match_count     INT   DEFAULT NULL,
    filter          JSONB DEFAULT '{}'::jsonb
)
RETURNS TABLE (
    id         BIGINT,
    content    TEXT,
    metadata   JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
SET search_path = public, extensions
AS $$
BEGIN
    RETURN QUERY
    SELECT
        kb.id::BIGINT,
        (kb.categoria || ' | ' || kb.titulo || E'\n' || kb.contenido) AS content,
        COALESCE(kb.metadata, '{}'::jsonb) AS metadata,
        1 - (kb.embedding <=> query_embedding) AS similarity
    FROM knowledge_base kb
    WHERE kb.embedding IS NOT NULL
      AND COALESCE(kb.metadata, '{}'::jsonb) @> COALESCE(filter, '{}'::jsonb)
    ORDER BY kb.embedding <=> query_embedding
    LIMIT COALESCE(match_count, 4);
END;
$$;

-- ----------------------------------------------------------------------------
-- 12. media_entrantes — adjuntos del PACIENTE (foto, audio, video, documento,
--     sticker) que el v6 sube a Supabase Storage (2026-09-06). Una fila por
--     archivo; `id` (16 hex aleatorio) es lo que viaja en el sufijo
--     ' [MEDIA:<id>]' del marcador de texto que va al buffer y a la memoria
--     (n8n_chat_histories / conversaciones). El panel resuelve id -> path y
--     sirve URLs firmadas (1 h) con la service key; el bucket es PRIVADO.
--     Bucket: `pacientes-media` (public=false, 50 MB, cualquier mime) — se crea
--     por la API de Storage, no por SQL: scripts/create_media_entrantes.py.
--     Escritor: nodo "Media: Registrar" del v6 (scripts/apply_media_entrantes.py).
--     RLS habilitado SIN policies (solo service_role), como el resto del v3.
--     (La numeración sigue a la 11; la "sección 10" del pedido original ya era
--     `servicios`.)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS media_entrantes (
    id         TEXT PRIMARY KEY CHECK (id ~ '^[0-9a-f]{16}$'),
    key_id     TEXT,                                  -- Info.ID de WhatsApp (une con mensajes_entrantes_live.key_id)
    telefono   TEXT NOT NULL,                         -- = Extraer Datos.phone tal cual (mismo valor que mensajes_entrantes_live.telefono / session_id)
    from_me    BOOLEAN NOT NULL DEFAULT false,        -- true = lo mandó el consultorio (fuera de alcance hoy)
    tipo       TEXT NOT NULL CHECK (tipo IN ('image','video','audio','document','sticker')),
    mime       TEXT,                                  -- normalizado (sin '; codecs=…'), corregido por magic bytes
    bucket     TEXT NOT NULL DEFAULT 'pacientes-media',
    path       TEXT NOT NULL,                         -- <telefono>/<yyyy>/<mm>/<id>.<ext>
    bytes      INTEGER,
    filename   TEXT,                                  -- original (documentos) o <id>.<ext>
    caption    TEXT,                                  -- texto que acompañó al adjunto
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    borrado_at TIMESTAMPTZ                            -- 2026-09-07: lo marca el satélite Retención cuando borró el objeto de Storage
);

CREATE INDEX IF NOT EXISTS idx_media_entrantes_key_id      ON media_entrantes (key_id);
CREATE INDEX IF NOT EXISTS idx_media_entrantes_tel_created ON media_entrantes (telefono, created_at DESC);
ALTER TABLE media_entrantes ENABLE ROW LEVEL SECURITY;

-- Retención (2026-09-07): bases creadas antes de esa fecha no tienen la columna; el satélite la necesita
-- (SELECT ... WHERE borrado_at IS NULL) y el panel la lee para mostrar "Adjunto vencido" / responder 410.
-- Mismo DDL que scripts/create_retencion_satelite.py --ddl.
ALTER TABLE media_entrantes ADD COLUMN IF NOT EXISTS borrado_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_media_entrantes_vivos_created ON media_entrantes (created_at) WHERE borrado_at IS NULL;

-- ----------------------------------------------------------------------------
-- 13. retencion_log — una fila por bucket/tabla y por corrida del satélite
--     "Áurea — Retención (archivos y bandeja)" (2026-09-07, cron 04:30 Jujuy):
--     bucket = 'pacientes-media' (adjuntos del paciente > 90 días),
--     'panel-media' (adjuntos del staff > 90 días) o 'mensajes_entrantes_live'
--     (bandeja > 365 días). borrados/fallidos por corrida; detalle = notas
--     ("> 90 días", errores del DELETE de Storage, smoke). Lucas recibe WhatsApp
--     SOLO si fallidos > 0. Escritor: nodo "Registrar retencion_log"
--     (scripts/create_retencion_satelite.py). RLS habilitado SIN policies.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS retencion_log (
    id         SERIAL PRIMARY KEY,
    corrida_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bucket     TEXT,
    borrados   INT NOT NULL DEFAULT 0,
    fallidos   INT NOT NULL DEFAULT 0,
    detalle    TEXT
);
ALTER TABLE retencion_log ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- Verificación post-run (correr a mano, no forma parte del DDL):
--
--   SELECT table_name FROM information_schema.tables
--    WHERE table_schema='public' ORDER BY 1;
--   -- esperadas: conversaciones, documents, escalaciones_log, knowledge_base,
--   --            media_entrantes, n8n_chat_histories, pacientes, peticiones,
--   --            recordatorios_enviados, retencion_log, servicios, urgencias_log
--   --            (+ mensajes_entrantes_live, cuyo DDL vive en scripts/apply_inbox_live.py)
--
--   SELECT proname, pg_get_function_arguments(oid) FROM pg_proc
--    WHERE proname = 'match_documents';
--
--   -- smoke del RPC (vector dummy de 1536 ceros; debe devolver 0 filas sin error):
--   SELECT * FROM match_documents(array_fill(0, ARRAY[1536])::extensions.vector(1536), 1, '{}');
--
-- Después de este schema, en orden:
--   1. rebuild_v3_kb.py           (re-poblar knowledge_base + embeddings)
--   2. rebuild_v3_backfill_recordatorios.py (execs 230100 + 231766)
--   3. apply_supabase_v3_rewire.py (repuntar credenciales/URLs en n8n)
-- NO hacen falta resets de secuencia: base nueva, todo arranca de 1.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 9. Realtime para el panel en vivo (2026-09-06). La publicacion supabase_realtime existe en
--    todo proyecto Supabase pero SIN tablas; el panel se suscribe server-side a estas 4 y
--    empuja los cambios al navegador por SSE. Script idempotente: scripts/apply_realtime_publication_v3.py
--    (media_entrantes sumada el 2026-09-06 tarde: INSERT = adjunto del paciente ya en Storage)
-- ---------------------------------------------------------------------------
alter publication supabase_realtime add table public.mensajes_entrantes_live, public.n8n_chat_histories, public.pacientes, public.media_entrantes;
