-- =====================================================================================================================
-- PROPUESTA (20/10/2026) — NO APLICADA. Lectura del espejo de la agenda para la pantalla Seguimientos del panel
-- (REC-05, lista "No vino"). El panel ya la llama (lib/fuentes/seguimientos.ts); mientras no exista, la lista muestra
-- "Falta conectar la lectura de la agenda propia" y la otra lista funciona igual.
--
-- Por qué una función y no exponer el esquema: `agenda` NO va a "Exposed schemas" de PostgREST (plan de migración del
-- 20/10, Permisos) y así sigue. Esta función:
--   - es de SOLO LECTURA (language sql, stable, sin DML);
--   - es security definer con search_path vacío (todo calificado con el esquema);
--   - la ejecuta SOLO service_role (el server del panel), nunca anon ni authenticated;
--   - devuelve solo id de cita, fecha, hora, categoría del estado y la hora de la última copia buena del espejo:
--     ningún dato de la persona. El teléfono y el nombre los cruza el panel con recordatorios_enviados, que ya lee.
--
-- Filas: las citas "No asiste" (categoría no_asistio) desde p_desde, más las citas con recordatorio desde p_desde (con su
-- categoría: así el panel sabe si el turno posterior sigue vigente o se anuló). Medido el 20/10 con p_desde = hoy − 60:
-- 238 filas (7 "No asiste"), 1,1 ms en la base.
--
-- Dónde va: raquel-n8n/sql/ con su DOWN, aplicada por conexión directa como postgres, igual que el resto del esquema.
-- =====================================================================================================================

create or replace function public.panel_seguimientos_citas(p_desde date)
returns table (dentalink_id bigint, fecha date, hora_inicio time, categoria text, espejo_at timestamptz)
language sql
stable
security definer
set search_path = ''
as $$
  select c.dentalink_id,
         c.fecha,
         c.hora_inicio,
         e.categoria,
         (select max(s.fin) from agenda.sync_corridas s where s.estado = 'ok') as espejo_at
  from agenda.citas c
  join agenda.estados_cita e on e.id = c.estado_id
  where c.desaparecida_at is null
    and c.dentalink_id is not null
    and c.fecha >= greatest(p_desde, (now() at time zone 'America/Argentina/Jujuy')::date - 366)
    and (e.categoria = 'no_asistio'
         or exists (select 1 from public.recordatorios_enviados r where r.id_cita_dentalink = c.dentalink_id))
  order by c.fecha desc, c.dentalink_id desc
  limit 1000;
$$;

revoke all on function public.panel_seguimientos_citas(date) from public, anon, authenticated;
grant execute on function public.panel_seguimientos_citas(date) to service_role;

-- PostgREST cachea el esquema: después de crearla, `notify pgrst, 'reload schema';` para que el panel la vea al instante.

-- DOWN:
-- drop function if exists public.panel_seguimientos_citas(date);
