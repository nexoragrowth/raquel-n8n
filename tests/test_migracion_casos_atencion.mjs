// test_migracion_casos_atencion.mjs — 2026-10-20 · prueba LOCAL (PGlite = Postgres 16 en WASM, en memoria) de ATE-02
// (sql/2026-10-20_casos_atencion.sql y su _DOWN) contra una réplica del esquema y los roles del Supabase v3. No toca ninguna base real.
// Teléfonos 100% sintéticos (forma 5490000000xxx). Mismo patrón que tests/test_migracion_contacto_tipos.mjs (y aplica primero esa
// migración, que es la que trae contacto_tel_normalizar).
// Lo central: (1) el tipo del caso sale de lo que registró el bot (origen, acción del triaje, etiqueta fija del código al principio
// del motivo), nunca del texto del paciente; (2) con el disparador ROTO el insert del bot en escalaciones_log / triaje_urgencias_log
// entra igual; (3) dedupe por teléfono + tipo con contador; (4) solo las últimas 72 h nacen como nuevas; (5) permisos.
// Requiere @electric-sql/pglite (devDependency del repo: `npm install`) o PGLITE_PATH.   Uso: node tests/test_migracion_casos_atencion.mjs
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const { PGlite } = await import(process.env.PGLITE_PATH ? pathToFileURL(path.join(process.env.PGLITE_PATH, 'dist', 'index.js')).href : '@electric-sql/pglite');
const RAIZ = new URL('../', import.meta.url);
const TIPOS_UP = readFileSync(new URL('sql/2026-10-14_contacto_tipos.sql', RAIZ), 'utf8').replaceAll('for role postgres', 'for role sbowner');
const UP = readFileSync(new URL('sql/2026-10-20_casos_atencion.sql', RAIZ), 'utf8');
const DOWN = readFileSync(new URL('sql/2026-10-20_casos_atencion_DOWN.sql', RAIZ), 'utf8');

const db = new PGlite();
let fallas = 0, ok = 0;
const check = (cond, msg) => { if (cond) { ok++; } else { fallas++; console.log('FALLA:', msg); } };
const q1 = async (sql, p) => (await db.query(sql, p)).rows[0];
const qn = async (sql, p) => (await db.query(sql, p)).rows;
const err = async (sql, p) => { try { await db.query(sql, p); return null; } catch (e) { return e.code || e.message; } };
const avisos = [];
db.onNotice?.((n) => avisos.push(String(n.message || n)));

// ---------------------------------------------------------------- réplica de Supabase (roles, defaults abiertos, RLS automático)
await db.exec(`
  create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
  create role authenticator noinherit login; grant anon, authenticated, service_role to authenticator;
  create role sbowner login createrole bypassrls;          -- hace de "postgres" de Supabase: NO superuser
  grant anon, authenticated, service_role to sbowner;
  grant all on schema public to sbowner;
  grant usage on schema public to anon, authenticated, service_role;
  create function public.rls_auto_enable() returns event_trigger language plpgsql security definer set search_path = pg_catalog as $$
  declare cmd record;
  begin
    for cmd in select * from pg_event_trigger_ddl_commands() where command_tag in ('CREATE TABLE','CREATE TABLE AS','SELECT INTO') and object_type in ('table','partitioned table') loop
      if cmd.schema_name = 'public' then execute format('alter table if exists %s enable row level security', cmd.object_identity); end if;
    end loop;
  end $$;
  create event trigger ensure_rls on ddl_command_end when tag in ('CREATE TABLE','CREATE TABLE AS','SELECT INTO') execute function public.rls_auto_enable();
`);
// Publicación de Realtime (si PGlite la soporta): la migración tiene que agregar 'casos'.
const hayPublicacion = (await err(`create publication supabase_realtime`)) === null
  && (await err(`alter publication supabase_realtime owner to sbowner`)) === null;   // en Supabase la maneja postgres

