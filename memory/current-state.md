# Estado actual — raquel-n8n

## 2026-09-10 01:40 ART — Triaje de urgencias ABIERTO A TODOS los pacientes

Lucas corrió `python scripts/create_triaje_config_tables.py --activar` (sin `--piloto`: en PowerShell
`--piloto ""` da error de argparse porque se come las comillas; omitirlo ya deja la allow-list vacía =
todos). `triaje_config`: activo=true, telefonos_piloto=[], modo='piloto', aviso_pasivo=false.
`check_triaje.py` -> TODO SANO (los 2 videos de alambre_pincha HTTP 200, v6 159 nodos, 7 satélites activos).

**Disparador**: el 9/9 entró la primera urgencia real de un paciente (…0362) — "Necesito un turno urgente
con la dra... se salió el alambre 🥺" (17:50) y una foto de la boca (19:12). Las dos quedaron
`razon='fuera_piloto'` en `triaje_urgencias_log` (ids 14 y 15) y escalaron al grupo sin video.

**Límite vigente**: solo `alambre_pincha` tiene videos (op1 y op2, activos). `bracket_suelto`,
`alambre_girado` y `ligadura_pincha` siguen con `activo=false` y caption '[PENDIENTE]' -> esos casos
escalan igual. La urgencia del 9/9 es de esa familia. Pendiente: que Raquel mande los 3 videos
(bracket_suelto primero: es el más frecuente junto con alambre_pincha en el análisis de 60 días).
Cuando lleguen: `scripts/upload_urgencia_video_supabase.py` + UPDATE de caption/activo +
`tests/test_triaje_textos_banlist.py --db`.

**A vigilar los próximos días**: primera urgencia real que caiga en alambre_pincha (tiene que recibir el
video op1 sin escalar), y `triaje_urgencias_log` por casos degradados (el Vigía avisa solo).

## 2026-09-08 16:15 ART — Recordatorio DISTINTO para las CONSULTAS: scripts listos, tests verdes, dry-run limpio, NADA aplicado

**Pedido textual de la Dra. (WhatsApp 09:20)**: los turnos con "puntito amarillo" son consultas (primera visita); a esos
mandarles un recordatorio propio que deje claro que "la confirmación es sí o sí con el pago" (bloque textual en
`docs/recordatorio-consultas-2026-09-08.md` §1). Workflow: `Recordatorio de Turno 48HS` (`7RqTApkvVavRmq3R`, ACTIVO).

- **Detección**: `motivo_atencion` EMPIEZA con "consulta" (`/^consulta\b/i`, trim; corrección de la tarde: el substring
  `/consulta/i` tomaba "Control post consulta" y le habría pedido el pago a un paciente en tratamiento). Verificado sobre
  66 citas próximas + 57 enviadas en 14 días: el único motivo con esa palabra es `Consulta Ortodoncia ` (con espacio
  final); `tratamiento_sin_asignar` es 0 en todas (no sirve). Las 5 consultas de los últimos 14 días recibieron el genérico.
- **Precio dinámico** desde `knowledge_base` id 21 (la Dra. lo edita en el panel): subconsulta `precio_contenido` en el SQL
  de `Gate - Leer config` (NO se puede insertar un nodo entre `Solo citas activas` y `Preparar mensaje`: emparejamiento
  por `$itemIndex`), leída con try/catch. Camino manual (webhook) → fallback `$50.000`.
- **3 nodos, 0 conexiones**: `Preparar mensaje` (jsCode = `recordatorios/preparar_mensaje.js`), `Gate - Leer config`
  (`recordatorios/gate_leer_config.sql`), `Insert recordatorios_enviados` (+ `motivo_atencion` text, `es_consulta` boolean).
  Todo lo que NO es consulta queda BYTE A BYTE (tests contra el snapshot vivo `recordatorios/preparar_mensaje.vivo_2026-09-08.js`).
- **Script** `scripts/apply_recordatorio_consultas.py`: `--dry-run` (default) / `--ddl` / `--apply` / `--rollback`. **Orden
  obligatorio `--ddl` → `--apply`** (el Postgres v2.6 valida contra la tabla viva y el Insert corre después del envío).
  Hoy la tabla NO tiene las columnas (dry-run: "FALTA --ddl"). DDL también en `rebuild_v3_schema.sql` §4.
- Tests: `tests/test_recordatorio_consultas.js` **87/87** (74 + 13 de la ronda de corrección); los otros 5 suites sin
  regresión (83/69/98/45/87).
- **Ronda de corrección (misma tarde, 2026-09-08)**: regex de detección anclado (`/^consulta\b/i`); regex del precio
  `/\$\s*(\d{1,3}(?:[.,]\d{3})+|\d{4,})/` (cualquier cantidad de espacios; "$50mil"/"$5" → fallback en vez de "$50");
  script: `flag_vivo()` con mensaje claro si falta la línea TEST_MODE, `gate_suspender_intacto` mira la query REAL del
  nodo, `--rollback` solo acepta un PRE (nombre `_PRE_` + jsCode = snapshot vivo; un POST re-aplicaría); doc §6.4:
  el primer envío real con el bloque nuevo sale por el CRON (si se aplica el 8/9 → mié 9/9 08:00 ART → vie 11/9, cita
  8899 consulta) y hay checklist de revisión + rollback listo; panel: `V3Recordatorio` con `motivo_atencion?` /
  `es_consulta?` opcionales (solo tipos, sin UI). NO aplicado: `motivo_atencion || null` (sin poder probar el null en el
  Postgres v2.6 punta a punta), R7 (decisión de negocio), alinear el regex del v6 (PUT aparte).
- **Hechos que corrigen premisas**: el cron es `0 13 * * 1-5` sin timezone → corre **08:00 ART lunes a viernes** (instancia
  UTC+2), no 9:00; el 24h NUNCA sale por cron (57/57 fueron 72h) → la variante consulta-24h solo por webhook manual.
- **Pendiente**: (1) Lucas confirma con la Dra. que puntito amarillo = motivo `Consulta Ortodoncia`; (2) la Dra. valida la
  frase del 24h; (3) OK → `--ddl` → `--apply` → prueba real: crear en Dentalink una cita "Consulta Ortodoncia" para
  `Test - Lucas Silva` (608) y `POST /webhook/trigger-recordatorios-manual {"fecha_target":"YYYY-MM-DD","id_paciente_filter":[608]}`
  (ints; NO usar el botón "adelantar" del panel: va a todos) → limpieza regla 9 + borrar las filas de
  `recordatorios_enviados` de la cita + anular la cita. Decisión abierta R7: el bot confirma cualquier "confirmo" sin pago.

## 2026-09-07 20:55 ART — APLICADO: formato de turnos pedido por la Dra. Raquel (3 workflows)

**Pedido textual de Raquel (WhatsApp, 15:39-15:55)**: no nombrar Dentalink al paciente; ofrecer el bloque
agrupado por mañana/tarde con al menos 2 de cada una, las más próximas; y NO preguntar franja ni fecha
("nosotros atendemos en horarios y días específicos... solo procedemos en decirles qué turnos disponemos
y ellos eligen"). Bloque final en `docs/turnos-formato-2026-09-07.md`.

**Aplicado con `scripts/apply_turnos_formato_raquel.py --apply`** (backups PRE/POST de los 3 en
workflows/history/, todas las verificaciones post-PUT en verde):
- `Sub-WF - Buscar Horarios Validado` (GuDQ9VmKWZvQnerV): 6 → 22 nodos. `Format Slots` arma el bloque
  listo para copiar; el token de Dentalink SALE del jsCode (ahora paginado por cursor en nodos
  httpRequest con la credencial "Header Auth account 3"): de hasta 91 llamadas (~80 s) a 6 como techo
  (~2 s típico). `fecha` deja de ser obligatoria (sin fecha = hoy, Jujuy) y aparece `desde` para el
  lote siguiente.
- `Sub-WF - CancelarReprogramar` (5cAWJxiWJ50hxEq3): 6 nodos editados. **De acá salían las 3 capturas**,
  no del `Sub-Agent Cancelar` (que está HUÉRFANO, sin conexión de entrada, desde hace meses). Step 5 ya
  no pregunta franja/fecha; Step 0b aprende a reconocer el bloque y arrastra el lote; al 2º rechazo escala.
  `Step 6b: GET Agendas` (httpRequest) → `Step 6b: Buscar Horarios (bloque)` (executeWorkflow): **único
  cambio estructural, lo primero a mirar en la prueba real**.
- `v6` (O155MqHgOSaNZ9ye): 8 campos, 0 conexiones. Tool `buscar_horarios` reescrita; prompts de Agendar
  (10 fragmentos), Cancelar, General y Formatting Agent; `Necesita Formatting?` y `Split en Mensajes`
  con 3 capas para que el bloque llegue INTACTO (bypass + guard determinístico + regla del prompt).

**Bugs latentes encontrados y arreglados en el camino** (no los pidió nadie, habrían roto el pedido):
- Step 0b del canrep no reconocía el bloque nuevo → el paciente elegía un turno y se perdía.
- `last_bot_msg` se guardaba cortado a 300 chars; el bloque mide ~230 + el saludo → se cortaba en
  "Por la tarde".
- El paciente que rechazaba el bloque recibía el MISMO bloque indefinidamente, sin escalar nunca.
- `siguiente_desde` usaba el máximo de las dos franjas → el lote 2 se salteaba mañanas más próximas.

**Pendiente**: prueba real punta a punta (pedir turno / "a la tarde" / "ninguno me sirve" / reprogramar)
y limpieza con `limpiar_numero_demo.py`. Tests: `tests/test_turnos_formato.js` 87 checks; los 5 suites
del repo en verde.

## 2026-09-07 (tarde) — Adjuntos del STAFF (rama fromMe): REDISEÑADO + 2ª ronda de correcciones, sin aplicar

El primer diseño (5 nodos `Media: * (staff)` colgados de `Es fromMe?`[0] + jsCode nuevo en `Build fromMe AI memory`)
quedó **bloqueado** por dos motivos y se rehízo entero; el rediseño pasó por una **segunda** revisión adversarial
que encontró otros dos must-fix (abajo). Nada aplicado: falta el OK de Lucas para
`python scripts/apply_media_fromme.py --apply` (dry-run limpio contra el v6 vivo, 153 → **159 nodos**).

- **Must-fix 1 (silenciamiento)**: el label `humano` de Chatwoot es lo ÚNICO que calla al bot en esta rama, y la
  cadena Media metía hasta 30 s (timeout de Storage) por delante. Ahora la cadena de silenciamiento
  (`Es fromMe?`[0] → `Build fromMe AI memory` → `Postgres - Save fromMe` → los 5 `CW *`) **no se toca ni una
  arista** y los 6 nodos nuevos cuelgan de la salida de `CW Set Label humano`, que hoy no tiene ninguna.
- **Must-fix 2 (grupos)**: el filtro `@g.us` / `status@broadcast` vive en `Filtrar duplicados y basura`, que cuelga
  de `Es fromMe?`[1] (rama del paciente): la del staff no filtraba nada. Ahora está en `media/preparar.js`
  (compartido por las dos ramas, motivo `grupo_o_estado`; no-op para el paciente) + guard de largo 8-15 dígitos.
- **Must-fix 3 (2ª ronda) — el blacklist de JID estaba incompleto**: cubría `@g.us` y la igualdad exacta con
  `status@broadcast`, pero NO las listas de difusión (`<id>@broadcast`), los canales (`<id>@newsletter`) ni los
  chats LID (`<id>@lid`). En los tres, `Extraer Datos` no encuentra un `@s.whatsapp.net` en `Info.Chat` y cae a
  `Info.Sender` = **el número del propio consultorio**, que pasa el guard de largo: el archivo se subía al bucket
  privado bajo el número de la clínica (reproducido con el archivo real). Arreglo: además de ampliar el blacklist
  (`endsWith('@broadcast')` / `'@newsletter'`), la rama del staff ahora exige un **JID 1:1** en `Info.Chat`
  (`ED.fromMe && !/@s.whatsapp.net$/` → `grupo_o_estado`). Es un **whitelist**: cierra también `@lid` y cualquier
  familia futura, que es justo lo que un blacklist deja pasar. No-op para la rama del paciente.
- **Must-fix 4 (2ª ronda) — el token se podía perder PARA SIEMPRE (panel)**: el Logger (`xsXeHp7WLXnFQc3o`, cron
  5 min) copia `n8n_chat_histories` → `conversaciones` con `ignore-duplicates`; la copia se escribe una vez y
  **nunca se corrige**. Si el cron cae dentro de la ventana INSERT→UPDATE (~1,4 s por foto, hasta 30 s por video),
  `conversaciones` queda sin token y el dedup por timestamp del panel **descarta** la fila de memoria que sí lo
  tiene → la foto no aparece nunca más (ni con F5, ni con el poll de 20 s). Medido: el dedup matchea 190/190 filas
  en 3 días; 14,7 adjuntos fromMe/día ⇒ ≈1 perdido cada 2 semanas, varios % de los videos. Arreglado **en el
  panel, sin tocar n8n**: `rescatarTokensMedia` (`lib/media-entrantes.ts`) le pasa a la fila de `conversaciones`
  los tokens que la memoria tiene y a ella le faltan, antes de descartarla; llamado desde `lib/chat-data.ts` y
  `lib/conversaciones-data.ts`. Respeta R3 (solo filas que pueden tener adjuntos) y es idempotente.
- Como el content se escribe ANTES de subir el archivo, el token ` [MEDIA:<id>]` llega por un **UPDATE acotado**
  (`media/actualizar_memoria_staff.js`, nodo nuevo `Media: Actualizar memoria (staff)`): una sola fila por
  `id = <el que devuelve el INSERT>`, idempotente (`NOT LIKE '%[MEDIA:%'`), con `media_id`/`media_tipo` en
  `additional_kwargs` y escape propio (sin `queryReplacement`). SQL validado con `EXPLAIN` read-only contra el v3
  real (entra por la PK). **Falla cerrado**: sin ese id devuelve el no-op. Había un fallback heurístico por
  `session_id` + content exacto y se **sacó** — bajo concurrencia (dos adjuntos sin caption al mismo paciente, con
  el content idéntico) le pegaba el token a la fila equivocada y cada burbuja mostraba la foto de la otra.
- **Único nodo existente modificado**: `Postgres - Save fromMe`, y solo su `query` (+ ` RETURNING id`). Verificado
  que hoy devuelve `{success:true}`, que nada aguas abajo usa su `$json` y que no hay ninguna referencia
  `$('Postgres - Save fromMe')` en los 153 nodos. `Build fromMe AI memory` **no se toca**.
- Borrados: `media/fromme_memory.js`, `media/fromme_memory_previo.js`, `media/hay_archivo_staff_expr.js`.
- Panel (parte E, ya aprobada): **no se rehízo**, dos ajustes aditivos. (1) `chat-view.tsx` programa **un** refetch
  extra a 1,5 s cuando llega un evento `media`, porque el UPDATE del token no genera evento Realtime (la
  publicación solo lleva INSERT) — cosmético. (2) `rescatarTokensMedia` en `lib/media-entrantes.ts` +
  `chat-data.ts` + `conversaciones-data.ts` — **no** cosmético: es el must-fix 4. `npx tsc --noEmit` limpio.
- `apply_media_fromme.py` cierra el círculo DESPUÉS del PUT (`verify_post_put`): re-corre el chequeo de
  "fuera de alcance" contra lo que n8n REALMENTE guardó y compara **byte a byte** `Build fromMe AI memory` y los
  5 nodos CW. Antes la garantía dependía de que n8n devolviera los nodos verbatim (verificado empíricamente en 3
  pares PRE/POST del historial: el único nodo distinto es siempre el que el script tocó).
- Tests: `test_media_fromme.js` **69/69** (SQL del UPDATE, todos los caminos de no-op incluido el concurrente, lo
  único que entra al SQL, y los JID que no son 1:1), `test_media_nodos.js` **83/83** (§23: blacklist, whitelist del
  staff, borde de largo del LID; sin regresión), `test_retencion_y_staff.js` verde, `check_triaje.py` TODO SANO.
  Doc: `docs/media-entrantes-2026-09-06.md` §8 reescrita (grafo, R1 con las 4 familias de JID, R13, R14 con el
  Logger, §8.4 con el requisito de Chatwoot, §8.6 con los dos ajustes del panel).
- **Riesgo aceptado (R13)**: si Chatwoot no encuentra el contacto o la conversación (`CW Extract Conv` /
  `CW Pick Conv` devuelven `[]`), la cadena Media no corre y el adjunto no se archiva — la fila de memoria queda
  como hoy. Se prefiere eso antes que demorar el silencio del bot. **Consecuencia práctica para la primera
  prueba real**: hay que hacerla sobre un chat donde el paciente YA escribió antes (y por eso existe la
  conversación en Chatwoot); con un número nuevo la cadena Media no corre y parece que el cambio no funciona.
- **Anotado, NO hecho** (excede el "solo el RETURNING" que autorizó el brief): `Postgres - Save fromMe` no tiene
  `onError` (default `stopWorkflow`) y está en el camino crítico del silenciamiento — si ese INSERT falla,
  `CW Set Label humano` nunca corre y el bot no se calla. Es el comportamiento de HOY y el `RETURNING id` no lo
  empeora, pero ponerle `continueRegularOutput` haría el silenciamiento estrictamente más robusto (y el UPDATE
  degradaría solo: sin fila insertada no hay id ⇒ no-op). PUT aparte con su propia prueba.

## 2026-09-07 04:25 ART — APLICADO: Retención + Vigía uso + audio desde el panel (todo en producción)

- **Satélite staff** `jzxb5zUKCaJcvCgp` actualizado (`--update`, 17 nodos): acepta `media_tipo: audio`, tipo
  desconocido → 400 "media_tipo invalido", sin secreto → 400. E2E: OGG a `panel-media` + webhook audio → 200
  (Lucas recibió el audio), `ptt` → 400. Residuo del E2E borrado (memoria 6396, objeto, label humano → bot).
- **DDL** aplicado (`--ddl`): `media_entrantes.borrado_at` + índice parcial + `retencion_log`.
- **Panel** `191381b` deployado: micrófono en el composer (MediaRecorder → MP3 mono con lamejs; único
  formato saliente porque Evolution GO no tiene ptt y WhatsApp reproduce mp3 en todos los teléfonos),
  clip acepta mp3/m4a/ogg/wav, `enviarAudioAction`, render `[audio]/[video]/[document] <url>` del staff,
  adjuntos vencidos (410 → chip "Adjunto vencido (se guardan 90 días)"). Falta la prueba real del
  micrófono desde Chrome por Lucas (y verificar que el mp3 suene en iPhone/Android: P2).
- **Satélite Retención** `TKByjzVE8rGKTioT` creado y ACTIVO (cron 04:30 Jujuy): smoke por webhook
  `trigger-retencion-manual {"smoke":true}` → 200/200, marcados 0, 3 filas en `retencion_log`, sin WhatsApp.
  Primera corrida real: 2026-09-07 04:30 ART (verificar `retencion_log` / startedAt). Días: 90 pacientes-media,
  90 panel-media, 365 bandeja (constantes arriba de `create_retencion_satelite.py`).
- **Vigía** `1UbmAtUMtTBN9Bn3` actualizado (`--update`) y disparado a mano: señales db_bytes 21,4 MB,
  storage 9,2 MB, retencion_tabla true, 0 alertas. Alertas nuevas: base > 400 MB, storage > 800 MB,
  retención sin correr 26 h, query rota (dedupe 24 h). `check_triaje.py` ahora también vigila Vigía y Retención.
- Números medidos hoy (para responder "¿satura?"): base 20 MB / 500, storage 9 MB / 1 GB, n8n SQLite 2,8 GB
  (poda 14 días por default), disco VPS 63 GB libres.
- Pendiente de Lucas: probar el micrófono; decidir si conserva sus mensajes de prueba (foto+audio del 02:24).

## 2026-09-07 madrugada (02:50→) — Retención + alertas de uso + audio del staff: scripts listos, NADA aplicado

**Pedido de Lucas**: "¿todo lo de hoy puede saturar la base? dejame todo para que funcione y se autoregule" + mandar AUDIO
desde el panel. Medido: base 20 MB de 500, Storage 9 MB de 1 GB (plan free); lo único que crece en serio son los adjuntos
(video WhatsApp hasta 16 MB). Diseño y operación: `docs/retencion-y-uso-2026-09-07.md`.
**Entregado lado bot (sin PUT/POST, sin escrituras, sin mensajes)**:
- `scripts/create_retencion_satelite.py` → satélite `Áurea — Retención (archivos y bandeja)` (17 nodos, cron 04:30 Jujuy
  vía `settings.timezone`, webhook manual `trigger-retencion-manual` con `{"smoke": true}` para ejercitar el DELETE sin
  borrar nada): adjuntos del paciente > 90 días (DELETE REST `/storage/v1/object/pacientes-media` con supabaseApi
  `H1PRagttKC5kxSzs` → `borrado_at = now()`), objetos de `panel-media` > 90 días (listados desde `storage.objects`, nunca
  borrados por SQL), `mensajes_entrantes_live` > 365 días, log en `retencion_log` y WhatsApp a Lucas SOLO si falló.
  `--dry-run` (default) / `--ddl` / `--apply` (exige DDL) / `--activate` / `--update`. JS en `retencion/*.js`.
  **Dry-run corrido contra el v6 vivo y la base**: host v3 coincidente en 4 fuentes, borraría HOY 0/0/0, DDL falta.
- DDL idempotente (`media_entrantes.borrado_at` + índice parcial + `retencion_log`): en el script (`--ddl`),
  `rebuild_v3_schema.sql` §12/§13 y `create_media_entrantes.py` (creación fresca).
- `scripts/create_vigia_bot.py`: `Query señales` suma `db_bytes` / `storage_bytes` / `storage_pacientes_bytes`;
  `EVAL_JS` con `ventanaMin` por alerta (históricas 60 min) y 3 alertas nuevas con dedupe 24 h: `supabase_db_alto`
  (> 400 MB), `supabase_storage_alto` (> 800 MB) y `vigia_query_rota` (la query no devolvió nada → el Vigía queda ciego).
  Query validada con SELECT real (storage.objects legible con el rol del pooler). Falta `--update 1UbmAtUMtTBN9Bn3`.
- `scripts/create_panel_acciones_staff.py`: `Validar secreto` acepta `media_tipo` `audio`, filename conserva la extensión
  al recortar a 80, tipo vacío si no hay `media_url`; `Armar fila memoria` ya escribía `[audio] <url>\n<caption>`
  (comentario actualizado). Falta `--update jzxb5zUKCaJcvCgp` (necesita el secreto local en `%TEMP%`).
- `tests/test_retencion_y_staff.js` → **98/98 OK** (Validar/Memoria del staff, Vigía, Retención). `py_compile` OK.
**Revisión y corrección (7/9 ~06:00, ambos repos, nada aplicado)**: (1) el smoke del alta avisaba en falso: con 0 vencidos
`ids=[]` → `queryReplacement ''` → n8n no pushea `$1` (`there is no parameter $1`) → `marcados NaN` → WhatsApp; ahora
`Q_MARCAR_PARAM = ids.join('|') || '-'` y `resumen.js` no exige el UPDATE sin ids (test con el comportamiento real). (2)
`Q_PACIENTES` filtra `bucket = 'pacientes-media'` (sin starvation), `Q_PANEL` excluye `is_delete_marker`; `resumen.js` no cuenta
el path fantasma del smoke y deja **advertencia** (aviso sin fallido) si Storage devolvió 0 de N reales. (3) `--dry-run` sigue
contando aunque n8n no responda. (4) Vigía: `retencion_no_corrio` (24 h) si `retencion_log` existe y no tiene fila en 26 h,
leído con `to_regclass` + `query_to_xml` para no romper la query mientras la tabla no exista (SELECT validado). (5) Staff:
`media_tipo` desconocido con URL → error 400 (`¿Sin secreto?` → `Responder 401`/`Responder 400`, 17 nodos; antes caía a
`image` y mandaba a Evolution una URL no-imagen al paciente); `--recover-secret <id>` copia el secreto del nodo vivo a `%TEMP%`.
(6) Panel: lock síncrono del mic (`iniciandoRef`/`montadoRef`, doble click o cambio de chat con el prompt abierto dejaba un
stream grabando); formato ÚNICO MP3 48 kHz (webm/opus primero, AAC de Safari también se transcodifica; `OfflineAudioContext`
a 48 kHz: con un headset BT a 8 kHz lamejs sacaba MPEG-2.5 que el server rechazaba; el server ahora acepta cualquier sync de
capa III); chip "vencido" solo con 404/410 confirmado (`clasificarFalla`: HEAD a `/api/media` sin seguir el 302 / GET de 1
byte a la URL pública; Supabase responde `400 {"statusCode":"404"}` para un objeto ausente, verificado) y chip neutro "No se
pudo reproducir acá · abrir" para el resto; `<audio>` del staff `preload="none"`; `video/*` rechazado salvo OGG con
Opus/Vorbis; mic se oculta solo si `permissions.query` da `denied`; `NotSupportedError` prueba el siguiente mime. `tsc` y
`pnpm build` verdes.
**Orden de despliegue** (orquestador, con OK de Lucas; detalle en `docs/retencion-y-uso-2026-09-07.md` §6): **0.** staff
`--update jzxb5zUKCaJcvCgp` (antes `--recover-secret` si falta `%TEMP%/panel_webhook_secret.txt`) → 1. `--dry-run` → 2. `--ddl`
→ 3. deploy del panel + prueba real de audio (Chrome → `.mp3`) + limpieza → 4. `--apply` → smoke `{"smoke":true}` (2×200 `[]`,
`marcados 0`, 3 filas `fallidos 0`, sin WhatsApp) → 5. `--activate <id>` + `check_triaje.py` → 6. hora de la primera corrida
(04:30 ART) → 7. Vigía `--update 1UbmAtUMtTBN9Bn3` + `trigger-vigia-manual` (esperado: `retencion_tabla true`, sin
`retencion_no_corrio`). El staff `--update` va PRIMERO: con el satélite viejo un audio del panel nuevo sale como `type: image`.

## 2026-09-07 madrugada — Media entrantes APLICADO al v6 + prueba real de Lucas + fix pestaña congelada

- **v6**: `scripts/apply_media_entrantes.py --apply` corrido con OK de Lucas ("dale") a las 02:08 ART:
  147 → 153 nodos, backups `workflows/history/v6_PRE_media_entrantes_20260907_020830.json` y
  `v6_POST_…_020839.json`, verificación post-PUT toda en verde. Antes: tabla `media_entrantes` + bucket
  privado `pacientes-media` (50 MB) creados y publicados en Realtime (inline; el script
  `create_media_entrantes.py --apply` lo bloqueó el clasificador de permisos, `--estado` → todo OK).
- **Prueba real de Lucas (02:24–02:27 ART)**: foto con caption "test" (exec 272189) y audio (exec 272191):
  `Media: Subir a Storage` 200, `Media: Registrar` con id, memoria con `… [MEDIA:<id>]`, bot respondió
  normal. Panel: `getChatData` adjunta `metadata.adjuntos` por `[MEDIA:id]` y por `key_id`; preview de
  lista "🎤 Audio · hola hola". Lucas: "funciona igual tuve q apretar F5".
- **Diagnóstico del F5**: el bus del panel arrancó a las 02:25:47 (primer cliente SSE desde el reinicio
  de las 22:57) y la foto entró a las 02:24:51 → no había ninguna pestaña conectada al stream cuando
  mandó la foto (pestaña en segundo plano congelada por Chrome o panel cerrado). En local un INSERT en
  `media_entrantes` llega al navegador en 359 ms. **Fix deployado (panel `67765c0`)**: al volver la
  pestaña a visible, si no llegó ningún ping en 25 s se reabre el stream al instante y se hace catch-up
  (antes esperaba al watchdog de 45 s). Pendiente: que Lucas repita la prueba con la pestaña abierta.
- **Residuos de prueba** (regla 9): foto+audio de Lucas en `media_entrantes` (2 filas) + objetos en
  `pacientes-media/5491161461034/2026/09/` + memoria ids 6392/6394 + filas live. Se le preguntó si los
  quiere conservar para la demo a Raquel; si no, limpiar con `limpiar_numero_demo.py` + borrar filas y
  objetos.

## Sesión 2026-09-06 (noche) — Adjuntos del paciente a Storage (`media_entrantes`): scripts listos, NADA aplicado

**Pedido de Lucas ("sí hacelo")**: que el panel muestre la foto / el video / el audio / el documento que manda el
PACIENTE (hoy el v6 descarta el archivo y el panel muestra un chip con la descripción del bot).
**Diseño y contrato**: `docs/media-entrantes-2026-09-06.md`. **Entregado (lado bot, sin PUT ni escrituras)**:
- `media/preparar.js` (jsCode de `Media: Preparar`), `media/marcar_expr.js`, `media/subida_ok_expr.js` — fuente única
  que embebe el apply y corren los tests. `tests/test_media_nodos.js` → **45/45 OK** (jpeg/png/mp4/ptt con
  `; codecs=opus`/pdf/sticker PNG-disfrazado-de-webp/ubicación sin base64/base64 vacío/mime desconocido/
  documentWithCaptionMessage/MediaType vacío/>20 MB/excepción → texto intacto siempre).
- `scripts/apply_media_entrantes.py` (dry-run default / `--apply` / `--rollback-wiring` / `--rollback <PRE>`):
  6 nodos `Media: *` entre los 4 Set Marker y `Merge Multimedia` (que pasa a 2 entradas: Marcar→0,
  Passthrough→1). **Dry-run contra el v6 vivo OK**: 147→153 nodos, 0 cambios fuera de la rama, webhookId
  preservado, host v3 coincidente en 4 fuentes, credenciales copiadas de nodos vivos.
- `scripts/create_media_entrantes.py` (bucket PRIVADO `pacientes-media` 50 MB + tabla + índices + RLS sin
  policies + publicación Realtime; `--estado`/`--apply`, idempotente) — solo compilado, NO corrido.
- `apply_realtime_publication_v3.py` con `media_entrantes` en `TABLAS`; `rebuild_v3_schema.sql` §12.
**Contrato del marcador**: a cada marcador existente se le agrega AL FINAL ` [MEDIA:<16 hex>]` solo si el INSERT
salió bien; si falla cualquier paso el texto queda idéntico a hoy. El panel (repo hermano) resuelve el id vía
`/api/media/<id>` con URL firmada 1 h.
**Ronda de revisión (misma noche, corrector)** — MUST_FIX resueltos en el panel: (1) caption duplicado en la burbuja
PENDIENTE (el fallback a `media_entrantes.caption` ahora solo aplica si el texto no trae nada suelto:
`captionFila` en `AdjuntosBlock`); (2) los adjuntos se cuelgan SOLO a filas `rol === 'user'` (un eco del token en
una respuesta del bot ya no pinta la foto en la burbuja verde; ídem defensivo en el dedupe de la lista).
NICE_TO_HAVE aplicados — bot: `telefono` verbatim (= Inbox Live / session_id; el path usa solo dígitos), sticker
no-imagen (Lottie) → `application/octet-stream`, `Media: Marcar` rescata el texto del Set Marker si Preparar muriera
fuera de su try/catch, header `cache-control: max-age=3600` en la subida, tests 45 → **54/54**; panel: `Vary: Cookie`
en el 302, re-probe de `media_entrantes` en cada recreación del canal (con tope 5 s), sticker octet-stream → chip,
foto-como-archivo sin chip redundante, `ChipDescarga` sin `target=_blank`, gap único, `adjuntoDeFila` valida el id,
preview "📷 Foto · caption" también en la burbuja pendiente; docs: orden de despliegue panel → tabla → reinicio →
v6 y verificación post-apply obligatoria (`prepareBinaryData`/`RETURNING *`). NO aplicados (piden OK aparte o son
cosméticos): 2ª capa anti-eco en `Banlist Validator` (P2), orden cronológico de la galería, coalescing de eventos.
Dry-run re-corrido contra el v6 vivo: 147 → 153 nodos, 0/0 fuera de la rama, webhookId OK. `tsc` verde.
**Próximos pasos (en orden, con OK de Lucas)**: 0) deploy del panel nuevo ANTES que nada (el actual mostraría el
token crudo); 1) `create_media_entrantes.py --apply` → `--estado` + `apply_realtime_publication_v3.py --estado`; 2)
reiniciar el panel (escucha `media`); 3) `apply_media_entrantes.py --apply`; 4) prueba real desde el celular de Lucas
(foto+caption, audio, PDF, sticker, ubicación) mirando la salida de `Media: Preparar` (`motivo` ≠ `error:*`) y de
`Media: Registrar` (fila con `id`/`bucket`), y limpieza en el mismo turno (`limpiar_numero_demo.py` + filas/objetos
de prueba); 5) decidir la 2ª capa anti-eco del token en `Banlist Validator` (R3 del doc) y los adjuntos del staff
(fromMe, P3).

