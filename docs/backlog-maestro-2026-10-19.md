# Backlog maestro — Asiri + panel + sistema propio (19/10/2026)

> Armado el 19/10/2026 con 4 relevamientos de solo lectura: el bot (raquel-n8n), el panel (nexora-whatsapp-agent), diseño/UX mobile y un cuarto que no llegó completo (ver Anexo). Fuentes: `docs/plan-ejecucion-2026-10-19.md`, `docs/plan-contactos-conversion-dentalink-2026-10-13.md`, `memory/backlog.md`, `memory/current-state.md` (últimas entradas) y `.claude/CLAUDE.md`. Reemplaza el "orden de trabajo" de `memory/backlog.md` como fuente del orden. El detalle técnico de cada ítem sigue en esos documentos.
>
> **Replanificado el 19/10/2026 (tarde) con el ritmo real medido (§1).** Se planifica con un factor de 3x. Con ese ritmo, el sistema propio entra antes del 26/02: CRM, recorrido, seguimientos, bandeja, PWA con push, diseño premium completo, espejo de Dentalink y agenda propia en paralelo. El pase del v7 vuelve a las fechas pedidas (02/11, 09/11 y 16/11). Todo lo que hacía o decidía Lucas pasa a Claude, salvo lo de §7. El diseño sale de las etapas 0 a 13 de `docs/diseno-premium-panel-2026-10-19.md`.

## 1. Cómo leer esto

1. **"El orden" (§2) es la cola única:** hay un ítem en construcción por vez, y se avanza de arriba hacia abajo. Cada viernes Claude tacha lo hecho, mide el ritmo de la semana y ajusta las fechas. El orden solo cambia si aparece un P0 o si Claude lo decide y lo anota en `memory/decisions.md`.
2. **Las épicas (§3) tienen el detalle de cada ítem:** por qué, qué incluye, cuándo está listo y de qué depende. Prioridades:
   - **P0:** riesgo hoy (seguridad, caídas, pacientes).
   - **P1:** lo necesario para el v7 a todos, para que la clínica use el panel y para febrero, más lo que pidió Lucas para antes del 26/02 (ver "La cuenta").
   - **P2:** valor importante que puede esperar.
   - **P3:** 2027 o después.
3. **El esfuerzo (columna "Días" de §3) está en días de trabajo de Claude, con la vara de la primera estimación.** Sale de los relevamientos. Las fechas de §2 lo convierten con el ritmo real: **1 día hábil = 3 días de esfuerzo**. No se cuentan los feriados (23/11, 08/12, 08-09/02) ni la veda (21/12 al 01/01).
4. **Lo que solo puede hacer otra persona está únicamente en §7**, al final. En el resto del documento aparece como "(§7)".

**Punto de partida (19/10):**
- **En producción:** el v6 atiende a todos, con el Día 1 aplicado (respeta las etiquetas de contacto), confirmación antes de cancelar, solo el precio de la consulta, modo humano de 1 hora y Health Check que se repara solo.
- **v7 desplegado:** atiende solo a los números con la marca `v7:tel:`.
- **Panel:** en el VPS, con el selector de tipo y el filtro "Silenciados".
- **Vigía externo básico:** desde el 19/10, una tarea de GitHub Actions prueba cada 30 minutos `/healthz` y `/login`, y si fallan le llega un mail a Lucas.
- **Recordatorios:** activos. NO TOCAR.

**El ritmo real (medido el 19/10):**
- **Qué se midió:** en una sola tarde del 19/10 se hicieron cuatro cosas:
  - la migración de tipos de contacto;
  - el selector de tipo en el panel, con deploy;
  - el Día 1 en el v6, con prueba de punta a punta;
  - el vigía externo.
  La primera versión de este backlog estimaba ese trabajo en **~6 a 8 días**. El ritmo medido fue de **más de 10 veces** lo estimado.
- **Se planifica con 3x, no con lo medido,** porque hay partes que no se aceleran:
  - la prueba en vivo y la limpieza (reglas 8 y 9);
  - un PUT al v6 por semana;
  - el soporte diario a la clínica y los incidentes.
- **Cómo se usa:** 1 día hábil = 3 días de esfuerzo. Se planifican **4 de cada 5 días**. El quinto (en general, el viernes por la tarde) queda para soporte, incidentes y lo que se corra.
- **Lo que no se divide por 3,** porque son esperas de calendario:
  - las compuertas de 5 y 10 días hábiles del v7;
  - los 7 días de conciliación del espejo;
  - las 3 semanas de sombra de la agenda propia;
  - los 3 días en paralelo con la secretaria;
  - las dos semanas de adopción;
  - la firma del contrato (§7).
  Mientras corren esas esperas, la cola sigue con otro ítem. "Una cosa a la vez" vale para lo que se construye y para lo que llega a producción, no para una medición que corre sola.
- **Revisión de cada viernes:** el ritmo de la semana es igual a los días de esfuerzo cerrados divididos por los días hábiles.
  - Si pasa de 3x, se adelanta la cola sin cambiar el orden. Lo primero que entra es lo de "Después de febrero".
  - Si baja de 2,5x dos semanas seguidas, se aplica la regla de corrimiento de §2.

**La cuenta:**
- **El backlog, recontado ítem por ítem, suma ~197 días de esfuerzo.** Incluye la etapa 12 del diseño dentro de SEG-15, y DIS-02 ya resuelto por la especificación.
- **Del 20/10 al 26/02 hay 80 días hábiles:** 42 hasta la veda y 38 en enero y febrero.
  - A 3x son 240 días de esfuerzo.
  - Planificando 4 de cada 5 días quedan **~190**.
  - Sin el margen del 25-26/02 quedan **~185**.
- **Antes del 26/02 entran ~178 días.** Entra todo, salvo SEG-20, CRM-09, BOT-17, SEG-22, BOT-15 y MAN-04 (~18,5 días). Esos quedan para después de febrero, con el acuerdo de mantenimiento (D9, §7).
- **BOT-12 queda flotante:** entra cuando lleguen los textos y los videos de la Dra. (§7).
- **Margen:** ~7 días de esfuerzo, además de la reserva semanal (el 20% de cada semana) y del 25-26/02.
- **Lo que pidió Lucas y entra antes del 26/02.** No se corre, salvo que aparezca un P0:
  - el CRM (CRM-03 a CRM-08): ficha, familias, historial de tipos y "Por clasificar";
  - el recorrido del paciente y el embudo (REC-01, REC-02, REC-03 y REC-07);
  - los seguimientos de a uno, con baja (REC-04 y REC-05);
  - los botones "hacer ahora" (REC-06);
  - la bandeja de Atención (ATE-02 y ATE-03);
  - la PWA con push (MOB-02 y MOB-04);
  - el diseño premium completo: las etapas 0 a 13 de la especificación (DIS-01 a DIS-10, MOB-01, MOB-03, ATE-04, ATE-05, ATE-07, AGE-04 y SEG-15);
  - la copia diaria de la agenda de Dentalink (AGE-02 y AGE-03);
  - la agenda propia en paralelo, con informe de diferencias (AGE-05 y AGE-06).

**Decisiones que toma Claude.** Cada una se anota en `memory/decisions.md` el día que se aplica, con la razón, la alternativa descartada y si es revisable:

| # | Decisión | Ítem | Cuándo |
|---|---|---|---|
| C1 | Ritmo 3x, este orden y la reserva de 1 de cada 5 días | §1, §2 | 19/10 |
| C2 | La purga del historial no espera a que el repo pase a privado. Lo que deja inútil la clave es la rotación de SEG-03 | SEG-02, SEG-03 | 21/10 |
| C3 | Acceso de deploy con un usuario `deploy` sin root. Tiene sudo solo para el `docker compose` del stack y para leer logs | SEG-07 | 21/10 |
| C4 | El panel se verifica con Playwright (390 y 1440 px, claro y oscuro), sin esperar a que Chrome esté conectado | CRM-01 y la regla 8 en todo el panel | 22/10 |
| C5 | Monitor externo: el servicio y el canal de aviso los elige Claude. El aviso va por mail a Lucas y a la secretaria, sin pasar por el VPS. El vigía de GitHub queda como respaldo | SEG-05 | 22/10 |
| C6 | BOT-02 se parchea, porque lo exige la regla del 15/10, que no es revisable | BOT-02 | 27/10 |
| C7 | Dirección visual "Porcelana y tinta" y tipografía Inter, de la especificación del 19/10. Dribbble no hace falta | DIS-02 | 30/10 |
| C8 | Claude revisa las capturas del arnés contra el criterio común de la especificación y despliega. A Lucas le llegan como resultado. Reemplaza la regla de la especificación "nada llega a producción sin el OK de Lucas sobre las capturas" | Etapas 0 a 13 | 30/10 |
| C9 | Claude elige a los pacientes del piloto: 5 a 10 con ficha, sin anuncio, que hayan escrito en los últimos 30 días. También decide cada compuerta del v7, con la definición de P0 de BOT-08 | BOT-08, BOT-09 | 02/11, 06/11, 13/11 |
| C10 | Backups con `pg_dump` cifrado, sin esperar a Supabase Pro. D1 queda como una mejora con gasto (§7) | SEG-10 | 06/11 |
| C11 | D11: la fase 0 de Dentalink es de solo lectura, con 1 pedido cada 1,5 s y sin datos personales. El limitador se despliega en el v7 recién el 30/11, dos semanas después de "todos" | AGE-02 | 16/11 |
| C12 | El espejo se parte en dos fases. **(a)** Ocupación de la agenda sin ningún dato de pacientes (horario, profesional, estado, motivo y duración): no espera el contrato. **(b)** Ficha, celular y si es menor: espera el contrato (D12). Revisable si el abogado dice otra cosa | AGE-03 | 25/11 |
| C13 | La agenda propia en sombra depende de los roles y del actor de SEG-12, no de Supabase Auth. SEG-20 pasa a después de febrero | AGE-05 | 07/12 |
| C14 | Un envío de "hacer ahora" con plantilla aprobada sale por el canal del bot (REC-04) y no prende el modo humano, así el "Confirmo" del paciente le llega a Asiri. Lo que se escribe a mano en el chat sí lo prende (regla 7) | REC-06 | 27/01 |
| C15 | Bracket perdido (REAL-07): sigue yendo a triaje y derivación, que es el lado seguro. No se convierte en un turno automático | BOT-12 | 19/10 |
| C16 | Los adjuntos del staff y del paciente pasan a Storage dentro de ATE-05, solo con el contrato firmado y con la retención que fije. Si no, se archivan | ATE-05 | 06/01 |
| C17 | Claude revisa los textos del manual, de Estado y de la guía de instalación (antes los aprobaba Lucas). Los textos que le llegan al paciente los aprueba la Dra. (§7) | SEG-15, MAN-03, MOB-02 | según el ítem |
| C18 | Dos semanas de adopción medidas en lugar de una: 07-11/12, para corregir antes de enero, y 01-05/02, para el informe final | ATE-06 | 04/12 |

---

## Hecho fuera de la fila (19/10, noche)
- **BOT-02 (parte reprogramar) — HECHO:** el v6 confirma antes de reprogramar (`scripts/apply_v6_confirmar_reprogramacion.py`, probado en vivo). Queda la parte **agendar** (guarda por código en `reservar_turno`).
- **Multipedido confirmar + alias (escalación 375) — HECHO:** el Sub-Agent Confirmar pasa los datos para transferir (`scripts/apply_v6_confirmar_con_alias.py`, probado en vivo).
- **SEG-05 (base) — HECHO:** vigía externo en GitHub Actions cada 30 min con mail si cae (`.github/workflows/vigia-externo.yml`); lo que falta del ítem es la sonda de 5 min, Evolution y hombre muerto.

## 2. El orden (una cosa a la vez)

**Reglas del orden:**
- **Una cosa a la vez:**
  - un ítem en construcción por vez;
  - como máximo un cambio a producción por día;
  - ningún deploy del panel el mismo día que un PUT al v6 o que un cambio de llave del v7;
  - si dos ítems del mismo día tienen que salir a producción, el segundo sale el siguiente día hábil sin otro cambio. Las fechas de este orden son de construcción, salvo las que dicen "PUT" o "deploy";
  - excepciones que cuentan como un solo cambio:
    - la rotación de SEG-03 (vie 23/10), que cambia la clave en n8n y en el `.env` del panel en la misma ventana, porque una clave rotada a medias deja al bot o al panel sin base;
    - el PUT de la mañana y la llave de la tarde del lun 02/11 (SEG-06 y el piloto) y del lun 09/11 (BOT-09 y `v7:nuevos`). La llave se prende solo si el PUT quedó verificado esa misma mañana.
  - Apagar algo de prueba que no atiende a nadie (SEG-23) no cuenta como cambio.
- **Un PUT al v6 por semana:**

  | Semana | PUT | Día |
  |---|---|---|
  | 19/10 | SEG-03 | vie 23/10 |
  | 26/10 | BOT-02 | mar 27/10 |
  | 02/11 | SEG-06 | lun 02/11, a primera hora |
  | 09/11 | BOT-09 | lun 09/11, a primera hora |
  | 16/11 | BOT-10 | jue 19/11 |
  | 23/11 | BOT-11 | mié 25/11 |

  Los cambios del v7 se despliegan con `crear_v7_en_n8n.py --aplicar`, que no toca el v6.
- **Sin cambios en producción entre el 21/12 y el 01/01.** El último deploy es el mié 16/12. El 17 y el 18/12 se trabaja solo en ramas.
- **El pase del v7 va en las fechas pedidas:** grupo chico el lun 02/11, nuevos el lun 09/11 y todos el lun 16/11.
  - Las compuertas no cambian (5 y 10 días hábiles sin P0) y entran justas: la primera cierra el vie 06/11 (del 02 al 06/11) y la segunda el vie 13/11 (del 02 al 13/11).
  - Si una compuerta falla, ese paso se corre una semana y el resto de la cola sigue.
- **Las pantallas nuevas se construyen sobre datos demo y adaptadores** (especificación, §5). La interfaz no espera al backend: cuando llega la tabla real, se cambia el adaptador y no la pantalla.
- **Si algo se atrasa, se corre en este orden:** primero SEG-21 y SEG-18, después MOB-05 y después BOT-16. **Nunca** se corren la seguridad, el Día 1, la estabilidad del v7 ni lo que pidió Lucas (§1, "La cuenta"). Si con eso no alcanza, el informe del viernes dice qué se corre y por qué.
- **Las fechas son de inicio.** Si un ítem termina antes, el siguiente arranca ese mismo día.

