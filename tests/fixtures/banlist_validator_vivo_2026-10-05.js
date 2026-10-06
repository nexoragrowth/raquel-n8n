// Banlist Validator - 2026-05-09
// Si el output del bot contiene frases prohibidas, lo reemplaza por escalacion.
// El bot SOLO debe agendar, recordar, pasar info de pago, confirmar/cancelar.
// Cualquier instruccion clinica/operativa o invitacion a la clinica = escalar.

const item = $input.first().json;
const output = (item.output || '').toString();

// FIX 2026-06-04: detectar si el paciente pregunto direccion explicitamente -> NO banear Balcarce 37
let pacienteMsg = '';
try {
  pacienteMsg = ($('Preparar Mensaje Final').first().json.text || '').toString().toLowerCase();
} catch(e) { pacienteMsg = ''; }
// FIX 2026-10-01: si el BOT ofrecio "direccion" en su turno ANTERIOR (menu de info) y el
// paciente contesta con un "todo" GENERICO (sin repetir la palabra), contarlo como pedido
// explicito. Acotado a CATCH-ALLS CORTOS (todo/todos/ambas/las dos): "si"/"dale"/"ok" sueltos
// quedan AFUERA a proposito — es el tipo de respuesta del incidente real de mayo (confirmacion de
// turno, no pedido de info) y destrabarlos ahi reabriria ese riesgo. Seguro por construccion: la
// memoria NUNCA guarda un output que el propio Banlist bloqueo (queda el canned de escalacion en
// su lugar), asi que el contexto solo puede traer menciones de "direccion" ya legitimas.
let botOfrecioDireccionAntes = false;
try {
  const ctx = ($('Build Router Context').first().json.ctx || '').toString();
  const turnos = ctx.split(/\n---\n/);
  const ultimoBot = [...turnos].reverse().find((t) => t.trim().toLowerCase().startsWith('bot:'));
  botOfrecioDireccionAntes = !!(ultimoBot && /\bdirecci[oó]n\b/i.test(ultimoBot));
} catch (e) { botOfrecioDireccionAntes = false; }
const esRespuestaTodoGenerica = /^\s*(todo|todos|toda|todas|las\s+dos|ambas?|lo\s+que\s+sea|toda\s+la\s+informaci[oó]n)\s*[.!]?\s*$/i.test(pacienteMsg);

const pacientePidioDireccion = /\b(d[oó]nde\s*(es|queda|est[aá]n?|ubicad|esta\s*ubicad)|a?\s*d[oó]nde\s+(voy|tengo\s+que\s+ir)|direcci[oó]n|ubicaci[oó]n|c[oó]mo\s*lleg(ar|o|amos)?|en\s*qu[eé]\s*(direcci[oó]n|calle|piso)|qu[eé]\s*direcci[oó]n|\bubi\b|\bmaps\b)\b/i.test(pacienteMsg)
  || (esRespuestaTodoGenerica && botOfrecioDireccionAntes); // ROUND 14: ampliada (donde es/adonde voy/como llego/piso/ubi/maps)

// FIX 2026-10-01 (pedido Lucas): el riesgo real nunca fue la direccion sola, fue combinarla
// con una invitacion a venir SIN turno (incidente real de mayo: "veni ahora mismo"). Esas
// frases de invitacion son reglas APARTE de este banlist, sin excepcion -- siguen bloqueadas
// siempre, esto no las toca. Si el propio mensaje del bot ya aclara "turnos programados",
// el paciente ya sabe que no es venir sin mas -> la direccion sola deja de ser riesgosa ahi.
const outputDiceTurnosProgramados = /turnos?\s+programados?/i.test(output);

