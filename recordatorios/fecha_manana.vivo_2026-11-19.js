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
// La fecha objetivo se calcula sumando 2 días hábiles, contando solo lunes a viernes.

const now = new Date();

// Ajuste horario Argentina UTC-3
const argTime = new Date(now.getTime() - (3 * 60 * 60 * 1000));

function addBusinessDays(date, days) {
  const result = new Date(date);
  let addedDays = 0;

  while (addedDays < days) {
    result.setDate(result.getDate() + 1);

    const day = result.getDay();
    const isWeekend = day === 0 || day === 6; // domingo = 0, sábado = 6

    if (!isWeekend) {
      addedDays++;
    }
  }

  return result;
}

function formatDateYYYYMMDD(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
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