# Retención de archivos y uso del plan free de Supabase — qué se borra, cuándo, y cómo se autoregula

**Fecha**: 2026-09-07 · **Pedido de Lucas** (02:50 ART): "¿todos los cambios de hoy pueden saturar la base? dejame todo para
que funcione y se autoregule" (+ audio desde el panel). **Estado**: scripts listos, revisados y corregidos (revisión 7/9 ~06:00:
smoke que avisaba en falso, orden de despliegue, `media_tipo` inválido, fuga del micrófono, formato único MP3, chip "vencido"
falso, MP3 a 8 kHz; tests 98/98, dry-run contra el v6 vivo y la base real). **Nada aplicado**: el DDL, la creación del satélite y
su activación las corre el orquestador con OK de Lucas.

## 1. Qué puede crecer y qué no (medido hoy)
Supabase v3 plan free: **500 MB** de base, **1 GB** de Storage, 5 GB/mes de egress.

| Recurso | Hoy | Ritmo | Qué lo frena |
|---|---|---|---|
| Base (`pg_database_size`) | 20 MB (`conversaciones` 3,8 MB / 5.811 filas; `n8n_chat_histories` 3,8 MB / 5.528 filas) | ~150 filas de memoria/día ≈ 40 MB/año | Nada que hacer por años. Alerta del Vigía a 400 MB. |
| Storage `pacientes-media` (privado) | 2 objetos, 0,03 MB | fotos ≤ 0,7 MB, audios ≤ 0,6 MB, PDFs ≤ 2,2 MB, **videos hasta 16 MB** | **Retención 90 días** (este doc). Alerta a 800 MB. |
| Storage `panel-media` (público, staff) | 2 objetos, 0,1 MB | imágenes comprimidas por el panel (≤ 1600 px), audios ≤ 10 MB | **Retención 90 días**. |
| Storage `urgencias-videos` | 2 objetos, 8,6 MB | fijo (videos del triaje) | No se toca. |
| `mensajes_entrantes_live` | 10 filas | 1 fila por mensaje con texto | **Retención 365 días**. |
| n8n (SQLite en el VPS) | 2,8 GB de 96 GB (63 GB libres) | pruning por defecto de n8n: 14 días / 10.000 ejecuciones | Ya se autoregula; fuera de este cambio. |

## 2. Qué se borra, cuándo y cómo — satélite `Áurea — Retención (archivos y bandeja)`
`scripts/create_retencion_satelite.py` (17 nodos, nace INACTIVO). Cron **04:30 America/Argentina/Jujuy** todos los días
(`settings.timezone` del workflow + cron `30 4 * * *`: el Schedule Trigger de n8n usa la zona del workflow). Webhook manual
`POST /webhook/trigger-retencion-manual` para correrlo a mano.

| Etapa | Criterio | Cómo | Resultado visible |
|---|---|---|---|
| 1. Adjuntos del **paciente** | `media_entrantes.created_at < now() - 90 días AND borrado_at IS NULL AND bucket = 'pacientes-media'`, lote de 200 | `DELETE {host}/storage/v1/object/pacientes-media` body `{"prefixes":[paths]}` con la credencial supabaseApi `H1PRagttKC5kxSzs` → si respondió 200, `UPDATE media_entrantes SET borrado_at = now()` para **todos** los ids del lote | El panel muestra el chip "Adjunto vencido (se guardan 90 días)"; `/api/media/<id>` responde 410 |
| 2. Adjuntos del **staff** (panel) | objetos de `panel-media` con `storage.objects.created_at < now() - 90 días` (`metadata IS NOT NULL` = archivos, no carpetas; `is_delete_marker IS NOT TRUE`), lote de 200 | Listado por SQL (credencial postgres `TpYhZX4UT61xAKSV`) y borrado por la **misma API REST** | La URL sigue en la memoria (`[imagen] <url>` / `[audio] <url>`); el panel pinta "Adjunto vencido" cuando Storage confirma que el archivo no está |
| 3. Bandeja en vivo | `mensajes_entrantes_live.created_at < now() - 365 días` | `DELETE` con `RETURNING` → cuenta | Nada visible (la memoria y `conversaciones` no se tocan) |
| 4. Log + aviso | siempre | 1 fila por etapa en `retencion_log`; WhatsApp a Lucas **solo si `fallidos > 0` o hay advertencia** (Storage no encontró NINGUNO de los paths pedidos; mismo nodo/headers que "Avisar a Lucas (WA)" del Vigía) | `retencion_log` |

