# Análisis retrospectivo de urgencias — modo sombra (2026-09-02)

Fuente: `escalaciones_log` últimos 60 días (183 escalaciones: 88 ruido, 21 operativo, 74 señal).
Candidatas al triaje (señal con tema urgencia/aparatología): **30**. Clasificador: `gpt-5-mini`, solo lectura.

## Revisión manual (Claude, 2/9) — leer antes que la tabla automática

Los 30 casos se revisaron uno por uno. Correcciones al clasificador:

- **#163 NO es bracket_suelto**: es un *attachment* de Invisalign ("atache del 3er diente") → `otra_urgencia` (grupo Invisalign). bracket_suelto real = **6**.
- **#17 NO es red_flag**: es una **cancelación de turno** ("Gerónimo pasó con fiebre... no va") que entró por CancelarReprogramar con error técnico → `no_urgencia`. Lección para el gate de red flags: la palabra "fiebre" sola dispara falsos positivos si se evalúa fuera del camino de urgencias — el gate debe correr SOLO después de que el Router clasificó como urgencia.
- **#143** ("alambrecito suelto que lastima el cachete"): "alambrecito" sugiere ligadura, no arco → probablemente `ligadura_pincha`, no alambre_pincha. Único candidato de ese tipo en 60 días.
- **#41** ("exceso de alambre que lastima la cara interna"): compatible con `alambre_girado` (sobra arco de un lado). Único candidato de ese tipo.
- **#120/#126** (Manu, rugby): el arco se salió *jugando al rugby* — ¿cuenta como "golpe/accidente" (red flag) o como alambre_pincha? Decisión de Raquel. El 2do mensaje ("está sin alambre directamente") ya no es resoluble con cera.
- **#159** ("me está matando la punta del alambre" de una contención): el LLM lo marcó red_flag por "dolor intenso", pero es hipérbole coloquial + alambre de contención pinchando. Muestra que "dolor intenso" como red flag es difuso — necesita criterio de Raquel.

**Distribución corregida (30 casos, ~6.5 semanas reales: la tabla arranca el 20/7):**

