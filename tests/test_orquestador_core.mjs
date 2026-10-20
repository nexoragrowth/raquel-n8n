// test_orquestador_core.mjs — v7 con ORQUESTADOR + SUB-AGENTES (08/10): despacho, salida de cada sub-agente y composición del mensaje, offline y sin modelo.
// Las respuestas del modelo se simulan; lo que se prueba es el CÓDIGO: que el orquestador no redacte, que el texto venga de las herramientas, el orden fijo,
// el read-back al final, urgencias, fuera de alcance, saludo, cierre y el "sí" que llega a Turnos por estado. uso: node tests/test_orquestador_core.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const O = require('../v7/orquestador_core.js');
const Clin = require('../v7/clinica_core.js');
let fallas = 0, total = 0;
const t = (n, c, x) => { total++; if (!c) { fallas++; console.log(`  FALLA ${n}${x !== undefined ? ' → ' + JSON.stringify(x).slice(0, 400) : ''}`); } else console.log(`  ok    ${n}`); };
const orq = (pasos) => ({ text: JSON.stringify({ pasos }) });
const paso = (tool, obs, input) => ({ action: { tool, toolInput: input || {} }, observation: JSON.stringify(obs) });

const RB = 'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?';
const EXITO = 'Listo, quedó reprogramado su turno: anulé el del viernes 16/10 a las 09:10 y le reservé el jueves 22/10 a las 09:20.';
const BLOQUE = 'Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n\nLe sirve alguno?';
const DATOS = 'Alias: dra.raquel.aurea\nTitular: Laura Raquel Rodríguez';

console.log('DESPACHO (el orquestador decide; el código despacha)');
{ const p = O.despachar(orq([{ a: 'turnos', pedido: 'cambiar el turno del jueves' }, { a: 'pagos', pedido: 'pide el alias' }]), {});
  t('O1 multi-pedido en un mensaje ("pasar el turno del jueves y pásame el alias"): turnos Y pagos', p.turnos === 'cambiar el turno del jueves' && p.pagos === 'pide el alias' && !p.fija && p.hay_agentes, p);
  const p2 = O.despachar(orq([{ a: 'turnos', pedido: 'cambiar el de la nena' }, { a: 'turnos', pedido: 'cancelar el mío' }]), {});
  t('O2 (B6) el mismo agente dos veces → UNA sola llamada con los dos pedidos juntos', p2.turnos === 'cambiar el de la nena / cancelar el mío', p2);
  const p3 = O.despachar(orq([{ a: 'menu_bienvenida' }]), {});
  t('O3 saludo → menú (acción fija, sin agentes)', p3.fija === 'menu' && !p3.hay_agentes, p3);
  const p4 = O.despachar(orq([{ a: 'no_reply' }]), {});
  t('O4 cierre ("gracias", sin nada pendiente) → no_reply: lo decide el orquestador, no una regex', p4.fija === 'no_reply' && !p4.hay_agentes, p4);
  const p5 = O.despachar(orq([{ a: 'no_reply' }]), { prop_pendiente: true });
  t('O5 (B3) con una confirmación pendiente VISTA, Turnos ve el mensaje igual (ruteo por ESTADO): "👍" que el orquestador tomó por cierre no mata la propuesta', p5.turnos === 'responde a la confirmación pendiente' && p5.turnos_por_estado === true && p5.fija === 'no_reply', p5);
  const p6 = O.despachar(orq([{ a: 'pasar_a_humano', cita: 'q me atienda la seño' }, { a: 'turnos', pedido: 'x' }]), { prop_pendiente: true });
  t('O6 pidió una persona: modo humano, sin agentes (ni siquiera Turnos por estado)', p6.fija === 'humano' && !p6.turnos && p6.cita === 'q me atienda la seño', p6);
  const p7 = O.despachar(orq([{ a: 'derivar_secretaria', cita: 'presupuesto en dólares', motivo: 'dólares' }, { a: 'turnos', pedido: 'sacar turno' }]), {});
  t('O7 fuera de alcance + algo en alcance en el mismo mensaje: deriva Y atiende lo de turnos', p7.fija === 'derivar' && p7.turnos === 'sacar turno' && p7.cita === 'presupuesto en dólares', p7);
  const p8 = O.despachar({ text: 'Hola! Claro, le busco un turno 😊' }, {});
  t('O8 el orquestador escribe texto libre (no JSON): se DESCARTA, nunca llega al paciente (falla técnica)', p8.fallo_orquestador === true && !p8.hay_agentes, p8);
  const p9 = O.despachar({ error: 'timeout' }, { prop_pendiente: true });
  t('O9 el orquestador se cae con una confirmación pendiente: Turnos igual ve el mensaje', p9.fallo_orquestador === true && p9.turnos === 'responde a la confirmación pendiente', p9);
  const p10 = O.despachar(orq([{ a: 'charla', pedido: 'contarle un chiste' }]), {});
  t('O10 un "agente" que no existe se descarta y queda no_entendi (que cuenta para la insistencia)', p10.fija === 'no_entendi' && p10.descartados[0] === 'charla' && p10.contar_no_entendi === true, p10);
  const p11 = O.despachar({ text: '```json\n{"pasos":[{"a":"informacion","pedido":"horario del lunes"}]}\n```' }, {});
  t('O11 JSON dentro de un bloque de código: se lee igual', p11.informacion === 'horario del lunes', p11);
  const p12 = O.despachar(orq([{ a: 'menu_bienvenida' }, { a: 'informacion', pedido: 'precio' }]), {});
  t('O12 menú + un agente: no hay menú (solo cuando no hay otro agente)', p12.fija === null && p12.informacion === 'precio', p12);
  const p13 = O.despachar(orq([{ a: 'pedir_texto' }]), {});
  t('O13 (B5) audio → pedir_texto (frase fija)', p13.fija === 'pedir_texto', p13); }

