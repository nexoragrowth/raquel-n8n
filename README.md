# Agente WhatsApp — Dra. Raquel Rodriguez (Áurea Odontología Estética)

Bot de WhatsApp para una clínica de ortodoncia en San Salvador de Jujuy. Primera instalación pagante de **Nexora** (caso bandera para PyMEs argentinas). Construido en n8n self-hosted + Evolution API + Dentalink + Supabase + Postgres + Redis.

> **Estado al 2026-05-12**: v6 multi-agent, **desactivado en prod**, endurecido con dos rounds de fixes post-incidente. Listo para shadow 24-48h y cutover supervisado.

---

## Qué hace (scope MVP)

El bot cumple **4 funciones** específicas:

1. **Agendar** turnos nuevos (busca disponibilidad en Dentalink + reserva)
2. **Recordar** turnos 48h hábiles antes (workflow aparte, cron 9 AM Arg lun-vie)
3. **Confirmar / Cancelar** turnos post-recordatorio
4. **Info canned** (precio consulta, horarios, dirección, alias bancario)

Para todo lo demás: **escalación al grupo** "WhatsApp Clínica Raquel" (`120363407321448469@g.us`, miembros: Lucas + Dra. Raquel).

## Qué NO hace (banlist explícito)

- Urgencias / dolor / sangrado / aparato salido → escalar
- Foto dental / consulta médica → escalar
- Comprobantes de pago → escalar al grupo (NO valida monto)
- Decir "venite" / "los esperamos" / "ahora mismo a la clínica" — bloqueado por Banlist regex
- Dar instrucciones operativas/médicas ("guardá", "traé", "tomá X", "no comas")
- Dar diagnóstico u opinión ("no te preocupes", "es normal")

---

## Componentes

| Capa | Tech | Rol |
|---|---|---|
| Mensajería | Evolution API (instance `raquel`) | WhatsApp ↔ webhook n8n |
| Orquestación | n8n self-hosted (`n8n.raquelrodriguez.com.ar`) | Workflows + lógica |
| LLM | OpenAI gpt-5 / gpt-5-mini | Router + 5 sub-agents (Confirmar, Cancelar, Agendar, Urgencia, General) |
| Agenda médica | Dentalink API (`api.dentalink.healthatom.com`) | Single source of truth de pacientes + turnos |
| Atención humana | Chatwoot (`chat.raquelrodriguez.com.ar`) | Label `humano` = bot pausa esa conversación |
| Memoria LLM | Postgres `n8n_chat_histories` | Historial conversacional 50 turnos |
| Buffer / kill-switch / rate limit | Redis | Estado efímero |
| Data layer (futuro) | Supabase | Pendiente: proyecto clínico nuevo (hoy no existe) |

Ver [`docs/architecture.md`](docs/architecture.md) para diagramas y detalles del flow.

---

## Workflows activos en n8n

| ID | Nombre | Estado |
|---|---|---|
| `O155MqHgOSaNZ9ye` | Agente IA v6 — Multi-agent | **OFF** (sin OK explícito) |
| `jaO9zQb6l5HM07gg` | Agente IA v4 — Multimedia Unificada | OFF (rollback backup) |
| `7RqTApkvVavRmq3R` | Recordatorio de Turno 48HS | ON ✅ |
| `Yjl6kyLnALhIfbFX` | Health Check (Dentalink + Evolution) | ON ✅ |
| `QsGBGkZdGu5gTdBf` | Daily Summary Recordatorios | ON ✅ |
| `fosfga62zNaN0qrx` | Auto Reactivar Bot (1h sin humano) | ON ✅ |
| `w7BBpZeEwZnpCX1q` | Human Takeover — Chatwoot | ON ✅ |

---

## Historia de bugs y fixes

El proyecto pasó por dos rounds de endurecimiento post-incidente:

- **Round 1 (2026-05-09)**: incidente Mariela — bot le dijo "venite a Balcarce 37" a una paciente un sábado con clínica cerrada. 5 capas determinísticas aplicadas + Banlist regex (22 patrones). Ver [`docs/fixes.md`](docs/fixes.md).
- **Round 2 (2026-05-12)**: endurecimiento MVP. R0 anti-conversación, Chatwoot label cuando humano habla (WA Web/Mobile), RAG contaminado desconectado, 4 Supabase rotos desconectados, `[NO_REPLY]` filtrado post-hoc, `Clear Old Memory` selectivo. Ver [`docs/fixes.md`](docs/fixes.md).

