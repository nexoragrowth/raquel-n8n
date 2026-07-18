# Proyecto: Agente WhatsApp Dra. Raquel Rodriguez (Áurea Odontología Estética)

> Este archivo se inyecta automaticamente en cada sesion de Claude Code abierta desde `D:\Dev\dra-raquel\`.
> Define el contexto LOCAL del proyecto. El `context.md` GLOBAL del vault (Lucas) se inyecta por separado via SessionStart hook.

---

## Que es este proyecto

Bot de WhatsApp para clinica de ortodoncia (San Salvador de Jujuy). Construido en n8n self-hosted + Evolution API (WhatsApp) + Dentalink (agenda medica) + Supabase (data layer) + Postgres (memoria LangChain) + Redis (buffer / kill-switch / rate limit).

Caso bandera de Nexora (consultorios/clinicas). Primera cuota cobrada. Doctora paga mensual.

## Que hace el bot (scope MVP cerrado)

**SI hace** (automatico):
1. **Agendar** turnos nuevos (busca disponibilidad Dentalink + reserva)
2. **Recordar** turnos 24h y 72h antes (workflow aparte, cron 9 AM Arg) — ✅ FUNCIONA
3. **Confirmar / Cancelar** turnos post-recordatorio
4. **Info canned**: precio consulta, horarios, direccion, alias bancario

**NO hace** (escala SIEMPRE):
- Urgencias / dolor / sangrado / aparato salido → derivar al grupo
- Foto dental / consulta medica → derivar
- Comprobantes de pago → recibe + deriva al grupo (NO valida monto)
- Cualquier otra cosa → silencio o derivar

**JAMAS hace** (banlist regex post-output):
- Decir "venite" / "los esperamos" / "ahora mismo a la clinica"
- Dar instrucciones operativas/medicas ("guarda", "trae", "toma X", "saca")
- Dar diagnostico u opinion ("no te preocupes", "es normal", "que macana")
- Dar la direccion fisica como confirmacion de cita

## Estado al 2026-05-11

- **v6 (`O155MqHgOSaNZ9ye`)**: DESACTIVADO post-incidente Mariela (2026-05-09). 5 capas determinisicas aplicadas + Banlist Validator (22 patrones regex). NO prender hasta completar refactor.
- **v4 (`jaO9zQb6l5HM07gg`)**: rollback backup, inactivo.
- **Recordatorios (`7RqTApkvVavRmq3R`)**: ✅ activo, funciona perfecto. NO TOCAR.
- **Health Check / Daily Summary / Auto Reactivar / Human Takeover**: activos, funcionan.

## Incidente clave a no olvidar (2026-05-09)

Una mama real (Mariela) recibio del v6 instruccion de ir a la clinica un sabado con clinica cerrada. Bot dijo: "guarda la pieza, traete el DNI, venite ahora mismo, Balcarce 37 2do piso, los esperamos". Mariela respondio "Bien, ahora salimos para la clinica". La doctora alcanzo a apagar el bot a tiempo.

Root cause triple:
1. Kill-switch usaba phone del destinatario en lugar del emisor → `/bot off` se ignoraba silencioso.
2. System prompt enseñaba "Te esperamos" en ejemplo (contradice R22 que lo prohibe) → bot copio literal.
3. Router no veia memoria → "esta incomoda, no come" se clasifico como consulta_general en vez de urgencia.

Auditorias completas en `<vault>/projects/audit-memoria-v6.md` y `audit-base-conocimiento-v6.md`.

## Reglas duras de este proyecto

1. **Nunca prender el v6 sin OK explicito de Lucas**. Hubo incidente real con paciente. Confianza de la doctora rota, se recupera con proceso, no con velocidad.
2. **Cero PUTs al workflow sin backup previo**. Ver `scripts/` para patrones.
3. **Preservar `webhookId: evo-webhook-v2` siempre** (leccion #1 vault: si lo perdes, Evolution apunta a UUID null y rompe todo).
4. **PUT al API solo acepta** `name, nodes, connections, settings, staticData`. Settings solo permite `saveExecutionProgress, saveManualExecutions, saveDataErrorExecution, saveDataSuccessExecution, executionTimeout, errorWorkflow, timezone, executionOrder, callerPolicy, callerIds`. Cualquier otra key → 400.
5. **Defensa en profundidad sobre prompt**: cada regla critica debe estar en al menos 2 capas (prompt + gate deterministico). El banlist regex es la ultima linea.
6. **MVP es agendar + recordar + escalar todo lo demas**. Cualquier intento de meter features extra (vision, RAG abierto, sub-agents creativos), parar.
7. **fromMe filter universal**: cualquier mensaje saliente del numero de la clinica que NO sea del bot → aplica label humano + silence flag Redis. No depender de Chatwoot solo.

## Accesos y endpoints

Ver `<vault>/projects/dra-raquel-n8n.md` seccion "Acceso (NO PERDER)" para credenciales, JWT, endpoints. **Nunca pegar valores reales en este repo.**

Datos clave para tener a mano (NO secretos):
- n8n UI: https://n8n.raquelrodriguez.com.ar
- Webhook v6: https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2
- Evolution instance: `raquel` (endpoint VPS-only)
- Chatwoot: https://chat.raquelrodriguez.com.ar
- Grupo de derivaciones (destino escalaciones): `120363407321448469@g.us` ("WhatsApp Clinica Raquel"). Miembros: Lucas + Dra. Raquel.
- Admin phones whitelisted para `/bot off|on|status`: Lucas `5491161461034`, Irina `5493885786946`, Dra. Raquel `5493513976787`.

## Proyecto hermano: el PANEL (dashboard)

`C:\Users\not\Desktop\proyectos\nexora-whatsapp-agent` — Next.js 16, panel del bot
(chat, citas, métricas, KB editable). Repo y deploy PROPIOS (GitHub nexoragrowth +
Vercel); NO moverlo adentro de este repo (decisión 18/7: producto multi-cliente).
Se trabaja desde sesiones de raquel-n8n igual — plan vigente y fases en
`docs/plan-dashboard-2026-07-18.md`; estado en `memory/current-state.md`.
Preview viejo vivo: nexora-whatsapp-agent.vercel.app (Vercel de Valentino, espejo).
Regla: los datos del bot los lee DIRECTO del Supabase v3 (dual-cliente, sin espejo).

## Fuentes externas a este repo (siempre cargar)

- **Vault context**: `C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/projects/dra-raquel-n8n.md` (notas persistentes con todas las lecciones aprendidas, IDs, accesos, evolucion del workflow).
- **Sessions log**: `C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/sessions/YYYY-MM-DD.md` (log diario que llena Claude. SE ESCRIBE AHI, no en este repo, para que el SessionStart hook lo inyecte en otras sesiones).
- **Handoff tecnico v6** (parcialmente desactualizado, ver disclaimer arriba): `C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/projects/handoff-dra-raquel-v6.md`
- **Auditoria memoria v6**: `C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/projects/audit-memoria-v6.md`
- **Auditoria base conocimiento v6**: `C:/Users/Lucas/Documents/.vault/life/02 - Areas/Claude/projects/audit-base-conocimiento-v6.md`

## Estructura del repo

```
D:\Dev\dra-raquel\
├── .claude\
│   ├── CLAUDE.md              ← este archivo
│   ├── stack.md               ← stack tecnico + Exclusions
│   └── project-context.md     ← contexto de negocio
├── workflows\
│   ├── current\               ← ultimo snapshot del v6 vivo (GET API)
│   └── history\               ← backups timestamped pre/post cada cambio
├── scripts\                   ← Python para fixes, audits, deploys
│   └── apply_*.py             ← un script por cambio aplicado
├── prompts\
│   ├── v6_actuales\           ← snapshot de los prompts actuales del v6 (referencia)
│   └── v7_supervisor\         ← prompts nuevos del refactor (orquestador + sub-agents)
├── tests\                     ← tests sinteticos (mensajes simulados vs intent esperado)
├── docs\
│   ├── plan-mvp.md            ← plan vigente del MVP
│   └── README.md              ← este proyecto en 1 pagina
└── README.md
```

## Estilo de trabajo en este proyecto

- Lucas (founder/owner) revisa cambios antes de aplicar. NUNCA hacer PUT al workflow vivo sin mostrar el diff primero.
- Cada cambio significativo deja un script `.py` en `scripts/` con nombre `apply_<descripcion>.py` + backup pre/post en `workflows/history/`.
- Tests sinteticos en `tests/` para validar intent classifier y banlist antes de cada PUT.
- Sessions log se escribe al VAULT (no acá), respetando regla global.

## Next steps (al 2026-05-11)

1. Refactor del Router → Supervisor minimalista (gpt-5-mini, T=0, JSON output, few-shot con casos reales del incidente).
2. Reducir 5 sub-agents → 3 (Agendar, Confirmar/Cancelar combinados, eliminar General y Urgencia).
3. Pre-filtro regex casos obvios (fromMe, /bot off, multimedia, cierres) ANTES del supervisor LLM.
4. Canneds hardcoded para info + escalacion al grupo.
5. Desconectar `buscar_conocimiento` (RAG contaminado de Nexora).
6. Filtrar `[NO_REPLY]` antes de persistir en memoria.
7. Tests sinteticos → shadow 24-48h → cutover supervisado.
