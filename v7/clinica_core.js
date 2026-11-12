// clinica_core.js — v7 · herramientas de CLÍNICA: derivar a la secretaria, pasar a una persona, recepción de pagos, datos para transferir, lista de espera,
// triaje de urgencias y avisos al grupo. Fuente de verdad en el repo (se inlinea en un nodo Code de n8n y se prueba offline).
// (08/10, orquestador + sub-agentes) QUIÉN decide qué quiso decir el paciente es la IA (el orquestador o un sub-agente eligen la acción). Este código
// EJECUTA la acción y arma el texto para el paciente; no lee el mensaje del paciente para juzgar su intención. Se borraron las regex de verificación
// por motivo (pedido de persona, quejas, bajas, urgencias) y esos motivos: lo que está fuera de las 8 tareas va a `derivar` (decisión de Lucas del 08/10).
// Lo único que el código compara con el texto del paciente es un DATO: que la frase que el modelo dice citar en `humano` esté de verdad en el mensaje
// (anti-alucinación). Si no coincide, se deriva igual (aviso ACCIÓN, sin silenciar): falla del lado seguro, nunca deja al paciente hablando solo con el bot.
// Todo lo que sale afuera (avisos, silencio) exige modo === 'vivo' EXPLÍCITO (decisión del 08/10).
const ClinicaCore = (() => {
  const sinT = (x) => String(x || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const tokens = (x) => sinT(x).replace(/[^a-z0-9ñ ]+/g, ' ').split(/\s+/).filter((t) => t.length >= 2);
  const NIVELES = ['FYI', 'ACCION'];
  const lim = (s, n) => String(s || '').trim().slice(0, n);
  // Textos fijos para el paciente (los arma el código; ningún modelo los redacta).
  const TEXTOS = {
    DERIVA: 'Le paso con la secretaria para que lo atienda.',
    DERIVA_INSISTE: 'Ya le pasé su consulta a la secretaria; le responde por este chat.',
    PAGO: 'Recibido. Dejé anotado su aviso de pago; la secretaria lo verifica en su horario de atención.',
    PAGO_YA: 'Recibido, gracias.',
    DATOS_PAGO: 'Le paso los datos para transferir:',
    ESPERA: 'Le dejo anotado a la clínica que quiere adelantar su turno si se libera uno.',
    ESPERA_SIN_TURNO: 'Le dejo anotado a la clínica que busca un turno, por si se libera uno.',
  };
  // (12/11, espejo con mensajes reales, r017) "No se olviden de mí, si hace falta agendo una consulta", SIN turno: el agente lo anotó en lista de espera
  // ("quiere adelantar su turno") y al grupo le iba un FYI falso. La lista de espera es para adelantar un turno o para cuando ninguno de los horarios
  // que Asiri mostró le sirve. Solo se miran DATOS (no la intención del paciente, decisión del 08/10): la lista de turnos que armó el cerebro y el último
  // mensaje de Asiri. Sin `turnos_json` (otros llamadores) todo sigue como antes.
  const sinTurnos = (j) => {
    if (typeof j !== 'string' || !j.trim()) return false;
    try { const t = JSON.parse(j); return Array.isArray(t) && t.length === 0; } catch (x) { return false; }
  };
  const vioHorarios = (u) => /turnos disponibles|siguen libres|tengo a las|por si se libera/i.test(String(u || ''));
  // ¿La cita está en lo que escribió el paciente? Mayoría (≥ 50 %) de sus palabras presentes en el texto crudo normalizado. Dato, no intención.
  function citaEnTexto(cita, texto) {
    const tc = tokens(cita), tp = new Set(tokens(texto));
    if (!tc.length) return false;
    return tc.filter((t) => tp.has(t)).length / tc.length >= 0.5;
  }

  // entrada: { accion:'aviso'|'derivar'|'humano'|'pago'|'datos_pago'|'espera'|'triaje', nivel, texto, motivo, cita_textual, texto_paciente, moneda, modo,
  //            pago_reciente:boolean, avisos_recientes:number, deriva_recientes:number, tel }
  // devuelve { avisar:null|{resumen,tomar}, marcar_pago, limpiar, contar_deriva, triaje:null|{motivo,cita}, resultado:{ ok, texto_para_el_paciente?, ... } }
  function decidir(e) {
    const sombra = e.modo !== 'vivo';
    const res = (resultado, extra) => ({ avisar: null, marcar_pago: false, limpiar: false, contar_deriva: false, triaje: null, resultado, ...(extra || {}) });
    const textual = () => { const tp = lim(e.cita_textual || e.texto_paciente, 200); return tp ? `«${tp}»` : '(mandó un archivo sin texto)'; };

    // Urgencias: el mensaje vuelve al triaje del v6 (videos aprobados por la Dra., pregunta guiada o la doctora). La cita la pone el CÓDIGO con el mensaje
    // completo del paciente (no una paráfrasis del modelo). La marca se deja también en sombra (solo la lee el cerebro de esta ejecución).
    if (e.accion === 'triaje') {
      return res({ ok: true, derivado_a_triaje: true, simulado: sombra || undefined }, { triaje: { motivo: 'derivar_triaje', cita: lim(e.texto_paciente || e.cita_textual, 300) } });
    }
    if (e.accion === 'derivar') {
      // Fuera de las 8 tareas. 1.ª vez: texto fijo + aviso ACCIÓN con la frase textual. Si ya se derivó en los últimos 30 min (contador PROPIO `deriva:`,
      // separado de los avisos técnicos), el paciente insiste: una persona toma el chat y el bot se calla (anti-bucle REAL-09).
      const motivo = lim(e.motivo, 120);
      if (Number(e.deriva_recientes || 0) >= 1) {
        return res({ ok: true, modo_humano: true, simulado: sombra || undefined, texto_para_el_paciente: TEXTOS.DERIVA_INSISTE },
          { contar_deriva: true, ...(sombra ? {} : { avisar: { resumen: `[ACCIÓN] El paciente insiste con algo que Asiri no atiende${motivo ? ' (' + motivo + ')' : ''}: ${textual()}. El bot queda en silencio en este chat hasta que lo reactiven.`, tomar: true }, limpiar: true }) });
      }
      return res({ ok: true, derivado: true, simulado: sombra || undefined, texto_para_el_paciente: TEXTOS.DERIVA },
        { contar_deriva: true, ...(sombra ? {} : { avisar: { resumen: `[ACCIÓN] Fuera de lo que atiende Asiri${motivo ? ' (' + motivo + ')' : ''}: ${textual()}. Contestarle por este chat.`, tomar: false } }) });
    }
    if (e.accion === 'humano') {
      // Pidió hablar con una persona: lo decidió el orquestador. El código solo verifica que la frase citada esté en el mensaje (anti-alucinación).
      if (!citaEnTexto(e.cita_textual, e.texto_paciente)) {
        const d = decidir({ ...e, accion: 'derivar', motivo: 'pidió una persona; la frase no se pudo verificar' });
        d.resultado = { ...d.resultado, degradado: true, motivo: 'no_verificado' };
        return d;
      }
      return res({ ok: true, humano: true, simulado: sombra || undefined, texto_para_el_paciente: TEXTOS.DERIVA },
        sombra ? {} : { avisar: { resumen: `El paciente pidió hablar con una persona: «${lim(e.cita_textual, 160)}»`, tomar: true }, limpiar: true });
    }
    if (e.accion === 'aviso') {
      const nivel = NIVELES.includes(String(e.nivel || '').toUpperCase()) ? String(e.nivel).toUpperCase() : null;
      const texto = lim(e.texto, 400);
      if (Number(e.avisos_recientes || 0) >= 2) return res({ ok: true, ya_avisado: true });
      if (!nivel || texto.length < 5) return res({ ok: false, motivo: 'aviso_invalido' });
      return res({ ok: true, simulado: sombra || undefined }, sombra ? {} : { avisar: { resumen: `[${nivel === 'ACCION' ? 'ACCIÓN' : 'FYI'}] ${texto}`, tomar: false } });
    }
    if (e.accion === 'espera') {
      const texto = lim(e.texto, 300);
      const sinTurno = sinTurnos(e.turnos_json);
      if (sinTurno && !vioHorarios(e.ultimo_asiri)) {
        return res({ ok: false, motivo: 'sin_turno_sin_horarios',
          para_asiri: 'No tiene turnos vigentes y todavía no vio horarios: no se anotó nada. Llamá a buscar_horarios y ofrecéselos; la lista de espera es para cuando ninguno le sirve.' });
      }
      const fyi = sinTurno ? '[FYI] Lista de espera: todavía no tiene turno; busca uno si se libera un lugar.' : '[FYI] Lista de espera: la paciente quiere adelantar su turno si se libera uno.';
      return res({ ok: true, simulado: sombra || undefined, texto_para_el_paciente: sinTurno ? TEXTOS.ESPERA_SIN_TURNO : TEXTOS.ESPERA },
        sombra ? {} : { avisar: { resumen: `${fyi}${texto ? ' ' + texto : ''}`, tomar: false } });
    }
    if (e.accion === 'pago') {
      // Qué es un pago lo decide el modelo (Pagos). El aviso NO afirma "transfirió": muestra las palabras textuales y la secretaria juzga (REAL-05).
      // Ya anotado en los últimos 15 min (REAL-02): no se avisa de nuevo y el texto es corto.
      if (e.pago_reciente) return res({ ok: true, ya_anotado: true, simulado: sombra || undefined, texto_para_el_paciente: TEXTOS.PAGO_YA });
      const base = { ok: true, simulado: sombra || undefined, texto_para_el_paciente: TEXTOS.PAGO };
      if (sombra) return res(base, { marcar_pago: true });   // la marca va a la clave de sombra (v7s:pago:), no avisa a nadie
      return res(base, { avisar: { resumen: `[ACCIÓN] Asiri lo tomó como aviso de pago o comprobante: ${textual()}. Verificar en el chat e imputarlo al turno.`, tomar: false }, marcar_pago: true });
    }
    if (e.accion === 'datos_pago') {
      // La moneda la decide Pagos (la IA). Solo hay datos en pesos: otra moneda queda fuera de alcance y la deriva el cerebro. Los datos los pega el código.
      if (String(e.moneda || 'pesos').toLowerCase() === 'otra') return res({ ok: false, fuera_de_alcance: true, motivo: 'otra_moneda' });
      return res({ ok: true, datos_pago: true, texto_para_el_paciente: TEXTOS.DATOS_PAGO });
    }
    return res({ ok: false, motivo: 'accion_invalida' });
  }
  return { decidir, citaEnTexto, TEXTOS };
})();
if (typeof module !== 'undefined') module.exports = ClinicaCore;
