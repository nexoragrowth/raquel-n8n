# Router y conversación multi-turno del v6 (`workflows/current/v6_LIVE.json`, 125 nodos) — lectura para diseñar el seguimiento del triaje

Archivo analizado: `c:/Users/not/Desktop/proyectos/raquel-n8n/workflows/current/v6_LIVE.json` (solo lectura, parseado con Python; no se hizo ningún GET/PUT a la API). Contexto leído: `.claude/CLAUDE.md`, `memory/decisions.md` (3 entradas 2026-09-02), `memory/current-state.md` (sesión 2/9 cont.), `docs/architecture.md` (Human Takeover / Auto Reactivar), snapshot `workflows/history/HelperNotify_POST_fix_ruido.json` (workflow `Helper - Notify Grupo`, el que llama `escalar_a_secretaria`).

Nota de credenciales: `Gate Humano Final` (v6) y `Chatwoot Apply` (Helper Notify) tienen un token de Chatwoot hardcodeado en el JS; `Evolution - Typing`, `Evolution API - Enviar Mensaje`, `Re-check Humano` y `Existe paciente?` tienen apikey/token en headers/params. Valores omitidos en todo este informe.

---

## 0. Camino completo de un mensaje entrante (orden real por conexiones)

```
Webhook - Evolution API (POST /webhook/evolution-v2, webhookId evo-webhook-v2)
 → Webhook Validator → Kill-switch Check → Es comando admin? [out1=no]
 → Redis GET bot:status → Bot enabled? [out0=sí] → Redis GET dentalink:status → Dentalink up? [out0=sí]
 → Rate Limit Prep → Rate Limit INCR → Rate Limit Eval → Rate Limit OK? [out0=ok]
 → Edit Fields - Extraer Datos  ──(en paralelo)──> Get Paciente Context (sin salida main)
 → Es fromMe? [out0=fromMe → Build fromMe AI memory → Postgres - Save fromMe → CW Search Contact … → CW Set Label humano]
             [out1=no fromMe → Filtrar duplicados y basura]
 → Switch - Tipo Mensaje  out0 audio → Evolution API - Obtener Media → Convert to File → OpenAI - Transcribir Audio → Set Marker Audio
                          out1 image → Evolution API - Obtener Imagen → Convert Imagen to File → OpenAI - Analizar Imagen (gpt-4o) → Set Marker Imagen
                          out2 documento → Set Marker Documento
                          out3 otros (video/sticker/ubicación/contacto) → Set Marker Otros
                          out4 text → Set Passthrough Texto
 → Merge Multimedia (5 inputs) → [rama A] Buffer: Push Mensaje   (Redis RPUSH lista chat_buffer:<phone>)
                              → [rama B] Buffer: Wait 10s (amount=22 → espera 22 s) → Buffer: Leer Lista → Soy el ultimo?
                                   [out1=no → Descartar (no soy ultimo)]  [out0=sí → Preparar Mensaje Final]
 → Build Router Context (Postgres: ctx de n8n_chat_histories) → Buffer: Limpiar (DEL lista)
 → Existe paciente? (Chatwoot contactSearch por phone) → Chatwoot - Buscar Conversacion → Verificar Label Humano → Bot Activo?
      [out0 = hasHumanoLabel=true → Humano Atendiendo (no hacer nada)]   ← SILENCIO TOTAL, no llega al Router
      [out1 → Check Session Age → Handle Stale Session → Clear Old Memory (borra memoria si >7 días)]
 → Pre-filtro Cierre → Es cierre? [out0 skip=true → Set NO_REPLY → Fallback Output] [out1 → Router - Clasificar Intent]
 → Parse Intent → Get KB Horarios y Precio → Extraer Horarios y Precio → Switch sobre Intent
      out0 confirmar → Sub-Agent Confirmar
      out1 cancelar  → Execute Sub-WF Cancelar (5cAWJxiWJ50hxEq3) → Format Sub-WF Output
      out2 urgencia  → Sub-Agent Urgencia
      out3 agendar   → Sub-Agent Agendar
      out4 general / out5 fallback → Sub-Agent General
 → Fallback Output → Canned Sidecar → Gate Pago Tratamiento → Banlist Validator
 → Re-check Humano → Hay humano ahora? → Humano aparecio? [out0 → Aviso humano tomo chat (fin)] [out1 → Necesita Formatting?]
 → Necesita Formatting? [out0 (len>80 y no NO_REPLY) → Formatting Agent - WhatsApp] [out1 → Split en Mensajes]
 → Split en Mensajes (split por '---') → Gate Error Tecnico → Tiene respuesta?
      [out1 contiene [NO_REPLY] → PG - Delete NO_REPLY → Descartar [NO_REPLY]]
      [out0 → Loop Mensajes (batch 1) → Evolution - Typing → Gate Humano Final → Evolution API - Enviar Mensaje (POST /send/text {number,text}) → Loop Mensajes …]
```

(`Es primer mensaje?` y `Delay Humano` quedaron huérfanos: nadie entra a `Es primer mensaje?`. `Banlist Validator` también sale en paralelo a `Banlist Shadow - Prep` → `Banlist Shadow - LLM` → `Banlist Shadow - Log`, solo logging.)

---

## 1. Router

### 1.1 `Router - Clasificar Intent` (`@n8n/n8n-nodes-langchain.agent` v2.2)

- Entradas: `Es cierre?` main out1; LM `Router LM` (ai_languageModel). **Sin memoria, sin tools, sin output parser.** Salida: `Parse Intent`.
- `promptType: define`. `text` (user prompt) exacto:

```
CONTEXTO DE LA CONVERSACION (ultimos turnos, mas recientes al final):
{{ $('Build Router Context').first().json.ctx || '(sin contexto)' }}

MENSAJE ACTUAL DEL PACIENTE:
{{ $('Preparar Mensaje Final').first().json.text }}
```

- **`options.systemMessage` COMPLETO (citado textual):**

