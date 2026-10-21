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
const ejec = (p, io, extra = {}) => Core.ejecutar({ propuesta: p, exec_id_actual: 'ex-2', enviada: true, modo: 'vivo', ...extra }, io, extra.ahora || AHORA);   // (08/10) solo escribe con modo 'vivo' explícito

console.log('PROPONER (validaciones por código)');
{ const r = prop(); t('P01 cambio feliz de la charla real de Dana', r.ok && /^Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra\. Raquel, reemplazando el turno del viernes 16\/10 a las 09:10\. ¿Procedo con la reserva\?$/.test(r.readback_text), r);
  t('P01b el read-back es idéntico al que el bot real mandó el 05/10', r.readback_text === 'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?', r.readback_text); }
t('P02 horario que nadie ofreció (10:00) → no_ofrecido', prop({ ...CAMBIO, hora: '10:00' }).motivo === 'no_ofrecido');
t('P03 año equivocado (2027) → no_ofrecido', prop({ ...CAMBIO, fecha: '2027-10-22' }).motivo === 'no_ofrecido');
t('P04 hora sin cero "9:20" vale (se normaliza)', prop().ok && prop().propuesta.slot.hora === '09:20');
t('P05 dos fichas sin elegir y las dos con turno ese día → ficha_no_elegida', prop(CAMBIO, estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: null }, turnos_vistos: [T_VIEJO, { ...T_VIEJO, id: 9300, id_paciente: 777 }] })).motivo === 'ficha_no_elegida');
{ const r = prop(CAMBIO, estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: 651 } })); t('P06 dos fichas con elegida: el read-back nombra al paciente', r.ok && / para Dana:/.test(r.readback_text), r.readback_text); }
// (08/10) REAL-06: antes devolvía turno_no_es_de_la_ficha y el modelo preguntaba "¿confirma…?" en bucle. Si UNA sola ficha tiene turno en esa fecha, es esa.
{ const r = prop(CAMBIO, estado({ turnos_vistos: [{ ...T_VIEJO, id_paciente: 777 }], ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: 651 } }));
  t('P07 cita vieja de OTRA ficha (una sola) → usa esa ficha y el read-back la nombra', r.ok && / para Martina:/.test(r.readback_text) && /reemplazando el turno del viernes 16\/10/.test(r.readback_text), r); }
{ const r = prop(CAMBIO, estado({ turnos_vistos: [{ ...T_VIEJO, id_paciente: 777 }, { ...T_VIEJO, id: 9301, id_paciente: 888 }], ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }, { id: 888, nombre: 'Jana' }], elegida: 651 } }));
  t('P07b dos OTRAS fichas con turno esa fecha → turno_no_es_de_la_ficha, la nota nombra a las dos', r.motivo === 'turno_no_es_de_la_ficha' && /Martina o Jana/.test(r.para_asiri), r); }
// (08/10) REAL-12: "familias solo cuando el paciente lo pide". Turno NUEVO sin decir para quién y una sola ficha con turnos → esa (el read-back la nombra).
{ const r = prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '08:00' }, estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: null } }));
  t('P07c turno nuevo, dos fichas y solo una con turnos → esa ficha, sin preguntar para quién', r.ok && / para Dana:/.test(r.readback_text), r); }
