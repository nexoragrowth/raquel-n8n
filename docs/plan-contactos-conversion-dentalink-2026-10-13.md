# Plan: contactos, conversión y reemplazo de Dentalink

**Fecha:** martes 13/10/2026 · **Para:** Lucas · **Estado:** esperando tus decisiones (§7). No se aplicó nada.

**Base:** 4 relevamientos de solo lectura (CRM de iPhones, uso real de Dentalink, quiénes le escriben a la clínica y agenda propia), 3 diseños (segmentación, conversión y reemplazo de Dentalink) y 2 críticas en contra (la tuya, de producto, y una de ingeniería y datos de salud). Este documento reemplaza a los 3 diseños: donde una crítica tenía razón, el plan ya viene corregido (lista completa en el Anexo D).

**Tu pedido, en una línea:** que los contactos se creen y se segmenten solos, que el bot no les hable a la Dra., a la secretaria, a los colegas ni a los proveedores, que lleve al potencial paciente al turno y que vayamos armando lo propio para dejar Dentalink.

Rutas: RQ = `C:\Users\not\Desktop\proyectos\raquel-n8n`, PN = `C:\Users\not\Desktop\proyectos\nexora-whatsapp-agent`, MB = `C:\Users\not\Desktop\proyectos\mbcell-supabase`. Los teléfonos van enmascarados.

---

## 0. Antes que nada (hoy): la clave secreta de Supabase está publicada

Lo verifiqué hoy, sin usar la clave:
- El repo `nexoragrowth/raquel-n8n` es **público**.
- `scripts/apply_desacoplar_chatwoot.py` está en `origin/main` desde el commit `eac44b1` (06/10) y tiene **4 veces una clave `sb_secret_…`**, la misma que el v6 tiene escrita a mano en nodos. Solo en el snapshot del v6 aparece 8 veces.
- Según la crítica de ingeniería, además hay 21 celulares que no son de admins en archivos versionados y los 3 teléfonos admin en `.claude/CLAUDE.md`.

**Por qué es lo primero:** esa clave saltea todos los permisos de la base. Con ella se puede leer y escribir el historial de chats, los contactos, las escalaciones y los recordatorios (que tienen nombre de paciente). Son datos de salud (Ley 25.326, arts. 9 y 10). No sé si alguien la usó.

**Qué hacemos (mar 13 – mié 14/10, unas 3 horas entre los dos):**
1. Inventario de dónde se usa la clave, con GET de solo lectura: la credencial de n8n, los nodos del v6 que la tienen escrita (entre ellos `Gate Humano Final`), el `.env` del panel en el VPS y los `.env` locales.
2. **Un PUT al v6 (PUT-A, con backup y diff):** los nodos con la clave escrita pasan a leerla de una credencial o variable de n8n. Si la instancia no lo permite hoy, se pone la clave nueva en el nodo como paso transitorio y el script no se commitea. Si se rota sin este paso, `Gate Humano Final` falla y deja pasar mensajes con el staff atendiendo.
3. Rotar la clave en Supabase y actualizarla en n8n, en el panel y en los `.env` locales.
4. Repo privado y purga del historial (`git filter-repo`) de la clave y los celulares.
5. Revisar los logs de la API de Supabase buscando accesos ajenos.
6. Avisarle a la clínica (es la responsable de la base) y consultar con un abogado si corresponde informar algo más.

**Hasta que esté rotada no se copia a la base ningún dato de salud nuevo** (DNI, dirección, fichas).

---

## 1. En 6 líneas

1. Cada número que le escribe a la clínica pasa a ser un **contacto con un tipo**: prospecto, paciente, familiar, interno, colega, proveedor o no paciente. El bot solo les habla a prospectos, pacientes y familiares.
2. **Desde el 20/10** el bot deja de contestarles a la Dra., a la empleada y a unos 50 proveedores, colegas y centros de imágenes. Hoy les contestó a 18 de 51, y a la Dra. le contestó 7 veces y la derivó 6.
3. Al prospecto que pregunta, el bot le responde y **le ofrece horarios concretos de la primera consulta**, como mucho 2 veces. Hoy, de 32 prospectos que atendió solo el bot, ninguno sacó turno.
4. Cada paso (oferta, reserva, pago, asistencia, presupuesto, tratamiento) queda registrado como un hecho, y el panel muestra **dónde se cae la gente**. Eso es lo que se vende: "tus anuncios traen X consultas y el bot agenda Y".
5. **Dentalink se copia en espejo desde fines de noviembre** y la agenda propia se arma y se prueba en sombra en enero y febrero, solo con lo que la clínica usa. Se apaga cuando se cumplan los criterios del §4.4 **y** haya quién la mantenga después de febrero.
6. Todo se arma con configuración por clínica, sin "Raquel" escrito en el código, para que la clínica 2 reciba lo mismo. Y antes que todo, hoy: rotar la clave publicada (§0).

---

## 2. Segmentación de contactos

### 2.1 Qué pasa hoy (medido entre el 18/07 y el 13/10)

| Hecho | Número |
|---|---|
| Identificadores distintos que escribieron, sin pruebas | **275**: 212 pacientes o prospectos (77%), 41 proveedores o comercios, 4 centros de imágenes, 4 colegas, 2 del staff y 12 ambiguos |
| Contactos a los que solo les escribe la clínica | **38** (3 grupos, comercios, colegas y pacientes en seguimiento) |
| Mensajes entrantes que no son de pacientes (05/09 al 13/10) | **~30%** de 2.155: 352 de proveedores, 129 del celular personal de la Dra., 73 de centros de imágenes |
| A no pacientes el bot les respondió | **18 de 51** (45 mensajes) y generó **22 avisos** al grupo |
| Tabla de contactos (`pacientes`) | 321 filas, sin tipo, sin origen y sin vínculo con la ficha; las 321 dicen "Paciente WhatsApp" |
| Teléfonos con turno en Dentalink (por recordatorios) | ~125 teléfonos con 142 fichas; **17 teléfonos con 2 o 3 fichas** (familias o duplicados) |
| Contactos `@lid` (WhatsApp esconde el número) | 26 |
| Silencio que existe hoy | Solo el modo humano, que **dura 1 hora** (verificado en el SQL de `Consultar Takeover Paciente` y de `Gate Humano Final`). Los 46 contactos con `human_takeover` en verdadero no silencian nada pasada esa hora |

### 2.2 Tipos de contacto

| Tipo | Quién es | ¿Le habla el bot? | Red de seguridad (§2.5) | Quién lo pone |
|---|---|---|---|---|
| **prospecto** | Número sin ficha y sin tipo | **Sí**, con el flujo de conversión (§3) | — | Nadie: es el valor por defecto |
| **paciente** | Tiene una ficha en la agenda | **Sí**, con el flujo de servicio | — | El sistema, por hecho |
| **familiar/tutor** | Escribe por un hijo u otro familiar (varias fichas, o fichas de menores) | **Sí** (el v7 ya pregunta "¿para quién es?") | — | El sistema propone; la relación queda "sin definir" hasta que alguien la confirme |
| **interno** | Dra., secretaria, empleada, otros profesionales de la clínica | **No.** Escribirles no prende el modo humano. Fuera de métricas | **No** (la Dra. escribe "dolor" hablando de pacientes) | **Solo un admin** (Dra. o vos) |
| **colega** | Odontólogos, médicos y **centros de imágenes** externos | **No** | **Sí**, solo con señales fuertes de urgencia (no se le pasan sus mensajes al modelo: traen datos clínicos de terceros) | Irina, con motivo |
| **proveedor** | Laboratorio, insumos, comercios, servicios | **No** | **Sí** | Irina, con motivo |
| **no paciente** | Conocido, número equivocado, spam, autorespuesta de empresa | **No** | **Sí** | Admin. Si tiene ficha, pide doble confirmación |
| **grupo** | Grupos de WhatsApp | No (ya se descartan) | No | El sistema |

- **"Colega" es nuevo:** no estaba en ningún plan previo. Lo pediste explícito.
- **Si un contacto tiene dos tipos**, manda el que más restringe: grupo > interno > no paciente > proveedor = colega > paciente = familiar > prospecto. Un colega que también es paciente queda en silencio; si pide turno, salta la red de seguridad y lo atiende una persona.
- **Historial:** un tipo nunca se edita ni se borra; se cierra. Siempre queda quién lo puso, cuándo y por qué. Es el modelo `crm.contacto_roles` del CRM de iPhones (MB, migración 60), adaptado.
- **El silencio por tipo no vence.** A los 90 días el contacto aparece como "para revisar", sin cron.
- **Tu teléfono de prueba y los números sintéticos quedan marcados como prueba**, nunca como interno: si no, el bot dejaría de contestarte en las pruebas.
- **Los comandos `/bot off|on|status` de la Dra. siguen funcionando** aunque sea interna: se procesan antes del silencio.

### 2.3 Cómo se genera cada contacto

