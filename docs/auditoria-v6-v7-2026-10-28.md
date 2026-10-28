# Auditoría v6 → v7 de Asiri (28/10/2026)

Hecha por 8 analistas independientes de solo lectura (código de los dos cerebros, 2.500 filas de memoria, 2.054 ejecuciones de la entrada y 154 del cerebro, tablas `casos`, `escalaciones_log`, `mensajes_entrantes_live`), más el análisis del panel. Los informes completos con evidencia por ítem (ids de fila y de ejecución, archivo:línea) están fuera del repo porque citan fragmentos de conversaciones de pacientes; este documento solo resume.

Pedido de Lucas: "la idea era un orquestador que resolviera múltiples peticiones en simultáneo; compará y decime qué hiciste de más y qué te faltó en la migración; y el panel tiene que dejar controlar los prompts de los agentes y el conocimiento".

## Veredicto
El v7 cumple la idea en código y tests, pero **en producción todavía no demuestra ser mejor que el v6**, y se le agregaron mecanismos que nadie pidió. Fechas: el v7 atiende a todos desde el **20/10 00:10 ART** (no el 19/10).

## Lo que el v7 sí mejoró
- Escrituras en la agenda más sólidas (read-back, candado, verificación, familias con varios turnos, confirmación por recordatorio 23/35 vs 29/56 en v6).
- El orquestador reparte pedidos entre agentes (código + tests). En tráfico real hay muy pocos pedidos múltiples: 6 mensajes en 7 días; v7 resolvió 2 bien, 3 parcial, 1 mal; v6 8/2/1 de 11. **Sin evidencia de que sea mejor todavía.**
- Latencia igual (mediana 41 s entrada completa; p90 48 s vs 61 s).
- Contratos con el resto de los workflows en regla: memoria `asiri_v7` (92/92 copiadas por el Logger), avisos por `notify-grupo` (48/48 con caso), modo humano respetado (84/84).

## De más (qué agregó el v7 que nadie pidió o que contradice la intención)
1. **Textos de Turnos/Pagos escritos por código.** Idea de Lucas (7/10, "que el orquestador no labure") extendida por Claude a todos los agentes (crítica B6, 8/10). Por eso editar el prompt de esos agentes no cambia lo que lee la paciente. Origen mixto.
2. **Deriva de más:** tel-día con derivación 18,1 % → 26,5 %; avisos al grupo 2,2 → 7,4 por 100 mensajes. Causa: la cláusula "informa algo" del prompt del orquestador, pago + derivación duplicados, y Información todo-o-nada (si una parte es fuera de alcance, deriva todo y se pierde el precio).
3. Dos regex que reescriben la salida de Información; 5 workflows muertos aún activos; ~12 redes de código que no dispararon nunca en 113 ejecuciones reales.
4. **Editor de prompts del panel borrado sin OK de Lucas** (commit 2a98d94, 20/10, BOT-14). El ticket pedía solo avisar y bloquear la edición del v6.
5. Código vs prompts: 94 % de la lógica es código (142 KB) contra 9,5 KB de prompts; parámetros de negocio (48 h, 2 bloques, 72 h, TTL 12 h, insistencia 30 min) no editables; 20 fichas de Conocimiento (reglas de la clínica) no las lee ningún agente y dos contradicen al v7 (KB 17 turno único, KB 9 reiterativos).

## Falta o quedó peor (ordenado por gravedad)
| # | Qué | Evidencia | Estado |
|---|---|---|---|
| 1 | Contesta encima de la charla de la secretaria con una paciente con ficha | 8 de 13 respuestas improcedentes (v6: 0–1 de 14); regla solo en el prompt | pendiente: decisión (ventana 1 h vs 24 h) |
| 2 | Información todo-o-nada: se pierde el precio | exec 321598 | prompt corregido (parte mixta), pendiente deploy |
| 3 | Comprobante que no se registra (ruteado a Turnos; agente "payments") | filas 12723 y 12885 | corregido en código (pendiente deploy) |
| 4 | Batería de ruteo con modelo real (urgencias 100 %, 0 falsos "confirma") nunca construida | diseño §8 | pendiente |
| 5 | Salud: Health Check/Vigía no miran al v7; alertas por un solo canal (Evolution); 85 ejecuciones del Health Check fallaron sin aviso el 17–19/10 | v6-otros O-26..O-30 | pendiente |
| 6 | Reportero semanal cuenta como "señal" 39 de 40 avisos de comprobante del v7 | ejec 323954 | pendiente |
| 7 | Check Session Age borra memoria >7 días antes del cerebro | O-13 | no medido |
| 8 | PDF-comprobante derivado sin registrar pago ("archivo sin texto → derivar") | sin casos reales | pendiente |
| 9 | Sin filtro de autorespuestas de otros bots ni de inyección de prompt | 3 autorespuestas v7, ninguna contestada | pendiente |
| 10 | Mensajes silenciados no quedan en memoria (15 de 125 ejecuciones) | E39 | no medido |
| 11 | Agradecimientos: v6 respondía "de nada", v7 calla | prod-tasas | decisión de producto |
| 12 | Higiene: 21 webhooks de prueba abiertos sin autenticación (uno borra filas de `n8n_chat_histories`), credenciales en texto en nodos | O-38, O-39, E41 | **urgente, requiere OK** |
| 13 | Bandeja Atención: 42 casos, 0 tomados; 37 ya atendidos por WhatsApp; contadores del panel mienten | casos | spec lista |
| 14 | Audio: la red detectaba solo `[AUDIO]` al principio del texto | v6-entrada E09 | corregido (pendiente deploy) |

## Panel
- **Editor de prompts:** diseño B (informe `panel-prompts`): esqueleto bloqueado en el repo + slots editables en `agente_directrices` (`prm_*`), leídos en cada mensaje, con fallback al texto del repo; sin PUT a workflows vivos; con los valores por defecto el resultado es idéntico byte a byte a los 5 prompts actuales (verificado). Probador en sombra factible (mediana 14,7 s). Despliega 5 workflows (cerebro + 4 agentes), sin tocar la entrada O155.
- **Piden hablar con una persona:** no hace falta tabla nueva. Vista `/atencion/personas` sobre `casos` + destino secretaria/doctora (campo `destino` que decide el modelo, no regex) + cierre automático cuando la clínica contesta por WhatsApp + espera medida en horario hábil. Volumen real bajo (3 pedidos explícitos en 8 días), el valor es no perder ninguno.
- **Push:** no hay emisor (solo el service worker que recibe).

## Decisiones tomadas el 28/10
- Se revierte la decisión "no hay cuadro de prompts para Turnos/Pagos": la clínica controla prompts de agentes y conocimiento desde el panel; lo que sea lógica de negocio/arquitectura se hace aparte con Claude Code (ver `docs/DIAGNOSTICO_IA.md`).
