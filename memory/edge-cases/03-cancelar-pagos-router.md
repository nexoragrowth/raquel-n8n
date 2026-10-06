# Casos consolidados: cancelar_reprogramar, pagos_comprobantes, router

Base: workflow vivo al 2026-10-04 (v6 ACTIVO). Los nodos "Sub-Agent Cancelar" y "Sub-Agent Urgencia" del v6 son nodos MUERTOS. `cancelar_o_reprogramar` va al sub-workflow determinístico `5cAWJxiWJ50hxEq3` y `urgencia_dolor` va al flujo Triaje. Prompts de Router, Agendar, Confirmar y General curados el 2026-10-04 (Router de 19.400 a 1.998 chars). `live_prompt_cancelar_subwf.md` está vacío, así que no se pudo comparar el texto del sub-WF; sus reglas son código de nodo.
Abreviaturas de fuente: "raw eN EC-x" = caso crudo x del extractor edgecases_N. Capas: prompt | gate | banlist | nodo | infra.

---

## cancelar_reprogramar

### CAN-01 · Ghost appointment: aceptar un slot sin turno previo dice "Listo, reservando" y nunca se crea la cita
- **Entrada/disparador:** el paciente acepta un slot ofrecido en el sub-WF CancelarReprogramar sin tener turno previo que reprogramar.
- **Falla previa:** el Switch del Step 6 no tenía case `reservar_solo`. El bot decía "Listo, reservando" y Dentalink jamás creaba la cita. El paciente creía tener turno.
- **Esperado:** cuando no hay turno previo, Step 5 (`Decidir Accion Ejecutable`) devuelve acción `escalar` con el canned de escalación a secretaria. NO debe aparecer "Listo, reservando" ni ninguna afirmación de reserva. No debe haber ningún POST /citas desde este camino hasta que exista el nodo HTTP de auto-reserva (TODO).
- **Capa:** nodo (Step 5 / Switch Step 6, sub-WF `5cAWJxiWJ50hxEq3`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-02, docs/sesion-2026-06-02-fixes-y-backlog.md fix #2 (raw e4 EC-64)
- **Estado:** vigente (la auto-reserva sigue como TODO; el sub-WF se refactorizó el 07/09, verificar que el case `escalar` siga en el Switch)

### CAN-02 · "No veo turnos disponibles registrados en Dentalink": la query de horarios era siempre `undefined`
- **Entrada/disparador:** reprogramación; escalación real pegada por Lucas. Ocurrió 4 veces desde el 30/7.
- **Falla previa:** `Step 6b-prep: Prep Query Horarios` armaba el filtro en `dentalink_query_url`, pero `Step 6b: GET Agendas` leía `q_horarios` (nunca existía). La query salía `undefined` y devolvía siempre `{"data": []}`; el bot decía que no había turnos cuando sí había.
- **Esperado:** la búsqueda de horarios en reprogramación nunca devuelve vacío por un campo mal leído. Un `data: []` por error de wiring no puede traducirse a "no hay turnos". El mensaje "No veo turnos disponibles" solo aparece si `Buscar Horarios Validado` informa `hay_turnos:false`.
- **Capa:** nodo (`scripts/apply_fix_buscar_horarios_deep.py`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-09/10, current-state "orden de recordatorios multi-turno + bug real de Dentalink" (raw e2 EC-35)
- **Estado:** superado por CAN-19 (el 07/09 se eliminó `Step 6b: GET Agendas`; hoy es `executeWorkflow` a `GuDQ9VmKWZvQnerV`, con 0 ocurrencias de GET Agendas)

### CAN-03 · Riesgo latente: `continueOnFail` en Step 6a / 6d-1 puede confirmar un turno que nunca se creó
- **Entrada/disparador:** 37 nodos con `continueOnFail` en 8 workflows. Los más riesgosos: `Step 6a: Cancelar en Dentalink` y `Step 6d-1: POST Reservar` (sub-WF CancelarReprogramar). De las 9 ejecuciones reales solo una corrió y salió bien.
- **Falla previa:** (potencial, sin daño real documentado) si el POST/PUT falla, el flujo sigue y el bot podría decirle al paciente que el turno fue cancelado/reprogramado sin que exista en Dentalink.
- **Esperado:** si Step 6a o 6d-1 devuelven `{error}`, el mensaje al paciente NO puede afirmar cancelación ni reserva; debe escalar a secretaria (o reintentar). Diseño aún no decidido.
- **Capa:** nodo (pendiente de diseño)
- **Test:** SIN TEST (tests/test_turnos_formato.js:254 solo cubre `continueOnFail` en la paginación de horarios, no Step 6a/6d-1)
- **Fecha/fuente:** 2026-08-18, "Barrido sistemático" paso 3 (raw e2 EC-20)
- **Estado:** pendiente de decisión (¿reintentar o escalar?)

### CAN-04 · Dead-end de familias: los turnos se buscan solo en la primera ficha (`pacientesAll[0]`) y el bot escala siempre (gap 1)
- **Entrada/disparador:** varios pacientes (familia) bajo un mismo celular; la ficha resuelta por DNI/contexto no es la primera que devuelve Dentalink.
- **Falla previa:** `Step 2a` y `Step 4 __pickTurno` fetchean turnos SOLO de `pacientesAll[0]`. Si el turno es de otra ficha, siempre escala "coordinar a mano". Marcado CRÍTICO. Pregunta abierta: ¿en qué orden devuelve Dentalink las fichas de un celular?
- **Esperado:** resolver la ficha ANTES de enganchar turno y re-fetchear las citas de la ficha resuelta (o de todas las fichas del teléfono, máx. 4 GET). Para una familia con turno en la ficha 2, el sub-WF encuentra el turno y NO escala por "no encuentro turno".
- **Capa:** nodo (sub-WF `5cAWJxiWJ50hxEq3`); el canned "DNI o nombre de pila" va por prompt/canned
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06, docs/sesion-2026-07-06-precio-lid-reprogramacion.md §3; BKL P1 Fase 2 (raw e3 EC-57, e4 EC-65)
- **Estado:** pendiente de decisión (Fase 2 propuesta, sin evidencia de aplicación; verificar contra el workflow vivo)

### CAN-05 · El paciente rechaza el bloque de turnos y recibe el MISMO bloque indefinidamente
- **Entrada/disparador:** tras el bloque de reprogramación: "ninguno me sirve" / "a la tarde".
- **Falla previa:** Router (continuación) → `cancelar_o_reprogramar` → Step 0b marca `oferta_horarios` → Step 3.5c `accepts:false` → Step 5 `fecha_objetivo:''` → Step 6b-prep busca desde HOY → bloque idéntico byte a byte. Las únicas salidas eran `is_frustrated` (exige "ya te dije", "insisto") y `loop_no_turnos` (regex que no matchea el bloque nuevo). Nunca escalaba.
- **Esperado:** Step 0b calcula `oferta_bloque`, `oferta_siguiente_desde` y `bloques_ofrecidos`. "a la tarde" repite esa sección del bloque anterior SIN consultar la agenda. "ninguno me sirve" ofrece el lote siguiente (`desde` del bloque anterior). Rechazo del segundo lote → acción `escalar` ("Le paso la consulta a la secretaria…"). NUNCA el mismo bloque dos veces; no hay un tercer bloque.
- **Capa:** nodo (Step 0b / Step 5, sub-WF)
- **Test:** tests/test_turnos_formato.js §4.c ("Step 0b: saca del último mensaje el bloque…", "Step 5: 'ninguno me sirve' -> siguiente lote", "después de DOS bloques rechazados escala", "si la franja pedida no tiene nada que sirva, se busca el lote siguiente")
- **Fecha/fuente:** 2026-09-07, docs/turnos-formato-2026-09-07.md §3B y §8 #4; current-state "APLICADO: formato de turnos" (raw e1 EC-25, e4 EC-61)
- **Estado:** vigente

### CAN-06 · Reprogramar preguntaba "¿qué día o franja le viene mejor? (mañana / tarde / fecha concreta)"
- **Entrada/disparador:** captura 3 de la Dra. (07/09): "Para reprogramar su turno del Miércoles 9 de Septiembre a las 16:10 hs, qué día o franja le viene mejor? (mañana / tarde / fecha concreta)" (Step 5, línea 100 del sub-WF).
- **Falla previa:** pedía fecha/franja, algo que la Dra. prohibió. Además el primer parche se aplicó al `Sub-Agent Cancelar` del v6, que es código muerto.
- **Esperado:** el primer "quiero reprogramar" ofrece el bloque desde hoy SIN preguntar día ni franja. Step 5 tiene tres salidas sin preguntas: repetir sección del bloque anterior / escalar tras dos bloques / ofrecer el (siguiente) bloque. Ningún mensaje de Step 5 contiene pregunta de día/franja ni nombra el sistema de gestión.
- **Capa:** nodo (Step 5)
- **Test:** tests/test_turnos_formato.js ("Step 5: primer 'quiero reprogramar' -> se ofrece el bloque desde hoy, SIN preguntar día ni franja", "ningún mensaje de Step 5 pregunta día ni franja ni nombra el sistema de gestión")
- **Fecha/fuente:** 2026-09-07, docs/turnos-formato-2026-09-07.md §1 captura 3 y §3B (raw e4 EC-62)
- **Estado:** vigente
- **Riesgo de regresión:** el Sub-Agent Cancelar muerto sí conserva "buscar_horarios SIN parámetros (NO preguntar mañana o tarde)"; el Sub-Agent Agendar curado mantiene la prohibición. Verificar que ningún prompt de General diga "Ahora le paso los turnos" (ver RTR-13).

### CAN-07 · Step 0b no reconocía el bloque de turnos nuevo (mañana/tarde): la elección del paciente se perdía
- **Entrada/disparador:** tras el nuevo formato de bloque, el paciente elige uno de los turnos ofrecidos.
- **Falla previa:** `Step 0b` del sub-WF no reconocía el bloque nuevo y la elección se perdía (bug latente, detectado al cambiar el formato).
- **Esperado:** `Step 0b` reconoce el bloque del último mensaje y arrastra el lote (`desde`) y `bloques_ofrecidos`. Si el último mensaje no trae bloque, no inventa nada.
- **Capa:** nodo (Step 0b)
- **Test:** tests/test_turnos_formato.js ("Step 0b: saca del último mensaje el bloque…", "cuenta los bloques ya ofrecidos", "sin bloque en el último mensaje no inventa nada")
- **Fecha/fuente:** 2026-09-07 20:55 ART, current-state "APLICADO: formato de turnos pedido por la Dra. Raquel" (raw e1 EC-23)
- **Estado:** vigente

### CAN-08 · Desambiguación por apellido familiar: el canned induce una respuesta que rompe el matching (gap 2)
- **Entrada/disparador:** el bot pide "nombre y apellido"; el paciente responde con el apellido que comparte toda la familia.
- **Falla previa:** `tokens.some()` sobre nombre+apellido matchea TODAS las fichas; el canned induce justo la respuesta que rompe el match (CRÍTICO).
- **Esperado:** matching por scoring (nombre de pila pesa más, all-tokens > some-token). El canned multi-ficha pide "DNI o solo el nombre de pila", NO "nombre y apellido".
- **Capa:** nodo (Step 1b / Step 4) + prompt/canned
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06, docs/sesion-2026-07-06-precio-lid-reprogramacion.md §3; BKL P1 Fase 1(c) (raw e3 EC-57, e4 EC-66)
- **Estado:** pendiente de decisión (Fase 1/2 esperando OK de Lucas; sin evidencia de aplicación)

### CAN-09 · Fichas duplicadas exactas ("Martina G. y Martina G."): la lista repite el nombre y hay loop sin salida (gap 3)
- **Entrada/disparador:** celular con dos fichas de nombre idéntico; el bot lista las fichas para elegir.
- **Falla previa:** la lista repite el nombre, el paciente no puede distinguir y entra en loop sin salida (ALTO).
- **Esperado:** con fichas indistinguibles por nombre, el bot pide DNI (o escala a secretaria) en vez de repetir la misma lista. No debe haber dos opciones con texto idéntico.
- **Capa:** nodo (Step 1b / Step 4)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06, docs/sesion-2026-07-06-precio-lid-reprogramacion.md §3 (raw e4 EC-66)
- **Estado:** pendiente de decisión (el fix concreto para duplicados no está definido en las fuentes)

### CAN-10 · Anti-loop: el canned multi-ficha no está en `fraseLoop` del Step 0b (gap 4)
- **Entrada/disparador:** respuestas repetidas del canned multi-ficha ("Con este número tengo registrada a más de una persona…").
- **Falla previa:** el loop de canned no se detecta porque la frase no está en `fraseLoop`.
- **Esperado:** sumar el canned multi-ficha a `fraseLoop` del Step 0b; tras repetirse, el flujo escala en vez de repetir el canned.
- **Capa:** nodo (Step 0b)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06, BKL P1 (b) (raw e3 EC-58, e4 EC-66)
- **Estado:** pendiente de decisión (sin evidencia de aplicación)

### CAN-11 · Cancelación por enfermedad ("pasó con fiebre… no va") entra por CancelarReprogramar con error técnico
- **Entrada/disparador:** "Buen día, G. pasó con fiebre y aún no le baja… no va. disculpe" (escalación #17, 21/7).
- **Falla previa:** `error_tecnico_dentalink` en [CancelarReprogramar]. Además, la palabra "fiebre" sola dispararía el gate de red flags si se evaluara fuera del camino de urgencias (falso positivo).
- **Esperado:** el gate de red flags corre SOLO dentro del camino `urgencia_dolor` (después de que el Router clasificó urgencia). Una cancelación por enfermedad NO es urgencia clínica: sigue por cancelar_o_reprogramar y no activa label humano ni escalación de urgencia.
- **Capa:** gate (ubicación del gate en el grafo)
- **Test:** triaje/test_gate.js ("fiebre en una CANCELACIÓN: el gate dispara, por eso solo debe correr dentro del camino de urgencias"). No hay test E2E de la cancelación por enfermedad ni del `error_tecnico_dentalink`.
- **Fecha/fuente:** 2026-07-21 (escalación) y 2026-09-02 (revisión), docs/analisis-retrospectivo-urgencias-2026-09-02.md (raw e4 EC-68)
- **Estado:** vigente (la parte del gate); el `error_tecnico_dentalink` de esa ejecución no está explicado en las fuentes

### CAN-12 · Pregunta legítima de un padre termina en [NO_REPLY] sin respuesta ni escalación
- **Entrada/disparador:** exec 184080 (ventana de julio): un padre pregunta algo sobre el turno de su hijo.
- **Falla previa:** terminó en `[NO_REPLY]`; el paciente quedó sin respuesta.
- **Esperado:** una pregunta legítima sin respuesta resoluble debe ir a la secretaria (canned de escalación), no a silencio. El silencio solo es válido para cierres puros y avisos de llegada.
- **Capa:** prompt + nodo (red anti-silencio de `Fallback Output`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06, docs/sesion-2026-07-06-precio-lid-reprogramacion.md §3 "Evidencia en vivo" (raw e4 EC-69)
- **Estado:** superado por RTR-03 (2026-10-02, `Fallback Output` devuelve el canned "Hola! Ya le transmito su consulta a la secretaria…" cuando el agente da vacío/`[NO_REPLY]` y el mensaje no es un cierre puro). La regla "ante duda silencio" de VALIDACION DE DESTINO quedó atenuada por esa red.

### CAN-13 · Cancelar/reprogramar no consulta `recordatorios_enviados`, no cierra la fila y toma `cita_a_cancelar = turnos[0]` (gap 6)
- **Entrada/disparador:** el paciente cancela/reprograma un turno que tiene recordatorio abierto.
- **Falla previa:** la fila de `recordatorios_enviados` queda abierta (el recordatorio sigue "pendiente"); el sub-WF no usa la solución que SÍ resuelve familia en Confirmar. `cita_a_cancelar = turnos[0]` (primer turno próximo, no el turno del que habla el paciente). MEDIO/ALTO.
- **Esperado:** consultar `recordatorios_enviados` (PASO 0) y llamar `marcar_recordatorio_cancelado` tras cancelar. Leer de vuelta antes de cancelar ("Le confirmo que quiere cancelar el turno del [fecha] a las [hora]?") salvo fecha+hora exacta que coincida con UN turno activo. Para el paciente con 2+ turnos, NO se cancela el primero por defecto.
- **Capa:** nodo (sub-WF) para la parte viva; el prompt `cancelar_paso0_recordatorios` / `cancelar_tools.md` solo aplica al Sub-Agent Cancelar MUERTO
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06, docs/sesion-2026-07-06-precio-lid-reprogramacion.md; BKL P1/P2 Fase 3 (raw e3 EC-60, e4 EC-67)
- **Estado:** pendiente de decisión. La implementación en prompt es de un nodo muerto, así que la regla hoy no está aplicada por ninguna capa viva salvo que el sub-WF la tenga (verificar).

### CAN-14 · Reprogramación multi-turno no persiste `turno_objetivo` (gap 5)
- **Entrada/disparador:** flujo de reprogramación de varios mensajes (el turno hablado al inicio se pierde entre turnos).
- **Falla previa:** no se persiste el turno objetivo en el estado multi-turno.
- **Esperado:** persistir `turno_objetivo` en el estado del sub-WF; el turno reprogramado en el mensaje N es el mismo del mensaje 1. Test sintético + shadow antes del cutover.
- **Capa:** nodo (sub-WF)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06, BKL P1/P2 Fase 2 (raw e3 EC-60, e4 EC-65)
- **Estado:** pendiente de decisión (sin evidencia de aplicación)

### CAN-15 · Política: el agente NO cancela turnos por defecto; read-back y solo `{id_estado:1}`
- **Entrada/disparador:** "no puedo ir", "cancelar", "anular", "reprogramar", "no voy a poder".
- **Falla previa:** n/a (política reforzada por la Dra. el 14/7: "cancelar es último recurso").
- **Esperado:** el agente sigue la agenda y marca confirmaciones. La cancelación exige read-back previo ("Le confirmo que quiere cancelar el turno del [fecha] a las [hora]?") y luego `cancelar_turno` con SOLO `{id_estado:1}`. Cancelar/reprogramar requiere aviso con 48 hs. NO mencionar penalizaciones que la doctora no documentó. Cancelar se hace EN LA AGENDA (Dentalink) y el bot no recuerda ese turno.
- **Capa:** prompt (cancelar_tools.md, solo vivo en el nodo muerto) + proceso (agenda como fuente de verdad)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-14, docs/reunion-2026-07-14-dra-raquel.md decisión 5; docs/kb-validacion-dra-2026-07-09.md [26] (raw e4 EC-71)
- **Estado:** vigente como política; la capa que la hace cumplir es un prompt de nodo muerto, así que no hay garantía en el camino vivo. Verificar que el sub-WF `5cAWJxiWJ50hxEq3` exija read-back.

### CAN-16 · Fila envenenada en la tabla de estado del sub-WF (JSON inválido / NOT NULL)
- **Entrada/disparador:** fila de estado del sub-WF (v2) con contenido no-JSON.
- **Falla previa:** Step 0b fallaba al parsear y el caso quedaba trabado.
- **Esperado:** Step 0b tolerante a no-JSON (try/catch → estado vacío) y la columna JSONB NOT NULL. Una fila inválida no puede bloquear al paciente.
- **Capa:** nodo (Step 0b) + infra (DB, v3 limpia + JSONB NOT NULL aplicado)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-18, BKL P1 post-incidente (raw e3 EC-59)
- **Estado:** pendiente de decisión (v3 limpia aplicada; el hardening de Step 0b sigue pendiente)

### CAN-17 · Dentalink PUT anular responde 400 si se manda `comentario_anulacion`
- **Entrada/disparador:** cita 7905 (abril 2026) al anular con un comentario.
- **Falla previa:** cualquier key distinta de `id_estado: 1` da 400 "Parametro X no existe".
- **Esperado:** el PUT de anulación envía solo `{id_estado:1}`; la tool `cancelar_turno` no manda ningún otro campo.
- **Capa:** nodo (tool `cancelar_turno`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-04, BUGS #15 y FIXES Lecciones (raw e3 EC-55)
- **Estado:** vigente

### CAN-18 · Reprogramación "cualquier día por la tarde después de las 17hs": repetía el canned / respuestas evasivas
- **Entrada/disparador:** "cualquier dia por la tarde despues de las 17hs" (turno previo: miércoles 29 de julio 18:40 hs).
- **Falla previa:** Step 5 no activaba la búsqueda y el sub-WF repetía el canned de clarificación; si las próximas 2 semanas de tarde estaban llenas daba respuestas largas/evasivas.
- **Esperado (versión 28/7):** con franja tarde y `hora_minima` 17, Step 5 ejecuta `buscar_horarios`; Step 6b-out busca 6 semanas de lunes y miércoles, descarta la mañana (11:00) y responde PRIMERO lo pedido ("primer turno disponible es el Miércoles 2 de Septiembre a las 17:00"), con nota secundaria de la alternativa de mañana y cierre "¿Te reservo el …?".
- **Esperado (versión vigente 07/09):** el bloque trae SIEMPRE las dos franjas; la franja pedida se resuelve recortando/filtrando la sección del bloque YA ofrecido (Step 5, p. ej. "después de las 16" filtra los horarios), sin repetir el canned. Si la franja no tiene nada que sirva, se busca el lote siguiente.
- **Capa:** nodo (Step 5 / Step 6b-out)
- **Test:** tests/test_turnos_formato.js ("después de las 16 filtra", "si la franja pedida no tiene nada que sirva…"). tests/test_nodes_eval.py es una simulación con copia de la lógica, no corre el nodo real. tests/test_reprogramar_franja.py solo imprime si `hora_minima_detectada` está en `Step 6b-out: Ofrecer Slots`, sin aserción; probablemente obsoleto porque ese nodo hoy solo reenvía `bloque`.
- **Fecha/fuente:** 2026-07-28, DEC "Reprogramacion: Busqueda profunda"; reemplazado por el rediseño 2026-09-07 (raw e3 EC-56, e4 EC-63)
- **Estado:** superado por CAN-19 y CAN-05 en lo que respecta a la búsqueda profunda de 6 semanas y al mensaje "primer turno disponible…". Contradicción: 28/7 decía que Step 6b-out filtraba y armaba el mensaje; 07/09 y 01/10 muestran que 6b-out solo reenvía `bloque`. Se mantiene el 07/09.

### CAN-19 · Una sola implementación de búsqueda de horarios; "prefiero por la tarde" sobre una oferta existente
- **Entrada/disparador:** ante un bloque ya ofrecido, el paciente responde "prefiero por la tarde".
- **Falla previa (histórica):** dos implementaciones del mismo problema (GET Agendas hardcodeado a Dentalink + `CORTE_TARDE`) divergían.
- **Esperado:** `Step 6b: Buscar Horarios (bloque)` es un `executeWorkflow` a `Sub-WF - Buscar Horarios Validado` (`GuDQ9VmKWZvQnerV`), el mismo que usa Agendar. `Step 6b-out` solo reenvía el campo `bloque`. El bloque trae SIEMPRE las dos franjas; `franja`/`hora_minima` ya no filtran. Las ~60 menciones de "franja" en `Step 5` son legítimas: recortan y repiten una sección (mañana/tarde) del bloque ya ofrecido sin volver a consultar Dentalink. En todo el workflow: 0 ocurrencias de `GET Agendas` y de `CORTE_TARDE`.
- **Capa:** nodo
- **Test:** tests/test_turnos_formato.js (indirecta, citada el 2026-09-07)
- **Fecha/fuente:** 2026-10-01 (tarde), verificado en el workflow vivo (cambio original 2026-09-07), current-state "CancelarReprogramar: el refactor … YA está en vivo" (raw e1 EC-11)
- **Estado:** vigente. Nota: el snapshot local en `workflows/current/` está desactualizado respecto al vivo.

### CAN-20 · Verificar el camino vivo antes de editar prompts: las capturas de la Dra. venían del sub-WF, no del Sub-Agent Cancelar huérfano
- **Entrada/disparador:** 3 capturas de la Dra. con formato de turnos erróneo.
- **Falla previa:** se asumió que el origen era `Sub-Agent Cancelar`, HUÉRFANO (sin conexión main de entrada) desde hace meses; el origen real era `Sub-WF - CancelarReprogramar`. El parche inicial fue código muerto. Se editaron 6 nodos del sub-WF (`Step 6b: GET Agendas` → `Step 6b: Buscar Horarios (bloque)`).
- **Esperado:** todo fix de cancelar/reprogramar va en el sub-WF `5cAWJxiWJ50hxEq3`, nunca en `Sub-Agent Cancelar` ni en sus partials de prompt. Pendiente de limpieza: borrar el nodo huérfano `Sub-Agent Cancelar` (Fase 3 del plan de reprogramaciones).
- **Capa:** nodo / proceso
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-07 20:55 ART, current-state "APLICADO: formato de turnos pedido por la Dra. Raquel"; 2026-07-06 BKL (raw e1 EC-27, e3 EC-60 parte "huérfano")
- **Estado:** vigente (confirmado el 4/10/2026: el nodo sigue muerto y sin borrar)

### CAN-21 · Regex de aceptación de Step 4: "sino" matchea `isAffirm` por el `si+`
- **Entrada/disparador:** el paciente escribe "sino" (o similar) en un paso de aceptación.
- **Falla previa:** `si+` matchea prefijos y lo lee como afirmación (edge raro, abierto). Un finding del auditor sobre `\b` mal escapado resultó falso positivo (los regex usan `^(...)`).
- **Esperado:** "sino" NO se interpreta como afirmación; anclar el regex por palabra completa / al final.
- **Capa:** nodo (Step 4)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-02, docs/sesion-2026-06-02-fixes-y-backlog.md "Otros (menor)" (raw e4 EC-70)
- **Estado:** vigente (abierto, severidad baja)

### CAN-22 · Step 3.5b LLM Acceptance: el "skip implícito" funciona pero es sucio
- **Entrada/disparador:** paciente en el paso de aceptación de slot.
- **Falla previa:** el skip implícito del nodo funciona pero es frágil (propuesta A3 de la auditoría, ALTO, sin aplicar).
- **Esperado:** limpiar el skip de manera explícita en el refactor v7, sin cambiar el comportamiento observable.
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-18, docs/auditoria-propuestas-a3-2026-07-18.md #5 (raw e4 EC-72)
- **Estado:** pendiente de decisión (diferido al refactor v7)

### Cobertura
22 casos; 16 SIN TEST (CAN-01, 02, 03, 04, 08, 09, 10, 12, 13, 14, 15, 16, 17, 20, 21, 22); 1 con test parcial (CAN-11, solo el gate) y 1 con test débil (CAN-18).
Huecos más peligrosos: (1) CAN-01/CAN-03: el bot puede afirmar al paciente una reserva/cancelación que Dentalink nunca registró, sin test del Switch ni de `continueOnFail`; (2) familias, CAN-04/08/09/10: dead-end y loop, sin ningún test, con el sub-WF como único camino; (3) CAN-13/15: la política de read-back y el cierre de `recordatorios_enviados` vivían en el prompt del Sub-Agent Cancelar muerto, así que hoy ninguna capa viva verificada las hace cumplir.

---

## pagos_comprobantes

### PAG-01 · Comprobante de pago nunca respondido ni registrado (migración a Evolution GO)
- **Entrada/disparador:** S. B. envió sus datos y un comprobante de pago el 2026-08-05.
- **Falla previa:** `Webhook Validator` rechazaba el 100% de los entrantes (shape viejo) antes de guardarlos; sin respuesta ni registro.
- **Esperado:** todo comprobante (imagen/documento "TIPO: COMPROBANTE") se recibe, se guarda y se deriva al grupo; NO se valida monto. El Webhook Validator acepta el shape Evolution GO (whatsmeow). Verificación obligatoria con un test E2E real con payload capturado.
- **Capa:** nodo (Webhook Validator + 4 nodos de extracción) / infra (migración Evolution GO)
- **Test:** SIN TEST (solo E2E manual con payload real; tests/test_e2e_triaje.py manda el shape GO al validator pero con texto de urgencia, no con comprobante; tests/test_media_nodos.js cubre un caso de excepción interna con "[IMAGEN] TIPO: COMPROBANTE")
- **Fecha/fuente:** 2026-08-05, DEC "Verificar SIEMPRE con un test E2E real" (raw e3 EC-61)
- **Estado:** vigente

### PAG-02 · Pregunta por el pago de un TRATAMIENTO recibe el canned de la CONSULTA (caso Carla / Gate Pago Tratamiento)
- **Entrada/disparador:** "Por otro lado tb quería saber si puedo ese lunes abonar el tratamiento de T.?" (conversaciones id 5944, exec 269717, 3/9).
- **Falla previa:** el bot respondió "Nosotros le enviamos un recordatorio… le solicitaremos abonar el valor de la consulta. Puede acercarse al consultorio a abonar en efectivo o transferir": canned de la CONSULTA, no del tratamiento.
- **Esperado:** el nodo determinístico `Gate Pago Tratamiento` sustituye la respuesta por "El pago del tratamiento lo coordina directamente la Dra. Raquel. Le paso su consulta para que se comunique con usted." y notifica al grupo (exactamente 1 escalación). La respuesta NO contiene "valor de la consulta".
- **Capa:** gate (Gate Pago Tratamiento) + prompt (capa 1)
- **Test:** tests/test_gate_pago_tratamiento.py ("REAL 3/9 Carla")
- **Fecha/fuente:** 2026-09-03, docstring de tests/test_gate_pago_tratamiento.py (raw e3 EC-62, e4 EC-93)
- **Estado:** vigente
- **Riesgo de regresión:** la capa 1 (prompt) que decía "el pago del tratamiento lo coordina la Dra." ya no está en el Sub-Agent General curado (solo conserva "pedidos de presupuesto a medida → escalar"). Hoy el gate es la única capa efectiva; verificar que siga conectado antes del Banlist.

### PAG-03 · Gate Pago: passthrough en `[NO_REPLY]` y en urgencia (no escalar pago cuando es una urgencia)
- **Entrada/disparador:** output `[NO_REPLY]`; "me duele mucho, puedo pagar el tratamiento después?" (intent `urgencia_dolor`).
- **Falla previa:** riesgo documentado: `TEMA_TRATAMIENTO` incluye "brackets"/"aparato". Un seguimiento mal ruteado a General ("se me despegó el bracket, ¿lo pago aparte?") dispara una escalación de pago (con label humano) en vez de urgencia.
- **Esperado:** passthrough exacto (sin override ni escalación) cuando `intent === 'urgencia_dolor'` o el output contiene `[NO_REPLY]`.
- **Capa:** gate
- **Test:** tests/test_gate_pago_tratamiento.py ("PASSTHROUGH [NO_REPLY]", "PASSTHROUGH urgencia"). El caso "bracket despegado mal ruteado a General" NO está testeado.
- **Fecha/fuente:** 2026-09-03 / 2026-09-04, tests/test_gate_pago_tratamiento.py; mapeo-read_router.md RISKS (raw e4 EC-97)
- **Estado:** vigente (riesgo residual del mal ruteo documentado)

### PAG-04 · Alias pedido junto con "Confirmo": el bot confirma el turno y no responde el alias (caso Paulina)
- **Entrada/disparador:** 2026-09-02, recordatorio 72h para el turno de la hija de P. V. (Viernes 4/9 11:10 hs). Dos burbujas en el mismo minuto, mergeadas por el buffer en una fila (id 5747): "Confirmo\nPor favor pásame el alias para que te transfiera el costo de la primera consulta".
- **Falla previa:** el bot confirmó en Dentalink y contestó 16 ms después solo el canned de confirmación (id 5746), sin mención del alias. La Dra. lo respondió a mano 1 h 38 después (marcado `[ATENCION HUMANA]`). Causa raíz: `confirmar_paso0_recordatorios.md` línea 35 ("REGLA CRITICA… NO ejecutes PASO 1/2/3… Solo responder y FIN") y `confirmar_tools.md` línea 52 dejaban el pedido extra para "el próximo turno" que el Router reclasificaría; con el buffer no hay próximo turno. Confirmar no tiene canned de INFO CANNED.
- **Esperado:** nodo `Canned Sidecar` (Code determinístico) donde convergen los 7 caminos de salida (`Fallback Output` → Canned Sidecar → `Banlist Validator`): lee el texto REAL del paciente, detecta por regex si pidió alias/datos de pago o precio y, si la respuesta del sub-agent no lo trae, lo ANEXA; nunca modifica lo que generó el sub-agent. La respuesta a "Confirmo + ¿alias?" contiene el canned de confirmación Y el alias/datos. Ningún sub-agent necesita saber de info canned.
- **Capa:** nodo (`Canned Sidecar`)
- **Test:** tests/test_canned_sidecar.py (caso "Confirmo. ¿Cuánto sale? ¿Y el alias?" → "SUPERSEDE precio+alias -> solo pago"). No hay caso con el texto exacto de Paulina.
- **Fecha/fuente:** 2026-09-02, current-state "Bug real (reportado por las secretarias): pedido de alias post-confirmación queda sin responder"; decisions.md 2026-09-02 (raw e1 EC-75)
- **Estado:** vigente
- **Riesgo de regresión:** el prompt de Confirmar fue curado el 4/10; ya no contiene la REGLA CRITICA que dejaba el pedido para el próximo turno. Verificar que el Sidecar siga anexando el alias y que Confirmar curado no lo duplique.

### PAG-05 · Pedido de alias con "ahora le mando el comprobante": el sub-agent responde "Recibimos su comprobante" y NO envía el alias
- **Entrada/disparador:** 28/8 (conversaciones id 5406): "Buenas tardes ahora le mando el comprobante\nA donde le hago la transferencia?\nQue alias?". Mismo patrón sistémico en un segundo teléfono el 28-29/8 (la Dra. contestó al día siguiente apuntando a una imagen: "Ese alias👆").
- **Falla previa:** el sub-agent respondió "Recibimos su comprobante. Le informo a la secretaria…" (PASO 0 de Confirmar trata "te paso el comprobante" como comprobante) y no envió el alias; sin respuesta del bot en el segundo caso.
- **Esperado:** el Canned Sidecar anexa alias+datos (sidecar 'pago') conservando intacto el texto del sub-agent. La respuesta final contiene tanto "Recibimos su comprobante…" como el alias y los datos de cuenta.
- **Capa:** nodo (`Canned Sidecar`)
- **Test:** tests/test_canned_sidecar.py ("REAL 28/8 (comprobante + donde transfiero + que alias)")
- **Fecha/fuente:** 2026-08-28/29 (detectado 2026-09-02), current-state "Bug real…"; tests/test_canned_sidecar.py (raw e1 EC-76, e4 EC-98)
- **Estado:** vigente
- **Riesgo de regresión:** el Confirmar curado mantiene su PASO 0 ("te paso el comprobante" → canned y sin alias), por lo que la dependencia del Sidecar es total.

### PAG-06 · "¿Puedo pagar el día de la consulta?" respondido con el canned genérico de alias
- **Entrada/disparador:** el paciente pregunta puntualmente si puede pagar el mismo día o al llegar.
- **Falla previa:** el canned genérico de alias sonaba a "podés pagar cuando quieras".
- **Esperado:** texto que pidió la Dra.: "Nosotros le enviamos un recordatorio… dos días hábiles antes… para confirmar su asistencia le solicitaremos abonar…". NO debe responder solo con el alias como si el pago fuera libre.
- **Capa:** prompt (canned en Sub-Agent General, `apply_fix_pago_dia_consulta.py`)
- **Test:** SIN TEST (tests/test_gate_pago_tratamiento.py solo verifica que el gate NO dispara para "Puedo pagar el mismo día de la consulta?", no el texto)
- **Fecha/fuente:** 2026-08-21, `apply_fix_pago_dia_consulta.py` (raw e2 EC-13)
- **Estado:** vigente
- **Riesgo de regresión:** el General curado (4/10) no contiene el texto "Nosotros le enviamos un recordatorio… dos días hábiles antes…"; solo dice "responde con los DATOS OFICIALES". Alta probabilidad de regresión; verificar el texto exacto en el prompt vivo.

### PAG-07 · Gate Pago: dedup cuando la capa 1 (prompt) ya produjo el canned
- **Entrada/disparador:** "puedo abonar el tratamiento el lunes?" con output igual al canned exacto del gate (también con saludo "Hola! Soy Asiri…" delante, exec 270379).
- **Falla previa:** riesgo de escalación duplicada y de perder el saludo.
- **Esperado:** sin override ni nueva escalación cuando el output ya es el canned del gate (incluye el caso con saludo, que se preserva). Cualquier otra respuesta (incluso el canned real de precio que no menciona "tratamiento") SÍ dispara override a propósito.
- **Capa:** gate
- **Test:** tests/test_gate_pago_tratamiento.py ("DEDUP: capa 1 ya devolvió el canned exacto", "DEDUP REAL (exec 270379)", "NO-DEDUP: canned real de precio")
- **Fecha/fuente:** 2026-09-03, tests/test_gate_pago_tratamiento.py (raw e4 EC-95)
- **Estado:** vigente

### PAG-08 · Gate Pago: variantes de fraseo (cuota, brackets, transferir, "pagué")
- **Entrada/disparador:** "Quiero pagar el tratamiento de mi hijo, ¿se puede en cuotas?"; "Cómo hago para transferir lo del tratamiento?"; "Si pagué el tratamiento este mes, ¿alcanza?"; "Puedo pagar la cuota el lunes?"; "Queria saber si puedo abonar los brackets este viernes".
- **Falla previa:** n/a (cobertura de test).
- **Esperado:** override + exactamente 1 escalación (los pacientes confunden "cuota" con "tratamiento"; los nombres específicos de tratamiento también disparan). Multi-item: override en todos los items. Texto vacío sin output: sin override.
- **Capa:** gate
- **Test:** tests/test_gate_pago_tratamiento.py ("VARIANTE …", "ROBUSTEZ multi-item", "ROBUSTEZ texto vacio")
- **Fecha/fuente:** 2026-09-03, tests/test_gate_pago_tratamiento.py (raw e4 EC-96)
- **Estado:** vigente

### PAG-09 · Gate Pago: el pago de la CONSULTA no dispara el gate (negativos)
- **Entrada/disparador:** "Puedo pagar el mismo día de la consulta?"; "tiene turno el lunes?"; "cuánto dura el tratamiento de T.?"; "El tratamiento le va muy bien.\nPuedo pagar la consulta el lunes?" (palabras en oraciones distintas).
- **Falla previa:** n/a (cobertura de test).
- **Esperado:** sin override ni escalación: pago y tratamiento deben estar en la MISMA oración para disparar.
- **Capa:** gate
- **Test:** tests/test_gate_pago_tratamiento.py ("NEG pago de consulta", "NEG pregunta de turno sin pago", "NEG 'tratamiento' sin palabra de pago", "NEG 'pago' sin tratamiento (otra oración)")
- **Fecha/fuente:** 2026-09-03, tests/test_gate_pago_tratamiento.py (raw e4 EC-94)
- **Estado:** vigente

### PAG-10 · Canned Sidecar: dedup, passthrough y robustez
- **Entrada/disparador:** General ya respondió con el alias; output `[NO_REPLY]`; intent urgencia ("me duele mucho, ¿cuánto sale la consulta?"); precio solo; "Confirmo. ¿Cuánto sale? ¿Y el alias?"; nodo `Extraer Horarios y Precio` no corrió (camino Set NO_REPLY); `Preparar Mensaje Final` no corrió; multi-item.
- **Falla previa:** n/a (cobertura de test).
- **Esperado:** no duplicar el alias si el sub-agent ya lo dio; passthrough en `[NO_REPLY]` y en urgencia; "cuánto sale la consulta?" → solo precio (sidecar 'precio'); precio+alias → solo 'pago'; sin `Extraer Horarios y Precio` usa el precio por defecto $50.000 y anexa igual; sin `Preparar Mensaje Final` no anexa; multi-item anexa en todos y conserva los campos del item.
- **Capa:** nodo (Canned Sidecar)
- **Test:** tests/test_canned_sidecar.py ("DEDUP General ya respondió el alias", "PASSTHROUGH …", "PRECIO solo", "SUPERSEDE precio+alias -> solo pago", "ROBUSTEZ …")
- **Fecha/fuente:** 2026-09-02, tests/test_canned_sidecar.py (raw e4 EC-100)
- **Estado:** vigente. Nota: el precio por defecto $50.000 está hardcodeado en el nodo; el precio vigente es dinámico (`precio_consulta`); verificar que no diverja.

### PAG-11 · Canned Sidecar: menciones que NO son pedidos no anexan nada
- **Entrada/disparador:** "El alias sigue siendo ese"; "Confirmo"; "ya transferí, te paso el comprobante"; "hay turnos a la tarde?"; "Perfecto, gracias".
- **Falla previa:** n/a (cobertura de test).
- **Esperado:** sin anexo (no se manda alias ni precio cuando el paciente no lo pidió).
- **Capa:** nodo (Canned Sidecar)
- **Test:** tests/test_canned_sidecar.py ("NEG mención…", "NEG 'Confirmo' solo", "NEG ya transfirió", "NEG pregunta sin tema canned", "NEG cierre cortés")
- **Fecha/fuente:** 2026-09-02, tests/test_canned_sidecar.py (raw e4 EC-99)
- **Estado:** vigente

### PAG-12 · Paciente confirma que viene HOY a abonar: escalar con resumen
- **Entrada/disparador:** "voy hoy", "voy", "paso hoy", "perfecto voy" tras ofrecer pagar en la clínica.
- **Falla previa:** n/a.
- **Esperado:** `escalar_a_secretaria` con "Paciente <nombre> confirmó que viene HOY a abonar la consulta. Confirmar recepción del pago." y canned "Perfecto, lo dejo anotado. Le confirmamos al recibir el pago…" (sin "le paso a la secretaria"). Máximo 1 escalación.
- **Capa:** prompt
- **Test:** SIN TEST
- **Fecha/fuente:** prompts/v6_partials/confirmacion_pago.md (sin fecha); prompt vivo del Sub-Agent General al 2026-10-04 (raw e4 EC-103)
- **Estado:** vigente. Contradicción de fuentes: el partial citaba un monto de $40.000 (desactualizado respecto al precio vigente $50.000) y la redacción difiere; se queda con el prompt vivo del General (4/10), que dice "Perfecto, lo dejamos anotado. Al recibir el pago le confirmamos. ¡Muchas gracias!" con `escalar_a_secretaria("Paciente confirma visita para abonar en el consultorio")`.
- **Riesgo de regresión:** esta regla vive hoy SOLO en el Sub-Agent General curado, pero el Router vivo manda "voy"/"dale" a `confirmar_post_recordatorio` (Sub-Agent Confirmar), que no tiene la regla. Verificar a qué sub-agent llega "voy hoy" tras la oferta de pagar en la clínica.

### PAG-13 · Política de pago: solo la PRIMERA CONSULTA requiere pago anticipado (pre-reserva)
- **Entrada/disparador:** turno de primera consulta (punto amarillo fluor en la agenda) vs controles/contención.
- **Falla previa:** n/a.
- **Esperado:** si no abona igual se agenda, pero junto al recordatorio (48 hs hábiles antes) se manda el mensaje de pago. Si 24 hs antes no respondió ni abonó: "debido a la falta de respuesta de su parte deberemos reprogramar su turno". La reserva es PRE-reserva; la confirmación definitiva llega con el pago hasta 72 hs antes. Faltante de monto: NO hay tolerancia (recalcar la diferencia). Controles y contención no piden pago anticipado.
- **Capa:** prompt + datos (KB 1, 16, 26, 27)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-09, docs/kb-validacion-dra-2026-07-09.md [1], [16], [26], [27] (raw e4 EC-101)
- **Estado:** vigente
- **Riesgo de regresión:** el Sub-Agent Agendar curado conserva el mensaje "PRE-reservado… pago hasta 72 hs antes". El Confirmar curado, ante un comprobante, ejecuta `confirmar_turno(id_cita)` sin esperar la verificación de la secretaria, lo cual choca con "confirmación definitiva con el pago verificado". Marcar para decisión.

### PAG-14 · Comprobante de monto alto / "Quiero pagar el tratamiento": preguntar cuántos pagos y pesos o dólares
- **Entrada/disparador:** comprobante de monto alto (plan de pagos de ortodoncia), o "Quiero pagar el tratamiento".
- **Falla previa:** n/a (KB 13; en tensión con la regla vigente del Gate Pago de escalar directo).
- **Esperado (KB 13):** preguntar "en cuántos pagos" y "en pesos o dólares" y luego "su petición será derivada a la secretaria para que pueda concretar el pago". El bot NUNCA valida el monto; siempre escala a la secretaria.
- **Capa:** prompt
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-09, docs/kb-validacion-dra-2026-07-09.md [13]; .claude/CLAUDE.md (raw e4 EC-102)
- **Estado:** pendiente de decisión. Contradicción: el Gate Pago Tratamiento (2026-09-03, más reciente) escala directo sin preguntar cuántos pagos ni moneda, y el Confirmar vivo responde el canned "Recibimos su comprobante…" sin preguntas. Prevalece la regla de 3/9 y del prompt vivo; la regla KB 13 queda superada salvo que la Dra. la pida de nuevo.

### Cobertura
14 casos; 5 SIN TEST (PAG-01, 06, 12, 13, 14); los 9 restantes están cubiertos por tests/test_canned_sidecar.py y tests/test_gate_pago_tratamiento.py (PAG-03 cubre el passthrough pero no el mal ruteo de un bracket despegado).
Huecos más peligrosos: (1) PAG-01, el camino de comprobantes de punta a punta (Webhook Validator → guardado → derivación) sin test automatizado: ya falló el 100% de los entrantes; (2) PAG-06 y PAG-12, reglas que existían en prompts curados el 4/10 y que no están en el texto vivo (texto de "pagar el día de la consulta", "voy hoy" que cae en Confirmar); (3) PAG-13, Confirmar curado confirma el turno al recibir un comprobante sin esperar la verificación humana, en contra de la política de pre-reserva.

---

## router

### RTR-01 · Mariela (9/5): el Router no veía la memoria y clasificó una urgencia como consulta_general
- **Entrada/disparador:** 2026-05-09 13:02, una madre (Mariela): "esta incomoda, no come, solo liquidos".
- **Falla previa:** `Router - Clasificar Intent` no estaba conectado a `Postgres Chat Memory.ai_memory`; solo veía el último mensaje y lo mandó a consulta_general. El Sub-Agent General improvisó: "guarda la pieza, traete el DNI, venite ahora mismo, Balcarce 37 2do piso, los esperamos" un sábado con la clínica cerrada. La madre contestó "Bien, ahora salimos para la clínica". La Dra. alcanzó a apagar el bot.
- **Esperado:** el Router recibe memoria reciente (conexión `ai_memory` + `Build Router Context`, últimos 6 mensajes) y ante urgencia clara clasifica `urgencia_dolor`. Ante duda NUNCA improvisa instrucciones: la salida a General no puede contener "venite", "los esperamos", "ahora mismo", "guarda", "traete". Refactor v7: Supervisor con few-shot del incidente y OTRO (escalación safe) ante duda.
- **Capa:** nodo (conexión ai_memory / Build Router Context) + prompt + banlist (última línea)
- **Test:** SIN TEST (docs/plan-mvp.md lista "Mariela completa → cada uno clasifica URGENCIA" como test requerido, no implementado en tests/)
- **Fecha/fuente:** 2026-05-09, .claude/CLAUDE.md "Incidente clave"; BUGS #4; FIXES Round 1 #3 (raw e3 EC-25, e4 EC-1)
- **Estado:** vigente
- **Riesgo de regresión:** el Router curado (1.998 chars) ya no tiene la frase de ejemplo ni reglas anecdóticas; solo `urgencia_dolor` ("dolor dental, muela, sangrado, hinchazón, alambre/bracket… 'qué tomo'"). "Está incómoda, no come" depende de la memoria y del criterio del LLM. Verificar que la conexión `ai_memory → Router` siga viva y probar la frase con contexto.

### RTR-02 · Caso Salvador M. 19-21/8: mensaje multi-pedido (datos de registro + precio + obra social) clasificado consulta_general y el turno nunca se creó
- **Entrada/disparador:** el bot (Agendar) pidió "Para registrarlo y reservar el turno, ¿me pasa nombre completo y DNI del paciente?". Respuesta real (reporte de la Dra., 19/8): "Si, el paciente es S. M., DNI … / Cual es el valor de la consulta? / Recibe instituto de seguros?". Reproducción de test: mismo formato con paciente "Test Prueba".
- **Falla previa:** el Router lo mandó a consulta_general; el Sub-Agent General respondió solo el canned de precio y obra social. Nunca se llamó `crear_paciente_dentalink` ni `reservar_turno`, y el paciente quedó creyendo que tenía turno. La Dra. agendó a mano. Causa: la regla "EXCEPCION A LA CONTINUACION" (en medio de un flujo, pregunta canned → abandonar a consulta_general) no contemplaba que el mensaje trajera AMBAS cosas. El primer fix (solo Agendar) reprodujo el bug en vivo.
- **Esperado:** "excepción a la excepción": si el mensaje trae la info pedida (nombre+DNI, slot) JUNTO con una pregunta canned, se mantiene el intent operativo (`agendar_nuevo`). Fix en 2 capas: (a) Router; (b) la "validación de destino" del General no debe ganarle a la acción pendiente. Aserción: en un mensaje con datos + precio + obra social, intent = `agendar_nuevo`, se llama `crear_paciente_dentalink` y `reservar_turno`, y la respuesta incluye también precio/obra social. Alternativa descartada: Router multi-intent (va con el refactor Supervisor).
- **Capa:** prompt (Router + Sub-Agent General); `apply_fix_router_continuacion_multi_pedido.py` y `apply_fix_subagent_general_os_carveout.py`
- **Test:** SIN TEST (verificado E2E manual en 3 turnos reales con cita real de test luego anulada; tests/test_e2e_bateria.py no lo incluye)
- **Fecha/fuente:** 2026-08-21, DEC "Un bug de clasificación de intent multi-pedido…"; BKL Done 2026-08-21 (raw e2 EC-9, e3 EC-26, e4 EC-11)
- **Estado:** vigente (la regla), pero el texto que la implementaba fue eliminado por la curación del 4/10
- **Riesgo de regresión:** el Router curado solo tiene la "REGLA DE CONTINUIDAD DE FLUJO" genérica (sin la excepción a la excepción) y lista precios/obra social en consulta_general. El Sub-Agent Agendar curado no tiene instrucción de responder info canned/obra social. El Canned Sidecar anexa solo alias/precio, no obra social. Verificar con la frase del caso que se cree el paciente y la cita.

### RTR-03 · Julieta (2/10): "qué posibilidad hay de cambiar el turno para la tarde?" clasificado consulta_general y bot en silencio total
- **Entrada/disparador:** exec 292455, 09:03 ART, paciente J. L.: "Buenos días quería consultar que posibilidad hay de cambiar el turno para el horario de la tarde?"
- **Falla previa:** el Router LLM lo clasificó `consulta_general` por la regla `0. PREGUNTA != ACCION` (vio el "?" y "consultar"). El Sub-Agent General entendió que era una acción sobre turno y devolvió `[NO_REPLY]`; `Tiene respuesta?` tomó la rama False (`PG - Delete NO_REPLY` → `Descartar [NO_REPLY]`). 0 mensajes salientes.
- **Esperado:** cualquier verbo de reprogramación/cambio (`cambiar`, `reprogramar`, `mover`, `pasar`, `posponer`…) junto con un término de agenda (`turno`, `cita`, `horario`, `tarde`, `mañana`, `fecha`) fuerza SIEMPRE `intent = cancelar_o_reprogramar`, aunque tenga "?" o palabras de consulta. Y red anti-silencio en `Fallback Output`: si un agente devuelve vacío o `[NO_REPLY]` y el mensaje NO es un cierre puro (ok, gracias, dale, emoji), se envía el canned "Hola! Ya le transmito su consulta a la secretaria para que le responda en su horario de atención. ¡Muchas gracias!" en vez de silenciar.
- **Capa:** nodo (override determinístico en `Parse Intent` + `Fallback Output`) + prompt (reglas 0 y 3 del Router suavizadas)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-10-02, current-state "Fix: Julieta… y red anti-silencio [NO_REPLY]" (`scripts/apply_fix_reprogramar_noreply.py`) (raw e1 EC-1)
- **Estado:** vigente
- **Riesgo de regresión:** el prompt del Router fue curado el 4/10 (después del fix) y hoy lista "¿se puede cambiar para la tarde?", "¿qué posibilidad hay de moverlo?" en cancelar_o_reprogramar, así que la regla de prompt sobrevivió. El override de `Parse Intent` no está en prompt; verificar que sigue en el código. El override puede dar falsos positivos con "pasar" + "mañana" (p. ej. "puedo pasar mañana a abonar").

### RTR-04 · Continuación de urgencia con video: el Router no tiene reglas para seguimiento de urgencia y estado Redis vencido
- **Entrada/disparador:** el paciente responde tras un video del triaje: "no me sirvió", "no tengo cera", "y si no tengo pinza?", "listo gracias ya me puse la cera", incluso cuando el estado Redis `triaje:{phone}` ya venció.
- **Falla previa:** (análisis 4/9) el Router tiene reglas de continuación para agendar/cancelar/confirmar y NINGUNA para urgencia; con "ante DUDA → consulta_general" y "cierres/post-escalación → consulta_general", esos mensajes caen en Sub-Agent General (KB + LLM o `[NO_REPLY]`) en vez de re-escalar o cerrar.
- **Esperado:** estado determinístico del triaje en Redis (`triaje:{phone}`) evaluado ANTES del Router (Triaje: Redis GET estado → ¿Seguimiento?). 2ª capa: reconstruir el estado desde el ctx del Router (fila "BOT: [VIDEO ENVIADO — tipo, Opción N]") y un párrafo "CONTINUACION DE URGENCIA CON VIDEO" en el Router (que vive solo en n8n, sin partial).
- **Capa:** gate (nodos Triaje) + nodo (fila en memoria) + prompt (párrafo del Router)
- **Test:** tests/test_triaje_nodos.js ("seg video1: …", "ctx reconstruye estado")
- **Fecha/fuente:** 2026-09-04, docs/triaje-fase2-analisis/mapeo-read_router.md §5.3 y RISKS; docs/triaje-fase2-diseno-2026-09-04.md §3-§4; current-state "Fase 2 (piloto en el v6)" (raw e1 EC-66, e4 EC-3)
- **Estado:** vigente (capa gate); la capa prompt quedó superada por la curación del 4/10
- **Riesgo de regresión:** el Router curado eliminó el párrafo "CONTINUACION DE URGENCIA CON VIDEO". Con estado Redis vencido, la 2ª capa solo existe como reconstrucción por ctx; verificar que sin ese párrafo un seguimiento ("no me sirvió") con estado vencido no caiga en General.

### RTR-05 · "Y si no tengo pinza?" cae en Sub-Agent General y arriesga consejo operativo (misma clase que Mariela)
- **Entrada/disparador:** "y si no tengo pinza?" tras el video del triaje.
- **Falla previa:** Regla 0 (PREGUNTA != ACCION) → consulta_general → General PASO 3 → `buscar_conocimiento` → el LLM parafrasea o improvisa ("puede usar una pinza de cejas limpia", "empuje el alambre con la goma de un lápiz"). El Banlist no cubría "use/pruebe/coloque/empuje/pinza/cera".
- **Esperado:** con estado de triaje vigente "no tengo pinza" cuenta como "no sirvió" → Opción 2 / escalar; nunca llega a General. La respuesta NO contiene instrucciones operativas.
- **Capa:** gate (`regex_no_sirvio` incluye "no tengo")
- **Test:** tests/test_triaje_nodos.js ("seg video1: y si no tengo pinza?")
- **Fecha/fuente:** 2026-09-04, mapeo-read_router.md §5.2 y RISKS (raw e4 EC-7)
- **Estado:** vigente. La regla 0 PREGUNTA != ACCION ya no existe (RTR-14), lo que baja el riesgo en el Router. El hueco de Banlist (verbos operativos) depende de test_triaje_textos_banlist.py; verificar.

### RTR-06 · "No me sirvió" tras el video se clasifica consulta_general
- **Entrada/disparador:** "no me sirvió".
- **Falla previa:** Pre-filtro Cierre `default_pass`; Router → consulta_general ("reclamos vagos", "ante duda"); General puede escalar por queja, `[NO_REPLY]` o `buscar_conocimiento`. Si fuera a Urgencia, su VALIDACION DE DESTINO ("sin señales claras → [NO_REPLY]") produce silencio en vez de re-escalar.
- **Esperado:** con estado `video_enviado` vigente, "no me sirvió" manda la Opción 2 (video de la pinza) sin LLM; si ya se mandó la Opción 2, escala.
- **Capa:** gate (`Triaje: Evaluar`, `regex_no_sirvio`)
- **Test:** tests/test_triaje_nodos.js ("seg video1: no sirvió -> opción 2")
- **Fecha/fuente:** 2026-09-04, mapeo-read_router.md §5.2 (raw e4 EC-4)
- **Estado:** vigente (el Sub-Agent Urgencia con VALIDACION DE DESTINO es un nodo muerto)

### RTR-07 · "Sigue pinchando" llega a urgencia_dolor solo por inferencia del LLM
- **Entrada/disparador:** "sigue pinchando", "no me sirvió, sigue pinchando", "me sigue lastimando el cachete".
- **Falla previa:** "pincha" no estaba en la regla 1 del Router; el Pre-filtro lo etiquetaba `reason:'urgencia'` pero ese campo no se usaba aguas abajo.
- **Esperado:** debe ir a Urgencia (re-escalar) de forma determinística por el estado Redis del triaje, no por inferencia del ctx.
- **Capa:** gate (estado Redis del triaje)
- **Test:** tests/test_triaje_nodos.js ("seg video1: me sigue lastimando el cachete", "no me sirvió, sigue pinchando")
- **Fecha/fuente:** 2026-09-04, mapeo-read_router.md §5.2; mapeo-read_urgencia_path.md §6 (raw e4 EC-5)
- **Estado:** vigente. El Router curado ya lista "alambre/bracket salido o que pincha" en urgencia_dolor, pero igual depende del gate para el seguimiento.

### RTR-08 · "Listo gracias ya me puse la cera" termina en [NO_REPLY] o escala en falso
- **Entrada/disparador:** "listo gracias ya me puse la cera".
- **Falla previa:** Router → consulta_general (cierre) → Sub-Agent General → `[NO_REPLY]` → `PG - Delete NO_REPLY`, y se pierde la señal "resuelto con video". Si fuera a Urgencia, escalaba en falso (label humano + grupo despertado).
- **Esperado:** cerrar con `texto_cierre` canned, limpiar el estado y marcar `resuelto_at` en `triaje_urgencias_log`. Evaluar CIERRE antes que las keywords de urgencia (cera/pinza): no hay label humano ni notificación al grupo.
- **Capa:** gate (`Triaje: Evaluar/Decidir`) + nodo (log)
- **Test:** tests/test_triaje_nodos.js ("cierre con cera -> cerrar (no escalar)", "cierre con pinza -> cerrar")
- **Fecha/fuente:** 2026-09-04, mapeo-read_router.md §5.2; docs/triaje-fase2-analisis/jueces.md MUST_FIX (cierre antes que URG_KW) (raw e4 EC-6)
- **Estado:** vigente

### RTR-09 · "Me duele mucho igual" tras el video debe escalar (caso a preservar)
- **Entrada/disparador:** "me duele mucho igual"; "ok pero me duele mucho igual".
- **Falla previa:** n/a (sale bien por keyword "dolor"; documentado como caso a preservar).
- **Esperado:** no se cierra ni se manda Opción 2: escala (menciona síntoma sin resolver; red flag "dolor intenso").
- **Capa:** gate
- **Test:** tests/test_triaje_nodos.js ("'ok' + duele -> escalar (no cierra)")
- **Fecha/fuente:** 2026-09-04, mapeo-read_router.md §5.2 (raw e4 EC-8)
- **Estado:** vigente

### RTR-10 · Aceptación de slot ("dale ese", "buenísimo para ese día") debe seguir en agendar_nuevo
- **Entrada/disparador:** tras la oferta de Agendar: "dale", "ese mismo", "ese me sirve", "el primero", "buenisimo para ese dia", "joya", emoji 👍/✅/🙏.
- **Falla previa:** se clasificaban como consulta_general y el turno no se reservaba.
- **Esperado:** si el último AI fue Sub-Agent Agendar y la respuesta no es interrogativa → `agendar_nuevo`. La reserva se ejecuta con read-back previo.
- **Capa:** prompt (Router; REGLA CRITICA 2026-06-03)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-03, mapeo-read_router.md §1.1 (raw e4 EC-14)
- **Estado:** vigente
- **Riesgo de regresión:** el Router curado lista "dale" y los emoji 👍/✅/🙏 en `confirmar_post_recordatorio` Y "dale ese", "el primero" en `agendar_nuevo`. La desambiguación depende solo de la REGLA DE CONTINUIDAD genérica. Verificar que "dale" tras una oferta de Agendar vaya a agendar_nuevo y no a Confirmar.

### RTR-11 · Incidente 27/05: preguntas de disponibilidad dentro del flujo agendar clasificadas consulta_general
- **Entrada/disparador:** el AI previo (Agendar) ofreció "Los próximos cupos: 4 de junio…" y el paciente dijo "El 30 de junio?" / "O digame que fechas tiene disponibles por la tarde?".
- **Falla previa:** clasificadas consulta_general (incidente 27/05 18:26); el bot además afirmó "para el 30/06 no tengo" sin haber consultado.
- **Esperado:** son continuación → `agendar_nuevo`. Solo cambia a consulta_general si la pregunta es de INFO CANNED (alias, horarios de clínica, dirección, precio, forma de pago). El agente consulta `buscar_horarios` antes de afirmar disponibilidad.
- **Capa:** prompt (Router)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-05-27, mapeo-read_router.md §1.1 (raw e4 EC-13)
- **Estado:** vigente
- **Riesgo de regresión:** la regla de continuidad curada habla de "aportando esa información"; una pregunta de disponibilidad no es información aportada. Verificar la clasificación de "El 30 de junio?" tras un bloque de turnos.

### RTR-12 · Clarificación sobre lo que el bot acaba de pedir no debe cambiar de intent
- **Entrada/disparador:** bot (Agendar): "Con este número tengo registrada a más de una persona. ¿Para quién es el turno?" y paciente: "A que personas?" (también "que opciones?", "cuales son?", "no entiendo").
- **Falla previa:** mandada a consulta_general; el General no tenía cómo responder y terminaba escalando.
- **Esperado:** mantener el intent del flow activo (`agendar_nuevo`); el sub-agent operativo lista las fichas devueltas por `buscar_paciente_dentalink`.
- **Capa:** prompt (Router + Agendar PASO 1 2.a)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-01 ("Ejemplo real (1/6)"), mapeo-read_router.md §1.1; prompts/v6_partials/agendar_tools.md (raw e4 EC-12)
- **Estado:** vigente
- **Riesgo de regresión:** el Agendar curado dice "pregunte a nombre de quién es el turno o pida el DNI" pero no "listá las fichas" y el Router curado no tiene regla de clarificación. Verificar.

### RTR-13 · Reprogramación interrogativa ("¿puedo cambiar el turno?") sin regla en el Router (gap 8)
- **Entrada/disparador:** "¿puedo cambiar el turno?", "¿puedo pasar el turno a otro día?", "se puede mover?".
- **Falla previa:** Regla 0 del Router (pregunta → consulta_general) y contradicción interna entre Regla 0 e Intent 5; el paciente nunca entra a `cancelar_o_reprogramar`. Además el Sub-Agent General respondía "Ahora le paso los turnos disponibles" y se callaba (no tiene `buscar_horarios` conectada): promesa de un mensaje que nunca llega.
- **Esperado:** regla en el Router para reprogramación interrogativa; General, si recibe el caso, responde "Confirmame que querés reprogramar tu turno y te paso los turnos que tenemos disponibles" sin prometer entrega inmediata y sin preguntar día/franja.
- **Capa:** prompt (Router y Sub-Agent General)
- **Test:** tests/test_turnos_formato.js (check "Sub-Agent General ya no promete un mensaje que nunca llega"). La regla del Router no está testeada.
- **Fecha/fuente:** 2026-07-06 (gap 8), docs/sesion-2026-07-06-precio-lid-reprogramacion.md §3; 2026-09-07 (defecto 6), docs/turnos-formato-2026-09-07.md §8 (raw e3 EC-27, e4 EC-9)
- **Estado:** superado por RTR-03 en lo que respecta al Router (override en `Parse Intent` y regla 3 del Router vigente lista "¿puedo cambiar el turno?"). Permanece vigente la parte del General (no prometer entrega).
- **Riesgo de regresión:** el General curado no contiene la promesa "Ahora le paso…", pero tampoco el texto "Confirmame que querés reprogramar…"; verificar que no prometa turnos sin herramienta.

### RTR-14 · Prompt del Router con contradicciones por parches acumulados
- **Entrada/disparador:** el prompt de `Router - Clasificar Intent` acumuló ~19.400 caracteres (191 líneas) de parches desde mayo (casos Mariela, Catalina, Valentino, Salvador, Round 13/14).
- **Falla previa:** contradicciones severas como `PREGUNTA != ACCION` (causa raíz del cuelgue de Julieta, RTR-03), párrafos redundantes, más latencia y fallas de clasificación.
- **Esperado:** Router mínimo de 5 intents (`urgencia_dolor`, `confirmar_post_recordatorio`, `cancelar_o_reprogramar`, `agendar_nuevo`, `consulta_general`) con regla de continuidad y salida de UNA palabra exacta del intent. NO existe la regla `PREGUNTA != ACCION`. Tamaño 1.998 chars / 26 líneas.
- **Capa:** prompt (`scripts/apply_curar_router_prompt.py`)
- **Test:** SIN TEST (no hay suite de clasificación del Router tras la curación)
- **Fecha/fuente:** 2026-10-04, current-state "Curación del Router: reducción del 90%" (raw e1 EC-3)
- **Estado:** vigente. Esta curación supera las reglas de Router de RTR-02, 04, 10-12, 15, 17-21 y 23 que dependían de párrafos eliminados (ver el "Riesgo de regresión" de cada caso).

### RTR-15 · Router y Confirmar se contradicen sobre quién responde la info canned
- **Entrada/disparador:** multi-intent (acción + pregunta canned) clasificado `confirmar_post_recordatorio`.
- **Falla previa:** el fix del 21/8 le dice al Router "mantené el intent operativo (agendar/cancelar/confirmar_post_recordatorio): el sub-agent operativo ya sabe responder la info canned ADEMÁS de ejecutar la acción", pero el prompt vivo de Confirmar decía lo opuesto; cada capa creía que la otra era dueña del alias. Misma clase que Salvador (RTR-02), cuyo fix solo tocó Agendar/General.
- **Esperado:** decisión estructural: la info canned se responde en una capa determinística de salida (`Canned Sidecar`, PAG-04), no en el prompt de cada sub-agent. Confirmar, Cancelar, Urgencia, el flow de comprobante y los 3 sub-agents del refactor futuro la heredan.
- **Capa:** nodo (`Canned Sidecar`) + prompt
- **Test:** SIN TEST (el Sidecar está testeado; la contradicción de capas no)
- **Fecha/fuente:** 2026-09-02, current-state "Bug real… pedido de alias post-confirmación" (raw e1 EC-77)
- **Estado:** vigente (la decisión). La frase contradictoria del Router fue eliminada por la curación del 4/10 (superado por RTR-14); el Sidecar sigue siendo la única garantía.
- **Riesgo de regresión:** el Sidecar cubre alias/precio, no obra social ni horarios; verificar qué capa responde la obra social cuando el mensaje es operativo.

### RTR-16 · Parse Intent por substring: salida con dos intents gana el primero de la lista fija
- **Entrada/disparador:** el Router (gpt-5-mini, sin JSON) devuelve texto libre tipo "urgencia_dolor / consulta_general".
- **Falla previa:** (riesgo documentado) `Parse Intent` usa `includes` en orden fijo confirmar > cancelar > urgencia > agendar > general; un intent nuevo cuyo nombre contenga el substring de otro rompe el mapeo y los passthrough de Canned Sidecar y Gate Pago, que comparan el string exacto `'urgencia_dolor'`.
- **Esperado:** nombrar intents sin colisión de substring; agregarlos a `valid` y al Switch. Plan v7: Supervisor con JSON forzado + validador (fuera del enum → OTRO). Con salida de dos intents, determinístico y documentado cuál gana.
- **Capa:** nodo (Parse Intent)
- **Test:** SIN TEST (los tests de Sidecar y Gate Pago mockean `Parse Intent`)
- **Fecha/fuente:** 2026-09-04, mapeo-read_router.md RISKS; docs/plan-mvp.md (raw e4 EC-19)
- **Estado:** vigente
- **Riesgo de regresión:** el Router curado exige "una sola palabra exacta" (mitiga la salida con dos intents). Con el override de Julieta (RTR-03) hay dos lógicas determinísticas en el mismo nodo; verificar el orden.

### RTR-17 · Comprobante de pago tiene prioridad sobre la continuación de flujo
- **Entrada/disparador:** `[DOCUMENTO]`/`[IMAGEN]` con "TIPO: COMPROBANTE", "comprobante", "transferencia", "monto", "BBVA", "Macro", "alias", "ARS $", incluso viniendo de un flujo agendar o cancelar.
- **Falla previa:** n/a (regla del prompt).
- **Esperado:** siempre `confirmar_post_recordatorio` (lo maneja Sub-Agent Confirmar, que escala a la secretaria). El post-reserva de Agendar pide enviar el comprobante, por lo que el comprobante llega justo después del flujo agendar.
- **Capa:** prompt (Router)
- **Test:** SIN TEST
- **Fecha/fuente:** prompt vivo, mapeo-read_router.md §1.1 (2026-09-04) (raw e4 EC-17)
- **Estado:** vigente
- **Riesgo de regresión:** el Router curado dice "envía comprobante de pago/transferencia bancaria" en `confirmar_post_recordatorio`, pero perdió "tiene prioridad sobre la continuación de flujo" y los marcadores `TIPO: COMPROBANTE`. Justo tras el post-reserva de Agendar, la REGLA DE CONTINUIDAD podría ganarle. Verificar.

### RTR-18 · Aviso de llegada ("estoy llegando 🙏") no es confirmación ni cancelación: silencio
- **Entrada/disparador:** "estoy llegando", "ya llegué", "estoy a dos cuadras", "estoy en la puerta", "subiendo", "en camino" (caso Catalina).
- **Falla previa:** se leía como confirmar/cancelar, sobre todo con emoji 🙏/👍.
- **Esperado:** consulta_general → Sub-Agent General → `[NO_REPLY]` (silencio, sin "te esperamos"). Excepción: "voy", "ahí estaré" en respuesta a un recordatorio = confirmación. Si hay dolor/urgencia, urgencia manda.
- **Capa:** prompt (Router regla 1.5 + header_common AVISOS PRE-LLEGADA)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-19 (pedido Dra., caso Catalina), mapeo-read_router.md §1.1; prompts/v6_partials/header_common.md (raw e4 EC-15)
- **Estado:** vigente
- **Riesgo de regresión:** el General curado dice "responde brevemente confirmando o devolvé `[NO_REPLY]`". Esto contradice el pedido de silencio: confirmando podría aparecer "los esperamos", que el Banlist prohíbe. Confirmar y Agendar curados sí dicen `[NO_REPLY]`. Verificar y alinear.

### RTR-19 · Emoji solo (👍, 👌, ✅, 🙏, ❤️…) en contexto post-recordatorio = confirmación
- **Entrada/disparador:** el paciente responde solo "👍" al recordatorio (feedback de la Dra.: "el pulgar arriba también es válido como confirmación, no lo está confirmando a esos").
- **Falla previa:** el bot no tomaba el pulgar arriba como confirmación.
- **Esperado:** en contexto post-recordatorio, emojis afirmativos solos → `confirmar_post_recordatorio` y se ejecuta `confirmar_turno`. Sin acción pendiente son cierres (silencio, RTR-20). Ante duda en contexto post-recordatorio, confirmar.
- **Capa:** prompt (Router regla 2) + nodo (parseo de input)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-03, docs/Asiri - Feedback Raquel 03-06.pdf punto 4; mapeo-read_router.md §1.1 (raw e4 EC-16)
- **Estado:** vigente
- **Riesgo de regresión:** el Router curado lista 👍/✅/🙏 como confirmación siempre, sin la condición "post-recordatorio"; el Pre-filtro Cierre puede devolver `[NO_REPLY]` antes. Verificar el orden Pre-filtro → Router.

### RTR-20 · Emoji solo / "gracias" respondido como confirmación de turno ("Buenísimo, te esperamos el martes 5 a las 8:40")
- **Entrada/disparador:** un emoji ❤️ solo, sin acción pendiente.
- **Falla previa:** el bot respondió "Buenisimo, te esperamos el martes 5 a las 8:40" (gpt-5-mini no respeta 100% las reglas "no respondas a cierres/emojis").
- **Esperado:** pre-filtro determinístico antes del LLM (`Pre-filtro Cierre`: `emoji_only`, `solo_gracias`, etc.; resuelve 60-70% de los casos obvios sin LLM) → `[NO_REPLY]`. Sin "te esperamos".
- **Capa:** nodo (Pre-filtro Cierre, regex)
- **Test:** SIN TEST ("shadow validado", sin archivo en el repo)
- **Fecha/fuente:** ~2026-05 (shadow), BUGS #16 (raw e3 EC-30)
- **Estado:** vigente. Tensión con RTR-19 (mismo emoji = confirmación en contexto post-recordatorio): el orden de evaluación decide.
- **Riesgo de regresión:** el General curado perdió la regla CIERRES CONVERSACIONALES (devolver `[NO_REPLY]` ante "ok/gracias/emoji"); depende solo del Pre-filtro y de la red anti-silencio, que deja pasar los cierres puros.

### RTR-21 · "Tengo turno el viernes" (afirmativo) vs "tengo turno el viernes?" (pregunta)
- **Entrada/disparador:** "tengo turno el viernes" vs "tengo turno el viernes?" / "¿tengo turno?".
- **Falla previa:** n/a (discriminación documentada).
- **Esperado:** el afirmativo sin "?" puede ser confirmar; con "?" o tono pregunta → consulta de turno propio (`consulta_info`, sin ejecutar acción: el sub-WF cancelar lo trata como `consulta_info` o General usa `ver_turnos_paciente`). Nunca clasificar una pregunta como acción ejecutable (no se llama `confirmar_turno` ni `cancelar_turno`).
- **Capa:** prompt (Router regla 0, ya eliminada)
- **Test:** SIN TEST
- **Fecha/fuente:** prompt vivo, mapeo-read_router.md §1.1 (2026-09-04) (raw e4 EC-18)
- **Estado:** superado por RTR-14 (la regla PREGUNTA != ACCION fue eliminada el 4/10 por ser la causa raíz de RTR-03). Queda pendiente de decisión cómo se discrimina sin esa regla.
- **Riesgo de regresión:** no hay regla de pregunta vs afirmación; "tengo turno el viernes?" podría ir a Confirmar y ejecutar `confirmar_turno`. Verificar.

### RTR-22 · Regla de oro: ante duda, consulta_general (el bot no es recepcionista)
- **Entrada/disparador:** saludos sueltos ("hola", "buenas tardes"), conversacionales ("como va?"), "buenas $9100", "tengo 30", reclamos vagos, mensajes random.
- **Falla previa:** n/a (regla del prompt).
- **Esperado:** el bot solo entra en 5 funciones (agendar, confirmar/cancelar/reprogramar, comprobante, urgencia concreta, info puntual). Todo lo demás → consulta_general, donde General devuelve `[NO_REPLY]` (o, desde el 2/10, el canned de escalación si no es un cierre puro).
- **Capa:** prompt
- **Test:** SIN TEST
- **Fecha/fuente:** prompt vivo citado en docs/triaje-fase2-analisis/mapeo-read_router.md §1.1 (2026-09-04) (raw e4 EC-2)
- **Estado:** vigente. Contradicción menor: este esperado ("General devuelve `[NO_REPLY]`") fue modificado por la red anti-silencio del 2/10 (RTR-03). Se queda con la más reciente.
- **Riesgo de regresión:** el Router curado conserva "Si el mensaje es ambiguo… clasificar acá (consulta_general)". Verificar que el General no responda por reclamos vagos.

### RTR-23 · "Vuelvo en X meses" debería ser agendar_nuevo, y el fix de `apply_fix_router_reagendar.py` no está en el Router vivo
- **Entrada/disparador:** el paciente dice que vuelve en X meses (reagendar).
- **Falla previa:** `scripts/apply_fix_router_reagendar.py` nunca se aplicó o fue pisado por la reescritura de reglas del 03/06; el Router vivo no tiene la regla.
- **Esperado:** clasificar como `agendar_nuevo` (reagendar). Verificar el workflow vivo y reaplicar si falta.
- **Capa:** prompt (Router)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06 (gap 9), docs/sesion-2026-07-06-precio-lid-reprogramacion.md §3; open-questions (sin fecha) (raw e3 EC-28, e4 EC-10)
- **Estado:** pendiente de decisión. El Router vivo al 4/10 NO contiene la regla (confirmado en live_prompts.md).

### RTR-24 · Presentación obligatoria de Asiri al inicio de toda conversación nueva
- **Entrada/disparador:** conversaciones nuevas por turno / precio / obra social. Raquel: "Asiri sigue sin presentarse… si no los pacientes se vuelven locos".
- **Falla previa:** en varios chats el bot respondía directo sin decir quién es (03/06).
- **Esperado:** "Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel 🤗" en: primera respuesta, saludo del paciente, último AI fue el recordatorio del cron, pregunta "¿con quién hablo?/¿sos robot?". Ante duda, presentarse. Ningún sub-agent responde sin la presentación en el primer turno.
- **Capa:** prompt (header_common IDENTIFICACION)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-03, docs/Asiri - Feedback Raquel 03-06.pdf punto 1; prompts/v6_partials/header_common.md (raw e4 EC-20)
- **Estado:** vigente. La IDENTIFICACION completa solo sobrevive en el nodo muerto Sub-Agent Urgencia.
- **Riesgo de regresión:** los prompts curados de Agendar y Confirmar no contienen la regla de presentación; General solo se presenta ante un saludo solo. La Dra. dijo "insiste" (no negociable). Verificar.

### RTR-25 · Onboarding redundante en continuaciones ("Hola, soy la asistente virtual…" a mitad de flujo)
- **Entrada/disparador:** continuación de un flujo en curso.
- **Falla previa:** el bot se re-presentaba; la lógica IF "primer mensaje" no preservaba estado.
- **Esperado:** prohibido onboarding si la memoria tiene menos de 24 h; excepción: más de 12 h sin interacción + saludo del paciente. Tono: "Soy la asistente virtual de la Dra. Raquel", profesional cordial, sin imitar a la secretaria (el tono "Iri" confundía).
- **Capa:** prompt (5 sub-agents)
- **Test:** SIN TEST ("shadow + sintético", sin archivo)
- **Fecha/fuente:** shadow 2026-05-04/09, BUGS #20; .claude/project-context.md "Tono" (raw e3 EC-33)
- **Estado:** vigente. Tensión con RTR-24 (que exige presentarse ante la duda); el criterio de las 24/12 h aplica a la presentación mid-flow.
- **Riesgo de regresión:** los prompts curados no contienen el umbral de 24/12 h. Verificar.

### RTR-26 · R0 demasiado agresivo en saludos cold: sub-agents devuelven `[NO_REPLY]` o escalan
- **Entrada/disparador:** tests sintéticos E2/E3/E5 (saludo primera, 0/5): "hola/buenas" sin memoria de 24 h.
- **Falla previa:** los sub-agents respondían `[NO_REPLY]` o escalaban en vez de saludar y ofrecer agendar ("si dudas escala" atajaba de más).
- **Esperado:** EXCEPCION SALUDOS COLD: sin mensajes en 24 h y solo saludo → UNA línea corta saludando + invitar a agendar. NO `[NO_REPLY]`, NO escalar.
- **Capa:** prompt (R0 suavizado)
- **Test:** SIN TEST en el repo (batería externa `C:/Users/Lucas/.claude/n8n_backups/test_100_pre_prod.py`, fuera del repo: 82/100 tras Round 2, objetivo 95+)
- **Fecha/fuente:** 2026-05-12, BUGS "No trackeados"; FIXES Round 2; PEND §1.2 (raw e3 EC-29)
- **Estado:** vigente. Contradicción de redacción: 05/12 sugiere "¿Queres agendar un turno?"; el General vivo (4/10) dice "¡Hola! Soy Asiri, la secretaria virtual de la Dra. Raquel 🤗 ¿En qué puedo ayudarte?" y "NUNCA escalar un saludo solo". Se queda con el texto vivo.

### RTR-27 · "Gracias" disparaba información no solicitada
- **Entrada/disparador:** "gracias" y "a las 9 gracias".
- **Falla previa:** disparaba info de pago/horarios; `termina_gracias` daba falsos positivos con "a las 9 gracias".
- **Esperado:** `solo_gracias` por match exacto → `[NO_REPLY]`; `termina_gracias` excluye mensajes con números ("a las 9 gracias" sigue al flujo normal).
- **Capa:** nodo (Pre-filtro Cierre)
- **Test:** SIN TEST en el repo (shadow + sintético)
- **Fecha/fuente:** shadow 2026-05-04/09, BUGS #21 (raw e3 EC-31)
- **Estado:** vigente

### RTR-28 · Autoresponders externos (otras clínicas) conversando con el bot
- **Entrada/disparador:** respuestas automáticas de otras clínicas (Omar Dental, Sil Odonto): "respuesta automática", "gracias por comunicarte con", "a la brevedad", horarios + días.
- **Falla previa:** el bot conversaba con ellos: gasto de tokens, memoria sucia, exposición B2B.
- **Esperado:** regex en `Pre-filtro Cierre` → `[NO_REPLY]` (reason `autoresponder_externo`). No se escribe en memoria ni se responde.
- **Capa:** nodo (regex)
- **Test:** SIN TEST en el repo (shadow + sintético, 7 categorías al 100% incl. autoresponder y B2B)
- **Fecha/fuente:** shadow 2026-05-04/09, BUGS #19 (raw e3 EC-32)
- **Estado:** vigente

### RTR-29 · Pre-filtro Cierre: `urgenciaWords` es solo una etiqueta y no incluye "cera", contención ni alineador
- **Entrada/disparador:** "listo, ya me puse la cera"; contención rota; Invisalign.
- **Falla previa:** `urgenciaWords` (substring) marca `reason:'urgencia'` pero ese campo no influye en el ruteo; 'cera', 'contención', 'alineador' no están. El Router tampoco lista 'pincha'/'contención'/'Invisalign' (el Router curado sí lista "que pincha"). Los sub-temas frecuentes dependen del criterio semántico del LLM.
- **Esperado:** ampliar con los tipos de triaje; el estado del triaje (Redis) manda sobre la heurística. Una contención rota o un alineador roto va a `urgencia_dolor`/Triaje, no a General.
- **Capa:** nodo (Pre-filtro Cierre) / prompt
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-04, mapeo-read_urgencia_path.md RISKS; mapeo-read_router.md (raw e4 EC-21)
- **Estado:** pendiente de decisión

### RTR-30 · Tools con descripción "precios/presupuestos" empujaban a escalar precios
- **Entrada/disparador:** consulta de precio.
- **Falla previa:** la description de `escalar_a_secretaria` decía "consultas de precios/presupuestos" y contradecía al prompt ("usa precios LITERAL del header").
- **Esperado:** description reescrita (270 → 708 chars): escalar solo urgencia, queja, obra social, o fuera de las 4 funciones; precio/horario/dirección/alias = canned (no se llama `escalar_a_secretaria` ante una consulta de precio).
- **Capa:** prompt (tool description)
- **Test:** SIN TEST ("sin shadow real")
- **Fecha/fuente:** 2026-05-09 (detectado), 2026-05-12 (aplicado), BUGS #23; FIXES Round 2 #8 (raw e3 EC-34)
- **Estado:** vigente
- **Riesgo de regresión:** el General curado dice escalar ante "pedidos de presupuesto a medida"; si la description de la tool aún dice "precios/presupuestos", reaparece la contradicción. Verificar la description viva.

### Cobertura
30 casos; 23 SIN TEST, 1 con test parcial (RTR-13) y 6 cubiertos (RTR-04 a 09, todos del gate Redis del triaje en tests/test_triaje_nodos.js).
Huecos más peligrosos: (1) RTR-01/RTR-14: no hay ninguna suite de clasificación del Router tras la curación del 4/10 (5 intents, urgencia con memoria tipo Mariela), con la frase del incidente solo en un plan; (2) RTR-02/RTR-17: multi-pedido (datos+precio+obra social) y comprobante justo después del post-reserva dependen ahora solo de la "REGLA DE CONTINUIDAD" genérica; (3) RTR-03/RTR-16: el override determinístico de `Parse Intent` (y su orden frente al `includes` por substring) y la red anti-silencio de `Fallback Output` no tienen ningún test, y es la única barrera contra el visto sin respuesta.
