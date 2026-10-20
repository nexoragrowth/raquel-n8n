# v7 — Orquestador + sub-agentes con alcance estricto (diseño, 2026-10-08)

> Estado: **CONSTRUIDO en el repo (08/10), NO desplegado.** Reemplaza al "agente único con herramientas" (retirado a `v7/_retirados/`).
> Lo construido sigue §8 "Cambios por la crítica", que **prevalece** sobre §1-§7 donde se contradicen (orquestador = UNA llamada con salida JSON + despacho por código).
> Fuente de la decisión: `memory/decisions.md` → 2026-10-08 "v7 = orquestador + sub-agentes con alcance estricto" y
> "La IA decide qué quiso decir el paciente; el código ejecuta y garantiza".
> Orden de Lucas (textual): *"odio las regex; para algo tenemos el agente orquestador, para orquestar agentes; ponele bien los puntos y los
> límites a los sub agentes; 0 conversaciones; lo único que hacemos es agendar, reprogramar, cancelar, recordar, confirmar, recepcionar pagos,
> dar información del negocio y el servicio, y asistir urgencias con la info que tenemos; lo que salga de ahí es mala directriz".*

Tres reglas que ordenan todo el diseño:

1. **La inteligencia (LLM) decide qué quiso decir el paciente.** El paciente es jujeño: escribe corto, cortado y con faltas ("ya" es sí, "la nena", "pa", "q", "alia"). Ninguna regex sobre el texto del paciente decide la intención ni lo frena.
2. **El código ejecuta y verifica, no juzga.** Escribe en Dentalink, Supabase y Redis, arma los textos exactos (read-back, bloque de horarios, datos bancarios, derivación, menú), compara las afirmaciones con la agenda real y respeta el modo sombra.
3. **Cero conversación.** Se hacen 8 cosas: agendar, reprogramar, cancelar, recordar (lo hace el workflow de Recordatorios, que no se toca), confirmar, recepcionar pagos, informar sobre el negocio y el servicio, y asistir urgencias. Todo lo demás recibe una respuesta fija de derivación más un aviso; si el paciente insiste, pasa a modo humano.

---

## 1. Arquitectura

```
Webhook v6 ─► filtros TÉCNICOS (kill-switch, fromMe, rate limit, buffer 22 s, modo humano) ─► fork "V7: ¿Vivo?" ─► CEREBRO v7
                                                                                             (ver §6: el fork pasa ANTES de Pre-filtro Cierre y Gate Canned)
CEREBRO v7
 1. Entrada {phone, texto, pushName, modo, historial_json}
 2. Lecturas (código): historial 30 filas · recordatorios abiertos · KB + agente_directrices · identificar paciente (ver_turnos)
    · Redis: propuesta pendiente, ofertas, avisos recientes, pago reciente
 3. "Armar contexto" (código): arma el CONTEXTO común (§3). SIN desvíos: no hay IF de cierre, de "sí directo" ni de bienvenida.
 4. ORQUESTADOR (AI Agent, gpt-5-mini, esfuerzo low, max_iter 4)
       herramientas = 4 sub-agentes + 4 herramientas-código directas
       ├─ turnos       → workflow "v7 Agente Turnos"       (LLM + ver_turnos, elegir_ficha, buscar_horarios, gestionar_turno, confirmar_turno, lista_espera)
       ├─ pagos        → workflow "v7 Agente Pagos"        (LLM + registrar_pago, datos_pago)
       ├─ informacion  → workflow "v7 Agente Información"  (LLM, sin herramientas, solo DATOS DEL CONSULTORIO)
       ├─ urgencias    → workflow "v7 Agente Urgencias"    (LLM + derivar_triaje)
       ├─ menu_bienvenida      (código: texto del panel / KB 40)
       ├─ derivar_secretaria   (código: texto fijo + aviso ACCIÓN; 2.º en 30 min → modo humano)
       ├─ pasar_a_humano       (código: pidió una persona → silencia + aviso)
       └─ no_entendi           (código: repregunta fija; la 2.ª seguida → derivar_secretaria)
       Respuesta propia del orquestador: SOLO "[LISTO]" o "[NO_REPLY]". Cualquier otro texto se descarta.
 5. Lecturas Redis: libro de escrituras, propuesta, ofertas, bloque, triaje, TRAZA (lo que devolvió cada sub-agente y cada herramienta)
 6. "Componer respuesta" (código, §3.4): arma el mensaje final con los textos de la traza, en orden fijo, sin reescribirlos.
 7. "Salida" (código): chequeo_salida contra la agenda · datos bancarios pegados · avisos al grupo y memoria SOLO con modo === 'vivo'.
 8. Devolver {texto, enviar, silencio, derivar_triaje, ...}  (mismo contrato que hoy, el v6 no se entera del cambio)
```

**Por qué así y no como la variante de especialistas del 06/10.** Esa variante perdió 22/45 contra 31/45 del agente único porque escribían dos modelos en fila: el especialista redactaba y el padre volvía a redactar (17 de 83 respuestas corregidas por código). En este diseño el orquestador **no redacta nunca**: lo que llega al paciente es el texto que devolvió cada sub-agente (que en Turnos y Pagos es casi siempre un texto armado por código), compuesto por código. Así se elimina la causa principal de esa derrota.

### Quién hace qué

| Situación (la decide el ORQUESTADOR, no una regex) | Va a | Qué ve el paciente |
|---|---|---|
| Sacar, cambiar o cancelar un turno, ver cuál tiene, elegir un horario, para quién es, aceptar o rechazar la confirmación pendiente, confirmar asistencia, lista de espera | `turnos` | Bloque de horarios / read-back / texto de éxito (código), o una pregunta mínima |
| "Ya pagué", "le giré", comprobante; pide alias, CBU o cuenta | `pagos` | Texto fijo de recepción (código) / "Le paso los datos para transferir:" + datos pegados por código |
| Precio, horarios, dirección, tratamientos, obra social, cómo se atiende | `informacion` | 1 a 3 frases sacadas solo de los DATOS |
| Dolor, molestia, sangrado, hinchazón, golpe, no come, aparato o alambre roto, suelto o que pincha | `urgencias` | Nada de Asiri: responde el protocolo de triaje (video aprobado, pregunta guiada o la doctora) |
| Saludo solo o "quiero información" sin tema | `menu_bienvenida` | Menú del panel, tal cual |
| Pide hablar con una persona, la secretaria o la doctora | `pasar_a_humano` | Texto fijo; el bot se calla en ese chat |
| Cualquier otra cosa: presupuestos, dólares, cuotas o excepciones, quejas, bajas, proveedores, temas personales, consulta clínica sin urgencia, respuesta a una pregunta del personal | `derivar_secretaria` | «Le paso con la secretaria para que lo atienda.» + aviso ACCIÓN; si insiste, modo humano |
| Agradece, se despide, "ok" sin nada pendiente, "estoy llegando" | — | `[NO_REPLY]` (lo decide el orquestador) |
| No se entiende ni con el contexto | `no_entendi` | Repregunta fija (código) |

"Recordar" no pasa por el cerebro: lo hace el workflow de Recordatorios (`7RqTApkvVavRmq3R`, NO TOCAR). El bot **nunca pide confirmación de asistencia** (decisión del 08/10). Solo confirma cuando el paciente la da, con `turnos` → `confirmar_turno`.

---

## 2. Agentes: prompts, herramientas y contratos

Convenciones comunes:

