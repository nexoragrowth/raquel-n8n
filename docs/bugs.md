# Matriz de bugs reportados en producción

Inventario completo de los 31 bugs/incidentes que tuvo el proyecto. Cruzado con sessions logs del vault de Lucas, auditorías 2026-05-09 (`audit-memoria-v6.md`, `audit-base-conocimiento-v6.md`) y las 13 notas tipo `fail` que Lucas destiló a Supabase `creator_notes` (user `47bad33a-cdac-4db0-a622-a52e27016114`).

**Leyenda:**
- 🟢 Fixeado y validado en prod
- 🟡 Fixeado pero sin validar con tráfico real
- 🔴 Pendiente (no fixeado aún)
- 📚 Lección documentada (aprendida, ya no recurrente)
- ⚠️ Fix superficial (la causa raíz sigue presente)

## Conteo final

| Estado | Cantidad |
|---|---|
| 🟢 Fixeado y validado | 11 |
| 🟡 Fixeado sin validar prod | 5 |
| ⚠️ Fix superficial | 1 |
| 🔴 Pendiente | 8 |
| 📚 Lección documentada | 6 |
| **TOTAL** | **31** |

---

## Tabla completa

| # | Bug / Incidente | Cuándo | Root cause | Fix aplicado | Test | Estado |
|---|---|---|---|---|---|---|
| 1 | Bot invita a paciente Mariela a clínica cerrada un sábado ("venite a Balcarce 37, los esperamos") | 2026-05-09 13:05 | Cero capa determinística post-LLM. Prompt enseñaba ejemplo literal "Te esperamos". | Banlist Validator regex (22 patrones) entre Formatting Agent → Split | ✅ 13/13 PASS contra mensajes reales | 🟢 |
| 2 | Kill-switch `/bot off` ignorado cuando admin escribe desde su WA | 2026-05-09 12:53 | Chequeaba `!fromMe && ADMINS[phone]`. Si admin manda desde su celular con `fromMe=true`, ambas condiciones fallan. | Reescribir `Kill-switch Check` para detectar admin con `!fromMe && phone IN ADMINS` (estricto: solo desde celular del admin). Comandos `/bot off|on|status`. | ✅ verificado JSON | 🟢 |
| 3 | `fromMe=true` persistido como `type:ai` → LLM lee mensajes humanos como propios | 2026-05-09 12:52 | LangChain auto-serializa solo `content` y `tool_calls`. Los `additional_kwargs.source` quedan invisibles al modelo. | Prefijar `content` con `[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria desde el WhatsApp del consultorio. NO es output tuyo...]:` explícito. | ✅ verificado script | 🟢 |
| 4 | Router LM clasifica sin contexto → urgencia va a Sub-Agent General | 2026-05-09 13:02 | Nodo `Router - Clasificar Intent` no estaba conectado a `Postgres Chat Memory.ai_memory`. Veía solo el último mensaje. | Conexión `Postgres Chat Memory.ai_memory → Router - Clasificar Intent` agregada. | ✅ verificado JSON | 🟢 |
| 5 | Recordatorios duplicados (3x) a pacientes del martes | 2026-05-08/09/10 | Cron diario `0 13 * * *` + `addBusinessDays(hoy, 2)` que saltea weekends. Vie/sáb/dom convergen al martes. | Cron `0 13 * * 1-5` (solo lun-vie). | ✅ validable martes 19/5 | 🟢 |
| 6 | Carmen Agostini paciente duplicada en Dentalink (`+543886869400` sin 9, bot buscó con 9, creó id=609) | ~2026-04 | Búsqueda Dentalink no normalizaba formato. Bot tiró 11 mensajes en loop "no figura su turno". | Tool `buscar_paciente_dentalink` busca 5 variantes (con/sin 9, con/sin +) + apellido como fallback. Cleanup id=609 sigue pendiente. | 🟡 lógica fix, cleanup DB pendiente | 🟡 |
| 7 | Primer batch recordatorios (6 envíos) falló todo | ~2026-04 | Lógica heredada quitaba "9" después de 54. Funcionaba para Buenos Aires (Evolution acepta sin 9), fallaba para Jujuy 388 y Córdoba 351. | Mantener "9" + testear con números del interior. | ✅ corre lun-vie | 🟢 |
| 8 | NOTA INTERNA del recordatorio sin `id_paciente` → causa raíz caso Carmen | ~2026-04 | NOTA INTERNA solo guardaba `cita_id`. Al responder, bot tenía que rebuscar paciente por celular (campo derivado, heterogéneo). | Workflow Recordatorios ahora persiste `id_paciente` en `additional_kwargs.id_paciente`. | ✅ verificado en code | 🟢 |
| 9 | Memoria LangChain rota 29/4 al 2/5 | 2026-04-29 a 2026-05-02 | Wrapper `{type, data:{content}}` (LangChain v0.2) vs FLAT esperado (v0.3+: `{type, content, additional_kwargs, ...}`). El bot ignoraba rows mal formateadas al hidratar memoria. | Migrar todos los INSERTs a formato flat v0.3+. | ✅ corre desde mayo | 📚 |
| 10 | Cron n8n con offset -2h aparente (recordatorios mandaban 7 AM en vez de 9 AM) | ~2026-04 | Server timezone n8n acumula offset. Para 9 AM Arg hay que poner cron `0 14 * * *` UTC, NO el +3 que dictaría matemáticamente. Estable, no depende de DST. | Documentado: cron Arg = `(hora_arg + 5) UTC`. Actual `0 13 * * 1-5` corresponde a 8 AM Arg... revisar si es 9. | ✅ corre OK | 📚 |
| 11 | Nodo `Typing` pisaba item → `$json.message` vacío en Send → HTTP 400 | ~2026-04 | Nodos intermedios pisan el `$json`. No es transparente. | Referenciar al nodo origen explícitamente: `$('Split en Mensajes').item.json` en vez de `$json`. | ✅ | 📚 |
| 12 | PUT /workflows borraba webhookId silenciosamente → Evolution apuntaba a UUID null | ~2026-04 | n8n acepta PUT sin webhookId. La response no se queja pero el path queda inactivo. | Regla #3 del proyecto: preservar `webhookId: evo-webhook-v2` siempre. Validar en GET post-PUT. | ✅ | 📚 |
| 13 | Evolution API miente: dice "Erro ao enviar mensagem" cuando SÍ se envió | ~2026-04 | Response post-envío tiene formato raro, el nodo lo interpreta como error pero el WhatsApp llegó. | Confirmar con destinatario, no confiar en output del nodo. | ✅ | 📚 |
| 14 | `continueOnFail=true` en nodo Evolution ocultaba que se rompieron 6 envíos | ~2026-04 | Workflow terminó con `status:success` aunque ningún mensaje se mandó. | Inspeccionar output de CADA nodo individual buscando `error` o `PENDING`, no confiar en status global. | ✅ | 📚 |
| 15 | Dentalink PUT `/citas/{id}` para anular tira 400 si mandás `comentario_anulacion` | 2026-04 (cita 7905) | API solo acepta `{id_estado: 1}`. Cualquier otra key → 400 "Parametro X no existe". | Documentado: PUT anular solo `id_estado:1`. Tool `cancelar_turno` ajustada. | ✅ | 📚 |
| 16 | Bot responde "Buenisimo, te esperamos el martes 5 a las 8:40" a un emoji solo ❤️ | ~2026-05 shadow | LLM (gpt-5-mini) no respeta 100% reglas como "no respondas a cierres/emojis". | Pre-filtro determinístico regex (capa antes del LLM): `emoji_only`, `solo_gracias`, etc. | ✅ shadow validado | 🟢 |
| 17 | Rate Limit con `phone=""` bloqueaba el 11vo mensaje **global** (todos los pacientes compartían contador) | 2026-05-09 mañana | `Rate Limit Prep` Code node leía `$json.phone` pero el item había sido pisado por nodos intermedios. Key Redis quedaba `rate:` sin sufijo. | Leer de `$('Webhook - Evolution API').first().json` + Code Eval intermedio + bypass si phone vacío. | ⚠️ sintético OK, sin prod | 🟡 |
| 18 | 20 refs `$json.body.data.*` rotas en `Edit Fields` post-upgrade | 2026-05-09 mañana | Mismo problema que #17: item pisado. | 20 refs reemplazadas a `$('Webhook - Evolution API').first().json.body.data.*`. | ⚠️ sintético OK, sin prod | 🟡 |
| 19 | Bot conversaba con autoresponders externos (Omar Dental, Sil Odonto) | shadow 2026-05-04/09 | Sin pre-filtro de auto-replies. Gasto tokens + memoria sucia + exposición B2B. | Regex en `Pre-filtro Cierre`: `respuesta automatica`, `gracias por comunicarte con`, `a la brevedad`, horarios + días → NO_REPLY. | ✅ shadow + sintético | 🟢 |
| 20 | Onboarding redundante en continuaciones ("Hola, soy la asistente virtual..." mid-flow) | shadow 2026-05-04/09 | Lógica IF "primer mensaje" no preservaba estado mid-flow. Prompts ambiguos. | Regla en los 5 sub-agents: prohibido onboarding si memoria <24h. Excepción: >12h sin interacción + saludo paciente. | ✅ shadow + sintético | 🟢 |
| 21 | "Gracias" disparaba data no solicitada (info pago, horarios) | shadow 2026-05-04/09 | Pre-filtro `solo_gracias` faltaba; `termina_gracias` daba falsos positivos con "a las 9 gracias". | `solo_gracias` match exacto + `termina_gracias` excluye mensajes con números. | ✅ shadow + sintético | 🟢 |
| 22 | Ejemplo "Te esperamos" literal en system prompt de los 5 sub-agents (causa raíz de #1) | detectado 2026-05-09 | Sección "REFERENCIA secretaria REAL" tenía: `"Listo, te queda confirmado para el martes 5 a las 17. Te esperamos."` mientras R22 prohíbe `te esperamos`. Bot copió literal. | R0 anti-conversacional aplicada en los 5 sub-agents (2026-05-12) + Banlist regex tapa post-output. **El ejemplo literal "Te esperamos" sigue en el prompt** — cobertura completa requiere editarlo. | ⚠️ Banlist regex como red de seguridad | ⚠️ |
| 23 | `escalar_a_secretaria` description decía "consultas de precios/presupuestos" → bot escalaba precios al humano | detectado 2026-05-09 | Contradicción: description invitaba a escalar precios; prompt decía "usá precios LITERAL del header". | Description reescrita (270 → 708 chars): aclara cuándo SÍ usar (urgencia, queja, obra social, fuera de 4 funciones) y cuándo NO (precio/horario/dirección/alias = canned). | ⚠️ sin shadow real | 🟡 |
| 24 | 4 tools Dentalink sin `toolDescription` (`cancelar_turno`, `reservar_turno`, `crear_paciente_dentalink`, `ver_profesionales`) | detectado 2026-05-09 | Nodos creados sin specs. LLM adivina params por nombre — funciona en happy path pero rompe en bordes. | Pendiente: redactar descriptions específicas incluyendo idiosincrasias (ej "PUT solo acepta {id_estado:1}"). | ❌ | 🔴 |
| 25 | `[NO_REPLY]` literal persistido como AIMessage en memoria | detectado 2026-05-09 (exec 13142) | LangChain auto-persiste el output del agent. Cuando el agent devuelve `[NO_REPLY]`, queda en memoria. El LLM lo ve en próximos turnos ("yo dije [NO_REPLY] antes?"). | Nodo nuevo `PG - Delete NO_REPLY` (DELETE selectivo post-hoc en la rama `Tiene respuesta? FALSE`). | ⚠️ sin shadow real | 🟡 |
| 26 | `Clear Old Memory` borraba TODO si stale (>3 días) incluyendo NOTA INTERNA del recordatorio | detectado 2026-05-09 | DELETE indiferenciado por `is_stale_session`. Resultado: paciente recibe recordatorio lunes, responde viernes → bot pide DNI desde cero (caso raíz Carmen). | SQL nueva: `DELETE ... WHERE session_id = $1 AND $2::boolean = true AND COALESCE(message::jsonb->'additional_kwargs'->>'source', '') NOT IN ('wa_outbound', 'human_takeover', 'reminder_note')`. Params bound. Plus: `Handle Stale Session` ya no referencia `Supabase - Buscar Paciente` (que fue desconectado). | ⚠️ sin shadow real | 🟡 |
| 27 | RAG `buscar_conocimiento` apuntaba a base contaminada de Nexora (88 rows scrapes marketing, 0 docs clínicos) | detectado 2026-05-09 | Credencial Supabase `Thn3jgEbbxPFD7d9` apunta al proyecto Nexora research. Tabla `knowledge_base` = scrapes YouTube/Twitter de competidores. | Desconectados: `buscar_conocimiento` (vectorStoreSupabase) + `Embeddings OpenAI` (solo se usaba para alimentar al RAG). | ✅ verificado | 🟢 |
| 28 | Vector store dim mismatch: OpenAI 1536-dim vs tabla 384-dim → RPC `match_knowledge` 400 silencioso siempre | detectado 2026-05-09 | Embeddings OpenAI default = 1536; tabla creada para SentenceTransformers (384). | Cubierto por #27 (nodo desconectado). | ✅ | 🟢 |
| 29 | Tablas Supabase `pacientes` y `conversaciones` NO EXISTEN | detectado 2026-05-09 + verificado 2026-05-11 via service_role | Credencial apunta a proyecto Nexora (research), no a uno clínico. Las tablas nunca fueron creadas. `Supabase - Buscar Paciente` retornaba 404 silencioso siempre. | Desconectados 5 nodos: `Supabase - Buscar Paciente`, `Existe Paciente?`, `Supabase - Crear Paciente`, `Supabase - Guardar Msg Usuario`, `Supabase - Guardar Msg Asistente`. Reconexión: `Bot Activo? FALSE → Check Session Age` directo. Lógica lead vs paciente la maneja el sub-agent Agendar via Dentalink tools. | ✅ verificado | 🟢 |
| 30 | `n8n_chat_histories` sin índice por `session_id` | detectado 2026-05-09 | Migration runtime solo agrega columna `created_at`, no indexa. | Pendiente: `CREATE INDEX idx_chat_histories_session_id ON n8n_chat_histories(session_id);` Requiere acceso al Postgres del n8n. | ❌ | 🔴 |
| 31 | Normalización `session_id` no maneja variantes (`+5493...`, `@lid`) | potencial | `Edit Fields` hace `phone.replace('@s.whatsapp.net','')`. No quita `+` ni `@lid` ni otros formatos. | Pendiente: `phone.replace(/[^0-9]/g, '')`. | ❌ no observado en prod | 🔴 |

---

## Bugs NO trackeados (pendientes de auditar)

Estos NO están en la tabla porque no fueron reportados como bugs sino que pueden aparecer cuando el v6 se prenda en shadow:

- **fromMe filter con phones desde Chatwoot**: si el agente humano usa Chatwoot, también dispara `fromMe=true` (mismo path via Evolution). El nuevo flow CW Search → Set Label aplicaría label `humano` redundantemente. Inocuo pero verificar.
- **Banlist gap `la esperamos` / `le esperamos`**: descubierto el 2026-05-12 en el batch sintético G8. El bot devolvió "queda confirmado. **La esperamos** en Balcarce 37" y Banlist no lo bloqueó. Hay que ampliar el regex.
- **R0 demasiado agresivo en saludos cold**: tests E2/E3/E5 cayeron en `[NO_REPLY]` cuando deberían dar saludo + invitación. R0 dice "si dudás escalá", ataja de más.

Ambos se resuelven en la próxima iteración antes del shadow.
