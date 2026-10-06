// test_agenda_core.mjs — v7 puerta 0: las guardas de escritura de la agenda, offline y sin modelo. uso: node tests/test_agenda_core.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const Core = require('../v7/agenda_core.js');

const AHORA = '2026-10-05T12:36:00Z';
const T_VIEJO = { id: 9104, id_paciente: 651, fecha: '2026-10-16', hora_inicio: '09:10:00', id_estado: 15, estado_anulacion: 0 };
const OFERTAS = [{ fecha: '2026-10-22', hora: '08:00' }, { fecha: '2026-10-22', hora: '9:20' }, { fecha: '2026-10-23', hora: '09:10' }];
const estado = (o = {}) => ({ tel: '5490000000651', exec_id: 'ex-1', ficha: { fichas: [{ id: 651, nombre: 'Dana' }], elegida: null }, turnos_vistos: [T_VIEJO], ofertas: OFERTAS, ...o });
const CAMBIO = { tipo: 'cambio', fecha: '2026-10-22', hora: '9:20', fecha_turno_viejo: '2026-10-16' };

let fallas = 0, total = 0;
const t = (nombre, cond, extra) => { total++; if (!cond) { fallas++; console.log(`  FALLA ${nombre}${extra ? ' → ' + JSON.stringify(extra).slice(0, 300) : ''}`); } else console.log(`  ok    ${nombre}`); };

// -------- mock de E/S
const mkIO = (o = {}) => {
  const log = []; const usadas = new Set();
  return { log,
    consumir: async (id) => { log.push('consumir'); if (o.consumirFalla) throw new Error('redis'); if (usadas.has(id)) return false; usadas.add(id); return true; },
    getCita: async (id) => { log.push('GET'); if (o.getFalla) throw new Error('timeout'); return { data: { ...T_VIEJO, ...(o.citaCambia || {}) } }; },
    postCita: async (b) => { log.push('POST'); if (o.postFalla) throw new Error('400'); if (o.postSinEstado) return { data: { id: 1 } }; if (o.postError) return { error: { message: '400' } }; return { data: { id: 99001, id_estado: 7, ...b } }; },
    putCita: async (id, b) => { log.push('PUT ' + id); if (o.putFalla) throw new Error('500'); return o.putMal ? { error: { message: 'x' } } : { data: { id, id_estado: 1 } }; },
  };
};
const prop = (entrada = CAMBIO, est = estado()) => Core.proponer(entrada, est, AHORA);
const ejec = (p, io, extra = {}) => Core.ejecutar({ propuesta: p, exec_id_actual: 'ex-2', enviada: true, ...extra }, io, extra.ahora || AHORA);

console.log('PROPONER (validaciones por código)');
{ const r = prop(); t('P01 cambio feliz de la charla real de Dana', r.ok && /^Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra\. Raquel, reemplazando el turno del viernes 16\/10 a las 09:10\. ¿Procedo con la reserva\?$/.test(r.readback_text), r);
  t('P01b el read-back es idéntico al que el bot real mandó el 05/10', r.readback_text === 'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?', r.readback_text); }
