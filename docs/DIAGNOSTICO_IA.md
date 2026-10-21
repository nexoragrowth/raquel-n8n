# Diagnóstico y arreglo con una inteligencia artificial (guía para la clínica)

> **Para quién es esto.** Para la Dra. Raquel, la secretaria o cualquier persona de confianza que necesite que una IA (Claude, ChatGPT, Gemini, la que tengan) revise o arregle a Asiri **sin saber programar**.
> **Cómo se usa.** Abrís la IA con acceso a una terminal y a la carpeta del proyecto, le pasás el documento privado de accesos (ver §2) y le pegás esto: *"Leé `docs/DIAGNOSTICO_IA.md` y `.claude/CLAUDE.md`. Quiero que revises por qué pasa X. No cambies nada sin mostrarme antes qué vas a cambiar."*
> Si usan Claude Code, `.claude/CLAUDE.md` se carga solo.

---

## 1. Reglas que la IA tiene que respetar (no negociables)

Salen de un incidente real (9/5/2026: Asiri le dijo a una mamá que fuera a la clínica con la clínica cerrada). Están completas en `.claude/CLAUDE.md`; las que más importan:

1. **Nunca prender o cambiar el flujo viejo (v6) sin un backup previo** y sin mostrar antes el cambio a quien lo pidió.
2. **Cada cambio al workflow vivo** (PUT por la API de n8n) lleva backup antes (`workflows/history/`) y un script `scripts/apply_<qué>.py`. El PUT solo acepta `name, nodes, connections, settings, staticData`.
3. **No perder `webhookId: evo-webhook-v2`** en el v6: si se pierde, WhatsApp deja de llegar.
4. **Asiri no da diagnósticos, instrucciones médicas ni dice "venite ahora"**. Urgencias, fotos dentales y comprobantes se derivan al grupo de la clínica. Esto está en el prompt **y** en código (dos capas).
5. **No afirmar que algo funciona sin probarlo de punta a punta** (mensaje real → respuesta real → efecto real en Dentalink). Leer el código no alcanza.
6. **Cero residuos de prueba**: al terminar CUALQUIER prueba con un teléfono real se borran la memoria, los logs y la marca de humano (`scripts/limpiar_numero_demo.py`), y **se anulan en Dentalink las citas de prueba** en el mismo momento.
7. **Nunca pegar claves ni datos de pacientes en el repositorio, en los chats con la IA que no sean de la clínica, ni en los logs.**
8. **El workflow de Recordatorios (`7RqTApkvVavRmq3R`) funciona: no se toca.**

---

## 2. Cómo se accede a todo

Los accesos **no están en el repositorio**. Viven en un archivo privado que se llama `ACCESOS.md` (carpeta `Asiri-Accesos`, fuera de `raquel-n8n`). Lo genera `scripts/generar_accesos_privados.py` a partir de los `.env`; la plantilla con los nombres está en `docs/ACCESOS.template.md`.

Qué hay detrás de cada nombre:

| Sistema | Para qué sirve | Dónde se toca |
|---|---|---|
| **n8n** (`n8n.raquelrodriguez.com.ar`) | Corre a Asiri: workflows, ejecuciones, credenciales | UI web o API (`N8N_API_KEY`) |
| **Evolution GO** (`evo.raquelrodriguez.com.ar`) | Conecta el WhatsApp de la clínica | API con el token de la instancia `raquel` |
| **Supabase v3** | Base de datos del bot (mensajes, pacientes, escalaciones, fotos) | API/SQL con la clave de servicio |
| **Redis** (contenedor `redis-rwlw-redis-1` en el VPS) | Estado temporal: confirmaciones pendientes, buffer, interruptores | `docker exec` por SSH |
| **Dentalink** (`api.dentalink.healthatom.com`) | Agenda y fichas de pacientes (fuente de verdad de los turnos) | API (`DENTALINK_TOKEN`), 60 pedidos por minuto |
| **Panel** (`panel.raquelrodriguez.com.ar`) | Lo que usa la secretaria | Contenedor `nexora-panel` en `/opt/nexora-panel` |
| **VPS** | Hospeda n8n, Evolution, Redis y el panel | SSH con clave (`~/.ssh/raquel_vps`) |
| **GitHub** | Código y documentos | Repos `raquel-n8n` (bot) y `nexora-whatsapp-agent` (panel) |

