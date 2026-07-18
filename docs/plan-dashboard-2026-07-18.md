# Plan Dashboard (panel Raquel) — 2026-07-18

> Salida del mapeo de `Desktop/proyectos/nexora-whatsapp-agent` (4 agentes) + gap analysis
> contra el MVP de la reunión 14/7. Informe completo del workflow en la sesión 18/7.

## Hallazgos clave

1. **El panel YA fue diseñado para Raquel**: modo espejo `organizations.read_only`,
   sync Chatwoot+Dentalink, toggle bot/humano vía label Chatwoot, comentarios en el
   código que nombran a "Asiri" y al workflow n8n "Auto Reactivar Bot".
2. **Hay un preview VIVO**: `https://nexora-whatsapp-agent.vercel.app` (Vercel de
   Valentino, plan Hobby, sin dominio custom) apuntando al Supabase standalone
   `xmcyidheaqgjhlgcihia` con espejo de los datos reales de Raquel.
3. Repo limpio (main=origin, commit 31419d7 11/7), typecheck 0 errores, deps OK local.
4. UI reutilizable casi entera: chat-view (burbujas + toggle optimista), lista de chats,
   calendario que YA parsea estados Dentalink, KPIs del dashboard, auth completo.
5. ⚠️ `ENCRYPTION_KEY` de los tokens espejo la tiene Valentino — irrelevante si se
   abandona el espejo (decisión de abajo).

## Decisión arquitectónica (recomendada)

**Dual-Supabase, SIN espejo**: auth/login quedan en el proyecto standalone (no se toca
`lib/auth.ts` ni migraciones); se agrega cliente server-only para v3
(`lib/supabase/v3.ts` + envs `V3_SUPABASE_URL`/`V3_SERVICE_ROLE_KEY`) y las páginas
leen v3 DIRECTO. Chau sync/cron/duplicación (mandato Lucas: sin requests de fondo).
El `DentalinkClient` del panel queda como fuente en vivo de `/citas`.

**Contrato panel↔n8n** (2 webhooks nuevos con header secreto, porque Evolution/Redis
son VPS-only):
- `POST /webhook/panel-toggle-bot {telefono, humano}` → Redis silence flag +
  `pacientes.human_takeover`. PRERREQUISITO: verificar qué gate lee realmente el v6.
- `POST /webhook/panel-send-human {telefono, mensaje}` → Evolution + insert
  `conversaciones` rol=human + takeover automático.

## Fases

- **F1 — Solo-lectura sobre v3** (~3-5 días, cero riesgo, cero n8n): cliente v3 +
  `/conversaciones` por telefono (polling 3-5s, no Realtime), `/dashboard` con métricas
  directas (mensajes/día, escalaciones, confirmaciones, recordatorios), `/citas` vía
  Dentalink en vivo. Deploy al Vercel de Lucas. Mostrable a Raquel.
- **F2 — Interacción** (~3-4 días): leído/no-leído (columna `pacientes.panel_last_read_at`),
  skin WhatsApp, webhooks n8n toggle+send, footer de envío. Reemplaza Chatwoot para el staff.
- **F3 — KB/servicios editables** (~2-3 días): página `/conocimiento` CRUD sobre
  `knowledge_base` con re-embedding al guardar (text-embedding-3-small, texto
  "categoria | titulo\ncontenido" — mismo pipeline del bot → impacto instantáneo);
  recrear tabla `servicios` + guardrail "tratamientos sin precio publicado". OJO: los
  canneds de precios viven en el prompt del v6 — repuntarlos a servicios/KB (diff+OK).
- **F4 — Weekly learning + citas bot-vs-manual** (~2-3 días): tabla `reportes_semanales`
  + página `/aprendizaje` (fallback: escalaciones agrupadas por motivo); log de citas
  creadas por el sub-WF Agendar para el KPI bot vs manual. Depende del Reportero v2.

Total panel ≈ 2 semanas efectivas. Camino crítico externo = 3 cambios chicos en n8n
(webhooks F2, canneds F3, log Agendar F4), todos con backup+diff+OK.

## Gaps sin fuente hoy (decidir si importan)

- "Citas agendadas por bot vs manual": requiere log en el sub-WF Agendar (no existe).
- "Minutos ahorrados": sin fuente real (constante × mensajes, o dropear — vanity).
- Leído/no-leído: no existe en ningún schema — columna nueva en v3 (F2).
- Formato teléfono: panel usa "+549…", v3 "549…" — normalización única obligatoria.
