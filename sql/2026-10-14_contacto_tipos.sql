-- =====================================================================================================================
-- sql/2026-10-14_contacto_tipos.sql  -  Dia 1 de la segmentacion de contactos
-- Plan: docs/plan-contactos-conversion-dentalink-2026-10-13.md (2.2 tipos y regla del mas restrictivo, 2.5 contacto_ruta,
-- 2.6 Dia 1, Anexo A modelo, Anexo B permisos).
--
-- ADITIVA E IDEMPOTENTE: no altera ninguna tabla existente (solo crea una FK nueva que APUNTA a pacientes(id)); se puede
-- correr dos veces. Correr como postgres (duenio de pacientes). Una sola transaccion: si algo falla, no queda nada.
--
-- Crea (Dia 1):
--   contacto_roles            historial de tipos. Un tipo NUNCA se edita ni se borra: se cierra una sola vez (hasta,
--                             quitado_por, motivo_baja). Sin texto libre (motivos de lista cerrada).
--   contacto_roles_notas      la nota libre opcional, en tabla aparte BORRABLE (derecho de supresion).
--   contacto_tel_normalizar() misma normalizacion que el v6 (Edit Fields - Extraer Datos).
--   contacto_ruta()           LECTURA. La llaman el v6 a la entrada y a la salida (y el panel despues). STABLE, barata.
--   contacto_tipo_poner()     ESCRITURA (Dia 1: solo el duenio; la usan el cargador de la lista y la prueba E2E).
--   contacto_tipo_cerrar()    ESCRITURA (idem). Deshacer = cerrar, nunca borrar.
-- NO crea (va en el "modelo unico" de la semana del 02/11): cola_clasificacion, eventos, leads, motivos_perdida,
--   columnas nuevas de pacientes, vista contactos, rol bot_n8n.
-- =====================================================================================================================
begin;
set local lock_timeout = '3s';       -- crear la FK toma un lock corto (SHARE ROW EXCLUSIVE) en pacientes: si hay una
                                     -- escritura larga en curso, la migracion falla en vez de hacer esperar al bot.
set local statement_timeout = '60s';

-- ---------------------------------------------------------------------------------------------------------------------
-- 1. Historial de tipos
-- ---------------------------------------------------------------------------------------------------------------------
create table if not exists public.contacto_roles (
  id           bigint generated always as identity primary key,
  contacto_id  bigint      not null,
  tipo         text        not null,
  subtipo      text,
  origen       text        not null,           -- por donde entro el cambio
  motivo       text        not null,           -- por que (lista cerrada; la nota libre va en contacto_roles_notas)
  puesto_por   text        not null,           -- quien (actor: 'lucas', 'dra', 'irina', 'sistema', usuario del panel)
  desde        timestamptz not null default now(),
  hasta        timestamptz,                    -- null = vigente
  quitado_por  text,
  motivo_baja  text,
  clave        uuid,                           -- idempotencia del alta (doble clic / re-corrida del cargador)
  clave_baja   uuid,                           -- idempotencia del cierre
  created_at   timestamptz not null default now(),
  constraint contacto_roles_contacto_fk foreign key (contacto_id) references public.pacientes (id) on delete restrict,
  -- 'prueba' NO es un tipo: la marca de prueba va en pacientes.es_prueba (lista fija por migracion, Anexo A, modelo unico del 02/11).
  -- Un telefono de prueba sin tipo no silencia, que es lo que hace falta el Dia 1.
  constraint contacto_roles_tipo_chk check (tipo in ('interno', 'colega', 'proveedor', 'no_paciente', 'paciente', 'familiar', 'grupo')),
  constraint contacto_roles_subtipo_chk check (
    subtipo is null or subtipo = 'otro'
    or (tipo = 'interno'     and subtipo in ('dra', 'secretaria', 'empleada', 'profesional'))
    or (tipo = 'colega'      and subtipo in ('odontologo', 'medico', 'centro_imagenes', 'consultorio'))
    or (tipo = 'proveedor'   and subtipo in ('laboratorio', 'insumos', 'farmacia', 'comercio', 'servicio'))
    or (tipo = 'no_paciente' and subtipo in ('conocido', 'equivocado', 'spam', 'autorespuesta', 'publicidad'))),
  constraint contacto_roles_origen_chk check (origen in ('precarga', 'panel', 'sistema', 'script')),
  constraint contacto_roles_motivo_chk check (motivo in (
    'precarga_confirmada',          -- precarga oct-2026, confirmado uno por uno por un admin (Lucas)
    'precarga_propuesta_revisada',  -- precarga oct-2026, propuesto por nombre y pistas (sin leer mensajes), revisado por un admin
    'clasificacion_manual',         -- una persona lo clasifico (panel o script)
    'cola_resuelta',                -- resuelto desde la cola "Por clasificar" (desde el 02/11)
    'directorio',                   -- coincidio con el directorio de colegas/proveedores y una persona lo confirmo
    'hecho_ficha',                  -- el sistema: tiene ficha en la agenda
    'hecho_grupo',                  -- el sistema: JID de grupo
    'prueba_e2e',                   -- marca temporal para una prueba de punta a punta (se cierra en el mismo turno)
    'correccion',                   -- corrige un tipo mal puesto
    'otro')),                       -- exige nota
  constraint contacto_roles_motivo_baja_chk check (motivo_baja is null or motivo_baja in (
    'reclasificado', 'error_carga', 'deshacer_precarga', 'fin_prueba', 'revision_90_dias', 'es_paciente', 'supresion', 'otro')),
  constraint contacto_roles_actor_chk check (
    puesto_por ~ '^[a-z0-9][a-z0-9._@+-]{0,63}$'
    and (quitado_por is null or quitado_por ~ '^[a-z0-9][a-z0-9._@+-]{0,63}$')),
  constraint contacto_roles_vigencia_chk check (hasta is null or hasta >= desde),
  constraint contacto_roles_cierre_chk check (
    (hasta is null) = (motivo_baja is null) and (hasta is null) = (quitado_por is null) and (clave_baja is null or hasta is not null)),
  constraint contacto_roles_clave_uk unique (clave),
  constraint contacto_roles_clave_baja_uk unique (clave_baja)
);