// Tablas del bot con las columnas EXACTAS de producción (information_schema del v3, 20/10/2026).
await db.exec(`set role sbowner;
  alter default privileges for role sbowner in schema public grant all on tables to anon, authenticated, service_role;
  alter default privileges for role sbowner in schema public grant all on sequences to anon, authenticated, service_role;
  alter default privileges for role sbowner in schema public grant all on functions to anon, authenticated, service_role;
  create table public.pacientes (id bigserial primary key, telefono text not null unique, nombre text default 'Paciente WhatsApp',
    human_takeover boolean default false, resumen_clinico text, resumen_actualizado_at timestamptz, created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(), panel_last_read_at timestamptz, alias_panel text, alias_panel_updated_at timestamptz,
    human_takeover_at timestamptz default now());
  create table public.recordatorios_enviados (id bigserial primary key, telefono text not null, chat_remote_jid text, id_cita_dentalink bigint,
    id_paciente_dentalink bigint, nombre_paciente text, fecha_turno date, hora_turno text, tipo text, workflow_execution_id text,
    enviado_at timestamptz not null default now(), confirmado_at timestamptz, cancelado_at timestamptz);
  create table public.n8n_chat_histories (id bigserial primary key, session_id varchar(255) not null, message jsonb not null, created_at timestamptz default now());
  create table public.escalaciones_log (id bigserial primary key, telefono text, motivo text, origen text default 'bot', exec_id text,
    created_at timestamptz not null default now());
  create index idx_escalaciones_created on public.escalaciones_log (created_at);
  create table public.triaje_urgencias_log (id bigserial primary key, escalacion_id bigint unique references public.escalaciones_log(id) on delete set null,
    telefono text, exec_id text, escalacion_created_at timestamptz, motivo_bot text, mensaje_paciente text,
    gate_red_flags jsonb not null default '[]'::jsonb, gate_escala boolean not null default false, tipo text, confianza text, razon text, modelo text,
    modo text not null default 'sombra', accion text not null default 'escalado', video_enviado text, created_at timestamptz not null default now(),
    opcion_enviada smallint, chat_history_id bigint, resuelto_at timestamptz, razon_cierre text);
  reset role;`);
await db.exec('set role sbowner');
await db.exec(TIPOS_UP);   // prerrequisito: contacto_tel_normalizar
await db.exec('reset role');

const T = { a: '5490000000011', b: '5490000000012', c: '5490000000013', d: '5490000000014', e: '5490000000015', f: '5490000000016',
            g: '5490000000017', h: '5490000000018', i: '5490000000019', j: '5490000000020', k: '5490000000021', viejo: '5490000000098', previo: '5490000000099' };
// Inserts como los hace el bot (n8n entra como el dueño): nodo Postgres "Log Escalacion" del Helper - Notify Grupo.
const esc = async (tel, motivo, { origen = 'bot', ...extra } = {}) => {
  const fila = { telefono: tel, motivo, origen, exec_id: String(Math.floor(Math.random() * 1e9)), ...extra };
  const keys = Object.keys(fila);
  return (await q1(`insert into public.escalaciones_log (${keys.join(', ')}) values (${keys.map((_, i) => '$' + (i + 1)).join(', ')}) returning id`,
                   Object.values(fila))).id;
};
// Insert de triaje/escalar_notify.js (fila 'escalado')
const tri = async (tel, { accion = 'escalado', modo = 'piloto', tipo = 'bracket_suelto', texto = 'se me salió un bracket' } = {}) =>
  (await q1(`insert into public.triaje_urgencias_log (telefono, exec_id, mensaje_paciente, gate_red_flags, gate_escala, tipo, confianza, razon, modelo, modo, accion)
             values ($1, $2, $3, '[]'::jsonb, false, $4, 'alta', 'razon', 'modelo', $5, $6) returning id`,
            [tel, String(Math.floor(Math.random() * 1e9)), texto, tipo, modo, accion])).id;
const casosDe = async (tel) => qn(`select * from public.casos where telefono = $1 order by id`, [tel]);
const abierto = async (tel, tipo) => q1(`select * from public.casos where telefono = $1 and tipo = $2 and estado <> 'resuelto'`, [tel, tipo]);
const accion = async (fn, ...a) => (await q1(`select public.${fn}(${a.map((_, i) => '$' + (i + 1)).join(', ')}) as r`, a)).r;

// ---------------------------------------------------------------- 0. filas ANTERIORES a la migración (para la carga inicial de 72 h)
await db.exec('set role sbowner');
await db.query(`insert into public.escalaciones_log (telefono, motivo, origen, exec_id, created_at) values
  ($1, '[ACCIÓN] Fuera de lo que atiende Asiri: pregunta por una orden. Contestarle por este chat.', 'bot', 'x1', now() - interval '10 hours'),
  ($2, '[ACCIÓN] Asiri lo tomó como aviso de pago o comprobante: «ahí va». Verificar en el chat e imputarlo al turno.', 'bot', 'x2', now() - interval '100 hours')`,
  [T.previo, T.viejo]);

