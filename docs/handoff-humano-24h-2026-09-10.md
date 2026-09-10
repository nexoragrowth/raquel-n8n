# Handoff humano→bot: modelo Intercom/Podium (1h → 24h) + botón masivo — 2026-09-10

**Estado**: n8n listo en `--dry-run` (verde, ver §4), **falta el OK de Lucas para `--apply`** — hay un riesgo
real detectado (§3) que no estaba en el pedido original y conviene confirmarlo antes de tocar el vivo.
Panel (botón masivo "Devolver todos al bot"): **implementado y con `tsc --noEmit` verde** sobre
`nexora-whatsapp-agent` (ver §8). **[2026-09-10, pasada de corrección]** una revisión encontró 3 MUST_FIX
sobre esta primera entrega (`HUMANO_MS` del panel seguía en 1h, el filtro `no_bot` no estaba implementado —
solo documentado como limitación —, y el aviso del botón masivo no era honesto sobre fallos parciales); los
tres quedaron resueltos en esta misma sesión — ver §9 para el detalle y el orden de despliegue correcto.

**⚠️ Antes de desplegar el panel: leer §9.1.** El fix de `HUMANO_MS` (1h → 24h) tiene que salir JUNTO con el
`--apply` de n8n, no antes — desplegarlo solo, con el workflow todavía en 1h, invierte el bug (el panel muestra
"modo humano" más tiempo del que dura de verdad el label en Chatwoot).

## 1. El modelo (por qué 1h → 24h)

Intercom/Podium (estándar de estas herramientas para clínicas) separan dos cosas que hoy este proyecto mezclaba
en un solo timer de 1 hora:

1. **Handoff humano**: cuando un humano (Dra./Irina/Lucas o el panel) toma una conversación, el bot queda
   pausado **sin reloj corto** — no vuelve solo a la hora porque "ya pasó un rato".
2. **Red de seguridad**: si la conversación lleva **24 h** sin actividad, el bot la retoma solo (para que un
   chat no quede huérfano para siempre si nadie lo cierra a mano).
3. **Botón masivo en el panel**: `Devolver todos al bot` — un solo click pasa TODAS las conversaciones open en
   modo humano a modo bot (solo panel web, no por WhatsApp). Existe además el botón individual por chat, que
   **no cambia**.

## 2. Qué se tocó en n8n (único cambio)

Workflow **`Auto Reactivar Bot (1h sin humano)`** (id `fosfga62zNaN0qrx`, 4 nodos, cron cada 15 min, **activo,
corre sobre conversaciones reales**). Nodo `Filtrar > 1 hora inactivas` (code), literal `ONE_HOUR`:

```diff
-const ONE_HOUR = 1 * 3600; // 2026-06-24: takeover 4h -> 1h (pedido Dra; gates R9 + label no_bot cubren anti-pisada)
+const ONE_HOUR = 24 * 3600; // 2026-09-10: takeover 1h -> 24h (pedido Lucas; estandar Intercom/Podium: handoff humano
+sin reloj corto + red de seguridad de 24h; gates R9 + label no_bot cubren anti-pisada)
```

Nada más cambia: mismos 4 nodos (`Cada 15 min` scheduleTrigger, `Chatwoot - Convs Humano` GET
`?labels[]=humano&status=open`, `Filtrar > 1 hora inactivas`, `Chatwoot - Label Bot` POST `{labels:['bot']}`),
mismo cron, mismas conexiones, mismo criterio de skip por label `no_bot` (vía de escape manual, existe en
Chatwoot pero hoy no la setea ningún workflow — ver §3.3).

Script: `scripts/apply_auto_reactivar_24h.py` — calca el molde de `scripts/apply_fix_turnos_doble_anuncio.py`
(1 campo, 1 workflow, GET fresco → diff → verify → dry-run por default). Aborta si el workflow no tiene
exactamente 4 nodos, si los nombres de nodo no son los esperados, o si el nodo cron no es `scheduleTrigger`
— para no pisar un estado que haya cambiado desde este doc.

