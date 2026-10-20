# Plan final: Nexora Clínicas

*Fecha: jueves 08/10/2026. Lo escribí a partir del relevamiento de las 4 piezas, los 3 diseños y los 3 veredictos. Corregí los errores de hecho que marcaron los jueces y, donde falta un dato, dejé una pregunta en vez de inventarlo.*

---

## 1. Qué es el producto y por qué se vende

**Nexora Clínicas** es una recepcionista de WhatsApp para consultorios odontológicos. Tiene dos partes:

- **El bot:** agenda, recuerda (24 h y 72 h antes), confirma o cancela, contesta lo de siempre (precio, horarios, dirección, alias) y deriva todo lo demás.
- **El panel:** la secretaria ve en una sola pantalla lo que requiere atención, chatea en vivo, marca a quién no le tiene que hablar el bot (proveedores, laboratorio, equipo) y sigue a cada paciente desde que escribe hasta que está en tratamiento.

**Por qué se vende:**

1. **Turnos fuera de horario y menos ausentes.** Los recordatorios ya funcionan en producción con la Dra. Raquel. Hay que abrir la demo con eso y con números.
2. **El bot no molesta.** El tipo de contacto lo calla con proveedores y equipo, y hay una lista visible de silenciados con quién los silenció y por qué.
3. **La secretaria no se pierde nada.** La bandeja "Requiere atención" reemplaza al grupo de WhatsApp como lugar de trabajo.
4. **Seguridad clínica.** Las urgencias (dolor, sangrado, aparato salido) se detectan por código antes que el modelo, y nunca se dan indicaciones médicas.

> Falta un dato para venderlo: **hoy ningún diseño mide el valor para el dueño.** Antes de la primera demo necesitamos 3 números de Raquel: turnos agendados por el bot fuera de horario, recordatorios confirmados y ausentes antes/después. **Pregunta: ¿tenemos esos datos o los sacamos de la base?**

---

## 2. Sobre qué base se construye

**Recomendación:** el panel que ya anda (`C:\Users\not\Desktop\proyectos\nexora-whatsapp-agent`), sin la marca de Raquel, con **una instancia por clínica** (un Supabase y un deploy por clínica, mismo código). El multi-tenant real (una sola base con tenant_id) queda para cuando haya 4 clínicas pagando o cuando aplicar un arreglo en todas las instancias lleve más de medio día.

**Por qué esta base y no el crm-panel:**
- Es el único panel que hoy funciona con un bot real y una secretaria real.
- La base de Raquel (Supabase v3) pasa a ser *su* instancia, así que su migración no mueve datos.
- El silencio (`bot_silenciado`) vive en la misma base que el v6 ya consulta, entonces el cambio en el bot es de verdad un solo SQL.
- Los datos de salud de cada clínica quedan en su propio proyecto: un error de permisos no expone a una clínica ante otra.
- El crm-panel de mbcell está metido en el negocio de iPhones también en el esquema, no solo en los textos. Nunca se desplegó, su último e2e está en rojo y vos mismo lo llamaste "monstruo al pedo" (mbcell `memory/decisions.md`, 2026-10-08).

### Qué se reutiliza de cada pieza

| Pieza | Se reutiliza | Se tira o se congela |
|---|---|---|
| **Panel de la Dra.** (`nexora-whatsapp-agent`) | Chat en vivo SSE + Realtime (`app/(app)/api/live/route.ts`, `lib/live/*`), envío de texto, imagen y audio con autor, modo humano de 1 h (`lib/modo-humano.ts`), adjuntos, alias, leído/no leído, "Devolver todos al bot", conocimiento editable, directrices, recordatorios como dato (`lib/recordatorios-config.ts`) | Residuo de Chatwoot (`conversaciones/actions.ts:133-237`), página "El agente" (lee el v6), editor de prompts que hace PUT a n8n (`lib/n8n.ts:165/458`), controles duplicados entre /control y /recordatorios, README y migraciones `supabase/0001-0007` de otro producto, dependencias sin uso. La marca, "Jujuy", "Asiri" y los ids fijos pasan a la configuración |
| **crm-panel** (`mbcell-supabase/apps/crm-panel`) | **Ideas y SQL concreto, copiados y adaptados, no el código entero:** `crm.contacto_roles` con historial, motivo obligatorio y precedencia de la más restrictiva (migración 60, L934-1143). También el patrón de silencio decidido en la base, la cola de clasificación, la auditoría de acciones (`core.panel_acciones`) y la batería tipo `rls_verificar` | Unidades, IMEI, cotizador, canje, stock y el resto del dominio iPhone. Para clínicas queda congelado hasta que haya multi-tenant |
| **nexora-agenda** | El patrón anti-solape (`lib/db/migrations/0001_exclusion_constraints.sql`) y la API `/api/v1`, para cuando haya agenda propia | No se despliega en 2026 salvo que aparezca una clínica pagante sin agenda (decisión 3) |
| **Bot** (`raquel-n8n`) | El generador de workflows (`scripts/v7_lib.py`, `crear_v7_en_n8n.py`), el núcleo del v7 que decide por código (`v7/agenda_core.js`, `chequeo_salida.js`) y los escenarios de prueba | Los valores fijos de Raquel pasan a `clinicas/<slug>/clinica.json` |
| **apps/agente** (mbcell) | Nada para clínicas (son solo contratos de tipos, pensados para TrendSpot) | Se commitea para no perderlo y queda fuera de este producto |

