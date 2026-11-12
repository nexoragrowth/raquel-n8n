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

## 2026-09-08 — Recordatorio de consultas: detección por `motivo_atencion`, precio vía el SQL del Gate, regex tolerante

**Decisión**: (1) una cita es consulta si `motivo_atencion` contiene "consulta" (i, trim); (2) el precio de la consulta se
lee de `knowledge_base` id 21 con una subconsulta en `Gate - Leer config` (no con un nodo nuevo) y `Preparar mensaje` lo
toma con try/catch, fallback `$50.000`; (3) el regex del precio es `/\$\s?(\d[\d.,]*)/` (+ recorte de punto final), NO el
`/\$[\d.,]+/` estricto del v6; (4) las columnas nuevas de `recordatorios_enviados` son nullable y las filas viejas quedan NULL.
**Razón**: (1) es el único campo que lo distingue (`tratamiento_sin_asignar` = 0 en 66/66; las consultas también traen
`nombre_tratamiento: 'Nuevo plan de tratamiento'`). (2) `Preparar mensaje` empareja la cita por
`$("Solo citas activas").all()[$itemIndex]`: cualquier nodo intercalado rompe el emparejamiento (regresión real del 11/8);
el Gate corre una vez por corrida y ya tiene credencial Postgres. (3) con el regex estricto, "$ 55.000" (espacio) caía al
fallback y el paciente recibía un precio VIEJO en silencio; el tolerante devuelve lo mismo que el v6 en todo lo que el v6
matchea. (4) 5 de las últimas 57 enviadas eran consultas: backfillear `false` sería mentir.
**Alternativas descartadas**: `tratamiento_sin_asignar` / `nombre_tratamiento` (no discriminan); nodo `Precio (KB)` antes de
`Preparar mensaje` (rompe `$itemIndex`); hardcodear `$50.000` (la Dra. lo edita en el panel); cambiar el regex del v6
para alinearlos (PUT al v6 fuera de alcance); `es_consulta NOT NULL DEFAULT false`.
**Revisable**: sí — si la Dra. confirma otro motivo para el puntito amarillo se ajusta la regla (un solo regex en
`recordatorios/preparar_mensaje.js`); si se suma el nodo de precio para el camino manual (R4), `Preparar mensaje` lo toma
como segunda fuente.

## 2026-09-08 (corrección, misma tarde) — Recordatorio de consultas: regex anclado al inicio y precio solo con importe real

**Decisión**: (1) `es_consulta = /^consulta\b/i` (anclado al inicio de `motivo_atencion` trimmeado) en lugar del substring
`/consulta/i` de la mañana; (2) el regex del precio pasa a `/\$\s*(\d{1,3}(?:[.,]\d{3})+|\d{4,})/`: cualquier cantidad de
espacios después del `$` y solo importes con miles (`dd.ddd`/`dd,ddd`) o de 4+ dígitos; (3) `--rollback` del script solo
acepta un archivo con `_PRE_` en el nombre cuyo 'Preparar mensaje' sea el snapshot vivo conocido; (4) el primer envío real
con el bloque nuevo se revisa a mano la mañana del primer cron post-apply (doc §6.4), con el rollback listo.
**Razón**: (1) el substring daba `true` para "Control post consulta" o "Consultar precio" → le pediría el pago de la
consulta a un paciente en tratamiento; con el anclaje el error posible es el inverso (una consulta con otro motivo recibe el
genérico de hoy, sin daño). Cubre el 100% de los motivos reales de Dentalink ('Consulta Ortodoncia '). (2) `\s?` dejaba
"$  70.000" en el fallback y `\d[\d.,]*` imprimía "$50" para "$50mil". (3) un `Recordatorio_POST_*.json` tiene el id
del WF y pasaba el guard: "revertir" desde ahí re-aplicaba. (4) la prueba manual por webhook no pasa por el Gate: el camino
KB → precio se ejercita por primera vez en producción, con un paciente real.
**Alternativas descartadas**: igualdad exacta con 'Consulta Ortodoncia' (más frágil ante un cambio de picklist en Dentalink);
`motivo_atencion || null` en la salida (no se pudo verificar punta a punta que el Postgres v2.6 acepte null, y el Insert
corre después del envío; Dentalink manda 'No registra motivo', no null); alinear el regex del v6 (PUT aparte, backlog P3);
sumar "Tipo: consulta" a la NOTA INTERNA de `Guardar en Chat Memory` (4º nodo, fuera del alcance declarado; backlog P3).
**Revisable**: sí — si la Dra. nombra un motivo de primera visita que no empiece con "consulta", se cambia la línea
`const es_consulta` de `recordatorios/preparar_mensaje.js` y los casos de motivo de `tests/test_recordatorio_consultas.js`.

## 2026-10-05 — Desacople Total de Chatwoot: Unificación en Supabase (`pacientes.human_takeover`)

**Decisión**:
1. Eliminar Chatwoot por completo de la ruta crítica del bot (`v6`), de las acciones del staff (`panel-acciones-staff`) y del escalador (`helper-notify-grupo`).
2. Establecer `pacientes.human_takeover` (booleano en Supabase v3) como la **Única Fuente de Verdad** del estado humano/bot de cada paciente.
3. Desactivar en n8n los flujos satélites `Human Takeover` (`w7BBpZeEwZnpCX1q`) y `Auto Reactivar` (`fosfga62zNaN0qrx`).

**Razón**:
1. **Eliminar el ghosting**: El desincronismo entre los labels de Chatwoot (`humano`) y el panel web hacía que mensajes legítimos de pacientes murieran en `Humano Atendiendo (no hacer nada)` en n8n sin que nadie supiera por qué.
2. **Performance y Latencia**: Se eliminaron 4 llamadas HTTP síncronas por cada mensaje entrante (búsqueda de contacto, lista de conversaciones, labels). El nuevo check es una consulta directa a Postgres que tarda ~30ms en vez de 1500ms.
3. **Mantenibilidad y Servidor**: Permite decomisionar el container de Chatwoot (Ruby on Rails + Redis + Postgres propios) en el VPS, ahorrando ~1.5 GB de RAM y complejidad operativa.

**Alternativas descartadas**:
- Mantener Chatwoot sincronizado bidireccionalmente con Supabase (complejo, propenso a carreras y fallos de red).
- Usar un flag en Redis (se pierde ante reinicios de container y no tiene persistencia relacional con el historial del paciente).

**Revisable**: No. La arquitectura converge definitivamente al Next.js panel (`nexora-whatsapp-agent`) conectado a Supabase.

## 2026-10-05 — Saneamiento Integral de Knowledge Base en Supabase (Eliminación de Placeholders Técnicos)

