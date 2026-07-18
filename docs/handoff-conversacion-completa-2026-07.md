# Handoff — conversación completa (06→16 julio 2026)

> Volcado de la sesión larga de Claude Code que corrió desde `C:\Users\not` (no desde el repo).
> Lucas la migra a una sesión nueva en `raquel-n8n`. Este doc + `memory/` = continuidad total.
> Orden: lo MÁS urgente arriba. Para el detalle técnico de cada fix ver `docs/sesion-*.md`
> y `memory/{current-state,decisions,backlog,open-questions}.md`.

---

## 🚨 LO PRIMERO AL RETOMAR: incidente Supabase abierto (16/7)

Ver `memory/current-state.md` (bloque "INCIDENTE ABIERTO"). Resumen:
- Postgres del proyecto `ujfyapjwrdhnvqdvsjwp` rechaza conexiones (`econnrefused` en el
  pooler `aws-1-us-west-2.pooler.supabase.com:5432`). REST responde 401 normal → proyecto
  VIVO, no pausado; solo la vía Postgres cae. Lucas vio "exceso de requests" en el dashboard.
- Bot mudo para pacientes; staff atiende manual.
- Plan de choque YA aplicado: Logger apagado + bajado a 5 min (era 30s = 90% de la carga),
  Cleanup apagado + a 1x/día, rollback del gate humano. Carga -90%.
- Pasos numerados para resolver están en `current-state.md`. Scripts listos en `scripts/`:
  `test_conexion_fresca.py`, `recovery_backfill.py`.
- Decisión de fondo pendiente con Lucas: **NO quiere gastar** → candidato = migrar Postgres
  al VPS de Hostinger (costo 0, sin cuotas free-tier, latencia 200ms→1ms). Alternativa cara:
  Supabase Pro USD 25/mes.
- Reenviar la captura de Supabase (llegó corrupta) para saber qué cuota exacta se excedió.

---

## Infraestructura del proyecto (mapa mental)

Bot WhatsApp para Áurea Odontología (Dra. Raquel, Jujuy). Caso bandera pagante de Nexora.
- **n8n** self-hosted `n8n.raquelrodriguez.com.ar` (VPS Hostinger). API pública header
  `X-N8N-API-KEY`. El `list` de workflows da 0 (scoping) → GET/PUT por ID. Retención execs ~72h.
- **Evolution API 2.3.7** `evo.raquelrodriguez.com.ar`, instancia `raquel` (WhatsApp).
- **Supabase Nexora v2** `ujfyapjwrdhnvqdvsjwp` (Postgres: memoria, conversaciones, pacientes,
  recordatorios, KB). El proyecto viejo `dchztroesbpwxxkfywwu` fue BORRADO el 8/7.
- **Dentalink** (agenda médica, fuente de verdad de turnos), **Chatwoot** (label humano), **Redis**.
- Workflows clave: v6 `O155MqHgOSaNZ9ye` (bot, 120 nodos), Sub-WF CancelarReprogramar
  `5cAWJxiWJ50hxEq3`, Logger `xsXeHp7WLXnFQc3o`, Recordatorio 48HS `7RqTApkvVavRmq3R`,
  Cleanup `En0A5lXd3Whb5yFy`, Health Check `Yjl6kyLnALhIfbFX`, Auto Reactivar `fosfga62zNaN0qrx`,
  Human Takeover `w7BBpZeEwZnpCX1q`, Helper Notify Grupo `S5U6tSipzlgFHCkf`.
- Credencial Postgres n8n nueva: "Postgres Supabase Nexora v2" id `EWhpNhb6tkGg1OTp`.
- Reglas duras: cero PUT sin backup en `workflows/history/`; preservar `webhookId: evo-webhook-v2`;
  PUT sólo acepta name/nodes/connections/settings/staticData; nunca prender/apagar sin OK.

## Cronología de lo hecho (06→16 julio)

- **06/07**: precio consulta $40k→$50k (E2E ✓). Fix LID-safe extracción de teléfono + campo
  pushName (estaba vacío siempre) — 5/5 tests. Fix CRÍTICO kill-switch: la regex tenía un
  BACKSPACE literal (U+0008) en vez de `\b`, `/bot off|on|status` roto en silencio desde el
  09/05 — reparado. Health check completo (9 satélites sanos). Diagnóstico reprogramaciones/
  familias (10 gaps, plan 3 fases en `docs/sesion-2026-07-06-*.md`) — NO aplicado, espera OK.