```
python scripts/apply_auto_reactivar_24h.py             # dry-run (default): GET + diff, no toca n8n
python scripts/apply_auto_reactivar_24h.py --apply      # backup PRE -> PUT -> backup POST -> verificación
python scripts/apply_auto_reactivar_24h.py --rollback workflows/history/auto_reactivar_PRE_auto_reactivar_24h_<ts>.json
```

**Nota de nombre**: el workflow se sigue llamando "Auto Reactivar Bot (**1h** sin humano)" tras el `--apply` — el
script no lo renombra a propósito, para no mezclar dos cambios (contenido + nombre) en un mismo PUT. Renombrarlo
a "(24h sin humano)" es un cambio de un campo más, trivial de agregar en una segunda pasada si Lucas lo pide.

## 3. Riesgos a confirmar con Lucas antes de `--apply`

### 3.1 — El label `humano` no distingue "humano real atendiendo" de "el bot se auto-silenció" (RIESGO ALTO)
`docs/triaje-fase2-analisis/mapeo-read_redis_humano.md:247-266` documenta que la tool `escalar_a_secretaria`
aplica el label `humano` **de forma sincrónica sobre la misma conversación que el bot está por responder**, y el
propio bot lo detecta 1.4s después y suprime su respuesta. Medido: 6 de 8 escalaciones desde el 30/8 (execs
267708, 267736, 267938, 269215, 269595, 270010) terminaron así, incluyendo 3 urgencias reales. Hoy
`Auto Reactivar Bot` limpia ese auto-silencio en 60-75 min **aunque nadie humano haya mirado el chat**. Con 24h,
cualquier auto-escalación (no solo un humano tipeando) deja a ese paciente sin bot hasta 24h, salvo que alguien
lo note y lo destrabe a mano (botón individual, o el masivo nuevo). **Esto es un efecto colateral directo del
cambio pedido que el pedido original no menciona — confirmarlo explícitamente con Lucas antes del `--apply`.**

### 3.2 — Impacto medido en vivo hoy (2026-09-10, GET read-only a Chatwoot)
`GET /conversations?labels[]=humano&status=open` → **1 sola conversación** ahora mismo: id `272`, `last_activity_at`
hace ~9 minutos, teléfono terminado en `...1034` (número de prueba interno de Lucas, no un paciente real). **No
hay ninguna conversación vieja "colgada" esperando el corte de 1h.** Conclusión: el cambio de 1h→24h **no
destraba ni atasca nada que ya estuviera esperando en este instante** — es una foto de un segundo, no valida
comportamiento bajo tráfico real de pacientes. Recomendado: remonitorear `labels[]=humano&status=open` durante
las primeras 24-48h post-`--apply`.

### 3.3 — `no_bot` es una vía de escape que hoy no usa nadie
El label `no_bot` existe en la cuenta de Chatwoot (id 3, sin descripción) pero **0 conversaciones lo tienen
aplicado** y ningún workflow (`Auto Reactivar Bot`, `Human Takeover`, el satélite `Panel — acciones staff`) lo
setea — solo lo *lee* `Filtrar > 1 hora inactivas` como skip-condition. Si la idea es usarlo como "pin manual"
para que ni el colchón de 24h ni el botón masivo toquen cierta conversación, hoy solo se puede aplicar a mano
desde la UI de Chatwoot; nada en el panel lo ofrece como opción.

## 4. Verificación (dry-run, 2026-09-10)

```
$ python -m py_compile scripts/apply_auto_reactivar_24h.py
COMPILE_OK

$ python scripts/apply_auto_reactivar_24h.py
Auto Reactivar Bot: 4 nodos, activo=True, versionId=38cf23e0-0435-4076-91c7-64bee84dacec

── Filtrar > 1 hora inactivas · jsCode  (1030 -> 1118 chars)
  @@ -8,5 +8,5 @@
   const conversations = data.data?.payload || [];
   const now = Math.floor(Date.now() / 1000);
  -const ONE_HOUR = 1 * 3600; // 2026-06-24: takeover 4h -> 1h (pedido Dra; gates R9 + label no_bot cubren anti-pisada)
  +const ONE_HOUR = 24 * 3600; // 2026-09-10: takeover 1h -> 24h (pedido Lucas; estandar Intercom/Podium: ...)

nodos: 4 (sin cambios) · conexiones: sin cambios
verificación: {'one_hour_en_24h': True, 'comentario_fecha_motivo': True, 'cuatro_nodos': True,
  'mismos_nodos': True, 'cron_intacto': True, 'no_bot_sigue_siendo_skip': True,
  'get_url_intacta': True, 'post_label_bot_intacto': True}

[DRY-RUN] no se tocó n8n. Para aplicar: --apply
```