**Decisión**:
1. Purgar de la base de conocimiento vectorial (`knowledge_base`) cualquier concepto operativo interno o jerga de software: nombres de plataformas médicas (`Dentalink`), colores de agendas de consultorio (`punto amarillo flúor`, `punto verde`, `punto negro`) y comandos del bot (`/bot off`).
2. Eliminar la marca "ASIRI" del listado médico de sistemas de alineadores transparentes (ID 29). Dejar exclusivamente marcas reales de ortodoncia (Invisalign, Keep Smiling, Angel Aligner).
3. Modificar el plazo ilimitado de reserva a un horizonte estándar de consultorio médico (30 a 60 días de antelación máxima) en lugar de permitir reservas a un año vista (ID 2).
4. Re-vectorizar inmediatamente todos los registros actualizados con OpenAI `text-embedding-3-small` (1536 dimensiones) para que el RAG del bot recupere contexto coherente y fidedigno.

**Razón**:
Los embeddings de la base de conocimiento son consultados directamente por el LLM (`Sub-Agent General` vía `buscar_conocimiento`). Dejar instrucciones operativas de pantalla o software en texto plano provocaba que el modelo alucinara respondiendo al paciente sobre colores internos del calendario o inventara marcas comerciales ficticias.

**Alternativas descartadas**:
- Filtrar por prompt (inseguro y gasta tokens innecesarios).
- Borrar las filas por completo (hubiera quitado información necesaria sobre turnos y tipos de atención).

**Revisable**:
Sí, si la Dra. Raquel incorpora nuevas marcas de ortodoncia o define una ventana de agenda distinta.

## 2026-10-05 — El modo humano lo decide un solo mecanismo determinístico (flag + ventana de 24 h); la memoria no le da órdenes al LLM

**Decisión (Lucas, con propuesta de Claude):** el aviso `[ATENCION HUMANA …]` que se guarda en `n8n_chat_histories` cuando escribe el staff deja de incluir la orden "Mantente en silencio y NO respondas … hasta que un admin diga /bot on". Si el bot calla o responde lo decide `pacientes.human_takeover` + `human_takeover_at` (ventana de 24 h), leído igual en los tres puntos: entrada (`Consultar Takeover Paciente`), `Gate Humano Final` y `Triaje: Decidir`.
**Razón:** con pacientes reales (era A, 13 días) el bot callaba el 78% de las veces con el aviso en los últimos 4 turnos vs 20% sin él; el LLM trataba la memoria como un takeover oculto que no vence (ej. exec 289847: la paciente elige un horario y recibe `[NO_REPLY]`).
**Alternativas descartadas:** (1) tag `[Mensaje del staff del consultorio]:` — el panel detecta y parsea los mensajes del staff por el prefijo `[ATENCION HUMANA` y "enviado por X desde el PANEL"; (2) aplicar solo el cambio del texto sin unificar la ventana — pasadas las 24 h el agente corría (reservar_turno incluido) y el gate final descartaba el mensaje, dejando turnos reservados sin aviso.
**Efecto colateral aceptado:** las filas viejas de memoria conservan la orden hasta salir de la ventana de 10 mensajes (o hasta correr `scripts/sql_marcador_staff_filas_viejas.sql`).
**Revisable:** sí. Medir después: tasa de `[NO_REPLY]` con aviso reciente en las ejecuciones nuevas.

## 2026-10-05 — Las directrices de Asiri son datos en Supabase que el bot lee en cada mensaje (no prompts editados por PUT desde el panel)

**Decisión (Lucas pidió que lo editado en el panel cambie al agente; Claude propuso el mecanismo):** el panel guarda "directrices" (menú de bienvenida, indicaciones adicionales) en la tabla `agente_directrices` (Supabase v3); n8n las trae junto con la KB (`UNION ALL` de las filas `dir:<clave>` en `Get KB Horarios y Precio`) y los prompts las leen por expresión (`dir_menu_bienvenida`, `dir_notas`). El prompt completo solo se edita desde el panel por administradores (`PANEL_ADMINS`), con protecciones.
**Razón:** (1) un PUT de todo el workflow desde el panel puede pisar otro cambio simultáneo (ya pasó el 05/10 con el envío); (2) un textarea libre permite borrar variables `{{ }}` (precio, alias, horarios) y el bot sigue "andando" sin ese dato; (3) como dato queda con autor, historial y se aplica al instante; (4) coherente con "textos exactos en tabla" del roadmap B3 y con el triaje (`triaje_config`).
**El menú de bienvenida pasa a ser texto fijo** (deterministico, sin modelo ni Formatting Agent) cuando es un saludo solo en conversación nueva: lo que la Dra. ve en el panel es lo que recibe el paciente. Con conversación previa sigue por el agente General, que usa el mismo texto por expresión.
**Las respuestas fijas ahora se guardan en la memoria del chat** (antes no: el panel no las mostraba y el bot no sabía qué había mandado).
**Alternativas descartadas:** editar el prompt crudo con PUT desde el panel para todo el equipo; guardar las directrices como filas de `knowledge_base` (se vectorizan y aparecerían en las búsquedas; mezcla conceptos).
**Revisable:** sí. Pendiente de aplicar (ver current-state).


## 2026-10-06 — v7: un solo agente conversacional + herramientas de código (no sub-agentes LLM anidados)

**Decisión**: reemplazar el v6 (Router + 5 sub-agentes + sub-workflow if/else de cambios) por Asiri plano: un AI Agent que lleva toda la conversación y resuelve todo lo que el paciente demanda; escala a una persona solo si el paciente delega explícitamente, queja, baja de datos o urgencia (urgencia → triaje, no silencio). Herramientas = sub-workflows determinísticos; ninguna escritura recibe identificadores del modelo.
**Razón**: el problema es de arquitectura (el estado se adivina por regex sobre el último mensaje; cada arreglo rompe otra cosa); en 90 días el bot completó 1 cambio de turno; línea base p50 12 s / p95 48 s + 22 s de buffer.
**Alternativas descartadas**: (a) seguir parchando el v6; (b) sub-agentes LLM anidados estilo "parent agent": la revisión los descartó (ids elegidos por un modelo, ok escrito por un modelo, 20-30 s por respuesta). Quedan como opción si el examen de entrada muestra que plano no alcanza.
**Revisable**: sí, tras la sombra retrospectiva (modelo, latencia) y el examen vivo. Diseño: `docs/v7-arquitectura-agente-asiri.md`.


## 2026-10-06 — Cierres ("gracias", "ok", "si, gracias") se resuelven en código, antes del modelo

