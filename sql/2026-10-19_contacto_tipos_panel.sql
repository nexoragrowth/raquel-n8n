-- 2026-10-19 · Tipos de contacto desde el PANEL (nexora-whatsapp-agent).
-- El panel habla con el Supabase v3 con la service key (solo server-side). La migración del 14/10 dejó las funciones de escritura
-- solo para el dueño; acá se habilitan para service_role (el panel) y se agrega una lectura de los tipos vigentes.
-- Aditiva e idempotente. Deshacer: revoke execute ... from service_role; drop function public.contacto_tipos_vigentes();
begin;

grant execute on function public.contacto_tipo_poner(text, text, text, text, text, text, text, uuid, boolean) to service_role;
grant execute on function public.contacto_tipo_cerrar(text, text, text, text, text, uuid) to service_role;

-- Tipos VIGENTES (hasta is null) por teléfono, para la lista de chats y el encabezado del chat. Solo lectura.
create or replace function public.contacto_tipos_vigentes()
returns table (telefono text, tipo text, subtipo text, desde timestamptz, puesto_por text)
language sql stable security definer set search_path = '' as $$
  select p.telefono, r.tipo, r.subtipo, r.desde, r.puesto_por
  from public.contacto_roles r
  join public.pacientes p on p.id = r.contacto_id
  where r.hasta is null
$$;
revoke all on function public.contacto_tipos_vigentes() from public, anon, authenticated;
grant execute on function public.contacto_tipos_vigentes() to service_role;

commit;
