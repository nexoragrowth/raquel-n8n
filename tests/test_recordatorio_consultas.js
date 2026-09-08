// tests/test_recordatorio_consultas.js — corre el JS REAL del nodo "Preparar mensaje" del workflow
// "Recordatorio de Turno 48HS - Dra. Raquel" (7RqTApkvVavRmq3R) con node, mockeando el entorno de n8n
// ($input, $(), $itemIndex, $execution) y fijando la fecha de "hoy" (Date sombreado) para que 24h/72h sea
// determinístico. Mismo harness que tests/test_media_nodos.js.
//
// Fuente única: recordatorios/preparar_mensaje.js (el apply lo embebe tal cual). El código VIVO del nodo al
// 2026-09-08 está congelado en recordatorios/preparar_mensaje.vivo_2026-09-08.js y se corre con los MISMOS mocks:
// para toda cita que NO es consulta, el mensaje nuevo tiene que ser BYTE A BYTE igual al vivo.
//
// Correr: node tests/test_recordatorio_consultas.js
process.env.TZ = "America/Argentina/Jujuy"; // el nodo usa getDay/getDate/setHours locales: fijamos la zona

const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const NUEVO = read("recordatorios/preparar_mensaje.js");
const VIVO = read("recordatorios/preparar_mensaje.vivo_2026-09-08.js");
const GATE_SQL = read("recordatorios/gate_leer_config.sql").trim();

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const compilar = (src) => new AsyncFunction("$input", "$", "$itemIndex", "$execution", "console", "Date", src);
const fnNuevo = compilar(NUEVO);
const fnVivo = compilar(VIVO);

// "Hoy" fijo: lunes 2026-09-07 08:00 ART (= 11:00Z, la hora real a la que corre el cron). Date sombreado:
// `new Date()` sin argumentos devuelve ese instante; con argumentos se comporta como el Date real.
const mkDate = (fixedIso) => {
  const FIXED = new Date(fixedIso).getTime();
  return class FixedDate extends Date {
    constructor(...a) { super(...(a.length ? a : [FIXED])); }
    static now() { return FIXED; }
  };
};
const HOY = "2026-09-07T11:00:00Z";

// Contenido REAL de knowledge_base id=21 al 2026-09-08 (SELECT contra el v3).
const KB21 = "La primera consulta tiene un valor de $50.000 e incluye evaluación + diagnóstico presuntivo. El valor de los tratamientos (ortopedia, brackets, alineadores) puede estimarse en la primer consulta pero se define luego de tener un diagnostico y plan de tratamiento personalizado según cada paciente.";

// Fixtures con la forma real de Dentalink (id_paciente int, hora_inicio HH:MM:SS, motivo con espacio final).
const CITA = (over = {}) => ({
  id: 8773, id_paciente: 4321, id_estado: 15, estado_cita: "Notificado por WhatsApp", estado_anulacion: 0,
  fecha: "2026-09-09", hora_inicio: "16:10:00", hora_fin: "16:50:00", duracion: 40,
  nombre_dentista: "Rodríguez Raquel", motivo_atencion: "En TTO LARGO", nombre_tratamiento: "Nuevo plan de tratamiento",
  tratamiento_sin_asignar: 0, ...over,
});
const PACIENTE = (over = {}) => ({ id: 4321, nombre: "Martina", apellidos: "Test", celular: "+543884176520", ...over });

// Mock de $(): tira para nodos no ejecutados (como n8n). `gate: SIN_GATE` simula el camino manual (webhook),
// donde 'Gate - Leer config' no corrió; `gate` con {error} simula el onError continueRegularOutput.
const SIN_GATE = Symbol("Gate - Leer config no ejecutó");
function mkDollar({ paciente, citas, gate }) {
  return (nombre) => {
    if (nombre === "GET Paciente (celular)") {
      const json = { data: paciente };
      return { item: { json }, first: () => ({ json }), all: () => [{ json }], isExecuted: true };
    }
    if (nombre === "Solo citas activas") {
      const items = citas.map((c) => ({ json: c }));
      return { all: () => items, item: items[0], first: () => items[0], isExecuted: true };
    }
    if (nombre === "Gate - Leer config") {
      if (gate === SIN_GATE) throw new Error("Referenced node is unexecuted: 'Gate - Leer config'");
      return { first: () => ({ json: gate }), item: { json: gate }, all: () => [{ json: gate }], isExecuted: true };
    }
    throw new Error(`nodo desconocido ${nombre}`);
  };
}