Decisiones de diseño (con la evidencia del mapa de lectura del 7/9):
- **Nunca se borra Storage por SQL** aunque el rol tenga DELETE sobre `storage.objects`: dejaría el blob huérfano en S3 y seguiría
  contando en el plan. `storage.objects` solo se **lee** (listar `panel-media`, medir uso).
- **`POST /object/list` no sirve para `panel-media`**: el panel guarda `<tel>/<ts>-<uuid>-<file>` y ese endpoint es jerárquico
  (devuelve carpetas con `created_at: null`). Por eso el listado sale de `storage.objects.name` (= path completo).
- **Objeto ya inexistente = OK**: la respuesta del DELETE trae solo los objetos que existían; un path que no está no es error. Se
  marca `borrado_at` en todo el lote si el status fue 200 (si no, las filas sin objeto se reintentarían cada noche para siempre).
  Si Storage devolvió menos objetos que los pedidos queda anotado en `detalle`.
- **ids al UPDATE unidos por `|`** (`WHERE id = ANY(string_to_array($1, '|'))`): n8n parte `queryReplacement` por coma DESPUÉS de
  evaluar (falla real del 5/9); un array literal `{a,b}` rompería. El INSERT en `retencion_log` usa `defineBelow` (el `detalle` lleva comas).
  **Con ids vacío el parámetro es `'-'`** (`ids.join('|') || '-'`): un `queryReplacement` vacío hace que n8n no pushee ningún
  parámetro (`stringToArray` filtra entradas vacías → `there is no parameter $1`, verificado en n8n 2.9.4 con el mismo
  typeVersion 2.5) y el smoke del día del alta habría avisado en falso. `'-'` no matchea ningún id (16 hex) → `marcados 0`; el
  `Resumen` además no exige el UPDATE cuando no había ids que marcar.
- **Advertencia ≠ fallo**: si había filas reales y Storage devolvió 0 objetos borrados, lo más probable es que `media_entrantes.path`
  no coincida con `storage.objects.name` (encoding, prefijo): `borrado_at` se marca igual (si no, reintentaría cada noche) pero
  el aviso a Lucas sale con "⚠ Storage no encontró NINGUNO de los N path(s)…" sin contar como fallido (el caso legítimo de
  huérfanos no bloquea nada). Hoy los paths son `<tel>/<yyyy>/<mm>/<id>.<ext>` (`media/preparar.js`): riesgo bajo, pero es la
  única forma de detectarlo. El path fantasma del smoke no cuenta entre los esperados.
- Todo nodo que habla con afuera lleva `onError: continueRegularOutput` + `alwaysOutputData`; el `Resumen` lee cada etapa con
  `isExecuted`/try-catch, así una etapa caída no frena a las otras y termina en `fallidos` + aviso.
- **Smoke sin borrar nada**: `POST /webhook/trigger-retencion-manual` con body `{"smoke": true}` agrega el path
  `__retencion_smoke__/no-existe.bin` al lote de cada bucket → ejercita los dos DELETE (esperado: HTTP 200 `[]`), el UPDATE
  (0 filas) y el log (`detalle` con "smoke"). Es la forma de validar credencial + método DELETE con body el día del alta,
  sin esperar 90 días.
- Fuente única del JS: `retencion/agrupar_lote.js`, `retencion/resumen.js`, `retencion/armar_aviso.js`
  (`tests/test_retencion_y_staff.js` corre exactamente esos archivos; el script los embebe).

## 3. Cómo cambiar los días / el lote / la hora
Constantes al inicio de `scripts/create_retencion_satelite.py`:
```python
DIAS_MEDIA_PACIENTES = 90   # adjuntos del paciente (media_entrantes + pacientes-media)
DIAS_PANEL_MEDIA = 90       # adjuntos del staff (panel-media)
DIAS_INBOX_LIVE = 365       # mensajes_entrantes_live
LOTE = 200                  # objetos por corrida y por bucket; lo que sobra sale a la noche siguiente
CRON = "30 4 * * *"; TZ = "America/Argentina/Jujuy"
```
Cambiar → `python scripts/create_retencion_satelite.py --dry-run` (muestra cuántos borraría HOY con los valores nuevos) →
`--update <id>` (PUT solo con name/nodes/connections/settings). El texto del chip del panel ("se guardan 90 días") está en el
repo del panel: si cambian los días de pacientes, avisar ahí.

