# Backlog — raquel-n8n

## P0 — hallazgos 2026-10-05 (verificados, nada aplicado; detalle en current-state)
- [x] 2026-10-05 05:49Z **El bot no enviaba respuestas** (01:09 → 02:49 ART; `Loop Mensajes` conectado
      por la salida equivocada tras el desacople). Aplicado `apply_fix_loop_mensajes_salida.py --apply`.
- [ ] **Prueba real del envío** desde el número de Lucas + limpiar residuos (`limpiar_numero_demo.py`).
- [ ] **El takeover de 24 h no vence nunca** (el gate final lee el booleano crudo y, al bloquear,
      re-arma el takeover vía `notify-grupo`): un solo lugar que lo venza (cron/pg_cron) y lectores
      simples. Arreglar antes del martes 06/10 a la mañana (primeros takeovers de 24 h).
- [ ] **Corregir `apply_desacoplar_chatwoot.py`** (o marcarlo como no re-ejecutable): compacta las
      salidas vacías de las conexiones. Buscar el mismo patrón en otros scripts.
- [ ] **Reactivación de `human_takeover`**: hoy no vuelve nunca a false (Auto Reactivar está
      desactivado desde el desacople de Chatwoot). Definir la política (¿24 h como se decidió el
      16/09?) e implementarla con un `human_takeover_at`, más una limpieza de los `true` viejos.
      Mientras tanto, revisar el contador "modo humano" del panel.
- [ ] **`Parse Intent`**: que el override de reprogramar no pise `urgencia_dolor` y que no
      dispare con "pasar" suelto. Agregar test con los casos del 05/10.
- [ ] **Key de Supabase escrita a mano** en `Gate Humano Final` y en `apply_desacoplar_chatwoot.py`:
      pasarla a una credencial de n8n, rotarla y no commitear el script con el literal.
- [ ] P1 **Banlist antes del Formatting Agent**: hoy un LLM reescribe el texto después del regex.
      Volver a correr el Banlist después del Formatting, o no pasar los canned por el Formatting.
- [ ] P1 **El sub-flujo Cancelar/Reprogramar guarda las respuestas del bot con `source: 'wa_outbound'`** (Step 8a del sub-WF `5cAWJxiWJ50hxEq3`), la marca que el panel y el Logger usan para los mensajes del STAFF: en el panel aparecen como escritas por la Dra./secretaria (azul), cuentan como "modo humano reciente" y `Clear Old Memory` no las limpia (33 de 43 respuestas rápidas del "staff" a cancelaciones eran de Asiri). Arreglo: cambiar el source a otro valor (p. ej. `bot_subwf`) en Step 8a; revisar luego los comentarios del panel que dicen que `wa_outbound` lo escribe solo `Build fromMe AI memory`.
- [ ] P1 **APLICAR `apply_politica_modo_humano.py`** (modo humano solo por pedido de persona/urgencia/queja/baja de datos o cuando una persona escribe) + prueba en vivo. Preparado y probado offline el 05/10.
- [ ] **APLICAR directrices editables** (construido, probado offline, sin aplicar): 1) `python scripts/apply_agente_directrices_db.py --apply`
      2) `python scripts/apply_agente_directrices_n8n.py --apply` 3) prueba real (saludo solo + anuncio) 4) deploy del panel
      (`/opt/nexora-panel`, env `PANEL_ADMINS` opcional). Incluye: anuncio y menú sin Formatting Agent, canned en memoria.
- [ ] P1 **El anuncio sale por `direct_canned` pero el Formatting Agent igual lo reescribe** (3 de 3 ejecuciones:
      294587, 294600, 294615; el texto enviado ≠ fila 40 de la KB: "Hola. Soy Asiri… Gracias por comunicarse", emojis
      cambiados). Falta que `Necesita Formatting?` saltee los `direct_canned`. Además la regex del gate solo
      reconoce la frase exacta (los reales también escriben "hola mas info", "quiero mas info") y el texto de la
      fila trae "$50.000" a mano.
- [ ] P1 **Regla de cierres perdida en la curación del General**: "Muchas gracias, impecable!" a veces se
      contesta ("¡Gracias a usted! ¿Desea agendar un turno…?", exec 294609) y a veces calla (294577); `Pre-filtro
      Cierre` no lo atrapa. El caso original TC-08/TC-09 esperaba `[NO_REPLY]`.
- [ ] P0 **Rate limit con puerta trasera**: `Rate Limit Prep` saltea el límite si el payload trae
      `data.source = 'test_e2e_suite'`. Sin autenticación en el webhook, cualquiera puede mandar mensajes sin tope
      (gasto de OpenAI + el bot responde por el WhatsApp de la clínica al número que el atacante ponga: riesgo de
      bloqueo del número). Quitar el bypass o exigir el secreto del webhook; para los tests, usar un teléfono
      de prueba reservado y el modo prueba.
- [ ] **P0 seguridad: el webhook del bot no autentica** (`Webhook Validator` solo exige el secreto si existe la env
      `EVOLUTION_WEBHOOK_SECRET`, que no está seteada: el runner de tests entró con una `apikey` inventada).
      `Kill-switch Check` decide "admin" por el teléfono que trae el propio payload → cualquiera que conozca un
      número admin puede mandar `/bot off` (misma clase que la causa 1 del incidente Mariela) o hacerse pasar por
      un paciente. Arreglo: setear `EVOLUTION_WEBHOOK_SECRET` en n8n y en Evolution GO (header) — probar con un
      mensaje real antes de cerrar. Lo mismo vale para los otros ~30 webhooks sin auth.
- [ ] P1 **Runner `tests/test_runner_aislado.py` (otra sesión, 05/10)**: (a) TC-04 da PASS por falso positivo (exec
      294508: el bot dijo "Ese horario no está disponible" y re-ofreció; la regex pasó por "8:00" de otro horario):
      sembrar con horarios reales; (b) asserta sobre `Split en Mensajes`, no sobre la respuesta de
      `Evolution API - Enviar Mensaje` (K1 habría pasado); (c) dispara producción contra el teléfono de Lucas
      (manda WhatsApp reales) y borra su memoria; (d) un intento por caso, sin tolerancia al no-determinismo.
- [ ] P1 **Editor de prompts del panel (`/agente`)**: `guardarPromptAction` valida longitud ≥50 y banlist, hace PUT y
      loguea, pero NO protege las expresiones `{{ … }}` (precio, alias, horarios dinámicos), NO chequea `versionId`
      (puede pisar un cambio concurrente) y NO corre tests antes de publicar. No activar edición libre tal cual:
      exponer campos estructurados (saludo, menú, respuesta al anuncio, tono) como datos.
