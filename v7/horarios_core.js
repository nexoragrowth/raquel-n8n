// horarios_core.js — v7 · qué horarios se le OFRECIERON al paciente. Fuente de verdad en el repo (se inlinea en nodos Code de n8n).
// buscar_horarios devuelve el bloque de texto que armó "Sub-WF - Buscar Horarios Validado" (formato pedido por la Dra. el 07/09). De ese mismo texto sale la lista
// de horarios ofrecidos que después valida agenda_core.proponer ("solo se puede reservar lo que se ofreció") y chequeo_salida (nada inventado).
const HorariosCore = (() => {
  const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const sinT = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const hh = (h, m) => String(Number(h)).padStart(2, '0') + ':' + m;

  // "* Jueves 22 de octubre 8:00 , 9:20" → [{fecha:'2026-10-22', hora:'08:00'}, {fecha:'2026-10-22', hora:'09:20'}]. El bloque no lleva año: el actual, o el que viene si ya pasó.
  function parseBloque(bloque, hoyISO) {
    const out = [];
    for (const linea of String(bloque || '').split('\n')) {
      const l = sinT(linea.trim());
      const m = /^\*\s*[^\d]*?(\d{1,2})\s+de\s+([a-z]+)\s+(.*)$/.exec(l);
      if (!m) continue;
      const mes = MESES.indexOf(m[2] === 'setiembre' ? 'septiembre' : m[2]) + 1;
      if (!mes) continue;
      const mm = String(mes).padStart(2, '0'), dd = String(Number(m[1])).padStart(2, '0');
      const anio = Number(hoyISO.slice(0, 4));
      const cand = `${anio}-${mm}-${dd}`;
      const fecha = cand >= hoyISO ? cand : `${anio + 1}-${mm}-${dd}`;
      for (const t of m[3].matchAll(/(\d{1,2}):(\d{2})/g)) out.push({ fecha, hora: hh(t[1], t[2]) });
    }
    return out;
  }
  // Une lo ya ofrecido con lo nuevo (el paciente puede elegir de un bloque anterior), sin duplicados y solo futuro.
  function unir(previas, nuevas, hoyISO) {
    const vistos = new Set(); const out = [];
    for (const o of [...(previas || []), ...(nuevas || [])]) {
      const k = `${o.fecha} ${o.hora}`;
      if (o.fecha < hoyISO || vistos.has(k)) continue;
      vistos.add(k); out.push({ fecha: o.fecha, hora: o.hora });
    }
    return out;
  }
  // Regla de la Dra. (07/09): como máximo 2 bloques por conversación. A la tercera consulta no se busca otro: se anota para la clínica.
  const MAX_LOTES = 2;
  const limiteLotes = (n) => Number(n) > MAX_LOTES;
  return { parseBloque, unir, limiteLotes, MAX_LOTES };
})();
if (typeof module !== 'undefined') module.exports = HorariosCore;
