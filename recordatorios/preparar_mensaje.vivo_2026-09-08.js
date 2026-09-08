// === MODO PRODUCTIVO ===
const TEST_MODE = false;
const TEST_PHONE = "5491161461034";

const paciente = $('GET Paciente (celular)').item.json;
const cita = $("Solo citas activas").all()[$itemIndex]?.json || {};

const pData = paciente.data || paciente;
const nombre = (pData.nombre || "paciente").trim();
let celular = pData.celular || "";

const fecha = cita.fecha || "";
const hora = (cita.hora_inicio || "").substring(0, 5);
const dentista = (cita.nombre_dentista || "Rodríguez Raquel").replace(/\s+/g, " ").trim();

// Inferir tipo_recordatorio por días hasta la cita
const today = new Date();
const argNow = new Date(today.getTime() - (3 * 60 * 60 * 1000));
argNow.setHours(0, 0, 0, 0);
const fechaCita = new Date(fecha + "T00:00:00");
const daysDiff = Math.round((fechaCita - argNow) / (1000 * 60 * 60 * 24));
const tipo_recordatorio = daysDiff <= 1 ? "24h" : "72h";

// Naturalización fecha
const dias = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
const meses = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];
const diaSemana = dias[fechaCita.getDay()];
const diaSemanaCap = diaSemana.charAt(0).toUpperCase() + diaSemana.slice(1);
const diaNum = fechaCita.getDate();
const mes = meses[fechaCita.getMonth()];
const anio = fechaCita.getFullYear();

// Género heurístico por terminación del primer nombre
const primerNombre = nombre.split(" ")[0];
const ult = primerNombre.slice(-1).toLowerCase();
const tratamiento = ult === "a" ? "Estimada" : ult === "o" ? "Estimado" : "Estimado/a";
const verboObj    = ult === "a" ? "la esperamos" : ult === "o" ? "lo esperamos" : "le esperamos";

// === Normalización celular: SIEMPRE termina como 549XXXXXXXXXX (13 dígitos)
// OJO: el "+" inicial es la señal de que el número YA trae código de país. Hay que
// leerlo ANTES del replace, que lo borra (pacientes de Bolivia, Jujuy es frontera).
const esInternacional = /^\s*\+/.test(celular);
celular = celular.replace(/[^0-9]/g, "");
if (!celular) {
  return { json: { phone: "", remoteJid: "", message: "", nombre, cita_id: cita.id || "", tipo_recordatorio } };
}
if (celular.startsWith("549") && celular.length === 13) {
  // ok, ya está perfecto
} else if (celular.startsWith("54") && celular.length === 12) {
  // 54 + 10 dígitos sin 9 -> agregar 9
  celular = "549" + celular.substring(2);
} else if (celular.length === 10) {
  // sólo 10 dígitos (sin código país ni 9)
  celular = "549" + celular;
} else if (celular.length === 11 && celular.startsWith("15")) {
  // formato local "15XXXXXXXX" -> agregar 549 quitando el 15
  celular = "549" + celular.substring(2);
} else if (esInternacional && !celular.startsWith("54")) {
  // Número EXTRANJERO ya completo (ej. Bolivia +591…): se deja TAL CUAL.
  // Prependerle 549 lo rompía y Evolution rechazaba el envío
  // (caso Isabel Sanai 22/07/2026: +59173327830 -> 54959173327830 -> "Erro ao enviar").
} else if (!celular.startsWith("54")) {
  // cualquier otra cosa que no empiece con 54: prepender 549
  celular = "549" + celular;
}

// === TEMPLATES OFICIALES ===
let realMessage;
if (tipo_recordatorio === "72h") {
  realMessage =
    "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\n" +
    tratamiento + " " + nombre + ",\n" +
    "Le recordamos su turno con la Dra. Rodríguez Raquel:\n\n" +
    "📅 " + diaSemanaCap + " " + diaNum + " de " + mes + " de " + anio + "\n" +
    "🕔 " + hora + " hs\n" +
    "📍 Balcarce Nº37, 2º piso\n\n" +
    "Le pedimos confirmar su asistencia respondiendo a este mensaje para conservar su turno.\n\n" +
    "⚠️ Importante:\n" +
    "* Si su turno está confirmado y no asiste al mismo, de igual manera deberá abonar el control.\n" +
    "* Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.\n\n" +
    "Esperamos su confirmación, gracias por elegirnos 💙";
} else {
  realMessage =
    "Hola, " + nombre + " 😊 le recordamos que mañana " + verboObj + " a las " + hora +
    " hs para su atención con la Dra. Raquel Rodríguez en nuestra Clínica Áurea Odontología Estética. Saludos ✨";
}

const finalPhone = TEST_MODE ? TEST_PHONE : celular;
const finalJid = finalPhone + "@s.whatsapp.net";
const finalMessage = TEST_MODE ? "[TEST " + tipo_recordatorio + "] Para: " + nombre + " (" + celular + ")\n\n" + realMessage : realMessage;

return {
  json: {
    phone: finalPhone,
    remoteJid: finalJid,
    message: finalMessage,
    nombre,
    cita_id: cita.id || "",
    id_paciente: pData.id || cita.id_paciente || "",
    fecha,
    hora,
    tipo_recordatorio,
    dentista
  }
};