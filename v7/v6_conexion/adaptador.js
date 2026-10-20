// V7: Adaptador — traduce la salida del cerebro v7 (orquestador + sub-agentes, nodo 'Devolver' de scripts/v7_workflow_cerebro.py) al contrato
// de 'Fallback Output' del v6: { output, _flow: 'v7' }.
// Contrato de 'Devolver': { texto, enviar, silencio, derivar_triaje, triaje, texto_original, modo, motivo_chequeo, motivo_banlist, fallo_agente,
//   modo_humano, tools, agentes, plan, avisos }.
//   - texto con enviar=true: respuesta compuesta por código (menú, información, pagos, derivación a la secretaria, pasar a humano, turnos verificados
//     contra la agenda, o el texto de error del propio cerebro si falló el orquestador). Se manda TAL CUAL (sin Formatting Agent).
//   - enviar=false / silencio=true: el orquestador decidió no responder → '[NO_REPLY]' (Fallback Output lo respeta por _flow; termina en Descartar).
//   - derivar_triaje=true: urgencia → no responde Asiri, responde el triaje del v6 (el IF siguiente lo manda a 'V7: Derivar a Triaje').
// El cerebro YA guardó la memoria del chat (nodo 'Guardar en memoria', solo vivo && !silencio) y YA mandó sus avisos al grupo: acá NO se escribe memoria ni se
// reenvían avisos. El item se arma DESDE CERO (sin spread): con continueOnFail un crash del sub-workflow llega como { error }.
// Fallo (crash, contrato roto, o el cerebro corrió en 'sombra' — herramientas simuladas, texto que no se cumplió): canned seguro + aviso [ACCIÓN].
const CANNED_FALLO = 'Hola! Soy Asiri🤗, la secretaria virtual de la Dra. Raquel Rodríguez. Le envío la información a la secretaria, ella le responderá en su horario de atención. Gracias!';
let r = {};
try { r = $input.first().json || {}; } catch (e) { r = {}; }
let phone = '';
try { phone = ($('Preparar Mensaje Final').first().json.phone || '').toString(); } catch (e) { phone = ''; }

const errorSubWf = r.error ? String((r.error && r.error.message) || r.error) : null;
const texto = typeof r.texto === 'string' ? r.texto.trim() : '';
const callar = r.enviar === false || r.silencio === true;

let output = '', caso = '', fallo = null, derivar = false;
if (errorSubWf) fallo = 'error_subworkflow: ' + errorSubWf;
else if (r.modo !== 'vivo') fallo = 'modo_no_vivo: ' + String(r.modo);            // nunca mandar un texto de sombra (escrituras simuladas)
else if (r.derivar_triaje === true) { derivar = true; output = '[NO_REPLY]'; caso = 'derivar_triaje'; }
else if (callar) { output = '[NO_REPLY]'; caso = 'silencio'; }
else if (!texto) fallo = 'sin_texto';
else { output = texto; caso = 'texto'; }

if (fallo) {
  output = CANNED_FALLO; caso = 'fallo';
  try {
    await this.helpers.httpRequest({ method: 'POST', url: 'https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo', json: true,
      qs: { phone, resumen: '[ACCIÓN] v7: el cerebro no devolvió una respuesta válida (' + fallo.slice(0, 200) + '). Se mandó el mensaje de secretaria: revisar y contestar a mano.' } });
  } catch (e) { /* el aviso nunca rompe la respuesta */ }
}
const tools = (Array.isArray(r.tools) ? r.tools : []).map((t) => t && t.tool).filter(Boolean);
console.log('[V7] adaptador:', JSON.stringify({ caso, fallo, phone, enviar: r.enviar, silencio: r.silencio, modo: r.modo, modo_humano: r.modo_humano === true,
  fallo_agente: r.fallo_agente === true, motivo_chequeo: r.motivo_chequeo || null, agentes: r.agentes || null, tools, len: output.length }));
return [{ json: { output, _flow: 'v7', derivar_triaje: derivar,
  _v7: { caso, fallo, modo_humano: r.modo_humano === true, fallo_agente: r.fallo_agente === true, motivo_chequeo: r.motivo_chequeo || null, tools } } }];
