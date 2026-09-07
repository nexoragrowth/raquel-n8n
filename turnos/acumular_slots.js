// "Acumular P1 / P2 / P3" — Sub-WF "Buscar Horarios Validado" (GuDQ9VmKWZvQnerV)
//
// UN SOLO archivo para los tres nodos: apply_turnos_formato_raquel.py reemplaza el marcador de
// NODO_PREVIO (unica aparicion en el archivo, abajo) por el nombre del nodo Acumular anterior — cadena
// vacia en la primera pagina, que no tiene anterior.
//
// POR QUE EXISTE ESTE NODO (paginado por cursor, 2026-09-07):
// La Dra. pide ofrecer SIEMPRE por lo menos 2 turnos de mañana y 2 de tarde. Dentalink no sabe filtrar
// por franja (`hora_inicio:{gte:"13:00"}` devuelve exactamente lo mismo que sin filtro) y devuelve SIEMPRE
// 10 slots por llamada (limit/page/offset se ignoran), asi que la unica forma de juntar las dos franjas es
// pedir mas paginas. `fecha:{eq:X}` se comporta como ">= X": la pagina siguiente se pide con la fecha del
// ULTIMO slot recibido (no +1 dia, para no perder los horarios que quedaron cortados en ese mismo dia) y
// se deduplica por (fecha, hora_inicio).
//
// ESTO REEMPLAZA EL ESCANEO DIA-POR-DIA que vivia adentro de "Format Slots" (hasta 91 llamadas ~80 s, con
// el token de Dentalink hardcodeado en el jsCode y sumando el MISMO turno 3 veces porque no deduplicaba).
// Ahora las llamadas las hacen nodos httpRequest con la credencial "Header Auth account 3": cero secretos
// en el codigo.
//
// TOPES (medidos contra la agenda REAL el 2026-09-07 con GET read-only, no inventados). Cuantas paginas
// hacen falta para juntar 2 dias de mañana + 2 dias de tarde, arrancando en distintas fechas:
//   desde 2026-09-07 -> 2 paginas (19 slots, 1.71 s)     desde 2026-11-01 -> 3 paginas (21 slots, 2.16 s)
//   desde 2026-10-20 -> 3 paginas (21 slots, 2.25 s)     desde 2026-12-15 -> 3 paginas (21 slots, 2.07 s)
//   desde 2027-01-05 -> 3 paginas (21 slots, 2.14 s)     desde 2027-03-01 -> 3 paginas (21 slots, 2.06 s)
// O sea: el minimo que pide la Dra. YA CONSUME 3 paginas en 5 de las 6 fechas probadas. Con la agenda un
// poco mas ocupada (exigiendo 3 dias por franja) el mismo barrido pide 4 y hasta 5 paginas (2026-12-15:
// 5 paginas / 3.52 s; 2026-10-20: 5 / 3.59 s; 2027-01-05: 5 / 3.25 s).
// POR ESO MAX_PAGINAS = 6 y no 3: con 3 no queda NINGUN margen y, cuando se agota, "Format Slots" omite la
// seccion "Por la tarde" entera y el paciente recibe solo mañanas — que es exactamente la captura que
// motivo el pedido de la Dra. El costo de cada pagina extra es ~0.7 s (medido) contra un turno de agente
// del v6 de 20-34 s: piso 1 llamada ~0.9 s, tipico 2-3 llamadas ~2.2 s, techo 6 llamadas ~4.5 s.
// El corte real casi siempre lo da `completo` (las dos franjas), no el tope.
// MAX_DIAS_HORIZONTE = 120: si el cursor se fue a mas de 4 meses, no tiene sentido seguir paginando.

const NODO_PREVIO = '__NODO_PREVIO__';

const MAX_PAGINAS = 6;
const MAX_DIAS_HORIZONTE = 120;
const MIN_DIAS_POR_FRANJA = 2;   // "por lo menos dos de la mañana y dos de la tarde" (Dra., 07/09)
const CORTE_TARDE = 13;          // mañana = hora_inicio < 13 · tarde = hora_inicio >= 13

const vf = $('Validar fecha').first().json || {};
const prev = NODO_PREVIO ? ($(NODO_PREVIO).first().json || {}) : {};
const respuesta = $input.first().json || {};

const paginas = (Number(prev.paginas) || 0) + 1;
const errores = Array.isArray(prev.errores) ? prev.errores.slice() : [];

