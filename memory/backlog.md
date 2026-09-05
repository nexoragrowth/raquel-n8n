# Backlog — raquel-n8n

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

## P1 — Panel: mensajes entrantes al instante ("Inbox Live", propuesto 5/9, esperando OK)
- [ ] Hoy el mensaje del paciente aparece en el panel 30–45 s después de enviado (la memoria
      lo escribe al final del turno). `scripts/apply_inbox_live.py` (dry-run listo): tabla
      `mensajes_entrantes_live` + nodo Postgres rama muerta en el v6 + merge en `chat-data.ts`
      / `conversaciones-data.ts` como burbuja pendiente. SENSIBLE (1 nodo en el v6, sin
      salidas). Después: bajar el buffer de 22 s es decisión de producto aparte.
- [x] 2026-09-05 Bug `order ASC` del tail en `chat-data.ts` arreglado y deployado (`cc642c7`).

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
