# v7 — Asiri como agente con herramientas (diseño, versión 2)

**Fecha:** 2026-10-06 · **Estado:** diseño revisado (v1 criticada por 5 revisores independientes: 43 observaciones validadas, 4 críticas; todas incorporadas acá) · nada construido todavía · **Reemplaza a:** el v6 (Router + 5 sub-agentes + sub-workflow de cambios)

## 1. Por qué (el problema de arquitectura, en una frase)

Hoy la conversación la lleva un **clasificador por mensaje** (Router LLM + reglas regex) que reparte cada mensaje entre piezas que no comparten capacidades: el flujo de cambios **ejecuta pero no conversa** (árbol if/else que adivina el estado buscando frases en el último mensaje del bot) y el agente de agenda **conversa pero no puede cambiar un turno** (no tiene herramienta de anular). Todo mensaje que no encaja en un patrón cae en el lugar equivocado, en una respuesta enlatada o en "le paso a la secretaria". El caso Dana (05/10) lo mostró entero, y cada parche del 05/10 fue agregar reglas de ruteo: eso es el *whack-a-mole*.

Dato que lo cuantifica: **en 90 días el bot completó un solo cambio de turno** (14/9, verificado en la agenda). La escritura en la agenda funciona; lo que falla es la conversación alrededor.

## 2. Principio de diseño

> **Un solo LLM conversa (Asiri). Todo lo que toca la agenda, la memoria operativa o a la clínica es código, y el código no confía en el LLM.**

- Asiri es dueño del chat: ve la memoria, entiende el contexto, decide qué herramienta llamar y redacta la respuesta. Lo que redacta libre es lo conversacional; **el bloque de horarios y el read-back de una escritura los arma el código y Asiri los pega textuales** (pedido escrito de la Dra. del 07/09: ni preguntar franja ni reescribir el bloque).
- Las herramientas son **sub-workflows determinísticos** (Code + HTTP), no otros agentes LLM. La v1 proponía sub-agentes LLM anidados como en el patrón "parent agent + specialist agents"; la revisión lo descartó con tres razones concretas: (a) un LLM intermedio vuelve a elegir `paciente_id` y `cita_id` y a re-interpretar fechas que Asiri ya entendió, reabriendo los bugs del 05/10; (b) el `ok` que recibiría Asiri lo escribiría un LLM, no la agenda; (c) dos loops anidados son ~8 llamadas y 20-30 s en el caso más frecuente (confirmar un recordatorio). Sub-agentes LLM solo si el examen (§8) demuestra que Asiri plano no alcanza.
- **Las herramientas de escritura no reciben de Asiri ningún identificador**: `paciente_id` sale de Redis (lo escribe el código de identificación), `cita_id` tiene que estar entre los turnos que `ver_turnos` cargó en esta conversación, y un horario solo es escribible si `buscar_horarios` lo ofreció en esta sesión. Asiri aporta solo `fecha`, `hora` y, para cancelar, cuál turno (por fecha).
- Un cambio es **una sola operación atómica** (reserva → verifica → anula → verifica), consumida una sola vez, con timeout, y si la reserva falla el turno viejo queda intacto.
- Las defensas que nacieron del incidente Mariela (09/05) **se conservan y se refuerzan**: pre-filtros determinísticos, triaje de urgencias, banlist (reescrito para el trato de "usted", §5).
- **Escalar es la excepción**: a una persona solo si el paciente la pidió, hay queja, pide baja de datos o es urgencia (y urgencia va al triaje, no a silencio). Un error de herramienta se maneja, no se deriva.

## 3. La arquitectura

