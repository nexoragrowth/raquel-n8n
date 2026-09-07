// media/preparar.js — jsCode del Code node "Media: Preparar" del v6 (lo embebe scripts/apply_media_entrantes.py).
//
// Corre UNA vez por mensaje multimedia del paciente, después de los 4 "Set Marker *" (Audio, Imagen,
// Documento, Otros) y antes de "Merge Multimedia". Su input es el item del Set Marker: `{ text }` con el
// marcador ya armado ('[IMAGEN] TIPO: … DESCRIPCION: …', '[AUDIO] …', '[DOCUMENTO: … ]', '[VIDEO]', …).
//
// QUÉ HACE: toma el archivo desencriptado que Evolution GO manda en el webhook como
// `body.data.Message.base64` (verificado 100% presente para image/ptt/audio/document/video/sticker en
// 2048 ejecuciones), decide tipo/mime/extensión, genera un id de 16 hex y arma el path del objeto en
// Storage. Devuelve `{ text, hay_archivo: true, id, key_id, telefono, tipo, mime, path, bytes, … }` +
// `binary.data` para que "Media: Subir a Storage" lo suba con la credencial supabaseApi de n8n.
//
// Desde 2026-09-07 lo comparten las DOS ramas: la del paciente ("Media: Preparar") y la del staff
// ("Media: Preparar (staff)", rama fromMe). De ahí el filtro de grupos/estados de más abajo (motivo
// 'grupo_o_estado'), que en la rama del paciente es no-op y en la del staff es la única defensa (R1 del doc).
//
// REGLA DE ORO: `text` sale SIEMPRE idéntico al que entró. Si algo falla (sin base64, sin teléfono,
// archivo enorme, excepción) devuelve `{ text, hay_archivo: false, motivo }` sin binario y el bot sigue
// EXACTAMENTE como hoy ("Media: Marcar" solo agrega el sufijo ' [MEDIA:<id>]' si el registro en la tabla
// salió bien). Nunca reexpide el base64 en `json` (una imagen de 500 KB se multiplica ~6x en la fila
// de la ejecución en SQLite): el binario va a disco vía prepareBinaryData y se poda con la ejecución.
//
// Tests: node tests/test_media_nodos.js (harness con $input/$/this.helpers mockeados).

const BUCKET = 'pacientes-media';
// Tope duro: n8n rechaza bodies > 16 MB (N8N_PAYLOAD_SIZE_MAX default), así que en la práctica nunca se
// alcanza; protege el timeout de 30 s del upload si algún día llega algo enorme.
const MAX_BYTES = 20 * 1024 * 1024;
const EXT_POR_MIME = {
  'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif',
  'video/mp4': 'mp4', 'video/3gpp': '3gp', 'video/ogg': 'ogv',
  'audio/ogg': 'ogg', 'audio/mpeg': 'mp3', 'audio/mp4': 'm4a',
  'application/pdf': 'pdf',
};
const MIME_POR_DEFECTO = { image: 'image/jpeg', audio: 'audio/ogg', video: 'video/mp4', sticker: 'image/webp', document: 'application/octet-stream' };

function safe(fn, dflt) { try { const v = fn(); return (v === undefined || v === null) ? dflt : v; } catch (e) { return dflt; } }

// 'audio/ogg; codecs=opus' -> 'audio/ogg' (Evolution GO manda el parámetro; Storage y el mapa de ext no lo quieren)
function normMime(m) { return String(m || '').split(';')[0].trim().toLowerCase(); }