## 4. Cómo leer `retencion_log`
```sql
-- últimas corridas (una fila por bucket/tabla y por corrida)
SELECT corrida_at, bucket, borrados, fallidos, detalle FROM retencion_log ORDER BY id DESC LIMIT 15;
-- corridas con problemas
SELECT * FROM retencion_log WHERE fallidos > 0 ORDER BY id DESC;
-- cuánto se borró por mes y bucket
SELECT date_trunc('month', corrida_at) mes, bucket, sum(borrados) FROM retencion_log GROUP BY 1, 2 ORDER BY 1 DESC, 2;
-- lo que queda vivo vs. vencido en media_entrantes
SELECT count(*) FILTER (WHERE borrado_at IS NULL) vivos, count(*) FILTER (WHERE borrado_at IS NOT NULL) vencidos FROM media_entrantes;
```
`bucket` vale `pacientes-media`, `panel-media` o `mensajes_entrantes_live`. `detalle` empieza con `> N días` y suma notas
("Storage devolvió X de Y", "DELETE Storage: HTTP 403 …", "SELECT falló: …", "smoke: …", "⚠ Storage no encontró NINGUNO…").
Una corrida sin filas que borrar deja `borrados = 0, fallidos = 0` (así se ve que corrió). `--dry-run` también imprime las
últimas 6 corridas (y sigue contando aunque n8n no responda: el preview de nodos es lo único que depende del GET al v6).

## 5. Límites del plan free y alertas del Vigía (`scripts/create_vigia_bot.py`)
`Query señales` ahora trae `db_bytes` (`pg_database_size`), `storage_bytes` (suma de `storage.objects.metadata->>'size'`, sin
carpetas) y `storage_pacientes_bytes`. `Evaluar y deduplicar`:
- `supabase_db_alto` si base > **400 MB**: "📦 La base de Supabase está en X MB de 500 (plan free): hay que subir de plan o limpiar".
- `supabase_storage_alto` si Storage > **800 MB**: "📦 El Storage de Supabase está en X MB de 1024 (plan free): … (pacientes-media: Y MB)".
- `vigia_query_rota` si la query no devolvió `ahora` (permiso sobre `storage.objects`, columna, base caída): en ese estado
  **ninguna** otra alerta puede salir, por eso el Vigía se vigila a sí mismo.
- `retencion_no_corrio` si existe `retencion_log` y no tiene una fila de las últimas **26 h** (o está vacía: "nunca corrió"):
  cubre un Code node de Retención roto (los 4 no tienen `onError` y el workflow no usa `errorWorkflow`), el satélite inactivo y
  el cron en otra hora — sin esto la retención se apagaría en silencio hasta `supabase_storage_alto`. La query lo lee con
  `to_regclass` + `query_to_xml` (SQL dinámico) para NO romper mientras la tabla no exista (Postgres resuelve las tablas al
  parsear aunque el `CASE` no entre). Por eso el `--update` del Vigía va DESPUÉS del smoke y del `--activate` (§6): con la tabla
  recién creada y vacía avisaría "nunca corrió" una vez por día, que sería cierto pero ruido.
- Dedupe con `ventanaMin` por alerta (`$getWorkflowStaticData`): las 4 nuevas **1440 min** (un aviso por día), las históricas siguen en 60.
- Umbrales: `DB_ALTO_MB / STORAGE_ALTO_MB` al inicio de `EVAL_JS`. El pie del mensaje suma `base: X MB, storage: Y MB`.
- Se aplica con `python scripts/create_vigia_bot.py --update 1UbmAtUMtTBN9Bn3` (no toca secretos ni archivos locales; la
  API key de n8n se relee del `.env`).

