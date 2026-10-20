// test_migracion_dentalink_espejo.mjs — 2026-10-20 · prueba LOCAL (PGlite = Postgres 16.4 en WASM, en memoria) del esquema del espejo de
// Dentalink (sql/2026-10-20_dentalink_espejo.sql) y de la carga que genera scripts/migrar_dentalink.py (--fixture … --dump-sql), contra una
// réplica de los roles del Supabase v3. No toca ninguna base real ni la API de Dentalink. Datos 100% ficticios (abonados 388 000-xxxx,
// que no existen en la numeración argentina).
// Prueba: el SQL corre limpio dos veces; RLS y permisos (anon/authenticated nada, service_role sin DELETE); la carga es idempotente
// (2.ª corrida = 0 cambios, 0 eventos); cambios de estado y citas desaparecidas quedan en cita_eventos; la guarda de extracción
// incompleta aborta sin tocar nada; las fases a/b no copian datos que no corresponden; solapes recalculados en la base.
// Requiere @electric-sql/pglite (devDependency: `npm install`) y python en el PATH.   Uso: node tests/test_migracion_dentalink_espejo.mjs
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { pathToFileURL, fileURLToPath } from 'node:url';
import os from 'node:os';
import path from 'node:path';
const { PGlite } = await import(process.env.PGLITE_PATH ? pathToFileURL(path.join(process.env.PGLITE_PATH, 'dist', 'index.js')).href : '@electric-sql/pglite');
const RAIZ = fileURLToPath(new URL('../', import.meta.url));
const UP = readFileSync(path.join(RAIZ, 'sql', '2026-10-20_dentalink_espejo.sql'), 'utf8').replaceAll('for role postgres', 'for role sbowner');
const TMP = mkdtempSync(path.join(os.tmpdir(), 'espejo-test-'));
let fallas = 0, ok = 0;
const check = (cond, msg) => { if (cond) { ok++; } else { fallas++; console.log('FALLA:', msg); } };
const err = async (db, sql, p) => { try { await db.query(sql, p); return null; } catch (e) { return e.code || e.message; } };
const q1 = async (db, sql, p) => (await db.query(sql, p)).rows[0];
const n = async (db, sql, p) => Number((await q1(db, sql, p)).n);

async function replica() {
  const db = new PGlite();
  await db.exec(`
    create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
    create role authenticator noinherit login; grant anon, authenticated, service_role to authenticator;
    create role sbowner login createrole bypassrls;          -- hace de "postgres" de Supabase: NO superuser
    grant anon, authenticated, service_role to sbowner;
    do $$ begin execute format('grant create on database %I to sbowner', current_database()); end $$;
    grant all on schema public to sbowner;
    grant usage on schema public to anon, authenticated, service_role;`);
  // peor caso: defaults GLOBALES abiertos (sin "in schema"), para probar que los revoke explícitos del SQL alcanzan
  await db.exec(`set role sbowner;
    alter default privileges for role sbowner grant all on tables to anon, authenticated, service_role;
    alter default privileges for role sbowner grant all on sequences to anon, authenticated, service_role;
    reset role;`);
  return db;
}

// ------------------------------------------------------------------------------------------------ fixture sintético (forma cruda de la API)
const P = (o) => ({ nombre: '', apellidos: '', rut: '', celular: '', telefono: '', email: '', direccion: '', fecha_nacimiento: '', fecha_afiliacion: '2026-01-10',
  habilitado: 1, tipo_documento: 0, es_pasaporte: 0, observaciones: '', ciudad: '', comuna: '', sexo: '', id_genero: 0, numero_ficha: '', nombre_social: '',
  fecha_deshabilitacion: '', id_usuario_deshabilitacion: '', es_carga: 0, tiene_cargas: 0, ...o });
const CITA = (o) => ({ id_sucursal: 1, id_dentista: 1, id_sillon: 1, duracion: 40, id_tratamiento: 0, tratamiento_sin_asignar: 1, estado_confirmacion: 0,
  estado_anulacion: 0, motivo_atencion: 'Consulta Ortodoncia', comentarios: '', fecha_actualizacion: '2026-10-19 10:00:00', ...o });