- **Modelo:** gpt-5-mini, esfuerzo `low`, temperatura por defecto. Sub-agentes con `max_iter` 4 (Turnos 6).
- **Texto de usuario de cada sub-agente** (lo arma el código, el orquestador no lo puede tocar): `CONTEXTO` (§3) + `\n\nPEDIDO DEL ORQUESTADOR: ` + `pedido`.
- **System de cada sub-agente:** su prompt + `DATOS DEL CONSULTORIO` (solo a `informacion` y `pagos`; a `turnos` y `urgencias` no les hace falta).
- **Salida de cada sub-agente:** exactamente una de estas tres:
  - el texto para el paciente;
  - `[NO_REPLY]`;
  - `FUERA_DE_ALCANCE` (el pedido no es de su área: no improvisa).

  El wrapper ("Armar salida", código) le agrega el **estado**, que sale de los resultados de sus herramientas y no del texto del modelo, y lo empuja a la traza. Contrato de la traza: `{agente, texto, fuera_de_alcance, herramientas:[{nombre, ok, etapa, texto_para_el_paciente?}], estado}`.
- Las herramientas que escriben exigen `modo === 'vivo'` explícito (decisión del 08/10, no revisable).

Los largos de los prompts se midieron con los bloques de abajo (todos por debajo de 2.500 caracteres; ver §6.1, test de largo).

### 2.1 Orquestador

**Herramientas:** `turnos`, `pagos`, `informacion`, `urgencias` (campo del modelo: `pedido`); `menu_bienvenida` (sin campos); `derivar_secretaria` (`cita_textual`, `motivo` libre de una línea); `pasar_a_humano` (`cita_textual`); `no_entendi` (sin campos).
**Recibe:** el CONTEXTO completo (§3), sin DATOS DEL CONSULTORIO (no los necesita para delegar).
**Devuelve:** `[LISTO]` o `[NO_REPLY]`. El texto final lo arma "Componer respuesta" con la traza.

```text
Sos el ORQUESTADOR de Asiri, la secretaria virtual de la Dra. Raquel Rodríguez (ortodoncia, San Salvador de Jujuy). NO le escribís al paciente: entendés qué quiso decir y llamás herramientas. Lo que ve el paciente lo arman las herramientas.

El paciente es jujeño: escribe corto, cortado, con faltas y en varios mensajes ("ya" = sí, "la nena" = su hija, "pa" = para). Interpretá con el CONTEXTO (historial, turnos del celular, propuesta pendiente, horarios ofrecidos). Si el contexto alcanza para entender, no repreguntes.

SOLO ESTO HACEMOS:
- turnos: sacar, cambiar o cancelar un turno, ver cuál tiene, elegir un horario, para quién es, aceptar o rechazar la confirmación pendiente, confirmar asistencia cuando él la confirma, lista de espera.
- pagos: avisa que pagó o manda comprobante; pide datos para pagar.
- informacion: precio, horarios, dirección, tratamientos, obra social, cómo se atiende.
- urgencias: dolor, molestia, sangrado, hinchazón, golpe, no puede comer, aparato, alambre o bracket roto, suelto o que pincha. Ante la duda entre urgencia y otra cosa: urgencias.

En pedido escribí en una línea qué quiere y TODOS los datos que dio (fecha, hora, nombre, DNI, "acepta la confirmación pendiente" o "la rechaza"). Si pide varias cosas, llamá a cada agente en el mismo paso.

Sin agente:
- Saludo solo, o pide información sin decir de qué: menu_bienvenida.
- Pide hablar con una persona, la secretaria o la doctora: pasar_a_humano con su frase.
- Todo lo demás (presupuestos, dólares, cuotas o excepciones, quejas, bajas, proveedores, temas personales, consultas clínicas sin urgencia, respuestas a una pregunta del personal): derivar_secretaria con su frase. No lo intentes resolver.
- No se entiende ni con el contexto: no_entendi.
- Si un agente devuelve FUERA_DE_ALCANCE, mandalo al que corresponda o a derivar_secretaria; nunca al mismo dos veces.

Tu respuesta final es SOLO una palabra:
- [LISTO] si llamaste herramientas.
- [NO_REPLY] si no hay nada que responder: agradece o se despide sin pedir nada, avisa que está en camino o llegando, "ok" sin nada pendiente.
Nunca escribas texto para el paciente: se descarta.
```

### 2.2 Sub-agente TURNOS

**Herramientas:** `ver_turnos`, `elegir_ficha`, `buscar_horarios`, `gestionar_turno` (**+ campo `confirma`**), `confirmar_turno`, `lista_espera`.
**Recibe:** CONTEXTO + `pedido` (+ campos fijos: tel, exec_id, modo, texto_paciente, ultimo_asiri, historial reciente del paciente para validar el DNI).
**Devuelve:** el `texto_para_el_paciente` de la herramienta tal cual, una pregunta mínima o `FUERA_DE_ALCANCE`. Estado, en la traza: `readback_pendiente` | `escrito_ok` | `escrito_error` | `bloque_ofrecido` | `confirmado` | `pregunta` | `fuera_de_alcance`.

```text
Sos el agente de TURNOS de Asiri (secretaria virtual de la Dra. Raquel Rodríguez). Recibís el CONTEXTO (historial, turnos del celular, recordatorios enviados, propuesta pendiente, horarios ofrecidos) y un PEDIDO del orquestador. Trabajás solo con tus herramientas, nunca de memoria.

TU ALCANCE: sacar turno, cambiarlo, cancelarlo, decir qué turno tiene, confirmar asistencia cuando el paciente la confirma, lista de espera. Nada más. Si el pedido no es eso, devolvé exactamente: FUERA_DE_ALCANCE

CÓMO
- Quiere turno, un día o una franja: buscar_horarios de una (con hasta si limita la fecha). No preguntes franja ni para quién antes de ofrecer.
- Elige un horario ofrecido: gestionar_turno. reserva si no tiene turno; sumar si tiene y pide otro; cambio solo si pidió CAMBIAR el suyo. Nunca un horario que no salió de buscar_horarios.
- Acepta la confirmación pendiente (cualquier forma de sí: "ya", "dale", "obvio", "sisi", 👍): gestionar_turno con confirma=true. Si la rechaza o cambia algo, NO pongas confirma.
- Cancelar: gestionar_turno tipo cancelacion con fecha_turno_viejo.
- Varias fichas y no sabés para quién: elegir_ficha con el nombre o DNI que dio, eligiendo de la lista que te devuelve. Si no lo dijo, preguntá solo: "¿Para quién es el turno? (nombre o DNI)".
- Paciente nuevo, recién al elegir horario: pedí nombre, apellido y DNI en un solo mensaje y pasalos a gestionar_turno.
- Confirma asistencia a un recordatorio: confirmar_turno, una vez por fecha. Vos nunca pidas que confirme.
- Pide que lo anoten si se libera un turno: lista_espera, una vez.
- No encontrás el turno que nombra: mostrá los que figuran en el CONTEXTO y preguntá cuál es.

QUÉ DEVOLVÉS
- Si una herramienta trae texto_para_el_paciente, tu respuesta es ESE texto, tal cual, sin agregar ni quitar.
- Si no, una o dos frases de "usted" con una sola pregunta, sin saludar, sin presentarte, sin ofrecer otras cosas.
- Nunca digas que algo quedó hecho si la herramienta no lo confirmó. Nunca escribas vos fechas, horas ni el texto de confirmación.
```

### 2.3 Sub-agente PAGOS

**Herramientas:** `registrar_pago` (sin campos del modelo), `datos_pago` (**campo nuevo `moneda`: `pesos` | `otra`**).
**Recibe:** CONTEXTO + `pedido` + DATOS DEL CONSULTORIO.
**Devuelve:** los `texto_para_el_paciente` de sus herramientas, uno debajo del otro, o `FUERA_DE_ALCANCE`. Estado: `pago_anotado` | `pago_ya_anotado` | `datos_enviados` | `fuera_de_alcance`. Los datos bancarios los pega la Salida, debajo, cuando `datos_pago` devolvió `ok` con `moneda=pesos`.

