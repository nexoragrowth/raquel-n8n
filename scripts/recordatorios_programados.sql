-- =============================================================================
-- recordatorios_programados  —  "Programar recordatorios" (19/11/2026)
-- =============================================================================
-- La clínica programa desde el panel: "mañana a las 08:00 mandá los avisos de los turnos del 25, del 26 y del 27".
-- Una fila por fecha de turnos. El workflow "Recordatorios programados" (n8n, cada 2 min) toma las filas vencidas de a una
-- (FOR UPDATE SKIP LOCKED: nunca dos ejecuciones con la misma fila), dispara el MISMO envío que el botón Adelantar,
-- verifica contra la base y, si salieron todos y no_repetir = true, suspende la corrida automática que lo repetiría.
-- Aditiva e idempotente. El panel escribe (service_role) y n8n lee/actualiza (pooler); RLS prendido sin policies como el resto de v3.
-- =============================================================================

create table if not exists public.recordatorios_programados (
  id             bigint generated always as identity primary key,
  fecha_turno    date        not null,                         -- de qué día son los turnos a avisar
  enviar_el      timestamptz not null,                         -- cuándo mandarlos
  no_repetir     boolean     not null default true,            -- suspender la corrida automática que los repetiría
  estado         text        not null default 'pendiente'
                 check (estado in ('pendiente', 'enviando', 'enviado', 'cancelado', 'error', 'vencido')),
  resultado      jsonb,                                        -- { esperado, enviados, ya, suspendido, motivo }
  creado_por     text,
  creado_at      timestamptz not null default now(),
  cancelado_por  text,
  cancelado_at   timestamptz,
  ejecutado_at   timestamptz
);
-- (que enviar_el sea antes del turno lo validan el panel y el workflow: una CHECK con zona horaria no es inmutable)

-- Una sola programación VIGENTE por fecha de turnos (si ya hay una pendiente para el 25, no se puede duplicar).
create unique index if not exists recordatorios_programados_una_vigente
  on public.recordatorios_programados (fecha_turno) where estado in ('pendiente', 'enviando');

create index if not exists recordatorios_programados_pendientes
  on public.recordatorios_programados (enviar_el) where estado = 'pendiente';

alter table public.recordatorios_programados enable row level security;

comment on table public.recordatorios_programados is
  'Envíos de recordatorios programados desde el panel; los ejecuta el workflow "Recordatorios programados" de n8n.';
