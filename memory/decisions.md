# Decisiones — raquel-n8n

_Append-only, la más nueva al final._

## 2026-07-06 — Precio: reemplazar TODOS los "40" de montos, no solo los canned
**Decisión**: al subir la consulta a $50.000, cambiar también los ejemplos few-shot
(Formatting Agent) y los ejemplos de formato de monto del analizador de comprobantes
(`$40.000`, `40000`, `$ 40.000,00` → todos a 50).
**Razón**: pedido explícito de Lucas — "donde leas 40 lo cambiás por 50, punto; se puede
confundir el LLM". Cero números viejos a la vista del modelo.
**Alternativa descartada**: cambiar solo los 4 canned reales (más purista, pero deja
$40.000 dando vueltas en prompts).
**Revisable**: sí, próximo cambio de precio usar el mismo criterio.

## 2026-07-06 — Fix @lid por cadena de candidatos con fallback idéntico al legacy
**Decisión**: extraer phone con el primer candidato que termine en `@s.whatsapp.net` entre
`remoteJid → remoteJidAlt → senderPn → participantAlt → participant`; si ninguno, devolver
EXACTAMENTE lo que devolvía el código viejo (cero cambio de comportamiento en el peor caso).
**Razón**: evidencia forense (527 execs) + código fuente Evolution 2.3.7 + doc Baileys v7.
El fallback idéntico garantiza no-regresión; las sesiones @lid quedan aisladas (no se mezclan).
**Alternativas descartadas**: (a) strippear `@lid` — los dígitos del LID NO son el teléfono;
(b) devolver phone vacío si no hay teléfono — `lk=""` en Dentalink podría matchear todo, y
colapsaría sesiones de memoria de todos los @lid en una sola (gravísimo).
**Revisable**: cuando se implemente la tabla de mapeo lid↔teléfono (Fase 2).

## 2026-07-06 — Kill-switch: cadena LID solo-DM (sin participant*)
**Decisión**: en el Kill-switch Check la cadena excluye `participant/participantAlt`.
**Razón**: incluirlos habilitaría `/bot off` desde el grupo de escalaciones, que hoy no
funciona y nadie pidió — no cambiar semántica sin pedido. Verificado con mensaje real de
grupo (exec 193150) que sigue ignorado.
**Revisable**: si la Dra./Lucas quieren comandar el bot desde el grupo, agregar los candidatos.

## 2026-07-06 — Guard fail-closed para @lid sin teléfono: NO por ahora
**Decisión**: no aplicar el guard "si el phone no resuelve → bot mudo + aviso al grupo",
pese al caso real exec 193142 (bot saludó en chat atendido por staff).
**Razón**: Lucas dice "tranqui" — la política de la Dra. es que el bot siempre se presente
como bot; prefieren bot presente a bot mudo. Queda en backlog como opción.
**Revisable**: sí — si se repite la interferencia en chats atendidos y molesta al staff.

## 2026-07-06 — Reprogramaciones: diagnóstico primero, fix con OK explícito

---

## 2026-07-28 — Reprogramación: Búsqueda profunda en Dentalink para turnos de la tarde (>17hs) + Respuesta directa

**Decisión**: En Sub-WF CancelarReprogramar (`5cAWJxiWJ50hxEq3`), si el paciente pide un turno por la tarde (>=17:00 hs) y las próximas 2 semanas de la tarde están completas, `Step 6b-out` realiza una **búsqueda profunda** iterando en la API de Dentalink sobre las próximas 6 semanas de Lunes y Miércoles hasta encontrar los primeros turnos reales a las 17 hs (hallando por ejemplo el **Miércoles 2 de Septiembre a las 17:00 hs**).

**Formato de respuesta directa (UX acortada por orden de Lucas):**
1. Responde PRIMERO lo que el usuario pidió: *"Para la tarde después de las 17 hs, el primer turno disponible es el Miércoles 2 de Septiembre a las 17:00 hs (o el Miércoles 2 de Septiembre a las 17:40 hs)."*
2. Agrega como nota secundaria opcional la alternativa de mañana más cercana (*"(Si te sirviera antes por la mañana, la opción más cercana es el Viernes 14 de Agosto a las 9:10 hs)."*).
3. Cierra con pregunta directa de reserva: *"¿Te reservo el Miércoles 2 de Septiembre a las 17:00 hs?"*

**Razón**: Evita dar respuestas largas o evasivas cuando las tardes están llenas a corto plazo. Le da al usuario exactamente la fecha real de la tarde que pidió, más la opción de reservar con un clic.

---

## 2026-08-05 — Migración de n8n y Panel a Evolution GO (API Nativa)

**Decisión**:
1. Conectar n8n a la nueva instancia **Evolution GO** usando nodos `n8n-nodes-base.httpRequest` nativos hacia `POST https://evo.raquelrodriguez.com.ar/send/text` y `POST /message/presence` con header `apikey: <token_instancia_raquel>`.
2. Actualizar las credenciales de Evolution en SQLite de n8n y en el panel web (`/opt/nexora-panel/.env.production`) con la nueva `GLOBAL_API_KEY` (`35643EDB-191F-4174-AB1B-42A859468FE5`).
3. Asegurar `CONNECT_ON_STARTUP: "true"` en Docker Compose y persistencia del webhook `https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2` en la base de datos `evogo_users`.

**Razón**: Evolution GO reemplaza la API anterior de Node.js por una versión en Go mucho más liviana y rápida. Al no depender del nodo de comunidad heredado, la integración REST nativa garantiza cero problemas de compatibilidad y mayor estabilidad.


---

## 2026-08-04 — Fix ruido "ya estas atendiendo": corta WhatsApp, mantiene el registro

**Decision**: cuando el bot detecta que un humano ya esta atendiendo el chat y se
calla, YA NO manda WhatsApp al grupo avisandolo (era el 50% del volumen de
escalaciones: 49 de 98 medidas 20/7-4/8). El registro en `escalaciones_log` se
mantiene intacto (visible en /aprendizaje) — solo se corto la notificacion.

**Como**: `Helper - Notify Grupo` (S5U6tSipzlgFHCkf) gano un nodo IF "Silencioso?"
entre `Log Escalacion` (siempre corre) y `Notify Grupo Send` (se saltea si el
querystring trae `silencioso=true`). El v6 le agrega ese flag SOLO en los 2 nodos
del caso "ya atendiendo" (`Aviso humano tomo chat`, `Gate Humano Final`) — el
resto de las escalaciones (urgencias/pagos/privacidad/dudas reales) no tocan el
flag y te siguen avisando por WhatsApp normal.

Aplicado con `scripts/apply_fix_ruido_notify_grupo.py --apply`, backups PRE/POST
en `workflows/history/`, verificado con un POST de prueba real al webhook
(quedo en escalaciones_log id=101, borrado despues de confirmar).

