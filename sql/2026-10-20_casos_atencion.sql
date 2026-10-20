-- =====================================================================================================================
-- sql/2026-10-20_casos_atencion.sql  -  ATE-02: base de la bandeja de Atencion (casos + registrar_aviso)
-- Backlog: docs/backlog-maestro-2026-10-19.md 3.4 (ATE-02). Pantalla: docs/diseno-premium-panel-2026-10-19.md 4.3 (ATE-03).
-- Test offline: node tests/test_migracion_casos_atencion.mjs (PGlite). NO APLICADA (20/10/2026).
--
-- ADITIVA E IDEMPOTENTE. No cambia ninguna columna de las tablas del bot: solo agrega un trigger AFTER INSERT a
-- escalaciones_log y otro a triaje_urgencias_log. Correr como postgres (duenio). Una sola transaccion.
-- Requiere la migracion del 14/10 (public.contacto_tel_normalizar).
--
-- Crea:
--   casos              un motivo abierto por contacto (tipo) con estado, duenio, contador y bitacora. Dedupe: UN caso abierto
--                      por (telefono, tipo); un aviso nuevo del mismo tipo suma al contador.
--   casos_eventos      bitacora (quien, que, cuando, estado antes/despues). La escriben solo las funciones de abajo.
--   casos_prefijos     etiqueta fija que el CODIGO del bot pone al principio del motivo -> tipo del caso (lista cerrada).
--   registrar_aviso()  el unico lugar que crea o suma a un caso. Idempotente por (tabla, id) del log.
--   casos_tipo_de_escalacion()  de que tipo es una fila de escalaciones_log.
--   casos_tg_desde_escalacion / casos_tg_desde_triaje   triggers FAIL-SAFE: cualquier error -> WARNING y el insert del
--                      bot entra igual (EXCEPTION WHEN OTHERS dentro de la funcion; lock_timeout de 1 s para no hacer esperar).
--   caso_tomar / caso_soltar / caso_esperando / caso_resolver / caso_reabrir   acciones del panel (service_role).
--   casos_backfill()   crea los casos de las ultimas N horas (por defecto 72) desde los logs; se corre al final.
--
-- EL TIPO SALE DE LO QUE REGISTRO EL BOT, NUNCA DEL TEXTO DEL PACIENTE (regla del backlog 4.6 y ATE-02):
--   1) una columna estructurada del log si algun dia existe (`tipo_aviso`, se lee con to_jsonb(new): hoy no hay);
--   2) la columna `origen` (triaje_video);
--   3) triaje_urgencias_log: columnas `accion` y `modo` (escalado y no sombra = urgencia);
--   4) la ETIQUETA FIJA que pone el codigo del bot al PRINCIPIO del motivo (plantillas de v7/clinica_core.js,
--      triaje/preparar_escalada.js, segmentacion/dia1/avisar_al_grupo.js, Health Check). Es un starts_with literal anclado
--      al inicio, contra la tabla casos_prefijos (sin regex). El texto del paciente va DESPUES de la etiqueta y no se mira.
--   Sin etiqueta conocida -> 'consulta' (Requiere secretaria): el lado seguro, nada se esconde.
--
-- Vuelta atras: sql/2026-10-20_casos_atencion_DOWN.sql (primero saca los triggers). Apagado rapido sin borrar nada:
--   alter table public.escalaciones_log disable trigger casos_desde_escalacion_trg;
--   alter table public.triaje_urgencias_log disable trigger casos_desde_triaje_trg;
-- =====================================================================================================================
begin;
set local lock_timeout = '3s';       -- crear un trigger toma un lock corto en escalaciones_log: si hay una escritura larga,
                                     -- la migracion falla en vez de hacer esperar al bot.
set local statement_timeout = '60s';

