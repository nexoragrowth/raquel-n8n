// test_verificador_core.mjs — "v7 Cerebro Agente": el VERIFICADOR por código de lo que le escribe el agente orquestador (v7/verificador_core.js), offline y sin modelo.
// El agente se simula con su salida ({output, intermediateSteps}); lo que se prueba es el CÓDIGO: horarios, montos, read-back, datos de pago, frases del incidente
// del 9/5 (chequeo de consistencia, NO banlist), respaldo (OrquestadorCore.componer) y silencio.  uso: node --test tests/test_verificador_core.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const V = require('../v7/verificador_core.js');
const O = require('../v7/orquestador_core.js');

const RB = 'Le confirmo: Jueves 22 de octubre a las 09:20 hs con la Dra. Raquel, reemplazando el turno del viernes 16/10 a las 09:10. ¿Procedo con la reserva?';
const EXITO = 'Listo, quedó reprogramado su turno: anulé el del viernes 16/10 a las 09:10 y le reservé el jueves 22/10 a las 09:20.';
const BLOQUE = 'Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20\n\nLe sirve alguno?';
const DATOS = 'Alias: dra.raquel.aurea\nTitular: Laura Raquel Rodríguez\nCBU: 0170099220000012345678';
const PRECIO = 'La primera consulta tiene un valor de $50.000.';
const CONSULTA = 'La primera consulta tiene un valor de $50.000 e incluye evaluación + diagnóstico presuntivo.';
const DERIVA = O.TEXTOS.DERIVA;

const sub = (agente, texto = '', estado = 'respondido', x = {}) => ({ agente, texto, estado, codigo: '[LISTO]', herramientas: [], traza: [], fuera_de_alcance: false, urgencia: false, derivar: null, error_tecnico: false, ...x });
const paso = (tool, obs, input) => ({ action: { tool, toolInput: input || {} }, observation: JSON.stringify(obs) });
const ag = (output, pasos = []) => ({ output, intermediateSteps: pasos });
const ESTADO = { libros: [], hechos: [], prop: null, ofertas: [], vistos: [], bloque: '', bloque_exec: '', triaje: null, ultimo_asiri: '', repeticiones: 0, mensajes: {}, anuncio: '', consulta: CONSULTA,
  datosPago: DATOS, conversacion_nueva: false, prop_pendiente: false, menu: undefined };
const ver = (salida, over = {}) => V.verificar({ salida, forzados: [], texto_paciente: 'hola', execId: 'ex1', modo: 'vivo', ctx: {}, ...over, estado: { ...ESTADO, ...(over.estado || {}) } });
const PROP = { exec_id: 'ex1', tipo: 'cambio', readback_text: RB, enviada: false };
const VISTOS = [{ fecha: '2026-10-16', hora_inicio: '09:10' }];
const OFERTAS = [{ fecha: '2026-10-22', hora: '08:00' }, { fecha: '2026-10-22', hora: '09:20' }];   // lo que buscar_horarios deja en Redis
const VISTOS_FAMILIA = [{ fecha: '2026-10-23', hora_inicio: '09:50' }, { fecha: '2026-10-23', hora_inicio: '10:30' }];

