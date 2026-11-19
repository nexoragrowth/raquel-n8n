// tests/test_datos_core.mjs — v7/datos_core.js: fuente única de los datos de la clínica (precios) con marcadores. Datos inventados (frases parecidas a las del conocimiento).
// Correr: node tests/test_datos_core.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const D = require('../v7/datos_core.js');
let ok = 0, fallos = 0;
const t = (n, c, e) => { if (c) ok++; else { fallos++; console.log('  ✗', n, e !== undefined ? JSON.stringify(e).slice(0, 400) : ''); } };

const ACTUAL = { precio_consulta: 50000, precio_devolucion: 50000 };
// Frases con el MISMO patrón que las del conocimiento real (8 de consulta + 2 de devolución, una entrada con las dos). Esperado = cómo se atribuye cada monto.
const TEXTOS = {
  a: { t: 'Solo los turnos de PRIMERA CONSULTA requieren pago anticipado ($50.000). Cuando el paciente confirma la fecha, se le envían los datos.', esperado: ['precio_consulta'] },
  b: { t: 'La primera consulta tiene un valor de $50.000 e incluye evaluación y diagnóstico. El presupuesto NO se da en esta consulta: se entrega en la cita de devolución (segunda cita, $50.000 aparte), con el plan ya definido.', esperado: ['precio_consulta', 'precio_devolucion'] },
  c: { t: 'No trabajamos con obras sociales. El valor de la consulta es $50.000.', esperado: ['precio_consulta'] },
  d: { t: 'La cita de devolución incluye: diagnóstico, plan de tratamiento y presupuesto de ortodoncia. Valor: $50.000, que se abona antes del horario del turno.', esperado: ['precio_devolucion'] },
  e: { t: 'El valor de la consulta es de $50.000, trabajamos de manera particular y con turnos programados.', esperado: ['precio_consulta'] },
  f: { t: 'En la primera consulta de valoración ($50.000) se evalúa la alineación, la mordida y la estética integral.', esperado: ['precio_consulta'] },
  g: { t: 'Las etapas se definen en la cita de devolución, luego de la primera consulta de diagnóstico ($50.000).', esperado: ['precio_consulta'] },
  h: { t: 'Si ya tiene radiografías recientes, puede traerlas para revisarlas en la consulta ($50.000).', esperado: ['precio_consulta'] },
};

// formato
t('pesos: separador de miles', D.pesos(50000) === '$50.000' && D.pesos(60000) === '$60.000' && D.pesos(1250000) === '$1.250.000' && D.pesos(999) === '$999');

// resolver
const r1 = D.resolver('La consulta cuesta {{precio_consulta}} y la devolución {{ precio_devolucion }}.', { precio_consulta: 60000, precio_devolucion: 50000 });
t('resolver reemplaza cada marcador (también con espacios) y no deja nada', r1.texto === 'La consulta cuesta $60.000 y la devolución $50.000.' && r1.faltan.length === 0, r1);
const r2 = D.resolver('Vale {{precio_consulta}} y {{cuota}}', { precio_consulta: 60000 });
t('un dato que falta NO se inventa: queda el marcador y se informa', r2.texto === 'Vale $60.000 y {{cuota}}' && r2.faltan.join() === 'cuota', r2);
for (const malo of [0, -5, NaN, '60000', null, undefined, Infinity]) t(`resolver rechaza el valor ${String(malo)}`, D.resolver('{{precio_consulta}}', { precio_consulta: malo }).faltan.length === 1);
t('resolver sin marcadores devuelve el texto igual', D.resolver('Hola', {}).texto === 'Hola' && D.resolver(null, {}).texto === '' && D.resolver(undefined, {}).texto === '');

