# Cómo ofrece los turnos el bot — formato pedido por la Dra. Raquel (2026-09-07)

**Fecha**: 2026-09-07 · **Estado**: implementado, revisado y probado en **dry-run** contra los tres workflows vivos,
tests verdes (87 checks en `tests/test_turnos_formato.js`, más `test_media_nodos` / `test_media_fromme` /
`test_retencion_y_staff` / `test_triaje_nodos` sin regresiones). **Falta el OK de Lucas para `--apply`.**

- Script: `scripts/apply_turnos_formato_raquel.py` (`--dry-run` por defecto, `--apply`, `--rollback`)
- Código fuente único de los nodos: `turnos/*.js` y `turnos/parches/*`
- Reemplazos de prompts: `prompts/v6_partials/turnos/*.antes.md` / `*.despues.md`
- Tests: `node tests/test_turnos_formato.js`

---

## 1. El pedido, textual

Por WhatsApp, la dueña del negocio:

1. *"Al momento de ofrecer los turnos no es necesario que diga dentalink 😅 los pacientes no conocen el sistema"*
2. El agente debería responder así:

```
Tenemos los próximos turnos disponibles: 
Por la mañana:
* Jueves 8 de septiembre 9:20 , 10:40
* Viernes 10 de septiembre 8:00

Por la tarde
* Miércoles 15 de septiembre 15:00 , 15:40
* Lunes 24 de septiembre 17:00

Le sirve alguno?
```

3. *"Por lo menos ofrecer dos de la mañana y dos de la tarde, los más próximos con la estructura que te envié"*
4. *"Otra cosa muy importante ❌ no preguntar que franja de horario le viene bien ni en que fecha específica quiere el
   turno, porque nosotros atendemos en horarios y dias específicos por lo que mayormente puede que no coincida con la
   necesidad del paciente"*
5. *"Por lo tanto, solo procedemos en decirles que turnos disponemos y ellos eligen de acuerdo a esas opciones"*

### Las capturas que lo motivaron (bugs reales del 07/09)

| # | Lo que hizo el bot | De dónde salía |
|---|---|---|
| 1 | "Tengo disponibles en **Dentalink** los siguientes turnos próximos: 24 de Septiembre 8:00 hs / 24 de Septiembre 8:40 hs / 24 de Septiembre 9:20 hs. Le sirve alguno?" (nombra el sistema, todo en una línea, los 3 del **mismo día** y todos de mañana) | `Step 6b-out: Ofrecer Slots`, línea 39 del jsCode, en el **sub-WF CancelarReprogramar** |
| 2 | La paciente contesta "A la tarde" y el bot **repite los mismos 3 turnos de mañana** | `Step 6b-prep` pedía UN solo día de agenda y `Step 6b-out` nunca filtraba por franja (recibía `franja`/`hora_minima` y los ignoraba) |
| 3 | "Para reprogramar su turno del Miércoles 9 de Septiembre a las 16:10 hs, qué día o franja le viene mejor? (mañana / tarde / fecha concreta)" | `Step 5: Decidir Accion Ejecutable`, línea 100 |

**Dato clave que cambia el alcance**: las tres salen del **Sub-WF CancelarReprogramar** (`5cAWJxiWJ50hxEq3`), no del
`Sub-Agent Cancelar` del v6 — ese nodo está **huérfano** (no tiene ninguna conexión `main` de entrada: es código muerto).
El `Switch sobre Intent` manda `cancelar_o_reprogramar` a `Execute Sub-WF Cancelar`, y ese sub-workflow tiene su
**propia** búsqueda de agenda. Arreglar sólo el v6 y "Buscar Horarios" habría dejado las tres capturas idénticas.

---

## 2. El formato final

```
Tenemos los próximos turnos disponibles:
Por la mañana:
* Jueves 24 de septiembre 8:00 , 8:40
* Martes 29 de septiembre 8:40 , 9:20

Por la tarde:
* Miércoles 30 de septiembre 16:20
* Lunes 5 de octubre 15:00 , 15:40

Le sirve alguno?
```

(ese bloque es **real**: sale de correr el `Format Slots` nuevo con la agenda que devolvió Dentalink hoy 07/09)

Reglas, todas determinísticas en `turnos/format_slots.js`:

- **mañana** = `hora_inicio < 13` · **tarde** = `hora_inicio >= 13`.
- Hasta **2 días por franja** (los más próximos) y hasta **2 horarios por día**, agrupados en una línea separados por
  `" , "` — exactamente la forma del ejemplo de la Dra. ("9:20 , 10:40").
- Día de la semana con mayúscula inicial y **mes en minúscula**; hora `H:MM` **sin cero adelante y sin "hs"**.
- Línea en blanco entre secciones y antes del cierre; el bloque cierra siempre con `Le sirve alguno?`.
- Si una franja **no tiene ningún turno**, se omite la **sección entera** (encabezado incluido) y no se inventa nada; el
  `resultado` que lee el LLM le avisa explícitamente que no la invente.
- Si no hay turnos en ninguna franja: `bloque` vacío y `resultado` = `SIN TURNOS … escala con escalar_a_secretaria`.
- Si la agenda no respondió: `ERROR_TECNICO … NO afirmes que no hay turnos` (nunca se miente por un timeout).
- **Nunca** aparece la palabra Dentalink en ningún camino (ni en el bloque, ni en el `resultado`, ni en los prompts, ni
  en los canned). Está testeado en los 5 caminos.