do $$
begin
  if to_regprocedure('public.contacto_tel_normalizar(text)') is null then
    raise exception 'falta public.contacto_tel_normalizar (sql/2026-10-14_contacto_tipos.sql)';
  end if;
  if to_regclass('public.escalaciones_log') is null or to_regclass('public.triaje_urgencias_log') is null then
    raise exception 'faltan escalaciones_log / triaje_urgencias_log';
  end if;
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 1. Casos
-- ---------------------------------------------------------------------------------------------------------------------
create table if not exists public.casos (
  id               bigint generated always as identity primary key,
  telefono         text        not null,                    -- misma clave que pacientes.telefono (contacto_tel_normalizar)
  tipo             text        not null,
  estado           text        not null default 'nuevo',
  motivo           text        not null,                    -- lo ultimo que registro el bot (max 500); el panel lo muestra en llano
  origen           text        not null,                    -- 'bot' | 'triaje_video' | 'triaje' | ... (de que log salio)
  contador         integer     not null default 1,          -- avisos de este motivo mientras estuvo abierto
  detalle          jsonb       not null default '{}'::jsonb,-- datos estructurados del log (tipo de triaje, confianza)
  dueno            text,                                    -- usuario del panel que lo tomo
  primer_aviso_at  timestamptz not null default now(),
  ultimo_aviso_at  timestamptz not null default now(),
  tomado_at        timestamptz,
  esperando_desde  timestamptz,
  resuelto_at      timestamptz,
  resuelto_por     text,
  nota_resolucion  text,
  devolver_bot     boolean,                                 -- lo que eligio quien resolvio (el panel hace el cambio de modo)
  ref_tabla        text,                                    -- ultimo log que SUMO al contador
  ref_id           bigint,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint casos_telefono_chk check (btrim(telefono) <> '' and char_length(telefono) <= 80),
  constraint casos_tipo_chk     check (tipo in ('urgencia', 'pago', 'pidio_persona', 'turno', 'consulta', 'aviso')),
  constraint casos_estado_chk   check (estado in ('nuevo', 'en_curso', 'esperando_paciente', 'resuelto')),
  constraint casos_contador_chk check (contador >= 1),
  constraint casos_motivo_chk   check (char_length(motivo) between 1 and 500),
  constraint casos_actor_chk    check (
    (dueno is null or dueno ~ '^[a-z0-9][a-z0-9._@+-]{0,63}$')
    and (resuelto_por is null or resuelto_por ~ '^[a-z0-9][a-z0-9._@+-]{0,63}$')),
  constraint casos_nota_chk     check (nota_resolucion is null or (char_length(nota_resolucion) <= 500 and nota_resolucion !~ '[0-9]{7,}')),
  constraint casos_en_curso_chk check (estado <> 'en_curso' or dueno is not null),
  constraint casos_resuelto_chk check ((estado = 'resuelto') = (resuelto_at is not null) and (resuelto_at is null) = (resuelto_por is null)),
  constraint casos_tiempos_chk  check (ultimo_aviso_at >= primer_aviso_at)
);

-- dedupe: UN caso abierto por (telefono, tipo)
create unique index if not exists casos_abierto_uk on public.casos (telefono, tipo) where estado <> 'resuelto';
-- la bandeja: abiertos por estado y lo resuelto hoy
create index if not exists casos_bandeja_idx   on public.casos (estado, ultimo_aviso_at desc);
create index if not exists casos_resuelto_idx  on public.casos (resuelto_at desc) where estado = 'resuelto';
create index if not exists casos_telefono_idx  on public.casos (telefono, created_at desc);

comment on table public.casos is
  'Bandeja de Atencion (ATE-02). Un caso = un motivo abierto para un contacto. Se crea solo por registrar_aviso() (triggers sobre '
  'escalaciones_log y triaje_urgencias_log) y cambia solo por caso_tomar/soltar/esperando/resolver/reabrir. El tipo sale de lo que '
  'registro el bot, nunca del texto del paciente.';

-- ---------------------------------------------------------------------------------------------------------------------
-- 2. Bitacora
-- ---------------------------------------------------------------------------------------------------------------------
create table if not exists public.casos_eventos (
  id              bigint generated always as identity primary key,
  caso_id         bigint      not null references public.casos (id) on delete cascade,
  evento          text        not null,
  actor           text        not null,                     -- 'bot', 'sistema' o el usuario del panel
  estado_antes    text,
  estado_despues  text,
  detalle         jsonb       not null default '{}'::jsonb,
  exec_id         text,
  ref_tabla       text,
  ref_id          bigint,
  created_at      timestamptz not null default now(),
  constraint casos_eventos_evento_chk check (evento in ('creado', 'aviso', 'tomado', 'soltado', 'esperando', 'resuelto', 'reabierto')),
  constraint casos_eventos_actor_chk  check (actor ~ '^[a-z0-9][a-z0-9._@+-]{0,63}$')
);
-- idempotencia: cada fila de log entra una sola vez (trigger + backfill + reintentos)
create unique index if not exists casos_eventos_ref_uk on public.casos_eventos (ref_tabla, ref_id)
  where ref_tabla is not null and ref_id is not null;
create index if not exists casos_eventos_caso_idx on public.casos_eventos (caso_id, id);

