# Catálogo consolidado: recordatorios + media_adjuntos

Base: casos crudos EC-xx de 4 extractores, deduplicados. Verificado contra workflow vivo y `live_prompts.md` al 2026-10-04. Los IDs EC-xx originales figuran en "Fecha/fuente". Nota: en los crudos "EC-45" aparece dos veces (flujo media_adjuntos, extractores 1 y 2); acá son MED-08 y MED-26.

## recordatorios

### REC-01 · Enviar WhatsApp con expresión n8n inválida + continueOnFail = cero recordatorios con status "success"
- **Entrada/disparador:** migración a Evolution GO; el `jsonBody` del nodo `Enviar WhatsApp` quedó con `{{ }}` anidados y `=` suelto (`"{{ String(={{ $json.X }}||"").replace(...) }}"`). La corrida cron de las 08:00 ART iba a ser la primera con el código nuevo.
- **Falla previa:** con `continueOnFail: true` el nodo fallaba en silencio, el workflow reportaba success y no salía ningún WhatsApp. Nadie lo había disparado desde el cambio.
- **Esperado:** tras tocar cualquier envío real, disparar el trigger manual con TEST_MODE y ver el mensaje llegar antes de confiar en el cron. Grepear la firma del bug (`={{`, `{{ String(=`) en TODOS los workflows activos de inmediato. "Actualizado" no es "probado".
- **Capa:** nodo + infra (regla de verificación)
- **Test:** SIN TEST (verificación manual TEST_MODE + trigger manual)
- **Fecha/fuente:** 2026-08-06 madrugada; EC-32, EC-68; bugs "Recordatorios: expresión rota" Bug 1; DEC "actualizado no es por-workflow" y "un bug de migración se grepea en TODOS".
- **Estado:** vigente (corregido con `apply_fix_recordatorios_enviar_whatsapp_expr.py`; el riesgo de silent failure sigue abierto, ver REC-03)

