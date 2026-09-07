// "Format Slots" — Sub-WF "Buscar Horarios Validado" (GuDQ9VmKWZvQnerV)
//
// PEDIDO TEXTUAL DE LA DRA. RAQUEL (WhatsApp, 2026-09-07):
//   "Al momento de ofrecer los turnos no es necesario que diga <sistema de gestion>, los pacientes no
//    conocen el sistema" · "por lo menos ofrecer dos de la mañana y dos de la tarde, los mas proximos"
//   · "no preguntar que franja de horario le viene bien ni en que fecha especifica quiere el turno" ·
//   "solo procedemos en decirles que turnos disponemos y ellos eligen de acuerdo a esas opciones".
//
// Este nodo YA NO llama a la agenda ni tiene tokens adentro: recibe los slots ya acumulados y
// deduplicados por "Acumular P1/P2/P3" y solo ARMA EL TEXTO. Formato exacto que escribio la Dra.:
//
//   Tenemos los próximos turnos disponibles:
//   Por la mañana:
//   * Jueves 24 de septiembre 8:00 , 8:40
//   * Martes 29 de septiembre 8:40 , 9:20
//
//   Por la tarde:
//   * Miércoles 30 de septiembre 16:20
//   * Lunes 5 de octubre 15:00 , 15:40
//
//   Le sirve alguno?
//
// Reglas del bloque: dia de la semana con mayuscula inicial y mes en MINUSCULA; hora HH:MM sin "hs" y sin
// cero adelante; los horarios del MISMO dia van en UNA linea separados por " , "; si una franja no tiene
// ningun turno se omite la seccion ENTERA (encabezado incluido) y no se inventa nada.
//
// El dia de la semana sale del calendario real (new Date(año, mes-1, dia) construye medianoche LOCAL del
// mismo Y-M-D: no lo corre ninguna zona horaria). El sub-agent tiene PROHIBIDO recalcularlo.

const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
               'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const DIAS = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];

const CORTE_TARDE = 13;            // mañana = hora_inicio < 13 · tarde = hora_inicio >= 13
const MAX_DIAS_POR_FRANJA = 2;     // "por lo menos dos de la mañana y dos de la tarde"
const MAX_HORARIOS_POR_DIA = 2;    // como en el ejemplo que mando la Dra. ("9:20 , 10:40")

const ENCABEZADO = 'Tenemos los próximos turnos disponibles:';
const CIERRE = 'Le sirve alguno?';

const entrada = $input.first().json || {};
const slots = Array.isArray(entrada.slots) ? entrada.slots : [];
const errores = Array.isArray(entrada.errores) ? entrada.errores : [];

const RE_FECHA = /^(\d{2})\/(\d{2})\/(\d{4})$/;
const aIso = (dmy) => { const m = RE_FECHA.exec(String(dmy || '')); return m ? m[3] + '-' + m[2] + '-' + m[1] : ''; };
const horaNum = (s) => parseInt(String(s.hora_inicio || '').slice(0, 2), 10);

// '08:00' -> '8:00' · '15:40' -> '15:40'  (la Dra. escribe "8:00", sin cero adelante y sin "hs")
function fmtHora(hhmm) {
  const m = /^(\d{1,2}):(\d{2})/.exec(String(hhmm || ''));
  if (!m) return String(hhmm || '');
  return String(parseInt(m[1], 10)) + ':' + m[2];
}

// '24/09/2026' -> 'Jueves 24 de septiembre'
function fmtDia(dmy) {
  const m = RE_FECHA.exec(String(dmy || ''));
  if (!m) return String(dmy || '');
  const dia = Number(m[1]), mes = Number(m[2]), anio = Number(m[3]);
  const d = new Date(anio, mes - 1, dia);
  return DIAS[d.getDay()] + ' ' + dia + ' de ' + MESES[mes - 1];
}

// Agrupa por dia (en orden) y devuelve hasta MAX_DIAS_POR_FRANJA lineas "* <dia> <hora> , <hora>"
function seccion(lista) {
  const porDia = [];
  const indice = new Map();
  for (const s of lista) {
    const iso = s.iso || aIso(s.fecha);
    if (!indice.has(iso)) { indice.set(iso, porDia.length); porDia.push({ iso: iso, fecha: s.fecha, horas: [] }); }
    porDia[indice.get(iso)].horas.push(s.hora_inicio);
  }
  porDia.sort((a, b) => a.iso.localeCompare(b.iso));
  const elegidos = porDia.slice(0, MAX_DIAS_POR_FRANJA);
  const lineas = elegidos.map(d => '* ' + fmtDia(d.fecha) + ' ' +
    d.horas.slice().sort().slice(0, MAX_HORARIOS_POR_DIA).map(fmtHora).join(' , '));
  const ultimo = elegidos.length ? elegidos[elegidos.length - 1].iso : '';
  return { lineas: lineas, ultimo: ultimo };
}

const ordenados = slots.slice().sort((a, b) =>
  ((a.iso || aIso(a.fecha)) + a.hora_inicio).localeCompare((b.iso || aIso(b.fecha)) + b.hora_inicio));
