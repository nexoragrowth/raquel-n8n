// ===== triaje/decidir.js — nodo "Triaje: Decidir" del v6 (Fase 2, 2026-09-04) =====
// FUENTE ÚNICA: scripts/apply_triaje_fase2_piloto.py lo embebe con estas sustituciones:
//   el placeholder CW_TOKEN (con guiones bajos dobles) -> api_access_token de Chatwoot copiado del nodo vivo "Re-check Humano" (nunca en el repo)
// Tests: node tests/test_triaje_nodos.js
//
// $input = (a) item de "Triaje: Merge Clasificación" (campos de Evaluar + respuesta de OpenAI en choices)
//          (b) item de "Triaje: Evaluar" directo (ruta_pre 'decidido')
// Salida: 1 item con ruta = 'video' | 'pregunta' | 'cerrar' | 'silencio' | 'escalar' + payloads canned + SQL.

const CW_TOKEN = "__CW_TOKEN__";
const ev = $input.first().json || {};
const d = { ...ev };
delete d.llm_body;

const cfg = ev.cfg || {};
const videos = Array.isArray(cfg.videos) ? cfg.videos : [];
const videosDe = (tipo) => videos.filter((v) => v.tipo === tipo).sort((a, b) => Number(a.opcion) - Number(b.opcion));
const esc = (v) => {
  if (v === null || v === undefined) return "NULL";
  // sin '$' en el SQL: pg-promise interpreta $N como parámetro
  return "'" + String(v).replace(/'/g, "''").split("$").join("' || chr(36) || '") + "'";
};
const memRow = (type, content, kw) => JSON.stringify({ type, content, additional_kwargs: kw, response_metadata: {}, tool_calls: [], invalid_tool_calls: [] });

if (!ev.triaje || !ev.ruta_pre) {
  d.ruta = "escalar"; d.razon = "sin_evaluacion";
} else if (ev.ruta_pre === "decidido") {
  d.ruta = ev.ruta || "escalar";
} else if (ev.ruta_pre === "clasificar") {
  let tipo = "error_llm", confianza = "baja", razon = "";
  try {
    const content = ev.choices[0].message.content;
    const p = JSON.parse(String(content).replace(/^```(json)?|```$/gm, "").trim());
    tipo = String(p.tipo || "error_llm"); confianza = String(p.confianza || "baja"); razon = String(p.razon || "").slice(0, 300);
  } catch (e) {
    razon = "error_llm: " + String((ev.error && ev.error.message) || ev.statusCode || (e && e.message) || "sin_respuesta").slice(0, 200);
  }
  Object.assign(d, { tipo, confianza, razon });
  const vids = videosDe(tipo);
  const fueraPiloto = Array.isArray(cfg.telefonos_piloto) && cfg.telefonos_piloto.length && !cfg.telefonos_piloto.map(String).includes(String(ev.phone));
  if (!cfg.activo || fueraPiloto) { d.ruta = "escalar"; d.razon = (!cfg.activo ? "triaje_inactivo" : "fuera_piloto") + " (" + tipo + ")"; }
  else if (["red_flag", "otra_urgencia", "no_urgencia", "error_llm"].includes(tipo) || vids.length === 0) { d.ruta = "escalar"; }
  else if (ev.post_video && ev.estado && ev.estado.tipo === tipo) {
    // Mismo problema después del video: si dijo que no sirvió y hay opción siguiente -> siguiente; si no -> doctora.
    const next = vids.find((v) => Number(v.opcion) === (Number(ev.estado.opcion) || 1) + 1);
    if (ev.reclasifica && next) { d.ruta = "video"; d.video = next; d.razon = "no_sirvio_reclasificado_mismo_tipo"; }
    else { d.ruta = "escalar"; d.razon = "mismo_problema_post_video"; }
  }
  else if (confianza === "alta") { d.ruta = "video"; d.video = vids[0]; }
  else if (!ev.reclasifica && vids[0].pregunta_guiada) { d.ruta = "pregunta"; d.pregunta = vids[0].pregunta_guiada; }
  else { d.ruta = "escalar"; d.razon = "confianza_" + confianza + (ev.reclasifica ? "_post_pregunta" : "_sin_pregunta"); }
} else {
  d.ruta = "escalar"; d.razon = "ruta_pre_desconocida";
}

// ---- Re-check de "humano atendiendo" justo antes de mandar algo al paciente (fail-open, como Gate Humano Final) ----
if (["video", "pregunta", "cerrar"].includes(d.ruta)) {
  try {
    const contactId = $('Existe paciente?').first().json.payload[0].id;
    const convs = await this.helpers.httpRequest({
      method: "GET",
      url: "https://chat.raquelrodriguez.com.ar/api/v1/accounts/1/contacts/" + contactId + "/conversations",
      headers: { api_access_token: CW_TOKEN },
      json: true,
    });
    const list = (convs && convs.payload) || [];
    for (const c of list) {
      if (c.labels && Array.isArray(c.labels) && c.labels.includes("humano")) { d.ruta = "silencio"; d.razon = "humano_atendiendo"; break; }
    }
  } catch (e) { /* fail-open */ }
}

// ---- Payloads canned (100% de tabla) ----
const num = String(ev.remoteJid || "").replace(/[^0-9]/g, "") || String(ev.phone || "").replace(/[^0-9]/g, "");
const textos = cfg.textos || {};
const flagsJson = JSON.stringify((ev.gate_flags || []).map((f) => "gate:" + f));
const humanRow = memRow("human", ev.text || "", { source: "triaje_paciente" });
d.send = { number: num, text: "" };
d.estado_json = null; d.estado_ttl = 60;
d.mem_ai = null; d.accion = null; d.video_enviado = null; d.opcion_enviada = null; d.motivo_aviso = null;

if (d.ruta === "video") {
  const v = d.video || {};
  d.send.url = String(v.url || ""); d.send.caption = String(v.caption || ""); d.send.filename = String(v.filename || (d.tipo + "_opcion" + v.opcion + ".mp4"));
  d.send.text = String(v.texto_salida_emergencia || "");
  d.estado_json = JSON.stringify({ tipo: d.tipo, opcion: Number(v.opcion), paso: "video_enviado", exec_id: ev.exec_id });
  d.estado_ttl = Number(cfg.ttl_video_seg) || 7200;
  d.mem_ai = memRow("ai", "[VIDEO ENVIADO — " + d.tipo + ", Opción " + v.opcion + "] " + d.send.caption + (d.send.text ? "\n" + d.send.text : ""), { source: "triaje_video", tipo: d.tipo, opcion: Number(v.opcion), video_url: d.send.url, video_id: v.id || null });
  d.accion = "video"; d.video_enviado = d.tipo + "/opcion" + v.opcion; d.opcion_enviada = Number(v.opcion);
  d.motivo_aviso = "[TRIAJE VIDEO] " + d.tipo + " Opción " + v.opcion + " — atendido con video canned, sin escalar. Paciente: «" + String(ev.text || "").slice(0, 160) + "»";
}
if (d.ruta === "pregunta") {
  d.send.text = String(d.pregunta || "");
  d.estado_json = JSON.stringify({ tipo: d.tipo, paso: "pregunta", pregunta: d.send.text, texto_original: ev.text || "", exec_id: ev.exec_id });
  d.estado_ttl = Number(cfg.ttl_pregunta_seg) || 1800;
  d.mem_ai = memRow("ai", "[TRIAJE — PREGUNTA GUIADA (" + d.tipo + ")] " + d.send.text, { source: "triaje_pregunta", tipo: d.tipo });
  d.accion = "pregunta";
}
if (d.ruta === "cerrar") {
  d.send.text = String(textos.texto_cierre || "Buenísimo, gracias por avisar. Si vuelve a molestar, escríbanos por acá.");
  d.estado_json = JSON.stringify({ tipo: d.tipo || null, paso: "cerrado", exec_id: ev.exec_id });
  d.estado_ttl = 60;
  d.mem_ai = memRow("ai", "[TRIAJE CIERRE] " + d.send.text, { source: "triaje_cierre", tipo: d.tipo || null });
  d.accion = "cierre";
}

const withAviso = d.ruta === "video" && cfg.aviso_pasivo === true;
const tipoEstado = ev.estado && ev.estado.tipo ? ev.estado.tipo : null;
// Un solo statement atómico: memoria (human + ai) [+ aviso pasivo] + fila de triaje_urgencias_log
d.sql_persistir = d.mem_ai ?
  "WITH h AS (INSERT INTO n8n_chat_histories(session_id, message) VALUES (" + esc(ev.phone) + ", " + esc(humanRow) + "::jsonb) RETURNING id), " +
  "a AS (INSERT INTO n8n_chat_histories(session_id, message) SELECT " + esc(ev.phone) + ", " + esc(d.mem_ai) + "::jsonb FROM h RETURNING id), " +
  "e AS (INSERT INTO escalaciones_log(telefono, motivo, origen, exec_id) SELECT " + esc(ev.phone) + ", " + esc(d.motivo_aviso) + ", 'triaje_video', " + esc(ev.exec_id) + " WHERE " + (withAviso ? "true" : "false") + " RETURNING id), " +
  (d.ruta === "cerrar" ?
    "u AS (UPDATE triaje_urgencias_log SET resuelto_at = NOW(), razon_cierre = " + esc(String(ev.text || "").slice(0, 200)) + " WHERE id = (SELECT id FROM triaje_urgencias_log WHERE telefono = " + esc(ev.phone) + " AND accion IN ('video','pregunta') AND resuelto_at IS NULL ORDER BY id DESC LIMIT 1) RETURNING id) "
    : "u AS (SELECT NULL::bigint AS id) ") +
  "INSERT INTO triaje_urgencias_log(escalacion_id, telefono, exec_id, mensaje_paciente, gate_red_flags, gate_escala, tipo, confianza, razon, modelo, modo, accion, video_enviado, opcion_enviada, chat_history_id) " +
  "SELECT (SELECT id FROM e), " + esc(ev.phone) + ", " + esc(ev.exec_id) + ", " + esc(ev.text) + ", " + esc(flagsJson) + "::jsonb, false, " + esc(d.tipo || tipoEstado) + ", " + esc(d.confianza || null) + ", " + esc(d.razon || null) + ", " + esc(cfg.modelo || null) + ", " + esc(cfg.modo || "piloto") + ", " + esc(d.accion) + ", " + esc(d.video_enviado) + ", " + (d.opcion_enviada ? Number(d.opcion_enviada) : "NULL") + ", (SELECT id FROM a) RETURNING id AS triaje_log_id"
  : "SELECT NULL::bigint AS triaje_log_id";

d.sql_silencio =
  "INSERT INTO triaje_urgencias_log(telefono, exec_id, mensaje_paciente, gate_red_flags, gate_escala, tipo, confianza, razon, modelo, modo, accion) VALUES (" +
  [esc(ev.phone), esc(ev.exec_id), esc(ev.text), esc(flagsJson) + "::jsonb", "false", esc(d.tipo || tipoEstado), esc(d.confianza || null), esc(d.razon || "humano_atendiendo"), esc(cfg.modelo || null), esc(cfg.modo || "piloto"), "'silencio_humano'"].join(", ") + ") RETURNING id";

return [{ json: d }];
