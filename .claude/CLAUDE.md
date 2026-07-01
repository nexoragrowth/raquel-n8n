# Proyecto: Agente WhatsApp Dra. Raquel Rodriguez (Áurea Odontología Estética)

> Este archivo se inyecta automaticamente en cada sesion de Claude Code abierta desde `D:\Dev\dra-raquel\`.
> Define el contexto LOCAL del proyecto. El `context.md` GLOBAL del vault (Lucas) se inyecta por separado via SessionStart hook.

---

## Que es este proyecto

Bot de WhatsApp para clinica de ortodoncia (San Salvador de Jujuy). Construido en n8n self-hosted + Evolution API (WhatsApp) + Dentalink (agenda medica) + Supabase (data layer) + Postgres (memoria LangChain) + Redis (buffer / kill-switch / rate limit).

Caso bandera de Nexora (consultorios/clinicas). Primera cuota cobrada. Doctora paga mensual.

## Que hace el bot (scope MVP cerrado)

**SI hace** (automatico):
1. **Agendar** turnos nuevos (busca disponibilidad Dentalink + reserva)
2. **Recordar** turnos 24h y 72h antes (workflow aparte, cron 9 AM Arg) — ✅ FUNCIONA
3. **Confirmar / Cancelar** turnos post-recordatorio
4. **Info canned**: precio consulta, horarios, direccion, alias bancario

**NO hace** (escala SIEMPRE):
- Urgencias / dolor / sangrado / aparato salido → derivar al grupo
- Foto dental / consulta medica → derivar
- Comprobantes de pago → recibe + deriva al grupo (NO valida monto)
- Cualquier otra cosa → silencio o derivar

**JAMAS hace** (banlist regex post-output):
- Decir "venite" / "los esperamos" / "ahora mismo a la clinica"
- Dar instrucciones operativas/medicas ("guarda", "trae", "toma X", "saca")
- Dar diagnostico u opinion ("no te preocupes", "es normal", "que macana")
- Dar la direccion fisica como confirmacion de cita

## Estado al 2026-05-22 (noche, post-Rounds 5/6/7)

- **v6 (`O155MqHgOSaNZ9ye`)**: ✅ **EN PRODUCCION** (cutover 21/5 01:50 AM). 120 nodos (Round 9 sumó 5: re-check #1 [4 nodos] + Gate Humano Final). Send + Typing + Admin Confirm enabled. Path `evolution-v2`. Las 4 write tools Dentalink enabled.
- **v4 (`jaO9zQb6l5HM07gg`)**: rollback backup, inactivo.
- **Recordatorios (`7RqTApkvVavRmq3R`)**: ✅ activo. Round 4 aplicado (`id_estado != 18` evita doble recordatorio a confirmados).
- **Cron - Resumen Clinico Pacientes (`BO1cdE8xmqln4IeO`)**: ✅ **NUEVO 22/5 noche**. Cron 02:00 ARG diario + webhook manual `trigger-resumen-clinico`. Resume últimos 30 msgs de `conversaciones` con gpt-4o-mini → escribe a `pacientes.resumen_clinico` + `resumen_actualizado_at`. 41 pacientes hidratados al cierre. Costo ~$0.10/mes.
- **Helper - Notify Grupo (`S5U6tSipzlgFHCkf`)**: ✅ **NUEVO 22/5 noche**. Webhook `notify-grupo` con plugin Evolution. Usado por `escalar_a_secretaria` para mandar al grupo derivaciones (`120363407321448469@g.us`). Reemplaza la IP rota que generaba fallo silencioso.
- **Auto Reactivar Bot (`fosfga62zNaN0qrx`)**: ✅ activo (**1h** sin humano → re-bot). Historia: era 1h → Round 9 (9/6) lo subió a 4h a pedido de Iri → **revertido a 1h el 24/6 a pedido de la Dra** (con 4h el agente quedaba mudo demasiado, poco protagonismo). Es por INACTIVIDAD (resetea con cada msg, no pisa conversación activa); anti-pisada real = gates R9; override manual de Iri = label `no_bot`. Script: `apply_fix_autoreactivar_1h.py`.
- **Human Takeover - Chatwoot (`w7BBpZeEwZnpCX1q`)**: ✅ activo.
- **Health Check / Daily Summary**: activos.

### Rounds de fixes acumulados

- **Round 1 (9/5)**: post-incidente Mariela. 5 fixes + Banlist Validator.
- **Round 2 (12/5)**: endurecimiento (R0, cron Recordatorios, RAG desconectado, etc).
- **Round 3 (21/5)**: pre-cutover. Prefiltro Lucas + leak Agendar v1.
- **Round 4 (22/5 AM)**: Recordatorios skip `id_estado=18`.
- **Round 5 (22/5 PM)**: idempotencia Sub-Agent Confirmar — "REGLA ABSOLUTA: si id_estado=18, NO escalar, canned y FIN".
- **Round 6 (22/5 PM)**: **leak Carmen Agostini v2 (root cause)**. El LLM alucinaba `5493886869400` y leakeaba identidad de Carmen. Causa: el `phone` del webhook NUNCA llegaba al input del LLM (`text` era solo el mensaje del paciente). Fix: `text` de los 5 sub-agents ahora incluye `phone` + `pushName` + `resumen_clinico` del paciente desde nodo `Get Paciente Context` (rama paralela desde Edit Fields). Tool descriptions despersonalizados.
- **Round 7 (22/5 noche)**: memoria larga via resumen nightly (descrito arriba en Cron). E2E validado: LLM razona con memoria larga.
- **Round 8 (22/5 noche, ultimo)**: dos fixes en cadena:
  1. **`escalar_a_secretaria` fallo silencioso**: hardcoded a IP `http://187.127.0.110:65302` que daba `ECONNREFUSED`. Las escalaciones del bot NUNCA llegaban a Iri/Dra/Lucas durante todo el dia (28 escalaciones reales de hoy quedaron operativamente "fantasma" hasta que las pasamos a mano al grupo via helper). Fix: el tool ahora postea al webhook `notify-grupo` que usa plugin Evolution con cred real.
  2. **Canned interpretativo "Para confirmar agenda de la doctora..."** en Sub-Agent General: respondia eso como default a cualquier consulta no clasificada, inventando el motivo. Reemplazado por neutro "Le paso tu consulta a la secretaria lo mas pronto posible.".
