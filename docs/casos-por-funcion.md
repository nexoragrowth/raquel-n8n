# Mapa de casos por función — datos reales del consultorio (18/07 → 05/10/2026)

Objetivo del bot: **completar la acción** (agendar, confirmar, reprogramar, cobrar la seña, informar) y no derivar a una persona
cuando el paciente ya está listo para cerrar. Este documento es la base de las pruebas: cada caso sale de frases reales y dice qué
tiene que pasar para que el paciente avance.

> Los datos crudos (conversaciones con nombres) NO están en el repo: viven en `data/conversaciones/` (ignorado por git). Se regeneran con
> `python scripts/exportar_conversaciones_periodos.py` y `python scripts/analizar_conversaciones_por_funcion.py`.

## 1. La foto real (90 días, 1.516 mensajes de pacientes, 302 conversaciones)

Quién le contestó **primero** a cada mensaje del paciente. Ojo: mezcla etapas del bot y chats en modo humano; mide cuánto del tráfico
resuelve hoy el bot, no si lo resuelve bien.

| Función | Mensajes | Contestó el bot | Contestó una persona | Espera mediana de la persona |
|---|---|---|---|---|
| Confirma un recordatorio | 147 | **95%** | 5% | — |
| Urgencia | 48 | 83% | 17% | 36 min |
| Precio / forma de pago | 69 | 65% | 33% | 4 min |
| Cancela / reprograma | 63 | 65% | 35% | 8 min |
| Agenda / elige horario | 222 | 55% | 43% | 6 min |
| Saludo / pide información | 232 | 50% | 42% | 51 min |
| Comprobante de pago | 88 | 40% | 59% | 60 min |
| Imagen, documento o audio | 166 | **18%** | 68% | **19 horas** |
| Otros (seguimientos sueltos, proveedores, links) | 423 | 34% | 56% | 53 min |

Totales de lo que se escribió en 90 días: pacientes 1.516 · bot 756 · personas del consultorio 6.410. Para cada mensaje de paciente: 41% lo
contestó el bot en menos de 5 minutos, 32% una persona después de 5 minutos o más, 18% una persona en menos de 5, 4% nadie.

**Dónde se pierde conversión (por volumen × demora):**
1. **Imágenes, documentos y audios** (166): casi todo lo atiende una persona y tarda horas. Son radiografías, estudios, presupuestos y comprobantes.
2. **Comprobantes de pago** (88): una hora de mediana; es plata esperando.
3. **Saludo / pide información** (232): la mitad espera a una persona 51 minutos; es el lead del anuncio.
4. **Agendar** (222): 43% lo cierra una persona.
5. Familias: 12 conversaciones recibieron 2 o más recordatorios casi juntos (hermanos con un solo celular).

**Lo que ya funciona:** confirmar tras el recordatorio (95%, frases como «confirmo», «confirmado», «buen día, sí confirmo», 👍).

## 2. Cómo leer los casos

`Normal` = lo que pasa todos los días y tiene que salir perfecto en segundos. `Borde` = real pero menos frecuente: es donde el bot suele
derivar o quedarse mudo.
**Contexto a sembrar** = lo que tiene que haber en la memoria antes del mensaje. **Esperado** = lo que hace avanzar al paciente.
**Nunca** = lo que no puede pasar (banlist y reglas de la Dra.). Los casos de agenda necesitan horarios que existan hoy en Dentalink
(se piden en el momento a la herramienta de horarios, o se simula Dentalink): un horario inventado da un falso positivo.

## 3. Catálogo

