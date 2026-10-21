# Auditoría del panel — 20/10/2026

Panel: `nexora-whatsapp-agent`, `main` = 6682894 (lo desplegado hoy). Cambios en la rama local `panel-limpio` (sin push ni deploy).
Pedido de Lucas: "enlatado 100% premium y funcional: que todo lo que está en el panel sirva y ande, sin ambigüedades".
Contexto: desde el 20/10 todos los pacientes los atiende Asiri v7 (orquestador + sub-agentes), que lee `knowledge_base` **por id fijo** y dos directrices.

Cómo se verificó: lectura del código de las 11 secciones; consultas de **solo lectura** al Supabase v3 (esquema, conteos y textos de la KB, sin datos de pacientes); GET de solo lectura a la API de n8n (workflows, webhooks, ejecuciones de Recordatorios); 4 GET de solo lectura a Dentalink (orden y filtros de `/citas`); prueba local del panel con el login de desarrollo y datos inventados (modo demo, 39/39 chequeos con Playwright a 1440 y 390 px). Ninguna escritura en Supabase, n8n, Dentalink ni recordatorios.

## 1. Veredicto en una tabla

| Sección | Veredicto | En una línea |
|---|---|---|
| Dashboard | SE ARREGLA | Contaba los mensajes del equipo como "del bot" (681 de 775 en 7 días) y la autonomía salía inflada (72 % → 51 % real). Corregido y renombrado. |
| Conversaciones | QUEDA | Lee el v3 en vivo y escribe por los webhooks `panel-toggle-bot` / `panel-send-human`, que existen y están activos. |
| Atención | QUEDA | Bandeja sobre `casos` (10 abiertos hoy); se ve solo con `ATENCION_BANDEJA=1`. |
| Seguimientos | QUEDA | Solo lectura (`panel_seguimientos_citas`); se ve solo con `SEGUIMIENTOS=1`; textos pendientes de la Dra. |
| Citas | SE ARREGLA | Traía las primeras 400 citas por id descendente: faltaban turnos (septiembre: 125 de 228). Ahora completa desde el 1.º del mes. |
| Recordatorios | QUEDA (+ dato real) | Funciona (gate, suspensión y "adelantar" existen en el workflow). Suma la hora REAL de la última corrida. Es el único lugar donde se manejan. |
| Conocimiento | SE ARREGLA y absorbe Servicios | Una sola sección: crear / editar / archivar / eliminar, marca "Lo usa Asiri", 23 entradas protegidas, guarda de precios y de datos bancarios. |
| Servicios | SE FUSIONA | Era la misma tabla filtrada. `/servicios` redirige a Conocimiento. Su "probar el bot" estaba roto desde SEG-06 y se quitó. |
| Aprendizaje | SE QUITA | Prometía "cargalo en Conocimiento y la próxima lo resuelve sola": con el v7 es falso. `/aprendizaje` redirige a Atención (o Dashboard). |
| El agente | SE QUITA → "Asiri" | Mostraba y editaba los prompts del v6, que no atiende a nadie (BOT-14). Reemplazada por `/asiri`: estado medido, interruptor en lectura y las 2 directrices. |
| Control | SE ARREGLA | Queda solo el interruptor de emergencia (con una confirmación que dice lo que de verdad pasa); el switch duplicado de recordatorios pasa a ser un enlace. |

Además (transversal): a 390 px la barra lateral de 256 px dejaba ~134 px para el contenido en todas las pantallas viejas. Ahora la barra lateral es solo de escritorio y en el celular todas las pantallas tienen la barra inferior de la bandeja (sin scroll horizontal en ninguna, medido).

## 2. Hallazgos que cambian algo para los pacientes o la clínica