---

## 3. Módulos de la v1 (lo que ve una clínica en la demo)

1. **Atención (bandeja "requiere atención")**: es la pantalla de inicio de la secretaria.
   - Tarjetas por tipo: urgencia, pidió una persona, comprobante de pago, no entendió o insiste, conflicto de turno, contacto por clasificar, urgencia de un contacto silenciado, turno pasado sin cerrar.
   - Columnas: Urgencia · Requiere secretaria · En curso · Esperando paciente · Resueltas hoy.
   - Botones a la vista: Tomar, Abrir chat, Esperando al paciente (pausa con tope de 24 h), Resolver con nota.
   - Avisos repetidos del mismo teléfono se suman en una sola tarjeta. Contador en el menú. Se ve bien en el celular.
2. **Conversaciones en vivo**: lo que ya existe, más:
   - Buscador por nombre o teléfono.
   - Filtros con contador: No leídos, Necesitan atención, Humano/Pausado, Por clasificar, Silenciados.
   - Acciones visibles, no escondidas en el clic derecho.
   - Encabezado con motivo y cuenta regresiva ("el bot vuelve en 42 min").
   - Selector de tipo, chips de etiquetas y una franja con las tarjetas abiertas del contacto.
   - Layout de celular. `chat-view.tsx` (2673 líneas) se parte en piezas.
3. **Contactos y pipeline de pacientes**:
   - Etapas: Nuevo → En charla → Agendó → Paciente (asistió) → **En tratamiento**, más **Perdido** (motivo obligatorio) y **Dormido** (sin actividad).
   - El paso de Agendó a Paciente se calcula con la agenda. "En tratamiento" y "Perdido" los marca la secretaria.
   - Embudo del mes e historial de cada contacto.
4. **Silenciados**: quién, cuándo, por qué, fecha de revisión y botón "volver a paciente".
5. **Agenda**: semana y día por profesional, y turnos del paciente dentro del chat. En la v1 es con Dentalink (lectura + alta desde el chat), sin suponer una sola profesional. Recordatorios (on/off, hora, suspensiones) como dato.
6. **Configuración de la clínica**: marca, datos del consultorio, reglas del bot (anticipación, opciones ofrecidas, duración, pago, menores), conocimiento, directrices, teléfonos admin, grupo de derivaciones, usuarios y roles. Unos 25 parámetros a la vista, no los ~260 del crm-panel.
7. **Bot**: prender y apagar con banner global (que también vea el `/bot off`), "Probar el bot" y salud (último mensaje y errores).
8. **Respuestas en sombra** (*nuevo, hoy no existe en ningún panel*): qué habría contestado el bot, mensaje por mensaje. Sin esta pantalla no se puede vender el rodaje en sombra.
9. **Inicio**: turnos de hoy, tarjetas abiertas y vencidas, turnos agendados por el bot, recordatorios confirmados, y modo humano contado con la ventana de 1 h. Hoy `dashboard/page.tsx:134-135` muestra 7 en vez de 0.

**Fuera de la v1:** vision y RAG abierto, varias líneas de WhatsApp por clínica, facturación, obras sociales, app nativa y agenda propia (ver decisión 3).

### Etiquetas y estados: para que el bot no moleste

