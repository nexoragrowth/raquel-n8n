# Propuesta: Bandeja de Atención y estado del contacto en el panel

*Para aprobar: Lucas · 08/10/2026 · Diseño base: "seguro". Lleva la fase 1 chica del "operativo" y algunas piezas del "crm". Los errores que marcaron los jueces ya están corregidos.*

---

## 1. Qué problema resuelve

Hoy el panel solo distingue dos cosas: si el contacto está en modo humano o no, y si leíste sus mensajes. De ahí salen cuatro problemas:

- **"Humano para siempre".** En el dashboard figuran 7 contactos en modo humano que en realidad ya vencieron. Uno de ellos es el celular de la Dra. Pasa porque se cuenta el flag tal cual está en la base, sin mirar la hora (`app/(app)/dashboard/page.tsx:135`).
- **Proveedores y chats personales.** El número de la clínica es el WhatsApp personal de Irina, y el bot les contesta a todos por igual. La etiqueta `no_bot` se perdió cuando se borró Chatwoot el 05/10.
- **Pacientes que insisten.** La regla del v7 dice que el bot "se calla hasta que la clínica lo reactive". En la práctica lo reactivaría Auto Reactivar, que está apagado (`memory/decisions.md:860-863`). El resultado real es 1 h de silencio y después vuelve a empezar.
- **Avisos que nadie cierra.** Las urgencias y los pagos se pierden en el grupo de WhatsApp. `escalaciones_log` registra 110 avisos en 30 días, pero no guarda si alguien los resolvió, quién ni cuándo.

La propuesta es una **bandeja de tarjetas con dueño**, un **tipo de contacto** que hace que el bot no conteste, y **una sola regla** que deciden por código el v6, el v7 y el panel para saber si el bot responde. No es un embudo de ventas: es el orden mínimo para que la secretaria trabaje y para que nadie quede trabado.

---

## 2. Estados del contacto

En cada chat se ven dos cosas separadas: **el color** (qué necesita ese contacto) y **si el bot habla**. Los dos salen de una función única en Supabase, `bot_silenciado(tel)`, que devuelve si está callado, el motivo y hasta cuándo.

Cuando hay más de un estado a la vez, se muestra en este orden: Urgencia, Pausado, Humano, Requiere secretaria, Silenciado, Bot.

| Estado | Qué significa | Cuándo entra | Cuándo sale | ¿Responde el bot? |
|---|---|---|---|---|
| **Urgencia** (rojo) | Hay una tarjeta de urgencia abierta: el triaje la escaló (bracket suelto, otra urgencia, red flag, alambre sin video) o hubo una urgencia junto con un cambio de agenda. | El triaje la escala (`triaje_urgencias_log` con accion='escalado' o un aviso `[TRIAJE]`). | Solo cuando una persona la resuelve en el panel. **No vence nunca.** | **Calla solo 1 h** (la ventana que ya existe por `tomar=true`). Después vuelve a contestar y la tarjeta muestra "el bot volvió a responder", pero sigue roja hasta que alguien la resuelve. *(Corrige el error de los diseños originales, que decían "no responde" sin aclarar esto).* |
| **Pausado esperando secretaria** | El bot se calla a propósito por más de 1 h, siempre con fecha de fin. | El v7 detecta que el paciente insiste (2.º aviso de acción en 30 min, `v7/clinica_core.js:39`) o que pidió hablar con una persona (`:84`). También la secretaria con "Esperando al paciente". | Al resolver la tarjeta, o al llegar al tope (24 h propuesto). En ese caso la tarjeta sigue abierta con "el bot volvió solo, nadie la resolvió". **No puede haber pausa sin tarjeta abierta ni sin fecha de fin.** | No |
| **Humano atendiendo** (azul) | Alguien del staff está hablando con el contacto. Es la regla de hoy, sin cambios: `human_takeover=true` y menos de 1 h desde el último mensaje del staff. | El staff escribe desde el celular, envía desde el panel o usa el switch. Cada mensaje renueva la hora. | Sola, 1 h después del último mensaje del staff, o con "Devolver al bot". | No. Se ve la cuenta regresiva: "el bot vuelve en 42 min". |
| **Requiere secretaria** (ámbar) | Hay una tarjeta de acción abierta: pago o comprobante a imputar, queja, baja de datos, turno a menos de 48 h, alta fallida en Dentalink, error del agente, falta de ficha, `escalar_a_secretaria` del v6. | Cualquier aviso de nivel acción que llega a `escalaciones_log`. | Cuando la secretaria la resuelve. Pasado el plazo **no se cierra sola**: queda marcada "vencida". | **Sí.** La queja no silencia, como dice la política del v7 del 07/10. |
| **Silenciado (no paciente)** (gris) | Proveedor, interno, no paciente o grupo. | El staff cambia el tipo de contacto en el panel. Es obligatorio dejar un motivo y, si el número tiene ficha en Dentalink, hay doble confirmación. Los `@g.us` se marcan solos. | Cuando el staff lo vuelve a "paciente". Cada 90 días aparece una tarjeta "¿sigue siendo proveedor?". | No. Hay una red de seguridad para urgencias (ver la decisión D2). |
| **Bot atendiendo / Por clasificar** | El estado normal. "Por clasificar" son los contactos sin ficha a los que nadie les puso tipo todavía. | Por defecto. | Cuando se cumple alguna condición de las filas de arriba. | Sí |
| *Bot apagado global* (estado del sistema, no del contacto) | Alguien mandó `/bot off` (Redis `bot:status`) o apagó el workflow desde `/control`. **Son dos mecanismos distintos:** prender el workflow no deshace un `/bot off`. | Por un admin. | Con `/bot on` o desde `/control`. | No, para nadie. El panel muestra un banner (requiere un webhook nuevo, ver fase 4). |