1. **El menú de bienvenida del panel NO lo usa Asiri.** El texto guardado en `agente_directrices.menu_bienvenida` dice "cuotas" y "En qué puedo ayudarle hoy?"; el v7 (`menuValido`, `v7/orquestador_core.js`) lo descarta en silencio y manda su menú estándar. El panel no avisaba nada. Ahora la pantalla Asiri lo dice ("Hoy Asiri NO usa este texto") y no deja guardar un menú que el v7 descartaría.
2. **Una entrada nueva de Conocimiento no le llegaba a Asiri.** El v7 leía solo los ids de `SQL_DATOS` (20, 21, 24, 25, 36, 39, 40 + KB_EXTRA) y el panel decía "lo que edités acá, Asiri lo empieza a usar al instante" en todas. Cerrado (21/10) en dos partes: el v7 ahora también lee las entradas con `metadata->>'asiri' = 'true'` no archivadas (hasta 12, las de id más bajo, recortadas a 600 caracteres, como datos de Información), y el panel tiene el interruptor "Asiri puede decírselo a los pacientes" en las entradas no fijas.
3. **"Probar el bot" (en Servicios) no funcionaba desde el 20/10 17:00**: postea al webhook sin `instanceToken` y el "Webhook Validator" (SEG-06) lo descarta; el probador esperaba 45 s y no mostraba nada. Además pegaba al bot real (con el v7 para todos, podía avisar al grupo: BOT-05). Se quitó.
4. **La agenda del panel estaba incompleta.** `/citas` de Dentalink sin filtro viene ordenado por id descendente (lo más recién creado primero); el panel pedía 8 páginas y recortaba. Medido contra la copia del 20/10: octubre 187 de 192, septiembre 125 de 228. Verificado contra la API: Dentalink acepta un solo operador por campo (`{"fecha":{"gte":…,"lte":…}}` se ignora entero) y el cursor `links.next` conserva el filtro.
5. **Dashboard**: en 7 días, de 775 mensajes "assistant" 681 eran del equipo (`wa_outbound`), 75 del bot anterior y 16 de Asiri v7. "Conversaciones activas" contaba 94 chats; con mensaje de paciente hay 53. La insignia "Humano" de "Últimas conversaciones" miraba solo el flag (106 pacientes con el flag en true; 0 vigentes con la regla del bot de 1 h).
6. **Horario de recordatorios**: el cron es `0 13 * * 1-5` sin zona horaria en el workflow; las corridas reales salen a las 11:00 UTC = **08:00 de Jujuy** (no 9, como dice el CLAUDE.md del repo). Si la zona del servidor de n8n tiene horario de verano, la hora real cambiaría sola; por eso Recordatorios y Control ahora muestran la hora real de la última corrida en vez de calcularla.
7. **Precios**: ninguna entrada vigente de la KB tiene montos de cuota mensual o retenedor (se corrieron las 44 contra la guarda nueva: 0 bloqueadas). El único resto es la palabra "cuotas" en el menú del punto 1, que el v7 ya ignora.

## 3. Sección por sección

### Dashboard (`/dashboard`)
- Muestra: KPIs del rango (24 h / 7 / 30 días), gráfico de mensajes por día y últimas 5 conversaciones.
- Lee: `conversaciones`, `escalaciones_log`, `recordatorios_enviados`, `pacientes` (v3). No escribe.
- Punta a punta: sí, los datos están frescos (último mensaje 22:02 UTC del 20/10). Lo roto era el cálculo.
- Arreglado: el gráfico separa Paciente / Asiri / Equipo (por `metadata.source`); "Conversaciones con pacientes" = chats con al menos un mensaje del paciente; "Resueltas por Asiri" = de esos, los que no terminaron en un aviso al grupo; "No-shows evitados" pasa a "Turnos confirmados por WhatsApp" (era un número de confirmaciones, no de faltas evitadas); "Escalaciones" pasa a "Avisos al grupo"; la insignia del equipo usa la misma regla que el bot (`esModoHumano`). Con datos reales de 7 días: 53 conversaciones, 51 % resueltas por Asiri.
- Pendiente (no se tocó): ATE-07 ("Hoy" para la Dra.) sigue en el backlog.

### Conversaciones (`/conversaciones`)
- Muestra: lista estilo WhatsApp con buscador (ATE-04), chat, tipo de contacto, turnos del paciente, envío de texto/imagen/audio, modo humano.
- Lee: `conversaciones`, `n8n_chat_histories`, `mensajes_entrantes_live`, `media_entrantes`, `pacientes`, `recordatorios_enviados` (v3); turnos por Dentalink.
- Escribe: n8n `panel-toggle-bot` y `panel-send-human` (workflow "Panel — acciones staff", activo, con secreto), `pacientes` (alias, leído), RPC de tipos de contacto, y Dentalink (crear/confirmar/anular/reprogramar con confirmación).
- Veredicto: QUEDA. No se modificó (solo el texto "El agente no puede…" → "Asiri no puede…").

