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
        return 'Pacientes con este celular: ' + (i.pacientes || []).join(', ') + '. ' + (i.ficha_elegida ? 'Ya está elegido: ' + (i.paciente_elegido || '') + '. ' : 'TODAVÍA no sabés para quién es: igual buscá y ofrecé horarios, y en el MISMO mensaje preguntá para quién es (nombre o DNI); elegir_ficha hace falta recién para proponer. ') + t;
      }
      return 'Paciente de este celular: ' + (i.paciente_elegido || '(una ficha)') + '. ' + t;
    }
    return 'No pude consultar la ficha o la agenda en este momento' + (i.motivo ? ' (' + i.motivo + ')' : '') + '. No inventes turnos; para consultas de datos del consultorio seguí normal, y si necesitás la agenda avisá a la clínica con avisar_grupo.';
  }
  function mensajeAgente(historial, mensaje, ahoraJujuy, recordatorios, pushName, ident) {
    const partes = [];
    partes.push('FECHA Y HORA ACTUAL (Jujuy): ' + ahoraJujuy);
    if (pushName) partes.push('Nombre en WhatsApp de quien escribe: ' + corta(pushName, 40) + ' (puede ser un familiar y no el paciente).');
    if (ident !== undefined) partes.push('DATOS DE ESTE CELULAR EN LA AGENDA (ya consultados por el sistema): ' + identidad(ident));
    if (recordatorios && recordatorios.length) partes.push('RECORDATORIOS PENDIENTES DE CONFIRMAR: ' + recordatorios.join(' | '));
    partes.push('CONVERSACIÓN RECIENTE (lo más nuevo abajo):\n' + (historial.length ? historial.join('\n') : '(es la primera vez que escribe)'));
    partes.push('MENSAJE ACTUAL DEL PACIENTE:\n' + mensaje);
    return partes.join('\n\n');
  }
  // ---------------------------------------------------------------------------------------------------- cierres de conversación ("gracias", "ok", "si, gracias")
  // Un agradecimiento / despedida PURO no necesita respuesta: se corta ANTES de llamar al modelo (sin costo, sin demora y sin el "De nada! Quedo a disposición para…" genérico
  // ni el "ya le transmito su consulta a la secretaria"). El 27/05 se había sacado el filtro conversacional porque mataba "Confirmamos turno gracias": por eso este exige que el
  // mensaje sean SOLO palabras de cierre (+ a lo sumo un nombre), y el pipeline lo anula si lo último que se le dijo al paciente fue una pregunta o hay un recordatorio sin confirmar.
  const sinT = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const PALABRAS_CIERRE = new Set(['gracias', 'ok', 'oka', 'okey', 'okk', 'dale', 'listo', 'perfecto', 'genial', 'buenisimo', 'excelente', 'joya', 'barbaro', 'entendido', 'chau', 'saludos', 'abrazo', 'abrazos', 'igualmente', 'luego', 'vemos', 'pronto', 'hasta']);
  const RELLENO = new Set(['si', 'sii', 'siii', 'bien', 'muy', 'muchas', 'muchisimas', 'mil', 'de', 'nada', 'acuerdo', 'a', 'usted', 'todo', 'un', 'nos', 'que', 'tenga', 'buen', 'buena', 'dia', 'tarde', 'noche', 'lindo', 'linda', 'descanse', 'hasta', 'ya', 'recibido', 'queda', 'asi', 'y', 'tambien', 'igual']);
  function esCierre(texto) {
    const crudo = String(texto || '');
    if (/[?¿]/.test(crudo) || crudo.length > 70) return false;
    const t = sinT(crudo).replace(/[\p{Extended_Pictographic}‍️\u{1F3FB}-\u{1F3FF}]/gu, ' ').replace(/[^a-z\s]/g, ' ').replace(/\s+/g, ' ').trim();
    if (!t) return false;                                   // solo emojis: lo resuelve el pre-filtro técnico del v6, acá no se decide
    const toks = t.split(' ');
    if (toks.length > 8 || !toks.some((w) => PALABRAS_CIERRE.has(w))) return false;
    let nombres = 0;
    for (const w of toks) {
      if (PALABRAS_CIERRE.has(w) || RELLENO.has(w)) continue;
      if (/^[a-z]{3,12}$/.test(w) && toks.includes('gracias')) { nombres++; continue; }   // "Gracias Iris", "Muchas gracias Iri"
      return false;
    }
    return nombres <= 1;
  }
  // ¿Lo último que se le dijo al paciente (Asiri, el staff o un recordatorio) le pedía una respuesta? Si sí, "si, gracias" NO es un cierre: es la respuesta.
  function ultimoPideRespuesta(hist) {
    for (let i = (hist || []).length - 1; i >= 0; i--) {
      const l = String(hist[i]);
      if (/^PACIENTE:/.test(l)) continue;
      return /[?¿]/.test(l) || /confirmar su asistencia|confirme su asistencia|responda|respondiendo a este mensaje|necesito|pasame|pásame/i.test(l);
    }
    return false;
  }
  return { armar, mensajeAgente, identidad, corta, esCierre, ultimoPideRespuesta };
})();
if (typeof module !== 'undefined') module.exports = HistorialCore;