```
WhatsApp (Evolution) ──► ENTRADA DETERMINÍSTICA (se conserva del v6)
                          validador · kill-switch /bot · rate limit (sin backdoor) · fromMe → modo humano (vuelve al bot 1 h después del último mensaje de una persona) · duplicados
                          multimedia (audio→texto, imagen→marcador) · buffer Redis 22 s + lock por paciente · "escribiendo…" apenas cierra el buffer
                          modo humano (flag + 1 h) · URGENCIAS: regex esUrgenciaFuerte + red flags → flujo de triaje actual (videos), NO Asiri
                          respuestas fijas (menú / anuncio) → salen directo
                          IDENTIFICACIÓN por código: ficha(s) del celular → Redis `ficha:{tel}` (lista + elegida) · recordatorios abiertos → contexto
                                │
                                ▼
                   ┌────────────────────────────────────────────────────────────┐
                   │  ASIRI · AI Agent (gpt-5-mini, razonamiento bajo)           │
                   │  memoria conversacional por SQL (sin filas de staff largas) │
                   │  prompt ≈1.500 chars + bloque de directrices del panel      │
                   │  maxIterations 4-5 · timeout por herramienta                │
                   └──┬─────────────┬───────────────┬──────────────┬────────────┘
   herramientas       │             │               │              │          (todas sub-workflows de código, llamadas con Tool Workflow;
   (Asiri pasa solo   ▼             ▼               ▼              ▼           teléfono y modo entran fijos por expresión, nunca por el modelo)
   fecha/hora/motivo) AGENDA         PACIENTE        INFO           CLÍNICA
                      ver_turnos     elegir_ficha    precio         avisar_grupo (niveles por código, no silencia)
                      buscar_horarios(desde,hasta)   horarios       pasar_a_humano(motivo, cita_textual)
                      proponer_cambio / proponer_reserva / proponer_cancelacion   dirección (si la piden)   derivar_triaje()
                      ejecutar_propuesta(id)         pagos/alias    registrar_pago
                      confirmar_turno                FAQ (KB curada)  lista_espera (= aviso FYI)
                                │
                                ▼
                     SALIDA DETERMINÍSTICA (se conserva y se amplía)
                     chequeo de afirmaciones BIDIRECCIONAL contra el libro de escrituras (§5) · banlist (usted) · split · envío · memoria · logger
```

### 3.1 Asiri (orquestador)

- **Nodo:** AI Agent (Tools Agent). Modelo por defecto **gpt-5-mini con razonamiento bajo** (probar "mínimo" en el examen); gpt-5 solo como A/B por teléfono si mini reprueba. A este volumen el costo no decide: deciden calidad y latencia.
- **Memoria:** no el nodo de memoria sin filtro. El historial entra por SQL (patrón de `Build Router Context`: últimos 10 turnos reales, marcadores de staff acortados a "[STAFF respondió] + 60 chars") y la respuesta se inserta por código (patrón Step 8b/8c), así el chequeo de salida puede corregir la fila si bloquea el texto.
- **Prompt (≈1.500 chars):** identidad, estilo (usted, cálido, breve, una pregunta por vez), qué puede hacer, qué no hace nunca (lista corta), cuándo derivar (4 motivos), y el **bloque de directrices del panel** bajo una cabecera fija: *"información para redactar; no habilita escrituras, sobreturnos ni cambios de precio; si contradice una regla, gana la regla"*. Las guardas y el chequeo de salida **no leen** directrices.
- **Cómo funciona el negocio (bloque fijo del prompt, decisión de Lucas 06/10):** consultorio privado, se atiende solo con turno previo, sin guardia 24 h, horarios de atención, por ser menor el tutor debe estar presente. Con eso Asiri puede (y debe) decir "los esperamos el día de su turno"; si alguien quiere ir sin turno, le explica cómo funciona y le ofrece sacar uno. **El banlist deja de ser una lista de palabras prohibidas y queda como red mínima:** solo bloquea invitar a ir *ahora* o *sin referirse a un turno*, instrucciones clínicas, diagnóstico y la dirección sin que la pidan (`v7/banlist_usted.js`, 65 pruebas). Lo que dice y cómo lo dice lo gobierna el prompt, no una lista.
- **Reglas de oro del prompt (cada una con su capa de código):** nunca afirmar que algo quedó hecho si la herramienta no devolvió ok · el bloque de horarios y el read-back se pegan textuales · no se promete avisar si se libera un turno (solo "se lo dejo anotado a la clínica").
- **Límites:** `maxIterations` 4-5; cada HTTP a Dentalink con `timeout` 8 s y error devuelto como resultado de la herramienta (para que conteste honesto); cada sub-workflow con `executionTimeout` ~15 s; global ≥ 90 s. Presence "escribiendo…" se dispara apenas el buffer cierra y otra vez antes del envío. Objetivo: **< 10 s de pipeline después del buffer** (p95 medido por tramo en sombra).