| Fuente | Qué pasa | ¿Toca n8n? |
|---|---|---|
| Entra un mensaje | La base da de alta el contacto (o lo actualiza) con el nombre que muestra WhatsApp **como etiqueta, no como verdad**, la fecha del primer mensaje y si la charla la empezó el contacto o la clínica. Si el alta falla, el mensaje igual se guarda | No |
| La clínica escribe primero | Queda registrado que la inició la clínica. Es un **hecho**, no una lectura del texto | No |
| Sale un recordatorio | El contacto queda vinculado a la ficha leyendo `recordatorios_enviados` con una **consulta**, **sin disparadores** sobre esa tabla: Recordatorios es NO TOCAR y un bloqueo ahí podría duplicar un recordatorio | No |
| El v7 consulta Dentalink | Vincula el teléfono con la ficha que encontró, **solo en modo vivo** | Sí (v7) |
| Panel | Alta manual o alias | No |
| Espejo de Dentalink (§4, desde fines de noviembre) | Vincula las fichas sin recordatorio y propone familiares por fecha de nacimiento, **después de limpiar duplicados por DNI** (el v6 creó fichas duplicadas) | No |

**Fuente del origen:** se toma desde `n8n_chat_histories` (existe desde el 18/07), no desde la bandeja (`mensajes_entrantes_live` arranca el 05/09). Si se usara la bandeja, 26 contactos sin ficha que escribieron primero figurarían como "los inició la clínica". Lo anterior al 18/07, o dudoso, queda como `legado`.

**Los `@lid`** quedan como prospectos, con una entrada de baja prioridad en la cola, hasta tener la tabla que une `@lid` y teléfono (backlog P2).

### 2.4 Cómo se clasifica

- **Siempre lo decide una persona.** El bot solo **sugiere**: cuando el orquestador del v7 deriva a la secretaria, indica además "parece proveedor / colega / no paciente / interno". **Lo decide el modelo, no una regex**, y queda la frase textual del contacto como evidencia.
- **Cola "Por clasificar"**, con motivos cerrados: precarga, la inició la clínica, posible proveedor, posible colega, posible no paciente, posible interno, silenciado pide turno, silenciado con urgencia, `@lid` sin teléfono, ficha ambigua, revisión de 90 días.
- **Directorio de colegas y proveedores conocidos** (se carga a mano o con un CSV): si el teléfono coincide, **sugiere**; nunca aplica solo.
- **Resolver:** al asignar un tipo se cierran todas las entradas de ese contacto. "Revisado, sin cambios" cierra la entrada sin tocar nada.
- **Mientras nadie confirma, el bot sigue como hoy:** deriva y, si el contacto insiste, pasa a modo humano.
- **Al poner un tipo que silencia, se cierra su lead abierto** con el motivo `no_es_paciente`, que el embudo no cuenta. En el CRM de iPhones esto no pasa y el embudo queda contaminado con proveedores.

### 2.5 Efecto en el bot: una sola regla

Una función en la base, `contacto_ruta(teléfono)`, decide si el bot habla. La leen el v6 a la entrada (`Consultar Takeover Paciente`), el v6 a la salida (`Gate Humano Final`, por donde sale también el v7) y el panel. Nadie más calcula el silencio por su cuenta.

| Orden | Si… | Entonces |
|---|---|---|
| 1 | Es un grupo o una difusión | Se descarta |
| 2 | Tiene tipo **interno** | Silencio, sin red |
| 3 | Tiene tipo **no paciente, proveedor o colega** | Silencio **con red de seguridad** |
| 4 | Una persona escribió en la última hora (modo humano) | Silencio |
| 5 | Pausa vigente puesta desde la bandeja | Silencio |
| 6 | **Contacto nuevo** (creado después de que esto esté vivo), sin tipo, sin ficha, y la charla la empezó la clínica | Silencio con red + entrada en la cola (**decisión D3**; los contactos históricos los clasifica una persona) |
| 7 | Tiene ficha, o tipo paciente o familiar | Responde con el flujo de **paciente** |
| 8 | Todo lo demás, incluido un número que nunca escribió | Responde con el flujo de **prospecto** |

**Red de seguridad (nunca contesta):** si un silenciado escribe algo que parece urgencia o pedido de turno, el bot **no le responde**. Avisa al grupo, por ejemplo: *"Contacto silenciado (proveedor, desde el 21/10, lo puso Irina) escribió: «…». El bot NO le respondió. Si es paciente, cambiale el tipo: <link>"*, y abre una entrada en la cola.
- **Capa 1:** las mismas señales fuertes de urgencia que ya usa el v6. Están permitidas porque fallan del lado seguro.
- **Capa 2** (solo para proveedor y no paciente): el orquestador del v7 en modo "solo clasificar".
- **Tope:** un aviso por contacto cada 6 horas. Una urgencia fuerte avisa siempre.
- **Antes de activarla:** 3 días en sombra (registra y no avisa).
- **Volumen:** unas 11 llamadas al modelo por día como máximo.
- **Nombre:** "Red de seguridad de silenciados", para no confundirla con el workflow "Áurea – Vigía" que ya existe.

**Si la función falla:**
- **En la entrada,** se mantiene lo de hoy: deja pasar. Hoy `Consultar Takeover Paciente` tiene `continueOnFail` y, ante un error, el bot responde. Lo verifiqué. Pasar a "cerrar ante un error" callaría también las urgencias, porque el triaje viene después. Si algún día se cambia, tiene que ser con las señales de urgencia corriendo igual.
- **El aviso técnico va al grupo de la clínica**, no solo a vos: después de febrero no vas a estar.
- **Un interruptor en Redis** (`seg:off`) vuelve al comportamiento anterior sin hacer un PUT.

### 2.6 "Día 1": el silencio mínimo, antes del v7 a todos (mar 20/10)

**Por qué no se puede esperar a noviembre:** hoy ningún silencio dura más de una hora, y el v7 deriva al grupo lo que no es de su alcance (proveedores incluidos). Si el v7 sale a todos sin esto, crece el ruido justo hacia la Dra.

Va en **una migración y un PUT al v6 (PUT-B)**:
1. **La tabla de tipos** se crea con su esquema final (no se tira nada después) y con los permisos cerrados (Anexo B).
2. **Una lista semilla de unos 50 números** que confirmás vos en unos 20 minutos: el celular personal de la Dra., la empleada, y los proveedores, colegas y centros de imágenes del relevamiento. La arma un script de solo lectura con los últimos 3 mensajes recortados a la vista; no se le manda el historial a ningún modelo. El motivo de carga es "Precarga oct-2026, confirmado por Lucas".
3. **En el v6:**
   - `Consultar Takeover Paciente` y `Gate Humano Final` también miran el tipo vigente.
   - La red de seguridad mínima: solo las señales fuertes de urgencia, que avisan al grupo.
   - **Se guarda el origen del anuncio** (`ctwa_ad`) en la base. Hoy WhatsApp lo manda (10 contactos de anuncio en 5 días) y se pierde.
4. **Prueba de punta a punta** con tu teléfono marcado temporalmente como proveedor, y limpieza en el mismo turno (regla 9).

**Qué ves:** desde el 20/10 la Dra. y los proveedores de la lista dejan de recibir respuestas del bot.

### 2.7 Precarga de los contactos actuales

| Grupo | Cantidad (medida) | Cómo se clasifica | Cuándo |
|---|---|---|---|
| Grupos | 3 | Automático (por el sufijo) | Día 1 |
| Con ficha (paciente o familiar) | ~125 teléfonos ↔ 142 fichas | Automático, por recordatorios. Los 17 con varias fichas quedan "sin definir" | Fines de octubre (migración del modelo, §5) |
| No pacientes medidos | 51 (41 proveedores o comercios, 4 centros de imágenes, 4 colegas, 2 del staff) | Lista semilla que confirmás vos | **Día 1 (20/10)** |
| Ambiguos | 12 | Irina, con los últimos 3 mensajes a la vista | Semana del 02/11 |
| Solo les escribe la clínica | 38 | Irina, igual | Semana del 02/11 |
| `@lid` | 26 | Prospecto + cola de baja prioridad | Automático |
| Pruebas (tu teléfono y números sintéticos) | ~7 | Marca de prueba | Día 1 |
| Resto | prospectos | Nada | — |

**Resultado esperado:** unos 125 pacientes o familiares, 3 grupos, unos 5 internos, entre 50 y 60 silenciados, unos 50 en la cola para Irina, y el resto prospectos.

- **No se usa `human_takeover` como señal de tipo:** hoy está mal usado.
- **La clasificación del relevamiento** (palabras clave más revisión) **solo ordena la lista** para que una persona la confirme. Nunca decide.

### 2.8 Pantallas: pocas y en el celular, porque hoy la clínica no usa el panel

El backlog dice "la clínica NO usa el panel", y la regla vigente es "Iri cancela y confirma EN Dentalink". Por eso arranca con **2 pantallas** y una **semana de prueba de adopción** (02 al 06/11), medida (entradas resueltas y tiempo):
1. **"Por clasificar"**, pensada para el celular: el motivo en lenguaje llano, la evidencia y botones grandes (Paciente/prospecto · Proveedor · Colega · No paciente · Interno, solo admin · Revisado sin cambios). El link de los avisos lleva acá.
2. **Selector de tipo en el encabezado del chat**, con motivo obligatorio, doble confirmación si tiene ficha y la leyenda "Silenciado: proveedor (Irina, 21/10)".

