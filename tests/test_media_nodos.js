// tests/test_media_nodos.js — corre el JS REAL de "Media: Preparar" (media/preparar.js) y las expresiones de
// "Media: Marcar" (media/marcar_expr.js) y "Media: ¿Subida OK?" (media/subida_ok_expr.js) con node, mockeando el
// entorno de n8n ($input, $(), $execution, this.helpers.prepareBinaryData). Mismo harness que test_triaje_nodos.js.
// Fuente única: si alguien edita media/*.js, el test corre el código editado (y el apply lo embebe tal cual).
//
// Correr: node tests/test_media_nodos.js
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const PREPARAR = read("media/preparar.js");
const MARCAR_EXPR = read("media/marcar_expr.js").trim();
const SUBIDA_OK_EXPR = read("media/subida_ok_expr.js").trim();

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const fnPreparar = new AsyncFunction("$input", "$", "$execution", "console", PREPARAR);
// Las expresiones de n8n son JS puro dentro de {{ }}: se evalúan con $json y $ en scope.
const fnMarcar = new Function("$json", "$", "return (" + MARCAR_EXPR + ");");
const fnSubidaOk = new Function("$json", "$", "return (" + SUBIDA_OK_EXPR + ");");

// ---- fixtures binarios (magic bytes reales + relleno) ----
const relleno = (n) => Buffer.alloc(n, 0x41);
const JPEG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), relleno(60)]);
const PNG = Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), relleno(60)]);
const WEBP = Buffer.concat([Buffer.from("RIFF"), Buffer.from([0x10, 0, 0, 0]), Buffer.from("WEBPVP8 "), relleno(60)]);
const PDF = Buffer.concat([Buffer.from("%PDF-1.4\n"), relleno(60)]);
const OGG = Buffer.concat([Buffer.from("OggS"), relleno(60)]);
const MP4 = Buffer.concat([Buffer.from([0, 0, 0, 0x18]), Buffer.from("ftypmp42"), relleno(60)]);
const RAW = relleno(64); // sin firma reconocible

const TEL = "5491161461034";
const KEY = "3EB0ABCDEF1234567890AB";

// Arma el $ de n8n con el webhook (Info + Message) y Extraer Datos como los produce el v6 hoy.
function mkDollar({ mediaType, message, ed = {}, timestamp = "2026-09-06T15:30:00-03:00", preparar = null, extra = {}, info: infoExtra = {} }) {
  // `infoExtra` permite inyectar Chat / RecipientAlt / SenderAlt (grupos, status@broadcast): en un 1:1 el
  // webhook los trae, pero para los casos de siempre da igual y el filtro los tolera ausentes.
  const info = { ID: KEY, MediaType: mediaType, Type: "media", Timestamp: timestamp, IsFromMe: false, ...infoExtra };
  const edFull = { phone: TEL, key_id: KEY, text: "", fromMe: false, image_mime: "", document_filename: "", document_mime: "", ...ed };
  return (nombre) => {
    const data = {
      "Webhook - Evolution API": { body: { event: "Message", instanceName: "raquel", data: { Info: info, Message: message } } },
      "Edit Fields - Extraer Datos": edFull,
      "Media: Preparar": preparar || {},
      ...extra, // p. ej. { "Set Marker Imagen": { text: "…" } }; los nodos que no están tiran, como $() en n8n con un nodo sin ejecutar
    }[nombre];
    if (!data) throw new Error(`nodo desconocido ${nombre}`);
    return { first: () => ({ json: data }), item: { json: data }, isExecuted: true };
  };
}
// Mock de this.helpers.prepareBinaryData: devuelve lo que n8n devolvería en modo filesystem (sin `data` inline)
// más el buffer para poder verificar que se subiría el archivo correcto.
const ctxHelpers = (opts = {}) => ({
  helpers: {
    prepareBinaryData: async (buf, fileName, mimeType) => {
      if (opts.explota) throw new Error("disco lleno");
      return { id: "filesystem-v2:test", fileName, mimeType, fileSize: buf.length, fileExtension: (fileName.split(".").pop() || ""), __buf: buf };
    },
  },
});
async function run(text, c, ctx = ctxHelpers()) {
  const $input = { first: () => ({ json: { text } }), all: () => [{ json: { text } }] };
  const res = await fnPreparar.call(ctx, $input, mkDollar(c), { id: "exec1" }, console);
  if (!Array.isArray(res) || res.length !== 1) throw new Error("Preparar debe devolver exactamente 1 item");
  return res[0];
}

