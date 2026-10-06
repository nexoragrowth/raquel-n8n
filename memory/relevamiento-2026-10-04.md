# Relevamiento — Agente WhatsApp Dra. Raquel (Áurea Odontología Estética)

Fotografía del sistema al **2026-10-04**. Verificada contra n8n en vivo (GET de solo lectura), no contra la memoria vieja.
Reemplaza a `current-state.md` (160 KB de bitácora). Los edge cases viven aparte, en `memory/edge-cases/`.

## 1. Estado de hoy

- **El bot está ACTIVO en producción** (v6 `O155MqHgOSaNZ9ye`, 163 nodos, `webhookId evo-webhook-v2` intacto, actualizado 2026-10-04 19:27Z). El `.claude/CLAUDE.md` dice que está desactivado: está desactualizado.
- Hoy se curaron los prompts de Router, Sub-Agent Agendar y Sub-Agent General (reducción ~90%). Confirmar quedó en 3.377 chars. **Ninguna de estas curaciones tiene test de regresión**; ver §5.
- Datos del bot en Supabase v3 (sa-east-1, proyecto nuevo del 2026-07-18). El v2 está muerto.
- Canal: Evolution GO (instancia `raquel`). Agenda: Dentalink. Memoria de chat: Postgres (LangChain). Buffer, kill-switch y rate limit: Redis. Etiquetas humano/bot: Chatwoot.
- Panel (repo hermano `nexora-whatsapp-agent`, Next.js): chat en vivo, citas, métricas, KB editable. Lee directo del Supabase v3.

## 2. Qué hace y qué no (scope MVP cerrado)

**Sí hace:** agendar turnos nuevos · recordar turnos (cron aparte) · confirmar/cancelar/reprogramar tras el recordatorio · info canned (precio de consulta, horarios, dirección, alias) · triaje de urgencias con video (texto 100% canned, el LLM solo clasifica).

**Siempre escala al grupo:** urgencia/dolor/sangrado/aparato salido, foto dental, comprobantes de pago (recibe y deriva, no valida monto), obra social, quejas, pedido de hablar con una persona, cualquier otra cosa.

**Jamás (banlist regex post-output):** "venite" / "los esperamos" / "ahora mismo a la clínica" · instrucciones operativas o médicas ("guardá", "traé", "tomá X") · diagnóstico u opinión ("no te preocupes", "es normal") · dar la dirección física como confirmación de cita (solo si el paciente la pide) · afirmar que un turno existe sin verificar con `ver_turnos_paciente`. Sin visión (la foto es solo respaldo adjunto), sin RAG abierto, sin sub-agents creativos.

**Reglas de negocio vigentes:** consulta $50.000 (dinámica desde la KB, id 21, editable en el panel) · cuota mensual $70.000 (KB id 36; según la curación de hoy el General ya la lee dinámica) · valores de septiembre: el panel manda · nunca precio fijo de tratamiento · primera consulta: efectivo o transferencia, no tarjeta, se paga el día de la consulta · cancelación con 48 h; no-show abona igual · horarios dinámicos desde la KB (id 20) · recordatorios lun–vie a +2 días hábiles, sin detección de feriados, y no se apagan con `/bot off` · el staff cancela y confirma EN Dentalink (la agenda es la fuente de verdad) · el bot se presenta siempre como bot.

**Reglas de proceso (las que costaron un incidente):** nunca prender/apagar el v6 sin OK de Lucas · diff + backup antes de todo PUT · preservar `webhookId` · cada regla crítica en ≥2 capas (prompt + gate) · no decir "funciona" sin correr el camino de punta a punta · limpiar residuos de test en el mismo turno (`scripts/limpiar_numero_demo.py`) · `python scripts/check_triaje.py` antes de cualquier PUT. El PUT solo acepta `name, nodes, connections, settings, staticData` y `settings` solo `saveExecutionProgress, saveManualExecutions, saveDataErrorExecution, saveDataSuccessExecution, executionTimeout, errorWorkflow, timezone, executionOrder, callerPolicy, callerIds`.

## 3. Arquitectura del v6 vivo

Pipeline, en orden lógico (verificado en `workflows/current/v6_LIVE.json`):

