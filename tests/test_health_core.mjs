// test_health_core.mjs — Health Check auto-reparable (incidente webhook vacío 06-08/10/2026), offline. uso: node tests/test_health_core.mjs
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const HC = require('../v7/health_core.js');

const W = HC.WEBHOOK;
const DL_OK = { data: { id: 1, nombre: 'Sucursal' } };
const inst = (o) => ({ data: [{ name: 'Waves', connected: false, webhook: '' }, { name: 'raquel', id: 'inst-1', token: 'SECRETO-TOKEN', connected: true, webhook: W, events: 'MESSAGE', ...o }] });
// Fechas en UTC; Jujuy = UTC-3. Jueves 08/10/2026 15:00 Jujuy = 18:00Z.
const JUE_15 = Date.parse('2026-10-08T18:00:00Z');
const JUE_10 = Date.parse('2026-10-08T13:00:00Z');
const SAB_12 = Date.parse('2026-10-10T15:00:00Z');
const JUE_22 = Date.parse('2026-10-09T01:00:00Z');   // jueves 22:00 Jujuy
const LUN_10 = Date.parse('2026-10-19T13:00:00Z');   // lunes 19/10 10:00 Jujuy (el 12/10 es feriado: ver caso 7h)
const hace = (ms, h) => new Date(ms - h * 3600e3).toISOString();
const base = (o) => ({ dentalink: DL_OK, evolution: inst(), ultimo: hace(JUE_15, 0.5), consultaOk: true, ahora: JUE_15, estado: {}, ...o });

let fallas = 0, total = 0;
const caso = (nombre, cond, detalle) => { total++; if (cond) console.log(`  ok    ${nombre}`); else { fallas++; console.log(`  FALLA ${nombre}`, detalle !== undefined ? JSON.stringify(detalle) : ''); } };
const sinToken = (x) => !JSON.stringify(x).includes('SECRETO-TOKEN');

console.log('Webhook');
let r = HC.evaluar(base());
caso('1 webhook ok + conectado + tráfico → nada', !r.reparar && r.lineas.length === 0 && HC.salida(r.lineas, JUE_15).skip_alert === true, r);
r = HC.evaluar(base({ evolution: inst({ webhook: '' }) }));
caso('2 webhook vacío + conectado → reparar (con instanceId, sin alerta previa)', r.reparar && r.instanciaId === 'inst-1' && r.lineas.length === 0, r);
caso('2b el resultado de evaluar no lleva el token', sinToken(r), r);
r = HC.evaluar(base({ evolution: inst({ webhook: 'https://otro.ejemplo.com/webhook/x' }) }));
caso('3 webhook distinto + conectado → reparar', r.reparar && r.instanciaId === 'inst-1', r);
r = HC.evaluar(base({ evolution: inst({ webhook: W + '/' }) }));
caso('3b webhook con barra de más → reparar (comparación exacta)', r.reparar, r);

console.log('Desconexión / instancia');
r = HC.evaluar(base({ evolution: inst({ connected: false, webhook: '', disconnect_reason: 'websocket closed' }) }));
let s = HC.salida(r.lineas, JUE_15);
caso('4 desconectado → NO repara, alerta [ACCIÓN] QR', !r.reparar && s.skip_alert === false && /\[ACCIÓN\] WhatsApp desconectado: hay que escanear el QR/.test(s.alert_message) && s.remoteJid === '5491161461034@s.whatsapp.net', s);
caso('4b desconectado → no suma alerta de sin tráfico (la causa ya está dicha)', r.lineas.filter((l) => l.includes('No entra ningún mensaje')).length === 0, r.lineas);
r = HC.evaluar(base({ evolution: { data: [{ name: 'Waves', connected: true, webhook: W }] } }));
s = HC.salida(r.lineas, JUE_15);
caso('5 instancia "raquel" no encontrada → alerta [ACCIÓN], sin reparar', !r.reparar && /\[ACCIÓN\] La instancia de WhatsApp "raquel" no existe/.test(s.alert_message), s);
r = HC.evaluar(base({ evolution: { error: 'ECONNREFUSED' } }));
caso('5b Evolution no responde → alerta [ACCIÓN]', !r.reparar && /Evolution \(WhatsApp\) no responde/.test(HC.salida(r.lineas, JUE_15).alert_message), r);
r = HC.evaluar(base({ dentalink: { error: 'timeout' } }));
caso('5c Dentalink caído → alerta como antes (❌ Dentalink…)', /❌ Dentalink API no responde como esperado/.test(HC.salida(r.lineas, JUE_15).alert_message) && /Health Check FAIL/.test(HC.salida(r.lineas, JUE_15).alert_message), r);