### 3.2 AGENDA (sub-workflow de código, el único que toca Dentalink)

| herramienta | qué hace | guardas por código |
|---|---|---|
| `ver_turnos()` | turnos vigentes de **todas** las fichas del celular, con nombre; los deja en Redis `turnos_vistos:{tel}` | — |
| `buscar_horarios(desde?, hasta?)` | el bloque 2 de mañana + 2 de tarde (reusa `Sub-WF - Buscar Horarios Validado`); **registra los horarios ofrecidos en `ofertas:{tel}`** (TTL 2 h) y cuenta lotes en `lotes:{tel}` | si ya hay ofertas vigentes y el rango no cambia, devuelve lo ofrecido sin ir a Dentalink · **límite de 2 lotes por código** (regla de la Dra. del 07/09; el tercero/"pedir preferencia" solo con OK escrito de ella) · timeout 8 s por GET |
| `proponer_cambio(fecha, hora, fecha_turno_viejo?)` | valida y guarda una **propuesta** (`propuesta:{tel}`, TTL 30 min, con `exec_id`); devuelve el `readback_text` **armado por código** (con el nombre del paciente si el celular tiene varias fichas) | ficha elegida (§3.3) · cita vieja en `turnos_vistos` y de esa ficha · horario en `ofertas:{tel}` (**no** "libre ahora": eso reabre el horario alucinado) · cita vieja a **menos de 48 h** → no se propone, se avisa [ACCIÓN] (modo alternativo lo decide la Dra. antes del piloto) |
| `proponer_reserva(fecha, hora, tipo?)` | idem para turno nuevo | rechaza si la ficha tiene cualquier turno futuro vigente, salvo `tipo='sumar'` con read-back "además de su turno del X" |
| `proponer_cancelacion(fecha_turno)` | idem para anular | cita en `turnos_vistos` · regla 48 h |
| `ejecutar_propuesta(id)` | **atómico**: consume la propuesta una sola vez (`SET NX` / `UPDATE … WHERE estado='pendiente' RETURNING`), re-GET de la cita vieja (si cambió → aborta sin tocar nada), POST reserva → verifica `id_estado` → PUT anula → verifica; devuelve `{ok, parcial, motivo, nueva_cita, vieja_anulada}`; **escribe el libro `escrituras:{tel}:{exec}`** con la respuesta cruda de Dentalink y el `readback_text`; **avisa al grupo desde el código** (FYI, con cita vieja → nueva) | rechaza si `propuesta.exec_id` es la ejecución actual (el paciente tiene que haber visto el read-back) o si la salida no marcó `enviada=true` · `onError: continueErrorOutput` en cada HTTP: siempre devuelve JSON, nunca se cuelga |
| `confirmar_turno()` | resuelve la cita por código: intersección de `recordatorios_enviados` abiertos del celular con `ver_turnos`; si hay más de una, devuelve la lista (Asiri pregunta); id_estado 18 + marca el recordatorio | nunca acepta un `cita_id` fuera de esa intersección |
| `lista_espera()` | **no hay tabla**: aviso [FYI] con texto fijo; Asiri solo puede decir "se lo dejo anotado a la clínica" | "le aviso si se libera" entra al banlist |

La cita nueva lleva comentario `Reprogramado por Asiri (WhatsApp), reemplaza cita #id` para que la secretaria lo vea en Dentalink.

### 3.3 PACIENTE (código, antes y durante)

Antes de Asiri, por código: fichas del celular → `ficha:{tel}` = `{fichas:[{id,nombre}], elegida, exec_id}`. Si hay una sola, queda elegida. Si hay varias, la lista va al contexto y Asiri pregunta nombre o DNI; `elegir_ficha(nombre|dni)` la fija por código (vence a los 20 min y se borra si interviene el staff). **Toda escritura exige ficha elegida en esta conversación.** `crear_paciente` queda **apagada** en el piloto (solo con DNI confirmado, más adelante).