-- un solo registro VIGENTE por (contacto, tipo); varios tipos distintos pueden convivir (colega + paciente): manda el mas restrictivo.
-- Este indice tambien sirve la lectura de contacto_ruta (contacto_id = X and hasta is null).
create unique index if not exists contacto_roles_vigente_uk on public.contacto_roles (contacto_id, tipo) where hasta is null;
-- historial de un contacto y chequeo de la FK cuando alguien intenta borrar una fila de pacientes
create index if not exists contacto_roles_contacto_idx on public.contacto_roles (contacto_id, desde desc);

comment on table public.contacto_roles is
  'Tipos de contacto (plan 2026-10-13 2.2/Anexo A). Un tipo nunca se edita ni se borra: se cierra una vez. Vigente = hasta is null. '
  'Escribir solo con contacto_tipo_poner / contacto_tipo_cerrar. Leer el silencio solo con contacto_ruta().';

-- ---------------------------------------------------------------------------------------------------------------------
-- 2. Nota libre opcional (borrable: derecho de supresion). Nunca telefonos ni texto de pacientes.
-- ---------------------------------------------------------------------------------------------------------------------
create table if not exists public.contacto_roles_notas (
  id          bigint generated always as identity primary key,
  rol_id      bigint not null references public.contacto_roles (id) on delete cascade,
  momento     text   not null check (momento in ('alta', 'baja')),
  nota        text   not null check (btrim(nota) <> '' and char_length(nota) <= 300 and nota !~ '[0-9]{7,}'),
  creada_por  text   not null check (creada_por ~ '^[a-z0-9][a-z0-9._@+-]{0,63}$'),
  created_at  timestamptz not null default now(),
  constraint contacto_roles_notas_uk unique (rol_id, momento)
);

