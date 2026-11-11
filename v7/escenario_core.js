// escenario_core.js — v7 · (11/11) ESCENARIO DE PRUEBA: fichas y citas inventadas que carga el webhook de prueba en Redis ("escenario:<tel>"),
// para probar a Asiri con el contexto armado a mano (no con las fichas reales del celular de prueba).
// Solo vale para el celular de Lucas o celulares sintéticos: con cualquier otro número devuelve null y la herramienta lee Dentalink como siempre.
// Formato: { fichas: [{ id, nombre, apellidos, rut }], citas: { "<id ficha>": [{ id, id_paciente, fecha:'YYYY-MM-DD', hora_inicio:'HH:MM:SS', id_estado, estado_anulacion }] } }
const EscenarioPrueba = (() => {
  const esTelPrueba = (t) => { const s = String(t || ''); return s === '5491161461034' || /^5490000000\d{3}$/.test(s) || /^549999\d{7}$/.test(s); };
  function leer(raw, tel) {
    if (!raw || !esTelPrueba(tel)) return null;
    let e = null; try { e = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch (x) { return null; }
    if (!e || typeof e !== 'object' || !e.citas || typeof e.citas !== 'object') return null;
    return e;
  }
  function cita(esc, id) {
    for (const lista of Object.values((esc && esc.citas) || {})) for (const c of (lista || [])) if (c && Number(c.id) === Number(id)) return c;
    return null;
  }
  return { esTelPrueba, leer, cita };
})();
if (typeof module !== 'undefined') module.exports = EscenarioPrueba;
