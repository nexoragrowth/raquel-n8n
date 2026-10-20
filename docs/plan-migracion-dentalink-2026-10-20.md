# Plan: migración completa de Dentalink al sistema propio (Supabase v3, esquema `agenda`)

**Fecha:** martes 20/10/2026 · **Para:** la sesión principal y Lucas · **Estado:** preparado y probado offline. **No se aplicó nada** en Supabase ni en n8n. Dentalink se leyó solo con GET.

**Base:** una extracción completa de solo lectura de la API de Dentalink (20/10, de 00:28 a 01:33, de noche: 1.745 pedidos y 0 respuestas 429). Se suman el backlog maestro del 19/10 (§3.6, AGE-01 a AGE-07; decisiones C11, C12 y C13; SEG-17) y el plan del 13/10 (§4 y Anexos A y B). Este documento **no reemplaza** esos criterios: deja lista la **copia de los datos** y la lista exacta de lo que hay que cambiar para el corte.

**Entregables (todos en el repo, sin datos de pacientes):**
- `sql/2026-10-20_dentalink_espejo.sql`: esquema `agenda` con 27 tablas. Lo aplica `scripts/apply_dentalink_espejo_esquema.py`.
- `scripts/migrar_dentalink.py`: extracción, curado y carga idempotente. Por defecto simula.
- Pruebas offline: `tests/test_migracion_dentalink_espejo.mjs` (PGlite) y `tests/test_migrar_dentalink_curado.py`.
- Reporte agregado de la simulación: `docs/migracion-dentalink-simulacion-2026-10-20.json`.

---

## 0. En 8 líneas

1. Dentalink tiene **685 fichas, 9.281 citas (11/2022 a 08/2027), 689 planes con 5.701 prestaciones, 4.175 pagos, 305 cajas y 5.313 evoluciones clínicas**. Además, 990 prestaciones de catálogo, 21 estados, 2 profesionales (1 activo) y 22 usuarios.
2. Todo eso se puede copiar por la API, salvo **bloqueos y feriados** (no hay ruta), el **historial de estados** de cada cita (tampoco) y las **tareas** (el token no tiene permiso). Los **archivos adjuntos** existen (3 de 30 fichas en la muestra) y se leen ficha por ficha.
3. **El "dale" de la Dra. es la firma del contrato de tratamiento de datos (SEG-17).** Antes del contrato se copia solo la ocupación de la agenda, sin ningún dato de pacientes (`--fase ocupacion`, C12 a). Después, todo lo personal y administrativo (`--fase pacientes`). La historia clínica, solo si ella decide migrarla (`--fase clinica`).
4. La copia es **idempotente**. Cada fila conserva su id de Dentalink (`id = dentalink_id`), así que los recordatorios, la memoria y el panel siguen apuntando bien después del corte. Se puede correr todas las noches hasta el día del corte (completa en unos 55 minutos, incremental en unos 8).
5. **Calidad:** el 94% de los celulares es válido después de normalizarlos y el 88% de los DNI está bien. Hay 15 fichas que parecen duplicadas, 89 celulares compartidos por familias, 26 fichas dadas de alta por el bot y 54 nacimientos de relleno (01/01/1900). No hay ninguna clave huérfana.
6. **El estado 15 "Notificado por WhatsApp"** se pone en horario de atención y, en 100 de 102 casos, 8 días o más antes del turno, o sea en el momento de la reserva. No lo ponen nuestros recordatorios (24 y 72 h): parece el aviso de reserva de Dentalink. Hay que confirmarlo antes de apagarlo.
7. Para el corte hay que cambiar **4 herramientas del v7, 2 sub-workflows, el v6, un clon de Recordatorios, el Health Check y 4 archivos del panel** (lista en el §8). Con funciones `agenda.api_*` que devuelven la misma forma que Dentalink, la lógica de `v7/*_core.js` no cambia.
8. El día del corte lleva unas **3 horas, un sábado**. Volver atrás, menos de 15 minutos. El corte sigue siendo **no antes del 01/03/2027** y con los 14 criterios del §4.4 del plan del 13/10.

---

## 1. Inventario de Dentalink (solo números)

**API:** `https://api.dentalink.healthatom.com/api/v1`, header `Authorization: Token …` (el token del panel, `DENTALINK_TOKEN` en `.env.local`). Paginación por cursor firmado, de 50 por página (`links.next`, que conserva el filtro `q`). **Límite medido: `X-RateLimit-Limit: 60` por minuto**, compartido con el bot, los recordatorios y el panel. Esto afina el "429 después de unos 40 seguidos" de C11. Los filtros `q={"campo":{"gte":…}}` funcionan sobre `citas.fecha_actualizacion`, `citas.fecha`, `evoluciones.fecha_registro`, `pagos.fecha_recepcion`, `tratamientos.fecha` y `pacientes.fecha_afiliacion`.

### 1.1 Entidades que responden

