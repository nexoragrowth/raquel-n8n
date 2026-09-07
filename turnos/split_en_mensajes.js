// "Split en Mensajes" — v6 (O155MqHgOSaNZ9ye)
//
// GUARD 2026-07-21: el Formatting Agent (LLM) a veces DESCARTA partes — típicamente el
// bloque de datos de cuenta (Titular/CUIT/CBU/...). Si el texto ORIGINAL del agente traía
// ese bloque y el formateado lo perdió, usamos el ORIGINAL. Determinístico: no depende de
// que el LLM obedezca.
//
// GUARD 2026-09-07 (a) — FUGA DEL TEXTO INTERNO DE LA TOOL: `buscar_horarios` devuelve en `resultado`
// una instrucción para el agente ("INSTRUCCION (no la copies): ... PROHIBIDO preguntarle al paciente...")
// y, después del centinela, el mensaje del paciente. Si el agente pega `resultado` ENTERO (una sola
// desobediencia del LLM), el paciente lee las tripas del bot. Acá se corta todo hasta el fin de la línea
// del centinela: determinístico, y deja inofensiva cualquier fuga futura de ese texto.
// Si después del centinela no quedara nada (caso que la tool no puede producir: el bloque va pegado en la
// línea siguiente) se busca el encabezado del bloque, y si tampoco está se deja el texto como vino: una
// fuga es fea, pero un mensaje vacío rompe el envío y el paciente se queda sin respuesta.
//
// GUARD 2026-09-07 (b) — EL BLOQUE DE TURNOS NO SE REESCRIBE (pedido de la Dra. Raquel): va al paciente
// EXACTAMENTE como lo arma "Sub-WF - Buscar Horarios Validado" — mes en minúscula, horas sin "hs"
// ("9:20 , 10:40"), dos secciones y las líneas en blanco. El Formatting Agent está entrenado para lo
// contrario (REGLA #3: "Horas SIEMPRE en 24hs con hs", "Fechas con día y mes capitalizados"), así que si
// alguna vez el bloque llega hasta él, lo reescribe. "Necesita Formatting?" ya lo desvía por el camino que
// NO pasa por el LLM; esto es la red determinística de atrás: si el original traía el bloque y el
// formateado no es idéntico, se manda el original. Cuando el bypass funciona, formateado === original y
// esto es un no-op.
const CENTINELA = 'MENSAJE EXACTO PARA EL PACIENTE';
const ENCABEZADO_BLOQUE = 'Tenemos los próximos turnos disponibles:';

function sinInstruccionInterna(t) {
  const i = t.indexOf(CENTINELA);
  if (i === -1) return t;
  const fin = t.indexOf('\n', i);
  const resto = fin === -1 ? '' : t.slice(fin + 1);
  if (resto.trim()) return resto;
  const j = t.indexOf(ENCABEZADO_BLOQUE);
  return j === -1 ? t : t.slice(j);
}

const formateado = sinInstruccionInterna(($input.first().json.output || '').toString());
let original = '';
try { original = ($('Banlist Validator').first().json.output || '').toString(); } catch (e) { original = ''; }
original = sinInstruccionInterna(original);
const perdioDatos = /\bCBU\b/i.test(original) && !/\bCBU\b/i.test(formateado);
const tocoElBloque = /turnos disponibles:/i.test(original) && original !== formateado;
const output = (perdioDatos || tocoElBloque) ? original : formateado;
const remoteJid = $('Preparar Mensaje Final').first().json.remoteJid;
const phone = $('Preparar Mensaje Final').first().json.phone;

// Split by --- separator
const parts = output.split('---').map(p => p.trim()).filter(p => p.length > 0);

// If no separator found, send as single message
if (parts.length === 0) {
  return [{ json: { message: output.trim(), remoteJid, phone, partIndex: 0, totalParts: 1 } }];
}

// Return each part as a separate item
return parts.map((msg, i) => ({
  json: {
    message: msg,
    remoteJid,
    phone,
    partIndex: i,
    totalParts: parts.length
  }
}));
