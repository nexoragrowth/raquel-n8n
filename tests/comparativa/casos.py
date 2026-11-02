# -*- coding: utf-8 -*-
"""
Casos INVENTADOS (ningún dato real de pacientes) para comparar los cerebros de Asiri en sombra. Reproducen los patrones de los casos reales que
fallaron o que importan (auditoría del 28/10). Cada historial es una lista de mensajes ANTERIORES, el más reciente primero:
  quien: paciente | asiri | staff (WhatsApp del consultorio) | recordatorio ; hace_min: minutos antes de ahora.
"""
RECORD = ("✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\nEstimada Ana, le recordamos su turno con la Dra. Rodríguez Raquel:\n\n📅 Jueves 12 de noviembre de 2026\n🕔 10:40 hs\n\n"
          "Por favor confirme su asistencia respondiendo este mensaje.")
COMPROBANTE = ("[IMAGEN] TIPO: COMPROBANTE | MONTO: {m} | DESTINATARIO: Laura Raquel Rodriguez | FECHA: 02/11/2026 | HORA: 09:40 | "
               "DESCRIPCION: Comprobante de transferencia")
CASOS = [
    dict(id="precio-1", cat="precio", texto="hola cuanto sale la consulta?", hist=[], esperado="Dice que la primera consulta sale $50.000 y ofrece buscar turno."),
    dict(id="precio-2", cat="precio", texto="buenas, me pasas el precio de la primera consulta por favor", hist=[], esperado="Precio de la consulta, corto."),
    dict(id="horarios-1", cat="horarios", texto="a que hora atienden los martes?", hist=[], esperado="Horario de los martes según Conocimiento, sin inventar."),
    dict(id="direccion-1", cat="direccion", texto="donde queda el consultorio?", hist=[], esperado="La dirección de Conocimiento."),
    dict(id="turno-1", cat="turno nuevo", texto="quiero un turno para la semana que viene", hist=[], esperado="Ofrece horarios reales y pregunta para quién."),
    dict(id="turno-2", cat="turno nuevo", texto="tienen turno para el jueves a la mañana?", hist=[], esperado="Busca solo jueves a la mañana; si no hay, lo dice y ofrece lo más cercano."),
    dict(id="turno-3", cat="turno nuevo", texto="necesito turno a la tarde, salgo del trabajo a las 18", hist=[], esperado="Ofrece horarios de tarde si existen."),
    dict(id="nuevo-datos", cat="paciente nuevo", texto="Camila Lopez DNI 40123456",
         hist=[dict(quien="asiri", hace_min=3, texto="Para reservarlo necesito nombre, apellido y DNI del paciente, en un solo mensaje."),
               dict(quien="paciente", hace_min=4, texto="el jueves 12 a las 8:40"),
               dict(quien="asiri", hace_min=5, texto="Tenemos los próximos turnos disponibles:\nPor la mañana:\n* Jueves 12 de noviembre 8:40 , 10:40\n\nLe sirve alguno?")],
         esperado="Arma el resumen del turno y pregunta '¿Procedo?' ANTES de reservar."),
    dict(id="confirmo-1", cat="confirmar recordatorio", texto="Confirmo", hist=[dict(quien="recordatorio", hace_min=30, texto=RECORD)], esperado="Confirma el turno del recordatorio, corto."),
    dict(id="confirmo-2", cat="confirmar recordatorio", texto="si ahi estaremos gracias", hist=[dict(quien="recordatorio", hace_min=45, texto=RECORD)], esperado="Lo toma como confirmación."),
    dict(id="confirmo-3", cat="confirmar recordatorio", texto="dale confirmado 👍", hist=[dict(quien="recordatorio", hace_min=20, texto=RECORD)], esperado="Lo toma como confirmación."),
    dict(id="comprobante-1", cat="comprobante", texto=COMPROBANTE.format(m=50000), hist=[], esperado="Recibe el comprobante, lo anota, avisa que la secretaria verifica. Un solo mensaje corto."),
    dict(id="comprobante-2", cat="comprobante", texto="Buenas tardes\n" + COMPROBANTE.format(m=70000), hist=[], esperado="Igual: registra y avisa; el saludo previo no lo cambia."),
    dict(id="comprobante-3", cat="comprobante", texto=COMPROBANTE.format(m=50000),
         hist=[dict(quien="recordatorio", hace_min=60, texto=RECORD)], esperado="Registra el pago y lo toma como confirmación del turno; sin preguntar de más."),
    dict(id="alias-1", cat="alias", texto="me pasas el alias para transferir?", hist=[], esperado="Pasa los datos de pago tal cual (los pone el sistema), corto."),
    dict(id="alias-2", cat="alias", texto="podria enviarme el alias? asi confirmo los turnos", hist=[], esperado="Pasa los datos de pago; no confirma nada."),
    dict(id="mixto-1", cat="mixto", texto="quiero un turno y pasame el alias", hist=[], esperado="Ofrece horarios Y pasa los datos de pago, en un solo mensaje ordenado."),
    dict(id="mixto-2", cat="mixto", texto="cuanto sale la consulta? y cuanto debo yo de lo mio?", hist=[], esperado="Da el precio de la consulta y deriva lo de la deuda a la secretaria."),
    dict(id="mixto-3", cat="mixto", texto="puedo cambiar el turno del lunes y me decis cuanto cuesta la contencion?", hist=[], esperado="Atiende el cambio de turno y deriva el precio de la contención (no informa precios de tratamiento)."),
    dict(id="urgencia-1", cat="urgencia", texto="se me salio un bracket y me duele mucho", hist=[], esperado="Urgencia: circuito de triaje, sin diagnosticar ni indicar nada."),
    dict(id="urgencia-2", cat="urgencia", texto="mi hija tiene el alambre que le pincha la mejilla", hist=[], esperado="Urgencia: triaje."),
    dict(id="urgencia-3", cat="urgencia", texto="se me cayo el aparato y tengo sangrado", hist=[], esperado="Urgencia: triaje."),
    dict(id="persona-1", cat="pide persona", texto="quiero hablar con la doctora", hist=[], esperado="Pasa a una persona y avisa al grupo."),
    dict(id="persona-2", cat="pide persona", texto="pasame con la secretaria por favor", hist=[], esperado="Pasa a una persona."),
    dict(id="staff-1", cat="contesta a la secretaria", texto="perfecto gracias, ahi estare",
         hist=[dict(quien="staff", hace_min=90, texto="Hola Ana! Ya te dejé reservado el jueves a las 10 😊")], esperado="Silencio: la secretaria ya está en la charla."),
    dict(id="staff-2", cat="contesta a la secretaria", texto="dale, ya le mande los estudios por mail",
         hist=[dict(quien="staff", hace_min=120, texto="Sra. mamá, por favor envíenos los estudios por mail cuando pueda 😊")], esperado="Silencio (le contesta a la secretaria)."),
    dict(id="sticker-1", cat="sticker/cortesía", texto="[STICKER]", hist=[], esperado="Silencio."),
    dict(id="gracias-1", cat="sticker/cortesía", texto="gracias 🙏", hist=[dict(quien="asiri", hace_min=2, texto="Listo, su turno del jueves 12/11 a las 10:40 quedó confirmado.")], esperado="Silencio o un cierre cortísimo."),
    dict(id="audio-1", cat="audio", texto="[AUDIO] hola queria saber cuanto sale la primera consulta [MEDIA:a1b2c3]", hist=[], esperado="Responde el precio como si fuera texto."),
    dict(id="audio-2", cat="audio", texto="hola\n[AUDIO] le puede preguntar a la doctora si la tomografia la tengo que hacer con o sin los brackets? [MEDIA:d4e5f6]", hist=[], esperado="Consulta clínica: la pasa a la secretaria, sin decir 'no puedo escuchar'."),
    dict(id="obrasocial-1", cat="obra social/cuotas", texto="trabajan con OSDE? y se puede pagar en cuotas el tratamiento?", hist=[], esperado="Responde solo lo que está en Conocimiento (obra social) y deriva las cuotas."),
    dict(id="familia-1", cat="familia", texto="el del lunes no vamos a poder, lo pasamos, pero el del miercoles queda",
         hist=[dict(quien="recordatorio", hace_min=40, texto="✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\nEstimada familia, le recordamos sus turnos:\n📅 Lunes 9 de noviembre 17:40 (Tomás)\n📅 Miércoles 18 de noviembre 18:20 (Sofía)")],
         esperado="Entiende dos pedidos distintos: reprogramar el del lunes (pide '¿Procedo?' / ofrece horarios) y dejar confirmado el del miércoles. No confunde los dos."),
    dict(id="fuera-1", cat="fuera de alcance", texto="hola soy proveedor de insumos odontologicos, con quien hablo?", hist=[], esperado="Lo pasa a la secretaria; no lo trata como paciente."),
]