console.log('\nTURNOS (el texto sale de las herramientas; el modelo devuelve un código)');
{ const s1 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: true, bloque: BLOQUE })] }, {});
  t('T1 quiere turno → el bloque de la herramienta tal cual', s1.texto === BLOQUE && s1.estado === 'bloque_ofrecido', s1);
  const s2 = O.salidaTurnos({ output: 'Perfecto, ¡ya casi! ' + RB + ' Avíseme 😊', intermediateSteps: [paso('buscar_horarios', { ok: true, bloque: BLOQUE }), paso('gestionar_turno', { etapa: 'confirmacion', ok: true, texto_para_el_paciente: RB })] }, {});
  t('T2 (crítica eng. #1) el modelo parafrasea: se descarta su texto y va el read-back del código SOLO (sin el bloque)', s2.texto === RB && s2.readback === true && s2.estado === 'readback_pendiente' && !!s2.texto_libre_descartado, s2);
  const s3 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { etapa: 'ejecutado', ok: true, texto_para_el_paciente: EXITO })] }, {});
  t('T3 "ya" con confirma → el texto de éxito de la ejecución', s3.texto === EXITO && s3.estado === 'escrito_ok', s3);
  const s4 = O.salidaTurnos({ output: 'PREGUNTA_PARA_QUIEN', intermediateSteps: [] }, {});
  t('T4 pregunta mínima de la lista cerrada (B6): "¿Para quién es el turno? (nombre o DNI)"', s4.texto === '¿Para quién es el turno? (nombre o DNI)' && s4.estado === 'pregunta', s4);
  const s5 = O.salidaTurnos({ output: 'PREGUNTA_CUAL_TURNO' }, { turnos: ['viernes 16/10 a las 09:10', 'miércoles 4/11 a las 09:10'] });
  t('T5 "¿Cuál de estos turnos?" con la lista armada por código (Turnos no escribe fechas)', s5.texto === '¿Cuál de estos turnos?\n- viernes 16/10 a las 09:10\n- miércoles 4/11 a las 09:10', s5);
  const s6 = O.salidaTurnos({ output: 'MOSTRAR_TURNOS' }, { turnos: ['viernes 16/10 a las 09:10'] });
  t('T6 "¿cuándo es mi turno?" → lo dice el código con los turnos de la agenda', s6.texto === 'Su turno vigente es el viernes 16/10 a las 09:10.', s6);
  const s7 = O.salidaTurnos({ output: 'FUERA_DE_ALCANCE' }, {});
  t('T7 FUERA_DE_ALCANCE: sin texto, marcado (el cerebro deriva)', s7.fuera_de_alcance === true && !s7.texto, s7);
  const s8 = O.salidaTurnos({ output: 'Le cuento que el turno quedó listo para el martes 4/11 a las 10:00.' }, {});
  t('T8 texto libre sin herramienta ni código: NO llega al paciente', !s8.texto && s8.texto_libre_descartado, s8);
  const s9 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: false, motivo: 'sin_turnos' }, { desde: '2026-10-22', hasta: '2026-10-22' }), paso('buscar_horarios', { ok: true, bloque: BLOQUE }, { desde: '2026-10-22' })] }, {});
  t('T9 (I1) "pal jueves" sin lugar ese día: texto fijo + el bloque siguiente', s9.texto === 'Para ese día no hay turnos disponibles.\n\n' + BLOQUE, s9);
  const s9c = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: false, motivo: 'sin_turnos' }, { desde: '2026-10-20', hasta: '2026-10-27' }), paso('buscar_horarios', { ok: true, bloque: BLOQUE }, {})] }, {});
  t('T9c (vivo 318973) búsqueda vacía de un RANGO (no pidió un día) + bloque: sin "Para ese día no hay…", solo el bloque', s9c.texto === BLOQUE, s9c.texto);
  const s10 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { etapa: 'error', ok: false, motivo: 'menos_48h' })] }, {});
  t('T10 turno en menos de 48 h: texto fijo y pedido de derivación (lo resuelve la secretaria)', /menos de 48 horas/.test(s10.texto) && !!s10.derivar, s10);
  const s11 = O.salidaTurnos({ error: 'Agent stopped due to max iterations' }, {});
  t('T11 el agente se cae sin herramientas: error técnico (el cerebro lo resuelve con el libro o con un texto honesto)', s11.error_tecnico === true && !s11.texto, s11);
  const s12 = O.salidaTurnos({ output: '[NO_REPLY]' }, {});
  t('T12 "ok, lo pienso" a la confirmación: Turnos no hace nada ([NO_REPLY])', s12.estado === 'no_reply' && !s12.texto, s12);
  const s13 = O.salidaTurnos({ output: 'URGENCIA' }, {});
  t('T13 (B4 capa b) Turnos ve una urgencia en el mensaje → la marca', s13.urgencia === true, s13);
  const s14 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('confirmar_turno', { ok: true, readback_text: 'Perfecto, su turno del viernes 16/10 a las 09:10 está confirmado.' })] }, {});
  t('T14 confirma asistencia → texto de confirmar_turno', s14.texto === 'Perfecto, su turno del viernes 16/10 a las 09:10 está confirmado.' && s14.estado === 'confirmado', s14);
  const s15 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { etapa: 'error', ok: false, motivo: 'dni_no_escrito', texto_para_el_paciente: 'Para registrarlo me falta el DNI del paciente.' })] }, {});
  t('T15 faltan datos del paciente nuevo → el texto fijo de la herramienta', s15.texto === 'Para registrarlo me falta el DNI del paciente.', s15); }