**Decisión**: en el v7 un agradecimiento o despedida puro no llega al modelo: el pre-filtro `esCierre` (`v7/historial_core.js`) devuelve silencio. Se anula si lo último que se le dijo al paciente pedía una respuesta (pregunta, recordatorio sin confirmar).
**Razón**: dos bugs reales de Irina (05-06/10): el Fallback Output del v6 reemplazaba el `[NO_REPLY]` del agente por "Ya le transmito su consulta a la secretaria…" y el Sub-Agent General contestaba "De nada! Quedo a disposición…". Pedir silencio por prompt no alcanza.
**Alternativas descartadas**: confiar solo en una regla de prompt (ya falló); volver al filtro conversacional del 27/05 (mataba "Confirmamos turno gracias"): por eso el filtro exige que el mensaje sean SOLO palabras de cierre.
**Revisable**: sí; si un paciente responde "si gracias" a un recordatorio pendiente y nadie confirma, se mide en la sombra.


## 2026-10-06 — Modo humano: ventana de 1 hora desde el último mensaje de una persona

**Decisión**: el bot vuelve solo 1 h después del último mensaje del personal. La ventana se mide con `pacientes.human_takeover_at`, que cada mensaje del personal renueva; el panel usa la misma (`HUMANO_MS`). El kill-switch admin (/bot off) sigue por encima.
**Razón**: pedido de Lucas ("post 1 hora sin que hable un humano que vuelva a modo bot, siempre sirvió"). La Dra. ya se quejó de 4 h ("queda mudo demasiado"). Al desacoplar Chatwoot se perdió el workflow que lo hacía y la ventana quedó en 24 h, y además el nodo que prende el flag está roto desde el 05/10.
**Alternativas descartadas**: reactivar `Auto Reactivar` con cron (depende de Chatwoot, y la ventana por timestamp no necesita cron).
**Revisable**: sí. Pendiente de aplicar con OK de Lucas.


## 2026-10-06 — Banlist del v7: se saca la regla "dirección sin que la pidan"

**Decisión**: `v7/banlist_usted.js` ya no bloquea por mencionar la dirección. Quedan las reglas de los incidentes graves: invitar a ir ahora o sin turno, instrucciones clínicas/medicación, diagnóstico y "le aviso si se libera".
**Razón**: en ~650 turnos de examen el banlist del v7 bloqueó 4 veces, todas por esa regla y en la variante con orquestador; en la que leí, el bot había ofrecido mandar la dirección, la paciente dijo "sí" y el filtro lo reemplazó por un texto genérico más un aviso a la clínica (peor que no filtrar). Dar la dirección no es un riesgo; "no dar la dirección salvo que la pidan" sigue en el prompt. Pedido de Lucas: explicarle al bot las reglas del negocio en vez de depender de listas.
**Revisable**: sí. La prueba retrospectiva sobre 90 días medirá falsos positivos de las reglas que quedan; si bloquean más de lo que atajan, se sacan.


## 2026-10-06 — Nombre y regla del diseño elegido: "Asiri orquestador"

**Decisión**: el v7 se llama "Asiri orquestador" (no "agente único"): una sola IA que entiende al paciente, decide qué workflow usar y es la ÚNICA que le escribe. Las herramientas son workflows que devuelven DATOS o textos armados por código; si alguna lleva una IA chica adentro (ej. elegir entre nombres parecidos), es para decidir y devolver un dato, nunca prosa para el paciente.
**Razón**: examen del 06/10 sobre 8 escenarios comunes: orquestador 20/24 repeticiones vs "orquestador con especialistas que escriben" 13/24 y más lento (mediana del peor turno 12,4 s vs 17,1 s). Las fallas de la variante con especialistas salieron de dos modelos escribiendo en fila (el padre reescribía la confirmación del especialista; el código tuvo que corregir 17 de 83 respuestas vs 9 de 82). Mismo patrón que Joaquín Basconi (agente + workflows; sus IA internas devuelven datos).
**Alternativas descartadas**: especialistas con su propio agente que redactan (`cerebro_ma`, `cerebro_mixto`): quedan en el repo, archivados, sin desplegar más.
**Revisable**: sí, con datos de la prueba retrospectiva y del piloto.


## 2026-10-07 — Pacientes nuevos: el alta la hace el código dentro de gestionar_turno

**Decisión**: un turno para alguien sin ficha se reserva igual. El modelo solo copia nombre, apellido y DNI que dio el paciente a `gestionar_turno`; el read-back los muestra y, con el "sí", el código busca el DNI, da el alta en Dentalink y reserva en la misma ejecución. Si la agenda rechaza el DNI, un reintento sin DNI y aviso para cargarlo a mano; ante cualquier duda (DNI de otra persona, error de red) no se escribe y se avisa ACCIÓN.
**Razón**: la retrospectiva del 06/10 marcó que era la única falta funcional del v7 frente al v6 (`crear_paciente_dentalink`), y los leads de anuncios son pacientes nuevos: derivarlos a la clínica corta la conversión. Buscar el DNI antes de crear evita las fichas duplicadas del v6; el DNI ahora sí llega a la agenda (GAP 7 / AGE-26 del v6).
**Alternativas descartadas**: herramienta aparte `crear_paciente` para el modelo (otra decisión probabilística y otro paso donde se puede cortar la charla); derivar el alta a la secretaria (pierde al lead fuera de horario).
**Revisable**: sí. El nombre del campo del DNI (`rut`) no está verificado contra la API real hasta la primera alta en vivo.


## 2026-10-07 — "No se preocupe" de la banlist solo en contexto clínico

**Decisión**: la regla "no se preocupe / no te preocupes" de `v7/banlist_usted.js` bloquea solo si el mensaje del paciente o la respuesta hablan de síntomas, aparato o dientes (o si no se conoce el mensaje del paciente). El resto de la banlist no cambia.
**Razón**: en la retrospectiva del 07/10 bloqueó una cortesía ("Disculpa, no vi los mensajes" → "No se preocupe…") y el paciente recibió "déjeme consultarlo con la clínica". El riesgo real (incidente del 09/05) es opinar sobre un síntoma; eso sigue bloqueado (test con el texto de Mariela).
**Revisable**: sí, con los bloqueos que registren el examen y la sombra.

## 2026-10-07 — Horarios nombrados sin buscar: los busca el código

**Decisión**: si la respuesta de Asiri nombra horarios que no salieron de la agenda y en la conversación no hay ningún bloque, el cerebro llama `buscar_horarios` antes de la salida y el chequeo pega el bloque real. Si no se puede, texto honesto + [ACCIÓN] a la clínica.
**Razón**: el chequeo ya frenaba bien el horario inventado, pero el reemplazo ("déjeme confirmar los horarios…") dejaba la conversación colgada (2/80 en la retrospectiva). Mismo camino que cuando el modelo se olvida de pegar el bloque.
**Alternativas descartadas**: reintentar el agente con una corrección (más lento y otra vez probabilístico).
**Revisable**: sí.

## 2026-10-07 — El orquestador entiende, elige y pega: los textos clave los arma el código