test('V01 texto normal con una herramienta: pasa intacto, sin respaldo', () => {
  const r = ver(ag(PRECIO, [paso('informacion', sub('informacion', PRECIO), { pedido: 'precio' })]));
  assert.equal(r.texto, PRECIO); assert.equal(r.usado_respaldo, false); assert.equal(r.motivo_verificador, null); assert.equal(r.silencio, false);
});
test('V02 el monto de la consulta de los DATOS (KB 21) alcanza aunque no haya herramienta', () => {
  const r = ver(ag('La consulta sale $50.000.'));
  assert.equal(r.usado_respaldo, false); assert.equal(r.texto, 'La consulta sale $50.000.');
});
test('V03 monto inventado ($80.000) → respaldo', () => {
  const r = ver(ag('La consulta sale $80.000.'));
  assert.equal(r.usado_respaldo, true); assert.match(r.motivo_verificador, /^monto_no_respaldado:80000/); assert.ok(!/80\.000/.test(r.texto));
});
test('V04 monto que devolvió una herramienta (aunque no sea el de la consulta): pasa', () => {
  const r = ver(ag('Son $15.000 de seña.', [paso('informacion', sub('informacion', 'La seña es de $15.000.'), { pedido: 'seña' })]));
  assert.equal(r.usado_respaldo, false);
});
test('V05 "50 mil" correcto pasa y "70 mil" va a respaldo', () => {
  assert.equal(ver(ag('Sale 50 mil pesos.')).usado_respaldo, false);
  assert.equal(ver(ag('Sale 70 mil pesos.')).usado_respaldo, true);
});
test('V06 montos(): $, pesos y mil', () => {
  assert.deepEqual(V.montos('$50.000, 1.200 pesos y 60 mil').sort((a, b) => a - b), [1200, 50000, 60000]);
  assert.deepEqual(V.montos('el 22/10 a las 9:20'), []);
});
test('V07 horario REAL (salió de buscar_horarios en este mensaje): pasa', () => {
  const r = ver(ag('Tengo el jueves 22 de octubre a las 9:20. ¿Le sirve?', [paso('turnos', sub('turnos', BLOQUE, 'bloque_ofrecido'), { pedido: 'turno' })]));
  assert.equal(r.usado_respaldo, false, JSON.stringify(r.motivo_verificador));
});
test('V08 horario INVENTADO (ninguna herramienta lo dio) → respaldo y el horario no llega al paciente', () => {
  const r = ver(ag('Tengo el jueves 22 de octubre a las 10:00. ¿Le sirve?'));
  assert.equal(r.usado_respaldo, true); assert.match(r.motivo_verificador, /^chequeo_salida:horario_no_ofrecido/); assert.ok(!/10:00/.test(r.texto));
  assert.equal(r.texto, O.TEXTOS.NO_ENTENDI);
});
test('V09 horario inventado CON herramientas: el respaldo es lo que dijeron las herramientas', () => {
  const r = ver(ag('Tengo el jueves 22 de octubre a las 10:00.', [paso('turnos', sub('turnos', BLOQUE, 'bloque_ofrecido'), { pedido: 'turno' })]), { estado: { ofertas: OFERTAS, bloque_exec: BLOQUE } });
  assert.equal(r.usado_respaldo, true); assert.ok(r.texto.includes(BLOQUE)); assert.ok(!/10:00/.test(r.texto));
});
test('V10 un turno que el paciente YA tiene se puede nombrar', () => {
  const r = ver(ag('Su turno vigente es el viernes 16/10 a las 09:10.'), { estado: { vistos: VISTOS } });
  assert.equal(r.usado_respaldo, false);
});
test('V11 afirmar "le reservé" sin escritura en la agenda → respaldo', () => {
  const r = ver(ag('Listo, le reservé el turno.'));
  assert.equal(r.usado_respaldo, true); assert.match(r.motivo_verificador, /afirma_reprogramar_sin_ok/);
});
test('V12 read-back FALTANTE: el agente no lo pegó → se agrega textual al final', () => {
  const r = ver(ag('Perfecto, ya lo dejo armado.', [paso('turnos', sub('turnos', RB, 'readback_pendiente', { readback: true }), { pedido: 'cambiar' })]), { estado: { prop: PROP, vistos: VISTOS } });
  assert.equal(r.usado_respaldo, false, JSON.stringify(r.motivo_verificador)); assert.ok(r.texto.endsWith(RB)); assert.ok(r.texto.includes('¿Procedo con la reserva?'));
  assert.equal(r.texto.split(RB).length, 2);
});
test('V13 read-back PRESENTE textual: no se duplica', () => {
  const r = ver(ag(RB, [paso('turnos', sub('turnos', RB, 'readback_pendiente', { readback: true }), { pedido: 'cambiar' })]), { estado: { prop: PROP, vistos: VISTOS } });
  assert.equal(r.usado_respaldo, false); assert.equal(r.texto, RB);
});
test('V14 read-back + otra pregunta del agente → respaldo con el read-back solo', () => {
  const r = ver(ag('¿Para quién es? ' + RB, [paso('turnos', sub('turnos', RB, 'readback_pendiente', { readback: true }), { pedido: 'cambiar' })]), { estado: { prop: PROP, vistos: VISTOS } });
  assert.equal(r.usado_respaldo, true); assert.match(r.motivo_verificador, /pregunta_extra_con_readback/); assert.ok(r.texto.includes(RB));
});
test('V15 los datos de pago los escribió el AGENTE (alias) → descartado, sale el respaldo con los datos del código', () => {
  const r = ver(ag('Transfiera al alias dra.raquel.aurea por favor.', [paso('pagos', sub('pagos', 'Le paso los datos para transferir:', 'datos_enviados', { datos_pago: true }), { pedido: 'alias' })]));
  assert.equal(r.usado_respaldo, true); assert.equal(r.motivo_verificador, 'datos_pago_escritos_por_el_agente');
  assert.equal(r.texto.split('dra.raquel.aurea').length, 2); assert.ok(r.texto.includes('Alias: dra.raquel.aurea'));
});
test('V16 un CBU escrito por el agente (aunque sea otro número) → respaldo', () => {
  const r = ver(ag('El CBU es 0170011122223333444455.'));
  assert.equal(r.usado_respaldo, true); assert.equal(r.motivo_verificador, 'datos_pago_escritos_por_el_agente');
});
test('V17 datos de pago: los pega el CÓDIGO debajo del texto del agente cuando datos_pago devolvió ok', () => {
  const r = ver(ag('Le paso los datos para transferir. Después nos manda el comprobante, por favor.', [paso('pagos', sub('pagos', 'Le paso los datos para transferir:', 'datos_enviados', { datos_pago: true }), { pedido: 'alias' })]));
  assert.equal(r.usado_respaldo, false); assert.ok(r.texto.endsWith(DATOS)); assert.equal(r.datos_pago_agregados, 'pedido');
});
test('V18 datos de pago sin cargar (KB 24 vacía): aviso [ACCIÓN], no se inventa nada', () => {
  const r = ver(ag('Le paso los datos para transferir.', [paso('pagos', sub('pagos', 'Le paso los datos para transferir:', 'datos_enviados', { datos_pago: true }), { pedido: 'alias' })]), { estado: { datosPago: '' } });
  assert.ok(r.avisos.some((a) => /no están cargados/.test(a.texto)));
});
for (const [n, frase] of [['los esperamos', 'Los esperamos mañana en la clínica.'], ['venite ahora', 'Venite ahora a la clínica.'], ['ahora mismo', 'Pase ahora mismo por el consultorio.'], ['pida confirmación', 'Pida confirmación en recepción.'], ['guarde la pieza', 'Guarde la pieza y tráigala.']]) {
  test(`V19 frase del incidente del 9/5 («${n}»): chequeo de consistencia con el prompt → respaldo`, () => {
    const r = ver(ag(frase));
    assert.equal(r.usado_respaldo, true); assert.match(r.motivo_verificador, /^frase_del_incidente/); assert.ok(!/esperamos|venite|ahora mismo|pida confirmaci|pieza/i.test(r.texto));
  });
}
test('V20 una frase parecida pero inocente NO se frena ("lo esperamos" sí, "esperamos su comprobante" no)', () => {
  assert.equal(ver(ag('Esperamos su comprobante por este medio, gracias.')).usado_respaldo, false);
});
test('V21 respaldo por texto vacío SIN herramientas → NO_ENTENDI', () => {
  const r = ver(ag('   '));
  assert.equal(r.usado_respaldo, true); assert.equal(r.motivo_verificador, 'vacio'); assert.equal(r.texto, O.TEXTOS.NO_ENTENDI);
});
test('V22 respaldo por ERROR del agente (se cayó / tardó): texto honesto + [ACCIÓN] al grupo, fallo_agente', () => {
  const r = ver({ error: { message: 'timeout' } });
  assert.equal(r.usado_respaldo, true); assert.equal(r.motivo_verificador, 'agente_error'); assert.equal(r.fallo_agente, true);
  assert.equal(r.texto, O.TEXTOS.ERROR); assert.ok(r.avisos.some((a) => a.nivel === 'ACCION'));
});
test('V23 sin salida del agente (nodo no corrió) → respaldo', () => {
  assert.equal(ver(null).motivo_verificador, 'agente_sin_salida');
});
test('V24 agente vacío PERO con herramientas: el respaldo es lo que ellas armaron', () => {
  const r = ver(ag('', [paso('informacion', sub('informacion', PRECIO), { pedido: 'precio' })]));
  assert.equal(r.usado_respaldo, true); assert.equal(r.motivo_verificador, 'vacio'); assert.equal(r.texto, PRECIO);
});
test('V25 basura (JSON del modelo) → respaldo', () => {
  assert.equal(ver(ag('{"pasos":[{"a":"turnos"}]}')).motivo_verificador, 'forma_invalida');
  assert.equal(ver(ag('x'.repeat(1600))).motivo_verificador, 'forma_invalida');
});
test('V26 familia con DOS turnos el mismo día (recordatorio): lo que dijo la herramienta pasa', () => {
  const conf = 'Perfecto, quedaron confirmados sus turnos del viernes 23/10 a las 09:50 (Pedro) y viernes 23/10 a las 10:30 (Hilario).';
  const r = ver(ag(conf, [paso('turnos', sub('turnos', conf, 'confirmado'), { pedido: 'responde al recordatorio', forzado: true })]), { forzados: [] });
  assert.equal(r.usado_respaldo, false, JSON.stringify(r.motivo_verificador));
});
test('V27 familia con dos turnos: el agente cambia una hora (10:00 en vez de 10:30) → respaldo con la confirmación real', () => {
  const conf = 'Perfecto, quedaron confirmados sus turnos del viernes 23/10 a las 09:50 (Pedro) y viernes 23/10 a las 10:30 (Hilario).';
  const r = ver(ag('Perfecto, quedaron confirmados el viernes 23/10 a las 09:50 (Pedro) y el viernes 23/10 a las 10:00 (Hilario).', [paso('turnos', sub('turnos', conf, 'confirmado'), { pedido: 'x' })]), { estado: { vistos: VISTOS_FAMILIA } });
  assert.equal(r.usado_respaldo, true); assert.ok(r.texto.includes('10:30')); assert.ok(!r.texto.includes('10:00'));
});
test('V28 forzados por código (comprobante / confirmación pendiente) entran a la traza y al respaldo', () => {
  const rec = 'Recibido. Dejé anotado su aviso de pago.';
  const r = ver(ag(''), { forzados: [{ tool: 'pagos', input: { forzado: true }, obs: sub('pagos', rec, 'pago_anotado') }] });
  assert.equal(r.texto, rec); assert.ok(r.traza.some((t) => t.tool === 'pagos' && t.forzado === true));
});
test('V29 silencio: la herramienta no_responder → silencio, sin texto, sin respaldo', () => {
  const r = ver(ag('', [paso('no_responder', { ok: true, silencio: true })]));
  assert.equal(r.silencio, true); assert.equal(r.texto, null); assert.equal(r.usado_respaldo, false);
});
test('V30 silencio: el agente contesta "[NO_REPLY]" → silencio', () => {
  const r = ver(ag('[NO_REPLY]'));
  assert.equal(r.silencio, true); assert.equal(r.texto, null);
});
test('V31 silencio CON una confirmación pendiente que el paciente vio: no se calla, se le dice que no se cambió nada', () => {
  const r = ver(ag('', [paso('no_responder', { ok: true })]), { estado: { prop_pendiente: true, prop: { ...PROP, exec_id: 'ex-anterior', tipo: 'cambio' } } });
  assert.equal(r.usado_respaldo, true); assert.equal(r.texto, 'Perfecto, no cambié nada: su turno queda como estaba.');
});
test('V32 no_responder junto a una herramienta que SÍ devolvió texto → contradicción: respaldo (el paciente recibe lo que armó la herramienta)', () => {
  const r = ver(ag('', [paso('informacion', sub('informacion', PRECIO), { pedido: 'precio' }), paso('no_responder', { ok: true })]));
  assert.equal(r.usado_respaldo, true); assert.equal(r.texto, PRECIO); assert.equal(r.motivo_verificador, 'silencio_con_resultados');
});
test('V33 charla que inició la clínica con un contacto sin ficha: silencio (el agente ni se llamó)', () => {
  const r = ver(null, { ctx: { charla_de_la_clinica: true } });
  assert.equal(r.silencio, true); assert.equal(r.motivo_verificador, 'charla_de_la_clinica'); assert.equal(r.usado_respaldo, false);
});
test('V34 staff reciente (< 6 h) y el agente SOLO derivó → silencio, sin aviso (la herramienta corre en sombra)', () => {
  const r = ver(ag(DERIVA, [paso('derivar_secretaria', { ok: true, derivado: true, texto_para_el_paciente: DERIVA }, { cita_textual: 'ya le mande los estudios', motivo: 'estudios' })]), { ctx: { staff_reciente: true } });
  assert.equal(r.silencio, true); assert.equal(r.motivo_verificador, 'contesta_al_staff'); assert.equal(r.avisos.length, 0);
});
test('V35 staff reciente pero pidió el precio Y derivó: se responde; aviso [ACCIÓN] porque la derivación no se envió', () => {
  const r = ver(ag(PRECIO + '\n' + DERIVA, [paso('informacion', sub('informacion', PRECIO), { pedido: 'precio' }), paso('derivar_secretaria', { ok: true, texto_para_el_paciente: DERIVA }, { cita_textual: 'x', motivo: 'y' })]), { ctx: { staff_reciente: true } });
  assert.equal(r.silencio, false); assert.ok(r.avisos.some((a) => /menos de 6 h/.test(a.texto)));
});
test('V36 derivar_secretaria: si el agente no escribió la frase de la derivación, el código la agrega', () => {
  const r = ver(ag('Esa consulta la ve la secretaria.', [paso('derivar_secretaria', { ok: true, texto_para_el_paciente: DERIVA }, { cita_textual: 'cuanto sale en dolares', motivo: 'dólares' })]));
  assert.equal(r.usado_respaldo, false); assert.ok(r.texto.endsWith(DERIVA));
});
test('V37 pasar_a_humano → modo_humano', () => {
  const r = ver(ag('Ya aviso.', [paso('pasar_a_humano', { ok: true, humano: true, texto_para_el_paciente: DERIVA }, { cita_textual: 'que me atienda la seño' })]));
  assert.equal(r.modo_humano, true); assert.ok(r.texto.includes(DERIVA));
});
test('V38 la derivación falló (la herramienta no devolvió ok): aviso [ACCIÓN] al grupo', () => {
  const r = ver(ag('Le paso con la secretaria para que lo atienda.', [paso('derivar_secretaria', { ok: false }, { cita_textual: 'x', motivo: 'y' })]));
  assert.ok(r.avisos.some((a) => /el aviso no salió/.test(a.texto)));
});
test('V39 urgencia derivada al triaje: v7 en silencio y derivar_triaje con la cita', () => {
  const r = ver(ag('', [paso('urgencias', sub('urgencias', '', 'derivado', { codigo: '[NO_REPLY]' }), { pedido: 'alambre' })]), { texto_paciente: 'la nena tiene el alambre q le pincha' });
  assert.equal(r.silencio, true); assert.equal(r.derivar_triaje, true); assert.equal(r.triaje.cita, 'la nena tiene el alambre q le pincha');
});
test('V40 otro agente vio una urgencia y nadie la derivó → respaldo con la frase fija + [ACCIÓN URGENTE]', () => {
  const r = ver(ag('Le busco turno.', [paso('turnos', sub('turnos', '', 'nada', { urgencia: true, codigo: 'URGENCIA' }), { pedido: 'x' })]), { texto_paciente: 'mi hija no come' });
  assert.equal(r.usado_respaldo, true); assert.equal(r.motivo_verificador, 'urgencia_sin_derivar'); assert.ok(r.texto.includes(O.TEXTOS.URG_FALLO)); assert.ok(r.avisos.some((a) => a.texto.startsWith('[ACCIÓN URGENTE]')));
});
test('V41 un agente devolvió FUERA_DE_ALCANCE y el orquestador no derivó → respaldo (deriva por código)', () => {
  const r = ver(ag('No tengo esa información.', [paso('informacion', sub('informacion', '', 'fuera_de_alcance', { fuera_de_alcance: true, codigo: 'FUERA_DE_ALCANCE' }), { pedido: 'presupuesto' })]));
  assert.equal(r.usado_respaldo, true); assert.equal(r.motivo_verificador, 'fuera_de_alcance_sin_derivar'); assert.ok(r.texto.includes(DERIVA));
});
test('V41b turnos pidió derivar (turno a < 48 h) y el orquestador no derivó → respaldo: el porqué, "le paso con la secretaria" y aviso al grupo', () => {
  const T48 = 'Su turno es en menos de 48 horas: no lo puedo cambiar ni cancelar por acá.';
  const r = ver(ag(T48, [paso('turnos', sub('turnos', T48, 'menos_48h', { derivar: 'turno en menos de 48 h' }), { pedido: 'no va al turno' })]), { texto_paciente: 'No vamos a estar' });
  assert.equal(r.usado_respaldo, true); assert.equal(r.motivo_verificador, 'derivacion_sin_llamar');
  assert.ok(r.texto.indexOf(T48) >= 0 && r.texto.indexOf(DERIVA) > r.texto.indexOf(T48), r.texto);
  assert.ok(r.avisos.some((a) => a.nivel === 'ACCION' && a.texto.includes('No vamos a estar') && a.texto.includes('turno en menos de 48 h') && !a.texto.includes('no salió')), JSON.stringify(r.avisos));
  // si el orquestador SÍ derivó, sale su texto (sin respaldo)
  const ok = ver(ag(T48, [paso('turnos', sub('turnos', T48, 'menos_48h', { derivar: 'turno en menos de 48 h' }), { pedido: 'no va' }), paso('derivar_secretaria', { ok: true, texto_para_el_paciente: DERIVA }, { cita_textual: 'No vamos a estar', motivo: '48 h' })]));
  assert.equal(ok.usado_respaldo, false); assert.ok(ok.texto.includes(DERIVA));
});
test('V42 una herramienta se cayó: respaldo con aviso', () => {
  const r = ver(ag('Ya le busco.', [paso('turnos', { error: 'boom' }, { pedido: 'x' })]));
  assert.equal(r.usado_respaldo, true); assert.equal(r.motivo_verificador, 'herramienta_con_error'); assert.ok(r.avisos.some((a) => a.nivel === 'ACCION'));
});
test('V43 conversación nueva: se antepone la presentación por código', () => {
  const r = ver(ag(PRECIO), { estado: { conversacion_nueva: true } });
  assert.equal(r.texto, O.TEXTOS.PRESENTACION + '\n\n' + PRECIO);
});
test('V44 mensajes fijos editados en el panel se aplican al texto final', () => {
  const nuevo = 'Enseguida le aviso a la secretaria para que se comunique con usted.';
  const r = ver(ag('Esa consulta la ve ella.', [paso('derivar_secretaria', { ok: true, texto_para_el_paciente: DERIVA }, { cita_textual: 'x', motivo: 'y' })]), { estado: { mensajes: { DERIVA: nuevo } } });
  assert.ok(r.texto.includes(nuevo) && !r.texto.includes(DERIVA));
});
test('V45 corte de bucle: la misma pregunta por tercera vez → se deriva con aviso', () => {
  const preg = '¿Para quién es el turno? (nombre o DNI)';
  const r = ver(ag(preg), { estado: { ultimo_asiri: preg, repeticiones: 1 } });
  assert.equal(r.motivo_verificador, 'bucle_cortado'); assert.equal(r.texto, DERIVA); assert.ok(r.avisos.some((a) => /repitió la misma respuesta/.test(a.texto)));
});
test('V46 una pregunta repetida solo una vez pasa (repeticiones = 0)', () => {
  const preg = '¿Para quién es el turno? (nombre o DNI)';
  assert.equal(ver(ag(preg), { estado: { ultimo_asiri: preg, repeticiones: 0 } }).texto, preg);
});
test('V47 2.º «no entendí» seguido sin herramientas: se deriva (antes lo hacía el contador de Redis)', () => {
  const r = ver(ag(''), { estado: { ultimo_asiri: O.TEXTOS.NO_ENTENDI } });
  assert.equal(r.usado_respaldo, true); assert.equal(r.texto, DERIVA); assert.ok(r.avisos.some((a) => a.nivel === 'ACCION'));
});
test('V48 confirmación ejecutada (libro ok): el texto tiene que traer lo que se hizo; si el agente lo cambia, sale el éxito real', () => {
  const libros = [{ ok: true, tipo: 'cambio', readback_text: EXITO }];
  const bien = ver(ag(EXITO, [paso('turnos', sub('turnos', EXITO, 'escrito_ok'), { pedido: 'sí' })]), { estado: { libros, vistos: VISTOS } });
  assert.equal(bien.usado_respaldo, false); assert.equal(bien.texto, EXITO);
  const mal = ver(ag('Listo, todo hecho para el jueves 22/10 a las 10:30.', [paso('turnos', sub('turnos', EXITO, 'escrito_ok'), { pedido: 'sí' })]), { estado: { libros, vistos: VISTOS } });
  assert.equal(mal.usado_respaldo, true); assert.ok(mal.texto.includes(EXITO));
});
test('V49 el respaldo conserva avisos y la traza lista cada herramienta con su agente', () => {
  const r = ver(ag('', [paso('turnos', sub('turnos', BLOQUE, 'bloque_ofrecido', { traza: [{ tool: 'buscar_horarios', input: {}, obs: '{}' }] }), { pedido: 'turno' })]));
  assert.ok(r.traza.some((t) => t.tool === 'turnos') && r.traza.some((t) => t.tool === 'buscar_horarios' && t.agente === 'turnos'));
});
test('V50 reserva de primera consulta: el pedido de pago + datos lo agrega el código una sola vez', () => {
  const ok = 'Listo, le reservé el jueves 22/10 a las 09:20.';
  const libros = [{ ok: true, tipo: 'reserva', primera_consulta: true, readback_text: ok }];
  const r = ver(ag(ok, [paso('turnos', sub('turnos', ok, 'escrito_ok'), { pedido: 'sí' })]), { estado: { libros } });
  assert.ok(r.texto.startsWith(ok) && r.texto.includes('Para confirmarlo definitivamente') && r.texto.split('Alias:').length === 2);
});
test('V51 el read-back queda ÚLTIMO aunque haya datos de pago: los datos bancarios se pegan antes de «¿Procedo?»', () => {
  const r = ver(ag('Perfecto. ' + RB, [paso('turnos', sub('turnos', RB, 'readback_pendiente', { readback: true }), { pedido: 'cambiar' }), paso('pagos', sub('pagos', 'Le paso los datos para transferir:', 'datos_enviados', { datos_pago: true }), { pedido: 'alias' })]), { estado: { prop: PROP, vistos: VISTOS } });
  assert.equal(r.usado_respaldo, false, JSON.stringify(r.motivo_verificador)); assert.ok(r.texto.endsWith(RB)); assert.ok(r.texto.indexOf('Alias:') < r.texto.indexOf('Le confirmo')); assert.equal(r.texto.split('Le confirmo').length, 2);
});
