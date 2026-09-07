// PEDIDO DE LA DRA. (2026-09-07): reprogramar NO vuelve a preguntar por dia ni por franja (la frase
// de la captura del 07/09 salia de aca).
// Antes habia dos ramas: si el paciente ya habia dicho fecha/franja se buscaba agenda, y si no, se le
// devolvia la pregunta (la captura que mando la Dra.). Ahora reprogramar SIEMPRE ofrece el bloque
// (2 turnos de mañana + 2 de tarde, armado por "Sub-WF - Buscar Horarios Validado") y el paciente elige.
// `prev.trigger` es la salida de "Step 0b" (la envuelve "Step 1.0: Prep Query"). A veces llega serializada:
// el mismo destrampe que ya hace "Step 3.5a: Prep Acceptance LLM".
let trg = prev.trigger;
if (typeof trg === 'string') { try { trg = JSON.parse(trg); } catch (e) { trg = {}; } }
trg = trg || {};
const bloqueOfrecido = String(trg.oferta_bloque || '');       // el bloque que ya vio el paciente (Step 0b)
const bloquesOfrecidos = Number(trg.bloques_ofrecidos) || 0;  // cuantos lotes se le mandaron ya
const esperandoEleccion = trg.multi_turn_state === 'oferta_horarios';

// "* Miercoles 30 de septiembre 16:20 , 17:00" -> la misma linea filtrada por hora minima (null si no queda
// ningun horario). Se copia el texto TAL CUAL: no se reescribe ni se recalcula el dia de la semana.
function lineaDesdeHora(linea, horaMin) {
  const m = /^(\*\s*.+?)\s((?:\d{1,2}:\d{2})(?:\s*,\s*\d{1,2}:\d{2})*)\s*$/.exec(linea);
  if (!m) return null;
  if (horaMin === null || horaMin === undefined || horaMin === '') return linea;
  const horas = m[2].split(/\s*,\s*/).filter(h => parseInt(h.split(':')[0], 10) >= Number(horaMin));
  return horas.length ? m[1] + ' ' + horas.join(' , ') : null;
}

// Devuelve el bloque recortado a UNA franja, con el MISMO formato (encabezado + seccion + cierre), o ''.
// Conserva el encabezado a proposito: es la marca que usan "Step 0b" (para saber que hay una oferta
// abierta) y el bypass del Formatting Agent en el v6.
function seccionDelBloque(franja, horaMin) {
  if (!bloqueOfrecido || (franja !== 'tarde' && franja !== 'manana')) return '';
  const lineas = [];
  let dentro = false;
  for (const raw of bloqueOfrecido.split('\n')) {
    const l = raw.trim();
    if (/^por la (mañana|manana|tarde)/i.test(l)) { dentro = (franja === 'tarde') === /tarde/i.test(l); continue; }
    if (!dentro || l.charAt(0) !== '*') continue;
    const filtrada = lineaDesdeHora(l, horaMin);
    if (filtrada) lineas.push(filtrada);
  }
  if (!lineas.length) return '';
  return ['Tenemos los próximos turnos disponibles:',
          franja === 'tarde' ? 'Por la tarde:' : 'Por la mañana:'].concat(lineas, ['', 'Le sirve alguno?']).join('\n');
}

if (intent.accion === 'reprogramar') {
  // (1) Pide una FRANJA sobre el bloque que acaba de recibir: NO se busca otro lote ni se le pregunta nada.
  //     Se le repiten las opciones de esa franja que YA estan en el bloque, copiadas letra por letra.
  //     ESTA ES LA CAPTURA #2 DE LA DRA.: pidio "A la tarde" y el bot repitio las mismas 3 mañanas.
  if (esperandoEleccion) {
    const soloFranja = seccionDelBloque(intent.franja, intent.hora_minima);
    if (soloFranja) {
      return [{ json: { ...prev, action_to_execute: 'ninguna', mensaje_final: soloFranja } }];
    }
  }
  // (2) Ya vio DOS bloques y sigue sin elegir: no hay un tercero, escala (regla de contrato del 07/09).
  if (esperandoEleccion && bloquesOfrecidos >= 2) {
    return [{ json: {
      ...prev,
      action_to_execute: 'escalar',
      mensaje_final: 'Le paso la consulta a la secretaria para que le busque un turno que le sirva y se comunique con usted.'
    }}];
  }
  // (3) Caso normal: se ofrece el (siguiente) bloque. `fecha_objetivo` viaja SOLO como "desde donde
  //     buscar" (Step 6b-prep lo valida), nunca como filtro de un dia puntual. Si el paciente ya habia
  //     recibido un bloque, el siguiente arranca despues del ultimo dia ofrecido (Step 0b lo calcula):
  //     sin eso el segundo lote salia identico al primero, byte a byte.
  return [{ json: {
    ...prev,
    action_to_execute: 'buscar_horarios',
    fecha_objetivo: intent.fecha_objetivo || (esperandoEleccion ? (trg.oferta_siguiente_desde || '') : ''),
    hora_objetivo: intent.hora_objetivo,
    franja: null,
    hora_minima: null,
    insiste_horario: intent.insiste_horario
  }}];
}