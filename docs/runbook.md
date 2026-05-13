# Runbook — operación día-a-día

Procedimientos operativos del bot. Pensado para usar cuando algo pasa en prod o se necesita intervenir.

---

## Kill-switch: apagar/encender el bot

**Cuándo:** el bot está respondiendo macanas. Iri o doctora quieren tomar el control inmediato.

**Cómo:** desde el WhatsApp personal de **Lucas, Iri o doctora**, mandar al número del consultorio:

```
/bot off
/bot on
/bot status
```

Requisitos:
- El mensaje viene con `fromMe=false` (escribís desde tu celular, no desde el consultorio).
- Tu phone tiene que estar en la whitelist:
  - Lucas: `5491161461034`
  - Irina: `5493885786946`
  - Dra. Raquel: `5493513976787`

El bot responde con confirmación al chat origen del comando. Si pasa 1h sin actividad humana en una conversación, el `Auto Reactivar` workflow vuelve a prender el bot automáticamente.

**Verificación manual** del estado:
```bash
# Via Redis CLI (si tenés acceso):
redis-cli GET bot:status

# Via n8n: workflow Health Check ejecuta cada N min y registra el estado.
```

---

## Pausar bot SOLO para una conversación (no global)

**Cuándo:** Iri o doctora quieren atender personalmente una conversación específica, sin apagar el bot para todos los pacientes.

**Cómo:** dos opciones:

### Opción A — Desde Chatwoot

1. Abrir la conversación en Chatwoot.
2. Aplicar el label `humano` a la conversación.
3. El workflow Human Takeover ya lo automatiza: cuando un agente escribe DESDE Chatwoot, el label se aplica solo.

### Opción B — Desde WhatsApp Web o Mobile del consultorio

Simplemente escribir en la conversación con el paciente. Evolution captura el `fromMe=true`. El v6:
1. Persiste el mensaje en memoria del LLM con tag `[ATENCION HUMANA]`
2. Llama Chatwoot Search Contact + Set Label `humano`
3. Próximo mensaje del paciente → flow detecta label → NoOp

**Para volver al modo bot:** marcar la conversación como `resolved` en Chatwoot. El `Auto Reactivar` workflow quita el label.

---

## Bot dejó de funcionar (no responde a nadie)

**Diagnóstico rápido (5 min):**

1. Verificar workflow v6 activo:
   ```bash
   curl -s -H "X-N8N-API-KEY: $N8N_API_KEY" \
     "https://n8n.raquelrodriguez.com.ar/api/v1/workflows/O155MqHgOSaNZ9ye" \
     | python -c "import json,sys; d=json.load(sys.stdin); print('active:', d['active'])"
   ```

2. Verificar Redis `bot:status`:
   ```bash
   redis-cli GET bot:status  # debería ser "on" o vacío
   ```

3. Verificar webhook path no se cambió:
   ```bash
   curl ... | python -c "import json,sys; d=json.load(sys.stdin); print([n['parameters'].get('path') for n in d['nodes'] if n.get('name')=='Webhook - Evolution API'])"
   # Debería decir: ['evolution-v2']
   ```

4. Verificar Evolution API responde:
   ```bash
   curl -X GET https://[evolution-host]/instance/connectionState/raquel \
     -H "apikey: [EVO_API_KEY]"
   ```

5. Verificar Dentalink up (Health Check workflow lo monitorea):
   ```bash
   redis-cli GET dentalink:status  # debería ser "up"
   ```

**Acciones según diagnóstico:**

| Síntoma | Causa | Acción |
|---|---|---|
| `active: false` | Workflow apagado | Reactivar via UI o API. Verificar quién lo apagó (logs) |
| `bot:status = off` | Kill-switch activo | Desde admin WA: `/bot on` |
| Path != `evolution-v2` | Quedó en modo test | `python scripts/test_prep_restore.py --restore <backup>` |
| Evolution disconnected | WhatsApp desconectó | Reconectar manualmente con QR |
| `dentalink:status = down` | API caída | Esperar + alertar a Dentalink. Mientras tanto, bot escala a Iri |

---

## Recordatorios

**Workflow**: `Recordatorio de Turno 48HS - Dra. Raquel` (`7RqTApkvVavRmq3R`).

**Cron**: `0 13 * * 1-5` = 8 AM Arg (server UTC), solo lunes-viernes.

**Lógica**:
1. Calcula `addBusinessDays(hoy, 2)` = fecha objetivo (2 días hábiles adelante, saltea sáb+dom).
2. Trae citas activas de Dentalink para esa fecha.
3. Para cada cita, manda WhatsApp humanizado al celular del paciente.
4. Guarda NOTA INTERNA en `n8n_chat_histories` con `additional_kwargs.source: reminder_note` + `id_paciente`.

**Salidas esperadas por día**:
- Lunes envía → miércoles
- Martes envía → jueves
- Miércoles envía → viernes
- Jueves envía → lunes (skipea fin de semana)
- Viernes envía → martes (skipea fin de semana)
- Sáb/dom → cron no corre

