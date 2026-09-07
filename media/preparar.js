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