**Después de la prueba, y solo si se usan:** contactos, silenciados, directorio y precarga. Todo lo que se puede sacar de hechos (recordatorios, espejo) **no depende de un clic**.

---

## 3. Flujo de conversión y cuestionario de descubrimiento

### 3.1 De dónde partimos

| Dato | Valor |
|---|---|
| Contactos nuevos | 79 desde el 14/08, unos **9 por semana** (17 son `@lid`) |
| Nuevos que terminaron con turno | 14 de 79 (18%) |
| Prospectos atendidos por el staff | **8 de 28** con turno (29%) |
| Prospectos atendidos **solo por el bot** | **0 de 32** |
| Leads de anuncio ("Quiero más información") | 0 de 18 con turno (contados por el texto). La metadata muestra **10 de anuncio en 5 días**, así que contar por el texto los subestima |
| Abandonan después de 1 o 2 mensajes sin respuesta humana | 25 de 60 prospectos |
| Primera respuesta humana a un nuevo | Mediana de 11 min, pero **p75 de unas 17 h**. 12 de 79 escribieron fuera de lunes a viernes de 8 a 20 |
| Qué piden en las primeras 24 h | Información 36, agendar 24, precio 22, anuncio 18, pago 14, urgencia 6 |

**El camino real del paciente** (sale de la base de conocimiento):
1. Primera consulta: $50.000, con pago anticipado.
2. Estudios.
3. Devolución ($50.000), con diagnóstico, plan y presupuesto.
4. El presupuesto vale 1 semana.
5. Tratamiento: inversión inicial más una cuota de $70.000 por mes.
6. Contención.

**El bot lleva al paciente hasta el sillón; el tratamiento lo vende la clínica.**

### 3.2 Problemas del v7 que se arreglan antes de salir a todos

| # | Problema | Arreglo | Cuándo |
|---|---|---|---|
| 1 | **El v7 pide el pago de la consulta en cualquier reserva,** también en el control de un paciente en tratamiento (`orquestador_core.js:319-323`). Va contra la KB 1 | Pedir el pago solo cuando no hay ficha (primera consulta), hasta que exista el tipo de turno. Una condición y un test | **Semana del 13/10** |
| 2 | **El v7 no tiene entrada para el anuncio:** con el v7, un lead de anuncio recibe el menú genérico | Hasta que exista la presentación del anuncio, el primer mensaje con origen `ctwa_ad` lo atiende el v6 | En el PUT del v7 a todos (03/11) |
| 3 | **Los `@lid` pueden quedar con un celular falso en Dentalink** (`agenda_core.js:254` arma el alta con `String(p.tel)`) | Verificar qué llega en `tel`. Si es un LID: alta sin celular, aviso "cargar celular a mano", y no cuenta como convertido | **Semana del 13/10** |
| 4 | Lo que reserva el bot no dice qué tipo de turno es (40 min fijos, sin motivo de atención) | `tipo_turno` (primera consulta, control, devolución) en la reserva y en el comentario | Conversión, noviembre |
| 5 | La KB se contradice: la 3 dice "nunca dar valores de tratamientos" y la 36 da la cuota | La cuota mensual solo para contactos con ficha (decisión D7) | Conversión, noviembre |

### 3.3 Cómo convierte sin conversar

1. **Primero contesta lo que preguntó,** en 1 a 3 frases, con los datos de la KB. **La oferta la agrega el código después**, nunca el modelo.
2. **Una sola pregunta u oferta por mensaje.** Si ya hay otra pendiente (confirmar un horario, para quién es, datos del paciente nuevo, el menú), no se agrega nada.
3. **La oferta es una acción, no una charla:** horarios reales para elegir con un número.
4. **Topes:**
   - 1 oferta por mensaje;
   - ninguna si hubo otra en las últimas 24 h;
   - **2 por episodio**;
   - nunca a quien dijo que no.
5. **Nunca hay oferta junto a:** una urgencia, una derivación, el pase a una persona, una pregunta pendiente, un silenciado, un pedido de "no me escriban", **ni después de Pagos**. Quien pide los datos para pagar desde un celular sin ficha suele ser el padre o la madre que paga la cuota del hijo.
6. **Solo a contactos sin ficha y sin turno vigente.** Eso se decide con la consulta a Dentalink que el v7 ya hace en cada mensaje, no con el espejo. Así nunca se le ofrece una "primera consulta" a alguien en tratamiento.
7. **Si el paciente acepta o no, lo decide la IA** (orquestador o Turnos). El código no pisa esa decisión: un "no, gracias" que el orquestador marca sin respuesta queda así. Solo un "no entendí" con una oferta vista hace menos de 24 h se manda a Turnos para que decida.
8. **No hay sub-agente "Comercial" que redacte.** Volverían dos modelos escribiendo en fila, que ya midió peor (13/24 contra 20/24 el 06/10, y 22/45 contra 31/45 el 08/10). Qué oferta va y cuándo es una política fija en código (`v7/conversion_core.js`) que se prueba offline.

### 3.4 Etapas (una sola lista para todo el sistema)

Las etapas salen de **hechos**, no de mover tarjetas. Una etapa marcada a mano manda solo hasta el próximo hecho.

| Columna en el panel | Etapas por dentro | Qué la mueve | Desde |
|---|---|---|---|
| **Consulta** | Nuevo → Interesado | Primer mensaje de un prospecto. El bot o el staff le respondió algo útil | Noviembre |
| **Primera consulta** | Agendada → Realizada / No vino | Reserva del bot. Recordatorio enviado a ese teléfono. Cita en estado "Atendido" (espejo). **"No vino" solo si el staff marca "No asistió"**, nunca porque falte el "Atendido" | Agendada: noviembre. El resto: con el espejo, diciembre |
| **Devolución y presupuesto** | Devolución agendada → Presupuesto entregado | Cita con motivo de devolución (espejo). El staff marca "Presupuesto enviado (fecha)" | Diciembre |
| **En tratamiento** | En tratamiento → Contención | Cita de inicio o de tratamiento (espejo), o lo marca el staff | Diciembre |
| *Archivo* | **Perdido** (con motivo obligatorio) | Solo el staff. Si vuelve a escribir, se abre un episodio nuevo | Diciembre |
| *Chip* | **Dormido** | Calculado al leer: 21 días en Consulta, 30 sin devolución, 10 con presupuesto (vence a los 7) | Diciembre |

- **Motivos de pérdida** (borrador para la Dra.): precio, no respondió, no vino a la consulta, no hizo los estudios, eligió otro profesional, quería obra social, distancia u horarios, solo consultaba, la Dra. no indicó tratamiento, otro (con nota).
- **`no_es_paciente`** queda reservado para el cierre automático al silenciar, y el embudo lo excluye.
- **Para vender:** la semántica es fija y los nombres de las columnas y la traducción de los motivos de Dentalink a etapas (`mapa_motivos`) son configuración de cada clínica. "Devolución" y "Contención" son de ortodoncia.

### 3.5 Qué se le pregunta al paciente, y cuándo

Casi todo es pasivo. El bot pregunta solo lo que destraba el turno.

| Dato | ¿Lo pregunta el bot? | Cuándo y de dónde |
|---|---|---|
| Para quién es | **Sí**, solo si hay varias fichas o es un alta (ya existe) | Al elegir horario |
| Nombre, apellido y DNI | **Sí**, en un solo mensaje (ya existe) | Al elegir horario de un paciente nuevo |
| Menor | **No** (la KB dice "no preguntamos la edad") | Si lo dijo ("la nena"), la reserva agrega: "el menor tiene que venir acompañado de su padre, madre o tutor" |
| Cómo nos conoció | **Nunca** | Sale de la metadata del anuncio, o lo carga el staff |
| Obra social | **Nunca** | Si pregunta, Información responde con la KB 22 |
| Interés (brackets, alineadores, ortopedia, continuar un tratamiento) | **No** | Lo carga el staff en el panel. El "Anotador" (una IA que llena la ficha sola) **queda para después de la prueba de adopción**: llenar una ficha que nadie lee es costo sin retorno |
| Franja (mañana o tarde) | **No** | La oferta ya trae 2 de mañana y 2 de tarde |

**Preguntas que el bot no supo responder:** cada vez que Información no tiene la respuesta, queda registrada la pregunta, recortada y sin datos personales. La Dra. o Irina cargan la respuesta en `/conocimiento` y la próxima vez la responde el bot. Así la información mejora con datos reales.

### 3.6 El otro cuestionario: el de la clínica (una sola reunión)

Tu pedido de "consultas, tratamientos y demás… en un nuevo cuestionario de descubrimiento" también se puede leer como un **cuestionario para la CLÍNICA**. Los relevamientos y diseños juntaron más de 40 preguntas en 3 listas. Las unifiqué en **un solo cuestionario (Anexo C)**, de unos 60 minutos con la Dra. e Irina, **en la semana del 19/10**. Sirve además como formulario de alta para la clínica 2.

