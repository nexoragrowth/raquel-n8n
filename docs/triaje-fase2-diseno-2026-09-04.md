# Triaje de urgencias con video — Fase 2 (piloto en el v6) — diseño final e implementación

**Fecha**: 2026-09-04 · **Estado**: script listo, tests verdes, esperando OK de Lucas para el PUT.
**Análisis completo** (6 mapeos del v6, 3 diseños, 3 jueces): `docs/triaje-fase2-analisis/`.
**Decisiones**: `memory/decisions.md` 2026-09-02 y 2026-09-04.

## 1. Qué hace (en una frase)
Cuando el Router clasifica `urgencia_dolor`, en vez de ir directo al Sub-Agent Urgencia (escalar siempre), el mensaje pasa por
un gate determinístico de red flags → un clasificador (gpt-5-mini, solo JSON) → y si es un tipo con video activo en la tabla y
confianza alta, el paciente recibe el **video real de la Dra.** + un texto canned; si dice "no me sirvió" recibe la **Opción 2**;
si sigue mal, agradece, o hay red flag, se escala/cierra **determinísticamente** (el LLM nunca escribe al paciente).
Todo lo que ve el paciente sale de `triaje_videos` / `triaje_config` (Supabase), editable sin tocar n8n.

## 2. Diferencias vs. el diseño ganador de los jueces (`diseno-ganador-product-first.md`)
1. **Escalación determinística** (no vía Sub-Agent Urgencia): el mapeo demostró que hoy `escalar_a_secretaria` → Helper →
   `Chatwoot Apply` aplica el label `humano` en forma sincrónica y `Re-check Humano` suprime la respuesta del sub-agent
   **en 6/6 escalaciones** desde el 30/8 (el paciente nunca recibe "Recibimos tu mensaje…"). En la rama nueva el texto
   canned se manda ANTES de avisar al grupo; el aviso aplica el label como siempre. `Sub-Agent Urgencia` queda huérfano
   (no se borra; `--rollback-wiring` lo reconecta).
2. **Merge por posición** después del clasificador: `Decidir` recibe los datos de `Evaluar` en el mismo item (no por
   `$('Triaje: Evaluar').first()`), eliminando la ambigüedad de doble corrida en el camino seguimiento→Router→urgencia.
3. **Re-check de humano dentro de `Decidir`** (Chatwoot, fail-open) antes de mandar video/pregunta/cierre → `silencio`.
4. Cierre estricto: "ok pero me duele" NO cierra (menciona aparato/síntoma sin resolver → escala); "listo gracias ya me puse
   la cera" SÍ cierra. `regex_no_sirvio` evaluado con límites Unicode; "igual"/"nada" sueltos no disparan.
5. `aviso_pasivo=false` por defecto (hasta el carve-out en el panel); el registro vive en `triaje_urgencias_log`.
6. `texto_cierre` se manda por `/send/text` directo (nunca pasa por Formatting Agent).

## 3. Grafo (21 nodos "Triaje: *", 2 conexiones existentes cambiadas, 1 párrafo en el Router)
```
Es cierre?[1] ─► Triaje: Redis GET estado ─► Triaje: ¿Seguimiento? ─[no]─► Router - Clasificar Intent   (idéntico a hoy si no hay estado)
                                                        └─[sí]─┐
Switch sobre Intent[2] (urgencia_dolor) ────────────────────────┴─► Triaje: Cargar Config ─► Triaje: Evaluar ─► Triaje: Ruta Pre
   Ruta Pre[clasificar] ─► Triaje: Clasificar (gpt-5-mini) ─► Triaje: Merge Clasificación ─► Triaje: Decidir ─► Triaje: Ruta
   Ruta Pre[decidido]   ─► Triaje: Decidir
   Ruta Pre[normal]     ─► Router - Clasificar Intent
   Ruta Pre[fallback]   ─► Triaje: Preparar Escalada
   Ruta[video]    ─► Triaje: Enviar Video (/send/media) ─► ¿Video OK? ─[sí]─► Triaje: Enviar Texto Canned ─► ¿Texto OK? ─► Triaje: Persistir ─► Triaje: Redis SET estado
   Ruta[pregunta] ─► Triaje: Enviar Texto Canned ─► …                                          └─[no]─► Preparar Escalada
   Ruta[cerrar]   ─► Triaje: Enviar Texto Canned ─► … (tolerante: si falla el texto de cierre igual persiste)
   Ruta[silencio] ─► Triaje: Log Silencio
   Ruta[escalar|fallback] ─► Triaje: Preparar Escalada ─► Triaje: Enviar Texto Escalada ─► Triaje: Escalar (notify-grupo) ─► Triaje: Log Escalado ─► Triaje: Redis SET escalado
```
Fuente única de cada Code node: `triaje/gate_red_flags.js`, `triaje/evaluar.js`, `triaje/decidir.js`, `triaje/preparar_escalada.js`,
`triaje/escalar_notify.js`, prompt del clasificador `triaje/prompt_clasificador.md`. El script `scripts/apply_triaje_fase2_piloto.py`
los embebe; apikey de Evolution y token de Chatwoot se copian de nodos vivos en el momento del PUT (nunca en el repo).

## 4. Estado y datos
- **Redis** `triaje:{phone}` (misma convención que `chat_buffer:`/`ratelimit:`): `{tipo, opcion, paso: video_enviado|pregunta|cerrado|escalado, exec_id}`
  con TTL 7200 (video) / 1800 (pregunta) / 60 (cerrado) / 3600 (escalado). Si Redis falla: 2ª capa = estado reconstruido desde el
  contexto del Router (`BOT: [VIDEO ENVIADO — tipo, Opción N]` sin `[TRIAJE CIERRE|ESCALADO]` posterior) + párrafo nuevo del Router.
