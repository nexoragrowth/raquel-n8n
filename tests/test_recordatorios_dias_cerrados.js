// tests/test_recordatorios_dias_cerrados.js — corre el JS REAL del nodo "Fecha Mañana" del workflow de Recordatorios (7RqTApkvVavRmq3R)
// con node, mockeando el entorno de n8n y fijando "hoy". Fuente: recordatorios/fecha_manana.js (el apply lo embebe tal cual).
// El código VIVO al 2026-11-19 está congelado en recordatorios/fecha_manana.vivo_2026-11-19.js y se corre con los MISMOS mocks:
// sin días cerrados, el nuevo tiene que dar EXACTAMENTE lo mismo que el vivo, todos los días de 2026 y 2027.
// Correr: node tests/test_recordatorios_dias_cerrados.js
process.env.TZ = "America/Argentina/Jujuy"; // el nodo usa getDay/getDate locales: fijamos la zona (igual que test_recordatorio_consultas.js)

const fs = require("node:fs");
const path = require("node:path");
const ROOT = path.join(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const NUEVO = read("recordatorios/fecha_manana.js");
const VIVO = read("recordatorios/fecha_manana.vivo_2026-11-19.js");
const GATE = read("recordatorios/gate_dias_cerrados.sql");

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const compilar = (src) => new AsyncFunction("$input", "$", "$itemIndex", "$execution", "console", "Date", src);
const fnNuevo = compilar(NUEVO);
const fnVivo = compilar(VIVO);

const mkDate = (fixedIso) => {
  const FIXED = new Date(fixedIso).getTime();
  return class FixedDate extends Date {
    constructor(...a) { super(...(a.length ? a : [FIXED])); }
    static now() { return FIXED; }
  };
};
const NO_EJECUTADO = () => { throw new Error("Node hasn't been executed"); };

// gate: undefined = el Gate no corrió (camino manual) · objeto = su salida
async function objetivo(fn, isoUtc, gate, webhook) {
  const $ = (nombre) => {
    if (nombre === "Webhook Manual Recordatorios") return { all: webhook ? () => [{ json: { body: webhook } }] : NO_EJECUTADO };
    if (nombre === "Gate - Leer config") return { first: gate === undefined ? NO_EJECUTADO : () => ({ json: gate }) };
    throw new Error("nodo inesperado: " + nombre);
  };
  const r = await fn(undefined, $, 0, {}, console, mkDate(isoUtc));
  return r[0].json;
}
const corrida = (iso) => `${iso}T11:00:00Z`; // 08:00 en Jujuy, la hora real del cron

let ok = 0, fallos = 0;
const t = (nombre, cond, extra) => { if (cond) ok++; else { fallos++; console.log("  ✗", nombre, extra !== undefined ? JSON.stringify(extra).slice(0, 300) : ""); } };
const sumar = (iso, n) => { const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const dow = (iso) => new Date(iso + "T12:00:00Z").getUTCDay();

(async () => {
  // R1 — INVARIANZA: sin días cerrados, idéntico al vivo (todos los días de 2026-2027, con las 4 formas en que el Gate puede llegar)
  const gates = [undefined, {}, { suspender: false }, { suspender: false, dias_cerrados: [] }, { dias_cerrados: null }];
  let comparados = 0, distintos = [];
  for (let d = "2026-01-01"; d <= "2027-12-31"; d = sumar(d, 1)) {
    const esperado = await objetivo(fnVivo, corrida(d));
    for (const g of gates) {
      const n = await objetivo(fnNuevo, corrida(d), g);
      comparados++;
      if (JSON.stringify(n) !== JSON.stringify(esperado)) distintos.push([d, n.fecha_target, esperado.fecha_target]);
    }
  }
  t(`R1 sin días cerrados el nodo nuevo da EXACTAMENTE lo del vivo (${comparados} comparaciones)`, distintos.length === 0, distintos.slice(0, 3));

  // R2 — el caso real: lunes 23/11 feriado
  const feriado = { suspender: false, dias_cerrados: ["2026-11-23"] };
  const f = async (dia, g) => (await objetivo(fnNuevo, corrida(dia), g)).fecha_target;
  t("R2a hoy (jue 19/11) sin cerrados: apunta al lunes 23 (que no tiene turnos)", (await f("2026-11-19", {})) === "2026-11-23");
  t("R2b hoy (jue 19/11) con el lunes cerrado: recuerda el MARTES 24", (await f("2026-11-19", feriado)) === "2026-11-24");
  t("R2c vie 20/11 con el lunes cerrado: recuerda el miércoles 25 (el martes ya salió el jueves)", (await f("2026-11-20", feriado)) === "2026-11-25");
  t("R2d mar 24/11: jueves 26", (await f("2026-11-24", feriado)) === "2026-11-26");
  t("R2e mié 18/11 (antes del feriado) no cambia: viernes 20", (await f("2026-11-18", feriado)) === "2026-11-20");
  t("R2f mar 17/11 no cambia: jueves 19", (await f("2026-11-17", feriado)) === "2026-11-19");
  const ninguno = [];
  for (const d of ["2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20", "2026-11-24"]) if ((await f(d, feriado)) === "2026-11-23") ninguno.push(d);
  t("R2g el día cerrado nunca es objetivo de ninguna corrida", ninguno.length === 0, ninguno);

  // R3 — puente + feriado seguidos (lun 7 y mar 8 de diciembre)
  const puente = { dias_cerrados: ["2026-12-07", "2026-12-08"] };
  t("R3a mié 2/12 → vie 4/12", (await f("2026-12-02", puente)) === "2026-12-04");
  t("R3b jue 3/12 → miércoles 9/12", (await f("2026-12-03", puente)) === "2026-12-09");
  t("R3c vie 4/12 → jueves 10/12", (await f("2026-12-04", puente)) === "2026-12-10");

  // R4 — PROPIEDAD con una definición independiente: la corrida del día hábil R[i] recuerda el día hábil R[i+2]. Todos los días hábiles quedan
  // recordados exactamente una vez (sin saltos ni duplicados), con varios conjuntos de días cerrados (incluye puentes y rangos de vacaciones).
  const conjuntos = [
    [], ["2026-11-23"], ["2026-12-07", "2026-12-08"], ["2026-12-24", "2026-12-25", "2026-12-31", "2027-01-01"],
    ["2027-01-04", "2027-01-05", "2027-01-06", "2027-01-07", "2027-01-08"], ["2026-11-20", "2026-11-23", "2026-11-24"], ["2027-02-15", "2027-02-16"],
  ];
  for (const cerr of conjuntos) {
    const cerrado = new Set(cerr);
    const habiles = [];
    for (let d = "2026-11-02"; d <= "2027-03-31"; d = sumar(d, 1)) if (dow(d) >= 1 && dow(d) <= 5 && !cerrado.has(d)) habiles.push(d);
    const malos = [];
    for (let i = 0; i + 2 < habiles.length; i++) {
      const got = (await objetivo(fnNuevo, corrida(habiles[i]), { dias_cerrados: cerr })).fecha_target;
      if (got !== habiles[i + 2]) malos.push([habiles[i], got, habiles[i + 2]]);
    }
    t(`R4 con cerrados [${cerr.join(", ") || "ninguno"}]: cada corrida recuerda el día hábil de 2 lugares después (${habiles.length - 2} corridas)`, malos.length === 0, malos.slice(0, 3));
  }

  // R5 — entradas raras del Gate no rompen ni inventan días cerrados
  const raro = await f("2026-11-19", { dias_cerrados: [null, "x", 20261123, "2026-13-45x", "", undefined] });
  t("R5a valores inválidos se ignoran (20261123 no es una fecha ISO)", raro === "2026-11-23", raro);
  t("R5b una fecha con hora (ISO completa) se toma por su día", (await f("2026-11-19", { dias_cerrados: ["2026-11-23T00:00:00.000Z"] })) === "2026-11-24");
  t("R5c dias_cerrados que no es lista se ignora", (await f("2026-11-19", { dias_cerrados: "2026-11-23" })) === "2026-11-23");

  // R6 — el camino manual (webhook "Adelantar") sigue igual: usa la fecha pedida, no mira los días cerrados
  const m = await objetivo(fnNuevo, corrida("2026-11-19"), undefined, { fecha_target: "2026-11-24", id_paciente_filter: [7, 9] });
  t("R6a webhook manual: fecha pedida + tipo manual_override + filtro de pacientes", m.fecha_target === "2026-11-24" && m.tipo_recordatorio === "manual_override" && JSON.stringify(m.id_paciente_filter) === "[7,9]", m);
  const mv = await objetivo(fnVivo, corrida("2026-11-19"), undefined, { fecha_target: "2026-11-24", id_paciente_filter: [7, 9] });
  t("R6b idéntico al vivo", JSON.stringify(m) === JSON.stringify(mv));
  t("R6c tipo de la corrida automática no cambia", (await objetivo(fnNuevo, corrida("2026-11-19"), {})).tipo_recordatorio === "48h_habiles");

  // R7 — SQL del Gate (revisión estática; la prueba real contra Postgres la hace apply_recordatorios_dias_cerrados.py antes de tocar nada)
  t("R7a el Gate saltea la corrida de un día cerrado", /now\(\) AT TIME ZONE 'America\/Argentina\/Jujuy'\)::date = ANY\(c\.dias_cerrados\)/.test(GATE));
  t("R7b entrega la lista como TEXTO yyyy-mm-dd (sin corrimiento de zona horaria)", /to_char\(d, 'YYYY-MM-DD'\)/.test(GATE) && /AS dias_cerrados/.test(GATE));
  t("R7c conserva las suspensiones que ya existían (activo, días sueltos, rango)", /NOT c\.activo/.test(GATE) && /ANY\(c\.dias_suspendidos\)/.test(GATE) && /suspender_desde/.test(GATE));

  console.log(`\n${ok}/${ok + fallos} ${fallos === 0 ? "TODO OK" : "CON FALLOS"}`);
  process.exit(fallos === 0 ? 0 : 1);
})();