// ---------------------------------------------------------------- 1. migración como sbowner (no superuser), DOS veces
await db.exec(UP);
await db.exec(UP);
check(true, 'up x2');
const rls = await q1(`select bool_and(relrowsecurity) as r from pg_class where oid in ('public.casos'::regclass, 'public.casos_eventos'::regclass, 'public.casos_prefijos'::regclass)`);
check(rls.r === true, 'RLS activo en las 3 tablas');
check((await q1(`select count(*)::int as n from pg_policies where tablename like 'casos%'`)).n === 0, 'sin policies');
if (hayPublicacion) {
  check((await q1(`select count(*)::int as n from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'casos'`)).n === 1, 'casos en supabase_realtime (bus en vivo)');
} else console.log('(PGlite sin publicaciones: no se prueba supabase_realtime)');
// la config de los triggers: lock_timeout corto (nunca hacen esperar al bot)
for (const fn of ['casos_tg_desde_escalacion', 'casos_tg_desde_triaje', 'registrar_aviso']) {
  const c = await q1(`select proconfig, prosecdef from pg_proc where proname = $1`, [fn]);
  check(c.prosecdef === true && (c.proconfig || []).includes('lock_timeout=1s') && (c.proconfig || []).includes('search_path=""'), `${fn}: security definer + lock_timeout=1s + search_path vacío ${JSON.stringify(c)}`);
}

// ---------------------------------------------------------------- 2. carga inicial: solo las últimas 72 h
{
  const p = await casosDe(T.previo);
  check(p.length === 1 && p[0].estado === 'nuevo' && p[0].tipo === 'consulta' && p[0].contador === 1, 'backfill: aviso de hace 10 h nace nuevo ' + JSON.stringify(p));
  check((await casosDe(T.viejo)).length === 0, 'backfill: aviso de hace 100 h no entra');
  const ev = await qn(`select * from public.casos_eventos where caso_id = $1`, [p[0].id]);
  check(ev.length === 1, 'up x2 no duplica la carga inicial (idempotente por tabla+id)');
}

// ---------------------------------------------------------------- 3. el tipo sale de lo que registró el bot
const casos1 = [
  [T.a, '[TRIAJE] escalar | tipo: bracket_suelto (alta) | videos enviados: ninguno | Paciente: «se le salió el aparato»', 'urgencia'],
  [T.b, '[ACCIÓN] Asiri lo tomó como aviso de pago o comprobante: «te mando el comprobante». Verificar en el chat e imputarlo al turno.', 'pago'],
  [T.c, 'El paciente pidió hablar con una persona: «quiero hablar con la secretaria»', 'pidio_persona'],
  [T.d, '[FYI] Lista de espera: la paciente quiere adelantar su turno si se libera uno.', 'aviso'],
  [T.e, '[CancelarReprogramar] no se pudo reprogramar el turno del jueves', 'turno'],
  [T.f, 'Contacto silenciado (proveedor, Farmacia) escribió: «urgente». Si es paciente, cambiarle el tipo a proveedor para que Asiri vuelva a atenderlo.', 'urgencia'],
  [T.g, 'El paciente consulta por una orden de estudios', 'consulta'],
  // TEXTO DEL PACIENTE que "parece" urgencia o pago, sin etiqueta del bot al principio: NO decide el tipo
  [T.h, 'Consulta derivada: «es urgente, me duele mucho, le mando el comprobante de pago»', 'consulta'],
  [T.i, '[ACCIÓN] Fuera de lo que atiende Asiri: «[TRIAJE] me duele, Asiri lo tomó como aviso de pago». Contestarle por este chat.', 'consulta'],
  [T.j, '   [FYI] con espacios adelante', 'aviso'],
];
for (const [tel, motivo, tipo] of casos1) {
  const id = await esc(tel, motivo);
  const cs = await casosDe(tel);
  check(cs.length === 1 && cs[0].tipo === tipo && cs[0].estado === 'nuevo' && cs[0].contador === 1 && cs[0].ref_tabla === 'escalaciones_log' && Number(cs[0].ref_id) === Number(id),
        `tipo ${tipo} para «${motivo.slice(0, 50)}…» -> ${JSON.stringify(cs.map((c) => [c.tipo, c.estado]))}`);
}
{ // origen triaje_video (aviso pasivo de triaje/decidir.js) -> aviso
  await esc(T.k, '[TRIAJE VIDEO] alambre_pincha Opción 1 — atendido con video canned, sin escalar. Paciente: «me pincha»', { origen: 'triaje_video' });
  const cs = await casosDe(T.k); check(cs.length === 1 && cs[0].tipo === 'aviso' && cs[0].origen === 'triaje_video', 'origen triaje_video -> aviso');
}
{ // no son casos: avisos técnicos, housekeeping, sin teléfono, grupos
  const antes = (await q1(`select count(*)::int as n from public.casos`)).n;
  await esc(T.g, '[FALLO TECNICO] El Health Check falló por dentro');
  await esc(T.g, 'Aviso técnico de Asiri: no se pudo leer la lista de contactos silenciados.');
  await esc(T.g, 'El bot detectó que ya estás atendiendo este chat y se quedó callado.');
  await esc(null, 'El paciente pidió hablar con una persona: «x»');
  await esc('', '[TRIAJE] algo');
  await esc('120363000000000001@g.us', '[ACCIÓN] algo del grupo');
  check((await q1(`select count(*)::int as n from public.casos`)).n === antes, 'técnicos / ruido / sin teléfono / grupo: no crean caso');
  check((await q1(`select count(*)::int as n from public.escalaciones_log where motivo like '[FALLO%' or telefono is null or telefono = ''`)).n === 3, 'pero las filas del log entraron');
}
{ // JID con sufijo -> misma clave que pacientes.telefono
  await esc(T.a + '@s.whatsapp.net', 'El paciente pidió hablar con una persona: «hola»');
  check((await abierto(T.a, 'pidio_persona'))?.contador === 1, 'telefono con @s.whatsapp.net se normaliza');
}
{ // columna estructurada futura (tipo_aviso): manda sobre la etiqueta
  await db.exec(`alter table public.escalaciones_log add column tipo_aviso text`);
  await esc(T.e, 'texto cualquiera sin etiqueta', { tipo_aviso: 'pago' });
  check((await abierto(T.e, 'pago'))?.contador === 1, 'tipo_aviso (columna futura) decide el tipo');
  await esc(T.e, '[TRIAJE] urgente', { tipo_aviso: 'ignorar' });
  check(!(await abierto(T.e, 'urgencia')), "tipo_aviso 'ignorar' no crea caso");
  await db.exec(`alter table public.escalaciones_log drop column tipo_aviso`);
}

