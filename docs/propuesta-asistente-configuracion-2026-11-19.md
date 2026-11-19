# Propuesta: Asistente de configuración para la clínica (chat de IA en el panel) + "Días sin atención"

Versión 2 · 19/11/2026 (ampliada por pedido de Lucas: autónomo, conversacional de punta a punta, precios con propagación, experiencia premium) · Para decidir: Lucas · Estado: **propuesta, nada de esto está desplegado**.
Pendiente de integrar: el análisis de plataforma, costos y diseños alternativos que está corriendo en segundo plano (secciones 7.3, 8 y 10 se ajustan con sus números).

---

## 1. Resumen (lo que hay que decidir, en 10 líneas)

- **Problema:** cada vez que pasa algo habitual (un feriado, vacaciones, adelantar avisos, apagar algo), la clínica le pregunta a Lucas o hay que sentarse con Claude a mirar código. En febrero de 2027 termina el soporte y esa persona deja de estar.
- **Propuesta:** un **chat dentro del panel** donde la secretaria o la doctora escriben lo que necesitan ("el lunes 23 es feriado, que los del martes se avisen el jueves"). El chat **propone** con una vista previa clara. Según el riesgo, lo reversible se hace **solo y con Deshacer**, y lo que cambia lo que ven los pacientes o compromete a la clínica (un precio, apagar el bot) pide un clic de confirmación. El **modelo** nunca escribe nada: ejecuta el código del panel, que valida todo.
- **Base:** cada cosa configurable es una **acción del panel con validaciones y vista previa**. El chat es una capa fina que llama a esas mismas acciones. Si el chat falla o se queda sin crédito, las pantallas siguen funcionando.
- **Alcance (versión 2):** se maneja conversando todo lo configurable: avisos y calendario, **precios y conocimiento** (un solo dato que se propaga a todos los textos), cómo habla Asiri, interruptores, atención, salud del sistema y agenda (mapa en la sección 4 bis). **Autonomía por niveles de riesgo** (sección 4 ter) y un asistente **proactivo**.
- **Primer módulo:** "Días sin atención" (calendario de feriados, puentes y vacaciones). Con eso el caso del 23/11 se resuelve una vez y queda programado: el jueves avisa solo el martes.
- **Segundo módulo:** **lista de precios única**: hoy el precio está repetido en 9 textos, una constante fija y varios respaldos; se unifica primero y después "che, la consulta pasa a 60 mil" cambia un solo dato y se ve todo lo que cambia antes de confirmar.
- **Después, por orden de riesgo:** consultas y proactividad, acciones simples, precios e interruptores con rol de doctora, agenda, y recién al final un agente que detecta y diagnostica fallas.
- **Lo que NO hace en esta propuesta:** cambiar código, prompts o workflows; hablar con pacientes; desplegar.
- **Recomendación de arranque:** Fase 1 (Días sin atención) esta semana, después Fase 2 (lista de precios única) y Fase 3 (chat de consultas y proactividad). Hasta tener el chat completo de configuración: 20–25 días de trabajo, 5–6 semanas de calendario; quedan ~10 hasta febrero.

---

## 1 bis. Qué cambió en la versión 2 (pedidos de Lucas del 19/11)

| Pedido | Cómo lo recoge esta versión |
|---|---|
| "No solo feriados: *che, cambiá el precio a 60 mil* y que se cambie en todos lados, uniformado en uno solo" | Sección 4 quater: hoy el precio está repetido en **9 textos del conocimiento, una constante fija del workflow de avisos y varios valores de respaldo del v6**. Primero se unifica en una **lista de precios única** y después el chat cambia un solo dato y muestra todo lo que cambia |
| "Que se vea el cambio interactivamente, experiencia premium y robusta" | Sección 7.1: tarjetas con **antes → después**, "así lo va a leer el paciente" y **"probar con Asiri"** antes de confirmar; línea de tiempo con Deshacer; validaciones por código |
| "Bien autónomo" | Sección 4 ter: **cuatro niveles de autonomía** según riesgo. Lo reversible y sin efecto directo en pacientes lo hace solo y avisa (con Deshacer); el asistente además es **proactivo** |
| "Que se pueda manejar el agente y el sistema de forma conversacional" | Sección 4 bis: mapa completo (avisos, precios y conocimiento, cómo habla Asiri, interruptores, atención, salud del sistema, agenda) |

"Autónomo" no significa "sin frenos": significa que **el freno es proporcional al riesgo**. Eso es lo que se propone decidir en D5.