---

## 3. Etiquetas y su efecto en el bot

La regla es simple: **solo el *tipo de contacto* puede callar al bot. Las etiquetas nunca lo hacen.** Así hay una sola fuente de silencio y no se repite lo que pasó con Chatwoot.

| Etiqueta / tipo | Efecto en el bot | Quién la pone |
|---|---|---|
| **tipo: paciente** | Ninguno. Lo protege: para pasarlo a un tipo silencioso hay que dejar un motivo y confirmar dos veces. | Se pone sola si el teléfono tiene ficha en Dentalink (tabla puente sembrada desde `recordatorios_enviados`: 125 teléfonos, 142 fichas). |
| **tipo: sin_clasificar** (por defecto) | Ninguno: el bot responde. Aparece en el filtro "Por clasificar". | Es el valor por defecto de cada contacto nuevo. |
| **tipo: proveedor** | **El bot no responde**, recién desde la fase 3, cuando el gate lo lee. | Solo el staff, con motivo. Asiri puede **sugerirlo** (queda en gris y no silencia), nunca aplicarlo. *Hoy el v7 no detecta proveedores por código; es solo una regla del prompt. Hay que construir esa detección.* |
| **tipo: interno** | El bot no responde y los mensajes del staff a ese número no prenden el modo humano. | Se precargan el celular de la Dra. (549351\*\*\*\*787) y el de Lucas (549116\*\*\*\*034). **El de Irina no**, porque es el número de la instancia de Evolution, no un contacto que le escribe a la clínica. |
| **tipo: no_paciente** | El bot no responde (número equivocado, spam, familiares). | El staff, con motivo. |
| **tipo: grupo** | Queda fuera del bot, de la bandeja y de los KPI. | Se pone sola por el sufijo `@g.us` (hoy hay 3 en `pacientes`). |
| pago_pendiente | Informativa: muestra un chip y suma el filtro "Pagos a imputar". | Se pone sola cuando se abre una tarjeta de pago y se quita al resolverla. |
| familia_multiple | Informativa: recuerda preguntar para quién es el turno. | Se pone sola cuando el teléfono tiene más de una ficha (hoy son 17). |
| lista_espera | Informativa. | Con el aviso `[FYI]` de lista de espera del v7. |
| urgencia_reciente | Informativa: chip rojo durante 7 días. | Al cerrar una tarjeta de urgencia. |
| baja_datos | Abre una tarjeta de acción. **No corta los recordatorios**, porque Recordatorios es NO TOCAR. | Se pone sola con el aviso de baja, o la pone el staff. |

---

