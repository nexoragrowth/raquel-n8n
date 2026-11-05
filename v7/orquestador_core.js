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
    PEDIR_TEXTO: 'Disculpe, no pude escuchar bien su audio. ¿Me lo puede escribir, por favor?',   // (28/10) antes decía "no puedo escuchar audios": es falso, los audios se transcriben; esto es solo si la transcripción falló
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

  // (28/10) MENSAJES FIJOS EDITABLES desde el panel (Asiri → "Mensajes fijos"; filas `msg_<CLAVE>` de agente_directrices). La clínica cambia las PALABRAS de estos
  // textos; el código sigue decidiendo CUÁNDO salen. Cada uno se valida acá aunque el panel también lo haga (defensa en profundidad): uno que no pasa se ignora
  // en silencio y sale el estándar. NO entran los de urgencia (URG_FALLO) ni los de pago (RESERVA_PAGO*): llevan una regla de negocio o de seguridad.
  // `pregunta`: tiene que seguir siendo una pregunta (el paciente tiene que saber que le piden algo). `requiere`: lo que el agente de Turnos necesita que se pida.
  const MENSAJES_EDITABLES = {
    DERIVA: {}, NO_ENTENDI: {}, PEDIR_TEXTO: {}, PRESENTACION: {}, ERROR: {}, ERROR_PARCIAL: {}, SIN_TURNOS: {}, HOLA_ANUNCIO: {},
    PARA_QUIEN: { pregunta: true }, CUAL_TURNO: { pregunta: true }, OFERTA_PRIMERA: { pregunta: true },
    DATOS_NUEVO: { requiere: [/nombre/i, /apellido/i, /dni/i] },
  };
  const MENSAJE_MIN = 8, MENSAJE_MAX = 400;
  // Motivo por el que el texto NO sirve como mensaje fijo (null = sirve). Sin precios escritos a mano: el precio sale de Conocimiento y se desactualiza si se copia acá.
  function mensajeInvalido(clave, v) {
    const def = MENSAJES_EDITABLES[clave];
    if (!def) return 'clave no editable';
    const s = String(v === undefined || v === null ? '' : v).trim();
    if (s.length < MENSAJE_MIN) return 'muy corto';
    if (s.length > MENSAJE_MAX) return 'muy largo';
    if (s.includes('{{') || s.includes('}}')) return 'llaves reservadas';
    if (/\$\s*\d|\d{1,3}(?:\.\d{3})+/.test(s)) return 'precio escrito a mano';
    if (/cuota|d[oó]lar|\busd\b|u\$s/i.test(s)) return 'habla de cuotas o dólares';
    if (def.pregunta && !s.includes('?')) return 'tiene que ser una pregunta';
    if (def.requiere && !def.requiere.every((rx) => rx.test(s))) return 'le falta pedir un dato';
    return null;
  }
  // `crudo` = { CLAVE: texto } tal como está en la base. Devuelve solo los que sirven y cambian algo.
  function mensajesDe(crudo) {
    const out = {};
    if (!crudo || typeof crudo !== 'object') return out;
    for (const k of Object.keys(MENSAJES_EDITABLES)) {
      const v = crudo[k];
      if (typeof v !== 'string' || !v.trim() || mensajeInvalido(k, v)) continue;
      if (v.trim() !== TEXTOS[k]) out[k] = v.trim();
    }
    return out;
  }
  // Una sola pasada (no encadena: un texto nuevo que contenga el estándar de otro no se vuelve a reemplazar).
  function aplicarMensajes(texto, mensajes) {
    const claves = Object.keys(mensajes || {});
    if (!texto || !claves.length) return texto;
    const porBase = new Map(claves.map((k) => [TEXTOS[k], mensajes[k]]));
    const bases = [...porBase.keys()].sort((a, b) => b.length - a.length);
    const rx = new RegExp(bases.map((b) => b.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|'), 'g');
    return texto.replace(rx, (m) => porBase.get(m));
  }

  // ------------------------------------------------------------------------------------------------ ORQUESTADOR → plan (despacho por código)
  function textoModelo(salida) {
    if (salida === undefined || salida === null) return '';
    if (typeof salida === 'string') return salida;
    return String(salida.text !== undefined ? salida.text : (salida.output !== undefined ? salida.output : ''));
  }
  // (28/10, caso real 26/10: el orquestador devolvió el agente "payments" y se perdió el registro de un comprobante) Nombres de agente en inglés o en singular: es
  // vocabulario del sistema (no texto del paciente), una lista cerrada. Lo que no esté acá sigue yendo a `descartados`.
  const ALIAS_AGENTE = { payments: 'pagos', payment: 'pagos', pago: 'pagos', appointments: 'turnos', appointment: 'turnos', turno: 'turnos', info: 'informacion', information: 'informacion', 'información': 'informacion', emergency: 'urgencias', emergencies: 'urgencias', urgencia: 'urgencias' };
  const nombreAgente = (a) => ALIAS_AGENTE[a] || a;
  function parsear(salida) {
    if (!salida || (typeof salida === 'object' && salida.error)) return { ok: false, motivo: 'error_modelo' };
    const t = textoModelo(salida).trim();
    const i = t.indexOf('{'), j = t.lastIndexOf('}');
    if (i < 0 || j < i) return { ok: false, motivo: 'sin_json', crudo: lim(t, 300) };
    let o; try { o = JSON.parse(t.slice(i, j + 1)); } catch (x) { return { ok: false, motivo: 'json_invalido', crudo: lim(t, 300) }; }
    const pasos = Array.isArray(o) ? o : (Array.isArray(o && o.pasos) ? o.pasos : []);
    return { ok: true, pasos: pasos.filter((p) => p && typeof p === 'object').map((p) => ({ a: nombreAgente(lim(p.a || p.agente || p.accion, 40).toLowerCase()), pedido: lim(p.pedido, 400), cita: lim(p.cita, 300), motivo: lim(p.motivo, 160) })) };
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
    // (28/10, caso real 27/10 12:18: una paciente mandó un audio que SÍ se transcribió —"…la tomografía la tengo que hacer con o sin los braquets?"— y Asiri
    // le contestó "no puedo escuchar audios") Red por ESTADO: "pedir el texto" solo vale si el audio llegó SIN transcripción. Si había transcripción y el
    // orquestador igual dijo pedir_texto, el mensaje no se descarta: va a la secretaria con lo que dijo, y el aviso la lleva a contestarle.
    if (plan.fija === 'pedir_texto' && c.audio_transcripto === true) {
      plan.fija = 'derivar'; plan.cita = plan.cita || String(c.cita_audio || '').slice(0, 300); plan.motivo = plan.motivo || 'audio transcripto';
      plan.audio_derivado = true;
    }
    // (28/10, caso real 23/10 ejec 321861: un comprobante con recordatorio pendiente fue solo a Turnos y nadie registró el pago) Un comprobante MARCADO por la
    // entrada ("[IMAGEN] TIPO: COMPROBANTE", clasificado por la visión del workflow de entrada, no por texto del paciente) siempre pasa por Pagos, además de lo que el
    // orquestador haya decidido. Por ESTADO, como las otras redes.
    if (c.comprobante_marcado === true && !plan.pagos && plan.fija !== 'humano') { plan.pagos = 'registrar el comprobante de pago que mandó (imagen marcada como comprobante)'; plan.pagos_por_codigo = true; plan.comprobante_forzado = true; }
    // (B3) Ruteo por ESTADO, no por texto: con una confirmación pendiente que el paciente vio, Turnos SIEMPRE ve este mensaje y decide `confirma`
    // con el MENSAJE ACTUAL. Así un "👍" que el orquestador tomó por cierre no deja morir la propuesta.
    if (c.prop_pendiente && plan.fija !== 'humano' && !plan.turnos) { plan.turnos = 'responde a la confirmación pendiente'; plan.turnos_por_estado = true; }
    // (21/10, Lucas + prueba con modelos reales: "dale gracias 👍" a un recordatorio quedó en silencio porque el orquestador lo tomó por cierre, y
    // "si vamos los dos" además ofreció horarios) Ruteo por ESTADO, como la B3: si está respondiendo a un recordatorio, Turnos SIEMPRE ve el mensaje y
    // decide (la IA, no una regex) si es un sí; con la instrucción de confirmar y no buscar horarios salvo que pida otro turno.
    if (c.recordatorio_pendiente && plan.fija !== 'humano' && !c.charla_de_la_clinica) {
      const NOTA_REC = 'responde al recordatorio: si su mensaje es una forma de sí (aunque sea informal) o el comprobante o aviso de pago de ese turno, confirmar_turno UNA vez y vacío; no busques horarios salvo que pida OTRO turno';
      if (!plan.turnos) { plan.turnos = NOTA_REC; plan.turnos_por_estado = true; }
      else if (!plan.turnos.includes('responde al recordatorio')) plan.turnos += ' — ' + NOTA_REC;
    }
    // (20/10, D3; escalaciones reales 380–386: plomero, proveedor, técnico) Charla que inició la CLÍNICA con un contacto SIN ficha: Asiri no
    // responde, no deriva y no avisa al grupo (la secretaria ya está en esa charla). Solo una urgencia que vea el orquestador sigue su camino.
    // (31/10, Lucas: "el silencio dura 1 h"; medido: 23 de 27 respuestas tras un mensaje del staff fueron pasada la hora) Le contesta a la secretaria: si lo
    // último que no escribió el paciente es del STAFF (< 6 h) y el orquestador SOLO decidió derivar (ningún agente), la secretaria ya está en esa charla:
    // silencio y sin aviso al grupo. No toca pasar_a_humano, urgencias ni pedidos a agentes (turnos, pagos, información, recordatorio, confirmación).
    if (c.staff_reciente === true && plan.fija === 'derivar' && !AGENTES.some((a) => plan[a])) { plan.fija = 'no_reply'; plan.cita = ''; plan.motivo = 'contesta_al_staff'; plan.staff_silencio = true; }
    // (05/11) Hay una PROPUESTA DE LA CLÍNICA sin responder (estado, la arma el cerebro): un saludo solo no lleva menú (le está contestando al staff; con el
    // menú guardado como último mensaje de Asiri, la propuesta dejaba de ser "lo último que se le dijo" y el "dale" siguiente se perdía — revisión, JOSE_TRAS_MENU).
    // componer usa la marca para callar (no derivar) si Turnos no tuvo nada que hacer: un rechazo o un "gracias" al staff no van al grupo.
    if (c.staff_reciente === true) plan.staff_reciente = true;   // (05/11, revisión M2) lo usa componer: con el staff en el chat, "no había nada que aplicar" = silencio
    if (c.propuesta_clinica === true) {
      plan.propuesta_clinica = true;
      if (plan.fija === 'menu' && !AGENTES.some((a) => plan[a])) { plan.fija = 'no_reply'; plan.motivo = 'saluda_tras_propuesta_de_la_clinica'; }
    }
    if (c.charla_de_la_clinica) {
      plan.turnos = plan.pagos = plan.informacion = null; plan.turnos_por_estado = false;
      plan.fija = 'no_reply'; plan.cita = ''; plan.motivo = 'charla_de_la_clinica'; plan.charla_de_la_clinica = true;
    }
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

  // (05/11) aceptar_propuesta_clinica es gestionar_turno con accion fija: mismo workflow, mismos resultados.
  const esGestion = (tool) => tool === 'gestionar_turno' || tool === 'aceptar_propuesta_clinica';
  // Qué le dice al paciente cada resultado de herramienta de TURNOS (texto del código; nada sale del modelo).
  function textoTurnos(p) {
    const o = p.obs || {};
    if (p.tool === 'buscar_horarios') {
      if (o.ok && o.bloque) return { texto: String(o.bloque).trim(), estado: 'bloque_ofrecido' };
      // (08/10, REAL-12) Antes: dos frases secas que se repetían igual en cada mensaje. Ahora una sola (unir() deduplica) que ofrece la salida: otra fecha o lista de espera.
      // (21/10, auditoría, ejecución 320042) "Nada nuevo" no es "no hay": si en ese rango siguen libres horarios que ya se le ofrecieron, se le nombran.
      if (o.sin_horarios_nuevos) {
        const ya = (Array.isArray(o.ya_ofrecidos_en_rango) ? o.ya_ofrecidos_en_rango : []).filter((x) => x && /^\d{4}-\d{2}-\d{2}$/.test(String(x.fecha)) && x.hora);
        if (ya.length) return { texto: textoYaOfrecidos(ya), estado: 'ya_ofrecidos', ya_ofrecidos: ya };
        return { texto: TEXTO_SIN_DISPONIBILIDAD, estado: 'sin_horarios_nuevos' };
      }
      if (o.motivo === 'sin_turnos') return { texto: TEXTO_SIN_DISPONIBILIDAD, estado: 'sin_turnos' };
      if (o.motivo === 'limite_de_bloques') return { texto: 'No tengo más horarios para ofrecerle por acá.', derivar: 'pidió más horarios de los que Asiri puede ofrecer', estado: 'limite' };
      return { error_tecnico: true, estado: 'error' };
    }
    if (esGestion(p.tool)) {
      // (05/11) aceptar_propuesta_clinica: la agenda ya estaba como la propuso la clínica → texto del código + aviso FYI (la secretaria esperaba esa respuesta).
      if (o.etapa === 'ya_en_agenda' && o.texto_para_el_paciente) return { texto: String(o.texto_para_el_paciente).trim(), estado: 'ya_en_agenda', aviso: o.aviso ? { nivel: 'FYI', texto: lim(o.aviso, 400) } : null };
      // (05/11) No se pudo aplicar la propuesta de la clínica (fecha incoherente, varias horas, varios turnos…): no se tocó nada; se deriva con el motivo exacto.
      if (o.derivar_staff) return { derivar: lim('aceptó el cambio que propuso la clínica; no aplicado: ' + o.derivar_staff, 120), estado: 'staff_derivado' };   // clinica_core corta el motivo a 120
      // (05/11, revisión P2) El "sí" a un cambio que propuso la clínica no se pudo escribir: el [ACCIÓN] ya lo manda ejecutar_propuesta (no se deriva dos veces).
      if (o.etapa === 'ejecutado' && o.origen === 'staff' && o.ok !== true && !o.texto_para_el_paciente && o.motivo !== 'ya_ejecutada')
        return { texto: 'No pude completar el cambio en la agenda: su turno no se modificó. Ya le avisé a la secretaria para que lo resuelva.', estado: 'escrito_error' };
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
      if (m === 'horario_pasado') return { texto: 'Ese horario ya pasó: no se cambió nada en la agenda.', estado: 'escrito_error' };
      if (m === 'no_pude_registrar' || m === 'dni_en_otra_ficha') return { texto: 'No pude registrarlo en la agenda: la secretaria le termina de agendar el turno.', estado: 'escrito_error' };
      if (m === 'no_pude_cancelar') return { texto: 'No pude cancelar el turno: sigue vigente. Ya le avisé a la clínica para que lo resuelva.', estado: 'escrito_error' };
      if (['no_ofrecido', 'horario_invalido', 'no_hay_turno_para_sumar', 'tipo_invalido', 'fecha_invalida', 'ver_turnos_primero', 'sin_propuesta_staff'].includes(m)) return { estado: m };   // el agente tiene que corregir el pedido
      return { error_tecnico: true, estado: 'error' };
    }
    if (p.tool === 'confirmar_turno') {
      if (o.ok === true && o.readback_text) return { texto: String(o.readback_text).trim(), estado: 'confirmado' };
      if (o.motivo === 'varios_recordatorios' && Array.isArray(o.fechas) && o.fechas.length) return { texto: '¿Cuál de estos turnos confirma?\n' + lista(o.fechas), estado: 'pregunta' };
      if (['sin_recordatorio', 'sin_turno_en_esa_fecha', 'cita_no_vigente', 'cita_cambio'].includes(o.motivo)) return { pregunta: 'CUAL_TURNO', estado: 'pregunta', motivo: o.motivo };
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
  // (21/10) Oraciones que, repetidas, indican un estado trabado: preguntas y "no hay". Un read-back ("¿Procedo…?") no cuenta: se repite a propósito.
  const readbackEn = (t) => /¿procedo|le confirmo:|¿confirma|quedó (?:reprogramado|confirmad|reservad)|le reservé|anulé|está confirmado|quedaron confirmados/i.test(String(t || ''));
  const oracionesClave = (t) => String(t || '').split(/\n+/).map((s) => s.trim()).filter((s) => s && (/\?$/.test(s) || /no hay turnos|no tengo más horarios|necesito nombre, apellido y dni/i.test(s)));
  // (21/10) Horarios que ya se le ofrecieron y siguen libres en lo que pidió. Un día: "El martes 27/10 tengo a las 9:20. ¿Le sirve?"; varios: lista corta.
  const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  const diaCorto = (iso) => `${DIAS[new Date(iso + 'T12:00:00Z').getUTCDay()]} ${Number(iso.slice(8, 10))}/${Number(iso.slice(5, 7))}`;
  const hCorta = (h) => String(h).replace(/^0(\d):/, '$1:');
  const yHoras = (hs) => (hs.length <= 1 ? hs.join('') : hs.slice(0, -1).join(', ') + ' y ' + hs[hs.length - 1]);
  function textoYaOfrecidos(ya) {
    const porDia = new Map();
    for (const x of ya) { const k = String(x.fecha); if (!porDia.has(k)) porDia.set(k, []); if (!porDia.get(k).includes(hCorta(x.hora))) porDia.get(k).push(hCorta(x.hora)); }
    const dias = [...porDia.keys()].sort().slice(0, 6);
    if (dias.length === 1) { const hs = porDia.get(dias[0]); return `El ${diaCorto(dias[0])} tengo a las ${yHoras(hs)}. ${hs.length === 1 ? '¿Le sirve?' : '¿Cuál le queda mejor?'}`; }
    return 'Siguen libres los horarios que le ofrecí:\n' + dias.map((d) => `- ${diaCorto(d)}: ${yHoras(porDia.get(d))}`).join('\n') + '\n¿Le sirve alguno?';
  }
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
    // (05/11, 331596) el porqué viaja al aviso [ACCIÓN] (antes decía solo "no pudo completar")
    if (a.error && !ps.length) return { ...base, estado: 'error', error_tecnico: true, error_detalle: lim(a.error, 200) };
    const r = ps.map((p) => ({ tool: p.tool, input: p.input, ...textoTurnos(p) }));
    // (20/10, vivo 318973) "Para ese día no hay…" solo si esa búsqueda vacía era de UN día (desde = hasta, como pide el prompt de Turnos para "pal jueves").
    const diaPuntual = (i) => { let o = i; if (typeof o === 'string') { try { o = JSON.parse(o); } catch (x) { o = {}; } } o = o || {}; return !!o.desde && o.desde === o.hasta; };
    let turnos = Array.isArray((ctx || {}).turnos) ? ctx.turnos : [];
    for (const x of r) if (Array.isArray(x.turnos)) turnos = x.turnos;
    const ultimo = (tool) => { const es = tool === 'gestionar_turno' ? esGestion : (t) => t === tool; for (let i = r.length - 1; i >= 0; i--) if (es(r[i].tool) && (r[i].texto || r[i].pregunta || r[i].error_tecnico || r[i].derivar)) return r[i]; return null; };
    let g = ultimo('gestionar_turno');
    // (15/10, prueba en vivo) El agente armó la confirmación y en el MISMO mensaje intentó ejecutarla: el código lo frena ('ya_ejecutada', el paciente
    // todavía no vio la pregunta). Ese intento frenado no puede pisar el read-back: el paciente tiene que recibir "¿Procedo…?", no "ya quedó registrado".
    if (g && g.ya_ejecutada) { const rb = r.filter((x) => esGestion(x.tool) && x.readback).pop(); if (rb) g = rb; }
    const c = ultimo('confirmar_turno'), le = ultimo('lista_espera'), ef = ultimo('elegir_ficha');
    const bloques = r.filter((x) => x.tool === 'buscar_horarios' && x.texto);
    const partes = []; let pregunta = null, readback = null;
    // (21/10, incidente familia: "¿Cuál de estos turnos confirma?" + "¿Cuál de estos turnos?" en el mismo mensaje, en bucle) Todas las confirmaciones
    // logradas van al mensaje (no solo la última); si confirmar_turno ya hizo SU pregunta con la lista, no se suma otra pregunta en el mismo mensaje.
    const confOk = r.filter((x) => x.tool === 'confirmar_turno' && x.texto && x.estado === 'confirmado');
    const confPregunto = !!(c && c.texto && c.estado === 'pregunta');
    if (confOk.length) for (const x of confOk) partes.push(x.texto);
    // (21/10, auditoría; el v6 escalaba "paciente confirma pero no tiene turno activo") Quiso confirmar y ver_turnos (de ESTE mensaje: si no se
    // llamó, una lista vacía puede ser un error de consulta) no encontró ningún turno con este celular: se le dice y la confirmación va a la secretaria.
    let confSinTurno = null;
    if (!confOk.length && c && c.pregunta === 'CUAL_TURNO' && ['sin_recordatorio', 'sin_turno_en_esa_fecha'].includes(c.motivo) && !turnos.length
      && r.some((x) => x.tool === 'ver_turnos' && (x.estado === 'turnos_vistos' || x.estado === 'sin_ficha'))) {
      confSinTurno = 'confirma asistencia pero no figura un turno vigente con este celular';
      partes.push('No veo un turno para confirmar con este número de celular.');   // + TEXTOS.DERIVA (reunir deriva por `derivar`)
    } else if (c) { if (c.texto) partes.push(c.texto); if (c.pregunta) pregunta = c.pregunta; }
    if (le && le.texto) partes.push(le.texto);
    if (g && g.readback) readback = g.texto;   // el read-back va SOLO y al final (sin el bloque: el paciente ya eligió)
    else {
      // (08/10) Si en la misma respuesta va un bloque de horarios, el "no hay" queda corto (la salida ya está a la vista); si no, ofrece otra fecha o lista de espera.
      const hayBloque = bloques.some((b) => b.estado === 'bloque_ofrecido' || b.estado === 'ya_ofrecidos');
      // (21/10, auditoría 320042) Si el agente ya entendió que ELIGIÓ (pide datos o para quién), no se le vuelven a listar horarios: con uno solo se lo nombra en la pregunta.
      const yaEligio = cod === 'PREGUNTA_DATOS_NUEVO' || cod === 'PREGUNTA_PARA_QUIEN';
      // (20/10) Con "menos de 48 h" no van horarios en el mismo mensaje: no se pueden reservar como cambio de ESE turno.
      if (!(g && g.texto && (g.estado === 'escrito_ok' || g.estado === 'menos_48h' || g.estado === 'ya_en_agenda'))) for (const b of bloques) {
        if (yaEligio && b.estado !== 'bloque_ofrecido') continue;
        if (!hayBloque || b.estado === 'bloque_ofrecido' || b.estado === 'ya_ofrecidos') partes.push(b.texto);
        else if (diaPuntual(b.input)) partes.push('Para ese día no hay turnos disponibles.');
      }
      if (g && g.texto) partes.push(g.texto);
      if (g && g.pregunta) pregunta = pregunta || g.pregunta;
    }
    if (ef && ef.pregunta && !readback && !(g && g.texto)) pregunta = pregunta || ef.pregunta;
    // (05/11, revisión B3) si la propuesta de la clínica ya se deriva, no se suma una pregunta del modelo ("¿Para quién…?" + "Le paso con la secretaria").
    if (!readback && !pregunta && !confPregunto && !confSinTurno && cod && cod.startsWith('PREGUNTA_') && !r.some((x) => x.estado === 'staff_derivado')) pregunta = cod.slice('PREGUNTA_'.length);
    if (!readback && !confSinTurno && cod === 'MOSTRAR_TURNOS') partes.push(textoPregunta('MOSTRAR_TURNOS', turnos));
    const elegidos = [...new Set(bloques.filter((b) => b.estado === 'ya_ofrecidos').flatMap((b) => b.ya_ofrecidos.map((x) => x.fecha + ' ' + x.hora)))];
    if (pregunta === 'DATOS_NUEVO' && !readback && elegidos.length === 1) partes.push(`Para reservar el ${diaCorto(elegidos[0].slice(0, 10))} a las ${hCorta(elegidos[0].slice(11))} necesito nombre, apellido y DNI del paciente, en un solo mensaje.`);
    else if (pregunta && !readback) partes.push(textoPregunta(pregunta, turnos));
    if (readback) partes.push(readback);
    const texto = unir(partes).join('\n\n');
    // (05/11, revisión MEDIA 4) Quiso aceptar una propuesta de la clínica que el sistema ya no ve (p. ej. pasó otro mensaje en el medio) y no quedó NADA para
    // decirle: nunca un "no le entendí" mudo; la secretaria recibe el aviso con lo que contestó.
    const sinPropuesta = !texto && !readback && r.some((x) => x.estado === 'sin_propuesta_staff') && !r.some((x) => x.texto || x.derivar)
      ? 'respondió a un mensaje de la clínica y Asiri no encontró la propuesta para aplicar' : null;
    const derivar = r.map((x) => x.derivar).find(Boolean) || confSinTurno || sinPropuesta || null;
    const fuera = cod === 'FUERA_DE_ALCANCE' && !texto;
    const error_tecnico = !texto && !fuera && r.some((x) => x.error_tecnico);
    const estado = readback ? 'readback_pendiente' : (g && g.estado === 'escrito_ok') ? 'escrito_ok' : (g && g.estado === 'escrito_error') ? 'escrito_error'
      : (g && g.estado === 'ya_en_agenda') ? 'ya_en_agenda'
      : (c && c.estado === 'confirmado') ? 'confirmado' : (bloques.length && !(pregunta && !bloques.some((b) => b.estado === 'bloque_ofrecido'))) ? 'bloque_ofrecido' : pregunta ? 'pregunta' : fuera ? 'fuera_de_alcance'
      : derivar && !texto ? 'derivar'
      : cod === '[NO_REPLY]' && !texto ? 'no_reply' : texto ? 'respondido' : error_tecnico ? 'error' : 'nada';
    // (05/11) avisos que traen las herramientas (hoy: el FYI de "la agenda ya estaba como la propuso la clínica"); los manda la Salida del cerebro.
    const avisos = r.map((x) => x.aviso).filter(Boolean);
    return { ...base, texto, estado, readback: !!readback, fuera_de_alcance: fuera, urgencia: cod === 'URGENCIA', derivar, error_tecnico, ...(avisos.length ? { avisos } : {}), ...(sinPropuesta && derivar === sinPropuesta ? { sin_propuesta: true } : {}) };
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
    // (05/11, revisión M2) "quiso aceptar una propuesta que no hay" con el staff en el chat (< 6 h) no se deriva: la secretaria ya está ahí (decisión 31/10).
    const porAgente = items.filter((x) => !(x.sin_propuesta === true && plan.staff_reciente === true)).map((x) => x.derivar).filter(Boolean);
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
    // (28/10) Mensajes fijos que la clínica editó en el panel: se aplican UNA vez, sobre el texto ya compuesto (ver MENSAJES_EDITABLES).
    const msgs = mensajesDe(e.mensajes);
    const aplic = (t) => aplicarMensajes(t, msgs);
    const fin = (texto, extra) => ({ texto: aplic(texto) || null, silencio: !texto, derivar_triaje: false, triaje: null, avisos, motivo_chequeo, agentes, datos_pago_agregados: null, ...(extra || {}) });

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
    // (05/11) avisos de las herramientas de Turnos (FYI "la agenda ya estaba como la propuso la clínica"), solo si su texto sale tal cual (el chequeo no lo reemplazó).
    if (T && Array.isArray(T.avisos) && T.texto && tTexto === T.texto) for (const a of T.avisos) if (a && a.texto) avisos.push({ nivel: a.nivel === 'ACCION' ? 'ACCION' : 'FYI', texto: lim(a.texto, 400) });
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
      const detalle = errores.map((a) => res[a].error_detalle).filter(Boolean).map((d) => lim(d, 120)).join(' | ');
      avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] Asiri no pudo completar (' + errores.join(', ') + '): «' + cita + '». Revisar y contestarle.' + (detalle ? ' Detalle técnico: ' + detalle : '') });
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
      const porCierre = plan.fija === 'no_reply';
      const callar = porCierre || (agentes.length > 0 && agentes.every((a) => res[a].estado === 'no_reply' || res[a].codigo === '[NO_REPLY]' || (res[a].sin_propuesta === true && plan.staff_reciente === true)));
      // (21/10, auditoría v6→v7, caso real …6023: 3 mensajes de un paciente nuevo sin ninguna respuesta) Red del v6 "Fallback Output": un sub-agente
      // que dice [NO_REPLY] a un mensaje que el ORQUESTADOR sí clasificó como pedido no es un cierre: se deriva a la secretaria con aviso, nunca silencio.
      // (05/11, revisión con el modelo real: Bautista "no puedo, me quedo con el del 28", Santi "Hoy no llegamos") Le está contestando una PROPUESTA DE LA
      // CLÍNICA y Turnos no tuvo nada que hacer (rechazo, duda, gracias): la secretaria está en esa charla → silencio, como "le contesta al STAFF" (28/10).
      // (revisión M2) con el staff en el chat (< 6 h), lo mismo si el único agente fue Turnos y no tuvo nada que hacer ("ahí lo llevo" a "cambiarle el arco").
      const soloTurnos = agentes.length === 1 && agentes[0] === 'turnos';
      if (callar && !porCierre && (plan.propuesta_clinica === true || (plan.staff_reciente === true && soloTurnos))) return fin(null, { silencio: true, contesta_a_la_clinica: true });
      if (callar && !porCierre) {
        avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] Asiri no supo qué responder (el agente no hizo nada): «' + cita + '». Contestarle por este chat.' });
        return fin(TEXTOS.DERIVA, { sin_respuesta_del_agente: true });
      }
      if (callar) return fin(null, { silencio: true });
      partes = [TEXTOS.NO_ENTENDI];
    }
    let texto = partes.join('\n\n');
    let repeticion = false;
    // (21/10, auditoría) Corte de bucle: si una PREGUNTA o un "no hay" ya salió tal cual en el último mensaje de Asiri y el paciente contestó algo,
    // repetirla una tercera vez no ayuda: se deriva a la secretaria con aviso. Compara texto NUESTRO (el último de Asiri) con texto NUESTRO; las
    // confirmaciones, read-backs y éxitos de la agenda se dejan pasar (repetirlos es inocuo y suelen ser respuestas a un "sí" repetido).
    if (!hayOk && e.ultimo_asiri && !readbackEn(texto)) {
      // (28/10) se compara lo que la paciente VERÍA (con los mensajes editados), porque el último mensaje de Asiri se guardó así.
      const visto = aplic(texto);
      const antes = norm(e.ultimo_asiri), ahora = norm(visto);
      const repetida = ahora && antes && (ahora === antes || (oracionesClave(visto).length > 0 && oracionesClave(visto).every((o) => antes.includes(norm(o)))));
      if (repetida && Number(e.repeticiones || 0) >= 1) {
        avisos.push({ nivel: 'ACCION', texto: '[ACCIÓN] Asiri repitió la misma respuesta y el paciente sigue sin resolver: «' + cita + '». Contestarle por este chat.' });
        return fin(TEXTOS.DERIVA, { bucle_cortado: true });
      }
      repeticion = !!repetida;
    }
    // 7) Presentación en una conversación nueva (dato de 12 h; el menú ya la trae).
    if (e.conversacion_nueva && !esMenu && !/soy asiri/i.test(texto)) texto = TEXTOS.PRESENTACION + '\n\n' + texto;
    return fin(texto, { datos_pago_agregados, ...(repeticion ? { repeticion: true } : {}), partes: { informacion: iTexto || null, pagos: pTexto || null, derivacion: dTexto || null, turnos: tTexto || null } });
  }
  return { AGENTES, FIJAS, TEXTOS, MENU, menuValido, menu, MENSAJES_EDITABLES, mensajeInvalido, mensajesDe, aplicarMensajes, parsear, despachar, pasosDe, codigo, textoTurnos, salidaTurnos, salidaPagos, salidaInformacion, salidaUrgencias, urgenciaPendiente, reunir, componer, norm };
})();
if (typeof module !== 'undefined') module.exports = OrquestadorCore;
