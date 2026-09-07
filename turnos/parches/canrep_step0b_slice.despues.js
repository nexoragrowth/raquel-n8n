  // 600 y no 300: el bloque de turnos mide ~230 chars y con el "Soy Asiri..." adelante se pasaba de 300.
  // Este campo es lo unico que ve el parser de aceptacion (Step 3.5a) para matchear el turno elegido:
  // truncado en 300 se perdia la seccion "Por la tarde" entera.
  last_bot_msg: (lastBotMsg || '').slice(0, 600),
  oferta_bloque,
  oferta_siguiente_desde,
  bloques_ofrecidos,