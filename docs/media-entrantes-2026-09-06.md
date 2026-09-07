# Adjuntos del paciente en Storage (`media_entrantes`) — diseño, contrato y operación

**Fecha**: 2026-09-06 · **Estado**: scripts listos y probados en dry-run contra el v6 vivo (147 nodos, versionId
`a259e1ef…`), tests verdes (54/54 tras la ronda de revisión). **Nada aplicado**: falta el OK de Lucas para `create_media_entrantes.py --apply`
y `apply_media_entrantes.py --apply`. Lado panel: lo implementa el repo `nexora-whatsapp-agent` (ruta `/api/media/<id>`,
render de imagen/video/audio/documento).

## 1. Qué resuelve (en una frase)
Hoy el v6 recibe la foto / el audio / el documento del paciente en el webhook (Evolution GO manda el archivo
desencriptado en `body.data.Message.base64`, 100 % de los casos en 13 días), lo usa para describirlo/transcribirlo y
**descarta el archivo**. El panel solo puede mostrar un chip ("Imagen · TIPO: FOTO_DENTAL …"). Con este cambio el v6
sube el archivo a un bucket **privado** de Supabase Storage, registra una fila en `media_entrantes` y deja en el texto
del mensaje un sufijo ` [MEDIA:<id>]`; el panel resuelve el id a una URL firmada de 1 h y muestra el adjunto real.
**Si algo falla, el bot sigue exactamente como hoy** (texto sin sufijo).

## 2. Grafo en el v6 (6 nodos nuevos "Media: *", 6 conexiones existentes recableadas, Merge 5 → 2 entradas)
```
Set Marker Audio ─┐
Set Marker Imagen ─┼─► Media: Preparar (code) ─► Media: ¿Hay archivo? (if)
Set Marker Documento ┤        [sí] ─► Media: Subir a Storage (httpRequest 4.2, cred supabaseApi "Supabase account v3")
Set Marker Otros ─┘                    └─► Media: ¿Subida OK? (if: 2xx y sin error)
                                              [sí] ─► Media: Registrar (postgres 2.5 insert defineBelow, cred "Postgres Supabase Nexora v3")
                                                          └─► Media: Marcar (set) ─► Merge Multimedia[0] ─► Buffer: Push / Buffer: Wait (igual que hoy)
                                              [no] ─────────► Media: Marcar
                              [no] ──────────────────────────► Media: Marcar
Set Passthrough Texto ──────────────────────────────────────────────────────► Merge Multimedia[1]   (antes [4])
```
- Posiciones: fila propia en y=1150 (x 5552 → 6992, paso 288), debajo de la rama multimedia; banda verificada libre.
- `Merge Multimedia` pasa de `numberInputs: 5` a `2` con **ambas** entradas conectadas. Evidencia: en producción
  (execs 271999, 270763, 270757, 270624, 270623, 269685) Merge v3 append con `executionOrder v1` emite cuando UNA sola de
  sus entradas conectadas recibe datos; no hay evidencia del caso "entrada declarada sin conexión", así que se reproduce
  el patrón probado en vez de dejar 3 entradas sueltas.
- Fuente única del código: `media/preparar.js` (jsCode), `media/marcar_expr.js` (expresión del Set), `media/subida_ok_expr.js`
  (expresión del IF). `scripts/apply_media_entrantes.py` los embebe; `tests/test_media_nodos.js` corre exactamente esos archivos.
- Secretos: ninguno en el repo. El host `https://<ref>.supabase.co` se lee del nodo vivo `obtener_historial_paciente`
  (fallback `consultar_recordatorios_abiertos`) y se cruza con `V3_SUPABASE_URL` (panel `.env.local`) y `SUPABASE_V3_URL`
  (`.env`): si no coinciden, el script aborta. Las credenciales se copian de nodos vivos verificando el id
  (`H1PRagttKC5kxSzs` supabaseApi, `TpYhZX4UT61xAKSV` postgres). La credencial supabaseApi agrega `apikey` +
  `Authorization: Bearer <service key>` (misma que usan los toolHttpRequest del v6 y el Logger): sirve igual para `/storage/v1`.

