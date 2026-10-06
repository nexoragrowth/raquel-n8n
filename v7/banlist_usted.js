// banlist_usted.js — v7 · banlist de la salida de Asiri, en VOSEO y en USTED, con límites de palabra Unicode. Fuente de verdad en el repo (se inlinea en un nodo Code de n8n).
// El banlist vivo del v6 (Banlist Validator) esta escrito en voseo: "venite", "guarda", "traigan". Asiri habla de usted ("acérquese", "tome", "guárdela"),
// que hoy no dispara nada. Regla del proyecto: las reglas del incidente del 09/05 (invitar a venir, instrucciones clínicas, diagnóstico, dirección como invitación)
// tienen que estar en dos capas; esta es la última línea. Devuelve { bloquea:boolean, why }.
//   contexto: { pacientePidioDireccion:boolean }
const BanlistUsted = (() => {
  const W = (src) => new RegExp(String.raw`(?<![\p{L}])(?:` + src + String.raw`)(?![\p{L}])`, 'iu');
  // Un turno YA AGENDADO nombrado con fecha ("su turno del viernes 16/10") vuelve legítimo recordar "puede venir acompañada": la invitación sin turno es el riesgo.
  const TURNO_CON_FECHA = /\bturno\s+(?:del|de|para\s+el|para\s+la|el)\s+(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|\d)/i;
  const REGLAS = [
    // --- Instrucciones clínicas / operativas
    { why: 'guarde/guarda (instrucción)', rx: W('guárd(?:ela|elo|ese|ense|alo|ala)|guard(?:á|a|e|en)\\s+(?:la|el|las|los|esa|ese|bien)'), skip_si_turno: false },
    { why: 'traiga/traé (instrucción)', rx: W('tra(?:iga|igan|igalo|igala|é|e|ele|igase)\\s+(?:el|la|los|las|su|sus|tu|tus|dni|documento|estudios?|radiograf[ií]as?)'), skip_si_turno: true },
    { why: 'tome/tomá medicación', rx: W('(?:tome|tomen|tomá|tómese|tomate)\\s+(?:\\d|un|una|el|la|los|las|cada|ibuprofeno|paracetamol|analg[eé]sico|antiinflamatorio|antibi[oó]tico|algo)'), skip_si_turno: false },
    { why: 'saque/sacá (instrucción)', rx: W('(?:saque|saquen|sacá|sáquese)\\s+(?:la|el|los|las)\\b'), skip_si_turno: false },
    { why: 'aplique/aplicá (instrucción médica)', rx: W('aplí(?:quese|quen)|aplique(?:n)?\\s+(?:hielo|fr[ií]o|calor|cera|gel|pasta|crema)|aplic(?:á|ate)\\s+(?:hielo|fr[ií]o|calor|cera|gel|pasta|crema)'), skip_si_turno: false },
    { why: 'enjuague/enjuagá', rx: W('enjuáguese|enjuaguese|enjuague(?:n)?(?:se)?\\s+(?:con|la\\s+boca)|enjuag(?:á|ate)'), skip_si_turno: false },
    { why: 'coloque/colocá', rx: W('colóque(?:se|nse)|coloque(?:n)?\\s+(?:cera|algod[oó]n|hielo|el|la)|coloc(?:á|ate)\\s+(?:cera|algod[oó]n|hielo)'), skip_si_turno: false },
    { why: 'ponga/poné cera, hielo, algodón', rx: W('(?:ponga|pongan|póngase|poné|ponete)\\s+(?:cera|hielo|algod[oó]n|fr[ií]o|calor)'), skip_si_turno: false },
    { why: 'evite/deje de comer', rx: W('evit(?:e|en)\\s+(?:comer|masticar|tocar|mover)|no\\s+(?:coma|mastique|toque)\\b'), skip_si_turno: false },
    // --- Diagnóstico / opinión
    { why: 'no se preocupe / no te preocupes', rx: W('no\\s+(?:se\\s+)?preocup(?:e|es|és|ese)|no\\s+te\\s+preocup(?:es|és)'), skip_si_turno: false },
    { why: 'no es grave / es normal (diagnóstico)', rx: W('no\\s+es\\s+(?:nada\\s+)?grave|es\\s+(?:algo\\s+)?(?:normal|habitual|com[uú]n)\\s+(?:que|en)|es\\s+normal\\b|no\\s+es\\s+nada\\b'), skip_si_turno: false },
    { why: 'opinión emocional', rx: W('qu[eé]\\s+(?:macana|embromado|l[aá]stima|feo)'), skip_si_turno: false },
    // --- Promesas que la clínica no puede cumplir
    { why: 'le aviso si se libera', rx: W('(?:le|te)\\s+avis(?:o|aremos|amos)\\s+si\\s+se\\s+(?:libera|desocupa|cancela)'), skip_si_turno: false },
  ];

  // INVITACIÓN: decir "los esperamos", "venga", "acérquese" NO está mal por sí solo: es el negocio ("lo esperamos el día de su turno"). Lo que fue peligroso el 09/05
  // fue invitar a ir AHORA y SIN turno a una clínica cerrada. Entonces: se bloquea si invita a ir de inmediato (siempre), o si invita sin ninguna referencia a un turno concreto.
  const INVITA = W(String.raw`ven[ií]te?|veng(?:a|an|amos)|acérque(?:se|nse)|acercarse|acérca(?:te|se)|pase(?:n)?\s+por|pasar\s+por\s+(?:la\s+)?(?:cl[ií]nica|consultorio)|(?:los|las|lo|la|te|le|les)\s+esperamos|pued(?:e|en)\s+(?:venir|pasar|acercarse)|(?:lo|la|los|las)\s+(?:atendemos|vemos|recibimos)\s+(?:hoy|ahora|ya)|salg(?:a|an)\s+(?:ya|ahora|para)|dirí(?:ja|jase|jan)se`);
  const INMEDIATO = /\b(?:ahora\s+mismo|ya\s+mismo|de\s+inmediato|enseguida|cuanto\s+antes|lo\s+antes\s+posible)\b/i;
  const TURNO_CONCRETO = /\bturno\b.{0,70}(?:\d{1,2}[:.]\d{2}|\d{1,2}\/\d{1,2}|\b(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado)\b)|\bd[ií]a\s+(?:de|del)\s+(?:su|la|el)\s+(?:turno|consulta|cita)\b|\ba\s+las\s+\d{1,2}[:.]\d{2}/i;
  const DIRECCION = /balcarce\s*(?:n[º°.]?\s*)?37/i;

  function revisar(texto, contexto) {
    const t = String(texto || '');
    const conTurno = TURNO_CON_FECHA.test(t);
    if (INVITA.test(t)) {
      if (INMEDIATO.test(t)) return { bloquea: true, why: 'invita a ir de inmediato' };
      if (!TURNO_CONCRETO.test(t)) return { bloquea: true, why: 'invita a ir sin referirse a un turno' };
    }
    for (const r of REGLAS) {
      if (r.skip_si_turno && conTurno) continue;
      if (r.rx.test(t)) return { bloquea: true, why: r.why };
    }
    if (DIRECCION.test(t) && !(contexto && contexto.pacientePidioDireccion)) return { bloquea: true, why: 'dirección sin que la pidan' };
    return { bloquea: false, why: null };
  }
  return { revisar, REGLAS };
})();
if (typeof module !== 'undefined') module.exports = BanlistUsted;