- El bloque **no contiene `---`**: ese es el separador con el que `Split en Mensajes` parte la respuesta en varios
  mensajes de WhatsApp.

- **`Por la tarde:` va con dos puntos.** La Dra. escribió `Por la mañana:` con dos puntos y `Por la tarde` sin. Se
  eligió la simetría a propósito (las dos secciones con `:`). Queda dicho acá para que nadie lo "corrija" después
  creyendo que es un typo.

`Format Slots` devuelve además, para depurar: `total_manana`, `total_tarde`, `dias_escaneados`, `paginas`,
`siguiente_desde` (la fecha para pedir el próximo lote) y `errores`.

### Desde dónde arranca el lote siguiente

`siguiente_desde` = el día siguiente al último día ofrecido de la franja que **termina antes** (el **mínimo** de las dos
secciones), no al último de todos. La tarde siempre cae más lejos (la Dra. atiende tarde sólo lunes y miércoles), así
que arrancar después del último turno de *tarde* se saltea mañanas más próximas que el paciente nunca vio. Medido con la
agenda real del 07/09: el bloque ofrece mañanas 24/09 y 29/09 + tardes 30/09 y 05/10; con el máximo el lote 2 arrancaba
el 06/10 y las mañanas del **01/10 y 02/10 no se ofrecían nunca** (estaban en los slots ya acumulados). Con el mínimo
(`2026-09-30`) el lote 2 sale así, verificado contra la agenda real:

```
Por la mañana:
* Jueves 1 de octubre 9:20 , 10:00
* Viernes 2 de octubre 8:30 , 9:10

Por la tarde:
* Miércoles 30 de septiembre 16:20
* Lunes 5 de octubre 15:00 , 15:40
```

**Contrapartida asumida**: la franja que se extiende más lejos (la tarde) se repite en el lote 2 mientras esos turnos
sigan libres. Se prefirió repetir un turno ya mostrado antes que no ofrecer nunca el más próximo, porque "los más
próximos" es literal en el pedido de la Dra. Cerrarlo del todo pide un `desde` **por franja** (o una lista de días ya
ofrecidos), que complica el contrato de la tool; queda anotado como posible siguiente paso.

### El choque del "hs"

