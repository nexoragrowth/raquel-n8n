const fraseFrustracion = /(^|\s)(repito|ya te dije|ya dije|reitero|como te dije|otra vez te digo|no entiendo|no me entend[eé]s|insisto|cuantas veces)([\s,.!?]|$)/i;
const userText = String(trigger.text || '').toLowerCase();
const is_frustrated = fraseFrustracion.test(userText);

// === LOTE DE TURNOS YA OFRECIDO (2026-09-07, pedido de la Dra. Raquel) ===
// El bot ahora ofrece un BLOQUE ("Tenemos los proximos turnos disponibles:" + seccion mañana + seccion
// tarde). SIN ESTO el paciente que rechaza el bloque recibe EXACTAMENTE el mismo bloque de nuevo, para
// siempre: "Step 5" volvia a buscar desde HOY porque nadie se acordaba de que ya se le habia ofrecido un
// lote (esa es la captura #2 que mando la Dra. el 07/09). Aca se saca del ULTIMO mensaje del bot:
//   (a) el bloque entero, para poder señalarle SOLO la franja que pide sin volver a buscar agenda,
//   (b) desde cuando pedir el lote SIGUIENTE,
//   (c) cuantos bloques se le ofrecieron ya, para escalar en vez de tirarle un tercero.
const MESES_BLOQUE = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                      'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
const HOY_JUJUY = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Argentina/Jujuy' }).format(new Date());
const RE_BLOQUE = /turnos disponibles:/i;
const oferta_bloque = RE_BLOQUE.test(lastBotMsg || '') ? String(lastBotMsg) : '';

// "* Jueves 24 de septiembre 8:00 , 8:40" -> "2026-09-24". El bloque NO lleva año: se usa el actual y, si
// esa fecha ya paso, el que viene (mismo criterio que el parser de aceptacion de "Step 3.5a").
function isoDeLineaBloque(linea) {
  const m = /^\*\s*[^\d]+?(\d{1,2})\s+de\s+([a-zA-Zá-úÁ-Úñ]+)/.exec(String(linea).trim());
  if (!m) return '';
  const mes = MESES_BLOQUE.indexOf(m[2].toLowerCase()) + 1;
  if (!mes) return '';
  const mm = String(mes).padStart(2, '0');
  const dd = String(Number(m[1])).padStart(2, '0');
  const anio = Number(HOY_JUJUY.slice(0, 4));
  const cand = anio + '-' + mm + '-' + dd;
  return cand >= HOY_JUJUY ? cand : (anio + 1) + '-' + mm + '-' + dd;
}

// Ultimo dia ofrecido POR SECCION. El siguiente lote arranca al dia siguiente del MINIMO de las dos: la
// tarde siempre cae mas lejos (la Dra. atiende tarde solo lunes y miercoles), asi que arrancar despues del
// ultimo turno de TARDE se saltearia mañanas mas proximas que el paciente nunca vio.
const ultimoPorSeccion = {};
let seccionBloque = '';
for (const raw of oferta_bloque.split('\n')) {
  const l = raw.trim();
  if (/^por la (mañana|manana|tarde)/i.test(l)) { seccionBloque = /tarde/i.test(l) ? 'tarde' : 'manana'; continue; }
  if (!seccionBloque || l.charAt(0) !== '*') continue;
  const iso = isoDeLineaBloque(l);
  if (iso && (!ultimoPorSeccion[seccionBloque] || iso > ultimoPorSeccion[seccionBloque])) ultimoPorSeccion[seccionBloque] = iso;
}
const ultimosBloque = Object.keys(ultimoPorSeccion).map(k => ultimoPorSeccion[k]).sort();
let oferta_siguiente_desde = '';
if (ultimosBloque.length) {
  const pb = ultimosBloque[0].split('-').map(Number);
  oferta_siguiente_desde = new Date(Date.UTC(pb[0], pb[1] - 1, pb[2] + 1)).toISOString().slice(0, 10);
}

// Cuantos bloques se le mandaron en los ultimos 10 mensajes. El marcador esta en la PRIMERA linea del
// bloque, asi que el slice(0, 300) de historyPairs no lo pierde.
const bloques_ofrecidos = historyPairs.filter(h => h.role === 'bot' && RE_BLOQUE.test(h.content)).length;