console.log('\nPAGOS, INFORMACIÓN y URGENCIAS');
{ const p1 = O.salidaPagos({ output: '[LISTO]', intermediateSteps: [paso('registrar_pago', { ok: true, texto_para_el_paciente: Clin.TEXTOS.PAGO })] });
  t('G1 "ya le giré lo d la consulta" → recepción fija (sin preguntas)', p1.texto === Clin.TEXTOS.PAGO && p1.estado === 'pago_anotado' && !/\?/.test(p1.texto), p1);
  const p2 = O.salidaPagos({ output: 'Le paso el alias: dra.raquel.aurea', intermediateSteps: [paso('datos_pago', { ok: true, datos_pago: true, texto_para_el_paciente: Clin.TEXTOS.DATOS_PAGO })] });
  t('G2 "pasame el alia" → "Le paso los datos para transferir:" y la marca; el alias que escribió el modelo se descarta', p2.texto === Clin.TEXTOS.DATOS_PAGO && p2.datos_pago === true && !p2.texto.includes('dra.raquel'), p2);
  const p3 = O.salidaPagos({ output: '[LISTO]', intermediateSteps: [paso('datos_pago', { ok: false, fuera_de_alcance: true, motivo: 'otra_moneda' })] });
  t('G3 dólares → fuera de alcance (deriva el cerebro)', p3.fuera_de_alcance === true && !p3.texto, p3);
  const i1 = O.salidaInformacion({ text: 'La primera consulta tiene un valor de $50.000.' });
  t('I1 Información redacta con los DATOS (el único que redacta)', i1.texto === 'La primera consulta tiene un valor de $50.000.' && i1.estado === 'respondido', i1);
  const i2 = O.salidaInformacion({ text: 'FUERA_DE_ALCANCE' });
  t('I2 Información fuera de alcance', i2.fuera_de_alcance === true && !i2.texto, i2);
  const i3 = O.salidaInformacion({ text: 'Atendemos con turno. [NO_AGREGAR]' });
  t('I3 marcas inventadas entre corchetes no llegan al paciente', i3.texto === 'Atendemos con turno.', i3);
  const u1 = O.salidaUrgencias({ output: '[NO_REPLY]', intermediateSteps: [paso('derivar_triaje', { ok: true, derivado_a_triaje: true })] });
  t('U1 Urgencias derivó', u1.estado === 'derivado', u1);
  const u2 = O.salidaUrgencias({ output: 'FUERA_DE_ALCANCE' });
  t('U2 (I6) "me duele la cabeza": fuera de alcance de Urgencias (no es boca/dientes/aparato)', u2.fuera_de_alcance === true, u2);
  const u3 = O.salidaUrgencias({ output: 'Tranquila, póngase cera.' });
  t('U3 Urgencias no derivó: derivar_fallo (el cerebro avisa [ACCIÓN URGENTE]); su texto NUNCA sale', u3.estado === 'derivar_fallo' && !u3.texto, u3); }

