// health_core.js — decisión del Health Check (n8n "Yjl6kyLnALhIfbFX"). Fuente de verdad en el repo; scripts/apply_health_check_autoreparable.py la inlinea.
// Incidente 06-08/10/2026: la instancia `raquel` de Evolution GO quedó CONECTADA pero con `webhook: ""` → 2 días sin que entre un solo mensaje a n8n y el
// Health Check (que solo miraba `connected`) dijo "healthy". Lucas: "no puede volver a pasar; en febrero la doctora queda sola" → detectar Y auto-reparar.
// Este módulo NO hace red: decide. Los nodos de n8n hacen los pedidos y le pasan las respuestas. Nunca devuelve ni arma texto con el token de la instancia.
//   evaluar()           → ¿hay que reparar el webhook/eventos? + líneas de alerta + estado (staticData: anti-spam y corte de reintentos).
//   cuerpoReparacion()  → body del POST /instance/connect: pone el webhook y CONSERVA los eventos y rabbitmq/websocket/nats actuales
//                         (Connect de Evolution GO pisa esos 5 campos con lo que venga en el body).
//   verificar()         → después del POST y la re-lectura de /instance/all: [AUTO-REPARADO] o [ACCIÓN], y actualiza el corte de reintentos.
//   salida()            → el item que espera el resto del workflow: { healthy, skip_alert, alert_message, remoteJid } (misma forma que el Evaluar Health viejo).
// OJO — WEBHOOK está fijo acá: si alguna vez se cambia la URL del webhook a propósito (v7, secreto por clínica, etc.), cambiar WEBHOOK PRIMERO y
// volver a aplicar scripts/apply_health_check_autoreparable.py; si no, el Health Check la "repara" de vuelta a esta en 30 min.
// OJO — "sin tráfico" lee mensajes_entrantes_live, que hoy solo escribe el nodo "Inbox Live" del v6 (y solo mensajes con texto). Si se apaga el v6 o se
// pasa al v7 sin ese nodo, esta alerta salta cada 6 h hábiles: el cutover al v7 tiene que seguir escribiendo esa tabla (o cambiar la consulta).
const HealthCore = (() => {
  const INSTANCIA = 'raquel';
  const WEBHOOK = 'https://n8n.raquelrodriguez.com.ar/webhook/evolution-v2';
  const EVENTO = 'MESSAGE';                            // sin este evento suscripto no entra ningún mensaje aunque el webhook esté bien
  const ALERTA_A = '5491161461034@s.whatsapp.net';   // el mismo destino que tenía el Health Check (Lucas)
  const TZ_OFFSET_H = -3;                              // America/Argentina/Jujuy: UTC-3 todo el año (sin horario de verano)
  const HORARIO = { desde: 9, hasta: 20 };            // lun-vie 09:00-20:00
  const SIN_TRAFICO_H = 6;                             // horas HÁBILES sin ningún mensaje entrante → alerta (33 días reales: 0 falsas alarmas con 6)
  const ANTISPAM_H = 6;                                // como máximo 1 alerta de cada tipo "repetible" cada 6 h
  const REP_MAX_FALLAS = 3;                            // después de 3 reparaciones fallidas seguidas...
  const REP_PAUSA_H = 2;                               // ...se reintenta como máximo 1 vez cada 2 h
  const REP_REPETIDAS = 2;                             // 2+ reparaciones exitosas en 24 h → algo lo está borrando: avisar que hay que buscar la causa
  const CONSULTA_MAX_FALLAS = 4;                       // 4 chequeos seguidos sin poder leer la tabla → avisar (1 vez por día)
  const H = 3600 * 1000;
  // Feriados nacionales (no laborables incluidos) + 23/08 (Éxodo Jujeño, provincial). Se tratan como fin de semana para "sin tráfico".
  // Los puentes turísticos 2027 todavía no están decretados: agregarlos cuando salgan (un feriado de menos = como mucho 1 falsa alarma).
  const FERIADOS = new Set([
    '2026-10-12', '2026-11-23', '2026-12-07', '2026-12-08', '2026-12-25',
    '2027-01-01', '2027-02-08', '2027-02-09', '2027-03-24', '2027-03-25', '2027-03-26', '2027-04-02', '2027-05-25', '2027-06-21',
    '2027-07-09', '2027-08-16', '2027-08-23', '2027-10-11', '2027-12-08',
  ]);

  const local = (ms) => new Date(ms + TZ_OFFSET_H * H);   // "reloj de pared" de Jujuy leído con getUTC*
  const habil = (paredMs) => { const d = new Date(paredMs); const dow = d.getUTCDay(); return dow >= 1 && dow <= 5 && !FERIADOS.has(d.toISOString().slice(0, 10)); };
  function enHorario(ms) {
    const d = local(ms); const h = d.getUTCHours() + d.getUTCMinutes() / 60;
    return habil(d.getTime()) && h >= HORARIO.desde && h < HORARIO.hasta;
  }
  // Horas de horario de atención transcurridas entre dos instantes. Así el lunes 09:00 no "lleva 60 h sin mensajes" por el fin de semana,
  // ni cada mañana a las 09:00 por la noche anterior.
  function horasHabiles(desdeMs, hastaMs) {
    if (!(hastaMs > desdeMs)) return 0;
    const a = desdeMs + TZ_OFFSET_H * H, b = hastaMs + TZ_OFFSET_H * H;   // en "ms de pared"
    let total = 0;
    for (let dia = Math.floor(a / (24 * H)) * 24 * H; dia < b; dia += 24 * H) {
      if (!habil(dia)) continue;
      const ini = Math.max(a, dia + HORARIO.desde * H), fin = Math.min(b, dia + HORARIO.hasta * H);
      if (fin > ini) total += fin - ini;
    }
    return total / H;
  }

  // JSON para el texto de "Detalle" con los secretos tapados (Evolution devuelve el token de cada instancia y el QR).
  const seguro = (x) => JSON.stringify(x === undefined ? {} : x, (k, v) => (/^(token|apikey|qrcode|password|authorization)$/i.test(k) ? '***' : v));
  const eventos = (inst) => String((inst && inst.events) || '').split(',').map((s) => s.trim().toUpperCase()).filter(Boolean);
  const eventosOk = (inst) => eventos(inst).some((x) => x === EVENTO || x === 'ALL');
  const formatoOk = (inst) => !!inst && typeof inst === 'object' && 'webhook' in inst && 'events' in inst && 'connected' in inst;
  const instanciaOk = (inst) => !!inst && inst.connected === true && inst.webhook === WEBHOOK && eventosOk(inst);
  const problema = (inst) => [inst.webhook !== WEBHOOK ? 'webhook ' + (inst.webhook ? 'cambiado' : 'vacío') : null,
    !eventosOk(inst) ? `sin el evento ${EVENTO} (events: "${String(inst.events || '')}")` : null].filter(Boolean).join(' y ');

  function dentalinkOk(d) { d = d || {}; return !d.error && (d.id !== undefined || d.data !== undefined); }   // la misma regla que el Health Check viejo

  // Body del POST /instance/connect: el webhook correcto + lo que la instancia ya tenía (para no borrar eventos ni rabbitmq/websocket/nats).
  function cuerpoReparacion(inst) {
    inst = inst || {};
    const subs = eventos(inst).filter((x) => x !== 'ALL');
    if (!subs.includes(EVENTO)) subs.unshift(EVENTO);
    const b = { webhookUrl: WEBHOOK, subscribe: subs };
    for (const k of ['rabbitmqEnable', 'websocketEnable', 'natsEnable']) b[k] = inst[k] == null ? '' : String(inst[k]);
    return b;
  }

  // e: { dentalink, evolution (body de GET /instance/all), ultimo (max(created_at) de mensajes_entrantes_live | null), consultaOk, ahora (ms), estado (staticData) }
  function evaluar(e) {
    const ahora = Number(e.ahora); const estado = { ...(e.estado || {}) };
    const lineas = []; let reparar = false; let instanciaId = null; let cuerpo = null;
    if (!dentalinkOk(e.dentalink)) {
      lineas.push('❌ Dentalink API no responde como esperado');
      lineas.push('   Detalle: ' + seguro(e.dentalink).substring(0, 200));
    }
    const ev = e.evolution || {};
    const lista = Array.isArray(ev.data) ? ev.data : null;
    const inst = lista ? lista.find((i) => i && i.name === INSTANCIA) : null;
    let vigilarTrafico = false;   // "sin tráfico" solo cuando nada de lo de arriba ya explica el problema
    if (!lista) {
      lineas.push('[ACCIÓN] Evolution (WhatsApp) no responde: el servidor evo.raquelrodriguez.com.ar no devolvió la lista de instancias.');
      lineas.push('   Detalle: ' + seguro(ev).substring(0, 200));
    } else if (!inst) {
      lineas.push(`[ACCIÓN] La instancia de WhatsApp "${INSTANCIA}" no existe en Evolution (¿la borraron o la renombraron?). El bot no recibe mensajes. Avisar a soporte.`);
    } else if (!formatoOk(inst)) {
      // Evolution cambió la forma de la respuesta (p. ej. una versión nueva renombró `webhook`): NO reparar a ciegas (sería un POST cada 30 min para siempre).
      if (ahora - (Number(estado.ultimaAlertaFormato) || 0) >= ANTISPAM_H * H) {
        const faltan = ['webhook', 'events', 'connected'].filter((k) => !(k in inst)).join(', ');
        lineas.push(`[ACCIÓN] Evolution cambió el formato de su respuesta (falta: ${faltan}): el Health Check ya no puede revisar ni reparar el webhook. Avisar a soporte.`);
        estado.ultimaAlertaFormato = ahora;
      }
      vigilarTrafico = inst.connected === true;
    } else if (inst.connected !== true) {
      lineas.push('[ACCIÓN] WhatsApp desconectado: hay que escanear el QR en el panel (Conversaciones → banner de WhatsApp) con el celular de la clínica. Mientras tanto el bot no recibe ni manda mensajes.');
      if (inst.disconnect_reason) lineas.push('   Motivo: ' + String(inst.disconnect_reason).substring(0, 160));
      if (!instanciaOk({ ...inst, connected: true })) lineas.push('   (Además: ' + problema(inst) + '. Se repone solo en el próximo chequeo después de reconectar.)');
    } else if (!instanciaOk(inst)) {
      const fallas = Number(estado.repFallas) || 0;
      const ultimoIntento = Number(estado.repUltimoIntento) || 0;
      if (fallas >= REP_MAX_FALLAS && ahora - ultimoIntento < REP_PAUSA_H * H) {
        // Corte de reintentos: no martillar Evolution con un POST cada 30 min si la reparación falla siempre (token cambiado, bug, etc.).
        if (ahora - (Number(estado.repUltimaAlertaPausa) || 0) >= ANTISPAM_H * H) {
          lineas.push(`[ACCIÓN] Webhook de WhatsApp roto (${problema(inst)}) y la auto-reparación falló ${fallas} veces seguidas: el bot NO recibe mensajes. Se reintenta solo cada ${REP_PAUSA_H} h. Correr scripts/apply_webhook_evolution.py o avisar a soporte.`);
          estado.repUltimaAlertaPausa = ahora;
        }
      } else {
        reparar = true; instanciaId = inst.id || null; cuerpo = cuerpoReparacion(inst);
        estado.repUltimoIntento = ahora;
      }
    } else {
      estado.repFallas = 0;   // se ve sano: se levanta el corte de reintentos
      vigilarTrafico = true;
    }
    // La consulta a la base: si falla siempre, la alerta de "sin tráfico" queda apagada en silencio → avisar 1 vez por día.
    if (e.consultaOk) estado.consultaFallas = 0;
    else {
      estado.consultaFallas = (Number(estado.consultaFallas) || 0) + 1;
      if (estado.consultaFallas >= CONSULTA_MAX_FALLAS && ahora - (Number(estado.ultimaAlertaConsulta) || 0) >= 24 * H) {
        lineas.push(`[AVISO] Hace ${estado.consultaFallas} chequeos que no puedo leer mensajes_entrantes_live (nodo "Ultimo Entrante"): la alerta de "no entra ningún mensaje" está apagada. Revisar la credencial Postgres o la tabla.`);
        estado.ultimaAlertaConsulta = ahora;
      }
    }
    // SIN TRÁFICO: red de seguridad para lo que el chequeo del webhook no ve (instancia "sorda", Evolution que no entrega, etc.).
    let sinTrafico = null;
    if (vigilarTrafico && e.consultaOk && enHorario(ahora)) {
      const ult = e.ultimo ? new Date(e.ultimo).getTime() : NaN;
      const horas = isFinite(ult) ? horasHabiles(ult, ahora) : Infinity;
      const ultimaAlerta = Number(estado.ultimaAlertaSinTrafico) || 0;
      if (horas >= SIN_TRAFICO_H && ahora - ultimaAlerta >= ANTISPAM_H * H) {
        const desde = isFinite(ult) ? `hace ${Math.floor((ahora - ult) / H)} h (${Math.floor(horas)} h en horario de atención)` : 'nunca (la tabla está vacía)';
        lineas.push(`[ACCIÓN] No entra ningún mensaje desde ${desde} aunque WhatsApp figura conectado: revisar webhook/Evolution. Probar mandando un WhatsApp al número de la clínica.`);
        estado.ultimaAlertaSinTrafico = ahora;
        sinTrafico = horas;
      }
    }
    return { reparar, instanciaId, cuerpo, lineas, estado, sinTrafico };
  }

  // r: { reparacion: { status, error } (del POST /instance/connect), recheck (body de GET /instance/all después del POST), estado (staticData), ahora (ms) }
  function verificar(r) {
    const ahora = Number(r.ahora) || 0; const estado = { ...(r.estado || {}) };
    const rep = r.reparacion || {}; const ev = (r.recheck || {});
    const lista = Array.isArray(ev.data) ? ev.data : [];
    const inst = lista.find((i) => i && i.name === INSTANCIA);
    const ok = instanciaOk(inst);
    if (ok) {
      estado.repFallas = 0;
      const exitos = (Array.isArray(estado.repExitos) ? estado.repExitos : []).map(Number).filter((t) => t && ahora - t < 24 * H);
      exitos.push(ahora); estado.repExitos = exitos;
      const lineas = ['[AUTO-REPARADO] El webhook de WhatsApp estaba vacío/cambiado; se repuso solo. No hace falta hacer nada.'];
      if (exitos.length >= REP_REPETIDAS) lineas.push(`[ACCIÓN] Es la ${exitos.length}.ª vez en 24 h que hay que reponer el webhook: algo lo está borrando (¿reconexión con QR desde el panel o desde el manager de Evolution?). Avisar a soporte; cada vez se pierden hasta 30 min de mensajes.`);
      return { ok, lineas, linea: lineas.join('\n'), estado };
    }
    estado.repFallas = (Number(estado.repFallas) || 0) + 1;
    const porque = [];
    if (rep.error || (rep.status && (rep.status < 200 || rep.status >= 300))) porque.push(`el pedido de reparación respondió ${rep.status || 'error'}${rep.error ? ' (' + String(rep.error).substring(0, 120) + ')' : ''}`);
    if (!inst) porque.push('no pude releer la instancia');
    else {
      if (inst.webhook !== WEBHOOK || !eventosOk(inst)) porque.push('sigue ' + problema(inst));
      if (inst.connected !== true) porque.push('la instancia quedó desconectada');
    }
    const pausa = estado.repFallas >= REP_MAX_FALLAS ? ` Falló ${estado.repFallas} veces seguidas: desde ahora se reintenta solo cada ${REP_PAUSA_H} h.` : '';
    const linea = '[ACCIÓN] Webhook de WhatsApp roto y no se pudo reparar: ' + (porque.join('; ') || 'motivo desconocido') + '. El bot NO recibe mensajes. Correr scripts/apply_webhook_evolution.py o avisar a soporte.' + pausa;
    return { ok, lineas: [linea], linea, estado };
  }

  function salida(lineas, ahoraMs) {
    if (!lineas || !lineas.length) return { healthy: true, skip_alert: true };
    const soloReparado = lineas.every((l) => l.startsWith('[AUTO-REPARADO]'));
    const cab = soloReparado ? '🛠️ *Áurea — Health Check* 🛠️' : '🚨 *Áurea — Health Check FAIL* 🚨';
    return { healthy: soloReparado, skip_alert: false, alert_message: [cab, '', ...lineas, '', 'Hora: ' + new Date(ahoraMs).toISOString()].join('\n'), remoteJid: ALERTA_A };
  }

  return { evaluar, verificar, salida, cuerpoReparacion, enHorario, horasHabiles, seguro, INSTANCIA, WEBHOOK, EVENTO };
})();
if (typeof module !== 'undefined') module.exports = HealthCore;