Todos los checks en verde. No se hizo ningún PUT/PATCH/POST — todo lo anterior son GET.

## 5. Cómo probar cada pieza (una vez que se apruebe el `--apply`)

1. **n8n**: correr `python scripts/apply_auto_reactivar_24h.py --apply` (muestra el diff antes de tocar nada,
   pide confirmación humana leyendo el diff — no automatizarlo). Verificar en la UI de n8n que el nodo quedó
   con `24 * 3600` y el comentario nuevo, y que el workflow sigue con 4 nodos y activo.
2. **Backlog real**: dejar pasar 24-48h monitoreando `GET /conversations?labels[]=humano&status=open` (mismo
   query que usa el workflow) para confirmar que el corte a 24h no deja acumular conversaciones reales sin que
   nadie las note.
3. **Botón individual** (`toggleBotAction` en el panel): confirmar que sigue funcionando igual — no lo toca
   este cambio.
4. **Botón masivo**: probar que `Devolver todos al bot` (a) lista correctamente las conversaciones open+humano,
   (b) excluye las que tengan `no_bot` — **solo si `CHATWOOT_BASE_URL`/`CHATWOOT_API_TOKEN` están seteadas en
   el panel, ver §8.3** —, (c) refleja el cambio en la lista sin recargar la página, (d) el contador previo a
   confirmar coincide con lo que trae el GET, (e) si algún toggle falla a mitad de camino, el aviso dice
   "N de M" y no esconde el resto (ver §9.3).

## 6. Cómo revertir

- **Solo el literal** (rollback rápido, sin volver a un backup completo): correr de nuevo el script con
  `ANCLA`/`NUEVO` invertidos, o restaurar a mano el comentario viejo `1 * 3600` en la UI de n8n.
- **Rollback completo**: `python scripts/apply_auto_reactivar_24h.py --rollback workflows/history/auto_reactivar_PRE_auto_reactivar_24h_<timestamp>.json`
  (el backup PRE se genera automáticamente en el mismo `--apply`, antes de tocar nada).
- El label `no_bot` sigue disponible como vía de escape manual por chat en cualquier momento, independiente de
  este cambio.

## 7. Qué falta (fuera del alcance de esta entrega)

- Confirmar con Lucas el riesgo de §3.1 antes de correr `--apply` en n8n.
- El webhook masivo nuevo en n8n (§8.4) — hoy documentado, no aplicado.

## 8. Panel: botón masivo "Devolver todos al bot" (implementado, 2026-09-10)

Repo `nexora-whatsapp-agent` (Next.js 16, deploy propio). `npx tsc --noEmit -p tsconfig.json` → verde.

### 8.1 — Qué se agregó

- `app/(app)/conversaciones/actions.ts`: `reactivarTodosAction(telefonos: string[])` → devuelve
  `{ok:true, cuantas}` o `Fail` (mismo shape que el resto de las actions del panel). Recibe la lista de
  teléfonos ya calculada del lado cliente (`items.filter(it => !it.botActive)` — el mismo campo que pinta el
  ícono de humano/bot en cada fila), así lo que se confirma en el diálogo es exactamente lo que se ejecuta.
- `components/conversaciones/conversation-list.tsx`: botón "Devolver todos al bot" con contador, debajo de los
  chips Todos/No leídos (oculto si `enModoHumano.length === 0`) → diálogo de confirmación (mismo patrón visual
  que `components/control/control-panel.tsx`, pero en color primario en vez de destructivo: volver al bot es la
  acción "segura") → `refetch()` tras aplicarse (igual que el resto de las acciones del panel) → aviso de
  resultado ("Se devolvieron N chats al bot." / error) auto-descartable a los 7s, igual que el resto de los avisos.
  El toggle individual (menú contextual, click derecho) queda intacto — no se tocó ese código.

