// historial_core.js — v7 · el contexto de la conversación que ve Asiri. Fuente de verdad en el repo (se inlinea en un nodo Code de n8n).
// Reemplaza al nodo de memoria sin filtro: arma los últimos turnos REALES desde n8n_chat_histories (más nuevo primero), acorta los marcadores del staff
// (250 caracteres de "[ATENCION HUMANA - ...]" en cada llamada era ruido) y descarta las etiquetas internas del Router viejo.
const HistorialCore = (() => {
  const ETIQUETAS_ROUTER = new Set(['cancelar_o_reprogramar', 'confirmar', 'agendar', 'urgencia', 'consulta_general', 'general', 'pago', 'derivar', 'silencio', 'no_reply', 'cancelar', 'reprogramar',
    'confirmar_post_recordatorio', 'agendar_nuevo', 'urgencia_dolor']);
  const corta = (s, n) => { const t = String(s || '').replace(/\s+/g, ' ').trim(); return t.length > n ? t.slice(0, n - 1) + '…' : t; };

  // rows: [{ message: {type, content, additional_kwargs?} | string JSON }] ordenadas del MÁS NUEVO al más viejo (como las devuelve la consulta).
  function armar(rows, max) {
    const turnos = [];
    for (const r of rows || []) {
      let m = r && r.message;
      if (typeof m === 'string') { try { m = JSON.parse(m); } catch (e) { continue; } }
      if (!m || typeof m !== 'object') continue;
      const c = String(m.content || '').trim();
      if (!c) continue;
      const src = (m.additional_kwargs || {}).source;
      if (m.type === 'human') turnos.push('PACIENTE: ' + corta(c, 500));
      else if (m.type === 'ai') {
        if (ETIQUETAS_ROUTER.has(c.toLowerCase())) continue;
        if (/^\[ATENCION HUMANA/i.test(c)) turnos.push('STAFF DE LA CLÍNICA (persona): ' + corta(c.replace(/^\[ATENCION HUMANA[^\]]*\]:?\s*/i, ''), 220));
        else if (/^\[NOTA INTERNA/i.test(c)) continue;
        else if (src === 'reminder_note' || /le recordamos su turno|recordamos que el d[ií]a/i.test(c)) turnos.push('CLÍNICA (recordatorio enviado): ' + corta(c, 260));
        else turnos.push('ASIRI: ' + corta(c, 700));
      }
      if (turnos.length >= (max || 12)) break;
    }
    return turnos.reverse();   // cronológico: lo más nuevo al final
  }
  // Texto único que se le pasa al agente como mensaje de usuario.
  // `ident` = salida de la herramienta ver_turnos (ya resuelta por el código ANTES de que Asiri responda): fichas del celular y turnos vigentes.
  function identidad(ident) {
    const i = ident || {};
    if (i.ok === true) {
      const t = (i.turnos && i.turnos.length) ? 'Turnos vigentes: ' + i.turnos.join('; ') + '.' : 'No tiene turnos vigentes.';
      if (i.varias_fichas) {
        // (06/10) Si TODOS los turnos vigentes son de una sola ficha, para cambiar/cancelar/sumar a ESE turno no hace falta preguntar para quién es
        // (gestionar_turno deduce la ficha por el turno). Solo un turno NUEVO puede ser para cualquiera de la familia. Examen 06/10, DANA-08: preguntaba "¿para quién?" de más.
        const duenos = [...new Set((i.turnos || []).map((x) => { const m = /\(([^()]+)\)\s*$/.exec(String(x)); return m ? m[1].trim() : null; }))];
        const unDueno = (i.turnos || []).length > 0 && duenos.length === 1 && duenos[0] ? duenos[0] : null;
        const pista = i.ficha_elegida ? 'Ya está elegido: ' + (i.paciente_elegido || '') + '. '
          : unDueno ? 'El paciente con turno es ' + unDueno + ' (los turnos de abajo son suyos). Si quiere cambiar o cancelar, es SU turno: gestionar_turno con esa fecha, SIN preguntar para quién es. Las otras fichas solo importan si pide un turno NUEVO para otra persona. '
          : 'TODAVÍA no sabés para quién es: igual buscá y ofrecé horarios, y en el MISMO mensaje preguntá para quién es (nombre o DNI); elegir_ficha hace falta recién para proponer. ';
        // Un familiar que no está en la lista es un paciente nuevo (gestionar_turno con nuevo_nombre/nuevo_apellido/nuevo_dni).
        return 'Pacientes con este celular: ' + (i.pacientes || []).join(', ') + '. ' + pista + 'Si es para alguien que no está en esta lista, es paciente nuevo. ' + t;
      }
      return 'Paciente de este celular: ' + (i.paciente_elegido || '(una ficha)') + '. ' + t;
    }
    // (06/10) Sin ficha = paciente NUEVO (la mayoría de los que llegan por anuncios), no una falla: se le ofrece turno y se lo da de alta al reservar.
    if (i.motivo === 'sin_ficha') return 'Paciente NUEVO: no hay ficha con este celular y no tiene turnos. Si quiere un turno, ofrecé horarios y, cuando elija uno, pedile nombre, apellido y DNI y pasalos a gestionar_turno.';
    return 'No pude consultar la ficha o la agenda en este momento' + (i.motivo ? ' (' + i.motivo + ')' : '') + '. No inventes turnos.';
  }
  // extra (08/10, orquestador): { conversacion_nueva:boolean, confirmacion_pendiente:{ texto, minutos }|null } — datos armados por código, no compuertas.
  function mensajeAgente(historial, mensaje, ahoraJujuy, recordatorios, pushName, ident, extra) {
    const partes = [];
    const x = extra || {};
    partes.push('FECHA Y HORA ACTUAL (Jujuy): ' + ahoraJujuy);
    if (x.conversacion_nueva !== undefined) partes.push('CONVERSACIÓN NUEVA (12 h sin mensajes): ' + (x.conversacion_nueva ? 'sí' : 'no'));
    if (pushName) partes.push('Nombre en WhatsApp de quien escribe: ' + corta(pushName, 40) + ' (puede ser un familiar y no el paciente).');
    if (ident !== undefined) partes.push('DATOS DE ESTE CELULAR EN LA AGENDA (ya consultados por el sistema): ' + identidad(ident));
    // (08/10, Lucas) Antes decía "PENDIENTES DE CONFIRMAR" y el modelo abría con "¿Me confirma su asistencia…?". Pedir confirmación es tarea del recordatorio, no de Asiri.
    if (recordatorios && recordatorios.length) partes.push('RECORDATORIOS YA ENVIADOS (sin respuesta; NO le pidas que confirme: si él confirma, confirmar_turno): ' + recordatorios.join(' | '));
    if (x.confirmacion_pendiente && x.confirmacion_pendiente.texto) partes.push('CONFIRMACIÓN PENDIENTE (el paciente la vio y todavía no contestó; hace ' + Number(x.confirmacion_pendiente.minutos || 0) + ' min): «' + corta(x.confirmacion_pendiente.texto, 400) + '»');
    partes.push('CONVERSACIÓN RECIENTE (lo más nuevo abajo):\n' + (historial.length ? historial.join('\n') : '(es la primera vez que escribe)'));
    partes.push('MENSAJE ACTUAL DEL PACIENTE:\n' + mensaje);
    return partes.join('\n\n');
  }
  // (08/10, orquestador) Se BORRARON las funciones de cierre, de pregunta pendiente, de saludo y de pedido de información: eran regex que decidían la intención del paciente
  // (silencio ante un "gracias", menú ante un saludo). Ahora lo decide el ORQUESTADOR (la IA) con el contexto; "conversación nueva" es un dato (12 h sin mensajes).
  return { armar, mensajeAgente, identidad, corta };
})();
if (typeof module !== 'undefined') module.exports = HistorialCore;
