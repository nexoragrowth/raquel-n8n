// "Step 6b-prep: Prep Query Horarios" — Sub-WF CancelarReprogramar (5cAWJxiWJ50hxEq3)
//
// ACA NACIA LA CAPTURA QUE MANDO LA DRA. EL 2026-09-07: este nodo armaba el `q` de UN SOLO dia
// (fecha:{eq:fechaObjetivo}) y "Step 6b-out" listaba los 3 primeros slots, todos del mismo dia y todos de
// mañana; cuando la paciente contestaba "A la tarde" volvia a salir lo mismo porque nadie filtraba nada.
//
// Ahora la busqueda la hace "Sub-WF - Buscar Horarios Validado" (GuDQ9VmKWZvQnerV), el MISMO que usa el
// Sub-Agent Agendar: devuelve el bloque con 2 turnos de mañana + 2 de tarde ya armado y sin nombrar el
// sistema de gestion. Este nodo solo decide DESDE cuando buscar.
//
// Regla de la Dra.: NUNCA se le pregunta al paciente la fecha ni la franja. `desde` se usa solo cuando el
// paciente por su cuenta nombro una fecha futura (o cuando ya rechazo un lote): es "traeme el siguiente
// lote", no un filtro. Si no hay nada valido, se busca desde hoy.

const prev = $input.first().json;
const intent = prev.intent || {};

const ISO = /^\d{4}-\d{2}-\d{2}$/;
const hoy = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Argentina/Jujuy' }).format(new Date());

// `fecha_objetivo` lo deja "Step 5": o la fecha que nombro el paciente por su cuenta, o —cuando ya se le
// mando un bloque y lo rechazo— el dia siguiente al ultimo turno ofrecido (Step 0b lo calcula del texto
// del bloque anterior). Sin ese arrastre el segundo lote salia identico al primero.
let desde = String(prev.fecha_objetivo || intent.fecha_objetivo || '').trim();
if (!ISO.test(desde) || desde < hoy) desde = '';

return [{
  json: {
    ...prev,
    // `desde` es lo unico que consume "Step 6b: Buscar Horarios (bloque)". Vacio = buscar desde hoy.
    desde: desde,
    // franja / hora_minima ya no filtran nada: el bloque trae SIEMPRE las dos franjas.
    franja: null,
    hora_minima: null
  }
}];