### 8.2 — Decisión de arquitectura: reusar el webhook individual, no uno nuevo (por ahora)

El satélite `Panel — acciones staff` (`jzxb5zUKCaJcvCgp`) solo tiene `/panel-toggle-bot` para **un** teléfono
por request — no hay campo de lista en ningún lado de su `jsCode` (confirmado por GET read-only). Sumarle un
webhook masivo es un cambio a n8n, y esta entrega tiene explícitamente prohibido tocar n8n sin el mismo proceso
de diff+OK que cualquier otro cambio del workflow vivo. Por eso `reactivarTodosAction` **reusa** la action
existente `toggleBotAction` (que ya pega a `/panel-toggle-bot` y ya refleja `human_takeover` en Supabase v3),
en lotes de 5 en paralelo (`REACTIVAR_LOTE`), para no golpear Chatwoot/n8n con N requests simultáneos.

Es más lento que un webhook dedicado si algún día hay decenas de chats en modo humano a la vez — hoy, en
producción, es **1 sola conversación** (id 272, número de prueba de Lucas, ver §3.2) — así que el costo real de
esta decisión es nulo hoy. Si el volumen crece, conviene sumar el webhook de §8.4 para que sea una sola ida y
vuelta en vez de N/5.

### 8.3 — `no_bot`: implementado (corrección 2026-09-10), gateado por env vars

**Actualizado en la pasada de corrección** (ver §9.2) — esto describía originalmente una limitación conocida
sin resolver; ahora `reactivarTodosAction` SÍ excluye `no_bot`, sin tocar n8n ni hardcodear ningún secreto:

- Si `CHATWOOT_BASE_URL` + `CHATWOOT_API_TOKEN` (+ opcional `CHATWOOT_ACCOUNT_ID`, default `"1"`) están
  seteadas como env vars del panel (mismo patrón que `N8N_PANEL_WEBHOOK_BASE`/`SECRET`), `telefonosConNoBot`
  (`app/(app)/conversaciones/actions.ts`) hace un GET solo-lectura a Chatwoot con el MISMO query que
  "Auto Reactivar Bot" (`?labels[]=no_bot&status=open`), matchea `meta.sender.phone_number` contra los
  teléfonos pedidos (sufijo de 10 dígitos, igual criterio que "Validar secreto" del satélite `Panel — acciones
  staff`) y los saca de la lista antes de tocar nada.
- Si esas env vars NO están seteadas (**es el caso hoy**, confirmado: no existen en el panel): el chequeo se
  saltea y se aplica sin filtrar — el mismo comportamiento/limitación que ya estaba documentado acá. Sin
  impacto real porque `no_bot` sigue en 0 conversaciones en producción (§3.3).
- Si las env vars SÍ están pero la consulta a Chatwoot falla (caído, timeout, 401/403): la action aborta el
  botón masivo entero y devuelve un error claro — fail-closed, para no aplicar sin haber podido confirmar el
  pin manual.

**Para activar el filtro de verdad**: agregar `CHATWOOT_BASE_URL=https://chat.raquelrodriguez.com.ar` y
`CHATWOOT_API_TOKEN=<el mismo <CHATWOOT_TOKEN> que ya vive en los workflows de n8n>` a las env vars de
producción del panel (Vercel). Es la única pieza que falta para cerrar esto del todo sin n8n — no requiere
código nuevo. El webhook masivo en n8n de §8.4 sigue siendo la alternativa "todo en una sola ida y vuelta" si
el volumen de chats en modo humano crece (hoy: 1, ver §3.2).

### 8.4 — Webhook masivo para n8n (documentado, NO aplicado)

Nodo nuevo a agregar al satélite `Panel — acciones staff` (`jzxb5zUKCaJcvCgp`) el día que se apruebe tocar ese
workflow — mismo proceso de diff+OK que todo lo demás. Patrón: un webhook GET-por-label (como
`Auto Reactivar Bot`), no el patrón por-contacto de `Label Chatwoot` de este mismo satélite. Grafo sugerido:

```
Webhook "panel-toggle-bot-masivo" (POST, path panel-toggle-bot-masivo, responseMode responseNode)
  → Validar secreto masivo (code: valida X-Panel-Secret, igual que "Validar secreto")
  → GET Chatwoot Convs Humano (mismo request que "Chatwoot - Convs Humano" de Auto Reactivar Bot:
      https://chat.raquelrodriguez.com.ar/api/v1/accounts/1/conversations?labels[]=humano&status=open,
      header api_access_token=<CHATWOOT_TOKEN>)
  → Filtrar sin no_bot (code: igual criterio que "Filtrar > 1 hora inactivas" pero SIN el corte de
      horas — acá el filtro es solo "labels no incluye no_bot")
  → Loop/Split in batches sobre conversationId → POST label bot (mismo patrón que
      "Chatwoot - Label Bot": POST .../conversations/{id}/labels; decidir ahí si reemplaza el array
      entero como hace ese nodo hoy, o lo preserva como hace "Label Chatwoot" del propio satélite —
      inconsistencia ya señalada en la entrega anterior de este doc, conviene resolverla en esa misma
      pasada)
  → Responder 200 { ok: true, cuantas: <N> }
```

jsCode de referencia para "Filtrar sin no_bot" (mismo esqueleto que "Filtrar > 1 hora inactivas", sin el
`ONE_HOUR`):

```js
const conversations = $input.first().json.data?.payload || [];
const resultado = [];
for (const conv of conversations) {
  const labels = conv.labels || [];
  if (labels.includes("no_bot")) continue; // vía de escape manual: se saltea, igual que Auto Reactivar
  resultado.push({ json: { conversationId: conv.id } });
}
return resultado;
```

Con esto, `reactivarTodosAction` del panel pasaría de N llamadas a `/panel-toggle-bot` a una sola llamada a
`/panel-toggle-bot-masivo` (sin body, o con `{}`) — y de paso el panel ya no necesitaría mandar la lista de
teléfonos calculada del lado cliente, la fuente de verdad pasaría a ser Chatwoot vía n8n, cerrando la
limitación de §8.3.

### 8.5 — Cómo probar el botón (dato real de hoy, 2026-09-10)

1. Con **1 chat en modo humano** hoy en producción (id 272, teléfono de prueba de Lucas terminado en `...1034`
   — no un paciente real, ver §3.2): abrir el panel en `/conversaciones`, confirmar que aparece el botón
   "Devolver todos al bot" con el número **1** al lado, debajo de los chips Todos/No leídos.
2. Click → diálogo de confirmación dice "1 conversación en modo humano..." → Cancelar debe cerrarlo sin tocar
   nada (repetir el paso 1 y confirmar que el chat 272 sigue en modo humano).
3. Click → "Sí, devolver todos" → esperar el aviso "Aplicando…" y después "Se devolvieron 1 de 1 chat al bot."
   (formato "N de M" desde la corrección del 2026-09-10, ver §9.3) → confirmar en la lista que el chat 272 pasó
   a ícono de robot (bot activo) sin recargar la página (refetch automático) → confirmar en Chatwoot que la
   conversación 272 tiene el label `bot` (o al menos ya no tiene `humano`) y que `pacientes.human_takeover` en
   Supabase v3 quedó en `false` para ese teléfono.
4. Con 0 chats en modo humano: confirmar que el botón directamente no aparece.
5. **Toggle individual sigue andando igual**: desde el menú contextual (click derecho) de cualquier chat,
   "Pasar a modo humano" / "Reactivar el bot" tiene que seguir funcionando exactamente como antes — no se tocó
   ese código, solo se agregó una function nueva al lado.
6. Caso de error: si `N8N_PANEL_WEBHOOK_BASE`/`N8N_PANEL_WEBHOOK_SECRET` faltan o n8n no responde, el aviso
   tiene que mostrar el error claro en rojo (no colgarse) — mismo comportamiento que ya tiene el toggle
   individual, porque `reactivarTodosAction` reusa la misma `toggleBotAction`.

### 8.6 — Cómo revertir el panel

- Es código de UI + una server action nueva, sin estado propio ni migración de base — revertir es un
  `git revert` (o borrar el botón/la action) del commit correspondiente, sin backups ni pasos extra.