### Atención (`/atencion`) y Seguimientos (`/seguimientos`)
- Atención: bandeja sobre `casos` (aplicada el 20/10, 10 casos "nuevo" hoy); acciones con el mismo camino del switch del chat. Seguimientos: dos listas de a uno, sin envíos, sobre `panel_seguimientos_citas`.
- Ambas existen solo con su flag (`ATENCION_BANDEJA`, `SEGUIMIENTOS`) en `/opt/nexora-panel/.env.production`. Sin flag, la ruta da 404 y no aparece en el menú.
- Veredicto: QUEDAN. No se modificaron.

### Citas (`/citas`)
- Muestra: calendario mensual de Dentalink, solo lectura, con marcas de recordatorio enviado / confirmó / canceló.
- Lee: Dentalink `/citas` + `recordatorios_enviados` (v3).
- Arreglado (AGE-01): `listCitasDesde(1.º del mes)` con `q={"fecha":{"gte":…}}`, sigue el cursor hasta el final (tope 20 páginas, ~6 hoy) con caché de 60 s (varias personas mirando no multiplican los pedidos, que comparten el límite con el bot). Si Dentalink tuviera más páginas que el tope, aviso "puede faltar alguno". Los meses anteriores muestran "se ven en Dentalink". Se borró `listAllCitas` (el que truncaba).

### Recordatorios (`/recordatorios`)
- Muestra y hace: prender/apagar el workflow, hora de envío (PUT del cron al workflow 7RqTApkvVavRmq3R), suspender un día / un rango (`recordatorios_config`, que el nodo "Gate - Leer config" del workflow lee en cada corrida), y "adelantar" (webhook `trigger-recordatorios-manual`, existe y está activo).
- Veredicto: QUEDA. Agregado: "Última corrida automática: …" con la hora real (GET de ejecuciones de n8n). El workflow NO se tocó.
- Riesgo a saber: cambiar la hora desde el panel hace un PUT al workflow de Recordatorios (regla "NO TOCAR" del proyecto). Es una función que ya estaba en producción; no se probó de punta a punta en esta auditoría para no escribir.

### Conocimiento (`/conocimiento`) — fusiona Servicios
- Lee y escribe `knowledge_base` (v3). 44 entradas hoy; 23 las lee Asiri v7.
- Qué hace ahora:
  - Filtros "Todas / Lo usa Asiri / Solo referencia / Archivadas", búsqueda sin tildes, grupos con nombre para la secretaria (Precios y pagos, Horarios y dirección, Turnos y políticas, Tratamientos, Presentación y trato, Otros). Las categorías viejas duplicadas (pago/pagos, ortodoncia/tratamientos, agendar) se muestran pero no se ofrecen para entradas nuevas; el dato guardado no se renombra.
  - Cada entrada que usa Asiri dice cómo la usa (por ejemplo, la 24: "la pega tal cual debajo de un pago o una reserva").
  - **Protegidas (no se archivan ni se borran ni cambian de categoría; sí se editan):** las 23 que lee el v7 — 1, 3, 20, 21, 22, 23, 24, 25, 26, 28, 29, 30, 32, 33, 36, 37, 39, 40, 41, 42, 43, 44, 45. Por qué: el v7 las lee por id; si una se borra o archiva, Asiri pierde ese dato sin aviso (la 24 = alias y CBU, la 21 = precio y saludo de los anuncios, la 20 = horarios, la 25 = dirección, la 36/39 = "la cuota y el retenedor los informa la secretaria"). La regla vive en el server (las acciones rechazan), no solo en la pantalla.
  - **KB 24 (datos para transferir):** se valida con las MISMAS regex que `datos_pago` del v7; sin "Alias:" o sin "CBU:" (22 números) no se guarda, con un error que dice qué falta; si falta Titular / CUIT / cuenta / Banco avisa que Asiri lo va a omitir; vista previa "Así lo pega Asiri".
  - **KB 21 (primera consulta):** la primera frase tiene que tener el precio con $ (la usa el saludo de los anuncios, BOT-06); vista previa del saludo.
  - **Guarda de precios (BOT-04):** por WhatsApp solo el valor de la consulta. Se rechaza, oración por oración, un monto junto a cuota mensual / por mes / retenedor / contención, o cuyo contexto más cercano sea un tratamiento (brackets, alineadores, tratamiento, presupuesto, control). "La primera consulta tiene un valor de $50.000" pasa. Mensaje claro con cómo reescribirlo. Las 44 entradas vigentes pasan.
  - **Archivar** = `metadata.archivado = true` + `embedding = NULL`; **Restaurar** lo revierte; **Eliminar para siempre** solo desde Archivadas (dos pasos). Sin columna ni tabla nueva.
  - Cada guardado deja `metadata.editado_por` / `editado_at` (se muestra "editado 20/10 por …").
