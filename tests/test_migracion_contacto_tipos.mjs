// test_migracion_contacto_tipos.mjs — 2026-10-14 · prueba LOCAL (PGlite = Postgres 16.4 en WASM, en memoria) de la migración del Día 1
// (sql/2026-10-14_contacto_tipos.sql y su _DOWN) contra una réplica del esquema y los roles del Supabase v3. No toca ninguna base real.
// Teléfonos 100% sintéticos (forma 5490000000xxx). También corre el SQL EXACTO de los nodos "Seg: Consultar Tipo"/"Seg: Tipo Salida"
// (SQL_TIPO de scripts/apply_dia1_segmentacion.py) y verifica que devuelve SIEMPRE 1 fila.
// Requiere @electric-sql/pglite 0.2.17 (devDependency del repo: `npm install`), o apuntar PGLITE_PATH a una carpeta
// node_modules/@electric-sql/pglite ya instalada. scripts/apply_dia1_segmentacion.py lo corre (el --apply exige verde).   Uso: node tests/test_migracion_contacto_tipos.mjs
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
const { PGlite } = await import(process.env.PGLITE_PATH ? pathToFileURL(path.join(process.env.PGLITE_PATH, 'dist', 'index.js')).href : '@electric-sql/pglite');
const RAIZ = new URL('../', import.meta.url);
const UP = readFileSync(new URL('sql/2026-10-14_contacto_tipos.sql', RAIZ), 'utf8').replaceAll('for role postgres', 'for role sbowner');
const DOWN = readFileSync(new URL('sql/2026-10-14_contacto_tipos_DOWN.sql', RAIZ), 'utf8');
const SQL_TIPO = (() => {
  const py = readFileSync(new URL('scripts/apply_dia1_segmentacion.py', RAIZ), 'utf8');
  const m = py.match(/SQL_TIPO = \(([\s\S]*?)\)\r?\n/);
  return m[1].split(/\r?\n/).map(l => (l.match(/"([^"]*)"/) || [, ''])[1]).join('');
})();
const db = new PGlite();
let fallas = 0, ok = 0;
const check = (cond, msg) => { if (cond) { ok++; } else { fallas++; console.log('FALLA:', msg); } };
const q1 = async (sql, p) => (await db.query(sql, p)).rows[0];
const err = async (sql, p) => { try { await db.query(sql, p); return null; } catch (e) { return e.code || e.message; } };
const ruta = async (tel) => (await q1('select public.contacto_ruta($1) as r', [tel])).r;
const poner = async (...a) => (await q1('select public.contacto_tipo_poner($1,$2,$3,$4,$5,$6,$7,$8,$9) as r',
  [a[0], a[1], a[2], a[3], a[4] ?? 'script', a[5] ?? null, a[6] ?? null, a[7] ?? null, a[8] ?? false])).r;
const cerrar = async (...a) => (await q1('select public.contacto_tipo_cerrar($1,$2,$3,$4,$5,$6) as r',
  [a[0], a[1], a[2], a[3], a[4] ?? null, a[5] ?? null])).r;

// ---------------------------------------------------------------- replica de Supabase (roles, defaults abiertos, event trigger)
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
  create index idx_recordatorios_telefono on public.recordatorios_enviados (telefono);
  reset role;`);

// contactos inventados: 13 digitos 549..., un @lid, un grupo, 300 de relleno para que el planificador use indices
const T = { dra: '5490000000001', prov: '5490000000002', col: '5490000000003', nop: '5490000000004', dev: '5490000000005',
            pac: '5490000000006', nuevo: '5490000000007', conficha: '5490000000008', lid: '123456789012345@lid', grupo: '120363000000000001@g.us',
            fantasma: '5490000009999' };
await db.exec(`set role sbowner;
  insert into public.pacientes (telefono) values ${Object.entries(T).filter(([k]) => k !== 'fantasma').map(([, t]) => `('${t}')`).join(',')};
  insert into public.pacientes (telefono) select '549000200' || lpad(g::text, 4, '0') from generate_series(1, 300) g;
  insert into public.recordatorios_enviados (telefono) values ('${T.conficha}'), ('${T.dev}');
  reset role;`);

// ---------------------------------------------------------------- 1. migracion como sbowner (no superuser), DOS veces
await db.exec('set role sbowner');
await db.exec(UP);
await db.exec(UP);
check(true, 'up x2');
const rls = await q1(`select bool_and(relrowsecurity) as r from pg_class where oid in ('public.contacto_roles'::regclass, 'public.contacto_roles_notas'::regclass)`);
check(rls.r === true, 'RLS activo en las 2 tablas');
check((await q1(`select count(*)::int as n from pg_policies where tablename like 'contacto_roles%'`)).n === 0, 'sin policies');

// ---------------------------------------------------------------- 2. sin tipo = hoy
for (const k of ['nuevo', 'pac', 'lid', 'fantasma']) {
  const r = await ruta(T[k]);
  check(r.ok === true && r.tipo === null && r.silencia === false && r.red === false && r.fuente === 'sin_tipo' && Array.isArray(r.tipos) && r.tipos.length === 0,
        `sin tipo (${k}): ${JSON.stringify(r)}`);
}
for (const v of [null, '', '   ']) {
  const r = await ruta(v);
  check(r.ok === false && r.error === 'telefono_vacio' && r.silencia === false && r.red === false, `vacio ${JSON.stringify(v)} -> ${JSON.stringify(r)}`);
}
{ const r = await ruta(T.grupo); check(r.silencia === true && r.red === false && r.tipo === 'grupo' && r.fuente === 'jid_grupo', 'grupo por sufijo'); }

// ---------------------------------------------------------------- 3. carga tipo semilla
let r;
r = await poner(T.dra, 'interno', 'precarga_confirmada', 'Lucas', 'precarga', null, 'Precarga oct-2026, confirmado por Lucas', 'a0000000-0000-4000-8000-000000000001');
check(r.ok && !r.repetido && r.ruta.silencia === true && r.ruta.red === false && r.ruta.tipo === 'interno' && r.ruta.puesto_por === 'lucas', 'interno: silencia sin red ' + JSON.stringify(r));
r = await poner(T.prov, 'proveedor', 'precarga_propuesta_revisada', 'lucas', 'precarga', null, 'farmacia; respuestas automaticas', 'a0000000-0000-4000-8000-000000000002');
check(r.ok && r.ruta.silencia === true && r.ruta.red === true, 'proveedor: silencia con red');
r = await poner(T.col, 'colega', 'precarga_confirmada', 'lucas', 'precarga', 'centro_imagenes');
check(r.ok && r.ruta.silencia === true && r.ruta.red === true && r.ruta.subtipo === 'centro_imagenes', 'colega: silencia con red');
r = await poner(T.nop, 'no_paciente', 'precarga_propuesta_revisada', 'lucas', 'precarga');
check(r.ok && r.ruta.silencia === true && r.ruta.red === true, 'no_paciente: silencia con red');
// 'prueba' NO es un tipo (Anexo A: va en pacientes.es_prueba): se rechaza, y el telefono de desarrollo sin tipo no silencia
check((await poner(T.dev, 'prueba', 'clasificacion_manual', 'lucas', 'precarga')).error === 'TIPO_INVALIDO', 'prueba no es tipo');
check(await err(`select public.contacto_tipo_poner($1,'proveedor','telefono_prueba','lucas')`, [T.nuevo]) === '23514', 'motivo telefono_prueba ya no existe');
{ const x = await ruta(T.dev); check(x.tipo === null && x.silencia === false && x.red === false, 'telefono de desarrollo sin tipo: no silencia'); }
// idempotencia: misma clave -> repetido; sin clave y ya vigente -> ya_estaba
r = await poner(T.dra, 'interno', 'precarga_confirmada', 'lucas', 'precarga', null, null, 'a0000000-0000-4000-8000-000000000001');
check(r.ok && r.repetido === true, 'repetido por clave');
r = await poner(T.col, 'colega', 'precarga_confirmada', 'lucas', 'precarga');
check(r.ok && r.ya_estaba === true, 'ya_estaba sin clave');
r = await poner(T.prov, 'colega', 'precarga_confirmada', 'lucas', 'precarga', null, null, 'a0000000-0000-4000-8000-000000000001');
check(r.ok === false && r.error === 'CLAVE_EN_USO', 'clave usada por otro alta');
check((await q1(`select count(*)::int as n from public.contacto_roles`)).n === 4, '4 filas tras re-correr');
// validaciones
check((await poner(T.nuevo, 'dudoso', 'precarga_confirmada', 'lucas')).error === 'TIPO_INVALIDO', 'dudoso no es tipo');
check((await poner(T.fantasma, 'proveedor', 'precarga_confirmada', 'lucas')).error === 'CONTACTO_NO_EXISTE', 'telefono sin fila en pacientes');
check((await poner(T.conficha, 'proveedor', 'clasificacion_manual', 'lucas')).error === 'TIENE_FICHA', 'tiene ficha: pide doble confirmacion');
check((await poner(T.nuevo, 'proveedor', 'otro', 'lucas')).error === 'NOTA_REQUERIDA', 'motivo otro sin nota');
check(await err(`select public.contacto_tipo_poner($1,'proveedor','inventado','lucas')`, [T.nuevo]) === '23514', 'motivo fuera de lista -> check_violation');
check(await err(`select public.contacto_tipo_poner($1,'proveedor','clasificacion_manual','Juan Perez')`, [T.nuevo]) === '23514', 'actor con espacios -> check');
check(await err(`select public.contacto_tipo_poner($1,'proveedor','clasificacion_manual','lucas','script','dra')`, [T.nuevo]) === '23514', 'subtipo de otro tipo -> check');
check(await err(`select public.contacto_tipo_poner($1,'proveedor','clasificacion_manual','lucas','script',null,'llamar al 3884123456')`, [T.nuevo]) === '23514', 'nota con telefono -> check');
check((await q1(`select count(*)::int as n from public.contacto_roles where contacto_id = (select id from public.pacientes where telefono = $1)`, [T.nuevo])).n === 0, 'nada escrito tras errores');

// ---------------------------------------------------------------- 4. precedencia (el mas restrictivo manda) y prueba E2E
r = await poner(T.dev, 'proveedor', 'prueba_e2e', 'lucas', 'script', null, 'Prueba E2E Dia 1', null, true);
check(r.ok && r.ruta.tipo === 'proveedor' && r.ruta.silencia === true && JSON.stringify(r.ruta.tipos) === '["proveedor"]', 'proveedor temporal (con ficha, confirmado) -> silencia ' + JSON.stringify(r.ruta));
r = await cerrar(T.dev, 'proveedor', 'fin_prueba', 'lucas', null, 'b0000000-0000-4000-8000-000000000001');
check(r.ok && r.ruta.tipo === null && r.ruta.silencia === false, 'fin de prueba -> vuelve a sin tipo (no silencia)');
r = await cerrar(T.dev, 'proveedor', 'fin_prueba', 'lucas', null, 'b0000000-0000-4000-8000-000000000001');
check(r.ok && r.repetido === true, 'cierre repetido por clave');
r = await cerrar(T.dev, 'proveedor', 'fin_prueba', 'lucas');
check(r.ok && r.ya_estaba_cerrado === true, 'cierre sin vigente -> ya_estaba_cerrado');
await poner(T.pac, 'paciente', 'hecho_ficha', 'sistema', 'sistema');
await poner(T.pac, 'colega', 'clasificacion_manual', 'lucas', 'script', 'odontologo');
r = await ruta(T.pac);
check(r.tipo === 'colega' && r.silencia === true && r.red === true && JSON.stringify(r.tipos) === '["colega","paciente"]', 'colega que es paciente: silencia con red');
await poner(T.pac, 'interno', 'clasificacion_manual', 'lucas');
r = await ruta(T.pac);
check(r.tipo === 'interno' && r.red === false, 'interno gana sobre colega');
// formatos de entrada que el v6 / el panel podrian mandar
check((await ruta('+54 9 000 000-0002')).tipo === 'proveedor', 'numero escrito a mano con espacios y guion');
check((await ruta(T.lid)).fuente === 'sin_tipo' && (await ruta(T.lid)).contacto_id !== null, '@lid se busca entero');
for (const v of [T.prov, ' ' + T.prov + ' ', '+' + T.prov, T.prov + '@s.whatsapp.net', T.prov + ':12@s.whatsapp.net']) {
  check((await ruta(v)).tipo === 'proveedor', 'normaliza ' + JSON.stringify(v));
}
check((await ruta(T.prov.slice(0, 2) + T.prov.slice(3))).tipo === null, 'sin el 9 NO matchea (no se adivina)');

// ---------------------------------------------------------------- 5. inmutabilidad
check(await err(`update public.contacto_roles set tipo = 'colega' where contacto_id = (select id from public.pacientes where telefono = $1)`, [T.prov]) === '23001', 'no se edita');
check(await err(`delete from public.contacto_roles`) === '23001', 'no se borra');
check(['0A000', '23001'].includes(await err(`truncate public.contacto_roles`)), 'no se vacia (la FK de notas lo frena antes)');
check(await err(`truncate public.contacto_roles cascade`) === '23001', 'no se vacia ni con cascade');
check(await err(`truncate public.pacientes cascade`) === '23001', 'truncate pacientes cascade tampoco se lleva los tipos');
check(await err(`update public.contacto_roles set hasta = now(), quitado_por = 'x', motivo_baja = 'otro' where motivo_baja = 'fin_prueba'`) === '23001', 'no se re-cierra');
check(await err(`update public.contacto_roles set hasta = now() + interval '2 days', quitado_por = 'x', motivo_baja = 'otro' where hasta is null and tipo = 'colega' and subtipo = 'centro_imagenes'`) === '23514', 'hasta futuro');
check(await err(`insert into public.contacto_roles (contacto_id, tipo, origen, motivo, puesto_por) select id, 'proveedor', 'script', 'correccion', 'lucas' from public.pacientes where telefono = $1`, [T.prov]) === '23505', 'dos vigentes iguales');
check(await err(`delete from public.pacientes where telefono = $1`, [T.prov]) === '23503', 'FK restrict: no se borra un contacto con tipos');
check(await err(`delete from public.pacientes where telefono = '5490002000001'`) === null, 'un contacto sin tipos se sigue pudiendo borrar');
check(await err(`delete from public.contacto_roles_notas where momento = 'baja'`) === null, 'las notas se pueden borrar (supresion)');

// ---------------------------------------------------------------- 6. permisos (como en Supabase: PostgREST entra con estos roles)
await db.exec('reset role');
for (const rol of ['anon', 'authenticated']) {
  await db.exec(`set role ${rol}`);
  check(await err(`select public.contacto_ruta($1)`, [T.prov]) === '42501', `${rol}: no ejecuta contacto_ruta`);
  check(await err(`select * from public.contacto_roles`) === '42501', `${rol}: no lee contacto_roles`);
  check(await err(`select * from public.contacto_roles_notas`) === '42501', `${rol}: no lee notas`);
  check(await err(`select public.contacto_tipo_poner($1,'proveedor','correccion','x')`, [T.nuevo]) === '42501', `${rol}: no escribe`);
  check(await err(`select public.contacto_tel_normalizar('1')`) === '42501', `${rol}: no ejecuta normalizar`);
  await db.exec('reset role');
}
await db.exec('set role service_role');
{ const x = await q1(`select public.contacto_ruta($1) as r`, [T.prov]); check(x.r.silencia === true, 'service_role: ejecuta contacto_ruta (Gate Humano Final por PostgREST)'); }
check(await err(`select * from public.contacto_roles`) === '42501', 'service_role: no lee la tabla directo (Dia 1)');
check(await err(`select public.contacto_tipo_cerrar($1,'proveedor','error_carga','x')`, [T.prov]) === '42501', 'service_role: no escribe (Dia 1)');
check(await err(`insert into public.contacto_roles (contacto_id, tipo, origen, motivo, puesto_por) values (1,'interno','script','correccion','x')`) === '42501', 'service_role: no inserta');
check(await err(`select * from public.contacto_roles_notas`) === '42501', 'service_role: no lee notas');
check(await err(`select public.contacto_tel_normalizar('1')`) === '42501', 'service_role: no ejecuta normalizar');
check(await err(`select public.contacto_tipo_poner($1,'proveedor','correccion','x')`, [T.nuevo]) === '42501', 'service_role: no ejecuta poner');
await db.exec('reset role');
// defaults cerrados para lo que se cree despues
await db.exec(`set role sbowner; create table public.zz_nueva (x int); create function public.zz_f() returns int language sql as 'select 1'; reset role;`);
const d = await q1(`select has_table_privilege('anon','public.zz_nueva','select') as t_anon, has_table_privilege('service_role','public.zz_nueva','select') as t_sr,
                           has_function_privilege('anon','public.zz_f()','execute') as f_anon, has_function_privilege('service_role','public.zz_f()','execute') as f_sr,
                           (select relrowsecurity from pg_class where oid = 'public.zz_nueva'::regclass) as rls`);
check(d.t_anon === false && d.f_anon === false && d.t_sr === true && d.f_sr === true && d.rls === true, 'defaults: anon nada, service_role igual que hoy ' + JSON.stringify(d));
await db.exec(`set role sbowner; drop table public.zz_nueva; drop function public.zz_f(); reset role;`);

// ---------------------------------------------------------------- 7. costo: usa indices (con seqscan apagado para que el plan sea el de produccion)
await db.exec('set role sbowner; set enable_seqscan = off;');
const plan = (await db.query(`explain (analyze, costs off, timing off, summary off)
  select p.id, r.tipo from public.pacientes p left join public.contacto_roles r on r.contacto_id = p.id and r.hasta is null where p.telefono = $1`, [T.prov])).rows.map(x => x['QUERY PLAN']).join('\n');
check(/pacientes_telefono_key/.test(plan) && /contacto_roles_vigente_uk|contacto_roles_contacto_idx/.test(plan), 'plan con indices:\n' + plan);
await db.exec('set enable_seqscan = on;');
const t0 = performance.now(); for (let i = 0; i < 500; i++) await ruta(T.prov); const ms = (performance.now() - t0) / 500;
console.log(`contacto_ruta: ${ms.toFixed(3)} ms por llamada (PGlite/WASM, 500 llamadas)`);
await db.exec('reset role');

// ---------------------------------------------------------------- 7b. SQL de los nodos del v6 (Seg: Consultar Tipo / Tipo Salida)
await db.exec('set role sbowner');
check(/contacto_ruta\(\$1\)/.test(SQL_TIPO), 'SQL_TIPO leido del script: ' + SQL_TIPO.slice(0, 60));
for (const [tel, sil, red] of [[T.prov, true, true], [T.col, true, true], [T.nuevo, false, false], [T.dev, false, false], [T.fantasma, false, false], ['', false, false], [T.lid, false, false]]) {
  const rs = (await db.query(SQL_TIPO, [tel])).rows;
  check(rs.length === 1 && rs[0].seg_silencia === sil && rs[0].seg_con_red === red && typeof rs[0].seg_silencia === 'boolean',
        `SQL_TIPO(${JSON.stringify(tel)}) -> 1 fila booleana ${JSON.stringify(rs)}`);
}
{ const rs = (await db.query(SQL_TIPO, [T.prov])).rows; check(rs[0].seg_puesto_por === 'lucas' && /^\d{4}-\d{2}-\d{2}T/.test(rs[0].seg_desde || ''), 'SQL_TIPO trae desde y puesto_por para el aviso ' + JSON.stringify(rs[0])); }
{ const rs = (await db.query(SQL_TIPO, [T.nuevo])).rows; check(rs[0].seg_desde === null && rs[0].seg_puesto_por === null, 'SQL_TIPO sin tipo: desde/puesto_por null'); }
{ const rs = (await db.query(SQL_TIPO, [T.pac])).rows; check(rs.length === 1 && rs[0].seg_tipo === 'interno' && rs[0].seg_silencia === true && rs[0].seg_con_red === false, 'SQL_TIPO interno: silencia sin red'); }
await db.exec('reset role');

// ---------------------------------------------------------------- 8. vuelta atras de la estructura y re-aplicar
await db.exec('set role sbowner');
await db.exec(DOWN);
check((await q1(`select count(*)::int as n from pg_class where relname like 'contacto_roles%'`)).n === 0, 'down: sin tablas');
check((await q1(`select count(*)::int as n from pg_proc where proname like 'contacto_%'`)).n === 0, 'down: sin funciones');
check((await q1(`select count(*)::int as n from public.pacientes`)).n === 309, 'down: pacientes intacto');
await db.exec(UP);
check((await ruta(T.prov)).fuente === 'sin_tipo', 're-up limpio');
await db.exec('reset role');

console.log(`\n${ok} OK, ${fallas} fallas`);
process.exit(fallas ? 1 : 0);
