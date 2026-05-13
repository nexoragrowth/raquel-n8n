# Stack técnico - Bot Dra. Raquel

## Skills técnicas relevantes

- n8n (workflow orchestration, self-hosted)
- LangChain (sub-agents, memoria Postgres Chat Memory)
- Evolution API (WhatsApp Business non-oficial)
- Dentalink (API REST gestión médica)
- Supabase (Postgres + Vector Store + Auth, proyecto `nexoragrowth` compartido)
- Redis (buffer, kill-switch, rate limit, dentalink:status)
- Postgres (`n8n_chat_histories` para memoria LangChain v0.3 flat)
- Chatwoot (UI agente humano, label `humano` como kill-switch parcial)
- OpenAI (gpt-5-mini para todos los LLM nodes; Whisper-1 para audio; gpt-4o para vision — éste último a desconectar en refactor)
- Python (scripts de deploy/audit/test)

## Constraints

- Webhook path en producción: `evolution-v2` con `webhookId: evo-webhook-v2`. Si se pierde el `webhookId` al hacer PUT, Evolution apunta a UUID null y rompe todo.
- API n8n PUT solo acepta keys: `name, nodes, connections, settings, staticData`. Settings filtrado a `executionOrder, callerPolicy, saveExecutionProgress, saveManualExecutions, saveDataErrorExecution, saveDataSuccessExecution, executionTimeout, errorWorkflow, timezone, callerIds`.
- Cron server n8n tiene offset +2h aparente: para 9 AM Arg cron `0 14 * * *` (no `0 12 * * *`).
- WhatsApp Argentina formato JID: `549XXXXXXXXXX@s.whatsapp.net`. El `9` es OBLIGATORIO para móviles del interior (Jujuy 388 falla sin `9`). NUNCA quitarlo al normalizar.
- LangChain Postgres Chat Memory v0.3+ usa formato FLAT en `n8n_chat_histories.message`:
  `{"type":"ai","content":"...","additional_kwargs":{},"response_metadata":{},"tool_calls":[],"invalid_tool_calls":[]}`
  NO usar wrapper `{type, data:{content}}` (formato viejo, LangChain lo ignora silentemente).
- Dentalink API:
  - No permite filtrar `id_paciente` en `/sucursales/{id}/citas` → usar `/pacientes/{id_paciente}/citas`
  - No permite `DELETE /pacientes/{id}` (HTTP 405)
  - `PUT /citas/{id}` para anular: SOLO acepta `{"id_estado":1}`. Cualquier param extra → 400
  - Campo `fecha` en responses viene `DD/MM/YYYY` (no ISO)
  - IDs hardcoded en v6: `id_dentista=1, id_sucursal=1, id_sillon=1` (parametrizar futuro)
  - Estados de cita relevantes: 1=Anulado, 2=Atendido, 7=No confirmado (default), 14=Cambio fecha, 15=Notificado WA, 18="Confirmado por whatsapp " (con espacio al final, ojo)
- Evolution node `Enviar Mensaje` tiene `continueOnFail:true` → workflow termina success aunque falle envío. SIEMPRE inspeccionar output del nodo Evolution buscando `error`.
- Si insertás un nodo entre `Split en Mensajes` y `Evolution API - Enviar Mensaje`, ese nodo puede pisar `$json.message` y `$json.remoteJid` → 400 "instance requires property number/text". Fix: referenciar al nodo origen con `$('Split en Mensajes').item.json.message`.

## Exclusions (NO usar aunque sean populares)

- **RAG abierto con LLM creativo**: el `buscar_conocimiento` actual apunta a base contaminada y dim mismatch, pero además el patrón en sí es overkill para clínica chica. Info clínica del bot vive hardcoded en el system prompt (precios, horarios, alias, dirección, política cancelación).
- **OpenAI Vision API en producción**: la auditoría confirmó que clasificar fotos dentales / comprobantes es ruido. Multimedia escala automáticamente sin procesar.
- **Whisper para audio**: idem. Audio escala. La doctora escucha si quiere.
- **Agent type complejo con tools + memoria + razonamiento** para tareas simples como clasificación. Usar `lmChatOpenAi` directo con `response_format: json_schema` cuando se necesita output estructurado.
- **gpt-4 / gpt-5 (full)** en producción. gpt-5-mini es suficiente y barato para todos los nodes excepto casos puntuales validados.
- **continueOnFail en nodos críticos** sin alerta downstream. Si una llamada a Dentalink/Evolution falla, hay que verlo, no esconder.
- **Sub-agents múltiples (5+) para scope cerrado** (clínica chica con 4 funciones). Multi-agent agrega complejidad que no necesitás. Mono-agent (o supervisor + 2 sub-agents max) es lo correcto.
- **`type:"ai"` para mensajes humanos en memoria**. Aunque LangChain lo acepte, el LLM lo lee como output propio y se confunde. Si hay que persistir un mensaje humano (Iri/Dra), prefijar con tag explícito `[ATENCION HUMANA - ...]:` para que el modelo lo distinga.
- **Auto Reactivar Bot 1h** pisando el kill-switch admin. El `/bot off` admin tiene prioridad absoluta; Auto Reactivar solo debe sacar label `humano` aplicado por Human Takeover.