// ---------------------------------------------------------------- 4. dedupe por teléfono + tipo, contador y fusión con el triaje
{
  await esc(T.b, '[ACCIÓN] Asiri lo tomó como aviso de pago o comprobante: «otro comprobante». Verificar en el chat e imputarlo al turno.');
  const p = await abierto(T.b, 'pago');
  check(p.contador === 2 && /otro comprobante/.test(p.motivo), 'mismo teléfono + tipo: un solo caso, contador 2 y el motivo más nuevo');
  await esc(T.b, 'El paciente pidió hablar con una persona: «x»');
  check((await casosDe(T.b)).filter((c) => c.estado !== 'resuelto').length === 2, 'otro tipo para el mismo teléfono: otro caso');
}
{ // la MISMA escalación vista por escalaciones_log ([TRIAJE]) y por triaje_urgencias_log: no cuenta dos veces
  const u0 = await abierto(T.a, 'urgencia');
  check(u0.contador === 1, 'urgencia del paso 3 con contador 1');
  const tid = await tri(T.a);
  const u1 = await abierto(T.a, 'urgencia');
  check(u1.contador === 1 && u1.detalle.triaje_tipo === 'bracket_suelto' && u1.ref_tabla === 'escalaciones_log', 'triaje dentro de la ventana: se fusiona (contador 1) y enriquece ' + JSON.stringify(u1));
  const ev = await q1(`select detalle from public.casos_eventos where ref_tabla = 'triaje_urgencias_log' and ref_id = $1`, [tid]);
  check(ev && ev.detalle.fusionado === true, 'la bitácora anota la fusión');
  await esc(T.a, '[TRIAJE] escalar | tipo: bracket_suelto (alta) | Paciente: «sigue igual»');
  check((await abierto(T.a, 'urgencia')).contador === 2, 'otra escalación del mismo log: suma (contador 2)');
  await tri(T.a);
  check((await abierto(T.a, 'urgencia')).contador === 2, 'y su fila de triaje se fusiona');
  await db.query(`update public.casos set primer_aviso_at = now() - interval '20 minutes', ultimo_aviso_at = now() - interval '10 minutes' where id = $1`, [u1.id]);
  await tri(T.a, { tipo: 'alambre_pincha' });
  check((await abierto(T.a, 'urgencia')).contador === 3, 'triaje fuera de la ventana de 5 min: suma');
}
{ // triaje: solo 'escalado' y no sombra crea caso
  const n0 = (await q1(`select count(*)::int as n from public.casos`)).n;
  await tri(T.c, { accion: 'video' });
  await tri(T.c, { accion: 'cierre' });
  await tri(T.c, { accion: 'silencio_humano' });
  await tri(T.c, { modo: 'sombra' });
  check((await q1(`select count(*)::int as n from public.casos`)).n === n0, 'triaje video / cierre / silencio_humano / sombra: sin caso');
  await tri(T.c, { tipo: null, texto: null });
  const u = await abierto(T.c, 'urgencia');
  check(u && u.motivo === 'Urgencia' && u.origen === 'triaje', 'triaje escalado sin tipo ni texto: urgencia (lado seguro) ' + JSON.stringify(u?.motivo));
}
{ // el CTE exacto de triaje/decidir.js (aviso pasivo): escalaciones_log + triaje_urgencias_log en un solo statement
  const r = await q1(`with h as (insert into public.n8n_chat_histories(session_id, message) values ($1, '{"type":"human"}'::jsonb) returning id),
      a as (insert into public.n8n_chat_histories(session_id, message) select $1, '{"type":"ai"}'::jsonb from h returning id),
      e as (insert into public.escalaciones_log(telefono, motivo, origen, exec_id) select $1, '[TRIAJE VIDEO] ligadura Opción 1 — atendido con video canned, sin escalar. Paciente: «x»', 'triaje_video', 'ex9' where true returning id),
      u as (select null::bigint as id)
    insert into public.triaje_urgencias_log(escalacion_id, telefono, exec_id, mensaje_paciente, gate_red_flags, gate_escala, tipo, confianza, razon, modelo, modo, accion, video_enviado, opcion_enviada, chat_history_id)
    select (select id from e), $1, 'ex9', 'x', '[]'::jsonb, false, 'ligadura_pincha', 'alta', 'r', 'm', 'piloto', 'video', 'ligadura/opcion1', 1, (select id from a) returning id as triaje_log_id`, [T.d]);
  check(r && r.triaje_log_id, 'CTE de decidir.js entra con los triggers');
  check((await abierto(T.d, 'aviso')).contador === 2, 'y el aviso pasivo suma al aviso abierto del mismo teléfono');
}