### CONF — Confirmar después del recordatorio
| ID | Tipo | El paciente dice (real) | Contexto a sembrar | Esperado | Nunca |
|---|---|---|---|---|---|
| CONF-01 | Normal | «Confirmo», «Confirmado», «Buen día, confirmo», «Sí voy», 👍 | Recordatorio de 1 turno | Confirma el turno en la agenda y responde con día y hora. Marca el recordatorio. | Pedir datos, derivar, quedar mudo |
| CONF-02 | Normal | «Buen día, sí asistirá» (habla un familiar) | Recordatorio de 1 turno | Igual que CONF-01 | Preguntar quién es |
| CONF-03 | Borde | «Confirmo» con 2 recordatorios seguidos (hermanos) | 2 recordatorios, mismo celular | Confirma los dos y los nombra. *(decisión de la Dra.: si no aclara, ¿ambos?)* | Confirmar solo uno sin avisar |
| CONF-04 | Borde | «Confirmo el de la nena, el otro no puede» | 2 recordatorios | Confirma uno, ofrece reprogramar el otro | Confirmar los dos |
| CONF-05 | Borde | «Confirmo, llego 10 minutos tarde» | Recordatorio | Confirma y acusa el aviso | Derivar por el comentario |
| CONF-06 | Borde | «Confirmo, ¿puedo abonar ese día?» | Recordatorio | Confirma y responde la forma de pago | Responder solo una de las dos cosas |
| CONF-07 | Borde | «Confirmo» sobre un turno que ya estaba confirmado | Recordatorio + turno ya confirmado en la agenda | Responde que ya figura confirmado, sin error | Mostrar un error técnico |
| CONF-08 | Borde | «Confirmo» pero el turno fue cancelado en la agenda | Recordatorio viejo + turno anulado | No afirma nada falso; avisa que no figura y deriva con contexto | Decir «confirmado» sin turno |
| CONF-09 | Borde | «Buen día», «hola, ¿cómo andás?» (solo saluda) | Recordatorio | Saluda y pregunta si confirma | Mandar el menú completo |
| CONF-10 | Borde | «Confirmo» cuando el staff ya lo marcó confirmado | Turno confirmado a mano | Agradece y no vuelve a confirmar | Duplicar la confirmación |

### AGE — Agendar un turno nuevo
| ID | Tipo | El paciente dice (real) | Contexto | Esperado | Nunca |
|---|---|---|---|---|---|
| AGE-01 | Normal | «Quiero sacar un turno», «Necesito consulta para ortodoncia», «¿Hay lugar?» | — | Muestra el bloque de turnos (mañana y tarde) de una vez | Preguntar «¿mañana o tarde?» (regla de la Dra.) |
| AGE-02 | Normal | «El miércoles 30», «Martes 20 de octubre 8.40 hs», «A las 9 y 10», «el primero» | Bloque ofrecido con horarios reales | Read-back («Le confirmo: …») y pide lo que falte | Re-ofrecer lo mismo, quedar mudo |
| AGE-03 | Normal | «Sí», «Dale» tras el read-back | Read-back pendiente | Reserva y manda la pre-reserva con el alias (en mensajes separados) | Tratarlo como confirmación de recordatorio |
| AGE-04 | Normal | «Nombre Apellido DNI …» sin saludo | Bot pidió los datos | Crea la ficha y sigue con la reserva | Pedir los datos de nuevo |
| AGE-05 | Borde | «Solo puedo a las 17», «después de las 17 sí o sí» | — | Filtra o explica con honestidad qué hay (la Dra. atiende por la tarde solo lunes y miércoles) y propone algo concreto | Derivar a la primera |
| AGE-06 | Borde | «Solo jueves y por la tarde» | — | Dice qué jueves por la tarde hay o que no hay y ofrece la alternativa más cercana | Silencio |
| AGE-07 | Borde | «La semana que viene, cualquier día después de las 17» | — | Busca esa ventana | Ignorar la ventana |
| AGE-08 | Borde | «Quería un turno antes del que me toca» | Paciente con turno | Ofrece horarios anteriores | Decir que no se puede sin intentar |
| AGE-09 | Borde | Elige un horario que ya no está | Bloque viejo | «Ese horario ya no está disponible» + bloque nuevo | Reservar igual o fallar |
| AGE-10 | Borde | «Agendar un turno» con 2 fichas en el celular | Celular con 2 pacientes | Una sola pregunta: «¿Para quién agendo?» | Elegir una ficha por su cuenta |
| AGE-11 | Borde | «¿Puedo pagar el día de la consulta?» mientras agenda | Flujo de agenda abierto | Responde y retoma la agenda | Perder el hilo |
| AGE-12 | Borde | Ya tiene un turno cerca | Turno en ±7 días | Pregunta si cambia ese o suma otro | Reservar doble |
| AGE-13 | Borde | Menor de edad | — | Aclara una vez que debe ir con un adulto | Repetirlo en cada mensaje |
| AGE-14 | Borde | Sin horarios en 2 búsquedas | Agenda llena | Lo dice y deriva con el pedido resumido | Seguir buscando en bucle |