1. **Entrada y defensas:** `Webhook - Evolution API` → `Webhook Validator` → `Kill-switch Check` (`/bot off|on|status`, solo teléfonos admin) → chequeo `dentalink:status` → **Rate limit** (Redis INCR).
2. **fromMe:** `Es fromMe?` separa lo que escribe el staff desde el celular de la clínica → `Build fromMe AI memory`, guarda en memoria, aplica label `humano` en Chatwoot y silencia al bot. Los adjuntos del staff van por `Media: * (staff)`.
3. **Tipo de mensaje:** `Switch - Tipo Mensaje` → audio (transcribe), imagen (analiza), documento, otros. Los adjuntos se suben a Storage (`media_entrantes`) y se marcan `[MEDIA:id]`.
4. **Buffer:** `Buffer: Push` → espera 10 s → `Soy el último?` (junta mensajes seguidos).
5. **Gates previos al LLM:** `Verificar Label Humano` / `Bot Activo?` · `Handle Stale Session` · `Pre-filtro Cierre` · `Gate Canned Directo` · `Canned Sidecar` · `Gate Pago Tratamiento`.
6. **Router** (`Router - Clasificar Intent`, 1.998 chars) → `Parse Intent` → `Switch sobre Intent`:
   - `confirmar_post_recordatorio` → **Sub-Agent Confirmar**
   - `cancelar_o_reprogramar` → **`Execute Sub-WF Cancelar`** (workflow `5cAWJxiWJ50hxEq3`, **determinístico: no tiene agente LLM**)
   - `urgencia_dolor` → **flujo Triaje** (`Triaje: Evaluar → Decidir → Ruta → video / pregunta / cerrar / silencio / escalar`)
   - `agendar_nuevo` → **Sub-Agent Agendar**
   - `consulta_general` → **Sub-Agent General**
7. **Salida:** `Gate Error Tecnico` → `Format Sub-WF Output` → `Formatting Agent - WhatsApp` → **`Banlist Validator`** (regex, última línea de defensa) → `Split en Mensajes` → `Gate Humano Final` → `Evolution API - Enviar Mensaje`. `[NO_REPLY]` se filtra y se borra de la memoria (`PG - Delete NO_REPLY`).

> **Nodos muertos dentro del v6:** `Sub-Agent Cancelar` (2.726 chars) y `Sub-Agent Urgencia` (954 chars) están cableados a herramientas y modelo pero **ninguna ruta llega a ellos**. Los prompts viejos de `prompts/v6_partials/` que los describen no gobiernan nada. Candidatos a borrar del workflow (PUT aparte, con diff y OK).

### Herramientas por agente
- **Agendar:** `ver_profesionales`, `buscar_horarios`, `buscar_paciente_dentalink`, `crear_paciente_dentalink`, `reservar_turno`, `obtener_historial_paciente`, `escalar_a_secretaria`.
- **Confirmar:** `buscar_paciente_dentalink`, `ver_turnos_paciente`, `confirmar_turno`, `consultar_recordatorios_abiertos`, `marcar_recordatorio_confirmado`, `obtener_historial_paciente`, `escalar_a_secretaria`.
- **General:** `buscar_paciente_dentalink`, `ver_turnos_paciente`, `buscar_conocimiento`, `obtener_historial_paciente`, `escalar_a_secretaria`.

### Prompts vivos (system message, chars)
Formatting 4.824 · Router 1.998 · Confirmar 3.377 · Agendar 4.053 · General 4.238 · (muertos: Cancelar 2.726, Urgencia 954). Medido a las 20:07Z del 2026-10-04; el General y el Urgencia cambiaron durante la sesión por trabajo de otra sesión paralela. Texto completo reproducible con `python scripts/snapshot_v6_live.py` y leyendo `parameters.options.systemMessage`.

## 4. Workflows en n8n

**Activos y propios del bot** (snapshot en `workflows/current/`):

| Workflow | ID | Función |
|---|---|---|
| Agente IA v6 | `O155MqHgOSaNZ9ye` | Bot principal |
| Sub-WF CancelarReprogramar | `5cAWJxiWJ50hxEq3` | Cancelar/reprogramar determinístico |
| Sub-WF Buscar Horarios Validado | `GuDQ9VmKWZvQnerV` | Horarios válidos contra Dentalink |
| Recordatorio de Turno 48HS | `7RqTApkvVavRmq3R` | Cron de recordatorios. **No tocar sin necesidad** |
| Human Takeover – Chatwoot | `w7BBpZeEwZnpCX1q` | Silencia al bot si habla un humano |
| Auto Reactivar Bot | `fosfga62zNaN0qrx` | Reactiva el bot (pasó de 1 h a 24 h el 2026-09-16) |
| Helper – Notify Grupo / Error Handler | `S5U6tSipzlgFHCkf` / `yop6TIVoKiWUxfEn` | Avisos al grupo de derivaciones |
| Logger Conversaciones | `xsXeHp7WLXnFQc3o` | Persistencia en Supabase |
| Panel – acciones staff | `jzxb5zUKCaJcvCgp` | Enviar como staff / toggle bot desde el panel |
| Retención · Vigía · Reportero · Daily Summary · Health Check | `TKByjzVE8rGKTioT` · `1UbmAtUMtTBN9Bn3` · `MJ38kSTRZDPgPCCy` · `QsGBGkZdGu5gTdBf` · `Yjl6kyLnALhIfbFX` | Autorregulación, alertas y reportes |
| Triaje Urgencias (sombra) | `Gm7ofyGohOJ2bI44` | Satélite del triaje |

