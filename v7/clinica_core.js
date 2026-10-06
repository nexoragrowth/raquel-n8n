// clinica_core.js — v7 · herramientas de CLÍNICA de Asiri: avisar al grupo, pasar a una persona, comprobantes de pago, lista de espera. Fuente de verdad en el repo.
// Regla central: Asiri solo pasa a una persona (y silencia al bot) por 4 motivos, y el código lo VERIFICA contra el texto literal del paciente.
// Si no se puede verificar, se degrada a un aviso que NO silencia. Avisar nunca silencia. Un error de herramienta no es motivo para derivar.
const ClinicaCore = (() => {
  const sinT = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
  const MOTIVOS = ['pidio_persona', 'queja', 'baja_de_datos', 'urgencia'];
  // Palabras que tienen que aparecer en lo que el paciente escribió, según el motivo que invoca Asiri.
  const VERIF = {
    pidio_persona: /\b(persona|humano|humana|secretaria|doctora|dra|raquel|hablar con|que me llamen|llamenme|llamar|alguien)\b/,
    queja: /\b(queja|reclamo|mal servicio|mala atencion|pesimo|horrible|indignad|molest|enojad|inaceptable|verguenza|nunca me|no puede ser|cansad)\w*/,
    baja_de_datos: /\b(baja|mis datos|borren|eliminen|no me escriban|dejen de escribir|no quiero recibir|no me contacten|desuscrib)\w*/,
    urgencia: /\b(dolor|duele|sangr|hinchaz|hinchad|fiebre|golpe|se (me )?(salio|solto|rompio|despego)|bracket|alambre|aparato|urgenc|infecci|pus|no puedo (comer|abrir))\w*/,
  };
  const NIVELES = ['FYI', 'ACCION'];
  const lim = (s, n) => String(s || '').trim().slice(0, n);

  // entrada: { accion:'aviso'|'humano'|'pago'|'espera', nivel, texto, motivo, cita_textual, texto_paciente, modo, pago_reciente:boolean, tel }
  // devuelve { avisar:null|{resumen,tomar}, marcar_pago:boolean, limpiar:boolean, resultado:{...} }
  function decidir(e) {
    const sombra = e.modo === 'sombra';
    const res = (resultado, extra) => ({ avisar: null, marcar_pago: false, limpiar: false, resultado, ...(extra || {}) });
    if (e.accion === 'aviso') {
      const nivel = NIVELES.includes(String(e.nivel || '').toUpperCase()) ? String(e.nivel).toUpperCase() : null;
      const texto = lim(e.texto, 400);
      if (!nivel || texto.length < 5) return res({ ok: false, motivo: 'aviso_invalido', para_asiri: 'Necesito nivel (FYI o ACCION) y un texto claro de qué pasó y qué hay que hacer.' });
      return res({ ok: true, simulado: sombra || undefined, para_asiri: 'Listo, la clínica fue avisada. Seguí atendiendo al paciente.' }, sombra ? {} : { avisar: { resumen: `[${nivel === 'ACCION' ? 'ACCIÓN' : 'FYI'}] ${texto}`, tomar: false } });
    }
    if (e.accion === 'espera') {
      const texto = lim(e.texto, 300);
      return res({ ok: true, simulado: sombra || undefined, para_asiri: 'Quedó anotado para la clínica. Decile solo "se lo dejo anotado a la clínica": NO prometas que le van a avisar si se libera un turno.' },
        sombra ? {} : { avisar: { resumen: `[FYI] Lista de espera: la paciente quiere adelantar su turno si se libera uno.${texto ? ' ' + texto : ''}`, tomar: false } });
    }
    if (e.accion === 'pago') {
      const base = { ok: true, simulado: sombra || undefined, para_asiri: 'Decile que dejaste anotado su aviso de pago y que, cuando mande el comprobante por este chat, la secretaria lo verifica en su horario de atención. NO digas que ya lo recibimos, NO valides el monto ni digas que el pago ingresó.' };
      if (sombra || e.pago_reciente) return res(base);
      return res(base, { avisar: { resumen: '[ACCIÓN] La paciente avisa que ya transfirió o que manda el comprobante: verificar que llegue por el chat e imputarlo al turno.', tomar: false }, marcar_pago: true });
    }
    if (e.accion === 'humano') {
      const motivo = String(e.motivo || '');
      const cita = sinT(e.cita_textual);
      const paciente = sinT(e.texto_paciente);
      const valido = MOTIVOS.includes(motivo) && cita.length >= 3 && paciente.includes(cita) && VERIF[motivo].test(paciente);
      if (!valido) {
        // No se puede verificar: NO se silencia. Se avisa a la clínica y se sigue atendiendo.
        return res({ ok: false, degradado: true, motivo: 'no_verificado', para_asiri: 'No pude verificar ese pedido con lo que escribió el paciente, así que NO lo pasé a una persona. Avisé a la clínica. Seguí atendiéndolo vos y resolvé lo que te pide.' },
          sombra ? {} : { avisar: { resumen: `[ACCIÓN] Asiri quiso pasar a una persona (${motivo || 'sin motivo'}) pero no se pudo verificar con el mensaje. Revisar la conversación.`, tomar: false } });
      }
      const etiqueta = { pidio_persona: 'pidió hablar con una persona', queja: 'hizo una queja', baja_de_datos: 'pidió la baja de sus datos', urgencia: 'tiene una urgencia (dolor, sangrado o aparato roto)' }[motivo];
      return res({ ok: true, simulado: sombra || undefined, para_asiri: motivo === 'urgencia'
        ? 'Ya avisé a la clínica de la urgencia y el chat queda para una persona. Decile con calma que la doctora se va a comunicar y que consulte con ella; NO des indicaciones ni opines sobre el síntoma.'
        : 'Ya avisé a la clínica y una persona toma el chat. Decíselo con amabilidad y no sigas la conversación sobre turnos.' },
        sombra ? {} : { avisar: { resumen: `El paciente ${etiqueta}: «${lim(e.cita_textual, 160)}»`, tomar: true }, limpiar: true });
    }
    return res({ ok: false, motivo: 'accion_invalida', para_asiri: 'Acción de clínica inválida.' });
  }
  return { decidir, MOTIVOS };
})();
if (typeof module !== 'undefined') module.exports = ClinicaCore;
