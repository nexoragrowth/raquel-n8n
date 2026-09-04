// ===== triaje/preparar_escalada.js — nodo "Triaje: Preparar Escalada" del v6 (Fase 2, 2026-09-04) =====
// FUENTE ÚNICA (la embebe scripts/apply_triaje_fase2_piloto.py). Tests: node tests/test_triaje_nodos.js
//
// Entra por: Ruta Pre[fallback] ($input = item de Evaluar), Ruta[escalar]/Ruta[fallback] ($input = item de Decidir),
//            ¿Video OK?[1] / ¿Texto OK?[1] ($input = respuesta HTTP de Evolution GO -> se usa $('Triaje: Decidir')).
// Salida: 1 item con send {number, text} (texto canned al paciente ANTES de que se aplique el label humano),
//         resumen para el grupo, y datos para el log/memoria. NO llama a ningún LLM.

let src = $input.first().json || {};
let envio = null;
if (!src.triaje) {
  // vinimos de un nodo HTTP (falló el envío): el contexto está en Decidir
  envio = src;
  try { src = $('Triaje: Decidir').first().json || {}; } catch (e) { src = {}; }
}
const pm = $('Preparar Mensaje Final').first().json;
const cfg = src.cfg || {};
const textos = cfg.textos || {};
const esc = (v) => (v === null || v === undefined) ? "NULL" : "'" + String(v).replace(/'/g, "''").split("$").join("' || chr(36) || '") + "'";
const memRow = (type, content, kw) => JSON.stringify({ type, content, additional_kwargs: kw, response_metadata: {}, tool_calls: [], invalid_tool_calls: [] });

let razon = src.razon || "sin_razon";
if (envio && (src.ruta === "video" || src.ruta === "pregunta" || src.ruta === "cerrar")) {
  razon = "envio_fallo_" + src.ruta + ": " + String((envio.error && envio.error.message) || envio.message || envio.statusCode || JSON.stringify(envio)).slice(0, 150);
}
const estado = src.estado || null;
const tipo = src.tipo || (estado && estado.tipo) || null;
const videosPrevios = estado && estado.paso === "video_enviado" ? (estado.tipo + " Opción 1" + (Number(estado.opcion) >= 2 ? " y 2" : "")) : (src.ruta === "video" && src.video ? src.tipo + " Opción " + src.video.opcion + " (falló el envío)" : "ninguno");

const texto = String(textos.texto_escalada || "Recibimos su mensaje. Le pasamos a la Dra. Raquel para que le coordine lo antes posible.");
const phone = String(pm.phone || "");
const number = String(pm.remoteJid || "").replace(/[^0-9]/g, "") || phone;
const texto_paciente = String(pm.text || "").slice(0, 220);
const resumen = "[TRIAJE] " + razon.replace(/_/g, " ") +
  (tipo ? " | tipo: " + tipo + (src.confianza ? " (" + src.confianza + ")" : "") : "") +
  (src.gate_flags && src.gate_flags.length ? " | red flags: " + src.gate_flags.join(", ") : "") +
  " | videos enviados: " + videosPrevios +
  " | Paciente: «" + texto_paciente + "»";

const flagsJson = JSON.stringify((src.gate_flags || []).map((f) => "gate:" + f));
const humanRow = memRow("human", String(pm.text || ""), { source: "triaje_paciente" });
const aiRow = memRow("ai", "[TRIAJE ESCALADO] " + texto, { source: "triaje_escalado", tipo, razon });

return [{ json: {
  triaje: true, phone, number, texto_paciente, resumen, razon, tipo,
  confianza: src.confianza || null, gate_flags: src.gate_flags || [], gate_escala: !!src.gate_escala,
  modelo: cfg.modelo || null, modo: cfg.modo || "piloto",
  video_enviado: estado && estado.paso === "video_enviado" ? estado.tipo + "/opcion" + estado.opcion : null,
  opcion_enviada: estado && estado.paso === "video_enviado" ? Number(estado.opcion) || null : null,
  exec_id: String($execution.id || ""),
  send: { number, text: texto },
  estado_json: JSON.stringify({ tipo, paso: "escalado", exec_id: String($execution.id || "") }),
  estado_ttl: 3600,
  human_row: humanRow, ai_row: aiRow, flags_json: flagsJson,
} }];