t('P07d turno nuevo, dos fichas y ninguna con turnos → ficha_no_elegida (pregunta)', prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '08:00' }, estado({ turnos_vistos: [], ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: null } })).motivo === 'ficha_no_elegida');
t('P07e turno nuevo, dos fichas y las dos con turnos → ficha_no_elegida (pregunta)', prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '08:00' }, estado({ turnos_vistos: [T_VIEJO, { ...T_VIEJO, id: 9300, id_paciente: 777, fecha: '2026-11-04' }], ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: null } })).motivo === 'ficha_no_elegida');
t('P08 fecha de turno viejo inexistente → cita_no_vista', prop({ ...CAMBIO, fecha_turno_viejo: '2026-10-19' }).motivo === 'cita_no_vista');
t('P09 turno viejo en menos de 48 h → menos_48h', prop({ ...CAMBIO, fecha_turno_viejo: '2026-10-06' }, estado({ turnos_vistos: [{ ...T_VIEJO, fecha: '2026-10-06', hora_inicio: '09:10:00' }] })).motivo === 'menos_48h');
t('P10 varios turnos y no dice cuál → cual_turno', prop({ ...CAMBIO, fecha_turno_viejo: undefined }, estado({ turnos_vistos: [T_VIEJO, { ...T_VIEJO, id: 9200, fecha: '2026-11-04' }] })).motivo === 'cual_turno');
t('P11 sin haber llamado ver_turnos → ver_turnos_primero', prop(CAMBIO, estado({ turnos_vistos: undefined })).motivo === 'ver_turnos_primero');
t('P12 turno anulado no cuenta como vigente (el paciente no tiene a qué cambiar)', prop({ ...CAMBIO, fecha_turno_viejo: undefined }, estado({ turnos_vistos: [{ ...T_VIEJO, id_estado: 1 }] })).motivo === 'sin_turnos');
{ const r = prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '09:20' });
  t('P13 pide un turno y ya tiene uno (07/10): sin pregunta extra, confirmación de OTRO turno "además de su turno del…"', r.ok && r.propuesta.tipo === 'sumar' && r.readback_text === 'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, además de su turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?', r); }
{ const r = prop({ tipo: 'sumar', fecha: '2026-10-22', hora: '09:20' }); t('P14 sumar explícito: read-back "además de su turno"', r.ok && /además de su turno del viernes 16\/10/.test(r.readback_text), r); }
t('P15 reserva sin turnos vigentes: ok', prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '09:20' }, estado({ turnos_vistos: [] })).ok);
{ const r = prop({ tipo: 'cancelacion', fecha_turno_viejo: '2026-10-16' }); t('P16 cancelación ok con confirmación', r.ok && /¿Procedo con la cancelación de su turno del viernes 16\/10 a las 09:10\?/.test(r.readback_text), r.readback_text); }
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
{ const r = await ejec(P, mkIO(), { ahora: '2026-10-06T01:00:00Z' }); t('E09 propuesta vencida (>12 h; 21/10: antes 30 min) → vencida', r.motivo === 'vencida'); }
{ const r = await ejec(P, mkIO(), { ahora: '2026-10-05T13:30:00Z' }); t('E09b (auditoría 21/10, real 320078) un "sí" a los 54 min ya NO vence la confirmación', r.motivo !== 'vencida', r); }
{ const io = mkIO({ getFalla: true }); const r = await ejec(P, io); t('E10 la agenda no responde al verificar: no escribe nada', r.motivo === 'error_tecnico' && !io.log.includes('POST')); }
{ const io = mkIO({ consumirFalla: true }); const r = await ejec(P, io); t('E10b Redis caído al consumir: no escribe nada', r.motivo === 'error_tecnico' && !io.log.includes('POST')); }
{ const pc = prop({ tipo: 'cancelacion', fecha_turno_viejo: '2026-10-16' }).propuesta; const io = mkIO(); const r = await ejec(pc, io);
  t('E11 cancelación feliz: solo PUT', r.ok && io.log.join(',') === 'consumir,GET,PUT 9104' && /cancelado/.test(r.readback_text), io.log);
  const io2 = mkIO({ putMal: true }); const r2 = await ejec(prop({ tipo: 'cancelacion', fecha_turno_viejo: '2026-10-16' }).propuesta, io2);
  t('E11b cancelación que la agenda rechaza: no dice cancelado', !r2.ok && r2.motivo === 'no_pude_cancelar' && !/quedó cancelado/.test(r2.readback_text || '')); }
{ const pr = prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '09:20' }, estado({ turnos_vistos: [] })).propuesta; const io = mkIO(); const r = await ejec(pr, io);
  t('E12 reserva simple: solo POST, sin GET ni PUT', r.ok && io.log.join(',') === 'consumir,POST', io.log);
  t('E12b (16/10) paciente con ficha: NO es primera consulta (sin pedido de pago)', r.primera_consulta === false, r.primera_consulta); }
{ const io = mkIO(); const r = await ejec(P, io, { modo: 'sombra' }); t('E13 modo sombra: cero llamadas y devuelve lo que habría hecho', r.ok && r.simulado === true && io.log.length === 0 && r.habria_hecho.slot.hora === '09:20', io.log); }
{ const r = await Core.ejecutar({ propuesta: null, exec_id_actual: 'ex-2', enviada: true }, mkIO(), AHORA); t('E14 sin propuesta → sin_propuesta', r.motivo === 'sin_propuesta'); }
{ const pf = prop(CAMBIO, estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: 777 }, turnos_vistos: [{ ...T_VIEJO, id_paciente: 777 }] })).propuesta; const io = mkIO({ citaCambia: { id_paciente: 777 } });
  const r = await ejec(pf, io); t('E15 familias: reserva para la ficha ELEGIDA (777), no la primera', r.ok && r.ledger.escrituras[0].body.id_paciente === 777, r.ledger); }

console.log('\nFAMILIAS: ficha deducida cuando no hay ambigüedad (06/10)');
{ const F2 = { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: null };
  const r1 = prop(CAMBIO, estado({ ficha: F2 })); t('F01 cambio de un turno que es de UNA sola ficha: la deduce y el read-back dice para quién', r1.ok && r1.propuesta.paciente_id === 651 && /para Dana/.test(r1.readback_text), r1);
  const r2 = prop({ tipo: 'sumar', fecha: '2026-10-22', hora: '08:00' }, estado({ ficha: F2 })); t('F02 sumar cuando solo una ficha tiene turno vigente: la deduce', r2.ok && r2.propuesta.paciente_id === 651, r2);
  const ambos = [T_VIEJO, { ...T_VIEJO, id: 9300, id_paciente: 777 }];
  const r3 = prop(CAMBIO, estado({ ficha: F2, turnos_vistos: ambos })); t('F03 las dos fichas tienen turno ese día: NO deduce, pide elegir ficha', !r3.ok && r3.motivo === 'ficha_no_elegida', r3);
  const r4 = prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '08:00' }, estado({ ficha: F2, turnos_vistos: [] })); t('F04 reserva nueva en un celular con varias fichas: NO deduce (puede ser para cualquiera)', !r4.ok && r4.motivo === 'ficha_no_elegida', r4); }

