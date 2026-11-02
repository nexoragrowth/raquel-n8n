// v6_salida_core.js — "v6 Orquestador": revisa, POR CÓDIGO, lo que escribió el agente padre antes de que salga al paciente (puro, sin red).
// Por qué NO se reusa VerificadorCore.verificar entero: ese módulo entiende las herramientas del v7 (turnos/pagos/informacion/urgencias que devuelven objetos con
// estado, libro de escrituras y propuestas en Redis). Los especialistas del v6 devuelven TEXTO LIBRE (con secciones HICE:/DATOS:/TEXTO_FIJO:/FALTA:...) y escriben
// directo en Dentalink: no hay libro ni propuesta que leer. De VerificadorCore se reusan solo `montos` y `FRASES_INCIDENTE` (si están cargados en el mismo nodo).
// Reglas (cualquiera que falle = RESPALDO; el motivo queda en `motivo_verificador`):
//   a) charla que inició la clínica con un contacto sin ficha → silencio   b) agente caído/vacío/basura → "no le entendí" o error + aviso
//   c) frases del incidente del 9/5 → respaldo   d) horarios (HH:MM) y montos en pesos que no salieron de un especialista de ESTE mensaje → respaldo
//   e) comprobante MARCADO por la entrada y agente_confirmar no llamado → respaldo con el texto de recepción + aviso   f) silencio decidido por el agente (no_responder / [NO_REPLY])
//   g) (nov) datos bancarios SOLO por código: el padre escribe el marcador [DATOS_DE_PAGO] (herramienta datos_pago) y este módulo lo reemplaza por el texto armado por el código;
//      alias/CBU/CUIT/cuenta escritos a mano o un número de 10+ dígitos → respaldo; marcador sin herramienta → respaldo
//   h) (nov) urgencia: si el padre llamó a agente_urgencia → derivar_triaje=true + triaje (mismo formato que el cerebro) y texto suprimido (contesta el circuito de triaje)
//   i) (nov) brevedad: la frase de derivación aparece UNA vez; más de 700 caracteres que no sean lista de horarios → respaldo
const V6Salida = (() => {
  const OC = (() => { if (typeof OrquestadorCore !== 'undefined') return OrquestadorCore; try { return (typeof module !== 'undefined' && typeof require !== 'undefined') ? require('./orquestador_core.js') : null; } catch (x) { return null; } })();
  const VC = (() => { if (typeof VerificadorCore !== 'undefined') return VerificadorCore; try { return (typeof module !== 'undefined' && typeof require !== 'undefined') ? require('./verificador_core.js') : null; } catch (x) { return null; } })();
  const ESPECIALISTAS = ['agente_agendar', 'agente_confirmar', 'agente_cancelar', 'agente_urgencia', 'agente_general'];
  const TEXTOS = {
    NO_ENTENDI: (OC && OC.TEXTOS.NO_ENTENDI) || 'Disculpe, no le entendí bien. ¿Me lo puede escribir de otra forma?',
    ERROR: (OC && OC.TEXTOS.ERROR) || 'Disculpe, tuve un inconveniente para responderle en este momento. Le aviso a la clínica para que se comunique con usted.',
    COMPROBANTE: 'Recibimos su comprobante. Le informo a la secretaria, que verificará el pago en su horario de atención. ¡Muchas gracias!',
    DERIVA: (OC && OC.TEXTOS.DERIVA) || 'Le paso con la secretaria para que lo atienda.',
    DATOS_PAGO: 'Le paso los datos para transferir:',
  };
  const MARCADOR = '[DATOS_DE_PAGO]';
  const MAX_CHARS = 700;   // más que esto, y que no sea una lista de horarios, es un mensaje largo: respaldo
  const escRx = (x) => String(x).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // La frase de derivación: la fija de hoy y la del v6 (por si algún especialista la devuelve en un TEXTO_FIJO).
  const RX_DERIVA = new RegExp(escRx(TEXTOS.DERIVA.replace(/\.$/, '')) + '\\.?|Le transmito su (?:consulta|caso) a la secretaria[^.!]*[.!](?:\\s*¡Muchas gracias!)?', 'g');
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
  // Datos de pago armados por el código (líneas "Alias: x", "Titular: y"...): los valores sensibles son alias, CUIT/CUIL, CBU y nro. de cuenta.
  function sensibles(datos) {
    return String(datos || '').split('\n').map((l) => l.match(/^\s*(Alias|CUIT\/CUIL|CBU|Nro\. de cuenta)\s*:\s*(.+?)\s*$/i)).filter(Boolean).map((m) => m[2]).filter((v) => v.length >= 6);
  }
  const digitos = (t) => String(t || '').replace(/\D/g, '');
  // ¿El texto trae datos bancarios escritos por el modelo? (alias/CBU/CUIT/cuenta reales o inventados, o un número de 10+ dígitos que no escribió el paciente)
  function datosPagoEscritos(texto, datos, textoPaciente) {
    const t = String(texto || '').split(MARCADOR).join('');
    if (sensibles(datos).some((v) => norm(t).includes(norm(v)))) return true;
    if (/\b(?:alias|cbu|cvu)\s*[:\-][ \t]*\S+/i.test(t)) return true;
    if (/\balias\s+(?:es|ser[ií]a|:)\s+\S+/i.test(t) || /\b(?:alias|cbu|cvu)\b[^\n]{0,30}?\b[\w-]+(?:\.[\w-]+)+\b/i.test(t)) return true;   // "el alias es X" / "alias: x.y.z" en prosa
    const propios = digitos(textoPaciente);
    const corridas = t.match(/\d(?:[\s.-]?\d){9,}/g) || [];
    return corridas.some((c) => !propios.includes(digitos(c)));
  }
  // Deja UNA sola frase de derivación (las demás se sacan) y prolija la puntuación.
  function unaDerivacion(texto) {
    let n = 0;
    const out = String(texto).replace(RX_DERIVA, (m) => (++n === 1 ? m : ''));
    return n > 1 ? out.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').replace(/[ \t]{2,}/g, ' ').trim() : String(texto);
  }

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
    const base = { texto: null, silencio: false, derivar_triaje: false, triaje: null, avisos: [], motivo_verificador: null, usado_respaldo: false, fallo_agente: false, modo_humano: false, traza, agentes, llamados, plan: { agente_padre: true, llamados, no_responder: noResp, comprobante_forzado: ctx.comprobante_marcado === true } };
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
    // h) urgencia: el padre llamó al especialista Urgencia → decide el CÓDIGO (no un regex sobre lo que escribió el paciente). Responde el circuito de triaje, no este texto.
    if (llamados.includes('agente_urgencia')) {
      const otras = llamados.filter((a) => a !== 'agente_urgencia').length > 0;
      const av = otras ? [{ nivel: 'FYI', texto: '[FYI] Mensaje derivado al triaje de urgencias; además pidió otras cosas que Asiri no respondió: «' + cita + '». Revisar.' }] : [];
      return hecho({ silencio: true, derivar_triaje: true, triaje: { motivo: 'derivar_triaje', cita: lim(e.texto_paciente, 300) }, avisos: av, motivo_verificador: 'urgencia_a_triaje' });
    }
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
    // g) datos bancarios: solo por el marcador. Se autoriza si el padre llamó a datos_pago o si un TEXTO_FIJO de un especialista lo trae (texto fijo del v6, sin datos reales).
    const datosOk = ps.some((p) => p.tool === 'datos_pago');
    const conMarcador = crudo.includes(MARCADOR);
    const datos = String(e.datos_pago || '').trim();
    const autorizado = datosOk || ps.some((p) => ESPECIALISTAS.includes(p.tool) && p.obs.includes(MARCADOR));
    if (datosPagoEscritos(crudo, datos, e.texto_paciente)) return respaldo('datos_pago_escritos_por_el_agente', datosOk && datos ? { texto: TEXTOS.DATOS_PAGO + '\n' + datos } : undefined);
    if (conMarcador && !autorizado) return respaldo('marcador_datos_pago_sin_herramienta');
    if (conMarcador && !datos) return respaldo('datos_pago_sin_datos');
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

    // i) brevedad: una sola derivación; un mensaje largo que no sea lista de horarios no sale
    let texto = unaDerivacion(crudo);
    if (texto.length > MAX_CHARS && horas(texto).length < 3) return respaldo('texto_largo');
    // g) el código pega los datos: en el marcador; si el padre llamó a datos_pago y no escribió el marcador, al final
    if (conMarcador) {
      let usado = false;
      texto = texto.split(MARCADOR).map((x, i, a) => x + (i < a.length - 1 && !usado && (usado = true) ? datos : '')).join('').replace(/\n{3,}/g, '\n\n').trim();
    } else if (datosOk && datos) texto = texto.replace(/\s+$/, '') + '\n' + datos;
    const avisos = [];
    // el sistema no puede frenar el aviso que mandó escalar_a_secretaria, pero deja constancia si la clínica ya estaba en la charla
    if (ctx.staff_reciente === true && escalo) avisos.push(aviso('Asiri derivó a la secretaria pero la clínica le escribió hace menos de 6 h (revisar si hacía falta)'));
    return hecho({ texto, silencio: false, avisos, datos_pago_agregados: (conMarcador || (datosOk && datos)) ? 'pedido' : null, partes: { agente: crudo } });
  }
  return { verificar, pasosDe, secciones, desenvolver, horas, sensibles, datosPagoEscritos, unaDerivacion, ESPECIALISTAS, TEXTOS, MARCADOR, MAX_CHARS };
})();
if (typeof module !== 'undefined') module.exports = V6Salida;