**Decisión**: además del bloque de horarios, el read-back y el mensaje final, `gestionar_turno` arma por código las preguntas de los momentos clave (cambiar o sumar, pedido de datos del paciente nuevo, para quién es, cuál turno) y una versión con otras palabras si el paciente contestó sin elegir. El modelo las pega; solo redacta libre en charla e información de los DATOS.
**Razón**: las fallas que quedaban eran de redacción del modelo en esos momentos (repetir la misma pregunta palabra por palabra en AGE-03). Lucas: "que el orquestador no tenga que laburar". No se agregó otra IA adentro de las herramientas (los especialistas que redactan ya midieron peor: 13/24 vs 20/24).
**Revisable**: sí, con el examen completo y el piloto.

## 2026-10-07 — "Que funcione como una app": el sí ejecuta lo que el paciente vio, sin preguntas de más

**Decisión**: (1) si el paciente ya tiene turno y pide otro, no se pregunta "¿cambiar o sumar?": se arma la confirmación de otro turno "además de su turno del…" y, si quería cambiarlo, lo dice ahí. (2) El "sí" a una confirmación ejecuta la confirmación guardada que el paciente vio, aunque el modelo mande otros datos. (3) Un "sí" a secas lo ejecuta el código sin pasar por el modelo.
**Razón**: captura de Lucas del examen: después de un "Sí" claro, Asiri volvió a preguntar "¿pasarlo o sacar uno más?" porque el modelo cambió el pedido entre las dos llamadas. La pregunta extra confundía y alargaba la charla; el "sí" directo además ahorra 4-8 s (una o dos vueltas del modelo).
**Alternativas descartadas**: mantener la pregunta cambiar/sumar con textos armados por código (seguía siendo un mensaje más y una fuente de ambigüedad).
**Revisable**: sí. Choca con la KB 17 ("un solo turno a futuro") si la Dra. la confirma: en ese caso, "pide otro turno y ya tiene uno" pasaría a ser cambio por defecto (la confirmación lo diría igual de explícito).

## 2026-10-07 — Pasar a una persona solo por urgencia o pedido explícito

**Decisión**: el bot se calla y pasa la charla a una persona solo si el paciente lo pide explícitamente (secretaria, doctora, una persona); las urgencias van al triaje. Una queja o un pedido de baja de datos se avisan a la clínica como [ACCIÓN] y el bot sigue atendiendo. Una duda o algo ambiguo nunca se deriva: se pregunta. Avisar a la clínica (comprobantes, presupuestos, turnos de menos de 48 h) no es escalar: el bot sigue.
**Razón**: pedido de Lucas: el v7 tiene que ser el sistema con el que el paciente resuelve su relación con el consultorio; escalar por ambigüedad es un fracaso de conversión. La verificación anterior de "pidió una persona" aceptaba cualquier mensaje con "Dra." o "secretaria".
**Revisable**: sí (si la Dra. quiere que las quejas callen al bot).

## 2026-10-07 — Se saca la banlist de frases (v6 y v7)

**Decisión**: sin banlist regex en la salida, ni en el v7 ni en el v6 ("lo controlamos con prompt; el banlist es bullshit, quitámelo en todo" — Lucas). v7: `banlist_usted.js` y su test borrados; la Salida ya no la usa. v6: `scripts/apply_quitar_banlist_v6.py` deja `Banlist Validator` como paso sin control (mismo nombre y salida de "no bloqueó", porque Split en Mensajes, Hay humano ahora? y Gate Humano Final lo leen) y desconecta/deshabilita la rama Banlist Shadow; el --apply lo corre Lucas (backup PRE, check_triaje, verificación).
**Razón**: en ~400 corridas de examen y 160 de retrospectiva la banlist del v7 solo frenó mensajes inocentes ("no se preocupe" de cortesía, "pase por favor su DNI", la dirección pedida) y su reemplazo ("déjeme consultarlo con la clínica") confundía al paciente; nunca frenó algo realmente peligroso.
**Qué cuida ahora lo que cuidaba**: el prompt (nunca invitar a ir ahora o sin turno; sin indicaciones clínicas ni diagnósticos; no prometer avisos) + el triaje de urgencias ANTES del modelo + el chequeo de salida (afirmaciones y horarios contra la agenda). Riesgo aceptado: si el modelo escribiera "acérquese ahora mismo", ya no lo frena el código (test Z7 sacado).
**Alternativas descartadas**: afinar los patrones (se intentó: "no se preocupe" solo clínico, "pase por" solo a un lugar, limpiar solo la frase) — seguían apareciendo falsos positivos.
**Revisable**: sí, si aparece en vivo una respuesta peligrosa.


## 2026-10-08 — Las herramientas del v7 solo escriben con `modo === 'vivo'` explícito

**Decisión**: todo lo que escribe afuera (Dentalink, recordatorios, avisos al grupo, memoria) exige `modo: 'vivo'` explícito; un modo ausente, vacío o cualquier otro valor es sombra. Aplica en `confirmar_turno` (nuevo IF "¿Es sombra?" antes del PUT y del UPDATE del recordatorio), `agenda_core.pasoInicial`, `clinica_core.decidir` y la Salida del cerebro; los `|| 'vivo'` del cerebro (sí directo, cierre) pasan a `'sombra'`. Tests: C10 (sombra) y C11 (sin modo) en `test_v7_grafo_herramientas.py`; los tests que daban "vivo" por hecho ahora lo pasan.
**Razón**: incidente del 06/10. El trigger de `confirmar_turno` no declaraba `modo`, n8n descartaba el campo y la herramienta confirmaba de verdad durante la retrospectiva en sombra: 11 citas reales quedaron en 18 y el recordatorio de la 9064, marcado. Con "sombra = `modo === 'sombra'`", un campo que no llega era vivo; ahora un campo que no llega no escribe.
**Alternativas descartadas**: solo agregar `modo` al trigger de confirmar (arregla este caso pero no el próximo workflow que se olvide el campo).
**Revisable**: no. Cualquier herramienta nueva que escriba tiene que declarar `modo` en su trigger y tener un test de sombra.

## 2026-10-08 — Asiri solo turnos e información del consultorio; lo demás, a la secretaria y modo humano si insiste
**Decisión (Lucas, feedback de la 4.ª corrida de reales)**: Asiri no conversa fuera de su función (turnos, confirmar/cancelar, info del consultorio). Fuera de tema (presupuestos, pagos en otra moneda, proveedores, temas personales o de terceros): una sola respuesta «Le paso con la secretaria para que lo atienda.» + avisar_grupo ACCION. Si insiste (2.º aviso ACCIÓN en 30 min), modo humano (tomar=true): el bot se calla en ese chat hasta que la clínica lo reactive (por ahora el Auto Reactivar del v6). Saludo → SIEMPRE el menú del panel; con turnos sin confirmar, el menú + una línea «responda Confirmo». Turno no encontrado con el nombre que dan → mostrar los turnos que figuran en el celular y preguntar.
**Razón**: REAL-08 (proveedor interrogado), REAL-09 (8 mensajes, 7 avisos), REAL-12 (saludo sin menú: lo había cambiado yo esa mañana). "Llevemos al usuario a donde queremos; la única función es la que le creamos" — Lucas.
**Revisable**: el modo humano "para siempre" se resuelve con el pipeline de estados del panel (próxima etapa).

