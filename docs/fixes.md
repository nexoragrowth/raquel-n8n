# Rounds de endurecimiento

Documenta los dos rounds de fixes aplicados al v6 post-incidente. Cada fix tiene script reusable en `scripts/` y backup pre/post en `workflows/history/` (gitignored).

---

## Round 1 — 2026-05-09: Post incidente Mariela

### El incidente

Mariela (paciente real, mamá de Martina, expansor maxilar caído) escribió al consultorio un sábado:
- 12:52 doctora le respondió "Buen día mamá" desde la app del consultorio (`fromMe=true`)
- 12:53 doctora tiró `/bot off` → **ignorado silenciosamente**
- 13:02 Mariela: "está incómoda, no come, solo líquidos"
- 13:05-13:08 bot le dijo: *"venite con Martina lo antes posible, traigan el expansor y el DNI. Balcarce 37, 2do piso. Los esperamos."*
- 13:08 Mariela respondió: *"Bien, ahora salimos para la clínica"* — clínica cerrada un sábado
- 13:15 doctora pidió detenerlo. Lucas apagó manualmente. Casi accidente real.

### Root causes (auditoría `audit-memoria-v6.md`)

1. Kill-switch chequeaba `!fromMe && ADMINS[phone]`. Con admin escribiendo desde multi-device del consultorio (`fromMe=true`), el comando se ignoraba siempre.
2. Mensajes `fromMe=true` se persistían con `type:ai` sin marcador. El LLM los hidrataba como output propio.
3. `Router - Clasificar Intent` NO estaba conectado a `Postgres Chat Memory.ai_memory`. Clasificaba con un solo mensaje sin contexto → "está incómoda, no come" fue a `Sub-Agent General` en vez de `Urgencia`.
4. Prompts laxos sin banlist explícito de instrucciones operativas/médicas.
5. **Causa raíz oculta** (descubierta en `audit-base-conocimiento-v6.md`): sección "REFERENCIA secretaria REAL" del prompt tenía LITERAL `"Listo, te queda confirmado para el martes 5 a las 17. Te esperamos."` mientras R22 prohíbe `te esperamos`. El bot copió el ejemplo del prompt.

### Fixes aplicados (5 capas + Banlist regex)

| # | Fix | Script | Estado |
|---|---|---|---|
| 1 | Kill-switch estricto: `!fromMe && phone IN ADMINS` con admin phones whitelisted (Lucas, Irina, Raquel) | `apply_4_fixes.py` | 🟢 |
| 2 | `Build fromMe AI memory`: prefijar content con `[ATENCION HUMANA - ...]:` explícito | `apply_4_fixes.py` | 🟢 |
| 3 | Conexión `Postgres Chat Memory.ai_memory → Router - Clasificar Intent` | `apply_4_fixes.py` | 🟢 |
| 4 | `HTTP Send Admin Confirm` apunta a `chatJid` (origen del comando) en vez de `adminPhone` | `apply_4_fixes.py` | 🟢 |
| 5 | **Banlist Validator** — nodo Code nuevo con 22 regex entre Formatting Agent → Split. Si match → reemplaza output por canned escalación. | `apply_banlist.py` | 🟢 |

**Test validador**: 13/13 PASS contra los 5 mensajes reales de Mariela del incidente.

**v6 desactivado al cierre del día.** Doctora notificada con plan de remediación.

---

## Round 2 — 2026-05-12: Endurecimiento MVP

### Contexto

Después de la auditoría completa de la base de conocimiento (`audit-base-conocimiento-v6.md`) salieron 10 hallazgos críticos adicionales. Lucas decidió ir por endurecimiento profundo antes de shadow + cutover.

Filosofía del round: **bot funcional > bot conversador**. El LLM puede ignorar prompts; las capas determinísticas no.

### Fixes aplicados (10 cambios, todos PUT 200)