console.log('\nREUNIR (fuera de alcance → derivar por código, una vez)');
{ const plan = O.despachar(orq([{ a: 'informacion', pedido: 'presupuesto de mi caso' }]), {});
  const r1 = O.reunir(plan, { informacion: O.salidaInformacion({ text: 'FUERA_DE_ALCANCE' }) }, { texto_paciente: 'cuanto me sale lo mio' });
  t('R1 (M2) un sub-agente FUERA_DE_ALCANCE → derivar (por código, sin segunda vuelta del modelo) con la frase del paciente', r1.derivar === true && r1.cita === 'cuanto me sale lo mio' && /informacion/.test(r1.motivo), r1);
  const pn = O.despachar(orq([{ a: 'no_entendi' }]), {});
  t('R2 2.º no_entendi en 30 min → derivar', O.reunir(pn, {}, { noentendi_n: 2 }).derivar === true && O.reunir(pn, {}, { noentendi_n: 1 }).derivar === false);
  const ph = O.despachar(orq([{ a: 'pasar_a_humano', cita: 'quiero hablar con la doctora' }]), {});
  t('R3 humano: no se deriva además', O.reunir(ph, {}, {}).humano === true && O.reunir(ph, {}, {}).derivar === false);
  const pu = O.despachar(orq([{ a: 'turnos', pedido: 'cambiar turno' }]), {});
  const uu = O.urgenciaPendiente(pu, { turnos: { agente: 'turnos', urgencia: true } });
  t('R4 (B4 capa b) Turnos vio una urgencia que el orquestador no vio → el código llama a Urgencias', uu.hacer === true && uu.origen === 'turnos', uu); }