**Regla de oro:** solo el **tipo de contacto** puede callar al bot. Las etiquetas nunca lo hacen. Hay una única función, `bot_silenciado(tel)`, que devuelve {silenciado, motivo, hasta}. La consultan el bot a la **entrada y a la salida** (dos capas, regla 5), el panel y los recordatorios.

**A) Tipo de contacto** (uno por contacto, con motivo, autor e historial; si hay duplicados gana el más restrictivo):

| Tipo | ¿Habla el bot? | Cómo se asigna |
|---|---|---|
| Sin clasificar (por defecto) | Sí | Aparece en "Por clasificar" |
| Prospecto | Sí | Entra al pipeline |
| Paciente | Sí | Automático si tiene ficha en la agenda. Para pasarlo a un tipo que silencia hay que confirmar dos veces |
| **Tutor/familiar** | Sí | Vinculado a uno o más pacientes (en ortodoncia escriben las mamás) |
| Proveedor / Laboratorio | **No** | Lo pone el staff. El bot solo puede *sugerirlo*, nunca aplicarlo (caso real REAL-08: al proveedor le pasó los datos bancarios) |
| Interno (la Dra., el staff, Nexora) | **No** | Se precarga con los admins. Escribirles no prende el modo humano |
| No paciente / spam / conocido | **No** | Lo pone el staff, con motivo |
| Grupo | **No** | Automático |

- **Red de seguridad:** aunque el contacto esté silenciado, el triaje de urgencias corre igual. No le contesta, pero abre una tarjeta roja y avisa al grupo. Si un silenciado pide turno, también abre tarjeta. *Corrección: la alerta que existe en la migración 60 del crm-panel es por intención de **compra** (iPhone), así que hay que reescribirla para turnos. No está hecha.*
- Cada 90 días se abre la tarjeta "¿sigue siendo proveedor?". Los silenciados no reciben recordatorios.

**B) Estado de la conversación** (es temporal y siempre muestra "hasta cuándo"):
- **Urgencia:** tarjeta abierta, el bot calla 1 h.
- **Pausado esperando secretaria:** tope de 24 h, solo con tarjeta abierta.
- **Humano:** 1 h desde el último mensaje del staff, ya sea desde el panel o desde el celular (regla 7).
- **Requiere secretaria:** el bot sigue respondiendo y la tarjeta espera.
- **Silenciado por tipo:** sin vencimiento.
- **Bot:** normal.
- El **bot apagado global** pisa todo.

**C) Etiquetas libres** (con color, por clínica, nunca silencian): pago pendiente, ortodoncia, menor, lista de espera, VIP, deudor, etc.

**Regla de confianza:** el selector de tipos que silencian **se habilita en el mismo deploy que el gate del bot, nunca antes**. Hasta entonces la secretaria solo clasifica. Así nadie cree que silenció a alguien cuando el bot todavía no lo lee.

---

## 4. Alta de una clínica nueva

**Objetivo:** 1 día hábil de trabajo de Nexora, más 3 a 5 días de sombra y 1 semana supervisada. **Hoy** son 1 a 2 semanas a mano (clonar el v6 y editar regex, prompts e ids). **Mientras no exista el script** (hasta mediados de noviembre), con checklist son unos 2 a 3 días.

1. **Formulario de alta** (30-45 min, la clínica con vos): datos, profesionales, horarios, tipos de turno con duración, precios, alias, reglas (anticipación, menores, pago), número de WhatsApp, grupo de derivaciones, teléfonos admin, token de Dentalink e ids (sucursal, sillón, dentista, códigos de estado), usuarios. Genera `clinicas/<slug>/clinica.json`.
2. **`alta_clinica.py <slug>`** (unas 2 h con el QR). Corre primero en simulación y aplica con `--aplicar`:
   - Crea el Supabase y aplica las migraciones.
   - Siembra configuración, conocimiento y directrices.
   - Crea las credenciales de n8n y genera los workflows de la clínica, mostrando el diff contra lo que hay en vivo y con backup automático.
   - Crea la instancia de Evolution y el webhook.
   - Crea el deploy del panel y da de alta los usuarios.
