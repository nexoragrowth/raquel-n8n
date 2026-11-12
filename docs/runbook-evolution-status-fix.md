# Runbook — Evolution GO "sordo" cada 50 min (fix `<status>`), 11/11/2026

## Qué pasa
WhatsApp está migrando cuentas (desde ~28/09/2026, de a poco y del lado del servidor) a mandar los **Estados** de los contactos
como stanza `<status>` de nivel superior. Evolution GO 0.7.2 (último release, imagen `latest`) trae whatsmeow `b572e5bc`
(30/06/2026), que **no tiene handler para `<status>`**: no manda el ack. A los ~50 min el servidor corta el stream con
`<stream:error><ack class="status" id=… type="media"/>`, Evolution reconecta solo y vuelve a pasar. Mientras el ack falta,
el servidor **retiene los mensajes entrantes**: la instancia dice `connected` pero no recibe nada (enviar sí funciona).

Firma en `GET /instance/logs/{id}`: `Unhandled event *events.StreamError … ack class="status"` + `Disconnected detected,
restarting instance` cada ~50 min + `OfflineSyncPreview` cuyo Total crece y nunca aparece `OfflineSyncCompleted`.

Fuentes: evolution-go issue #211, #185, PR #220 (fix mínimo), PR #190; whatsmeow commit a238105 ("client: handle <status> nodes");
Baileys #2858 (mismo bug en otra librería).

## Qué NO sirve (no perder tiempo)
- `ignoreStatus=true`, `/instance/connect`, `/instance/reconnect`, `/instance/forcereconnect`: no mandan ese ack; el ciclo sigue.
- **Logout + QR nuevo: NO.** Reportado que la sesión nueva sigue cayendo a los 50 min (es por cuenta, server-side), y deja el bot
  sin WhatsApp hasta escanear.
- Tag `0.7.2-beta` / `develop`: usa un fork de whatsmeow de abril sin el handler (y con riesgo de "Client outdated (405)").

## Fix: imagen de Evolution GO 0.7.2 + whatsmeow a238105 (PR #220: solo go.mod/go.sum)
Del pin actual al fix hay 11 commits de whatsmeow; **no hay migraciones SQL nuevas** (el cambio en `store/sqlstore/upgrades`
es un refactor): la base de la sesión no cambia → se puede volver a la imagen vieja sin re-escanear.

**Antes de empezar:** el v6 ya descarta mensajes con >15 min de atraso (`apply_v6_descartar_atrasados.py`, 11/11). Al aplicar el
fix el servidor suelta de golpe la cola retenida (283+ mensajes de días atrás): el bot no los va a contestar.

```bash
# 0) Ubicar el contenedor y cómo se levanta (anotar imagen actual para la vuelta atrás)
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -i evo
docker inspect <contenedor_evo> --format '{{.Config.Image}} {{index .Config.Labels "com.docker.compose.project.working_dir"}}'

# 1) Backup de la base de Evolution (sesión de WhatsApp + instancias). Nombre de la DB: ver DATABASE_URL / POSTGRES_* del compose.
docker exec <contenedor_postgres> pg_dump -U <usuario> -Fc <db_evolution> > /root/backup_evogo_$(date +%Y%m%d_%H%M).dump

# 2) Build de la imagen con el fix (PR #220 sobre 0.7.2)
cd /root && git clone https://github.com/evolution-foundation/evolution-go.git evogo-fix && cd evogo-fix
git fetch origin pull/220/head:fix-status && git checkout fix-status
grep whatsmeow go.mod        # tiene que decir v0.0.0-20260720135917-a2381054887e
docker build -t evolution-go:0.7.2-statusfix .

# 3) Cambiar SOLO la imagen del servicio de Evolution en el compose a evolution-go:0.7.2-statusfix y recrear ese servicio
cd <working_dir_del_compose> && docker compose up -d <servicio_evolution>

# 4) Verificar (ver abajo). 5) Vuelta atrás si algo sale mal: volver a poner la imagen anotada en el paso 0 y
docker compose up -d <servicio_evolution>
```

## Verificación (sin VPS, desde el repo)
- `GET /instance/logs/{id}`: deja de aparecer `ack class="status"`; aparece `OfflineSyncCompleted`; deja de haber
  `Disconnected detected` cada 50 min.
- n8n: entran ejecuciones del v6; las de la cola vieja terminan en `Webhook Validator` sin salida (log `[ATRASADO]`).
- Mandar un WhatsApp de prueba al número de la clínica desde el celular de Lucas: tiene que entrar en segundos.

## Agravante a vigilar: fuga de conexiones Postgres en 0.7.2
Cada reconexión crea un `sqlstore.Container` nuevo y no lo cierra (#165): con ~29 reconexiones/día puede agotar
`max_connections` y matar la instancia entera (envío incluido). El restart del paso 3 libera las acumuladas.
Chequeo: `docker exec <contenedor_postgres> psql -U <usuario> -c "select count(*), datname from pg_stat_activity group by 2;"`
Paliativo si vuelve a crecer: `ALTER DATABASE <db_evolution> SET idle_session_timeout = '1h';`
