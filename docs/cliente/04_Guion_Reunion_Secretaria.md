# Guion de la reunión grabada con la secretaria (y la Dra.)

*Duración sugerida: 50 a 60 minutos. Se graba (pantalla + voz) y la Dra. lo pone en su manual. Hecho para que lo conduzca Lucas y la secretaria lo vaya haciendo con sus manos.*

## Antes de la reunión (Lucas, 20 minutos)
- [ ] Panel desplegado con la última versión y las pantallas **Atención**, **Seguimientos** y **Asiri** visibles (`ATENCION_BANDEJA=1` y `SEGUIMIENTOS=1` en el servidor).
- [ ] La secretaria tiene **usuario y contraseña propios** del panel (probados el día anterior, también desde el celular).
- [ ] Un **número de prueba** (el de Lucas) con dos turnos de prueba en Dentalink y sus recordatorios, para mostrar "Confirmo" en vivo. Después se limpian (citas anuladas, memoria borrada).
- [ ] Manual impreso o abierto (`docs/cliente/01_Manual_Operativo_Secretaria.md`).
- [ ] Un caso real **sin datos de pacientes** preparado en Atención (un aviso de ejemplo) para practicar.
- [ ] Grabación de pantalla probada (sonido incluido). **Mostrar datos de pacientes reales en la grabación es un riesgo**: usar el número de prueba, o tapar los nombres.

## Agenda (con tiempos)

| Min | Tema | Qué se hace en pantalla | La secretaria practica |
|---|---|---|---|
| 0–5 | **Qué es Asiri** | Mostrar el WhatsApp de la clínica: un saludo, un pedido de turno, una consulta de precio. Explicar lo que hace y lo que **no** hace (capítulos 1 y 2 del manual). | — |
| 5–10 | **Entrar al panel** | Login, menú, el celular. | Entra con su usuario. |
| 10–20 | **Conversaciones** | Lista, buscador, filtros, interruptor **Bot / Humano**, escribir un mensaje, fotos de perfil, turnos del paciente. | Busca un chat, lo pasa a Humano y le escribe al número de prueba, y lo devuelve a Bot. |
| 20–28 | **Atención** | Qué es un caso, **Tomar → Resolver**. Qué significan **[ACCIÓN]** y **[FYI]** en el grupo. | Toma y resuelve el caso de ejemplo. |
| 28–33 | **Seguimientos y Citas** | A quién escribirle (no vino) y el calendario. Aclarar que no envía nada solo. | Mira un día del calendario. |
| 33–40 | **Recordatorios** | Prender/apagar, hora, **suspender un feriado**, adelantar. En vivo: llega el recordatorio al celular de prueba y se contesta **"Confirmo"**: se confirman los dos turnos juntos. | Suspende un día de prueba y lo vuelve a activar. |
| 40–50 | **Cambiar lo que Asiri dice** | **Conocimiento**: editar el horario, sumar una entrada para Asiri, las reglas de precios y datos de transferencia. **Asiri**: menú de bienvenida y notas de tono. | Edita un dato y lo deja como estaba. |
| 50–55 | **Si algo no anda** | Control (interruptor de emergencia), reconectar el WhatsApp por QR, `/bot off` para administradores. Capítulo 8 del manual. | — |
| 55–60 | **Ayuda con IA** | Mostrar `DIAGNOSTICO_IA.md` y cómo se le pide a una IA que revise un problema (capítulo 9 del manual). Quién guarda el documento de accesos. | — |

## Cosas para decir en voz alta (para que quede grabado)
1. *"Asiri no da consejos médicos ni agenda sin que el paciente diga que sí."*
2. *"Cuando una persona de la clínica escribe desde el celular, Asiri se calla en ese chat."*
3. *"Por WhatsApp Asiri solo dice el precio de la consulta; todo lo demás lo informa la secretaria."*
4. *"Si hay una urgencia, Asiri avisa al grupo: hay que contestar rápido."*
5. *"Nada se pierde: los avisos quedan como casos en Atención."*
6. *"Si algo raro pasa, no lo borren: copien el mensaje, el número y la hora."*

## Decisiones que hay que llevar a la Dra. (anotar la respuesta en el momento)
- [ ] **Cambios y cancelaciones a menos de 48 horas:** hoy Asiri **deriva** a la secretaria. ¿Quieren que pueda cancelar o reprogramar, o se mantiene la derivación?
- [ ] **Menú de bienvenida:** ¿se usa el estándar o quieren uno propio?
- [ ] **Textos de Seguimientos:** revisar los mensajes sugeridos para pacientes que no vinieron.
- [ ] **Quién administra el sistema** a partir de febrero (usuarios del panel, documento de accesos, a quién llamar).
- [ ] **Migración al servidor propio de la clínica:** ¿cuándo y quién la autoriza?
- [ ] **Datos de pacientes de Dentalink / historias clínicas:** solo con contrato firmado y definición de qué se guarda.

## Después de la reunión (Lucas)
- [ ] Subir la grabación a donde la Dra. arme su manual (con el índice de minutos de la tabla de arriba).
- [ ] Anular las citas de prueba y limpiar el número de prueba (`scripts/limpiar_numero_demo.py`).
- [ ] Entregar el documento de accesos **cifrado** y confirmar quién lo guarda.
- [ ] Anotar las decisiones en `memory/decisions.md` y en `memory/open-questions.md`.
