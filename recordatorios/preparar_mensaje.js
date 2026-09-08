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

// === CONSULTA (primera visita) — pedido de la Dra. Raquel, WhatsApp 2026-09-08 ===
// El "puntito amarillo" de la agenda es motivo_atencion 'Consulta Ortodoncia ' (Dentalink lo manda con
// espacio final). tratamiento_sin_asignar es 0 en TODAS las citas (verificado sobre 66), así que el único
// marcador confiable es el motivo. Anclado al INICIO (/^consulta\b/i): "Consulta Ortodoncia", "Consulta" y
// "CONSULTA" sí; "Control post consulta" / "Consultar precio" NO. Un falso negativo manda el genérico de
// siempre (sin daño); un falso positivo le pediría el pago de la consulta a un paciente en tratamiento.
// Si la Dra. confirma otro motivo de primera visita, se ajusta esta línea (y los tests de motivo).
const motivo_atencion = String(cita.motivo_atencion || "").trim();
const es_consulta = /^consulta\b/i.test(motivo_atencion);

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
  return { json: { phone: "", remoteJid: "", message: "", nombre, cita_id: cita.id || "", tipo_recordatorio, motivo_atencion, es_consulta } };
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

// === Precio de la consulta: knowledge_base id=21 ("Valor de la primera consulta"), que la Dra. edita
// desde el panel. Llega en la columna precio_contenido de 'Gate - Leer config' (subconsulta en el SQL del
// gate): NO se puede meter un nodo entre 'Solo citas activas' y este porque la cita se empareja por
// $itemIndex. Mismo criterio que 'Extraer Horarios y Precio' del v6 (/\$[\d.,]+/, fallback '$50.000'),
// tolerando además espacios entre el $ y el número ("$ 55.000") y sin tragarse el punto final de oración
// ("$55.000."). Exige un importe con miles (dd.ddd / dd,ddd) o de 4+ dígitos: "$50mil" o "$5" NO son un
// precio y caen al fallback en vez de imprimir "$50" en el recordatorio.
// try/catch OBLIGATORIO: por el 'Webhook Manual Recordatorios' el Gate no corre y $('Gate - Leer config') tira.
const FALLBACK_PRECIO = "$50.000";
let precio_consulta = FALLBACK_PRECIO;
let precio_origen = "fallback";
try {
  const cfg = $('Gate - Leer config').first().json || {};
  const m = String(cfg.precio_contenido || "").match(/\$\s*(\d{1,3}(?:[.,]\d{3})+|\d{4,})/);
  if (m) {
    precio_consulta = "$" + m[1];
    precio_origen = "kb";
  }
} catch (e) {
  // Camino manual (webhook) o Gate caído (onError continueRegularOutput): queda el fallback.
}

// === TEMPLATES OFICIALES ===
let realMessage;
if (tipo_recordatorio === "72h" && es_consulta) {
  // Bloque TEXTUAL de la Dra. Raquel (2026-09-08): en las consultas la confirmación es sí o sí con el pago.
  // Misma primera línea y misma frase "Le recordamos su turno..." que el genérico: el v6 reconoce el
  // recordatorio en memoria por esas dos señales (Router intent 2 / caso (c) de los sub-agents).
  realMessage =
    "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\n" +
    tratamiento + " " + nombre + ",\n" +
    "Le recordamos su turno con la Dra. Rodríguez Raquel:\n\n" +
    "📅 " + diaSemanaCap + " " + diaNum + " de " + mes + " de " + anio + "\n" +
    "🕔 " + hora + " hs\n" +
    "📍 Balcarce Nº37, 2º piso\n\n" +
    "Para confirmar su asistencia le solicitamos abonar el valor de la consulta (" + precio_consulta + ").\n\n" +
    "⚠️ Importante:\n" +
    "* Si su turno ya está abonado, solo responda a este mensaje con un \"confirmo\".\n" +
    "* Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.\n\n" +
    "Esperamos su confirmación, gracias por elegirnos 💙";
} else if (tipo_recordatorio === "72h") {
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
  if (es_consulta) {
    // Consulta a 24h (solo alcanzable por el webhook manual con fecha_target = mañana: el cron apunta a
    // +2 días hábiles). Misma regla que el bloque largo, sin inventar política nueva.
    realMessage +=
      "\n\nRecuerde que la consulta se confirma con el pago de su valor (" + precio_consulta + "). " +
      "Si ya lo abonó, responda \"confirmo\".";
  }
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
    dentista,
    // Trazabilidad (los lee 'Insert recordatorios_enviados' y quedan visibles en la ejecución):
    // motivo_atencion SIEMPRE string ('' si falta) y es_consulta SIEMPRE boolean — el Postgres v2.6
    // valida tipos contra la tabla viva y un null en boolean lo rechaza.
    motivo_atencion,
    es_consulta,
    precio_consulta,
    precio_origen
  }
};