| Entidad (ruta) | Filas | Rango de fechas | Cobertura de campos (lo que no está al 100%) | Relaciones |
|---|---|---|---|---|
| Fichas (`/pacientes`) | 685 (652 habilitadas) | alta 02/11/2022 → 19/10/2026 | celular 95%, DNI (`rut`) 90%, nacimiento 93%, email 86%, dirección 84%, número de ficha 70%, sexo 86%, observaciones 4%, teléfono 4% | ids 1–685 sin huecos |
| Citas (`/citas`) | 9.281 (178 futuras) | 01/11/2022 → 16/08/2027 | comentarios 14%; el resto, 100% | ficha 100%, plan 100%, profesional, sillón y estado 100%. 661 fichas distintas |
| Planes de tratamiento (`/tratamientos`) | 689 | 02/11/2022 → 19/10/2026 | nombre 99%, comentario 0%, convenio 0% | ficha 100% (663 fichas con plan) |
| Prestaciones de cada plan (`/tratamientos/{id}/detalles`, 1 pedido por plan) | 5.701 | creación 14/11/2022 → 19/10/2026 | realizada (fecha y profesional) 69%, pieza dental 0% | plan y prestación 100% |
| Pagos (`/pagos`) | 4.175 | 06/04/2022 → 19/10/2026 | banco 59%, medio de pago y referencia 60% | ficha 100%, caja 100% |
| Cajas (`/cajas`) | 305 | apertura 03/11/2022 → **10/08/2026** (no se abren cajas desde agosto) | cierre 99% | sucursal y usuario 100% |
| Devoluciones (`/cajas/{id}/devoluciones`, 305 pedidos) | 0 | — | — | — |
| Evoluciones clínicas (`/evoluciones`) | **5.313** (la paginación devolvió 5.330: 17 repetidas) | 14/11/2022 → 19/10/2026 | texto 99,9% | 485 fichas; plan 99,9% |
| Recetas (`/recetas`) | 3 | 08/2024 → 07/2026 | — | — |
| Profesionales (`/dentistas`) | 2 (1 habilitado) | — | — | usuario, sucursal y especialidad |
| Horario semanal (`/dentistas/{id}/horarios`) | 1 profesional (el otro, 404) | — | lunes y miércoles 15:00–19:20, martes y jueves 08:00–11:40, viernes 08:30–11:40, grilla de 10 min | — |
| Contratos y liquidaciones del profesional | 4 y 4 | — | — | profesional |
| Prestaciones de catálogo (`/prestaciones`) | 990 | — | código 2% | arancel y categoría |
| Catálogos | estados 21, especialidades 14, categorías 18, aranceles 2, bancos 29, sillones 2, sucursales 1, laboratorios 3 (+102 prestaciones de laboratorio, 57 compartidas entre laboratorios), convenios 0 | — | — | — |
| Usuarios (`/usuarios`) | 22 (7 habilitados) | — | celular 41%, email 64%, DNI 41% | 2 son profesionales |
| Archivos adjuntos (`/pacientes/{id}/archivos`, solo por ficha) | muestra: 3 archivos en 3 de 30 fichas (alrededor del 10%) | — | — | ficha |
| Campos adicionales (`/pacientes/{id}/adicionales`, solo por ficha) | muestra: 28 en 30 fichas | — | — | ficha |

### 1.2 Lo que no responde

| Ruta | Respuesta | Qué significa |
|---|---|---|
| `/bloqueos`, `/feriados`, `/dentistas/{id}/bloqueos`, `/sucursales/{id}/bloqueos`, `/agendas/bloqueos`, `/horarios/bloqueos` | 404 | **La API no expone bloqueos, feriados ni vacaciones.** Solo se ven como huecos que faltan en `/agendas` |
| `/tareas`, `/pacientes/{id}/tareas`, `/dentistas/{id}/adicionales` | **401 "No tiene autorización"** | **Bloqueo de permisos del token.** Para copiar tareas, la clínica tendría que habilitar ese permiso en Dentalink |
| `/pagos/{id}/boletas` | 403 "no tiene activa la nueva facturación electrónica" | No se usa (la facturación es chilena) |
| `/pacientes/{id}/apoderados`, `/cargas` | 404 en las 30 fichas de la muestra | No se usan (0 vínculos familiares cargados en Dentalink) |
| `/presupuestos`, `/archivos`, `/devoluciones`, `/abonos`, `/mediospago`, `/gastos`, `/documentos`, `/formularios`, `/odontogramas`, `/fichas`, `/campanas`, `/encuestas`, `/notificaciones`, `/descuentos`, `/motivos`, `/citas/motivos`, `/sucursales/{id}/sillones` | 404 | No existen en la API v1 (los presupuestos son los planes; los motivos van como texto en cada cita) |
| `/horarios` | 400 (pide parámetros) | Se usa la versión por profesional |
| Historial de estados de una cita | no hay ruta | El espejo lo registra desde que empieza a correr (`agenda.cita_eventos`) |

**Ritmo de la extracción completa:** 1.745 pedidos en 65 minutos, a unos 27 por minuto. Hubo 43 esperas para dejarle cupo al bot y 51 pausas por el Health Check. Sin `--descubrir`, son unos 1.450 pedidos (**~55 minutos**). Con `--con-archivos` se suman 1.370 pedidos (~50 minutos). La incremental de cada noche hace unos 200 pedidos (**~8 minutos**).

---

## 2. Problemas de calidad (agregados)

