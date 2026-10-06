# ❓ Auditoría de Conocimiento: Dudas Pendientes y Contenido Sospechoso
> **Propósito**: Listado de información encontrada en `knowledge_base` que sospechamos que fue inventada, rellenada como placeholder por Claude/asistentes previos o que contiene políticas que la clínica **nunca confirmó**.  
> **Acción**: Validar estos puntos con la Dra. Raquel / Irina antes de la entrega final.

---

## 🚨 1. Puntos Sospechosos / Placeholders Técnicos Detectados

### A. La marca "ASIRI" mezclada con alineadores dentales (ID 29)
- **Texto actual en Supabase**:
  > *"La Dra. es especialista en ortodoncia y está certificada para trabajar con alineadores Invisalign, ASIRI, Keep Smiling, Angel Aligner..."*
- **El disparate**: Pusieron el nombre del bot (**ASIRI**) como si fuera una marca médica de alineadores invisibles. Esto fue un placeholder inventado por un LLM previo que se copió literal a la base de datos.
- **Acción**: Borrar "ASIRI" de las marcas de alineadores.

### B. "Aceptamos reservas sin límite de tiempo hasta 1 año o más" (ID 2)
- **Texto actual en Supabase**:
  > *"Aceptamos reservas con cualquier antelación. Sin límite de tiempo. Se pueden agendar turnos hasta un año o más adelante. Lo importante es tenerlos registrados en Dentalink..."*
- **El disparate**: Ningún consultorio médico particular abre agenda a 1 año vista sin saber sus vacaciones, congresos o inflación de aranceles. Además nombra a Dentalink de cara al paciente.
- **Duda para Raquel**: ¿Con cuántas semanas/meses de anticipación máxima se permite agendar una primera consulta? (Normalmente son 2 a 4 semanas).

### C. Los "Puntos de Colores" de Dentalink en textos de pacientes (IDs 1 y 4)
- **Texto actual en Supabase**:
  > *"Punto amarillo flúor en agenda, punto verde flúor para tratamiento largo (40 min), punto verde opaco para corto (30 min), punto negro para urgencias (20 min), punto morado oscuro para contención."*
- **El disparate**: Esas son instrucciones operativas internas para la secretaria que mira la pantalla de la computadora, pero están en la base vectorial que lee el bot para responderle a los pacientes. Si un paciente pregunta por turnos, el bot le puede llegar a decir *"te asigné un punto amarillo flúor"*.
- **Acción**: Purgar toda mención a colores y dejar solo la duración o el tipo de cita.

### D. Duración y Validez del Presupuesto (ID 32)
- **Texto actual en Supabase**:
  > *"Se envía el presupuesto del tratamiento (ortodoncia / Invisalign) con validez de una semana a partir de la fecha de envío."*
- **Duda para Raquel**: ¿Realmente el presupuesto dura 7 días o tiene otra vigencia?

### E. Planes de Pago con Tarjetas Macro (ID 23)
- **Texto actual en Supabase**:
  > *"Formas de pago: efectivo, transferencia o débito/crédito Macro (hasta 3 cuotas)..."*
- **Duda para Raquel**: ¿Sigue vigente la promoción de Macro en 3 cuotas o hoy en día se manejan 100% por transferencia/efectivo?

---

## 📋 2. Preguntas Concretas para Hacerle a la Dra. Raquel (Checklist Rápido)

1. **Agenda a futuro**: ¿Hasta cuántos días/semanas adelante dejamos que un paciente reserve turno nuevo?
2. **Medios de pago en consultorio**: ¿Siguen cobrando con tarjeta de crédito Macro en cuotas o preferís que el bot solo informe Transferencia y Efectivo?
3. **Seña de primera consulta**: ¿Es obligatorio que transfieran los $50.000 antes de ir, o si no transfieren el turno se mantiene igual y abonan en el consultorio?
4. **Marcas de alineadores**: ¿Mencionamos solo Invisalign y Keep Smiling, o alguna otra? (Eliminando el error de "ASIRI").
