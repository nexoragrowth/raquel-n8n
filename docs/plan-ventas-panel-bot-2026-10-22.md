# Plan: que el bot y el panel vendan (convertir consultas en pacientes)

*22/10/2026. Contexto: la Dra. Raquel hace publicidad; cada contacto que llega cuesta plata. Meta: que ninguno se pierda por demora, por no confirmar o por falta de seguimiento, y que la clínica controle lo que Asiri dice sin depender de nadie.*

## 0. Dónde estamos parados (datos reales del 22/10)

| Dato | Valor | Qué significa |
|---|---|---|
| Consultas atendidas (90 d) | 27 (antes 35) | El volumen bajó |
| Consultas perdidas (anuladas o no vino) | 12 = **31 %** ≈ $600.000 | Fuga principal medible |
| Cambios de fecha | 10 | No son pérdida, pero consumen horarios |
| Devolución/escaneo | 35 | Hay trabajo clínico, la conversión depende del seguimiento |
| Inicios de tratamiento | 10 (≈ 37 % de las consultas) | La plata grande |
| Casos abiertos en Atención | 25, con 2 urgencias abiertas hace 2 días | Lo urgente se enterraba |
| Contactos nuevos (7 d) sin turno cercano | 2 | Medir mejor la entrada de anuncios |

## 1. Principios
1. **Una sola pantalla para cada cosa.** Cada dato tiene un único lugar donde se carga.
2. **Lo urgente a la vista, con plata.** El Home dice qué hacer primero y cuánto vale.
3. **El bot nunca promete lo que no puede cumplir** (reglas del incidente del 9/5 siguen firmes).
4. **Nada masivo ni sin permiso del paciente.** Mensajes proactivos por Evolution (no oficial) tienen riesgo de bloqueo: seguimientos con texto sugerido para que los mande una persona, y automáticos solo dentro de la conversación abierta.
5. **Se mide todo lo que se pueda con datos propios, sin inventar.**

## 2. Frentes (ordenados por impacto / esfuerzo)

### A. Claridad de dónde cargar (esfuerzo bajo, impacto alto)
- Desplegar el panel nuevo: **Conocimiento** único (reemplaza Servicios y Aprendizaje).
- Recuadro fijo en Conocimiento: "Qué se carga acá y qué no" con 5 ejemplos (horarios, precio de la consulta, dirección, alias, texto de anuncio) y qué pasa con cada tipo.
- **Probador "así contesta Asiri"** dentro de Conocimiento (modo sombra, no escribe ni avisa al grupo): la clínica escribe una pregunta y ve la respuesta *antes* de guardar. Resuelve el miedo a "no sé qué va a decir".

### B. No perder el contacto del anuncio (impacto alto)
1. **Saludo de anuncio** ya existe (corto + precio + oferta de turno). Medirlo: cuántos contactos de anuncio pidieron turno, cuántos agendaron.
2. **Origen del contacto** (anuncio / orgánico) en la lista de chats y en el Home. Hoy `ctwa_ad` se detecta pero no se muestra.
3. **Costo por consulta atendida y por inicio de tratamiento:** campo "inversión en publicidad del mes" (manual) en el panel → costo por contacto, por consulta, por inicio. Convierte el Home en un tablero de retorno.
4. **Velocidad de respuesta:** alerta "contacto nuevo sin respuesta hace X minutos" (hoy 0 casos, pero es el primer lugar donde se pierde plata).

### C. Bajar la fuga de consultas (impacto alto)
1. **Pago anticipado como fricción:** medir cuántas consultas se pierden entre "agendó" y "pagó" (comprobantes vs. turnos de consulta). Probar un texto más claro del pedido de pago (decisión de la Dra.).
2. **Recordatorios:** hoy a 2 días hábiles con pedido de confirmar. Evaluar un segundo toque el día anterior solo a quien no confirmó (la lista ya está en "Para confirmar esta semana").
3. **Anulaciones:** al anularse una consulta, ofrecer reprogramar en el mismo mensaje (Asiri ya sabe agendar) y mostrar en el Home "Para recuperar".
4. **Lista de espera:** si se libera un hueco (anulación), avisar al panel quién estaba esperando y sugerir el texto. Hoy Asiri solo anota.