- [ ] P1 **El aviso `[ATENCION HUMANA … Mantente en silencio y NO respondas … hasta que un admin diga /bot on]`
      guardado en la memoria funciona como un takeover oculto**: el LLM lo obedece (78% de silencios con el
      aviso en los últimos 4 turnos vs 20% sin él, pacientes reales, era A; ej. exec 289847: la paciente elige
      horario y recibe `[NO_REPLY]`). No vence nunca y no depende de la ventana de 24 h. Decidir: sacar la
      orden del texto del aviso (dejar solo "Mensaje del staff: …") y que mande el flag determinístico.
- [ ] P1 **Agendar**: (a) `ver_turnos_paciente` NO está conectada a Sub-Agent Agendar pero el prompt le
      manda usarla contra doble reserva; (b) `reservar_turno` escribe en Dentalink antes del gate final: si
      el gate descarta el mensaje, el turno queda reservado y el paciente sin aviso (exec 285150);
      (c) la descripción de la tool habla de `id_estado`/`nota` y el body real manda `comentario`, con
      dentista, sucursal y sillón fijos en 1 y duración 40. Embudo real (13 días, sin Lucas): 10 pacientes
      llegaron a Agendar, 3 vieron horarios, 1 reservó.
- [ ] P1 **Mensaje de anuncio "¡Hola! Quiero más información"**: que lo responda un gate determinístico
      con el texto de la fila de KB (categoría `conversacion`), sin LLM ni Formatting Agent, en vez de
      depender de que el modelo busque en la KB. El texto trae "$50.000" a mano (duplica la KB de precio).
- [ ] P1 **Bajar Chatwoot del VPS** — chequeos de Redis y panel hechos 05/10 (no son del bot); falta el
      valor de `CHATWOOT_ENABLED` en `growth-engine-evolution-api`. (pedido de Lucas 05/10; 4 containers: rails, sidekiq, postgres,
      redis). Verificado en el snapshot: ningún workflow ACTIVO llama a Chatwoot (solo quedan textos
      en `escalar_a_secretaria`, `Triaje: Decidir` y `Step 7` del sub-WF Cancelar). Los workflows del
      bot usan la credencial `Postgres Supabase Nexora v3`; la vieja `Postgres account` solo la usan
      los TEST/ADMIN. **Sin verificar (solo se ve en el VPS):** a qué contenedor apunta la credencial
      `Redis account` del v6 (buffer, kill-switch, rate limit, triaje). Si fuera `chatwoot-redis`,
      apagarlo tumba el bot. Orden: (1) chequear qué Redis tiene `dentalink:status`, env de los otros
      containers y `CHATWOOT_*` en `/opt/nexora-panel/.env.production` (el botón masivo del panel
      consulta Chatwoot si están seteadas); (2) `docker stop` de rails+sidekiq y probar el bot;
      (3) dump de la base (tiene 5 meses de conversaciones de pacientes: fuera del repo);
      (4) recién después borrar containers y volúmenes. Avisar a Irina.
- [ ] P1 **Automatizar los 8 casos tipo** en la batería (con el shape de Evolution GO) y correrlos
      contra los prompts curados.

## Recordatorio para CONSULTAS (pedido Dra. 8/9) — scripts listos, NADA aplicado (`docs/recordatorio-consultas-2026-09-08.md`)
- [ ] **P1** Lucas confirma con la Dra.: ¿"puntito amarillo" = motivo de atención `Consulta Ortodoncia` exactamente? ¿Hay otro
      motivo de primera visita? Y que valide la frase del 24h (§3.2 del doc; hoy no la recibe nadie: el cron es +2 días hábiles).
- [ ] **P1** Con OK: `python scripts/apply_recordatorio_consultas.py` (dry-run) → `--ddl` → `check_triaje.py` → `--apply` →
      prueba real por webhook manual con cita "Consulta Ortodoncia" de `Test - Lucas Silva` (608) (payload en §6.3) →
      limpieza regla 9 + filas de `recordatorios_enviados` de la cita + anular la cita en Dentalink.
- [ ] **P1** La mañana siguiente al `--apply` (si es el 8/9: miércoles 9/9 08:00 ART → fecha_target viernes 11/9, cita 8899
      `Consulta Ortodoncia `, paciente real): revisar la ejecución del cron (doc §6.4: Gate con `precio_contenido`, Preparar
      mensaje con `precio_origen: 'kb'` / `es_consulta: true`, filas del Insert) y tener `--rollback <PRE>` listo antes de
      las 08:00. La prueba manual (§6.3) NO pasa por el Gate: ese camino se ve por primera vez en producción.
- [ ] P2 Precio en el camino MANUAL = fallback `$50.000` (R4): nodo `Precio consulta (KB)` entre `Webhook Manual Recordatorios`
      y `Fecha Mañana` + segunda fuente en `Preparar mensaje`. PUT aparte.
- [ ] P2 Decisión de negocio (R7): el Sub-Agent Confirmar marca confirmado en Dentalink cualquier "confirmo" sin verificar
      pago; para consultas la regla "sí o sí con el pago" queda solo en el texto. ¿Debe el bot exigir comprobante?
- [ ] P3 `Guardar en Chat Memory`: sumar "Tipo: consulta (se confirma con el pago)" a la NOTA INTERNA para el Sub-Agent Confirmar.
- [ ] P3 R2 preexistente: `Preparar mensaje` empareja la cita por `$itemIndex` con `¿Ya se recordó?` en el medio (0 skips en 14
      días); `$('Solo citas activas').item.json` con fallback sería más robusto. PUT aparte.
- [ ] P3 Panel: mostrar `motivo_atencion` / `es_consulta` en la vista de recordatorios (los tipos opcionales ya están en
      `lib/v3/database.types.ts` `V3Recordatorio`, 8/9; sin UI todavía, sin commit en ese repo).
- [ ] P3 Alinear el regex del precio del v6 (`Extraer Horarios y Precio`, `/\$[\d.,]+/` estricto) con el del recordatorio
      (tolera "$ 55.000"): con ese texto en la KB el bot diría $50.000 y el recordatorio $55.000. PUT al v6 aparte.
- [ ] P3 `motivo_atencion || null` en la salida de `Preparar mensaje` (hoy `''` cuando la cita no trae el campo; Dentalink
      manda `No registra motivo`, no null). Solo después de probar que el Postgres v2.6 acepta null punta a punta.