-- ---------------------------------------------------------------------------------------------------------------------
-- 3. Etiquetas fijas del codigo del bot -> tipo. Gana la etiqueta MAS LARGA que coincide con el principio del motivo.
--    'ignorar' = no es un caso de la bandeja (avisos tecnicos para Lucas, housekeeping del modo humano).
--    Si el bot cambia una plantilla, el aviso cae en 'consulta' (se ve igual en Requiere secretaria): agregar la fila nueva.
-- ---------------------------------------------------------------------------------------------------------------------
create table if not exists public.casos_prefijos (
  prefijo  text primary key,
  tipo     text not null,
  fuente   text not null,      -- de que archivo del bot sale la plantilla
  constraint casos_prefijos_tipo_chk check (tipo in ('urgencia', 'pago', 'pidio_persona', 'turno', 'consulta', 'aviso', 'ignorar')),
  constraint casos_prefijos_chk check (char_length(prefijo) between 3 and 80)
);
insert into public.casos_prefijos (prefijo, tipo, fuente) values
  ('[TRIAJE]',                                                  'urgencia',      'triaje/preparar_escalada.js'),
  ('[TRIAJE VIDEO]',                                            'aviso',         'triaje/decidir.js (aviso pasivo, ya atendido con video)'),
  ('Contacto silenciado (',                                     'urgencia',      'segmentacion/dia1/avisar_al_grupo.js (red de seguridad)'),
  ('[ACCIÓN] Asiri lo tomó como aviso de pago',                 'pago',          'v7/clinica_core.js registrar_pago'),
  ('El paciente pidió hablar con una persona',                  'pidio_persona', 'v7/clinica_core.js pedir_persona'),
  ('[ACCIÓN] El paciente pidió hablar con una persona',         'pidio_persona', 'v7/orquestador_core.js (aviso que no salio)'),
  ('[ACCIÓN]',                                                  'consulta',      'v7 avisar_grupo ACCION'),
  ('[FYI]',                                                     'aviso',         'v7 avisar_grupo FYI'),
  ('[CancelarReprogramar]',                                     'turno',         'v6 Sub-WF CancelarReprogramar'),
  ('[FALLO TECNICO]',                                           'ignorar',       'Health Check (aviso tecnico)'),
  ('Aviso técnico de Asiri',                                    'ignorar',       'segmentacion/dia1/aviso_tecnico.js'),
  ('El bot detectó que ya estás atendiendo',                    'ignorar',       'v6 (modo humano: el bot se callo bien)')
on conflict (prefijo) do nothing;

-- ---------------------------------------------------------------------------------------------------------------------
-- 4. Tipo de una fila de escalaciones_log (solo lo que registro el bot)
-- ---------------------------------------------------------------------------------------------------------------------
create or replace function public.casos_tipo_de_escalacion(p_origen text, p_motivo text, p_fila jsonb default '{}'::jsonb)
returns text
language plpgsql stable security definer set search_path = '' as $$
declare
  v text := coalesce(p_fila, '{}'::jsonb) ->> 'tipo_aviso';   -- columna estructurada futura (hoy no existe)
begin
  if v in ('urgencia', 'pago', 'pidio_persona', 'turno', 'consulta', 'aviso') then
    return v;
  elsif v = 'ignorar' then
    return null;
  end if;
  if p_origen = 'triaje_video' then
    return 'aviso';
  end if;
  select x.tipo into v
    from public.casos_prefijos x
   where starts_with(btrim(coalesce(p_motivo, '')), x.prefijo)
   order by char_length(x.prefijo) desc
   limit 1;
  if found then
    return nullif(v, 'ignorar');
  end if;
  return 'consulta';
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 5. registrar_aviso: crea el caso o suma al abierto del mismo (telefono, tipo).
--    - Idempotente por (p_ref_tabla, p_ref_id): la misma fila de log nunca cuenta dos veces.
--    - Un aviso de hace mas de 72 h nace RESUELTO (archivado por 'sistema') y no se mezcla con uno abierto.
--    - Fusion: si el caso abierto recibio un aviso de OTRA tabla hace menos de p_fusionar_seg (misma escalacion vista por
--      escalaciones_log y por triaje_urgencias_log), se anota en la bitacora y se enriquece, pero NO suma al contador.
--    - Un caso 'esperando_paciente' que recibe un aviso vuelve a 'en_curso' (si tiene duenio) o a 'nuevo'.
--    - lock_timeout 1 s: nunca hace esperar al bot (si no consigue el lock, error -> el trigger lo traga).
-- ---------------------------------------------------------------------------------------------------------------------
create or replace function public.registrar_aviso(
  p_telefono text, p_tipo text, p_motivo text, p_origen text,
  p_ref_tabla text default null, p_ref_id bigint default null, p_exec_id text default null,
  p_cuando timestamptz default null, p_detalle jsonb default '{}'::jsonb, p_fusionar_seg integer default 300)
returns jsonb
language plpgsql security definer set search_path = '' set lock_timeout = '1s' as $$
declare
  v_tel     text := public.contacto_tel_normalizar(p_telefono);
  v_cuando  timestamptz := least(coalesce(p_cuando, now()), now());
  v_motivo  text := coalesce(left(nullif(btrim(coalesce(p_motivo, '')), ''), 500), 'Sin motivo registrado');
  v_origen  text := left(coalesce(nullif(btrim(coalesce(p_origen, '')), ''), 'bot'), 40);
  v_det     jsonb := coalesce(p_detalle, '{}'::jsonb);
  v_caso    public.casos;
  v_antes   text;
  v_fusion  boolean;