### Semana 1 — mar 20 a vie 23/10 (P0: seguridad y aviso)
1. **mar 20/10 — SEG-01** Aviso a la clínica por la caída del 16-19/10, con la lista de chats que quedaron sin respuesta.
2. **mar 20/10 — MAN-01 (parte 1)** Sale el cuestionario, sin cuota ni retenedor. La llamada con Irina está en §7.
3. **mar 20/10 — SEG-04** Commit **local** de lo pendiente en los dos repos, con secret-scan, **antes** de la purga. El push del panel sale ya. El de raquel-n8n sale después de la purga.
4. **mié 21/10 — SEG-02** Purga del historial de `raquel-n8n` (la `sb_secret` y los teléfonos). No espera a que el repo pase a privado (C2).
5. **mié 21/10 — SEG-07** Acceso de deploy acotado para Claude (C3). Lo necesitan SEG-03 y SEG-06, que cambian el `.env` del panel y variables de n8n y de Evolution.
6. **mié 21/10 — SEG-17 (adelantado desde el 20/11)** Pedido al abogado y textos. Se adelanta un mes para que el contrato llegue antes de la fase (b) del espejo (C12).
7. **jue 22/10 — CRM-01** Verificación del selector de tipo y del filtro Silenciados con Playwright (C4), con limpieza.
8. **jue 22/10 — SEG-05** Completar el monitor externo (C5): sonda cada 5 minutos que incluye Evolution, "hombre muerto" del Health Check y aviso también a la clínica. Va el jueves y no el viernes, para que el PUT-A ya salga vigilado y no caigan dos cambios el mismo día.
9. **jue 22/10 — SEG-03** Preparación del PUT-A. El **vie 23/10** sale el PUT de la semana: sacar la clave de los nodos del v6, rotarla y actualizarla en n8n, en el panel y en los `.env`.
10. **vie 23/10 — SEG-23** Desactivar el webhook "v7 Test (sombra)" cuando no se usa.

### Semana 2 — lun 26 a vie 30/10 (cierre de P0, preparación del piloto y base del diseño)
11. **lun 26/10 — MAN-01 (parte 2)** Las respuestas se cargan en la KB y en `decisions.md`, y se le avisa a la clínica cómo cambian los admins.
12. **lun 26/10 — BOT-01** v7: alta de pacientes que escriben desde un `@lid`, respuesta después de un "no" y la doble pregunta.
13. **mar 27/10 — BOT-02** Parche del read-back del v6 al agendar y al reprogramar (C6). Es el PUT de la semana.
14. **mié 28/10 — SEG-16** Rotar la API key de n8n, el token de Chatwoot y el `ghp_`. No va el martes, porque ese día sale el PUT de BOT-02.
15. **mié 28/10 — BOT-07** Regresión antes del piloto: la suite offline completa, y con IA solo se vuelve a correr lo que cambió o lo que falló.
16. **mié 28/10 — BOT-06** v7: entrada para los leads de anuncio. La regla del fork queda lista para el PUT del 09/11.
17. **jue 29/10 — BOT-04 y BOT-05** La guarda de precios alineada con "solo la consulta", y el probador del bot sin avisos al grupo real. El deploy del panel sale el vie 30/10, porque el jueves se carga el secreto en Evolution (SEG-06).
18. **jue 29/10 — SEG-06 (preparación)** Script, invariantes, tests y secreto en Evolution para el PUT del lun 02/11: secreto del webhook, rate limit, kill-switch y cambio de admins.
19. **vie 30/10 — DIS-02 y DIS-01 (etapa 0 del diseño)** Se anota la dirección visual (C7) y arranca el modo demo con el arnés de capturas. Es solo local, sin deploy, y termina el mar 03/11.

### Semana 3 — lun 02 a vie 06/11 (**lun 02/11: v7 para el grupo chico**)
20. **lun 02/11 — SEG-06 (PUT) y BOT-08** A primera hora sale el PUT de la semana y se verifica: un POST sin el secreto da 401 y un mensaje real pasa. Si está bien, **a la tarde arranca el piloto del v7** con 5 a 10 pacientes (C9). Se revisa 15 minutos por día hasta el 27/11.
21. **mar 03/11 — BOT-09 (preparación)** Script del PUT con las llaves `v7:nuevos` y `v7:on` apagadas, `test_v7_flag` y la regla de `ctwa_ad` de BOT-06. Va primero porque BOT-14 lee esas llaves.
22. **mar 03/11 — AGE-01** /citas pide la agenda por rango de fechas.
23. **mar 03/11 — BOT-14** /agente avisa que el que atiende es el v7 y bloquea la edición de los prompts del v6. Tiene que estar antes de "todos".
24. **mié 04/11 — SEG-08** Deploy del panel unificado: la imagen se arma fuera del VPS, sin root y con vuelta atrás.
25. **jue 05/11 — SEG-13** Tests del panel: unitarios, smoke E2E y CI. Van antes de tocar el diseño en producción.
26. **vie 06/11 — SEG-10** Copias de respaldo fuera del servidor y restauración probada (C10). Ese día **cierra la compuerta 1:** 5 días hábiles sin P0 (la decide Claude, C9).

### Semana 4 — lun 09 a vie 13/11 (**lun 09/11: v7 para contactos nuevos**)
27. **lun 09/11 — BOT-09 (PUT)** A primera hora sale el PUT de la semana con las llaves apagadas. Después se hace el alta en vivo de un paciente nuevo de prueba, con limpieza. Si la compuerta 1 pasó, se prende `v7:nuevos`.
28. **lun 09/11 — SEG-14** Migraciones del v3 versionadas en el repo del panel y tipos generados. No hay cambio en producción.
29. **mar 10/11 — CRM-02** Cargar la lista semilla de 25 contactos (§7). Si para entonces no llegó el OK, se carga el día que llegue.
30. **mar 10/11 — BOT-03** Prueba en vivo de la red de seguridad de los silenciados. Claude le avisa antes a la Dra. por el grupo.
31. **mar 10/11 — SEG-11** Health Check: el mail como segundo canal y señales nuevas.
32. **mié 11/11 — SEG-12** Roles mínimos y auditoría de acciones sensibles.
33. **jue 12/11 — DIS-03, DIS-04 y DIS-05 (etapa 1)** Tokens AA y temas claro, oscuro y sistema. Tipografía Inter y escala mobile. Espaciado, radios, elevación y movimiento. El deploy sale el mar 17/11, porque el panel no se despliega el día que cierra una compuerta ni el día de "todos".
34. **vie 13/11 — Cierra la compuerta 2:** 10 días hábiles sin P0 desde el 02/11 (C9).

### Semana 5 — lun 16 a vie 20/11 (**lun 16/11: v7 para todos**)
35. **lun 16/11 — v7 para todos** Si la compuerta 2 pasó, se prende `v7:on`. Ese día no hay otro cambio en producción.
36. **lun 16/11 — AGE-02** Fase 0 de Dentalink (C11) y limitador común de pedidos. El limitador se despliega en el v7 el lun 30/11. Hasta entonces, el script de la fase 0 corre de noche, fuera del horario de la clínica, para no competir con el v7 por el tope de Dentalink justo cuando empieza a atender a todos.
37. **mar 17/11 — DIS-06 y DIS-07 (etapa 2)** Sale el deploy de la etapa 1, y empiezan las primitivas accesibles con la ruta `/design`. El deploy de la etapa 2 es el vie 20/11.
38. **mié 18/11 — BOT-10** El freno "Dentalink up?" pasa a modo degradado. El PUT de la semana sale el jue 19/11.
39. **jue 19/11 — MOB-01 y MOB-02 (etapa 3)** Barra inferior en el celular, barra lateral agrupada en el escritorio y PWA instalable. El deploy es el mar 24/11.

> Con AGE-02, las etapas 1 a 3 y BOT-10, esta semana ya suma unos 13 días de esfuerzo (más de 4 días hábiles). Por eso AGE-03 (fase a) pasa a la semana 6 y ATE-01 a la semana 9: la semana de "todos" conserva parte de su reserva para incidentes.

### Semana 6 — mar 24 a vie 27/11 (23/11 feriado)
40. **mar 24/11 — BOT-11** Admins, grupo y datos de la clínica pasan a una tabla editable. El PUT de la semana sale el mié 25/11.
41. **mié 25/11 — AGE-03 (fase a)** Copia de la ocupación de la agenda, sin datos de pacientes (C12). Se despliega el mar 01/12, después del limitador.
42. **jue 26/11 — ATE-02** Base de la bandeja: tabla `casos`, `registrar_aviso` y un disparador que nunca frena el insert.
43. **vie 27/11 — SEG-09** El VPS vuelve a quedar sano solo después de un reinicio. El reinicio de prueba es el dom 29/11 a las 22 h, fuera del horario de la clínica y lejos de Recordatorios.

### Semana 7 — lun 30/11 a vie 04/12 (la bandeja y el CRM llegan al celular)
44. **lun 30/11 — ATE-03 (etapa 6)** **Bandeja de Atención en el celular** (Tomar / Resolver). El deploy es el mié 02/12. El lunes sale el limitador de AGE-02 en el v7, y el martes la fase (a) del espejo.
45. **mié 02/12 — MOB-04** Notificaciones push de urgencias en la PWA. El deploy es el jue 03/12, el día de la tanda con celulares reales (§7).
46. **mié 02/12 — CRM-03** El selector de tipo pide motivo y muestra quién lo puso y cuándo.
47. **jue 03/12 — CRM-04** Pantalla "Por clasificar" en el celular, de a un contacto por vez.
48. **vie 04/12 — ATE-06 (medición)** Eventos de uso y tablero. Salen en un solo deploy con CRM-03 y CRM-04, antes de la primera semana de adopción.

### Semana 8 — lun 07 a vie 11/12 (08/12 feriado; **semana de adopción 1, sin deploys del panel**)
49. **lun 07/12 — Semana de adopción 1** (07, 09, 10 y 11/12). Incluye la sesión con la secretaria (§7). El informe de una página sale el vie 11/12, con las fricciones y qué se corrige.
50. **lun 07/12 — AGE-05** Agenda propia en sombra: modelo, motor de disponibilidad, comparador e informe semanal de diferencias. La sombra se despliega el lun 14/12 y corre sola durante la veda.

### Semana 9 — lun 14 a vie 18/12 (**último deploy: mié 16/12**)
51. **lun 14/12 — AGE-03 (fase b)** Ficha, celular y si es menor, en el espejo. **Solo con el contrato firmado (§7).**
    - El deploy es el mié 16/12, y los 7 días de conciliación corren solos durante la veda.
    - Si el contrato no llegó, se adelanta la etapa 4 y la fase (b) sale el mar 05/01. En ese caso CRM-06 y REC-01, que dependen de la fase (b), arrancan detrás de ella.
52. **mar 15/12 — ATE-01** Lista de conversaciones y dashboard calculados en la base, en una rama. Sale con el deploy de la etapa 4 el lun 04/01, porque las dos tocan la lista de conversaciones. Lo necesita CRM-07 (11/01).
53. **jue 17/12 — ATE-04 y MOB-03 (etapa 4)** Lista de conversaciones v2 y gestos, en una rama. El deploy es el lun 04/01.

**Veda: 21/12 al 01/01, sin cambios en producción.** La sombra de la agenda y la conciliación del espejo corren solas y se revisan el lun 04/01.

### Enero 2027 — el sistema propio en el panel
54. **lun 04/01 — Revisión de la veda** Se revisan la conciliación del espejo (7 días al 100%) y el informe de diferencias de la sombra, y sale el deploy de la etapa 4.
55. **lun 04/01 — CRM-06** Familias en la base: teléfono ↔ fichas (el v7 lo lee).
56. **mié 06/01 — ATE-05 (etapa 5)** Chat v2, con chat-view partido en módulos (C16). El deploy es el lun 11/01.
57. **vie 08/01 — REC-01** Eventos del recorrido del paciente, escritos por el bot.
58. **lun 11/01 — CRM-07 (etapa 7)** Contactos: lista y ficha del contacto.
59. **mié 13/01 — CRM-08** Familias en la interfaz (chip y confirmar la relación).
60. **jue 14/01 — CRM-05** Pantalla Silenciados con historial de tipos.
61. **vie 15/01 — SEG-19** Matriz de fallas, con detección y reparación o aviso, y un simulacro de cada una.
62. **lun 18/01 — REC-02** Recorrido del paciente en la ficha y en el chat.
63. **mar 19/01 — REC-03 (etapa 10)** Embudo en el panel.
64. **jue 21/01 — REC-07** Línea del embudo en el Daily Summary y reporte antes/después.
65. **jue 21/01 — REC-04** Seguimientos: el canal controlado del lado del bot y de n8n. Necesita el contrato.
66. **mar 26/01 — REC-05 (etapa 11)** Seguimientos de a uno desde el panel, con baja.
67. **mié 27/01 — REC-06** Botones "hacer ahora" y respuestas aprobadas en el chat (C14).
68. **jue 28/01 — ATE-07 (etapa 8)** "Hoy" para la Dra. y dashboard de valor. El último deploy del panel antes de la semana de adopción 2 es el vie 29/01.
69. **jue 28/01 — BOT-13** Recordatorio específico para las primeras consultas (§7). Va el jueves porque el viernes sale el deploy del panel, y así la primera corrida que se vigila cae en un día hábil (vie 29/01).

### Febrero 2027 — traspaso (el soporte termina el vie 26/02)
70. **lun 01/02 — Semana de adopción 2**, sin deploys del panel. El informe final sale el vie 05/02.
71. **lun 01/02 — BOT-16** Conversión del v7: primero con `conv:tel` en el número de Lucas, y `conv:on` cuando los textos estén aprobados (§7).
72. **mié 03/02 — SEG-24** Rol `bot_n8n` con permisos mínimos en la base, probado antes en un clon.
73. **jue 04/02 — AGE-04 (etapa 9)** Agenda v2, en una rama. El deploy es el mié 10/02.
74. **mié 10/02 — AGE-06** Agenda propia en modo práctica en el panel. El deploy es el vie 12/02, y los 3 días en paralelo van del lun 15 al mié 17/02 (§7).
75. **jue 11/02 — SEG-25** Bajar Chatwoot del VPS. Pasa del jue 04/02 a esta semana porque sacar `CHATWOOT_*` del `.env` del panel es un deploy del panel, y en la semana de adopción 2 el panel no se toca.
76. **vie 12/02 — MAN-05** Plan de baja de accesos de Nexora y propuesta de acuerdo de mantenimiento (D9: §7).
77. **vie 12/02 — MOB-05** Decisión sobre una app nativa, con los datos de las dos semanas de adopción.
78. **lun 15/02 — SEG-15 (etapa 12)** Estado en lenguaje llano y el resto de las pantallas: Recordatorios (solo la interfaz), Conocimiento, Configuración y la migración a primitivas.
79. **mar 16/02 — SEG-18 y SEG-21** `/api/health` con el banner de servicio degradado, y limpieza de restos del panel.
80. **mié 17/02 — DIS-08, DIS-09 y DIS-10 (etapa 13)** Barrido de accesibilidad AA, rendimiento percibido y regresión visual en CI. Son 6 días de esfuerzo (2 días hábiles): arrancando el miércoles terminan el jueves y el viernes queda para el deploy. **Último deploy del panel: vie 19/02.**
81. **lun 22/02 — MAN-02** Runbook técnico actualizado.
82. **lun 22/02 — MAN-03** Manual de operación para la clínica. Los 3 simulacros con la secretaria son el mié 24/02 (§7).
83. **mar 23/02 — AGE-07** Informe "¿se puede apagar Dentalink?", con unas 10 semanas de sombra y los 3 días en paralelo medidos.
84. **jue 25 y vie 26/02 — Margen y entrega.** Sirve para repetir un simulacro de MAN-03 que haya fallado.

**Flotante — BOT-12** (triaje: textos definitivos, videos y apertura a todos). Entra en la reserva de la semana en que lleguen los textos y los videos de la Dra. (§7). Si no llegan antes del 12/02, pasa a después de febrero.