t('P02 horario que nadie ofreció (10:00) → no_ofrecido', prop({ ...CAMBIO, hora: '10:00' }).motivo === 'no_ofrecido');
t('P03 año equivocado (2027) → no_ofrecido', prop({ ...CAMBIO, fecha: '2027-10-22' }).motivo === 'no_ofrecido');
t('P04 hora sin cero "9:20" vale (se normaliza)', prop().ok && prop().propuesta.slot.hora === '09:20');
t('P05 dos fichas sin elegir → ficha_no_elegida', prop(CAMBIO, estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: null } })).motivo === 'ficha_no_elegida');
{ const r = prop(CAMBIO, estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: 651 } })); t('P06 dos fichas con elegida: el read-back nombra al paciente', r.ok && / para Dana:/.test(r.readback_text), r.readback_text); }
t('P07 cita vieja de OTRA ficha del celular → turno_no_es_de_la_ficha', prop(CAMBIO, estado({ turnos_vistos: [{ ...T_VIEJO, id_paciente: 777 }], ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: 651 } })).motivo === 'turno_no_es_de_la_ficha');
t('P08 fecha de turno viejo inexistente → cita_no_vista', prop({ ...CAMBIO, fecha_turno_viejo: '2026-10-19' }).motivo === 'cita_no_vista');
t('P09 turno viejo en menos de 48 h → menos_48h', prop({ ...CAMBIO, fecha_turno_viejo: '2026-10-06' }, estado({ turnos_vistos: [{ ...T_VIEJO, fecha: '2026-10-06', hora_inicio: '09:10:00' }] })).motivo === 'menos_48h');
t('P10 varios turnos y no dice cuál → cual_turno', prop({ ...CAMBIO, fecha_turno_viejo: undefined }, estado({ turnos_vistos: [T_VIEJO, { ...T_VIEJO, id: 9200, fecha: '2026-11-04' }] })).motivo === 'cual_turno');
t('P11 sin haber llamado ver_turnos → ver_turnos_primero', prop(CAMBIO, estado({ turnos_vistos: undefined })).motivo === 'ver_turnos_primero');
t('P12 turno anulado no cuenta como vigente (el paciente no tiene a qué cambiar)', prop({ ...CAMBIO, fecha_turno_viejo: undefined }, estado({ turnos_vistos: [{ ...T_VIEJO, id_estado: 1 }] })).motivo === 'sin_turnos');
t('P13 reserva con turno vigente → tiene_turno_vigente', prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '09:20' }).motivo === 'tiene_turno_vigente');
{ const r = prop({ tipo: 'sumar', fecha: '2026-10-22', hora: '09:20' }); t('P14 sumar explícito: read-back "además de su turno"', r.ok && /además de su turno del viernes 16\/10/.test(r.readback_text), r); }
t('P15 reserva sin turnos vigentes: ok', prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '09:20' }, estado({ turnos_vistos: [] })).ok);
{ const r = prop({ tipo: 'cancelacion', fecha_turno_viejo: '2026-10-16' }); t('P16 cancelación ok con confirmación', r.ok && /¿Le confirmo que desea cancelar el turno del viernes 16\/10 a las 09:10\?/.test(r.readback_text), r.readback_text); }
t('P17 cancelación a menos de 48 h → menos_48h', prop({ tipo: 'cancelacion', fecha_turno_viejo: '2026-10-06' }, estado({ turnos_vistos: [{ ...T_VIEJO, fecha: '2026-10-06' }] })).motivo === 'menos_48h');
t('P18 sin ficha → sin_ficha', prop(CAMBIO, estado({ ficha: { fichas: [], elegida: null } })).motivo === 'sin_ficha');
t('P19 el modelo no puede elegir paciente: la propuesta usa SIEMPRE la ficha del estado', prop(CAMBIO, estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana' }], elegida: null } })).propuesta.paciente_id === 651 && prop({ ...CAMBIO, paciente_id: 777 }).propuesta.paciente_id === 651);

console.log('\nEJECUTAR (atómico, una vez, verificado)');
const P = prop().propuesta;
{ const io = mkIO(); const r = await ejec(P, io);
  t('E01 feliz: reserva y DESPUÉS anula, en ese orden', r.ok && io.log.join(',') === 'consumir,GET,POST,PUT 9104', io.log);
  const body = r.ledger.escrituras[0].body;
  t('E01b cuerpo exacto del POST (hora HH:MM, comentario con la cita reemplazada)', JSON.stringify(body) === JSON.stringify({ id_dentista: 1, id_sucursal: 1, id_sillon: 1, id_paciente: 651, fecha: '2026-10-22', hora_inicio: '09:20', duracion: 40, comentario: 'Reprogramado por Asiri (WhatsApp), reemplaza cita #9104' }), body);
  t('E01c el mensaje lo arma el código y dice lo que pasó', r.readback_text === 'Listo, quedó reprogramado su turno: anulé el del viernes 16/10 a las 09:10 y le reservé el jueves 22/10 a las 09:20.', r.readback_text); }
{ const r = await ejec(P, mkIO(), { exec_id_actual: P.exec_id }); t('E02 propuesta de la MISMA ejecución → readback_no_visto', r.motivo === 'readback_no_visto'); }
{ const io = mkIO(); const r = await ejec(P, io, { enviada: false }); t('E03 el read-back no salió por WhatsApp (enviada=false) → no escribe', r.motivo === 'readback_no_visto' && !io.log.some((x) => x === 'POST')); }
{ const io = mkIO(); const a = await ejec(P, io); const b = await ejec(P, io); t('E04 doble ejecución: una sola reserva', a.ok && b.motivo === 'ya_ejecutada' && io.log.filter((x) => x === 'POST').length === 1, io.log); }
{ const io = mkIO({ postError: true }); const r = await ejec(P, io); t('E05 la agenda rechaza la reserva: NO anula y dice que el turno sigue vigente', !r.ok && r.motivo === 'reserva_rechazada' && !io.log.some((x) => x.startsWith('PUT')) && /sigue vigente/.test(r.para_asiri), io.log); }
{ const io = mkIO({ postFalla: true }); const r = await ejec(P, io); t('E05b la agenda lanza excepción en el POST: igual no anula', r.motivo === 'reserva_rechazada' && !io.log.some((x) => x.startsWith('PUT'))); }
{ const io = mkIO({ postSinEstado: true }); const r = await ejec(P, io); t('E05c respuesta sin id_estado se trata como rechazo', r.motivo === 'reserva_rechazada'); }
{ const io = mkIO({ putMal: true }); const r = await ejec(P, io); t('E06 reserva ok pero no pudo anular → parcial y lo dice', !r.ok && r.parcial === true && r.motivo === 'no_pude_anular' && r.nueva_cita === 99001 && /no pude anular/.test(r.readback_text)); }
{ const io = mkIO({ citaCambia: { fecha: '2026-10-19' } }); const r = await ejec(P, io); t('E07 la cita vieja cambió de fecha desde la propuesta → aborta sin escribir', r.motivo === 'cita_cambio' && !io.log.includes('POST')); }
{ const io = mkIO({ citaCambia: { id_estado: 1 } }); const r = await ejec(P, io); t('E08 la cita vieja ya está anulada → aborta sin escribir', r.motivo === 'cita_cambio' && !io.log.includes('POST')); }
{ const io = mkIO({ citaCambia: { id_paciente: 777 } }); const r = await ejec(P, io); t('E08b la cita vieja ahora es de otro paciente → aborta', r.motivo === 'cita_cambio' && !io.log.includes('POST')); }
{ const r = await ejec(P, mkIO(), { ahora: '2026-10-05T13:30:00Z' }); t('E09 propuesta vencida (>30 min) → vencida', r.motivo === 'vencida'); }
{ const io = mkIO({ getFalla: true }); const r = await ejec(P, io); t('E10 la agenda no responde al verificar: no escribe nada', r.motivo === 'error_tecnico' && !io.log.includes('POST')); }
{ const io = mkIO({ consumirFalla: true }); const r = await ejec(P, io); t('E10b Redis caído al consumir: no escribe nada', r.motivo === 'error_tecnico' && !io.log.includes('POST')); }
{ const pc = prop({ tipo: 'cancelacion', fecha_turno_viejo: '2026-10-16' }).propuesta; const io = mkIO(); const r = await ejec(pc, io);
  t('E11 cancelación feliz: solo PUT', r.ok && io.log.join(',') === 'consumir,GET,PUT 9104' && /cancelado/.test(r.readback_text), io.log);
  const io2 = mkIO({ putMal: true }); const r2 = await ejec(prop({ tipo: 'cancelacion', fecha_turno_viejo: '2026-10-16' }).propuesta, io2);
  t('E11b cancelación que la agenda rechaza: no dice cancelado', !r2.ok && r2.motivo === 'no_pude_cancelar' && !/quedó cancelado/.test(r2.readback_text || '')); }
{ const pr = prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '09:20' }, estado({ turnos_vistos: [] })).propuesta; const io = mkIO(); const r = await ejec(pr, io);
  t('E12 reserva simple: solo POST, sin GET ni PUT', r.ok && io.log.join(',') === 'consumir,POST', io.log); }
{ const io = mkIO(); const r = await ejec(P, io, { modo: 'sombra' }); t('E13 modo sombra: cero llamadas y devuelve lo que habría hecho', r.ok && r.simulado === true && io.log.length === 0 && r.habria_hecho.slot.hora === '09:20', io.log); }
{ const r = await Core.ejecutar({ propuesta: null, exec_id_actual: 'ex-2', enviada: true }, mkIO(), AHORA); t('E14 sin propuesta → sin_propuesta', r.motivo === 'sin_propuesta'); }
{ const pf = prop(CAMBIO, estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: 777 }, turnos_vistos: [{ ...T_VIEJO, id_paciente: 777 }] })).propuesta; const io = mkIO({ citaCambia: { id_paciente: 777 } });
  const r = await ejec(pf, io); t('E15 familias: reserva para la ficha ELEGIDA (777), no la primera', r.ok && r.ledger.escrituras[0].body.id_paciente === 777, r.ledger); }

console.log(`\n${total - fallas}/${total} ${fallas ? 'FALLAS: ' + fallas : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