console.log('Sin tráfico');
r = HC.evaluar(base({ ultimo: hace(JUE_15, 6.5) }));
s = HC.salida(r.lineas, JUE_15);
caso('6 en horario, 6.5 h sin mensajes → alerta [ACCIÓN] y marca anti-spam', /\[ACCIÓN\] No entra ningún mensaje desde hace 6 h/.test(s.alert_message) && r.estado.ultimaAlertaSinTrafico === JUE_15, s);
r = HC.evaluar(base({ ultimo: hace(JUE_15, 5) }));
caso('6b en horario, 5 h sin mensajes → nada', r.lineas.length === 0, r);
r = HC.evaluar(base({ ultimo: null }));
caso('6c tabla vacía (max = null) en horario → alerta "nunca"', r.lineas.some((l) => l.includes('nunca')), r);
r = HC.evaluar(base({ ahora: SAB_12, ultimo: hace(SAB_12, 30) }));
caso('7 sábado, 30 h sin mensajes → nada', r.lineas.length === 0 && !r.estado.ultimaAlertaSinTrafico, r);
r = HC.evaluar(base({ ahora: JUE_22, ultimo: hace(JUE_22, 10) }));
caso('7b jueves 22:00 (fuera de horario), 10 h sin mensajes → nada', r.lineas.length === 0, r);
r = HC.evaluar(base({ ahora: JUE_10, ultimo: hace(JUE_10, 14) }));
caso('7c jueves 10:00, último a las 20:00 del día anterior → 1 h hábil → nada', r.lineas.length === 0, r);
r = HC.evaluar(base({ ahora: LUN_10, ultimo: '2026-10-16T22:00:00Z' }));   // viernes 19:00 Jujuy
caso('7d lunes 10:00, último viernes 19:00 → 2 h hábiles → nada', r.lineas.length === 0, r);
r = HC.evaluar(base({ ahora: LUN_10, ultimo: '2026-10-16T15:00:00Z' }));   // viernes 12:00 Jujuy → 8 h (vie) + 1 h (lun)
caso('7e lunes 10:00, último viernes 12:00 → 9 h hábiles → alerta', r.lineas.some((l) => l.includes('No entra ningún mensaje')), r);
r = HC.evaluar(base({ ultimo: hace(JUE_15, 7), consultaOk: false }));
caso('7f la consulta a la base falló → no se inventa una alerta de tráfico', r.lineas.length === 0, r);
r = HC.evaluar(base({ evolution: inst({ webhook: '' }), ultimo: hace(JUE_15, 7) }));
caso('7g webhook roto + sin tráfico → solo repara (no alerta de tráfico aparte)', r.reparar && r.lineas.length === 0, r);

