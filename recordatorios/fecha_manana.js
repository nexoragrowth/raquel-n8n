// === Override desde Webhook Manual Recordatorios ===
let whBody = null;
try {
  const whItems = $('Webhook Manual Recordatorios').all();
  if (whItems && whItems.length > 0) {
    whBody = whItems[0].json?.body || whItems[0].json;
  }
} catch (e) {
  // El nodo Webhook Manual no se ejecuto en esta corrida (vino del cron)
}
if (whBody && whBody.fecha_target) {
  const filter = Array.isArray(whBody.id_paciente_filter) ? whBody.id_paciente_filter : [];
  return [{ json: { fecha_target: whBody.fecha_target, tipo_recordatorio: "manual_override", id_paciente_filter: filter } }];
}

// Recordatorio 48h hábiles
// El workflow puede correr todos los días, incluidos sábados y domingos.
// La fecha objetivo se calcula sumando 2 días hábiles: lunes a viernes que la clínica NO tenga cerrados.
// (19/11) Los días cerrados (feriados, puentes, vacaciones) los carga la clínica en el panel (recordatorios_config.dias_cerrados) y el
// Gate los entrega ya como texto 'YYYY-MM-DD' (así no hay corrimiento de día por zona horaria). Sin lista, o si el Gate no la trae,
// el cálculo es EXACTAMENTE el de antes (lunes a viernes). El Gate saltea la corrida de un día cerrado: así cada día hábil queda
// recordado una sola vez, 2 días hábiles antes.

let cerrados = new Set();
try {
  const g = $('Gate - Leer config').first().json;
  if (g && Array.isArray(g.dias_cerrados)) {
    cerrados = new Set(g.dias_cerrados.map((d) => String(d).slice(0, 10)).filter((d) => /^\d{4}-\d{2}-\d{2}$/.test(d)));
  }
} catch (e) {
  // Gate no ejecutado o sin la columna todavía: sin días cerrados
}

const now = new Date();

// Ajuste horario Argentina UTC-3
const argTime = new Date(now.getTime() - (3 * 60 * 60 * 1000));

function formatDateYYYYMMDD(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function addBusinessDays(date, days) {
  const result = new Date(date);
  let addedDays = 0;

  while (addedDays < days) {
    result.setDate(result.getDate() + 1);

    const day = result.getDay();
    const isWeekend = day === 0 || day === 6; // domingo = 0, sábado = 6
    const isCerrado = cerrados.has(formatDateYYYYMMDD(result));

    if (!isWeekend && !isCerrado) {
      addedDays++;
    }
  }

  return result;
}

const targetDate = addBusinessDays(argTime, 2);

return [
  {
    json: {
      fecha_target: formatDateYYYYMMDD(targetDate),
      tipo_recordatorio: "48h_habiles",
      id_paciente_filter: []
    }
  }
];