### 3.4 INFO (código)

Precio, horarios, dirección (solo si la preguntan), pagos/alias, FAQ: canned por clave desde `knowledge_base` curada (sin el RAG de Nexora). Lo frecuente va estático en el prompt.

### 3.5 CLÍNICA (código)

- `avisar_grupo(texto)` con **nivel fijado por código**: `[ACCIÓN]` (comprobante, urgencia, escritura parcial, pidió persona, regla 48 h), `[FYI]` (cambio/reserva/cancelación ok, lista de espera) y los técnicos (chequeo de afirmaciones, timeouts) **solo a Lucas**. Nunca silencia.
- `pasar_a_humano(motivo, cita_textual)`: motivos `{pidio_persona, queja, baja_de_datos, urgencia}`; la herramienta exige un fragmento **literal** del mensaje del paciente y lo verifica por código (para `pidio_persona`: persona|humano|secretaria|doctora|hablar con|que me llamen); si no verifica, se degrada a aviso sin silenciar y se loguea. `urgencia` no silencia: llama a `derivar_triaje`.
- `derivar_triaje()`: reinyecta el mensaje al flujo de triaje actual (video / pregunta guiada / escalada). Capa 2 de urgencias; la capa 1 es el regex antes de Asiri.
- `registrar_pago()`: fila en `escalaciones_log` ("comprobante recibido de X, verificar") + aviso [ACCIÓN]; dedupe `pago:{tel}` 15 min. No valida montos, no silencia.

Al activar modo humano por cualquier vía (toggle del panel, fromMe, `pasar_a_humano`) el código borra `propuesta:`, `ofertas:`, `lotes:` y `turnos_vistos:` del teléfono (`ficha:` se conserva): el staff interviene y ninguna propuesta vieja puede ejecutarse después.

## 4. Estado explícito en vez de adivinar

| clave Redis | contenido | TTL |
|---|---|---|
| `ficha:{tel}` | fichas del celular + elegida | 2 h (elegida: 20 min) |
| `turnos_vistos:{tel}` | citas que `ver_turnos` mostró | 2 h |
| `ofertas:{tel}` / `lotes:{tel}` | horarios ofrecidos / cuántos lotes | 2 h |
| `propuesta:{tel}` | escritura pendiente de confirmación (+ exec_id, estado) | 30 min |
| `escrituras:{tel}:{exec}` | libro: respuesta cruda de Dentalink + readback_text | 5 min |
| `v7:tel:{tel}` | `vivo` / `sombra` / vacío | sin TTL |

## 5. Salida: chequeo bidireccional + banlist en "usted"

Nodo Code entre `Fallback Output` y `Banlist Validator`, que lee **solo el libro de escrituras** (nunca lo que diga el LLM):

1. Hay escritura ok y el texto **no contiene** el `readback_text` (timeout, "Agent stopped", maxIterations) → se envía el read-back por código + aviso técnico.
2. No hay ok y el texto cierra con fecha+hora ("anoté", "reservé", "le dejo", "ya está", "cambiado", "movido", "listo", "quedó…") → se bloquea y se reemplaza por un mensaje honesto + aviso.
3. Hay ok pero el texto trae **otra** fecha+hora → se bloquea y se manda el read-back por código.
4. Toda fecha+hora que aparezca en un mensaje con horarios tiene que estar en `ofertas:{tel}`; si no, se reemplaza por el bloque crudo.

Cuando el chequeo o el banlist bloquean, se **actualiza la fila de memoria** con el texto que realmente salió. Y antes del piloto se reescribe el **banlist** (hoy en voseo) con las formas de usted e impersonales que Asiri usaría: acérquese / pase por / puede venir / lo atendemos hoy / tome / guarde / traiga / colóquese / enjuáguese / aplíquese…, con límites Unicode; el bloque de directrices del panel pasa por el banlist antes de inyectarse.

## 6. Modelos, latencia, costo: medir antes de decidir

