// Fallback Output: protege de silencios accidentales ([NO_REPLY])
const CANNED_SECRETARIA = 'Hola! Ya le transmito su consulta a la secretaria para que le responda en su horario de atención. ¡Muchas gracias!';

let text = '';
try {
  text = ($('Preparar Mensaje Final').first().json.text || '').trim();
} catch (e) { text = ''; }

const norm = text.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase().replace(/[!.,;:]+/g, '').trim();

// Cierres genuinos que SI deben ser silenciosos
const CIERRES = ['ok', 'dale', 'gracias', 'muchas gracias', 'listo', 'perfecto', 'joya', 'genial', 'de nada', 'chau', 'adios', 'buenisimo'];
const esCierrePuro = CIERRES.includes(norm) || norm.length === 0;

const items = $input.all();
return items.map(it => {
  let output = (it.json.output || '').trim();
  
  // Si vino vacio o como [NO_REPLY], pero el paciente hizo una consulta real (no es un cierre puro ni emoji)
  if ((!output || output === '[NO_REPLY]') && !esCierrePuro) {
    // Si tiene mas de 3 caracteres y no es un cierre, NO clavar el visto: escalar amablemente
    output = CANNED_SECRETARIA;
  } else if (!output) {
    output = '👍';
  }
  
  return { json: { ...it.json, output } };
});