```text
Sos el agente de PAGOS de Asiri (secretaria virtual de la Dra. Raquel Rodríguez). Recibís el CONTEXTO, un PEDIDO del orquestador y los DATOS DEL CONSULTORIO.

TU ALCANCE, solo dos cosas:
1. Recepcionar un aviso de pago o un comprobante.
2. Pasar los datos para pagar en pesos.
No validás montos, no decís que un pago ingresó, no acordás cuotas, fechas, descuentos ni otras formas de pago. Si el pedido es otra cosa, devolvé exactamente: FUERA_DE_ALCANCE

CÓMO
- Avisa que pagó, transfirió, "ya le giré", o manda comprobante o foto de pago: registrar_pago. No le preguntes para quién es, a qué corresponde ni su DNI: lo imputa la secretaria.
- Pide alias, CBU, la cuenta o cómo pagar: datos_pago con moneda="pesos". Si quiere pagar en dólares u otra moneda: datos_pago con moneda="otra".
- Si pide las dos cosas, llamá las dos.

QUÉ DEVOLVÉS
- El texto_para_el_paciente de cada herramienta, tal cual, uno debajo del otro. Nada más.
- Si una herramienta devuelve fuera_de_alcance, devolvé exactamente: FUERA_DE_ALCANCE
- Nunca escribas vos alias, CBU, montos ni "ya lo recibimos".
```

### 2.4 Sub-agente INFORMACIÓN

**Herramientas:** ninguna. Es el único sub-agente que redacta libremente, y solo con los DATOS.
**Recibe:** CONTEXTO + `pedido` + DATOS DEL CONSULTORIO (KB 20, 21, 25, 36, 39, KB_EXTRA y notas_para_asiri; **sin** KB 24 bancaria, que es de Pagos).
**Devuelve:** 1 a 3 frases, o `FUERA_DE_ALCANCE`. Estado: `respondido` | `fuera_de_alcance` | `ofrece_primera_consulta` (si cerró con la oferta fija).

```text
Sos el agente de INFORMACIÓN de Asiri (secretaria virtual de la Dra. Raquel Rodríguez, ortodoncia, San Salvador de Jujuy). Recibís el CONTEXTO, un PEDIDO del orquestador y los DATOS DEL CONSULTORIO. Respondés dudas sobre el consultorio y el servicio usando SOLO los DATOS.

TU ALCANCE: precio de la consulta y del tratamiento, horarios de atención, dirección (solo si la pide), tratamientos, obra social, cómo se atiende (solo con turno previo, sin guardia; un menor va con su tutor) y lo que esté escrito en los DATOS.

LÍMITES
- Si la respuesta no está en los DATOS, devolvé exactamente: FUERA_DE_ALCANCE. No inventes, no supongas, no digas "lo consulto y le aviso".
- También FUERA_DE_ALCANCE si pide algo que no es información: presupuesto para su caso, descuento, excepción, opinión o indicación clínica, datos para transferir.
- Nunca invites a ir ahora ni sin turno. "Lo esperamos el día de su turno" está bien.
- No opines, no des diagnósticos, no hables de otros temas.

CÓMO RESPONDÉS
- De "usted", 1 a 3 frases, solo lo que preguntó, con los números y las palabras de los DATOS. Sin saludar, sin presentarte, sin emojis.
- Si el CONTEXTO dice que no tiene turnos y preguntó por precio, tratamientos u obra social, terminá con esta frase exacta: "¿Quiere que le busque un turno para la primera consulta?"
```

### 2.5 Sub-agente URGENCIAS

**Herramientas:** `derivar_triaje` (`cita_textual`).
**Recibe:** CONTEXTO + `pedido`.
**Devuelve:** `[NO_REPLY]` (responde el triaje del v6 con el video aprobado por la Dra., la pregunta guiada o el aviso a la doctora) o `FUERA_DE_ALCANCE`. Estado: `derivado` | `derivar_fallo` | `fuera_de_alcance`. Si `derivar_triaje` falla, "Componer respuesta" manda por código la frase fija «Le paso su mensaje a la doctora para que lo vea.» y un aviso `[ACCIÓN URGENTE]` al grupo (en vivo).

```text
Sos el agente de URGENCIAS de Asiri (secretaria virtual de la Dra. Raquel Rodríguez, ortodoncia). Recibís el CONTEXTO y un PEDIDO del orquestador.

TU ÚNICA TAREA: pasar el caso al protocolo de urgencias de la clínica con derivar_triaje. Ese protocolo le responde al paciente por su cuenta: un video de ayuda aprobado por la doctora, una pregunta guiada o la doctora misma.

CÓMO
- Llamá derivar_triaje UNA vez. En cita_textual van las palabras del paciente que describen el problema, copiadas tal cual. Si lo contó en varios mensajes, juntalas.
- Después devolvé exactamente: [NO_REPLY]

LÍMITES, sin excepción
- No das indicaciones: ni "guarde", "traiga", "tome", "saque", "póngase".
- No diagnosticás ni tranquilizás: ni "es normal" ni "no se preocupe".
- No invitás a ir a la clínica, no das la dirección, no prometés que lo atienden hoy.
- No escribís ningún texto para el paciente: solo [NO_REPLY] o FUERA_DE_ALCANCE.
- Si el pedido no es un problema de la boca, los dientes o el aparato, devolvé exactamente: FUERA_DE_ALCANCE
```

### 2.6 Herramientas-código directas del orquestador (nuevas o cambiadas)

| Herramienta | Entrada (modelo) | Qué hace el código | Texto al paciente (fijo, código) |
|---|---|---|---|
| `menu_bienvenida` | — | Lee `agente_directrices.menu_bienvenida` (o KB 40). | El menú tal cual. Si es conversación nueva, el menú ya incluye la presentación. |
| `derivar_secretaria` | `cita_textual`, `motivo` | `clinica` acción `derivar`: aviso `[ACCIÓN]` con la frase **textual** del paciente. Si ya hubo un aviso ACCIÓN en los últimos 30 min (contador `avisos`), pasa a modo humano (`tomar=true`, silencia). | «Le paso con la secretaria para que lo atienda.» / si insiste: «Ya le pasé su consulta a la secretaria; le responde por este chat.» |
| `pasar_a_humano` | `cita_textual` | Valida contra alucinación **sin regex de intención**: la mayoría (≥ 60 %) de los tokens de la cita, normalizados con `sinT`, tienen que estar en los mensajes del paciente de este turno. Si valida: silencia + aviso. Si no: lo trata como `derivar_secretaria`, que tampoco deja al paciente hablando solo con el bot. | «Le paso con la secretaria para que lo atienda.» |
| `no_entendi` | — | Si el último mensaje de Asiri ya era este mismo texto (comparación exacta de un texto propio), hace `derivar_secretaria`. | «Disculpe, no le entendí bien. ¿Me lo puede escribir de otra forma? Puedo ayudarlo con turnos, pagos, información del consultorio o una urgencia.» |

Cambios en las herramientas de los sub-agentes:

