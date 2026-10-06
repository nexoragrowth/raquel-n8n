// test_banlist_usted.mjs — v7: banlist en voseo + usted. Debe bloquear lo del incidente del 09/05 en las dos formas y NO bloquear lo legítimo. uso: node tests/test_banlist_usted.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const B = require('../v7/banlist_usted.js');
let fallas = 0, total = 0;
const caso = (esperaBloqueo, texto, ctx) => { total++; const r = B.revisar(texto, ctx); const ok = r.bloquea === esperaBloqueo; if (!ok) { fallas++; console.log(`  FALLA (${esperaBloqueo ? 'debía bloquear' : 'debía pasar'}): «${texto.slice(0, 80)}» → ${r.bloquea ? r.why : 'pasó'}`); } else console.log(`  ok    ${esperaBloqueo ? 'bloquea' : 'pasa   '} ${esperaBloqueo ? '[' + r.why + '] ' : ''}«${texto.slice(0, 70)}»`); };

console.log('INCIDENTE DEL 09/05 (el texto real que se le mandó a una mamá), en voseo y en usted');
caso(true, 'Guardá la pieza, traete el DNI, venite ahora mismo, Balcarce 37 2do piso, los esperamos');
caso(true, 'Guarde la pieza, traiga el DNI, acérquese ahora mismo a la clínica, Balcarce 37 2do piso, lo esperamos');
caso(true, 'Pase por la clínica hoy y la atendemos.');
caso(true, 'Puede venir hoy mismo a la clínica.');
caso(true, 'Acérquese cuando pueda.');
caso(true, 'La atendemos hoy.');
caso(true, 'Venite cuando puedas');
caso(true, 'Vengan mañana temprano');

console.log('\nINSTRUCCIONES CLÍNICAS (usted y voseo)');
['Tome un analgésico cada 8 horas.', 'Tómese un ibuprofeno.', 'Tomá un paracetamol.', 'Aplique hielo en la zona.', 'Aplicate frío.', 'Enjuáguese con agua tibia.', 'Enjuagate con sal.',
  'Colóquese cera en el alambre.', 'Poné cera en la punta.', 'Póngase algodón.', 'Guárdela en un lugar seco.', 'Traiga la radiografía.', 'Evite masticar del lado derecho.', 'No coma cosas duras.',
  'Saque la ligadura con una pinza.'].forEach((t) => caso(true, t));

console.log('\nDIAGNÓSTICO / OPINIÓN / PROMESAS');
['No se preocupe, no es grave.', 'No te preocupes, es normal.', 'Es normal que duela unos días.', 'Qué macana.', 'No es nada.', 'Le aviso si se libera un turno antes.'].forEach((t) => caso(true, t));

console.log('\nDIRECCIÓN: solo si la preguntan');
caso(true, 'Estamos en Balcarce 37, 2do piso.');
caso(false, 'Estamos en Balcarce 37, 2do piso.', { pacientePidioDireccion: true });

console.log('\nEL NEGOCIO FUNCIONANDO: invitar al DIA DE LA CONSULTA es correcto');
[
  'Su turno es el jueves 22 de octubre a las 9:20. Los esperamos ese día, recuerde que el consultorio es privado y se atiende solo con turno previo.',
  'Quedó reprogramado su turno para el jueves 22/10 a las 09:20. Lo esperamos.', 'Los esperamos el día de su consulta.', 'Nos vemos el día de su turno, la esperamos.',
  'Su turno es hoy a las 17:00, la esperamos.', 'Puede venir acompañada el día de su turno del viernes 16/10 a las 09:10.',
  'Por ser menor, el tutor debe estar presente. Los esperamos el jueves 22/10 a las 9:20.',
].forEach((t) => caso(false, t));
console.log('\nINVITAR A IR YA, O SIN NINGÚN TURNO: lo que no se puede (incidente 09/05)');
[
  'Los esperamos.', 'Lo esperamos en la clínica.', 'Venga ahora mismo.', 'Su turno es el jueves, pero venga ahora mismo así lo vemos.', 'Pase por la clínica cuando quiera.',
  'Acérquese ya al consultorio.', '¿Puede venir hoy a la clínica?', 'Lo antes posible acérquese.',
].forEach((t) => caso(true, t));

console.log('\nLO LEGÍTIMO TIENE QUE PASAR');
[
  'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?',
  '¿Le confirmo que desea cancelar el turno del viernes 16/10 a las 09:10?',
  'Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n\nPor la tarde:\n* Lunes 2 de noviembre 16:20\n\nLe sirve alguno?',
  'La consulta inicial cuesta $50.000. Se abona por transferencia o en efectivo.', 'Atendemos lunes y miércoles de 15 a 20 hs y martes, jueves y viernes de 8 a 12 hs.',
  'Por ser menor, el tutor debe estar presente.', 'Su turno del jueves 22/10 a las 9:20 está confirmado. Puede venir acompañada.',
  'Le aviso a la clínica y se van a comunicar con usted.', 'Con gusto. ¿Para quién es el turno?', 'No pude reservar ese horario: puede que se haya ocupado recién. Su turno actual sigue vigente.',
  'Su turno quedó cancelado. Cuando quiera, le busco otro horario.', 'Recibimos su comprobante, la clínica lo va a verificar.', 'Quedó anotada su consulta, la secretaria se comunicará con usted.',
  'Gracias por avisar, que tenga un lindo día.', 'Tomo nota y se lo paso a la doctora.', 'Voy a pasar su consulta a la secretaria.', 'Estamos para ayudarle.',
  'Podemos buscar otra fecha si prefiere.', 'Le sirve el jueves o prefiere otro día?',
].forEach((t) => caso(false, t));

console.log(`\n${total - fallas}/${total} ${fallas ? 'FALLAS: ' + fallas : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
