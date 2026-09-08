# Recordatorio distinto para las CONSULTAS (primera visita) — pedido de la Dra. Raquel (2026-09-08)

**Fecha**: 2026-09-08 (ronda de corrección la misma tarde: regla anclada, regex del precio, guards del script, §6.4) ·
**Estado**: implementado, tests verdes (`node tests/test_recordatorio_consultas.js`), dry-run
limpio contra el workflow vivo (solo GET). **NADA aplicado**: falta el OK de Lucas para `--ddl` y `--apply`, y la
confirmación de la Dra. de que "puntito amarillo" = motivo de atención `Consulta Ortodoncia` (§2).

- Workflow: `Recordatorio de Turno 48HS - Dra. Raquel` (`7RqTApkvVavRmq3R`, 21 nodos, ACTIVO, producción)
- Script: `scripts/apply_recordatorio_consultas.py` (`--dry-run` default · `--ddl` · `--apply` · `--rollback <PRE>`)
- Fuente única del código: `recordatorios/preparar_mensaje.js` (jsCode nuevo), `recordatorios/gate_leer_config.sql`
  (SQL nuevo del gate), `recordatorios/preparar_mensaje.vivo_2026-09-08.js` (snapshot BYTE A BYTE del nodo vivo,
  baseline de los tests y guard del apply)
- Tests: `node tests/test_recordatorio_consultas.js` · DDL también en `scripts/rebuild_v3_schema.sql` §4

---

## 1. El pedido, textual (WhatsApp, 2026-09-08 09:20)

> "los turnos que tienen un puntito amarillo son consultas (o sea pacientes que vienen por primera vez). Necesito que
> a todos ellos el agente le envie un mensaje en particular como recordatorio del turno. Seria el siguiente:"

```
✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨

Estimada Martina,
Le recordamos su turno con la Dra. Rodríguez Raquel:

📅 Miércoles 9 de septiembre de 2026
🕔 16:10 hs
📍 Balcarce Nº37, 2º piso

Para confirmar su asistencia le solicitamos abonar el valor de la consulta ($50.000).

⚠️ Importante:
* Si su turno ya está abonado, solo responda a este mensaje con un "confirmo".
* Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.

Esperamos su confirmación, gracias por elegirnos 💙
```

> "Lo que quiero lograr es que sepan que la confirmacion es si o si con el pago (esto solo en consultas)".

---

## 2. Regla de detección: `motivo_atencion` EMPIEZA con "consulta"

En cada cita que devuelve Dentalink (`GET /sucursales/1/citas`) el único campo que distingue una primera visita es
`motivo_atencion`. Verificado el 2026-09-08 sobre 66 citas de los próximos 10 días y sobre las 57 enviadas en los
últimos 14 días:

| motivo_atencion (tal cual llega) | citas próximas | enviadas 14 d |
|---|---|---|
| `En TTO LARGO` | 47 | 36 |
| `En TTO CORTO` | 7 | 6 |
| **`Consulta Ortodoncia `** (con espacio final) | 7 | 5 |
| `Inicio TTO de Ortopedia` | 2 | — |
| `Control Contención ` | 1 | 4 |
| `Devolución con escaneo ` | 1 | 4 |
| `No registra motivo` | 1 | — |

- `tratamiento_sin_asignar` es `0` en TODAS (las consultas también tienen `nombre_tratamiento: 'Nuevo plan de
  tratamiento'`): **no sirve** para detectarlas.
- Regla implementada: `es_consulta = /^consulta\b/i.test(String(cita.motivo_atencion || '').trim())`. Tolera espacios y
  mayúsculas; **anclada al inicio** de la palabra: `Consulta Ortodoncia`, `Consulta`, `CONSULTA` sí; `Control post
  consulta`, `Consultar precio` y `Primera Consulta` no (corrección 8/9: el substring `/consulta/i` daba `true` para
  "Control post consulta"). Asimetría buscada: un falso negativo manda el genérico de hoy (sin daño); un falso positivo
  le pediría el pago de la consulta a un paciente en tratamiento. `null`/ausente → `false`. Si la Dra. nombra otro
  motivo de primera visita (p. ej. "Primera Consulta"), es una línea en `recordatorios/preparar_mensaje.js`
  (`const es_consulta`) + los tests de motivo (§7 del test).
