// "Output Error" — Sub-WF "Buscar Horarios Validado" (GuDQ9VmKWZvQnerV)
//
// Red de seguridad de la rama `false` de "Fecha valida?". Desde el 2026-09-07 es un camino practicamente
// muerto: "Validar fecha" ya no rechaza nada (fecha vacia / mal formada / pasada -> busca desde HOY).
// Lo que SI cambio es el texto: antes decia "el parametro 'fecha' es OBLIGATORIO ... pedile al paciente
// una fecha concreta (que dia prefiere)", que es exactamente lo que la Dra. prohibio.
const v = $('Validar fecha').first().json || {};
return [{
  json: {
    resultado: 'ERROR_INTERNO_BUSQUEDA: no pude preparar la busqueda de agenda (fecha calculada: "'
      + (v.fecha || '') + '"). NO le pidas al paciente una fecha ni una franja y NO afirmes que no hay '
      + 'turnos. Volve a llamar esta tool SIN parametros (busca desde hoy); si vuelve a fallar, escala '
      + 'con escalar_a_secretaria.',
    bloque: '',
    hay_turnos: false,
    error_tecnico: true,
    total_manana: 0,
    total_tarde: 0,
    dias_escaneados: 0,
    paginas: 0,
    siguiente_desde: '',
    errores: ['fecha invalida en Validar fecha']
  }
}];