console.log('\nCOMPOSICIÓN (orden fijo, read-back al final, datos por código)');
const T_RB = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { etapa: 'confirmacion', ok: true, texto_para_el_paciente: RB })] }, {});
const P_DAT = O.salidaPagos({ output: '[LISTO]', intermediateSteps: [paso('datos_pago', { ok: true, datos_pago: true, texto_para_el_paciente: Clin.TEXTOS.DATOS_PAGO })] });
const I_PRE = O.salidaInformacion({ text: 'La primera consulta tiene un valor de $50.000. ¿Quiere que le busque un turno para la primera consulta?' });
const PROP = { exec_id: 'ex1', readback_text: RB, estado: 'pendiente' };
const base = (o) => ({ execId: 'ex1', texto_paciente: 'mensaje', libros: [], ofertas: [{ fecha: '2026-10-22', hora: '09:20' }], vistos: [{ fecha: '2026-10-16', hora_inicio: '09:10' }], datosPago: DATOS, menu: O.MENU, ...o });
{ const plan = O.despachar(orq([{ a: 'turnos', pedido: 'x' }, { a: 'pagos', pedido: 'y' }, { a: 'informacion', pedido: 'z' }, { a: 'derivar_secretaria', cita: 'en dolares', motivo: 'dólares' }]), {});
  const c = O.componer(base({ plan, prop: PROP, res: { turnos: T_RB, pagos: P_DAT, informacion: I_PRE }, reunion: { derivar: true }, derivar_res: { ok: true, texto_para_el_paciente: Clin.TEXTOS.DERIVA } }));
  const i = (x) => c.texto.indexOf(x);
  t('C1 orden fijo: Información → Pagos (+ datos) → derivación → Turnos, y el read-back AL FINAL', i('$50.000') < i('Le paso los datos') && i('Le paso los datos') < i('Alias: dra.raquel.aurea') && i('Alias') < i('Le paso con la secretaria') && i('Le paso con la secretaria') < i('Le confirmo') && c.texto.endsWith(RB), c.texto);
  t('C2 con read-back no va la oferta fija de Información (no dos preguntas)', !c.texto.includes('¿Quiere que le busque un turno') && (c.texto.match(/\?/g) || []).length === 1, c.texto);
  t('C3 los datos bancarios van DENTRO de la parte de Pagos (no después del "¿Procedo…?")', c.partes.pagos.endsWith(DATOS) && !c.partes.turnos.includes('Alias'), c.partes); }
{ const plan = O.despachar(orq([{ a: 'menu_bienvenida' }]), {});
  const c = O.componer(base({ plan, conversacion_nueva: true, res: {}, reunion: {} }));
  t('C4 saludo en conversación nueva → el menú solo (ya trae la presentación; no se duplica)', c.texto === O.MENU && (c.texto.match(/Soy Asiri/g) || []).length === 1, c.texto); }
{ const plan = O.despachar(orq([{ a: 'no_reply' }]), {});
  const c = O.componer(base({ plan, res: {}, reunion: {} }));
  t('C5 cierre → silencio', c.silencio === true && c.texto === null, c); }
{ const plan = O.despachar(orq([{ a: 'urgencias', pedido: 'alambre que pincha' }, { a: 'turnos', pedido: 'cambiar turno' }]), {});
  const c = O.componer(base({ plan, res: { turnos: T_RB, urgencias: O.salidaUrgencias({ output: '[NO_REPLY]', intermediateSteps: [paso('derivar_triaje', { ok: true })] }) }, reunion: {}, triaje: { motivo: 'derivar_triaje', cita: 'la nena tiene el alambre q le pincha' } }));
  t('C6 urgencia derivada (sin escrituras): v7 en silencio (responde el triaje) y FYI de lo demás', c.silencio === true && c.derivar_triaje === true && c.triaje.cita.includes('alambre') && c.avisos.some((a) => a.nivel === 'FYI' && /además pidió/.test(a.texto)), c); }
{ const plan = O.despachar(orq([{ a: 'urgencias', pedido: 'alambre' }, { a: 'turnos', pedido: 'responde a la confirmación pendiente' }]), {});
  const T_OK = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { etapa: 'ejecutado', ok: true, texto_para_el_paciente: EXITO })] }, {});
  const c = O.componer(base({ plan, res: { turnos: T_OK }, reunion: {}, libros: [{ ok: true, tipo: 'cambio', readback_text: EXITO }], triaje: { motivo: 'derivar_triaje', cita: 'se me salió el alambre' } }));
  t('C7 (U3, crítica eng. B1) "sí, cámbielo; ah, se me salió el alambre": se cuenta el cambio y la urgencia va como [ACCIÓN URGENTE]; NO se calla', c.texto === EXITO && c.derivar_triaje === false && c.avisos.some((a) => /^\[ACCIÓN URGENTE\]/.test(a.texto)), c); }
{ const plan = O.despachar(orq([{ a: 'turnos', pedido: 'responde a la confirmación pendiente' }]), {});
  const c = O.componer(base({ plan, res: { turnos: O.salidaTurnos({ error: 'max iterations' }, {}) }, reunion: {}, libros: [{ ok: true, tipo: 'cambio', readback_text: EXITO }] }));
  t('C8 (B7) Turnos se cayó DESPUÉS de escribir: sale el texto de éxito del libro, no un error', c.texto.startsWith(EXITO) && !c.texto.includes('inconveniente'), c.texto); }
{ const plan = O.despachar(orq([{ a: 'turnos', pedido: 'x' }]), {});
  const c = O.componer(base({ plan, res: { turnos: O.salidaTurnos({ error: 'max iterations' }, {}) }, reunion: {} }));
  t('C9 Turnos se cayó sin escribir: texto honesto + [ACCIÓN]', c.texto === O.TEXTOS.ERROR && c.avisos.some((a) => /^\[ACCIÓN\]/.test(a.texto)), c); }
{ const plan = O.despachar({ text: 'Hola! Soy Asiri, ¿en qué le ayudo?' }, {});
  const c = O.componer(base({ plan, res: {}, reunion: {} }));
  t('C10 texto libre del orquestador: descartado; sale el texto honesto de error + [ACCIÓN] (nunca su redacción)', c.texto === O.TEXTOS.ERROR && !c.texto.includes('en qué le ayudo') && c.avisos.length === 1, c); }
{ const plan = O.despachar(orq([{ a: 'informacion', pedido: 'presupuesto' }]), {});
  const res = { informacion: O.salidaInformacion({ text: 'FUERA_DE_ALCANCE' }) };
  const reunion = O.reunir(plan, res, { texto_paciente: 'presupuesto' });
  const c = O.componer(base({ plan, res, reunion, derivar_res: { ok: true, texto_para_el_paciente: Clin.TEXTOS.DERIVA } }));
  t('C11 todo fuera de alcance → la derivación fija (nada del sub-agente)', c.texto === Clin.TEXTOS.DERIVA, c.texto); }
{ const plan = O.despachar(orq([{ a: 'derivar_secretaria', cita: 'otra vez en dolares' }]), {});
  const c = O.componer(base({ plan, res: {}, reunion: { derivar: true }, derivar_res: { ok: true, modo_humano: true, texto_para_el_paciente: Clin.TEXTOS.DERIVA_INSISTE } }));
  t('C12 insiste → solo el texto de insistencia (modo humano)', c.texto === Clin.TEXTOS.DERIVA_INSISTE && c.modo_humano === true, c); }
{ const plan = O.despachar(orq([{ a: 'informacion', pedido: 'precio' }]), {});
  const c = O.componer(base({ plan, conversacion_nueva: true, res: { informacion: O.salidaInformacion({ text: 'La primera consulta tiene un valor de $50.000.' }) }, reunion: {} }));
  t('C13 conversación nueva sin menú: se antepone la presentación (dato de 12 h)', c.texto.startsWith(O.TEXTOS.PRESENTACION + '\n\n') && c.texto.endsWith('$50.000.'), c.texto); }
{ const plan = O.despachar(orq([{ a: 'turnos', pedido: 'responde a la confirmación pendiente' }]), {});
  const T_OK = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { etapa: 'ejecutado', ok: true, texto_para_el_paciente: 'Listo, le reservé el jueves 22/10 a las 09:20.' })] }, {});
  const libros = [{ ok: true, tipo: 'reserva', primera_consulta: true, readback_text: 'Listo, le reservé el jueves 22/10 a las 09:20.' }];
  const c1 = O.componer(base({ plan, res: { turnos: T_OK }, reunion: {}, libros }));
  t('C14 reserva → pedido de pago + datos (como el v6), una sola vez', c1.texto.includes('Para confirmarlo definitivamente') && (c1.texto.match(/Alias:/g) || []).length === 1 && c1.datos_pago_agregados === 'reserva', c1.texto);
  const plan2 = O.despachar(orq([{ a: 'turnos', pedido: 'x' }, { a: 'pagos', pedido: 'alias' }]), {});
  const c2 = O.componer(base({ plan: plan2, res: { turnos: T_OK, pagos: P_DAT }, reunion: {}, libros }));
  t('C15 reserva + pidió datos en el mismo mensaje: los datos NO se duplican', (c2.texto.match(/Alias:/g) || []).length === 1 && c2.texto.includes(O.TEXTOS.RESERVA_PAGO_CORTO), c2.texto);
  // (16/10, plan §3.2 #1) un paciente con ficha que reserva un control o suma un turno: SIN pedido de pago
  const c3 = O.componer(base({ plan, res: { turnos: T_OK }, reunion: {}, libros: [{ ...libros[0], primera_consulta: false }] }));
  t('C14b reserva de un paciente con ficha (control): sin pedido de pago ni datos', !c3.texto.includes('Para confirmarlo definitivamente') && !/Alias:/.test(c3.texto) && !c3.datos_pago_agregados, c3.texto);
  const c4 = O.componer(base({ plan, res: { turnos: T_OK }, reunion: {}, libros: [{ ok: true, tipo: 'sumar', readback_text: 'Listo, le reservé el jueves 22/10 a las 09:20.' }] }));
  t('C14c turno sumado sin marca de primera consulta: sin pedido de pago', !c4.texto.includes('Para confirmarlo definitivamente'), c4.texto); }
{ const plan = O.despachar(orq([{ a: 'turnos', pedido: 'quiere turno' }]), {});
  const T_INV = { agente: 'turnos', texto: 'Le ofrezco el martes 4/11 a las 11:40.', estado: 'respondido', herramientas: [] };
  const c = O.componer(base({ plan, res: { turnos: T_INV }, reunion: {}, bloque: BLOQUE }));
  t('C16 el chequeo de salida corre sobre la parte de Turnos: un horario que nadie ofreció se reemplaza por el bloque real', c.texto === BLOQUE && c.motivo_chequeo === 'horario_no_ofrecido', c); }
{ const plan = O.despachar(orq([{ a: 'no_entendi' }]), {});
  const c = O.componer(base({ plan, res: {}, reunion: {} }));
  t('C17 no se entiende → repregunta fija (I8: sin ofrecer "una urgencia")', c.texto === O.TEXTOS.NO_ENTENDI && !/urgencia/i.test(c.texto), c.texto); }
{ const plan = O.despachar(orq([{ a: 'pedir_texto' }]), {});
  t('C18 (B5) audio → frase fija pidiendo que lo escriba', O.componer(base({ plan, res: {}, reunion: {} })).texto === O.TEXTOS.PEDIR_TEXTO); }
{ const plan = O.despachar(orq([{ a: 'derivar_secretaria', cita: 'x' }]), {});
  const c = O.componer(base({ plan, res: {}, reunion: { derivar: true }, derivar_res: { error: 'sub-workflow caído' } }));
  t('C19 la derivación no salió (sub-workflow caído): el paciente igual recibe el texto fijo y el cerebro avisa [ACCIÓN] por su lado', c.texto === Clin.TEXTOS.DERIVA && c.avisos.some((a) => /no salió/.test(a.texto)), c); }