- **Round 9 (9/6)**: **doble re-check humano (anti-pisada) + takeover 4h**. Problema: si un humano tomaba el chat durante la generacion/envio del bot, el bot lo pisaba porque el check de label `humano` solo corria al INICIO del flujo (que ocurre a ~+24s del mensaje, por el `Buffer: Wait 10s` + ~13s de latencia fija).
  1. **Re-check #1 (pre-split, ~+32-38s)**: 4 nodos entre `Banlist Validator` y `Necesita Formatting?` → `Re-check Humano` (HTTP clon de `Chatwoot - Buscar Conversacion`, continueOnFail) → `Hay humano ahora?` (code: parsea label + passthrough item Banlist preservando `output`) → `Humano aparecio?` (IF `hasHumanoLabel==true`) → `Aviso humano tomo chat` (code). Cubre la ventana de generacion (Router+Sub-Agent+tools+Banlist).
  2. **Gate Humano Final (#2, post-Typing, ~+43s, JUSTO antes de enviar)**: 1 nodo code `Gate Humano Final` entre `Evolution - Typing` y `Evolution API - Enviar Mensaje`. Modo once-for-all-items: chequea Chatwoot 1 vez; sin humano → `return items` (pairing intacto, envia normal); con humano → `return []` (no envia) + aviso. Cubre el **tail** (~11s: Formatting Agent + Typing + Delay Humano) que el #1 no alcanza. Resuelve el caso mas comun real: la secretaria ve entrar el mensaje y salta a responder mientras el bot "escribe".
  3. **Aviso al grupo**: ambos avisos postean a `notify-grupo` con el resumen **en la QUERY** (`qs:{phone,resumen}`), NO en el body. El helper arma `[ESCALADO BOT] + (query.resumen || body.text || 'Caso escalado sin resumen.')` y `escalar_a_secretaria` lo manda con `sendQuery:true`. **Bug inicial**: el primer intento mando el resumen en `body` → llegaba "Caso escalado sin resumen.". Fix: body→qs. **NO_REPLY**: solo avisa si el bot tenia respuesta real (output != `[NO_REPLY]`); si no tenia nada que enviar, no hay pisada que reportar → no avisa (evita ruido).
  4. **Takeover 1h→4h** en Auto Reactivar (`ONE_HOUR=3600` → `FOUR_HOURS=4*3600`).
  - **Cobertura total**: desde +24s (check inicial) hasta ~+43s (gate, justo antes de enviar). Residual: milisegundos entre el gate y el send real. **Fail-open** en ambos re-checks (si Chatwoot cae, envia igual; sin regresion).
  - **E2E validado en vivo** (tests por API simulando el webhook de Evolution + aplicando label en timing controlado): 94372 (re-check #1 detecta humano → aborta + avisa con resumen), 94477 (gate no-regresion: sin humano → devuelve item → envia normal), 94489 (gate #2 detecta humano en el tail → aborta). Para gatillar el caso "humano toma mid-generacion" hay que aplicar el label entre +24s y +43s; a mano es casi imposible (ventana fina), por eso se hizo por API midiendo los timestamps reales de los nodos.
  - **Gate Error Tecnico (mismo bug, FIXEADO 9/6)**: posteaba a `notify-grupo` con resumen en `body` → sus avisos de error tecnico llegaban "sin resumen". Fix: body→qs. Testeado: el helper recibe `query.resumen` OK.
  - **Excepcion al modo "solo reporto"**: Lucas pidio explicitamente que Claude aplicara estos cambios por API (backup pre/post + diff mostrado). La regla general de aplicar a mano sigue vigente para lo demas.

- **Round 10 (19/6)**: **bot confirma turnos PASADOS + caso Catalina (pre-llegada)**. Lucas autorizo explicitamente aplicar (se iba, "metele robusto y testeado"). Excepcion puntual a `feedback_no_aplicar_cambios`, igual que Round 9.
  1. **[CRITICO] Confirma turnos pasados**. Casos reales 19/6: Delfina ("confirmados los 2 turnos: 3 de Junio y 23 de Junio") y Geronimo ("8 de Junio y 23 de Junio"). **Root cause**: el tool `consultar_recordatorios_abiertos` (PASO 0 del Sub-Agent Confirmar) consultaba `recordatorios_enviados` con `confirmado_at=is.null&cancelado_at=is.null` SIN filtro de fecha. Devolvia filas viejas que nunca se cerraron (el paciente nunca confirmo/cancelo en su momento). Cuando el paciente ahora dice "confirmo", el agente itera TODAS las filas abiertas y confirma cada una -> `confirmar_turno` marca id_estado=18 en Dentalink **tambien para el turno pasado** + lo recita. Probado contra Supabase: 35 filas pasadas abiertas, 33 phones "armados". **Fix determinista**: la URL del tool ahora agrega `&fecha_turno=gte.{{ $now.setZone('America/Argentina/Buenos_Aires').toFormat('yyyy-MM-dd') }}` (URL pasada a expresion n8n). Validado read-only: elimina las 35 pasadas, conserva las 4 futuras, ninguna futura perdida. **Defensa en profundidad**: regla "NUNCA CONFIRMES TURNOS PASADOS" agregada al prompt PASO 0. Resolucion de la expresion `$now.setZone().toFormat()` en runtime **PROBADA el 20/6** (workflow throwaway con la expresion literal en query a Dentalink -> devolvio solo futuros). Fail-safe ademas: si no resolviera, PostgREST devuelve vacio -> "0 filas" -> flow legacy PASO 1 que ya es future-only (NO regresion).
  1b. **[COMPLEMENTO de Cogne, socio de Lucas, 19/6 ~15:47 ARG] segunda capa en `ver_turnos_paciente`**: Cogne agrego a la tool Dentalink (path PASO 1/2/comprobante, NO PASO 0) un query fijo `q={"fecha":{"gte":{{ $now... }}}}` (sendQuery=true). Cubre el camino legacy que mi fix no tocaba. **Validado el 20/6 contra Dentalink real** (pid 110 Geronimo): sin filtro 50 turnos desde 2024; con filtro solo 3 (>= hoy), cero pasados. Campo `fecha` y operador `gte` validos en Dentalink. Complementario, NO pisa mi fix (paths distintos). Nota menor: la `toolDescription` de ver_turnos_paciente sigue diciendo que el LLM pasa `q` pero ahora `q` esta hardcodeado (el LLM ya no lo controla); inofuso para los flows actuales (confirm/cancel/read todos quieren futuros). Cogne NO dejo backup local; diff confirmado contra `v6_POST_FIX_PASADOS_PRELLEGADA_20260619_121651.json` (solo cambio ese 1 nodo, mis 3 fixes intactos).
  2. **[ALTO] Caso Catalina "Estoy llegando" -> "¿cancelar o reprogramar?"**. El Router clasificaba pre-llegada como `confirmar`/`cancelar` (con recordatorio reciente en memoria). El **Sub-WF Cancelar es codigo deterministico sin LLM** (no puede auto-silenciar), y la regla pre-llegada vivia solo en los Sub-Agents General/Confirmar, NUNCA en el Router. **Fix**: regla 1.5 "AVISO DE LLEGADA / EN CAMINO -> consulta_general" agregada al prompt del Router (el Sub-Agent General ya silencia con [NO_REPLY]). Distingue "llegando/en camino/ya estoy cerca" (silencio) de "voy/ahi estare" (confirmacion futura). **Testeado offline** con gpt-5-mini reasoning=low (mismo modelo/config que prod) sobre el prompt EXACTO desplegado: 15/15 casos OK; baseline reproduce el bug. (E2E webhook NO se pudo: el `simulate_v6_message.py` quedo desactualizado, el Webhook Validator ahora exige header `x-evolution-secret` y el secret no esta en `.env` local.)
  3. **Pedido Dra #1 "que el agente siempre diga que es asistente virtual"**: ya cubierto por las reglas IDENTIFICACION existentes (casos a-d) + el aviso del gate humano ya se autoidentifica. No se toco (evitar over-identificacion). Monitorear.
  4. **Cleanup pendiente para Iri**: 3 turnos PASADOS quedaron marcados id_estado=18 en Dentalink hoy ANTES del fix (todos pre-12:16 ARG): Delfina cita 7901 (3/6), Geronimo cita 7902 (8/6), Diego cita 8026 (4/6). Revisar/corregir el registro de atencion real en Dentalink a mano (Claude NO los reviro: write riesgoso, necesita criterio sobre el estado correcto).
  - Backups: `workflows/history/v6_PRE_FIX_PASADOS_PRELLEGADA_20260619_121651.json` / `v6_POST_...`. Script: `scripts/apply_fix_confirma_pasados_y_prellegada.py`. webhookId `evo-webhook-v2` + path `evolution-v2` preservados, active=True, 120 nodos.

### Lecciones operativas que NO se pueden olvidar

1. **Las `toolDescription` son contexto del LLM** — cualquier "ejemplo real" hardcoded ahi lo van a copiar todos los sub-agents wireados al tool (causa raíz del leak Carmen).
2. **Reglas tipo "NUNCA hagas X" son inutiles si el LLM no tiene los inputs para hacer lo correcto** — defensa de prompt sin defensa de datos = bug oculto.
3. **Cualquier nuevo sub-agent debe recibir `phone` + `pushName` como contexto explicito** en su `text` input (no en el system prompt — el system prompt es estatico, no resuelve placeholders dinamicos).
4. **`try/catch` con `console.log` SOLAMENTE** es un fallo silencioso. Si el tool hace HTTP a algo critico (Evolution send, Chatwoot label), la falla debe ser visible. Las 28 escalaciones fantasma de hoy son consecuencia directa de esto.
5. **`escalar_a_secretaria` ahora va al grupo `120363407321448469@g.us`** (no al phone personal de Lucas). Si se cambia el grupo, hay que actualizar el helper `S5U6tSipzlgFHCkf`.

### Backlog menor (no critico, dejar pendiente)

- En `escalar_a_secretaria.jsCode` quedo declarada `const evolutionBase = 'http://187.127.0.110:65302';` y `const instance = 'raquel';` que ya no se usan (todo va via helper webhook ahora). Limpiar en proximo round.
- Pulir prompt del resumen nightly: algunos resumenes incluyen "se coordino con Iri" — el resumen deberia ser SOLO sobre el paciente, no la asistente.
- Canned escalacion en Sub-Agent Urgencia: revisar si la frase actual ("Le paso a la secretaria Irina para que le ayude lo antes posible.") es adecuada o se puede unificar con la neutra del Sub-Agent General.

## Incidente clave a no olvidar (2026-05-09)

Una mama real (Mariela) recibio del v6 instruccion de ir a la clinica un sabado con clinica cerrada. Bot dijo: "guarda la pieza, traete el DNI, venite ahora mismo, Balcarce 37 2do piso, los esperamos". Mariela respondio "Bien, ahora salimos para la clinica". La doctora alcanzo a apagar el bot a tiempo.

Root cause triple:
1. Kill-switch usaba phone del destinatario en lugar del emisor → `/bot off` se ignoraba silencioso.
2. System prompt enseñaba "Te esperamos" en ejemplo (contradice R22 que lo prohibe) → bot copio literal.
3. Router no veia memoria → "esta incomoda, no come" se clasifico como consulta_general en vez de urgencia.

Auditorias completas en `<vault>/projects/audit-memoria-v6.md` y `audit-base-conocimiento-v6.md`.

## Reglas duras de este proyecto

1. **El v6 esta en PRODUCCION (desde 21/5 01:50 AM)**. Cualquier cambio al workflow vivo requiere: (a) backup pre, (b) dry-run o diff antes de aplicar, (c) backup post + verificacion. Si algo grave se rompe, `python scripts/apply_cutover.py --rollback` lo vuelve a shadow (recibe pero no responde).
2. **Cero PUTs al workflow sin backup previo**. Ver `scripts/` para patrones.
3. **Preservar `webhookId: evo-webhook-v2` siempre** (leccion #1 vault: si lo perdes, Evolution apunta a UUID null y rompe todo).
4. **PUT al API solo acepta** `name, nodes, connections, settings, staticData`. Settings solo permite `saveExecutionProgress, saveManualExecutions, saveDataErrorExecution, saveDataSuccessExecution, executionTimeout, errorWorkflow, timezone, executionOrder, callerPolicy, callerIds`. Cualquier otra key → 400.
5. **Defensa en profundidad sobre prompt**: cada regla critica debe estar en al menos 2 capas (prompt + gate deterministico). El banlist regex es la ultima linea.
6. **MVP es agendar + recordar + escalar todo lo demas**. Cualquier intento de meter features extra (vision, RAG abierto, sub-agents creativos), parar.
7. **fromMe filter universal**: cualquier mensaje saliente del numero de la clinica que NO sea del bot → aplica label humano + silence flag Redis. No depender de Chatwoot solo.

## Accesos y endpoints

Credenciales en `.env` del repo (gitignored, ver `.env.example` como template). Carga via:

```python
from lib_env import env, require
N8N_API_KEY = require('N8N_API_KEY')
SUPABASE_URL = env('SUPABASE_URL')
```

Variables disponibles: `N8N_BASE_URL`, `N8N_API_KEY`, `N8N_WORKFLOW_*_ID`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `EVOLUTION_*`, `CHATWOOT_*`, `DENTALINK_*`, `ADMIN_*_PHONE`, `WHATSAPP_DERIVACIONES_GROUP_JID`.

Backup historico en `<vault>/projects/dra-raquel-n8n.md` seccion "Acceso (NO PERDER)".

Datos clave para tener a mano (NO secretos):
- n8n UI: https://n8n.raquelrodriguez.com.ar
- Webhook v6: https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2
- Evolution instance: `raquel` (endpoint VPS-only)
- Chatwoot: https://chat.raquelrodriguez.com.ar
- **Supabase clinica (PROD)**: `https://dchztroesbpwxxkfywwu.supabase.co` (project: nexoragrowth, env: main/PRODUCTION). El v6 SIEMPRE apunto a este Supabase. Schema auditado 21/5 — ver seccion siguiente.

### Supabase schema (auditado 2026-05-21)

| Tabla | Filas | Columnas | Uso actual |
|---|---:|---|---|
| `agent_learnings` | 0 | (vacia, schema pendiente de revisar) | aprendizajes del bot — no se usa todavia |
| `conversaciones` | 1334 | `id (uuid)`, `paciente_id (uuid FK)`, `telefono`, `rol` (user/ai/system), `mensaje`, `timestamp`, `metadata (jsonb)`, `fuente` (whatsapp/...) | **ya se llena** (origen a confirmar). Es el log persistente de TODOS los mensajes. |
| `knowledge_base` | 34 | `id`, `categoria`, `titulo`, `contenido`, `embedding (vector)`, `metadata (jsonb)`, `created_at` | RAG real. Tiene horarios, info de la clinica, secretaria. Lo consume Sub-Agent General via `buscar_conocimiento`. |
| `n8n_chat_histories` | 1733 | `id (int)`, `session_id` (phone), `message (jsonb)`, `created_at` | Memoria LangChain del v6 (TTL stale=3d, preserva `source IN (wa_outbound, human_takeover, reminder_note)`). |
| `pacientes` | 262 | `id (uuid)`, `telefono`, `nombre`, `email`, `fecha_nacimiento`, `tratamiento_actual`, `etapa_tratamiento`, `profesional_id_dentalink`, `paciente_id_dentalink`, `es_paciente_problema`, `preferencia_horario`, `notas_internas`, `created_at`, `updated_at`, `human_takeover`, `human_takeover_at`, `human_takeover_by`, `chatwoot_contact_id`, `chatwoot_conversation_id` | **ya se llena**. Master de pacientes con info clinica + flags operativos. |
| `turnos_log` | 0 | vacia | log de turnos (reserva/confirma/cancela). A poblar. |
| `urgencias_log` | 0 | vacia | log de urgencias detectadas. A poblar. |

**Hallazgo importante**: `conversaciones` y `pacientes` YA tienen data (1334 / 262 filas) — algun workflow/integracion los esta llenando, pero el v6 en su flow principal solo lee `knowledge_base`. Falta auditar quien escribe a esas tablas hoy y asegurar consistencia.

### Plan en curso (memoria larga)

- Extender el v6 para loguear CADA mensaje (paciente, bot, secretaria/doctora — incluso con label humano activo) a `conversaciones`.
- Hidratar contexto: SELECT a `conversaciones` ANTES del Router para inyectar las ultimas N mensajes al LLM. Asi el bot tiene memoria >3d sin depender solo de `n8n_chat_histories`.
- Loguear eventos de turnos a `turnos_log` y urgencias a `urgencias_log`.
- Grupo de derivaciones (destino escalaciones): `120363407321448469@g.us` ("WhatsApp Clinica Raquel"). Miembros: Lucas + Dra. Raquel.
- Admin phones whitelisted para `/bot off|on|status`: Lucas `5491161461034`, Irina `5493885786946`, Dra. Raquel `5493513976787`.

## Fuentes externas a este repo (siempre cargar)

- **Vault context**: `C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/projects/dra-raquel-n8n.md` (notas persistentes con todas las lecciones aprendidas, IDs, accesos, evolucion del workflow).
- **Sessions log**: `C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/sessions/YYYY-MM-DD.md` (log diario que llena Claude. SE ESCRIBE AHI, no en este repo, para que el SessionStart hook lo inyecte en otras sesiones).
- **Handoff tecnico v6** (parcialmente desactualizado, ver disclaimer arriba): `C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/projects/handoff-dra-raquel-v6.md`
- **Auditoria memoria v6**: `C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/projects/audit-memoria-v6.md`
- **Auditoria base conocimiento v6**: `C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/projects/audit-base-conocimiento-v6.md`

## Estructura del repo

```
D:\Dev\dra-raquel\
├── .claude\
│   ├── CLAUDE.md              ← este archivo
│   ├── stack.md               ← stack tecnico + Exclusions
│   └── project-context.md     ← contexto de negocio
├── workflows\
│   ├── current\               ← ultimo snapshot del v6 vivo (GET API)
│   └── history\               ← backups timestamped pre/post cada cambio
├── scripts\                   ← Python para fixes, audits, deploys
│   └── apply_*.py             ← un script por cambio aplicado
├── prompts\
│   ├── v6_actuales\           ← snapshot de los prompts actuales del v6 (referencia)
│   └── v7_supervisor\         ← prompts nuevos del refactor (orquestador + sub-agents)
├── tests\                     ← tests sinteticos (mensajes simulados vs intent esperado)
├── docs\
│   ├── plan-mvp.md            ← plan vigente del MVP
│   └── README.md              ← este proyecto en 1 pagina
└── README.md
```

## Estilo de trabajo en este proyecto

- Lucas (founder/owner) revisa cambios antes de aplicar. NUNCA hacer PUT al workflow vivo sin mostrar el diff primero.
- Cada cambio significativo deja un script `.py` en `scripts/` con nombre `apply_<descripcion>.py` + backup pre/post en `workflows/history/`.
- Tests sinteticos en `tests/` para validar intent classifier y banlist antes de cada PUT.
- Sessions log se escribe al VAULT (no acá), respetando regla global.

## Next steps (al 2026-05-21, post-cutover)

### En curso

1. **Memoria larga via Supabase `conversaciones` + `pacientes`** (en `dchztroesbpwxxkfywwu`). Hoy el bot solo lee `n8n_chat_histories` con TTL de 3 dias y solo preserva `source IN (wa_outbound, human_takeover, reminder_note)`. Resultado: cuando un paciente dice "Confirmo" sin recordatorio reciente del cron, el bot no tiene contexto y escala. Fix: integrar `conversaciones` para contexto >3d + `pacientes` para identificar al paciente sin recargar Dentalink cada vez.
2. **Fallback Dentalink en Sub-Agent Confirmar/Cancelar**: si no hay NOTA INTERNA, llamar `ver_turnos_paciente` + filtrar turnos proximos. Si hay UNO solo, asumir ese. Si varios, preguntar. Resuelve casos como "Confirmo" sin recordatorio previo.
3. **Voz / naming consistencia** (detectado 21/5 post-cutover):
   - "Iri" / "Irina" solas → siempre "la secretaria Iri/Irina" en outputs canned (pacientes nuevos no saben quien es).
   - "la doctora" en primera mencion → "la Dra. Raquel".
   - "imputar" (jerga contable) → "registrar el comprobante".
   - Voseo/ustedeo inconsistente en Sub-Agent Agendar.
   - "primera consulta" suelta → aclarar precio + duracion.
   - Alias bancario sin contexto → ofrecer CBU/banco si pide alternativa.

### Backlog (cosmeticos)

- "Aurea Odontologia Estetica" mencion de marca en saludos.
- Despedidas canned consistentes ("Cualquier consulta nos escribis").
- Re-identificarse cuando bot retoma de Iri (post auto-reactivar 1h).
- "el turno" ambiguo cuando hay multiples → especificar siempre fecha.
- Sub-Agent Agendar verboso (agrega pago/72hs/alias no pedido).
- Mayusculas como enfasis (PRE-reservado, CRITICO) → prose normal.

### Observabilidad (idea con Lucas, post)

- Agente observer Nivel 1: cron cada 15-30min, lee executions del v6, aplica heuristicas anti-alucinacion (banlist amplio, info inventada, leak detection), notifica a Lucas via WhatsApp/Telegram. Read-only primer semana, despues subir a Nivel 2 (safe actions: aplicar label humano, cancelar turnos fantasma).