- **08/07**: el amigo de Lucas borró el proyecto Supabase. Migración completa a v2: credencial
  nueva, tablas, **secuencias de ID reseteadas a max+1** (lección clave post-restore), función
  match_documents recreada a knowledge_base, 22 cambios en 7 workflows, apikeys viejos removidos
  de URLs. Verificado E2E. Bot revivido.
- **09/07**: alias con datos bancarios completos, cuota mensual $70k + regla de desambiguación
  cuota/consulta/control, KB exportada para validación de la Dra (`docs/kb-validacion-dra-*.md`).
- **10-14/07**: recordatorios apagados/prendidos por pedido (feriados/partido). El 14/7 se
  disparó manual vía webhook interno `trigger-recordatorios-manual` → primeras escrituras
  reales en `recordatorios_enviados` (8 citas → 4 enviados) ✓.
- **14/07**: reunión con la Dra procesada → `docs/reunion-2026-07-14-dra-raquel.md`. VERIFICADO
  que el flujo agenda-céntrico YA funciona (filtros id_estado!=1 cancelado, !=18 confirmado) →
  no más on/off manual del workflow; feriados se resuelven confirmando en agenda.
- **15/07**: caso Esteban (bot saludó frío en chat iniciado por staff). Se creó gate humano
  determinístico → falló los tests (era el arranque de la caída de DB, no el fix) → ROLLBACK.
  Tablas fundacionales creadas: peticiones (SLA 24hs), escalaciones_log, urgencias_log, servicios.
  Logging de escalaciones agregado al Helper Notify Grupo (`apply_escalaciones_logging.py`).
- **16/07**: incidente Supabase (arriba).

## Scope nuevo pactado en la reunión (backlog P1/P2)

1. **Triaje de urgencias con videos** (P1): clasificar tipo, preguntas guiadas, pedir foto,
   enviar video, scoring severidad. BLOQUEADO: Raquel manda videos + fraseo.
2. **Reportero v2 "aprendizaje semanal"** (P1): mapear escalaciones (ya hay tabla
   `escalaciones_log`) + urgencias, sugerir KB faltante específica, mandar al grupo nuevo.
   El reportero viejo cuenta mal (mezcla fromMe/receipts). NUNCA se ubicó el workflow del
   reportero — quizá corre fuera de n8n o se purga; buscarlo.
3. **Dashboard** `nexora-whatsapp-agent` (P2): OJO — NO es un panel sobre este bot n8n. Es un
   PRODUCTO Next.js aparte (agente propio Anthropic + WhatsApp Cloud API + tablas en inglés,
   modo espejo Chatwoot/Dentalink). Ref Supabase distinto (`xmcyidheaqgjhlgcihia`). Lucas quiere
   que el dashboard edite servicios/precios que alimenten la KB REAL del bot n8n, deje peticiones
   con SLA 24hs, y exponga lo agéntico (modelos LLM por sub-agente, prompts, workflows). Requiere
   PUENTE dashboard↔n8n/Supabase-v2 que HOY NO EXISTE. Mapa completo del dashboard: pedírselo al
   agente Explore que ya lo analizó, o re-explorar.
4. Grupo nuevo Raquel+Lucas+Irina (ya existe según Lucas) → actualizar destino de escalaciones
   si cambia el group id (hoy `120363407321448469@g.us`).
5. Landing page: secciones flujo de tratamiento + sección Transformaciones (P3, otro proyecto).

## Recomendación de modelos (auditada 06/07, sin aplicar)
Costo LLM irrelevante (~USD 17/mes). El problema es latencia (~67s/respuesta, ~35s LLM).
Cambios de bajo riesgo sugeridos: Formatting Agent gpt-5-mini→Haiku 4.5 (-7s/respuesta),
Banlist Shadow judge→Haiku. NO tocar Agendar/Confirmar/Cancelar (gpt-5, escriben turnos reales,
historial de incidentes). Sonnet se probó en junio y se revirtió (motivo no documentado).

## Higiene / deudas
- Rotar la API key de n8n (quedó en historial de chats viejos).
- Health Check NO monitorea Supabase (por eso las 2 caídas fueron invisibles) → agregar ping DB.
- Credenciales huérfanas en n8n del proyecto borrado (Postgres account viejo, Supabase Bearer viejo).
- Falta `SUPABASE_SERVICE_ROLE_KEY` en `.env` (la credencial de n8n la tiene; para scripts locales).
- Preguntas abiertas en `memory/open-questions.md` (quién arregló el Health Check el 05/07, etc.).