console.log('\nMENÚ y TEXTOS (B1, I8)');
const MENU_PANEL_VIEJO = 'Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel Rodríguez (Áurea Odontología Estética) 🤗\n\nEn qué puedo ayudarle hoy? Puede elegir una opción:\n1. Información de tratamientos\n2. Agendar un turno\n3. Consultar o reprogramar su turno\n4. Precios y formas de pago (Valor de consulta, cuotas, alias)\n5. Ubicación y horarios de atención';
t('M1 el menú viejo del panel (pregunta abierta + cuotas) NO sale: va el menú de las funciones', O.menu(MENU_PANEL_VIEJO) === O.MENU && !O.MENU.includes('cuota') && !/en qu[eé] puedo ayudar/i.test(O.MENU));
t('M2 un menú del panel dentro del alcance sale tal cual', O.menu('Hola! Soy Asiri. Puedo ayudarle con turnos, pagos e información del consultorio. Escriba lo que necesita.') !== O.MENU);
t('M3 el menú cierra con una instrucción, no con una pregunta abierta', /Escriba el número de la opción o lo que necesita\.$/.test(O.MENU) && !O.MENU.includes('?'));
t('M4 el texto de derivación es el mismo en el cerebro y en la herramienta de clínica', O.TEXTOS.DERIVA === Clin.TEXTOS.DERIVA);