begin
  if v_tel is null or v_tel ~ '@(g\.us|broadcast)$' then
    return jsonb_build_object('ok', false, 'error', 'SIN_TELEFONO');
  end if;
  if p_tipo is null or p_tipo not in ('urgencia', 'pago', 'pidio_persona', 'turno', 'consulta', 'aviso') then
    return jsonb_build_object('ok', false, 'error', 'TIPO_INVALIDO');
  end if;
  if p_ref_tabla is not null and p_ref_id is not null
     and exists (select 1 from public.casos_eventos e where e.ref_tabla = p_ref_tabla and e.ref_id = p_ref_id) then
    return jsonb_build_object('ok', true, 'repetido', true);
  end if;

  -- viejo: nace archivado (solo las ultimas 72 h nacen como nuevas)
  if v_cuando < now() - interval '72 hours' then
    insert into public.casos (telefono, tipo, estado, motivo, origen, detalle, primer_aviso_at, ultimo_aviso_at,
                              resuelto_at, resuelto_por, nota_resolucion, ref_tabla, ref_id)
    values (v_tel, p_tipo, 'resuelto', v_motivo, v_origen, v_det, v_cuando, v_cuando,
            now(), 'sistema', 'Aviso de hace mas de 72 h: se archivo al crear la bandeja', p_ref_tabla, p_ref_id)
    returning * into v_caso;
    insert into public.casos_eventos (caso_id, evento, actor, estado_antes, estado_despues, detalle, exec_id, ref_tabla, ref_id, created_at)
    values (v_caso.id, 'creado', 'bot', null, 'resuelto', v_det || jsonb_build_object('origen', v_origen, 'archivado', true),
            p_exec_id, p_ref_tabla, p_ref_id, now());
    return jsonb_build_object('ok', true, 'caso_id', v_caso.id, 'nuevo', true, 'archivado', true);
  end if;

  perform pg_advisory_xact_lock(hashtextextended('casos|' || v_tel || '|' || p_tipo, 0));
  select * into v_caso from public.casos c where c.telefono = v_tel and c.tipo = p_tipo and c.estado <> 'resuelto' for update;

  if not found then
    insert into public.casos (telefono, tipo, motivo, origen, detalle, primer_aviso_at, ultimo_aviso_at, ref_tabla, ref_id)
    values (v_tel, p_tipo, v_motivo, v_origen, v_det, v_cuando, v_cuando, p_ref_tabla, p_ref_id)
    returning * into v_caso;
    insert into public.casos_eventos (caso_id, evento, actor, estado_antes, estado_despues, detalle, exec_id, ref_tabla, ref_id)
    values (v_caso.id, 'creado', 'bot', null, 'nuevo', v_det || jsonb_build_object('origen', v_origen), p_exec_id, p_ref_tabla, p_ref_id);
    return jsonb_build_object('ok', true, 'caso_id', v_caso.id, 'nuevo', true);
  end if;

  v_antes  := v_caso.estado;
  v_fusion := p_ref_tabla is not null and v_caso.ref_tabla is not null and v_caso.ref_tabla <> p_ref_tabla
              and v_caso.ultimo_aviso_at >= v_cuando - make_interval(secs => greatest(coalesce(p_fusionar_seg, 0), 0));
  update public.casos c set
    contador        = c.contador + case when v_fusion then 0 else 1 end,
    motivo          = case when v_fusion then c.motivo else v_motivo end,
    origen          = case when v_fusion then c.origen else v_origen end,
    detalle         = c.detalle || v_det,
    ultimo_aviso_at = greatest(c.ultimo_aviso_at, v_cuando),
    estado          = case when c.estado = 'esperando_paciente' then case when c.dueno is null then 'nuevo' else 'en_curso' end else c.estado end,
    esperando_desde = case when c.estado = 'esperando_paciente' then null else c.esperando_desde end,
    ref_tabla       = case when v_fusion then c.ref_tabla else coalesce(p_ref_tabla, c.ref_tabla) end,
    ref_id          = case when v_fusion then c.ref_id    else coalesce(p_ref_id, c.ref_id) end,
    updated_at      = now()
  where c.id = v_caso.id
  returning * into v_caso;
  insert into public.casos_eventos (caso_id, evento, actor, estado_antes, estado_despues, detalle, exec_id, ref_tabla, ref_id)
  values (v_caso.id, 'aviso', 'bot', v_antes, v_caso.estado, v_det || jsonb_build_object('origen', v_origen, 'fusionado', v_fusion),
          p_exec_id, p_ref_tabla, p_ref_id);
  return jsonb_build_object('ok', true, 'caso_id', v_caso.id, 'nuevo', false, 'fusionado', v_fusion, 'contador', v_caso.contador);
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 6. Triggers FAIL-SAFE. AFTER INSERT (no pueden tocar la fila del bot). Todo adentro de un bloque con EXCEPTION: si falta una
--    tabla, una funcion, un lock o hay un bug, queda un WARNING en el log de Postgres y el INSERT del bot sigue.
-- ---------------------------------------------------------------------------------------------------------------------
create or replace function public.casos_tg_desde_escalacion() returns trigger
language plpgsql security definer set search_path = '' set lock_timeout = '1s' as $$
declare
  v_tipo text;