// Slots de ESTA pagina. Devuelve null si la llamada fallo (el nodo HTTP tiene continueOnFail:
// el item que llega es {error: ...} o algo que no parsea) -> se sigue con lo que haya, no se rompe.
function slotsDeRespuesta(resp) {
  try {
    if (!resp || resp.error) return null;
    const cuerpo = Array.isArray(resp) ? resp[0] : resp;
    if (!cuerpo) return null;
    let data = cuerpo.data !== undefined ? cuerpo.data : cuerpo;
    if (typeof data === 'string') { try { data = JSON.parse(data); } catch (e) { return null; } }
    if (data && !Array.isArray(data) && Array.isArray(data.data)) data = data.data;
    return Array.isArray(data) ? data : null;
  } catch (e) { return null; }
}

const RE_FECHA = /^(\d{2})\/(\d{2})\/(\d{4})$/;   // Dentalink devuelve dd/mm/yyyy
const RE_HORA = /^(\d{1,2}):(\d{2})/;
const aIso = (dmy) => { const m = RE_FECHA.exec(String(dmy || '')); return m ? m[3] + '-' + m[2] + '-' + m[1] : ''; };
// Hoy la agenda devuelve la hora con cero adelante ('08:00', verificado por GET), pero TODO el orden de
// este nodo y el de "Format Slots" es por comparacion de strings: si algun dia devolviera '8:00', el
// bloque saldria desordenado ('10:00 , 8:00'). Se normaliza una sola vez, aca, en la puerta de entrada.
const normHora = (h) => { const m = RE_HORA.exec(String(h || '')); return m ? m[1].padStart(2, '0') + ':' + m[2] : ''; };

const recibidos = slotsDeRespuesta(respuesta);
if (recibidos === null) errores.push('pagina ' + paginas + ': la agenda no respondio');

const acumulados = Array.isArray(prev.slots) ? prev.slots.slice() : [];
const vistos = new Set(acumulados.map(s => s.fecha + '|' + s.hora_inicio));
let nuevos = 0;
for (const s of (recibidos || [])) {
  const fecha = String(s && s.fecha || '');
  const hora = normHora(s && s.hora_inicio);
  if (!RE_FECHA.test(fecha) || !hora) continue;
  if (Number(s.id_paciente || 0) !== 0) continue;      // ocupado: no se ofrece (defensivo, la API ya filtra)
  const clave = fecha + '|' + hora;
  if (vistos.has(clave)) continue;
  vistos.add(clave);
  acumulados.push({ fecha, hora_inicio: hora, iso: aIso(fecha) });
  nuevos++;
}

acumulados.sort((a, b) => (a.iso + a.hora_inicio).localeCompare(b.iso + b.hora_inicio));

const hora = (s) => parseInt(s.hora_inicio.slice(0, 2), 10);
const manana = acumulados.filter(s => hora(s) < CORTE_TARDE);
const tarde = acumulados.filter(s => hora(s) >= CORTE_TARDE);
const diasManana = new Set(manana.map(s => s.iso)).size;
const diasTarde = new Set(tarde.map(s => s.iso)).size;

const ultimo = acumulados.length ? acumulados[acumulados.length - 1] : null;
const cursor = ultimo ? ultimo.iso : '';
const dias = (a, b) => (!a || !b) ? 0 : Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / 86400000);
const dias_escaneados = Math.max(0, dias(vf.fecha, cursor));

const completo = diasManana >= MIN_DIAS_POR_FRANJA && diasTarde >= MIN_DIAS_POR_FRANJA;
// Se corta apenas estan las dos franjas. Tambien se corta si la pagina no trajo NADA nuevo (el cursor no
// avanzo: pedir otra vez lo mismo seria una llamada al pedo), si fallo la red, si se agoto el horizonte
// o si ya se gastaron las paginas.
const seguir = !completo
  && paginas < MAX_PAGINAS
  && recibidos !== null
  && nuevos > 0
  && !!cursor
  && cursor !== (prev.cursor || '')
  && dias_escaneados < MAX_DIAS_HORIZONTE;

return [{
  json: {
    slots: acumulados,
    cursor,
    paginas,
    completo,
    seguir,
    total_manana: manana.length,
    total_tarde: tarde.length,
    dias_manana: diasManana,
    dias_tarde: diasTarde,
    dias_escaneados,
    errores,
    // pasa derecho para "Format Slots" y para depurar
    fecha_desde: vf.fecha || '',
    parametro_ignorado: !!vf.parametro_ignorado
  }
}];
