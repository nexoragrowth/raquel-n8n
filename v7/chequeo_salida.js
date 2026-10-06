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
      tokens.sort((a, b) => a.i - b.i);
      let fecha = null;
      for (const t of tokens) { if (t.tipo === 'f') fecha = t.md; else if (fecha) out.push(`${fecha} ${t.h}`); }
    }
    return out;
  }
  const clave = (o) => `${o.fecha.slice(5)} ${String(o.hora).replace(/^(\d):/, '0$1:')}`;

  // "Afirmaciones de haber hecho algo". Solo formas conjugadas que dicen "ya esta hecho"; "le confirmo:" (read-back) y "confirme su asistencia" NO cuentan.
  // Limites de palabra UNICODE: el \b de JavaScript no sirve pegado a una letra con tilde ("agendé", "moví").
  const W = (src) => new RegExp(String.raw`(?<![\p{L}])(?:` + src + String.raw`)(?![\p{L}])`, 'iu');
  const CLAIMS = [
    { tipo: 'reprogramar', rx: W(String.raw`qued(?:ó|o|a|an)\s+(?:reprogramad|cambiad|movid|reservad|agendad)\p{L}*|qued(?:ó|a)\s+anotad\p{L}*\s+(?:el|su|un)\s+turno|reprogramé|cambié|moví|reservé|agendé|anot[eé]\s+(?:su|el|un)\s+turno|(?:le|lo|la)\s+(?:reserve|agende|cambie|movi|reprograme)|ya\s+(?:le\s+)?(?:reserv|agend|cambi|mov|anot)\p{L}*|le\s+dej[oé]\s+(?:reservad|agendad|anotad)\p{L}*|list[oa],?\s+(?:reprogramad|reservad|agendad|cambiad)\p{L}*`) },
    { tipo: 'cancelar', rx: W(String.raw`qued(?:ó|o|a|an)\s+cancelad\p{L}*|cancelé|anulé|(?:le|lo|la)\s+(?:cancele|anule)|list[oa],?\s+(?:cancelad|anulad)\p{L}*`) },
    { tipo: 'confirmar', rx: W(String.raw`qued(?:ó|o|a|an)\s+confirmad\p{L}*|confirmé|list[oa],?\s+confirmad\p{L}*`) },
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
    if (entrada.bloque_exec && !nTexto.includes(normTexto(entrada.bloque_exec))) {
      return { accion: 'reemplazar', texto: entrada.bloque_exec, motivo: 'falta_bloque', avisar: { nivel: 'tecnico', texto: 'Asiri no pegó el bloque de horarios; se envió el armado por el código.' } };
    }

    // (2) afirma que algo quedó hecho y NO hay una escritura OK compatible
    // Se evalua sobre el texto SIN los read-backs que el propio codigo escribio (el de la escritura, el de la propuesta): esos dicen la verdad.
    let sobrante = String(texto);
    for (const l of libros) sobrante = quitar(sobrante, l && l.readback_text);
    sobrante = quitar(sobrante, entrada.propuesta_readback);
    if (!(propuestaVigente(entrada))) {
      for (const c of CLAIMS) {
        if (!c.rx.test(sobrante)) continue;
        const compatible = oks.some((l) => TIPOS_OK[c.tipo].includes(l.tipo));
        if (!compatible) return { accion: 'reemplazar', texto: honesto, motivo: `afirma_${c.tipo}_sin_ok`, avisar: { nivel: 'tecnico', texto: `Asiri afirmó "${c.tipo}" sin una escritura ok en la agenda (bloqueado).` } };
      }
    }

    // (4) cualquier fecha+hora de un mensaje con horarios tiene que estar entre las ofrecidas por buscar_horarios
    const pares = parejas(texto);
    if (pares.length) {
      const permitidas = new Set(ofertas.map(clave));
      for (const l of libros) if (l && l.readback_text) parejas(l.readback_text).forEach((p) => permitidas.add(p));
      if (entrada.propuesta_readback) parejas(entrada.propuesta_readback).forEach((p) => permitidas.add(p));
      (entrada.turnos_vistos || []).forEach((t) => permitidas.add(`${t.fecha.slice(5)} ${String(t.hora_inicio || t.hora).slice(0, 5)}`));
      const ajenas = pares.filter((p) => !permitidas.has(p));
      if (ajenas.length) {
        if (entrada.bloque_ofertas) return { accion: 'reemplazar', texto: entrada.bloque_ofertas, motivo: 'horario_no_ofrecido', avisar: { nivel: 'tecnico', texto: 'Asiri mencionó un horario que nadie ofreció; se reemplazó por el bloque real.' } };
        return { accion: 'reemplazar', texto: 'Disculpe, déjeme confirmar los horarios disponibles para pasarle los correctos.', motivo: 'horario_no_ofrecido', avisar: { nivel: 'tecnico', texto: 'Asiri mencionó un horario que nadie ofreció (sin bloque para reemplazar).' } };
      }
    }
    return { accion: 'pasar', texto, motivo: null, avisar: null };
  }
  // Una propuesta de ESTA ejecucion cuyo read-back es el texto: el mensaje "Le confirmo: ... ¿Procedo con la reserva?" no es una afirmacion de haber hecho nada.
  function propuestaVigente(e) { return !!(e.propuesta_readback && normTexto(e.texto).includes(normTexto(e.propuesta_readback))); }
  return { revisar, parejas, honesto };
})();
if (typeof module !== 'undefined') module.exports = ChequeoSalida;