- **Primero** `scripts/medir_latencia_v6.py` (solo lectura de ejecuciones): p50/p95 por intent y por nodo del v6 y del sub-workflow. La línea base de "3 llamadas por mensaje" estaba subestimada; esos números son la base del sombra.
- Orquestador: gpt-5-mini razonamiento bajo (probar mínimo). Sin sub-agentes LLM.
- Objetivo: pipeline < 10 s después del buffer, p95 por tramo (entrada / modelo / Dentalink / envío).

## 7. Construcción y salida, con puertas

0. **Contratos + tests offline al 100 %** (§8a) antes de armar nada en vivo. Decidido ya: Asiri plano con herramientas de código; INFO y PACIENTE por código.
1. **Cerebro v7 como sub-workflow** `{phone, texto, modo} → {texto, herramientas, escrituras}`; en `modo=sombra` **por código**: sin nodo de memoria (contexto por SQL, sesión `v7s:{tel}`), toda herramienta con efecto devuelve `{ok:true, simulado:true, habria_hecho}` sin HTTP y escribe solo en `v7_sombra`; claves Redis con prefijo `v7s:`. Test automático: en sombra, cero requests a Dentalink / Helper.
2. **Sombra retrospectiva** sobre los mensajes de agenda y cambios de 90 días (Dentalink simulado con las citas de cada paciente, formato del fixture de Dana), por webhook manual: elige el modelo y fija umbrales.
3. **Inserción en el v6**: nodo Redis `GET v7:tel:{tel}` reemplaza los arcos que entran al Router: vacío → Router (todo igual); `vivo` → Execute Workflow v7 (espera, continueOnFail) → adaptador `{output, _flow:'v7'}` → `Fallback Output`; `sombra` → Router **y** v7 sin esperar. El triaje y los pre-filtros quedan antes del nodo; `Necesita Formatting?`, `Canned Sidecar` y `Gate Pago Tratamiento` saltan cuando `_flow='v7'`.
4. **Sombra en vivo** (≥ 1 semana) con métricas automáticas v6 vs v7 por función: % con escritura o propuesta, % `pasar_a_humano` vs escalaciones reales, % bloqueos de afirmaciones/banlist, % `[NO_REPLY]`, p95 por tramo, mensajes hasta éxito.
5. **Examen vivo** con la ficha de prueba y el celular de Lucas (§8b).
6. **Piloto por cohortes diarias de recordatorio** (satélite que lee `recordatorios_enviados` del día y hace SADD; semana 1 una cohorte, semana 2 todas), **supervisado por código**: toda escritura real publica al grupo, comentario "bot v7" visible en la cita, `reconciliar_v7.py` cruza Dentalink con `v7_log` cada mañana; `crear_paciente` apagada; `cancelar_turno` solo con propuesta y regla 48 h.
7. **Cutover**; el v6 queda de rollback. **Rollback drenado**: sacar de `v7:tel` solo teléfonos sin propuesta/ofertas vivas y sin mensaje en 30 min (reintentando el resto); la emergencia sigue siendo `/bot off`. Comando admin `/v7 off`.

## 8. Examen de entrada (dos capas; "aprobó" tiene que significar algo)

**a) Offline, sin modelo (repetible):** `tests/harness_tool_v7.mjs` para el sub-workflow de herramientas de escritura: entrada = propuesta + ficha + respuestas simuladas de Dentalink → salida = POST/PUT exactos, orden reservar→anular, `{ok, parcial, motivo}`. Se portan los 24 escenarios de escritura de hoy (`tests/test_flujo_dana_subwf.py`: agenda que rechaza, modelo que alucina, familias, 48 h, propuesta en la misma ejecución, doble ejecución), un fixture del chequeo de afirmaciones (~40 frases × hubo/no hubo ok) y el rechazo de motivos en `pasar_a_humano`.

**b) Con modelo y agenda (resultado, no texto):** `tests/examen_v7.py` con **paciente simulado** (objetivo + persona, gpt-5-mini, tope 8 turnos) para los 25 escenarios de turnos y la charla de Dana, contra un **Dentalink falso** (workflow n8n con webhook que responde con el fixture) y, al final, contra la ficha de prueba real. Aserciones por resultado: cita nueva en un horario que `buscar_horarios` devolvió en esa corrida (según el log de herramientas), vieja con `id_estado=1`, 0 escrituras extra, 0 bloqueos, 0 `pasar_a_humano`, p95 < 10 s, ≤ N mensajes; N=5 repeticiones. **Teardown obligatorio** aunque falle: anular toda cita viva de la ficha de prueba, borrar sus `recordatorios_enviados` y la memoria sembrada; comentario "TEST v7 <escenario>" en cada reserva.