3. **Precargar silenciados** (30 min): importar proveedores, laboratorio y personal desde los chats o la agenda de la clínica. Es lo que el dueño siente como "no molesta desde el día 1".
4. **Control de calidad** (1-2 h): batería de escenarios con la configuración de la clínica y prueba con un número de prueba (agendar, confirmar, urgencia, proveedor silenciado, modo humano, `/bot off`). **Se limpia todo en el mismo turno** (regla 9).
5. **Sombra** (3-5 días): el bot no envía nada y la clínica ve en el panel lo que habría contestado. **Condición:** antes tiene que estar desplegado el arreglo que obliga a escribir solo en modo vivo. El 06/10 la sombra del v7 confirmó 11 citas reales en Dentalink, y ese arreglo figura como "falta desplegar" (`raquel-n8n/memory/current-state.md` L2792-2797).
6. **Vivo supervisado** (1 semana): en horario de atención, con vos mirando la bandeja.

---

## 5. Cómo migra la Dra. sin cortar su servicio

Principio: no se mueven datos. Su Supabase v3 **es** su instancia, Dentalink sigue siendo su agenda y el webhookId `evo-webhook-v2` no se toca. El workflow de Recordatorios (`7RqTApkvVavRmq3R`) no se toca. Todo cambio en n8n lleva tu OK, backup, diff y `check_triaje.py`.

1. **09/10.** Commit y deploy de `lib/modo-humano.ts` y arreglo del KPI de modo humano en su panel actual. No toca n8n.
2. **19-23/10. Migraciones solo aditivas en su v3:** tablas de casos, eventos, etiquetas, tipo de contacto, configuración y `bot_silenciado`. Primero se prueban en un clon con backup del esquema. Nada frena los inserts que ya hace el v6.
   - La bandeja se alimenta de lo que el bot **ya escribe** en la base (escalaciones y triaje), con disparadores en la base, sin tocar n8n. **Pregunta: hay que verificar que esos logs alcancen.**
   - *Corrección al diseño 2:* si hiciera falta que notify-grupo cree la tarjeta, eso **sí** es tocar el bot. notify-grupo es un workflow n8n del v6 (`workflows/current/helper_notify_grupo_S5U6tSipzlgFHCkf.json`) y necesita PUT con backup y diff.
3. **Desde el 23/10. Panel nuevo en paralelo,** en otra URL, contra el mismo v3, con la marca Áurea desde la configuración. Irina usa la bandeja y clasifica contactos, y el panel viejo sigue vivo. A los 5 días hábiles sin problemas se cambia el dominio y el viejo queda archivado (se puede volver a desplegar).
4. **Semana del 02/11, con tu OK. Gate de silencio en el v6:** solo cambia el SQL de "Consultar Takeover Paciente" y "Gate Humano Final" para que use `bot_silenciado`, con el mismo nombre de campo. El fromMe deja de actuar sobre contactos internos y grupos.
   - Prueba con tu celular marcado como proveedor: el bot calla; si escribís "dolor", se abre una tarjeta; lo volvés a paciente y el bot contesta. Al terminar se limpia con `limpiar_numero_demo.py`.
   - **En ese mismo deploy** se habilita el selector de proveedor.
   - Rollback: un PUT con el backup de `workflows/history/`.
5. **Corte v6 → v7:** sigue su propio plan (`docs/plan-conexion-v7-celular-lucas-2026-10-06.md`, 27 cambios) y queda **fuera del camino crítico de la venta**. Antes hay que cerrar los P0 abiertos (`memory/backlog.md` L510-511).

---

## 6. Roadmap con fechas

*Ojo con los feriados: 12/10, 20/11 (o su traslado) y 08/12 pueden caer en semanas de entrega. **Pregunta: ¿se trabaja esos días?***

