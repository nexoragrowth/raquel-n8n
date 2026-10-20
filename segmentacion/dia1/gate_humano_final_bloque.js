// Seg (2026-10-14 · Día 1 de la segmentación · scripts/apply_dia1_segmentacion.py): contacto silenciado por tipo → no se envía.
// Mira 'Seg: Tipo Salida' (contacto_ruta justo antes de enviar; por acá sale también el v7) y el interruptor seg:off leído a la entrada.
// FALLA ABIERTA: si la consulta o Redis fallaron, si no corrieron, o si seg:off existe, sigue exactamente como hoy. Sin aviso al grupo:
// la entrada ya avisó si correspondía (esto cubre un tipo puesto a mitad del proceso).
let segSilencia = false;
try {
  const segOff = $('Seg: Redis GET off');
  const off = segOff.isExecuted ? segOff.first().json.seg_off : undefined;
  const segTipo = $('Seg: Tipo Salida');
  const t = segTipo.isExecuted ? (segTipo.first().json || {}) : {};
  segSilencia = (off === null || off === '') && t.seg_silencia === true;
} catch (e) { segSilencia = false; }
if (segSilencia) {
  console.log('[SEG] salida bloqueada: contacto silenciado por tipo');
  return [];
}