console.log('Anti-spam');
r = HC.evaluar(base({ ultimo: hace(JUE_15, 7), estado: { ultimaAlertaSinTrafico: JUE_15 - 5.5 * 3600e3 } }));
caso('8 ya alertó hace 5.5 h → no repite', r.lineas.length === 0 && r.estado.ultimaAlertaSinTrafico === JUE_15 - 5.5 * 3600e3, r);
r = HC.evaluar(base({ ultimo: hace(JUE_15, 7), estado: { ultimaAlertaSinTrafico: JUE_15 - 6 * 3600e3 } }));
caso('8b alertó hace 6 h → vuelve a alertar', r.lineas.length === 1 && r.estado.ultimaAlertaSinTrafico === JUE_15, r);
r = HC.evaluar(base({ ultimo: hace(JUE_15, 7), estado: { ultimaAlertaSinTrafico: JUE_15 - 7 * 3600e3, otraCosa: 1 } }));
caso('8c conserva otras claves del staticData', r.estado.otraCosa === 1, r.estado);

console.log('Verificación de la reparación');
let v = HC.verificar({ reparacion: { status: 200 }, recheck: inst() });
s = HC.salida([v.linea], JUE_15);
caso('9 reparación OK → [AUTO-REPARADO], cabecera sin FAIL', v.ok && /\[AUTO-REPARADO\] El webhook de WhatsApp estaba vacío\/cambiado; se repuso solo/.test(s.alert_message) && !/FAIL/.test(s.alert_message) && s.skip_alert === false, s);
v = HC.verificar({ reparacion: { status: 401, error: 'not authorized' }, recheck: inst({ webhook: '' }) });
s = HC.salida([v.linea], JUE_15);
caso('10 reparación fallida (401, webhook sigue vacío) → [ACCIÓN] con motivo', !v.ok && /\[ACCIÓN\] Webhook de WhatsApp roto y no se pudo reparar: el pedido de reparación respondió 401/.test(s.alert_message) && /sigue webhook vacío/.test(s.alert_message) && /FAIL/.test(s.alert_message), s);
v = HC.verificar({ reparacion: { status: 200 }, recheck: inst({ connected: false }) });
caso('10b POST 200 pero la instancia quedó desconectada → [ACCIÓN]', !v.ok && /quedó desconectada/.test(v.linea), v);
v = HC.verificar({ reparacion: { status: 200 }, recheck: { error: 'timeout' } });
caso('10c no se pudo releer → [ACCIÓN]', !v.ok && /no pude releer/.test(v.linea), v);
caso('10d ninguna salida lleva el token', sinToken([v, s, HC.salida(HC.evaluar(base({ evolution: inst({ webhook: '' }) })).lineas, JUE_15)]));
s = HC.salida([HC.verificar({ reparacion: { status: 200 }, recheck: inst() }).linea, '❌ Dentalink API no responde como esperado'], JUE_15);
caso('10e reparado + otro problema → cabecera FAIL', /FAIL/.test(s.alert_message) && s.healthy === false, s);

console.log('Eventos suscriptos (revisión 08/10)');
r = HC.evaluar(base({ evolution: inst({ events: '' }) }));
caso('11 webhook bien pero events vacío → reparar', r.reparar && r.cuerpo && r.cuerpo.subscribe.includes('MESSAGE'), r);
r = HC.evaluar(base({ evolution: inst({ events: 'CONNECTION' }) }));
caso('11b events sin MESSAGE → reparar y CONSERVA CONNECTION', r.reparar && JSON.stringify(r.cuerpo.subscribe) === '["MESSAGE","CONNECTION"]', r.cuerpo);
r = HC.evaluar(base({ evolution: inst({ events: 'message, READ_RECEIPT' }) }));
caso('11c events "message, READ_RECEIPT" (minúsculas/espacios) → sano', !r.reparar && r.lineas.length === 0, r);
r = HC.evaluar(base({ evolution: inst({ events: 'ALL' }) }));
caso('11d events ALL → sano', !r.reparar, r);
let v2 = HC.verificar({ reparacion: { status: 200 }, recheck: inst({ events: '' }), estado: {}, ahora: JUE_15 });
caso('11e verificar: webhook bien pero events vacío → NO ok', !v2.ok && /sin el evento MESSAGE/.test(v2.linea), v2);