| Tipo | Casos | Pacientes distintos | Nota |
|---|---:|---:|---|
| alambre_pincha | 7–8 | 6 | 1 de ellos quizás alambre_girado (#41) |
| bracket_suelto | 6 | 5 | Emma x2, Máxima x2 (misma familia repite) |
| ligadura_pincha | 0–1 | 1 | solo #143, dudoso |
| alambre_girado | 0–1 | 1 | solo #41, dudoso |
| red_flag | 2 | 2 | ambos "dolor que no cede", ninguno trauma/sangrado/tragado |
| otra_urgencia | 12 | ~9 | ver sub-temas abajo |
| no_urgencia | 2 | 2 | foto sin consulta, cancelación por fiebre |

**Sub-temas recurrentes SIN video (dentro de otra_urgencia):**
- **Contención rota/partida/despegada: 3 escalaciones, 2 pacientes** (#130, #134 misma paciente en 2 días seguidos; #159). Candidato claro a 5to video.
- **Invisalign: 3 casos** — alineador partido (#136), attachments/"ganchitos" aflojados (#83, #163).
- **Bracket que irrita sin estar suelto: 2 casos** (#99 choca con colmillo, #153 lastima el labio) — la cera (Opción 1 de alambre) aplica igual.
- Microimplante (cadena salida, #132), dolor post-procedimiento sin aparatología (#19/#21/#25 + #33 red flag = la MISMA paciente …0434 escalando 4 veces por el mismo dolor de "perno").

**Lecturas clave:**
1. **~47% (14/30) se hubiera resuelto con video, y casi todo cae en solo 2 tipos**: alambre_pincha y bracket_suelto (~1 caso/semana cada uno). alambre_girado y ligadura_pincha: 0–1 caso en 6 semanas cada uno → los videos de esos 2 tipos tienen muy poco uso; **el de bracket_suelto es el que más falta**.
2. **Red flags reales son raros (2/30) y ninguno era trauma/sangrado/tragado** — todos "dolor que no cede". El gate determinístico va a disparar poco; el riesgo real está en el criterio difuso de "dolor intenso".
3. **Los pacientes re-escalan cuando no reciben respuesta rápida** (Máxima x2, Catalina x2, Manu x3, …0434 x4). Una respuesta inmediata con video corta esa repetición — pero el flujo tiene que reconocer "mismo problema, segundo mensaje" para no mandar el mismo video dos veces.
4. **Volumen: ~15 urgencias/mes → ≤15 envíos de video/mes (~70MB de egress)**. Supabase Storage público sobra.
5. **3 casos llegaron con foto** (#23, #79, #163) — el v6 ya las describe con el analizador de imágenes existente (`[IMAGEN] TIPO: FOTO_DENTAL...`), pero esa descripción es genérica y no alcanza para decidir tipo. Confirma la decisión de no usar vision para clasificar.

## Distribución (automática, sin corregir)

| Tipo | Casos | % | De los cuales confianza alta |
|---|---:|---:|---:|
| otra_urgencia | 11 | 36% | 5 |
| alambre_pincha | 8 | 26% | 7 |
| bracket_suelto | 7 | 23% | 6 |
| red_flag | 3 | 10% | 1 |
| no_urgencia | 1 | 3% | 1 |

**Se hubieran resuelto con video (4 tipos): 15/30 (50%)** — con confianza alta: 13.
**Red flags (siempre escalan): 3.** Otras urgencias sin video: 11. No urgencia: 1.

## Casos

### #41 · 2026-07-27 14:54 · tel …0260 · **alambre_pincha** (alta)
- Motivo del bot: Paciente sin nombre informado. Informa mucha molestia por exceso de alambre que lastima la cara interna; solicita turno urgente para resolver la molestia.
- Paciente dijo:
  - «Buen día. Como están? Que día puedo acercarme al consultorio? Estoy con mucha molestia debido al exceso de alambre. Me lastima la cara interna»
- Razón: Describe exceso de alambre que lastima la cara interna (arco sobresaliente que pincha) sin signos de trauma, sangrado, fiebre o dificultad respiratoria.

### #71 · 2026-07-30 17:38 · tel …4354 · **alambre_pincha** (alta)
- Motivo del bot: Paciente reporta alambre ortodóntico posterior salido e incrustado en la mucosa, solicita atención urgente para retirar/coordinar turno.
- Paciente dijo:
  - «Te consulto me pasa q tengo alambre de atrás salido y se incrustó en la parte de atrás»
- Razón: Alambre posterior salió y está incrustado/pinchando la mucosa, requiere extracción/ajuste pero sin señales de alarma mayores.

### #90 · 2026-08-03 18:21 · tel …9549 · **alambre_pincha** (alta)
- Motivo del bot: Paciente no se identifica en el mensaje. Informa que se le soltó el alambre superior y que necesita que la Dra. le ponga la gomita. Solicita que se le informe a la doctora.
- Paciente dijo:
  - «Buenas tardes Iris. Cómo estás? Podés decirle a la doc que se soltó el alambre q tengo arriba para poner la Gomita»
- Razón: El paciente indica explícitamente que 'se soltó el alambre' superior, es consistente con el arco principal salido del bracket/tubo y necesita que le pongan la gomita.

### #120 · 2026-08-09 20:14 · tel …2399 · **alambre_pincha** (alta)
- Motivo del bot: Paciente Álvaro Manuel Saltos informa que se le salió un alambre inferior derecho jugando rugby; solicita coordinación urgente.
- Paciente dijo:
  - «hola raquel te quería informar que se me salió un alambre de la parte derecha de abajo jugando rugby
lo tengo salido al alambre»
- Razón: El arco inferior derecho se salió y está protruyendo tras jugar rugby, sin signos de sangrado, hinchazón, fiebre o dificultad para respirar/deglutir.

### #126 · 2026-08-10 16:58 · tel …2399 · **alambre_pincha** (alta)
- Motivo del bot: Paciente Manu (Álvaro Manuel Saltos) informa que se le salió el alambre de la parte baja derecha jugando rugby; ahora quedó sin alambre. Solicita coordinación urgente para reparación.
- Paciente dijo:
  - «ayer se terminó de salir
al final del partido
está sin alambre directamente
dale»
- Razón: El arco/alambre principal se salió por completo durante un golpe (juego) y quedó sin alambre, requiere reparación urgente pero no hay signos de alarma reportados.

### #143 · 2026-08-13 17:14 · tel …3949 · **alambre_pincha** (media)
- Motivo del bot: Intervención externa: Irina informa que a Justina Quintana le quedó un alambrecito suelto que le está lastimando el cachete y pide que la Dra. la vea un momento. Coordinar atención y respuesta.
- Paciente dijo:
  - «Hola Irina como estas? Vos sabes que le quedó un alambrecito suelto a Justina y le esta lastimando el cachete
Podra verla un ratito la dra?»
- Razón: Describe un alambrecito suelto que le está lastimando el cachete, compatible con arco sobresaliendo que pincha y sin signos de sangrado, fiebre, dificultad o trauma.

### #147 · 2026-08-18 10:50 · tel …7347 · **alambre_pincha** (alta)
- Motivo del bot: Paciente Julia Sánchez de Bustamante: alambre inferior de brackets cortado que se sale al comer y se le cayó una gomita; tiene turno el 7 de Septiembre. Solicita coordinación urgente.
- Paciente dijo:
  - «Hola buen día, a Julia se le cortó el alambre de los brackets de abajo y se le sale cada vez que come, también se le salió una de las gomitas. Tiene turno recién el 7»
- Razón: El alambre inferior está cortado y se sale al comer, lo que indica que el arco principal está desalojado y necesita atención antes del turno.

### #183 · 2026-08-31 20:07 · tel …9329 · **alambre_pincha** (alta)
- Motivo del bot: Solicitan atención para Abel: tiene un alambre con la punta descubierta (se le salió el protector) y pide que lo vea para evitar que le pinche. Coordinar respuesta y posible turno.
- Paciente dijo:
  - «Buenas tardes doctora quería pedirle si me lo puede ver a Abel porque tiene un alambre de punta que aparentemente se le salio lo que usted le pone en la punta para que no le pinche»
- Razón: Protector del alambre se salió dejando la punta expuesta que puede pinchar mejilla/encía, por lo que corresponde alambre_pincha.

### #7 · 2026-07-20 14:51 · tel …4774 · **bracket_suelto** (media)
- Motivo del bot: Menor (hija) se le salió el topecito del diente superior; la madre solicita coordinación urgente para solución.
- Paciente dijo:
  - «hola buen dia como esta? disculpa a mi  hija se le salio el topecito que esta en su diente de arriba»
- Razón: Se indica que se le salió un 'topecito' del diente superior, lo que concuerda con un bracket/elemento adherido suelto sin signos de emergencia, aunque el término es algo ambiguo.

### #23 · 2026-07-21 20:14 · tel …4774 · **bracket_suelto** (alta)
- Motivo del bot: Madre de Emma envía foto del sector superior con brackets; topecito del bracket se salió. Solicita revisión y confirmación (turno pendiente mañana 10:40 hs).
- Paciente dijo:
  - «Hola buenas tardes
[IMAGEN] TIPO: FOTO_DENTAL  
MONTO: N/A  
DESTINATARIO: N/A  
FECHA: N/A  
HORA: N/A  
DESCRIPCION: Boca abierta mostrando dientes superiores con brackets, sin signos evidentes de caries o inflamación visible.»
- Razón: El resumen y la foto muestran que se salió la parte superior del bracket en el sector superior sin signos de sangrado, hinchazón o compromiso respiratorio, por lo que corresponde bracket_suelto.

### #141 · 2026-08-13 16:52 · tel …0434 · **bracket_suelto** (alta)
- Motivo del bot: Informe: familiar reporta que se le salió un bracket a la paciente Máxima; lo tiene guardado. Solicita coordinación/instrucciones sobre cómo proceder.
- Paciente dijo:
  - «Me olvidé de decirles que se le salió un bracket a Máxima
Lo tiene guardado»
- Razón: Se reporta que se le salió un bracket y lo tienen guardado, sin mencionar trauma, sangrado, hinchazón ni dolor intenso que sugieran alarma.

### #163 · 2026-08-20 17:54 · tel …5731 · **bracket_suelto** (alta)
- Motivo del bot: Paciente Florencia (ID paciente 442) pregunta si tienen su ID de Invisalign para recuperación de contraseña; además consulta si debe usar gomas y reporta que se le salió un attaché del 3er diente superior derecho. Solicita que la secretaria/doctora la contacte.
- Paciente dijo:
  - «[IMAGEN] TIPO: OTRO
MONTO: N/A
DESTINATARIO: N/A
FECHA: N/A
HORA: N/A
DESCRIPCION: Pantalla de recuperación de contraseña de Invisalign donde se solicita el ID de paciente para reestablecer la contraseña; incluye opciones de ayuda y restablecimiento vía correo electrónico.»
  - «Hola chicas consultas tienen mi ID? ..y no le pregunte a la doc si uso gomas o todavia no.. y se me salio un atache del 3er diente de arriba lado derecho»
- Razón: Paciente informa que se le salió un atache del 3er diente superior derecho, sin signos de sangrado, dolor intenso, hinchazón o dificultad, por lo que corresponde clasificación como bracket_suelto.

### #169 · 2026-08-26 17:06 · tel …9076 · **bracket_suelto** (alta)
- Motivo del bot: Paciente Nahiara Lamas: se despegó un bracket de una muela. Solicita coordinación urgente para reparación/consulta.
- Paciente dijo:
  - «Buenas tardes 
Es para avisar que a nahiara se le despegó un brackets de la muelita 
Muchas gracias»
- Razón: Paciente reporta que se le despegó un bracket de una muela sin síntomas de sangrado, dolor intenso, inflamación, dificultad para respirar/tragar o ingestión, por lo que corresponde bracket_suelto.

### #171 · 2026-08-26 17:31 · tel …4216 · **bracket_suelto** (alta)
- Motivo del bot: Paciente Flavia Silvana informa que se le soltó el bracket delantero de una corona y solicita que la doctora lo coordine lo antes posible.
- Razón: Se desprendió un bracket (delantero sobre una corona) y no hay signos de sangrado, hinchazón, dificultad respiratoria ni dolor intenso.

### #185 · 2026-09-02 20:13 · tel …0434 · **bracket_suelto** (alta)
- Motivo del bot: Paciente María informa que Máxima no encuentra el bracket que se le salió. Solicita indicaciones o coordinación para solución.
- Paciente dijo:
  - «Hola
Máxima no encuentra el bracket»
- Razón: Paciente informa que se le salió un bracket y no lo encuentra, sin signos de alarma.

### #79 · 2026-07-31 23:08 · tel …4432 · **no_urgencia** (alta)
- Motivo del bot: Paciente envió foto dental con brackets inferiores y una descripción. Solicita evaluación/consulta sobre la imagen.
- Paciente dijo:
  - «[IMAGEN] TIPO: FOTO_DENTAL
MONTO: N/A
DESTINATARIO: N/A
FECHA: N/A
HORA: N/A
DESCRIPCION: La imagen muestra una boca abierta con brackets en la parte inferior. También es visible la lengua y los dientes superiores.»
- Razón: Solo envió una foto para evaluación sin reportar dolor, sangrado, aparatología rota ni alambre que pinche o sobresalga.

### #19 · 2026-07-21 18:11 · tel …0434 · **otra_urgencia** (media)
- Motivo del bot: Paciente consulta si el dolor se irá; solicita orientación sobre la evolución del dolor y/o alivio. Requiere evaluación de la Dra.
- Paciente dijo:
  - «Hola
En algún momento el dolor se irá?»
- Razón: Paciente refiere dolor sin detallar si hay alambre/bracket involucrado ni signos de alarma, por lo que no puede clasificarse en las categorías específicas.

### #21 · 2026-07-21 18:37 · tel …6789 · **otra_urgencia** (media)
- Motivo del bot: Paciente María Sanchez de Bustamante informa dolor/ molestias dentales persistentes, está con calmantes y que el alidase se terminó el viernes; pide saber si la molestia será permanente. Coordinar con la doctora para atención/ indicaciones urgentes.
- Paciente dijo:
  - «En algún momento el dolor o la molestia se irá?
Es permanente la molestia
Estoy con calmantes
Por qué el alidase se terminó el viernes
Maria Sanchez de Bustamante»
- Razón: Dolor dental persistente y fin de medicación sin mención de trauma, sangrado, hinchazón o dificultad respiratoria; no hay datos de alambre/bracket/ligadura afectado, requiere evaluación/indicaciones urgentes pero no encaja en las categorías específicas.

### #25 · 2026-07-22 11:28 · tel …0434 · **otra_urgencia** (media)
- Motivo del bot: Paciente Sra. Maria reporta dolor persistente en cara/cachete; menciona que aún tiene dolor y sospecha que sea por un perno. Pide evaluación urgente y posible coordinación de turno.
- Paciente dijo:
  - «Buen día»
  - «Todavía sigo dolorida nose si es el perno que tengo»
- Razón: Paciente refiere dolor persistente en cara/cachete relacionado con un perno pero no reporta sangrado abundante, hinchazón, dificultad respiratoria/para tragar, fiebre ni ingestión de pieza, por lo que requiere evaluación pero no hay señal clara de red_flag ni de los tipos específicos de alambre/bracket.

### #31 · 2026-07-22 15:16 · tel …7347 · **otra_urgencia** (media)
- Motivo del bot: Paciente informa que tras limpieza con ultrasonido con la Dra. Mannori el 14 de julio y haber cambiado alineadores ayer, amaneció con un problema oral (envió foto). Solicita atención urgente para coordinar consulta/indicaciones.
- Paciente dijo:
  - «Hola buen día, ayer cambié de alineadores, el día 14 de julio me hice la limpieza con ultrasonido con la Dra.   Mannori y amanecí así:»
- Razón: Paciente reporta problema oral tras limpieza y cambio de alineadores pero no describe signos de alarma ni detalla la lesión ni presencia de alambre/bracket, por lo que no puede clasificarse en una categoría específica.

### #83 · 2026-08-01 13:10 · tel …@lid · **otra_urgencia** (alta)
- Motivo del bot: Paciente informa que se le aflojaron los ganchitos blancos de una muela caída al colocar los alineadores; solicita coordinación urgente para reparación/consulta.
- Paciente dijo:
  - «Y después se aflojó los ganchitos blancos de la muela caída cuando apreté para ponerle los alineadores»
- Razón: Los ganchitos (attachments) se aflojaron al colocar los alineadores y requieren reparación en consultorio, sin signos de alarma (sangrado, hinchazón, dolor intenso o dificultad).

### #99 · 2026-08-04 17:43 · tel …2399 · **otra_urgencia** (alta)
- Motivo del bot: Paciente Álvaro Manuel Saltos informa que un bracket inferior choca con el colmillo superior desde ayer y solicita atención/consulta urgente.
- Paciente dijo:
  - «hola raquel ayer me olvidé de mandarte mensaje y es por el tema del bracket de abajo que choca con el colmillo de arriba»
- Razón: Describe que un bracket inferior está chocando con el colmillo superior sin indicar alambre sobresaliente, bracket suelto ni signos de alarma, por lo que no encaja en las categorías específicas.

### #130 · 2026-08-11 18:04 · tel …9610 · **otra_urgencia** (alta)
- Motivo del bot: Paciente Catalina Carattoni informa que se le partió la contención. Solicita atención/coordinar turno urgente para reparación.
- Paciente dijo:
  - «Hola como estas»
  - «Te queria contar que se me acaba de partir la contención»
- Razón: La contención se partió y requiere reparación/coordinar turno, no hay signos de emergencia (sangrado, dolor intenso, hinchazón o dificultad).

### #132 · 2026-08-11 21:03 · tel …6953 · **otra_urgencia** (media)
- Motivo del bot: Paciente Hernán Andres Rojas informa que la cadena del otro microimplante se le salió; solicita indicaciones o coordinación de revisión.
- Paciente dijo:
  - «buenas tardes, estuvo bien, pero la cadena del otro micro se me salio»
- Razón: Se desprendió la cadena del microimplante (componente del aparato) sin signos de sangrado, hinchazón o dolor intenso y no encaja en las categorías específicas.

### #134 · 2026-08-12 13:07 · tel …9610 · **otra_urgencia** (alta)
- Motivo del bot: Paciente Catalina informó que se le partió la contención y expresa molestia porque respondió el asistente virtual; solicita atención humana para coordinar lo antes posible.
- Paciente dijo:
  - «Holaa buen dia»
  - «No se si pudieron leer mi mensaje porque me contesto el asistente virtual 🙄🙄😂»
- Razón: Paciente reporta contención rota sin datos de sangrado, dolor intenso, hinchazón, dificultad para respirar/tragar ni ingestión de piezas, por lo que entra en otra_urgencia.

### #136 · 2026-08-12 15:50 · tel …5318 · **otra_urgencia** (alta)
- Motivo del bot: Hija Ámbar Malena Rioja: alineadores superiores se partieron en 2 anoche; solicita coordinación urgente para evaluar y resolver.
- Paciente dijo:
  - «Buenas tardes»
  - «Anoche mi hija estaba cepillando sus alineadores y se partieron en 2. Los de arriba.»
- Razón: Alineadores removibles superiores se partieron en dos; es una urgencia de ortodoncia para evaluar/reemplazar pero no hay signos de trauma, sangrado, fiebre ni dificultad respiratoria.

### #153 · 2026-08-18 21:19 · tel …2058 · **otra_urgencia** (media)
- Motivo del bot: Paciente menor (hija) con dolor en el labio por un bracket que le molesta; madre pide atención urgente para coordinar solución.
- Paciente dijo:
  - «Buenas starde
Srta a mí hijita
Le duele
Una parte del labio dice que tiene un brackets que le molesta»
- Razón: Paciente menor presenta dolor por irritación de un bracket en el labio, sin indicios claros de que el bracket esté suelto ni de signos de alarma (sangrado/hinchazón/fiebre/atragantamiento).

### #17 · 2026-07-21 12:16 · tel …3899 · **red_flag** (alta)
- Motivo del bot: [CancelarReprogramar] phone 5493885083899, mensaje: Buen dia geronimo paso con fiebre y aun no le baja ..no va.disculpe.. Razon: error_tecnico_dentalink
- Paciente dijo:
  - «Buen dia geronimo paso con fiebre y aun no le baja ..no va.disculpe.»
- Red flags: fiebre
- Razón: Paciente refiere fiebre persistente, lo cual es una señal de alerta que requiere contacto/consulta médica y que no debe presentarse en la consulta.

### #33 · 2026-07-23 12:52 · tel …0434 · **red_flag** (media)
- Motivo del bot: Paciente sin nombre informado reporta dolor persistente en zona de perno, viaja mañana a Jujuy y solicita poder pasar mañana a ver a la Dra. Pide coordinación urgente para turno antes de viajar.
- Paciente dijo:
  - «Hola buen día»
  - «Mañana estoy saliendo a jujuy si se puede pasar en caso que puedo podría pasar a verte Raquel? La verdad que el dolor no baja y nose hasta cuando tengo que seguir tomando calmantes»
- Red flags: dolor intenso que no cede
- Razón: Paciente refiere dolor persistente en zona de perno que no cede con calmantes y solicita evaluación urgente antes de viajar.

### #159 · 2026-08-19 20:11 · tel …9704 · **red_flag** (media)
- Motivo del bot: Paciente informa que se le despegó una contención y la punta del alambre le está provocando mucho dolor; solicita atención urgente.
- Paciente dijo:
  - «Hola si sabes q se me despegó una contención y me está matando la punta del alambre»
  - «Dale mil gracias !»
- Red flags: dolor intenso que no cede
- Razón: Contención despegada con punta de alambre que provoca dolor intenso ('me está matando'), requiere atención inmediata.
