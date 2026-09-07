# Adjuntos del paciente en Storage (`media_entrantes`) — diseño, contrato y operación

**Fecha**: 2026-09-06 · §8 (rama staff) rehecha el **2026-09-07** tras la revisión adversarial.
**Estado**: la rama del PACIENTE (§1-§7) está **aplicada y viva** en el v6 (153 nodos, versionId `3a8c0794…`) y el panel
que la renderiza está deployado (`191381b`). La rama del **STAFF** (§8) está lista y probada en dry-run contra el v6 vivo
(153 → 159 nodos), tests verdes (67 en `test_media_nodos.js` + 57 en `test_media_fromme.js`): **falta el OK de Lucas para
`apply_media_fromme.py --apply`**. Lado panel: lo implementa el repo `nexora-whatsapp-agent` (ruta `/api/media/<id>`,
render de imagen/video/audio/documento); la parte de adjuntos del staff está en el working tree, sin commit.

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
- **Retención (2026-09-07)**: columna `borrado_at TIMESTAMPTZ NULL` (+ índice parcial `idx_media_entrantes_vivos_created`) que
  marca el satélite `Áurea — Retención` cuando borró el objeto de Storage (adjuntos > 90 días, lote de 200 por noche). DDL
  idempotente: `scripts/create_retencion_satelite.py --ddl` y `rebuild_v3_schema.sql` §12/§13 (`retencion_log`). Diseño y
  operación: `docs/retencion-y-uso-2026-09-07.md`.

## 5. Límites y observaciones con evidencia
- Tamaños reales (13 días, 2048 execs): imagen ≤ 706 KB, ptt ≤ 608 KB (297 s), documento ≤ 2,2 MB, sticker ≤ 486 KB, video
  (solo staff) ≤ 5,1 MB. n8n rechaza bodies > 16 MB (`N8N_PAYLOAD_SIZE_MAX` default, no verificado) ⇒ un archivo > ~11,5 MB
  no llega; el tope de 20 MB en Preparar es un guarda-rail para el timeout de 30 s.
- La fila de la ejecución en SQLite ya pesa ~6× el base64 por el webhook; la cadena nueva agrega ≈0 porque `Preparar` no
  reexpide el base64 en `json` y el binario va a filesystem (`binaryMode: separate` del workflow).
- Latencia: +0,3–2 s (upload + insert) antes del `Buffer: Push`. El `Buffer: Wait` (22 s) arranca en paralelo al push, así
  que el mecanismo "Soy el último?" no cambia; puede reordenar texto/foto casi simultáneos igual que hoy lo hace la latencia de OpenAI.
- **Fuera de alcance (al 6/9; resuelto el 7/9, ver §8)**: adjuntos del **staff** desde el celular (rama `Es fromMe?[0]`). El dato está (el webhook
  fromMe trae base64: image 142, document 25, ptt 6, video 3 en 13 días) pero esa rama no pasa por Switch/Set Marker/Merge:
  hacía falta una cadena Media propia + sufijar el placeholder de `Build fromMe AI memory`. **Hecho el 7/9: ver §8**
  (`scripts/apply_media_fromme.py`, 6 nodos `Media: * (staff)` colgados DESPUÉS del label de Chatwoot).
- **Riesgo R3 (recomendado, no incluido para no tocar nodos fuera de la rama)**: el Router, los sub-agents y el Formatting
  Agent ven ` [MEDIA:…]` en el mensaje y en el contexto; nada lo filtra en la salida. Segunda capa determinística barata:
  `text.replace(/\s*\[MEDIA:[0-9a-f]{16}\]/g, '')` sobre el OUTPUT en `Banlist Validator` (o en `Split en Mensajes`).
  Pedir OK a Lucas como cambio aparte (regla dura 5: dos capas).
- Bugs preexistentes que NO se tocan: `contactsArrayMessage` no detectado por Extraer Datos; audio con `Info.MediaType=''`
  muere en `Filtrar duplicados y basura` (Preparar ya lo cubriría si llegara).
- **Adjuntos vencidos (2026-09-07)**: a los 90 días el objeto se borra de `pacientes-media` y la fila queda con `borrado_at`.
  El panel trae `borrado_at` en `getChatData` y muestra el chip "Adjunto vencido (se guardan 90 días)" en vez de la imagen;
  `/api/media/<id>` responde **410 Gone** si `borrado_at` no es null (404 sigue siendo "no existe"). Un `UPDATE` no dispara evento
  en vivo (el bus escucha INSERT): el chip aparece al próximo refetch. Los adjuntos del staff (`panel-media`, públicos) también se
  borran a los 90 días; la URL queda en la memoria y el panel cae al chip cuando Storage confirma que el objeto no está. El chip
  "vencido" se reserva para un 404/410 confirmado por el servidor (`HEAD /api/media/<id>` sin seguir el 302; GET de 1 byte a la
  URL pública): el `onError` de `<audio>/<video>/<img>` solo no distingue "borrado" de "este navegador no lo reproduce" (las notas
  ogg/opus del paciente en Safari), y en ese caso el panel muestra "No se pudo reproducir acá · abrir" con link de descarga.

