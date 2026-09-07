// tests/test_turnos_formato.js — corre el JS REAL de los nodos que arman el bloque de turnos que pidió la
// Dra. Raquel el 2026-09-07: turnos/format_slots.js ("Format Slots"), turnos/acumular_slots.js ("Acumular
// P1/P2/P3"), turnos/validar_fecha.js ("Validar fecha"), turnos/output_error.js y turnos/split_en_mensajes.js
// ("Split en Mensajes" del v6), mockeando el entorno de n8n ($input, $()). Mismo harness que
// tests/test_media_nodos.js y tests/test_triaje_nodos.js.
// Fuente única: si alguien edita turnos/*.js, el test corre el código editado (y el apply lo embebe tal cual).
//
// Correr: node tests/test_turnos_formato.js
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

const FORMAT = read("turnos/format_slots.js");
const ACUMULAR = read("turnos/acumular_slots.js");
const VALIDAR = read("turnos/validar_fecha.js");
const OUTPUT_ERROR = read("turnos/output_error.js");
const SPLIT = read("turnos/split_en_mensajes.js");
// Los parches del Sub-WF CancelarReprogramar son FRAGMENTOS del jsCode vivo: se corren con las variables
// que el nodo ya tiene en scope, igual que cuando el script los embebe.
const STEP5 = read("turnos/parches/canrep_step5_reprogramar.despues.js");
const STEP0B_LOTE = read("turnos/parches/canrep_step0b_lote.despues.js");

const fnFormat = new AsyncFunction("$input", "$", FORMAT);
const fnValidar = new AsyncFunction("$input", "$", VALIDAR);
const fnOutputError = new AsyncFunction("$input", "$", OUTPUT_ERROR);
const fnSplit = new AsyncFunction("$input", "$", SPLIT);
const fnAcumular = (previo) => new AsyncFunction("$input", "$", ACUMULAR.replace("__NODO_PREVIO__", previo));
const fnStep5 = new AsyncFunction("prev", "intent", STEP5 + "\nreturn null;");
const fnStep0bLote = new AsyncFunction("trigger", "lastBotMsg", "historyPairs",
  STEP0B_LOTE + "\nreturn { oferta_bloque, oferta_siguiente_desde, bloques_ofrecidos, is_frustrated };");

let fallos = 0;
const check = (nombre, cond, detalle) => {
  console.log(`${cond ? "OK  " : "FAIL"} ${nombre}${cond ? "" : " — " + detalle}`);
  if (!cond) fallos++;
};

// ---------------------------------------------------------------- helpers de fixtures
const aIso = (dmy) => { const m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(dmy); return m[3] + "-" + m[2] + "-" + m[1]; };
// "24/09/2026 08:00" -> slot ya acumulado (lo que deja "Acumular")
const S = (s) => { const [fecha, hora] = s.split(" "); return { fecha, hora_inicio: hora, iso: aIso(fecha) }; };
// lo que devuelve la agenda (dd/mm/yyyy + los campos que trae de verdad)
const API = (s, extra = {}) => {
  const [fecha, hora] = s.split(" ");
  return { id_paciente: 0, nombre_paciente: "", hora_inicio: hora, hora_fin: hora, duracion: 40,
           id_dentista: 1, nombre_dentista: " Rodríguez  Raquel", fecha, id_recurso: 1, ...extra };
};
const mkInput = (json) => ({ first: () => ({ json }), all: () => [{ json }] });
const mkDollar = (nodos) => (nombre) => {
  if (!(nombre in nodos)) throw new Error(`nodo no ejecutado: ${nombre}`); // igual que $() en n8n
  return { first: () => ({ json: nodos[nombre] }), item: { json: nodos[nombre] }, isExecuted: true };
};
const formatear = async (json) => (await fnFormat(mkInput(json), mkDollar({})))[0].json;

// Agenda REAL de la Dra. bajada por GET el 2026-09-07 (páginas 1 y 2 del cursor: 19 slots libres).
// Congelada acá a propósito: el test verifica el FORMATO, no la agenda del día.
const AGENDA_REAL = [
  "24/09/2026 08:00", "24/09/2026 08:40", "24/09/2026 09:20", "24/09/2026 10:00",
  "29/09/2026 08:40", "29/09/2026 09:20", "29/09/2026 10:00", "29/09/2026 10:40",
  "30/09/2026 16:20",
  "01/10/2026 09:20", "01/10/2026 10:00", "01/10/2026 10:40",
  "02/10/2026 08:30", "02/10/2026 09:10", "02/10/2026 09:50", "02/10/2026 10:30",
  "05/10/2026 15:00", "05/10/2026 15:40", "05/10/2026 18:20",
].map(S);

// El formato EXACTO que escribió la Dra. por WhatsApp (encabezado, dos secciones, línea en blanco, cierre).
const BLOQUE_ESPERADO = [
  "Tenemos los próximos turnos disponibles:",
  "Por la mañana:",
  "* Jueves 24 de septiembre 8:00 , 8:40",
  "* Martes 29 de septiembre 8:40 , 9:20",
  "",
  "Por la tarde:",
  "* Miércoles 30 de septiembre 16:20",
  "* Lunes 5 de octubre 15:00 , 15:40",
  "",
  "Le sirve alguno?",
].join("\n");

