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
