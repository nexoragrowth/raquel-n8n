# Catálogo de edge cases — flujos agendar y confirmar

Consolidado el 2026-10-04 desde `flow_agendar.md` (41 casos crudos) y `flow_confirmar.md` (12 casos crudos). Los IDs crudos "EC-n" se repiten entre extractores (e1..e4); en "Fecha/fuente" cada origen se cita como `eN/EC-n`. Estado del workflow vivo verificado el 2026-10-04: v6 ACTIVO; los nodos "Sub-Agent Cancelar" y "Sub-Agent Urgencia" dentro del v6 son MUERTOS (cancelar_o_reprogramar va al sub-workflow determinístico `5cAWJxiWJ50hxEq3`; urgencia_dolor va al flujo Triaje). Los prompts de Router, Agendar, Confirmar y General fueron curados el 2026-10-04 (~90% menos). Los fragmentos de prompt de Agendar/General/Cancelar que cita este catálogo pueden estar hoy solo en el sub-WF (código de nodo) o haberse perdido en la curación; cada caso lo indica.

Hallazgos transversales de la comparación contra `live_prompts.md`:
- El bloque "DIA DE LA SEMANA (nunca calcules)" y el bloque "VALIDACION DE DESTINO" solo aparecen hoy dentro del prompt del nodo muerto Sub-Agent Urgencia; no están en los prompts curados de Agendar ni de Confirmar.
- Los tests `tests/test_nodes_eval.py` y `tests/test_reprogramar_franja.py` codifican la lógica VIEJA de Step 5 / Step 6b-out (filtrar por franja, `tieneFranjaTexto`, `hora_minima_detectada`); contradicen la reescritura del 2026-09-07 y probablemente están obsoletos.

---

## agendar

### AGE-01 · Reserva sin confirmación explícita ni pago
- **Entrada/disparador:** paciente eligió una fecha y preguntó el precio de un frenillo ("valor $50.000"); nunca dijo "sí, reservá" ni mandó comprobante.
- **Falla previa:** el bot reservó en Dentalink igual.
- **Esperado:** `reservar_turno` NO se llama sin confirmación afirmativa explícita posterior al read-back; para tratamientos con seña/pago, no se reserva hasta comprobante (o se deja como "pre-reserva"). Un turno agendado tras solo "elegir fecha + preguntar precio" es falla.
- **Capa:** prompt (read-back PASO 3 vivo); gate determinístico pendiente (marcado SENSIBLE)
- **Test:** SIN TEST (relacionado, no cubre: `tests/test_gate_pago_tratamiento.py`)
- **Fecha/fuente:** 2026-07-19 · e3/EC-49 (BKL "P1 BUG agendar prematuro")
- **Estado:** pendiente de decisión (gate determinístico sin implementar; la política tratamientos-con-seña vs "PRE-reservado, pago hasta 72 hs" de AGE-24 no está unificada)
- **Riesgo de regresión:** el prompt vivo conserva read-back y "esperá su confirmación afirmativa", pero no distingue consulta de tratamiento con seña. Verificar que un "cuánto sale?" tras elegir horario no dispare `reservar_turno`.

### AGE-02 · El bot nunca agenda turnos de urgencia
- **Entrada/disparador:** "se me salió un bracket / se me soltó un alambre / se me salió un tubo" pidiendo turno.
- **Falla previa:** n/a (política de la Dra.); antes (KB 5) preguntaba "¿Siente alguna molestia en esa parte?" y luego "No se preocupe, estaremos informando a la secretaria…".
- **Esperado:** NUNCA agendar turno de URGENCIA (punto negro, 20 min); derivar a la secretaria, que hace espacio manual el mismo día o el siguiente. `reservar_turno` NO se llama; se rutea al triaje con video.
- **Capa:** prompt (Router lista "alambre/bracket salido o que pincha" -> urgencia_dolor -> flujo Triaje) + gate determinístico (triaje)
- **Test:** SIN TEST específico del camino Agendar (el triaje tiene `tests/test_e2e_triaje.py` y `tests/test_triaje_nodos.js`, no verificados para este caso)
- **Fecha/fuente:** 2026-07-09 · e4/EC-45 (docs/kb-validacion-dra-2026-07-09.md [5], [18])
- **Estado:** vigente; la parte "preguntar molestia / No se preocupe" superada por el triaje con video
- **Riesgo de regresión:** el prompt curado de Agendar no tiene la regla "no agendar urgencias"; si el Router lo manda igual a agendar_nuevo, no hay defensa en Agendar (solo "pedido ajeno a agendar -> escalar").

### AGE-03 · Alucinación de disponibilidad: "no tengo turnos para X" sin consultar la tool
- **Entrada/disparador:** caso real 27/05: el bot dijo "para el 30/06 no tengo" sin haber llamado `buscar_horarios`.
- **Falla previa:** afirmó falta de turnos sin evidencia.
- **Esperado:** PROHIBIDO afirmar falta de turnos para una fecha/franja sin verlo en la respuesta de la tool. Que una fecha no figure en el bloque NO significa que esté ocupada -> pedir lote siguiente con `desde`. Solo se puede afirmar lo que diga `resultado` (SIN TURNOS / franja vacía). En un test: ante "¿hay para el 30/06?", debe haber una llamada a `buscar_horarios` antes de cualquier afirmación negativa.
- **Capa:** prompt (agendar_anti_alucinacion)
- **Test:** SIN TEST (el test solo verifica coherencia de partials, no comportamiento del LLM)
- **Fecha/fuente:** 2026-05-27 (caso) / 2026-09-07 (reescritura) · e4/EC-38
- **Estado:** vigente
- **Riesgo de regresión:** ALTO. El prompt curado de Agendar no contiene esta regla (solo "no agregues turnos"). Verificar que se conserve en Agendar y en el Router/General.

### AGE-04 · "Solo ofrece turnos de tarde": el blindaje leía '18' dentro de la fecha
- **Entrada/disparador:** reporte real de la Dra. (captura WhatsApp): paciente pidió turno de ortodoncia sin horario y el bot ofreció solo tardes hasta el 16/9, habiendo mañanas desde el 28/8 (`total_manana: 10`). Exec v6 260221 -> Sub-WF Buscar Horarios Validado 260225.
- **Falla previa:** el nodo `Validar fecha` tenía un "BLINDAJE" que buscaba '17'/'18'/'19'/'tarde'/'despues' en el JSON de input de la tool, que solo contiene `{fecha}`. "2026-08-18" contiene "18" -> `franja='tarde'`, `hora_minima=18` -> `Format Slots` decía al LLM "NO ofrezcas mañanas". Se repetía con cualquier fecha con 17/18/19.
- **Esperado:** `franja` queda `null` sin preferencia; una fecha que contenga 17/18/19 NO activa franja ni `hora_minima`; con mañanas disponibles, el bloque las incluye (respuesta correcta esperada en el E2E: "Viernes 28 de Agosto 8:30 hs").
- **Capa:** nodo (`Validar fecha`; `apply_fix_bulletproof_tarde_fix.py`)
- **Test:** SIN TEST (2 E2E manuales; cobertura indirecta: `tests/test_turnos_formato.js` §3 comprueba que Validar fecha ya no lee franja/hora_minima)
- **Fecha/fuente:** 2026-08-18 · e2/EC-15 (Bug 1)
- **Estado:** superado por AGE-28 (reescritura de Validar fecha el 2026-09-07: ya no lee franja/hora_minima); mantener como caso de regresión con fecha "2026-08-18"