### Qué hace cada nodo
| Nodo | Tipo | Detalle |
|---|---|---|
| Media: Preparar | code v2, onError continue | Toma `text` del Set Marker, `base64` del webhook, `phone/key_id/text/mimes` de Extraer Datos. Decide `tipo` por `Info.MediaType` (`image`; `ptt`/`audio`→audio; `video`/`gif`→video; `document`; `sticker`/`user_created_sticker`→sticker) con fallback por sub-key de `Message` (caso real 25/8 con MediaType vacío). Normaliza el mime (`audio/ogg; codecs=opus` → `audio/ogg`), **sniffea magic bytes** (Evolution GO manda los stickers estáticos como PNG aunque declare webp), calcula ext (`jpg png webp gif mp4 3gp ogv ogg mp3 m4a pdf`, si no: ext del filename original, si no `bin`), id 16 hex, `path = <tel solo dígitos>/<yyyy>/<mm>/<id>.<ext>` (mes en hora Argentina), `telefono` **verbatim** como lo deja Extraer Datos (mismo valor que `mensajes_entrantes_live.telefono` / `session_id`: el panel cruza por igualdad), `filename` (original de documentos o `<id>.<ext>`), `caption` (= `Extraer Datos.text` o null). Sticker cuyo contenido no es PNG/WEBP/GIF (Lottie) → mime `application/octet-stream` (el panel lo pinta como chip, no como `<img>` roto). Devuelve `json` chico (sin base64, R4; **sin** clave `bucket`, solo `bucket_destino`) + `binary.data` vía `prepareBinaryData`. Sin base64 / sin teléfono / > 20 MB / excepción → `{text, hay_archivo:false, motivo}`. |
| Media: ¿Hay archivo? | if 2.2 | `$json.hay_archivo === true` |
| Media: Subir a Storage | httpRequest 4.2, onError continue | `POST <host>/storage/v1/object/pacientes-media/{{ $json.path }}`, `contentType: binaryData` (`inputDataFieldName: data`), headers `Content-Type = {{ $json.mime }}`, `x-upsert: true`, `cache-control: max-age=3600` (Storage lo guarda como metadata y lo sirve en la URL firmada; sin él responde `no-cache` y el panel revalida en cada remount); `neverError + fullResponse`, timeout 30 s. |
| Media: ¿Subida OK? | if 2.2 | `!$json.error && 200 ≤ statusCode < 300 && !body.error` |
| Media: Registrar | postgres 2.5 insert `defineBelow`, onError continue | Columnas desde `$('Media: Preparar').first().json`: id, key_id, telefono, from_me, tipo, mime, bucket (`pacientes-media`), path, bytes, filename, caption. Devuelve la fila (`RETURNING *`). Sin `executeQuery`+`queryReplacement` (n8n parte por coma: un caption con coma rompería; lección 5/9). |
| Media: Marcar | set 3.4 | `text = Preparar.text + (fila.bucket === 'pacientes-media' && fila.id === Preparar.id && !fila.error ? ' [MEDIA:' + id + ']' : '')`. En las ramas "no" `$json` es Preparar o la respuesta HTTP → nunca cumple → sin sufijo. Blindaje: si Preparar murió FUERA de su try/catch (kill del sandbox / timeout del runner, hoy inalcanzable) n8n emite `{error}` sin `text`; Marcar rescata entonces el texto del Set Marker que corrió (los otros tres no ejecutaron y `$()` tira → try/catch) para que al Router nunca llegue un mensaje vacío. |

## 3. Contrato del marcador (lo que lee el panel)
A cada marcador **existente** se le agrega **al final** ` [MEDIA:<id>]` (espacio, corchetes, `MEDIA`, dos puntos, 16 hex).
El prefijo no cambia (Pre-filtro Cierre, Router y Sub-Agent Confirmar miran `[IMAGEN`/`[DOCUMENTO`/`[AUDIO`/`TIPO: COMPROBANTE`).
```
[IMAGEN] TIPO: FOTO_DENTAL\nDESCRIPCION: …\nCaption del paciente: mirá [MEDIA:3fa9c2e1b7d04a58]
[AUDIO] hola quería saber si hay turno [MEDIA:8c01…]
[DOCUMENTO: presupuesto.pdf (application/pdf)]\nCaption: te lo mando [MEDIA:…]
[VIDEO] mirá cómo se mueve [MEDIA:…]        [STICKER] [MEDIA:…]
```
- 3 fotos seguidas = UNA fila `human` en `n8n_chat_histories` con 3 marcadores unidos por `\n` (`Preparar Mensaje Final`
  concatena el buffer) → cada marcador lleva su propio id. El Logger copia el content textual a `conversaciones.mensaje`.
  **Orden**: lo fija el momento del `Buffer: Push` de cada foto, que ya hoy depende de la latencia de OpenAI Vision por
  foto (no del orden de envío); la cadena Media suma ~0,3–2 s de varianza (30 s solo si Storage cuelga). Los 3 tokens
  pueden salir en otro orden que el de WhatsApp; el panel lo tolera (adjunta por id, no por posición).