## 4. Pantallas del panel

**Atención** (`/atencion`, nueva, primera del menú, con un contador rojo). Es una bandeja con estas columnas: **Urgencia · Requiere secretaria · En curso · Esperando paciente · Resueltas hoy**. En el celular se ve como una lista agrupada. Los avisos informativos (FYI) se archivan solos. Los avisos técnicos van a una pestaña que solo ve el admin. Cada tarjeta tiene cuatro botones:

- **Tomar**: me la asigno.
- **Abrir chat**.
- **Esperando al paciente**: pausa al bot con tope.
- **Resolver**: la nota es *opcional* y la casilla "devolver el chat al bot" viene *tildada*.

Si llegan avisos repetidos del mismo tipo y del mismo teléfono, se suman a la misma tarjeta con un contador, en vez de crear otra. Hoy hay un teléfono con 18 avisos.

Ejemplo de tarjeta (con datos inventados):

```
URGENCIA · hace 12 min · sin tomar                 [3 avisos]
Sofía (mamá de Tomás) · 549388****326 · Familia (2 fichas)
"Se le salió un bracket y le lastima" — Triaje escalado
Bot: callado hasta 15:42, después vuelve a responder
[Tomar]  [Abrir chat]  [Esperando al paciente]  [Resolver]
```

**Conversaciones** (cambios en la lista que ya existe). Hoy solo hay dos filtros (`conversation-list.tsx:64`). Pasan a ser **Todos · No leídos · Necesitan atención · Humano/Pausado · Por clasificar · Silenciados**, cada uno con contador. Cada chat lleva un punto de color y chips: "Humano 42 min", "Pausado hasta 18:30", "Pago pendiente". Se ordenan primero por prioridad y después por el último mensaje. "Devolver todos al bot" deja afuera a los silenciados.

**Encabezado del chat.** Muestra el motivo exacto, que viene de la función: "Humano hasta 15:42", "Pausado por la tarjeta #123", "Silenciado: proveedor (Irina, 08/10)". Hay **un solo botón para devolverlo al bot**. Al lado van el selector de tipo, las etiquetas y una franja con las tarjetas abiertas de ese contacto, para resolverlas sin salir del chat.

**Silenciados.** Es la lista de todos los contactos callados, con quién los calló, cuándo, el motivo, la próxima revisión y el botón "volver a paciente". Es la garantía visible de que nadie queda callado sin que se sepa.

**Historial del contacto** (un panel lateral). Muestra la línea de tiempo: cambios de tipo, quién tomó y resolvió tarjetas, pausas y devoluciones al bot, y quién hizo cada cosa.

**Dashboard.** El número de "en modo humano" pasa a respetar la ventana de 1 h (`esModoHumano`, igual que la lista). Se suman: tarjetas abiertas, tarjetas vencidas en los últimos 7 días y el tiempo hasta tomar una urgencia.

---

## 5. Qué cambia

### En Supabase v3 (todo se agrega, nada se rompe)

Todas las columnas nuevas aceptan vacío o traen un valor por defecto. Así no se rompe ningún INSERT que ya existe, en particular el que hace **"Triaje: Decidir"** directo en `escalaciones_log`.

- **`pacientes`** (ya está publicada en Realtime, así que los cambios se ven al instante en el panel). Se suman:
  - `tipo_contacto`, con `sin_clasificar` por defecto, más `tipo_motivo`, `tipo_por`, `tipo_at` y `tipo_revisar_at`.
  - `bot_pausa_desde`, `bot_pausa_hasta` y `bot_pausa_motivo`, con una regla que impide que hasta menos desde supere 72 h. *(Corrige el diseño original: la regla no se podía escribir con `now()`).*
  - `human_takeover` y `human_takeover_at` **no cambian de significado**.