- `gestionar_turno`: campo nuevo `confirma` (boolean, lo decide Turnos). Se borran `esAfirmacion` y `siDirecto`. Con `confirma=true`, el código ejecuta la **propuesta guardada** (no la que mande el modelo en esa llamada) solo si se cumplen las cuatro condiciones: (a) `estado === 'pendiente'`; (b) el último mensaje de Asiri contiene ese read-back (`normT`/`includes`); (c) está dentro del TTL de 30 min; (d) el candado INCR está libre. Si alguna falla, devuelve el read-back de nuevo con `texto_repregunta`. Con `confirma` ausente o false, nunca escribe.
- `gestionar_turno` y el DNI: el código **deja de pisar** `nuevo_dni` con un número del texto. Verifica que esos dígitos (6 a 8) aparezcan literalmente en algún mensaje del paciente de las últimas 12 h. Si no aparecen, devuelve `faltan_datos` y el agente lo pide.
- `elegir_ficha`: si no hay coincidencia exacta, devuelve la **lista cerrada** de nombres de las fichas del celular (sin ids). El agente vuelve a llamar con uno de esos nombres, tal cual, y el código verifica que pertenezca a la lista. Así los apodos ("la Agus", "Juanchi") los resuelve el modelo y no un puntaje de tokens. `fichaDelNuevo` solo da por nuevo a alguien si el agente lo declara así **y** el DNI no coincide con ninguna ficha.
- `registrar_pago` y `datos_pago`: devuelven `texto_para_el_paciente` fijo, armado por código. Ya no traen `para_asiri` con instrucciones para que redacte el modelo. Con `moneda=otra`, `datos_pago` devuelve `{ok:false, fuera_de_alcance:true}`.
- `clinica_core`: se borran `VERIF` (las cuatro regex) y los motivos `queja` y `baja_de_datos`. Las acciones que quedan son `aviso` (lo usa `derivar_secretaria`), `derivar`, `humano` (solo `pidio_persona`, con validación por tokens), `pago`, `datos_pago`, `espera` y `triaje`.

---

## 3. Estado y contexto compartidos

El problema del v6 era que cada sub-agente veía solo su rama, sin memoria ni turnos, y el Router mandaba a **una** sola rama. Aquí:

### 3.1 Un único CONTEXTO, armado por código y pasado igual a todos

"Armar contexto" (código, `historial_core` + `agenda_core`) arma un texto con estos bloques. El orquestador y cada sub-agente reciben **el mismo texto** como campo fijo (`$('Armar contexto').first().json.mensaje_agente`). El orquestador solo agrega `pedido`; no puede recortar ni reescribir el contexto.

| Bloque | Fuente | Para qué |
|---|---|---|
| AHORA (día, fecha y hora de Jujuy) | código | fechas relativas ("el jueves") |
| CONVERSACIÓN NUEVA: sí/no (12 h sin mensajes) | historial | presentación y menú; es un **dato**, no una compuerta |
| HISTORIAL (últimos 12, etiquetados PACIENTE / ASIRI / STAFF / RECORDATORIO) | `n8n_chat_histories` | entender mensajes cortados; ver qué preguntó el personal |
| FICHAS Y TURNOS DE ESTE CELULAR (nombres, turnos vigentes) | `ver_turnos` (identificar) | para quién es; qué turno cambiar |
| RECORDATORIOS YA ENVIADOS (sin respuesta; no pedir que confirme) | `recordatorios_enviados` | saber que "confirmo" va a confirmar_turno |
| CONFIRMACIÓN PENDIENTE: «read-back» (hace N min) | Redis `propuesta:{tel}` | que el orquestador y Turnos sepan que "ya" acepta ESO |
| HORARIOS OFRECIDOS | Redis `ofertas:{tel}` | elegir "el de las 17" sin volver a buscar |
| AVISOS RECIENTES / PAGO RECIENTE | contadores Redis | no repetir avisos; detectar insistencia |
| MENSAJE ACTUAL (los mensajes del buffer, en orden) | Entrada | — |

### 3.2 Estado entre llamadas: Redis y Dentalink, no la memoria de un LLM

- Lo que una herramienta descubre o propone queda en Redis con la clave del teléfono (`ofertas`, `propuesta`, `bloque`, `libro`, `triaje`, `pago`, `avisos`; con prefijo `v7s:` en sombra). Si en el mismo mensaje el orquestador llama a Turnos y después a Pagos, Pagos lee lo que Turnos dejó a través de sus propias herramientas. En el mensaje siguiente, "Armar contexto" lo vuelve a leer.
- Lo que se le dijo al paciente queda en la memoria (`n8n_chat_histories`) como **un solo** mensaje `ai`: el texto compuesto final, con `additional_kwargs.source = 'asiri_v7'` y `agentes = [...]`. Así el read-back siempre está en `ultimo_asiri` y la verificación del "sí" funciona. Solo en vivo; `[NO_REPLY]` no se guarda.
- Los sub-agentes no tienen memoria propia: cada llamada recibe el CONTEXTO completo. No hay estado escondido en la ventana de un modelo.

### 3.3 Varios sub-agentes en un mismo mensaje

"hola, quiero pasar el turno del jueves y pásame el alias" → el orquestador llama a `turnos` ("cambiar el turno del jueves") y a `pagos` ("pide los datos para transferir") en el mismo paso. n8n los ejecuta uno después del otro dentro del paso, y cada uno deja su resultado en `traza:{tel}:{exec}`. El orquestador ve lo que devolvió cada uno (por ejemplo, `FUERA_DE_ALCANCE`) y puede redirigir **una** vez.

### 3.4 "Componer respuesta" (código, determinístico)

1. Si el orquestador respondió `[NO_REPLY]` y no hay ninguna herramienta en la traza → silencio.
2. **Urgencia derivada:** v7 en silencio para este mensaje, porque responde el triaje. Si en la traza hay otros pedidos (turno, pago), en vivo sale un FYI al grupo: "Además pidió: …". Si `derivar_triaje` falló → frase fija + `[ACCIÓN URGENTE]`.
3. **pasar_a_humano válido** o **derivar_secretaria con insistencia** → solo su texto fijo.
4. **menu_bienvenida** → el menú solo, si no hubo otro agente. Si hubo otro, se omite el menú.
5. Si no, se concatena en este orden fijo, con una línea en blanco entre partes: **Información → Pagos (+ datos bancarios por código) → Turnos → derivación fija**.
   - El read-back de Turnos va **al final** y es lo único con pregunta. Si hay read-back, se quita la oferta fija de Información, que es una comparación exacta de un texto nuestro.
   - Los textos con `FUERA_DE_ALCANCE` no se muestran. Si **todo** quedó fuera de alcance y el orquestador no derivó, el código aplica `derivar_secretaria`.
6. Si es conversación nueva y no se manda el menú → se antepone «Soy Asiri, la secretaria virtual de la Dra. Raquel.» (es un dato de 12 h, no una regex).
7. Si no hay texto y tampoco `[NO_REPLY]` → `no_entendi`.
8. El texto compuesto pasa por `chequeo_salida` (§5) y por la Salida actual (modo sombra o vivo).

---

## 4. Cada regex del inventario y qué la reemplaza