// Magic bytes: Evolution GO re-encodea los stickers ESTÁTICOS a PNG aunque declare image/webp (hallazgo 6/9),
// y un documento puede venir con mime genérico. Si lo que hay adentro se reconoce, manda el contenido real.
function sniffMime(buf, declarado) {
  if (!buf || buf.length < 12) return null;
  const hex = (o, n) => buf.slice(o, o + n).toString('hex');
  const asc = (o, n) => buf.slice(o, o + n).toString('latin1');
  if (hex(0, 4) === '89504e47') return 'image/png';
  if (hex(0, 3) === 'ffd8ff') return 'image/jpeg';
  if (asc(0, 4) === 'RIFF' && asc(8, 4) === 'WEBP') return 'image/webp';
  if (asc(0, 4) === 'GIF8') return 'image/gif';
  if (asc(0, 4) === '%PDF') return 'application/pdf';
  if (asc(0, 4) === 'OggS') return declarado.startsWith('video/') ? 'video/ogg' : 'audio/ogg';
  if (asc(4, 4) === 'ftyp') {
    const brand = asc(8, 4).toLowerCase();
    if (brand.startsWith('3gp')) return 'video/3gpp';
    if (brand.startsWith('m4a') || declarado.startsWith('audio/')) return 'audio/mp4';
    return 'video/mp4';
  }
  return null;
}

function extDeFilename(fn) { const m = /\.([a-z0-9]{1,8})$/i.exec(String(fn || '')); return m ? m[1].toLowerCase() : null; }

// 16 hex aleatorios. Sin precedente de `crypto` en los Code nodes de esta instancia -> tres caminos, en orden.
function generarId() {
  try {
    if (globalThis.crypto && typeof globalThis.crypto.getRandomValues === 'function') {
      const a = new Uint8Array(8); globalThis.crypto.getRandomValues(a);
      return Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('');
    }
  } catch (e) { /* sigue */ }
  try { return require('crypto').randomBytes(8).toString('hex'); } catch (e) { /* sigue */ }
  let s = ''; while (s.length < 16) s += Math.floor(Math.random() * 16).toString(16);
  return s;
}

// yyyy/mm en hora de Argentina (Info.Timestamp viene con -03:00; sin él, ahora). Fallback UTC si Intl falla.
function fechaDe(ts) {
  let d = ts ? new Date(ts) : new Date();
  if (isNaN(d.getTime())) d = new Date();
  try {
    const s = d.toLocaleDateString('en-CA', { timeZone: 'America/Argentina/Buenos_Aires', year: 'numeric', month: '2-digit', day: '2-digit' });
    const m = /^(\d{4})-(\d{2})/.exec(s);
    if (m) return { yyyy: m[1], mm: m[2] };
  } catch (e) { /* sigue */ }
  return { yyyy: String(d.getUTCFullYear()), mm: String(d.getUTCMonth() + 1).padStart(2, '0') };
}

// ---- texto de entrada: se preserva tal cual en TODOS los caminos ----
const textoEntrada = safe(() => $input.first().json.text, '');
const text = (typeof textoEntrada === 'string') ? textoEntrada : String(textoEntrada);
const sinArchivo = (motivo) => [{ json: { text, hay_archivo: false, motivo } }];