**Basura en la instancia (NO tocada, requiere decisión de Lucas):**
- ~25 workflows `TEST …` / `[ADMIN] …` / `AUDIT …` **activos** desde junio, más `EXPLORE – Dentalink Citas`.
- Inactivos de otros proyectos: TrendSpot (7), Oso (3), Waves, Tomi Agent, Nexora Propuestas, Content Ideas, `v4`, `v6 backup`, etc.
- Borrarlos es irreversible en producción: confirmar antes.

## 5. Riesgos de regresión por la curación de prompts (2026-10-04)

Reglas que el análisis de edge cases detectó que pudieron perderse al reducir los prompts ~90%. **Verificar antes de dar por buena la curación**:

| Caso | Qué podría haberse perdido |
|---|---|
| `URG-01` (incidente Mariela) | El Router no nombra "incómoda", "no come", "expansor" y manda a `consulta_general` si el mensaje es ambiguo. Es la causa 3 del incidente |
| `PAG-06` | Falta el texto de "pagar el día de la consulta" en el General |
| `PAG-12` | "Voy hoy a abonar" lo maneja General, pero el Router lo manda a Confirmar |
| `RTR-18` / `MEM-04` | Avisos de llegada: el General curado contesta; la Dra. pidió `[NO_REPLY]` exacto |
| `RTR-04` | Se perdió la continuación de urgencia con video |
| `RTR-02` | Se perdió la regla de multi-pedido (caso Salvador) |
| `RTR-24` | Se perdió la presentación de Asiri en Agendar y Confirmar |
| `MEM-09` | El General perdió: canned sin turno, filtro de estados, "sin día de semana", varias fichas |
| `MEM-05` | `obtener_historial_paciente` no aparece en ningún prompt vivo |

## 6. Catálogo de edge cases

**386 casos únicos** (deduplicados desde 469 entradas de 4 fuentes). Cada caso trae: disparador, falla previa, comportamiento esperado como aserción testeable, capa que lo cumple, test existente, fecha/fuente y estado (`vigente` / `superado` / `pendiente de decisión`). Los que dependen de reglas curadas llevan `Riesgo de regresión`.

| Archivo | Flujos | Casos | Sin test |
|---|---|---|---|
| `edge-cases/01-urgencia-triaje.md` | Urgencia y triaje con video | 53 | 11 (+~15 parciales) |
| `edge-cases/02-agendar-confirmar.md` | Agendar · Confirmar | 37 + 10 | 16 + 8 |
| `edge-cases/03-cancelar-pagos-router.md` | Cancelar/reprogramar · Pagos · Router | 22 + 14 + 30 | 16 + 5 + 23 |
| `edge-cases/04-general-banlist.md` | Info general · Banlist y gates | 35 + 18 | 19 + 12 |
| `edge-cases/05-handoff-memoria.md` | Handoff humano/kill-switch · Memoria | 29 + 19 | 26 + 14 |
| `edge-cases/06-recordatorios-media.md` | Recordatorios · Media | 26 + 26 | 14 + 10 |
| `edge-cases/07-infra-panel.md` | Infra (Evolution/n8n/Supabase) · Panel | 43 + 24 | 29 + 21 |

Cómo usarlo para testear un flujo: cargar solo el archivo de ese flujo, tomar `Entrada` y `Esperado` de cada caso y correrlo contra el prompt/gate de la columna `Capa`. Prioridad: casos `vigente` con `SIN TEST` y los marcados `Riesgo de regresión`.

