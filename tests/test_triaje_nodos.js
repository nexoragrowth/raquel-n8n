// tests/test_triaje_nodos.js — corre el JS REAL de los nodos del triaje (triaje/*.js) con node,
// mockeando el entorno de n8n ($input, $(), $execution, this.helpers.httpRequest).
// Fuente única: si alguien edita triaje/evaluar.js o decidir.js, el test corre el código editado.
//
// Correr: node tests/test_triaje_nodos.js
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const GATE = read("triaje/gate_red_flags.js");
const PROMPT = read("triaje/prompt_clasificador.md");
const EVALUAR = GATE + "\n" + read("triaje/evaluar.js").split("__SYSTEM_PROMPT_JSON__").join(JSON.stringify(PROMPT));
const DECIDIR = read("triaje/decidir.js").split("__CW_TOKEN__").join("test-token");
const PREPARAR = read("triaje/preparar_escalada.js");

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const fnEvaluar = new AsyncFunction("$input", "$", "$execution", "console", EVALUAR);
const fnDecidir = new AsyncFunction("$input", "$", "$execution", "console", DECIDIR);
const fnPreparar = new AsyncFunction("$input", "$", "$execution", "console", PREPARAR);

const VIDEOS = [
  { id: 1, tipo: "alambre_pincha", opcion: 1, url: "https://x/1.mp4", filename: "1.mp4", caption: "Cap 1 con $ y 'comilla'", pregunta_guiada: "¿Es el alambre principal?", texto_salida_emergencia: "Salida 1" },
  { id: 2, tipo: "alambre_pincha", opcion: 2, url: "https://x/2.mp4", filename: "2.mp4", caption: "Cap 2", pregunta_guiada: null, texto_salida_emergencia: "Salida 2" },
];
const CFG_ROW = (over = {}) => ({ triaje_activo: true, modo: "piloto", telefonos_piloto: [], red_flags_extra: [], regex_no_sirvio: null, regex_cierre: null,
  regex_nuevo_problema: null, regex_aparato: null, textos: { texto_escalada: "Escalada canned", texto_cierre: "Cierre canned" }, aviso_pasivo: false,
  ttl_video_seg: 7200, ttl_pregunta_seg: 1800, modelo: "gpt-5-mini", videos: VIDEOS, ...over });

function mkDollar({ text, estado, parseExecuted, ctx = "", contactLabels = ["bot"] }) {
  return (nombre) => {
    const data = {
      "Preparar Mensaje Final": { text, phone: "5491161461034", remoteJid: "5491161461034@s.whatsapp.net" },
      "Build Router Context": { ctx },
      "Triaje: Redis GET estado": { triaje_estado: estado ? JSON.stringify(estado) : null },
      "Parse Intent": { intent: "urgencia_dolor" },
      "Existe paciente?": { payload: [{ id: 1 }] },
      "Triaje: Decidir": global.__lastDecidir || {},
      "Triaje: Preparar Escalada": global.__lastPreparar || {},
      "Triaje: Enviar Texto Escalada": { data: { Info: { ID: "x" } } },
    }[nombre];
    if (!data) throw new Error(`nodo desconocido ${nombre}`);
    return { first: () => ({ json: data }), item: { json: data }, isExecuted: nombre === "Parse Intent" ? !!parseExecuted : true };
  };
}
const ctxHelpers = (labels) => ({ helpers: { httpRequest: async () => ({ payload: [{ id: 272, labels }] }) } });
const llmResp = (tipo, confianza) => ({ choices: [{ message: { content: JSON.stringify({ tipo, confianza, razon: "r" }) } }] });

async function runEvaluar(c) {
  const $input = { first: () => ({ json: c.cfg || CFG_ROW() }), all: () => [{ json: c.cfg || CFG_ROW() }] };
  const res = await fnEvaluar($input, mkDollar(c), { id: "exec1" }, console);
  return res[0].json;
}
async function runDecidir(evOut, c, llm) {
  const merged = llm ? { ...evOut, ...llm } : evOut;
  const $input = { first: () => ({ json: merged }), all: () => [{ json: merged }] };
  const res = await fnDecidir.call(ctxHelpers(c.contactLabels || ["bot"]), $input, mkDollar(c), { id: "exec1" }, console);
  global.__lastDecidir = res[0].json;
  return res[0].json;
}
async function runPreparar(inputJson, c) {
  const $input = { first: () => ({ json: inputJson }), all: () => [{ json: inputJson }] };
  const res = await fnPreparar($input, mkDollar(c), { id: "exec1" }, console);
  global.__lastPreparar = res[0].json;
  return res[0].json;
}

