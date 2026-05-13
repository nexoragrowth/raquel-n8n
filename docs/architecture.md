# Arquitectura del Agente

## Vista de alto nivel

```
WhatsApp paciente
       │
       ▼
Evolution API (instance "raquel", VPS only)
       │  POST webhook
       ▼
n8n self-hosted (n8n.raquelrodriguez.com.ar)
       │
       ▼
┌────────────────────────────────────────────────────┐
│  WORKFLOW v6 Multi-agent (O155MqHgOSaNZ9ye)        │
│                                                    │
│  ENTRADA → BUFFER → MULTIMEDIA → AI AGENT → SALIDA │
└────────────────────────────────────────────────────┘
       │
       ├─→ Postgres (memoria LangChain)
       ├─→ Redis (buffer + kill-switch + rate limit)
       ├─→ Dentalink API (agenda real)
       ├─→ Chatwoot API (label humano)
       └─→ Evolution API (envío respuesta)
```

---

## Workflow v6 — 5 zonas

El workflow vivo tiene ~100 nodos agrupados visualmente en sticky notes:

### 1. ENTRADA — Recepción WhatsApp

Cadena determinística que decide si el mensaje merece procesarse:

```
Webhook
  → Webhook Validator
  → Kill-switch Check          ← admin /bot off|on desde Lucas/Iri/Raquel
  → Es comando admin?
       ├─ TRUE: Redis SET bot:status + HTTP Send Admin Confirm
       └─ FALSE: continúa
  → Redis GET bot:status
  → Bot enabled?
       ├─ FALSE: NoOp ✋
       └─ TRUE: continúa
  → Redis GET dentalink:status
  → Dentalink up?
       ├─ FALSE: NoOp (escalar a humano) ✋
       └─ TRUE: continúa
  → Rate Limit (Prep → INCR → Eval → OK?)
       ├─ FALSE: NoOp ✋
       └─ TRUE: continúa
  → Edit Fields - Extraer Datos    ← normaliza phone, pushName, text, fromMe
  → Es fromMe?
       ├─ TRUE: Build fromMe AI memory + Save fromMe + CW Search/Get/Pick/SetLabel humano ✋
       └─ FALSE: continúa
  → Filtrar duplicados y basura
```

**Reglas críticas implementadas:**
- **Kill-switch estricto**: solo admins desde su WA personal con `!fromMe`. Comandos: `/bot off`, `/bot on`, `/bot status`.
- **Bot enabled global**: Redis key `bot:status`. Se controla via kill-switch o auto-reactivar (1h sin humano).
- **Dentalink up**: Redis key `dentalink:status` actualizada por workflow Health Check.
- **Rate limit**: 10 msgs/15min por phone. Key Redis `rate:{phone}`.
- **fromMe filter**: cuando humano habla (desde Chatwoot/WA Web/WA Mobile), persiste con TAG `[ATENCION HUMANA - ...]` + aplica label `humano` en Chatwoot. Rama termina, bot no responde.

### 2. BUFFER (Redis)

Patrón Twilio: PUSH + Wait 10s en paralelo. Junta mensajes consecutivos del paciente antes de procesar.

```
Filtrar → Switch Tipo Mensaje (texto/audio/imagen/doc/otros)
       → ramas multimedia (siguiente sección)
       → Merge Multimedia
       → Buffer: Push Mensaje (RPUSH chat_buffer:{phone})
       → Buffer: Wait 10s
       → Buffer: Leer Lista (LRANGE)
       → Soy el último?
            ├─ FALSE: Descartar (no soy último) ✋
            └─ TRUE: Preparar Mensaje Final + Buffer: Limpiar
       → Pre-filtro Cierre  ← regex deterministic (gracias/cierres/autoresponders)
       → Es cierre?
            ├─ TRUE: Set NO_REPLY → SALIDA con [NO_REPLY]
            └─ FALSE: continúa al AI Agent
       → Check Session Age (Postgres)  ← edad del último msg del chat
       → Handle Stale Session  ← marca is_stale_session si >3 días
       → Clear Old Memory  ← borra mensajes "regulares" si stale, preserva wa_outbound/human_takeover/reminder_note
```