---

## 2. Por qué ahora (evidencia)

| Hecho | Qué muestra |
|---|---|
| 18/11: la clínica pregunta si "mañana jueves" salen los avisos del martes 24 porque el lunes es feriado | El sistema cuenta "2 días hábiles lunes a viernes" y **no sabe de feriados**. Nadie en la clínica sabía qué hacer |
| El panel ya tenía "Adelantar" y "Suspender un día" | Existen, nadie los conocía, y **tienen una trampa**: si se adelanta y después sale igual el aviso automático, el que no contestó recibe el mensaje dos veces |
| 17/11: los avisos salieron a las 09:00 en vez de las 08:00 y la secretaria mandó a mano; varios pacientes recibieron doble mensaje | Cuando algo parece raro, la clínica improvisa por su cuenta |
| 13/11: Asiri confirmó turnos que nadie pidió | Resolverlo requirió investigar, escribir código, probar, desplegar y revisar: eso **no** lo puede hacer la clínica (es el nivel 2, ver sección 5) |
| Febrero 2027 | Termina el soporte: toda consulta a Lucas es una deuda |

Pendiente del análisis: cuántos de los incidentes del último año eran de configuración (los resuelve el nivel 1) y cuántos de código (nivel 2).

---

## 3. Objetivos y no-objetivos

**Objetivos**
1. La clínica resuelve sola lo habitual, en lenguaje natural o con pantallas simples, sin conocimiento técnico.
2. **Cero riesgo de decirle algo equivocado o peligroso a un paciente** (lección del incidente del 09/05).
3. Todo cambio es **visible antes, auditable después y reversible** cuando se puede.
4. Sirve para revender el panel a otras clínicas (la configuración vive en el panel, no en la cabeza de una persona).
5. Si el modelo de IA no está disponible, **nada deja de funcionar**: queda el camino manual.

**No-objetivos de esta propuesta**
- Que el chat cambie código, prompts del bot, workflows de n8n o credenciales.
- Que el chat escriba o le conteste a pacientes.
- Decisiones clínicas, de precios de tratamiento o de pagos.
- Ediciones masivas en Dentalink.
- Reemplazar a una persona técnica para fallas de fondo (eso se discute en el nivel 2).

---

## 4. Usuarios y casos de uso

Usuarios: **secretaria** (Irina y la próxima), **doctora**, **administrador técnico** (Lucas).

### Nivel 1 — configuración y consultas (alcance de esta propuesta)

| Pedido en lenguaje natural | Qué ejecuta el sistema (acción existente o nueva) | Quién | Riesgo |
|---|---|---|---|
| "El lunes 23 es feriado" / "cerramos del 28/12 al 8/1" | Cerrar días (Días sin atención) | secretaria | bajo, reversible |
| "Hoy no mandes avisos" / "mañana tampoco" | Suspender un día (existe) | secretaria | bajo, reversible |
| "Mandá ya los avisos del martes" | Adelantar avisos de una fecha (existe, mejorada: no se repite) | secretaria | **medio: sale un mensaje a pacientes, no se deshace** → vista previa con cantidad |
| "¿Qué avisos salen mañana?" / "¿cuántos turnos hay el martes?" / "¿corrió el aviso de hoy?" | Consultas de solo lectura | todos | ninguno |
| "Apagá el bot un rato" / "volvé a prenderlo" | Interruptor del bot (existe) | doctora/admin | medio, reversible |
| "Cambiá el texto de «no hay turnos»" | Mensajes fijos (existe, con validación) | doctora | medio, reversible (volver al estándar) |
| "Agregá una respuesta sobre estacionamiento" | Conocimiento (existe) | doctora | medio, reversible |
| "Cambiá el precio de la consulta" | Conocimiento + guarda de precios (existe) | doctora | alto: es un compromiso con pacientes → confirmación reforzada |

Fuera del nivel 1 (hoy): cualquier cosa sin acción validada detrás. Si piden algo que no existe, el asistente lo dice claro y deja un **pedido registrado** para Lucas, en vez de improvisar.

### Nivel 2 — detectar, investigar y proponer arreglos (se diseña aparte, sección 5)

---

## 4 bis. Mapa completo: qué se maneja conversando