- **`casos`** (nueva). Son las tarjetas: tipo, nivel, estado, dueño, fechas, nota, contador de avisos, si sostiene una pausa, y vínculos a `escalaciones_log` y `triaje_urgencias_log`. Hay una sola puerta de entrada, la función `registrar_aviso`, que deduplica y une en la misma tarjeta el aviso del grupo y el registro del triaje. *(Corrige el diseño original: dos disparadores separados chocaban entre sí y se perdía el vínculo).* Reemplaza la tabla `peticiones` de `rebuild_v3_schema.sql`, que nunca se aplicó.
- **`escalaciones_log`**. Se suman `nivel`, `tipo` y `caso_id`, que pueden quedar vacíos. Mientras los avisos no traigan el tipo, un disparador lo deduce del prefijo del texto, igual que hoy `lib/escalaciones.ts`, y marca `tipo_inferido`. "Ya estás atendiendo" y los restos de la banlist pasan a informativos, no a acción. Si un disparador falla, **nunca** frena el INSERT original.
- **`contacto_eventos`** (nueva). Es la bitácora única, donde solo se agrega y nunca se borra. Sirve para el historial de cada contacto y, más adelante, para el embudo.
- **`contacto_etiquetas`**: solo etiquetas informativas, con estado `sugerida`, `activa` o `quitada`.
- **`contacto_fichas`**: puente entre el teléfono y el id de paciente en Dentalink. Es el primer paso de "nuestro Supabase".
- **Funciones:** `bot_silenciado(tel)` es la única definición de silencio. Devuelve silencio si el modo humano tiene menos de 1 h, **o** si hay una pausa vigente, **o** si el tipo es silencioso. Además hay una vista `v_contacto_estado` para la lista, así no se suman consultas pesadas a `getConversacionesList`.
- **Sin `org_id`.** Para tener varios clientes se usa una base por clínica con el mismo esquema versionado, en una carpeta propia del repo del panel, separada de las migraciones viejas 0001-0007.

### En el bot v6 (hoy en producción)

Son cambios mínimos: backup, diff que te muestro, `check_triaje.py`, `webhookId evo-webhook-v2` preservado y **siempre partiendo de un GET nuevo**. Los JSON de `workflows/current/` son del 04/10 y todavía tienen la lógica de Chatwoot.

1. **"Consultar Takeover Paciente"**: se cambia solo el texto del SQL para que use `bot_silenciado`, con el mismo nombre de campo (`hasHumanoLabel`). El grafo no cambia.
2. **"Gate Humano Final"** (la segunda capa, después del modelo) también consulta la función.
3. **"Activar Takeover (fromMe)"** no actúa si el contacto es interno o grupo. Hoy los mensajes del staff no crean tarjetas, pero sí ponen contactos en modo humano y crean filas de "paciente" falsas.
4. **Dato verificado:** en el v6 el triaje corre **después** del gate de entrada. Por eso un proveedor silenciado pierde el triaje. La red de seguridad tiene que vivir en otro lado (decisión D2).
5. **Helper Notify Grupo:** recibe tipo, nivel y pausa ya estructurados. Exige un secreto compartido en el mismo momento en que empieza a crear pausas. "Decidir Takeover" deja de silenciar por palabras ("queja", "dolor") para los avisos que traen tipo, y conserva esa búsqueda por palabras solo como respaldo para los avisos viejos del v6.

### En el v7 (Asiri)

- El cerebro consulta `bot_silenciado` **antes** de llamar al modelo y, si está silenciado, corre igual el filtro de urgencias.
- Insiste o pidió persona: avisa con `tomar` **y además** pausa con tope, ligada a una tarjeta.
- Todos los avisos salen con tipo y nivel estructurados.
- Los avisos técnicos van a la pestaña técnica, no al grupo de la Dra.
- Todo sigue sujeto a `modo==='vivo'`.

### En el panel

- `toggleBotAction` deja de escribir `human_takeover` sin fecha y usa solo el webhook, para que haya un solo lugar que lo escribe.
- "Resolver con devolver al bot" llama a `panel-toggle-bot` y, en las urgencias, también vence la clave Redis `triaje:<tel>`.

---

## 6. Fases de entrega

Sigue tu orden: **v7 primero**. Las fases 1 y 2 no tocan n8n y no frenan el v7. Las que tocan el bot van junto con el plan de conexión del v7 (a6c3a70).

**Requisito previo:** desde el 06/10 a las 13:00 UTC no entra tráfico (WhatsApp desconectado de Evolution). Ninguna prueba de punta a punta vale hasta reconectarlo.