### 3.7 Ejemplos de mensajes

Los textos los arma el código y la Dra. los aprueba. Se editan desde el panel como directrices.

```
PACIENTE: hola cuanto sale la consulta
ASIRI:    La primera consulta tiene un valor de $50.000 e incluye evaluación y diagnóstico presuntivo.

          Si quiere, ya le reservo la primera consulta. Estos son los próximos horarios:
          1) …  2) …  (mañana)     3) …  4) …  (tarde)
          Responda con el número del que le quede mejor.
PACIENTE: el 3 es pa mi nena
ASIRI:    (repite el horario elegido) Para reservarlo necesito nombre, apellido y DNI de la paciente, en un solo mensaje.
          … al reservar: confirmación + pedido de pago (es primera consulta) + "La paciente menor tiene que venir
          acompañada de su padre, madre o tutor."
```

```
(primer mensaje con origen de anuncio)  PACIENTE: ¡Hola! Quiero más información
ASIRI: presentación del anuncio (KB 40 sin "responda Quiero un turno") + los horarios de la primera consulta.
       Hasta que esto exista, ese primer mensaje lo atiende el v6 como hoy.
```

```
PACIENTE: no por ahora gracias            → ASIRI: (no responde; el episodio no recibe más ofertas en 24 h)
PACIENTE: no me escriban más              → ASIRI: Listo, no le vamos a enviar más mensajes. Si necesita algo,
                                                    puede escribirnos cuando quiera.   (queda la marca)
PACIENTE (sin ficha): ¿me pasás el alias? → ASIRI: datos de pago. SIN oferta de turno.
```

**Seguimientos** (en 2026, tarjetas que Irina manda con un toque; ver D8). **Todos llevan la línea de baja:**
- **No vino** (solo si el staff marcó "No asistió"): «Hola. Vimos que no pudo venir a su primera consulta del {fecha}. Si quiere, le buscamos otro turno: respóndanos por acá. Si prefiere que no le escribamos más, avísenos.»
- **Presupuesto por vencer:** «Hola. ¿Pudo ver el presupuesto que le enviamos el {fecha}? Tiene validez hasta el {fecha+7}. La secretaria le responde por acá. Si prefiere que no le escribamos más, avísenos.»

**Límites de Información:** la duración del tratamiento y la continuación de un tratamiento empezado con otro profesional se responden **solo con el texto literal de la KB**. Si la KB dice "depende", el bot dice eso. Nunca opina.

### 3.8 Métricas

| Métrica | Hoy | Meta (hipótesis, a 4 semanas de prender la oferta) |
|---|---|---|
| **Principal: primeras consultas realizadas por semana**, por origen | Sin dato (necesita el espejo, diciembre) | Medir desde diciembre |
| **Secundaria: pagos de la consulta recibidos** | Sin dato | Medir |
| Prospectos atendidos solo por el bot → turno | **0/32** | **≥ 15%** |
| Leads de anuncio → turno | **0/18** | ≥ 15% |
| Prospectos que preguntan información o precio y reciben horarios concretos | No existe | ≥ 90% |
| **Pasos** (dónde se cae): oferta mostrada → horario elegido → datos pedidos → datos dados → horario confirmado → reservado → pago avisado → asistió | No existe | Medir |
| **Barandas** | — | 0 ofertas a silenciados, urgencias o derivaciones; 0 ofertas repetidas en 24 h; bajas < 5% de los que recibieron oferta; 0 quejas por insistencia |

- **Antes y después se miden con el mismo script, sobre las mismas fuentes crudas** (`tests/embudo_baseline.py`, solo lectura). Los eventos nuevos sirven para ver los pasos, no para la comparación.
- **Con unos 35 nuevos en 4 semanas, un 15% son 5 turnos:** se reportan cantidades, no solo porcentajes. No hay volumen para un A/B.
- **Antes de cerrar los textos de la oferta** se hace una retrospectiva de solo lectura de las 60 charlas: las 32 donde el bot no convirtió y las 28 del staff. Dónde se cortan y qué dice Irina antes del turno son las "mejores prácticas" que pediste copiar.

---

## 4. Reemplazo de Dentalink

### 4.1 Qué usamos hoy y qué usa la clínica

| Módulo de Dentalink | ¿Lo usa el bot, el panel o la clínica? (medido) | Prioridad para reemplazar |
|---|---|---|
| Agenda: citas y disponibilidad | Bot, recordatorios, panel y staff. Lunes y miércoles empiezan entre 15:00 y 19:40; martes, jueves y viernes, entre 08:00 y 12:10. **El 23,5% de los turnos empieza fuera de la grilla de 40 min** | **P0** |
| Estados de cita | 1 Anulado, 2 Atendido, 7 No confirmado, 14 Cambio de fecha, **15 Notificado por WhatsApp (48-51% de las citas: no lo pone el bot y no se sabe quién)**, 18 Confirmado por WhatsApp (bot), 22 Confirmado (panel) | **P0** |
| Fichas de pacientes | DNI, email, fecha de nacimiento y dirección en 21 de 21; número de ficha en 19 de 21; familiares vinculados en 0 de 21 | **P0** |
| Tipos de turno y motivos | Duraciones de 40, 20 y 10 min. Motivos: En TTO LARGO, Consulta Ortodoncia, Devolución con escaneo, Escaneo + FOTOS, Inicio TTO de Ortopedia. El bot siempre reserva 40 | **P0** |
| Bloqueos, feriados y vacaciones | No medido, pero indispensable (el incidente de Mariela fue un sábado con la clínica cerrada) | **P0** |
| Profesional, sillón y sucursal | 1, 1 y 1, fijos en todas las escrituras | P0 en el modelo; P1 en pantallas |
| Usuarios y auditoría | Implícitos (el staff corrigió 11 citas a mano el 07/10) | **P0** |
| Recordatorios | Ya son nuestros: solo cambia de dónde se leen las citas | **P0** (al final) |
| Planes de tratamiento | Todas las citas cuelgan de un plan (13 nombres comerciales) | P1, si la clínica confirma que los usa |
| Pagos, caja y deuda | Sin evidencia | Pregunta → P1 si se usa |
| Archivos (escaneos, fotos) | Hay motivos que lo sugieren | Pregunta → P1 si se usa |
| Historia clínica, evoluciones, odontograma | Sin evidencia | **No se migra en 2026** (§4.6) |
| Reportes, encuestas, campañas, inventario, recetas, facturación (es de Chile), convenios, multisucursal | Sin evidencia | No se replica |

**Uso de la API:** el bot, los recordatorios y el panel usan 9 rutas de unos 30 recursos.

**Problemas de Dentalink que lo propio resuelve:**
- `/agendas` trae 10 turnos por llamada y hacen falta hasta 6 páginas;
- da error 429 después de unos 40 pedidos seguidos;
- no evita que dos reservas se pisen;
- a veces rechaza el DNI en el alta;
- el panel muestra como máximo 400 citas.

### 4.2 Qué se replica primero

**Solo lo que la clínica usa, no todo Dentalink:** agenda con tipos de turno y duración, grilla de 10 min, **sobreturno que marca el staff** (el bot nunca lo usa), bloqueos y feriados (una persona resuelve los turnos afectados; nada se cancela solo), estados configurables con historial y "confirmado por" (bot o staff), reprogramación que deja la cita vieja como "cambio de fecha" (hoy el bot la deja como cancelación), fichas, usuarios con auditoría y recordatorios leyendo la agenda propia.

**Dónde vive:** en el **mismo Supabase v3**, en un esquema `agenda`, con plan Pro. nexora-agenda (MVP del 02-03/09, nunca desplegado) aporta las entidades y los tests. La agenda del CRM de iPhones aporta las reglas en SQL ya probadas: validación de horario, bloqueos con afectados, reprogramación atómica y reserva sin duplicados. Su "pendiente que vence solo" no se porta: el bot nunca pide confirmación.

### 4.3 Fases

En cada fase, hasta la 3, volver atrás es cambiar un valor de configuración.

