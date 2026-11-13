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
  // (12/11, espejo con mensajes reales) paciente nuevo: "Quería saber si tiene turno para el viernes a la tarde" → horarios, sin "No veo turnos vigentes"
  const s6b = O.salidaTurnos({ output: 'MOSTRAR_TURNOS', intermediateSteps: [paso('buscar_horarios', { ok: true, bloque: BLOQUE })] }, { turnos: [] });
  t('T6b sin turnos propios y con horarios ofrecidos: no agrega "No veo turnos vigentes"', s6b.texto === BLOQUE, s6b);
  const s6c = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: true, bloque: BLOQUE }), paso('gestionar_turno', { ok: false, motivo: 'sin_ficha' })] }, { turnos: [] });
  t('T6c gestionar_turno sin ficha + horarios ofrecidos: solo los horarios', s6c.texto === BLOQUE, s6c);
  const s6d = O.salidaTurnos({ output: 'MOSTRAR_TURNOS' }, { turnos: [] });
  t('T6d "¿cuándo es mi turno?" sin turnos y sin horarios: sigue diciendo que no ve turnos', s6d.texto === O.TEXTOS.SIN_TURNOS, s6d);
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

// (21/10, prueba con modelos reales) respuesta a un recordatorio: Turnos siempre ve el mensaje (estado, no texto)
{ const p = O.despachar(orq([{ a: 'no_reply' }]), { recordatorio_pendiente: true });
  t('RC1 "dale gracias 👍" que el orquestador tomó por cierre: con recordatorio pendiente, Turnos igual lo ve con la instrucción de confirmar', !!p.turnos && p.turnos.startsWith('responde al recordatorio') && p.turnos_por_estado === true && p.hay_agentes, p);
  const p2 = O.despachar(orq([{ a: 'turnos', pedido: 'confirma asistencia de los dos' }]), { recordatorio_pendiente: true });
  t('RC2 si el orquestador ya mandó a Turnos, se le suma la instrucción (no buscar horarios salvo otro turno)', p2.turnos.startsWith('confirma asistencia de los dos — responde al recordatorio') && p2.turnos.includes('no busques horarios'), p2.turnos);
  const p3 = O.despachar(orq([{ a: 'pasar_a_humano', cita: 'quiero hablar con alguien' }]), { recordatorio_pendiente: true });
  t('RC3 pidió una persona: no se fuerza Turnos', !p3.turnos && p3.fija === 'humano', p3);
  const p4 = O.despachar(orq([{ a: 'no_reply' }]), { recordatorio_pendiente: true, charla_de_la_clinica: true });
  t('RC4 charla de la clínica: tampoco', !p4.turnos, p4);
  const p5 = O.despachar(orq([{ a: 'no_reply' }]), {});
  t('RC5 sin recordatorio pendiente: un cierre sigue siendo silencio', !p5.turnos && p5.fija === 'no_reply', p5); }

// (21/10, incidente familia: dos turnos el mismo día) confirmaciones: todas al mensaje, nunca dos preguntas
{ const PL = 'Perfecto, quedaron confirmados sus turnos del viernes 23/10 a las 09:50 (Pedro) y viernes 23/10 a las 10:30 (Hilario).';
  const s1 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('confirmar_turno', { ok: true, readback_text: PL })] }, {});
  t('CF1 una sola llamada con los dos turnos: el texto en plural tal cual, estado confirmado', s1.texto === PL && s1.estado === 'confirmado', s1);
  const s2 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('confirmar_turno', { ok: true, readback_text: 'Perfecto, su turno del viernes 23/10 a las 09:50 está confirmado.' }),
    paso('confirmar_turno', { ok: true, readback_text: 'Perfecto, su turno del viernes 23/10 a las 10:30 está confirmado.' })] }, {});
  t('CF2 si el agente igual llama dos veces: van LAS DOS confirmaciones (antes solo la última)', s2.texto.includes('09:50 está confirmado') && s2.texto.includes('10:30 está confirmado'), s2.texto);
  const s3 = O.salidaTurnos({ output: 'PREGUNTA_CUAL_TURNO', intermediateSteps: [paso('confirmar_turno', { ok: false, motivo: 'varios_recordatorios', fechas: ['viernes 23/10 a las 09:50', 'viernes 23/10 a las 10:30'] })] },
    { turnos: ['viernes 23/10 a las 09:50 (Pedro)', 'viernes 23/10 a las 10:30 (Hilario)'] });
  t('CF3 si la herramienta ya preguntó "¿Cuál…?" con su lista, el código NO suma otra pregunta (antes: dos listas en el mismo mensaje)', (s3.texto.match(/\?/g) || []).length === 1, s3.texto); }

// (20/10, D3; escalaciones reales 380–386) charla que inició la clínica con un contacto sin ficha: Asiri no se mete
{ const p = O.despachar(orq([{ a: 'derivar_secretaria', cita: 'Yo por la tarde puedo pasar únicamente', motivo: 'proveedor: arreglar grifo' }]), { charla_de_la_clinica: true });
  t('CL1 charla de la clínica + el orquestador quería derivar: NO deriva, NO responde (sin aviso al grupo)', p.fija === 'no_reply' && !p.hay_agentes && p.charla_de_la_clinica === true, p);
  const c = O.componer(base({ plan: p, res: {}, reunion: O.reunir(p, {}, {}) }));
  t('CL1b el mensaje final es silencio', c.silencio === true && !c.texto && O.reunir(p, {}, {}).derivar === false, c);
  const p2 = O.despachar(orq([{ a: 'turnos', pedido: 'pide turno' }, { a: 'informacion', pedido: 'precio' }]), { charla_de_la_clinica: true });
  t('CL2 tampoco llama a Turnos ni a Información', !p2.turnos && !p2.informacion && p2.fija === 'no_reply', p2);
  const p3 = O.despachar(orq([{ a: 'urgencias', pedido: 'le sangra la encía' }]), { charla_de_la_clinica: true });
  t('CL3 una urgencia que ve el orquestador SÍ sigue su camino', p3.urgencias === 'le sangra la encía' && p3.hay_agentes, p3);
  const p4 = O.despachar(orq([{ a: 'turnos', pedido: 'pide turno' }]), {});
  t('CL4 sin la marca, todo igual que siempre', p4.turnos === 'pide turno' && !p4.charla_de_la_clinica, p4); }