| # | Fix | Script | Detalle |
|---|---|---|---|
| 1 | **Auto-layout Dagre del workflow** | `apply_layout_v6_dagre.py` + `layout_dagre.js` | 97 nodos reposicionados left-to-right por depth topológico. AI children debajo de agent padre. Mismas libs que usa n8n internamente. |
| 2 | **Cron Recordatorios `0 13 * * 1-5`** (era `* *`) | `apply_cron_recordatorios_fix.py` | Workflow `7RqTApkvVavRmq3R`. Fix de pacientes del martes recibiendo 3 recordatorios (vie+sáb+dom convergían). |
| 3 | **5 nodos Supabase rotos desconectados** (`Buscar Paciente`, `Existe Paciente?`, `Crear Paciente`, `Guardar Msg Usuario/Asistente`) | `apply_disconnect_supabase.py` | Tablas no existen en el Supabase apuntado. Lead vs paciente lo maneja sub-agent Agendar via Dentalink. Re-cableo: `Bot Activo? FALSE → Check Session Age`. |
| 4 | **R0 anti-conversación** prefix al TOP de los 5 sub-agents | `apply_r0_anti_conversational.py` | `+1362 chars` c/u. "AGENTE FUNCIONAL — 4 funciones específicas. NO conversás. Si dudás → escalá." |
| 5 | **Chatwoot label cuando `fromMe=true`** | `apply_chatwoot_label_fromme.py` | 5 nodos en cadena después de `Postgres - Save fromMe`: search contact → get conversations → pick active → POST label `humano`. Cubre WA Web + WA Mobile. continueOnFail en HTTPs. |
| 6 | **RAG `buscar_conocimiento` desconectado** + `Embeddings OpenAI` removido | `apply_disconnect_rag.py` | Apuntaba a base de Nexora (88 rows marketing competidores, 0 clínicos). Vector dim mismatch 1536/384 hacía RPC 400 silencioso siempre. |
| 7 | **Filter `[NO_REPLY]` post-hoc** | `apply_filter_no_reply.py` | Nodo nuevo `PG - Delete NO_REPLY` entre `Tiene respuesta? FALSE → Descartar [NO_REPLY]`. DELETE selectivo del último AIMessage con content `[NO_REPLY]` para esa session. Limpia contexto LLM. |
| 8 | **`escalar_a_secretaria` description nueva** (270 → 708 chars) | `apply_escalar_description.py` | Sin "precios/presupuestos". Aclara cuándo SÍ usar (urgencia, queja, obra social, fuera de 4 funciones) y cuándo NO (precio/horario/dirección/alias = canned). |
| 9 | **`Clear Old Memory` selectivo + `Handle Stale Session` limpio** | `apply_clear_memory_selective.py` | SQL nueva: `DELETE WHERE session_id=$1 AND $2::boolean=true AND COALESCE(message::jsonb->'additional_kwargs'->>'source','') NOT IN ('wa_outbound','human_takeover','reminder_note')`. Params bound. Plus: `Handle Stale Session` ya no referencia `Supabase - Buscar Paciente` (desconectado en #3). |
| 10 | **Prep/restore script para tests shadow** | `test_prep_restore.py` | `--prep`: disable 7 nodos (Send/Typing/HTTP Send Admin + 4 tools Dentalink write). `secretaryPhone` → Lucas. Webhook path → `evolution-v6-test`. Activa helpers + v6. `--restore <backup>`: deshace todo. |

### Test sintético post-round 2

100 tests sintéticos del 9/5 corridos contra el v6 endurecido: **82/100 PASS**.

- 7 categorías al 100%: agendar, autoresponder, B2B, cierre, injection, multimedia, urgencia.
- 3 categorías con regresiones: saludo primera (0/5), confirmar (2/10), cancelar (6/8).

Análisis de regresiones:
- **Saludo primera (0/5)**: R0 demasiado agresivo. Cae en `[NO_REPLY]` cuando debería dar saludo corto + invitación a agendar. Algunos fails son falsos negativos del check viejo (E1/E4 dieron output razonable pero check viejo esperaba onboarding completo).
- **Confirmar (2/10)**: con tools `confirmar_turno` disabled (modo test), el sub-agent llama `ver_turnos_paciente` y después escala. Comportamiento esperado en test mode, no regresión real.
- **G8** (bug crítico descubierto): bot dijo `"queda confirmado. La esperamos en Balcarce 37, 2do piso"` y **Banlist no lo bloqueó**. El regex tiene `te esperamos` pero no `la esperamos`. **Gap real, hay que ampliar el regex.**

### Lo que falta en Round 2

Antes de shadow:

1. **Banlist gap**: agregar `/la esperamos/i`, `/le esperamos/i`, `/los esperamos/i` al regex existente.
2. **R0 menos agresivo** en saludos cold: permitir respuesta corta + invitación, no caer en `[NO_REPLY]` reflexivo.
3. Re-correr tests sintéticos → objetivo 95+/100.

---

## Lecciones documentadas (no recurrentes)

Estos bugs ya no aplican porque la lección quedó internalizada en el proyecto. Documentados en [`bugs.md`](bugs.md) #9-15:

- **LangChain memory wrapper FLAT vs nested** — siempre formato v0.3+ flat.
- **Cron n8n offset** — `(hora_arg + 5) UTC` para días Argentina, no depende de DST.
- **Nodos intermedios pisan `$json`** — referenciar al origen explícito.
- **Preservar `webhookId`** en PUT (regla #3 del proyecto).
- **Evolution API miente** en algunos casos — confirmar con destinatario, no con response.
- **`continueOnFail` oculta fails** — inspeccionar output de cada nodo, no status global.
- **Dentalink PUT anular** solo acepta `{id_estado:1}` — cualquier campo extra → 400.