| # | Dónde | Qué juzgaba | La reemplaza |
|---|---|---|---|
| 1 | `agenda_core.esAfirmacion` | si el paciente dijo "sí" (dispara escrituras) | **Turnos** → `gestionar_turno(confirma=true)`. El código solo valida datos: propuesta pendiente, read-back visto, TTL y candado. Se borra. |
| 2 | `agenda_core.siDirecto` + IF "¿Sí a la confirmación?" | atajo sin LLM | Orquestador → Turnos. Se borran el atajo y el nodo "Gestionar (sí directo)". |
| 3 | `decidir` → `dnisPaciente` | pisaba el DNI del modelo | El modelo pasa el DNI y el código verifica que aparezca literal en los mensajes del paciente; si no, `faltan_datos`. Nunca reemplaza. |
| 4 | `historial_core.esCierre` + `ultimoPideRespuesta` + IF "¿Es un cierre?" | silencio ante "gracias" | **Orquestador** → `[NO_REPLY]`. La Salida solo respeta la marca. Se borran. |
| 5 | `esSaludo` / `esPedidoInfo` + IF "¿Es una bienvenida?" | menú ante un saludo | **Orquestador** → `menu_bienvenida` (texto exacto por código). "Conversación nueva" pasa a ser un dato del contexto. Se borran. |
| 6 | `clinica_core.VERIF.pidio_persona` | si pidió una persona | **Orquestador** → `pasar_a_humano`. El código valida por superposición de tokens de la cita (anti-alucinación), sin lista de frases. Si no valida → `derivar_secretaria` (nunca deja al paciente hablando solo con el bot). |
| 7 | `VERIF.queja`, `VERIF.baja_de_datos` | queja / baja | Fuera de alcance → **orquestador** → `derivar_secretaria` (texto textual en el aviso). Se borran, junto con esos motivos. |
| 8 | `VERIF.urgencia` | código muerto | Se borra. Urgencias → sub-agente **Urgencias**. |
| 9 | Salida: veto `/dólar\|usd/` sobre el texto | si se pegaban los datos bancarios | **Pagos** → `datos_pago(moneda)`. Con `otra` → FUERA_DE_ALCANCE → derivación. Se borra. |
| 10 | Salida: `DIJO_AVISO` | si el modelo dijo "le avisé" sin herramienta | Ya no redacta nadie que pueda decirlo: la derivación es una herramienta con texto fijo. Queda como red pasiva solo en la variante de transición; en el diseño final se borra. |
| 11 | Salida: `RE_META`, marcas, `RE_DECILE`, `RE_PRESENTA`, jerga | limpieza cosmética de lo que redacta el modelo | Se reduce a quitar `[MARCAS]` y `FUERA_DE_ALCANCE` sueltos. La presentación la pone el código (§3.4 paso 6), así que `RE_PRESENTA` y `ya_se_presento` sobran. |
| 12 | `chequeo_salida.js` + `JS_FALTA_BLOQUE` | verifica afirmaciones contra la agenda | **SE QUEDA** (no juzga al paciente). Ahora solo atrapa desvíos, porque los textos de éxito, read-back y bloque los arma el código. |
| 13 | Plan de conexión: "V7: Pre-Triaje Regex" (`esUrgenciaFuerte`) | urgencia antes del modelo | **No se agrega.** Ver §7, riesgo R1: lo decide Lucas, porque choca con la regla dura 5 de `.claude/CLAUDE.md`. Propuesta: el orquestador ("ante la duda, urgencias") + el clasificador LLM del triaje del v6 ("Triaje: Evaluar") son las dos capas. |
| 14 | v6 "Pre-filtro Cierre" | silencio por inyección, autoresponders y emojis | El fork "V7: ¿Vivo?" se mueve **antes** de este nodo en el plan de conexión. En el v7, el orquestador interpreta el emoji en contexto (👍 a un read-back = acepta) y la inyección cae en derivar_secretaria o no_entendi. El v6 no se toca. |
| 15 | v6 "Gate Canned Directo" (baja, alias) | canned por regex | Igual: el fork va antes. La baja es fuera de alcance; el alias, Pagos → `datos_pago`. |
| 16 | `ficha_core.elegir`, `fichaDelNuevo`, `pasoBuscarDni` (tokens) | a qué ficha corresponde un nombre | **Turnos** elige de la lista cerrada que devuelve `elegir_ficha`. El código verifica la pertenencia a la lista y el DNI exacto. |
| 17 | `historial_core` (etiquetas), `normHora`, `datosNuevo`, `es4xx`, `evaluarConfirmacion`, `parseBloque`, parseo de la KB 24 | parseo de datos propios | **SE QUEDAN** (no juzgan al paciente). Pendiente opcional: etiquetar recordatorios por `additional_kwargs.source`. |

---

## 5. Código que se conserva, y por qué

| Pieza | Por qué se queda |
|---|---|
| `buscar_horarios` (`horarios_core`, sub-WF del v6, tope de 2 bloques) | Arma el bloque real de Dentalink; ningún modelo escribe horarios. |
| `gestionar_turno` (`agenda_core.proponer/decidir/ejecutar`) | El read-back lo arma el código y la escritura solo pasa con propuesta pendiente + read-back visto + TTL + candado + `confirma`. |
| `ejecutar_propuesta` (consumo atómico, re-verificar la cita, alta, POST reserva, PUT anulación, libro) | La escritura es exacta, idempotente y queda registrada. |
| `confirmar_turno` (`confirmar_core`, IF "¿Es sombra?") | Escribe en Dentalink y en recordatorios; solo con modo vivo. |
| `ver_turnos`, `elegir_ficha` | Los ids nunca salen del código; el modelo ve nombres. |
| `clinica` (aviso, derivar, humano, pago, datos_pago, espera, triaje) + contadores Redis | Avisos exactos, insistencia → modo humano (anti-bucle REAL-09) y anti-repetición del pago (REAL-02). |
| Datos bancarios pegados por la Salida (KB 24) | El alias y el CBU nunca los escribe un modelo. |
| `chequeo_salida.js` | Lo que se dice "hecho" tiene escritura ok en el libro; los horarios nombrados salieron de una oferta o son turnos del paciente; el read-back va solo. |
| Modo sombra / vivo explícito (`modo === 'vivo'`) | Decisión del 08/10, no revisable: un campo que no llega no escribe. |
| Webhook de pruebas solo-Lucas, `limpiar_numero_demo.py` | Pruebas sin tocar pacientes reales; sin residuos (regla 9). |
| Componer respuesta (§3.4) | Hace que el texto final sea la suma de textos verificados, sin re-redacción. |

---

## 6. Plan de pruebas

### 6.1 Offline (sin n8n, Evolution ni Dentalink; `node tests\*.mjs`, `python tests\test_v7_*.py`)

**Cambian**

- `tests/test_agenda_core.mjs`: se van los casos de `esAfirmacion` y `siDirecto`. Entran:
  - `confirma=true` con read-back visto → ejecutar;
  - `confirma=true` sin propuesta, con propuesta vencida o con un read-back que no está en `ultimo_asiri` → no ejecuta y repite el read-back;
  - `confirma` ausente → nunca ejecuta;
  - DNI que no aparece en los mensajes → `faltan_datos`;
  - DNI distinto en el texto → **no** pisa.
- `tests/test_historial_clinica_core.mjs`: se van `esCierre`, `esSaludo`, `esPedidoInfo` y `VERIF`. Entran:
  - `humano` validado por tokens (cita con faltas corregidas por el modelo → válida; cita inventada → derivar);
  - `derivar` 1.º → ACCIÓN, 2.º en 30 min → modo humano;
  - `datos_pago` con `moneda=otra` → `fuera_de_alcance`;
  - textos fijos de `pago` / `datos_pago`;
  - todo en sombra sin `avisar`.
- `tests/test_ficha_horarios_core.mjs`: `elegir_ficha` devuelve una lista cerrada y acepta solo nombres de la lista.
- `tests/test_v7_cerebro.py`: se van los desvíos (cierre, sí directo, bienvenida) y entra la ausencia de esos IF en el grafo.
- `tests/test_v7_grafo.py` / `test_v7_grafo_herramientas.py`: herramientas nuevas (`menu_bienvenida`, `derivar_secretaria`, `no_entendi`) con `modo` declarado en el trigger (C10/C11 para cada una que escribe).
- `tests/test_v7_ma.py` → se reescribe como `tests/test_v7_orquestador.py`.

**Se agregan** (`tests/test_v7_orquestador.py`, con `harness_grafo.mjs` y respuestas del modelo simuladas)

1. Composición (§3.4):
   - orden fijo;
   - read-back al final;
   - urgencia gana y manda el FYI de lo demás;
   - el menú solo sin otros agentes;
   - todo FUERA_DE_ALCANCE → derivación;
   - texto libre del orquestador descartado;
   - vacío → no_entendi;
   - presentación solo con conversación nueva.
