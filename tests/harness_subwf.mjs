// harness_subwf.mjs — reproduce el sub-WF "CancelarReprogramar" ejecutando el JS REAL de sus nodos Code, siguiendo sus conexiones reales.
// SIN RED. Simulado por escenario: memoria (Postgres), agenda (respuestas de Dentalink), los 2 LLM (parser de intencion y de aceptacion) y el
// sub-WF de horarios. El reloj esta fijo (escenario.ahora) para que el resultado no dependa del dia en que se corre.
// Registra TODO lo que el flujo escribiria afuera: POST /citas, PUT /citas/{id}, avisos al grupo y filas de memoria.
// uso: node harness_subwf.mjs <subwf.json> <escenarios.json>   → imprime un JSON con el resultado de cada escenario.
import fs from 'node:fs';
const [wfPath, escPath] = process.argv.slice(2);
const wf = JSON.parse(fs.readFileSync(wfPath, 'utf8'));
const escenarios = JSON.parse(fs.readFileSync(escPath, 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const byName = Object.fromEntries(wf.nodes.map((n) => [n.name, n]));
const RealDate = Date;

function relojFijo(iso) {
  const FIJO = new RealDate(iso).getTime();
  return class FakeDate extends RealDate {
    constructor(...a) { if (a.length === 0) super(FIJO); else super(...a); }
    static now() { return FIJO; }
  };
}

async function correr(esc) {
  const FakeDate = relojFijo(esc.ahora || '2026-10-05T12:36:00Z');
  const salidas = {};
  const escrituras = [];
  const horariosPedidos = [];
  const orden = [];
  const evalVal = (str, ctx) => {
    if (typeof str !== 'string' || !str.startsWith('=')) return str;
    if (str.startsWith('={{') && str.trim().endsWith('}}')) {
      const e = str.slice(3, str.lastIndexOf('}}'));
      return new Function('$json', '$', 'return (' + e + ')')(ctx.$json, ctx.$);
    }
    return str.slice(1).replace(/\{\{([\s\S]+?)\}\}/g, (_m, e) => {
      const v = new Function('$json', '$', 'return (' + e + ')')(ctx.$json, ctx.$);
      return typeof v === 'string' ? v : JSON.stringify(v);
    });
  };
  const $ = (nombre) => {
    if (!(nombre in salidas)) throw new Error(`Referenced node is unexecuted: '${nombre}'`);
    return { first: () => salidas[nombre][0], all: () => salidas[nombre], isExecuted: true };
  };
  const helpers = { httpRequest: async (o) => { escrituras.push({ tipo: 'aviso-grupo (Step 7)', resumen: (o.qs && o.qs.resumen) || null }); return {}; } };
  const llm = (obj) => [{ json: { choices: [{ message: { content: typeof obj === 'string' ? obj : JSON.stringify(obj) } }] } }];

  async function ejecutar(nombre, entrada) {
    const n = byName[nombre];
    if (!n) throw new Error('nodo inexistente: ' + nombre);
    orden.push(nombre);
    const ctx = { $json: entrada[0]?.json ?? {}, $ };
    const t = n.type.split('.').pop();
    let salida;
    if (t === 'executeWorkflowTrigger') salida = [{ json: esc.trigger }];
    else if (nombre === 'Step 0a: Read Chat Memory') salida = (esc.memoria && esc.memoria.length) ? esc.memoria.map((m) => ({ json: m })) : [{ json: {} }];
    else if (t === 'code') {
      const fn = new AsyncFunction('$input', '$', '$json', 'console', 'Date', n.parameters.jsCode);
      const $input = { first: () => entrada[0], all: () => entrada, item: entrada[0] };
      salida = await fn.call({ helpers }, $input, $, ctx.$json, { log() {} }, FakeDate);
    } else if (nombre === 'Step 1a: Buscar full') salida = [{ json: esc.dentalink_caido ? { error: { message: 'timeout' } } : esc.dentalink.paciente }];
    else if (nombre === 'Step 2a: Ver Turnos') salida = [{ json: esc.dentalink.citas }];
    else if (nombre === 'Step 3a: LLM Extract Intent') salida = llm(esc.llm_intent);
    else if (nombre === 'Step 3.5b: LLM Acceptance') salida = llm(esc.llm_aceptacion ?? { accepts: false, slot_chosen: null, razon: 'stub' });
    else if (nombre === 'Step 6b: Buscar Horarios (bloque)') {
      const desde = String(ctx.$json.desde || '');
      horariosPedidos.push(desde);
      const bloques = esc.bloques || {};
      const bloque = bloques['desde_' + (desde || 'hoy')] ?? bloques.default ?? '';
      salida = [{ json: bloque ? { bloque, total_manana: 2, total_tarde: 2, siguiente_desde: '' } : {} }];
    } else if (nombre === 'Step 6d-1: POST Reservar') {
      const body = JSON.parse(evalVal(n.parameters.jsonBody, ctx));
      escrituras.push({ tipo: 'POST /citas', body });
      salida = [{ json: esc.dentalink_rechaza_reserva ? { error: { message: '400 - horario no disponible' } } : { data: { id: 99001, id_estado: 7, ...body } } }];
    } else if (nombre === 'Step 6d-3a: PUT Cancelar Viejo' || nombre === 'Step 6a: Cancelar en Dentalink') {
      const url = evalVal(n.parameters.url, ctx);
      const body = JSON.parse(evalVal(n.parameters.jsonBody, ctx));
      escrituras.push({ tipo: 'PUT ' + url.replace(/^.*\/api\/v1/, ''), body });
      salida = [{ json: esc.dentalink_rechaza_cancel ? { error: { message: '400' } } : { data: { id_estado: 1 } } }];
    } else if (nombre === 'Step 6c: POST Helper') {
      escrituras.push({ tipo: 'aviso-grupo (escalacion 6c)', resumen: ctx.$json.escalate_body?.text ?? null });
      salida = [{ json: {} }];
    } else if (t === 'postgres') salida = entrada;
    else if (t === 'switch') {
      const reglas = n.parameters.rules.values;
      const v = evalVal(reglas[0].conditions.conditions[0].leftValue, ctx);
      let idx = reglas.findIndex((r) => r.conditions.conditions[0].rightValue === v);
      if (idx < 0) idx = reglas.length;
      const ramas = Array.from({ length: reglas.length + 1 }, () => []);
      ramas[idx] = entrada;
      salidas[nombre] = entrada;
      return seguir(nombre, ramas);
    } else if (t === 'if') {
      const c = n.parameters.conditions.conditions[0];
      const ok = Number(evalVal(c.leftValue, ctx)) > Number(c.rightValue);
      salidas[nombre] = entrada;
      return seguir(nombre, ok ? [entrada, []] : [[], entrada]);
    } else throw new Error('tipo de nodo sin soporte en el harness: ' + n.type + ' (' + nombre + ')');
    if (!Array.isArray(salida) || !salida.length) throw new Error('el nodo ' + nombre + ' no devolvio items');
    salidas[nombre] = salida;
    return seguir(nombre, [salida]);
  }
  async function seguir(nombre, ramas) {
    const con = wf.connections[nombre]?.main ?? [];
    for (let i = 0; i < con.length; i++) {
      const items = ramas[i] ?? [];
      if (!items.length) continue;
      for (const d of con[i]) await ejecutar(d.node, items);
    }
  }
  let error = null;
  try { await ejecutar('When called by v6', [{ json: esc.trigger }]); } catch (e) { error = String(e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e); }
  const j = (nombre) => salidas[nombre]?.[0]?.json ?? null;
  const s0 = j('Step 0b: Detect Multi-Turn State') || {};
  const s5 = j('Step 5: Decidir Accion Ejecutable') || {};
  const s8a = j('Step 8a: Prep Memory Writeback');
  const fin = j('Step 8d: Return Output') ?? j('Step 7: Output Final');
  return {
    id: esc.id, error,
    recorrido: orden,
    estado: s0.multi_turn_state ?? null,
    bloques_ofrecidos: s0.bloques_ofrecidos ?? null,
    readback_accept: s0.readback_accept ?? null,
    intent: j('Step 3b: Parse Intent')?.intent ?? null,
    aceptacion: j('Step 3.5c: Parse Acceptance')?.acceptance_intent ?? null,
    decision: j('Step 4: Identificar Turno + Decision')?.decision ?? null,
    accion: s5.action_to_execute ?? null,
    descarte: s5.descarte_aceptacion ?? ((s5.acceptance_intent && /^descartada/.test(String(s5.acceptance_intent.razon || ''))) ? s5.acceptance_intent.razon : null),
    escrituras, horarios_pedidos: horariosPedidos,
    mensaje: fin?.mensaje_final ?? null,
    apply_label_humano: fin?.apply_label_humano ?? null,
    memoria_escrita: s8a ? [JSON.parse(s8a.message_json), JSON.parse(s8a.ai_message_json)] : null,
    cuerpos_llm: { intent: j('Step 3.0: Prep LLM Body')?.openai_body ?? null, aceptacion: j('Step 3.5a: Prep Acceptance LLM')?.accept_openai_body ?? null },
  };
}
const res = [];
for (const e of escenarios) res.push(await correr(e));
process.stdout.write(JSON.stringify(res));
