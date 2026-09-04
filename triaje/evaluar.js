// ===== triaje/evaluar.js — nodo "Triaje: Evaluar" del v6 (Fase 2, 2026-09-04) =====
// FUENTE ÚNICA: scripts/apply_triaje_fase2_piloto.py lo embebe en n8n con estas sustituciones:
//   - antepone triaje/gate_red_flags.js (define gateRedFlags)
//   - el placeholder SYSTEM_PROMPT_JSON (con guiones bajos dobles) -> JSON del prompt (triaje/prompt_clasificador.md)
// Tests: node tests/test_triaje_nodos.js
//
// Entradas posibles ($input = fila única de "Triaje: Cargar Config"):
//   (A) modo "seguimiento": vino de "Es cierre?"[1] -> Redis GET -> ¿Seguimiento? (hay estado triaje:{phone})
//   (B) modo "nuevo": vino de "Switch sobre Intent"[2] (Router dijo urgencia_dolor)
// Salida: 1 item con ruta_pre = 'clasificar' | 'decidido' | 'normal' (+ campos para Decidir).
// Todo texto que ve el paciente sale de la tabla (cfg.videos / cfg.textos), nunca de acá.

const SYSTEM_PROMPT = __SYSTEM_PROMPT_JSON__;

const DEFAULTS = {
  // Si la config no carga (Postgres caído), estos defaults mantienen el seguimiento seguro.
  regex_no_sirvio: "no (?:me |le )?(?:sirvi[oó]|funcion[oó]|ayud[oó]|result[oó]|alcanz[oó]|pude|puedo|consegu[ií]|entra|queda|se queda|se qued[oó])|sigue (?:igual|pinchando|molestando|saliendo|doliendo|lastimando)|sigo igual|igual sigue|se (?:me )?(?:vuelve a |volvi[oó] a )?sal(?:e|i[oó]|ir)|no (?:tengo|hay|consigo|encuentro) (?:cera|pinza)|(?:est[aá]|qued[oó]) peor",
  regex_cierre: "listo|ok|oka|okey|dale|gracias|graci|perfecto|buen[ií]simo|genial|joya|excelente|ya (?:me )?(?:la |lo )?puse|ya est[aá]|ya (?:me )?qued[oó]|mejor[oó]|me sirvi[oó]|funcion[oó]|solucion|resuelto|muchas gracias|mil gracias|me qued[oó] bien",
  regex_resuelto: "ya (?:me |le )?(?:la |lo )?puse|acomod|coloqu|qued[oó] bien|se arregl|mejor[oó]|me sirvi[oó]|funcion[oó]|solucion|resuelto",
  regex_nuevo_problema: "otra cosa|otro problema|ahora (?:es|tengo) otr|muela|diente|enc[ií]a|golpe|ca[ií]da",
  regex_aparato: "cera|pinza|alambre|bracket|arco|video|ligadura|gom(?:a|ita)|pinch|lastim|molest|duel|dolor|sangr|hinch|se sal|tubo|aparato|frenillo",
  ttl_video_seg: 7200,
  ttl_pregunta_seg: 1800,
  modelo: "gpt-5-mini",
};

// B0/B1/W vienen de triaje/gate_red_flags.js (antepuesto por el script de apply). WS = W tolerante a regex inválida.
const safeRe = (src, flags) => { try { return new RegExp(src, flags); } catch (e) { return null; } };
const WS = (src) => { try { return W(String(src)); } catch (e) { return null; } };
const parseJ = (x, d) => { try { return typeof x === "string" ? JSON.parse(x) : (x === undefined || x === null ? d : x); } catch (e) { return d; } };