- `mensajes_entrantes_live` sigue teniendo una fila por `key_id` (Inbox Live corre antes); `media_entrantes.key_id` permite
  al panel adjuntar el archivo a la burbuja "en vivo" antes de que la memoria tenga el `[MEDIA:]` (~25–45 s después).
- Si la subida o el INSERT fallan: texto **idéntico a hoy**, objeto huérfano posible en Storage si falló solo el INSERT
  (inofensivo; `x-upsert` evita duplicados por reintento).
- Consumidores aguas abajo verificados: ninguno usa anchors `$`/longitud/parseo posicional sobre el marcador; Canned Sidecar,
  Gate Pago Tratamiento y Triaje testean palabras que un id hex (a–f) no puede formar. Cosmético: el token puede aparecer en
  el resumen `[ESCALADO BOT]` del grupo (`texto_paciente = text.slice(0,220)`) y en `triaje_urgencias_log.mensaje_paciente`.

## 4. Datos e infraestructura (`scripts/create_media_entrantes.py`)
- **Bucket** `pacientes-media`: `public=false`, `file_size_limit` 50 MB, sin restricción de mime. Se crea/ajusta por la API de
  Storage con la service key del `.env.local` del panel (`V3_SUPABASE_URL`/`V3_SUPABASE_SERVICE_KEY`; fallback `.env`).
  Privado ⇒ solo service_role lee; el panel firma URLs de 1 h; el path incluye el teléfono pero solo se ve del lado servidor.
- **Tabla** `public.media_entrantes` (DDL en `rebuild_v3_schema.sql` §12): `id text PK CHECK 16 hex`, `key_id text` (índice),
  `telefono text not null` (índice con created_at), `from_me bool default false`, `tipo` check `image|video|audio|document|sticker`,
  `mime`, `bucket default 'pacientes-media'`, `path not null`, `bytes int`, `filename`, `caption`, `created_at`.
  RLS habilitado **sin policies** (como el resto del v3). Agregada a la publicación `supabase_realtime`
  (también en `TABLAS` de `apply_realtime_publication_v3.py`).
- `--estado` devuelve exit 0 si bucket privado + tabla + índices + RLS + publicación están; `--apply` es idempotente.

## 5. Límites y observaciones con evidencia
- Tamaños reales (13 días, 2048 execs): imagen ≤ 706 KB, ptt ≤ 608 KB (297 s), documento ≤ 2,2 MB, sticker ≤ 486 KB, video
  (solo staff) ≤ 5,1 MB. n8n rechaza bodies > 16 MB (`N8N_PAYLOAD_SIZE_MAX` default, no verificado) ⇒ un archivo > ~11,5 MB
  no llega; el tope de 20 MB en Preparar es un guarda-rail para el timeout de 30 s.
- La fila de la ejecución en SQLite ya pesa ~6× el base64 por el webhook; la cadena nueva agrega ≈0 porque `Preparar` no
  reexpide el base64 en `json` y el binario va a filesystem (`binaryMode: separate` del workflow).
- Latencia: +0,3–2 s (upload + insert) antes del `Buffer: Push`. El `Buffer: Wait` (22 s) arranca en paralelo al push, así
  que el mecanismo "Soy el último?" no cambia; puede reordenar texto/foto casi simultáneos igual que hoy lo hace la latencia de OpenAI.
- **Fuera de alcance (decidido)**: adjuntos del **staff** desde el celular (rama `Es fromMe?[0]`). El dato está (el webhook
  fromMe trae base64: image 142, document 25, ptt 6, video 3 en 13 días) pero esa rama no pasa por Switch/Set Marker/Merge:
  sería una segunda entrada a `Media: Preparar` + sufijar el placeholder de `Build fromMe AI memory`. Se documenta como P3.
- **Riesgo R3 (recomendado, no incluido para no tocar nodos fuera de la rama)**: el Router, los sub-agents y el Formatting
  Agent ven ` [MEDIA:…]` en el mensaje y en el contexto; nada lo filtra en la salida. Segunda capa determinística barata:
  `text.replace(/\s*\[MEDIA:[0-9a-f]{16}\]/g, '')` sobre el OUTPUT en `Banlist Validator` (o en `Split en Mensajes`).
  Pedir OK a Lucas como cambio aparte (regla dura 5: dos capas).
