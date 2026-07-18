# Preguntas abiertas — raquel-n8n

- **¿Quién arregló el Health Check el 2026-07-05 22:20Z?** Estuvo roto 2.3 días (114 errores
  seguidos, monitoreo ciego el finde) y alguien lo reparó. ¿Lucas? ¿Codex? ¿Otra sesión?
  Importa para saber quién más está tocando prod.
- **¿Qué fracción del tráfico llega como @lid "pelado"** (sin remoteJidAlt/senderPn)? En la
  ventana del 06/07 fue 1/15 DMs reales (~7%, exec 193142, paciente CeC!). Si crece, la tabla
  de mapeo lid↔teléfono (Fase 2) sube de prioridad.
- **¿Dentalink devuelve las fichas de un celular en qué orden?** (¿data[0] = la más vieja =
  usualmente la madre/padre?) El impacto real del GAP 1 (turnos solo de data[0]) depende de esto.
- **¿El fix `apply_fix_router_reagendar.py` se aplicó alguna vez?** El Router vivo no tiene
  sus señales — o nunca corrió o fue pisado por la reescritura de reglas del 03/06.
- **¿Las ejecuciones que alimentaron el reporte semanal (score 6/10) de dónde salen?**
  n8n retiene ~72h; el reporte probablemente lee del Logger/Supabase — auditar esa fuente
  antes de ajustar el reportero. _Nota 17/7_: el workflow desconocido hallado en la
  auditoría (`BO1cdE8xmqln4IeO` Cron Resumen Clinico) NO es el reportero — el reportero
  semanal sigue sin ubicarse (la ventana del censo fue ~22h; si es semanal no aparece).
- **¿Quién prendió/dejó prendido el Logger y Cleanup que "debían estar inactivos"?**
  (17/7) La auditoría confirma que corrieron activos hasta 16/7 16:37Z. Misma incógnita
  que el arreglo fantasma del Health Check: ¿alguien más toca prod?
- **¿La dominancia del modo "Humano Atendiendo" es política deliberada o TTLs largos de label?**
  Si el label expira distinto de lo esperado, el bot podría meterse en charlas humanas.