| Tema | Números | Qué hace el curado |
|---|---|---|
| Celulares | 645 válidos (94%): 89 ya venían como `549…` y 556 se normalizaron (la mayoría tenían `+54` sin el 9). 33 vacíos, 3 extranjeros, 2 sintéticos (de pruebas), 1 sin código de área y 1 inválido. 0 `@lid` | `celular_normalizado` + `celular_estado` (R1) |
| DNI | 601 bien (88%), 68 vacíos, 13 pasaporte u otro, 3 dudosos (6 o 9 dígitos) | `documento_normalizado` + `documento_estado` (R2) |
| Email | 586 bien, 96 vacíos, 2 falsos ("no tiene"), 1 inválido | R3 |
| Nacimiento | 49 vacíos, **54 con 01/01/1900 de relleno**, 1 inválido: edad desconocida en 104 (15%). **285 menores (42%)** | NULL con marca. `es_menor` (R4) |
| Dirección | 109 vacías | marca |
| Fichas duplicadas probables | **15** en 15 grupos: 13 por mismo nombre y mismo celular (el patrón del alta del v6, sin DNI) y 2 por mismo nombre y mismo nacimiento. 0 casos de mismo DNI con otro nombre | `duplicado_de` (marca; la secretaria decide, CRM-06) |
| Familias | 89 celulares con 2 a 4 fichas (195 fichas; máximo 4) | `celular_compartido_n`. No son duplicados |
| Fichas dadas de alta por el bot | 21 con la firma del v6 (sin DNI ni nada más que nombre, apellido y celular `549…`) y 5 del v7 (con DNI). Por mes: abr 1, may 10, jun 3, jul 2, ago 5, sep 2, oct 3 | `origen_probable` (R6) |
| Datos de prueba | 4 fichas (2 con teléfono sintético) y 52 citas con "prueba" o similar. **Ninguna es futura y activa** | `posible_prueba` |
| Fichas sin ninguna cita | 24 | — |
| Citas que se pisan | 139 no anuladas (6 futuras) | `solape_importado` (no es sobreturno) |
| Citas fuera de la grilla o del horario | 1.074 empiezan fuera de la grilla de 10 min y 793 caen fuera del horario semanal **actual** (es histórico: el horario cambió). Entre las futuras activas, 3 | marcas `fuera_de_grilla` y `fuera_de_horario` |
| Duraciones reales | 40 min (4.322), 30 (2.481), 45 (930), 20 (481), 60 (453), 10 (415), 15 (95) y 50 (90). **El bot siempre reserva 40** | — (insumo de AGE-05: tipos de turno) |
| Estados de las citas | Atendido 5.318, Anulado 2.025, Cambio de fecha 1.545, No asiste 221, Notificado por WhatsApp 102, No confirmado 36, Confirmado por WhatsApp 18 y otros 16. **Futuras (178):** Notificado 96, No confirmado 25, Cambio de fecha 25, Anulado 16, Confirmado por WhatsApp 16 | `estados_cita.categoria` |
| ¿Quién pone el 15? (AGE-02) | 100 de 102 se pusieron **8 días o más antes del turno**, repartidos entre las 08 y las 20 h, sin un pico a hora fija. El 18 (lo pone el bot) aparece 1 a 5 días antes | Ver §10, riesgos |
| Origen de las citas (por comentario) | 42 del v6 ("…por bot") y 2 del v7 ("…por Asiri"); el resto, del staff. Últimos 90 días: 19 del v6, 2 del v7 y 836 del staff | `origen_inferido` |
| Motivos | 28 distintos: En TTO LARGO 4.850, En TTO CORTO 963, Consulta Ortodoncia 677, Devolución con escaneo 671, Control Contención 616, Escaneo + FOTOS 275, Consulta 251, Inicio tto con Brackets 176, No registra motivo 166, Escaneo 157, Urgencia 144, Estudio con escaneo 125 | texto tal cual |
| Planes | **2 finalizados de 689** (la clínica no cierra planes), 31 con deuda, 5 sin nombre y 505 con el nombre por defecto "Nuevo plan de tratamiento" | marcas |
| Pagos | 5 con monto no positivo. Transferencia 2.442, efectivo 1.657, en dólares 41, tarjeta 34, depósito 1 | marca |
| Paginación | `/evoluciones` devolvió 17 filas repetidas (los ids 1–5.313 están completos). 57 prestaciones de laboratorio aparecen en más de un laboratorio | Se deduplica por clave antes de cargar. Si no, el upsert fallaba |
| Borrados físicos en Dentalink (huecos de ids) | citas 3, planes 13, pagos 23, prestaciones de planes 318 | El espejo marca `desaparecida_at` desde la primera carga |
| Claves huérfanas | **0** (citas, planes, pagos, evoluciones y prestaciones apuntan a filas que existen) | — |

**Prueba con los datos reales** (en un PGlite en memoria, nunca en producción; el SQL temporal se borró): la carga de `ocupacion` entra en 0,8 s y la de `pacientes` en 1,3 s, sin violar ningún check. La segunda corrida no cambia ninguna fila ni genera eventos. Las 9.281 citas quedan vinculadas a su ficha y a su plan. `fichas_por_celular` da 534 celulares con 624 fichas vigentes.

---

## 3. Esquema propio: `agenda` en el Supabase v3

Archivo: `sql/2026-10-20_dentalink_espejo.sql` (aditivo, idempotente, una transacción; **no aplicado**). Lo aplica `python scripts/apply_dentalink_espejo_esquema.py --apply`, que antes exige la prueba PGlite en verde y después verifica tablas, RLS y permisos. En simulación ya confirmó, con una sesión de solo lectura, que hoy el esquema `agenda` no existe en el v3.

**Ids.** Cada fila espejada tiene `id = dentalink_id` (único, con un check). Las filas propias que se creen después del corte toman id desde 10.000.000. Así, todo lo que hoy guarda un id de Dentalink (`recordatorios_enviados.id_cita_dentalink` e `id_paciente_dentalink`, la memoria del bot, los avisos al grupo y el panel) sigue apuntando a la misma fila después del corte, sin traducir nada.

| Grupo | Tablas | Fase |
|---|---|---|
| Control | `esquema_version`, `config` (`backend = 'dentalink'` hasta el corte), `sync_corridas` (cada carga, con conteos agregados) | — |
| Recursos y catálogos | `sucursales`, `profesionales`, `sillones`, `especialidades`, `estados_cita` (con `categoria`), `horarios`, `aranceles`, `categorias_prestacion`, `prestaciones`, `bancos`, `laboratorios`, `convenios`, `usuarios` | ocupacion (el contacto del staff, pacientes) |
| Agenda | `citas`: la ocupación en `ocupacion`; `ficha_id` en `ficha_minima`; `tratamiento_id` en `pacientes`; `comentarios` en `clinica`. Además, `cita_eventos` (historial observado: estado, fecha y hora, desaparecida, reaparecida) y `bloqueos` (propia y vacía: la API no los expone) | ocupacion |
| Fichas | `fichas`: en `ficha_minima`, celular normalizado, si es menor, habilitada, duplicados y origen; en `pacientes`, nombre, documento, nacimiento, email y dirección; en `clinica`, observaciones. Vista `fichas_por_celular` | ficha_minima / pacientes / clinica |
| Administración | `tratamientos`, `tratamiento_detalles`, `pagos`, `cajas` | pacientes |
| Historia clínica | `evoluciones`, `recetas` (y la pieza dental de los detalles) | clinica |
| Resto | `dentalink_otros` (jsonb): contratos y liquidaciones, prestaciones de laboratorio, devoluciones, campos adicionales y metadatos de archivos | según la entidad |