## 2026-10-08 — Asiri nunca pide confirmación de asistencia
**Decisión (Lucas)**: "el bot no pide confirmación; hacer recordatorios y ahí confirma". Pedir confirmación es tarea exclusiva del workflow de Recordatorios. Asiri solo confirma cuando el paciente lo dice (confirmar_turno). Saludo → solo el menú del panel, sin línea de "tiene pendiente confirmar". El contexto del modelo dice "RECORDATORIOS YA ENVIADOS (sin respuesta; NO le pidas que confirme…)" en vez de "PENDIENTES DE CONFIRMAR" (que lo empujaba a preguntar, REAL-13). Prompt: "Vos nunca pidas que confirme su asistencia". Tests B6-B8, H6.
**Revisable**: no.

## 2026-10-08 — Health Check auto-reparable (post-incidente webhook vacío 06-08/10)
**Decisión**: el Health Check (`Yjl6kyLnALhIfbFX`) detecta y repara solo el webhook/eventos de la instancia `raquel` (POST /instance/connect con el token de la instancia, body armado con lo que la instancia ya tenía), con corte de reintentos (3 fallas → 1 cada 2 h), aviso si se repara 2+ veces en 24 h, alerta de "sin tráfico" en horas hábiles (con feriados) y nodos HTTP que no cortan la ejecución ante timeout. Lógica en `v7/health_core.js` (test `tests/test_health_core.mjs`), aplica `scripts/apply_health_check_autoreparable.py` (el `--apply` lo corre Lucas). Canal de mail si falla el WhatsApp: opcional con `--mail-a` (decide Lucas). Panel: `reconectarInstancia()` ya no manda body `{}` (causa raíz probable: Connect pisa el webhook con ""); pendiente deploy + env `EVOLUTION_WEBHOOK_URL` en Vercel.
**OJO**: la URL del webhook está FIJA en `health_core.WEBHOOK`. Si se cambia a propósito (v7, secreto por clínica), cambiar ahí primero y re-aplicar; si no, el Health Check la revierte en ≤ 30 min. La alerta "sin tráfico" depende de que alguien siga escribiendo `mensajes_entrantes_live` (hoy el nodo Inbox Live del v6): prerrequisito del cutover al v7.
**Descartado**: `errorWorkflow` = Error Handler (sale por el mismo WhatsApp y al grupo de la doctora, hasta 48/día; en su lugar try/catch → "[FALLO TECNICO]" a Lucas); `saveDataSuccessExecution: none` (rompe la simulación y el diagnóstico; la exposición del token en ejecuciones ya existía); chequear `active` del v6 desde el workflow (necesita una API key de n8n dentro de n8n).
**Revisable**: sí — quedan abiertos el canal fuera de WhatsApp (mail / monitor externo tipo healthchecks.io para "n8n caído"), el destinatario después de febrero y si se deja esta alerta de sin tráfico o la del Vigía.

## 2026-10-08 — La IA decide qué quiso decir el paciente; el código ejecuta y garantiza (nada de regex como juez de intención)
**Decisión (Lucas: "no vas a saber nunca cómo va a hablar el paciente, es jujeño; por eso la capa de inteligencia")**: una regex sobre el texto del paciente NUNCA decide la intención ni bloquea una acción que el modelo eligió. El modelo decide (eligiendo una herramienta); el código hace la acción exacta y, si duda, falla del lado seguro (no afirma cosas falsas), no del lado de "no hago nada".
**Aplicado**: datos bancarios → herramienta `datos_pago` (el modelo la llama con las palabras que sea; el código pega los datos exactos; único veto por código: dólares). `registrar_pago` ya no se bloquea por falta de palabras "de pago": registra y el aviso muestra las palabras TEXTUALES del paciente ("Asiri lo tomó como aviso de pago: «…»") en vez de afirmar "transfirió". Tests C6d-g, Z32-Z39.
**Regex que quedan (fallan del lado seguro, no juzgan intención)**: saludo/cierre → si no reconoce, contesta el modelo; `pidio_persona` → si no verifica, avisa sin silenciar; red flags de urgencia → capa extra antes del modelo, que también deriva.
**Revisable**: no. Toda regex nueva sobre el texto del paciente tiene que justificar por qué falla del lado seguro.

## 2026-10-08 — v7 = orquestador + sub-agentes con alcance estricto (reemplaza "un agente con herramientas")
**Decisión (Lucas, textual)**: "odio las regex; para algo tenemos el agente orquestador, para orquestar agentes; ponele bien los puntos y los límites a los sub agentes; 0 conversaciones; lo único que hacemos es agendar, reprogramar, cancelar, recordar, confirmar, recepcionar pagos, dar información del negocio y el servicio, y asistir urgencias con la info que tenemos; lo que salga de ahí es mala directriz".
**Diseño**: Orquestador (entiende y delega, no conversa) + sub-agentes Turnos / Pagos / Información / Urgencias, cada uno con sus herramientas-código (Dentalink, avisos, triaje). Fuera de alcance → derivación fija + aviso; insiste → modo humano. Ninguna regex decide la intención del paciente; el código queda solo para ejecutar y verificar (read-back, ejecución con el sí, chequeo de salida, modo sombra, datos bancarios). Doc: `docs/v7-orquestador-subagentes-2026-10-08.md`.
**Antes**: el 07/10 se había elegido un solo agente porque la variante con especialistas fue más lenta y no resolvió mejor; Lucas prioriza robustez ante cómo escribe el paciente sobre la velocidad.
**Revisable**: no sin Lucas.