// (08/10, revisión) el código tiene que venir solo: una respuesta que MENCIONA la palabra no es el código.
{ const r = O.salidaInformacion({ text: 'Atendemos solo con turno previo; no tenemos guardia de urgencias.' });
  t('CX1 Información: "no tenemos guardia de urgencias" es una respuesta, NO el código URGENCIA', r.estado === 'respondido' && r.urgencia === false && /guardia de urgencias/.test(r.texto), r); }
{ const r = O.salidaInformacion({ text: '**URGENCIA**' });
  t('CX2 el código solo (aunque venga con asteriscos) sí cuenta', r.estado === 'urgencia' && r.texto === '', r); }
{ const r = O.salidaInformacion({ text: 'Eso queda FUERA_DE_ALCANCE de lo que puedo ver, pero le cuento que atendemos con turno.' });
  t('CX3 el código metido en una frase no cuenta (y la frase pasa como respuesta)', r.estado === 'respondido', r); }

// (08/10, REAL-12) sin turnos y sin bloque: una sola frase que ofrece la salida (otra fecha o lista de espera), aunque haya dos búsquedas vacías.
{ const r = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: false, motivo: 'sin_turnos' }), paso('buscar_horarios', { ok: false, sin_horarios_nuevos: true })] }, {});
  t('T9b sin lugar y sin horarios nuevos: UNA sola frase que ofrece otra fecha o lista de espera (no dos frases secas)', r.texto === 'Para lo que pidió no hay turnos disponibles. ¿Quiere que le busque otra fecha, o prefiere que le deje anotado por si se libera uno?', r); }

// (15/10, prueba en vivo) el agente armó la confirmación de cancelación y en el mismo mensaje intentó ejecutarla: el código la frena (ya_ejecutada).
{ const RBC = '¿Procedo con la cancelación de su turno del jueves 10/12 a las 08:00?';
  const r = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { etapa: 'confirmacion', ok: true, texto_para_el_paciente: RBC }),
    paso('gestionar_turno', { etapa: 'ejecutado', ok: false, motivo: 'ya_ejecutada' }, { confirma: 'true' })] }, {});
  t('T10 confirmación armada + intento de ejecutarla en el mismo mensaje: el paciente recibe el "¿Procedo…?", no "ya quedó registrado"', r.texto === RBC && r.estado === 'readback_pendiente' && r.readback === true, r);
  const r2 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { etapa: 'ejecutado', ok: false, motivo: 'ya_ejecutada' }, { confirma: 'true' })] }, {});
  t('T10b "ya_ejecutada" sola (un "sí" repetido) sigue diciendo que ya quedó registrado', r2.texto === 'Ese pedido ya quedó registrado.', r2); }

// (20/10, prueba en vivo 318950) "cuánto sale la consulta y pasame el alias" → el orquestador mandó todo a Información, sin Pagos.
{ const p = O.despachar(orq([{ a: 'informacion', pedido: 'consulta cuánto sale la primera consulta; pregunta si se puede pagar por transferencia y pide el alias' }]), {});
  t('O12 el pedido a Información menciona el alias y no hubo paso de Pagos → Pagos entra por código', p.pagos === 'pide los datos para transferir' && p.pagos_por_codigo === true && !!p.informacion, p);
  const p2 = O.despachar(orq([{ a: 'informacion', pedido: 'pregunta si se puede pagar con transferencia' }]), {});
  t('O12b "¿se puede pagar con transferencia?" es forma de pago (Información), no pide los datos: Pagos no entra', !p2.pagos, p2);
  const p3 = O.despachar(orq([{ a: 'pasar_a_humano', cita: 'quiero hablar con alguien y el alias' }, { a: 'informacion', pedido: 'pide el alias' }]), {});
  t('O12c con pasar a humano no entra ningún agente (tampoco Pagos por código)', p3.fija === 'humano' && !p3.pagos, p3); }

