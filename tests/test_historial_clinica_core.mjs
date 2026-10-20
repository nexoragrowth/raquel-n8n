// test_historial_clinica_core.mjs — v7: el historial que ve Asiri y las herramientas de Clínica (cuándo se pasa a una persona). uso: node tests/test_historial_clinica_core.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const H = require('../v7/historial_core.js'); const C0 = require('../v7/clinica_core.js'); const C = { ...C0, decidir: (e) => C0.decidir({ modo: 'vivo', ...e }) };   // (08/10) avisar solo con modo 'vivo' explícito
let fallas = 0, total = 0;
const t = (n, c, x) => { total++; if (!c) { fallas++; console.log(`  FALLA ${n}${x ? ' → ' + JSON.stringify(x).slice(0, 300) : ''}`); } else console.log(`  ok    ${n}`); };

console.log('HISTORIAL');
const M = (type, content, src) => ({ message: { type, content, additional_kwargs: src ? { source: src } : {} } });
const filas = [ // más nuevo primero, como la consulta
  M('ai', 'Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 22 de octubre 8:00 , 9:20', 'wa_outbound'), M('human', 'Buen dia me pude cambiar ese turno'),
  M('ai', '[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria desde el WhatsApp del consultorio. NO es output tuyo, es un humano atendiendo este chat. Mantente en silencio y NO respondas en este chat hasta que un admin diga /bot on.]: Buenos días sra. mamá, por favor hoy lleguen a horario', 'wa_outbound'),
  M('ai', '[NOTA INTERNA - contexto del último recordatorio enviado, NO mencionar al paciente]\nAcabo de enviar un recordatorio 72h', 'reminder_note'),
  M('ai', 'Estimada Dana, Le recordamos su turno con la Dra. Rodríguez Raquel: Viernes 16 de octubre 09:10', 'reminder_note'), M('ai', 'cancelar_o_reprogramar'),
];
const h = H.armar(filas, 12);
t('H1 orden cronológico (lo más nuevo al final) y roles claros', h[h.length - 1].startsWith('ASIRI: Tenemos los próximos turnos') && h[h.length - 2] === 'PACIENTE: Buen dia me pude cambiar ese turno', h);
t('H2 el marcador de 250 caracteres del staff queda en una línea corta, sin las instrucciones internas', h.some((l) => l.startsWith('STAFF DE LA CLÍNICA (persona): Buenos días sra. mamá')) && !h.join('\n').includes('NO es output tuyo'), h);
t('H3 la nota interna de recordatorio se descarta y el recordatorio visible se rotula', !h.join('\n').includes('NOTA INTERNA') && h.some((l) => l.startsWith('CLÍNICA (recordatorio enviado): Estimada Dana')), h);
t('H4 las etiquetas viejas del Router no entran', !h.join('\n').includes('cancelar_o_reprogramar'), h);
t('H5 tope de turnos', H.armar(Array.from({ length: 30 }, (_, i) => M('human', 'msg ' + i)), 10).length === 10);
t('H6 mensaje del agente: fecha, recordatorios, historial y mensaje actual', (() => { const m = H.mensajeAgente(h, 'Si', 'lunes 2026-10-05 09:36', ['viernes 16/10 a las 09:10'], 'CELE'); return m.includes('FECHA Y HORA ACTUAL (Jujuy): lunes 2026-10-05 09:36') && m.includes('RECORDATORIOS YA ENVIADOS (sin respuesta; NO le pidas que confirme: si él confirma, confirmar_turno): viernes 16/10 a las 09:10') && m.includes('puede ser un familiar') && m.endsWith('MENSAJE ACTUAL DEL PACIENTE:\nSi'); })());
t('H7 primera vez sin historial', H.mensajeAgente([], 'Hola', 'x', [], '').includes('(es la primera vez que escribe)'));

console.log('\nCONTEXTO del orquestador (08/10): datos, no compuertas');
{ const m = H.mensajeAgente([], 'ya', 'x', [], '', undefined, { conversacion_nueva: false, confirmacion_pendiente: { texto: '¿Procedo con la cancelación de su turno del viernes 16/10 a las 09:10?', minutos: 4 } });
  t('H8 el contexto dice si la conversación es nueva y muestra la CONFIRMACIÓN PENDIENTE (que el paciente vio) con los minutos', m.includes('CONVERSACIÓN NUEVA (12 h sin mensajes): no') && m.includes('CONFIRMACIÓN PENDIENTE') && m.includes('hace 4 min') && m.includes('¿Procedo con la cancelación'), m); }