**Columnas comunes del espejo:** `espejo_creado_at`, `espejo_actualizado_at` (solo cambia si cambió el dato), `espejo_corrida_id`, `desaparecida_at` (lo que Dentalink dejó de devolver: se marca, nunca se borra) y `calidad text[]` (marcas del curado).

**Claves foráneas:** todas `deferrable initially deferred`, para cargar todo en una transacción. Si el destino no existe en Dentalink, queda NULL, con la marca `<x>_inexistente` y el id original en `<x>_dentalink_id`.

**Índices:** fichas por celular, documento, nombre y duplicado; citas por fecha y hora, por profesional y fecha, por ficha, por estado y por `dentalink_actualizado_at` (la base del incremental). La prueba confirma que las dos lecturas que va a hacer el bot usan índice.

**Permisos (Anexo B del plan del 13/10):** RLS en las 27 tablas y sin policies. `anon` y `authenticated` no tienen nada, ni siquiera USAGE del esquema (probado con los defaults globales abiertos). `service_role` tiene SELECT, INSERT y UPDATE, **nunca DELETE ni TRUNCATE**. Las funciones están cerradas. El esquema **no se agrega** a "Exposed schemas" de PostgREST. La carga entra por conexión directa como `postgres`, igual que las migraciones de hoy.

**Solapes:** `agenda.recalcular_solapes()` corre al final de cada carga, también en las incrementales. Así, el EXCLUDE de la agenda propia (AGE-05) puede ser parcial (`where not anulada and not solape_importado`) sin rechazar la historia. El EXCLUDE con `btree_gist` sobre profesional y `tstzrange` ya existe probado en `nexora-agenda/lib/db/migrations/0001_exclusion_constraints.sql`: se reutiliza. nexora-agenda también aporta las entidades (appointments, professional_schedules, chairs, locations). Sus tests son e2e (Playwright), no de base.

---

## 4. Reglas de curado (detalle en el docstring del script)

Nada se borra ni se fusiona solo. El dato original queda en su columna y el curado va en columnas propias.

| Regla | Qué hace |
|---|---|
| R1 celular | Lo lleva a `549XXXXXXXXXX`: quita `+54`, el 9, el 0 troncal y el 15 después del código de área (11 = 2 dígitos; si no, 3 o 4). Estados: `ok`, `normalizado`, `vacio`, `lid` (identificador oculto de WhatsApp), `sin_codigo_area` (**no se adivina el 388**), `extranjero`, `falso`, `sintetico` (teléfonos de prueba del proyecto) e `invalido` |
| R2 documento | Quita puntos, espacios y guiones. DNI de 7 u 8 dígitos = `ok`; 6 o 9 = `dudoso`; pasaporte u otro tipo; `falso` (todos iguales, 12345678); `vacio` |
| R3 email | Minúsculas y sin espacios. Estados `invalido` y `falso` ("no tiene", "sin mail") |
| R4 nacimiento | Vacío, 01/01/190x (relleno) o imposible → NULL con marca. `es_menor` se calcula a la fecha de la corrida |
| R5 duplicados | Mismo documento válido; mismo nombre + nacimiento; mismo nombre + celular. Canónica: con documento > habilitada > id más bajo (estable entre corridas). Mismo DNI con nombres distintos **no se une**: se marca. Mismo celular con otro nombre es **familia** |
| R6 origen | `bot_v6` (solo nombre, apellido y celular `549…`, que es lo que manda el alta del v6), `bot_v7` (lo mismo, con DNI) o `staff`. Además, `posible_prueba` |
| R7 citas | Marca estado, ficha, plan, profesional o sillón inexistente; cita sin paciente; duración que no cierra; inicio fuera de la grilla; fuera del horario semanal; solape; cita de prueba. `origen_inferido` sale del comentario |
| R8 resto | Claves foráneas inexistentes → NULL con marca. Pago sin monto positivo. Plan con deuda negativa. Filas repetidas por la paginación: una sola |
| R9 desaparecidos | En una corrida completa, lo que Dentalink ya no devuelve queda con `desaparecida_at`. Si Dentalink devuelve menos del 90% de lo que el espejo tiene activo, **la carga aborta entera** |

---

## 5. Qué se copia antes y qué después del "dale"

**El "dale" de la Dra. = firmar el contrato de tratamiento de datos con Nexora (SEG-17, D12).** El script tiene una bandera por fase. Las que copian datos de pacientes **se niegan a correr con `--apply` sin `--contrato-firmado`**.

| Cuándo | `--fase` | Qué copia | Exige |
|---|---|---|---|
| **Antes del "dale" (ya)** | `ocupacion` | Agenda completa **sin ningún dato de pacientes**: 9.281 citas con fecha, hora, duración, estado, profesional, sillón y motivo; horarios; estados; catálogos; profesionales y usuarios sin datos de contacto. Es C12 (a) | Solo el SQL aplicado |
| Si el abogado restringe | `ficha_minima` | C12 (b) literal: id de la ficha, celular normalizado, si es menor, duplicados, y el vínculo cita → ficha. Sin nombre, DNI, dirección ni comentarios | `--contrato-firmado` |
| **Después del "dale"** | `pacientes` | Todo lo necesario para dejar Dentalink: fichas completas (nombre, DNI, nacimiento, email, dirección), planes y sus prestaciones, pagos, cajas, contacto del staff, contratos y liquidaciones | `--contrato-firmado`, y que Lucas deje anotado en `decisions.md` que **amplía C12** ("nunca DNI, dirección ni comentarios") |
| Si la Dra. decide migrar la historia clínica | `clinica` | + 5.313 evoluciones, 3 recetas, observaciones de las fichas, comentarios de citas y planes (y, con `--con-archivos`, los metadatos de los archivos adjuntos) | `--contrato-firmado --incluir-clinico`. Sin `--incluir-clinico`, ese texto ni se guarda en la caché |