### REC-02 · Recordatorio multilínea rompe el JSON del body ("The value in the JSON Body field is not valid JSON")
- **Entrada/disparador:** tras corregir solo la sintaxis (REC-01), el envío real devolvió "not valid JSON": el template del recordatorio tiene `\n` reales.
- **Falla previa:** el body armado con interpolación de string rompía con saltos de línea.
- **Esperado:** `{{ JSON.stringify($json.message) }}` sin comillas propias, y lo mismo para `number`. El envío de un recordatorio multilínea real devuelve 2xx y llega el texto completo. Verificado con un recordatorio real a Lucas en TEST_MODE (turno de una paciente, viernes 7/8 10:00).
- **Capa:** nodo (`apply_fix_recordatorios_enviar_whatsapp_expr.py`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-06 madrugada; EC-33; bugs "Recordatorios: expresión rota" Bug 2.
- **Estado:** vigente

### REC-03 · Enviar WhatsApp con continueOnFail marca como enviado lo que Evolution rechazó
- **Entrada/disparador:** Evolution devuelve error al enviar el recordatorio (ej. "Erro ao enviar mensagem de texto").
- **Falla previa:** no hay error branch; la fila de `recordatorios_enviados` queda como enviada y el paciente nunca lo recibió. El resumen diario solo dice "Errores Evolution: N"; el error real viene dentro del item y el workflow figura "success".
- **Esperado:** validar la respuesta de Evolution antes de insertar la fila; si falla, no marcar enviado y escalar al helper. Ante "Errores Evolution: N" en el resumen, leer la ejecución y contar items nodo por nodo.
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-02 (docs/sesion-2026-06-02-fixes-y-backlog.md "Silent failures"); lección 2026-07-22; EC-157.
- **Estado:** pendiente de decisión (backlog 2/6; el fix posterior de 6/8 corrigió la expresión, no agregó error branch)

### REC-04 · TEST_MODE olvidado en `true` mandaría todos los recordatorios a Lucas
- **Entrada/disparador:** se activa `TEST_MODE` en `Preparar mensaje` (redirige todo al `TEST_PHONE` con prefijo `[TEST 24h/72h]`, ej. "[TEST 72h] Para: Martina (…)").
- **Falla previa:** riesgo crítico: si queda en `true`, la corrida real de las 08:00 ART le manda todo a Lucas y los pacientes no reciben nada. Residuo real: 3 filas del 5/8 en `recordatorios_enviados` (citas 8633 x2 y 8634, pacientes reales) con el teléfono de Lucas por TEST_MODE.
- **Esperado:** revertir a `false` en el mismo turno (`apply_toggle_recordatorios_test_mode.py --on/--off`); el jsCode conserva el literal `const TEST_MODE = false;` (el script lo busca); filas de prueba en `recordatorios_enviados` limpiadas (regla dura 9). Mismo patrón en la prueba del orden multi-turno (REC-23).
- **Capa:** nodo (flag) + infra (proceso)
- **Test:** parcial: `tests/test_recordatorio_consultas.js` §11, §13 (literal y prefijo); SIN TEST de que el flag quede en `false` en el vivo
- **Fecha/fuente:** 2026-08-06 madrugada; 2026-08-09/10; 2026-09-08; EC-34, EC-154 (parte TEST_MODE).
- **Estado:** vigente

### REC-05 · Detección de CONSULTA por `motivo_atencion` anclada: "Control post consulta" no es consulta
- **Entrada/disparador:** puntito amarillo de la Dra. = motivo `Consulta Ortodoncia ` (espacio final). Otros motivos reales: "En TTO LARGO", "En TTO CORTO", "Inicio TTO de Ortopedia", "Control Contención ", "Devolución con escaneo ", "No registra motivo".
- **Falla previa:** el substring `/consulta/i` daba true para "Control post consulta" o "Consultar precio" y le habría pedido el pago de la consulta a un paciente en tratamiento. `tratamiento_sin_asignar` es 0 en 66/66 citas próximas: no sirve como señal.
- **Esperado:** `es_consulta = /^consulta\b/i.test(motivo.trim())`. false: "Consultar precio", "Consultas", "Control post consulta", "Primera Consulta"; true: "Consulta", "CONSULTA", "consulta ortodoncia", "Consulta-Ortodoncia", " Consulta Ortodoncia "; null/undefined -> false. Asimetría buscada: un falso negativo (genérico) no daña, un falso positivo (pide pago a paciente en tratamiento) sí. Verificado en 66 citas próximas + 57 enviadas en 14 días: único motivo con esa palabra es `Consulta Ortodoncia `. `--rollback` solo con archivo `_PRE_`; revisar a mano la 1ª corrida real.
- **Capa:** nodo (`Preparar mensaje`, `recordatorios/preparar_mensaje.js`)
- **Test:** `tests/test_recordatorio_consultas.js` (87/87; §7 motivos, 14 casos)
- **Fecha/fuente:** 2026-09-08; EC-18, EC-70, EC-146; current-state "Recordatorio DISTINTO para las CONSULTAS", docs/recordatorio-consultas-2026-09-08.md §2, §8 #1.
- **Estado:** pendiente de decisión (abierto: confirmar con la Dra. que "puntito amarillo" = motivo `Consulta Ortodoncia` y si hay otro motivo de primera visita; 'Primera Consulta' hoy da falso negativo)

### REC-06 · Pedido de la Dra.: recordatorio distinto para CONSULTAS con pago obligatorio
- **Entrada/disparador:** Dra. (WhatsApp 8/9 09:20): "los turnos que tienen un puntito amarillo son consultas… a todos ellos el agente le envíe un mensaje en particular… Lo que quiero lograr es que sepan que la confirmación es sí o sí con el pago (esto solo en consultas)".
- **Falla previa:** las 5 consultas de los últimos 14 días (citas 8626, 8831, 8834, 8692, 8773) recibieron el template genérico sin pedir pago.
- **Esperado:** para `es_consulta`, el mensaje es el bloque textual de la Dra. ("Para confirmar su asistencia le solicitamos abonar el valor de la consulta ($50.000). … Si su turno ya está abonado, solo responda con un "confirmo"…"); precio dinámico desde `knowledge_base` id 21; TODO lo que no es consulta queda byte a byte igual al vivo.
- **Capa:** nodo (`Preparar mensaje`)
- **Test:** `tests/test_recordatorio_consultas.js` ("consulta 72h: mensaje === bloque textual de la Dra."; "tratamiento: igual al vivo")
- **Fecha/fuente:** 2026-09-08; EC-145; docs/recordatorio-consultas-2026-09-08.md §1-§3.
- **Estado:** pendiente de decisión (último dato 8/9: preparado y testeado, NO aplicado; verificar en el workflow vivo si se aplicó)
- **Riesgo de regresión:** el Sub-Agent Confirmar vivo (curado 4/10) ejecuta `confirmar_turno` ante cualquier "confirmo" con fila pendiente y no mira `es_consulta` ni el pago; la promesa del recordatorio ("la confirmación es sí o sí con el pago") no la hace cumplir ningún prompt. Verificar qué hace Confirmar con una consulta sin pago registrado.

### REC-07 · Irina apaga/prende recordatorios a mano y nadie confirma lunes/martes (incidente recurrente)
- **Entrada/disparador:** Irina pidió apagar los recordatorios porque ya había confirmado a mano; Lucas entendió "reactivar el lunes" en vez del día siguiente (feriado); el viernes Irina se encontró sin confirmaciones de lunes/martes y trabajó el fin de semana. Raquel: "esto ha sido una macana… la idea es que esto nos saque trabajo, no al revés".
- **Falla previa:** no es bug de código: el fix técnico del 14/7 (agenda de Dentalink como fuente de verdad) sigue sano. El gap es de proceso: Irina pide on/off del bot en vez de gestionar todo por Dentalink.
- **Esperado:** cancelar EN la agenda (el workflow filtra `id_estado != 1` en el GET) y marcar CONFIRMADO en la agenda (condición skip `id_estado != 18`); feriados: confirmar de antemano en agenda, sin infraestructura de "detectar feriado"; "no más on/off manual". Si ocurre una 3ª vez: alerta al staff sobre el flujo correcto.
- **Capa:** nodo (filtros del GET + IF) + infra (proceso/comunicación)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-14 (decisión) y 2026-08-15 (reincidencia); EC-22, EC-67, EC-158; docs/reunion-2026-07-14-dra-raquel.md, docs/reunion-2026-08-15-dra-raquel.md; DEC "gap de proceso, no de código"; BKL "Cerrado: feriados".
- **Estado:** vigente (revisable si hay una 3ª reincidencia)

### REC-08 · Recordatorios duplicados 3x a pacientes del martes
- **Entrada/disparador:** cron diario `0 13 * * *` + `addBusinessDays(hoy, 2)`: viernes, sábado y domingo convergían al martes (2026-05-08/09/10).
- **Falla previa:** 3 recordatorios al mismo paciente.
- **Esperado:** cron `0 13 * * 1-5` (solo lun-vie); pacientes con turno sáb/dom no reciben recordatorio (clínica cerrada). Un paciente recibe un solo recordatorio por cita.
- **Capa:** nodo (cron)
- **Test:** SIN TEST ("validable martes 19/5", sin test)
- **Fecha/fuente:** 2026-05-11; EC-63; BUGS #5; FIXES R2 #2; docs/architecture.md.
- **Estado:** vigente (superó al cron diario `0 13 * * *`)

### REC-09 · Emparejamiento por `$itemIndex`: un nodo intercalado cruza citas entre pacientes
- **Entrada/disparador:** `Preparar mensaje` empareja la cita por `$("Solo citas activas").all()[$itemIndex]`; cualquier nodo intercalado, o `¿Ya se recordó?` salteando un ítem (3 citas: el ítem 1 toma la cita 2, 10:30 consulta).
- **Falla previa:** regresión real del 11/8 al intercalar un nodo; riesgo R2: hora/fecha/`es_consulta` cruzados entre pacientes. Hoy 0 skips en 14 días (0/10 ejecuciones), pero es frágil.
- **Esperado:** no intercalar nodos; arreglo posible `$('Solo citas activas').item.json` (pairedItem) con fallback al índice, en PUT aparte (P3). Mientras tanto se testea que `$itemIndex=1` -> cita 2 y `$itemIndex=2` -> cita 3.
- **Capa:** nodo
- **Test:** `tests/test_recordatorio_consultas.js` (§10)
- **Fecha/fuente:** 2026-08-11 y 2026-09-08; EC-69, EC-151; DEC recordatorio de consultas; BKL P3; docs/recordatorio-consultas-2026-09-08.md §8 #5.
- **Estado:** vigente (P3 sin aplicar)

### REC-10 · Celular extranjero con "+" recibía prefijo 549 y fallaba el envío
- **Entrada/disparador:** resumen diario del 22/7 "4 enviados / 1 error Evolution": número de Bolivia `+591…` -> `549591…` -> "Erro ao enviar mensagem de texto" (exec 237284). Alcance: 3 de 649 pacientes de Dentalink (Bolivia x2, España x1); Jujuy es frontera con Bolivia, reaparece. Formatos probados: argentino de 10 dígitos sin prefijo, con 54, con 549, con 15 intermedio, con 0, con espacios y guiones (7 formatos), paciente sin celular.
- **Falla previa:** `Preparar mensaje` asumía pacientes argentinos; la rama catch-all `if (!celular.startsWith("54")) celular = "549" + celular` pegaba 549 porque el `+` se perdía en el `replace` previo.
- **Esperado:** `esInternacional = /^\s*\+/.test(celular)` leído ANTES del replace; el extranjero queda tal cual (sin "+", remoteJid `…@s.whatsapp.net`); los argentinos se normalizan a `549…`; sin celular -> `phone` y `message` vacíos (rama `Tiene celular?` false); salida idéntica al nodo vivo.
- **Capa:** nodo (`apply_fix_telefono_internacional.py`)
- **Test:** `tests/test_recordatorio_consultas.js` §9 (el fix original de 22/7 no tuvo test propio)
- **Fecha/fuente:** 2026-07-22 y 2026-09-08; EC-49, EC-153; "Panel LIVE… BUG DE PRODUCCIÓN".
- **Estado:** vigente

### REC-11 · Primer batch (6 envíos) falló: la lógica heredada quitaba el "9" tras 54
- **Entrada/disparador:** números de Jujuy (388) y Córdoba (351).
- **Falla previa:** la lógica heredada quitaba el 9 (sirve para Buenos Aires, falla en el interior).
- **Esperado:** mantener el "9" tras 54 (formato `549…`) y testear con números del interior.
- **Capa:** nodo
- **Test:** SIN TEST (cobertura indirecta de normalización a 549 en `tests/test_recordatorio_consultas.js` §9, sin casos 388/351 explícitos)
- **Fecha/fuente:** ~2026-04; EC-64; BUGS #7.
- **Estado:** vigente

### REC-12 · Fila de `recordatorios_enviados` con teléfono roto: el "confirmo" no matchea
- **Entrada/disparador:** Isabel (cita 8529, 24/7 09:10) no recibió el recordatorio 72h; se le mandó a mano; su fila (id=26) quedó con el teléfono roto.
- **Falla previa:** `consultar_recordatorios_abiertos` busca por teléfono, así que su "confirmo" no habría matcheado la fila.
- **Esperado:** al reenviar a mano, corregir también la fila de `recordatorios_enviados`. Ante "Errores Evolution: N" leer la ejecución y contar items (REC-03).
- **Capa:** infra (datos/proceso)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-22; EC-50.
- **Estado:** vigente
- **Riesgo de regresión:** Confirmar vivo sigue llamando `consultar_recordatorios_abiertos(phone)` primero; su rama B (0 filas -> `ver_turnos_paciente`) es la red de seguridad. Verificar que se mantenga esa rama.

### REC-13 · El recordatorio nunca quedaba en `n8n_chat_histories` (newlines literales en strings)
- **Entrada/disparador:** cron del recordatorio, nodo `Guardar en Chat Memory`.
- **Falla previa:** strings con saltos de línea literales dentro de `'…'` rompían el parse JS; los recordatorios NUNCA quedaban en la memoria y el bot no sabía que el último AI era el recordatorio.
- **Esperado:** template literals (backticks); tras la corrida real del cron hay 2 filas por paciente: el recordatorio + la NOTA INTERNA.
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-02; EC-156; docs/sesion-2026-06-02-fixes-y-backlog.md fix #1.
- **Estado:** vigente

### REC-14 · NOTA INTERNA del recordatorio sin `id_paciente` (raíz del caso Carmen)
- **Entrada/disparador:** paciente responde a un recordatorio.
- **Falla previa:** la nota solo guardaba `cita_id`; el bot rebuscaba al paciente por celular (campo derivado, heterogéneo).
- **Esperado:** persistir `id_paciente` en `additional_kwargs.id_paciente` con `source: reminder_note`; el bot usa los datos de la nota (cita_id/fecha/hora/id_paciente) y no pide que el paciente los repita.
- **Capa:** nodo + prompt
- **Test:** SIN TEST
- **Fecha/fuente:** ~2026-04; EC-65; BUGS #8; regla "MEMORIA ANTES QUE PREGUNTA" del prompt.
- **Estado:** vigente
- **Riesgo de regresión:** la regla "MEMORIA ANTES QUE PREGUNTA / NOTA INTERNA" vive hoy solo en el nodo muerto Sub-Agent Urgencia; Agendar vivo busca por `phone_last10` (el celular derivado que se quiso evitar) y General no menciona la nota. Verificar que Agendar/Confirmar/General usan `id_paciente` de la nota cuando existe.

### REC-15 · `Clear Old Memory` borraba la NOTA INTERNA del recordatorio si la sesión era stale
- **Entrada/disparador:** paciente recibe el recordatorio el lunes y responde el viernes (>3 días).
- **Falla previa:** DELETE indiferenciado; el bot pedía el DNI desde cero.
- **Esperado:** DELETE selectivo que preserva `wa_outbound`, `human_takeover` y `reminder_note`; `Handle Stale Session` ya no referencia `Supabase - Buscar Paciente`.
- **Capa:** nodo (SQL)
- **Test:** SIN TEST (sin shadow real)
- **Fecha/fuente:** detectado 2026-05-09, aplicado 2026-05-12; EC-66; BUGS #26; FIXES R2 #9.
- **Estado:** vigente

### REC-16 · El v6 reconoce "el último AI fue el recordatorio" por dos señales de texto
- **Entrada/disparador:** el paciente responde horas después; el bloque nuevo de consultas cambia el texto del recordatorio.
- **Falla previa:** riesgo: si se pierde "AUREA ODONTOLOGIA ESTETICA" al inicio o "Le recordamos su turno con la Dra. Rodriguez Raquel", el Router y los sub-agents no reconocen el recordatorio (afirmaciones/emojis post-recordatorio, presentación de Asiri).
- **Esperado:** todo mensaje de recordatorio (genérico y de consulta) empieza con "AUREA ODONTOLOGIA ESTETICA" y contiene "Le recordamos su turno con la Dra. Rodriguez Raquel".
- **Capa:** nodo + prompt
- **Test:** `tests/test_recordatorio_consultas.js` ("señales que el v6 usa para reconocer el recordatorio en memoria")
- **Fecha/fuente:** 2026-09-08; EC-150; docs/recordatorio-consultas-2026-09-08.md §5; prompts/v6_partials/header_common.md.
- **Estado:** vigente
- **Riesgo de regresión:** en `live_prompts.md` la señal "empieza AUREA…" y la identificación de Asiri tras el recordatorio (caso c) solo figuran en el nodo muerto Sub-Agent Urgencia; Router, Agendar, Confirmar y General curados no la nombran, y el parcial `header_common.md` no aparece. Verificar que el reconocimiento sobrevive (Router: "turno recordado"; presentación de Asiri en el primer mensaje post-recordatorio).

### REC-17 · Cita "Cambio de fecha" (id_estado 14) o anulada recordada/confirmada por error ("turno fantasma")
- **Entrada/disparador:** en la agenda aparecen "Cambio de fecha" y "No confirmado" para el mismo paciente (feedback Raquel 3/6).
- **Falla previa:** el recordatorio y la confirmación tomaban ambos turnos.
- **Esperado:** el workflow filtra `id_estado != 1` (anulado) y `!= 18` (confirmado); los prompts de Confirmar/Cancelar/Agendar/General ignoran `id_estado == 14`.
- **Capa:** nodo + prompt
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-06-03; EC-159; docs/Asiri - Feedback Raquel 03-06.pdf punto 3; prompts/v6_partials/*.
- **Estado:** vigente (la parte de prompt de Cancelar es nodo muerto; Cancelar es hoy el sub-workflow determinístico 5cAWJxiWJ50hxEq3)
- **Riesgo de regresión:** `live_prompts.md` no menciona `id_estado != 14` en Agendar/Confirmar/General (Confirmar solo conoce 18). Verificar que el filtro 14 quedó en las tools o en el sub-workflow de cancelar.

### REC-18 · Precio de la consulta en el recordatorio: formatos raros de la KB ("$ 55.000", "$50mil", "$5")
- **Entrada/disparador:** `knowledge_base` id 21 (la Dra. lo edita en el panel) con "$50.000", "$ 55.000", "$  70.000", "$60.000.", "$ 45,000", "$50mil", "$5", "$50.000,00", "$1.500.000; consulta $50.000", "$50000", "u$s 100", "$ abc", null.
- **Falla previa:** el regex laxo imprimía "$50" para "$50mil"; el estricto del v6 (`/\$[\d.,]+/`) ante "$ 55.000" caía al fallback y el paciente recibía un precio VIEJO ($50.000) en silencio. Desalineación: el v6 (`Extraer Horarios y Precio`) seguiría contestando $50.000 si la KB dice "$ 55.000".
- **Esperado:** regex `/\$\s*(\d{1,3}(?:[.,]\d{3})+|\d{4,})/` (cualquier cantidad de espacios); importes reales con separador de miles o 4+ dígitos; "$50mil", "$5", "u$s 100", "$ abc", sin "$" o null -> fallback `$50.000` (`precio_origen: 'fallback'`); varios importes -> el primero; "$50.000,00" -> "$50.000". Subconsulta `precio_contenido` en el SQL de `Gate - Leer config`, leída con try/catch.
- **Capa:** nodo (`Preparar mensaje` / `Gate - Leer config`)
- **Test:** `tests/test_recordatorio_consultas.js` (§5, 13 casos de precio)
- **Fecha/fuente:** 2026-09-08; EC-19, EC-71, EC-147; DEC; BKL; docs/recordatorio-consultas-2026-09-08.md §4.
- **Estado:** vigente (pendiente P3: alinear el regex del v6)

### REC-19 · Camino manual (webhook / botón "adelantar") no pasa por el Gate: precio siempre fallback
- **Entrada/disparador:** `POST /webhook/trigger-recordatorios-manual {"fecha_target":…, "id_paciente_filter":[…]}` (ints), o el botón "adelantar" del panel, que manda solo `fecha_target` y por eso va a TODOS los pacientes de esa fecha.
- **Falla previa:** `$('Gate - Leer config')` tira (nodo no ejecutado) -> fallback $50.000 aunque Raquel cambie el precio en el panel.
- **Esperado:** try/catch -> fallback sin romper; opcional (P2/R4) un nodo "Precio consulta (KB)" entre el webhook y `Fecha Mañana`; NO usar el botón "adelantar" para pruebas; prueba real con el paciente de prueba id 608 vía webhook con `id_paciente_filter` + limpieza regla 9.
- **Capa:** nodo
- **Test:** `tests/test_recordatorio_consultas.js` ("manual sin Gate: no tira y usa el fallback"; "manual sin Gate, tratamiento: igual al vivo")
- **Fecha/fuente:** 2026-09-08; EC-148; docs/recordatorio-consultas-2026-09-08.md §3.2, §4, §6.3.
- **Estado:** vigente (P2 sin aplicar)

### REC-20 · Hora real del cron: 08:00 ART (no 9 AM) y cambio horario europeo
- **Entrada/disparador:** cron `0 13 * * 1-5` sin timezone en una instancia UTC+2; el nodo se llama "Diario 9AM Arg (cron 0 14 UTC)"; bugs.md/runbook dicen 8 AM, architecture/CLAUDE.md dicen 9 AM.
- **Falla previa:** docs inconsistentes; en realidad corre 08:00 ART lun-vie; al cambio horario europeo (2026-10-25) pasaría a 09:00 ART salvo que se normalice la timezone.
- **Esperado:** hora ART = (hora_arg + 5) UTC según la lección; el apply no toca settings ni trigger (aborta si aparece `timezone`); Lucas confirmó 08:00 ART; el primer envío real con cambios de bloque sale por el cron (checklist de revisión + rollback listo). Revisar la timezone antes del 2026-10-25.
- **Capa:** infra (config del workflow)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-04, 2026-06-02, 2026-07-18, 2026-09-08; EC-20, EC-72, EC-155; BUGS #10; BKL P3 (renombrar cron); docs/auditoria-propuestas-a3-2026-07-18.md.
- **Estado:** pendiente de decisión (CLAUDE.md "cron 9 AM" superado por 08:00 ART; falta decidir timezone antes del 25/10 y renombrar el nodo)

### REC-21 · El recordatorio 24h nunca sale por cron (solo 72h; 24h solo por webhook manual)
- **Entrada/disparador:** premisa de diseño "existe el 24h" contradicha por datos: `Fecha Mañana` apunta a +2 días hábiles; 57/57 envíos de 14 días fueron 72h.
- **Falla previa:** la variante consulta-24h solo existe por webhook manual; hoy nadie recibe un 24h.
- **Esperado:** la Dra. debe validar la frase del 24h antes de usarla; no asumir que se probó por cron. Una prueba real de 24h se hace por webhook manual (ver REC-19).
- **Capa:** infra (cron/config) + nodo
- **Test:** `tests/test_recordatorio_consultas.js` (solo el mensaje 24h de consulta); que el cron no lo dispara: SIN TEST
- **Fecha/fuente:** 2026-09-08; EC-20, EC-72, EC-148; current-state "Hechos que corrigen premisas".
- **Estado:** pendiente de decisión (validar frase 24h con la Dra.; CLAUDE.md lo da por funcionando: "Recordar 24h y 72h")

### REC-22 · Plantillas 24h/72h y trato por género (Estimada / Estimado / Estimado/a)
- **Entrada/disparador:** pacientes Martina, Santiago, Alexis, María José.
- **Falla previa:** n/a (especificación testeada).
- **Esperado:** 72h formal con política de cancelación 48 h; 24h corto y cálido; primer nombre terminado en "a" -> "Estimada … la esperamos"; en "o" -> "Estimado … lo esperamos"; otra letra -> "Estimado/a … le esperamos". Observación: el 24h usa "la esperamos/lo esperamos", frase que el Banlist bloquea en respuestas del bot; el recordatorio sale directo por el cron y no pasa por el Banlist (no exigir ausencia de esa frase en recordatorios, sí en respuestas del bot).
- **Capa:** nodo
- **Test:** `tests/test_recordatorio_consultas.js` (§8 género)
- **Fecha/fuente:** 2026-04 y 2026-09-08; EC-72 (plantillas), EC-152.
- **Estado:** vigente

### REC-23 · Paciente con 2+ turnos el mismo día: recordatorios en orden invertido
- **Entrada/disparador:** pedido real de la Dra.; Ignacio A. con turnos 11:10 y 11:40 mandados invertidos.
- **Falla previa:** no se ordenaban por hora.
- **Esperado:** nodo `Ordenar Citas por Hora` entre `GET Citas por fecha` y `Split Citas`: sort global por `hora_inicio`, escala a cualquier cantidad de turnos por paciente. Filas de prueba en `recordatorios_enviados` limpiadas tras la prueba.
- **Capa:** nodo (`apply_fix_recordatorios_orden_multiturno.py`)
- **Test:** SIN TEST (exec 255176 con TEST_MODE)
- **Fecha/fuente:** 2026-08-09/10; EC-38.
- **Estado:** vigente

### REC-24 · Columnas nuevas deben existir ANTES del apply (el Insert corre después del envío)
- **Entrada/disparador:** `--apply` del recordatorio antes de `--ddl`.
- **Falla previa:** el nodo Postgres v2.6 valida contra la tabla viva y el Insert corre DESPUÉS de `Enviar WhatsApp`: los WhatsApps salen y el Insert explota -> 0 filas en `recordatorios_enviados` -> `consultar_recordatorios_abiertos` no encuentra el turno cuando el paciente responde "confirmo".
- **Esperado:** orden obligatorio `--ddl` (ALTER TABLE ADD COLUMN IF NOT EXISTS `motivo_atencion`, `es_consulta`; filas viejas NULL = desconocido, no backfillear como false) y luego `--apply`; el script se niega si la tabla no tiene las columnas; tipos de salida: `es_consulta` boolean, `motivo_atencion` string.
- **Capa:** infra (script apply con guard)
- **Test:** parcial: `tests/test_recordatorio_consultas.js` (contrato de tipos de salida); el guard del script: SIN TEST
- **Fecha/fuente:** 2026-09-08; EC-149; docs/recordatorio-consultas-2026-09-08.md §5.
- **Estado:** vigente (condicionado a que REC-06 se aplique)

### REC-25 · Gate de suspensión (`recordatorios_config`, `dias_suspendidos`): fail-open, auto-resume, finde no-op
- **Entrada/disparador:** diseño del gate (14 -> 17 nodos); `Gate - Leer config` devuelve `suspender`; falta la fila o PG caído.
- **Falla previa:** n/a (diseño); riesgo: tocar el SQL al sumar `precio_contenido`.
- **Esperado:** si falta la fila o PG está caído, el workflow corre igual (fail-open). Suspender un día es una fecha que al día siguiente ya no está (auto-resume). El cron es lun-vie: suspender un finde es no-op y el panel lo marca "finde · no aplica". La columna `suspender` del SQL queda EXACTAMENTE igual (solo se suma `precio_contenido`); el SQL es solo lectura.
- **Capa:** nodo (gate)
- **Test:** parcial: `tests/test_recordatorio_consultas.js` §11, §13 (columna `suspender` intacta); fail-open/auto-resume: SIN TEST
- **Fecha/fuente:** 2026-07-19 ("Recordatorios — diseño escalable") y 2026-09-08; EC-51, EC-154 (parte gate).
- **Estado:** vigente

### REC-26 · Recordatorio 48h no corrió el 14/7 tras el incidente de Supabase v2 (backfill)
- **Entrada/disparador:** recordatorios del 16/7 y 17/7 tras el incidente de Supabase v2; Lucas se colgó con las 08:00 y hubo disparo manual.
- **Falla previa:** el bot no escribía en `recordatorios_enviados`; el workflow necesitó disparo manual.
- **Esperado:** backfill de 13 filas en v3 con `wa_message_id`; exec 222062 = 8 citas -> 4 WhatsApps; vigilar la 1ª corrida real contra v3 (lunes 20/7 08:00 ART).
- **Capa:** nodo + infra (proceso)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-14/18; EC-73; BKL post-incidente.
- **Estado:** vigente (histórico; cerrado si la corrida del 20/7 salió bien, sin confirmación en las fuentes)

### Cobertura
- 26 casos; 14 SIN TEST (REC-01, 02, 03, 07, 08, 11, 12, 13, 14, 15, 17, 20, 23, 26) y 4 con cobertura solo parcial (REC-04, 21, 24, 25). Todo lo cubierto está en un único archivo, `tests/test_recordatorio_consultas.js`, centrado en el bloque de consultas.
- Huecos más peligrosos: (1) el envío real: nada verifica status de Evolution ni el JSON del body (REC-01, 02, 03), un recordatorio puede fallar con workflow "success" y fila marcada enviada; (2) la memoria y el contexto post-recordatorio (REC-13, 14, 15, 16) dependen de nodos y de prompts curados el 4/10 sin test que lo vigile; (3) filtros de agenda y cron (REC-08 duplicados, REC-17 id_estado 14) más el proceso de Irina (REC-07) sin test.

## media_adjuntos

### MED-01 · Comprobante de pago y fotos tratados como si no hubieran llegado (Switch de media muerto tras migrar a Evolution GO)
- **Entrada/disparador:** Samira mandó un comprobante de MercadoPago (PDF) a las 19:45 y se perdió sin rastro; cualquier adjunto del paciente tras la migración.
- **Falla previa:** `Switch - Tipo Mensaje` ruteaba por `image_url`/`audio_url`/`document_url`, que se armaban leyendo `imageMessage.url` (shape viejo) y quedaban siempre vacíos; ninguna rama de media matcheaba y el adjunto se perdía sin dejar marcador de texto.
- **Esperado:** Evolution GO NO expone URLs: manda el archivo en base64 en el webhook (`Info.MediaType`, `Message.base64`, `documentMessage.fileName/mimetype`; 100 % de 2048 execs). El Switch rutea por `Info.MediaType`; `Obtener Media`/`Obtener Imagen` son nodos `Set` que copian el base64. Con el payload real del comprobante debe rutear a "documento" y generar `[DOCUMENTO: …pdf (application/pdf)]`. El endpoint `/message/downloadmedia` nunca se verificó contra Evolution GO real. Test con payload REAL capturado.
- **Capa:** nodo (`apply_fix_evolution_go_media.py`)
- **Test:** parcial: `tests/test_media_nodos.js` (posterior, cubre Preparar); el ruteo del Switch: SIN TEST propio
- **Fecha/fuente:** 2026-08-05 noche (Fix 3); EC-44, EC-74; DEC "Verificar SIEMPRE con un test E2E real"; DEC 2026-09-06 (Adjuntos).
- **Estado:** vigente
- **Riesgo de regresión:** el Router curado no describe los marcadores `[IMAGEN]`/`[DOCUMENTO]`/`[AUDIO]` que recibe; solo dice que un comprobante es `confirmar_post_recordatorio`. Verificar el ruteo de un mensaje que es solo marcador.

### MED-02 · La cadena Media del staff debe ir DESPUÉS del label `humano` (riesgo clase Mariela)
- **Entrada/disparador:** el paciente escribe en t=0; la doctora contesta desde el celular del consultorio con un video/foto pesada (5 MB) en t=5 s; la subida tarda 25 s o Storage cuelga (timeout 30 s).
- **Falla previa:** si la cadena Media va delante de `CW Set Label humano`, el label (lo ÚNICO que calla al bot en la rama fromMe) llegaría recién en t≈31 s, cuando el pipeline del paciente (buffer + LLM + typing ≈ 25-30 s) ya terminó: el bot escribe encima de la doctora. El primer diseño fue bloqueado por la revisión adversarial.
- **Esperado:** los 6 nodos `Media: * (staff)` cuelgan de `CW Set Label humano`; `CW Set Label humano` corre ANTES de `Media: Subir a Storage (staff)` y el bot NO contesta; `Build fromMe AI memory` no se toca; `Postgres - Save fromMe` solo suma `RETURNING id`; el token llega por un UPDATE posterior por id.
- **Capa:** nodo (orden de conexiones del grafo)
- **Test:** SIN TEST (el orden solo lo verifica el dry-run de `apply_media_fromme.py`; prueba E2E pendiente; `tests/test_media_fromme.js` cubre los nodos, no el orden)
- **Fecha/fuente:** 2026-09-07; EC-79, EC-177; DEC "La cadena Media va DESPUÉS del label"; docs/media-entrantes-2026-09-06.md §8.1, §8.3 R5; BKL P1/P2.
- **Estado:** vigente (E2E pendiente)

### MED-03 · Comprobantes de pago (imagen/doc): recibir y derivar, sin validar monto
- **Entrada/disparador:** paciente manda un comprobante (imagen o PDF) o dice "te paso el comprobante", "ya transferí", "adjunto pago".
- **Falla previa:** (riesgo) el bot valide el monto o confirme el turno por su cuenta.
- **Esperado:** el bot recibe y deriva al grupo (`escalar_a_secretaria`); responde "Recibimos su comprobante. Le informo a la secretaria, que verificará el pago en su horario de atención. ¡Muchas gracias!"; NO valida monto ni dice si el pago ingresó; Irina verifica; documento/otros -> marcador para escalar.
- **Capa:** prompt + nodo
- **Test:** SIN TEST
- **Fecha/fuente:** AGENTS.md y .claude/CLAUDE.md (scope MVP); DEC 2026-08-15; EC-83.
- **Estado:** pendiente de decisión (contradicción: la fuente de 15/8 lista "confirme el turno" como riesgo, pero el Sub-Agent Confirmar vivo del 4/10, PASO 0, ejecuta `confirmar_turno(id_cita)` cuando identifica un turno próximo al recibir el comprobante; gana lo vivo, decidir si es lo deseado)
- **Riesgo de regresión:** verificar en Confirmar (PASO 0) el canned exacto, "PROHIBIDO validar montos", una sola llamada a `escalar_a_secretaria`, y que el Router sigue mandando comprobantes a `confirmar_post_recordatorio`.

### MED-04 · Adjuntos del staff a grupos, estados, difusión, canales y chats LID se subían bajo el número de la clínica
- **Entrada/disparador:** adjunto enviado desde el número de la clínica a `@g.us` (ej. grupo de derivaciones), `status@broadcast`, lista de difusión `<id>@broadcast`, canal `<id>@newsletter` o chat LID `<id>@lid`.
- **Falla previa:** la rama del staff no filtraba nada (el filtro @g.us / status@broadcast vive en `Filtrar duplicados y basura`, que cuelga de `Es fromMe?`[1], rama del paciente). `Extraer Datos` toma el primer candidato terminado en `@s.whatsapp.net`; si `Info.Chat` no es 1:1 cae a `Info.Sender` = el número de la clínica, que pasa el guard de largo: el archivo terminaba en `pacientes-media/<nro del consultorio>/…` y se pintaba en una conversación fantasma (reproducido con el archivo real).
- **Esperado:** tres guards en `media/preparar.js` (compartido, no-op para el paciente): (1) blacklist `@g.us`, `status@broadcast`, `@broadcast`, `@newsletter` -> motivo `grupo_o_estado`; (2) whitelist solo staff: `ED.fromMe && !/@s.whatsapp.net$/.test(info.Chat)` -> `grupo_o_estado` (cierra también `@lid` y cualquier familia futura); (3) largo de teléfono E.164 8-15 dígitos (15 sube; jid de grupo pelado de 18 dígitos -> `grupo_o_estado`; LID de 16-17 descartado a propósito). `sin_telefono`/`sin_base64` gana sobre `grupo_o_estado`. No se crea fila ni binario.
- **Capa:** nodo (`media/preparar.js`)
- **Test:** `tests/test_media_fromme.js` (§7, 7a-7h, JID no 1:1), `tests/test_media_nodos.js` §23 (83/83, 29 checks, borde de largo del LID)
- **Fecha/fuente:** 2026-09-07 (tarde y 2ª ronda); EC-31, EC-32, EC-78, EC-176; DEC "Whitelist de JID para el staff"; BKL P3; docs/media-entrantes-2026-09-06.md §8.3 R1.
- **Estado:** vigente (abierto: revisar si aparece un LID real de 16-17 dígitos, ver MED-14)

### MED-05 · Token `[MEDIA:id]` pegado a la fila equivocada (fallback heurístico por session_id + content)
- **Entrada/disparador:** la doctora manda dos adjuntos SIN caption al mismo paciente: los dos INSERT tienen `content` idéntico (TAG + placeholder), bajo concurrencia.
- **Falla previa:** el fallback "última fila de la sesión con el mismo content" con `ORDER BY id DESC LIMIT 1` pegaba el token ` [MEDIA:<id>]` a la fila equivocada: cada burbuja mostraba la foto de la otra (en un chat médico, peor que no mostrar ninguna).
- **Esperado:** fallback eliminado; sin `id` devuelto por `Postgres - Save fromMe` (`RETURNING id`) -> NOOP (falla cerrado); el UPDATE es `WHERE id = <n>` (bigint como string, validado `/^[1-9][0-9]{0,17}$/`), idempotente (`NOT LIKE '%[MEDIA:%'`), escape propio sin `queryReplacement`, nunca incluye texto libre del paciente/doctora (solo id de 16 hex y `media_tipo` del whitelist de 5); caption hostil con comilla/coma/`$` no rompe el SQL; `Build fromMe AI memory` y su TAG/placeholder no se tocan.
- **Capa:** nodo (`media/actualizar_memoria_staff.js`)
- **Test:** `tests/test_media_fromme.js` (69/69; 4a-4k incluido el caso concurrente, 5a-5f caption hostil, 3a-3m NOOP)
- **Fecha/fuente:** 2026-09-07 (tarde y 2ª ronda); EC-33, EC-80, EC-178; docs/media-entrantes-2026-09-06.md §8.2.
- **Estado:** vigente

### MED-06 · Adjunto del paciente: el texto debe quedar idéntico si falla cualquier paso de la cadena Media
- **Entrada/disparador:** foto/audio/PDF/sticker/ubicación del paciente con excepción en `Media: Preparar`, Storage o `Media: Registrar`. Casos: jpeg/png/mp4/ptt `; codecs=opus`/pdf, sticker PNG-disfrazado-de-webp, sticker Lottie, ubicación sin base64, base64 vacío, mime desconocido, `documentWithCaptionMessage`, MediaType vacío, video >20 MB, excepción interna ("disco lleno"), teléfono ausente o sin dígitos, `Preparar` devolviendo `{error}` (hoy inalcanzable; kill del sandbox).
- **Falla previa:** (riesgo) perder el mensaje del paciente o dejarle al Router un mensaje vacío por una falla de la cadena Media.
- **Esperado:** `hay_archivo:false` con motivo (`sin_base64`, `archivo_muy_grande`, `error:<msg>`, `sin_telefono`) y el `text` intacto; sin fila ni binario; el marcador del Set Marker recibe ` [MEDIA:<16 hex>]` solo si el INSERT salió bien; `Media: Marcar` rescata el texto del Set Marker que corrió si `Preparar` muriera fuera de su try/catch. Tope 20 MB como guard-rail del timeout de 30 s (n8n rechaza bodies >16 MB).
- **Capa:** nodo (`media/preparar.js`, `Media: Marcar`)
- **Test:** `tests/test_media_nodos.js` (45 -> 54/54 -> 83/83)
- **Fecha/fuente:** 2026-09-06 (noche) y 2026-09-07 madrugada; EC-43, EC-77, EC-174; current-state "Adjuntos del paciente a Storage (`media_entrantes`)"; docs/media-entrantes-2026-09-06.md §5.
- **Estado:** vigente

### MED-07 · Foto dental del paciente: el v6 la describe pero no la usa para clasificar; se deriva
- **Entrada/disparador:** paciente manda una foto dental (con o sin texto).
- **Falla previa:** toda imagen pasa por `OpenAI - Analizar Imagen` (gpt-4o) y entra al Router/memoria como "[IMAGEN] TIPO: FOTO_DENTAL … DESCRIPCION: …" + caption; la descripción es genérica y no decide el tipo de urgencia.
- **Esperado:** foto dental / consulta médica -> derivar (`escalar_a_secretaria`, sin diagnóstico ni consejo); la foto es solo respaldo para la doctora; no se usa visión para clasificar; multimedia sin texto -> marcar tipo + escalar; Whisper/visión del flow v7 se eliminan del MVP.
- **Capa:** prompt + nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-02/04; EC-186; docs/analisis-retrospectivo-urgencias-2026-09-02.md; docs/triaje-fase2-analisis/mapeo-read_router.md; docs/plan-mvp.md.
- **Estado:** vigente (el nodo "Sub-Agent Urgencia" del v6 está muerto: urgencia_dolor va al flujo Triaje)
- **Riesgo de regresión:** el Router curado no menciona fotos ni multimedia sin texto; solo General vivo cubre "fotos clínicas enviadas -> escalar". Verificar que una foto sin texto no cae en un sub-agent que improvise y que una foto con dolor llega a Triaje.

### MED-08 · El LLM ecoa el token `[MEDIA:id]` y el panel pinta el adjunto en la burbuja del bot
- **Entrada/disparador:** el Router/sub-agents/Formatting Agent ven ` [MEDIA:…]` en el mensaje y en el contexto (también en las filas `[ATENCION HUMANA …]`) y el bot repite el token en su respuesta.
- **Falla previa:** nada lo filtra en la salida; el panel pinta la foto en la burbuja verde del bot. Agujero conocido: si el LLM ecoa el TAG completo `[ATENCION HUMANA …]` junto con el token, `esMensajeDeStaff` da true y la burbuja del bot pinta el adjunto del staff. Cosmético: el token puede aparecer en el resumen `[ESCALADO BOT]` del grupo y en `triaje_urgencias_log.mensaje_paciente`.
- **Esperado:** (aplicado) los adjuntos se cuelgan SOLO a filas `rol === 'user'`, también en el dedupe de la lista; (pendiente P1 con la rama staff, R3) 2ª capa determinística `text.replace(/\s*\[MEDIA:[0-9a-f]{16}\]/g, '')` en `Banlist Validator` (o `Split en Mensajes`); ninguna respuesta del bot contiene `[MEDIA:`. Requiere OK aparte (regla dura 5).
- **Capa:** panel (aplicado) + banlist (pendiente)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-06 (noche) y 2026-09-07; EC-45 (extractor 1), EC-181; current-state "Adjuntos del paciente a Storage" (MUST_FIX 2); docs/media-entrantes-2026-09-06.md §5, §8.6.
- **Estado:** pendiente de decisión (banlist regex no aplicada)
- **Riesgo de regresión:** los prompts vivos curados no dicen "no repitas marcadores `[MEDIA:…]`"; hoy solo el panel lo contiene. Verificar el Banlist Validator o `Split en Mensajes` y que ninguna regla de prompt dependa de ocultar el token.

### MED-09 · R14: el Logger (cron 5 min) copia la memoria sin token y la foto desaparece para siempre
- **Entrada/disparador:** el Logger `xsXeHp7WLXnFQc3o` cae dentro de la ventana INSERT -> UPDATE (~1,4 s por foto, hasta 30 s por video; ~1 adjunto perdido cada 2 semanas, varios % por cada video).
- **Falla previa:** `conversaciones` se escribe una sola vez (`ignore-duplicates`) sin token y nunca se corrige; el panel prefiere `conversaciones` y su dedup por timestamp en ms descarta la fila de memoria que SÍ tiene el token.
- **Esperado:** `rescatarTokensMedia` del lado del panel (pasa a la fila de `conversaciones` los tokens que la memoria tiene) + repesca de refetch a 1,5 s; obligatorio antes de `apply_media_fromme.py`. Plan B: `AND created_at < now() - interval '60 seconds'` en `PG - SELECT nuevos` del Logger.
- **Capa:** infra (código del panel)
- **Test:** SIN TEST (código del panel, no está en `tests/`)
- **Fecha/fuente:** 2026-09-07; EC-81, EC-179; DEC; BKL P1 R14; docs/media-entrantes-2026-09-06.md §8.3 R14, §8.6.
- **Estado:** vigente

### MED-10 · `media_tipo` desconocido desde el panel salía como imagen al paciente
- **Entrada/disparador:** el panel envía `media_tipo` desconocido con URL, o `audio` aún no aceptado por el satélite viejo.
- **Falla previa:** caía a `image` y se mandaba a Evolution una URL no-imagen al paciente; con el satélite viejo, un audio del panel nuevo salía como `type: image`.
- **Esperado:** `media_tipo` desconocido -> 400 "media_tipo invalido"; sin secreto -> 400/401; tipo vacío si no hay `media_url`; el filename conserva la extensión al recortar a 80. El satélite staff `Panel — acciones staff` (`jzxb5zUKCaJcvCgp`, `Validar secreto`) se actualiza PRIMERO (E2E: OGG + webhook audio -> 200; `ptt` -> 400).
- **Capa:** nodo (satélite)
- **Test:** `tests/test_retencion_y_staff.js` (98/98)
- **Fecha/fuente:** 2026-09-07 madrugada y 04:25; EC-39; current-state "APLICADO: Retención + Vigía uso + audio desde el panel".
- **Estado:** vigente

### MED-11 · Foto, audio, documento, video y sticker del paciente se descartaban (solo un chip en el panel)
- **Entrada/disparador:** foto con caption "mirá mi diente", nota de voz, PDF "presupuesto.pdf" ("te mando el presupuesto"), video "mirá cómo se mueve", sticker.
- **Falla previa:** Evolution GO manda el archivo en `body.data.Message.base64` y el v6 lo usaba solo para describir/transcribir y lo descartaba; el panel solo mostraba "Imagen · TIPO: FOTO_DENTAL …".
- **Esperado:** subir a bucket privado `pacientes-media` (path `<tel>/<yyyy>/<mm>/<id>.<ext>`, mes en hora Argentina), fila en `media_entrantes` y sufijo ` [MEDIA:<id16hex>]` al final del marcador (200 ids: todos 16 hex y únicos); si algo falla el bot sigue exactamente como hoy.
- **Capa:** nodo (`Media: Preparar / Subir / Registrar / Marcar`)
- **Test:** `tests/test_media_nodos.js` (jpeg, png, video, ptt, pdf, sticker, path Argentina)
- **Fecha/fuente:** 2026-09-06; EC-172; docs/media-entrantes-2026-09-06.md §1-§3.
- **Estado:** vigente (superó a MED-26)

### MED-12 · `Media: Marcar`: el sufijo solo se agrega si el INSERT devolvió LA fila
- **Entrada/disparador:** INSERT con error (duplicate key), rama "no hay archivo", subida fallida (400 "Bucket not found"), fila con otro id, `Preparar` con `{error}`, texto con saltos de línea y comas.
- **Falla previa:** riesgo de sufijar un token de una fila que no existe o de otro adjunto.
- **Esperado:** `text + " [MEDIA:<id>]"` solo si `fila.bucket === 'pacientes-media' && fila.id === Preparar.id && !fila.error`; `¿Subida OK?` = `!error && 200 ≤ statusCode < 300 && !body.error` (error de red e item vacío -> false); expresiones sin `}}` internas.
- **Capa:** nodo (expresiones `Media: Marcar` / `¿Subida OK?`)
- **Test:** `tests/test_media_nodos.js`
- **Fecha/fuente:** 2026-09-06; EC-175.
- **Estado:** vigente

### MED-13 · Mime y extensión: sniff de magic bytes, Lottie, `audio/ogg; codecs`, tipos desconocidos
- **Entrada/disparador:** sticker estático que Evolution GO manda como PNG aunque declare webp; sticker Lottie (animado, no PNG/WEBP/GIF); `audio/ogg; codecs=opus`; `audio/mp4` con ftyp; mime desconocido con/sin filename; imagen sin firma reconocible; jpg enviado como documento; gif; `documentWithCaptionMessage` anidado; MediaType vacío (caso real 25/8).
- **Falla previa:** el panel pintaba un `<img>` roto para el sticker Lottie; los casos reales del 25/8 y los stickers motivaron el sniff.
- **Esperado:** mime real por magic bytes (png/webp/gif/jpeg/pdf/ogg/mp4); Lottie -> `application/octet-stream` (el panel lo pinta como chip "Sticker", no `<img>`); `audio/ogg; codecs=opus` -> `audio/ogg`; mime desconocido -> extensión del filename original o `bin`; solo el sticker cae a octet-stream, imagen sin firma conserva el mime declarado; fallback por sub-key de `Message` si `Info.MediaType` viene vacío; prefijo `data:` removido.
- **Capa:** nodo (`media/preparar.js`)
- **Test:** `tests/test_media_nodos.js`
- **Fecha/fuente:** 2026-09-06; EC-75, EC-173; DEC "media_entrantes"; docs/media-entrantes-2026-09-06.md §2.
- **Estado:** vigente

### MED-14 · `media_entrantes.telefono` verbatim vs saneado, y `@lid` legítimo del paciente
- **Entrada/disparador:** `phone` `…@lid` legítimo (1:1) del paciente.
- **Falla previa:** con dígitos solos, los adjuntos del paciente `@lid` nunca resolverían en el panel (`.eq` por `phone` crudo).
- **Esperado:** `media_entrantes.telefono` = `Extraer Datos.phone` TAL CUAL; solo el `path` del objeto se sanea; un `@lid` 1:1 de paciente SÍ sube.
- **Capa:** nodo
- **Test:** `tests/test_media_nodos.js` (test 17b)
- **Fecha/fuente:** 2026-09-06; EC-76; DEC; docs/media-entrantes-2026-09-06.md §8.3 R1.
- **Estado:** pendiente de decisión (tensión con MED-04: el tope 8-15 dígitos descarta a propósito un LID de 16-17 dígitos; revisar cuando aparezca un LID real de paciente)

### MED-15 · R13: Chatwoot sin contacto/conversación -> el adjunto del staff no se archiva
- **Entrada/disparador:** la doctora manda una foto a un número nuevo; `CW Extract Conv` / `CW Pick Conv` devuelven `[]`.
- **Falla previa:** `CW Set Label humano` no ejecuta y la cadena Media entera no corre; el adjunto no se archiva y parece que el cambio no funciona.
- **Esperado:** aceptado a propósito: "entre no archivar un adjunto y demorar el silencio del bot, gana el silencio". La primera prueba real debe hacerse con un chat donde el paciente YA escribió antes.
- **Capa:** infra (decisión de diseño, dependencia de Chatwoot)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-07; EC-35, EC-180; current-state "Adjuntos del STAFF (rama fromMe)"; docs/media-entrantes-2026-09-06.md §8.3 R13, §8.4.
- **Estado:** vigente (riesgo aceptado)

### MED-16 · Ramas paciente y staff corren código distinto de `Media: Preparar`
- **Entrada/disparador:** el nodo VIVO de la rama del paciente tiene el jsCode viejo, sin los guards de JID.
- **Falla previa:** `apply_media_entrantes.py` deja de ser no-op (dry-run: "ACTUALIZA Media: Preparar" + 5 más).
- **Esperado:** alinear ambas ramas en un PUT aparte con OK propio; después de alinear, el dry-run vuelve a ser no-op.
- **Capa:** nodo
- **Test:** `tests/test_media_nodos.js`
- **Fecha/fuente:** 2026-09-07; EC-82; BKL P2.
- **Estado:** pendiente de decisión (P2 sin aplicar)

### MED-17 · Orden de 3 fotos seguidas del paciente (una fila con 3 marcadores)
- **Entrada/disparador:** 3 fotos seguidas del paciente = UNA fila `human` con 3 marcadores unidos por "\n".
- **Falla previa:** los 3 tokens pueden salir en otro orden que el de WhatsApp (depende de la latencia de OpenAI Vision por foto).
- **Esperado:** el panel adjunta por id, no por posición.
- **Capa:** infra (panel) / aceptado
- **Test:** parcial: `tests/test_media_nodos.js` ("200 ids: todos 16 hex y únicos"); el adjuntado por id en el panel: SIN TEST
- **Fecha/fuente:** 2026-09-06; EC-182; docs/media-entrantes-2026-09-06.md §3.
- **Estado:** vigente

### MED-18 · R12: reentrega del webhook fromMe sube dos copias del archivo
- **Entrada/disparador:** Evolution reentrega el mismo webhook fromMe (adjunto del staff).
- **Falla previa:** la rama fromMe no dedupea webhooks; se subirían dos copias con ids distintos; `x-upsert` no ayuda (el path lleva un id aleatorio). No se vio ninguna reentrega en 13 días.
- **Esperado:** riesgo aceptado/documentado; no hay dedupe en esta rama.
- **Capa:** nodo / aceptado
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-07; EC-182; docs/media-entrantes-2026-09-06.md §8.3 R12.
- **Estado:** pendiente de decisión (aceptado sin dedupe)

### MED-19 · Objetos huérfanos en Storage si `Media: Registrar` falla tras la subida (R11)
- **Entrada/disparador:** la subida sale OK y `Media: Registrar` falla (onError continue).
- **Falla previa:** el objeto queda sin fila en `media_entrantes`; el satélite de retención borra POR FILA, así que nunca se recolecta.
- **Esperado:** P3: barrido de `storage.objects` sin fila.
- **Capa:** infra (retención)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-07; EC-183; docs/media-entrantes-2026-09-06.md §8.3 R11; docs/retencion-y-uso-2026-09-07.md §7.
- **Estado:** pendiente de decisión (P3 sin aplicar)

### MED-20 · Residuo de pruebas en `media_entrantes` y Storage (`limpiar_numero_demo.py` no los toca)
- **Entrada/disparador:** pruebas de adjuntos con un teléfono real (Lucas incluido).
- **Falla previa:** `scripts/limpiar_numero_demo.py` no toca `media_entrantes` ni Storage; queda residuo de pruebas.
- **Esperado:** tras cada prueba, borrar a mano las filas de prueba y los objetos del bucket (regla dura 9, mismo turno), además de memoria, logs y label humano.
- **Capa:** infra (proceso)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-07; EC-183; docs/retencion-y-uso-2026-09-07.md §7; regla dura 9.
- **Estado:** pendiente de decisión (el script no cubre media)

### MED-21 · Retención 90 días: DELETE con `queryReplacement`, ids unidos por "|" y `'-'` cuando no hay ids
- **Entrada/disparador:** adjuntos de más de 90 días (paciente y staff `panel-media`) y corrida del smoke `{"smoke": true}`.
- **Falla previa:** n8n parte `queryReplacement` por coma DESPUÉS de evaluar (falla real del 5/9); un `queryReplacement` vacío no pushea parámetro (`there is no parameter $1`).
- **Esperado:** ids unidos por "|" y `'-'` cuando están vacíos (`ids.join('|') || '-'`); `agrupar_lote` con filas / vacío / error / otro bucket / smoke cubiertos.
- **Capa:** nodo (agrupar_lote)
- **Test:** `tests/test_retencion_y_staff.js` (agrupar con filas/vacío/error/otro bucket/smoke)
- **Fecha/fuente:** 2026-09-05 y 2026-09-07; EC-185 (a); docs/retencion-y-uso-2026-09-07.md §2, §8-§9.
- **Estado:** vigente

### MED-22 · Retención: borrar blobs por la API REST de Storage (no por SQL); "objeto ya inexistente = OK"; advertencia no es fallo
- **Entrada/disparador:** listar y borrar objetos de `panel-media` y `pacientes-media`; Storage encuentra 0 de N paths.
- **Falla previa:** `POST /object/list` no sirve para `panel-media` (devuelve carpetas con `created_at` null); borrar Storage por SQL deja el blob huérfano en S3; si Storage encuentra 0 de N paths hay advertencia pero el UPDATE `borrado_at` se marca igual (si no, reintentaría cada noche).
- **Esperado:** listar `storage.objects` por SQL y borrar por la API REST; "objeto ya inexistente = OK"; "advertencia ≠ fallo"; el UPDATE `borrado_at` se hace aun con advertencia; `resumen` cubre DELETE 403 / red / UPDATE roto / SELECT roto.
- **Capa:** nodo (resumen)
- **Test:** `tests/test_retencion_y_staff.js` (resumen con DELETE 403/red/UPDATE roto/SELECT roto)
- **Fecha/fuente:** 2026-09-07; EC-185 (b, c, d); docs/retencion-y-uso-2026-09-07.md §2, §8-§9.
- **Estado:** vigente

### MED-23 · Retención: starvation por bucket, delete markers, aviso a Lucas y chip "vencido"
- **Entrada/disparador:** consulta de lote `Q_PACIENTES`/`Q_PANEL`; bandeja en vivo >365 días; fallo o advertencia en la corrida; imagen no cargada en el panel.
- **Falla previa:** sin filtro de bucket una consulta puede dejar sin cupo a la otra (starvation); las filas con delete marker se reprocesan.
- **Esperado:** filtro de bucket en `Q_PACIENTES` y `is_delete_marker IS NOT TRUE` en `Q_PANEL`; `armar_aviso` manda WhatsApp a Lucas solo si `fallidos > 0` o hay advertencia; el chip "vencido" aparece solo ante 404/410 confirmado (HEAD `/api/media/<id>`), no por `onError` de `<img>`.
- **Capa:** nodo (`armar_aviso`) + infra (panel)
- **Test:** `tests/test_retencion_y_staff.js` (aviso solo con fallo o advertencia); chip "vencido": SIN TEST
- **Fecha/fuente:** 2026-09-07; EC-185; docs/retencion-y-uso-2026-09-07.md §2, §8-§9.
- **Estado:** vigente

### MED-24 · Tarjeta de contacto (`contactsArrayMessage` / vcard) no detectada
- **Entrada/disparador:** el paciente comparte una tarjeta de contacto.
- **Falla previa:** `Extraer Datos` no detecta `contactsArrayMessage`; un vcard no trae base64 y cae en `hay_archivo:false`.
- **Esperado:** bug preexistente que NO se tocó en esa entrega; el mensaje no debe romper el flujo ni subir archivo.
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-06/07; EC-184; docs/media-entrantes-2026-09-06.md §5, §8.
- **Estado:** pendiente de decisión (bug conocido sin corregir)

### MED-25 · Nota de voz con `Info.MediaType=''` muere en `Filtrar duplicados y basura`
- **Entrada/disparador:** audio con `Info.MediaType` vacío.
- **Falla previa:** el mensaje muere en el filtro `Filtrar duplicados y basura` (`Media: Preparar` ya lo cubriría si llegara).
- **Esperado:** bug preexistente que NO se tocó en esa entrega; el fallback por `audioMessage` solo existe en `Preparar`.
- **Capa:** nodo
- **Test:** parcial: `tests/test_media_nodos.js` ("MediaType vacío: fallback por audioMessage", solo Preparar); el filtro: SIN TEST
- **Fecha/fuente:** 2026-09-06/07; EC-184; docs/media-entrantes-2026-09-06.md §5, §8.
- **Estado:** pendiente de decisión (bug conocido sin corregir)

### MED-26 · Video/sticker/ubicación/contacto solo generan un marcador de texto
- **Entrada/disparador:** tipos de media `document`/`otros` tras la migración.
- **Falla previa:** ninguna: así estaba diseñado antes de la migración (no es bug).
- **Esperado:** solo marcador de texto, sin archivo.
- **Capa:** nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-08-05 noche (Fix 3); EC-45 (extractor 2).
- **Estado:** superado por MED-11 (2026-09-06: video/sticker/foto/audio/PDF ahora se suben a Storage; ubicación y contacto siguen como marcador, ver MED-06 y MED-24)

### Cobertura
- 26 casos; 10 SIN TEST (MED-02, 03, 07, 08, 09, 15, 18, 19, 20, 24; MED-26 superado) y 3 con cobertura solo parcial (MED-01, 17, 25). Lo cubierto está en `tests/test_media_nodos.js`, `tests/test_media_fromme.js` y `tests/test_retencion_y_staff.js`, todos de nodos aislados.
- Huecos más peligrosos: (1) MED-02, el orden label-antes-que-Media (clase Mariela) solo se verifica por dry-run, sin E2E; (2) MED-03 y MED-07, comprobantes y foto dental dependen de prompts curados el 4/10 y del Router sin test, con contradicción abierta sobre si Confirmar confirma el turno; (3) MED-08 y MED-09, el eco de `[MEDIA:…]` en respuestas del bot (banlist pendiente) y la pérdida de fotos por el Logger R14 (solo mitigado en el panel).
