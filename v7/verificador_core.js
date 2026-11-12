// verificador_core.js — v7 "Cerebro Agente" · VERIFICADOR de la salida del agente orquestador (puro, sin red; se prueba con node en tests/test_verificador_core.mjs).
// El agente orquestador (IA con herramientas) le escribe la respuesta al paciente; esto es lo que decide, POR CÓDIGO, si ese texto sale o si sale el RESPALDO
// (las partes que devolvieron las herramientas, armadas con OrquestadorCore.componer: lo que hace hoy el cerebro de orquestador + código).
// Reglas (cualquiera que falle = respaldo; el motivo queda en `motivo_verificador`):
//   a) todo horario/fecha del texto salió de una herramienta de ESTE mensaje (o es un turno que el paciente ya tiene)  → ChequeoSalida
//   b) todo monto en pesos coincide con la consulta de los DATOS (KB 21) o con lo que devolvió una herramienta
//   c) el read-back ("¿Procedo...?") sale TEXTUAL: si el agente no lo pegó, se agrega al final
//   d) los datos de pago (alias, CBU...) los pega el código si la herramienta datos_pago los devolvió; si el agente los escribió, respaldo
//   e) CHEQUEO DE CONSISTENCIA contra el prompt (no es una banlist de salida): si aparece una frase que el prompt prohíbe (las del incidente del 9/5), respaldo
//   f) agente caído / vacío / basura (JSON, código) → respaldo
// No toca el modelo ni la agenda. Lee el libro de escrituras y las ofertas que dejan las herramientas (Redis), nunca lo que diga el modelo sobre lo que hizo.
const VerificadorCore = (() => {
  const OC = (() => { if (typeof OrquestadorCore !== 'undefined') return OrquestadorCore; try { return (typeof module !== 'undefined' && typeof require !== 'undefined') ? require('./orquestador_core.js') : null; } catch (x) { return null; } })();
  const CS = (() => { if (typeof ChequeoSalida !== 'undefined') return ChequeoSalida; try { return (typeof module !== 'undefined' && typeof require !== 'undefined') ? require('./chequeo_salida.js') : null; } catch (x) { return null; } })();
  const AGENTES = ['turnos', 'pagos', 'informacion', 'urgencias'];
  const lim = (s, n) => String(s === undefined || s === null ? '' : s).trim().slice(0, n);
  const norm = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9:/? ]+/g, ' ').replace(/\s+/g, ' ').trim();

  // (e) Frases que el PROMPT prohíbe (incidente del 9/5: «guarda la pieza, traete el DNI, venite ahora mismo, los esperamos»). Chequeo de consistencia con el prompt:
  // si el agente se salió de él, sale el respaldo. No es una lista de palabras malas general: son solo las del incidente y sus variantes.
  const FRASES_INCIDENTE = [
    ['te_esperamos', /\b(?:te|los|lo|la|le)\s+esperamos\b/i], ['venite', /\b(?:venite|veni|vení|vengan?|venga)\s+(?:ya|ahora|hoy)\b|\bvenite\b/i],
    ['ahora_mismo', /\bahora\s+mismo\b/i], ['pida_confirmacion', /\bpid[ae]\s+confirmaci[oó]n\b/i], ['traete', /\btra[eé]te\b|\btraiga\s+(?:el\s+)?dni\b|\btrae\s+(?:el\s+)?dni\b/i],
    ['guarda_la_pieza', /\bguard[ae]\s+la\s+pieza\b/i],
  ];

  // ------------------------------------------------------------------------------------------------ montos (b)
  function montos(texto) {
    const out = new Set(); const s = String(texto || '');
    const num = (d, mil) => { let n = Number(String(d).replace(/[.,]/g, '')); if (mil && n < 1000) n *= 1000; return n; };
    for (const m of s.matchAll(/\$\s?(\d{1,3}(?:[.,]\d{3})+|\d+)(?:\s*(mil)\b)?/gi)) out.add(num(m[1], m[2]));
    for (const m of s.matchAll(/\b(\d{1,3}(?:\.\d{3})+|\d+)\s*(mil\s+)?pesos\b/gi)) out.add(num(m[1], m[2]));
    for (const m of s.matchAll(/\b(\d{1,3})\s*mil\b/gi)) out.add(Number(m[1]) * 1000);
    out.delete(0);
    return [...out];
  }

  // ------------------------------------------------------------------------------------------------ pasos de las herramientas
  const errorSub = (k) => ({ agente: k, estado: 'error', error_tecnico: true, texto: '', herramientas: [], traza: [], codigo: null, fuera_de_alcance: false, urgencia: false, derivar: null, readback: false });
  // Resultado de cada sub-agente (herramienta) y de las acciones fijas. `ps` = [{ tool, input, obs }] (OrquestadorCore.pasosDe + los forzados por código).
  function estructura(ps) {
    const res = {}; let derivar = null, humano = null, noResp = false;
    const llamadas = {};
    for (const p of ps) {
      const t = String(p.tool || '');
      const o = p.obs && typeof p.obs === 'object' ? p.obs : {};
      if (AGENTES.includes(t)) {
        llamadas[t] = (llamadas[t] || 0) + 1;
        const r = (o.agente === t && !o.error) ? o : errorSub(t);
        // varias llamadas al mismo agente: manda la que trae read-back; si no, la última.
        if (!(res[t] && res[t].readback && !r.readback)) res[t] = r;
      } else if (t === 'derivar_secretaria') derivar = { cita: lim(p.input && (p.input.cita_textual || p.input.cita), 300), motivo: lim(p.input && p.input.motivo, 160), res: o };
      else if (t === 'pasar_a_humano') humano = { cita: lim(p.input && (p.input.cita_textual || p.input.cita), 300), res: o };
      else if (t === 'no_responder') noResp = true;
    }
    return { res, derivar, humano, noResp, llamadas };
  }
  const textoDe = (salida) => {
    if (!salida || typeof salida !== 'object') return typeof salida === 'string' ? salida : '';
    const v = salida.output !== undefined ? salida.output : salida.text;
    return typeof v === 'string' ? v : (v === undefined || v === null ? '' : JSON.stringify(v));
  };
  const trazaDe = (ps, res) => {
    const out = [];
    for (const p of ps) {
      const o = p.obs || {};
      if (AGENTES.includes(p.tool)) {
        out.push({ tool: p.tool, input: p.input, obs: lim(JSON.stringify({ estado: o.estado, codigo: o.codigo, texto: lim(o.texto, 160), error: o.error ? true : undefined }), 400), forzado: p.forzado === true || undefined });
        for (const t of (Array.isArray(o.traza) ? o.traza : [])) out.push({ ...t, agente: p.tool });
      } else out.push({ tool: p.tool, input: p.input, obs: lim(JSON.stringify(o), 400), forzado: p.forzado === true || undefined });
    }
    return out;
  };
  // Para el respaldo y la salida de trazas
  const agentesDe = (res) => AGENTES.filter((a) => res[a]).map((a) => ({ agente: a, estado: res[a].estado, codigo: res[a].codigo || null, texto_libre_descartado: res[a].texto_libre_descartado || null }));

  // ------------------------------------------------------------------------------------------------ corte de bucle (igual que OrquestadorCore.componer; helpers no exportados allá)
  const readbackEn = (t) => /¿procedo|le confirmo:|¿confirma|quedó (?:reprogramado|confirmad|reservad)|le reservé|anulé|está confirmado|quedaron confirmados/i.test(String(t || ''));
  const oracionesClave = (t) => String(t || '').split(/\n+/).map((s) => s.trim()).filter((s) => s && (/\?$/.test(s) || /no hay turnos|no tengo más horarios|necesito nombre, apellido y dni/i.test(s)));

  function verificar(e) {
    if (!OC || !CS) throw new Error('VerificadorCore necesita OrquestadorCore y ChequeoSalida');
    const ctx = e.ctx || {}; const st = e.estado || {};
    const T = OC.TEXTOS;
    const salida = e.salida || null;
    const fallaAgente = !salida || typeof salida !== 'object' || !!salida.error;
    const forz = (e.forzados || []).map((f) => ({ tool: f.tool, input: f.input || { forzado: true }, obs: f.obs && typeof f.obs === 'object' ? f.obs : {}, forzado: true }));
    const ps = forz.concat(fallaAgente ? [] : OC.pasosDe(salida));
    const { res, derivar, humano, noResp } = estructura(ps);
    const crudo = fallaAgente ? '' : textoDe(salida).trim();
    const traza = trazaDe(ps, res);
    const libros = (st.libros || []).filter(Boolean); const okLibro = libros.filter((l) => l.ok === true); const hayOk = okLibro.length > 0;
    const hayAg = AGENTES.some((a) => res[a]);
    const cita = lim(e.texto_paciente, 200);
    const resumen = { traza, agentes: agentesDe(res) };
    const plan = {
      agente_orquestador: true, turnos: res.turnos ? (lim(((ps.find((p) => p.tool === 'turnos') || {}).input || {}).pedido, 120) || 'sí') : null,
      pagos: res.pagos ? 'sí' : null, informacion: res.informacion ? 'sí' : null, urgencias: res.urgencias ? 'sí' : null,
      fija: humano ? 'humano' : derivar ? 'derivar' : (noResp && !hayAg) ? 'no_reply' : null, forzados: forz.map((f) => f.tool),
    };
    const base = { motivo_verificador: null, usado_respaldo: false, derivar_triaje: false, triaje: null, avisos: [], motivo_chequeo: null, modo_humano: false, datos_pago_agregados: null, partes: null,
      fallo_agente: false, plan, ...resumen };
    const hecho = (x) => ({ ...base, ...x });
    const silencio = (motivo, extra) => hecho({ texto: null, silencio: true, motivo_verificador: motivo || null, ...(extra || {}) });

    // 0) Charla que inició la clínica con un contacto sin ficha: ni se llamó al agente.
    if (ctx.charla_de_la_clinica === true) return silencio('charla_de_la_clinica');

    // 1) Le contesta a la secretaria (< 6 h, por ESTADO) y el agente SOLO derivó: silencio (la herramienta corrió en modo sombra: no avisó ni silenció el chat).
    if (ctx.staff_reciente === true && derivar && !humano && !hayAg) return silencio('contesta_al_staff');

    // 2) Urgencia derivada al triaje del v6: responde el triaje, v7 en silencio (salvo que en el mismo mensaje se haya escrito en la agenda).
    const triaje = st.triaje || (res.urgencias && res.urgencias.estado === 'derivado' ? { motivo: 'derivar_triaje', cita: lim(e.texto_paciente, 300) } : null);
    const avisosPre = [];
    if (triaje && !hayOk) {
      const otras = ['turnos', 'pagos', 'informacion'].filter((a) => res[a] && res[a].texto).length;
      if (otras) avisosPre.push({ nivel: 'FYI', texto: '[FYI] Mensaje derivado al triaje de urgencias; además pidió otras cosas que Asiri no respondió: «' + cita + '». Revisar.' });
      return silencio(null, { derivar_triaje: true, triaje, avisos: avisosPre });
    }
    if (triaje && hayOk) avisosPre.push({ nivel: 'ACCION', texto: '[ACCIÓN URGENTE] La paciente mencionó una urgencia en el mismo mensaje en que se hizo un cambio en la agenda: revisar y contestarle. «' + lim(triaje.cita, 160) + '»' });

    // ---- RESPALDO: las partes que devolvieron las herramientas, armadas por OrquestadorCore.componer (lo que hace hoy el cerebro) ----
    const respaldo = (motivo, extra) => {
      const rr = { ...res };
      const sinDerivar = AGENTES.filter((a) => a !== 'urgencias').some((a) => rr[a] && rr[a].urgencia === true) && !(rr.urgencias && rr.urgencias.estado === 'derivado');
      if (sinDerivar && !rr.urgencias) rr.urgencias = { agente: 'urgencias', estado: 'derivar_fallo', texto: '', herramientas: [], traza: [], codigo: null, fuera_de_alcance: false, urgencia: false, derivar: null, error_tecnico: false };
      const hay = AGENTES.some((a) => rr[a]);
      const pl = { turnos: null, pagos: null, informacion: null, urgencias: null, fija: null, cita: '', motivo: '', descartados: [], fallo_orquestador: false, turnos_por_estado: false, pasos: [], hay_agentes: hay, contar_no_entendi: false };
      if (humano) { pl.fija = 'humano'; pl.cita = humano.cita; }
      else if (derivar) { pl.fija = 'derivar'; pl.cita = derivar.cita; pl.motivo = derivar.motivo; }
      else if (!hay) { pl.fija = (noResp && !(extra && extra.sinSilencio)) ? 'no_reply' : 'no_entendi'; pl.fallo_orquestador = fallaAgente; }
      if (ctx.staff_reciente === true && pl.fija === 'derivar' && !hay) { pl.fija = 'no_reply'; pl.cita = ''; pl.motivo = 'contesta_al_staff'; }
      const reunion = OC.reunir(pl, rr, { noentendi_n: 0, texto_paciente: e.texto_paciente });
      // 2.º «no entendí» seguido (antes: contador en Redis): si lo último que dijo Asiri ya fue ese mensaje, se deriva (por el corte de bucle de componer).
      const repite = pl.fija === 'no_entendi' && !hay && norm(st.ultimo_asiri) && norm(st.ultimo_asiri).includes(norm(OC.aplicarMensajes(T.NO_ENTENDI, OC.mensajesDe(st.mensajes))));
      const c = OC.componer({ modo: e.modo, texto_paciente: e.texto_paciente, execId: e.execId, plan: pl, reunion, res: rr,
        derivar_res: derivar ? derivar.res : null, humano_res: humano ? humano.res : null, libros, hechos: st.hechos || [], prop: st.prop || null, ofertas: st.ofertas || [], vistos: st.vistos || [],
        bloque: st.bloque || '', bloque_exec: st.bloque_exec || '', triaje: st.triaje || null, ultimo_asiri: st.ultimo_asiri || '', repeticiones: repite ? Math.max(1, st.repeticiones || 0) : (st.repeticiones || 0),
        menu: st.menu, mensajes: st.mensajes || {}, anuncio: st.anuncio || '', consulta: st.consulta || '', datosPago: st.datosPago || '', conversacion_nueva: st.conversacion_nueva === true, prop_pendiente: st.prop_pendiente === true });
      // Derivación que pidió un agente y el orquestador no hizo: el grupo recibe el porqué (no "el aviso no salió", que confundía a la secretaria).
      const avC = motivo === 'derivacion_sin_llamar'
        ? (c.avisos || []).map((a) => /quiso derivar a la secretaria y el aviso no salió/.test(a.texto) ? { nivel: 'ACCION', texto: '[ACCIÓN] Asiri le dijo al paciente que le pasa con la secretaria (' + (reunion.motivo || 'derivación') + '): «' + cita + '». Contestarle por este chat.' } : a)
        : (c.avisos || []);
      return hecho({ ...c, avisos: avisosPre.concat(avC), motivo_verificador: motivo, usado_respaldo: true, fallo_agente: fallaAgente, agentes: agentesDe(rr), plan: { ...plan, fija: pl.fija } });
    };

    // 3) El agente falló / tardó / devolvió vacío
    if (fallaAgente) return respaldo(!salida ? 'agente_sin_salida' : 'agente_error');
    const sinSilencioPorEstado = st.prop_pendiente === true && !hayOk && st.prop && String(st.prop.exec_id) !== String(e.execId);

    // 4) Silencio decidido por el agente (herramienta no_responder, o «[NO_REPLY]»)
    const silenciar = noResp || /^\[?NO_REPLY\]?$/i.test(crudo);
    if (silenciar) {
      const conResultados = AGENTES.some((a) => res[a] && res[a].texto) || derivar || humano;
      if (sinSilencioPorEstado) return respaldo('silencio_con_confirmacion_pendiente', { sinSilencio: true });
      if (conResultados) return respaldo('silencio_con_resultados', { sinSilencio: true });
      return silencio(null);
    }
    if (!crudo) return respaldo('vacio');
    // 5) Forma: la respuesta al paciente es texto; JSON o código es basura del modelo
    if (/^\s*[\[{]/.test(crudo) || /"(?:pasos|output|tool|action)"\s*:|```/.test(crudo) || crudo.length > 1500) return respaldo('forma_invalida');
    // 6) Consistencia con el prompt (e)
    for (const [nombre, rx] of FRASES_INCIDENTE) if (rx.test(crudo)) return respaldo('frase_del_incidente:' + nombre);
    // 7) Herramientas caídas, urgencia sin derivar, fuera de alcance sin derivar
    if (AGENTES.some((a) => res[a] && res[a].error_tecnico)) return respaldo('herramienta_con_error');
    if ((res.urgencias && res.urgencias.estado === 'derivar_fallo') || (AGENTES.filter((a) => a !== 'urgencias').some((a) => res[a] && res[a].urgencia === true) && !(res.urgencias && res.urgencias.estado === 'derivado'))) return respaldo('urgencia_sin_derivar');
    if (AGENTES.some((a) => res[a] && res[a].fuera_de_alcance) && !derivar && !humano) return respaldo('fuera_de_alcance_sin_derivar');
    // (12/11) Un agente pidió derivar (turno a menos de 48 h, más horarios de los que se ofrecen...) y el orquestador no lo hizo: deriva el código, como el cerebro actual.
    // Sin esto el paciente leía "no lo puedo cancelar por acá" y la clínica no se enteraba de que no viene.
    if (AGENTES.some((a) => res[a] && res[a].derivar) && !derivar && !humano) return respaldo('derivacion_sin_llamar');
    // 8) Datos de pago (d): los pega el código; si el agente los escribió, respaldo
    const campos = String(st.datosPago || '').split('\n').map((l) => l.replace(/^[^:]+:\s*/, '').trim()).filter((v) => v.length >= 4);
    if (campos.some((v) => norm(crudo).includes(norm(v))) || (/\d(?:[\s.-]?\d){10,}/.test(crudo) && /\b(?:cbu|cvu|cuenta|cuit|cuil)\b/i.test(crudo)) || /\b(?:alias|cbu|cvu)\s*[:\-]\s*\S+/i.test(crudo)) return respaldo('datos_pago_escritos_por_el_agente');
    // 9) Montos en pesos (b): de la consulta de los DATOS (KB 21) o de una herramienta
    const textosHerr = AGENTES.map((a) => (res[a] && res[a].texto) || '').concat([derivar && derivar.res && derivar.res.texto_para_el_paciente, humano && humano.res && humano.res.texto_para_el_paciente], libros.map((l) => l.readback_text), [st.prop && st.prop.readback_text]).filter(Boolean);
    const permitidosMonto = new Set(montos(st.consulta).concat(...textosHerr.map(montos)));
    const ajenos = montos(crudo).filter((m) => !permitidosMonto.has(m));
    if (ajenos.length) return respaldo('monto_no_respaldado:' + ajenos.join(','));

    // 10) Read-back textual (c): el que armó la herramienta (esta ejecución). Si el agente no lo pegó, va al final.
    let texto = crudo;
    const propEsta = (st.prop && String(st.prop.exec_id) === String(e.execId) && st.prop.readback_text) ? st.prop.readback_text : null;
    const rbHerr = res.turnos && res.turnos.readback ? (propEsta || String(res.turnos.texto || '').split(/\n\n/).pop()) : null;
    if (rbHerr && !norm(texto).includes(norm(rbHerr))) texto = texto.replace(/\s+$/, '') + '\n\n' + rbHerr;

    // 11) Horarios y afirmaciones sobre la agenda (a): ChequeoSalida con lo que dieron las herramientas de ESTE mensaje (no las ofertas viejas de Redis)
    const ofertasEsta = []; for (const p of CS.parejas(textosHerr.join('\n'))) if (!p.startsWith('xx-')) ofertasEsta.push({ fecha: '2000-' + p.slice(0, 5), hora: p.slice(6) });
    const chq = CS.revisar({ texto, libros, libros_previos: st.hechos || [], ofertas: ofertasEsta, turnos_vistos: st.vistos || [], propuesta_readback: propEsta || (res.turnos && res.turnos.readback ? rbHerr : null),
      bloque_ofertas: null, bloque_exec: null });
    if (chq.accion === 'reemplazar') return respaldo('chequeo_salida:' + chq.motivo);

    // ---- el texto del agente sale: lo que agrega el CÓDIGO (datos de pago, derivación, presentación, mensajes fijos, corte de bucle) ----
    const avisos = avisosPre.slice(); let datos_pago_agregados = null;
    if (res.pagos && res.pagos.datos_pago) {
      // El read-back va SIEMPRE al final (el paciente tiene que ver «¿Procedo?» último): los datos bancarios se pegan antes.
      if (st.datosPago) { texto = (rbHerr && texto.includes(rbHerr)) ? texto.replace(rbHerr, '').replace(/\s+$/, '') + '\n' + st.datosPago + '\n\n' + rbHerr : texto.replace(/\s+$/, '') + '\n' + st.datosPago; datos_pago_agregados = 'pedido'; }
      else avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] El paciente pidió los datos para transferir y no están cargados (KB 24): pasárselos a mano.' });
    }
    if (st.datosPago && okLibro.some((l) => (l.tipo === 'reserva' || l.tipo === 'sumar') && l.primera_consulta === true) && !/\bCBU\b/i.test(texto)) {
      texto += '\n\n' + (datos_pago_agregados ? T.RESERVA_PAGO_CORTO : T.RESERVA_PAGO + '\n' + st.datosPago);
      datos_pago_agregados = datos_pago_agregados || 'reserva';
    }
    const aviso = (x, m) => { if (x && !(x.res && x.res.ok === true)) avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] ' + m + ': «' + cita + '»' }); };
    aviso(derivar, 'Asiri quiso derivar a la secretaria y el aviso no salió'); aviso(humano, 'El paciente pidió hablar con una persona y el aviso no salió');
    if (derivar && ctx.staff_reciente === true) avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] Asiri derivó a la secretaria pero la clínica le escribió hace menos de 6 h (el aviso no se envió): «' + cita + '». Revisar.' });
    const textoDeriv = (humano && humano.res && humano.res.texto_para_el_paciente) || (derivar && derivar.res && derivar.res.texto_para_el_paciente) || ((humano || derivar) ? T.DERIVA : '');
    if (textoDeriv && !norm(texto).includes(norm(textoDeriv))) texto = texto.replace(/\s+$/, '') + '\n\n' + textoDeriv;
    const modo_humano = !!humano || !!(derivar && derivar.res && derivar.res.modo_humano);

    const msgs = OC.mensajesDe(st.mensajes);
    const visto = OC.aplicarMensajes(texto, msgs);
    let repeticion = false;
    if (!hayOk && st.ultimo_asiri && !readbackEn(texto)) {
      const antes = norm(st.ultimo_asiri), ahora = norm(visto);
      const repetida = ahora && antes && (ahora === antes || (oracionesClave(visto).length > 0 && oracionesClave(visto).every((o) => antes.includes(norm(o)))));
      if (repetida && Number(st.repeticiones || 0) >= 1) {
        avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] Asiri repitió la misma respuesta y el paciente sigue sin resolver: «' + cita + '». Contestarle por este chat.' });
        return hecho({ texto: OC.aplicarMensajes(T.DERIVA, msgs), silencio: false, avisos, motivo_verificador: 'bucle_cortado', usado_respaldo: true, bucle_cortado: true });
      }
      repeticion = !!repetida;
    }
    if (st.conversacion_nueva === true && !/soy asiri/i.test(texto)) texto = T.PRESENTACION + '\n\n' + texto;
    return hecho({ texto: OC.aplicarMensajes(texto, msgs), silencio: false, avisos, modo_humano, datos_pago_agregados, derivar_triaje: false, triaje: null, ...(repeticion ? { repeticion: true } : {}), partes: { agente: crudo }, motivo_chequeo: null });
  }
  return { verificar, montos, estructura, FRASES_INCIDENTE };
})();
if (typeof module !== 'undefined') module.exports = VerificadorCore;
