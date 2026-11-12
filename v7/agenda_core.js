// agenda_core.js — v7 · núcleo de las herramientas de AGENDA de Asiri. Fuente de verdad en el repo.
// Se inlinea tal cual dentro de nodos Code de n8n (sin require/import) y se prueba offline con node (tests/test_agenda_core.mjs y tests/test_v7_grafo.py).
// Principio (docs/v7-arquitectura-agente-asiri.md §2-3): el LLM NO confía; acá el código decide.
//   - proponer(...)  valida y arma la propuesta + el read-back POR CODIGO. No escribe nada afuera.
//   - ejecutar: consume la propuesta UNA vez, verifica contra la agenda y escribe: reservar → verificar → anular → verificar.
//     Está partido en PASOS PUROS (paso*, armar*): en n8n cada paso es un nodo Code entre nodos Redis/HTTP; `ejecutar(io)` los compone para los tests.
//     Los pasos reciben y devuelven JSON simple: { fin: resultado } corta; { ok: true, ... } sigue.
const AgendaCore = (() => {
  const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  // (21/10, auditoría v6→v7: un "Si" a los 31 min repetía el mismo read-back) El v6 no vencía la pregunta. 12 h: al ejecutar igual se re-verifica
  // el lugar y la cita vieja contra la agenda, y el sí solo vale si ese read-back es lo ÚLTIMO que dijo Asiri (pendienteVista).
  const TTL_PROPUESTA_MS = 12 * 60 * 60 * 1000;
  const MIN_ANTICIPACION_MS = 48 * 60 * 60 * 1000;
  const ESTADOS_NO_VIGENTES = [1, 14]; // anulado / no vigente (mismo criterio que Step 2b del sub-WF)

  const normHora = (h) => { const m = /^(\d{1,2}):(\d{2})/.exec(String(h || '')); return m ? m[1].padStart(2, '0') + ':' + m[2] : ''; };
  const esISO = (f) => /^\d{4}-\d{2}-\d{2}$/.test(String(f || ''));
  const fechaDe = (iso) => new Date(iso + 'T12:00:00Z');
  const diaSemana = (iso) => DIAS[fechaDe(iso).getUTCDay()];
  const diaMes = (iso) => Number(iso.slice(8, 10));
  const mesNombre = (iso) => MESES[Number(iso.slice(5, 7)) - 1];
  const largo = (iso, hora) => `${diaSemana(iso)} ${diaMes(iso)} de ${mesNombre(iso)} a las ${hora}`;
  const corto = (iso, hora) => `${diaSemana(iso)} ${diaMes(iso)}/${iso.slice(5, 7).replace(/^0/, '')} a las ${hora}`;
  const msTurno = (iso, hora) => Date.parse(`${iso}T${normHora(hora)}:00-03:00`); // Jujuy = UTC-3 todo el año
  const vigente = (t) => !ESTADOS_NO_VIGENTES.includes(Number(t.id_estado)) && Number(t.estado_anulacion || 0) === 0;
  const no = (motivo, para_asiri, extra) => ({ ok: false, motivo, para_asiri, ...(extra || {}) });
  const capital = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  // ----------------------------------------------------------------- paciente nuevo (06/10)
  // Un turno para alguien SIN ficha (lead nuevo, o un familiar que no figura en el celular) se reserva igual: el modelo pasa nombre, apellido y DNI tal como
  // los dijo el paciente, el read-back los muestra, y con el "sí" el código da el alta en la agenda y reserva en la misma ejecución. Antes (v6 y v7) se
  // derivaba a la clínica: la retrospectiva del 06/10 lo marcó como la única falta funcional del v7 frente al v6 (que tenía crear_paciente_dentalink).
  const sinTil = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const soloDig = (x) => String(x || '').replace(/\D/g, '');
  const tokensNombre = (x) => sinTil(x).replace(/[^a-z ]/g, ' ').split(/\s+/).filter((t) => t.length >= 3);
  const tituloNombre = (s) => String(s || '').replace(/[^\p{L}' -]/gu, ' ').replace(/\s+/g, ' ').trim().split(' ').filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');
  const dniLindo = (d) => d.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  // → null (no vino nada) | { faltan: [...] } | { nombre, apellidos, dni }
  function datosNuevo(entrada) {
    const nombre = tituloNombre(entrada.nuevo_nombre), apellidos = tituloNombre(entrada.nuevo_apellido), dni = soloDig(entrada.nuevo_dni);
    if (!nombre && !apellidos && !dni) return null;
    const faltan = [];
    if (nombre.length < 2) faltan.push('nombre');
    if (apellidos.length < 2) faltan.push('apellido');
    if (dni.length < 6 || dni.length > 8) faltan.push('DNI');   // DNI argentino: 6 a 8 dígitos (07/10: el modelo copió "33.444.555" como "334.445.555")
    return faltan.length ? { faltan } : { nombre, apellidos, dni };
  }
  // ¿El paciente "nuevo" es en realidad una ficha que ya está en el celular? Por DNI, o por nombre + apellido (fichas que dio de alta el v6 sin DNI).
  function fichaDelNuevo(fichas, n) {
    const porDni = fichas.filter((f) => soloDig(f.rut) && soloDig(f.rut) === n.dni);
    if (porDni.length === 1) return { id: porDni[0].id };
    const tn = tokensNombre(n.nombre), ta = tokensNombre(n.apellidos);
    const porNombre = fichas.filter((f) => { const ft = tokensNombre(f.nombre + ' ' + (f.apellidos || '')); return tn.some((t) => ft.includes(t)) && ta.some((t) => ft.includes(t)); });
    if (porNombre.length !== 1) return null;
    if (soloDig(porNombre[0].rut) && soloDig(porNombre[0].rut) !== n.dni) return { conflicto: true };
    return { id: porNombre[0].id };
  }

  // (07/10) En los momentos clave el texto para el paciente lo arma el CÓDIGO, como el read-back: el orquestador entiende, elige y pega.
  // Antes los redactaba el modelo a partir de una nota interna y a veces repetía la misma pregunta palabra por palabra o la armaba raro (examen AGE-03).
  // `texto_repregunta`: si el último mensaje de Asiri ya era esa pregunta (el paciente contestó sin elegir), decidir manda esta otra versión.
  const NOTA_PEGAR = '[Nota interna para vos, NO la repitas al paciente] Tu respuesta es texto_para_el_paciente, tal cual y sola. ';
  const conTexto = (motivo, texto, para, extra) => no(motivo, NOTA_PEGAR + para, { texto_para_el_paciente: texto, ...(extra || {}) });
  const lista = (xs, y) => (xs.length <= 1 ? (xs[0] || '') : xs.slice(0, -1).join(', ') + ` ${y} ` + xs[xs.length - 1]);

  // ----------------------------------------------------------------- proponer
  // entrada: { tipo: 'cambio'|'reserva'|'sumar'|'cancelacion', fecha, hora, fecha_turno_viejo, nuevo_nombre?, nuevo_apellido?, nuevo_dni? }   (lo unico que aporta el modelo)
  // estado : { ficha:{fichas:[{id,nombre,apellidos,rut}], elegida}, turnos_vistos:[...], ofertas:[{fecha,hora}], exec_id, tel }   (lo pone el codigo)
  function proponer(entrada, estado, ahoraISO) {
    const ahora = Date.parse(ahoraISO);
    let tipo = String(entrada.tipo || '');
    if (!['cambio', 'reserva', 'sumar', 'cancelacion'].includes(tipo)) return no('tipo_invalido', 'Tipo de propuesta inválido.');
    const ficha = estado.ficha || { fichas: [], elegida: null };
    const fichas = ficha.fichas || [];
    const pedirDatos = 'Cuando mande nombre, apellido y DNI, volvé a llamar gestionar_turno con esos datos (nuevo_nombre, nuevo_apellido, nuevo_dni) y el mismo horario. No le confirmes nada vos.';
    // Paciente nuevo: los datos se piden recién con un horario que SÍ se ofreció (si no, primero hay que ofrecer).
    const horaPedida = normHora(entrada.hora);
    const slotOfrecido = esISO(entrada.fecha) && !!horaPedida && (estado.ofertas || []).some((o) => o.fecha === entrada.fecha && normHora(o.hora) === horaPedida);
    const noOfrecido = () => no('no_ofrecido', 'Ese horario no se le ofreció al paciente. Llamá a buscar_horarios y ofrecé lo que devuelva.');
    let nuevo = datosNuevo(entrada);
    if (nuevo && nuevo.faltan) {
      if (!slotOfrecido && tipo !== 'cancelacion') return noOfrecido();
      return conTexto('faltan_datos_paciente', 'Para registrarlo me falta ' + lista(nuevo.faltan.map((f) => 'el ' + f), 'y') + ' del paciente.', 'Para registrarlo como paciente nuevo falta: ' + nuevo.faltan.join(', ') + '. ' + pedirDatos);
    }
    let elegida = ficha.elegida;
    if (nuevo) {
      const ya = fichaDelNuevo(fichas, nuevo);
      if (ya && ya.conflicto) return no('dni_no_coincide', 'Ese nombre ya tiene ficha en este celular pero con otro DNI: confirmá el DNI con el paciente (una sola pregunta).');
      if (ya) { elegida = ya.id; nuevo = null; }                      // ya tiene ficha: es una reserva común
      else elegida = null;
    }
    if (nuevo) {
      if (tipo === 'sumar') tipo = 'reserva';                            // un paciente nuevo no tiene turno al que sumar
      if (tipo !== 'reserva') return no('paciente_nuevo_sin_turnos', 'Un paciente sin ficha no tiene turnos para cambiar o cancelar. Si quiere un turno, usá tipo reserva; si dice que ya tiene uno, pedile nombre completo y DNI y pasalo a la clínica con avisar_grupo ACCION.');
    } else if (!fichas.length) {
      if ((tipo === 'reserva' || tipo === 'sumar') && !slotOfrecido) return noOfrecido();
      return (tipo === 'reserva' || tipo === 'sumar') ? conTexto('sin_ficha', 'Para reservarle el turno necesito nombre, apellido y DNI del paciente, en un solo mensaje.', 'Es un paciente nuevo: no hay ficha con este celular. ' + pedirDatos,
        { texto_repregunta: 'Disculpe, para registrarlo necesito el nombre, el apellido y el número de DNI del paciente.' })
        : no('sin_ficha', 'No hay ficha con este celular, así que no veo sus turnos. Pedile nombre completo y DNI y pasalo a la clínica con avisar_grupo ACCION.');
    }
    if (!nuevo && !elegida && fichas.length === 1) elegida = fichas[0].id;
    const vistos = nuevo ? (Array.isArray(estado.turnos_vistos) ? estado.turnos_vistos : []) : estado.turnos_vistos;
    // (06/10) Familia sin ficha elegida: si el turno que se cambia/cancela, o el turno al que se le suma otro, es de UNA sola ficha, esa es la ficha
    // (no hay ambigüedad; el read-back igual dice "para <nombre>" y el paciente lo confirma). Examen 06/10: el paciente dijo "Lucas" junto con el horario,
    // el modelo no llamó a elegir_ficha y volvía a preguntar "¿para quién es?".
    if (!nuevo && !elegida && Array.isArray(vistos)) {
      const fichasCon = (lista) => [...new Set(lista.filter(vigente).map((t) => Number(t.id_paciente)))].filter((id) => fichas.some((f) => Number(f.id) === id));
      let ids = [];
      if ((tipo === 'cambio' || tipo === 'cancelacion') && entrada.fecha_turno_viejo) ids = fichasCon(vistos.filter((t) => t.fecha === entrada.fecha_turno_viejo));
      // (07/10) sin fecha: si todos los turnos son de una ficha, es esa. (08/10) También para un turno NUEVO: "familias solo cuando el paciente lo pide"
      // (Lucas). Si no dijo para quién y una sola ficha tiene turnos, es su paciente; el read-back dice "para <nombre>" y, si es otro, lo corrige (REAL-12).
      else if (tipo === 'sumar' || tipo === 'reserva' || tipo === 'cambio' || tipo === 'cancelacion') ids = fichasCon(vistos);
      if (ids.length === 1) elegida = ids[0];
    }
    // (08/10) REAL-06: la ficha elegida no tiene turno en la fecha del turno a cambiar/cancelar, pero UNA sola ficha del mismo celular sí: es ese turno
    // (el paciente lo identificó por la fecha; el read-back dice "para <nombre>"). Antes devolvía turno_no_es_de_la_ficha, el modelo preguntaba
    // "¿confirma…?" y con el "sí" volvía a llamar con la misma ficha: tres vueltas iguales.
    if (!nuevo && elegida && (tipo === 'cambio' || tipo === 'cancelacion') && esISO(entrada.fecha_turno_viejo || '') && Array.isArray(vistos)) {
      const f = entrada.fecha_turno_viejo, inv = `${f.slice(0, 4)}-${f.slice(8, 10)}-${f.slice(5, 7)}`;
      const en = (fe) => vistos.filter((t) => t.fecha === fe && vigente(t));
      if (![...en(f), ...en(inv)].some((t) => Number(t.id_paciente) === Number(elegida))) {
        const otras = [...new Set(en(f).map((t) => Number(t.id_paciente)))].filter((id) => fichas.some((x) => Number(x.id) === id));
        if (otras.length === 1) elegida = otras[0];
      }
    }
    if (!nuevo && !elegida) return no('ficha_no_elegida', '[Nota interna para vos, NO la repitas al paciente] Este celular tiene varias fichas. Si el paciente YA dijo para quién es, NO mandes texto_para_el_paciente: llamá elegir_ficha con ese nombre y después gestionar_turno otra vez. Si no lo dijo, tu respuesta es texto_para_el_paciente, tal cual. Si es para alguien que no está entre las fichas, es paciente nuevo: pasá nuevo_nombre, nuevo_apellido y nuevo_dni.',
      { fichas: fichas.map((f) => f.nombre), texto_para_el_paciente: `¿Para quién es el turno: ${lista(fichas.map((f) => f.nombre), 'o')}? Si es para otra persona, me pasa nombre, apellido y DNI.` });
    const nombreFicha = (fichas.find((f) => Number(f.id) === Number(elegida)) || {}).nombre || '';
    const variasFichas = fichas.length > 1;
    if (!Array.isArray(vistos)) return no('ver_turnos_primero', 'Llamá a ver_turnos antes de proponer.');
    const delPaciente = nuevo ? [] : vistos.filter((t) => Number(t.id_paciente) === Number(elegida) && vigente(t));

    // (07/10) Un turno nuevo el MISMO DÍA que uno que ya tiene es un cambio, no un turno extra: nadie saca dos turnos de ortodoncia el mismo día.
    // Examen AGE-06: "quería un turno antes del que me toca" → eligió el 16/10 9:10 (su turno era el 16/10 10:30) → quedaba con los dos ese día.
    let fechaViejo = entrada.fecha_turno_viejo;
    if (tipo === 'reserva' && esISO(entrada.fecha) && delPaciente.some((t) => t.fecha === entrada.fecha)) { tipo = 'cambio'; fechaViejo = entrada.fecha; }

    // (07/10) "10/12" leído como 12/10: si la fecha del turno viejo no coincide con ninguno suyo pero invertida sí, es esa.
    if (fechaViejo && esISO(fechaViejo) && !delPaciente.some((t) => t.fecha === fechaViejo)) {
      const inv = `${fechaViejo.slice(0, 4)}-${fechaViejo.slice(8, 10)}-${fechaViejo.slice(5, 7)}`;
      if (delPaciente.some((t) => t.fecha === inv)) fechaViejo = inv;
    }
    let viejo = null;
    if (tipo === 'cambio' || tipo === 'cancelacion') {
      const f = fechaViejo;
      let cands = delPaciente;
      if (f) {
        if (!esISO(f)) return no('fecha_invalida', 'La fecha del turno actual debe ser YYYY-MM-DD.');
        cands = delPaciente.filter((t) => t.fecha === f);
        if (!cands.length) {
          const deOtra = vistos.some((t) => t.fecha === f && Number(t.id_paciente) !== Number(elegida) && vigente(t));
          const duenios = fichas.filter((x) => vistos.some((t) => t.fecha === f && Number(t.id_paciente) === Number(x.id) && vigente(t))).map((x) => x.nombre);
          return no(deOtra ? 'turno_no_es_de_la_ficha' : 'cita_no_vista', deOtra ? `[Nota interna para vos, NO la repitas al paciente] Ese turno figura a nombre de ${lista(duenios, 'o')}. Preguntale de quién es ese turno; cuando lo diga, llamá elegir_ficha con ese nombre y después gestionar_turno otra vez (no le pidas que confirme de nuevo).` : 'No veo un turno vigente en esa fecha para este paciente. Mostrale los turnos con ver_turnos.');
        }
      }
      if (cands.length === 0) return no('sin_turnos', 'El paciente no tiene turnos vigentes.');
      if (cands.length > 1) return conTexto('cual_turno', `¿Cuál de sus turnos: ${lista(cands.map((t) => 'el ' + corto(t.fecha, normHora(t.hora_inicio))), 'o')}?`, 'Tiene más de un turno vigente. Cuando conteste, volvé a llamar gestionar_turno con fecha_turno_viejo.', { turnos: cands.map((t) => largo(t.fecha, normHora(t.hora_inicio))) });
      viejo = cands[0];
      if (msTurno(viejo.fecha, viejo.hora_inicio) - ahora < MIN_ANTICIPACION_MS) {
        return no('menos_48h', 'El turno es en menos de 48 horas: no se cambia ni se cancela por acá. Decile que lo pasás a la clínica y llamá avisar_grupo con nivel ACCION. No menciones penalizaciones.', { cita_id: viejo.id });
      }
    }

    let slot = null;
    if (tipo !== 'cancelacion') {
      const fecha = entrada.fecha, hora = normHora(entrada.hora);
      if (!esISO(fecha) || !hora) return no('horario_invalido', 'Faltan fecha (YYYY-MM-DD) y hora (HH:MM).');
      const ofrecidos = (estado.ofertas || []).map((o) => `${o.fecha} ${normHora(o.hora)}`);
      if (!ofrecidos.includes(`${fecha} ${hora}`)) return noOfrecido();
      slot = { fecha, hora };
      // (07/10, Lucas: "que funcione como una app; si pide un turno y eligió uno, hacé eso") Pide un turno y ya tiene uno: no se pregunta "¿cambiar o sumar?".
      // Se arma la confirmación de OTRO turno "además de su turno del …": eso deja claro qué va a pasar y, si en realidad quería cambiarlo, lo dice ahí (antes la pregunta
      // extra confundía: en el examen un "Sí" a la confirmación terminó en "¿Quiere pasarlo… o mantenerlo?"). Para CAMBIAR su turno el modelo usa tipo cambio.
      if (tipo === 'reserva' && delPaciente.length > 0) tipo = 'sumar';
      if (tipo === 'sumar' && delPaciente.length === 0) return no('no_hay_turno_para_sumar', 'No tiene un turno vigente al que sumar: usá tipo reserva.');
    }

    const para = variasFichas && nombreFicha ? ` para ${nombreFicha}` : '';
    let readback;
    if (tipo === 'cambio') readback = `Le confirmo${para}: ${capital(largo(slot.fecha, slot.hora))} hs con la Dra. Raquel, reemplazando el turno del ${corto(viejo.fecha, normHora(viejo.hora_inicio))}. ¿Procedo con la reserva?`;
    else if (tipo === 'sumar') readback = `Le confirmo${para}: ${capital(largo(slot.fecha, slot.hora))} hs con la Dra. Raquel, además de su${delPaciente.length > 1 ? 's turnos' : ' turno'} ${lista(delPaciente.map((t) => 'del ' + corto(t.fecha, normHora(t.hora_inicio))), 'y')}. ¿Procedo con la reserva?`;
    else if (tipo === 'reserva' && nuevo) readback = `Le confirmo: ${capital(largo(slot.fecha, slot.hora))} hs con la Dra. Raquel, a nombre de ${nuevo.nombre} ${nuevo.apellidos} (DNI ${dniLindo(nuevo.dni)}), como paciente nuevo. ¿Procedo con la reserva?`;
    else if (tipo === 'reserva') readback = `Le confirmo${para}: ${capital(largo(slot.fecha, slot.hora))} hs con la Dra. Raquel. ¿Procedo con la reserva?`;
    else readback = `¿Procedo con la cancelación de su turno${para} del ${corto(viejo.fecha, normHora(viejo.hora_inicio))}?`;

    const propuesta = {
      id: `${estado.tel}-${ahora}`, tipo, estado: 'pendiente', creada_ms: ahora, exec_id: estado.exec_id, tel: estado.tel,
      paciente_id: nuevo ? null : elegida, slot, cita_vieja: viejo ? { id: viejo.id, fecha: viejo.fecha, hora: normHora(viejo.hora_inicio) } : null, readback_text: readback,
      ...(nuevo ? { paciente_nuevo: nuevo } : {}),
    };
    return { ok: true, propuesta, readback_text: readback, para_asiri: '[Nota interna para vos, NO la repitas al paciente] El texto para el paciente es readback_text: mandáselo tal cual, sin introducciones, y esperá su confirmación en el próximo mensaje. No digas que quedó hecho.' };
  }

  // ----------------------------------------------------------------- ejecutar: pasos puros
  // Cada paso: { fin: resultado } corta la ejecución con ese resultado; cualquier otra forma sigue.
  // El mensaje de éxito lo arma el CÓDIGO (el modelo lo pega): también el que se devuelve en modo sombra, para poder evaluar la charla completa sin escribir nada.
  const textoExito = (p) => (p.tipo === 'cambio' ? `Listo, quedó reprogramado su turno: anulé el del ${corto(p.cita_vieja.fecha, p.cita_vieja.hora)} y le reservé el ${corto(p.slot.fecha, p.slot.hora)}.`
    : p.tipo === 'cancelacion' ? `Listo, su turno del ${corto(p.cita_vieja.fecha, p.cita_vieja.hora)} quedó cancelado.`
    : p.paciente_nuevo ? `Listo, le reservé el ${corto(p.slot.fecha, p.slot.hora)} a nombre de ${p.paciente_nuevo.nombre} ${p.paciente_nuevo.apellidos}.` : `Listo, le reservé el ${corto(p.slot.fecha, p.slot.hora)}.`);
  const nuevoLedger = (p) => ({ propuesta: p && p.id, tipo: p && p.tipo, ...(p && p.origen ? { origen: p.origen } : {}), escrituras: [] });

  // 1) chequeos previos a tocar nada
  // entrada: { propuesta, exec_id_actual, enviada, modo }
  function pasoInicial(entrada, ahoraISO) {
    const p = entrada.propuesta;
    const ahora = Date.parse(ahoraISO);
    const ledger = nuevoLedger(p);
    if (!p) return { fin: { ...no('sin_propuesta', 'No hay una propuesta pendiente. Llamá a proponer_* primero.'), ledger } };
    if (p.estado !== 'pendiente') return { fin: { ...no('ya_ejecutada', 'Esa propuesta ya se ejecutó.'), ledger } };
    if (ahora - p.creada_ms > TTL_PROPUESTA_MS) return { fin: { ...no('vencida', 'La propuesta venció. Volvé a proponer.'), ledger } };
    if (p.exec_id === entrada.exec_id_actual || entrada.enviada !== true) {
      return { fin: { ...no('readback_no_visto', 'El paciente todavía no vio el texto de confirmación: mandáselo tal cual y esperá su respuesta en el próximo mensaje.'), ledger } };
    }
    // (05/11, revisión adversarial R5) El "sí" puede llegar horas después del read-back (vence a las 12 h): si el horario nuevo ya pasó (o falta menos de
    // media hora) o el turno que se cambiaba ya pasó, no se escribe nada. Antes solo se chequeaba al proponer.
    if (p.slot && esISO(p.slot.fecha) && normHora(p.slot.hora) && msTurno(p.slot.fecha, p.slot.hora) - ahora < 30 * 60 * 1000) {
      return { fin: { ...no('horario_pasado', 'El horario de la confirmación ya pasó: no se cambió nada en la agenda.'), ledger } };
    }
    if (p.cita_vieja && esISO(p.cita_vieja.fecha) && msTurno(p.cita_vieja.fecha, p.cita_vieja.hora) <= ahora) {
      return { fin: { ...no('horario_pasado', 'El turno que se iba a cambiar o cancelar ya pasó: no se tocó nada.'), ledger } };
    }
    if (entrada.modo !== 'vivo') {   // (08/10) solo escribe con modo 'vivo' EXPLÍCITO: si el modo no llega, es sombra (incidente de confirmar_turno del 06/10)
      return { fin: { ok: true, simulado: true, habria_hecho: { tipo: p.tipo, slot: p.slot, cita_vieja: p.cita_vieja, ...(p.paciente_nuevo ? { alta_paciente: p.paciente_nuevo } : {}) }, readback_text: textoExito(p), primera_consulta: p.tipo !== 'cambio' && !!p.paciente_nuevo, ledger } };
    }
    return { ok: true, propuesta: p, ledger };
  }
  // 2) consumo atómico: `consumida` = true si este fue el único que la tomó (INCR de Redis == 1); undefined/error = fallo técnico
  function pasoConsumo(estado, consumida) {
    if (consumida === undefined || consumida === null) return { fin: { ...no('error_tecnico', 'No pude verificar el estado de la propuesta; no se hizo ningún cambio.'), ledger: estado.ledger } };
    if (consumida !== true) return { fin: { ...no('ya_ejecutada', 'Esa propuesta ya se ejecutó.'), ledger: estado.ledger } };
    return { ok: true, propuesta: estado.propuesta, ledger: estado.ledger };
  }
  // 3) re-verificar la cita vieja (cambio/cancelación). resp = respuesta cruda del GET (o { error } / undefined si falló)
  function pasoCita(estado, resp) {
    const p = estado.propuesta;
    if (!p.cita_vieja) return { ok: true, propuesta: p, ledger: estado.ledger };
    if (!resp || resp.error) return { fin: { ...no('error_tecnico', 'No pude consultar la agenda; no se hizo ningún cambio.'), ledger: estado.ledger } };
    const d = resp.data || resp || {};
    const ok = d && Number(d.id) === Number(p.cita_vieja.id) && d.fecha === p.cita_vieja.fecha && normHora(d.hora_inicio) === p.cita_vieja.hora
      && Number(d.id_paciente) === Number(p.paciente_id) && vigente(d);
    if (!ok) return { fin: { ...no('cita_cambio', 'El turno cambió o ya no está vigente: no se tocó nada. Mostrale sus turnos de nuevo con ver_turnos.'), ledger: estado.ledger } };
    // (05/11, revisión P3) Un cambio que propuso la clínica conserva la duración de la cita original (la secretaria elige huecos a mano, a veces de 20 min).
    if (p.origen === 'staff' && Number(d.duracion) > 0) return { ok: true, propuesta: { ...p, duracion: Number(d.duracion) }, ledger: estado.ledger };
    return { ok: true, propuesta: p, ledger: estado.ledger };
  }
  // 3b) paciente nuevo: antes de reservar, el alta en la agenda (solo reservas con paciente_nuevo; el resto pasa de largo).
  //   - pasoBuscarDni: resp = GET /pacientes?q={"rut":{"eq":dni}}. Si ese DNI ya tiene ficha (con otro celular) y el nombre coincide, se reserva en ESA ficha
  //     (sin duplicar: el v6 tuvo fichas duplicadas por crear sin buscar). Si el DNI es de alguien con otro nombre, no se toca nada. Si la consulta falla, se sigue a crear.
  //   - pasoAlta: resp = POST /pacientes/. Primero con el DNI (campo rut, el mismo que devuelve la agenda); si la agenda lo rechaza (4xx) se reintenta UNA vez
  //     sin DNI (el cuerpo probado del v6) y se avisa a la clínica para cargarlo a mano. Error de red: no se reintenta (podría haberse creado).
  const nombreCompleto = (n) => `${n.nombre} ${n.apellidos}`;
  function pasoBuscarDni(estado, resp) {
    const p = estado.propuesta; const ledger = estado.ledger; const n = p.paciente_nuevo;
    if (!n || p.paciente_id) return { ok: true, crear: false, propuesta: p, ledger };
    const data = resp && !resp.error && Array.isArray(resp.data) ? resp.data : [];
    const conDni = data.filter((x) => x && x.id && soloDig(x.rut) === n.dni && Number(x.habilitado === undefined ? 1 : x.habilitado) === 1);
    if (!conDni.length) return { ok: true, crear: true, propuesta: p, ledger };
    const tn = tokensNombre(nombreCompleto(n));
    const mismo = conDni.filter((x) => tokensNombre(`${x.nombre} ${x.apellidos || ''}`).some((t) => tn.includes(t)));
    if (mismo.length === 1) return { ok: true, crear: false, propuesta: { ...p, paciente_id: Number(mismo[0].id), alta: 'existente' }, ledger };
    return { fin: { ...no('dni_en_otra_ficha', 'Ese DNI ya figura en la agenda y no pude confirmar que sea el mismo paciente: NO se reservó nada. Decile con sinceridad que la secretaria le termina de agendar el turno.'),
      aviso_clinica: `[ACCIÓN] Paciente nuevo por WhatsApp: ${nombreCompleto(n)} (DNI ${n.dni}) pidió el ${corto(p.slot.fecha, p.slot.hora)}, pero ese DNI ya figura en la agenda con otros datos. Asiri no reservó: revisar la ficha y agendar a mano.`, ledger } };
  }
  // (20/10, BOT-01) Quien escribe desde un número oculto de WhatsApp (@lid) llega con un identificador que NO es un celular: la ficha se da de alta
  // sin celular (antes quedaba un celular falso en la agenda) y la clínica recibe el aviso para cargarlo a mano. Celular válido = argentino (54 + 10/11 dígitos).
  const celularValido = (tel) => /^54\d{10,11}$/.test(String(tel || ''));
  const armarPaciente = (p, conDni) => ({ nombre: p.paciente_nuevo.nombre, apellidos: p.paciente_nuevo.apellidos, ...(celularValido(p.tel) ? { celular: String(p.tel) } : {}), ...(conDni ? { rut: p.paciente_nuevo.dni } : {}) });
  // Solo un rechazo explícito de la agenda (código HTTP 4xx) habilita el reintento; un error de red (que puede traer "port: 443") no.
  const es4xx = (resp) => {
    const e = resp && resp.error; if (!e) return false;
    const o = typeof e === 'object' ? e : { message: String(e) };
    const code = Number(o.statusCode || o.httpCode || o.status || (o.response && (o.response.status || o.response.statusCode)) || (/^\s*(4\d\d)\b/.exec(String(o.message || '')) || [])[1] || 0);
    return code >= 400 && code < 500;
  };
  function pasoAlta(estado, resp, conDni) {
    const p = estado.propuesta; const ledger = estado.ledger;
    ledger.escrituras.push({ tipo: 'POST paciente', body: armarPaciente(p, conDni), resp: resp || null });
    const id = resp && !resp.error && resp.data ? Number(resp.data.id) : 0;
    // Si la agenda devuelve la ficha con un rut distinto (o vacío), el DNI no quedó cargado aunque el alta saliera: se avisa para cargarlo a mano.
    const dniQuedo = id > 0 && conDni && !('rut' in resp.data && soloDig(resp.data.rut) !== p.paciente_nuevo.dni);
    if (id > 0) return { ok: true, propuesta: { ...p, paciente_id: id, alta: dniQuedo ? 'creado' : 'creado_sin_dni' }, ledger };
    if (conDni && es4xx(resp)) return { ok: true, reintentar: true, propuesta: p, ledger };
    return { fin: { ...no('no_pude_registrar', 'No pude registrar al paciente en la agenda: NO se reservó ningún turno. Decile con sinceridad que la secretaria le termina de agendar el turno.'),
      aviso_clinica: `[ACCIÓN] Paciente nuevo por WhatsApp: ${nombreCompleto(p.paciente_nuevo)} (DNI ${p.paciente_nuevo.dni}) quería el ${corto(p.slot.fecha, p.slot.hora)} y la agenda no aceptó el alta. Asiri no reservó: darlo de alta y agendar a mano.`, ledger } };
  }
  // 4) cuerpos de las escrituras
  const armarReserva = (p) => ({ id_dentista: 1, id_sucursal: 1, id_sillon: 1, id_paciente: p.paciente_id, fecha: p.slot.fecha, hora_inicio: p.slot.hora,
    duracion: p.origen === 'staff' && Number(p.duracion) > 0 ? Number(p.duracion) : 40,
    comentario: p.tipo === 'cambio' ? (p.origen === 'staff' ? `Reprogramado por Asiri a pedido de la clínica (WhatsApp), reemplaza cita #${p.cita_vieja.id}` : `Reprogramado por Asiri (WhatsApp), reemplaza cita #${p.cita_vieja.id}`) : 'Reservado por Asiri (WhatsApp)' });
  const armarAnulacion = () => ({ id_estado: 1 });
  // Lo que la clínica tiene que saber de un alta (va en el aviso FYI de la reserva).
  const notaAlta = (p) => (!p.paciente_nuevo || !p.alta ? null
    : p.alta === 'existente' ? `Paciente que escribió desde un celular nuevo: ${nombreCompleto(p.paciente_nuevo)} (DNI ${p.paciente_nuevo.dni}); se usó su ficha #${p.paciente_id}.`
    : `Paciente nuevo dado de alta: ${nombreCompleto(p.paciente_nuevo)} (DNI ${p.paciente_nuevo.dni}), ficha #${p.paciente_id}` + (p.alta === 'creado_sin_dni' ? '. La agenda no aceptó el DNI: cargarlo a mano en la ficha.' : '.')
      + (celularValido(p.tel) ? '' : ' Escribió desde un número oculto de WhatsApp: la ficha quedó SIN celular, cargarlo a mano (pedírselo por este chat).'));
  // 5) verificar la reserva. resp = respuesta cruda del POST
  function pasoReserva(estado, resp) {
    const p = estado.propuesta; const ledger = estado.ledger;
    ledger.escrituras.push({ tipo: 'POST', body: armarReserva(p), resp: resp || null });
    const nueva = resp && resp.data && Number(resp.data.id_estado) > 0 ? resp.data : null;
    const alta = notaAlta(p) ? { nota_alta: notaAlta(p) } : {};
    if (!nueva) return { fin: { ...no('reserva_rechazada', p.paciente_nuevo ? 'La agenda no aceptó el horario (puede que se haya ocupado). Contáselo y ofrecé otro horario con buscar_horarios.' : 'La agenda no aceptó el horario (puede que se haya ocupado). Su turno actual sigue vigente. Contáselo y ofrecé otro horario con buscar_horarios.'), ...alta, ledger } };
    // (16/10, plan §3.2 #1) primera_consulta: solo un paciente NUEVO dado de alta ahora (no uno que ya tenía ficha con otro celular). El pedido de
    // pago de la consulta va solo en ese caso; a un paciente en tratamiento que saca un control no se le pide.
    if (p.tipo !== 'cambio') return { fin: { ok: true, nueva_cita: nueva.id, readback_text: textoExito(p), primera_consulta: !!(p.paciente_nuevo && p.alta !== 'existente'), ...alta, ledger } };
    return { ok: true, propuesta: p, ledger, nueva_cita: nueva.id };
  }
  // 6) verificar la anulación. resp = respuesta cruda del PUT
  function pasoAnulacion(estado, resp) {
    const p = estado.propuesta; const ledger = estado.ledger;
    ledger.escrituras.push({ tipo: 'PUT', cita: p.cita_vieja.id, resp: resp || null });
    const anulada = !!(resp && resp.data && Number(resp.data.id_estado) === 1);
    if (p.tipo === 'cancelacion') {
      return { fin: anulada ? { ok: true, vieja_anulada: p.cita_vieja.id, readback_text: textoExito(p), ledger }
        : { ...no('no_pude_cancelar', 'No pude cancelar el turno: sigue vigente. Decíselo y avisá a la clínica con ACCION.'), ledger } };
    }
    if (!anulada) {
      return { fin: { ok: false, parcial: true, motivo: 'no_pude_anular', nueva_cita: estado.nueva_cita, ledger,
        para_asiri: 'Se reservó el turno nuevo pero NO pude anular el anterior. Decíselo con sinceridad y avisá a la clínica con ACCION.',
        readback_text: `Le reservé el ${corto(p.slot.fecha, p.slot.hora)} pero no pude anular el anterior; le aviso a la clínica para que lo ajuste.` } };
    }
    return { fin: { ok: true, nueva_cita: estado.nueva_cita, vieja_anulada: p.cita_vieja.id, ledger,
      readback_text: textoExito(p) } };
  }

  // Composición con E/S inyectada (tests y simulaciones). En n8n la misma secuencia la hacen los nodos.
  // io: { consumir(id)->bool, getCita(id)->resp, postCita(body)->resp, putCita(id, body)->resp, buscarDni(dni)->resp, postPaciente(body)->resp }   (cada una puede lanzar)
  async function ejecutar(entrada, io, ahoraISO) {
    const s0 = pasoInicial(entrada, ahoraISO);
    if (s0.fin) return s0.fin;
    const p = s0.propuesta;
    let consumida; try { consumida = await io.consumir(p.id); } catch (e) { consumida = undefined; }
    const s1 = pasoConsumo(s0, consumida); if (s1.fin) return s1.fin;
    let rc; try { rc = p.cita_vieja ? await io.getCita(p.cita_vieja.id) : null; } catch (e) { rc = { error: true }; }
    let s2 = pasoCita(s1, rc); if (s2.fin) return s2.fin;
    if (p.tipo === 'cancelacion') {
      let r; try { r = await io.putCita(p.cita_vieja.id, armarAnulacion()); } catch (e) { r = null; }
      return pasoAnulacion(s2, r).fin;
    }
    if (p.paciente_nuevo && !p.paciente_id) {
      let rd; try { rd = await io.buscarDni(p.paciente_nuevo.dni); } catch (e) { rd = { error: { message: 'network error' } }; }
      s2 = pasoBuscarDni(s2, rd); if (s2.fin) return s2.fin;
      if (s2.crear) {
        let ra; try { ra = await io.postPaciente(armarPaciente(s2.propuesta, true)); } catch (e) { ra = { error: { message: 'network error' } }; }
        s2 = pasoAlta(s2, ra, true); if (s2.fin) return s2.fin;
        if (s2.reintentar) {
          try { ra = await io.postPaciente(armarPaciente(s2.propuesta, false)); } catch (e) { ra = { error: { message: 'network error' } }; }
          s2 = pasoAlta(s2, ra, false); if (s2.fin) return s2.fin;
        }
      }
    }
    let r1; try { r1 = await io.postCita(armarReserva(s2.propuesta)); } catch (e) { r1 = null; }
    const s3 = pasoReserva(s2, r1); if (s3.fin) return s3.fin;
    let r2; try { r2 = await io.putCita(p.cita_vieja.id, armarAnulacion()); } catch (e) { r2 = null; }
    return pasoAnulacion(s3, r2).fin;
  }

  // ----------------------------------------------------------------- decidir (herramienta única gestionar_turno, 06/10; 08/10 orquestador)
  // El mismo pedido se llama DOS veces. Primera vez: el código valida y devuelve el read-back (no escribe).
  // Segunda vez, cuando el paciente contestó: el agente de TURNOS (la IA, no una regex) decide si el MENSAJE ACTUAL acepta la confirmación pendiente y lo
  // dice con `confirma`. El código SOLO verifica datos: que haya una confirmación guardada pendiente, que ese read-back sea lo último que le dijo Asiri
  // (el paciente lo vio), que no haya vencido (30 min) y, al ejecutar, el candado INCR. (08/10) Se borraron el reconocedor de afirmaciones y el atajo del sí directo: una regex no decide un "sí".
  const sinTildes = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const normT = (x) => sinTildes(x).replace(/[^a-z0-9:/? ]+/g, ' ').replace(/\s+/g, ' ').trim();
  function hashTexto(s) { let h = 5381; const t = normT(s); for (let i = 0; i < t.length; i++) h = ((h * 33) ^ t.charCodeAt(i)) >>> 0; return h.toString(36); }
  // (05/11, incidente 331596) `confirma` se pide como la palabra "si": con la descripción "true…" el modelo mandó un booleano, el esquema (string) lo rechazó y
  // se cayó el agente entero. Se aceptan las dos formas por si acaso (true booleano llega igual si algún día el esquema cambia).
  const esVerdadero = (v) => v === true || ['true', 'si'].includes((sinTildes(v).match(/[a-z]+/) || [''])[0]);
  // ¿Hay una confirmación guardada que el paciente vio (es lo último que le dijo Asiri) y sigue vigente? Es estado, no lectura del texto del paciente.
  function pendienteVista(pg, ultimoAsiri, ahoraISO) {
    return !!(pg && pg.estado === 'pendiente' && pg.readback_text && ultimoAsiri && normT(ultimoAsiri).includes(normT(pg.readback_text))
      && Date.parse(ahoraISO) - Number(pg.creada_ms || 0) <= TTL_PROPUESTA_MS);
  }
  // (08/10, I3 de la crítica) El DNI del paciente nuevo: el modelo lo copia y el código verifica que esos dígitos estén en lo que escribió el paciente
  // (sus mensajes de las últimas 12 h, los mismos que ve el contexto). Se comparan SOLO dígitos de los dos lados: "35.123.456" y "35 123 456" valen.
  // Es validación de un dato (anti-alucinación), no juicio de intención; si no aparece, se le pide el DNI con un texto fijo. Nunca se pisa el DNI del modelo.
  function dniEnMensajes(dni, textos) {
    const d = soloDig(dni);
    if (!d) return true;
    return (Array.isArray(textos) ? textos : [textos]).some((t) => soloDig(t).includes(d));
  }
  // entrada: lo que decide el modelo { tipo, fecha, hora, fecha_turno_viejo, nuevo_*, confirma }; estado: el de proponer + { ultimo_asiri, propuesta_guardada, textos_paciente? }
  function decidir(entrada, estado, ahoraISO) {
    // (05/11) aceptar_propuesta_clinica: el modelo no manda datos; todo sale del mensaje del staff y de la agenda (decidirPropuestaStaff).
    if (entrada && entrada.accion === 'propuesta_staff') return decidirPropuestaStaff(entrada, estado, ahoraISO);
    const pg = estado.propuesta_guardada;
    // El agente dijo que el paciente aceptó: se ejecuta la confirmación GUARDADA (la que vio el paciente), no lo que mande el modelo en esta llamada.
    // (15/10, prueba en vivo) La guardada tiene que haberse ENVIADO en un mensaje ANTERIOR: si el agente la armó en esta misma ejecución y en la misma
    // llamada dice "confirma", el texto puede coincidir con el último mensaje de Asiri (misma pregunta de antes) y se ejecutaba sin que el paciente
    // la viera de nuevo. Sin enviada === true, o creada en esta ejecución, no hay "sí" posible.
    if (esVerdadero(entrada.confirma) && pg && pg.enviada === true && String(pg.exec_id) !== String(estado.exec_id) && pendienteVista(pg, estado.ultimo_asiri, ahoraISO)) {
      // (15/10) El candado de consumo es por PROPUESTA (texto + cuándo se creó): con solo el texto, una segunda propuesta idéntica (cancelar un turno
      // vuelto a dar en el mismo horario) quedaba bloqueada como "ya ejecutada". Dos "sí" a la MISMA propuesta siguen chocando en el mismo candado.
      return { etapa: 'ejecutar', propuesta: { ...pg, id: `h-${estado.tel}-${hashTexto(pg.readback_text)}-${Number(pg.creada_ms) || 0}`, exec_id: 'confirmada', enviada: true, confirmada_por: 'agente_turnos' } };
    }
    if (entrada.nuevo_dni && Array.isArray(estado.textos_paciente) && !dniEnMensajes(entrada.nuevo_dni, estado.textos_paciente)) {
      return { etapa: 'error', resultado: { etapa: 'error', ...conTexto('dni_no_escrito', 'Para registrarlo me falta el DNI del paciente.', 'El DNI no aparece en lo que escribió el paciente: no lo inventes ni lo corrijas. Pediselo.') } };
    }
    const r = proponer(entrada, estado, ahoraISO);
    if (!r.ok) {
      const { texto_repregunta, ...resto } = r;
      // Si Asiri ya le hizo ESA pregunta en su último mensaje (el paciente contestó sin elegir), se pregunta con otras palabras: nunca el mismo texto dos veces.
      if (texto_repregunta && resto.texto_para_el_paciente && estado.ultimo_asiri && normT(estado.ultimo_asiri).includes(normT(resto.texto_para_el_paciente))) resto.texto_para_el_paciente = texto_repregunta;
      return { etapa: 'error', resultado: { etapa: 'error', ...resto } };
    }
    // Sin "confirma" (o sin confirmación vigente que el paciente haya visto) NUNCA se escribe: se muestra el read-back.
    return { etapa: 'confirmacion', propuesta: r.propuesta, resultado: { etapa: 'confirmacion', ok: true, texto_para_el_paciente: r.readback_text,
      para_asiri: '[Nota interna para vos, NO la repitas al paciente] El sistema le manda este texto. Cuando el paciente acepte en su PRÓXIMO mensaje, llamá gestionar_turno con confirma="si": recién ahí se escribe en la agenda.' } };
  }

  // ----------------------------------------------------------------- propuesta de la CLÍNICA (05/11, incidente José 331590; casos 324904 Hernán, Santiago T., 16/09, 03/10)
  // La secretaria le escribe a mano al paciente proponiendo MOVER su turno ("¿Podríamos reagendar su turno para las 8:40 hs de ese mismo día?") y el paciente
  // contesta "dale". Antes no había camino: decidir solo ejecuta confirmaciones que armó Asiri y proponer exige horarios de buscar_horarios → tipo_invalido,
  // no_ofrecido y el agente se caía. Ahora (herramienta aceptar_propuesta_clinica):
  //   - el MODELO copia del mensaje de la clínica la fecha y la hora NUEVAS, la fecha del turno que se mueve y para quién (entiende "8 y 40", "6 de la tarde",
  //     "este jueves"); el CÓDIGO verifica cada dato contra el mensaje CRUDO del staff (como el DNI: que esté escrito ahí) y contra la agenda. Ante la duda, deriva.
  //   - A) si la agenda YA tiene ese turno para esa ficha (la secretaria lo movió antes de preguntar, como con José) y no queda otro turno suyo en esas fechas
  //     (posible duplicado): no escribe nada, contesta con texto del código + FYI con lo que se le dijo;
  //   - B) si no: arma la propuesta de CAMBIO y el read-back de siempre, con la fecha y hora PRIMERO. Recién con el "sí" a ESE read-back se escribe por el camino
  //     de siempre (candado, re-verificación de la cita vieja y del horario, reservar → anular → verificar). Regla dura del read-back intacta.
  // El horario NO sale de buscar_horarios: lo propuso la clínica. La regla de 48 h (política para cambios que pide el PACIENTE) no se aplica a esta ruta.
  // (05/11, revisión adversarial) Primera versión: el CÓDIGO leía fecha y hora del texto libre; fallaba con "8 y 40", "6 de la tarde", "al 19" y adivinaba el turno
  // viejo. Ahora lee el modelo y el código solo verifica.
  const VENTANA_STAFF_MS = 48 * 60 * 60 * 1000;
  const MESES_N = { enero: 1, febrero: 2, marzo: 3, abril: 4, mayo: 5, junio: 6, julio: 7, agosto: 8, septiembre: 9, setiembre: 9, octubre: 10, noviembre: 11, diciembre: 12 };
  const DIA_NOMBRE = ['domingo', 'lunes', 'martes', 'miercoles', 'jueves', 'viernes', 'sabado'];
  const isoJujuy = (ms) => new Date(ms - 3 * 3600 * 1000).toISOString().slice(0, 10);
  const diasEntre = (a, b) => Math.round((fechaDe(b) - fechaDe(a)) / 86400000);
  // ¿El mensaje de la clínica propone MOVER un turno? (texto de la clínica, nunca del paciente). Verbo de cambio + alguna hora escrita; una señal de turno NUEVO
  // ("podemos agendar el próximo turno de Delfi", caso real 30/10) gana: eso lo agenda la secretaria. Lo usa el cerebro para mostrar la PROPUESTA DE LA CLÍNICA.
  const VERBO_CAMBIO = /\b(re ?agend\w*|re ?program\w*|cambi\w*|adelant\w*|atras\w*|posterg\w*|pasar\w*|pasamos|pasemos|mover\w*|movemos|corr(?:er\w*|emos))\b/;
  const TURNO_NUEVO = /\b(agend\w*|proximo turno|nuevo turno|otro turno|turno nuevo|sacar\w* (?:un )?turno)\b/;
  const HAY_HORA = /(?<![\d\/])\d{1,2}\s*[:.,h]\s*\d{2}(?![\d\/])|\ba las \d{1,2}\b|(?<![\d\/])\d{1,2}\s*(?:hs|hrs|horas)\b/;
  // (05/11, revisión con el modelo real) además tiene que hablar de un TURNO / horario / cita: "mañana a las 10:00 la Dra. puede cambiarle el arco a Santi" o
  // "¿puede pasar a las 10 a retirar los estudios?" no son mover su turno (el modelo los aceptaba 3/3 y el read-back anulaba su control).
  const DE_TURNO = /\b(turnos?|horarios?|citas?|control(?:es)?)\b/;   // "el control de Delfi" = su turno
  function esPropuestaDeCambio(texto) { const n = sinTildes(texto); return VERBO_CAMBIO.test(n) && !TURNO_NUEVO.test(n) && HAY_HORA.test(n) && DE_TURNO.test(n); }
  // ¿Esa hora (HH:MM, 24 h) está ESCRITA en el mensaje de la clínica? "8:40", "08.40", "8 y 40", "8 40", "8,40"; "9 y media"; "a las 9", "17 hs"; "6 de la tarde".
  function horaEnTexto(hora, texto) {
    const hh = normHora(hora); if (!hh) return false;
    const h = Number(hh.slice(0, 2)), m = Number(hh.slice(3)); const n = ' ' + sinTildes(texto).replace(/\s+/g, ' ') + ' ';
    const formas = [h]; if (h > 12 && /\b(tarde|noche)\b/.test(n)) formas.push(h - 12);
    const mm = String(m).padStart(2, '0');
    return formas.some((H) => {
      const hR = '0?' + H;
      const pruebas = m > 0
        ? [new RegExp('(?<![\\d\\/])' + hR + '\\s*(?:[:.,h]|\\s+y\\s+|\\s)\\s*' + mm + '(?![\\d\\/])')]
          .concat(m === 30 ? [new RegExp('(?<![\\d\\/])' + hR + '\\s+y\\s+media\\b')] : []).concat(m === 15 ? [new RegExp('(?<![\\d\\/])' + hR + '\\s+y\\s+cuarto\\b')] : [])
        : [new RegExp('(?<![\\d\\/.:,])' + hR + '\\s*(?:hs|hrs|horas|h)\\b'), new RegExp('\\ba las ' + hR + '(?!\\d|\\s*[:.,]\\s*\\d|\\s+y\\s)'), new RegExp('(?<![\\d\\/])' + hR + '\\s*[:.]\\s*00(?!\\d)')];
      return pruebas.some((re) => re.test(n));
    });
  }
  // ¿Esa fecha está respaldada por lo que ESCRIBIÓ la clínica? → 'ok' | 'inconsistente' (día de la semana que no coincide: "Lunes 19 de Noviembre") | false.
  // Respaldo: el número del día (con su mes si lo escribió), el día de la semana dentro de las 2 semanas del mensaje, hoy / mañana / pasado mañana (contra la
  // fecha del MENSAJE DEL STAFF, no de hoy) o "ese mismo día" si es el día del turno que se mueve.
  function fechaEnTexto(fecha, texto, msStaff, fechaViejo) {
    if (!esISO(fecha)) return false;
    const base = isoJujuy(Number(msStaff) || Date.now());
    if (fecha < base || diasEntre(base, fecha) > 120) return false;
    const n = ' ' + sinTildes(texto).replace(/\s+/g, ' ') + ' ';
    const dia = Number(fecha.slice(8)), mes = Number(fecha.slice(5, 7)), nombre = DIA_NOMBRE[fechaDe(fecha).getUTCDay()];
    let m; const reDia = /\b(lunes|martes|miercoles|jueves|viernes|sabado|domingo)[\s,]*(?:el\s+|dia\s+)?(\d{1,2})\b/g;
    while ((m = reDia.exec(n))) if (Number(m[2]) === dia && m[1] !== nombre) return 'inconsistente';
    const reNum = new RegExp('(?<![\\d:.,\\/])0?' + dia + '(?![\\d])(\\s*(?:de\\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)|\\/\\s*(\\d{1,2})))?', 'g');
    while ((m = reNum.exec(n))) {
      const antes = n.slice(Math.max(0, m.index - 7), m.index), despues = n.slice(m.index + m[0].length, m.index + m[0].length + 6);
      if (/las\s*$/.test(antes) || /^\s*(?:hs|hrs|horas|h\b|[:.,]\s*\d|y\s)/.test(despues)) continue;   // es una hora, no un día
      const mesEscrito = m[2] ? MESES_N[m[2]] : m[3] ? Number(m[3]) : null;
      if (mesEscrito === null || mesEscrito === mes) return 'ok';
    }
    const d = diasEntre(base, fecha);
    if (new RegExp('\\b' + nombre + '\\b').test(n) && d >= 0 && d <= 13) return 'ok';
    if (d === 0 && /\bhoy\b/.test(n)) return 'ok';
    if (d === 2 && /\bpasado manana\b/.test(n)) return 'ok';
    if (d === 1 && /(?<!(?:\bla|\buna|\besta|\bpor la|\bde la)\s)\bmanana\b/.test(n) && !/\bpasado manana\b/.test(n)) return 'ok';
    if (fechaViejo && fecha === fechaViejo && /\b(mismo dia|ese dia)\b/.test(n)) return 'ok';
    return false;
  }
  // (05/11, revisión B2) Horas distintas escritas en el mensaje (en minutos, 12 h: "17:00" y "5 de la tarde" son la misma). Si hay más de una, el mensaje
  // nombra el horario VIEJO y el NUEVO: el código no confía en cuál copió el modelo como nuevo.
  function horasEscritas(texto) {
    const n = ' ' + sinTildes(texto).replace(/\s+/g, ' ') + ' '; const out = new Set(); let m;
    const add = (h, mi) => { h = Number(h); mi = Number(mi); if (h >= 0 && h <= 23 && mi >= 0 && mi <= 59) out.add((h % 12) * 60 + mi); };
    const re1 = /(?<![\d\/])(\d{1,2})\s*(?:[:.,h]|\s+y\s+)\s*(\d{2})(?![\d\/])/g; while ((m = re1.exec(n))) add(m[1], m[2]);
    const re2 = /(?<![\d\/])(\d{1,2})\s+y\s+media\b/g; while ((m = re2.exec(n))) add(m[1], 30);
    const re3 = /\ba las (\d{1,2})(?!\d|\s*[:.,]\s*\d|\s+y\s)/g; while ((m = re3.exec(n))) add(m[1], 0);
    const re4 = /(?<![\d\/.:,])(\d{1,2})\s*(?:hs|hrs|horas)\b/g; while ((m = re4.exec(n))) add(m[1], 0);
    return out;
  }
  const minutos12 = (hora) => { const h = normHora(hora); return h ? (Number(h.slice(0, 2)) % 12) * 60 + Number(h.slice(3)) : -1; };
  // ¿Qué números de día (1-31) escribió la clínica? (para saber si nombra otro día además del que copió el modelo)
  function diasEscritos(texto) {
    const n = ' ' + sinTildes(texto).replace(/\s+/g, ' ') + ' '; const out = new Set(); let m;
    const re = /(?<![\d:.,\/])(\d{1,2})(?![\d])/g;
    while ((m = re.exec(n))) {
      const antes = n.slice(Math.max(0, m.index - 7), m.index), despues = n.slice(m.index + m[0].length, m.index + m[0].length + 6);
      if (/las\s*$/.test(antes) || /^\s*(?:hs|hrs|horas|h\b|[:.,]\s*\d|y\s)/.test(despues)) continue;
      const d = Number(m[1]); if (d >= 1 && d <= 31) out.add(d);
    }
    return out;
  }
  const tokensDe = (s) => sinTil(s).replace(/[^a-z ]/g, ' ').split(/\s+/).filter((t) => t.length >= 3);
  // ¿Ese nombre (o su forma corta: "Delfi" por Delfina, "Joa" no: menos de 4 letras) está escrito en el texto?
  const nombreEnTexto = (nombre, texto) => { const tn = tokensDe(texto); return tokensDe(nombre).some((p) => tn.some((t) => t === p || (t.length >= 4 && p.startsWith(t)) || (p.length >= 4 && t.startsWith(p)))); };
  const lim200 = (s) => { const t = String(s || '').replace(/\s+/g, ' ').trim(); return t.length > 200 ? t.slice(0, 199) + '…' : t; };

  // entrada: { fecha, hora, fecha_turno_viejo, para } (lo copió el modelo del mensaje de la clínica); estado: { tel, exec_id, ficha, turnos_vistos, propuesta_staff: { texto, ms } }
  function decidirPropuestaStaff(entrada, estado, ahoraISO) {
    const ahora = Date.parse(ahoraISO);
    const ps = estado.propuesta_staff;
    const e = entrada || {};
    const DERIVA_NOTA = '[Nota interna para vos, NO la repitas al paciente] No se tocó la agenda: el sistema le pasa la respuesta a la secretaria con el motivo. Respondé [LISTO].';
    const derivar = (motivo, detalle) => ({ etapa: 'error', resultado: { etapa: 'error', ...no(motivo, DERIVA_NOTA), derivar_staff: detalle } });
    if (!ps || !String(ps.texto || '').trim()) {
      // (05/11, revisión P1) si lo último es un read-back que armó Asiri (también uno de una propuesta de la clínica), el "sí" va por gestionar_turno, no acá.
      return { etapa: 'error', resultado: { etapa: 'error', ...no('sin_propuesta_staff', '[Nota interna para vos, NO la repitas al paciente] No hay una propuesta de la clínica sin responder. Si hay CONFIRMACIÓN PENDIENTE y el paciente la acepta, gestionar_turno con confirma="si".') } };
    }
    const msStaff = Number(ps.ms);
    if (!(msStaff > 0) || ahora - msStaff > VENTANA_STAFF_MS) return derivar('staff_vencida', 'la propuesta tiene más de 48 h');
    if (!esPropuestaDeCambio(ps.texto)) return derivar('staff_no_es_cambio', 'el mensaje no es mover un turno con día y hora');
    const fecha = String(e.fecha || '').trim(), hora = normHora(e.hora), fViejo = String(e.fecha_turno_viejo || '').trim();
    if (!esISO(fecha) || !hora) return derivar('staff_sin_fecha_hora', 'no pude leer la fecha y hora nuevas');
    const hMin = Number(hora.slice(0, 2)) * 60 + Number(hora.slice(3));
    if (hMin < 7 * 60 || hMin > 21 * 60) return derivar('staff_hora_rara', 'hora ' + hora + ' fuera del horario de la clínica');
    if (!horaEnTexto(hora, ps.texto)) return derivar('staff_hora_no_escrita', 'la hora ' + hora + ' no figura en el mensaje de la clínica');
    const fr = fechaEnTexto(fecha, ps.texto, msStaff, fViejo);
    if (fr === 'inconsistente') return derivar('staff_fecha_inconsistente', 'la fecha no coincide con el día de la semana');
    if (fr !== 'ok') return derivar('staff_fecha_no_escrita', 'el ' + corto(fecha, hora) + ' no figura en el mensaje');
    const vistos = estado.turnos_vistos;
    if (!Array.isArray(vistos)) return derivar('staff_sin_agenda', 'no pude consultar la agenda');
    const fichas = ((estado.ficha || {}).fichas) || [];
    if (!fichas.length) return derivar('staff_sin_ficha', 'no hay ficha con este celular');
    // Para quién: con una ficha, esa. Con varias, la que NOMBRA el mensaje de la clínica (o el modelo, si ese nombre está escrito ahí); si no, no se adivina.
    let ficha = null;
    if (fichas.length === 1) ficha = fichas[0];
    else {
      const porPara = e.para && nombreEnTexto(e.para, ps.texto) ? fichas.filter((f) => nombreEnTexto(e.para, f.nombre)) : [];
      const nombradas = fichas.filter((f) => nombreEnTexto(f.nombre, ps.texto));
      // (revisión B3) sin nombre, la fecha del turno viejo ESCRITA en el mensaje identifica la ficha si ese día hay un solo turno vigente de toda la familia.
      const porFechaVieja = fViejo && Array.isArray(estado.turnos_vistos) && fechaEnTexto(fViejo, ps.texto, msStaff, fViejo) === 'ok'
        ? [...new Set(estado.turnos_vistos.filter(vigente).filter((t) => t.fecha === fViejo).map((t) => Number(t.id_paciente)))].map((id) => fichas.find((f) => Number(f.id) === id)).filter(Boolean) : [];
      if (porPara.length === 1) ficha = porPara[0];
      else if (nombradas.length === 1) ficha = nombradas[0];
      else if (!nombradas.length && !e.para && porFechaVieja.length === 1 && estado.turnos_vistos.filter(vigente).filter((t) => t.fecha === fViejo).length === 1) ficha = porFechaVieja[0];
      else return derivar('staff_para_quien', 'varias fichas y el mensaje no dice de quién es el turno');
    }
    const F = Number(ficha.id);
    const nombre = fichas.length > 1 ? (ficha.nombre || '') : '';
    const suyos = vistos.filter(vigente).filter((t) => Number(t.id_paciente) === F && msTurno(t.fecha, t.hora_inicio) > ahora);
    // A) La agenda ya está así. Si además queda OTRO turno suyo ese día o el día del turno que se movía, puede ser un duplicado: no se afirma nada.
    // (revisión B2) el mensaje nombra más de un horario (el viejo y el nuevo): solo se acepta si la hora copiada NO es la de un turno vigente suyo (eso sería
    // copiar el viejo); y nunca se afirma "ya está en la agenda" (el turno que coincide puede ser justamente el viejo).
    const variasHoras = horasEscritas(ps.texto).size > 1;
    if (variasHoras && suyos.some((t) => minutos12(t.hora_inicio) === minutos12(hora))) return derivar('staff_hora_ambigua', 'el mensaje nombra el horario viejo y el nuevo y no sé cuál es cuál');
    // (revisión B2) si la fecha copiada es la del turno que se mueve y el mensaje nombra OTRO día, sin decir "ese mismo día": puede haber copiado la fecha vieja.
    if (fViejo && fecha === fViejo && !/\b(mismo dia|ese dia)\b/.test(sinTildes(ps.texto)) && [...diasEscritos(ps.texto)].some((d) => d !== Number(fecha.slice(8)))) {
      return derivar('staff_fecha_ambigua', 'el mensaje nombra dos días y no sé cuál es el nuevo');
    }
    const ya = suyos.find((t) => t.fecha === fecha && normHora(t.hora_inicio) === hora);
    if (ya) {
      const otros = suyos.filter((t) => t.id !== ya.id && (t.fecha === fecha || (fViejo && t.fecha === fViejo)));
      if (otros.length) return derivar('staff_posible_duplicado', 'figura el ' + corto(fecha, hora) + ' y también el ' + corto(otros[0].fecha, normHora(otros[0].hora_inicio)) + ' (¿duplicado?)');
      const quien = nombre ? 'el turno de ' + nombre : 'su turno';
      return { etapa: 'ya_en_agenda', resultado: { etapa: 'ya_en_agenda', ok: true, cita_id: ya.id,
        texto_para_el_paciente: 'Perfecto, ' + quien + ' queda el ' + corto(fecha, hora) + ' con la Dra. Raquel.',
        aviso: '[FYI] ' + (nombre || 'El paciente') + ' aceptó la propuesta de la clínica («' + lim200(ps.texto) + '»). El turno ya figuraba así en la agenda y Asiri le confirmó: ' + corto(fecha, hora) + '.',
        para_asiri: NOTA_PEGAR + 'La agenda ya tiene ese turno: no hay nada que cambiar.' } };
    }
    if (msTurno(fecha, hora) - ahora < 60 * 60 * 1000) return derivar('staff_horario_pasado', 'el horario propuesto ya pasó');
    // B) El turno que se mueve: el ÚNICO turno vigente de esa ficha, o (si tiene varios) el de la fecha que copió el modelo, siempre que esa fecha esté escrita.
    let viejo = null;
    if (!suyos.length) return derivar('staff_sin_turno', 'no tiene un turno vigente para mover');
    if (suyos.length === 1 && (!fViejo || fViejo === suyos[0].fecha)) viejo = suyos[0];
    else {
      const c = suyos.filter((t) => t.fecha === fViejo);
      if (c.length !== 1 || fechaEnTexto(fViejo, ps.texto, msStaff, fViejo) !== 'ok') return derivar('staff_turno_ambiguo', 'no sé cuál de sus turnos mover');
      viejo = c[0];
    }
    const vh = normHora(viejo.hora_inicio);
    const para = nombre ? ' para ' + nombre : '';
    // (05/11, revisión) La fecha y la hora van PRIMERO: "Le confirmo el cambio que le propuso la clínica…" invitaba a decir "sí" sin leer el horario.
    const readback = 'Le confirmo' + para + ': ' + capital(largo(fecha, hora)) + ' hs con la Dra. Raquel, en lugar de su turno del ' + corto(viejo.fecha, vh) + ' (el cambio que le propuso la clínica). ¿Procedo con el cambio?';
    const propuesta = { id: 's-' + estado.tel + '-' + hashTexto(ps.texto) + '-' + msStaff, tipo: 'cambio', estado: 'pendiente', creada_ms: ahora, exec_id: estado.exec_id, tel: estado.tel,
      paciente_id: F, slot: { fecha, hora }, cita_vieja: { id: viejo.id, fecha: viejo.fecha, hora: vh }, readback_text: readback, origen: 'staff' };
    // (revisión B1) en 8 de 18 corridas el agente seguía llamando herramientas en el mismo turno (gestionar_turno, buscar_horarios): se le dice que termine.
    return { etapa: 'confirmacion', propuesta, resultado: { etapa: 'confirmacion', ok: true, origen: 'staff', texto_para_el_paciente: readback,
      para_asiri: '[Nota interna para vos, NO la repitas al paciente] El sistema le manda este texto. Respondé [LISTO] YA: no llames ninguna otra herramienta. Cuando el paciente acepte en su PRÓXIMO mensaje, llamá gestionar_turno con confirma="si": recién ahí se escribe en la agenda.' } };
  }

  return { proponer, decidir, decidirPropuestaStaff, esPropuestaDeCambio, horaEnTexto, fechaEnTexto, pendienteVista, dniEnMensajes, hashTexto, ejecutar, pasoInicial, pasoConsumo, pasoCita, pasoBuscarDni, pasoAlta, pasoReserva, pasoAnulacion, armarPaciente, armarReserva, armarAnulacion, normHora, vigente, TTL_PROPUESTA_MS, MIN_ANTICIPACION_MS };
})();
if (typeof module !== 'undefined') module.exports = AgendaCore;