| Área | Lectura ("¿qué pasa con…?") | Acciones | Estado hoy |
|---|---|---|---|
| **Avisos y calendario** | próximos avisos, cuántos turnos por día, si corrió el de hoy | días sin atención, adelantar, suspender, horario de envío | panel parcial (Adelantar, Suspender) |
| **Precios y conocimiento** | dónde aparece un dato, qué dice Asiri sobre X | cambiar un precio (lista única), agregar/editar respuestas | panel: editor de conocimiento; precio repetido en 9 textos |
| **Cómo habla Asiri** | cómo contesta a una pregunta (probador) | tono, saludo, menú, mensajes fijos, notas de cada agente | panel: Tono y estilo, Mensajes fijos, "Probá cómo contesta" |
| **Interruptores** | si el bot, los avisos y el modo humano están prendidos | prender/apagar el bot, avisos, modo humano de un chat | panel y mensajes `/bot off` por WhatsApp |
| **Atención** | pacientes esperando, urgencias abiertas, casos sin tomar | tomar y resolver casos | panel: Atención |
| **Salud del sistema** | "¿anda todo?", "¿por qué no salió el aviso de X?" en lenguaje común | reparaciones seguras del catálogo existente (reconectar, reponer webhook) | Health Check y Vigía existentes; sin traducción a lenguaje común |
| **Agenda (Dentalink)** | huecos, turnos del día | agendar/anular con "cero doble trabajo" y un clic de confirmación | panel: Calendario con acciones |

El asistente es la **puerta única**: la misma pantalla de chat habla con todas las áreas. Cada área sigue teniendo su pantalla propia (el chat nunca es el único camino).

## 4 ter. Autonomía proporcional al riesgo

| Nivel | Qué es | Cómo actúa el asistente | Ejemplos |
|---|---|---|---|
| **A — lo hace solo y avisa** | Reversible, sin efecto directo en lo que reciben los pacientes | Ejecuta, muestra el resultado y deja **Deshacer** | cerrar/abrir un día sin atención, pausar avisos de un día, consultas, anotar un pedido |
| **B — vista previa y un clic** | Cambia lo que ven los pacientes, pero se puede volver atrás; o sale un mensaje que no se deshace | Tarjeta con **antes → después** y "así lo lee el paciente"; la persona confirma | mensajes fijos, textos de conocimiento, tono, saludo y menú, **adelantar avisos** (con cantidad) |
| **C — confirmación reforzada, rol doctora** | Compromisos con pacientes o efecto amplio | Tarjeta con todos los lugares afectados + prueba con Asiri + confirmación de doctora/admin | **precios**, apagar el bot, cambios que tocan varios textos, envíos a muchos pacientes |
| **D — nunca por chat** | Peligro alto o fuera de alcance | Lo explica y deja el pedido anotado para una persona técnica | prompts completos, código, workflows, credenciales, borrar historiales, ediciones masivas en Dentalink |

**Proactivo:** el asistente no espera a que le pregunten. Ejemplos: "El lunes 23 es feriado y todavía no está cerrado: ¿lo cerramos?" · "Hoy salieron 7 avisos; 1 paciente no tiene celular cargado." · "Hay 3 pacientes esperando respuesta hace más de 2 horas." Las sugerencias aparecen en el panel (y, si se decide, también en el grupo de WhatsApp que ya existe).

## 4 quater. El caso del precio ("che, cambiá la consulta a 60 mil")

**Dónde vive hoy el precio de la consulta** (relevado el 19/11, solo lectura):

| Lugar | Cómo está | Problema |
|---|---|---|
| Conocimiento (base del bot) | **9 entradas** con "$50.000" escrito en el texto (1, 21, 22, 33, 40, 41, 42, 43, 44) | Cambiar el precio = editar 9 textos a mano; se olvida alguno y Asiri se contradice |
| Workflow de avisos (en vivo) | constante fija `PRECIO_CONSULTA = "50.000"` | No lee la base: hay que cambiar código |
| Bot v6 de entrada | valores de respaldo fijos: consulta $50.000, **cuota $70.000**, **contención $50.000** | Otros precios también están repetidos |
| Bot v7 | lo lee de la base en cada mensaje | Está bien: se actualiza solo cuando cambia el texto fuente |
| Panel | guardas de precios y matching de pagos por monto | Hay que revisarlas al cambiar un valor |
| Dentalink (sistema externo) | el valor de la prestación | Los comprobantes de $60.000 no coincidirían con una prestación de $50.000 |

*(Las menciones de "$50.000" en el código del v7 son ejemplos en comentarios del detector de montos, no precios.)*

