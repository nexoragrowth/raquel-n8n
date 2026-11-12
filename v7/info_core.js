// info_core.js — v7 · control por CÓDIGO de la respuesta del agente de INFORMACIÓN (el único sub-agente que redacta). Fuente de verdad en el repo: se inlinea
// en el nodo "Armar salida" de "v7 Agente Informacion" (lo usan el cerebro actual y el Cerebro Agente) y se prueba offline (tests/test_info_core.mjs).
// (12/11, espejo con mensajes reales, r007 "esta tarde hasta qué hora está la doctora", jueves) El orquestador escribió en el PEDIDO una respuesta inventada
// ("por la tarde la Dra atiende hasta las 18:00") e Información la copió: los jueves a la tarde no se atiende y las 18:00 no figura en ningún horario.
// Regla 5 (defensa en profundidad): además del prompt, toda HORA y todo MONTO que Información le dice al paciente tiene que estar ESCRITO en los DATOS del
// consultorio (el Conocimiento). Si no, la respuesta no sale: queda fuera de alcance y el cerebro deriva a la secretaria, como cualquier fuera de alcance.
// Solo compara DATOS (el texto del agente contra el Conocimiento); no lee el mensaje del paciente (decisión del 08/10).
const InfoCore = (() => {
  const hm = (h, m) => `${Number(h)}:${m}`;
  // Horas del texto: "8:00", "08.30", "19 hs", "hasta las 18". Las de 24 h o más ("24 hs", "48 hs" = plazos) no son horas del día y no se controlan.
  function horas(texto) {
    const s = String(texto || '');
    const out = new Set();
    for (const m of s.matchAll(/\b(\d{1,2})[:.](\d{2})\b/g)) if (Number(m[1]) < 24 && Number(m[2]) < 60) out.add(hm(m[1], m[2]));
    for (const m of s.matchAll(/\b(\d{1,2})\s*(?:hs|h|horas)\b/gi)) if (Number(m[1]) < 24) out.add(hm(m[1], '00'));
    for (const m of s.matchAll(/\b(?:a|hasta|desde)\s+las\s+(\d{1,2})\b(?![:.]\d)/gi)) if (Number(m[1]) < 24) out.add(hm(m[1], '00'));   // no "las 3 cuotas"
    return out;
  }
  // Montos en pesos: "$50.000", "$ 50000", "50 mil", "50.000 pesos".
  function montos(texto) {
    const s = String(texto || '');
    const out = new Set();
    const num = (d, mil) => { let n = Number(String(d).replace(/[.,]/g, '')); if (mil && n < 1000) n *= 1000; return n; };
    for (const m of s.matchAll(/\$\s?(\d{1,3}(?:[.,]\d{3})+|\d+)(?:\s*(mil)\b)?/gi)) out.add(num(m[1], m[2]));
    for (const m of s.matchAll(/\b(\d{1,3}(?:\.\d{3})+|\d+)\s*(mil\s+)?pesos\b/gi)) out.add(num(m[1], m[2]));
    for (const m of s.matchAll(/\b(\d{1,3})\s*mil\b/gi)) out.add(Number(m[1]) * 1000);
    out.delete(0);
    return out;
  }
  // salida: lo que devuelve OrquestadorCore.salidaInformacion. datos: el texto de los DATOS DEL CONSULTORIO que recibió el agente.
  function verificar(salida, datos) {
    const s = salida || {};
    if (s.estado !== 'respondido' || !s.texto) return s;
    const hd = horas(datos), md = montos(datos);
    // "de 8 a 12 hs": el "12 hs" de los DATOS también vale como "12:00"; y un "12:00" de los DATOS vale para "a las 12".
    const horasMal = [...horas(s.texto)].filter((h) => !hd.has(h));
    const montosMal = [...montos(s.texto)].filter((n) => !md.has(n));
    if (!horasMal.length && !montosMal.length) return s;
    const motivo = [horasMal.length ? 'horas que no están en los DATOS: ' + horasMal.join(', ') : '', montosMal.length ? 'montos que no están en los DATOS: ' + montosMal.join(', ') : ''].filter(Boolean).join('; ');
    return { ...s, texto: '', estado: 'fuera_de_alcance', fuera_de_alcance: true, codigo: 'NO_ESTA_EN_DATOS', motivo_control: motivo, texto_descartado: String(s.texto).slice(0, 300), largo: 0 };
  }
  return { horas, montos, verificar };
})();
if (typeof module !== 'undefined') module.exports = InfoCore;
