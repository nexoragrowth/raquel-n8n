// v6_salida_core.js — "v6 Orquestador": revisa, POR CÓDIGO, lo que escribió el agente padre antes de que salga al paciente (puro, sin red).
// Por qué NO se reusa VerificadorCore.verificar entero: ese módulo entiende las herramientas del v7 (turnos/pagos/informacion/urgencias que devuelven objetos con
// estado, libro de escrituras y propuestas en Redis). Los especialistas del v6 devuelven TEXTO LIBRE (con secciones HICE:/DATOS:/TEXTO_FIJO:/FALTA:...) y escriben
// directo en Dentalink: no hay libro ni propuesta que leer. De VerificadorCore se reusan solo `montos` y `FRASES_INCIDENTE` (si están cargados en el mismo nodo).
// Reglas (cualquiera que falle = RESPALDO; el motivo queda en `motivo_verificador`):
//   a) charla que inició la clínica con un contacto sin ficha → silencio   b) agente caído/vacío/basura → "no le entendí" o error + aviso
//   c) frases del incidente del 9/5 → respaldo   d) horarios (HH:MM) y montos en pesos que no salieron de un especialista de ESTE mensaje → respaldo
//   e) comprobante MARCADO por la entrada y agente_confirmar no llamado → respaldo con el texto de recepción + aviso   f) silencio decidido por el agente (no_responder / [NO_REPLY])
const V6Salida = (() => {
  const OC = (() => { if (typeof OrquestadorCore !== 'undefined') return OrquestadorCore; try { return (typeof module !== 'undefined' && typeof require !== 'undefined') ? require('./orquestador_core.js') : null; } catch (x) { return null; } })();
  const VC = (() => { if (typeof VerificadorCore !== 'undefined') return VerificadorCore; try { return (typeof module !== 'undefined' && typeof require !== 'undefined') ? require('./verificador_core.js') : null; } catch (x) { return null; } })();
  const ESPECIALISTAS = ['agente_agendar', 'agente_confirmar', 'agente_cancelar', 'agente_urgencia', 'agente_general'];
  const TEXTOS = {
    NO_ENTENDI: (OC && OC.TEXTOS.NO_ENTENDI) || 'Disculpe, no le entendí bien. ¿Me lo puede escribir de otra forma?',
    ERROR: (OC && OC.TEXTOS.ERROR) || 'Disculpe, tuve un inconveniente para responderle en este momento. Le aviso a la clínica para que se comunique con usted.',
    COMPROBANTE: 'Recibimos su comprobante. Le informo a la secretaria, que verificará el pago en su horario de atención. ¡Muchas gracias!',
  };
  const MARCAS = ['HICE', 'DATOS', 'TEXTO_FIJO', 'FALTA', 'ESCALÓ', 'FUERA_DE_AREA', 'SIN_RESPUESTA'];
  const lim = (s, n) => String(s === undefined || s === null ? '' : s).trim().slice(0, n);
  const norm = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9:/? ]+/g, ' ').replace(/\s+/g, ' ').trim();
  const FRASES = (VC && VC.FRASES_INCIDENTE) || [['venite', /\bvenite\b/i], ['te_esperamos', /\b(?:te|los|lo|la|le)\s+esperamos\b/i], ['ahora_mismo', /\bahora\s+mismo\b/i]];

  // El texto que devolvió una herramienta puede venir envuelto ({"output": "..."} / {"response": "..."}).
  function desenvolver(obs) {
    let s = typeof obs === 'string' ? obs : JSON.stringify(obs === undefined || obs === null ? '' : obs);
    for (let i = 0; i < 2; i++) {
      try { const j = JSON.parse(s); if (j && typeof j === 'object' && !Array.isArray(j)) { const v = ['output', 'response', 'text', 'result'].map((k) => j[k]).find((x) => typeof x === 'string'); if (v !== undefined) { s = v; continue; } } else if (typeof j === 'string') { s = j; continue; } } catch (x) { /* ya es texto */ }
      break;
    }
    return s;
  }
  // Secciones etiquetadas que devuelve un especialista (ver "Qué recibís del orquestador y qué devolvés").
  function secciones(texto) {
    const out = {}; const re = new RegExp('^\\s*(' + MARCAS.join('|') + ')\\s*:', 'gm'); const idx = [];
    let m; while ((m = re.exec(texto)) !== null) idx.push({ k: m[1], ini: m.index, fin: m.index + m[0].length });
    idx.forEach((it, i) => { const v = texto.slice(it.fin, i + 1 < idx.length ? idx[i + 1].ini : texto.length).trim(); (out[it.k] = out[it.k] || []).push(v); });
    return out;
  }
  function pasosDe(salida) {
    const arr = salida && Array.isArray(salida.intermediateSteps) ? salida.intermediateSteps : [];
    return arr.map((s) => { const a = (s && s.action) || {}; const obs = desenvolver(s && s.observation); return { tool: String(a.tool || a.toolName || ''), input: a.toolInput === undefined ? null : a.toolInput, obs, sec: secciones(obs) }; });
  }
  const horas = (t) => [...String(t || '').matchAll(/(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])/g)].map((m) => m[1].padStart(2, '0') + ':' + m[2]);
  const montos = (t) => (VC ? VC.montos(t) : []);

  function verificar(e) {
    const ctx = e.ctx || {}; const salida = e.salida || null;
    const cita = lim(e.texto_paciente, 200);
    const fallaAgente = !salida || typeof salida !== 'object' || !!salida.error;
    const ps = fallaAgente ? [] : pasosDe(salida);
    const llamados = [...new Set(ps.map((p) => p.tool).filter((t) => ESPECIALISTAS.includes(t)))];
    const noResp = ps.some((p) => p.tool === 'no_responder');
    const crudo = fallaAgente ? '' : (typeof salida.output === 'string' ? salida.output : (typeof salida.text === 'string' ? salida.text : (salida.output === undefined || salida.output === null ? '' : JSON.stringify(salida.output)))).trim();
    const traza = ps.map((p) => ({ tool: p.tool, input: p.input, obs: lim(p.obs, 400) }));
    const agentes = llamados.map((a) => ({ agente: a, estado: (ps.filter((p) => p.tool === a).map((p) => Object.keys(p.sec)[0]).find(Boolean)) || 'respondido' }));
    const escalo = ps.some((p) => ESPECIALISTAS.includes(p.tool) && (p.sec['ESCALÓ'] || /\bescalar_a_secretaria\b/.test(p.obs)));
    const base = { texto: null, silencio: false, avisos: [], motivo_verificador: null, usado_respaldo: false, fallo_agente: false, modo_humano: false, traza, agentes, llamados, plan: { agente_padre: true, llamados, no_responder: noResp, comprobante_forzado: ctx.comprobante_marcado === true } };
    const hecho = (x) => ({ ...base, ...x });
    const silencio = (motivo) => hecho({ silencio: true, motivo_verificador: motivo || null });
    const aviso = (txt) => ({ nivel: 'ACCION', texto: '[ACCIÓN] ' + txt + ': «' + cita + '»' });
    // Respaldo: lo que devolvieron los especialistas como TEXTO_FIJO (o la pregunta de FALTA); si no hay nada, "no le entendí" (o el error si el agente se cayó).
    const respaldo = (motivo, extra) => {
      const x = extra || {}; const fijos = [], faltas = [];
      for (const p of ps) { if (!ESPECIALISTAS.includes(p.tool)) continue; for (const v of (p.sec.TEXTO_FIJO || [])) if (v && !fijos.includes(v)) fijos.push(v); for (const v of (p.sec.FALTA || [])) if (v && !faltas.includes(v)) faltas.push(v); }
      let texto = x.texto || fijos.join('\n\n') || faltas.join('\n\n') || (fallaAgente ? TEXTOS.ERROR : TEXTOS.NO_ENTENDI);
      const avisos = (x.avisos || []).slice();
      if (fallaAgente || !x.sinAviso) avisos.push(aviso('El orquestador v6 usó el respaldo (' + motivo + ')'));
      return hecho({ texto, silencio: false, avisos, motivo_verificador: motivo, usado_respaldo: true, fallo_agente: fallaAgente });
    };

    // a) charla que inició la clínica con un contacto sin ficha: ni se llamó al agente
    if (ctx.charla_de_la_clinica === true) return silencio('charla_de_la_clinica');
    // b) agente caído / vacío
    if (fallaAgente) return respaldo(!salida ? 'agente_sin_salida' : 'agente_error');
    // e) comprobante marcado por la entrada y nadie lo registró: sale la recepción y se avisa al grupo (la secretaria tiene que verlo)
    const faltaComprobante = ctx.comprobante_marcado === true && !llamados.includes('agente_confirmar');
    // f) silencio decidido por el agente
    const silenciar = noResp || /^\[?NO_REPLY\]?$/i.test(crudo);
    if (silenciar) {
      if (faltaComprobante) return respaldo('comprobante_sin_confirmar', { texto: TEXTOS.COMPROBANTE, avisos: [aviso('Llegó un comprobante de pago y el orquestador v6 no lo pasó por agente_confirmar')], sinAviso: true });
      if (llamados.length) return respaldo('silencio_con_resultados', { sinAviso: true });
      return silencio(null);
    }
    if (!crudo) return respaldo('vacio');
    // forma: la respuesta al paciente es texto; JSON, código o etiquetas internas son basura del modelo
    if (/^\s*[\[{]/.test(crudo) || /"(?:output|tool|action|pasos)"\s*:|```/.test(crudo) || crudo.length > 1800 || new RegExp('^\\s*(?:' + MARCAS.join('|') + ')\\s*:', 'm').test(crudo)) return respaldo('forma_invalida');
    // c) consistencia con el prompt: las frases del incidente del 9/5
    for (const [nombre, rx] of FRASES) if (rx.test(crudo)) return respaldo('frase_del_incidente:' + nombre);
    // e) comprobante sin pasar por agente_confirmar
    if (faltaComprobante) return respaldo('comprobante_sin_confirmar', { texto: TEXTOS.COMPROBANTE, avisos: [aviso('Llegó un comprobante de pago y el orquestador v6 no lo pasó por agente_confirmar')], sinAviso: true });
    // d) horarios y montos: tienen que salir de lo que devolvió un especialista en ESTE mensaje (o ser algo que el paciente ya escribió)
    const obsTodas = ps.filter((p) => ESPECIALISTAS.includes(p.tool)).map((p) => p.obs).join('\n');
    const horasOk = new Set(horas(obsTodas).concat(horas(e.texto_paciente), horas(e.contexto)));
    const horasAjenas = [...new Set(horas(crudo))].filter((h) => !horasOk.has(h));
    if (horasAjenas.length) return respaldo('horario_no_respaldado:' + horasAjenas.join(','));
    const montosOk = new Set(montos(e.consulta).concat(montos(obsTodas), montos(e.texto_paciente)));
    const montosAjenos = montos(crudo).filter((m) => !montosOk.has(m));
    if (montosAjenos.length) return respaldo('monto_no_respaldado:' + montosAjenos.join(','));

    const avisos = [];
    // el sistema no puede frenar el aviso que mandó escalar_a_secretaria, pero deja constancia si la clínica ya estaba en la charla
    if (ctx.staff_reciente === true && escalo) avisos.push(aviso('Asiri derivó a la secretaria pero la clínica le escribió hace menos de 6 h (revisar si hacía falta)'));
    return hecho({ texto: crudo, silencio: false, avisos, partes: { agente: crudo } });
  }
  return { verificar, pasosDe, secciones, desenvolver, horas, ESPECIALISTAS, TEXTOS };
})();
if (typeof module !== 'undefined') module.exports = V6Salida;
