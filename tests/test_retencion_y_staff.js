// tests/test_retencion_y_staff.js — corre el JS REAL de los nodos con node, mockeando el entorno de n8n
// ($input, $(), $getWorkflowStaticData). Mismo harness que test_triaje_nodos.js / test_media_nodos.js.
//   - "Validar secreto" (media_tipo inválido = error 400, 7/9) y "Armar fila memoria" del satélite Panel — acciones staff (VALIDAR_JS / MEMORIA_JS embebidos en
//     scripts/create_panel_acciones_staff.py: se extraen del .py por regex, así el test corre exactamente lo que se deploya).
//   - "Evaluar y deduplicar" del Vigía (EVAL_JS + QUERY de scripts/create_vigia_bot.py): umbrales de uso de Supabase,
//     ventanaMin 24 h vs 60 min, dedupe, query rota.
//   - Code nodes del satélite Retención: retencion/agrupar_lote.js, resumen.js, armar_aviso.js.
//
// Correr: node tests/test_retencion_y_staff.js
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const pyStr = (src, name) => {
  const m = src.match(new RegExp("\\n" + name + ' = r?"""([\\s\\S]*?)"""'));
  if (!m) throw new Error("no encontré " + name + " en el .py");
  return m[1];
};
const STAFF_PY = read("scripts/create_panel_acciones_staff.py");
const VIGIA_PY = read("scripts/create_vigia_bot.py");
const LUCAS = "5491161461034";
const VALIDAR = pyStr(STAFF_PY, "VALIDAR_JS").split("__PANEL_SECRET__").join("test-secret");
const MEMORIA = pyStr(STAFF_PY, "MEMORIA_JS");
const EVAL = pyStr(VIGIA_PY, "EVAL_JS").split("__LUCAS__").join(LUCAS);
const QUERY = pyStr(VIGIA_PY, "QUERY");
const AGRUPAR = read("retencion/agrupar_lote.js");
const RESUMEN = read("retencion/resumen.js").split("__DIAS_MEDIA_PACIENTES__").join("90").split("__DIAS_PANEL_MEDIA__").join("90").split("__DIAS_INBOX_LIVE__").join("365");
const AVISO = read("retencion/armar_aviso.js").split("__LUCAS__").join(LUCAS);

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const fnValidar = new AsyncFunction("$input", "$", "console", VALIDAR);
const fnMemoria = new AsyncFunction("$input", "$", "console", MEMORIA);
const fnEval = new AsyncFunction("$input", "$", "$getWorkflowStaticData", "console", EVAL);
const mkAgrupar = (bucket) => new AsyncFunction("$input", "$", "console", AGRUPAR.split("__BUCKET__").join(bucket));
const fnResumen = new AsyncFunction("$input", "$", "console", RESUMEN);
const fnAviso = new AsyncFunction("$input", "$", "console", AVISO);

let fallos = 0;
const check = (nombre, cond, detalle) => { console.log(`${cond ? "OK  " : "FAIL"} ${nombre}${cond ? "" : " — " + detalle}`); if (!cond) fallos++; };
const inputDe = (items) => ({ all: () => items.map((j) => ({ json: j })), first: () => ({ json: items[0] }) });
// $('nodo') como en n8n: nodo no ejecutado -> isExecuted false y first()/all() tiran.
const mk$ = (outs) => (n) => {
  if (!(n in outs) || outs[n] === null) return { isExecuted: false, first: () => { throw new Error("unexecuted " + n); }, all: () => { throw new Error("unexecuted " + n); } };
  const arr = Array.isArray(outs[n]) ? outs[n] : [outs[n]];
  return { isExecuted: true, first: () => ({ json: arr[0] }), all: () => arr.map((j) => ({ json: j })) };
};

// ---------------- staff: Validar secreto ----------------
async function validar(body, headers = { "x-panel-secret": "test-secret" }, url = "https://n8n/webhook/panel-send-human") {
  const j = { headers, body, webhookUrl: url };
  return (await fnValidar(inputDe([j]), mk$({}), console))[0].json;
}
async function memoria(p) {
  return (await fnMemoria(inputDe([p]), mk$({ "Validar secreto": p }), console))[0].json;
}

// ---------------- vigía: Evaluar y deduplicar ----------------
const Q_SANA = () => ({ triaje_degradado: "0", triaje_razones: null, entrantes_3h: "5", ultimo_entrante: new Date().toISOString(), triaje_activo: true,
  videos_activos: "2", db_bytes: String(20 * 1048576), storage_bytes: String(9 * 1048576), storage_pacientes_bytes: "30000",
  retencion_tabla: true, retencion_min: "125.5", ahora: new Date().toISOString() });