## Adjuntos del STAFF (rama fromMe) — rediseñado 7/9, NADA aplicado (`docs/media-entrantes-2026-09-06.md` §8)
- [ ] **P1** Con OK de Lucas: `python scripts/apply_media_fromme.py` (dry-run, mostrar el diff) → `--apply`
      (153 → 159 nodos). ANTES: deploy del panel con la parte E (adjuntos de staff + el refetch tardío de
      `media` + **el rescate del token**, `rescatarTokensMedia`), que hoy está en el working tree de
      `nexora-whatsapp-agent` sin commit. El rescate NO es opcional: sin él, cada vez que el cron del Logger
      cae dentro de la ventana INSERT→UPDATE (~1 adjunto cada 2 semanas, varios % de los videos) la foto se
      pierde para siempre — `conversaciones` guarda el texto sin token y nunca lo corrige (R14, §8.6).
- [ ] **P1** Prueba del silenciamiento (§8.4 punto 5): bot encendido, el teléfono de prueba escribe, ~5 s después la
      doctora manda una foto pesada desde el celular del consultorio → `CW Set Label humano` corre ANTES de
      `Media: Subir a Storage (staff)` y el bot NO contesta. Bonus: foto al grupo de derivaciones → 0 filas nuevas
      en `media_entrantes` y `motivo: 'grupo_o_estado'` en la ejecución.
- [ ] **P2 — OJO ANTES DE CORRER `apply_media_entrantes.py`**: ese script YA NO ES NO-OP. El nodo VIVO
      `Media: Preparar` (rama del PACIENTE) quedó con el jsCode viejo, sin los guards de JID de
      `media/preparar.js` (que ahí son no-op porque `Filtrar duplicados y basura` filtra aguas arriba), así que
      un `--dry-run` hoy dice "ACTUALIZA Media: Preparar" + los otros 5 de la cadena. Es deliberado (el PUT del
      staff no toca la rama del paciente), pero deja las dos ramas corriendo código distinto para el MISMO
      archivo: alinearlas en un PUT aparte, con su propio OK. Verificado con `--dry-run` el 7/9.
- [ ] P3 Guard de largo del teléfono (8-15 dígitos) vs. LID: un LID de 16-17 dígitos se descarta a propósito
      (los reales suelen ser de 15; un jid de grupo pelado son 18, el margen es de un dígito). Decisión escrita
      en §8.3 R1 y cubierta por tests. Si algún día aparece un LID largo real, subir el tope y re-correr
      `test_media_nodos.js` §23.
- [ ] P2 R13: si Chatwoot no encuentra contacto/conversación (`CW Extract Conv` / `CW Pick Conv` devuelven `[]`),
      el adjunto del staff no se archiva. Arreglo posible: que esos dos Code nodes emitan un item vacío en vez de
      `[]` (toca la cadena de silenciamiento → PUT aparte con prueba propia).

## Retención + uso + audio del staff (7/9) → scripts listos, NADA aplicado (`docs/retencion-y-uso-2026-09-07.md`)
- [ ] **P1** Orquestador, con OK de Lucas y EN ESTE ORDEN (`docs/retencion-y-uso-2026-09-07.md` §6): **0.**
      `create_panel_acciones_staff.py --update jzxb5zUKCaJcvCgp` (audio + 400 por tipo inválido; antes `--recover-secret
      jzxb5zUKCaJcvCgp` si falta `%TEMP%/panel_webhook_secret.txt`; con el satélite viejo un audio del panel nuevo sale como
      `type: image`) → 1. `create_retencion_satelite.py --dry-run` → 2. `--ddl` → 3. deploy del panel (audio MP3 / borrado_at /
      chip vencido confirmado / 410) + prueba real de audio al celular de Lucas + limpieza (regla 9) → 4. `--apply` → smoke
      `POST /webhook/trigger-retencion-manual {"smoke":true}` (2 DELETE con 200 `[]`, `marcados 0`, 3 filas `fallidos 0` en
      `retencion_log`, sin WhatsApp) → 5. `--activate <id>` → sumar el id a `scripts/check_triaje.py` → 6. hora de la primera
      corrida → 7. `create_vigia_bot.py --update 1UbmAtUMtTBN9Bn3` + `trigger-vigia-manual` (`retencion_tabla true`, sin
      `retencion_no_corrio`).
- [ ] P2 Verificar la hora de la primera corrida automática de Retención (04:30 ART esperado; si corre 01:30 ART la instancia
      ignora `settings.timezone` → `CRON = "30 7 * * *"` sin `TZ` y `--update`).
- [ ] P2 Verificar en un iPhone y un Android que el MP3 del panel (lamejs, 48 kHz) se reproduce como audio en WhatsApp; si
      Evolution/WhatsApp también reproducen el AAC fMP4 de Safari/Chrome, evaluar saltear la transcodificación en Safari.
- [ ] P3 lamejs es LGPL-3.0 dentro del panel propietario (chunk dinámico aparte, anotado en `decisions.md`); alternativa MIT
      si molesta.
- [ ] P3 Huérfanos en `pacientes-media` (objeto sin fila en `media_entrantes`): listar desde `storage.objects` como panel-media.
- [ ] P3 `limpiar_numero_demo.py`: opción para borrar `media_entrantes` + objetos del teléfono (hoy a mano).

## Panel UX "como WhatsApp Web" (pedido 6/9) → APLICADO 6/9
- [x] 2026-09-06 Orden por último mensaje + filtro No leídos; alias manual (`pacientes.alias_panel`);
      envío de imágenes (Storage `panel-media` → `/send/media`); autor en burbujas; pushName real
      compartido (`lib/push-names.ts`). Panel `b76fbfd`/`a309708`, backend `c1b177b`. Deployado.
- [ ] P2 Lucas: prueba desde la UI (alias, imagen, autor, orden) y ponerle alias a su número.
- [ ] **P1** Adjuntos ENTRANTES del paciente a Storage (`media_entrantes`) — scripts listos, revisados y corregidos
      el 6/9 noche (`docs/media-entrantes-2026-09-06.md`, tests 54/54, dry-run 147→153 nodos). Falta, con OK de
      Lucas y EN ESTE ORDEN: deploy del panel nuevo → `create_media_entrantes.py --apply` (+ `--estado` de la
      publicación) → reiniciar el panel → `apply_media_entrantes.py --apply` → prueba real mirando la salida de
      `Media: Preparar`/`Media: Registrar` en la primera ejecución + limpieza (regla dura 9).
- [ ] P3 Cosméticos del render de adjuntos en el panel (no aplicados a propósito): orden cronológico de la galería
      (hoy imágenes primero, después video/audio/doc); coalescing de los 3 eventos live/media/memoria (3 refetch por
      adjunto, aceptable).