function fixture() {
  return {
    sucursales: [{ id: 1, nombre: 'Sucursal ficticia', direccion: 'Calle Falsa 123', telefono: '', ciudad: '', comuna: '', habilitada: 1 }],
    especialidades: [{ id: 14, nombre: 'Ortodoncia', id_tipo_sucursal: 1, habilitada: 1 }],
    dentistas: [{ id: 1, nombre: 'Prof', apellidos: 'Ficticia', id_especialidad: 14, id_sucursal: 1, intervalo: 10, habilitado: 1, agenda_online: 0, id_usuario: 12,
                  rut: '20000001', email: 'prof@ejemplo.com', celular: '', telefono: '', direccion: '', ciudad: '', comuna: '' },
                { id: 2, nombre: 'Otro', apellidos: 'Prof', id_especialidad: 99, id_sucursal: 1, intervalo: 15, habilitado: 0 }],
    sillones: [{ id: 1, nombre: 'Sillón 1' }, { id: 7, nombre: 'Sillón 7' }],
    estados_cita: [{ id: 1, nombre: 'Anulado', anulacion: 1, reservado: 1, uso_interno: 0, habilitado: 1, color: '#f00' },
                   { id: 2, nombre: 'Atendido', anulacion: 0, reservado: 1, uso_interno: 0, habilitado: 1 },
                   { id: 7, nombre: 'No confirmado', anulacion: 0, reservado: 1, uso_interno: 0, habilitado: 1 },
                   { id: 15, nombre: 'Notificado por WhatsApp', anulacion: 0, reservado: 1, uso_interno: 1, habilitado: 1 },
                   { id: 18, nombre: 'Confirmado por whatsapp ', anulacion: 0, reservado: 0, uso_interno: 0, habilitado: 1 }],
    horarios: [{ id_dentista: 1, id_sucursal: 1, intervalo: 10, dias: [
      { dia: 1, hora_inicio: '15:00:00', hora_fin: '19:20:00', hora_inicio_break: '15:00:00', hora_fin_break: '15:00:00', sillones: 1, id_box: 1 },
      { dia: 2, hora_inicio: '08:00:00', hora_fin: '11:40:00', hora_inicio_break: '15:00:00', hora_fin_break: '15:00:00', sillones: 1, id_box: 1 },
      { dia: 6, hora_inicio: '15:00:00', hora_fin: '15:00:00', hora_inicio_break: '15:00:00', hora_fin_break: '15:00:00', sillones: 1, id_box: 1 }] }],
    aranceles: [{ id: 0, nombre: 'Base', habilitado: 1 }, { id: 1, nombre: 'Otro', habilitado: 1 }],
    categorias: [{ id: 3, nombre: 'Ortodoncia', tipo: 'Clínica', id_tipo: 1, habilitado: 1 }],
    prestaciones: [{ id: 5001, codigo: '', nombre: 'Consulta', precio: 1000, id_arancel: 0, id_categoria: 3, tipo: 'Clínica', id_tipo: 1, habilitado: 1 },
                   { id: 5002, codigo: '', nombre: 'Control', precio: 500, id_arancel: 1, id_categoria: 77, tipo: 'Clínica', id_tipo: 1, habilitado: 1 }],
    bancos: [{ id: 1, nombre: 'Banco ficticio', habilitado: 1 }],
    laboratorios: [{ id: 3, nombre: 'Lab ficticio', direccion: '', telefono: '', detalle: '', habilitado: 1 }],
    laboratorios_extra: [],
    laboratorio_prestaciones: [{ id: 900, _padre_id: 3, nombre: 'Placa', precio: 1, costo: 1 }, { id: 900, _padre_id: 4, nombre: 'Placa', precio: 1, costo: 1 }],
    convenios: [],
    usuarios: [{ id: 12, usuario: 'prof', nombre: 'Prof Ficticia', id_dentista: 1, id_sucursal: 1, habilitado: 1, rut: '', email: '', celular: '', telefono: '' },
               { id: 23, usuario: 'secre', nombre: 'Secretaria Ficticia', id_dentista: '', id_sucursal: 1, habilitado: 1 }],
    cajas: [{ id: 305, id_sucursal: 1, id_usuario: 23, estado: 1, fecha_apertura: '2026-10-19 08:00:00', fecha_cierre: '', abono_inicial: 0, acumulado: 0,
              gastos: 0, saldo_anterior: 0, saldo_inicial: 0, saldo_cierre: 0, saldo_total: 0 }],
    contratos: [{ id: 1, _padre_id: 1, porcentaje: 0 }], liquidaciones: [{ id: 1, _padre_id: 1, monto: 0 }], devoluciones: [],
    pacientes: [
      P({ id: 1, nombre: 'Ana', apellidos: 'Ficticia', rut: '30000001', celular: '+5493880000201', email: 'a@ejemplo.com', direccion: 'Calle 1', fecha_nacimiento: '2015-05-05',
          observaciones: 'texto clínico ficticio' }),
      P({ id: 2, nombre: 'Ana', apellidos: 'Ficticia', celular: '5493880000201' }),                       // dup del v6 (sin DNI)
      P({ id: 3, nombre: 'Beto', apellidos: 'Inventado', rut: '30000003', celular: '+5493880000201', email: 'b@ejemplo.com', direccion: 'x', fecha_nacimiento: '1980-01-02' }),
      P({ id: 4, nombre: 'Carla', apellidos: 'Imaginaria', rut: '30000004', celular: '0388 15 000-0204', email: 'c@ejemplo.com', direccion: 'x', fecha_nacimiento: '1900-01-01' }),
      P({ id: 5, nombre: 'Lid', apellidos: 'Oculto', celular: '123456789012345@lid' }),
    ],
    tratamientos: [{ id: 638, id_paciente: 1, id_dentista: 1, id_sucursal: 1, id_convenio: 0, nombre: 'Ortodoncia', fecha: '2026-01-10', total: 100, total_realizado: 0,
                     abonado: 0, deuda: 100, abono_libre: 0, asignado_realizado: 0, asignado_sin_realizar: 0, finalizado: 0, bloqueado: 0, comentario: '' }],
    tratamiento_detalles: [{ id: 7001, _padre_id: 638, id_tratamiento: 638, id_prestacion: 5001, nombre_prestacion: 'Consulta', tipo_prestacion: 'Clínica', precio: 100,
                             descuento_convenio: 0, descuento_usuario: 0, descuento_total: 0, total: 100, pagado: 0, realizado: 0, futura_realizacion: 0, liquidado: 0,
                             fecha_creacion: '2026-01-10 09:00:00', fecha_realizacion: '', id_dentista_realizador: 0, id_usuario_creador: 23, pieza: [] }],
    pagos: [{ id: 4211, id_paciente: 1, id_caja: 305, id_sucursal: 1, id_banco: 0, id_medio_pago: 1, medio_pago: 'Transferencia', monto_pago: 100, folio: '',
              numero_referencia: '', fecha_creacion: '2026-10-19 09:00:00', fecha_recepcion: '2026-10-19', fecha_vencimiento: '2026-10-19', tipo_pagador: 'Paciente',
              id_pagador: 1, nombre_pagador: 'Ana Ficticia', rut_emisor: '' }],
    evoluciones: [{ id: 5313, id_paciente: 1, id_tratamiento: 638, id_dentista: 1, id_sucursal: 1, id_usuario: 12, fecha: '2026-10-19',
                    fecha_registro: '2026-10-19 10:00:00', habilitado: 1, datos: 'evolución ficticia' },
                  { id: 5313, id_paciente: 1, id_tratamiento: 638, id_dentista: 1, id_sucursal: 1, id_usuario: 12, fecha: '2026-10-19',
                    fecha_registro: '2026-10-19 10:00:00', habilitado: 1, datos: 'evolución ficticia' }],   // la paginación repite filas
    recetas: [],
    citas: [
      CITA({ id: 101, id_paciente: 1, id_estado: 7, fecha: '2026-10-26', hora_inicio: '15:00:00', hora_fin: '15:40:00', comentarios: 'Reservado por Asiri (WhatsApp)' }),
      CITA({ id: 102, id_paciente: 3, id_estado: 15, fecha: '2026-10-26', hora_inicio: '15:20:00', hora_fin: '16:00:00' }),   // se pisa con 101
      CITA({ id: 103, id_paciente: 4, id_estado: 1, fecha: '2026-10-26', hora_inicio: '15:20:00', hora_fin: '16:00:00' }),    // anulada
      CITA({ id: 104, id_paciente: 999, id_estado: 99, fecha: '2026-10-24', hora_inicio: '10:05:00', hora_fin: '10:40:00', id_tratamiento: 55, tratamiento_sin_asignar: 0 }),
      CITA({ id: 105, id_paciente: 1, id_estado: 18, fecha: '2026-10-27', hora_inicio: '08:00:00', hora_fin: '08:40:00', id_tratamiento: 638, tratamiento_sin_asignar: 0,
             comentarios: 'Agendado desde el panel' }),
      ...Array.from({ length: 15 }, (_, i) => CITA({ id: 200 + i, id_paciente: 3, id_estado: 2, fecha: '2026-09-07', hora_inicio: `${String(15 + Math.floor(i / 6)).padStart(2, '0')}:${String((i % 6) * 10).padStart(2, '0')}:00`,
                                                     hora_fin: `${String(15 + Math.floor(i / 6)).padStart(2, '0')}:${String((i % 6) * 10 + 9).padStart(2, '0')}:00`, duracion: 9 })),
    ],
  };
}
let corridaN = 0;
function sqlDe(fx, fase = 'clinica') {
  const f = path.join(TMP, `fx${++corridaN}.json`), out = path.join(TMP, `carga${corridaN}.sql`);
  writeFileSync(f, JSON.stringify(fx));
  execFileSync('python', [path.join(RAIZ, 'scripts', 'migrar_dentalink.py'), '--fixture', f, '--dump-sql', out, '--fase', fase, '--hoy', '2026-10-20',
    '--corrida-id', `00000000-0000-4000-8000-${String(corridaN).padStart(12, '0')}`, '--cache-dir', path.join(TMP, 'cache')], { stdio: ['ignore', 'ignore', 'inherit'] });
  return readFileSync(out, 'utf8');
}

