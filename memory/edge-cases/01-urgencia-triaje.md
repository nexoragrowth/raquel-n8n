## urgencia_triaje

Notas de lectura (aplican a todo el flujo):
- Hechos vivos 4/10/2026: v6 ACTIVO. "Sub-Agent Urgencia" y "Sub-Agent Cancelar" dentro del v6 son nodos MUERTOS; `urgencia_dolor` va al flujo Triaje (`Triaje: Evaluar` > `Triaje: Decidir` > videos / escalación determinística). Los textos al paciente son canned (el LLM solo clasifica y devuelve JSON).
- Archivos de test: `triaje/test_gate.js` (29 casos, NO está en `tests/`, solo prueba el gate de red flags, no la clasificación del LLM), `tests/test_triaje_nodos.js` (Evaluar/Decidir/Preparar), `tests/test_e2e_triaje.py` (harness E2E con shape Evolution GO), `tests/test_triaje_textos_banlist.py` (`--live`/`--db`), `scripts/check_triaje.py` (HEAD 200 de videos, config).
- Prompt vivo del Router (curado 4/10/2026): `urgencia_dolor` = "Dolor dental, muela, sangrado, hinchazón, alambre/bracket salido o que pincha, solicitud de medicación urgente ('qué tomo'). (Máxima prioridad ante cualquier señal médica/urgencia)"; pero "si el mensaje es ambiguo o no encaja claramente → consulta_general". Respaldo en Sub-Agent General: "Escala inmediatamente si hay: fotos clínicas enviadas, dolores o urgencias, quejas...".
- Refs de origen: "retro #N" = `docs/analisis-retrospectivo-urgencias-2026-09-02.md` caso N. "cs" = `memory/current-state.md`.

