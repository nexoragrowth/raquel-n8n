// test_migracion_panel_usuarios.mjs — 2026-11-02 · prueba LOCAL (PGlite = Postgres 16 en WASM, en memoria) de sql/2026-11-02_panel_usuarios.sql y su _DOWN
// contra una réplica de los roles y del RLS automático del Supabase v3. No toca ninguna base real. Datos 100% inventados.
// Lo central: (1) idempotente (UP x2); (2) RLS activo y SIN policies; (3) anon/authenticated no leen ni escriben (hay hashes); service_role sí;
// (4) login único y con la forma válida (minúsculas, 3-32); (5) defaults (activo, created_at); (6) no está en Realtime; (7) el DOWN la borra y es idempotente.
// Requiere @electric-sql/pglite (devDependency del repo: `npm install`) o PGLITE_PATH.   Uso: node tests/test_migracion_panel_usuarios.mjs
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const { PGlite } = await import(process.env.PGLITE_PATH ? pathToFileURL(path.join(process.env.PGLITE_PATH, 'dist', 'index.js')).href : '@electric-sql/pglite');
const RAIZ = new URL('../', import.meta.url);
const UP = readFileSync(new URL('sql/2026-11-02_panel_usuarios.sql', RAIZ), 'utf8');
const DOWN = readFileSync(new URL('sql/2026-11-02_panel_usuarios_DOWN.sql', RAIZ), 'utf8');

const db = new PGlite();
let fallas = 0, ok = 0;
const check = (cond, msg) => { if (cond) { ok++; } else { fallas++; console.log('FALLA:', msg); } };
const q1 = async (sql, p) => (await db.query(sql, p)).rows[0];
const err = async (sql, p) => { try { await db.query(sql, p); return null; } catch (e) { return e.code || e.message; } };

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
// Supabase deja los privilegios por defecto ABIERTOS a anon/authenticated: la migración tiene que cerrarlos.
await db.exec(`set role sbowner;
  alter default privileges for role sbowner in schema public grant all on tables to anon, authenticated, service_role;`);
const hayPublicacion = (await err(`reset role; create publication supabase_realtime`)) === null;
await db.exec('reset role; set role sbowner');

// 1. UP dos veces
await db.exec(UP);
await db.exec(UP);
check(true, 'up x2');
check((await q1(`select to_regclass('public.panel_usuarios') is not null as e`)).e, 'la tabla existe');
check((await q1(`select relrowsecurity as r from pg_class where oid = 'public.panel_usuarios'::regclass`)).r === true, 'RLS activo');
check((await q1(`select count(*)::int as n from pg_policies where tablename = 'panel_usuarios'`)).n === 0, 'sin policies');

// 2. permisos
const p = await q1(`select has_table_privilege('anon','public.panel_usuarios','select') as a_s, has_table_privilege('anon','public.panel_usuarios','insert') as a_i,
  has_table_privilege('authenticated','public.panel_usuarios','select') as u_s, has_table_privilege('authenticated','public.panel_usuarios','update') as u_u,
  has_table_privilege('service_role','public.panel_usuarios','select') as s_s, has_table_privilege('service_role','public.panel_usuarios','insert') as s_i,
  has_table_privilege('service_role','public.panel_usuarios','update') as s_u, has_table_privilege('service_role','public.panel_usuarios','delete') as s_d`);
check(!p.a_s && !p.a_i && !p.u_s && !p.u_u, 'anon/authenticated sin acceso ' + JSON.stringify(p));
check(p.s_s && p.s_i && p.s_u && p.s_d, 'service_role con select/insert/update/delete');

// 3. como service_role: alta, defaults y reglas
const H = 'a'.repeat(64);
const ins = (login, extra = '') => err(`insert into public.panel_usuarios (login, salt, hash${extra ? ', ' + extra.split('=')[0] : ''}) values ($1, 'salt', '${H}'${extra ? ', ' + extra.split('=')[1] : ''})`, [login]);
await db.exec('reset role; set role service_role');
check(await ins('sec.nueva') === null, 'alta válida');
const f = await q1(`select * from public.panel_usuarios where login = 'sec.nueva'`);
check(f.activo === true && f.created_at && f.desactivado_at === null && f.nombre === null, 'defaults: activo, created_at, sin desactivación ' + JSON.stringify(f));
check(await ins('sec.nueva') === '23505', 'login único (clave primaria)');
for (const malo of ['Sec.Nueva2', 'ab', '.ab', '-abc', 'a'.repeat(33), 'con espacio', 'ñandu', "x'; drop table--"]) {
  check(await ins(malo) === '23514', 'login inválido rechazado: ' + malo);
}
check(await ins('abc') === null && await ins('a'.repeat(32)) === null, 'bordes válidos: 3 y 32 caracteres');
check(await err(`update public.panel_usuarios set activo = false, desactivado_at = now(), desactivado_por = 'lucas' where login = 'sec.nueva'`) === null, 'service_role desactiva');
check((await q1(`select activo, desactivado_por from public.panel_usuarios where login = 'sec.nueva'`)).activo === false, 'quedó desactivado');
check(await err(`insert into public.panel_usuarios (login, salt, hash) values ('sin.hash', 'x', null)`) === '23502', 'hash obligatorio');

// 4. anon / authenticated no pueden ni leer ni escribir
for (const rol of ['anon', 'authenticated']) {
  await db.exec(`reset role; set role ${rol}`);
  check(await err(`select * from public.panel_usuarios`) === '42501', rol + ': no lee');
  check(await err(`insert into public.panel_usuarios (login, salt, hash) values ('intruso', 'x', 'y')`) === '42501', rol + ': no escribe');
}
await db.exec('reset role; set role sbowner');

// 5. Realtime
if (hayPublicacion) check((await q1(`select count(*)::int as n from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'panel_usuarios'`)).n === 0, 'no está en supabase_realtime');
else console.log('(PGlite sin publicaciones: no se prueba supabase_realtime)');

// 6. DOWN (dos veces)
await db.exec(DOWN);
await db.exec(DOWN);
check(!(await q1(`select to_regclass('public.panel_usuarios') is not null as e`)).e, 'DOWN borra la tabla (x2 sin error)');
// y se puede volver a subir
await db.exec(UP);
check((await q1(`select to_regclass('public.panel_usuarios') is not null as e`)).e, 'UP después del DOWN');

console.log(`
migración panel_usuarios: ${ok} OK, ${fallas} fallas`);
process.exit(fallas ? 1 : 0);