// ================================================================================================ 1. esquema: corre dos veces, RLS, permisos
const db = await replica();
await db.exec('set role sbowner');
await db.exec(UP);
await db.exec(UP);
check(true, 'up x2');
const tablas = (await db.query(`select c.relname, c.relrowsecurity from pg_class c join pg_namespace s on s.oid = c.relnamespace where s.nspname = 'agenda' and c.relkind = 'r'`)).rows;
check(tablas.length >= 25, `tablas en agenda: ${tablas.length}`);
check(tablas.every((t) => t.relrowsecurity), 'RLS en todas: ' + tablas.filter((t) => !t.relrowsecurity).map((t) => t.relname).join(','));
check((await n(db, `select count(*) as n from pg_policies where schemaname = 'agenda'`)) === 0, 'sin policies');
check((await q1(db, `select valor from agenda.config where clave = 'backend'`)).valor === 'dentalink', 'backend = dentalink por defecto');
check((await n(db, `select count(*) as n from agenda.esquema_version where version = '2026-10-20'`)) === 1, 'versión registrada una vez');
await db.exec('reset role');
for (const rol of ['anon', 'authenticated']) {
  await db.exec(`set role ${rol}`);
  for (const t of ['citas', 'fichas', 'fichas_por_celular', 'sync_corridas', 'config']) check(await err(db, `select * from agenda.${t} limit 1`) === '42501', `${rol}: no lee agenda.${t}`);
  check(await err(db, `select agenda.recalcular_solapes()`) === '42501', `${rol}: no ejecuta funciones`);
  check(await err(db, `insert into agenda.config (clave, valor) values ('x','y')`) === '42501', `${rol}: no escribe`);
  await db.exec('reset role');
}
check(!(await q1(db, `select has_schema_privilege('anon', 'agenda', 'usage') as u`)).u, 'anon sin USAGE en el esquema');

