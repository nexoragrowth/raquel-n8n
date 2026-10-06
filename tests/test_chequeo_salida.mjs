// test_chequeo_salida.mjs — v7: el chequeo bidireccional de salida, offline. ~45 frases × hubo/no hubo escritura ok. uso: node tests/test_chequeo_salida.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const C = require('../v7/chequeo_salida.js');

const RB_CAMBIO = 'Listo, quedó reprogramado su turno: anulé el del viernes 16/10 a las 09:10 y le reservé el jueves 22/10 a las 09:20.';
const OFERTAS = [{ fecha: '2026-10-22', hora: '08:00' }, { fecha: '2026-10-22', hora: '09:20' }, { fecha: '2026-10-23', hora: '09:10' }, { fecha: '2026-11-02', hora: '16:20' }];
const BLOQUE = 'Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n* Viernes 23 de octubre 9:10\n\nPor la tarde:\n* Lunes 2 de noviembre 16:20\n\nLe sirve alguno?';
const OK_CAMBIO = { ok: true, tipo: 'cambio', readback_text: RB_CAMBIO };
const OK_CANCEL = { ok: true, tipo: 'cancelacion', readback_text: 'Listo, su turno del viernes 16/10 a las 09:10 quedó cancelado.' };
const OK_CONF = { ok: true, tipo: 'confirmacion', readback_text: 'Listo, su turno del viernes 16/10 a las 09:10 quedó confirmado.' };
const PARCIAL = { ok: false, parcial: true, tipo: 'cambio', readback_text: 'Le reservé el jueves 22/10 a las 09:20 pero no pude anular el anterior; le aviso a la clínica para que lo ajuste.' };
const FALLO = { ok: false, tipo: 'cambio', readback_text: null };

let fallas = 0, total = 0;
const caso = (nombre, entrada, esperado) => {
  total++;
  const r = C.revisar({ ofertas: OFERTAS, bloque_ofertas: BLOQUE, turnos_vistos: [{ fecha: '2026-10-16', hora_inicio: '09:10:00' }], ...entrada });
  const ok = r.accion === esperado.accion && (!esperado.motivo || r.motivo === esperado.motivo) && (!esperado.texto || r.texto === esperado.texto);
  if (!ok) { fallas++; console.log(`  FALLA ${nombre} → ${r.accion}/${r.motivo}  (esperaba ${esperado.accion}/${esperado.motivo || '*'})`); } else console.log(`  ok    ${nombre}`);
};
const pasa = { accion: 'pasar' };
const reemplaza = (motivo, texto) => ({ accion: 'reemplazar', motivo, texto });

console.log('P. Anotar un AVISO no es escribir en la agenda (falsos positivos del examen 06/10)');
caso('P1 "Dejé anotado su aviso de pago…" sin escritura → pasa', { texto: 'Dejé anotado su aviso de pago. Cuando mande el comprobante por este chat, la secretaria lo verifica en su horario de atención.', libro: null }, pasa);
caso('P2 "Quedó anotado su aviso de pago para Lucas." → pasa', { texto: 'Quedó anotado su aviso de pago para Lucas. ¿Puede enviar el comprobante?', libro: null }, pasa);
caso('P3 "Se lo dejo anotado a la clínica." (lista de espera) → pasa', { texto: 'Se lo dejo anotado a la clínica.', libro: null }, pasa);
caso('P4 "Ya le anoté para el jueves." sin ok → sigue bloqueando', { texto: 'Ya le anoté para el jueves.', libro: null }, reemplaza('afirma_reprogramar_sin_ok', C.honesto));
caso('P5 "Ya anoté su turno." sin ok → bloquea', { texto: 'Ya anoté su turno.', libro: null }, reemplaza('afirma_reprogramar_sin_ok', C.honesto));

console.log('A. Hay escritura OK: el texto tiene que decir lo que se hizo');
caso('A1 el texto contiene el read-back exacto', { texto: RB_CAMBIO, libro: OK_CAMBIO }, pasa);
caso('A2 el read-back con un saludo antes y una pregunta después', { texto: 'Perfecto, Dana. ' + RB_CAMBIO + ' ¿Necesita algo más?', libro: OK_CAMBIO }, pasa);
caso('A3 timeout: el modelo no llegó a escribir nada → se manda el resultado real', { texto: '', libro: OK_CAMBIO }, reemplaza('falta_confirmacion_de_lo_hecho', RB_CAMBIO));
caso('A4 el modelo dice otra fecha (jueves 29/10 a las 10:00) → se reemplaza', { texto: 'Listo, le reservé el jueves 29/10 a las 10:00.', libro: OK_CAMBIO }, reemplaza('fecha_distinta_a_la_escrita', RB_CAMBIO));
caso('A5 el modelo se va por las ramas y no confirma lo hecho', { texto: 'Con gusto. Cualquier consulta me escribe.', libro: OK_CAMBIO }, reemplaza('falta_confirmacion_de_lo_hecho', RB_CAMBIO));
caso('A6 cancelación ok con su texto', { texto: OK_CANCEL.readback_text, libro: OK_CANCEL }, pasa);
caso('A7 confirmación ok con su texto', { texto: OK_CONF.readback_text, libro: OK_CONF }, pasa);
caso('A8 escritura parcial: tiene que decirlo (y se avisa ACCION)', { texto: 'Listo, ya está todo.', libro: PARCIAL }, reemplaza('escritura_parcial_sin_decirlo', PARCIAL.readback_text));
caso('A9 escritura parcial dicha bien: pasa', { texto: PARCIAL.readback_text, libro: PARCIAL }, pasa);

