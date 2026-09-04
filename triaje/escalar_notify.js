// ===== triaje/escalar_notify.js — nodo "Triaje: Escalar (notify-grupo)" del v6 (Fase 2, 2026-09-04) =====
// FUENTE ÚNICA (la embebe scripts/apply_triaje_fase2_piloto.py). Tests: node tests/test_triaje_nodos.js
//
// Corre DESPUÉS de "Triaje: Enviar Texto Escalada": el paciente ya recibió el canned, recién ahora
// se avisa al grupo (el Helper aplica el label 'humano' y el bot queda en silencio, como hoy).
// Mismo patrón que Gate Pago Tratamiento / Gate Error Tecnico (this.helpers.httpRequest a notify-grupo).

const p = $('Triaje: Preparar Escalada').first().json;
const esc = (v) => (v === null || v === undefined) ? "NULL" : "'" + String(v).replace(/'/g, "''").split("$").join("' || chr(36) || '") + "'";

let notify_ok = false, notify_error = "";
try {
  await this.helpers.httpRequest({
    method: "POST",
    url: "https://n8n.raquelrodriguez.com.ar/webhook/notify-grupo",
    qs: { phone: p.phone, resumen: p.resumen },
    json: true,
  });
  notify_ok = true;
} catch (e) {
  notify_error = String((e && e.message) || e).slice(0, 200);
  console.log("[TRIAJE] notify-grupo fallo:", notify_error);
}

let texto_ok = true;
try {
  const r = $('Triaje: Enviar Texto Escalada').first().json || {};
  texto_ok = !!(r.data && r.data.Info && r.data.Info.ID);
} catch (e) { texto_ok = false; }

const razonFinal = p.razon + (notify_ok ? "" : " | NOTIFY_FALLO: " + notify_error) + (texto_ok ? "" : " | texto_no_enviado");
const sql =
  "WITH h AS (INSERT INTO n8n_chat_histories(session_id, message) VALUES (" + esc(p.phone) + ", " + esc(p.human_row) + "::jsonb) RETURNING id), " +
  "a AS (INSERT INTO n8n_chat_histories(session_id, message) SELECT " + esc(p.phone) + ", " + esc(p.ai_row) + "::jsonb FROM h RETURNING id) " +
  "INSERT INTO triaje_urgencias_log(telefono, exec_id, mensaje_paciente, gate_red_flags, gate_escala, tipo, confianza, razon, modelo, modo, accion, video_enviado, opcion_enviada, chat_history_id) VALUES (" +
  [esc(p.phone), esc(p.exec_id), esc(p.texto_paciente), esc(p.flags_json) + "::jsonb", p.gate_escala ? "true" : "false", esc(p.tipo), esc(p.confianza), esc(razonFinal), esc(p.modelo), esc(p.modo), "'escalado'", esc(p.video_enviado), p.opcion_enviada ? Number(p.opcion_enviada) : "NULL", "(SELECT id FROM a)"].join(", ") +
  ") RETURNING id";

return [{ json: { ...p, notify_ok, notify_error, texto_ok, sql } }];
