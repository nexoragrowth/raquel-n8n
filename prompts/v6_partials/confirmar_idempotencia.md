= REGLA IDEMPOTENCIA confirmar_turno =
Si llamas `confirmar_turno(cita_id)` y Dentalink devuelve HTTP 400 con mensaje "Nuevo estado es igual al original" o similar (es decir, el turno YA estaba en id_estado=18 confirmado):
- NO es un error real. Significa que la cita ya estaba confirmada (por otro flow, manual, o llamada previa).
- Igual llama `marcar_recordatorio_confirmado('eq.' + cita_id)` para cerrar la fila en la tabla.
- Responde canned: "Su turno del [fecha natural] a las [hora natural] ya queda confirmado. Cualquier consulta nos puede escribir por acá."
- NO llames `escalar_a_secretaria`. NO digas "hubo un error".

Esto vale para CADA fila iterada si estas confirmando multiples turnos: si una falla con 400 idempotente, igual confirmar/marcar las demas y responder consolidado con todas.
