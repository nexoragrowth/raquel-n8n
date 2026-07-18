# Estado actual — raquel-n8n

_Última actualización: 2026-07-18 ~14:30 ART — ✅ SISTEMA 100% OPERATIVO sobre Supabase v3_

## ✅ FASE 2 COMPLETADA (18/7 ~14:15): sistema completo, nada pendiente de la migración

- `sb_secret` v3 recibida, validada contra REST (bypasea RLS ✓) y anotada en `.env`.
- Credencial supabaseApi **"Supabase account v3" id `H1PRagttKC5kxSzs`** creada
  (truco schema: `allowedHttpRequestDomains:"all"` explícito). 9/9 nodos REST
  repunteados (5 v6 + 4 Logger). Backups `supav3_20260718_141034`.
- **Logger ACTIVO** (5 min): sincronizó 8 filas a `conversaciones` + upsert `pacientes` ✓.
- **KB E2E PASS con forense**: "frenillo corto de mi hijo" → `buscar_conocimiento`
  invocado real (exec 232804 muestra la entrada "menores | Atención a menores" del
  vector store) → respuesta correcta.
- **RLS ON en las 6 tablas** (Lucas pasó la publishable key por chat → blindado; el bot
  entra por PG como owner y la sb_secret es service_role: ninguno afectado).
- **Simplificación pedida por Lucas**: v3 quedó en **6 tablas** (borradas documents/
  peticiones/servicios/urgencias_log, vacías y sin escritores — ver decisions 18/7).
- Credenciales huérfanas BORRADAS de n8n (v1 `xwvjww5Odcxiy1K9`, v2 `EWhpNhb6tkGg1OTp`,
  supabaseApi v2 `Thn3jgEbbxPFD7d9`) con guard previo de cero referencias.
- Tests E2E acumulados hoy: precio $50k ✓ · contexto/alias ✓ · memoria forense
  (Build Router Context + loadMemoryVariables leyendo n8n_chat_histories) ✓ · KB ✓.

**Credenciales v3 vigentes en n8n**: Postgres `TpYhZX4UT61xAKSV` · supabaseApi
`H1PRagttKC5kxSzs`. Todo lo demás en `.env`.

## 🖥️ Dashboard (arrancado 18/7 tarde)

Lucas dio el GO al panel. Mapeo completo hecho (4 agentes) → **plan en
`docs/plan-dashboard-2026-07-18.md`** (leerlo antes de tocar el panel). Highlights:
el repo `Desktop/proyectos/nexora-whatsapp-agent` ya tiene modo espejo diseñado para
Raquel + preview vivo en `nexora-whatsapp-agent.vercel.app` (Vercel de Valentino);
decisión recomendada = dual-Supabase SIN espejo (auth propio + lectura directa v3);
fases F1(solo-lectura)→F2(interacción+webhooks n8n)→F3(KB editable con re-embed)→
F4(weekly learning).

**F1 CONSTRUIDA (18/7 tarde, workflow 4 agentes)** en la rama **`panel-v3-f1`** del
panel — SIN COMMITEAR, esperando review + prueba en vivo. Diff: 8 archivos, +530/−597
(se fue el espejo). Piezas: `lib/supabase/v3.ts` + `lib/v3/database.types.ts` (base,
hecha a mano) · conversaciones agrupadas por telefono con polling 5s + resumen clínico
colapsable + toggle disabled ("F2") · dashboard con métricas v3 reales (mensajes/día
14d apilado, escalaciones 7d, tasa confirmación de turnos pasados, modo humano) ·
citas vía Dentalink EN VIVO (sin tabla) enriquecidas con recordatorios v3.
Typecheck PASS verificado. `actions.ts` viejo (toggle Chatwoot + WhatsApp Cloud)
ELIMINADO — F2 lo reemplaza con webhooks n8n.

**GIRO 18/7 ~15:45 — "nexora proyect" NO VA MÁS (Lucas)** → login del panel UNIFICADO
en el Supabase v3 (un solo proyecto para bot + panel):
- `.env.local` del panel apunta TODO a v3 (URL + publishable como anon + sb_secret).
- Signup con allowlist (`ALLOWED_SIGNUP_EMAILS`: nexora.srv@ y raquel.agenteia2026@)
  — registro cerrado para extraños (crítico: el panel ve TODOS los datos del bot).
- Junction creado: `raquel-n8n/panel` → `../nexora-whatsapp-agent` (gitignoreado).
- Dev server CORRIENDO en localhost:3000 (task btv0ovelc): /login 200 ✓ redirect ✓.
- ⚠️ El clasificador de permisos bloqueó ejecutar el DDL de auth (trigger sobre
  auth.users) → quedó en **`scripts/panel_auth_v3.sql`** para que LUCAS lo pegue en
  el SQL Editor de v3. Sin eso el signup falla (no hay organizations/profiles/trigger).