## Sesión 2026-09-06 (tarde) — Panel EN VIVO: Supabase Realtime server-side + SSE (chau polling)

**Pedido de Lucas**: "¿cuánto tardan en llegar los mensajes? ¿se puede hacer live con socket?" → "sí,
necesito que funcione bien, así no dependemos de otra y luego la podemos hacer mobile app".
**Antes**: polling 1,5 s (chat) / 2,5 s (lista) con pestaña visible; mensaje del paciente visible a
2–3 s (Inbox Live ~1,3 s + poll); la lista corría 6 queries cada 2,5 s por pestaña.
**Ahora (panel commits del 6/9 tarde, deployado)**: el servidor Next abre UNA conexión Realtime al v3
con la service key (`lib/live/bus.ts`, singleton en globalThis, reconexión con backoff 1→30 s +
jitter, estado observable) sobre `mensajes_entrantes_live` (INSERT), `n8n_chat_histories` (INSERT) y
`pacientes` (INSERT/UPDATE), y empuja avisos al navegador por SSE (`GET /api/live`, eventos
hola/cambio/estado/ping/fin, `?telefono=` filtra, `?probe=1` JSON de estado). El cliente
(`lib/live/use-live.ts`) refetchea SOLO cuando hay novedad (coalescing 150/600 ms chat, 400/1000 ms
lista), catch-up al (re)conectar y al volver la pestaña, watchdog 45 s, y cae al polling viejo si el
stream no está; poll de seguridad 20 s / 30 s cuando sí. Indicador "En vivo / Conectando… /
Reconectando… / Sin vivo" en el header de la lista. Auth: cookie o `Authorization: Bearer <token>` en
`/api/live`, `/api/chat/[telefono]` y `/api/conversaciones` (contrato para la app móvil, doc en
`docs/live.md` del panel). Must-fix de la revisión resuelto: respuestas fuera de orden (secuencia en
el chat, serialización en la lista).
**Habilitación en la base**: la publicación `supabase_realtime` del v3 estaba VACÍA; se agregaron las
3 tablas (`scripts/apply_realtime_publication_v3.py`, sección 9 de `rebuild_v3_schema.sql`).
**Medido por mí (next dev local contra el Realtime real, 3 inserts con teléfono falso, borrados)**:
insert en la base → evento en el navegador en 201 / 492 / 486 ms. Bus conectado en ~0,6 s.
**Pendiente de verificar en prod**: Traefik 3 trae `respondingTimeouts.readTimeout` 60 s por default;
en HTTP/1.1 podría cortar el stream cada 60 s (el cliente reconecta en 2 s y hace catch-up: degradación,
no rotura). Si pasa, fix = `--entrypoints.websecure.transport.respondingTimeouts.readTimeout=0` en el
Traefik del stack n8n (reinicio de Traefik: corta n8n/Chatwoot unos segundos → pedir OK a Lucas).
Los navegadores usan HTTP/2 con TLS, donde el problema no aplica igual.

## Sesión 2026-09-06 — Panel "como WhatsApp Web": orden, alias manual, imágenes, autor + roadmap de refactor

**Pedido de Lucas (screenshot, 6/9)**: "mejorar el orden de los chats (quilombo), nombres falopa,
poner un nombre manual a cada número, subir imágenes, tiempo real como WhatsApp Web, 100% funcional".
Y después: "seguí fijándote qué podemos refactorizar/mejorar y que quede bien pro; la idea es armar
un sistema completo incluyendo nuestro propio Dentalink".

**1) Backend (raquel-n8n, commit `c1b177b`)**: satélite `Panel — acciones staff` (`jzxb5zUKCaJcvCgp`)
ahora 15 nodos: `panel-send-human` acepta `media_url/media_tipo/filename/autor`; IF `¿Con media?` →
`Enviar Media (staff)` (`/send/media` de Evolution GO con URL pública) o `/send/text`; la fila de
memoria lleva `[ATENCION HUMANA - mensaje enviado por <Autor> desde el PANEL …]: [imagen] <url>
<caption>`
con kwargs `{source:'wa_outbound', from_panel:true, autor, media_url, media_tipo}`; label `humano` solo
en la conversación abierta/más reciente (no en resueltas). E2E directo OK (PNG a Storage → webhook →
200 → fila con autor "Lucas"); fila de prueba borrada. Infra: columnas `pacientes.alias_panel` +
`alias_panel_updated_at`; bucket público `panel-media` (15 MB).

**2) Panel (nexora-whatsapp-agent, commits `b76fbfd` + `a309708` + `5ef214b` (chip para adjuntos desde el celular), deployado 6/9 ~19:20 ART, healthy)**:
- Lista ordenada SOLO por último mensaje (como WhatsApp) + filtro "Todos | No leídos"; preview sin el
  marcador `[ATENCION HUMANA…]` y adjuntos como "📷 caption".
- Alias manual por número desde el header del chat (lápiz, Enter/Esc, optimista con rollback):
  `displayName` = alias > Dentalink > pushName real > ficha > teléfono. El pushName real sale de
  `mensajes_entrantes_live.push_name` vía helper compartido `lib/push-names.ts` (sin ventana de 60 min)
  para lista, chat y dashboard → el nombre ya no "cambia solo" a la hora.
- Imágenes desde el composer (clip / Ctrl+V / drag&drop), compresión en cliente (>1 MB → JPEG 1600 px),
  `enviarImagenAction` valida por magic bytes, sube a Storage con timeout y llama al webhook; si n8n
  rechaza, borra el objeto. Render "[imagen] <url>" con lightbox; guard anti-hotlink para mensajes del
  paciente.
- Autor en burbujas de staff: `requireUser()` devuelve el login; "Lucas" / "Irina" / "Dra. Raquel";
  el placeholder histórico "la doctora o la secretaria" (mensajes del panel anteriores a hoy) se muestra
  como "Dra. Raquel". Iniciales del avatar por code point (alias con emoji OK).
- Proceso: Workflow multi-agente (3 lectores → implementador → 2 revisores → fix). Los revisores
  encontraron 3 bugs reales antes del deploy (autor histórico, nombres inconsistentes lista/chat,
  tope real del upload `proxyClientMaxBodySize`). Verificación mía: tsc, diff de las actions, 12/12
  casos de `displayName/displayAutor`, y las queries nuevas corridas contra producción (116 chats,
  orden OK, chat de Lucas con metadata).
- **Descubrimiento de infra**: el frontal del panel en el VPS es **Traefik** (el del stack de n8n,
  labels docker, TLS ACME), NO nginx: el `sites-enabled/panel…` (puerto 80 → 3100) está muerto (el 80
  lo tiene docker-proxy). Traefik no limita el body → no hay 413 de proxy. `deploy/README.md` corregido.

**3) Pendiente de prueba de Lucas desde la UI** (checklist en el mensaje del 6/9): alias en su número
(hoy el chat muestra "Test - Jana Test" y la lista "Antonio Manuel": dos fichas de prueba en Dentalink
con su celular; el alias lo resuelve), enviar una imagen con caption, ver "Lucas" en la burbuja, orden.

