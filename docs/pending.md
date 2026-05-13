# Roadmap pendiente — del v6 actual a producción

Este doc está orientado al colaborador (Codex u otro) que toma el proyecto y lo lleva hasta cutover. Detalla qué falta, en qué orden y cómo ejecutarlo.

> **Estado al 2026-05-12**: v6 endurecido con 2 rounds de fixes. Tests sintéticos en 82/100. Faltan 2 fixes críticos + shadow + cutover.

---

## Fase 1 — Pre-shadow (estimado: 30 min)

### 1.1 Banlist gap crítico (5 min)

Bug confirmado en test G8: bot dijo *"queda confirmado. La esperamos en Balcarce 37, 2do piso"* y Banlist NO lo bloqueó. El regex captura `te esperamos` pero no `la esperamos` / `le esperamos` / `los esperamos`.

**Acción:**
1. GET `Banlist Validator` node del workflow v6 (`O155MqHgOSaNZ9ye`).
2. Inspeccionar el array de regex patterns en `jsCode`.
3. Agregar 3 patterns: `/\bla esperamos\b/i`, `/\ble esperamos\b/i`, `/\blos esperamos\b/i`.
4. Backup pre-cambio, PUT, verify.
5. Test unitario en Python: pasar 3 outputs de muestra al code del Banlist y verificar bloqueo.

Crear script `scripts/apply_banlist_extend.py` siguiendo el patrón de los otros.

### 1.2 Suavizar R0 en saludos cold (10 min)

Bug: tests E2/E3/E5 caen en `[NO_REPLY]` cuando deberían dar saludo corto + invitación. R0 dice "si dudás escalá" demasiado fuerte.

**Acción:**
1. GET los 5 sub-agents del workflow.
2. En el bloque R0 (al TOP del system message), agregar excepción:

```
EXCEPCION SALUDOS COLD: si la memoria NO tiene mensajes de las ultimas 24h Y
el paciente solo saluda (hola/buenas/buen dia/holaa), responder UNA linea
corta saludando + invitar a agendar. NO uses `[NO_REPLY]` en este caso, NO
escales.

Ejemplo correcto: "¡Hola! Soy la asistente virtual de la Dra. Raquel. ¿Querés
agendar un turno?"
```

3. Backup, PUT, verify.

Crear `scripts/apply_r0_soften_greetings.py`.

### 1.3 Re-correr tests sintéticos (15 min)

```bash
# Prep modo shadow (workflow ya queda activo con Send disabled)
python scripts/test_prep_restore.py --prep
# anotá el path del backup que genera

# Correr tests (10-15 min, paralelo 8 workers)
python C:/Users/Lucas/.claude/n8n_backups/test_100_pre_prod.py

# Si pasa >=95/100 → ok, seguir a Fase 2
# Si pasa <95/100 → ver fails, iterar fixes

# Restore al estado pre-test (importante)
python scripts/test_prep_restore.py --restore workflows/history/v6_PRE_TEST_PREP_<ts>.json
```

**Criterio de éxito**: 95+/100 PASS y G8 (la esperamos) ahora bloqueado.

---

## Fase 2 — Shadow 24-48h (estimado: tiempo real)

### 2.1 Setup shadow

Diferencia con tests sintéticos: shadow es con **tráfico real** de pacientes. El v6 procesa todo pero NO envía respuesta (Send disabled).

**Acción:**
1. Confirmar que workflow `Human Takeover` está activo (debe seguir respondiendo via Chatwoot mientras shadow).
2. Cambiar webhook path del v6 a `evolution-v2` (path de prod). Esto hace que Evolution mande mensajes reales al v6.
3. Disable nodos `Evolution API - Enviar Mensaje` y `Evolution - Typing` (asegurar que estén disabled).
4. **Importante**: NO activar las 4 tools Dentalink de escritura (`reservar_turno`, `cancelar_turno`, `confirmar_turno`, `crear_paciente_dentalink`) durante shadow. Solo lectura.
5. Activar v6.

```bash
# Script shadow prep (a crear):
python scripts/apply_shadow_mode.py --enable
```

### 2.2 Monitoreo durante shadow

Cada 4-6h durante 24-48h:

1. Revisar ejecuciones del v6 en `https://n8n.raquelrodriguez.com.ar/workflow/O155MqHgOSaNZ9ye/executions`
2. Verificar:
   - Ningún nodo con error inesperado
   - El output del Banlist Validator no genera muchos canned (señal de macanas frecuentes)
   - El Router clasifica correctamente
   - Sub-Agent Urgencia + escalar_a_secretaria se invocan en casos médicos
3. Si aparece una macana: comparar lo que el bot ITUO decir vs lo que efectivamente se hubiera enviado (Send disabled → solo lo vemos en logs).
4. **Si hay falla grave**: desactivar v6 inmediatamente.

```bash
# Verificar últimas ejecuciones
curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" \
  "https://n8n.raquelrodriguez.com.ar/api/v1/executions?workflowId=O155MqHgOSaNZ9ye&limit=20" \
  | python -m json.tool
```

### 2.3 Criterios de éxito del shadow

Pasar a Fase 3 si:
- ✅ ≥80% de mensajes procesados correctamente (clasificación + tool call correcto)
- ✅ Cero "macanas" tipo Mariela (instrucciones operativas, invitaciones a clínica)
- ✅ El Banlist regex no se activa más de 1-2 veces (señal de prompts mal)
- ✅ Doctora + Iri confirman que lo que el bot "habría dicho" es razonable

