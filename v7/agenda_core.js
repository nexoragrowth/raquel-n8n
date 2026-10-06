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
  const TTL_PROPUESTA_MS = 30 * 60 * 1000;
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

  // ----------------------------------------------------------------- proponer
  // entrada: { tipo: 'cambio'|'reserva'|'sumar'|'cancelacion', fecha, hora, fecha_turno_viejo }   (lo unico que aporta el modelo)
  // estado : { ficha:{fichas:[{id,nombre}], elegida}, turnos_vistos:[...], ofertas:[{fecha,hora}], exec_id, tel }   (lo pone el codigo)
  function proponer(entrada, estado, ahoraISO) {
    const ahora = Date.parse(ahoraISO);
    const tipo = String(entrada.tipo || '');
    if (!['cambio', 'reserva', 'sumar', 'cancelacion'].includes(tipo)) return no('tipo_invalido', 'Tipo de propuesta inválido.');
    const ficha = estado.ficha || { fichas: [], elegida: null };
    const fichas = ficha.fichas || [];
    if (!fichas.length) return no('sin_ficha', 'No hay ficha de paciente para este celular: pasalo a la clínica con avisar_grupo.');
    let elegida = ficha.elegida;
    if (!elegida && fichas.length === 1) elegida = fichas[0].id;
    if (!elegida) return no('ficha_no_elegida', 'Este celular tiene varias fichas. Preguntá para quién es el turno (nombre o DNI) y llamá a elegir_ficha antes.', { fichas: fichas.map((f) => f.nombre) });
    const nombreFicha = (fichas.find((f) => f.id === elegida) || {}).nombre || '';
    const variasFichas = fichas.length > 1;
    const vistos = estado.turnos_vistos;
    if (!Array.isArray(vistos)) return no('ver_turnos_primero', 'Llamá a ver_turnos antes de proponer.');
    const delPaciente = vistos.filter((t) => Number(t.id_paciente) === Number(elegida) && vigente(t));

    let viejo = null;
    if (tipo === 'cambio' || tipo === 'cancelacion') {
      const f = entrada.fecha_turno_viejo;
      let cands = delPaciente;
      if (f) {
        if (!esISO(f)) return no('fecha_invalida', 'La fecha del turno actual debe ser YYYY-MM-DD.');
        cands = delPaciente.filter((t) => t.fecha === f);
        if (!cands.length) {
          const deOtra = vistos.some((t) => t.fecha === f && Number(t.id_paciente) !== Number(elegida) && vigente(t));
          return no(deOtra ? 'turno_no_es_de_la_ficha' : 'cita_no_vista', deOtra ? 'Ese turno es de otra ficha del mismo celular: confirmá para quién es.' : 'No veo un turno vigente en esa fecha para este paciente. Mostrale los turnos con ver_turnos.');
        }
      }
      if (cands.length === 0) return no('sin_turnos', 'El paciente no tiene turnos vigentes.');
      if (cands.length > 1) return no('cual_turno', 'Tiene más de un turno vigente: preguntale cuál.', { turnos: cands.map((t) => largo(t.fecha, normHora(t.hora_inicio))) });
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
      if (!ofrecidos.includes(`${fecha} ${hora}`)) return no('no_ofrecido', 'Ese horario no se le ofreció al paciente. Llamá a buscar_horarios y ofrecé lo que devuelva.');
      slot = { fecha, hora };
      if (tipo === 'reserva' && delPaciente.length > 0) return no('tiene_turno_vigente', 'El paciente ya tiene un turno vigente. Si quiere cambiarlo usá proponer_cambio; si quiere SUMAR otro, preguntale y usá tipo sumar.', { turnos: delPaciente.map((t) => largo(t.fecha, normHora(t.hora_inicio))) });
      if (tipo === 'sumar' && delPaciente.length === 0) return no('no_hay_turno_para_sumar', 'No tiene un turno vigente al que sumar: usá tipo reserva.');
    }

    const para = variasFichas && nombreFicha ? ` para ${nombreFicha}` : '';
    let readback;
    if (tipo === 'cambio') readback = `Le confirmo${para}: ${capital(largo(slot.fecha, slot.hora))} hs con la Dra. Raquel, reemplazando el turno del ${corto(viejo.fecha, normHora(viejo.hora_inicio))}. ¿Procedo con la reserva?`;
    else if (tipo === 'sumar') readback = `Le confirmo${para}: ${capital(largo(slot.fecha, slot.hora))} hs con la Dra. Raquel, además de su turno del ${corto(delPaciente[0].fecha, normHora(delPaciente[0].hora_inicio))}. ¿Procedo con la reserva?`;
    else if (tipo === 'reserva') readback = `Le confirmo${para}: ${capital(largo(slot.fecha, slot.hora))} hs con la Dra. Raquel. ¿Procedo con la reserva?`;
    else readback = `¿Le confirmo que desea cancelar el turno${para} del ${corto(viejo.fecha, normHora(viejo.hora_inicio))}?`;

    const propuesta = {
      id: `${estado.tel}-${ahora}`, tipo, estado: 'pendiente', creada_ms: ahora, exec_id: estado.exec_id, tel: estado.tel,
      paciente_id: elegida, slot, cita_vieja: viejo ? { id: viejo.id, fecha: viejo.fecha, hora: normHora(viejo.hora_inicio) } : null, readback_text: readback,
    };
    return { ok: true, propuesta, readback_text: readback, para_asiri: '[Nota interna para vos, NO la repitas al paciente] El texto para el paciente es readback_text: mandáselo tal cual, sin introducciones, y esperá su confirmación en el próximo mensaje. No digas que quedó hecho.' };
  }

  // ----------------------------------------------------------------- ejecutar: pasos puros
  // Cada paso: { fin: resultado } corta la ejecución con ese resultado; cualquier otra forma sigue.
  // El mensaje de éxito lo arma el CÓDIGO (el modelo lo pega): también el que se devuelve en modo sombra, para poder evaluar la charla completa sin escribir nada.
  const textoExito = (p) => (p.tipo === 'cambio' ? `Listo, quedó reprogramado su turno: anulé el del ${corto(p.cita_vieja.fecha, p.cita_vieja.hora)} y le reservé el ${corto(p.slot.fecha, p.slot.hora)}.`
    : p.tipo === 'cancelacion' ? `Listo, su turno del ${corto(p.cita_vieja.fecha, p.cita_vieja.hora)} quedó cancelado.` : `Listo, le reservé el ${corto(p.slot.fecha, p.slot.hora)}.`);
  const nuevoLedger = (p) => ({ propuesta: p && p.id, tipo: p && p.tipo, escrituras: [] });

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
    if (entrada.modo === 'sombra') {
      return { fin: { ok: true, simulado: true, habria_hecho: { tipo: p.tipo, slot: p.slot, cita_vieja: p.cita_vieja }, readback_text: textoExito(p), ledger } };
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
    return { ok: true, propuesta: p, ledger: estado.ledger };
  }
  // 4) cuerpos de las escrituras
  const armarReserva = (p) => ({ id_dentista: 1, id_sucursal: 1, id_sillon: 1, id_paciente: p.paciente_id, fecha: p.slot.fecha, hora_inicio: p.slot.hora, duracion: 40,
    comentario: p.tipo === 'cambio' ? `Reprogramado por Asiri (WhatsApp), reemplaza cita #${p.cita_vieja.id}` : 'Reservado por Asiri (WhatsApp)' });
  const armarAnulacion = () => ({ id_estado: 1 });
  // 5) verificar la reserva. resp = respuesta cruda del POST
  function pasoReserva(estado, resp) {
    const p = estado.propuesta; const ledger = estado.ledger;
    ledger.escrituras.push({ tipo: 'POST', body: armarReserva(p), resp: resp || null });
    const nueva = resp && resp.data && Number(resp.data.id_estado) > 0 ? resp.data : null;
    if (!nueva) return { fin: { ...no('reserva_rechazada', 'La agenda no aceptó el horario (puede que se haya ocupado). Su turno actual sigue vigente. Contáselo y ofrecé otro horario con buscar_horarios.'), ledger } };
    if (p.tipo !== 'cambio') return { fin: { ok: true, nueva_cita: nueva.id, readback_text: textoExito(p), ledger } };
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
  // io: { consumir(id)->bool, getCita(id)->resp, postCita(body)->resp, putCita(id, body)->resp }   (cada una puede lanzar)
  async function ejecutar(entrada, io, ahoraISO) {
    const s0 = pasoInicial(entrada, ahoraISO);
    if (s0.fin) return s0.fin;
    const p = s0.propuesta;
    let consumida; try { consumida = await io.consumir(p.id); } catch (e) { consumida = undefined; }
    const s1 = pasoConsumo(s0, consumida); if (s1.fin) return s1.fin;
    let rc; try { rc = p.cita_vieja ? await io.getCita(p.cita_vieja.id) : null; } catch (e) { rc = { error: true }; }
    const s2 = pasoCita(s1, rc); if (s2.fin) return s2.fin;
    if (p.tipo === 'cancelacion') {
      let r; try { r = await io.putCita(p.cita_vieja.id, armarAnulacion()); } catch (e) { r = null; }
      return pasoAnulacion(s2, r).fin;
    }
    let r1; try { r1 = await io.postCita(armarReserva(p)); } catch (e) { r1 = null; }
    const s3 = pasoReserva(s2, r1); if (s3.fin) return s3.fin;
    let r2; try { r2 = await io.putCita(p.cita_vieja.id, armarAnulacion()); } catch (e) { r2 = null; }
    return pasoAnulacion(s3, r2).fin;
  }

  return { proponer, ejecutar, pasoInicial, pasoConsumo, pasoCita, pasoReserva, pasoAnulacion, armarReserva, armarAnulacion, normHora, vigente, TTL_PROPUESTA_MS, MIN_ANTICIPACION_MS };
})();
if (typeof module !== 'undefined') module.exports = AgendaCore;