**Pre-filtros determinísticos** (capturan ~30-40% de mensajes sin invocar LLM):
- `autoresponder_externo`: gracias por comunicarte con / respuesta automática / horarios de atención
- `solo_gracias` / `termina_gracias`: variantes de "gracias" sin info útil
- `saludo_inicial`: hola/buenas/buen día sin contexto (memoria reciente vacía)
- `emoji_only`: solo emojis
- `default_pass`: el resto pasa al LLM

### 3. MULTIMEDIA — Procesamiento por tipo

Switch sobre `message.type`:
- **Texto**: pass-through
- **Audio**: Evolution Obtener Media → Convert to File → OpenAI Whisper transcribir
- **Imagen**: Evolution Obtener Imagen → Convert → OpenAI Vision analizar
- **Documento/Otros**: marker para escalar

### 4. AI AGENT — Núcleo inteligente

```
Postgres Chat Memory (50 mensajes context)
       │
       ▼
Router LM (gpt-5) ← Clasificar Intent
  → 1 de 5 intents: confirmar / cancelar / agendar / urgencia / general
       │
       ▼
Parse Intent
       │
       ▼
Switch sobre Intent
       │
       ├─→ Sub-Agent Confirmar  (tools: ver_turnos_paciente, confirmar_turno, escalar_a_secretaria)
       ├─→ Sub-Agent Cancelar   (tools: ver_turnos_paciente, cancelar_turno, escalar_a_secretaria)
       ├─→ Sub-Agent Agendar    (tools: ver_profesionales, buscar_horarios, buscar_paciente_dentalink, crear_paciente_dentalink, reservar_turno, escalar_a_secretaria)
       ├─→ Sub-Agent Urgencia   (tools: escalar_a_secretaria)
       └─→ Sub-Agent General    (tools: escalar_a_secretaria)
       │
       ▼
Fallback Output (si el sub-agent devolvió vacío)
       │
       ▼
Necesita Formatting?  → Formatting Agent - WhatsApp (gpt-5-mini)
       │
       ▼
Banlist Validator  ← 22 regex patterns deterministic
       │
       ▼
Split en Mensajes  ← divide respuesta larga en chunks
```

**R0 (regla absoluta) en los 5 sub-agents** (aplicado 2026-05-12):

> NO sos un chatbot. Sos un agente que cumple 4 funciones: agendar / confirmar-cancelar / info-canned / escalar. NO conversás, NO opinás, NO sugerís, NO interpretás síntomas. Si dudás → escalá.

**Banlist regex (red de seguridad post-output)** intercala entre Formatting Agent y Split. 22 patrones que cubren:
- `venite` / `vengan` / `te esperamos` / `los esperamos`
- Instrucciones operativas: `guarda`, `traé`, `tomá`, `no comas`
- Diagnóstico: `no te preocupes`, `es normal`
- `Balcarce 37` fuera de contexto de confirmación

Si match → reemplaza output por canned: *"Recibimos tu mensaje. Estamos derivando tu caso a la Dra. Raquel..."*

### 5. SALIDA — Envío y persistencia

```
Tiene respuesta?  ← chequea si output != [NO_REPLY]
  ├─ FALSE: PG - Delete NO_REPLY  ← post-hoc cleanup memoria
  │        → Descartar [NO_REPLY] (NoOp) ✋
  └─ TRUE:
       → Es primer mensaje? (decide si poner delay)
       → Delay Humano (Wait)
       → Evolution - Typing (send-presence)
       → Evolution API - Enviar Mensaje (send-text)
```

---

## Workflow Recordatorios (`7RqTApkvVavRmq3R`)

Cron `0 13 * * 1-5` (9 AM Arg, lun-vie). Cada día calcula `addBusinessDays(hoy, 2)` y manda recordatorio a todos los pacientes con turno en esa fecha.