Si NO cumple: iterar prompts y re-shadow.

---

## Fase 3 — Cutover supervisado

### 3.1 Pre-cutover

1. Backup del v6 + workflow Human Takeover (por si algo).
2. Aviso a Iri y doctora: "vamos a prender el bot ahora, miremos los primeros 6h juntos".
3. Cambiar `secretaryPhone` en `escalar_a_secretaria` de Lucas → Irina (`5493885786946`).

### 3.2 Cutover

1. **Activar nodos send**: `Evolution API - Enviar Mensaje`, `Evolution - Typing`, `HTTP Send Admin Confirm`.
2. **Activar tools Dentalink write**: `reservar_turno`, `cancelar_turno`, `confirmar_turno`, `crear_paciente_dentalink`.
3. Verificar que el workflow `Human Takeover - Chatwoot` siga activo (label `humano` debe funcionar).
4. Verificar webhook path = `evolution-v2`.
5. v6 active = true.

```bash
# Script cutover (a crear):
python scripts/apply_cutover.py
```

### 3.3 Post-cutover (primeras 6h)

- Iri + Lucas + doctora mirando Chatwoot en vivo.
- Cada conversación que el bot atienda: verificar que la respuesta es la correcta.
- Si aparece una macana grave: `/bot off` desde el celular de Lucas/Iri/Raquel.
- Después de 6h sin macanas: cutover declarado exitoso.

### 3.4 Post-cutover (primera semana)

- Revisión diaria de ejecuciones.
- Iri reporta cualquier respuesta rara → se crea ticket en `docs/bugs.md`.
- Si todo OK después de 1 semana: pasar a "modo mantenimiento" (revisión semanal).

---

## Backlog (post-MVP)

Estos pueden trabajarse después del cutover, en orden de impacto:

### Mejoras de robustez

- **#24 — 4 tool descriptions vacías** (cancelar_turno, reservar_turno, crear_paciente_dentalink, ver_profesionales). LLM adivina params por nombre. Riesgo bajo, pero rompe en edge cases.
- **#30 — Index Postgres en `n8n_chat_histories(session_id)`**. Mejora performance del Check Session Age. Requiere acceso al Postgres del n8n (no Supabase).
- **#31 — Normalizar session_id**. Manejar `+5493...`, `@lid`. No observado en prod pero potencial.

### Mejora de prompt (opcional)

- **#22 — Sacar ejemplo "Te esperamos" del prompt** y agregar R23 anti-invitación. El Banlist regex ya lo cubre como red de seguridad, pero la causa raíz sigue en el prompt. Cosmetico pero ayuda a reducir falsos positivos del Banlist.

### Mejora arquitectural (mediano plazo)

- **Refactor Router → Supervisor mono-agent**. El v6 actual es multi-agent con 5 sub-agents y prompts de 20-30k chars c/u. Reemplazar por:
  - Pre-filtro regex (60-70% de casos: saludos, gracias, autoresponders, emojis)
  - Supervisor minimalista (gpt-5-mini, T=0, JSON output) que clasifica el resto en 3 intents
  - 3 funciones puras (no sub-agents): agendar / confirmar_cancelar / escalar
  - Cero charla libre

Esto es trabajo de varios días pero elimina la arquitectura conversacional. R0 + Banlist son band-aids; el refactor es el fix definitivo.

### Datos reales

- **Proyecto Supabase clínico**. Hoy las tablas `pacientes` / `conversaciones` no existen. Si en el futuro se quiere RAG real o analytics propios, crear proyecto nuevo (`aurea-prod`) con schema correcto. Curar 10-30 docs clínicos para RAG con embeddings 1536-dim.
- **Cleanup Carmen Agostini duplicada** en Dentalink (id=609 duplicado). Trabajo manual con la doctora.

---

## Anti-patrones que NO hacer

1. **NO prender el v6 sin OK explícito de Lucas**. Hubo incidente real con paciente.
2. **NO hacer PUTs al workflow sin backup previo**. Ver patrón en cualquier script de `scripts/`.
3. **NO borrar el `webhookId: evo-webhook-v2`** en ningún PUT. Si se pierde, Evolution apunta a UUID null y rompe todo.
4. **NO meter features extra** mientras se está cerrando MVP (vision OCR, RAG abierto, sub-agents creativos).
5. **NO confiar 100% en lo que el LLM va a decir**. Cada regla crítica debe estar en al menos 2 capas (prompt + gate determinístico).
6. **NO usar `git push --force` a `main`** del repo.
7. **NO commitear secrets** (`N8N_API_KEY`, `CHATWOOT_TOKEN`, etc.). El `.gitignore` ya excluye `.env*` pero verificá grep antes de cada commit.

---

## Referencias

- Estado actual del v6: `workflows/history/v6_POST_CLEAR_MEM_<ts>.json` (último snapshot post Round 2)
- Bugs reportados: [`docs/bugs.md`](bugs.md)
- Fixes aplicados: [`docs/fixes.md`](fixes.md)
- Operación día-a-día: [`docs/runbook.md`](runbook.md)
- Arquitectura: [`docs/architecture.md`](architecture.md)