**Nota sobre esta pasada:** para medir cobertura y duplicados, la extracción del 20/10 leyó las fichas completas. Fuera de la PC solo salieron agregados. La caché cruda quedó en la carpeta temporal de la sesión, fuera del repo, y con el texto clínico ya reemplazado por su largo. **D11 pedía la fase 0 "sin datos personales": esa caché hay que borrarla cuando se termine de revisar esto.**

---

## 6. Qué queda fuera y por qué

| Qué | Por qué | Qué se hace |
|---|---|---|
| Bloqueos, feriados y vacaciones | La API no los expone (404 en las 6 rutas) | Tabla propia `agenda.bloqueos`, que carga Irina o se infiere (día con horario, sin huecos en `/agendas` y sin citas). El comparador de sombra (AGE-05) mide las diferencias |
| Historial de estados | No hay ruta | `cita_eventos` lo registra desde la primera corrida (estado, fecha y hora, desaparecida) |
| Tareas | 401: el token no tiene permiso | Pedir el permiso en Dentalink, o dejarlas fuera (no hay evidencia de uso) |
| Binarios de los archivos adjuntos | La API da metadatos por ficha. Bajar los binarios a un bucket privado de Supabase Storage es un paso aparte | `--con-archivos` copia los metadatos (fase `clinica`). La descarga se diseña con el contrato firmado. Hay alrededor de 70 fichas con archivos |
| Facturación electrónica, apoderados, cargas, convenios, devoluciones, notificaciones GES | 403, 404 o 0 filas | Nada |
| Odontograma, formularios, presupuestos | No hay ruta (los presupuestos son los planes) | Nada. Si la Dra. usa el odontograma, export de Dentalink antes de la baja |
| Disponibilidad (`/agendas`) | Es un cálculo, no un dato | La reemplaza el motor de disponibilidad propio (AGE-05) |
| Usuarios y contraseñas de Dentalink | No se exponen ni corresponden | Login propio y roles (SEG-12) |

---

## 7. Plan de corte, paso a paso

**Cuándo:** no antes del **lun 01/03/2027** y solo con los 14 criterios del §4.4 del plan del 13/10 en verde: espejo conciliado 14 días seguidos, disponibilidad propia igual a la de Dentalink en 200 búsquedas o más, recordatorios v2 iguales al v1 durante 10 días hábiles, contrato firmado, acuerdo de mantenimiento, Irina con 3 días en paralelo, etc. Si Lucas quiere adelantarlo, es una decisión aparte que cambia el backlog.

### 7.0 Antes del corte

1. Backup de la base (Supabase Pro, D1). Después: `python scripts/apply_dentalink_espejo_esquema.py --apply`.
2. **Ya, sin esperar el contrato:** `python scripts/migrar_dentalink.py --apply` (fase `ocupacion`). Al terminar verifica solo: conteos, ids y citas por estado.
3. **Con el "dale" (contrato firmado):** `python scripts/migrar_dentalink.py --apply --fase pacientes --contrato-firmado`. La historia clínica, solo si se decide: `--fase clinica --contrato-firmado --incluir-clinico` (y `--con-archivos`).
4. **Sincronización** (de noche, fuera de las ventanas prohibidas; hasta que exista el limitador común de AGE-02, que se despliega el 30/11):
   - incremental cada noche: `--apply --incremental --fase …` (~8 min). Trae las citas por `fecha_actualizacion`, las evoluciones por `fecha_registro` y las prestaciones solo de los planes cuyos totales cambiaron; el resto, completo;
   - completa los sábados de noche (~55 min): es la que detecta desaparecidos y verifica;
   - si la verificación sale con 1, se avisa al grupo (señal "espejo atrasado" en el Health Check, AGE-03).
5. Construir las funciones `agenda.api_*` del §8.1 y medirlas en sombra contra Dentalink (AGE-05). Construir Recordatorios v2 (clon) y medirlo 10 días hábiles.
6. Preparar, con backup y diff, cada cambio del §8 en una versión "agenda", sin aplicarla. Ensayo de vuelta atrás un sábado (criterio 12).

### 7.1 El día del corte (un sábado; la clínica cierra; unas 3 horas)

| Hora | Paso | Quién | Si falla |
|---|---|---|---|
| 08:00 | **Congelamiento:** aviso al grupo. Desde ahora nadie carga ni mueve turnos en Dentalink. El bot sigue atendiendo, y en agendar, confirmar y cancelar responde en modo degradado (BOT-10) | Claude avisa y la Dra. confirma | Se posterga |
| 08:05 | **Última sincronización completa** con la fase decidida (`--apply --fase pacientes --contrato-firmado`, o `clinica`). Unos 55 minutos. Al terminar verifica sola: 0 diferencias en conteos, ids y citas por estado | Claude | Se reintenta. Ante un 429 frena y corta: se espera y se vuelve a correr |
| 09:05 | **Control humano:** Irina o la Dra. comparan 1 día de la semana que viene en la pantalla de Dentalink contra el panel | Irina o la Dra. | No se sigue |
| 09:15 | **Cambio de lectura y escritura:** los cambios del §8 (v7, sub-WF de horarios, Recordatorios v2 encendido y v1 apagado, Health Check), deploy del panel con `AGENDA_BACKEND=agenda` y `agenda.config.backend = 'agenda'` | Claude | Vuelta atrás (§9) |
| 09:45 | **Prueba de punta a punta** desde el teléfono de Lucas: pedir turno, confirmar, reprogramar y cancelar contra la agenda propia, y verlo en el panel. **Limpieza en el mismo turno** (regla 9: anular la cita de prueba, borrar memoria y recordatorio sembrado) | Claude | Vuelta atrás |
| 10:30 | **Descongelamiento:** aviso al grupo. Irina carga desde el panel. Dentalink queda abierto solo para consulta | Claude avisa | — |
| Lun 08:00 | Primer día hábil: revisar los recordatorios del lunes y las primeras reservas. El espejo sigue mirando Dentalink 1 semana y avisa si aparece algo cargado allá | Claude | Vuelta atrás |