**Huecos más peligrosos (por flujo, según el consolidado):**
- **Urgencia:** no hay test dedicado del incidente Mariela; la clasificación del LLM del triaje no tiene ningún test; label humano autoaplicado y aviso pasivo sin test.
- **Handoff/kill-switch:** HUM-01…05 (teléfono del destinatario en vez del emisor, backspace U+0008 en la regex, chats `@lid`, comando desde el grupo) sin test. Es la causa 1 del incidente Mariela.
- **Router:** 23 de 30 casos sin test.
- **Cancelar:** 16 de 22 sin test, y el sub-WF fue refactorizado el 2026-09-07.

## 7. Tests que existen en `tests/`

| Archivo | Cubre |
|---|---|
| `test_canned_sidecar.py` | Sidecar canned (alias/precio pegado a otra acción). Importa `SIDECAR_JS` de `scripts/apply_canned_sidecar.py` |
| `test_gate_pago_tratamiento.py` | Gate de pago de tratamiento. Importa `GATE_JS` de `scripts/apply_gate_pago_tratamiento.py` |
| `test_triaje_nodos.js`, `test_triaje_textos_banlist.py`, `test_e2e_triaje.py` | Triaje |
| `test_turnos_formato.js` | Formato de turnos 2+2 |
| `test_media_nodos.js`, `test_media_fromme.js` | Media del paciente y del staff |
| `test_recordatorio_consultas.js` | Recordatorio de consultas (**todavía no aplicado**) |
| `test_retencion_y_staff.js` | Retención y adjuntos del staff |
| `test_e2e_bateria.py` | Batería end-to-end |
| `test_nodes_eval.py`, `test_reprogramar_franja.py` | **Probablemente obsoletos**: prueban lógica vieja de Step 5 y Step 6b-out del sub-WF |

## 8. Pendientes verificados

- **Recordatorio especial para CONSULTAS (pedido Dra. 2026-09-08): NO aplicado.** Scripts y tests listos (`scripts/apply_recordatorio_consultas.py`, `tests/test_recordatorio_consultas.js`). Bloquea una pregunta abierta: ¿el "puntito amarillo" de Dentalink es exactamente el motivo `Consulta Ortodoncia`?
- **R7:** el Sub-Agent Confirmar marca confirmado en Dentalink cualquier "confirmo" sin verificar pago. Decisión de negocio pendiente (Dra./Lucas).
- **Bug P1 "agendar prematuro"** (detectado 2026-07-19): reservar sin confirmación explícita. No se pudo verificar si quedó cerrado; ver `AGE-*` en el catálogo antes de darlo por resuelto.
- Podar los dos nodos muertos del v6 (Cancelar y Urgencia) y limpiar la instancia de n8n.
- Traefik `readTimeout` del panel en vivo (pendiente desde 2026-09-06 según la memoria; no verificado hoy).
- Decidir el grupo de supervisión (Raquel + Lucas + Irina) y actualizar el JID en `Helper – Notify Grupo`.

## 9. Preguntas abiertas (resumen)

Fuente completa: `memory/open-questions.md` (17 al 2026-09-08). Las que más condicionan trabajo: (3) orden en que Dentalink devuelve fichas de un mismo celular (impacta familias con teléfono compartido); (4) si se aplicó alguna vez `apply_fix_router_reagendar.py` (el Router vivo no tiene sus señales); (9–12) fraseo y red flags definitivos del triaje; (16) motivo exacto de las consultas; (17) R7.

## 10. Operación (sin secretos)

- n8n: https://n8n.raquelrodriguez.com.ar · webhook v6: `/webhook/evolution-v2` · Chatwoot: https://chat.raquelrodriguez.com.ar
- Grupo de derivaciones `120363407321448469@g.us`. Admin `/bot off|on|status` solo desde los celulares de Lucas, Irina y la Dra.
- Credenciales: `.env` local (no versionado) y la nota de accesos del vault. Nunca pegarlas en el repo.
- Herramientas vigentes en `scripts/`: `snapshot_v6_live.py` (baja el v6 por API), `check_triaje.py`, `limpiar_numero_demo.py`, `probar_bot_e2e.py`, `simulate_v6_message.py`, `report_banlist_shadow.py`, `verify_*`, `create_*` de satélites y SQL de esquemas.
- Convención nueva: ya no hay un `apply_*` por cambio ni carpeta `workflows/history`. Antes de un PUT se guarda un snapshot con fecha (`python scripts/snapshot_v6_live.py --out workflows/pre_<cambio>_<fecha>.json`, ignorado por git) y se borra cuando el cambio queda verificado. El script del cambio sí se commitea mientras no esté aplicado.