- No toca nada de n8n ni de Chatwoot que necesite rollback aparte: cada click del botón es, en los hechos, N
  toggles individuales de `/panel-toggle-bot` — el mismo camino que ya está en producción hoy.

## 9. Pasada de corrección (2026-09-10, rol: corrector, ambos repos)

Una revisión sobre la entrega de §2–§8 encontró 3 MUST_FIX y 7 NICE_TO_HAVE. Resumen de qué se corrigió, qué
se dejó documentado sin aplicar (por las restricciones duras del proyecto) y el orden exacto de despliegue.

### 9.1 — MUST_FIX #1: `HUMANO_MS` del panel seguía hardcodeado en 1h

`lib/chat-data.ts:42` y `lib/conversaciones-data.ts:29` (`nexora-whatsapp-agent`) calculaban "modo humano" con
una ventana de 1h propia, calcada del corte VIEJO de "Auto Reactivar Bot" — nadie la había tocado al preparar
el cambio a 24h. Con el `--apply` de n8n corrido pero el panel sin este fix, un chat con label `humano` puesto
hace más de ~60-75 min pero menos de 24h iba a mostrar el ícono de **bot** (botActive:true) mientras Chatwoot
todavía tenía el label `humano` puesto por hasta 24h más — y ese mismo campo (`!it.botActive` en
`conversation-list.tsx:232`) es lo que alimenta el contador y la lista de teléfonos del botón masivo, así que
el botón iba a subestimar silenciosamente el alcance real, salteándose justo los chats más tiempo silenciados
(los más urgentes: incluye el efecto de auto-escalación de escalar_a_secretaria, ver §3.1).

**Fix**: `HUMANO_MS` pasa de `60 * 60 * 1000` a `24 * 60 * 60 * 1000` en ambos archivos, con comentario
explicando el porqué y el orden de despliegue.

**⚠️ ORDEN DE DESPLIEGUE (crítico)**: este fix tiene que salir EN EL MISMO MOMENTO que el `--apply` de
`apply_auto_reactivar_24h.py`, nunca antes por separado. Si el panel sale con `HUMANO_MS=24h` mientras el
workflow de n8n sigue en 1h (p. ej. mientras se espera el OK de Lucas sobre el riesgo de §3.1), el efecto es el
inverso al bug original pero sigue siendo un estado incorrecto: el panel va a seguir mostrando "modo humano"
hasta 24h después de que Chatwoot ya le devolvió el label `bot` a la conversación (a los 60-75 min reales). Es
menos peligroso que el bug que corrige (no hace que el botón masivo omita nada — al revés, un chat que ya
volvió a bot en Chatwoot simplemente tarda más en mostrarse como tal en el panel) pero es información
incorrecta en la UI igual. **Orden correcto: (1) Lucas confirma el riesgo de §3.1 → (2) `--apply` en n8n → (3)
deploy del panel con este fix — los pasos (2) y (3) en la misma ventana de trabajo, no uno sin el otro.**

### 9.2 — MUST_FIX #2: el filtro `no_bot` no estaba implementado, solo documentado

El contrato pedía explícitamente excluir `no_bot` del botón masivo; la entrega original solo lo documentó como
limitación (§8.3, versión vieja) porque el panel no tiene credenciales propias de Chatwoot y agregar un
webhook nuevo en n8n está fuera de lo que esta sesión puede tocar (PROHIBIDO ABSOLUTO: PUT/PATCH/POST a n8n).

**Fix implementado sin tocar n8n ni hardcodear secretos**: `telefonosConNoBot()` nueva en
`app/(app)/conversaciones/actions.ts` — lee `CHATWOOT_BASE_URL`/`CHATWOOT_API_TOKEN`/`CHATWOOT_ACCOUNT_ID` de
env vars (mismo patrón que `N8N_PANEL_WEBHOOK_BASE`/`SECRET`, nunca hardcodeadas en el código), hace un GET
solo-lectura a Chatwoot con el mismo query que usa "Auto Reactivar Bot" y excluye los teléfonos que matchean.
Sin esas env vars configuradas (el caso hoy) el comportamiento es idéntico al de antes — la limitación sigue
existiendo hasta que alguien cargue esas dos variables en el panel, pero ahora es un interruptor de
configuración, no una reescritura de código. Con las env vars configuradas y Chatwoot caído/con error, la
action aborta el botón masivo entero en vez de aplicar sin haber podido verificar el pin manual (fail-closed).
Detalle completo en §8.3 (actualizada). El webhook masivo de n8n en §8.4 sigue sin aplicarse (requiere el
mismo proceso de diff+OK que cualquier cambio a un workflow vivo) y sigue siendo la vía "una sola ida y
vuelta" preferible si el volumen crece.