**Cuánto lleva el trabajo previo** (no está en esta entrega): funciones `agenda.api_*` y motor de disponibilidad (AGE-05, 10 días), cambios del §8 en versión "agenda" (unos 3 días), Recordatorios v2 (2 días) y el cliente del panel (1,5 días). Con el factor 3x del backlog maestro, eso entra entre diciembre y febrero.

---

## 8. Qué hay que cambiar para leer y escribir el esquema propio (lista exacta)

**Principio:** el v7 ya recibe la E/S inyectada (los `*_core.js` procesan la respuesta cruda de Dentalink). Si cada nodo HTTP de Dentalink se reemplaza por un nodo Postgres que llama a una función `agenda.api_*` que **devuelve la misma forma** (`{data: [...]}`, con los mismos campos: `id`, `id_estado`, `fecha`, `hora_inicio`, `rut`…), la lógica de los cores no cambia. Cambian los nodos y los tests de grafo.

### 8.1 Funciones nuevas en `agenda` (AGE-05; no están en este SQL)

| Función | Reemplaza | La usan |
|---|---|---|
| `api_fichas_por_celular(lk)` | `GET /pacientes?q={"celular":{"lk":…}}` | v7 ver_turnos, sub-WF CancelarReprogramar, panel |
| `api_ficha(id)` / `api_fichas_por_documento(dni)` | `GET /pacientes/{id}` / `?q={"rut":…}` | Recordatorios v2, v7 ejecutar_propuesta |
| `api_citas_de_ficha(id, desde)` | `GET /pacientes/{id}/citas` | v7 ver_turnos, sub-WF CancelarReprogramar, panel |
| `api_cita(id)` | `GET /citas/{id}` | v7 confirmar_turno y ejecutar_propuesta |
| `api_citas_del_dia(fecha)` | `GET /sucursales/1/citas` | Recordatorios v2 |
| `api_disponibilidad(fecha, profesional, duracion)` | `GET /agendas` (hasta 6 páginas) | sub-WF Buscar Horarios, panel |
| `api_cita_estado(id, estado, actor)` | `PUT /citas/{id} {id_estado}` | v7 confirmar_turno, sub-WF, panel |
| `api_cita_crear(body, actor)` | `POST /citas` (con EXCLUDE: dos reservas no se pisan) | v7 ejecutar_propuesta, sub-WF, panel |
| `api_ficha_crear(body, actor)` | `POST /pacientes` (con el curado R1/R2 en la entrada) | v7 ejecutar_propuesta, panel |
| `api_profesionales()` | `GET /dentistas` | panel |

Cada escritura deja un evento en `cita_eventos` con el actor (`set_config('app.actor')`, SEG-12 / C13).

### 8.2 n8n: v7 (`v7/workflows/*.json`, generados por los scripts)

| Workflow (id) | Nodos que hoy llaman a Dentalink | Cambio |
|---|---|---|
| v7 Tool - ver_turnos (`ZHGzacebRHAFQ7wn`) | `GET fichas del celular`, `GET citas por ficha` | Postgres → `api_fichas_por_celular`, `api_citas_de_ficha` |
| v7 Tool - confirmar_turno (`cdiBTgcABItdgQ9y`) | `GET cita`, `PUT confirmar` | → `api_cita`, `api_cita_estado(id, 18)` |
| v7 Tool - ejecutar_propuesta (`9E5Lse6TDJ74wpsM`) | `GET cita vieja`, `GET paciente por DNI`, `POST paciente`, `POST paciente (sin DNI)`, `POST reserva`, `PUT anular` | → `api_cita`, `api_fichas_por_documento`, `api_ficha_crear` (x2), `api_cita_crear`, `api_cita_estado` |
| v7 Tool - buscar_horarios (`4dFlp6TEfV8A5e6y`) | Llama al sub-WF `GuDQ9VmKWZvQnerV` (compartido con el v6) | Apuntar a un sub-WF nuevo que llame a `api_disponibilidad` (el viejo queda para la vuelta atrás) |
| Generadores | `scripts/v7_lib.py` (`DENTALINK`, `CRED_DENTALINK`, `Grafo.dentalink()`), `scripts/v7_workflows_herramientas.py`, `scripts/v7_workflows_confirmar_clinica.py`, `scripts/build_v7_workflows.py`; deploy con `scripts/crear_v7_en_n8n.py --aplicar` | Agregar `Grafo.agenda()` (nodo Postgres) y elegir con un flag de build, para poder volver |
| Cores JS (sin cambio de lógica si la forma es igual) | `v7/agenda_core.js` (`pasoBuscarDni`, `pasoAlta`, `armarPaciente`, cuerpo de la reserva, comentario "…por Asiri"), `v7/confirmar_core.js` (`ESTADO_CONFIRMADO = 18` y el 400 de Dentalink "estado igual al original"), `v7/ficha_core.js` (vigente = no 1 ni 14; `rut`), `v7/horarios_core.js` (la fecha de `/agendas` en DD/MM/YYYY), `v7/health_core.js` (`dentalinkOk` → `agendaOk`) | Revisar y probar. Tests: `tests/test_agenda_core.mjs`, `test_ficha_horarios_core.mjs`, `test_health_core.mjs`, `test_v7_grafo.py`, `test_v7_grafo_herramientas.py` (estos dos buscan la URL de Dentalink) |

### 8.3 n8n: el resto

