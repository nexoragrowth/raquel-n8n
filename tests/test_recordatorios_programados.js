// tests/test_recordatorios_programados.js — recordatorios/programados.js (lógica del workflow "Recordatorios programados"). Datos inventados.
// Correr: node tests/test_recordatorios_programados.js
const P = require('../recordatorios/programados.js');
let ok = 0, mal = 0;
const t = (n, c, e) => { if (c) ok++; else { mal++; console.log('  ✗', n, e !== undefined ? JSON.stringify(e).slice(0, 300) : ''); } };
const cita = (x) => ({ id: 1, estado_anulacion: 0, id_estado: 15, ...x });

const e1 = P.esperado({ data: [cita({}), cita({ id_estado: 18 }), cita({ id_estado: 14 }), cita({ estado_anulacion: 1 }), cita({ id_estado: 3 })], links: { current: 'x' } });
t('esperado: mismo filtro que el workflow (fuera 18, 14 y anuladas; los otros confirmados cuentan)', e1.ok && e1.esperado === 2, e1);
t('esperado: Dentalink sin datos → no se puede contar', P.esperado({}).ok === false && P.esperado(null).ok === false);
t('esperado: más de una página → no se confía', P.esperado({ data: [cita({})], links: { next: 'n' } }).ok === false);
t('esperado: links como lista vacía (sin citas) está bien', P.esperado({ data: [], links: [] }).ok === true && P.esperado({ data: [], links: [] }).esperado === 0);

t('decidir: dispara con 0 enviados y algo para mandar', P.decidir(0, { ok: true, esperado: 6 }).disparar === true);
t('decidir: NO dispara si ya hay avisos de esa fecha', P.decidir(3, { ok: true, esperado: 6 }).disparar === false);
t('decidir: NO dispara sin turnos', P.decidir(0, { ok: true, esperado: 0 }).disparar === false);
t('decidir: NO dispara si no se pudo contar', P.decidir(0, { ok: false, motivo: 'x' }).disparar === false);

t('diaDeCorrida: miércoles 25/11 → lunes 23 (sin cerrados)', P.diaDeCorrida('2026-11-25', []) === '2026-11-23');
t('diaDeCorrida: martes 24/11 → viernes 20', P.diaDeCorrida('2026-11-24', []) === '2026-11-20');
t('diaDeCorrida: con el lunes 23 cerrado, el martes 24 → jueves 19', P.diaDeCorrida('2026-11-24', ['2026-11-23']) === '2026-11-19');
t('diaDeCorrida: un sábado o un día cerrado no tiene corrida', P.diaDeCorrida('2026-11-21', []) === null && P.diaDeCorrida('2026-11-23', ['2026-11-23']) === null);

const base = { est: { ok: true, esperado: 8 }, fechaTurno: '2026-11-25', cerrados: [], hoy: '2026-11-20', hora: 8, horaEnvio: 8, noRepetir: true };
const c1 = P.cerrar({ ...base, ya: 0, enviados: 8, disparado: true });
t('cerrar: salieron todos → enviado y suspende la corrida del lunes 23', c1.estado === 'enviado' && c1.suspender === '2026-11-23', c1);
const c2 = P.cerrar({ ...base, ya: 0, enviados: 7, disparado: true });
t('cerrar: faltó uno → error y NO suspende (mejor duplicar que dejar sin aviso)', c2.estado === 'error' && c2.suspender === null, c2);
const c3 = P.cerrar({ ...base, ya: 0, enviados: 8, disparado: true, noRepetir: false });
t('cerrar: sin "no repetir" no suspende', c3.estado === 'enviado' && c3.suspender === null);
const c4 = P.cerrar({ ...base, ya: 0, enviados: 8, disparado: true, hoy: '2026-11-23', hora: 9 });
t('cerrar: si la corrida automática ya pasó, no hay nada que suspender', c4.suspender === null && c4.estado === 'enviado', c4);
const c5 = P.cerrar({ ...base, ya: 0, enviados: 8, disparado: true, hoy: '2026-11-23', hora: 7 });
t('cerrar: corrida de hoy que todavía no corrió → se suspende', c5.suspender === '2026-11-23', c5);
const c6 = P.cerrar({ ...base, ya: 5, enviados: 5, disparado: false });
t('cerrar: ya estaba mandado por otra vía → enviado (no se repite)', c6.estado === 'enviado' && c6.resultado.disparado === false);
const c7 = P.cerrar({ ...base, est: { ok: true, esperado: 0 }, ya: 0, enviados: 0, disparado: false });
t('cerrar: no había turnos → enviado sin suspender', c7.estado === 'enviado' && c7.suspender === null);
const c8 = P.cerrar({ ...base, est: { ok: false, motivo: 'Dentalink no devolvió datos' }, ya: 0, enviados: 0, disparado: false });
t('cerrar: no se pudo contar → error, con el motivo', c8.estado === 'error' && /Dentalink/.test(c8.resultado.motivo), c8);
console.log(`\n${ok}/${ok + mal} ${mal ? 'CON FALLOS' : 'TODO OK'}`); process.exit(mal ? 1 : 0);