-- ---------------------------------------------------------------------------------------------------------------------
-- 3. Inmutabilidad: solo se cierra, una vez; no se borra; no se vacia.
-- ---------------------------------------------------------------------------------------------------------------------
create or replace function public.contacto_roles_tg_inmutable() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'contacto_roles: un tipo no se borra; se cierra con contacto_tipo_cerrar()' using errcode = 'restrict_violation';
  end if;
  if old.hasta is not null then
    raise exception 'contacto_roles: el tipo % ya estaba cerrado (se cierra una sola vez)', old.id using errcode = 'restrict_violation';
  end if;
  if new.hasta is null
     or (to_jsonb(new) - array['hasta', 'quitado_por', 'motivo_baja', 'clave_baja'])
        is distinct from (to_jsonb(old) - array['hasta', 'quitado_por', 'motivo_baja', 'clave_baja']) then
    raise exception 'contacto_roles: un tipo no se edita; lo unico permitido es cerrarlo (hasta, quitado_por, motivo_baja)' using errcode = 'restrict_violation';
  end if;
  if new.hasta > now() + interval '1 minute' then
    raise exception 'contacto_roles: hasta no puede quedar en el futuro' using errcode = 'check_violation';
  end if;
  return new;
end $$;

create or replace function public.contacto_roles_tg_no_truncate() returns trigger
language plpgsql set search_path = '' as $$
begin
  raise exception 'contacto_roles: no se vacia con TRUNCATE; los tipos se cierran' using errcode = 'restrict_violation';
end $$;

create or replace trigger contacto_roles_inmutable_trg before update or delete on public.contacto_roles
  for each row execute function public.contacto_roles_tg_inmutable();
create or replace trigger contacto_roles_no_truncate_trg before truncate on public.contacto_roles
  for each statement execute function public.contacto_roles_tg_no_truncate();

-- ---------------------------------------------------------------------------------------------------------------------
-- 4. Telefono: la MISMA clave que el v6 guarda en pacientes.telefono.
--    v6 (Edit Fields - Extraer Datos): JID '...@s.whatsapp.net' -> lo de antes de '@' y de ':' (549XXXXXXXXXX para AR);
--    '@lid' y '@g.us' quedan enteros. Aca ademas se toleran '+', espacios, guiones y parentesis en un numero escrito a mano
--    ('+54 9 388 ...'). NUNCA agrega ni saca el 9 ni el 54 (no se adivina: dos numeros distintos nunca terminan en la misma clave).
-- ---------------------------------------------------------------------------------------------------------------------
create or replace function public.contacto_tel_normalizar(p_telefono text) returns text
language sql immutable parallel safe set search_path = '' as $$
  select nullif(case when x ~ '@s\.whatsapp\.net$'    then split_part(split_part(x, '@', 1), ':', 1)
                     when x ~ '^\+?[0-9][0-9 ().-]*$' then regexp_replace(x, '[^0-9]', '', 'g')
                     else x end, '')
  from (select left(btrim(coalesce(p_telefono, '')), 80) as x) s