// migración: atribución por contexto
for (const [id, c] of Object.entries(TEXTOS)) {
  const p = D.proponerMigracion(c.t, ACTUAL);
  t(`migración ${id}: cada monto va al dato correcto`, JSON.stringify(p.cambios.map((x) => x.marcador)) === JSON.stringify(c.esperado), p.cambios.map((x) => [x.marcador, x.confianza, x.motivo]));
  t(`migración ${id}: con confianza alta (nada para revisar)`, p.dudosos === 0, p.cambios);
  t(`migración ${id}: ya no queda ningún monto literal`, D.literalesPendientes({ x: p.texto }, ACTUAL).length === 0, p.texto);
  // SIN PÉRDIDA: resolver con los valores actuales devuelve EXACTAMENTE el texto original
  t(`migración ${id}: ida y vuelta idéntica con los valores de hoy`, D.resolver(p.texto, ACTUAL).texto === c.t, D.resolver(p.texto, ACTUAL).texto);
}

// el punto clave: cambiar UN dato no arrastra al otro aunque hoy valgan lo mismo
const pb = D.proponerMigracion(TEXTOS.b.t, ACTUAL).texto;
const nuevo = D.resolver(pb, { precio_consulta: 60000, precio_devolucion: 50000 }).texto;
t('consulta a $60.000: cambia la consulta y la devolución del MISMO texto sigue en $50.000', nuevo.includes('valor de $60.000') && nuevo.includes('segunda cita, $50.000 aparte'), nuevo);
const pd = D.proponerMigracion(TEXTOS.d.t, ACTUAL).texto;
t('consulta a $60.000: un texto solo de devolución no cambia', D.resolver(pd, { precio_consulta: 60000, precio_devolucion: 50000 }).texto === TEXTOS.d.t);
t('devolución a $55.000: cambia solo la devolución', D.resolver(pd, { precio_consulta: 60000, precio_devolucion: 55000 }).texto.includes('Valor: $55.000'));

// lo que no se debe tocar / lo dudoso
const otro = D.proponerMigracion('La cuota mensual es $70.000 y la consulta $50.000.', ACTUAL);
t('un monto que no es ningún dato conocido se deja como está', otro.texto.includes('$70.000') && otro.texto.includes('{{precio_consulta}}'), otro.texto);
const sin = D.proponerMigracion('Tenemos un valor de $50.000 por sesión.', ACTUAL);
t('sin pista de contexto y dos datos posibles: NO se reemplaza y queda para revisar', sin.texto.includes('$50.000') && sin.dudosos === 1 && sin.cambios[0].marcador === null, sin);
const empate = D.proponerMigracion('La consulta de devolución cuesta $50.000.', ACTUAL);
t('dos pistas a la par: se propone pero queda para revisar', empate.dudosos === 1, empate.cambios);
t('un solo dato posible y sin pista: se propone pero queda para revisar', D.proponerMigracion('Vale $50.000.', { precio_consulta: 50000 }).dudosos === 1);
t('formatos raros ($ 50000 / $50.000,00) también se reconocen', D.proponerMigracion('Sale $ 50000 la consulta y $50.000,00 la consulta.', { precio_consulta: 50000 }).cambios.length === 2);

// vista previa y pendientes
const migrados = Object.fromEntries(Object.entries(TEXTOS).map(([k, c]) => [k, D.proponerMigracion(c.t, ACTUAL).texto]));
migrados.z = 'Horarios: martes y jueves.';
const vp = D.vistaPrevia(migrados, ACTUAL, { precio_consulta: 60000, precio_devolucion: 50000 });
t('vista previa: lista solo los textos con marcadores (8) y marca los que cambian', vp.length === 8 && vp.filter((x) => x.cambia).length === 7 && !vp.find((x) => x.id === 'd').cambia, vp.map((x) => [x.id, x.cambia]));
t('vista previa: antes y después de cada texto', vp.find((x) => x.id === 'c').antes.endsWith('$50.000.') && vp.find((x) => x.id === 'c').despues.endsWith('$60.000.'));
t('literalesPendientes antes de migrar: los 8 textos', D.literalesPendientes(Object.fromEntries(Object.entries(TEXTOS).map(([k, c]) => [k, c.t])), ACTUAL).length === 8);
t('marcadores() lista los datos usados', D.marcadores('{{precio_consulta}} y {{precio_devolucion}} y {{precio_consulta}}').join() === 'precio_consulta,precio_devolucion');

console.log(`\n${ok}/${ok + fallos} ${fallos === 0 ? 'TODO OK' : 'CON FALLOS'}`);
process.exit(fallos === 0 ? 0 : 1);