| Fase | Qué es | Fechas | Qué ves |
|---|---|---|---|
| **0. Relevamiento** | GET de solo lectura a Dentalink con el token del panel, a 1 pedido cada 1,5 s. Mide: módulos que se usan, historial de estados (**quién pone el 15**), configuración de notificaciones, horarios, motivos y totales. Más el cuestionario de la clínica | 19/10 – 06/11 | Lista cerrada de qué se replica y respuesta sobre el estado 15 |
| **1. Espejo (solo lectura)** | Un workflow de mantenimiento copia de Dentalink a nuestra base **solo lo mínimo**: id y celular de la ficha, si es menor, y las citas con estado, motivo y duración. **Sin DNI, dirección, email ni comentarios** hasta tener el contrato de datos firmado | Construcción 16/11 – 27/11; vivo desde el 30/11 | Desde el 04/12: el panel muestra la agenda completa (sin el tope de 400), los contactos quedan vinculados con sus fichas y el embudo calcula "vino", "devolución" y "en tratamiento" |
| **2. Sombra** (la "doble escritura", simulada) | La agenda propia calcula en paralelo y se compara: cada búsqueda de horarios del v7 contra `/agendas`, y **cada cambio que ve el espejo, sea de quien sea** (el staff escribe la mayoría desde la pantalla de Dentalink), pasa por las reglas propias para medir qué habría rechazado. Recordatorios v2 (un clon) arma su lista sin enviar y se compara con la del v1. El panel tiene la agenda propia en "modo práctica" | 04/01 – 26/02/2027 | Un informe semanal de diferencias. El 26/02: "la agenda propia coincide en X%; estas son las diferencias que faltan" |
| **3. Sistema propio con Dentalink de respaldo** | Lo propio pasa a ser la verdad. Irina opera en el panel. Cada cambio se copia a Dentalink (escritura inversa) para poder volver | **No antes del lun 01/03/2027**, y solo con los criterios del §4.4 y el acuerdo de mantenimiento (D9) | Irina trabaja sin Dentalink |
| **4. Apagado** | Export final verificado y baja en la renovación | Después de 6 semanas de la fase 3 sin volver atrás | Dentalink dado de baja |

**Por qué no es una doble escritura real:** escribir dos veces deja dos verdades que se separan. Además, la mayoría de las escrituras las hace el staff desde la pantalla de Dentalink, así que la doble escritura solo cubriría al bot (que hizo 0 reservas en las últimas 60 ejecuciones del v6). La sombra mide todo sin riesgo.

**Por qué el corte no puede ser antes de marzo:** son unos 25 días de trabajo solo para la sombra, y compite con todo lo demás. Además, cortar justo cuando termina el soporte deja a la clínica sola con algo recién estrenado. **Tu pedido ("cuando dejemos Dentalink ya lo tengamos") se cumple el 26/02, con la agenda propia construida y medida en sombra**; el corte es una decisión aparte.

### 4.4 Criterios para apagar Dentalink (todos en verde)

1. Espejo conciliado al 100% durante **14 días seguidos**, con datos de no más de 10 min (p95).
2. Disponibilidad propia igual a la de Dentalink en **200 búsquedas o más**, con cada diferencia explicada.
3. Los cambios reales que vio el espejo durante 3 semanas, pasados por las reglas propias: **0 rechazos sin explicar** (incluye sobreturnos y el estado 14).
4. Recordatorios v2 igual al v1 durante **10 días hábiles**.
5. Escritura inversa probada con citas de prueba: crear, reprogramar, anular y confirmar; que se vea en Dentalink en menos de 5 min, **sin duplicados ante un reintento y sin que Dentalink les mande avisos a los pacientes**.
6. **Irina hizo 3 días completos en paralelo** (cargó en el panel lo mismo que en Dentalink) y la Dra. dio el OK.
7. **El v6 no atiende a nadie** (v7 al 100%) y sus herramientas de Dentalink están desconectadas.
8. **El control "Dentalink up?" del v6 ya no frena el bot.** Hoy, si dice que Dentalink está caído, se apaga todo el bot, urgencias incluidas.
9. Login por usuario, roles y auditoría en producción.
10. Supabase Pro, copia diaria fuera de Supabase y una restauración probada en menos de 1 h. Agenda del día en PDF por mail a las 07:00.
11. Prueba de punta a punta real desde tu teléfono, y limpieza.
12. Un simulacro de vuelta atrás hecho un sábado.
13. Manual de operación de la agenda y de qué hacer si se cae.
14. Contrato de datos firmado (Nexora como encargado) y **acuerdo de mantenimiento después de febrero**.

### 4.5 Vuelta atrás (objetivo: menos de 15 minutos)

1. **Drenar primero:** frenar propuestas nuevas del v7, vaciar la cola de escritura inversa y completar en `recordatorios_enviados` el id de Dentalink de cada cita. Si no, el v1 puede reenviar recordatorios y las propuestas pendientes apuntan a ids que Dentalink no conoce.
2. Cambiar la configuración a `dentalink`. El bot y el panel vuelven a leer de Dentalink.
3. Recordatorios: apagar el v2 y prender el v1 (antes de las 9 si es el mismo día).
4. Avisar a Irina.
5. El espejo vuelve a copiar de Dentalink a lo propio.

**Qué dispara la vuelta atrás:** una doble reserva, el espejo o la cola de escritura caídos más de 30 minutos en horario hábil, un recordatorio que no salió, que Irina no pueda operar, o que la Dra. lo pida.

### 4.6 Datos de salud y ley (validar con un abogado; esto no es asesoramiento legal)

- **Roles:** la clínica es la responsable de la base y Nexora es el encargado (Ley 25.326, art. 25). Hace falta un **contrato escrito** que diga qué pasa con los datos cuando termina el servicio. Es crítico por febrero. Hay que verificar si la base está inscripta en la AAIP.
- **Transferencias internacionales:** Supabase está en San Pablo, Dentalink en Chile y **OpenAI en EE.UU.** (el v7 le manda los mensajes). Hay que ver con el abogado si esos países se consideran adecuados y, si no, qué cláusulas hacen falta. Mientras tanto:
  - minimizar lo que va al modelo;
  - no mandarle los mensajes de los colegas a la red de seguridad;
  - no hacer la precarga con un modelo.
- **Minimización:** el espejo copia lo mínimo. DNI, dirección y comentarios de las citas (que se tratan como texto clínico) recién con la clave rotada, el contrato firmado, Pro y los permisos cerrados.
- **Historia clínica** (Ley 26.529: inalterable y custodiada al menos 10 años): **no se migra en 2026**. Si la Dra. la usa en Dentalink, antes de apagarlo se genera un export congelado (un PDF por paciente más los datos crudos, con hash) guardado en 2 lugares, uno de la clínica. La historia nueva se sigue llevando en Dentalink (con el plan más barato) o se diseña aparte en 2027.
- **Publicidad:** cada mensaje que no es del servicio (reactivación, "no vino", presupuesto) **lleva la línea de baja** (Decreto 1558/01, art. 27). Segmentar por tratamiento o "no vino" para promover es un uso de datos sensibles que el abogado tiene que validar, y hace falta un consentimiento registrado. Sin eso, solo seguimientos que el staff manda a mano.
- **Aviso de privacidad:** una línea con un link en el menú de Asiri (quién es el responsable, para qué se usan los datos y cómo ejercer los derechos), con texto aprobado por la Dra.
- **Derecho de supresión:** no se guarda texto libre en tablas que no se pueden borrar (Anexo A).
- **Retención:** las tablas nuevas entran al workflow de Retención que ya existe. No hace falta un cron nuevo.

---

## 5. Cómo encaja con el v7 y el v6 (sin romper producción)

**Reglas para cada cambio:**
- **Como mucho un PUT al v6 por semana,** siempre desde un GET nuevo, con backup PRE y POST, diff que ves antes, `check_triaje.py`, `webhookId evo-webhook-v2` preservado y prueba de que **"sin tipo y sin flag = el grafo de hoy"** (como `tests/test_v7_flag.py`).
- **Migraciones solo aditivas,** primero en un clon y después en el v3, y **con Supabase Pro antes de la primera tabla nueva**.
- **Disparadores** sobre la bandeja de entrantes: se crean apagados, solo encolan (sin bloqueos, con tiempo máximo) y se prenden después de repetir el INSERT real. **Ninguno sobre `recordatorios_enviados`.**
- **No se tocan:** Recordatorios v1 (`7RqTApkvVavRmq3R`), el sub-workflow de horarios `GuDQ9VmKWZvQnerV` (lo comparte el v6) ni el Health Check, salvo por sus chequeos nuevos.
- **Sin cambios en producción entre el 21/12 y el 01/01.**

| Cambio | Pieza | Fecha | Qué toca |
|---|---|---|---|
| **PUT-A** | v6 | mié 14/10 | Clave de Supabase fuera de los nodos (requisito para rotarla) |
| **PUT-B "Día 1"** | v6 + 1 migración | mar 20/10 | Silencio por tipo en `Consultar Takeover Paciente` y `Gate Humano Final`, red mínima (señales fuertes de urgencia → aviso), guardado del origen del anuncio, interruptor `seg:off` |
| v7: pago solo en la primera consulta, `@lid` | v7 (`crear_v7_en_n8n.py`) | semana del 13/10 | `orquestador_core.js`, `agenda_core.js` + tests |
| **PUT-C "v7 a todos"** | v6 | mar 03/11 | Llave global del v7 (hoy es por número); el primer mensaje de anuncio sigue en el v6; los silenciados ni llegan |
| Modelo único | 1 migración | semana del 02/11 | Contactos, cola, bitácora, leads y motivos de pérdida (Anexo A) |
| **PUT-D "segmentación completa"** | v6 | mar 17/11 | `contacto_ruta` (calcula la ruta vieja y la nueva; `seg:on` elige), red de seguridad con modelo en sombra, `Activar Takeover (fromMe)` no prende el modo humano en internos ni grupos, registro del entrante adelantado (se mueve el nodo de extracción **completo**, con test de que da lo mismo) |
| v7: tipo en la derivación, vínculo con la ficha | v7 | 17-18/11 | El orquestador indica el tipo sugerido → cola. El vínculo con la ficha solo en modo vivo |
| v7: conversión | v7 | 18/11 (tu teléfono), 25/11 (contactos sin ficha) | `conversion_core.js`, prompts, `tipo_turno`, eventos. Flags `conv:tel:{tel}` y `conv:on` |
| Espejo de Dentalink | Workflow nuevo de mantenimiento | 16/11 – 04/12 | Un solo workflow (espejo, conciliación, chequeos) con una señal en el Health Check |
| Adaptador de agenda | v7 (no el v6) | enero | `agenda_io` responde con la misma forma que Dentalink. `agenda_core.js` casi no cambia porque ya recibe la E/S inyectada |
| Antes del corte (2027) | v6 | — | Sacar el freno de "Dentalink up?" y desconectar las herramientas de Dentalink del v6 |