```
SCOPE DEL BOT (MUY IMPORTANTE - LEELO PRIMERO):
El bot SOLO existe para 5 funciones operativas concretas. Si el mensaje NO entra claramente en una de ellas, devolver `silencio` (en este Router devolves `consulta_general` y el Sub-Agent General se encarga del [NO_REPLY]).

Las 5 funciones validas:
1. AGENDAR turno nuevo (frases tipo "quiero/queria turno", "necesito consulta", "primera vez", "agendarme")
2. CONFIRMAR/CANCELAR/REPROGRAMAR turno existente (con NOTA INTERNA en memoria O referencia explicita a un turno suyo)
3. COMPROBANTE de pago (mensaje con marker [DOCUMENTO]/[IMAGEN] mostrando monto + banco + destinatario)
4. URGENCIA concreta (dolor especifico, alambre/bracket roto, sangrado, hinchazon - palabras concretas, no genericas)
5. CONSULTA INFO PUNTUAL (precio de consulta, direccion clinica, horarios, alias bancario - pregunta directa)

NO ENTRAN (devolver consulta_general para que se silencie):
- Saludos sueltos sin pedido ("hola", "buenas tardes", "como estas")
- Preguntas conversacionales ("como va?", "todo bien?")
- Frases ambiguas con numeros sin contexto ("buenas $9100", "tengo 30")
- Reclamos vagos sin info concreta
- Mensajes random fuera de tema (alguien contandote algo personal, etc.)
- Cualquier mensaje que no sea operativo en una de las 5 cajas

REGLA: ante DUDA, devolver `consulta_general`. El bot NO es onboarding ni recepcionista vacia. Iri saluda y filtra el primer contacto humano. El bot solo entra cuando el pedido es CLARO.

---

Sos un clasificador de intents para un bot conversacional de la clinica de la Dra. Raquel Rodriguez (Ortodoncia, Jujuy).

CONTEXTO DE CONVERSACION (LEELO PRIMERO, ES OBLIGATORIO):
Antes de clasificar, mira la memoria reciente:
1. Cual fue tu ULTIMO mensaje AI? (que pediste, que prometiste)
2. ¿Estas en mitad de un flujo? (te dijeron "asisto al turno", "queria un turno", "necesito cancelar")
3. ¿La respuesta del paciente es la INFO QUE PEDISTE en tu mensaje anterior?

REGLA DE ORO DE CONTINUACION:
**Si tu ultimo AI estaba en flujo X y pediste info al paciente, la respuesta del paciente con esa info SIGUE estando en flujo X. NO cambies de intent.**

EXCEPCION A LA CONTINUACION (CAMBIO DE TEMA):
Si en medio de un flujo operativo el paciente pregunta sobre INFO CANNED basica (alias bancario, horarios de la clinica, direccion, precio de consulta, forma de pago) -> ABANDONAR la continuacion y devolver `consulta_general`. El paciente cambio de tema, no esta respondiendo a tu pregunta del flujo anterior.

Ejemplos:
- AI previo: "Que dia preferis para reprogramar?" en flujo CANCELAR -> "antes de eso, me pasas el alias?" -> intent = `consulta_general` (NO cancelar_o_reprogramar).
- AI previo: "Para reservar necesito tu DNI" en flujo AGENDAR -> "donde queda la clinica?" -> intent = `consulta_general`.
- AI previo: "Que dia preferis?" en flujo CANCELAR -> "el viernes" -> intent = `cancelar_o_reprogramar` (continuacion legitima).

**EXCEPCION A LA EXCEPCION (NUEVO 2026-08-21, caso real Salvador Mayans / reproduccion 21-08) — el mensaje trae AMBAS COSAS A LA VEZ**: si el mensaje del paciente incluye LA INFO QUE PEDISTE en tu ultimo mensaje (nombre+DNI, eleccion de dia/slot, confirmacion de fecha, cual turno cancelar, etc.) Y ADEMAS pregunta algo de INFO CANNED (precio, obra social, alias, horarios) EN EL MISMO MENSAJE, NO abandones la continuacion. El paciente no cambio de tema: esta completando el flujo Y preguntando algo extra al mismo tiempo. Mantene el intent operativo del flow activo (agendar_nuevo / cancelar_o_reprogramar / confirmar_post_recordatorio) -- el sub-agent operativo ya sabe responder la info canned ADEMAS de ejecutar la accion pendiente, en la misma respuesta. Solo abandonar a consulta_general cuando la pregunta de info canned es LO UNICO que trae el mensaje, sin la info pedida.

Ejemplo real que fallo: AI previo (Agendar) "Para registrarlo y reservar el turno, me pasa el nombre completo y DNI del paciente?" + paciente "Si, el paciente es Test Prueba, DNI 99999999. Cual es el valor de la consulta? Reciben instituto de seguros?" -> el mensaje TRAE el nombre+DNI pedido (continuacion legitima) ADEMAS de 2 preguntas de info canned -> intent = `agendar_nuevo` (NO consulta_general). El Router lo mando mal a consulta_general -> Sub-Agent General respondio SOLO el canned de obra social y el turno JAMAS se registro/reservo en Dentalink, dejando al paciente creyendo que tenia turno.

Ejemplos criticos:
- AI previo: "Para confirmarlo, me podes pasar nombre completo y DNI?" en flujo CONFIRMAR -> respuesta del paciente "Maria Laredo 36182735" -> intent = `confirmar_post_recordatorio`. NO `agendar_nuevo`.
- AI previo: "Que dia preferis?" en flujo AGENDAR -> "viernes a la mañana" -> intent = `agendar_nuevo`.
- AI previo: "Confirmas que cancele el turno X?" en flujo CANCELAR -> "si, dale" -> intent = `cancelar_o_reprogramar`.
- AI previo: "lo paso a la secretaria Irina" -> respuesta corta del paciente ("ok", "gracias", "te veo el jueves") -> intent = `consulta_general` (donde el sub-agent decide NO_REPLY).

Si la memoria esta vacia o el ultimo AI fue un saludo generico, clasificar segun el mensaje del paciente directamente.

**EXCEPCION SECUNDARIA — PREGUNTAS DENTRO DEL MISMO FLOW OPERATIVO:**

La regla "PREGUNTA != ACCION" (mas abajo, regla 0) NO aplica cuando la pregunta es CONTINUACION del flow ya activo. Si el ultimo AI fue una respuesta de un sub-agent operativo (Agendar/Cancelar/Confirmar) y el paciente pregunta sobre algo del MISMO dominio, sigue siendo el mismo intent.

Casos concretos:

- **Flow AGENDAR activo** (ultimo AI: ofrecio slots / pidio fecha-franja / pidio DNI / confirmo pre-reserva) + paciente pregunta sobre **disponibilidad de horarios o fechas** ("que fechas tenes disponibles?", "hay para la tarde?", "tienen para manana?", "que horarios hay el [dia]?", "se puede el [fecha]?", "hay alguno mas tarde?", "que tenes para mas adelante?") -> intent = `agendar_nuevo` (CONTINUACION, NO consulta_general).

- **Flow CANCELAR activo** (ultimo AI: ofrecio slots de reprogramacion / pregunto que turno cancelar) + paciente pregunta sobre **fechas o disponibilidad** ("que dia tenes libre?", "hay para martes?") -> intent = `cancelar_o_reprogramar` (CONTINUACION).

- **Flow CONFIRMAR activo** + paciente pregunta sobre el turno ("a que hora era?", "que dia es?") -> intent = `confirmar_post_recordatorio` (CONTINUACION).

- **CLARIFICACION SOBRE LO QUE EL BOT ACABA DE PEDIR (caso comun, NO mandar a consulta_general)**: si el ultimo AI fue un sub-agent operativo (Agendar/Cancelar/Confirmar) PIDIENDOLE INFO al paciente (ej "para quien es el turno?", "DNI?", "que dia preferis?", "a nombre de quien?", "que turno cancela?") y el paciente devuelve una PREGUNTA CLARIFICATORIA en vez de la info pedida (ej "a que personas?", "que opciones?", "que dias hay?", "como?", "cuales son?", "no entiendo"), MANTENE el mismo intent del flow activo. El sub-agent operativo es quien tiene las tools + el contexto en memoria (las fichas devueltas, los slots ofrecidos, etc.) para responder esa clarificacion. Si lo mandas a consulta_general no tiene como responder y termina escalando.

Ejemplo real (1/6): bot (Agendar) "Con este numero tengo registrada a mas de una persona. Para quien es el turno? Paseme nombre y apellido del paciente." + paciente "A que personas?" -> intent = `agendar_nuevo` (CONTINUACION clarificatoria). El Sub-Agent Agendar lista las fichas devueltas por buscar_paciente_dentalink.

EJEMPLOS REALES (incidente 27/05 18:26):
- AI previo (Agendar): "Los proximos cupos: 4 de junio a las 10 de la manana, 18 de junio a las 10..." + paciente: "El 30 de junio?" -> `agendar_nuevo` (continuacion).
- AI previo (Agendar): "Para el martes 30 de junio no tengo turnos. Los mas cercanos: 18 jun 10AM, 19 jun 10:30AM..." + paciente: "O digame que fechas tiene disponibles por la tarde?" -> `agendar_nuevo` (continuacion — pregunta sobre slots dentro de flow agendar, NO consulta_general).
- AI previo (Agendar): "Le confirmo: martes 4 de junio a las 10. Procedo?" + paciente: "Si" -> `agendar_nuevo`.

CLAVE: las PREGUNTAS QUE SON DEL DOMINIO DEL SUB-AGENT ACTIVO siguen en su flow. Solo cambia a consulta_general si la pregunta es sobre INFO CANNED (alias, horarios de la clinica, direccion, precio de consulta, forma de pago) o un tema completamente fuera del flow.

5 INTENTS posibles:
- urgencia_dolor
- confirmar_post_recordatorio
- cancelar_o_reprogramar
- agendar_nuevo
- consulta_general

REGLAS DE PRIORIDAD:

**0. REGLA ABSOLUTA — PREGUNTA != ACCION (LEELA ANTES QUE TODO LO DEMAS):**
Si el mensaje del paciente es una PREGUNTA, NUNCA lo clasifiques como accion ejecutable (confirmar/cancelar/reprogramar/agendar). Las preguntas son consultas de informacion.

Senales de pregunta:
- Termina con "?" o "¿".
- Empieza con palabra interrogativa: cuando, cuándo, que, qué, a que hora, dónde, donde, como, cómo, cual, cuál, quien, quién.
- Frases tipo: "tengo turno el [fecha]?", "es el [fecha]?", "puedo cancelar?", "se puede mover?", "podria reprogramar?", "hay forma de pasarlo?".

Para preguntas sobre turnos propios del paciente -> `cancelar_o_reprogramar` (el sub-WF las maneja como consulta_info, NO ejecuta accion).
Para preguntas sobre info de la clinica/tratamientos -> `consulta_general`.

ATENCION ESPECIAL — discriminar "tengo turno" segun forma:
- "tengo turno el viernes" (afirmativo, sin ?) -> puede ser confirmar (paciente confirmando)
- "tengo turno el viernes?" (con ? o tono pregunta) -> consulta_info -> `cancelar_o_reprogramar`
- "¿tengo turno?" (pregunta) -> consulta_info -> `cancelar_o_reprogramar`

**1. urgencia_dolor — MAXIMA PRIORIDAD**
Cualquier mencion de: dolor, muela, alambre, brackets, sangrado, hinchazon, pedido de medicacion ("que tomo", "que pastilla").

**1.5. AVISO DE LLEGADA / EN CAMINO (PRIORIDAD ALTA - pedido Dra 2026-06-19, caso Catalina) -> consulta_general:**
Si el paciente avisa que esta YENDO o YA LLEGO al consultorio (no pide nada, solo informa que esta en camino, cerca o en la puerta), clasifica SIEMPRE `consulta_general` (el Sub-Agent General lo silencia con [NO_REPLY]). NUNCA `cancelar_o_reprogramar` ni `confirmar_post_recordatorio`.
Frases gatillo (lista abierta, usa criterio): "estoy llegando", "llegando", "ya llegue", "ya llego", "ya estoy aca/aqui/ahi", "estoy en la puerta", "estoy abajo", "subiendo", "en camino", "voy en camino", "estoy yendo", "yendo para alla", "estoy a [N] cuadras", "a dos cuadras", "ya estoy cerca", "estoy cerca".
Esta regla MANDA sobre los emojis de confirmacion: "Estoy llegando 🙏" -> `consulta_general` (NO confirmar, aunque traiga 🙏/👍).
EXCEPCION (NO confundir con confirmacion de asistencia futura): "voy", "ahi voy", "ahi estare", "alli estare", "voy a ir" SIN "en camino"/"llegando"/"ya estoy" en respuesta a un recordatorio = confirmacion -> `confirmar_post_recordatorio`. Solo es aviso de llegada cuando el paciente esta FISICAMENTE yendo/llegando AHORA. Si hay dolor/urgencia, urgencia_dolor manda.

**2. confirmar_post_recordatorio**
AFIRMACION DE ASISTENCIA: si el ultimo AI fue un recordatorio (empieza con "AUREA" o contiene "Le recordamos su turno con la Dra. Rodriguez Raquel") Y el paciente responde con CUALQUIER expresion afirmativa de que va a ir al turno, intent = `confirmar_post_recordatorio`. La lista de senales es ABIERTA — usa criterio: cualquier dicho que indique afirmacion o asistencia entra aca.

Senales explicitas (ejemplos, NO limitativos):
- Confirmacion directa: "confirmo", "si confirmo", "confirmado", "confirmamos", "le confirmo", "te confirmo".
- Verbos de asistir: "asisto", "asisto al turno", "asistire", "asistiré", "asistimos", "asistiremos", "voy a asistir", "vamos a asistir".
- Verbos de ir / presencia: "voy", "vamos", "alli voy", "alli vamos", "ahi voy", "ahi vamos", "ahi estare", "ahi estoy", "ahi estamos", "ahi vamos a estar", "presente", "presentes".
- Afirmaciones generales (en contexto post-recordatorio): "si", "sí", "siii", "si si", "sisi", "si dale", "si claro", "ok", "okey", "dale", "claro", "claro que si", "obvio", "obviamente", "perfecto", "joya", "genial", "listo", "todo bien", "todo ok".
- EMOJIS REACCIONES (NUEVO 2026-06-03 pedido Dra): si el paciente responde SOLO con un emoji afirmativo (sin texto adicional) en contexto post-recordatorio, ES confirmacion. Incluye: 👍 (pulgar arriba), 👌 (OK), ✅ ☑️ (check), 🙏 (manos oracion), ❤️ 💙 💚 🧡 💛 (corazones), 🤝 (apreton de manos), 😊 ☺️ 🙂 (sonrisas), 💯 (cien). Estos emojis SOLOS post-recordatorio = confirmar_post_recordatorio (NO los confundas con CIERRES_CONVERSACIONALES del header — los cierres aplican solo cuando NO hay accion pendiente; en contexto post-recordatorio HAY accion pendiente = confirmar el turno).
- Verbos de tener turno: "tengo turno con raquel", "tengo el turno", "tengo turno", "tenemos turno".
- Negaciones que son afirmacion: "no falto", "no faltamos", "no nos perdemos", "seguro que si".

REGLA DE ORO en contexto post-recordatorio: ante DUDA entre confirmar y otra cosa, elegi `confirmar_post_recordatorio` (el bot lo va a confirmar si el turno existe; si no, escala). NUNCA clasifiques como `cancelar_o_reprogramar` salvo que haya senal CLARA de cancelar/reprogramar/no poder ir.
- COMPROBANTE (PRIORIDAD sobre la regla de continuacion): [DOCUMENTO] o [IMAGEN] que contenga "TIPO: COMPROBANTE" o las palabras "comprobante", "transferencia", "monto", "BBVA", "Macro", "alias", "ARS $" -> SIEMPRE confirmar_post_recordatorio, INCLUSO si venis de un flujo agendar o cancelar. Un comprobante confirma un turno PRE-reservado; lo maneja el Sub-Agent Confirmar.
- TEXTO PEGADO DEL RECORDATORIO: si contiene "Le recordamos que el dia ... cita con la Dra. Rodriguez Raquel".

- **CONTINUACION**: si el ultimo AI pidio nombre+DNI/celular EN FLUJO CONFIRMAR, y el paciente lo pasa.

**3. cancelar_o_reprogramar**
Cualquier indicio de que el paciente quiere mover, cambiar, posponer o no asistir a un turno existente:
- Explicitos: "cancelar", "reprogramar", "anular", "suspender".
- Imposibilidad: "no puedo ir", "no voy a poder", "no llego", "no llegaria", "no me da", "no me da el tiempo", "voy a faltar", "ahi no llego", "no me cierra", "me queda lejos", "no me alcanza el tiempo".
- Cambio: "podemos pasarlo", "lo podemos mover", "lo podemos cambiar", "moverlo a otro dia", "pasarlo a otro dia/horario", "lo necesito mover".
- Conflicto de agenda: "tengo clases", "tengo trabajo", "tengo otro compromiso", "se me complico", "me surgio algo", "tengo que viajar".
- Pregunta sobre cambio: "se puede cambiar?", "habria forma de pasarlo?", "puedo moverlo?".

**IMPORTANTE**: este intent (cancelar_o_reprogramar) es SOLO para AFIRMACIONES claras de intencion de accion ("cancelo", "reprogramo", "lo paso para el [fecha]"). Cualquier mensaje con "?" o palabras interrogativas (puedo, podria, se puede, hay forma, cuando, que dia, etc) -> consulta_general (NO cancelar_o_reprogramar). El paciente tiene que afirmar sin pregunta para que ejecutemos accion.
**CONTINUACION**: si el ultimo AI estaba en flujo cancelar/reprogramar y el paciente confirma, da fecha, elige slot, rechaza slot, o aclara cual turno -> sigue siendo cancelar_o_reprogramar.

**4. agendar_nuevo**
"queria sacar un turno", "primera vez", "necesito una consulta", "se puede agendar".
**CONTINUACION** (REGLA CRITICA, NUEVO 2026-06-03): si el flujo en curso ES agendar (ultimo AI fue Sub-Agent Agendar ofreciendo slot o haciendo read-back), TODO mensaje del paciente que sea aceptacion del slot, eleccion, confirmacion o info para registrar sigue siendo `agendar_nuevo`. Senales de ACEPTACION DE SLOT post-oferta (NO `consulta_general`):
- "dale", "dale vamos con ese", "dale ese", "vamos con ese", "ese", "ese mismo", "ese me sirve", "ese de las X", "el primero", "el de las X hs".
- "buenisimo", "buenisimo para ese dia", "perfecto", "perfecto ese", "joya", "listo".
- "si", "si por favor", "si dale", "ok", "okey", "claro", "ese si", "obvio".
- "confirmo", "confirmado", emoji solo 👍/✅/🙏 cuando hay slot ofrecido en memoria.
- "X a las HH" / "para ese dia entonces" / "queria ese de las X" / "el de manana" / "el de la tarde" (filtrando dentro de la oferta).
REGLA DE ORO: si el ultimo AI fue Sub-Agent Agendar y el paciente da CUALQUIER respuesta no-interrogativa, intent = `agendar_nuevo`. NO `consulta_general` salvo que el paciente cambie de tema explicito (precio, direccion, otra cosa no-turno).

**5. consulta_general (fallback Y preguntas)**
- Precios, direccion, horarios, alias bancario, info general de la clinica.
- TODAS las PREGUNTAS sobre turnos propios del paciente: "tengo turno?", "cuando es mi turno?", "que dia tengo?", "a que hora?", "tengo turno manana?", "es presencial?", "mi turno es el [fecha]?", "que turno tengo?".
- TODAS las PREGUNTAS de capacidad: "puedo cancelar?", "se puede mover?", "podria reprogramar?", "hay forma de cambiarlo?", "puedo agendar?".
- Preguntas generales sobre tratamientos / FAQ.
- Cierres / agradecimientos / mensajes post-escalacion.

El Sub-Agent General tiene tools de LECTURA (ver_turnos_paciente, buscar_conocimiento, obtener_historial_paciente). Para preguntas que requieren accion, responde confirmando capacidad e invita al paciente a afirmar sin pregunta.

DEVUELVE SOLO el string del intent. UNA palabra exacta. Sin explicacion, sin comillas.

---

SUB-AGENTS DISPONIBLES Y SUS RESPONSABILIDADES:

Cada intent que devolves se rutea a un sub-agent. Saber QUE puede hacer cada uno te ayuda a clasificar mejor.

- `confirmar_post_recordatorio` -> Sub-Agent Confirmar
  Hace: confirmar turnos (tras recordatorio). Tools Dentalink: ver_turnos_paciente, confirmar_turno.
  Detecta comprobantes y escala. Output: canned tras exito, o escalar.

- `cancelar_o_reprogramar` -> Sub-Agent Cancelar
  Hace: cancelar turnos con read-back. Tools: ver_turnos_paciente, cancelar_turno.
  Si quiere reprogramar, deriva a Agendar en proximo turno. Output: canned o escalar.

- `agendar_nuevo` -> Sub-Agent Agendar
  Hace: busqueda exhaustiva de paciente (5 variantes phone + apellido), crear si nuevo,
  buscar horarios, reservar. Tools: 6 de Dentalink. Output: turno PRE-reservado + mensaje pago.

- `urgencia_dolor` -> Sub-Agent Urgencia
  Hace: UNICAMENTE escalar. Prohibido dar consejos, recomendar medicacion, diagnosticar.
  Tool: escalar_a_secretaria. Output: canned escalacion.

- `consulta_general` -> Sub-Agent General
  Hace: info canned (precio/horario/direccion/alias), FAQ via Vector Store
  (23 docs sobre tratamientos/pagos/clinica), o escalar.
  Tools: buscar_conocimiento (KB), escalar_a_secretaria.

Tu decision de routing afecta que tools y conocimiento estan disponibles para responder
al paciente. Si dudas entre consulta_general y otro intent operativo claro -> elegi consulta_general.
```

