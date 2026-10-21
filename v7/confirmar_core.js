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

  const sinTildes = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const primerNombre = (s) => String(s || '').trim().split(/\s+/)[0] || '';
  // rows: filas abiertas de recordatorios_enviados (confirmado_at y cancelado_at nulos); turnosVistos: lo que dejó ver_turnos (o null);
  // fecha 'YYYY-MM-DD', hora 'HH:MM' y nombre (familia): opcionales, solo si el paciente confirma UNO de varios.
  // (21/10, incidente real: papá con dos hijos con turno el MISMO día respondió "Confirmo" → bucle "¿Cuál de estos turnos confirma?", porque
  // se elegía solo por fecha y no había forma de distinguir dos turnos del mismo día). Ahora: sin datos = TODOS los pendientes (lo que hacía el
  // v6), con datos = los que coinciden. Devuelve { ok, cands: [...] } (cand = el primero, por compatibilidad) o { fin }.
  function elegir(rows, turnosVistos, fecha, hoyISO, hora, nombre, ahoraHM) {
    // (21/10, auditoría) recordatorios_enviados tiene filas REPETIDAS para la misma cita cuando el envío se corre dos veces (18 citas): una cita = un turno.
    // (21/10, auditoría: el v6 confirmó "por WhatsApp" dos citas de HOY cuando el paciente mandó el comprobante después de atenderse) Un turno de hoy
    // cuya hora ya pasó no se confirma: ahoraHM = 'HH:MM' de Jujuy (opcional).
    const ahora = normHora(ahoraHM);
    const porCita = new Map();
    for (const r of (rows || [])) {
      if (!(r && r.id_cita_dentalink && r.fecha_turno && String(r.fecha_turno).slice(0, 10) >= hoyISO)) continue;
      if (ahora && String(r.fecha_turno).slice(0, 10) === hoyISO && normHora(r.hora_turno) && normHora(r.hora_turno) <= ahora) continue;
      const id = Number(r.id_cita_dentalink);
      if (!porCita.has(id)) porCita.set(id, { cita_id: id, paciente_id: Number(r.id_paciente_dentalink) || null, fecha: String(r.fecha_turno).slice(0, 10), hora: normHora(r.hora_turno),
        nombre: primerNombre(r.nombre_paciente), origen: 'recordatorio' });
    }
    const abiertas = [...porCita.values()];
    // (07/10) El modelo a veces da vuelta día y mes ("jueves 10/12" → 2026-10-12; escenarios reales REAL-14/15). Si la fecha no coincide se prueba invertida,
    // y si hay UN solo recordatorio pendiente, "confirmo" es para ese.
    const invertida = (f) => (/^\d{4}-\d{2}-\d{2}$/.test(String(f || '')) ? `${f.slice(0, 4)}-${f.slice(8, 10)}-${f.slice(5, 7)}` : f);
    let sel = fecha ? abiertas.filter((c) => c.fecha === fecha) : abiertas;
    if (fecha && !sel.length) sel = abiertas.filter((c) => c.fecha === invertida(fecha));
    if (fecha && !sel.length && abiertas.length === 1) sel = abiertas;
    // Filtros que solo ACHICAN la selección si coinciden (un dato que no coincide con nada no deja al paciente sin confirmar).
    const h = normHora(hora);
    if (h && sel.length > 1) { const x = sel.filter((c) => c.hora === h); if (x.length) sel = x; }
    const nom = sinTildes(primerNombre(nombre));
    if (nom && sel.length > 1) { const x = sel.filter((c) => sinTildes(c.nombre) === nom); if (x.length) sel = x; }
    if (sel.length) return { ok: true, cands: sel, cand: sel[0] };
    if (fecha && Array.isArray(turnosVistos)) {
      const t = turnosVistos.find((x) => (x.fecha === fecha || x.fecha === invertida(fecha)) && vigente(x) && (!h || normHora(x.hora_inicio) === h));
      if (t) { const c = { cita_id: Number(t.id), paciente_id: Number(t.id_paciente) || null, fecha: t.fecha, hora: normHora(t.hora_inicio), nombre: '', origen: 'agenda' }; return { ok: true, cands: [c], cand: c }; }
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
  // (07/10, Lucas) Para el paciente es lo mismo si ya figuraba confirmado o se confirmó recién: "ya estaba confirmado" sonaba a corrección cuando él acababa de confirmar.
  // (21/10) Con varios turnos, un solo mensaje; con varios pacientes (familia), cada turno con su nombre.
  const lista = (xs) => (xs.length <= 1 ? xs.join('') : xs.slice(0, -1).join(', ') + ' y ' + xs[xs.length - 1]);
  function mensaje(cands) {
    const cs = (Array.isArray(cands) ? cands : [cands]).filter(Boolean);
    if (cs.length <= 1) return `Perfecto, su turno del ${corto(cs[0].fecha, cs[0].hora)} está confirmado.`;
    const conNombre = new Set(cs.map((c) => sinTildes(c.nombre)).filter(Boolean)).size > 1;
    return `Perfecto, quedaron confirmados sus turnos del ${lista(cs.map((c) => corto(c.fecha, c.hora) + (conNombre && c.nombre ? ` (${c.nombre})` : '')))}.`;
  }
  // (21/10) Junta lo que devolvió confirmar_una por cada turno: [{ ok, ya, escribio, motivo, para_asiri, cand }]. Si confirmó alguno, éxito con el texto
  // de los confirmados (y, si otro falló, la frase honesta + aviso para la clínica). Si ninguno, el primer motivo de falla.
  function resumir(resultados) {
    const rs = (resultados || []).filter((r) => r && r.cand);
    const oks = rs.filter((r) => r.ok === true);
    // (21/10, auditoría) Recordatorio de un turno que la clínica anuló o movió después de mandarlo: si se confirmaron los otros, al paciente no se le
    // dice "no pude confirmar" (no hay nada que confirmar); la secretaria se entera con un FYI.
    const NO_APLICA = ['cita_no_vigente', 'cita_cambio'];
    const viejas = oks.length ? rs.filter((r) => r.ok !== true && NO_APLICA.includes(r.motivo)) : [];
    const fallas = rs.filter((r) => r.ok !== true && !viejas.includes(r));
    if (!oks.length) {
      const f = fallas[0] || {};
      return { ok: false, motivo: f.motivo || 'error_tecnico', para_asiri: f.para_asiri || 'No pude confirmar en la agenda; avisá a la clínica con avisar_grupo (ACCION).', escribio: false, cands: [] };
    }
    let texto = mensaje(oks.map((r) => r.cand));
    let aviso = null;
    if (fallas.length) {
      const cuales = lista(fallas.map((r) => 'el del ' + corto(r.cand.fecha, r.cand.hora) + (r.cand.nombre ? ` (${r.cand.nombre})` : '')));
      texto += ` No pude confirmar ${cuales}: la secretaria lo revisa.`;
      aviso = `[ACCIÓN] Confirmación a medias: el paciente confirmó, pero no se pudo confirmar en la agenda ${cuales}. Revisar.`;
    } else if (viejas.length) {
      aviso = `[FYI] El paciente confirmó; el recordatorio ${lista(viejas.map((r) => 'del ' + corto(r.cand.fecha, r.cand.hora) + (r.cand.nombre ? ` (${r.cand.nombre})` : '')))} ya no coincide con la agenda (anulado o movido): ese no se confirmó.`;
    }
    return { ok: true, ya: oks.every((r) => r.ya === true), escribio: oks.some((r) => r.escribio === true || r.ya === true), readback_text: texto, parcial: fallas.length > 0, aviso, cands: oks.map((r) => r.cand) };
  }
  return { elegir, verificar, evaluarConfirmacion, mensaje, resumir, ESTADO_CONFIRMADO };
})();
if (typeof module !== 'undefined') module.exports = ConfirmarCore;