**Plan:** una **lista de precios única** (consulta, devolución, contención, cuota…) como fuente de verdad. Los textos usan marcadores (`{{precio_consulta}}`) y un solo resolver los reemplaza al leer. Los valores de respaldo dejan de ser números fijos: usan el último valor de la lista. Es una migración **de contenido** que revisa la doctora (se reescriben 9 textos) más un cambio chico en el bot v7, el v6 y el workflow de avisos.

**Cómo se ve conversando** (nivel C):
1. Doctora: *"Che, la consulta pasa a 60 mil."*
2. Asistente: *"La consulta hoy es $50.000. ¿La pasamos a $60.000?"* (si hubiera dos precios parecidos, pregunta cuál: consulta, devolución, contención, cuota).
3. Tarjeta: **$50.000 → $60.000.** Se actualiza en **9 textos** (se listan, con el antes→después de cada frase), en los avisos de turno y en la respuesta de pago. **"Así lo lee un paciente:"** burbujas de WhatsApp con el texto nuevo. **"Probar con Asiri:"** responde en vivo a "¿cuánto sale la consulta?" con el precio nuevo (en borrador, sin tocar nada). Aviso: *"En Dentalink la prestación sigue en $50.000; los comprobantes de $60.000 no van a coincidir hasta cambiarla."*
4. **[Confirmar]** (solo doctora/admin) → se cambia **un solo dato**, todo se actualiza, queda en el historial con **Deshacer**.
5. El asistente verifica después: vuelve a leer los textos resueltos y confirma "Listo: 9 de 9 textos muestran $60.000".

**Probado el 19/11 (solo sombra, sin tocar producción) — con los textos reales y con el modelo real:**
- **Hallazgo clave:** de las 10 menciones de "$50.000" en los 9 textos, **8 son la consulta y 2 son la devolución** (hoy valen lo mismo). Un reemplazo "por valor" las habría mezclado: el día que la consulta cambie, la devolución cambiaría sola. Por eso son **dos datos separados** (`precio_consulta`, `precio_devolucion`) y la migración **clasifica cada mención por contexto** (la pista más cercana antes del monto) y deja **para revisar** lo dudoso en vez de adivinar.
- **Clasificador contra los 9 textos reales** (`v7/datos_core.js`, `tests/test_datos_core.mjs` 55/55): 10 de 10 menciones bien atribuidas, **0 dudosas**, y la ida y vuelta es **idéntica** en los 9 textos (resolver con los valores de hoy devuelve el texto original). El test encontró un error mío de diseño (la palabra "diagnóstico" está en las dos descripciones, no sirve de pista) y quedó corregido.
- **Con el modelo real, en sombra** (clon temporal del cerebro en el espacio de pruebas apagado, restaurado y verificado idéntico al terminar; nada escrito en la base): con `precio_consulta = 60.000` y `precio_devolucion = 50.000`, "¿cuánto sale la primera consulta?" → **$60.000**; el mensaje de 3 pedidos (precio + alias + turnos) → **$60.000** y los datos de pago y horarios intactos; "¿y la devolución?" → **$50.000**. Un solo dato cambió y el otro no se movió.
- **Lo que NO prueba todavía:** el camino de los avisos de turno (workflow aparte, tiene el precio fijo en el código) ni el v6; eso es la Fase 2.
- **Hallazgo aparte (error del bot de hoy):** ante "quiero pagar la consulta, ¿cuánto transfiero y a dónde?", el especialista de Pagos **registra un "aviso de pago" que nadie hizo** y no dice el monto. En 9 días reales: 32 avisos registrados, **30 reales y 2 falsos** (una consulta de cómo pagar y una promesa de pago). Está en el backlog.

Sin esa migración previa, "cambiar el precio en todos lados" sería un reemplazo de texto sobre 9 entradas más código: frágil y fácil de dejar inconsistente. Por eso la lista de precios única va **antes** del chat de precios.

## 5. Los dos niveles y por qué se separan

| | **Nivel 1: asistente de configuración** | **Nivel 2: agente de diagnóstico y reparación** |
|---|---|---|
| Para qué | Que la clínica configure lo habitual | Que alguien detecte, investigue y arregle fallas cuando no hay Lucas |
| Cómo actúa | Llama **acciones validadas** del panel | Lee ejecuciones, conversaciones y documentación; propone arreglos |
| Escribe en producción | Solo vía acción validada + confirmación humana | **No en esta propuesta.** Propone; una persona técnica aprueba |
| Datos de pacientes | No los ve (solo cantidades) | Los necesita para investigar → requiere reglas de privacidad y contrato (SEG-17) |
| Riesgo | Bajo y acotado | Alto: el fallo del 13/11 vino de una regla escrita dentro del código que invitaba a confirmar; un agente que cambia cosas puede repetir ese tipo de error |
| Cuándo | Semanas 1–5 | Semanas 6–9, y **solo si el análisis confirma que vale la pena** |
| Quién lo apoya en febrero | La propia clínica | Hace falta una persona técnica (¿Lucas/Nexora de guardia?) → decisión de negocio (D9) |

