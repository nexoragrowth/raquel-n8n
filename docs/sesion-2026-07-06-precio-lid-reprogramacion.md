# Sesión 2026-07-06 — Precio $50k + Fix LID + Diagnóstico reprogramaciones

> Sesión Claude Code (máquina Windows de Lucas). Cambios aplicados a prod CON autorización
> explícita de Lucas. Backups PRE/POST de cada PUT en `workflows/history/`.

---

## 1. Precio consulta: $40.000 → $50.000 ✅ APLICADO Y TESTEADO

- 9 reemplazos en 3 nodos del v6: **Sub-Agent General** (4 canned reales), **Formatting Agent**
  (ejemplo few-shot), **OpenAI - Analizar Imagen** (ejemplos de formato de monto, incl. `40000`).
- Pedido de Lucas: cambiar TODO 40→50 para no confundir al LLM. Contención quedó en $50.000 (igual que consulta).
- Script: `scripts/` no aplica (cambio ad-hoc con guardas, ver backups `v6_PRE/POST_precio50_apply_*`).
- **Test E2E PASS**: sim con número de Lucas → *"El valor de la consulta es de $50.000..."* (exec 192800).
- ⚠️ Drift: `prompts/v6_partials/general_funcion.md` sigue diciendo $40.000 y el wording vivo difiere del snapshot. El vivo es la fuente de verdad.

## 2. Fix LID-safe phone extraction ✅ APLICADO (tests E2E corriendo al cierre de este doc)

**Contexto** (workflow de investigación con 3 agentes — forense de 527 execs + análisis estático + research):
- Evolution API **2.3.7** ya normaliza lid→PN en DMs: los mensajes de pacientes llegan con
  el teléfono en `key.remoteJid` + `key.remoteJidAlt` + `addressingMode: "lid"` (154/154).
- Los "@lid" masivos en ejecuciones son **`messages.update` (receipts)** — el Webhook Validator
  los corta; NO son mensajes de pacientes. (El susto de "@lid es mayoría del tráfico" era eso.)
