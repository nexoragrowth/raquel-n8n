# Casos consolidados: infra_evolution_n8n y panel

Convención de fuentes: `e1..e4` = edgecases_1..4 (cada extractor numera EC-nn por su cuenta, hay colisiones: e1/EC-28 y e2/EC-28 son casos distintos). Hechos vivos 2026-10-04: v6 ACTIVO; Sub-Agent Cancelar y Sub-Agent Urgencia del v6 son nodos muertos; prompts Router/Agendar/Confirmar/General curados el 2026-10-04. Los prompts vivos (live_prompts.md) siguen leyendo `$('Extraer Horarios y Precio').item.json.{horarios,precio_consulta,direccion,pago_alias,pago_titular}` en Confirmar, Cancelar, Agendar y General (verificado).

## infra_evolution_n8n

### INF-01 · Pipeline de ENTRADA rechazaba el 100 % de los mensajes (shape Evolution GO) y ~11 mensajes reales perdidos
- **Entrada/disparador:** migración a Evolution GO (2026-08-05 noche). 40 ejecuciones seguidas sin llegar a "Enviar Mensaje". Caso real: Samira B. (cita/DNI a las 19:46, luego datos + comprobante) y M.S. ("me sigue chocando", suena a aparatología), nunca procesados.
- **Falla previa:** `Webhook Validator`, `Kill-switch Check`, `Rate Limit Prep` y `Edit Fields - Extraer Datos` leían el shape de la Evolution clásica (`body.data.key.*`). El rechazo ocurre antes de toda persistencia: no quedó nada en `conversaciones` ni en `n8n_chat_histories` (no recuperable desde el panel). Ventana rota 19:05-20:07 ART del 05/08, ~11 mensajes de pacientes reales perdidos; se reportaron a Lucas por WhatsApp para seguimiento humano.
- **Esperado:** el webhook con shape GO real (`body.instanceName`, `Info.Chat`, `Info.ID`, `Info.IsFromMe`, `Info.PushName`, `Info.Type`, `Message.conversation`) se acepta, genera respuesta y persiste `human`+`ai`. Extracción de teléfono LID-safe: se prueban en orden `Chat`, `Sender`, `RecipientAlt`, `SenderAlt` y se toma el primero que termina en `@s.whatsapp.net` (un fromMe a veces trae el número real en otro campo que un entrante). NO debe haber rechazo silencioso del Validator con payload GO.
- **Capa:** nodo (`apply_fix_evolution_go_payload.py`)
- **Test:** `tests/test_e2e_triaje.py` (webhook con shape GO); sin test unitario específico de los 4 nodos
- **Fecha/fuente:** 2026-08-05 noche · e2/EC-42, e2/EC-47, e3/EC-90 (parte del síntoma)
- **Estado:** vigente (corregido 2026-08-05)

### INF-02 · "El envío funciona" declarado como "el bot funciona" (E2E de migración incompleto)
- **Entrada/disparador:** 2026-08-05 tarde, otra sesión declaró "verificado E2E" tras un POST directo a la API REST de Evolution GO; captura de Lucas a las 21:00 mostraba el mensaje llegando. "0 nodos antiguos" era cierto solo para el envío.
- **Falla previa:** la RECEPCIÓN estuvo rota ~2 h (ver INF-01) porque nunca se disparó el webhook público completo.
- **Esperado:** "listo" = disparar el webhook público con el shape REAL del proveedor (payload real capturado) y confirmar que la respuesta se genera Y persiste en memoria. NO se acepta como verificación un envío directo a la API. Regla dura 8 del proyecto.
- **Capa:** infra (proceso / regla dura 8)
- **Test:** `tests/test_e2e_triaje.py` (webhook con shape GO); `tests/test_e2e_bateria.py` está en shape viejo (ver INF-03)
- **Fecha/fuente:** 2026-08-05 · e2/EC-48, e3/EC-90 (parte de la regla), DEC "Verificar SIEMPRE con un test E2E real"
- **Estado:** vigente

### INF-03 · Batería E2E `test_e2e_bateria.py` envía el shape VIEJO y el Validator lo descarta
- **Entrada/disparador:** `tests/test_e2e_bateria.py` manda `data.key.remoteJid` / `message.conversation`.
- **Falla previa:** `Webhook Validator` descarta ese shape; los 3 diseños del triaje lo ignoraban. La batería no prueba nada real.
- **Esperado:** usar `data.Info.ID/Chat/Sender/IsFromMe`, `data.Message.conversation`, `data.source='test_e2e_suite'` (bypass del rate limit) como en `tests/test_e2e_triaje.py`; migrar la batería.
- **Capa:** infra (tests)
- **Test:** `tests/test_e2e_triaje.py` (shape correcto); `tests/test_e2e_bateria.py` (shape viejo, inservible)
- **Fecha/fuente:** 2026-09-04/06 · e4/EC-210 (docs/triaje-fase2-analisis/jueces.md; docs/roadmap-refactor-2026-09-06.md B5)
- **Estado:** pendiente de decisión (migrar la batería)

### INF-04 · `Evolution API - Enviar Mensaje` rompía el JSON con saltos de línea: paciente sin respuesta (17 de 18 errores del v6, ~15 pacientes)
- **Entrada/disparador:** cualquier respuesta del bot con salto de línea real (más de un párrafo). Descubierto probando el pedido explícito de "mañana" (exec 260293). Barrido pedido por Lucas el 2026-08-18: 70 errores en workflows activos, 18 del v6, 17 de ellos este bug, entre 05/08 y 18/08 (13 días).
- **Falla previa:** el nodo tenía `"text": "{{ ... .message }}"` sin `JSON.stringify`; Evolution GO devolvía "Bad control character" y el paciente no recibía nada, en silencio. ~15 pacientes reales sin respuesta, varias eran confirmaciones de turno o datos de pago. Ya se había arreglado en otros 5 workflows esa semana pero nunca en este nodo, el de mayor tráfico. Los otros 1+ errores ya explicados (50 del Health Check previos al fix del 6/8 y 2 del Daily Summary).
- **Esperado:** `JSON.stringify` sin comillas propias (`apply_fix_v6_evo_go.py`); un mensaje multilínea llega completo. Ante un patrón de bug, grepear TODOS los workflows activos por la misma firma y revisar el historial real de errores.
- **Capa:** nodo (+ proceso de barrido)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-18 · e2/EC-17, e2/EC-18
- **Estado:** vigente (corregido 2026-08-18)

### INF-05 · Expresión rota con mustache anidado (`String(={{ ... }})`): escalaciones al grupo muertas 17+ h y Daily Summary sin llegar
- **Entrada/disparador:** Lucas no recibió el resumen diario de recordatorios (06/08 mañana). Firma `"{{ String(={{ $json.X }}||"").replace(...) }}"` en `Daily Summary Recordatorios` (falla desde el 05/08), `Helper - Notify Grupo`, `Health Check` y `Human Takeover`. Los recordatorios SÍ se enviaron (7/7).
- **Falla previa:** las escalaciones reales al grupo estuvieron rotas 17+ h (el bot igual logueaba en `escalaciones_log`); el Daily Summary no llegaba.
- **Esperado:** grep sistemático de la firma (`String(={{` / `{{ ={{`) en TODOS los workflows activos apenas se identifica el patrón, antes de cerrar el tema. Los 3 restantes se encontraron en un solo paso. Las escalaciones llegan al grupo `120363407321448469@g.us`.
- **Capa:** nodo + infra (proceso de barrido)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-06 mañana · e2/EC-28, e3/EC-92
- **Estado:** vigente (corregido 2026-08-06)