// ================================================================================================ 2. primera carga completa (fases a-d)
const fx1 = fixture();
await db.exec('set role sbowner');
await db.exec(sqlDe(fx1));
const cuenta = async (t) => n(db, `select count(*) as n from agenda.${t}`);
check(await cuenta('citas') === 20 && await cuenta('fichas') === 5 && await cuenta('horarios') === 3 && await cuenta('estados_cita') === 5, 'conteos tras la carga');
check(await cuenta('dentalink_otros') === 3, 'otros: contratos, liquidaciones y prestación de laboratorio (la repetida en 2 labs, una sola vez)');
check(await cuenta('evoluciones') === 1, 'evolución repetida por la paginación: una sola fila');
check(JSON.stringify((await q1(db, `select datos->'_padres' as p from agenda.dentalink_otros where entidad = 'laboratorio_prestaciones'`)).p) === '[3,4]', 'prestación compartida: anota los 2 laboratorios');
check((await q1(db, `select count(*) filter (where id = dentalink_id) as a, count(*) as b from agenda.citas`)).a == 20, 'id = dentalink_id');
const f2 = await q1(db, `select duplicado_de, duplicado_regla, origen_probable, celular_normalizado from agenda.fichas where id = 2`);
check(f2.duplicado_de == 1 && f2.duplicado_regla === 'mismo_nombre_y_celular' && f2.origen_probable === 'bot_v6' && f2.celular_normalizado === '5493880000201', 'ficha 2 dup del v6 ' + JSON.stringify(f2));
const f4 = await q1(db, `select celular_normalizado, celular_estado, fecha_nacimiento, calidad from agenda.fichas where id = 4`);
check(f4.celular_normalizado === '5493880000204' && f4.celular_estado === 'normalizado' && f4.fecha_nacimiento === null && f4.calidad.includes('nacimiento_relleno'), 'ficha 4 ' + JSON.stringify(f4));
check((await q1(db, `select celular_estado from agenda.fichas where id = 5`)).celular_estado === 'lid', '@lid');
const s = (await db.query(`select id, solape_importado from agenda.citas where id in (101, 102, 103, 105) order by id`)).rows.map((r) => r.solape_importado);
check(JSON.stringify(s) === '[true,true,false,false]', 'solapes recalculados en la base ' + JSON.stringify(s));
const c104 = await q1(db, `select estado_id, ficha_id, paciente_dentalink_id, tratamiento_id, tratamiento_dentalink_id, fuera_de_horario, calidad from agenda.citas where id = 104`);
check(c104.estado_id === null && c104.ficha_id === null && Number(c104.paciente_dentalink_id) === 999 && c104.tratamiento_id === null && Number(c104.tratamiento_dentalink_id) === 55
      && c104.fuera_de_horario === true, 'cita 104 huérfana conservada con sus ids originales ' + JSON.stringify(c104));
