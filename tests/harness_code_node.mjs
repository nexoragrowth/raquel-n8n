// harness_code_node.mjs — corre el JS REAL de UN nodo Code de n8n con sus entradas simuladas. Sin red.
// uso: node harness_code_node.mjs <casos.json>
// caso = { id, codigo, input: {...json del item de entrada}, nodos: { "Nombre de nodo": {...json} }, ahora?: ISO }
// Un nodo que no esta en `nodos` se comporta como en n8n cuando no se ejecuto: $('X') tira error (el codigo vivo lo ataja con try/catch).
import fs from 'node:fs';
const casos = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const RealDate = Date;
const salida = [];
for (const c of casos) {
  const FIJO = new RealDate(c.ahora || '2026-10-05T12:36:00Z').getTime();
  class FakeDate extends RealDate { constructor(...a) { if (a.length === 0) super(FIJO); else super(...a); } static now() { return FIJO; } }
  const items = [{ json: c.input || {} }];
  const $input = { first: () => items[0], all: () => items, item: items[0] };
  const $ = (n) => {
    if (!c.nodos || !(n in c.nodos)) throw new Error(`Referenced node is unexecuted: '${n}'`);
    return { first: () => ({ json: c.nodos[n] }), all: () => [{ json: c.nodos[n] }], isExecuted: true };
  };
  try {
    const fn = new AsyncFunction('$input', '$', '$json', 'console', 'Date', c.codigo);
    const r = await fn.call({ helpers: {} }, $input, $, items[0].json, { log() {} }, FakeDate);
    salida.push({ id: c.id, json: r && r[0] ? r[0].json : null, n: r ? r.length : 0 });
  } catch (e) { salida.push({ id: c.id, error: String(e.message || e) }); }
}
process.stdout.write(JSON.stringify(salida));
