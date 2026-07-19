-- =============================================================================
-- recordatorios_config  —  control escalable de recordatorios (Dra. Raquel)
-- =============================================================================
-- Fila única (id=1) que el workflow de Recordatorios lee UNA vez por corrida
-- (1 SELECT/día, cero timers nuevos) y que el panel escribe on-demand.
--
-- Principio de ingeniería: el "calendario de suspensiones" es DATO evaluado
-- durante la corrida que YA ocurre (el cron diario), NO un scheduler nuevo.
-- Suspender un día = poner esa fecha en dias_suspendidos; al día siguiente
-- la fecha ya no está → corre solo. Auto-resume gratis, sin saturación.
--
-- Aplicar en el SQL Editor del proyecto v3 (eoizfjsyejixjzwgzwkt). Idempotente.
-- =============================================================================

create table if not exists public.recordatorios_config (
  id                smallint     primary key default 1,
  activo            boolean      not null default true,   -- on/off maestro (lo lee el gate)
  hora_envio        smallint     not null default 8,      -- hora ART, informativa (el cron real lo setea el panel via n8n API)
  dias_suspendidos  date[]       not null default '{}',   -- días sueltos salteados (auto-resume: sólo saltea esas fechas)
  suspender_desde   date,                                 -- rango de suspensión (vacaciones); null = sin rango
  suspender_hasta   date,
  updated_at        timestamptz  not null default now(),
  updated_by        text,                                 -- quién lo tocó desde el panel (auditoría)
  constraint recordatorios_config_singleton check (id = 1)
);

-- Semilla: la fila 1 siempre existe (el gate hace fail-open si faltara, igual).
insert into public.recordatorios_config (id) values (1)
on conflict (id) do nothing;

-- RLS on para consistencia con el resto de v3. service_role (panel) y el usuario
-- del pooler (n8n) bypassean RLS → no hacen falta policies.
alter table public.recordatorios_config enable row level security;

-- =============================================================================
-- GATE (query que corre el nodo Postgres nuevo del workflow, 1 vez por corrida)
-- Devuelve SIEMPRE una fila con debe_correr boolean. Fail-open: si la fila no
-- existe, bool_and sobre conjunto vacío = NULL → coalesce → true (los
-- recordatorios NO se cortan solos por un problema de config).
-- =============================================================================
-- select coalesce(bool_and(
--     c.activo
--     and not ((now() at time zone 'America/Argentina/Jujuy')::date = any(c.dias_suspendidos))
--     and not (c.suspender_desde is not null
--              and (now() at time zone 'America/Argentina/Jujuy')::date
--                  between c.suspender_desde and c.suspender_hasta)
--   ), true) as debe_correr
-- from public.recordatorios_config c
-- where c.id = 1;
-- =============================================================================
