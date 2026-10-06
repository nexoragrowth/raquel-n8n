// ficha_core.js — v7 · quién es el paciente. Fuente de verdad en el repo (se inlinea en nodos Code de n8n).
// Un celular puede tener VARIAS fichas (familia). El modelo nunca elige ids: el código resuelve las fichas del celular, el paciente dice para quién es
// (nombre o DNI), y el código verifica que coincida con una ficha real. Toda escritura exige ficha elegida (agenda_core.proponer).
const FichaCore = (() => {
  const sinT = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const tokens = (x) => sinT(x).replace(/[^a-z0-9 ]/g, ' ').split(/\s+/).filter((t) => t.length >= 3);
  const soloDigitos = (x) => String(x || '').replace(/\D/g, '');
  const vigente = (t) => ![1, 14].includes(Number(t.id_estado)) && Number(t.estado_anulacion || 0) === 0;
  const titulo = (s) => String(s || '').trim().split(/\s+/).map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()).join(' ');

  // Respuesta cruda de Dentalink (GET /pacientes?q=celular) → fichas habilitadas. rut = DNI (solo se usa para comparar, nunca se muestra).
  function fichasDeRespuesta(resp) {
    const data = (resp && (resp.data || (Array.isArray(resp) && resp[0] && resp[0].data))) || [];
    return data.filter((p) => p && p.id && Number(p.habilitado === undefined ? 1 : p.habilitado) === 1)
      .map((p) => ({ id: Number(p.id), nombre: titulo(p.nombre), apellidos: titulo(p.apellidos || ''), rut: soloDigitos(p.rut) }));
  }
  // Estado guardado en Redis: { fichas:[{id,nombre,apellidos,rut}], elegida: id|null }.  Con una sola ficha queda elegida.
  const estadoInicial = (fichas) => ({ fichas, elegida: fichas.length === 1 ? fichas[0].id : null });

  // El paciente dijo para quién es (nombre/apellido o DNI). Devuelve { ok:true, estado } o { ok:false, motivo, para_asiri }.
  function elegir(estado, dato) {
    const fichas = (estado && estado.fichas) || [];
    if (!fichas.length) return { ok: false, motivo: 'sin_ficha', para_asiri: '[Nota interna para vos, NO la repitas al paciente] No hay fichas para este celular: pasalo a la clínica con avisar_grupo.' };
    const dni = soloDigitos(dato.dni);
    if (dni.length >= 6) {
      const c = fichas.filter((f) => f.rut && f.rut === dni);
      if (c.length === 1) return { ok: true, estado: { ...estado, elegida: c[0].id }, nombre: c[0].nombre };
      return { ok: false, motivo: 'dni_no_coincide', para_asiri: '[Nota interna para vos, NO la repitas al paciente] Ese DNI no coincide con ninguna ficha de este celular. Pedile nombre y apellido del paciente.' };
    }
    const tk = tokens(dato.nombre);
    if (!tk.length) return { ok: false, motivo: 'sin_dato', para_asiri: '[Nota interna para vos, NO la repitas al paciente] Pedile el nombre y apellido (o el DNI) del paciente.' };
    // Puntaje = cuántos tokens del dato aparecen en la ficha: "Lucas Test" coincide 2 con "Test - Lucas" y 1 con "Test - Jana" → gana la primera.
    // Solo si el mejor puntaje es único; con empate ("Test") sigue siendo ambiguo y se pide el DNI.
    const puntos = fichas.map((f) => { const ft = tokens(f.nombre + ' ' + f.apellidos); return tk.filter((t) => ft.includes(t)).length; });
    const max = Math.max(...puntos);
    const c = max > 0 ? fichas.filter((_, i) => puntos[i] === max) : [];
    if (c.length === 1) return { ok: true, estado: { ...estado, elegida: c[0].id }, nombre: c[0].nombre };
    return { ok: false, motivo: c.length ? 'ambiguo' : 'nombre_no_coincide', para_asiri: c.length ? 'Hay más de una ficha que coincide: pedile el DNI.' : 'Ese nombre no coincide con ninguna ficha de este celular. Pedile el DNI.',
      fichas: fichas.map((f) => f.nombre) };
  }

  // Citas de TODAS las fichas del celular (una respuesta cruda por ficha, en el mismo orden) → turnos vigentes futuros ordenados.
  function turnosVistos(fichas, respuestas, hoyISO) {
    const out = [];
    fichas.forEach((f, i) => {
      const r = respuestas[i]; const data = (r && (r.data || (Array.isArray(r) && r[0] && r[0].data))) || [];
      for (const t of data) {
        if (!t || !t.id || !t.fecha || t.fecha < hoyISO || !vigente(t)) continue;
        out.push({ id: Number(t.id), id_paciente: Number(t.id_paciente || f.id), fecha: t.fecha, hora_inicio: String(t.hora_inicio || '').slice(0, 5), id_estado: Number(t.id_estado), estado_anulacion: Number(t.estado_anulacion || 0) });
      }
    });
    out.sort((a, b) => (a.fecha + a.hora_inicio).localeCompare(b.fecha + b.hora_inicio));
    const vistos = new Set();
    return out.filter((t) => (vistos.has(t.id) ? false : (vistos.add(t.id), true)));
  }
  // Texto para Asiri (nunca ids): "viernes 16/10 a las 09:10 (Dana)"
  const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  function resumenTurnos(fichas, turnos) {
    const nombre = (id) => (fichas.find((f) => f.id === id) || {}).nombre || '';
    return turnos.map((t) => `${DIAS[new Date(t.fecha + 'T12:00:00Z').getUTCDay()]} ${Number(t.fecha.slice(8))}/${Number(t.fecha.slice(5, 7))} a las ${t.hora_inicio}` + (fichas.length > 1 ? ` (${nombre(t.id_paciente)})` : ''));
  }
  return { fichasDeRespuesta, estadoInicial, elegir, turnosVistos, resumenTurnos };
})();
if (typeof module !== 'undefined') module.exports = FichaCore;
