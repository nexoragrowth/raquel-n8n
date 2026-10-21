# Accesos del sistema de Asiri — PLANTILLA (sin valores)

> Este archivo **sí** está en el repositorio porque no tiene ninguna clave: solo dice **qué** hay que tener y **dónde** vive cada cosa.
> El archivo real (`ACCESOS.md`, con los valores) se genera en una carpeta **fuera** del repositorio con `python scripts/generar_accesos_privados.py` y se guarda cifrado o en un gestor de contraseñas. **Nunca se sube a GitHub, ni se manda por WhatsApp o mail sin cifrar.**
> Para usarlo con una IA: se le pasa el contenido de `ACCESOS.md` y la guía `docs/DIAGNOSTICO_IA.md`.

## 1. n8n (el motor de Asiri)
- URL: https://n8n.raquelrodriguez.com.ar
- `N8N_API_KEY` — clave de la API (Settings → n8n API). Con esto una IA lee, prueba y modifica workflows.
- `N8N_BASE_URL` — la URL de arriba.
- Credenciales guardadas dentro de n8n (por nombre, no se copian): *Redis account*, *Postgres Supabase Nexora v3*, *OpenAi account*, *Header Auth account 3* (Dentalink), *Supabase account v3*, *SMTP account*.

## 2. Supabase v3 (base de datos del bot)
- `SUPABASE_V3_URL` (o `V3_SUPABASE_URL`) — dirección del proyecto.
- `SUPABASE_V3_SERVICE_ROLE_KEY` (o `V3_SUPABASE_SERVICE_KEY`) — clave de servicio: lee y escribe todo. **La más delicada.**
- `SUPABASE_V3_DB_HOST`, `SUPABASE_V3_DB_PORT`, `SUPABASE_V3_DB_NAME`, `SUPABASE_V3_DB_USER`, `SUPABASE_V3_DB_PASSWORD` — acceso directo a Postgres (para los scripts de migración).

## 3. Evolution GO (conexión con WhatsApp)
- URL: https://evo.raquelrodriguez.com.ar
- `EVOLUTION_INSTANCE` — nombre de la instancia (hoy `raquel`).
- `EVOLUTION_INSTANCE_TOKEN` — token de la instancia (enviar mensajes, pedir fotos).
- `EVOLUTION_GLOBAL_API_KEY` — clave de administración (lista instancias y sus tokens).

## 4. Dentalink (agenda y fichas)
- `DENTALINK_BASE_URL` — https://api.dentalink.healthatom.com/api/v1
- `DENTALINK_TOKEN` — token de la API. Límite: 60 pedidos por minuto.

## 5. OpenAI
- `OPENAI_API_KEY` — usada por n8n y por el panel. Se puede ver el gasto en el panel de OpenAI.

## 6. Panel (panel.raquelrodriguez.com.ar)
- `PANEL_SESSION_SECRET`, `PANEL_USERS` (usuarios con contraseña cifrada), `PANEL_ADMINS`.
- `N8N_PANEL_WEBHOOK_BASE`, `N8N_PANEL_WEBHOOK_SECRET` — para que el panel mande mensajes y apague/prenda el bot.
- `ATENCION_BANDEJA`, `SEGUIMIENTOS` — interruptores de pantallas (1 = activa).
- Las contraseñas de los usuarios del panel **no se pueden leer** (están cifradas): para cambiarlas hay que generar una nueva (ver `deploy/README.md` del panel).

## 7. Servidor (VPS)
- Dirección: `VPS_HOST` (hoy 187.127.0.110), usuario `root`, clave SSH privada (`~/.ssh/raquel_vps`).
- Contenedores: `nexora-panel` (panel), `redis-rwlw-redis-1` (Redis), `evolution-go-postgres`, `n8n-traefik-1`.
- Carpetas: `/opt/nexora-panel` (panel), `/docker/evolution-go` (Evolution).

## 8. GitHub
- Repositorios: `nexoragrowth/raquel-n8n` (bot y documentación) y `LucasEzequielSilva/nexora-whatsapp-agent` (panel).
- Para trabajar con ellos hace falta una cuenta con acceso.

## 9. Datos de operación (no son secretos pero hay que tenerlos a mano)
- Grupo de derivaciones de WhatsApp ("WhatsApp Clínica Raquel"): ID `120363407321448469@g.us`.
- Teléfonos de administradores del bot (pueden escribir `/bot off`, `/bot on`, `/bot status`): se cargan en n8n (nodo *Kill-switch Check*) — ver `.claude/CLAUDE.md`.
- Persona de soporte: Lucas (Nexora). Soporte pleno hasta febrero de 2027.

## Qué hacer si una clave se filtra
1. Rotarla en el sistema que la emite (Supabase, n8n, Evolution, Dentalink, OpenAI).
2. Actualizarla **en la misma ventana** en n8n (credenciales) y en el `.env.production` del panel (`/opt/nexora-panel`), y redesplegar el panel (`bash deploy/redeploy.sh`).
3. Verificar con `python scripts/status.py` y un mensaje de prueba.
Rotar una clave sin actualizar los otros lugares **tumba al bot o al panel**.