**Llamadas a Dentalink:** el espejo, el bot y el panel comparten el mismo límite (429 después de unos 40 pedidos seguidos). Antes del espejo va **un limitador común en Redis, con prioridad para el bot**. El espejo usa una ventana corta (hoy a +14 días) cada 10 minutos y una ventana larga de noche, y **se detiene solo ante un 429**.

---

## 6. Roadmap con fechas

**Orden:**
1. Clave.
2. v7 en tu teléfono.
3. Día 1.
4. Panel en Vercel.
5. Piloto con pocos pacientes.
6. Bandeja de Atención.
7. v7 a todos.
8. Segmentación completa.
9. Conversión.
10. Espejo.
11. Embudo.
12. Agenda propia en sombra.
13. Manual.

**Fechas por compuertas:** si una compuerta no pasa, se corre lo que depende de ella, nunca la calidad.

| Semana | Qué se hace | Compuerta | Qué ves al terminar |
|---|---|---|---|
| **mar 13 – vie 16/10** | §0: inventario, PUT-A, rotación, repo privado. **v7 en tu teléfono:** T0 (sin flag, contesta el v6 de siempre) → flag → T1-T6 → limpieza. Repo del v7: pago solo en la primera consulta y `@lid`. Firmás las decisiones del §7. Sale el cuestionario de la clínica | Clave vieja inválida; T1-T6 bien | El v7 contestándote en vivo; la base protegida |
| **lun 19 – vie 23/10** | Lista semilla (lun) → **PUT-B Día 1 (mar 20)** → **panel en Vercel (mié 21)**, con el commit de lo pendiente (modo humano 1 h, KPI, login, Reconectar). **Piloto del v7 con 5 a 10 pacientes con ficha** elegidos con Irina, sin leads de anuncio (desde el jue 22), con 15 min de revisión por día. Reunión del cuestionario. Retrospectiva de las 60 charlas. Relevamiento GET de Dentalink | Día 1 sin efectos raros durante 2 días antes del piloto | **La Dra. y los proveedores dejan de recibir respuestas del bot.** El panel en Vercel |
| **lun 26 – vie 30/10** | **Bandeja de Atención** (tarjetas con Tomar y Resolver, desde las escalaciones y el triaje) + "Por clasificar" en el celular + selector de tipo. Sin n8n. Sigue el piloto | Piloto: 5 días hábiles sin P0 (evaluación del vie 30) | Irina con la bandeja y la cola en el celular |
| **lun 02 – vie 06/11** | **Semana de adopción de Irina,** medida. **PUT-C v7 a todos (mar 03)**. Migración del modelo único. Irina clasifica los 50 de la cola. Arranca la conversión offline | Piloto en verde | **El v7 atiende a todos** (menos el primer mensaje de anuncio) |
| **lun 09 – vie 13/11** | Conversión offline: suite verde, textos con lo aprendido en la retrospectiva. Segmentación completa en la base: `contacto_ruta`, disparador que solo encola, red con modelo | v7 a todos estable | Conversaciones de ejemplo de la oferta para aprobar con la Dra. |
| **lun 16 – vie 20/11** | **PUT-D (mar 17):** segmentación en sombra (registra qué habría silenciado). Conversión en tu teléfono (mié 18) y limpieza. Limitador de Dentalink y construcción del espejo | v7 a todos: 10 días hábiles sin P0 | La oferta funcionando en tu teléfono |
| **mar 24 – vie 27/11** (23/11 feriado) | `seg:on` (mar 24) si la sombra no afectó a ningún paciente; red de seguridad en vivo tras 3 días en sombra. **`conv:on` para contactos sin ficha (mié 25)**. Espejo construido | La sombra de la segmentación limpia; tu prueba de la oferta bien | **Los prospectos reciben horarios concretos**; los silenciados con urgencia avisan al grupo |
| **lun 30/11 – vie 04/12** | **Espejo vivo** y conciliación. El panel lee la agenda del espejo. Contactos vinculados con sus fichas. Etapas por hechos | Espejo 7 días al 100% (se cierra el 07/12) | Agenda completa en el panel; "vino" y "en tratamiento" calculados |
| **lun 07 – vie 11/12** (08/12 feriado) | **Embudo en el panel** (4 columnas + perdidos + dormidos). Seguimientos "no vino" y "presupuesto" como tarjetas. Línea del embudo en el Daily Summary | — | El embudo de punta a punta |
| **lun 14 – vie 18/12** | Margen. Revisión de 4 semanas de la oferta (textos y topes). **Primer reporte antes/después** con el mismo script | — | Cuántos turnos sacó el bot solo, contra 0 de 32 |
| **21/12 – 01/01** | **Veda:** sin cambios en producción | — | — |
| **lun 04 – vie 15/01/2027** | Login por usuario + roles + auditoría (Supabase Auth). Agenda propia: modelo y catálogos (tipos, estados, horarios), motor de disponibilidad | — | Usuarios propios en el panel |
| **lun 18 – vie 29/01** | Sombra de la agenda: comparador de búsquedas y repaso de cada cambio del espejo. Agenda en el panel en modo práctica. Adaptador `agenda_io` con tests de contrato contra los dos lados | — | Primer informe de diferencias |
| **lun 01 – vie 12/02** (08-09/02 Carnaval) | Recordatorios v2 sin enviar (clon). Escritura inversa probada con una cita de prueba (con tu OK). **Irina 3 días en paralelo**, si acepta | — | La agenda propia operable en práctica |
| **lun 15 – vie 26/02** | Manual de operación (alertas, modo humano, tipos, embudo, agenda). Chequeos automáticos en el Health Check. Entrega. **Informe "¿se puede apagar Dentalink?"** con los criterios del §4.4 medidos | — | **La clínica opera sola.** Agenda propia lista en sombra |
| **Desde lun 01/03/2027** | Corte de Dentalink (fase 3), **solo** con los criterios en verde y el acuerdo de mantenimiento | §4.4 | — |

**Capacidad:**
- **Del 14/10 al 18/12** hay 46 días hábiles (sin el 23/11 ni el 08/12). El plan usa unos 38 días de trabajo; el resto queda para el soporte diario de Raquel y los imprevistos.
- **Enero y febrero** tienen 38 días hábiles; el plan usa unos 31.
- **No entran** la demo navegable, el alta repetible ni la clínica 2 del plan del 08/10 (decisión D10).
- **Si algo se atrasa,** se corre primero la sombra de la agenda, después el embudo del panel. **Nunca** el Día 1 ni la estabilidad del v7.

---

## 7. Decisiones (con mi recomendación)

