(() => {
  // media/actualizar_memoria_staff.js — expresion del campo `query` del nodo Postgres
  // "Media: Actualizar memoria (staff)" del v6. scripts/apply_media_fromme.py la embebe entera
  // (por eso el archivo es SOLO la expresion, sin cabecera afuera, y no puede contener llaves
  // dobles: cerrarian la expresion de n8n antes de tiempo). Tests: tests/test_media_fromme.js.
  //
  // DONDE VIVE: ultimo nodo de la cadena Media del STAFF, que cuelga DESPUES del silenciamiento:
  //   Es fromMe?[0] -> Build fromMe AI memory -> Postgres - Save fromMe -> CW Search Contact ->
  //   CW Extract Conv -> CW Get Conversations -> CW Pick Conv -> CW Set Label humano   <- calla al bot
  //   -> Media: Preparar (staff) -> ¿Hay archivo? -> Subir a Storage -> ¿Subida OK?
  //   -> Media: Registrar (staff) -> Media: Actualizar memoria (staff)   (este nodo)
  //
  // QUE HACE: la fila de memoria del mensaje saliente YA esta escrita (la escribio "Postgres - Save
  // fromMe" segundos antes, con el TAG de atencion humana y el caption o el placeholder). Este UPDATE
  // le agrega al final del `content` el mismo token ' [MEDIA:<id>]' que usa la rama del paciente, mas
  // `media_id` y `media_tipo` en `additional_kwargs`, para que el panel resuelva el adjunto real.
  //
  // POR QUE UN UPDATE Y NO ARMAR EL CONTENT ANTES: porque el content se escribe ANTES de subir el
  // archivo, y eso no es negociable — entre "Es fromMe?" y "CW Set Label humano" (lo UNICO que calla
  // al bot en esta rama) no puede haber una subida a Storage de hasta 30 s: el pipeline del paciente
  // termina en ~25-30 s y el bot escribiria encima de la doctora (incidente Mariela, 2026-05-09).
  // "Build fromMe AI memory" no se toca: la fila que escribe es byte a byte la de hoy.
  //
  // GARANTIAS (las verifica tests/test_media_fromme.js):
  //   a) toca UNA sola fila: `id = <el que devolvio el INSERT>` y nada mas (sin id -> NOOP);
  //   b) idempotente: no agrega el token si el content ya lo tiene (NOT LIKE con [MEDIA:);
  //   c) si "Media: Registrar (staff)" no devolvio la fila (error, otro id, otro bucket, sin archivo)
  //      no hace nada: devuelve un SELECT no-op. El nodo es un Postgres y no puede saltearse a si
  //      mismo, asi que el gate vive en el SQL;
  //   d) sin `queryReplacement`: los valores se escapan aca (mismo `esc` que triaje/decidir.js, que
  //      ademas saca los '$' porque pg-promise los interpreta como parametros). Un caption con coma
  //      reventaria el queryReplacement de n8n (leccion 5/9). Los unicos valores que llegan al SQL
  //      son el id (16 hex) y el tipo (whitelist): ningun texto libre del paciente ni de la doctora.
  //
  // El nodo va con onError: continueRegularOutput; si el UPDATE falla, la fila queda como hoy (sin
  // token) y el panel muestra el chip de siempre.
  const NOOP = 'SELECT 1 WHERE false';
  const HEX16 = /^[0-9a-f]{16}$/;
  const TIPOS = ['image', 'video', 'audio', 'document', 'sticker'];

  // Escape de valores. Duplica la comilla simple y SACA los '$' partiendo el literal
  // (' || chr(36) || '), porque pg-promise interpreta $N como un parametro posicional.
  // OJO si se agregan valores: ese truco rompe el literal en varios trozos unidos por '||', y '::'
  // liga MAS FUERTE que '||'. Un valor con '$' pegado a un cast quedaria como
  // 'x' || chr(36) || ('y'::jsonb) — otro SQL. Hoy no puede pasar (lo unico que va pegado a
  // '::jsonb' son las kwargs: un id de 16 hex y un tipo del whitelist, ninguno con '$'), y el test
  // 5c de tests/test_media_fromme.js lo vigila. Si alguna vez entra un valor libre en esa posicion,
  // envolverlo en parentesis: (esc(v))::jsonb.
  const esc = function (v) {
    if (v === null || v === undefined) return 'NULL';
    return "'" + String(v).replace(/'/g, "''").split('$').join("' || chr(36) || '") + "'";
  };
  // $('X') tira si el nodo no ejecuto en esta ejecucion: aca eso significa "no hay nada que actualizar".
  const nodo = function (n) {
    try {
      const x = $(n).first().json;
      return (x && typeof x === 'object') ? x : {};
    } catch (e) {
      return {};
    }
  };

  const P = nodo('Media: Preparar (staff)');
  const R = ($json && typeof $json === 'object') ? $json : {};
  const id = String(P.id || '');

  // Mismo criterio que media/marcar_expr.js en la rama del paciente (+ el formato del id, que va crudo
  // al SQL): el item de entrada tiene que ser LA FILA que devolvio el INSERT en media_entrantes
  // (RETURNING *), del bucket correcto y con el id del archivo que preparo ESTA ejecucion.
  const registrado = P.hay_archivo === true && HEX16.test(id) && !R.error
    && R.bucket === 'pacientes-media' && !!R.id && R.id === id;
  if (!registrado) return NOOP;

  const tipo = TIPOS.indexOf(String(P.tipo || '')) >= 0 ? String(P.tipo) : null;
  const token = ' [MEDIA:' + id + ']';
  const kwargs = JSON.stringify({ media_id: id, media_tipo: tipo });

  // Fila a tocar: UNICAMENTE el id que devolvio "Postgres - Save fromMe" con su RETURNING id
  // (n8n/node-postgres traen los bigint como STRING: "6516", no 6516 — verificado en la salida real de
  // "Check Session Age"). Se valida como digitos y se inyecta crudo: es un entero, no lleva comillas.
  //
  // FALLA CERRADO A PROPOSITO (2026-09-07). Habia aca un fallback heuristico — "la ultima fila de
  // ESTA sesion cuyo content sea exactamente el que acaba de escribir Build fromMe AI memory" — y se
  // saco: bajo concurrencia real le pega el token a la fila EQUIVOCADA. Si la doctora manda dos
  // adjuntos SIN caption al mismo paciente y el INSERT de la ejecucion B entra antes del UPDATE de la
  // A, las dos filas tienen el content identico (TAG + placeholder) y el ORDER BY id DESC LIMIT 1 de
  // A toma la fila de B (y despues B toma la de A): dos tokens cruzados, cada burbuja con la foto de
  // la OTRA. En un chat medico mostrar la foto equivocada es peor que no mostrar ninguna.
  // Ademas era codigo muerto: el RETURNING id siempre llega (si el INSERT fallara, el nodo no tiene
  // onError y la ejecucion se corta antes de llegar hasta aca).
  // Sin id no hay a que fila pegarle con CERTEZA -> NOOP: la fila queda como hoy, sin token, y el
  // panel muestra el chip de siempre. La regresion visible es "el adjunto no se linkea", nunca
  // "el adjunto se linkea mal".
  const filaId = String(nodo('Postgres - Save fromMe').id || '');
  if (!/^[1-9][0-9]{0,17}$/.test(filaId)) return NOOP;
  const donde = 'id = ' + filaId;

  return 'UPDATE n8n_chat_histories SET message = jsonb_set(jsonb_set(message, '
    + esc('{content}') + ", to_jsonb((message->>'content') || " + esc(token) + ')), '
    + esc('{additional_kwargs}') + ", COALESCE(message->'additional_kwargs', '{}'::jsonb) || "
    + esc(kwargs) + '::jsonb) WHERE ' + donde
    + " AND message->>'content' NOT LIKE '%[MEDIA:%' RETURNING id";
})()