- [ ] **P1 (era P2; sube con la rama del staff)** Segunda capa anti-eco del token ` [MEDIA:<id>]` en la SALIDA
      del bot (`Banlist Validator` o `Split en Mensajes`: `replace(/\s*\[MEDIA:[0-9a-f]{16}\]/g,'')`) — cambio
      aparte, fuera de la rama multimedia. Sube de prioridad porque ahora es ALCANZABLE: el token vive dentro de
      filas `[ATENCION HUMANA …]` que el LLM ve por `Build Router Context`, y si ecoa el TAG **completo** junto
      con el token, `esMensajeDeStaff` da true por el TAG y la burbuja del BOT pinta el adjunto del staff. Antes
      de este cambio ninguna fila con TAG tenía un token adentro.
- [ ] P3 Adjuntos del STAFF desde el celular (rama `Es fromMe?[0]`) a Storage: el webhook fromMe trae base64,
      pero es una segunda entrada a `Media: Preparar` + sufijar el placeholder de `Build fromMe AI memory`.
- [ ] P3 Burbuja optimista "enviando…" al mandar desde el panel (hoy aparece al próximo poll ≤1,5 s).
- [ ] P3 Miniaturas vía `/storage/v1/render/image` si el plan de Supabase lo permite.

## Roadmap de refactor (6/9) → `docs/roadmap-refactor-2026-09-06.md`
- [ ] B1 Registro único de mensajes (retirar Logger de 5 min) — base del panel y del sistema propio.
- [ ] B2 Higiene del v6: nodos huérfanos, Banlist Shadow, `` sin `u` en Banlist, continueOnFail en
      `Existe paciente?`, tokens Chatwoot a credencial, gate humano solo `open`, buffer 22 s.
- [ ] B3 Canned/config a tablas editables desde el panel (alias/CBU, cuota, admins, JID grupo).
- [ ] B5 Tests: E2E cierre triaje, `test_e2e_bateria.py` al shape Evolution GO, drift de prompts.
- [ ] C "Dentalink propio": modelo en Supabase → adaptador → doble escritura → cutover con flag
      (decisión de negocio de Raquel/Irina antes de arrancar).

## Panel EN VIVO (SSE + Realtime) → APLICADO 6/9 tarde
- [x] 2026-09-06 `/api/live` + bus Realtime + hook; polling reemplazado; Bearer en las 3 APIs.
- [ ] P2 Verificar en prod el readTimeout 60 s de Traefik sobre el stream (ver current-state); si
      corta, `readTimeout=0` en el Traefik del stack n8n (con OK de Lucas: reinicia el frontal).
- [ ] P3 App móvil: `POST /api/login` que devuelva el token (hoy solo cookie) y exponer las Server
      Actions (enviar, toggle, alias, imagen) como `POST /api/*` con Bearer.
- [ ] P3 `/api/foto` y `/api/whatsapp-status` siguen cookie-only (2 líneas cada una con `sesionDeRequest`).

## P0
- [x] 2026-07-18 **Fase 2 v3 COMPLETA**: sb_secret validada → supabaseApi v3
      (`H1PRagttKC5kxSzs`) → 9 nodos REST → Logger activo y sincronizando → KB E2E PASS
      con invocación real del vector store → credenciales huérfanas borradas.
- [ ] Ticket a soporte Supabase por el v2 pausado (histórico 202k conversaciones) — texto
      entregado a Lucas 17/7; NO borrar el proyecto v2 hasta resolverlo.
- [ ] Decisión antes del **15/8** (fin de gracia egress org vieja): VPS Hostinger vs
      quedarse en v3 free (medir consumo real con Logger a 5 min).
- [ ] Lunes 20/7 08:00 ART: vigilar la primera corrida real del Recordatorio contra v3
      (y que las confirmaciones de los 13 backfilleados matcheen).

## P1 — Panel: mensajes entrantes al instante ("Inbox Live") → APLICADO 5/9
- [x] 2026-09-05 `Inbox Live` en el v6 (147 nodos) + merge en el panel (`c5b0bf3`): el mensaje
      del paciente aparece a ~1 s de llegar. Ver current-state 5/9 (incluye el bug de
      queryReplacement con comas que se corrigió en el camino).
- [x] 2026-09-05 Bug `order ASC` del tail en `chat-data.ts` arreglado y deployado (`cc642c7`).
- [ ] P2 (producto): bajar el buffer de 22 s ("Buffer: Wait 10s" tiene amount 22) → el bot
      respondería ~10 s antes; riesgo: mensajes en 2 burbujas se procesan como 2 turnos (clase
      de bug Confirmar/alias). Decidir con Lucas.

## P2 — Gate humano: label `humano` en conversaciones RESUELTAS silencia al bot para siempre
- [ ] `Verificar Label Humano` / `Re-check Humano` / `Gate Humano Final` miran TODAS las
      conversaciones del contacto; `Auto Reactivar` solo limpia las `open`. Caso real 5/9 (Lucas,
      7 resueltas con humano → bot mudo). Opciones: (a) que los 3 chequeos del v6 consideren
      solo `status='open'`; (b) que Auto Reactivar limpie también resueltas. SENSIBLE (gate
      humano del v6). Mitigado hoy en el origen (el webhook del panel ya no etiqueta resueltas).

## P1 — Panel: enviar mensaje / toggle bot NUNCA funcionó (confirmado 5/9) → RESUELTO 5/9
- [x] 2026-09-05 Satélite n8n `Panel — acciones staff (send-human / toggle-bot)`
      (`jzxb5zUKCaJcvCgp`, activo, `scripts/create_panel_acciones_staff.py`): webhooks
      `panel-send-human` y `panel-toggle-bot` con validación de `X-Panel-Secret` (401 si no
      coincide); envío por Evolution GO + fila `[ATENCION HUMANA … desde el PANEL]` en memoria
      (source `wa_outbound`, `from_panel:true`) + label `humano` en TODAS las conversaciones del
      contacto; toggle = label `humano`/`bot`. Variables `N8N_PANEL_WEBHOOK_BASE/SECRET`
      agregadas al `.env.production` del VPS (secreto generado, no está en el repo) y container
      del panel recreado (healthy). Probado directo: 401 / 200 envío real a Lucas / 200 toggles.
      Falta que Lucas lo pruebe desde la UI del panel.
