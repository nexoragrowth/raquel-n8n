# Agente orquestador ("v7 Cerebro Agente") — diseño

Estado: construido y probado en el repo (2/11/2026). **No está desplegado en n8n ni conectado a nada.** El cerebro vivo (`v7 Cerebro`, NBHzj8ar2XuSvyIY) no se tocó.

## Qué cambia

Hoy el orquestador es **una llamada a un modelo sin herramientas** que devuelve un JSON de pasos; el código llama a los 4 sub-agentes y arma el texto. En el workflow nuevo el orquestador es **un agente de n8n que tiene a los otros agentes como herramientas**: llama a Turnos, Pagos, Información o Urgencias, ve lo que devuelven, puede encadenar (por ejemplo Información y después Turnos) y **él le escribe la respuesta al paciente**. El código no desaparece: verifica lo que escribió.

Archivos: `scripts/v7_workflow_cerebro_agente.py` (genera `v7/workflows/cerebro_agente.json`), `v7/prompt_orquestador_agente.md` (prompt, ~3.100 caracteres), `v7/verificador_core.js` (verificador puro), pruebas en `tests/test_verificador_core.mjs` y `tests/test_v7_cerebro_agente.py`.

## Cómo está armado

1. **Entrada y contexto**: igual que el cerebro actual (mismos nodos y mismo código: historial, recordatorios, datos del consultorio, identificar paciente, "Armar contexto"). Solo cambia el prompt.
2. **Pedidos por estado** (código): las redes por estado de hoy. Si la imagen vino marcada como comprobante, **Pagos se llama por código antes del agente**; si hay una confirmación pendiente que el paciente vio, o un recordatorio abierto, **Turnos se llama por código antes del agente**; si la charla la inició la clínica con un contacto sin ficha, ni siquiera se llama al agente (silencio). El resultado de lo forzado entra en el mensaje del agente ("no la vuelvas a llamar").
3. **Orquestador Agente**: gpt-5-mini, razonamiento medio, hasta 8 vueltas. Herramientas: `turnos`, `pagos`, `informacion`, `urgencias` (los 4 sub-workflows de siempre, con teléfono, ejecución, modo, mensaje y contexto FIJOS; el agente solo escribe el "pedido"), `derivar_secretaria` y `pasar_a_humano` (workflow `clinica`) y `no_responder` (silencio; es una herramienta de código que no toca nada).
4. **Verificar salida** (código, `verificador_core.js`) → **Salida** (avisos al grupo, memoria solo en vivo, marca de propuesta enviada) → **Devolver**. La salida tiene los mismos campos que el cerebro actual más `motivo_verificador` y `usado_respaldo`; el Adaptador de la entrada no cambia.

## Qué protege el código

El agente no ve ni escribe la agenda: escribir sigue pasando solo dentro de los sub-agentes y sus herramientas (confirmación en dos pasos, libro de escrituras, modo sombra con escrituras simuladas). Después del agente, el verificador exige:

- **Horarios y fechas**: solo los que salieron de una herramienta en este mismo mensaje (o un turno que el paciente ya tiene). Usa el chequeo de salida de siempre; además descarta "le reservé/cancelé/confirmé" sin escritura real.
- **Montos en pesos**: solo el de la consulta (KB 21) o el que devolvió una herramienta.
- **Read-back**: el "¿Procedo…?" sale textual y al final; si el agente no lo pegó, se agrega. Los datos bancarios van antes.
- **Datos de pago**: los pega el código solo si `datos_pago` los devolvió; si el agente escribió un alias, un CBU o un número de cuenta, se descarta.
- **Consistencia con el prompt** (no es una banlist): si aparece "los esperamos", "venite", "ahora mismo", "pida confirmación", "guarde la pieza", "traiga el DNI", sale el respaldo.
- **Falla, vacío o basura** (JSON, código, más de 1.500 caracteres): respaldo.
- Siguen igual: corte de bucle (tercera repetición → deriva con aviso), presentación en conversación nueva, mensajes fijos editables, regla de 6 h del staff (la herramienta `derivar_secretaria` corre en sombra si la clínica escribió hace menos de 6 h; si solo derivó, silencio), urgencias (si Urgencias derivó, v7 calla; si otro agente vio una urgencia y nadie la derivó, frase fija + `[ACCIÓN URGENTE]`).

**Respaldo** = las partes que devolvieron las herramientas, armadas con `OrquestadorCore.componer` (lo que hace hoy el cerebro). Sin herramientas: "no le entendí" (y si ya se lo dijimos en el mensaje anterior, deriva); si el agente se cayó: el texto honesto de error + `[ACCIÓN]` al grupo.

## Cómo se activa (sin riesgo)

Lo despliega Lucas; este cambio no lo hace. Pasos previstos: (1) crearlo en n8n **inactivo** con el mismo mecanismo que los demás (agregarlo a `crear_v7_en_n8n.py` resolviendo los `@@ID:…@@`); (2) **sombra**: llamarlo con `modo: 'sombra'` en paralelo al cerebro actual desde una entrada de prueba o desde la retrospectiva (`historial_json`), sin enviar nada y comparando `texto`, `usado_respaldo` y `motivo_verificador` contra el cerebro vivo; (3) revisar los casos con respaldo y los de latencia; (4) recién después, decidir si reemplaza al cerebro. Hasta entonces el cerebro actual sigue siendo el único que contesta.

## Qué NO hace todavía

- **Épica B**: que Turnos y Pagos también redacten (hoy sus textos los arma el código y el agente solo los junta; el agente puede reescribirlos pero el verificador exige los datos exactos).
- Editor de prompts desde el panel (el prompt vive en `v7/prompt_orquestador_agente.md`).
- Saludo de anuncio con precio y menú del panel: el agente pega el menú que le pasa el código; el saludo corto de anuncio ya no es una acción fija.
- Contador de "no entendí" en Redis: se reemplazó por la comparación con el último mensaje de Asiri.

## Riesgos conocidos

- **Latencia**: cada vuelta del agente suma segundos (modelo + sub-agente, que es otro agente con sus herramientas). Hoy son ~41 s de punta a punta con el orquestador de una llamada; con el agente puede subir. Se mide en sombra antes de decidir. El tope de 8 vueltas acota el peor caso.
- **Contexto grande**: las herramientas devuelven el JSON completo de cada sub-agente (con su traza); puede inflar tokens.
- **Expresiones en herramientas**: los campos fijos de las herramientas usan `$('Entrada')` y `$('Armar contexto')` dentro de un nodo `toolWorkflow`; en el harness no se pueden ejecutar, hay que verificarlo en n8n (primera prueba en sombra).
- **`no_responder`** usa el nodo `toolCode` (v1.1); si la versión de n8n no lo tiene, el agente igual puede callar contestando `[NO_REPLY]` (el verificador lo acepta).
- **Falsos positivos del verificador** → respaldo (más "frío" pero seguro). Por ejemplo "ahora mismo" en una frase inocente; se mide en sombra.
- **Timeout**: n8n no pone un tope de tiempo propio al nodo agente; depende del timeout de ejecución del workflow. Un agente que se cuelgue no llega al verificador.