```
Schedule Trigger
  → Fecha Mañana  ← calcula fecha objetivo (2 días hábiles)
  → GET Citas por fecha (Dentalink API)
  → Split Citas
  → Solo citas activas (filtra anuladas)
  → GET Paciente (celular)
  → Tiene celular?
       ├─ NO: skip ✋
       └─ SÍ:
            → Preparar mensaje (template humanizado por género + día semana)
            → Enviar WhatsApp (Evolution)
            → Guardar en Chat Memory (Postgres con source:reminder_note + id_paciente)
```

**Fix aplicado 2026-05-11**: cron pasó de `0 13 * * *` (todos los días) a `0 13 * * 1-5` (solo hábiles). El bug previo hacía que viernes, sábado y domingo convergieran al mismo martes → pacientes del martes recibían 3 recordatorios.

---

## Workflow Human Takeover Chatwoot (`w7BBpZeEwZnpCX1q`)

Webhook reactivo a eventos de Chatwoot. Cuando un agente humano escribe DESDE Chatwoot:

1. Aplica label `humano` a la conversación (POST /labels)
2. Replica el mensaje a WhatsApp via Evolution (echo desde Chatwoot a Evolution)
3. Guarda en memoria Postgres con `additional_kwargs.source: human_takeover`

Cuando la conversation se marca `resolved` en Chatwoot:
- Quita label `humano` → bot vuelve a atender

**Gap cubierto en Round 2**: este workflow solo se entera de mensajes desde Chatwoot. Para WA Web / WA Mobile, ahora el v6 directamente aplica el label `humano` en la rama `fromMe=true` (5 nodos `CW Search Contact → ... → Set Label humano`).

---

## Otros workflows soportes

| ID | Función |
|---|---|
| `Yjl6kyLnALhIfbFX` Health Check | Cron cada N min. Ping a Dentalink + Evolution. Setea `dentalink:status` en Redis. |
| `QsGBGkZdGu5gTdBf` Daily Summary | Cron 8 AM. Manda resumen de recordatorios del día al grupo de admins. |
| `fosfga62zNaN0qrx` Auto Reactivar | Si pasa 1h sin actividad humana en una conversación con label humano → quita label, bot vuelve. |

---

## Pre-prep para tests sintéticos

`scripts/test_prep_restore.py --prep`:
1. Backup completo del v6
2. Disable nodos que tocan APIs externas (Send/Typing, HTTP Send Admin, 4 tools Dentalink de escritura)
3. Cambiar `secretaryPhone` en `escalar_a_secretaria` → Lucas (recibe escalados de prueba)
4. Webhook path → `evolution-v6-test` (separado de `evolution-v2` de prod). webhookId intacto.
5. Activar workflows helpers (`tmp-test-cleanup-v6`, `tmp-test-seed-memory`)
6. Activar v6

`--restore <backup_path>` deshace todo lo anterior.

---

## Decisiones arquitectónicas clave

| Decisión | Por qué | Cuándo |
|---|---|---|
| Auto-layout con Dagre via Node.js | n8n usa Dagre internamente; layouts topológicos manuales con 100 nodos quedan ilegibles. | 2026-05-11 |
| Chatwoot label como single source of truth (vs Redis silence flag) | Iri/doctora ven el estado en su UI; el workflow Human Takeover ya lo entiende. | 2026-05-12 |
| Funcional > Conversacional (R0 absoluta) | Lucas explícito: el bot debe cumplir funciones, no conversar. El LLM es generador libre, los band-aids reducen riesgo pero no lo eliminan. | 2026-05-12 |
| Dentalink como única fuente de verdad de pacientes/turnos (vs Supabase) | Las tablas Supabase `pacientes`/`conversaciones` nunca existieron (proyecto apunta a Nexora). Mejor eliminar el doble-source. | 2026-05-12 |
| Recordatorios cron lun-vie en lugar de diario | El algoritmo `addBusinessDays(hoy, 2)` con cron diario hacía vie/sáb/dom converger al martes → 3 recordatorios al mismo paciente. | 2026-05-11 |

Ver [`docs/fixes.md`](fixes.md) para detalle.
