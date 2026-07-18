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
**Decisión**: el fix estructural del Sub-WF (re-fetch de turnos de la ficha resuelta,
matching por scoring, turno_objetivo persistente) NO se aplica sin revisión conjunta.
**Razón**: es la pieza más delicada del bot (historial de incidentes: Mariela, Luis,
Julieta, ghost appointments); regla del proyecto: cambios grandes se revisan antes.
**Estado**: plan en 3 fases en `docs/sesion-2026-07-06-precio-lid-reprogramacion.md`.

## 2026-07-08 — Migración a Supabase v2 sin esperar el service_role key
**Decisión**: reutilizar la credencial supabaseApi 'Supabase account' existente (validada
con un test REST contra el proyecto nuevo) para las 3 tools de recordatorios, en vez de
esperar a que Lucas pase el service_role key nuevo. Los apikeys viejos embebidos en URL
se removieron (quedaban expuestos en cada export del workflow).
**Razón**: bot caído en horario pre-apertura; la credencial ya apuntaba al proyecto nuevo
(alguien la actualizó al recuperar datos) y el patrón predefinedCredentialType ya estaba
probado en obtener_historial_paciente.
**Alternativa descartada**: crear credencial httpHeaderAuth nueva (requería el key, bloqueante).

## 2026-07-08 — Secuencias post-restore: setval a max+1 SIEMPRE
**Decisión/lección**: tras cualquier restore de datos con IDs explícitos, resetear TODAS las
secuencias (setval max+1) y verificar defaults/identity de los id ANTES de recablear.
**Razón**: los INSERTs del bot habrían fallado con duplicate key aunque el recableado
estuviera perfecto. Bug silencioso clásico.

