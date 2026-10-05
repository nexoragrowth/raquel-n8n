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
- **¿Cuándo crea Raquel el grupo de supervisión (ella+Lucas+Irina)?** Pedido el 14/7, repetido
  el 15/8, sigue sin crearse. Cuando exista, hay que actualizar el JID destino en
  `Helper - Notify Grupo` (y decidir si reemplaza o se suma al grupo de escalaciones actual
  `120363407321448469@g.us`).
- **Fraseo exacto de las preguntas guiadas de triaje de urgencias**: Raquel dijo que lo pasa
  junto con los 4 videos (ya filmados al 15/8) — sin eso no se puede armar el prompt del
  Sub-Agent de urgencias. _Actualización 2/9_: diseño completo del triaje ya cerrado
  (decisions.md 2/9), Raquel empezó a mandar los videos — todavía falta este fraseo y
  confirmar la lista de "red flags" que siempre escalan sin importar el tipo (borrador en
  decisions.md 2/9: trauma, sangrado abundante, pieza tragada, hinchazón/dificultad para
  respirar, fiebre, dolor intenso).
- **Casos límite del triaje para que Raquel decida** (salieron de la sombra retrospectiva del
  2/9, `docs/analisis-retrospectivo-urgencias-2026-09-02.md`): (a) arco que se sale *jugando al
  rugby* — ¿cuenta como golpe/red flag o es alambre_pincha normal?; (b) "me está matando la
  punta del alambre" — ¿"dolor intenso" es red flag aunque sea hipérbole coloquial? ¿cuál es
  el criterio?; (c) contención rota/despegada (3 escalaciones en 6 semanas) — ¿video propio,
  o siempre escala?; (d) Invisalign (alineador partido, attachment suelto: 3 casos) — ¿video o
  escala?; (e) bracket que irrita sin estar suelto (choca con colmillo, lastima el labio) —
  ¿se le manda el video de la cera (Opción 1 de alambre) o escala?
- **¿Qué video prioriza Raquel?** Con datos reales, bracket_suelto es el que más falta (6
  casos en 6 semanas); alambre_girado y ligadura_pincha tuvieron 0–1 caso cada uno.
- **Textos definitivos del triaje (4/9)**: los captions, la pregunta guiada, `texto_escalada` y
  `texto_cierre` que hoy están en `triaje_videos`/`triaje_config` son BORRADORES míos (voz de
  usted, con "Hola! Soy Asiri…" en la Opción 1). Raquel los reemplaza por UPDATE; después correr
  `tests/test_triaje_textos_banlist.py --db`.
- **¿Cuándo abre Lucas el piloto a todos los pacientes?** Hoy `telefonos_piloto={5491161461034}`.
- **¿Se arregla el auto-silencio post-escalación (6/6) a nivel Helper/Re-check?** Afecta a todos
  los sub-agents, no solo al triaje. Ver backlog P1.
- **¿Qué formato quiere Lucas para consolidar Dentalink+KB "en un formato unificado" para que
  Raquel lo revise?** Mencionado como action item el 15/8, sin definir todavía si es un doc,
  una vista nueva del panel, o un export.
- **¿El "puntito amarillo" de Dentalink es exactamente el motivo de atención `Consulta Ortodoncia`?** (8/9) Es lo
  único que distingue una primera visita en la API (`tratamiento_sin_asignar` es 0 en todas). Si hay otro motivo de
  primera visita o consultas cargadas sin motivo (`No registra motivo`, 1 hoy), reciben el genérico. Bloquea el `--apply`
  de `apply_recordatorio_consultas.py`. La regla quedó ANCLADA (`/^consulta\b/i`): si la Dra. nombra un motivo que no
  empieza con "consulta" (p. ej. "Primera Consulta"), hay que ajustar la línea `const es_consulta` y los tests.
- **¿Cuándo vuelve el bot después de que un humano toma el chat?** (05/10) Desde el desacople de
  Chatwoot, `human_takeover` solo vuelve a false con el toggle del panel. El 16/09 se había
  decidido reactivar a las 24 h (modelo Intercom/Podium). ¿Se mantiene esa regla o la Dra./Irina
  prefieren devolverle el chat al bot a mano? Decisión de Lucas y la Dra.
- **¿El bot debe dejar de confirmar consultas sin comprobante?** (8/9, R7) El template nuevo dice "si ya está abonado
  responda confirmo", pero el Sub-Agent Confirmar marca confirmado cualquier "confirmo". Decisión de la Dra./Lucas.