**c) Urgencias y banlist:** los 6 casos reales sin palabra clave (URG-02/26/33/34/37/38) + el caso Mariela tienen que terminar en triaje; ninguna respuesta puede decir venite/acérquese ni dar instrucciones.

## 9. Riesgos y cobertura (actualizada)

| riesgo | cobertura |
|---|---|
| El agente dice que hizo algo que no hizo / se hizo y no lo dice / dice otra fecha | libro de escrituras por código + chequeo bidireccional (§5) + read-back por código |
| Escribe para la ficha o el turno equivocado (familias) | `ficha:{tel}` con lista + elegida, `turnos_vistos`, ids nunca vienen del LLM |
| Horario inventado | solo horarios en `ofertas:{tel}` |
| Ejecuta sin que el paciente haya visto el read-back / ejecuta dos veces | propuesta de otra ejecución + `enviada=true` + consumo atómico + re-GET |
| Doble turno | `proponer_reserva` rechaza con turno vigente salvo `sumar` explícito |
| Venite / instrucciones / dirección | regex de urgencia + triaje + banlist en usted (prompt sin ejemplos contrarios) |
| Deriva o silencia por todo | 4 motivos verificados por código; urgencia → triaje, no silencio |
| Anula el turno de mañana a las 23 h | regla 48 h por código → [ACCIÓN] |
| Latencia | Asiri plano, timeouts por herramienta, presence temprano, p95 por tramo en sombra |
| Sombra que escribe de verdad / contamina memoria | `modo` por código en todas las herramientas; memoria y Redis separadas; test de cero requests |
| Rollback a mitad de conversación | rollback drenado por script; `/bot off` de emergencia |
| Ruido en el grupo | niveles [ACCIÓN]/[FYI]/técnico por código; dedupe de pagos |
| Panel apuntando al workflow equivocado | config por fila (id del workflow principal, nodos editables), muestra qué teléfonos están en v7 |

## 10. Qué se descarta del v6 (y qué no)

- **Se descarta:** Router LLM, Parse Intent y sus regex de continuidad, los 5 sub-agentes y sus prompts, el Formatting Agent, el RAG de Nexora, el Chat Memory sin filtro.
- **Se reusa:** toda la entrada determinística, el triaje con videos, `Sub-WF - Buscar Horarios Validado`, el tramo `6d-prep → POST → IF → PUT → Consolidar` (y `6a`) del sub-workflow de cambios extraído a `v7 Tool - ejecutar_propuesta` (sin sus pasos de memoria ni avisos), el Helper del grupo, el panel y las directrices, los recordatorios (no se tocan).

## 11. Decisiones que necesita Lucas

1. **Asiri plano con herramientas de código** (recomendado por la revisión, decidido en este diseño) vs. sub-agentes LLM como en el patrón de la captura: queda como opción si el examen demuestra que plano no alcanza.
2. **Modelo**: gpt-5-mini bajo por defecto; gpt-5 solo A/B si reprueba.
3. Con la **Dra.**, antes del piloto: regla de 2 lotes (se mantiene por código; ¿tercer lote o pedir preferencia?), **política de 48 h** (¿no anular + aviso, o anular + aviso?), si **Irina entra al grupo** de avisos, y quién trabaja la lista de espera (hasta entonces es solo un aviso).
4. **Mientras se construye el v7**: aplicar o no el parche del 05/10 al sub-workflow de cambios (protege a los pacientes de hoy; su código es la herramienta `ejecutar_propuesta`).

## 12. Qué no se construye hasta pasar las puertas

Sub-agentes LLM, tabla de lista de espera, cron de resúmenes, grupo nuevo de avisos, `crear_paciente` en vivo, caché compartida de horarios. Cada uno solo si el examen o la sombra muestran que hace falta.