// (20/10, BOT-06) lead de anuncio: la presentación de la clínica (KB 40), no el menú
{ const KB40 = 'Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel 🤗 gracias por comunicarte con nosotros ✨\n\nLa Dra. Raquel Rodríguez es especialista en ortodoncia…';
  const p = O.despachar(orq([{ a: 'presentacion_anuncio' }]), {});
  t('AN1 "¡Hola! Quiero más información" → fija anuncio, sin agentes', p.fija === 'anuncio' && !p.hay_agentes, p);
  const KB21 = 'La primera consulta tiene un valor de $50.000 e incluye evaluación + diagnóstico presuntivo. El presupuesto del tratamiento NO se da en esta consulta.';
  const c = O.componer(base({ plan: p, res: {}, reunion: {}, anuncio: KB40, consulta: KB21, conversacion_nueva: true }));
  t('AN2 (Lucas 20/10) saludo CORTO: quién es Asiri + el precio de la KB 21 + la oferta de turno; sin la presentación larga',
    c.texto === O.TEXTOS.HOLA_ANUNCIO + '\n\n' + 'La primera consulta tiene un valor de $50.000.' + '\n\n' + O.TEXTOS.OFERTA_PRIMERA && (c.texto.match(/Soy Asiri/g) || []).length === 1, c.texto);
  const c1 = O.componer(base({ plan: p, res: {}, reunion: {}, anuncio: KB40, consulta: 'Consulta: consultar con la secretaria.' }));
  t('AN2b la KB 21 sin precio: va la presentación larga (KB 40)', c1.texto === KB40, c1.texto);
  const c2 = O.componer(base({ plan: p, res: {}, reunion: {}, anuncio: '' }));
  t('AN3 sin KB 21 ni KB 40: el menú (nunca un mensaje vacío)', c2.texto === O.MENU, c2.texto);
  const p4 = O.despachar(orq([{ a: 'presentacion_anuncio' }, { a: 'informacion', pedido: 'atiende niños' }]), {});
  t('AN4 saludo de anuncio + una pregunta: responde la pregunta (Información), no la presentación sola', p4.informacion === 'atiende niños' && p4.fija !== 'anuncio', p4); }

// (20/10, escalación real 382) "no voy a llegar" con turno a < 48 h: primero el porqué, después la derivación.
{ const plan = O.despachar(orq([{ a: 'turnos', pedido: 'cancelar el turno de hoy' }]), {});
  const T48 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { ok: false, motivo: 'menos_48h' })] }, {});
  const reunion = O.reunir(plan, { turnos: T48 }, { texto_paciente: 'no voy a llegar' });
  const c = O.componer(base({ plan, res: { turnos: T48 }, reunion, derivar_res: { ok: true, texto_para_el_paciente: Clin.TEXTOS.DERIVA } }));
  t('D48 turno a < 48 h: "Su turno es en menos de 48 horas…" ANTES de "Le paso con la secretaria"', reunion.derivar === true && c.texto.indexOf('menos de 48 horas') >= 0 && c.texto.indexOf('menos de 48 horas') < c.texto.indexOf('Le paso con la secretaria'), c.texto);
  const p2 = O.despachar(orq([{ a: 'derivar_secretaria', cita: 'presupuesto', motivo: 'presupuesto' }, { a: 'turnos', pedido: 'sacar turno' }]), {});
  const T_B = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: true, bloque: BLOQUE })] }, {});
  const c2 = O.componer(base({ plan: p2, res: { turnos: T_B }, reunion: O.reunir(p2, { turnos: T_B }, {}), derivar_res: { ok: true, texto_para_el_paciente: Clin.TEXTOS.DERIVA }, bloque: BLOQUE, bloque_exec: BLOQUE, ofertas: [{ fecha: '2026-10-22', hora: '08:00' }, { fecha: '2026-10-22', hora: '09:20' }] }));
  const T48b = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: true, bloque: BLOQUE }), paso('gestionar_turno', { ok: false, motivo: 'menos_48h' })] }, {});
  t('D48c buscó horarios y después gestionar_turno dijo "menos de 48 h": NO van los horarios (no se pueden reservar)', !T48b.texto.includes('Tenemos los próximos') && T48b.texto.includes('menos de 48 horas'), T48b.texto);
  t('D48b derivación por OTRO motivo + bloque de Turnos: el orden de siempre (derivación y después los horarios)', c2.texto.indexOf('Le paso con la secretaria') < c2.texto.indexOf('Tenemos los próximos'), c2.texto); }

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
// (21/10) Auditoría de paridad v6→v7: comportamientos del v6 que el v7 había perdido (quedan como tests permanentes).
{ const T_NO = O.salidaTurnos({ output: '[NO_REPLY]', intermediateSteps: [] }, {});
  const c = O.componer(base({ plan: O.despachar(orq([{ a: 'turnos', pedido: 'quiere turno para el viernes' }]), {}), res: { turnos: T_NO }, reunion: {}, texto_paciente: 'para el viernes tenes algo?' }));
  t('P1 (v6 Fallback Output; real …6023) el orquestador vio un pedido y el agente dijo [NO_REPLY]: deriva con aviso, nunca silencio',
    c.texto === O.TEXTOS.DERIVA && !c.silencio && c.sin_respuesta_del_agente === true && c.avisos.some((a) => /no supo qu[eé] responder/.test(a.texto)), c);
  const c2 = O.componer(base({ plan: O.despachar(orq([{ a: 'no_reply' }]), {}), res: {}, reunion: {} }));
  t('P1b un cierre ("gracias") que el orquestador marcó no_reply sigue en silencio', c2.silencio === true && !c2.texto, c2);
  const T_DIA = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: true, sin_horarios_nuevos: true, ya_ofrecidos_en_rango: [{ fecha: '2026-10-27', hora: '09:20' }] }, { desde: '2026-10-27', hasta: '2026-10-27' })] }, {});
  t('P2 (real 320042) eligió un día que ya se le ofreció: nombra ese horario, no "no hay turnos"', T_DIA.texto === 'El martes 27/10 tengo a las 9:20. ¿Le sirve?' && !/no hay/i.test(T_DIA.texto), T_DIA.texto);
  const T_DIA2 = O.salidaTurnos({ output: 'PREGUNTA_DATOS_NUEVO', intermediateSteps: [paso('buscar_horarios', { ok: true, sin_horarios_nuevos: true, ya_ofrecidos_en_rango: [{ fecha: '2026-10-27', hora: '09:20' }] }, { desde: '2026-10-27', hasta: '2026-10-27' })] }, {});
  t('P2b si el agente ya entendió que eligió (pide datos), una sola pregunta que nombra el horario y sin "no hay"',
    T_DIA2.texto === 'Para reservar el martes 27/10 a las 9:20 necesito nombre, apellido y DNI del paciente, en un solo mensaje.' && T_DIA2.estado === 'pregunta', T_DIA2);
  const T_VAR = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: false, motivo: 'sin_turnos' }, { desde: '2026-10-23', hasta: '2026-10-23' }),
    paso('buscar_horarios', { ok: true, sin_horarios_nuevos: true, ya_ofrecidos_en_rango: [{ fecha: '2026-10-27', hora: '08:00' }, { fecha: '2026-10-27', hora: '10:40' }, { fecha: '2026-10-29', hora: '16:00' }] }, { desde: '2026-10-23' })] }, {});
  t('P2c ese día no hay y lo siguiente ya se le ofreció: "para ese día no hay" + lo que sigue libre, una sola pregunta',
    T_VAR.texto === 'Para ese día no hay turnos disponibles.\n\nSiguen libres los horarios que le ofrecí:\n- martes 27/10: 8:00 y 10:40\n- jueves 29/10: 16:00\n¿Le sirve alguno?', T_VAR.texto);
  const T_NADA = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: true, sin_horarios_nuevos: true }, { desde: '2026-10-23' })] }, {});
  t('P2d sin nada libre en el rango (ni nuevo ni ofrecido), sigue el "no hay" con la salida', /no hay turnos disponibles/.test(T_NADA.texto), T_NADA.texto);
  const T_PREG = O.salidaTurnos({ output: 'PREGUNTA_DATOS_NUEVO', intermediateSteps: [] }, {});
  const plan = O.despachar(orq([{ a: 'turnos', pedido: 'eligió horario' }]), {});
  const PREG = O.TEXTOS.DATOS_NUEVO;
  const r1 = O.componer(base({ plan, res: { turnos: T_PREG }, reunion: {}, ultimo_asiri: PREG, repeticiones: 0 }));
  t('P3 (real 12333→12335) la misma pregunta por segunda vez: sale, marcada como repetición', r1.texto === PREG && r1.repeticion === true, r1);
  const r2 = O.componer(base({ plan, res: { turnos: T_PREG }, reunion: {}, ultimo_asiri: PREG, repeticiones: 1, texto_paciente: 'como?' }));
  t('P3b (v6: sin bucles) la misma pregunta por TERCERA vez: deriva a la secretaria con aviso', r2.texto === O.TEXTOS.DERIVA && r2.bucle_cortado === true && r2.avisos.some((a) => /repiti[oó] la misma respuesta/.test(a.texto)), r2);
  const T_RB = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { etapa: 'confirmacion', ok: true, texto_para_el_paciente: RB })] }, {});
  const r3 = O.componer(base({ plan, prop: PROP, res: { turnos: T_RB }, reunion: {}, ultimo_asiri: RB, repeticiones: 3 }));
  t('P3c un read-back ("¿Procedo…?") repetido NO corta: se repite a propósito', r3.texto === RB && !r3.bucle_cortado, r3.texto);
  const r4 = O.componer(base({ plan, res: { turnos: T_PREG }, reunion: {}, ultimo_asiri: 'Otra cosa distinta.', repeticiones: 4 }));
  t('P3d si lo último de Asiri fue otra cosa, no hay corte', r4.texto === PREG && !r4.bucle_cortado && !r4.repeticion, r4); }
{ const pasosSin = [paso('confirmar_turno', { ok: false, motivo: 'sin_recordatorio' }), paso('ver_turnos', { ok: false, motivo: 'sin_ficha' })];
  const T1 = O.salidaTurnos({ output: 'PREGUNTA_CUAL_TURNO', intermediateSteps: pasosSin }, {});
  t('P4 (v6: "confirma pero no tiene turno activo" → secretaria) sin recordatorio ni turnos: lo dice una vez y deriva', T1.derivar && T1.texto === 'No veo un turno para confirmar con este número de celular.', T1);
  const plan = O.despachar(orq([{ a: 'turnos', pedido: 'confirma asistencia' }]), {});
  const reu = O.reunir(plan, { turnos: T1 }, { texto_paciente: 'Confirmo' });
  const cc = O.componer(base({ plan, res: { turnos: T1 }, reunion: reu, texto_paciente: 'Confirmo' }));
  t('P4b el paciente recibe "no veo…" + la derivación, y reunir deriva (aviso a la clínica)', reu.derivar === true && cc.texto === 'No veo un turno para confirmar con este número de celular.\n\n' + O.TEXTOS.DERIVA, [reu, cc.texto]);
  const T2 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('confirmar_turno', { ok: false, motivo: 'sin_recordatorio' }), paso('ver_turnos', { ok: true, turnos: ['jueves 23/10 a las 10:00'] })] }, {});
  t('P4c si tiene UN turno, no deriva y se lo nombra (13/11: nunca "¿Cuál de estos turnos?" con uno solo)', !T2.derivar && T2.texto === 'Su turno vigente es el jueves 23/10 a las 10:00.', T2);
  const T3 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('confirmar_turno', { ok: false, motivo: 'sin_recordatorio' })] }, {});
  t('P4d sin ver_turnos en este mensaje (la lista vacía puede ser un error), no deriva por esto', !T3.derivar, T3);
  const p = O.despachar(orq([{ a: 'pagos', pedido: 'manda el comprobante' }]), { recordatorio_pendiente: true });
  t('P5 (v6: el comprobante como respuesta al recordatorio confirmaba) Turnos lo ve con la nota de que el pago de ese turno es un sí', !!p.turnos && /comprobante o aviso de pago/.test(p.turnos), p.turnos); }