**Matriz completa de 31 bugs reportados** (estado fixeado / pendiente / lección documentada): [`docs/bugs.md`](docs/bugs.md).

---

## Estado actual vs MVP

**Funcionalmente cerca del MVP.** Faltan 3 cosas para cutover supervisado:

1. ✅ Las 4 funciones existen y andan a nivel código.
2. ⚠️ Tests sintéticos: 82/100 PASS contra v6 endurecido. **2 fixes pendientes** antes de re-correr (Banlist regex para `la esperamos`, R0 menos agresivo en saludos).
3. ❌ Shadow 24-48h con tráfico real.

Detalle de qué falta: [`docs/pending.md`](docs/pending.md).

---

## Cómo correr scripts

Todos los scripts en `scripts/` requieren env var `N8N_API_KEY` (JWT del n8n public API). Algunos también `CHATWOOT_TOKEN`.

```bash
export N8N_API_KEY="<jwt-de-n8n-public-api>"
export CHATWOOT_TOKEN="<chatwoot-api-access-token>"

# ejemplo: aplicar fix de cron recordatorios
python scripts/apply_cron_recordatorios_fix.py

# ejemplo: prep modo shadow para correr tests
python scripts/test_prep_restore.py --prep

# después de los tests, restore
python scripts/test_prep_restore.py --restore workflows/history/v6_PRE_TEST_PREP_<ts>.json
```

Cada script:
- Toma snapshot pre-cambio en `workflows/history/v6_PRE_<algo>_<ts>.json`
- Aplica el patch via PUT al n8n API
- Guarda snapshot post en `v6_POST_<algo>_<ts>.json`

---

## Estructura del repo

```
.
├── README.md              ← este archivo
├── .claude/               ← contexto Claude Code (CLAUDE.md, stack.md, project-context.md)
├── docs/                  ← documentación completa
│   ├── architecture.md    ← cómo está armado el flow
│   ├── bugs.md            ← matrix de 31 bugs reportados
│   ├── fixes.md           ← rounds 1 y 2 de endurecimiento
│   ├── pending.md         ← qué falta para MVP
│   └── runbook.md         ← operación día-a-día
├── scripts/               ← Python para fixes/audits/deploys (un script por cambio)
├── tests/                 ← tests sintéticos
├── prompts/               ← snapshots de prompts
├── workflows/             ← snapshots JSON del workflow (gitignored)
└── .gitignore
```

---

## Cómo Codex / colaborador debería arrancar

1. Leer este README hasta acá.
2. Leer [`docs/architecture.md`](docs/architecture.md) — entender el flow.
3. Leer [`docs/bugs.md`](docs/bugs.md) — entender qué problemas tuvimos y cuáles ya se resolvieron.
4. Leer [`docs/pending.md`](docs/pending.md) — entender qué falta.
5. Revisar [`docs/runbook.md`](docs/runbook.md) cuando toque operación.
6. Scripts: revisar `scripts/` — cada uno tiene docstring que explica qué hace y por qué.

---

## Reglas duras del proyecto

1. **NUNCA prender el v6 sin OK explícito de Lucas**. Hubo incidente real con paciente. Confianza de la doctora se recupera con proceso, no con velocidad.
2. **Cero PUTs al workflow sin backup previo**. Ver patrón en `scripts/`.
3. **Preservar `webhookId: evo-webhook-v2` siempre**. Si lo perdés, Evolution apunta a UUID null y rompe todo.
4. **PUT al n8n API solo acepta** `name, nodes, connections, settings, staticData`. Cualquier otra key → 400.
5. **Defensa en profundidad sobre prompt**: cada regla crítica debe estar en al menos 2 capas (prompt + gate determinístico). El Banlist regex es la última línea.
6. **MVP scope cerrado**: cualquier intento de meter features extra (vision, RAG abierto, sub-agents creativos), parar.
7. **fromMe filter universal**: cualquier mensaje saliente del número de la clínica que NO sea del bot → label humano en Chatwoot + silencio.
