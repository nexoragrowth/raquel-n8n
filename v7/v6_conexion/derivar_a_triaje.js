// V7: Derivar a Triaje — ÚNICO punto por el que un teléfono en v7 entra al triaje del v6 (regex antes del orquestador, o derivar_triaje del orquestador).
// 'Triaje: Evaluar' lo detecta con $('V7: Derivar a Triaje').isExecuted para entrar en modo 'nuevo' (triaje/evaluar.js): así una derivación del v7
// nunca vuelve como ruta_pre 'normal' (sin bucle) y, si el triaje concluye "no es urgencia", Decidir la ESCALA (texto de escalada + aviso al grupo):
// el paciente nunca queda sin respuesta. 'Triaje: Cargar Config' ignora el item de entrada (consulta fija), acá solo se deja rastro de por dónde vino.
let via = 'cerebro';
try { if ($('V7: Pre-Triaje Regex').first().json.urgencia_regex === true) via = 'regex'; } catch (e) { via = 'cerebro'; }
console.log('[V7] derivar a triaje via', via);
return [{ json: { _flow: 'v7', via } }];