t('H9 sin datos extra el contexto queda como antes (compatibilidad)', !H.mensajeAgente([], 'Hola', 'x', [], '').includes('CONFIRMACIÓN PENDIENTE'));
t('H10 ya no existen las regex de intención (esCierre, esSaludo, esPedidoInfo, ultimoPideRespuesta)', ['esCierre', 'esSaludo', 'esPedidoInfo', 'ultimoPideRespuesta'].every((k) => H[k] === undefined));

console.log('\nCLÍNICA: avisos y textos fijos (el texto para el paciente lo arma el código)');
let r = C.decidir({ accion: 'aviso', nivel: 'FYI', texto: 'La paciente preguntó por un presupuesto de alineadores' });
t('C1 aviso FYI: avisa, no silencia, no limpia', r.avisar && r.avisar.tomar === false && r.avisar.resumen.startsWith('[FYI]') && r.limpiar === false && r.resultado.ok, r);
r = C.decidir({ accion: 'aviso', nivel: 'accion', texto: 'Falló la reserva y hay que coordinar un horario' });
t('C2 nivel en minúscula vale; sale como ACCIÓN', r.avisar.resumen.startsWith('[ACCIÓN]'), r);
t('C3 aviso sin nivel o con texto vacío se rechaza', !C.decidir({ accion: 'aviso', nivel: 'urgente', texto: 'x' }).resultado.ok && !C.decidir({ accion: 'aviso', nivel: 'FYI', texto: '' }).resultado.ok);
r = C.decidir({ accion: 'espera', texto: 'Quiere antes del 22/10' });
t('C4 lista de espera: aviso FYI y texto fijo que NO promete avisar', r.avisar.resumen.startsWith('[FYI] Lista de espera') && r.resultado.texto_para_el_paciente === C0.TEXTOS.ESPERA && !/le (vamos a|van a) avisar/i.test(r.resultado.texto_para_el_paciente) && r.avisar.tomar === false, r);
r = C.decidir({ accion: 'pago', pago_reciente: false });
t('C5 comprobante de pago: aviso ACCIÓN, NO silencia, marca para evitar duplicados, texto fijo que NO dice que el pago ingresó', r.avisar.resumen.startsWith('[ACCIÓN]') && r.avisar.tomar === false && r.marcar_pago === true && r.resultado.texto_para_el_paciente === C0.TEXTOS.PAGO && !/ingres|acredit|recibimos el pago/i.test(r.resultado.texto_para_el_paciente), r);
r = C.decidir({ accion: 'pago', pago_reciente: true });
t('C6 segundo comprobante en 15 min: no avisa de nuevo, texto corto y no vuelve a marcar (REAL-02)', r.avisar === null && r.resultado.ok && r.resultado.ya_anotado === true && r.resultado.texto_para_el_paciente === C0.TEXTOS.PAGO_YA && r.marcar_pago === false, r);
r = C.decidir({ accion: 'pago', pago_reciente: false, texto_paciente: 'ya le giré lo de la consulta' });
t('C6d sin ninguna palabra "de pago" ("ya le giré lo de la consulta") se registra igual: decide el modelo, no una lista de palabras', r.resultado.ok === true && r.marcar_pago === true && r.avisar && r.avisar.resumen.includes('«ya le giré lo de la consulta»'), r);
r = C.decidir({ accion: 'pago', pago_reciente: false, texto_paciente: 'Sí ahora los subo.' });
t('C6e el aviso NO afirma "transfirió": dice que Asiri lo tomó como pago y muestra lo que escribió el paciente', r.avisar && /Asiri lo tomó como aviso de pago/.test(r.avisar.resumen) && r.avisar.resumen.includes('«Sí ahora los subo.»') && !/transfiri[oó]/i.test(r.avisar.resumen), r);
r = C.decidir({ accion: 'datos_pago' });
t('C6g datos_pago (pesos por defecto): no avisa a nadie, texto fijo y la marca para que el código pegue los datos', r.resultado.ok === true && r.avisar === null && r.resultado.datos_pago === true && r.resultado.texto_para_el_paciente === C0.TEXTOS.DATOS_PAGO, r);
r = C.decidir({ accion: 'datos_pago', moneda: 'otra' });
t('C6h datos_pago en dólares u otra moneda (lo decide Pagos): fuera de alcance, sin datos (reemplaza el veto por regex de "dólar")', r.resultado.ok === false && r.resultado.fuera_de_alcance === true && !r.resultado.texto_para_el_paciente, r);
r = C.decidir({ accion: 'pago', pago_reciente: false, texto_paciente: '[imagen]' });
t('C6f solo un archivo (comprobante como imagen) → se registra', r.resultado.ok === true && r.marcar_pago === true, r);
r = C.decidir({ accion: 'pago', pago_reciente: false, modo: 'sombra' });
t('C6c sombra: no avisa a nadie pero deja la marca (clave v7s:) para comportarse igual que vivo', r.avisar === null && r.marcar_pago === true && r.resultado.simulado === true, r);