console.log('\nDECIDIR (herramienta única gestionar_turno: misma llamada para confirmar y para ejecutar)');
{ // (08/10, orquestador) El "sí" lo decide el agente de TURNOS (confirma=true), no una regex. El código solo verifica DATOS: confirmación guardada pendiente,
  // vista (es lo último que dijo Asiri), vigente (30 min). Sin confirma, NUNCA se ejecuta.
  const RB = prop().readback_text;
  const d1 = Core.decidir(CAMBIO, { ...estado(), ultimo_asiri: 'Tenemos los próximos turnos disponibles…', texto_paciente: 'el jueves 22 a las 9:20' }, AHORA);
  t('D01 primera llamada: devuelve el read-back y NO ejecuta', d1.etapa === 'confirmacion' && d1.resultado.texto_para_el_paciente === RB && d1.propuesta.exec_id === 'ex-1', d1);
  const G = { ...d1.propuesta, enviada: true };
  const d2 = Core.decidir({ ...CAMBIO, hora: '09:20', confirma: 'true' }, { ...estado({ exec_id: 'ex-2' }), propuesta_guardada: G, ultimo_asiri: RB, texto_paciente: 'ya' }, AHORA);
  t('D02 confirma=true (lo decidió Turnos) + read-back visto: ejecuta la GUARDADA', d2.etapa === 'ejecutar' && d2.propuesta.enviada === true && d2.propuesta.exec_id === 'confirmada' && d2.propuesta.cita_vieja.id === 9104 && d2.propuesta.confirmada_por === 'agente_turnos', d2);
  const d2b = Core.decidir({ ...CAMBIO, confirma: true }, { ...estado({ exec_id: 'ex-3' }), propuesta_guardada: G, ultimo_asiri: 'Perfecto. ' + RB, texto_paciente: 'sisi porfa' }, AHORA);
  t('D03 mismo pedido confirmado dos veces: el id de la propuesta es ESTABLE (el candado evita la doble escritura)', d2b.etapa === 'ejecutar' && d2b.propuesta.id === d2.propuesta.id, [d2b.propuesta.id, d2.propuesta.id]);
  const d3 = Core.decidir(CAMBIO, { ...estado(), propuesta_guardada: G, ultimo_asiri: RB, texto_paciente: 'Sí' }, AHORA);
  t('D04 SIN confirma (aunque el texto diga "Sí") NO ejecuta: el código no lee el "sí", vuelve a mostrar la confirmación', d3.etapa === 'confirmacion', d3.etapa);
  const d4 = Core.decidir({ ...CAMBIO, confirma: 'true' }, { ...estado(), propuesta_guardada: G, ultimo_asiri: 'Tenemos los próximos turnos…', texto_paciente: 'Sí' }, AHORA);
  t('D05 confirma=true pero el último mensaje de Asiri NO es ese read-back (no lo vio): NO ejecuta', d4.etapa === 'confirmacion', d4.etapa);
  const d5 = Core.decidir({ ...CAMBIO, confirma: 'true' }, { ...estado(), propuesta_guardada: null, ultimo_asiri: RB, texto_paciente: 'Si' }, AHORA);
  t('D06 confirma=true sin confirmación guardada: NO ejecuta (muestra el read-back)', d5.etapa === 'confirmacion', d5.etapa);
  const d6 = Core.decidir({ ...CAMBIO, confirma: 'true' }, { ...estado(), propuesta_guardada: { ...G, creada_ms: Date.parse(AHORA) - 13 * 3600000 }, ultimo_asiri: RB, texto_paciente: 'Sí' }, AHORA);
  t('D07 confirma=true con la confirmación vencida (13 h): NO ejecuta', d6.etapa !== 'ejecutar', d6.etapa);
  const d7 = Core.decidir({ ...CAMBIO, hora: '10:00' }, { ...estado(), ultimo_asiri: RB, texto_paciente: 'Sí' }, AHORA);
  t('D08 horario no ofrecido: error del código, nunca ejecuta', d7.etapa === 'error' && d7.resultado.motivo === 'no_ofrecido' && d7.resultado.ok === false, d7);
  const d8 = Core.decidir({ tipo: 'reserva', fecha: '2026-10-22', hora: '9:20' }, { ...estado(), ultimo_asiri: '', texto_paciente: 'el jueves 22' }, AHORA);
  t('D09 reserva con turno vigente: devuelve la confirmación de otro turno además del suyo (no pregunta cambiar o sumar)', d8.etapa === 'confirmacion' && d8.resultado.texto_para_el_paciente === 'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, además de su turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?', d8.resultado);
  const d9 = Core.decidir({ ...CAMBIO, confirma: 'false' }, { ...estado(), propuesta_guardada: G, ultimo_asiri: RB, texto_paciente: 'ok lo pienso' }, AHORA);
  t('D10 confirma="false" ("ok lo pienso"): NO ejecuta', d9.etapa === 'confirmacion', d9.etapa);
  t('D11 ya no existen esAfirmacion / siDirecto / siALaConfirmacion (ninguna regex decide un "sí")', Core.esAfirmacion === undefined && Core.siDirecto === undefined && Core.siALaConfirmacion === undefined); }