El nivel 1 se puede construir **ya** sobre lo que existe y cubre lo que pidió la clínica. El nivel 2 es otro proyecto, con otra clase de riesgo, y conviene no mezclarlo con el primero.

---

## 6. Modelo de seguridad (los principios que no se negocian)

1. **El modelo propone; el código valida y decide cuánta autonomía corresponde.** El chat no tiene herramientas que escriban directamente: tiene herramientas `proponer_*` que devuelven una **propuesta con vista previa**. Según el **nivel de riesgo** (sección 4 ter) la acción corre sola con **Deshacer** (nivel A) o espera la confirmación de una persona (B y C). Toda ejecución es server-side, **vuelve a validar todo** y se registra. Una propuesta vence a los 10 minutos y se usa una sola vez. El nivel de cada acción lo fija el código, nunca el modelo.
2. **Mínimo privilegio.** Las herramientas del chat son exactamente las acciones del panel; no hay SQL libre, ni API de n8n, ni shell.
3. **Roles.** Hoy el panel solo distingue "administrador técnico" (`PANEL_ADMINS`) del resto. Se propone: **clínica** (secretaria: calendario, avisos, consultas), **doctora** (+ mensajes fijos, conocimiento, precios, apagar el bot) y **admin técnico** (Lucas). Requiere agregar un campo de rol (decisión D2).
4. **Vista previa honesta.** Cada propuesta muestra *qué va a pasar* en lenguaje común, con días de la semana y cantidades: "El lunes 23/11 queda cerrado. Los turnos del martes 24/11 (6) se avisan el jueves 19/11 a las 08:00". Nada de "¿seguro?" genérico: se confirma algo concreto.
5. **El modelo no interpreta fechas solo.** El modelo extrae la intención ("cerrar", "el lunes 23"); **una función determinista** valida la fecha (existe, no es pasada, día de semana correcto) y calcula el efecto. Si el pedido es ambiguo ("el lunes"), pregunta.
6. **Solo texto del personal y datos estructurados entran al modelo.** Lo que escribe un paciente nunca llega al asistente en esta propuesta → no hay vía de inyección de instrucciones desde pacientes. Los comentarios libres de Dentalink tampoco.
7. **Auditoría y deshacer.** Tabla `asistente_log`: quién, qué pidió, qué se propuso, qué se confirmó, resultado y cómo se deshace. Cerrar un día se deshace con un clic; adelantar avisos **no** se puede deshacer (los mensajes salen) y por eso lleva la vista previa más fuerte.
8. **Topes.** Máximo de días por acción, máximo de destinatarios por envío (sobre el tope: confirma una persona del nivel doctora), límite de mensajes por usuario por día y **tope de gasto mensual** de la API.
9. **Interruptor general.** Lucas puede apagar el asistente sin tocar el bot ni el resto del panel.
10. **Degradación segura.** Sin modelo o sin crédito: el chat muestra "no disponible, usá las pantallas" y todo lo demás sigue igual.

---

## 7. Diseño

### 7.1 Experiencia (mobile primero: la doctora lee desde el celular)