### Después de febrero (solo con acuerdo de mantenimiento D9; fechas aproximadas)
> Son ~18,5 días de esfuerzo: unas 2 semanas a 3x. Se adelantan si la revisión de los viernes muestra que sobra ritmo. Lo que se adelante antes del 26/02 entra en el soporte y no necesita D9; lo que quede para marzo, sí. Ninguno es parte de lo que pidió Lucas en el replan.

85. **≈ 01/03 — SEG-20** Login por usuario con Supabase Auth.
86. **≈ 03/03 — CRM-09** Segmentación completa: `contacto_ruta`, sombra y `seg:on` (PUT-D del plan del 13/10).
87. **≈ 10/03 — BOT-17** Retiro del v6 como entrada: entrada propia del v7 (D10) y apagado de los sub-agentes del v6.
88. **≈ 15/03 — SEG-22** Configuración por clínica en el panel (sacar "Raquel/Jujuy/Asiri" del código).
89. **≈ 17/03 — BOT-15** /agente apuntando al v7.
90. **≈ 18/03 — MAN-04** Ayuda dentro del panel.

---

## 3. Épicas

Columnas: **ID · Item · Por qué · Qué incluye · Listo cuando · Prio · Días · Depende de**.

### 3.1 Bot y v7

| ID | Item | Por qué | Qué incluye | Listo cuando | Prio | Días | Depende de |
|---|---|---|---|---|---|---|---|
| BOT-01 | v7 antes del piloto: alta de `@lid`, cierre después de un "no" y doble pregunta | Son bugs conocidos que van a tocar a pacientes reales. El `@lid` da de alta en Dentalink una ficha con un celular falso (`v7/agenda_core.js:254`) | (1) Si el teléfono no es un celular válido: alta sin celular, aviso "cargar celular a mano" y que no cuente como convertido. (2) Después de "no, ese turno sí voy": "Perfecto, su turno queda como estaba". (3) Después de dar el precio, no sumar "¿Para quién es?" al "¿Desea que le agende?". Tests nuevos | Suite offline verde con los tests nuevos, desplegado con `crear_v7_en_n8n.py --aplicar`, prueba en vivo con el número de Lucas y limpieza | P1 | 1,5 | — |
| BOT-02 | v6 mientras atiende a todos: agendar y reprogramar sin read-back | El v6 reserva y reprograma apenas se elige el horario, sin un "sí" (mismo bug del 19/07, "agendar prematuro"). Va contra la regla del 15/10, que **no es revisable** y dice "vale para el v6 mientras atienda". Con las fechas del replan, el v6 atiende a los pacientes con ficha hasta el 16/11, y más si una compuerta falla | Reprogramar: Sub-WF CancelarReprogramar (`5cAWJxiWJ50hxEq3`), con el mismo patrón y en el mismo workflow que `apply_v6_confirmar_cancelacion.py`. Agendar: `reservar_turno` (es una herramienta HTTP dentro del v6, así que es un PUT al v6). Invariantes, backup PRE/POST, `check_triaje` y prueba en vivo que corta antes del "sí". **Decidido: se parchea (C6)** | La prueba en vivo muestra la pregunta antes de escribir en Dentalink y 0 citas de prueba activas | **P0** (pacientes reales hoy) | 1,5 | — |
| BOT-03 | Probar en vivo la red de seguridad de los silenciados | Es la única defensa para un paciente marcado por error que escribe una urgencia. Hoy está cubierta solo offline | Aviso previo a la Dra. y al grupo. El número de Lucas se marca como "colega" un rato y se manda una urgencia fuerte. Se verifica que el bot no contesta y que el grupo recibe el aviso con el tipo, desde cuándo y quién lo marcó. `limpiar_numero_demo.py --seg --borrar-logs --apply` en el mismo turno | Aviso enviado, ninguna respuesta al "paciente", limpieza hecha y anotada | P1 | 0,5 | Aviso previo a la Dra. (lo manda Claude) |
| BOT-04 | La guarda de precios de la KB y la ayuda de /servicios con "solo la consulta" | El panel todavía dice que la cuota se puede publicar (`conocimiento/actions.ts:26,62`, `lib/servicios.ts:40`), y la decisión del 16/10 dice que no | La guarda rechaza montos de cuota y de retenedor. Se actualizan el hint y el error. Se revisa que la KB vigente no tenga esos montos | Guardar "cuota mensual $70.000" da un error claro y ninguna entrada vigente tiene montos de cuota ni de retenedor | P1 | 0,5 | — |
| BOT-05 | Probador del bot sin efectos en el grupo real | El probador pega al webhook real del v6 con un número sintético: una urgencia o un comprobante de prueba avisan al grupo de la Dra. Además deja restos en la memoria | Pasar el probador al v7 en sombra, o marcar el número de prueba con el aviso bloqueado. Advertencia visible. Limpieza automática al cerrar | Una urgencia en el probador no llega al grupo y la memoria del número de prueba queda vacía al terminar | P1 | 1 | — |
| BOT-06 | v7: entrada para los leads de anuncio (`ctwa_ad`) | El v7 no tiene presentación para el anuncio (un grep de `ctwa` en `v7/` no encuentra nada). Sin esto no se abre el v7 a contactos nuevos | Hasta que exista la presentación del v7, el primer mensaje con `ctwa_ad` lo atiende el v6 (regla en el fork, en el mismo PUT que BOT-09). Después, la presentación corta (texto: §7) y como máximo 2 ofertas de horarios (D7) | Test de grafo: `ctwa_ad` con la marca del v7 va al canned del v6. Prueba en vivo simulando un anuncio, con limpieza | P1 | 1,5 | §7 (solo para la segunda parte) |
| BOT-07 | Regresión antes del piloto | Desde el examen del 07/10 (74/78) cambiaron cancelar, la propuesta, el pago y los precios | La suite offline completa. Con IA se vuelven a correr **solo** los casos tocados por esos cambios y los que fallaron (memoria del 08/10, "testear solo fallas"). Cita de prueba lejos en el calendario: se anula y se borra su recordatorio al terminar (regla 9) | Suite verde, 0 fallas graves (cancelar o reservar sin "sí", datos a quien no los pidió) en lo que se volvió a correr y 0 citas de prueba activas | P1 | 1 | BOT-01 |
| BOT-08 | Piloto del v7 con un grupo chico (02/11) | Es la primera vez que el v7 atiende a pacientes reales. La confianza se recupera con proceso (regla 1) | 5 a 10 pacientes con ficha y sin anuncio, elegidos por Claude (C9). La lista se le pasa a la clínica. Marca `v7:tel` persistente y un listado de quién está en el piloto. 15 minutos de revisión por día. Interruptor para sacar a todos de golpe. **P0 del piloto** (lo que corta la compuerta): escribir en la agenda sin un "sí", dar un dato a quien no lo pidió, responderle a un silenciado, una urgencia no derivada, un mensaje que invita a ir sin turno o un precio que no es el de la consulta | OK de la Dra. (§7). Informe diario con la cuenta de P0. El vie 06/11 (5 días hábiles) Claude decide si se sigue o se vuelve (C9) | P1 | 3 (repartidos en 2 semanas) | BOT-07; SEG-03; SEG-06; Día 1 estable 2 días |
| BOT-09 | PUT-C: llave global del v7 (nuevos 09/11, todos 16/11) | Hoy el v7 se prende número por número | `v7:on` y `v7:nuevos` además de `v7:tel`, en el fork del v6. Los silenciados ni llegan. Invariante "sin llave = el grafo de hoy". `check_triaje`, backup PRE/POST y diff. **Antes de prender `v7:nuevos`:** la primera alta en vivo de un paciente nuevo (pendiente desde el 07/10: hasta ahora el alta solo se probó offline y en sombra). Se verifica el `rut` del POST y el filtro `rut` del GET, se corta antes del aviso al grupo o se le avisa antes a la Dra., y después se deshabilita la ficha y se anula la cita (regla 9) | `test_v7_flag` con mutaciones en verde. Apagar la llave devuelve todo al v6 en menos de 1 minuto. Alta en vivo correcta, con limpieza. 10 días hábiles sin P0 antes de "todos" | P1 | 2,5 | El PUT con las llaves apagadas puede salir antes de la compuerta del piloto. **Prender** `v7:nuevos` exige BOT-08 en verde y BOT-06; prender `v7:on` exige 10 días hábiles sin P0 |
| BOT-10 | El freno "Dentalink up?" pasa a modo degradado | Si Dentalink se cae, hoy se apaga todo el bot, urgencias incluidas, y el v7 lo hereda. Es incompatible con que la clínica quede sola | Siguen andando el triaje, la info y las derivaciones. Agendar, confirmar y cancelar responden "en este momento no puedo ver la agenda, la secretaria le responde" y avisan al grupo | Con `dentalink:status=down` simulado, una urgencia se deriva y un "hola" recibe respuesta. Test de grafo | P1 | 1,5 | PUT de seguridad hecho |
| BOT-11 | Admins, grupo y datos de la clínica en una tabla editable (lado del bot) | Los teléfonos de los admins y el JID del grupo están escritos a mano. Cada cambio de personal exige un PUT, y después de febrero no va a haber quién lo haga | Tabla de configuración que leen "Kill-switch Check", los avisos al grupo y el v7, con caché en Redis y un fallback idéntico a los valores de hoy. Edición mínima desde el panel (solo admin) | Cambiar un admin tiene efecto en menos de 5 minutos, sin PUT. Test "sin fila = valores de hoy" | P1 | 3 | MAN-01, SEG-06 |
| BOT-12 | Triaje: textos definitivos, videos y apertura a todos | Los textos son borradores. Solo hay videos de alambre que pincha (el bracket suelto, que es lo más frecuente, no tiene). La última anotación dice que está en piloto solo con Lucas | `SELECT` del estado real de `triaje_config`. Casos límite, textos y videos de la Dra. (§7), más `check_triaje`. Bracket perdido (REAL-07): sigue en triaje y derivación (C15). **No usar `tests/test_triaje_textos_banlist.py`:** lee el array `BANLIST` del nodo "Banlist Validator", que se sacó el 07/10. Con un snapshot nuevo del v6 falla, y mantenerlo sería volver a poner la banlist (regla 5). Se borra o se reemplaza por una revisión de formato (largo, sin placeholders `{{ }}`, sin montos que no sean la consulta). Apertura con `--activar --piloto ""` y 1 semana de revisión | Textos de la Dra. cargados, al menos 1 video nuevo y 0 incidentes en una semana con todos | P2 | 2 | §7 (flotante: entra la semana en que llegan) |
| BOT-13 | Recordatorio específico para las primeras consultas | Lo pidió la Dra. el 08/09. Los scripts están listos y sin aplicar | Confirmar el "puntito amarillo". Dry-run, `--ddl`, `check_triaje` y `--apply` de `apply_recordatorio_consultas.py` (excepción a "NO TOCAR": §7). Cita de prueba anulada. Se vigila la corrida de las 08:00 del día siguiente | Primera corrida real correcta y cita de prueba anulada | P2 | 1 | §7 |
| BOT-14 | /agente: avisar que atiende el v7 y bloquear la edición del v6 | Desde el 16/11 la pantalla editaría prompts de un bot que ya no responde | Banner "Atiende Asiri v7" y edición de los prompts del v6 deshabilitada mientras el v7 tenga la llave | Con `v7:on` no se puede guardar un prompt del v6 y el banner está visible | P1 | 0,5 | BOT-09 (preparación: los nombres de las llaves; no espera el PUT) |
| BOT-15 | /agente apuntando al v7 | Para que la pantalla vuelva a servir | Configuración del workflow activo, directrices que lee el v7 y editor del prompt del cerebro v7 con backup y diff | /agente muestra y edita lo que usa el v7, con historial | P2 | 1,5 | BOT-14; SEG-22 |
| BOT-16 | Conversión del v7: oferta a prospectos sin ficha | Es el corazón del sistema comercial ("tus anuncios traen X, el bot agenda Y"), y el plan del 13/10 la tenía para noviembre (`conversion_core.js`, `conv:tel` / `conv:on`). La primera versión de este backlog no la incluía | Retrospectiva de las 60 charlas. Oferta según la D7, corregida por la decisión del 16/10: horarios directos en la 1.ª oferta y pregunta en la 2.ª, como mucho 2 por episodio, nunca después de Pagos, de una urgencia, de una derivación ni a un silenciado, y **sin cuota ni retenedor para nadie**. Textos que redacta Claude (la aprobación: §7). `tipo_turno` y eventos. Interruptores `conv:tel` (el número de Lucas) y `conv:on`. Suite offline. La intención la decide el modelo, sin regex | Suite verde. Prueba en el número de Lucas con limpieza. Con `conv:on` y 2 semanas: 0 ofertas fuera de las reglas y la tasa de "primera consulta realizada" medida contra la línea base | P2 | 4 | BOT-09 a todos estable; BOT-06; §7 (solo para `conv:on`) |
| BOT-17 | Retiro del v6 como entrada | Después del 16/11, el v6 (163 nodos) sigue siendo la puerta de entrada y conserva sub-agentes que ya no contestan. Para que la clínica quede sola y para la clínica 2 (D10) hace falta una entrada propia del v7 | Workflow de entrada del v7 con Día 1, triaje, kill-switch, rate limit, secreto y Gate Humano. Sub-agentes del v6 apagados. Freno "Dentalink up?" y herramientas de Dentalink del v6 desconectados (plan §5). `webhookId: evo-webhook-v2` preservado (regla 3). El v6 queda como vuelta atrás | Con la entrada nueva, la suite y una semana en vivo sin P0. Volver al v6 lleva menos de 5 minutos y está probado | P2 | 4 | BOT-09 a todos estable 4 semanas; BOT-10; BOT-11 |

### 3.2 Seguridad y operación