begin
  begin
    v_tipo := public.casos_tipo_de_escalacion(new.origen, new.motivo, to_jsonb(new));
    if v_tipo is not null then
      perform public.registrar_aviso(new.telefono, v_tipo, new.motivo, coalesce(new.origen, 'bot'),
                                     'escalaciones_log', new.id, new.exec_id, new.created_at, '{}'::jsonb, 300);
    end if;
  exception when others then
    raise warning 'casos: escalaciones_log id=% no creo caso (% %)', new.id, sqlstate, sqlerrm;
  end;
  return null;
end $$;

create or replace function public.casos_tg_desde_triaje() returns trigger
language plpgsql security definer set search_path = '' set lock_timeout = '1s' as $$
begin
  begin
    -- escalado de verdad (no sombra) = urgencia. video / pregunta / cierre / silencio_humano: lo resolvio el bot o ya atiende una persona.
    if new.accion = 'escalado' and coalesce(new.modo, '') <> 'sombra' then
      perform public.registrar_aviso(
        new.telefono, 'urgencia',
        'Urgencia' || coalesce(' (' || replace(nullif(new.tipo, ''), '_', ' ') || ')', '')
          || coalesce(': «' || left(nullif(btrim(new.mensaje_paciente), ''), 160) || '»', ''),
        'triaje', 'triaje_urgencias_log', new.id, new.exec_id, new.created_at,
        jsonb_strip_nulls(jsonb_build_object('triaje_tipo', new.tipo, 'triaje_confianza', new.confianza, 'gate_escala', new.gate_escala)),
        300);
    end if;
  exception when others then
    raise warning 'casos: triaje_urgencias_log id=% no creo caso (% %)', new.id, sqlstate, sqlerrm;
  end;
  return null;
end $$;

create or replace trigger casos_desde_escalacion_trg after insert on public.escalaciones_log
  for each row execute function public.casos_tg_desde_escalacion();
create or replace trigger casos_desde_triaje_trg after insert on public.triaje_urgencias_log
  for each row execute function public.casos_tg_desde_triaje();

-- ---------------------------------------------------------------------------------------------------------------------
-- 7. Acciones del panel (service_role). Devuelven jsonb {ok, error?, caso}. Actor = usuario del panel (minusculas).
-- ---------------------------------------------------------------------------------------------------------------------
create or replace function public.casos_actor_ok(p_actor text) returns text
language sql immutable set search_path = '' as $$
  select case when lower(btrim(coalesce(p_actor, ''))) ~ '^[a-z0-9][a-z0-9._@+-]{0,63}$' then lower(btrim(p_actor)) end
$$;

create or replace function public.caso_tomar(p_caso_id bigint, p_actor text) returns jsonb
language plpgsql security definer set search_path = '' set lock_timeout = '3s' as $$
declare
  v_actor text := public.casos_actor_ok(p_actor);
  v public.casos;
  v_antes text;
begin
  if v_actor is null then return jsonb_build_object('ok', false, 'error', 'ACTOR_INVALIDO'); end if;
  select * into v from public.casos where id = p_caso_id for update;
  if not found then return jsonb_build_object('ok', false, 'error', 'NO_EXISTE'); end if;
  if v.estado = 'resuelto' then return jsonb_build_object('ok', false, 'error', 'YA_RESUELTO', 'caso', to_jsonb(v)); end if;
  if v.estado = 'en_curso' then
    if v.dueno = v_actor then return jsonb_build_object('ok', true, 'ya_estaba', true, 'caso', to_jsonb(v)); end if;
    return jsonb_build_object('ok', false, 'error', 'YA_TOMADO', 'dueno', v.dueno, 'caso', to_jsonb(v));
  end if;
  v_antes := v.estado;
  update public.casos set estado = 'en_curso', dueno = v_actor, tomado_at = now(), esperando_desde = null, updated_at = now()
   where id = p_caso_id returning * into v;
  insert into public.casos_eventos (caso_id, evento, actor, estado_antes, estado_despues) values (v.id, 'tomado', v_actor, v_antes, v.estado);
  return jsonb_build_object('ok', true, 'caso', to_jsonb(v));
end $$;

-- Deshacer de "Tomar": vuelve a sin duenio.
create or replace function public.caso_soltar(p_caso_id bigint, p_actor text) returns jsonb
language plpgsql security definer set search_path = '' set lock_timeout = '3s' as $$
declare
  v_actor text := public.casos_actor_ok(p_actor);
  v public.casos;
  v_antes text;