console.log('\nCLÍNICA: derivar a la secretaria (fuera de las 8 tareas) e insistencia → modo humano');
r = C.decidir({ accion: 'derivar', cita_textual: 'cuánto me sale en dólares el tratamiento', motivo: 'presupuesto en dólares', texto_paciente: 'cuánto me sale en dólares el tratamiento' });
t('D1 1.ª derivación: texto fijo «Le paso con la secretaria…», aviso ACCIÓN con la frase textual, NO silencia, cuenta en deriva', r.resultado.texto_para_el_paciente === 'Le paso con la secretaria para que lo atienda.' && r.avisar.tomar === false && /^\[ACCIÓN\]/.test(r.avisar.resumen) && r.avisar.resumen.includes('«cuánto me sale en dólares el tratamiento»') && r.contar_deriva === true && r.limpiar === false, r);
r = C.decidir({ accion: 'derivar', cita_textual: 'y entonces en dólares?', texto_paciente: 'y entonces en dólares?', deriva_recientes: 1 });
t('D2 2.ª derivación en 30 min (insiste): modo humano (tomar=true), limpia el estado, texto fijo de insistencia', r.resultado.modo_humano === true && r.avisar.tomar === true && r.limpiar === true && r.resultado.texto_para_el_paciente === C0.TEXTOS.DERIVA_INSISTE, r);
r = C.decidir({ accion: 'derivar', cita_textual: 'x', texto_paciente: 'x', deriva_recientes: 1, avisos_recientes: 0 });
t('D3 el contador de derivaciones es PROPIO: un aviso técnico previo (avisos) no cuenta como insistencia', C.decidir({ accion: 'derivar', cita_textual: 'x', texto_paciente: 'x', deriva_recientes: 0, avisos_recientes: 5 }).resultado.modo_humano === undefined && r.resultado.modo_humano === true);
r = C.decidir({ accion: 'derivar', cita_textual: 'x', texto_paciente: 'x', deriva_recientes: 1, modo: 'sombra' });
t('D4 sombra: modo humano simulado, sin avisar ni silenciar el chat real, pero cuenta (clave v7s:)', r.avisar === null && r.limpiar === false && r.resultado.modo_humano === true && r.resultado.simulado === true && r.contar_deriva === true, r);