const hace = (min) => new Date(Date.now() - min * 60 * 1000).toISOString();
async function evaluar(q, st = {}, execs = []) {
  const r = await fnEval(inputDe([{}]), mk$({ "Query señales": q, "Ejecuciones v6 con error": { data: execs } }), () => st, console);
  return { out: r, texto: r.length ? r[0].json.texto : "", numero: r.length ? r[0].json.numero : null, st };
}

// ---------------- retención ----------------
async function agrupar(items, { bucket = "pacientes-media", webhook = undefined } = {}) {
  const $ = mk$({ "Webhook Manual Retención": webhook === undefined ? null : webhook });
  return (await mkAgrupar(bucket)(inputDe(items), $, console))[0].json;
}
const AG = (over = {}) => ({ bucket: "pacientes-media", ids: [], paths: [], n: 0, filas: 0, omitidas: 0, smoke: false, error: null, ...over });
async function resumen(outs) {
  const r = await fnResumen(inputDe([{}]), mk$(outs), console);
  const porBucket = Object.fromEntries(r.map((i) => [i.json.bucket, i.json]));
  return { filas: r.map((i) => i.json), p: porBucket["pacientes-media"], s: porBucket["panel-media"], b: porBucket["mensajes_entrantes_live"] };
}
async function aviso(filasResumen, inputItems) {
  return fnAviso(inputDe(inputItems), mk$({ Resumen: filasResumen }), console);
}