let fallos = 0;
const check = (nombre, cond, detalle) => { console.log(`${cond ? "OK  " : "FAIL"} ${nombre}${cond ? "" : " — " + detalle}`); if (!cond) fallos++; };

(async () => {
  // --- Modo nuevo: sin estado, clasificar ---
  let c = { text: "se me salió el alambre de atrás y me pincha el cachete", estado: null, parseExecuted: true };
  let ev = await runEvaluar(c);
  check("nuevo -> clasificar", ev.ruta_pre === "clasificar" && ev.modo_entrada === "nuevo", JSON.stringify(ev.ruta_pre));
  let d = await runDecidir(ev, c, llmResp("alambre_pincha", "alta"));
  check("alta -> video op1", d.ruta === "video" && d.video.opcion === 1 && d.send.url === "https://x/1.mp4" && d.estado_ttl === 7200, d.ruta);
  check("sql sin $ crudo", !/\$\d/.test(d.sql_persistir) && d.sql_persistir.includes("chr(36)"), d.sql_persistir.slice(0, 120));
  check("sql sin comillas rotas", d.sql_persistir.includes("''comilla''"), "");
  d = await runDecidir(ev, c, llmResp("alambre_pincha", "media"));
  check("media -> pregunta guiada", d.ruta === "pregunta" && d.send.text.startsWith("¿Es el alambre") && d.estado_ttl === 1800, d.ruta);
  d = await runDecidir(ev, c, llmResp("bracket_suelto", "alta"));
  check("tipo sin video -> escalar", d.ruta === "escalar", d.ruta);
  d = await runDecidir(ev, c, llmResp("red_flag", "alta"));
  check("LLM red_flag -> escalar", d.ruta === "escalar", d.ruta);
  d = await runDecidir(ev, c, { choices: [{ message: { content: "no json" } }] });
  check("LLM roto -> escalar error_llm", d.ruta === "escalar" && d.tipo === "error_llm", d.ruta + " " + d.tipo);
  d = await runDecidir(ev, { ...c, contactLabels: ["humano"] }, llmResp("alambre_pincha", "alta"));
  check("humano atendiendo -> silencio", d.ruta === "silencio" && d.sql_silencio.includes("silencio_humano"), d.ruta);

  // --- Gate antes que nada (nuevo y seguimiento) ---
  c = { text: "se cayó y le sangra mucho la boca, se le salió el alambre", estado: null, parseExecuted: true };
  ev = await runEvaluar(c);
  check("gate red flag -> decidido escalar", ev.ruta_pre === "decidido" && ev.ruta === "escalar" && ev.gate_flags.includes("trauma"), JSON.stringify(ev.gate_flags));
  c = { text: "tengo fiebre desde anoche", estado: { tipo: "alambre_pincha", opcion: 1, paso: "video_enviado" }, parseExecuted: false };
  ev = await runEvaluar(c);
  check("gate en seguimiento -> escalar", ev.ruta_pre === "decidido" && ev.ruta === "escalar" && ev.gate_flags.includes("fiebre"), JSON.stringify(ev));

  // --- Inactivo / fuera de piloto ---
  c = { text: "me pincha el alambre", estado: null, parseExecuted: true, cfg: CFG_ROW({ triaje_activo: false }) };
  ev = await runEvaluar(c);
  check("inactivo -> escalar triaje_inactivo", ev.ruta === "escalar" && ev.razon === "triaje_inactivo", JSON.stringify(ev.razon));
  c = { text: "me pincha el alambre", estado: null, parseExecuted: true, cfg: CFG_ROW({ telefonos_piloto: ["5490000000000"] }) };
  ev = await runEvaluar(c);
  check("fuera piloto -> escalar", ev.ruta === "escalar" && ev.razon === "fuera_piloto", JSON.stringify(ev.razon));
  c = { text: "me pincha el alambre", estado: null, parseExecuted: true, cfg: { } };
  ev = await runEvaluar(c);
  check("config vacía (Postgres caído) -> escalar", ev.ruta === "escalar" && ev.razon === "config_no_disponible", JSON.stringify(ev.razon));

  // --- Seguimiento paso video_enviado ---
  const est1 = { tipo: "alambre_pincha", opcion: 1, paso: "video_enviado" };
  const casosSeg = [
    ["no me sirvió, sigue pinchando", "video", 2, "no sirvió -> opción 2"],
    ["No funcionó", "video", 2, "no funcionó (mayúscula, tilde) -> opción 2"],
    ["no tengo cera", "video", 2, "no tengo cera -> opción 2"],
    ["se me vuelve a salir", "video", 2, "se vuelve a salir -> opción 2"],
    ["listo gracias ya me puse la cera", "cerrar", null, "cierre con cera -> cerrar (no escalar)"],
    ["listo, lo pude acomodar con la pinza, gracias", "cerrar", null, "cierre con pinza -> cerrar"],
    ["igual gracias, ya está", "cerrar", null, "'igual gracias' -> cerrar (no opción 2)"],
    ["Gracias!!", "cerrar", null, "gracias -> cerrar"],
    ["y si no tengo pinza?", "video", 2, "no tengo pinza -> opción 2"],
    ["me sigue lastimando el cachete", "video", 2, "sigue lastimando -> opción 2"],
    ["ok pero me duele mucho igual", "escalar", null, "'ok' + duele -> escalar (no cierra)"],
    ["dale, voy a probar", "cerrar", null, "dale voy a probar -> cerrar"],
    ["hola, quería sacar un turno para mi hija", "normal", null, "otro tema -> normal (Router)"],
    ["cuánto sale la consulta?", "normal", null, "precio -> normal"],
  ];
  for (const [txt, ruta, opcion, nombre] of casosSeg) {
    c = { text: txt, estado: est1, parseExecuted: false };
    ev = await runEvaluar(c);
    const r = ev.ruta_pre === "normal" ? "normal" : ev.ruta;
    const okOp = opcion ? (ev.video && Number(ev.video.opcion) === opcion) : true;
    check("seg video1: " + nombre, r === ruta && okOp, JSON.stringify({ ruta_pre: ev.ruta_pre, ruta: ev.ruta, razon: ev.razon }));
  }
  // duda sobre el mismo aparato sin cerrar ni "no sirvió" -> escalar (nunca General)
  c = { text: "la cera se me pega en el diente, está bien eso?", estado: est1, parseExecuted: false };
  ev = await runEvaluar(c);
  check("seg video1: duda sobre cera -> escalar", ev.ruta === "escalar" && ev.razon === "seguimiento_no_resuelto", JSON.stringify(ev.razon));
  // nuevo problema + no sirvió -> reclasificar (no mandar opción 2 a ciegas)
  c = { text: "no me sirvió, ahora me duele la muela de arriba, es otra cosa", estado: est1, parseExecuted: false };
  ev = await runEvaluar(c);
  check("seg video1: no sirvió + otra cosa -> clasificar", ev.ruta_pre === "clasificar" && ev.post_video === true, JSON.stringify(ev.ruta_pre));
  d = await runDecidir(ev, c, llmResp("otra_urgencia", "media"));
  check("  ...otra_urgencia -> escalar", d.ruta === "escalar", d.ruta);
  // opción 2 agotada
  const est2 = { tipo: "alambre_pincha", opcion: 2, paso: "video_enviado" };
  c = { text: "no lo pude meter con la pinza, sigue igual", estado: est2, parseExecuted: false };
  ev = await runEvaluar(c);
  check("seg video2: no sirvió -> escalar sin más opciones", ev.ruta === "escalar" && ev.razon === "no_sirvio_sin_mas_opciones", JSON.stringify(ev.razon));
  // kill-switch con estado vigente: no sirvió -> escalar (no opción 2)
  c = { text: "no me sirvió", estado: est1, parseExecuted: false, cfg: CFG_ROW({ triaje_activo: false }) };
  ev = await runEvaluar(c);
  check("seg con activo=false: no sirvió -> escalar", ev.ruta === "escalar", JSON.stringify(ev.razon));
  c = { text: "listo gracias", estado: est1, parseExecuted: false, cfg: CFG_ROW({ triaje_activo: false }) };
  ev = await runEvaluar(c);
  check("seg con activo=false: gracias -> cerrar (no escala)", ev.ruta === "cerrar", JSON.stringify(ev.ruta));

  // --- Seguimiento paso pregunta ---
  const estP = { tipo: "alambre_pincha", paso: "pregunta", pregunta: "¿Es el alambre principal?", texto_original: "algo me pincha" };
  c = { text: "sí, el de atrás, me lastima el cachete", estado: estP, parseExecuted: false };
  ev = await runEvaluar(c);
  check("pregunta -> reclasificar", ev.ruta_pre === "clasificar" && ev.reclasifica === true && ev.llm_body.includes("RESPUESTA DEL PACIENTE"), JSON.stringify(ev.ruta_pre));
  d = await runDecidir(ev, c, llmResp("alambre_pincha", "alta"));
  check("  ...alta -> video op1", d.ruta === "video" && d.video.opcion === 1, d.ruta);
  d = await runDecidir(ev, c, llmResp("alambre_pincha", "media"));
  check("  ...media -> escalar (nunca 2ª pregunta)", d.ruta === "escalar" && d.razon.includes("post_pregunta"), d.ruta + " " + d.razon);

  // --- Estado reconstruido desde ctx (Redis vencido), modo nuevo, mismo tipo -> escalar ---
  const ctx = "PACIENTE: se me salió el alambre\n---\nBOT: [VIDEO ENVIADO — alambre_pincha, Opción 1] cap\n---\nPACIENTE: sigue pinchando";
  c = { text: "sigue pinchando", estado: null, parseExecuted: true, ctx };
  ev = await runEvaluar(c);
  check("ctx reconstruye estado", ev.estado && ev.estado.origen === "ctx" && ev.post_video === true, JSON.stringify(ev.estado));
  d = await runDecidir(ev, c, llmResp("alambre_pincha", "alta"));
  check("  ...mismo tipo post video -> escalar", d.ruta === "escalar" && d.razon === "mismo_problema_post_video", d.ruta + " " + d.razon);
  const ctx2 = ctx + "\n---\nBOT: [TRIAJE ESCALADO] x";
  c = { text: "hola me pincha el alambre", estado: null, parseExecuted: true, ctx: ctx2 };
  ev = await runEvaluar(c);
  check("ctx con ESCALADO posterior -> sin estado", !ev.estado, JSON.stringify(ev.estado));

  // --- Decidir defensivo: input sin evaluación ---
  d = await runDecidir({ choices: [] }, c, null);
  check("decidir sin evaluar -> escalar", d.ruta === "escalar" && d.razon === "sin_evaluacion", d.ruta);

  // --- Preparar Escalada ---
  c = { text: "no lo pude meter con la pinza, sigue igual", estado: est2, parseExecuted: false };
  ev = await runEvaluar(c);
  let p = await runPreparar(ev, c);
  check("preparar: texto canned + resumen", p.send.text === "Escalada canned" && p.resumen.includes("[TRIAJE]") && p.resumen.includes("Opción 1 y 2") && p.estado_ttl === 3600, JSON.stringify(p.resumen));
  // desde fallo de envío (input = respuesta HTTP)
  global.__lastDecidir = await runDecidir(await runEvaluar({ text: "me pincha el alambre", estado: null, parseExecuted: true }), { text: "me pincha el alambre", estado: null, parseExecuted: true }, llmResp("alambre_pincha", "alta"));
  p = await runPreparar({ statusCode: 500, error: { message: "boom" } }, { text: "me pincha el alambre", estado: null, parseExecuted: true });
  check("preparar tras fallo /send/media", p.razon.startsWith("envio_fallo_video") && p.send.text === "Escalada canned", p.razon);

  console.log(`\n${fallos === 0 ? "✅" : "❌"} fallos: ${fallos}`);
  process.exit(fallos ? 1 : 0);
})();
