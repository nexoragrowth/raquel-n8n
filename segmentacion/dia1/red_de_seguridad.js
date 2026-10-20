// Seg: Red de seguridad (2026-10-14 · Día 1 de la segmentación · scripts/apply_dia1_segmentacion.py)
// Corre SOLO para un contacto silenciado por tipo (Seg: ¿Silenciar?[sí]). NUNCA le responde al contacto y NO se conecta al pipeline de
// respuesta ni al triaje (sus únicas salidas son Seg: ¿Avisar? → Seg: Redis INCR aviso → Seg: Avisar al grupo).
// Decide si hay que avisar al grupo: tipo con red (colega / proveedor / no_paciente; interno NUNCA: la Dra. escribe "dolor" hablando de
// pacientes) y señales FUERTES de urgencia. Las líneas de textoNorm y esUrgenciaFuerte son COPIA TEXTUAL del nodo vivo 'Parse Intent'
// (el script las extrae del nodo vivo y aborta si cambiaron): no hay regex nueva; fallan del lado seguro (avisar de más).
let tipo = null, conRed = false, phone = '', text = '';
try { const t = $('Seg: Consultar Tipo').first().json || {}; tipo = t.seg_tipo || null; conRed = t.seg_con_red === true; } catch (e) { conRed = false; }
try { const pm = $('Preparar Mensaje Final').first().json || {}; phone = (pm.phone || '').toString(); text = (pm.text || '').toString(); } catch (e) { text = ''; }
/*__COPIA_PARSE_INTENT__*/
const urgencia = esUrgenciaFuerte === true;
const avisar = conRed === true && tipo !== 'interno' && urgencia && phone !== '';
console.log('[SEG] silenciado por tipo:', tipo, '| urgencia fuerte:', urgencia, '| aviso al grupo:', avisar);
return [{ json: { _seg: 'silenciado', seg_tipo: tipo, seg_con_red: conRed, urgencia_fuerte: urgencia, avisar } }];