2. Contrato de la traza: cada sub-agente empuja `{agente, texto, estado, herramientas}`. El estado sale de las herramientas y no del texto.
3. Herramientas de cada sub-agente: **ninguna fuera de su lista** (Turnos sin `registrar_pago`, Información sin herramientas, Urgencias solo `derivar_triaje`, el orquestador sin herramientas de Dentalink).
4. Largo de los prompts: cada `v7/prompt_*.md` nuevo < 2.500 caracteres.
5. Ningún prompt nuevo contiene "Te esperamos", "venite", "ahora mismo" ni "pida confirmación" (control del texto **nuestro**, no del paciente).
6. Sin regex sobre el texto del paciente: un test estático falla si `cerebro*.json` o `clinica_core.js` vuelven a tener `esAfirmacion`, `esCierre`, `esSaludo`, `VERIF` o el veto de dólares.

**Ruteo con el modelo real, sin n8n** (`tests/ruteo_orquestador.py`, nuevo; llama solo a OpenAI con herramientas simuladas, no escribe nada; lo corre Lucas con su key):

- Batería de ~80 mensajes jujeños con el destino esperado, sacados de `docs/dataset_conversaciones_reales.json` y de REAL-01..13.
- Ejemplos: "ya" / "obvio" / "sisi porfa" / "hágale" / 👍 con read-back pendiente → turnos+confirma; "ok, lo pienso" con read-back → [NO_REPLY] o turnos sin confirma; "pasame el alia" → pagos; "cobran en dolar? si no pasame la cuenta" → pagos `pesos`; "la nena tiene el alambre q le pincha" → urgencias; "mi hija esta incomoda, no come" (Mariela) → urgencias; "Buenas, horario de atención del lunes" → informacion; "que me atienda la seño" → pasar_a_humano; "ya me tienen podrida" → derivar_secretaria; "hola doc buenas tardes q tal" → menu_bienvenida; "gracias mañana" con nada pendiente → [NO_REPLY]; "me duele la cabeza, quiero cambiar el turno" → turnos (no urgencias dental) o urgencias, porque las dos son aceptables y se registran.
- Criterio: 100 % en urgencias y en confirma (ningún falso "sí"), ≥ 95 % en el resto, 3 corridas.

### 6.2 Sombra, solo con el celular de Lucas

1. Lucas crea los workflows nuevos **inactivos** (`crear_v7_en_n8n.py --aplicar` lo corre él). El cerebro nuevo se llama desde el webhook de pruebas solo-Lucas, con `modo: 'sombra'`. No se toca el v6.
2. Examen `tests/examen_v7.py` con los 15 escenarios (DANA-01..10, AGE-01..05) × 3 + 15 escenarios jujeños nuevos. Se compara con el agente único (31/45) y se miden p50/p95 con `scripts/tiempos_v7.py`, las correcciones de `chequeo_salida` y el costo por mensaje.
3. Retrospectiva en sombra (`tests/retrospectiva_v7.py`) sobre conversaciones reales: solo lectura; las escrituras quedan en `v7s:` o simuladas.
4. Criterio de pase:
   - ≥ 38/45 en el examen;
   - 0 escrituras sin "sí";
   - 0 afirmaciones falsas que llegan al paciente;
   - 100 % de urgencias derivadas;
   - 0 respuestas fuera de las 8 tareas (todo lo demás, derivación fija);
   - p95 ≤ 25 s.
5. Recién con OK explícito de Lucas: el flag "V7: ¿Vivo?" solo para `5491161461034`, en vivo y con prueba de punta a punta (regla 8), según el plan de conexión **corregido**: el fork pasa antes de Pre-filtro Cierre y Gate Canned. Ese cambio del v6 requiere backup previo, `check_triaje.py` y mostrar el diff.
6. Después de **cada** prueba con un teléfono real: `scripts/limpiar_numero_demo.py` (memoria, logs, label humano, claves `v7s:`) en el mismo turno.

---

## 7. Riesgos y cómo se cubren

| # | Riesgo | Cobertura |
|---|---|---|
| R1 | **Urgencia sin regex previa** (regla dura 5 de `.claude/CLAUDE.md`: triaje antes del modelo) | Conflicto que **decide Lucas**. Propuesta: (a) el orquestador tiene la regla "ante la duda, urgencias" y la batería de ruteo exige 100 %; (b) el triaje del v6 tiene su propio clasificador LLM; (c) Urgencias no escribe nada al paciente. Si Lucas quiere mantener una red previa, que sea **solo de más** (deriva y nunca bloquea), documentada como excepción en `decisions.md`. Hasta su OK no se cambia la regla 5. |
| R2 | **Latencia**: orquestador + sub-agente = 2-3 llamadas en fila (el agente único tenía p50 8,4 s) | El orquestador no redacta (su respuesta final es una palabra); los sub-agentes con esfuerzo low y max_iter bajo; Turnos con read-back y bloque de código; Urgencias, Información y Pagos de 1 o 2 pasos. El buffer de 22 s ya existe. Medir en sombra: p95 ≤ 25 s como corte. Si no alcanza: esfuerzo `minimal` en el orquestador. Nunca volver a un atajo por regex. |
| R3 | **Costo**: ~2-3× tokens por mensaje (el contexto va a cada agente) | Contexto de 12 mensajes; DATOS solo a Información y Pagos; prompts < 2,5 k. Medir el costo por mensaje en sombra con `tiempos_v7.py` antes del vivo. |
| R4 | **Alucinación de un sub-agente** | Turnos y Pagos devuelven textos de código; `chequeo_salida` verifica afirmaciones y horarios; Información solo con los DATOS o `FUERA_DE_ALCANCE`; Urgencias no escribe al paciente. |
| R5 | **Ruteo equivocado del orquestador** | `FUERA_DE_ALCANCE` le vuelve y puede redirigir una vez; si todo queda fuera de alcance, el código deriva. Batería de ruteo con el modelo real. |
| R6 | **Falso "sí"** (el modelo pone `confirma` ante "ok, lo pienso") | La escritura además exige read-back visto, TTL y candado. El read-back es explícito («¿Procedo…?»), así que el paciente aceptó un texto concreto. La batería exige 0 falsos `confirma`. |
| R7 | **Bucles** (derivar o no_entendi una y otra vez) | Contadores por código: 2.º ACCIÓN en 30 min → modo humano; 2.º no_entendi seguido → derivar. |
| R8 | **"Cero conversación" demasiado seco** (el 07/10 se pedía no derivar por una duda) | La pregunta mínima la hace el sub-agente de su área ("¿Para quién es el turno?"). Lo ambiguo de verdad lo resuelve `no_entendi` con un texto fijo. Queja y baja pasan a ser fuera de alcance: **esto reemplaza** la decisión del 07/10 "queja/baja → avisar y seguir"; hay que registrarlo en `decisions.md`. |
| R9 | **Regresión de lo que hoy anda** (31/45) | Construir en paralelo (workflows nuevos, el cerebro actual queda intacto) y pasar a vivo solo con un criterio de pase mejor que el actual. |

### Pendiente de Lucas antes de construir

1. R1: ¿se mantiene alguna red de urgencias antes del modelo?
2. Mover el fork del v7 antes de Pre-filtro Cierre y Gate Canned. Es un cambio en el v6: backup, diff y OK.
3. Confirmar que queja y baja de datos pasan a fuera de alcance (reemplaza lo decidido el 07/10).
4. Aceptar el corte de latencia (p95 ≤ 25 s) y el criterio de pase (≥ 38/45).

### Archivos que se tocarían (en la etapa de construcción, no ahora)

