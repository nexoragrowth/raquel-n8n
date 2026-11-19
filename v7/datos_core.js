// datos_core.js — v7 · FUENTE ÚNICA de los datos de la clínica que se repiten en los textos (hoy: precios). Se inlinea en nodos Code de n8n.
// Idea: el dato se escribe UNA vez (tabla de datos) y los textos llevan un marcador {{precio_consulta}}; al leer, un solo resolver lo reemplaza.
// Dos precios que HOY valen lo mismo (consulta y devolución, $50.000) son datos DISTINTOS: reemplazar "por valor" los mezclaría el día que cambie uno.
// Por eso la migración de textos viejos (literal → marcador) es una PROPUESTA que clasifica por contexto y marca lo dudoso para que lo revise una persona.
const DatosCore = (() => {
  // clave → etiqueta (para la pantalla) y pistas del contexto (la más cercana ANTES del monto decide)
  const DATOS = {
    precio_consulta: { etiqueta: 'Primera consulta', pistas: /consulta|valoraci[oó]n/i },
    precio_devolucion: { etiqueta: 'Cita de devolución', pistas: /devoluci[oó]n|segunda cita/i },
  };
  const MARCA = /\{\{\s*([a-z][a-z0-9_]*)\s*\}\}/g;
  const MONTO = /\$\s?(\d{1,3}(?:\.\d{3})+|\d{4,})(?:,00)?/g;
  const VENTANA = 140; // caracteres hacia atrás donde se busca la pista

  const aEntero = (s) => Number(String(s).replace(/\./g, ''));
  // 60000 → "$60.000"
  const pesos = (n) => '$' + Math.round(Number(n)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');

  // Reemplaza cada {{clave}} por su monto. Sin dato válido NO inventa nada: deja el marcador y lo informa (el llamador decide: nunca debe llegar a un paciente).
  function resolver(texto, valores) {
    const faltan = new Set();
    const out = String(texto == null ? '' : texto).replace(MARCA, (m, k) => {
      const v = valores && valores[k];
      if (typeof v === 'number' && Number.isFinite(v) && v > 0) return pesos(v);
      faltan.add(k); return m;
    });
    return { texto: out, faltan: [...faltan] };
  }
  const marcadores = (texto) => [...new Set([...String(texto || '').matchAll(MARCA)].map((m) => m[1]))];

  // Propone pasar los montos literales de un texto a marcadores. NO escribe nada. `actuales` = { precio_consulta: 50000, precio_devolucion: 50000, … }.
  // Por cada monto igual a algún valor actual: pista MÁS CERCANA antes del monto → ese dato. Dudoso (sin pista, o dos datos posibles con pistas a la par) → 'revisar'.
  function proponerMigracion(texto, actuales) {
    const t = String(texto == null ? '' : texto);
    const cambios = [];
    let salida = '';
    let cursor = 0;
    for (const m of t.matchAll(MONTO)) {
      const valor = aEntero(m[1]);
      const candidatos = Object.keys(DATOS).filter((k) => actuales && actuales[k] === valor);
      if (!candidatos.length) continue; // otro monto (no es ninguno de los datos conocidos): no se toca
      const antes = t.slice(Math.max(0, m.index - VENTANA), m.index);
      const cercanas = candidatos.map((k) => {
        let ult = -1;
        for (const x of antes.matchAll(new RegExp(DATOS[k].pistas.source, 'gi'))) ult = x.index + x[0].length;
        return { k, dist: ult < 0 ? Infinity : antes.length - ult };
      }).sort((a, b) => a.dist - b.dist);
      let elegido = null; let confianza = 'revisar'; let motivo = '';
      if (candidatos.length === 1) {
        elegido = candidatos[0]; confianza = Number.isFinite(cercanas[0].dist) ? 'alta' : 'revisar';
        motivo = confianza === 'alta' ? 'una pista clara' : 'sin pista en el contexto';
      } else if (Number.isFinite(cercanas[0].dist)) {
        const otra = cercanas[1];
        const empate = Number.isFinite(otra.dist) && Math.abs(otra.dist - cercanas[0].dist) < 25;
        elegido = cercanas[0].k; confianza = empate ? 'revisar' : 'alta'; motivo = empate ? 'dos pistas a la par' : 'la pista más cercana';
      } else { motivo = 'ninguna pista: puede ser cualquiera de ' + candidatos.join(' / '); }
      cambios.push({ posicion: m.index, literal: m[0], marcador: elegido, confianza, motivo, contexto: t.slice(Math.max(0, m.index - 60), m.index + m[0].length + 30).replace(/\s+/g, ' ') });
      if (elegido) { salida += t.slice(cursor, m.index) + '{{' + elegido + '}}'; cursor = m.index + m[0].length; }
    }
    salida += t.slice(cursor);
    return { texto: salida, cambios, dudosos: cambios.filter((c) => c.confianza !== 'alta' || !c.marcador).length };
  }

  // Todo lo que muestra un cambio de valor, ANTES de aplicarlo: por cada texto, cómo se lee ahora y cómo se leería.
  function vistaPrevia(textos, valoresAhora, valoresNuevos) {
    const filas = [];
    for (const [id, t] of Object.entries(textos || {})) {
      const marcas = marcadores(t);
      if (!marcas.length) continue;
      const antes = resolver(t, valoresAhora).texto; const despues = resolver(t, valoresNuevos).texto;
      filas.push({ id, marcadores: marcas, cambia: antes !== despues, antes, despues });
    }
    return filas;
  }

  // Los textos que SIGUEN mostrando un monto literal que coincide con un dato conocido (candidatos a migrar, o inconsistencias después de migrar).
  function literalesPendientes(textos, conocidos) {
    const out = [];
    for (const [id, t] of Object.entries(textos || {})) {
      const n = [...String(t || '').matchAll(MONTO)].filter((m) => Object.values(conocidos || {}).includes(aEntero(m[1]))).length;
      if (n) out.push({ id, literales: n });
    }
    return out;
  }

  return { DATOS, pesos, resolver, marcadores, proponerMigracion, vistaPrevia, literalesPendientes };
})();
if (typeof module !== 'undefined') module.exports = DatosCore;