**Lo que importa del prompt para el triaje:**
- La "REGLA DE ORO DE CONTINUACION" es genérica ("si tu ultimo AI estaba en flujo X y pediste info..."), pero TODAS las reglas de continuación explícitas (EXCEPCION SECUNDARIA, CLARIFICACION, CONTINUACION de cada intent) enumeran solo AGENDAR / CANCELAR / CONFIRMAR. **No existe ninguna regla de continuación para `urgencia_dolor`.**
- El único ejemplo post-escalación empuja al lado contrario: `AI previo: "lo paso a la secretaria Irina" -> respuesta corta del paciente ("ok", "gracias", "te veo el jueves") -> consulta_general`. Y en el intent 5: `Cierres / agradecimientos / mensajes post-escalacion` → consulta_general.
- `urgencia_dolor` es "MAXIMA PRIORIDAD" pero definido por lista de palabras: `dolor, muela, alambre, brackets, sangrado, hinchazon, pedido de medicacion ("que tomo", "que pastilla")` + scope 4 `alambre/bracket roto, sangrado, hinchazon`. "pincha", "cera", "pinza", "ligadura", "goma", "arco" NO figuran.
- Regla 0 "PREGUNTA != ACCION": una pregunta (termina en `?`) nunca es acción; "preguntas sobre info de la clinica/tratamientos -> consulta_general". La regla 0 no dice nada de urgencia, pero al no haber palabra-clave de urgencia, una pregunta cae en consulta_general.
- El bloque "SUB-AGENTS DISPONIBLES" le dice al Router que Urgencia "Hace: UNICAMENTE escalar" — el LLM sabe que mandar algo a `urgencia_dolor` = escalar, lo que sesga a NO usarlo cuando el paciente parece estar "bien" (p. ej. "ya me puse la cera").

### 1.2 `Router LM` (`lmChatOpenAi` v1.2)
- `model: gpt-5-mini`, `options: { reasoningEffort: "low" }`. **No hay `temperature`** configurada (la familia gpt-5 no la acepta), **no hay `responseFormat`/JSON ni output parser**: salida = texto libre, el prompt pide "UNA palabra exacta".

### 1.3 `Parse Intent` (Code v2) — código COMPLETO

```js
const valid = ['confirmar_post_recordatorio', 'cancelar_o_reprogramar', 'urgencia_dolor', 'agendar_nuevo', 'consulta_general'];
const out = ($input.first().json.output || '').trim().toLowerCase();
let intent = 'consulta_general';
for (const v of valid) {
  if (out.includes(v)) { intent = v; break; }
}
// Propagar text para que los sub-agents lo accedan via $json.text
const text = $('Preparar Mensaje Final').first().json.text;
return [{ json: { ...$input.first().json, intent, text } }];
```

- Intents existentes (5): `confirmar_post_recordatorio`, `cancelar_o_reprogramar`, `urgencia_dolor`, `agendar_nuevo`, `consulta_general`.
- Default: `consulta_general` (si el LLM devuelve vacío o algo que no contiene ningún intent).
- Parseo: no es JSON; `includes()` por substring sobre `output` en minúsculas, **primer match en el orden del array gana** (si el LLM escribiera "urgencia_dolor o consulta_general", gana `urgencia_dolor`; si escribiera "confirmar_post_recordatorio ... urgencia_dolor", gana confirmar).
- Campos que agrega: `intent` y `text` (texto mergeado de `Preparar Mensaje Final`), manteniendo `output` del Router. Aguas abajo, `Canned Sidecar` y `Gate Pago Tratamiento` leen `$('Parse Intent').first().json.intent` (passthrough exacto cuando `=== 'urgencia_dolor'`).

### 1.4 `Switch sobre Intent` (Switch v3.2) — entra desde `Extraer Horarios y Precio`
Reglas `={{ $json.intent }}` equals (strict, case sensitive): out0 `confirmar` → `Sub-Agent Confirmar`; out1 `cancelar` → `Execute Sub-WF Cancelar`; **out2 `urgencia` → `Sub-Agent Urgencia`**; out3 `agendar` → `Sub-Agent Agendar`; out4 `general` → `Sub-Agent General`; out5 `fallback` (fallbackOutput extra) → `Sub-Agent General`.