$$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 5. contacto_ruta (version Dia 1 del 2.5: ordenes 1-3). SOLO LEE. Un indice por tabla. Devuelve jsonb (se le agregan
--    claves en el PUT-D sin cambiar la firma). Precedencia (el mas restrictivo manda):
--      grupo > interno > no_paciente > proveedor = colega > paciente = familiar > (sin tipo = prospecto)
--    silencia: grupo, interno, no_paciente, proveedor, colega.   red (aviso al grupo con senal fuerte): no_paciente, proveedor, colega.
--    Sin tipo (o telefono desconocido): {"tipo": null, "silencia": false, "red": false, "fuente": "sin_tipo"} = el v6 de hoy.
--    Telefono vacio: ok=false, error 'telefono_vacio', silencia=false (deja pasar).
--    No mira modo humano ni seg:off: eso sigue en el v6 (Consultar Takeover Paciente / Redis).
-- ---------------------------------------------------------------------------------------------------------------------
create or replace function public.contacto_ruta(p_telefono text) returns jsonb
language sql stable security definer set search_path = '' as $$
  with k as (
    select array['grupo', 'interno', 'no_paciente', 'proveedor', 'colega', 'paciente', 'familiar']::text[] as orden
  ), e as (
    select public.contacto_tel_normalizar(p_telefono) as tel
  ), c as (
    select e.tel, p.id from e left join public.pacientes p on p.telefono = e.tel
  ), w as (
    select c.tel, c.id,
           (array_agg(r.tipo       order by array_position(k.orden, r.tipo), r.id))[1] as tipo,
           (array_agg(r.subtipo    order by array_position(k.orden, r.tipo), r.id))[1] as subtipo,
           (array_agg(r.desde      order by array_position(k.orden, r.tipo), r.id))[1] as desde,
           (array_agg(r.puesto_por order by array_position(k.orden, r.tipo), r.id))[1] as puesto_por,
           coalesce(jsonb_agg(r.tipo order by array_position(k.orden, r.tipo), r.id) filter (where r.id is not null), '[]'::jsonb) as tipos
    from c cross join k
    left join public.contacto_roles r on r.contacto_id = c.id and r.hasta is null
    group by c.tel, c.id
  ), f as (
    select w.*, coalesce(w.tipo, case when w.tel ~ '@(g\.us|broadcast)$' then 'grupo' end) as tipo_ef from w
  )
  select jsonb_build_object(
           'v', 1,
           'ok', f.tel is not null,
           'contacto_id', f.id,
           'tipo', f.tipo_ef,
           'subtipo', f.subtipo,
           'tipos', f.tipos,
           'silencia', coalesce(f.tipo_ef in ('grupo', 'interno', 'no_paciente', 'proveedor', 'colega'), false),
           'red', coalesce(f.tipo_ef in ('no_paciente', 'proveedor', 'colega'), false),
           'desde', f.desde,
           'puesto_por', f.puesto_por,
           'fuente', case when f.tipo is not null then 'tipo' when f.tipo_ef = 'grupo' then 'jid_grupo' else 'sin_tipo' end)
         || case when f.tel is null then jsonb_build_object('error', 'telefono_vacio') else '{}'::jsonb end
  from f
$$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 6. Escritura (Dia 1: solo el duenio = postgres; el panel la recibe cuando tenga login por usuario, con el actor verificado)
-- ---------------------------------------------------------------------------------------------------------------------
create or replace function public.contacto_tipo_poner(
  p_telefono text, p_tipo text, p_motivo text, p_puesto_por text,
  p_origen text default 'script', p_subtipo text default null, p_nota text default null,
  p_clave uuid default null, p_confirmo_ficha boolean default false)
returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_tel   text := public.contacto_tel_normalizar(p_telefono);
  v_actor text := lower(btrim(coalesce(p_puesto_por, '')));
  v_nota  text := nullif(btrim(coalesce(p_nota, '')), '');
  v_id    bigint;
  v_rol   bigint;
  v_prev  public.contacto_roles;
begin
  if v_tel is null then
    return jsonb_build_object('ok', false, 'error', 'TELEFONO_VACIO');
  end if;
  if p_tipo is null or p_tipo not in ('interno', 'colega', 'proveedor', 'no_paciente', 'paciente', 'familiar', 'grupo') then
    return jsonb_build_object('ok', false, 'error', 'TIPO_INVALIDO');   -- 'dudoso' no es un tipo: va a la cola (02/11); 'prueba' va en es_prueba
  end if;
  if p_motivo = 'otro' and v_nota is null then
    return jsonb_build_object('ok', false, 'error', 'NOTA_REQUERIDA');
  end if;
  select p.id into v_id from public.pacientes p where p.telefono = v_tel;
  if v_id is null then
    return jsonb_build_object('ok', false, 'error', 'CONTACTO_NO_EXISTE');
  end if;
  perform pg_advisory_xact_lock(hashtextextended('contacto_roles|' || v_id::text, 0));
  if p_clave is not null then
    select * into v_prev from public.contacto_roles r where r.clave = p_clave;
    if found then
      if v_prev.contacto_id <> v_id or v_prev.tipo <> p_tipo then
        return jsonb_build_object('ok', false, 'error', 'CLAVE_EN_USO');
      end if;
      return jsonb_build_object('ok', true, 'repetido', true, 'rol_id', v_prev.id, 'vigente', v_prev.hasta is null);
    end if;
  end if;
  select r.id into v_rol from public.contacto_roles r where r.contacto_id = v_id and r.tipo = p_tipo and r.hasta is null;
  if v_rol is not null then
    return jsonb_build_object('ok', true, 'ya_estaba', true, 'rol_id', v_rol);
  end if;
  -- doble confirmacion si un tipo que silencia cae sobre alguien con turnos en la agenda (plan 2.2 y 8). Solo LEE recordatorios_enviados.
  if p_tipo in ('interno', 'colega', 'proveedor', 'no_paciente')
     and exists (select 1 from public.recordatorios_enviados re where re.telefono = v_tel)
     and not coalesce(p_confirmo_ficha, false) then
    return jsonb_build_object('ok', false, 'error', 'TIENE_FICHA');
  end if;
  insert into public.contacto_roles (contacto_id, tipo, subtipo, origen, motivo, puesto_por, clave)
  values (v_id, p_tipo, p_subtipo, p_origen, p_motivo, v_actor, p_clave)
  returning id into v_rol;
  if v_nota is not null then
    insert into public.contacto_roles_notas (rol_id, momento, nota, creada_por) values (v_rol, 'alta', v_nota, v_actor);
  end if;
  return jsonb_build_object('ok', true, 'repetido', false, 'ya_estaba', false, 'rol_id', v_rol, 'ruta', public.contacto_ruta(v_tel));
