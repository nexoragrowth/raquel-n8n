# Propuestas A3 de la auditoría total (18/7) — NO aplicar sin review

> Salida de la auditoría de 13 agentes (workflow wwros9tph). Fases A1 (aplicada) y A2
> (bloqueada por clasificador) están en `memory/current-state.md`. Esto es la **Fase A3**:
> cambios de mayor riesgo que tocan grafo/prompt del v6 — solo propuestas, con review de Lucas.

## A3 — solo propuesta (no tocar hoy)

1. **v6 · "Check Supabase" en Health Check (ALTO, el más valioso)**: el Health Check NO
   monitorea Supabase — por eso las 2 caídas (8/7 y 15-17/7) fueron invisibles. Agregar un
   nodo que pingee la base v3 y alerte al grupo. Recablea grafo → review.
2. **v6 · Gate Humano Final — doble disparo de escalación (ALTO)**: el gate anti-Mariela
   puede disparar la escalación dos veces en algunos paths, ensuciando los datos del
   Reportero v2. Toca el jsCode del gate del incidente → solo con review de Lucas.
3. **v6 · Clear Old Memory no-op por mensaje (ALTO)**: hay 2 diseños en competencia para el
   mismo desperdicio; consolidar en el refactor v7.
4. **DB · pooler transaction-mode :6543 (ALTO)**: los 19 nodos PG usan session-mode (:5432).
   Pasar a transaction-mode (:6543) reduce el churn de conexiones (backlog P1). Con Lucas,
   horario muerto, plan de rollback de credencial.
5. **Sub-WF Cancelar · Step 3.5b LLM Acceptance (ALTO)**: el "skip implícito" funciona pero
   es sucio; limpiar en el refactor.
6. **Health Check · canal de alerta fuera de banda (ALTO)**: si Evolution cae, la alerta que
   va por Evolution puede no llegar. Segundo canal (email/otro).

## Resto de A2 pendiente (MEDIO, aplicable con OK)

- **Get Paciente Context muerto** (`scripts/apply_audit_a2_get_paciente.py`, listo): el
  clasificador de seguridad lo frenó por tocar los systemMessage del v6. Ahorra ~100-200
  queries/día. Correr con OK explícito de Lucas.
- **Dedup nodos sombra del Logger** (http_upsert/http_insert/code_upd duplicados): con backup
  + re-test. El Logger funciona; hacerlo en una ventana tranquila.
- **Barrido del token Chatwoot hardcodeado** (`1vwA3ihq...`, 14+ lugares en v6 + Auto
  Reactivar + Human Takeover + Helper): mover a credencial + rotar. Requiere acceso VPS.
- **Health Check · alerta real Dentalink/Evolution** (hoy fallo silencioso): MEDIO, bajo riesgo.
- **Config externa (Lucas)**: quitar `MESSAGES_UPDATE` de los eventos de la instancia
  Evolution `raquel` (hoy ~85% del tráfico del v6 son ACKs basura que mueren en el Validator
  pero inflan la DB interna de n8n). NUNCA tocar la URL del webhook (evo-webhook-v2).

## Contradicciones resueltas por la síntesis (para no re-proponer)

- El índice único `conversaciones.chat_history_id` SÍ existe (no hay 42P10 inminente).
- Recordatorios corre 08:00 ART (confirmado por Lucas; ni 9 ni 10).
- NO desconectar `buscar_conocimiento`: la KB v3 curada está validada E2E (el ítem del
  backlog/CLAUDE.md quedó obsoleto).
- Auto Reactivar: la cadencia de 15 min NO se toca (pedido de la Dra: takeover 1h).