## 6. Cómo probar (regla dura 8: camino completo, y 9: limpiar residuos)
**Orden de despliegue (obligatorio, panel ANTES que v6)**: el panel deployado hoy (HEAD `2e5c8c0`) mostraría el token
crudo dentro de la itálica DESCRIPCION y `[VIDEO] [MEDIA:x]` como texto plano. Secuencia segura:
(1) deploy del panel nuevo (tolera tabla inexistente: `PGRST205` → 404 en `/api/media`, probe del bus) →
(2) `create_media_entrantes.py --apply` → (3) reiniciar el panel (o esperar una reconexión del canal: el bus re-prueba
`media_entrantes` en cada recreación) para que sume la escucha `media` → (4) `apply_media_entrantes.py --apply`.
1. `node tests/test_media_nodos.js` → 83/83 (Preparar con 9+ shapes reales + los guards de JID de §8.3 R1, expresiones de Marcar y ¿Subida OK?).
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

---

## 8. Rama staff (fromMe) — 2026-09-07 (rediseñada el 2026-09-07 tras la revisión adversarial)
Lo que en §5 estaba "fuera de alcance (P3)". Mismo mecanismo, misma tabla, mismo bucket, mismo token: cuando la
doctora o la secretaria manda una foto / audio / video / documento **desde el celular o el WA Web del consultorio**,
el archivo se guarda igual que el del paciente y el panel lo muestra de verdad, en vez del chip "Adjunto enviado
desde el celular del consultorio". Script: `scripts/apply_media_fromme.py` · SQL del UPDATE:
`media/actualizar_memoria_staff.js` · guards de JID: `media/preparar.js` (compartido con la rama del paciente) ·
tests: `tests/test_media_fromme.js` (69 checks) + `tests/test_media_nodos.js` (83).

**Qué cambió respecto del primer diseño (el que se bloqueó)**: la cadena Media ya NO se mete entre `Es fromMe?` y
el label de Chatwoot, y `Build fromMe AI memory` ya NO se toca. La cadena entera de silenciamiento queda **exacta
como hoy**, la subida cuelga DESPUÉS del label, y el token llega a la fila de memoria por un UPDATE posterior.
Archivos borrados de ese diseño: `media/fromme_memory.js`, `media/fromme_memory_previo.js`,
`media/hay_archivo_staff_expr.js` (con ellos desaparece el riesgo "byte a byte" sobre el TAG y el placeholder).

Evidencia de que el dato está: exec **272512** (2026-09-07 14:05, `IsFromMe=true`, `Info.MediaType='image'`) trae
`Message.base64` de 137.900 ch (≈103 KB reales, `fileLength` 103.423) + `imageMessage.mimetype image/jpeg` + caption.
Un vcard (exec 272486, `MediaType='vcard'`) **no** trae base64 y cae correctamente en `hay_archivo:false`.

### 8.1 Grafo (6 nodos nuevos "Media: * (staff)", 1 conexión nueva, 1 nodo existente modificado)
```
Es fromMe?[0] ─► Build fromMe AI memory ─► Postgres - Save fromMe ─► CW Search Contact ─► CW Extract Conv
                    (NO SE TOCA)              (+ RETURNING id)          ─► CW Get Conversations ─► CW Pick Conv
                                                                        ─► CW Set Label humano   ← CALLA AL BOT
                                                                              │  (hoy: fin de la cadena)
                                                                              ▼
                            Media: Preparar (staff) ─► Media: ¿Hay archivo? (staff)
                                 [true] ─► Media: Subir a Storage (staff) ─► Media: ¿Subida OK? (staff)
                                                [true] ─► Media: Registrar (staff)
                                                              └─► Media: Actualizar memoria (staff)   ← UPDATE
                                 [false] de los dos IF: sin destino (fin de rama, no hay nada que hacer)
Es fromMe?[1] ─► Filtrar duplicados y basura        (rama del PACIENTE: no se toca)
```
- **Todo el silenciamiento queda intacto**: `Es fromMe?`[0] → `Build fromMe AI memory` → `Postgres - Save fromMe`
  → los 5 nodos `CW *`, en el mismo orden, con los mismos parámetros. Ni una arista movida. La única conexión
  nueva sobre un nodo existente es la salida de `CW Set Label humano`, que **hoy no tiene ninguna**.