| Semana | Entrega | Qué se ve |
|---|---|---|
| **Jue 08 – vie 09/10** | **Decisiones y piso firme.** Firmás las decisiones de la sección 7 (no se dan por firmadas hoy). Commit y deploy del modo humano y del KPI en el panel de Raquel. Commit con mensajes reales de lo que está sin trackear en mbcell (126 archivos, incluidos apps/agente, el e2e y la migración 80). Dump limpio del esquema v3 como base de las migraciones. Pedir una cuenta demo de Dentalink y un número de WhatsApp de demo | El KPI de modo humano en 0 en el panel de Raquel |
| **12 – 16/10** | **Demo navegable.** Panel sin la marca de Raquel (todo sale de la configuración). Supabase demo con unas 40 conversaciones sintéticas. Bandeja, tipos de contacto (solo clasificar), buscador, filtros | **Vie 16/10:** demo navegable en una URL de demo, sin pacientes reales, para mostrar por videollamada |
| **19 – 23/10** | **Celular + pipeline + Raquel adentro.** Layout de celular, pipeline con embudo, Silenciados. Migraciones aditivas en el clon y después en el v3 de Raquel. Panel nuevo en paralelo para Irina | Irina trabaja las derivaciones reales desde la bandeja: es la prueba social, mostrada en video o capturas **anonimizadas**, nunca en vivo con datos de Raquel |
| **26 – 30/10** | **Demo de punta a punta con bot**, en el número de demo contra la cuenta demo de Dentalink. El bot de la demo usa la entrada que ya existe (el v6 generado con slug), **no** una entrada nueva escrita de cero. `bot_silenciado` en entrada y salida. Desplegar el arreglo de sombra del v7, con tu OK | **Vie 30/10:** recorrido grabado de 5 min: un prospecto agenda, el turno aparece en la agenda, se lo marca proveedor y el bot calla, escribe "dolor" y aparece una tarjeta roja. Desde acá, demos en vivo |
| **02 – 06/11** | **El bot de Raquel obedece las etiquetas** (gate en el v6 con tu OK, selector habilitado en el mismo deploy). Precarga de proveedores y laboratorio de Raquel. Arranca el login por usuario | Raquel: el bot deja de contestarle a proveedores |
| **09 – 13/11** | **Listo para cobrar.** Login por usuario con roles (Supabase Auth en cada instancia) y auditoría de quién hizo qué. Clave propia del bot por instancia en lugar de la service key. Secreto por clínica en los webhooks. Anexo de datos (Ley 25.326). Pantalla de respuestas en sombra | Panel con usuarios propios por clínica |
| **16 – 20/11** | **Alta repetible.** `alta_clinica.py` (generar, diff, aplicar, backup) y formulario de alta. Batería de calidad con la configuración de cada clínica | Una clínica de prueba dada de alta en 1 día |
| **23/11 – 18/12** | **Clínica 2 piloto** (si cierra una demo): sombra desde el 23/11, después supervisado. Sale en vivo con el bot que Raquel tenga **estable en producción** en ese momento. El v7 no sale en vivo en la clínica 2 hasta que lleve 2 semanas estable con Raquel | Clínica 2 en sombra o supervisada. Fecha comprometida para clínica 2 con respuestas activas: **2.ª semana de enero de 2027** (hay margen si se adelanta) |
| **Noviembre, en paralelo, sin fecha comprometida** | Corte v6 → v7 de Raquel según su plan | — |
| **Enero 2027 en adelante** | Agenda propia si hay clínicas sin Dentalink. Multi-tenant cuando haya 4 clínicas pagando o los arreglos en N instancias pasen de medio día (unas 4-6 semanas) | — |

---

## 7. Decisiones que tenés que tomar (con mi recomendación)

1. **Base del producto:** panel de la Dra. o crm-panel. → **Panel de la Dra.** El crm-panel se commitea, queda congelado para clínicas y sirve como fuente de SQL y patrones.
2. **Aislamiento:** una base por clínica ahora, o una base compartida con tenant_id. → **Una por clínica ahora; multi-tenant con 4 clínicas pagando.**
   - Hay un hueco a declarar: si todas las clínicas nuevas comparten un n8n y un Redis de Nexora, en el camino del bot el aislamiento es por convención, no por infraestructura.
   - **Recomiendo** n8n compartido con credenciales y prefijos por clínica, dejarlo escrito, y ofrecer n8n dedicado a quien lo exija.
3. **Agenda:** solo Dentalink en 2026, o también agenda propia. → **Solo Dentalink en 2026.** La agenda propia, en 2027 o cuando aparezca una clínica pagante sin agenda, y al principio con supervisión. **Pregunta: ¿Dentalink da cuentas demo?** Si no, la demo de punta a punta necesita otro plan.
4. **Con qué bot sale la clínica 2:** el que Raquel tenga estable en producción. → **Sí.** El v7 entra en una clínica nueva recién con 2 semanas estables en Raquel.
5. **Precio:** alta + abono mensual. → Hay que fijarlo **antes del 30/10**, cubriendo por clínica Supabase, deploy, Evolution, consumo del LLM y soporte. **Pregunta: no hay ninguna cifra en la memoria; la tenés que poner vos.**
6. **A quién se le muestra la demo:** el borrador habla de "3 clínicas" y en la memoria no hay ningún registro de eso. **Pregunta: ¿quiénes son y en qué estado está cada una?**
7. **Quién usa el panel día a día** (¿Irina desde el celular?). Define si en la semana del 12/10 va primero el celular o la bandeja en escritorio.
8. **Dónde se guardan los datos de salud** (región de Supabase y Vercel) para el anexo de la Ley 25.326. → Que el anexo diga dónde se guardan los datos y que incluya la transferencia internacional si queda fuera de Argentina.
9. **nexora-agenda:** → archivarlo como referencia y no desplegarlo en 2026.