console.log('\nPACIENTE NUEVO (alta en la agenda con el mismo "sí", 06/10)');
{ // celular sin ficha: ver_turnos no deja ni ficha ni turnos en Redis
  const SIN = estado({ ficha: null, turnos_vistos: null });
  const RES = { tipo: 'reserva', fecha: '2026-10-22', hora: '9:20' };
  const NUEVO = { ...RES, nuevo_nombre: 'juan carlos', nuevo_apellido: 'PÉREZ', nuevo_dni: '40.123.456' };
  const r0 = prop(RES, SIN);
  t('N01 sin ficha y sin datos: pide nombre, apellido y DNI en un mensaje (no deriva a la clínica)', r0.motivo === 'sin_ficha' && /nombre, apellido y DNI/.test(r0.para_asiri) && /nuevo_dni/.test(r0.para_asiri) && !/avisar_grupo/.test(r0.para_asiri), r0);
  const r0b = prop({ tipo: 'cancelacion', fecha_turno_viejo: '2026-10-16' }, SIN);
  t('N01b sin ficha y quiere cancelar: no inventa turnos, lo pasa a la clínica', r0b.motivo === 'sin_ficha' && /avisar_grupo/.test(r0b.para_asiri), r0b);
  const r1 = prop({ ...RES, nuevo_nombre: 'Juan', nuevo_dni: '40123456' }, SIN);
  t('N02 datos incompletos (sin apellido) → faltan_datos_paciente y dice qué falta', r1.motivo === 'faltan_datos_paciente' && /apellido/.test(r1.para_asiri), r1);
  t('N02b DNI imposible (3 dígitos) → faltan_datos_paciente', prop({ ...NUEVO, nuevo_dni: '123' }, SIN).motivo === 'faltan_datos_paciente');
  const r2 = prop(NUEVO, SIN);
  t('N03 read-back con nombre normalizado, DNI con puntos y "paciente nuevo"', r2.ok && r2.readback_text === 'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, a nombre de Juan Carlos Pérez (DNI 40.123.456), como paciente nuevo. ¿Procedo con la reserva?', r2.readback_text);
  t('N03b la propuesta no tiene ficha y lleva los datos del alta', r2.ok && r2.propuesta.paciente_id === null && r2.propuesta.paciente_nuevo.dni === '40123456' && r2.propuesta.tipo === 'reserva', r2.propuesta);
  t('N04 paciente nuevo igual exige un horario ofrecido', prop({ ...NUEVO, hora: '10:00' }, SIN).motivo === 'no_ofrecido');
  t('N05 "sumar" para un paciente nuevo se vuelve reserva', prop({ ...NUEVO, tipo: 'sumar' }, SIN).propuesta?.tipo === 'reserva');
  t('N05b cambio para un paciente nuevo → paciente_nuevo_sin_turnos', prop({ ...NUEVO, tipo: 'cambio', fecha_turno_viejo: '2026-10-16' }, SIN).motivo === 'paciente_nuevo_sin_turnos');
  // celular con ficha(s): el "nuevo" puede ser alguien que ya está
  const FAM = estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana', apellidos: 'Barro', rut: '49966117' }, { id: 777, nombre: 'Martina', apellidos: 'Barro', rut: '' }], elegida: null } });
  const r3 = prop({ ...RES, nuevo_nombre: 'Dana', nuevo_apellido: 'Barro', nuevo_dni: '49966117' }, FAM);
  t('N06 el "nuevo" es una ficha del celular (mismo DNI): usa esa ficha, no da de alta (y como tiene turno, es otro además del suyo)', r3.ok && r3.propuesta.paciente_id === 651 && !r3.propuesta.paciente_nuevo && r3.propuesta.tipo === 'sumar', r3);
  const r4 = prop({ ...RES, nuevo_nombre: 'Martina', nuevo_apellido: 'Barro', nuevo_dni: '51234567' }, FAM);
  t('N07 ficha del v6 sin DNI y mismo nombre y apellido: usa esa ficha (sin duplicar)', r4.ok && r4.propuesta.paciente_id === 777 && !r4.propuesta.paciente_nuevo && / para Martina:/.test(r4.readback_text), r4);
  t('N08 mismo nombre que una ficha con OTRO DNI → dni_no_coincide (no duplica ni elige)', prop({ ...RES, nuevo_nombre: 'Dana', nuevo_apellido: 'Barro', nuevo_dni: '11111111' }, FAM).motivo === 'dni_no_coincide');
  const r5 = prop({ ...RES, nuevo_nombre: 'Tomás', nuevo_apellido: 'Barro', nuevo_dni: '55666777' }, FAM);
  t('N09 familiar que no figura (hijo nuevo en el celular de la mamá): alta como paciente nuevo', r5.ok && r5.propuesta.paciente_id === null && r5.propuesta.paciente_nuevo.nombre === 'Tomás', r5);
  const r6 = prop({ ...RES, nuevo_nombre: 'Tomás', nuevo_apellido: 'Barro', nuevo_dni: '55666777' }, estado());
  t('N09b una sola ficha (elegida sola) pero el turno es para otro: gana el paciente nuevo', r6.ok && r6.propuesta.paciente_id === null && /como paciente nuevo/.test(r6.readback_text), r6);
  t('N10 la ficha_no_elegida le dice al modelo que un familiar que no figura es paciente nuevo', /nuevo_dni/.test(prop(RES, estado({ ficha: FAM.ficha, turnos_vistos: [] })).para_asiri || ''));

  // decidir: el "sí" al read-back del paciente nuevo ejecuta
  const d1 = Core.decidir({ ...NUEVO, confirma: 'true' }, { ...SIN, exec_id: 'ex-2', propuesta_guardada: { ...r2.propuesta, enviada: true }, ultimo_asiri: r2.readback_text, texto_paciente: 'Sí, dale' }, AHORA);
  t('N11 decidir: read-back visto + confirma (Turnos) → ejecutar con los datos del alta', d1.etapa === 'ejecutar' && d1.propuesta.paciente_nuevo && d1.propuesta.paciente_id === null, d1);
  const d2 = Core.decidir({ ...NUEVO, nuevo_apellido: 'Pérez Gómez' }, { ...SIN, ultimo_asiri: r2.readback_text, texto_paciente: 'Sí' }, AHORA);
  t('N11b otro apellido en la 2.ª llamada: el texto no coincide → vuelve a confirmar, no escribe', d2.etapa === 'confirmacion');

  // ejecutar con alta
  const PN = { ...r2.propuesta, creada_ms: Date.parse(AHORA) - 60000, exec_id: 'ex-1' };
  const ioN = (o = {}) => { const io = mkIO(o); const bodies = [];
    io.buscarDni = async (dni) => { io.log.push('GET dni ' + dni); if (o.dniFalla) throw new Error('timeout'); return o.dniResp || { data: [] }; };
    io.postPaciente = async (b) => { io.log.push('POST paciente' + (b.rut ? ' con dni' : ' sin dni')); bodies.push(b); const r = (o.altas || [{ data: { id: 900, ...b } }]); return r[Math.min(bodies.length - 1, r.length - 1)]; };
    io.bodies = bodies; return io; };
  { const io = ioN(); const r = await ejec(PN, io);
    t('N12 alta feliz: busca DNI → crea con DNI → reserva en la ficha nueva', r.ok && io.log.join('|') === 'consumir|GET dni 40123456|POST paciente con dni|POST' && r.readback_text === 'Listo, le reservé el jueves 22/10 a las 09:20 a nombre de Juan Carlos Pérez.', [io.log, r]);
    t('N12b el alta lleva nombre, apellidos, celular y DNI (rut); la reserva va a la ficha 900', JSON.stringify(io.bodies[0]) === JSON.stringify({ nombre: 'Juan Carlos', apellidos: 'Pérez', celular: '5490000000651', rut: '40123456' }) && r.ledger.escrituras[1].body.id_paciente === 900, io.bodies);
    t('N12c nota para la clínica con la ficha nueva', /Paciente nuevo dado de alta: Juan Carlos Pérez \(DNI 40123456\), ficha #900\.$/.test(r.nota_alta || ''), r.nota_alta);
    t('N12d (16/10) paciente nuevo dado de alta: primera consulta (va el pedido de pago)', r.primera_consulta === true, r.primera_consulta); }
  { const io = ioN(); const r = await ejec({ ...PN, tel: '186523445209876' }, io);   // (20/10, BOT-01) escribe desde un @lid: el "teléfono" no es un celular
    t('N12e (BOT-01) número oculto (@lid): alta SIN celular (nunca uno falso), reserva igual y la nota pide cargar el celular a mano',
      r.ok && !('celular' in io.bodies[0]) && io.bodies[0].rut === '40123456' && /SIN celular, cargarlo a mano/.test(r.nota_alta || ''), [io.bodies, r.nota_alta]);
    t('N12f con un celular válido la nota no pide cargarlo', !/SIN celular/.test((await ejec(PN, ioN())).nota_alta || '')); }
  { const io = ioN({ dniResp: { data: [{ id: 555, nombre: 'Juan', apellidos: 'Perez', rut: '40123456', habilitado: 1 }] } }); const r = await ejec(PN, io);
    t('N13 el DNI ya tiene ficha (otro celular) y el nombre coincide: NO crea, reserva en esa ficha', r.ok && !io.log.some((x) => x.startsWith('POST paciente')) && r.ledger.escrituras[0].body.id_paciente === 555 && /celular nuevo/.test(r.nota_alta || ''), [io.log, r]); }
  { const io = ioN({ dniResp: { data: [{ id: 556, nombre: 'Rosa', apellidos: 'Quispe', rut: '40123456', habilitado: 1 }] } }); const r = await ejec(PN, io);
    t('N14 el DNI es de OTRA persona: no crea, no reserva, aviso ACCIÓN a la clínica', r.motivo === 'dni_en_otra_ficha' && !io.log.some((x) => x.startsWith('POST')) && /^\[ACCIÓN\]/.test(r.aviso_clinica || ''), [io.log, r]); }
  { const io = ioN({ dniFalla: true }); const r = await ejec(PN, io);
    t('N15 la búsqueda por DNI falla: sigue y crea igual (no frena la reserva)', r.ok && io.log.includes('POST paciente con dni'), io.log); }
  { const io = ioN({ altas: [{ error: { message: '422 - rut inválido', httpCode: '422' } }, { data: { id: 901 } }] }); const r = await ejec(PN, io);
    t('N16 la agenda rechaza el DNI (4xx): reintenta UNA vez sin DNI, reserva y pide cargar el DNI a mano', r.ok && io.log.join('|') === 'consumir|GET dni 40123456|POST paciente con dni|POST paciente sin dni|POST' && r.ledger.escrituras[2].body.id_paciente === 901 && /cargarlo a mano/.test(r.nota_alta || ''), [io.log, r]); }
  { const io = ioN({ altas: [{ data: { id: 902, nombre: 'Juan Carlos', rut: '' } }] }); const r = await ejec(PN, io);
    t('N16b la agenda crea la ficha pero devuelve el rut vacío: reserva igual y pide cargar el DNI a mano', r.ok && r.ledger.escrituras[1].body.id_paciente === 902 && /cargarlo a mano/.test(r.nota_alta || ''), r.nota_alta); }
  { const io = ioN({ altas: [{ data: { id: 903 } }] }); const r = await ejec(PN, io);
    t('N16c la agenda devuelve solo el id (sin rut): se asume cargado, sin falsa alarma', r.ok && !/cargarlo a mano/.test(r.nota_alta || ''), r.nota_alta); }
  { const io = ioN({ altas: [{ error: { message: 'network error' } }] }); const r = await ejec(PN, io);
    t('N17 error de red en el alta: NO reintenta (podría haberse creado) ni reserva; aviso ACCIÓN', r.motivo === 'no_pude_registrar' && io.log.filter((x) => x.startsWith('POST')).length === 1 && /^\[ACCIÓN\]/.test(r.aviso_clinica || ''), [io.log, r]); }
  { const io = ioN({ altas: [{ error: { message: 'read ECONNRESET', code: 'ECONNRESET', port: 443, address: '10.0.0.1' } }] }); const r = await ejec(PN, io);
    t('N17b error de red con "port: 443" en el detalle: tampoco se toma como rechazo 4xx', r.motivo === 'no_pude_registrar' && io.log.filter((x) => x.startsWith('POST')).length === 1, io.log); }
  { const io = ioN({ altas: [{ error: { message: '400 - "{\\"error\\":\\"rut\\"}"', statusCode: 400 } }, { error: { message: '400' } }] }); const r = await ejec(PN, io);
    t('N18 la agenda rechaza el alta dos veces: no reserva, aviso ACCIÓN', r.motivo === 'no_pude_registrar' && !io.log.includes('POST'), [io.log, r]); }
  { const io = ioN({ postError: true }); const r = await ejec(PN, io);
    t('N19 alta ok pero el horario se ocupó: no dice "su turno actual sigue vigente" (no tenía) y deja la nota del alta', r.motivo === 'reserva_rechazada' && !/sigue vigente/.test(r.para_asiri) && /ficha #900/.test(r.nota_alta || ''), r); }
  { const io = ioN(); const r = await ejec(PN, io, { modo: 'sombra' });
    t('N20 sombra: no busca, no crea ni reserva; devuelve el texto final y lo que habría dado de alta', r.simulado && !io.log.length && r.habria_hecho.alta_paciente.dni === '40123456' && /a nombre de Juan Carlos Pérez/.test(r.readback_text), [io.log, r]); } }

console.log('\nTEXTOS ARMADOS POR CÓDIGO en los momentos clave (07/10: el orquestador entiende, elige y pega)');
{ const RES = { tipo: 'reserva', fecha: '2026-10-22', hora: '9:20' };
  // (07/10) EL CASO DE LA CAPTURA DE LUCAS: 1.ª llamada "sumar" → confirmación; el paciente dice "Sí"; en la 2.ª llamada el modelo manda "reserva".
  // Antes: no coincidía y terminaba en "¿Quiere pasarlo… o mantenerlo?". Ahora el "sí" ejecuta la confirmación guardada (la que vio el paciente).
  const r1 = prop({ ...RES, tipo: 'sumar' });
  const guardada = { ...r1.propuesta, enviada: true };
  const d1 = Core.decidir({ ...RES, tipo: 'reserva', confirma: 'true' }, { ...estado({ exec_id: 'ex-2' }), propuesta_guardada: guardada, ultimo_asiri: r1.readback_text, texto_paciente: 'Sí.' }, AHORA);
  t('T01 "Sí" a la confirmación y el modelo cambia el pedido en la 2.ª llamada: se ejecuta LO QUE VIO el paciente (sumar), sin otra pregunta', d1.etapa === 'ejecutar' && d1.propuesta.tipo === 'sumar' && d1.propuesta.readback_text === r1.readback_text && d1.propuesta.id === 'h-5490000000651-' + Core.hashTexto(r1.readback_text) + '-' + r1.propuesta.creada_ms, d1);
  // (15/10, prueba en vivo) misma pregunta, otra propuesta (el turno se volvió a dar en el mismo horario): candado distinto; la MISMA propuesta, el mismo.
  const otra = { ...guardada, creada_ms: guardada.creada_ms + 60000 };
  const d1b = Core.decidir({ ...RES, confirma: 'true' }, { ...estado({ exec_id: 'ex-2' }), propuesta_guardada: otra, ultimo_asiri: r1.readback_text, texto_paciente: 'Sí.' }, AHORA);
  const d1c = Core.decidir({ ...RES, confirma: 'true' }, { ...estado({ exec_id: 'ex-2' }), propuesta_guardada: guardada, ultimo_asiri: r1.readback_text, texto_paciente: 'Sí sí' }, AHORA);
  // (15/10, prueba en vivo) Turnos arma la propuesta y en la MISMA ejecución dice "confirma"; el último mensaje de Asiri es la MISMA pregunta de antes
  // (texto idéntico): no se ejecuta, porque esta propuesta no se envió (enviada !== true) y es de esta ejecución.
  const recien = { ...r1.propuesta };   // como la guarda proponer: sin enviada, exec_id = esta ejecución
  const dRec1 = Core.decidir({ ...RES, tipo: 'sumar', confirma: 'true' }, { ...estado(), propuesta_guardada: recien, ultimo_asiri: r1.readback_text, texto_paciente: 'Quiero sumar el turno' }, AHORA);
  const dRec2 = Core.decidir({ ...RES, tipo: 'sumar', confirma: 'true' }, { ...estado({ exec_id: 'ex-2' }), propuesta_guardada: recien, ultimo_asiri: r1.readback_text, texto_paciente: 'sí' }, AHORA);
  t('T01e propuesta armada en ESTA ejecución + "confirma": NO ejecuta (vuelve a mostrar la pregunta); tampoco una no enviada en otra ejecución', dRec1.etapa !== 'ejecutar' && dRec2.etapa !== 'ejecutar', [dRec1.etapa, dRec2.etapa]);
  t('T01b dos propuestas con el mismo texto tienen candados distintos; dos "sí" a la misma, el mismo candado', d1b.etapa === 'ejecutar' && d1b.propuesta.id !== d1.propuesta.id && d1c.propuesta.id === d1.propuesta.id, [d1.propuesta.id, d1b.propuesta.id, d1c.propuesta.id]);
  const d1n = Core.decidir({ ...RES, tipo: 'reserva' }, { ...estado(), propuesta_guardada: guardada, ultimo_asiri: r1.readback_text, texto_paciente: 'No, mejor cambiarlo' }, AHORA);
  t('T01b "No, mejor cambiarlo" (Turnos no pone confirma): NO ejecuta', d1n.etapa !== 'ejecutar', d1n);
  const d1v = Core.decidir({ ...RES, tipo: 'sumar', confirma: 'true' }, { ...estado(), propuesta_guardada: { ...guardada, creada_ms: Date.parse(AHORA) - 31 * 60000 }, ultimo_asiri: r1.readback_text, texto_paciente: 'Sí' }, AHORA);
  t('T01c confirmación guardada vencida (31 min): no se ejecuta la guardada; se recalcula con lo que pide ahora', !(d1v.etapa === 'ejecutar' && d1v.propuesta.creada_ms === guardada.creada_ms - 31 * 60000), d1v);
  const d1e = Core.decidir({ ...RES, tipo: 'sumar', confirma: 'true' }, { ...estado(), propuesta_guardada: { ...guardada, estado: 'ejecutada' }, ultimo_asiri: r1.readback_text, texto_paciente: 'Sí' }, AHORA);
  t('T01d confirmación guardada ya ejecutada: no la vuelve a tomar como pendiente (el candado de ejecución sigue cuidando la doble escritura)', d1e.propuesta && d1e.propuesta.estado !== 'ejecutada', d1e);
  // (08/10) T02/T02b ("sí directo" por regex, sin el modelo) se borraron con siDirecto: el "sí" lo decide el agente de Turnos.
  const dos = prop(RES, estado({ turnos_vistos: [T_VIEJO, { ...T_VIEJO, id: 9200, fecha: '2026-11-04' }] }));
  t('T03 con dos turnos: la confirmación los nombra a los dos ("además de sus turnos del … y del …")', dos.readback_text === 'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, además de sus turnos del viernes 16/10 a las 09:10 y del miércoles 4/11 a las 09:10. ¿Procedo con la reserva?', dos.readback_text);
  const SIN = estado({ ficha: null, turnos_vistos: null });
  const s1 = prop(RES, SIN);
  t('T04 paciente nuevo: el pedido de datos lo arma el código', s1.motivo === 'sin_ficha' && s1.texto_para_el_paciente === 'Para reservarle el turno necesito nombre, apellido y DNI del paciente, en un solo mensaje.', s1);
  const s2 = Core.decidir(RES, { ...SIN, ultimo_asiri: s1.texto_para_el_paciente, texto_paciente: 'Camila' }, AHORA);
  t('T04b si ya se los pidió y no llegaron completos, lo pide con otras palabras', s2.resultado.texto_para_el_paciente === 'Disculpe, para registrarlo necesito el nombre, el apellido y el número de DNI del paciente.', s2.resultado);
  t('T05 paciente nuevo con un horario que NO se ofreció: no pide el DNI, primero hay que ofrecer', prop({ ...RES, hora: '10:00' }, SIN).motivo === 'no_ofrecido');
  const f1 = prop({ ...RES, nuevo_nombre: 'Camila' }, SIN);
  t('T06 datos incompletos: dice exactamente qué falta', f1.texto_para_el_paciente === 'Para registrarlo me falta el apellido y el DNI del paciente.', f1);
  const fam = prop(RES, estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: null }, turnos_vistos: [] }));
  t('T07 familia: "¿Para quién es el turno: Dana o Martina?" y la nota dice que si YA lo dijo no lo mande', fam.texto_para_el_paciente === '¿Para quién es el turno: Dana o Martina? Si es para otra persona, me pasa nombre, apellido y DNI.' && /YA dijo/.test(fam.para_asiri), fam);
  const cual = prop({ ...CAMBIO, fecha_turno_viejo: undefined }, estado({ turnos_vistos: [T_VIEJO, { ...T_VIEJO, id: 9200, fecha: '2026-11-04' }] }));
  t('T08 varios turnos y no dijo cuál: la pregunta los nombra', cual.texto_para_el_paciente === '¿Cuál de sus turnos: el viernes 16/10 a las 09:10 o el miércoles 4/11 a las 09:10?', cual); }