// (13/11, 4 mensajes reales del 02/11 al 13/11) "¿Cuál de estos turnos?" con UN solo turno: debajo de "Su turno vigente es el X" (el mismo turno dos
// veces), debajo de los horarios ofrecidos, o sola. Con uno solo, si el mensaje ya lleva otra parte de Turnos no va; si no, se nombra el turno.
{ const UNO = ['miércoles 18/11 a las 15:40'];
  const YA = [{ fecha: '2026-12-03', hora: '08:00' }, { fecha: '2026-12-03', hora: '10:00' }, { fecha: '2026-12-04', hora: '09:10' }];
  const SIGUEN = 'Siguen libres los horarios que le ofrecí:\n- jueves 3/12: 8:00 y 10:00\n- viernes 4/12: 9:10\n¿Le sirve alguno?';
  const a = O.salidaTurnos({ output: 'PREGUNTA_CUAL_TURNO', intermediateSteps: [paso('buscar_horarios', { ok: true, sin_horarios_nuevos: true, ya_ofrecidos_en_rango: YA }, { desde: '2026-12-03', hasta: '2026-12-04' })] }, { turnos: UNO });
  t('CU1 (real 339756) el modelo pregunta "cuál" con un solo turno y van los horarios ya ofrecidos: solo los horarios', a.texto === SIGUEN, a);
  const plan = O.despachar(orq([{ a: 'turnos', pedido: 'pide turno a la mañana; turno vigente miércoles 18/11 15:40' }, { a: 'derivar_secretaria', cita: 'me tiene que dar los alineadores', motivo: 'entrega de alineadores' }]), {});
  const reu = O.reunir(plan, { turnos: a }, { texto_paciente: 'me tiene que dar los alineadores, o a la mañana?' });
  const c = O.componer(base({ plan, ofertas: YA, res: { turnos: a }, reunion: reu, derivar_res: { ok: true, derivado: true, texto_para_el_paciente: O.TEXTOS.DERIVA }, texto_paciente: 'me tiene que dar los alineadores, o a la mañana?' }));
  t('CU1b el mensaje con la derivación ya no termina en "¿Cuál de estos turnos?\\n- (uno)"', c.texto === O.TEXTOS.DERIVA + '\n\n' + SIGUEN, c.texto);
  const b = O.salidaTurnos({ output: '[NO_REPLY]', intermediateSteps: [paso('confirmar_turno', { ok: false, motivo: 'cita_no_vigente' })] }, { turnos: ['viernes 20/11 a las 09:50'] });
  t('CU2 (real 335555, "me lo cambiaron para el 20") la pregunta sola con un turno pasa a nombrarlo', b.texto === 'Su turno vigente es el viernes 20/11 a las 09:50.', b);
  const d = O.salidaTurnos({ output: 'MOSTRAR_TURNOS', intermediateSteps: [paso('gestionar_turno', { ok: false, motivo: 'cita_no_vista' })] }, { turnos: ['miércoles 4/11 a las 19:10'] });
  t('CU3 (real 330189) "Su turno vigente es el X" + "¿Cuál de estos turnos? - X": queda una sola vez', d.texto === 'Su turno vigente es el miércoles 4/11 a las 19:10.', d);
  const BL = 'Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Viernes 27 de noviembre 8:30\n\nLe sirve alguno?';
  const e = O.salidaTurnos({ output: 'MOSTRAR_TURNOS', intermediateSteps: [paso('buscar_horarios', { ok: true, bloque: BL }), paso('gestionar_turno', { ok: false, motivo: 'cita_no_vista' }), paso('ver_turnos', { ok: true, turnos: ['viernes 27/11 a las 09:10'] })] }, {});
  t('CU4 (real 331594) horarios + "Su turno vigente…": sin la pregunta de uno debajo', e.texto === BL + '\n\nSu turno vigente es el viernes 27/11 a las 09:10.', e);
  const f = O.salidaTurnos({ output: 'PREGUNTA_CUAL_TURNO', intermediateSteps: [paso('buscar_horarios', { ok: true, bloque: BL })] }, { turnos: ['viernes 16/10 a las 09:10', 'miércoles 4/11 a las 09:10'] });
  t('CU5 con DOS turnos la pregunta sigue (es una pregunta de verdad)', f.texto === BL + '\n\n¿Cuál de estos turnos?\n- viernes 16/10 a las 09:10\n- miércoles 4/11 a las 09:10', f.texto);
  // (13/11, real 339767) con buscar_horarios mirando la agenda en otro mensaje: "ese día no hay" + lo ya ofrecido que sigue libre, no el bloque entero de nuevo.
  const g = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('buscar_horarios', { ok: false, motivo: 'sin_turnos' }, { desde: '2026-11-18', hasta: '2026-11-18' }),
    paso('buscar_horarios', { ok: true, sin_horarios_nuevos: true, ya_ofrecidos_en_rango: YA }, { desde: '2026-11-18' }), paso('lista_espera', { ok: true, texto_para_el_paciente: O.TEXTOS.ESPERA })] }, { turnos: UNO });
  t('CU6 (real 339767) lista de espera + "Para ese día no hay…" + lo ya ofrecido, sin el bloque entero', g.texto === O.TEXTOS.ESPERA + '\n\nPara ese día no hay turnos disponibles.\n\n' + SIGUEN && !/Tenemos los próximos/.test(g.texto), g.texto); }
