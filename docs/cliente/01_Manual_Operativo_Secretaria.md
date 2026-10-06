# 🏥 Manual Operativo: Asistente Virtual WhatsApp (Áurea Odontología)

> **Destinatarios**: Dra. Raquel Rodríguez e Irina (Secretaría).  
> **Sistema**: Nexora WhatsApp Agent + Dentalink.  
> **Fecha de Actualización**: Octubre 2026.

---

## 1. ¿Cómo Ingresar al Panel de Control?
El panel web es su única herramienta de trabajo diario para ver los chats y responder a los pacientes:
- **Enlace de acceso**: `https://nexora-whatsapp-agent.vercel.app` (o su dominio oficial).
- **Usuario y Clave**: Los provistos por el equipo técnico.
- **Acceso móvil o PC**: Se puede abrir en cualquier computadora del consultorio o en el celular.

---

## 2. ¿Cómo Atender un Chat? (Modo Bot vs. Modo Humano)

En la parte superior de cada conversación del panel verán un interruptor (switch):

```
[ Modo Bot: ACTIVADO 🟢 ]  <--->  [ Modo Humano: ACTIVADO 👤 ]
```

### Reglas Simples de Uso:
1. **Si quieren responder ustedes**:
   - Mueven el switch a **Modo Humano**.
   - El bot se apaga de inmediato para ese paciente. Ya pueden escribir tranquilas por el panel o desde el WhatsApp del consultorio sin que el bot se meta.
2. **Cuando terminan de atender**:
   - Vuelven a poner el switch en **Modo Bot** para que el asistente retome la atención automática.
3. **Seguridad Automática (Ventana de 24 horas)**:
   - Si por alguna razón se olvidan de reactivar el bot al finalizar una charla, **a las 24 horas exactas de inactividad el bot retoma el control solo**. Ningún paciente quedará desatendido para siempre.

---

## 3. ¿Qué Hace el Bot en Automático? (Sin molestarlas)

El asistente virtual está programado para resolver las tareas repetitivas de forma 100% autónoma:
1. **Dar Información Básica**:
   - **Dirección**: Balcarce Nº 37, 2º piso, San Salvador de Jujuy.
   - **Horarios**: Lunes y Miércoles 15 a 19 hs | Martes, Jueves y Viernes 8 a 12 hs.
   - **Precios oficiales**: Primera consulta de valoración: **$50.000** | Cuota mensual de ortodoncia: **$70.000**.
   - **Datos Bancarios**: Alias `dra.raquel.aurea` (Brubank, Laura Raquel Rodríguez).
2. **Agendar Nuevos Turnos**:
   - Consulta Dentalink en tiempo real y ofrece los turnos disponibles organizados por mañana y tarde.
   - Crea la ficha en Dentalink y bloquea el sillón automáticamente.
3. **Recordatorios y Confirmaciones**:
   - Envía recordatorios automáticos 24 y 72 hs antes del turno.
   - Si el paciente responde "Sí, confirmo", marca la cita como *Confirmada* en Dentalink para que cambie de color en su agenda.

---

## 4. ¿Qué Cosas Deriva SIEMPRE al Grupo de WhatsApp?

El bot tiene prohibido inventar información médica o validar transferencias bancarias. En los siguientes casos, les enviará una alerta automática al grupo de WhatsApp *"WhatsApp Clínica Raquel"*:
- 🚨 **Dolor, sangrado o urgencias** (brackets despegados, alambre que pincha).
- 📸 **Fotos de bocas o estudios radiográficos**.
- 💳 **Comprobantes de pago**: El bot le avisa al paciente que recibió la foto y les deriva el caso para que ustedes verifiquen la acreditación en la cuenta bancaria.
- ❓ **Dudas fuera de ortodoncia**: Cualquier consulta clínica compleja.

---

## 5. Contacto y Soporte Técnico
Ante cualquier cambio de precios, cambio de alias bancario o consulta técnica:
- **Soporte Nexora**: Canal directo de WhatsApp con Lucas / Equipo Técnico.
