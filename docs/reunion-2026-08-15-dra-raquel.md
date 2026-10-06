# Reunión Dra. Raquel — 2026-08-15 (seguimiento de la del 14/7)

> Fuente: transcript + resumen automático pegado por Lucas. Mismos temas que
> `reunion-2026-07-14-dra-raquel.md` — esta reunión es en gran parte un SEGUIMIENTO: ver qué
> avanzó y qué sigue igual. Lucas seguía de viaje (Toscana, Italia).

## Qué cambió respecto al 14/7 (progreso real)

- **Reportero semanal**: construido y probado con datos reales el 11/8 (`Áurea — Reportero
  Semanal`, ver `memory/current-state.md`). Ya no es "diseño pactado, nunca construido" —
  ahora el pedido es EXTENDERLO (ver scope nuevo abajo).
- **Panel/dashboard**: construido y en producción desde el 18-19/7
  (`panel.raquelrodriguez.com.ar`). Esta reunión fue, en parte, la demo formal a Raquel (chat
  simplificado tipo WhatsApp, leído/no-leído, métricas, servicios editables — todo ya vivo).
- **Triaje de urgencias**: Raquel confirma que YA FILMÓ los videos (alambre que pincha,
  bracket suelto, alambre girado, ligadura que pincha) — la semana pasada. Sigue faltando que
  los mande + el fraseo de las preguntas guiadas.
- **Landing page**: SIGUE IGUAL que el 14/7 — Belén (fotógrafa) mandó solo 1 foto (congreso)
  de la sesión del miércoles. Las secciones faltantes del flujo de tratamiento (evaluación
  clínica, estudios complementarios, diagnóstico/explicación/plan) siguen sin material, un mes
  después. Detalle movido a `raquel-rodriguez/memory/` (repo propio de la landing).

## Incidente recurrente (el que dispara esta reunión)

El fix técnico del 14/7 ("agenda es la fuente de verdad", verificado en el workflow vivo) es
correcto y sigue funcionando — pero el incidente volvió a pasar por un motivo DISTINTO al
técnico: Irina pidió apagar los recordatorios porque ya había confirmado turnos a mano, Lucas
entendió que había que reactivarlos "el lunes" en vez de al día siguiente, quedaron apagados
extra, y el viernes Irina se encontró sin confirmaciones de lunes/martes y tuvo que laburar el
fin de semana. **No es un bug de código — es que Irina sigue pidiendo apagar/prender el bot en
vez de usar la agenda (marcar confirmado/cancelado en Dentalink), que es el flujo que YA
funciona solo.** Raquel lo remarca fuerte: "esto ha sido una macana... la idea es que esto nos
saque trabajo, no al revés".

## Decisiones (reafirmadas o nuevas)

1. **Reafirmado, con más énfasis**: Iri gestiona TODO por agenda — cancelar en Dentalink (no
   pedir apagar el bot) y marcar confirmado en Dentalink (el bot no vuelve a confirmar turnos
   ya marcados, sin importar si Iri mandó o no el recordatorio ella misma). Feriados: mismo
   mecanismo, sin necesidad de infraestructura nueva de "detectar feriado" — confirmar de
   antemano alcanza. Ver [[decisions.md]] entrada 2026-08-15.
2. **Reafirmado sin cambios**: política de precios — nunca precio fijo de tratamiento por el
   bot (se define en consulta), sí valores estáticos de consulta/estudios.
3. **Reafirmado**: reducir escalaciones innecesarias, el agente debe resolver más solo con
   contexto/KB — pero las escalaciones de pago (comprobante a verificar por Irina) están bien,
   no se tocan.
4. **Nuevo — grupo de supervisión sigue sin crearse**: Raquel lo pidió el 14/7 y de nuevo hoy
   (Raquel + Lucas + Irina, para ver en vivo los pedidos/decisiones que Irina manda sobre el
   chatbot). Un mes después, sigue pendiente del lado de Raquel — no es un bloqueo técnico.

## Scope nuevo/extendido acordado

### A. Reportero semanal → agregar scoring de urgencias
Sobre el reportero ya construido (11/8): agregar que el agente **califique la urgencia**
(scoring de severidad), haga **preguntas específicas** de triaje, y que el reporte semanal
**mapee las urgencias de la semana** además de las escalaciones generales, sugiriendo
contenido/video nuevo para casos recurrentes. Casos muy graves (poco frecuentes en ortodoncia
según Raquel) → aviso inmediato al grupo, no esperar al semanal.

### B. Triaje de urgencias con videos (ya no bloqueado por falta de filmación)
Falta: (1) que Raquel mande los 4 videos, (2) el fraseo/preguntas guiadas que usan ellos en
consulta para discernir tipo de urgencia (piden foto primero, porque el paciente no sabe
explicar). Con eso, el bot debe: clasificar tipo de urgencia → preguntas guiadas → pedir foto →
mandar el video correcto → si es grave, escalar con score alto.

### C. Panel — pendientes puntuales de esta demo
- Toggle bot/humano **inmediato** al escribir un mensaje humano (ya existe la lógica de
  ventana de 30 min de verificación — Raquel pide que sea al toque, no esperar).
- Idea nueva (exploratoria, no comprometida): perfil/análisis de personalidad del paciente
  visible en la ficha de la agenda, cruzando CRM + Dentalink.
- Servicios/KB editables desde la UI — ya existe (`/servicios`, `/conocimiento`), reafirmado
  como el lugar correcto para que Raquel actualice valores sin depender de Lucas.

### D. Landing page (repo aparte — ver `raquel-rodriguez/memory/`)
Mismo pedido que el 14/7, sin material nuevo todavía. Raquel además pidió puntualmente
revisar la barra de navegación fija (inicios/tratamientos/primera consulta) para agregar un
link a resultados/transformaciones.

## Action items (de la minuta)

- **Raquel**: crear el grupo de supervisión (pendiente desde 14/7) · enviar los 4 videos de
  urgencias + el fraseo de preguntas guiadas · revisar navegación/ubicación de resultados en
  la landing.
- **Lucas**: consolidar Dentalink+KB en un formato unificado para review de Raquel · agregar
  scoring de urgencias + mapeo semanal de urgencias al reportero · toggle bot/humano inmediato
  en el panel · sección transformaciones + link navbar en la landing (bloqueado por material) ·
  mandar el reporte semanal al grupo de escalaciones actual (y al nuevo cuando exista).
- **Iri**: seguir la agenda — confirmar/cancelar en Dentalink, no pedir apagar/prender el bot.