**Pacientes con turno sábado/domingo**: no se envía recordatorio (clínica cerrada).

**Validación visual del fix de duplicados**: el martes 19/5 debería haber UN solo recordatorio para pacientes con turno ese día (enviado el viernes 15/5 a las 8 AM).

---

## Escalación al grupo

**Grupo**: `WhatsApp Clínica Raquel`, JID `120363407321448469@g.us`. Miembros: Lucas + Dra. Raquel.

**Cuándo se dispara**: el LLM llama a la tool `escalar_a_secretaria` con un `query` que resume el motivo. Casos típicos:
- Urgencia médica (dolor, sangrado, aparato salido)
- Paciente insatisfecho / queja
- Consulta sobre obra social
- Paciente pide hablar con persona
- Caso fuera de las 4 funciones MVP

**Qué hace la tool** (ver `escalar_a_secretaria` toolCode en el workflow):
1. POST a Evolution API mandando WhatsApp a `secretaryPhone` (Iri por default, Lucas en modo test) con `[ESCALADO BOT] {query}`.
2. GET a Chatwoot Search Contact por phone del paciente.
3. GET a Chatwoot Get Conversations.
4. POST a Chatwoot Set Label `humano` en la conversation del paciente.
5. Devuelve al LLM: `"Escalado a la secretaria correctamente"`.

**Resultado**: Iri recibe el WhatsApp con el resumen. La conversation del paciente en Chatwoot queda con label `humano` → bot pausado para ese paciente.

---

## Tests sintéticos

**Cuándo**: antes de cualquier cutover, después de cambios significativos en prompts/lógica, antes de shadow.

### Setup

```bash
# 1) Prep: blindaje + activar v6 en modo shadow
export N8N_API_KEY="<jwt>"
python scripts/test_prep_restore.py --prep
# Output incluye el path del backup, GUARDARLO
```

### Correr

```bash
# 2) Run (10-15 min, paralelo 8 workers)
python C:/Users/Lucas/.claude/n8n_backups/test_100_pre_prod.py
# Logs en stdout. Resultados detallados en n8n_backups/test_100_results.json
```

### Reporte

El script imprime al final:
- Score X/100
- Por categoría con barra de %
- Lista de fails con razón

### Restore

```bash
# 3) IMPORTANTE: restore al estado pre-test
python scripts/test_prep_restore.py --restore <backup_path_del_paso_1>
```

El restore desactiva v6, desactiva helpers, vuelve webhook path a `evolution-v2`, vuelve `secretaryPhone` a Iri, re-enable nodos que estaban activos.

---

## Rollback de un cambio

Cada script de fix toma un backup automático antes de aplicar. Para revertir:

```bash
# Backup queda en workflows/history/v6_PRE_<FIX>_<ts>.json
# Ejemplo: revertir el round 2 al estado pre-Round 2 (snapshot post-Round 1)

python -c "
import json, os, urllib.request
KEY = os.environ['N8N_API_KEY']
wf = json.load(open('workflows/history/v6_PRE_R0_<ts>.json', encoding='utf-8'))
ALLOWED = {'saveExecutionProgress','saveManualExecutions','saveDataErrorExecution','saveDataSuccessExecution','executionTimeout','errorWorkflow','timezone','executionOrder','callerPolicy','callerIds'}
payload = {
    'name': wf['name'],
    'nodes': wf['nodes'],
    'connections': wf['connections'],
    'settings': {k:v for k,v in wf.get('settings',{}).items() if k in ALLOWED},
    'staticData': wf.get('staticData'),
}
req = urllib.request.Request(
    'https://n8n.raquelrodriguez.com.ar/api/v1/workflows/O155MqHgOSaNZ9ye',
    method='PUT',
    headers={'X-N8N-API-KEY': KEY, 'Content-Type':'application/json'},
    data=json.dumps(payload).encode(),
)
with urllib.request.urlopen(req) as r:
    print('rollback PUT:', r.status)
"
```

---

## Contactos / accesos clave

| Sistema | URL / detalle |
|---|---|
| n8n UI | https://n8n.raquelrodriguez.com.ar |
| Webhook v6 prod | https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2 |
| Webhook v6 test | https://n8n.raquelrodriguez.com.ar/webhook/evolution-v6-test |
| Chatwoot | https://chat.raquelrodriguez.com.ar |
| Evolution instance | `raquel` (VPS-only endpoint) |
| Dentalink API | https://api.dentalink.healthatom.com |

**Phones whitelist admin** (kill-switch):
- Lucas: `5491161461034`
- Irina: `5493885786946`
- Dra. Raquel: `5493513976787`

**Grupo escalación**: `120363407321448469@g.us` (WhatsApp Clínica Raquel)

**Credenciales reales**: ver vault local de Lucas (`projects/dra-raquel-n8n.md` sección "Acceso (NO PERDER)"). **NUNCA pegarlas en este repo.**
