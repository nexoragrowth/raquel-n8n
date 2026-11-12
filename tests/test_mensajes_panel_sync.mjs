// test_mensajes_panel_sync.mjs — los MENSAJES FIJOS que la clínica edita en el panel tienen que coincidir con el bot. uso: node tests/test_mensajes_panel_sync.mjs
// El bot reemplaza el texto ESTÁNDAR exacto (OrquestadorCore.aplicarMensajes): si el panel muestra otro estándar, o una clave que el bot no conoce, lo que la
// clínica guarda no se aplica y nadie se entera. Lo cita lib/asiri/mensajes-fijos.ts del panel (repo hermano nexora-whatsapp-agent; si no está, esa parte se salta).
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const O = require('../v7/orquestador_core.js');
const C = require('../v7/clinica_core.js');
let fallas = 0, total = 0;
const t = (n, c, x) => { total++; if (!c) { fallas++; console.log(`  FALLA ${n}${x ? ' → ' + JSON.stringify(x).slice(0, 400) : ''}`); } else console.log(`  ok    ${n}`); };

console.log('BOT');
// (12/11) Los textos de lista de espera los arma clinica_core; orquestador_core los tiene solo para poder reemplazarlos. Si difieren, el reemplazo no se aplica.
for (const k of ['ESPERA', 'ESPERA_SIN_TURNO']) t(`S1 ${k}: igual en clinica_core y orquestador_core`, C.TEXTOS[k] === O.TEXTOS[k], [C.TEXTOS[k], O.TEXTOS[k]]);
t('S2 el texto que arma la lista de espera se reemplaza por el del panel',
  O.aplicarMensajes(C.TEXTOS.ESPERA_SIN_TURNO, O.mensajesDe({ ESPERA_SIN_TURNO: 'Lo anoto en la lista de espera y le avisamos si se libera un lugar.' })) === 'Lo anoto en la lista de espera y le avisamos si se libera un lugar.');
t('S3 cada editable tiene su estándar y es válido', Object.keys(O.MENSAJES_EDITABLES).every((k) => typeof O.TEXTOS[k] === 'string' && O.mensajeInvalido(k, O.TEXTOS[k]) === null));

const PANEL = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'nexora-whatsapp-agent', 'lib', 'asiri', 'mensajes-fijos.ts');
if (!fs.existsSync(PANEL)) {
  console.log(`\n(panel no encontrado en ${PANEL}: se salta la comparación con el panel)`);
} else {
  console.log('\nPANEL ↔ BOT');
  const src = fs.readFileSync(PANEL, 'utf8');
  const panel = {};
  for (const m of src.matchAll(/clave:\s*"([A-Z_]+)"[\s\S]*?estandar:\s*"((?:[^"\\]|\\.)*)"/g)) panel[m[1]] = JSON.parse('"' + m[2] + '"');
  const bot = Object.keys(O.MENSAJES_EDITABLES).sort(), enPanel = Object.keys(panel).sort();
  t('S4 las mismas claves en el panel y en el bot', JSON.stringify(bot) === JSON.stringify(enPanel), { solo_bot: bot.filter((k) => !panel[k]), solo_panel: enPanel.filter((k) => !O.MENSAJES_EDITABLES[k]) });
  for (const k of enPanel) if (O.TEXTOS[k] !== undefined) t(`S5 ${k}: el estándar del panel es el del bot`, panel[k] === O.TEXTOS[k], [panel[k], O.TEXTOS[k]]);
}

console.log(`\n${total - fallas}/${total} ${fallas ? 'FALLAS: ' + fallas : 'TODO OK'}`);
process.exit(fallas ? 1 : 0);