- **Memoria** `n8n_chat_histories`: filas `human` (source `triaje_paciente`) + `ai` (`[VIDEO ENVIADO — …]`, `[TRIAJE — PREGUNTA GUIADA …]`,
  `[TRIAJE CIERRE] …`, `[TRIAJE ESCALADO] …`) con el mismo shape que `Postgres - Save fromMe`. El Router las ve en su ctx, los sub-agents
  en su ventana de 10, el Logger las copia al panel como "Asiri".
- **Log** `triaje_urgencias_log` (modo `piloto`, accion `video|pregunta|cierre|silencio_humano|escalado`, tipo, confianza, razon,
  gate_red_flags, video_enviado, opcion_enviada, chat_history_id, resuelto_at). Leer con `python scripts/ver_triaje_sombra.py`.
- **Config** `triaje_config` (activo, modo, telefonos_piloto, red_flags_extra, regex_*, texto_escalada, texto_cierre, aviso_pasivo, TTLs, modelo)
  y `triaje_videos` (tipo, opcion, url, caption, pregunta_guiada, texto_salida_emergencia, activo). Script: `scripts/create_triaje_config_tables.py`.

## 5. Fail-closed (qué recibe el paciente si algo falla)
| Falla | Resultado |
|---|---|
| Postgres caído / tabla ausente | modo nuevo: escalar (`config_no_disponible`); seguimiento: regexes default, "no sirvió" → escalar |
| OpenAI caído / JSON inválido | escalar (`error_llm`), paciente recibe `texto_escalada`, grupo avisado |
| `/send/media` falla | escalar (`envio_fallo_video`) |
| `/send/text` de pregunta falla | escalar |
| `/send/text` de salida tras video OK | se persiste igual (el caption ya lleva la instrucción) |
| Persistir / Redis fallan | paciente ya tiene el video; seguimiento cae a la 2ª capa (ctx + Router) |
| Ruta inesperada | fallback de ambos Switch → escalar |
| Label humano en Chatwoot | silencio (como hoy) + fila `silencio_humano` |
| notify-grupo falla | el paciente igual recibió `texto_escalada`; queda `NOTIFY_FALLO` en la razón del log |

## 6. Operación
- **Activar (piloto solo Lucas)**: `python scripts/create_triaje_config_tables.py --activar --piloto 5491161461034`
- **Abrir a todos**: `--activar --piloto ""` · **Kill-switch por dato**: `--desactivar` (0 PUT, instantáneo)
- **Nuevo video**: `python scripts/upload_urgencia_video_supabase.py "<mp4>" "bracket_suelto/opcion1.mp4"` +
  `UPDATE triaje_videos SET url=..., caption=..., activo=true WHERE tipo='bracket_suelto' AND opcion=1` → sin tocar n8n.
- **Textos**: `UPDATE triaje_videos/triaje_config …` → luego `python tests/test_triaje_textos_banlist.py --db` (2ª capa del Banlist).
- **Limpiar un teléfono para demo**: `python scripts/limpiar_numero_demo.py --phone <tel> --apply [--borrar-logs]`
- **Rollback**: `--desactivar` (datos) → `apply_triaje_fase2_piloto.py --rollback-wiring` (2 conexiones) → `--rollback <PRE.json>` (total).
- **Sombra** (`Gm7ofyGohOJ2bI44`): al activar el piloto conviene desactivarla o dejarla (duplica filas `modo=sombra` de lo que el piloto escaló).

## 7. Guion de demo (teléfono real, ≥25 s entre mensajes por el buffer de 22 s; máx 10 msgs/15 min)
| # | Paciente escribe | Recibe |
|---|---|---|
| 1 | "hola, se me salió el alambre de atrás y me pincha el cachete" | Video Opción 1 (cera) + texto de salida |
| 2 | "no me sirvió, sigue pinchando" | Video Opción 2 (pinza) + texto de salida — sin LLM |
| 3 | "no lo pude meter con la pinza, sigue igual" | `texto_escalada` + aviso al grupo `[TRIAJE] no sirvio sin mas opciones | tipo: alambre_pincha | videos enviados: alambre_pincha Opción 1 y 2 | Paciente: «…»` |
| 4 | (limpiar label humano) "listo, gracias, ya me puse la cera" tras un video | `texto_cierre` |
| 5 | "se cayó y le sangra mucho la boca" | escalación inmediata por red flags (sin LLM ni video) |
Bonus config: `UPDATE triaje_videos SET activo=false WHERE opcion=2` → el paso 2 escala en vez de mandar la Opción 2.

## 8. Tests
- `node triaje/test_gate.js` (29/29) · `node tests/test_triaje_nodos.js` (44 casos de ruteo sobre el código real) ·
  `python tests/test_triaje_textos_banlist.py [--db]` (0 matches) · `python tests/test_e2e_triaje.py --phone … --texto …` (E2E real).
- Pendiente de Raquel: fraseo de la pregunta guiada y textos definitivos (hoy borradores en la tabla), lista de red flags.

## 9. Bug preexistente encontrado (fuera de alcance de este PUT)
Toda escalación del bot (cualquier sub-agent) aplica el label `humano` antes de que el propio bot mande su respuesta, y el
`Re-check Humano` la suprime: 6/6 casos desde el 30/8 con contacto en Chatwoot. El paciente escalado no recibe el canned de cierre.
Fix sugerido aparte: que `Chatwoot Apply` del Helper no se aplique en la misma ejecución que escala, o que el re-check ignore
labels aplicados por la propia ejecución.
