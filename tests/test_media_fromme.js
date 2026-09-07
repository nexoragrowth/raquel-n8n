// tests/test_media_fromme.js — rama STAFF (fromMe) de la cadena Media del v6. Corre con node el codigo REAL
// de los dos unicos archivos propios de esta rama, mockeando el entorno de n8n ($json, $(), $input,
// this.helpers). Mismo harness que tests/test_media_nodos.js.
//
//   1) media/actualizar_memoria_staff.js — expresion del `query` del nodo Postgres "Media: Actualizar
//      memoria (staff)", que agrega ' [MEDIA:<id>]' + media_id/media_tipo a la fila de memoria YA escrita.
//      Se testea el SQL que genera en cada camino: el feliz (por id) y todos los de falla, que son NOOP
//      (falla cerrado: sin el id del INSERT no se adivina a que fila pegarle — ver seccion 4).
//   2) media/preparar.js — los casos de JID que NO es un chat 1:1 (grupo, estado, lista de difusion,
//      canal, LID), que en esta rama son la unica defensa (la del paciente ya viene filtrada por
//      "Filtrar duplicados y basura"). El resto de Preparar lo cubre tests/test_media_nodos.js.
//
// Lo que este test NO cubre a proposito: "Build fromMe AI memory" NO SE TOCA con este cambio (la fila que
// escribe sigue siendo byte a byte la de hoy), asi que no hay nada nuevo que verificar de ese lado.
//
// Correr: node tests/test_media_fromme.js
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(ROOT, p), "utf8");
const ACTUALIZAR = read("media/actualizar_memoria_staff.js").trim();
const PREPARAR = read("media/preparar.js");

// Las expresiones de n8n son JS puro dentro de llaves dobles: se evaluan con $json y $ en scope.
const fnActualizar = new Function("$json", "$", "return (" + ACTUALIZAR + ");");
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const fnPreparar = new AsyncFunction("$input", "$", "$execution", "console", PREPARAR);

const TEL = "5493885786946";            // telefono del PACIENTE (el chat), no el del consultorio
const CLINICA = "5493884445566";        // numero del consultorio (el que manda)
const KEY = "3EB0F1A2B3C4D5E6F70819";
const ID = "3fa9c2e1b7d04a58";
const GRUPO = "120363407321448469@g.us"; // grupo de derivaciones
const PLACEHOLDER = "[mensaje multimedia enviado por la doctora/secretaria - sin texto adjunto]";
const TAG =
  "[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria desde el WhatsApp del consultorio. " +
  "NO es output tuyo, es un humano atendiendo este chat. Mantente en silencio y NO respondas en este chat " +
  "hasta que un admin diga /bot on.]: ";

// $ de n8n: los nodos que NO estan en el mapa tiran, igual que $('X') en n8n con un nodo que no ejecuto.
function mkDollar(nodos) {
  return (nombre) => {
    if (!(nombre in nodos)) throw new Error(`nodo desconocido ${nombre}`);
    const data = nodos[nombre];
    return { first: () => ({ json: data }), item: { json: data }, isExecuted: true };
  };
}
// Salida de "Media: Preparar (staff)" cuando SI hay archivo (shape real de media/preparar.js)
const prep = (extra = {}) => ({
  text: "", hay_archivo: true, id: ID, key_id: KEY, telefono: TEL, from_me: true, tipo: "image",
  mime: "image/jpeg", mime_declarado: "image/jpeg", ext: "jpg", bucket_destino: "pacientes-media",
  path: `${TEL}/2026/09/${ID}.jpg`, bytes: 103423, filename: `${ID}.jpg`, caption: null, media_type_origen: "image",
  ...extra,
});
// Fila que devuelve "Media: Registrar (staff)" (el nodo insert de n8n hace RETURNING *)
const fila = (extra = {}) => ({
  id: ID, key_id: KEY, telefono: TEL, from_me: true, tipo: "image", mime: "image/jpeg", bucket: "pacientes-media",
  path: `${TEL}/2026/09/${ID}.jpg`, bytes: 103423, filename: `${ID}.jpg`, caption: null,
  created_at: "2026-09-07T17:05:42.120Z", borrado_at: null, ...extra,
});
// Salidas de los dos nodos de memoria que el UPDATE puede mirar.
// OJO: n8n/node-postgres devuelven los bigint como STRING ("6516"), verificado en "Check Session Age".
const savePg = (id = "6516") => (id === null ? { success: true } : { id });
const buildMem = (content = TAG + PLACEHOLDER, session_id = TEL) => ({
  session_id,
  message: JSON.stringify({
    type: "ai", content, additional_kwargs: { source: "wa_outbound", from_iri_or_dra: true, was_multimedia: true },
    response_metadata: {}, tool_calls: [], invalid_tool_calls: [],
  }),
});
// Mapa completo de nodos para el camino feliz; cada test pisa lo que necesita.
const nodos = (o = {}) => ({
  "Media: Preparar (staff)": o.preparar === undefined ? prep() : o.preparar,
  "Postgres - Save fromMe": o.savePg === undefined ? savePg() : o.savePg,
  "Build fromMe AI memory": o.mem === undefined ? buildMem() : o.mem,
});
// Quita del mapa los nodos que "no ejecutaron" (el $ del harness tira con ellos, como n8n).
const sinNodos = (mapa, ...fuera) => {
  const m = { ...mapa };
  for (const f of fuera) delete m[f];
  return m;
};
const sql = ($json, mapa) => fnActualizar($json, mkDollar(mapa));