- **Por qué la subida va DESPUÉS del label** (era el must-fix #1): el label `humano` de Chatwoot es lo ÚNICO que
  calla al bot en esta rama — los tres gates que lo miran (`Verificar Label Humano`, `Hay humano ahora?` y
  `Gate Humano Final`, que hace un GET fresco justo antes de enviar) leen Chatwoot; **no hay** ningún nodo Redis
  ni SQL de humano acá, y **no existe** ningún nodo "Check Humano Reciente (DB)" en el v6. Repro de la falla si la
  subida quedara antes: el paciente escribe en t=0; la doctora contesta con un video de 5 MB en t=5 s; la subida
  tarda 25 s (o Storage cuelga y corre el timeout de 30 s) ⇒ el label recién en t≈31 s, mientras el pipeline del
  paciente (Buffer 10-22 s + LLM + `Delay Humano` 1,2-4 s + typing) termina en t≈25-30 s **sin** label: el bot
  escribe encima de la doctora. Es la clase de falla del incidente Mariela. Con la cadena colgada del final, la
  subida no puede demorar el label ni un ms: ya pasó.
- **Los 5 primeros nodos son copias exactas** de los vivos de la rama del paciente (mismo `typeVersion`, mismos
  parámetros, mismas credenciales — copiadas en caliente de `Media: Subir a Storage` y `Media: Registrar` —,
  mismo `onError: continueRegularOutput`, mismo timeout 30 s). Difieren en el nombre con sufijo ` (staff)`, el id,
  la posición y **dos desviaciones deliberadas**:
  1. las **10 referencias** `$('Media: Preparar')` de `Media: Registrar` pasan a `$('Media: Preparar (staff)')`
     (si se copiaran literales, la fila del staff se escribiría con los datos del nodo del paciente, que en esa
     ejecución ni ejecutó). El script lo hace con una sola sustitución y aborta si queda alguna;
  2. `Media: Preparar (staff)` lleva el `media/preparar.js` **del repo**, que tiene 45 líneas más que el jsCode
     del nodo vivo del paciente: los guards de JID (R1, §8.3). El script exige que el jsCode vivo sea ese mismo
     archivo **menos líneas** (solo opcodes `insert` en el diff, y entre lo insertado tienen que estar los DOS
     guards: el motivo `grupo_o_estado` y el whitelist `ED.fromMe` + `@s.whatsapp.net`): si alguien editó el nodo
     en la UI, aborta. El nodo del paciente **no se toca acá** — los guards son no-op para él y su PUT va aparte,
     con `apply_media_entrantes.py` y su propio OK.
- **`Media: ¿Hay archivo? (staff)` es idéntico al del paciente** (`$json.hay_archivo === true`). Ya no lleva los
  guards de JID: se movieron a `preparar.js`, donde valen para las dos ramas y donde el archivo todavía no se subió.
- **Nodo nuevo de verdad**: `Media: Actualizar memoria (staff)` (postgres 2.5 `executeQuery`, credencial
  "Postgres Supabase Nexora v3", `onError: continueRegularOutput`, sin `queryReplacement`). Su `query` es la
  expresión de `media/actualizar_memoria_staff.js`, que arma el SQL con escape propio (§8.2).
- **Único nodo existente modificado**: `Postgres - Save fromMe`, y **solo** su `query`, que pasa de
  `INSERT INTO n8n_chat_histories(session_id, message) VALUES ($1, $2::jsonb)` a la misma con ` RETURNING id`.
  Mismo nodo, mismo `queryReplacement`, misma credencial, mismo `onError` (ninguno). Verificado en el v6 vivo:
  hoy ese nodo devuelve `{success: true}` (salida real de la exec 272xxx) y **nada aguas abajo usa su `$json`**
  (`CW Search Contact` manda `q = $('Edit Fields - Extraer Datos').first().json.phone`; `CW Extract Conv` lee la
  respuesta HTTP de esa búsqueda), ni hay una sola referencia `$('Postgres - Save fromMe')` en los 153 nodos.
  Con `RETURNING id` devuelve **un** item `{id: "<bigint como string>"}` — el conteo de items no cambia.
- **Un solo item**: `CW Set Label humano` devuelve `{"payload": ["humano"]}` — un objeto, no un array — verificado
  en 4 ejecuciones reales (272695/272696/272697/272709). Importa porque si devolviera un array, n8n lo partiría en
  N items y `Media: Preparar (staff)` subiría el mismo archivo N veces con N ids distintos. Con `onError:
  continueRegularOutput` un fallo tampoco cambia el conteo: emite un item con `{error}`, y `Preparar (staff)` no
  usa `$json` más que para `text` (que en esta rama no existe y queda `''`, como debe).
- Posiciones: fila propia libre en **y=1780**, x 6128 → 7568 (paso 288), a la derecha de `CW Set Label humano`
  [5840,800] y **630 px por debajo** de la cadena Media del paciente (y=1150). La separación es de 3 filas y no de
  una a propósito: las dos cadenas comparten el prefijo `Media: ` y las columnas x, y pegadas se confunden al leer
  una ejecución en el canvas. Acá el orden de ejecución **no** depende de la posición: hay una sola rama y es serial.

### 8.2 Contrato del `content`: el token llega por UPDATE, no armando la fila
`Build fromMe AI memory` **no se toca**: la fila que escribe (TAG + caption o placeholder, `additional_kwargs`
con `source: 'wa_outbound'`, `from_iri_or_dra`, `was_multimedia` en el mismo orden) es **byte a byte la de hoy**.
El token se agrega después, sobre la fila ya escrita:

```sql
UPDATE n8n_chat_histories
SET message = jsonb_set(
      jsonb_set(message, '{content}', to_jsonb((message->>'content') || ' [MEDIA:<id>]')),
      '{additional_kwargs}',
      COALESCE(message->'additional_kwargs', '{}'::jsonb) || '{"media_id":"<id>","media_tipo":"image"}'::jsonb)
WHERE id = <id de la fila> AND message->>'content' NOT LIKE '%[MEDIA:%'
RETURNING id
```

| Caso | `content` que queda en `n8n_chat_histories` |
|---|---|
| texto normal | `TAG + texto` — **byte a byte lo de hoy** (la cadena Media ni corre: `hay_archivo:false`) |
| foto/audio/doc **sin** caption, archivo registrado | `TAG + '[mensaje multimedia … sin texto adjunto]' + ' [MEDIA:<id>]'` |
| foto **con** caption, archivo registrado | `TAG + caption + ' [MEDIA:<id>]'` |
| sin archivo, subida fallida, INSERT fallido, id que no coincide, grupo/estado, Chatwoot sin conversación | **byte a byte lo de hoy** (el UPDATE es un no-op o no llega a correr) |
| sin `phone` | `[]`, igual que hoy (`Build fromMe AI memory` no emite nada y se corta todo) |

- **Una sola fila, siempre, y por id**: `WHERE id = <n>` con el id que devolvió el INSERT (n8n/node-postgres
  traen los `bigint` como **string**: `"6516"` — verificado en la salida real de `Check Session Age`; el SQL lo
  valida con `/^[1-9][0-9]{0,17}$/` antes de inyectarlo crudo). Verificado con `EXPLAIN` contra el v3 real: entra
  por la PK (`Index Scan using n8n_chat_histories_pkey`).
- **Sin id, FALLA CERRADO** (2026-09-07): devuelve el no-op, no adivina. Hubo un fallback heurístico —"la última
  fila de esta sesión cuyo `content` sea exactamente el que acaba de escribir `Build fromMe AI memory`"— y se
  **sacó**: bajo concurrencia real le pega el token a la fila **equivocada**. Si la doctora manda dos adjuntos
  **sin caption** al mismo paciente y el INSERT de la ejecución B entra antes del UPDATE de la A, las dos filas
  tienen el `content` idéntico (TAG + placeholder) y el `ORDER BY id DESC LIMIT 1` de A toma la fila de B (y
  después B toma la de A): dos tokens cruzados, **cada burbuja con la foto de la otra**. En un chat médico mostrar
  la foto equivocada es peor que no mostrar ninguna. Además era código muerto: el `RETURNING id` siempre llega (si
  el INSERT fallara, el nodo no tiene `onError` y la ejecución se corta antes). La degradación visible pasa a ser
  "el adjunto no se linkea" (el chip de siempre), nunca "el adjunto se linkea mal". Tests: §4 de
  `test_media_fromme.js`, incluido el caso concurrente (4k).
- **Idempotente**: `NOT LIKE '%[MEDIA:%'` — una segunda corrida no duplica el token.
- **Gate**: el UPDATE solo se arma si `Media: Registrar (staff)` devolvió LA fila — mismo criterio que
  `media/marcar_expr.js` en la rama del paciente (`!error`, `bucket === 'pacientes-media'`, `id` igual al de
  `Media: Preparar (staff)`, que además dio `hay_archivo === true`) **más** la validación de que el id sea 16 hex
  (va crudo al SQL). Si no se cumple, la expresión devuelve `SELECT 1 WHERE false`: el nodo es un Postgres y no
  puede saltearse a sí mismo, así que el gate vive en el SQL y no toca ninguna fila.
- **Escape**: sin `queryReplacement` (n8n parte por coma: un caption con coma rompería — lección 5/9). Los
  valores se escapan con el mismo `esc` de `triaje/decidir.js`, que duplica las comillas simples y saca los `$`
  del literal (pg-promise interpreta `$N` como parámetro). Desde que el fallback se fue, **lo único** que llega al
  SQL es el id (16 hex) y el `media_tipo` (whitelist de 5): ningún texto libre del paciente ni de la doctora.
  Nota para el próximo que lo toque: sacar los `$` parte el literal en trozos unidos por `||`, y `::` liga **más
  fuerte** que `||` — un valor con `$` pegado a un cast quedaría como `'x' || chr(36) || ('y'::jsonb)`, otro SQL.
  Hoy no puede pasar (lo único pegado a `::jsonb` son las kwargs) y el test 5b lo vigila; si alguna vez entra un
  valor libre en esa posición, hay que envolverlo: `(esc(v))::jsonb`.
- El **TAG** y el **placeholder** no cambian ni una letra: los miran los system prompts de los sub-agents,
  `previewDe()` y `FROMME_MULTIMEDIA_RE` del panel. Como `Build fromMe AI memory` ni se abre, no hay forma de
  romperlos con este cambio.
- Consumidores verificados: `Build Router Context` filtra por igualdad contra los intents y `[NO_REPLY]` y por
  `LIKE '[CONTEXTO%'` — el content fromMe empieza con `[ATENCION HUMANA`, así que pasa igual (el sufijo suma 26 ch
  al contexto del Router). El único nodo del v6 que mira `additional_kwargs.source` es `Clear Old Memory`, que NO
  borra las filas `wa_outbound`; el UPDATE conserva ese `source` (hace merge, no reemplazo). Riesgo R3 (eco del
  token en la salida del LLM) sigue abierto como P2.

### 8.3 Riesgos propios de esta rama
- **R1 (ALTO) — chats que NO son 1:1 (grupo, estado, lista de difusión, canal, LID): CERRADO en
  `media/preparar.js`.** El filtro `@g.us` / `status@broadcast` del v6 vive en `Filtrar duplicados y basura`, que
  cuelga de `Es fromMe?`**[1]** (rama del paciente): **la rama fromMe no filtra nada**. Si la doctora manda una
  foto **al grupo de derivaciones** (que recibe escalaciones con datos clínicos), publica un **estado**, o escribe
  en una **lista de difusión** / un **canal** / un chat **LID** desde el celular del consultorio, `Extraer Datos`
  recorre `[Chat, Sender, RecipientAlt, SenderAlt]` buscando el primero que termine en `@s.whatsapp.net`: como
  `Info.Chat` no lo es, se queda con `Info.Sender` = **el número del propio consultorio**, que pasa el chequeo de
  largo. El archivo terminaría en `pacientes-media/<nro del consultorio>/…`, con su fila en `media_entrantes` y la
  foto renderizada en una "conversación" **fantasma** del panel. Hoy eso ya ensucia `n8n_chat_histories`, pero con
  texto; sería la primera vez que se guardan **archivos**.

  Los guards, en `media/preparar.js` (compartido por las dos ramas), justo después del chequeo de teléfono:
  ```js
  const jids = [info.Chat, info.RecipientAlt, info.SenderAlt, telefono].map((j) => String(j || ''));
  // (1) blacklist, las dos ramas
  if (jids.some((j) => j.includes('@g.us') || j.endsWith('@broadcast') || j.endsWith('@newsletter'))) return sinArchivo('grupo_o_estado');
  // (2) whitelist, SOLO el staff: exige un JID 1:1 en vez de listar exclusiones
  if (ED.fromMe && !/@s\.whatsapp\.net$/.test(String(info.Chat || ''))) return sinArchivo('grupo_o_estado');
  // (3) largo E.164
  if (telPath.length < 8 || telPath.length > 15) return sinArchivo('grupo_o_estado');
  ```
  Son **tres** y no uno a propósito (regla dura 5). El (2) solo ya cierra la rama del staff — y es un **whitelist**,
  así que también cierra `@lid` y cualquier familia de JID que WhatsApp invente mañana, que es justo lo que un
  blacklist deja pasar por definición (`ED.fromMe === true` ⇔ salida [0] de `Es fromMe?`, que testea exactamente
  `$json.fromMe === true`: el guard es exactamente esa rama). El (1) y el (3) siguen valiendo para la rama del
  paciente, donde `Filtrar duplicados y basura` arrastra el mismo blacklist incompleto que tenía este archivo.
  `@lid` **no** entra en el blacklist a propósito: en la rama del paciente un `phone` `…@lid` es un 1:1 legítimo y
  hoy se sube (columna verbatim + path con dígitos, test 17b).

  Va en `preparar.js` y no en la IF porque es el único lugar donde el archivo **todavía no se subió** y porque así
  vale para las dos ramas. Para la del paciente es **no-op** (ya viene filtrada aguas arriba) y no cambia ningún
  motivo existente: corre DESPUÉS de `sin_base64` y `sin_telefono`. Con `hay_archivo:false` la cadena muere en la
  IF y **no pasa nada más**: la fila de memoria y el label ya se escribieron aguas arriba, exactamente como hoy.
  **Decisión explícita sobre el largo**: un LID de 16-17 dígitos se **descarta** (los LID reales suelen ser de 15,
  que entra). Falla cerrado: un jid de grupo pelado son 18 dígitos y el margen es de un solo dígito, así que subir
  un archivo bajo un número que no es un teléfono es peor que perder el adjunto (el chat sigue mostrando el chip
  de siempre). Si algún día aparece un LID largo real, se sube el tope y se re-corre el test.
  Tests: `test_media_nodos.js` §23 (29 checks, incluidos los de no regresión y el borde de largo del LID) y
  `test_media_fromme.js` §7 (18).
- **R5 (ALTO) — el SILENCIAMIENTO no puede quedar detrás de Storage: RESUELTO cambiando el orden.** Ver §8.1.
  El primer diseño colgaba la cadena Media de `Es fromMe?`[0] y movía la de Chatwoot; el segundo (este) no mueve
  nada y cuelga la cadena Media del final. Es estrictamente más seguro: no depende del orden en que n8n resuelve
  dos ramas hermanas (array vs. posición en el canvas), porque **no hay** dos ramas.
- **R13 (MEDIO, nuevo por este orden) — si Chatwoot no encuentra el contacto, el archivo no se archiva.**
  `CW Extract Conv` devuelve `[]` si la búsqueda no trajo contacto, y `CW Pick Conv` devuelve `[]` si ese contacto
  no tiene conversaciones: en esos casos `CW Set Label humano` no ejecuta y la cadena Media tampoco. Consecuencia:
  la fila de memoria queda **sin** token y el panel muestra el chip de siempre (o sea, lo de hoy). Un error HTTP
  de Chatwoot **no** rompe la cadena (`CW Search Contact`, `CW Get Conversations` y `CW Set Label humano` tienen
  `onError: continueRegularOutput`); solo la corta un `[]`. Se acepta a propósito: entre "no archivar un adjunto"
  y "demorar el silencio del bot", gana el silencio. Si algún día molesta, el arreglo es colgar la cadena Media de
  `CW Pick Conv`… no: es el mismo problema. Sería hacer que `CW Extract Conv` / `CW Pick Conv` emitan un item
  vacío en vez de `[]` — cambio en dos nodos de la cadena de silenciamiento, PUT aparte y con prueba propia.
- **R14 (MEDIO, nuevo) — el token llega segundos después que la fila, y el Logger puede fotografiar el "antes"
  PARA SIEMPRE: CERRADO del lado del panel.** El panel ve el INSERT de la memoria (sin token) y después el INSERT
  de `media_entrantes`; el UPDATE que agrega el token **no** genera evento Realtime (la publicación solo lleva
  INSERT). Eso solo sería un retardo de segundos… si no fuera por el **Logger**: el workflow
  `Logger Conversaciones (Supabase)` (`xsXeHp7WLXnFQc3o`, ACTIVO, cron cada 5 min) copia `n8n_chat_histories` →
  `conversaciones` (`PG - SELECT nuevos` con `WHERE id > MAX(chat_history_id)`, `HTTP - Insert Conversacion` con
  `Prefer: resolution=ignore-duplicates` + `on_conflict=chat_history_id`): **la copia se escribe una vez y nunca
  se corrige**. Si el cron cae dentro de la ventana INSERT→UPDATE, `conversaciones` queda sin token para siempre —
  y el panel **prefiere** `conversaciones`: el dedup por timestamp en ms descarta la fila de memoria (la que SÍ
  tiene el token) en `lib/chat-data.ts` y `lib/conversaciones-data.ts`. Resultado sin arreglo: la foto **no aparece
  nunca más**, ni con F5, ni con el poll de 20 s, ni al día siguiente; el problema no es *cuándo* se refetchea sino
  *cuál* de las dos fuentes gana, así que ni la repesca a 1,5 s ni el poll ayudan.
  **Medido, no supuesto**: (a) el dedup siempre matchea — `date_trunc('milliseconds', c.timestamp) =
  date_trunc('milliseconds', h.created_at)` da 190/190 filas en 3 días; (b) la ventana real es de ~1,4 s para una
  foto (exec 272509: 0,929 s de `Media: Preparar` a fin de `Media: Registrar`, más 0,229-0,494 s de
  `Postgres - Save fromMe` a fin de `CW Set Label humano` en las exec 272695/272697/272709) y hasta 30 s con un
  video o el timeout de Storage; (c) volumen: 191 filas fromMe multimedia en 13 días (14,7/día). Exposición
  ≈1,4/300 por adjunto ⇒ del orden de **1 adjunto perdido cada ~2 semanas**, y varios % por cada video.
  **Arreglado en el panel, sin tocar n8n** (`rescatarTokensMedia` en `lib/media-entrantes.ts`, llamado desde los
  dos sitios de dedup): antes de descartar la fila de memoria, se le pasan a la de `conversaciones` los tokens que
  la memoria tiene y a ella le faltan. Ver §8.6. La alternativa del lado n8n —agregar
  `AND created_at < now() - interval '60 seconds'` a `PG - SELECT nuevos` del Logger— queda anotada como plan B:
  es un PUT a OTRO workflow, fuera de la rama fromMe, y necesita su propio OK.
- **R11 (BAJO, preexistente, ahora se duplica) — objetos huérfanos en Storage.** Si la subida sale OK y
  `Media: Registrar (staff)` falla (`onError: continueRegularOutput`), el archivo queda en `pacientes-media` **sin**
  fila en `media_entrantes`, y el satélite de retención borra POR FILA
  (`create_retencion_satelite.py`: `SELECT id, bucket, path FROM media_entrantes WHERE created_at < now() -
  interval '90 days'`), así que ese objeto no se recolecta nunca. Ya pasaba con la rama del paciente; con la del
  staff (≈13,5 archivos/día más, ver R9) se duplica la exposición. Cuando moleste: barrido de `storage.objects`
  sin fila en `media_entrantes`.
- **R12 (BAJO, preexistente) — la rama fromMe no dedupea webhooks.** El único nodo que dice "duplicados" es
  `Filtrar duplicados y basura` (y cuelga de `Es fromMe?`[1]; además ni siquiera dedupea por `key_id`). Si Evolution
  reentregara el mismo webhook fromMe, hoy se guardan dos filas de memoria; con este cambio, además, se suben **dos
  copias** del archivo con ids distintos y quedan dos filas en `media_entrantes` (el `x-upsert` no ayuda: el path
  lleva un id aleatorio). Cada UPDATE toca su propia fila de memoria, así que no se pisan. No se vio ninguna
  reentrega en 13 días de logs.
- **R9 (BAJO) — volumen.** 13 días de webhooks fromMe: image 142, document 25, ptt 6, video 3 (hasta 5,1 MB) ⇒
  ~13,5 archivos/día extra a Storage, más que el flujo del paciente. Las alertas de uso ya están en el Vigía.
- **R10 (cerrado, era del diseño anterior) — `phone` vacío.** Ya no aplica: `Build fromMe AI memory` sigue siendo
  el primer nodo de la rama, así que con `phone` vacío devuelve `[]` y se corta todo igual que hoy (ni memoria ni
  label ni cadena Media). El recableado que lo abría se descartó.
- Retención: `create_retencion_satelite.py` borra por `created_at`/`bucket` **sin** filtrar `from_me` ⇒ los adjuntos
  del staff también se borran a los 90 días y el panel muestra "Adjunto vencido". Nada que tocar.

### 8.4 Cómo probar
1. `node tests/test_media_fromme.js` (69 checks: SQL del UPDATE en el camino feliz, los caminos de no-op —
   incluido el concurrente que motivó sacar el fallback—, lo único que entra al SQL, y los casos de JID que no es
   1:1 de `preparar.js`) y `node tests/test_media_nodos.js` (83, sin regresión: los 29 de §23 son de los guards de
   JID). `node tests/test_retencion_y_staff.js`. `python -m py_compile scripts/apply_media_fromme.py` y
   `python scripts/check_triaje.py` (TODO SANO, regla dura 9). Del lado del panel:
   `npx tsc --noEmit -p tsconfig.json`.
2. `python scripts/apply_media_fromme.py` (dry-run: nodos nuevos con tipo/versión/credencial/onError, el bloque
   SILENCIAMIENTO, diff de conexiones, el único nodo existente modificado con su query antes/después,
   **"Fuera de la rama fromMe: 0 nodos, 0 conexiones"** — la rama del paciente, su cadena Media y toda la cadena de
   silenciamiento cuentan como "fuera" y abortan el script —, `webhookId True`, 153 → 159 nodos) → mostrarle el
   diff a Lucas → `--apply`.
3. Orden de despliegue: **el panel primero** (tiene que saber colgar adjuntos en las burbujas de staff; si no, la
   foto no aparece y el chip sigue). La tabla y el bucket ya existen desde la rama del paciente.
4. Prueba real: desde el celular del consultorio, a un chat de prueba, una foto **con** caption y otra **sin**,
   un audio y un PDF.
   ⚠️ **El chat de prueba tiene que ser uno donde el paciente YA escribió antes** (y por eso existe el contacto y
   la conversación en Chatwoot). Si el número es nuevo, `CW Extract Conv` o `CW Pick Conv` devuelven `[]`,
   `CW Set Label humano` no ejecuta y **la cadena Media entera no corre** (R13): el adjunto no se archiva y va a
   parecer que el cambio no funciona, cuando en realidad es el comportamiento esperado.
   Verificar (a) la ejecución pasa por `Media: Registrar (staff)` (devuelve la fila) y por
   `Media: Actualizar memoria (staff)` (su salida tiene que ser `{id: …}`, no `{success: true}`: si sale
   `success` el UPDATE no tocó ninguna fila y hay que mirar el SQL que armó);
   (b) `select id, tipo, from_me, telefono, caption from media_entrantes where from_me order by created_at desc limit 5`;
   (c) el content en `n8n_chat_histories` termina en ` [MEDIA:<id>]` y `additional_kwargs` tiene `media_id`;
   (d) el panel pinta la imagen (no el chip) con autor "Dra. Raquel", **unos segundos después** de que aparezca
   la burbuja de texto (el token llega por el UPDATE, ver §8.6).
5. **Prueba del silenciamiento (obligatoria, es lo más importante)**: con el bot ENCENDIDO, el teléfono de prueba
   escribe algo que el bot contestaría; ~5 s después la doctora responde desde el celular del consultorio **con
   una foto** (mejor si es la más pesada a mano). Verificar en la ejecución de n8n que `CW Set Label humano` corre
   ANTES de `Media: Subir a Storage (staff)` — con este cableado es imposible que no pase, está aguas arriba —,
   que el label queda puesto en Chatwoot en ~1-2 s (igual que hoy) y que el bot NO contesta.
   Bonus: mandar una foto **al grupo de derivaciones** y confirmar que NO aparece ninguna fila nueva en
   `media_entrantes` y que en la ejecución `Media: Preparar (staff)` devuelve `motivo: 'grupo_o_estado'` (R1).
6. Limpiar en el mismo turno (regla dura 9): `python scripts/limpiar_numero_demo.py` + borrar las filas de prueba de
   `media_entrantes` y los objetos del bucket.

### 8.5 Cómo revertir
- **Cableado + query** (deja los 6 nodos huérfanos, cero riesgo):
  `python scripts/apply_media_fromme.py --rollback-wiring` → `CW Set Label humano` vuelve a ser hoja (sin salida),
  `Postgres - Save fromMe` vuelve a la query sin `RETURNING id` y los 6 nodos `Media: * (staff)` quedan sin
  conexiones. **La cadena de silenciamiento no se tocó nunca**, así que revertir no la mueve. El comando verifica
  las dos cosas después del PUT.
- **Total**: `python scripts/apply_media_fromme.py --rollback workflows/history/v6_PRE_media_fromme_<ts>.json`.
  El cableado y la query previos también quedan sueltos en `v6_PRE_media_fromme_wiring_<ts>.json`.
- Datos: las filas con `from_me=true` en `media_entrantes` son aditivas; pueden quedar (el panel las ignora si el
  content no tiene el token). Los tokens ya escritos en `n8n_chat_histories` también: el panel los resuelve o cae
  al chip si la fila de media no está.
- El panel tolera los dos estados: un mensaje de staff sin `[MEDIA:]` sigue mostrando el chip de siempre.

### 8.6 Lado panel: el token llega DESPUÉS del INSERT
La parte E del panel (adjuntos de staff: `esMensajeDeStaff` / `puedeTenerAdjuntos` en `lib/media-entrantes.ts`,
`getChatData`, `previewDe`, `textoStaffLimpio`) **no se rehizo**: sigue resolviendo el adjunto por el token del
`content`, sin importar cuándo se escribió. Pero **sí necesitó dos ajustes**, porque este diseño cambia el
**momento** en que aparece el token — y uno de esos dos no es cosmético (R14):

1. `t=0` — INSERT en `n8n_chat_histories` **sin** token → evento `memoria` → refetch → la burbuja del staff
   aparece con el placeholder / el caption y el chip de siempre (idéntico a hoy).
2. `t≈+0,3-30 s` — INSERT en `media_entrantes` → evento `media` → refetch.
3. `t≈+0,3-30 s` (unos ms después del 2) — UPDATE que agrega el token. **No genera evento**: la publicación
   `supabase_realtime` de `n8n_chat_histories` solo lleva INSERT, y el bus (`lib/live/bus.ts`) escucha INSERT.

**Ajuste 1 — repesca del refetch** (`components/conversaciones/chat-view.tsx`, cosmético). El refetch del paso 2
es el que trae el content ya actualizado. El UPDATE es el nodo siguiente en n8n (~50-200 ms) contra ~400 ms-1,5 s
de Realtime + SSE + debounce de 150 ms + query, así que gana casi siempre; pero es una carrera, y perderla dejaba
la foto sin aparecer hasta el poll de seguridad de 20 s. Cuando el lote coalescido trae un evento `media`, además
del refetch normal se programa **uno solo** a 1,5 s (`REFETCH_MEDIA_TARDIO_MS`), cancelado al desmontar y salteado
con la pestaña oculta. Un GET extra por evento `media` (~25/día entre paciente y staff).

**Ajuste 2 — rescate del token del lado del panel** (`rescatarTokensMedia` en `lib/media-entrantes.ts`, llamado
desde `lib/chat-data.ts` y `lib/conversaciones-data.ts`). **Este no es cosmético: sin él la foto se pierde para
siempre** cuando el cron del Logger cae dentro de la ventana INSERT→UPDATE (R14 en §8.3: `conversaciones` queda
con el texto sin token, se escribe una sola vez y nunca se corrige, y el dedup por timestamp del panel descarta la
fila de memoria que sí lo tiene). El arreglo: **antes** de descartar la fila de memoria, se le pasan a la de
`conversaciones` los tokens que la memoria tiene y a ella le faltan (`mensaje` + completar `metadata` sin pisarla,
en el chat; solo `mensaje` en la lista, que es lo que el preview necesita). El token se agrega **al final**, que es
exactamente donde lo pone el UPDATE del v6, así que el texto rescatado queda igual al de la memoria; el usuario no
ve el token (`sinTokensMedia` lo saca, como en cualquier otra fila). Es idempotente (si ya está, no hace nada) y
respeta R3: **solo** rescata sobre filas que pueden tener adjuntos (`puedeTenerAdjuntos`), así que un eco del bot
sigue sin poder colgarse la foto de otro. Plan B del lado n8n, si alguna vez se prefiere arreglarlo en el origen:
`AND created_at < now() - interval '60 seconds'` en `PG - SELECT nuevos` del Logger (PUT a otro workflow, OK propio).

- La **lista** (`lib/conversaciones-data.ts`) lleva el mismo rescate que el chat, así que no hay asimetría. La
  repesca a 1,5 s no la tiene y no la necesita: su coalesce es de 400 ms (contra 150 ms del chat) y, sin token, el
  preview cae al "📎 Adjunto enviado desde el celular del consultorio" de siempre — menos detalle por unos
  segundos, nunca un estado erróneo.
- `metadataDeKwargs` (`lib/chat-data.ts`) es una **whitelist estricta**: copia `source`, `autor`, `media_url` y
  `media_tipo`. El `media_id` que este cambio agrega a `additional_kwargs` **nunca llega al panel** (el Logger
  tampoco lo copia a `conversaciones`): queda write-only, para diagnóstico en SQL. El panel resuelve el adjunto
  por el **token del content**, no por las kwargs. Ojo con `media_tipo`: la whitelist lo copia, y en las filas de
  staff ahora existe — es el mismo valor que la fila de `media_entrantes`, así que no contradice nada, pero si
  algún día se le da otro uso hay que mirar de dónde viene.
- `getChatData` trae `media_entrantes` **por teléfono, sin filtrar `from_me`** (las filas del staff entran) pero con
  `limit(300)`: en un chat con muchísimos adjuntos, los más viejos dejan de resolver y la burbuja cae al chip. No es
  una regresión nueva, pero ahora el mismo cupo lo comparten paciente y staff (la rama fromMe es la de más volumen, R9).
- La lista resuelve los tokens del preview con las filas de `media_entrantes` de la **última hora** más una consulta
  puntual por los ids que quedaron sin resolver, para que el preview de un chat viejo no mute solo a los 60 minutos.
- **Eco del token (R3, sube a P1 con este cambio)**: el `[MEDIA:<id>]` viaja ahora también en las filas
  `[ATENCION HUMANA …]` que el LLM ve por `Build Router Context` y la memoria. El panel se defiende
  (`puedeTenerAdjuntos`: una fila del bot no recibe adjuntos) **pero la defensa tiene un agujero conocido**: si el
  LLM ecoa el **TAG completo** `[ATENCION HUMANA …]` junto con el token, `esMensajeDeStaff` da true por el TAG y
  la burbuja del bot pinta el adjunto del staff. Antes de este cambio ninguna fila con TAG tenía un token adentro,
  así que el eco no tenía nada que resolver; ahora sí. (Verificado con las funciones reales: una fila del bot con
  el token pero **sin** el TAG y con `additional_kwargs` sin `source` — la forma de las 130 filas reales del bot en
  20 días — NO recibe adjuntos.) El cierre real es determinístico y sigue pendiente:
  `text.replace(/\s*\[MEDIA:[0-9a-f]{16}\]/g, '')` en `Banlist Validator`. Es un cambio FUERA de la rama fromMe
  (toca la salida del bot), así que va como PUT aparte con su propio OK.
