# Roadmap de refactor y mejora — 2026-09-06

Pedido de Lucas: "seguí fijándote qué podemos refactorizar/mejorar y que quede bien pro funcionando;
la idea es armar un sistema completo incluyendo nuestro propio Dentalink". Este doc lista lo que
vimos con evidencia en las sesiones del 2–6/9 (mapeo completo del v6 en `docs/triaje-fase2-analisis/`),
ordenado por valor/riesgo. Cada ítem dice si toca el v6 (sensible) o no.

## A. Lo que ya quedó (para no perderlo de vista)
- Triaje de urgencias con video (piloto), Vigía, `check_triaje.py`, fix del auto-silencio post-escalación,
  panel: envío/toggle/imágenes/autor/alias/orden, Inbox Live, switch bot/humano instantáneo.

## B. Refactors con más valor (orden sugerido)

### B1. Un solo registro de mensajes (matar el Logger de 5 min) — NO toca la lógica del bot
**Hoy**: el panel fusiona 3 fuentes (`conversaciones` copiada por el Logger cada 5 min, `n8n_chat_histories`
en vivo, `mensajes_entrantes_live`) con dedupes por timestamp/texto. Cada fuente tiene un shape distinto; de
ahí salieron el bug del `order ASC`, el "hay que hacer F5", el indicador de modo humano con lag, y la
metadata que se pierde (autor, adjuntos) cuando el Logger copia.
**Propuesta**: una tabla canónica `mensajes` que escriben TODOS los emisores en el momento del hecho:
entrante (ya lo hace Inbox Live), saliente del bot (un nodo después de `Evolution API - Enviar Mensaje` y
en los envíos del triaje), staff desde el celular (rama fromMe), staff desde el panel (webhook),
recordatorios. Columnas: id, telefono, direccion(in/out), autor(bot|staff:<user>|paciente), texto,
media_url/tipo, wa_message_id, estado_envio, created_at. El panel lee UNA tabla; el Logger se retira;
`n8n_chat_histories` queda solo como memoria del LLM. **Esfuerzo**: 1–2 días. **Riesgo**: medio (varios
nodos nuevos en el v6, todos "rama muerta"). **Valor**: alto — es la base de cualquier panel serio y del
sistema propio.

### B2. Higiene del v6 (nodos muertos y trampas conocidas) — toca el v6, bajo riesgo si va por partes
- Nodos huérfanos: `Es primer mensaje?`, `Delay Humano`, `Sub-Agent Cancelar`, `Sub-Agent Urgencia`
  (desde el 4/9). Borrarlos con backup.
- `Banlist Shadow` lee campos que el Banlist no produce (siempre ALLOW) y gasta 1 llamada gpt-5-nano por
  respuesta: retirarlo o arreglar el contrato.
- `Banlist Validator`: `\b` sin flag `u` no cierra después de tildes ("Aplicá cera" pasa, "Aplica cera"
  bloquea); no cubre formas de usted (Aplique/Guarde/Tome/Saque). Mismo fix que `triaje/gate_red_flags.js`.
- `Existe paciente?` sin `continueOnFail` → Chatwoot caído = bot mudo para todos. `Re-check Humano` sin
  `onError`. Tokens de Chatwoot hardcodeados en 3 Code nodes → credencial de n8n.
- `Buffer: Wait 10s` espera 22 s (decisión de producto: bajarlo a ~12 s haría al bot más ágil; riesgo:
  mensajes en 2 burbujas como 2 turnos).
- Gate humano: mira TODAS las conversaciones de Chatwoot (incl. resueltas) y Auto Reactivar solo limpia
  las abiertas → un `humano` viejo silencia para siempre (pasó el 5/9). Fix: solo `status='open'`.
- `dentalink:status=down` apaga TODO el bot, urgencias incluidas.

### B3. Comportamiento como datos, no prompts (seguir el camino que ya funciona)
Precio/horarios (21/8) y los textos del triaje (4/9) ya viven en tablas. Candidatos siguientes: canned de
Sub-Agent General (alias/CBU, dirección, obra social, cuota mensual $70.000 hardcodeada), la lista de
admins del kill-switch, el JID del grupo de escalaciones. Editables desde el panel con el mismo guard
del Banlist que ya tiene `/agente`. Reduce PUTs al v6 a casi cero.

### B4. Panel: cosas que faltan para "WhatsApp Web de verdad"
- Imágenes ENTRANTES del paciente (hoy se ven como "[IMAGEN] TIPO: … DESCRIPCION: …"): guardar el
  archivo (llega en base64 al webhook) en Storage y mostrarlo. Encaja natural en B1 (media_url).
- Audios entrantes: hoy se transcriben; mostrar transcripción + player.
- Realtime real (Supabase Realtime / SSE) en vez de polling 1,5 s: sirve cuando haya >10 usuarios
  concurrentes; hoy no es cuello de botella.
- `/aprendizaje`: carve-out `[TRIAJE VIDEO]` para que un caso resuelto con video no cuente como "Asiri no
  supo" (3 líneas en `lib/escalaciones.ts` + dashboard + reportero), y entonces activar `aviso_pasivo`.
- Reportero semanal: sección de urgencias desde `triaje_urgencias_log` (pedido de Raquel del 15/8).

### B5. Tests y cobertura que faltan
- E2E del cierre del triaje ("listo gracias ya me puse la cera") y del bug de Confirmar + alias mergeado
  (backlog P1 desde el 2/9, sin aplicar).
- `tests/test_e2e_bateria.py` usa el shape viejo del webhook (Evolution clásica): migrar al shape de
  Evolution GO (`tests/test_e2e_triaje.py` ya lo tiene).
- Sincronizar `prompts/v6_partials/` con los prompts vivos (drift) o dejar de mantenerlos y tratar el
  editor `/agente` + `agente_prompt_log` como fuente de verdad.

## C. "Nuestro propio Dentalink" — qué implica y por dónde empezar
Lo que el bot usa hoy de Dentalink (`buscar_horarios`, `reservar_turno`, `cancelar_turno`,
`buscar_paciente_dentalink`, `crear_paciente_dentalink`, `ver_turnos_paciente`, `confirmar_turno`) y lo que
usa el panel (`/citas`, cards de turno, nombre de ficha) es una API chica: pacientes, profesionales,
agenda con slots, citas con estado. Un sistema propio = esas 4 entidades en Supabase + reglas de agenda
(horarios de la Dra. por día, duración por tratamiento, feriados, bloqueos) + UI en el panel.
Camino sugerido, sin big-bang:
1. **Modelo propio en Supabase** (`profesionales`, `pacientes` ya existe, `agenda_reglas`, `citas`) espejando
   lo que el bot ya consume, con los mismos nombres de campos que devuelven las tools de hoy.
2. **Capa de adaptador**: las tools del v6 pegan a un endpoint propio (n8n o Next API) que hoy delega a
   Dentalink y mañana lee de las tablas propias. Cero cambios de prompt.
3. **Doble escritura** un tiempo (Dentalink + propio) para comparar; después cutover con feature flag.
4. Recordatorios y triaje ya son independientes de Dentalink salvo por la fuente de citas.
**Riesgo principal**: la agenda es el corazón del consultorio; migrar requiere que Raquel/Irina trabajen
en el sistema propio (no en Dentalink) — decisión de negocio, no técnica.

## D. Reglas de proceso que sostienen todo esto
`check_triaje.py` antes de cada PUT; Vigía activo; `limpiar_numero_demo.py` después de cada prueba real;
diff + backup antes de cualquier cambio al v6; y ningún "funciona" sin E2E del camino completo.