- **Nuevos:**
  - `v7/prompt_orquestador_v2.md`, `v7/prompt_sub_turnos.md`, `v7/prompt_sub_pagos.md`, `v7/prompt_sub_informacion.md`, `v7/prompt_sub_urgencias.md`;
  - `scripts/v7_workflows_subagentes.py` (generaliza `_wf_especialista`), `wf_cerebro(ma="orquestador")`;
  - `tests/test_v7_orquestador.py`, `tests/ruteo_orquestador.py`.
- **Cambian:** `v7/agenda_core.js`, `v7/clinica_core.js`, `v7/ficha_core.js`, `v7/historial_core.js` (se borran las funciones de juicio), `scripts/v7_workflow_cerebro.py` (JS_CONTEXTO sin desvíos, Componer respuesta, Salida reducida), `scripts/v7_workflow_clinica.py`, `scripts/v7_workflows_herramientas.py`, `scripts/build_v7_workflows.py`, `docs/plan-conexion-v7-celular-lucas-2026-10-06.md`.
- **No se tocan:** el v6 (`O155MqHgOSaNZ9ye`), Recordatorios (`7RqTApkvVavRmq3R`), `chequeo_salida.js` (solo se ajustan los casos), el cerebro actual (queda como respaldo).

---

## 8. Cambios por la crítica (construido el 08/10, sin desplegar)

Se incorporaron las dos críticas (la de alcance de Lucas y la técnica). Donde §1-§7 dicen otra cosa, **vale esta sección**.

### 8.1 Cambio de fondo: orquestador = UNA llamada + despacho por código

El ORQUESTADOR sigue siendo la IA que entiende al paciente y elige agentes (orden de Lucas), pero es **una sola llamada al modelo con salida JSON** (`{"pasos":[{"a":"turnos","pedido":"…"}, …]}`), nodo *Basic LLM Chain*, sin herramientas. El **código despacha** (nodo "Despacho"). Esto resuelve la latencia (crítica técnica B5: sin la 2.ª vuelta del orquestador), las llamadas repetidas (B6: una llamada por sub-agente y por mensaje, impuesta por código), que el orquestador redacte (texto libre → se descarta y sale el texto honesto + `[ACCIÓN]`) y permite probar el despacho **offline**. Ninguna regex lee el mensaje del paciente.

Cerebro (`scripts/v7_workflow_cerebro.py` → `v7/workflows/cerebro.json`, 42 nodos):
lecturas → Armar contexto → **Orquestador** → Despacho → ¿no entendí? (contador) → Turnos → Pagos → Información → Ver urgencia → Urgencias → **Reunir** (derivar / humano) → Derivar a secretaria → Pasar a humano → lecturas Redis → **Salida** (componer + chequeo + avisos + memoria) → hechos / propuesta enviada / memoria → Devolver.
Lógica en `v7/orquestador_core.js` (probada en `tests/test_orquestador_core.mjs`).

Sub-agentes (`scripts/v7_workflows_ma.py`): `v7 Agente Turnos`, `v7 Agente Pagos`, `v7 Agente Informacion`, `v7 Agente Urgencias`. Turnos, Pagos y Urgencias devuelven **un código** (no redactan); el texto lo arma el código con lo que devolvieron sus herramientas. Información es el único que redacta (1-3 frases, lista cerrada de temas). Prompts: `v7/prompt_orquestador.md`, `v7/prompt_sub_{turnos,pagos,informacion,urgencias}.md` (todos < 2.500 caracteres).

### 8.2 Bloqueantes e importantes (crítica de Lucas)

| # | Arreglo construido |
|---|---|
| B1 menú | El menú enumera solo lo que hacemos y cierra con "Escriba el número de la opción o lo que necesita." (`OrquestadorCore.MENU`). El del panel sale tal cual **solo si** no trae cuotas/dólares ni "¿en qué puedo ayudarle?" (regex sobre texto NUESTRO); el `MENU_DEFAULT` actual del panel no pasa → va el del código. Orquestador: "si el último mensaje de ASIRI es el menú y contesta con un número, es esa opción". **Pendiente panel**: validar al guardar y cambiar `MENU_DEFAULT` (`scripts/directrices_def.py` + panel). |
| B2 Información | Lista cerrada de temas; todo lo demás `FUERA_DE_ALCANCE` aunque esté en los DATOS o en las notas; las notas del panel entran como "cambian el tono, nunca agregan temas"; se borró "Lo esperamos…". Juez con rúbrica cerrada: pendiente (batería con modelo real). |
| B3 el "sí" | Turnos decide `confirma` **solo con el MENSAJE ACTUAL**; el orquestador escribe "responde a la confirmación pendiente" y tiene prohibido decidir si acepta. **Ruteo por estado**: si hay una confirmación guardada, vigente y que el paciente VIO, el código siempre manda el mensaje a Turnos (aunque el orquestador diga `no_reply`). `agenda_core.decidir` ejecuta solo con `confirma=true` + propuesta pendiente + read-back visto + TTL (+ candado al ejecutar); se borraron el reconocedor de afirmaciones, el "sí directo" y el **segundo camino** que ejecutaba sin propuesta guardada. |
| B4 regex del v6 | Ver 8.4. Segunda capa de urgencias del v7 = (b): cualquier sub-agente puede devolver `URGENCIA` y el código llama a Urgencias aunque el orquestador no lo haya hecho (test Z9, caso Mariela). La capa (a) (clasificador corto en paralelo) queda **para decidir Lucas**. Si Urgencias no deriva: frase fija + `[ACCIÓN URGENTE]`; si dice que no es urgencia: se deriva a la secretaria (nadie queda sin respuesta). |
| B5 fotos/audios | Orquestador: imagen sin texto → pagos solo si hay un pago en curso en el historial, si no `derivar_secretaria`; audio → `pedir_texto` (frase fija). Faltan los casos en la batería con modelo real. |
| B6 Turnos escribe fechas | Turnos no escribe: devuelve `PREGUNTA_PARA_QUIEN` / `PREGUNTA_DATOS_NUEVO` / `PREGUNTA_CUAL_TURNO` / `MOSTRAR_TURNOS` y el código arma el texto (lista de turnos incluida). |
| I1 "pal jueves" | Prompt: día puntual → `desde = hasta`; si no hay, otra búsqueda sin `hasta`; el código dice "En esa fecha no hay turnos disponibles." + el bloque siguiente. |
| I2 cita jujeña | `humano` valida la cita por mayoría de palabras contra el texto crudo; si no valida, deriva (aviso, no silencia). |
| I3 DNI | `decidir` compara solo dígitos de los dos lados contra los mensajes del paciente de 12 h (los mismos de "Armar contexto", respeta `historial_json`); si no está, pide el DNI con texto fijo. Ya no se pisa el DNI con una regex sobre el texto. |
| I4 STAFF | Orquestador: si le contesta al STAFF sin pedirnos nada → `no_reply`. |
| I6 urgencias | Urgencias limitada a boca, dientes, encías o aparato. |
| I8 | `no_entendi` ya no ofrece "una urgencia". |
| M1 | La presentación no sale si la respuesta es silencio (urgencia) ni con el menú. |
| M2 | Un `FUERA_DE_ALCANCE` → derivar por código, una vez (sin segunda vuelta del modelo). |

### 8.3 Bloqueantes (crítica técnica)