- **Pendiente de la Dra. (Lucas tiene que confirmarlo)**: que el "puntito amarillo" de la agenda sea exactamente el
  motivo `Consulta Ortodoncia` y que no exista otro motivo de primera visita. Una consulta cargada sin motivo
  (`No registra motivo`, 1 caso hoy) o con otro texto recibe el recordatorio genérico de siempre (falso negativo,
  sin daño: es el mensaje de hoy).
- Las 5 consultas de los últimos 14 días (citas 8626, 8831, 8834, 8692, 8773) recibieron el template genérico.

---

## 3. Los templates finales

### 3.1 Consulta, recordatorio 72h (el del cron) — bloque textual de la Dra.

Idéntico al de §1. Variables: `Estimada/Estimado/Estimado/a` + nombre (mismo heurístico de género que hoy: primer
nombre terminado en *a* / *o* / otra letra), día de la semana, fecha, hora y dirección como hoy, y el **precio
dinámico** en `(...abonar el valor de la consulta (<precio>).`. Renderizado con Martina / miércoles 9 de septiembre
de 2026 / 16:10 / precio real de la KB:

```
✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨

Estimada Martina,
Le recordamos su turno con la Dra. Rodríguez Raquel:

📅 Miércoles 9 de septiembre de 2026
🕔 16:10 hs
📍 Balcarce Nº37, 2º piso

Para confirmar su asistencia le solicitamos abonar el valor de la consulta ($50.000).

⚠️ Importante:
* Si su turno ya está abonado, solo responda a este mensaje con un "confirmo".
* Para cancelar o reprogramar, solicitamos avisar con un mínimo de 48 hs de anticipación.

Esperamos su confirmación, gracias por elegirnos 💙
```

### 3.2 Consulta, recordatorio 24h — template corto de hoy + frase final (**a validar por la Dra.**)

El 24h **no sale nunca por el cron** (`Fecha Mañana` apunta a +2 días hábiles: 57/57 envíos de 14 días fueron `72h`);
solo es alcanzable por el webhook manual con `fecha_target` = mañana. Se le suma una frase con la misma regla, sin
inventar política:

```
Hola, Martina 😊 le recordamos que mañana la esperamos a las 16:10 hs para su atención con la Dra. Raquel Rodríguez en nuestra Clínica Áurea Odontología Estética. Saludos ✨

Recuerde que la consulta se confirma con el pago de su valor ($50.000). Si ya lo abonó, responda "confirmo".
```

### 3.3 Todo lo que NO es consulta: sin cambios, BYTE A BYTE

Los dos templates genéricos (72h y 24h) quedan exactamente como hoy. Lo garantizan (a) el test, que corre el código
VIVO congelado (`preparar_mensaje.vivo_2026-09-08.js`) y el nuevo con los mismos mocks y exige salida idéntica para
7 motivos reales, 7 formatos de celular y el camino manual; (b) el test estructural: las 12 líneas literales de los
templates del nodo vivo están textuales en el nuevo; (c) el apply, que solo acepta como base el snapshot conocido.

---

## 4. De dónde sale el precio

- Fuente: `knowledge_base` id **21** (categoría `precios`, título "Valor de la primera consulta"), que la Dra. edita
  desde el panel. Contenido hoy: "La primera consulta tiene un valor de $50.000 e incluye evaluación + diagnóstico
  presuntivo. ...". Mismo doc que usa el v6 (`Get KB Horarios y Precio` → `Extraer Horarios y Precio`).
