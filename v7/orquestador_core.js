// orquestador_core.js — v7 · ORQUESTADOR + SUB-AGENTES (08/10, orden de Lucas: "para algo tenemos el agente orquestador, para orquestar agentes; 0 conversaciones").
// Fuente de verdad en el repo: se inlinea en los nodos Code del cerebro y de cada sub-agente, y se prueba offline (tests/test_orquestador_core.mjs).
//
// Reparto (docs/v7-orquestador-subagentes-2026-10-08.md, §8 "Cambios por la crítica"):
//   - La IA DECIDE: el ORQUESTADOR (una llamada, salida JSON) entiende qué quiso decir el paciente y elige agentes o una acción fija;
//     cada SUB-AGENTE (Turnos, Pagos, Información, Urgencias) elige sus herramientas y devuelve un CÓDIGO (Información es la única que redacta).
//   - El CÓDIGO EJECUTA Y COMPONE: despacha (una llamada por sub-agente y por mensaje), arma el texto para el paciente con lo que devolvieron las
//     herramientas (read-back, bloque, éxito, recepción de pago, derivación, menú) y lo verifica contra la agenda (chequeo_salida).
//   - Ninguna regex lee el mensaje del PACIENTE para decidir su intención. Las regex de este archivo solo leen textos NUESTROS (la salida del modelo,
//     el menú del panel, el texto compuesto) y fallan del lado seguro.
const OrquestadorCore = (() => {
  // En n8n el chequeo va inlineado antes (nodo Salida); en los sub-agentes no hace falta (null). Offline (node) se carga del repo.
  const CS = (() => { if (typeof ChequeoSalida !== 'undefined') return ChequeoSalida; try { return (typeof module !== 'undefined' && typeof require !== 'undefined') ? require('./chequeo_salida.js') : null; } catch (x) { return null; } })();
  const AGENTES = ['turnos', 'pagos', 'informacion', 'urgencias'];
  const FIJAS = ['menu_bienvenida', 'presentacion_anuncio', 'derivar_secretaria', 'pasar_a_humano', 'no_entendi', 'pedir_texto', 'no_reply'];
  const lim = (s, n) => String(s === undefined || s === null ? '' : s).trim().slice(0, n);
  const norm = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9:/? ]+/g, ' ').replace(/\s+/g, ' ').trim();

  // Textos fijos (los arma el código; ningún modelo los redacta). DERIVA es el mismo texto que ClinicaCore.TEXTOS.DERIVA (test).
  const TEXTOS = {
    DERIVA: 'Le paso con la secretaria para que lo atienda.',
    NO_ENTENDI: 'Disculpe, no le entendí bien. ¿Me lo puede escribir de otra forma? Puedo ayudarlo con turnos, pagos o información del consultorio.',
    PEDIR_TEXTO: 'Disculpe, por este medio no puedo escuchar audios. ¿Me lo puede escribir, por favor?',
    PRESENTACION: 'Soy Asiri, la secretaria virtual de la Dra. Raquel.',
    ERROR: 'Disculpe, tuve un inconveniente para responderle en este momento. Le aviso a la clínica para que se comunique con usted.',
    ERROR_PARCIAL: 'No pude resolver todo en este momento; le aviso a la clínica para que lo complete.',
    URG_FALLO: 'Le paso su mensaje a la doctora para que lo vea.',
    PARA_QUIEN: '¿Para quién es el turno? (nombre o DNI)',
    DATOS_NUEVO: 'Para reservarlo necesito nombre, apellido y DNI del paciente, en un solo mensaje.',
    CUAL_TURNO: '¿Cuál de estos turnos?',
    SIN_TURNOS: 'No veo turnos vigentes con este número de celular.',
    OFERTA_PRIMERA: '¿Quiere que le busque un turno para la primera consulta?',
    HOLA_ANUNCIO: 'Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel Rodríguez, especialista en ortodoncia 🤗',
    RESERVA_PAGO: 'Para confirmarlo definitivamente necesitamos el pago de la consulta hasta 72 hs antes (transferencia o efectivo). Le paso los datos por si le resulta cómodo transferir; en ese caso nos envía el comprobante por este medio, por favor:',
    RESERVA_PAGO_CORTO: 'Para confirmarlo definitivamente necesitamos el pago de la consulta hasta 72 hs antes (transferencia o efectivo); si transfiere, nos envía el comprobante por este medio, por favor.',
  };
  // (B1 de la crítica) El menú enumera SOLO lo que hacemos y cierra con una instrucción, sin pregunta abierta ni cuotas.
  const MENU = 'Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel Rodríguez (Áurea Odontología Estética).\n\n'
    + 'Por acá puedo ayudarle con:\n1. Sacar un turno (primera consulta o control)\n2. Cambiar o cancelar su turno\n3. Confirmar su asistencia a un turno\n'
    + '4. Avisar un pago o pedir los datos para transferir\n5. Información del consultorio: precios, horarios, dirección y tratamientos\n\n'
    + 'Escriba el número de la opción o lo que necesita.';
  // El menú del panel sale tal cual SOLO si respeta el alcance (texto NUESTRO, no del paciente): sin cuotas ni dólares y sin "¿en qué puedo ayudarle?".
  // Si no, va el menú de arriba. (Pendiente en el panel: validar al guardar; ver docs §8.)
  function menuValido(t) {
    const s = String(t || '').trim();
    return s.length >= 40 && s.length <= 900 && !/cuota|d[oó]lar|\busd\b|u\$s/i.test(s) && !/en qu[eé] (?:le |lo |la )?(?:puedo|podemos) ayudar/i.test(s);
  }
  const menu = (panel) => (menuValido(panel) ? String(panel).trim() : MENU);

  // ------------------------------------------------------------------------------------------------ ORQUESTADOR → plan (despacho por código)
  function textoModelo(salida) {
    if (salida === undefined || salida === null) return '';
    if (typeof salida === 'string') return salida;
    return String(salida.text !== undefined ? salida.text : (salida.output !== undefined ? salida.output : ''));
  }
  function parsear(salida) {
    if (!salida || (typeof salida === 'object' && salida.error)) return { ok: false, motivo: 'error_modelo' };
    const t = textoModelo(salida).trim();
    const i = t.indexOf('{'), j = t.lastIndexOf('}');
    if (i < 0 || j < i) return { ok: false, motivo: 'sin_json', crudo: lim(t, 300) };
    let o; try { o = JSON.parse(t.slice(i, j + 1)); } catch (x) { return { ok: false, motivo: 'json_invalido', crudo: lim(t, 300) }; }
    const pasos = Array.isArray(o) ? o : (Array.isArray(o && o.pasos) ? o.pasos : []);
    return { ok: true, pasos: pasos.filter((p) => p && typeof p === 'object').map((p) => ({ a: lim(p.a || p.agente || p.accion, 40).toLowerCase(), pedido: lim(p.pedido, 400), cita: lim(p.cita, 300), motivo: lim(p.motivo, 160) })) };
  }
  const PIDE_DATOS_PAGO = /\balias\b|\bcbu\b|\bcvu\b|datos\s+(?:para\s+(?:transferir|la\s+transferencia|pagar)|bancarios|de\s+(?:la\s+)?cuenta|de\s+pago)|n[uú]mero\s+de\s+cuenta/i;
  // ctx: { prop_pendiente: hay una confirmación guardada, vigente, que el paciente VIO (estado, no texto) }
  function despachar(salida, ctx) {
    const c = ctx || {};
    const p = parsear(salida);
    const plan = { turnos: null, pagos: null, informacion: null, urgencias: null, fija: null, cita: '', motivo: '', descartados: [], fallo_orquestador: false, turnos_por_estado: false, pasos: p.ok ? p.pasos : [] };
    if (!p.ok) { plan.fallo_orquestador = true; plan.motivo_fallo = p.motivo; plan.crudo = p.crudo || null; }
    else {
      const pedidos = {}; const fijas = new Set();
      for (const s of p.pasos) {
        if (AGENTES.includes(s.a)) (pedidos[s.a] = pedidos[s.a] || []).push(s.pedido || '(sin detalle)');
        else if (FIJAS.includes(s.a)) {
          fijas.add(s.a);
          if ((s.a === 'derivar_secretaria' || s.a === 'pasar_a_humano') && s.cita && !plan.cita) plan.cita = s.cita;
          if (s.a === 'derivar_secretaria' && s.motivo && !plan.motivo) plan.motivo = s.motivo;
        } else plan.descartados.push(s.a || '(vacío)');
      }
      // (B6) UNA llamada por sub-agente y por mensaje: los pedidos repetidos van juntos en el mismo pedido.
      for (const a of AGENTES) if (pedidos[a]) plan[a] = [...new Set(pedidos[a])].join(' / ');
      // (20/10, prueba en vivo) "cuánto sale la consulta y pasame el alias": el orquestador mandó TODO a Información (sin Pagos) e Información, por el alias,
      // dijo FUERA_DE_ALCANCE → derivó y se perdió también el precio. Red por código sobre el PEDIDO (texto del orquestador, no del paciente): si menciona
      // los datos para transferir y no hay paso de Pagos, Pagos entra igual.
      if (!plan.pagos && ['informacion', 'turnos'].some((a) => PIDE_DATOS_PAGO.test(plan[a] || ''))) { plan.pagos = 'pide los datos para transferir'; plan.pagos_por_codigo = true; }
      if (fijas.has('pasar_a_humano')) { plan.fija = 'humano'; plan.turnos = plan.pagos = plan.informacion = null; }   // la urgencia, si la hay, se conserva
      else if (fijas.has('derivar_secretaria')) plan.fija = 'derivar';
      const hayAgente = AGENTES.some((a) => plan[a]);
      if (!plan.fija && !hayAgente) {
        // (20/10, BOT-06) el saludo automático de un anuncio lleva la presentación de la clínica (KB 40), no el menú.
        plan.fija = fijas.has('presentacion_anuncio') ? 'anuncio' : fijas.has('menu_bienvenida') ? 'menu' : fijas.has('pedir_texto') ? 'pedir_texto' : fijas.has('no_reply') ? 'no_reply' : 'no_entendi';
      }
    }
    // (B3) Ruteo por ESTADO, no por texto: con una confirmación pendiente que el paciente vio, Turnos SIEMPRE ve este mensaje y decide `confirma`
    // con el MENSAJE ACTUAL. Así un "👍" que el orquestador tomó por cierre no deja morir la propuesta.
    if (c.prop_pendiente && plan.fija !== 'humano' && !plan.turnos) { plan.turnos = 'responde a la confirmación pendiente'; plan.turnos_por_estado = true; }
    plan.hay_agentes = AGENTES.some((a) => plan[a]);
    plan.contar_no_entendi = plan.fija === 'no_entendi' && !plan.hay_agentes;
    return plan;
  }

  // ------------------------------------------------------------------------------------------------ SUB-AGENTES → salida (texto armado por código)
  function pasosDe(ag) {
    return (Array.isArray(ag && ag.intermediateSteps) ? ag.intermediateSteps : []).map((s) => {
      const tool = s && s.action && s.action.tool;
      let obs = s && s.observation;
      if (typeof obs === 'string') { try { obs = JSON.parse(obs); } catch (x) { obs = { crudo: obs }; } }
      if (Array.isArray(obs)) obs = obs.length && obs[0] && typeof obs[0] === 'object' ? (obs[0].json || obs[0]) : {};
      return { tool, input: s && s.action ? s.action.toolInput : null, obs: obs && typeof obs === 'object' ? obs : {} };
    });
  }
  const traza = (ps) => ps.map((p) => ({ tool: p.tool, input: p.input, obs: lim(JSON.stringify(p.obs), 400) }));
  // Código que devolvió el modelo (texto NUESTRO). Cualquier otra cosa se descarta: nunca llega al paciente.
  // (08/10, revisión) El código tiene que ser la respuesta ENTERA o una línea sola (con o sin comillas/asteriscos/punto). Antes era `includes`
  // y la respuesta legítima de Información "no tenemos guardia de urgencias" se tomaba como el código URGENCIA: el paciente perdía la respuesta.
  function codigo(salida, permitidos) {
    const limpiar = (l) => l.trim().toUpperCase().replace(/^[\s*`"'«».:-]+|[\s*`"'«».:!-]+$/g, '');
    const lineas = textoModelo(salida).split(/\r?\n/).map(limpiar).filter(Boolean);
    for (const c of permitidos) if (lineas.includes(c)) return c;
    return null;
  }
  const COD_TURNOS = ['FUERA_DE_ALCANCE', 'URGENCIA', 'PREGUNTA_PARA_QUIEN', 'PREGUNTA_DATOS_NUEVO', 'PREGUNTA_CUAL_TURNO', 'MOSTRAR_TURNOS', '[NO_REPLY]', '[LISTO]'];
  const COD_SIMPLE = ['FUERA_DE_ALCANCE', 'URGENCIA', '[NO_REPLY]', '[LISTO]'];
  const lista = (ts) => ts.map((t) => '- ' + t).join('\n');

  // Qué le dice al paciente cada resultado de herramienta de TURNOS (texto del código; nada sale del modelo).
  function textoTurnos(p) {
    const o = p.obs || {};
    if (p.tool === 'buscar_horarios') {
      if (o.ok && o.bloque) return { texto: String(o.bloque).trim(), estado: 'bloque_ofrecido' };
      // (08/10, REAL-12) Antes: dos frases secas que se repetían igual en cada mensaje. Ahora una sola (unir() deduplica) que ofrece la salida: otra fecha o lista de espera.
      if (o.sin_horarios_nuevos) return { texto: TEXTO_SIN_DISPONIBILIDAD, estado: 'sin_horarios_nuevos' };
      if (o.motivo === 'sin_turnos') return { texto: TEXTO_SIN_DISPONIBILIDAD, estado: 'sin_turnos' };
      if (o.motivo === 'limite_de_bloques') return { texto: 'No tengo más horarios para ofrecerle por acá.', derivar: 'pidió más horarios de los que Asiri puede ofrecer', estado: 'limite' };
      return { error_tecnico: true, estado: 'error' };
    }
    if (p.tool === 'gestionar_turno') {
      if (o.texto_para_el_paciente) {
        const estado = o.etapa === 'confirmacion' ? 'readback_pendiente' : o.etapa === 'ejecutado' ? (o.ok === true ? 'escrito_ok' : 'escrito_error') : 'pregunta';
        return { texto: String(o.texto_para_el_paciente).trim(), readback: o.etapa === 'confirmacion', estado };
      }
      const m = o.motivo;
      if (m === 'menos_48h') return { texto: 'Su turno es en menos de 48 horas: no lo puedo cambiar ni cancelar por acá.', derivar: 'turno en menos de 48 h', estado: 'menos_48h' };
      if (['cita_no_vista', 'sin_turnos', 'turno_no_es_de_la_ficha', 'cita_cambio'].includes(m)) return { pregunta: 'CUAL_TURNO', estado: 'pregunta' };
      if (m === 'dni_no_coincide') return { texto: 'Ese nombre ya figura en la agenda con otro DNI. ¿Me confirma el DNI del paciente?', estado: 'pregunta' };
      if (m === 'paciente_nuevo_sin_turnos' || m === 'sin_ficha') return { texto: TEXTOS.SIN_TURNOS, estado: 'sin_turnos' };
      if (m === 'reserva_rechazada') return { texto: 'Ese horario ya no está disponible; no se cambió nada en la agenda.', estado: 'escrito_error' };
      if (m === 'ya_ejecutada') return { texto: 'Ese pedido ya quedó registrado.', estado: 'escrito_ok', ya_ejecutada: true };
      if (m === 'no_pude_registrar' || m === 'dni_en_otra_ficha') return { texto: 'No pude registrarlo en la agenda: la secretaria le termina de agendar el turno.', estado: 'escrito_error' };
      if (m === 'no_pude_cancelar') return { texto: 'No pude cancelar el turno: sigue vigente. Ya le avisé a la clínica para que lo resuelva.', estado: 'escrito_error' };
      if (['no_ofrecido', 'horario_invalido', 'no_hay_turno_para_sumar', 'tipo_invalido', 'fecha_invalida', 'ver_turnos_primero'].includes(m)) return { estado: m };   // el agente tiene que corregir el pedido
      return { error_tecnico: true, estado: 'error' };
    }
    if (p.tool === 'confirmar_turno') {
      if (o.ok === true && o.readback_text) return { texto: String(o.readback_text).trim(), estado: 'confirmado' };
      if (o.motivo === 'varios_recordatorios' && Array.isArray(o.fechas) && o.fechas.length) return { texto: '¿Cuál de estos turnos confirma?\n' + lista(o.fechas), estado: 'pregunta' };
      if (['sin_recordatorio', 'sin_turno_en_esa_fecha', 'cita_no_vigente', 'cita_cambio'].includes(o.motivo)) return { pregunta: 'CUAL_TURNO', estado: 'pregunta' };
      return { error_tecnico: true, estado: 'error' };
    }
    if (p.tool === 'lista_espera') return o.texto_para_el_paciente ? { texto: o.texto_para_el_paciente, estado: 'espera' } : { error_tecnico: true, estado: 'error' };
    if (p.tool === 'elegir_ficha') return o.ok === true ? { estado: 'ficha_elegida' } : { pregunta: 'PARA_QUIEN', estado: 'pregunta' };
    if (p.tool === 'ver_turnos') return o.ok === true ? { turnos: Array.isArray(o.turnos) ? o.turnos : [], estado: 'turnos_vistos' } : (o.motivo === 'sin_ficha' ? { turnos: [], estado: 'sin_ficha' } : { error_tecnico: true, estado: 'error' });
    return { estado: 'herramienta_desconocida' };
  }
  function textoPregunta(cual, turnos) {
    if (cual === 'PARA_QUIEN') return TEXTOS.PARA_QUIEN;
    if (cual === 'DATOS_NUEVO') return TEXTOS.DATOS_NUEVO;
    if (cual === 'CUAL_TURNO') return turnos.length ? TEXTOS.CUAL_TURNO + '\n' + lista(turnos) : TEXTOS.SIN_TURNOS;
    if (cual === 'MOSTRAR_TURNOS') return turnos.length ? (turnos.length === 1 ? 'Su turno vigente es el ' + turnos[0] + '.' : 'Sus turnos vigentes:\n' + lista(turnos)) : TEXTOS.SIN_TURNOS;
    return '';
  }
  // (20/10, BOT-01) Información responde SIN preguntas (su prompt): si el modelo igual suma una ("¿para quién es (nombre o DNI)?"), se quita por
  // código y queda solo la oferta fija. Texto NUESTRO (salida del modelo), nunca el del paciente.
  function sinPreguntas(t) {
    const oferta = t.includes(TEXTOS.OFERTA_PRIMERA);
    let s = t.split(TEXTOS.OFERTA_PRIMERA).join(' ').replace(/[;,:]?\s*¿[^¿?]*\?/g, '');
    if (s.includes('?')) s = s.replace(/[^.!?\n]*\?/g, '');
    s = s.split('\n').map((l) => l.replace(/[ \t]{2,}/g, ' ').replace(/\s+([.,;:])/g, '$1').replace(/[;,]\s*$/, '').trim()).filter(Boolean)
      .map((l) => (/[.!:]$/.test(l) ? l : l + '.')).join('\n');
    return (oferta ? (s ? s + '\n' : '') + TEXTOS.OFERTA_PRIMERA : s).trim();
  }
  // (20/10, prueba en vivo) Si los datos para transferir van en ESTE mensaje, "los datos de cuenta se envían al confirmar el turno" (de los DATOS) se contradice.
  const FRASE_DATOS_LUEGO = /,?\s*(?:y\s+)?(?:los\s+)?datos(?:\s+(?:de\s+(?:la\s+)?cuenta|bancarios|para\s+(?:transferir|la\s+transferencia)))?\s+(?:se\s+(?:los\s+)?(?:env[ií]an|pasan|mandan|dan)|(?:se\s+)?los\s+(?:enviamos|pasamos|mandamos))[^.;\n()]*/gi;
  const PAREN_DATOS_LUEGO = /\s*\([^()]*\bdatos\b[^()]*\b(?:env[ií]an|pasan|mandan|enviamos|pasamos|mandamos)\b[^()]*\)/gi;
  // (20/10, prueba en vivo) Información convirtió los HORARIOS DE ATENCIÓN en "Hay turnos disponibles: martes 20/10 de 8:00 a 12:00…": los turnos
  // reales los da SOLO Turnos (bloque verificado contra la agenda). Se quita toda oración de Información que hable de disponibilidad o pida día y horario.
  // Una "oración" no corta en "$50.000" ni en "Dra. ".
  const ORA = String.raw`(?:\d\.\d|Dra?\.\s|[^.!?\n])*`;
  const ORACION_DISPONIBILIDAD = new RegExp(ORA + String.raw`(?:turnos?\s+(?:disponibles?|libres?)|hay\s+turnos?|disponibilidad|indique\s+(?:el\s+)?d[ií]a\s+y\s+(?:el\s+)?horario|d[ií]a\s+y\s+horario\s+de\s+preferencia)` + ORA + '[.!]?', 'gi');
  // (20/10, BOT-01) "No, ese turno sí voy" a una confirmación pendiente: la propuesta se descarta (Salida, descartar_propuesta) y el paciente lo sabe.
  const SIN_CAMBIOS = { cancelacion: 'Perfecto, no cancelé nada: su turno queda como estaba.', cambio: 'Perfecto, no cambié nada: su turno queda como estaba.',
    reserva: 'Perfecto, no reservé nada. Si quiere otro horario, me avisa.', sumar: 'Perfecto, no reservé nada. Si quiere otro horario, me avisa.' };
  const TEXTO_SIN_DISPONIBILIDAD ='Para lo que pidió no hay turnos disponibles. ¿Quiere que le busque otra fecha, o prefiere que le deje anotado por si se libera uno?';
  const unir = (partes) => { const vistos = new Set(); return partes.filter((x) => { const k = norm(x); if (!x || !k || vistos.has(k)) return false; vistos.add(k); return true; }); };

  // ag = salida del AI Agent de Turnos ({output, intermediateSteps} o {error}); ctx = { turnos: [textos de los turnos vigentes del celular] }
  function salidaTurnos(ag, ctx) {
    const a = ag || {};
    const ps = pasosDe(a);
    const cod = codigo(a.output, COD_TURNOS);
    const base = { agente: 'turnos', codigo: cod, herramientas: ps.map((p) => ({ nombre: p.tool, ok: p.obs.ok === true, etapa: p.obs.etapa || null, motivo: p.obs.motivo || null })), traza: traza(ps),
      texto: '', estado: 'nada', fuera_de_alcance: false, urgencia: false, derivar: null, error_tecnico: false, readback: false,
      texto_libre_descartado: (!cod && textoModelo(a.output).trim()) ? lim(textoModelo(a.output), 300) : null };
    if (a.error && !ps.length) return { ...base, estado: 'error', error_tecnico: true };
    const r = ps.map((p) => ({ tool: p.tool, input: p.input, ...textoTurnos(p) }));
    // (20/10, vivo 318973) "Para ese día no hay…" solo si esa búsqueda vacía era de UN día (desde = hasta, como pide el prompt de Turnos para "pal jueves").
    const diaPuntual = (i) => { let o = i; if (typeof o === 'string') { try { o = JSON.parse(o); } catch (x) { o = {}; } } o = o || {}; return !!o.desde && o.desde === o.hasta; };
    let turnos = Array.isArray((ctx || {}).turnos) ? ctx.turnos : [];
    for (const x of r) if (Array.isArray(x.turnos)) turnos = x.turnos;
    const ultimo = (tool) => { for (let i = r.length - 1; i >= 0; i--) if (r[i].tool === tool && (r[i].texto || r[i].pregunta || r[i].error_tecnico || r[i].derivar)) return r[i]; return null; };
    let g = ultimo('gestionar_turno');
    // (15/10, prueba en vivo) El agente armó la confirmación y en el MISMO mensaje intentó ejecutarla: el código lo frena ('ya_ejecutada', el paciente
    // todavía no vio la pregunta). Ese intento frenado no puede pisar el read-back: el paciente tiene que recibir "¿Procedo…?", no "ya quedó registrado".
    if (g && g.ya_ejecutada) { const rb = r.filter((x) => x.tool === 'gestionar_turno' && x.readback).pop(); if (rb) g = rb; }
    const c = ultimo('confirmar_turno'), le = ultimo('lista_espera'), ef = ultimo('elegir_ficha');
    const bloques = r.filter((x) => x.tool === 'buscar_horarios' && x.texto);
    const partes = []; let pregunta = null, readback = null;
    if (c) { if (c.texto) partes.push(c.texto); if (c.pregunta) pregunta = c.pregunta; }
    if (le && le.texto) partes.push(le.texto);
    if (g && g.readback) readback = g.texto;   // el read-back va SOLO y al final (sin el bloque: el paciente ya eligió)
    else {
      // (08/10) Si en la misma respuesta va un bloque de horarios, el "no hay" queda corto (la salida ya está a la vista); si no, ofrece otra fecha o lista de espera.
      const hayBloque = bloques.some((b) => b.estado === 'bloque_ofrecido');
      // (20/10) Con "menos de 48 h" no van horarios en el mismo mensaje: no se pueden reservar como cambio de ESE turno.
      if (!(g && g.texto && (g.estado === 'escrito_ok' || g.estado === 'menos_48h'))) for (const b of bloques) {
        if (!hayBloque || b.estado === 'bloque_ofrecido') partes.push(b.texto);
        else if (diaPuntual(b.input)) partes.push('Para ese día no hay turnos disponibles.');
      }
      if (g && g.texto) partes.push(g.texto);
      if (g && g.pregunta) pregunta = pregunta || g.pregunta;
    }
    if (ef && ef.pregunta && !readback && !(g && g.texto)) pregunta = pregunta || ef.pregunta;
    if (!readback && !pregunta && cod && cod.startsWith('PREGUNTA_')) pregunta = cod.slice('PREGUNTA_'.length);
    if (!readback && cod === 'MOSTRAR_TURNOS') partes.push(textoPregunta('MOSTRAR_TURNOS', turnos));
    if (pregunta && !readback) partes.push(textoPregunta(pregunta, turnos));
    if (readback) partes.push(readback);
    const texto = unir(partes).join('\n\n');
    const derivar = r.map((x) => x.derivar).find(Boolean) || null;
    const fuera = cod === 'FUERA_DE_ALCANCE' && !texto;
    const error_tecnico = !texto && !fuera && r.some((x) => x.error_tecnico);
    const estado = readback ? 'readback_pendiente' : (g && g.estado === 'escrito_ok') ? 'escrito_ok' : (g && g.estado === 'escrito_error') ? 'escrito_error'
      : (c && c.estado === 'confirmado') ? 'confirmado' : bloques.length ? 'bloque_ofrecido' : pregunta ? 'pregunta' : fuera ? 'fuera_de_alcance'
      : cod === '[NO_REPLY]' && !texto ? 'no_reply' : texto ? 'respondido' : error_tecnico ? 'error' : 'nada';
    return { ...base, texto, estado, readback: !!readback, fuera_de_alcance: fuera, urgencia: cod === 'URGENCIA', derivar, error_tecnico };
  }
  function salidaPagos(ag) {
    const a = ag || {};
    const ps = pasosDe(a);
    const cod = codigo(a.output, COD_SIMPLE);
    const base = { agente: 'pagos', codigo: cod, herramientas: ps.map((p) => ({ nombre: p.tool, ok: p.obs.ok === true, motivo: p.obs.motivo || null })), traza: traza(ps),
      texto: '', estado: 'nada', fuera_de_alcance: false, urgencia: false, derivar: null, error_tecnico: false, datos_pago: false,
      texto_libre_descartado: (!cod && textoModelo(a.output).trim()) ? lim(textoModelo(a.output), 300) : null };
    if (a.error && !ps.length) return { ...base, estado: 'error', error_tecnico: true };
    const reg = [...ps].reverse().find((p) => p.tool === 'registrar_pago');
    const dat = [...ps].reverse().find((p) => p.tool === 'datos_pago');
    const partes = []; let estado = 'nada'; let datos_pago = false; let fuera = cod === 'FUERA_DE_ALCANCE';
    if (reg && reg.obs.texto_para_el_paciente) { partes.push(reg.obs.texto_para_el_paciente); estado = reg.obs.ya_anotado ? 'pago_ya_anotado' : 'pago_anotado'; }
    if (dat && dat.obs.ok === true) { partes.push(dat.obs.texto_para_el_paciente || 'Le paso los datos para transferir:'); datos_pago = true; estado = estado === 'nada' ? 'datos_enviados' : estado; }
    if (dat && dat.obs.fuera_de_alcance) fuera = true;
    const texto = partes.join('\n\n');
    const error_tecnico = !texto && !fuera && ps.some((p) => p.obs.ok !== true && !p.obs.fuera_de_alcance);
    return { ...base, texto, estado: texto ? estado : fuera ? 'fuera_de_alcance' : error_tecnico ? 'error' : estado, datos_pago, fuera_de_alcance: fuera, urgencia: cod === 'URGENCIA' && !texto, error_tecnico };
  }
  // Información: el ÚNICO sub-agente que redacta (1 a 3 frases, solo con los DATOS). Se quitan marcas sueltas; un código gana sobre el texto.
  function salidaInformacion(llm) {
    const a = llm || {};
    const crudo = textoModelo(a).trim();
    const base = { agente: 'informacion', herramientas: [], traza: [], texto: '', estado: 'nada', fuera_de_alcance: false, urgencia: false, derivar: null, error_tecnico: false, ofrece_primera: false };
    if (a.error || !crudo) return { ...base, estado: 'error', error_tecnico: true };
    const cod = codigo(crudo, ['FUERA_DE_ALCANCE', 'URGENCIA']);
    if (cod === 'FUERA_DE_ALCANCE') return { ...base, codigo: cod, estado: 'fuera_de_alcance', fuera_de_alcance: true };
    if (cod === 'URGENCIA') return { ...base, codigo: cod, estado: 'urgencia', urgencia: true };
    if (/^\[NO_REPLY\]$/i.test(crudo)) return { ...base, codigo: '[NO_REPLY]', estado: 'no_reply' };
    const texto = crudo.replace(/\s*\[[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ_ ]{2,40}\]\s*/g, ' ').replace(/[ \t]{2,}/g, ' ').trim();
    return { ...base, texto, estado: 'respondido', ofrece_primera: texto.includes(TEXTOS.OFERTA_PRIMERA), largo: texto.length };
  }
  function salidaUrgencias(ag) {
    const a = ag || {};
    const ps = pasosDe(a);
    const cod = codigo(a.output, COD_SIMPLE);
    const base = { agente: 'urgencias', codigo: cod, herramientas: ps.map((p) => ({ nombre: p.tool, ok: p.obs.ok === true })), traza: traza(ps), texto: '', fuera_de_alcance: false, urgencia: false, derivar: null, error_tecnico: false };
    const derivado = ps.some((p) => p.tool === 'derivar_triaje' && p.obs.ok === true);
    if (derivado) return { ...base, estado: 'derivado' };
    if (cod === 'FUERA_DE_ALCANCE') return { ...base, estado: 'fuera_de_alcance', fuera_de_alcance: true };
    return { ...base, estado: 'derivar_fallo' };   // el orquestador lo vio como urgencia y no se derivó: el cerebro avisa [ACCIÓN URGENTE]
  }

  // ------------------------------------------------------------------------------------------------ después de los agentes (código)
  // (B4 de la crítica, capa b) Un sub-agente que ve una urgencia en el mensaje la devuelve (URGENCIA) y el código la manda a Urgencias aunque el orquestador no lo haya hecho.
  function urgenciaPendiente(plan, res) {
    if (plan && plan.urgencias) return { hacer: true, pedido: plan.urgencias, origen: 'orquestador' };
    const de = AGENTES.filter((a) => res && res[a] && res[a].urgencia === true);
    if (de.length) return { hacer: true, pedido: 'el paciente describe un problema de la boca o del aparato (lo vio ' + de.join(', ') + ')', origen: de.join(',') };
    return { hacer: false, pedido: '', origen: null };
  }
  // ¿Hay que derivar a la secretaria o pasar a una persona? (Fuera de alcance de un sub-agente → derivar por CÓDIGO, una sola vez; sin segundo intento del modelo.)
  function reunir(plan, res, ctx) {
    const c = ctx || {};
    const items = AGENTES.map((a) => res && res[a]).filter(Boolean);
    const fuera = items.filter((x) => x.fuera_de_alcance).map((x) => x.agente);
    const porAgente = items.map((x) => x.derivar).filter(Boolean);
    const humano = plan.fija === 'humano';
    const noEntendiInsiste = plan.contar_no_entendi === true && Number(c.noentendi_n || 0) >= 2;
    const derivar = !humano && (plan.fija === 'derivar' || fuera.length > 0 || porAgente.length > 0 || noEntendiInsiste);
    const motivo = plan.motivo || (fuera.length ? 'fuera del alcance de ' + fuera.join(', ') : porAgente[0] || (noEntendiInsiste ? 'no se entendió el mensaje dos veces seguidas' : ''));
    return { derivar, humano, cita: lim(plan.cita || c.texto_paciente, 300), motivo: lim(motivo, 160), fuera, no_entendi_derivado: noEntendiInsiste };
  }

  // Compone el mensaje final con los textos verificados, en orden fijo: Información → Pagos (+ datos bancarios) → derivación → Turnos (read-back al final).
  function componer(e) {
    const plan = e.plan || {}; const res = e.res || {}; const reunion = e.reunion || {};
    const libros = (e.libros || []).filter(Boolean); const okLibro = libros.filter((l) => l.ok === true); const hayOk = okLibro.length > 0;
    const avisos = []; let motivo_chequeo = null;
    const agentes = AGENTES.filter((a) => res[a]);
    const T = res.turnos, P = res.pagos, I = res.informacion, U = res.urgencias;
    const cita = lim(e.texto_paciente, 200);
    let triaje = e.triaje || null;
    if (!triaje && U && U.estado === 'derivado') triaje = { motivo: 'derivar_triaje', cita: lim(e.texto_paciente, 300) };
    const fin = (texto, extra) => ({ texto: texto || null, silencio: !texto, derivar_triaje: false, triaje: null, avisos, motivo_chequeo, agentes, datos_pago_agregados: null, ...(extra || {}) });

    // 1) Urgencia derivada: responde el triaje del v6. Si en el MISMO mensaje se escribió en la agenda, gana contarle lo que se hizo y la urgencia va al grupo.
    const otrasPartes = [T, P, I].filter((x) => x && x.texto).length;
    if (triaje && !hayOk) {
      if (otrasPartes) avisos.push({ nivel: 'FYI', texto: '[FYI] Mensaje derivado al triaje de urgencias; además pidió otras cosas que Asiri no respondió: «' + cita + '». Revisar.' });
      return fin(null, { silencio: true, derivar_triaje: true, triaje });
    }
    if (triaje && hayOk) avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN URGENTE] La paciente mencionó una urgencia en el mismo mensaje en que se hizo un cambio en la agenda: revisar y contestarle. «' + lim(triaje.cita, 160) + '»' });
    const urgFallo = !!(U && U.estado === 'derivar_fallo');
    if (urgFallo) avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN URGENTE] Asiri no pudo pasar al triaje un mensaje que parece urgencia: «' + cita + '». Contestarle ya.' });

    // 2) Parte de TURNOS: si el sub-agente falló después de escribir (B7), el texto sale del libro; el chequeo corre sobre ESTA parte.
    const propEsta = (e.prop && String(e.prop.exec_id) === String(e.execId) && e.prop.readback_text) ? e.prop.readback_text : null;
    let tTexto = T && T.texto ? T.texto : '';
    if (!tTexto && hayOk) tTexto = okLibro[okLibro.length - 1].readback_text || '';
    if (!tTexto && propEsta) tTexto = propEsta;
    if (tTexto && CS) {
      const c = CS.revisar({ texto: tTexto, libros, libros_previos: e.hechos || [], ofertas: e.ofertas || [], turnos_vistos: e.vistos || [], propuesta_readback: propEsta,
        bloque_ofertas: e.bloque || null, bloque_exec: (propEsta || hayOk) ? null : (e.bloque_exec || null) });
      if (c.accion === 'reemplazar') { tTexto = c.texto; motivo_chequeo = c.motivo; if (c.avisar && c.avisar.nivel === 'ACCION') avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] ' + c.avisar.texto }); }
    }
    // 3) INFORMACIÓN: sin la oferta fija si participó Turnos (no dos preguntas); una afirmación de "quedó hecho" sin escritura se reemplaza.
    let iTexto = I && I.texto ? sinPreguntas(I.texto.replace(ORACION_DISPONIBILIDAD, ' ')) : '';
    if (iTexto && (T || tTexto)) iTexto = iTexto.replace(TEXTOS.OFERTA_PRIMERA, '').trim();
    const datosEnEste = !!e.datosPago && (!!(P && P.datos_pago) || okLibro.some((l) => (l.tipo === 'reserva' || l.tipo === 'sumar') && l.primera_consulta === true));
    if (iTexto && datosEnEste) iTexto = iTexto.replace(PAREN_DATOS_LUEGO, '').replace(FRASE_DATOS_LUEGO, '').replace(/\s+([.,;])/g, '$1').trim();
    if (iTexto && CS) {
      const c = CS.revisar({ texto: iTexto, libros, libros_previos: e.hechos || [], ofertas: [], turnos_vistos: e.vistos || [], propuesta_readback: null, bloque_ofertas: null, bloque_exec: null });
      if (c.accion === 'reemplazar' && /^afirma_/.test(String(c.motivo))) { iTexto = c.texto; motivo_chequeo = motivo_chequeo || 'informacion_' + c.motivo; avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] Asiri (información) afirmó algo de la agenda que no se hizo; revisar y contestarle.' }); }
    }
    // 4) PAGOS: su texto y, debajo, los datos bancarios pegados por código (ningún modelo los ve ni los escribe).
    let pTexto = P && P.texto ? P.texto : '';
    let datos_pago_agregados = null;
    if (P && P.datos_pago) {
      if (e.datosPago) { pTexto = pTexto.replace(/\s+$/, '') + '\n' + e.datosPago; datos_pago_agregados = 'pedido'; }
      else { pTexto = pTexto.replace('Le paso los datos para transferir:', '').trim(); avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] El paciente pidió los datos para transferir y no están cargados (KB 24): pasárselos a mano.' }); }
    }
    // Reserva de PRIMERA CONSULTA (paciente nuevo dado de alta) en esta respuesta: el pedido de pago (como el v6), dentro de la parte de Turnos y sin
    // repetir los datos si ya van en Pagos. (16/10, plan §3.2 #1) A un paciente con ficha que saca un control o suma un turno no se le pide el pago.
    if (tTexto && e.datosPago && okLibro.some((l) => (l.tipo === 'reserva' || l.tipo === 'sumar') && l.primera_consulta === true) && !/\bCBU\b/i.test(tTexto)) {
      tTexto += '\n\n' + (datos_pago_agregados ? TEXTOS.RESERVA_PAGO_CORTO : TEXTOS.RESERVA_PAGO + '\n' + e.datosPago);
      datos_pago_agregados = datos_pago_agregados || 'reserva';
    }
    // 5) Pasar a una persona / derivación con insistencia: solo su texto fijo (más lo que ya se escribió en la agenda, si hubo).
    const dRes = e.derivar_res || null, hRes = e.humano_res || null;
    if (reunion.derivar && (!dRes || dRes.error || dRes.ok !== true)) avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] Asiri quiso derivar a la secretaria y el aviso no salió: «' + cita + '»' });
    if (reunion.humano && (!hRes || hRes.error || hRes.ok !== true)) avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] El paciente pidió hablar con una persona y el aviso no salió: «' + cita + '»' });
    const dTexto = reunion.derivar ? ((dRes && dRes.texto_para_el_paciente) || TEXTOS.DERIVA) : '';
    if (reunion.humano || (dRes && dRes.modo_humano)) {
      const h = reunion.humano ? ((hRes && hRes.texto_para_el_paciente) || TEXTOS.DERIVA) : dTexto;
      return fin(unir([hayOk ? tTexto : '', h]).join('\n\n'), { modo_humano: true, datos_pago_agregados: hayOk ? datos_pago_agregados : null });
    }
    // 6) Armado en orden fijo.
    // (20/10, escalación real 382) Si la derivación la pidió TURNOS (p. ej. turno a < 48 h), primero va el porqué y al final "Le paso con la
    // secretaria" (antes salía al revés: "Le paso con la secretaria… / Su turno es en menos de 48 horas…").
    const turnosDeriva = !!(T && T.derivar) && reunion.derivar === true && !(T && T.readback);
    let partes = unir(turnosDeriva ? [iTexto, pTexto, urgFallo ? TEXTOS.URG_FALLO : '', tTexto, dTexto] : [iTexto, pTexto, urgFallo ? TEXTOS.URG_FALLO : '', dTexto, tTexto]);
    const errores = agentes.filter((a) => res[a].error_tecnico);
    if (errores.length) {
      avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] Asiri no pudo completar (' + errores.join(', ') + '): «' + cita + '». Revisar y contestarle.' });
      partes = partes.length ? partes.concat(hayOk ? [] : [TEXTOS.ERROR_PARCIAL]) : [TEXTOS.ERROR];
    }
    if (!partes.length && plan.fallo_orquestador) { partes = [TEXTOS.ERROR]; avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] Asiri no pudo responder (falló el orquestador): revisar y contestar a mano. «' + cita + '»' }); }
    let esMenu = false;
    if (!partes.length && plan.fija === 'menu') { partes = [e.menu || MENU]; esMenu = true; }
    // (20/10, Lucas: "no hace falta explicar de más: la consulta sale 50 mil") Saludo del anuncio CORTO: quién es Asiri + el precio tal como
    // está en la KB 21 (no escrito a mano) + la oferta de turno. "¿Qué incluye?" lo responde Información con la KB 21 completa.
    // Si la KB 21 no trae un precio, va la presentación larga (KB 40); si tampoco está, el menú.
    if (!partes.length && plan.fija === 'anuncio') {
      const precio = (String(e.consulta || '').match(/^[^.]*?\$\s?\d[\d.]*/) || [])[0];
      partes = [precio ? TEXTOS.HOLA_ANUNCIO + '\n\n' + precio.trim() + '.\n\n' + TEXTOS.OFERTA_PRIMERA : (String(e.anuncio || '').trim() || e.menu || MENU)];
      esMenu = true;
    }
    if (!partes.length && plan.fija === 'pedir_texto') partes = [TEXTOS.PEDIR_TEXTO];
    if (!partes.length && e.prop_pendiente === true && !hayOk && e.prop && String(e.prop.exec_id) !== String(e.execId)) {
      partes = [SIN_CAMBIOS[e.prop.tipo] || 'Perfecto, no hice ningún cambio en la agenda.'];
    }
    if (!partes.length) {
      const callar = plan.fija === 'no_reply' || (agentes.length > 0 && agentes.every((a) => res[a].estado === 'no_reply' || res[a].codigo === '[NO_REPLY]'));
      if (callar) return fin(null, { silencio: true });
      partes = [TEXTOS.NO_ENTENDI];
    }
    let texto = partes.join('\n\n');
    // 7) Presentación en una conversación nueva (dato de 12 h; el menú ya la trae).
    if (e.conversacion_nueva && !esMenu && !/soy asiri/i.test(texto)) texto = TEXTOS.PRESENTACION + '\n\n' + texto;
    return fin(texto, { datos_pago_agregados, partes: { informacion: iTexto || null, pagos: pTexto || null, derivacion: dTexto || null, turnos: tTexto || null } });
  }
  return { AGENTES, FIJAS, TEXTOS, MENU, menuValido, menu, parsear, despachar, pasosDe, codigo, textoTurnos, salidaTurnos, salidaPagos, salidaInformacion, salidaUrgencias, urgenciaPendiente, reunir, componer, norm };
})();
if (typeof module !== 'undefined') module.exports = OrquestadorCore;