| # | Decisión | Recomendación |
|---|---|---|
| D1 | **Supabase Pro** (unos US$25 por mes) antes de la primera tabla nueva | **Sí, esta semana.** Hoy es un plan gratis sin copias descargables, que ya tuvo un problema de cuota en julio. Va a guardar el historial de tipos y, después, la agenda |
| D2 | **Día 1:** silencio por tipo con la lista semilla que confirmás vos (~50 números), el mar 20/10 | **Sí.** Ante un error, igual que hoy (deja pasar), con un aviso al grupo e interruptor para volver atrás sin PUT |
| D3 | Contactos desconocidos | **Número sin ficha = prospecto: el bot lo atiende** y lo lleva al turno. **"La inició la clínica, sin ficha" = silencio + cola + red**, solo para contactos **nuevos** desde noviembre y después de 1 semana en sombra. Los históricos los clasifica una persona |
| D4 | Colegas y centros de imágenes | **Silencio total más red de seguridad solo con señales fuertes de urgencia** (sus mensajes no van al modelo). Sin tarjeta por cada mensaje: el staff ya lee esos chats |
| D5 | Quién clasifica | **Interno y no paciente: solo un admin** (Dra. o vos; hay que sumar a la Dra. como admin del panel). **El resto: Irina desde el celular.** Vos revisás la cola una vez por semana hasta febrero. Definir si **Irina entra al grupo de derivaciones** (hoy son solo vos y la Dra.) o si el link le llega por la bandeja |
| D6 | Etapas | **Una sola lista** (§3.4): Consulta → Primera consulta → Devolución y presupuesto → En tratamiento, más Perdido y Dormido. "En tratamiento" = cita de inicio o de tratamiento, o marca del staff. "No vino" solo con la marca "No asistió" |
| D7 | Oferta | **Horarios directos en la 1.ª oferta y pregunta en la 2.ª**; como mucho 2 por episodio; nunca después de Pagos, de una urgencia ni de una derivación; solo a contactos sin ficha. La cuota mensual, solo a contactos con ficha. La métrica principal es la **primera consulta realizada**, no la agendada |
| D8 | Seguimientos y reactivación | **En 2026: tarjetas en la bandeja que Irina manda con un toque**, siempre con la línea de baja. Automáticos solo con el OK de la Dra., del abogado y un consentimiento registrado. Sin reactivación masiva (Evolution no es la API oficial: riesgo de bloqueo del número) |
| D9 | **Dentalink:** reabrir "solo Dentalink en 2026", "nexora-agenda archivado" y "solo leer y vincular" (08/10) | **Sí.** Espejo mínimo en noviembre; agenda propia en el Supabase v3 (esquema `agenda`), en sombra en enero y febrero; nexora-agenda como fuente de entidades y tests, sin desplegarlo. **Corte desde marzo de 2027 y solo con un acuerdo de mantenimiento** (abono de Nexora) |
| D10 | ¿Qué se corre del plan de producto del 08/10? | **La clínica 2, la demo navegable y el alta repetible pasan a 2027.** Lo vendible se arma adentro: configuración por clínica en vez de "Raquel" fijo, migraciones en el repo del panel y login por usuario en enero. Falta además un **workflow de entrada genérico** para el v7 (la clínica 2 no tiene v6): lo estimo en febrero |
| D11 | Relevamiento de solo lectura (GET) a Dentalink con el token del panel | **Sí**, a 1 pedido cada 1,5 s, sin guardar datos personales: módulos, historial de estados (quién pone el 15) y configuración de notificaciones |
| D12 | Abogado | **Sí, antes del espejo (noviembre):** contrato de encargado, inscripción en la AAIP, transferencias internacionales (Brasil, Chile, EE.UU.), consentimiento para seguimientos e historia clínica |

**Decisiones técnicas menores** (las tomo yo salvo que digas otra cosa):
- subir el tope del prompt del orquestador de 2.700 a 2.900 caracteres;
- un tope de 6 horas por contacto para los avisos de la red;
- revisión de los silenciados a los 90 días;
- el silencio por tipo no frena los recordatorios: Recordatorios es NO TOCAR, y un colega que es paciente tiene que recibirlos.

---

## 8. Riesgos

| Riesgo | Cómo se cubre |
|---|---|
| **La clave publicada ya se usó** | §0 hoy: rotación, revisión de logs, aviso a la clínica y abogado |
| **Silenciar por error a un paciente real** (un colega o un familiar del staff que también es paciente) | Doble confirmación si tiene ficha, motivo obligatorio, varios tipos visibles, red de seguridad, revisión a 90 días, sombra antes de activar. El caso "lo inició la clínica" solo para contactos nuevos |
| **La red de seguridad no ve un mensaje ambiguo** de un silenciado | Dos capas y 3 días en sombra midiendo. El staff igual lee esos chats: hoy escribe el 90% de lo que sale |
| **La clínica no adopta el panel** | Solo 2 pantallas al principio, en el celular, con una semana de prueba medida. Lo que sale de hechos no depende de un clic. Si no se adopta, se frena lo que depende de clics (perdidos, presupuesto) y sigue lo automático |
| **El bot "vende" y molesta** | 1 oferta por mensaje y 2 por episodio, textos aprobados por la Dra., `conv:on` para apagarlo sin tocar n8n, barandas medidas |
| **Muchos cambios en producción a la vez** (v7, segmentación, conversión) | Un PUT por semana, invariantes, interruptores en Redis (`seg:off`, `conv:on`, flags del v7) y veda de fin de año |
| **Dentalink: límite de pedidos** compartido por el espejo, el bot y el panel | Limitador común con prioridad para el bot; el espejo se detiene ante un 429 |
| **Datos de salud** (permisos, transferencias, publicidad) | Permisos cerrados por defecto (Anexo B), minimización, abogado antes del espejo, línea de baja y aviso de privacidad |
| **"Dentalink up?" apaga todo el bot** si alguien vuelve a escribir esa clave | Criterio 8 del §4.4; mientras tanto, revisar que nadie la escriba (hoy el Health Check no la escribe) |
| **Fin del soporte en febrero:** nadie clasifica, nadie mira alertas | El valor por defecto es seguro (desconocido = prospecto atendido). Avisos al grupo de la clínica, no solo a vos. Una pantalla para resolver con un toque. Manual. Corte de Dentalink solo con acuerdo de mantenimiento |
| **Supabase gratis como base del historial y de la agenda** | D1 |
| **Un solo dev con varios frentes** | Compuertas, margen del ~17% y orden de lo que se corre (§6) |
| **El número de la clínica es el WhatsApp personal de Irina** (según `current-state.md`; el relevamiento lista "el celular de Irina" como un contacto aparte: hay que aclararlo) | Si es su número personal, su vida privada pasa por el bot y queda guardada. Para la clínica 2, **un número dedicado es requisito del alta** |
| **Evolution es una API no oficial** (riesgo de bloqueo) | Sin envíos masivos; evaluar la API oficial desde la clínica 2 |

---

## Anexo A. Modelo de datos único (para quien lo construye)

**Una sola migración inicial.** Así se evitan los choques entre los 3 diseños: dos `contacto_fichas`, leads por teléfono contra contactos por id, 4 bitácoras y 4 vocabularios de etapas.

- **Contacto** = `pacientes.id`. La tabla `pacientes` se extiende (no se rompe ningún INSERT del v6, del Logger ni del panel) y la vista `contactos` le da el nombre nuevo. Columnas nuevas:
  - `push_name` y `push_name_at`;
  - `origen` y `origen_ref` (anuncio);
  - `primer_mensaje_at`, `primer_mensaje_de` (contacto, clínica o legado) y `ultimo_entrante_at`;
  - `jid_tipo` (generada);
  - `es_prueba` (la mantiene una **lista fija de teléfonos de prueba** que solo cambia por migración, no un clic);
  - `no_contactar_at`.
- **`contacto_roles`:**
  - tipo, subtipo, origen, quién lo puso, desde, hasta, quién lo quitó y clave única (sin duplicados por doble clic);
  - el motivo sale de **una lista corta**, con una nota opcional que va en una **tabla aparte que se puede borrar** (derecho de supresión);
  - triggers: solo se puede cerrar una vez y no se puede borrar.
- **`cola_clasificacion`:** contacto, motivo cerrado, tipo sugerido, referencia a la evidencia (id del mensaje, no copia del texto), origen, prioridad, estado y quién la resolvió. Una sola entrada abierta por contacto y motivo.
- **`eventos`:** una sola bitácora de solo agregar para contactos y leads, con tipo, actor, clave de idempotencia y datos **sin teléfonos ni texto del paciente**. Las citas tienen la suya, `agenda.cita_eventos`, porque espeja el historial de estados de Dentalink.
- **`leads`** (episodios):
  - FK a `contacto_id`, no al teléfono;
  - un solo lead abierto por contacto;
  - cierre: `en_tratamiento`, `perdido`, `no_es_paciente` o `fusionado`;
  - motivo de pérdida y nota;
  - origen y la ficha de descubrimiento (para quién, menor, interés, objeción).
- **`motivos_perdida`:** catálogo editable.
- **Vínculo con la ficha:**
  - **Hasta el espejo:** una vista sobre `recordatorios_enviados` (sin disparador).
  - **Desde el espejo:** `agenda.contacto_fichas`, con FK a `agenda.fichas(id)`, el id de Dentalink como atributo, relación `sin_definir` por defecto y una deduplicación por DNI antes de proponer familiares.
- **Agenda (2027):**
  - `fichas`: DNI único sobre (tipo de documento, número) **después** de una cola de deduplicación; hay documentos extranjeros.
  - `citas`: con `anulada` (booleana, mantenida por trigger: el EXCLUDE no puede leer el catálogo) y `solape_importado` para los solapes históricos, sin marcarlos como sobreturno.
  - Catálogos y recursos: `tipos_turno` (con `es_primera_consulta`), `estados_cita` (id de Dentalink y categoría), `horarios`, `excepciones`, `bloqueo_afectados`.
  - Sincronización: `sync_corridas`, `sombra_diferencias`, `salida_dentalink` (cola de escritura inversa).
  - `config`.
- **Ids:**
  - Las citas espejadas usan el mismo id que en Dentalink.
  - Las nuevas propias arrancan en 10.000.000, y el adaptador traduce esos ids al de Dentalink en los dos modos.
  - El valor `agenda.config.backend` se cachea en Redis y **nunca cambia por defecto** si la lectura falla.

