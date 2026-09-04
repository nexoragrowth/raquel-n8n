// triaje/gate_red_flags.js — Capa 0 del triaje de urgencias (diseño 2026-09-02).
//
// Gate DETERMINÍSTICO de "red flags": señales que SIEMPRE escalan a la doctora, sin
// importar lo que después diga el clasificador LLM. Mismo principio que el Banlist
// Validator del v6: regex, no modelo. Defensa en profundidad (regla dura #5).
//
// FUENTE ÚNICA DE VERDAD: este archivo se embebe tal cual en el nodo "Gate Red Flags"
// del workflow sombra (scripts/create_triaje_sombra.py lo lee al crear el workflow) y,
// en fases posteriores, en el v6. Editar ACÁ y volver a desplegar — nunca editar en n8n.
// Tests: node triaje/test_gate.js
//
// IMPORTANTE: corre SOLO sobre mensajes que ya entraron por el camino de urgencias.
// Sobre todos los mensajes daría falsos positivos (ej. "no va porque tiene fiebre" es
// una cancelación de turno, caso real #17 de la sombra retrospectiva del 2/9).
//
// Nota técnica: NO usar \b — en JS sin flag `u` no trata "ó/á/í/ñ" como letra, así que
// "se cayó" no matchea. Se usan límites Unicode explícitos (B0/B1) con flag `u`.
//
// Lista BORRADOR pendiente de confirmación de la Dra. Raquel (open-questions.md 2/9).

const B0 = "(?<![\\p{L}\\p{N}])"; // límite de palabra al inicio (Unicode)
const B1 = "(?![\\p{L}\\p{N}])";  // límite de palabra al final (Unicode)
const W = (alts) => new RegExp(B0 + "(?:" + alts + ")" + B1, "iu");

const RED_FLAGS = [
  // Trauma: el aparato/diente se dañó por un golpe, no por uso normal.
  { flag: "trauma",
    re: W("golpe\\p{L}*|se golpe\\p{L}*|me golpe\\p{L}*|ca[ií]da|me ca[ií]|se cay[oó]|se me cay[oó]|accidente|choqu\\p{L}*|choc[oó]|pelotazo|pi[ñn]a|trompada|le pegaron|me pegaron|se peg[oó]") },
  // Sangrado ABUNDANTE (no "me sangra un poco la encía", que es normal con brackets).
  { flag: "sangrado_abundante",
    test: (t) => /sangr|hemorrag/iu.test(t) && W("mucho|much[ií]sim\\p{L}*|abundante|no para|sin parar|no deja de|no se corta|chorro|a chorros").test(t) },
  // Pieza o parte del aparato tragada / aspirada.
  { flag: "tragado",
    re: W("se (?:lo|la) trag[oó]|me (?:lo|la) trag[uú]\\p{L}*|trag[oó] (?:el|la|un|una)|se (?:lo|la) comi[oó]|aspir[oó]") },
  // Hinchazón de cara / cuello (infección).
  { flag: "hinchazon",
    re: W("hinch\\p{L}*|inflamad[oa] (?:la )?(?:cara|cachete|mejilla|cuello)|se le inflam[oó] (?:la )?(?:cara|cachete|mejilla|cuello)") },
  // Dificultad para respirar o tragar.
  { flag: "respirar_tragar",
    re: new RegExp(B0 + "(?:no (?:puede|pued[oe]|podemos)|le cuesta|me cuesta|dificultad|dif[ií]cil)" + B1 + "[^.]{0,30}" + B0 + "(?:respirar|tragar|pasar (?:la )?saliva)" + B1, "iu") },
  // Fiebre.
  { flag: "fiebre", re: W("fiebre") },
  // Dolor intenso que no cede. Incluye hipérbole coloquial ("me está matando") de forma
  // conservadora — la sombra mide cuántas veces dispara; Raquel define el criterio final.
  { flag: "dolor_intenso",
    re: W("dolor (?:muy )?(?:fuerte|intenso|insoportable|terrible|horrible)|much[ií]simo dolor|mucho dolor|no (?:me |le )?(?:baja|cede|calma|pasa|afloja) (?:el |la )?(?:dolor|molestia)|(?:el )?dolor (?:que )?no (?:me |le )?(?:baja|cede|calma|pasa|afloja)|calmantes?|analg[eé]sic\\p{L}*|me est[aá] matando|le est[aá] matando|no (?:lo )?aguant\\p{L}*|no (?:lo )?soport\\p{L}*") },
];

/**
 * @param {string} texto  Mensaje(s) crudos del paciente (+ opcionalmente el resumen del bot).
 * @returns {{escala: boolean, flags: string[]}}
 */
function gateRedFlags(texto) {
  const t = (texto || "").normalize("NFC");
  const flags = [];
  for (const rf of RED_FLAGS) {
    const hit = rf.test ? rf.test(t) : rf.re.test(t);
    if (hit) flags.push(rf.flag);
  }
  return { escala: flags.length > 0, flags };
}

if (typeof module !== "undefined") module.exports = { gateRedFlags, RED_FLAGS };
