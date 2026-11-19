// recordatorios/programados.js — lógica PURA del workflow "Recordatorios programados" (n8n). Se inlinea en sus nodos Code.
// Mismas reglas que el envío del 19/11 a las 08:01 (workflow de un solo uso, verificado en vivo): contar lo esperado con el filtro del workflow de avisos,
// no disparar si ya hay avisos de esa fecha, verificar después y suspender la corrida automática SOLO si salieron todos.
const ProgramadosCore = (() => {
  const ISO = /^\d{4}-\d{2}-\d{2}$/;
  const sumar = (iso, n) => { const d = new Date(iso + 'T12:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
  const finde = (iso) => { const w = new Date(iso + 'T12:00:00Z').getUTCDay(); return w === 0 || w === 6; };

  // Citas de Dentalink de ESA fecha → cuántas recibirían el aviso (mismo filtro que "Solo citas activas": no anuladas, ni 18, ni 14).
  function esperado(respuestaDentalink) {
    const r = respuestaDentalink || {};
    const data = Array.isArray(r.data) ? r.data : null;
    if (data === null) return { ok: false, motivo: 'Dentalink no devolvió datos' };
    const hayMas = !!(r.links && !Array.isArray(r.links) && r.links.next);
    const n = data.filter((c) => Number(c.estado_anulacion || 0) !== 1 && ![18, 14].includes(Number(c.id_estado || 0))).length;
    return { ok: !hayMas, esperado: n, hay_mas: hayMas, motivo: hayMas ? 'hay más de una página de citas' : 'ok' };
  }

  // ¿Se dispara? Solo si no había avisos de esa fecha (si alguien ya lo mandó, no se repite) y hay algo para mandar.
  function decidir(ya, est) {
    if (!est || est.ok !== true) return { disparar: false, motivo: (est && est.motivo) || 'no se pudo contar' };
    if (Number(ya) > 0) return { disparar: false, motivo: 'ya había avisos enviados para esa fecha' };
    if (est.esperado === 0) return { disparar: false, motivo: 'no hay turnos para avisar' };
    return { disparar: true, motivo: 'ok' };
  }

  // Día de la corrida AUTOMÁTICA que avisa esa fecha: el día hábil 2 lugares antes (lunes a viernes, salteando los días cerrados).
  // Idéntico a recordatorios/fecha_manana.js y al panel (lib/recordatorios/dias-sin-atencion.ts: diaDeEnvio).
  function diaDeCorrida(fechaTurno, cerrados) {
    const c = new Set((cerrados || []).map((d) => String(d).slice(0, 10)));
    const habil = (d) => !finde(d) && !c.has(d);
    if (!ISO.test(String(fechaTurno)) || !habil(fechaTurno)) return null;
    let d = fechaTurno;
    for (let n = 0; n < 2; ) { d = sumar(d, -1); if (habil(d)) n++; }
    return d;
  }

  // Después del envío: salió todo si se registraron al menos tantos avisos como se esperaban. Solo así se suspende la corrida automática,
  // y solo si esa corrida todavía no pasó (hoyJujuy, horaJujuy, horaEnvio).
  function cerrar({ ya, est, enviados, disparado, noRepetir, fechaTurno, cerrados, hoy, hora, horaEnvio }) {
    const e = est && est.ok === true ? Number(est.esperado) || 0 : 0;
    let estado; let salioTodo;
    if (disparado) { salioTodo = e > 0 && Number(enviados) >= e; estado = salioTodo ? 'enviado' : 'error'; }
    else if (Number(ya) > 0) { salioTodo = true; estado = 'enviado'; }            // ya estaba mandado por otra vía: no se repite
    else if (est && est.ok === true && e === 0) { salioTodo = false; estado = 'enviado'; }   // no había nada para mandar
    else { salioTodo = false; estado = 'error'; }
    const corrida = diaDeCorrida(fechaTurno, cerrados);
    const corridaPendiente = !!corrida && (corrida > hoy || (corrida === hoy && Number(hora) < Number(horaEnvio)));
    const suspender = noRepetir === true && salioTodo && corridaPendiente ? corrida : null;
    return { estado, suspender, resultado: { esperado: e, enviados: Number(enviados) || 0, ya: Number(ya) || 0, disparado: !!disparado, corrida, suspendido: suspender, salio_todo: salioTodo, motivo: (est && est.motivo) || '' } };
  }

  return { esperado, decidir, diaDeCorrida, cerrar };
})();
if (typeof module !== 'undefined') module.exports = ProgramadosCore;