const NOOP = "SELECT 1 WHERE false";
let fallos = 0;
const check = (nombre, cond, detalle) => { console.log(`${cond ? "OK  " : "FAIL"} ${nombre}${cond ? "" : " — " + detalle}`); if (!cond) fallos++; };

// Harness de media/preparar.js (identico al de test_media_nodos.js, recortado a lo que usa esta rama).
const relleno = (n) => Buffer.alloc(n, 0x41);
const JPEG = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), relleno(60)]);
const ctxHelpers = () => ({
  helpers: {
    prepareBinaryData: async (buf, fileName, mimeType) => ({ id: "filesystem-v2:test", fileName, mimeType, fileSize: buf.length, __buf: buf }),
  },
});
async function preparar({ text = "", info = {}, ed = {}, message = null }) {
  const infoFull = { ID: KEY, MediaType: "image", Type: "media", Timestamp: "2026-09-07T15:30:00-03:00", IsFromMe: true, ...info };
  const edFull = { phone: TEL, key_id: KEY, text: "", fromMe: true, image_mime: "image/jpeg", document_filename: "", document_mime: "", ...ed };
  const msg = message || { base64: JPEG.toString("base64"), imageMessage: { mimetype: "image/jpeg" } };
  const $ = (nombre) => {
    const data = {
      "Webhook - Evolution API": { body: { event: "Message", instanceName: "raquel", data: { Info: infoFull, Message: msg } } },
      "Edit Fields - Extraer Datos": edFull,
    }[nombre];
    if (!data) throw new Error(`nodo desconocido ${nombre}`);
    return { first: () => ({ json: data }), item: { json: data }, isExecuted: true };
  };
  const $input = { first: () => ({ json: { text } }), all: () => [{ json: { text } }] };
  const res = await fnPreparar.call(ctxHelpers(), $input, $, { id: "exec1" }, console);
  if (!Array.isArray(res) || res.length !== 1) throw new Error("Preparar debe devolver exactamente 1 item");
  return res[0];
}

