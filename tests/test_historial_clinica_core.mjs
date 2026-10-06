// test_historial_clinica_core.mjs — v7: el historial que ve Asiri y las herramientas de Clínica (cuándo se pasa a una persona). uso: node tests/test_historial_clinica_core.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const H = require('../v7/historial_core.js'); const C = require('../v7/clinica_core.js');
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
t('H6 mensaje del agente: fecha, recordatorios, historial y mensaje actual', (() => { const m = H.mensajeAgente(h, 'Si', 'lunes 2026-10-05 09:36', ['viernes 16/10 a las 09:10'], 'CELE'); return m.includes('FECHA Y HORA ACTUAL (Jujuy): lunes 2026-10-05 09:36') && m.includes('RECORDATORIOS PENDIENTES DE CONFIRMAR: viernes 16/10 a las 09:10') && m.includes('puede ser un familiar') && m.endsWith('MENSAJE ACTUAL DEL PACIENTE:\nSi'); })());
t('H7 primera vez sin historial', H.mensajeAgente([], 'Hola', 'x', [], '').includes('(es la primera vez que escribe)'));

console.log('\nCLÍNICA: avisos que NO silencian');
let r = C.decidir({ accion: 'aviso', nivel: 'FYI', texto: 'La paciente preguntó por un presupuesto de alineadores' });
t('C1 aviso FYI: avisa, no silencia, no limpia', r.avisar && r.avisar.tomar === false && r.avisar.resumen.startsWith('[FYI]') && r.limpiar === false && r.resultado.ok, r);
r = C.decidir({ accion: 'aviso', nivel: 'accion', texto: 'Falló la reserva y hay que coordinar un horario' });
t('C2 nivel en minúscula vale; sale como ACCIÓN', r.avisar.resumen.startsWith('[ACCIÓN]'), r);
t('C3 aviso sin nivel o con texto vacío se rechaza', !C.decidir({ accion: 'aviso', nivel: 'urgente', texto: 'x' }).resultado.ok && !C.decidir({ accion: 'aviso', nivel: 'FYI', texto: '' }).resultado.ok);
r = C.decidir({ accion: 'espera', texto: 'Quiere antes del 22/10' });
t('C4 lista de espera: aviso FYI y se le dice a Asiri que NO prometa', r.avisar.resumen.startsWith('[FYI] Lista de espera') && /NO prometas/.test(r.resultado.para_asiri) && r.avisar.tomar === false, r);
r = C.decidir({ accion: 'pago', pago_reciente: false });
t('C5 comprobante de pago: aviso ACCIÓN, NO silencia, marca para evitar duplicados', r.avisar.resumen.startsWith('[ACCIÓN]') && r.avisar.tomar === false && r.marcar_pago === true && /NO valides/.test(r.resultado.para_asiri), r);
r = C.decidir({ accion: 'pago', pago_reciente: true });
t('C6 segundo comprobante en 15 min: no avisa de nuevo', r.avisar === null && r.resultado.ok, r);