- **Pantalla "Asistente":** chat simple, con 4 ejemplos para empezar ("El lunes es feriado", "¿Qué avisos salen mañana?", "Pausá los avisos de hoy", "¿Corrió el aviso de hoy?").
- **Tarjeta de propuesta** dentro del chat, con el efecto en claro. En los niveles B y C lleva **Confirmar** y **Cancelar**; en el nivel A el asistente lo hace y muestra el resultado con **Deshacer**. Después de ejecutar, el chat muestra el resultado real ("Listo: el lunes 23/11 quedó cerrado").
- **Experiencia premium en lo que cambia textos y precios:** vista **antes → después** lado a lado, **"así lo lee el paciente"** (burbujas de WhatsApp con el texto ya resuelto), **"probar con Asiri"** (el probador real contesta a una pregunta de ejemplo con el cambio aplicado en borrador, sin tocar nada) y una **línea de tiempo de cambios** con Deshacer. Respuestas en streaming, tarjetas con la lista de todo lo afectado, dictado por voz y sin jerga técnica.
- **Robusta:** las fechas y los montos los valida código (no el modelo); cada cambio se registra y se verifica después ("9 de 9 textos muestran $60.000"); si falla el modelo o se acaba el crédito, las pantallas siguen funcionando.
- **Pantalla "Días sin atención"** (misma acción, sin chat): lista de días cerrados, feriados sugeridos con un toque ("¿Cerramos el lunes 23?") y el efecto escrito debajo de cada día. Es la fuente de verdad visible: el chat y la pantalla muestran lo mismo.
- **Qué va a pasar con los avisos:** una lista de las próximas 5 corridas ("Jue 19 → turnos del mar 24 · 6"), así la secretaria ve el sistema en vez de adivinarlo.
- **Si piden algo que no existe:** "Eso todavía no lo puedo hacer. Dejé el pedido anotado para Lucas."

### 7.2 Arquitectura

```
Secretaria ── chat ──► Panel (Next.js, VPS)
                         │  /api/asistente  (SDK "ai" + Claude, streaming)
                         │   herramientas de SOLO LECTURA ─► Supabase v3 / Dentalink (cantidades)
                         │   herramientas proponer_*      ─► guarda propuesta (vence a los 10 min)
                         ▼
                  [Confirmar]  ──► acción server-side (la misma de las pantallas)
                                      │ revalida · ejecuta · registra en asistente_log
                                      ▼
                  recordatorios_config.dias_cerrados  ──►  Workflow Recordatorios (n8n)
                                                            Gate + "Fecha Mañana" leen la lista
```

- El SDK de IA (`ai`, `@ai-sdk/anthropic`) **ya está instalado en el panel y hoy no se usa**.
- La clave de la API vive solo en el VPS (nueva variable), con tope de gasto configurado en la consola del proveedor.
- Cambios en el bot: **solo dos nodos** del workflow de Recordatorios (Gate y "Fecha Mañana"); con la lista vacía el comportamiento es idéntico al de hoy (probado en 2 años de fechas).
- Datos nuevos: columna `recordatorios_config.dias_cerrados` (aditiva) y tabla `asistente_log`. Más adelante `asistente_propuestas` y el campo de rol.

### 7.3 Costos y plataforma (a completar con el análisis)

Uso estimado del nivel 1: pocas conversaciones cortas por día. **Costo a confirmar con los precios vigentes de la API** (el análisis los está relevando). Se fija un tope mensual y un límite diario por usuario. Quién paga y a nombre de quién va la cuenta es la decisión D4.

### 7.4 Cómo se ve el caso del 23/11, paso a paso

1. Secretaria: *"El lunes 23 es feriado, que los del martes se avisen el jueves."*
2. El asistente (herramientas de lectura): mira la configuración y cuenta los turnos del 24/11.
3. El asistente (herramienta `proponer_cerrar_dias`): fecha `2026-11-23`, validada (lunes, futuro, no cerrado).
4. Tarjeta: *"Cierro el **lunes 23/11**. Los turnos del **martes 24/11 (6)** se avisan el **jueves 19/11 a las 08:00** (antes: viernes 20). No hay turnos el lunes."* **[Confirmar] [Cancelar]**
5. Si ya pasaron las 08:00 del jueves, la tarjeta agrega: *"Esa corrida ya pasó: los 6 quedarían sin aviso. ¿Los mando ahora?"* con el mismo botón.
6. Confirmar → se guarda, se registra, el chat muestra el resultado y **Deshacer**.
7. El jueves a las 08:00 el workflow cuenta 2 días hábiles salteando el lunes y avisa el martes. Nadie hizo nada más.

---

## 8. Plan por fases