## 2026-10-08 — Orquestador = UNA llamada con salida JSON + despacho por código (construido, sin desplegar)
**Decisión**: el v7 "cerebro" pasa a ser ORQUESTADOR + sub-agentes (Turnos, Pagos, Información, Urgencias). El orquestador es la IA que entiende al paciente, pero en UNA llamada (Basic LLM Chain, salida `{"pasos":[…]}`); el código despacha (una llamada por sub-agente y por mensaje) y compone la respuesta con los textos de las herramientas. Turnos, Pagos y Urgencias devuelven un CÓDIGO (no redactan); Información es la única que redacta (lista cerrada de temas). El "sí" lo decide Turnos (`confirma`) con el MENSAJE ACTUAL; el código manda a Turnos todo mensaje que llega con una confirmación pendiente vista (ruteo por estado). Fuera de alcance → derivar (contador propio `deriva:`; 2.º en 30 min → modo humano).
**Razón**: crítica técnica del diseño (latencia de 4-6 llamadas en fila, llamadas repetidas al mismo sub-agente, el orquestador redactando) y crítica de alcance (menú, Información abierta, falso "sí" por dos modelos en fila). Detalle: `docs/v7-orquestador-subagentes-2026-10-08.md` §8.
**Se borraron** (código de juicio de intención): reconocedor de "sí" y "sí directo" (`agenda_core`), cierre/saludo/pedido de info (`historial_core`), VERIF y motivos queja/baja (`clinica_core`), veto de dólares sobre el texto, DIJO_AVISO/RE_PRESENTA/RE_DECILE de la Salida. Queda validación de DATOS (cita en el mensaje, dígitos del DNI) que falla del lado seguro.
**Alternativas descartadas**: orquestador AI Agent con sub-agentes como herramientas (2 llamadas más del orquestador, no se puede probar offline, puede redactar); agente único (Lucas: "para algo tenemos el orquestador").
**Revisable**: sí, con la batería de ruteo con el modelo real y la sombra (p95, examen ≥ 38/45).

## 2026-10-14 — Toda cita de prueba se anula al terminar la prueba
- **Decisión (Lucas):** al cerrar cualquier prueba, se anulan en Dentalink las citas que existan por ella (creadas a mano, reservadas o reprogramadas por el bot) y se borra su recordatorio sembrado. Si otra prueba necesita una cita, se crea de nuevo.
- **Razón:** una cita de prueba ocupa un horario que podría tomar un paciente real.
- **Descartado:** mantener una cita de prueba fija con la nota "NO ANULAR NI MOVER" (lo que se hacía desde el 07/10).
- **Revisable:** no. Agregado a la regla 9 de `.claude/CLAUDE.md`.

## 2026-10-15 — Toda acción que cambia la agenda se confirma antes con el paciente (regla dura)
- **Decisión (Lucas):** "ante cualquier acción destructiva consulta": agendar, cancelar y reprogramar (y cualquier otra que escriba en la agenda) requieren un read-back explícito ("Le confirmo… ¿Procedo?") y el "sí" del paciente ANTES de ejecutarse. Vale para el v6 mientras atienda y para el v7.
- **Razón:** incidente del 14/10 (el v6 anuló un turno vigente al leer "tuve que cancelar el turno", que hablaba de uno anterior).
- **Revisable:** no.

## 2026-10-16 — Precios por WhatsApp: solo la consulta (Dra.)
- **Decisión (Dra., grupo 16/10 8:27):** en precios y formas de pago solo el valor de la consulta ($50.000) y "aceptamos efectivo y transferencia". La cuota mensual y el retenedor NO se dicen (los informa la secretaria). Reemplaza la D7 del plan ("cuota solo a contactos con ficha"): la cuota no se da a nadie por WhatsApp.
- **Aplicado:** `scripts/apply_precios_solo_consulta.py` (KB 23/36/39 + embeddings; v6 "Sub-Agent General" DATOS OFICIALES; backups data/kb_backup_precios_1792151368.json y workflows/history/O155MqHgOSaNZ9ye_PRE/POST_precios_solo_consulta_1792151368.json; v6 versionId 4053a7d9). Probado en vivo v6 y v7: "$50.000 … efectivo y transferencia", sin cuota ni retenedor.
- **Revisable:** solo por la Dra.

## 2026-10-20 — El v7 (orquestador) atiende a TODOS los pacientes
- **Decisión (Lucas, 19/10):** "poneme asiri nueva" para todos, ya. Mecanismo: llave Redis global `v7:global = 'vivo'` leída por el v6 (`scripts/apply_v7_para_todos.py`, `scripts/v7_global.py`). La marca por número sigue: `v7:tel:<tel> = 'off'` deja a un número en el v6.
- **Razón:** el v6 resuelve un pedido por mensaje (Router → un sub-agente); los pedidos múltiples terminan en la secretaria (escalación 375).
- **Descartado:** seguir parchando el v6 pedido por pedido; esperar a BOT-01/BOT-07 antes de prender (se corrigieron BOT-01 en caliente la misma noche).
- **Revisable:** sí — vuelta atrás inmediata con `v7_global.py --off`.

## 2026-10-20 — Orquestador del v7 con razonamiento "medium" (era "low")
- **Razón:** con "low", 2 de 4 pedidos múltiples en vivo se rutearon mal (318950, 318965). Más una red por código: si el pedido del orquestador menciona alias/CBU y no hay Pagos, Pagos entra igual.
- **Costo:** algo más de latencia del orquestador (el buffer de 22 s ya la absorbe).
- **Revisable:** sí, si la latencia molesta o si un modelo mejor rutea igual de bien con menos.

## 2026-10-20 — Lista semilla: cargados los 11 que clasificó Lucas (sin OK explícito de la Dra.)
- **Qué:** `cargar_lista_semilla.py --apply --ok-dra` cargó los 11 contactos que Lucas clasificó él mismo el 14/10 (2 interno, 6 proveedor, 3 colega; ninguno con ficha). Las 14 propuestas que armó Claude solo por el nombre y los 12 dudosos NO se cargaron (el bot les sigue respondiendo; se clasifican desde el panel).
- **Ojo:** el flag `--ok-dra` se pasó por orden de Lucas del 20/10 ("todo lo de segmentación"), NO porque la Dra. haya respondido: su OK nunca quedó registrado. Contárselo a la Dra. con la lista; si objeta a alguno, se lo vuelve a paciente desde el panel o `cargar_lista_semilla.py --deshacer --apply` cierra los 11.
- **Red:** proveedores y colegas tienen la red de seguridad (urgencia → aviso al grupo); los 2 internos no.
- **Revisable:** sí (Dra.).

## 2026-10-20 — Contactos no pacientes etiquetados por Claude (pedido de Lucas)
- **Qué:** 17 contactos con tipo que silencia, autor "claude", evidencia en la nota (comercio por nombre, o mensajes de proveedor/insumos). Ninguno con ficha. Lista y criterio en current-state del 20/10.
- **Criterio:** silenciar solo con evidencia clara de no-paciente; ante nombre de persona sin evidencia, NO (el bot sigue atendiendo). Caso que lo justifica: …3000 figuraba como "publicidad" y manda comprobantes de pago.
- **Revisable:** sí — cualquiera se vuelve a paciente desde el panel.