- [ ] (histórico) `nexora-whatsapp-agent` tiene la UI y las server actions (`enviarMensajeAction`,
      `toggleBotAction`) que POSTean a `{N8N_PANEL_WEBHOOK_BASE}/panel-send-human` y
      `/panel-toggle-bot` con header `X-Panel-Secret` — pero en n8n NO existen esos webhooks
      (63 workflows revisados) y el `.env.production` del VPS no tiene las 2 variables → el
      panel siempre respondió "El panel todavía no está conectado al servidor del bot".
      Build propuesto (~40 min): satélite n8n "Panel — acciones staff" con 2 webhooks que
      validan el secreto; `panel-send-human`: `/send/text` por Evolution GO al paciente +
      fila `ai` en `n8n_chat_histories` con source `human_takeover` (el panel la muestra como
      "Dra. Raquel", el Logger como `rol=human`) + label `humano` en Chatwoot (mismo efecto
      que escribir desde el WhatsApp del consultorio); `panel-toggle-bot`: label
      `humano`/`bot` en Chatwoot. Después: agregar las 2 env al VPS + `docker compose up -d
      --force-recreate` (el redeploy.sh preserva el .env pero hay que recrear el container).

## P1 — BUG agendar prematuro (detectado 19/7 por Lucas)
- [ ] **El bot RESERVA el turno sin confirmación explícita del paciente ni pago.** Caso real:
      el paciente eligió una fecha y preguntó el PRECIO (frenillo → "valor $50.000") pero NUNCA
      dijo "sí, reservá" ni mandó comprobante — y el bot igual reservó en Dentalink. Debe:
      (a) NO reservar hasta confirmación explícita de intención de agendar; (b) para tratamientos
      que requieren seña/pago, no reservar hasta comprobante (o dejar "pre-reserva"). Fix en el
      prompt del Sub-Agent Agendar del v6 + posible gate determinístico. SENSIBLE (toca el v6).

## P1 — post-incidente
- [x] 2026-07-18 Backfill recordatorios 16/7 + 17/7 (13 filas en v3, con wa_message_id).
- [x] 2026-07-18 Fila envenenada Sub-WF Cancelar: muerta con v2 (v3 limpia + JSONB NOT NULL).
- [ ] v6 optimización DB (con diff, revisar con Lucas): mover "Get Paciente Context" DESPUÉS
      del filtro fromMe/buffer; sacar el guard DDL de "Check Session Age" (correr una vez,
      no por mensaje); evaluar pooler transaction-mode (6543); desconectar
      `buscar_conocimiento` del Sub-Agent General (estaba planificado y sigue conectado).
- [ ] Step 0b Sub-WF Cancelar: parse tolerante a no-JSON (hardening, la defensa NOT NULL
      ya evita la causa).
- [ ] Batería E2E: agregar los casos específicos que pida Lucas (contexto/KB/precios) a
      tests/test_e2e_bateria.py.
- [ ] Documentar/auditar `BO1cdE8xmqln4IeO` "Cron - Resumen Clinico Pacientes" (descubierto
      17/7, snapshot en workflows/current/, hoy DESACTIVADO por orden de Lucas).

## P1
- [ ] **Extender horarios/precio dinámico a cuota mensual** ($70.000, KB id=36):
      mismo patrón ya armado 21/8 para horarios (id=20) y precio consulta (id=21)
      — agregar id=36 a la query de `Get KB Horarios y Precio` + extraer en
      `Extraer Horarios y Precio` + interpolar en el canned de "Cuota mensual" de
      Sub-Agent General (hoy sigue con "$70.000" hardcodeado).
- [ ] **Fase 1 reprogramaciones** (quick wins, esperando OK de Lucas):
      (a) `crear_paciente_dentalink`: agregar `documento`+`id_sucursal` al jsonBody (hoy el
      DNI nunca llega a Dentalink → fichas sin rut, GAP 7);
      (b) anti-loop: sumar el canned multi-ficha a `fraseLoop` del Step 0b (GAP 4);
      (c) canned: pedir "DNI o nombre de pila" en vez de "nombre y apellido" (el apellido
      familiar rompe el matching, GAP 2 parcial);
      (d) Router: regla para reprogramación interrogativa "¿puedo cambiar el turno?" (GAP 8).
- [ ] **Rotar API key de n8n** (quedó en historial de chat del 06/07) + actualizar `.env`
      del repo y de `Desktop/proyectos/n8n-context-pack/`.
- [ ] **Fase 2 reprogramaciones** (revisar juntos antes): re-fetch de turnos de la ficha
      resuelta (GAP 1, el dead-end de familias), matching por scoring (GAP 2), persistir
      `turno_objetivo` (GAP 5). Test sintético + shadow antes de cutover.

## P2
- [ ] **Alias + datos de cuenta dinámicos desde la KB (id=24), en UNA sola pasada para el
      `Canned Sidecar` Y el prompt de Sub-Agent General**: hoy ambos lo tienen hardcodeado con
      el MISMO texto (a propósito — ver decisions.md 2/9: dinamizar solo uno haría que Raquel
      edite `/servicios` y cambie una respuesta y la otra no). La fila ya existe
      (`knowledge_base` id=24 "Datos de cuenta para transferencia", categoría `pagos`, ya
      editable desde `/servicios`), así que el trabajo es: extender la query de
      `Get KB Horarios y Precio` a `IN (20,21,24)`, extraer alias + bloque de cuenta en
      `Extraer Horarios y Precio`, y apuntar los dos consumidores a esos campos. OJO: si se
      reescribe el `contenido` de id=24 para que sea texto citable literal (mismo patrón que
      se aplicó a id=20 el 21/8), re-embeddear esa fila para que `buscar_conocimiento` no
      quede con el vector viejo. Mismo patrón ya probado el 21/8 para horarios/precio.
- [ ] **Encender las reglas `horarios`/`direccion` del `Canned Sidecar`** (hoy `enabled:false`
      a propósito: se arrancó solo con lo que falló de verdad en producción, que fue plata).
      Es cambiar una palabra por regla. Antes de la de dirección, revisar que no choque con el
      ban de "Balcarce 37" del Banlist (hoy el Banlist ya la deja pasar SOLO si el paciente
      preguntó la dirección explícitamente — misma condición que usaría la regla).
- [ ] **Ajustar reportero semanal**: definición de "escalación" (excluye fromMe/receipts),
      roles mal categorizados, métricas alucinadas ("agregó items al KB" falso). Primero
      auditar de qué fuente lee (¿Logger/Supabase?).
- [ ] **Tabla de mapeo lid↔teléfono** (Redis o Supabase): guardar el par cuando llegan juntos,
      consultar cuando llega @lid pelado (caso exec 193142). Único fix real para el ~7%.
- [ ] **Cleanup Dentalink**: ficha duplicada Carmen (id 609), 3 duplicados históricos de la
      clínica (tarea de Irina), backfill de DNI en fichas creadas por el bot.