| Workflow (id) | Nodos | Cambio |
|---|---|---|
| Sub-WF Buscar Horarios Validado (`GuDQ9VmKWZvQnerV`) | `GET Horarios Dentalink`, `GET Horarios P2` … `P6` (6 páginas de `/agendas`) | Copia nueva con 1 nodo Postgres (`api_disponibilidad`). El original no se toca (lo usa el v6) |
| Sub-WF CancelarReprogramar (`5cAWJxiWJ50hxEq3`) | `Step 1a: Buscar full`, `Step 2a: Ver Turnos`, `Step 6a: Cancelar en Dentalink`, `Step 6d-1: POST Reservar`, `Step 6d-3a: PUT Cancelar Viejo` | Solo si el v6 sigue atendiendo a alguien (no debería: criterio 7). Si no, se desconecta |
| v6 (`O155MqHgOSaNZ9ye`) | Herramientas `ver_profesionales`, `reservar_turno`, `cancelar_turno`, `buscar_paciente_dentalink`, `crear_paciente_dentalink`, `confirmar_turno`, `ver_turnos_paciente`; freno `Redis GET dentalink:status` + `Dentalink up?` | Desconectar las herramientas y sacar el freno (criterios 7 y 8, BOT-17). `webhookId: evo-webhook-v2` intacto |
| Recordatorios (`7RqTApkvVavRmq3R`) — **NO TOCAR** | `GET Citas por fecha` (`/sucursales/1/citas`), `GET Paciente (celular)` (`/pacientes/{id}`) | **Clon** "Recordatorios v2" con esos 2 nodos en Postgres (`api_citas_del_dia`, `api_ficha`), en sombra 10 días hábiles. El día del corte, v2 se prende y v1 se apaga, antes de las 9 |
| Health Check (`Yjl6kyLnALhIfbFX`) | `Check Dentalink` (`/sucursales/1`) | Sumar el chequeo de la agenda propia y la frescura del espejo. El de Dentalink queda mientras exista |
| Redis | clave `dentalink:status` | Se deja de leer cuando se saca el freno |

### 8.4 Panel (`nexora-whatsapp-agent`)

| Archivo | Uso de Dentalink | Cambio |
|---|---|---|
| `lib/integrations/dentalink/client.ts` (+ `types.ts`, `ingest.ts`) | Cliente: GET, PUT de estado, POST de cita, POST de paciente | `lib/integrations/agenda/client.ts`, con la misma interfaz y las RPC por service_role. Se elige con `AGENDA_BACKEND` |
| `app/(app)/citas/page.tsx` | `listAllCitas()` (tope de 400) | Lee `agenda.citas` por rango (AGE-01 se resuelve solo) |
| `app/(app)/conversaciones/[id]/turnos-actions.ts` | `updateCitaEstado` (x3), `pacientesByCelular`, `listDentistas`, `crearTurno` (x2), `buscarHorarios` | Los mismos métodos sobre el cliente nuevo |
| `lib/chat-data.ts` | `pacientesByCelular`, `citasByPaciente` | Ídem |
| `components/conversaciones/nuevo-turno.tsx` | Usa las acciones | Sin cambio |
| Variables | `DENTALINK_TOKEN`, `DENTALINK_BASE_URL` | Se retiran después de las 6 semanas de respaldo |

### 8.5 Scripts y datos de este repo

- `scripts/crear_cita_prueba_examen.py` y `tests/seed_examen_v7.py` crean y anulan citas de prueba en Dentalink a través de n8n: pasan a la agenda propia (regla 9).
- `recordatorios_enviados.id_cita_dentalink` e `id_paciente_dentalink` **no cambian**, porque los ids espejados son los mismos.
- `scripts/migrar_dentalink.py`: después del corte deja de correr. Una corrida final queda como export (§9).

---

## 9. Vuelta atrás

**Antes del corte** no hay nada que volver: Dentalink es la verdad y el espejo solo copia. Para borrar el espejo, si se decidiera no seguir, alcanza con `drop schema agenda cascade`, que no toca nada del bot.

**Después del corte** (objetivo: menos de 15 minutos, ensayado un sábado antes):

1. Congelar de nuevo y avisar al grupo.
2. Lo que se cargó en la agenda propia después del corte (citas con id desde 10.000.000, o con `espejo_actualizado_at` posterior al corte) se vuelca a una lista para cargar en Dentalink. Si en la fase 3 del plan del 13/10 corre la escritura inversa, ya está allá.
3. `agenda.config.backend = 'dentalink'`, deploy del panel con `AGENDA_BACKEND=dentalink`, y se restauran las versiones "dentalink" del §8 desde sus backups (`scripts/restaurar_workflow.py <backup> --apply`).
4. Recordatorios: v2 apagado y v1 prendido, antes de las 9.
5. El espejo vuelve a copiar de Dentalink.

**Qué la dispara:** una doble reserva, un recordatorio que no salió, que Irina no pueda operar, o que la Dra. lo pida.

**Export final antes de dar de baja Dentalink** (después de 6 semanas sin volver atrás): una corrida completa con `--fase clinica --contrato-firmado --incluir-clinico --con-archivos` a una caché cifrada, más el export propio de Dentalink (PDF por paciente de la historia clínica), guardados en 2 lugares, uno de ellos de la clínica (Ley 26.529).

---

## 10. Riesgos