- Bugs preexistentes que NO se tocan: `contactsArrayMessage` no detectado por Extraer Datos; audio con `Info.MediaType=''`
  muere en `Filtrar duplicados y basura` (Preparar ya lo cubriría si llegara).

## 6. Cómo probar (regla dura 8: camino completo, y 9: limpiar residuos)
**Orden de despliegue (obligatorio, panel ANTES que v6)**: el panel deployado hoy (HEAD `2e5c8c0`) mostraría el token
crudo dentro de la itálica DESCRIPCION y `[VIDEO] [MEDIA:x]` como texto plano. Secuencia segura:
(1) deploy del panel nuevo (tolera tabla inexistente: `PGRST205` → 404 en `/api/media`, probe del bus) →
(2) `create_media_entrantes.py --apply` → (3) reiniciar el panel (o esperar una reconexión del canal: el bus re-prueba
`media_entrantes` en cada recreación) para que sume la escucha `media` → (4) `apply_media_entrantes.py --apply`.
1. `node tests/test_media_nodos.js` → 54/54 (Preparar con 9+ shapes reales, expresiones de Marcar y ¿Subida OK?).
2. `python scripts/create_media_entrantes.py` (preview) → `--apply` → `--estado` exit 0. Confirmar también
   `python scripts/apply_realtime_publication_v3.py --estado` (el probe del panel solo mira que la tabla exista, no que esté
   publicada: si falta en la publicación no llegan eventos `media` y no hay log).
3. `python scripts/apply_media_entrantes.py` (dry-run: ver diff, "Fuera de la rama multimedia: 0/0", webhookId True) → `--apply`.
   **Verificación post-apply obligatoria en la PRIMERA ejecución real** (no hay precedente de `this.helpers.prepareBinaryData`
   ni de `Buffer` en los Code nodes de esta instancia; con Task Runners el Buffer viaja por RPC): abrir la ejecución en n8n y
   mirar la salida de `Media: Preparar`: si `hay_archivo` es false con `motivo` que empieza en `error:`, el feature está apagado
   en silencio (falla segura, texto intacto) y hay que ver el mensaje. Ídem `Media: Registrar`: la salida tiene que ser la fila
   insertada (`RETURNING *`) con `id` y `bucket`; si el nodo devolviera otra cosa, `Media: Marcar` nunca agrega el sufijo
   (también silencioso) — la prueba es que `n8n_chat_histories` termine en ` [MEDIA:<id>]`.
4. Desde el celular de Lucas: una foto con caption, un audio, un PDF, un sticker, una ubicación (esta NO debe crear fila).
   Verificar: (a) en n8n la ejecución pasa por `Media: Registrar` con fila devuelta; (b) `select id, tipo, mime, path, bytes,
   caption from media_entrantes order by created_at desc limit 5`; (c) el objeto existe en Storage (`GET /storage/v1/object/
   info/authenticated/pacientes-media/<path>` con service key); (d) en `n8n_chat_histories` el content termina en ` [MEDIA:<id>]`;
   (e) el panel muestra el adjunto y `/api/media/<id>` redirige (302) a una URL firmada.
5. Limpiar en el mismo turno: `python scripts/limpiar_numero_demo.py` (memoria, logs, label) + borrar las filas de prueba de
   `media_entrantes` y los objetos del bucket bajo `<tel de Lucas>/`.
6. Chequeo de regresión: un mensaje de texto plano (Passthrough → Merge[1]) llega al Router igual que hoy; `check_triaje.py` TODO SANO.

## 7. Cómo revertir
- Cableado solamente (deja los 6 nodos huérfanos, cero riesgo): `python scripts/apply_media_entrantes.py --rollback-wiring`
  → Set Marker * → Merge[0..3], Passthrough → Merge[4], `numberInputs: 5`, `Media: Marcar` sin salida.
- Total: `python scripts/apply_media_entrantes.py --rollback workflows/history/v6_PRE_media_entrantes_<ts>.json`
  (PUT del backup completo; guarda a su vez un PRE del rollback). El cableado previo exacto también queda en
  `workflows/history/v6_PRE_media_entrantes_wiring_<ts>.json`.
- Datos: la tabla y el bucket son aditivos; pueden quedar. Si se quiere borrar: `drop table media_entrantes` +
  `alter publication supabase_realtime drop table public.media_entrantes` (o `apply_realtime_publication_v3.py --quitar`
  después de sacarla de `TABLAS`) + vaciar y borrar el bucket desde el dashboard de Supabase.
- El panel tolera ambos estados: mensajes sin `[MEDIA:]` siguen como chip.