console.log('Body de la reparación (no pisar config)');
let c = HC.cuerpoReparacion({ webhook: '', events: 'MESSAGE,QRCODE', rabbitmqEnable: 'enabled', websocketEnable: '', natsEnable: '' });
caso('12 body: webhook correcto + eventos actuales + rabbitmq conservado', c.webhookUrl === W && JSON.stringify(c.subscribe) === '["MESSAGE","QRCODE"]' && c.rabbitmqEnable === 'enabled' && c.websocketEnable === '' && c.natsEnable === '', c);
c = HC.cuerpoReparacion({ webhook: '', events: '' });
caso('12b body con events vacío → ["MESSAGE"] y los enable en ""', JSON.stringify(c.subscribe) === '["MESSAGE"]' && c.natsEnable === '', c);
caso('12c el body no lleva el token', sinToken(HC.cuerpoReparacion(inst().data[1])));

console.log('Formato de Evolution cambiado');
const sinCampo = (k) => { const d = inst(); delete d.data[1][k]; return d; };
r = HC.evaluar(base({ evolution: sinCampo('webhook') }));
caso('13 falta el campo webhook → NO repara, alerta de formato 1 vez', !r.reparar && r.lineas.length === 1 && /cambió el formato.*webhook/.test(r.lineas[0]) && r.estado.ultimaAlertaFormato === JUE_15, r);
r = HC.evaluar(base({ evolution: sinCampo('webhook'), estado: { ultimaAlertaFormato: JUE_15 - 3600e3 } }));
caso('13b formato cambiado, ya alertó hace 1 h → silencio', !r.reparar && r.lineas.length === 0, r);
r = HC.evaluar(base({ evolution: sinCampo('events') }));
caso('13c falta el campo events → NO repara, alerta de formato', !r.reparar && /falta: events/.test(r.lineas.join()), r);
r = HC.evaluar(base({ evolution: sinCampo('webhook'), ultimo: hace(JUE_15, 7), estado: { ultimaAlertaFormato: JUE_15 - 3600e3 } }));
caso('13d formato cambiado + 7 h sin tráfico → la red de "sin tráfico" sigue activa', r.lineas.some((l) => l.includes('No entra ningún mensaje')), r);

console.log('Corte de reintentos');
r = HC.evaluar(base({ evolution: inst({ webhook: '' }), estado: { repFallas: 2, repUltimoIntento: JUE_15 - 1800e3 } }));
caso('14 2 fallas seguidas → todavía repara y marca el intento', r.reparar && r.estado.repUltimoIntento === JUE_15, r);
r = HC.evaluar(base({ evolution: inst({ webhook: '' }), estado: { repFallas: 3, repUltimoIntento: JUE_15 - 1800e3 } }));
caso('14b 3 fallas, último intento hace 30 min → NO repara, alerta de pausa', !r.reparar && /falló 3 veces seguidas/.test(r.lineas.join()) && r.estado.repUltimaAlertaPausa === JUE_15, r);
r = HC.evaluar(base({ evolution: inst({ webhook: '' }), estado: { repFallas: 3, repUltimoIntento: JUE_15 - 1800e3, repUltimaAlertaPausa: JUE_15 - 3600e3 } }));
caso('14c en pausa y ya avisó hace 1 h → silencio total (ni POST ni alerta)', !r.reparar && r.lineas.length === 0, r);
r = HC.evaluar(base({ evolution: inst({ webhook: '' }), estado: { repFallas: 5, repUltimoIntento: JUE_15 - 2 * 3600e3 } }));
caso('14d en pausa, pasaron 2 h → reintenta', r.reparar, r);
r = HC.evaluar(base({ estado: { repFallas: 5, repUltimoIntento: JUE_15 - 1800e3 } }));
caso('14e se ve sano → repFallas vuelve a 0', !r.reparar && r.estado.repFallas === 0, r);
v2 = HC.verificar({ reparacion: { status: 401, error: 'x' }, recheck: inst({ webhook: '' }), estado: { repFallas: 2 }, ahora: JUE_15 });
caso('14f verificar fallido suma la falla y avisa que entra en pausa a la 3.ª', !v2.ok && v2.estado.repFallas === 3 && /cada 2 h/.test(v2.linea), v2);
v2 = HC.verificar({ reparacion: { status: 200 }, recheck: inst(), estado: { repFallas: 2 }, ahora: JUE_15 });
caso('14g verificar ok → repFallas 0 y registra el éxito', v2.ok && v2.estado.repFallas === 0 && v2.estado.repExitos.length === 1 && v2.lineas.length === 1, v2);
v2 = HC.verificar({ reparacion: { status: 200 }, recheck: inst(), estado: { repExitos: [JUE_15 - 3 * 3600e3, JUE_15 - 30 * 3600e3] }, ahora: JUE_15 });
s = HC.salida(v2.lineas, JUE_15);
caso('14h 2.ª reparación en 24 h → [AUTO-REPARADO] + [ACCIÓN] "algo lo está borrando", cabecera FAIL', v2.ok && v2.estado.repExitos.length === 2 && /algo lo está borrando/.test(s.alert_message) && /FAIL/.test(s.alert_message), s);

