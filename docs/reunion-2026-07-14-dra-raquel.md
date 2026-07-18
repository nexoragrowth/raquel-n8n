# Reunión Dra. Raquel — 2026-07-14 (Lucas desde Italia)

> Fuente: transcript + resumen automático pegado por Lucas. Temas: incidente recordatorios,
> escalaciones/autonomía, dashboard, triaje de urgencias con videos, landing page.

## Decisiones clave

1. **La agenda de Dentalink es la fuente de verdad** — no más on/off manual del workflow:
   - Cancelación → se cancela EN LA AGENDA → el bot no recuerda ese turno.
   - Confirmación anticipada de Iri → marca CONFIRMADO en agenda → el bot no re-confirma.
   - ✅ **VERIFICADO TÉCNICO (Claude, 14/7)**: ambos filtros YA existen en el workflow vivo
     (`id_estado != 1` en el GET + condición `skip-confirmados id_estado != 18` en el IF).
     El flujo que pidió Raquel funciona HOY. Feriados: no requiere infra — se resuelve
     confirmando antemano en agenda.
2. **Reducir escalaciones** — el agente debe resolver más solo; escalar pagos SÍ (Iri verifica),
   pero no info que ya tiene o puede tener en KB. Meta estratégica: agente "bastante autónomo"
   para fin de año, gestionable por el staff vía panel (sin depender de Lucas).
3. **Grupo de supervisión nuevo**: Raquel + Lucas + Irina — Raquel quiere ver los pedidos que
   Iri hace y las escalaciones para corregir criterios. (Raquel lo crea.)
4. **Precios**: ratificado lo actual — NUNCA precio de tratamientos (se evalúa en consulta);
   SÍ valores estáticos (consulta, estudios). Ya implementado así.
5. **El agente NO cancela turnos por defecto** — sigue agenda y marca confirmaciones;
   cancelar es último recurso (política reforzada por Raquel).

## Nuevo scope acordado

### A. Triaje de urgencias con videos (prioridad de Raquel)
- Raquel filmó videos: alambre que pincha, bracket suelto, alambre girado, ligadura que pincha.
- El bot debe: **clasificar el tipo de urgencia** → hacer **preguntas guiadas** (Raquel pasa el
  fraseo exacto que usan ellos) → **pedir FOTO** (los pacientes no saben explicar) → enviar el
  **video correspondiente** para urgencias menores (clave: fuera de horario/fin de semana) →
  **scoring de severidad** → solo lo grave escala con notificación inmediata.
- Contexto clínico de Raquel: "nada en ortodoncia es de vida o muerte" — el triaje puede ser
  generoso resolviendo solo. Cada vez más alineadores → menos urgencias de alambres.
- BLOQUEADO POR: Raquel envía videos + fraseo de preguntas.

### B. Reportero v2 = "reporte de aprendizaje semanal"
- Mapear escalaciones de la semana + urgencias ocurridas.
- Decir ESPECÍFICAMENTE qué información falta añadir a la KB (no "falta info" genérico) y
  sugerir contenido/videos nuevos para urgencias recurrentes.
- Raquel valida qué se agrega y qué no (hay info post-consulta que NO va al bot).
- Se envía al grupo de supervisión (Raquel ya recibe el semanal en su celu ✓).
- (Se fusiona con el pendiente previo: el reportero actual cuenta mal las escalaciones.)

### C. Dashboard "nexora-whatsapp-agent"
- Proyecto: `Desktop/proyectos/nexora-whatsapp-agent` (Next.js + Supabase) —
  deploy: https://nexora-whatsapp-agent.vercel.app/
- Pedidos de la reunión: UI estilo WhatsApp simple (Raquel encuentra a Chatwoot confuso),
  controles leído/no-leído, toggle bot/humano inmediato (sin esperar la ventana de 30-60 min),
  métricas clave (citas por agente vs secretaria, conversaciones, mensajes/día, minutos
  ahorrados) desde Dentalink, y **servicios/KB editables desde la UI** (fuente de verdad
  actualizable por el staff — cambian valores/forma de trabajo seguido).
- Futuro: perfil/análisis del paciente (CRM sobre Dentalink) visible en la agenda.
- Objetivo: reemplazar Chatwoot para el staff.

### D. Landing page (proyecto aparte)
- Faltan secciones del flujo de tratamiento: 1ra visita (evaluación clínica), 2da visita
  (estudios complementarios), diagnóstico, explicación y plan. Belén solo mandó 1 foto (congreso) —
  falta material.
- Agregar sección **Transformaciones/Resultados (antes-después)**: ubicación acordada =
  después del hero O después de tratamiento/proceso, + cerca de testimonios/estrellitas.
  Label marketinero ("Mirá las transformaciones"). Agregar al navbar fijo (inicios,
  tratamientos, primera consulta → + resultados).
- Raquel tiene casos lindos para mostrar; storytelling cohesivo.

## Action items (de la minuta)
- Raquel: crear grupo con Lucas+Irina · enviar videos de urgencias · pasar fraseo de preguntas
  de triaje · revisar navegación/ubicación de resultados en landing.
- Lucas: consolidar Dentalink+KB en el panel · mostrar panel a Raquel · simplificar UI chat
  (leído/no leído + métricas) · urgency scoring + reporte semanal de aprendizaje + sugerencias
  de KB · mandar el reporte al grupo · sección transformaciones en landing · (feriados: RESUELTO
  vía agenda, no requiere infra).
- Iri: gestionar TODO por agenda (confirmar/cancelar en Dentalink, no pedir on/off del bot).
