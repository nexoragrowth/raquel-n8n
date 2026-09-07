// 'turnos disponibles:' es la primera linea del bloque nuevo ("Tenemos los próximos turnos disponibles:",
// pedido de la Dra. 2026-09-07). Sin esta pata el paciente elige un turno del bloque, "Step 3.5a" no
// arranca el parser de aceptacion y se pierde la eleccion.
if (/turnos disponibles:|te ofrezco|te puedo ofrecer|tengo disponible|cual confirma|cual prefiere/i.test(lower)) {