**FORK DEFINITIVO (18/7 ~16:00, orden de Lucas)**: el panel dejó de ser el producto
multi-tenant y pasó a ser EL PANEL DE RAQUEL: (a) landing eliminada, `/` redirige a
/login; (b) rebrandeado "Áurea / Odontología Estética" + "Asiri · Secretaria Virtual"
(cero "Nexora" visible; los tokens CSS --nexora-* quedan, son internos); (c) **git
NUEVO**: historia vieja borrada (respaldo completo en github.com/nexoragrowth/
nexora-whatsapp-agent hasta 31419d7), `git init -b main` + commit inicial `a828626`
"panel raquel v1" con TODO el F1 adentro — ya no existe la rama panel-v3-f1, main ES
el panel de Raquel, SIN remote todavía (Lucas dijo "haremos otra nueva"); (d) DB: ya
estaba 100% en v3. Typecheck PASS + smoke: / → login, marca Áurea/Asiri ✓.
**GIRO FINAL 18/7 ~16:45 — LOGIN SIMPLE**: por orden de Lucas el panel usa
**admin/admin** (env PANEL_USER/PANEL_PASS, `lib/simple-auth.ts`, cookie) — Supabase
Auth ELIMINADO del panel, `scripts/panel_auth_v3.sql` OBSOLETO (no correr). Borradas
las rutas del producto viejo (signup/callback/personalizacion/integraciones/app/api).
E2E completo PASS (rebotes + dashboard con datos reales). Ver decisions 18/7.
**También 18/7 tarde**: bug del Logger (cursor=0 re-insertando todo cada 5 min —
origen de los "requests fantasma" que alarmaron a Lucas) arreglado de raíz: cursor
derivado de la base + UNIQUE chat_history_id + 390 duplicados limpiados. Verificado
tick post-fix = 0 inserts. Workflow nuevo inventariado: Sub-WF "Buscar Horarios
Validado" `GuDQ9VmKWZvQnerV` (legítimo, lo llama Agendar).
**Bloqueado en Lucas**: solo el DENTALINK_TOKEN en `.env.local` del panel (línea
CHANGEME_LUCAS) para encender /citas. Entrar al panel: localhost:3000 → admin/admin.
Pendiente próximo: repo GitHub nuevo + push; F2 (webhooks n8n toggle/send).

**Próximos pasos (nada urgente)**:
1. Reportero v2 "aprendizaje semanal" (P1) — diseño pactado: leer escalaciones_log +
   conversaciones → clasificar escaló-bien/por-gilada → pedidos ACCIONABLES (qué sumar
   a KB/prompt/comportamiento) → grupo. Mostrar el primer reporte a Lucas antes.
2. Batería de tests: casos específicos que pida Lucas (harness tests/test_e2e_bateria.py).
3. Ticket soporte Supabase por histórico v2 (Lucas) + decisión VPS vs v3-free antes 15/8.
4. Lunes 20/7 08:00 ART: primera corrida real del Recordatorio contra v3 — vigilar.

## ✅ RESOLUCIÓN DEL INCIDENTE 15-18/7: migrado a Supabase v3, bot respondiendo

**v3 = EL VIGENTE**: proyecto `eoizfjsyejixjzwgzwkt`, cuenta NUEVA
`raquel.agenteia2026@gmail.com` (org free con cuota fresca), región **sa-east-1 São Paulo**
(pooler `aws-1-sa-east-1.pooler.supabase.com:5432`, user `postgres.eoizfjsyejixjzwgzwkt`).
Credenciales en `.env`. **Falta solo la `sb_secret`** (Lucas la debe: API Keys → sb_secret).

**Lo ejecutado el 18/7** (todo verificado):
1. Esquema completo: 10 tablas + `match_documents` (`scripts/rebuild_v3_schema.sql`).
2. Backfill: **13 recordatorios** del 16-17/7 insertados (7 turnos lun 20/7 + 6 mar 21/7).
3. KB: **36 entradas** con embeddings (35 del export + [36] cuota mensual $70k nueva;
   precios $40k→$50k corregidos en [21][22][31]). Self-match 1.0 ✓.
4. Rewire n8n: 19 nodos Postgres en 8 workflows → credencial **"Postgres Supabase Nexora
   v3" id `TpYhZX4UT61xAKSV`** + 8 URLs REST al ref v3. Backups tag `supav3_20260718_*`.
   Lección: el POST /credentials exige `sshTunnel:false` explícito SIN campos ssh, y el
   pooler Supabase necesita `allowUnauthorizedCerts:true` (cert self-signed; con
   ssl:"require" estricto los nodos mueren — 1ra credencial `OZZVT9wQ14wyJjKW` borrada).
5. E2E PASS x2: precio → "$50.000" ✓ · contexto+alias ("y como puedo pagar?") →
   alias `dra.raquel.aurea` ✓. Memoria escribe en v3 (session Lucas, ids 1+).