| Fase | Qué se hace | Qué ves al terminar |
|---|---|---|
| **F0** (½ día, solo panel) | Commit y deploy del cambio de modo humano de 24 h a 1 h (hoy está sin commit), y el dashboard con `esModoHumano`. | El dashboard muestra **0 en modo humano** (hoy muestra 7), y el switch coincide con lo que hace el bot. |
| **F1** (2-3 días, Supabase y panel, **cero n8n**) | `casos`, `registrar_aviso`, disparadores con protección, bitácora, Realtime. Pantalla Atención con Tomar, Resolver y Devolver al bot, franja de tarjetas en el chat y KPI. Solo las tarjetas de las últimas 72 h nacen como nuevas. | **Irina ya tiene la bandeja**: ve en vivo los pagos y las urgencias, los toma y los cierra con su nombre. La prueba es un aviso real con tu número que aparece como tarjeta, se resuelve y se limpia en el mismo turno (`limpiar_numero_demo.py`). |
| **F2** (2 días, panel) | Tipo de contacto cargado automáticamente (paciente si tiene ficha, grupo, interno para la Dra. y para vos), `contacto_fichas` sembrada, filtros nuevos, "Por clasificar", chips de familia y pago pendiente. **Todavía no se pueden elegir tipos silenciosos.** | La lista ordenada por prioridad y estado, con los no pacientes identificados a mano por clasificar. |
| **F3** (1 día de cambio + prueba en sombra, **toca el v6, con tu OK**, junto con la conexión del v7) | `bot_silenciado` en Consultar Takeover y en Gate Humano Final, fromMe sin interno ni grupo, el v7 consulta la función, red de seguridad de urgencias. **El selector de proveedor se habilita en el mismo deploy.** | Marcás un número de prueba como proveedor y el bot no le contesta. Si escribe "dolor", se abre una tarjeta de urgencia. Lo volvés a paciente y el bot contesta. Después se limpia. |
| **F4** (1-2 días, Helper y v7) | Secreto en notify-grupo, tipos estructurados, pausa con tope para insiste y pidió persona, Decidir Takeover sin búsqueda por palabras para los avisos con tipo, link a la tarjeta en el mensaje del grupo, botón "¿Marcar como proveedor?", banner de bot apagado (webhook nuevo en el satélite Panel acciones staff). | Se termina el loop del que insiste. La queja deja de callar al bot. Si alguien dejó `/bot off`, se ve. |
| **F5** (después, si lo aprobás) | Embudo Nuevo → Interesado → Agendó → Paciente como vista calculada; réplica de citas y lectura de `ver_turnos` y `elegir_ficha` desde Supabase, con comparación en sombra. | Es el primer paso medible de "las herramientas leen de nuestro Supabase". Requiere la decisión D5. |

---

## 7. Lo que hay que decidir