| Riesgo | Efecto | Mitigación |
|---|---|---|
| **Datos de salud sin contrato** (Ley 25.326, art. 25; transferencias a Brasil, Chile y EE.UU.) | Riesgo legal para la clínica y para Nexora | Fases. `ocupacion` no tiene datos de pacientes. El resto se niega sin `--contrato-firmado`, y `clinica` además sin `--incluir-clinico` |
| **C12 dice "nunca DNI, dirección ni comentarios"** | El corte completo los necesita (altas, búsqueda por DNI) | `--fase pacientes` existe, pero hace falta que Lucas deje anotado en `decisions.md` que amplía C12, y el visto bueno del abogado |
| **La historia clínica sí se usa** (5.313 evoluciones en 485 fichas, hasta el 19/10; el plan del 13/10 decía "sin evidencia") | Si queda en Dentalink, no se puede dar de baja Dentalink; si se migra mal, pierde valor legal (Ley 26.529) | Decisión de la Dra.: migrar con `--fase clinica`, o mantener Dentalink en el plan más barato solo para la historia clínica, o export congelado con hash |
| **Bloqueos y feriados no se pueden copiar** | La agenda propia ofrecería días cerrados (el incidente del 09/05 fue un sábado con la clínica cerrada) | `agenda.bloqueos` a mano o inferidos, y el comparador de sombra mide las diferencias antes del corte |
| **El estado 15** se pone al reservar (8 días o más antes, en horario de atención) | Si es el aviso de reserva por WhatsApp de Dentalink, al apagarlo los pacientes dejan de recibirlo | Confirmar con la Dra. qué es. Si hace falta, Asiri manda el aviso de reserva |
| **Tope de 60 pedidos por minuto compartido** con el v7, que desde el 20/10 atiende a todos | El bot se queda sin agenda | El script va a 1 pedido cada 1,6 s (≥1,5 s, C11), deja 25 de reserva y **frena ante un 429**: pausa de 120 s y, al segundo, corta sin cargar nada. No pide nada cerca del Health Check (:00 y :30) ni entre las 08:50 y las 09:20. Las corridas son de noche. Cuando esté el limitador de AGE-02, toma el cupo de ahí |
| **El staff sigue cargando en Dentalink** después del congelamiento | Una cita se pierde | Congelamiento confirmado por la Dra. El espejo sigue mirando Dentalink 1 semana y avisa |
| **Duplicados y fichas del bot** | Turnos en la ficha equivocada | Se marcan (R5, R6) y la secretaria los revisa (CRM-06). Nada se fusiona solo |
| **La caché cruda** tiene datos de pacientes y queda en la PC | Fuga si la PC se comparte | Fuera del repo (el script se niega a guardarla adentro), con el texto clínico reemplazado por su largo salvo `--incluir-clinico`. Se borra después de cada corrida aplicada. La del export final, cifrada |
| **Horas sin zona horaria** (`fecha_actualizacion` llega en hora local de la cuenta) | Errores de ±3 h en el incremental | Se guarda como `timestamp` sin zona y el incremental arranca 1 día antes de la última corrida OK |
| **La paginación de Dentalink repite filas** (y podría saltear alguna) | Faltantes silenciosos | Deduplicación por clave; `ids_repetidos` en el reporte; la completa semanal y la verificación comparan ids |

---

## 11. Para la doctora

**Qué es esto.** Hoy su agenda vive en Dentalink. Estamos preparando una **copia exacta** de todo lo que hay ahí (turnos, pacientes, tratamientos y pagos) en el sistema propio, el mismo donde ya están los chats y los recordatorios. Mientras tanto, **usted sigue usando Dentalink como siempre**: la copia solo mira, no cambia nada.

**El "dale" que le vamos a pedir es firmar el contrato de datos** con Nexora (lo prepara el abogado). Antes de esa firma copiamos solo los horarios de la agenda, sin nombres ni datos de nadie. Después de la firma copiamos todo lo demás. El día del cambio se elige después, cuando todo esté probado.

**Qué cambia para usted el día del cambio:**
- Un sábado a la mañana, por unas 3 horas, no se cargan turnos. Asiri sigue contestando y deriva al grupo lo que sea de agenda.
- Desde ese día, Irina y usted ven y cargan los turnos en el panel (en el celular o en la computadora), no en Dentalink.
- Los recordatorios y Asiri siguen igual. Por dentro leen la agenda propia.
- Dentalink queda abierto unas semanas para consultar, por si hace falta volver atrás. Volver atrás lleva menos de 15 minutos.

**Lo que le vamos a pedir que diga que sí (o que no):**
1. **Que firme el contrato de datos.** Ese es el "dale".
2. **Qué hacemos con la historia clínica.** Usted escribió más de 5.000 evoluciones en Dentalink. Podemos copiarlas o dejarlas en Dentalink con un plan más barato. Las dos opciones son válidas.
3. **Que Irina revise 15 fichas que parecen repetidas y unas 100 sin fecha de nacimiento real.** Le pasamos la lista y las corrige en Dentalink, sin borrar nada.
4. **Que nos cuente los días cerrados, feriados y vacaciones**, porque Dentalink no nos deja copiarlos.
5. **Qué es el estado "Notificado por WhatsApp"** que tienen la mitad de los turnos próximos: si es un aviso que manda Dentalink al reservar, hay que saberlo antes de apagarlo.
6. **La fecha del sábado del cambio.** No antes de marzo de 2027, y solo con todo probado.

---

## 12. Comandos

```
# 0) Pruebas offline (sin red ni base)
node tests/test_migracion_dentalink_espejo.mjs        # 63 OK (esquema x2, permisos, carga, idempotencia, eventos, guardas, fases)
python tests/test_migrar_dentalink_curado.py          # 88 OK (R1-R9, fases en el SQL, guardas del CLI, incremental, archivos)

# 1) Esquema (con backup previo)
python scripts/apply_dentalink_espejo_esquema.py           # simulación (prueba local + mira el v3 en solo lectura)
python scripts/apply_dentalink_espejo_esquema.py --apply

# 2) Antes del "dale": ocupación sin datos de pacientes (verifica sola al final)
python scripts/migrar_dentalink.py --apply

# 3) Después del "dale" (contrato firmado + C12 ampliado en decisions.md)
python scripts/migrar_dentalink.py --apply --fase pacientes --contrato-firmado
python scripts/migrar_dentalink.py --apply --fase clinica --contrato-firmado --incluir-clinico --con-archivos   # solo si la Dra. lo decide

# 4) Todas las noches / los sábados
python scripts/migrar_dentalink.py --apply --incremental --fase <la cargada> [--contrato-firmado]
python scripts/migrar_dentalink.py --apply --fase <la cargada> [--contrato-firmado]        # completa + verificación
python scripts/migrar_dentalink.py --verificar --sin-detalles                               # control aparte, solo lectura
```