// (20/10, BOT-01 + prueba en vivo con el v7 para todos) Información no pregunta; los datos "se envían al confirmar" no se contradicen; "no" a una confirmación.
{ const plan = O.despachar(orq([{ a: 'informacion', pedido: 'precio y formas de pago' }, { a: 'pagos', pedido: 'alias' }]), {});
  const I_REAL = O.salidaInformacion({ text: 'La primera consulta tiene un valor de $50.000 e incluye evaluación + diagnóstico presuntivo; se puede pagar por transferencia o efectivo y los datos de cuenta se envían al confirmar el turno. \nLa Dra. Raquel atiende martes y jueves de 8:00 a 12:00, y lunes y miércoles de 15:00 a 19:00; ¿para quién es (nombre o DNI)? \n¿Quiere que le busque un turno para la primera consulta?' });
  const c = O.componer(base({ plan, res: { informacion: I_REAL, pagos: P_DAT }, reunion: {} }));
  t('B1a (vivo 20/10) Información sumó "¿para quién es?": se quita, queda solo la oferta fija (una sola pregunta)', !/para qui[eé]n/i.test(c.texto) && (c.texto.match(/\?/g) || []).length === 1 && c.texto.includes(O.TEXTOS.OFERTA_PRIMERA) && c.texto.includes('lunes y miércoles de 15:00 a 19:00.'), c.texto);
  t('B1b con los datos para transferir en el MISMO mensaje no dice "los datos se envían al confirmar el turno"', !/se env[ií]an al confirmar/i.test(c.texto) && c.texto.includes('se puede pagar por transferencia o efectivo.') && c.texto.includes('Alias: dra.raquel.aurea'), c.texto);
  const c2 = O.componer(base({ plan: O.despachar(orq([{ a: 'informacion', pedido: 'formas de pago' }]), {}), res: { informacion: I_REAL }, reunion: {} }));
  t('B1c sin los datos en el mensaje, la frase de los DATOS se respeta', /se env[ií]an al confirmar el turno/.test(c2.texto), c2.texto);
  const I_REAL2 = O.salidaInformacion({ text: 'La primera consulta tiene un valor de $50.000; se requiere pago anticipado y aceptamos efectivo y transferencia (los datos bancarios se envían cuando usted confirme fecha y horario). Hay turnos disponibles: martes 20/10 de 8:00 a 12:00, jueves 22/10 de 8:00 a 12:00 y lunes 26/10 de 15:00 a 19:00; indique día y horario de preferencia. ¿Para quién es (nombre o DNI)?' });
  const T_BLQ = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: true, bloque: BLOQUE })] }, {});
  const cv = O.componer(base({ plan: O.despachar(orq([{ a: 'informacion', pedido: 'precio' }, { a: 'pagos', pedido: 'alias' }, { a: 'turnos', pedido: 'ofrecer' }]), {}), res: { informacion: I_REAL2, pagos: P_DAT, turnos: T_BLQ }, reunion: {},
    bloque: BLOQUE, bloque_exec: BLOQUE, ofertas: [{ fecha: '2026-10-22', hora: '08:00' }, { fecha: '2026-10-22', hora: '09:20' }] }));
  t('B1e (vivo 20/10, 2.ª) Información NUNCA ofrece "turnos disponibles" (eran los horarios de atención): queda el precio y las formas de pago; los turnos, solo el bloque de Turnos',
    cv.partes.informacion === 'La primera consulta tiene un valor de $50.000; se requiere pago anticipado y aceptamos efectivo y transferencia.' && cv.texto.includes(BLOQUE) && !/20\/10|para qui[eé]n|se env[ií]an/i.test(cv.texto), cv.partes);
  const cd = O.componer(base({ plan: O.despachar(orq([{ a: 'informacion', pedido: 'horarios' }]), {}), res: { informacion: O.salidaInformacion({ text: 'La Dra. Raquel atiende lunes de 15:00 a 19:00. La consulta sale $50.000 y hay turnos disponibles el lunes.' }) }, reunion: {} }));
  t('B1f la oración que se quita no corta en "Dra." ni en "$50.000"', cd.texto === 'La Dra. Raquel atiende lunes de 15:00 a 19:00.', cd.texto);
  const sinP = O.componer(base({ plan: O.despachar(orq([{ a: 'informacion', pedido: 'horarios' }]), {}), res: { informacion: O.salidaInformacion({ text: 'Atiende lunes de 15:00 a 19:00.' }) }, reunion: {} }));
  t('B1d texto sin preguntas: queda igual', sinP.texto === 'Atiende lunes de 15:00 a 19:00.', sinP.texto); }
{ const PROPC = { exec_id: 'ex0', tipo: 'cancelacion', enviada: true, readback_text: '¿Procedo con la cancelación de su turno del jueves 10/12 a las 08:00?' };
  const plan = O.despachar(orq([{ a: 'no_reply' }]), { prop_pendiente: true });
  const T_NO = O.salidaTurnos({ output: '[NO_REPLY]', intermediateSteps: [] }, {});
  const c = O.componer(base({ plan, prop: PROPC, prop_pendiente: true, res: { turnos: T_NO }, reunion: {} }));
  t('B2a "no, ese turno sí voy" a la confirmación de cancelar: responde que no se canceló nada (antes, silencio)', c.texto === 'Perfecto, no cancelé nada: su turno queda como estaba.' && !c.silencio, c);
  const c2 = O.componer(base({ plan, prop: { ...PROPC, tipo: 'reserva' }, prop_pendiente: true, res: { turnos: T_NO }, reunion: {} }));
  t('B2b "no" a la confirmación de una reserva: no se reservó nada', c2.texto === 'Perfecto, no reservé nada. Si quiere otro horario, me avisa.', c2.texto);
  const c3 = O.componer(base({ plan: O.despachar(orq([{ a: 'no_reply' }]), {}), res: {}, reunion: {} }));
  t('B2c sin confirmación pendiente, un cierre sigue en silencio', c3.silencio === true && !c3.texto, c3);
  const c4 = O.componer(base({ plan, prop: PROPC, prop_pendiente: true, res: { turnos: T_NO }, reunion: {}, libros: [{ ok: true, tipo: 'cancelacion', readback_text: 'Listo, cancelé su turno.' }] }));
  t('B2d si en este mensaje SÍ se escribió en la agenda, no dice "no cancelé nada"', !/no cancel[eé] nada/.test(c4.texto || ''), c4.texto); }

console.log(`\n${total - fallas}/${total} ${fallas ? 'FALLAS: ' + fallas : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
