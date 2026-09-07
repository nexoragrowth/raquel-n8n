// retencion/armar_aviso.js — jsCode de "Armar aviso" del satélite "Áurea — Retención". Le avisa a Lucas por WhatsApp
// SOLO si algo falló o dejó una advertencia (Storage no encontró ninguno de los paths pedidos, ver resumen.js); una
// corrida limpia no manda nada: el log queda en retencion_log. __LUCAS__ lo reemplaza el script.
// Entrada: los items que devolvió "Registrar retencion_log" (uno por fila; con {error} si el INSERT falló).
const filas = (() => { try { return $('Resumen').all().map(i => (i && i.json) || {}); } catch (e) { return []; } })();
const insertErr = $input.all().map(i => (i && i.json) || {}).find(j => j && j.error);
const fallas = filas.filter(f => Number(f.fallidos) > 0);
const advertencias = filas.filter(f => !(Number(f.fallidos) > 0) && f.advertencia);
if (!fallas.length && !advertencias.length && !insertErr) return [];
const lineas = fallas.map(f => `• ${f.bucket}: ${f.fallidos} fallido(s), ${f.borrados} borrado(s)${f.detalle ? ' — ' + f.detalle : ''}`);
for (const f of advertencias) lineas.push(`• ${f.bucket}: ${f.borrados} borrado(s) — ⚠ ${f.advertencia}`);
if (insertErr) {
  const e = insertErr.error;
  lineas.push('• retencion_log: no se pudo escribir el log (' + String(typeof e === 'string' ? e : (e.message || JSON.stringify(e))).slice(0, 160) + ')');
}
const titulo = (fallas.length || insertErr) ? 'la limpieza nocturna tuvo problemas:' : 'la limpieza nocturna terminó con una advertencia:';
const texto = '🧹 *Retención Áurea* — ' + titulo + '\n\n' + lineas.join('\n') +
  '\n\nRevisar la ejecución en n8n (workflow "Áurea — Retención") y la tabla retencion_log.';
return [{ json: { texto, numero: "__LUCAS__" } }];