console.log('\nCLÍNICA: pasar a una persona (verificado contra el texto literal)');
const humano = (motivo, cita, texto) => C.decidir({ accion: 'humano', motivo, cita_textual: cita, texto_paciente: texto });
r = humano('pidio_persona', 'quiero hablar con la secretaria', 'Hola, quiero hablar con la secretaria por favor');
t('P1 pidió una persona (cita literal): silencia (tomar) y limpia el estado', r.avisar.tomar === true && r.limpiar === true && r.resultado.ok, r);
r = humano('pidio_persona', 'prefiero hablar con la doctora', 'No, prefiero hablar con la doctora');
t('P2 "prefiero hablar con la doctora" (delega): silencia', r.avisar.tomar === true, r);
r = humano('urgencia', 'me duele mucho la muela', 'Me duele mucho la muela desde anoche');
t('P3 pasar_a_humano con urgencia NO silencia: va al triaje (sin aviso propio, sin borrar estado) y Asiri calla', r.avisar === null && r.limpiar === false && r.triaje && r.triaje.motivo === 'pasar_a_humano_urgencia' && r.resultado.derivado_a_triaje === true && /\[NO_REPLY\]/.test(r.resultado.para_asiri) && /NO des indicaciones|no des indicaciones/.test(r.resultado.para_asiri), r);
r = C.decidir({ accion: 'triaje', cita_textual: 'se me salió el alambre y me pincha', texto_paciente: 'Hola, se me salió el alambre y me pincha' });
t('T1 derivar_triaje: marca de triaje con la frase del paciente, sin aviso al grupo y sin silenciar', r.triaje && r.triaje.motivo === 'derivar_triaje' && r.triaje.cita === 'se me salió el alambre y me pincha' && r.avisar === null && r.limpiar === false && r.resultado.ok === true, r);
r = C.decidir({ accion: 'triaje', cita_textual: '', texto_paciente: 'está incómoda, no come' });
t('T2 caso Mariela ("está incómoda, no come", sin palabra clave): deriva igual; si falta la frase usa el mensaje', r.triaje && r.triaje.cita === 'está incómoda, no come', r);
r = C.decidir({ accion: 'triaje', cita_textual: 'me duele', texto_paciente: 'me duele', modo: 'sombra' });
t('T3 sombra: deja la marca (la lee solo el cerebro de esta ejecución) y lo dice simulado', r.triaje && r.resultado.simulado === true && r.avisar === null, r);
r = humano('baja_de_datos', 'no me escriban más', 'Por favor no me escriban más');
t('P4 baja de datos verificada', r.avisar.tomar === true, r);
r = humano('queja', 'esto es una vergüenza', 'Esto es una vergüenza, me hicieron esperar una hora');
t('P5 queja verificada', r.avisar.tomar === true, r);
r = humano('pidio_persona', 'quiero hablar con la secretaria', 'Hola, quiero confirmar mi turno del jueves');
t('P6 el modelo inventa que pidió una persona (la cita no está en el mensaje): NO silencia, avisa [ACCIÓN]', r.avisar.tomar === false && r.limpiar === false && r.resultado.degradado === true && r.avisar.resumen.startsWith('[ACCIÓN]'), r);
r = humano('pidio_persona', 'turno del jueves', 'Hola, quiero confirmar mi turno del jueves');
t('P7 la cita existe pero no expresa el motivo: NO silencia', r.avisar.tomar === false && r.resultado.degradado === true, r);
r = humano('error_de_herramienta', 'confirmar mi turno', 'quiero confirmar mi turno');
t('P8 motivo que no existe ("error de herramienta"): NO silencia', r.avisar.tomar === false && r.resultado.degradado === true, r);
r = humano('pidio_persona', 'ok', 'ok');
t('P9 cita demasiado corta: NO silencia', r.avisar.tomar === false, r);
r = humano('urgencia', 'quiero cambiar el turno', 'quiero cambiar el turno para la tarde');
t('P10 "urgencia" sin síntoma en el texto: NO silencia (va al triaje, que la reclasifica; ante la duda es lo seguro)', r.avisar === null && r.limpiar === false && !!r.triaje, r);
r = C.decidir({ accion: 'humano', motivo: 'pidio_persona', cita_textual: 'quiero hablar con la secretaria', texto_paciente: 'quiero hablar con la secretaria', modo: 'sombra' });
t('P11 sombra: no avisa ni silencia, pero devuelve ok simulado', r.avisar === null && r.limpiar === false && r.resultado.simulado === true, r);
t('P12 acento y mayúsculas no importan', humano('pidio_persona', 'QUIERO HABLAR CON LA SECRETARÍA', 'quiero hablar con la secretaría').avisar.tomar === true);

console.log(`\n${total - fallas}/${total} ${fallas ? 'FALLAS: ' + fallas : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