### INF-06 · Supabase caído invisible: el Health Check no monitorea la base (borrado v1 el 8/7 y caída 15-17/7)
- **Entrada/disparador:** 2026-07-08 proyecto Supabase borrado/pausado (v2 pausado con 202k conversaciones); 15-17/7 `econnrefused` en el pooler :5432 con REST respondiendo 401 normal.
- **Falla previa:** bot mudo para pacientes; ambas caídas invisibles porque el Health Check no pingea Supabase; alerta vía Evolution puede no llegar si Evolution cae; Logger a 30 s generaba ~90 % de la carga; Logger y Cleanup "debían estar inactivos" corrían activos hasta 2026-07-16 16:37Z; nadie sabía quién había arreglado el Health Check (¿otra sesión toca prod?); gap 22/7→28/7 sin registro en backups.
- **Esperado:** nodo "Check Supabase" en el Health Check (propuesta A3 #1, ALTO); canal de alerta fuera de banda; plan de choque (Logger a 5 min, Cleanup 1×/día); pooler transaction-mode :6543 en vez de session-mode (19 nodos PG); comparar el snapshot live con el último backup antes de cambios grandes; no borrar el proyecto v2 hasta resolver el ticket; Vigía (cron 15 min `1UbmAtUMtTBN9Bn3`) alerta a Lucas ante triaje degradado/errores/instancia sorda/triaje sin videos/uso: `supabase_db_alto` (>400 MB), `supabase_storage_alto` (>800 MB), `vigia_query_rota`, `retencion_no_corrio` (26 h, dedupe 24 h).
- **Capa:** nodo (Health Check / Vigía) + infra
- **Test:** `tests/test_retencion_y_staff.js` (Vigía: umbrales estrictos, dedupe 24 h vs 60 min, bigint como string, query rota, `retencion_no_corrio` tabla ausente/vacía/27 h/25 h, varias alertas en un mensaje); Check Supabase en Health Check: SIN TEST
- **Fecha/fuente:** 2026-07-08, 2026-07-16/18, 2026-09-07 · e4/EC-205, e3/EC-98 (parte Supabase)
- **Estado:** vigente (Vigía en producción; estado del nodo "Check Supabase" en Health Check no confirmado en las fuentes)

### INF-07 · Crash-loop de Supabase v2: nano agotado por Logger 30 s + Cleanup full-scan + 6-10 queries por mensaje
- **Entrada/disparador:** 15-17/7, ~8.6k req/hora en el dashboard (servicios internos de Supabase en retry), `SQLSTATE 53100 could not access status of transaction 0`.
- **Falla previa:** Postgres corrupto en loop; proyecto pausado con 202k conversaciones históricas.
- **Esperado:** mandato "Supabase solo para lo esencial" (Logger 5 min, Cleanup 1×/día, Resumen Clínico OFF); migración a v3 (`eoizfjsyejixjzwgzwkt`). Pendiente: el guard DDL por mensaje en "Check Session Age" y "Get Paciente Context" corre antes del filtro fromMe y debe moverse/eliminarse.
- **Capa:** infra
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-18 · e2/EC-56
- **Estado:** vigente (resuelto con v3); sub-pendiente: guard DDL por mensaje antes del filtro fromMe

### INF-08 · Migración de Supabase (restore a v2/v3): secuencias de ID sin restaurar, `match_documents`, apikeys viejos
- **Entrada/disparador:** restore tras el borrado del proyecto (2026-07-08): 22 cambios en 7 workflows, credencial nueva "Postgres Supabase Nexora v2" (luego v3).
- **Falla previa:** las secuencias de ID no se restauran; `match_documents` hubo que recrearla apuntando a `knowledge_base`; apikeys viejos en URLs; credenciales huérfanas del proyecto borrado.
- **Esperado:** resetear secuencias a max+1; verificar E2E; el índice único `conversaciones.chat_history_id` SÍ existe (no hay 42P10 inminente).
- **Capa:** infra (procedimiento de migración)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-08 · e4/EC-206
- **Estado:** vigente

### INF-09 · Logger con cursor=0 reinsertaba toda la tabla cada 5 min ("requests fantasma", 390 duplicados)
- **Entrada/disparador:** Lucas alarmado por requests fantasma (2026-07-18).
- **Falla previa:** el cursor volvía a 0 y reinsertaba todo en cada corrida.
- **Esperado:** cursor derivado de la base + UNIQUE en `chat_history_id` + limpieza; tick post-fix = 0 inserts.
- **Capa:** nodo + constraint SQL
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-18 · e2/EC-55
- **Estado:** vigente (corregido)

### INF-10 · Health Check roto 2,3 días (114 errores), fin de semana ciego
- **Entrada/disparador:** Health Check roto hasta 2026-07-05 22:20Z.
- **Falla previa:** monitoreo ciego durante el fin de semana; no se supo quién lo arregló.
- **Esperado:** Health Check con ping a Supabase (INF-06); alerta real de Dentalink/Evolution (hoy fallo silencioso, ver INF-18).
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-05 · e3/EC-98 (parte Health Check)
- **Estado:** vigente

### INF-11 · Health Check apuntaba al hostname Docker de la Evolution clásica (DNS muerto cada 30 min)
- **Entrada/disparador:** nodo `Check Evolution` usaba `http://evolution-api-y6xc-api-1:8080/...`, que ya no existe.
- **Falla previa:** crasheaba con error de DNS cada 30 min desde las 12:00 UTC, antes de llegar al nodo de alerta (50 errores, anteriores al fix del 6/8).
- **Esperado:** `GET https://evo.raquelrodriguez.com.ar/instance/all`; `Evaluar Health` parsea `{data:[{name, connected}]}` en vez de `{state}`/`{connectionStatus}`. Verificado `{healthy:true, skip_alert:true}`.
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-06 mañana · e2/EC-30
- **Estado:** vigente (corregido; el script `apply_fix_health_check_evo_go_endpoint.py` existe en el repo)

### INF-12 · Postgres de Evolution GO sin conexiones: el WhatsApp "se cayó" (no genera QR)
- **Entrada/disparador:** Lucas reportó que el WhatsApp "se cayó"; ninguna instancia (`raquel`, `Waves`) podía generar QR (2026-08-05 noche).
- **Falla previa:** `idle_session_timeout` e `idle_in_transaction_session_timeout` en 0 y whatsmeow filtra conexiones en cada `/instance/connect`; se agotó `max_connections=100`.
- **Esperado:** `idle_session_timeout=3min` e `idle_in_transaction_session_timeout=2min` declarados en el `docker-compose.yml`; auto-refresh del banner de reconexión del panel de 20 s a 50 s.
- **Capa:** infra
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-05 noche · e2/EC-46
- **Estado:** vigente

### INF-13 · Instancia "sorda": mensaje real "che me pincha" nunca llegó a Evolution GO (identidad LID)
- **Entrada/disparador:** 2026-09-05 ~17:20 ART, mensaje de Lucas "che me pincha"; en el log de `evolution-go-api` solo entró su "Hola" (17:17:49) vía LID con JID swap y WARN "untrusted identity… clearing stored identity and retrying".
- **Falla previa:** ninguna ejecución del v6 posterior; instancia `Connected/LoggedIn`, Health Check verde. No se pudo probar pérdida del lado de WhatsApp.
- **Esperado:** el Vigía (C) alerta si hay 0 entrantes en 3 h dentro del horario de clínica (lun-vie 8-20, sáb 8-13 ART) aunque Evolution diga connected. Pendiente: que Lucas reenvíe y ver si es problema de entrega por identidad LID.
- **Capa:** infra (Vigía `1UbmAtUMtTBN9Bn3`, cron 15 min)
- **Test:** `tests/test_retencion_y_staff.js` evalúa el Vigía en general; la regla "0 entrantes en 3 h" específica: SIN TEST
- **Fecha/fuente:** 2026-09-05 · e1/EC-58
- **Estado:** pendiente de decisión (causa raíz sin confirmar; el síntoma tiene alerta)

### INF-14 · Rate Limit con `phone=""` bloqueaba el 11.º mensaje GLOBAL
- **Entrada/disparador:** item pisado por nodos intermedios; key Redis `rate:` sin teléfono.
- **Falla previa:** todos los pacientes compartían un solo contador.
- **Esperado:** leer de `$('Webhook - Evolution API').first().json` + Code Eval + bypass si phone vacío; 10 mensajes/15 min por phone.
- **Capa:** nodo
- **Test:** "sintético OK, sin prod" (sin archivo en tests/): SIN TEST
- **Fecha/fuente:** 2026-05-09 · e3/EC-93 (BUGS #17)
- **Estado:** vigente. Nota: la ruta de lectura debe re-verificarse contra el shape GO de INF-01 (el Rate Limit Prep fue reescrito el 2026-08-05).

### INF-15 · 20 referencias `$json.body.data.*` rotas en `Edit Fields` tras un upgrade de n8n
- **Entrada/disparador:** upgrade de n8n; item pisado.
- **Falla previa:** las refs `$json.body.data.*` dejaron de resolver.
- **Esperado:** usar `$('Webhook - Evolution API').first().json.body.data.*`.
- **Capa:** nodo
- **Test:** "sintético OK, sin prod": SIN TEST
- **Fecha/fuente:** 2026-05-09 · e3/EC-94 (BUGS #18)
- **Estado:** superado en parte por INF-01 (2026-08-05): la regla de referenciar el nodo webhook explícito sigue vigente, pero los paths `body.data.*` pertenecen al shape de la Evolution clásica y hoy es `Info.*` / `Message.*`

### INF-16 · `Evolution - Typing` pisa `remoteJid`/`phone`/`message` y el envío falla con "Bad request"
- **Entrada/disparador:** tras el fix de INF-01 el bot ya generaba la respuesta, pero `Enviar Mensaje` fallaba (2026-08-05 noche). Segunda ocurrencia de la clase "nodos intermedios pisan `$json`" (antes: abril, BUGS #11, HTTP 400 por `$json.message` vacío).
- **Falla previa:** `Evolution - Typing` (httpRequest genérico) reemplaza el json con la respuesta de `/message/presence`; se pierden `remoteJid`/`phone`/`message` (el nodo custom viejo los preservaba).
- **Esperado:** `Typing` y `Enviar Mensaje` leen con referencia explícita al nodo origen. Verificado con 2 E2E reales (`human`+`ai` persistidos).
- **Capa:** nodo (`apply_fix_evolution_typing_pisa_datos.py`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-05 noche (y ~2026-04) · e2/EC-43, e3/EC-91
- **Estado:** vigente. Contradicción de fuentes: e2/EC-43 y el script aplicado usan `$('Loop Mensajes').first().json.X` (batchSize=1); e3/EC-91 cita `$('Split en Mensajes').item.json`. Se toma el script aplicado (Loop Mensajes, `.first()`) como el vigente; e3 queda superado en el nombre del nodo.

### INF-17 · "No path back to referenced node": `$('Nodo')` desde una rama paralela sin salida
- **Entrada/disparador:** los 2 nodos nuevos de horarios/precio se conectaron como rama paralela sin salida desde "Edit Fields - Extraer Datos"; 2 ejecuciones reales fallaron (2026-08-21). Pasó 2 veces según e4.
- **Falla previa:** se asumió que "ejecutó antes en la misma corrida" alcanza para que `$('NodeName')` funcione.
- **Esperado:** n8n exige camino CONECTADO real (pairedItem lineage). Insertar nodos EN LÍNEA (entre `Parse Intent` y `Switch sobre Intent`) con merge explícito `{...$('Parse Intent').item.json, horarios, precio_consulta}` para no perder campos de ruteo; referencias con `.first()` en lugar de `.item` cuando no hay pairedItem.
- **Capa:** nodo / topología
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-21 · e2/EC-7, e4/EC-207 (parte)
- **Estado:** vigente
- **Riesgo de regresión:** los prompts curados del 2026-10-04 siguen leyendo `$('Extraer Horarios y Precio').item.json.horarios` (Confirmar/Cancelar/Agendar/General) y `.precio_consulta`/`.direccion` (General) y `.pago_alias`/`.pago_titular` (Agendar): verificar que el nodo siga EN LÍNEA antes del Switch y que `Parse Intent` conserve los campos de ruteo.

### INF-18 · `PUT /workflows` borra `webhookId` en silencio y solo acepta ciertas keys
- **Entrada/disparador:** PUT del v6 sin `webhookId` o con key extra (`availableInMCP`, `binaryMode`).
- **Falla previa:** sin `webhookId` Evolution apunta a UUID null y el path queda inactivo sin queja del API (BUGS #12); key extra → 400; el `list` de workflows da 0 (scoping): hay que hacer GET/PUT por ID.
- **Esperado:** preservar `webhookId: evo-webhook-v2` con assert explícito y validar en GET post-PUT; PUT acepta solo `name, nodes, connections, settings, staticData`, settings filtrados con SETTINGS_OK (`saveExecutionProgress, saveManualExecutions, saveDataErrorExecution, saveDataSuccessExecution, executionTimeout, errorWorkflow, timezone, executionOrder, callerPolicy, callerIds`); backup PRE/POST en `workflows/history`; diff mostrado a Lucas; `scripts/apply_*.py` con dry-run por default; NUNCA tocar la URL del webhook.
- **Capa:** infra (reglas duras 2-4 + scripts apply)
- **Test:** SIN TEST
- **Fecha/fuente:** ~2026-04 y 2026-09-04/07 · e3/EC-95 (BUGS #12), e4/EC-207
- **Estado:** vigente

### INF-19 · Otra sesión modifica el nodo vivo mientras se prepara un PUT
- **Entrada/disparador:** entre la primera lectura de `Banlist Validator` y la aplicación del fix, `pacientePidioDireccion` ya había sido ampliado por otra sesión (incluye "dónde es", "cómo llego", "ubi", "maps"; comentario "ROUND 14").
- **Falla previa (riesgo):** pisar trabajo ajeno con un script basado en una lectura vieja.
- **Esperado:** el script se ajusta al contenido real del nodo vivo justo antes de aplicar (releer antes de cada PUT); abortar si el `versionId` cambió entre backup y PUT.
- **Capa:** infra (proceso / script de apply)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-10-01 · e1/EC-9, e4/EC-207 (parte versionId)
- **Estado:** vigente

### INF-20 · Snapshot local `workflows/current/` desactualizado respecto al vivo
- **Entrada/disparador:** se iba a aplicar el refactor "Sub-WF CancelarReprogramar usa Buscar Horarios Validado"; el vivo ya lo tenía desde 2026-09-07 mientras el snapshot local lo mostraba viejo.
- **Falla previa:** diseñar/aplicar sobre una foto vieja habría duplicado o roto trabajo en producción.
- **Esperado:** antes de diseñar o aplicar, leer el nodo vivo vía `GET /workflows/{id}`; no confiar en `workflows/current/*.json`.
- **Capa:** infra (proceso)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-10-01 tarde · e1/EC-10
- **Estado:** vigente

### INF-21 · Comparación `r.id === 20` falla en silencio (el nodo Postgres devuelve el id como string)
- **Entrada/disparador:** el nodo Postgres devuelve `id` "20" y el código comparaba con el número 20 (precio dinámico, 2026-08-21).
- **Falla previa:** siempre falso, caía al fallback sin error visible; el bot seguía diciendo el valor viejo.
- **Esperado:** `String(r.id) === '20'`. Los fallbacks defensivos pueden enmascarar un bug: verificar cambiando el dato a un valor distinguible ($99.999) y viendo que el bot lo repite.
- **Capa:** nodo
- **Test:** SIN TEST (prueba de fuego manual)
- **Fecha/fuente:** 2026-08-21 · e2/EC-8
- **Estado:** vigente
- **Riesgo de regresión:** General usa `precio_consulta` dinámico y el Router lo trata como info canned; tras la curación del 2026-10-04 verificar que cambiar el valor en la KB (id 20) se refleje en la respuesta.

### INF-22 · Fallas silenciosas por onError/continueOnFail y nodos sin continueOnFail (fail-closed → bot mudo)
- **Entrada/disparador:** Chatwoot, Redis, Postgres o Evolution fallan en un nodo.
- **Falla previa:** `Existe paciente?` sin continueOnFail (Chatwoot caído = bot mudo); `Re-check Humano` y `Postgres - Save fromMe` sin onError; los 7 nodos Redis sin continueOnFail (Redis caído = ejecución en error = bot mudo); `continueOnFail` en `/send/media` con jsonBody roto reportaría success sin enviar; Auto-reserva TODO.
- **Esperado:** neverError + inspección de la respuesta (`statusCode` 2xx o `data.Info.ID`) con fail-closed a la escalación normal; Health Check con alerta real de Dentalink/Evolution.
- **Capa:** nodo
- **Test:** `tests/test_triaje_nodos.js` (fail-closed del triaje); nodos del v6: SIN TEST
- **Fecha/fuente:** 2026-06-02 / 2026-09-03 · e4/EC-213
- **Estado:** pendiente de decisión (hardening listado, sin evidencia de aplicación)

### INF-23 · Evolution "miente" ("Erro ao enviar mensagem") y `continueOnFail` oculta 6 envíos fallidos
- **Entrada/disparador:** respuestas post-envío de Evolution; workflow `success` sin envíos (~abril 2026, BUGS #13/#14).
- **Falla previa:** error aparente con envío real; y a la inversa, fallos ocultos (6 envíos).
- **Esperado:** confirmar con el destinatario; inspeccionar el output de CADA nodo (error/PENDING), no el status global.
- **Capa:** infra (proceso)
- **Test:** SIN TEST
- **Fecha/fuente:** ~2026-04 · e3/EC-96
- **Estado:** vigente

### INF-24 · `queryReplacement` parte por coma DESPUÉS de evaluar y desplaza los parámetros del INSERT
- **Entrada/disparador:** texto del paciente con coma ("hola, cuanto sale…") en `Inbox Live` (2026-09-05); también caption con coma.
- **Falla previa:** n8n parte los params por coma tras evaluar; parámetros desplazados (`invalid input syntax for type boolean`).
- **Esperado:** insert parametrizado `columns.mappingMode: defineBelow` (mismo patrón que `Log Escalacion` del Helper) o SQL armado en Code con `esc()` + `chr(36)`; nunca `executeQuery` + `queryReplacement` con texto libre; ids unidos por `|`.
- **Capa:** nodo
- **Test:** `tests/test_media_fromme.js` (5a-5f)
- **Fecha/fuente:** 2026-09-05 · e1/EC-54, e3/EC-101, e4/EC-211 (parte coma)
- **Estado:** vigente

### INF-25 · pg-promise interpreta `$N` dentro de literales y `::` liga más fuerte que `||`
- **Entrada/disparador:** mensaje o caption con "$50.000"; INSERT con SQL de texto libre.
- **Falla previa:** "Variable $50 out of range"; un valor con `$` pegado a un cast queda como otro SQL.
- **Esperado:** armar el SQL con `esc()` (duplica comillas, saca `$`); envolver `(esc(v))::jsonb` si entra un valor libre; ninguna salida SQL con `$` crudo.
- **Capa:** nodo
- **Test:** `tests/test_triaje_nodos.js` ("sql sin $ crudo"), `tests/test_media_fromme.js`
- **Fecha/fuente:** 2026-09-05/07 · e4/EC-211 (parte pg-promise)
- **Estado:** vigente

### INF-26 · `queryReplacement` vacío: n8n no pushea `$1` y el smoke de Retención avisa falsa alarma por WhatsApp
- **Entrada/disparador:** smoke del satélite de retención con 0 vencidos: `ids=[]` → `queryReplacement ''` ("there is no parameter $1").
- **Falla previa:** "marcados NaN" → aviso de falla a Lucas en falso.
- **Esperado:** `Q_MARCAR_PARAM = ids.join('|') || '-'`; `resumen.js` no exige el UPDATE sin ids; advertencia (no fallido) si Storage devolvió 0 de N reales; el path fantasma del smoke no se cuenta; avisar a Lucas SOLO si falla.
- **Capa:** nodo
- **Test:** `tests/test_retencion_y_staff.js` (98/98)
- **Fecha/fuente:** 2026-09-07 madrugada · e1/EC-37, e3/EC-100 (parte 1)
- **Estado:** vigente

### INF-27 · Retención: starvation por bucket, delete markers y Vigía ciego
- **Entrada/disparador:** listar objetos para borrar en `storage.objects`; query del Vigía sobre tablas que pueden no existir.
- **Falla previa:** sin filtro por bucket otros objetos ocupaban el límite (starvation); `is_delete_marker` se listaba; el Vigía podía romper su query mientras `retencion_log` no existía y quedar ciego.
- **Esperado:** `Q_PACIENTES` filtra `bucket = 'pacientes-media'`; `Q_PANEL` excluye `is_delete_marker`; alerta `retencion_no_corrio` (26 h) con `to_regclass` + `query_to_xml`; alerta `vigia_query_rota` (la query no devolvió nada) con dedupe 24 h; `supabase_db_alto` >400 MB, `supabase_storage_alto` >800 MB. Satélite `Áurea — Retención`, cron 04:30 Jujuy.
- **Capa:** nodo (Vigía / Retención)
- **Test:** `tests/test_retencion_y_staff.js` (98/98)
- **Fecha/fuente:** 2026-09-07 madrugada · e1/EC-38
- **Estado:** vigente

### INF-28 · Borrar `storage.objects` por SQL deja el blob y sigue contando
- **Entrada/disparador:** retención de adjuntos (cron 04:30 Jujuy).
- **Falla previa:** el SQL borra la fila pero no el objeto físico, que sigue ocupando cuota.
- **Esperado:** borrar SOLO por API REST de Storage.
- **Capa:** nodo
- **Test:** `tests/test_retencion_y_staff.js` (cobertura general de Retención; no se cita una aserción específica: verificar)
- **Fecha/fuente:** 2026-09-07 · e3/EC-100 (parte 2)
- **Estado:** vigente

### INF-29 · Primer envío saliente de video por Evolution GO: formato desconocido y apikey hardcodeada vencida
- **Entrada/disparador:** primer envío de video (hasta entonces solo se había resuelto la recepción de media, 05/08). Triaje de urgencias con video.
- **Falla previa:** documentación inexistente; scripts viejos con apikey de Evolution hardcodeada vencida (401 "not authorized" en `/send/text` y `/send/media`).
- **Esperado:** `POST /send/media` `{number, type:"video", url, caption, filename}`; sin campo `instance`; `url` acepta base64 CRUDO (sin prefijo `data:`) o URL https (bucket público `urgencias-videos`); videos 3,9-5,1 MB H.264/AAC 720x1280 sin comprimir. El script extrae la clave en caliente del nodo "Evolution API - Enviar Mensaje" del v6; NUNCA hardcodear.
- **Capa:** nodo / infra (credenciales)
- **Test:** `scripts/test_evo_go_send_video.py`
- **Fecha/fuente:** 2026-09-02 · e1/EC-74
- **Estado:** vigente

### INF-30 · `/send/media` de Evolution GO: `type:'ptt'` devuelve 500, tipo desconocido caía a `image`
- **Entrada/disparador:** audio/imagen/video/documento desde el panel o el triaje.
- **Falla previa:** `ptt` → 500 "invalid media type"; no existe `/send/audio`; antes un tipo desconocido con URL caía a `image` y mandaba una URL `.mp3` como imagen a un paciente real; una respuesta OK debe verificarse porque continueOnFail puede ocultar un jsonBody roto.
- **Esperado:** `audio` → 200 (verificado 7/9); tipos válidos image/video/document/audio; `Validar secreto` responde 400 `media_tipo invalido` y 401 sin secreto; verificar `data.Info.Type==='VideoMessage'` tras enviar; WhatsApp reproduce mp3/m4a/ogg-opus (webm no confiable en iOS: el panel manda siempre MP3 mono 64 kbps). Abierto: no se sabe si `/send/media` rebota como fromMe (solo se verificó `/send/text`).
- **Capa:** nodo (satélite Panel — acciones staff, Triaje: Enviar Video)
- **Test:** `tests/test_retencion_y_staff.js` (Validar secreto: audio aceptado, tipos inválidos, mime en vez de tipo, filename saneado, secreto incorrecto, toggle)
- **Fecha/fuente:** 2026-09-07 · e4/EC-209, e3/EC-100 (parte 5)
- **Estado:** vigente; sub-pendiente: rebote fromMe de `/send/media` sin verificar

### INF-31 · Secretos hardcodeados, webhooks sin auth y `scratch/` fuera del .gitignore
- **Entrada/disparador:** revisión de seguridad (2026-06-02 y 2026-09-07).
- **Falla previa:** JWT service_role de Supabase hardcodeado en 3 nodos del v6 (exp 2089, saltea RLS) y en querystring de URLs; token de Chatwoot hardcodeado en 14+ lugares (Gate Humano Final, fallback de Chatwoot Apply, scripts); apikey de Evolution en 5 nodos; token de Dentalink dentro de los backups PRE/POST de `workflows/history` y en `scratch/test_node.js` (28/07); `scratch/` NO está en .gitignore (`git add .` lo commitea); la API key de n8n quedó en historial de chats.
- **Esperado:** rotar y migrar a credenciales nativas (supabaseApi, httpHeaderAuth); no copiar nodos con valores literales a scripts nuevos; no mandar backups por Slack/mail sin limpiar; ignorar `scratch/`; el token de Dentalink sale del jsCode (ver INF-37).
- **Capa:** infra (higiene / credenciales)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-02 / 2026-07-06 / 2026-09-07 · e4/EC-212
- **Estado:** pendiente de decisión (rotación). Nota: `git status` actual muestra `scratch/` sin trackear.

### INF-32 · Fix @lid: cadena de candidatos y fallback idéntico al legacy (Evolution clásica)
- **Entrada/disparador:** ~7 % de DMs reales sin teléfono por `@lid` (exec 193142); evidencia 527 execs + Evolution 2.3.7 + Baileys v7.
- **Falla previa:** `@lid` sin teléfono.
- **Esperado:** primer candidato que termine en `@s.whatsapp.net` entre `remoteJid → remoteJidAlt → senderPn → participantAlt → participant`; si ninguno, EXACTAMENTE lo del código viejo.
- **Capa:** nodo
- **Test:** "5/5 tests PASS" (sin archivo citado): SIN TEST en tests/
- **Fecha/fuente:** 2026-07-06 · e3/EC-99
- **Estado:** superado por INF-01 (2026-08-05, Evolution GO): la cadena vigente es `Chat → Sender → RecipientAlt → SenderAlt`; la lista de campos de Baileys/Evolution clásica ya no aplica. El principio (probar candidatos y exigir `@s.whatsapp.net`) sigue.

### INF-33 · `MESSAGES_UPDATE` genera ~85 % del tráfico basura y los `@lid` masivos eran receipts
- **Entrada/disparador:** eventos `messages.update` (ACKs) y mensajes con `@lid`.
- **Falla previa:** ~85 % del tráfico del v6 son ACKs que mueren en el Validator pero inflan la DB interna de n8n; el susto de que "@lid es mayoría del tráfico" eran receipts, no pacientes.
- **Esperado:** quitar `MESSAGES_UPDATE` de los eventos de la instancia `raquel` (config externa de Lucas); NUNCA tocar la URL del webhook (`evo-webhook-v2`).
- **Capa:** infra (config Evolution)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06/18 · e4/EC-208
- **Estado:** pendiente de decisión. La fuente es anterior a la migración a Evolution GO (2026-08-05); verificar si la config aplica al evento equivalente de GO.

### INF-34 · Orden de despliegue de adjuntos: panel nuevo → tabla → v6
- **Entrada/disparador:** aplicar la cadena Media del v6 antes de que el panel conozca el token `[MEDIA:id]`.
- **Falla previa:** el panel actual mostraría el token crudo al staff.
- **Esperado:** panel nuevo ANTES; luego `create_media_entrantes.py --apply`, reinicio del panel (escucha `media`), `apply_media_entrantes.py --apply`, prueba real con limpieza (regla 9); verificación post-apply obligatoria (`prepareBinaryData`/`RETURNING *`).
- **Capa:** infra (proceso de despliegue)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-06 noche · e1/EC-47
- **Estado:** vigente (aplicado en v6 el 2026-09-07 según current-state)

### INF-35 · Merge v3 con entrada declarada sin conexión y Task Runners con `Buffer` (cadena Media)
- **Entrada/disparador:** `Merge Multimedia` pasa de 5 a 2 entradas al insertar la cadena Media; `prepareBinaryData` y `Buffer` en Code nodes sin precedente en la instancia.
- **Falla previa (riesgo):** sin evidencia del caso "entrada declarada sin conexión"; con Task Runners el Buffer viaja por RPC; la fila de ejecución en SQLite pesa ~6× el base64; si `hay_archivo` es false con motivo `error:*` el feature queda apagado en silencio.
- **Esperado:** reproducir el patrón probado (numberInputs 2 con ambas entradas conectadas); verificación obligatoria en la PRIMERA ejecución real: salida de `Media: Preparar` (`hay_archivo`) y `Media: Registrar` (fila `RETURNING *`); retención de ejecuciones ~72 h.
- **Capa:** nodo + infra (verificación post-apply)
- **Test:** `tests/test_media_nodos.js`
- **Fecha/fuente:** 2026-09-06 · e4/EC-214
- **Estado:** vigente

### INF-36 · Recordatorios: orden DDL → apply y límite de insertar nodos
- **Entrada/disparador:** agregar columnas `motivo_atencion` / `es_consulta` a `recordatorios_enviados` y subconsulta de precio (recordatorio distinto para consultas).
- **Falla previa (riesgo):** el Postgres v2.6 valida contra la tabla viva y el Insert corre después del envío: sin columnas, el recordatorio se envía pero falla el registro. No se puede insertar un nodo entre `Solo citas activas` y `Preparar mensaje` (emparejamiento por `$itemIndex`). `motivo_atencion || null` no se aplicó por no poder probar el null punta a punta.
- **Esperado:** orden obligatorio `--ddl` → `--apply`; `--rollback` solo acepta un PRE (un POST re-aplicaría); `flag_vivo()` con mensaje claro si falta la línea TEST_MODE. Recordatorios (`7RqTApkvVavRmq3R`) es workflow que NO se toca sin necesidad.
- **Capa:** nodo / infra (script de apply)
- **Test:** `tests/test_recordatorio_consultas.js`
- **Fecha/fuente:** 2026-09-08 · e1/EC-22
- **Estado:** vigente

### INF-37 · Buscar horarios: hasta 91 llamadas / ~80 s y token de Dentalink dentro del jsCode
- **Entrada/disparador:** búsqueda de agenda en `Sub-WF - Buscar Horarios Validado`.
- **Falla previa:** hasta 91 llamadas a Dentalink (~80 s) y token de Dentalink embebido en el jsCode.
- **Esperado:** 6 → 22 nodos con paginación por cursor en httpRequest con la credencial "Header Auth account 3"; techo de 6 llamadas (~2 s típico); el token sale del jsCode.
- **Capa:** nodo
- **Test:** `tests/test_turnos_formato.js`
- **Fecha/fuente:** 2026-09-07 · e1/EC-28
- **Estado:** vigente

### INF-38 · Offset de cron de n8n (recordatorios a las 7 AM en vez de 9 AM)
- **Entrada/disparador:** recordatorios llegaban 7 AM en vez de 9 AM (~abril 2026, BUGS #10).
- **Falla previa:** el timezone del server acumula un offset de -2 h aparentes.
- **Esperado:** según la fuente, "cron Arg = (hora_arg + 5) UTC; estable sin DST" (valor textual de la fuente, no coincide con UTC-3 estándar: re-verificar contra el cron vivo; el recordatorio hoy dispara 9 AM Arg y FUNCIONA). Para Retención: verificar si `settings.timezone` se respeta (04:30 ART esperado).
- **Capa:** nodo (cron)
- **Test:** SIN TEST
- **Fecha/fuente:** ~2026-04 · e3/EC-97 (BUGS #10; BKL P2 Retención)
- **Estado:** pendiente de decisión (verificación de `settings.timezone` en Retención)

### INF-39 · Reportero Semanal con métricas alucinadas y conteos erróneos de escalaciones
- **Entrada/disparador:** reporte semanal a la Dra. (score 6/10), "agrego items al KB" falso.
- **Falla previa:** la definición de escalación incluye fromMe/receipts, roles mal categorizados, lee solo `escalaciones_log` (7 días); n8n retiene ~72 h de ejecuciones; fuente desconocida (¿Logger/Supabase?).
- **Esperado:** excluir fromMe/receipts y validar conteos; Reportero v2 "aprendizaje semanal" (construido y probado 2026-08-11): decir ESPECÍFICAMENTE qué información falta añadir a la KB, mapear las urgencias (scoring) desde `triaje_urgencias_log` y mandar al grupo; casos muy graves → aviso inmediato; auditar la fuente.
- **Capa:** nodo (Reportero Semanal `MJ38kSTRZDPgPCCy`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06 / 2026-07-14 / 2026-07-17 / 2026-08-11 / 2026-08-15 · e3/EC-102, e4/EC-215
- **Estado:** vigente (v2 absorbió el pendiente; auditoría de fuente sin confirmar)

### INF-40 · Reportero Semanal: gpt-5-nano rechaza `temperature` custom
- **Entrada/disparador:** primer test del workflow nuevo (2026-08-11). Error: "Only the default (1) value is supported".
- **Falla previa:** el body incluía `temperature`.
- **Esperado:** sin `temperature` en el body del modelo gpt-5-nano.
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-11 · e2/EC-25
- **Estado:** vigente

### INF-41 · Reportero: copia 1:1 de las regex de `lib/escalaciones.ts` (riesgo de drift con el panel)
- **Entrada/disparador:** el nodo `Clasificar y Agrupar` duplica las regex señal/ruido/operativo del panel.
- **Falla previa (riesgo):** editar un lado sin el otro desincroniza `/aprendizaje` y el reporte.
- **Esperado:** si se edita un lado, editar el otro.
- **Capa:** infra (convención)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-11 · e2/EC-27
- **Estado:** vigente

### INF-42 · Error aislado de OpenAI en el triaje (exec 286089) como ruido conocido de `check_triaje.py`
- **Entrada/disparador:** error de OpenAI único el 2026-09-24 (exec 286089).
- **Falla previa:** único ❌ que sigue apareciendo en `check_triaje.py`, ya resuelto, sin ejecuciones con error desde entonces.
- **Esperado:** el Vigía (B) alerta ante ejecuciones con error del v6 en 20 min y el triaje (A) ante `error_llm`/`config_no_disponible`/`envio_fallo`/`NOTIFY_FALLO`; considerar ruido conocido del chequeo.
- **Capa:** infra (monitoreo: Vigía + `check_triaje.py`)
- **Test:** `scripts/check_triaje.py`
- **Fecha/fuente:** 2026-09-30 · e1/EC-78
- **Estado:** vigente

### INF-43 · GitHub Actions bloqueado por billing y `deploy.yml` desactualizado (deploy del panel)
- **Entrada/disparador:** `startup_failure` hasta con un `echo hola`; `deploy.yml` describe el enfoque systemd/standalone viejo y el deploy real es Docker+Traefik.
- **Falla previa:** el CI/CD no despliega.
- **Esperado:** redeploy manual con `deploy/redeploy.sh`; si se reactiva Actions, reescribir el job a `docker compose`.
- **Capa:** infra
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-22 (y 2026-08-09/10) · e2/EC-65
- **Estado:** vigente

### Cobertura
43 casos; 26 SIN TEST (INF-04, 05, 07, 08, 09, 10, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 23, 31, 32, 33, 34, 38, 39, 40, 41, 43), 4 con cobertura solo parcial (INF-01, 13, 22, 28) y 13 con test.
Huecos más peligrosos: (1) INF-01/02/03: la batería E2E (`test_e2e_bateria.py`) usa el shape viejo y no hay test unitario de los 4 nodos de entrada, así que una regresión del Validator vuelve a dejar al bot mudo sin que nada falle; (2) INF-04/05/22: ningún test detecta JSON roto en `Enviar Mensaje`, expresiones con mustache anidado ni nodos Redis/Chatwoot sin continueOnFail (bot mudo o escalaciones muertas en silencio); (3) INF-18/19/20/31: PUT sin `webhookId`, snapshot viejo, sesiones concurrentes y secretos hardcodeados dependen solo de disciplina de proceso, sin chequeo automático.

---

## panel

### PAN-01 · El panel NUNCA pudo enviar mensajes ni togglear el bot (se afirmó lo contrario)
- **Entrada/disparador:** Lucas vio "El panel todavía no está conectado al servidor del bot." (2026-09-05); staff escribe en el panel / toggle bot.
- **Falla previa:** las server actions POSTean a `panel-send-human` / `panel-toggle-bot`, que NO existían en n8n (63 workflows revisados), y `/opt/nexora-panel/.env.production` no tenía `N8N_PANEL_WEBHOOK_BASE` / `SECRET`. El 2026-09-02 se le dijo a Lucas (y él a la Dra.) que el panel enviaba y togglaba; solo se había leído el código de la UI.
- **Esperado:** regla dura 8: nunca afirmar que una feature "funciona" sin ejecutar el camino completo UI → backend → efecto real. Contrato: `POST /webhook/panel-toggle-bot` (Redis + `pacientes.human_takeover`) y `/webhook/panel-send-human` con header `x-panel-secret` (porque Evolution/Redis son VPS-only). Satélite `Panel — acciones staff` (`jzxb5zUKCaJcvCgp`): `Validar secreto` → 401 o `/send/text` → `¿Enviado?` (502 si Evolution falla) → fila en `n8n_chat_histories` (`[ATENCION HUMANA … desde el PANEL]`, `wa_outbound`, `from_panel:true`) → label Chatwoot → 200. Probado: secreto malo 401, envío real 200, toggle false/true/false 200.
- **Capa:** nodo (satélite) + infra (proceso, regla dura 8)
- **Test:** `tests/test_retencion_y_staff.js` (Validar secreto); E2E manual 401/200/200
- **Fecha/fuente:** 2026-09-02 (afirmación errónea), 2026-09-05 (descubierto/construido) · e1/EC-51, e3/EC-103, e4/EC-216
- **Estado:** vigente (corregido 2026-09-05)

### PAN-02 · Botón masivo "Devolver todos al bot": exclusión de `no_bot`, fail-closed y aviso honesto
- **Entrada/disparador:** click en "Devolver todos al bot" con N chats en modo humano.
- **Falla previa:** (3 MUST_FIX de la revisión del 10/9) `HUMANO_MS` en 1 h; el filtro `no_bot` solo documentado, no implementado; el aviso decía "Se devolvieron 3 chats" aunque 2 de 5 fallaron.
- **Esperado:** `telefonosConNoBot()` consulta Chatwoot (`?labels[]=no_bot&status=open`, match por sufijo de 10 dígitos) y excluye esos chats; sin env vars `CHATWOOT_*` el chequeo se saltea; con env vars y Chatwoot caído → aborta el botón entero (fail-closed); aviso "N de M chats", ámbar si parcial, más "X quedaron afuera por pin manual (no_bot)"; lotes de 5 en paralelo reusando `/panel-toggle-bot`; botón deshabilitado con `actionPending`.
- **Capa:** infra (código del panel Next.js) + nodo (`/panel-toggle-bot`)
- **Test:** SIN TEST (solo `tsc --noEmit`)
- **Fecha/fuente:** 2026-09-10 · e4/EC-217 (docs/handoff-humano-24h-2026-09-10.md §8-§9)
- **Estado:** vigente; sub-pendiente: `botActive` es proxy heurístico de v3 (no lee el label real), no resuelto

### PAN-03 · La Dra. no podía guardar en Conocimiento/Servicios: falso positivo del guard de precios
- **Entrada/disparador:** audios/WhatsApp de la Dra.: al editar "Valor de la primera consulta" el panel rechazaba con "No se publican precios de tratamientos (se evalúan en consulta). Consulta y cuota mensual sí." Texto: "la consulta vale $50.000" + "el valor de los tratamientos... se define en consulta".
- **Falla previa:** `pareceTratamientoConPrecio()` chequeaba el TEXTO COMPLETO; una palabra de tratamiento (`bracket|ortodoncia|alineador|invisalign`) en cualquier parte más un "$" con número en otra bloqueaba sin relación entre ambos.
- **Esperado:** regla de la reunión 14/7 ("nunca precio fijo de tratamiento") evaluada por ORACIÓN (`split(/[.!?\n]+/)` + `.some`): bloquea solo si tratamiento y precio van en la MISMA oración. "el bracket cuesta $50.000 fijo" SIGUE bloqueando; el ejemplo de la consulta guarda OK. "ortodóncico" con acento no matchea (inofensivo, no se tocó). Mismo patrón que el Canned Sidecar.
- **Capa:** infra (server action del panel, `app/(app)/conocimiento/actions.ts`)
- **Test:** SIN TEST (3 casos a mano); el patrón del Canned Sidecar está en `tests/test_canned_sidecar.py` pero no cubre la server action
- **Fecha/fuente:** 2026-09-02 · e2/EC-5, e3/EC-104 (deploy `173c8b8`)
- **Estado:** vigente
- **Riesgo de regresión:** la regla "nunca precio fijo de tratamiento; consulta y cuota mensual sí" también vive en el prompt de General y en los gates del bot; tras la curación del 2026-10-04 verificar que General no pierda "tratamientos sin precio publicado" y que siga respondiendo el valor de consulta vía `precio_consulta`.

### PAN-04 · Toggle bot/humano por conversación no es inmediato (~30 min)
- **Entrada/disparador:** demo del panel a la Dra. el 2026-08-15.
- **Falla previa:** el toggle tarda ~30 min en confirmarse; gap señalado por la Dra.
- **Esperado:** el toggle se refleja de inmediato (confirmar con un toggle real antes de asegurarle que anda al 100%; el 2/9 solo se verificó el código). Banner rojo persistente cuando el bot está apagado y confirmación al apagarlo.
- **Capa:** infra (webhooks `panel-toggle-bot` / `panel-send-human`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-15 y 2026-09-02 · e2/EC-23
- **Estado:** pendiente de decisión (el toggle del 2026-09-05 dio 200, pero la latencia de ~30 min no se re-midió)

### PAN-05 · Token de adjunto del staff se pierde para siempre por la carrera del Logger
- **Entrada/disparador:** el Logger (cron 5 min) copia `n8n_chat_histories` → `conversaciones` con `ignore-duplicates` y nunca corrige; si cae en la ventana INSERT→UPDATE (~1,4 s por foto, hasta 30 s por video), `conversaciones` queda sin token.
- **Falla previa:** el dedup por timestamp del panel descarta la fila de memoria que sí tiene el token; la foto no aparece nunca más (ni con F5). ~1 perdido cada 2 semanas (14,7 adjuntos fromMe/día).
- **Esperado:** `rescatarTokensMedia` (`lib/media-entrantes.ts`, llamado desde `chat-data.ts` y `conversaciones-data.ts`) le pasa a la fila de `conversaciones` los tokens de la memoria antes de descartarla; idempotente; sin tocar n8n.
- **Capa:** infra (código del panel)
- **Test:** SIN TEST (`npx tsc --noEmit` limpio)
- **Fecha/fuente:** 2026-09-07 tarde · e1/EC-34
- **Estado:** vigente

### PAN-06 · Mensajes de staff (`wa_outbound`) atribuidos a "Asiri" con marcador crudo `[ATENCION HUMANA ...]`
- **Entrada/disparador:** captura real de Lucas: el chat mostraba el marcador crudo y el label verde "Asiri" en vez de "Dra. Raquel" (azul).
- **Falla previa:** `chat-view.tsx` tenía el guard `!esBotFuente &&` antes de chequear `metadata.source === "wa_outbound"`; el Logger marca `fuente: "bot"` para CUALQUIER fila `type: "ai"`, incluidas las notas de relay humano.
- **Esperado:** `source: wa_outbound` (solo lo escribe `Build fromMe AI memory`, rama `fromMe=true`) es señal exclusiva: se atribuye al staff y no se muestra el marcador crudo. Guard quitado.
- **Capa:** infra (código del panel)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-09/10 · e2/EC-39
- **Estado:** vigente

### PAN-07 · Mensaje del paciente tardaba 30-45 s en verse (memoria LangChain escribe al final del turno)
- **Entrada/disparador:** Lucas veía el panel "sin actualizar" (2026-09-05 ~20:15 ART).
- **Falla previa:** la fila `human` la escribe LangChain al final del turno: latencia inherente de 30-45 s.
- **Esperado:** nodo Postgres `Inbox Live` (rama muerta de `Edit Fields - Extraer Datos`, `onError: continue`, no afecta el flujo principal) inserta cada mensaje crudo en `mensajes_entrantes_live` (~1,3 s); el panel lo mergea como burbuja pendiente (dedup por texto en ventana de 5 min; `from_me` se ignora); SSE + Supabase Realtime. Buffer de 22 s: bajarlo arriesga 2 burbujas = 2 turnos (clase Confirmar/alias). Insert por `defineBelow` (ver INF-24).
- **Capa:** nodo + infra (código del panel)
- **Test:** E2E manual (fila a 1,3 s del webhook, `scripts/apply_inbox_live.py`): SIN TEST automatizado
- **Fecha/fuente:** 2026-09-05/06 · e1/EC-53, e3/EC-105
- **Estado:** vigente

### PAN-08 · Tail "en vivo" traía los 60 mensajes MÁS VIEJOS
- **Entrada/disparador:** "el panel anda choto: no se actualiza sin F5" (Lucas, 2026-09-05), en conversaciones con >60 filas de memoria (13 de 240 sesiones).
- **Falla previa:** `lib/chat-data.ts` pedía `order id ASC + limit 60`; los mensajes nuevos nunca entraban al polling y aparecían recién cuando el Logger los copiaba (hasta 5 min). La lista lateral ya usaba DESC.
- **Esperado:** orden DESC en el tail del chat.
- **Capa:** infra (código del panel)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-05 · e1/EC-52 (commit `cc642c7`), e3/EC-105 (parte)
- **Estado:** vigente (corregido)

### PAN-09 · Adjunto del paciente solo aparece tras F5 (pestaña congelada)
- **Entrada/disparador:** prueba real de Lucas 2026-09-07 02:24-02:27 (foto con caption "test", exec 272189; audio, exec 272191): "funciona igual tuve q apretar F5".
- **Falla previa:** ninguna pestaña conectada al stream SSE (primer cliente 02:25:47, foto 02:24:51); pestaña en segundo plano congelada por Chrome o panel cerrado. En local el INSERT llega en 359 ms.
- **Esperado:** al volver la pestaña a visible, si no llegó ningún ping en 25 s se reabre el stream al instante y se hace catch-up (antes esperaba el watchdog de 45 s).
- **Capa:** infra (código del panel)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-07 madrugada · e1/EC-46
- **Estado:** pendiente de decisión (que Lucas repita con la pestaña abierta)

### PAN-10 · Realtime/SSE: posible corte cada 60 s por Traefik y respuestas fuera de orden
- **Entrada/disparador:** stream SSE `/api/live` detrás de Traefik 3 (`respondingTimeouts.readTimeout` 60 s por default); refetches concurrentes.
- **Falla previa:** en HTTP/1.1 podría cortar el stream cada 60 s (el cliente reconecta en 2 s: degradación, no rotura); respuestas fuera de orden en chat/lista (must-fix de revisión).
- **Esperado:** secuencia en el chat y serialización en la lista; fallback al polling viejo; poll de seguridad 20/30 s. Si Traefik corta: `readTimeout=0` (reiniciar Traefik corta n8n/Chatwoot unos segundos → pedir OK a Lucas).
- **Capa:** infra (código del panel / Traefik)
- **Test:** SIN TEST (latencias medidas en local 201/492/486 ms)
- **Fecha/fuente:** 2026-09-06 tarde · e1/EC-48, e3/EC-105 (parte)
- **Estado:** pendiente de decisión (verificar en prod)

### PAN-11 · Nombre del contacto "cambia solo" y fichas de prueba duplicadas
- **Entrada/disparador:** Lucas (screenshot 2026-09-06): "nombres falopa". El chat mostraba "Test - Jana Test" y la lista "Antonio Manuel": dos fichas de prueba en Dentalink con su celular.
- **Falla previa:** el nombre cambiaba a la hora por una ventana de 60 min del pushName; nombres inconsistentes entre lista y chat.
- **Esperado:** `displayName` = alias manual > Dentalink > pushName real > ficha > teléfono; pushName desde `mensajes_entrantes_live.push_name` vía `lib/push-names.ts` (sin ventana); alias manual por número resuelve el caso; mismo nombre en lista y chat.
- **Capa:** infra (código del panel)
- **Test:** verificación manual 12/12 casos de `displayName/displayAutor` (sin archivo): SIN TEST automatizado
- **Fecha/fuente:** 2026-09-06 · e1/EC-49, e1/EC-50 (punto 2)
- **Estado:** vigente

### PAN-12 · Revisión previa al deploy del panel "como WhatsApp Web": autor histórico y tope de upload
- **Entrada/disparador:** revisión del panel (2026-09-06) antes del deploy. Tres bugs reales; el de nombres es PAN-11.
- **Falla previa:** (1) autor histórico: placeholder "la doctora o la secretaria" en mensajes del panel anteriores al 6/9; (3) tope real del upload (`proxyClientMaxBodySize`).
- **Esperado:** el placeholder histórico se muestra como "Dra. Raquel"; `requireUser()` devuelve el login como autor ("Lucas"/"Irina"/"Dra. Raquel"); frontal es Traefik (no nginx), sin 413 de proxy; `enviarImagenAction` valida magic bytes y borra el objeto si n8n rechaza.
- **Capa:** infra (código del panel)
- **Test:** tsc + diff de actions; SIN TEST dedicado
- **Fecha/fuente:** 2026-09-06 · e1/EC-50 (puntos 1 y 3)
- **Estado:** vigente

### PAN-13 · Caption duplicado en la burbuja pendiente de un adjunto
- **Entrada/disparador:** adjunto del paciente con caption mientras la burbuja está PENDIENTE.
- **Falla previa:** el caption se mostraba duplicado (fallback a `media_entrantes.caption`).
- **Esperado:** el fallback solo aplica si el texto no trae nada suelto (`captionFila` en `AdjuntosBlock`); preview "📷 Foto · caption" también en la burbuja pendiente; foto-como-archivo sin chip redundante.
- **Capa:** infra (código del panel)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-06 noche · e1/EC-44 (MUST_FIX 1)
- **Estado:** vigente

### PAN-14 · Chip "adjunto vencido" mostrado ante cualquier falla de reproducción
- **Entrada/disparador:** adjunto del paciente o del staff que no se puede reproducir (>90 días, o nota ogg/opus en Safari).
- **Falla previa:** se marcaba vencido ante fallas que no eran 404/410 (Supabase responde `400 {"statusCode":"404"}` para objeto ausente); `MediaError.code` = 4 cubre 404, 410, corrupto y contenedor no soportado; el `onError` de `<audio>/<video>/<img>` no distingue borrado de "este navegador no lo reproduce"; un UPDATE de `borrado_at` no dispara evento en vivo (el bus escucha solo INSERT).
- **Esperado:** `/api/media/<id>` responde 410 Gone si `borrado_at` no es null (404 = no existe); chip "Adjunto vencido (se guardan 90 días)" solo con 404/410 confirmado por el servidor (`clasificarFalla`: HEAD sin seguir el 302 / GET de 1 byte); el resto muestra chip neutro "No se pudo reproducir acá · abrir"; `<audio>` del staff `preload="none"`.
- **Capa:** infra (código del panel + ruta `/api/media`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-07 · e1/EC-42, e4/EC-221, e3/EC-100 (parte 3)
- **Estado:** vigente

### PAN-15 · Micrófono: doble click o cambio de chat dejaba un stream grabando
- **Entrada/disparador:** doble click en el micrófono o cambio de chat con el prompt de permiso abierto.
- **Falla previa:** quedaba un stream de audio grabando (fuga del micrófono).
- **Esperado:** lock síncrono (`iniciandoRef`/`montadoRef`); el mic se oculta solo si `permissions.query` da `denied`; `NotSupportedError` prueba el siguiente mime.
- **Capa:** infra (código del panel)
- **Test:** SIN TEST (`tsc` y `pnpm build` verdes; falta prueba real Chrome/iPhone/Android)
- **Fecha/fuente:** 2026-09-07 madrugada · e1/EC-40
- **Estado:** pendiente de decisión (prueba real en dispositivos)

### PAN-16 · Audio con headset Bluetooth a 8 kHz generaba MPEG-2.5 que el server rechazaba
- **Entrada/disparador:** grabación con headset BT a 8 kHz; Safari/AAC o webm/opus (`new AudioContext()` toma 8 kHz; lamejs codifica MPEG-2.5).
- **Falla previa:** el server rechazaba el MPEG-2.5; webm no es confiable en iOS; `/send/media` con `type: ptt` → 500 (ver INF-30).
- **Esperado:** formato ÚNICO MP3 mono 64 kbps 48 kHz (`OfflineAudioContext` a 48 kHz; webm/opus y AAC se transcodifican); el server acepta cualquier sync de capa III; `video/*` rechazado salvo OGG con Opus/Vorbis; `media_tipo` inválido = 400. Motivo: Evolution GO no tiene ptt y WhatsApp reproduce mp3 en todos los teléfonos.
- **Capa:** infra (código del panel) + nodo (`Validar secreto`)
- **Test:** `tests/test_retencion_y_staff.js` (parcial); falta verificar que suene en iPhone/Android (P2)
- **Fecha/fuente:** 2026-09-07 madrugada · e1/EC-41, e3/EC-100 (parte 4)
- **Estado:** vigente

### PAN-17 · Audio del staff: orden de despliegue (satélite antes que panel), tipo `image` por defecto y filename largo
- **Entrada/disparador:** audio grabado desde el panel enviado al celular de un paciente.
- **Falla previa:** el panel viejo siempre manda `media_tipo: image`; si el satélite vivo tiene el `Validar secreto` viejo, un audio del panel nuevo cae a `image` y `Enviar Media (staff)` hace `/send/media type: image` con una URL `.mp3`; filename largo perdía la extensión.
- **Esperado:** desplegar el satélite (acepta audio, 400 ante tipo desconocido) ANTES que el panel; filename saneado a `[A-Za-z0-9._-]` máx 80 chars conservando la extensión; 401 sin secreto y 400 con el error en el body; la fila de memoria es `[audio] <url>` + `\n` + caption y la lista muestra "🎤 Audio · caption".
- **Capa:** nodo (`Validar secreto` / `Armar fila memoria`) + infra (orden de despliegue)
- **Test:** `tests/test_retencion_y_staff.js` (Validar secreto, Armar fila memoria: audio/imagen/video/document/texto)
- **Fecha/fuente:** 2026-09-07 · e4/EC-220 (docs/retencion-y-uso-2026-09-07.md §6, §8)
- **Estado:** vigente

### PAN-18 · Guardar KB sin `OPENAI_API_KEY` dejaba `embedding=NULL` y el bot dejaba de encontrar la entrada
- **Entrada/disparador:** guardar una entrada en `/conocimiento` sin key de embeddings; fila id 28 "menores".
- **Falla previa:** el embedding quedaba NULL y `buscar_conocimiento` no la encontraba.
- **Esperado:** si no se puede re-embeddar, se OMITE la columna (se preserva el vector). Fila re-embebida con `reembed_kb_nulls.py` (0 NULL, sale #1 con sim 0.765 para "¿atienden niños?"). Re-embedding al guardar con text-embedding-3-small, formato "categoria | titulo\ncontenido".
- **Capa:** infra (código del panel)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-19 · e2/EC-52
- **Estado:** vigente
- **Riesgo de regresión:** el plan v7 desconecta `buscar_conocimiento` (RAG contaminado); si la KB sigue alimentando el bot, la entrada "menores" debe ser accesible por el camino vigente (General curado el 2026-10-04 o canned/KB dinámico), no solo por RAG.

### PAN-19 · Turno nuevo no se veía en el chat porque caía en otra ficha del mismo celular
- **Entrada/disparador:** un celular con varias fichas en Dentalink.
- **Falla previa:** el panel solo traía la 1.ª ficha; el turno que reserva el bot caía en otra.
- **Esperado:** agregar turnos de TODAS las fichas del celular (`pacientesByCelular`); `id_paciente` no es filtrable en `/citas`, usar `/pacientes/{id}/citas`.
- **Capa:** infra (código del panel)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-19 · e2/EC-53
- **Estado:** vigente

### PAN-20 · Acciones Confirmar/Cancelar del cockpit escriben en Dentalink y no son autoprobables
- **Entrada/disparador:** `PUT /citas/{id}` (`id_estado` 1=Anulado, 22=Confirmado) desde el cockpit al click del staff.
- **Falla previa (riesgo):** el clasificador bloquea escrituras a Dentalink, así que no se pudo probar.
- **Esperado:** modal de confirmación en 2 pasos; confirmación al apagar el bot y banner rojo persistente cuando está apagado (salvaguardas del incidente).
- **Capa:** infra (código del panel)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-18/19 · e2/EC-54
- **Estado:** pendiente de decisión (sin prueba real contra Dentalink)

### PAN-21 · Un video del bot no aparece en el chat del panel salvo que se inserte una fila en memoria
- **Entrada/disparador:** video enviado por `/send/media` desde el triaje.
- **Falla previa:** no deja rastro en ninguna tabla; el Logger pone `metadata.type='ai'`, no copia URLs y `detectMedia` solo reconoce `[video]` si el mensaje entero lo es → el caption se ve como texto plano; `source='reminder_note'` mapea a rol system y desaparece; `Check Humano Reciente (DB)` mira solo la última fila (una `triaje_video` posterior a un `wa_outbound` ocultaría la atención humana).
- **Esperado:** INSERT en `n8n_chat_histories` con `{type:'ai', content: caption, additional_kwargs:{source:'triaje_video'}}` → burbuja verde "Asiri"; chip "Video" con link = 2 cambios chicos (no bloqueante); carve-out `[TRIAJE VIDEO]` en /aprendizaje; la fila NO debe ocultar la atención humana previa.
- **Capa:** nodo + infra (panel)
- **Test:** SIN TEST (`tests/test_triaje_nodos.js` cubre el triaje en general; esta aserción de panel no está citada)
- **Fecha/fuente:** 2026-09-04 · e4/EC-219 (mapeo-read_data_panel.md KEY FACTS)
- **Estado:** pendiente de decisión (los "2 cambios chicos" del chip no confirmados como aplicados)

### PAN-22 · Diseño de datos del panel: formato de teléfono, humano real vs auto-silencio, métricas sin fuente
- **Entrada/disparador:** lectura directa del Supabase v3 por teléfono (plan 2026-07-18).
- **Falla previa:** panel usa "+549…", v3 "549…"; el panel no distingue "humano real" de "auto-silencio"; "minutos ahorrados" sin fuente real (vanity); "citas bot vs manual" requiere un log que no existe en el sub-WF Agendar; leído/no-leído no existe en ningún schema (`pacientes.panel_last_read_at` fuera de `rebuild_v3_schema.sql`); `ENCRYPTION_KEY` del espejo la tiene Valentino.
- **Esperado:** normalización única de teléfono; dual-cliente sin espejo (lee el v3 directo); polling 3-5 s en vez de Realtime (luego SSE, ver PAN-07/10); KB editable con re-embedding al guardar y guardrail "tratamientos sin precio publicado".
- **Capa:** infra (diseño del panel)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-18 · e4/EC-218 (docs/plan-dashboard-2026-07-18.md; mapeo-read_data_panel.md)
- **Estado:** vigente; "polling 3-5 s" superado por SSE + Supabase Realtime (2026-09-06, PAN-07/10)

### PAN-23 · Panel viejo olvidado (`dra-raquel-dashboard`) ocupaba el dominio del panel
- **Entrada/disparador:** `dra-raquel-dashboard` (del 2026-05-20, basic-auth) en `panel.raquelrodriguez.com.ar` (2026-07-22).
- **Falla previa:** dos paneles compitiendo por el dominio.
- **Esperado:** apagado con `docker stop` (rollback con `docker start`); panel nuevo con cookie HMAC firmada + scrypt, vencimiento 7 d y `mem_limit 512m` para no competir con el bot.
- **Capa:** infra
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-22 · e2/EC-63
- **Estado:** vigente

### PAN-24 · Secretos pegados en el chat (a rotar)
- **Entrada/disparador:** la `OPENAI_API_KEY` de Lucas (2026-07-19) y la contraseña del panel (2026-07-22) pasaron por el chat; un token `ghp_…` filtrado en el git config del panel viejo del server (visto 2026-08-05).
- **Falla previa:** credenciales expuestas.
- **Esperado:** rotar los tres; regla dura: nunca pegar valores reales en el repo ni en el chat.
- **Capa:** infra (proceso)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-19, 2026-07-22, 2026-08-05 · e2/EC-64
- **Estado:** pendiente de decisión (rotaciones pendientes de Lucas)

### Cobertura
24 casos; 21 SIN TEST automatizado (PAN-11 y PAN-12 solo tienen verificación manual/tsc); solo PAN-01, PAN-16 (parcial) y PAN-17 tienen test, y todos cubren nodos n8n (`Validar secreto`, `Armar fila memoria`): ningún test cubre el código Next.js del panel.
Huecos más peligrosos: (1) PAN-02/04: el botón masivo "Devolver todos al bot" y el toggle por conversación pueden reactivar el bot sobre chats humanos o `no_bot` (el riesgo del incidente 2026-05-09) sin ningún test, con `botActive` heurístico y latencia ~30 min sin medir; (2) PAN-03: el guard de precios por oración no tiene test, y un cambio puede volver a bloquear a la Dra. o dejar pasar un precio fijo de tratamiento; (3) PAN-01/20: acciones del panel que escriben (enviar, toggle, Confirmar/Cancelar en Dentalink) dependen de E2E manual; la última nunca se probó contra Dentalink real.