begin
  if v_actor is null then return jsonb_build_object('ok', false, 'error', 'ACTOR_INVALIDO'); end if;
  select * into v from public.casos where id = p_caso_id for update;
  if not found then return jsonb_build_object('ok', false, 'error', 'NO_EXISTE'); end if;
  if v.estado = 'resuelto' then return jsonb_build_object('ok', false, 'error', 'YA_RESUELTO', 'caso', to_jsonb(v)); end if;
  if v.dueno is null and v.estado = 'nuevo' then return jsonb_build_object('ok', true, 'ya_estaba', true, 'caso', to_jsonb(v)); end if;
  v_antes := v.estado;
  update public.casos set estado = 'nuevo', dueno = null, tomado_at = null, esperando_desde = null, updated_at = now()
   where id = p_caso_id returning * into v;
  insert into public.casos_eventos (caso_id, evento, actor, estado_antes, estado_despues) values (v.id, 'soltado', v_actor, v_antes, v.estado);
  return jsonb_build_object('ok', true, 'caso', to_jsonb(v));
end $$;

create or replace function public.caso_esperando(p_caso_id bigint, p_actor text) returns jsonb
language plpgsql security definer set search_path = '' set lock_timeout = '3s' as $$
declare
  v_actor text := public.casos_actor_ok(p_actor);
  v public.casos;
  v_antes text;
begin
  if v_actor is null then return jsonb_build_object('ok', false, 'error', 'ACTOR_INVALIDO'); end if;
  select * into v from public.casos where id = p_caso_id for update;
  if not found then return jsonb_build_object('ok', false, 'error', 'NO_EXISTE'); end if;
  if v.estado = 'resuelto' then return jsonb_build_object('ok', false, 'error', 'YA_RESUELTO', 'caso', to_jsonb(v)); end if;
  if v.estado = 'esperando_paciente' then return jsonb_build_object('ok', true, 'ya_estaba', true, 'caso', to_jsonb(v)); end if;
  v_antes := v.estado;
  update public.casos set estado = 'esperando_paciente', dueno = coalesce(dueno, v_actor), tomado_at = coalesce(tomado_at, now()),
                          esperando_desde = now(), updated_at = now()
   where id = p_caso_id returning * into v;
  insert into public.casos_eventos (caso_id, evento, actor, estado_antes, estado_despues) values (v.id, 'esperando', v_actor, v_antes, v.estado);
  return jsonb_build_object('ok', true, 'caso', to_jsonb(v));
end $$;

create or replace function public.caso_resolver(p_caso_id bigint, p_actor text, p_nota text default null, p_devolver_bot boolean default true)
returns jsonb
language plpgsql security definer set search_path = '' set lock_timeout = '3s' as $$
declare
  v_actor text := public.casos_actor_ok(p_actor);
  v_nota  text := nullif(btrim(coalesce(p_nota, '')), '');
  v public.casos;
  v_antes text;
begin
  if v_actor is null then return jsonb_build_object('ok', false, 'error', 'ACTOR_INVALIDO'); end if;
  if v_nota is not null and (char_length(v_nota) > 500 or v_nota ~ '[0-9]{7,}') then
    return jsonb_build_object('ok', false, 'error', 'NOTA_INVALIDA');    -- sin telefonos ni DNI en la nota
  end if;
  select * into v from public.casos where id = p_caso_id for update;
  if not found then return jsonb_build_object('ok', false, 'error', 'NO_EXISTE'); end if;
  if v.estado = 'resuelto' then return jsonb_build_object('ok', true, 'ya_estaba', true, 'caso', to_jsonb(v)); end if;
  v_antes := v.estado;
  update public.casos set estado = 'resuelto', resuelto_at = now(), resuelto_por = v_actor, nota_resolucion = v_nota,
                          devolver_bot = coalesce(p_devolver_bot, true), dueno = coalesce(dueno, v_actor), updated_at = now()
   where id = p_caso_id returning * into v;
  insert into public.casos_eventos (caso_id, evento, actor, estado_antes, estado_despues, detalle)
  values (v.id, 'resuelto', v_actor, v_antes, v.estado,
          jsonb_build_object('devolver_bot', coalesce(p_devolver_bot, true), 'con_nota', v_nota is not null));
  return jsonb_build_object('ok', true, 'caso', to_jsonb(v));
end $$;

-- Deshacer de "Resolver": vuelve al estado anterior (el de la bitacora). No si ya hay otro abierto del mismo motivo.
create or replace function public.caso_reabrir(p_caso_id bigint, p_actor text) returns jsonb
language plpgsql security definer set search_path = '' set lock_timeout = '3s' as $$
declare
  v_actor text := public.casos_actor_ok(p_actor);
  v public.casos;
  v_volver text;
