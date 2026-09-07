// "Step 6b-out: Ofrecer Slots" — Sub-WF CancelarReprogramar (5cAWJxiWJ50hxEq3)
//
// Antes armaba el mensaje a mano: "Tengo disponibles en <sistema de gestion> los siguientes turnos
// proximos: <3 slots del mismo dia separados por ' / '>. ¿Te sirve alguno?" (captura de la Dra., 07/09).
// Ahora el texto llega YA ARMADO desde "Sub-WF - Buscar Horarios Validado" (campo `bloque`) con el
// formato exacto que pidio la Dra., y este nodo solo elige entre bloque / canned de escalada.
//
// NO se reescribe el bloque acá: es texto final para el paciente, y el bot lo manda tal cual
// ("Necesita Formatting?" lo desvia del Formatting Agent y "Split en Mensajes" tiene el guard).

const respuesta = $input.first().json || {};
const prev = $('Step 6b-prep: Prep Query Horarios').first().json;

const bloque = typeof respuesta.bloque === 'string' ? respuesta.bloque.trim() : '';
const fallo = !!(respuesta.error || respuesta.error_tecnico);

let mensaje;
let escalar;
if (bloque) {
  mensaje = bloque;
  escalar = false;
} else if (fallo) {
  mensaje = 'Disculpe, tuve un inconveniente tecnico para acceder a la agenda en este momento. Le dejo una nota a la secretaria para que se comunique con usted.';
  escalar = true;
} else {
  mensaje = 'En este momento no tengo turnos disponibles para ofrecerle. Le dejo una nota a la secretaria para que se comunique con usted.';
  escalar = true;
}

return [{
  json: {
    ...prev,
    slots_match: [],
    bloque_turnos: bloque,
    total_manana: Number(respuesta.total_manana) || 0,
    total_tarde: Number(respuesta.total_tarde) || 0,
    siguiente_desde: respuesta.siguiente_desde || '',
    mensaje_final: mensaje,
    apply_label_humano: escalar
  }
}];