const row = $input.first().json || {};
const cfg = {
  activo: row.triaje_activo === true,
  modo: row.modo || "piloto",
  telefonos_piloto: parseJ(row.telefonos_piloto, []) || [],
  red_flags_extra: parseJ(row.red_flags_extra, []) || [],
  regex_no_sirvio: row.regex_no_sirvio || DEFAULTS.regex_no_sirvio,
  regex_cierre: row.regex_cierre || DEFAULTS.regex_cierre,
  regex_nuevo_problema: row.regex_nuevo_problema || DEFAULTS.regex_nuevo_problema,
  regex_aparato: row.regex_aparato || DEFAULTS.regex_aparato,
  textos: parseJ(row.textos, {}) || {},
  aviso_pasivo: row.aviso_pasivo === true,
  ttl_video_seg: Number(row.ttl_video_seg) || DEFAULTS.ttl_video_seg,
  ttl_pregunta_seg: Number(row.ttl_pregunta_seg) || DEFAULTS.ttl_pregunta_seg,
  modelo: row.modelo || DEFAULTS.modelo,
  videos: parseJ(row.videos, []) || [],
  config_ok: row.triaje_activo !== undefined && row.triaje_activo !== null,
};

const pm = $('Preparar Mensaje Final').first().json;
const text = String(pm.text || "").trim();
let ctx = ""; try { ctx = String($('Build Router Context').first().json.ctx || ""); } catch (e) { ctx = ""; }
let estado = null; try { estado = parseJ($('Triaje: Redis GET estado').first().json.triaje_estado, null); } catch (e) { estado = null; }
if (estado && typeof estado !== "object") estado = null;

// Modo de entrada: si el Router/Parse Intent corrió en esta ejecución, venimos del Switch (nuevo).
let modo_entrada = "seguimiento";
try { if ($('Parse Intent').isExecuted) modo_entrada = "nuevo"; } catch (e) { modo_entrada = estado ? "seguimiento" : "nuevo"; }

const videosDe = (tipo) => cfg.videos.filter((v) => v.tipo === tipo).sort((a, b) => Number(a.opcion) - Number(b.opcion));
const base = {
  triaje: true, modo_entrada, phone: String(pm.phone || ""), remoteJid: String(pm.remoteJid || ""), text, ctx, estado, cfg,
  exec_id: String($execution.id || ""), gate_flags: [], gate_escala: false,
};
const decidido = (extra) => [{ json: { ...base, ruta_pre: "decidido", ...extra } }];
const clasificar = (userPrompt, extra) => {
  const llm_body = JSON.stringify({
    model: cfg.modelo,
    messages: [{ role: "system", content: SYSTEM_PROMPT }, { role: "user", content: userPrompt }],
    response_format: { type: "json_object" },
  });
  return [{ json: { ...base, ruta_pre: "clasificar", llm_body, ...extra } }];
};

// ---- Capa 0/3: gate determinístico SIEMPRE (también en seguimientos) ----
const gate = gateRedFlags(text);
for (const src of cfg.red_flags_extra) {
  const re = safeRe(String(src), "iu");
  if (re && re.test(text)) gate.flags.push("extra:" + String(src).slice(0, 24));
}
if (gate.flags.length) {
  return decidido({ gate_flags: gate.flags, gate_escala: true, ruta: "escalar", razon: "gate_red_flags", tipo: estado ? estado.tipo || null : null });
}

// ---- Estado reconstruido desde la memoria si Redis no lo tiene (2ª capa, solo modo nuevo) ----
if (!estado && modo_entrada === "nuevo" && ctx) {
  const partes = ctx.split("\n---\n");
  let ultimoVideo = null;
  for (const p of partes) {
    if (/^BOT: \[TRIAJE (?:CIERRE|ESCALADO)\]/.test(p)) ultimoVideo = null;
    const m = p.match(/^BOT: \[VIDEO ENVIADO — ([a-z_]+), Opción (\d)\]/);
    if (m) ultimoVideo = { tipo: m[1], opcion: Number(m[2]), paso: "video_enviado", origen: "ctx" };
  }
  if (ultimoVideo) estado = ultimoVideo;
  base.estado = estado;
}

