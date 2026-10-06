# Traspaso: panel "super WhatsApp Web" (para la otra IA / instancia)

**Fecha:** 2026-10-06 · **De:** Claude (sesión del bot v7) · **Repo del panel:** `C:\Users\not\Desktop\proyectos\nexora-whatsapp-agent` (Next.js 16, deploy manual con `bash deploy/redeploy.sh`, ver `.env.local` para variables; **nunca pegar secretos en el repo**)
**Pedido de Lucas:** el panel de conversaciones tiene que sentirse como WhatsApp Web: nombres consistentes, orden correcto, foto de perfil del contacto. "Quiero tener un super WhatsApp Web."

No hace falta tocar n8n ni el bot para nada de esto. Trabajar solo en el repo del panel.

## 1. Bug de nombres cruzados: causa encontrada (verificada leyendo el código)

En la captura de Lucas, el chat abierto (`/conversaciones/5493888529463`) muestra en el encabezado **"Gael Emmanuel Huanuco"**, y en la lista, para ese mismo celular, **"Yesica Graciela"** (con la hora y el preview del mismo chat). Es el mismo número con dos nombres.

- **Lista** (`lib/conversaciones-data.ts`, ~líneas 222-229): el "nombre de Dentalink" sale de `recordatorios_enviados.nombre_paciente`, el del **último recordatorio** mandado a ese teléfono (`nombreDentalinkByPhone`). Si el recordatorio fue para el hermano o para la mamá, ese es el nombre que aparece.
- **Chat** (`lib/chat-data.ts`, `fetchDentalink`, ~línea 110-142): el nombre sale de `client.pacientesByCelular(telefono)` (**primera ficha** de Dentalink que coincide con el celular).
- `displayName()` (`components/conversaciones/phone.ts`) aplica la misma prioridad (alias > Dentalink > pushName > ficha > teléfono) pero a **entradas distintas**, y por eso devuelve cosas distintas.
- Una familia comparte un celular: hay 1 contacto de WhatsApp (la mamá, con su pushName) y N fichas de pacientes (los hijos).

**Cómo arreglarlo bien (propuesta):**
1. **Una sola función de resolución de nombre** usada por lista, encabezado, dashboard y citas. Que reciba teléfono y devuelva `{ titulo, subtitulo, fichas[] }`.
2. Modelo mental de WhatsApp Web: el **título** es el *contacto* (alias puesto a mano > nombre de la agenda de WhatsApp/pushName > teléfono formateado). Los **pacientes** (fichas de Dentalink) van como **subtítulo o chips** ("Pacientes: Gael, Martina"), no como título. Si el celular tiene una sola ficha y no hay alias ni pushName, el título puede ser el nombre del paciente.
3. Cachear la lista de fichas por teléfono (una consulta por teléfono, no por poll) y compartirla entre lista y chat.
4. Test: para un teléfono con 2 fichas y un recordatorio al segundo, lista y encabezado muestran **el mismo título**.

## 2. Orden de los mensajes ("el mensaje se pone arriba cuando tiene que ir al revés")

**No lo pude reproducir mirando la captura** (en la captura el orden cronológico es correcto: 08:27 bot, 08:28 adjunto del staff, 08:28 staff, 08:29 staff). Necesito un ejemplo concreto de Lucas (captura de la lista Y del chat con el mensaje mal ubicado). Hipótesis a revisar:
- El chat mezcla 3 fuentes con relojes distintos: `conversaciones.timestamp` (lo copia el Logger cada 5 min; si el Logger usa la hora de copia y no la del mensaje, el orden se desfasa), `n8n_chat_histories.created_at` (hora de escritura en memoria) y `mensajes_entrantes_live.created_at`. Ver cómo se ordena y deduplica el hilo (`hilo` en `lib/chat-data.ts`, ~línea 290 en adelante) y qué timestamp gana cuando el mismo mensaje está en dos fuentes.
- La lista se ordena por `lastTs` (`lib/conversaciones-data.ts`): puede subir un chat por un mensaje interno ([NOTA INTERNA], marcadores del staff) que no debería mover la lista.

## 3. Foto de perfil (avatares como WhatsApp Web)

- Hoy hay iniciales sobre un círculo de color. Objetivo: la foto de perfil de WhatsApp del contacto, con las iniciales como respaldo.
- **Fuente:** el API de WhatsApp que usa la clínica es **Evolution GO** (`https://evo.raquelrodriguez.com.ar`, instancia `raquel`; el n8n ya le envía mensajes con `/send/text`, `/send/media`). **No verifiqué** el endpoint de foto de perfil: hay que confirmarlo en la documentación de Evolution GO (buscar "profile picture" / "avatar" / "user info"). Las URLs de foto de WhatsApp **vencen**, así que no se guardan tal cual.
- **Diseño recomendado:** un endpoint del servidor del panel (`/api/avatar/[telefono]`) que (1) mira un bucket privado de Supabase Storage `avatares` (clave = teléfono, con fecha de actualización); (2) si no hay o tiene > 7 días, pide la URL a Evolution, descarga la imagen y la guarda; (3) devuelve la imagen con cache HTTP; (4) si el contacto no tiene foto o Evolution falla, responde 404 y el componente muestra las iniciales. Nunca pedir a Evolution en cada render de la lista (120 chats): carga perezosa solo de los visibles y cache.
- Privacidad: bucket privado, servir solo a usuarios logueados del panel (`requireUser()`).

## 4. "Super WhatsApp Web": lista corta de lo que haría falta (priorizar con Lucas)

Nombres consistentes · foto de perfil · fijar/silenciar/archivar chats · búsqueda dentro del chat y en la lista · respuestas rápidas · etiquetas (ej. "modo humano", "pago pendiente") · indicador de "escribiendo…" y de entregado/leído (los ticks ya existen) · atajos de teclado. No construir todo: elegir con Lucas los 3 que más usa Irina.

## 5. Reglas del proyecto que aplican

- Repo y deploy propios del panel; **no mover** código al repo del bot. Deploy: `bash deploy/redeploy.sh` (build + swap en el VPS, config en `/opt/nexora-panel/.env.production`).
- Typecheck antes de deployar (`npx tsc --noEmit`) y probar en el navegador **antes** de decir que anda ("nunca afirmar que una feature funciona sin haber ejecutado el camino completo").
- Lo que el bot guarda: memoria en `n8n_chat_histories`, mensajes del paciente en vivo en `mensajes_entrantes_live`, `conversaciones` la copia el Logger cada 5 min. El modo humano se decide por `pacientes.human_takeover` + `human_takeover_at` (24 h): `lib/modo-humano.ts` (arreglado hoy, commit 8775272).
- Lucas pide que cada cambio significativo deje constancia en `memory/` del repo del bot (current-state / decisions).