### REP — Cancelar y reprogramar (retener al paciente)
| ID | Tipo | El paciente dice (real) | Contexto | Esperado | Nunca |
|---|---|---|---|---|---|
| REP-01 | Normal | «Necesito cancelar mi turno de hoy», «No voy a poder ir» | Turno activo | Read-back, cancela, ofrece reprogramar | Cancelar sin confirmación |
| REP-02 | Normal | «¿Se puede pasar para otro día?», «¿Qué posibilidad hay de cambiarlo a la tarde?» | Turno activo | Busca horarios y los ofrece (no responde «sí» a secas) | `[NO_REPLY]` (caso real de la paciente que quedó en visto) |
| REP-03 | Normal | «Podría reprogramar para otra fecha» tras un recordatorio | Recordatorio | Ofrece bloque de horarios | Tratarlo como confirmación |
| REP-04 | Borde | «Por la mañana no puedo» | Bloque ofrecido | Muestra solo los de la tarde del bloque | Ofrecer los mismos |
| REP-05 | Borde | «No podré asistir» (no pide nada) | Turno activo | Pregunta una vez si lo reprogramamos | Cancelar sin preguntar |
| REP-06 | Borde | Reprograma con 2 fichas en el celular | 2 turnos | «¿De quién es?» | Elegir uno |
| REP-07 | Borde | Cambio para hoy o mañana | Turno próximo | Comunica la política de 48 hs sin sermón y resuelve o deriva | Prometer lo que no puede |
| REP-08 | Borde | «Quiero cancelar» sin turno activo | Sin turnos | No inventa; deriva con contexto | Decir que canceló |
| REP-09 | Borde | «Mil gracias por cambiarlo, disculpe» | Reprogramación hecha | Cierre breve o silencio | Reabrir el menú |
| REP-10 | Borde | Una urgencia con «¿puedo pasar mañana?» | Síntoma + ventana | **Urgencia** (triaje), no reprogramar | Mandarlo al flujo de cancelar |

### PAG — Pagos y comprobantes
| ID | Tipo | El paciente dice | Contexto | Esperado | Nunca |
|---|---|---|---|---|---|
| PAG-01 | Normal | Foto del comprobante de transferencia | Pre-reserva con alias enviado | Acusa recibo y avisa a la secretaria; deja el turno como pendiente de verificación | Decir que el pago ingresó o validar el monto |
| PAG-02 | Normal | «¿A qué alias transfiero?» | — | Alias y titular (y datos de cuenta si los pide) | Olvidar uno de los dos datos |
| PAG-03 | Normal | «¿Cuánto sale la consulta?» | — | Valor vigente de la base, y empuja a agendar | Precio de tratamientos |
| PAG-04 | Borde | «Ya transferí» sin imagen | Pre-reserva | Pide el comprobante y avisa a la secretaria | Confirmar por esa frase |
| PAG-05 | Borde | Comprobante de $70.000 (cuota) | Paciente en tratamiento | Acusa recibo sin validar | Decir si el monto es el correcto |
| PAG-06 | Borde | Imagen que no es comprobante (radiografía, estudio, anuncio) | — | No la llama comprobante: acusa recibo y deriva | Tratarla como pago |
| PAG-07 | Borde | «¿Puedo abonar el día de la consulta?» | — | Texto de la Dra. (pago después del recordatorio, efectivo o transferencia) | Respuesta genérica de alias |
| PAG-08 | Borde | «¿Aceptan tarjeta?» | — | Transferencia o efectivo | Inventar otras formas |
| PAG-09 | Borde | Obra social, factura, reintegro | — | Regla única (hoy el prompt y la documentación se contradicen) | Contestar distinto cada vez |
| PAG-10 | Borde | Comprobante un domingo a la noche | Pre-reserva | Acusa igual; el aviso queda para el horario hábil | Silencio |

### URG — Urgencias
| ID | Tipo | El paciente dice | Esperado | Nunca |
|---|---|---|---|---|
| URG-01 | Normal | «Se me salió el bracket», «me pincha el alambre» | Triaje con video y aviso de consultorio privado sin guardia | «Venite», dirección como invitación |
| URG-02 | Borde | «Está incómoda y no come» (sin palabra clave) | Triaje / derivación | Mandarlo a consulta general (incidente de mayo) |
| URG-03 | Borde | Golpe, sangrado fuerte, hinchazón, fiebre | Deriva sin video | Intentar resolver con un video |
| URG-04 | Borde | Solo una foto | Triaje o derivación | Silencio |
| URG-05 | Borde | Sábado o domingo | Aclara que no hay guardia 24 hs y avisa a la Dra. | Invitar a ir |
| URG-06 | Borde | «Puedo pasar mañana» + síntoma | Triaje (ver REP-10) | Reprogramar |