// ---- Modo seguimiento (hay estado vigente en Redis, aún no pasó por el Router) ----
if (modo_entrada === "seguimiento") {
  if (!estado || !estado.paso) return [{ json: { ...base, ruta_pre: "normal" } }];
  const reCierre = W(cfg.regex_cierre) || W(DEFAULTS.regex_cierre);
  const reNoSirvio = W(cfg.regex_no_sirvio) || W(DEFAULTS.regex_no_sirvio);
  const reNuevo = W(cfg.regex_nuevo_problema) || W(DEFAULTS.regex_nuevo_problema);
  const reAparato = safeRe(cfg.regex_aparato, "iu") || safeRe(DEFAULTS.regex_aparato, "iu");

  if (estado.paso === "pregunta") {
    if (reCierre && reCierre.test(text) && !(reNoSirvio && reNoSirvio.test(text))) {
      return decidido({ ruta: "cerrar", tipo: estado.tipo || null, razon: "cierre_post_pregunta" });
    }
    const user = "CONTEXTO PREVIO (últimos turnos):\n" + (ctx || "(sin contexto)") +
      "\n\nMENSAJE ORIGINAL DEL PACIENTE:\n" + String(estado.texto_original || "") +
      "\n\nPREGUNTA GUIADA QUE LE HICIMOS:\n" + String(estado.pregunta || "") +
      "\n\nRESPUESTA DEL PACIENTE:\n" + text;
    return clasificar(user, { reclasifica: true, tipo_hint: estado.tipo || null });
  }

  if (estado.paso === "video_enviado") {
    const reResuelto = safeRe(DEFAULTS.regex_resuelto, "iu");
    const esNoSirvio = reNoSirvio && reNoSirvio.test(text);
    const esNuevo = reNuevo && reNuevo.test(text);
    const mencionaAparato = reAparato && reAparato.test(text);
    // Cierre = agradece/cierra, NO dice que no sirvió, y si menciona el aparato es porque lo resolvió ("ya me puse la cera")
    const esCierre = reCierre && reCierre.test(text) && !esNoSirvio && (!mencionaAparato || (reResuelto && reResuelto.test(text)));
    if (esCierre) return decidido({ ruta: "cerrar", tipo: estado.tipo, razon: "cierre_post_video" });
    if (esNoSirvio) {
      if (esNuevo) {
        const user = "CONTEXTO PREVIO (últimos turnos):\n" + (ctx || "(sin contexto)") +
          "\n\nYA SE LE ENVIÓ un video de auto-ayuda por: " + estado.tipo + " (Opción " + estado.opcion + ").\n\nMENSAJE ACTUAL DEL PACIENTE:\n" + text;
        return clasificar(user, { reclasifica: true, tipo_hint: estado.tipo, post_video: true });
      }
      const next = cfg.activo ? videosDe(estado.tipo).find((v) => Number(v.opcion) === (Number(estado.opcion) || 1) + 1) : null;
      if (next) return decidido({ ruta: "video", tipo: estado.tipo, confianza: "alta", video: next, razon: "no_sirvio_opcion_" + estado.opcion });
      return decidido({ ruta: "escalar", tipo: estado.tipo, razon: "no_sirvio_sin_mas_opciones" });
    }
    if (mencionaAparato) {
      // Habla del mismo problema/aparato sin cerrar ni decir que no sirvió (dudas, "ok pero me duele") -> a la doctora, nunca a General.
      return decidido({ ruta: "escalar", tipo: estado.tipo, razon: "seguimiento_no_resuelto" });
    }
    return [{ json: { ...base, ruta_pre: "normal" } }];
  }

  // paso 'escalado' | 'cerrado' | desconocido -> flujo normal (el label humano ya frena si corresponde)
  return [{ json: { ...base, ruta_pre: "normal" } }];
}

// ---- Modo nuevo (Router dijo urgencia_dolor) ----
if (!cfg.config_ok || !cfg.activo || cfg.videos.length === 0) {
  return decidido({ ruta: "escalar", razon: !cfg.config_ok ? "config_no_disponible" : "triaje_inactivo" });
}
if (cfg.telefonos_piloto.length && !cfg.telefonos_piloto.map(String).includes(String(pm.phone))) {
  return decidido({ ruta: "escalar", razon: "fuera_piloto" });
}
const user = "CONTEXTO PREVIO (últimos turnos, puede estar vacío):\n" + (ctx || "(sin contexto)") +
  (estado && estado.paso === "video_enviado" ? "\n\nYA SE LE ENVIÓ un video de auto-ayuda por: " + estado.tipo + " (Opción " + estado.opcion + ")." : "") +
  "\n\nMENSAJE ACTUAL DEL PACIENTE:\n" + text;
return clasificar(user, { reclasifica: false, post_video: !!(estado && estado.paso === "video_enviado") });