---

## 3. El sistema en un minuto

```
Paciente ──WhatsApp──► Evolution GO ──webhook evolution-v2──► v6 (O155MqHgOSaNZ9ye)
                                                               │ entrada determinística: kill-switch, rate limit, mensajes de la clínica
                                                               │ (fromMe), buffer de 22 s, triaje de urgencias
                                                               ▼
                                                  ¿llave Redis v7:global activa?
                                              sí ──► v7 CEREBRO (NBHzj8ar2XuSvyIY)       no ──► Router y sub-agentes del v6
                                                     ├─ Orquestador (decide quién atiende)
                                                     ├─ Agentes: Turnos · Pagos · Información · Urgencias
                                                     └─ Herramientas (leen/escriben Dentalink con verificación por código)
Respuesta ◄── el TEXTO lo arma el código; un "chequeo de salida" revisa que no diga nada inventado antes de enviar
```

Principio de diseño: **el código decide y escribe en la agenda; la IA solo conversa y entiende.** Nada se agenda sin un "sí" del paciente a un resumen ("¿Procedo?").

Documentos de arquitectura, por orden de utilidad:
- `docs/v7-orquestador-subagentes-2026-10-08.md` — arquitectura vigente del v7 (el §8 manda sobre el resto).
- `.claude/stack.md` — trampas de Dentalink, formato de teléfonos (el 9 de Argentina), restricciones de la API de n8n.
- `memory/current-state.md` — bitácora: **lo último está al final**. Leé las últimas 100 líneas antes de empezar.
- `memory/decisions.md` — por qué se decidió cada cosa (no la reviertas sin leerla).
- `docs/auditoria-panel-2026-10-20.md` — el panel pantalla por pantalla.

IDs de los workflows (solo nombres e IDs, no son secretos):

| Workflow | ID |
|---|---|
| v6 principal (entrada) | `O155MqHgOSaNZ9ye` |
| v7 Cerebro | `NBHzj8ar2XuSvyIY` |
| Agentes Turnos / Pagos / Información / Urgencias | `S3DgPOyHg77M6SHQ` / `yjMpDQ3UH1tsZdDe` / `DhuxFBF6vrzDrkBK` / `yrCuq7hj04ox3sad` |
| Herramientas (ejecutar_propuesta, ver_turnos, elegir_ficha, proponer, buscar_horarios, confirmar_una, confirmar_turno, clinica, gestionar_turno) | están en `v7/ids.json` |
| Recordatorios (NO TOCAR) | `7RqTApkvVavRmq3R` |
| Health Check · Daily Summary · Auto Reactivar · Vigía | `Yjl6kyLnALhIfbFX` · `QsGBGkZdGu5gTdBf` · `fosfga62zNaN0qrx` · `1UbmAtUMtTBN9Bn3` |
| Logger de conversaciones · Retención | `xsXeHp7WLXnFQc3o` · `TKByjzVE8rGKTioT` |
| Panel (acciones del staff) · Aviso al grupo · Manejo de errores | `jzxb5zUKCaJcvCgp` · `S5U6tSipzlgFHCkf` · `yop6TIVoKiWUxfEn` |

---

## 4. Árbol de diagnóstico: "pasa X, ¿qué miro?"

Siempre empezar por **`python scripts/status.py`** (tablero de salud: workflows activos, últimas ejecuciones, errores).