{ // (07/10) familia: si todos los turnos son de una ficha, cancelar/cambiar SIN fecha deduce esa ficha (examen DANA-08: preguntaba "¿para quién?" dos veces)
  const FAMx = estado({ ficha: { fichas: [{ id: 651, nombre: 'Dana' }, { id: 777, nombre: 'Martina' }], elegida: null } });
  const c = prop({ tipo: 'cancelacion' }, FAMx);
  t('F10 cancelar sin fecha en una familia donde el único turno es de Dana → propone cancelar el de Dana', c.ok && c.propuesta.paciente_id === 651 && c.propuesta.cita_vieja.id === 9104, c); }

{ // (07/10) examen AGE-06: un turno el MISMO DÍA que el que ya tiene es un cambio (no quedar con dos turnos ese día)
  const OF = [...OFERTAS, { fecha: '2026-10-16', hora: '08:30' }];
  const r = prop({ tipo: 'reserva', fecha: '2026-10-16', hora: '08:30' }, estado({ ofertas: OF }));
  t('S01 pide turno y elige uno el mismo día que el suyo → confirmación de CAMBIO ("reemplazando el turno del…")', r.ok && r.propuesta.tipo === 'cambio' && r.propuesta.cita_vieja.id === 9104 && /reemplazando el turno del viernes 16\/10 a las 09:10/.test(r.readback_text), r);
  const r2 = prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '9:20' });
  t('S02 otro día → sigue siendo un turno además del suyo', r2.ok && r2.propuesta.tipo === 'sumar', r2.propuesta && r2.propuesta.tipo); }

