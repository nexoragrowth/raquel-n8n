# Edge cases consolidados: handoff_humano_fromMe y memoria_contexto

Base: 4 extractores sobre fuentes solapadas, dedupe al 2026-10-04. Estado contrastado con el workflow vivo (v6 activo; "Sub-Agent Cancelar" y "Sub-Agent Urgencia" son nodos muertos; prompts Router/Agendar/Confirmar/General curados el 2026-10-04) y con `live_prompts.md`.
Equivalencias de IDs crudos entre corchetes: eN = edgecases_N.

## handoff_humano_fromMe

### HUM-01 · Kill-switch `/bot off` ignorado en silencio (Mariela, causa 1)
- **Entrada/disparador:** sábado 2026-05-09 12:53, la doctora manda `/bot off` desde el multi-device del consultorio (`fromMe=true`) durante el incidente de Mariela; también cualquier `/bot off|on|status` de un admin (Lucas, Irina, Dra.).
- **Falla previa:** `Kill-switch Check` chequeaba `!fromMe && ADMINS[phone]` y usaba el phone del DESTINATARIO del chat en vez del emisor. El comando se ignoraba sin avisar y la doctora apagó el bot por otra vía, justo a tiempo.
- **Esperado:** el comando solo se acepta si `fromMe=false` Y el emisor ∈ ADMINS (celular PERSONAL del admin), con regex `^\/bot\s+(off|on|status)\b`. La confirmación (`HTTP Send Admin Confirm`) va a `chatJid` (origen del comando), NO a `adminPhone`. Un `/bot off` con `fromMe=true` NO apaga el bot. El bot NUNCA le manda mensaje al paciente cuando se apaga o prende (KB 12). Runbook: escribir desde el celular propio, no desde el del consultorio.
- **Capa:** nodo (`Kill-switch Check`)
- **Test:** SIN TEST (solo `scripts/test_lid_fix_e2e.py` T4-bis/T5, fuera de `tests/`; "verificado JSON" en BUGS #2)
- **Fecha/fuente:** 2026-05-09 · `.claude/CLAUDE.md`/`AGENTS.md`; BUGS #2; FIXES Round 1 #1 y #4; `docs/runbook.md` "Kill-switch"; `docs/kb-validacion-dra-2026-07-09.md` [12] [fusiona e3 EC-12 + e4 EC-160]
- **Estado:** vigente

### HUM-02 · Kill-switch inoperante por BACKSPACE U+0008 en la regex
- **Entrada/disparador:** `/bot off`, `/bot on`, `/bot status` de cualquiera de los 3 admins.
- **Falla previa:** el `jsCode` tenía un carácter BACKSPACE (U+0008) donde debía ir `\b` (al cargar por API/JSON, `"\b"` se interpreta como backspace). La regex NUNCA matcheaba: los comandos fallaron en silencio desde 2026-05-09 hasta 2026-07-06.
- **Esperado:** el `\b` se carga como `\\b` en el JSON del PUT; auditar los scripts `apply_*.py` por escapes de control (`\b`, `\f`) antes de cualquier PUT; prueba con mensaje real (T4-bis y T5, y exec 193150 de grupo). Aserción: `/bot status` de un admin produce confirmación; el jsCode publicado no contiene bytes `\x08`.
- **Capa:** nodo (`Kill-switch Check`)
- **Test:** SIN TEST (`scripts/test_lid_fix_e2e.py` está fuera de `tests/`)
- **Fecha/fuente:** 2026-07-06 · BKL "Done reciente" (fix crítico backspace); `docs/sesion-2026-07-06-precio-lid-reprogramacion.md` §2b [fusiona e3 EC-13 + e4 EC-161]
- **Estado:** vigente

### HUM-03 · Kill-switch y teléfono desde chats `@lid`
- **Entrada/disparador:** un admin escribe `/bot status` desde un chat con JID `…@lid` (con `remoteJid=@lid + remoteJidAlt=phone`, y @lid sin Alt, el peor caso). Un paciente real también puede llegar como @lid.
- **Falla previa:** la extracción tomaba el @lid crudo como teléfono (issue Evolution #1872 en v2.3.7): paciente invisible para Dentalink/Supabase/recordatorios, human-takeover fail-open, comandos admin ignorados en silencio. Además `pushName` llegaba vacío SIEMPRE (el extractor lo guardaba como `name`).
- **Esperado:** cadena de candidatos `remoteJid → remoteJidAlt → senderPn → participantAlt → participant`; toma el primero que termine en `@s.whatsapp.net`, recortando `:device` y dominio. El Kill-switch usa la cadena solo-DM. Sin candidato → fallback EXACTO al comportamiento previo (no strippear dígitos del LID, no devolver phone vacío). `pushName` poblado.
- **Capa:** nodo (`Edit Fields - Extraer Datos`, `Kill-switch Check`)
- **Test:** SIN TEST en `tests/` (`scripts/test_lid_fix_e2e.py` T1-T5; `tests/test_media_nodos.js` cubre solo el teléfono @lid de media)
- **Fecha/fuente:** 2026-07-06 · `docs/sesion-2026-07-06-precio-lid-reprogramacion.md` §2 [e4 EC-162; e3 EC-87 comparte la causa, ver MEM-08]
- **Estado:** vigente

### HUM-04 · `/bot off` enviado desde el grupo de escalaciones no funciona
- **Entrada/disparador:** comando dentro del grupo de escalaciones (exec 193150).
- **Falla previa:** la cadena LID del Kill-switch es solo-DM (excluye `participant`/`participantAlt`), así que el comando desde el grupo se ignora.
- **Esperado:** hoy el comando desde el grupo NO debe tener efecto (decisión: no cambiar la semántica sin pedido). Si Dra./Lucas lo piden, agregar `participant/participantAlt` como candidatos solo para el Kill-switch.
- **Capa:** nodo (`Kill-switch Check`)
- **Test:** SIN TEST (verificado manual con exec 193150)
- **Fecha/fuente:** 2026-07-06 · DEC "Kill-switch: cadena LID solo-DM"
- **Estado:** pendiente de decisión

### HUM-05 · `HTTP Send Admin Confirm` sin `JSON.stringify`: el admin no recibe la confirmación de `/bot off|on`
- **Entrada/disparador:** el admin manda `/bot off` o `/bot on`. Hallado por grep de "text/message sin JSON.stringify" en 32 workflows.
- **Falla previa:** la confirmación nunca llegaba, mismo tipo de escenario que Mariela (apagar el bot sin saber si funcionó).
- **Esperado:** tras `/bot off` y `/bot on` el admin recibe la confirmación en `chatJid`; el body del nodo usa `JSON.stringify` para `text`. Verificado con ciclo real off→on, bot restaurado en menos de 1 min.
- **Capa:** nodo (`HTTP Send Admin Confirm`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-18 · "Barrido sistemático", paso 1 [e2 EC-19]
- **Estado:** vigente

### HUM-06 · Mensaje humano (fromMe) persistido como `type:ai`: el LLM lo lee como propio
- **Entrada/disparador:** sábado 2026-05-09 12:52, la doctora respondió "Buen dia mama" desde la app del consultorio.
- **Falla previa:** LangChain serializa solo `content`; `additional_kwargs.source` es invisible para el modelo, que hidrataba el mensaje humano como output propio.
- **Esperado:** `Build fromMe AI memory` prefija el content con `[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria desde el WhatsApp del consultorio. NO es output tuyo...]:`. Regla dura #7: filtro fromMe universal (label humano + silencio), sin depender solo de Chatwoot. El bot no adopta el tono ni continúa la conversación de la secretaria.
- **Capa:** nodo (`Build fromMe AI memory`) + prompt
- **Test:** parcial: `tests/test_retencion_y_staff.js:129` (TAG con autor en el audio del panel); `tests/test_media_fromme.js` usa el TAG como fixture. El nodo `Build fromMe AI memory` en sí: SIN TEST.
- **Fecha/fuente:** 2026-05-09 · BUGS #3; FIXES Round 1 #2
- **Estado:** vigente
- **Riesgo de regresión:** la regla de prompt "MENSAJES HUMANOS EN TU MEMORIA: NO son tu voz, NUNCA imites ese tono" figura en `live_prompts.md` solo dentro de "Sub-Agent Urgencia" (nodo MUERTO). Los prompts curados de Agendar/Confirmar/General no la tienen (puede vivir en `prompts/v6_partials/memoria_historica.md`; verificar que esté inyectada en los tres).

### HUM-07 · Escalación del bot silencia su propia respuesta: el paciente escalado nunca recibe "Recibimos tu mensaje…"
- **Entrada/disparador:** toda escalación vía la tool `escalar_a_secretaria` de los sub-agents (6/6 desde 2026-08-30).
- **Falla previa:** el Helper `Helper - Notify Grupo` (`S5U6tSipzlgFHCkf`) aplicaba el label `humano` en forma sincrónica (~2 s) y `Re-check Humano`/`Gate Humano Final` cortaban la respuesta 1,4 s después; se suprimía el canned.
- **Esperado:** el webhook del Helper responde al instante (`responseMode` lastNode → onReceived), el aviso al grupo sale inmediato y el nodo `Esperar respuesta del bot (20s)` va antes de `Chatwoot Apply` en ambas ramas. Aserción: a +3 s el label `humano` NO está; a +25 s SÍ está; el paciente recibe el canned y luego silencio. Riesgo aceptado: en esos 20 s, un paciente que re-escribe rápido puede recibir una 2ª respuesta/escalación. Vigilar la primera escalación real.
- **Capa:** nodo (Helper, `scripts/apply_fix_helper_label_diferido.py`)
- **Test:** SIN TEST automatizado (verificación en vivo; `docs/triaje-fase2-diseno-2026-09-04.md` §9)
- **Fecha/fuente:** 2026-09-04 17:26 ART · current-state.md "Fase 2 … Hallazgo grave aparte"; DEC "Escalaciones: el label humano se aplica 20 s DESPUÉS del aviso"; BKL; OQ [fusiona e1 EC-61 + e3 EC-19]
- **Estado:** vigente
- **Riesgo de regresión:** el canned "Recibimos tu mensaje…" aparece en `live_prompts.md` solo en el nodo muerto Urgencia (urgencias ahora van al flujo Triaje). Los sub-agents vivos usan "Le transmito su caso/consulta a la secretaria…". Verificar que el canned de escalación de cada ruta viva sea el esperado y que el Gate no lo suprima.

### HUM-08 · Label `humano` en una conversación RESUELTA/pending silencia al bot indefinidamente
- **Entrada/disparador:** caso 2026-09-05 con Lucas: la primera versión del webhook `panel-toggle-bot` etiquetó las 8 conversaciones del contacto; quedaron 7 resueltas con `humano`. El "Test" de Lucas (18:29) y un E2E (20:00) murieron en `Humano Atendiendo`.
- **Falla previa:** `Verificar Label Humano`/`Re-check Humano`/`Gate Humano Final` miran TODAS las conversaciones del contacto (incluso resueltas), pero `Auto Reactivar` solo limpia las `open`: bloqueo indefinido. Además `Chatwoot Apply` del Helper etiqueta `payload[0]` (no la abierta), inconsistente con `CW Pick Conv`.
- **Esperado:** el satélite (`Label Chatwoot`) pone `humano` SOLO en la conversación abierta (o la más reciente) y `bot` quita `humano` de TODAS. Aserción verificada: `humano` → solo conv 272; `false` → ninguna con `humano`. Pendiente P2 (SENSIBLE): que los 3 chequeos del v6 consideren solo `status='open'`, o que Auto Reactivar limpie también las resueltas, y alinear `Chatwoot Apply` con `CW Pick Conv`.
- **Capa:** nodo (satélite/panel) + gate (sin blindar)
- **Test:** SIN TEST (verificado manual)
- **Fecha/fuente:** 2026-09-05/06 · current-state.md "Sesión 2026-09-05" punto 6; DEC "Inbox Live … Decisión 2"; BKL P2 "Gate humano"; `docs/roadmap-refactor-2026-09-06.md` B2; mapeo-read_redis_humano.md RISKS [fusiona e1 EC-55 + e3 EC-20 + e4 EC-163]
- **Estado:** parcialmente superado (escritores del panel corregidos); gate del v6 pendiente de decisión. Con Auto Reactivar a 24 h (HUM-09) el impacto de una resuelta etiquetada es mayor.

### HUM-09 · Auto Reactivar pasa de 1 h a 24 h: auto-silencio del bot por escalación hasta 24 h
- **Entrada/disparador:** decisión de Lucas "24hs para todo, confiar en el botón masivo" (modelo Intercom/Podium); pedido 2026-09-10; humano atiende y pasa 1 h sin actividad, o el bot se auto-silencia al escalar.
- **Falla previa:** antes el bot volvía a hablar a la hora (política de la Dra.: takeover 1 h). El label `humano` no distingue "humano real atendiendo" de "el bot se auto-silenció" (6 de 8 escalaciones desde el 30/8 terminaron así, incluidas 3 urgencias reales). Con 24 h, cualquier auto-escalación deja al paciente sin bot hasta 24 h salvo destrabe manual.
- **Esperado:** `ONE_HOUR = 24*3600` en `Auto Reactivar Bot` (workflow `fosfga62zNaN0qrx`; cron cada 15 min, que NO se toca). Mitigación: botón individual y masivo "Devolver todos al bot" del panel (excluye `no_bot`); `no_bot` como pin manual (0 conversaciones lo tienen); `HUMANO_MS` del panel alineado a 24 h. Si se vuelve problema real: corte corto (1-2 h) solo para escalaciones del bot, distinto del handoff humano real. Aplicado y verificado 8/8 en producción (`check_triaje.py` TODO SANO). Pregunta abierta: ¿la dominancia del modo "Humano Atendiendo" es política deliberada o TTLs largos?
- **Capa:** nodo (`Auto Reactivar Bot`, "Filtrar > 1 hora inactivas") + panel
- **Test:** SIN TEST (8/8 verificaciones del script antes/después del PUT)
- **Fecha/fuente:** 2026-09-10 (diseño, `docs/handoff-humano-24h-2026-09-10.md` §1-§3) / 2026-09-16 16:29 ART (aplicado, commit c6dbb6f); current-state.md "APLICADO: Auto Reactivar de 1h a 24h"; `docs/auditoria-propuestas-a3-2026-07-18.md` [fusiona e1 EC-17 + e3 EC-21 + e4 EC-167]
- **Estado:** vigente. Contradicción anotada: `docs/runbook.md` todavía dice 1 h y los casos fechados antes del 2026-09-16 hablan de 60-75 min; manda 24 h (más reciente).

### HUM-10 · Orden de despliegue de las 24 h: el panel (`HUMANO_MS`) debe salir junto con el apply de n8n
- **Entrada/disparador:** panel con `HUMANO_MS` en 1 h mientras n8n queda en 24 h (o al revés).
- **Falla previa:** un chat con label humano de hace 1-24 h mostraría el ícono de BOT mientras Chatwoot sigue en `humano`; el botón masivo "Devolver todos al bot" subestimaría su alcance (justo los chats más silenciados). Al revés: el panel muestra "modo humano" hasta 24 h después de que Chatwoot ya lo devolvió.
- **Esperado:** orden: (1) Lucas confirma el riesgo, (2) `--apply` en n8n, (3) deploy del panel con `HUMANO_MS=24h` en la misma ventana. Aserción: el estado bot/humano del panel coincide con el label de Chatwoot para chats de 1-24 h.
- **Capa:** infra (orden de despliegue) + panel
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-10 · `docs/handoff-humano-24h-2026-09-10.md` §9.1 [e4 EC-168]
- **Estado:** vigente (verificar que el deploy del panel con 24 h se hizo junto al apply del 2026-09-16)

### HUM-11 · Caso Esteban: el bot saludó "frío" en un chat iniciado por el staff; el gate determinístico por memoria no existe
- **Entrada/disparador:** 15/7 el staff había iniciado la conversación con el paciente Esteban y este respondió; el bot contestó con saludo genérico. En general: paciente que responde al staff después de más de 1 h.
- **Falla previa:** se creó `Check Humano Reciente (DB)` (24 h, sources `wa_outbound`/`human_takeover`), falló los tests (arranque de la caída de DB) y se hizo ROLLBACK; el nodo desapareció del v6 entre 16/7 y 18/7 sin registro. Hoy `Bot Activo?` tiene una sola condición (`hasHumanoLabel`): la defensa es solo prompt-layer.
- **Esperado:** restituir un gate determinístico por memoria: si hay fila `wa_outbound`/`human_takeover` en las últimas 24 h, el bot NO saluda ni responde sin escalar. Hasta entonces, el bot que ve mensajes `[ATENCION HUMANA…]` recientes no debe presentarse como si fuera el primer contacto (ver HUM-12, HUM-06).
- **Capa:** gate (pendiente) / prompt
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-15/18 · `docs/handoff-conversacion-completa-2026-07.md`; mapeo-read_redis_humano.md §3e [e4 EC-166]
- **Estado:** pendiente de decisión
- **Riesgo de regresión:** la defensa prompt-layer ("no imites ni continúes la conversación humana") está solo en Urgencia muerto en `live_prompts.md`; verificar que Agendar/Confirmar/General vivos la hereden.

### HUM-12 · Caso Santiago: el Router no tiene la regla "no te metás si hay un humano atendiendo"
- **Entrada/disparador:** Irina coordinaba a mano un cambio de turno del paciente Santiago; la mamá le contestó "Si, no hay problema"; luego "Holaaa" fue respondido por el bot con "En que puedo ayudarle?" y se puso a ofrecer cancelar/reprogramar.
- **Falla previa:** el saludo trivial del bot tapó el rastro del hilo humano abierto; ni el Router ni los sub-agents (Confirmar/Cancelar/Agendar/General) tienen la regla.
- **Esperado:** (a) regla en el Router con este caso de ejemplo: si el contexto reciente tiene `[ATENCION HUMANA…]`/mensajes de la secretaria sin cerrar, no clasificar como saludo/flujo del bot y silenciar o escalar; (b) en los sub-agents, un saludo propio del bot no cierra un hilo humano en curso. No debe responder "En que puedo ayudarle?" ni ofrecer cancelar/reprogramar.
- **Capa:** prompt (Router y sub-agents), no aplicado
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-04 · DEC "Fix ruido 'ya estás atendiendo'" (hallazgo pendiente) [e3 EC-17]
- **Estado:** pendiente de decisión (sigue sin aplicarse: el Router curado del 2026-10-04 en `live_prompts.md` no contiene la regla)

### HUM-13 · @lid "pelado" sin teléfono en chat atendido por staff: el bot saludó igual (exec 193142)
- **Entrada/disparador:** DM entrante con `@lid` sin `remoteJidAlt`/`senderPn`, paciente CeC; ventana 06/07 = 1 de 15 DMs (~7%).
- **Falla previa:** el phone no resuelve, no se detecta el label humano y el bot saluda en un chat atendido por staff.
- **Esperado:** hoy NO se aplica fail-closed ("bot mudo + aviso al grupo"): política de la Dra. = el bot siempre se presenta, prefieren bot presente a bot mudo. Fix real: tabla de mapeo lid↔teléfono (P2). Revisable si se repite la interferencia.
- **Capa:** otra (decisión de producto; hoy ninguna capa lo cubre)
- **Test:** "5/5 tests PASS" del fix LID-safe (BKL; archivo no nombrado, probablemente `scripts/test_lid_fix_e2e.py`). El caso residual: SIN TEST.
- **Fecha/fuente:** 2026-07-06 · DEC "Guard fail-closed para @lid sin teléfono: NO por ahora"; BKL P2; OQ [e3 EC-22]
- **Estado:** pendiente de decisión (revisable)

### HUM-14 · Reacción/emoji o multimedia desde el celular del consultorio apaga el bot y deja una fila permanente
- **Entrada/disparador:** la Dra./Irina reacciona con un emoji o manda una foto desde el celular del consultorio (fromMe, incluso por LID). Caso real 2/9: la reacción fromMe del 2/9 19:37Z generó la fila id 5912.
- **Falla previa:** marca humano y deja una fila `[ATENCION HUMANA …]` (source `wa_outbound`) que `Clear Old Memory` NUNCA borra y que le pide silencio al LLM "hasta que un admin diga /bot on"; `/bot on` no la limpia ni el label.
- **Esperado:** regla dura #7: todo saliente del número de la clínica que NO sea del bot aplica label humano + silence flag Redis (eso es lo correcto), pero la fila permanente no debe bloquear al bot tras `/bot on` ni tras el vencimiento del label. En demos nadie reacciona desde el celular del consultorio. Con Auto Reactivar a 24 h (HUM-09) una reacción puede dejar al paciente sin bot hasta 24 h.
- **Capa:** nodo (rama fromMe) + prompt
- **Test:** SIN TEST (`tests/test_media_fromme.js` cubre adjuntos del staff, no reacciones)
- **Fecha/fuente:** 2026-09-02/03 · mapeo-read_redis_humano.md §3e-§3g, RISKS [e4 EC-164; ver MEM-07]
- **Estado:** vigente (fila permanente sin resolver)
- **Riesgo de regresión:** la instrucción de prompt "silencio hasta /bot on" que lee la fila no está en los prompts vivos curados de Agendar/Confirmar/General; confirmar qué prompt la aplica hoy y que `/bot on` realmente reabra el bot.

### HUM-15 · Aviso de escalaciones al grupo roto del 05/08 20:44 al 06/08 ~13:55 (JID del grupo mal armado)
- **Entrada/disparador:** `Notify Grupo Send` en `Helper - Notify Grupo` (4 ejecuciones fallidas confirmadas).
- **Falla previa:** las escalaciones se logueaban en `escalaciones_log` pero el aviso por WhatsApp nunca llegó: el "number" intentaba hardcodear el JID del grupo como token JS inválido.
- **Esperado:** Evolution GO acepta el JID COMPLETO del grupo con sufijo `@g.us`. A un grupo NO se le aplica `.replace(/[^0-9]/g,...)` (a diferencia de los números de paciente). Aserción: tras una escalación, llega el aviso al grupo de derivaciones y existe fila en `escalaciones_log`.
- **Capa:** nodo (`Notify Grupo Send`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-06 mañana [e2 EC-29]
- **Estado:** vigente

### HUM-16 · `Human Takeover - Chatwoot`: nodo `Evolution API - Enviar a WA` con la misma expresión rota
- **Entrada/disparador:** webhook Chatwoot `message_created` (agente humano responde desde Chatwoot). El nodo no había disparado desde la migración (04/08 18:42) hasta el fix.
- **Falla previa (preventiva):** mismo patrón de expresión rota que HUM-05; la respuesta de la humana no llegaría al paciente.
- **Esperado:** nodo arreglado y verificado con un webhook Chatwoot sintético (`message_created`, número de prueba); el mensaje llega por WhatsApp.
- **Capa:** nodo (`Human Takeover - Chatwoot`)
- **Test:** SIN TEST (webhook sintético manual)
- **Fecha/fuente:** 2026-08-06 mañana [e2 EC-31]
- **Estado:** vigente

### HUM-17 · Webhooks públicos sin autenticación: inyección de mensajes (`human_takeover`) y gasto de OpenAI
- **Entrada/disparador:** POST sin secreto a `/webhook/chatwoot-takeover` o al webhook de `cron_resumen_clinico`.
- **Falla previa:** `human_takeover` permite inyectar mensajes arbitrarios al paciente y envenenar la memoria del bot; `cron_resumen_clinico` es DoS/cost-bombing trivial; en `human_takeover` un `continueOnFail` en el envío hace que la humana crea que respondió cuando el paciente no recibió nada (silent failure).
- **Esperado:** `httpHeaderAuth` o secret por query string en ambos webhooks (un POST sin credencial → 401/403 y NO se envía nada al paciente); validar la respuesta de Evolution y escalar al helper si falla el envío.
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-02 · `docs/sesion-2026-06-02-fixes-y-backlog.md` "Webhooks públicos sin auth", "Silent failures" [e4 EC-170]
- **Estado:** pendiente de decisión (no consta que se haya aplicado)

### HUM-18 · Helper: las escalaciones del flujo de cancelar no silenciaban al bot
- **Entrada/disparador:** escalación disparada desde el flujo de cancelar.
- **Falla previa:** el workflow Helper no ponía el silence flag en esas escalaciones; el bot seguía respondiendo tras escalar (bug funcional #1).
- **Esperado:** Helper parcheado en la auditoría A1; tras escalar desde cancelar, el bot queda silenciado (kill-switch PASS, v6 con 0 errores en 30 ejecuciones).
- **Capa:** nodo (Helper)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-18 · "Optimización auditoría — Track A" (A1) [e2 EC-59]
- **Estado:** vigente con contexto cambiado: el nodo "Sub-Agent Cancelar" del v6 está MUERTO; `cancelar_o_reprogramar` va al sub-workflow determinístico `5cAWJxiWJ50hxEq3`.
- **Riesgo de regresión:** verificar que las escalaciones del sub-workflow `5cAWJxiWJ50hxEq3` también pasen por el Helper (silence flag + aviso al grupo).

### HUM-19 · `Postgres - Save fromMe` sin `onError` en el camino crítico del silenciamiento
- **Entrada/disparador:** falla del INSERT de `Postgres - Save fromMe` (default `stopWorkflow`).
- **Falla previa:** `CW Set Label humano` nunca corre y el bot no se calla (comportamiento de HOY).
- **Esperado:** poner `continueRegularOutput` en el nodo para que el UPDATE degrade solo y el silenciamiento sea estrictamente más robusto. Anotado, NO hecho: PUT aparte con su propia prueba. Aserción: con el INSERT fallando, el label `humano` igual se aplica.
- **Capa:** nodo (pendiente)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-07 (tarde) · current-state.md "Adjuntos del STAFF (rama fromMe)" [e1 EC-36]
- **Estado:** pendiente de decisión

### HUM-20 · La cadena Media del staff no puede demorar el silenciamiento del bot
- **Entrada/disparador:** adjunto (foto/video) enviado por el staff desde el celular de la clínica (rama fromMe).
- **Falla previa (primer diseño, bloqueado):** el label `humano` de Chatwoot es lo ÚNICO que calla al bot en esta rama, y la cadena Media metía hasta 30 s (timeout de Storage) por delante.
- **Esperado:** la cadena de silenciamiento (`Es fromMe?`[0] → `Build fromMe AI memory` → `Postgres - Save fromMe` → 5 `CW *`) no se toca ni una arista; los 6 nodos Media nuevos cuelgan de la salida de `CW Set Label humano`.
- **Capa:** nodo (topología del workflow)
- **Test:** `tests/test_media_fromme.js` (69/69)
- **Fecha/fuente:** 2026-09-07 (tarde) · current-state.md "Adjuntos del STAFF (rama fromMe): REDISEÑADO" [e1 EC-30]
- **Estado:** vigente

### HUM-21 · Audio fromMe de la doctora se descartaba de la memoria
- **Entrada/disparador:** la doctora/secretaria manda una nota de voz desde el celular.
- **Falla previa:** `Build fromMe AI memory` descartaba el audio.
- **Esperado:** se loguea el placeholder `[mensaje multimedia enviado por la doctora/secretaria…]` con `was_multimedia`.
- **Capa:** nodo (`Build fromMe AI memory`)
- **Test:** parcial: `tests/test_media_fromme.js` usa ese placeholder como fixture; `tests/test_retencion_y_staff.js:128` cubre el audio del PANEL (`was_multimedia`). El nodo en sí: SIN TEST.
- **Fecha/fuente:** 2026-06-02 · `docs/sesion-2026-06-02-fixes-y-backlog.md` fix #11 [e4 EC-165]
- **Estado:** vigente

### HUM-22 · Doble disparo de escalación en el Gate Humano Final
- **Entrada/disparador:** el gate anti-Mariela (`Gate Humano Final`) dispara la escalación dos veces en algunos paths.
- **Falla previa:** ensucia los datos del Reportero v2 (propuesta A3 #2, ALTO, solo con review de Lucas). 7 de 11 escalaciones no silenciosas desde el 28/8 tienen su gemela `silencioso=true` 2-8 s después (ids 177/178 … 189/190).
- **Esperado:** una sola escalación por mensaje; deduplicar; el Reportero excluye fromMe/receipts de su definición de escalación.
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-18 y 2026-09-03 · `docs/auditoria-propuestas-a3-2026-07-18.md`; mapeo-read_redis_humano.md §3f [e4 EC-169]
- **Estado:** pendiente de decisión

### HUM-23 · Ruido en el grupo: avisos "ya estás atendiendo" (~50% de las escalaciones)
- **Entrada/disparador:** el bot detecta que un humano atiende y se calla, y mandaba WhatsApp al grupo (49 de 98 escalaciones entre 20/7 y 4/8; 55 ocurrencias = 48% sobre 40 pacientes reales con ficha según el análisis del 9-10/8).
- **Falla previa:** spam al grupo de la doctora. NO es ruido espurio de bug: es la secretaria atendiendo de verdad.
- **Esperado:** se corta la notificación WhatsApp y se mantiene el registro en `escalaciones_log`; `Helper - Notify Grupo` tiene nodo IF "Silencioso?" y solo los 2 nodos del caso "ya atendiendo" agregan `silencioso=true`. Urgencias/pagos/privacidad/dudas reales SIGUEN avisando. `/aprendizaje` las separa de la señal.
- **Capa:** nodo (`Helper - Notify Grupo`) + panel (`/aprendizaje`)
- **Test:** SIN TEST (verificado con POST de prueba real, fila borrada después)
- **Fecha/fuente:** 2026-08-04 (DEC "Fix ruido") y 2026-08-09/10 [fusiona e3 EC-18 + e2 EC-37]
- **Estado:** vigente. Nota: el aviso de este caso se cortó el 4/8; HUM-22 sigue produciendo gemelas `silencioso=true`.

### HUM-24 · Mensajes del número personal de Irina crean fichas de "paciente" falsas (caso "Ange")
- **Entrada/disparador:** un número con 7 mensajes desde el 21/7, solo notas `[ATENCION HUMANA]`; el contenido relayado ("Ange fijate si ese es el botón...", "planilla de compra") es Irina hablando de insumos.
- **Falla previa:** la instancia Evolution GO "raquel" está conectada al número personal de Irina; cualquier mensaje que mande desde ahí, a paciente o no, dispara el webhook y puede crear una ficha falsa. Viene desde el 21/7, no es de la migración.
- **Esperado:** sin resolver. Depende de si Irina usa ese número para proveedores o uso personal; si es así, separar el número del bot del personal. Mientras tanto, un fromMe a un contacto que no es paciente no debe crear ficha en `pacientes`.
- **Capa:** otra (decisión de negocio), con el filtro fromMe como base
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-06 madrugada (hallazgo aparte) [e2 EC-41; ver MEM-10]
- **Estado:** pendiente de decisión

### HUM-25 · Indicador bot/humano del panel desfasado hasta 5 min; enviar desde el panel deja el chat en modo humano
- **Entrada/disparador:** un humano escribe desde el celular o desde el panel.
- **Falla previa:** `humanTakeover`/`botActive` se calculaban solo con `conversaciones` (Logger, hasta 5 min): el panel mostraba "bot activo" aunque el bot ya estaba callado por el label. Enviar desde el panel deja el chat en modo humano (igual que escribir desde el celular) hasta Auto Reactivar (entonces 60-75 min, desde 2026-09-16 24 h) o el toggle.
- **Esperado:** el panel mira también `n8n_chat_histories` en vivo (`[ATENCION HUMANA…]`, sources `wa_outbound`/`human_takeover`) y `mensajes_entrantes_live` con `from_me=true`; el cambio de modo en sí ya era automático.
- **Capa:** panel (`nexora-whatsapp-agent`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-05 · current-state.md "Sesión 2026-09-05" puntos 3 y 6 [e1 EC-56]
- **Estado:** vigente (la duración del modo humano actualizada a 24 h; ver HUM-09/HUM-10)

### HUM-26 · Toggle bot/humano no inmediato (ventana ~30 min); la Dra. lo pide al toque
- **Entrada/disparador:** demo 2026-08-15: la Dra. quiere que el bot se calle "al toque" cuando un humano escribe, y que el panel lo exponga.
- **Falla previa:** hoy espera la ventana de verificación de ~30 min.
- **Esperado:** toggle inmediato (P2): en cuanto un humano escribe (celular, Chatwoot o panel), el bot queda silenciado sin esperar la ventana. Aserción: un mensaje del paciente enviado segundos después de un mensaje humano NO recibe respuesta del bot.
- **Capa:** nodo + panel
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-15 · BKL "Reunión 2026-08-15"; `docs/reunion-2026-08-15-dra-raquel.md` C [fusiona e3 EC-23 + parte e4 EC-171]
- **Estado:** pendiente de decisión (P2). Posible solapamiento con la rama fromMe → label inmediato (HUM-27); verificar qué tramo sigue con latencia.

### HUM-27 · Human Takeover (Evolution GO + Chatwoot): comportamiento esperado al responder un humano y al resolver
- **Entrada/disparador:** evento `message_created` outgoing de `sender.type==='user'` sin `source_id`; evento `conversation_status_changed` a `resolved`.
- **Falla previa:** ninguna observada (caso de especificación).
- **Esperado:** `message_created` humano → set label `humano` + reenviar a WhatsApp + guardar en memoria con source `human_takeover`; `resolved` → label `bot`. Rama `fromMe=true` del v6 (staff desde WA Web/Mobile, que Human Takeover no ve): aplica label `humano` con 5 nodos (`CW Search Contact → Get Conversations → Pick → Set Label`) con `continueOnFail` en los HTTP; el label de Chatwoot es la fuente ÚNICA de verdad del silencio; label redundante cuando el agente usa Chatwoot es inocuo.
- **Capa:** nodo (Human Takeover + rama fromMe del v6)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-05-12 (FIXES Round 2 #5; `docs/architecture.md` "Human Takeover"; BUGS "No trackeados") y 2026-08-15 (`docs/reunion-2026-08-15-dra-raquel.md` C; mapeo-read_redis_humano.md §3e) [fusiona e3 EC-16 + parte e4 EC-171]
- **Estado:** vigente

### HUM-28 · Rate limiter cuenta los mensajes fromMe del staff en la cuota del paciente
- **Entrada/disparador:** el staff escribe muchos mensajes al paciente.
- **Falla previa:** consumen la cuota de 10 mensajes/15 min del paciente.
- **Esperado:** el Rate Limit no cuenta fromMe del staff (P2 pendiente). Aserción: tras 10 mensajes del staff, el siguiente mensaje del paciente NO es rate-limiteado.
- **Capa:** nodo (Rate Limit)
- **Test:** SIN TEST
- **Fecha/fuente:** backlog P2, vigente al 2026-09 · BKL P2 [e3 EC-24]
- **Estado:** pendiente de decisión

### HUM-29 · Cada escalación en cuentas de prueba/demo re-aplica el label `humano`
- **Entrada/disparador:** demos o pruebas con el número de Lucas tras cada escalación.
- **Falla previa:** el label `humano` (conv 272) se vuelve a aplicar tras cada escalación y deja el chat sin bot.
- **Esperado:** tras cada escalación en demo, `scripts/limpiar_numero_demo.py --phone … --apply --solo-label`; limpieza completa según regla dura 9 (55 filas de memoria, `escalaciones_log` 189/190, `triaje_urgencias_log` 3, 5 filas de `conversaciones`). Con 24 h (HUM-09) el chat de prueba queda mudo un día si no se limpia.
- **Capa:** otra (proceso / script de limpieza)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-04 · current-state.md "Fase 2 (piloto en el v6)" [e1 EC-62; ver MEM-01]
- **Estado:** vigente

### Cobertura
29 casos; 26 SIN TEST total, 3 con cobertura parcial o total (HUM-20 completa en `tests/test_media_fromme.js`; HUM-06 y HUM-21 parciales). Ningún test automatizado cubre el Kill-switch en `tests/` (solo `scripts/test_lid_fix_e2e.py`).
Huecos más peligrosos: (1) HUM-01/02/03/05, el Kill-switch (regresión silenciosa por backspace ya ocurrió y duró dos meses) sin test en `tests/`; (2) HUM-08/HUM-09/HUM-14, label humano en resueltas + 24 h + fila permanente, pueden dejar al paciente sin bot por un día o indefinidamente sin que nadie lo vea; (3) HUM-11/HUM-12/HUM-06, el bot interviene sobre un hilo humano abierto, con defensa solo en prompt y las reglas de "voz humana" presentes solo en un nodo muerto.

---

## memoria_contexto

### MEM-01 · Mensajes de test viejos y residuos de pruebas contaminan el contexto de chats reales
- **Entrada/disparador:** pruebas con un teléfono real (Lucas incluido) dejan filas en `n8n_chat_histories`, `conversaciones`, `escalaciones_log`, `triaje_urgencias_log`, label humano en Chatwoot y Redis (`chat_buffer`, `ratelimit`, `triaje`). El teléfono de prueba comparte contacto Chatwoot con 9 contact_inboxes y una conversación con historial real; filas `[TEST 72h]` de recordatorios y notas internas se ven en `Build Router Context`.
- **Falla previa:** el 2026-09-04 un E2E de Claude en el chat de Lucas dejó un mensaje de test viejo en la memoria y contaminó una prueba real del triaje.
- **Esperado:** al terminar CUALQUIER prueba con teléfono real se limpian memoria (`n8n_chat_histories`), logs y label humano EN EL MISMO TURNO con `scripts/limpiar_numero_demo.py`; `python scripts/check_triaje.py` antes de cualquier PUT; regla #8 (no afirmar que funciona sin E2E completo). Aserción: tras la limpieza, 0 filas del teléfono de prueba en las tablas y Redis. Limitación conocida: `limpiar_numero_demo.py` aún no toca `media_entrantes` ni Storage.
- **Capa:** otra (proceso)
- **Test:** `scripts/check_triaje.py` (no es test de `tests/`)
- **Fecha/fuente:** 2026-09-04/05 · `.claude/CLAUDE.md` reglas 8-9; DEC "Robustez verificable"; mapeo-read_redis_humano.md §3g; `docs/retencion-y-uso-2026-09-07.md` §7 [fusiona e3 EC-86 + e4 EC-197]
- **Estado:** vigente

### MEM-02 · Doble respuesta: el bot manda el mismo mensaje dos veces (buffer / doble disparo)
- **Entrada/disparador:** feedback de la Dra. del 3/6 10:06: "Está enviando doble respuesta" (caso Cande); mensajes en 2 burbujas separadas.
- **Falla previa:** el buffer que concatena mensajes dispara dos veces, o el subagente emite y el router reemite.
- **Esperado:** `Buffer: Wait` pasó de 10 s a 22 s (2/6); `Soy el último?` compara el `key_id` del último elemento de la lista; `Preparar Mensaje Final` entrega UNA sola salida por turno (dedupe/lock por conversación). Aserción: 2 mensajes del paciente dentro de la ventana generan una sola respuesta. Dos burbujas separadas por más de 22 s se leen como 2 turnos (bajar a ~12 s es decisión de producto). Si una ejecución muere antes de `Buffer: Limpiar`, el buffer huérfano (sin TTL) se pega al próximo mensaje.
- **Capa:** nodo (buffer Redis)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-02/03 · `docs/sesion-2026-06-02-fixes-y-backlog.md` #4; `docs/Asiri - Feedback Raquel 03-06.pdf` punto 2; mapeo-read_redis_humano.md RISKS; `docs/roadmap-refactor-2026-09-06.md` B2 [e4 EC-202]
- **Estado:** vigente (buffer huérfano sin TTL: pendiente de decisión)

### MEM-03 · La memoria (`n8n_chat_histories`) diverge de lo realmente enviado al paciente
- **Entrada/disparador:** el triaje reemplaza la respuesta del sub-agent (video + caption en vez del canned de Urgencia); un video por `/send/media` no deja rastro en ninguna tabla.
- **Falla previa:** el sub-agent escribe su output CRUDO en la memoria al terminar (antes de Sidecar/Banlist/Formatting): memoria y panel dirían "Recibimos tu mensaje…" mientras el paciente recibió el video.
- **Esperado:** el nodo `Triaje: Persistir` corre y persiste filas con el mismo shape que `Postgres - Save fromMe`: `human` (source `triaje_paciente`) + `ai` (`[VIDEO ENVIADO — …]`, `[TRIAJE — PREGUNTA GUIADA …]`, `[TRIAJE CIERRE]`, `[TRIAJE ESCALADO]`). NO usar source `reminder_note` ni content de menos de 3 caracteres o igual a un intent (el Logger lo descarta); NO duplicar la fila `human` si luego corre un sub-agent. El sub-agent viejo no debe escribir una respuesta que no se envió.
- **Capa:** nodo (`Triaje: Persistir`)
- **Test:** `tests/test_triaje_nodos.js` (SQL de persistencia: `chr(36)`, comillas)
- **Fecha/fuente:** 2026-09-04 · mapeo-read_salida_memoria.md; `docs/triaje-fase2-diseno-2026-09-04.md` §4 [e4 EC-199]
- **Estado:** vigente, con redacción desactualizada: "el triaje corre ANTES de Sub-Agent Urgencia" ya no aplica; `urgencia_dolor` va directo al flujo Triaje y "Sub-Agent Urgencia" es un nodo MUERTO. La aserción (nada se persiste que no se envió) sigue en pie.

### MEM-04 · `[NO_REPLY]` literal persistido como AIMessage y visto por el LLM en turnos siguientes
- **Entrada/disparador:** el agente devuelve `[NO_REPLY]` (exec 13142).
- **Falla previa:** LangChain lo persiste y el LLM lo ve en turnos siguientes (copia el silencio o se confunde).
- **Esperado:** `PG - Delete NO_REPLY` (DELETE selectivo del último AIMessage) en la rama `Tiene respuesta? FALSE`; `Build Router Context` filtra contenidos `[NO_REPLY]`; el Logger también los descarta. Aserción: tras un turno `[NO_REPLY]`, no queda fila AI con ese texto. Cierres ("ok", "gracias", "estoy llegando") devuelven `[NO_REPLY]` exacto.
- **Capa:** nodo (`PG - Delete NO_REPLY`)
- **Test:** SIN TEST ("sin shadow real"; `tests/test_canned_sidecar.py` y `tests/test_gate_pago_tratamiento.py` solo prueban el PASSTHROUGH de `[NO_REPLY]` en Sidecar/gate)
- **Fecha/fuente:** 2026-05-09/12 · BUGS #25; FIXES R2 #7 [e3 EC-85]
- **Estado:** vigente
- **Riesgo de regresión:** el prompt curado de General dice para avisos de llegada "responde brevemente confirmando o devolvé `[NO_REPLY]`", mientras la orden de la Dra. (2026-06-03, solo en el nodo muerto Urgencia) era `[NO_REPLY]` EXACTO y sin confirmar. Verificar que General/Agendar/Confirmar devuelvan siempre `[NO_REPLY]` ante "en camino", "ya llegué", "estoy a dos cuadras".

### MEM-05 · `obtener_historial_paciente`: cuándo SÍ llamarla y no confundirse con la voz del bot
- **Entrada/disparador:** "confirmo" sin recordatorio reciente; "ya lo hablamos"; "como te dije"; "ese turno", "lo de la ortodoncia"; "el turno de mi hija"; "dale", "el lunes está bien" ambiguos.
- **Falla previa:** n/a (regla de prompt).
- **Esperado:** llamarla (últimos 20 mensajes, todos los canales) cuando la memoria está vacía sin consulta nueva, hay referencias a algo no presente, continuidad ambigua, antes de escalar por falta de contexto y ante persona/turno sin precisar. NO llamarla en consulta nueva clara, urgencia ni multimedia/comprobante. Los mensajes `rol=human` son la secretaria/doctora: NO adoptar su tono ni continuar su conversación; si la secretaria manejaba algo → `escalar_a_secretaria` con resumen.
- **Capa:** prompt (`memoria_historica`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026 · `prompts/v6_partials/memoria_historica.md` [e4 EC-201]
- **Estado:** vigente
- **Riesgo de regresión:** `live_prompts.md` no menciona `obtener_historial_paciente` en Agendar/Confirmar/General curados; verificar que la partial siga inyectada y que el Sub-Agent Confirmar la use cuando "confirmo" llega sin recordatorio (hoy usa `consultar_recordatorios_abiertos` + `ver_turnos_paciente`). Ver HUM-06.

### MEM-06 · `Build Router Context`: últimos 6 mensajes, único contexto del Router
- **Entrada/disparador:** ctx del Router en cada mensaje (`PACIENTE:`/`BOT:`/`SYSTEM:` separados por `---`).
- **Falla previa:** corre ANTES de `Clear Old Memory` (puede incluir mensajes stale) y antes del check de label humano; el Router NO tiene memoria LangChain; una fila `ai` insertada a mano aparece como `BOT: …`; el sufijo ` [MEDIA:…]` suma 26 caracteres. Raíz de Mariela causa 3: "está incómoda, no come" se clasificó como `consulta_general` en vez de urgencia porque el Router no veía la memoria.
- **Esperado:** filtra contenidos iguales a un intent, `[CONTEXTO%` y `[NO_REPLY]`; recorta al episodio actual; los mensajes humanos del path fromMe aparecen como `BOT: [ATENCION HUMANA …]`. Aserción: ctx de máximo 6 mensajes sin intents ni `[NO_REPLY]` ni `[CONTEXTO`.
- **Capa:** nodo (`Build Router Context`)
- **Test:** `tests/test_triaje_nodos.js` (ctx reconstruye y recorta al episodio actual)
- **Fecha/fuente:** 2026-09-04 · mapeo-read_router.md §2; mapeo-read_urgencia_path.md §6; `.claude/CLAUDE.md` incidente 2026-05-09 [e4 EC-200]
- **Estado:** vigente
- **Riesgo de regresión:** el Router curado (2026-10-04) lista dolor, sangrado, hinchazón, alambre/bracket y "qué tomo", pero no señales indirectas ("no come", "está incómoda", niño que se cayó). Verificar con un caso del tipo Mariela y que se conserve la REGLA DE CONTINUIDAD DE FLUJO.

### MEM-07 · `Clear Old Memory` preserva `wa_outbound`/`human_takeover`/`reminder_note` y borra el resto a los 7 días
- **Entrada/disparador:** sesión cuya última fila tiene más de 7 días (`Handle Stale Session`).
- **Falla previa:** las filas `[ATENCION HUMANA …]` (source `wa_outbound`) no se borran nunca y le piden silencio al LLM "hasta que un admin diga /bot on"; una fila `triaje_video` se pierde a los 7 días (aceptable: el registro duradero es `triaje_urgencias_log`).
- **Esperado:** para limpiar una demo, borrar al menos las filas con source `wa_outbound`/`human_takeover`; si el bot debe recordar "ya mandé la opción 1" entre sesiones, persistir en el log y no en la memoria.
- **Capa:** nodo (`Clear Old Memory`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-03/04 · mapeo-read_redis_humano.md §3e, §3g; mapeo-read_salida_memoria.md KEY FACTS [e4 EC-198; ver HUM-14]
- **Estado:** vigente

### MEM-08 · Normalización de `session_id` no maneja `+5493…` ni `@lid`
- **Entrada/disparador:** phone con `+` o con `@lid`.
- **Falla previa:** `Edit Fields` solo hace `phone.replace('@s.whatsapp.net','')`.
- **Esperado:** potencial `phone.replace(/[^0-9]/g,'')` para `+`; OJO: el fix @lid del 2026-07-06 NO strippea (los dígitos del LID no son el teléfono) y NO devuelve phone vacío (colapsaría todas las sesiones @lid y `lk=""` en Dentalink podría matchear todo). Fallback idéntico al legacy.
- **Capa:** nodo (`Edit Fields - Extraer Datos`)
- **Test:** "5/5 tests PASS" (BKL; archivo no nombrado); SIN TEST en `tests/`
- **Fecha/fuente:** 2026-05-09 / 2026-07-06 · BUGS #31; DEC "Fix @lid por cadena de candidatos" [e3 EC-87; ver HUM-03]
- **Estado:** vigente

### MEM-09 · Pregunta sobre el turno propio: leer con herramientas, nunca inventar
- **Entrada/disparador:** "¿Cuándo es mi turno?", "¿Tengo turno?", "¿A qué hora es?", "¿Qué día tengo?".
- **Falla previa:** n/a (regla de prompt; el modelo erra el día de la semana a partir de fechas numéricas).
- **Esperado:** `buscar_paciente_dentalink` (lk-last10) + `ver_turnos_paciente`; con turno próximo activo (`id_estado` != 1 y != 14, fecha futura): "Su próximo turno es el [N de Mes] a las [HH:MM] hs." SIN día de semana; sin turno: "No veo turnos próximos a su nombre. Si quiere agendar, escribame 'quiero un turno'."; varias fichas → preguntar a nombre de quién. Sub-Agent General es solo lectura. No se calcula el día de la semana (solo se copia si viene escrito, p. ej. del bloque de `buscar_horarios`).
- **Capa:** prompt
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06 · `prompts/v6_partials/general_funcion.md`, `general_preguntas_turnos.md` [e4 EC-204]
- **Estado:** vigente
- **Riesgo de regresión:** ALTO. El General curado solo dice "consulta con `ver_turnos_paciente`. Responde informando día y hora." Se perdieron: el canned sin turno, el filtro `id_estado` != 1/14, la regla "SIN día de semana", el match por `lk` last10 y el manejo de varias fichas. La regla del día de semana en `live_prompts.md` solo sobrevive en el nodo muerto Urgencia. Verificar cada una.

### MEM-10 · El Logger copia `n8n_chat_histories` → `conversaciones` una sola vez y crea fichas fantasma
- **Entrada/disparador:** cron de 5 min del Logger; teléfonos sintéticos de tests; filas de menos de 3 caracteres; INSERT manual con `session_id` nuevo.
- **Falla previa:** el Logger crea ficha en `pacientes` para CUALQUIER fila (también `ai`): un INSERT manual con session_id nuevo crea un "Paciente WhatsApp" falso. Descarta vacío, `[NO_REPLY]`, labels de intent y menos de 3 caracteres; la copia no se corrige jamás; el panel fusiona 3 fuentes con dedupes por timestamp/texto (bug del `order ASC`, "hay que hacer F5", metadata perdida). El Logger a 30 s causó el 90% de la carga del incidente de Supabase (15-17/7, bajado a 5 min).
- **Esperado:** en tests usar solo teléfonos reales o limpiar después; solo mensajes `rol=user` deberían crear ficha. Propuesta B1: una tabla canónica `mensajes` escrita por todos los emisores y retirar el Logger de 5 min. El cursor del Logger es `MAX(chat_history_id) FROM conversaciones`.
- **Capa:** nodo + otra (rediseño)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-16 / 2026-09-04 / 2026-09-06 · `docs/handoff-conversacion-completa-2026-07.md`; mapeo-read_salida_memoria.md; `docs/roadmap-refactor-2026-09-06.md` B1 [e4 EC-203; ver HUM-24, MEM-11]
- **Estado:** pendiente de decisión (B1 sin aplicar)

### MEM-11 · Intento de fix del Logger (no crear fichas falsas) rompió `Insert Conversacion` para todos
- **Entrada/disparador:** se agregó un IF entre "Parse mensajes" y "HTTP - Upsert Paciente" para que solo mensajes `rol=user` creen ficha.
- **Falla previa:** dos caminos convergiendo en un solo puerto rompieron la referencia posicional `{{ $json[0].id }}`. Error Postgres `invalid input syntax for type bigint: ""` en TODOS los items.
- **Esperado:** revertido al backup PRE. Si se retoma, pasar `paciente_id` como campo del item en cada rama antes de converger, sin depender del "nodo inmediato anterior", y con E2E real. El cursor del Logger es `MAX(chat_history_id) FROM conversaciones`, NO `last_synced_chat_id` (vestigial).
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-06 madrugada, "Intento de fix del Logger — REVERTIDO" [e2 EC-40]
- **Estado:** vigente (el fix de fichas falsas sigue pendiente; ver MEM-10)

### MEM-12 · Memoria LangChain rota del 29/4 al 2/5: wrapper anidado vs plano
- **Entrada/disparador:** INSERTs con `{type, data:{content}}` (formato v0.2).
- **Falla previa:** el bot ignoraba las filas mal formateadas al hidratar la memoria.
- **Esperado:** SIEMPRE formato plano v0.3+ `{type, content, additional_kwargs,…}` en cualquier INSERT manual o de nodo (incluidos los de Triaje y fromMe, ver MEM-03).
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-04-29 a 2026-05-02 · BUGS #9 [e3 EC-84]
- **Estado:** vigente

### MEM-13 · `last_bot_msg` guardado cortado a 300 caracteres
- **Entrada/disparador:** el bloque de turnos mide ~230 caracteres + el saludo.
- **Falla previa:** `last_bot_msg` se cortaba en "Por la tarde", perdiendo parte del bloque ofrecido.
- **Esperado:** se guarda el bloque completo para poder reconocerlo en el turno siguiente (Step 0b "lote ofrecido" y "no se repite el lote").
- **Capa:** nodo
- **Test:** parcial: `tests/test_turnos_formato.js` (4.c CANREP, usa `BLOQUE_VIVO.slice(0, 300)` en el historial); no verifica el campo `last_bot_msg` en sí.
- **Fecha/fuente:** 2026-09-07 · current-state.md "APLICADO: formato de turnos pedido por la Dra. Raquel" (bugs latentes) [e1 EC-24]
- **Estado:** vigente

### MEM-14 · Residuo de test (escalación sin phone) se coló en el reporte semanal
- **Entrada/disparador:** `escalaciones_log` id=113, del test de Notify Grupo del 06/08, quedó sin phone y sin borrar y apareció en el reporte semanal.
- **Falla previa:** dato de test contaminando una salida real (misma familia que la regla dura 9).
- **Esperado:** limpiar los datos de prueba en el mismo turno (quedó borrado). Aserción: el reporte semanal no contiene filas de `escalaciones_log` sin phone.
- **Capa:** otra (proceso)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-11 · "Barrido sistemático" [e2 EC-26; ver MEM-01]
- **Estado:** vigente

### MEM-15 · Paciente con identidad `@lid` nueva dice "se los envié a la secretaria" y el bot no tiene contexto
- **Entrada/disparador:** "se los envié a la secretaria", desde una identidad @lid nueva sin historial.
- **Falla previa:** no es bug: el bot no sabe qué mandó el paciente.
- **Esperado:** coincide con la decisión del 6/7 sobre @lid (ver HUM-13); backlog aparte, no se toca sin resolver la identidad de fondo. Sugerencia: ante falta de contexto, `obtener_historial_paciente` y luego `escalar_a_secretaria` en lugar de inventar.
- **Capa:** otra (decisión)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-09/10 [e2 EC-36]
- **Estado:** pendiente de decisión

### MEM-16 · Weekly Learning y Cleanup contaminaban la KB (domingo)
- **Entrada/disparador:** workflow Weekly Learning `B7IS4EVvxUAnGDXi`; Cleanup `En0A5lXd3Whb5yFy` (full-scan que borraba 0 filas, con credencial PG borrada).
- **Falla previa:** contaminación de la KB.
- **Esperado:** ambos desactivados con backup; la KB solo se edita por el panel. Aserción: ninguno de los dos está activo.
- **Capa:** otra (workflow desactivado)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-18 · A1 [e2 EC-60]
- **Estado:** vigente. Nota: MEM-17 (2026-05-09) menciona un "cron cleanup" que filtra por contenido; si es `En0A5…`, ese cleanup ya no corre y la limpieza de memoria la hace `Clear Old Memory` (MEM-07).

### MEM-17 · `n8n_chat_histories` sin índice por `session_id` y sesión basura de test `@lid`
- **Entrada/disparador:** sesión basura de test con ID `@lid`.
- **Falla previa:** `Check Session Age` lento; el cron cleanup filtra por contenido, no por `session_id`, y no toca la sesión.
- **Esperado:** `CREATE INDEX idx_chat_histories_session_id`; borrado manual de la sesión basura.
- **Capa:** infra (DB)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-05-09 · BUGS #30; BKL P3 [e3 EC-88]
- **Estado:** pendiente de decisión (P3; no consta si el índice se creó)

### MEM-18 · Tablas Supabase `pacientes`/`conversaciones` inexistentes (404 silencioso)
- **Entrada/disparador:** `Supabase - Buscar Paciente` y 4 nodos más.
- **Falla previa:** la credencial apuntaba al proyecto Nexora research; 404 silencioso siempre.
- **Esperado:** desconectar los 5 nodos; Dentalink = fuente única de verdad de pacientes/turnos (lead vs paciente lo maneja Agendar).
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-05-09 (verificado 2026-05-11) · BUGS #29; FIXES R2 #3 [e3 EC-89]
- **Estado:** superado por la migración al Supabase v3 (2026-07-18): `pacientes` y `conversaciones` hoy existen y el Logger (`HTTP - Upsert Paciente`, `Insert Conversacion`) y el panel los usan (ver MEM-10, MEM-11). Contradicción resuelta a favor de lo más reciente; Dentalink sigue siendo la fuente de verdad de turnos.

### MEM-19 · Lección: no agregar heurísticas de texto sobre datos que no reflejan el mensaje del paciente
- **Entrada/disparador:** generaliza EC-15 de la auditoría del 2026-08-18 (un blindaje agregado sin test real).
- **Falla previa:** el blindaje inspeccionaba datos (la fecha buscada) y no lo que dijo el paciente, y generó más falsos positivos que los casos que cubría.
- **Esperado:** antes de agregar detección heurística por texto, verificar qué datos le llegan realmente al nodo y probarla con casos reales (positivos y negativos).
- **Capa:** otra (regla de trabajo)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-18 · "Barrido sistemático", Lección [e2 EC-21]
- **Estado:** vigente

### Cobertura
19 casos; 14 SIN TEST total, 5 con cobertura parcial o completa (MEM-03 y MEM-06 en `tests/test_triaje_nodos.js`; MEM-13 parcial en `tests/test_turnos_formato.js`; MEM-01 solo con `scripts/check_triaje.py`; MEM-08 con tests fuera de `tests/`).
Huecos más peligrosos: (1) MEM-09, la lectura de turno propio perdió reglas al curar General y no tiene test (riesgo de inventar día de semana o turnos); (2) MEM-05/HUM-06, la regla de "mensajes humanos no son tu voz" y `obtener_historial_paciente` no figuran en los prompts vivos curados; (3) MEM-04/MEM-02, `[NO_REPLY]` y la doble respuesta sin ningún test de integración (avisos de llegada: General curado permite responder).