async function correr(fn, { paciente = PACIENTE(), cita = CITA(), citas = null, gate = { suspender: false, precio_contenido: KB21 }, itemIndex = 0, hoy = HOY } = {}) {
  const lista = citas || [cita];
  const $input = { first: () => ({ json: { ya_existe: false } }), all: () => [{ json: { ya_existe: false } }], item: { json: { ya_existe: false } } };
  const res = await fn.call({}, $input, mkDollar({ paciente, citas: lista, gate }), itemIndex, { id: "exec-test" }, console, mkDate(hoy));
  if (!res || typeof res !== "object" || Array.isArray(res) || !res.json) throw new Error("Preparar mensaje debe devolver UN objeto {json}");
  return res.json;
}
const nuevo = (o) => correr(fnNuevo, o);
const vivo = (o) => correr(fnVivo, o);

let fallos = 0;
const check = (nombre, cond, detalle) => { console.log(`${cond ? "OK  " : "FAIL"} ${nombre}${cond ? "" : " — " + detalle}`); if (!cond) fallos++; };
const KEYS_VIVO = ["phone", "remoteJid", "message", "nombre", "cita_id", "id_paciente", "fecha", "hora", "tipo_recordatorio", "dentista"];
const igualAlVivo = (a, b) => KEYS_VIVO.every((k) => a[k] === b[k]);
const difKeys = (a, b) => KEYS_VIVO.filter((k) => a[k] !== b[k]).map((k) => `${k}: ${JSON.stringify(a[k])} vs ${JSON.stringify(b[k])}`).join(" | ");

// Bloque TEXTUAL de la Dra. Raquel (WhatsApp 2026-09-08 09:20), con el precio de la KB real.
const BLOQUE_DRA =
  "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n" +
  "\n" +
  "Estimada Martina,\n" +
  "Le recordamos su turno con la Dra. Rodríguez Raquel:\n" +
  "\n" +
  "📅 Miércoles 9 de septiembre de 2026\n" +
  "🕔 16:10 hs\n" +
  "📍 Balcarce Nº37, 2º piso\n" +
  "\n" +
  "Para confirmar su asistencia le solicitamos abonar el valor de la consulta ($50.000).\n" +
  "\n" +
  "⚠️ Importante:\n" +
  "* Si su turno ya está abonado, solo responda a este mensaje con un \"confirmo\".\n" +
  "* Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.\n" +
  "\n" +
  "Esperamos su confirmación, gracias por elegirnos 💙";

// Template genérico 72h de HOY (constantes del nodo vivo), para Martina 9/9 16:10.
const GENERICO_72H_MARTINA =
  "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\n" +
  "Estimada Martina,\n" +
  "Le recordamos su turno con la Dra. Rodríguez Raquel:\n\n" +
  "📅 Miércoles 9 de septiembre de 2026\n" +
  "🕔 16:10 hs\n" +
  "📍 Balcarce Nº37, 2º piso\n\n" +
  "Le pedimos confirmar su asistencia respondiendo a este mensaje para conservar su turno.\n\n" +
  "⚠️ Importante:\n" +
  "* Si su turno está confirmado y no asiste al mismo, de igual manera deberá abonar el control.\n" +
  "* Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.\n\n" +
  "Esperamos su confirmación, gracias por elegirnos 💙";
// Template genérico 24h de HOY, para Martina mañana 16:10.
const GENERICO_24H_MARTINA =
  "Hola, Martina 😊 le recordamos que mañana la esperamos a las 16:10 hs para su atención con la Dra. Raquel Rodríguez en nuestra Clínica Áurea Odontología Estética. Saludos ✨";
const FRASE_24H_CONSULTA = "\n\nRecuerde que la consulta se confirma con el pago de su valor ($50.000). Si ya lo abonó, responda \"confirmo\".";