## 2026-07-17 — Apagar "Cron - Resumen Clinico Pacientes" (BO1cdE8xmqln4IeO)
**Decisión**: desactivado (no borrado) el cron diario que resume el historial de cada
paciente con LLM y escribe `pacientes.resumen_clinico` (lo que lee "Get Paciente Context"
del v6). Snapshot previo en `workflows/current/cron_resumen_clinico_BO1cdE8xmqln4IeO.json`.
**Razón**: orden explícita de Lucas durante el incidente Supabase ("elimina ese cron; solo
necesitamos contexto de 10-30 mensajes atrás"). El bot sigue funcionando: el SELECT hace
COALESCE a '' si el resumen no existe/queda viejo.
**Aclaración importante**: este cron NO era el martillo — corría 1x/día. Se apaga por
decisión de simplificación, no por carga.
**Alternativa descartada**: borrarlo — innecesario, la desactivación es reversible.
**Revisable**: sí — si la Dra./Lucas extrañan el resumen del paciente en el contexto del
bot, reactivar con 1 click (POST /workflows/BO1cdE8xmqln4IeO/activate).

## 2026-07-18 — Migración completa a Supabase v3 (cuenta nueva) en vez de pelear el free tier
**Decisión**: ante el crash-loop irrecuperable del v2 y el cupo free agotado en la org
vieja, se creó cuenta nueva (`raquel.agenteia2026@gmail.com`) + proyecto v3
`eoizfjsyejixjzwgzwkt` en **sa-east-1** y se reconstruyó todo (esquema, KB 36 entradas,
backfill 13 recordatorios, rewire 19 nodos + 8 URLs). Autorización total de Lucas
("hacelo todo rapido y sin preguntar"). E2E PASS. Credencial PG v3: `TpYhZX4UT61xAKSV`.
**Lecciones API n8n credentials**: el schema exige `sshTunnel:false` EXPLÍCITO y sin
campos ssh presentes (if vacuoso de JSON Schema); el pooler Supabase presenta cert
self-signed → `allowUnauthorizedCerts:true` y SIN `ssl` (regla allOf). La credencial
estricta (`OZZVT9wQ14wyJjKW`) fallaba con "self-signed certificate" y fue borrada.
**Alternativas descartadas**: (a) revivir v2 — imposible sin soporte (pg_xact dañado);
(b) tablas del bot en el proyecto del dashboard — Lucas prefirió cuenta limpia;
(c) VPS ya — más lento hoy (requiere SSH + PostgREST); sigue como candidato pre-15/8.
**Revisable**: v3 puede ser puente o destino según el consumo real del mes.

## 2026-07-18 — Logger APAGADO hasta tener la sb_secret v3
**Decisión**: no reactivar el Logger aunque quedó recableado y a 5 min.
**Razón**: sus 2 writes van por REST con la credencial supabaseApi VIEJA (v2) → 401,
y su cursor avanza aunque el insert falle (continueOnFail) = pérdida silenciosa de
conversaciones. Con el Logger apagado no se pierde nada (la memoria v3 retiene todo y
el cursor quedó en 0 → al reactivar sincroniza desde el principio).
**Revisable**: reactivar en fase 2 (sb_secret) junto al repunteo de los 9 nodos REST.

## 2026-07-18 — Simplificación: v3 queda con 6 tablas (borradas 4 vacías)
**Decisión**: DROP de `documents`, `peticiones`, `servicios`, `urgencias_log` (todas con
0 filas y sin ningún workflow que las escriba). Reclamo de Lucas: "te pedí algo simple,
¿por qué tantas tablas?". Quedan 6, cada una con escritor y lector ACTIVOS hoy:
n8n_chat_histories (memoria/contexto), knowledge_base (KB), recordatorios_enviados
(confirmaciones), conversaciones (log legible→reportes/dashboard), pacientes (link
teléfono↔nombre para el log; la ficha real vive en Dentalink), escalaciones_log
(insumo del reportero semanal pactado con la Dra).
**Razón**: peticiones/servicios eran apuestas al dashboard (no existe el puente aún) y
urgencias_log esperaba el triaje (bloqueado por videos de la Dra); recrearlas cuando
esas features existan es un CREATE TABLE de 1 minuto (el DDL queda en
scripts/rebuild_v3_schema.sql como referencia).
**Revisable**: sí — recrear cada tabla cuando su feature llegue de verdad.

## 2026-07-18 — RLS habilitado en las 6 tablas v3 (publishable key expuesta)
**Decisión**: `ENABLE ROW LEVEL SECURITY` en las 6 tablas (sin policies = anon bloqueado).
**Razón**: Lucas pasó por chat la `sb_publishable` (key PÚBLICA) creyendo que era la
secreta; con RLS off esa key daba lectura/escritura total vía REST. Con RLS on: el bot
no se afecta (entra por Postgres directo como owner, bypasea RLS) y la futura
`sb_secret` (service_role) también bypasea. Verificado post-cambio con test E2E PASS.
**Pendiente**: sigue faltando la `sb_secret` para la fase 2 (9 nodos REST + Logger).

## 2026-07-18 — Fase 2 completada: supabaseApi v3 + Logger + higiene
**Decisión/hechos**: sb_secret validada → credencial "Supabase account v3"
(`H1PRagttKC5kxSzs`; el POST exige `allowedHttpRequestDomains:"all"` explícito por el
mismo patrón de if-vacuo del schema). 9/9 nodos REST repunteados. Logger reactivado
(5 min, cursor 0) y verificado: 8 filas a conversaciones + upsert pacientes. KB E2E
PASS con invocación real de buscar_conocimiento (exec 232804). Credenciales huérfanas
v1/v2 borradas de n8n con guard de cero referencias. Sistema 100% en v3.
**Nota clave de las keys nuevas de Supabase**: `sb_publishable_*` = PÚBLICA (frontend,
anon, bloqueada por RLS) · `sb_secret_*` = server-side, actúa como service_role
(bypasea RLS). n8n las acepta como drop-in del JWT viejo en supabaseApi.

## 2026-07-18 — Bug Logger cursor=0 (mío) + fix definitivo sin staticData
**Qué pasó**: al migrar a v3 reseteé el cursor del Logger a 0, pero el nodo que lo
avanza NUNCA persistió (roto desde la era v2: nodos duplicados con el mismo id en el
JSON + staticData flaky). Resultado: cada tick de 5 min re-insertaba TODA la memoria
en `conversaciones` (llegó a 26 copias de cada mensaje; era el grueso de los ~440
requests/hora que alarmaron a Lucas).
**Fix (backups logger_PRE/POST_cursorfix_20260718_162532)**: (1) columna real
`chat_history_id bigint` + UNIQUE en conversaciones; (2) el SELECT del Logger deriva
el cursor DE LA BASE: `WHERE id > (SELECT COALESCE(MAX(chat_history_id),0) FROM
conversaciones)` — chau staticData; (3) insert con on_conflict=chat_history_id +
resolution=ignore-duplicates (idempotente); (4) duplicados limpiados (368 + 22 de un
tick intermedio). Verificado: tick post-fix insertó 0, tabla 22/22 limpia.
**Nota**: en v2 el cursor también estuvo clavado (154 fijo) — las 202k conversaciones
del histórico probablemente tengan duplicación masiva; tenerlo en cuenta si soporte
recupera ese proyecto.

## 2026-07-18 — Panel: login simple admin/admin (chau Supabase Auth)
**Decisión de Lucas** ("no hace falta un login, admin admin y listo"). Implementado:
`lib/simple-auth.ts` (PANEL_USER/PANEL_PASS por env, default admin/admin, cookie
firmada por derivación), proxy.ts chequea cookie, getOrgContext estático (Áurea,
tz Jujuy, read_only). ELIMINADO: signup, callback, /personalizacion, /integraciones,
app/api/* legacy, componentes huérfanos. `scripts/panel_auth_v3.sql` QUEDA OBSOLETO
(no correrlo — el panel ya no usa organizations/profiles ni Supabase Auth).
E2E: sin cookie rebota ✓, admin/admin entra al dashboard con datos reales ✓, cookie
falsa rebota ✓. Al deployar público: setear PANEL_USER/PANEL_PASS fuertes.

## 2026-07-18 — Lucas borró el Supabase "nexora proyect" (xmcyidheaqgjhlgcihia)
**Hecho**: proyecto del dashboard standalone eliminado por Lucas. Impacto CERO: el
panel ya no lo usaba (auth simple + datos v3). Muere el preview viejo de Vercel.
**⚠️ Recordatorio vigente**: "raquel proyect" (v2 PAUSADO, ujfyapjwrdhnvqdvsjwp) NO
se borra — histórico 202k conversaciones pendiente del ticket de soporte.