// (21/10, auditoría) confirmar_core: un turno de HOY cuya hora ya pasó no se confirma (el v6 confirmó dos así, con el comprobante de después de atenderse).
{ const Conf = require('../v7/confirmar_core.js');
  const rows = [{ id_cita_dentalink: 1, fecha_turno: '2026-10-21', hora_turno: '10:00:00', nombre_paciente: 'Ana' }, { id_cita_dentalink: 2, fecha_turno: '2026-10-21', hora_turno: '18:30:00', nombre_paciente: 'Ana' }];
  const e1 = Conf.elegir(rows, null, '', '2026-10-21', '', '', '15:43');
  t('CF-H1 a las 15:43 se confirma solo el de las 18:30 (el de las 10:00 ya pasó)', e1.ok && e1.cands.map((c) => c.cita_id).join() === '2', e1);
  const e2 = Conf.elegir(rows.slice(0, 1), null, '', '2026-10-21', '', '', '15:43');
  t('CF-H2 si el único es de hoy y ya pasó: no hay nada para confirmar', !!e2.fin, e2);
  const e3 = Conf.elegir(rows, null, '', '2026-10-21', '', '');
  t('CF-H3 sin la hora actual se comporta como antes (todos los de hoy)', e3.ok && e3.cands.length === 2, e3); }

// (28/10) AUDIOS: el v6 transcribía y el v7 recibe "[AUDIO] <transcripción>". Caso real 27/10 12:18: una paciente preguntó por la tomografía con o sin braquets
// (audio transcripto) y Asiri contestó "no puedo escuchar audios". "Pedir el texto" solo vale si el audio llegó SIN transcripción.
{ const CITA = 'Hola Iris, ¿le puede preguntar a la doctora si la tomografía la tengo que hacer con o sin los braquets?';
  const pl = O.despachar(orq([{ a: 'pedir_texto' }]), { audio_transcripto: true, cita_audio: CITA });
  t('AU1 audio transcripto que el orquestador mandó a pedir_texto: se deriva con lo que dijo', pl.fija === 'derivar' && pl.cita === CITA && pl.motivo === 'audio transcripto' && pl.audio_derivado === true, pl);
  const pl2 = O.despachar(orq([{ a: 'pedir_texto' }]), { audio_transcripto: false });
  t('AU2 un audio SIN transcripción sigue pidiendo que lo escriba', pl2.fija === 'pedir_texto' && !pl2.audio_derivado, pl2);
  const pl3 = O.despachar(orq([{ a: 'informacion', pedido: 'tomografía' }]), { audio_transcripto: true, cita_audio: CITA });
  t('AU3 si el orquestador ruteó bien el audio transcripto, no se toca', pl3.fija === null && !!pl3.informacion && !pl3.audio_derivado, pl3);
  const pl4 = O.despachar(orq([{ a: 'derivar_secretaria', cita: 'su frase', motivo: 'consulta clínica' }]), { audio_transcripto: true, cita_audio: CITA });
  t('AU4 si ya derivó, conserva su cita y motivo', pl4.fija === 'derivar' && pl4.cita === 'su frase' && pl4.motivo === 'consulta clínica' && !pl4.audio_derivado, pl4);
  const reu = O.reunir(pl, {}, { texto_paciente: '[AUDIO] ' + CITA });
  const cc = O.componer(base({ plan: pl, res: {}, reunion: reu, texto_paciente: '[AUDIO] ' + CITA }));
  t('AU5 la paciente recibe la derivación (no "no pude escuchar") y la secretaria el aviso con lo que dijo', cc.texto === O.TEXTOS.DERIVA && reu.derivar === true && /tomograf/i.test(String(reu.cita || '') + JSON.stringify(cc.avisos)), [reu, cc]);
  t('AU6 el texto de "no se pudo escuchar" ya no dice que Asiri no escucha audios', !/no puedo escuchar audios/i.test(O.TEXTOS.PEDIR_TEXTO) && /audio/i.test(O.TEXTOS.PEDIR_TEXTO)); }

// (28/10) COMPROBANTES Y NOMBRES DE AGENTE (auditoría v6->v7): el comprobante marcado por la entrada siempre pasa por Pagos; "payments" (caso real 26/10) se entiende.
{ const pl = O.despachar(orq([{ a: 'turnos', pedido: 'responde al recordatorio' }]), { comprobante_marcado: true, recordatorio_pendiente: true });
  t('CP1 comprobante marcado con recordatorio pendiente: Pagos entra por código además de Turnos (caso 23/10 ejec 321861)', !!pl.pagos && pl.pagos_por_codigo === true && pl.comprobante_forzado === true && !!pl.turnos, pl);
  const pl2 = O.despachar(orq([{ a: 'pagos', pedido: 'comprobante' }]), { comprobante_marcado: true });
  t('CP2 si el orquestador ya mandó a Pagos, no se duplica ni se marca forzado', pl2.pagos === 'comprobante' && !pl2.comprobante_forzado, pl2);
  const pl3 = O.despachar(orq([{ a: 'derivar_secretaria', cita: 'x', motivo: 'y' }]), { comprobante_marcado: true });
  t('CP3 comprobante que el orquestador derivó: Pagos igual lo registra (y la derivación sigue)', !!pl3.pagos && pl3.fija === 'derivar', pl3);
  const pl4 = O.despachar(orq([{ a: 'pasar_a_humano', cita: 'quiero hablar' }]), { comprobante_marcado: true });
  t('CP4 si pidió una persona, no se fuerza Pagos (manda el humano)', !pl4.pagos && pl4.fija === 'humano', pl4);
  const pl5 = O.despachar(orq([{ a: 'payments', pedido: 'comprobante' }]), {});
  t('CP5 el agente "payments" se entiende como pagos y no se descarta', pl5.pagos === 'comprobante' && pl5.descartados.length === 0, pl5);
  const pl6 = O.despachar(orq([{ a: 'Appointments', pedido: 'turno' }, { a: 'inventado', pedido: 'x' }]), {});
  t('CP6 alias en singular/inglés; lo desconocido sigue descartándose', pl6.turnos === 'turno' && pl6.descartados.join() === 'inventado', pl6);
  const pl7 = O.despachar(orq([{ a: 'no_reply' }]), { comprobante_marcado: false });
  t('CP7 sin comprobante marcado no se agrega nada', !pl7.pagos && pl7.fija === 'no_reply', pl7); }

