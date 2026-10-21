-- 2026-10-21 · Panel, fluidez de la lista de Conversaciones (Fase 1A del plan maestro).
-- Antes el panel traía las últimas 2000 filas COMPLETAS de `conversaciones` (~0,7 s) y calculaba en memoria el último mensaje y los no leídos de cada chat;
-- además, un chat cuyo último mensaje caía fuera de esas 2000 filas desaparecía de la lista y del buscador.
-- Esta función hace ese cálculo en la base: UNA fila (el último mensaje) por teléfono, con la cantidad de no leídos, más los mensajes de las últimas
-- p_recientes_horas (el panel los usa para no duplicar mensajes que ya llegaron por la memoria en vivo). Solo lectura. Solo service_role la ejecuta.
drop function if exists public.panel_ultimos_mensajes(integer, integer);
create or replace function public.panel_ultimos_mensajes(p_recientes_horas integer default 6, p_limite_chats integer default 800, p_no_leidos_dias integer default 7)
returns table (telefono text, rol text, mensaje text, fuente text, "timestamp" timestamptz, metadata jsonb, es_ultimo boolean, no_leidos integer)
language sql
stable
security definer
set search_path = public
as $$
  with ult as (
    select distinct on (c.telefono) c.telefono, c.rol, c.mensaje, c.fuente, c."timestamp", c.metadata
    from public.conversaciones c
    where c.rol <> 'system'
    order by c.telefono, c."timestamp" desc, c.id desc
  ),
  top as (
    select * from ult order by "timestamp" desc limit greatest(p_limite_chats, 1)
  ),
  nl as (
    select c.telefono, count(*)::int as n
    from public.conversaciones c
    join top t on t.telefono = c.telefono
    left join public.pacientes p on p.telefono = c.telefono
    where c.rol = 'user'
      and c."timestamp" > now() - make_interval(days => greatest(p_no_leidos_dias, 1))   -- el contador de no leídos mira los últimos días (como la ventana de antes), no todo el historial
      and (p.panel_last_read_at is null or c."timestamp" > p.panel_last_read_at)
    group by c.telefono
  )
  select t.telefono, t.rol, t.mensaje, t.fuente, t."timestamp", t.metadata, true, coalesce(nl.n, 0)
  from top t left join nl on nl.telefono = t.telefono
  union all
  select r.telefono, r.rol, r.mensaje, r.fuente, r."timestamp", r.metadata, false, 0
  from public.conversaciones r
  join top t on t.telefono = r.telefono
  where r.rol <> 'system'
    and r."timestamp" > now() - make_interval(hours => greatest(p_recientes_horas, 0))
    and not (r."timestamp" = t."timestamp" and r.mensaje = t.mensaje and r.rol = t.rol);
$$;

revoke all on function public.panel_ultimos_mensajes(integer, integer, integer) from public, anon, authenticated;
grant execute on function public.panel_ultimos_mensajes(integer, integer, integer) to service_role;
