// V7: Pre-Triaje Regex — red determinística ANTES del orquestador v7 (solo corre para teléfonos con v7:tel:{tel} = 'vivo').
// Las líneas de textoNorm y esUrgenciaFuerte son COPIA TEXTUAL del nodo vivo 'Parse Intent' del v6: scripts/apply_v7_flag_lucas.py las extrae del
// nodo vivo, verifica que no cambiaron y las pega en el marcador de abajo. Es el mismo criterio que hoy manda al triaje a TODOS los teléfonos
// (Parse Intent: `if (esUrgenciaFuerte) intent = 'urgencia_dolor'` → Switch sobre Intent[2] → Triaje: Cargar Config), así que una urgencia fuerte
// llega al triaje del v6 sin depender de ningún modelo (regla dura #5, lección Mariela).
// NO incluye gateRedFlags: corre igual dentro de 'Triaje: Evaluar' una vez que el mensaje entra al triaje, y su cabecera (triaje/gate_red_flags.js)
// prohíbe correrlo sobre todos los mensajes (falsos positivos con "tuve un accidente, necesito cambiar el turno").
let text = '';
try { text = ($('Preparar Mensaje Final').first().json.text || '').toString(); } catch (e) { text = ''; }
/*__COPIA_PARSE_INTENT__*/
console.log('[V7] pre-triaje regex:', esUrgenciaFuerte ? 'URGENCIA -> triaje (sin pasar por el orquestador)' : 'no', '|', text.slice(0, 120));
return [{ json: { _flow: 'v7', urgencia_regex: esUrgenciaFuerte === true } }];
