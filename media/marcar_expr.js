(() => {
  const p = $('Media: Preparar').first().json || {};
  let base = (typeof p.text === 'string') ? p.text : '';
  // Blindaje: si "Media: Preparar" falló FUERA de su try/catch (kill del sandbox / timeout del runner), n8n con
  // onError=continue emite {error} SIN `text` y el marcador se perdería (al Router llegaría un mensaje vacío).
  // Se rescata del Set Marker que corrió: uno solo por ejecución; los otros tres no ejecutaron y $() tira.
  if (!base && p.text === undefined) {
    for (const n of ['Set Marker Audio', 'Set Marker Imagen', 'Set Marker Documento', 'Set Marker Otros']) {
      try { const t = $(n).first().json.text; if (typeof t === 'string' && t) { base = t; break; } } catch (e) { /* no ejecutó */ }
    }
  }
  const registrado = p.hay_archivo === true && !!$json && !$json.error && $json.bucket === 'pacientes-media' && !!$json.id && $json.id === p.id;
  return registrado ? base + ' [MEDIA:' + p.id + ']' : base;
})()
