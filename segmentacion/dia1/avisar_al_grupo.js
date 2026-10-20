// Seg: Avisar al grupo (2026-10-14 · Día 1 de la segmentación · scripts/apply_dia1_segmentacion.py)
// Un contacto silenciado (colega / proveedor / no_paciente) escribió algo con señales FUERTES de urgencia: el bot NO le respondió y avisa
// al grupo de derivaciones por el mecanismo existente (webhook notify-grupo → workflow "Helper - Notify Grupo": escalaciones_log + grupo).
// El texto va en el BODY (body.text) y NO en qs.resumen, a propósito: el Helper decide prender el modo humano mirando solo resumen/tomar
// (regex urgenc|dolor|sangr), así este aviso no toca human_takeover (el silencio por tipo no prende el modo humano). Sin tomar ni silencioso.
// SIN TOPE (plan §2.5: "una urgencia fuerte avisa siempre"): cada bloque de mensajes con urgencia fuerte avisa. El buffer ya junta la ráfaga
// en un solo bloque y el Rate Limit del v6 (10 mensajes / 15 min por teléfono) corre antes, así que no hay spam posible más allá de eso.
// Siempre devuelve 1 item (queda en la ejecución para verificar por GET); si el aviso falla, el contacto sigue silenciado y el mensaje está en el panel.
let phone = '', text = '', tipo = '', desde = '', puestoPor = '';
try { const pm = $('Preparar Mensaje Final').first().json || {}; phone = (pm.phone || '').toString(); text = (pm.text || '').toString(); } catch (e) { phone = ''; }
try {
  const t = $('Seg: Consultar Tipo').first().json || {};
  tipo = t.seg_tipo || ''; desde = (t.seg_desde || '').toString(); puestoPor = (t.seg_puesto_por || '').toString();
} catch (e) { tipo = ''; }
if (!phone) return [{ json: { avisado: false, aviso_error: 'sin_telefono' } }];
let fecha = '';
const ms = Date.parse(desde);
if (Number.isFinite(ms)) { const d = new Date(ms - 3 * 3600 * 1000).toISOString(); fecha = d.slice(8, 10) + '/' + d.slice(5, 7); }   // hora de Argentina (UTC-3)
const quien = puestoPor ? puestoPor.charAt(0).toUpperCase() + puestoPor.slice(1) : '';
const detalle = [fecha ? 'desde el ' + fecha : '', quien ? 'lo marcó ' + quien : ''].filter(Boolean).join(', ');
const plano = text.replace(/\s+/g, ' ').trim();
const recorte = plano.length > 220 ? plano.slice(0, 220) + '…' : plano;
const resumen = 'Contacto silenciado (' + (tipo || 'sin tipo') + (detalle ? ', ' + detalle : '') + ') escribió: «' + recorte + '». '
  + 'El bot NO le respondió. Si es paciente o necesita atención, contestale vos desde el WhatsApp de la clínica y pedí que le quiten la marca de '
  + (tipo || 'silenciado') + ' para que Asiri vuelva a atenderlo.';
let avisado = false, aviso_error = null;
try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
    qs: { phone: phone },
    body: { text: resumen },
    json: true,
    timeout: 15000,
  });
  avisado = true;
} catch (e) {
  aviso_error = String((e && e.message) || e).slice(0, 200);
  console.log('[SEG] aviso al grupo falló:', aviso_error);
}
return [{ json: { avisado, aviso_error } }];