(async () => {
  // ============================================================ 1) FORMAT SLOTS — el bloque de la Dra.
  {
    const j = await formatear({ slots: AGENDA_REAL, errores: [], dias_escaneados: 28, paginas: 2 });
    check("bloque exacto 2+2 con la agenda real de hoy", j.bloque === BLOQUE_ESPERADO,
      JSON.stringify(j.bloque));
    check("hay_turnos + totales + siguiente lote",
      j.hay_turnos === true && j.total_manana === 15 && j.total_tarde === 4 && j.siguiente_desde === "2026-09-30",
      JSON.stringify({ m: j.total_manana, t: j.total_tarde, sig: j.siguiente_desde }));
    // El lote 2 arranca al dia siguiente del ultimo dia de la franja que termina ANTES (29/09, mañana), no
    // del ultimo de todos (05/10, tarde): con el maximo se salteaban las mañanas del 01/10 y 02/10, que
    // estaban en los slots acumulados y el paciente no vio nunca.
    check("siguiente lote: dia siguiente al MINIMO de las dos franjas (no se saltea nada mas proximo)",
      j.siguiente_desde === "2026-09-30" && AGENDA_REAL.some((s) => s.iso === "2026-10-01"),
      j.siguiente_desde);
    check("dos horarios del MISMO día en una sola línea, separados por ' , '",
      j.bloque.includes("* Jueves 24 de septiembre 8:00 , 8:40")
      && j.bloque.split("\n").filter((l) => l.startsWith("* ")).length === 4, j.bloque);
    check("hora sin cero adelante y SIN 'hs' adentro del bloque",
      !/\bhs\b/.test(j.bloque) && j.bloque.includes(" 8:00 ") && !j.bloque.includes("08:00"), j.bloque);
    check("mes en minúscula, día de la semana capitalizado",
      j.bloque.includes("de septiembre") && !j.bloque.includes("de Septiembre")
      && j.bloque.includes("* Jueves ") && j.bloque.includes("* Miércoles "), j.bloque);
    check("línea en blanco entre secciones y antes del cierre",
      j.bloque.includes("\n\nPor la tarde:") && j.bloque.endsWith("\n\nLe sirve alguno?"), JSON.stringify(j.bloque));
    check("el bloque NO trae '---' (partiría el mensaje en Split en Mensajes)", !j.bloque.includes("---"), j.bloque);
    check("`resultado` manda copiar tal cual y prohíbe preguntar franja/fecha",
      /Pegalo TAL CUAL|Pegalo tal cual/.test(j.resultado)
      && /PROHIBIDO preguntarle al paciente que dia, que fecha o que franja/.test(j.resultado)
      && j.resultado.trimEnd().endsWith(j.bloque), j.resultado.slice(0, 200));
    check("`resultado` termina con el bloque (no hay marca de cierre que se pueda copiar)",
      j.resultado.endsWith(BLOQUE_ESPERADO), JSON.stringify(j.resultado.slice(-40)));
    check("`resultado` dice cómo pedir el siguiente lote", j.resultado.includes("desde=2026-09-30"), j.resultado);
  }

  // ---- una sola franja: la sección entera se omite, encabezado incluido
  {
    const soloManana = await formatear({ slots: ["13/10/2026 08:00", "13/10/2026 08:40", "15/10/2026 09:20"].map(S) });
    check("solo mañana: no aparece la sección 'Por la tarde'",
      soloManana.bloque.includes("Por la mañana:") && !soloManana.bloque.includes("Por la tarde"),
      soloManana.bloque);
    check("solo mañana: el bloque igual cierra con 'Le sirve alguno?'",
      soloManana.bloque.endsWith("\n\nLe sirve alguno?"), JSON.stringify(soloManana.bloque));
    check("solo mañana: el `resultado` avisa que no hay tarde y prohíbe inventarla",
      /no hay ningun turno de tarde/.test(soloManana.resultado), soloManana.resultado);

    const soloTarde = await formatear({ slots: ["05/10/2026 15:00", "07/10/2026 17:30", "07/10/2026 18:10"].map(S) });
    check("solo tarde: no aparece la sección 'Por la mañana'",
      soloTarde.bloque.includes("Por la tarde:") && !soloTarde.bloque.includes("Por la mañana"), soloTarde.bloque);
    check("solo tarde: dos días, el segundo agrupa dos horarios",
      soloTarde.bloque.includes("* Lunes 5 de octubre 15:00")
      && soloTarde.bloque.includes("* Miércoles 7 de octubre 17:30 , 18:10"), soloTarde.bloque);
    check("solo tarde: el `resultado` avisa que no hay mañana",
      /no hay ningun turno de mañana/.test(soloTarde.resultado), soloTarde.resultado);
  }

  // ---- sin turnos / error técnico
  {
    const vacio = await formatear({ slots: [], errores: [] });
    check("ningún slot: bloque vacío, hay_turnos false y hay que escalar",
      vacio.bloque === "" && vacio.hay_turnos === false
      && /SIN TURNOS/.test(vacio.resultado) && /escalar_a_secretaria/.test(vacio.resultado), vacio.resultado);
    check("ningún slot: NO le pide fecha ni franja al paciente",
      !/que dia|que franja|fecha concreta/i.test(vacio.resultado.replace(/NO le pregunte[^.]*/i, "")),
      vacio.resultado);

    const red = await formatear({ slots: [], errores: ["pagina 1: la agenda no respondio"] });
    check("error de red sin ningún slot: ERROR_TECNICO y prohibido decir que no hay turnos",
      red.error_tecnico === true && /ERROR_TECNICO/.test(red.resultado)
      && /NO afirmes que no hay turnos/.test(red.resultado), red.resultado);

    const redParcial = await formatear({ slots: ["24/09/2026 08:00", "05/10/2026 15:00"].map(S),
                                         errores: ["pagina 3: la agenda no respondio"] });
    check("error de red con slots ya juntados: igual se ofrece lo que hay",
      redParcial.error_tecnico === false && redParcial.bloque.includes("* Jueves 24 de septiembre 8:00")
      && redParcial.bloque.includes("* Lunes 5 de octubre 15:00"), redParcial.bloque);
  }

  // ---- orden, mes y año, día de la semana
  {
    const desordenados = ["05/10/2026 15:40", "24/09/2026 08:40", "05/10/2026 15:00", "24/09/2026 08:00",
                          "29/09/2026 08:40", "29/09/2026 09:20", "30/09/2026 16:20"].map(S);
    const j = await formatear({ slots: desordenados });
    check("slots desordenados: el bloque sale ordenado por fecha y hora",
      j.bloque === [
        "Tenemos los próximos turnos disponibles:", "Por la mañana:",
        "* Jueves 24 de septiembre 8:00 , 8:40", "* Martes 29 de septiembre 8:40 , 9:20", "",
        "Por la tarde:", "* Miércoles 30 de septiembre 16:20", "* Lunes 5 de octubre 15:00 , 15:40", "",
        "Le sirve alguno?"].join("\n"), j.bloque);

    const finDeAnio = await formatear({ slots: ["31/12/2026 08:00", "01/01/2027 08:30", "28/12/2026 15:00",
                                                "04/01/2027 17:00"].map(S) });
    check("cambio de mes y de año: diciembre -> enero, día de la semana real",
      finDeAnio.bloque.includes("* Jueves 31 de diciembre 8:00")
      && finDeAnio.bloque.includes("* Viernes 1 de enero 8:30")
      && finDeAnio.bloque.includes("* Lunes 28 de diciembre 15:00")
      && finDeAnio.bloque.includes("* Lunes 4 de enero 17:00"), finDeAnio.bloque);
    check("siguiente lote cruzando el año", finDeAnio.siguiente_desde === "2027-01-02", finDeAnio.siguiente_desde);

    // fechas verificadas con el calendario real (2026 y el bisiesto 2028)
    const conocidas = { "24/09/2026": "Jueves", "29/09/2026": "Martes", "30/09/2026": "Miércoles",
                        "01/10/2026": "Jueves", "02/10/2026": "Viernes", "05/10/2026": "Lunes",
                        "26/10/2026": "Lunes", "02/11/2026": "Lunes", "31/12/2026": "Jueves",
                        "01/01/2027": "Viernes", "29/02/2028": "Martes" };
    let malos = [];
    for (const [fecha, dia] of Object.entries(conocidas)) {
      const b = (await formatear({ slots: [S(fecha + " 08:00")] })).bloque;
      if (!b.includes("* " + dia + " ")) malos.push(fecha + " != " + dia + " -> " + b.split("\n")[2]);
    }
    check("día de la semana correcto contra 11 fechas conocidas (incluye bisiesto 2028)", malos.length === 0,
      malos.join(" | "));
  }

  // ---- el nombre del sistema de gestión NO puede aparecer NUNCA
  {
    const casos = [
      { slots: AGENDA_REAL, errores: [] },
      { slots: [], errores: [] },
      { slots: [], errores: ["pagina 1: la agenda no respondio"] },
      { slots: ["13/10/2026 08:00"].map(S) },
      { slots: ["05/10/2026 15:00"].map(S) },
    ];
    let sucio = [];
    for (const c of casos) {
      const j = JSON.stringify(await formatear(c));
      if (/dentalink/i.test(j)) sucio.push(JSON.stringify(c).slice(0, 60));
    }
    const err = await fnOutputError(mkInput({}), mkDollar({ "Validar fecha": { fecha: "2026-09-07" } }));
    if (/dentalink/i.test(JSON.stringify(err))) sucio.push("Output Error");
    check("ningún camino menciona el sistema de gestión ('Dentalink'/'dentalink')", sucio.length === 0,
      sucio.join(" | "));
    check("Output Error ya no pide la fecha al paciente",
      !/OBLIGATORIO/.test(err[0].json.resultado) && /NO le pidas al paciente una fecha/.test(err[0].json.resultado),
      err[0].json.resultado);
  }

  // ============================================================ 2) ACUMULAR — paginado por cursor
  const VF = { "Validar fecha": { fecha: "2026-09-07", hoy: "2026-09-07", valida: true } };
  const correrAcum = async (previo, respuesta, prevJson) => {
    const nodos = { ...VF };
    if (previo) nodos[previo] = prevJson;
    return (await fnAcumular(previo)(mkInput(respuesta), mkDollar(nodos)))[0].json;
  };
  {
    const pag1 = { data: ["24/09/2026 08:00", "24/09/2026 08:40", "24/09/2026 09:20", "24/09/2026 10:00",
                          "29/09/2026 08:40", "29/09/2026 09:20", "29/09/2026 10:00", "29/09/2026 10:40",
                          "30/09/2026 16:20", "01/10/2026 09:20"].map((s) => API(s)) };
    const p1 = await correrAcum("", pag1, null);
    check("P1: parsea los 10 slots, ordena y arma el cursor con el último",
      p1.slots.length === 10 && p1.cursor === "2026-10-01" && p1.paginas === 1, JSON.stringify({ n: p1.slots.length, c: p1.cursor }));
    check("P1: 9 de mañana / 1 de tarde -> falta tarde -> sigue paginando",
      p1.total_manana === 9 && p1.total_tarde === 1 && p1.dias_tarde === 1 && p1.completo === false && p1.seguir === true,
      JSON.stringify(p1));
    check("P1: dias_escaneados se mide desde la fecha de búsqueda", p1.dias_escaneados === 24, String(p1.dias_escaneados));

    // página 2: la agenda repite los slots del último día (fecha:{eq:X} se comporta como >= X)
    const pag2 = { data: ["01/10/2026 09:20", "01/10/2026 10:00", "01/10/2026 10:40", "02/10/2026 08:30",
                          "02/10/2026 09:10", "02/10/2026 09:50", "02/10/2026 10:30", "05/10/2026 15:00",
                          "05/10/2026 15:40", "05/10/2026 18:20"].map((s) => API(s)) };
    const p2 = await correrAcum("Acumular P1", pag2, p1);
    check("P2: deduplica por (fecha, hora_inicio) — el slot repetido no se suma dos veces",
      p2.slots.length === 19 && p2.slots.filter((s) => s.fecha === "01/10/2026" && s.hora_inicio === "09:20").length === 1,
      String(p2.slots.length));
    check("P2: 2 días con mañana y 2 con tarde -> completo -> CORTA (no llama la página 3)",
      p2.dias_manana === 4 && p2.dias_tarde === 2 && p2.completo === true && p2.seguir === false, JSON.stringify(p2));

    // la misma página otra vez: no aporta nada nuevo -> no se gasta otra llamada
    const p2bis = await correrAcum("Acumular P1", pag1, { ...p1, completo: false });
    check("página sin nada nuevo: seguir=false (no se repite la llamada al pedo)",
      p2bis.seguir === false && p2bis.slots.length === 10, JSON.stringify({ s: p2bis.seguir, n: p2bis.slots.length }));

    // error de red (continueOnFail deja {error})
    const pErr = await correrAcum("Acumular P1", { error: { message: "ETIMEDOUT" } }, p1);
    check("error de red: se sigue con lo que hay, se registra y se deja de paginar",
      pErr.slots.length === 10 && pErr.errores.length === 1 && pErr.seguir === false, JSON.stringify(pErr.errores));

    // horizonte agotado
    const lejos = await correrAcum("", { data: ["20/03/2027 08:00", "21/03/2027 08:40"].map((s) => API(s)) }, null);
    check("horizonte agotado (>120 días): no se pagina más aunque falte la tarde",
      lejos.dias_escaneados > 120 && lejos.completo === false && lejos.seguir === false,
      JSON.stringify({ d: lejos.dias_escaneados, s: lejos.seguir }));

    // tope de páginas: 6, no 3. Con 3 no quedaba margen — medido el 07/09 contra la agenda real, juntar 2
    // mañanas + 2 tardes YA consume 3 páginas arrancando en 5 de las 6 fechas probadas, y al agotarse el
    // bloque sale sin la sección "Por la tarde" (la captura #2 que motivó el pedido de la Dra.).
    check("MAX_PAGINAS declarado en el jsCode = 6", /const MAX_PAGINAS = 6;/.test(ACUMULAR), "no dice 6");
    const soloManana10 = (dia) => ({ data: [API(dia + " 08:00"), API(dia + " 08:40")] });
    let prevPag = null, pagN = 0;
    for (const dia of ["08/10/2026", "13/10/2026", "15/10/2026", "20/10/2026", "22/10/2026", "27/10/2026"]) {
      prevPag = await correrAcum(pagN === 0 ? "" : "Acumular P" + pagN, soloManana10(dia), prevPag);
      pagN++;
      if (pagN < 6) {
        check("P" + pagN + " sin tarde: sigue paginando (antes se cortaba en la 3)",
          prevPag.seguir === true && prevPag.paginas === pagN, JSON.stringify({ p: prevPag.paginas, s: prevPag.seguir }));
      }
    }
    check("P6 es la última: seguir=false aunque falte la tarde (MAX_PAGINAS=6)",
      prevPag.paginas === 6 && prevPag.seguir === false && prevPag.dias_tarde === 0,
      JSON.stringify({ p: prevPag.paginas, s: prevPag.seguir }));

    // orden por string: la agenda hoy devuelve '08:00', pero si alguna vez devolviera '8:00' el bloque
    // salía desordenado ('10:00 , 8:00'). Se normaliza a HH:MM en la puerta de entrada.
    const sinCero = await correrAcum("", { data: [API("24/09/2026 10:00"), API("24/09/2026 8:00")] }, null);
    check("horas sin cero adelante: se normalizan a HH:MM y quedan ordenadas",
      sinCero.slots.map((x) => x.hora_inicio).join(",") === "08:00,10:00", JSON.stringify(sinCero.slots));
    const bloqueOrden = await formatear({ slots: sinCero.slots });
    check("y el bloque sale ordenado (8:00 antes que 10:00)",
      bloqueOrden.bloque.includes("* Jueves 24 de septiembre 8:00 , 10:00"), bloqueOrden.bloque);

    // basura y ocupados
    const sucio = await correrAcum("", { data: [API("24/09/2026 08:00"), API("2026-09-24 08:40"),
                                                API("29/09/2026 08:40", { id_paciente: 123, nombre_paciente: "X" }),
                                                { fecha: "30/09/2026" }] }, null);
    check("descarta fechas mal formadas, slots ocupados y filas sin hora",
      sucio.slots.length === 1 && sucio.slots[0].hora_inicio === "08:00", JSON.stringify(sucio.slots));

    const raro = await correrAcum("", { data: { data: [API("24/09/2026 08:00")] } }, null);
    check("tolera la respuesta anidada {data:{data:[...]}}", raro.slots.length === 1, JSON.stringify(raro.slots));
    const nada = await correrAcum("", {}, null);
    check("respuesta vacía: 0 slots, sin explotar", nada.slots.length === 0 && nada.seguir === false, JSON.stringify(nada));
  }

  // ============================================================ 3) VALIDAR FECHA — ya no exige nada
  {
    const hoy = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Jujuy" }).format(new Date());
    const correr = async (json) => (await fnValidar(mkInput(json), mkDollar({})))[0].json;
    const sinNada = await correr({});
    check("sin parámetros: busca desde HOY (Jujuy) y valida=true",
      sinNada.fecha === hoy && sinNada.valida === true && sinNada.parametro_ignorado === false, JSON.stringify(sinNada));
    const pasada = await correr({ fecha: "2020-01-01" });
    check("fecha pasada: se ignora y se busca desde hoy (NO se le pide fecha al paciente)",
      pasada.fecha === hoy && pasada.valida === true && pasada.parametro_ignorado === true, JSON.stringify(pasada));
    const basura = await correr({ fecha: "el jueves" });
    check("fecha basura: se ignora y se busca desde hoy", basura.fecha === hoy && basura.parametro_ignorado === true,
      JSON.stringify(basura));
    const lejana = await correr({ fecha: "2030-05-05" });
    check("fecha a más de 12 meses: se ignora", lejana.fecha === hoy && lejana.parametro_ignorado === true,
      JSON.stringify(lejana));
    const futura = "2026-12-30" > hoy ? "2026-12-30" : "2030-01-01";
    const conDesde = await correr({ desde: futura, fecha: "2026-09-08" });
    check("`desde` gana sobre `fecha` y se respeta si es futura y está dentro del año",
      conDesde.fecha === (futura === "2026-12-30" ? "2026-12-30" : hoy), JSON.stringify(conDesde));
    const vacios = await correr({ fecha: "", desde: "" });
    check("strings vacíos: hoy, sin marcar parámetro ignorado",
      vacios.fecha === hoy && vacios.parametro_ignorado === false, JSON.stringify(vacios));
    check("ya no lee franja ni hora_minima (nunca llegaron)",
      !("franja" in vacios) && !("hora_minima" in vacios), JSON.stringify(vacios));
  }

  // ============================================================ 4) SPLIT EN MENSAJES — el bloque no se rompe
  {
    const PMF = { "Preparar Mensaje Final": { remoteJid: "549116@s.whatsapp.net", phone: "5491161461034" } };
    const correrSplit = async (formateado, original) =>
      (await fnSplit(mkInput({ output: formateado }), mkDollar({ ...PMF, "Banlist Validator": { output: original } })))
        .map((i) => i.json.message);

    const iguales = await correrSplit(BLOQUE_ESPERADO, BLOQUE_ESPERADO);
    check("bypass del Formatting Agent: UN solo mensaje con el bloque intacto (líneas en blanco incluidas)",
      iguales.length === 1 && iguales[0] === BLOQUE_ESPERADO, JSON.stringify(iguales));

    const reescrito = BLOQUE_ESPERADO.replace(/8:00/g, "8:00 hs").replace("septiembre", "Septiembre");
    const rescatado = await correrSplit(reescrito, BLOQUE_ESPERADO);
    check("si el LLM igual lo reescribe: gana el ORIGINAL (guard determinístico)",
      rescatado.length === 1 && rescatado[0] === BLOQUE_ESPERADO, JSON.stringify(rescatado));

    const conAlias = BLOQUE_ESPERADO + "\n---\nAlias: dra.raquel.aurea\nTitular: Laura Raquel Rodriguez";
    const partes = await correrSplit(conAlias, conAlias);
    check("bloque + sidecar de alias: 2 mensajes y el primero es el bloque completo",
      partes.length === 2 && partes[0] === BLOQUE_ESPERADO && partes[1].startsWith("Alias:"), JSON.stringify(partes));

    const cbu = await correrSplit("Le paso los datos", "Le paso los datos\n---\nCBU: 000000");
    check("el guard viejo del CBU sigue funcionando", cbu.join(" | ").includes("CBU: 000000"), JSON.stringify(cbu));

    const normal = await correrSplit("Listo, le reservo el turno.", "Perfecto, le reservo el turno.");
    check("texto sin bloque: sigue mandando el formateado del LLM",
      normal.length === 1 && normal[0] === "Listo, le reservo el turno.", JSON.stringify(normal));
  }

  // ============================================================ 4.b) FUGA DEL TEXTO INTERNO DE LA TOOL
  // `resultado` es UN solo string: instruccion para el agente + centinela + bloque. Si el agente lo pega
  // entero, el paciente lee las tripas del bot — y como ese texto contiene "turnos disponibles:", las dos
  // capas nuevas (el bypass del IF y el guard del bloque) lo dejarian pasar INTACTO. Esta es la red.
  {
    const PMF = { "Preparar Mensaje Final": { remoteJid: "549116@s.whatsapp.net", phone: "5491161461034" } };
    const correrSplit = async (formateado, original) =>
      (await fnSplit(mkInput({ output: formateado }), mkDollar({ ...PMF, "Banlist Validator": { output: original } })))
        .map((i) => i.json.message);

    const fuga = (await formatear({ slots: AGENDA_REAL })).resultado;   // el `resultado` CRUDO de la tool
    check("el `resultado` crudo trae el centinela y la instrucción interna",
      fuga.includes("MENSAJE EXACTO PARA EL PACIENTE") && fuga.includes("PROHIBIDO preguntarle al paciente"),
      fuga.slice(0, 80));
    const salida = await correrSplit(fuga, fuga);
    check("si el agente pega el `resultado` ENTERO, al paciente le llega SOLO el bloque",
      salida.length === 1 && salida[0] === BLOQUE_ESPERADO, JSON.stringify(salida));
    check("nada de la instrucción interna sobrevive al guard",
      !salida.join("\n").includes("INSTRUCCION") && !salida.join("\n").includes("MENSAJE EXACTO")
      && !salida.join("\n").includes("PROHIBIDO"), JSON.stringify(salida));

    // fuga con una linea propia del agente adelante: se recorta igual desde el centinela
    const conPreambulo = await correrSplit("Perfecto, le busco.\n" + fuga, "Perfecto, le busco.\n" + fuga);
    check("fuga con preámbulo del agente: igual sale sólo el bloque",
      conPreambulo.length === 1 && conPreambulo[0] === BLOQUE_ESPERADO, JSON.stringify(conPreambulo));

    // caso degenerado (la tool no lo puede producir): centinela sin nada abajo -> no se manda vacío
    const truncado = "INSTRUCCION (no la copies): pegalo tal cual.\nMENSAJE EXACTO PARA EL PACIENTE:";
    const degenerado = await correrSplit(truncado, truncado);
    check("centinela sin bloque abajo: NO se manda un mensaje vacío",
      degenerado.length === 1 && degenerado[0].trim().length > 0, JSON.stringify(degenerado));

    // el preámbulo legítimo (una línea del agente antes del bloque) NO se recorta
    const legit = "Atendemos martes, jueves y viernes por la mañana.\n" + BLOQUE_ESPERADO;
    const conLinea = await correrSplit(legit, legit);
    check("una línea legítima del agente antes del bloque se conserva",
      conLinea.length === 1 && conLinea[0] === legit, JSON.stringify(conLinea));
  }

  // ============================================================ 4.c) CANREP — el lote no se repite ni se
  // ofrece para siempre (Step 0b calcula el lote ofrecido, Step 5 decide)
  {
    const HOY = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Argentina/Jujuy" }).format(new Date());
    const ANIO = Number(HOY.slice(0, 4));
    // un bloque "de este año" para que el parser de Step 0b (que no ve el año) lo ubique en el futuro
    const dd = (iso) => Number(iso.slice(8, 10));
    const BLOQUE_VIVO = [
      "Tenemos los próximos turnos disponibles:", "Por la mañana:",
      "* Jueves 24 de septiembre 8:00 , 8:40", "* Martes 29 de septiembre 8:40 , 9:20", "",
      "Por la tarde:", "* Miércoles 30 de septiembre 16:20", "* Lunes 5 de octubre 15:00 , 15:40", "",
      "Le sirve alguno?"].join("\n");
    const hist = (n) => Array.from({ length: n }, () => ({ role: "bot", content: BLOQUE_VIVO.slice(0, 300) }));

    const lote1 = await fnStep0bLote({ text: "ninguno me sirve" }, "Soy Asiri. " + BLOQUE_VIVO, hist(1));
    const esperado = (dd("2026-09-29") && (ANIO + "-09-30") >= HOY) ? ANIO + "-09-30" : (ANIO + 1) + "-09-30";
    check("Step 0b: saca del último mensaje el bloque y desde cuándo pedir el lote siguiente",
      lote1.oferta_bloque.includes("turnos disponibles:") && lote1.oferta_siguiente_desde === esperado,
      JSON.stringify({ sig: lote1.oferta_siguiente_desde, esp: esperado }));
    check("Step 0b: cuenta los bloques ya ofrecidos", lote1.bloques_ofrecidos === 1, String(lote1.bloques_ofrecidos));
    const sinBloque = await fnStep0bLote({ text: "hola" }, "Le confirmo el turno.", []);
    check("Step 0b: sin bloque en el último mensaje no inventa nada",
      sinBloque.oferta_bloque === "" && sinBloque.oferta_siguiente_desde === "" && sinBloque.bloques_ofrecidos === 0,
      JSON.stringify(sinBloque));

    const prevBase = (extra) => ({
      trigger: { text: "a la tarde", multi_turn_state: "oferta_horarios", oferta_bloque: BLOQUE_VIVO,
                 oferta_siguiente_desde: "2026-09-30", bloques_ofrecidos: 1, ...extra } });

    // (1) pide una franja sobre el bloque que acaba de recibir -> se le repite SOLO esa franja
    const r1 = (await fnStep5(prevBase({}), { accion: "reprogramar", franja: "tarde" }))[0].json;
    check("Step 5: 'a la tarde' sobre el bloque -> se le repiten los turnos de tarde, sin tocar la agenda",
      r1.action_to_execute === "ninguna"
      && r1.mensaje_final === ["Tenemos los próximos turnos disponibles:", "Por la tarde:",
                               "* Miércoles 30 de septiembre 16:20", "* Lunes 5 de octubre 15:00 , 15:40", "",
                               "Le sirve alguno?"].join("\n"), JSON.stringify(r1.mensaje_final));
    check("Step 5: la respuesta por franja conserva la marca (bypass del Formatting Agent + Step 0b)",
      r1.mensaje_final.includes("turnos disponibles:"), r1.mensaje_final);

    const r1m = (await fnStep5(prevBase({}), { accion: "reprogramar", franja: "manana" }))[0].json;
    check("Step 5: 'a la mañana' recorta la sección de mañana",
      r1m.mensaje_final.includes("Por la mañana:") && !r1m.mensaje_final.includes("Por la tarde"), r1m.mensaje_final);

    const r1h = (await fnStep5(prevBase({}), { accion: "reprogramar", franja: "tarde", hora_minima: 16 }))[0].json;
    check("Step 5: 'después de las 16' filtra los horarios de la franja",
      r1h.mensaje_final.includes("16:20") && !r1h.mensaje_final.includes("15:00"), r1h.mensaje_final);

    const r1x = (await fnStep5(prevBase({}), { accion: "reprogramar", franja: "tarde", hora_minima: 19 }))[0].json;
    check("Step 5: si la franja pedida no tiene nada que sirva, se busca el lote siguiente",
      r1x.action_to_execute === "buscar_horarios" && r1x.fecha_objetivo === "2026-09-30", JSON.stringify(r1x.fecha_objetivo));

    // (2) rechaza todo -> lote SIGUIENTE (no el mismo bloque otra vez)
    const r2 = (await fnStep5(prevBase({ text: "ninguno me sirve" }), { accion: "reprogramar" }))[0].json;
    check("Step 5: 'ninguno me sirve' -> siguiente lote (`desde` del bloque anterior), NO el mismo bloque",
      r2.action_to_execute === "buscar_horarios" && r2.fecha_objetivo === "2026-09-30"
      && r2.franja === null && r2.hora_minima === null, JSON.stringify(r2));

    // (3) segundo rechazo -> escala, no hay un tercer bloque
    const r3 = (await fnStep5(prevBase({ text: "tampoco", bloques_ofrecidos: 2 }), { accion: "reprogramar" }))[0].json;
    check("Step 5: después de DOS bloques rechazados escala (no hay un tercero)",
      r3.action_to_execute === "escalar" && /secretaria/.test(r3.mensaje_final), JSON.stringify(r3));

    // (4) primer pedido de reprogramar, sin bloque previo -> se busca desde hoy
    const r4 = (await fnStep5({ trigger: { text: "quiero cambiar el turno", multi_turn_state: "conversacion_nueva" } },
                              { accion: "reprogramar" }))[0].json;
    check("Step 5: primer 'quiero reprogramar' -> se ofrece el bloque desde hoy, SIN preguntar día ni franja",
      r4.action_to_execute === "buscar_horarios" && r4.fecha_objetivo === "", JSON.stringify(r4));

    // (5) el paciente nombró una fecha por su cuenta: gana como "desde"
    const r5 = (await fnStep5({ trigger: { text: "para el 20 de octubre", multi_turn_state: "conversacion_nueva" } },
                              { accion: "reprogramar", fecha_objetivo: "2026-10-20" }))[0].json;
    check("Step 5: la fecha que dice el paciente se usa como 'desde', no como filtro de un día",
      r5.fecha_objetivo === "2026-10-20", JSON.stringify(r5.fecha_objetivo));

    // (6) NADA de lo que devuelve Step 5 vuelve a preguntar por día o franja
    const mensajes = [r1.mensaje_final, r1m.mensaje_final, r1h.mensaje_final, r3.mensaje_final];
    check("ningún mensaje de Step 5 pregunta día ni franja ni nombra el sistema de gestión",
      !/que dia|qué día|franja|fecha concreta|dentalink/i.test(mensajes.join(" | ")), mensajes.join(" | "));
  }

  // ============================================================ 4.d) los partials del prompt son coherentes
  {
    const D = "prompts/v6_partials/turnos/";
    const despues = fs.readdirSync(path.join(ROOT, D)).filter((f) => f.endsWith(".despues.md"));
    const textos = Object.fromEntries(despues.map((f) => [f, read(D + f)]));

    check("la línea de TOOLS deja de decir que `fecha` es OBLIGATORIO",
      /NINGUN parametro es obligatorio/.test(textos["agendar_tools_buscar_horarios.despues.md"])
      && !/OBLIGATORIO/.test(textos["agendar_tools_buscar_horarios.despues.md"].replace("NINGUN parametro es obligatorio", "")),
      textos["agendar_tools_buscar_horarios.despues.md"]);

    // Las dos comprobaciones de abajo miran el CONTEXTO de cada aparición (±140 chars), no el archivo
    // entero: los fragmentos nombran las frases prohibidas justamente para prohibirlas.
    const apariciones = (texto, rx) => {
      const out = [];
      for (const m of texto.matchAll(new RegExp(rx.source, rx.flags.includes("g") ? rx.flags : rx.flags + "g"))) {
        out.push(texto.slice(Math.max(0, m.index - 140), m.index + m[0].length + 140));
      }
      return out;
    };

    // MUST_FIX: la regla del "hs" no puede quedar contradicha. El carve-out es: ADENTRO del bloque las horas
    // van como vienen (sin "hs"); en cualquier otro lado, incluida la frase que repite un turno del bloque,
    // el "hs" es obligatorio. Antes, tres fragmentos mandaban copiar la línea del bloque suelta y "sin hs":
    // esa respuesta no lleva la marca, así que pasa por el Formatting Agent, que le pone el "hs" igual — el
    // paciente veía dos formatos distintos en dos mensajes seguidos y la instrucción era inejecutable.
    check("el carve-out del 'hs' dice explícitamente que FUERA del bloque el 'hs' sigue yendo",
      /INCLUSO cuando repet[ií]s un turno que sali[oó] del bloque/i.test(textos["agendar_formato_horas.despues.md"])
      && /CON "hs"/i.test(textos["agendar_formato_horas.despues.md"]),
      textos["agendar_formato_horas.despues.md"]);
    const franjaFrags = ["agendar_paso5.despues.md", "agendar_regla_17hs.despues.md", "agendar_regla_franja.despues.md"];
    const sinHs = franjaFrags.filter((f) => !/con "hs"/i.test(textos[f])
      || /letra por letra|copiados exactamente igual|copiadas letra/i.test(textos[f]));
    check("los 3 fragmentos de franja mandan repetir el turno en una frase CON 'hs' (no copiar la línea suelta)",
      sinHs.length === 0, sinHs.join(", "));

    // Nombrar la pregunta prohibida está bien; ponerla en boca del bot no.
    const RX_PREGUNTA = /(prefiere por la mañana o por la tarde\?|qu[eé] d[ií]a o franja (te|le) viene mejor|qu[eé] d[ií]a le viene mejor|qu[eé] d[ií]a preferis|fecha concreta)/i;
    const preguntan = Object.entries(textos).filter(([, t]) =>
      apariciones(t, RX_PREGUNTA).some((ctx) => !/PROHIBIDO|NUNCA|NO preguntes|no le preguntes|ni ninguna variante/i.test(ctx)));
    check("ningún fragmento nuevo le pregunta al paciente la franja o el día", preguntan.length === 0,
      preguntan.map(([f]) => f).join(", "));

    const sistema = Object.entries(textos).filter(([, t]) => /dentalink/i.test(t));
    check("ningún fragmento nuevo nombra el sistema de gestión", sistema.length === 0,
      sistema.map(([f]) => f).join(", "));

    // el patrón 12 del Banlist (/\btra(é|e)\s+(el|la|los|las|tu)/i) no debería estar ni de ejemplo
    const traeBanlist = Object.entries(textos).filter(([, t]) => /\btra(é|e)\s+(el|la|los|las|tu)/i.test(t));
    check("ningún fragmento nuevo escribe una frase que el Banlist tiene prohibida", traeBanlist.length === 0,
      traeBanlist.map(([f]) => f).join(", "));

    check("Sub-Agent General ya no promete un mensaje que nunca llega",
      !/Ahora le paso los turnos|Ahora te paso los turnos/.test(textos["general_capacidad.despues.md"])
      && /Confirmame/.test(textos["general_capacidad.despues.md"]), textos["general_capacidad.despues.md"]);
  }

  // ============================================================ 5) el bloque pasa limpio por el Banlist
  {
    const p = path.join(ROOT, "workflows/current/v6_LIVE.json");
    if (!fs.existsSync(p)) {
      console.log("SKIP banlist: falta workflows/current/v6_LIVE.json");
    } else {
      const wf = JSON.parse(fs.readFileSync(p, "utf8"));
      const js = wf.nodes.find((n) => n.name === "Banlist Validator").parameters.jsCode;
      const patrones = [...js.matchAll(/\{\s*rx:\s*(\/(?:[^/\\\n]|\\.)+\/i)/g)].map((m) => eval(m[1]));
      const textos = [BLOQUE_ESPERADO,
        "Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Viernes 2 de octubre 8:30\n\nLe sirve alguno?",
        "Tenemos los próximos turnos disponibles:\nPor la tarde:\n* Miércoles 30 de septiembre 16:20 , 17:00\n\nLe sirve alguno?",
        "En este momento no tengo turnos disponibles para ofrecerle. Le dejo una nota a la secretaria para que se comunique con usted."];
      const disparos = [];
      for (const t of textos) for (const rx of patrones) if (rx.test(t)) disparos.push(rx.source + " -> " + t.slice(0, 40));
      check(`el bloque no dispara ninguno de los ${patrones.length} patrones del Banlist Validator`,
        patrones.length >= 20 && disparos.length === 0, disparos.join(" | ") || `solo ${patrones.length} patrones parseados`);
    }
  }

  // ============================================================ 6) la marca que usan las 3 capas del v6
  {
    const j = await formatear({ slots: AGENDA_REAL });
    check("el bloque trae la marca 'turnos disponibles:' que desvía el Formatting Agent",
      j.bloque.includes("turnos disponibles:"), j.bloque.split("\n")[0]);
  }

  console.log(`\n${fallos === 0 ? "✅" : "❌"} fallos: ${fallos}`);
  process.exit(fallos ? 1 : 0);
})().catch((e) => { console.error("EXCEPCIÓN", e); process.exit(2); });
