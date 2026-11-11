// chequeo_salida.js — v7 · chequeo BIDIRECCIONAL de lo que Asiri le va a decir al paciente. Fuente de verdad en el repo (se inlinea en un nodo Code de n8n).
// Lee SOLO el libro de escrituras que dejan las herramientas (nunca lo que diga el modelo) y las ofertas registradas por buscar_horarios.
//   libros : [{ ok:boolean, tipo:'cambio'|'reserva'|'sumar'|'cancelacion'|'confirmacion', readback_text, parcial?:boolean }]   (TODAS las escrituras de ESTA ejecucion, en orden; acepta también `libro` suelto)
//   ofertas: [{fecha:'YYYY-MM-DD', hora:'HH:MM'}]   (lo que buscar_horarios ofrecio)
//   propuesta_readback: texto del read-back de una propuesta hecha en ESTA ejecucion (todavia no ejecutada), o null
// devuelve { accion:'pasar'|'reemplazar', texto, motivo, avisar:null|{nivel,texto} }
const ChequeoSalida = (() => {
  const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const sinT = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const normTexto = (x) => sinT(x).replace(/[^a-z0-9:/ ]+/g, ' ').replace(/\s+/g, ' ').trim();
  const hh = (h, m) => String(Number(h)).padStart(2, '0') + ':' + m;

  // Todas las parejas fecha(sin año)+hora que aparecen en el texto. Una hora se asocia a la ULTIMA fecha vista en la misma linea
  // ("* Jueves 22 de octubre 8:00 , 9:20" → dos parejas; "el jueves 22/10 a las 09:20" → una).
  function parejas(texto) {
    const out = [];
    for (const linea of String(texto || '').split('\n')) {
      const l = sinT(linea);
      const tokens = [];
      for (const m of l.matchAll(/(\d{1,2})\s+de\s+([a-z]+)/g)) { const mes = MESES.indexOf(m[2] === 'setiembre' ? 'septiembre' : m[2]) + 1; if (mes) tokens.push({ i: m.index, tipo: 'f', md: `${String(mes).padStart(2, '0')}-${String(Number(m[1])).padStart(2, '0')}` }); }
      for (const m of l.matchAll(/\b(\d{1,2})\/(\d{1,2})\b/g)) tokens.push({ i: m.index, tipo: 'f', md: `${String(Number(m[2])).padStart(2, '0')}-${String(Number(m[1])).padStart(2, '0')}` });
      for (const m of l.matchAll(/\b(\d{1,2}):(\d{2})\b/g)) tokens.push({ i: m.index, tipo: 'h', h: hh(m[1], m[2]) });
      // (07/10) "jueves 22" sin mes: fecha con mes desconocido (xx-22). Antes la hora siguiente se pegaba a la fecha anterior de la línea
      // ("cambiar su turno del 16/10 10:30 por jueves 22 a las 8:00" → "16/10 08:00", inventado; examen DANA-04).
      // (11/11) "jueves 8:00–12:00" es un HORARIO de atención, no "el jueves 8": un número seguido de ":" es hora (el agente lo bloqueaba al dar los horarios del Conocimiento).
      for (const m of l.matchAll(/\b(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)\s+(\d{1,2})\b(?!\s*(?:de\s+[a-z]|\/)|:\d)/g)) tokens.push({ i: m.index, tipo: 'f', md: `xx-${String(Number(m[1])).padStart(2, '0')}` });
      tokens.sort((a, b) => a.i - b.i);
      let fecha = null;
      for (const t of tokens) { if (t.tipo === 'f') fecha = t.md; else if (fecha) out.push(`${fecha} ${t.h}`); }
    }
    return out;
  }
  const clave = (o) => `${o.fecha.slice(5)} ${String(o.hora).replace(/^(\d):/, '0$1:')}`;
  // Una pareja con mes desconocido ("xx-22 08:00") vale si hay una permitida con ese día y esa hora.
  const permitida = (p, set) => set.has(p) || (p.startsWith('xx-') && [...set].some((q) => q.slice(3) === p.slice(3)));

  // "Afirmaciones de haber hecho algo". Solo formas conjugadas que dicen "ya esta hecho"; "le confirmo:" (read-back) y "confirme su asistencia" NO cuentan.
  // "anotar" cuenta SOLO si anota un TURNO: "dejé anotado su aviso de pago" / "se lo dejo anotado a la clínica" (lista de espera) no son escrituras (falso positivo del examen 06/10).
  // Limites de palabra UNICODE: el \b de JavaScript no sirve pegado a una letra con tilde ("agendé", "moví").
  const W = (src) => new RegExp(String.raw`(?<![\p{L}])(?:` + src + String.raw`)(?![\p{L}])`, 'iu');
  const CLAIMS = [
    { tipo: 'reprogramar', rx: W(String.raw`qued(?:ó|o|a|an)\s+(?:reprogramad|cambiad|movid|reservad|agendad)\p{L}*|qued(?:ó|a)\s+anotad\p{L}*\s+(?:el|su|un)\s+turno|reprogramé|cambié|moví|reservé|agendé|anot[eé]\s+(?:su|el|un)\s+turno|(?:le|lo|la)\s+(?:reserve|agende|cambie|movi|reprograme)|ya\s+(?:le\s+)?(?:reserv|agend|cambi|mov)\p{L}*|ya\s+(?:le\s+)?anot\p{L}*\s+(?:(?:su|el|un|ese)\s+turno|para\s+el\s+\p{L}+|el\s+(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado))|le\s+dej[oé]\s+(?:reservad|agendad)\p{L}*|le\s+dej[oé]\s+anotad\p{L}*\s+(?:su|el|un|ese)\s+turno|list[oa],?\s+(?:reprogramad|reservad|agendad|cambiad)\p{L}*`) },
    { tipo: 'cancelar', rx: W(String.raw`qued(?:ó|o|a|an)\s+cancelad\p{L}*|cancelé|anulé|(?:le|lo|la)\s+(?:cancele|anule)|list[oa],?\s+(?:cancelad|anulad)\p{L}*`) },
    // (07/10) "está confirmado" también: es el texto de confirmar_turno; dicho por el modelo sin confirmar de verdad, es una afirmación falsa.
    { tipo: 'confirmar', rx: W(String.raw`qued(?:ó|o|a|an)\s+confirmad\p{L}*|est[aá]n?\s+confirmad\p{L}*|confirmé|list[oa],?\s+confirmad\p{L}*|(?:^|[.!¡]\s*)confirmad[oa](?=\s*[.!,]|\s*$)`) },   // (07/10) "Confirmado." suelto (REAL-15)
  ];
  const TIPOS_OK = { reprogramar: ['cambio', 'reserva', 'sumar'], cancelar: ['cancelacion'], confirmar: ['confirmacion'] };
  const esc = (x) => String(x).replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
  const quitar = (texto, frase) => (frase ? String(texto).replace(new RegExp(esc(frase), 'gi'), ' ') : texto);
  const honesto = 'Disculpe, todavía no pude concretar eso en la agenda, así que no quedó hecho. Le aviso a la clínica para que lo resuelva y se comunique con usted.';

  function revisar(entrada) {
    const texto = String(entrada.texto || '');
    const libros = Array.isArray(entrada.libros) ? entrada.libros : (entrada.libro ? [entrada.libro] : []);
    const oks = libros.filter((l) => l && l.ok === true);
    const libro = oks.length ? oks[oks.length - 1] : (libros.length ? libros[libros.length - 1] : null);   // el que tiene que contar el texto: la última escritura ok
    const ofertas = entrada.ofertas || [];
    // (07/10) Escrituras OK de mensajes anteriores (últimas 12 h, mismo celular). Solo sirven para no tomar como falsa una afirmación que repite algo ya hecho
    // ("Su turno del viernes 16/10 está confirmado", dicho dos mensajes después de confirmarlo: el chequeo lo cambiaba por "no pude concretar eso"; examen MULTI-01).
    const previos = (Array.isArray(entrada.libros_previos) ? entrada.libros_previos : []).filter((l) => l && l.ok === true);
    const nTexto = normTexto(texto);
    const hechoOk = oks.length > 0;

    // (1) hay una escritura OK y el texto no contiene el read-back de lo que se hizo (timeout / maxIterations / el modelo se fue por las ramas)
    const sinDecir = oks.filter((l) => l.readback_text && !nTexto.includes(normTexto(l.readback_text)));
    if (hechoOk && sinDecir.length === oks.length && libro.readback_text) {
      // (3) ...y ademas habla de OTRA fecha+hora distinta: tambien se reemplaza (mismo remedio: decir lo que realmente paso)
      return { accion: 'reemplazar', texto: libro.readback_text, motivo: parejas(texto).length ? 'fecha_distinta_a_la_escrita' : 'falta_confirmacion_de_lo_hecho', avisar: { nivel: 'tecnico', texto: 'El chequeo de salida reemplazó el mensaje de Asiri por el resultado real de la agenda.' } };
    }
    const parcial = libros.find((l) => l && l.parcial === true && l.readback_text && !nTexto.includes(normTexto(l.readback_text)));
    if (parcial) {
      return { accion: 'reemplazar', texto: parcial.readback_text, motivo: 'escritura_parcial_sin_decirlo', avisar: { nivel: 'ACCION', texto: 'Escritura parcial: revisar la agenda.' } };
    }

    // (1b) lo que el CÓDIGO le dio a Asiri para que pegue textual (el read-back de una propuesta de esta ejecución; el bloque de horarios recién buscado) tiene que
    // llegar al paciente. Si el modelo se lo salteó, se reemplaza por ese texto: sin él la charla se traba (el paciente no ve las opciones / no tiene qué confirmar).
    if (entrada.propuesta_readback && !nTexto.includes(normTexto(entrada.propuesta_readback))) {
      return { accion: 'reemplazar', texto: entrada.propuesta_readback, motivo: 'falta_readback', avisar: { nivel: 'tecnico', texto: 'Asiri no pegó el texto de confirmación; se envió el armado por el código.' } };
    }
    // (1c) el read-back va SOLO: si el modelo le agrega otra pregunta ("¿para quién cancela?" + "¿Procedo con la cancelación?") el "Sí" del paciente queda ambiguo y el modelo
    // vuelve a repetir el read-back en vez de ejecutar (examen 06/10, DANA-08). Una frase de cortesía sin pregunta ("Perfecto.") se deja pasar.
    if (entrada.propuesta_readback) {
      const resto = quitar(texto, entrada.propuesta_readback);
      if (/[?¿]/.test(resto)) {
        return { accion: 'reemplazar', texto: entrada.propuesta_readback, motivo: 'pregunta_extra_con_readback', avisar: { nivel: 'tecnico', texto: 'Asiri agregó otra pregunta al texto de confirmación; se envió solo el armado por el código.' } };
      }
    }
    // (07/10) El bloque cuenta como pegado aunque el modelo cambie la última línea ("Le sirve alguno?" → "¿Cuál prefiere para Martina?"): antes eso disparaba el reemplazo.
    const cuerpoBloque = String(entrada.bloque_exec || '').replace(/\n*\s*¿?\s*le sirve alguno\s*\??\s*$/i, '').trim();
    if (entrada.bloque_exec && !nTexto.includes(normTexto(cuerpoBloque))) {
      // (06/10) Se reemplaza SOLO el bloque: se conservan las frases del modelo que no son parte de la lista de horarios ni traen fechas/horas propias
      // (ej. "No hay turno el jueves a las 9:20" se va por tener hora; "¿Para quién es el cambio?" se queda). Antes se borraba todo el mensaje.
      const ES_LISTA = /^\s*(?:[*\-•·]|por la (?:mañana|manana|tarde)|tenemos (?:los|estos)|le sirve alguno|estos son los|le ofrezco|horarios disponibles)/i;
      const TRAE_FECHA = /\b\d{1,2}[:.]\d{2}\b|\b\d{1,2}\/\d{1,2}\b|\b(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+\d{1,2}\b/i;
      const AFIRMA = /qued[oó]\s+(?:reprogramad|cancelad|confirmad|reservad)|le\s+reserv[eé]|anul[eé]/i;
      const lineas = String(texto).split('\n');
      const lista = lineas.map((l) => ES_LISTA.test(l));
      const primero = lista.indexOf(true), ultimo = lista.lastIndexOf(true);
      const NEGATIVA = /^\s*(?:no hay|no tenemos|no queda|ese horario no|lamentablemente no)/i;   // decir que algo NO está disponible es seguro aunque nombre la hora
      // (07/10) Se conservan también las líneas que dicen la verdad: el texto que armó el código (una confirmación de recordatorio, "ya estaba confirmado") y las que solo
      // nombran turnos que el paciente YA tiene u horarios ya ofrecidos. Antes se borraban por traer fecha (examen MULTI-01: se perdía "Su turno del viernes 16/10… quedó confirmado").
      const permitidasL = new Set(ofertas.map(clave));
      for (const lb of libros) if (lb && lb.readback_text) parejas(lb.readback_text).forEach((p) => permitidasL.add(p));
      (entrada.turnos_vistos || []).forEach((t) => permitidasL.add(`${String(t.fecha).slice(5)} ${String(t.hora_inicio || t.hora).slice(0, 5)}`));
      const deCodigo = (l) => libros.some((lb) => lb && lb.readback_text && normTexto(lb.readback_text).includes(normTexto(l)));
      const conocidas = (l) => { const ps = parejas(l); return ps.length > 0 && ps.every((p) => permitida(p, permitidasL)); };
      const util = (l) => l.trim() && (deCodigo(l) || (!AFIRMA.test(l) && (!TRAE_FECHA.test(l) || NEGATIVA.test(l) || conocidas(l))));
      const antes = (primero >= 0 ? lineas.slice(0, primero) : lineas).filter(util).join('\n').trim();
      const despues = (ultimo >= 0 ? lineas.slice(ultimo + 1) : []).filter(util).join('\n').trim();
      const nuevo = (antes ? antes + '\n\n' : '') + entrada.bloque_exec + (despues ? '\n' + despues : '');
      return { accion: 'reemplazar', texto: nuevo, motivo: 'falta_bloque', avisar: { nivel: 'tecnico', texto: 'Asiri no pegó el bloque de horarios; se envió el armado por el código.' } };
    }

    // (2) afirma que algo quedó hecho y NO hay una escritura OK compatible
    // Se evalua sobre el texto SIN los read-backs que el propio codigo escribio (el de la escritura, el de la propuesta): esos dicen la verdad.
    let sobrante = String(texto);
    for (const l of libros.concat(previos)) sobrante = quitar(sobrante, l && l.readback_text);
    sobrante = quitar(sobrante, entrada.propuesta_readback);
    // (06/10) Una PREGUNTA no afirma nada: "¿Desea que le reserve un turno?" se tomaba como "le reservé" y el código reemplazaba una buena respuesta
    // por "no pude concretar eso en la agenda" (retrospectiva con mensajes reales: consulta por ATM y cotización de alineadores).
    sobrante = sobrante.replace(/¿[^?¿]*\?/g, ' ').replace(/(?:^|[.!\n])[^.!?\n¿]*\?/g, ' ');
    if (!(propuestaVigente(entrada))) {
      for (const c of CLAIMS) {
        if (!c.rx.test(sobrante)) continue;
        const compatible = oks.concat(previos).some((l) => TIPOS_OK[c.tipo].includes(l.tipo));
        if (!compatible) return { accion: 'reemplazar', texto: honesto, motivo: `afirma_${c.tipo}_sin_ok`, avisar: { nivel: 'tecnico', texto: `Asiri afirmó "${c.tipo}" sin una escritura ok en la agenda (bloqueado).` } };
      }
    }

    // (4) cualquier fecha+hora de un mensaje con horarios tiene que estar entre las ofrecidas por buscar_horarios
    // (07/10) Una oración que dice que un horario NO está ("El 4/11 a las 17:00 no figura entre los disponibles") no ofrece nada: sus horas no cuentan.
    // Examen completo 07/10: el modelo lo decía bien y el chequeo lo reemplazaba por el bloque entero; el paciente volvía a pedir lo mismo y la charla se alargaba.
    // Si en la misma oración ofrece algo ("no hay problema, le reservo el …"), cuenta igual.
    // (sin \b al final: en JS sin /u la "á" no es letra y "no está\b" nunca coincidía)
    const FIN = '(?![a-záéíóúñ])';
    const NO_ESTA = new RegExp('\\bno\\s+(?:hay|tenemos|queda|quedan|est[aá]n?|figuran?|tengo|es\\s+posible)' + FIN, 'i');
    const OFRECE = new RegExp('le\\s+(?:ofrezco|reservo|agendo|anoto|doy|propongo)|puedo\\s+(?:ofrecerle|darle|reservarle|agendarle)|le\\s+sirve|tenemos\\s+(?:el|lugar|turno)' + FIN + '|\\bs[ií]\\s+(?:hay|tenemos|queda|est[aá])' + FIN + '|\\bpero' + FIN, 'i');
    const sinNegativas = String(texto).split(/(?<=[.!?¿\n])/).filter((o) => !(NO_ESTA.test(o) && !OFRECE.test(o))).join('');
    const pares = parejas(sinNegativas);
    if (pares.length) {
      const permitidas = new Set(ofertas.map(clave));
      for (const l of libros) if (l && l.readback_text) parejas(l.readback_text).forEach((p) => permitidas.add(p));
      if (entrada.propuesta_readback) parejas(entrada.propuesta_readback).forEach((p) => permitidas.add(p));
      (entrada.turnos_vistos || []).forEach((t) => permitidas.add(`${t.fecha.slice(5)} ${String(t.hora_inicio || t.hora).slice(0, 5)}`));
      const ajenas = pares.filter((p) => !permitida(p, permitidas));
      // (08/10) REAL-10: el modelo escribió un turno que el paciente YA tiene con día y mes invertidos ("jueves 12/10" por 10/12). No es un horario
      // inventado: se corrige la fecha en el texto y pasa. Antes se buscaba el bloque y un aviso de presupuesto terminaba reemplazado por la lista de
      // horarios (el paciente simulado eligió uno y se le sumó un turno que nunca pidió).
      const inv = (p) => `${p.slice(3, 5)}-${p.slice(0, 2)}${p.slice(5)}`;
      const vistosSet = new Set((entrada.turnos_vistos || []).map((t) => `${String(t.fecha).slice(5)} ${String(t.hora_inicio || t.hora).slice(0, 5)}`));
      if (ajenas.length && ajenas.every((p) => !p.startsWith('xx-') && vistosSet.has(inv(p)))) {
        let corregido = String(texto);
        for (const p of ajenas) { const m = Number(p.slice(0, 2)), d = Number(p.slice(3, 5)); corregido = corregido.replace(new RegExp(`(?<!\\d)0?${d}/0?${m}(?!\\d)`, 'g'), `${m}/${d}`); }
        return { accion: 'reemplazar', texto: corregido, motivo: 'fecha_invertida', avisar: null };
      }
      if (ajenas.length) {
        if (entrada.bloque_ofertas) return { accion: 'reemplazar', texto: entrada.bloque_ofertas, motivo: 'horario_no_ofrecido', avisar: { nivel: 'tecnico', texto: 'Asiri mencionó un horario que nadie ofreció; se reemplazó por el bloque real.' } };
        // (07/10) Antes: "déjeme confirmar los horarios…" y nadie volvía a escribir. Ahora es honesto y la clínica recibe [ACCIÓN] para contestarle.
        // (El cerebro busca el bloque por código antes de llegar acá; esto queda solo si esa búsqueda falló.)
        return { accion: 'reemplazar', texto: 'Disculpe, no tengo esos horarios confirmados en este momento. Le paso su consulta a la secretaria para que le ofrezca los turnos disponibles.', motivo: 'horario_no_ofrecido', avisar: { nivel: 'ACCION', texto: 'Asiri mencionó un horario que no salió de la agenda y no se pudo buscar el bloque real: contestarle al paciente con los turnos disponibles.' } };
      }
    }
    return { accion: 'pasar', texto, motivo: null, avisar: null };
  }
  // Una propuesta de ESTA ejecucion cuyo read-back es el texto: el mensaje "Le confirmo: ... ¿Procedo con la reserva?" no es una afirmacion de haber hecho nada.
  function propuestaVigente(e) { return !!(e.propuesta_readback && normTexto(e.texto).includes(normTexto(e.propuesta_readback))); }
  return { revisar, parejas, honesto };
})();
if (typeof module !== 'undefined') module.exports = ChequeoSalida;