### 9.3 — MUST_FIX #3: el aviso no era honesto sobre fallos parciales

`reactivarTodosAction` devolvía `{ok:true, cuantas}` sin el total intentado; con 2 fallos de 5, el toast decía
"Se devolvieron 3 chats al bot." sin ningún indicio de los 2 que quedaron sin tocar.

**Fix**: `ReactivarTodosResult` ahora lleva `total` (intentados, después de excluir `no_bot`) y
`excluidosNoBot`. El toast en `conversation-list.tsx` arma el mensaje como "Se devolvieron N de M chats al
bot." siempre, agrega "X no se pudieron actualizar — reintentá desde el menú de cada chat." si `cuantas < total`,
y "X quedaron afuera por tener el pin manual (no_bot)." si `excluidosNoBot > 0`. El aviso además cambia de
color (verde → ámbar) cuando el resultado es parcial, para que no se lea como un éxito total a simple vista.

### 9.4 — NICE_TO_HAVE aplicados (chicos y seguros)

1. `scripts/apply_auto_reactivar_24h.py --rollback`: ahora llama `verify()` después del PUT y aborta con
   `sys.exit` si `ONE_HOUR` no volvió a 1h — paridad con `--apply`, que ya verificaba.
2. `docs/architecture.md` (líneas ~65 y ~213) y
   `docs/triaje-fase2-analisis/mapeo-read_redis_humano.md:311`: se agregó una nota de "pasando a 24h, ver este
   doc" en vez de reescribir el número — hoy el workflow SIGUE en 1h (no se corrió `--apply`), así que decir
   directamente "24h" ahí sería falso; la nota evita que una sesión futura re-derive la suposición vieja sin
   marcar que está por cambiar.
3. `components/conversaciones/conversation-list.tsx`: el botón masivo ahora también se deshabilita con
   `actionPending` (antes solo con `masivoPending`) — evita superponer dos "Aplicando…" lógicamente distintos
   con un doble click casi simultáneo entre el menú contextual y el botón masivo.
4. `REACTIVAR_LOTE` (`actions.ts`): se documentó en el propio comentario el techo esperado (N/5 rondas de
   latencia) y cuándo conviene el webhook masivo de §8.4.

### 9.5 — NICE_TO_HAVE NO aplicados (con motivo)

- **#4** (`lib/conversaciones-data.ts` — `botActive` es un proxy heurístico de v3, no una lectura directa del
  label de Chatwoot): es una decisión de diseño preexistente de antes de este pedido, no algo que esta entrega
  haya introducido. Corregirlo de raíz (leer Chatwoot en vivo para la lista completa, no solo para el filtro
  `no_bot` del botón masivo) es un cambio de arquitectura de la lista entera, no un "chico y seguro" — queda
  fuera de esta pasada.
- **#5** (`reactivarTodosAction` debería re-validar server-side que los teléfonos siguen en modo humano, en
  vez de confiar en el array que manda el cliente): mismo trust model que ya tiene `toggleBotAction`
  individual desde siempre, así que no es una superficie nueva de esta entrega. Implementarlo bien requiere
  duplicar del lado server la misma heurística pesada de `getConversacionesList` (~6 queries a v3) solo para
  esta action — no es un cambio chico. Con el fix de `HUMANO_MS` (§9.1) desplegado junto al `--apply` de n8n,
  el array que manda el cliente queda razonablemente fresco (viene del mismo estado que pinta el ícono por
  fila, refrescado por polling/SSE); se deja como mejora futura si hace falta más rigor.