| ID | Item | Por qué | Qué incluye | Listo cuando | Prio | Días | Depende de |
|---|---|---|---|---|---|---|---|
| SEG-01 | Aviso a la clínica y mensajes sin respuesta de la caída (16-19/10) | Hubo unos 2,5 días sin entrada ni respuestas, y ya pasó una vez (06-08/10) | Lista de solo lectura de los chats con mensajes entrantes entre el 16/10 21:37 y el 19/10 ~13:20 sin respuesta. Mensaje corto al grupo. Confirmar también que Irina revisó los del 06 al 08/10 (pendiente desde el 08/10) | La clínica recibió la lista y confirmó que la revisó (§7), incluidos los del 06 al 08/10 | P0 | 0,5 | — |
| SEG-02 | Repo privado y purga del historial | La `sb_secret` (que saltea RLS sobre datos de salud) está publicada: el repo devuelve 200 sin autenticar, y `scripts/apply_desacoplar_chatwoot.py:145,146,224,225` está en origin desde eac44b1 | Repo privado: §7. La purga no lo espera (C2). `git filter-repo` de `sb_secret_`, de los celulares que no son de admins y de los teléfonos de `.claude/CLAUDE.md`. Force-push coordinado y revisión de forks. **Antes de la purga:** el commit local de SEG-04, porque `filter-repo` con 98 cambios sin commitear arriesga perderlos. **El vigía:** en un repo privado consume minutos de Actions (cada 30 minutos son ~1.440 por mes, contra 2.000 gratis, y el billing ya estuvo bloqueado). Si no alcanza, el `vigia-externo.yml` pasa a un repo público aparte que solo tenga ese archivo. La purga no reemplaza la rotación (SEG-03) | `git log -S 'sb_secret_' --all` → 0 commits y el vigía corrió bien después del force-push. Con el repo privado (§7), un GET sin autenticar → 404 | P0 | 0,5 | SEG-04 (commit local) |
| SEG-03 | PUT-A y rotación de la clave (bot y panel) | Si se rota sin este paso, "Gate Humano Final" deja pasar respuestas aunque haya un humano atendiendo, y el triaje deja de decidir | Inventario (credencial de n8n, nodos, `.env` del panel en el VPS y `.env` locales). PUT al v6: "Gate Humano Final" y "Triaje: Decidir" leen de una credencial o variable. Rotar en Supabase. Actualizar n8n, el `.env.production` del panel (y sacar las variables que sean restos) y los `.env` locales. Revisar los logs de la API de Supabase en busca de accesos ajenos. Se rota la `sb_secret` (API). La contraseña de Postgres, que usa Recordatorios (NO TOCAR), queda igual en este ítem | 0 `sb_secret_` en un GET nuevo del v6. La clave vieja da 401. Panel: lista, chat, media firmada, `/api/live?probe=1` y las RPC `contacto_*` andan. Un humano atendiendo sigue silenciando al bot. `check_triaje` sano. La corrida de Recordatorios del día siguiente, sin errores | P0 | 1,5 | SEG-07 (acceso al VPS para el `.env` del panel) |
| SEG-04 | Commit y push de lo pendiente (los dos repos) | Hay 98 cambios sin commit (incluido el Día 1 en producción) y el panel desplegado (9999553) no está en GitHub. Si se pierde la PC de Lucas, no queda cómo revertir | Secret-scan del diff. Commits **locales** por tema, antes de la purga de SEG-02. Borrar `data/cita_prueba_examen.json` (la 9248, cancelada el 15/10). Push de 9999553 ya (el repo del panel es privado y no tiene `sb_secret_` en el historial: verificado el 19/10). Push y PR a main de raquel-n8n después de la purga. Marcar `apply_desacoplar_chatwoot.py` como no re-ejecutable (compacta salidas vacías de las conexiones: backlog del 05/10) | `git status` limpio, secret-scan sin hallazgos y origin igual a lo desplegado | P0 | 0,5 | — (el push de raquel-n8n, después de SEG-02) |
| SEG-05 | Completar el monitor externo de caídas | El vigía del 19/10 existe, pero prueba cada 30 minutos, solo `/healthz` y `/login`, no mira Evolution y avisa solo a Lucas por mail. Encima los cron de GitHub se pausan tras 60 días sin actividad | Sonda externa cada 5 minutos (n8n, panel y Evolution), con un servicio que no dependa de GitHub ni del VPS. "Hombre muerto": el Health Check hace ping cada 30 minutos y, si deja de hacerlo, se avisa. Avisos a Lucas **y a la clínica** por el canal que decide Claude (C5). El vigía de GitHub queda como respaldo | Simulacro: con n8n frenado (o el :80 ocupado) llega un aviso en menos de 15 minutos por un canal que no pasa por el VPS, y llega el aviso de recuperación | P0 | 1 | SEG-07 |
| SEG-06 | Cerrar la puerta trasera del webhook y cambiar los admins | Sin autenticación cualquiera puede mandar mensajes sin tope o un `/bot off` haciéndose pasar por un admin: es la misma clase de falla que la causa 1 del incidente Mariela | Quitar el atajo `test_e2e_suite` de "Rate Limit Prep". `EVOLUTION_WEBHOOK_SECRET` en n8n y en Evolution, y "Webhook Validator" rechaza si falta (fail-closed). Revisar los ~30 webhooks sin auth. Los scripts de prueba mandan el secreto. "Kill-switch Check" deja de confiar en el teléfono que trae el mensaje, y se actualizan los admins (sale Irina, entra la nueva secretaria) | Un POST sin el header devuelve 401/403 y no ejecuta nada. Un mensaje real de Evolution pasa. El rate limit se respeta. `/bot status` responde a la nueva secretaria y a Irina ya no | P0 | 2 | SEG-03 (un PUT por semana); SEG-07 (variables en n8n y en Evolution); §7 (celular de la nueva secretaria) |
| SEG-07 | Acceso de deploy acotado para Claude | Hoy el permiso de Claude bloquea las escrituras remotas, así que todo lo que es servidor queda trabado (el arreglo de la caída del 17/10 lo tuvo que correr Lucas) | Usuario `deploy` sin root (C3), con permisos acotados (`docker compose` del stack y lectura de logs) o un runner con llave. Lista de los comandos permitidos | Claude despliega el panel y reinicia Traefik, con trazas, sin Lucas | **P0** (bloquea SEG-03 y SEG-06) | 0,5 | §7 (permiso) |
| SEG-08 | Deploy del panel unificado | `deploy.yml` (systemd) no coincide con el contenedor real y `redeploy.sh` compila como root en el VPS, lo que se puede comer la RAM del bot | La imagen se arma fuera del VPS (Actions → GHCR, o un runner alternativo si el billing sigue bloqueado). En el VPS solo `pull && up` con un usuario que no es root. Vuelta atrás por tag. Healthcheck después del deploy. Borrar el camino systemd | Un push a main despliega sin compilar en el VPS y sin root, y la vuelta atrás está probada en menos de 5 minutos | P1 | 1,5 | SEG-04, SEG-07 |
| SEG-09 | El VPS vuelve a quedar sano solo después de un reinicio | El 17/10 el nginx del sistema tomó el :80 y Traefik no levantó. No se sabe por qué se apagó | Logs del proveedor del 16/10 21:37. `restart: unless-stopped` en todos los contenedores. Script de verificación después del arranque (80/443 en Traefik, `/healthz`, Evolution) que avisa. Reinicio de prueba en una ventana acordada, fuera del horario de la clínica y lejos de la corrida de Recordatorios | Un reboot vuelve a quedar sano solo en menos de 5 minutos, el monitor lo registra y la causa queda en `decisions.md` | P1 | 1 | SEG-05, SEG-07 |
| SEG-10 | Copias de respaldo fuera del servidor y restauración probada (D1) | Supabase está en plan gratis, sin copias descargables. Ya hay tablas nuevas, y los backups de los workflows están solo en la PC de Lucas | `pg_dump` nocturno cifrado, sin esperar a D1 (C10), y export de los workflows de n8n fuera del VPS. 30 días de retención. Procedimiento escrito | 7 copias diarias verificadas, restauración en un clon en menos de 1 hora y señal "backup no corrió" | P1 | 2 | SEG-07 |
| SEG-11 | Health Check: el mail como segundo canal y señales nuevas | El único aviso sale por WhatsApp a Lucas. Si se cae Evolution, o desde febrero, nadie se entera | `--mail-a` con Lucas y la clínica. Señales: Supabase o Redis inalcanzables, `seg:falla` del Día 1 y "los recordatorios no corrieron a las 9". Refrescar el snapshot (7 nodos contra 13 vivos) | Una alerta forzada llega por mail y por WhatsApp, y las señales nuevas tienen test offline | P1 | 1 | SEG-05 |
| SEG-12 | Roles mínimos y auditoría en el panel | Cualquier usuario puede apagar el bot, anular turnos o editar la KB, y no queda registro. La sesión dura 7 días, no se puede revocar y el login no tiene límite de intentos. Llega una secretaria nueva | Tabla `panel_acciones` (actor, acción, objetivo, antes/después). Gate por rol en /control y en las escrituras a Dentalink. Límite de intentos de login. Revocación de sesión. Usuario real en la barra lateral. `set_config('app.actor')` | Un usuario que no es admin no puede apagar el bot, cada escritura tiene autor, 5 intentos fallidos bloquean 15 minutos y cerrar sesión invalida el token | P1 | 2 | SEG-14 |
| SEG-13 | Tests del panel y CI | El repo no tiene ni un test ni lint. Una regresión silenciosa puede hacer que el bot conteste a quien no debe | Vitest para modo humano, tipos de contacto, escalaciones, previews y mime. Test de contrato de `setTipoContactoAction`. Smoke con Playwright (login, lista, chat, filtro Silenciados) contra un entorno de prueba. ESLint. Todo en CI | `test` y `e2e` en verde en CI, y un PR que rompe `esModoHumano` falla | P1 | 3 | SEG-08 |
| SEG-14 | Migraciones del v3 versionadas en el repo del panel | Las migraciones 0001-0007 son del producto viejo, los tipos del v3 están escritos a mano y las RPC se llaman con un cast. Lo que viene (casos, cola, eventos, config) necesita un lugar probado | `db/v3/` con las migraciones aplicadas (14/10 y 19/10). Test "anon rechazado" por objeto (Anexo B). `supabase gen types`. Archivar lo viejo | Una base vacía se arma solo con `db/v3`, los tipos se generan sin editar a mano y el test de permisos corre en CI | P1 | 2 | SEG-13 |
| SEG-15 | Control como página de estado | Desde febrero la clínica queda sola, y la caída del 16-19/10 no se vio en el panel | Semáforo general y filas para Asiri, WhatsApp (último mensaje que entró y que salió), recordatorios, Health Check y monitor externo. Cada problema trae "qué hacer" y el botón que lo repara (Reconectar). Prender o apagar Asiri con confirmación y con el nombre de quien lo tocó. **Suma el resto de la etapa 12 del diseño:** Recordatorios (solo la interfaz: el workflow no se toca), Conocimiento, Configuración (Apariencia) y la migración a primitivas de agente, servicios y aprendizaje | Con datos demo de 4 escenarios, cada captura a 390 px muestra el problema y la acción sin scroll. Textos revisados por Claude para el manual (C17) | P1 | 3,5 (incluye el resto de la etapa 12) | DIS-06, MOB-01, SEG-05 |
| SEG-16 | Higiene de las credenciales que quedan | La API key de n8n quedó en un chat del 06/07, el token de Chatwoot está en un nodo y hay un `ghp_` en el servidor viejo | Rotarlos y pasar el token a una credencial (o borrar el nodo si se baja Chatwoot). Secret-scan del repo y de los snapshots | Secret-scan sin hallazgos y las credenciales viejas inválidas | P1 | 0,5 | SEG-03 |
| SEG-17 | Contrato de datos, abogado y aviso de privacidad | Nexora es encargado de datos de salud (Ley 25.326, art. 25), con transferencias a Brasil, Chile y EE.UU. Hay que definir qué pasa después de febrero | Consulta con un abogado: contrato de encargado, AAIP, transferencias, consentimiento y línea de baja para seguimientos. Aviso de privacidad en el menú de Asiri. Claude prepara el pedido y los textos (21/10). La revisión y la firma: §7 | Pedido enviado el 21/10. Contrato firmado y aviso aprobado (§7) **antes de la fase (b) de AGE-03** (D12, C12) y antes de REC-04 | P1 | 1 (0,5 de Claude) | — |
| SEG-18 | `/api/health` del panel y banner de servicio degradado | Los errores del panel van solo a `console.error` y el vigía prueba solo `/login` | Estado de v3, Dentalink, n8n, Evolution y el bus en vivo, sin datos sensibles. Errores registrados. Enchufado al monitor externo. Banner en la interfaz | Con Dentalink caído, `/api/health` lo marca, el monitor avisa y el banner aparece en menos de 1 minuto | P2 | 1 | SEG-08 |
| SEG-19 | Matriz de fallas: detección, reparación y simulacros | Ya pasaron: webhook de Evolution vacío, WhatsApp desconectado, VPS que no arranca, horas sin mensajes entrantes y `Activar Takeover (fromMe)` fallando en silencio (182 fallos seguidos que pasaron como "success" por `continueOnFail`, 06/10) | Matriz falla → detección → reparación automática o aviso con la instrucción del manual. Las señales de Supabase, Redis, `seg:falla` y "recordatorios no corrieron" se construyen en SEG-11; acá solo se suman el token de Dentalink y la falla de `Activar Takeover`, para no duplicar. Un simulacro por falla. El de "recordatorios no corrieron" se hace sin tocar Recordatorios, con una copia o leyendo su registro | Cada falla de la matriz tiene un simulacro registrado que dispara su aviso o su reparación, y Recordatorios queda intacto | P1 | 3 | SEG-05, SEG-11 |
| SEG-20 | Login por usuario con Supabase Auth | Los usuarios en una variable de entorno no escalan y no permiten dar de baja sin redeploy | Roles admin, secretaria y doctora. Alta y baja desde el panel. Actor por sesión. Migrar la sesión Bearer de la futura app | Alta o baja de un usuario sin redeploy, cada acción con autor y los accesos de Nexora revocables en 1 paso | P2 | 4 | SEG-12 |
| SEG-21 | Limpieza de restos del panel | El README describe otro producto, hay dependencias sin uso, unas 30 referencias a Chatwoot, controles duplicados y dos escritores de `human_takeover` | README real, dependencias fuera, `.env.example` vigente, /control y /recordatorios unificados y n8n como único escritor de `human_takeover` | Build y tests en verde, un bundle más chico y un README que permite levantar el panel desde cero | P2 | 1,5 | SEG-13 |
| SEG-22 | Configuración por clínica en el panel | Hay 98 menciones fijas a Raquel, Jujuy o Asiri. Es necesario para vender (D10) | Tabla de configuración (nombre, marca, logo, zona horaria, horarios, transferencia, dirección, IDs de n8n, mapa de estados, etapas) con caché y pantalla de admin. Comparte la tabla con BOT-11 | Un grep de "Raquel\|Jujuy\|Asiri" en el código da 0 fuera de los datos semilla, y cambiar el nombre o la zona horaria se refleja en todo el panel | P2 | 3 | SEG-14, BOT-11 |
| SEG-23 | Webhook "v7 Test (sombra)" cerrado cuando no se usa | Es una superficie más, aunque solo acepta el número de Lucas y números sintéticos | `probar_v7.py --desactivar` al terminar cada tanda | Inactivo fuera de las pruebas | P3 (va antes de febrero porque son 0,1 días) | 0,1 | — |
| SEG-24 | Rol `bot_n8n` con permisos mínimos en la base | n8n entra como `postgres`: es dueño de todo y saltea RLS. Por eso "el bot solo sugiere" (plan del 13/10, Anexo B) hoy es solo una convención | Rol con EXECUTE solo sobre `contacto_ruta`, `contacto_sugerir`, `contacto_vincular_ficha` y las RPC de agenda, más lo que lee el v6. Se cambia la credencial de n8n con backup y se verifica Recordatorios (NO TOCAR: usa la credencial Postgres, así que el cambio se prueba antes en un clon) | Con el rol nuevo, el bot no puede escribir en `contacto_roles` (test), todo lo demás anda y Recordatorios corre igual | P2 | 1,5 | SEG-14; SEG-10 |
| SEG-25 | Bajar Chatwoot del VPS | Lo pidió Lucas el 05/10. Son 4 contenedores que comen RAM del único servidor (SEG-09) y guardan 5 meses de conversaciones de pacientes. El §6 dice "se baja", pero ningún ítem lo hacía | (1) Verificar a qué contenedor apunta la credencial `Redis account` del v6: si es `chatwoot-redis`, apagarlo tumba el bot. (2) `CHATWOOT_*` fuera del `.env` del panel. (3) `docker stop` de rails y sidekiq, y probar el bot. (4) Dump cifrado de la base fuera del repo y del VPS, con la retención que diga el abogado. (5) Recién ahí, borrar contenedores y volúmenes. Avisar a la clínica | El bot y el panel andan 48 h sin Chatwoot, el dump está verificado y la RAM libre está medida antes y después | P2 | 1 | SEG-07; SEG-10; SEG-16 |