- [ ] **Fase 3 reprogramaciones**: sub-WF debe usar `recordatorios_enviados` (patrón Confirmar)
      + cerrar filas al cancelar (GAP 6); borrar Sub-Agent Cancelar huérfano.
- [ ] Rate limiter: no contar mensajes fromMe del staff en la cuota del paciente.
- [ ] Mover token de Chatwoot hardcodeado (nodo "Chatwoot - Buscar Conversacion") al
      credential store de n8n + rotarlo.

## P3
- [ ] Sincronizar `prompts/v6_partials/` con los prompts vivos (drift múltiple, GAP 10).
- [ ] Banlist Shadow: el judge gpt-5-nano da BLOCKs falsos crónicos (log-only) — recalibrar
      o cambiar de modelo.
- [ ] Sesión de memoria basura del test (`223871026389070@lid`) en n8n_chat_histories —
      el cron cleanup no la toca (filtra por contenido, no session_id). Borrado manual algún día.
- [ ] Renombrar nodo cron "Diario 9AM Arg (cron 0 14 UTC)" — la expresión real es `0 13 * * 1-5`.

## Done reciente
- [x] 2026-09-05 **Vigía** (`1UbmAtUMtTBN9Bn3`): alerta a Lucas si el triaje se degrada, el v6
      tira errores, la instancia queda sorda en horario de clínica, o el triaje está activo sin
      videos. + `scripts/check_triaje.py` (chequeo único pre-PUT). + reglas 8/9 en CLAUDE.md.
- [x] 2026-09-05 **Panel envía/togglea** (satélite `jzxb5zUKCaJcvCgp`) y **fix de contexto del
      clasificador** (episodios cerrados no contaminan). Ver current-state 5/9.
- [x] 2026-09-02 **Bug real reportado por las secretarias: el bot "tragaba" el pedido de
      alias cuando venía pegado a "Confirmo"** (caso Paulina Villanueva 2/9 + otro casi
      idéntico el 28/8). Causa raíz: Router y Sub-Agent Confirmar se contradecían en vivo
      sobre quién responde la info canned, y con el buffer mergeando 2 mensajes en un turno
      no existe el "próximo turno" que Confirmar asumía. Fix estructural: nodo determinístico
      `Canned Sidecar` en el punto de convergencia de los 7 caminos de salida — ningún
      sub-agent necesita saber de info canned nunca más. 17/17 tests + 3 E2E reales (la 269291
      reprodujo el bug en OTRO sub-agent y lo mostró rescatado). Ver current-state y
      decisions.md 2/9.
- [x] 2026-09-02 **Bug real: guard de precios bloqueaba guardado legítimo en
      /conocimiento y /servicios** (Raquel reportó por WhatsApp que no podía
      guardar "Valor de la primera consulta"). Fix: chequeo por oración en vez
      de texto completo. Deployado (`173c8b8`) y verificado. Ver current-state 2/9.
- [x] 2026-08-21 **Horarios y precio de consulta dinámicos desde /servicios**: el
      bot ahora lee ambos de `knowledge_base` en cada mensaje (no más texto fijo en
      el prompt) — editar el panel cambia lo que dice el bot al instante, sin tocar
      n8n. Probado cambiando valores reales en vivo y confirmando que el bot los
      repite. Ver current-state 21/8.
- [x] 2026-08-21 Bug real Salvador Mayans (turno nunca creado en Dentalink, mensaje
      multi-pedido): fix en 2 capas (Router + Sub-Agent General), verificado E2E
      creando y cancelando una cita real de test. Ver current-state 21/8.
- [x] 2026-08-21 3 pedidos de contenido de la Dra. (horarios actualizados, wording de
      pago el día de la consulta, saludo de precio en primer contacto) — probados con
      mensajes reales.
- [x] 2026-07-06 Precio consulta $50.000 en prod (testeado E2E).
- [x] 2026-07-06 Fix LID-safe extracción de teléfono + pushName (5/5 tests PASS).
- [x] 2026-07-06 Fix crítico kill-switch (backspace U+0008 → `\b`; roto desde 09/05).
- [x] 2026-07-06 Health check completo post-cambios (0 errores, 9 satélites sanos).
- [x] 2026-07-06 Diagnóstico reprogramaciones/familias (10 gaps, plan 3 fases).
- [x] 2026-07-06 Snapshot Sub-WF CancelarReprogramar al repo.

## Reunión Dra. Raquel 2026-07-14 (ver docs/reunion-2026-07-14-dra-raquel.md)
- [x] 2026-08-11: **P1: Reportero v2 "aprendizaje semanal"** construido y probado con datos
      reales (ver current-state 11/8). Absorbió el pendiente del reportero que contaba mal.
      Extensión pedida 15/8: ver bullet nuevo abajo.
- [x] 18-19/7: **P2: Dashboard nexora-whatsapp-agent** construido y en producción
      (`panel.raquelrodriguez.com.ar`) — UI WhatsApp-like, leído/no-leído, métricas Dentalink,
      servicios/KB editables. Demoeado formalmente a Raquel el 15/8. Gap señalado en esa demo:
      toggle bot/humano no es inmediato (ver bullet nuevo abajo).
- [ ] P2: Cuando Raquel cree el grupo nuevo (ella+Lucas+Irina): actualizar destino de
      escalaciones si cambia el group id. **Sigue pendiente del lado de Raquel al 15/8**
      (pedido primero el 14/7, un mes sin crearse — no es bloqueo técnico).
- [x] Cerrado: "revisar lógica de feriados" — no requiere infra (decisión de la reunión +
      verificación técnica). Reafirmado 15/8 tras un incidente recurrente — ver
      `docs/reunion-2026-08-15-dra-raquel.md` (el gap fue de proceso, no de código: Irina pidió
      apagar recordatorios en vez de usar la agenda).
- [ ] P3: Landing page → **movido a `raquel-rodriguez/memory/backlog.md`** (repo propio).
      Sin material nuevo de Belén al 15/8, mismo pedido que el 14/7.

