// "Validar fecha" — Sub-WF "Buscar Horarios Validado" (GuDQ9VmKWZvQnerV)
//
// 2026-09-07, pedido de la Dra. Raquel: el bot NO le pregunta al paciente que dia ni que franja quiere
// ("atendemos en horarios y dias especificos, mayormente no coincide con la necesidad del paciente").
// Consecuencia directa para este nodo: la busqueda YA NO puede exigir una fecha. Sin parametros se
// busca desde HOY (America/Argentina/Jujuy) y listo.
//
// Parametros (los dos OPCIONALES):
//   fecha  YYYY-MM-DD  compatibilidad con las llamadas viejas del v6.
//   desde  YYYY-MM-DD  "dame el SIGUIENTE lote": el paciente rechazo los turnos que ya se le ofrecieron.
//                      Gana sobre `fecha` cuando vienen los dos.
// Si lo que llega no es una fecha ISO, o es pasada, o esta a mas de 12 meses -> SE IGNORA y se busca
// desde hoy. Nunca se devuelve un error que termine pidiendole la fecha al paciente.
//
// `franja` / `hora_minima` NO se leen mas: nunca llegaron. La tool `buscar_horarios` (toolWorkflow v2.2)
// solo mapea los campos de `workflowInputs`, y el trigger solo declara los suyos; el array `fields` que
// los describia era residuo de la tv 1.x. Verificado en las ejecuciones 272491 / 272461 / 270492:
// `Validar fecha` siempre salio con franja:null, hora_minima:null. Ahora el bloque trae mañana Y tarde,
// asi que no hace falta ninguna preferencia.

const input = $input.first().json || {};

const ISO = /^\d{4}-\d{2}-\d{2}$/;
const HOY = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Argentina/Jujuy' }).format(new Date());
// Tope defensivo de 12 meses: una fecha mas lejana casi siempre es un año mal tipeado por el LLM.
const TOPE = (() => {
  const [y, m, d] = HOY.split('-').map(Number);
  return new Date(Date.UTC(y + 1, m - 1, d)).toISOString().slice(0, 10);
})();

function crudo(clave) {
  const q = input.query;
  let v = input[clave];
  if (v == null && q && typeof q === 'object') v = q[clave];
  if (v == null && typeof q === 'string' && ISO.test(q.trim())) v = q;
  return String(v ?? '').trim();
}

const pedidoFecha = crudo('fecha');
const pedidoDesde = crudo('desde');
const pedido = pedidoDesde || pedidoFecha;
const pedidoValido = ISO.test(pedido) && pedido >= HOY && pedido <= TOPE;

// LO IMPORTANTE: si el parametro no sirve, se ignora y se busca desde hoy. No se le pide nada al paciente.
const fecha = pedidoValido ? pedido : HOY;

return [{
  json: {
    fecha,
    hoy: HOY,
    fecha_pedida: pedidoFecha || null,
    desde_pedido: pedidoDesde || null,
    parametro_ignorado: !!(pedido && !pedidoValido),
    // La rama `false` del IF quedo como red de seguridad: con el fallback a HOY esto es true siempre.
    valida: ISO.test(fecha) && fecha >= HOY
  }
}];