(async () => {
  console.log("--- staff: Validar secreto ---");
  let v = await validar({ telefono: "5491161461034", media_url: "https://x.supabase.co/storage/v1/object/public/panel-media/549/1-a.m4a", media_tipo: "audio", filename: "nota de voz.m4a", autor: "lucas" });
  check("audio aceptado (ok, media_tipo audio)", v.ok === true && v.error === null && v.media_tipo === "audio", JSON.stringify(v));
  check("audio: filename saneado conserva extensión", v.filename === "nota_de_voz.m4a", v.filename);
  check("audio: autor capitalizado, mensaje vacío permitido con media", v.autor === "Lucas" && v.mensaje === "" && v.number === "5491161461034", JSON.stringify(v));
  for (const t of ["image", "video", "document"]) {
    v = await validar({ telefono: "5491161461034", media_url: "https://x/a.bin", media_tipo: t, filename: "a.bin" });
    check(`${t} sigue aceptado`, v.ok && v.media_tipo === t, JSON.stringify(v));
  }
  v = await validar({ telefono: "5491161461034", media_url: "https://x/a.ogg", media_tipo: "ptt", filename: "a.ogg" });
  check("tipo inválido (ptt) -> error 'media_tipo invalido' (ya NO cae a image)", v.ok === false && v.error === "media_tipo invalido" && v.media_tipo === "", JSON.stringify(v));
  v = await validar({ telefono: "5491161461034", media_url: "https://x/a.webp", media_tipo: "sticker" });
  check("tipo inválido (sticker) -> error", v.ok === false && v.error === "media_tipo invalido", JSON.stringify(v));
  v = await validar({ telefono: "5491161461034", media_url: "https://x/a.mp4", media_tipo: "video/mp4" });
  check("mime en vez de tipo (video/mp4) -> error", v.ok === false && v.error === "media_tipo invalido", JSON.stringify(v));
  v = await validar({ telefono: "5491161461034", media_url: "https://x/a.jpg" });
  check("media_url sin media_tipo -> error (el panel siempre lo manda)", v.ok === false && v.error === "media_tipo invalido", JSON.stringify(v));
  check("el satélite responde 400 (no 401) a los errores de validación: IF '¿Sin secreto?' + 'Responder 400'",
    STAFF_PY.includes('"¿Sin secreto?": {"main": [[C("Responder 401")], [C("Responder 400")]]}') && STAFF_PY.includes('"¿Autorizado?": {"main": [[C("¿Es envío?")], [C("¿Sin secreto?")]]}'), "");
  v = await validar({ telefono: "5491161461034", media_tipo: "audio" });
  check("media_tipo sin media_url -> tipo vacío y 'mensaje vacio'", v.media_tipo === "" && v.error === "mensaje vacio" && v.ok === false, JSON.stringify(v));
  const largo = "a".repeat(120) + ".m4a";
  v = await validar({ telefono: "5491161461034", media_url: "https://x/a.m4a", media_tipo: "audio", filename: largo });
  check("filename > 80 chars: recorta la base y conserva .m4a", v.filename.length === 80 && v.filename.endsWith(".m4a"), v.filename);
  v = await validar({ telefono: "5491161461034", media_url: "https://x/a.mp3", media_tipo: "audio", filename: "a".repeat(76) + ".mp3" });
  check("filename de exactamente 80 chars queda igual", v.filename === "a".repeat(76) + ".mp3", v.filename);
  v = await validar({ telefono: "5491161461034", media_url: "https://x/a.mp3", media_tipo: "audio", filename: "canción ñandú (final).mp3" });
  check("filename con espacios/tildes -> guiones bajos, ext intacta", v.filename === "canci_n__and___final_.mp3", v.filename);
  v = await validar({ telefono: "5491161461034", media_url: "https://x/a.mp3", media_tipo: "audio" });
  check("sin filename con media -> 'archivo'", v.filename === "archivo", v.filename);
  v = await validar({ telefono: "5491161461034", mensaje: "hola" });
  check("texto sin media -> filename vacío, media_tipo vacío", v.filename === "" && v.media_tipo === "" && v.ok, JSON.stringify(v));
  v = await validar({ telefono: "5491161461034", media_url: "http://x/a.mp3", media_tipo: "audio", filename: "a.mp3" });
  check("media_url http -> 'media_url invalida'", v.ok === false && v.error === "media_url invalida", JSON.stringify(v));
  v = await validar({ telefono: "5491161461034", mensaje: "hola" }, { "x-panel-secret": "otro" });
  check("secreto incorrecto -> unauthorized", v.ok === false && v.error === "unauthorized", v.error);
  v = await validar({ telefono: "+54 9 11 6146-1034", humano: "true" }, undefined, "https://n8n/webhook/panel-toggle-bot");
  check("toggle: acción, teléfono solo dígitos, humano", v.accion === "toggle" && v.telefono === "5491161461034" && v.humano === true && v.ok, JSON.stringify(v));

  console.log("--- staff: Armar fila memoria ---");
  const base = { telefono: "5491161461034", autor: "Lucas", autor_raw: "lucas", mensaje: "", media_url: "", media_tipo: "", filename: "" };
  let m = await memoria({ ...base, mensaje: "escuchá esto", media_url: "https://x/panel-media/549/a.m4a", media_tipo: "audio", filename: "a.m4a" });
  let msg = JSON.parse(m.message);
  check("audio + caption -> '[audio] <url>\\n<caption>' tras el TAG", /\]: \[audio\] https:\/\/x\/panel-media\/549\/a\.m4a\nescuchá esto$/.test(msg.content), JSON.stringify(msg.content.slice(-60)));
  check("audio: additional_kwargs coherentes (panel, wa_outbound, media_tipo audio)", msg.type === "ai" && msg.additional_kwargs.from_panel === true && msg.additional_kwargs.source === "wa_outbound" && msg.additional_kwargs.media_tipo === "audio" && msg.additional_kwargs.was_multimedia === true && msg.additional_kwargs.autor === "lucas", JSON.stringify(msg.additional_kwargs));
  check("audio: session_id = teléfono y TAG con autor", m.session_id === "5491161461034" && msg.content.startsWith("[ATENCION HUMANA - mensaje enviado por Lucas desde el PANEL"), m.session_id);
  m = await memoria({ ...base, media_url: "https://x/a.m4a", media_tipo: "audio" });
  msg = JSON.parse(m.message);
  check("audio sin caption -> termina en la URL, sin salto", msg.content.endsWith("[audio] https://x/a.m4a"), JSON.stringify(msg.content.slice(-40)));
  m = await memoria({ ...base, mensaje: "mirá", media_url: "https://x/a.jpg", media_tipo: "image" });
  check("imagen -> '[imagen] <url>' (intacto)", JSON.parse(m.message).content.includes("]: [imagen] https://x/a.jpg\nmirá"), m.message.slice(-60));
  m = await memoria({ ...base, media_url: "https://x/a.mp4", media_tipo: "video" });
  check("video -> '[video] <url>'", JSON.parse(m.message).content.endsWith("[video] https://x/a.mp4"), m.message.slice(-40));
  m = await memoria({ ...base, media_url: "https://x/a.pdf", media_tipo: "document" });
  check("document -> '[document] <url>'", JSON.parse(m.message).content.endsWith("[document] https://x/a.pdf"), m.message.slice(-40));
  m = await memoria({ ...base, mensaje: "solo texto" });
  msg = JSON.parse(m.message);
  check("texto sin media -> sin marcador, media_url null", msg.content.endsWith("]: solo texto") && msg.additional_kwargs.media_url === null && msg.additional_kwargs.was_multimedia === false, msg.content.slice(-30));

  console.log("--- vigía: QUERY ---");
  check("QUERY trae db_bytes / storage_bytes / storage_pacientes_bytes", /AS db_bytes/.test(QUERY) && /AS storage_bytes/.test(QUERY) && /AS storage_pacientes_bytes/.test(QUERY), "");
  check("QUERY termina en NOW() AS ahora (sin coma colgando)", /NOW\(\) AS ahora\s*$/.test(QUERY), JSON.stringify(QUERY.slice(-40)));
  check("QUERY filtra carpetas virtuales (metadata IS NOT NULL)", (QUERY.match(/metadata IS NOT NULL/g) || []).length === 2, "");
  check("QUERY trae retencion_tabla / retencion_min vía query_to_xml (no rompe si la tabla no existe)",
    /AS retencion_tabla/.test(QUERY) && /AS retencion_min/.test(QUERY) && QUERY.includes("query_to_xml('SELECT extract(epoch FROM now() - max(corrida_at))/60 AS min FROM public.retencion_log'") && !/FROM retencion_log/.test(QUERY), "");

  console.log("--- vigía: Evaluar y deduplicar ---");
  let e = await evaluar(Q_SANA());
  check("señales sanas -> sin alertas", e.out.length === 0, JSON.stringify(e.out));
  e = await evaluar({ ...Q_SANA(), db_bytes: String(450 * 1048576) });
  check("base 450 MB (bigint como string) -> supabase_db_alto con MB reales", e.out.length === 1 && e.texto.includes("450 MB de 500") && e.texto.includes("subir de plan o limpiar") && !!e.st.last.supabase_db_alto, e.texto);
  check("  ...va a Lucas, encabezado Vigía, pie con base/storage", e.numero === LUCAS && e.texto.startsWith("👁️ *Vigía Asiri*") && /base: 450 MB, storage: 9 MB/.test(e.texto), e.texto);
  e = await evaluar({ ...Q_SANA(), db_bytes: String(400 * 1048576) });
  check("base exactamente 400 MB -> no alerta (umbral estricto)", e.out.length === 0, e.texto);
  e = await evaluar({ ...Q_SANA(), storage_bytes: String(900 * 1048576), storage_pacientes_bytes: String(850 * 1048576) });
  check("storage 900 MB -> supabase_storage_alto con MB y pacientes-media", e.out.length === 1 && e.texto.includes("900 MB de 1024") && e.texto.includes("pacientes-media: 850 MB") && !!e.st.last.supabase_storage_alto, e.texto);
  e = await evaluar({ ...Q_SANA(), storage_bytes: String(800 * 1048576) });
  check("storage exactamente 800 MB -> no alerta", e.out.length === 0, e.texto);
  e = await evaluar({ ...Q_SANA(), db_bytes: String(450 * 1048576) }, { last: { supabase_db_alto: hace(23 * 60) } });
  check("db_alto avisada hace 23 h -> dedupe 24 h, no repite", e.out.length === 0, e.texto);
  const stDb = { last: { supabase_db_alto: hace(25 * 60) } };
  e = await evaluar({ ...Q_SANA(), db_bytes: String(450 * 1048576) }, stDb);
  check("db_alto avisada hace 25 h -> repite y actualiza staticData", e.out.length === 1 && new Date(stDb.last.supabase_db_alto).getTime() > Date.now() - 5000, e.texto);
  e = await evaluar({ ...Q_SANA(), storage_bytes: String(900 * 1048576) }, { last: { supabase_storage_alto: hace(90) } });
  check("storage_alto avisada hace 90 min -> sigue deduplicada (ventana 24 h, no 60 min)", e.out.length === 0, e.texto);
  e = await evaluar({ ...Q_SANA(), triaje_degradado: "2", triaje_razones: "error_llm" }, { last: { triaje_degradado: hace(30) } });
  check("triaje_degradado avisada hace 30 min -> dedupe 60 min", e.out.length === 0, e.texto);
  e = await evaluar({ ...Q_SANA(), triaje_degradado: "2", triaje_razones: "error_llm" }, { last: { triaje_degradado: hace(61) } });
  check("triaje_degradado avisada hace 61 min -> repite (las históricas siguen en 60)", e.out.length === 1 && e.texto.includes("Triaje degradado"), e.texto);
  e = await evaluar({ ...Q_SANA(), db_bytes: String(450 * 1048576), storage_bytes: String(900 * 1048576), triaje_degradado: "1" });
  check("varias alertas -> un solo mensaje con las 3 y 3 claves en staticData", e.out.length === 1 && e.texto.includes("450 MB") && e.texto.includes("900 MB") && e.texto.includes("Triaje degradado") && Object.keys(e.st.last).length === 3, e.texto);
  e = await evaluar({});
  check("query vacía ({}) -> vigia_query_rota, sin falso 'sorda'", e.out.length === 1 && e.texto.includes("no pudo leer sus señales") && !e.texto.includes("sorda") && !!e.st.last.vigia_query_rota, e.texto);
  e = await evaluar({ error: "permission denied for table objects" });
  check("query con error -> el texto trae el error", e.texto.includes("permission denied"), e.texto);
  e = await evaluar({ error: "x" }, { last: { vigia_query_rota: hace(120) } });
  check("query rota avisada hace 2 h -> dedupe 24 h", e.out.length === 0, e.texto);
  e = await evaluar({ ...Q_SANA(), db_bytes: undefined, storage_bytes: null });
  check("sin columnas de uso (Vigía viejo) -> sin alerta de uso, pie con '?'", e.out.length === 0, e.texto);
  e = await evaluar({ ...Q_SANA(), retencion_tabla: false, retencion_min: null });
  check("retencion_log no existe todavía -> sin alerta de retención", e.out.length === 0, e.texto);
  e = await evaluar({ ...Q_SANA(), retencion_tabla: true, retencion_min: null });
  check("tabla existe pero vacía -> retencion_no_corrio ('nunca corrió')", e.out.length === 1 && e.texto.includes("nunca corrió") && !!e.st.last.retencion_no_corrio, e.texto);
  e = await evaluar({ ...Q_SANA(), retencion_min: String(27 * 60) });
  check("última corrida hace 27 h -> retencion_no_corrio con las horas", e.out.length === 1 && e.texto.includes("hace 27 h") && e.texto.includes("Retención"), e.texto);
  e = await evaluar({ ...Q_SANA(), retencion_min: String(25 * 60) });
  check("última corrida hace 25 h -> no alerta (umbral 26 h)", e.out.length === 0, e.texto);
  e = await evaluar({ ...Q_SANA(), retencion_min: String(30 * 60) }, { last: { retencion_no_corrio: hace(5 * 60) } });
  check("retencion_no_corrio avisada hace 5 h -> dedupe 24 h", e.out.length === 0, e.texto);
  e = await evaluar({ ...Q_SANA(), retencion_tabla: undefined, retencion_min: undefined });
  check("Vigía sin las columnas de retención -> sin alerta", e.out.length === 0, e.texto);
  e = await evaluar({ ...Q_SANA(), db_bytes: undefined, triaje_degradado: "1" });
  check("  ...y si hay otra alerta el pie no rompe (base: ?)", e.out.length === 1 && e.texto.includes("base: ?"), e.texto);

  console.log("--- retención: agrupar lote ---");
  const F1 = { id: "3fa9c2e1b7d04a58", bucket: "pacientes-media", path: "549/2026/06/3fa9c2e1b7d04a58.jpg" };
  const F2 = { id: "8c01aaaaaaaaaaaa", bucket: "pacientes-media", path: "549/2026/06/8c01aaaaaaaaaaaa.ogg" };
  let a = await agrupar([F1, F2]);
  check("2 filas -> 1 lote con ids y paths", a.n === 2 && a.filas === 2 && a.ids.join("|") === F1.id + "|" + F2.id && a.paths[1] === F2.path && a.bucket === "pacientes-media" && a.error === null && a.smoke === false, JSON.stringify(a));
  check("ids sin comas (queryReplacement de n8n parte por coma)", !a.ids.join("|").includes(","), a.ids.join("|"));
  a = await agrupar([{}]);
  check("sin filas (item vacío por alwaysOutputData) -> n 0", a.n === 0 && a.filas === 0 && a.error === null, JSON.stringify(a));
  a = await agrupar([{ error: "column \"borrado_at\" does not exist" }]);
  check("SELECT falló -> n 0 + error", a.n === 0 && /borrado_at/.test(a.error), JSON.stringify(a));
  a = await agrupar([{ error: { message: "connection refused" } }]);
  check("error como objeto -> mensaje", a.error === "connection refused", JSON.stringify(a));
  a = await agrupar([F1, { ...F2, bucket: "otro-bucket" }]);
  check("fila de otro bucket -> omitida (no se manda al DELETE de este bucket)", a.n === 1 && a.omitidas === 1 && a.ids.length === 1, JSON.stringify(a));
  a = await agrupar([{ path: "549/1-uuid-foto.jpg", bucket: "panel-media" }], { bucket: "panel-media" });
  check("panel-media (sin id) -> paths sí, ids vacío", a.n === 1 && a.ids.length === 0 && a.bucket === "panel-media", JSON.stringify(a));
  a = await agrupar([F1], { webhook: { body: { smoke: true } } });
  check("smoke desde webhook manual -> agrega path inexistente (n = filas + 1)", a.smoke === true && a.n === 2 && a.filas === 1 && a.paths[1] === "__retencion_smoke__/no-existe.bin" && a.ids.length === 1, JSON.stringify(a));
  a = await agrupar([{}], { webhook: { body: { smoke: true } } });
  check("smoke sin filas -> lote de 1 path fantasma, ids vacío", a.n === 1 && a.filas === 0 && a.ids.length === 0, JSON.stringify(a));
  a = await agrupar([F1], { webhook: { body: {} } });
  check("webhook manual sin smoke -> normal", a.smoke === false && a.n === 1, JSON.stringify(a));
  a = await agrupar([F1], { webhook: { body: { smoke: "true" } } });
  check("smoke solo con boolean true (string no)", a.smoke === false, JSON.stringify(a));

  console.log("--- retención: resumen ---");
  const OK2 = { "Pacientes: agrupar lote": AG({ n: 2, filas: 2, ids: [F1.id, F2.id], paths: [F1.path, F2.path] }),
    "Pacientes: borrar en Storage": { statusCode: 200, body: [{ name: F1.path }, { name: F2.path }] },
    "Pacientes: marcar borrado_at": { marcados: 2 },
    "Panel: agrupar lote": AG({ bucket: "panel-media", n: 1, filas: 1, paths: ["549/x.jpg"] }),
    "Panel: borrar en Storage": { statusCode: 200, body: [] },
    "Bandeja: purgar": { borrados: 3 } };
  let r = await resumen(OK2);
  check("corrida feliz -> 3 filas, sin fallos", r.filas.length === 3 && r.p.borrados === 2 && r.p.fallidos === 0 && r.s.borrados === 1 && r.b.borrados === 3 && r.filas.every((f) => f.hubo_fallo === false), JSON.stringify(r.filas));
  check("  ...detalle con los días de retención", r.p.detalle.startsWith("> 90 días") && r.b.detalle.startsWith("> 365 días") && r.p.dias === 90 && r.b.dias === 365, JSON.stringify([r.p.detalle, r.b.detalle]));
  check("  ...objeto ya inexistente NO es fallo (Storage devolvió 0 de 1)", r.s.fallidos === 0 && r.s.detalle.includes("devolvió 0 de 1"), r.s.detalle);
  check("  ...pero 0 de N pedidos deja advertencia (paths que no coinciden con storage.objects.name)", typeof r.s.advertencia === "string" && r.s.advertencia.includes("NINGUNO") && r.s.detalle.includes("⚠") && r.p.advertencia === null && r.b.advertencia === null, JSON.stringify(r.s));
  r = await resumen({ ...OK2, "Pacientes: borrar en Storage": { statusCode: 200, body: [] } });
  check("pacientes: 2 reales y Storage devolvió 0 -> borrados 2, fallidos 0, advertencia", r.p.borrados === 2 && r.p.fallidos === 0 && !!r.p.advertencia && r.p.detalle.includes("devolvió 0 de 2"), JSON.stringify(r.p));
  r = await resumen({ ...OK2, "Pacientes: borrar en Storage": { statusCode: 200, body: [{ name: F1.path }] } });
  check("pacientes: Storage devolvió 1 de 2 -> nota, sin advertencia", r.p.advertencia === null && r.p.detalle.includes("devolvió 1 de 2"), JSON.stringify(r.p));
  r = await resumen({ "Pacientes: agrupar lote": AG(), "Panel: agrupar lote": AG({ bucket: "panel-media" }), "Bandeja: purgar": { borrados: 0 } });
  check("nada que borrar (DELETE/UPDATE no ejecutan) -> ceros, sin fallo", r.p.borrados === 0 && r.p.fallidos === 0 && r.s.fallidos === 0 && r.b.borrados === 0 && !r.p.hubo_fallo, JSON.stringify(r.filas));
  r = await resumen({ ...OK2, "Pacientes: borrar en Storage": { statusCode: 403, body: { message: "forbidden" } }, "Pacientes: marcar borrado_at": null });
  check("DELETE 403 -> fallidos = filas del lote, detalle con HTTP 403, hubo_fallo", r.p.fallidos === 2 && r.p.borrados === 0 && r.p.detalle.includes("HTTP 403") && r.p.detalle.includes("forbidden") && r.p.hubo_fallo === true && r.b.hubo_fallo === true, JSON.stringify(r.p));
  r = await resumen({ ...OK2, "Pacientes: borrar en Storage": { error: { message: "ECONNRESET" } }, "Pacientes: marcar borrado_at": null });
  check("DELETE con error de red -> fallidos, detalle con el error", r.p.fallidos === 2 && r.p.detalle.includes("ECONNRESET"), r.p.detalle);
  r = await resumen({ ...OK2, "Pacientes: marcar borrado_at": { error: "column \"borrado_at\" does not exist" } });
  check("UPDATE borrado_at falló -> borrados 2 pero fallidos 1 y detalle", r.p.borrados === 2 && r.p.fallidos === 1 && r.p.detalle.includes("UPDATE borrado_at") && r.p.hubo_fallo, JSON.stringify(r.p));
  r = await resumen({ ...OK2, "Pacientes: marcar borrado_at": { marcados: 1 } });
  check("UPDATE marcó 1 de 2 -> nota, sin fallo", r.p.fallidos === 0 && r.p.detalle.includes("marcado en 1 de 2"), r.p.detalle);
  r = await resumen({ ...OK2, "Pacientes: agrupar lote": AG({ error: "permission denied for table media_entrantes" }), "Pacientes: borrar en Storage": null, "Pacientes: marcar borrado_at": null });
  check("SELECT falló -> fallidos 1 con 'SELECT falló'", r.p.fallidos === 1 && r.p.detalle.includes("SELECT falló") && r.p.hubo_fallo, JSON.stringify(r.p));
  r = await resumen({ ...OK2, "Pacientes: agrupar lote": AG({ n: 1, filas: 0, smoke: true, paths: ["__retencion_smoke__/no-existe.bin"] }), "Pacientes: borrar en Storage": { statusCode: 200, body: [] }, "Pacientes: marcar borrado_at": { marcados: 0 } });
  check("smoke sin vencidos con DELETE 200 y UPDATE ('-') marcados 0 -> 0 borrados, 0 fallidos, nota smoke", r.p.borrados === 0 && r.p.fallidos === 0 && r.p.detalle.includes("smoke") && !r.p.hubo_fallo, JSON.stringify(r.p));
  check("  ...el path fantasma no cuenta como esperado: sin nota 'devolvió' ni advertencia", !r.p.detalle.includes("devolvió") && r.p.advertencia === null, r.p.detalle);
  r = await resumen({ ...OK2, "Pacientes: agrupar lote": AG({ n: 1, filas: 0, smoke: true, paths: ["__retencion_smoke__/no-existe.bin"] }), "Pacientes: borrar en Storage": { statusCode: 200, body: [] }, "Pacientes: marcar borrado_at": { error: "there is no parameter $1" } });
  check("smoke sin ids: si el UPDATE igual respondiera error, NO es fallo (nada que marcar) pero queda anotado", r.p.fallidos === 0 && !r.p.hubo_fallo && r.p.detalle.includes("sin ids que marcar"), JSON.stringify(r.p));
  r = await resumen({ ...OK2, "Pacientes: agrupar lote": AG({ n: 1, filas: 0, smoke: true, paths: ["__retencion_smoke__/no-existe.bin"] }), "Pacientes: borrar en Storage": { statusCode: 200, body: [] }, "Pacientes: marcar borrado_at": null });
  check("smoke sin ids y UPDATE no ejecutó -> tampoco es fallo", r.p.fallidos === 0 && !r.p.hubo_fallo, JSON.stringify(r.p));
  r = await resumen({ ...OK2, "Pacientes: agrupar lote": AG({ n: 2, filas: 1, ids: [F1.id], paths: [F1.path, "__retencion_smoke__/no-existe.bin"], smoke: true }), "Pacientes: borrar en Storage": { statusCode: 200, body: [{ name: F1.path }] }, "Pacientes: marcar borrado_at": { marcados: 1 } });
  check("smoke con 1 vencido real: Storage devolvió 1 de 1 esperado -> sin nota, borrados 1", r.p.borrados === 1 && r.p.fallidos === 0 && !r.p.detalle.includes("devolvió") && r.p.advertencia === null, JSON.stringify(r.p));
  r = await resumen({ ...OK2, "Pacientes: agrupar lote": AG({ n: 2, filas: 2, ids: [F1.id, F2.id] }), "Pacientes: marcar borrado_at": { error: "there is no parameter $1" } });
  check("con ids reales el UPDATE roto SÍ es fallo", r.p.fallidos === 1 && r.p.detalle.includes("UPDATE borrado_at"), JSON.stringify(r.p));
  const RET_PY = read("scripts/create_retencion_satelite.py");
  check("queryReplacement del UPDATE manda '-' cuando ids está vacío (n8n no pushea un parámetro '' → 'there is no parameter $1')",
    RET_PY.includes(`Q_MARCAR_PARAM = "={{ $('Pacientes: agrupar lote').first().json.ids.join('|') || '-' }}"`) && RET_PY.includes("Q_MARCAR, Q_MARCAR_PARAM)"), "");
  check("Q_PACIENTES filtra bucket = 'pacientes-media' (sin starvation por filas de otro bucket)", /Q_PACIENTES = \([\s\S]*?AND borrado_at IS NULL AND bucket = '\{BUCKET_PACIENTES\}'/.test(RET_PY), "");
  check("Q_PANEL excluye is_delete_marker", /Q_PANEL = \([\s\S]*?is_delete_marker IS NOT TRUE/.test(RET_PY), "");
  r = await resumen({ ...OK2, "Pacientes: agrupar lote": AG({ n: 1, filas: 0, smoke: true, paths: ["__retencion_smoke__/no-existe.bin"] }), "Pacientes: borrar en Storage": { statusCode: 500, body: "boom" }, "Pacientes: marcar borrado_at": null });
  check("smoke con DELETE 500 -> fallidos 1 (el humo detecta la falla)", r.p.fallidos === 1 && r.p.hubo_fallo, JSON.stringify(r.p));
  r = await resumen({ ...OK2, "Pacientes: agrupar lote": AG({ n: 2, filas: 2, ids: [F1.id, F2.id], omitidas: 1 }) });
  check("filas omitidas de otro bucket -> nota", r.p.detalle.includes("1 fila(s) de otro bucket"), r.p.detalle);
  r = await resumen({ ...OK2, "Bandeja: purgar": { error: "relation does not exist" } });
  check("bandeja falló -> fallidos 1", r.b.fallidos === 1 && r.b.detalle.includes("DELETE falló") && r.b.hubo_fallo, JSON.stringify(r.b));
  r = await resumen({ ...OK2, "Bandeja: purgar": null });
  check("bandeja no ejecutó -> fallidos 1", r.b.fallidos === 1 && r.b.detalle.includes("no ejecutó"), JSON.stringify(r.b));

  console.log("--- retención: armar aviso ---");
  const filasOk = [{ bucket: "pacientes-media", borrados: 2, fallidos: 0, detalle: "> 90 días", hubo_fallo: false }, { bucket: "panel-media", borrados: 0, fallidos: 0, detalle: "> 90 días", hubo_fallo: false }, { bucket: "mensajes_entrantes_live", borrados: 3, fallidos: 0, detalle: "> 365 días", hubo_fallo: false }];
  let av = await aviso(filasOk, [{ id: 1 }, { id: 2 }, { id: 3 }]);
  check("corrida limpia -> no avisa (0 items)", av.length === 0, JSON.stringify(av));
  const filasMal = [{ ...filasOk[0], fallidos: 2, borrados: 0, detalle: "> 90 días · DELETE Storage: HTTP 403 forbidden", hubo_fallo: true }, filasOk[1], filasOk[2]];
  av = await aviso(filasMal, [{ id: 1 }, { id: 2 }, { id: 3 }]);
  check("fallo -> 1 mensaje a Lucas con bucket, conteo y detalle", av.length === 1 && av[0].json.numero === LUCAS && av[0].json.texto.includes("pacientes-media: 2 fallido(s), 0 borrado(s)") && av[0].json.texto.includes("HTTP 403") && av[0].json.texto.startsWith("🧹 *Retención Áurea*"), JSON.stringify(av));
  check("  ...solo los buckets con fallo aparecen", !av[0].json.texto.includes("panel-media") && !av[0].json.texto.includes("mensajes_entrantes_live"), av[0].json.texto);
  av = await aviso(filasOk, [{ error: "relation \"retencion_log\" does not exist" }, { error: "x" }, { error: "x" }]);
  check("INSERT en retencion_log falló -> avisa aunque la limpieza salió bien", av.length === 1 && av[0].json.texto.includes("retencion_log: no se pudo escribir") && av[0].json.texto.includes("does not exist"), JSON.stringify(av));
  av = await fnAviso(inputDe([{ id: 1 }]), mk$({}), console);
  check("Resumen inaccesible y sin error de INSERT -> silencio", av.length === 0, JSON.stringify(av));
  const filasAdv = [{ ...filasOk[0], advertencia: "Storage no encontró NINGUNO de los 2 path(s) pedidos en pacientes-media: revisar…" }, filasOk[1], filasOk[2]];
  av = await aviso(filasAdv, [{ id: 1 }, { id: 2 }, { id: 3 }]);
  check("solo advertencia (0 fallidos) -> avisa igual, con título de advertencia", av.length === 1 && av[0].json.texto.includes("terminó con una advertencia") && av[0].json.texto.includes("NINGUNO") && av[0].json.texto.includes("pacientes-media: 2 borrado(s)"), JSON.stringify(av));
  av = await aviso(filasOk.map((f) => ({ ...f, advertencia: null })), [{ id: 1 }, { id: 2 }, { id: 3 }]);
  check("advertencia null explícita -> silencio", av.length === 0, JSON.stringify(av));

  console.log(`\n${fallos === 0 ? "✅" : "❌"} fallos: ${fallos}`);
  process.exit(fallos ? 1 : 0);
})();