## Reunión Dra. Raquel 2026-08-15 (seguimiento — ver docs/reunion-2026-08-15-dra-raquel.md)
- [ ] **P1: Triaje de urgencias con videos** — diseño completo cerrado 2/9 (ver decisions.md
      y current-state.md 2/9: gate de red flags determinístico antes Y después de clasificar,
      sin vision (foto = solo respaldo adjunto), aviso pasivo al resolver con video, rollout
      sombra → piloto 1 tipo → expandir). Raquel está mandando los videos ahora. Bloqueado en:
      (a) recibir el resto de los videos (2/9: solo llegaron 2, del tipo "alambre pincha" —
      faltan "bracket suelto", "alambre girado", "ligadura pincha", Raquel avisó que los
      demás siguen en edición);
      (b) fraseo exacto de las preguntas guiadas (open-questions.md),
      (c) confirmar con Raquel la lista de "red flags" que siempre escalan.
      **Ajuste de diseño (2/9, descubierto al ver los 2 primeros videos)**: NO es 1 video = 1
      tipo — "alambre pincha" ya trajo 2 videos secuenciales (Opción 1: cera de ortodoncia:
      Opción 2: reinsertar con pinza, para probar si la 1 no alcanza). El flujo probablemente
      necesita mandar Opción 1 primero y ofrecer la 2 si el paciente dice que no resolvió, no
      un solo video fijo por tipo — confirmar este patrón se repite en los otros 3 tipos cuando
      lleguen.
      **Build resuelto (2/9): envío de video saliente por Evolution GO YA VERIFICADO en vivo.**
      `POST /send/media` (existe en el swagger real del VPS, no estaba documentado en el
      repo) acepta `{number, type:"video", url:<BASE64 CRUDO, sin prefijo data:>, caption,
      filename}` — mismo apikey que ya usa "Evolution API - Enviar Mensaje" del v6 (sin campo
      `instance`, igual que `/send/text`). Probado con un video real (3.9MB) mandado a Lucas,
      200 OK, `Type:"VideoMessage"` confirmado. Script reusable:
      `scripts/test_evo_go_send_video.py` (no hardcodea el apikey — lo extrae en caliente del
      nodo vivo vía API de n8n, porque las claves hardcodeadas en scripts de jul/ago ya están
      vencidas). Ver current-state.md 2/9 para el detalle completo.
      **Hosting resuelto (2/9)**: bucket público Supabase Storage `urgencias-videos`, ya con
      `alambre_pincha/opcion1.mp4` y `opcion2.mp4`; `/send/media` acepta la URL directa
      (verificado E2E). Script: `scripts/upload_urgencia_video_supabase.py`.
      **Sombra retrospectiva hecha (2/9)**: 30 urgencias reales en 60 días, ~47% resolubles
      con video, casi todas alambre_pincha (7–8) o bracket_suelto (6); alambre_girado y
      ligadura_pincha ≈ 0. Piloto recomendado: alambre_pincha (videos ya listos). Video que
      más falta: bracket_suelto. Candidatos a video 5/6: contención rota, Invisalign. Detalle
      y revisión manual caso por caso: `docs/analisis-retrospectivo-urgencias-2026-09-02.md`.
      **FASE 1 (sombra) HECHA Y ACTIVA (3/9)**: workflow satélite `Áurea — Triaje Urgencias
      (sombra)` (`Gm7ofyGohOJ2bI44`), cada 15 min clasifica las urgencias nuevas de
      `escalaciones_log` → `triaje_urgencias_log` (tabla nueva). No toca el v6, no manda
      nada. Gate de red flags en `triaje/gate_red_flags.js` (29/29 tests). Ver con
      `python scripts/ver_triaje_sombra.py`. Primera corrida real OK (2 casos).
      **FASE 2 APLICADA AL v6 (4/9) y verificada con 4 E2E reales**: video Opción 1 → Opción 2
      → escalación determinística → red flag. Piloto activo SOLO para el número de Lucas
      (`triaje_config.telefonos_piloto`). Diseño: `docs/triaje-fase2-diseno-2026-09-04.md`.
      Siguiente: (a) demo de Lucas desde su teléfono; (b) textos definitivos de Raquel por
      UPDATE (hoy borradores); (c) abrir a todos: `create_triaje_config_tables.py --activar
      --piloto ""`; (d) E2E del cierre; (e) cuando lleguen los videos de bracket_suelto /
      alambre_girado / ligadura_pincha: `upload_urgencia_video_supabase.py` + UPDATE
      `triaje_videos` activo=true (sin n8n).
- [x] 2026-09-04 **BUG preexistente arreglado: toda escalación del bot silenciaba su propia
      respuesta al paciente** (6/6 casos desde el 30/8). Fix en el Helper `S5U6tSipzlgFHCkf`
      (`scripts/apply_fix_helper_label_diferido.py`, 0 cambios en el v6): webhook responde al
      instante (`onReceived`) + Wait 20 s antes de `Chatwoot Apply` → el aviso al grupo sigue
      inmediato, el label `humano` llega cuando la respuesta del bot ya salió. Verificado en
      vivo (label ausente a +3 s, presente a +25 s). Vigilar la primera escalación real de un
      paciente: debe recibir "Recibimos tu mensaje…" y después quedar en silencio.
- [ ] **P1: Scoring de urgencias en el reportero semanal** — extender el reportero ya
      construido (11/8) para que además mapee las urgencias de la semana (no solo
      escalaciones generales) y sugiera contenido/video nuevo para casos recurrentes.
- [ ] P2: Toggle bot/humano **inmediato** en el panel (hoy espera la ventana de verificación de
      ~30 min; Raquel lo quiere al toque cuando un humano escribe).
- [ ] P2: Consolidar Dentalink + KB en un formato unificado para que Raquel lo revise.
- [ ] P3 (exploratorio, sin comprometer): perfil/análisis de personalidad del paciente en la
      ficha de la agenda, cruzando CRM + Dentalink.

## Post-incidente 2026-07-08 (nuevos)
- [x] 2026-07-10: Recordatorio 48HS re-activado (Claude, a pedido de Lucas)
- [x] 2026-07-14: Recordatorio 48HS re-activado + disparado manual vía webhook interno (Lucas se colgó con las 08:00). Exec 222062 success: 8 citas → 4 WhatsApps enviados (turnos jue 16/07) → 4 filas en recordatorios_enviados nueva = primeras escrituras reales de producción en la tabla ✅. Queda ACTIVO para el cron normal.
- [ ] P1: Health Check NO monitorea Supabase (el borrado fue invisible) — agregar ping a la base
- [ ] P2: Analizar imagen de reclamos de pacientes que va a pasar Lucas
- [ ] P2: Pedir SUPABASE_SERVICE_ROLE_KEY a Lucas para completar .env (scripts locales)
- [ ] P3: Borrar credenciales huérfanas en n8n (Postgres account viejo, Supabase Bearer viejo)
- [ ] P3: Región us-west-2 queda lejos del VPS (~+150ms/query); considerar región más cercana en futuro proyecto
- [x] 2026-07-08 Migración completa a Supabase v2 + verificación E2E (bot vivo)
- [x] 2026-07-09 Canned alias con datos bancarios completos (Brubank/CBU/CUIT) — pedido Dra 08/07, testeado E2E 3/3
- [x] 2026-07-09 Cuota mensual $70.000 + regla desambiguación cuota/consulta/control (caso Valentina) — testeado E2E
- [x] 2026-07-09 KB exportada para validación de la Dra → docs/kb-validacion-dra-2026-07-09.md (35 entradas, 22 categorías)
- [ ] P2: Enviar kb-validacion-dra-2026-07-09.md a la Dra y aplicar sus correcciones/altas a la KB