Cuando llegue una alerta: (1) mirar `retencion_log` y `SELECT bucket_id, count(*), sum((metadata->>'size')::bigint)/1e6 FROM
storage.objects WHERE metadata IS NOT NULL GROUP BY 1`; (2) bajar `DIAS_*` y `--update`; (3) si aun así no alcanza, subir de plan
(Pro: 8 GB base / 100 GB storage) — decisión de Lucas.

## 6. Orden de despliegue (lo corre el orquestador, con OK de Lucas) — EL ORDEN IMPORTA
0. **Satélite staff ANTES que el panel**: `python scripts/create_panel_acciones_staff.py --update jzxb5zUKCaJcvCgp` (acepta
   `media_tipo: audio`, responde 400 a un tipo desconocido, filename con extensión). Es compatible hacia atrás (el panel viejo
   siempre manda `media_tipo: image`). Al revés NO: mientras el satélite vivo tenga el `Validar secreto` viejo, un audio del panel
   nuevo cae a `image` y `Enviar Media (staff)` hace `/send/media type: image` con una URL `.mp3` al número del paciente.
   Si `%TEMP%/panel_webhook_secret.txt` no existe, primero `--recover-secret jzxb5zUKCaJcvCgp` (GET al nodo vivo, no imprime nada).
   Verificar después con un envío de texto desde el panel (el toggle bot/humano también pasa por acá).
1. `python scripts/create_retencion_satelite.py --dry-run` → ver nodos, "Borraría HOY" (hoy: 0 / 0 / 0) y `DDL: … falta`.
2. `python scripts/create_retencion_satelite.py --ddl` → `media_entrantes.borrado_at` + índice parcial + `retencion_log` (idempotente;
   también en `scripts/rebuild_v3_schema.sql` §12/§13).
3. Deploy del panel (audio del staff, `borrado_at`, chip "vencido" confirmado por 404/410, 410 en `/api/media`) — antes de que
   el satélite marque algo, o sea antes del primer objeto con 90 días (hoy no hay ninguno). Prueba real: un audio desde el
   panel al celular de Lucas (Chrome Windows: tiene que llegar `.mp3` y sonar en el celular) + limpieza (regla dura 9).
4. `--apply` (exige el DDL) → `POST /webhook/trigger-retencion-manual` con `{"smoke": true}` y revisar la ejecución en n8n: los dos
   "borrar en Storage" con `statusCode 200` y `body []`, "marcar borrado_at" con `marcados 0` (corre con `$1 = '-'`), 3 filas
   nuevas en `retencion_log` con "smoke" en `detalle` y `fallidos 0`, **sin** WhatsApp a Lucas. Si el DELETE devolviera 4xx,
   llega el aviso y no se marca nada.
5. `--activate <id>` → registrar el id en `scripts/check_triaje.py` (tupla de workflows activos) y en `memory/current-state.md`.
6. Verificar la hora de la primera corrida automática (`startedAt` de la ejecución): debe ser 04:30 ART. Si la instancia ignorara
   `settings.timezone`, correría 04:30 UTC = 01:30 ART (igual de noche; corregir a `CRON = "30 7 * * *"` sin `TZ` y `--update`).
7. Recién ahora `python scripts/create_vigia_bot.py --update 1UbmAtUMtTBN9Bn3` y disparar `POST /webhook/trigger-vigia-manual`: la
   salida de `Query señales` tiene que traer `db_bytes`/`storage_bytes`/`retencion_tabla: true`/`retencion_min` (minutos desde el
   smoke) y NO tiene que llegar `retencion_no_corrio` (llegaría si el smoke no dejó filas o si pasaron > 26 h). Si `storage.objects`
   no fuera legible con la credencial de n8n, llega `vigia_query_rota` (verificado hoy con el rol del pooler:
   `has_table_privilege('storage.objects','SELECT') = true`).

## 7. Qué NO se borra y pendientes
- `n8n_chat_histories` (memoria del bot) y `conversaciones` (Logger): son el contexto y el historial del panel; a 40 MB/año no
  hace falta. El cron cleanup de memoria existente sigue igual. `urgencias-videos`: fijo. Redis: TTLs propios.
- **P3** objetos de `pacientes-media` sin fila en `media_entrantes` (huérfanos si el INSERT falló tras subir): hoy 0; se podrían
  listar desde `storage.objects` como `panel-media` y borrar igual.
