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
const esPedidoReprogramar = /\b(cambiar|reprogramar|mover|pasar|posponer|anular|cancelar)\b/.test(textoNorm) &&
  /\b(turnos?|cita|horarios?|fecha|dia|tarde|manana)\b/.test(textoNorm);

if (esPedidoReprogramar) {
  intent = 'cancelar_o_reprogramar';
} else {
  // FIX 2026-10-01 (caso anuncios de ads): pedido generico de info sin accion operativa
  const esPedidoGenericoInfo = /\b(quiero|necesito|quisiera|me\s+interesa|mas)\s+(mas\s+)?info(rmacion)?\b/.test(textoNorm);
  const tienePedidoOperativo = /\bturnos?\b|\bagend\w*|\breserv\w*|\bcancel\w*|\breprogram\w*|\bconfirm\w*/.test(textoNorm);
  if (esPedidoGenericoInfo && !tienePedidoOperativo) {
    intent = 'consulta_general';
  }
}

return [{ json: { ...$input.first().json, intent, text } }];