## 2026-10-20 — Búsqueda de mensajes del panel sin índice (por ahora)
- **Medido:** 54 ms de mediana y 190 ms en el peor caso sobre 10.499 filas (escaneo secuencial). Con `pg_trgm` disponible pero no instalado.
- **Regla del patrón:** la búsqueda no cuenta lo que dice el marcador "[ATENCION HUMANA - … doctora/secretaria … WhatsApp del consultorio]" (3 de cada 4 filas lo llevan) y deja afuera notas internas, [NO_REPLY] y avisos de adjunto sin texto.
- **Revisable:** sí, al acercarse a ~50.000 filas (índice trigram).

## 2026-10-20 — D3 en vivo: charla iniciada por la clínica con un contacto sin ficha = Asiri no se mete
- **Regla:** si el primer mensaje guardado del chat es del staff y Dentalink no tiene ficha para ese celular, el v7 no responde, no deriva y no avisa al grupo (la secretaria ya está en esa charla). Urgencias: siguen (pre-triaje del v6 + Urgencias del orquestador).
- **Por qué ya y sin sombra:** en un solo día cayeron 7 escalaciones al grupo de contactos así (plomero, proveedores, técnico); medido sobre 114 contactos, los que parecían pacientes tenían ficha.
- **Riesgo aceptado:** un prospecto al que la secretaria escribió primero no recibe respuesta de Asiri (la atiende la secretaria).
- **Revisable:** sí; vuelta atrás = sacar el bloque `charla_de_la_clinica` de `despachar` y redeploy.

## 2026-10-28 — El control de la clínica sobre Asiri = Conocimiento + instrucciones de Información + MENSAJES FIJOS (no prompts de Turnos/Pagos)
- **Qué:** se agregó un editor de 12 mensajes fijos (filas `msg_<CLAVE>`), con validación doble, vista previa, historial y "volver al estándar". No se agregó un cuadro de instrucciones para Turnos/Pagos/Urgencias/orquestador.
- **Por qué:** esos agentes devuelven códigos y NO redactan lo que lee la paciente; editar su prompt no cambia el mensaje (placebo) y sí puede romper el agendado. Lo que la paciente lee de Turnos/Pagos sale de `TEXTOS` y eso es lo que la clínica sí quiere cambiar.
- **Descartado por ahora:** (a) variantes rotativas de cada mensaje (anti-repetición): el corte de bucle compara TEXTOS iguales; con variantes dejaría de cortar. Primero hay que comparar por clave de mensaje. (b) "Redactor" con modelo (el código decide, el modelo redacta, el código verifica hechos): más inteligente pero más riesgo; recién después de la capacitación en vivo con las secretarias, en sombra y con verificación de hechos (sin banlist de frases, decisión del 07/10).
- **Revisable:** sí. Vuelta atrás: dejar vacías las filas `msg_*` (el bot usa el estándar) o restaurar el backup PRE del Cerebro.

## 2026-10-28 — Un audio transcripto es un mensaje normal; "pedir texto" solo si no hubo transcripción
- **Regla:** el cerebro recibe `[AUDIO] <transcripción>`; solo `[AUDIO]` sin texto se contesta pidiendo que lo escriban. Si el orquestador pide texto para un audio transcripto, el código lo deriva a la secretaria con lo que dijo (nunca "no puedo escuchar").
- **Por qué:** caso real 27/10 09:18 hora Jujuy (12:18 UTC); el v6 transcribía y procesaba el texto, el v7 lo perdió en la migración.
- **Revisable:** sí (`audio_transcripto` en `despachar`).

## 2026-10-28 (2.ª) — REVIERTE la decisión de la mañana: la clínica SÍ controla los prompts de los agentes
- **Qué:** el panel vuelve a dar control sobre los prompts de los agentes (orquestador, Información, Turnos, Pagos, Urgencias) además del conocimiento. Diseño: esqueleto bloqueado en el repo + partes editables (`prm_*` en `agente_directrices`), leídas en cada mensaje, con fallback al texto del repo. Lógica de negocio/arquitectura se cambia aparte con Claude Code.
- **Por qué:** pedido explícito de Lucas ("es importante poder controlar todo… directriz (prompts agents) como conocimiento"); el editor del v6 se había borrado sin su OK (BOT-14 pedía solo avisar/bloquear); mi argumento "placebo" valía para la redacción pero no para el ruteo ni para Información.
- **Descartado:** reeditar el workflow por API como el panel viejo (el prompt del orquestador vive dentro de un nodo Code y los otros dentro de un literal JSON en una expresión; los `apply_*` lo pisarían; viola "cero PUT sin backup" en runtime); prompt completo editable (rompe el contrato de salida; causa raíz 2 del 9/5 fue texto contradictorio).
- **Revisable:** sí.

## 2026-10-28 (3.ª) — Un comprobante marcado por la entrada siempre pasa por Pagos; alias de agentes; sticker/emoji = silencio; mensaje mixto se parte
- **Qué:** red por estado (`comprobante_marcado`, estructura que arma el sistema) + alias cerrados de nombres de agente + 3 líneas del prompt del orquestador (sacar "informa algo"; sticker/emoji a silencio; parte fuera de alcance a derivar y el resto a Información).
- **Por qué:** auditoría v6→v7 (casos reales 23/10 ejec 321861, 26/10 "payments", 22/10 sticker; derivación de más medida).
- **Estado:** en el repo y probado; deploy pendiente del OK de Lucas.
- **Revisable:** sí.

## 2026-10-28 (4.ª) — El modo humano dura 1 hora (confirmado por Lucas); NO se extiende a 24 h
- **Qué:** queda la ventana de 1 h tras un mensaje del staff. Se descarta la propuesta D3 de 24 h.
- **Medido:** de 27 respuestas del v7 dentro de las 24 h posteriores a un mensaje del staff, 23 fueron pasada la hora (64 min a 23,6 h: el silencio ya había vencido, por diseño) y 4 en el mismo minuto del mensaje del staff (carrera: la secretaria escribe mientras el cerebro procesa; Gate Humano Final falla abierto).
- **Cómo se ataca:** (a) las 23: regla del prompt del orquestador "le contesta al STAFF sin pedirnos nada nuevo, aunque cuente algo → no_reply" (en el repo, deploy pendiente); (b) las 4: arreglar la carrera en Gate Humano Final (backlog).