// (31/10) LE CONTESTA A LA SECRETARIA (< 6 h): si el orquestador solo deriva, silencio (la secretaria ya está en la charla).
{ const der = orq([{ a: 'derivar_secretaria', cita: 'ya le mande los estudios por mail', motivo: 'informa estudios' }]);
  const p1 = O.despachar(der, { staff_reciente: true });
  t('SR1 deriva solo + staff reciente: silencio sin aviso (caso de la batería del 28/10)', p1.fija === 'no_reply' && p1.staff_silencio === true && !p1.cita, p1);
  const p2 = O.despachar(der, { staff_reciente: false });
  t('SR2 sin staff reciente (más de 6 h o nunca): deriva como siempre', p2.fija === 'derivar' && !p2.staff_silencio, p2);
  const p3 = O.despachar(orq([{ a: 'informacion', pedido: 'precio' }, { a: 'derivar_secretaria', cita: 'y lo mio', motivo: 'deuda' }]), { staff_reciente: true });
  t('SR3 si además hay un pedido a un agente, no se silencia', p3.fija === 'derivar' && !!p3.informacion && !p3.staff_silencio, p3);
  const p4 = O.despachar(orq([{ a: 'pasar_a_humano', cita: 'quiero hablar con alguien' }]), { staff_reciente: true });
  t('SR4 pedir una persona nunca se silencia', p4.fija === 'humano' && !p4.staff_silencio, p4);
  const p5 = O.despachar(der, { staff_reciente: true, recordatorio_pendiente: true });
  t('SR5 con recordatorio pendiente, Turnos ve el mensaje: no se silencia', !!p5.turnos && !p5.staff_silencio, p5);
  const p6 = O.despachar(orq([{ a: 'urgencias', pedido: 'dolor' }, { a: 'derivar_secretaria', cita: 'x', motivo: 'y' }]), { staff_reciente: true });
  t('SR6 una urgencia nunca se silencia', !!p6.urgencias && !p6.staff_silencio, p6);
  const reu = O.reunir(p1, {}, { texto_paciente: 'ya le mande los estudios por mail' });
  const cc = O.componer(base({ plan: p1, res: {}, reunion: reu }));
  t('SR7 el silencio no deriva ni manda texto', reu.derivar !== true && cc.silencio === true && !cc.texto, [reu, cc]); }