Entre `Parse Intent` y el Switch: `Get KB Horarios y Precio` (`SELECT id, contenido FROM knowledge_base WHERE id IN (20, 21) ORDER BY id;`) → `Extraer Horarios y Precio` (Code: `horarios` = contenido id 20 o fallback fijo; `precio_consulta` = primer `$[\d.,]+` del id 21 o `$50.000`; devuelve `{...$('Parse Intent').item.json, horarios, precio_consulta}`).

---

## 2. Contexto que ve el Router y memoria

### 2.1 `Build Router Context` (Postgres v2.5, executeQuery) — entra desde `Preparar Mensaje Final`, sale a `Buffer: Limpiar`
Query exacta:

```sql
SELECT COALESCE(string_agg(  CASE message->>'type'     WHEN 'human' THEN 'PACIENTE: '     WHEN 'ai' THEN 'BOT: '     ELSE 'SYSTEM: '   END || (message->>'content'),   E'\n---\n' ORDER BY id ASC), '(sin mensajes previos)') AS ctx FROM (  SELECT id, message FROM n8n_chat_histories   WHERE session_id = '{{ $json.phone }}'   AND (message->>'content') NOT IN ('agendar_nuevo', 'consulta_general', 'cancelar_o_reprogramar', 'confirmar_post_recordatorio', 'urgencia_dolor')   AND (message->>'content') NOT LIKE '[CONTEXTO%'   AND (message->>'content') != '[NO_REPLY]'   ORDER BY id DESC LIMIT 6) recent
```

- Fuente: tabla `n8n_chat_histories` (la misma que usa `Postgres Chat Memory`), `session_id = phone`.
- **Últimos 6 mensajes** (después de filtrar), re-ordenados ASC, formateados `PACIENTE: …` (type human) / `BOT: …` (type ai) / `SYSTEM: …` (otro), separados por `\n---\n`. Campo de salida: `ctx`. Si no hay filas: `(sin mensajes previos)`.
- Filtra: contenidos iguales a un nombre de intent (legado de cuando el Router tenía memoria), `[CONTEXTO%`, `[NO_REPLY]`.
- Los mensajes humanos del path fromMe (`Build fromMe AI memory`) se guardan con `type: 'ai'`, `additional_kwargs.source: 'wa_outbound'` y content prefijado `[ATENCION HUMANA - mensaje enviado por la doctora o la secretaria desde el WhatsApp del consultorio. NO es output tuyo, ...]: <texto>` → en el ctx aparecen como `BOT: [ATENCION HUMANA ...]: …`.
- Ese `ctx` entra al Router SOLO por expresión en `text`. El Router NO escribe en `n8n_chat_histories` (no tiene memoria conectada).
- Implicación: en un seguimiento de triaje, el ctx sería p. ej. `PACIENTE: se me salió el alambre y pincha\n---\nBOT: <canned de Urgencia o caption del video>`; ese caption es lo único que le dice al Router "estamos en flujo urgencia".

### 2.2 `Get Paciente Context` (Postgres v2.5) — entra desde `Edit Fields - Extraer Datos`, **sin salida main**
```sql
SELECT COALESCE(nombre,'') as nombre, COALESCE(resumen_clinico,'') as resumen_clinico, COALESCE(resumen_actualizado_at::text,'') as resumen_actualizado_at FROM pacientes WHERE telefono = $1 LIMIT 1;
```
`queryReplacement: ={{ $('Edit Fields - Extraer Datos').item.json.phone }}`. Tabla `pacientes` (Supabase v3). Se consume solo por expresión `$('Get Paciente Context')` en los systemMessage de `Sub-Agent Confirmar`, `Sub-Agent Cancelar` y `Sub-Agent Agendar` (resumen clínico del paciente). **Ni el Router, ni Urgencia, ni General lo usan.**

### 2.3 `Postgres Chat Memory` (`memoryPostgresChat` v1.3)
`sessionIdType: customKey`, `sessionKey: ={{ $('Preparar Mensaje Final').first().json.phone }}`, `contextWindowLength: 10`. Conectado (ai_memory) a los 5 sub-agents: Confirmar, Cancelar, Agendar, Urgencia, General. Es quien persiste el turno humano + la respuesta AI de cada sub-agent (incluido `[NO_REPLY]`, que luego borra `PG - Delete NO_REPLY` si la respuesta final fue NO_REPLY). El Sub-WF Cancelar no está en esta lista (tiene su propia memoria si la usa).

### 2.4 Memoria stale
`Check Session Age` (último id/created_at de `n8n_chat_histories` por phone) → `Handle Stale Session` (`is_stale_session = diffDays > 7`) → `Clear Old Memory` (`DELETE FROM n8n_chat_histories WHERE session_id = $1 AND $2::boolean = true AND COALESCE(message::jsonb->'additional_kwargs'->>'source','') NOT IN ('wa_outbound','human_takeover','reminder_note') RETURNING id`).

---

## 3. `Pre-filtro Cierre` (Code v2) → `Es cierre?` → `Set NO_REPLY`

Código COMPLETO de `Pre-filtro Cierre`:

```js
// Pre-filtro deterministico: solo filtros tecnicos/anomalos.
// Toda clasificacion CONVERSACIONAL (cierres, gracias, ok/dale/meta, etc.)
// se delega al Router LLM que tiene contexto de memoria.
//
// Mantiene:
//  - prompt_injection / autoresponder_externo / emoji_only -> skip:true (tecnicos)
//  - urgencias / afirmaciones-negaciones cortas / saludos / multimedia / pregunta
//    / confirmaciones whitelist -> skip:false (fast-path positivo, evita LLM)
//  - todo lo demas -> default_pass (Router decide)
//
// Historia: 27/05 - removidos 5 bloques skip:true conversacionales
// (termina_gracias, cierres_exactos, te_veo_dia, ok_plus_short, short_closing)
// porque mataban "Confirmamos turno gracias", "ok", "dale", "meta", etc.
// El Router LLM (gpt-5 main) ahora clasifica con memoria.

const text = ($('Preparar Mensaje Final').first().json.text || '').trim();
const stripAccents = s => s.normalize('NFD').replace(/\p{Diacritic}/gu, '');
const stripEmoji = s => s.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F000}-\u{1F02F}\u{1F0A0}-\u{1F0FF}\u{1F100}-\u{1F64F}\u{1F680}-\u{1F6FF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}‍️☺☹]/gu, '').replace(/\s+/g, ' ').trim();
const norm = s => stripAccents(stripEmoji(s)).toLowerCase().replace(/[!.,;:]+/g, '').trim();

const t = norm(text);
const tLen = text.length;

// === DETECTOR PROMPT INJECTION (silencia) ===
const injectionPatterns = [
  /ignor[ae]\s+(todas?\s+)?tus\s+(instrucciones|reglas)/i,
  /olvid[ae]?\s+(lo\s+que\s+|todas?\s+)?(te\s+dijeron|tus\s+instrucciones|tus\s+reglas)/i,
  /tus?\s+nuevas?\s+(reglas|instrucciones|directivas)\s+(son|es)/i,
  /de\s+ahora\s+en\s+m[áa]s\s+sos\s+(otro|un)/i,
  /actu[áa]\s+como\s+(otro|un|una)/i,
  /pretend[ée]\s+ser\s+/i,
  /modo\s+(developer|admin|dios|dios\s+mode|debug|sudo|root)/i,
  /\[admin\s*mode\]/i,
  /\[system\s*(override|mode|prompt)\]/i,
  /system\s+override/i,
  /(mostrame|repet[íi]|dame|pasame)\s+(tu|el)\s+(system\s+)?prompt/i,
  /(que|cuales)\s+(tools|herramientas)\s+(tenes|tienes)/i,
  /(api\s*key|api_key|apikey|credenciales)\s+(real(es)?|de\s+\w+)/i,
  /(decime|pasame|mostrame)\s+.*(api\s*key|credencial|token|secret)/i,
  /listado\s+(completo\s+)?(de\s+)?pacientes/i,
  /todos?\s+los\s+(pacientes|turnos|datos)/i,
  /cancel[áa]\s+todos?\s+los\s+turnos/i,
  /borr[áa]\s+(todo|todos)/i,
  /soy\s+(el\s+desarrollador|admin|administrador|developer|root)/i,
  /usuario\s+autorizado/i,
];
for (const pat of injectionPatterns) {
  if (pat.test(text)) {
    return [{ json: { skip: true, reason: 'prompt_injection:'+pat.source.slice(0,30), text, output: '[NO_REPLY]' } }];
  }
}

// === AUTORESPONDERS DE OTRAS CLINICAS / SAAS BOTS ===
const autoresponderPatterns = [
  /gracias por comunicarte con\s+\S/i,
  /gracias por (escribir|contactarnos|tu mensaje)\s/i,
  /este es un (mensaje|saludo) (automatico|automático)/i,
  /respuesta automatica|respuesta automática/i,
  /mensaje automatico recibido|mensaje automático recibido/i,
  /horario(s)? de atenci[oó]n.*(lunes|martes|miercoles|jueves|viernes)/i,
  /a la brevedad le responderemos/i,
  /en breve nos comunicaremos/i,
  /instagram\.com\/od\.rodriguezraquel/i,
  /te\s+invitamos\s+a\s+seguirnos\s+en\s+instagram/i,
];
for (const pat of autoresponderPatterns) {
  if (pat.test(text)) {
    return [{ json: { skip: true, reason: 'autoresponder_externo:'+pat.source.slice(0,30), text, output: '[NO_REPLY]' } }];
  }
}

// === AFIRMACIONES/NEGACIONES CORTAS — pasar al Router (fast-path positivo) ===
const afirmaciones_cortas = [
  'si','sí','sii','siii','sis','sip','sipi','si si','sí sí','sip sip',
  'no','nop','nope','nono','no no',
  'claro','claro que si','claro que sí','obvio','obvio si','obvio sí',
  'exacto','correcto','asi es','así es','tal cual eso','tal cual ese',
  'ese','ese mismo','ese si','ese sí','ese era','ese mismo si','ese mismo sí',
  'eso','eso es','eso mismo','eso era',
  'si confirmo','sí confirmo','confirmo eso','confirmo ese',
  'no era','no era ese','ese no','no ese'
];
if (afirmaciones_cortas.includes(t)) {
  return [{ json: { skip: false, reason: 'afirmacion_negacion_corta', text } }];
}

// === SALUDOS — pasar ===
const saludos = ['hola','holaa','holaaa','holis','buenas','buen dia','buenos dias','buenas tardes','buenas noches','que tal','como va','como andas','que onda'];
if (saludos.includes(t)) {
  return [{ json: { skip: false, reason: 'saludo_inicial', text } }];
}

// === URGENCIAS — pasar (defensive, leccion Mariela 09/05) ===
const urgenciaWords = ['dolor','duele','duela','muela','alambre','bracket','arco','sangrado','hinchazon','hinchada','no aguanto','urgent','infeccion','fiebre','golpe','accidente','rompi','pincha','pinchando','medicacion','que tomo','que tomar','que pastilla','pastilla','pastillas','ibuprofeno','paracetamol','antibio'];
for (const w of urgenciaWords) {
  if (t.includes(w)) return [{ json: { skip: false, reason: 'urgencia', text } }];
}

// === MULTIMEDIA markers — pasar ===
if (text.includes('[DOCUMENTO') || text.includes('[IMAGEN') || text.includes('[AUDIO')) {
  return [{ json: { skip: false, reason: 'multimedia_marker', text } }];
}

// === Pregunta — pasar ===
if (text.includes('?')) {
  return [{ json: { skip: false, reason: 'tiene_pregunta', text } }];
}

// === Confirmaciones cortas — pasar al sub-agent ===
const confirmaciones = ['confirmo','si confirmo','confirmado','confirmamelo','dale confirmo','ahi estare','ahi voy','voy','voy a ir','asisto','confirmo doctora','confirmo dra','confirmo gracias','si voy','si asisto'];
if (confirmaciones.includes(t) || confirmaciones.some(c => t === 'si ' + c || t.endsWith(' ' + c))) {
  return [{ json: { skip: false, reason: 'confirmacion_post_recordatorio', text } }];
}

// === Emoji-only — descartar (anti garbage tecnico) ===
if (stripEmoji(text).length === 0 && tLen > 0) {
  return [{ json: { skip: true, reason: 'emoji_only', text, output: '[NO_REPLY]' } }];
}

// === Default: pasar al Router LLM, que decide con memoria ===
return [{ json: { skip: false, reason: 'default_pass', text } }];
```