// ---------------------------------------------------------------- 5. 72 h: lo viejo nace archivado y no se mezcla
{
  await db.query(`insert into public.escalaciones_log (telefono, motivo, created_at) values ($1, '[FYI] viejo', now() - interval '80 hours')`, [T.d]);
  const cs = await casosDe(T.d);
  const viejo = cs.find((c) => c.motivo === '[FYI] viejo');
  check(viejo && viejo.estado === 'resuelto' && viejo.resuelto_por === 'sistema', 'aviso de hace 80 h: nace resuelto por sistema');
  check((await abierto(T.d, 'aviso')).contador === 2, 'y no suma al abierto');
}

// ---------------------------------------------------------------- 6. acciones del panel + bitácora
{
  const u = await abierto(T.g, 'consulta');
  let r = await accion('caso_tomar', u.id, 'Irina');
  check(r.ok && r.caso.estado === 'en_curso' && r.caso.dueno === 'irina' && r.caso.tomado_at, 'tomar: en curso con dueño (minúsculas)');
  r = await accion('caso_tomar', u.id, 'irina');
  check(r.ok && r.ya_estaba, 'tomar dos veces: ya_estaba');
  r = await accion('caso_tomar', u.id, 'lucas');
  check(!r.ok && r.error === 'YA_TOMADO' && r.dueno === 'irina', 'tomar uno tomado por otra persona: YA_TOMADO');
  r = await accion('caso_soltar', u.id, 'irina');
  check(r.ok && r.caso.estado === 'nuevo' && r.caso.dueno === null, 'soltar (deshacer tomar): vuelve a nuevo sin dueño');
  await accion('caso_tomar', u.id, 'irina');
  r = await accion('caso_esperando', u.id, 'irina');
  check(r.ok && r.caso.estado === 'esperando_paciente' && r.caso.esperando_desde, 'esperando paciente');
  await esc(T.g, 'El paciente consulta otra vez por la orden');
  const u2 = await abierto(T.g, 'consulta');
  check(u2.id === u.id && u2.estado === 'en_curso' && u2.contador === 2 && u2.esperando_desde === null, 'el paciente vuelve a escribir: de esperando a en curso (sigue con dueño)');
  r = await accion('caso_resolver', u.id, 'irina', 'DNI 12345678 cargado', true);
  check(!r.ok && r.error === 'NOTA_INVALIDA', 'nota con DNI/teléfono: rechazada');
  r = await accion('caso_resolver', u.id, 'irina', 'Le pasé la orden por el chat', false);
  check(r.ok && r.caso.estado === 'resuelto' && r.caso.resuelto_por === 'irina' && r.caso.devolver_bot === false && r.caso.nota_resolucion === 'Le pasé la orden por el chat', 'resolver con nota y sin devolver al bot');
  r = await accion('caso_resolver', u.id, 'irina');
  check(r.ok && r.ya_estaba, 'resolver dos veces: ya_estaba');
  r = await accion('caso_reabrir', u.id, 'irina');
  check(r.ok && r.caso.estado === 'en_curso' && r.caso.resuelto_at === null && r.caso.nota_resolucion === null, 'reabrir (deshacer resolver): vuelve a en curso');
  await accion('caso_resolver', u.id, 'irina');
  await esc(T.g, 'El paciente consulta una tercera cosa');
  const nuevo = await abierto(T.g, 'consulta');
  check(nuevo && nuevo.id !== u.id && nuevo.estado === 'nuevo' && nuevo.contador === 1, 'aviso después de resuelto: caso nuevo');
  r = await accion('caso_reabrir', u.id, 'irina');
  check(!r.ok && r.error === 'HAY_OTRO_ABIERTO', 'no se reabre si ya hay otro abierto del mismo motivo');
  r = await accion('caso_tomar', nuevo.id, 'Juan Perez');
  check(!r.ok && r.error === 'ACTOR_INVALIDO', 'actor con espacios: ACTOR_INVALIDO');
  r = await accion('caso_tomar', 999999, 'irina');
  check(!r.ok && r.error === 'NO_EXISTE', 'caso inexistente');
  const ev = (await qn(`select evento, actor, estado_antes, estado_despues from public.casos_eventos where caso_id = $1 order by id`, [u.id])).map((e) => `${e.evento}:${e.actor}:${e.estado_antes}>${e.estado_despues}`);
  check(JSON.stringify(ev) === JSON.stringify(['creado:bot:null>nuevo', 'tomado:irina:nuevo>en_curso', 'soltado:irina:en_curso>nuevo', 'tomado:irina:nuevo>en_curso',
    'esperando:irina:en_curso>esperando_paciente', 'aviso:bot:esperando_paciente>en_curso', 'resuelto:irina:en_curso>resuelto', 'reabierto:irina:resuelto>en_curso',
    'resuelto:irina:en_curso>resuelto']), 'bitácora completa con autor: ' + JSON.stringify(ev));
  // urgencia: tomar y resolver devolviendo a Asiri (los 2 toques de la bandeja)
  const urg = await abierto(T.f, 'urgencia');
  r = await accion('caso_tomar', urg.id, 'irina'); check(r.ok, 'urgencia: tomar');
  r = await accion('caso_resolver', urg.id, 'irina', null, true); check(r.ok && r.caso.devolver_bot === true && r.caso.nota_resolucion === null, 'urgencia: resolver devolviendo a Asiri, sin nota');
}

