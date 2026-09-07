  fecha: slot.fecha,
  // El bloque de turnos escribe las horas SIN cero adelante ("8:00", "8:40") — asi las pidio la Dra. — y el
  // parser de aceptacion (Step 3.5c, un LLM) las copia de ahi. La agenda espera HH:MM: se normaliza aca,
  // que es el ultimo lugar antes del POST de reserva.
  hora_inicio: (function (h) { const m = /^(\d{1,2}):(\d{2})/.exec(String(h || '')); return m ? m[1].padStart(2, '0') + ':' + m[2] : h; })(slot.hora_inicio),