| Fase | Entrega | Criterio para pasar a la siguiente | Esfuerzo (días de trabajo) |
|---|---|---|---|
| **0 (hecha)** | Núcleo de cálculo del bot para días sin atención (idéntico al vivo en 2026–2027; cada día hábil se avisa una vez) y lógica + acciones del panel (8/8, comparado con el nodo real del bot). Sin pantalla ni despliegue | — | — |
| **1. Días sin atención** | Migración + despliegue del bot + pantalla con feriados sugeridos, vista previa y "qué va a pasar con los avisos"; "Adelantar" que no repite | OK de Lucas; **la ejecución real del siguiente día hábil avisa la fecha esperada**; cero duplicados | 3–4 |
| **2. Lista de precios única** | Tabla de precios, marcadores en los 9 textos (revisados por la doctora), resolver en v7, v6 y avisos; respaldo = último valor | La doctora aprueba los textos; los 3 caminos (v7, v6, avisos) muestran el mismo precio; **cambio de prueba de punta a punta y vuelta atrás** | 4–5 |
| **3. Chat: consultas y proactividad** | `/asistente` solo lectura sobre todas las áreas + sugerencias proactivas (feriado próximo, avisos que no salieron, pacientes esperando) | Una semana de uso sin respuestas inventadas; tope de gasto verificado | 3 |
| **4. Chat: acciones A y B** | Calendario, avisos, mensajes fijos, textos, tono; vista previa "así lo lee el paciente" y "probar con Asiri"; log y Deshacer | Batería de casos de la sección 9 en verde; auditoría completa | 5–6 |
| **5. Chat: nivel C** | Precios, interruptores del bot, cambios multi-texto; roles (clínica, doctora, admin) y confirmación reforzada | Revisión con la doctora; **cambio de precio real verificado en los 3 caminos** | 3–4 |
| **6. Agenda conversacional** | Huecos, agendar/anular con un clic y sin doble trabajo en Dentalink | Prueba con paciente de prueba y anulación al terminar | 4–5 |
| **7. Salud y diagnóstico (nivel 2)** | "¿Anda todo?" en lenguaje común; diagnóstico de fallas con propuesta de arreglo que aprueba una persona técnica; nunca despliega solo | Solo si el análisis lo recomienda y se resuelve D9 | 10–15 |
| **8. Varias clínicas** | Configuración por clínica y alta de clínica | A definir con el plan de ventas | aparte |

Total hasta tener el **chat completo de configuración (fases 1–5): unos 20–25 días de trabajo**, 5–6 semanas de calendario con revisiones. Quedan ~10 semanas hasta febrero: alcanza para las fases 1–5 y el **manual de operación**; las fases 6 y 7 quedan ajustadas y se priorizan con el resultado del análisis. Lo más valioso por menos esfuerzo: fases 1, 2 y 3.

---

## 9. Verificación (cómo sabemos que anda, no solo que "compila")

- **Offline:** tests de la lógica de fechas (ya), de las validaciones y de las propuestas (que una propuesta vencida, repetida o alterada no ejecute).
- **Contra el sistema real:** el SQL del Gate se prueba en una tabla temporal con transacción revertida antes de tocar nada; el despliegue del bot es con `diff_vivo`, backup y `guarda_vivo`; después se mira la **ejecución real** del siguiente día hábil.
- **Del chat:** una batería fija de pedidos reales y trampas (ambiguos, fechas pasadas, "borrá todo", pedidos fuera de alcance, intentos de inyección dentro del texto) con resultado esperado; se corre antes de cada cambio del chat.
- **De punta a punta:** cargar y sacar un día ficticio lejano en el panel real, verificar el efecto en la base y en la lista de próximos avisos, y dejar todo limpio (regla de cero residuos).
- **Por qué no se prueba solo en pantalla:** leer el código de la pantalla no alcanza (lección del 2/9).

Casos de aceptación de la Fase 3 (mínimo): feriado simple · vacaciones con rango que cruza fin de semana · "el lunes" ambiguo · fecha pasada · día ya cerrado · deshacer · adelantar con 0 pacientes · adelantar después de que salió el automático · usuario sin rol · modelo caído · crédito agotado · pedido fuera de alcance.

---

## 10. Riesgos

