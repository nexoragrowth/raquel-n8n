const textRaw = ((prev.trigger && prev.trigger.text) || '').toLowerCase();
const tieneFranjaTexto = /(tarde|mañana|mañnana|despues|pasadas|a las|hs|colegio|cole|solo puedo)/i.test(textRaw);

if (intent.accion === 'reprogramar' && (intent.fecha_objetivo || intent.franja || intent.hora_minima != null || intent.hora_objetivo || tieneFranjaTexto)) {
  const hoyStr = new Date().toISOString().slice(0, 10);
  const targetDate = intent.fecha_objetivo || hoyStr;
  return [{ json: {
    ...prev,
    action_to_execute: 'buscar_horarios',
    fecha_objetivo: targetDate,
    hora_objetivo: intent.hora_objetivo,
    franja: intent.franja,
    hora_minima: intent.hora_minima,
    insiste_horario: intent.insiste_horario
  }}];
}

if (intent.accion === 'reprogramar') {
  return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: 'Para reprogramar su turno del ' + fechaNatural(turno.fecha) + ' a las ' + horaNatural(turno.hora_inicio) + ', que dia o franja le viene mejor? (manana / tarde / fecha concreta)' } }];
}