- **Lo único que corta ANTES del Router** (`skip: true`): prompt injection (20 regex), autoresponders externos (10 regex), emoji-only. Todo lo demás pasa (`skip:false`). `[VIDEO]`/`[STICKER]` no están en la lista de markers pero pasan igual por `default_pass`.
- `Es cierre?` (If v2): `{{ $json.skip }}` is true → out0 `Set NO_REPLY` (Set: `output = "[NO_REPLY]"`) → `Fallback Output`; out1 → `Router - Clasificar Intent`.
- **El campo `reason` (p. ej. `urgencia`) NO se usa aguas abajo**: el Router recibe solo `ctx` + `text`; la lista `urgenciaWords` es un fast-path sin efecto sobre la clasificación. (Además `t.includes(w)` es substring: `arco` matchea "marco/barco", `duela` matchea cualquier palabra que la contenga.)

---

## 4. Entrada, multimedia y buffer

### 4.1 `Edit Fields - Extraer Datos` (Set v3.4)
Campos: `phone` (primer JID `@s.whatsapp.net` entre Info.Chat/Sender/RecipientAlt/SenderAlt, sin sufijo `:device`), `phone_last10`, `remoteJid` (Info.Chat), `name`/`pushName` (Info.PushName), `key_id` (Info.ID), `text` (conversation || extendedTextMessage.text || imageMessage.caption || videoMessage.caption || documentWithCaptionMessage…caption || documentMessage.caption || ''), `image_url` ('image' si MediaType=image), `image_mime`, `audio_url` ('audio'|'ptt'), `instance`, `fromMe` (Info.IsFromMe), `document_url`, `document_filename`, `document_mime`, `video_url` ('video' si MediaType=video), `sticker_present`, `location_lat/lng`, `contact_name/vcard`, `message_type` (Info.Type).

### 4.2 `Filtrar duplicados y basura` (Code v2) — código completo
```js
const input = $input.first().json;

const text = input.text || '';
const imageUrl = input.image_url || '';
const audioUrl = input.audio_url || '';
const docUrl = input.document_url || '';
const videoUrl = input.video_url || '';
const sticker = input.sticker_present === true;
const locLat = input.location_lat || '';
const contactName = input.contact_name || '';
const remoteJid = input.remoteJid || '';

if (input.fromMe === true || input.fromMe === 'true') return [];
if (remoteJid.includes('@g.us')) return [];
if (remoteJid === 'status@broadcast') return [];
if (!remoteJid) return [];

const hasContent =
  text.trim() !== '' ||
  imageUrl !== '' ||
  audioUrl !== '' ||
  docUrl !== '' ||
  videoUrl !== '' ||
  sticker ||
  locLat !== '' ||
  contactName !== '';

if (!hasContent) return [];

return [{ json: { ...input, dedup_passed: true } }];
```
No hay dedup por key_id real (el nombre engaña): descarta fromMe, grupos (`@g.us`), `status@broadcast`, sin remoteJid, sin contenido. **Un mensaje del grupo de derivaciones nunca entra** (relevante si el triaje quisiera escuchar respuestas de la doctora en el grupo).

### 4.3 Markers multimedia (lo que el Router "ve" cuando llega media)
- `Set Marker Audio`: `text = '[AUDIO] ' + transcripción`.
- `Set Marker Imagen`: `text = '[IMAGEN] ' + salida de OpenAI - Analizar Imagen + ('\nCaption del paciente: ' + caption si hay)`. **`OpenAI - Analizar Imagen` corre gpt-4o vision sobre TODA imagen entrante** y devuelve `TIPO: COMPROBANTE|FOTO_DENTAL|OTRO / MONTO / DESTINATARIO / FECHA / HORA / DESCRIPCION`; para FOTO_DENTAL: "Describi lo que ves clinicamente (brackets, caries, inflamacion, etc) - NO diagnostiques, solo describi". Esa descripción entra al Router y al sub-agent como texto, y queda en memoria.
- `Set Marker Documento`: `[DOCUMENTO: <filename> (<mime>)]` + `\nCaption: …`.
- `Set Marker Otros`: `[VIDEO]` / `[STICKER]` / `[UBICACION: lat,lng]` / `[CONTACTO: nombre]` + ' ' + caption. **Un video del paciente NO se analiza**: el Router ve literalmente `[VIDEO] <caption>`.
- `Set Passthrough Texto`: `text` tal cual.

### 4.4 Buffer de burbujas
- `Merge Multimedia` (Merge v3, 5 inputs) → en paralelo: **`Buffer: Push Mensaje`** (Redis `push`, `tail:true`, lista `'chat_buffer:' + phone`, valor `JSON.stringify({key_id, text: $json.text || ''})`) y **`Buffer: Wait 10s`** (Wait v1.1, **`amount: 22`** → espera 22 s, el nombre está desactualizado).
- `Buffer: Leer Lista` (Redis `get`, `keyType: list`, key `'chat_buffer:' + phone`, propertyName `messages`).
- `Soy el ultimo?` (If v2.2): `JSON.parse($json.messages.last()).key_id` equals `$('Edit Fields - Extraer Datos').first().json.key_id`. Solo la ejecución cuyo key_id es el último de la lista sigue; las demás → `Descartar (no soy ultimo)`.
- `Preparar Mensaje Final` (Code v2) — código completo:
```js
const original = $('Edit Fields - Extraer Datos').first().json;
const messages = $('Buffer: Leer Lista').first().json.messages || [];

const parts = [];
for (const msg of messages) {
  try {
    const parsed = JSON.parse(msg);
    if (parsed.text && parsed.text.trim() !== '') parts.push(parsed.text);
  } catch (e) {
    // legacy/unparseable: tratar como texto plano si tiene contenido
    if (typeof msg === 'string' && msg.trim() !== '' && msg !== '[MEDIA:audio]') parts.push(msg);
  }
}

const fullText = parts.join('\n').trim();

return [{
  json: {
    phone: original.phone,
    remoteJid: original.remoteJid,
    name: original.name,
    key_id: original.key_id,
    instance: original.instance || '',
    text: fullText
  }
}];
```
  **Separador de merge: `'\n'`** (una burbuja por línea, en orden de llegada). **Campo final con el texto mergeado: `text`** de `Preparar Mensaje Final` (`$('Preparar Mensaje Final').first().json.text`), que es lo que leen el Router (`text`), Parse Intent, los 5 sub-agents (`text`), Canned Sidecar, Gate Pago Tratamiento, Banlist y el Sub-WF Cancelar. Otros campos: `phone`, `remoteJid`, `name`, `key_id`, `instance`.
- `Buffer: Limpiar` (Redis `delete` de `chat_buffer:<phone>`) corre DESPUÉS de `Build Router Context`.
- Consecuencia para el triaje: "no me sirvió" + "sigue pinchando" mandados en <22 s llegan como UN texto `"no me sirvió\nsigue pinchando"` y se clasifican una sola vez; una foto + texto en ventana corta llegan como `"[IMAGEN] TIPO: FOTO_DENTAL ...\nme pincha el alambre"`.

### 4.5 Gate humano antes del Router
`Existe paciente?` (Chatwoot contactSearch) → `Chatwoot - Buscar Conversacion` → `Verificar Label Humano` (busca `labels.includes('humano')` en las conversaciones del contacto; si el HTTP falló, `hasHumanoLabel:false`) → `Bot Activo?` → si hay label: `Humano Atendiendo (no hacer nada)`. **Mientras la conversación tenga label `humano`, ningún mensaje del paciente llega al Router.**

---

## 5. Evaluación concreta de los 6 mensajes de seguimiento

### 5.1 Premisa que cambia todo: hoy, después de una urgencia, el seguimiento NO llega al Router
`Sub-Agent Urgencia` llama `escalar_a_secretaria` → `POST https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo?phone=<phone>&resumen=...` → workflow `Helper - Notify Grupo`: `Webhook` → `Log Escalacion` (INSERT en `escalaciones_log`: telefono, motivo=resumen, origen='bot', exec_id) → `Silencioso?` → (no silencioso) `Notify Grupo Send` → `Chatwoot Apply`; (silencioso) `Chatwoot Apply` directo. **`Chatwoot Apply` aplica `POST /conversations/{id}/labels {labels:['humano']}` en TODOS los casos.** El label lo quita `Auto Reactivar` (`fosfga62zNaN0qrx`, corre cada 15 min, criterio 1 h sin actividad humana) o marcar `resolved` en Chatwoot (`docs/architecture.md`, `docs/runbook.md`).
→ En el v6 actual, "no me sirvió", "sigue pinchando", etc. enviados después de la escalación terminan en `Humano Atendiendo (no hacer nada)`: silencio, sin log, sin Router. El prompt de Urgencia lo asume: `Si el paciente insiste tras escalar -> el label humaño ya esta aplicado. Devolver [NO_REPLY]`.
→ La evaluación de abajo aplica al **escenario del triaje con video (sin escalación previa, sin label)** o a un seguimiento que llega después de que Auto Reactivar levantó el label. Historial supuesto en ctx: `PACIENTE: <urgencia, ej. "se me salió el alambre y me pincha">` / `BOT: <caption del video o canned>`.

