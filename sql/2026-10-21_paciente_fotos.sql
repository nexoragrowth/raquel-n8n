-- 2026-10-21 · Panel, fotos de perfil de WhatsApp (Fase 2 del plan maestro).
-- Guarda la URL de la foto (96 px, https://pps.whatsapp.net/...) de cada contacto con su vencimiento (parámetro `oe` de la URL: ~10 días), para que la lista de
-- Conversaciones no pida una foto por fila a Evolution. 'sin_foto' = el contacto no tiene o la tiene oculta (se reconsulta a los 7 días).
-- A propósito NO está en la publicación supabase_realtime y NO es una columna de `pacientes`: cualquier UPDATE en `pacientes` dispara un evento en vivo que
-- hace recargar la lista de todos los paneles abiertos.
create table if not exists public.paciente_fotos (
  telefono      text primary key,
  estado        text not null check (estado in ('ok', 'sin_foto')),
  url           text,
  foto_id       text,
  expira_at     timestamptz,
  consultada_at timestamptz not null default now(),
  constraint paciente_fotos_ok_con_url check ((estado = 'ok') = (url is not null)),
  constraint paciente_fotos_host check (url is null or url like 'https://pps.whatsapp.net/%')
);
alter table public.paciente_fotos enable row level security;
revoke all on public.paciente_fotos from public, anon, authenticated;
grant select, insert, update, delete on public.paciente_fotos to service_role;
create index if not exists paciente_fotos_consultada_idx on public.paciente_fotos (consultada_at);