### D. Del consultorio al tratamiento (impacto muy alto, necesita a la Dra.)
Pantalla **Seguimientos** con cuatro listas, con texto sugerido editable (copiar y pegar):
1. Consulta atendida sin devolución agendada (a los N días).
2. Devolución hecha sin inicio de tratamiento (a los N días).
3. No vino o anuló sin reprogramar.
4. Contacto nuevo sin respuesta de la clínica.
Plazos y textos por defecto; la Dra. los ajusta. Limitación: por persona solo con teléfono conocido (quienes tuvieron recordatorio) hasta que se firme el contrato de datos de Dentalink (SEG-17). Los totales ya salen sin datos personales.

### E. Control del bot por la clínica (impacto alto)
1. Probador (ver A).
2. **"Qué le faltó a Asiri":** los casos "consulta fuera de lo que atiende" (8 hoy) agrupados por tema con botón "crear entrada en Conocimiento". Cierra el ciclo pregunta nueva → respuesta cargada.
3. **Revisión semanal en 5 minutos:** una pantalla con 10 conversaciones al azar de Asiri, con "estuvo bien / corregir" (alimenta la lista de tests permanentes).
4. Interruptor de emergencia y modo humano (ya están).

### F. Panel usable en el celular (impacto medio-alto)
1. **App instalable (PWA)** con guía "agregar a la pantalla de inicio" en el onboarding de cada usuario.
2. **Notificaciones push** para: urgencia, pidió persona, contacto nuevo sin respuesta. Activación por persona. En iPhone requiere la app instalada (iOS 16.4+).
3. **Una sola barra inferior** en todas las pantallas del celular (hoy tres pantallas traen la suya).
4. **Onboarding del usuario** (2 minutos la primera vez): qué hace Asiri, dónde ver lo urgente, cómo contestar, cómo instalar.

### G. Informes para la Dra. (impacto medio)
Resumen semanal automático por el grupo (1.ª página autosuficiente): consultas atendidas, perdidas y su plata, inicios, casos abiertos hace más de 24 h, una recomendación. Sin nombres ni teléfonos.

### H. Solidez (no se negocia)
- Panel: desplegar lo hecho y verificarlo con la Dra. en la web real.
- Bot: tests permanentes, smoke test nocturno con número sintético, revisión semanal de escalaciones.
- Seguridad: repo privado, rotar claves, purgar historial (pendiente de Lucas).

## 3. Orden de ejecución propuesto
1. **Semana 1:** deploy + recuadro "qué se carga acá" (A) + origen del contacto y velocidad de respuesta (B2, B4) + PWA e instalación (F1) + barra única (F3).
2. **Semana 2:** push (F2) + probador "así contesta Asiri" (A/E1) + "qué le faltó a Asiri" (E2) + inversión y costo por consulta (B3).
3. **Semana 3:** Seguimientos con las 4 listas y textos (D) + recuperación de anulaciones y lista de espera con aviso (C3, C4).
4. **Semana 4:** informe semanal (G) + revisión semanal de respuestas (E3) + onboarding del usuario (F4).

## 4. Decisiones que necesito de la Dra. (con valor por defecto)
| Decisión | Por defecto si no responde |
|---|---|
| Plazo para escribir tras una consulta sin devolución | 3 días |
| Plazo tras devolución sin inicio de tratamiento | 7 días |
| Cambios y cancelaciones a menos de 48 h | Asiri deriva (como hoy) |
| ¿Puede Asiri ofrecer reprogramar automáticamente cuando alguien anula? | Sí, dentro de la misma conversación |
| Inversión mensual en publicidad (para el costo por consulta) | Se carga a mano en el panel |
| Textos de seguimiento | Propuestos por nosotros, editables |

## 5. Lo que NO se hace (por ahora)
- Mensajes masivos o campañas salientes por Evolution (riesgo de bloqueo del número).
- Precios de tratamientos por WhatsApp (solo el valor de la consulta).
- Historia clínica o datos de salud en el panel (esperan el contrato firmado).