begin
  if v_actor is null then return jsonb_build_object('ok', false, 'error', 'ACTOR_INVALIDO'); end if;
  select * into v from public.casos where id = p_caso_id for update;
  if not found then return jsonb_build_object('ok', false, 'error', 'NO_EXISTE'); end if;
  if v.estado <> 'resuelto' then return jsonb_build_object('ok', true, 'ya_estaba', true, 'caso', to_jsonb(v)); end if;
  perform pg_advisory_xact_lock(hashtextextended('casos|' || v.telefono || '|' || v.tipo, 0));
  if exists (select 1 from public.casos c where c.telefono = v.telefono and c.tipo = v.tipo and c.estado <> 'resuelto') then
    return jsonb_build_object('ok', false, 'error', 'HAY_OTRO_ABIERTO', 'caso', to_jsonb(v));
  end if;
  select e.estado_antes into v_volver from public.casos_eventos e
   where e.caso_id = v.id and e.evento = 'resuelto' order by e.id desc limit 1;
  v_volver := coalesce(v_volver, 'nuevo');
  if v_volver in ('en_curso', 'esperando_paciente') and v.dueno is null then v_volver := 'nuevo'; end if;
  update public.casos set estado = v_volver, resuelto_at = null, resuelto_por = null, nota_resolucion = null, devolver_bot = null,
                          esperando_desde = case when v_volver = 'esperando_paciente' then coalesce(esperando_desde, now()) else null end,
                          updated_at = now()
   where id = p_caso_id returning * into v;
  insert into public.casos_eventos (caso_id, evento, actor, estado_antes, estado_despues) values (v.id, 'reabierto', v_actor, 'resuelto', v.estado);
  return jsonb_build_object('ok', true, 'caso', to_jsonb(v));
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 8. Backfill: los casos de las ultimas p_horas (72 por defecto) desde los dos logs, en orden de llegada. Idempotente.
-- ---------------------------------------------------------------------------------------------------------------------
create or replace function public.casos_backfill(p_horas integer default 72) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  r record;
  v_tipo text;
  n_esc integer := 0;
  n_tri integer := 0;
begin
  for r in
    select 'e' as fuente, e.id, e.created_at from public.escalaciones_log e
     where e.created_at >= now() - make_interval(hours => greatest(coalesce(p_horas, 72), 0))
    union all
    select 't', t.id, t.created_at from public.triaje_urgencias_log t
     where t.created_at >= now() - make_interval(hours => greatest(coalesce(p_horas, 72), 0)) and t.accion = 'escalado' and coalesce(t.modo, '') <> 'sombra'
    order by 3, 1, 2
  loop
    if r.fuente = 'e' then
      select public.casos_tipo_de_escalacion(e.origen, e.motivo, to_jsonb(e)) into v_tipo from public.escalaciones_log e where e.id = r.id;
      if v_tipo is not null then
        perform public.registrar_aviso(e.telefono, v_tipo, e.motivo, coalesce(e.origen, 'bot'), 'escalaciones_log', e.id, e.exec_id, e.created_at, '{}'::jsonb, 300)
           from public.escalaciones_log e where e.id = r.id;
        n_esc := n_esc + 1;
      end if;
    else
      perform public.registrar_aviso(
        t.telefono, 'urgencia',
        'Urgencia' || coalesce(' (' || replace(nullif(t.tipo, ''), '_', ' ') || ')', '')
          || coalesce(': «' || left(nullif(btrim(t.mensaje_paciente), ''), 160) || '»', ''),
        'triaje', 'triaje_urgencias_log', t.id, t.exec_id, t.created_at,
        jsonb_strip_nulls(jsonb_build_object('triaje_tipo', t.tipo, 'triaje_confianza', t.confianza, 'gate_escala', t.gate_escala)), 300)
        from public.triaje_urgencias_log t where t.id = r.id;
      n_tri := n_tri + 1;
    end if;
  end loop;
  return jsonb_build_object('ok', true, 'escalaciones', n_esc, 'triaje', n_tri);
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 9. Permisos (Anexo B). RLS sin policies. service_role (el panel, server-side): LEE casos y bitacora y ejecuta SOLO las
--    acciones caso_*. Nadie escribe las tablas directo; anon / authenticated: nada.
-- ---------------------------------------------------------------------------------------------------------------------
alter table public.casos          enable row level security;
alter table public.casos_eventos  enable row level security;
alter table public.casos_prefijos enable row level security;
revoke all on table public.casos, public.casos_eventos, public.casos_prefijos from public, anon, authenticated, service_role;
grant select on table public.casos, public.casos_eventos to service_role;
do $$
declare s text;
begin
  foreach s in array array[pg_get_serial_sequence('public.casos', 'id'), pg_get_serial_sequence('public.casos_eventos', 'id')] loop
    execute format('revoke all on sequence %s from public, anon, authenticated, service_role', s);
  end loop;