// (28/10) MENSAJES FIJOS EDITABLES desde el panel (filas msg_<CLAVE>): la clínica cambia las palabras, el código decide cuándo salen.
{ const NUEVO_NE = 'Perdón, no logré entender. ¿Podría escribirlo con otras palabras? Le ayudo con turnos, pagos o información.';
  const NUEVO_DN = 'Para reservar necesito su nombre, su apellido y su DNI, todo en un solo mensaje, por favor.';
  const planNE = O.despachar(orq([{ a: 'no_entendi' }]), {});
  // Validación (la misma que corre el panel al guardar; acá es la red de seguridad)
  t('MF1 un texto razonable es válido', O.mensajeInvalido('NO_ENTENDI', NUEVO_NE) === null);
  t('MF2 vacío o muy corto se ignora', O.mensajeInvalido('NO_ENTENDI', '') !== null && O.mensajeInvalido('NO_ENTENDI', 'ok') !== null);
  t('MF3 más de 400 caracteres se ignora', O.mensajeInvalido('NO_ENTENDI', 'a'.repeat(401)) === 'muy largo');
  t('MF4 llaves dobles reservadas', O.mensajeInvalido('NO_ENTENDI', 'Hola {{nombre}}, no le entendí bien, disculpe.') === 'llaves reservadas');
  t('MF5 un precio escrito a mano se rechaza (sale de Conocimiento)', O.mensajeInvalido('HOLA_ANUNCIO', 'Hola! Soy Asiri, la consulta sale $50.000 y es para usted.') === 'precio escrito a mano' && O.mensajeInvalido('HOLA_ANUNCIO', 'Hola! La consulta sale 50.000 pesos, venga.') === 'precio escrito a mano');
  t('MF6 cuotas o dólares se rechazan', O.mensajeInvalido('NO_ENTENDI', 'No le entendí. Puede pagar en cuotas o en dólares si prefiere.') === 'habla de cuotas o dólares');
  t('MF7 las preguntas tienen que seguir siendo preguntas', O.mensajeInvalido('PARA_QUIEN', 'Dígame para quién es el turno, por favor.') === 'tiene que ser una pregunta' && O.mensajeInvalido('PARA_QUIEN', '¿Para quién sería el turno?') === null && O.mensajeInvalido('CUAL_TURNO', 'Elija uno de estos turnos, por favor.') !== null && O.mensajeInvalido('OFERTA_PRIMERA', 'Le puedo buscar turno para la consulta.') !== null);
  t('MF8 el pedido de datos del paciente nuevo sigue pidiendo nombre, apellido y DNI', O.mensajeInvalido('DATOS_NUEVO', 'Para reservar necesito su nombre y su DNI, en un solo mensaje.') === 'le falta pedir un dato' && O.mensajeInvalido('DATOS_NUEVO', NUEVO_DN) === null);
  t('MF9 no se pueden editar los de urgencia ni los de pago', O.mensajeInvalido('URG_FALLO', 'Le paso su mensaje a la doctora ahora.') === 'clave no editable' && O.mensajeInvalido('RESERVA_PAGO', 'Para confirmar necesitamos el pago de la consulta antes.') === 'clave no editable');
  // mensajesDe: solo los válidos que cambian algo
  const md = O.mensajesDe({ NO_ENTENDI: NUEVO_NE, PEDIR_TEXTO: 'x', DERIVA: O.TEXTOS.DERIVA, URG_FALLO: 'Le paso su mensaje a la doctora ahora.', PARA_QUIEN: 'sin signo' });
  t('MF10 mensajesDe se queda solo con los válidos que difieren del estándar', Object.keys(md).join() === 'NO_ENTENDI', md);
  t('MF11 mensajesDe tolera basura (null, texto, números)', Object.keys(O.mensajesDe(null)).length === 0 && Object.keys(O.mensajesDe('x')).length === 0 && Object.keys(O.mensajesDe({ NO_ENTENDI: 5 })).length === 0);
  // En la respuesta
  const sin = O.componer(base({ plan: planNE, res: {}, reunion: {} }));
  t('MF12 sin mensajes editados todo sale como siempre', sin.texto === O.TEXTOS.NO_ENTENDI, sin.texto);
  const con = O.componer(base({ plan: planNE, res: {}, reunion: {}, mensajes: { NO_ENTENDI: NUEVO_NE } }));
  t('MF13 con el mensaje editado sale el nuevo', con.texto === NUEVO_NE, con.texto);
  const malo = O.componer(base({ plan: planNE, res: {}, reunion: {}, mensajes: { NO_ENTENDI: 'ok' } }));
  t('MF14 un mensaje inválido en la base se ignora y sale el estándar (nunca se rompe la respuesta)', malo.texto === O.TEXTOS.NO_ENTENDI, malo.texto);
  // Turnos: el texto lo arma OTRO workflow (con el estándar adentro) y el reemplazo igual aplica
  const T_PREG2 = O.salidaTurnos({ output: 'PREGUNTA_DATOS_NUEVO', intermediateSteps: [] }, {});
  const planT = O.despachar(orq([{ a: 'turnos', pedido: 'eligió horario' }]), {});
  const dn = O.componer(base({ plan: planT, res: { turnos: T_PREG2 }, reunion: {}, mensajes: { DATOS_NUEVO: NUEVO_DN } }));
  t('MF15 el pedido de datos que arma el agente de Turnos sale con el texto de la clínica', dn.texto === NUEVO_DN, dn.texto);
  // Derivación: el mismo texto sale cuando lo arma el cerebro y cuando lo arma la herramienta de clínica
  const DERIVA_NUEVA = 'Enseguida le aviso a la secretaria para que se comunique con usted.';
  const rr = O.componer(base({ plan: planT, res: { turnos: T_PREG2 }, reunion: {}, ultimo_asiri: NUEVO_DN, repeticiones: 1, mensajes: { DATOS_NUEVO: NUEVO_DN, DERIVA: DERIVA_NUEVA } }));
  t('MF16 el corte de bucle sigue andando con los textos editados (compara lo que la paciente vio) y deriva con el texto de la clínica', rr.bucle_cortado === true && rr.texto === DERIVA_NUEVA, rr);
  const rr1 = O.componer(base({ plan: planT, res: { turnos: T_PREG2 }, reunion: {}, ultimo_asiri: NUEVO_DN, repeticiones: 0, mensajes: { DATOS_NUEVO: NUEVO_DN } }));
  t('MF17 la misma pregunta editada por segunda vez se marca como repetición', rr1.repeticion === true && rr1.texto === NUEVO_DN, rr1);
  // Una pasada: un texto nuevo que contiene el estándar de otro no se vuelve a reemplazar
  const enc = O.aplicarMensajes(O.TEXTOS.NO_ENTENDI + ' ' + O.TEXTOS.DERIVA, { NO_ENTENDI: 'Perdón. ' + O.TEXTOS.DERIVA + ' (nuevo)', DERIVA: 'Chau, la secretaria lo llama.' });
  t('MF18 el reemplazo es de una sola pasada (no encadena)', enc === 'Perdón. ' + O.TEXTOS.DERIVA + ' (nuevo) Chau, la secretaria lo llama.', enc);
  // Caracteres especiales del texto nuevo no se interpretan ($&, $1)
  t('MF19 un "$&" en el texto nuevo se copia literal', O.aplicarMensajes(O.TEXTOS.NO_ENTENDI, { NO_ENTENDI: 'Costo $& y $1 no aplican, disculpe.' }) === 'Costo $& y $1 no aplican, disculpe.');
  // El read-back de la agenda no se toca aunque haya mensajes editados
  const T_RB2 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('gestionar_turno', { etapa: 'confirmacion', ok: true, texto_para_el_paciente: RB })] }, {});
  const rb = O.componer(base({ plan: planT, prop: PROP, res: { turnos: T_RB2 }, reunion: {}, mensajes: { NO_ENTENDI: NUEVO_NE, DERIVA: DERIVA_NUEVA, DATOS_NUEVO: NUEVO_DN } }));
  t('MF20 el "¿Procedo?" de la agenda sale intacto con mensajes editados', rb.texto === RB, rb.texto);
  // Los 12 editables existen en TEXTOS y sus estándares pasan su propia validación (si no, el panel mostraría un estándar "inválido")
  const todos = Object.keys(O.MENSAJES_EDITABLES);
  t('MF21 los 14 editables existen en TEXTOS y su estándar es válido', todos.length === 14 && todos.every((k) => typeof O.TEXTOS[k] === 'string' && O.mensajeInvalido(k, O.TEXTOS[k]) === null), todos.filter((k) => O.mensajeInvalido(k, O.TEXTOS[k]) !== null).map((k) => k + ':' + O.mensajeInvalido(k, O.TEXTOS[k]))); }