- Embeddings (decisión): Asiri v7 NO usa búsqueda por similitud (lee por id), así que el embedding no hace falta para Asiri. El bot anterior (v6) sí busca con `match_documents` (herramienta `buscar_conocimiento`) si alguna vez se vuelve a él (`v7_global --off` o un número excluido). Por eso el panel lo sigue regenerando **de mejor esfuerzo y en silencio** con la misma receta que `apply_precios_solo_consulta.py` ("categoria | titulo\ncontenido", text-embedding-3-small, 1536): si falta `OPENAI_API_KEY` u OpenAI falla, se guarda igual, se conserva el embedding anterior y no se le muestra nada a la secretaria. Archivar pone el embedding en NULL porque `match_documents` descarta `embedding IS NULL` (el v6 deja de encontrarla).
- Probado en local (modo demo): crear → queda "Solo referencia"; archivar → restaurar/eliminar; la 24 sin alias bloquea; la 36 con "$70.000" bloquea; 390 px sin scroll horizontal.

### Servicios (`/servicios`)
- Era una vista de `knowledge_base` por categorías (precios, pagos, tratamientos…) con las mismas acciones de Conocimiento, más "Probar el bot".
- Su ayuda decía que la cuota mensual se podía publicar (contradice la decisión del 16/10).
- Veredicto: SE FUSIONA en Conocimiento (los mismos datos, con grupos). `/servicios` redirige. Se borraron `servicios-editor`, `bot-tester`, `lib/servicios.ts` y `lib/test-bot.ts`.

### Aprendizaje (`/aprendizaje`)
- Mostraba las escalaciones de la semana agrupadas por tema con "Cargar al Conocimiento".
- Con el v7 la promesa es falsa (punto 2 de §2) y los mismos avisos ya están, mejor, en la bandeja de Atención. Mostraba motivos de escalación en texto libre.
- Veredicto: SE QUITA. Redirige a `/atencion` (o `/dashboard` si la bandeja está apagada). Se borró `lib/escalaciones.ts`.

### El agente (`/agente`) → Asiri (`/asiri`)
- Mostraba la "arquitectura" del v6 leída de n8n (Recepción, Sub-Agent General/Agendar/Confirmar…) y dejaba a un admin editar sus prompts con PUT al v6. Desde el 20/10 esos prompts no atienden a nadie (BOT-14) y el editor era un PUT al workflow vivo desde el panel.
- Veredicto: SE QUITA y se reemplaza por **Asiri**: (a) quién respondió en las últimas 24 h, medido en la memoria del bot por la marca de origen (`asiri_v7` / triaje / bot anterior; hoy 16 de Asiri v7, 0 del anterior); (b) interruptor de emergencia en **solo lectura** (se cambia en Control); (c) chats atendidos por el equipo ahora; (d) "Qué hace Asiri" en 4 líneas; (e) las dos directrices que sí lee el v7 (`menu_bienvenida`, `notas_para_asiri`), editables con historial, con la regla `menuValido` del v7 y la guarda de precios. `/agente` redirige. Se borraron `prompt-actions`, `agente-view`, `prompt-editor`, `lib/prompt-guard.ts` y `getAgenteArquitectura`/`setSubAgentePrompt` de `lib/n8n.ts`.