6. Cursor Logger reseteado a 0 (base nueva). Cleanup ACTIVO (1x/día 04:00Z).
   `.env` actualizado a v3. Batería de tests nueva: `tests/test_e2e_bateria.py`.

**PENDIENTE INMEDIATO (fase 2, ~2 min cuando Lucas pase la `sb_secret`)**:
1. Anotarla en `.env` como SUPABASE_SERVICE_ROLE_KEY / SUPABASE_V3_SERVICE_ROLE_KEY.
2. Crear credencial supabaseApi "Supabase account v3" + repuntear los 9 nodos REST
   (5 en v6: obtener_historial_paciente, buscar_conocimiento/vector store, 3 tools
   recordatorios; 4 en Logger): re-correr `apply_supabase_v3_rewire.py` con
   `UPDATE_SUPA_CRED_IN_UI=0`, `REWIRE_DRY_RUN=0`, `N8N_V3_PG_CRED_ID=TpYhZX4UT61xAKSV`
   y la key real (el pase repuntea solo los nodos que sigan en la cred vieja Thn3jgEbbxPFD7d9).
3. **Reactivar Logger** (`xsXeHp7WLXnFQc3o`, quedó a 5 min, cursor 0) — está APAGADO
   a propósito: sus writes REST con la key vieja fallarían y el cursor avanza igual
   (pérdida silenciosa). Nada se pierde mientras tanto: memoria v3 lo guarda todo.
4. Test KB vector: descomentar el caso "kb" en tests/test_e2e_bateria.py y correr.

**Hasta que llegue la key, NO funcionan** (todo lo demás sí): buscar_conocimiento (KB
vector del Sub-Agent General), las 3 tools de confirmar/cancelar recordatorios,
obtener_historial_paciente, y el Logger→conversaciones. ⚠️ Si un paciente de los turnos
del lun 20/21 contesta "confirmo" ANTES de la fase 2, escala a Iri (las tools no llegan).

## Proyecto v2 MUERTO (pausado) — `ujfyapjwrdhnvqdvsjwp`

Murió en crash-loop 15-17/7: compute nano agotado (Logger @30s + Cleanup full-scan +
v6 6-10 queries/msg) → Postgres corrupto (`SQLSTATE 53100 could not access status of
transaction 0` en el redo, loop eterno). Los ~8.6k req/hora del dashboard eran los
servicios INTERNOS de Supabase en retry — no nuestros workflows. Quedó PAUSADO con el
**histórico de 202k conversaciones adentro**: ticket a soporte pendiente (texto ya
entregado a Lucas 17/7). NO BORRARLO hasta resolver el ticket o renunciar al histórico.
La org vieja `nexoragrowth` tiene egress 182% con gracia hasta el **15/8**.

## Qué es esto (refresh)

Bot WhatsApp producción para Áurea Odontología (Dra. Raquel, Jujuy). n8n self-hosted
(`n8n.raquelrodriguez.com.ar`) + Evolution API + Dentalink + **Supabase v3** + Redis.
v6 = `O155MqHgOSaNZ9ye` (activo). Sub-WF Cancelar `5cAWJxiWJ50hxEq3`. La fila envenenada
que rompía el Sub-WF murió con la base v2 (v3 arranca limpia + message JSONB NOT NULL).

## Workflows (estado 18/7)

- **v6**: ACTIVO ✓ sobre v3 (memoria/contexto OK; tools REST esperan sb_secret).
- **Recordatorio 48HS** (`7RqTApkvVavRmq3R`): ACTIVO, recableado. Próxima corrida lun
  08:00 ART — primera escritura real en v3.
- **Logger** (`xsXeHp7WLXnFQc3o`): APAGADO hasta fase 2 (schedule 5 min, cursor 0).
- **Cleanup** (`En0A5lXd3Whb5yFy`): ACTIVO, 1x/día 04:00Z.
- **Cron Resumen Clinico** (`BO1cdE8xmqln4IeO`): DESACTIVADO por orden de Lucas 17/7
  (recableado igual por si se reactiva).
- Health Check / Auto Reactivar / Human Takeover / Helper Notify: activos, recableados.

## Mandato de optimización de Lucas (17-18/7) — "Supabase solo para lo esencial"

Uso permitido: (1) contexto conversacional últimos 10-30 msgs, (2) KB para respuestas,
(3) recordatorios/confirmaciones, (4) data para reportes semanales + dashboard. Nada de
crons que martillen ni requests de fondo. Estado: Logger 30s→5min, Cleanup 30min→1x/día,
Resumen Clinico OFF. Carga total ~300 execs-DB/día (era ~2.930). Pendiente de fondo:
v6 hace un guard DDL (DO/ALTER) POR MENSAJE en "Check Session Age" y "Get Paciente
Context" corre ANTES del filtro fromMe — optimizar con diff (backlog P1). Decisión
antes del 15/8: VPS Hostinger vs quedarse en v3 free (con la carga nueva puede alcanzar).