console.log('\nB. NO hay escritura OK: no puede afirmar que algo quedó hecho');
const afirmaciones = [
  'Listo, quedó reprogramado su turno para el jueves 22/10 a las 09:20.', 'Su turno quedó cancelado.', 'Ya le reservé el turno.', 'Le agendé el jueves 22 a las 9:20.',
  'Ya está, le cambié el turno.', 'Anoté su turno para el 22/10.', 'Cancelé el turno del viernes.', 'Lo moví al jueves.', 'Queda confirmado su turno del 16/10.',
  'Listo, confirmado.', 'Le dejo agendado el turno.', 'Ya le anoté para el jueves.', 'Reprogramé su turno como me pidió.', 'Quedó reservado el jueves 22 a las 09:20.',
  'Perfecto, quedó agendado.', 'Anulé el turno anterior.', 'Confirmé su asistencia.',
];
afirmaciones.forEach((t, i) => caso(`B${i + 1} afirma sin ok: «${t.slice(0, 48)}»`, { texto: t, libro: null }, { accion: 'reemplazar' }));
caso('B18 escritura que FALLÓ + "listo" → bloquea', { texto: 'Listo, quedó reprogramado.', libro: FALLO }, reemplaza('afirma_reprogramar_sin_ok', C.honesto));
caso('B19 ok de OTRO tipo: confirmó un turno pero dice "cancelé" → se reemplaza por lo que realmente pasó', { texto: 'Cancelé su turno.', libro: OK_CONF }, reemplaza('falta_confirmacion_de_lo_hecho', OK_CONF.readback_text));
caso('B20 ok de cancelación pero dice "quedó reprogramado" → se reemplaza por lo que realmente pasó', { texto: 'Quedó reprogramado para el jueves.', libro: OK_CANCEL }, reemplaza('falta_confirmacion_de_lo_hecho', OK_CANCEL.readback_text));
caso('B21 la escritura salió bien Y el modelo agrega una afirmación de otro tipo ("y cancelé el otro") → bloquea', { texto: RB_CAMBIO + ' Además cancelé su otro turno.', libro: OK_CONF.readback_text ? { ...OK_CAMBIO } : null }, reemplaza('afirma_cancelar_sin_ok', C.honesto));
caso('B22 sin tilde, con clítico: "Ya le reserve el turno" → bloquea', { texto: 'Ya le reserve el turno.', libro: null }, { accion: 'reemplazar' });

console.log('\nC. Frases que NO son afirmaciones (no se pueden bloquear)');
const normales = [
  'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?',
  '¿Le confirmo que desea cancelar el turno del viernes 16/10 a las 09:10?', 'Por favor confirme su asistencia respondiendo a este mensaje.',
  'Con gusto. ¿Para quién es el turno?', 'La consulta cuesta $50.000.', 'Atendemos lunes y miércoles de 15 a 20 hs y martes, jueves y viernes de 8 a 12 hs.',
  'Quedó anotada su consulta, la secretaria se comunicará con usted.', 'No pude reservar ese horario: puede que se haya ocupado recién. Su turno actual sigue vigente.',
  '¿Le sirve alguno de esos horarios?', 'Puedo cambiarlo si me dice qué día le queda mejor.', 'Cuando quiera, le busco otro horario.', 'Gracias por avisar.',
];
normales.forEach((t, i) => caso(`C${i + 1} «${t.slice(0, 54)}»`, { texto: t, libro: null, propuesta_readback: i === 0 ? t : (i === 1 ? t : null), ofertas: OFERTAS }, pasa));