try {
  const ED = safe(() => $('Edit Fields - Extraer Datos').first().json, {}) || {};
  const data = safe(() => $('Webhook - Evolution API').first().json.body.data, {}) || {};
  const info = data.Info || {};
  const msg = data.Message || {};

  let b64 = (typeof msg.base64 === 'string') ? msg.base64 : '';
  b64 = b64.replace(/^data:[^;,]*;base64,/i, '').replace(/\s+/g, '');
  if (!b64) return sinArchivo('sin_base64');           // ubicación, contacto, texto con link preview, webhook sin archivo

  // `telefono` va VERBATIM como lo deja Extraer Datos: es el mismo valor que Inbox Live escribe en
  // mensajes_entrantes_live.telefono, que la memoria usa de session_id y que el Logger copia a conversaciones —
  // el panel cruza por igualdad exacta (.eq). Si algún día llegara con sufijo (Extraer Datos cae a Info.Chat
  // cuando ningún JID termina en @s.whatsapp.net → podría quedar '…@lid'), solo el PATH del objeto usa la
  // versión saneada (dígitos), porque Storage no acepta '@' en la key.
  const telefono = String(ED.phone || '').trim();
  const telPath = telefono.replace(/\D/g, '');
  if (!telefono || !telPath) return sinArchivo('sin_telefono');

  // CHATS QUE NO SON 1:1 — grupo, estado, lista de difusión, canal, LID (2026-09-07, riesgo R1 de
  // docs/media-entrantes-2026-09-06.md §8.3). El filtro `@g.us` / `status@broadcast` del v6 vive en
  // "Filtrar duplicados y basura", que cuelga SOLO de "Es fromMe?"[1] (la rama del PACIENTE): la rama
  // del staff no filtra nada. Sin esto, una foto que la doctora manda al GRUPO DE DERIVACIONES desde el
  // celular del consultorio (o un estado que publica, o un mensaje a una lista de difusión / un canal /
  // un chat LID) se subiría al bucket privado bajo el número del grupo o del PROPIO CONSULTORIO, con su
  // fila en `media_entrantes` y la foto renderizada en una "conversación" fantasma del panel.
  // Va acá y no en la IF porque este archivo lo comparten las dos ramas y es el único lugar donde el
  // archivo TODAVÍA no se subió. Para la rama del paciente es no-op (ya viene filtrada aguas arriba).
  // Va DESPUÉS de `sin_telefono` a propósito: los casos que ya se reportaban así no cambian de motivo.
  //
  // Son TRES guards, a propósito (regla dura 5, defensa en profundidad). El (2) solo por sí mismo ya
  // cierra la rama del staff, pero el (1) y el (3) siguen valiendo para la rama del paciente, donde
  // "Filtrar duplicados y basura" arrastra exactamente el mismo blacklist incompleto que tenía este
  // archivo (`@g.us` + igualdad con 'status@broadcast', sin '@broadcast'/'@newsletter' genéricos).
  const jids = [info.Chat, info.RecipientAlt, info.SenderAlt, telefono].map((j) => String(j || ''));

  // (1) BLACKLIST, las dos ramas: grupo (@g.us), lista de difusión (@broadcast — `endsWith` subsume
  //     'status@broadcast') y canal (@newsletter). Ninguno de los tres es nunca un chat 1:1.
  //     NO incluye '@lid' a propósito: en la rama del PACIENTE un `phone` '@lid' es un 1:1 legítimo y
  //     hoy se sube (columna verbatim + path con dígitos, tests 17b de test_media_nodos.js). Para el
  //     staff sí se descarta, pero por el guard (2), que es más estricto y no toca al paciente.
  if (jids.some((j) => j.includes('@g.us') || j.endsWith('@broadcast') || j.endsWith('@newsletter'))) return sinArchivo('grupo_o_estado');

  // (2) WHITELIST, SOLO la rama del staff (ED.fromMe true ⇔ salida [0] de "Es fromMe?", que testea
  //     exactamente `$json.fromMe === true`). Exige un JID 1:1 en Info.Chat en vez de listar exclusiones:
  //     cierra de una @g.us, @broadcast, @newsletter, @lid y cualquier familia de JID que WhatsApp
  //     invente mañana. Es la diferencia entre un blacklist (falla abierto ante lo desconocido) y un
  //     whitelist (falla cerrado), y acá fallar abierto significa subir el archivo al bucket privado
  //     bajo el número del PROPIO CONSULTORIO: "Edit Fields - Extraer Datos" recorre
  //     [Chat, Sender, RecipientAlt, SenderAlt] y se queda con el primero que termina en
  //     '@s.whatsapp.net'; si Info.Chat no es 1:1, ese primero es Info.Sender = la clínica, que pasa
  //     el chequeo de largo del guard (3). Resultado: fila en `media_entrantes` y conversación
  //     fantasma en el panel (R1). No-op para la rama del paciente.
  //     Chat ausente también cae acá, y está bien: sin Info.Chat el `phone` sale de Info.Sender.
  if (ED.fromMe && !/@s\.whatsapp\.net$/.test(String(info.Chat || ''))) return sinArchivo('grupo_o_estado');

  // (3) Un jid de grupo son 18 dígitos y uno de estado no tiene ninguno: si algún día Evolution mandara
  //     el chat en otro campo, el largo del teléfono resultante lo caza igual (los E.164 van de 8 a 15).
  if (telPath.length < 8 || telPath.length > 15) return sinArchivo('grupo_o_estado');

  // Sub-mensaje y tipo. Primero Info.MediaType (lo que mira el Switch), después el sub-key de Message como
  // fallback (caso real 25/8: audio con Info.MediaType = '' — hoy muere antes, pero si algún día pasa, cubre).
  const docMsg = msg.documentMessage
    || safe(() => msg.documentWithCaptionMessage.message.documentMessage, null);
  const mt = String(info.MediaType || '').toLowerCase();
  let tipo = null, sub = null;
  if (mt === 'image') { tipo = 'image'; sub = msg.imageMessage; }
  else if (mt === 'ptt' || mt === 'audio') { tipo = 'audio'; sub = msg.audioMessage; }
  else if (mt === 'video' || mt === 'gif') { tipo = 'video'; sub = msg.videoMessage; }
  else if (mt === 'document') { tipo = 'document'; sub = docMsg; }
  else if (mt === 'sticker' || mt === 'user_created_sticker') { tipo = 'sticker'; sub = msg.stickerMessage; }
  if (!tipo) {
    if (msg.imageMessage) { tipo = 'image'; sub = msg.imageMessage; }
    else if (msg.audioMessage) { tipo = 'audio'; sub = msg.audioMessage; }
    else if (msg.videoMessage) { tipo = 'video'; sub = msg.videoMessage; }
    else if (docMsg) { tipo = 'document'; sub = docMsg; }
    else if (msg.stickerMessage) { tipo = 'sticker'; sub = msg.stickerMessage; }
  }
  if (!tipo) return sinArchivo('tipo_desconocido:' + (mt || '-'));
  sub = sub || {};

  const buf = Buffer.from(b64, 'base64');
  if (!buf.length) return sinArchivo('base64_invalido');
  if (buf.length > MAX_BYTES) return sinArchivo('archivo_muy_grande:' + buf.length);

  const declarado = normMime(sub.mimetype || (tipo === 'image' ? ED.image_mime : '') || (tipo === 'document' ? ED.document_mime : ''));
  const sniff = sniffMime(buf, declarado);
  let mime = sniff || declarado || MIME_POR_DEFECTO[tipo];
  // Sticker cuyo contenido NO es una imagen reconocible (Lottie / animado propietario: WhatsApp igual declara
  // image/webp): se sube igual, pero con mime genérico para que el panel lo pinte como chip "Sticker" y no como
  // un <img> roto.
  if (tipo === 'sticker' && !sniff) mime = 'application/octet-stream';

  const filenameOrig = String(sub.fileName || '').trim() || null;   // solo documentMessage lo trae
  const ext = EXT_POR_MIME[mime] || extDeFilename(filenameOrig) || 'bin';
  const id = generarId();
  const f = fechaDe(info.Timestamp);
  const path = telPath + '/' + f.yyyy + '/' + f.mm + '/' + id + '.' + ext;
  const filename = filenameOrig || (id + '.' + ext);
  const caption = (typeof ED.text === 'string' && ED.text.trim()) ? ED.text : null;

  const binario = await this.helpers.prepareBinaryData(buf, filename, mime);
  return [{
    json: {
      text, hay_archivo: true,
      id, key_id: String(ED.key_id || info.ID || ''), telefono, from_me: !!ED.fromMe,
      tipo, mime, mime_declarado: declarado || null, ext, bucket_destino: BUCKET, path,
      bytes: buf.length, filename, caption, media_type_origen: mt || null,
    },
    binary: { data: binario },
  }];
} catch (e) {
  return sinArchivo('error:' + (e && e.message ? e.message : String(e)));
}