check(Number((await q1(db, `select tratamiento_id from agenda.citas where id = 105`)).tratamiento_id) === 638, 'cita→plan (fase c)');
check((await q1(db, `select comentarios from agenda.citas where id = 101`)).comentarios === 'Reservado por Asiri (WhatsApp)', 'comentarios con fase d (fixture)');
const vista = (await db.query(`select celular_normalizado, fichas, ficha_ids from agenda.fichas_por_celular order by 1`)).rows;
check(vista.length === 2 && vista[0].fichas === 2 && JSON.stringify(vista[0].ficha_ids.map(Number)) === '[1,3]', 'vista por celular sin el duplicado ' + JSON.stringify(vista));
check((await q1(db, `select estado from agenda.sync_corridas where id = '00000000-0000-4000-8000-000000000001'`)).estado === 'ok', 'corrida ok');
check((await cuenta('cita_eventos')) === 0, 'la carga inicial no genera eventos');

// ================================================================================================ 3. idempotencia: misma data, otra corrida
const antes = await q1(db, `select max(espejo_actualizado_at) as m, count(*) as n from agenda.citas`);
await db.exec(sqlDe(fixture()));
const despues = await q1(db, `select max(espejo_actualizado_at) as m, count(*) as n from agenda.citas`);
check(Number(despues.n) === 20 && String(despues.m) === String(antes.m), 'segunda corrida igual: 0 filas tocadas');
check((await cuenta('cita_eventos')) === 0 && (await cuenta('fichas')) === 5, 'sin eventos ni filas nuevas');
check((await cuenta('sync_corridas')) === 2, '2 corridas registradas');

// ================================================================================================ 4. cambios: estado, cita borrada en Dentalink, cita nueva
const fx3 = fixture();
fx3.citas.find((c) => c.id === 101).id_estado = 18;
fx3.citas = fx3.citas.filter((c) => c.id !== 102);
fx3.citas.push(CITA({ id: 106, id_paciente: 4, id_estado: 7, fecha: '2026-10-28', hora_inicio: '15:00:00', hora_fin: '15:40:00' }));
await db.exec(sqlDe(fx3));
check(Number((await q1(db, `select estado_id from agenda.citas where id = 101`)).estado_id) === 18, 'estado actualizado');
check((await q1(db, `select desaparecida_at is not null as d from agenda.citas where id = 102`)).d === true, 'cita borrada en Dentalink: marcada, no borrada');
check(await cuenta('citas') === 21, 'la nueva entró y la borrada sigue en la tabla');
const ev = (await db.query(`select cita_id, campo, corrida_id from agenda.cita_eventos order by id`)).rows;
check(ev.length === 2 && ev.some((e) => e.cita_id == 101 && e.campo === 'estado') && ev.some((e) => e.cita_id == 102 && e.campo === 'desaparecida')
      && ev.every((e) => e.corrida_id === '00000000-0000-4000-8000-000000000003'), 'eventos ' + JSON.stringify(ev));