El prompt vigente exige **hora SIEMPRE con "hs"** y el formato de la Dra. escribe `9:20 , 10:40` **sin** "hs". Manda el
formato de la Dra. **dentro del bloque**. La regla del prompt quedó con una excepción explícita: el "hs" sigue siendo
obligatorio **fuera** del bloque (cuando el bot menciona un turno suelto en una frase: *"le confirmo el Jueves 24 de
septiembre a las 8:00 hs"*) y **no aplica adentro del bloque copiado**. Lo mismo en el `Formatting Agent` (REGLA #0.b,
que gana sobre su REGLA #3).

**La regla es binaria y hay que leerla así**: o el bot pega **el bloque entero sin tocarlo** (y ahí no hay "hs"), o
escribe **una frase normal con "hs"**. Lo que NO puede hacer es copiar una línea suelta del bloque (`* Lunes 5 de
octubre 15:00 , 15:40`) como respuesta: esa respuesta **no lleva la marca** `turnos disponibles:`, así que no la
desvía la 3ra condición de `Necesita Formatting?` ni la protege el guard de `Split en Mensajes` — pasa por el
`Formatting Agent`, que le aplica su REGLA #3 y la convierte en *"Lunes 5 de Octubre 15:00 hs, 15:40 hs"*. El paciente
vería dos formatos distintos en dos mensajes seguidos, y la instrucción del prompt sería inejecutable. Por eso los tres
fragmentos que hablan de franjas (`agendar_paso5`, `agendar_regla_17hs`, `agendar_regla_franja`) mandan responder
*"Por la tarde tengo el Miércoles 30 de septiembre a las 16:20 hs y el Lunes 5 de octubre a las 15:00 hs. ¿Le reservo
alguno?"*, y `agendar_formato_horas` lo dice explícitamente: el "hs" va **incluso cuando repetís un turno que salió del
bloque**. Hay un test que lo verifica sobre los archivos de los partials.

---

## 3. Qué cambió, nodo por nodo

### A) `GuDQ9VmKWZvQnerV` — "Sub-WF - Buscar Horarios Validado" (ACTIVO, 6 → 22 nodos)

```
Cuando llama Agendar ─► Validar fecha ─► Fecha valida? ─[false]─► Output Error
                                              │
                                            [true]
                                              ▼
GET Horarios Dentalink ─► Acumular P1 ─► Faltan turnos? P1 ─[true]─► GET Horarios P2 ─► Acumular P2 ─► …
                                                  │                                          │
                                              [false]                                     (ídem P2…P5)
                                                  ▼                                          ▼
                                            Format Slots ◄────────────────────────── Acumular P6
```

La cadena tiene **6 páginas**: `Acumular P1…P6`, `Faltan turnos? P1…P5` y `GET Horarios P2…P6`. Cada `Faltan turnos?`
corta por la salida `false` (→ `Format Slots`) apenas hay 2 días con mañana **y** 2 días con tarde.

| Nodo | Qué cambia |
|---|---|
| `Cuando llama Agendar` | el schema pasa de `{fecha}` a `{fecha, desde}`, los dos **opcionales** |
| `Validar fecha` | sin fecha (o con una inválida/pasada/a más de 12 meses) busca desde **HOY** (America/Argentina/Jujuy). Deja de leer `franja`/`hora_minima` |
| `GET Horarios Dentalink` | se le saca el `?q=…` inline de la URL, que duplicaba el query param `q` (los dos codificaban lo mismo). Todo lo demás igual, misma credencial |
| **16 nodos nuevos** | paginado por cursor con dedupe, hasta 6 páginas (ver abajo) |
| `Format Slots` | ya **no llama a la agenda**: sólo arma el texto |
| `Output Error` | mismo camino, otro texto: deja de pedirle la fecha al paciente |

**El token de Dentalink deja de estar hardcodeado.** El `Format Slots` viejo escaneaba día por día con
`this.helpers.httpRequest` y un `DL_TOKEN` en claro adentro del jsCode (hasta 91 llamadas ≈ 80 s), y encima **no
deduplicaba**: como `fecha:{eq:X}` se comporta como `>= X`, cada llamada diaria devolvía los mismos días posteriores y
el bot llegaba a ofrecer *el mismo turno tres veces*. Ahora las llamadas las hacen nodos `httpRequest` v4.2 con la
credencial `httpHeaderAuth` **"Header Auth account 3"** (`TwN6eBWsydjMdsCM`), la misma que ya usaba el nodo hermano.
`this.helpers.httpRequestWithAuthentication` **no** era opción: resuelve la credencial *del nodo que la invoca* y un
Code node de n8n no declara credenciales (ninguno de los 159 nodos del v6 ni de este sub-WF lo hace).

**Por qué hay que paginar**: Dentalink devuelve **siempre 10 slots** por llamada (`limit`, `page`, `offset` se ignoran)
y **no sabe filtrar por franja** (`hora_inicio:{gte:"13:00"}` devuelve exactamente lo mismo que sin filtro). La única
paginación posible es por cursor: pedir de nuevo con la fecha del **último** slot recibido (no +1 día, para no perder
horarios cortados en ese mismo día) y deduplicar por `(fecha, hora_inicio)`.

**Topes, medidos contra la agenda real (GET read-only, no inventados)**. Corrida de hoy, arrancando en HOY:

| página | cursor | slots acumulados | mañana / tarde | días con mañana / con tarde | latencia |
|---|---|---|---|---|---|
| 1 | 2026-09-07 | 10 | 9 / 1 | 3 / 1 | 1.00 s |
| 2 | 2026-10-01 | 19 | 16 / 3 | **5 / 2** → corta | 0.70 s |

Pero **arrancar hoy es el caso fácil**. Cuántas páginas hacen falta para juntar 2 días de mañana + 2 de tarde según
desde cuándo se busque (mismo barrido, mismo día de medición):

| desde | 2 días por franja (el mínimo de la Dra.) | 3 días por franja (agenda algo más ocupada) |
|---|---|---|
| 2026-09-07 | 2 páginas · 1.71 s | 3 páginas · 2.47 s |
| 2026-10-20 | **3** páginas · 2.25 s | **5** páginas · 3.59 s |
| 2026-11-01 | **3** páginas · 2.16 s | 4 páginas · 2.83 s |
| 2026-12-15 | **3** páginas · 2.07 s | **5** páginas · 3.52 s |
| 2027-01-05 | **3** páginas · 2.14 s | **5** páginas · 3.25 s |
| 2027-03-01 | **3** páginas · 2.06 s | 4 páginas · 2.61 s |

Por eso `MAX_PAGINAS = 6` y no 3: **el mínimo que pide la Dra. ya consume 3 páginas en 5 de las 6 fechas probadas**, así
que con el tope en 3 no quedaba ningún margen — y cuando se agota, `Format Slots` omite la sección "Por la tarde"
entera y el paciente recibe **sólo mañanas**, que es exactamente la captura #2 que motivó el pedido. `MAX_DIAS_HORIZONTE
= 120` (los dos valores comentados en `turnos/acumular_slots.js`, y el script **aborta** si el jsCode y el cableado no
declaran el mismo tope). Se corta apenas hay **2 días con mañana y 2 días con tarde**; también corta si una página no
trae nada nuevo, si falla la red o si el cursor se fue a más de 4 meses. Piso ~0.9 s, típico **2-3 llamadas ≈ 2.2 s**,
techo 6 llamadas ≈ 4.4 s (medido). Una ejecución del v6 con turno de agente tarda 20-34 s: sigue siendo marginal. El
techo viejo era ~80 s.

Los `GET Horarios P2…P6` llevan `retryOnFail` con `waitBetweenTries: 2000` (2 intentos): durante el sondeo del 07/09 la
agenda devolvió **429** tras una ráfaga, y el diseño nuevo pasa de 1 a hasta 6 llamadas por turno de paciente
conviviendo con los otros 7 nodos Dentalink del v6 y con el workflow de recordatorios. Un 429 no rompe nada
(`continueOnFail` + `Acumular` sigue con lo que haya) pero degradaría el bloque a solo-mañana en silencio.

**Frecuencia real de la agenda** (162 slots libres escaneados, 24/09→23/11): lunes y miércoles **tarde** (15:00-18:20),
martes y jueves **mañana** (08:00-10:40), viernes **mañana** (08:30-10:30), sábado y domingo no atiende. Coincide con la
`knowledge_base` id 20. Mañana y tarde **nunca caen el mismo día**, así que cada sección del bloque tiene sus propias
líneas y el agrupado por día siempre es dentro de una franja.

### B) `5cAWJxiWJ50hxEq3` — "Sub-WF - CancelarReprogramar" (ACTIVO, 35 nodos, misma cantidad)

| Nodo | Antes | Ahora |
|---|---|---|
| `Step 5: Decidir Accion Ejecutable` | dos ramas: si el paciente ya había dicho fecha/franja buscaba agenda, si no le devolvía *"¿qué día o franja le viene mejor? (mañana / tarde / fecha concreta)"* | tres salidas, ninguna pregunta: **(1)** si pide una franja sobre el bloque que acaba de recibir, se le repite **esa sección del bloque anterior** (sin tocar la agenda); **(2)** si ya vio **dos** bloques y sigue sin elegir, **escala**; **(3)** si no, se ofrece el (siguiente) bloque |
| `Step 6b-prep: Prep Query Horarios` | armaba el `q` de **un solo día** | decide **desde cuándo** buscar (`desde` sólo si el paciente por su cuenta nombró una fecha futura) |
| `Step 6b: GET Agendas` (httpRequest) | GET de 1 día a la agenda | **reemplazado** por `Step 6b: Buscar Horarios (bloque)` — `executeWorkflow` al sub-WF A. Mismo lugar en el canvas, mismas dos aristas |
| `Step 6b-out: Ofrecer Slots` | armaba a mano *"Tengo disponibles en Dentalink…"* con 3 slots del mismo día | el mensaje **es** el bloque; si no hay nada, canned de escalada sin nombrar el sistema |
| `Step 0b: Detect Multi-Turn State` | detectaba `oferta_horarios` con `/te ofrezco\|tengo disponible\|…/` y guardaba `last_bot_msg` en **300** chars | aprende `turnos disponibles:`, guarda **600** chars y agrega tres campos: `oferta_bloque` (el bloque entero del último mensaje del bot), `oferta_siguiente_desde` (desde cuándo pedir el lote siguiente) y `bloques_ofrecidos` (cuántos lotes vio ya) |
| `Step 6d-prep: Build Reserva Body` | mandaba a la agenda la `hora_inicio` que devolvió el parser de aceptación, tal cual | la normaliza a `HH:MM` (`8:40` → `08:40`) antes del POST de reserva |

**El cambio de `Step 0b` no es cosmético**: `last_bot_msg` es lo ÚNICO que ve el parser de aceptación (`Step 3.5a` →
LLM que decide qué slot eligió el paciente). Con la regex vieja el bloque nuevo no activaba el estado `oferta_horarios`
y el parser ni arrancaba: el paciente elegía un turno y se perdía. Y con el corte en 300 chars (el bloque mide 234 y
`Step 7` le puede anteponer *"Soy Asiri, la secretaria virtual…"*) se cortaba justo la sección "Por la tarde".

**Y sin los tres campos nuevos, la captura #2 sobrevivía en este camino.** El paciente que rechaza el bloque recibía
**el mismo bloque, byte a byte, para siempre**: `Step 5` devolvía `fecha_objetivo: ''` y `Step 6b-prep` lo convertía en
"buscar desde HOY". Las únicas salidas eran `is_frustrated` (exige que el paciente escriba *"ya te dije"*, *"insisto"*)
y `loop_no_turnos` (su regex no matchea el bloque nuevo). Ahora:

| El paciente contesta… | Antes | Ahora |
|---|---|---|
| *"a la tarde"* | mismo bloque otra vez | se le repiten **los turnos de tarde del bloque que ya tiene** (sección recortada, mismo formato, sin llamar a la agenda). Si dijo *"después de las 17"*, se filtran los horarios de esa sección |
| *"ninguno me sirve"* | mismo bloque otra vez | lote **siguiente**: `desde` = día después del último día ofrecido, sacado del texto del bloque anterior |
| rechaza el **segundo** lote | mismo bloque otra vez, indefinidamente | `escalar` + *"Le paso la consulta a la secretaria…"* |

La respuesta recortada por franja **conserva el encabezado** `Tenemos los próximos turnos disponibles:` a propósito: es
la marca que usan el bypass del `Formatting Agent` en el v6 y el propio `Step 0b` en el turno siguiente.

### C) `O155MqHgOSaNZ9ye` — v6 (ACTIVO, 159 nodos, misma cantidad, **ni una conexión tocada**)

| Nodo | Qué cambia |
|---|---|
| `buscar_horarios` (toolWorkflow 2.2) | `description` entera nueva: sin fecha obligatoria, se llama SIEMPRE que el paciente quiere agendar/reprogramar, devuelve un bloque para pegar, prohibido preguntar franja o fecha, `desde` para el siguiente lote. Se mapea `desde` y se borra el array `fields` muerto |
| `Sub-Agent Agendar` | 10 reemplazos (abajo) |
| `Sub-Agent Cancelar` | el texto de reprogramar deja de preguntar día/franja (código muerto hoy, ver §1 — se cambia igual para que no reviva mal) |
| `Sub-Agent General` | "PREGUNTAS DE CAPACIDAD" deja de pedir día/franja **sin prometer un mensaje que no llega** (ver §7); "Hay turnos para…" pasa a pegar el bloque |
| `Necesita Formatting?` | 3ra condición AND: el bloque **no** pasa por el LLM formateador |
| `Split en Mensajes` | guard determinístico: si el original traía el bloque y el formateado no es idéntico, se manda el original |
| `Formatting Agent - WhatsApp` | REGLA #0.b (devolver el bloque byte a byte) + el ejemplo viejo con "hs" reemplazado por el bloque nuevo |

**`Sub-Agent Confirmar` NO se toca**: no tiene ninguna pregunta de franja/fecha y sus 14 menciones a Dentalink son
razonamiento interno ("validá que hay un turno activo en Dentalink"), nunca texto al paciente.

Los 10 reemplazos de `Sub-Agent Agendar` (líneas del systemMessage vivo):

| Líneas | Antes | Ahora |
|---|---|---|
| 79 (`= TOOLS DISPONIBLES =`) | ``- `buscar_horarios`: disponibilidad de turnos. Param `fecha` (YYYY-MM-DD) OBLIGATORIO.`` — **la contradicción viva**: el resto del prompt decía "llamala sin parámetros" y esta línea seguía diciendo que la fecha era obligatoria, así que el modelo podía volver a preguntarle la fecha al paciente antes de llamarla (justo el punto 4 del pedido) | ningún parámetro obligatorio; `desde` sólo para el lote siguiente |
| 4-8 | "REGLA FRANJA/HORARIO — ABSOLUTA": mandaba pasar `franja: "tarde"` (**parámetro que nunca llegaba**) y ofrecer UN solo turno | "REGLA DE OFERTA DE TURNOS": prohibido preguntar, llamar la tool de una, pegar el bloque |
| 37 | "Hora SIEMPRE en 24hs con hs" | + la excepción del bloque (ver §2) |
| 39 | ejemplo `"Jueves 18 de Junio 10:30 hs"` | `"* Jueves 24 de septiembre 8:00 , 8:40"` (la regla de **no calcular el día de la semana** queda intacta) |
| 106-116 | PASO 3 (anclar grilla + primer turno) y **PASO 3.b — PREFERENCIA** (*"¿Prefiere por la mañana o por la tarde?"*) | PASO 3: llamar la tool sin parámetros y pegar el bloque. PASO 3.b **borrado** |
| 118-129 | PASO 4 con el formato viejo (3-4 turnos, "hs", agrupado con `;`) | PASO 4: el bloque no se reescribe; si rechaza todo, `desde`; después de 2 lotes, escalar |
| 131-140 | PASO 5 (filtrar, franjas con umbral **14:00** — incoherente con el `>= 13` del código) | PASO 5: la franja ya está en el bloque; corte 13:00 alineado con la tool |
| 148 | REGLA ANTI-ALUCINACION: ``PROHIBIDO afirmar "no tengo turnos para [fecha X]" si no llamaste `buscar_horarios(fecha=X)` `` | misma regla dura, redactada para la tool nueva: el bloque muestra **los más próximos** (2 días por franja), no la agenda entera, así que que una fecha no figure **no** significa que esté ocupada — se pide el lote siguiente con `desde` y se mira |
| 158-160 | PASO 7.b (turno ocupado por un race): *"Le puedo ofrecer: [los próximos 2-3 slots libres del mismo día o cercano]"* — el único lugar del prompt donde el agente todavía redactaba su propia lista de turnos | disculpa en una línea + `buscar_horarios` sin parámetros + **el bloque**; prohibido armar la lista a mano |
| 235-241 | "REGLA ABSOLUTA — BUSQUEDA DE FRANJA / DESPUES DE LAS 17HS" (ofrecer 1 turno en 1-2 líneas) | misma prohibición de repreguntar, pero señalando los turnos del bloque **en una frase con "hs"** (§2) |

**No se toca ninguna regla dura**: R0/Asiri, IDENTIFICACION, memoria antes que pregunta, conversación en manos de un
humano → `[NO_REPLY]`, ANTI-INJECTION, privacidad de terceros, cierres conversacionales, día de la semana,
ANTI-ALUCINACION, UNA SOLA ESCALACION, contexto runtime. El script lo verifica después del PUT.

Los prompts se cambian con **reemplazos quirúrgicos sobre el texto VIVO**, nunca reconstruyendo desde
`prompts/v6_partials/`: esos partials están **stale** (`build_prompts_v6.py --check` da Agendar −4558 chars, General
−12102, Confirmar −2719, Cancelar −1500), aplicarlos borraría meses de fixes. Cada parche guarda su ANTES exacto,
extraído del vivo, y el script **aborta** si no lo encuentra tal cual.

---

## 4. Las capas que evitan que el bloque llegue mal

Sin esto, el bloque se genera bien y **igual llega mal al paciente**:

0. **`Split en Mensajes`, recorte del centinela** (determinística). `buscar_horarios` devuelve en `resultado` **un solo
   string**: instrucción para el agente (*"INSTRUCCION (no la copies)… PROHIBIDO preguntarle al paciente qué día…"*) +
   la línea `MENSAJE EXACTO PARA EL PACIENTE (…):` + el bloque. Si el agente pega `resultado` **entero** —una sola
   desobediencia del LLM— el paciente lee las tripas del bot. Y como ese texto **contiene** `turnos disponibles:`, las
   capas 1 y 2 de abajo lo dejarían pasar **intacto**: el IF lo desvía del formateador y el guard prefiere el original.
   Los 20 patrones del Banlist tampoco disparan con ese texto. Por eso `Split en Mensajes` **recorta todo hasta el fin
   de la línea del centinela** antes de partir por `---`: una línea de código, determinística, que además deja
   inofensiva cualquier fuga futura de ese texto. Una línea propia del agente **antes** del bloque (permitida por el
   PASO 3) no se toca: el recorte se dispara sólo con el centinela, que la tool nunca manda al paciente.

1. **`Necesita Formatting?`** (determinística, primera). Hoy el IF manda al `Formatting Agent - WhatsApp` (gpt-5-mini)
   todo texto de más de 80 chars sin `[NO_REPLY]` — el bloque mide ~230. Y ese prompt ordena *"Horas SIEMPRE en 24hs con
   'hs'"* y *"Fechas con día y mes capitalizados"*: le agregaría "hs" a `9:20 , 10:40` y pondría "Septiembre". Que hoy
   reescribe está **probado**: el sub-WF genera "jueves 24 de septiembre a las 8 de la mañana" y la captura de la Dra.
   dice "24 de Septiembre 8:00 hs". La 3ra condición (`output` notContains `turnos disponibles:`) manda el bloque por la
   salida que **no** pasa por el LLM.
2. **`Split en Mensajes`** (determinística, red de atrás). Si el bloque llegara igual al formateador, se compara con el
   original de `Banlist Validator`: si difiere, se manda el original. Es el mismo mecanismo que ya salvaba el bloque de
   CBU. Cuando el bypass funciona, `formateado === original` y es un no-op.
3. **`Formatting Agent`** (prompt, última). REGLA #0.b: si el texto contiene `Tenemos los próximos turnos disponibles:`,
   devolverlo byte a byte. Gana sobre la REGLA #3.

Además: el bloque **no trae `---`**, así que `Split en Mensajes` lo manda como **un solo mensaje de WhatsApp** con sus
líneas en blanco intactas (`JSON.stringify` en `Evolution API - Enviar Mensaje` preserva los `\n` de punta a punta). Si
el `Canned Sidecar` anexa el alias/CBU, el bloque queda como parte 1 **completa** y el alias va como mensaje aparte.

**Banlist**: los 20 patrones del `Banlist Validator` corren contra 4 variantes del bloque en el test — **0 disparos**.
Cuidado al editar los textos: `guardá`, `traé`, `tomá el`, `sacá la`, `aplicá`, `enjuagá`, `vení/venga`, `los esperamos`
y `ahora mismo … clínica` están baneados. Por eso las instrucciones dicen "pegá"/"copiá" y nunca "guardá el bloque".

---

## 5. Cómo probar

```bash
node tests/test_turnos_formato.js        # 87 checks: bloque exacto, agrupado, una sola franja, sin slots,
                                          # desordenados, cambio de mes/año, día de semana contra 11 fechas
                                          # conocidas, sin "Dentalink" en ningún camino, horizonte agotado,
                                          # error de red, paginado/dedupe hasta la página 6, horas sin cero
                                          # adelante, validar fecha, split, fuga del texto interno de la tool,
                                          # el lote siguiente y la escalada del canrep (Step 0b + Step 5),
                                          # coherencia de los partials del prompt, banlist
node tests/test_media_nodos.js && node tests/test_media_fromme.js
node tests/test_retencion_y_staff.js && node tests/test_triaje_nodos.js
python -m py_compile scripts/apply_turnos_formato_raquel.py

python scripts/apply_turnos_formato_raquel.py --dry-run     # GET de los 3 workflows + diff campo por campo
python scripts/apply_turnos_formato_raquel.py --apply       # sólo con OK de Lucas
```

El `--dry-run` imprime, por workflow: la lista de cambios, el diff unificado de **cada campo** que se toca (jsCode,
descripción de la tool, systemMessages, condiciones del IF) con el conteo de caracteres antes/después, el conteo de
nodos, los `settings` que irían en el PUT (y cuáles se filtran) y **cuántos nodos/conexiones quedarían fuera de la lista
declarada** — si ese número no es 0, aborta.

**Prueba real, obligatoria después del `--apply`** (regla dura 8: nada "funciona" sin el camino completo):

1. Desde un teléfono de prueba: *"hola, quiero un turno"* → tiene que llegar **un solo mensaje** con el bloque, con las
   dos secciones, mes en minúscula y **sin "hs"** adentro.
2. Contestar *"a la tarde"* → tiene que señalar los turnos de tarde **que ya estaban en el bloque**, sin volver a
   preguntar nada.
3. Elegir uno → read-back y reserva.
4. Con un turno existente: *"quiero cambiar mi turno"* → pasa por el Sub-WF CancelarReprogramar y tiene que llegar **el
   mismo bloque** (nunca "qué día o franja le viene mejor").
5. Contestar *"ninguno me sirve"* → tiene que llegar un bloque **distinto** (lote siguiente), y al rechazar **ese**,
   escalar a la secretaria. Nunca el mismo bloque dos veces.
6. En la ejecución de n8n del sub-WF: `Acumular P2` con `completo: true` y `Faltan turnos? P2` **sin** disparar la
   página 3 (o `Faltan turnos? P1` cortando en 1 sola llamada si la agenda tiene las dos franjas cerca). Si alguna vez
   se ve llegar hasta `Acumular P6` con `dias_tarde: 0`, la agenda se quedó sin tardes en 4 meses: eso **no** es un bug
   del código, es para avisarle a la clínica.
7. **Limpiar** el número de prueba con `python scripts/limpiar_numero_demo.py` (regla dura 9): memoria, logs y label.

## 6. Cómo revertir

```bash
python scripts/apply_turnos_formato_raquel.py --rollback \
  workflows/history/bh_PRE_turnos_formato_raquel_<ts>.json \
  workflows/history/canrep_PRE_turnos_formato_raquel_<ts>.json \
  workflows/history/v6_PRE_turnos_formato_raquel_<ts>.json
```

Cada backup PRE sabe a qué workflow pertenece (por su `id`), así que se pueden revertir los tres o sólo uno. El rollback
hace su propio backup PRE antes de pisar. Si se revierte **sólo** el sub-WF A dejando el B, `Step 6b-out` se queda sin
`bloque` y cae en el canned de escalada: se puede vivir un rato, pero lo correcto es revertir A y B juntos.

El script es **idempotente**: re-correr `--apply` no cambia nada (verificado ejecutando el build dos veces sobre los
tres workflows: 0 cambios y JSON idéntico). Y aborta si el `versionId` cambió entre el backup PRE y el PUT — el v6 lo
está tocando otra sesión hoy mismo (153 → 159 nodos).

> **Los backups PRE/POST contienen el token de Dentalink.** El PRE del sub-WF A lo trae dentro del jsCode viejo de
> `Format Slots`, y **los dos** lo traen en la clave `activeVersion` que devuelve el GET (un snapshot de la versión
> activa que **no** viaja en el PUT: `PUT_KEYS` lo excluye). `workflows/history/` y `workflows/current/` están en
> `.gitignore` y no hay ningún archivo trackeado que lo contenga, así que "el token desaparece del repo" se sostiene
> para git — pero **no mandes un backup por Slack/mail/adjunto** sin limpiarlo antes.
>
> **Hallazgo aparte (pre-existente, no lo introduce este cambio)**: `scratch/test_node.js` (28/07) tiene el token de
> Dentalink en claro y **`scratch/` NO está en `.gitignore`** (`git check-ignore` no lo matchea; hoy figura como
> `?? scratch/` en `git status`). Un `git add .` lo commitea. Conviene ignorar `scratch/` o borrar ese archivo — no se
> tocó acá porque está fuera del alcance declarado de este cambio.

## 7. Cosas que quedaron afuera a propósito

- **`Sub-Agent Cancelar` y `Sub-Agent Urgencia` siguen huérfanos.** El parche de `cancelar_reprogramar` es **código
  muerto**: ese nodo no tiene ninguna conexión `main` de entrada en el v6 vivo. La captura #3 de la Dra. (*"¿qué día o
  franja le viene mejor?"*) **no** sale de ahí: sale de `Step 5` del Sub-WF CancelarReprogramar, que sí está parcheado.
  El parche del sub-agent queda por si algún día se lo vuelve a cablear, y el `--apply` lo recuerda por pantalla.
  Reconectarlos o borrarlos es otra decisión (y el prompt del Router todavía describe la arquitectura vieja).
- **`Sub-Agent General` no tiene `buscar_horarios` conectada** aunque su prompt la nombra (sus `ai_tool` son
  `buscar_conocimiento`, `buscar_paciente_dentalink`, `escalar_a_secretaria`, `obtener_historial_paciente`,
  `ver_turnos_paciente`), y el v6 no encadena un segundo turno de agente. Por eso el texto de "PREGUNTAS DE CAPACIDAD"
  **no promete** entregar los turnos en ese mismo mensaje: dice *"Confirmame que querés reprogramar tu turno y te paso
  los turnos que tenemos disponibles"* y le devuelve la pelota al paciente, que en el turno siguiente cae en
  `cancelar_o_reprogramar` / `agendar` y ahí sí recibe el bloque. Redactarlo como *"ahora le paso los turnos"* habría
  dejado al bot prometiendo un mensaje que nunca llega. **No** se agregó ni se quitó ninguna tool: eso cambia
  comportamiento en producción y no es lo que pidió la Dra. El fragmento `general_hay_turnos` sigue diciéndole que
  llame la tool (como antes de este cambio); si se decide conectarla, ese texto ya está listo.
- **El `desde` del lote siguiente es uno solo, no uno por franja.** Ver §2: la franja que se extiende más lejos (la
  tarde) se repite en el lote 2. Se prefirió eso a saltear mañanas más próximas. Un `desde` por franja (o una lista de
  días ya ofrecidos) lo cerraría del todo, a costa de complicar el contrato de la tool.
- **`slot_a_reservar` del canrep sigue saliendo del parser LLM sin validarse contra la agenda** antes del POST de
  reserva (`Step 5` → `Step 6d-prep` → `Step 6d-1`). Es pre-existente, pero el formato nuevo pone dos horarios en una
  misma línea (`8:00 , 8:40`) y el bloque no lleva año, así que el parser tiene más superficie para equivocarse. Lo que
  sí se cerró es el formato de la hora (`8:40` → `08:40` antes del POST). Validar el slot contra las líneas del bloque
  antes de reservar queda como siguiente paso.
- **`prompts/v6_partials/` sigue stale.** Este cambio no lo arregla: los `.antes/.despues` nuevos viven en
  `prompts/v6_partials/turnos/` y son parches, no el prompt entero.
- **El corte mañana/tarde es 13:00.** En la práctica no hay slots entre 12:00 y 15:00, así que 12, 13 o 14 dan el mismo
  resultado; se eligió 13 porque es el que ya usaba el código y ahora el prompt dice lo mismo (antes decía 14:00).

---

## 8. Correcciones de la revisión (misma fecha, después del primer pase)

Seis defectos encontrados releyendo la implementación contra el pedido y contra los workflows vivos. Todos **corregidos**
en esta versión; quedan acá con su repro para que se entienda por qué el diseño es el que es.

| # | Qué estaba mal | Repro | Cómo quedó |
|---|---|---|---|
| 1 | `MAX_PAGINAS = 3` no tenía margen para el único requisito duro de la Dra. ("por lo menos dos de la tarde") | Barrido con cursor desde 2026-11-01, 2026-12-15 o 2027-03-01: juntar 2 mañanas + 2 tardes consume **exactamente 3** páginas; con 3 días por franja pide 4 y hasta 5. Al agotarse, `Format Slots` omite la sección "Por la tarde" **sin ningún aviso** y el paciente recibe sólo mañanas = la captura #2 | `MAX_PAGINAS = 6` (+ 9 nodos), medido: ~0.7 s por página extra. El script aborta si el jsCode y el cableado no declaran el mismo tope |
| 2 | Contradicción de formato justo en el turno que señaló la Dra. (*"A la tarde"*): un fragmento dejaba el `"hs"` obligatorio fuera del bloque y otros tres mandaban copiar la línea del bloque **sin** `"hs"` | Bloque enviado → paciente *"a la tarde"* → el agente contesta `* Lunes 5 de octubre 15:00 , 15:40`; ese texto **no lleva la marca**, así que no lo desvía `Necesita Formatting?` ni lo protege el guard de `Split en Mensajes` → el `Formatting Agent` aplica su REGLA #3 y sale *"Lunes 5 de Octubre 15:00 hs, 15:40 hs"*. Dos formatos distintos en dos mensajes seguidos | Regla binaria (§2): o el bloque entero sin tocar, o una frase con `"hs"`. Los tres fragmentos alineados + test sobre los partials |
| 3 | El prompt de Agendar seguía diciendo, en `= TOOLS DISPONIBLES =` (línea 79), ``Param `fecha` (YYYY-MM-DD) OBLIGATORIO`` | Aplicando los 7 parches del primer pase sobre el v6 vivo, en el prompt resultante convivían la línea 79 ("OBLIGATORIO") y la 107 ("llamala SIN parámetros"): el modelo podía volver a preguntarle la fecha al paciente = el punto 4 del pedido | 8º parche (`agendar_tools_buscar_horarios`): ningún parámetro obligatorio, `desde` sólo para el lote siguiente |
| 4 | La captura #2 sobrevivía en el camino de reprogramar: el que rechaza el bloque recibía **el mismo bloque, indefinidamente**, y nunca se escalaba | *"ninguno me sirve"* → Router (continuación) → `cancelar_o_reprogramar` → `Step 0b` marca `oferta_horarios` → `Step 3.5c` da `accepts:false` → `Step 5` rama reprogramar → `fecha_objetivo: ''` → `Step 6b-prep` busca desde HOY → bloque idéntico byte a byte. Las únicas salidas eran `is_frustrated` (exige *"ya te dije"*/*"insisto"*) y `loop_no_turnos` (regex que no matchea el bloque nuevo) | `Step 0b` calcula `oferta_bloque` / `oferta_siguiente_desde` / `bloques_ofrecidos`; `Step 5` recorta la franja pedida del bloque anterior, arrastra el `desde` y **escala al segundo rechazo** (§3B) |
| 5 | Cero capas determinísticas contra la fuga del texto interno de la tool — y las dos capas nuevas la ayudaban a pasar | Si el agente pega `resultado` entero, el paciente lee *"INSTRUCCION (no la copies)… PROHIBIDO preguntarle al paciente…"*. Ese texto contiene `turnos disponibles:`, así que el IF lo desvía del formateador y el guard prefiere el original: llega **intacto**. Los 20 patrones del Banlist: 0 disparos | Recorte del centinela en `Split en Mensajes` (§4, capa 0) + 5 tests |
| 6 | `Sub-Agent General` prometía un mensaje que nunca llega | *"¿se puede mover el turno?"* → Router regla 0 (interrogativa) → `consulta_general` → `Sub-Agent General` responde *"Ahora le paso los turnos disponibles"*… y se calla: **no tiene `buscar_horarios` conectada** y el v6 no encadena un segundo turno de agente | El texto devuelve la pelota sin prometer entrega inmediata y sin preguntar día ni franja (§7) |

**Extras chicos aplicados en la misma pasada**: `siguiente_desde` por el mínimo de las dos franjas (§2); horas
normalizadas a `HH:MM` al entrar (`Acumular`) y al reservar (`Step 6d-prep`); `retryOnFail` en los GET nuevos;
`$fromAI('desde', …, 'string', '')` con `defaultValue` para que el parámetro quede **opcional** en el schema de la tool;
la REGLA ANTI-ALUCINACION y el PASO 7.b de Agendar reescritos para la tool nueva; `trae` → `incluye` en los fragmentos
(el Banlist tiene baneado `traé el/la/los/las`); campo muerto `buscar_desde` borrado de `Step 6b-prep`.

## 9. Orden de despliegue

1. `node tests/test_turnos_formato.js` y el resto de `tests/*.js` → 0 fallos.
2. `python -m py_compile scripts/apply_turnos_formato_raquel.py`.
3. `python scripts/apply_turnos_formato_raquel.py --dry-run` → revisar el diff con Lucas; **0 nodos y 0 conexiones fuera
   de la lista declarada** en los tres workflows.
4. Con el OK: `--apply`. El script hace, por workflow, backup PRE → GET fresco (aborta si otra sesión lo tocó) → PUT →
   backup POST → verificación. **El orden importa**: primero `bh` (el que arma el bloque), después `canrep` (que lo
   llama) y último el `v6`. Si se cortara en el medio, el estado intermedio es sano: `bh` nuevo con `canrep` viejo sigue
   funcionando (el canrep viejo no lo usa) y `canrep` nuevo necesita `bh` nuevo — por eso `bh` va primero.
5. Prueba real de punta a punta (§5) y limpieza del número de prueba.
6. Recién ahí, memoria del proyecto (`memory/current-state.md`, `decisions.md`).