// ---------------------------------------------------------------- 7. FAIL-SAFE: con el disparador roto, el insert del bot entra igual
{
  const nLog = async () => (await q1(`select count(*)::int as n from public.escalaciones_log`)).n;
  const nTri = async () => (await q1(`select count(*)::int as n from public.triaje_urgencias_log`)).n;
  // (a) falta la tabla casos
  await db.exec(`alter table public.casos rename to casos_x`);
  let n0 = await nLog();
  let e1 = await err(`insert into public.escalaciones_log (telefono, motivo, origen, exec_id) values ($1, '[TRIAJE] roto a', 'bot', 'r1')`, [T.h]);
  check(e1 === null && (await nLog()) === n0 + 1, '(a) sin tabla casos: el insert en escalaciones_log entra');
  n0 = await nTri();
  e1 = await err(`insert into public.triaje_urgencias_log (telefono, exec_id, mensaje_paciente, tipo, modo, accion) values ($1, 'r1', 'x', 'otra_urgencia', 'piloto', 'escalado')`, [T.h]);
  check(e1 === null && (await nTri()) === n0 + 1, '(a) sin tabla casos: el insert en triaje_urgencias_log entra');
  await db.exec(`alter table public.casos_x rename to casos`);
  check(!(await abierto(T.h, 'urgencia')), '(a) y no quedó caso a medias');
  // (b) registrar_aviso explota
  await db.exec(`create or replace function public.registrar_aviso(p_telefono text, p_tipo text, p_motivo text, p_origen text,
      p_ref_tabla text default null, p_ref_id bigint default null, p_exec_id text default null, p_cuando timestamptz default null,
      p_detalle jsonb default '{}'::jsonb, p_fusionar_seg integer default 300) returns jsonb language plpgsql as $$
    begin raise exception 'roto a proposito'; end $$`);
  n0 = await nLog();
  const r = await q1(`insert into public.escalaciones_log (telefono, motivo, origen, exec_id) values ($1, 'El paciente pidió hablar con una persona: «roto b»', 'bot', 'r2') returning id`, [T.h]);
  check(r && r.id && (await nLog()) === n0 + 1, '(b) registrar_aviso con error: el insert entra y devuelve su id (RETURNING del nodo de n8n)');
  check(!(await abierto(T.h, 'pidio_persona')), '(b) sin caso');
  // (c) falta la función del tipo
  await db.exec(`drop function public.casos_tipo_de_escalacion(text, text, jsonb)`);
  e1 = await err(`insert into public.escalaciones_log (telefono, motivo) values ($1, '[FYI] roto c')`, [T.h]);
  check(e1 === null, '(c) sin casos_tipo_de_escalacion: el insert entra');
  // (d) un check de casos que falla por dentro (motivo vacío forzado no puede: se fuerza un tipo inválido desde el trigger)
  await db.exec(`create or replace function public.casos_tipo_de_escalacion(p_origen text, p_motivo text, p_fila jsonb default '{}'::jsonb)
    returns text language sql as $$ select 'inventado'::text $$`);
  await db.exec(`create or replace function public.registrar_aviso(p_telefono text, p_tipo text, p_motivo text, p_origen text,
      p_ref_tabla text default null, p_ref_id bigint default null, p_exec_id text default null, p_cuando timestamptz default null,
      p_detalle jsonb default '{}'::jsonb, p_fusionar_seg integer default 300) returns jsonb language plpgsql as $$
    begin insert into public.casos (telefono, tipo, motivo, origen) values (p_telefono, p_tipo, p_motivo, p_origen); return '{}'::jsonb; end $$`);
  e1 = await err(`insert into public.escalaciones_log (telefono, motivo) values ($1, 'violación de check adentro')`, [T.h]);
  check(e1 === null && !(await q1(`select 1 as x from public.casos where tipo = 'inventado'`)), '(d) check_violation adentro del trigger: el insert entra y no queda nada');
  // service_role (PostgREST con la clave secreta) también puede seguir insertando
  await db.exec('set role service_role');
  e1 = await err(`insert into public.escalaciones_log (telefono, motivo) values ($1, '[FYI] por postgrest')`, [T.h]);
  await db.exec('reset role; set role sbowner');
  check(e1 === null, '(d) service_role inserta en escalaciones_log con el trigger roto');
  // re-aplicar la migración arregla todo (create or replace) y la carga inicial levanta lo que quedó sin caso de las últimas 72 h
  await db.exec(UP);
  const pp = await abierto(T.h, 'pidio_persona');
  check(pp && pp.contador === 1, 're-up: el aviso que entró con el trigger roto ahora tiene su caso (backfill idempotente)');
  check((await abierto(T.h, 'urgencia'))?.contador >= 1, 're-up: la urgencia del paso (a) también');
  await esc(T.h, '[FYI] después de arreglar');
  check((await abierto(T.h, 'aviso'))?.contador >= 1, 'trigger sano otra vez');
}