### GEN — Consultas generales y anuncio
| ID | Tipo | El paciente dice | Esperado | Nunca |
|---|---|---|---|---|
| GEN-01 | Normal | «Hola», «Buenas tardes» (conversación nueva) | Menú de bienvenida (texto editable en el panel) | Derivar un saludo |
| GEN-02 | Normal | «¡Hola! Quiero más información» (anuncio) y variantes («hola más info») | Texto de la Dra. de la base de conocimiento, tal cual | Reescribirlo, mandar otro texto |
| GEN-03 | Normal | «2», «la 3», «opción 4» tras el menú | Sigue esa opción | Preguntar qué quiso decir |
| GEN-04 | Normal | «¿Dónde queda?», «¿Qué horarios tienen?» | Dirección y horarios de la base | Bloquear por la dirección |
| GEN-05 | Normal | Tratamientos, duración, blanqueamiento | Foco en ortodoncia + empuja a la consulta | Inventar tratamientos |
| GEN-06 | Normal | «Gracias», «Listo, muchas gracias, impecable» | Silencio (`[NO_REPLY]`) | «¿Desea agendar un turno?» (pasa hoy) |
| GEN-07 | Borde | «Estoy llegando», «ya llegué» | Silencio o respuesta mínima (pedido de la Dra.) | Menú |
| GEN-08 | Borde | «Quiero hablar con una persona» | Deriva de inmediato (único caso legítimo) | Insistir |
| GEN-09 | Borde | Mensajes de proveedores, laboratorios, links, contactos | No responde (no es un paciente) | Contestar como a un paciente |
| GEN-10 | Borde | Pregunta + pedido en el mismo mensaje | Responde las dos cosas | Contestar solo una |

### ADJ — Imágenes, documentos y audios
| ID | Tipo | Qué manda | Esperado | Nunca |
|---|---|---|---|---|
| ADJ-01 | Normal | Radiografía o estudio | Acusa recibo («la Dra. lo revisa») y avisa al grupo con el archivo | Opinar sobre la imagen |
| ADJ-02 | Normal | Audio | Lo transcribe y lo trata como texto | Ignorarlo |
| ADJ-03 | Borde | PDF de presupuesto o documento | Acusa recibo y deriva | Silencio |
| ADJ-04 | Borde | Contacto compartido o ubicación | Responde lo mínimo o deriva | Menú |

## 4. Reglas de conversión (cuándo NO derivar)

El bot no se pasa a modo humano ni se calla cuando el paciente:
1. confirma, elige un horario ofrecido, responde «sí/dale» a un read-back, manda un comprobante o pide reprogramar;
2. hace una pregunta que está en la base de conocimiento;
3. escribe con errores o con dos pedidos juntos.

Deriva a una persona solo cuando: hay una urgencia, pide hablar con una persona, manda algo clínico (foto, estudio), pasa algo que el bot no puede
verificar (turno que no figura, pago a validar) o falló dos veces en lo mismo. Al derivar, el aviso al grupo lleva el pedido resumido.

## 5. Cómo se convierte en pruebas

Cada fila es un caso: *mensaje + contexto sembrado + qué se espera + qué nunca*. Para que sirvan:
- **Medir lo que sale por WhatsApp**, no solo lo que el bot genera.
- **Correr cada caso varias veces** (el modelo no es determinístico) y mostrar el porcentaje.
- **Sembrar horarios reales** o simular la agenda.
- **Usar un teléfono de prueba reservado** y no mandar WhatsApp reales (modo prueba).
- **Casos nuevos desde conversaciones reales:** el panel puede armar un caso a partir de una charla y la Dra. aprueba qué debía contestarse.

*Limitaciones de esta foto:* la clasificación de funciones es por palabras clave y contexto (aproximada); el historial empieza el 18/07;
una parte de las respuestas «de una persona» del flujo de cancelar eran del bot (ver backlog: el sub-flujo las guarda con la marca del staff) y se
reclasificaron por su voz, pudiendo quedar alguna sin detectar.