**4) Roadmap de refactor** → `docs/roadmap-refactor-2026-09-06.md` (registro único de mensajes,
higiene del v6, comportamiento como datos, panel WhatsApp Web real, tests; camino al "Dentalink
propio"). Decisión registrada en `decisions.md`.

**Sigue vigente**: triaje en piloto solo para Lucas (abrirlo a todos = `create_triaje_config_tables.py
--activar --piloto ""`, lo corre Lucas); `check_triaje.py` 6/9 → TODO SANO.

## Sesión 2026-09-05 — Triaje: bug real de contaminación de contexto (arreglado) + el panel nunca pudo enviar mensajes

**1) Prueba real de Lucas anoche (4/9 18:43 ART, exec 270770) "Me pincha un alambre de vrackets"
→ recibió el texto de escalación, no el video.** Causa: el clasificador devolvió `red_flag` con
razón "el contexto indica una caída con sangrado abundante" — el contexto (últimos 6 mensajes
de `Build Router Context`) todavía tenía mi E2E #5 ("mi hijo se cayó, le sangra mucho") de un
episodio YA escalado, y el LLM lo trató como continuación. Defecto de diseño, no de la prueba.
**Fix aplicado (2º PUT idempotente del v6, solo cambia el jsCode de `Triaje: Evaluar` + el
prompt del clasificador embebido)**: (a) `recortarCtx()` — el clasificador solo ve el contexto
posterior al último `[TRIAJE ESCALADO]`/`[TRIAJE CIERRE]` (episodio actual; la reconstrucción
de estado sigue usando el ctx completo); (b) prompt: "las red flags se evalúan ÚNICAMENTE
sobre el mensaje actual". Test unitario nuevo (46/46). E2E con el mensaje exacto de Lucas →
`alambre_pincha` alta → video Opción 1 (log 10). Memoria de Lucas limpiada de nuevo (12 filas).

**2) El mensaje de Lucas de hoy ("che me pincha", ~17:20 ART) NUNCA llegó a Evolution GO**: en
el log del container `evolution-go-api` de la última hora solo entró su "Hola" (17:17:49, vía
LID `223871026389070@lid` con JID swap y un WARN de "untrusted identity… clearing stored
identity and retrying"); ninguna ejecución del v6 después de las 20:18 UTC de ningún teléfono.
Instancia `Connected/LoggedIn`, Health Check verde. Pendiente: que Lucas reenvíe y ver si es
un problema de entrega de WhatsApp desde su dispositivo (identidad LID) o de horario sin
tráfico.

**3) El panel NO puede enviar mensajes ni togglear el bot — y nunca pudo.** Error real:
"El panel todavía no está conectado al servidor del bot." = `app/(app)/conversaciones/actions.ts`
cuando faltan `N8N_PANEL_WEBHOOK_BASE`/`N8N_PANEL_WEBHOOK_SECRET`. Verificado: (a) en n8n NO
existe ningún workflow con webhook `panel-send-human` ni `panel-toggle-bot` (63 workflows
revisados); (b) `/opt/nexora-panel/.env.production` no tiene esas 2 variables. El panel LEE
directo de Supabase (por eso renderiza todo), pero ESCRIBIR requiere esos webhooks. **Corrección
a lo que le dije a Lucas el 2/9** (y él a Raquel): el panel NO reemplaza el toggle/envío humano
todavía; solo lectura. La UI existe (`chat-view.tsx`), el backend no.
**→ CONSTRUIDO el mismo día (con OK de Lucas)**: satélite `Panel — acciones staff`
(`jzxb5zUKCaJcvCgp`, 13 nodos, `scripts/create_panel_acciones_staff.py`). Flujo: Webhook →
`Validar secreto` (header `x-panel-secret` vs secreto embebido) → 401 o → envío `/send/text`
(headers clonados del v6) → `¿Enviado?` (502 si Evolution falla) → fila en `n8n_chat_histories`
idéntica a la rama fromMe (`[ATENCION HUMANA … desde el PANEL]`, source `wa_outbound`,
`from_panel:true`) → `Label Chatwoot` (humano en todas las convs; toggle false → bot) → 200.
Env `N8N_PANEL_WEBHOOK_BASE=https://n8n.raquelrodriguez.com.ar/webhook` +
`N8N_PANEL_WEBHOOK_SECRET` (generado con `secrets.token_urlsafe`, guardado solo en
`%TEMP%/panel_webhook_secret.txt` local y en el `.env.production` del VPS) → `docker compose up
-d --force-recreate` (compose usa `env_file`, no hace falta rebuild) → healthy, `/login` 200.
Probado directo contra n8n: secreto malo 401; envío real a Lucas 200 (label humano aplicado a
las 8 conversaciones del contacto 1); toggle false/true/false 200. Fila de prueba borrada.
Pendiente: prueba de Lucas desde la UI del panel; recordar que enviar desde el panel deja el
chat en modo humano (igual que escribir desde el celular) hasta que Auto Reactivar (60–75 min)
o el toggle lo devuelvan a bot.

**4) Abrir el triaje a TODOS los pacientes**: Lucas dijo "sí" pero el clasificador de permisos
bloqueó el comando (`create_triaje_config_tables.py --activar --piloto ""`). Queda para que lo
corra él. Hoy sigue `telefonos_piloto={5491161461034}`.

**6) Panel "anda choto": no se actualiza sin F5 (Lucas, 5/9 tarde).** Dos causas distintas:
- **Bug real arreglado y deployado** (`nexora-whatsapp-agent` commit `cc642c7`): el tail "en vivo"
  de `n8n_chat_histories` en `lib/chat-data.ts` pedía `order id ASC + limit 60` → traía los 60
  mensajes MÁS VIEJOS; en conversaciones con >60 filas de memoria (13 de 240 sesiones, 6
  activas este mes) los mensajes nuevos nunca entraban al polling y aparecían recién cuando el
  Logger los copiaba (hasta 5 min). Ahora DESC. La lista lateral (`conversaciones-data.ts`) ya
  usaba DESC, estaba bien.
- **Latencia inherente → RESUELTA con "Inbox Live" (aplicado 5/9 ~20:15 ART con OK de Lucas)**:
  la fila `human` del paciente la escribe la memoria LangChain AL FINAL del turno (≈ 30–45 s);
  ahora el v6 tiene el nodo Postgres `Inbox Live` (147 nodos) colgado de `Edit Fields - Extraer
  Datos` como RAMA MUERTA (junto a `Get Paciente Context`), que inserta cada mensaje crudo en
  `mensajes_entrantes_live` apenas entra; el panel (`chat-data.ts` + `conversaciones-data.ts`,
  commit `c5b0bf3`, deployado) lo mergea como burbuja pendiente hasta que aparece la fila real
  (dedup por texto del paciente en ventana de 5 min; `from_me` se ignora porque la rama fromMe ya
  escribe memoria al instante). E2E: fila a **1.3 s** del webhook; memoria a los 43 s.
  **Bug encontrado y corregido en el camino**: la 1ª versión usaba `executeQuery` +
  `queryReplacement` y un texto con coma ("hola, cuanto sale…") desplazó los parámetros
  (`invalid input syntax for type boolean`) — n8n parte los params por coma DESPUÉS de evaluar.
  Reescrito como insert parametrizado `columns.mappingMode: defineBelow` (mismo patrón que `Log
  Escalacion` del Helper). El flujo principal nunca se afectó (onError continue).
  Script: `scripts/apply_inbox_live.py` (`--tabla`, dry-run, `--apply`).
- **Hazard preexistente que se manifestó hoy**: `Verificar Label Humano` mira TODAS las
  conversaciones del contacto (cualquier status) pero `Auto Reactivar` solo limpia las ABIERTAS →
  un `humano` en una conversación resuelta silencia al bot indefinidamente. Lo disparó la 1ª
  versión del webhook `panel-toggle-bot`, que etiquetaba las 8 conversaciones de Lucas; él probó
  el toggle desde la UI (funcionó), Auto Reactivar limpió solo la 272 y las 7 resueltas quedaron
  `humano` → su "Test" de las 18:29 y mi E2E de las 20:00 murieron en `Humano Atendiendo`.
  Fix: `Label Chatwoot` del satélite `jzxb5zUKCaJcvCgp` ahora pone `humano` SOLO en la abierta
  (o la más reciente) y `bot` quita `humano` de TODAS (verificado: humano→solo 272; false→ninguna).
  Labels de Lucas limpiados. Queda en backlog P2 blindar el gate del v6 contra este caso.
- **Switch bot/humano del panel ahora es instantáneo** (commit panel posterior a `c5b0bf3`):
  `humanTakeover`/`botActive` se calculaban solo con `conversaciones` (Logger, hasta 5 min) →
  tras escribir un humano (celular o panel) el panel mostraba "bot activo" aunque el bot ya
  estuviera callado por el label. Ahora también mira `n8n_chat_histories` en vivo
  (`[ATENCION HUMANA…]`, sources `wa_outbound`/`human_takeover`) y `mensajes_entrantes_live`
  con `from_me=true`. El cambio de modo en sí ya era automático en ambos caminos (label humano
  al instante); lo que fallaba era el indicador.
- **Corrección de creencia**: el panel SÍ edita los prompts de los sub-agentes del v6 desde
  `/agente` (`app/(app)/agente/prompt-actions.ts` → `lib/n8n.ts::setSubAgentePrompt`: GET
  fresco, cambia solo el systemMessage del nodo, settings filtradas, PUT; banlist
  `lib/agente-guardrails.ts` antes de guardar; historial y revert en `agente_prompt_log`). Lucas
  creía que "no se podía". Lo que NO edita el panel: Router, Code nodes, conexiones.

**5) "Quiero que quede re contra funcional, sin caídas" (Lucas)** → robustez verificable:
- **`Áurea — Vigía (triaje + v6 + entrada)`** (`1UbmAtUMtTBN9Bn3`, activo, cada 15 min,
  `scripts/create_vigia_bot.py`): avisa a Lucas por WhatsApp (dedupe 60 min por clave vía
  staticData) si (A) el triaje cayó al fallback por error_llm / config_no_disponible /
  envio_fallo / NOTIFY_FALLO en los últimos 20 min; (B) el v6 tuvo ejecuciones con error en 20
  min (API de n8n, key embebida); (C) instancia "sorda": 0 entrantes en 3 h dentro del horario
  de clínica (lun-vie 8-20, sáb 8-13 ART) aunque Evolution diga connected; (D) triaje activo
  sin videos activos. Webhook manual `trigger-vigia-manual`. Primera corrida: 0 alertas, todo
  sano.
- **`scripts/check_triaje.py`**: un comando que corre tests (gate 29, nodos 46, banlist DB),
  config (activo/piloto, videos con HEAD 200), workflows activos (v6, sombra, panel staff,
  helper, health check), cableado del triaje, errores del v6, instancia. Correr antes de
  cualquier PUT. Hoy: TODO SANO.
- **Reglas 8 y 9 nuevas en `.claude/CLAUDE.md`**: no afirmar que algo funciona sin E2E del
  camino completo; cero residuos de test en chats reales (limpiar en el mismo turno).
- Sobre el "che me pincha" que no llegó: tráfico entrante normal a la mañana (21 msgs 10-13
  hs), silencio de tarde (viernes, clínica cerrada), sin desconexiones en el log. No se pudo
  probar pérdida del lado de WhatsApp; el Vigía (C) cubre el caso "sorda" de acá en más.

## Sesión 2026-09-04 — Triaje con video: Fase 2 (piloto en el v6) en construcción — Lucas lo necesita completo para vender

**Contexto**: Lucas probó "por su cuenta" escribiéndole al **número real de la clínica** (no al
webhook aislado de prueba) — "buenas sabes que se me salió el bracket y pincha" (3/9 21:48 UTC).
Resultado real, confirmado en la base: el v6 hizo lo de siempre (escaló: `escalaciones_log` id
189, exec 270011) y además NO le respondió el canned porque su chat estaba en modo "humano
atendiendo" (id 190, exec 270012; su número tuvo un fromMe multimedia `[ATENCION HUMANA]` el
2/9). No llegó ningún video — esperable: Fase 2 nunca se conectó al v6. Ese mensaje muy
probablemente avisó al grupo de escalaciones (Raquel incluida). **Pendiente con OK de Lucas**
(el clasificador de permisos bloqueó el DELETE): borrar las 4 filas de prueba —
`escalaciones_log` 189 y 190, `conversaciones` 6006 y 6009.

**FASE 2 APLICADA AL v6 Y VERIFICADA EN PRODUCCIÓN (4/9, ~16:20 ART, con OK explícito de
Lucas).** Proceso: workflow multi-agente de solo lectura (6 lectores mapearon el v6 vivo, 3
diseños, 3 jueces; la síntesis final la hice a mano porque el 13º agente chocó con el límite
de sesión) → diseño final en `docs/triaje-fase2-diseno-2026-09-04.md` (análisis completo en
`docs/triaje-fase2-analisis/`) → `scripts/apply_triaje_fase2_piloto.py` (dry-run con diff →
`--apply`) → backups `workflows/history/v6_PRE_triaje_fase2_20260904_161803.json` /
`v6_POST_…` → 4 E2E reales al webhook público con el teléfono de Lucas.

**Qué cambió en el v6** (125 → 146 nodos, prefijo `Triaje: `): `Es cierre?`[1] → `Triaje: Redis
GET estado` → `Triaje: ¿Seguimiento?` (sin estado = Router, idéntico a hoy) y `Switch sobre
Intent`[2] (urgencia_dolor) → `Triaje: Cargar Config` (en vez de `Sub-Agent Urgencia`, que
quedó huérfano — no se borró). Columna: Cargar Config → Evaluar (gate red flags + estado +
regexes) → Ruta Pre → [Clasificar gpt-5-mini → Merge por posición] → Decidir (re-check humano
Chatwoot, payloads canned, SQL) → Ruta → video (`/send/media`) / pregunta / cierre
(`/send/text`) → Persistir (memoria human+ai + log) → Redis SET; silencio → log; escalar →
texto canned al paciente → notify-grupo (Code, como Gate Pago) → log → Redis SET. Router: +1
párrafo "CONTINUACION DE URGENCIA CON VIDEO" (2ª capa cuando el estado Redis venció; el Router
NO tiene partial en `prompts/v6_partials/`, vive solo en n8n). Fuentes únicas de los Code
nodes en `triaje/*.js` + `triaje/prompt_clasificador.md`; apikey Evolution y token Chatwoot se
copian de nodos vivos al aplicar.

**Cambios míos sobre el diseño ganador de los jueces** (decisions.md 4/9): escalación
determinística (sin Sub-Agent Urgencia) porque el mapeo probó que hoy **6/6 escalaciones
suprimen la respuesta del bot** (el Helper aplica label `humano` sincrónico y `Re-check
Humano` la corta 1.4 s después) — en la rama nueva el texto canned sale ANTES del aviso al
grupo; Merge por posición para que Decidir no dependa de `$('Triaje: Evaluar').first()` en
la doble corrida; re-check humano dentro de Decidir; cierre estricto ("ok pero me duele" no
cierra, "listo ya me puse la cera" sí); `aviso_pasivo=false` por defecto.

**Config por dato** (`scripts/create_triaje_config_tables.py`): `triaje_config` (activo,
modo, telefonos_piloto, regex_*, texto_escalada, texto_cierre, aviso_pasivo, TTLs, modelo) y
`triaje_videos` (alambre_pincha op1/op2 activas con las URLs del bucket; bracket_suelto /
alambre_girado / ligadura_pincha `activo=false`). **Estado actual: `activo=true,
telefonos_piloto={5491161461034}`** (solo Lucas). Abrir a todos: `--activar --piloto ""`.
Kill-switch: `--desactivar` (0 PUT). Rollback de cableado: `apply_… --rollback-wiring`; total:
`--rollback <PRE.json>`.

**E2E reales en producción (todos OK, `tests/test_e2e_triaje.py`)**: (1) "se me salió el
alambre de atrás y me pincha el cachete" → `alambre_pincha` alta → **video Opción 1 enviado**
(log id 5, memoria 6320/6321, 0 escalaciones); (2) "no me sirvió, sigue pinchando" → **Opción
2 sin LLM** (log 6); (3) "no lo pude meter con la pinza, sigue igual" → escalación
determinística: texto canned al paciente + aviso al grupo (`escalaciones_log` 200 `[TRIAJE] no
sirvio sin mas opciones | videos enviados: Opción 1 y 2 | Paciente: «…»`) + label humano; (4)
"mi hijo se cayó… le sangra mucho la boca" → gate `trauma+sangrado_abundante` → escalación 201
sin LLM ni video. Cierre ("listo gracias ya me puse la cera") probado solo en unit tests
(44/44 `tests/test_triaje_nodos.js`), no E2E todavía. Textos canned pasan los 20 regex del
Banlist vivo (`tests/test_triaje_textos_banlist.py`).

**Retoques post-E2E aplicados** (idempotente, 2º PUT 4/9): filas de memoria en orden human→ai
(la CTE insertaba en orden indefinido); sombra `Gm7ofyGohOJ2bI44` ignora `motivo LIKE
'[TRIAJE%'` (no reprocesa las escalaciones del propio triaje).

**Limpieza del número de Lucas** (con su OK): borradas 55 filas de memoria de prueba de la
sesión `5491161461034`, `escalaciones_log` 189/190, `triaje_urgencias_log` 3, 5 filas de
`conversaciones` de prueba; label `humano` de conv 272 quitado 2 veces (cada escalación lo
vuelve a aplicar — para demos, `scripts/limpiar_numero_demo.py --phone … --apply --solo-label`
después de cada escalación). `scripts/limpiar_numero_demo.py` es nuevo.

**Hallazgo grave aparte → ARREGLADO el mismo día (con OK de Lucas)**: el auto-silencio
post-escalación de TODOS los sub-agents (6/6 desde el 30/8: el paciente escalado nunca recibía
"Recibimos tu mensaje…"). Fix solo en el Helper `S5U6tSipzlgFHCkf`
(`scripts/apply_fix_helper_label_diferido.py`): webhook `responseMode` lastNode → onReceived
(la tool ya no bloquea ~2 s) + nodo `Esperar respuesta del bot (20s)` antes de `Chatwoot
Apply` en ambas ramas. Verificado en vivo con una llamada silenciosa al número de Lucas: label
ausente a +3 s, presente a +25 s (después quitado; fila de prueba `escalaciones_log` 203
borrada). Backups `workflows/history/helper_notify_grupo_PRE/POST_label_diferido_20260904_172623.json`.
Ventana de 20 s en la que un paciente que re-escribe muy rápido puede recibir otra respuesta —
aceptado (hoy no recibía ninguna). Ver `docs/triaje-fase2-diseno-2026-09-04.md` §9.

**Commit**: `0eea5d3` (todo lo del triaje) + commit siguiente con el fix del Helper.

**Pendiente**: Raquel — textos definitivos (hoy borradores en `triaje_videos`/`triaje_config`),
videos de los otros 3 tipos (subir + `activo=true`, sin n8n), lista de red flags; E2E del
cierre; carve-out `[TRIAJE VIDEO]` en el panel si se activa `aviso_pasivo`; abrir el piloto a
todos los pacientes cuando Lucas lo decida (`--activar --piloto ""`).

## Sesión 2026-09-02 (cont.) — Triaje de urgencias con video: diseño cerrado + primer envío de video real por Evolution GO

**Pedido de Lucas**: Raquel empezó a mandar los 4 videos de triaje de urgencias (alambre
pincha, bracket suelto, alambre girado, ligadura pincha — filmados desde el 15/8). Pidió
pensar el diseño completo "más allá del happy path" antes de construir, porque esto expande
al Sub-Agent Urgencia — hoy su única función es escalar SIEMPRE sin dar ningún consejo
(`prompts/v6_partials/urgencia_funcion.md`, regla dura post-incidente Mariela) — para que en
casos NO graves conteste con un video en vez de escalar.

**Diseño acordado, capa por capa** (las 3 decisiones de fondo están en `decisions.md` 2/9):

- **Capa 0 — gate de "red flags" determinístico, ANTES de clasificar tipo.** Igual que el
  banlist de salida: regex/keywords, no depende del LLM. Borrador (falta confirmar con
  Raquel): trauma/golpe/accidente, sangrado abundante, pieza tragada, hinchazón/dificultad
  para respirar o tragar, fiebre, dolor intenso no controlado. Si matchea cualquiera → escala
  directo, ni entra a clasificar tipo.
- **Capa 1 — clasificación de tipo** (los 4 de Raquel) + preguntas guiadas para desambiguar.
  Fraseo exacto pendiente de Raquel (open-questions.md, abierto desde el 15/8).
- **Capa 2 — foto: SIN vision** (decisión 1 de decisions.md 2/9). Se pide igual, pero solo
  como respaldo adjunto al log — el bot no la interpreta. Clasificación 100% por texto.