(async () => {
  // 0) el entorno de test es el que creemos
  check("entorno: TZ Argentina y 2026-09-09 es miércoles", new Date("2026-09-09T00:00:00").getDay() === 3 && new Date("2026-09-09T00:00:00").getTimezoneOffset() === 180, String(new Date("2026-09-09T00:00:00")));
  check("entorno: el vivo con Date fijo infiere 72h para el 9/9 y 24h para el 8/9", (await vivo()).tipo_recordatorio === "72h" && (await vivo({ cita: CITA({ fecha: "2026-09-08" }) })).tipo_recordatorio === "24h", "");

  // 1) CONSULTA 72h -> bloque EXACTO de la Dra. con el precio de la KB
  let n = await nuevo({ cita: CITA({ motivo_atencion: "Consulta Ortodoncia " }) });
  check("consulta 72h: mensaje === bloque textual de la Dra.", n.message === BLOQUE_DRA, JSON.stringify(n.message));
  check("consulta 72h: es_consulta true, motivo trimmeado, precio de la KB", n.es_consulta === true && n.motivo_atencion === "Consulta Ortodoncia" && n.precio_consulta === "$50.000" && n.precio_origen === "kb", JSON.stringify(n));
  check("consulta 72h: tipo 72h y el resto de las keys igual que hoy", n.tipo_recordatorio === "72h" && n.phone === "5493884176520" && n.remoteJid === "5493884176520@s.whatsapp.net" && n.cita_id === 8773 && n.id_paciente === 4321 && n.fecha === "2026-09-09" && n.hora === "16:10" && n.dentista === "Rodríguez Raquel", JSON.stringify(n));
  check("consulta 72h: señales que el v6 usa para reconocer el recordatorio en memoria (empieza AUREA + 'Le recordamos su turno')", n.message.startsWith("✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨") && n.message.includes("Le recordamos su turno con la Dra. Rodríguez Raquel:"), n.message.slice(0, 60));
  check("consulta 72h: NO trae la frase del genérico ('deberá abonar el control' / 'respondiendo a este mensaje para conservar')", !n.message.includes("deberá abonar el control") && !n.message.includes("para conservar su turno"), n.message);

  // 2) CONSULTA 24h -> template corto de hoy + frase final
  n = await nuevo({ cita: CITA({ motivo_atencion: "Consulta Ortodoncia ", fecha: "2026-09-08" }) });
  check("consulta 24h: genérico 24h de hoy + frase final con el precio", n.message === GENERICO_24H_MARTINA + FRASE_24H_CONSULTA, JSON.stringify(n.message));
  check("consulta 24h: tipo 24h, es_consulta true", n.tipo_recordatorio === "24h" && n.es_consulta === true, JSON.stringify(n));

  // 3) TRATAMIENTO 72h -> BYTE A BYTE igual a hoy (contra el código vivo y contra el literal)
  for (const motivo of ["En TTO LARGO", "En TTO CORTO", "Control Contención ", "Devolución con escaneo ", "Inicio TTO de Ortopedia", "No registra motivo", "Escaneo"]) {
    const a = await nuevo({ cita: CITA({ motivo_atencion: motivo }) });
    const b = await vivo({ cita: CITA({ motivo_atencion: motivo }) });
    check(`tratamiento 72h '${motivo.trim()}': salida igual al nodo vivo`, igualAlVivo(a, b), difKeys(a, b));
    check(`tratamiento 72h '${motivo.trim()}': es_consulta false, motivo string`, a.es_consulta === false && a.motivo_atencion === motivo.trim(), JSON.stringify([a.es_consulta, a.motivo_atencion]));
  }
  n = await nuevo();
  check("tratamiento 72h: mensaje === literal del template vivo", n.message === GENERICO_72H_MARTINA, JSON.stringify(n.message));

  // 4) TRATAMIENTO 24h -> BYTE A BYTE igual a hoy
  n = await nuevo({ cita: CITA({ fecha: "2026-09-08" }) });
  let v = await vivo({ cita: CITA({ fecha: "2026-09-08" }) });
  check("tratamiento 24h: salida igual al nodo vivo", igualAlVivo(n, v), difKeys(n, v));
  check("tratamiento 24h: mensaje === literal del template vivo (sin frase de consulta)", n.message === GENERICO_24H_MARTINA && !n.message.includes("se confirma con el pago"), JSON.stringify(n.message));

  // 5) PRECIO desde la KB con distintos formatos
  const precio = async (contenido) => (await nuevo({ cita: CITA({ motivo_atencion: "Consulta Ortodoncia " }), gate: { suspender: false, precio_contenido: contenido } }));
  n = await precio("La primera consulta tiene un valor de $50.000 e incluye evaluación.");
  check("precio '$50.000' -> $50.000 (kb)", n.precio_consulta === "$50.000" && n.precio_origen === "kb" && n.message.includes("consulta ($50.000)."), JSON.stringify([n.precio_consulta, n.precio_origen]));
  n = await precio("La primera consulta vale $ 55.000 e incluye evaluación.");
  check("precio '$ 55.000' (espacio, el regex del v6 NO lo toma) -> $55.000 (kb)", n.precio_consulta === "$55.000" && n.precio_origen === "kb" && n.message.includes("consulta ($55.000)."), JSON.stringify([n.precio_consulta, n.precio_origen]));
  n = await precio("La consulta cuesta $60.000.");
  check("precio '$60.000.' (punto final de oración) -> $60.000", n.precio_consulta === "$60.000", n.precio_consulta);
  n = await precio("Consulta: $ 45,000");
  check("precio '$ 45,000' (coma) -> $45,000", n.precio_consulta === "$45,000", n.precio_consulta);
  n = await precio("La primera consulta incluye evaluación y diagnóstico.");
  check("precio sin '$' -> fallback $50.000", n.precio_consulta === "$50.000" && n.precio_origen === "fallback" && n.message === BLOQUE_DRA, JSON.stringify([n.precio_consulta, n.precio_origen]));
  n = await precio(null);
  check("precio_contenido null (fila 21 borrada) -> fallback", n.precio_consulta === "$50.000" && n.precio_origen === "fallback", JSON.stringify([n.precio_consulta, n.precio_origen]));
  n = await precio("$ abc");
  check("precio '$ abc' (sin dígito) -> fallback", n.precio_consulta === "$50.000" && n.precio_origen === "fallback", n.precio_consulta);
  // Corrección 8/9: `\s*` (antes `\s?`: dos espacios caían al fallback) y solo importes reales (antes "$50mil" -> "$50").
  n = await precio("Consulta: $  70.000 (dos espacios)");
  check("precio '$  70.000' (dos espacios) -> $70.000 (kb)", n.precio_consulta === "$70.000" && n.precio_origen === "kb", JSON.stringify([n.precio_consulta, n.precio_origen]));
  n = await precio("La consulta sale $50mil");
  check("precio '$50mil' (no es un importe) -> fallback, nunca '$50'", n.precio_consulta === "$50.000" && n.precio_origen === "fallback", n.precio_consulta);
  n = await precio("Seña $5 y el resto después");
  check("precio '$5' (un dígito) -> fallback", n.precio_consulta === "$50.000" && n.precio_origen === "fallback", n.precio_consulta);
  n = await precio("Valor $50.000,00 final");
  check("precio '$50.000,00' -> $50.000 (sin centavos)", n.precio_consulta === "$50.000" && n.precio_origen === "kb", n.precio_consulta);
  n = await precio("Plan completo $1.500.000; consulta $50.000");
  check("precio '$1.500.000' (primer importe del texto, como el v6) -> $1.500.000", n.precio_consulta === "$1.500.000", n.precio_consulta);
  n = await precio("Consulta $50000");
  check("precio '$50000' (4+ dígitos sin separador) -> $50000", n.precio_consulta === "$50000" && n.precio_origen === "kb", n.precio_consulta);
  n = await precio("u$s 100");
  check("precio 'u$s 100' (3 dígitos sin miles) -> fallback", n.precio_consulta === "$50.000" && n.precio_origen === "fallback", n.precio_consulta);
  n = await nuevo({ cita: CITA({ motivo_atencion: "Consulta Ortodoncia " }), gate: { suspender: false } });
  check("Gate sin columna precio_contenido (SQL viejo) -> fallback sin excepción", n.precio_consulta === "$50.000" && n.precio_origen === "fallback", JSON.stringify(n));
  n = await nuevo({ cita: CITA({ motivo_atencion: "Consulta Ortodoncia " }), gate: { error: "connect ECONNREFUSED" } });
  check("Gate caído (onError continue -> {error}) -> fallback sin excepción", n.precio_consulta === "$50.000" && n.precio_origen === "fallback" && n.message === BLOQUE_DRA, JSON.stringify(n));

  // 6) CAMINO MANUAL (webhook): 'Gate - Leer config' NO ejecutó -> $() tira -> fallback, sin romper
  let sinExcepcion = true;
  try { n = await nuevo({ cita: CITA({ motivo_atencion: "Consulta Ortodoncia " }), gate: SIN_GATE }); } catch (e) { sinExcepcion = false; n = { message: String(e) }; }
  check("manual sin Gate: no tira y usa el fallback", sinExcepcion && n.precio_consulta === "$50.000" && n.precio_origen === "fallback" && n.message === BLOQUE_DRA, JSON.stringify(n.message));
  n = await nuevo({ gate: SIN_GATE });
  v = await vivo({ gate: SIN_GATE });
  check("manual sin Gate, tratamiento: igual al vivo", igualAlVivo(n, v), difKeys(n, v));

  // 7) motivo_atencion: espacios, mayúsculas, 'No registra motivo', null, undefined. Regex ANCLADO al inicio
  //    (/^consulta\b/i, corrección 8/9): "Control post consulta" / "Consultar precio" NO son consulta (a un paciente en
  //    tratamiento no se le pide el pago de la consulta); "Primera Consulta" tampoco (falso negativo = genérico de hoy).
  const motivos = [
    [" Consulta Ortodoncia ", true, "Consulta Ortodoncia"],
    ["CONSULTA", true, "CONSULTA"],
    ["consulta ortodoncia", true, "consulta ortodoncia"],
    ["Consulta", true, "Consulta"],
    ["Consulta-Ortodoncia", true, "Consulta-Ortodoncia"],
    ["Primera Consulta", false, "Primera Consulta"],
    ["Consultar precio", false, "Consultar precio"],
    ["Control post consulta", false, "Control post consulta"],
    ["Consultas", false, "Consultas"],
    ["No registra motivo", false, "No registra motivo"],
    ["Devolución con escaneo ", false, "Devolución con escaneo"],
    ["", false, ""],
    [null, false, ""],
    [undefined, false, ""],
  ];
  for (const [m, esperado, motivoOut] of motivos) {
    const c = CITA(); if (m === undefined) delete c.motivo_atencion; else c.motivo_atencion = m;
    const r = await nuevo({ cita: c });
    check(`motivo ${JSON.stringify(m)} -> es_consulta ${esperado}, motivo_atencion ${JSON.stringify(motivoOut)}`, r.es_consulta === esperado && r.motivo_atencion === motivoOut && typeof r.es_consulta === "boolean" && typeof r.motivo_atencion === "string", JSON.stringify([r.es_consulta, r.motivo_atencion]));
  }
  // cita vacía ({}, el fallback del `?.json || {}`): el nodo VIVO tira (Invalid Date -> dias[NaN].charAt). No es un
  // camino real (Solo citas activas siempre trae fecha) y NO se cambia: solo se exige paridad con el vivo.
  const excepcionDe = async (fn, o) => { try { await correr(fn, o); return null; } catch (e) { return e.constructor.name + ": " + e.message; } };
  check("cita vacía ({}): mismo comportamiento que el vivo (ambos tiran TypeError, sin regresión)", (await excepcionDe(fnNuevo, { cita: {} })) === (await excepcionDe(fnVivo, { cita: {} })) && (await excepcionDe(fnVivo, { cita: {} })).startsWith("TypeError"), await excepcionDe(fnNuevo, { cita: {} }));

  // 8) género por terminación del primer nombre (Estimada / Estimado / Estimado/a) en el bloque de la Dra.
  for (const [nombre, trat, verbo] of [["Martina", "Estimada", "la esperamos"], ["Santiago", "Estimado", "lo esperamos"], ["Alexis", "Estimado/a", "le esperamos"], ["María José", "Estimada", "la esperamos"]]) {
    const r72 = await nuevo({ paciente: PACIENTE({ nombre }), cita: CITA({ motivo_atencion: "Consulta Ortodoncia " }) });
    const r24 = await nuevo({ paciente: PACIENTE({ nombre }), cita: CITA({ motivo_atencion: "Consulta Ortodoncia ", fecha: "2026-09-08" }) });
    check(`género ${nombre}: '${trat} ${nombre},' en el bloque 72h y '${verbo}' en el 24h`, r72.message.includes(`\n\n${trat} ${nombre},\nLe recordamos`) && r24.message.startsWith(`Hola, ${nombre} 😊 le recordamos que mañana ${verbo} a las 16:10 hs`), JSON.stringify([r72.message.slice(35, 60), r24.message.slice(0, 70)]));
  }

  // 9) celular: extranjero con '+' intacto, formatos argentinos, sin celular
  n = await nuevo({ paciente: PACIENTE({ celular: "+59173327830" }), cita: CITA({ motivo_atencion: "Consulta Ortodoncia " }) });
  check("celular +591… (Bolivia) queda tal cual, consulta", n.phone === "59173327830" && n.remoteJid === "59173327830@s.whatsapp.net" && n.message === BLOQUE_DRA, JSON.stringify([n.phone, n.remoteJid]));
  for (const cel of ["+59173327830", "3884176520", "543884176520", "5493884176520", "153884176520", "+54 9 388 417-6520", "388-4176520"]) {
    const a = await nuevo({ paciente: PACIENTE({ celular: cel }) });
    const b = await vivo({ paciente: PACIENTE({ celular: cel }) });
    check(`celular ${JSON.stringify(cel)}: phone/remoteJid igual al vivo (${b.phone})`, a.phone === b.phone && a.remoteJid === b.remoteJid && a.message === b.message, difKeys(a, b));
  }
  n = await nuevo({ paciente: PACIENTE({ celular: "" }), cita: CITA({ motivo_atencion: "Consulta Ortodoncia " }) });
  check("sin celular: phone/message vacíos (rama 'Tiene celular?' false) + es_consulta boolean", n.phone === "" && n.message === "" && n.es_consulta === true && n.motivo_atencion === "Consulta Ortodoncia", JSON.stringify(n));

  // 10) emparejamiento por $itemIndex (como hoy): con 3 citas, el ítem 1 toma la segunda
  const tres = [CITA({ id: 1, hora_inicio: "09:00:00" }), CITA({ id: 2, hora_inicio: "10:30:00", motivo_atencion: "Consulta Ortodoncia " }), CITA({ id: 3, hora_inicio: "11:00:00" })];
  n = await nuevo({ citas: tres, itemIndex: 1 });
  check("$itemIndex=1 -> cita 2 (10:30, consulta)", n.cita_id === 2 && n.hora === "10:30" && n.es_consulta === true, JSON.stringify(n));
  n = await nuevo({ citas: tres, itemIndex: 2 });
  v = await vivo({ citas: tres, itemIndex: 2 });
  check("$itemIndex=2 -> cita 3, igual al vivo", n.cita_id === 3 && igualAlVivo(n, v), difKeys(n, v));

  // 11) TEST_MODE: la línea literal existe (la busca apply_toggle_recordatorios_test_mode.py) y al prenderla redirige
  check("jsCode: conserva 'const TEST_MODE = false;' literal", NUEVO.includes("const TEST_MODE = false;") && (NUEVO.match(/const TEST_MODE = (true|false);/g) || []).length === 1, "");
  const fnTest = compilar(NUEVO.replace("const TEST_MODE = false;", "const TEST_MODE = true;"));
  n = await correr(fnTest, { cita: CITA({ motivo_atencion: "Consulta Ortodoncia " }) });
  check("TEST_MODE=true: va al TEST_PHONE con prefijo [TEST 72h] y el bloque de la Dra. abajo", n.phone === "5491161461034" && n.message === "[TEST 72h] Para: Martina (5493884176520)\n\n" + BLOQUE_DRA, JSON.stringify(n.message.slice(0, 60)));

  // 12) el jsCode nuevo contiene VERBATIM las líneas de los templates del nodo vivo (defensa en profundidad del byte a byte)
  const seccionVivo = VIVO.split("=== TEMPLATES OFICIALES ===")[1].split("const finalPhone")[0];
  const lineasTemplate = seccionVivo.split("\n").filter((l) => l.trim().startsWith('"'));
  const faltan = lineasTemplate.filter((l) => !NUEVO.includes(l));
  check(`jsCode: las ${lineasTemplate.length} líneas de template del nodo vivo están textuales en el nuevo`, lineasTemplate.length === 12 && faltan.length === 0, JSON.stringify(faltan));
  check("jsCode: el emparejamiento de la cita sigue siendo por $itemIndex y el paciente por nombre de nodo (no $input)", NUEVO.includes('$("Solo citas activas").all()[$itemIndex]') && NUEVO.includes("$('GET Paciente (celular)').item.json") && !/\$input\./.test(NUEVO), "");
  check("jsCode: la lectura del Gate está dentro de try/catch (R12)", /try \{[\s\S]*\$\('Gate - Leer config'\)\.first\(\)\.json[\s\S]*\} catch/.test(NUEVO), "");
  check("jsCode: es_consulta usa el regex ANCLADO /^consulta\\b/i (no el substring)", NUEVO.includes("const es_consulta = /^consulta\\b/i.test(motivo_atencion);") && !NUEVO.includes("= /consulta/i.test("), "");

  // 13) SQL del Gate: la columna `suspender` queda EXACTAMENTE igual; solo se suma precio_contenido
  const SQL_VIVO = "SELECT COALESCE(bool_or(\n    (NOT c.activo)\n    OR ((now() AT TIME ZONE 'America/Argentina/Jujuy')::date = ANY(c.dias_suspendidos))\n    OR (c.suspender_desde IS NOT NULL\n        AND (now() AT TIME ZONE 'America/Argentina/Jujuy')::date\n            BETWEEN c.suspender_desde AND c.suspender_hasta)\n  ), false) AS suspender\nFROM public.recordatorios_config c\nWHERE c.id = 1;";
  const SUBQ = " AS suspender,\n  (SELECT kb.contenido FROM public.knowledge_base kb WHERE kb.id = 21) AS precio_contenido\n";
  check("gate_leer_config.sql = SQL vivo + subconsulta precio_contenido (suspender intacto)", GATE_SQL.includes(SUBQ) && GATE_SQL.replace(SUBQ, " AS suspender\n") === SQL_VIVO, GATE_SQL);
  check("gate_leer_config.sql: solo lectura (sin INSERT/UPDATE/DELETE), id 21 y una sola sentencia", /^SELECT/.test(GATE_SQL) && !/insert|update|delete|drop|alter/i.test(GATE_SQL) && GATE_SQL.includes("kb.id = 21") && GATE_SQL.split(";").filter((s) => s.trim()).length === 1, "");

  // 14) salida: contrato de tipos para 'Insert recordatorios_enviados' (Postgres v2.6 valida contra la tabla viva)
  for (const c of [CITA(), CITA({ motivo_atencion: null }), CITA({ motivo_atencion: "Consulta Ortodoncia " }), CITA({ id: undefined, id_paciente: undefined })]) {
    const r = await nuevo({ cita: c });
    check(`salida: es_consulta boolean y motivo_atencion string (motivo ${JSON.stringify(c.motivo_atencion)})`, typeof r.es_consulta === "boolean" && typeof r.motivo_atencion === "string" && typeof r.precio_consulta === "string" && ["kb", "fallback"].includes(r.precio_origen), JSON.stringify(r));
  }
  n = await nuevo();
  check("salida: mismas keys que hoy + motivo_atencion, es_consulta, precio_consulta, precio_origen", JSON.stringify(Object.keys(n)) === JSON.stringify([...KEYS_VIVO, "motivo_atencion", "es_consulta", "precio_consulta", "precio_origen"]), Object.keys(n).join(","));

  console.log(`\n${fallos ? "FALLOS: " + fallos : "todo verde"}`);
  process.exit(fallos ? 1 : 0);
})().catch((e) => { console.error("EXCEPCION", e); process.exit(2); });