### 5.2 Tabla

| Mensaje | Pre-filtro Cierre (`reason`) | Intent probable hoy (Router) | Adónde cae y qué pasa |
|---|---|---|---|
| "no me sirvió" | `default_pass` (sin keyword; "no" solo está en la lista, la frase no) | **`consulta_general`** (alta prob.): "Reclamos vagos sin info concreta → consulta_general", "ante DUDA consulta_general", ejemplo post-escalación "respuesta corta → consulta_general". Sin regla de continuación de urgencia. Podría salir `urgencia_dolor` solo si el LLM infiere del ctx. | Sub-Agent General: puede (a) escalar por "Queja / reclamo" (PASO 2), (b) `[NO_REPLY]` por VALIDACION DE DESTINO/SCOPE, o (c) PASO 3 → `buscar_conocimiento` y responder. No determinístico. Si por el contrario va a Urgencia: su VALIDACION DE DESTINO dice "Si NO hay señales claras [de dolor/sangrado] → [NO_REPLY]" → riesgo de SILENCIO en vez de re-escalar. |
| "sigue pinchando" | `urgencia` (substring `pincha`) — sin efecto aguas abajo | **`urgencia_dolor`** (prob. media-alta): "pincha" no está en la lista de la regla 1, pero el scope 4 dice "alambre/bracket roto" y el ctx menciona alambre. Depende del LLM, no de una regla. | Sub-Agent Urgencia → `escalar_a_secretaria` + canned "Recibimos tu mensaje. Le pasamos a la doctora para que le coordine lo antes posible." (comportamiento deseado, pero por inferencia). |
| "listo gracias ya me puse la cera" | `default_pass` | **`consulta_general`**: intent 5 "Cierres / agradecimientos / mensajes post-escalacion"; ejemplo "ok/gracias → consulta_general". | Sub-Agent General → CIERRES CONVERSACIONALES → `[NO_REPLY]` → `PG - Delete NO_REPLY`. Correcto para el paciente, pero **la señal "resuelto con video" se pierde** (no queda en `escalaciones_log` ni en `triaje_urgencias_log`). |
| "no tengo cera" | `default_pass` | **Ambiguo, sesgo a `consulta_general`** (sin keyword de urgencia; sin regla de continuación). `urgencia_dolor` posible si el LLM lee el ctx. | Si General: PASO 3 ("cuidados, recomendaciones… → OBLIGATORIO PRIMERO buscar_conocimiento… responder parafraseando los docs") → puede improvisar ("consígala en farmacia", "use algodón") o escalar con "Eso lo evalúa la Dra. Raquel en consulta. Le paso a la secretaria." Si Urgencia: VALIDACION DE DESTINO → posible `[NO_REPLY]` (no hay dolor explícito). |
| "y si no tengo pinza?" | `tiene_pregunta` (`?`) | **`consulta_general`** (alta prob.): regla 0 "PREGUNTA != ACCION… preguntas sobre info de la clinica/tratamientos -> consulta_general"; "pinza" no es keyword de urgencia. | Sub-Agent General → PASO 3 → `buscar_conocimiento` → respuesta LLM. **Riesgo alto de consejo operativo** ("puede usar una pinza de cejas limpia", "empuje el alambre con la goma de un lápiz"): el Banlist NO cubre "use/pruebe/coloque/empuje/corte/pinza/cera" (solo `guardá`, `traé`, `tomá + dosis`, `sacá la/el`, `aplicá`, `enjuagá`, "venite", "los esperamos", "no te preocupes", "no es grave", "Balcarce 37"). |
| "me duele mucho igual" | `urgencia` (`duele`) | **`urgencia_dolor`** (alta prob.): regla 1 "dolor". | Sub-Agent Urgencia → escalar + canned. Es la red flag "dolor intenso" del diseño (Capa 3) y hoy sale bien. |

### 5.3 ¿Hay regla de "continuación" que mantenga el intent anterior?
- Sí para **agendar / cancelar / confirmar** (REGLA DE ORO DE CONTINUACION + EXCEPCION SECUNDARIA + CLARIFICACION + CONTINUACION por intent). **No para urgencia**: la palabra "urgencia" aparece en el prompt solo en el scope (4), la regla 1 (keywords), 1.5 ("Si hay dolor/urgencia, urgencia_dolor manda") y la ficha del sub-agent ("UNICAMENTE escalar").
- La REGLA DE ORO genérica ("si tu ultimo AI estaba en flujo X y pediste info, la respuesta con esa info SIGUE en flujo X") podría aplicar si el bot del triaje HACE una pregunta guiada (p. ej. "¿El alambre se salió del último bracket?") y el paciente responde ("sí, del último") — pero eso depende de que el LLM generalice "flujo X" a urgencia, sin ejemplo que lo respalde, y con el ejemplo contrario post-escalación empujando a consulta_general.
- Determinístico hoy NO hay nada: ni el Pre-filtro ni Parse Intent miran el intent previo; `Build Router Context` no marca "flujo activo" (solo texto plano). El intent anterior no se persiste en ningún lado (los outputs del Router se filtran del ctx por legado).

---

## 6. Sub-Agent General, Urgencia, Sidecar, Gate, Banlist, salida

### 6.1 `Sub-Agent General` (agent v2.2; LM `LM Sub-Agent General` gpt-5-mini reasoningEffort low; memoria `Postgres Chat Memory`; tools `buscar_conocimiento`, `escalar_a_secretaria`, `buscar_paciente_dentalink`, `ver_turnos_paciente`, `obtener_historial_paciente`; input `text = {{ $('Preparar Mensaje Final').first().json.text }}`; entra por Switch out4 y out5).

Cómo usa `buscar_conocimiento` (citas textuales del systemMessage):
- ORDEN DE DECISION: `PASO 2. ¿Es escalación DIRECTA sin pasar por KB? (queja/hostilidad/urgencia/factura/disponibilidad de doctora/personal/obra social). → escalar_a_secretaria + canned. Fin.`
- `PASO 3. CUALQUIER OTRA pregunta sobre la clínica, tratamientos, cuidados, recomendaciones, dudas, edades, materiales, procedimientos, dolor, alimentación, deportes, higiene → **OBLIGATORIO PRIMERO**: llamar buscar_conocimiento con la pregunta del paciente. NO escalar antes de llamar la tool. NO asumir que la KB no tiene la info. - Si la tool retorna docs relevantes → responder con esa info (máx 2-3 oraciones, parafraseando los docs, NO inventar). Fin. - Si la tool retorna [] o nada relevante → recién ahí escalar con canned: "Eso lo evalúa la Dra. Raquel en consulta. Le paso a la secretaria."`
- `REGLA ABSOLUTA: ANTES DE LLAMAR escalar_a_secretaria sobre tema clínico/tratamiento/cuidado, SIEMPRE llamar buscar_conocimiento primero. Si saltás este paso, fallas el protocolo. La KB tiene 50+ docs, probablemente la respuesta está ahí.`
- Ejemplos que el prompt manda a KB: "puedo hacer deporte con brackets?", "duele ponerse brackets?", "cómo se cuidan los brackets?".
- Tool `buscar_conocimiento`: `vectorStoreSupabase` v1.3, `mode: retrieve-as-tool`, tabla `knowledge_base`, `queryName: match_documents`, embeddings `Embeddings OpenAI` (default). `toolDescription`: `"Base de conocimiento de la clinica Aurea: FAQ, tratamientos, pagos, horarios, info general de la clinica y la doctora. NO usar para urgencias o protocolos medicos. Si la consulta del paciente NO matchea con info aca -> el agente debe escalar con escalar_a_secretaria."` (advertencia, no gate).

Reglas del prompt que PROHÍBEN improvisar consejos (existen, pero son prompt-only):
- R0: `NO conversas, NO opinas, NO consolas, NO sugeris, NO recomendas, NO interpretas sintomas, NO das diagnosticos, NO das instrucciones operativas, NO improvisas.`
- REGLAS: `NO dar opiniones sobre tratamientos ("es lo mejor", "te conviene", "duele poco").` y `NUNCA inventar info. Si la KB no la tiene → escalar.`
- SCOPE COMERCIAL: "OPERACIÓN SENSIBLE: urgencia" está dentro del scope → NO devuelve `[NO_REPLY]` por scope; y "dudas de paciente" también.
- VALIDACION DE DESTINO (General): `tu funcion es info canned (...) Y consultas read sobre turnos del paciente. Si el paciente claramente esta accionando (agendar/cancelar/confirmar) → [NO_REPLY]` — no menciona urgencia como motivo de `[NO_REPLY]`.
- `obtener_historial_paciente` — CUANDO NO LLAMARLA: `Es una urgencia inmediata (dolor, sangrado) -> escalar directo, no perder tiempo en historial.`
- Riesgo neto: un seguimiento de triaje sin palabra de dolor ("no tengo cera", "y si no tengo pinza?") cae en PASO 3 (KB + parafraseo LLM), no en PASO 2, y el único freno determinístico es el Banlist, que no cubre ese vocabulario.

### 6.2 `Sub-Agent Urgencia` (agent v2.2; LM `LM Sub-Agent Urgencia` gpt-5-mini low; memoria; única tool `escalar_a_secretaria`; input `text` mergeado)
Función (cita): `**Sub-Agent Urgencia — funcion unica: ESCALAR** Tu unica funcion es derivar el caso a la doctora. No conversas, no diagnosticas, no das consejos (ni siquiera paliativos como cera o enjuagues), no recomendas medicacion. PASOS OBLIGATORIOS: 1. Llamar escalar_a_secretaria con query = resumen breve (1-2 oraciones) del caso. (...) 2. Responder al paciente EXACTAMENTE: "Recibimos tu mensaje. Le pasamos a la doctora para que le coordine lo antes posible." PROHIBIDO ABSOLUTO: - Dar cualquier consejo médico u operativo (cera, enjuagues, "evita masticar") - Recomendar medicacion o dosis - Diagnosticar - Conversar mas alla del canned. Si el paciente insiste tras escalar -> el label humaño ya esta aplicado. Devolver [NO_REPLY].` + `REGLA CRITICA - UNA SOLA ESCALACION POR TURNO`. Header compartido con VALIDACION DE DESTINO: `Si sos Sub-Agent Urgencia: validá señales claras de urgencia/dolor/sangrado. Si NO hay señales claras → [NO_REPLY]`.
Es el único nodo del v6 que menciona "cera" (como prohibición). Ningún nodo menciona "pinza" ni envía video.