end $$;

create or replace function public.contacto_tipo_cerrar(
  p_telefono text, p_tipo text, p_motivo_baja text, p_quitado_por text,
  p_nota text default null, p_clave_baja uuid default null)
returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_tel   text := public.contacto_tel_normalizar(p_telefono);
  v_actor text := lower(btrim(coalesce(p_quitado_por, '')));
  v_nota  text := nullif(btrim(coalesce(p_nota, '')), '');
  v_id    bigint;
  v_rol   bigint;
  v_prev  public.contacto_roles;
begin
  if v_tel is null then
    return jsonb_build_object('ok', false, 'error', 'TELEFONO_VACIO');
  end if;
  if p_motivo_baja = 'otro' and v_nota is null then
    return jsonb_build_object('ok', false, 'error', 'NOTA_REQUERIDA');
  end if;
  select p.id into v_id from public.pacientes p where p.telefono = v_tel;
  if v_id is null then
    return jsonb_build_object('ok', false, 'error', 'CONTACTO_NO_EXISTE');
  end if;
  perform pg_advisory_xact_lock(hashtextextended('contacto_roles|' || v_id::text, 0));
  if p_clave_baja is not null then
    select * into v_prev from public.contacto_roles r where r.clave_baja = p_clave_baja;
    if found then
      if v_prev.contacto_id <> v_id or v_prev.tipo <> p_tipo then
        return jsonb_build_object('ok', false, 'error', 'CLAVE_EN_USO');
      end if;
      return jsonb_build_object('ok', true, 'repetido', true, 'rol_id', v_prev.id);
    end if;
  end if;
  update public.contacto_roles r
     set hasta = now(), quitado_por = v_actor, motivo_baja = p_motivo_baja, clave_baja = p_clave_baja
   where r.contacto_id = v_id and r.tipo = p_tipo and r.hasta is null
  returning r.id into v_rol;
  if v_rol is null then
    return jsonb_build_object('ok', true, 'ya_estaba_cerrado', true, 'ruta', public.contacto_ruta(v_tel));
  end if;
  if v_nota is not null then
    insert into public.contacto_roles_notas (rol_id, momento, nota, creada_por) values (v_rol, 'baja', v_nota, v_actor);
  end if;
  return jsonb_build_object('ok', true, 'repetido', false, 'rol_id', v_rol, 'ruta', public.contacto_ruta(v_tel));
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 7. Permisos (Anexo B). RLS sin policies = nada para roles sin BYPASSRLS. Grants explicitos, aunque los defaults esten abiertos.
--    Lee:     service_role (Gate Humano Final por PostgREST con la clave secreta; despues el panel) -> SOLO EXECUTE de contacto_ruta.
--             postgres (n8n hoy entra como postgres, duenio) -> todo, por ser duenio.
--    Escribe: solo postgres (duenio), y solo por contacto_tipo_poner / contacto_tipo_cerrar (los triggers frenan el resto).
--    anon / authenticated: nada.
-- ---------------------------------------------------------------------------------------------------------------------
alter table public.contacto_roles enable row level security;
alter table public.contacto_roles_notas enable row level security;
revoke all on table public.contacto_roles, public.contacto_roles_notas from public, anon, authenticated, service_role;
do $$
declare s text;
begin
  foreach s in array array[pg_get_serial_sequence('public.contacto_roles', 'id'), pg_get_serial_sequence('public.contacto_roles_notas', 'id')] loop
    execute format('revoke all on sequence %s from public, anon, authenticated, service_role', s);
  end loop;