| Síntoma | Primero mirar | Causas frecuentes | Cómo se arregla |
|---|---|---|---|
| **Asiri no contesta a nadie** | `status.py`; el workflow v6 `O155MqHgOSaNZ9ye` ¿activo?; Evolution ¿conectada? (banner del panel) | WhatsApp desvinculado (hay que escanear el QR desde el panel); webhook vacío en Evolution; el interruptor `/bot off` quedó prendido (`python scripts/v7_global.py --estado`) | Reconectar por QR; el Health Check ya repone el webhook solo (`scripts/apply_health_check_autoreparable.py`) |
| **No contesta a UN paciente** | ¿Está en modo humano? (panel → ese chat; el bot vuelve solo a la hora); ¿tipo de contacto silenciado (proveedor, personal)?; `n8n_chat_histories` de ese número | Una persona de la clínica le escribió desde el celular: el bot se calla a propósito | "Devolver al bot" desde el panel |
| **Contestó algo raro o equivocado** | La ejecución en n8n (Executions → buscar por el teléfono); en la salida del nodo "Salida" del Cerebro: `plan`, `agentes`, `motivo_chequeo`; memoria del chat | El orquestador entendió mal; un agente pidió algo que la herramienta rechazó; el chequeo de salida reemplazó el texto | Reproducir con `scripts/probar_v7.py` (modo sombra, no escribe); corregir prompt (`v7/prompt_*.md`) o código (`v7/*_core.js`); agregar un test (§6) |
| **Se repite la misma respuesta** | `repeticiones` en el contexto del Cerebro; ¿una confirmación pendiente venció? | Antes de 21/10 había casos; ahora a la 3.ª repetición deriva a la secretaria con aviso | Mirar el caso en `/atencion` del panel |
| **Confirmó/agendó de más o de menos** | Libro de escrituras: `escrituras:<tel>:<ejecución>` en Redis; la cita en Dentalink | Familia con varios turnos; recordatorio duplicado | `confirmar_turno` confirma todos los recordatorios abiertos; ver `v7/confirmar_core.js` |
| **Un recordatorio no salió / salió dos veces** | Workflow Recordatorios (NO se toca): ejecuciones del día; tabla `recordatorios_enviados`; `recordatorios_config` | Alguien disparó el webhook manual además del cron; día suspendido en el panel (Recordatorios) | Solo configuración desde el panel. Si hay que cambiar el flujo: pedirlo explícitamente, con backup |
| **El panel no carga datos o va lento** | `docker logs nexora-panel`; `https://panel…/login` responde 200 | Clave de Supabase rotada y el `.env.production` no se actualizó; Dentalink caído | `bash deploy/redeploy.sh` (desde el repo del panel) |
| **Las fotos de perfil no aparecen** | Tabla `paciente_fotos`; Evolution ¿conectada? | Contacto sin foto o con foto oculta (normal); token de instancia | Se reintentan solas a los 10 min / 7 días |
| **Llegó un mensaje pero no figura en el panel** | `n8n_chat_histories` (tiempo real) vs `conversaciones` (la copia el Logger cada 5 min); Realtime de Supabase | Logger parado | Ver ejecuciones del workflow `xsXeHp7WLXnFQc3o` |
| **Dentalink da error 429** | Límite de 60 pedidos/min | Algo hace demasiados pedidos | Revisar bucles; el panel y el bot comparten el límite |

Consultas útiles (Supabase, solo lectura):

```sql
-- últimos mensajes de un número (reemplazá el teléfono por el real, formato 549…)
select id, created_at, message->>'type' as tipo, left(message->>'content', 120) as texto,
       message->'additional_kwargs'->>'source' as origen
from n8n_chat_histories where session_id = '549XXXXXXXXXX' order by id desc limit 20;

-- avisos recientes al grupo de la clínica
select * from escalaciones_log order by created_at desc limit 20;

-- ¿hay recordatorios abiertos para un número?
select id_cita_dentalink, nombre_paciente, fecha_turno, hora_turno, confirmado_at, cancelado_at
from recordatorios_enviados where telefono = '549XXXXXXXXXX' order by enviado_at desc limit 10;
```

---

## 5. Cómo se hace un cambio sin romper nada