- **P3** `scripts/limpiar_numero_demo.py` no toca `media_entrantes` ni Storage: los residuos de pruebas con un teléfono real se
  borran a mano hasta sumarle esa opción.
- Un `UPDATE` de `borrado_at` no dispara evento en vivo (el bus escucha solo INSERT en `media_entrantes`): el chip "vencido"
  aparece en el próximo refetch/poll o al reabrir el chat. Aceptable.

## 8. Audio desde el panel (lado bot: `scripts/create_panel_acciones_staff.py`, 17 nodos)
- `Validar secreto` acepta `media_tipo` `audio` (además de `image` / `video` / `document`); **un tipo desconocido con URL es
  error `media_tipo invalido`** (antes caía a `image`: como el panel siempre manda el tipo, ese fallback solo servía para
  mandarle a Evolution `type: image` con una URL que no es imagen hacia un paciente real); sin `media_url` el tipo queda vacío.
  `filename` saneado a `[A-Za-z0-9._-]`, máx. 80 chars **conservando la extensión** (antes un nombre largo la perdía).
- Respuestas: secreto incorrecto → **401** (`¿Sin secreto?` → `Responder 401`; el panel dice "sin autorización"); pedido mal armado
  (`telefono requerido` / `mensaje vacio` / `media_url invalida` / `media_tipo invalido`) → **400** con el error en el body (nodo
  nuevo `Responder 400`; el panel muestra el error genérico con el detalle); Evolution sin `Info.ID` → 502.
- `Enviar Media (staff)` no cambia: `POST /send/media` con `type = media_tipo` (verificado 7/9 con un envío real: `audio` → 200;
  `ptt` → 500 "invalid media type"; no existe `/send/audio`). La URL tiene que ser https accesible (pública o firmada).
- `Armar fila memoria` escribe `[audio] <url>` (+ `\n` + caption si hay) y `additional_kwargs.media_tipo = 'audio'`; el panel lo
  reconoce con `PANEL_MEDIA_RE` y pinta `<audio controls preload="none">`; la lista muestra "🎤 Audio · caption".
- Formato: WhatsApp reproduce mp3 / m4a (AAC) / ogg-opus; webm no es confiable (iOS). El panel manda **siempre MP3** (mono
  64 kbps, 48 kHz): graba webm/opus en Chrome/Firefox y AAC en Safari y transcodifica todo en el navegador (lamejs) antes de
  subir; un `.m4a`/`.webm`/`.ogg` solo sale si el encoder falla (con `console.warn`). El AAC fMP4 de Chrome ya no se manda crudo
  (nadie había verificado que WhatsApp lo reproduzca).
- Se aplica con `python scripts/create_panel_acciones_staff.py --update jzxb5zUKCaJcvCgp` (requiere el secreto local en
  `%TEMP%/panel_webhook_secret.txt`; si se perdió, `--recover-secret jzxb5zUKCaJcvCgp` lo copia del nodo vivo sin imprimirlo).
  **Antes del deploy del panel** (§6 paso 0).

## 9. Tests
`node tests/test_retencion_y_staff.js` (98 checks): `Validar secreto` (audio, tipos inválidos → error, mime en vez de tipo, sin
tipo, IF `¿Sin secreto?`/`Responder 400` en el script, filename largo/raro, http, secreto, toggle), `Armar fila memoria`
(audio/imagen/video/document/texto), Vigía (QUERY con `retencion_*` vía `query_to_xml`, umbrales estrictos, bigint como string,
dedupe 24 h vs 60 min, varias alertas en un mensaje, query rota sin falso "sorda", `retencion_no_corrio` tabla ausente/vacía/27 h/
25 h/dedupe/Vigía viejo), Retención (agrupar con filas/vacío/error/otro bucket/smoke; resumen con DELETE 403/red/UPDATE roto/SELECT
roto/smoke sin ids con `marcados 0`, con error y sin ejecutar/smoke con 1 real/0 de N → advertencia/1 de 2 → nota/bandeja; el
`queryReplacement` con `|| '-'`, el filtro de bucket y `is_delete_marker` leídos del `.py`; aviso solo con fallos, advertencia o
INSERT roto).
