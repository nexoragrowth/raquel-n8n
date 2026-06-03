# Sesión 2026-06-02 — Fixes aplicados + backlog

## Fixes aplicados hoy (16, todos con backup + verify)

### Críticos (impactaban runtime / paciente / observabilidad)

1. **Cron de recordatorios — memory save**. `7RqTApkvVavRmq3R` / nodo `Guardar en Chat Memory`. Strings con newlines literales dentro de `'...'` rompían el parse JS → recordatorios NUNCA quedaban en `n8n_chat_histories`. Fix: template literals (backticks). E2E testado con exec real (workflow `TEST - Cron Memory Save Fix (Lucas)`). Validación final mañana 8 AM ARG con corrida real.
2. **Sub-WF Cancelar — ghost appointments**. `5cAWJxiWJ50hxEq3` / nodo `Step 5: Decidir Accion Ejecutable`. Switch del Step 6 no tenía case `reservar_solo` → cuando paciente aceptaba slot ofrecido sin turno previo, el bot decía "Listo, reservando" pero Dentalink jamás creaba la cita. Fix safe: cambiar a `'escalar'` con canned correcto (la auto-reserva queda como TODO).
3. **Gate Error Tecnico — URL placeholder**. v6 main / nodo `Gate Error Tecnico`. La URL era `<EVOLUTION_URL>/message/sendText/raquel` literal → la escalación a Lucas siempre fallaba con DNS lookup + try/catch silent. Fix: POST al helper `notify-grupo` (mismo patrón Round 8).

### Wording / coherencia (pedidos de la Dra)

4. **Buffer Wait 10s → 22s** (caso bot doble respuesta — caso Cande).
5. **Wording "por aca" → "por este medio"** (en canneds).
6. **Canned comprobante** con horario de atención.
7. **Saludo Asiri con emoji 🤗**.
8. **Barrido "Irina" sueltos visibles al paciente** (v1 + v2 Sub-WF Cancelar).
9. **Router clarificación** (preguntas clarificatorias mantienen flow).
10. **General read tools** (ver_turnos_paciente, buscar_horarios, buscar_paciente_dentalink agregados a Sub-Agent General).
11. **Audio fromMe** — `Build fromMe AI memory` ahora loguea con placeholder `[mensaje multimedia enviado por la doctora/secretaria...]` en vez de descartar.
12. **Canneds con horario** en PRIVACIDAD / sin turno / anulado / cancelar sin turno.
13. **NO_ENROSCARSE / Gate Error Tecnico / Format Sub-WF Output** con wording Dra (2026-06-02): *"Hola! Soy Asiri🤗, la secretaria virtual de la Dra. Raquel Rodríguez. Le envío la información a la secretaria, ella le responderá en su horario de atención. Gracias!"*
14. **"asistente virtual" → "secretaria virtual"** en partials (`memoria_historica`, `r0_full`, `r0_general`, `saludos_solos`, `general_funcion`) + sub-agents v6 (rebuild + apply).
15. **`obtener_historial_paciente.toolDescription`** "asistente" → "secretaria virtual".
16. **Router confirmación amplia** — red de seguridad: AFIRMACION DE ASISTENCIA exhaustiva (asistiremos, vamos, claro, dale, etc.) + REGLA DE ORO "ante duda → confirmar_post_recordatorio".

## Auditoría multi-workflow (workflow tool, 8 workflows revisados)

- 25 critical/high confirmados con verify adversarial sobre 68 findings totales.
- 7 de 8 workflows en rojo.
- Resultado salvó dos bugs nuevos no conocidos (Sub-WF Cancelar ghost appointment + Gate Error URL).
- Un finding del auditor (regex `\b` mal escapado en Sub-WF Cancelar Step 4) resultó **falso positivo** — los regex usan `^(...)` no `\b`.

## Backlog pendiente — NO urgente pero hay que hacer

### Seguridad (rotar tokens)

- **JWT service_role Supabase** hardcoded en 3 nodos v6_main + querystring en URLs (loguea en traces OpenAI). Exp 2089, acceso admin total saltea RLS.
- **Token Chatwoot** hardcoded en 6+ nodos entre v6 + helper_notify_grupo + human_takeover + auto_reactivar + JSONs del repo.
- Acción: rotar ambos en Supabase / Chatwoot, migrar a credenciales nativas n8n (`supabaseApi`, `httpHeaderAuth`), borrar JWT de URLs (debe ir por header).

### Webhooks públicos sin auth (DoS / inyección)

- `cron_resumen_clinico` `BO1cdE8xmqln4IeO` webhook POST sin auth → DoS / cost-bombing trivial (cada request gasta OpenAI).
- `human_takeover` `w7BBpZeEwZnpCX1q` webhook público → permite inyectar mensajes arbitrarios al paciente y envenenar memoria del bot.
- Acción: agregar `httpHeaderAuth` o secret query string a ambos.

### Discrepancias cron real vs documentado

- `cron_recordatorios` corre **10 AM ARG**, no 9 AM como dice el nombre. Investigar.
- `auto_reactivar` corre cada **15 min**, no 1 h como dice CLAUDE.md. Investigar.

### Silent failures restantes (patrón Round 8)

- `cron_recordatorios` `Enviar WhatsApp` con `continueOnFail` sin error branch → marca como enviado lo que Evolution rechazó.
- `human_takeover` `continueOnFail` en envío → humana cree que respondió pero paciente no recibió nada.
- Acción: validar response antes de marcar como enviado + escalar al helper si falla.

### Otros (menor)

- **Auto-reserva en Sub-WF Cancelar** (case `reservar_solo` con nodo HTTP nuevo a Dentalink POST /citas). Hoy escalamos como safe — la feature de reserva automática post-cancelación queda como ticket.
- **Regex de Step 4 Sub-WF Cancelar** matchea prefijos: "sino" matchearía `isAffirm` por el `si+`. Edge case raro pero existe.
- **Banlist Validator** dice *"derivando a la Dra. Raquel para que te responda personalmente"* — falso (responde Iri). Cambiar wording.
- **Sub-Agent Urgencia canned** *"Recibimos tu mensaje. Le pasamos a la doctora..."* — ver si unifica con el wording Asiri o queda WAI porque escala al grupo.

### Backlog viejo (mantenido)

- B opcional: wording recordatorio guiando paciente ("CONFIRMO o SI ASISTO").
- Memoria "sin emojis" excepción canneds curados.
- Limpiar KB Supabase (requiere OPENAI_API_KEY).
- Cron L-V verificación fin de semana.
- Patron #2 social.
- Test en vivo (chat de Lucas tiene label humano — sacarlo).
- Irina unifica 3 duplicados clínica (Colque / Jonas / Romanela).
- Observer V1 (cron heurísticas + WhatsApp alerts para fallos silenciosos).

## Próxima sesión — primer paso

Validar mañana 8 AM ARG (corrida real del cron de recordatorios). Revisar exec en n8n + verificar que `n8n_chat_histories` tenga las 2 filas (recordatorio + NOTA INTERNA) por cada paciente con turno 24/72h.

Si funciona → bug del cron oficialmente cerrado.
Si no → revisar el output del nodo `Guardar en Chat Memory` y `Postgres - Insert Memory`.