---

## 8. Riesgos

1. **Romper a Raquel mientras se hace producto.** Es el único servicio en producción y la confianza ya se quebró una vez (Mariela, 09/05; confirmaciones en sombra, 06/10). → Migraciones solo aditivas probadas en un clon; gate con tu OK, backup, diff y `check_triaje.py`; nada de PUT desde el panel; el corte al v7 fuera del camino crítico.
2. **"Sombra" que no es sombra.** Hoy no es segura: el 06/10 escribió en Dentalink. → No se vende ni se usa ningún rodaje hasta desplegar el arreglo y tener la pantalla de respuestas en sombra.
3. **El v7 todavía se equivoca.** 4.ª corrida (08/10): 9 bien, 4 con detalles, 3 mal, con P0 sin desplegar. → Demo con guion sobre casos cubiertos y chequeo de salida activo. El v7 no va en vivo en una clínica nueva antes que en Raquel.
4. **Silenciar a un paciente por error,** sobre todo a un familiar. → Doble confirmación si tiene ficha, motivo obligatorio, lista de Silenciados visible, revisión a 90 días y triaje de urgencias que corre igual.
5. **Falsa sensación de control.** → El selector de silencio sale en el mismo deploy que el gate del bot.
6. **Datos reales en la demo.** → Solo datos sintéticos y un número propio. *Corrección:* el webhook "solo-Lucas" protege el entorno de Raquel, no un número de demo nuevo; hay que replicar esa protección.
7. **Deriva entre instancias.** Un arreglo hecho en una clínica y no en otra. → Un solo repo, migraciones aplicadas por script a todas (con registro de versión por instancia), workflows generados y nunca editados en la UI de n8n, y el generador avisa si lo que está en vivo difiere.
8. **Permisos flojos para datos de salud.** La cookie compartida y los usuarios en variables de entorno no alcanzan. → Login por usuario con roles y auditoría **antes** de la primera clínica pagante (semana del 09/11), y una clave propia del bot en lugar de la service key.
9. **Fechas apretadas para un solo dev con tres frentes** (producto, corte v7, soporte de Raquel). Los más justos son la semana del 12/10 y la del 26/10. → Entregas semanales que sirven solas; si algo se corre, se corre la clínica 2, no la calidad. Plan C para el 30/10: demo navegable + bot en sombra grabado.
10. **Dependencias externas.** Dentalink (límites de uso, códigos de estado distintos por cuenta: 1/14/18 en Raquel) y Evolution, que es WhatsApp no oficial con riesgo de bloqueo. → Mapeo de estados en la configuración y prueba automática al dar de alta; un número por clínica, sin envíos masivos; la API oficial de WhatsApp queda como opción.
11. **Dos líneas de producto compitiendo** (crm-panel/TrendSpot y Clínicas). → Queda escrito que, para clínicas, el crm-panel es fuente de patrones hasta el multi-tenant.

---

### Errores de los borradores que ya corregí en este plan

- **El crm-panel no tiene un rol "profesional".** Sus roles son dueño, vendedor y operador, y no existe la entidad profesional.
- **La alerta "silenciado pide turno" no existe.** La de la migración 60 es por intención de compra.
- **El plan de migraciones del diseño 1 no cierra.** "Copiar las migraciones 00-60 y 70-75" traía la gestión iPhone y dejaba afuera los permisos (90, 91, 95).
- **El v6 no puede consultar otra base "con un solo SQL".** Ya no aplica, porque `bot_silenciado` vive en el v3.
- **En el v3 la seguridad por filas ya está activa, pero sin reglas.** El trabajo real es escribir esas reglas, no "activarla después".
- **No hay "DEFAULT clinica_id = Raquel".** Ese default fallaba abierto: cualquier olvido escribía en Raquel. Con una base por clínica no hace falta.
- **No hay demo en vivo con datos de Raquel.**
- **No hay workflow de entrada nuevo del v7 para la demo.**
- **El 10/10/2026 cae sábado.** La semana 0 termina el viernes 09/10.