// ---------------------------------------------------------------- 8. permisos (como en Supabase: PostgREST entra con estos roles)
await db.exec('reset role');
const unCaso = (await q1(`select id from public.casos where estado <> 'resuelto' order by id limit 1`)).id;
for (const rol of ['anon', 'authenticated']) {
  await db.exec(`set role ${rol}`);
  check(await err(`select * from public.casos`) === '42501', `${rol}: no lee casos`);
  check(await err(`select * from public.casos_eventos`) === '42501', `${rol}: no lee la bitácora`);
  check(await err(`select public.caso_tomar($1, 'x')`, [unCaso]) === '42501', `${rol}: no toma casos`);
  check(await err(`select public.registrar_aviso('5490000000011', 'consulta', 'x', 'bot')`) === '42501', `${rol}: no registra avisos`);
  await db.exec('reset role');
}
await db.exec('set role service_role');
check((await q1(`select count(*)::int as n from public.casos`)).n > 0, 'service_role: lee casos (el panel)');
check((await q1(`select count(*)::int as n from public.casos_eventos`)).n > 0, 'service_role: lee la bitácora');
{ const r = await q1(`select public.caso_tomar($1, 'lucas') as r`, [unCaso]); check(r.r.ok === true || r.r.error === 'YA_TOMADO', 'service_role: ejecuta caso_tomar'); }
check(await err(`insert into public.casos (telefono, tipo, motivo, origen) values ('5490000000011', 'consulta', 'x', 'panel')`) === '42501', 'service_role: no inserta casos directo');
check(await err(`update public.casos set estado = 'resuelto'`) === '42501', 'service_role: no edita casos directo');
check(await err(`delete from public.casos_eventos`) === '42501', 'service_role: no borra la bitácora');
check(await err(`select public.registrar_aviso('5490000000011', 'consulta', 'x', 'bot')`) === '42501', 'service_role: no ejecuta registrar_aviso (solo los triggers)');
check(await err(`select * from public.casos_prefijos`) === '42501', 'service_role: no lee casos_prefijos');
check(await err(`select public.casos_backfill(72)`) === '42501', 'service_role: no corre el backfill');
await db.exec('reset role');

