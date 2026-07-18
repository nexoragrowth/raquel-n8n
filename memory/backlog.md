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
- [x] 2026-07-06 Precio consulta $50.000 en prod (testeado E2E).
- [x] 2026-07-06 Fix LID-safe extracción de teléfono + pushName (5/5 tests PASS).
- [x] 2026-07-06 Fix crítico kill-switch (backspace U+0008 → `\b`; roto desde 09/05).
- [x] 2026-07-06 Health check completo post-cambios (0 errores, 9 satélites sanos).
- [x] 2026-07-06 Diagnóstico reprogramaciones/familias (10 gaps, plan 3 fases).
- [x] 2026-07-06 Snapshot Sub-WF CancelarReprogramar al repo.

## Reunión Dra. Raquel 2026-07-14 (ver docs/reunion-2026-07-14-dra-raquel.md)
- [ ] **P1: Triaje de urgencias con videos** — clasificar tipo, preguntas guiadas, pedir foto, enviar video, scoring severidad. BLOQUEADO: Raquel envía videos + fraseo
- [ ] **P1: Reportero v2 "aprendizaje semanal"** — mapear escalaciones + urgencias, sugerir KB faltante ESPECÍFICA, enviar al grupo nuevo (absorbe el pendiente del reportero que cuenta mal)
- [ ] P2: Dashboard nexora-whatsapp-agent (`Desktop/proyectos/nexora-whatsapp-agent`): UI WhatsApp-like, leído/no-leído, toggle bot/humano inmediato, métricas Dentalink, servicios/KB editables en UI
- [ ] P2: Cuando Raquel cree el grupo nuevo (ella+Lucas+Irina): actualizar destino de escalaciones si cambia el group id
- [ ] P3: Landing page: secciones flujo de tratamiento faltantes + sección Transformaciones (antes/después) post-hero o post-proceso + navbar
- [x] 2026-07-14: VERIFICADO que el flujo agenda-céntrico YA funciona (cancelado id_estado=1 filtrado en GET; confirmado id_estado=18 filtrado en IF skip-confirmados) → no más on/off manual del workflow, feriados resueltos vía confirmación anticipada. Comunicar a Iri/Raquel
- [x] Cerrado: "revisar lógica de feriados" — no requiere infra (decisión de la reunión + verificación técnica)

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