let fallos = 0;
const check = (nombre, cond, detalle) => { console.log(`${cond ? "OK  " : "FAIL"} ${nombre}${cond ? "" : " — " + detalle}`); if (!cond) fallos++; };
const HEX16 = /^[0-9a-f]{16}$/;
const sinBase64EnJson = (json) => !Object.values(json).some((v) => typeof v === "string" && v.length > 300);

(async () => {
  // 1) jpeg con caption (rama Imagen: text ya trae la clasificación + "Caption del paciente")
  let txt = "[IMAGEN] TIPO: FOTO_DENTAL\nDESCRIPCION: bracket suelto\nCaption del paciente: mirá mi diente";
  let it = await run(txt, { mediaType: "image", message: { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg", caption: "mirá mi diente" } }, ed: { text: "mirá mi diente", image_mime: "image/jpeg" } });
  let j = it.json;
  check("jpeg: hay_archivo + tipo image + mime/ext", j.hay_archivo === true && j.tipo === "image" && j.mime === "image/jpeg" && j.ext === "jpg", JSON.stringify(j));
  check("jpeg: text intacto", j.text === txt, j.text);
  check("jpeg: id 16 hex", HEX16.test(j.id), j.id);
  check("jpeg: path <tel>/<yyyy>/<mm>/<id>.jpg (hora Argentina)", j.path === `${TEL}/2026/09/${j.id}.jpg`, j.path);
  check("jpeg: caption, key_id, telefono, from_me, bytes", j.caption === "mirá mi diente" && j.key_id === KEY && j.telefono === TEL && j.from_me === false && j.bytes === JPEG.length, JSON.stringify(j));
  check("jpeg: binary.data con el buffer exacto, mime y filename <id>.jpg", it.binary && it.binary.data && it.binary.data.__buf.equals(JPEG) && it.binary.data.mimeType === "image/jpeg" && it.binary.data.fileName === `${j.id}.jpg`, JSON.stringify(it.binary));
  check("jpeg: json NO reexpide el base64 (R4)", sinBase64EnJson(j), Object.keys(j).join(","));
  check("jpeg: bucket destino", j.bucket_destino === "pacientes-media", j.bucket_destino);
  check("jpeg: json NO trae `bucket` (solo la fila de Postgres lo trae; Marcar se apoya en eso)", !("bucket" in j) && !("error" in j), Object.keys(j).join(","));

  // 2) png declarado png
  it = await run("[IMAGEN] TIPO: IMAGEN", { mediaType: "image", message: { base64: PNG.toString("base64"), imageMessage: { mimetype: "image/png" } }, ed: { image_mime: "image/png" } });
  check("png: ext png, caption null (sin texto)", it.json.tipo === "image" && it.json.mime === "image/png" && it.json.ext === "png" && it.json.caption === null, JSON.stringify(it.json));

  // 3) video mp4 (rama Otros: '[VIDEO]' + caption con espacio)
  it = await run("[VIDEO] mirá cómo se mueve", { mediaType: "video", message: { base64: MP4.toString("base64"), videoMessage: { mimetype: "video/mp4", seconds: 0 } }, ed: { text: "mirá cómo se mueve", video_url: "video" } });
  check("video: tipo video mp4, caption", it.json.tipo === "video" && it.json.mime === "video/mp4" && it.json.ext === "mp4" && it.json.caption === "mirá cómo se mueve" && it.json.text === "[VIDEO] mirá cómo se mueve", JSON.stringify(it.json));

  // 4) audio ptt con mime con parámetro (shape real de Evolution GO)
  it = await run("[AUDIO] hola quería saber si hay turno", { mediaType: "ptt", message: { base64: OGG.toString("base64"), audioMessage: { mimetype: "audio/ogg; codecs=opus", PTT: true, seconds: 7 } }, ed: { audio_url: "ptt" } });
  check("ptt: tipo audio, mime normalizado audio/ogg, ext ogg, sin caption", it.json.tipo === "audio" && it.json.mime === "audio/ogg" && it.json.ext === "ogg" && it.json.caption === null && it.json.mime_declarado === "audio/ogg", JSON.stringify(it.json));
  check("ptt: binary mimeType normalizado (Content-Type de Storage)", it.binary.data.mimeType === "audio/ogg", it.binary.data.mimeType);

  // 5) pdf con filename y caption (rama Documento)
  txt = "[DOCUMENTO: presupuesto.pdf (application/pdf)]\nCaption: te mando el presupuesto";
  it = await run(txt, { mediaType: "document", message: { base64: PDF.toString("base64"), documentMessage: { mimetype: "application/pdf", fileName: "presupuesto.pdf", pageCount: 2 } }, ed: { text: "te mando el presupuesto", document_filename: "presupuesto.pdf", document_mime: "application/pdf" } });
  check("pdf: tipo document, ext pdf, filename original, caption", it.json.tipo === "document" && it.json.ext === "pdf" && it.json.filename === "presupuesto.pdf" && it.json.caption === "te mando el presupuesto" && it.json.text === txt, JSON.stringify(it.json));
  check("pdf: binary fileName = original", it.binary.data.fileName === "presupuesto.pdf", it.binary.data.fileName);

  // 6) sticker estático: declara webp pero Evolution GO manda PNG (hallazgo 6/9) -> sniff manda
  it = await run("[STICKER]", { mediaType: "sticker", message: { base64: PNG.toString("base64"), stickerMessage: { mimetype: "image/webp", isAnimated: false } }, ed: { sticker_present: true } });
  check("sticker estático: tipo sticker, mime real png, declarado webp", it.json.tipo === "sticker" && it.json.mime === "image/png" && it.json.ext === "png" && it.json.mime_declarado === "image/webp", JSON.stringify(it.json));

  // 7) sticker animado real webp, MediaType 'user_created_sticker'
  it = await run("[STICKER]", { mediaType: "user_created_sticker", message: { base64: WEBP.toString("base64"), stickerMessage: { mimetype: "image/webp", isAnimated: true } }, ed: { sticker_present: true } });
  check("sticker animado: user_created_sticker -> sticker webp", it.json.tipo === "sticker" && it.json.mime === "image/webp" && it.json.ext === "webp", JSON.stringify(it.json));

  // 8) ubicación: sin base64 -> sin archivo, texto intacto, sin binario
  txt = "[UBICACION: -24.18,-65.29] acá estoy";
  it = await run(txt, { mediaType: "location", message: { locationMessage: { degreesLatitude: -24.18, degreesLongitude: -65.29 } }, ed: { text: "acá estoy", location_lat: "-24.18", location_lng: "-65.29" } });
  check("ubicación: hay_archivo false, motivo sin_base64, text intacto, sin binary", it.json.hay_archivo === false && it.json.motivo === "sin_base64" && it.json.text === txt && !it.binary, JSON.stringify(it));

  // 9) base64 vacío
  it = await run("[IMAGEN] x", { mediaType: "image", message: { base64: "", imageMessage: { mimetype: "image/jpeg" } } });
  check("base64 vacío: hay_archivo false", it.json.hay_archivo === false && it.json.motivo === "sin_base64" && it.json.text === "[IMAGEN] x", JSON.stringify(it.json));

  // 10) mime desconocido con filename -> ext del filename
  it = await run("[DOCUMENTO: datos.xyz (application/x-foo)]", { mediaType: "document", message: { base64: RAW.toString("base64"), documentMessage: { mimetype: "application/x-foo", fileName: "datos.XYZ" } } });
  check("mime desconocido + filename: ext del filename (minúscula), mime declarado", it.json.hay_archivo === true && it.json.ext === "xyz" && it.json.mime === "application/x-foo" && it.json.filename === "datos.XYZ", JSON.stringify(it.json));

  // 11) mime desconocido sin filename ni firma -> bin
  it = await run("[DOCUMENTO: archivo (desconocido)]", { mediaType: "document", message: { base64: RAW.toString("base64"), documentMessage: {} } });
  check("mime desconocido sin filename: ext bin, mime octet-stream", it.json.ext === "bin" && it.json.mime === "application/octet-stream" && it.json.filename === `${it.json.id}.bin`, JSON.stringify(it.json));

  // 12) documentWithCaptionMessage: Extraer Datos deja filename/mime vacíos; Preparar los rescata del sub-mensaje anidado
  it = await run("[DOCUMENTO: archivo (desconocido)]\nCaption: hola", { mediaType: "document", message: { base64: PDF.toString("base64"), documentWithCaptionMessage: { message: { documentMessage: { mimetype: "application/pdf", fileName: "orden.pdf", caption: "hola" } } } }, ed: { text: "hola" } });
  check("documentWithCaptionMessage: filename y mime anidados", it.json.tipo === "document" && it.json.filename === "orden.pdf" && it.json.ext === "pdf" && it.json.caption === "hola", JSON.stringify(it.json));

  // 13) Info.MediaType vacío con audioMessage (caso real 25/8) -> fallback por sub-mensaje
  it = await run("[AUDIO] texto", { mediaType: "", message: { base64: OGG.toString("base64"), audioMessage: { mimetype: "audio/ogg; codecs=opus", PTT: true } } });
  check("MediaType vacío: fallback por audioMessage", it.json.hay_archivo === true && it.json.tipo === "audio" && it.json.ext === "ogg" && it.json.media_type_origen === null, JSON.stringify(it.json));

  // 14) foto mandada "como documento" (visto 2 veces en 13 días): tipo document, ext jpg
  it = await run("[DOCUMENTO: IMG_20260901.jpg (image/jpeg)]", { mediaType: "document", message: { base64: JPEG.toString("base64"), documentMessage: { mimetype: "image/jpeg", fileName: "IMG_20260901.jpg" } } });
  check("jpg como documento: tipo document, mime image/jpeg, ext jpg", it.json.tipo === "document" && it.json.mime === "image/jpeg" && it.json.ext === "jpg" && it.json.filename === "IMG_20260901.jpg", JSON.stringify(it.json));

  // 15) archivo por encima del tope -> no se sube, texto intacto
  const grande = Buffer.alloc(20 * 1024 * 1024 + 1, 0x42);
  it = await run("[VIDEO]", { mediaType: "video", message: { base64: grande.toString("base64"), videoMessage: { mimetype: "video/mp4" } } });
  check("archivo > 20 MB: hay_archivo false, motivo archivo_muy_grande", it.json.hay_archivo === false && String(it.json.motivo).startsWith("archivo_muy_grande") && it.json.text === "[VIDEO]", JSON.stringify(it.json));

  // 16) prepareBinaryData explota -> hay_archivo false con motivo error, texto intacto (el bot sigue)
  it = await run("[IMAGEN] TIPO: COMPROBANTE", { mediaType: "image", message: { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg" } } }, ctxHelpers({ explota: true }));
  check("excepción interna: hay_archivo false, motivo error:*, text intacto", it.json.hay_archivo === false && it.json.motivo === "error:disco lleno" && it.json.text === "[IMAGEN] TIPO: COMPROBANTE" && !it.binary, JSON.stringify(it));

  // 17) sin teléfono -> no se sube
  it = await run("[IMAGEN] x", { mediaType: "image", message: { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg" } }, ed: { phone: "" } });
  check("sin teléfono: hay_archivo false", it.json.hay_archivo === false && it.json.motivo === "sin_telefono", JSON.stringify(it.json));

  // 17b) teléfono con sufijo (Extraer Datos cae a Info.Chat sin @s.whatsapp.net): columna VERBATIM (= Inbox Live /
  //      session_id, el panel cruza por igualdad) y path con dígitos (Storage no acepta '@' en la key)
  it = await run("[IMAGEN] x", { mediaType: "image", message: { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg" } }, ed: { phone: "5493885786946@lid" } });
  check("teléfono '@lid': telefono verbatim y path solo dígitos", it.json.hay_archivo === true && it.json.telefono === "5493885786946@lid" && it.json.path.startsWith("5493885786946/2026/09/"), JSON.stringify(it.json));
  it = await run("[IMAGEN] x", { mediaType: "image", message: { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg" } }, ed: { phone: "status@broadcast" } });
  check("teléfono sin dígitos: hay_archivo false (sin_telefono)", it.json.hay_archivo === false && it.json.motivo === "sin_telefono", JSON.stringify(it.json));

  // 17c) sticker cuyo contenido no es una imagen reconocible (Lottie): se sube con mime genérico → el panel lo pinta como chip
  it = await run("[STICKER]", { mediaType: "sticker", message: { base64: RAW.toString("base64"), stickerMessage: { mimetype: "image/webp", isLottie: true } } });
  check("sticker Lottie: tipo sticker, mime octet-stream, ext bin, declarado webp", it.json.hay_archivo === true && it.json.tipo === "sticker" && it.json.mime === "application/octet-stream" && it.json.ext === "bin" && it.json.mime_declarado === "image/webp", JSON.stringify(it.json));
  it = await run("[IMAGEN] x", { mediaType: "image", message: { base64: RAW.toString("base64"), imageMessage: { mimetype: "image/jpeg" } } });
  check("imagen sin firma reconocible: conserva el mime declarado (solo el sticker cae a octet-stream)", it.json.mime === "image/jpeg", it.json.mime);

  // 18) $input sin text (defensivo): text = '' y no explota
  {
    const $input = { first: () => ({ json: {} }), all: () => [{ json: {} }] };
    const res = await fnPreparar.call(ctxHelpers(), $input, mkDollar({ mediaType: "image", message: { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg" } } }), { id: "e" }, console);
    check("input sin text: text '' y sube igual", res[0].json.text === "" && res[0].json.hay_archivo === true, JSON.stringify(res[0].json));
  }

  // 19) ids únicos y con formato en 200 corridas
  {
    const ids = new Set();
    for (let i = 0; i < 200; i++) {
      const r = await run("[IMAGEN] x", { mediaType: "image", message: { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg" } } });
      ids.add(r.json.id);
    }
    check("200 ids: todos 16 hex y únicos", ids.size === 200 && [...ids].every((x) => HEX16.test(x)), `${ids.size}`);
  }

  // 20) gif -> video; prefijo data: se tolera
  it = await run("[VIDEO]", { mediaType: "gif", message: { base64: "data:video/mp4;base64," + MP4.toString("base64"), videoMessage: { mimetype: "video/mp4", gifPlayback: true } } });
  check("gif: tipo video, prefijo data: removido, bytes correctos", it.json.tipo === "video" && it.json.ext === "mp4" && it.json.bytes === MP4.length, JSON.stringify(it.json));

  // 21) fecha del path en hora Argentina: 23:30 del 31/8 (-03:00) es 02:30Z del 1/9 -> debe quedar 2026/08
  it = await run("[IMAGEN] x", { mediaType: "image", message: { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg" } }, timestamp: "2026-08-31T23:30:00-03:00" });
  check("path usa mes de Argentina, no UTC", it.json.path.startsWith(`${TEL}/2026/08/`), it.json.path);
  it = await run("[IMAGEN] x", { mediaType: "image", message: { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg" } }, timestamp: "no-es-fecha" });
  check("Timestamp inválido: usa ahora, no explota", it.json.hay_archivo === true && /^\d+\/\d{4}\/\d{2}\/[0-9a-f]{16}\.jpg$/.test(it.json.path), it.json.path);

  // 22) mp4 con firma pero declarado audio -> audio/mp4 (m4a)
  it = await run("[AUDIO] x", { mediaType: "audio", message: { base64: MP4.toString("base64"), audioMessage: { mimetype: "audio/mp4" } } });
  check("audio/mp4 con ftyp: mime audio/mp4, ext m4a", it.json.tipo === "audio" && it.json.mime === "audio/mp4" && it.json.ext === "m4a", JSON.stringify(it.json));

  // 23) GRUPOS Y ESTADOS (2026-09-07, R1): el filtro vive acá porque este archivo lo comparten las dos ramas
  //     y la del STAFF (Es fromMe?[0]) no pasa por "Filtrar duplicados y basura". Para la del paciente es no-op.
  {
    const GRUPO = "120363407321448469@g.us"; // grupo de derivaciones
    const img = { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg" } };
    // (a) foto al grupo: Extraer Datos cae a Info.Sender (el número del propio consultorio) → phone válido,
    //     así que sin el filtro se subiría al bucket bajo el número de la clínica.
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: TEL, fromMe: true }, info: { Chat: GRUPO, Sender: `${TEL}@s.whatsapp.net`, IsFromMe: true } });
    check("grupo (@g.us en Info.Chat): hay_archivo false, motivo grupo_o_estado, text intacto, sin binary", it.json.hay_archivo === false && it.json.motivo === "grupo_o_estado" && it.json.text === "[IMAGEN] x" && !it.binary, JSON.stringify(it.json));
    // (b) el jid del grupo llegando como phone (Extraer Datos sin ningún @s.whatsapp.net)
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: GRUPO }, info: { Chat: GRUPO } });
    check("grupo en el phone: grupo_o_estado (no sube bajo el número del grupo)", it.json.hay_archivo === false && it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));
    // (c) estado de WhatsApp publicado desde el celular del consultorio
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: TEL, fromMe: true }, info: { Chat: "status@broadcast", Sender: `${TEL}@s.whatsapp.net`, IsFromMe: true } });
    check("status@broadcast: grupo_o_estado", it.json.hay_archivo === false && it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));
    // (d) el grupo escondido en RecipientAlt / SenderAlt (por si Evolution moviera el jid de campo)
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, info: { RecipientAlt: GRUPO } });
    check("grupo en Info.RecipientAlt: grupo_o_estado", it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, info: { SenderAlt: GRUPO } });
    check("grupo en Info.SenderAlt: grupo_o_estado", it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));
    // (e) largo del teléfono: 18 dígitos (un jid de grupo sin '@g.us') no pasa; 8 y 15 sí (E.164 real)
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: "120363407321448469" } });
    check("18 dígitos (jid de grupo pelado): grupo_o_estado", it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: "1234567" } });
    check("7 dígitos: grupo_o_estado", it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));
    for (const tel of ["12345678", "549388578694", "541112345678901"]) {
      it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: tel } });
      check(`teléfono real de ${tel.length} dígitos: sube (no lo caza el filtro)`, it.json.hay_archivo === true && it.json.path.startsWith(`${tel}/`), JSON.stringify(it.json));
    }
    // (e2) LISTAS DE DIFUSIÓN Y CANALES (2026-09-07): familias hermanas de @g.us que el blacklist viejo
    //      (igualdad con 'status@broadcast') NO cazaba. Acá van con fromMe:false — o sea, la rama del
    //      PACIENTE —, así que lo que las frena es el blacklist, no el whitelist del staff.
    for (const jid of ["120363407321448469@broadcast", "1234567890@broadcast", "120363407321448469@newsletter"]) {
      it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: TEL }, info: { Chat: jid } });
      check(`${jid}: grupo_o_estado (blacklist, vale para las dos ramas)`, it.json.hay_archivo === false && it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));
      it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: TEL }, info: { RecipientAlt: jid } });
      check(`${jid} en RecipientAlt: grupo_o_estado`, it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));
    }
    // (e3) WHITELIST del STAFF: con fromMe true, Info.Chat TIENE que ser un 1:1 '@s.whatsapp.net'.
    //      Cierra @lid y cualquier familia de JID futura, que un blacklist deja pasar por definición.
    for (const jid of ["108187302929820@lid", "120363407321448469@newsletter", "1234567890@broadcast", ""]) {
      it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: TEL, fromMe: true }, info: { Chat: jid, Sender: `${TEL}@s.whatsapp.net`, IsFromMe: true } });
      check(`staff con Chat '${jid || "(vacio)"}' (no 1:1): grupo_o_estado`, it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));
    }
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: TEL, fromMe: true }, info: { Chat: `${TEL}@s.whatsapp.net`, IsFromMe: true } });
    check("staff con Chat 1:1: sube (el whitelist no rompe el caso bueno)", it.json.hay_archivo === true && it.json.from_me === true, JSON.stringify(it.json));
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: TEL, fromMe: true }, info: { Chat: `${TEL}:12@s.whatsapp.net`, IsFromMe: true } });
    check("staff con Chat 1:1 y sufijo de dispositivo (':12'): sube igual", it.json.hay_archivo === true, JSON.stringify(it.json));
    // (e4) El whitelist es SOLO del staff: con fromMe false, un '@lid' de PACIENTE sigue subiendo (17b).
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: `${TEL}@lid` }, info: { Chat: `${TEL}@lid` } });
    check("paciente con jid '@lid': sigue subiendo (el whitelist no toca la rama del paciente)", it.json.hay_archivo === true && it.json.telefono === `${TEL}@lid`, JSON.stringify(it.json));
    // (e5) BORDE del guard de largo con LID (decisión explícita, 2026-09-07): los LID de WhatsApp suelen
    //      ser de 15 dígitos y entran; uno de 16-17 se DESCARTA a propósito. Fallar cerrado: un jid de
    //      grupo pelado son 18 dígitos y el margen es de un solo dígito, así que subir un archivo bajo un
    //      número que no es un teléfono (conversación fantasma) es peor que perder el adjunto — el chat
    //      sigue mostrando el chip de siempre, que es el comportamiento de hoy. Si algún día aparece un
    //      LID largo real, se sube el tope acá y se re-corre este test (queda anotado en el backlog).
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: "108187302929820@lid" }, info: { Chat: "108187302929820@lid" } });
    check("LID de 15 dígitos (el largo típico): sube", it.json.hay_archivo === true && it.json.path.startsWith("108187302929820/"), JSON.stringify(it.json));
    for (const lid of ["1234567890123456@lid", "12345678901234567@lid"]) {
      it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: lid }, info: { Chat: lid } });
      check(`LID de ${lid.split("@")[0].length} dígitos: grupo_o_estado (descarte deliberado)`, it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));
    }
    // (f) NO REGRESIÓN: 1:1 normal con Info.Chat presente sigue subiendo, y los motivos viejos no cambian
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, info: { Chat: `${TEL}@s.whatsapp.net` } });
    check("1:1 con Info.Chat normal: sube igual que siempre", it.json.hay_archivo === true && it.json.tipo === "image", JSON.stringify(it.json));
    it = await run("[IMAGEN] x", { mediaType: "image", message: img, ed: { phone: "" }, info: { Chat: GRUPO } });
    check("sin teléfono Y grupo: gana 'sin_telefono' (el orden de los guards no cambió)", it.json.motivo === "sin_telefono", JSON.stringify(it.json));
    it = await run("[UBICACION: x]", { mediaType: "location", message: { locationMessage: {} }, info: { Chat: GRUPO } });
    check("grupo sin archivo: gana 'sin_base64' (el filtro corre después)", it.json.motivo === "sin_base64", JSON.stringify(it.json));
  }

  // ---- Expresión de "Media: Marcar" (sufijo solo si el INSERT devolvió la fila con el mismo id) ----
  const P = { text: "[IMAGEN] TIPO: FOTO_DENTAL DESCRIPCION: x", hay_archivo: true, id: "3fa9c2e1b7d04a58", path: `${TEL}/2026/09/3fa9c2e1b7d04a58.jpg` };
  const $M = mkDollar({ mediaType: "image", message: {}, preparar: P });
  const fila = { id: "3fa9c2e1b7d04a58", key_id: KEY, telefono: TEL, from_me: false, tipo: "image", mime: "image/jpeg", bucket: "pacientes-media", path: P.path, bytes: 64, filename: "x.jpg", caption: null, created_at: "2026-09-06T18:30:00+00:00" };
  check("marcar: INSERT OK -> sufijo ' [MEDIA:<id>]'", fnMarcar(fila, $M) === P.text + " [MEDIA:3fa9c2e1b7d04a58]", fnMarcar(fila, $M));
  check("marcar: INSERT con error (onError continue) -> sin sufijo", fnMarcar({ message: "duplicate key", error: { message: "duplicate key" } }, $M) === P.text, fnMarcar({ error: {} }, $M));
  check("marcar: rama ¿Hay archivo? = false ($json es Preparar) -> sin sufijo", fnMarcar({ ...P, hay_archivo: false, motivo: "sin_base64" }, mkDollar({ mediaType: "location", message: {}, preparar: { ...P, hay_archivo: false } })) === P.text, "");
  check("marcar: rama ¿Subida OK? = false ($json es la respuesta HTTP) -> sin sufijo", fnMarcar({ statusCode: 400, body: { statusCode: "400", error: "Bucket not found", message: "Bucket not found" }, headers: {} }, $M) === P.text, "");
  check("marcar: fila con OTRO id -> sin sufijo", fnMarcar({ ...fila, id: "ffffffffffffffff" }, $M) === P.text, "");
  check("marcar: Preparar con hay_archivo true pero $json = Preparar (cable mal) -> sin sufijo", fnMarcar(P, $M) === P.text, "");
  check("marcar: texto con saltos de línea y caption se preserva", fnMarcar(fila, mkDollar({ mediaType: "image", message: {}, preparar: { ...P, text: "[DOCUMENTO: a.pdf (application/pdf)]\nCaption: hola, con coma" } })) === "[DOCUMENTO: a.pdf (application/pdf)]\nCaption: hola, con coma [MEDIA:3fa9c2e1b7d04a58]", "");

  {
    // Preparar falló FUERA de su try/catch (onError=continue emite {error} sin text): el marcador se rescata del Set Marker que corrió
    const $E = mkDollar({ mediaType: "image", message: {}, preparar: { error: { message: "Sandbox killed" } }, extra: { "Set Marker Imagen": { text: "[IMAGEN] TIPO: FOTO_DENTAL" } } });
    check("marcar: Preparar {error} sin text -> texto del Set Marker que corrió, sin sufijo", fnMarcar({ error: { message: "Sandbox killed" } }, $E) === "[IMAGEN] TIPO: FOTO_DENTAL", fnMarcar({ error: {} }, $E));
    const $E2 = mkDollar({ mediaType: "image", message: {}, preparar: { error: { message: "x" } } });
    check("marcar: Preparar {error} y ningún Set Marker accesible -> '' sin explotar", fnMarcar({ error: {} }, $E2) === "", "");
    const $E3 = mkDollar({ mediaType: "image", message: {}, preparar: { text: "", hay_archivo: true }, extra: { "Set Marker Otros": { text: "[VIDEO]" } } });
    check("marcar: Preparar con text '' legítimo (input sin text) -> no toca el Set Marker", fnMarcar({ error: {} }, $E3) === "", "");
  }
  // Las expresiones van dentro de ={{ … }}: un '}}' interno cerraría la expresión de n8n antes de tiempo
  check("expresiones sin '}}' interno", !MARCAR_EXPR.includes("}}") && !SUBIDA_OK_EXPR.includes("}}"), "");

  // ---- Expresión de "Media: ¿Subida OK?" (fullResponse + neverError) ----
  check("subida ok: 200 con Key -> true", fnSubidaOk({ statusCode: 200, body: { Key: "pacientes-media/x.jpg", Id: "u" }, headers: {} }) === true, "");
  check("subida ok: '200' string -> true", fnSubidaOk({ statusCode: "200", body: { Key: "k" } }) === true, "");
  check("subida ok: 400 Storage -> false", fnSubidaOk({ statusCode: 400, body: { statusCode: "400", error: "Bucket not found", message: "x" } }) === false, "");
  check("subida ok: 200 pero body con error -> false", fnSubidaOk({ statusCode: 200, body: { error: "raro" } }) === false, "");
  check("subida ok: error de red (onError continue) -> false", fnSubidaOk({ error: { message: "ETIMEDOUT" } }) === false, "");
  check("subida ok: item vacío -> false", fnSubidaOk({}) === false, "");

  console.log(`\n${fallos === 0 ? "✅" : "❌"} fallos: ${fallos}`);
  process.exit(fallos ? 1 : 0);
})().catch((e) => { console.error("EXCEPCIÓN", e); process.exit(2); });