// ---------------------------------------------------------------- 9. costo: la búsqueda del caso abierto usa el índice único parcial
await db.exec('set role sbowner; set enable_seqscan = off;');
const plan = (await db.query(`explain (costs off) select * from public.casos c where c.telefono = $1 and c.tipo = $2 and c.estado <> 'resuelto'`, [T.a, 'urgencia'])).rows.map((x) => x['QUERY PLAN']).join('\n');
check(/casos_abierto_uk/.test(plan), 'plan con casos_abierto_uk:\n' + plan);
await db.exec('set enable_seqscan = on;');
const t0 = performance.now(); for (let i = 0; i < 200; i++) await esc(T.j, '[FYI] carga ' + i); const ms = (performance.now() - t0) / 200;
console.log(`insert en escalaciones_log con trigger: ${ms.toFixed(3)} ms por fila (PGlite/WASM, 200 filas)`);
check((await abierto(T.j, 'aviso')).contador === 201, '200 avisos seguidos: un solo caso, contador 201');
await db.exec('reset role');

// ---------------------------------------------------------------- 10. vuelta atrás y re-aplicar
await db.exec('set role sbowner');
const logAntes = (await q1(`select count(*)::int as n from public.escalaciones_log`)).n;
await db.exec(DOWN);
check((await q1(`select count(*)::int as n from pg_class where relname in ('casos', 'casos_eventos', 'casos_prefijos')`)).n === 0, 'down: sin tablas');
check((await q1(`select count(*)::int as n from pg_proc where proname like 'caso%' or proname = 'registrar_aviso'`)).n === 0, 'down: sin funciones');
check((await q1(`select count(*)::int as n from pg_trigger where tgname like 'casos_%'`)).n === 0, 'down: sin triggers');
check((await q1(`select count(*)::int as n from public.escalaciones_log`)).n === logAntes, 'down: escalaciones_log intacto');
check(await err(`insert into public.escalaciones_log (telefono, motivo) values ($1, '[FYI] sin casos')`, [T.a]) === null, 'down: el bot sigue insertando');
check(await err(`insert into public.triaje_urgencias_log (telefono, tipo, modo, accion) values ($1, 'x', 'piloto', 'escalado')`, [T.a]) === null, 'down: el triaje sigue insertando');
await db.exec(UP);
check((await q1(`select count(*)::int as n from public.casos where estado <> 'resuelto'`)).n > 0, 're-up: la carga inicial vuelve a armar los casos de las últimas 72 h');
await db.exec('reset role');

if (avisos.length) console.log(`(${avisos.length} WARNING de Postgres durante las pruebas de fail-safe, esperados)`);
console.log(`\n${ok} OK, ${fallas} fallas`);
process.exit(fallas ? 1 : 0);
