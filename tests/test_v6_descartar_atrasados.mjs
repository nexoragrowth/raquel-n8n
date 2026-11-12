// Test del "Webhook Validator" del v6 con el paso 4 (mensajes atrasados). Recibe el jsCode por stdin y lo corre como lo corre n8n
// (cuerpo de función async con $input / $env), con payloads de Evolution GO reales (forma del 11/11/2026).
import { readFileSync } from 'node:fs';

const code = readFileSync(0, 'utf8');
const TOKEN = (code.match(/const TOKEN_INSTANCIA = '([^']+)'/) || [])[1];
if (!TOKEN) { console.error('no encuentro TOKEN_INSTANCIA en el código'); process.exit(1); }

const AHORA = Date.parse('2026-11-11T16:10:00Z');
const RealDate = Date;
globalThis.Date = class extends RealDate { constructor(...a) { super(...(a.length ? a : [AHORA])); } static now() { return AHORA; } };
Date.parse = RealDate.parse;
console.log = () => {};

const correr = async (body) => {
  const fn = new Function('$input', '$env', `return (async () => {\n${code}\n})();`);
  return fn({ first: () => ({ json: { body, headers: {} } }) }, {});
};
const msg = (Timestamp, extra = {}) => ({ instanceToken: TOKEN, event: 'Message', data: { Info: { ID: 'ABC', Chat: '5493880000000@s.whatsapp.net', IsFromMe: false, ...(Timestamp === undefined ? {} : { Timestamp }), ...extra }, Message: { conversation: 'hola' } } });

let fallos = 0;
const t = async (nombre, body, pasa) => {
  const r = await correr(body);
  const ok = pasa ? (Array.isArray(r) && r.length === 1) : (Array.isArray(r) && r.length === 0);
  if (!ok) { fallos++; process.stderr.write(`FALLA ${nombre}: devolvió ${Array.isArray(r) ? r.length + ' item(s)' : typeof r}\n`); }
};

await t('mensaje de ahora pasa', msg('2026-11-11T13:09:30-03:00'), true);
await t('14 min de atraso pasa', msg('2026-11-11T12:56:00-03:00'), true);
await t('16 min de atraso se descarta', msg('2026-11-11T12:54:00-03:00'), false);
await t('comprobante del 09/11 11:40 (2 días) se descarta', msg('2026-11-09T11:40:25-03:00'), false);
await t('"Me lo cambiaron" 09/11 09:02 se descarta', msg('2026-11-09T09:02:07-03:00'), false);
await t('fromMe viejo (staff) también se descarta: no marca modo humano tarde', msg('2026-11-10T10:00:00-03:00', { IsFromMe: true }), false);
await t('sin Timestamp: falla abierta (pasa)', msg(undefined), true);
await t('Timestamp ilegible: falla abierta (pasa)', msg('cualquier cosa'), true);
await t('Timestamp en UTC (Z) reciente pasa', msg('2026-11-11T16:05:00Z'), true);
await t('reloj del celular 2 min adelantado (futuro) pasa', msg('2026-11-11T13:12:00-03:00'), true);
await t('sin instanceToken se sigue descartando (seguridad intacta)', { ...msg('2026-11-11T13:09:30-03:00'), instanceToken: 'otro' }, false);
await t('payload sin Info se sigue descartando', { instanceToken: TOKEN, data: {} }, false);

console.log = (...a) => process.stdout.write(a.join(' ') + '\n');
console.log(fallos ? `${fallos} fallo(s)` : '12/12 casos OK');
process.exit(fallos ? 1 : 0);