- **Cómo llega al nodo**: `Preparar mensaje` empareja la cita por `$("Solo citas activas").all()[$itemIndex]` →
  **no se puede insertar ningún nodo** entre `Solo citas activas` y `Preparar mensaje`. Por eso la lectura va en el SQL
  de `Gate - Leer config` (que corre UNA vez por corrida): a la query de hoy se le suma
  `(SELECT kb.contenido FROM public.knowledge_base kb WHERE kb.id = 21) AS precio_contenido`. La columna `suspender`
  queda idéntica (`Gate - ¿Suspendido hoy?` solo lee `$json.suspender`; el test y el apply lo verifican). Ejecutada
  hoy con SELECT contra el v3: `(false, <contenido id 21>)`.
- **Parseo** en `Preparar mensaje`: `/\$\s*(\d{1,3}(?:[.,]\d{3})+|\d{4,})/` sobre `precio_contenido` → `$50.000`.
  Es el criterio del v6 (`/\$[\d.,]+/`) **más** tolerancia a espacios ("$ 55.000", "$  70.000") y sin tragarse el
  punto final de oración ("$55.000."), y **más estricto** en lo que acepta como importe: miles con separador
  (`dd.ddd` / `dd,ddd`, también `$1.500.000`; de "$50.000,00" toma `$50.000`) o 4+ dígitos seguidos. "$50mil", "$5",
  "u$s 100" o "$ abc" no son un precio y caen al fallback (con el regex laxo de la primera versión, "$50mil"
  imprimía "$50"). Si el texto trae varios importes se toma el primero, como el v6. Decisión: con el regex estricto
  del v6, "$ 55.000" caía al fallback y el paciente recibía un precio viejo en silencio (R11 del lector). Sin importe,
  fila 21 borrada o columna ausente → fallback `'$50.000'`. **Desalineación conocida**: si la KB dijera "$ 55.000", el
  v6 (`Extraer Horarios y Precio`, regex estricto) seguiría contestando `$50.000` y el recordatorio `$55.000`; alinear
  el regex del v6 es un PUT aparte (backlog P3).
- **Camino manual (webhook / botón "adelantar" del panel)**: no pasa por el Gate → `$('Gate - Leer config')` tira →
  try/catch → fallback `$50.000` (`precio_origen: 'fallback'` en la salida del nodo, visible en la ejecución). Si Raquel
  cambia el precio en el panel, los envíos MANUALES lo ignoran hasta que se sume un nodo `Precio consulta (KB)` entre
  `Webhook Manual Recordatorios` y `Fecha Mañana` (fuera de este cambio; `Fecha Mañana` lee el webhook por nombre y
  tolera un nodo intermedio).

---

## 5. Qué cambia en el workflow (3 nodos, 0 conexiones, 0 nodos nuevos)

| Nodo | Campo | Cambio |
|---|---|---|
| `Preparar mensaje` (code v2, runOnceForEachItem) | `jsCode` | = `recordatorios/preparar_mensaje.js`: `es_consulta`, `motivo_atencion`, lectura del precio con try/catch, tres ramas de template. Salida = las 10 keys de hoy + `motivo_atencion` (string, `''` si falta), `es_consulta` (boolean, nunca null), `precio_consulta`, `precio_origen`. Conserva `const TEST_MODE = false;` literal (lo busca `apply_toggle_recordatorios_test_mode.py`); el apply respeta el valor VIVO del flag. |
| `Gate - Leer config` (postgres 2.5, onError continue) | `query` | = `recordatorios/gate_leer_config.sql` (la de hoy + `precio_contenido`). |
| `Insert recordatorios_enviados` (postgres 2.6, defineBelow) | `columns.value` + `columns.schema` | + `motivo_atencion` (string) y `es_consulta` (boolean) desde `$('Preparar mensaje').item.json`. |

**Columnas nuevas** en `public.recordatorios_enviados`: `motivo_atencion TEXT`, `es_consulta BOOLEAN` (nullable; las
filas anteriores quedan NULL = desconocido — no backfillear como false). DDL idempotente en el script (`--ddl`) y en
`scripts/rebuild_v3_schema.sql` §4.