### AGE-05 · El agente pega el `resultado` entero de la tool y el paciente lee instrucciones internas
- **Entrada/disparador:** el LLM pega `resultado` completo ("INSTRUCCION (no la copies)… PROHIBIDO preguntarle al paciente qué día… MENSAJE EXACTO PARA EL PACIENTE (…): <bloque>").
- **Falla previa:** como el texto contiene "turnos disponibles:", las capas 1 y 2 de AGE-14 lo dejaban pasar intacto; el Banlist no dispara.
- **Esperado:** al paciente le llega SOLO el bloque: `Split en Mensajes` recorta todo hasta el fin de la línea del centinela "MENSAJE EXACTO PARA EL PACIENTE" antes de partir; una línea propia del agente antes del bloque se conserva; centinela sin bloque no manda mensaje vacío. Ningún mensaje saliente contiene "INSTRUCCION" ni "PROHIBIDO".
- **Capa:** nodo (Split en Mensajes)
- **Test:** `tests/test_turnos_formato.js` §4.b ("si el agente pega el `resultado` ENTERO…", "fuga con preámbulo del agente", "centinela sin bloque abajo…", "una línea legítima del agente antes del bloque se conserva")
- **Fecha/fuente:** 2026-09-07 · e4/EC-34 (docs/turnos-formato-2026-09-07.md §4 capa 0, §8 #5)
- **Estado:** vigente

### AGE-06 · Política de turno único: no duplicar turno futuro (doble booking)
- **Entrada/disparador:** paciente que ya tiene un turno futuro pide otro (KB id 17).
- **Falla previa:** n/a (política de la clínica).
- **Esperado:** un paciente tiene UN solo turno futuro; si confirma una fecha y luego pide otra, REPROGRAMAR (cancelar el primero y reservar el segundo). Antes de reservar, `ver_turnos_paciente` y preguntar "Veo que ya tiene un turno reservado el [fecha]. ¿Quiere CAMBIAR ese o agregar otro?". Se ignoran citas con id_estado 1 (anulado) y 14 (cambio de fecha). `reservar_turno` no se llama antes de esa pregunta.
- **Capa:** prompt (DOBLE BOOKING)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-09 · e4/EC-44 (docs/kb-validacion-dra-2026-07-09.md [17])
- **Estado:** vigente; contradicción detectada: la política KB (cualquier turno futuro) vs el prompt vivo del 2026-10-04 ("turno activo en +/- 7 días"). Se deja el vivo como más reciente, pendiente de confirmar con la Dra.
- **Riesgo de regresión:** verificar (a) la ventana +/-7 días vs "cualquier turno futuro", (b) exclusión de id_estado 1 y 14, (c) la acción "reprogramar = cancelar el primero", ausente en el prompt curado.

### AGE-07 · Ficha duplicada de paciente en Dentalink y loop de 11 mensajes (caso Carmen A.)
- **Entrada/disparador:** paciente con celular guardado sin el 9 (formato +54 sin 9); el bot buscó con 9. Ficha duplicada id=609 (bug pre-fix multi-formato de teléfono).
- **Falla previa:** `crear_paciente_dentalink` creó una ficha duplicada ("BUG GRAVE conocido") y el bot tiró 11 mensajes en loop "no figura su turno".
- **Esperado:** `buscar_paciente_dentalink` busca 5 variantes (con/sin 9, con/sin +) + apellido como fallback; REGLA DURA ANTI-DUPLICADO: crear solo si el celular no devolvió ninguna ficha o el paciente dice explícitamente que es una persona nueva; nunca más de un mensaje de "no figura" por turno. Cleanup pendiente: id=609, 3 duplicados históricos, backfill de DNI (tarea con Irina).
- **Capa:** nodo (tool) + prompt (regla anti-duplicado)
- **Test:** SIN TEST
- **Fecha/fuente:** ~2026-04 (bug) / 2026-05-11 (pendiente operativo) · e3/EC-50 (BUGS #6; BKL P2 "Cleanup Dentalink") + e4/EC-43 (docs/plan-mvp.md)
- **Estado:** vigente; cleanup operativo pendiente
- **Riesgo de regresión:** el prompt vivo busca con `lk` + `phone_last10` (más robusto que las variantes) pero solo dice "si NO devuelve fichas: pedí nombre y DNI"; se perdió "o el paciente dice que es persona nueva" y la prohibición explícita de crear duplicado. Verificar.

### AGE-08 · Celular compartido por una familia: varias fichas en Dentalink
- **Entrada/disparador:** `buscar_paciente_dentalink` (lk-last10) devuelve varias fichas (madre/padre + hijos) con el mismo celular.
- **Falla previa:** asumir la primera ficha o escalar; en reprogramación, dead-end del sub-WF.
- **Esperado:** NO escalar. Si el paciente ya dijo a nombre de quién, elegir por nombre/apellido; si no, preguntar UNA vez "Con este número tengo registrada a más de una persona… ¿Para quién es el turno?" (con pregunta clarificatoria, listar nombres); si dos fichas tienen el MISMO nombre (duplicado real), usar la que tenga turnos/historial.
- **Capa:** prompt (Agendar PASO 1)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06 / 2026-07-06 · e4/EC-42 (docs/sesion-2026-07-06-precio-lid-reprogramacion.md)
- **Estado:** vigente
- **Riesgo de regresión:** el prompt vivo dice "preguntá a nombre de quién o pedí el DNI para matchear con `rut`"; pero AGE-26 indica que las fichas creadas por el bot no tienen `rut`, así que el match por DNI falla. Se perdieron "preguntar UNA vez", "no escalar" y el criterio de mismo-nombre-usa-la-que-tiene-historial.

### AGE-09 · Fix aplicado en la capa equivocada (el sub-agent correcto nunca corría)
- **Entrada/disparador:** reproducción del caso Salvador con teléfono de test (exec 262253).
- **Falla previa:** el primer fix, solo en Sub-Agent Agendar, no tuvo efecto: el Router mandó el mensaje a Sub-Agent General (`consulta_general`).
- **Esperado:** antes de dar por bueno un fix de prompt, reproducir en vivo y verificar QUÉ sub-agent corre. Los bugs de ruteo se arreglan en el Router y en el sub-agent destino (2 capas). Una aserción testeable: para el mensaje del caso, el Router devuelve el intent esperado (agendar_nuevo / cancelar_o_reprogramar) y no `consulta_general`.
- **Capa:** prompt (Router + sub-agent destino) + proceso de verificación
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-21 · e2/EC-11
- **Estado:** vigente (proceso). Nota: el sub-agent de reprogramación hoy es el sub-WF `5cAWJxiWJ50hxEq3`, no el nodo muerto.
- **Riesgo de regresión:** el Router curado cubre "¿se puede cambiar para la tarde?" en cancelar_o_reprogramar y tiene REGLA DE CONTINUIDAD; "¿hay turnos para el viernes?" no está listado y cae en `consulta_general` por regla de ambigüedad (ver AGE-10).

### AGE-10 · Sub-Agent General no tiene `buscar_horarios` conectada pero su prompt la nombraba
- **Entrada/disparador:** "¿hay turnos para el viernes?" / "¿se puede mover?" atendido por Sub-Agent General.
- **Falla previa:** General prometía "Ahora le paso los turnos disponibles" y no enviaba nada (el v6 no encadena un segundo turno de agente).
- **Esperado:** General devuelve la pelota ("Confirmame que querés el turno y te paso los turnos") y el paciente cae en agendar_nuevo / cancelar_o_reprogramar el turno siguiente; nunca promete un mensaje futuro ni "le paso con la agenda". Fragmento `general_hay_turnos` listo si se conecta la tool.
- **Capa:** prompt
- **Test:** `tests/test_turnos_formato.js` ("Sub-Agent General ya no promete un mensaje que nunca llega")
- **Fecha/fuente:** 2026-09-07 · e4/EC-50 (docs/turnos-formato-2026-09-07.md §7, §8 #6)
- **Estado:** vigente
- **Riesgo de regresión:** el General curado no contiene la regla "devolver la pelota" ni el "NUNCA digas le paso con la agenda" (este último solo figura en el bloque del nodo muerto Urgencia). Verificar con "¿hay turnos para el viernes?".

### AGE-11 · "Nunca preguntar franja ni fecha": ofrecer directo los turnos
- **Entrada/disparador:** pedido textual de la Dra. (WhatsApp 2026-09-07): "no preguntar qué franja de horario le viene bien ni en qué fecha específica quiere el turno, porque nosotros atendemos en horarios y días específicos… solo procedemos en decirles qué turnos disponemos y ellos eligen". Salía de 3 capturas de la Dra. tomadas del sub-WF Cancelar/Reprogramar.
- **Falla previa:** PASO 3.b de Agendar preguntaba "¿Prefiere por la mañana o por la tarde?"; Step 5 del sub-WF preguntaba "qué día o franja le viene mejor? (mañana / tarde / fecha concreta)"; la línea 79 de TOOLS decía que `fecha` era OBLIGATORIO (contradicción viva).
- **Esperado:** ante un pedido de turno o de cambio, llamar `buscar_horarios` UNA vez SIN parámetros y pegar el bloque INTACTO (agrupado mañana/tarde, mínimo 2 de cada, las más próximas); `desde` solo para el lote siguiente; ningún mensaje contiene "¿mañana o tarde?" ni "¿qué día…?". Sin fecha = hoy (Jujuy).
- **Capa:** prompt (Agendar, General, Cancelar [nodo muerto], Formatting Agent) + nodo (Format Slots, Step 5 del sub-WF)
- **Test:** `tests/test_turnos_formato.js` (87 checks; "la línea de TOOLS deja de decir que `fecha` es OBLIGATORIO", "ningún fragmento nuevo le pregunta al paciente la franja o el día", "Step 5: … ningún mensaje de Step 5 pregunta día ni franja")
- **Fecha/fuente:** 2026-09-07 (reafirmada 2026-10-04) · e1/EC-5 (current-state.md) + e4/EC-24 (docs/turnos-formato-2026-09-07.md §1, §3C, §8 #3)
- **Estado:** vigente
- **Riesgo de regresión:** el Agendar curado preserva la regla, pero agrega "si pidió una ventana específica, pasá `desde` y `hasta`", que contradice "`desde` solo para el lote siguiente" y no hay evidencia en las fuentes de que la tool acepte `hasta`. Verificar el parámetro `hasta` en el sub-WF Buscar Horarios Validado.

### AGE-12 · Paciente contesta "A la tarde" y el bot repite los 3 turnos de mañana
- **Entrada/disparador:** captura 2 del 7/9: la paciente contesta "A la tarde" tras la oferta; variantes "a la mañana", "después de las 16".
- **Falla previa:** el bot repitió los mismos 3 turnos de mañana (Step 6b-prep pedía UN solo día de agenda; Step 6b-out nunca filtraba por franja y recibía `franja`/`hora_minima` e ignoraba).
- **Esperado:** el bloque ya trae las dos franjas; "a la tarde" -> se señalan los turnos de tarde que YA figuran en el bloque, en frase normal y con "hs"; "después de las X" filtra horarios; si esa franja no aparece, decir derecho que no hay y ofrecer lo que hay. No se repiten los turnos de la otra franja.
- **Capa:** nodo (Step 5 / Step 6b-out) + prompt (PASO 5 / REGLA 17HS)
- **Test:** `tests/test_turnos_formato.js` ("Step 5: 'a la tarde' sobre el bloque -> se le repiten los turnos de tarde", "'a la mañana'", "'después de las 16' filtra los horarios"). Ojo: `tests/test_nodes_eval.py` y `tests/test_reprogramar_franja.py` prueban la lógica vieja y están en conflicto.
- **Fecha/fuente:** 2026-09-07 · e4/EC-25 (docs/turnos-formato-2026-09-07.md §1 captura 2, §2)
- **Estado:** vigente; tests viejos probablemente obsoletos
- **Riesgo de regresión:** el prompt vivo dice "indicále los turnos de esa franja que YA están en el bloque con hora y formato 24 hs"; se perdió "si esa franja no aparece, decirlo derecho" y "después de las X filtra".

### AGE-13 · El bot nombraba "Dentalink" al ofrecer turnos
- **Entrada/disparador:** captura del 7/9: "Tengo disponibles en Dentalink los siguientes turnos próximos: 24 de Septiembre 8:00 hs / 24 de Septiembre 8:40 hs / 24 de Septiembre 9:20 hs. Le sirve alguno?" (una línea, 3 turnos del mismo día y franja). Dra.: "no es necesario que diga dentalink, los pacientes no conocen el sistema".
- **Falla previa:** nombraba el sistema de gestión y mostraba 3 turnos del mismo día (salía de Step 6b-out del sub-WF CancelarReprogramar). También lo hacía Agendar (e1/EC-5).
- **Esperado:** la palabra "Dentalink" NO aparece nunca al paciente en ningún camino (bloque, resultado de la tool, prompts, canned).
- **Capa:** nodo (Format Slots / Step 6b-out) + prompt
- **Test:** `tests/test_turnos_formato.js` (check "ningún camino menciona el sistema de gestión")
- **Fecha/fuente:** 2026-09-07 · e4/EC-22 (docs/turnos-formato-2026-09-07.md §1) + e1/EC-5
- **Estado:** vigente
- **Riesgo de regresión:** los prompts curados de Agendar y Confirmar siguen nombrando "Dentalink" en el propio prompt ("agendar… en Dentalink", "confirmar_turno… en Dentalink") y no tienen prohibición explícita de decirlo al paciente. Verificar que ninguna respuesta de texto libre lo mencione. El banlist no lo cubre (no hay patrón en las fuentes).

### AGE-14 · El bloque de turnos no debe pasar por el Formatting Agent ni partirse
- **Entrada/disparador:** el bloque mide ~230 chars (>80), así que `Necesita Formatting?` lo mandaría a gpt-5-mini, que agrega "hs" y capitaliza meses ("jueves 24 de septiembre a las 8 de la mañana"); además `Split en Mensajes` parte por "---".
- **Falla previa:** el LLM reescribe el bloque.
- **Esperado:** 3 capas: (1) `Necesita Formatting?` con 3ª condición `notContains 'turnos disponibles:'`; (2) guard en `Split en Mensajes` que prefiere el original si el formateado difiere; (3) REGLA #0.b del Formatting Agent. El bloque no contiene "---" -> un solo mensaje con sus líneas en blanco; con alias/CBU del Sidecar, el bloque va completo como parte 1.
- **Capa:** gate (Necesita Formatting? / Split) + prompt (Formatting Agent REGLA #0.b, presente en el vivo)
- **Test:** `tests/test_turnos_formato.js` ("bypass del Formatting Agent: UN solo mensaje…", "si el LLM igual lo reescribe: gana el ORIGINAL", "bloque + sidecar de alias: 2 mensajes", "el guard viejo del CBU sigue funcionando")
- **Fecha/fuente:** 2026-09-07 · e4/EC-33 (docs/turnos-formato-2026-09-07.md §4)
- **Estado:** vigente

### AGE-15 · Choque entre el "hs" obligatorio y el formato de la Dra. (sin "hs")
- **Entrada/disparador:** paciente "a la tarde" tras el bloque; el agente contesta con una línea suelta copiada `* Lunes 5 de octubre 15:00 , 15:40`.
- **Falla previa:** esa línea no lleva "turnos disponibles:", no la desvía `Necesita Formatting?` ni la protege el guard de Split -> el Formatting Agent aplica su REGLA #3 y sale "Lunes 5 de Octubre 15:00 hs, 15:40 hs": dos formatos distintos en dos mensajes seguidos.
- **Esperado:** regla binaria: o el bloque entero sin tocar (sin "hs") o una frase normal con "hs" ("le confirmo el Jueves 24 de septiembre a las 8:00 hs"); los 3 fragmentos de franja y `agendar_formato_horas` alineados; REGLA #0.b del Formatting Agent. Una línea suelta de horarios sin "hs" no debe llegar al paciente.
- **Capa:** prompt + gate (Necesita Formatting? 3ª condición; guard de Split)
- **Test:** `tests/test_turnos_formato.js` ("los 3 fragmentos de franja mandan repetir el turno en una frase CON 'hs'", "el carve-out del 'hs' …")
- **Fecha/fuente:** 2026-09-07 · e4/EC-32 (docs/turnos-formato-2026-09-07.md §8 #2)
- **Estado:** vigente
- **Riesgo de regresión:** el Formatting Agent vivo conserva #0.b y el ejemplo del bloque, pero la REGLA #3 sigue exigiendo "hs" y solo la salva el carve-out. El Agendar curado no tiene `agendar_formato_horas` (solo "formato 24 hs"). Verificar la respuesta a "a la tarde".

### AGE-16 · Sesgo a la tarde cuando no hay preferencia (Format Slots)
- **Entrada/disparador:** tras AGE-04, con `franja=null`.
- **Falla previa:** `Format Slots` daba las listas mañana/tarde por separado sin decir cuál es el más próximo, y el modelo seguía sesgando a tarde.
- **Esperado:** sin preferencia de franja, el bloque incluye mañana y tarde, y el slot cronológicamente más próximo se identifica explícitamente (Dentalink ya ordena por fecha).
- **Capa:** nodo (`apply_fix_format_slots_iterate.py`)
- **Test:** SIN TEST (cobertura indirecta: "bloque exacto 2+2 con la agenda real de hoy" en `tests/test_turnos_formato.js`)
- **Fecha/fuente:** 2026-08-18 · e2/EC-16 (Bug 2)
- **Estado:** superado por AGE-20 (el Format Slots reescrito el 2026-09-07 produce un bloque determinístico 2 mañana + 2 tarde)

### AGE-17 · Dentalink devuelve siempre 10 slots y no filtra por franja (MAX_PAGINAS=3 no alcanzaba)
- **Entrada/disparador:** búsqueda desde 2026-11-01, 2026-12-15 o 2027-03-01 (juntar 2 mañanas + 2 tardes consume exactamente 3 páginas; con 3 días por franja, 4-5).
- **Falla previa:** con tope en 3 se agotaba la paginación y Format Slots omitía la sección "Por la tarde" SIN aviso; el paciente recibía solo mañanas (= captura 2).
- **Esperado:** MAX_PAGINAS = 6 (el script aborta si el jsCode y el cableado no declaran el mismo tope); `limit/page/offset` se ignoran; `hora_inicio:{gte:"13:00"}` no filtra; corta si una página no trae nada nuevo, si falla la red o si el cursor pasa de 4 meses.
- **Capa:** nodo (Acumular P1..P6) + script apply (aborta ante inconsistencia)
- **Test:** `tests/test_turnos_formato.js` ("P<N> sin tarde: sigue paginando (antes se cortaba en la 3)", "P6 es la última: seguir=false")
- **Fecha/fuente:** 2026-09-07 · e4/EC-27 (docs/turnos-formato-2026-09-07.md §3A, §8 #1)
- **Estado:** vigente

### AGE-18 · El Format Slots viejo ofrecía el mismo turno tres veces y tardaba ~80 s
- **Entrada/disparador:** cualquier pedido de turno con el Format Slots viejo (escaneo día por día con `this.helpers.httpRequest` y token de Dentalink en claro dentro del jsCode).
- **Falla previa:** hasta 91 llamadas (~80 s); como `fecha:{eq:X}` se comporta como `>= X`, cada llamada devolvía los mismos días posteriores y el bot llegaba a ofrecer el mismo turno tres veces (sin dedupe).
- **Esperado:** paginado por cursor (fecha del último slot, no +1 día), dedupe por (fecha, hora_inicio), hasta 6 páginas, corta con 2 días de mañana y 2 de tarde, techo ~4,4 s; credencial `httpHeaderAuth`, token fuera del jsCode (ningún jsCode contiene el token).
- **Capa:** nodo (Acumular P1..P6 / Faltan turnos?)
- **Test:** `tests/test_turnos_formato.js` ("P2: deduplica por (fecha, hora_inicio)", "P2: … completo -> CORTA", "MAX_PAGINAS declarado en el jsCode = 6")
- **Fecha/fuente:** 2026-09-07 · e4/EC-26 (docs/turnos-formato-2026-09-07.md §3A)
- **Estado:** vigente

### AGE-19 · Dentalink responde 429 tras una ráfaga y degrada el bloque a solo-mañana
- **Entrada/disparador:** sondeo del 7/9 (y ~40 GET seguidos el 8/9): HTTP 429.
- **Falla previa:** el diseño pasa de 1 a hasta 6 llamadas por pedido de turno; un 429 en páginas avanzadas dejaría el bloque solo con lo ya juntado, en silencio.
- **Esperado:** GET Horarios P2..P6 con `retryOnFail` (2 intentos, 2 s); `continueOnFail` + Acumular sigue con lo que haya; error de red sin slots -> ERROR_TECNICO "NO afirmes que no hay turnos" (no se debe afirmar "no hay turnos" ante un error técnico).
- **Capa:** nodo
- **Test:** `tests/test_turnos_formato.js` ("error de red sin ningún slot: ERROR_TECNICO…", "error de red con slots ya juntados: igual se ofrece lo que hay")
- **Fecha/fuente:** 2026-09-07 · e4/EC-28 (docs/turnos-formato-2026-09-07.md §3A; docs/recordatorio-consultas-2026-09-08.md §6.3)
- **Estado:** vigente

### AGE-20 · Formato del bloque de turnos pedido por la Dra. (2 mañana + 2 tarde, sin "hs")
- **Entrada/disparador:** paciente pide turno; la Dra. envió el formato: "Tenemos los próximos turnos disponibles: / Por la mañana: / * Jueves 8 de septiembre 9:20 , 10:40 / … / Por la tarde / … / Le sirve alguno?".
- **Falla previa:** el bot ofrecía 3-4 turnos agrupados con ";" y "hs", sin separar franjas (Format Slots, Acumular P1/P2/P3, Validar fecha sin fechas exactas validadas).
- **Esperado:** bloque determinístico (`turnos/format_slots.js`): mañana = hora_inicio < 13, tarde >= 13; hasta 2 días por franja y 2 horarios por día separados por " , "; día de la semana capitalizado, mes en minúscula, hora H:MM sin cero ni "hs"; línea en blanco entre secciones; cierra con "Le sirve alguno?"; sin "---" (partiría el mensaje); mínimo 2 de cada franja, las más próximas.
- **Capa:** nodo (Format Slots) + gate (bypass del Formatting Agent, ver AGE-14) + prompt
- **Test:** `tests/test_turnos_formato.js` ("bloque exacto 2+2 con la agenda real de hoy", "hora sin cero adelante y SIN 'hs'", "mes en minúscula…")
- **Fecha/fuente:** 2026-09-07 · e4/EC-23 (docs/turnos-formato-2026-09-07.md §1-§2) + e3/EC-53 (pedido de Raquel 2026-09-07) + e1/EC-5
- **Estado:** vigente (los scripts `apply_fix_format_slots_*` sin commitear sugieren iteraciones de fechas exactas/iterate/json_parse)

### AGE-21 · `siguiente_desde` saltaba mañanas: ahora = mínimo de las dos franjas
- **Entrada/disparador:** el paciente rechaza el primer bloque ("ninguno me sirve", "más adelante") o pide más opciones.
- **Falla previa:** `siguiente_desde` tomaba el MÁXIMO entre mañana y tarde; si el lote 2 arrancaba tras el último turno de tarde, las mañanas del 01/10 y 02/10 nunca se ofrecían (medido con la agenda real del 07/09).
- **Esperado:** `siguiente_desde` = día siguiente al último día de la franja que termina antes (2026-09-30 en el ejemplo); no saltea turnos de ninguna franja; contrapartida aceptada: la tarde puede repetirse en el lote 2 mientras siga libre; cruza el año ("2027-01-02").
- **Capa:** nodo (`Format Slots`, `Sub-WF - Buscar Horarios Validado`)
- **Test:** `tests/test_turnos_formato.js` ("siguiente lote: día siguiente al MINIMO de las dos franjas")
- **Fecha/fuente:** 2026-09-07 · e1/EC-26 (current-state.md, bugs latentes) + e4/EC-31 (docs/turnos-formato-2026-09-07.md §2)
- **Estado:** vigente

### AGE-22 · Turno ocupado por race entre ofrecer y reservar (PASO 7.b)
- **Entrada/disparador:** `reservar_turno` falla porque otro paciente tomó el slot entre la oferta y la reserva.
- **Falla previa:** era el único lugar donde el agente redactaba su propia lista de turnos ("Le puedo ofrecer: [los próximos 2-3 slots libres]").
- **Esperado:** disculpa en una línea ("Quedó tomado ese horario, mil disculpas."), `buscar_horarios` sin parámetros y pegar el bloque nuevo; prohibido armar lista a mano.
- **Capa:** prompt
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-03 (pedido Dra.) / 2026-09-07 (actualización) · e4/EC-39
- **Estado:** vigente
- **Riesgo de regresión:** el vivo conserva "pedí disculpas y mostrá un nuevo bloque"; se perdió el texto exacto de disculpa y la prohibición de armar la lista a mano (queda cubierta solo por la regla genérica "pegalo TAL CUAL").

### AGE-23 · Reserva automática ante expresiones afirmativas (no pedir comando exacto)
- **Entrada/disparador:** tras el read-back: "si", "si por favor", "dale", "confirmo", "obvio", "ok", "perfecto", "listo", emojis 👍/✅/🙏, "ese mismo", "buenísimo para ese día", "el primero".
- **Falla previa:** el bot pedía que el paciente escribiera una frase exacta ("por favor escriba 'quiero un turno el X a las Y'").
- **Esperado:** ejecutar `reservar_turno` UNA vez inmediatamente; PROHIBIDO pedir comandos o frases exactas; fecha/hora/paciente ya están en memoria. Ver contrapeso en AGE-01 (la afirmativa debe ser posterior al read-back).
- **Capa:** prompt (PASO 7)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-03 · e4/EC-40
- **Estado:** vigente
- **Riesgo de regresión:** el prompt vivo lista solo "sí, dale, perfecto, confirmo, 👍" y no prohíbe pedir comandos; verificar con "obvio", "listo", "ese mismo", "el primero". Tensión con el Router: un "dale" puede ir a confirmar_post_recordatorio (ver CON-01).

### AGE-24 · Mensaje post-reserva: PRE-reservado, pago hasta 72 hs, alias con preámbulo
- **Entrada/disparador:** reserva exitosa de un turno.
- **Falla previa:** el alias se mandaba crudo, sin preámbulo.
- **Esperado:** "Listo, le queda PRE-reservado para [día/hora]. Para confirmarlo definitivamente necesitamos el pago hasta 72hs antes… Le envío alias y datos de cuenta de la Dra. …" + `---` + "Alias: … / Titular: …" (alias y titular salen limpios y copiables). Nunca crear paciente sin PASO 2 completo, nunca inventar horarios, nunca reservar sin confirmación.
- **Capa:** prompt (PASO 4 vivo) + gate (Canned Sidecar para alias)
- **Test:** `tests/test_canned_sidecar.py` (alias con preámbulo, no duplicar); el texto del prompt no tiene test
- **Fecha/fuente:** 2026-06-03 · e4/EC-48
- **Estado:** vigente (preservado en el curado del 2026-10-04; ver AGE-36)

### AGE-25 · La hora del parser de aceptación llega sin cero adelante al POST de reserva
- **Entrada/disparador:** aceptación de "8:40" tras un bloque (el bloque nuevo pone dos horarios por línea y no lleva año).
- **Falla previa:** `Step 6d-prep` mandaba a la agenda la `hora_inicio` tal cual ("8:40").
- **Esperado:** normalizar a `HH:MM` ("08:40") antes del POST; pendiente validar `slot_a_reservar` (viene de un parser LLM) contra las líneas del bloque antes de reservar, para no reservar un horario que nunca se ofreció.
- **Capa:** nodo (Step 6d-prep, sub-WF reprogramar)
- **Test:** `tests/test_turnos_formato.js` (parcial: normalización de horas en Acumular; `slot_a_reservar` sin validar no tiene test)
- **Fecha/fuente:** 2026-09-07 · e4/EC-49 (docs/turnos-formato-2026-09-07.md §3B, §7)
- **Estado:** vigente; validación del slot pendiente de implementar

### AGE-26 · El DNI nunca llega a Dentalink al crear paciente (GAP 7)
- **Entrada/disparador:** invocación de `crear_paciente_dentalink`.
- **Falla previa:** no manda `documento` ni `id_sucursal` en el jsonBody: fichas creadas sin `rut`; el DNI-match nunca las encuentra; el apellido fallback es el pushName de WhatsApp.
- **Esperado:** el jsonBody incluye `documento` e `id_sucursal`; backfill de DNI en fichas ya creadas por el bot.
- **Capa:** nodo (tool)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06 · e3/EC-51 (BKL P1 "Fase 1 reprogramaciones (a)") + e4/EC-43
- **Estado:** vigente (no se confirma en las fuentes que esté aplicado)

### AGE-27 · Menor de edad: avisar que el tutor debe estar presente, una sola vez
- **Entrada/disparador:** "es para mi hijo de X años", "tutor".
- **Falla previa:** n/a (reglas de prompt).
- **Esperado:** decir UNA vez "Por ser menor, el tutor debe estar presente."; NO pedir DNI del tutor ni relación; no duplicar el pedido de datos del PASO 2; no preguntar la edad al agendar; si se entera después de agendar, mencionarlo sin re-anunciar pedidos; la cita de devolución no requiere al menor.
- **Capa:** prompt
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-09 · e4/EC-47 (docs/kb-validacion-dra-2026-07-09.md [6], [28], [33])
- **Estado:** vigente
- **Riesgo de regresión:** el vivo conserva la frase "una sola vez"; se perdieron "no pedir DNI del tutor", "no preguntar edad" y "devolución no requiere al menor".

### AGE-28 · Fecha inválida, pasada o a más de 12 meses ya no se le pide al paciente
- **Entrada/disparador:** `buscar_horarios` sin parámetros, con fecha pasada, fecha basura, a más de 12 meses, strings vacíos, o `desde` + `fecha` a la vez.
- **Falla previa:** el Validar fecha viejo devolvía error y el agente pedía la fecha al paciente (Output Error).
- **Esperado:** sin fecha o inválida -> busca desde HOY (America/Argentina/Jujuy) y marca `parametro_ignorado`; `desde` gana sobre `fecha` si es futura y dentro del año; ya no lee franja/hora_minima. El agente nunca pide fecha por esto.
- **Capa:** nodo (Validar fecha)
- **Test:** `tests/test_turnos_formato.js` §3 ("sin parámetros: busca desde HOY", "fecha pasada", "fecha basura", "fecha a más de 12 meses", "`desde` gana sobre `fecha`")
- **Fecha/fuente:** 2026-09-07 · e4/EC-35 (docs/turnos-formato-2026-09-07.md §3A)
- **Estado:** vigente

### AGE-29 · Agenda sin turnos en una franja: omitir la sección entera, nunca inventar
- **Entrada/disparador:** Dentalink devuelve solo turnos de mañana (o solo de tarde, o ninguno).
- **Falla previa:** n/a (test).
- **Esperado:** se omite la sección completa (encabezado incluido); el `resultado` que lee el LLM le avisa que no la invente; sin turnos en ninguna franja -> bloque vacío, `hay_turnos=false` y `SIN TURNOS … escala con escalar_a_secretaria`, sin pedirle fecha ni franja al paciente.
- **Capa:** nodo (Format Slots)
- **Test:** `tests/test_turnos_formato.js` ("solo mañana…", "solo tarde…", "ningún slot: bloque vacío, hay_turnos false y hay que escalar", "ningún slot: NO le pide fecha ni franja")
- **Fecha/fuente:** 2026-09-07 · e4/EC-29 (docs/turnos-formato-2026-09-07.md §2)
- **Estado:** vigente

### AGE-30 · Slots desordenados, cambio de mes/año y día de la semana calculado en código
- **Entrada/disparador:** slots que llegan desordenados; diciembre->enero; fechas conocidas incluyendo bisiesto 2028.
- **Falla previa:** n/a (el modelo "erra seguido" el día de la semana: regla crítica del header).
- **Esperado:** el bloque sale ordenado por fecha y hora; día de la semana real calculado en código (11 fechas conocidas); `siguiente_desde` cruza el año; el LLM nunca calcula el día de la semana, solo copia el que vino escrito; si solo tiene fecha numérica escribe "el [n] de [Mes] a las [HH:MM] hs" sin día de semana.
- **Capa:** nodo (Format Slots) + prompt (header DIA DE LA SEMANA)
- **Test:** `tests/test_turnos_formato.js` ("slots desordenados…", "cambio de mes y de año…", "día de la semana correcto contra 11 fechas conocidas")
- **Fecha/fuente:** 2026-09-07 · e4/EC-30 (prompts/v6_partials/header_common.md)
- **Estado:** vigente
- **Riesgo de regresión:** la regla de prompt "NUNCA calcules el día de la semana" ya no está en los prompts curados de Agendar/Confirmar/General (solo en el bloque del nodo muerto Urgencia). El read-back de Agendar ("[Día N de Mes…]") y la confirmación de Confirmar ("[fecha natural]") pueden hacer que el LLM invente el día. Verificar.

### AGE-31 · Horas sin cero adelante y slots mal formados
- **Entrada/disparador:** horas "8:00" vs "08:00:00", fechas mal formadas, slots ocupados, filas sin hora, respuesta anidada `{data:{data:[…]}}`, respuesta vacía.
- **Falla previa:** n/a (test).
- **Esperado:** se normalizan a HH:MM y quedan ordenadas; se descartan fechas mal formadas, ocupados y filas sin hora; tolera el anidado; vacío -> 0 slots, `seguir=false`, sin explotar.
- **Capa:** nodo (Acumular)
- **Test:** `tests/test_turnos_formato.js` §2 ("horas sin cero adelante: se normalizan a HH:MM", "descarta fechas mal formadas…", "tolera la respuesta anidada", "respuesta vacía…")
- **Fecha/fuente:** 2026-09-07 · e4/EC-36
- **Estado:** vigente

### AGE-32 · Horizonte agotado (> 120 días) y página sin novedades
- **Entrada/disparador:** agenda sin tardes en 4 meses / Dentalink repite la misma página.
- **Falla previa:** n/a (test).
- **Esperado:** MAX_DIAS_HORIZONTE = 120 corta aunque falte la tarde (se avisa a la clínica, no es bug); página sin nada nuevo -> `seguir=false`.
- **Capa:** nodo (Acumular)
- **Test:** `tests/test_turnos_formato.js` ("horizonte agotado (>120 días)", "página sin nada nuevo: seguir=false")
- **Fecha/fuente:** 2026-09-07 · e4/EC-37 (docs/turnos-formato-2026-09-07.md §3A, §5.6)
- **Estado:** vigente

### AGE-33 · Plazo máximo de reserva: la política dice "sin límite", Validar fecha ignora > 12 meses
- **Entrada/disparador:** paciente quiere turno a más de 12 meses (o "vuelvo en X meses").
- **Falla previa:** Validar fecha ignora fechas a más de 12 meses para el parámetro de la tool.
- **Esperado:** la KB id 2 dice "Aceptamos reservas con cualquier antelación… hasta un año o más, lo importante es tenerlos registrados en Dentalink para el recordatorio". Tensión conocida con el tope de 12 meses; el comportamiento deseado no está decidido.
- **Capa:** prompt / nodo (tensión abierta)
- **Test:** `tests/test_turnos_formato.js` ("fecha a más de 12 meses: se ignora") cubre el código, no resuelve la política
- **Fecha/fuente:** 2026-07-09 (KB) y 2026-09-07 (Validar fecha) · e4/EC-46 (docs/kb-validacion-dra-2026-07-09.md [2])
- **Estado:** pendiente de decisión

### AGE-34 · Ofrecer la grilla de atención primero
- **Entrada/disparador:** paciente pide turno; Raquel: "lo primero que debería decir es: la doctora atiende lunes y miércoles de 15 a 20 hs, y martes, jueves y viernes de 8 a 12 hs… si no, pregunta un montón de días que no están disponibles y se hace engorroso".
- **Falla previa:** el bot arrancaba buscando disponibilidad sin anclar la grilla; el paciente tanteaba fechas inexistentes.
- **Esperado:** PASO 3 (3/6): declarar grilla + primer turno libre. Desde el 7/9 el bot pega el bloque y puede anteponer UNA línea con los horarios dinámicos de la KB (Extraer Horarios y Precio); no se pregunta nada.
- **Capa:** prompt
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-03 · e4/EC-41 (docs/Asiri - Feedback Raquel 03-06.pdf punto 7; docs/turnos-formato-2026-09-07.md §3C)
- **Estado:** superado por el bloque de turnos (2026-09-07; ver AGE-11/AGE-20). El prompt vivo no ordena anteponer la línea de horarios.

### AGE-35 · Tools de Dentalink sin `toolDescription`
- **Entrada/disparador:** `cancelar_turno`, `reservar_turno`, `crear_paciente_dentalink`, `ver_profesionales`.
- **Falla previa:** el LLM adivina parámetros por nombre; rompe en bordes.
- **Esperado:** descripciones específicas con idiosincrasias (p.ej. "PUT solo acepta {id_estado:1}").
- **Capa:** prompt (tool description), pendiente
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-05-09 · e3/EC-52 (BUGS #24; PEND backlog robustez)
- **Estado:** vigente (pendiente de implementar)

### AGE-36 · Sub-Agent Agendar con 32.500 chars de reglas duplicadas y de otros agentes (curación)
- **Entrada/disparador:** el prompt acumulaba 244 líneas: regla >17hs repetida 3 veces, validaciones de destino ajenas a Agendar, casos viejos de soporte (caso Salvador, Round 13/14).
- **Falla previa:** degradación de velocidad/precisión por prompt inflado y contradictorio.
- **Esperado:** curado a 4.052 chars / 49 líneas (2026-10-04, `scripts/apply_curar_subagent_agendar.py`) preservando: identificación con `phone_last10`, familias con teléfono compartido, alta con Nombre y DNI, Read-Back antes de reservar, doble booking, menores, y el mensaje post-reserva con `---` (Alias y Titular copiables).
- **Capa:** prompt
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-10-04 (tarde) · e1/EC-4 (current-state.md "Curación Sub-Agent Agendar: reducción del 88%")
- **Estado:** vigente
- **Riesgo de regresión:** comparado con las reglas de este catálogo, el curado NO conserva: anti-alucinación de disponibilidad (AGE-03), no agendar urgencias (AGE-02), exclusión de id_estado 1/14 y política de turno único completa (AGE-06), regla anti-duplicado explícita (AGE-07), comandos afirmativos extendidos (AGE-23), día de la semana (AGE-30), prohibición de nombrar Dentalink (AGE-13) y los detalles de menores (AGE-27).

### AGE-37 · Parches de prompt por reemplazo quirúrgico: los partials del repo están desactualizados
- **Entrada/disparador:** `build_prompts_v6.py --check` da Agendar -4558 chars, General -12102, Confirmar -2719, Cancelar -1500 contra el vivo.
- **Falla previa:** aplicar los partials borraría meses de fixes.
- **Esperado:** los cambios de prompt son reemplazos exactos sobre el texto VIVO (ANTES extraído del vivo; el script aborta si no lo encuentra); los `.antes/.despues` de `prompts/v6_partials/turnos/` son parches, no el prompt entero.
- **Capa:** infra (script apply con ancla única + backup)
- **Test:** `tests/test_turnos_formato.js` (coherencia de partials; no cubre el drift contra el vivo)
- **Fecha/fuente:** 2026-09-07 · e4/EC-51 (docs/turnos-formato-2026-09-07.md §3C, §7; docs/roadmap-refactor-2026-09-06.md B5)
- **Estado:** superado en parte por la curación del 2026-10-04 (AGE-36): los 4 prompts vivos son ahora mucho más cortos y los partials son aún menos representativos. No correr `build_prompts_v6.py` sin revisar.

### Cobertura
37 casos consolidados (de 41 crudos). 16 SIN TEST (AGE-01, 02, 03, 04, 06, 07, 08, 09, 16, 22, 23, 26, 27, 34, 35, 36); los demás tienen cobertura de `tests/test_turnos_formato.js` o `tests/test_canned_sidecar.py`, con parciales en AGE-24, 25, 33, 37. Casi todo lo cubierto es código de nodo; las reglas de prompt (comportamiento del LLM) casi no tienen tests.
Los 3 huecos más peligrosos: (1) AGE-01 reserva sin confirmación/pago, sin gate y sin test, más AGE-03 alucinación de disponibilidad, que se perdió en la curación; (2) AGE-06/07/08/26 identidad y duplicación de pacientes (doble booking +/-7 días contra la política, fichas duplicadas, familias, DNI no enviado), todo sin test y con reglas parcialmente perdidas; (3) AGE-02 urgencia desde Agendar sin defensa en el prompt curado, y AGE-25 `slot_a_reservar` sin validar contra el bloque ofrecido, que permitiría reservar un horario inexistente.

---

## confirmar

### CON-01 · Confirmar sin turno real en agenda (caso Valentino): el bot inventaba fecha/hora
- **Entrada/disparador:** paciente dice "confirmo/dale" sin NOTA INTERNA ni turno activo en los próximos 7 días (caso Valentino, 2026-06-03).
- **Falla previa:** el bot inventaba fecha/hora a partir de mensajes anteriores del paciente (propuestas, no turnos) y respondía "Listo, su turno del X queda confirmado" sin ejecutar `confirmar_turno`.
- **Esperado:** prohibido el canned de confirmación sin un `confirmar_turno` exitoso con id_cita real de esa ejecución ("una respuesta sin tool ejecutada = MENTIRA al paciente"). Sin NOTA INTERNA con cita_id y sin turno activo -> `escalar_a_secretaria` + canned con horario ("Le paso su consulta a la secretaria…"); NO se inventa fecha/hora desde mensajes previos. Tool `confirmar_turno` no llamada -> no aparece "queda confirmado".
- **Capa:** prompt (Confirmar; VALIDACION DE DESTINO / REGLA ABSOLUTA ANTI-ALUCINACION)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-03 · e4/EC-56 (prompts/v6_partials/confirmar_tools.md, header_common.md)
- **Estado:** vigente
- **Riesgo de regresión:** el Confirmar curado conserva "NUNCA afirmes confirmado sin `confirmar_turno` exitoso", "NO inventes turnos" y el escalado cuando no hay turno activo. Se perdió el chequeo de NOTA INTERNA, la aclaración "mensajes previos = propuestas" y el bloque VALIDACION DE DESTINO (hoy solo en el nodo muerto Urgencia). Además, el "dale" ambiguo entre agendar_nuevo ("dale ese") y confirmar_post_recordatorio depende de la REGLA DE CONTINUIDAD del Router curado; verificar un "dale" tras una oferta de turnos.

### CON-02 · Comprobante de pago recibido por Sub-Agent Confirmar: respuesta fija, sin recitar fecha ni monto
- **Entrada/disparador:** imagen "TIPO: COMPROBANTE" o texto "transferí/comprobante/depósito/pagué/ya transferí/adjunto pago".
- **Falla previa:** el modelo recitaba fecha/día/hora del turno ("le confirmo el turno"), el monto, o afirmaba que el pago estaba OK (el día de la semana lo erra seguido).
- **Esperado:** respuesta EXACTA "Recibimos su comprobante. Le informo a la secretaria, que verificará el pago en su horario de atención (…). Gracias!"; SIEMPRE `escalar_a_secretaria` (una vez); `confirmar_turno` solo si hay UN único turno próximo identificado (0 o varios -> NO confirmar); NUNCA dar por validado el pago ni mencionar monto, fecha o día.
- **Capa:** prompt (PASO 0) + gate (Canned Sidecar para "dónde transfiero / qué alias")
- **Test:** `tests/test_canned_sidecar.py` (comprobante + "dónde transfiero / qué alias"); la exactitud del canned y el criterio de turno único no tienen test
- **Fecha/fuente:** 2026 (sin fecha exacta) · e4/EC-60 (prompts/v6_partials/confirmar_tools.md PASO 0)
- **Estado:** vigente
- **Riesgo de regresión:** el Confirmar curado dice "si identificás un turno próximo activo, ejecutá `confirmar_turno`" sin la condición de UN único turno; el canned vivo termina con "¡Muchas gracias!" (distinto del "Gracias!" de la fuente; se toma el vivo por más reciente); se perdió la prohibición de recitar fecha/día/hora; la prohibición queda solo para "montos". Verificar con 0 y 2+ turnos próximos.

### CON-03 · El bot confirmaba DOS turnos: el "No confirmado" y el fantasma "Cambio de fecha"
- **Entrada/disparador:** paciente confirma el recordatorio; en agenda hay una cita "No confirmado" (9:50) y otra "Cambio de fecha" (9:40). Raquel: "El único turno que tiene que confirmar el agente es el que dice No confirmado. El Cambio de fecha es un turno que ya no existe". Chat de Pilar: "no sé por qué tengo dos turnos" (también caso Samanta).
- **Falla previa:** el bot confirmaba/ofrecía ambos y el paciente quedaba confundido (la más crítica del feedback del 3/6).
- **Esperado:** único estado accionable = "No confirmado"; excluir "Cambio de fecha" (id_estado 14), "Anulado" (1) y "Atendido"; si queda un solo turno No confirmado, operar sin preguntar "¿cuál?"; si quedan 0, no hay turno pendiente. `confirmar_turno` nunca se llama sobre una cita id_estado 14.
- **Capa:** nodo/filtro (tools de turnos y workflows) + prompt (`id_estado != 1 Y != 14`)
- **Test:** SIN TEST (el PDF lista el QA pendiente: "Un turno No confirmado + uno Cambio de fecha -> solo ve/confirma el No confirmado")
- **Fecha/fuente:** 2026-06-03 · e4/EC-52 (docs/Asiri - Feedback Raquel 03-06.pdf punto 3; prompts/v6_partials/confirmar_tools.md)
- **Estado:** vigente
- **Riesgo de regresión:** ALTO. El Confirmar curado no menciona id_estado 14/1 ni "solo No confirmado"; la rama B usa `ver_turnos_paciente` y "turno activo próximo" sin filtro. Verificar que el filtro viva en la tool (o restaurar la regla en el prompt).

### CON-04 · "Confirmo" sin pago en consultas: el bot confirma cualquier "confirmo" (R7)
- **Entrada/disparador:** paciente de PRIMERA CONSULTA responde "confirmo" al recordatorio nuevo que exige abonar el valor de la consulta ("la confirmación es sí o sí con el pago").
- **Falla previa:** Sub-Agent Confirmar marca confirmado en Dentalink cualquier "confirmo" sin verificar pago; solo el comprobante (PASO 0) escala. La regla queda solo en el texto del recordatorio, sin gate.
- **Esperado:** sin resolver (decisión R7): ¿dejar de confirmar consultas sin comprobante? Mientras tanto, agregar "Tipo: consulta (se confirma con el pago)" a la NOTA INTERNA (P3). Si se decide que exige pago: ante "confirmo" de consulta sin comprobante, `confirmar_turno` NO se llama.
- **Capa:** otra (decisión de negocio abierta; sin capa que lo haga cumplir). Prompt pendiente.
- **Test:** SIN TEST (relacionado, no cubre: `tests/test_recordatorio_consultas.js` valida el texto del recordatorio, no el gate)
- **Fecha/fuente:** 2026-09-08 · e1/EC-21 (current-state.md "Decisión abierta R7") + e3/EC-54 (BKL P2/P3; OQ) + e4/EC-58 (docs/recordatorio-consultas-2026-09-08.md §8 #2)
- **Estado:** pendiente de decisión (Dra./Lucas)
- **Riesgo de regresión:** el Confirmar curado confirma cualquier "confirmo" que tenga fila abierta; no hay distinción consulta/tratamiento. La regla de pago nunca estuvo en el prompt, así que no es una pérdida de la curación, pero tampoco hay NOTA INTERNA "Tipo: consulta" que la sostenga.

### CON-05 · "Confirmo" + varias filas abiertas: iterar y confirmar TODAS (caso G.)
- **Entrada/disparador:** paciente con el mismo teléfono para varios pacientes responde "confirmo", "confirmados", "si", "dale", "voy", "ahí estaré", 👍.
- **Falla previa:** el agente confirmaba solo la primera fila.
- **Esperado:** PASO 0 `consultar_recordatorios_abiertos` (source of truth); ejecutar `confirmar_turno` + `marcar_recordatorio_confirmado` UNA VEZ POR FILA antes de armar la respuesta consolidada; con mención explícita ("confirmo el de Jana") matchear por `nombre_paciente` y confirmar solo ese; caso mixto (confirmar uno y cancelar otro) -> `escalar_a_secretaria("dividir flow")`.
- **Capa:** prompt
- **Test:** SIN TEST
- **Fecha/fuente:** regla anterior o igual al 2026-06-02 (sin fecha documentada) · e4/EC-53 (prompts/v6_partials/confirmar_paso0_recordatorios.md)
- **Estado:** vigente
- **Riesgo de regresión:** el vivo itera "para CADA fila" y consolida la respuesta, pero se perdieron el match por nombre ("confirmo el de Jana") y el caso mixto -> `escalar("dividir flow")`. Verificar ambos.

### CON-06 · Confirmar + pedido de alias en el mismo mensaje (Paulina): el alias se perdía
- **Entrada/disparador:** "Confirmo\nPor favor pásame el alias para que te transfiera el costo de la primera consulta" (conversaciones id 5747, 2/9).
- **Falla previa:** Sub-Agent Confirmar contestó solo "Listo, su turno del 4 de Septiembre a las 11:10 hs queda confirmado…" y NUNCA mandó el alias.
- **Esperado:** el Canned Sidecar determinístico anexa precio/alias cuando el paciente lo pidió y el sub-agent no lo incluyó; conserva intacto el texto del sub-agent; `sidecar='pago'`. La salida contiene la confirmación Y el alias.
- **Capa:** gate (Canned Sidecar)
- **Test:** `tests/test_canned_sidecar.py` ("REAL 2/9 Paulina (confirmo + alias)"); el E2E "Confirmar + alias mergeado" está como backlog P1 sin test (roadmap B5)
- **Fecha/fuente:** 2026-09-02 · e4/EC-59
- **Estado:** vigente

### CON-07 · Idempotencia: Dentalink 400 "Nuevo estado es igual al original"
- **Entrada/disparador:** `confirmar_turno(cita_id)` sobre un turno que ya estaba en id_estado 18.
- **Falla previa:** el agente lo trataba como error ("hubo un error") o escalaba.
- **Esperado:** NO es error: igual llamar `marcar_recordatorio_confirmado` y responder "Su turno del [fecha] a las [hora] ya queda confirmado…" (vale para cada fila al confirmar varias). No se llama a `escalar_a_secretaria`.
- **Capa:** prompt (confirmar_idempotencia)
- **Test:** SIN TEST
- **Fecha/fuente:** sin fecha · e4/EC-54 (prompts/v6_partials/confirmar_idempotencia.md)
- **Estado:** vigente (preservado en el vivo: "consideralo confirmado, cerrá la fila con `marcar_recordatorio_confirmado` y respondé cordial sin error")

### CON-08 · Turno ya confirmado (id_estado 18): no escalar, no llamar tools de más
- **Entrada/disparador:** paciente reafirma asistencia ("confirmo") sobre un turno ya confirmado en agenda.
- **Falla previa:** escalaba o llamaba `obtener_historial_paciente` (ruido).
- **Esperado:** canned sin `confirmar_turno`, sin escalar, sin historial. Texto fuente: "Su turno del [fecha natural] a las [hora natural] ya queda confirmado. Cualquier consulta nos puede escribir por este medio."
- **Capa:** prompt (PASO 2)
- **Test:** SIN TEST
- **Fecha/fuente:** sin fecha · e4/EC-55 (prompts/v6_partials/confirmar_tools.md PASO 2)
- **Estado:** vigente; contradicción de texto: el prompt vivo del 2026-10-04 usa "Su turno del [fecha natural] a las [hora natural] ya se encuentra confirmado. ¡Muchas gracias!". Se toma el vivo (más reciente); la fuente queda superada en el texto, no en la regla.

### CON-09 · Ventana de la migración v3: un "confirmo" a un recordatorio escalaba a Irina
- **Entrada/disparador:** paciente de los turnos del lun 20 / mar 21 contestaba "confirmo" antes de la fase 2 de la migración v3.
- **Falla previa:** las 3 tools de recordatorios (REST) no llegaban sin `sb_secret`.
- **Esperado:** con la credencial `supabaseApi` v3 y 9/9 nodos REST repunteados, el flujo queda operativo; con el Logger apagado a propósito no hay pérdida (la memoria v3 guarda todo y el cursor no avanza). `consultar_recordatorios_abiertos` y `marcar_recordatorio_confirmado` responden sin error de credencial.
- **Capa:** infra (credencial `supabaseApi`)
- **Test:** SIN TEST directo (`tests/test_e2e_bateria.py` valida la capa v3 con precio/cuota/alias/kb, no un "confirmo")
- **Fecha/fuente:** 2026-07-18 ("RESOLUCIÓN" + "FASE 2 COMPLETADA") · e2/EC-57
- **Estado:** superado por la migración v3 fase 2 (2026-07-18); sigue como dependencia de infra, porque el Confirmar vivo usa las mismas tools REST.

### CON-10 · Quien escribe NO es el paciente (madre/padre confirma el turno del hijo)
- **Entrada/disparador:** 3/3 confirmaciones post-recordatorio en la ventana retenida de 72 h fueron de madre/padre.
- **Falla previa:** n/a (funciona).
- **Esperado:** `consultar_recordatorios_abiertos` mapea teléfono -> cita directo en Supabase sin resolver fichas en Dentalink; la confirmación funciona sin preguntar quién es el paciente. Esta es la solución que SÍ resuelve familia en Confirmar y que el sub-WF Cancelar no usa.
- **Capa:** nodo (tool) + prompt (PASO 1 vivo)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06 · e4/EC-57 (docs/sesion-2026-07-06-precio-lid-reprogramacion.md §3 "Evidencia en vivo")
- **Estado:** vigente

### Cobertura
10 casos consolidados (de 12 crudos; los 3 crudos de R7 se fusionaron en CON-04). 8 SIN TEST (CON-01, 03, 04, 05, 07, 08, 09, 10); cubiertos: CON-02 (parcial, `tests/test_canned_sidecar.py`) y CON-06 (`tests/test_canned_sidecar.py`). No hay ningún test del comportamiento del Sub-Agent Confirmar.
Los 3 huecos más peligrosos: (1) CON-03 doble turno No confirmado / Cambio de fecha, sin filtro en el prompt curado y sin test; (2) CON-01 confirmar sin tool ni turno real (mentira al paciente), sin test y sin el bloque VALIDACION DE DESTINO; (3) CON-04 y CON-02 pago: "confirmo" de consultas sin pago confirma igual (decisión pendiente) y el comprobante confirma sin exigir turno único.
