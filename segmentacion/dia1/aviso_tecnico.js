// Seg: Aviso técnico (2026-10-14 · Día 1 de la segmentación · scripts/apply_dia1_segmentacion.py · plan §2.5 "Si la función falla")
// Corre SOLO si 'Seg: Consultar Tipo' terminó con error (rama terminal, en paralelo y DESPUÉS del camino normal: el bot ya respondió como hoy,
// falla abierta). Avisa al GRUPO de la clínica (después de febrero no hay quien lo mire a mano) que la segmentación no está rigiendo.
// Tope fijo: 1 aviso cada 6 h. 'Seg: Redis GET falla' leyó seg:falla; si existe, ya se avisó → no hace nada. Si el POST sale bien, devuelve
// 1 item y 'Seg: Redis SET falla' escribe seg:falla con TTL fijo (no se renueva). Si el POST falla devuelve [] (no se marca: reintenta con el
// próximo mensaje). Si Redis falló, avisa igual (del lado seguro). Sin teléfono ni texto del contacto: no es un aviso sobre un paciente.
let ya = null;
try { const j = $input.first().json || {}; ya = j.seg_falla === undefined ? null : j.seg_falla; } catch (e) { ya = null; }
if (ya !== null && ya !== '') {
  console.log('[SEG] aviso técnico omitido: ya se avisó en las últimas 6 h');
  return [];
}
let detalle = '';
try { detalle = String(($('Seg: Consultar Tipo').first().json || {}).error || ''); } catch (e) { detalle = ''; }
detalle = detalle.replace(/[0-9]{7,}/g, '…').replace(/\s+/g, ' ').slice(0, 120);
const texto = 'Aviso técnico de Asiri: no se pudo leer la lista de contactos silenciados' + (detalle ? ' (' + detalle + ')' : '') + '. '
  + 'Mientras dure, Asiri les responde a todos como antes, también a la Dra., colegas y proveedores. '
  + 'Avisale a quien administra Asiri. Si sigue, este aviso se repite cada 6 horas.';
try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
    body: { text: texto },
    json: true,
    timeout: 15000,
  });
} catch (e) {
  console.log('[SEG] aviso técnico falló:', String((e && e.message) || e).slice(0, 200));
  return [];
}
return [{ json: { aviso_tecnico: true } }];
