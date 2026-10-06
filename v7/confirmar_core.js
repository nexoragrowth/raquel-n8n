// confirmar_core.js — v7 · confirmar un turno (el caso más frecuente: "Confirmo" tras el recordatorio). Fuente de verdad en el repo (se inlinea en nodos Code de n8n).
// Misma regla que el resto: el modelo solo dice la fecha del turno; el código elige la cita (recordatorio abierto o turno visto), la verifica contra la agenda y confirma (id_estado 18).
// Idempotente: si ya estaba confirmada, lo dice sin error.
const ConfirmarCore = (() => {
  const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  const normHora = (h) => { const m = /^(\d{1,2}):(\d{2})/.exec(String(h || '')); return m ? m[1].padStart(2, '0') + ':' + m[2] : ''; };
  const corto = (iso, hora) => `${DIAS[new Date(iso + 'T12:00:00Z').getUTCDay()]} ${Number(iso.slice(8, 10))}/${Number(iso.slice(5, 7))} a las ${hora}`;
  const vigente = (t) => ![1, 14].includes(Number(t.id_estado)) && Number(t.estado_anulacion || 0) === 0;
  const no = (motivo, para_asiri, extra) => ({ ok: false, motivo, para_asiri, ...(extra || {}) });
  const ESTADO_CONFIRMADO = 18;   // "Confirmado por WhatsApp" (el que usa el v6)

  // rows: filas abiertas de recordatorios_enviados (confirmado_at y cancelado_at nulos); turnosVistos: lo que dejó ver_turnos (o null); fecha: 'YYYY-MM-DD' o ''.
  function elegir(rows, turnosVistos, fecha, hoyISO) {
    const abiertas = (rows || []).filter((r) => r && r.id_cita_dentalink && r.fecha_turno && String(r.fecha_turno).slice(0, 10) >= hoyISO)
      .map((r) => ({ cita_id: Number(r.id_cita_dentalink), paciente_id: Number(r.id_paciente_dentalink) || null, fecha: String(r.fecha_turno).slice(0, 10), hora: normHora(r.hora_turno), origen: 'recordatorio' }));
    const sel = fecha ? abiertas.filter((c) => c.fecha === fecha) : abiertas;
    if (sel.length === 1) return { ok: true, cand: sel[0] };
    if (sel.length > 1) {
      return { fin: no('varios_recordatorios', 'Hay varios recordatorios pendientes. Si el paciente confirma todos, llamá a confirmar_turno una vez por cada fecha (formato YYYY-MM-DD); si no está claro, preguntale cuál.',
        { fechas: sel.map((c) => corto(c.fecha, c.hora)), fechas_iso: sel.map((c) => c.fecha) }) };
    }
    if (fecha && Array.isArray(turnosVistos)) {
      const t = turnosVistos.find((x) => x.fecha === fecha && vigente(x));
      if (t) return { ok: true, cand: { cita_id: Number(t.id), paciente_id: Number(t.id_paciente) || null, fecha: t.fecha, hora: normHora(t.hora_inicio), origen: 'agenda' } };
    }
    if (!abiertas.length && !fecha) {
      return { fin: no('sin_recordatorio', 'No hay un recordatorio pendiente. Llamá a ver_turnos; si el paciente tiene un turno vigente que quiere confirmar, llamá a confirmar_turno con su fecha (YYYY-MM-DD).') };
    }
    return { fin: no('sin_turno_en_esa_fecha', 'No encuentro un turno pendiente de confirmar en esa fecha. Mostrale sus turnos con ver_turnos.') };
  }
  // resp = respuesta cruda de GET /citas/{id}
  function verificar(cand, resp) {
    if (!resp || resp.error) return { fin: no('error_tecnico', 'No pude consultar la agenda; no se confirmó nada. Decíselo con sinceridad y avisá a la clínica con avisar_grupo (ACCION).') };
    const d = resp.data || resp;
    const coincide = Number(d.id) === cand.cita_id && d.fecha === cand.fecha && (!cand.hora || normHora(d.hora_inicio) === cand.hora) && (!cand.paciente_id || Number(d.id_paciente) === cand.paciente_id);
    if (!coincide) return { fin: no('cita_cambio', 'El turno cambió desde el recordatorio: no se confirmó nada. Mostrale sus turnos con ver_turnos.') };
    if (!vigente(d)) return { fin: no('cita_no_vigente', 'Ese turno ya no está vigente (anulado). No lo confirmes; ofrecé reprogramarlo si corresponde.') };
    return { ok: true, ya: Number(d.id_estado) === ESTADO_CONFIRMADO };
  }
  // resp = respuesta cruda de PUT /citas/{id} {id_estado: 18}
  function evaluarConfirmacion(cand, resp) {
    const confirmado = !!(resp && resp.data && Number(resp.data.id_estado) === ESTADO_CONFIRMADO);
    // Dentalink contesta 400 "el nuevo estado es igual al original" si ya estaba confirmada: es un éxito.
    const msg = JSON.stringify((resp && resp.error) || '');
    if (confirmado) return { ok: true, ya: false };
    if (/igual|mismo|same|already/i.test(msg)) return { ok: true, ya: true };
    return { fin: no('no_pude_confirmar', 'No pude confirmar el turno en la agenda: sigue como estaba. Decíselo y avisá a la clínica con avisar_grupo (ACCION).') };
  }
  const mensaje = (cand, ya) => (ya ? `Su turno del ${corto(cand.fecha, cand.hora)} ya estaba confirmado.` : `Listo, su turno del ${corto(cand.fecha, cand.hora)} quedó confirmado.`);
  return { elegir, verificar, evaluarConfirmacion, mensaje, ESTADO_CONFIRMADO };
})();
if (typeof module !== 'undefined') module.exports = ConfirmarCore;