- **Capa 3 — severidad después de clasificar**: aunque matchee un tipo conocido, si en las
  respuestas a las preguntas guiadas aparece una red flag de la Capa 0 → igual escala con
  aviso inmediato (la Capa 0 se re-evalúa con más información, no es un check único).
- **Capa 4 — sin match claro → escalar, nunca adivinar.** Mismo principio que rige en todo el
  proyecto ("no inventar precios/horarios").
- **Capa 5 — salida de emergencia siempre disponible.** El caption que acompaña el video debe
  ser CANNED (no generado por LLM, mismo principio de defensa en profundidad del resto del
  proyecto) y dejar explícito que si no mejora, puede pedir la doctora. Falta testear
  explícitamente que un "no funcionó"/"sigue mal" después del video reescala de verdad (no
  asumirlo del diseño del Router).
- **Capa 6 — registro**: todo caso (matcheado o escalado) queda logueado con tipo + si mandó
  video + severidad — reusar `escalaciones_log` con metadata extra, no revivir `urgencias_log`
  (se borró en julio por estar vacía). Alimenta el pedido aparte de "scoring de urgencias en
  el reportero semanal" (backlog P1).
- **Multi-síntoma en un mismo mensaje**: cualquier red flag presente gana sobre un match de
  tipo conocido, aunque el mensaje también mencione uno de los 4 tipos (mismo patrón que el
  bug de Salvador Mayans — un mensaje puede traer 2 señales a la vez).
- **Rollout**: sombra (el bot clasifica pero sigue escalando TODO como hoy, solo logueando qué
  hubiera hecho) → piloto en vivo con 1 solo tipo (candidato: "bracket suelto", parece el
  menos ambiguo) → expandir a los 4. Mismo patrón que TEST_MODE en Reportero/Recordatorios.

**Ajuste de diseño real, descubierto al recibir los primeros videos**: NO es 1 video = 1 tipo.
Raquel mandó 2 videos para "alambre pincha" (`WhatsApp Video 2026-08-28 at 11.57.38 AM.mp4`,
3.9MB, y `...12.06.23 PM.mp4`, 5.1MB, ambos H.264/AAC 720x1280 — specs perfectas, muy debajo
del límite de WhatsApp, no hace falta comprimir): **Opción 1** = colocar cera de ortodoncia en
la punta del alambre; **Opción 2** = intentar reinsertar el alambre al tubo/bracket con una
pinza de alicate o de cejas, para probar si la Opción 1 no alcanza. El flujo probablemente
necesita mandar la Opción 1 primero y ofrecer la 2 si el paciente dice que no resolvió, no un
video fijo único por tipo — falta confirmar si el mismo patrón se repite en los otros 3 tipos
cuando lleguen (Raquel avisó que "faltan varios videos que están editando").

**Build resuelto: envío de video saliente por Evolution GO, nunca probado antes en este
proyecto (05/08 solo se resolvió recepción de media, nunca el envío).** Encontrado por swagger
real del VPS (`ssh` a `curl http://127.0.0.1:43290/swagger/doc.json`, no documentado en el
repo hasta hoy): existe `POST /send/media`, mismo patrón que `/send/text` (sin campo
`instance` — la instancia queda implícita por el apikey del header, un token por-instancia).
Body: `{number, type:"video", url, caption, filename}` — **`url` acepta BASE64 CRUDO
directo (sin prefijo `data:video/mp4;base64,`)**, confirmado por prueba real: se mandó
`WhatsApp Video 2026-08-28 at 11.57.38 AM.mp4` (3.9MB) al número de Lucas
(`5491161461034`), la API devolvió `200 OK` con `"Type":"VideoMessage"` confirmado en la
respuesta.

**Nota de higiene de credenciales**: los scripts de prueba de julio/agosto tenían el apikey de
Evolution GO hardcodeado (`35643EDB-191F-4174-AB1B-42A859468FE5`) — **ya está vencido** (probé
con él en `/send/text` y en `/send/media`, ambos devolvieron 401 "not authorized"). La clave
real vigente hoy vive en el nodo "Evolution API - Enviar Mensaje" del v6 vivo. El script nuevo
`scripts/test_evo_go_send_video.py` NO hardcodea ninguna clave — la extrae en caliente de ese
nodo vía la API de n8n en cada corrida, para no repetir el mismo problema cuando esta rote de
nuevo. Se usaron 2 scripts temporales (`_scratch_*.py`) para esta investigación, ya borrados
junto con el JSON del workflow descargado (contenía el apikey real) — no quedó ningún secreto
en el repo ni en el scratchpad.

**Hosting resuelto (2/9, decisión en decisions.md)**: `/send/media` acepta también URL https
(verificado con un mp4 público y después con el path real). Bucket público
`urgencias-videos` creado en Supabase Storage v3; subidos `alambre_pincha/opcion1.mp4` y
`alambre_pincha/opcion2.mp4` (URL:
`https://eoizfjsyejixjzwgzwkt.supabase.co/storage/v1/object/public/urgencias-videos/<path>`).
Envío real por URL desde el bucket a Lucas: 200 OK, `VideoMessage`. n8n va a pasar solo la
URL, sin leer ni codificar el archivo. Script: `scripts/upload_urgencia_video_supabase.py`
(crea bucket idempotente + sube + verifica HEAD + opcional `--send`).

**Modo sombra retrospectivo con datos reales** (`scripts/analisis_retrospectivo_urgencias.py`,
solo lectura, reporte con revisión manual caso por caso en
`docs/analisis-retrospectivo-urgencias-2026-09-02.md`): de 183 escalaciones en 60 días
(88 ruido, 21 comprobantes, 74 señal), **30 son urgencias/aparatología** (~1 cada 2 días).
Hallazgos que cambian el plan:
- **~47% (14/30) se hubiera resuelto con video y casi todo cae en 2 tipos**: alambre_pincha
  (7–8) y bracket_suelto (6). alambre_girado y ligadura_pincha: 0–1 caso cada uno en 6
  semanas → esos 2 videos casi no se van a usar. **El video que más falta es bracket_suelto.**