### URG-01 · Incidente Mariela: el bot invita a la clínica cerrada un sábado
- **Entrada/disparador:** Mariela (mamá de Martina, expansor maxilar caído), sáb 2026-05-09 13:02: "esta incomoda, no come, solo liquidos".
- **Falla previa:** Router (sin ver memoria) lo clasificó `consulta_general`; el bot respondió 13:05-13:08: "venite con Martina lo antes posible, traigan el expansor y el DNI. Balcarce 37, 2do piso. Los esperamos." Mariela: "Bien, ahora salimos para la clinica" con la clínica cerrada. La doctora pidió frenarlo 13:15; Lucas apagó el bot a mano; v6 desactivado ese día. Root cause triple: kill-switch con phone del destinatario (`/bot off` ignorado), prompt con ejemplo "Te esperamos" (contradice R22), Router sin memoria.
- **Esperado:** urgencia/dolor/aparato salido SIEMPRE escala al grupo con canned; la respuesta al paciente NO matchea el Banlist (22 patrones: "venite", "los esperamos", "ahora mismo a la clínica", "guarda/trae/toma/saca", "no te preocupes", "es normal", dirección como confirmación de cita); ninguna tool de agenda se llama; mensajes de malestar sin palabra clave ("incómoda", "no come") deben ir a `urgencia_dolor`, no a `consulta_general`.
- **Capa:** banlist (última línea) + prompt (R0 anti-conversacional) + gate (Router con memoria; `/bot off` con phone del emisor) + nodo (Triaje determinístico)
- **Test:** SIN TEST dedicado (fixes.md/bugs.md citan "13/13 PASS contra los 5 mensajes reales de Mariela", archivo no existe en el repo; grep de "incomoda" en tests/ scripts/ triaje/ da 0). Cobertura indirecta: `tests/test_triaje_textos_banlist.py` (solo textos canned del triaje).
- **Fecha/fuente:** 2026-05-09 · `.claude/CLAUDE.md` "Incidente clave", `docs/fixes.md` Round 1, `docs/bugs.md` #1, `.claude/project-context.md`
- **Estado:** vigente (regla dura #1: no prender v6 sin OK de Lucas; hoy v6 activo con el triaje como capa). El Sub-Agent Urgencia con que se cerró el incidente es nodo muerto: la defensa actual es Router > Triaje.
- **Riesgo de regresión:** el prompt curado del Router lista síntomas explícitos (dolor, muela, sangrado, hinchazón, alambre/bracket) pero NO "incómoda / no come / solo líquidos / expansor / aparato caído", y tiene el fallback "ambiguo → consulta_general". Verificar con el mensaje textual de Mariela que va a `urgencia_dolor` y que el Router recibe contexto reciente (regla "analizar el contexto reciente"). Verificar que el Banlist y R0 de Sub-Agent General siguen presentes.

### URG-02 · Cualquier red flag gana sobre un match de tipo (trauma + sangrado escala sin LLM ni video)
- **Entrada/disparador:** "mi hijo se cayó… le sangra mucho la boca" (E2E 4/9, escalación id 201). Lista borrador de red flags: trauma, sangrado abundante, pieza tragada, hinchazón/dificultad para respirar, fiebre, dolor intenso (pendiente que Raquel confirme la lista).
- **Falla previa:** riesgo de diseño: mandar un video "no grave" cuando hay una señal grave (misma clase de falla que Mariela / multi-síntoma "Salvador Mayans"); riesgo de que el clasificador intente resolverlo con video.
- **Esperado:** `gate_red_flags.js` corre ANTES de clasificar tipo y de nuevo DESPUÉS de las preguntas guiadas (Capa 3); si hay red flag: ruta `escalar` sin llamar al LLM, sin `/send/media`, texto canned + aviso al grupo; la red flag gana aunque el mensaje también matchee `alambre_pincha`; sin match claro → escalar, nunca adivinar. Caption del video siempre canned con salida de emergencia explícita.
- **Capa:** gate (`triaje/gate_red_flags.js`) + nodo (Triaje: Evaluar; texto 100% canned, LLM solo clasifica)
- **Test:** `triaje/test_gate.js` (29/29), `tests/test_triaje_nodos.js` ("gate red flag -> decidido escalar", "gate en seguimiento -> escalar"), `tests/test_e2e_triaje.py` (paso 5 del guion), `tests/test_triaje_textos_banlist.py`
- **Fecha/fuente:** 2026-09-02 (diseño) y 2026-09-04 (E2E) · DEC "Diseño del triaje... 3 decisiones cerradas", BKL "Triaje de urgencias con videos", cs "Fase 2"
- **Estado:** vigente (la lista exacta de red flags sigue pendiente de confirmación de Raquel, ver URG-23/24/25)

### URG-03 · Gate de red flags: mensajes sintéticos que SIEMPRE deben escalar
- **Entrada/disparador:** (a) "Mi hijo se cayó en el colegio y se le partió el bracket, le sangra mucho la boca" (trauma, sangrado_abundante); (b) "Se me salió el bracket y creo que me lo tragué" (tragado); (c) "Tengo la cara hinchada del lado del alambre que pincha" (hinchazon); (d) "Le cuesta tragar y le duele mucho" (respirar_tragar); (e) "Tiene fiebre desde anoche y le duele la muela con el bracket" (fiebre); (f) "Me pegaron un pelotazo y se me aflojó el diente con el bracket" (trauma); (g) "el dolor es insoportable, no aguanto más" (dolor_intenso).
- **Falla previa:** n/a (casos de test).
- **Esperado:** `escala === true` con las flags indicadas en cada caso; sin LLM, sin video.
- **Capa:** gate (`triaje/gate_red_flags.js`)
- **Test:** `triaje/test_gate.js`
- **Fecha/fuente:** 2026-09-02/04 · `triaje/test_gate.js`
- **Estado:** vigente

### URG-04 · Auto-supresión: el canned de Urgencia nunca llega al paciente tras escalar (6/6)
- **Entrada/disparador:** Lucas, desde su teléfono de prueba, 2026-09-03 ~21:48 UTC: "buenas sabes que se me salió el bracket y pincha" (execs 270010/270011/270012; escalaciones_log id 189 y 190).
- **Falla previa:** Sub-Agent Urgencia llamaba `escalar_a_secretaria` > Helper aplicaba label `humano` sincrónicamente (responseMode lastNode) > 1,4 s después `Re-check Humano` lo detectaba > "Aviso humano tomó chat" (escalación 190 "silenciosa") y NUNCA se enviaba "Recibimos tu mensaje. Le pasamos a la doctora…". De 790 ejecuciones desde el 30/8, 8 llamaron `escalar_a_secretaria`; 6/6 con contacto Chatwoot fueron suprimidas (incluye 2 comprobantes y 3 urgencias reales); las 2 enviadas fue porque Chatwoot Apply devolvió "contact not found". Tampoco llegó video (Fase 2 no estaba conectada). Contradicción entre fuentes: la primera lectura (cs 4/9) atribuyó el silencio a que el chat estaba en "humano atendiendo" por un fromMe multimedia `[ATENCION HUMANA]` del 2/9; el mapeo posterior (mapeo-read_redis_humano.md §3f, 4/9) demostró que el label lo puso la propia ejecución. Se conserva el segundo (más específico).
- **Esperado:** en la rama de triaje el texto canned se envía ANTES de avisar al grupo (`Triaje: Enviar Texto Escalada` > `Escalar`); el aviso aplica el label como siempre; el paciente recibe el canned aunque `notify-grupo` falle (queda NOTIFY_FALLO en el log). Fix sugerido aparte: Chatwoot Apply no se aplica en la misma ejecución que escala, o Re-check ignora labels aplicados por la propia ejecución. Limpieza pendiente de filas de prueba (escalaciones_log 189/190, conversaciones 6006/6009) con OK de Lucas.
- **Capa:** nodo (orden de envío en la rama Triaje; Re-check Humano dentro de Decidir)
- **Test:** SIN TEST (ni unit ni E2E del orden "canned antes del aviso" ni del label autoaplicado); `tests/test_triaje_nodos.js` solo cubre `preparar` (texto canned + resumen)
- **Fecha/fuente:** 2026-09-03 (caso) / 2026-09-04 (diseño) · cs "Triaje con video: Fase 2", `docs/triaje-fase2-analisis/mapeo-read_redis_humano.md` §3f, `docs/triaje-fase2-diseno-2026-09-04.md` §9
- **Estado:** vigente en la rama Triaje; los 6/6 suprimidos son del Sub-Agent Urgencia (nodo muerto). Pendiente de decisión: fix en Chatwoot Apply/Re-check para las demás escalaciones (comprobantes) que siguen usando `escalar_a_secretaria`.

### URG-05 · Contaminación de contexto: mensaje viejo de test hace escalar un caso nuevo
- **Entrada/disparador:** Lucas, 2026-09-04 18:43 ART (exec 270770): "Me pincha un alambre de brackets" (o "…de vrackets"), con contexto previo del E2E #5 "mi hijo se cayó, le sangra mucho" de un episodio ya escalado; ctx de test: `PACIENTE: mi hijo se cayó… / BOT: [TRIAJE ESCALADO] … / PACIENTE: Hola`.
- **Falla previa:** el clasificador devolvió `red_flag` ("el contexto indica una caída con sangrado abundante") porque `Build Router Context` (últimos 6 mensajes) conservaba el episodio ya escalado; recibió texto de escalación en vez del video. Origen de la regla dura #9 (limpiar residuos de test).
- **Esperado:** `recortarCtx()` en `Triaje: Evaluar`: el LLM solo ve el contexto posterior al último `[TRIAJE ESCALADO]`/`[TRIAJE CIERRE]` (el texto actual llega igual); prompt: "las red flags se evalúan ÚNICAMENTE sobre el mensaje actual y la respuesta a la pregunta guiada"; la reconstrucción de estado (Opción ya enviada) sigue mirando el contexto completo; resultado del E2E con el mensaje exacto: `alambre_pincha` confianza alta > video Opción 1 (log 10). Debe afirmarse: `llm_body` no contiene "se cayó" y sí el "Hola! Soy Asiri" posterior; con ESCALADO posterior al video, `estado` es null.
- **Capa:** nodo (`Triaje: Evaluar`, `recortarCtx`) + prompt (`triaje/prompt_clasificador.md`) + gate (red flags del mensaje actual)
- **Test:** `tests/test_triaje_nodos.js` ("ctx recortado al episodio actual", "ctx con ESCALADO posterior -> sin estado"; suite 46/46) + E2E real
- **Fecha/fuente:** 2026-09-04 (caso) / 2026-09-05 (fix) · cs "Sesión 2026-09-05" punto 1, DEC "2026-09-05 — el clasificador solo ve el contexto del episodio actual"
- **Estado:** vigente

### URG-06 · Escalación determinística: el LLM no puede devolver [NO_REPLY] ni decidir el texto
- **Entrada/disparador:** diseño del triaje con video (2026-09-02/04): urgencia que pasaba por Sub-Agent Urgencia con "validación de destino" (`[NO_REPLY]` si no hay señales claras).
- **Falla previa:** el LLM podía devolver `[NO_REPLY]` y no escalar; `Re-check Humano` suprimía la respuesta (ver URG-04); el Sub-Agent Urgencia es un sub-agente conversacional prohibido de dar consejo (regla post-Mariela).
- **Esperado:** en la rama nueva: Code > texto canned al paciente ANTES del aviso > `notify-grupo` > log (`triaje_urgencias_log`) > Redis; sin LLM en el texto; `Triaje: Merge Clasificacion` (combine by position) para no depender de `$('Triaje: Evaluar').first()` cuando Evaluar corre 2 veces (seguimiento > Router > urgencia_dolor); Re-check humano Chatwoot dentro de Decidir (fail-open); caption del video canned que deja explícito que si no mejora puede pedirle a la doctora; `aviso_pasivo=false`; config 100% por dato (`triaje_config` + `triaje_videos`); kill-switch `--desactivar` (0 PUT).
- **Capa:** nodo (`Triaje: Evaluar/Decidir/Preparar Escalada`, Merge)
- **Test:** `tests/test_triaje_nodos.js` (44/44 > 46/46), `tests/test_e2e_triaje.py` (4 E2E reales: Opción 1 > Opción 2 > escalación > red flag), `tests/test_triaje_textos_banlist.py`
- **Fecha/fuente:** 2026-09-02 y 2026-09-04 · DEC "Fase 2 del triaje: escalación determinística, Merge por posición, config por dato", `prompts/v6_partials/urgencia_funcion.md`
- **Estado:** vigente. Sub-Agent Urgencia quedó huérfano y hoy es nodo muerto (su prompt sigue con el canned "Recibimos tu mensaje. Le pasamos a la doctora…").

### URG-07 · Los textos canned del triaje salen por /send/* directo y deben pasar el Banlist
- **Entrada/disparador:** captions, pregunta guiada, salidas de emergencia, `texto_escalada` y `texto_cierre` editables por UPDATE en `triaje_videos`/`triaje_config` (borradores con voz de "usted" y "Hola! Soy Asiri…" en Opción 1); un editor podría guardar "aplicá cera y venite".
- **Falla previa:** riesgo: salen por `/send/*` directo sin pasar por `Banlist Validator`. Verbos como "aplicá", "sacá el", "guardá", "tomá" disparan el Banlist; formas de usted (Aplique/Guarde/Tome) y el bug de `\b` + acentos son brechas del Banlist vivo.
- **Esperado:** 2ª capa: antes de cada PUT y después de cada UPDATE de textos, correr el array BANLIST REAL del nodo vivo (snapshot) con node sobre TODOS los textos (seeds + filas activas con `--db`): 0 disparos; guard `chequearBanlist` en el panel al editar.
- **Capa:** banlist (regex del nodo vivo aplicado por test) + infra (test pre-PUT, regla dura #5)
- **Test:** `tests/test_triaje_textos_banlist.py [--live] [--db]` (22 textos validados al 30/9; 18 textos al 17/9)
- **Fecha/fuente:** 2026-09-04 · OQ "Textos definitivos del triaje (4/9)", docstring del test, `docs/triaje-fase2-analisis/jueces.md`
- **Estado:** vigente. Brecha conocida: el Banlist no cubre las formas de usted ni `\b` con acentos (ver URG-11).

### URG-08 · Fail-closed del triaje: confianza alta/media/baja, tipo sin video, LLM roto, config vacía, fuera de piloto
- **Entrada/disparador:** "se me salió el alambre de atrás y me pincha el cachete" (alambre_pincha alta/media); bracket_suelto sin video activo; `red_flag` del LLM; JSON inválido; Postgres caído/config vacía; triaje inactivo; teléfono fuera del piloto; label humano.
- **Falla previa:** n/a (test); regla de diseño: 0 filas de config = escalar como antes.
- **Esperado:** alta > video Opción 1 (Redis TTL 7200); media > pregunta guiada (TTL 1800); tipo sin video > escalar; LLM `red_flag` > escalar; LLM roto > escalar con `error_llm`; `triaje_inactivo` / `fuera_piloto` / `config_no_disponible` > escalar; label humano > silencio (`silencio_humano` en el log); el LLM nunca escribe al paciente (solo JSON).
- **Capa:** gate (`Triaje: Evaluar/Decidir`) + infra (tablas `triaje_config`/`triaje_videos` con kill-switch)
- **Test:** `tests/test_triaje_nodos.js` ("alta -> video op1", "media -> pregunta guiada", "tipo sin video -> escalar", "LLM red_flag -> escalar", "LLM roto -> escalar error_llm", "humano atendiendo -> silencio", "inactivo/fuera piloto/config vacía")
- **Fecha/fuente:** 2026-09-04 · `docs/triaje-fase2-diseno-2026-09-04.md` §5
- **Estado:** vigente

### URG-09 · Decidir sin evaluación previa y fallo del envío del video
- **Entrada/disparador:** `Triaje: Decidir` recibe `{choices: []}` sin Evaluar; `/send/media` responde 500; `/send/text` de salida tras video OK; `notify-grupo` falla.
- **Falla previa:** n/a (test).
- **Esperado:** escalar `sin_evaluacion`; tras fallo del video: razón `envio_fallo_video`, el paciente recibe `texto_escalada` y el grupo es avisado; fail-closed: si el texto de salida tras video OK falla igual se persiste; si `notify-grupo` falla el paciente igual recibió el canned (queda NOTIFY_FALLO en el log).
- **Capa:** nodo (`Triaje: Decidir/Preparar Escalada`)
- **Test:** `tests/test_triaje_nodos.js` ("decidir sin evaluar -> escalar", "preparar tras fallo /send/media")
- **Fecha/fuente:** 2026-09-04 · `docs/triaje-fase2-diseno-2026-09-04.md` §5
- **Estado:** vigente

### URG-10 · Kill-switch del triaje con estado vigente (`triaje_activo=false`)
- **Entrada/disparador:** "no me sirvió" / "listo gracias" con `triaje_activo=false` y estado Redis vigente.
- **Falla previa:** n/a (test).
- **Esperado:** "no me sirvió" > escalar (no Opción 2); "listo gracias" > cerrar (no escala). `--desactivar` = 0 PUT al workflow.
- **Capa:** gate (config por dato)
- **Test:** `tests/test_triaje_nodos.js` ("seg con activo=false: …")
- **Fecha/fuente:** 2026-09-04 · `docs/triaje-fase2-diseno-2026-09-04.md` §6
- **Estado:** vigente

### URG-11 · `\b` de JS no reconoce letras acentuadas: "se cayó" no disparaba la red flag
- **Entrada/disparador:** regex del gate con `\b` sobre "se cayó", ó/á/ñ.
- **Falla previa:** "se cayó" no matcheaba trauma (bug hallado por los tests).
- **Esperado:** límites Unicode `(?<![\p{L}\p{N}])` / `(?![\p{L}\p{N}])` con flag `u` en el gate y en las regex de seguimiento/cierre; "se cayó" dispara `trauma`.
- **Capa:** gate (`triaje/gate_red_flags.js`)
- **Test:** `triaje/test_gate.js` (29/29)
- **Fecha/fuente:** 2026-09-03 · cs "Fase 1 (sombra)... Gate de red flags"
- **Estado:** vigente (el mismo defecto de `\b` + acentos persiste en el Banlist vivo, ver URG-07)

### URG-12 · El gate de red flags solo corre en el camino de urgencias ("fiebre" en una cancelación)
- **Entrada/disparador:** retrospectiva: "fiebre" apareció solo en una CANCELACIÓN de turno (retro #17).
- **Falla previa:** (riesgo) si el gate corriera sobre todos los mensajes, una cancelación por fiebre se trataría como urgencia.
- **Esperado:** el gate corre solo dentro del camino de urgencias, nunca sobre todos los mensajes; dentro del camino de urgencias "fiebre" dispara aunque sea una cancelación.
- **Capa:** gate + nodo (cableado Router > urgencia_dolor)
- **Test:** `triaje/test_gate.js` (el gate dispara con fiebre); el aislamiento "solo urgencias" SIN TEST
- **Fecha/fuente:** 2026-09-02 y 2026-09-03 · cs "diseño cerrado" y "Fase 1 (sombra)"
- **Estado:** vigente
- **Riesgo de regresión:** el Router curado dice "(Máxima prioridad ante cualquier señal médica/urgencia)": verificar que una cancelación que menciona fiebre/enfermedad se rutea según la regla deseada (cancelar_o_reprogramar vs urgencia_dolor), porque el criterio quedó sin test en el Router.

### URG-13 · Sangrado leve y molestia leve NO deben escalar por el gate
- **Entrada/disparador:** "me sangra un poquito la encía cuando me cepillo con los brackets"; "me molesta un poco el alambre, me raspa el cachete"; "se me soltó la gomita de un bracket".
- **Falla previa:** n/a (test); objetivo: no inflar escalaciones.
- **Esperado:** `escala === false` para los tres.
- **Capa:** gate
- **Test:** `triaje/test_gate.js`
- **Fecha/fuente:** 2026-09-04 · `triaje/test_gate.js`
- **Estado:** vigente

### URG-14 · Foto del paciente: se pide pero NO se interpreta (sin visión)
- **Entrada/disparador:** el paciente manda foto de la boca/aparato (ej. 2026-09-09, foto a las 19:12 de un paciente que ya había escrito "se salió el alambre").
- **Falla previa:** (riesgo) diagnosticar con visión; el analizador de imágenes genérico describe sin precisión (ver URG-38 y URG-15).
- **Esperado:** decisión 1 (2026-09-02): SIN visión; la foto es respaldo adjunto al log para la doctora; la clasificación es 100% por texto; Capa 4: sin match claro > escalar, nunca adivinar; el bot no debe describir ni interpretar la foto en ninguna respuesta. Reafirma la regla "cualquier intento de visión, parar".
- **Capa:** prompt + nodo (diseño; el clasificador solo recibe texto)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-02 · cs "Triaje de urgencias con video: diseño cerrado" (Capas 2 y 4)
- **Estado:** vigente
- **Riesgo de regresión:** el prompt curado del Router/General ya no menciona foto; el respaldo es la línea de Sub-Agent General "Escala inmediatamente si hay fotos clínicas enviadas". Verificar que sigue presente.

### URG-15 · Foto sola sin texto (FOTO_DENTAL) clasificada como urgencia
- **Entrada/disparador:** "[IMAGEN] TIPO: FOTO_DENTAL … La imagen muestra una boca abierta con brackets en la parte inferior. También es visible la lengua y los dientes superiores." sin texto (retro #79, 2026-07-31).
- **Falla previa:** se escalaba como urgencia.
- **Esperado:** `no_urgencia` (no reporta dolor, sangrado, aparatología rota ni alambre). Tensión con URG-14 ("sin match claro > escalar") y con la regla general del bot (fotos clínicas se derivan): decidir qué hace el bot con una foto sin texto (silencio vs derivar). Se mantiene la decisión de no usar visión (3 casos llegaron con foto: retro #23, #79, #163).
- **Capa:** nodo (clasificador) + prompt
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-31 · retro #79
- **Estado:** pendiente de decisión (comportamiento esperado ante foto sin texto no está cerrado en el flujo vivo)

### URG-16 · "No me sirvió / sigue pinchando" tras el video de Opción 1 > Opción 2 sin LLM
- **Entrada/disparador:** E2E 4/9: (1) "se me salió el alambre de atrás y me pincha el cachete" > video Opción 1; (2) "no me sirvió, sigue pinchando" > Opción 2. Frases de test: "No funcionó", "no tengo cera", "se me vuelve a salir", "y si no tengo pinza?", "me sigue lastimando el cachete".
- **Falla previa:** (riesgo diseñado) un "no funcionó" tras el video debe reescalar de verdad, no asumirlo del Router.
- **Esperado:** con estado `video_enviado` opción 1, la regex `regex_no_sirvio` manda el video Opción 2 sin LLM; `next` se calcula genéricamente (`videosDe(tipo)`).
- **Capa:** gate (`regex_no_sirvio` en `Triaje: Evaluar`)
- **Test:** `tests/test_triaje_nodos.js` ("seg video1: …"), `tests/test_e2e_triaje.py`
- **Fecha/fuente:** 2026-09-04 · cs "Fase 2 (piloto en el v6)", `tests/test_triaje_nodos.js`
- **Estado:** vigente

### URG-17 · Opción 2 agotada > escalar sin más opciones
- **Entrada/disparador:** tras la Opción 2: "no lo pude meter con la pinza, sigue igual".
- **Falla previa:** (riesgo) loop de videos o silencio cuando no quedan opciones.
- **Esperado:** escalar con razón `no_sirvio_sin_mas_opciones`: `texto_escalada` al paciente + aviso al grupo exacto "[TRIAJE] no sirvio sin mas opciones | tipo: alambre_pincha | videos enviados: Opción 1 y 2 | Paciente: «…»" + label humano; Redis TTL 3600.
- **Capa:** gate + nodo (`Triaje: Preparar Escalada`)
- **Test:** `tests/test_triaje_nodos.js` ("seg video2: no sirvió -> escalar sin más opciones", "preparar: texto canned + resumen"), `tests/test_e2e_triaje.py` (paso 3)
- **Fecha/fuente:** 2026-09-04 · cs "Fase 2", `docs/triaje-fase2-diseno-2026-09-04.md` §7
- **Estado:** vigente. Si se agrega la Opción 3 de alambre_pincha (ver URG-31), verificar que "agotada" se calcule sobre la última opción real y no sobre la 2.

### URG-18 · "No me sirvió, ahora me duele la muela de arriba, es otra cosa" no debe mandar la Opción 2 a ciegas
- **Entrada/disparador:** "no me sirvió, ahora me duele la muela de arriba, es otra cosa"; "me sigue doliendo la muela de arriba".
- **Falla previa:** los 3 diseños candidatos mandaban la Opción 2 (pinza) por la regex `sigue|igual` (MUST_FIX de los jueces).
- **Esperado:** `regex_nuevo_problema`: nuevo problema + "no sirvió" > reclasificar (`post_video=true`); `otra_urgencia` > escalar; no se envía video.
- **Capa:** gate (`regex_nuevo_problema`) + prompt (clasificador)
- **Test:** `tests/test_triaje_nodos.js` ("seg video1: no sirvió + otra cosa -> clasificar", "...otra_urgencia -> escalar")
- **Fecha/fuente:** 2026-09-04 · `docs/triaje-fase2-analisis/jueces.md` MUST_FIX
- **Estado:** vigente

### URG-19 · Cierre estricto: "ok pero me duele" no cierra; "listo ya me puse la cera" / "igual gracias" sí
- **Entrada/disparador:** SÍ cierran: "listo gracias ya me puse la cera", "listo, lo pude acomodar con la pinza, gracias", "igual gracias, ya está", "Gracias!!", "dale, voy a probar". NO cierra: "ok pero me duele mucho igual".
- **Falla previa:** bugs de diseño de los jueces: (1) `NO_SIRVIO.test || URG_KW` antes de CIERRE con URG_KW incluyendo cera|pinza escalaba un caso resuelto y aplicaba label humano 1 h; (2) la regex `no_sirvio` con "nada"/"igual"/"sigue" sueltos mandaba la Opción 2 ante "de nada", "igual gracias". Riesgo inverso: cerrar con un "ok" que trae una queja.
- **Esperado:** evaluar CIERRE antes que NO_SIRVIO cuando ambos matchean, con límites Unicode; cierre > `texto_cierre` canned por `/send/text` directo (NUNCA por el Formatting Agent), limpiar estado Redis y marcar resuelto; "ok pero me duele…" no cierra y escala.
- **Capa:** gate (`regex_cierre` / `regex_no_sirvio` en `Triaje: Evaluar`)
- **Test:** `tests/test_triaje_nodos.js` (44/44; "cierre con cera -> cerrar", "'igual gracias' -> cerrar", "'ok' + duele -> escalar"), `tests/test_e2e_triaje.py` (paso 4)
- **Fecha/fuente:** 2026-09-04 · cs "Fase 2" (nota: "probado solo en unit tests, no E2E todavía"), `docs/triaje-fase2-analisis/jueces.md` MUST_FIX
- **Estado:** vigente

### URG-20 · Mensaje de otro tema durante un estado de triaje vigente va al Router; duda sobre el mismo aparato escala
- **Entrada/disparador:** "hola, quería sacar un turno para mi hija"; "cuánto sale la consulta?"; contraejemplo: "la cera se me pega en el diente, ¿está bien eso?".
- **Falla previa:** un diseño descartado escalaba todo lo que no matcheaba no_sirvio/cierre (falsa escalación + label humano 1 h).
- **Esperado:** otro tema > `ruta_pre = normal` > Router (idéntico a hoy); duda sobre el mismo aparato sin cerrar ni "no sirvió" > escalar con razón `seguimiento_no_resuelto`, nunca a Sub-Agent General.
- **Capa:** gate (`regex_aparato`, `Triaje: Evaluar`)
- **Test:** `tests/test_triaje_nodos.js` ("otro tema -> normal", "precio -> normal", "duda sobre cera -> escalar")
- **Fecha/fuente:** 2026-09-04 · `docs/triaje-fase2-analisis/jueces.md`
- **Estado:** vigente

### URG-21 · Respuesta a la pregunta guiada: reclasificar combinando, nunca una 2ª pregunta
- **Entrada/disparador:** pregunta "¿Es el alambre principal?" y respuesta "sí, el de atrás, me lastima el cachete".
- **Falla previa:** n/a (test).
- **Esperado:** reclasificar combinando mensaje original + respuesta; alta > video Opción 1; media > escalar con razón `post_pregunta`; jamás una segunda pregunta.
- **Capa:** gate + prompt (clasificador)
- **Test:** `tests/test_triaje_nodos.js` ("pregunta -> reclasificar", "...media -> escalar (nunca 2ª pregunta)")
- **Fecha/fuente:** 2026-09-04 · `tests/test_triaje_nodos.js`
- **Estado:** vigente

### URG-22 · El paciente re-escala el mismo problema si no hay respuesta rápida (bracket guardado/perdido, familia de Máxima)
- **Entrada/disparador:** "Me olvidé de decirles que se le salió un bracket a Máxima\nLo tiene guardado" (retro #141, 2026-08-13) y "Hola\nMáxima no encuentra el bracket" (retro #185, 2026-09-02). En 60 días: 4 familias con 2-4 escalaciones por el mismo problema (Máxima x2, Catalina x2, Manu x3, la paciente del perno x4).
- **Falla previa:** el paciente re-escribe y re-escala; todo se escalaba; riesgo de mandar el mismo video dos veces.
- **Esperado:** bracket_suelto sin red flags > video; el flujo reconoce "mismo problema, segundo mensaje": estado Redis + reconstrucción desde ctx; si el LLM clasifica el MISMO tipo tras un video > escalar con razón `mismo_problema_post_video`; no se re-envía el mismo video.
- **Capa:** gate + nodo (`Triaje: Decidir`, estado Redis / `triaje_urgencias_log`)
- **Test:** `tests/test_triaje_nodos.js` ("ctx reconstruye estado", "...mismo tipo post video -> escalar"); `triaje/test_gate.js` (#141/#185 no disparan red flag)
- **Fecha/fuente:** 2026-08-13, 2026-09-02 · retro #141, #185; cs "Modo sombra retrospectivo con datos reales"
- **Estado:** vigente

### URG-23 · Caso límite: el arco se salió jugando al rugby (¿golpe/accidente o alambre?)
- **Entrada/disparador:** Manu: "hola raquel te quería informar que se me salió un alambre de la parte derecha de abajo jugando rugby\nlo tengo salido al alambre" (retro #120, 2026-08-09) y al día siguiente "ayer se terminó de salir\nal final del partido\nestá sin alambre directamente\ndale" (retro #126, 2026-08-10).
- **Falla previa:** el mismo paciente re-escala 3 veces; ambigüedad: el bot podría tratarlo como alambre_pincha normal sin considerar trauma; el 2º mensaje ("sin alambre directamente") ya no es resoluble con cera.
- **Esperado:** hoy el gate NO cuenta "rugby" como golpe (`esperado:false`, documentado como límite); decisión pendiente de Raquel sobre si "jugando al rugby" es trauma/red flag; si el alambre se salió completamente, la cera no alcanza > escalar; mientras tanto, sin match claro > escalar.
- **Capa:** gate (red flags, pendiente de criterio de Raquel)
- **Test:** `triaje/test_gate.js` ("rugby: hoy NO cuenta como golpe (pendiente Raquel)") fija el comportamiento actual, no el deseado
- **Fecha/fuente:** 2026-08-09/10 y 2026-09-02 · retro #120/#126; OQ "Casos límite del triaje (a)"
- **Estado:** pendiente de decisión (Raquel)

### URG-24 · Caso límite: hipérbole "me está matando la punta del alambre" vs red flag "dolor intenso"
- **Entrada/disparador:** "Hola si sabes q se me despegó una contención y me está matando la punta del alambre" (retro #159, 2026-08-19); "me está matando la punta del alambre".
- **Falla previa:** el LLM/gate lo marca `dolor_intenso` (red_flag) aunque es hipérbole coloquial + alambre de contención pinchando. Red flags reales en 60 días: 2/30, ambos "dolor que no cede"; cero trauma/sangrado/tragado. Contradicción: OQ del 2/9 pedía criterio de Raquel (escalar si no hay match); el test del 4/9 dejó `esperado:true` (hoy dispara). Se conserva lo vigente (dispara y escala) como estado actual y se marca el criterio como no resuelto.
- **Esperado:** hoy `escala === true` por `dolor_intenso` (más conservador); Raquel debe definir "dolor intenso" (¿"me está matando" = intenso?); si lo redefine, cambiar el test y el gate a la vez.
- **Capa:** gate (pendiente de calibración)
- **Test:** `triaje/test_gate.js` ("hipérbole 'me está matando' (pendiente Raquel)", esperado true)
- **Fecha/fuente:** 2026-08-19 y 2026-09-02 · retro #159; OQ "Casos límite del triaje (b)"
- **Estado:** pendiente de decisión (Raquel)

### URG-25 · Dolor persistente post-procedimiento con calmantes ("el dolor no baja", perno)
- **Entrada/disparador:** misma paciente escala 4 veces: "En algún momento el dolor se irá?" (retro #19), "Todavía sigo dolorida nose si es el perno que tengo" (#25), "Mañana estoy saliendo a jujuy si se puede pasar… La verdad que el dolor no baja y nose hasta cuando tengo que seguir tomando calmantes" (#33, 2026-07-21/23); otra paciente: "En algún momento el dolor o la molestia se irá? / Es permanente la molestia / Estoy con calmantes / Por qué el alidase se terminó el viernes" (#21).
- **Falla previa:** la misma paciente escala 4 veces por dolor post-procedimiento sin aparatología; el bot no tiene video para eso.
- **Esperado:** #33 es red flag "dolor que no cede" (pide evaluación urgente) > escalar siempre (gate `dolor_intenso`; "calmantes" también dispara); los demás `otra_urgencia` > escalar con aviso; el bot no recomienda medicación ni dosis ni diagnostica el "perno".
- **Capa:** gate (red flags) + nodo (clasificador `otra_urgencia`)
- **Test:** `triaje/test_gate.js` ("dolor que no baja + calmantes" > true); #19/#21/#25 sin test de clasificación (SIN TEST parcial)
- **Fecha/fuente:** 2026-07-21/23 y 2026-09-02/03 · retro #19, #21, #25, #33; cs "Fase 1 (sombra)"
- **Estado:** vigente (lista de red flags pendiente de validación de Raquel)

### URG-26 · Contención rota/partida/despegada (3 escalaciones, 2 pacientes) — sin video
- **Entrada/disparador:** "Te queria contar que se me acaba de partir la contención" (retro #130, Catalina, 2026-08-11) y al día siguiente "No se si pudieron leer mi mensaje porque me contesto el asistente virtual 🙄🙄😂" (#134); "se me despegó una contención y me está matando la punta del alambre" (#159, ver URG-24).
- **Falla previa:** sin tipo ni video; escala; la paciente respondió molesta porque contestó el asistente virtual en vez de un humano y re-escaló en 2 días seguidos.
- **Esperado:** clasificar `otra_urgencia` > escalar con aviso a la secretaria, canned al paciente, sin dejar sin respuesta; no inventar consejo (no hay video de contención); el gate NO dispara en #130 (`esperado:false`) y sí en #159 (ver URG-24). Candidato a 5º video junto con Invisalign (pendiente: ¿video propio o siempre escala?).
- **Capa:** nodo (clasificador `otra_urgencia`) + gate
- **Test:** `triaje/test_gate.js` (#130 no dispara; #159 sí); clasificación SIN TEST
- **Fecha/fuente:** 2026-08-11/12/19 y 2026-09-02 · retro #130/#134/#159; OQ "Casos límite del triaje (c)"; cs "Modo sombra retrospectivo"
- **Estado:** pendiente de decisión (¿video 5?)

### URG-27 · Invisalign: alineador partido en 2 y attachments/"ganchitos" aflojados — sin video
- **Entrada/disparador:** "Anoche mi hija estaba cepillando sus alineadores y se partieron en 2. Los de arriba." (retro #136, 2026-08-12); "Y después se aflojó los ganchitos blancos de la muela caída cuando apreté para ponerle los alineadores" (#83, 2026-08-01); "ayer cambié de alineadores, el 14 de julio me hice la limpieza con ultrasonido… y amanecí así:" con foto (#31, 2026-07-22). 3 casos en 60 días.
- **Falla previa:** escalaciones sin video disponible; riesgo de clasificarlo como bracket_suelto (ver URG-28).
- **Esperado:** `otra_urgencia` (Invisalign/alineadores) > escalar con aviso; el clasificador conservador usa `otra_urgencia` cuando no alcanza para los 4 tipos con video; ningún consejo ni video de brackets. Candidato a video 5/6 (pendiente de decisión).
- **Capa:** nodo (`triaje/prompt_clasificador.md`)
- **Test:** `triaje/test_gate.js` (#136 no dispara; #83 y #31 no están en el test); clasificación SIN TEST
- **Fecha/fuente:** 2026-07-22/08-01/08-12 y 2026-09-02 · retro #31, #83, #136; OQ "Casos límite del triaje (d)"
- **Estado:** pendiente de decisión (¿video o escala?)

### URG-28 · Attachment de Invisalign NO es bracket_suelto (+ captura de pantalla de contraseña)
- **Entrada/disparador:** "[IMAGEN] TIPO: OTRO … Pantalla de recuperación de contraseña de Invisalign…" + "Hola chicas consultas tienen mi ID? ..y no le pregunte a la doc si uso gomas o todavia no.. y se me salio un atache del 3er diente de arriba lado derecho" (retro #163, 2026-08-20).
- **Falla previa:** el clasificador automático lo marcó `bracket_suelto`; corrección manual > `otra_urgencia` (grupo Invisalign). Bracket suelto real = 6 casos, no 7.
- **Esperado:** `otra_urgencia`, NO `bracket_suelto`; no se envía el video de bracket suelto; escalar. El prompt del clasificador dice "bracket_suelto … NO incluye attachments de Invisalign".
- **Capa:** nodo (`triaje/prompt_clasificador.md`)
- **Test:** SIN TEST (`test_gate.js` no clasifica y no incluye "atache")
- **Fecha/fuente:** 2026-08-20 · retro #163; `triaje/prompt_clasificador.md`
- **Estado:** vigente

### URG-29 · Bracket que choca con el colmillo o lastima el labio (irrita sin estar suelto)
- **Entrada/disparador:** "hola raquel ayer me olvidé de mandarte mensaje y es por el tema del bracket de abajo que choca con el colmillo de arriba" (retro #99, 2026-08-04); "Buenas starde / Srta a mí hijita / Le duele / Una parte del labio dice que tiene un brackets que le molesta" (#153, 2026-08-18). 2 casos.
- **Falla previa:** no encaja en los 4 tipos con video; ¿se manda la cera (Opción 1 de alambre) o escala?
- **Esperado:** `otra_urgencia` (la cera de la Opción 1 aplica igual, pero no se improvisa consejo); sin red flag; escalar con aviso. Decisión de Raquel pendiente (¿cera o escalar?).
- **Capa:** nodo (`triaje/prompt_clasificador.md`)
- **Test:** `triaje/test_gate.js` (el gate no dispara); clasificación SIN TEST
- **Fecha/fuente:** 2026-08-04/18 y 2026-09-02 · retro #99/#153; OQ "Casos límite del triaje (e)"
- **Estado:** pendiente de decisión (Raquel)

### URG-30 · Microimplante: la cadena se salió — sin video
- **Entrada/disparador:** "buenas tardes, estuvo bien, pero la cadena del otro micro se me salio" (retro #132, 2026-08-11).
- **Falla previa:** sin video; escalación.
- **Esperado:** `otra_urgencia` > escalar; sin consejo; no red flag.
- **Capa:** nodo (clasificador)
- **Test:** `triaje/test_gate.js` (no dispara); clasificación SIN TEST
- **Fecha/fuente:** 2026-08-11 · retro #132
- **Estado:** vigente

### URG-31 · alambre_pincha tiene opciones secuenciales (1 cera, 2 pinza, 3 protector de la punta) en vez de 1 video por tipo
- **Entrada/disparador:** videos de Raquel (2/9): Opción 1 cera de ortodoncia, Opción 2 reinsertar con pinza; 17/9: Opción 3 "Alambre delantero que pincha porque se salió la protección de los extremos" (cera en la punta, algodón como alternativa).
- **Falla previa:** un video fijo por tipo no cubre "la 1 no alcanzó"; con la Opción 3, el flujo la envía recién si las Opciones 1 y 2 no sirvieron: si la causa es "se salió el protector", la Opción 2 (reinsertar con pinza) no aplica y es una vuelta de más, y la Opción 3 recomienda lo mismo que la 1.
- **Esperado:** mandar Opción 1 primero y ofrecer la siguiente si el paciente dice que no resolvió (`next` calculado genéricamente por `videosDe(tipo)` en `triaje/decidir.js`, sin cambio de código; solo INSERT en `triaje_videos`); los otros 3 tipos siguen el mismo patrón. Alternativas abiertas con Raquel: (a) dejar así, (b) fusionar el algodón dentro de la Opción 1, (c) pregunta guiada en la Opción 1 que salte a la Opción 3. Nada tocado.
- **Capa:** nodo (`triaje/decidir.js`) + dato (`triaje_videos`)
- **Test:** `tests/test_triaje_nodos.js` (fixtures con 2 opciones de alambre_pincha), `tests/test_triaje_textos_banlist.py --db` (18 textos, 0 disparos al 17/9), `scripts/check_triaje.py`; la Opción 3 sin test de flujo
- **Fecha/fuente:** 2026-09-02 y 2026-09-17 · BKL "Triaje de urgencias con videos — Ajuste de diseño", cs "alambre_pincha gana una Opción 3"
- **Estado:** pendiente de decisión (a/b/c con Raquel)

### URG-32 · Se salió el protector de la punta del alambre (Abel)
- **Entrada/disparador:** "Buenas tardes doctora quería pedirle si me lo puede ver a Abel porque tiene un alambre de punta que aparentemente se le salio lo que usted le pone en la punta para que no le pinche" (retro #183, 2026-08-31).
- **Falla previa:** escalación; el prompt del clasificador lo incluye explícitamente en alambre_pincha ("o se le salió el protector de la punta").
- **Esperado:** `alambre_pincha`, no red flag; video (Opción 1 cera; Opción 3 específica de protector desprendido agregada el 17/9, commit 7d0793e).
- **Capa:** nodo (prompt_clasificador + `triaje_videos`)
- **Test:** `triaje/test_gate.js` (no dispara); clasificación SIN TEST
- **Fecha/fuente:** 2026-08-31 y 2026-09-17 · retro #183; git 7d0793e
- **Estado:** vigente

### URG-33 · Exceso de alambre que lastima la cara interna (pide turno urgente)
- **Entrada/disparador:** "Buen día. Como están? Que día puedo acercarme al consultorio? Estoy con mucha molestia debido al exceso de alambre. Me lastima la cara interna" (retro #41, 2026-07-27).
- **Falla previa:** antes del triaje se escalaba siempre a la secretaria; la revisión manual lo marca compatible con `alambre_girado` (sobra arco de un lado), no solo alambre_pincha; único candidato de ese tipo en 60 días.
- **Esperado:** no es red flag; clasificar y mandar video (alambre_pincha Opción 1: cera, o alambre_girado según clasificador) con caption y salida de emergencia; el bot NO agenda turno de urgencia ni dice "venga"; escalar solo lo grave.
- **Capa:** gate (no red flag) + nodo (clasificador + `triaje_videos`)
- **Test:** `triaje/test_gate.js` (esperado false); clasificación SIN TEST
- **Fecha/fuente:** 2026-07-27 · retro #41
- **Estado:** vigente

### URG-34 · Alambre de atrás salido e incrustado en la mucosa
- **Entrada/disparador:** "Te consulto me pasa q tengo alambre de atrás salido y se incrustó en la parte de atrás" (retro #71, 2026-07-30).
- **Falla previa:** se escalaba (alambre_pincha, confianza alta).
- **Esperado:** `alambre_pincha` sin señales de alarma > video Opción 1 (cera); si no sirve, Opción 2 (reinsertar con pinza).
- **Capa:** gate + nodo
- **Test:** `triaje/test_gate.js` (no dispara); clasificación y secuencia SIN TEST específico
- **Fecha/fuente:** 2026-07-30 · retro #71
- **Estado:** vigente

### URG-35 · "Se soltó el alambre de arriba… para poner la gomita" (mensaje dirigido a Iris)
- **Entrada/disparador:** "Buenas tardes Iris. Cómo estás? Podés decirle a la doc que se soltó el alambre q tengo arriba para poner la Gomita" (retro #90, 2026-08-03).
- **Falla previa:** escalación; el paciente se dirige a la secretaria por nombre y no se identifica.
- **Esperado:** clasificar como `alambre_pincha` (arco principal salido del bracket/tubo); no red flag; video Opción 1.
- **Capa:** gate + nodo (clasificador)
- **Test:** `triaje/test_gate.js` (no dispara); clasificación SIN TEST
- **Fecha/fuente:** 2026-08-03 · retro #90
- **Estado:** vigente

### URG-36 · Alambre inferior cortado que se sale al comer (turno recién el 7)
- **Entrada/disparador:** "Hola buen día, a Julia se le cortó el alambre de los brackets de abajo y se le sale cada vez que come, también se le salió una de las gomitas. Tiene turno recién el 7" (retro #147, 2026-08-18).
- **Falla previa:** escalación urgente por un caso con turno a ~3 semanas.
- **Esperado:** `alambre_pincha` (confianza alta); video antes del turno; no red flag; el bot no adelanta el turno ni agenda.
- **Capa:** gate + nodo (clasificador)
- **Test:** `triaje/test_gate.js` (no dispara); clasificación SIN TEST
- **Fecha/fuente:** 2026-08-18 · retro #147
- **Estado:** vigente

### URG-37 · "Alambrecito suelto que lastima el cachete" sugiere ligadura, no arco
- **Entrada/disparador:** "Hola Irina como estas? Vos sabes que le quedó un alambrecito suelto a Justina y le esta lastimando el cachete\nPodra verla un ratito la dra?" (retro #143, 2026-08-13; escalación por intervención externa de Irina).
- **Falla previa:** el clasificador automático lo marcó `alambre_pincha` (media); la revisión manual dice que "alambrecito" sugiere `ligadura_pincha`; único candidato de ese tipo.
- **Esperado:** `ligadura_pincha` (alambrecito finito o gomita de un solo bracket), sin red flags; video "Ligadura de alambre que pincha.mp4" (ver URG-40).
- **Capa:** nodo (`triaje/prompt_clasificador.md`)
- **Test:** `triaje/test_gate.js` (solo el gate); clasificación SIN TEST
- **Fecha/fuente:** 2026-08-13 · retro #143; `triaje/prompt_clasificador.md`
- **Estado:** vigente

### URG-38 · "Se le salió el topecito" del diente superior (madre de Emma, luego con foto)
- **Entrada/disparador:** "hola buen dia como esta? disculpa a mi hija se le salio el topecito que esta en su diente de arriba" (retro #7, 2026-07-20) y 2 días después, con foto: "Hola buenas tardes [IMAGEN] TIPO: FOTO_DENTAL … Boca abierta mostrando dientes superiores con brackets, sin signos evidentes de caries o inflamación visible" (#23, turno pendiente al día siguiente 10:40).
- **Falla previa:** "topecito" es ambiguo; la descripción de la foto del analizador de imágenes es genérica y no alcanza para decidir el tipo.
- **Esperado:** `bracket_suelto` ("se salió el cuadradito/topecito") por TEXTO; NO usar visión (la foto es solo respaldo para la doctora); no red flag.
- **Capa:** nodo (`triaje/prompt_clasificador.md`) + prompt (decisión sin visión)
- **Test:** `triaje/test_gate.js` (no dispara); clasificación SIN TEST
- **Fecha/fuente:** 2026-07-20/21 · retro #7, #23
- **Estado:** vigente

### URG-39 · Bracket despegado de una muela / bracket delantero de una corona
- **Entrada/disparador:** "Buenas tardes / Es para avisar que a nahiara se le despegó un brackets de la muelita / Muchas gracias" (retro #169, 2026-08-26) y Flavia (#171): se soltó el bracket delantero de una corona.
- **Falla previa:** escalación; sin red flags.
- **Esperado:** `bracket_suelto` con video (es el que más falta: ~1 caso/semana).
- **Capa:** gate + nodo (clasificador)
- **Test:** `triaje/test_gate.js` (#169); #171 y clasificación SIN TEST
- **Fecha/fuente:** 2026-08-26 · retro #169, #171
- **Estado:** vigente

### URG-40 · ligadura_pincha reutiliza TEXTUALMENTE el texto ya aprobado de alambre_pincha
- **Entrada/disparador:** video "Ligadura de alambre que pincha.mp4" (42 MB) sin texto propio de Raquel.
- **Falla previa:** (riesgo) inventar contenido médico nuevo.
- **Esperado:** el caption reutiliza textualmente la técnica de cera/algodón que Raquel aprobó tres veces para `alambre_pincha` (Opción 1 y 3), mismo mecanismo y solución, a pedido explícito de Lucas; pasa el Banlist.
- **Capa:** prompt/dato (caption canned en `triaje_videos`) + banlist
- **Test:** `tests/test_triaje_textos_banlist.py --db`
- **Fecha/fuente:** 2026-09-30 · cs "Las 4 categorías del triaje de urgencias quedan con video activo"
- **Estado:** vigente

### URG-41 · Texto de bracket_suelto escrito por Claude, sin validación de Raquel
- **Entrada/disparador:** Lucas pidió 3 veces que Claude redactara el caption de `bracket_suelto` (Opción 1); no hay texto de Raquel. Es el único de los 4 textos del triaje sin validación de la Dra.
- **Falla previa:** (riesgo) mecanismo distinto a los otros 3 (pieza despegada, no algo que pincha); no se puede extrapolar con la misma confianza.
- **Esperado:** criterio conservador: NO manipular ni recolocar el bracket (riesgo de lastimarse o tragarlo), guardar la pieza si se desprendió del todo, venir a control, solo cera/algodón si molesta mientras tanto; ninguna maniobra activa. OJO: "guardar la pieza" es la frase que el Banlist prohíbe en el bot ("guarda"); verificar que el texto lo expresa de una forma que pasa el Banlist y que "venir a control" no se lee como invitación inmediata (patrón Mariela). Pendiente: que Raquel lo revise; si lo corrige, UPDATE del caption en `triaje_videos` + `test_triaje_textos_banlist.py --db` + `check_triaje.py`.
- **Capa:** prompt/dato (caption canned) + banlist (22 textos validados)
- **Test:** `tests/test_triaje_textos_banlist.py --db` (valida solo el Banlist, no el contenido clínico)
- **Fecha/fuente:** 2026-09-30 · cs "Las 4 categorías del triaje..."
- **Estado:** pendiente de decisión (validación de Raquel)

### URG-42 · Video equivocado subido a Storage (bracket_suelto)
- **Entrada/disparador:** se subió `WhatsApp Video 2026-09-29...` (contenido no relacionado) creyendo que era el de `bracket_suelto`; Lucas lo reprodujo y no coincidía.
- **Falla previa:** archivo equivocado en el Storage; se borró antes de que ningún paciente lo viera (la fila nunca llegó a estar activa).
- **Esperado:** para videos de triaje SIEMPRE confirmar el nombre exacto del archivo con Lucas antes de subir; nunca asumir por fecha/orden de descarga; el correcto fue `WhatsApp Video 2026-09-30 at 7.07.54 PM.mp4` (6,7 MB); la fila `activo=true` solo después de que Lucas reproduce el video.
- **Capa:** infra (proceso)
- **Test:** SIN TEST de contenido (`check_triaje.py` hace HEAD 200 de los 6 videos y `test_triaje_textos_banlist.py --db` revisa 22 textos; ninguno detecta un archivo equivocado)
- **Fecha/fuente:** 2026-09-30 · cs "Las 4 categorías del triaje de urgencias quedan con video activo"
- **Estado:** vigente (lección de proceso)

### URG-43 · Primera urgencia real de un paciente cae fuera del piloto y sin video
- **Entrada/disparador:** 2026-09-09: "Necesito un turno urgente con la dra... se salió el alambre 🥺" (17:50) y una foto de la boca (19:12).
- **Falla previa:** ambos quedaron `razon='fuera_piloto'` en `triaje_urgencias_log` (ids 14 y 15) y escalaron al grupo sin video (el triaje seguía en piloto solo para Lucas).
- **Esperado:** triaje abierto a todos desde 2026-09-10 01:40 (`telefonos_piloto=[]`); vigilar que la primera urgencia real de alambre_pincha reciba el video Opción 1 sin escalar y revisar los casos degradados en `triaje_urgencias_log`. Límite de entonces (solo alambre_pincha con video; bracket_suelto, alambre_girado y ligadura_pincha `activo=false` con caption '[PENDIENTE]' y escalan) quedó superado.
- **Capa:** infra (config `triaje_config` / `triaje_videos`)
- **Test:** `scripts/check_triaje.py` (estado de config y videos; no valida el caso real)
- **Fecha/fuente:** 2026-09-10 · cs "Triaje de urgencias ABIERTO A TODOS los pacientes"
- **Estado:** superado por 2026-09-30 (las 4 categorías con video activo, commits 8dbbd00/cb23c20/7d0793e); queda vigente la vigilancia del log

### URG-44 · La sombra reprocesa las escalaciones del propio triaje; memoria en orden indefinido
- **Entrada/disparador:** workflow sombra `Gm7ofyGohOJ2bI44` y filas de memoria insertadas por una CTE.
- **Falla previa:** la sombra reprocesaría las escalaciones `[TRIAJE…]`; la CTE insertaba las filas human/ai en orden indefinido.
- **Esperado:** la sombra ignora `motivo LIKE '[TRIAJE%'`; filas de memoria en orden human > ai; pre-filtro de la sombra: >10 min de edad (para que el Logger ya haya sincronizado); dedupe por `escalacion_id` UNIQUE.
- **Capa:** nodo
- **Test:** SIN TEST de la sombra (la fuente cita `tests/test_triaje_nodos.js`, que cubre Evaluar/Decidir/Preparar y no el pre-filtro de la sombra)
- **Fecha/fuente:** 2026-09-03/04 · cs "Fase 1 (sombra)" y "Fase 2 (retoques post-E2E)"
- **Estado:** vigente (verificar si la sombra sigue activa tras el cutover; no confirmado)

### URG-45 · SQL de persistencia no debe romperse con "$" ni comillas del paciente
- **Entrada/disparador:** caption con `$` y `'comilla'`; paciente escribe "$50.000".
- **Falla previa:** (riesgo, jueces) pg-promise formatea todo `$N` del string, incluso dentro de literales > "Variable $50 out of range" y el INSERT en memoria falla en silencio (onError continue).
- **Esperado:** el SQL se arma con `esc()` (duplica comillas, reemplaza `$` por chr(36)); sin queryReplacement; el SQL generado no contiene `$` crudo ni comillas rotas; E2E extra con "$50.000" y comillas simples.
- **Capa:** nodo (`Triaje: Decidir`)
- **Test:** `tests/test_triaje_nodos.js` ("sql sin $ crudo", "sql sin comillas rotas")
- **Fecha/fuente:** 2026-09-04 · `docs/triaje-fase2-analisis/jueces.md` (2º juez)
- **Estado:** vigente

### URG-46 · El aviso pasivo contamina /aprendizaje, dashboard y reportero
- **Entrada/disparador:** "[Triaje] Urgencia resuelta con video (alambre_pincha, Opción 1) — tel …" insertado en `escalaciones_log`.
- **Falla previa:** se clasifica 'senal' (tema Urgencias y dolor) y aparece como "caso que Asiri no supo resolver", infla el KPI de escalaciones, baja la autonomía en /dashboard y la sombra lo reprocesaría; `notify-grupo?silencioso=true` tampoco sirve porque Chatwoot Apply aplica el label humano igual.
- **Esperado:** `aviso_pasivo=false` por defecto; el registro vive en `triaje_urgencias_log` (accion='video'); carve-out `[TRIAJE VIDEO]` en `lib/escalaciones.ts` + dashboard + reportero ANTES de activar el aviso pasivo; fila de memoria `[VIDEO ENVIADO — tipo, Opción N]` con source 'triaje_video' (NO 'reminder_note': el Logger la mapearía a rol system y desaparecería del panel).
- **Capa:** nodo + infra (panel `lib/escalaciones.ts`)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-04/06 · `docs/triaje-fase2-analisis/mapeo-read_data_panel.md`, jueces.md MUST_FIX, `docs/roadmap-refactor-2026-09-06.md` B4
- **Estado:** vigente

### URG-47 · Bugs de cableado detectados por los jueces (Switch, Get Config, Cerrar, Formatting Agent)
- **Entrada/disparador:** revisión de los 3 diseños candidatos del triaje Fase 2.
- **Falla previa:** (a) `Switch Acción[normal]` > `Switch sobre Intent` entregaba el item de un Postgres `{id}` y `$json.intent` quedaba undefined > todo iba a Sub-Agent General; (b) `Get Config` devolvía N filas y el Re-check de Chatwoot corría N veces; (c) `Switch` declaraba `fallbackOutput: "none"` y conectaba un output 5; (d) `Triaje: Cerrar` no limpiaba Redis ni persistía la fila ai de cierre; (e) `texto_cierre` editable >80 chars pasaría por el Formatting Agent (LLM); (f) `modo_entrada` se deducía capturando la excepción de `$('Parse Intent')`; (g) el video salía sin re-check de label humano (~30-40 s entre `Bot Activo?` y `/send/media`); (h) `$('Triaje: Evaluar').first()` ambiguo en doble corrida.
- **Esperado:** grafts del diseño ganador (product-first): `jsonb_agg` a 1 item, `$('Parse Intent').isExecuted`, Re-check Humano dentro de Decidir (fail-open) > silencio, Redis DEL al escalar, texto de cierre por `/send/text` directo, `fullResponse + neverError` con IF de statusCode 2xx, Merge por posición.
- **Capa:** nodo
- **Test:** `tests/test_triaje_nodos.js` cubre la lógica de Evaluar/Decidir/Preparar pero NO el cableado de los Switch (SIN TEST de wiring; solo E2E)
- **Fecha/fuente:** 2026-09-04 · `docs/triaje-fase2-analisis/jueces.md`
- **Estado:** vigente

### URG-48 · Sub-Agent Urgencia prohíbe todo consejo (cera, enjuagues, medicación) pero el video de la Dra. sí lo da
- **Entrada/disparador:** "se me salió un bracket / alambre / tubo", dolor de muela, "qué tomo", "qué pastilla".
- **Falla previa:** el prompt del Sub-Agent Urgencia trata cera y pinza como PROHIBIDO ABSOLUTO (y su canned "Recibimos tu mensaje. Le pasamos a la doctora para que le coordine lo antes posible." de 84 chars pasa por el Formatting Agent), mientras el video de la Dra. sí las indica (decisión 2/9 y 4/9: los captions con "colocar cera" son consejo paliativo por diseño). Con el estado "[VIDEO ENVIADO]" en memoria el sub-agent podía leerlo como output propio contradictorio. Antes (KB 5, 2026-07-09): preguntar "¿Siente alguna molestia en esa parte?" y NO agendar turno de urgencia.
- **Esperado:** el consejo paliativo solo sale por texto canned de un nodo determinístico (caption del video); si lo emitiera el LLM, la prohibición aplica (ni cera, ni enjuagues, ni medicación, ni dosis, ni diagnóstico).
- **Capa:** prompt + nodo
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-04 · `prompts/v6_partials/urgencia_funcion.md`, `docs/triaje-fase2-analisis/mapeo-read_salida_memoria.md` OPEN QUESTIONS, `docs/kb-validacion-dra-2026-07-09.md` [5]
- **Estado:** superado (depende del nodo "Sub-Agent Urgencia", MUERTO en el v6 vivo al 4/10/2026; urgencia_dolor va al flujo Triaje). La regla "ningún LLM da consejo" sigue vigente para Sub-Agent General.
- **Riesgo de regresión:** si la consulta de dolor/aparato llega a Sub-Agent General (Router ambiguo > consulta_general, ver URG-01), verificar que el prompt curado de General sigue prohibiendo consejo médico y escalando dolores/urgencias.

### URG-49 · El rate limit de 10 mensajes/15 min descarta en silencio el 11º del flujo guiado
- **Entrada/disparador:** paciente ansioso con preguntas guiadas + fotos + respuestas cortas.
- **Falla previa:** el 11º mensaje se descarta sin aviso; el limiter cuenta además los mensajes fromMe del staff en la cuota del paciente (9/20 rate-limited eran de la clínica).
- **Esperado:** documentar; bypass por intent urgencia o contar solo turnos procesados es decisión pendiente; riesgo bajo en el flujo pregunta > video > Opción 2 (≤4 mensajes). `data.source='test_e2e_suite'` bypassa el límite en pruebas.
- **Capa:** nodo (`Rate Limit INCR`) / infra (Redis)
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-07-06 y 2026-09-04 · `docs/sesion-2026-07-06-precio-lid-reprogramacion.md` §3, mapeo-read_redis_humano.md RISKS
- **Estado:** pendiente de decisión

### URG-50 · `dentalink:status=down` y Chatwoot/Redis caídos apagan también las urgencias
- **Entrada/disparador:** caída de la agenda (Dentalink), de Chatwoot o de Redis.
- **Falla previa:** `dentalink:status='down'` silencia TODO el bot (incluido triaje y urgencias); `Existe paciente?` sin continueOnFail > Chatwoot caído = bot mudo para todos; Redis caído mata el bot en `Rate Limit INCR`.
- **Esperado:** las urgencias no deberían depender de Dentalink/Chatwoot: ante caída, el paciente con urgencia debe recibir igual el canned de escalación y el grupo ser avisado (pendiente de refactor).
- **Capa:** nodo / infra
- **Test:** SIN TEST
- **Fecha/fuente:** 2026-09-04/06 · mapeo-read_urgencia_path.md RISKS, `docs/roadmap-refactor-2026-09-06.md` B2
- **Estado:** pendiente de decisión (refactor B2)

### URG-51 · Procedimiento de E2E/demo del triaje: guion de 5 mensajes y limpieza obligatoria
- **Entrada/disparador:** guion: (1) "hola, se me salió el alambre de atrás y me pincha el cachete" > video Op1; (2) "no me sirvió, sigue pinchando" > video Op2; (3) "no lo pude meter con la pinza, sigue igual" > escalada; (4) "listo, gracias, ya me puse la cera" > cierre; (5) "se cayó y le sangra mucho la boca" > escalación inmediata por red flags.
- **Falla previa:** el paso 4 en dos de los diseños escalaba en falso (cierre vs URG_KW); los 3 diseños ignoraban que `tests/test_e2e_bateria.py` usa el shape viejo del webhook; mensajes de test viejos contaminaron una prueba real (URG-05).
- **Esperado:** ≥25 s entre mensajes (buffer de 22 s); máx 10 msgs/15 min; `data.source='test_e2e_suite'` bypassa el rate limit; limpiar antes y después con `scripts/limpiar_numero_demo.py` (label humano en TODAS las conversaciones, memoria incluida la fila `wa_outbound`, Redis chat_buffer/ratelimit/triaje, logs) en el mismo turno (regla dura #9); nadie reacciona desde el celular del consultorio en ese chat; `python scripts/check_triaje.py` antes de cualquier PUT.
- **Capa:** infra (procedimiento de prueba)
- **Test:** `tests/test_e2e_triaje.py` (harness con shape Evolution GO); `tests/test_e2e_bateria.py` usa shape viejo (no apto)
- **Fecha/fuente:** 2026-09-04 · `docs/triaje-fase2-diseno-2026-09-04.md` §7, `docs/triaje-fase2-analisis/diseno-ganador-product-first.md` §10-§12
- **Estado:** vigente

### URG-52 · Retrospectiva: ~47% de las escalaciones de urgencia se resuelven con video, concentradas en 2 tipos
- **Entrada/disparador:** 30 escalaciones candidatas de 183 en 60 días (6,5 semanas reales).
- **Falla previa:** todo se escalaba; distribución corregida: alambre_pincha 7-8 (6 pacientes), bracket_suelto 6, ligadura_pincha 0-1, alambre_girado 0-1, red_flag 2 (ninguno trauma/sangrado/tragado), otra_urgencia 12, no_urgencia 2.
- **Esperado:** priorizar videos de alambre_pincha y bracket_suelto; volumen ~15 urgencias/mes > ≤15 envíos de video/mes (~70 MB de egress); el 47% (14/30) se hubiera resuelto con video; `otra_urgencia` (12) sigue escalando.
- **Capa:** infra (decisión de producto)
- **Test:** `triaje/test_gate.js` (usa los mensajes reales de la retrospectiva); el KPI "% resuelto por video" SIN TEST
- **Fecha/fuente:** 2026-09-02 · `docs/analisis-retrospectivo-urgencias-2026-09-02.md`
- **Estado:** vigente

### URG-53 · Raquel: "nada en ortodoncia es de vida o muerte" — triaje generoso; scoring y mapeo semanal pendientes
- **Entrada/disparador:** reuniones del 14/7 y 15/8 con la Dra.: ya filmó 4 videos (alambre pincha, bracket suelto, alambre girado, ligadura pincha); falta que los mande y el fraseo de las preguntas; pidió además scoring de severidad y mapeo semanal de urgencias en el reportero.
- **Falla previa:** se escalaba todo (sobrecarga a Irina); el bot no tenía triaje guiado de urgencias.
- **Esperado:** clasificar el tipo > preguntas guiadas (fraseo pendiente de Raquel) > pedir foto (los pacientes no saben explicar) > video de la Dra. para urgencias menores (clave fuera de horario/fin de semana) > scoring de severidad > solo lo grave escala con aviso inmediato al grupo.
- **Capa:** gate + nodo + infra (reportero)
- **Test:** `triaje/test_gate.js`; scoring y mapeo semanal SIN TEST
- **Fecha/fuente:** 2026-07-14 y 2026-08-15 · `docs/reunion-2026-07-14-dra-raquel.md`, `docs/reunion-2026-08-15-dra-raquel.md`
- **Estado:** superado en parte (los 4 videos ya están activos desde 2026-09-30, commits 8dbbd00/7d0793e/cb23c20/ligadura/bracket); pendiente de decisión: scoring de severidad y mapeo semanal de urgencias en el reportero (no hay evidencia de que existan)

### Cobertura
- 53 casos consolidados (71 crudos de 4 extractores). SIN TEST total: 11 (URG-01, 04, 14, 15, 28, 42, 44, 46, 48, 49, 50); parciales por componente sin test: URG-12 (aislamiento "gate solo en urgencias"), URG-52 (KPI) y URG-53 (scoring/mapeo semanal); además ~15 con cobertura solo parcial (`triaje/test_gate.js` prueba que el gate NO escala, pero la clasificación del LLM a alambre_pincha/bracket_suelto/ligadura_pincha/otra_urgencia no tiene ningún test: URG-26 a 39).
- Huecos más peligrosos: (1) URG-01 Mariela: no existe test dedicado (el "13/13" citado no está en el repo) y el Router curado el 4/10 no nombra "incómoda/no come/expansor" y cae a `consulta_general` si es ambiguo; (2) clasificación del LLM sin tests (URG-26 a 39: Invisalign/attachment vs bracket_suelto, contención, foto sola) donde un error manda el video equivocado o deja sin respuesta; (3) URG-04/URG-46: label humano autoaplicado y Re-check que suprimen el canned, y aviso_pasivo que contamina panel/KPIs, sin ningún test.