// Frases prohibidas (regex case-insensitive)
const BANLIST = [
  // Imperativos clinicos / venirse a la clinica
  { rx: /\bven[íi](te)?\b/i,                           why: 'venite/veni' },
  { rx: /\bveng(a|an|amos)\b/i,                        why: 'venga/vengan' },
  { rx: /\b(los|las|te|le|la|lo|los?\s+espera|las?\s+espera)\s*esperamos\b/i, why: 'los esperamos' },
  { rx: /\bte\s+esper(amos|amos\s+a|an)\b/i,           why: 'te esperamos' },
  { rx: /\b(la|lo)\s+esperamos\b/i,                    why: 'la/lo esperamos' },
  { rx: /\bsalgan?\s+(ya|ahora|para)\b/i,              why: 'salgan ya/para' },
  { rx: /\b(ven[íi]|vengan)\s+ahora\s+mismo\b/i,        why: 'veni/vengan ahora mismo' },
  { rx: /\bahora\s+mismo\b.{0,50}\b(cl[íi]nica|consultorio|aurea|áurea)\b/i, why: 'ahora mismo + clinica' },
  { rx: /\blo\s+antes\s+posible\b.{0,50}\b(cl[íi]nica|consultorio|aurea|áurea|venir)\b/i, why: 'lo antes posible + clinica' },
  // Instrucciones medicas / clinicas
  { rx: /\bguard(á|a|alo|enlo|en|amos|en\s+la)\s+/i,   why: 'guarda/guarden (instruccion)' },
  { rx: /\btraig(a|an|alo|anlo|amos|an\s+(el|la|los|las))\b/i, why: 'traigan (instruccion operativa)' },
  { rx: /\btra(é|e)\s+(el|la|los|las|tu)/i,             why: 'trae (instruccion)' },
  { rx: /\btom(á|a|alo|en|amos)\s+(\d|un|una|el|la|los|las|cada)/i, why: 'toma medicacion/dosis' },
  { rx: /\bsac(á|a|alo|en|amos)\s+(la|el)/i,            why: 'saca (instruccion)' },
  { rx: /\baplic(á|a|ate|en|ense)\b/i,                  why: 'aplica (instruccion medica)' },
  { rx: /\benjuag(á|a|ate|en|ense)\b/i,                 why: 'enjuaga (instruccion medica)' },
  // Diagnostico / opinion medica
  { rx: /\bno\s+te\s+preocup(es|és)\b/i,                why: 'no te preocupes (minimizar sintoma)' },
  { rx: /\bno\s+es\s+(nada\s+)?grave\b/i,               why: 'no es grave (diagnostico)' },
  { rx: /\b(qu[ée]\s+macana|qu[ée]\s+embromado|qu[ée]\s+l[áa]stima)\b/i, why: 'opinion emocional' },
  // Direccion fisica como confirmacion de cita.
  // FIX 2026-06-04: si paciente preguntó explícitamente la dirección, NO banear.
];

// Excepciones: si el paciente pregunto por la direccion explicitamente, "Balcarce 37" si va.
// Esa logica la hara el sub-agente futuro. Por ahora: BAN absoluto sobre Balcarce 37.

let triggered = null;
for (const entry of BANLIST) {
  if (entry.skip_if_paciente_pidio_direccion && pacientePidioDireccion) continue;
  if (entry.skip_if_turnos_programados && outputDiceTurnosProgramados) continue;
  if (entry.rx.test(output)) {
    triggered = entry.why;
    break;
  }
}

if (triggered) {
  const CANNED = 'Recibimos tu mensaje. Estamos derivando tu caso a la Dra. Raquel para que te responda personalmente por este chat. Disculpa la demora.';
  console.log('[BANLIST TRIGGERED]', triggered, '|original:', output.slice(0, 300));

  // ROUND 14: la derivacion que este canned promete no existia en ningun lado - avisar de verdad.
  let phone = '';
  try { phone = ($('Preparar Mensaje Final').first().json.phone || '').toString(); } catch (e) {}
  try {
    await this.helpers.httpRequest({
      method: 'POST',
      url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo',
      qs: {
        phone: phone,
        resumen: 'Banlist bloqueo una respuesta del bot (' + triggered + '). Revisar conversacion y responder al paciente.',
      },
    });
  } catch (e) {
    console.log('[BANLIST] escalation POST fallo:', e.message);
  }

  return [{
    json: {
      ...item,
      output: CANNED,
      banlist_triggered: triggered,
      banlist_original_output: output,
      escalate_to_human: true,
    }
  }];
}

return [{ json: { ...item, banlist_triggered: null, escalate_to_human: false } }];