console.log('\nCLÍNICA: pasar a una persona (lo decide el orquestador; el código solo verifica que la cita esté en el mensaje)');
const humano = (cita, texto, extra) => C.decidir({ accion: 'humano', cita_textual: cita, texto_paciente: texto, ...(extra || {}) });
r = humano('quiero hablar con la secretaria', 'Hola, quiero hablar con la secretaria por favor');
t('P1 pidió una persona (cita literal): silencia (tomar), limpia el estado y texto fijo', r.avisar.tomar === true && r.limpiar === true && r.resultado.ok && r.resultado.texto_para_el_paciente === C0.TEXTOS.DERIVA, r);
r = humano('q me atienda la seño', 'holaa q me atienda la seño x fa');
t('P2 castellano jujeño ("q me atienda la seño"): la cita copiada tal cual valida', r.avisar.tomar === true, r);
r = humano('que me atienda la señora', 'q me atienda la seño');
t('P2b (I2 de la crítica) el modelo "corrigió" las faltas de la cita: con la mayoría de las palabras presentes igual valida', r.avisar.tomar === true, r);
r = humano('quiero hablar con la secretaria', 'Hola, quiero confirmar mi turno del jueves');
t('P3 cita inventada (no está en el mensaje): NO silencia, se DERIVA (aviso ACCIÓN, texto fijo): nunca deja al paciente hablando solo con el bot', r.avisar.tomar === false && r.limpiar === false && r.resultado.degradado === true && r.avisar.resumen.startsWith('[ACCIÓN]') && r.resultado.texto_para_el_paciente === C0.TEXTOS.DERIVA, r);
r = humano('', 'quiero hablar con alguien');
t('P4 sin cita: se deriva (no silencia)', r.avisar.tomar === false && r.resultado.degradado === true, r);
r = humano('quiero hablar con la secretaria', 'quiero hablar con la secretaria', { modo: 'sombra' });
t('P5 sombra: no avisa ni silencia, devuelve ok simulado', r.avisar === null && r.limpiar === false && r.resultado.simulado === true, r);
t('P6 acento y mayúsculas no importan', humano('QUIERO HABLAR CON LA SECRETARÍA', 'quiero hablar con la secretaría').avisar.tomar === true);
t('P7 ya no existen VERIF ni los motivos queja/baja (lo de afuera de las 8 tareas va a derivar)', C0.VERIF === undefined && C0.MOTIVOS === undefined);
r = C.decidir({ accion: 'triaje', cita_textual: 'alambre', texto_paciente: 'Hola, se me salió el alambre y me pincha' });
t('T1 derivar_triaje: la cita la pone el CÓDIGO con el mensaje completo (no una paráfrasis), sin aviso al grupo y sin silenciar', r.triaje && r.triaje.motivo === 'derivar_triaje' && r.triaje.cita === 'Hola, se me salió el alambre y me pincha' && r.avisar === null && r.limpiar === false && r.resultado.ok === true, r);
r = C.decidir({ accion: 'triaje', texto_paciente: 'está incómoda, no come' });
t('T2 caso Mariela ("está incómoda, no come", sin palabra clave): deriva igual', r.triaje && r.triaje.cita === 'está incómoda, no come', r);
r = C.decidir({ accion: 'triaje', texto_paciente: 'me duele', modo: 'sombra' });
t('T3 sombra: deja la marca (la lee solo el cerebro de esta ejecución) y lo dice simulado', r.triaje && r.resultado.simulado === true && r.avisar === null, r);
{ const r2 = C.decidir({ accion: 'aviso', nivel: 'FYI', texto: 'Pregunta si aceptan dólares', avisos_recientes: 2 });
  t('P13 con 2 avisos técnicos en los últimos 30 min no se manda otro', !r2.avisar && r2.resultado.ya_avisado === true, r2); }

console.log('\nIDENTIDAD con familias (06/10)');
{ const uno = H.identidad({ ok: true, varias_fichas: true, ficha_elegida: false, pacientes: ['Test - Jana', 'Test - Lucas'], turnos: ['viernes 16/10 a las 10:30 (Test - Lucas)'] });
  t('I01 todos los turnos vigentes son de una ficha: no hay que preguntar para quién para cambiar/cancelar/sumar; solo para un turno nuevo', /El paciente con turno es Test - Lucas/.test(uno) && /SIN preguntar para quién/.test(uno) && /turno NUEVO/.test(uno) && !/TODAVÍA no sabés/.test(uno), uno);
  const dos = H.identidad({ ok: true, varias_fichas: true, ficha_elegida: false, pacientes: ['Ana', 'Beto'], turnos: ['viernes 16/10 a las 10:30 (Ana)', 'lunes 20/10 a las 16:20 (Beto)'] });
  t('I02 turnos de dos fichas distintas: sigue pidiendo para quién es', /TODAVÍA no sabés para quién es/.test(dos), dos);
  const cero = H.identidad({ ok: true, varias_fichas: true, ficha_elegida: false, pacientes: ['Ana', 'Beto'], turnos: [] });
  t('I03 sin turnos vigentes en una familia: pide para quién es', /TODAVÍA no sabés para quién es/.test(cero), cero);
  t('I03b familia: un familiar que no está en la lista es paciente nuevo', /no está en esta lista, es paciente nuevo/.test(cero), cero);
  const nuevo = H.identidad({ ok: false, motivo: 'sin_ficha', para_asiri: '…' });
  t('I04 celular sin ficha = paciente NUEVO (no "no pude consultar"): ofrecer turno y pedir nombre, apellido y DNI al elegir', /Paciente NUEVO/.test(nuevo) && /nombre, apellido y DNI/.test(nuevo) && !/No pude consultar/.test(nuevo), nuevo);
  const caida = H.identidad({ ok: false, motivo: 'error_tecnico' });
  t('I05 una falla real de la agenda sigue diciendo que no pudo consultar', /No pude consultar/.test(caida), caida); }

// (08/10) SALUDO y ANUNCIO por regex (S01-S03) se borraron: el saludo lo reconoce el ORQUESTADOR (menu_bienvenida). Ver tests/test_orquestador_core.mjs.

console.log(`\n${total - fallas}/${total} ${fallas ? 'FALLAS: ' + fallas : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
