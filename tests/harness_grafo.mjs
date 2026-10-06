// harness_grafo.mjs — ejecuta un workflow de n8n (JSON generado en v7/workflows/) nodo por nodo, SIN red, siguiendo sus conexiones reales.
// Soporta los tipos que usa el v7: executeWorkflowTrigger, code, if (v2.2, boolean), redis (get/set/incr/delete/push/lrange en memoria), httpRequest (simulado por nombre),
// executeWorkflow (simulado por nombre), postgres (simulado por nombre), set, noOp. Reloj fijo. Registra pedidos HTTP, avisos al grupo, Redis final y el recorrido.
// uso: node harness_grafo.mjs <workflow.json> <escenarios.json>   → JSON con el resultado de cada escenario.
//   escenario = { id, trigger:{...}, ahora?, redis?:{clave:valor}, http?:{nodo: resp | [resp,...]}, subwf?:{nodo: resp}, pg?:{nodo: resp}, repeticiones?:n, redis_falla?:true }
//   Una respuesta http { __throw:true } simula un fallo de red (el nodo con continueOnFail devuelve {error:{message}}).
import fs from 'node:fs';
const [wfPath, escPath] = process.argv.slice(2);
const wf = JSON.parse(fs.readFileSync(wfPath, 'utf8'));
const escenarios = JSON.parse(fs.readFileSync(escPath, 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const byName = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
const RealDate = Date;
const relojFijo = (iso) => { const F = new RealDate(iso).getTime(); return class FakeDate extends RealDate { constructor(...a) { if (a.length === 0) super(F); else super(...a); } static now() { return F; } }; };

async function correrUna(esc, estadoCompartido, nRep) {
  const FakeDate = relojFijo(esc.ahora || '2026-10-05T12:36:00Z');
  const redis = estadoCompartido.redis;
  const salidas = {}; const orden = []; const pedidos = []; const avisos = [];
  const contHttp = estadoCompartido.contHttp;
  const evalExpr = (str, ctx) => {
    if (typeof str !== 'string' || !str.startsWith('=')) return str;
    if (str.startsWith('={{') && str.trim().endsWith('}}') && str.indexOf('}}') === str.lastIndexOf('}}')) {
      return new Function('$json', '$', '$execution', 'return (' + str.slice(3, str.lastIndexOf('}}')) + ')')(ctx.$json, ctx.$, { id: String(esc.exec_id || esc.trigger.exec_id_actual || 'ex') });
    }
    return str.slice(1).replace(/\{\{([\s\S]+?)\}\}/g, (_m, e) => { const v = new Function('$json', '$', '$execution', 'return (' + e + ')')(ctx.$json, ctx.$, { id: String(esc.exec_id || esc.trigger.exec_id_actual || 'ex') }); return typeof v === 'string' ? v : JSON.stringify(v); });
  };
  // Igual que n8n: un nodo que no corrió tiene isExecuted=false y tira error si se le pide un ítem.
  const $ = (nombre) => {
    if (!(nombre in salidas)) { const e = () => { throw new Error(`Referenced node is unexecuted: '${nombre}'`); }; return { first: e, all: e, last: e, isExecuted: false }; }
    return { first: () => salidas[nombre][0], all: () => salidas[nombre], isExecuted: true };
  };
  const helpers = { httpRequest: async (o) => { if (esc.aviso_falla) throw new Error('webhook caído'); avisos.push({ url: o.url, qs: o.qs || null, body: o.body || null }); return {}; } };

  async function ejecutar(nombre, entrada) {
    const n = byName[nombre]; if (!n) throw new Error('nodo inexistente: ' + nombre);
    orden.push(nombre);
    const ctx = { $json: entrada[0]?.json ?? {}, $ };
    const t = n.type.split('.').pop();
    let salida;
    if (t === 'executeWorkflowTrigger') salida = [{ json: esc.trigger }];
    else if (t === 'code') {
      const fn = new AsyncFunction('$input', '$', '$json', '$execution', 'console', 'Date', n.parameters.jsCode);
      const $input = { first: () => entrada[0], all: () => entrada, item: entrada[0] };
      salida = await fn.call({ helpers }, $input, $, ctx.$json, { id: String(esc.exec_id || esc.trigger.exec_id_actual || 'ex') }, { log() {} }, FakeDate);
    } else if (t === 'if') {
      const c = n.parameters.conditions.conditions[0];
      const v = evalExpr(c.leftValue, ctx);
      const ok = c.operator.operation === 'true' ? v === true : c.operator.operation === 'false' ? v === false : false;
      salidas[nombre] = entrada; return seguir(nombre, ok ? [entrada, []] : [[], entrada]);
    } else if (t === 'redis') {
      const p = n.parameters; const key = evalExpr(p.key, ctx);
      if (esc.redis_falla && ['incr', 'get', 'set'].includes(p.operation) && esc.redis_falla === p.operation) salida = [{ json: {} }];
      else if (p.operation === 'get') salida = [{ json: { [p.propertyName]: key in redis ? redis[key] : null } }];
      else if (p.operation === 'set') { redis[key] = evalExpr(p.value, ctx); salida = [{ json: { [key]: redis[key] } }]; }
      else if (p.operation === 'incr') { redis[key] = (Number(redis[key]) || 0) + 1; salida = [{ json: { [key]: redis[key] } }]; }
      else if (p.operation === 'delete') { delete redis[key]; salida = [{ json: { deleted: true } }]; }
      else if (p.operation === 'push') { (redis[key] = redis[key] || []).push(evalExpr(p.messageData, ctx)); salida = [{ json: { pushed: true } }]; }
      else throw new Error('redis op sin soporte: ' + p.operation);
    } else if (t === 'httpRequest') {
      salida = [];
      for (const it of entrada) {
        const c2 = { $json: it.json, $ };
        const url = evalExpr(n.parameters.url, c2);
        const body = n.parameters.jsonBody ? evalExpr(n.parameters.jsonBody, c2) : null;
        const q = n.parameters.queryParameters ? Object.fromEntries(n.parameters.queryParameters.parameters.map((x) => [x.name, evalExpr(x.value, c2)])) : null;
        pedidos.push({ nodo: nombre, metodo: n.parameters.method || 'GET', url, query: q, body: body ? JSON.parse(body) : null });
        const cfg = (esc.http || {})[nombre];
        const lista = Array.isArray(cfg) ? cfg : [cfg];
        const k = contHttp[nombre] = (contHttp[nombre] || 0); contHttp[nombre]++;
        const r = lista[Math.min(k, lista.length - 1)];
        if (r === undefined) throw new Error('sin respuesta simulada para ' + nombre);
        salida.push({ json: r && r.__throw ? { error: { message: 'network error' } } : r });
      }
    } else if (t === 'agent') {
      if (esc.agente === undefined) throw new Error('sin respuesta simulada para el agente ' + nombre);
      pedidos.push({ nodo: nombre, metodo: 'agent', url: null, entradas: { text: evalExpr(n.parameters.text, ctx), sistema: evalExpr(n.parameters.options.systemMessage, ctx) } });
      salida = [{ json: esc.agente }];
    } else if (t === 'executeWorkflow' || t === 'postgres') {
      const r = ((t === 'postgres' ? esc.pg : esc.subwf) || {})[nombre];
      if (r === undefined) throw new Error('sin respuesta simulada para ' + nombre);
      pedidos.push({ nodo: nombre, metodo: t, url: null, params: t === 'postgres' && n.parameters.options && n.parameters.options.queryReplacement ? evalExpr(n.parameters.options.queryReplacement, ctx) : null,
        entradas: t === 'executeWorkflow' ? Object.fromEntries(Object.entries(n.parameters.workflowInputs.value).map(([k, v]) => [k, evalExpr(v, ctx)])) : null });
      salida = (Array.isArray(r) ? r : [r]).map((j) => ({ json: j }));
    } else if (t === 'set') { salida = [{ json: { ...ctx.$json, ...Object.fromEntries((n.parameters.assignments?.assignments || []).map((a) => [a.name, evalExpr(a.value, ctx)])) } }]; }
    else if (t === 'noOp') salida = entrada;
    else throw new Error('tipo sin soporte en el harness: ' + n.type + ' (' + nombre + ')');
    if (!Array.isArray(salida) || !salida.length) throw new Error('el nodo ' + nombre + ' no devolvio items');
    salidas[nombre] = salida; return seguir(nombre, [salida]);
  }
  async function seguir(nombre, ramas) {
    const con = wf.connections[nombre]?.main ?? [];
    for (let i = 0; i < con.length; i++) { const items = ramas[i] ?? []; if (!items.length) continue; for (const d of con[i]) await ejecutar(d.node, items); }
  }
  let error = null;
  try { await ejecutar(Object.keys(byName).find((k) => byName[k].type.endsWith('executeWorkflowTrigger')), [{ json: esc.trigger }]); } catch (e) { error = String(e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e); }
  const ultimo = orden[orden.length - 1];
  return { rep: nRep, error, recorrido: orden, salida: salidas[ultimo]?.[0]?.json ?? null, pedidos, avisos };
}
const res = [];
for (const e of escenarios) {
  const compartido = { redis: JSON.parse(JSON.stringify(e.redis || {})), contHttp: {} };
  const reps = [];
  for (let i = 0; i < (e.repeticiones || 1); i++) reps.push(await correrUna(e, compartido, i + 1));
  res.push({ id: e.id, reps, redis_final: compartido.redis });
}
process.stdout.write(JSON.stringify(res));