console.log('\nPROPUESTA DE LA CLÍNICA (05/11, incidente José 331590/331596)');
{ const H = require('../v7/historial_core.js');
  const PRE = '[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria desde el WhatsApp del consultorio. Mensaje del staff, no es output tuyo.]: ';
  const JOSE = 'Buenas noches sr. José, disculpe el día Martes 17 de Noviembre (día de su turno), la Dra. tiene médico, por lo tanto, se tiene que retirar temprano. Podríamos reagendar su turno para las 8:40 hs de ese mismo día?';
  const staff = (c, at, kw = {}) => ({ message: { type: 'ai', content: PRE + c, additional_kwargs: { source: 'wa_outbound', was_multimedia: false, from_iri_or_dra: true, ...kw } }, created_at: at });
  const AHORA_MS = Date.parse('2026-11-05T01:50:00Z');
  // filas reales del exec 331590 (más nueva primero): la propuesta, y antes un recordatorio automático de Dentalink que también entra como staff
  const FILAS = [staff(JOSE, '2026-11-04T17:06:40.599Z'), staff('Buenos días sr. José, la Dra. me dijo que si va a atender normal esos dos días…', '2026-11-02T13:30:00Z'),
    staff('Estimado José Pugliese, Le recordamos que el día Martes, 17 de Noviembre de 2026, a las 11:20 tiene programada una cita con la Dra. Rodríguez Raquel', '2026-10-30T12:00:00Z')];
  const u = H.ultimoStaff(FILAS, AHORA_MS, 48 * 3600000);
  t('PS1 José: lo último que no escribió el paciente es la propuesta del staff → texto CRUDO y completo (sin el prefijo ni el corte de 220) + hora', u && u.texto === JOSE && u.ms === Date.parse('2026-11-04T17:06:40.599Z'), u);
  t('PS2 si después escribió el PACIENTE (y quedó en memoria) no hay propuesta sin responder', H.ultimoStaff([{ message: { type: 'human', content: 'dale' }, created_at: '2026-11-04T18:00:00Z' }, ...FILAS], AHORA_MS, 48 * 3600000) === null);
  t('PS3 si después habló ASIRI, la propuesta del staff ya no es lo último → null', H.ultimoStaff([{ message: { type: 'ai', content: 'Le paso con la secretaria.', additional_kwargs: { source: 'asiri_v7' } }, created_at: '2026-11-04T18:00:00Z' }, ...FILAS], AHORA_MS, 48 * 3600000) === null);
  t('PS4 el más nuevo es multimedia del staff (no se puede leer) → null', H.ultimoStaff([staff('[mensaje multimedia enviado por la doctora/secretaria - sin texto adjunto] [MEDIA:abc]', '2026-11-04T17:10:00Z', { was_multimedia: true }), ...FILAS], AHORA_MS, 48 * 3600000) === null);
  t('PS5 el más nuevo es el recordatorio AUTOMÁTICO de Dentalink ("Estimado…, Le recordamos…") → null', H.ultimoStaff(FILAS.slice(2), Date.parse('2026-10-30T14:00:00Z'), 48 * 3600000) === null);
  t('PS6 el staff solo pidió CONFIRMAR asistencia (sin cambio) → null: sigue por confirmar_turno como hoy (Agustín 324637)',
    H.ultimoStaff([staff('Buen día, necesitamos confirmarnos si Agustín va a asistir a su turno del miércoles a las 15:40', '2026-11-04T17:00:00Z')], AHORA_MS, 48 * 3600000) === null);
  const rafaga = H.ultimoStaff([staff('Por favor me confirma y le cambio el turno', '2026-11-04T17:08:00Z'), staff('¿Podemos pasar su turno al jueves 19/11 a las 9:00?', '2026-11-04T17:05:00Z'), staff('Hola!', '2026-11-03T10:00:00Z')], AHORA_MS, 48 * 3600000);
  t('PS7 ráfaga del staff (mensajes seguidos, < 10 min) → se leen juntos, en orden; uno de otro día no entra', rafaga && rafaga.texto === '¿Podemos pasar su turno al jueves 19/11 a las 9:00?\nPor favor me confirma y le cambio el turno' && rafaga.ms === Date.parse('2026-11-04T17:08:00Z'), rafaga);
  t('PS8 propuesta de hace más de 48 h → null', H.ultimoStaff(FILAS, Date.parse('2026-11-07T18:00:00Z'), 48 * 3600000) === null);
  t('PS9 mensaje del sub-WF Cancelar del v6 (wa_outbound SIN prefijo, sin from_iri_or_dra) no es staff humano → null',
    H.ultimoStaff([{ message: { type: 'ai', content: 'Su turno del martes 17/11 a las 8:40 quedó cancelado', additional_kwargs: { source: 'wa_outbound' } }, created_at: '2026-11-04T17:00:00Z' }], AHORA_MS, 48 * 3600000) === null);
  const ctx = H.mensajeAgente([], 'Dale hagamos el cambio', 'miércoles 2026-11-04 22:50', [], '', undefined, { propuesta_clinica: { texto: JOSE, horas: 8.7 } });
  t('PS10 el contexto muestra la PROPUESTA DE LA CLÍNICA con el texto completo y hace cuántas horas', ctx.includes('PROPUESTA DE LA CLÍNICA SIN RESPONDER (la escribió el staff hace 9 h') && ctx.includes('8:40 hs de ese mismo día'), ctx);

  // (revisión R6) mensajes del paciente que NO quedaron en memoria (Asiri calló o modo humano) vienen de mensajes_entrantes_live
  const AH5 = Date.parse('2026-11-05T01:50:00Z');
  t('PS11 el paciente ya contestó después de la propuesta (aunque no quedó en memoria) → ya no está sin responder',
    H.ultimoStaff(FILAS, AH5, 48 * 3600000, [Date.parse('2026-11-04T18:00:00Z')]) === null);
  t('PS12 el mensaje ACTUAL (lote de los últimos 90 s) no cuenta como respuesta previa', !!H.ultimoStaff(FILAS, AH5, 48 * 3600000, [AH5 - 30000]));
  t('PS12b (revisión M1) un "Hola buenos días" de hace 2 min (que Asiri calló) tampoco: la propuesta sigue sin responder', !!H.ultimoStaff(FILAS, AH5, 48 * 3600000, [AH5 - 2 * 60000]));
  const z = H.ultimoStaff([staff('Perfecto, queda como estaba entonces', '2026-11-04T13:07:00Z'), staff('¿Podemos pasar su turno al jueves 19/11 a las 9:00?', '2026-11-04T13:00:00Z')], AH5, 48 * 3600000, [Date.parse('2026-11-04T13:03:00Z')]);
  t('PS13 (caso Z) el paciente contestó ENTRE dos mensajes del staff → la ráfaga se corta: queda solo "queda como estaba" (que no es una propuesta)', z && z.texto === 'Perfecto, queda como estaba entonces', z);
  // (revisión ALTA 2 / MEDIA 4) despacho y composición con una PROPUESTA DE LA CLÍNICA sin responder
  const pm = O.despachar(orq([{ a: 'menu_bienvenida' }]), { propuesta_clinica: true });
  t('PS14 saludo solo con una propuesta de la clínica sin responder → no_reply (sin menú: le contesta al staff)', pm.fija === 'no_reply' && pm.propuesta_clinica === true, pm);
  t('PS14b sin propuesta de la clínica el saludo sigue llevando el menú', O.despachar(orq([{ a: 'menu_bienvenida' }]), {}).fija === 'menu');
  const pr = O.despachar(orq([{ a: 'turnos', pedido: 'acepta la propuesta de la clínica' }]), { propuesta_clinica: true });
  const rechazo = O.salidaTurnos({ output: '[NO_REPLY]', intermediateSteps: [] }, {});
  const cr = O.componer(base({ plan: pr, res: { turnos: rechazo }, reunion: O.reunir(pr, { turnos: rechazo }, {}), texto_paciente: 'no puedo, me quedo con el del 28' }));
  t('PS15 (Bautista) rechaza la propuesta de la clínica y Turnos no hace nada → SILENCIO y sin aviso (antes: "Le paso con la secretaria" + [ACCIÓN] falso)', cr.silencio === true && !cr.texto && !cr.avisos.length, cr);
  const pn = O.despachar(orq([{ a: 'turnos', pedido: 'x' }]), {});
  const cn = O.componer(base({ plan: pn, res: { turnos: rechazo }, reunion: O.reunir(pn, { turnos: rechazo }, {}), texto_paciente: 'quiero un turno' }));
  t('PS16 SIN propuesta de la clínica, la red de siempre sigue: Turnos [NO_REPLY] a un pedido → deriva con aviso', cn.texto && cn.avisos.some((a) => /no supo qué responder/.test(a.texto)), cn);
  // (revisión M2) "dale, ahí lo llevo" a "cambiarle el arco" con el staff en el chat: el agente intenta aceptar, no hay propuesta → silencio (no deriva)
  const sinP = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('aceptar_propuesta_clinica', { etapa: 'error', ok: false, motivo: 'sin_propuesta_staff' })] }, {});
  const ps1 = O.despachar(orq([{ a: 'turnos', pedido: 'acepta la propuesta de la clínica' }]), { staff_reciente: true });
  const rs1 = O.reunir(ps1, { turnos: sinP }, { texto_paciente: 'dale, ahí lo llevo' });
  const cs1 = O.componer(base({ plan: ps1, res: { turnos: sinP }, reunion: rs1, texto_paciente: 'dale, ahí lo llevo' }));
  t('PS17 (M2) staff en el chat (< 6 h) y no había propuesta que aplicar → silencio, sin derivar ni avisar', !rs1.derivar && cs1.silencio === true && !cs1.avisos.length, [rs1, cs1]);
  const ps2 = O.despachar(orq([{ a: 'turnos', pedido: 'acepta la propuesta de la clínica' }]), {});
  const rs2 = O.reunir(ps2, { turnos: sinP }, { texto_paciente: 'Dale hagamos el cambio' });
  t('PS18 (M2) SIN staff reciente (José, 9 h) sigue derivando con motivo', rs2.derivar === true && /no encontró la propuesta/.test(rs2.motivo), rs2);
  const ps3 = O.despachar(orq([{ a: 'turnos', pedido: 'x' }, { a: 'pagos', pedido: 'y' }]), { staff_reciente: true });
  const cs3 = O.componer(base({ plan: ps3, res: { turnos: rechazo, pagos: { agente: 'pagos', estado: 'no_reply', codigo: '[NO_REPLY]', texto: '' } }, reunion: {}, texto_paciente: 'x' }));
  t('PS19 (M2 acotado) con el staff en el chat pero DOS agentes sin nada que hacer, la red de siempre no cambia (deriva con aviso)', cs3.texto && cs3.avisos.some((a) => /no supo qué responder/.test(a.texto)), cs3);
  const s3b = O.salidaTurnos({ output: 'PREGUNTA_PARA_QUIEN', intermediateSteps: [paso('aceptar_propuesta_clinica', { etapa: 'error', ok: false, motivo: 'staff_para_quien', derivar_staff: 'varias fichas y el mensaje no dice de quién es el turno' })] }, {});
  t('PS20b (B3) si la propuesta se deriva, no se suma "¿Para quién es el turno?"', !s3b.texto && s3b.derivar && !/Para quién/.test(s3b.texto), s3b);

  // salida de Turnos con aceptar_propuesta_clinica (mismo workflow que gestionar_turno)
  const YA = 'Perfecto, el turno de José queda el martes 17/11 a las 08:40 con la Dra. Raquel.';
  const s1 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('aceptar_propuesta_clinica', { etapa: 'ya_en_agenda', ok: true, texto_para_el_paciente: YA, aviso: '[FYI] José aceptó la propuesta de la clínica; el turno ya figura en la agenda (martes 17/11 a las 08:40) y Asiri se lo confirmó.' })] }, {});
  t('PS20 ya_en_agenda: el texto del código sale tal cual, estado ya_en_agenda y un aviso FYI para la secretaria', s1.texto === YA && s1.estado === 'ya_en_agenda' && s1.avisos && s1.avisos[0].nivel === 'FYI' && !s1.error_tecnico, s1);
  const RBS = 'Le confirmo el cambio que le propuso la clínica para José: Martes 17 de noviembre a las 08:40 hs con la Dra. Raquel, en lugar de su turno del martes 17/11 a las 11:20. ¿Procedo con el cambio?';
  const s2 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('aceptar_propuesta_clinica', { etapa: 'confirmacion', ok: true, origen: 'staff', texto_para_el_paciente: RBS })] }, {});
  t('PS21 la agenda no lo refleja: sale el read-back del cambio (va solo y al final, como cualquier read-back)', s2.texto === RBS && s2.readback === true && s2.estado === 'readback_pendiente', s2);
  const s3 = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('aceptar_propuesta_clinica', { etapa: 'error', ok: false, motivo: 'staff_fecha_inconsistente', derivar_staff: 'la fecha no coincide con el día de la semana' })] }, {});
  t('PS22 no se pudo aplicar: sin texto propio, deriva con el motivo EXACTO (no "error técnico")', !s3.texto && s3.estado === 'derivar' && /no coincide con el día de la semana/.test(s3.derivar) && !s3.error_tecnico, s3);
  const s4 = O.salidaTurnos({ output: '[NO_REPLY]', intermediateSteps: [paso('aceptar_propuesta_clinica', { etapa: 'error', ok: false, motivo: 'sin_propuesta_staff', para_asiri: 'x' })] }, {});
  t('PS23 (revisión MEDIA 4) quiso aceptar y el sistema ya no ve la propuesta, sin nada más que decir: deriva con motivo (nunca un "no le entendí" mudo)', !s4.error_tecnico && /no encontró la propuesta/.test(s4.derivar || '') && !s4.texto, s4);
  const s4b = O.salidaTurnos({ output: '[LISTO]', intermediateSteps: [paso('aceptar_propuesta_clinica', { etapa: 'error', ok: false, motivo: 'sin_propuesta_staff' }), paso('confirmar_turno', { ok: true, readback_text: 'Perfecto, su turno del martes 17/11 a las 08:40 está confirmado.' })] }, {});
  t('PS23b si después resolvió con otra herramienta (confirmar_turno), no deriva', !s4b.derivar && /confirmado/.test(s4b.texto), s4b);
  // composición
  const planT = O.despachar(orq([{ a: 'turnos', pedido: 'responde a la propuesta de la clínica' }]), {});
  const c1 = O.componer(base({ plan: planT, res: { turnos: s1 }, reunion: {}, vistos: [{ fecha: '2026-11-17', hora_inicio: '08:40' }] }));
  t('PS24 componer: "Perfecto, el turno de José queda…" pasa el chequeo (el turno está en la agenda) y el FYI va al grupo', c1.texto === YA && c1.avisos.some((a) => a.nivel === 'FYI' && /aceptó la propuesta de la clínica/.test(a.texto)), c1);
  const c1b = O.componer(base({ plan: planT, res: { turnos: s1 }, reunion: {}, vistos: [] }));
  t('PS25 si el chequeo de salida reemplaza el texto (el turno no figura), el FYI NO sale (no se avisa algo que no se le dijo)', c1b.texto !== YA && !c1b.avisos.some((a) => a.nivel === 'FYI'), c1b);
  const reun = O.reunir(planT, { turnos: s3 }, { texto_paciente: 'Dale hagamos el cambio' });
  t('PS26 reunir: la derivación de Turnos va a la secretaria con el motivo exacto y COMPLETO (entra en los 120 caracteres del aviso)', reun.derivar === true && /aceptó el cambio que propuso la clínica; no aplicado: la fecha no coincide con el día de la semana$/.test(reun.motivo) && reun.motivo.length <= 120, reun);
  const c3 = O.componer(base({ plan: planT, res: { turnos: s3 }, reunion: reun, derivar_res: { ok: true, texto_para_el_paciente: Clin.TEXTOS.DERIVA }, texto_paciente: 'Dale hagamos el cambio' }));
  t('PS27 componer: el paciente recibe la derivación (no "tuve un inconveniente") y no hay aviso de error', c3.texto === Clin.TEXTOS.DERIVA && !c3.avisos.some((a) => /no pudo completar/.test(a.texto)), c3);
  // (331596) un error de esquema de una herramienta tumba al agente: el aviso dice el porqué
  const se = O.salidaTurnos({ error: 'Received tool input did not match expected schema\n\n✖ Expected string, received boolean\n  → at confirma' }, {});
  const c4 = O.componer(base({ plan: planT, res: { turnos: se }, reunion: {}, texto_paciente: 'Dale hagamos el cambio' }));
  t('PS28 error de esquema: el [ACCIÓN] trae el detalle técnico (antes solo "no pudo completar")', se.error_detalle && c4.avisos.some((a) => /no pudo completar \(turnos\).*Detalle técnico: Received tool input did not match/.test(a.texto.replace(/\n/g, ' '))), c4.avisos); }

console.log(`\n${total - fallas}/${total} ${fallas ? 'FALLAS: ' + fallas : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
