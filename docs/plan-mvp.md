# Plan MVP - Refactor del bot v6 → v7

> Última actualización: 2026-05-11

## Principio rector

Bot **simple y cerrado**. NO creativo. NO conversa. Cada decisión tiene 2 capas de defensa (prompt + gate determinístico). Cualquier cosa que el bot pueda manejar con certeza → ejecuta. Todo lo demás → escala al grupo.

## Arquitectura propuesta (Supervisor pattern minimalista)

```
Webhook Evolution
    ↓
[Pre-filtro regex] casos obvios (cero LLM)
    ├─ fromMe + no es admin → silence flag Redis + persist con tag + return
    ├─ /bot off|on (admin whitelisted, fromMe=false) → kill-switch
    ├─ multimedia sin texto → marca tipo + escala
    ├─ cierres ("gracias", emoji solo, ok seco) → silencio
    └─ default → sigue
    ↓
[Buffer Redis] 8s para juntar mensajes seguidos
    ↓
[Check label humano Chatwoot] + [Check silence flag Redis]
    ↓ (si humano o silenciado → return)
[Supervisor LLM] (lmChatOpenAi, gpt-5-mini, T=0, JSON output forzado)
    System prompt: ~800 chars
      - Rol: clasificar intent + acotar contexto
      - Sub-agentes disponibles: AGENDAR, CONFIRMAR, CANCELAR, INFO, URGENCIA, COMPROBANTE, OTRO
      - 10-15 few-shot examples (incluidos los del incidente Mariela)
      - REGLA: ante duda, devolver OTRO (escalación safe)
    Output (JSON forzado vía response_format):
      { intent: ENUM, razon: string, acotacion_para_subagent: string }
    ↓
[Validador del output supervisor] (Code node)
    - Parse JSON. Si malformado → fuerza OTRO.
    - Validar intent ∈ enum. Si no → fuerza OTRO.
    ↓
[Switch determinístico sobre intent]
    ├─ AGENDAR    → Sub-Agent Agendar (LLM con tools Dentalink)
    ├─ CONFIRMAR  → Sub-Agent Confirmar/Cancelar (LLM con tools)
    ├─ CANCELAR   → Sub-Agent Confirmar/Cancelar (LLM con tools)
    ├─ INFO       → canned hardcoded (NO LLM)
    ├─ URGENCIA   → canned + notifica al grupo (NO LLM)
    ├─ COMPROBANTE → canned + notifica al grupo (NO LLM)
    └─ OTRO       → canned escalación + grupo (NO LLM)
    ↓
[Banlist Validator] regex post-output (22 patrones, ya implementado)
    Si match → reescribe a canned escalación
    ↓
[Formatter] (corto, ~500 chars) → Split en Mensajes → Evolution Send
    + persistencia Postgres
    + notificación al grupo si escalate_to_human:true
```

## Eliminaciones del v6

| Componente actual | Acción | Por qué |
|---|---|---|
| Sub-Agent General (23k chars) | **Eliminar** | Catch-all que improvisa. Reemplaza el "OTRO" canned. |
| Sub-Agent Urgencia (19k chars) | **Eliminar** | Reemplaza el "URGENCIA" canned + grupo. NO le damos LLM a las urgencias. |
| Router LLM (4k chars + agent type) | **Reemplazar** por Supervisor minimalista (~800 chars + lmChat directo) | El agent type actual con tools y memoria es caja negra. |
| Vision OpenAI | **Eliminar** del flow | Multimedia escala automáticamente. |
| Whisper (audio) | **Eliminar** | Audio escala. |
| `buscar_conocimiento` RAG | **Desconectar** | Apunta a tabla `knowledge_base` del proyecto Nexora compartido (88 rows contaminadas). Dim mismatch silencioso (1536 vs 384). Info clínica hardcoded en system prompt. |
| 4 nodos Supabase pacientes/conversaciones | **Revisar** | Las tablas SÍ existen (verificado por screenshot), pero la lógica "Existe paciente?" → Crear corre sobre Supabase compartido con otros bots. Decisión pendiente. |

## Mantenimientos del v6

- Buffer Redis (patrón Twilio, key_id por mensaje)
- Memoria Postgres `n8n_chat_histories` (formato LangChain v0.3 flat)
- Kill-switch admin (`/bot off|on|status`) — ya estricto post-fix 2026-05-09
- Banlist Validator (22 patrones regex) — ya implementado 2026-05-09
- Pre-filtro Cierre (gracias / emoji / ok seco) — ya existe
- Rate limit Redis (10/15min por phone)
- Health Check Dentalink + Redis flag

## Capas de defensa (defensa en profundidad)

1. **Pre-filtro regex** — captura casos obvios sin LLM.
2. **Silence flag Redis** — bot calla 2h en chats donde un humano ya respondió.
3. **Kill-switch admin** — `/bot off` apaga global; `/bot on` reanuda. Confirmación visible.
4. **Supervisor con JSON forzado + validador** — clasifica con output enumerado; cualquier salida fuera del enum → OTRO (escala).
5. **Switch determinístico** sobre intent del supervisor — la ruta no es probabilística.
6. **Sub-agents endurecidos** — prompts cortos, tools cerradas, system prompt sin ejemplos contaminantes.
7. **Banlist Validator regex** — 22 patrones que el bot no puede mandar. Última línea de defensa post-LLM.
8. **Continuidad humana** — toda escalación + cualquier `fromMe` no-bot aplica label humano en Chatwoot + notifica al grupo.

## Tests sintéticos requeridos antes de shadow

1. Mariela completa (5 mensajes reales del incidente) → cada uno clasifica URGENCIA → canned + grupo. Banlist no se gatilla porque el output ya es canned.
2. Agendar happy path → Sub-Agent Agendar llama tools Dentalink → confirma.
3. Confirmar post-recordatorio → identifica NOTA INTERNA → llama `confirmar_turno(id_estado=18)`.
4. Comprobante de pago → COMPROBANTE → canned + grupo.
5. "Cuánto sale la consulta?" → INFO → canned con precio.
6. "Gracias" / 👍 / "Ok" → silencio.
7. Foto dental sin caption → OTRO → canned + grupo.
8. fromMe desde app del consultorio → silence flag activo → bot mudo en ese chat 2h.
9. `/bot off` desde phone admin → confirmación visible.
10. Tests adversariales: prompt injection en el mensaje del paciente, intento de hacer al bot dar diagnóstico, intento de hacer al bot invitar a la clínica.

## Shadow → cutover

- 24-48h en shadow: workflow procesa eventos pero `Evolution API - Enviar Mensaje` deshabilitado.
- Comparar respuestas del bot vs respuestas reales de Irina.
- Lucas + doctora revisan logs.
- Si OK → habilitar Send + path productivo + supervisión 2-3h en vivo.

## Pendientes operativos

- [ ] Contactar a Mariela post-incidente (responsabilidad de la doctora, Lucas a confirmar).
- [ ] Limpiar paciente duplicado Carmen Agostini (id=609 en Dentalink, generado por bug pre-fix multi-format).
- [ ] Decidir destino futuro del `knowledge_base` (proyecto Supabase nuevo dedicado o mantener hardcoded).
- [ ] Considerar tabla `paciente_perfil` en Supabase con `preferencia_horario`, etc. para futuras versiones.