## v7 — construcción (orden con puertas; detalle en docs/v7-arquitectura-agente-asiri.md §7-8)
- P1 Puerta 0: contratos de herramientas + `tests/harness_tool_v7.mjs` con los 24 escenarios de escritura portados + fixture del chequeo de afirmaciones (~40 frases) + rechazo de motivos de pasar_a_humano. Hecho: línea base de latencia del v6.
- P1 Sub-workflow `v7 Tool - ejecutar_propuesta` (extraer 6d-prep→POST→IF→PUT→Consolidar y 6a del sub-WF de cambios; sin memoria ni avisos propios) + `v7 Tool - Agenda` (ver_turnos, buscar_horarios con ofertas/lotes en Redis, proponer_*, confirmar_turno) + Clínica (avisar_grupo con niveles, pasar_a_humano verificado, derivar_triaje, registrar_pago) + Info.
- P1 Cerebro v7 como sub-workflow `{phone, texto, modo}` con modo sombra POR CÓDIGO (memoria `v7s:{tel}`, Redis `v7s:`, cero HTTP con efecto) + prompt de Asiri (≈1.500 chars + directrices del panel) + chequeo bidireccional de salida + banlist en "usted".
- P1 Sombra retrospectiva sobre 90 días con Dentalink simulado → elige modelo y umbrales.
- P2 Inserción en v6: nodo Redis `v7:tel:{tel}` antes del Router; sombra en vivo con métricas; examen vivo (ficha de prueba, teardown); piloto por cohortes de recordatorio supervisado; cutover con rollback drenado y `/v7 off`.
- P2 Panel: config por fila (id del workflow principal, nodos editables), mostrar teléfonos en v7; directrices bajo cabecera fija.
- P3 Verificar/corregir "Reprogramar" del panel (formato de hora).

## 2026-10-06 tarde
- P1: Lucas pega a mano en el v6 el parche de cierres (`python scripts/parche_manual_cierres_v6.py` imprime Fallback Output + regla del Sub-Agent General). Hasta que el v7 reemplace al v6.
- P1: v7 sombra, escenarios restantes (cambio/cancelación, confirmar tras recordatorio, familias, pagos, pedir persona, urgencia, errores de agenda) + latencia < 10 s.
- P2: decidir con la Dra. si Asiri ofrece los datos de pago tras reservar o los manda un texto fijo.
- P2: cerrar el webhook "v7 Test (sombra)" cuando terminen las pruebas (`python scripts/probar_v7.py --desactivar`).
- [x] 2026-10-06 P1: portar el triaje con videos al v7 → `derivar_triaje` construido offline (359/359). Falta: subir a n8n (`crear_v7_en_n8n.py --aplicar`) y, al conectar con el v6, que `Triaje: Evaluar` tome la derivación del v7 como entrada "nueva".
- P2: que Asiri diga claramente cuando la franja pedida no existe en el rango pedido (hoy pega el bloque con una frase vaga).
- P2: confirmar_turno tras recordatorio no se pudo probar en sombra: el celular de prueba no tiene turno vigente. Hace falta una cita de prueba en la agenda.
- P1: Lucas da el OK y se corre `python scripts/apply_fix_cierres_v6.py --apply` (cierres en el v6). Hasta entonces los "gracias" siguen recibiendo "De nada…" o el aviso a la secretaria.
- P1: v7: desplegar la regla de respuestas a preguntas del staff y repetir los casos del 03/10 y 16/09 con el modelo real.
- P2: modo humano que se traga confirmaciones: un "confirmo" en conversación con la secretaria no confirma el turno en Dentalink. Decidir quién lo confirma.
- P0: aplicar `python scripts/apply_fix_modo_humano_1h.py --apply` (con OK de Lucas) y después desplegar el panel con `HUMANO_MS` de 1 h. Hasta entonces el bot le contesta al paciente mientras habla la Dra.
- P1: decidir si los recordatorios manuales de Dentalink ("Le recordamos que el día…") activan o no el modo humano (hoy lo harían y taparían el "Confirmo").
- P1: alerta del Vigía cuando `Activar Takeover (fromMe)` falle: 182 fallos seguidos pasaron como "success" por continueOnFail.
- [x] 2026-10-06 P0 modo humano arreglado en v6 y Helper, verificado en vivo (ver current-state). Resta: desplegar el panel con HUMANO_MS de 1 h.

## 2026-10-06 noche — v7 (sesión nube)
- [ ] P0 Lucas: `python scripts/crear_v7_en_n8n.py --aplicar` desde la rama `claude/inspiring-mayer-ki0b7p` (sube triaje, regla del staff, arreglo de propuesta consumida, hint de fichas, webhook de prueba en sombra forzada). El permiso de la sesión nube lo bloquea.
- [ ] P0 Lucas: `OPENAI_API_KEY` en el entorno de la nube (paciente simulado) + una cita de prueba para "Test - Lucas" en Dentalink → `python tests/examen_v7.py --todos --reps 3`.
- [ ] P1 Antes de conectar al v6: mover `esUrgenciaFuerte`+red flags antes del fork `v7:tel`; Banlist Validator para `_flow='v7'` (5 reglas "esperamos"); `Triaje: Evaluar` + `isExecuted`; `executionTimeout` en los 9 workflows v7.
- [ ] P1 Verificar con la Dra.: ¿se puede "abonar el día de la consulta"? Asiri lo afirmó sin herramienta (AGE-04 en sombra). Si no, agregar la política de seña a DATOS DEL CONSULTORIO.
- [ ] P2 Recorte v7: fusionar ver_turnos+elegir_ficha+proponer+confirmar_turno en "v7 Tool - agenda" con `accion`; un solo JSON de estado por teléfono en vez de 7 GETs post-modelo; "¿Es un cierre?" antes de Datos+Identificar (hoy un "gracias" paga 3 Postgres + 1 GET Dentalink).
- [ ] P2 Cerrar el webhook "v7 Test (sombra)" al terminar las pruebas (`probar_v7.py --desactivar`); hoy está ACTIVO.