### 3.3 Contactos / CRM

| ID | Item | Por qué | Qué incluye | Listo cuando | Prio | Días | Depende de |
|---|---|---|---|---|---|---|---|
| CRM-01 | Verificar en el navegador el selector de tipo y Silenciados | Se desplegó sin verlo (Chrome desconectado). Por la regla 8 no se puede decir que funciona | Recorrido real con Playwright (C4) a 1440 y a 390 px, con un número de prueba: proveedor → etiqueta y filtro → "Equipo" solo admin → doble confirmación con ficha → vuelta a paciente. `limpiar_numero_demo.py --seg` en el mismo turno | Capturas de cada paso, el bot silencia y vuelve a responder, y no queda ningún tipo de prueba abierto | P0 | 0,5 | — |
| CRM-02 | Cargar la lista semilla (25) y resolver los 12 dudosos | Con la tabla vacía el Día 1 no silencia a nadie: el bot le contestó 73 veces a Tecnodent y 24 a "…8700 Irina" | Revisar las 14 propuestas por nombre. `cargar_lista_semilla.py --apply --ok-dra`. Los 12 dudosos van a la secretaria desde el panel (§7) | Los 25 vigentes. A los 2 días, 0 respuestas a esos números y 0 silencios a pacientes con ficha | P1 | 0,5 | §7 |
| CRM-03 | Selector de tipo con motivo, autor y fecha | El plan §2.8 pide motivo y la leyenda "Silenciado: proveedor (Irina, 21/10)". Hoy el motivo es fijo (`actions.ts:600`) y no se ve quién lo puso | Motivo de una lista corta con nota opcional. Leyenda con autor y fecha en el encabezado y en la lista. Historial corto. Aviso si lo cambió otra persona | Silenciar exige motivo y el encabezado muestra la leyenda tal como está en `contacto_roles` | P1 | 1 | CRM-01, DIS-06 |
| CRM-04 | "Por clasificar" en el celular, de a uno | Es una de las 2 pantallas del plan §2.8. El 30% de lo que entra no es de pacientes, y hay 12 dudosos y 26 `@lid` | Tabla `cola_clasificacion` (motivo cerrado, tipo sugerido, evidencia por id de mensaje, una entrada abierta por contacto y motivo). El tipo sugerido lo da el v7 cuando deriva ("parece proveedor"), nunca una regex. Mientras no exista (CRM-09), la tarjeta sale sin sugerencia. Tarjeta con el porqué en lenguaje llano, los últimos 3 mensajes y si tiene ficha o turnos. Botones de 48 px (Equipo solo admin). Doble confirmación si tiene turnos. Deshacer. Progreso. Link directo desde los avisos | Con datos demo se clasifican 10 contactos en menos de 60 s a 390 px. Cada decisión queda en `contacto_roles` con autor. Equipo no aparece para quien no es admin | P1 | 3 | DIS-06, MOB-01, SEG-14; D5 |
| CRM-05 | Pantalla Silenciados con historial de tipos | Hoy es solo un filtro de los chats con mensajes, y no dice quién, cuándo, por qué ni cuándo revisar | `/contactos/silenciados` con tipo, autor, fecha, motivo, próxima revisión (90 días) y "volver a paciente". Panel de historial con `contacto_roles` y eventos | Todo silenciado aparece aunque no tenga chat, y volverlo a paciente queda en el historial | P1 | 1,5 | CRM-03 |
| CRM-06 | Familias en la base: teléfono ↔ fichas | Un celular tiene varias fichas (17 teléfonos con 2 o 3) y un paciente varios celulares. Hoy el bot lo resuelve preguntándole a Dentalink en cada mensaje | Tabla de vínculos alimentada por el espejo y por `recordatorios_enviados`, con relación "sin_definir" por defecto y deduplicación por DNI antes de proponer. El v7 la lee con fallback a Dentalink (plan #12). Incluye los pendientes que dejaba `memory/backlog.md`: el par `@lid` ↔ teléfono, guardado cuando llegan juntos (hoy es ~7% de los mensajes); la lista de fichas duplicadas (Carmen 609 y 3 históricas) para que las limpie la secretaria (§7); y las fichas que creó el v6 sin DNI, para que ella cargue el DNI (§7) | Todos los teléfonos con ficha vinculados, test con un celular de 2 fichas y el v7 leyendo de la tabla | P1 | 3 | AGE-03 (fase b) |
| CRM-07 | Contactos: lista y ficha | No hay ruta de contactos: la información de una persona está repartida en el v3, los recordatorios, Dentalink y el chat | `/contactos` con búsqueda y vistas (Pacientes, Familias, Prospectos, Silenciados, Por clasificar, Dormidos). Ficha con tipo, etapa, familia, turnos, chats, notas y acciones. Mobile como pantalla completa. Sin DNI, dirección ni email hasta que haya contrato | Desde la ficha se ve todo sin abrir Dentalink, la búsqueda responde en menos de 300 ms y el render no tiene DNI, dirección ni email | P1 | 5 | CRM-06, ATE-01 |
| CRM-08 | Familias en la interfaz | Sin familias, el embudo y los seguimientos cuentan mal | Chip "Familia (2 fichas)" en la lista y en el chat. Confirmar la relación (tutor, hijo, duplicado) con autor | Los 17 teléfonos multificha agrupados y la relación confirmada con autor | P1 | 2,5 | CRM-07 |
| CRM-09 | Segmentación completa (PUT-D del plan del 13/10) | El Día 1 solo silencia a quien se etiquetó a mano. El plan del 13/10 también tenía la función única `contacto_ruta` (que la leen el v6 a la entrada, el Gate Humano Final y el panel), la sombra antes de `seg:on`, la sugerencia de tipo del v7 y la D3 ("la inició la clínica, sin ficha" = silencio + cola + red, solo para contactos nuevos). La primera versión de este backlog no la incluía | `contacto_ruta(tel)`, que calcula la ruta vieja y la nueva (`seg:on` elige). `contacto_sugerir` desde el v7 cuando deriva. Red de seguridad con modelo, en sombra 3 días. `Activar Takeover (fromMe)` deja de prender el modo humano en internos y grupos. 1 semana en sombra registrando qué habría silenciado. PUT con invariantes | Sombra de 1 semana con 0 pacientes con ficha silenciados. Después de `seg:on`, 2 semanas sin silencios equivocados. `seg:off` vuelve atrás en menos de 1 minuto | P2 | 4 | CRM-04; SEG-14; BOT-09 a todos estable |

### 3.4 Bandeja de Atención

| ID | Item | Por qué | Qué incluye | Listo cuando | Prio | Días | Depende de |
|---|---|---|---|---|---|---|---|
| ATE-01 | Lista de conversaciones y dashboard calculados en la base | Cada evento en vivo rearma la lista con unas 7 queries (2.000 conversaciones, todos los pacientes, etc.) y el dashboard pagina hasta 15.000 mensajes cada 30 s | Vista o RPC `v_conversaciones_lista` y `contacto_tipo_de(tel)`. Agregados en SQL. Caché corta. Refetch por teléfono. p95 medido antes y después | `/api/conversaciones` con p95 < 300 ms y < 3 queries, y el mismo resultado que hoy | P1 | 3 | SEG-14 |
| ATE-02 | Base de la bandeja: `casos` y `registrar_aviso` | `escalaciones_log` no tiene tipo, estado, dueño ni caso. Hoy las escalaciones solo llegan al grupo | Tabla `casos` con dedupe por teléfono y tipo (más un contador). Disparador fail-safe sobre `escalaciones_log` y el triaje que nunca frena el insert. Bitácora. Bus en vivo. Solo las últimas 72 h nacen como nuevas. **El tipo sale de lo que registró el bot, no de un regex sobre el texto** | Un aviso real con el número de Lucas crea un caso en menos de 2 s sin tocar n8n, y si el disparador falla, el insert igual entra | P1 | 2 | SEG-14, SEG-12 |
| ATE-03 | Bandeja de Atención mobile-first | Es la pantalla que hace que la clínica use el panel y que reemplaza al grupo como lugar de trabajo | Mobile: lista agrupada (Urgencia arriba, Requiere secretaria, En curso, Esperando paciente, Resueltas hoy). Tarjeta con el motivo en lenguaje llano, tipo de contacto, hora relativa, contador, dueño y "Asiri vuelve en 42 min". Botones Tomar, Abrir chat, Esperando paciente y Resolver (nota opcional, "devolver al bot" tildado). Desktop: lista + detalle (especificación §4.3). Hasta ATE-05, el detalle muestra los últimos mensajes y "Abrir chat", sin el chat embebido. Contador rojo en el menú y franja de tarjetas abiertas en el chat. Referencias: Linear Inbox, Front, Intercom | Con datos demo, una urgencia, un pago y un "pidió persona" se toman y se resuelven con el pulgar en 2 toques o menos a 390 px. La urgencia se distingue sin color. axe sin "serious". Aviso real del número de Lucas en menos de 2 s, con limpieza (regla 9) | P1 | 4 | ATE-02, DIS-06, MOB-01 |
| ATE-04 | Lista de conversaciones v2 | En el celular la lista y el chat no entran juntos. El estado es un ícono de 13 px, la hora tiene contraste 2,39 y el menú abre solo con clic derecho | Lista a pantalla completa y chat empujado en mobile. Fila de 72 px con un chip de estado con texto. Búsqueda. Filtros con contadores. Deslizar y mantener apretado. Virtualización | Cada estado se reconoce en escala de grises, la hora y el badge pasan AA, y con 1.000 ítems demo el scroll va a más de 55 fps | P1 | 3 | MOB-03, DIS-07 |
| ATE-05 | Chat v2 y chat-view partido en módulos | Es la pantalla más usada y tiene 2.680 líneas. El header está sobrecargado y el campo de escribir es un input de una línea a 14 px (zoom en iOS) | Header de 56 px con un chip de estado con motivo y vencimiento, y un solo "Devolver a Asiri". Panel de contexto (rail o sheet). Textarea de 16 px que crece, fijo arriba del teclado, con burbuja optimista. Módulos: header, timeline, bubble, media, composer, search, y parsers con tests | La timeline ocupa al menos el 65% del alto a 390 px, ningún archivo pasa de 600 líneas, la meta de las burbujas pasa AA y hay una prueba real de envío con limpieza | P1 | 5 | ATE-04 |
| ATE-06 | Semana de adopción medida y sesión con la secretaria | El riesgo número 1 es que la clínica no use el panel. Hoy el panel no registra uso | Eventos de uso sin datos personales en `panel_acciones`: tiempo hasta tomar y hasta resolver, por gesto o por botón. Tablero (lo lee Claude para el informe). 20 minutos con la secretaria en su celular, con 3 tareas (§7). Informe de una página para el grupo | La medición está desplegada **antes** de la primera semana. Dos semanas medidas, sin deploys del panel (C18): 07-11/12 (informe el vie 11/12, con las fricciones que se corrigen en enero) y 01-05/02 (informe final el vie 05/02). En cada una queda medida la tasa de casos resueltos en el panel frente al grupo y la mediana hasta tomar una urgencia, con al menos 5 fricciones con decisión. Si la clínica está de vacaciones, se corre a la semana siguiente | P1 | 1,5 | ATE-03, CRM-04, CRM-03, MOB-02; §7 (calendario) |
| ATE-07 | "Hoy" para la Dra. y dashboard de valor | Son 7 tarjetas de KPI iguales que no responden "¿qué tengo que hacer hoy y está todo bien?" | Bloque Hoy (estado de Asiri y WhatsApp, pendientes de Atención, turnos de hoy y mañana, quién espera a un humano) que se lee en 10 s. Debajo, 3 KPIs con sparkline y texto. Gráfico con eje y tabla accesible (skill dataviz) | A 390 px el bloque Hoy entra sin scroll. Mirando solo la captura (datos demo), la Dra. responde 3 preguntas: ¿Asiri está prendida?, ¿cuántas urgencias hay abiertas? y ¿cuántos turnos hay mañana? | P1 | 3 | ATE-03 |

### 3.5 Recorrido y seguimientos

| ID | Item | Por qué | Qué incluye | Listo cuando | Prio | Días | Depende de |
|---|---|---|---|---|---|---|---|
| REC-01 | Eventos del recorrido escritos por el bot | El embudo tiene que avanzar solo con hechos, y el bot es la fuente de "consultó", "se le ofreció", "reservó" y "pagó" | Tabla de eventos que el v7 escribe en modo vivo (oferta, reserva con `tipo_turno`, aviso de pago, derivación). "Vino" y "no vino" salen del espejo | Eventos en vivo para los pacientes del piloto y el cálculo de etapa con tests | P1 | 3 | AGE-03 (fase b), CRM-06 |
| REC-02 | Recorrido del paciente en la ficha y en el chat | Para entender en qué etapa está una persona y por qué, sin leer el chat entero | Stepper con las 4 etapas del plan (Consulta, Primera consulta, Devolución/presupuesto, En tratamiento) + Dormido. Línea de tiempo de hechos con autor. Marcar a mano con motivo obligatorio, que manda solo hasta el próximo hecho | 5 recorridos demo distintos se entienden a 390 px, "Perdido" sin motivo está bloqueado y 200 hechos cargan en menos de 1 s | P1 | 4 | REC-01, CRM-07 |
| REC-03 | Embudo en el panel | Lo vendible: "tus anuncios traen X, el bot agenda Y" | Vista de etapas por hechos, columnas con conteos (lista en mobile), motivos de pérdida editables y `no_es_paciente` excluido | El embudo coincide con `tests/embudo_baseline.py` sobre las mismas fuentes | P1 | 5 | REC-02 |
| REC-04 | Seguimientos: canal controlado (bot y n8n) | El envío tiene que salir con textos aprobados, línea de baja, tope por número (Evolution no es la API oficial) y registro | Extensión autenticada de `panel_acciones_staff` con acciones sobre plantillas aprobadas, sin montos de cuota ni de retenedor (solo la consulta). Tope diario y por número. Baja registrada: la entiende el modelo del v7 con cualquier palabra ("no me escriban más"), nunca una regex. La palabra BAJA de la plantilla es solo la instrucción visible; si aparece, también da de baja, que es el lado seguro (se manda menos). Evento en el recorrido. Envío de a uno, nunca masivo | Cada acción probada de punta a punta con el número de Lucas, con limpieza, y una "baja" frena los envíos siguientes | P1 | 4 | SEG-06, SEG-17, REC-01 |
| REC-05 | Seguimientos de a uno desde el panel | D8: Irina manda de a uno, con textos de la Dra. y la línea de baja | Cola por tipo (consultó y no agendó, no vino, presupuesto sin respuesta, dormidos). Vista previa completa. Enviar, Posponer y Descartar con motivo. Tope visible. **No existe "seleccionar todos"** | Ninguna acción manda más de uno a la vez, todo texto enviado coincide con una plantilla aprobada e incluye la baja, y un contacto con baja no aparece más | P1 | 3 | REC-04, REC-02 |
| REC-06 | Botones "hacer ahora" y respuestas aprobadas en el chat | La secretaria repite a mano el recordatorio, los horarios libres, los datos para transferir y la dirección | Botón de rayo (y "/" en el escritorio) con un sheet de acciones con vista previa editable. Textos desde directrices y canned aprobados. Sin precios salvo la consulta. **Decidido (C14):** un envío con plantilla aprobada sale por el canal del bot y no prende el modo humano. Hoy lo prende, y el "Confirmo" del paciente no le llegaría a Asiri (pendiente del 06/10). Y Asiri sigue sin pedir confirmación de asistencia (decisión del 08/10): el botón lo usa una persona | Cada acción muestra la vista previa y exige "Enviar", las plantillas no tienen montos de cuota ni de retenedor, y hay una prueba real con limpieza | P1 | 2 | ATE-05; BOT-11 (datos de la clínica); REC-04 |
| REC-07 | Embudo en el Daily Summary y reporte antes/después | La Dra. mira poco: el resumen tiene que llegar solo | Línea del embudo en el Daily Summary y reporte con el mismo script (frente a "0 de 32") | El resumen diario trae el embudo y el reporte está entregado al grupo | P1 | 1 | REC-03 |

### 3.6 Agenda propia y salida de Dentalink

| ID | Item | Por qué | Qué incluye | Listo cuando | Prio | Días | Depende de |
|---|---|---|---|---|---|---|---|
| AGE-01 | /citas por rango de fechas | `listAllCitas` trae 8 × 50 sin filtro y recorta en JS: el mes actual puede venir incompleto y comparte el límite de 429 con el bot | Filtro gte/lte por el mes visible ±1. Caché de 60 s. Aviso de datos truncados | El mes actual coincide 1 a 1 con Dentalink, con 2 GET por carga como máximo | P1 | 1 | — |
| AGE-02 | Fase 0 de Dentalink y limitador común de pedidos | Antes de copiar hay que saber qué se usa y quién pone el estado 15 (48-51% de las citas). El bot, el panel y la copia comparten el tope de unos 40 pedidos seguidos | Script GET a 1 pedido cada 1,5 s, sin datos personales (módulos, historial de estados, notificaciones, motivos, duraciones). Limitador en Redis con prioridad para el bot | Informe con la lista de qué se replica y la respuesta sobre el estado 15, y el limitador con tests y el v7 usándolo | P1 | 3 | — (D11: C11) |
| AGE-03 | Copia diaria (espejo) de la agenda de Dentalink | Es la base del sistema propio: agenda completa, familias, vino/no vino | Ventana corta (+14 días) cada 10 minutos y ventana larga de noche, en dos fases (C12). **(a)** Ocupación sin ningún dato de pacientes: citas con horario, profesional, estado, motivo y duración. **(b)** Con el contrato: id y celular de la ficha, y si es menor. Nunca DNI, dirección ni comentarios. Se frena solo ante un 429. Esquema aparte. Señal "espejo atrasado" en el Health Check | 7 días conciliado al 100% con datos de no más de 10 minutos (p95) | P1 | 5 | SEG-03, SEG-10, AGE-02 (con el limitador desplegado). La fase (b): **SEG-17 (D12: contrato antes de copiar datos de pacientes)** |
| AGE-04 | Agenda v2: día en el celular y semana en el escritorio | La grilla mensual de 7 columnas a 11 px no se lee en el celular ni muestra la forma real del día | Tira de días con lista por hora y huecos visibles. Detalle en un sheet con acciones confirmadas. Semana con las franjas reales. Estados con forma además de color. Indicador "esto no toca Dentalink" para el modo práctica | Con una semana demo a 390 y 1440, la leyenda se entiende en grises, cancelar siempre confirma y no hay citas de prueba reales | P1 | 5 | AGE-03, DIS-07, MOB-03 |
| AGE-05 | Agenda propia en sombra (back) | Lucas quiere reemplazar a Dentalink, y el corte necesita la agenda propia medida en sombra | Esquema `agenda` (tipos, estados con historial, grilla de 10 minutos, bloqueos y feriados, sobreturno). Motor de disponibilidad. Comparador contra `/agendas`. Adaptador `agenda_io` con la misma forma. Reutilizar las entidades y tests de nexora-agenda | Informe semanal de diferencias, 200 búsquedas o más iguales con cada diferencia explicada y 3 semanas sin rechazos sin explicar | P1 | 10 | AGE-03 (fase a), SEG-12 (C13) |
| AGE-06 | Agenda propia en modo práctica y 3 días en paralelo | Es lo último antes de poder decidir el corte | Crear, mover y anular contra `agenda_io` en sombra, cada acción con vista previa y confirmación explícita (§4, punto 7), con diferencias visibles. Escritura inversa probada con una cita de prueba (anulada después). La secretaria trabaja 3 días en paralelo (§7) | El informe de diferencias de esos 3 días da igual (criterio §4.4) | P1 | 5 | AGE-05, AGE-04, SEG-17 |
| AGE-07 | Informe "¿se puede apagar Dentalink?" | El corte es **no antes del 01/03/2027** y solo con los criterios del §4.4 y el acuerdo de mantenimiento | Los criterios del §4.4 medidos al 23/02, con unas 10 semanas de sombra, la conciliación del espejo y los 3 días en paralelo, y qué falta | Informe entregado a la Dra. y la decisión anotada | P1 | 1 | AGE-03, AGE-05, AGE-06 |

### 3.7 Diseño premium

| ID | Item | Por qué | Qué incluye | Listo cuando | Prio | Días | Depende de |
|---|---|---|---|---|---|---|---|
| DIS-01 | Modo demo con datos inventados y arnés de capturas | Todos los criterios de listo de diseño piden capturas, y no se pueden sacar de chats reales (datos de salud, regla 9). El panel lee el v3 en el servidor. También sirve para la demo vendible | `DEMO_MODE` que cambia los loaders por fixtures (~40 contactos de todos los tipos, multimedia, turnos). Playwright en 360, 390, 768 y 1440, claro y oscuro. Solo en dev local | 4 capturas o más por ruta, 0 teléfonos reales y ningún pedido de red a Supabase, n8n ni Dentalink con `DEMO_MODE` | P1 | 2,5 | — |
| DIS-02 | Benchmark visual con Dribbble y dirección de arte | El panel es un port 1:1 de otro proyecto: oscuro forzado, verde ácido, tarjetas iguales, MAYÚSCULAS. Nada que ver con una clínica estética que trabaja de día y desde el celular | Brief de 1 página (Irina en el celular, la Dra. que mira 10 s, Lucas en el escritorio; 3 principios). Paleta propuesta "Porcelana y tinta", con el claro primero (#F6F7F9 / #121722 / #0E6B66, dorado #9A6B12 solo para la marca), y una alternativa. Moodboard de 6 a 10 referencias por patrón (inbox, triage, agenda del día, ficha CRM, timeline, bottom sheet) con el **MCP de Dribbble**; si no está conectado, Linear, Superhuman, Intercom, Front, Attio, Things, Cal.com y WhatsApp Business. Agente UX/UI dedicado | Documento con la paleta en hex y los contrastes calculados (≥ 4,5:1 texto, ≥ 3:1 bordes), 2 tipografías con una muestra real, wireframes de Atención y Chat a 390 px, y la elección en `decisions.md` (C7). **Ya lo resolvió `docs/diseno-premium-panel-2026-10-19.md` (§1 y §2): solo queda anotar la elección** | P1 | 0,25 (el resto ya está hecho) | — (Dribbble ya no hace falta) |
| DIS-03 | Tokens de color semánticos AA y temas claro/oscuro/sistema | Medido: blanco sobre el primario da 2,30:1, el badge de no leídos 2,18 y el borde 1,22. Los estados se mezclan con la marca (verde = marca = bot = confirmado). El oscuro está forzado | Capas de superficie, texto y borde. Estados con nombre fijo, como en la especificación §2.2.3: bot, humano, silenciado, urgencia, pago y requiere secretaria, más los del turno, que se distinguen por forma (confirmado, sin confirmar, anulado, no asistió y atendido). Burbujas distinguibles por posición e ícono. Claro por defecto, oscuro con pares verificados y "sistema". Script en el head sin parpadeo (storage con try/catch). Migrar los colores crudos de Tailwind | Script de contraste en CI que falla por debajo de 4,5:1 o 3:1 en los dos temas. Un grep de colores crudos da 0. Sin flash de tema incorrecto. Capturas de chat y lista | P1 | 2,5 | DIS-02 |
| DIS-04 | Tipografía y escala mobile-first | Hay 53 usos de 10-11 px, ilegibles a pleno sol, y el input de 14 px hace zoom en iOS | Una familia, pesos 400/500/600. Escala con nombre (12/14/16/17/18/22/28/34 en mobile: especificación §2.1). Body e inputs de 16 en mobile. `tabular-nums` en horas y KPIs (reemplaza a Space Mono). Sin MAYÚSCULAS en rótulos | Un grep de `text-[Npx]` da 0, ningún texto mide menos de 12 px a 390 px (Playwright) y no hay zoom en el composer en iOS | P1 | 1 | DIS-02 |
| DIS-05 | Espaciado, radios, elevación, z-index y movimiento | Hay un solo radio, la misma sombra, glows decorativos y todo en z-50 | Grilla de 4 pt. Radios por jerarquía (6/10/16/24/9999). 3 niveles de elevación sin glow. Escala de z. Movimiento de 120/200/320 ms solo en respuesta a una acción, con `prefers-reduced-motion` | Un grep de `btn-glow\|card-glow\|text-gradient` da 0 y no hay transform animado con reduced-motion | P1 | 1 | DIS-03 |
| DIS-06 | Primitivas base accesibles | Hay 5 modales sin trampa de foco, 5 switches y 13 botones primarios hechos a mano. Sin primitivas, Atención y Por clasificar duplicarían todo esto | Sobre shadcn/Radix con los tokens: Button (con lg de 48 px), IconButton con aria-label obligatorio, Input/Textarea autosize, Dialog, Sheet (bottom sheet en mobile), StatusChip, Toast único, EmptyState/ErrorState, Skeleton. Ruta `/design` solo para admin | axe sin serious/critical en `/design`, y Dialog y Sheet atrapan el foco, cierran con Esc y devuelven el foco (test) | P1 | 2 | DIS-03, DIS-04 |
| DIS-07 | Resto de las primitivas y migración de lo hecho a mano | Para terminar con los modales, switches, menús por coordenadas y toasts propios | Select (nativo en mobile), Switch, Checkbox, SegmentedControl, DropdownMenu/ActionSheet, Tooltip complementario, Avatar, Kbd. Migrar los 5 modales, los 5 switches y los toasts de conversation-list | Un grep de `fixed inset-0` y de `role="switch"` fuera de `components/ui` da 0 | P1 | 2 | DIS-06 |
| DIS-08 | Barrido de accesibilidad AA | Hay contraste bajo, objetivos táctiles chicos, información solo en el color o en tooltips (30 aria-label contra 57 title=) y texto oculto en mobile | axe por ruta y tema. Objetivos de 44 × 44 en mobile y 32 × 32 en escritorio (especificación §2.8; WCAG 2.2 2.5.8 pide 24 × 24 como mínimo). Foco visible. Nombres accesibles. Live regions. VoiceOver/TalkBack en el flujo Atención → Tomar → Chat → Resolver. Zoom al 200% | 0 serious/critical en todas las rutas P1, 0 objetivos chicos (script) y una grabación de VoiceOver del flujo | P1 | 2 | ATE-03, CRM-04 |
| DIS-09 | Rendimiento percibido | Celular de gama media con 4G: hay un solo loading genérico, el envío espera al refetch y la lista hace muchas queries | `loading.tsx` por ruta, UI optimista con rollback, prefetch, virtualización, tamaños reservados e instrumentación de Web Vitals sin datos personales (el detalle del relevamiento llegó cortado) | LCP < 2,5 s, CLS < 0,05 e INP < 200 ms en /atencion y en un chat demo, y tomar o resolver se refleja en menos de 100 ms | P1 | 3 | ATE-03, ATE-04, ATE-05 |
| DIS-10 | Regresión visual en CI | Mencionada en el orden del relevamiento de diseño; el detalle no llegó | Las capturas del arnés (DIS-01) se comparan en CI contra una línea base aprobada | Un cambio visual no aprobado hace fallar el PR | P1 | 1 | DIS-01, SEG-13 |

### 3.8 Mobile

| ID | Item | Por qué | Qué incluye | Listo cuando | Prio | Días | Depende de |
|---|---|---|---|---|---|---|---|
| MOB-01 | Estructura responsive: barra inferior en el celular, barra lateral agrupada en el escritorio | A 390 px la barra lateral de 256 px deja unos 134 px útiles: hoy el panel no se usa en el celular. El menú mezcla el trabajo del día con la configuración. El aviso de bot apagado tiene un emoji | Desktop: 4 grupos, como en la especificación §4.0 (Trabajo: Hoy, Atención, Conversaciones, Agenda, Contactos y Seguimientos; Crecimiento: Recorrido; Asiri; Sistema), colapsable a 64 px. Cada destino aparece recién cuando existe su pantalla (especificación, etapa 3). Mobile: barra inferior (Atención, Chats, Agenda, Contactos, Más) con badges y safe-area, y header de 56 px. Tablet: rail de íconos. Pastilla persistente "Asiri apagada" que abre un sheet (prender: solo admin) | Sin scroll horizontal en 360, 390, 768 y 1440 (Playwright), pestañas de 44 × 44 o más y ningún emoji en la interfaz del sistema | P1 | 3 | DIS-06 |
| MOB-02 | PWA instalable | Instalado, abre con un toque y habilita el push web en iOS 16.4 o superior. Hoy no hay manifest, íconos, theme-color ni viewport-fit | `app/manifest.ts` (start_url `/conversaciones` hasta que salga la bandeja el 02/12, y `/atencion` desde ese día), íconos 192/512/maskable, apple-touch-icon, viewport-fit=cover, themeColor claro/oscuro, safe-area en header, barra y composer, pantalla offline mínima. Guía de instalación de 1 página para el grupo | Lighthouse "installable" en verde. Instalada en un Android y un iPhone reales, abre standalone sin contenido tapado. Guía revisada por Claude (C17). La instalación en los celulares reales: §7 | P1 | 1,5 | MOB-01 |
| MOB-03 | Gestos en el celular | El menú de la lista solo abre con clic derecho, hay 57 tooltips que en táctil no se ven y el composer queda tapado por el teclado | `useSwipeAction` con deshacer y alternativa por botón. Mantener apretado → ActionSheet. Sheet arrastrable. `useVisualViewport` para el teclado. Lo importante que hoy está en `title=` pasa a texto visible | Deslizar con "Deshacer" en un Android y un iPhone reales, composer visible con el teclado abierto y todo gesto con su botón equivalente | P1 | 2 | DIS-06 |
| MOB-04 | Notificaciones push de urgencias en la PWA | Para que la urgencia llegue al celular de la secretaria sin depender del grupo (lo menciona el relevamiento de diseño como MO-03; el detalle no llegó) | Push web solo para casos de Urgencia y Requiere secretaria, con opt-in por usuario, sin datos de salud en el texto de la notificación. El opt-in va en la hoja "Más" hasta que exista Configuración (etapa 12) | Una urgencia demo dispara el push en un Android y un iPhone instalados, y el texto no tiene datos clínicos | P1 | 1,5 (estimación propia) | MOB-02, ATE-02 |
| MOB-05 | Decisión sobre una app nativa | La API ya acepta Bearer "para la futura app móvil". El push nativo y el audio podrían justificarla | Evaluar Expo/React Native sobre los endpoints actuales, **solo con datos de adopción** | Decisión documentada con datos. Si va, el MVP es un ítem nuevo | P3 | 0,5 | ATE-06, MOB-02 |

### 3.9 Manual y traspaso

| ID | Item | Por qué | Qué incluye | Listo cuando | Prio | Días | Depende de |
|---|---|---|---|---|---|---|---|
| MAN-01 | Cambio de secretaria: cuestionario, llamada con Irina y aviso a la clínica | Irina se va y sabe reglas que el bot no tiene. Su número es admin. Contradicción: el …6946 figura como "Irina" en el kill-switch y como "número de la clínica" en `scripts/flag_v7.py:25` | (1) Cuestionario sin cuota ni retenedor. (2) Llamada con Irina (§7) y respuestas en la KB y `decisions.md`. (3) Pedirle a la clínica (§7) el celular personal de Irina, el de la nueva y de quién es el …6946. (4) Aviso a la clínica de cómo cambian los admins, el tipo "equipo", el usuario del panel y el grupo (D5). El cambio técnico de admins va en SEG-06. (5) Horario de la secretaria en la KB. (6) Inducción de 30 minutos con la nueva, con la guía que arma Claude y el manual cuando exista (§7) | Cuestionario respondido y volcado, la contradicción del …6946 resuelta y anotada, y la clínica avisada | P0 | 1 | §7 |
| MAN-02 | Runbook técnico actualizado | `docs/runbook.md` habla de Auto Reactivar a 1 hora y de Chatwoot | Reescribirlo con lo vigente: monitor, backups, restauración, deploy, vuelta atrás, llaves del v7, `seg:off` | Alguien de afuera restaura y despliega solo con el runbook (simulacro) | P1 | 1 | SEG-08, SEG-10, SEG-19 |
| MAN-03 | Manual de operación para la clínica | Desde febrero de 2027 la clínica queda sola | Manual corto para el celular: qué significa cada alerta y qué hacer, apagar y prender el bot, modo humano, etiquetas, bandeja, qué hacer si se cae el servidor (a quién llamar), recordatorios, alta y baja de admins. PDF para el grupo (formato "informes para la Dra.": la primera página se entiende sola) | La secretaria resuelve 3 simulacros (alerta, bot a apagar, contacto mal etiquetado) solo con el manual | P1 | 2 | SEG-15, BOT-11, ATE-03 |
| MAN-04 | Ayuda dentro del panel | La ayuda está repartida en textos del código y en docs internos | `/ayuda` con guías cortas y una ayuda contextual (?) por pantalla | La secretaria resuelve 5 tareas típicas solo con la ayuda, sin preguntar | P3 | 2 | MAN-03 |
| MAN-05 | Plan de baja de accesos de Nexora y acuerdo de mantenimiento | El Anexo B pide la baja de accesos en febrero, y el corte de Dentalink y todo lo de después de febrero dependen de D9 | Lista de accesos (panel, Supabase, n8n, Vercel, grupo, teléfonos admin) con el paso para revocarlos. Propuesta de abono que arma Claude (la decisión de D9: §7) | La lista está probada en seco y el acuerdo decidido (sí o no) | P1 | 1 | SEG-12 |

---

## 4. Definición de listo (vale para todos los ítems)

Un ítem está listo solo si cumple **todo** esto, además de su criterio propio:

1. **Pruebas automáticas en verde.**
   - Las suites offline del bot (agenda, orquestador, cerebro, grafo, herramientas, chequeo, triaje) o las del panel (unitarios + smoke en CI).
   - Tests nuevos para lo que se cambió.
   - `python scripts/check_triaje.py` sano antes y después de cualquier PUT.
2. **Prueba en vivo de punta a punta** (UI → backend → efecto real) **con el número de Lucas**, sin mandar avisos al grupo de derivaciones.
   - Si la prueba necesita un aviso al grupo (por ejemplo BOT-03), se le avisa antes a la Dra.
   - Si no hace falta, se corta antes del paso que avisa.
   - No se dice "funciona" sin haberlo visto (regla 8). En el panel, se ve en el navegador a 390 px y a 1440 px, en claro y en oscuro, **con datos demo**, nunca con chats reales.
3. **Limpieza en el mismo turno** (regla 9).
   - `scripts/limpiar_numero_demo.py`: memoria, logs, label humano y `--seg` si se usó un tipo.
   - Citas de prueba anuladas (`crear_cita_prueba_examen.py --anular <id> --apply`) y recordatorio borrado (`seed_examen_v7.py --limpiar`).
   - 0 marcas temporales.
4. **Cambios en producción con red.**
   - Backup PRE/POST en `workflows/history/`, diff mostrado y script `apply_*.py` con invariantes.
   - Un PUT al v6 por semana. El PUT solo con las keys permitidas (regla 4). `webhookId: evo-webhook-v2` intacto.
   - Interruptor o vuelta atrás documentada.
   - Sin cambios entre el 21/12 y el 01/01.
5. **Memoria actualizada.**
   - `memory/current-state.md` (fecha absoluta), `decisions.md` si se decidió algo, `open-questions.md` y este backlog tachado.
   - Log de la sesión en el vault.
6. **Nada de regex que juzgue intención** (decisiones del 07/10 y del 08/10).
   - Ni banlist sobre la salida (sacada el 07/10 por decisión de Lucas), ni en tests que la vuelvan a usar.
   - Una regex sobre el texto del paciente nunca decide la intención ni bloquea una acción que eligió el modelo.
   - La intención la decide el modelo o el triaje, y los hechos los registra el código.
   - Se admite validar **formato o datos** (por ejemplo, un monto en la KB o un celular válido).
   - Quedan solo las regex que **fallan del lado seguro**, como dice la decisión del 08/10: las red flags de urgencia, como capa extra antes del modelo que también deriva (incluida la red de seguridad de los silenciados del Día 1), y el saludo o cierre, donde si no se reconoce contesta el modelo. Toda regex nueva sobre el texto del paciente tiene que justificar por escrito por qué falla del lado seguro.
7. **Confirmación antes de escribir en la agenda.** Toda acción que crea, mueve, cancela o anula un turno, del bot o del panel, muestra qué va a hacer y espera un "sí" o un toque explícito.
8. **Sin secretos ni datos de pacientes en el repo.** Secret-scan del diff y ningún teléfono que no sea de un admin.

---

## 5. Riesgos

| Riesgo | Efecto | Qué hacemos |
|---|---|---|
| **El ritmo de 3x no se sostiene.** Lo medido el 19/10 fue una tarde con trabajo conocido, y lo que viene tiene más diseño, más datos y más pruebas en vivo | La lista que pidió Lucas se corre hacia el 26/02 | Revisión de cada viernes con el ritmo medido. Si baja de 2,5x dos semanas seguidas, se aplica el orden de corrimiento de §2 (SEG-21, SEG-18, MOB-05 y BOT-16), y el informe dice qué más se corre. La reserva de 1 de cada 5 días y el 25-26/02 son el colchón |
| **Muchos cambios a producción seguidos.** Con 3x hay cerca de un deploy por día hábil, entre el bot y el panel | Más chances de romper algo durante el pase del v7 o con la clínica sola | "Una cosa a la vez" (§2): un cambio a producción por día, y ningún deploy del panel el día de un PUT o de una llave del v7. El panel no se despliega durante las semanas de adopción ni el día que cierra una compuerta. Vuelta atrás probada (SEG-08) y tests en CI antes del diseño (SEG-13) |
| **El pase del v7 tiene las compuertas justas** (02/11, 09/11 y 16/11) | Si SEG-06 sale mal el lun 02/11, o si aparece un P0 en el piloto, no hay días de colchón | El piloto arranca solo si SEG-06 quedó verificado esa misma mañana. Si una compuerta falla, ese paso se corre una semana y la cola sigue. Interruptor global en menos de 1 minuto |
| **El contrato (SEG-17) no llega a tiempo** | Sin la fase (b) del espejo se traban CRM-06, REC-01, REC-04 y AGE-06, y lo que depende de ellos | Pedido el 21/10, un mes antes que en la primera versión. La fase (a) del espejo y la agenda en sombra no lo esperan (C12). Las pantallas avanzan con datos demo y se enchufan cuando llega |
| **La clínica recibe muchas pantallas nuevas en poco tiempo** | La secretaria se pierde o vuelve al grupo de WhatsApp | La bandeja, la PWA y "Por clasificar" están antes del 04/12. Dos semanas de adopción medidas (07-11/12 y 01-05/02). Cada etapa sale con un aviso corto al grupo, y el manual llega al final |
| **El v6 sigue atendiendo hasta el 16/11** (y más, si falla una compuerta) | Un turno escrito sin un "sí", la misma clase que el incidente del 14/10 | BOT-02 parcheado el 27/10 (C6) |
| **Incidente con un paciente en el piloto o en "todos"** | Se rompe la confianza de la Dra. (regla 1) | Compuertas de 5 y 10 días hábiles sin P0, revisión diaria hasta el 27/11, interruptor global en menos de 1 minuto, y nada se abre sin el OK de la Dra. (§7) |
| **Lo de §7 que no llega a tiempo** | Se trabarían SEG-03 y SEG-06 (permiso de deploy), CRM-02 (OK a la lista), el pase del v7 (OK de la Dra.), la fase (b) del espejo (contrato) y BOT-13 y BOT-16 en vivo | Claude lo pide con fecha, por el grupo o en el informe del viernes. Si algo no llega, se sigue con el próximo ítem que no depende de eso |
| **Cambio de secretaria a mitad del plan** | Se pierde lo que sabe Irina, quedan admins equivocados y la adopción del panel recae en alguien nuevo | MAN-01 en la semana 1, admins en SEG-06, BOT-11 para que cambiar admins no necesite un PUT, e inducción con el manual |
| **El monitor depende de GitHub** | Si el repo pasa a privado, los minutos de Actions y el billing (bloqueado en el panel) pueden frenar el vigía. Los cron se pausan tras 60 días sin actividad | SEG-05 con un servicio independiente y "hombre muerto". El vigía de GitHub queda como respaldo |
| **El VPS es un único punto de falla** (n8n, Evolution, panel, Redis) | Otra caída como la del 16-19/10 | SEG-05, SEG-09, SEG-10 y SEG-19, y SEG-15 en lenguaje llano para la clínica |
| **Datos de salud** (Ley 25.326, transferencias internacionales) | Riesgo legal para la clínica y para Nexora | Espejo en dos fases: la (a) sin datos de pacientes y la (b) solo con contrato (C12). Nunca DNI, dirección ni comentarios. Demo con datos inventados. Repo purgado (y privado: §7) |
| **WhatsApp por Evolution (no es la API oficial)** | Bloqueo del número si se mandan envíos masivos | Seguimientos de a uno, con tope por número y línea de baja (D8), y sin "seleccionar todos" |
| **Límite de Dentalink (429)** | Si el espejo, el panel y el bot compiten, el bot se queda sin agenda | Limitador común con prioridad para el bot (AGE-02), desplegado el 30/11, antes de la fase (a) del espejo. Ventanas cortas y de noche |
| **Pruebas en celulares reales.** La emulación de Playwright no cubre instalar la PWA, el push ni el teclado de iOS | No se puede cumplir la regla 8 en esas partes | Tandas cortas con guía (§7) al cerrar las etapas 3, 4 y 5 y MOB-04. Mientras tanto, Playwright con emulación de dispositivos (C4) |
| **Estimaciones tomadas de los relevamientos** (uno llegó cortado) | Las fechas pueden moverse | Se recalculan cada viernes, sumando los días de la cola y no a ojo. La especificación de diseño estima sus etapas en 54 días, y se usan los días del backlog por ítem, que dan parecido. MOB-04 se re-releva antes de empezarlo |


---

## 6. Qué NO entra (y por qué)

- **Banlist de frases ni ningún regex que juzgue intención.** Lucas la sacó el 07/10: en las pruebas solo frenó mensajes inocentes y el reemplazo genérico confundía al paciente. No vuelve sin su OK (regla 5).
- **Visión de fotos dentales, RAG abierto, sub-agentes "creativos", diagnóstico u opinión médica.** El MVP es agendar, recordar y escalar todo lo demás (regla 6). Las fotos y las urgencias se derivan.
- **Validar montos de comprobantes de pago.** El bot recibe y deriva (scope del MVP).
- **Decir la cuota mensual o el precio del retenedor.** Decisión de la Dra. del 16/10: solo el precio de la consulta.
- **Envíos masivos o "seleccionar todos" en los seguimientos.** D8 y riesgo de bloqueo con Evolution.
- **Cortar Dentalink antes del 01/03/2027, o sin los criterios del §4.4 en verde y el acuerdo de mantenimiento (D9, §7).** La agenda propia corre en sombra desde el 14/12 y en paralelo del 15 al 17/02. El informe del 23/02 (AGE-07) dice si se cumplen los criterios, pero el corte no es antes del 01/03/2027.
- **Migrar la historia clínica en 2026.** Plan §4.6: requiere contrato y validación legal.
- **App nativa en 2026.** Primero la PWA. Una app nativa solo con datos de adopción (MOB-05).
- **Clínica 2, demo navegable y alta repetible.** D10: pasan a 2027. Lo que sí entra es dejar el panel preparado (config por clínica, migraciones versionadas, login por usuario).
- **Narrativas con scroll, preloaders y parallax.** El relevamiento de diseño los descartó: en una herramienta operativa estorban. Movimiento solo como respuesta a lo que hace la persona.
- **Datos personales sensibles en el espejo (DNI, dirección, comentarios) antes del contrato.** Minimización (§4.6).
- **Chatwoot.** Se baja: no se le agregan funciones y se limpian sus restos (SEG-21).
- **El esquema multi-tenant viejo del panel (migraciones 0001-0007).** Se archiva. No es el v3 real.

---

## Anexo — Contradicciones resueltas y faltantes

| Tema | Qué decía cada fuente | Cómo se resolvió |
|---|---|---|
| Monitor externo | Bot: "falta". Memoria del 19/10: vigía de GitHub activo (cada 30 minutos, mail a Lucas) | Existe uno básico. SEG-05 lo **completa** (cada 5 minutos, Evolution, hombre muerto, aviso a la clínica, sin depender de GitHub) |
| Fechas del v7 | Plan del 13/10: PUT-C a todos el 03/11. Plan del 19/10 y pedido: grupo chico 02/11, nuevos 09/11, todos 16/11 | **Replan del 19/10:** se usan las pedidas (02/11, 09/11 y 16/11). Con el ritmo 3x los P0 entran antes, y los PUT caen uno por semana: SEG-06 el lun 02/11 y BOT-09 el lun 09/11, a primera hora. Las compuertas de 5 y 10 días hábiles cierran el 06/11 y el 13/11 (§2) |
| Calendario | El pedido dice "lun 20/10/2026" | El 20/10/2026 es **martes** (el 19/10 es lunes, como dicen los dos planes). El orden arranca el mar 20/10 |
| Regresión del v7 | Bot: examen completo `--todos --reps 3` y los 16 reales. Memoria del 08/10 ("testear solo fallas"): con IA solo lo que falló, y las regresiones las cubre la suite offline | Manda la indicación de Lucas: BOT-07 = suite offline + volver a correr con IA solo lo tocado o fallado |
| Precio de la cuota | Panel: la KB y /servicios dicen que se puede decir. Decisión del 16/10: no | Manda la decisión. BOT-04 alinea el panel |
| Número …6946 | Kill-switch: "Irina". `flag_v7.py:25`: "número de la clínica" | Queda abierto. Se confirma con la clínica en MAN-01 antes de tocar admins (SEG-06) |
| Dónde está el panel | Plan del 13/10: Vercel. Realidad: contenedor en el VPS (panel.raquelrodriguez.com.ar), con `deploy.yml` viejo | Se toma el VPS. SEG-08 unifica el deploy |
| Bandeja de Atención | Plan: 26-30/10 sobre el panel actual. Panel: depende de la estructura mobile, los componentes, las migraciones y los roles. Diseño: todo el sistema de diseño antes (~34 días de P0) | Base **mínima** antes de la bandeja (DIS-01 a DIS-04, DIS-06, MOB-01, SEG-12, SEG-14). **Replan del 19/10:** con 3x, esa base entra entre el 30/10 y el 24/11, y la bandeja sale el 02/12. El resto del sistema de diseño (etapas 4, 5 y 7 a 13) entra entre el 02/12 (CRM-03 y CRM-04, la primera parte de la etapa 7) y el 19/02 |
| Espejo de Dentalink | Plan del 19/10: semana 26-30/10. Plan del 13/10: fines de noviembre | **Replan del 19/10:** entra antes de febrero, en dos fases (C12). La (a), sin datos de pacientes, el 01/12. La (b), con el contrato, el 16/12 |
| Recorrido del paciente | Plan del 19/10: semana 26-30/10. Depende del espejo ("vino", "en tratamiento") | **Replan del 19/10:** REC-01 el 08/01 y el resto en enero, sobre el espejo |
| Login por usuario | Plan del 13/10: enero (Supabase Auth). Panel: roles mínimos ahora | SEG-12 (roles mínimos y auditoría) el 11/11. SEG-20 (Supabase Auth) después de febrero. La agenda propia usa el actor de SEG-12 (C13) |
| Red de seguridad en vivo y "sin avisos al grupo" | BOT-03 tiene que avisar al grupo para probarse | Es la única excepción a la Definición de listo, con aviso previo a la Dra. |
| Prioridades duplicadas | Mismos ítems con distinta prioridad (por ejemplo, la bandeja P1 en el panel y P0 en diseño) | Se unificaron: P0 solo para lo que es riesgo hoy, y lo de diseño y mobile pasa a P1 o P2 según el calendario |
| Duplicados fusionados | La rotación de la clave estaba en el bot y en el panel. Accesibilidad en el panel y en QA-01. El tema estaba en DS-02 y DS-06. Familias en los planes #7 y #12. "Hacer ahora" en el panel, el bot y PA-10. La bandeja en el panel y en PA-01 | Un ítem cada uno: SEG-03, DIS-08, DIS-03, CRM-06, REC-06 y ATE-03 |

**Correcciones de la revisión de completitud (19/10):**

| Tema | Qué decía | Cómo quedó |
|---|---|---|
| BOT-02 (read-back del v6 al agendar y reprogramar) | Primera versión: "no parchearlo, el riesgo queda anotado". Decisión del 15/10: no revisable y vale para el v6 mientras atienda | Manda la decisión: se parchea, como P0 (C6) |
| Acceso de deploy (SEG-07) | Primera versión: el 11/11. Pero SEG-03 (22/10) y SEG-06 (28/10) cambian el `.env` y variables en el VPS | SEG-07 pasa a la semana 1, como P0 |
| Commit y purga (SEG-04 y SEG-02) | Primera versión: la purga primero y el commit de los 98 cambios después | El commit local va primero (`filter-repo` con cambios sin commitear arriesga perderlos) y el push sale después de la purga |
| BOT-09 y la compuerta del piloto | Primera versión: el PUT el 05/11 "dependiendo de BOT-08 en verde", con la compuerta el 06/11 | El PUT instala las llaves apagadas. Lo que espera la compuerta es prender la llave |
| Abogado (SEG-17) | Primera versión: el 04/02, después del espejo. D12: "antes del espejo" | Pedido al abogado el 20/11 (el replan lo adelantó al 21/10). AGE-03 depende del contrato |
| Semana de adopción (ATE-06) | Primera versión: del 18 al 22/01, con CRM-04, CRM-03 y la propia medición terminando adentro de esa semana | Del 01 al 05/02, con todo desplegado antes y sin deploys del panel durante la semana (el replan suma otra, del 07 al 11/12: C18) |
| Último deploy antes de la veda | Primera versión: vie 18/12, con MOB-01 empezando el 16/12 (3 días) | Último deploy el mié 16/12 (el replan pasó MOB-01 y DIS-03 a noviembre: §2) |
| Test de textos del triaje | BOT-12 pedía `test_triaje_textos_banlist --db`, que lee el `BANLIST` del nodo que se sacó el 07/10 | Se saca del criterio (regla 5). Revisión de formato en su lugar |
| Regex en la Definición de listo | §4.6 decía "ni clasificar el mensaje del paciente con regex", pero las red flags y la red de seguridad del Día 1 son regex permitidas por la decisión del 08/10 | §4.6 alineado con la decisión del 08/10: solo las que fallan del lado seguro, con justificación escrita |
| Señales de monitoreo | SEG-11 y SEG-19 pedían las mismas señales (Supabase, Redis, recordatorios) | Se construyen en SEG-11. SEG-19 suma solo el token de Dentalink y `Activar Takeover` |

**Pendientes de `memory/backlog.md` que no estaban en la primera versión (qué pasa con cada uno):**

| Pendiente viejo | Qué pasa |
|---|---|
| Conversión del v7 (`conv:on`, oferta D7) y segmentación completa (PUT-D, `contacto_ruta`, D3), del plan del 13/10 | Ítems nuevos: BOT-16 (febrero) y CRM-09 (después de febrero) |
| Workflow de entrada genérico del v7 (D10) y sacar el freno y las herramientas de Dentalink del v6 (plan §5) | Ítem nuevo: BOT-17 |
| Rol `bot_n8n` (plan del 13/10, Anexo B) | Ítem nuevo: SEG-24 |
| Bajar Chatwoot del VPS (05/10) | Ítem nuevo: SEG-25. SEG-16 y SEG-21 limpian los restos |
| Primera alta en vivo de un paciente nuevo (`rut`), pendiente desde el 07/10 | Dentro de BOT-09, antes de prender `v7:nuevos` |
| Irina revisa los mensajes del 06 al 08/10 | Dentro de SEG-01 |
| Alerta cuando `Activar Takeover (fromMe)` falla en silencio | Dentro de SEG-19 |
| Tabla `@lid` ↔ teléfono; duplicados de Dentalink y fichas sin DNI | Dentro de CRM-06 |
| ¿Un mensaje mandado desde el panel prende el modo humano y tapa el "Confirmo"? | Decidido por Claude (C14), dentro de REC-06 |
| `apply_desacoplar_chatwoot.py` re-ejecutable | Dentro de SEG-04 |
| Extender el precio dinámico a la cuota mensual (KB id=36) | **Descartado** por la decisión del 16/10 (solo la consulta) |
| Banlist antes del Formatting Agent, recalibrar el juez de Banlist Shadow | **Descartados** por la decisión del 07/10 (sin banlist) |
| Bugs del v6 que el v7 reemplaza: Formatting Agent que reescribe el anuncio, cierres del General, `Parse Intent`, Fases 1-3 de reprogramaciones, `ver_turnos_paciente` sin conectar, `wa_outbound` del Sub-WF, aviso `[ATENCION HUMANA…]` en memoria, Canned Sidecar de horarios y dirección | **Se cierran con el v7 a todos (16/11).** No se arreglan en el v6, salvo BOT-02, que es regla dura. Si una compuerta falla y el v6 sigue más de 4 semanas, se re-evalúan |
| Adjuntos del staff y del paciente a Storage (scripts listos desde 06-07/09, sin aplicar) | Dentro de ATE-05, solo con el contrato (C16). Si no, se archivan. Retención (`TKByjzVE8rGKTioT`) figura activa en el snapshot: no hace falta ítem |
| Reportero semanal y scoring de urgencias | Sin ítem. Se evalúa en REC-07 (el resumen que llega solo) y en MAN-02 (quién lo mira después de febrero) |
| Bracket perdido → turno en vez de triaje (REAL-07) | Decidido por Claude (C15): sigue en triaje y derivación, que es el lado seguro. Se revisa con la Dra. en BOT-12 |

**Correcciones del replan con el ritmo real (19/10, tarde):**

| Tema | Qué decía | Cómo quedó |
|---|---|---|
| Ritmo | 1 día de esfuerzo por día hábil: ~180 días contra 80 hábiles | 3x, con la medición del 19/10 (§1). Antes del 26/02 entran ~178 de ~197 días |
| Pase del v7 | 05/11, 16/11 y 19/11 | 02/11, 09/11 y 16/11, como se pidió |
| Sistema propio | CRM, recorrido, seguimientos, espejo y agenda propia después de febrero (≈ marzo a agosto) | Entre el 16/11 (AGE-02) y el 23/02 |
| Bandeja y PWA | Enero | PWA el 24/11, bandeja el 02/12 y push el 03/12 |
| Diseño | La base en diciembre y enero, y el resto después de febrero | Las 14 etapas de la especificación, entre el 30/10 y el 19/02 |
| Tareas y decisiones de Lucas | Tabla "Lo que necesita Lucas", con 13 filas | Las decisiones técnicas las toma Claude (C1 a C18, en §1). Lo que es imposible para Claude está solo en §7 |
| Semana de adopción | Una sola, 01-05/02 | Dos: 07-11/12 y 01-05/02 (C18) |
| SEG-17 (abogado) | Pedido el 20/11 | Pedido el 21/10, y el espejo partido en dos fases (C12) |
| SEG-10 (backups) | Esperaba D1 (Supabase Pro) | `pg_dump` sin esperar (C10) |
| CRM-01 | Esperaba que Chrome estuviera conectado | Playwright (C4) |
| Espejo "solo si entra" y revisión del 22/01 | AGE-02 y AGE-03 podían pasar a marzo | Entran (P1). La revisión del 22/01 ya no hace falta |
| Prioridades | CRM, REC, AGE-04/05/06 y parte de DIS y MOB en P2 o P3 | P1, porque son parte del pedido |

**Faltantes:**
- **Cuarto relevamiento:** no llegó; solo hubo 3.
- **Relevamiento de diseño:** llegó cortado en QA-02. Por eso DIS-09, DIS-10 y MOB-04 tenían detalle parcial. La etapa 13 de la especificación del 19/10 completa DIS-09 y DIS-10. MOB-04 se re-releva antes de empezarlo.
- **MCP de Dribbble:** no estuvo conectado en ningún relevamiento. Ya no hace falta: la especificación de diseño del 19/10 resolvió DIS-02 (C7).

---

## 7. Solo puede hacerlo otra persona

> Claude lo pide con fecha, por el grupo o en el informe del viernes, y deja preparado todo lo que se puede preparar. Esto no se repite en otras partes: en el resto del documento aparece como "(§7)".

| Quién | Qué | Para | Fecha |
|---|---|---|---|
| Lucas | Pasar `raquel-n8n` a privado desde la cuenta nexoragrowth (botón en GitHub, 5 minutos) | SEG-02 | mié 21/10 |
| Lucas | Habilitar en los permisos de Claude Code la lista de comandos de deploy por SSH que deja Claude, porque Claude no puede cambiar sus propios permisos | SEG-07 (sin esto se traban SEG-03, SEG-06, SEG-08 y SEG-09) | mié 21/10 |
| Lucas | La llamada con Irina, con el cuestionario de Claude | MAN-01 | jue 22/10 |
| Lucas | Levantar "Recordatorios: NO TOCAR" para BOT-13. Es una regla dura del proyecto, y Claude no se la puede autorizar a sí mismo | BOT-13 | vie 22/01 |
| Lucas | Los gastos: Supabase Pro (D1, opcional, porque los backups no lo esperan) y cualquier servicio pago. También el alta en un servicio externo que pida verificar el mail o el teléfono de una persona | SEG-10, SEG-05 | cuando Claude lo pida (para SEG-05, a más tardar el jue 22/10) |
| Lucas y la Dra. | D9: el acuerdo de mantenimiento. Claude arma la propuesta | MAN-05 y "Después de febrero" | vie 19/02 |
| La Dra. | OK para que el v7 atienda a pacientes reales: un solo sí para el pase completo (grupo chico el 02/11, nuevos el 09/11 y todos el 16/11), con las compuertas de C9 | BOT-08, BOT-09 | vie 30/10 |
| La Dra. | OK a la lista semilla | CRM-02 | vie 06/11 |
| La Dra. | Aprobar los textos que le llegan al paciente, que redacta Claude: la presentación del anuncio (BOT-06), el aviso de privacidad (SEG-17), las plantillas de seguimiento (REC-04 y REC-05), la conversión (BOT-16) y el triaje con sus videos (BOT-12) | Esos ítems | BOT-06: 06/11 · SEG-17: 27/11 · REC: 15/01 · BOT-16: 29/01 · BOT-12: cuando pueda |
| El abogado y la Dra. | Revisar y firmar el contrato de encargado de datos | SEG-17 (sin esto se traban la fase (b) de AGE-03, CRM-06, REC-01, REC-04 y AGE-06) | Objetivo: vie 27/11. A más tardar: vie 11/12 |
| La clínica | Revisar la lista de chats que quedaron sin respuesta en la caída del 16-19/10, y confirmar que se revisaron los del 06 al 08/10. Los datos que solo tiene ella: el celular de la nueva secretaria y la fecha de salida de Irina, de quién es el …6946, qué es el "puntito amarillo", si atienden el lun 07/12 (entre el fin de semana y el feriado del 08/12) y el calendario de vacaciones de enero y febrero | SEG-01, SEG-06, MAN-01, BOT-13, ATE-06 | La revisión y los celulares: vie 23/10 (con los celulares, Claude avisa el lun 26/10 cómo cambian los admins y prepara SEG-06). El resto: vie 04/12 |
| La secretaria | Clasificar los 12 contactos dudosos de la lista semilla. La inducción de 30 minutos (la nueva). Limpiar en Dentalink las fichas duplicadas y cargar los DNI que faltan. Dos sesiones de 20 minutos en su celular, los 3 días de práctica en paralelo con la agenda propia (si acepta) y los 3 simulacros del manual | CRM-02, MAN-01, CRM-06, ATE-06, AGE-06, MAN-03 | Desde el mar 10/11 · la semana en que entra · desde el lun 04/01 · mié 09/12 y semana del 01/02 · 15-17/02 · mié 24/02 |
| Quien tenga los celulares (la secretaria o Lucas) | Probar en un Android y en un iPhone reales lo que la emulación no cubre: instalar la PWA, el push, el teclado y deslizar. Son 10 minutos por tanda, con la guía de Claude | MOB-02, MOB-04, MOB-03, ATE-05 | 25/11, 03/12, 05/01 y 12/01 |