const manana = seccion(ordenados.filter(s => horaNum(s) < CORTE_TARDE));
const tarde = seccion(ordenados.filter(s => horaNum(s) >= CORTE_TARDE));

let bloque = '';
if (manana.lineas.length || tarde.lineas.length) {
  const partes = [ENCABEZADO];
  if (manana.lineas.length) partes.push('Por la mañana:', ...manana.lineas, '');
  if (tarde.lineas.length) partes.push('Por la tarde:', ...tarde.lineas, '');
  partes.push(CIERRE);
  bloque = partes.join('\n');
}

// Para el SIGUIENTE lote cuando el paciente rechaza todo: el dia siguiente al ultimo dia ofrecido de la
// franja que termina ANTES (el MINIMO de las dos secciones), no al ultimo de todos.
// Por que el minimo: la tarde siempre cae mas lejos que la mañana (la Dra. atiende tarde solo lun/mie).
// Con el maximo, el segundo lote arrancaba despues del ultimo turno de TARDE y se salteaba mañanas mas
// proximas que el paciente nunca vio — contradice el "los mas proximos" del pedido. Ejemplo real del
// 07/09: bloque con mañanas 24/09 y 29/09 + tardes 30/09 y 05/10; con el maximo el lote 2 arrancaba el
// 06/10 y las mañanas del 01/10 y 02/10 no se ofrecian nunca. Con el minimo arranca el 30/09 y salen.
// El costo es que puede repetirse algun turno de tarde ya mostrado (si sigue libre); mostrar dos veces un
// turno es mucho menos grave que no ofrecer nunca el mas proximo.
const ultimosPorFranja = [manana.ultimo, tarde.ultimo].filter(Boolean).sort();
const ultimoOfrecido = ultimosPorFranja.length ? ultimosPorFranja[0] : '';
let siguiente_desde = '';
if (ultimoOfrecido) {
  const p = ultimoOfrecido.split('-').map(Number);
  siguiente_desde = new Date(Date.UTC(p[0], p[1] - 1, p[2] + 1)).toISOString().slice(0, 10);
}

const total_manana = ordenados.filter(s => horaNum(s) < CORTE_TARDE).length;
const total_tarde = ordenados.filter(s => horaNum(s) >= CORTE_TARDE).length;
const error_tecnico = !bloque && errores.length > 0;

// `resultado` es lo que lee el LLM. Primero la instruccion y el bloque AL FINAL (de la marca hasta el
// final del texto), asi no hay ninguna marca de cierre que se pueda copiar por error. Sin guiones: "---"
// es el separador con el que "Split en Mensajes" parte la respuesta en varios mensajes.
let resultado;
if (error_tecnico) {
  resultado = 'ERROR_TECNICO: no pude leer la agenda en este momento (' + errores.join('; ') + '). '
    + 'NO afirmes que no hay turnos y NO le pidas al paciente una fecha ni una franja. '
    + 'Intenta la busqueda una vez mas; si vuelve a fallar, escala con escalar_a_secretaria.';
} else if (!bloque) {
  resultado = 'SIN TURNOS: la agenda no tiene ningun turno libre en las proximas semanas. '
    + 'NO inventes horarios y NO le preguntes al paciente que dia o que franja prefiere: '
    + 'decile que en este momento no hay turnos disponibles y escala con escalar_a_secretaria.';
} else {
  const faltaTarde = !tarde.lineas.length
    ? ' En este periodo no hay ningun turno de tarde: por eso el bloque no trae esa seccion (no la inventes).' : '';
  const faltaManana = !manana.lineas.length
    ? ' En este periodo no hay ningun turno de mañana: por eso el bloque no trae esa seccion (no la inventes).' : '';
  resultado = 'INSTRUCCION (no la copies): abajo esta el MENSAJE EXACTO para el paciente. Pegalo tal cual, '
    + 'letra por letra: sin reescribirlo, sin reordenarlo, sin agregar ni quitar turnos, sin agregar "hs", '
    + 'sin cambiar mayusculas ni acentos y sin nombrar el sistema de gestion de la clinica. '
    + 'PROHIBIDO preguntarle al paciente que dia, que fecha o que franja prefiere: estas son las opciones y elige el.'
    + faltaTarde + faltaManana
    + ' Si las rechaza TODAS, volve a llamar esta tool con desde=' + siguiente_desde + ' para el siguiente lote.\n'
    + 'MENSAJE EXACTO PARA EL PACIENTE (desde la proxima linea hasta el final):\n'
    + bloque;
}

return [{
  json: {
    resultado: resultado,
    bloque: bloque,
    hay_turnos: !!bloque,
    error_tecnico: error_tecnico,
    total_manana: total_manana,
    total_tarde: total_tarde,
    dias_escaneados: Number(entrada.dias_escaneados) || 0,
    paginas: Number(entrada.paginas) || 0,
    siguiente_desde: siguiente_desde,
    errores: errores
  }
}];