console.log('Consulta de tráfico rota');
r = HC.evaluar(base({ consultaOk: false, estado: { consultaFallas: 2 } }));
caso('15 3.ª falla de la consulta → cuenta, sin alerta', r.estado.consultaFallas === 3 && r.lineas.length === 0, r);
r = HC.evaluar(base({ consultaOk: false, estado: { consultaFallas: 3 } }));
caso('15b 4.ª falla → [AVISO] y marca', r.estado.consultaFallas === 4 && /\[AVISO\].*mensajes_entrantes_live/.test(r.lineas.join()) && r.estado.ultimaAlertaConsulta === JUE_15, r);
r = HC.evaluar(base({ consultaOk: false, estado: { consultaFallas: 10, ultimaAlertaConsulta: JUE_15 - 5 * 3600e3 } }));
caso('15c ya avisó hace 5 h → silencio (1 por día)', r.lineas.length === 0, r);
r = HC.evaluar(base({ estado: { consultaFallas: 10 } }));
caso('15d la consulta vuelve → contador a 0', r.estado.consultaFallas === 0, r);

console.log('Feriados y secretos');
const LUN_FER = Date.parse('2026-10-12T15:00:00Z');   // lunes 12/10 12:00 Jujuy, feriado
r = HC.evaluar(base({ ahora: LUN_FER, ultimo: hace(LUN_FER, 60) }));
caso('7h feriado 12/10, 60 h sin mensajes → nada', r.lineas.length === 0, r);
caso('7i horasHabiles vie 16:00 → mar 13/10 10:00 cruza fin de semana + feriado = 4 + 1 h',
  Math.abs(HC.horasHabiles(Date.parse('2026-10-09T19:00:00Z'), Date.parse('2026-10-13T13:00:00Z')) - 5) < 1e-9, HC.horasHabiles(Date.parse('2026-10-09T19:00:00Z'), Date.parse('2026-10-13T13:00:00Z')));
r = HC.evaluar(base({ evolution: { message: 'otra forma', instances: [{ name: 'raquel', token: 'SECRETO-TOKEN', qrcode: 'data:x' }] } }));
caso('16 Evolution responde con otra forma que trae el token → el Detalle lo tapa', /Evolution \(WhatsApp\) no responde/.test(r.lineas.join()) && sinToken(r) && sinToken(HC.salida(r.lineas, JUE_15)), r.lineas);
r = HC.evaluar(base({ dentalink: { error: 'x', apikey: 'SECRETO-TOKEN' } }));
caso('16b Detalle de Dentalink también tapa claves', sinToken(r), r.lineas);

console.log(`\n${total - fallas}/${total} ok`);
process.exit(fallas ? 1 : 0);