**Orden obligatorio: `--ddl` ANTES de `--apply`** (R1). El nodo Postgres v2.6 valida las columnas contra la tabla VIVA
(no contra `columns.schema`) y el Insert corre DESPUÉS de `Enviar WhatsApp`: sin las columnas, el próximo cron manda los
WhatsApps y explota en el Insert → 0 filas → `consultar_recordatorios_abiertos` no encuentra el turno cuando el paciente
responde "confirmo". El `--apply` se niega a correr si la tabla no las tiene.

**Memoria del bot**: `Guardar en Chat Memory` guarda `prep.message` tal cual (2 filas `reminder_note`): el bloque nuevo
entra igual. El v6 reconoce "el último AI fue el recordatorio del cron" por prompt con dos señales — empieza con
"AUREA ODONTOLOGIA ESTETICA" y contiene "Le recordamos su turno con la Dra. Rodriguez Raquel" — y el bloque de la Dra.
conserva las dos (test "señales que el v6 usa"). Consumidores REST de `recordatorios_enviados` (`consultar_recordatorios_
abiertos`, `marcar_recordatorio_*`) usan columnas explícitas: indiferentes a las nuevas. `Daily Summary Recordatorios`
solo cuenta `Enviar WhatsApp`/`Sin celular (skip)`. Panel: `lib/v3/database.types.ts` `V3Recordatorio` puede sumar
`motivo_atencion?: string | null; es_consulta?: boolean | null` cuando quiera mostrarlos (no es necesario para el PUT).

**Lo que NO se toca**: trigger (`0 13 * * 1-5` sin timezone = 08:00 ART lunes a viernes, por la TZ UTC+2 de la
instancia; el apply filtra `availableInMCP`/`binaryMode` de settings y aborta si aparece `timezone`), webhook
(`trigger-recordatorios-manual`), conexiones, `Guardar en Chat Memory` (opcional a futuro: sumar "Tipo: consulta" a la
NOTA INTERNA para que el Sub-Agent Confirmar lo vea), el emparejamiento por `$itemIndex` (R2 preexistente, anotado).

---

## 6. Cómo probar

### 6.1 Sin tocar nada
```
node tests/test_recordatorio_consultas.js          # consulta 72h/24h, tratamiento byte a byte, precio, manual, motivo, género, celular
python scripts/apply_recordatorio_consultas.py     # dry-run: GET + diff de jsCode/query/columns + estado de la tabla
python scripts/check_triaje.py                     # antes de cualquier PUT (regla dura 9)
```

### 6.2 Aplicar (con OK de Lucas, en este orden)
```
python scripts/apply_recordatorio_consultas.py --ddl      # ALTER TABLE ... ADD COLUMN IF NOT EXISTS x2 + verificación
python scripts/apply_recordatorio_consultas.py --apply    # PRE -> PUT -> POST -> verificación post-PUT
```
Backups: `workflows/history/Recordatorio_PRE_consultas_<ts>.json` / `Recordatorio_POST_consultas_<ts>.json`.

### 6.3 Prueba real por el webhook manual (la corre el orquestador después del OK)

**Prerrequisito en Dentalink** (UI de la clínica; la API solo se toca con GET): las fichas de prueba de Lucas son
`Test - Lucas Silva` (id **608**) y `Test - Jana Test` (id **621**), ambas con el celular de Lucas, y **ninguna tiene
citas** entre el 2026-09-05 y el 2026-09-29. Hay que **crear una cita** para una de ellas con:
- fecha = el `fecha_target` que se va a mandar;
- **motivo de atención exactamente `Consulta Ortodoncia`** (el mismo texto que Dentalink pone en las 5 consultas
  reales futuras; si la Dra. confirma que el puntito amarillo es otro motivo, usar ese);
- estado que no sea Anulado (1), Cambio de fecha (14) ni Confirmado por WhatsApp (18): al crearla queda 7 "No
  confirmado" y pasa el filtro `Solo citas activas`.

