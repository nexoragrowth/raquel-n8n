// retencion/resumen.js — jsCode de "Resumen" del satélite "Áurea — Retención". Junta las 3 etapas en 3 filas para
// retencion_log (una por bucket/tabla) y marca hubo_fallo. __DIAS_*__ los reemplaza scripts/create_retencion_satelite.py.
//
// Regla (R7 del diseño): la respuesta del DELETE de Storage trae SOLO los objetos que existían; un path ya inexistente no
// es error. Por eso "borrado" = el DELETE respondió 200 para el lote entero (y así también se marca borrado_at en todas
// las filas pedidas; si no, las huérfanas se reintentarían cada noche para siempre).
// Advertencia (no fallo): si había filas reales y Storage no devolvió NINGUNA, lo más probable es que `path` no coincida
// con `storage.objects.name` (encoding, prefijo) → borrado_at se marcó igual y los blobs quedarían huérfanos contando en
// el plan. Se avisa a Lucas (armar_aviso.js) sin contarlo como fallido, para no bloquear el caso legítimo de huérfanos.
const DIAS = { 'pacientes-media': __DIAS_MEDIA_PACIENTES__, 'panel-media': __DIAS_PANEL_MEDIA__, 'mensajes_entrantes_live': __DIAS_INBOX_LIVE__ };
function salida(nombre) {
  try { const n = $(nombre); if (!n.isExecuted) return null; return (n.first() || {}).json || {}; } catch (e) { return null; }
}
const errTxt = (e) => String(typeof e === 'string' ? e : ((e && e.message) || JSON.stringify(e))).slice(0, 200);
function etapaStorage(bucket, nomAgrupar, nomBorrar, nomMarcar) {
  const a = salida(nomAgrupar) || {};
  const d = salida(nomBorrar);
  const notas = [];
  let borrados = 0, fallidos = 0, advertencia = null;
  if (a.error) { notas.push('SELECT falló: ' + a.error); fallidos += 1; }
  const n = Number(a.n) || 0, reales = Number(a.filas) || 0, ids = Array.isArray(a.ids) ? a.ids : [];
  // El smoke agrega 1 path fantasma que Storage nunca va a devolver: no cuenta entre los esperados.
  const esperados = Math.max(0, n - (a.smoke ? 1 : 0));
  if (n > 0) {
    const st = d ? Number(d.statusCode) : 0;
    const ok = !!d && st === 200 && !d.error;
    if (ok) {
      borrados = reales;
      const devueltos = Array.isArray(d.body) ? d.body.length : null;
      if (devueltos !== null && esperados > 0 && devueltos !== esperados) notas.push(`Storage devolvió ${devueltos} de ${esperados} (el resto ya no existía)`);
      if (devueltos === 0 && esperados > 0) {
        advertencia = `Storage no encontró NINGUNO de los ${esperados} path(s) pedidos en ${bucket}: revisar que media_entrantes.path coincida con storage.objects.name (borrado_at se marcó igual; los archivos pueden haber quedado huérfanos)`;
      }
    } else {
      fallidos += Math.max(reales, 1);
      notas.push('DELETE Storage: ' + (d ? ('HTTP ' + (d.statusCode || '?') + ' ' + errTxt(d.body || d.error || '')) : 'no ejecutó'));
    }
    // El UPDATE de borrado_at solo se exige cuando había ids reales que marcar. Con ids vacío (smoke sin vencidos, o
    // filas de otro bucket) el nodo corre igual con '-' como $1 (marca 0) y su resultado no cuenta como fallo.
    if (nomMarcar && ok && ids.length > 0) {
      const m = salida(nomMarcar);
      const marcados = m ? Number(m.marcados) : NaN;
      if (!(marcados >= 0)) { fallidos += 1; notas.push('UPDATE borrado_at: ' + (m && m.error ? errTxt(m.error) : 'sin respuesta')); }
      else if (marcados !== ids.length) notas.push(`borrado_at marcado en ${marcados} de ${ids.length} filas`);
    } else if (nomMarcar && ok) {
      const m = salida(nomMarcar);
      if (m && m.error) notas.push('UPDATE borrado_at (sin ids que marcar) respondió error: ' + errTxt(m.error));
    }
  }
  if (a.omitidas) notas.push(`${a.omitidas} fila(s) de otro bucket omitidas`);
  if (a.smoke) notas.push('smoke: incluyó un path inexistente a propósito');
  if (advertencia) notas.push('⚠ ' + advertencia);
  return { bucket, dias: DIAS[bucket], borrados, fallidos, advertencia, detalle: [`> ${DIAS[bucket]} días`].concat(notas).join(' · ') };
}
const pacientes = etapaStorage('pacientes-media', 'Pacientes: agrupar lote', 'Pacientes: borrar en Storage', 'Pacientes: marcar borrado_at');
const panel = etapaStorage('panel-media', 'Panel: agrupar lote', 'Panel: borrar en Storage', null);
const b = salida('Bandeja: purgar');
const bandeja = { bucket: 'mensajes_entrantes_live', dias: DIAS['mensajes_entrantes_live'],
  borrados: b && !b.error ? (Number(b.borrados) || 0) : 0,
  fallidos: !b || b.error ? 1 : 0,
  advertencia: null,
  detalle: `> ${DIAS['mensajes_entrantes_live']} días` + (!b ? ' · DELETE no ejecutó' : (b.error ? ' · DELETE falló: ' + errTxt(b.error) : '')) };
const filas = [pacientes, panel, bandeja];
const hubo_fallo = filas.some(f => f.fallidos > 0);
return filas.map(f => ({ json: { ...f, hubo_fallo } }));