**Hallazgo del mismo analisis (pendiente, no aplicado)**: el Router NO tiene la
regla "no te metas si hay un humano atendiendo" (si la tienen Confirmar/
Cancelar/Agendar/General). Caso real que lo probo: paciente Santiago Rodriguez
(fam. Rodriguez) — Irina coordinaba a mano un cambio de turno, la mama contesto
"Si, no hay problema" respondiendole a Irina, pero el saludo trivial del bot
("Holaaa" -> "En que puedo ayudarle?") tapo el rastro del hilo humano abierto y
el bot se metio a ofrecer cancelar/reprogramar. Falta: (a) agregar la regla al
Router con este caso como ejemplo, (b) aclarar en los sub-agents que un saludo
propio no cierra un hilo humano en curso. Discutido con Lucas, no aplicado aun.

**Nota de proceso**: hubo un gap 22/7->28/7 donde Lucas uso Antigravity en vez
de esta sesion (Claude "se le habia caido"). El v6 se actualizo el 28/7 sin que
quedara registrado aca. Ya confirmado que `Postgres Chat Memory` tiene
`contextWindowLength: 10` (pedido de Lucas de mas contexto). Antes de futuros
cambios grandes al v6, conviene comparar el snapshot live contra el ultimo
backup local para detectar cambios no documentados.

---

## 2026-08-05 (noche) — Verificar SIEMPRE con un test E2E real, no con "no hay errores"

**Decision**: ante cualquier migracion de infraestructura de mensajeria (cambio de proveedor
de WhatsApp, nuevo esquema de API, etc.), el criterio de "listo" NUNCA es "el codigo compila"
ni "un mensaje de prueba salio" — es disparar el webhook publico completo con el shape REAL
del proveedor nuevo y confirmar que la respuesta se genera Y persiste en memoria
(`n8n_chat_histories`/`conversaciones`).

**Por que**: otra sesion (con Gemini, misma tarde) migro Evolution API clasica -> Evolution GO
y declaro "verificado E2E" tras mandar un mensaje de prueba DIRECTO a la API REST de envio.
Eso prueba que el ENVIO funciona, no que el BOT funciona. El pipeline de RECEPCION (el webhook
que procesa lo que escribe un paciente) quedo con el shape de payload viejo en 4 nodos
criticos (`Webhook Validator`, `Kill-switch Check`, `Rate Limit Prep`,
`Edit Fields - Extraer Datos`) — el validador rechazaba el 100% de los mensajes entrantes,
silenciosamente, antes de que nada se guarde. Una paciente real (Samira Benitez) escribio sus
datos y un comprobante de pago y nunca tuvo respuesta ni quedo registro en ningun lado.

Se sumaron 2 bugs mas del mismo origen (falta de test E2E real), cada uno encontrado leyendo
ejecuciones reales de n8n, NO el codigo en abstracto:
- `Evolution - Typing` (httpRequest generico que reemplazo al nodo custom viejo) pisaba
  `remoteJid`/`message` del item con su propia respuesta HTTP -> el bot generaba la respuesta
  correcta pero el envio final fallaba con "Bad request".
- El ruteo de MEDIA (`Switch - Tipo Mensaje`) dependia de campos (`image_url`, etc.) que en el
  shape nuevo nunca existen -> cualquier foto/audio/documento se perdia sin generar ni un
  marcador de texto.

**Metodo que funciono**: para cada sospecha, simular la logica nueva en Node contra un
payload REAL capturado de una ejecucion (no un payload inventado), y despues re-disparar el
webhook publico con ese mismo payload real (cambiando el destinatario a un numero de test)
para confirmar el comportamiento end-to-end antes de dar el fix por bueno.

**Revisable**: no — esto es un principio de verificacion, aplica a cualquier migracion futura
de este tipo (Dentalink, Chatwoot, o cualquier otro proveedor externo del que dependa el bot).

## 2026-08-06 (madrugada) — "actualizado" no es por-workflow, es por-nodo: probar CADA cron tocado

**Decision**: cuando una migracion de infraestructura toca "todos los workflows activos", el
principio de "verificar con test E2E real" (ver entrada anterior) no alcanza con probar el
workflow de mayor trafico (v6) — cada workflow con un envio real (Recordatorios, Daily Summary,
Helper Notify, etc.) necesita su propio test E2E antes de confiar en su proxima corrida
automatica, sobre todo si es un cron que no corre hasta el dia siguiente.

**Por que**: `Recordatorio de Turno 48HS` (`7RqTApkvVavRmq3R`) quedo con el nodo `Enviar
WhatsApp` con una expresion n8n invalida tras la migracion a Evolution GO — mismo tipo de bug
que los 3 del v6, pero en OTRO workflow, que nadie habia disparado desde el cambio porque su
proxima corrida real era recien al otro dia 08:00 ART. Si no se auditaba a mano (Lucas
pregunto "¿los recordatorios andan?"), el bug se descubria recien con la corrida real, con
pacientes reales, sin ningun aviso (el nodo tiene `continueOnFail: true` -> falla en silencio,
el workflow queda "success").

**Metodo reusable**: si el workflow tiene (o se le puede agregar) un trigger manual + un flag
tipo `TEST_MODE` que redirige el envio real a un telefono de prueba en vez de a destinatarios
reales, usarlo para disparar la logica COMPLETA (no un mock) antes de confiar en la proxima
corrida automatica. Revertir el flag apenas termina el test — anotarlo en el todo list para no
olvidarlo, es el paso que mas facil se salta.

**Revisable**: no — extension directa de la entrada anterior (2026-08-05 noche), aplica al
mismo tipo de migracion.

## 2026-08-06 (mañana) — un bug de migracion encontrado UNA VEZ se grepea en TODOS los workflows YA, no despues

**Decision**: en cuanto un bug de migracion (expresion rota, endpoint viejo, shape de
payload) aparece en un workflow, el paso inmediato siguiente es grepear la MISMA firma en
TODOS los workflows activos de la cuenta ANTES de dar el tema por cerrado — no arreglar
uno por uno a medida que cada uno "se manifiesta" (a veces dias despues, cuando alguien nota
que le falta un mensaje).

**Por que**: la expresion rota `"{{ String(={{ $json.X }}||"").replace(...) }}"` (nested
mustache + "=" suelto) de la migracion a Evolution GO se encontro y arreglo en v6 y
Recordatorios la noche del 05/08 — pero **NO se grepeo el resto de la cuenta esa misma
noche**. Resultado: goteo durante 24hs — Lucas no recibio el resumen de recordatorios
(06/08 mañana), y las escalaciones reales al grupo de WhatsApp estuvieron rotas 17+ horas
sin que nadie se enterara (el bot igual logueaba en `escalaciones_log`, pero el aviso por
WhatsApp nunca llegaba). Un solo grep de 30 workflows activos por esa firma encontro los
3 casos restantes en un paso.

**Metodo reusable**: `grep`/busqueda de texto sobre el JSON completo de CADA workflow activo
(no solo los que "se tocaron" segun el reporte de la migracion) por la firma exacta del bug
encontrado, apenas se identifica el patron — no como tarea de auditoria aparte para "despues".

**Revisable**: no — es la continuacion logica de verificar-con-test-E2E: una vez que un test
real revela que un patron esta roto, el patron se busca en TODOS lados de inmediato, no solo
donde el test miraba.

---

## 2026-08-15 — Incidente de recordatorios recurrente: gap de proceso, no de código

