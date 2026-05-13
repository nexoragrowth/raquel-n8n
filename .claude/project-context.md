# Contexto de negocio - Áurea Odontología Estética

## Cliente

**Dra. Raquel Rodriguez** — odontóloga ortodoncista, dueña de Áurea Odontología Estética.

Ubicación: Balcarce 37, 2do piso, San Salvador de Jujuy.

Equipo:
- **Dra. Raquel Rodriguez** — owner, profesional principal.
- **Irina** (también referida como "Iri") — secretaria. Atiende WA del consultorio. Phone admin para `/bot off|on`: `5493885786946`.

## Por qué importa para Nexora

Caso bandera para vertical clínicas/consultorios. Primera cuota mensual cobrada. Estado de relación al 2026-05-09: doctora le pidió a Lucas detener el bot tras incidente Mariela. Confianza temporalmente rota, Lucas tomó responsabilidad y se comprometió a refactor + shadow + cutover supervisado antes de volver a prender.

## Valor entregado vs riesgo

**Lo que YA entrega valor sin riesgo** (NO TOCAR):
- Recordatorios automáticos 24h y 72h antes del turno. Workflow `7RqTApkvVavRmq3R`, cron 9 AM Arg, plantillas pasadas por Irina (verificadas):
  - 72h: header formal `✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨` + política cancelación 48h
  - 24h: corto cálido `Hola, [Nombre] 😊 le recordamos que mañana la esperamos...`
  - Detección de género por terminación del primer nombre (a/o)
- Health Check Dentalink + Evolution cada 30 min.
- Daily Summary 9:30 AM Arg.

**Lo que tiraba macanas y por eso está apagado**:
- Bot conversacional v6 (Multi-agent). Apagado tras incidente Mariela 2026-05-09.

## Política operativa (acordada con Lucas)

1. Bot SOLO atiende: agendar, recordar, confirmar/cancelar, info canned.
2. Todo lo demás (urgencias, fotos dentales, consultas médicas, comprobantes) escala automáticamente a la doctora vía grupo de WhatsApp.
3. Cuando Irina o la doctora responden manualmente desde cualquier canal (Chatwoot, WhatsApp Web del consultorio, app del consultorio), el bot detecta y se calla en ese chat por X horas.
4. El bot NUNCA da indicaciones operativas/médicas ni invita a la clínica.

## Tono del bot al paciente

- "Soy la asistente virtual de la Dra. Raquel."
- Profesional cordial, no imitar secretaria humana casual (tono "Iri" generaba confusión: pacientes nuevos no entendían quién era).
- Read-back formal con datos del turno post-confirmación (no solo emoji 👍).
- Nunca afirmar que un turno existe sin verificar con `ver_turnos_paciente`.
- Nunca "veo el recordatorio" — el bot mandó el recordatorio, no es ajeno.

## Datos clínicos hardcoded (info canned)

> Estos van en el system prompt corto del sub-agent + en canneds de info directa. Fuente de verdad: vault `dra-raquel-n8n.md`. **Confirmar con doctora antes de hardcodear.**

- **Primera consulta**: $40.000 (verificar)
- **Alias bancario**: `dra.raquel.aurea`
- **Horarios atención**: Lun y Mié 15-20 hs / Mar, Jue, Vie 8-12 hs / Sáb, Dom y feriados CERRADO
- **Política cancelación**: 48hs antes del turno. No-show debe abonar igual.
- **Dirección**: Balcarce 37, 2do piso, San Salvador de Jujuy.
- **Métodos de pago primera consulta**: efectivo en clínica o transferencia. NO acepta tarjeta en primera visita.

## Lecciones del incidente Mariela (no repetir)

1. Si el bot puede generar texto libre con poder de "invitar a la clínica", encontrará la forma de tirar macana. Defensa determinística (banlist regex) es no-negociable.
2. Examples en el system prompt actúan como patrón a copiar. El ejemplo "Te esperamos" en sub-agents era LITERAL — el bot lo copió. Verificar que TODOS los ejemplos del prompt sean output deseable, no solo "ilustrativos".
3. Confianza de la doctora se gana con proceso. Cada feature nuevo va a shadow 24-48h antes de cutover supervisado. Sin atajos.
4. Mariela fue paciente real, no test. Si pasa otra vez, no hay segunda chance.
