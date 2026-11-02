-- 2026-11-02 · Panel, usuarios que se crean desde la pantalla "Usuarios" (la secretaria cambia seguido).
-- Los usuarios "principales" siguen en la variable de entorno PANEL_USERS del panel; esta tabla guarda SOLO los que se crean/desactivan desde el panel.
-- salt + hash = el mismo scrypt que PANEL_USERS (lib/simple-auth.ts hashPassword: scrypt(pass, salt, 32) en hex). Nunca se guarda la contraseña.
-- login: minúsculas, 3 a 32 caracteres, empieza con letra o número (misma regla que valida el panel en lib/usuarios/reglas.ts).
-- A propósito NO está en la publicación supabase_realtime. RLS activada SIN policies: solo service_role (el panel, del lado servidor) la lee y escribe.
create table if not exists public.panel_usuarios (
  login           text primary key,
  nombre          text,
  salt            text not null,
  hash            text not null,
  activo          boolean not null default true,
  creado_por      text,
  created_at      timestamptz not null default now(),
  desactivado_at  timestamptz,
  desactivado_por text,
  constraint panel_usuarios_login_forma check (login ~ '^[a-z0-9][a-z0-9._-]{2,31}$')
);
alter table public.panel_usuarios enable row level security;
revoke all on public.panel_usuarios from public, anon, authenticated;
grant select, insert, update, delete on public.panel_usuarios to service_role;
create index if not exists panel_usuarios_activo_idx on public.panel_usuarios (activo);

-- Autochequeo: si algo quedó abierto, la migración falla y no se aplica.
do $$
begin
  if not (select relrowsecurity from pg_class where oid = 'public.panel_usuarios'::regclass) then
    raise exception 'panel_usuarios: falta RLS';
  end if;
  if has_table_privilege('anon', 'public.panel_usuarios', 'select') or has_table_privilege('authenticated', 'public.panel_usuarios', 'select') then
    raise exception 'panel_usuarios: anon/authenticated no deben poder leer (tiene hashes)';
  end if;
  if not has_table_privilege('service_role', 'public.panel_usuarios', 'select') then
    raise exception 'panel_usuarios: service_role tiene que poder leer';
  end if;
end $$;