- PERO el issue oficial de Evolution (#1872, abierto, "symptoms persist on v2.3.7") documenta
  que el @lid crudo se filtra cuando el mapeo no está cacheado → ese día el paciente queda
  invisible (Dentalink/Supabase/recordatorios) y el human-takeover queda **fail-open**.
- LID→PN **no es derivable por protocolo** (doc Baileys): si no viene Alt/senderPn, no hay teléfono.

**Cambios** (`scripts/apply_fix_lid_phone_extraction.py`, backups `v6_PRE/POST_lid_phone_fix_*`):
1. `Edit Fields - Extraer Datos` → `phone` y `phone_last10`: cadena de candidatos
   `remoteJid → remoteJidAlt → senderPn → participantAlt → participant` (primero que termine
   en `@s.whatsapp.net`, recorta `:device` y dominio). Sin candidato → fallback EXACTO al
   comportamiento previo (cero regresión).
2. `Edit Fields` → **nuevo campo `pushName`**: los sub-agents inyectan
   `{{ ...json.pushName }}` pero el extractor lo guardaba como `name` → **pushName llegaba
   vacío SIEMPRE** (bug lateral vivo desde el inicio, no solo @lid).
3. `Kill-switch Check` → misma cadena pero solo-DM (sin `participant*`): un admin escribiendo
   desde chat @lid recupera `/bot off|on|status` (antes se ignoraban EN SILENCIO — mismo patrón
   del root cause #1 del incidente Mariela).

**NO tocado**: Rate Limit Prep (guard seguro ya existente), envío (usa remoteJid crudo — correcto,
así las respuestas a @lid salen bien), conexiones, webhookId (`evo-webhook-v2` verificado).

**Tests**: `scripts/test_lid_fix_e2e.py` — usa el LID real de Lucas (`223871026389070@lid`),
descubierto correlacionando receipts `messages.update` con los messageIds enviados a su número
(no inventa LIDs). **Resultados — TODOS PASS**:

| Test | Qué prueba | Resultado |
|---|---|---|
| T1 | Regresión DM normal (precio) | ✅ PASS (exec 192897) — phone/last10/pushName ok, responde $50.000 |
| T2 | `remoteJid=@lid + remoteJidAlt=phone` | ✅ PASS (exec 192917) — phone recuperado `5491161461034` |
| T3 | `@lid` sin Alt (peor caso) | ✅ PASS (exec 192920) — fallback intacto, sin crash, canned responde |
| T4-bis | `/bot status` desde chat @lid | ✅ PASS (exec 192943) — isAdminCommand=true, admin=Lucas |
| T5 | `/bot status` desde JID normal | ✅ PASS (exec 192947) |

## 2b. BONUS — Bug CRÍTICO pre-existente encontrado y reparado: kill-switch roto para TODOS ✅

El T4 original falló y el debug reveló que el jsCode del `Kill-switch Check` contenía un
**carácter BACKSPACE literal (U+0008)** donde debía haber un `\b` de regex (alguien cargó el
código vía JSON: `"\b"` en JSON = backspace). La regex `/^\/bot\s+(off|on|status)<BS>/` **no
matcheaba NUNCA** → `/bot off|on|status` estaba roto EN SILENCIO para los 3 admins **desde el
2026-05-09** — el mismo modo de falla (kill-switch mudo) del incidente Mariela.

Fix: `scripts/apply_fix_killswitch_backspace.py` (backups `v6_PRE/POST_killswitch_backspace_*`).
Verificado con T4-bis y T5 arriba. **Lección**: al cargar jsCode por API, `\b` de regex debe ir
como `\\b` en el JSON; auditar futuros scripts por escapes de control (`\b`, `\f`).

## 3. Diagnóstico reprogramaciones + familias/fichas (workflow de análisis, 3 agentes)

### La arquitectura real (distinta de lo que dicen los docs)
- `cancelar_o_reprogramar` NO va a un agente LLM: va al **Sub-WF - CancelarReprogramar**
  (`5cAWJxiWJ50hxEq3`, 35 nodos, determinístico + 2 LLMs utilitarios). El **"Sub-Agent Cancelar"
  del canvas está HUÉRFANO** (0 conexiones de entrada, código muerto) — los partials
  `cancelar_*.md` del repo documentan un agente que no corre.
- Snapshot del sub-WF (no existía en el repo): `workflows/current/subwf_cancelar_reprogramar_LIVE.json`.
- No existe intent "reprogramar" separado; reprogramación real = Step 6d del sub-WF
  (POST cita nueva → PUT cancelar vieja).

### Evidencia en vivo (ventana retenida ~72h, 534 execs)
- El bot **no procesó ninguna reprogramación** en la ventana: todas las reprogramaciones las
  manejó un humano (label humano). Las ejecuciones del reporte semanal ya se purgaron (retención 72h).
- **Confirmado el nicho**: 3/3 confirmaciones post-recordatorio, quien escribe NO es el paciente
  (madre/padre confirmando turno del hijo). Funciona porque `consultar_recordatorios_abiertos`
  mapea teléfono→cita directo en Supabase (sin resolver fichas en Dentalink).
- Bug detectado de paso: el **rate limiter cuenta los mensajes fromMe del staff** en la cuota
  del teléfono del paciente (9/20 rate-limited eran de la clínica).
- Exec 184080: pregunta legítima de un padre terminó en `[NO_REPLY]` sin respuesta ni escalación.

### Causa raíz (hipótesis de Lucas: parcialmente correcta, la raíz operativa es el código)
Las familias/duplicados son el detonante, pero el dead-end está en el sub-WF:

| # | Gap | Dónde | Severidad |
|---|---|---|---|
| 1 | Turnos se fetchean SOLO de `pacientesAll[0]`; si la ficha resuelta (DNI/contexto) no es la primera → **escala SIEMPRE** ("coordinar a mano") | Step 2a + Step 4 `__pickTurno` | 🔴 CRÍTICO — el dead-end de familias |
| 2 | Desambiguación `tokens.some()` sobre nombre+apellido: el apellido familiar matchea TODAS las fichas; el canned del bot pide "nombre y apellido" = induce la respuesta que rompe el match | Step 1b + Step 4 | 🔴 CRÍTICO |
| 3 | Fichas duplicadas exactas → lista "Martina García y Martina García", loop sin salida | Step 4 | 🟠 ALTO |
| 4 | El canned de clarificación multi-ficha no está en el anti-loop → puede repetirse hasta frustración | Step 0b | 🟠 ALTO |
| 5 | `cita_a_cancelar = turnos[0]` (primer turno próximo, no el hablado); acepta slot ANTES de resolver multi-ficha | Step 5 | 🟠 ALTO |
| 6 | El sub-WF no consulta `recordatorios_enviados` (la solución que SÍ resuelve familia en Confirmar) ni cierra filas al cancelar | todo el sub-WF | 🟠 MEDIO/ALTO |
| 7 | `crear_paciente_dentalink` NO manda `documento` (DNI) en el body aunque la description lo exige → fichas del bot sin `rut`, el DNI-match nunca las encuentra; apellido fallback = pushName de WhatsApp | tool en v6 | 🟠 ALTO (retroalimenta el problema) |
| 8 | Router: "¿puedo pasar el turno a otro día?" (interrogativo) → `consulta_general`, nunca entra al flow de reprogramación; y contradicción interna Regla 0 vs Intent 5 | Router systemMessage | 🟡 MEDIO |
| 9 | `apply_fix_router_reagendar.py` ("vuelvo en X meses" → agendar) NO está en el Router vivo — nunca se aplicó o fue pisado | Router | 🟡 MEDIO |
| 10 | Reporte semanal: alucina métricas, cuenta mal escalaciones (mezcla fromMe/receipts), roles mal categorizados | workflow reporte | 🟡 (ya sabido) |

### Plan propuesto (PARA OK DE LUCAS — nada de esto se aplicó)

**Fase 1 — quick wins de bajo riesgo:**
- a. `crear_paciente_dentalink`: agregar `documento` (+`id_sucursal`) al jsonBody real (gap 7).
- b. Anti-loop: sumar el canned multi-ficha a `fraseLoop` (gap 4).
- c. Canned de clarificación: pedir "DNI **o solo el nombre de pila**" (evita inducir el apellido, gap 2 parcial).
- d. Router: regla para reprogramación interrogativa ("¿puedo cambiar…?") (gap 8).

**Fase 2 — el fix estructural (gap 1+2+5, requiere test sintético + shadow):**
- Reordenar el sub-WF: resolver la ficha ANTES de enganchar turno; si la ficha resuelta ≠
  `data[0]`, **re-fetchear** sus citas (nuevo branch Step 4→Step 2a' o fetch de citas de TODAS
  las fichas del teléfono desde el arranque, son ≤4 GETs).
- Matching por scoring (nombre de pila pesa más que apellido; all-tokens > some-token).
- Persistir `turno_objetivo` en el estado multi-turno (no `turnos[0]`).

**Fase 3 — estructural de datos:**
- Consultar `recordatorios_enviados` en el sub-WF (patrón Confirmar) + cerrar filas al cancelar (gap 6).
- Cleanup Dentalink: ficha duplicada Carmen id=609, duplicados históricos (tarea Irina), backfill DNI.
- Borrar el Sub-Agent Cancelar huérfano (código muerto que confunde).
- Ajustar el reportero semanal (definición de escalación: excluir fromMe/receipts; validar conteos).

## 4. Otros pendientes
- Rotar la API key de n8n (quedó pegada en el chat de la sesión) y actualizar `.env`.
- Sincronizar partials del repo con los prompts vivos (drift múltiple, gap 10 del análisis).
- Fix rate limiter: no contar fromMe del staff en la cuota del paciente.