**Decisión**: no tocar el workflow — el fix técnico del 14/7 ("agenda es la fuente de verdad",
verificado en código) sigue correcto y funcionando. El incidente volvió a pasar (Irina se
quedó sin confirmaciones de lunes/martes un fin de semana) porque Irina pidió apagar los
recordatorios manualmente en vez de usar la agenda, y hubo una confusión sobre cuándo
reactivarlos. Reafirmado con Raquel presente: Iri debe cancelar/confirmar turnos EN Dentalink,
nunca pedir on/off del bot — ese flujo ya funciona solo.
**Razón**: Raquel lo remarcó explícitamente — "esto tiene que sacarnos trabajo, no al revés".
**Alternativa descartada**: agregar detección de feriados como servicio nuevo (infraestructura
extra) — innecesario, confirmar de antemano en agenda ya cubre el caso feriado.
**Revisable**: si el incidente se repite una tercera vez pese a la comunicación reforzada,
considerar un recordatorio/alerta al staff sobre el flujo correcto (no cambio de código).

## 2026-08-15 — Política de precios y alcance del bot: reafirmada sin cambios

**Decisión**: el bot nunca da precio fijo de tratamiento (se evalúa en consulta, varía según
lo que necesita el paciente); sí puede dar valores estáticos de consulta y estudios.
**Razón**: Raquel marca límites claros de alcance financiero del bot — evitar que el bot
comprometa un precio que después no se sostiene.
**Revisable**: no, es política de negocio estable desde antes del 14/7 (ver ese doc), esta
sesión solo la ratifica.

## 2026-09-02 — Diseño del triaje de urgencias con video: 3 decisiones cerradas

**Contexto**: Raquel empezó a mandar los 4 videos de triaje (alambre pincha, bracket suelto,
alambre girado, ligadura pincha — filmados desde el 15/8). Lucas pidió pensar el diseño
completo más allá del happy path antes de construir, porque expande al Sub-Agent Urgencia
(hoy: función única, escalar siempre, prohibido dar cualquier consejo — regla dura post-incidente
Mariela) para que en casos NO graves conteste con un video en vez de escalar.