| # | Arreglo construido |
|---|---|
| B1 urgencia + escritura | Se mantiene U3: con escritura ok responde el texto de la escritura y la urgencia va como `[ACCIÓN URGENTE]`; silencio solo sin escrituras (tests Z8 / C7). |
| B2 chequeo sobre el compuesto | `chequeo_salida` corre sobre la parte de **Turnos** (contra libro, propuesta, ofertas); en Información solo cuentan las afirmaciones falsas. Orden: Información → Pagos (+ datos bancarios dentro de su parte) → derivación → Turnos (read-back al final). Reserva + datos no se duplican (C14/C15). |
| B3 el "sí" | Ver 8.2 B3. Batería de punta a punta (orquestador + Turnos con negativos "ok lo pienso", "ya, pero mejor el martes", "si, a q hora era?"): pendiente, con modelo real. |
| B4 dos capas | Ver 8.2 B4. La medición (muchas más urgencias, indirectas) queda en la batería pendiente. |
| B5 latencia | Orquestador de una llamada + despacho por código. Turnos ≥ 2 llamadas (herramienta + cierre con código). Medir p50/p95 de punta a punta (webhook → envío, con y sin buffer) en sombra. |
| B6 varias llamadas | Una llamada por sub-agente y por mensaje (pedidos repetidos se unen); una sola propuesta pendiente. Los sub-agentes corren **en cadena** (secuencial), no en paralelo. |
| B7 sub-agente cae | "Salida" lee primero el libro `escrituras:{tel}:{exec}`: si hubo escritura ok y Turnos se cayó, sale el texto de éxito (Z17 / C8). Agentes con `onError: continueRegularOutput` y sub-workflows con `continueOnFail`. |
| No bloqueantes | (1) la respuesta sale del texto de las herramientas, nunca de la paráfrasis; (2) Pagos y Urgencias quedan como sub-agentes (orden de Lucas) pero solo eligen herramienta y devuelven un código; la cita del triaje la pone el código con el mensaje completo; (3) Pagos sin DATOS, ningún prompt ve alias/CBU (test A12); (4) sin la oferta fija de Información cuando participó Turnos; (5) contadores propios `noentendi:` y `deriva:` (con `v7s:` en sombra), separados de `avisos:`; (6) en sombra `derivar`/`humano` no llaman al webhook (no silencian el chat real; K14/K18, Z19); (7) test estructural: ninguna herramienta de un sub-agente usa su propio `$execution.id` (A3); (8) DNI contra las filas de "Armar contexto"; (9) memoria con `source: 'asiri_v7'` (**pendiente panel**: sumarlo a `SOURCES_DEL_BOT` en `lib/media-entrantes.ts`; verificar que el filtro fromMe del v6 no tome el eco como humano); (13) suite Z/U/S portada al cerebro nuevo (`tests/test_v7_cerebro.py`); (14) el control "Te esperamos/venite" es sobre prompts NUESTROS; el riesgo aceptado el 07/10 (sin banlist) queda solo en Información, el único que redacta. |

### 8.4 Regex que quedan (ninguna decide la intención del paciente en el v7)

| Dónde | Qué hace | Por qué queda |
|---|---|---|
| `chequeo_salida.js` | Busca afirmaciones "quedó hecho" y fechas/horas en textos NUESTROS | Verifica contra la agenda real; falla del lado seguro (texto honesto). |
| `orquestador_core.menuValido` | Lee el menú del PANEL (cuotas, dólares, pregunta abierta) | Texto nuestro; si duda, va el menú del código. |
| `orquestador_core.codigo` / `salidaInformacion` | Lee la salida del MODELO (códigos, marcas) | Texto del modelo, no del paciente; lo desconocido se descarta. |
| `clinica_core.citaEnTexto`, `agenda_core.dniEnMensajes` | Compara la cita / los dígitos del DNI con lo que escribió el paciente | Validación de un DATO (anti-alucinación), no de intención; si falla, deriva o pide el dato (lado seguro). |
| `normHora`, `parseBloque`, `evaluarConfirmacion`, parseo KB 24 | Parseo de datos propios / de Dentalink | No juzgan al paciente. |
| **v6, antes del fork** (`Pre-filtro Cierre`, `Gate Canned Directo` / `Es Canned Directo?`, `Es cierre?`, `Triaje: ¿Seguimiento?`, `Triaje: Evaluar` con `gateRedFlags`) | Juzgan intención por regex | **No se tocaron** (regla: no tocar el v6). Plan: mover el fork "V7: ¿Vivo?" antes de `Pre-filtro Cierre` **y** de `Es cierre?` (backup, diff, `check_triaje.py`, OK de Lucas). `Triaje: Evaluar` corre regex + LLM: si concluye "no es urgencia" después de que el v7 se calló, hoy el paciente puede quedar sin respuesta → definir con Lucas. |
| **v6, después del fork** (`Gate Pago Tratamiento`, `Gate Humano Final`) | Pueden reemplazar o frenar la respuesta | Verificar en el JSON vivo qué hacen con `_flow:'v7'` antes de conectar (pendiente). |

### 8.5 Archivos

- **Nuevos:** `v7/orquestador_core.js`, `v7/prompt_sub_{turnos,pagos,informacion,urgencias}.md`, `v7/workflows/agente_{pagos,informacion,urgencias}.json`, `tests/test_orquestador_core.mjs`.
- **Reescritos:** `scripts/v7_workflow_cerebro.py`, `scripts/v7_workflows_ma.py`, `scripts/v7_workflow_clinica.py`, `v7/clinica_core.js`, `v7/prompt_orquestador.md`, `tests/test_v7_cerebro.py`, `tests/test_v7_ma.py`.
- **Cambiados:** `v7/agenda_core.js` (decidir con `confirma`, DNI por dígitos), `v7/historial_core.js` (sin regex de cierre/saludo; contexto con conversación nueva y confirmación pendiente), `scripts/v7_workflows_herramientas.py` (gestionar_turno: `confirma`, `textos_paciente`), `scripts/v7_lib.py` (`Grafo.cadena`), `scripts/build_v7_workflows.py`, `scripts/crear_v7_en_n8n.py`, `v7/ids.json` (placeholders `PENDIENTE_crear_v7_en_n8n` para los 3 sub-agentes nuevos: los crea `crear_v7_en_n8n.py --aplicar`), `tests/harness_grafo.mjs` (respuesta simulada por nodo y *LLM Chain*), `tests/test_agenda_core.mjs`, `tests/test_historial_clinica_core.mjs`, `tests/test_v7_grafo_herramientas.py`.
- **Retirados (a `v7/_retirados/`, nada borrado):** cerebro de agente único y su suite, `cerebro_ma`, `cerebro_mixto`, `cerebro_min`, `agente_clinica`, `prompt_asiri.md`, `prompt_agente_*.md`, `prompt_orquestador_mixto.md`. En n8n siguen existiendo (el script nunca borra).

### 8.6 Pendiente de Lucas

1. Desplegar: `python scripts/crear_v7_en_n8n.py --aplicar` (crea inactivos Pagos/Información/Urgencias y actualiza Turnos y el Cerebro por nombre).
2. Batería de ruteo con el modelo real (`tests/ruteo_orquestador.py`, no construida): de punta a punta (orquestador + Turnos) con negativos del "sí", fotos, audios, "ola kiero turno pal jueves", "ya le gire lo d la consulta", urgencias indirectas y falsos positivos; juez con rúbrica cerrada (I7).
3. R1 / B4: ¿capa (a) clasificador de urgencia en paralelo? ¿Qué pasa si el triaje del v6 concluye "no es urgencia" después de que el v7 se calló?
4. I5: con "me duele y quiero cambiar el turno" hoy solo responde el triaje (lo demás va como FYI al grupo). ¿Queda así?
5. Queja y baja de datos pasan a fuera de alcance (derivar): reemplaza lo decidido el 07/10.
6. Mover el fork del v7 antes de `Pre-filtro Cierre` y `Es cierre?` en el v6 (backup/diff/OK) y revisar `Gate Pago Tratamiento` / `Gate Humano Final` con `_flow:'v7'`; autorespuestas de otros bots (punto 10) y candado por teléfono (punto 11).
7. Panel: `asiri_v7` en `SOURCES_DEL_BOT`, validación del menú y nuevo `MENU_DEFAULT`.