(async () => {
  // =========================================================================================
  // 1) CAMINO FELIZ: la fila de media_entrantes volvio, el UPDATE toca UNA fila por id
  // =========================================================================================
  {
    const q = sql(fila(), nodos());
    check("1a happy: es un UPDATE de n8n_chat_histories", q.startsWith("UPDATE n8n_chat_histories SET message = "), q);
    check("1b happy: WHERE por el id que devolvio el INSERT (una sola fila, sin comillas)", q.includes("WHERE id = 6516 AND"), q);
    check("1c happy: agrega el token con el formato exacto del contrato", q.includes(`to_jsonb((message->>'content') || ' [MEDIA:${ID}]')`), q);
    check("1d happy: suma media_id y media_tipo a additional_kwargs sin pisar lo que ya hay", q.includes(`COALESCE(message->'additional_kwargs', '{}'::jsonb) || '{"media_id":"${ID}","media_tipo":"image"}'::jsonb`), q);
    check("1e happy: idempotente (no toca una fila que ya tiene token)", q.includes("AND message->>'content' NOT LIKE '%[MEDIA:%'"), q);
    check("1f happy: RETURNING id (para ver en la ejecucion si toco la fila)", q.endsWith("RETURNING id"), q);
    check("1g happy: NO usa el fallback por content cuando hay id", !q.includes("SELECT id FROM n8n_chat_histories"), q);
    check("1h happy: no hay placeholders de pg-promise ($1/$2) ni '$' sueltos en el SQL", !/\$/.test(q), q);
    check("1i happy: una sola fila — un unico predicado de identidad", (q.match(/WHERE id = /g) || []).length === 1, q);
  }

  // =========================================================================================
  // 2) TIPOS: media_tipo sale del whitelist; cualquier otra cosa queda null (nunca al SQL crudo)
  // =========================================================================================
  {
    for (const t of ["image", "video", "audio", "document", "sticker"]) {
      const q = sql(fila({ tipo: t }), nodos({ preparar: prep({ tipo: t }) }));
      check(`2a tipo ${t}: viaja en las kwargs`, q.includes(`"media_tipo":"${t}"`), q);
    }
    const q = sql(fila(), nodos({ preparar: prep({ tipo: "'; DROP TABLE n8n_chat_histories; --" }) }));
    check("2b tipo fuera del whitelist (intento de inyeccion): media_tipo null y nada del payload en el SQL", q.includes('"media_tipo":null') && !q.includes("DROP TABLE"), q);
  }

  // =========================================================================================
  // 3) NO-OP: si "Media: Registrar (staff)" no devolvio LA fila, el UPDATE no existe
  // =========================================================================================
  {
    check("3a Registrar con error (onError continue) -> no-op", sql({ error: { message: "duplicate key" } }, nodos()) === NOOP, sql({ error: {} }, nodos()));
    check("3b fila de OTRO bucket -> no-op", sql(fila({ bucket: "panel-media" }), nodos()) === NOOP, "");
    check("3c fila con OTRO id -> no-op", sql(fila({ id: "ffffffffffffffff" }), nodos()) === NOOP, "");
    check("3d fila sin id -> no-op", sql(fila({ id: null }), nodos()) === NOOP, "");
    check("3e Preparar con hay_archivo false -> no-op", sql(fila(), nodos({ preparar: { text: "", hay_archivo: false, motivo: "sin_base64" } })) === NOOP, "");
    check("3f Preparar con hay_archivo false y motivo grupo_o_estado -> no-op (nada del grupo llega a la memoria)", sql(fila(), nodos({ preparar: { text: "", hay_archivo: false, motivo: "grupo_o_estado" } })) === NOOP, "");
    check("3g id de Preparar que no es 16 hex -> no-op (nunca va crudo al SQL)", sql(fila({ id: "NO-HEX" }), nodos({ preparar: prep({ id: "NO-HEX" }) })) === NOOP, "");
    check("3h id de 16 hex en MAYUSCULAS (no es el formato del contrato) -> no-op", sql(fila({ id: ID.toUpperCase() }), nodos({ preparar: prep({ id: ID.toUpperCase() }) })) === NOOP, "");
    check("3i $json vacio (cable mal) -> no-op", sql({}, nodos()) === NOOP, "");
    check("3j $json = la salida de Preparar (cable mal) -> no-op", sql(prep(), nodos()) === NOOP, "");
    check("3k respuesta HTTP de la subida en vez de la fila -> no-op", sql({ statusCode: 200, body: { Key: "pacientes-media/x.jpg" } }, nodos()) === NOOP, "");
    check("3l 'Media: Preparar (staff)' no ejecuto ($() tira) -> no-op sin explotar", sql(fila(), sinNodos(nodos(), "Media: Preparar (staff)")) === NOOP, "");
    check("3m Preparar devolvio {error} (murio fuera del try) -> no-op", sql(fila(), nodos({ preparar: { error: { message: "Sandbox killed" } } })) === NOOP, "");
  }

  // =========================================================================================
  // 4) SIN id -> NOOP (falla cerrado). Antes habia un fallback heuristico por session_id+content y se
  //    saco: bajo concurrencia le pegaba el token a la fila EQUIVOCADA (dos adjuntos sin caption al
  //    mismo paciente comparten el content exacto). Mostrar la foto de otra burbuja es peor que no
  //    mostrar ninguna. Estos tests son el candado de esa decision.
  // =========================================================================================
  {
    check("4a sin id (RETURNING revertido / n8n viejo) -> NOOP", sql(fila(), nodos({ savePg: savePg(null) })) === NOOP, sql(fila(), nodos({ savePg: savePg(null) })));
    // NINGUN camino puede volver a generar el subselect heuristico (se prueban todos los que existen).
    const todosLosCaminos = [
      sql(fila(), nodos()), sql(fila(), nodos({ savePg: savePg(null) })), sql({}, nodos()),
      sql(fila(), nodos({ savePg: { id: "-3" } })), sql(fila(), nodos({ mem: buildMem("") })),
      sql(fila(), sinNodos(nodos(), "Build fromMe AI memory")),
      sql(fila(), sinNodos(nodos(), "Postgres - Save fromMe")),
    ];
    check("4b ningun camino genera el subselect por session_id + content", todosLosCaminos.every((q) => !q.includes("SELECT id FROM n8n_chat_histories") && !q.includes("ORDER BY") && !q.includes("session_id")), JSON.stringify(todosLosCaminos));
    check("4c la expresion ya no LEE 'Build fromMe AI memory' (no depende de su content byte a byte)", !ACTUALIZAR.includes("nodo('Build fromMe AI memory')"), "");
    check("4c2 y por eso da igual que ese nodo no haya ejecutado: sigue el camino por id", sql(fila(), sinNodos(nodos(), "Build fromMe AI memory")).includes("WHERE id = 6516 AND"), sql(fila(), sinNodos(nodos(), "Build fromMe AI memory")));

    check("4d id como number (por si algun dia n8n deja de mandarlo como string)", sql(fila(), nodos({ savePg: { id: 6516 } })).includes("WHERE id = 6516 AND"), "");
    check("4e id no numerico -> NOOP, no se inyecta crudo", sql(fila(), nodos({ savePg: { id: "6516; DROP TABLE x" } })) === NOOP, "");
    check("4f id negativo -> NOOP", sql(fila(), nodos({ savePg: { id: "-3" } })) === NOOP, "");
    check("4g id 0 y con ceros a la izquierda -> NOOP (bigserial arranca en 1)", sql(fila(), nodos({ savePg: { id: "0" } })) === NOOP && sql(fila(), nodos({ savePg: { id: "007" } })) === NOOP, "");
    check("4h id con espacios / vacio -> NOOP", sql(fila(), nodos({ savePg: { id: " 6516 " } })) === NOOP && sql(fila(), nodos({ savePg: { id: "" } })) === NOOP, "");
    check("4i 'Postgres - Save fromMe' no ejecuto ($() tira) -> NOOP sin explotar", sql(fila(), sinNodos(nodos(), "Postgres - Save fromMe")) === NOOP, "");
    check("4j 'Postgres - Save fromMe' devolvio {success:true} (la query de HOY, sin RETURNING) -> NOOP", sql(fila(), nodos({ savePg: { success: true } })) === NOOP, "");

    // EL CASO CONCURRENTE que motivo sacar el fallback: dos ejecuciones con el MISMO content y
    // distinta fila. Con el id de cada una, cada UPDATE toca SU fila; no hay forma de cruzarlos.
    const contenidoIgual = buildMem(TAG + PLACEHOLDER);
    const qA = sql(fila({ id: ID }), { "Media: Preparar (staff)": prep({ id: ID }), "Postgres - Save fromMe": savePg("7001"), "Build fromMe AI memory": contenidoIgual });
    const ID_B = "b1c2d3e4f5061728";
    const qB = sql(fila({ id: ID_B }), { "Media: Preparar (staff)": prep({ id: ID_B }), "Postgres - Save fromMe": savePg("7002"), "Build fromMe AI memory": contenidoIgual });
    check("4k dos adjuntos sin caption al mismo paciente: cada token va a SU fila (nunca cruzados)",
      qA.includes("WHERE id = 7001 AND") && qA.includes(` [MEDIA:${ID}]`) && !qA.includes(ID_B)
      && qB.includes("WHERE id = 7002 AND") && qB.includes(` [MEDIA:${ID_B}]`) && !qB.includes(ID), `${qA}
${qB}`);
  }

  // =========================================================================================
  // 5) LO QUE ENTRA AL SQL: solo el id (16 hex) y el tipo (whitelist). Ningun texto libre.
  // =========================================================================================
  {
    const q = sql(fila(), nodos());
    check("5a ningun '$' en el SQL (pg-promise interpretaria $N como parametro)", !/\$/.test(q), q);
    // nice_to_have 5: '::' liga mas fuerte que '||'. Si un valor con '$' cayera pegado a un cast, el
    // esc lo partiria en trozos y el SQL cambiaria de significado. Hoy no puede pasar; esto lo vigila.
    check("5b el literal pegado a '::jsonb' es UN literal simple, no una concatenacion con chr(36)",
      /'\{"media_id":"[0-9a-f]{16}","media_tipo":(?:"[a-z]+"|null)\}'::jsonb/.test(q) && !q.includes("chr(36) || '::jsonb"), q);
    check("5c ningun camino mete chr(36) (nada con '$' llega al SQL: id hex + tipo del whitelist)",
      [q, sql(fila({ tipo: "video" }), nodos({ preparar: prep({ tipo: "video" }) })), sql(fila({ tipo: null }), nodos({ preparar: prep({ tipo: null }) }))].every((x) => !x.includes("chr(36)")), q);
    // El content y el session_id ya NO viajan al SQL: un caption con comilla, coma, salto de linea o
    // '$' es inocuo por construccion (leccion 5/9: la coma reventaba el queryReplacement de n8n).
    const NL = String.fromCharCode(10), TABC = String.fromCharCode(9);
    const bravo = TAG + "el diente de Ana O'Brien, mirá — salen $5000" + NL + "linea2" + TABC + "tab";
    const q2 = sql(fila(), nodos({ mem: buildMem(bravo) }));
    check("5d un caption hostil (comilla, coma, salto, '$') no aparece NI ENTERO NI EN PARTES en el SQL", !q2.includes("O''Brien") && !q2.includes("O'Brien") && !q2.includes("5000") && !/\$/.test(q2), q2);
    check("5e con ese caption el SQL sale IDENTICO al de un caption vacio (el content ya no lo toca)", q2 === q, q2);
    check("5f el id nunca sale del formato 16 hex: cualquier otra cosa es NOOP antes del SQL", sql(fila({ id: "1234567890abcde'" }), nodos({ preparar: prep({ id: "1234567890abcde'" }) })) === NOOP, "");
  }

  // =========================================================================================
  // 6) La expresion entera tiene que poder vivir dentro de un ={{ … }} de n8n
  // =========================================================================================
  {
    check("6a la expresion no trae llaves dobles (cerrarian el ={{ … }} antes de tiempo)", !ACTUALIZAR.includes("}}") && !ACTUALIZAR.includes("{{"), "");
    check("6b arranca como IIFE y devuelve un string en todos los caminos", ACTUALIZAR.startsWith("(() =>") && ACTUALIZAR.endsWith("})()"), ACTUALIZAR.slice(0, 20));
    const todos = [sql(fila(), nodos()), sql(fila(), nodos({ savePg: savePg(null) })), sql({}, nodos()), sql(fila(), sinNodos(nodos(), "Media: Preparar (staff)"))];
    check("6c todos los caminos devuelven un SQL no vacio (el nodo nunca recibe undefined)", todos.every((q) => typeof q === "string" && q.length > 10), JSON.stringify(todos.map((q) => typeof q)));
    check("6d los caminos de falla no tocan ninguna fila (3 de 4: sin id, $json vacio y sin Preparar)", todos.filter((q) => q === NOOP).length === 3, JSON.stringify(todos.map((q) => q === NOOP)));
  }

  // =========================================================================================
  // 7) GRUPOS / ESTADOS en media/preparar.js: la unica defensa de esta rama (R1)
  // =========================================================================================
  {
    // La doctora manda una foto AL GRUPO DE DERIVACIONES desde el celular del consultorio. Extraer Datos cae
    // a Info.Sender (el numero de la clinica) -> sin el filtro, el archivo terminaria en el bucket privado
    // bajo el numero del propio consultorio, con su fila y su foto en una "conversacion" fantasma del panel.
    let it = await preparar({ text: "", info: { Chat: GRUPO, Sender: `${CLINICA}@s.whatsapp.net` }, ed: { phone: CLINICA } });
    check("7a foto de la doctora al grupo de derivaciones: NO se sube (grupo_o_estado)", it.json.hay_archivo === false && it.json.motivo === "grupo_o_estado" && !it.binary, JSON.stringify(it.json));
    check("7b y no queda ni el path ni el id del archivo en el item", !it.json.path && !it.json.id, JSON.stringify(it.json));

    it = await preparar({ info: { Chat: GRUPO }, ed: { phone: GRUPO } });
    check("7c el jid del grupo como phone: tampoco (no se crea la carpeta del grupo en el bucket)", it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));

    it = await preparar({ info: { Chat: "status@broadcast", Sender: `${CLINICA}@s.whatsapp.net` }, ed: { phone: CLINICA } });
    check("7d estado de WhatsApp publicado desde el consultorio: NO se sube", it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));

    // 7d2..7d5 (2026-09-07): las FAMILIAS HERMANAS de @g.us. En las cuatro, "Edit Fields - Extraer Datos"
    // no encuentra ningun JID '@s.whatsapp.net' en Info.Chat y cae a Info.Sender = el numero del PROPIO
    // CONSULTORIO, que pasa el chequeo de largo 8-15: sin el guard el archivo se subia al bucket privado
    // bajo el numero de la clinica, con su fila en media_entrantes y una conversacion FANTASMA en el panel.
    // Por eso la rama del staff exige un JID 1:1 (whitelist) en vez de listar exclusiones (blacklist).
    const noEs1a1 = [
      ["d2", "120363407321448469@broadcast", "lista de difusion"],
      ["d3", "1234567890@broadcast", "lista de difusion con parte de usuario de largo E.164"],
      ["d4", "120363407321448469@newsletter", "canal"],
      ["d5", "108187302929820@lid", "chat LID de 15 digitos (el guard de largo NO lo caza)"],
      ["d6", "", "sin Info.Chat (el phone sale de Info.Sender = la clinica)"],
    ];
    for (const [n, jid, que] of noEs1a1) {
      it = await preparar({ info: { Chat: jid, Sender: `${CLINICA}@s.whatsapp.net` }, ed: { phone: CLINICA } });
      check(`7${n} ${que} (${jid || "vacio"}): NO se sube`, it.json.hay_archivo === false && it.json.motivo === "grupo_o_estado" && !it.binary, JSON.stringify(it.json));
      check(`7${n} ${que}: no queda nada bajo el numero de la clinica`, !it.json.path && !JSON.stringify(it.json).includes(`${CLINICA}/2026`), JSON.stringify(it.json));
    }
    // Y el guard NO depende de que el phone sea el de la clinica: con cualquier phone, si el chat no es 1:1, no sube.
    it = await preparar({ info: { Chat: "120363407321448469@newsletter" }, ed: { phone: TEL } });
    check("7d7 canal con un phone de paciente: tampoco sube", it.json.motivo === "grupo_o_estado", JSON.stringify(it.json));

    // Y el caso que SI tiene que funcionar: el 1:1 con el paciente.
    it = await preparar({ info: { Chat: `${TEL}@s.whatsapp.net`, Sender: `${CLINICA}@s.whatsapp.net` }, ed: { phone: TEL, text: "te mando la foto" } });
    check("7e 1:1 con el paciente: sube, from_me true, telefono = el del PACIENTE (asi lo encuentra el panel)", it.json.hay_archivo === true && it.json.from_me === true && it.json.telefono === TEL && it.json.path.startsWith(`${TEL}/`), JSON.stringify(it.json));
    check("7f el caption del staff viaja a media_entrantes.caption", it.json.caption === "te mando la foto", JSON.stringify(it.json));
    check("7g el id es 16 hex (lo exige el UPDATE y la DDL)", /^[0-9a-f]{16}$/.test(it.json.id), it.json.id);

    // Encadenado real: lo que produce Preparar alcanza para que el UPDATE arme el SQL correcto.
    const p = it.json;
    const q = sql(fila({ id: p.id, telefono: p.telefono }), { "Media: Preparar (staff)": p, "Postgres - Save fromMe": savePg("7001"), "Build fromMe AI memory": buildMem(TAG + "te mando la foto") });
    check("7h Preparar -> Registrar -> Actualizar: el token que se escribe es el id de ESE archivo", q.includes(` [MEDIA:${p.id}]`) && q.includes("WHERE id = 7001 AND"), q);
  }

  console.log(`\n${fallos === 0 ? "✅" : "❌"} fallos: ${fallos}`);
  process.exit(fallos ? 1 : 0);
})().catch((e) => { console.error("EXCEPCIÓN", e); process.exit(2); });