**Payload exacto** (`id_paciente_filter` con ENTEROS: `Solo citas activas` usa `includes` sobre `id_paciente` int):
```
POST https://n8n.raquelrodriguez.com.ar/webhook/trigger-recordatorios-manual
Content-Type: application/json

{"fecha_target": "YYYY-MM-DD", "id_paciente_filter": [608]}
```
- `fecha_target` ≥ hoy + 2 días → `tipo_recordatorio: '72h'` → bloque de la Dra. (§3.1).
- `fecha_target` = mañana → `'24h'` → frase corta (§3.2).
- Responde al toque (`responseMode: onReceived`); la ejecución se lee con
  `GET /api/v1/executions?workflowId=7RqTApkvVavRmq3R&limit=1` y `GET /api/v1/executions/<id>?includeData=true`:
  mirar la salida de `Preparar mensaje` (`es_consulta: true`, `motivo_atencion: 'Consulta Ortodoncia'`,
  `precio_origen: 'fallback'` — el camino manual no pasa por el Gate, §4) y la fila de `Insert recordatorios_enviados`.
- **NO usar el botón "adelantar" del panel** para esta prueba: manda solo `fecha_target` → a TODOS los pacientes de
  esa fecha.
- El celular de las fichas es el de Lucas → el mensaje le llega sin `TEST_MODE`. Si igual se usa
  `apply_toggle_recordatorios_test_mode.py --on`, volver a `--off` después.
- **Limpieza (regla dura 9), en el mismo turno**: `python scripts/limpiar_numero_demo.py --phone 5491161461034 --apply`
  (memoria + logs + label), borrar las filas de `recordatorios_enviados` de la cita de prueba (si el bot marcó
  `confirmado_at`, `¿Ya se recordó?` saltearía un re-disparo) y anular la cita en Dentalink. Dentalink devolvió 429
  tras ~40 GET seguidos: espaciar.

### 6.4 El primer envío REAL con el template nuevo sale por el CRON, no por la prueba manual

La prueba de §6.3 **no ejercita** el camino `Gate - Leer config` → `knowledge_base` (`precio_origen: 'fallback'` por
diseño, §4). El primer recordatorio real con el bloque de la Dra. y el precio leído de la KB lo manda el cron a un
**paciente real**: si el `--apply` se hace el 8/9, el miércoles 9/9 a las 08:00 ART `Fecha Mañana` apunta al **viernes
11/9** (+2 días hábiles) y la cita **8899** (`Consulta Ortodoncia `, 09:50) recibe el bloque nuevo. Las otras consultas
futuras conocidas: 8917 (15/9 11:20), 8762 / 8818 / 8866 (16/9). Checklist para esa mañana:

1. **Antes de las 08:00 ART**: `python scripts/apply_recordatorio_consultas.py` (dry-run → "ya aplicado", verificación
   del vivo en verde) y tener a mano `--rollback workflows/history/Recordatorio_PRE_consultas_<ts>.json`.
2. **Después de la ejecución** (`GET /api/v1/executions?workflowId=7RqTApkvVavRmq3R&limit=1` →
   `GET /api/v1/executions/<id>?includeData=true`):
   - salida de `Gate - Leer config`: `suspender: false` y `precio_contenido` con el texto de la KB id 21;
   - salida de `Preparar mensaje` del ítem de la cita 8899: `es_consulta: true`, `motivo_atencion: 'Consulta Ortodoncia'`,
     `precio_origen: 'kb'`, `precio_consulta: '$50.000'`, `message` que empieza por "✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨" y
     contiene "abonar el valor de la consulta ($50.000)";
   - los demás ítems (tratamientos): `es_consulta: false` y el genérico de siempre;
   - `Insert recordatorios_enviados`: una fila por envío con `motivo_atencion` y `es_consulta` cargados
     (`SELECT id_cita_dentalink, tipo, motivo_atencion, es_consulta FROM recordatorios_enviados WHERE enviado_at::date = current_date`).