| # | Pregunta | Mi recomendación |
|---|---|---|
| D1 | ¿El silencio por tipo (proveedor, interno, no paciente) vence solo? | **No vence.** Queda a la vista en "Silenciados" y genera una tarjeta de revisión a los 90 días. |
| D2 | **Red de seguridad:** ¿qué pasa si un contacto silenciado escribe una urgencia? Hoy, en el v6, el triaje corre después del gate y se perdería. Además, las red flags base viven en el código del nodo de n8n: `triaje_config` solo tiene `red_flags_extra`, no un regex completo. | Un **disparador en `mensajes_entrantes_live`** con una copia de las red flags base más `red_flags_extra`, que abra una tarjeta de urgencia sin respuesta del bot. En el v7, el cerebro corre su propio filtro. Antes hay que confirmar que `mensajes_entrantes_live` recibe todos los entrantes. La otra opción es cambiar el grafo del v6, y es más riesgosa. |
| D3 | Tope de la pausa por insistencia o pidió persona: ¿24 h? Las urgencias siguen en 1 h. | **24 h, solo para esos dos casos**, siempre con tarjeta. **No** extender el silencio de las urgencias (tu regla del 06/10). |
| D4 | ¿Cron nuevo ("Vigía") para volver a avisar las tarjetas vencidas? Choca con "sin requests de fondo" (18/7). | **No hacer cron nuevo.** Los vencimientos se calculan contra la hora actual. El aviso de "N tarjetas vencidas" se suma al Daily Summary o al Health Check que ya existen. |
| D5 | Réplica de citas de Dentalink en Supabase (cron o sync): ¿reabrimos la decisión del 18/7? | Que sea una decisión aparte, para F5. Hasta entonces, Dentalink se lee bajo demanda al abrir una tarjeta, no por cada render. |
| D6 | "Integrado con Dentalink": ¿leer o escribir? | **Solo leer y vincular** (fichas ↔ teléfono). No escribir etiquetas en la ficha. Si la Dra. lo quiere más adelante, va en sombra y con `modo==='vivo'`. |
| D7 | ¿Quién trabaja la bandeja y quién mira las urgencias los fines de semana? (`open-questions.md:69`) | Decisión de negocio con la Dra. Propongo Irina en horario hábil, y la Dra. y vos en las urgencias sin tomar. |
| D8 | Avisos técnicos (`[FALLO TECNICO]`, chequeo de salida): ¿siguen yendo al grupo de la Dra.? | Que vayan **solo a la pestaña técnica y a vos**. |
| D9 | ¿Nota obligatoria al resolver? ¿Roles separados? | Nota **opcional**. Sin roles por ahora: la bitácora registra quién hizo qué. |
| D10 | ¿Qué hacemos con los 26 contactos `@lid`? | Que queden "Por clasificar". Unificarlos con el número de celular queda abierto. |
| D11 | El embudo de conversión (producto Nexora): ¿lo queremos ya? | **Después del v7 estable** (regla 6). Primero, lo que Irina usa todos los días. |

---

## 8. Riesgos y cómo se cubren

| Riesgo | Cobertura |
|---|---|
| Un tipo silencioso que el bot no lee le da a la secretaria una falsa sensación de control. | El selector se habilita **en el mismo deploy** que el gate (F3), y la fase no se da por terminada sin la prueba de punta a punta (regla 8). |
| Un paciente real marcado por error como proveedor queda sin bot y sin triaje. | Motivo obligatorio, doble confirmación si tiene ficha, el bot solo sugiere, revisión a los 90 días, pestaña Silenciados y la red de seguridad de D2. Queda un riesgo: la detección por palabras no cubre todo. |
| Un disparador nuevo rompe el log de escalaciones o del triaje en vivo. | Disparadores con protección que nunca frenan el INSERT, columnas que aceptan vacío, `check_triaje.py` y un INSERT de prueba igual al de "Triaje: Decidir" antes de habilitar. |
| Silencio desde varias fuentes (como pasó con Chatwoot). | Una sola función, `bot_silenciado`, la leen el v6, el v7 y el panel. Las etiquetas nunca silencian. |
| notify-grupo no tiene autenticación (`current-state.md:219-220`). | En F1 solo genera tarjetas visibles, que no silencian. El secreto entra en F4, **antes** de que pueda crear pausas. |
| La búsqueda por palabras de "Decidir Takeover" calla al bot por una "queja". | Se alinea en F4. Hasta entonces, coordinarlo con la conexión del v7. |
| PostgREST se cae o se rota la service key, que está escrita en Gate Humano Final y en Triaje: Decidir. | Sigue fallando abierto como hoy, pero con aviso técnico. Cuando se toque el nodo en F3, aprovechar para pasar la key a una credencial de n8n. |
| La bandeja arranca llena de pendientes falsos. | Solo las tarjetas de las últimas 72 h nacen como nuevas. Las 309 históricas quedan como historial. |
| Nadie mira la bandeja. | Contador en el menú, link a la tarjeta en el mensaje del grupo, vencidas en el Daily Summary y D7 resuelta con la Dra. |
| Los chats personales de Irina ensucian `pacientes`. | fromMe sin interno ni grupo desde F3, y el filtro "Por clasificar" para limpiar los primeros días. |
| Se toca producción partiendo de los snapshots viejos. | GET nuevo obligatorio, backup antes y después, diff que te muestro y un script `apply_*.py` por cambio. |

---

**Pedido de OK:** F0 y F1 se pueden arrancar ya, porque no tocan el bot. Para F3 y F4 necesito tus respuestas a D1-D4 y que las coordinemos con la conexión del v7.