end $$;
revoke all on function public.casos_tipo_de_escalacion(text, text, jsonb) from public, anon, authenticated, service_role;
revoke all on function public.registrar_aviso(text, text, text, text, text, bigint, text, timestamptz, jsonb, integer) from public, anon, authenticated, service_role;
revoke all on function public.casos_tg_desde_escalacion() from public, anon, authenticated, service_role;
revoke all on function public.casos_tg_desde_triaje()     from public, anon, authenticated, service_role;
revoke all on function public.casos_actor_ok(text)        from public, anon, authenticated, service_role;
revoke all on function public.casos_backfill(integer)     from public, anon, authenticated, service_role;
revoke all on function public.caso_tomar(bigint, text)     from public, anon, authenticated;
revoke all on function public.caso_soltar(bigint, text)    from public, anon, authenticated;
revoke all on function public.caso_esperando(bigint, text) from public, anon, authenticated;
revoke all on function public.caso_resolver(bigint, text, text, boolean) from public, anon, authenticated;
revoke all on function public.caso_reabrir(bigint, text)   from public, anon, authenticated;
grant execute on function public.caso_tomar(bigint, text), public.caso_soltar(bigint, text), public.caso_esperando(bigint, text),
                          public.caso_resolver(bigint, text, text, boolean), public.caso_reabrir(bigint, text) to service_role;

-- ---------------------------------------------------------------------------------------------------------------------
-- 10. Bus en vivo: casos entra a la publicacion de Realtime (el panel la escucha server-side con la service key).
--     OJO panel: suscribir postgres_changes a una tabla que no existe rompe el canal (lib/live/bus.ts): agregar la
--     suscripcion a 'casos' recien despues de aplicar esta migracion.
-- ---------------------------------------------------------------------------------------------------------------------
--     Si no se puede (otra duenia de la publicacion), la migracion sigue: el panel igual refresca por polling.
do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime')
     and not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'casos') then
    begin
      execute 'alter publication supabase_realtime add table public.casos';
    exception when insufficient_privilege then
      raise warning 'casos: no se pudo agregar a supabase_realtime (%); hacerlo desde Database > Replication', sqlerrm;
    end;
  end if;
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 11. Autochequeo: forma, triggers y permisos esperados; si no, abortar todo.
-- ---------------------------------------------------------------------------------------------------------------------
do $$
declare v_cols text;
begin
  select string_agg(column_name, ',' order by ordinal_position) into v_cols
    from information_schema.columns where table_schema = 'public' and table_name = 'casos';
  if v_cols is distinct from 'id,telefono,tipo,estado,motivo,origen,contador,detalle,dueno,primer_aviso_at,ultimo_aviso_at,tomado_at,'
                             'esperando_desde,resuelto_at,resuelto_por,nota_resolucion,devolver_bot,ref_tabla,ref_id,created_at,updated_at' then
    raise exception 'casos existe con otra forma: %', v_cols;
  end if;
  if not exists (select 1 from pg_indexes where schemaname = 'public' and indexname = 'casos_abierto_uk') then
    raise exception 'falta el indice casos_abierto_uk';
  end if;
  if not exists (select 1 from pg_trigger where tgrelid = 'public.escalaciones_log'::regclass and tgname = 'casos_desde_escalacion_trg')
     or not exists (select 1 from pg_trigger where tgrelid = 'public.triaje_urgencias_log'::regclass and tgname = 'casos_desde_triaje_trg') then
    raise exception 'faltan los triggers de casos';
  end if;
  if exists (
       select 1
         from unnest(array['anon', 'authenticated']) rol,
              unnest(array['public.casos', 'public.casos_eventos', 'public.casos_prefijos']) tab,
              unnest(array['select', 'insert', 'update', 'delete', 'truncate', 'references', 'trigger']) priv
        where has_table_privilege(rol, tab, priv))
     or exists (
       select 1 from unnest(array['public.casos', 'public.casos_eventos', 'public.casos_prefijos']) tab,
                     unnest(array['insert', 'update', 'delete', 'truncate']) priv
        where has_table_privilege('service_role', tab, priv))
     or has_table_privilege('service_role', 'public.casos_prefijos', 'select')
     or not has_table_privilege('service_role', 'public.casos', 'select')
     or has_function_privilege('service_role', 'public.registrar_aviso(text,text,text,text,text,bigint,text,timestamptz,jsonb,integer)', 'execute')
     or has_function_privilege('anon', 'public.caso_tomar(bigint,text)', 'execute')
     or not has_function_privilege('service_role', 'public.caso_resolver(bigint,text,text,boolean)', 'execute') then
    raise exception 'permisos de casos distintos de los esperados (Anexo B)';
  end if;
end $$;

-- ---------------------------------------------------------------------------------------------------------------------
-- 12. Carga inicial: los avisos de las ultimas 72 h nacen como casos nuevos (lo anterior no entra).
-- ---------------------------------------------------------------------------------------------------------------------
select public.casos_backfill(72);

notify pgrst, 'reload schema';
commit;