3. **Si algo no cuadra**: `--rollback <PRE>` (deja el workflow como antes; las columnas quedan, inocuas) y avisar a la
   Dra. qué pacientes recibieron el bloque nuevo (`... WHERE es_consulta`), porque ya salió por WhatsApp.

---

## 7. Cómo revertir

```
python scripts/apply_recordatorio_consultas.py --rollback workflows/history/Recordatorio_PRE_consultas_<ts>.json
```
Solo acepta un PRE de verdad: nombre con `_PRE_` **y** `Preparar mensaje` igual al snapshot vivo
(`recordatorios/preparar_mensaje.vivo_2026-09-08.js`); un `Recordatorio_POST_*.json` o un `PRE_rollback` (traen el
jsCode nuevo) se rechazan porque "revertir" desde ahí re-aplicaría el cambio. Guarda un `PRE_rollback` del vivo antes de
pisar, hace el PUT del backup (settings filtradas, webhookId y cron verificados) y un `POST_rollback`, e imprime si
`Preparar mensaje`, el Gate y el Insert quedaron como el vivo. Las columnas `motivo_atencion`/`es_consulta` quedan en la
tabla: son nullable y nadie las exige, inocuas.

---

## 8. Riesgos y decisiones abiertas (para Lucas / la Dra.)

1. **Puntito amarillo = `Consulta Ortodoncia`?** (§2). Confirmar antes del `--apply`. Con la regla anclada, un motivo de
   primera visita que no empiece con "consulta" recibiría el genérico de hoy (sin daño) hasta que se ajuste la línea.
2. **El bot confirma sin pago** (R7): el template dice "si ya está abonado responda confirmo", pero el v6 (Sub-Agent
   Confirmar, PASOS 1-3) marca confirmado en Dentalink cualquier "confirmo" sin verificar el pago; solo el comprobante
   (PASO 0) escala a la secretaria. La regla "confirmación sí o sí con el pago" queda **solo en el texto**. ¿Debe el bot
   dejar de confirmar consultas sin comprobante? Fuera de este cambio.
3. **Precio en el camino manual = fallback** (§4, R4): si Raquel cambia el precio en el panel, los envíos manuales
   siguen diciendo `$50.000`.
4. **24h de consulta solo por manual** (§3.2): la frase corta la tiene que validar la Dra.; hoy no la recibe nadie.
5. **Emparejamiento por `$itemIndex`** (R2, preexistente): si `¿Ya se recordó?` saltea un ítem, los siguientes toman la
   cita de OTRO paciente (hora/fecha/es_consulta cruzados). En 14 días la rama "ya recordado" no se disparó nunca
   (0/10 ejecuciones). Arreglo posible: `$('Solo citas activas').item.json` (pairedItem se propaga, verificado) con
   fallback al índice — PUT aparte con su propia prueba.
6. **Hora real del cron**: 08:00 ART lunes a viernes (no 9:00): `0 13 * * 1-5` sin timezone en una instancia UTC+2.
   Al cambio horario europeo (2026-10-25) pasa a 09:00 ART salvo que el panel normalice la timezone. El apply no toca
   settings ni trigger.
7. **Residuos previos**: 3 filas del 5/8 en `recordatorios_enviados` (citas 8633 ×2 y 8634, pacientes reales) con el
   teléfono de Lucas por `TEST_MODE`. No se tocan en este cambio.
8. **Primer cron después del `--apply` = primer paciente real con el bloque nuevo** (§6.4): la prueba manual no pasa por
   el Gate, así que el camino KB → precio se ve por primera vez en producción. Revisar esa ejecución esa mañana.
9. **`motivo_atencion` vacío se guarda como `''`, no como NULL** (cuando la cita no trae el campo; Dentalink manda
   `No registra motivo`, no null, así que en la práctica no pasa). Se dejó `''` a propósito: garantiza que el Insert
   (postgres v2.6, corre DESPUÉS del envío) nunca reciba un null sin haberlo probado punta a punta. Cosmético.