check((await q1(db, `select solape_importado from agenda.citas where id = 101`)).solape_importado === false, 'sin la 102, la 101 ya no se pisa');
// vuelve a aparecer
await db.exec(sqlDe(fixture()));
check((await q1(db, `select desaparecida_at is null as d from agenda.citas where id = 102`)).d === true, 'reaparece');
check((await n(db, `select count(*) as n from agenda.cita_eventos where campo = 'reaparecida'`)) === 1, 'evento reaparecida');

// ================================================================================================ 5. guarda: Dentalink devuelve <90% → aborta sin tocar nada
const fx5 = fixture();
fx5.citas = fx5.citas.slice(0, 5);
const e5 = await err(db, sqlDe(fx5));
await db.exec('rollback');
check(e5 !== null, 'extracción incompleta aborta');
check((await n(db, `select count(*) as n from agenda.citas where desaparecida_at is null`)) === 20, 'nada marcado como desaparecido (siguen las 20 activas; la 106 ya estaba desaparecida)');
check((await n(db, `select count(*) as n from agenda.sync_corridas`)) === 4, 'la corrida abortada no quedó registrada (la registra el script aparte)');

// ================================================================================================ 6. permisos de service_role sobre los datos
await db.exec('reset role; set role service_role');
check(await err(db, `select count(*) from agenda.citas`) === null, 'service_role lee');
check(await err(db, `update agenda.citas set estado_id = 2 where id = 106`) === null, 'service_role actualiza (y el trigger registra el evento)');
check(await err(db, `delete from agenda.citas where id = 106`) === '42501', 'service_role NO borra');
check(await err(db, `truncate agenda.citas`) === '42501', 'service_role NO vacía');
await db.exec('reset role');
check((await n(db, `select count(*) as n from agenda.cita_eventos where cita_id = 106 and campo = 'estado'`)) === 1, 'evento del update de service_role');

// ================================================================================================ 7. fases: a sola no copia pacientes; b agrega la ficha mínima
const db2 = await replica();
await db2.exec('set role sbowner');
await db2.exec(UP);
await db2.exec(sqlDe(fixture(), 'ocupacion'));
check((await n(db2, `select count(*) as n from agenda.fichas`)) === 0, 'fase a: 0 fichas');
check((await n(db2, `select count(*) as n from agenda.citas where ficha_id is not null or paciente_dentalink_id is not null or comentarios is not null or tratamiento_id is not null`)) === 0,
      'fase a: citas sin paciente, plan ni comentarios');
check((await n(db2, `select count(*) as n from agenda.citas`)) === 20 && (await n(db2, `select count(*) as n from agenda.profesionales where rut is not null or email is not null`)) === 0,
      'fase a: ocupación completa, profesionales sin datos de contacto');
check((await n(db2, `select count(*) as n from agenda.tratamientos`)) === 0 && (await n(db2, `select count(*) as n from agenda.pagos`)) === 0
      && (await n(db2, `select count(*) as n from agenda.evoluciones`)) === 0, 'fase a: sin planes, pagos ni evoluciones');
await db2.exec(sqlDe(fixture(), 'ficha_minima'));
check((await n(db2, `select count(*) as n from agenda.fichas where nombre is null and documento is null and observaciones is null and celular_normalizado is not null`)) === 4,
      'fase b: ficha mínima (celular normalizado), sin nombre, documento ni observaciones');
check((await n(db2, `select count(*) as n from agenda.citas where ficha_id is not null`)) === 19 && (await n(db2, `select count(*) as n from agenda.citas where comentarios is not null`)) === 0,
      'fase b: citas vinculadas a la ficha, sin comentarios');
check((await n(db2, `select count(*) as n from agenda.cita_eventos`)) === 0, 'pasar de fase a a fase b no genera eventos');

// ================================================================================================ 8. costo: lecturas por índice
await db.exec('set role sbowner; set enable_seqscan = off;');
const plan = (await db.query(`explain (costs off) select * from agenda.fichas where celular_normalizado = '5493880000201' and desaparecida_at is null`)).rows.map((x) => x['QUERY PLAN']).join(' ');
check(/fichas_celular_idx/.test(plan), 'fichas por celular usa índice: ' + plan);
const plan2 = (await db.query(`explain (costs off) select * from agenda.citas where fecha between '2026-10-01' and '2026-10-31' and desaparecida_at is null`)).rows.map((x) => x['QUERY PLAN']).join(' ');
check(/citas_fecha_idx/.test(plan2), 'citas por rango de fechas usa índice: ' + plan2);

rmSync(TMP, { recursive: true, force: true });
console.log(`\n${ok} OK, ${fallas} FALLAS`);
process.exit(fallas ? 1 : 0);
