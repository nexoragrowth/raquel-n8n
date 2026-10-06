const valid = ['confirmar_post_recordatorio', 'cancelar_o_reprogramar', 'urgencia_dolor', 'agendar_nuevo', 'consulta_general'];
const out = ($input.first().json.output || '').trim().toLowerCase();
let intent = 'consulta_general';
for (const v of valid) {
  if (out.includes(v)) { intent = v; break; }
}
// Propagar text para que los sub-agents lo accedan via $json.text
const text = $('Preparar Mensaje Final').first().json.text;

const textoNorm = (text || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();

// FIX 2026-10-02 (caso real Julieta Limpitay): "que posibilidad hay de cambiar el turno para el horario de la tarde?"
// El Router clasifica como consulta_general por tener '?' y 'consultar', Sub-Agent General devuelve [NO_REPLY]
// y el bot se clava en visto.
// Override deterministico: si el paciente pide cambiar/mover/reprogramar/pasar un turno o franja, forzar cancelar_o_reprogramar.
// URGENCIA (defensa en profundidad): un sintoma o un aparato roto gana sobre "pasar/cambiar el turno".
const esUrgenciaFuerte = (/\b(dolor\w*|duele\w*|sangr\w*|hinchaz\w*|hinchad[oa]|fiebre|pincha\w*|lastima\w*)\b/.test(textoNorm) ||
  /\bse (me |le )?(salio|desprendio|despego|rompio|solto|cayo)\b.{0,40}\b(bracket|brackets|alambre|aparato|arco|banda|ligadura|expansor)/.test(textoNorm)) &&
  !/\b(sin dolor|no (me |le )?(duele|dolio)|no (tengo|tiene|siento|siente) (ningun |nada de )?(dolor|molestia)\w*|sin molestias)\b/.test(textoNorm);
// CAMBIO / CANCELACION con las formas reales de escribirlo ("cambio el turno", "lo cancelo", "no podre asistir", "antes del que me toca").
const esPedidoReprogramar = (/\b(cambi\w*|reprogramar|mover|posponer|anular|cancel\w*|adelantar|adelanto|pasar|pasarlo|pasarla)\b/.test(textoNorm) &&
  /\b(turnos?|cita|horarios?|fecha|dias?|tarde|manana|semana)\b/.test(textoNorm)) ||
  /\bno (voy a |podre |puedo |podria |llego )?(asistir|ir|llegar|concurrir|venir)\b/.test(textoNorm) ||
  (/\bantes del (que|turno)\b/.test(textoNorm) && /\bturno\b/.test(textoNorm));

if (esUrgenciaFuerte) {
  intent = 'urgencia_dolor';
} else if (esPedidoReprogramar) {
  intent = 'cancelar_o_reprogramar';
} else {
  // FIX 2026-10-01 (caso anuncios de ads): pedido generico de info sin accion operativa
  const esPedidoGenericoInfo = /\b(quiero|necesito|quisiera|me\s+interesa|mas)\s+(mas\s+)?info(rmacion)?\b/.test(textoNorm);
  const tienePedidoOperativo = /\bturnos?\b|\bagend\w*|\breserv\w*|\bcancel\w*|\breprogram\w*|\bconfirm\w*/.test(textoNorm);
  if (esPedidoGenericoInfo && !tienePedidoOperativo) {
    intent = 'consulta_general';
  }
}

// === CONTINUIDAD DE FLUJO v2 (2026-10-05, caso real exec 294752 + replay de escenarios) ===
// El Router decide con el texto suelto. Si un flujo de turnos tiene una pregunta PENDIENTE (read-back, bloque de horarios, "¿le busco otra fecha?",
// "¿para quien es?", pedido de nombre/DNI) y el paciente la responde, la respuesta PERTENECE a ese flujo. Un cambio de turno se queda en
// cancelar_o_reprogramar (unico que puede reservar el nuevo y anular el viejo); una reserva pura en agendar_nuevo; nunca en confirmar_post_recordatorio.
// Sobrevive a una interrupcion (el paciente pregunta el precio en medio) hasta que el flujo se cierra ("quedo confirmado/cancelado/reprogramado", pre-reserva).
// No pisa urgencias, pagos/comprobantes, precio/alias/direccion ni adjuntos. Si el contexto falla o el ultimo turno no es del bot, sigue el Router.
let continuidad = null;
try {
  const ctxCrudo = String($('Build Router Context').first().json.ctx || '');
  const turnos = ctxCrudo.split('\n---\n').map(s => s.trim()).filter(Boolean).map(s => ({
    quien: /^PACIENTE:/.test(s) ? 'P' : (/^BOT:/.test(s) ? 'B' : 'S'),
    texto: s.replace(/^(PACIENTE|BOT|SYSTEM):\s*/, '')
  }));
  const ultimo = turnos[turnos.length - 1];
  const sinTildes = x => (x || '').normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
  const excluir = /\b(cuanto|precio|vale|cuesta|costo|alias|cbu|transfer\w*|comprobante|abon\w*|pague|obra social|direccion|donde queda)\b|\[imagen|\[documento|\[audio/.test(textoNorm);
  if (!esUrgenciaFuerte && intent !== 'urgencia_dolor' && !excluir &&
      ultimo && ultimo.quien === 'B' && !/^\[ATENCION HUMANA/.test(ultimo.texto)) {
    const RE_CIERRE = /queda(ra)? (confirmado|cancelado|reprogramado)|quedo (confirmado|cancelado|reprogramado)|pre-?reservado/;
    const RE_CAMBIO = /reemplazando el turno|desea cambiar ese|cambiar ese por|desea cancelar|que desea cancelar|cancelar (el|ese) turno\?/;
    const RE_RESERVA = /procedo con la reserva|le confirmo:/;
    const RE_DATOS = /nombre completo|\bdni\b|para quien (es|agendo|reservo|lo agendo)|de quien es el turno|cual de ellos/;
    const RE_HORARIOS = /tenemos los proximos turnos disponibles|le sirve alguno|quiere que le busque|desea que (le )?busque|fechas mas proximas|le busco otra|otra fecha\?/;
    const recientesPaciente = turnos.slice(-6).filter(x => x.quien === 'P').map(x => sinTildes(x.texto)).join(' | ');
    const hablaDeCambio = esPedidoReprogramar || /\b(cambi\w*|reprogram\w*|mover|no podre|no puedo|otro dia|otro turno|adelant\w*|posterg\w*|reemplaz\w*|antes del (que|turno)|pasar (el )?turno)\b/.test(recientesPaciente);
    let flujo = null, pideDatos = false, esElUltimo = false, vistos = 0;
    for (let i = turnos.length - 1; i >= 0; i--) {
      const t = turnos[i];
      if (t.quien !== 'B') continue;
      vistos++;
      if (/^\[ATENCION HUMANA/.test(t.texto)) break;
      const ub = sinTildes(t.texto);
      if (RE_CIERRE.test(ub)) break;
      if (RE_CAMBIO.test(ub)) { flujo = 'cancelar_o_reprogramar'; }
      else if (RE_RESERVA.test(ub)) { flujo = 'agendar_nuevo'; }
      else if (RE_DATOS.test(ub)) { pideDatos = true; flujo = hablaDeCambio ? 'cancelar_o_reprogramar' : 'agendar_nuevo'; }
      else if (RE_HORARIOS.test(ub)) { flujo = hablaDeCambio ? 'cancelar_o_reprogramar' : 'agendar_nuevo'; }
      if (flujo) { esElUltimo = (vistos === 1); break; }
    }
    if (flujo) {
      const limpio = textoNorm.replace(/[^a-z\s]/g, ' ').replace(/\b(muchas|gracias|por favor|porfa|pf)\b/g, ' ').replace(/\s+/g, ' ').trim();
      const afirma = esElUltimo && /^(si+|dale|ok|oka|okey|listo|perfecto|de una|confirmo|proceda|procede|claro|bueno|genial|si si|si dale)$/.test(limpio);
      const eligeHorario = /\b(lunes|martes|miercoles|jueves|viernes|sabado)\b|\ba las \d|\b\d{1,2}\s*(:|\.|y)\s*\d{2}\b|\b\d{1,2}\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b|\b(el|la)\s+(primero|primera|segundo|segunda|ultimo|ultima)\b|\b(ese|esa)\b|\b(por la|a la)\s+(manana|tarde)\b/.test(textoNorm);
      const preguntaDisponibilidad = /disponib|que (fecha|dia|horario)|hay (lugar|turno)|otra (fecha|semana)|otro (dia|horario)|mas (temprano|tarde)|esta semana|semana que viene|proxim/.test(textoNorm);
      const respondeDatos = esElUltimo && pideDatos && textoNorm.length > 2 && textoNorm.length < 220;
      if (afirma || eligeHorario || preguntaDisponibilidad || respondeDatos) {
        intent = flujo;
        continuidad = 'flujo_pendiente:' + flujo;
      }
    }
  }
} catch (e) { continuidad = null; }

return [{ json: { ...$input.first().json, intent, text, continuidad } }];