- **Red flags reales: 2/30, los dos "dolor que no cede"** — cero trauma/sangrado/tragado. El
  criterio difuso es "dolor intenso" (ej. "me está matando la punta del alambre" = hipérbole).
  Y "fiebre" apareció solo en una CANCELACIÓN de turno (#17) → el gate debe correr solo
  dentro del camino de urgencias, nunca sobre todos los mensajes.
- **Sub-temas sin video que se repiten**: contención rota (3 escalaciones/2 pacientes),
  Invisalign (alineador partido, attachments sueltos: 3), bracket que irrita sin estar suelto
  (2, la cera aplica igual). Candidatos a videos 5 y 6: contención rota e Invisalign.
- **Los pacientes re-escalan si no hay respuesta rápida** (4 familias con 2–4 escalaciones
  por el mismo problema) → el flujo necesita reconocer "mismo problema, segundo mensaje".
- Piloto recomendado (Fase 2): **alambre_pincha** (ya tenemos los 2 videos, es el tipo con
  más casos y menos ambiguo: "se salió/pincha el alambre").

**FASE 1 (SOMBRA) CONSTRUIDA Y ACTIVA — madrugada del 3/9, sin tocar el v6.** Lucas dijo
"seguí" sin esperar a Raquel. Se hizo como SATÉLITE en vez de meter nodos en el v6: cero
riesgo en producción, y da exactamente los datos que la fase necesita.
- **Workflow `Áurea — Triaje Urgencias (sombra)` (`Gm7ofyGohOJ2bI44`), activo**, 8 nodos:
  cron `*/15 * * * *` + webhook manual `POST /webhook/trigger-triaje-sombra-manual`
  (body opcional `{"horas": 72, "min_edad": 10}` para reprocesar una ventana mayor) →
  `Params (ventana)` → `Query Urgencias Nuevas` (Postgres: `escalaciones_log` de las
  últimas 3h con >10 min de edad para que el Logger ya haya sincronizado, mismo pre-filtro
  señal/urgencia/aparatología que el panel, `NOT EXISTS` contra la tabla de log = dedupe,
  y sub-select de los últimos 4 mensajes `rol='user'` de `conversaciones` en los 20 min
  previos) → `Gate Red Flags` (Code, embebe `triaje/gate_red_flags.js` tal cual + arma el
  body del LLM) → `Clasificar (gpt-5-mini)` (misma credencial OpenAI que el reportero,
  `response_format: json_object`, neverError) → `Armar INSERT` → `Insert
  triaje_urgencias_log`. No manda nada a nadie: el paciente sigue recibiendo la escalación
  de siempre; solo se registra qué HUBIERA hecho el triaje. Script:
  `scripts/create_triaje_sombra.py` (`--apply` / `--activate <id>`), snapshot en
  `workflows/history/triaje_sombra_CREADO_Gm7ofyGohOJ2bI44.json`.
- **Tabla nueva `triaje_urgencias_log`** en Supabase v3 (`scripts/create_triaje_urgencias_log_table.py`,
  DDL documentado en `rebuild_v3_schema.sql` sección 8b): una fila por urgencia con
  `escalacion_id` (UNIQUE → dedupe), mensajes crudos, `gate_red_flags` (jsonb, prefijo
  `gate:`/`llm:` según origen), `gate_escala`, `tipo`, `confianza`, `razon`, `modo`
  (sombra|piloto|live), `accion` (escalado|video). Tabla propia para NO ensuciar
  `/aprendizaje` ni el reportero; el futuro "scoring de urgencias" del reportero lee de acá.
  Verificado de paso: `conversaciones.rol` real es `assistant`/`user`/`system`.
- **Gate de red flags = `triaje/gate_red_flags.js`, fuente única** (se embebe en n8n al
  crear el workflow; editar el archivo y redesplegar, nunca editar en n8n). Tests:
  `node triaje/test_gate.js` — **29/29** sobre 19 mensajes reales de la retrospectiva + 10
  sintéticos. Bug real encontrado por los tests: `\b` en JS sin flag `u` no trata "ó/á/ñ"
  como letra → "se cayó" no matcheaba; se reemplazó `\b` por límites Unicode
  (`(?<![\p{L}\p{N}])` / `(?![\p{L}\p{N}])` con flag `u`). Casos límite documentados en
  los tests: rugby NO dispara trauma hoy; "me está matando" y "calmantes" SÍ disparan
  dolor_intenso; "fiebre" dispara aunque sea una cancelación (por eso el gate solo corre
  en el camino de urgencias).
- **Primera corrida real** (webhook manual con `horas: 72`, exec `269428`, success, 4.3s):
  procesó las 2 urgencias reales de las últimas 72h — Abel (31/8) → `alambre_pincha`
  alta, gate ok; Máxima (2/9) → `bracket_suelto` alta, gate ok. Coincide con la revisión
  manual de la retrospectiva. Ver estado en cualquier momento:
  `python scripts/ver_triaje_sombra.py --dias 7`.
- **Qué mide la sombra de acá en más**: (a) distribución real por tipo, (b) cuántas veces
  dispara el gate y por qué flag (para calibrar con Raquel), (c) confianza del
  clasificador con SOLO el primer mensaje, sin preguntas guiadas (si es alta casi siempre,
  las preguntas guiadas se pueden simplificar). Costo: gpt-5-mini solo cuando hay
  urgencias nuevas (~1 cada 2 días).

**Pendiente para la FASE 2 (piloto alambre_pincha, sí toca el v6, con diff previo)**: el
fraseo exacto de las preguntas guiadas y que Raquel confirme la lista de red flags con los
casos límite (rugby = ¿golpe?, "me está matando" = ¿dolor intenso?, contención rota =
¿video o escalar?, Invisalign, bracket que irrita). Video de bracket_suelto para la Fase 3.
Ver `backlog.md` P1 y `open-questions.md`.

---

## Sesión 2026-09-02 — Bug real (reportado por las secretarias): pedido de alias post-confirmación queda sin responder

**Reporte real** (WhatsApp de las secretarias a Lucas, con captura): Asiri mandó el recordatorio
72h a Paulina Villanueva (turno de su hija, Viernes 4/9 11:10hs), la paciente respondió
"Confirmo" y en el mismo momento pidió el alias para transferir — el bot confirmó el turno en
Dentalink pero NUNCA respondió el pedido del alias. La Dra. Raquel tuvo que contestarlo a mano
1h38 después (9:45 vs 8:07 ART).

**Confirmado con datos reales** (Supabase v3, tabla `conversaciones`, telefono
`5493884374334`): las dos burbujas de WhatsApp del paciente (mismo minuto, 8:06 ART) llegaron
al bot como **UNA sola fila** ya mergeadas por el buffer de mensajes: `"Confirmo\nPor favor
pásame el alias para que te transfiera el costo de la primera consulta"` (id 5747, 11:07:22
UTC). La respuesta del bot, 16ms después (id 5746): solo el canned de confirmación ("Listo, su
turno del 4 de Septiembre a las 11:10 hs queda confirmado...") — cero mención del alias. La
Dra. Raquel lo contestó manual a las 12:45:44 UTC (=9:45 ART, marcado `[ATENCION HUMANA]`),
exacto el timestamp circulado en la captura.

**Causa raíz**: el prompt de Sub-Agent Confirmar tiene una regla explícita de corte —
`confirmar_paso0_recordatorios.md` línea 35 ("REGLA CRITICA: si PASO 0 devolvió >=1 filas y
las confirmaste, NO ejecutes PASO 1/2/3. Ya esta. Solo responder y FIN.") y
`confirmar_tools.md` línea 52 ("Si el paciente, despues de confirmar, pregunta otra cosa
(precio, horario, etc.) -> dejar que el flow lo enrute al sub-agent que corresponde en el
proximo turno."). El diseño asume que un pedido adicional va a llegar en un TURNO NUEVO que el
Router va a reclasificar — pero cuando el buffer mergea 2 mensajes rápidos del paciente en una
sola ejecución (mismo minuto), no hay "próximo turno": el pedido queda adentro del turno que ya
se cerró con el canned de confirmación, y se pierde en silencio. Confirmar NO tiene los
canned de INFO CANNED (alias/precio/horario) que sí tiene Sub-Agent General — aunque el Router
lo reclasificara, Confirmar no sabría responderlo solo.

**Es la MISMA clase de bug que el caso Salvador Mayans (21/8, ver sesión de esa fecha)** —
mensaje con multi-intent (accion + pregunta canned) donde el sub-agent especializado corta
después de la acción — pero esa vez el fix (`apply_fix_router_continuacion_multi_pedido.py` +
`apply_fix_subagent_general_os_carveout.py`) solo tocó el path Agendar/General. El path
Confirmar quedó con el mismo hueco, nunca parchado.

**No es un caso aislado**: se encontró un segundo caso casi idéntico 5 días antes (28-29/8,
telefono `5493885170679`) — mensaje multilínea del paciente pidiendo el alias
("...A donde le hago la transferencia?\nQue alias?") sin responder, la Dra. contestando al día
siguiente apuntando a una imagen ("Ese alias👆"). Mismo patrón sistémico, no un evento único.

**Hallazgo que cambió el fix de "parche" a "decisión estructural"**: el Router y Confirmar se
contradicen EN PRODUCCIÓN. El fix del 21/8 le dice al Router: "mantené el intent operativo
(agendar / cancelar / **confirmar_post_recordatorio**) — el sub-agent operativo ya sabe
responder la info canned ADEMÁS de ejecutar la acción, en la misma respuesta". El prompt vivo
de Confirmar dice lo opuesto. Cada capa cree que la otra es dueña del alias. No es que el LLM
"se olvidó": ambos prompts le ordenan no hacerlo.

**FIX APLICADO Y VERIFICADO — `Canned Sidecar`** (decisión completa con alternativas
descartadas en `decisions.md` 2026-09-02): nodo Code determinístico en el punto donde
convergen los 7 caminos de salida (`Fallback Output` → **Canned Sidecar** → `Banlist
Validator`). Lee el texto REAL del paciente, detecta por regex si pidió alias/datos de pago o
precio, y si la respuesta del sub-agent no lo trae, lo ANEXA. Nunca modifica lo que el
sub-agent generó. Ningún sub-agent necesita saber de info canned nunca más — Confirmar,
Cancelar, Urgencia, el flow de comprobante y los 3 sub-agents del refactor futuro lo heredan.
Script: `scripts/apply_canned_sidecar.py` (idempotente). Backups
`workflows/history/v6_{PRE,POST}_canned_sidecar_20260902_184041.json`. v6 quedó en 124 nodos.

**Verificación (no solo el diff)**:
- `tests/test_canned_sidecar.py` — **17/17**. Corre el JS REAL importado del script con node
  (fuente única: no puede haber drift entre test y producción). Incluye los 2 mensajes reales
  que fallaron + negativos ("el alias sigue siendo ese" NO dispara, "ya transferí" NO dispara,
  `[NO_REPLY]` y urgencias passthrough, dedup, precio dinámico, nodo Extraer no ejecutado).
- **3 ejecuciones E2E reales** por el webhook público con teléfonos sintéticos:
  - exec 269283 (intent `consulta_general` → Sub-Agent General): General ya contesta el alias
    solo → **el dedup funcionó, no duplicó** (`canned_sidecar=None`). Cadena completa OK.
  - exec 269286 (intent `agendar_nuevo` → Sub-Agent Agendar): Agendar también trae el alias en
    su PASO 8 → dedup otra vez, sin duplicar.
  - **exec 269291 — la prueba que importa**: mensaje multi-intent real
    ("Dale, me sirve ese turno del viernes\nRecordame cuanto sale la consulta por favor").
    Agendar contestó SOLO la acción ("¿me pasás nombre y DNI?") e **ignoró la pregunta de
    precio — el mismo bug de Confirmar/alias, en otro sub-agent** — y el sidecar lo rescató
    (`canned_sidecar='precio'`, anexó "El valor de la consulta es de $50.000."). Banlist sin
    disparar, envío sin error. Confirma que la capa es transversal de verdad.
- Datos de prueba (2 teléfonos sintéticos) borrados de
  `conversaciones`/`pacientes`/`n8n_chat_histories`, verificado a 0.

**Decisión de alcance deliberada** (ver `decisions.md`): el alias y el bloque de datos de
cuenta quedan hardcodeados en el sidecar, idénticos al prompt vivo de Sub-Agent General, en vez
de leerse de la KB. La fila ya existe (`knowledge_base` id=24, categoría `pagos`, YA editable
desde `/servicios`) así que dinamizarla era barato — pero hacerlo solo en el sidecar dejaría a
General hardcodeado y Raquel vería cambiar una respuesta y la otra no. **Dinamismo parcial es
peor que ninguno**; migrar ambos en una pasada es P2. El precio sí es dinámico en los dos.

**Reglas de horarios/dirección**: escritas en el nodo pero `enabled:false` a propósito — se
arranca solo con lo que falló de verdad en producción (plata). Encenderlas es cambiar una
palabra, cuando el patrón se pruebe en vivo.

---

## Sesión 2026-09-02 — Bug real: Raquel no podía guardar en Conocimiento/Servicios (falso positivo del guard de precios)

**Reporte real de la Dra. Raquel (audios de WhatsApp a Lucas)**: al editar "Valor de
la primera consulta" en `/conocimiento` (y también probó en `/servicios`), el panel
rechazaba el guardado con "No se publican precios de tratamientos (se evalúan en
consulta). Consulta y cuota mensual sí." — pese a que el texto que quería guardar
NO fijaba precio de tratamiento, solo aclaraba que el precio del tratamiento se
define en consulta (contenido legítimo y correcto).

**Causa raíz**: `pareceTratamientoConPrecio()` en
`nexora-whatsapp-agent/app/(app)/conocimiento/actions.ts` (la server action que
usan TANTO `/conocimiento` como `/servicios` — mismo componente `guardarEntrada`)
implementa la regla dura de la reunión 14/7 ("nunca precio fijo de tratamiento")
pero chequeaba el TEXTO COMPLETO de la entrada de una: si en cualquier parte
aparecía una palabra de tratamiento (`bracket|ortodoncia|alineador|invisalign`) Y
en cualquier otra parte un "$" con número, bloqueaba — sin importar si estaban
relacionados. El texto real de Raquel decía en una oración "la consulta vale
$50.000" y en la siguiente "el valor de los tratamientos... se define en consulta"
— exactamente el patrón que la regla del 14/7 quiere fomentar, pero el regex lo
interpretaba como violación.

**Fix**: mismo regex y misma regla de negocio, pero el chequeo ahora es por
ORACIÓN (`split(/[.!?\n]+/)` + `.some(...)`) — solo bloquea si tratamiento y
precio aparecen juntos en la MISMA oración. Verificado con 3 casos: (1) el texto
real de Raquel → ya no bloquea; (2) violación real sintética "el bracket cuesta
$50.000 fijo" (mismo oración) → sigue bloqueando, como debe; (3) cuota mensual
("...tratamiento ortodóncico es de $70.000") → no bloquea (ya no bloqueaba antes
tampoco, por el acento en "ortodóncico" no matchea el regex — no se tocó, es
harmless coincidence, no está en el alcance de este fix).

**Deploy**: commit `173c8b8`, subido a producción con `deploy/redeploy.sh`
(`panel.raquelrodriguez.com.ar` → HTTP 200 post-deploy, healthcheck OK).

**Pendiente de Lucas**: responder a Raquel con el mensaje armado (3 preguntas
suyas del mismo hilo de audios, ya confirmadas contra el código):
1. Cómo crear categoría nueva en la KB → no hay paso aparte, se escribe libre en
   el campo "Categoría" (datalist con sugeridas, pero acepta cualquier string
   nuevo).
2. Si el contenido de la KB es literal o el bot lo interpreta → depende de la
   sección: horarios/precio de consulta (`prompts/v6_partials/general_funcion.md`
   PASO 1, "INFO CANNED") se cita TEXTUAL; todo lo demás pasa por
   `buscar_conocimiento` (RAG) y el bot PARAFRASEA sin inventar
   (`general_orden_decision.md` PASO 3). Nota: `prompts/v6_partials/` tiene drift
   con el prompt vivo (P3 backlog, GAP 10) — los VALORES citados en ese archivo
   ($40.000, horarios viejos) están desactualizados, pero la ESTRUCTURA de
   decisión (literal vs RAG-parafraseado) sigue vigente y es lo que se usó para
   responderle.
3. Si el panel reemplaza "el chatbot" (probablemente Chatwoot) para el día a día
   → confirmado por código que `/conversaciones` (`chat-view.tsx`,
   `conversation-list.tsx`) ya tiene toggle bot/humano + enviar mensaje como
   staff (`app/(app)/conversaciones/actions.ts`, pega a webhooks n8n
   `panel-toggle-bot`/`panel-send-human`) — consistente con lo demoeado el 15/8
   (gap conocido: el toggle tarda ~30 min en confirmarse). **No se probó en vivo
   esta sesión** (solo lectura de código) — si Lucas quiere, confirmar con un
   toggle real antes de asegurárselo a Raquel como 100% andando.

## Sesión 2026-08-21 (cont.) — Horarios y precio de consulta ahora dinámicos (pedido de Lucas antes de irse)

Lucas pidió explícitamente ("necesitamos buscar la forma de que puedan editar esos
datos que van a seguir cambiando como horarios y precios, que las prompt lo manejen
de manera dinamica") tras el fix de horarios de hoy — porque él se iba a ausentar y
no quería que cada cambio futuro de horario/precio dependiera de que Claude edite el
workflow a mano.

**Hallazgo real antes de tocar nada**: el panel YA tenía un lugar pensado para esto
— `/servicios`, que lee/edita `knowledge_base` y dice literalmente "Lo que edités acá,
Asiri lo empieza a usar al instante". Eso era **falso** para horarios y precio de
consulta: esos 2 valores estaban como texto fijo en el prompt de Sub-Agent
Agendar/General, y el propio orden de decisión de General (PASO 1: info canned
LITERAL, nunca llega a `buscar_conocimiento`) hacía que la KB fuera invisible para
esas 2 preguntas. Además la fila de horarios (KB id=20) tenía el valor VIEJO — nadie
lo había notado porque nunca se consultaba.

**Fix** (reusa la KB existente, no tabla/UI nueva):
- KB id=20 ("Días y horarios de atención") recortada a solo la frase citable
  ("La Dra. Raquel atiende martes y jueves de 8 a 12 hs, viernes de 8:30 a 12 hs, y
  lunes y miércoles de 15 a 19 hs.") — antes tenía además una instrucción interna
  ("Al pedir un turno, el primer mensaje debe declarar...") que no era segura de citar
  textual al paciente.
- 2 nodos nuevos en v6: `Get KB Horarios y Precio` (Postgres, `SELECT id, contenido
  FROM knowledge_base WHERE id IN (20, 21)`) → `Extraer Horarios y Precio` (Code:
  arma `horarios` + `precio_consulta` extraído por regex `$XX.XXX` del contenido de
  id=21, con fallback defensivo a los valores reales de hoy).
- Sub-Agent Agendar (PASO 3) y Sub-Agent General (canned "Horarios Dra. Raquel",
  "Precio consulta" x2, "PRECIO DE TRATAMIENTO especifico") ahora interpolan
  `{{ $('Extraer Horarios y Precio').item.json.horarios/precio_consulta }}` en vez de
  texto fijo.
- `lib/servicios.ts` (panel): nueva sección "Horarios de atención" en `/servicios`
  (antes solo existía "Precios y valores") — deployado.

**2 bugs reales encontrados y arreglados DURANTE el armado (no en el diseño inicial)**:
1. **"No path back to referenced node"** — el primer intento conectó los 2 nodos
   nuevos como rama paralela muerta desde "Edit Fields - Extraer Datos" (mismo patrón
   sin salida que "Get Paciente Context"), asumiendo que "ejecutó antes en la misma
   corrida" alcanza para que `$('NodeName')` funcione desde otro nodo. NO alcanza:
   n8n necesita un camino CONECTADO real (pairedItem lineage). Confirmado con 2
   ejecuciones reales que fallaron justo así. Fix: insertar los 2 nodos EN LINEA entre
   `Parse Intent` y `Switch sobre Intent` (punto compartido por todos los sub-agents
   antes de la bifurcación), con merge explícito `{...$('Parse Intent').item.json,
   horarios, precio_consulta}` para no perder los campos que el Switch necesita para
   rutear.
2. **Comparación de tipos silenciosa** — el código comparaba `r.id === 20` (número),
   pero el nodo Postgres devuelve `id` como STRING ("20") → la comparación siempre
   daba falso y el código caía al fallback en silencio (sin error visible). Se probó
   con la **prueba de fuego real**: cambiar el precio en la KB a un valor de prueba
   ($99.999) y ver que el bot lo seguía diciendo con el valor viejo — eso expuso el
   bug. Fix: `String(r.id) === '20'`.

**Verificado con la prueba que realmente importa** (no solo "el diff se ve bien"):
se cambió el precio y despues el horario en la KB a valores de prueba claramente
distinguibles, se mandó un mensaje real, y el bot repitió el valor de prueba
exacto — confirmando que editar `/servicios` (o la KB directo) cambia lo que el bot
dice SIN tocar n8n. Se probó también el path de Sub-Agent Agendar (oferta de turno)
con el valor real ya revertido. Todos los datos de prueba (6 teléfonos sintéticos)
limpiados de `n8n_chat_histories`/`conversaciones`/`pacientes` al terminar.

**Pendiente (no se tocó hoy, por alcance)**: precio de cuota mensual ($70.000, KB
id=36) sigue hardcodeado en Sub-Agent General — mismo patrón, se puede extender
cuando haga falta agregándolo a la misma query/Code node.

## Sesión 2026-08-21 — Bug real: turno de Salvador Mayans nunca se creó en Dentalink (2 capas rotas) + 3 pedidos de contenido de la Dra.

**Reporte real de la Dra. Raquel (19/8, WhatsApp a Lucas)**: un paciente (Salvador
Mayans) tuvo conversación con el bot pero el turno JAMÁS se creó en Dentalink — ella
tuvo que agendarlo a mano. Reconstruyendo la conversación real (`n8n_chat_histories`,
session `5493885861016`): el paciente escribió en UN SOLO mensaje "Si, el paciente es
Salvador Mayans, DNI 56009370 / Cual es el valor de la consulta? / Recibe instituto de
seguros?" — el bot solo contestó precio/obra social y nunca llamó
`crear_paciente_dentalink` ni `reservar_turno`.

**Causa raíz (confirmada reproduciendo el caso en vivo, no solo leyendo el prompt) —
son 2 capas rotas, no una:**

1. **Router - Clasificar Intent**: tiene una regla "EXCEPCION A LA CONTINUACION" (si
   en medio de un flujo el paciente pregunta info canned → abandonar y devolver
   `consulta_general`) que no contemplaba el caso de que el mensaje trajera AMBAS
   cosas a la vez (la info pedida + la pregunta nueva). Clasificó mal a
   `consulta_general` en vez de `agendar_nuevo`.
2. **Sub-Agent General** ya tenía desde el 03/06 (caso Valentino) una "VALIDACION DE
   DESTINO" pensada exactamente para este escenario (si el paciente claramente está
   accionando → `[NO_REPLY]`, deja que el Router reclasifique) — pero la regla de
   obra social ("REGLA DE PRIORIDAD ABSOLUTA... IGNORAR EL RESTO y responder SOLO el
   canned de OS") la pisaba en la práctica: el bot respondió el canned de obra social
   e ignoró que el mensaje traía nombre+DNI para completar un registro pendiente.

**Primer intento de fix (solo en Sub-Agent Agendar) NO alcanzó**: reproduciendo el
caso con teléfono de test, la ejecución real (262253) mostró que el Router mandó el
mensaje a Sub-Agent General (intent `consulta_general`), no a Agendar — el fix nunca
tuvo chance de aplicarse porque el sub-agent correcto ni corrió.

**Fix real (2 capas, defensa en profundidad — regla dura del proyecto)**:
- `apply_fix_router_continuacion_multi_pedido.py`: nueva excepción-a-la-excepción en
  el Router — si el mensaje trae la info pedida (nombre+DNI, slot, etc.) JUNTO con
  una pregunta canned, mantener el intent operativo, no abandonar a
  `consulta_general`.
- `apply_fix_subagent_general_os_carveout.py`: excepción a la regla de prioridad
  absoluta de obra social — si el mensaje también completa una acción pendiente que
  Sub-Agent General no puede ejecutar, gana la validación de destino ya existente
  (`[NO_REPLY]`, deja reclasificar).

**Verificado E2E de punta a punta** (3 turnos reales vía webhook público, esperando
la respuesta real del bot entre cada turno — no solo el diff): turno 1 oferta de
slot, turno 2 confirmación + pedido nombre/DNI, turno 3 (multi-intent real: nombre+
DNI+precio+obra social en un solo mensaje) → Router clasificó `agendar_nuevo`,
`crear_paciente_dentalink` se ejecutó (paciente id 664 creado), `reservar_turno`
se ejecutó (**cita real 8850 creada en Dentalink**, 03/09 10:30hs) — el bug
completo está resuelto. Cita de test cancelada después (`id_estado=1`) y
conversación de test borrada de `n8n_chat_histories`/`conversaciones`/`pacientes`.

**3 pedidos de contenido de la Dra. (mismo hilo de WhatsApp, 19/8 y 21/8), también
implementados y probados hoy:**
- **Horarios actualizados** (`apply_fix_horarios_dra_raquel.py`, toca Sub-Agent
  Agendar PASO 3 + Sub-Agent General "Horarios Dra. Raquel"): Martes y jueves 8 a 12
  hs, Viernes 8:30 a 12 hs, Lunes y miércoles 15 a 19 hs (antes: Lun/Mié 15-20,
  Mar/Jue/Vie 8-12 parejo — estaba mal en los dos ejes). **NO se tocó** el horario de
  atención de la SECRETARIA ("Lun y Mié 15 a 20 hs / Mar, Jue y Vie 8 a 13 hs", KB
  id=11) que aparece en los canned de escalación — es un concepto distinto,
  confirmado por grep en los 4 sub-agents.
- **Pago el día de la consulta** (`apply_fix_pago_dia_consulta.py`, nuevo canned en
  Sub-Agent General): si preguntan puntualmente si pueden pagar el mismo día/al
  llegar, ahora responde el texto exacto que pidió la Dra. ("Nosotros le enviamos un
  recordatorio... dos días hábiles antes... para confirmar su asistencia le
  solicitaremos abonar...") en vez del canned genérico de alias que sonaba a "podés
  pagar cuando quieras".
- **Precio en primer contacto** (`apply_fix_precio_primer_contacto.py`, split del
  canned de precio en Sub-Agent General): paciente nuevo que pregunta precio SIN
  haber pedido turno todavía → respuesta simple sin alias/CBU ("Hola! Soy Asiri...
  El valor de la consulta es de $50.000... ¿Desea agendar un turno?"); paciente ya en
  flow de agendar o que pide explícitamente el alias → sigue la respuesta completa de
  3 partes con CBU.

Los 5 fixes de hoy probados con mensajes reales vía webhook público antes de darlos
por buenos (teléfonos sintéticos, limpiados después). Backups PRE/POST de cada uno en
`workflows/history/`. Mensaje-resumen para pasarle a la Dra. armado y entregado a
Lucas.

## Sesión 2026-08-18 — Bug real: "el agente solo ofrece turnos de tarde"

Reporte real de la Dra. Raquel (captura de WhatsApp): a una paciente que pidió un
turno de ortodoncia sin especificar horario, el bot solo ofreció tardes, llegando
hasta **16 de Septiembre** — cuando había turnos de mañana desde el **28 de Agosto**
(3 semanas antes). Causa raíz encontrada con la ejecución real (v6 exec 260221 →
Sub-WF Buscar Horarios Validado exec 260225, `GuDQ9VmKWZvQnerV`):

**Bug 1 (raíz)**: el nodo `Validar fecha` tenía un "BLINDAJE" que buscaba las
substrings `'17'/'18'/'19'/'tarde'/'despues'` en el JSON stringificado de TODO el
input de la tool — pero a este sub-workflow solo le llega `{fecha}`, nunca el
mensaje real de la paciente. Como la paciente escribió hoy 18/8 sin fecha concreta,
el Sub-Agent buscó desde `fecha: "2026-08-18"` — el string de esa fecha CONTIENE
"18" → el blindaje interpretó "pidió después de las 18hs" → `franja='tarde'`,
`hora_minima=18` → el texto que arma `Format Slots` le decía literalmente al LLM
**"NO ofrezcas mañanas"**, con `total_manana: 10` turnos reales disponibles. Bug
sistémico: se repite CUALQUIER día que la fecha buscada tenga 17, 18 o 19 en el
día del mes (o el sub-workflow reciba una fecha con esos dígitos en cualquier
posición) — no un caso aislado del 18/8. Fix: sacar el blindaje entero (no puede
funcionar bien, nunca tiene el texto real de la paciente para inspeccionar).

**Bug 2 (secundario, encontrado al re-testear)**: con el blindaje sacado, `franja`
correctamente queda `null` — pero cuando no hay preferencia, `Format Slots` le
daba al LLM las listas de mañana/tarde por separado sin decir cuál es el más
próximo en general, y el modelo seguía sesgando hacia tarde por las suyas. Fix:
calcular explícitamente el slot cronológicamente más próximo (Dentalink ya
devuelve los slots ordenados por fecha) y decírselo directo al modelo en el texto.

**Verificado con 2 tests E2E reales** (webhook público, números de prueba, no
pacientes reales) antes y después de cada fix — el segundo test post-fix confirmó
la respuesta correcta: *"El primer turno disponible que tengo es Viernes 28 de
Agosto 8:30 hs"*. Scripts: `apply_fix_bulletproof_tarde_fix.py`,
`apply_fix_format_slots_iterate.py`. Backups en `workflows/history/buscar_horarios_*`.

**Bug 3 (más grave, encontrado al re-verificar mañana/tarde)**: probando el pedido
explícito de "mañana", la ejecución real (260293) FALLÓ de verdad: `Evolution API -
Enviar Mensaje` del v6 — el nodo que manda CADA respuesta del bot a CADA
paciente — todavía tenía el patrón viejo sin `JSON.stringify` (`"text": "{{
$('Loop Mensajes').first().json.message }}"`), el mismo bug que se arregló esta
semana en Recordatorios/Daily Summary/Notify Grupo/Health Check/Human Takeover
pero que NUNCA se le aplicó a este nodo específico. Cualquier respuesta del bot
con un salto de línea real (muy común, cualquier mensaje de más de un párrafo)
rompía el JSON y Evolution GO devolvía "Bad control character" → el paciente NO
recibía la respuesta, en silencio. Fix aplicado (`apply_fix_v6_evo_go.py`) y
verificado: el mismo pedido de "mañana" que había fallado, reintentado, salió
sin error. Este es el nodo de mayor tráfico de todo el sistema — probablemente
explica fallos de envío esporádicos no reportados hasta ahora.

## Barrido sistemático de bugs silenciosos (18/8, pedido de Lucas tras el bug de JSON)

Después de encontrar el bug de `Evolution API - Enviar Mensaje` (arriba), Lucas pidió
un barrido completo para encontrar TODO lo que pueda estar fallando en silencio.
3 pasos, todos con evidencia real:

1. **Grep de "text/message sin JSON.stringify" en los 32 workflows activos** →
   encontró UN nodo más: `HTTP Send Admin Confirm` (v6) — la confirmación de
   `/bot off`/`/bot on`. Arreglado y **verificado en vivo con un ciclo real
   off→on** (mismo bot de producción, restaurado en <1 min). Grave porque es
   justo el tipo de escenario del incidente de Mariela: un admin apaga el bot y
   no recibe confirmación de que funcionó.

2. **Historial real de ejecuciones con error, en TODOS los workflows activos**:
   70 errores encontrados. 50 eran de Health Check (todos de ANTES del fix del
   6/8, nada nuevo). 2 de Daily Summary (también ya explicados). **18 del v6 —
   17 de los 18 eran el MISMO bug de `Evolution API - Enviar Mensaje`**, desde
   el **05/08 hasta HOY**: 13 días, ~15 pacientes reales afectados (lista
   completa con teléfono/fecha en el chat con Lucas — varios eran confirmaciones
   de turno o datos de pago que nunca llegaron). Ya no puede volver a pasar,
   el nodo está arreglado.

3. **Mapeo de nodos `continueOnFail`** (pueden fallar sin que el workflow se
   marque como error): 37 nodos en 8 workflows. Los de más riesgo — `Step 6a:
   Cancelar en Dentalink` / `Step 6d-1: POST Reservar` (Sub-WF
   CancelarReprogramar, `5cAWJxiWJ50hxEq3`) — se revisaron contra las 9
   ejecuciones reales que existen: solo una corrió, y salió bien. **Sin
   evidencia de daño real**, pero sigue siendo un riesgo latente (si algún día
   falla, el bot podría confirmarle un turno a un paciente que nunca se creó de
   verdad en Dentalink). Pendiente diseñar qué hacer en ese caso (¿reintentar?
   ¿escalar a secretaria?) — no aplicado, solo documentado.

**Lección**: mismo patrón que toda la semana — un "blindaje"/salvaguarda agregado
sin test real, que termina generando MÁS falsos positivos que los casos que
pretendía cubrir, porque revisaba datos que no reflejan lo que dice el paciente
(la fecha buscada, no su mensaje). Antes de agregar detección heurística por
texto, verificar qué datos realmente le llegan al nodo.

---

## Sesión 2026-08-15 — Reunión de seguimiento con Dra. Raquel (Lucas desde Toscana)

Detalle completo en `docs/reunion-2026-08-15-dra-raquel.md`. Es en gran parte un seguimiento
de `docs/reunion-2026-07-14-dra-raquel.md` (mismos temas) — lo nuevo:

- **Incidente recurrente de recordatorios**: Irina volvió a pedir apagar recordatorios porque
  ya había confirmado a mano, se reactivaron tarde, faltaron confirmaciones de lunes/martes.
  Diagnóstico: NO es bug — el fix técnico del 14/7 (agenda como fuente de verdad) sigue sano,
  el gap es que Irina sigue pidiendo on/off en vez de gestionar todo por Dentalink. Ver
  `decisions.md` 15/8.
- **Reportero semanal** (construido 11/8): pedido de extenderlo con scoring de urgencias +
  mapeo semanal específico de urgencias (no solo escalaciones generales).
- **Panel**: demo formal a Raquel — reacción positiva al chat simplificado tipo WhatsApp y las
  métricas. Gap señalado: toggle bot/humano no es inmediato (espera ventana ~30 min).
- **Triaje de urgencias**: Raquel confirma que ya filmó los 4 videos (alambre pincha, bracket
  suelto, alambre girado, ligadura pincha) — falta que los mande + el fraseo de preguntas.
- **Landing page**: sin material nuevo de Belén, mismo pedido que el 14/7. Detalle movido a
  `raquel-rodriguez/memory/` (repo propio, memoria creada esta sesión).
- **Grupo de supervisión** (Raquel+Lucas+Irina): pedido el 14/7, sigue sin crearse un mes
  después — pendiente de Raquel, no bloqueo técnico.

Backlog actualizado (`memory/backlog.md`, secciones "Reunión 14/7" cerrada/actualizada +
"Reunión 15/8" nueva).

---

## Sesión 2026-08-11 — Reportero Semanal construido y probado con datos reales

Backlog P1 desde el 18/7 ("diseño pactado, nunca construido"), pedido explícito de Lucas
("dale el reportero semanal"). Workflow nuevo `Áurea — Reportero Semanal`
(`MJ38kSTRZDPgPCCy`), activo, 11 nodos:

- Trigger doble: cron lunes 10 AM ART (`0 15 * * 1`, recordar que el cron del server usa
  hora Berlin — ver nota de zona horaria en sesiones previas) + webhook manual
  `trigger-reportero-manual` para pruebas.
- `Query Escalaciones Semana` (Postgres, credencial `TpYhZX4UT61xAKSV`) trae
  `escalaciones_log` de los últimos 7 días.
- `Clasificar y Agrupar`: **copia 1:1 de `lib/escalaciones.ts` del panel** (mismas regex
  señal/ruido/operativo + temas) — si se edita un lado, editar el otro. Mantiene
  consistencia con lo que ya ve la Dra. en `/aprendizaje`.
- Si hay señal: `Prep LLM Body` → `LLM Síntesis` (gpt-5-nano, credencial OpenAI
  `nYujqfon7GGDnJUO`, la misma que ya usa "Banlist Shadow" en el v6) le pide una sugerencia
  concreta por tema de qué cargar en Conocimiento. **OJO real encontrado en el primer test**:
  gpt-5-nano rechaza `temperature` custom ("Only the default (1) value is supported") — se
  sacó el parámetro del body.
- `Prep Envío (test mode)`: **nace con `TEST_MODE=true`** (manda a Lucas, no al grupo) —
  mismo patrón ya usado en Recordatorios. Pasar a `false` recién cuando Lucas confirme que
  el formato/contenido del reporte le sirve (así lo pidió el diseño original: "mostrar el
  primer reporte a Lucas antes").
- `Enviar WA`: mismo patrón `JSON.stringify` sin comillas propias ya validado 3 veces esta
  semana para mensajes multilínea con emojis.

**Verificado con datos reales de la semana** (no solo el diff): 2 pruebas E2E reales vía el
webhook manual, la primera reveló el bug de `temperature`, la segunda salió limpia — 12
casos de señal reales, agrupados en 4 temas, con sugerencias concretas y en español
generadas por el LLM, mensaje entregado a Lucas por WhatsApp real. De paso se encontró y
limpió un resto de escalación de prueba (`id=113`, del test de Notify Grupo del 06/08 que
había quedado sin phone y sin borrar) que se había colado en el reporte.

**Decisión de Lucas (11/8)**: queda mandando SOLO a Lucas (`TEST_MODE=true` permanente, no
es un modo de prueba transitorio) — "que me mande a mí nomás, así que tranca". No pasar a
mandar al grupo salvo que lo pida explícitamente.

---

_Última actualización: 2026-08-06 mañana ART — barrido completo: la misma expresión rota de
Evolution GO apareció en 4 workflows más además de v6/Recordatorios, los 5 ya arreglados y
verificados con ejecución real_

## Sesión 2026-08-06 mañana — barrido sistemático del bug de expresión rota (Evolution GO)

**Motivo**: Lucas notó que no le llegó el resumen diario de recordatorios y me marcó,
correctamente, que decir "revisé todo" y seguir dejando el mismo bug en otros lados no es
suficiente rigor. Tenía razón: encontré la misma expresión rota (`"{{ String(={{ $json.X }}
||"").replace(...) }}"`, nested mustache + "=" suelto — el patrón de la migración apurada de
la noche del 04→05/08) en **4 workflows más**, además de los 2 ya arreglados anoche
(v6, Recordatorios):

1. **`Áurea — Daily Summary Recordatorios`** (`QsGBGkZdGu5gTdBf`) / nodo `Send WA Lucas`:
   por esto Lucas no recibió el resumen de hoy ni de ayer (falla desde el 05/08). Los
   recordatorios en sí SE MANDARON BIEN los dos días (7/7 hoy, 0 errores) — solo el aviso A
   LUCAS sobre eso estaba roto.
2. **`Helper - Notify Grupo`** (`S5U6tSipzlgFHCkf`) / nodo `Notify Grupo Send` — **el más
   grave**: el aviso de escalaciones (urgencias, pagos, dudas reales) al grupo de WhatsApp de
   la clínica estuvo roto desde el 05/08 20:44 hasta el fix (06/08 ~13:55 confirmado con 4
   ejecuciones reales fallidas). Las escalaciones SÍ se loguearon en `escalaciones_log`
   (visibles en `/aprendizaje`) pero el aviso por WhatsApp nunca llegó — agravado porque este
   nodo tenía además su PROPIO bug: el "number" pretendía hardcodear el JID del grupo
   (`120363407321448469@g.us`) pero mal escrito como token JS inválido. Verificado con un
   envío real de prueba: Evolution GO acepta el JID completo del grupo (CON el sufijo
   `@g.us` — a diferencia de los números de paciente, un grupo NO se debe pasar por
   `.replace(/[^0-9]/g,...)`, eso lo rompe).
3. **`Áurea — Health Check (Dentalink + Evolution)`** (`Yjl6kyLnALhIfbFX`) / nodo
   `Send WA Alert Lucas` — mismo patrón. Pero además tenía un bug SEPARADO y más profundo: el
   nodo `Check Evolution` seguía apuntando al hostname Docker interno de la Evolution API
   CLÁSICA (`http://evolution-api-y6xc-api-1:8080/...`), que ya no existe → el workflow
   entero crasheaba con error de DNS cada 30 min desde las 12:00 UTC de hoy, ANTES de llegar
   siquiera al nodo con la expresión rota. Fix: apuntar a
   `GET https://evo.raquelrodriguez.com.ar/instance/all` (Evolution GO no tiene un endpoint
   de estado por-instancia más simple) + reescribir `Evaluar Health` para parsear el nuevo
   shape (`{data: [{name, connected: bool}]}`, antes esperaba `{state:...}`/
   `{connectionStatus:...}`). Verificado con la corrida real de las 17:00 UTC:
   `{healthy:true, skip_alert:true}` — sano de punta a punta.
4. **`Human Takeover - Chatwoot`** (`w7BBpZeEwZnpCX1q`) / nodo
   `Evolution API - Enviar a WA` — no había disparado desde la migración (ninguna ejecución
   real entre el 04/08 18:42 y el fix), así que no afectó a nadie todavía, pero tenía el
   mismo patrón roto. Arreglado preventivamente y verificado con un webhook Chatwoot
   sintético (`event: message_created`, número de prueba) — el nodo construye y manda la
   petición sin error.

**Todos verificados con ejecución real** (no solo el diff), datos de prueba limpiados de la
base después. Scripts: `apply_fix_daily_summary_send_wa_expr.py`,
`apply_fix_ruido_notify_grupo_evo_go.py` (los 3 de expresión), `apply_fix_health_check_evo_go_endpoint.py`
(el del endpoint muerto). Backups PRE/POST de cada uno en `workflows/history/`.

**Lección reforzada, esta vez con evidencia de que no se aplicó a tiempo**: en cuanto se
encuentra un patrón de bug (una expresión rota, un endpoint muerto) en UN workflow durante
una migración, hay que **grepear TODOS los workflows activos por esa misma firma antes de
cerrar el tema** — no esperar a que cada uno se manifieste por separado (a veces días después,
cuando alguien nota que falta un mensaje). El grep sistemático (`String(={{` / `{{ ={{`) en
los 30 workflows activos encontró los 3 restantes en un solo paso.

---

## Sesión 2026-08-06 madrugada — Recordatorios: expresión rota tras la migración a Evolution GO

**Contexto**: Lucas preguntó "¿los recordatorios y eso anda?" — auditoría directa del workflow
`Recordatorio de Turno 48HS - Dra. Raquel` (`7RqTApkvVavRmq3R`) mostró que corrió OK todos los
días hasta ayer 08:00 ART, pero esa corrida fue **antes** de la migración a Evolution GO de
anoche. La corrida de hoy 08:00 ART iba a ser la primera con el código nuevo — nunca probada.

**Bug 1 (sintaxis)**: el nodo `Enviar WhatsApp` (httpRequest) tenía un `jsonBody` con `{{ }}`
anidados y un `=` suelto (`"{{ String(={{ $json.remoteJid }}||"").replace(...) }}"`) — mismo
patrón de migración apurada que los 3 bugs del v6 de anoche. Con `continueOnFail: true`, esto
fallaría en silencio: el workflow reportaría "success" pero CERO recordatorios saldrían.

**Bug 2 (encontrado recién al testear, no estaba en el diagnóstico inicial)**: al corregir SOLO
la sintaxis (interpolar `$json.message` directo entre comillas dobles), el envío real devolvió
`"The value in the JSON Body field is not valid JSON"` — el mensaje de recordatorio es
multi-línea de verdad (`\n` reales del template), y un salto de línea crudo dentro de un string
JSON entre comillas rompe el JSON. Fix real: `{{ JSON.stringify($json.message) }}` **sin**
comillas propias alrededor (`JSON.stringify` ya devuelve el string completo escapado y
citado) — mismo patrón para `number`.

**Verificado con test E2E real, no solo el diff**: se activó momentáneamente `TEST_MODE=true`
en el nodo `Preparar mensaje` (ya existía, hecho para esto — redirige TODO el envío al
`TEST_PHONE` de Lucas con prefijo `[TEST 24h/72h] Para: <nombre real>`), se disparó
`POST /webhook/trigger-recordatorios-manual`, y se confirmó por captura de Lucas que el mensaje
completo (multi-línea, con el turno real de una paciente — Pamela, viernes 7/8 10:00hs) llegó
íntegro a WhatsApp. Después se revirtió `TEST_MODE` a `false` — **crítico no olvidarlo**, si
queda en `true` la corrida real de las 8 AM le manda todo a Lucas en vez de a los pacientes.

Scripts: `scripts/apply_fix_recordatorios_enviar_whatsapp_expr.py` (fix definitivo) +
`scripts/apply_toggle_recordatorios_test_mode.py --on/--off` (toggle de test, reusable para la
próxima vez que haga falta probar este workflow sin tocar pacientes reales). Backups PRE/POST
de las 3 aplicaciones en `workflows/history/recordatorios_*`.

**Lección reforzada**: la migración de anoche tocó "TODOS los workflows activos" según el
reporte de la sesión de la tarde, pero solo el v6 recibió test E2E real esa noche. Este bug en
Recordatorios confirma que "actualizado" ≠ "probado" aplica a CUALQUIER workflow tocado en una
migración de infraestructura, no solo al que tiene más tráfico. Antes de confiar en un cron que
todavía no corrió con el código nuevo, conviene disparar su trigger manual (si tiene) con un
modo de test real, no asumir por el diff que va a andar.

## Sesión 2026-08-09/10 — orden de recordatorios multi-turno + bug real de Dentalink

**Bug de Dentalink en CancelarReprogramar (arreglado, verificado):** Lucas pegó 2
escalaciones reales del grupo. La de "No veo turnos disponibles registrados en Dentalink"
resultó ser un bug real, no falta de disponibilidad: en `Sub-WF - CancelarReprogramar`
(`5cAWJxiWJ50hxEq3`), "Step 6b-prep: Prep Query Horarios" armaba el filtro en un campo
`dentalink_query_url` (URL completa) pero "Step 6b: GET Agendas" leía un campo DISTINTO,
`q_horarios` (nunca existía) → la query a Dentalink era literalmente `undefined` → siempre
`{"data": []}`. Pasó 4 veces desde el 30/7 (mismo motivo exacto en `escalaciones_log`).
Fix: renombrar al campo correcto + agregar filtro `fecha` (mismo patrón ya probado de
"Sub-WF - Buscar Horarios Validado"). Verificado pegándole directo a la API real de
Dentalink: la query vieja no filtraba nada útil, la nueva trae turnos reales.
Script: `apply_fix_buscar_horarios_deep.py`.

**Escalación "se los envié a la secretaria" — no es bug**: numero con identidad @lid
nueva sin historial previo, el bot no tiene contexto de qué "les" mandó. Coincide con la
decisión ya tomada el 6/7 sobre @lid (backlog aparte, no se toca sin resolver el problema
de fondo de identidad).

**Escalaciones "ya atendiendo" (48% del volumen)**: verificado que el panel `/aprendizaje`
YA las separa correctamente de la señal (no ensucian la vista), el aviso por WhatsApp para
ese caso ya se cortó el 4/8, y las 55 ocurrencias corresponden a 40 pacientes reales con
ficha — no es ruido espurio, es la secretaria atendiendo de verdad. Sin acción necesaria.

**Orden de recordatorios cuando un paciente tiene 2+ turnos el mismo día** (pedido real de
la Dra. Raquel, caso Ignacio Agus 11:10/11:40 mandados invertidos): se agregó el nodo
"Ordenar Citas por Hora" en `Recordatorio de Turno 48HS` (`7RqTApkvVavRmq3R`), entre "GET
Citas por fecha" y "Split Citas" — ordena TODO el array del día por `hora_inicio` antes de
partirlo en items. Es un sort global (no agrupado por paciente), así que escala solo a
cualquier cantidad de turnos el mismo día por paciente, no solo 2. Verificado con test real
(TEST_MODE on, ejecución 255176): el nodo corrió limpio, devolvió las citas del día
ordenadas cronológicamente, y la cadena completa (Split→GET Paciente→Preparar mensaje→
Enviar WhatsApp) siguió funcionando sin error. TEST_MODE revertido a false, filas de prueba
en `recordatorios_enviados` limpiadas. Script: `apply_fix_recordatorios_orden_multiturno.py`.

---

## Panel — polling más agresivo (pedido de Lucas en vivo)

`chat-view.tsx` 4s→1.5s, `conversation-list.tsx` 6s→2.5s (ambos siguen gateados a pestaña
visible). Deployado a `panel.raquelrodriguez.com.ar` vía `deploy/redeploy.sh` (GitHub Actions
sigue trabado por billing, pendiente de Lucas). Commit `27a039a`.

## Panel — bug de atribución: mensajes de staff (wa_outbound) sin limpiar, atribuidos a "Asiri"

Lucas mostró una captura real: el chat de `+54 9 388 470-8109` mostraba el marcador crudo
`[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria...]:` sin limpiar, con label
"Asiri" (verde, bot) en vez de "Dra. Raquel" (azul, humano). Causa: `chat-view.tsx` tenía un
guard `!esBotFuente &&` antes de chequear `metadata.source === "wa_outbound"` — pero el Logger
marca `fuente: "bot"` para CUALQUIER fila `type: "ai"` de `n8n_chat_histories`, incluidas las
notas de relay humano (confirmado con la fila real en Supabase: `fuente: "bot"` +
`metadata.source: "wa_outbound"` al mismo tiempo). El guard bloqueaba la detección SIEMPRE.
`source: wa_outbound` lo escribe un único nodo del v6 (`Build fromMe AI memory`, rama
`fromMe=true`) — nunca la generación normal del bot — así que es señal exclusiva, no hacía
falta cruzarla con `fuente`. Fix: sacar el guard. Deployado (commit `2a96394`).

## Intento de fix del Logger (fichas falsas) — REVERTIDO, no dejar aplicado sin más cuidado

Se intentó (madrugada 06/08) agregar un nodo IF entre "Parse mensajes" y "HTTP - Upsert
Paciente" en el Logger (`xsXeHp7WLXnFQc3o`) para que solo mensajes `rol=user` creen ficha de
paciente (evitar el caso "Ange"/fichas falsas de arriba). **Se revirtió de inmediato**: el
test con datos sintéticos mostró que rompía `HTTP - Insert Conversacion` para TODOS los items
(no solo el bypass) — error real de Postgres `invalid input syntax for type bigint: ""`,
porque "Insert Conversacion" lee `{{ $json[0].id }}` (el id de la ficha creada) del nodo
INMEDIATO ANTERIOR, y con dos caminos convergiendo en un solo puerto de entrada n8n dejó de
resolver bien esa referencia incluso para el item que SÍ pasó por el upsert. Revertido al
backup PRE (`workflows/history/logger_PRE_fix_no_ficha_falsa.json`), confirmado con ejecución
real que "Insert Conversacion" volvió a funcionar sin error y que el cursor
(`MAX(chat_history_id) FROM conversaciones`, que es como el Logger determina qué es "nuevo" —
OJO que NO usa el `last_synced_chat_id` de static data pese a lo que sugiere el nombre del
nodo "Get last_synced", ese campo parece vestigial) quedó sincronizado sin backlog (verificado
con una ejecución real limpia, 0 filas nuevas, cursor = 2416 = mismo que el máximo real de
`n8n_chat_histories` en ese momento). Cero pacientes reales afectados — se probó con teléfonos
sintéticos (5490000000001/002), limpiados de la base al terminar.

**Si se retoma este fix**: hay que resolver la referencia `$json[0].id` de forma que no
dependa de "cuál fue el nodo inmediato anterior" — por ejemplo pasando el `paciente_id` como
parte del mismo item que sale de la rama IF (agregando un campo `paciente_id` en cada rama
antes de que converjan), en vez de leerlo con un `$json` posicional que se rompe si el grafo
tiene más de un camino de entrada al nodo. Corregir con un test E2E real (no solo el diff)
ANTES de dar por bueno, tal como esta misma sesión tuvo que aprender dos veces esta noche.

**Hallazgo aparte, no resuelto (para hablar con Lucas)**: ese número específico no tiene
ninguna conversación real de paciente en 7 mensajes desde el 21/7 — solo notas
`[ATENCION HUMANA]`. El contenido relayado ("Ange fijate si ese es el botón...", "planilla de
compra") es claramente Irina hablando de insumos/compras con alguien, no un paciente. La
instancia Evolution GO "raquel" está conectada al **número personal de Irina**
(`5493885786946`, confirmado por el JID) — cualquier mensaje que ella mande desde ese WhatsApp,
sea a un paciente o no, dispara el webhook y puede crear una ficha de "paciente" falsa. No es
nuevo de esta migración (viene desde el 21/7 al menos). Sin resolver — depende de si Irina usa
ese numero tambien para uso personal/proveedores; si es asi, en algun momento conviene separar
el numero del bot del numero personal de ella.

---

## Sesión 2026-08-05 — Integración Definitiva de Evolution GO (APLICADO Y CONFIRMADO)

**Contexto e Infraestructura:**
- La Dra. Raquel escaneó el QR en la nueva interfaz de **Evolution GO** (escrito en Go, instanciado en VPS `187.127.0.110`).
- Instancia `raquel` **Conectada** (`connected: True`, JID `5493885786946`).

**Acciones y Fixes Aplicados:**
1. **Configuración y Persistencia de Webhook**:
   - `webhook` en `evogo_users` configurado a `https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2`.
   - `CONNECT_ON_STARTUP: "true"` activado en `/docker/evolution-go/docker-compose.yml`.
2. **Actualización de Workflows en n8n para Evolution GO**:
   - Evolution GO utiliza peticiones HTTP REST estándar (`POST /send/text`, `POST /message/downloadmedia`, `POST /message/presence`) con el token de instancia `apikey: fe27778f-6608-4a71-9385-e5c5c1eebf14`.
   - Nodos actualizados a `n8n-nodes-base.httpRequest` nativos en **TODOS los workflows activos**:
     - `Agente IA v6` (`O155MqHgOSaNZ9ye`): Enviar Mensaje, Obtener Media/Imagen (`/message/downloadmedia`), Typing status (`/message/presence`), Admin Confirm.
     - `Recordatorio de Turno 48HS` (`7RqTApkvVavRmq3R`).
     - `Helper - Notify Grupo` (`S5U6tSipzlgFHCkf`).
     - `Daily Summary Recordatorios` (`QsGBGkZdGu5gTdBf`).
     - `Health Check` (`Yjl6kyLnALhIfbFX`).
     - `Reactivación de Pacientes Inactivos` (`v8G9Cp98gioXObtu`).
     - `Human Takeover - Chatwoot` (`w7BBpZeEwZnpCX1q`).
3. **Panel de Métricas y `.env.production`**:
   - `EVOLUTION_API_KEY`/`EVOLUTION_GLOBAL_API_KEY` actualizada en `panel/.env.local` y en
     `/opt/nexora-panel/.env.production` en el VPS (valor real NUNCA en este repo — regla del
     proyecto; vive en los `.env*` locales/server, gitignored).
4. **Verificación de Envío**:
   - Mensaje de prueba real enviado por Evolution GO a Lucas (`"Hola Lucas! Prueba de envio con Instance token desde Evolution GO 🚀"`).
   - **Confirmado por Lucas en WhatsApp Web con captura de pantalla a las 9:00 p.m.**

⚠️ **CORRECCIÓN de esta misma noche** (ver sesión siguiente): ese test probaba SOLO el envío
directo a la API REST — el pipeline de RECEPCIÓN (webhook entrante) quedó completamente roto
hasta ~2hs después. "0 nodos antiguos en workflows activos" era cierto para el mecanismo de
envío, pero no cubría el shape del payload de *entrada*, que es una estructura totalmente
distinta. Ver el detalle abajo.

---

## Sesión 2026-08-05 (noche) — Evolution GO: el bot estaba MUDO Y SORDO, 3 fixes reales

**Contexto:** tras la migración de la tarde, Lucas reportó que el WhatsApp "se cayó" (en
realidad: Postgres de Evolution GO se quedó sin conexiones — ver más abajo). Al reconectar el
QR, pedí "corroborar sin mandar cagada" el trabajo de la sesión de la tarde. La auditoría real
(ejecuciones de n8n, no la afirmación del reporte) encontró que **el bot recibía WhatsApp pero
nunca respondía a ningún paciente** — 40 ejecuciones seguidas, ninguna llegaba a "Enviar
Mensaje". Root cause en 3 capas distintas, cada una diagnosticada con datos reales antes de
tocar nada:

### Fix 1 — pipeline de ENTRADA roto (CRÍTICO, afectaba al 100% de los mensajes)
`Webhook Validator` (y 3 nodos más: `Kill-switch Check`, `Rate Limit Prep`,
`Edit Fields - Extraer Datos`) seguían leyendo el shape de la Evolution API clásica
(`body.data.key.{remoteJid,id,fromMe}`, `body.data.message.conversation`,
`body.data.pushName`) — campos que **no existen** en Evolution GO (usa `whatsmeow`, shape
totalmente distinto). El validador rechazaba el 100% de los mensajes entrantes en el segundo
nodo del flujo, antes de que nada se guarde en memoria. Confirmado con un paciente real
(**Samira Benitez**, cita/DNI enviados a las 19:46, nunca procesados — ni guardados en
`conversaciones` ni en `n8n_chat_histories`, porque el rechazo pasa ANTES de cualquier
persistencia).

**Mapeo real del shape nuevo** (confirmado con payloads reales, no documentación):
```
body.data.key.remoteJid       -> body.data.Info.Chat
body.data.key.id              -> body.data.Info.ID
body.data.key.fromMe          -> body.data.Info.IsFromMe
body.data.pushName            -> body.data.Info.PushName
body.data.messageType         -> body.data.Info.Type  ("text"/"reaction"/"media")
body.data.message.conversation -> body.data.Message.conversation
body.instance                 -> body.instanceName
```
LID-safe (número real puede venir en `Chat`, `Sender`, `RecipientAlt` o `SenderAlt` según el
caso — el mismo mensaje `fromMe` a veces trae el numero real en un campo distinto que un
mensaje entrante): se prueban los 4 en orden, primero que matchee `@s.whatsapp.net`.

Aplicado con `scripts/apply_fix_evolution_go_payload.py --apply`. Backups en
`workflows/history/v6_{PRE,POST}_fix_evolution_go_payload.json`.

### Fix 2 — pipeline de SALIDA roto (el bot generaba la respuesta pero no la mandaba)
Tras el Fix 1, el bot ya clasificaba y generaba respuestas correctas — pero
`Evolution API - Enviar Mensaje` fallaba con "Bad request". Causa: `Evolution - Typing` (un
`httpRequest` genérico que reemplazó al nodo custom viejo) **pisa completamente** el `json`
del item con la respuesta HTTP de `/message/presence` — se pierden `remoteJid`/`phone`/
`message` que había armado `Split en Mensajes`. El nodo custom viejo probablemente preservaba
esos campos; el `httpRequest` genérico no, y nadie lo notó porque nunca se hizo un test E2E
real disparando el webhook completo.

**Fix**: `Evolution - Typing` y `Evolution API - Enviar Mensaje` ahora leen con referencia
explícita a `$('Loop Mensajes').first().json.X` (mismo patrón que ya usaba `Gate Humano Final`
con `Preparar Mensaje Final`) en vez de `$json.X` — no importa qué haga el nodo intermedio con
su propio output.

Aplicado con `scripts/apply_fix_evolution_typing_pisa_datos.py --apply`.
**Verificado con 2 tests E2E reales** disparando el webhook público con el shape real de
whatsmeow: ambos llegaron hasta el envío y quedaron guardados en `n8n_chat_histories`
(`human`+`ai` por par), confirmando memoria + clasificación + generación + envío funcionando
de punta a punta.

### Fix 3 — pipeline de MEDIA roto (fotos/audios/documentos, no bloqueante pero real)
`Switch - Tipo Mensaje` rutea según `image_url`/`audio_url`/`document_url` — campos que
`Edit Fields` armaba leyendo `imageMessage.url` (shape viejo, no existe más) → SIEMPRE vacíos
→ el switch nunca matchea ninguna rama de media → un paciente que manda una foto o un
comprobante de pago es tratado como si no hubiera mandado nada. Confirmado con el caso real:
**Samira mandó un comprobante de MercadoPago (PDF) a las 19:45, se perdió sin rastro.**

Hallazgo clave sobre cómo funciona Evolution GO: **NO expone URLs descargables** como la
Evolution API clásica — manda el archivo **ya descargado y en base64 directo en el webhook**:
```
body.data.Info.Type       = "media"
body.data.Info.MediaType  = "document" | "image" | "audio" | "ptt" | "video" | ...
body.data.Message.base64  = contenido ya decodificado
body.data.Message.documentMessage.{fileName, mimetype, ...}   (imageMessage/audioMessage/
  videoMessage/stickerMessage/locationMessage/contactMessage siguen el protocolo estándar de
  WhatsApp — no cambia entre libs, solo el contenedor padre sí: `Message`, no `message`)
```

**Fix**: `Switch - Tipo Mensaje` rutea por `Info.MediaType` directo (dato explícito, no
"¿hay URL?"). `Evolution API - Obtener Media`/`Obtener Imagen` — que eran `httpRequest` a
`/message/downloadmedia`, un endpoint **nunca verificado** contra Evolution GO real — se
reconstruyeron como nodos `Set` que copian el base64 directo del webhook (sin conexiones
nuevas, mismo nombre/posición, solo cambia CÓMO consiguen el dato: sin llamada HTTP externa,
más rápido, sin dependencia no probada). `document`/`otros` (video/sticker/ubicación/
contacto) solo generan un marcador de texto — así estaba diseñado desde antes de la
migración, no es parte de este bug.

Aplicado con `scripts/apply_fix_evolution_go_media.py --apply`. Verificado con el payload
real del comprobante de Samira (re-disparado al webhook con destinatario de test): rutea
correctamente a "documento", genera el marcador `[DOCUMENTO: mercadopago_comprobante_....pdf
(application/pdf)]`.

### Incidente aparte — Postgres de Evolution GO se quedó sin conexiones (causa de la "caída")
`idle_session_timeout`/`idle_in_transaction_session_timeout` estaban en `0` (sin límite) en
`evolution-go-postgres` — `whatsmeow` tiene un leak de conexiones conocido (no cierra bien la
conexión en cada `/instance/connect`), y sin timeout las conexiones fugadas nunca se
liberaban → agotó `max_connections=100` → NINGUNA instancia (`raquel` ni `Waves`, comparten el
mismo Postgres) podía generar QR. Fix de infraestructura, **declarado en el propio
`docker-compose.yml`** (no solo un `ALTER SYSTEM` ad-hoc que se pierde si se recrea el
container): `idle_session_timeout=3min`, `idle_in_transaction_session_timeout=2min`. Con esto
puesto, el pool nunca más puede agotarse por acumulación, pase lo que pase con el bug de la
app. Además, el banner de reconexión del panel (`whatsapp-status-banner.tsx`) bajó su
auto-refresh de 20s a 50s (menos presión sobre el mismo leak).

### Pendientes de esta sesión
- **Ventana rota real** (~19:05 a 20:07 ART del 05/08): ~11 mensajes de pacientes reales no
  llegaron a procesarse ni guardarse. Los más relevantes para seguimiento humano: **Samira
  Benitez** (datos + comprobante de pago) y **"manuu saltos"** ("me sigue chocando", suena a
  aparatología). Reportados a Lucas por WhatsApp, no recuperables desde el panel (nunca se
  guardaron en `conversaciones`).
- **Auditados y sanos**: los otros 6 workflows que la sesión de la tarde tocó no dependen del
  shape de Evolution (o no tienen webhook de entrada, o su entrada no es de Evolution) — el
  bug era exclusivo del v6.
- Token `ghp_p1z37…` filtrado (sesión 22/7) y contraseña del panel: siguen pendientes de Lucas.
- **Lección para la próxima migración de infraestructura de mensajería**: "el envío funciona"
  y "el bot funciona" son afirmaciones distintas. Verificar SIEMPRE con un test E2E que dispare
  el webhook público completo (no solo un POST directo a la API de envío) y confirme que la
  respuesta se genera Y persiste en memoria — el pipeline de recepción es donde vive la lógica
  de negocio real y es lo primero que rompe un cambio de shape de payload.















---

## Sesión 22/7 — Panel LIVE en producción


**El panel `nexora-whatsapp-agent` está deployado y andando:** https://panel.raquelrodriguez.com.ar
(login `lucas`/`irina`/`raquel`). Verificado E2E: la API real devolvió 67 conversaciones (auth
firmada + Supabase v3 OK).

**Infra del VPS (Hostinger KVM2, `187.127.0.110`, Ubuntu 24.04) — descubierto este día:**
- TODO corre en **Docker detrás de un Traefik** (`n8n-traefik-1`, dueño de :80/:443). Red
  compartida `n8n_default`. Certs Let's Encrypt vía certresolver `mytlschallenge`. Middleware
  de seguridad reusable `n8n@docker`.
- Containers vivos: n8n, 2x evolution-api, chatwoot (rails+sidekiq+pg+redis), waha, growth-engine,
  redis varios. El bot vive acá → el panel se limita con `mem_limit 512m` para no competir.
- **Había un panel viejo olvidado** (`dra-raquel-dashboard`, repo `LucasEzequielSilva/dra.raquel-dashboard`,
  del 20/5, otro código con basic-auth) ocupando `panel.raquelrodriguez.com.ar`. Se **apagó**
  (no borró) → rollback: `docker start dra-raquel-dashboard` tras `docker stop nexora-panel`.

**Cómo se deployó (aplicado, funciona):**
- Repo del panel pusheado a **`github.com/LucasEzequielSilva/nexora-whatsapp-agent`** (PRIVADO).
- Docker: `Dockerfile` multi-stage (pnpm + `output: standalone`) + `docker-compose.yml`
  (labels Traefik) + `.dockerignore`, todo commiteado. En el VPS: `/opt/nexora-panel/`.
- `.env.production` en el server (chmod 600, fuera del repo): solo las 15 vars que el código
  usa + `PANEL_SESSION_SECRET` nuevo. Los valores nunca pasaron por el chat.
- Swap de 4 GB agregada al VPS (tenía 0) para que el build no arriesgue OOM del bot.
- Build en el VPS (no había Docker local): `docker compose build` → imagen `nexora-panel:latest`.

**Auth del panel endurecida (commit `2f67529`):** cookie firmada HMAC + scrypt (`PANEL_USERS`),
vencimiento 7d, `secure` en prod. Reemplazó el `base64(user:pass)` viejo. Detalle del deploy
en `decisions.md` (entrada 22/7).

**BUG DE PRODUCCIÓN encontrado y arreglado el 22/7 — recordatorios a extranjeros:**
El resumen diario del 22/7 marcó "4 enviados / 1 error Evolution". Leyendo la ejecución
real (237284) salió que el nodo `Preparar mensaje` del workflow de Recordatorios asumía que
TODOS los pacientes son argentinos: su rama catch-all `if (!celular.startsWith("54"))
celular = "549" + celular` le pegaba 549 a números que YA traían código de país (el `+`
se perdía en el `replace(/[^0-9]/g,"")` previo). Ejemplo: `+59173327830` (Bolivia, válido)
→ `54959173327830` → Evolution: "Erro ao enviar mensagem de texto".
- **Fix aplicado** (`scripts/apply_fix_telefono_internacional.py --apply`): se lee
  `esInternacional = /^\s*\+/.test(celular)` ANTES del replace + rama nueva que deja el
  número extranjero TAL CUAL. Verificado post-PUT: activo, 17 nodos, webhookId
  `trigger-recordatorios-manual` preservado. Backups PRE/POST en `workflows/history/`.
- **Alcance real** (escaneo de los 649 pacientes de Dentalink): 3 con número extranjero —
  fichas 269 y 88 (`+59173327830`, Bolivia, mismo número) y 200 (`+34611237936`, España).
  Jujuy es frontera con Bolivia, así que esto reaparece; el fix cubre cualquier país.
- **Isabel Sanai** (cita 8529 del 24/7 09:10) no había recibido el recordatorio 72h → se
  le mandó a mano por Evolution al número correcto. Además su fila en
  `recordatorios_enviados` (id=26) había quedado con el teléfono roto → se corrigió, si no
  su "confirmo" no habría matcheado (`consultar_recordatorios_abiertos` busca por teléfono).
- **Lección**: cuando el resumen diario marque "Errores Evolution: N", leer la ejecución
  (`/api/v1/executions/<id>?includeData=true`) y contar items nodo por nodo — el error real
  viene en el item, no en el status del workflow (que dice "success" igual).

**Pendientes de Lucas (no bloquean):**
- **GitHub Actions trabado por billing**: ningún workflow arranca (`startup_failure` hasta con
  un `echo hola`). El `.github/workflows/deploy.yml` (build→scp→symlink, con fallback que
  saltea el deploy si no hay `VPS_HOST`) está listo para cuando se destrabe. Mientras, redeploy
  manual por SSH. **OJO**: ese deploy.yml es el enfoque systemd/standalone viejo; el deploy
  real quedó Docker+Traefik. Si se reactiva Actions, reescribir el job a `docker compose`.
- Rotar token `ghp_p1z37…` filtrado en el git config del panel viejo del server.
- Cambiar la contraseña del panel (pasó por el chat).
- SSH: `ssh -i C:\Users\not\.ssh\raquel_vps root@187.127.0.110`.

---

## Sesión 19/7 — Panel: chat cockpit + sección Recordatorios escalable (diseño)

## Sesión 19/7 — Panel: chat cockpit + sección Recordatorios escalable

**Chat (`nexora-whatsapp-agent`, commits `ff102ec`):**
- Card de turno **inline** en el hilo, justo donde el bot reserva (híbrido WhatsApp+Dentalink):
  detecta el mensaje de reserva (parse fecha/hora), matchea la cita real y muestra card
  accionable (confirmar/anular en Dentalink, confirmación en 2 pasos). Dark+light legible.
- Dentalink ahora agrega turnos de **todas las fichas** del celular (antes solo la 1ra → el
  turno nuevo caía en otra ficha y no se veía). `pacientesByCelular` nuevo.
- Sacado el wallpaper doodle del chat (plano, `--chat-surface`).
- Tiempo real: `force-dynamic` en /conversaciones + polling propio de la lista (8s).

**Recordatorios — diseño escalable (commit panel `49e01ed`):**
- Mandato de Lucas: "nunca más saturación de requests/infra/DB — pensalo como ingeniero".
- **Arquitectura**: el calendario de suspensiones es DATO leído 1 vez por la corrida diaria
  que YA ocurre (cero timers nuevos). Suspender un día = fecha en `dias_suspendidos`; al día
  siguiente ya no está → corre solo (auto-resume). 1 SELECT/día, fail-open.
- **v3**: tabla `recordatorios_config` (fila única id=1) — `scripts/recordatorios_config.sql`
  (PENDIENTE aplicar en SQL editor v3).
- **Panel**: nueva sección `/recordatorios` (on/off + hora vía n8n API ya funciona; suspender
  día/rango escribe a v3). Degrada con aviso si la tabla no existe.
- **Gate del workflow** (`7RqTApkvVavRmq3R`): ✅ **APLICADO 19/7** (lo corrió Lucas — el
  classifier me bloqueó el PUT+credencial n8n 4 veces; le pasé el comando). 14→17 nodos,
  0 nodos viejos mutados, webhookId preservado, verificación post-PUT OK. Backup PRE en
  `workflows/history/Recordatorio_PRE_gate_LIVE.json`. Semántica `suspender` fail-open:
  fila faltante o PG caído → corre igual. Config actual = default limpio (lunes corre normal).
- Cron recordatorios = lun-vie (`0 H * * 1-5`): suspender un finde es no-op; la sección
  del panel lo marca ("finde · no aplica") para no confundir a la secretaria.

**KB + Agente (commits panel `a47f3f0`, `929710b`):**
- **OPENAI_API_KEY** de Lucas cargada en `nexora-whatsapp-agent/.env.local` (gitignored) →
  el panel re-embebe de verdad al guardar en /conocimiento. **Lucas la pegó en el chat →
  conviene rotarla.** Modelo text-embedding-3-small, 1536 dims (mismo que el bot).
- **Bug arreglado**: guardar KB sin key ponía `embedding=NULL` (el bot dejaba de encontrar la
  entrada). Ahora si no se puede re-embeddar, se OMITE la columna (preserva el vector). Fila
  id 28 "menores" re-embebida (`scripts/reembed_kb_nulls.py`) → 0 NULL; sale #1 (sim 0.765)
  para "¿atienden niños?". KB = 100% real (auditoría panel: 0 datos de negocio hardcodeados).
- **Sección `/agente`** (nueva): lee el v6 EN VIVO de n8n y muestra Recepción (router) + 5
  especialistas + Estilo WhatsApp con modelo, tools e instrucción (systemMessage) VERBATIM.
  UI simple para secre/doctora, read-only (editar prompts = sensible, causó el incidente).

---

_Actualización previa: 2026-07-18 ~14:30 ART — ✅ SISTEMA 100% OPERATIVO sobre Supabase v3_

## ✅ FASE 2 COMPLETADA (18/7 ~14:15): sistema completo, nada pendiente de la migración

- `sb_secret` v3 recibida, validada contra REST (bypasea RLS ✓) y anotada en `.env`.
- Credencial supabaseApi **"Supabase account v3" id `H1PRagttKC5kxSzs`** creada
  (truco schema: `allowedHttpRequestDomains:"all"` explícito). 9/9 nodos REST
  repunteados (5 v6 + 4 Logger). Backups `supav3_20260718_141034`.
- **Logger ACTIVO** (5 min): sincronizó 8 filas a `conversaciones` + upsert `pacientes` ✓.
- **KB E2E PASS con forense**: "frenillo corto de mi hijo" → `buscar_conocimiento`
  invocado real (exec 232804 muestra la entrada "menores | Atención a menores" del
  vector store) → respuesta correcta.
- **RLS ON en las 6 tablas** (Lucas pasó la publishable key por chat → blindado; el bot
  entra por PG como owner y la sb_secret es service_role: ninguno afectado).
- **Simplificación pedida por Lucas**: v3 quedó en **6 tablas** (borradas documents/
  peticiones/servicios/urgencias_log, vacías y sin escritores — ver decisions 18/7).
- Credenciales huérfanas BORRADAS de n8n (v1 `xwvjww5Odcxiy1K9`, v2 `EWhpNhb6tkGg1OTp`,
  supabaseApi v2 `Thn3jgEbbxPFD7d9`) con guard previo de cero referencias.
- Tests E2E acumulados hoy: precio $50k ✓ · contexto/alias ✓ · memoria forense
  (Build Router Context + loadMemoryVariables leyendo n8n_chat_histories) ✓ · KB ✓.

**Credenciales v3 vigentes en n8n**: Postgres `TpYhZX4UT61xAKSV` · supabaseApi
`H1PRagttKC5kxSzs`. Todo lo demás en `.env`.

## 🖥️ Dashboard (arrancado 18/7 tarde)

Lucas dio el GO al panel. Mapeo completo hecho (4 agentes) → **plan en
`docs/plan-dashboard-2026-07-18.md`** (leerlo antes de tocar el panel). Highlights:
el repo `Desktop/proyectos/nexora-whatsapp-agent` ya tiene modo espejo diseñado para
Raquel + preview vivo en `nexora-whatsapp-agent.vercel.app` (Vercel de Valentino);
decisión recomendada = dual-Supabase SIN espejo (auth propio + lectura directa v3);
fases F1(solo-lectura)→F2(interacción+webhooks n8n)→F3(KB editable con re-embed)→
F4(weekly learning).

**PANEL F1-F4 COMPLETO (18/7 noche)** — commits en el repo del panel (git propio):
`c7b0617` F1-F3+chat premium · `3e9803d` F4 métricas · `bf173df` limpieza código muerto.
Todo andando en localhost:3000 (admin/admin), typecheck 0 errores, smoke de las 6 páginas OK.
- **Chat WhatsApp Web 2.0**: multimedia (chips + lightbox), tildes de visto (listo para ACKs),
  emoji picker, buscador in-chat, scroll-to-bottom, timestamps relativos.
- **Diferenciación**: paciente gris (izq) · Asiri verde · Dra. Raquel azul (der) — CSS
  `--chat-bubble-human` nuevo. Avatares con foto real de WhatsApp (`lib/evolution.ts` +
  `/api/foto/[telefono]`, cae a iniciales con color; la mayoría de pacientes no tienen foto
  pública → iniciales). Credenciales Evolution en panel `.env.local`.
- **Menú click-derecho** en la lista: marcar leído/no-leído (`marcarLeido/NoLeidoAction`),
  modo humano, abrir.
- **F3**: `/conocimiento` (KB editable + re-embedding con `lib/embeddings.ts`), `/servicios`
  (preset de la KB, constantes en `lib/servicios.ts` — módulo neutro, NO exportar valores
  desde un "use client" a un server component → rompe).
- **F4**: dashboard con % autonomía + no-shows evitados + tendencia escalaciones; página
  `/aprendizaje` (motivos de escalación → link a cargar KB — el loop que pidió la Dra).
- **Nombre real**: pushName de WhatsApp en vez de "Paciente WhatsApp" (`displayName` en phone.ts).
- **B4**: borrado el código muerto del producto viejo (117→62 archivos): lib/agent,
  lib/whatsapp, lib/google, lib/events, chatwoot, mirror, crypto, constants, supabase auth
  viejo. Se conservó dentalink + database.types (AppointmentStatus).
- **F5 Control** (19/7): página `/control` — prende/apaga bot + recordatorios y cambia el
  horario desde el panel (server-side vía API de n8n; `lib/n8n.ts`). Salvaguardas del
  incidente: confirmación al apagar el bot + banner rojo persistente cuando el bot está
  apagado. Env nuevas en panel: N8N_API_BASE/KEY + N8N_WF_BOT/RECORDATORIOS.
- **/citas ENCENDIDO** (19/7): token de Dentalink resuelto. NO era extraíble (n8n write-only;
  el store del dashboard viejo se borró con su Supabase). Login Dentalink real:
  `aureaodontologiaestetica.dentalink.cl`. Lucas sacó el token con el workflow reflector
  (httpbin) que armé y ejecutó él. Probado contra la API (`Authorization: Token <t>`, base
  `api.dentalink.healthatom.com`) → 200. En panel `.env.local` (gitignored). Panel habla
  DIRECTO con Dentalink (cero infra n8n ongoing). Token rotable en Dentalink si se quiere.
  **Lección**: n8n NO devuelve valores de credenciales (ni API 405, ni UI = `__n8n_BLANK_VALUE_`);
  se recuperan reflejando la credencial en un httpRequest a httpbin, o desde la fuente original.
- **Pendiente panel** (menor): (a) OPENAI_API_KEY para re-embed real de F3 (editar KB funciona,
  solo el re-embed al guardar espera la key); (b) foto de Raquel para mensajes salientes;
  (c) **webhooks n8n `panel-toggle-bot`/`panel-send-human`** para el toggle POR CONVERSACIÓN
  del chat y el "responder como staff" (hoy degradan con aviso; el toggle GLOBAL del bot ya
  anda por /control). Gate real = label Chatwoot 'humano' (patrón Human Takeover).

**F1 vieja (rama panel-v3-f1) quedó absorbida en main del panel.**

**COCKPIT — Dentalink en el chat (19/7)**: cada conversación muestra los turnos del
paciente en Dentalink (card colapsable "Turnos en Dentalink": fecha/hora/tratamiento/
profesional/estado con color) + **acciones Confirmar/Cancelar** que escriben en Dentalink
(`PUT /citas/{id}` id_estado 1=Anulado/22=Confirmado) con modal de confirmación. Cliente:
`pacienteIdByCelular` (celular Dentalink = telefono v3, match directo) + `/pacientes/{id}/citas`
(id_paciente NO es filtrable en /citas) + `updateCitaEstado` + `CITA_ESTADO`. Endpoint de
estados: `/api/v1/citas/estados`. El PUT NO se pudo autoprobar (clasificador bloquea escrituras
a Dentalink) — la escritura ocurre al click del staff. Commits panel: 48a2b4a (turnos read) +
6b041ef (acciones). **Foto de Raquel** (public/raquel.png) en sidebar + sus mensajes del chat.
**Visión "cockpit" (siguiente)**: cards inline en el punto del chat donde el bot agendó/escaló;
ficha del paciente arriba; toda acción del agente con rastro visible.

**F1 CONSTRUIDA (18/7 tarde, workflow 4 agentes)** en la rama **`panel-v3-f1`** del
panel — SIN COMMITEAR, esperando review + prueba en vivo. Diff: 8 archivos, +530/−597
(se fue el espejo). Piezas: `lib/supabase/v3.ts` + `lib/v3/database.types.ts` (base,
hecha a mano) · conversaciones agrupadas por telefono con polling 5s + resumen clínico
colapsable + toggle disabled ("F2") · dashboard con métricas v3 reales (mensajes/día
14d apilado, escalaciones 7d, tasa confirmación de turnos pasados, modo humano) ·
citas vía Dentalink EN VIVO (sin tabla) enriquecidas con recordatorios v3.
Typecheck PASS verificado. `actions.ts` viejo (toggle Chatwoot + WhatsApp Cloud)
ELIMINADO — F2 lo reemplaza con webhooks n8n.

**GIRO 18/7 ~15:45 — "nexora proyect" NO VA MÁS (Lucas)** → login del panel UNIFICADO
en el Supabase v3 (un solo proyecto para bot + panel):
- `.env.local` del panel apunta TODO a v3 (URL + publishable como anon + sb_secret).
- Signup con allowlist (`ALLOWED_SIGNUP_EMAILS`: nexora.srv@ y raquel.agenteia2026@)
  — registro cerrado para extraños (crítico: el panel ve TODOS los datos del bot).
- Junction creado: `raquel-n8n/panel` → `../nexora-whatsapp-agent` (gitignoreado).
- Dev server CORRIENDO en localhost:3000 (task btv0ovelc): /login 200 ✓ redirect ✓.
- ⚠️ El clasificador de permisos bloqueó ejecutar el DDL de auth (trigger sobre
  auth.users) → quedó en **`scripts/panel_auth_v3.sql`** para que LUCAS lo pegue en
  el SQL Editor de v3. Sin eso el signup falla (no hay organizations/profiles/trigger).
**FORK DEFINITIVO (18/7 ~16:00, orden de Lucas)**: el panel dejó de ser el producto
multi-tenant y pasó a ser EL PANEL DE RAQUEL: (a) landing eliminada, `/` redirige a
/login; (b) rebrandeado "Áurea / Odontología Estética" + "Asiri · Secretaria Virtual"
(cero "Nexora" visible; los tokens CSS --nexora-* quedan, son internos); (c) **git
NUEVO**: historia vieja borrada (respaldo completo en github.com/nexoragrowth/
nexora-whatsapp-agent hasta 31419d7), `git init -b main` + commit inicial `a828626`
"panel raquel v1" con TODO el F1 adentro — ya no existe la rama panel-v3-f1, main ES
el panel de Raquel, SIN remote todavía (Lucas dijo "haremos otra nueva"); (d) DB: ya
estaba 100% en v3. Typecheck PASS + smoke: / → login, marca Áurea/Asiri ✓.
**GIRO FINAL 18/7 ~16:45 — LOGIN SIMPLE**: por orden de Lucas el panel usa
**admin/admin** (env PANEL_USER/PANEL_PASS, `lib/simple-auth.ts`, cookie) — Supabase
Auth ELIMINADO del panel, `scripts/panel_auth_v3.sql` OBSOLETO (no correr). Borradas
las rutas del producto viejo (signup/callback/personalizacion/integraciones/app/api).
E2E completo PASS (rebotes + dashboard con datos reales). Ver decisions 18/7.
**También 18/7 tarde**: bug del Logger (cursor=0 re-insertando todo cada 5 min —
origen de los "requests fantasma" que alarmaron a Lucas) arreglado de raíz: cursor
derivado de la base + UNIQUE chat_history_id + 390 duplicados limpiados. Verificado
tick post-fix = 0 inserts. Workflow nuevo inventariado: Sub-WF "Buscar Horarios
Validado" `GuDQ9VmKWZvQnerV` (legítimo, lo llama Agendar).
**Bloqueado en Lucas**: solo el DENTALINK_TOKEN en `.env.local` del panel (línea
CHANGEME_LUCAS) para encender /citas. Entrar al panel: localhost:3000 → admin/admin.
Pendiente próximo: repo GitHub nuevo + push; F2 (webhooks n8n toggle/send).

## Optimización auditoría (18/7 tarde) — Track A

**A1 APLICADO Y VERIFICADO** (batch, backups en workflows/history/*_a1_*):
- URGENTE: Weekly Learning `B7IS4EVvxUAnGDXi` (contaminaba KB el domingo, cred PG borrada)
  y Cleanup `En0A5lXd3Whb5yFy` (full-scan borra 0 filas) → DESACTIVADOS con backup.
- 5 workflows parcheados: Helper (bug funcional #1: escalaciones de cancelar no silenciaban
  al bot), Sub-WF Cancelar (parse tolerante Step 0b), Buscar Horarios (TZ Jujuy), Recordatorio
  (INSERT parametrizado + webhook onReceived + skip item inválido), v6 (guard DDL fuera de
  Check Session Age, Banlist Shadow early-return en NO_REPLY, buscar_horarios anti-sondeo,
  confirmar_turno placeholder). Scripts: `apply_audit_a1_satelites.py` + `apply_audit_a1_v6.py`.
- SQL: índice único conversaciones.chat_history_id asegurado + drop idx_nch_session_created huérfano.
- Verificado: v6 0 errores/30 execs, kill-switch PASS, E2E 5/5 (el "fail" de cuota es correcto:
  desambigua antes de dar $70k). 120 nodos, webhook intacto.

**A2 PREPARADO PERO BLOQUEADO POR EL CLASIFICADOR** (necesita OK explícito de Lucas):
`scripts/apply_audit_a2_get_paciente.py` — desactiva "Get Paciente Context" (query muerta que
corre por cada webhook, resumen_clinico vacío garantizado; ahorra ~100-200 queries/día) +
reemplaza su expresión por texto estático en los 3 Sub-Agents. El clasificador lo frenó por
tocar los systemMessage del v6 (zona sensible del incidente). Para aplicar: correr el script
con OK de Lucas. Resto de A2 (dedup Logger, Sub-Agent Cancelar huérfano, Health Check alertas,
barrido token Chatwoot que necesita VPS) documentado, sin aplicar.

**A3 solo-propuesta** (no aplicar): Clear Old Memory no-op, Gate Humano doble-disparo, Health
Check "Check Supabase" (el ALTO más valioso), pooler transaction-mode :6543. Detalle en el
output de la auditoría (workflow wwros9tph).

**Próximos pasos (nada urgente)**:
1. Reportero v2 "aprendizaje semanal" (P1) — diseño pactado: leer escalaciones_log +
   conversaciones → clasificar escaló-bien/por-gilada → pedidos ACCIONABLES (qué sumar
   a KB/prompt/comportamiento) → grupo. Mostrar el primer reporte a Lucas antes.
2. Batería de tests: casos específicos que pida Lucas (harness tests/test_e2e_bateria.py).
3. Ticket soporte Supabase por histórico v2 (Lucas) + decisión VPS vs v3-free antes 15/8.
4. Lunes 20/7 08:00 ART: primera corrida real del Recordatorio contra v3 — vigilar.

## ✅ RESOLUCIÓN DEL INCIDENTE 15-18/7: migrado a Supabase v3, bot respondiendo

**v3 = EL VIGENTE**: proyecto `eoizfjsyejixjzwgzwkt`, cuenta NUEVA
`raquel.agenteia2026@gmail.com` (org free con cuota fresca), región **sa-east-1 São Paulo**
(pooler `aws-1-sa-east-1.pooler.supabase.com:5432`, user `postgres.eoizfjsyejixjzwgzwkt`).
Credenciales en `.env`. **Falta solo la `sb_secret`** (Lucas la debe: API Keys → sb_secret).

**Lo ejecutado el 18/7** (todo verificado):
1. Esquema completo: 10 tablas + `match_documents` (`scripts/rebuild_v3_schema.sql`).
2. Backfill: **13 recordatorios** del 16-17/7 insertados (7 turnos lun 20/7 + 6 mar 21/7).
3. KB: **36 entradas** con embeddings (35 del export + [36] cuota mensual $70k nueva;
   precios $40k→$50k corregidos en [21][22][31]). Self-match 1.0 ✓.
4. Rewire n8n: 19 nodos Postgres en 8 workflows → credencial **"Postgres Supabase Nexora
   v3" id `TpYhZX4UT61xAKSV`** + 8 URLs REST al ref v3. Backups tag `supav3_20260718_*`.
   Lección: el POST /credentials exige `sshTunnel:false` explícito SIN campos ssh, y el
   pooler Supabase necesita `allowUnauthorizedCerts:true` (cert self-signed; con
   ssl:"require" estricto los nodos mueren — 1ra credencial `OZZVT9wQ14wyJjKW` borrada).
5. E2E PASS x2: precio → "$50.000" ✓ · contexto+alias ("y como puedo pagar?") →
   alias `dra.raquel.aurea` ✓. Memoria escribe en v3 (session Lucas, ids 1+).
6. Cursor Logger reseteado a 0 (base nueva). Cleanup ACTIVO (1x/día 04:00Z).
   `.env` actualizado a v3. Batería de tests nueva: `tests/test_e2e_bateria.py`.

**PENDIENTE INMEDIATO (fase 2, ~2 min cuando Lucas pase la `sb_secret`)**:
1. Anotarla en `.env` como SUPABASE_SERVICE_ROLE_KEY / SUPABASE_V3_SERVICE_ROLE_KEY.
2. Crear credencial supabaseApi "Supabase account v3" + repuntear los 9 nodos REST
   (5 en v6: obtener_historial_paciente, buscar_conocimiento/vector store, 3 tools
   recordatorios; 4 en Logger): re-correr `apply_supabase_v3_rewire.py` con
   `UPDATE_SUPA_CRED_IN_UI=0`, `REWIRE_DRY_RUN=0`, `N8N_V3_PG_CRED_ID=TpYhZX4UT61xAKSV`
   y la key real (el pase repuntea solo los nodos que sigan en la cred vieja Thn3jgEbbxPFD7d9).
3. **Reactivar Logger** (`xsXeHp7WLXnFQc3o`, quedó a 5 min, cursor 0) — está APAGADO
   a propósito: sus writes REST con la key vieja fallarían y el cursor avanza igual
   (pérdida silenciosa). Nada se pierde mientras tanto: memoria v3 lo guarda todo.
4. Test KB vector: descomentar el caso "kb" en tests/test_e2e_bateria.py y correr.

**Hasta que llegue la key, NO funcionan** (todo lo demás sí): buscar_conocimiento (KB
vector del Sub-Agent General), las 3 tools de confirmar/cancelar recordatorios,
obtener_historial_paciente, y el Logger→conversaciones. ⚠️ Si un paciente de los turnos
del lun 20/21 contesta "confirmo" ANTES de la fase 2, escala a Iri (las tools no llegan).

## Proyecto v2 MUERTO (pausado) — `ujfyapjwrdhnvqdvsjwp`

Murió en crash-loop 15-17/7: compute nano agotado (Logger @30s + Cleanup full-scan +
v6 6-10 queries/msg) → Postgres corrupto (`SQLSTATE 53100 could not access status of
transaction 0` en el redo, loop eterno). Los ~8.6k req/hora del dashboard eran los
servicios INTERNOS de Supabase en retry — no nuestros workflows. Quedó PAUSADO con el
**histórico de 202k conversaciones adentro**: ticket a soporte pendiente (texto ya
entregado a Lucas 17/7). NO BORRARLO hasta resolver el ticket o renunciar al histórico.
La org vieja `nexoragrowth` tiene egress 182% con gracia hasta el **15/8**.

## Qué es esto (refresh)

Bot WhatsApp producción para Áurea Odontología (Dra. Raquel, Jujuy). n8n self-hosted
(`n8n.raquelrodriguez.com.ar`) + Evolution API + Dentalink + **Supabase v3** + Redis.
v6 = `O155MqHgOSaNZ9ye` (activo). Sub-WF Cancelar `5cAWJxiWJ50hxEq3`. La fila envenenada
que rompía el Sub-WF murió con la base v2 (v3 arranca limpia + message JSONB NOT NULL).

## Workflows (estado 18/7)

- **v6**: ACTIVO ✓ sobre v3 (memoria/contexto OK; tools REST esperan sb_secret).
- **Recordatorio 48HS** (`7RqTApkvVavRmq3R`): ACTIVO, recableado. Próxima corrida lun
  08:00 ART — primera escritura real en v3.
- **Logger** (`xsXeHp7WLXnFQc3o`): APAGADO hasta fase 2 (schedule 5 min, cursor 0).
- **Cleanup** (`En0A5lXd3Whb5yFy`): ACTIVO, 1x/día 04:00Z.
- **Cron Resumen Clinico** (`BO1cdE8xmqln4IeO`): DESACTIVADO por orden de Lucas 17/7
  (recableado igual por si se reactiva).
- Health Check / Auto Reactivar / Human Takeover / Helper Notify: activos, recableados.

## Mandato de optimización de Lucas (17-18/7) — "Supabase solo para lo esencial"

Uso permitido: (1) contexto conversacional últimos 10-30 msgs, (2) KB para respuestas,
(3) recordatorios/confirmaciones, (4) data para reportes semanales + dashboard. Nada de
crons que martillen ni requests de fondo. Estado: Logger 30s→5min, Cleanup 30min→1x/día,
Resumen Clinico OFF. Carga total ~300 execs-DB/día (era ~2.930). Pendiente de fondo:
v6 hace un guard DDL (DO/ALTER) POR MENSAJE en "Check Session Age" y "Get Paciente
Context" corre ANTES del filtro fromMe — optimizar con diff (backlog P1). Decisión
antes del 15/8: VPS Hostinger vs quedarse en v3 free (con la carga nueva puede alcanzar).