| Riesgo | Cómo se controla |
|---|---|
| El modelo malinterpreta una fecha ("el lunes") | La función determinista valida; la tarjeta muestra día de la semana y fecha completa; si es ambiguo, pregunta |
| La persona confirma sin leer (fatiga) | Solo se pide confirmar algo concreto y con efecto escrito; sin "¿estás seguro?" genérico; cantidades visibles; confirmación reforzada solo cuando sale un mensaje a pacientes |
| Alguien sin permiso hace algo | Roles; la ejecución revalida el rol; el modelo no decide permisos |
| Inyección de instrucciones | El modelo no lee texto de pacientes ni comentarios libres; las herramientas devuelven datos estructurados |
| Datos de salud enviados a un proveedor del exterior | El chat solo ve **cantidades y fechas**, no nombres. Si en el futuro hace falta ver pacientes ("¿le llegó el aviso a X?"), es otra decisión (D3) con contrato y revisión legal (SEG-17, Ley 25.326) |
| Se acaba el crédito o cambia el modelo | Degradación segura; tope de gasto; aviso a Lucas; las pantallas funcionan siempre |
| La lista de feriados queda vieja | Sugerencias hasta 01/01/2027 con fuente oficial; **puentes de 2027 todavía no decretados**; recordatorio en diciembre para cargarlos; cualquier día se agrega a mano |
| Doble trabajo con Dentalink | El asistente no toca la agenda en esta propuesta |
| Dos personas editan a la vez | Última escritura gana y queda en el log (mismo patrón que hoy); se avisa si cambió mientras se confirmaba |
| Falla el workflow tras el cambio | Con la lista vacía es idéntico al actual; backup PRE/POST y restauración con script; se verifica en la primera corrida real |
| Se confunde con Asiri (el bot de pacientes) | Otro nombre y otra pantalla: "Asistente de configuración" (D7) |

Pendientes de seguridad que **no** son de esta propuesta pero conviene no olvidar: repo del bot público con datos viejos en su historial (SEG-02), credenciales dentro de nodos de n8n, documentación vieja (el runbook todavía menciona Chatwoot, eliminado en octubre).

---

## 11. Decisiones que necesito de Lucas

| # | Decisión | Mi recomendación |
|---|---|---|
| D1 | Alcance del chat v1 | Solo recordatorios/Días sin atención + consultas de solo lectura (fases 1–3) |
| D2 | Roles | Tres: clínica, doctora, admin técnico (agrega un campo de rol a los usuarios del panel) |
| D3 | ¿El chat puede ver nombres de pacientes? | **No** en v1: solo cantidades |
| D4 | Proveedor, clave y quién paga | Clave de la API de Anthropic solo en el VPS, con tope mensual; la cuenta a nombre de Nexora hasta febrero y después de la clínica (a confirmar con el análisis) |
| D5 | **Autonomía:** ¿de acuerdo con los 4 niveles (A solo + Deshacer, B un clic, C refuerzo + doctora, D nunca)? | Sí. Es lo que permite que sea "bien autónomo" sin que pueda hacer daño |
| D6 | ¿Se piensa para revender? | Sí: configuración por clínica desde el diseño, aunque la Fase 6 sea después |
| D7 | Nombre | "Asistente de configuración", distinto de Asiri |
| D8 | Feriados | Sugerencias en el panel, decide la clínica; Lucas carga los de 2027 cuando salga el decreto |
| D9 | Después de febrero: ¿quién aprueba arreglos técnicos? | Decisión de negocio: **soporte de guardia pago** (Nexora segunda línea). Sin eso el nivel 2 queda en informes |
| D10 | Orden de arranque | Fase 1 esta semana; después Fase 2 (precios) y Fase 3 (consultas y proactividad) |
| D11 | **Lista de precios única:** ¿qué precios entran? | Consulta, devolución, contención y cuota; los demás se agregan después. La doctora revisa los 9 textos antes de migrar |
| D12 | Dentalink: ¿el chat cambia también el valor de la prestación? | No en v1: avisa que hay que cambiarlo y lo deja anotado; se evalúa por API más adelante |
| D13 | Proactividad: ¿dónde avisa? | Dentro del panel; y opcional en el grupo de WhatsApp que ya existe para derivaciones |

---

## 12. Estado de lo ya hecho (Fase 0), para no duplicar

- **Bot (subido a GitHub, SIN desplegar):** `recordatorios/fecha_manana.js` y `recordatorios/gate_dias_cerrados.sql` (base: el Gate vivo de hoy), con copias congeladas del código vivo y `tests/test_recordatorios_dias_cerrados.js` (27/27).
- **Panel (en la compu, sin commitear, SIN desplegar):** `lib/recordatorios/dias-sin-atencion.ts` (lógica pura), `tests/recordatorios-dias.test.mjs` (8/8, incluye la comparación con el nodo real del bot), acciones `cerrarDiasAction` / `cerrarRangoAction` / `abrirDiaAction` y `adelantarRecordatoriosAction` con "no repetir el aviso" (tipado correcto). **Falta la pantalla**: se pausó hasta aprobar esta propuesta.
- **Verificado el 19/11:** el panel y el bot calculan lo mismo en más de 600 días comparados; las sugerencias de feriados salen de fuentes oficiales (Resolución 164/2025 y Ley 27.399).