**Decisión 1 — Foto: SIN vision, solo respaldo adjunto.** El bot NO interpreta la foto que se
le pide al paciente; la clasificación del tipo de urgencia es 100% por texto + preguntas
guiadas. La foto queda adjunta al log/escalación para que la doctora la vea si hace falta.
**Razón**: Lucas delegó la decisión ("decide por mí lo que funcione mejor para la experiencia"),
pero el proyecto tiene una regla dura explícita (#6 del CLAUDE.md, post-incidente) de pararse
antes de meter vision — usarla acá para "mejorar UX" sería la misma clase de decisión apurada
que causó el incidente de Mariela (bot inventando una respuesta autónoma en área médica sin
capa de control determinística). Si el modo sombra muestra que la clasificación por texto no
alcanza, se revisa con datos reales, no a priori.
**Alternativa descartada**: usar vision para confirmar el tipo antes de mandar el video (más
preciso en teoría, pero abre una puerta que el proyecto cerró explícitamente).
**Revisable**: sí, con evidencia real del modo sombra/piloto de que la clasificación por texto
falla seguido.

**Decisión 2 — Aviso pasivo cuando se resuelve con video.** Cuando el caso matchea un tipo
conocido (no grave) y se manda el video en vez de escalar, igual queda logueado y se ve
reflejado (reportero semanal / resumen) para que la doctora tenga visibilidad — sin pedirle
que actúe, no es un aviso urgente.
**Razón**: Lucas eligió esto sobre "totalmente silencioso" — visibilidad sin generar ruido
operativo.

**Decisión 3 — Rollout en 3 fases: sombra → piloto de 1 tipo → expandir a los 4.** Fase 1: el
bot clasifica pero sigue escalando TODO como hoy, solo logueando qué hubiera hecho (compara
contra qué resolvió la secretaria en cada caso real). Fase 2: piloto en vivo con el tipo que
la fase sombra muestre más confiable (candidato: "bracket suelto", parece el menos ambiguo).
Fase 3: expandir a los 4 tipos con Raquel mirando de cerca los primeros casos.
**Razón**: misma área del incidente real de Mariela — Lucas confirmó ir con el patrón ya usado
en este proyecto (TEST_MODE en Reportero/Recordatorios) antes de que un paciente reciba
un video equivocado en producción.
**Revisable**: sí, duración de cada fase a definir con datos reales, no fija de antemano.

**Diseño acordado, no solo estas 3 decisiones** (ver current-state 2/9 para el detalle completo
capa por capa): gate determinístico de "red flags" (trauma, sangrado abundante, pieza tragada,
hinchazón/dificultad respirar, fiebre, dolor intenso) corre ANTES de clasificar tipo y de nuevo
DESPUÉS de las preguntas guiadas — cualquier red flag gana sobre un match de tipo conocido. Sin
match claro → escalar, nunca adivinar. Caption del video es canned (no generado por LLM), con
salida de emergencia explícita. Pendiente de Raquel: confirmar la lista de red flags y el fraseo
exacto de las preguntas guiadas (ver open-questions.md).

## 2026-09-02 — Hosting de los videos de urgencias: Supabase Storage público, n8n pasa la URL

**Decisión**: los videos de triaje viven en el bucket público `urgencias-videos` de Supabase
Storage v3 (path `<tipo>/opcionN.mp4`); el v6 le pasa a Evolution GO la URL pública en
`POST /send/media` (`{number, type:"video", url, caption, filename}`), sin leer ni codificar
el archivo en n8n.
**Razón**: `/send/media` acepta base64 y URL https (ambos verificados en vivo el 2/9); la URL
evita mover 4–5MB por ejecución de n8n. Volumen real medido: ~15 urgencias/mes → ≤15 envíos
→ ~70MB/mes de egress, irrelevante para el free tier. Los videos son contenido instructivo
pensado para mandarse a pacientes: URL pública es aceptable.
**Alternativas descartadas**: (a) base64 inline en n8n — funciona pero mueve MBs por
ejecución y complica el nodo; (b) servir estáticos desde el VPS — evita egress de Supabase
pero requiere tocar el reverse proxy y versionar binarios; no se justifica con este volumen.
**Revisable**: sí, si el volumen crece 20x o si Supabase v3 se migra fuera del free tier
(decisión pendiente en backlog P0).

## 2026-08-15 — Autonomía del agente: reducir escalaciones sin volverse un mero derivador

**Decisión**: seguir el punto medio ya buscado desde el inicio del proyecto — ni el agente
responde todo (estado inicial, generaba errores) ni escala todo (lo vuelve inútil, "un mero
escalador a la secretaria"). Las escalaciones de pago (comprobante que Irina debe verificar)
SÍ están bien y no se tocan; el resto se debe resolver con más contexto/KB antes que con
escalación.
**Razón**: objetivo de fondo de Raquel para fin de año — que el agente funcione lo bastante
solo para no depender de la secretaria como cuello de botella, gestionable por el staff desde
el panel.
**Revisable**: sí, según cómo evolucione el volumen y tipo de escalaciones (medible con el
reportero semanal ya construido).

## 2026-08-21 — Un bug de clasificación de intent multi-pedido se arregla en las 2 capas que lo tocan, no solo en el sub-agent "obvio"

**Decisión**: cuando un mensaje real trae más de un pedido a la vez (ej: completar un
registro/reserva + preguntar precio/obra social en el mismo mensaje), el fix no puede
vivir solo en el sub-agent operativo (Agendar) — el Router clasifica por UN intent, y si
clasifica mal, el sub-agent correcto ni corre. Se corrigió en las 2 capas: el Router
(no abandonar el flujo activo si el mensaje TAMBIÉN trae la info pedida) y Sub-Agent
General (su propia "validación de destino" debe ganarle a la regla de prioridad absoluta
de obra social cuando el mensaje completa una acción pendiente que no puede ejecutar).
**Razón**: el primer intento (solo Sub-Agent Agendar) se probó en vivo y reprodujo
exactamente el mismo bug — el Router nunca mandó el mensaje a ese sub-agent. Verificar
con reproducción real, no con el diff, expuso que la causa raíz estaba un nivel arriba.
**Alternativa descartada**: intentar que el clasificador de intent devuelva múltiples
intents a la vez (rediseño mayor del Router/switch) — descartado por alcance, el carve-out
puntual resuelve el caso real sin tocar la arquitectura de un-intent-por-mensaje.
**Revisable**: si aparece un tercer caso real de mensaje multi-pedido que ninguna de las
2 capas cubra, reconsiderar si el Router necesita devolver más de un intent.

## 2026-09-02 — La info canned deja de vivir en los prompts de los sub-agents: capa determinística transversal (Canned Sidecar)

**Decisión**: agregar un nodo Code determinístico `Canned Sidecar` en el punto donde
convergen los 7 caminos de salida del v6 (`Fallback Output` → **Canned Sidecar** →
`Banlist Validator`). Lee el texto REAL del paciente, detecta por regex si pidió alias/datos
de pago o precio, y si la respuesta del sub-agent no lo trae, lo ANEXA. Nunca modifica lo que
el sub-agent generó: solo agrega. Ningún sub-agent necesita saber de info canned nunca más.

**Razón**: es la ejecución de la cláusula "revisable" de la decisión del 21/8 — aparecieron
dos casos reales más (2/9 Paulina Villanueva, 28/8 tel ...170679) que ninguna de las 2 capas
de ese fix cubría. La causa raíz no fue "el LLM se olvidó": el Router (fix 21/8) afirma que
"el sub-agent operativo ya sabe responder la info canned ADEMÁS de ejecutar la acción", y el
prompt vivo de Sub-Agent Confirmar ordena lo contrario ("si después de confirmar pregunta otra
cosa → dejar que el flow lo enrute en el próximo turno" + "SOLO responder el canned y FIN").
Dos capas vivas contradiciéndose, cada una creyendo que la otra es dueña del alias. Cuando el
buffer mergea 2 mensajes rápidos en una sola ejecución NO HAY "próximo turno" y el pedido se
pierde en silencio. Un parche en el prompt de Confirmar sería whack-a-mole: es exactamente lo
que se hizo el 21/8 para Agendar, y por eso Confirmar quedó afuera (N sub-agents × M canned).

**Alternativa descartada 1 — carve-out en el prompt de Sub-Agent Confirmar**: no escala
(hay que repetirlo en Cancelar, Urgencia, el flow de comprobante y en los 3 sub-agents del
refactor futuro) y depende de que el LLM cumpla bajo reglas en conflicto, que es el modo de
falla ya observado dos veces.
**Alternativa descartada 2 — Router multi-intent (devolver lista de intents)**: es la
arquitectura correcta a largo plazo pero cambia el contrato del Router, el Switch y el orden
de salidas sobre un bot vivo con la confianza de la doctora en recuperación, y vuelve a
depender de un LLM. Va con el refactor a Supervisor, no ahora. El sidecar sigue siendo útil
como red de seguridad debajo de ese refactor.
**Alternativa descartada 3 — desarmar el buffer de mensajes**: existe por buena razón (evita
contestar a mitad de una frase) y el caso del 28/8 era un solo mensaje multilínea de todas
formas — no lo hubiera evitado.

**Decisión secundaria (cambio respecto del plan inicial)**: el alias y el bloque de datos de
cuenta quedan hardcodeados en el sidecar, idénticos al prompt vivo de Sub-Agent General, en vez
de leerse de la KB. La fila ya existe (`knowledge_base` id=24 "Datos de cuenta para
transferencia", categoría `pagos`, ya editable desde `/servicios`), así que dinamizarla era
barato — pero hacerlo SOLO en el sidecar dejaría a General hardcodeado: Raquel edita
`/servicios`, cambia una respuesta y la otra no. **Dinamismo parcial es peor que ninguno.**
Migrar AMBOS a KB id=24 en una sola pasada queda como P2. El precio sí es dinámico en los dos
(ya lo era: `Extraer Horarios y Precio`, KB id=21).

**Guardrails elegidos** (lección del "blindaje tarde" del 18/8 — heurística sobre datos que no
son lo que dijo el paciente): inspecciona el texto real del paciente y no datos derivados;
dispara solo con pedido explícito (interrogativo/imperativo), no con menciones; evalúa POR
ORACIÓN (mismo patrón que arregló el guard de precios del panel el 24/8); dedup si la respuesta
ya trae alias/CBU/monto; passthrough en `[NO_REPLY]` y urgencias; falso positivo = un bloque de
alias de más, nunca comportamiento incorrecto. Reglas de horarios/dirección quedan escritas
pero `enabled:false` — se arranca solo con lo que falló de verdad en producción (plata).

**Ubicación elegida — antes del Banlist, no después**: `Split en Mensajes` ya tiene un guard
determinístico ("si el original traía CBU y el formateado lo perdió, usá el original") que lee
de `$('Banlist Validator')`; insertando antes, ese guard protege gratis el bloque anexado si el
Formatting Agent lo descarta. Además el Banlist inspecciona también el texto anexado (regla 5,
defensa en profundidad) y `Gate Humano Final` lo incluye en el aviso al grupo.

**Revisable**: sí. Si aparecen falsos positivos reales (el bot anexa el alias cuando no
correspondía), ajustar `PEDIDO`/`YA_HECHO` en el nodo. Si el refactor a Supervisor llega a
manejar multi-intent de verdad, el sidecar puede quedar como red de seguridad o retirarse.

## 2026-09-04 — Triaje con video: construir la Fase 2 (piloto en el v6) YA, sin esperar a Raquel

**Decisión**: Lucas pidió que el triaje de urgencias "funcione completo" porque necesita venderlo
a otro cliente. Se acelera la Fase 2 (piloto en el v6, tipo alambre_pincha con sus 2 videos
reales) SIN esperar el fraseo de preguntas guiadas ni la confirmación de red flags de Raquel:
se usan los borradores ya escritos (open-questions.md 2/9) como texto canned EDITABLE en una
tabla de configuración (`triaje_videos`), para que Raquel los corrija después desde datos, no
desde n8n. Los otros 3 tipos quedan en la tabla con `activo=false` y siguen escalando hasta que
lleguen sus videos.
**Razón**: el bloqueo era de contenido (videos/fraseo), no técnico; la sombra retrospectiva
(30 casos reales) mostró que el clasificador acierta con confianza alta en el primer mensaje
en la gran mayoría de alambre_pincha, y los 2 videos ya están hospedados y probados E2E.
Mantener la fase sombra como única salida no sirve para una demo comercial.
**Lo que NO cambia**: todas las reglas duras siguen (texto al paciente 100% canned, LLM solo
clasifica, gate determinístico de red flags antes, fail-closed a la escalación actual, diff +
backup antes del PUT, webhookId preservado). Sigue siendo piloto de UN tipo — no es "los 4 en
vivo".
**Alternativa descartada**: esperar a Raquel (semanas sin fecha) o demostrar con el webhook
aislado (no es el bot real; Lucas ya intentó escribirle al número real y vio que "no anda").
**Revisable**: sí — cuando Raquel conteste, sus textos reemplazan los borradores en la tabla;
si la sombra/piloto muestra clasificaciones erróneas en vivo, se desactiva el tipo por fila
(`activo=false`) sin tocar n8n.

## 2026-09-04 — Fase 2 del triaje: escalación determinística, Merge por posición, config por dato (aplicado)

**Decisión**: sobre el diseño ganador del panel de jueces ("product-first", ver
`docs/triaje-fase2-analisis/jueces.md`), tres cambios al implementar:
1. **La escalación desde la rama de triaje es determinística** (Code → texto canned al paciente
   → `notify-grupo` → log → Redis), NO vía `Sub-Agent Urgencia` (queda huérfano en el v6, sin
   borrar; `--rollback-wiring` lo reconecta).
   **Razón**: el mapeo con ejecuciones reales mostró que hoy el Helper aplica el label `humano`
   sincrónicamente y `Re-check Humano` suprime la respuesta del sub-agent en 6/6 escalaciones
   desde el 30/8 — el LLM además podía devolver `[NO_REPLY]` por "validación de destino" y no
   escalar. Con la escalación determinística el paciente SIEMPRE recibe el texto canned antes de
   que se aplique el label, y el resumen al grupo lleva tipo/opciones enviadas/texto del paciente.
2. **`Triaje: Merge Clasificación` (combine by position)** entre el clasificador y `Decidir`,
   para que Decidir reciba los datos de Evaluar en el mismo item. **Razón**: en el camino
   seguimiento → Router → urgencia_dolor, `Triaje: Evaluar` corre dos veces en la misma ejecución
   y `$('Triaje: Evaluar').first()` es ambiguo (n8n 2.13.4, semántica de runIndex no garantizada).
3. **Config 100% por dato** (`triaje_config` + `triaje_videos`): kill-switch, allow-list piloto,
   textos, regexes, TTLs, modelo, videos por tipo/opción. `aviso_pasivo=false` por defecto (una
   fila en `escalaciones_log` hoy se muestra como "señal" en /aprendizaje e infla el KPI).
**Alternativas descartadas**: mantener Sub-Agent Urgencia como ejecutor de la escalación con un
párrafo de prompt (LLM-dependiente para el caso más sensible); referencias cruzadas con
`.first(0, runIndex)`; notify-grupo con `silencioso=true` para el aviso pasivo (aplica label y
mataría la Opción 2).
**Rollout**: piloto activo solo para el número de Lucas hasta que él decida abrirlo
(`create_triaje_config_tables.py --activar --piloto ""`).
**Revisable**: sí — si el auto-silencio post-escalación se arregla a nivel Helper/Re-check, se
puede reevaluar volver a un sub-agent para el resumen; hoy no aporta nada que el resumen
determinístico no tenga.

## 2026-09-04 — Escalaciones: el label `humano` se aplica 20 s DESPUÉS del aviso, no al instante

**Decisión**: en `Helper - Notify Grupo` (S5U6tSipzlgFHCkf) el webhook responde al instante
(`onReceived`) y `Chatwoot Apply` corre después de un Wait de 20 s. El aviso al grupo sigue
siendo inmediato.
**Razón**: con el label sincrónico, `Re-check Humano`/`Gate Humano Final` del v6 veían el label
1.4 s después de que el propio bot escalara y suprimían su respuesta: 6/6 escalaciones desde el
30/8 sin "Recibimos tu mensaje…" para el paciente (confirmado con ejecuciones reales). Todos los
prompts asumen que ese canned se entrega y que DESPUÉS el bot se calla — el delay restituye esa
semántica sin tocar el v6.
**Alternativas descartadas**: que el re-check ignore labels "propios" (no hay timestamp por
label en Chatwoot); no aplicar label cuando escala el bot (rompería el silencio post-escalación
que sí se quiere); arreglarlo dentro del v6 (blast radius mayor).
**Costo aceptado**: ventana de 20 s en la que un paciente que re-escribe muy rápido puede recibir
una segunda respuesta/escalación. Antes no recibía ninguna.
**Revisable**: sí — ajustar `--segundos` si la ventana molesta o si la respuesta del bot tarda
más (tail con Formatting Agent ≈ 5–10 s).

## 2026-09-05 — Triaje: el clasificador solo ve el contexto del episodio actual

**Decisión**: `Triaje: Evaluar` recorta el contexto del Router al tramo posterior al último
`[TRIAJE ESCALADO]` / `[TRIAJE CIERRE]` antes de pasárselo al clasificador, y el prompt del
clasificador exige evaluar red flags ÚNICAMENTE sobre el mensaje actual. La reconstrucción de
estado (Opción ya enviada) sigue mirando el contexto completo.
**Razón**: caso real (Lucas, 4/9 18:43 ART, exec 270770): "Me pincha un alambre de brackets"
salió `red_flag` porque el contexto aún contenía "se cayó, le sangra mucho" de un episodio ya
escalado. Un episodio cerrado/escalado no debe contaminar el siguiente; las red flags del
mensaje actual las cubre además el gate determinístico.
**Alternativa descartada**: no pasar contexto al clasificador (pierde "sigue igual" → mismo
tipo); confiar solo en el prompt (una sola capa).
**Revisable**: sí — si aparecen casos donde el contexto del episodio anterior sí importa
clínicamente (hoy la doctora ya lo tiene porque ese episodio se escaló).

## 2026-09-05 — Robustez verificable: Vigía + chequeo único + reglas de proceso 8/9

**Decisión**: (1) satélite `Áurea — Vigía` cada 15 min que avisa a Lucas por WhatsApp ante
triaje degradado / errores del v6 / instancia sorda en horario de clínica / triaje sin videos
(dedupe 60 min); (2) `scripts/check_triaje.py` obligatorio antes de cualquier PUT; (3) reglas
duras 8 ("no afirmar que funciona sin E2E del camino completo") y 9 ("cero residuos de test en
chats reales, limpiar en el mismo turno") en `.claude/CLAUDE.md`.
**Razón**: Lucas pidió "re contra funcional, sin caídas" después de dos regresiones percibidas
que fueron de proceso, no de código: afirmar que el panel enviaba sin verificar el backend
(2/9) y dejar residuos de mis E2E en su chat que contaminaron su prueba real del triaje (4/9).
No se puede prometer cero fallas; sí que él se entere primero y que cada cambio pase por el
mismo chequeo.
**Alternativas descartadas**: E2E diario automático contra producción (manda WhatsApps reales a
Lucas todos los días — ruido); extender el Health Check existente (mezcla responsabilidades y
toca un workflow que funciona).
**Revisable**: sí — umbrales (20 min, 3 h, horario) y destinatario (hoy solo Lucas, patrón
TEST_MODE del reportero).

## 2026-09-05 — Inbox Live (mensaje entrante al instante) + label humano solo en la conversación abierta

**Decisión 1**: el v6 escribe cada mensaje entrante crudo en `mensajes_entrantes_live` (nodo
`Inbox Live`, rama muerta desde `Edit Fields - Extraer Datos`, insert parametrizado defineBelow)
y el panel lo mergea como burbuja pendiente hasta que existe la fila real en memoria.
**Razón**: la memoria LangChain escribe el mensaje del paciente al FINAL del turno (30–45 s);
Lucas veía el panel "sin actualizar" y necesitaba F5. Rama muerta = cero impacto en el flujo.
**Alternativa descartada**: insertar la fila `human` en memoria al entrar (la memoria LangChain
la duplicaría); bajar el buffer (decisión de producto aparte, backlog P2).
**Lección**: NUNCA `executeQuery` + `queryReplacement` con texto libre — n8n parte los parámetros
por coma después de evaluar. Usar insert `defineBelow` (Log Escalacion) o SQL armado en Code con
`esc()` + `chr(36)` (triaje).

**Decisión 2**: los escritores de label `humano` del panel etiquetan SOLO la conversación abierta
(o la más reciente); "volver a bot" quita `humano` de TODAS.
**Razón**: el gate del v6 mira todas las conversaciones y Auto Reactivar solo limpia abiertas →
un `humano` en una resuelta silencia al bot indefinidamente (pasó con Lucas el 5/9). Blindar el
gate del v6 queda en backlog P2.

## 2026-09-06 — Dirección del proyecto: pulir/refactorizar hacia un sistema completo (agenda propia)

**Decisión**: Lucas (6/9) fija la dirección: seguir puliendo y refactorizando para que quede "pro",
con la visión de armar un sistema completo que incluya un reemplazo propio de Dentalink (agenda +
pacientes + citas), "que eso ya lo vamos a ir cocinando". El mapa priorizado con evidencia está en
`docs/roadmap-refactor-2026-09-06.md` (B1 registro único de mensajes, B2 higiene del v6, B3
comportamiento como datos, B4 panel WhatsApp Web real, B5 tests; C camino al Dentalink propio:
modelo en Supabase → adaptador → doble escritura → cutover con flag).
**Razón**: los bugs de estos días vinieron de fuentes duplicadas (Logger vs memoria vs bandeja) y
de comportamiento enterrado en prompts/nodos; consolidar datos y sacar lógica a tablas reduce la
superficie de fallas y prepara el sistema propio.
**Revisable**: sí — el orden de B1..B5 es sugerido; Lucas decide qué va primero.

## 2026-09-06 — Panel en vivo: Supabase Realtime server-side + SSE (no polling, no socket propio)

**Decisión**: Lucas pide que el panel sea live de verdad ("así no dependemos de otra y luego la
podemos hacer mobile app"). Se elige: el servidor Next se suscribe UNA vez por WebSocket a
Realtime del v3 (service key, nunca en el navegador) sobre `mensajes_entrantes_live` (INSERT),
`n8n_chat_histories` (INSERT) y `pacientes` (UPDATE), y empuja eventos al navegador por
Server-Sent Events (`/api/live`); el cliente refetchea solo cuando hay novedad, con polling de
respaldo si el stream cae. Publicación habilitada con `scripts/apply_realtime_publication_v3.py`.
**Alternativas descartadas**: polling más rápido (carga a Supabase: 6 queries cada 2,5 s por
pestaña); WebSocket propio con socket.io (servicio extra, nada que SSE no dé acá); Realtime
directo desde el navegador (exige anon key + RLS en el v3, que hoy no tiene policies).
**Razón**: <1 s de latencia, casi cero consultas en reposo, sin infra nueva, atraviesa Traefik
sin config, y el par SSE + APIs JSON es lo que consumiría una app móvil.
**Revisable**: sí — si Realtime del v3 se vuelve poco confiable, el plan B es LISTEN/NOTIFY con
triggers `pg_notify` y una conexión directa a Postgres desde el panel.

## 2026-09-06 — Adjuntos del paciente: el v6 los sube a Storage privado y deja ` [MEDIA:<id>]` en el marcador

**Decisión**: los archivos que manda el PACIENTE (foto, audio, video, documento, sticker) se suben desde el v6
al bucket PRIVADO `pacientes-media` con la credencial supabaseApi de n8n (mismo `Message.base64` que ya llega
en el webhook de Evolution GO), se registran en `media_entrantes` (id 16 hex aleatorio) y el marcador de texto
existente recibe AL FINAL el sufijo ` [MEDIA:<id>]` — solo si el INSERT salió bien. El panel firma URLs de 1 h.
Cadena nueva (6 nodos "Media: *") entre los 4 Set Marker y `Merge Multimedia`; el Merge pasa de 5 a 2 entradas
con ambas conectadas. Adjuntos del staff (fromMe) quedan fuera por ahora.
**Razón**: Lucas quiere ver el adjunto real en el panel ("sí hacelo"); el archivo ya viaja desencriptado en
cada webhook (100 % en 2048 execs), así que no hace falta llamar a `/message/downloadmedia` (nunca verificado).
Privado porque son bocas y comprobantes. El sufijo al final del marcador no toca los prefijos que miran los
gates/prompts, y un id hex no puede formar ninguna palabra que testeen Canned Sidecar / Gate Pago / Triaje.
**Alternativas descartadas**: bucket público (privacidad); guardar el base64 en la tabla (6× el tamaño en la
fila de la ejecución y en Postgres); Merge con 5 entradas y 3 sueltas (sin evidencia de cómo se comporta en
executionOrder v1; con 2 conectadas se reproduce el patrón probado en producción); `executeQuery` +
`queryReplacement` para el INSERT (parte por coma: lección 5/9); marcador nuevo en vez de sufijo (rompería
Pre-filtro Cierre y los prompts que miran `[IMAGEN`/`[DOCUMENTO`/`[AUDIO`).
**Revisable**: sí — el tope de 20 MB, el timeout 30 s, la 2ª capa anti-eco del token en la salida (pendiente
P2) y sumar la rama fromMe (P3).

## 2026-09-06 — media_entrantes: `telefono` verbatim, sticker no-imagen como octet-stream, Marcar con red de seguridad

**Decisión** (ronda de revisión del mismo día): (a) `media_entrantes.telefono` guarda `Extraer Datos.phone` TAL CUAL
(no solo dígitos) y únicamente el `path` del objeto se sanea a dígitos; (b) un sticker cuyo contenido no es
PNG/WEBP/GIF (Lottie) se sube con mime `application/octet-stream`; (c) `Media: Marcar` cae al `text` del Set Marker
que ejecutó si `Media: Preparar` devolvió `{error}` sin `text`; (d) la subida manda `cache-control: max-age=3600`;
(e) el panel cuelga adjuntos solo a filas del paciente (`rol user`) y el 302 de `/api/media` lleva `Vary: Cookie`.
**Razón**: (a) Inbox Live, la memoria (`session_id`) y el Logger usan `phone` crudo y el panel cruza con `.eq`; si
algún día llega `…@lid`, con dígitos solos los adjuntos de ese paciente nunca resolverían. (b) el panel pintaría un
`<img>` roto; con mime genérico lo muestra como chip "Sticker". (c) hoy inalcanzable (el try/catch cubre todo el
código) pero un kill del sandbox dejaría al Router un mensaje vacío. (d) Storage sirve `no-cache` si no se manda; la
firma dura 1 h así que cachear 1 h es coherente. (e) riesgo R3 (eco del token por el bot) sin 2ª capa todavía: la
foto del paciente no debe aparecer en la burbuja verde; y un `<img>` cacheado no debe seguir resolviendo tras logout.
**Alternativas descartadas**: sanear también la columna (rompe el cruce con el panel); rechazar stickers Lottie
(se pierde el archivo); filtrar el token en `Banlist Validator` ya (fuera de la rama multimedia: pide OK aparte, P2).
**Revisable**: sí — si Extraer Datos garantiza dígitos, (a) es inocua; (c) se puede quitar si el runner demuestra
que nunca emite `{error}` sin `text`.

## 2026-09-07 — Retención propia (90/90/365 días) en un satélite n8n + alertas de uso en el Vigía, en vez de subir de plan

**Decisión**: lo único que puede saturar el Supabase v3 free (500 MB base / 1 GB storage) son los adjuntos; se crea el
satélite `Áurea — Retención (archivos y bandeja)` (cron 04:30 Jujuy) que borra adjuntos del paciente
(`pacientes-media`) y del staff (`panel-media`) con más de 90 días y filas de `mensajes_entrantes_live` con más de
365, en lotes de 200, marcando `media_entrantes.borrado_at` y dejando `retencion_log`; avisa a Lucas SOLO si falló.
El Vigía suma `supabase_db_alto` (> 400 MB) y `supabase_storage_alto` (> 800 MB) con dedupe de 24 h (`ventanaMin`
por alerta) y `vigia_query_rota` (si la query única falla, ninguna alerta puede salir). Memoria y `conversaciones`
no se tocan (40 MB/año).
**Razón**: Lucas pidió "que funcione y se autoregule"; 90 días cubre cualquier seguimiento clínico razonable y el
panel muestra "Adjunto vencido" en vez de romperse. Storage se borra SOLO por la API REST (borrar `storage.objects`
por SQL deja el blob en S3 y sigue contando); `panel-media` se lista desde `storage.objects` porque `/object/list`
es jerárquico y devuelve carpetas sin `created_at`; un objeto ya inexistente cuenta como OK (si no, se reintentaría
cada noche). ids al UPDATE unidos por `|` (n8n parte `queryReplacement` por coma). Zona horaria vía
`settings.timezone` (comportamiento documentado del Schedule Trigger) con verificación de la primera corrida.
**Alternativas descartadas**: subir a Pro ya (USD 25/mes por 9 MB usados); borrar por SQL; `POST /object/list` con
`prefix ''`; borrar solo lo que Storage confirmó (deja huérfanas reintentando); avisar a Lucas en cada corrida (ruido).
**Revisable**: sí — `DIAS_*`, `LOTE`, `CRON`/`TZ` son constantes + `--update`; los umbrales del Vigía son
`DB_ALTO_MB` / `STORAGE_ALTO_MB` en `EVAL_JS`.

## 2026-09-07 — Audio del staff desde el panel: `/send/media` type `audio`, formato m4a/mp3, memoria `[audio] <url>`

**Decisión**: el satélite `Panel — acciones staff` acepta `media_tipo: audio` y lo pasa tal cual a `/send/media`
de Evolution GO; el content de la memoria es `[audio] <url>` (+ `\n` + caption), mismo patrón que `[imagen]`.
`filename` saneado conserva la extensión al recortar a 80 chars. El panel graba con MediaRecorder, manda m4a tal cual y
transcodifica webm/opus → mp3 en el navegador (lamejs) antes de subir a `panel-media`.
**Razón**: verificado 7/9 con un envío real: `type: 'audio'` → 200; `'ptt'` → 500 "invalid media type"; no existe
`/send/audio`. WhatsApp reproduce mp3 / m4a / ogg-opus; webm no es confiable en iOS. Sin la extensión, WhatsApp
puede no reconocer el mime del audio/documento.
**Alternativas descartadas**: transcodificar en el servidor (ffmpeg en el container del panel: peso y CPU en el VPS);
subir el webm crudo (iOS); marcador nuevo en la memoria (el panel ya parsea `[tipo] <url>`).
**Revisable**: sí — si Evolution GO suma `ptt` real (nota de voz con forma de onda) se cambia el `type`.

## 2026-09-07 — Revisión de retención/audio: smoke con `'-'`, `media_tipo` inválido = 400, MP3 único, "vencido" solo confirmado

**Decisión** (correcciones tras el mapa de lectura del 7/9, ambos repos, nada aplicado):
1. `Pacientes: marcar borrado_at` recibe `ids.join('|') || '-'`: un `queryReplacement` vacío hace que n8n no pushee `$1`
   (`stringToArray` filtra entradas vacías → `there is no parameter $1`) y el smoke del alta avisaba en falso. Se eligió el
   parámetro `'-'` y no un IF antes del UPDATE para que el smoke ejercite TODOS los nodos (`marcados 0` real).
2. `Validar secreto` del satélite staff responde `media_tipo invalido` (400 vía `¿Sin secreto?` → `Responder 400`) ante un
   tipo desconocido con URL; ya no cae a `image`. Compatible hacia atrás; su `--update` va ANTES del deploy del panel.
3. El panel manda SIEMPRE MP3 (mono 64 kbps, 48 kHz vía `OfflineAudioContext`): MediaRecorder pide webm/opus primero y el
   AAC de Safari también se transcodifica; solo `audio/mpeg` pasa tal cual. El server acepta cualquier frame sync de capa III.
4. El chip "Adjunto vencido (se guardan 90 días)" solo con 404/410 confirmado por el servidor; otra falla → chip neutro
   "No se pudo reproducir acá · abrir" con link.
5. Vigía: `retencion_no_corrio` (26 h, dedupe 24 h) leído con `to_regclass` + `query_to_xml`; Retención: advertencia (sin
   fallido) si Storage devolvió 0 de N reales; `Q_PACIENTES` filtra bucket; `--recover-secret` en el script del staff.
6. lamejs 1.2.1 es **LGPL-3.0** dentro del panel propietario: va en un chunk dinámico aparte (`import()` de `lib/lamejs-cjs.cjs`),
   se deja anotado; alternativa MIT si algún día molesta (Opus→OGG nativo de Firefox, o transcodificar en el server).
**Razón**: el harness mockeaba el UPDATE con `{marcados:0}` y tapaba el `$1` faltante (verificado en n8n 2.9.4, mismo
typeVersion); el camino principal del staff (Chrome Windows → AAC fMP4 crudo) era el NO probado, el MP3 (111 frames MPEG-1
contiguos) sí; `MediaError.code` es 4 para 404, 410, bytes corruptos y contenedor no soportado, así que un `onError` solo
mostraba "vencido" a las notas ogg/opus del paciente en Safari; `new AudioContext()` toma la frecuencia del dispositivo de
salida (8 kHz con un headset BT en HFP) y lamejs codificaba MPEG-2.5 que el server rechazaba sin explicación.
**Alternativas descartadas**: IF antes del UPDATE (el smoke no ejercitaría el UPDATE); seguir mandando `.m4a` de Chrome sin
verificarlo en iPhone/Android; `errorWorkflow` en Retención (ningún satélite lo usa; el Vigía ya vigila la ausencia de
filas); subselect directo a `retencion_log` en el Vigía (rompería la query entera mientras la tabla no exista).
**Revisable**: sí — `RETENCION_MAX_H` en `EVAL_JS`; el orden de `MIMES_GRABACION` en `lib/audio-mp3.ts` si Evolution/WhatsApp
confirman que reproducen el AAC fMP4 (entonces se podría saltear la transcodificación en Safari).

## 2026-09-07 (tarde) — Adjuntos del staff: la cadena Media va DESPUÉS del label, y el token por UPDATE
**Decisión**: (1) los 6 nodos `Media: * (staff)` cuelgan de `CW Set Label humano` (fin de la cadena de
silenciamiento), no de `Es fromMe?`[0]; la cadena de silenciamiento no se toca. (2) `Build fromMe AI memory` no se
modifica: el token ` [MEDIA:<id>]` se agrega con un UPDATE posterior acotado a una fila, y `Postgres - Save fromMe`
gana ` RETURNING id` para identificarla. (3) El filtro de grupos/`status@broadcast` vive en `media/preparar.js`
(las dos ramas), no en la IF del staff.
**Razón**: el label de Chatwoot es el ÚNICO mecanismo que calla al bot en la rama fromMe (los tres gates lo leen; no
hay Redis ni SQL de humano acá, y el nodo `Check Humano Reciente (DB)` no existe desde el 18/7). Cualquier cosa
delante de él — una subida de 5 MB, o el timeout de 30 s de Storage — puede dejar al bot escribiendo encima de la
doctora: la falla del incidente Mariela. Y `preparar.js` es el único punto donde el archivo todavía no se subió y
que comparten las dos ramas.
**Alternativas descartadas**: colgar la cadena Media de `Es fromMe?`[0] poniendo Chatwoot "primero en el array"
(depende de cómo n8n desempata dos ramas hermanas: array vs. posición en el canvas; no es una garantía); armar el
content con el token en `Build fromMe AI memory` (obliga a reescribir el nodo que contiene el TAG y el placeholder,
riesgo byte-a-byte, y a esperar la subida antes de guardar la memoria); poner el filtro de grupos en la IF del
staff (deja `preparar.js` capaz de subir un archivo de grupo si algún día se lo llama de otro lado); bajar el
timeout de Storage a 8 s (mitiga, no cierra).
**Revisable**: R13 — si molesta que un adjunto no se archive cuando Chatwoot no tiene la conversación, se puede
hacer que `CW Extract Conv` / `CW Pick Conv` emitan un item vacío en vez de `[]`; es un PUT aparte sobre la cadena
de silenciamiento, con su propia prueba.

## 2026-09-07 (tarde, 2ª ronda) — Whitelist de JID para el staff, y el token se rescata en el panel
**Decisión**: (1) en `media/preparar.js`, además de ampliar el blacklist a `@g.us` / `endsWith('@broadcast')` /
`endsWith('@newsletter')` (las dos ramas), la rama del STAFF exige un **JID 1:1**:
`if (ED.fromMe && !/@s.whatsapp.net$/.test(info.Chat)) return sinArchivo('grupo_o_estado')`. (2) El UPDATE del
token **falla cerrado**: sin el `id` que devuelve `Postgres - Save fromMe` no hace nada (se eliminó el fallback
heurístico por `session_id` + content). (3) El token perdido por el Logger se **rescata en el panel**
(`rescatarTokensMedia`), no en n8n.
**Razón**:
1. Un blacklist falla ABIERTO ante lo desconocido, y acá "abierto" significa subir un archivo del consultorio al
   bucket privado bajo el número de la propia clínica: `Edit Fields - Extraer Datos` recorre
   `[Chat, Sender, RecipientAlt, SenderAlt]` y se queda con el primero que termina en `@s.whatsapp.net`; si
   `Info.Chat` no es 1:1, ese primero es `Info.Sender` = la clínica, que pasa el guard de largo. Reproducido con
   el archivo real para `@broadcast`, `@newsletter` y `@lid`. Un whitelist cierra la familia entera de una, y las
   que WhatsApp invente mañana. Solo aplica al staff porque en la rama del paciente un `phone` `…@lid` es un 1:1
   legítimo que hoy se sube.
2. Con dos adjuntos SIN caption al mismo paciente, las dos filas de memoria tienen el `content` idéntico (TAG +
   placeholder): si el INSERT de la ejecución B entra antes del UPDATE de la A, el `ORDER BY id DESC LIMIT 1` de A
   toma la fila de B y viceversa — dos tokens cruzados, cada burbuja con la foto de la otra. En un chat médico
   mostrar la foto equivocada es peor que no mostrar ninguna. Y era código muerto: el `RETURNING id` siempre llega.
3. El Logger (`xsXeHp7WLXnFQc3o`, cron 5 min) copia la memoria a `conversaciones` con `ignore-duplicates`: escribe
   una vez y **nunca corrige**. Si cae dentro de la ventana INSERT→UPDATE, `conversaciones` queda sin token y el
   dedup por timestamp del panel descarta la fila de memoria que sí lo tiene ⇒ la foto no aparece **nunca más**
   (el problema no es cuándo se refetchea sino cuál fuente gana). Medido: dedup 190/190 en 3 días, ventana ~1,4 s
   por foto y hasta 30 s por video, 14,7 adjuntos fromMe/día ⇒ ≈1 perdido cada 2 semanas.
**Alternativas descartadas**: quedarse solo con ampliar el blacklist (cierra `@broadcast`/`@newsletter` pero deja
`@lid` y lo que venga); meter `@lid` en el blacklist compartido (rompe el caso legítimo del paciente, test 17b);
conservar el fallback agregándole `HAVING count(*) = 1` (más SQL para cubrir un camino que no se ejecuta nunca);
arreglar el Logger con `AND created_at < now() - interval '60 seconds'` en `PG - SELECT nuevos` (es un PUT a OTRO
workflow activo, fuera de la rama fromMe y del alcance autorizado — queda como plan B); confiar en el refetch a
1,5 s o en el poll de 20 s del panel (no sirven: la fuente que gana es `conversaciones`, no el momento del fetch).
**Revisable**: el tope de 8-15 dígitos del teléfono descarta un LID de 16-17 (los reales suelen ser de 15, y un jid
de grupo pelado son 18): si aparece un LID largo real, se sube el tope y se re-corre `test_media_nodos.js` §23. El
plan B del Logger sigue siendo válido si algún día se quiere que `conversaciones` también quede correcta.
