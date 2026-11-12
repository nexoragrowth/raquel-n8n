// test_info_core.mjs — v7: control por código de la respuesta de Información (horas y montos tienen que estar en los DATOS). uso: node tests/test_info_core.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const I = require('../v7/info_core.js');
const O = require('../v7/orquestador_core.js');
let fallas = 0, total = 0;
const t = (n, c, x) => { total++; if (!c) { fallas++; console.log(`  FALLA ${n}${x ? ' → ' + JSON.stringify(x).slice(0, 300) : ''}`); } else console.log(`  ok    ${n}`); };

// DATOS de ejemplo con el mismo formato que el Conocimiento de la clínica.
const DATOS = 'DATOS DEL CONSULTORIO:\n- Horarios de atención: La Dra. atiende martes y jueves de 8:00 a 12:00 hs, viernes de 8:30 a 12:00 hs, y lunes y miércoles de 15:00 a 19:00 hs.\n'
  + '- Primera consulta: tiene un valor de $50.000 e incluye evaluación.\n- No contamos con guardia ni atención espontánea 24 hs.\n- Para cancelar, avisar con 48 hs de anticipación.';
const sal = (texto) => O.salidaInformacion({ text: texto });
const v = (texto, datos = DATOS) => I.verificar(sal(texto), datos);

console.log('HORAS');
{ const r = v('Hoy por la tarde la Dra. atiende hasta las 18:00; aceptamos efectivo y transferencia.');
  t('I1 (r007 real, 12/11) una hora que no está en los DATOS no sale: fuera de alcance, el cerebro deriva', r.fuera_de_alcance === true && r.estado === 'fuera_de_alcance' && r.texto === '' && /18:00/.test(r.motivo_control) && r.codigo === 'NO_ESTA_EN_DATOS', r); }
t('I2 la respuesta correcta de r007 pasa igual', v('Esta tarde no se atiende; los jueves la Dra. atiende de 8:00 a 12:00 hs.').texto === 'Esta tarde no se atiende; los jueves la Dra. atiende de 8:00 a 12:00 hs.');
t('I3 todos los horarios de la semana pasan', v('La Dra. atiende lunes y miércoles de 15:00 a 19:00 hs; martes y jueves de 8:00 a 12:00; y viernes de 8:30 a 12:00.').estado === 'respondido');
t('I4 "08:00" y "8.30" valen como 8:00 y 8:30', v('Atiende de 08:00 a 12:00, y los viernes desde 8.30.').estado === 'respondido');
t('I5 "hasta las 19 hs" / "a las 12" valen (19:00 y 12:00 están en los DATOS)', v('Hoy miércoles atiende hasta las 19 hs.').estado === 'respondido' && v('Los martes atiende hasta las 12.').estado === 'respondido');
t('I6 "hasta las 20" no está en los DATOS: no sale', v('Hoy miércoles la Dra. atiende hasta las 20.').fuera_de_alcance === true);
t('I7 "18 hs" tampoco', v('La Dra. está hasta las 18 hs.').fuera_de_alcance === true);
t('I8 plazos de 24 o 48 hs no son horas del día', v('No contamos con guardia 24 hs; para cancelar, avise con 48 hs de anticipación.').estado === 'respondido');
t('I9 "las 3 cuotas" no es una hora', v('Se puede abonar en las 3 cuotas que figuran.').estado === 'respondido');

console.log('\nMONTOS');
t('I10 el precio de los DATOS pasa ($50.000, $ 50000, 50 mil pesos)', ['La primera consulta tiene un valor de $50.000.', 'Sale $ 50000.', 'Son 50 mil pesos.'].every((x) => v(x).estado === 'respondido'));
{ const r = v('La primera consulta tiene un valor de $35.000.');
  t('I11 un precio que no está en los DATOS no sale', r.fuera_de_alcance === true && /35000/.test(r.motivo_control), r); }

console.log('\nLO DEMÁS NO SE TOCA');
for (const x of ['FUERA_DE_ALCANCE', 'URGENCIA', '[NO_REPLY]']) { const s = sal(x); t(`I12 ${x}: sale tal cual`, I.verificar(s, DATOS) === s); }
{ const s = O.salidaInformacion({ error: 'x' }); t('I13 error técnico: sale tal cual', I.verificar(s, DATOS) === s); }
t('I14 sin horas ni montos pasa aunque no haya DATOS', v('Atendemos solo con turno previo; no tenemos guardia.', '').estado === 'respondido');
t('I15 sin DATOS, cualquier hora es sospechosa: no sale', v('Atiende de 8:00 a 12:00.', '').fuera_de_alcance === true);
{ const r = v('Atiende hasta las 18:00.');
  t('I16 se guarda lo descartado (para revisar) y los demás campos quedan', r.texto_descartado === 'Atiende hasta las 18:00.' && r.agente === 'informacion' && r.urgencia === false, r); }

console.log('\nCON EL CEREBRO');
{ const plan = O.despachar({ informacion: 'horario de hoy' }, {});
  const r = O.reunir(plan || {}, { informacion: v('Hoy por la tarde atiende hasta las 18:00.') }, { texto_paciente: 'hasta qué hora está hoy' });
  t('I17 lo descartado se deriva como cualquier fuera de alcance', r && r.derivar === true, r); }

console.log(`\n${total - fallas}/${total} ${fallas ? 'CON FALLAS' : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
