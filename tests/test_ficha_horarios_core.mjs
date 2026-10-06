// test_ficha_horarios_core.mjs — v7: fichas (familias) y horarios ofrecidos, offline. uso: node tests/test_ficha_horarios_core.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const F = require('../v7/ficha_core.js'); const H = require('../v7/horarios_core.js');
let fallas = 0, total = 0;
const t = (n, c, x) => { total++; if (!c) { fallas++; console.log(`  FALLA ${n}${x ? ' → ' + JSON.stringify(x).slice(0, 260) : ''}`); } else console.log(`  ok    ${n}`); };

console.log('FICHAS');
const resp1 = { data: [{ id: 651, nombre: 'Dana Yael', apellidos: 'Barro', rut: '49966117', habilitado: 1 }] };
const resp2 = { data: [{ id: 651, nombre: 'DANA YAEL', apellidos: 'barro', rut: '49.966.117', habilitado: 1 }, { id: 777, nombre: 'Martina', apellidos: 'Barro', rut: '51234567', habilitado: 1 }, { id: 888, nombre: 'Inactivo', apellidos: 'X', rut: '1', habilitado: 0 }] };
t('F1 una ficha: queda elegida', F.estadoInicial(F.fichasDeRespuesta(resp1)).elegida === 651);
const f2 = F.fichasDeRespuesta(resp2);
t('F2 dos fichas habilitadas (la inhabilitada no entra), nombres normalizados', f2.length === 2 && f2[0].nombre === 'Dana Yael' && f2[0].rut === '49966117', f2);
t('F3 dos fichas: ninguna elegida todavía', F.estadoInicial(f2).elegida === null);
t('F4 elegir por nombre ("es para Martina")', F.elegir(F.estadoInicial(f2), { nombre: 'Martina' }).estado.elegida === 777);
t('F5 elegir por nombre sin tildes/mayúsculas ("dána")', F.elegir(F.estadoInicial(f2), { nombre: 'dána' }).estado.elegida === 651);
t('F6 elegir por DNI con puntos', F.elegir(F.estadoInicial(f2), { dni: '51.234.567' }).estado.elegida === 777);
t('F7 DNI que no coincide → no elige', F.elegir(F.estadoInicial(f2), { dni: '99999999' }).motivo === 'dni_no_coincide');
t('F8 nombre que no existe → no elige', F.elegir(F.estadoInicial(f2), { nombre: 'Lucía' }).motivo === 'nombre_no_coincide');
t('F9 apellido común a las dos ("Barro") → ambiguo, pide DNI', F.elegir(F.estadoInicial(f2), { nombre: 'Barro' }).motivo === 'ambiguo');
t('F10 sin dato → pide nombre o DNI', F.elegir(F.estadoInicial(f2), { nombre: '' }).motivo === 'sin_dato');
t('F11 un DNI corto no se toma como DNI (cae a nombre)', F.elegir(F.estadoInicial(f2), { dni: '12', nombre: 'Martina' }).estado.elegida === 777);

console.log('\nTURNOS VISTOS');
const citas651 = { data: [{ id: 9104, id_paciente: 651, fecha: '2026-10-16', hora_inicio: '09:10:00', id_estado: 15, estado_anulacion: 0 }, { id: 8983, id_paciente: 651, fecha: '2026-09-24', hora_inicio: '09:20:00', id_estado: 2 }, { id: 9001, id_paciente: 651, fecha: '2026-10-30', hora_inicio: '10:00:00', id_estado: 1, estado_anulacion: 1 }] };
const citas777 = { data: [{ id: 9300, id_paciente: 777, fecha: '2026-10-20', hora_inicio: '16:20:00', id_estado: 15, estado_anulacion: 0 }, { id: 9104, id_paciente: 651, fecha: '2026-10-16', hora_inicio: '09:10:00', id_estado: 15 }] };
const tv = F.turnosVistos(f2, [citas651, citas777], '2026-10-05');
t('T1 solo futuros y vigentes, ordenados, sin duplicados entre fichas', tv.length === 2 && tv[0].id === 9104 && tv[1].id === 9300, tv);
t('T2 cada turno conserva SU paciente (no se cruza la familia)', tv[0].id_paciente === 651 && tv[1].id_paciente === 777, tv);
t('T3 el resumen para Asiri no lleva ids y nombra al paciente cuando hay varias fichas', F.resumenTurnos(f2, tv).join(' | ') === 'viernes 16/10 a las 09:10 (Dana Yael) | martes 20/10 a las 16:20 (Martina)', F.resumenTurnos(f2, tv));
t('T4 con una sola ficha no repite el nombre', F.resumenTurnos(F.fichasDeRespuesta(resp1), F.turnosVistos(F.fichasDeRespuesta(resp1), [citas651], '2026-10-05')).join('') === 'viernes 16/10 a las 09:10');
t('T5 respuesta con error de la agenda → no inventa turnos', F.turnosVistos(f2, [{ error: { message: 'x' } }, undefined], '2026-10-05').length === 0);

console.log('\nHORARIOS OFRECIDOS');
const BLOQUE = 'Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n* Viernes 23 de octubre 9:10\n\nPor la tarde:\n* Lunes 2 de noviembre 16:20\n* Miércoles 4 de noviembre 15:00 , 15:40\n\nLe sirve alguno?';
const of = H.parseBloque(BLOQUE, '2026-10-05');
t('H1 el bloque real de Dana da 6 horarios con fecha ISO', of.length === 6 && of[0].fecha === '2026-10-22' && of[0].hora === '08:00' && of[1].hora === '09:20' && of[5].fecha === '2026-11-04' && of[5].hora === '15:40', of);
t('H2 cambio de año: "5 de enero" visto en diciembre es el año que viene', H.parseBloque('* Martes 5 de enero 9:10', '2026-12-20')[0].fecha === '2027-01-05');
t('H3 horas de un dígito se normalizan (8:00 → 08:00)', of[0].hora === '08:00');
t('H4 unir sin duplicados y descarta pasado', H.unir([{ fecha: '2026-10-22', hora: '09:20' }, { fecha: '2026-09-01', hora: '10:00' }], of, '2026-10-05').length === 6);
t('H5 texto sin horarios → lista vacía', H.parseBloque('Disculpe, no tengo turnos', '2026-10-05').length === 0);
t('H6 límite de 2 bloques por código (regla de la Dra. 07/09)', !H.limiteLotes(2) && H.limiteLotes(3));

console.log(`\n${total - fallas}/${total} ${fallas ? 'FALLAS: ' + fallas : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