### 6.3 `Canned Sidecar` (Code v2, entre `Fallback Output` y `Gate Pago Tratamiento`)
Qué hace: lee el texto real del paciente (`Preparar Mensaje Final.text`), lo parte por líneas y oraciones, y si alguna oración es un PEDIDO (`/\?|\bpasame\b|\bme pasas\b|…|\bcuanto\b|\bcomo hago\b|\bque alias\b|\bpor favor\b|\bme gustaria\b/`) y no un YA_HECHO (`/\bya (transfer|pagu|abon|deposit|hice)|\bsigue siendo\b|\bes ese\b|…/`) y matchea una regla habilitada — `pago` (alias/cbu/cvu/transferencia/…; yaRespondido `/dra\.raquel\.aurea|\bCBU\b/i`) o `precio` (`/\b(precio|valor|costo|arancel)\b|cuanto (sale|cuesta|es|vale|debo|tengo que|hay que)/`; yaRespondido `/\$\s?\d/`; `supersededBy: 'pago'`); `horarios` está `enabled:false` — ANEXA al `output` el bloque canned (`output.trim() + '\n---\n' + …`) y marca `canned_sidecar`. Nunca modifica lo generado. Passthrough si `output` vacío o contiene `[NO_REPLY]`.
Cita clave para el triaje: `// --- 4. urgencias: nunca meter info comercial en un flujo de dolor --- let intent = ''; try { intent = ($('Parse Intent').first().json.intent || '').toString(); } catch (e) { intent = ''; } if (intent === 'urgencia_dolor') return items;`
Precio dinámico desde `$('Extraer Horarios y Precio').first().json.precio_consulta` (fallback `$50.000`); alias/CBU hardcodeados idénticos al prompt de General.

### 6.4 `Gate Pago Tratamiento` (Code v2, entre `Canned Sidecar` y `Banlist Validator`)
Qué hace: si alguna oración del texto real del paciente matchea `TEMA_TRATAMIENTO = /\btratamientos?\b|\bcuotas?\b|\bbrackets?\b|\bortodoncia\b|\balineadores?\b|\binvisalign\b|\baparatos?\b|\bfrenillos?\b/` Y `PAGO = /\b(abon(ar|o|e|amos)?|pag(ar|o|u[eé]|amos)?|transfer(ir|encia|encias)?|deposit(ar|o)?|planes? de pago|se[ñn]a)\b/` en la MISMA oración → **REEMPLAZA** el output por `'El pago del tratamiento lo coordina directamente la Dra. Raquel. Le paso su consulta para que se comunique con usted.'`, hace `POST notify-grupo` (sin `silencioso` → aplica label humano) y marca `gate_pago_tratamiento: true`. Dedup solo si el output ya es exactamente ese canned. Passthrough en `[NO_REPLY]` y, cita: `if (intent === 'urgencia_dolor') return items;`.
Nota para el triaje: "brackets"/"aparato" están en TEMA; un seguimiento tipo "se me despegó el bracket, ¿lo pago aparte?" que fuera mal ruteado a General dispararía este gate (escalación de pago en vez de urgencia). Con intent `urgencia_dolor` el gate no toca nada.

### 6.5 `Banlist Validator` (Code v2) — patrones completos (regex, `why`)
`\bven[íi](te)?\b`; `\bveng(a|an|amos)\b`; `\b(los|las|te|le|la|lo|los?\s+espera|las?\s+espera)\s*esperamos\b`; `\bte\s+esper(amos|amos\s+a|an)\b`; `\b(la|lo)\s+esperamos\b`; `\bsalgan?\s+(ya|ahora|para)\b`; `\b(ven[íi]|vengan)\s+ahora\s+mismo\b`; `\bahora\s+mismo\b.{0,50}\b(cl[íi]nica|consultorio|aurea|áurea)\b`; `\blo\s+antes\s+posible\b.{0,50}\b(cl[íi]nica|consultorio|aurea|áurea|venir)\b`; `\bguard(á|a|alo|enlo|en|amos|en\s+la)\s+`; `\btraig(a|an|alo|anlo|amos|an\s+(el|la|los|las))\b`; `\btra(é|e)\s+(el|la|los|las|tu)`; `\btom(á|a|alo|en|amos)\s+(\d|un|una|el|la|los|las|cada)`; `\bsac(á|a|alo|en|amos)\s+(la|el)`; `\baplic(á|a|ate|en|ense)\b`; `\benjuag(á|a|ate|en|ense)\b`; `\bno\s+te\s+preocup(es|és)\b`; `\bno\s+es\s+(nada\s+)?grave\b`; `\b(qu[ée]\s+macana|qu[ée]\s+embromado|qu[ée]\s+l[áa]stima)\b`; `\bbalcarce\s*(n[º°]?\s*)?37\b` (se saltea si el paciente pidió dirección). Si dispara → output = `'Recibimos tu mensaje. Estamos derivando tu caso a la Dra. Raquel para que te responda personalmente por este chat. Disculpa la demora.'`, `banlist_triggered`, `escalate_to_human: true` (no llama a notify-grupo por sí mismo). Solo mira `$input.first()` (un item).
Importante para el triaje: un caption canned que diga "colocá cera", "coloque un poco de cera", "probá con una pinza", "empuje el alambre" **NO** dispara el Banlist; pero uno que diga "aplicá cera" o "sacá el alambre" o "guardá el bracket" **SÍ** (y reemplazaría el caption por el canned de derivación). El caption tiene que testearse contra estas regex (patrón `tests/test_canned_sidecar.py`, que ejecuta el JS real).

### 6.6 Salida de texto — no hay camino para media
- `Necesita Formatting?` (If v2): `output.length > 80` AND no contiene `[NO_REPLY]` → `Formatting Agent - WhatsApp` (agent v1.8, LM `OpenAI Chat Model1` gpt-5-mini low). Su prompt reescribe (`Reemplazá ** por *`, elimina `¿ ¡`, "NO uses Dale", split por `---` solo para datos copiables, `NO modifiques contenido ni significado. NO agregues texto nuevo.`) — es un LLM en el camino de cualquier texto >80 chars; un caption canned largo pasa por acá y puede ser retocado (tono, signos).
- `Split en Mensajes`: parte por `---`; guard determinístico solo para CBU perdido. Emite `{message, remoteJid, phone, partIndex, totalParts}`.
- `Gate Error Tecnico`: regex `/agent stopped|max iterations|cannot read property|NodeOperationError|undefined is not/i` → canned + notify-grupo.
- `Tiene respuesta?`: `message` notContains `[NO_REPLY]` → `Loop Mensajes` (batch 1) → `Evolution - Typing` (`POST https://evo.raquelrodriguez.com.ar/message/presence`, apikey presente valor omitido) → `Gate Humano Final` (re-check label vía Chatwoot con token hardcodeado, valor omitido; fail-open) → `Evolution API - Enviar Mensaje` (`POST https://evo.raquelrodriguez.com.ar/send/text`, body `{"number": remoteJid solo dígitos, "text": message}`) → vuelve a `Loop Mensajes`.
- **No existe ningún nodo que llame `/send/media`.** El envío del video del triaje necesita un nodo nuevo (o `this.helpers.httpRequest` dentro de un Code, como hacen `Gate Pago Tratamiento`/`Gate Humano Final`) fuera del pipeline de texto, y ese envío quedaría FUERA de `Gate Humano Final`/`Re-check Humano` salvo que se replique el chequeo.

---

## 7. Helper - Notify Grupo (workflow externo, snapshot `HelperNotify_POST_fix_ruido.json`)
Nodos: `Webhook` (POST `/webhook/notify-grupo`, responseMode lastNode) → `Log Escalacion` (Postgres insert `escalaciones_log`: `telefono = query.phone||body.phone`, `motivo = query.resumen||body.text||'sin resumen'`, `origen='bot'`, `exec_id`) → `Silencioso?` (query/body `silencioso` notEquals `'true'`) → out0 `Notify Grupo Send` (nodo Evolution API, manda al grupo) → `Chatwoot Apply`; out1 (silencioso) → `Chatwoot Apply` directo. `Chatwoot Apply` busca contacto por phone, toma la primera conversación y hace `POST …/conversations/{id}/labels {labels:['humano']}` — siempre. Comentario en el código: `// SAFE: solo aplica label humano, NO crea messages`.
Consecuencia: **cada `escalar_a_secretaria` (y cada Gate que llama notify-grupo) = fila en `escalaciones_log` + label humano = bot mudo en ese chat hasta Auto Reactivar (1 h sin humano) o `resolved`.** El triaje "sombra" ya lee `escalaciones_log` (workflow `Gm7ofyGohOJ2bI44`), así que la "Capa 6 registro" del diseño puede colgarse de este mismo INSERT, pero si el video NO escala no habrá fila acá (habría que loguear aparte, p. ej. `triaje_urgencias_log`).


