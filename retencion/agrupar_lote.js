// retencion/agrupar_lote.js — jsCode de "Pacientes: agrupar lote" y "Panel: agrupar lote" del satélite
// "Áurea — Retención" (scripts/create_retencion_satelite.py reemplaza __BUCKET__ por bucket; tests/test_retencion_y_staff.js
// corre este archivo tal cual).
//
// Entrada: N items del SELECT anterior ({id?, bucket?, path}); 1 item vacío si no había filas (alwaysOutputData);
//          {error} si el SELECT falló (onError continueRegularOutput).
// Salida: SIEMPRE 1 item {bucket, ids, paths, n, filas, omitidas, smoke, error} para que el DELETE de Storage haga UNA
//         sola llamada con la lista completa de paths (body {prefixes:[...]}) y el UPDATE marque los mismos ids.
// Smoke: si la corrida vino del webhook manual con body {"smoke": true}, se agrega un path inexistente a propósito
//        para ejercitar el DELETE (Storage responde 200 [] ante un objeto que no existe) sin tocar nada real.
const BUCKET = "__BUCKET__";
const items = $input.all().map(i => (i && i.json) || {});
const errItem = items.find(r => r && r.error);
const error = errItem ? String(typeof errItem.error === 'string' ? errItem.error : (errItem.error.message || JSON.stringify(errItem.error))).slice(0, 300) : null;
const filas = items.filter(r => r && typeof r.path === 'string' && r.path && (!r.bucket || r.bucket === BUCKET));
const omitidas = items.filter(r => r && r.path && r.bucket && r.bucket !== BUCKET).length;
let smoke = false;
try {
  const w = $('Webhook Manual Retención');
  smoke = !!(w.isExecuted && (((w.first().json || {}).body || {}).smoke === true));
} catch (e) { smoke = false; }
const paths = filas.map(r => r.path);
const ids = filas.filter(r => r.id).map(r => String(r.id));
if (smoke) paths.push('__retencion_smoke__/no-existe.bin');
return [{ json: { bucket: BUCKET, ids, paths, n: paths.length, filas: filas.length, omitidas, smoke, error } }];