{ // (08/10, I3 de la crítica) El DNI que copia el modelo NO se pisa con una regex sobre el texto: se VERIFICA que esos dígitos estén en lo que escribió el paciente,
  // comparando solo dígitos de los dos lados ("35.123.456", "35 123 456" valen). Si no aparece → se lo pide (texto fijo).
  const SINF = estado({ ficha: null, turnos_vistos: null });
  const NV = { tipo: 'reserva', fecha: '2026-10-22', hora: '9:20', nuevo_nombre: 'Lucas', nuevo_apellido: 'Fernández' };
  const d = Core.decidir({ ...NV, nuevo_dni: '334445555' }, { ...SINF, ultimo_asiri: '…', texto_paciente: '33.444.555', textos_paciente: ['quiero turno', '33.444.555'] }, AHORA);
  t('R01 el modelo copió mal el DNI (no está en lo que escribió el paciente): no lo corrige ni lo inventa, pide el DNI', d.etapa === 'error' && d.resultado.motivo === 'dni_no_escrito' && d.resultado.texto_para_el_paciente === 'Para registrarlo me falta el DNI del paciente.', d.resultado);
  const ok1 = Core.decidir({ ...NV, nuevo_dni: '33444555' }, { ...SINF, ultimo_asiri: '…', texto_paciente: 'x', textos_paciente: ['lucas fernandez dni 33.444.555'] }, AHORA);
  const ok2 = Core.decidir({ ...NV, nuevo_dni: '33.444.555' }, { ...SINF, ultimo_asiri: '…', texto_paciente: 'x', textos_paciente: ['Lucas', 'Fernandez', '33 444 555'] }, AHORA);
  t('R01b DNI con puntos o espacios (en el mensaje o en la copia del modelo): vale, sale el read-back de paciente nuevo', ok1.etapa === 'confirmacion' && ok2.etapa === 'confirmacion' && /DNI 33\.444\.555\)/.test(ok2.resultado.texto_para_el_paciente), [ok1.etapa, ok2.resultado]);
  const sinLista = Core.decidir({ ...NV, nuevo_dni: '33444555' }, { ...SINF, ultimo_asiri: '…', texto_paciente: 'x' }, AHORA);
  t('R01c sin la lista de mensajes (llamada vieja) no se verifica: no se traba al paciente', sinLista.etapa === 'confirmacion', sinLista.etapa);
  t('R02 un DNI de 9 dígitos no es válido (faltan datos)', prop({ tipo: 'reserva', fecha: '2026-10-22', hora: '9:20', nuevo_nombre: 'Lucas', nuevo_apellido: 'Fernández', nuevo_dni: '334445555' }, SINF).motivo === 'faltan_datos_paciente'); }

{ // (07/10) "16/10" leído al revés (2026-16-10): la fecha del turno viejo se prueba invertida
  const r = prop({ ...CAMBIO, fecha_turno_viejo: '2026-16-10' });
  t('R03 fecha del turno viejo con día y mes invertidos → encuentra su turno del 16/10', r.ok && r.propuesta.cita_vieja.id === 9104, r); }

console.log(`\n${total - fallas}/${total} ${fallas ? 'FALLAS: ' + fallas : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