## KEY FACTS
- El Router ('Router - Clasificar Intent', agent v2.2, LM gpt-5-mini reasoningEffort low, sin temperature ni JSON) NO tiene memoria ni tools: ve solo ctx (Build Router Context) + text (Preparar Mensaje Final) y devuelve texto libre; Parse Intent lo mapea por substring en orden confirmar_post_recordatorio > cancelar_o_reprogramar > urgencia_dolor > agendar_nuevo > consulta_general, default consulta_general.
- Build Router Context = ultimos 6 mensajes de n8n_chat_histories (session_id=phone) formateados 'PACIENTE: '/'BOT: '/'SYSTEM: ' separados por '\n---\n', excluyendo contenidos iguales a un intent, '[CONTEXTO%' y '[NO_REPLY]'. Los mensajes humanos del path fromMe aparecen como 'BOT: [ATENCION HUMANA ...]: ...'. Postgres Chat Memory (window 10, sessionKey phone) solo esta conectada a los 5 sub-agents.
- El prompt del Router tiene reglas de continuacion explicitas SOLO para agendar/cancelar/confirmar; no hay ninguna para urgencia_dolor, y el unico ejemplo post-escalacion ('lo paso a la secretaria' + 'ok/gracias') manda a consulta_general. urgencia_dolor se define por keywords (dolor, muela, alambre, brackets, sangrado, hinchazon, medicacion) — 'pincha', 'cera', 'pinza', 'ligadura' no figuran.
- Pre-filtro Cierre solo corta (skip:true) prompt injection, autoresponders externos y emoji-only. Su lista urgenciaWords (incluye pincha/pinchando/arco/golpe/fiebre) es un fast-path cuyo campo reason NO se usa aguas abajo: no influye en la clasificacion.
- Buffer: Merge Multimedia -> Buffer: Push Mensaje (Redis RPUSH chat_buffer:<phone> de {key_id,text}) y en paralelo Buffer: Wait 10s (amount=22 -> 22 s reales) -> Buffer: Leer Lista -> Soy el ultimo? (key_id del ultimo item == mio) -> Preparar Mensaje Final une las burbujas con '\n' en el campo text (+ phone, remoteJid, name, key_id, instance) -> Build Router Context -> Buffer: Limpiar. Varias burbujas en <22 s se clasifican como un solo mensaje.
- Hoy, tras una urgencia, el seguimiento NO llega al Router: Sub-Agent Urgencia llama escalar_a_secretaria -> Helper Notify Grupo aplica label 'humano' en Chatwoot en TODOS los casos (silencioso o no) -> Verificar Label Humano / Bot Activo? -> 'Humano Atendiendo (no hacer nada)'. El label lo quita Auto Reactivar (1 h sin humano, corre cada 15 min) o resolved en Chatwoot. Toda escalacion tambien inserta en escalaciones_log (origen 'bot').
- Evaluacion de los 6 seguimientos en el escenario video (sin label): 'me duele mucho igual' -> urgencia_dolor (keyword dolor) y 'sigue pinchando' -> probable urgencia_dolor (por inferencia del ctx, no por regla); 'listo gracias ya me puse la cera' -> consulta_general -> [NO_REPLY] (se pierde la senal 'resuelto'); 'no me sirvió' y 'no tengo cera' -> ambiguos con sesgo a consulta_general; 'y si no tengo pinza?' -> consulta_general por regla 0 (pregunta) -> Sub-Agent General PASO 3 buscar_conocimiento -> riesgo de consejo operativo del LLM.
- Sub-Agent General: R0 prohibe 'NO sugeris, NO recomendas, NO interpretas sintomas, NO das instrucciones operativas, NO improvisas' pero PASO 3 ordena para 'cuidados, recomendaciones, dolor, higiene' llamar buscar_conocimiento (vectorStoreSupabase sobre knowledge_base, match_documents) y 'responder parafraseando los docs'; la descripcion de la tool ('NO usar para urgencias o protocolos medicos') es advisory. Ambas reglas viven solo en prompt.
- Canned Sidecar (anexa alias/precio si el paciente lo pidio) y Gate Pago Tratamiento (reemplaza por canned de coordinacion + notify-grupo si tratamiento/cuota/brackets/aparato + pagar en la misma oracion) hacen passthrough exacto cuando $('Parse Intent').first().json.intent === 'urgencia_dolor' y cuando output contiene [NO_REPLY].
- Banlist Validator (21 regex) no cubre vocabulario del triaje: 'cera', 'pinza', 'colocá', 'probá', 'usá', 'empujá', 'cortá' pasan; en cambio 'aplicá', 'sacá la/el', 'guardá', 'traé', 'tomá <dosis>', 'enjuagá', 'venite', 'los esperamos', 'ahora mismo ... clinica' disparan y reemplazan la respuesta por el canned de derivacion. Un caption canned del video debe testearse contra estas regex.
- Todo output >80 chars sin [NO_REPLY] pasa por Formatting Agent - WhatsApp (LLM gpt-5-mini) antes de Split en Mensajes (split por '---'); el unico guard deterministico es el de CBU. El envio es exclusivamente POST /send/text ({number,text}) en Evolution API - Enviar Mensaje: no hay ningun nodo que use /send/media en el v6.
- Toda imagen entrante pasa por OpenAI - Analizar Imagen (gpt-4o vision) y entra al Router/sub-agent/memoria como '[IMAGEN] TIPO: FOTO_DENTAL ... DESCRIPCION: <descripcion clinica>' + caption; un video del paciente entra como '[VIDEO] <caption>' sin analisis. Get Paciente Context (pacientes.resumen_clinico) solo lo usan Confirmar/Cancelar/Agendar por expresion.
- Sub-Agent Urgencia (unica tool escalar_a_secretaria, memoria compartida) es el unico nodo del v6 que menciona 'cera' (como prohibicion: 'no das consejos (ni siquiera paliativos como cera o enjuagues)'); su VALIDACION DE DESTINO devuelve [NO_REPLY] si 'NO hay senales claras' de dolor/sangrado, y 'Si el paciente insiste tras escalar -> [NO_REPLY]'.

## RISKS
- Sin regla determinística de 'flujo urgencia activo', el seguimiento post-video depende 100% del LLM del Router: 'no me sirvió' / 'no tengo cera' pueden ir a consulta_general (y de ahí a KB+LLM o a [NO_REPLY]) en vez de re-escalar. La Capa 5 del diseño ('no funcionó reescala de verdad') hoy no está garantizada por ninguna capa.
- 'y si no tengo pinza?' y similares (preguntas sin keyword de dolor) caen por regla 0 en consulta_general -> Sub-Agent General PASO 3 -> buscar_conocimiento -> el LLM parafrasea docs de la KB o improvisa un consejo operativo; el Banlist no cubre 'use/pruebe/coloque/empuje/pinza/cera' -> misma clase de falla que el incidente Mariela, en el área que el diseño quería blindar.
- Si un seguimiento SÍ va a urgencia_dolor pero sin palabra de dolor ('no me sirvió'), la VALIDACION DE DESTINO de Sub-Agent Urgencia ('Si NO hay señales claras → [NO_REPLY]') puede producir silencio en vez de escalación: el paciente queda sin respuesta después de haber probado el video.
- Si el triaje se inserta reusando escalar_a_secretaria/notify-grupo para el aviso pasivo (Decisión 2), el Helper aplica label 'humano' siempre -> el bot se enmudece y ninguna respuesta a la pregunta guiada llegará al Router. Hace falta un camino de log/aviso que NO aplique el label (hoy incluso silencioso:'true' lo aplica).
- El buffer (22 s, join '\n') puede fusionar la respuesta a la pregunta guiada con otro mensaje ('no, del medio\nme duele mucho') en un solo texto: el gate de red flags debe evaluar por oración/línea y una red flag debe ganar (Capa 3), pero el Router clasifica UNA sola vez por texto mergeado.
- Los captions canned del video pasan por Formatting Agent (LLM) si superan 80 chars y por Banlist: verbos como 'aplicá', 'sacá el', 'guardá', 'tomá' disparan el Banlist y reemplazan el caption por el canned de derivación; el Formatting Agent puede retocar tono/signos. Hay que testear el caption exacto contra Banlist (tests/test_canned_sidecar.py como patrón) y, si posible, enviarlo por un camino que no pase por el Formatting Agent.
- No existe nodo de envío de media: el video tiene que salir por un Code con this.helpers.httpRequest a /send/media o un nodo nuevo, fuera del pipeline Loop Mensajes -> Gate Humano Final; ese envío quedaría sin el re-check de label humano salvo que se replique, y sin registro en memoria (n8n_chat_histories) salvo que se inserte a mano -> el Router no vería 'BOT: <caption>' en el ctx y perdería la única pista de flujo urgencia.
- 'listo gracias ya me puse la cera' termina en [NO_REPLY] (y PG - Delete NO_REPLY borra la fila): la señal 'resuelto' no queda en ningún log; la Capa 6 (registro con tipo + video + severidad) necesita persistir aparte (triaje_urgencias_log) porque escalaciones_log solo se escribe cuando hay notify-grupo.
- Parse Intent matchea por substring con orden fijo: si el Router devuelve texto con más de un intent (p. ej. 'urgencia_dolor / consulta_general'), gana el primero del array (confirmar > cancelar > urgencia > agendar > general); si se agrega un intent nuevo para el triaje hay que tocar Parse Intent, Switch sobre Intent (índices de salida) y los passthrough de Canned Sidecar / Gate Pago Tratamiento que comparan contra el string exacto 'urgencia_dolor'.
- Gate Pago Tratamiento incluye 'brackets' y 'aparato' en TEMA_TRATAMIENTO: un seguimiento mal ruteado a General que mencione pagar + bracket ('se me despegó el bracket, ¿lo pago aparte?') dispara una escalación de pago (con label humano) en lugar de urgencia.
- Vision ya corre sobre toda imagen (OpenAI - Analizar Imagen, gpt-4o) y su descripción clínica entra al Router y a la memoria: la Decisión 1 ('foto sin vision, solo respaldo') no refleja el pipeline actual; si el paciente manda la foto pedida, el texto '[IMAGEN] TIPO: FOTO_DENTAL ...' se clasifica y persiste igual.

## OPEN QUESTIONS
- ¿El triaje con video se inserta como rama nueva entre Switch sobre Intent (out2) y Sub-Agent Urgencia (manteniendo intent 'urgencia_dolor' para que Sidecar/Gate hagan passthrough) o como intent nuevo? Lo segundo obliga a tocar Parse Intent, Switch y los dos gates.
- ¿Cómo se marca 'flujo triaje activo' de forma determinística para el turno siguiente (Redis key tipo triaje:<phone> con TTL, o fila abierta en triaje_urgencias_log), para no depender de que el Router LLM infiera continuación de urgencia desde el ctx?
- ¿Se agrega al prompt del Router una regla de continuación URGENCIA (AI previo = caption del video / pregunta guiada -> cualquier respuesta no-cierre sigue en urgencia_dolor) como segunda capa, además del gate determinístico?
- ¿El envío del video se persiste en n8n_chat_histories (INSERT manual tipo 'ai' con source propio) para que Build Router Context muestre 'BOT: <caption>'? Sin eso el Router no ve el turno del bot.
- ¿El aviso pasivo (Decisión 2) va a un endpoint que NO aplique label humano (nuevo path en Helper Notify o INSERT directo en triaje_urgencias_log), dado que hoy notify-grupo siempre aplica el label, incluso con silencioso=true?
- ¿Qué pasa con 'listo gracias ya me puse la cera' / 'no tengo cera': se quiere que el bot responda (p. ej. ofrecer Opción 2 / indicar que hay cera en farmacias — hoy prohibido por R0 y por Urgencia) o que solo loguee y calle? El fraseo de la Opción 2 y de los cierres sigue pendiente de Raquel (open-questions.md).
- ¿Se verificó en vivo que Verificar Label Humano lee la conversación correcta cuando el contacto tiene varias (Chatwoot Apply etiqueta payload[0])? Afecta cuánto tarda en volver el bot tras una escalación real de urgencia.
- El caption canned del video: ¿va por el pipeline de texto (Formatting Agent + Banlist + Gate Humano Final) o como caption del /send/media? En el segundo caso hay que replicar Banlist y re-check humano a mano.