console.log('\nD. Horarios: toda fecha+hora tiene que haber sido ofrecida');
caso('D1 el bloque tal cual → pasa', { texto: BLOQUE, libro: null }, pasa);
caso('D2 el bloque con un horario inventado (viernes 23 a las 10:00) → se reemplaza por el bloque real', { texto: BLOQUE.replace('9:10', '10:00'), libro: null }, reemplaza('horario_no_ofrecido', BLOQUE));
caso('D3 una oferta suelta en una frase ("el jueves 22/10 a las 09:20") → pasa', { texto: 'Tenemos el jueves 22/10 a las 09:20, ¿le sirve?', libro: null }, pasa);
caso('D4 una oferta suelta con hora inventada → reemplaza', { texto: 'Tenemos el jueves 22/10 a las 11:40, ¿le sirve?', libro: null }, reemplaza('horario_no_ofrecido', BLOQUE));
caso('D5 un turno que el paciente YA tiene (16/10 09:10) no cuenta como horario inventado', { texto: 'Veo su turno del viernes 16/10 a las 09:10. ¿Lo quiere cancelar o cambiar?', libro: null }, pasa);
caso('D6 horario inventado y sin bloque disponible → mensaje seguro', { texto: 'Tenemos el 22/10 a las 11:40.', libro: null, bloque_ofertas: null }, { accion: 'reemplazar', motivo: 'horario_no_ofrecido' });
caso('D7 la hora del horario de atención ("de 15 a 20 hs") no es una pareja fecha+hora', { texto: 'Atendemos lunes y miércoles de 15 a 20 hs.', libro: null }, pasa);

console.log('\nF. Varias escrituras en la misma respuesta (libro = lista)');
const OK_CONF_B = { ok: true, tipo: 'confirmacion', readback_text: 'Listo, su turno del martes 20/10 a las 16:20 quedó confirmado.' };
caso('F1 dos confirmaciones y el texto dice las dos → pasa', { texto: OK_CONF.readback_text + ' ' + OK_CONF_B.readback_text, libros: [OK_CONF, OK_CONF_B] }, pasa);
caso('F2 dos confirmaciones y el texto dice solo la última → pasa (la clínica ve las dos en la agenda)', { texto: OK_CONF_B.readback_text, libros: [OK_CONF, OK_CONF_B] }, pasa);
caso('F3 dos confirmaciones y el texto no dice ninguna → se reemplaza por lo hecho', { texto: 'Gracias por avisar.', libros: [OK_CONF, OK_CONF_B] }, { accion: 'reemplazar', motivo: 'falta_confirmacion_de_lo_hecho' });
caso('F4 una confirmación ok y una que falló: el texto dice la ok y no afirma la otra → pasa', { texto: OK_CONF.readback_text, libros: [OK_CONF, { ok: false, tipo: 'confirmacion', readback_text: null }] }, pasa);
caso('F5 libros vacío + afirma → bloquea', { texto: 'Listo, quedó confirmado.', libros: [] }, { accion: 'reemplazar', motivo: 'afirma_confirmar_sin_ok' });

console.log('\nG. Lo que el código le da a Asiri para pegar TEXTUAL tiene que llegar al paciente');
const RB_PROP = 'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?';
caso('G1 propuesta de esta ejecución y el modelo la pega → pasa', { texto: 'Perfecto. ' + RB_PROP, libros: [], propuesta_readback: RB_PROP }, pasa);
caso('G2 propuesta y el modelo se la saltea (habla de otra cosa) → se envía el read-back del código', { texto: 'Un momento, lo estoy viendo.', libros: [], propuesta_readback: RB_PROP }, reemplaza('falta_readback', RB_PROP));
caso('G3 propuesta y el modelo responde con una afirmación falsa → gana el read-back (la salida correcta de la charla)', { texto: 'Listo, quedó reprogramado.', libros: [], propuesta_readback: RB_PROP }, reemplaza('falta_readback', RB_PROP));
caso('G4 bloque recién buscado y el modelo lo pega → pasa', { texto: BLOQUE, libros: [], bloque_exec: BLOQUE }, pasa);
caso('G5 bloque recién buscado y el modelo pregunta otra cosa → se envía el bloque', { texto: 'Le quedan las fichas de Jana y Lucas. ¿Confirma?', libros: [], bloque_exec: BLOQUE }, reemplaza('falta_bloque', BLOQUE));
caso('G6 bloque pegado con una frase antes → pasa', { texto: 'Con gusto.\n\n' + BLOQUE, libros: [], bloque_exec: BLOQUE }, pasa);
caso('G7 sin propuesta ni bloque de esta ejecución: no se fuerza nada', { texto: 'Hola, ¿en qué puedo ayudarle?', libros: [] }, pasa);

console.log('\nE. Extracción de fechas y horas');
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
total++; if (eq(C.parejas(BLOQUE), ['10-22 08:00', '10-22 09:20', '10-23 09:10', '11-02 16:20'])) console.log('  ok    E1 el bloque entero da las 4 parejas'); else { fallas++; console.log('  FALLA E1', C.parejas(BLOQUE)); }
total++; if (eq(C.parejas('el jueves 22/10 a las 9:20'), ['10-22 09:20'])) console.log('  ok    E2 "22/10 a las 9:20" se normaliza a 09:20'); else { fallas++; console.log('  FALLA E2', C.parejas('el jueves 22/10 a las 9:20')); }
total++; if (eq(C.parejas('Atendemos de 8:00 a 12:00'), [])) console.log('  ok    E3 horas sin fecha no generan parejas'); else { fallas++; console.log('  FALLA E3'); }

console.log(`\n${total - fallas}/${total} ${fallas ? 'FALLAS: ' + fallas : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