**Reglas del espejo:**
- Si una cita falta en la ventana, se confirma con `GET /citas/{id}` y se marca como desaparecida.
- La simulación excluye el id de la propia cita.
- Lo que entre desde Dentalink en la fase 3 queda "pendiente de revisión".
- La escritura inversa no pisa una cita modificada después de la última lectura, consulta antes de reintentar un POST y manda siempre `flag_notificar_anulacion=0`.

## Anexo B. Permisos de la base (sin esto no se migra nada)

Hoy los permisos por defecto del esquema `public` le dan a `anon` y `authenticated` acceso total a las vistas y funciones nuevas. Las tablas actuales se salvan solo porque tienen RLS activo sin reglas.

En cada migración:
1. Vistas con `security_invoker = true`.
2. `revoke all on function … from public, anon, authenticated`.
3. `alter default privileges … revoke` para los dueños `postgres` y `supabase_admin`.
4. El esquema `agenda` **no se expone** en PostgREST.
5. Un test que llama con la clave anon a cada objeto nuevo y espera que lo rechace.

Además:
- **Rol `bot_n8n`** con EXECUTE solo sobre `contacto_ruta`, `contacto_sugerir`, `contacto_vincular_ficha` y las RPC de agenda. Hoy n8n entra como `postgres` (dueño de todo, salta RLS), así que "el bot solo sugiere" sería solo una convención.
- **El actor de cada cambio** lo fija el panel en la misma transacción (`set_config('app.actor')`) después de verificar la sesión, y las funciones lo leen de ahí.
- **Workflows con datos de pacientes** (espejo, escritura inversa, Recordatorios v2): `saveDataSuccessExecution: 'none'` (es una clave permitida por la regla 4) y vencimiento de ejecuciones en la instancia.
- **Ningún webhook nuevo sin secreto en el header** (P0 abierto).
- **Copias:** en una cuenta de almacenamiento de la clínica, con la custodia de la clave de cifrado documentada. La copia de Nexora se borra al terminar el contrato.
- **Plan de baja de accesos de Nexora en febrero:** panel, Supabase, n8n, Vercel, el grupo y los teléfonos admin.

## Anexo C. Cuestionario único para la clínica (una reunión de ~60 min con la Dra. e Irina)

★ = lo necesitamos antes del 30/10.

**Contactos**
1. ★ ¿Quiénes son el staff completo? (Dra., Irina, la empleada, ¿otros?) ¿Hay otros profesionales con agenda en la clínica (algunos pacientes piden turno "para el Dr. del 1er piso")?
2. ★ El WhatsApp de la clínica, ¿es el número personal de Irina?
3. ★ ¿Quién va a clasificar contactos en el día a día? ¿Desde la computadora o el celular? ¿Irina entra al grupo de derivaciones?
4. ¿Qué colegas, laboratorios y proveedores escriben seguido? (para el directorio)
5. Con un colega que deriva un paciente, ¿alcanza con que el bot calle y el staff lo atienda?

**Primera consulta, devolución y presupuesto**
6. ★ ¿El "puntito amarillo" es exactamente el motivo "Consulta Ortodoncia"? ¿Qué motivo y duración usamos cuando reserva el bot?
7. ★ Si alguien reserva la primera consulta y no paga, ¿qué pasa? ¿Se libera el turno? ¿Con qué plazo?
8. ★ Los controles, ¿se pagan el día de la atención o también por adelantado?
9. La devolución, ¿se agenda en la consulta o cuando tiene los estudios? ¿Cuánto dura? ¿La puede reservar el bot?
10. El presupuesto: ¿quién lo manda y por dónde? ¿Sale de Dentalink? ¿Irina puede marcar "presupuesto enviado"?
11. ¿Se le dice la cuota mensual a alguien que todavía no es paciente?
12. De memoria: ¿cuántas de cada 10 primeras consultas terminan en tratamiento?

**Agenda y Dentalink**
13. ★ ¿Quién pone "Notificado por WhatsApp" (estado 15)? ¿Los pacientes reciben dos recordatorios?
14. ★ ¿Marcan "Atendido" en todas las citas que se cumplen? ¿Y "No asistió"?
15. ¿Cuál es el horario real de la Dra.? ¿Qué turnos duran 20 y 10 minutos? ¿Cuándo usan sobreturno?
16. Las reprogramaciones del bot, ¿prefieren que figuren como "Cambio de fecha" en vez de "Anulado"?
17. ¿Usan en Dentalink historia clínica, evoluciones, odontograma, archivos (escaneos, fotos), presupuestos, caja o pagos, consentimientos o reportes?
18. ¿Qué plan de Dentalink tienen, cuánto pagan, cuándo renueva? ¿Garantiza la exportación completa?
19. ¿Trabajarían en el panel en vez de Dentalink? ¿Cierran o se van de vacaciones en diciembre o enero?
20. ¿Quieren el recordatorio de 24 h además del de 2 días hábiles? (hoy sale uno solo)

**Textos y legal**
21. ¿Aprueban los textos de la oferta, la presentación del anuncio, los seguimientos y el aviso de privacidad?
22. ¿Sirven los motivos de pérdida del §3.4?
23. ¿Tienen la base inscripta en la AAIP? ¿Tienen abogado? ¿Cómo facturan (ARCA)?

**A verificar por nosotros (no hace falta preguntar):**
- qué llega en `tel` para un `@lid`;
- si `POST /citas/changeDate` conserva el id;
- si el filtro `q` acepta `fecha_actualizacion`;
- el tamaño de página de `/sucursales/1/citas`;
- la configuración de notificaciones (`GET /configuraciones`);
- si Dentalink permite usuarios de solo lectura;
- los feriados puente de 2026 y 2027.

## Anexo D. Qué cambió respecto de los diseños, por las críticas

| Crítica | Cambio en este plan |
|---|---|
| Clave publicada | §0, antes que todo |
| Hoy ningún silencio dura más de 1 hora | "Día 1" el 20/10 (§2.6), antes del v7 a todos |
| El v7 no tiene entrada de anuncio | El primer mensaje de anuncio sigue en el v6 hasta que exista la presentación; el piloto es con pacientes con ficha |
| El pago se pide en cualquier reserva | Arreglo en la semana del 13/10 |
| Modelos de datos que chocaban | Anexo A: un solo modelo, una migración, contacto = `pacientes.id`, etapas únicas |
| "Lo inició la clínica" silencia a pacientes reales; origen mal calculado | Solo contactos nuevos, origen desde `n8n_chat_histories`, lo dudoso como `legado` |
| La clínica no usa el panel | 2 pantallas, semana de adopción medida, lo automático no depende de clics |
| `@lid` con celular falso | Verificación y alta sin celular |
| Métrica equivocada; pago no modelado | La métrica principal es la primera consulta realizada; pasos medidos; el pago queda como pregunta ★ |
| Oferta después de Pagos | Eliminada |
| El código pisaba el "no" del modelo | El ruteo por estado queda solo para "no entendí" |
| Información cerca de opinar | Solo el texto literal de la KB |
| Plantilla que invitaba a charlar | "La secretaria le responde por acá" |
| Disparador sobre Recordatorios (NO TOCAR) | Reemplazado por una vista |
| "Entrada cierra ante un error" era falso y peligroso | Se mantiene lo de hoy (deja pasar) con aviso al grupo e interruptor |
| Permisos por defecto abiertos y n8n como `postgres` | Anexo B |
| Espejo con fichas completas sin contrato | Espejo mínimo; los datos sensibles después del contrato |
| Reactivación como publicidad con datos sensibles | Línea de baja en todo, consentimiento y abogado; en 2026, tarjetas manuales |
| OpenAI como receptor no declarado | Incluido en el §4.6; colegas fuera del modelo; precarga sin modelo |
| Escritura inversa no idempotente; rollback con ids mezclados | Criterio 5 del §4.4 y drenaje en el §4.5 |
| "Dentalink up?" apaga el bot | Criterio 8 del §4.4 y riesgo |
| Procesos de fondo nuevos | Un solo workflow de mantenimiento con una señal en el Health Check |
| Fechas irreales (~100 días contra 46) | Roadmap por compuertas con ~38 días hasta diciembre; la agenda propia en sombra en enero y febrero; el corte desde marzo con acuerdo; la clínica 2 en 2027 |
| No es vendible (todo vive en el v6, "Raquel" fijo) | Configuración por clínica, migraciones en el repo del panel, entrada genérica del v7 estimada (D10) |
| Anotador sin retorno hoy | Postergado hasta que se adopte el panel |
| Nombre "Vigía" repetido | "Red de seguridad de silenciados" |

**Lo que se mantiene de los diseños:**
- leer y vincular antes de escribir;
- la sombra en lugar de la doble escritura real;
- la cola de escritura inversa;
- el corte global;
- la historia clínica fuera de 2026;
- `es_primera_consulta` en lugar de leer el texto del motivo;
- la red de seguridad que nunca contesta;
- la oferta armada por código;
- ninguna regex juzgando la intención.