### Control (`/control`)
- Hacía: prender/apagar el workflow del bot (v6, que recibe los mensajes) y, otra vez, prender/apagar y programar los recordatorios (duplicado de Recordatorios).
- Veredicto: SE ARREGLA. Queda solo el interruptor de emergencia. La confirmación ahora dice lo que pasa de verdad: nadie recibe respuesta automática (tampoco el triaje), y los mensajes que entren mientras esté apagado **no aparecen en Conversaciones** (el registro lo hace el mismo workflow) — se ven solo en el celular de la clínica. Sugiere el modo humano para un solo chat. Los recordatorios se ven como estado (con la última corrida) y enlazan a Recordatorios. El aviso rojo global pasó a "Asiri está APAGADA…", sin emoji.

## 4. Archivos y commits (panel, rama `panel-limpio`)

Nuevos: `lib/conocimiento/{reglas,fuente,demo}.ts`, `lib/asiri/{estado,origen}.ts`, `lib/demo.ts`, `app/(app)/asiri/{page,actions}.ts(x)`, `components/conocimiento/conocimiento.tsx`, `components/asiri/directrices-editor.tsx` (movido), `components/barra-celular.tsx`, `tests/conocimiento.test.mjs` (12 tests; compara las listas, las regex de la KB 24 y el menú estándar con este repo cuando está al lado).
Modo demo para probar sin tocar la base: `PANEL_DEMO=1` con `next dev` (nunca en producción).

## 5. Qué falta / riesgos

- **Deploy** (lo hace Lucas: `bash deploy/redeploy.sh`). No requiere variables nuevas. Después: abrir Conocimiento, editar una entrada de referencia y volverla a su texto; mirar /asiri.
- **Menú de bienvenida**: la clínica (o Lucas) tiene que guardar un menú que Asiri use (botón "Cargar el menú estándar en el editor" → Guardar), o dejarlo así sabiendo que sale el estándar.
- **Entradas marcadas para Asiri (21/10):** interruptor "Asiri puede decírselo a los pacientes" en crear/editar de las entradas NO fijas → `metadata.asiri = true/false` (el resto de metadata se conserva). Con el interruptor: máximo 600 caracteres, tope de 12 marcadas (error claro), la guarda de precios de siempre y la ayuda "no cambia cómo agenda ni lo que deriva". Llevan el sello "Lo usa Asiri" con contorno (las fijas, con candado) y sí se archivan o eliminan; archivada, la marca no tiene efecto, y al restaurar vuelve marcada solo si hay lugar. La marca sirve recién cuando estén desplegados los dos lados (v7 y panel). Información sigue respondiendo solo su lista cerrada de temas.
- **Drift con el bot:** la lista de ids protegidos, las regex de la KB 24, el menú estándar y `KB_ASIRI_MAX` / `KB_ASIRI_LARGO` están copiados en el panel. El test los compara con este repo si está al lado; si cambia `v7_workflow_cerebro.py` u `orquestador_core.js`, hay que actualizar `lib/conocimiento/reglas.ts`.
- **Guarda de precios:** es por palabras (validación del texto de la clínica, no del paciente). Falso positivo conocido: "La consulta para brackets cuesta $50.000" (pide reescribir "La consulta cuesta $50.000 …"). Falso negativo posible: un monto suelto sin ninguna palabra de contexto en la frase ("Sale $70.000.") pasa.
- **Archivar** usa `metadata` (no hay columna `archivado`): cualquier script que lea `knowledge_base` entero debería filtrar `metadata->>'archivado'`. Hoy solo el panel y `match_documents` (que ya descarta por embedding NULL).
- **Interruptor de Control** apaga el workflow entero del v6 (incluido el registro de mensajes); para un problema puntual conviene `/bot off` por WhatsApp o el modo humano. No se cambió el mecanismo.
- **Mobile:** la barra inferior en todas las pantallas es el paso mínimo; MOB-01 (estructura responsive completa) sigue en el backlog.