## 2026-11-05 — REVIERTE "no resolver lo que el paciente le contesta al staff" SOLO para ACEPTAR un cambio de turno que propuso la clínica
- **Qué:** si lo último que no escribió el paciente es un mensaje del staff escrito a mano (< 48 h) que propone MOVER su turno (verbo de cambio + hora + turno/horario/cita/control; no "agendar el próximo turno"), y el paciente no lo contestó todavía (según `mensajes_entrantes_live`, que el v6 llena aunque Asiri calle o esté en modo humano), el contexto muestra PROPUESTA DE LA CLÍNICA. Si el paciente la ACEPTA, Turnos llama `aceptar_propuesta_clinica` copiando del mensaje de la clínica fecha y hora nuevas, la fecha del turno que se mueve y para quién. El CÓDIGO verifica cada dato contra el texto crudo del staff y contra la agenda (como el DNI) y: (A) si la agenda ya está así y no queda otro turno suyo esas fechas → "Perfecto, … queda el …" sin escribir + FYI; (B) si no → read-back del cambio (fecha y hora primero) y recién con el "sí" se escribe por la tubería de siempre; (C) cualquier duda → no toca nada y deriva con el motivo exacto.
- **Por qué:** pedido de Lucas ("que lo gestione hasta llegar al outcome del requerimiento del paciente") tras el incidente José (04/11 22:50, ejec. 331590/331596): Iri había movido el turno el 02/11 y preguntó; el paciente dijo "Dale hagamos el cambio"; `decidir` no tenía camino (tipo_invalido → no_ofrecido) y en el 3.er intento el modelo mandó `confirma` booleano → el esquema tumbó al agente → "tuve un inconveniente". Medido 23/10–05/11: ~2 propuestas de horario del staff por semana, el bot falló 3 de 4 (más 4 casos del v6 en sep/oct).
- **Diseño descartado:** que el CÓDIGO leyera fecha y hora del texto libre (primera versión del 05/11). La revisión adversarial lo rompió con "8 y 40", "6 de la tarde", "al 19", y adivinaba el turno viejo (podía mover el de otra ficha). Queda: el modelo lee, el código verifica.
- **Lo que NO cambia:** la regla dura del read-back; el staff que solo pide confirmar asistencia sigue por `confirmar_turno`; turnos NUEVOS propuestos por el staff los agenda la secretaria.
- **Rechazos:** un rechazo, duda o "gracias" a la propuesta → silencio, sin aviso (la secretaria está en esa charla; misma lógica que "le contesta al STAFF" del 28/10). Un saludo solo, con la propuesta sin responder, no recibe el menú.
- **Excepciones explícitas en esta ruta:** el horario no sale de `buscar_horarios` (lo propuso la clínica) y la regla de 48 h no se aplica (es política para cambios que pide el PACIENTE). [DECIDE LUCAS si quiere volver a exigir 48 h.]
- **Derivan (sin tocar la agenda):** varias fichas sin nombre en el mensaje, hora o fecha que no figuran en el mensaje, fecha que no coincide con el día de la semana, dos turnos posibles, posible duplicado, hora fuera de 07–21, horario pasado, más de 48 h.
- **También:** `confirma` se pide como la palabra "si"; al ejecutar se re-chequea que el horario no haya pasado (vale para todos los cambios); el [ACCIÓN] de un agente caído trae el detalle técnico.
- **Pendiente conocido (no lo crea este cambio, lo hace más visible):** al anular la cita vieja, su fila de `recordatorios_enviados` queda abierta; un "Confirmo" posterior puede elegir la cita anulada (ConfirmarCore). Afecta igual a los cambios que ya hacía Asiri. → backlog.
- **Revisable:** sí. Vuelta atrás: backups PRE de `scripts/apply_propuesta_staff.py` con `restaurar_workflow.py` (orden inverso).

## 2026-11-11 — La entrada descarta mensajes con más de 15 min de atraso (lo aplicó Lucas)
- **Qué:** paso 4 del "Webhook Validator" de O155: si `info.Timestamp` tiene más de 15 min, el mensaje se descarta sin respuesta.
- **Por qué:** WhatsApp estuvo cortado del 09/11 (mediodía) al 11/11 (~13 h). Al reconectar, Evolution entregó mensajes del lunes y el bot los contestó a las 00:35 y 01:25; la Dra. se quejó.
- **Dónde:** copia del workflow vivo en `workflows/history/O155MqHgOSaNZ9ye_POST_descartar_atrasados_lucas_2026-11-11.json` (el script `apply_v6_descartar_atrasados.py` que cita el comentario no está en el repo).
- **Pendiente:** segundo canal de alertas (el corte pasó 2 días sin que nadie lo note) y revisar los recordatorios del 10/11 y 11/11.

## 2026-11-12 — Antes de desplegar, el generado tiene que ser igual a lo vivo salvo lo que se quiere cambiar
- **Qué:** todo `apply_*` que pisa workflows vivos muestra el diff nodo por nodo contra lo vivo (como `apply_arreglos_espejo.py`); si aparece algo que no es el cambio buscado, se frena y se trae lo vivo al repo primero.
- **Por qué:** el 05/11 se desplegó la "propuesta de la clínica" (incidente José) sin commitearla; un despliegue desde el repo la hubiera borrado sin aviso. Se encontró el 12/11 al simular.
- **Revisable:** no (es una guarda).

## 2026-11-12 — El espejo del Cerebro Agente se hace con mensajes reales re-jugados, no en paralelo en la entrada
- **Qué:** `extraer_reales.py --contexto` + `correr.py`: mensaje real + historial + fichas/turnos reales copiados (ids falsos) a un celular sintético, en sombra.
- **Por qué:** el espejo en paralelo usa el teléfono real y pisa las claves de Redis del bot vivo (ofertas, propuesta, bloque): el paciente podría quedar sin poder elegir el horario que le ofreció el bot de verdad. Además no requiere tocar la entrada O155.
- **Descartado:** nodo en O155 que llame al agente con `modo: sombra` (necesitaba claves aparte en todos los workflows).
- **Revisable:** sí, si algún día se separan las claves de sombra.

## 2026-11-12 — Freno por código: no se despliega encima de cambios que el repo no conoce
- **Qué:** `scripts/guarda_vivo.py` envuelve todos los `api()` de scripts/: antes de cada PUT compara la huella de lo vivo (nodos + conexiones) con la última registrada en `workflows/vivo_huellas.json`; si no coincide, frena y dice qué nodos cambiaron. Después del PUT registra la nueva. `scripts/diff_vivo.py` compara repo vs vivo parámetro por parámetro (antes los apply_* miraban solo jsCode y no veían prompts ni descripciones de herramientas).
- **Por qué:** despliegan dos compus. El 05/11 se desplegó desde la otra sin subir; desplegar desde acá lo borraba sin aviso. Una regla en memoria no alcanza (la otra compu no la ve hasta hacer pull); el freno sí actúa.
- **Descartado:** comparar con el último backup de `workflows/history` (está en .gitignore: cada compu tiene los suyos, y el PRE recién escrito tapaba el cambio). Usar `versionId` de n8n (cambia también con cosas que no son el código).
- **Escape:** `N8N_ACEPTAR_VIVO=<id>` solo después de traer lo vivo al repo y revisar el diff.
- **Revisable:** no (es una guarda).
