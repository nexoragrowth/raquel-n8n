-- 2026-10-22 · Panel, Home comercial (pipeline). Solo agregados: NINGÚN dato de pacientes.
-- (1) embudo_mapa_motivos: traduce el "motivo de atención" de Dentalink a una etapa del embudo. Es configuración de la clínica (editable con SQL; el panel la lee).
-- (2) panel_embudo(): cuenta citas del espejo de la agenda (esquema agenda) por etapa y período. "Perdidas" = anulaciones puras + "No asiste"; los cambios de fecha y
--     reprogramaciones NO son pérdidas (se vio el 22/10: de 22 consultas anuladas, 11 eran "Cambio de fecha").
-- (3) panel_leads_nuevos(): contactos que escribieron por primera vez en los últimos días y todavía no tienen recordatorio de turno (no son pacientes con turno cercano).
create table if not exists public.embudo_mapa_motivos (
  patron text primary key,            -- se compara con ILIKE contra agenda.citas.motivo_atencion
  etapa  text not null check (etapa in ('consulta', 'devolucion', 'inicio_tto', 'tratamiento', 'control', 'urgencia')),
  orden  int  not null default 100    -- si un motivo matchea varios patrones gana el de menor orden
);
alter table public.embudo_mapa_motivos enable row level security;
revoke all on public.embudo_mapa_motivos from public, anon, authenticated;
grant select, insert, update, delete on public.embudo_mapa_motivos to service_role;
insert into public.embudo_mapa_motivos (patron, etapa, orden) values
  ('Consulta%',   'consulta',    10),
  ('Devoluci%',   'devolucion',  20),
  ('Escaneo%',    'devolucion',  21),
  ('Inicio%',     'inicio_tto',  30),
  ('En TTO%',     'tratamiento', 40),
  ('Control%',    'control',     50),
  ('Urgencia%',   'urgencia',    60)
on conflict (patron) do nothing;

drop function if exists public.panel_embudo(integer);
create or replace function public.panel_embudo(p_dias integer default 90)
returns table (etapa text, periodo text, total integer, atendidas integer, perdidas integer, reprogramadas integer, vigentes integer, sin_confirmar_7d integer)
language sql stable security definer set search_path = public, agenda
as $$
  with base as (
    select m.etapa,
           c.fecha,
           e.categoria,
           (e.categoria = 'anulada' and (e.nombre ilike 'Cambio de fecha%' or e.nombre ilike '%reprogram%')) as es_reprog
    from agenda.citas c
    join agenda.estados_cita e on e.dentalink_id = c.estado_id
    join lateral (
      select mm.etapa from public.embudo_mapa_motivos mm
      where c.motivo_atencion ilike mm.patron order by mm.orden limit 1
    ) m on true
    where c.fecha between current_date - 2 * greatest(p_dias, 7) and current_date + 60
  ),
  clasif as (
    select etapa, categoria, es_reprog, fecha,
           case when fecha > current_date then 'futuro'
                when fecha >= current_date - greatest(p_dias, 7) then 'actual'
                else 'previo' end as periodo
    from base
  )
  select etapa, periodo,
         count(*)::int,
         count(*) filter (where categoria in ('atendida', 'en_curso'))::int,
         count(*) filter (where categoria = 'no_asistio' or (categoria = 'anulada' and not es_reprog))::int,
         count(*) filter (where categoria = 'anulada' and es_reprog)::int,
         count(*) filter (where categoria <> 'anulada')::int,
         count(*) filter (where periodo = 'futuro' and categoria in ('pendiente', 'notificada') and fecha <= current_date + 7)::int
  from clasif
  group by etapa, periodo;
$$;
revoke all on function public.panel_embudo(integer) from public, anon, authenticated;
grant execute on function public.panel_embudo(integer) to service_role;

drop function if exists public.panel_leads_nuevos(integer, integer);
create or replace function public.panel_leads_nuevos(p_dias integer default 7, p_limite integer default 60)
returns table (telefono text, primer_msg_at timestamptz, ultimo_msg_at timestamptz, ultimo_rol text, msgs_paciente integer, atendido_por_humano boolean)
language sql stable security definer set search_path = public
as $$
  with msgs as (
    select c.telefono, c.rol, c.mensaje, c."timestamp",
           row_number() over (partition by c.telefono order by c."timestamp") as rn_asc,
           row_number() over (partition by c.telefono order by c."timestamp" desc) as rn_desc
    from public.conversaciones c
    where c.rol <> 'system'
  ),
  agr as (
    select telefono,
           min("timestamp") as primer_msg_at,
           max("timestamp") as ultimo_msg_at,
           max(rol) filter (where rn_desc = 1) as ultimo_rol,
           min(rol) filter (where rn_asc = 1) as primer_rol,
           count(*) filter (where rol = 'user')::int as msgs_paciente,
           bool_or(mensaje like '[ATENCION HUMANA%') as atendido_por_humano
    from msgs group by telefono
  )
  select a.telefono, a.primer_msg_at, a.ultimo_msg_at, a.ultimo_rol, a.msgs_paciente, a.atendido_por_humano
  from agr a
  where a.primer_rol = 'user'
    and a.primer_msg_at >= now() - make_interval(days => greatest(p_dias, 1))
    and not exists (select 1 from public.recordatorios_enviados r where r.telefono = a.telefono)
  order by a.ultimo_msg_at desc
  limit greatest(p_limite, 1);
$$;
revoke all on function public.panel_leads_nuevos(integer, integer) from public, anon, authenticated;
grant execute on function public.panel_leads_nuevos(integer, integer) to service_role;