1. **Entender** (leer `memory/current-state.md` al final y `decisions.md`).
2. **Reproducir** el problema: `python scripts/probar_v7.py` (webhook de prueba, modo *sombra*: simula y no escribe en la agenda).
3. **Cambiar** el código fuente (`v7/*.js`, `v7/prompt_*.md`, `scripts/v7_*.py`). Nunca editar el workflow a mano en la UI de n8n: se pisa en el próximo deploy.
4. **Probar offline** (no tocan nada real):
   ```
   node tests/test_orquestador_core.mjs        node tests/test_agenda_core.mjs
   node tests/test_chequeo_salida.mjs          node tests/test_historial_clinica_core.mjs
   node tests/test_health_core.mjs             node tests/test_ficha_horarios_core.mjs
   python scripts/build_v7_workflows.py        (compila los workflows v7)
   python tests/test_v7_grafo.py               python tests/test_v7_grafo_herramientas.py
   python tests/test_v7_cerebro.py             python tests/test_v7_ma.py
   python scripts/check_triaje.py              (obligatorio antes de tocar el v6)
   ```
   Todos tienen que dar "TODO OK" / 0 fallas.
5. **Desplegar** el v7: `python scripts/crear_v7_en_n8n.py --aplicar` (verifica nodo por nodo y que el v6 siga intacto). Para el v6: backup + `scripts/apply_<qué>.py`.
6. **Probar en vivo** con el número de prueba (el de Lucas): un mensaje real, ver la respuesta y el efecto en Dentalink. Ejemplo hecho el 21/10: `scripts/prueba_real_confirmar_familia.py` (crea dos turnos, manda recordatorios, responde "Confirmo", verifica y limpia).
7. **Limpiar**: `python scripts/limpiar_numero_demo.py --phone <tel> --apply --borrar-logs` y anular las citas de prueba.
8. **Dejar registro**: una línea en `memory/current-state.md` (qué se cambió, por qué, cómo se probó) y, si hubo una decisión, en `memory/decisions.md`.

### Volver atrás

| Qué | Cómo |
|---|---|
| **Apagar el v7 y volver al flujo viejo** (rápido, sin tocar nada más) | `python scripts/v7_global.py --off` |
| Volver a un workflow anterior | `python scripts/restaurar_workflow.py workflows/history/<backup>.json` (simula) y con `--apply` (restaura) |
| **Frenar a Asiri por completo** (emergencia) | Desde WhatsApp, un administrador escribe `/bot off` al número de la clínica; `/bot on` lo vuelve a prender; `/bot status` muestra el estado |
| Un número puntual al flujo viejo | `python scripts/v7_global.py --excluir <tel>` |
| Panel con un problema | Volver al commit anterior y `bash deploy/redeploy.sh` |

---

## 6. Qué hacer cuando aparece un error nuevo (para que no vuelva)

1. Arreglarlo en el código fuente.
2. **Escribir un test que lo reproduzca** (en `tests/test_orquestador_core.mjs` o el que corresponda) con datos inventados (teléfonos tipo `5490000000xxx`).
3. Correr toda la suite (§5.4).
4. Anotarlo en `memory/current-state.md`.

Así cada cosa que "ya funcionaba" queda protegida. Es el mecanismo para llegar a "ya no hay que corregir tanto".

---

## 7. Qué NO hacer

- No agregar funciones fuera del alcance (agendar, recordar, confirmar/cancelar, información básica; todo lo demás se deriva).
- No volver a poner la lista de frases prohibidas por expresiones regulares sobre el texto de salida (se sacó el 7/10 por decisión de Lucas: frenaba mensajes inocentes).
- No decidir intenciones del paciente con expresiones regulares sobre su texto: eso lo hace el orquestador.
- No pegar claves en el chat con la IA si el servicio de la IA no es de la clínica: usar variables de entorno.
- No enviar mensajes masivos.
- No tocar el workflow de Recordatorios ni la contraseña de Postgres que usa.

---

## 8. Si todo esto no alcanza

Escribir a Lucas (Nexora). Hasta febrero de 2027 hay soporte; después, esta guía y la IA son el plan.