end $$;
revoke all on function public.contacto_roles_tg_inmutable()   from public, anon, authenticated, service_role;
revoke all on function public.contacto_roles_tg_no_truncate() from public, anon, authenticated, service_role;
revoke all on function public.contacto_tel_normalizar(text)   from public, anon, authenticated, service_role;
revoke all on function public.contacto_ruta(text)             from public, anon, authenticated;
grant execute on function public.contacto_ruta(text) to service_role;
revoke all on function public.contacto_tipo_poner(text, text, text, text, text, text, text, uuid, boolean) from public, anon, authenticated, service_role;
revoke all on function public.contacto_tipo_cerrar(text, text, text, text, text, uuid)                     from public, anon, authenticated, service_role;

-- Defaults para lo que se cree DESPUES (Anexo B punto 3). Solo para el duenio postgres: los de supabase_admin no se pueden
-- cambiar desde postgres (no es miembro de supabase_admin). No toca objetos existentes; service_role conserva sus defaults.
alter default privileges for role postgres in schema public revoke all on tables    from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on functions from anon, authenticated;
alter default privileges for role postgres revoke execute on functions from public;

-- ---------------------------------------------------------------------------------------------------------------------
-- 8. Autochequeo: si la tabla ya existia con otra forma (create table if not exists la saltea), abortar todo.
-- ---------------------------------------------------------------------------------------------------------------------
do $$
declare v_cols text;
begin
  select string_agg(column_name, ',' order by ordinal_position) into v_cols
    from information_schema.columns where table_schema = 'public' and table_name = 'contacto_roles';
  if v_cols is distinct from 'id,contacto_id,tipo,subtipo,origen,motivo,puesto_por,desde,hasta,quitado_por,motivo_baja,clave,clave_baja,created_at' then
    raise exception 'contacto_roles existe con otra forma: %', v_cols;
  end if;
  if not exists (select 1 from pg_indexes where schemaname = 'public' and indexname = 'contacto_roles_vigente_uk') then
    raise exception 'falta el indice contacto_roles_vigente_uk';
  end if;
  if (select count(*) from pg_trigger where tgrelid = 'public.contacto_roles'::regclass and not tgisinternal) <> 2 then
    raise exception 'contacto_roles: triggers distintos de los esperados';
  end if;
  -- Anexo B: TODOS los objetos nuevos, para anon / authenticated / service_role (service_role: solo EXECUTE de contacto_ruta)
  if exists (
       select 1
         from unnest(array['anon', 'authenticated', 'service_role']) rol,
              unnest(array['public.contacto_roles', 'public.contacto_roles_notas']) tab,
              unnest(array['select', 'insert', 'update', 'delete', 'truncate', 'references', 'trigger']) priv
        where has_table_privilege(rol, tab, priv))
     or exists (
       select 1
         from unnest(array['anon', 'authenticated', 'service_role']) rol,
              unnest(array['public.contacto_tel_normalizar(text)', 'public.contacto_ruta(text)',
                           'public.contacto_tipo_poner(text,text,text,text,text,text,text,uuid,boolean)',
                           'public.contacto_tipo_cerrar(text,text,text,text,text,uuid)',
                           'public.contacto_roles_tg_inmutable()', 'public.contacto_roles_tg_no_truncate()']) fn
        where has_function_privilege(rol, fn, 'execute') and not (rol = 'service_role' and fn = 'public.contacto_ruta(text)'))
     or not has_function_privilege('service_role', 'public.contacto_ruta(text)', 'execute') then
    raise exception 'permisos de los objetos nuevos distintos de los esperados (Anexo B)';
  end if;
end $$;

notify pgrst, 'reload schema';   -- PostgREST ve la funcion nueva (Supabase igual lo hace solo con pgrst_ddl_watch)
commit;
