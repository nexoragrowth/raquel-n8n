# -*- coding: utf-8 -*-
"""
migrar_dentalink.py — 2026-10-20 · copia COMPLETA y CURADA de Dentalink al esquema propio `agenda` del Supabase v3
(sql/2026-10-20_dentalink_espejo.sql). Prepara el corte de Dentalink; NO lo hace. Plan: docs/plan-migracion-dentalink-2026-10-20.md.

QUÉ HACE
  1. EXTRAE todo lo que la API de Dentalink expone y la clínica usa (catálogos, horarios, fichas, citas con todos sus estados,
     planes de tratamiento y sus prestaciones, pagos, cajas, devoluciones, evoluciones, recetas, contratos/liquidaciones, labs).
     SOLO GET: el cliente rechaza cualquier otro método y cualquier URL fuera de la API (nunca escribe en Dentalink).
  2. CURA (reglas R1–R9 de abajo): normaliza celulares/documentos/emails, MARCA (nunca borra) duplicados, huérfanos, fichas del
     bot, citas de prueba, solapes y turnos fuera de horario. Lo curado va en columnas propias; el dato original se conserva.
  3. CARGA idempotente (upsert por dentalink_id, misma clave = mismo id) en una sola transacción, solo con --apply.

MODOS
  python scripts/migrar_dentalink.py                         SIMULACIÓN (default): lee Dentalink y reporta EN AGREGADOS qué cargaría
                                                             y qué curaría. No escribe en ninguna base.
  python scripts/migrar_dentalink.py --usar-cache            ídem sobre la última extracción guardada con --guardar-cache (0 pedidos a Dentalink)
  (20/10) Por defecto NO se guarda nada en disco, y sin --contrato-firmado no se piden pagos, cajas, evoluciones, recetas ni
  detalles, y de fichas y planes solo queda el id (SIN_CONTRATO_NO_PEDIR / SIN_CONTRATO_SOLO_ID).
  python scripts/migrar_dentalink.py --descubrir             además prueba ~55 rutas candidatas y muestrea las rutas por paciente
  python scripts/migrar_dentalink.py --con-archivos          además metadatos de archivos adjuntos y campos adicionales (por ficha)
  python scripts/migrar_dentalink.py --apply                 CARGA REAL de la fase ocupacion (ver FASES) en agenda.* — exige el SQL.
                                                             Al terminar una carga completa verifica sola (sale con 1 si difiere)
  python scripts/migrar_dentalink.py --apply --fase pacientes --contrato-firmado   datos personales completos (después del "dale" =
                                                             contrato firmado, SEG-17/D12)
  python scripts/migrar_dentalink.py --apply --fase clinica --contrato-firmado --incluir-clinico   + historia clínica
  python scripts/migrar_dentalink.py --apply --incremental   sincronización incremental: citas por fecha_actualizacion y evoluciones
                                                             por fecha_registro desde la última corrida OK (-1 día); el resto completo
  python scripts/migrar_dentalink.py --verificar [--sin-detalles]   compara conteos, ids y citas por estado Dentalink vs espejo
                                                             (solo lectura en los dos lados; sale con 1 si hay diferencias)
  python scripts/migrar_dentalink.py --fixture f.json --dump-sql out.sql   offline: SQL de carga desde datos SINTÉTICOS (test PGlite)

FASES (--fase; acumulativas; default ocupacion). Respetan D12/C12/SEG-17: nada con datos de pacientes antes del contrato firmado.
  ocupacion     (letra a) ANTES del "dale". Ocupación de la agenda SIN ningún dato de pacientes: sucursales, profesionales (sin
                datos de contacto), sillones, estados, horarios, especialidades, aranceles, categorías, prestaciones, bancos,
                laboratorios, usuarios (sin contacto), citas con fecha/hora/duración/estado/profesional/sillón/motivo (sin paciente,
                plan ni comentarios). = C12 (a). No espera el contrato.
  ficha_minima  (a+b) C12 (b) literal: id de la ficha, celular normalizado, si es menor, habilitada, duplicados y el vínculo
                cita→ficha. Sin nombre, DNI, dirección ni comentarios. Exige --contrato-firmado.
  pacientes     (a+b+c) DESPUÉS del "dale" (contrato firmado): todo lo personal y administrativo para dejar Dentalink: nombre,
                documento, nacimiento, email, dirección, planes de tratamiento y sus prestaciones, pagos, cajas, devoluciones,
                contacto del staff, contratos y liquidaciones. Exige --contrato-firmado (y que Lucas deje anotado que amplía C12).
  clinica       (a+b+c+d) + historia clínica (Ley 26.529): evoluciones, recetas, observaciones de la ficha, comentarios de citas
                y de planes, piezas dentales. Exige --contrato-firmado y --incluir-clinico (decisión de la Dra.). Sin
                --incluir-clinico esos textos ni se guardan en la caché: se reemplazan por su largo al extraer.

REGLAS DE CURADO (marcar, nunca borrar; el original siempre queda)
  R1 Celular AR → 549XXXXXXXXXX (13 dígitos) en fichas.celular_normalizado, con celular_estado:
     - solo dígitos; '00' inicial = prefijo internacional; '+54'/'54' y el '9' de celular se quitan; '0' troncal se quita;
     - '15' después del código de área (11 → 2 dígitos; si no, 3 o 4) se quita cuando deja 10 dígitos;
     - 10 dígitos nacionales que empiezan con 1/2/3 → '549' + N ('ok' si ya venía así, 'normalizado' si se corrigió);
     - 6 a 8 dígitos = número local sin código de área → 'sin_codigo_area' (NO se adivina el 388);
     - '@lid' o ≥14 dígitos que no empiezan con 54 → 'lid' (identificador oculto de WhatsApp, no es un celular);
     - '+' con otro país → 'extranjero' (se guarda E.164 sin '+'); todos iguales/secuencias/<6 dígitos → 'falso'; resto 'invalido';
     - 5490000000xxx / 549999xxxxxxx = teléfonos sintéticos de las pruebas del proyecto → 'sintetico' (y la ficha 'posible_prueba').
  R2 Documento (campo `rut` de Dentalink): sin puntos/espacios/guiones; DNI de 7-8 dígitos → 'ok'; 6 o 9 → 'dudoso';
     pasaporte/otro tipo → 'pasaporte_u_otro'; todos iguales o 12345678 → 'falso'; vacío → 'vacio'.
  R3 Email: minúsculas y sin espacios; formato inválido → 'invalido'; 'no tiene', 'sin mail', etc. → 'falso'.
  R4 Nacimiento: vacío/0000-00-00 → NULL ('nacimiento_vacio'); 01/01 de 1900-1909 = valor de relleno → NULL ('nacimiento_relleno');
     antes de 1900, futuro o >110 años → NULL ('nacimiento_invalido'). es_menor = <18 años a la fecha de la corrida.
  R5 Duplicados (fichas.duplicado_de = ficha canónica, duplicado_regla): mismo documento válido ('mismo_documento'); mismo
     nombre normalizado + mismo nacimiento ('mismo_nombre_y_nacimiento'); mismo nombre + mismo celular ('mismo_nombre_y_celular').
     Canónica = con documento válido > habilitada > id más bajo (estable entre corridas). Mismo documento con nombres que no se parecen NO se
     une: se marca 'documento_compartido_nombres_distintos' (suele ser el DNI del padre en la ficha del hijo). Mismo celular con
     otro nombre NO es duplicado: es familia ('celular_compartido', celular_compartido_n).
  R6 Origen probable de la ficha: 'bot_v6' (celular 549… exacto y sin documento, nacimiento, email ni dirección: el alta del v6
     manda solo nombre/apellido/celular), 'bot_v7' (ídem pero con documento: el v7 manda el DNI), 'staff' (resto).
     'posible_prueba' si el nombre dice prueba/test/demo/examen/asiri/nexora.
  R7 Citas: 'estado_desconocido', 'paciente_inexistente', 'sin_paciente', 'tratamiento_inexistente', 'profesional_inexistente',
     'sillon_inexistente', 'duracion_inconsistente' (hora_fin - hora_inicio ≠ duración), 'fuera_de_grilla' (minuto no múltiplo del
     intervalo del profesional), 'fuera_de_horario' (fuera del horario semanal vigente), solape_importado (se pisa con otra cita no
     anulada del mismo profesional; lo recalcula agenda.recalcular_solapes() al final de cada carga, también en las incrementales;
     NO se marca como sobreturno), origen_inferido por el comentario ('bot_v7' "…por Asiri",
     'bot_v6' "…por bot", 'panel' "…desde el panel", 'staff_o_desconocido'), 'posible_prueba' (comentario o ficha de prueba).
  R8 Planes/pagos/evoluciones/detalles: claves foráneas que no existen → NULL + flag '<x>_inexistente' (el id original queda en
     <x>_dentalink_id). 'monto_no_positivo' en pagos; 'deuda_negativa' en planes.
  R9 Desaparecidos: en una corrida COMPLETA, lo que estaba en el espejo y Dentalink ya no devuelve queda con desaparecida_at
     (no se borra). Si Dentalink devuelve <90% de lo que el espejo tiene activo, la carga ABORTA (extracción incompleta).

LÍMITES DE DENTALINK (medidos el 20/10: X-RateLimit-Limit 60 por minuto, compartido con el bot, los recordatorios y el panel)
  1 pedido cada 1,6 s como mínimo (≥1,5 s acordado en C11; ≤37/min); si quedan <25 en la ventana, espera 20 s (el bot conserva
  cupo); ante un 429 FRENA: pausa 120 s (o Retry-After) y, si vuelve a pasar en la misma corrida, corta SIN cargar nada; 5xx/timeout
  → 5/15/45 s. Cuando exista el limitador común en Redis (AGE-02), tomar el cupo de ahí. No pide nada de :59:30 a :01:00 ni de
  :29:30 a :31:00 (Health Check cada 30 min: un 429 ahí le manda una alerta falsa a Lucas) ni de 08:50 a 09:20 (Recordatorios).

PRIVACIDAD (repo PÚBLICO): la consola y el --reporte muestran SOLO agregados (conteos, %, rangos de fechas, nombres de catálogos).
La caché cruda (datos de pacientes) va a --cache-dir, que debe estar FUERA del repo (default: %TEMP%/dentalink_espejo). El token se
lee de DENTALINK_TOKEN (entorno o .env del repo) o del .env.local del panel; nunca se imprime.
"""
import argparse, datetime as dt, json, os, random, re, sys, tempfile, time, unicodedata, urllib.error, urllib.parse, urllib.request, uuid
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env  # noqa: E402

VERSION_ESQUEMA = "2026-10-20"
VERSION_SCRIPT = "2026-10-20.1"
BASE = "https://api.dentalink.healthatom.com/api/v1"
PANEL_ENV = ROOT.parent / "nexora-whatsapp-agent" / ".env.local"
FASES = "abcd"
FASE_NOMBRE = {"ocupacion": ["a"], "ficha_minima": ["a", "b"], "pacientes": ["a", "b", "c"], "clinica": ["a", "b", "c", "d"]}
LETRA_NOMBRE = {"a": "ocupacion", "b": "ficha_minima", "c": "pacientes", "d": "clinica"}


# ===================================================================================================================== cliente
class DentalinkSaturado(Exception):
    pass


class DentalinkSoloLectura:
    """Cliente GET-only con ritmo, reserva de cupo para el bot, ventanas prohibidas y reintentos."""

    def __init__(self, token, pausa=1.6, reserva=25, respetar_ventanas=True, log=print):
        self.token, self.pausa, self.reserva, self.respetar, self.log = token, pausa, reserva, respetar_ventanas, log
        self._ultimo, self._restantes = 0.0, None
        self.pedidos = 0
        self.n429 = 0
        self.stats = Counter()

    def _esperar_turno(self):
        falta = self.pausa - (time.time() - self._ultimo)
        if falta > 0:
            time.sleep(falta)
        while self.respetar:
            t = time.localtime()
            m, s = t.tm_min, t.tm_sec
            hc = (m in (59, 29) and s >= 30) or (m in (0, 30))
            rec = (t.tm_hour == 8 and m >= 50) or (t.tm_hour == 9 and m < 20)
            if not (hc or rec):
                break
            self.stats["esperas_ventana"] += 1
            time.sleep(5)
        if self._restantes is not None and self._restantes < self.reserva:
            self.stats["esperas_reserva"] += 1
            time.sleep(20)

    def _pedir(self, url):
        metodo = "GET"  # único método permitido. No hay ningún camino de escritura en este cliente.
        if not url.startswith(BASE + "/"):
            raise ValueError("URL fuera de la API de Dentalink (no se manda el token)")
        req = urllib.request.Request(url, method=metodo, headers={"Authorization": "Token " + self.token, "Accept": "application/json"})
        assert req.get_method() == "GET"
        return urllib.request.urlopen(req, timeout=40)

    def get(self, path_o_url, q=None):
        url = path_o_url if path_o_url.startswith("http") else BASE + path_o_url
        if q is not None:
            url += ("&" if "?" in url else "?") + "q=" + urllib.parse.quote(json.dumps(q, separators=(",", ":")))
        intentos_err = 0
        while True:
            self._esperar_turno()
            self._ultimo = time.time()
            self.pedidos += 1
            try:
                with self._pedir(url) as r:
                    try:
                        self._restantes = int(r.headers.get("X-RateLimit-Remaining"))
                    except (TypeError, ValueError):
                        self._restantes = None
                    self.stats[f"http_{r.status}"] += 1
                    return r.status, json.loads(r.read() or b"null")
            except urllib.error.HTTPError as e:
                self.stats[f"http_{e.code}"] += 1
                try:
                    cuerpo = json.loads(e.read() or b"null")
                except Exception:
                    cuerpo = None
                if e.code == 429:  # el bot está atendiendo: se frena. Una pausa larga; al segundo 429 de la corrida, se corta.
                    self.n429 += 1
                    if self.n429 >= 2:
                        raise DentalinkSaturado("Dentalink respondió 429 por segunda vez en la corrida: se corta sin cargar nada")
                    ra = e.headers.get("Retry-After")
                    espera = max(int(ra) if (ra or "").isdigit() else 0, 120)
                    self.log(f"  429 de Dentalink: freno {espera} s para no competir con el bot")
                    time.sleep(espera)
                    continue
                if e.code >= 500 and intentos_err < 3:
                    intentos_err += 1
                    time.sleep((5, 15, 45)[intentos_err - 1])
                    continue
                return e.code, cuerpo
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                self.stats["error_red"] += 1
                if intentos_err < 3:
                    intentos_err += 1
                    time.sleep((5, 15, 45)[intentos_err - 1])
                    continue
                raise DentalinkSaturado(f"Dentalink no responde ({type(e).__name__}): se corta sin cargar nada")

    def paginar(self, path, q=None, max_paginas=None):
        """Sigue links.next (cursor firmado de 50). Devuelve (items, completo, status_primera)."""
        items, url, pag, status0 = [], path, 0, None
        while url:
            st, b = self.get(url, q if pag == 0 else None)
            status0 = st if status0 is None else status0
            if st != 200 or not isinstance(b, dict):
                return items, False, status0 if pag == 0 else st
            d = b.get("data")
            if isinstance(d, list):
                items.extend(d)
            elif isinstance(d, dict):
                items.append(d)
            pag += 1
            nxt = (b.get("links") or {}).get("next") if isinstance(b.get("links"), dict) else None
            if not nxt or (isinstance(d, list) and not d):
                return items, True, status0
            if not nxt.startswith(BASE + "/"):
                raise ValueError("links.next apunta fuera de la API")
            if max_paginas and pag >= max_paginas:
                return items, False, status0
            url = nxt


def leer_token():
    t = env("DENTALINK_TOKEN")
    if t:
        return t
    p = Path(os.environ.get("PANEL_ENV", str(PANEL_ENV)))
    if p.exists():
        for linea in p.read_text(encoding="utf-8").splitlines():
            if linea.strip().startswith("DENTALINK_TOKEN="):
                return linea.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("ERROR: falta DENTALINK_TOKEN (entorno, .env del repo o .env.local del panel)")


# ===================================================================================================================== extracción
LISTAS = [  # entidad, ruta, filtro incremental (campo de fecha) o None
    ("sucursales", "/sucursales", None), ("especialidades", "/especialidades", None), ("dentistas", "/dentistas", None),
    ("sillones", "/sillones", None), ("estados_cita", "/citas/estados", None), ("aranceles", "/aranceles", None),
    ("categorias", "/categorias", None), ("prestaciones", "/prestaciones", None), ("bancos", "/bancos", None),
    ("laboratorios", "/laboratorios", None), ("convenios", "/convenios", None), ("usuarios", "/usuarios", None),
    ("cajas", "/cajas", None), ("pacientes", "/pacientes", None), ("citas", "/citas", "fecha_actualizacion"),
    ("tratamientos", "/tratamientos", None), ("pagos", "/pagos", None), ("evoluciones", "/evoluciones", "fecha_registro"),
    ("recetas", "/recetas", None),
]
ANIDADAS = [  # entidad, padre, ruta
    ("horarios", "dentistas", "/dentistas/{id}/horarios"), ("contratos", "dentistas", "/dentistas/{id}/contratos"),
    ("liquidaciones", "dentistas", "/dentistas/{id}/liquidaciones"), ("laboratorio_prestaciones", "laboratorios", "/laboratorios/{id}/prestaciones"),
    ("tratamiento_detalles", "tratamientos", "/tratamientos/{id}/detalles"), ("devoluciones", "cajas", "/cajas/{id}/devoluciones"),
]
POR_PACIENTE = ["archivos", "apoderados", "cargas", "adicionales", "convenios", "devoluciones", "tareas", "notificacionesGes"]
# (20/10) Antes del contrato (D12/C12, SEG-17): qué NO se pide a Dentalink y de qué se guarda solo el id.
SIN_CONTRATO_NO_PEDIR = {"cajas", "pagos", "evoluciones", "recetas", "convenios", "tratamiento_detalles", "devoluciones"}
SIN_CONTRATO_SOLO_ID = {"pacientes", "tratamientos"}
CANDIDATAS = [  # --descubrir: rutas probadas (las que responden 200 entran en LISTAS/ANIDADAS)
    "/sucursales", "/dentistas", "/citas", "/citas/estados", "/pacientes", "/tratamientos", "/pagos", "/evoluciones", "/prestaciones",
    "/aranceles", "/cajas", "/usuarios", "/especialidades", "/sillones", "/convenios", "/recetas", "/laboratorios", "/bancos",
    "/categorias", "/archivos", "/horarios", "/bloqueos", "/presupuestos", "/tareas", "/devoluciones", "/abonos", "/mediospago",
    "/gastos", "/documentos", "/formularios", "/odontogramas", "/fichas", "/campanas", "/encuestas", "/notificaciones", "/descuentos",
    "/feriados", "/motivos", "/citas/motivos", "/agendas", "/dentistas/1/horarios", "/dentistas/1/bloqueos", "/dentistas/1/contratos",
    "/dentistas/1/liquidaciones", "/dentistas/1/adicionales", "/sucursales/1/horarios", "/sucursales/1/bloqueos", "/sucursales/1/cajas",
    "/sucursales/1/usuarios", "/sucursales/1/sillones", "/agendas/bloqueos", "/horarios/bloqueos", "/especialidades/1",
]
# Texto clínico/libre (fase d): sin --incluir-clinico se reemplaza por su largo ANTES de guardar la caché.
CLINICO = {"pacientes": ["observaciones"], "citas": ["comentarios"], "tratamientos": ["comentario"], "evoluciones": ["datos"],
           "recetas": ["detalles"], "tratamiento_detalles": ["pieza"]}
RX_ORIGEN = [("bot_v7", re.compile(r"por asiri", re.I)), ("bot_v6", re.compile(r"por (el )?bot|bot \(sub-wf\)|whats ?app.*bot|bot.*whats ?app", re.I)),
             ("panel", re.compile(r"desde el panel", re.I))]
RX_SINTETICO = re.compile(r"549(0000000\d{3}|999\d{7})")  # forma de los teléfonos de prueba del proyecto (tests/, scripts/)
RX_PRUEBA = re.compile(r"\b(prueba|pruebas|test|testing|demo|examen|asiri|nexora)\b", re.I)


def redactar(entidad, item, incluir_clinico):
    """Calcula lo derivado del texto libre (origen, prueba) y, si no se incluye lo clínico, deja solo su largo."""
    if entidad == "citas":
        c = item.get("comentarios") or ""
        item["_origen_inferido"] = next((o for o, rx in RX_ORIGEN if rx.search(c)), "staff_o_desconocido")
        item["_prueba_texto"] = bool(RX_PRUEBA.search(c))
    if not incluir_clinico:
        for campo in CLINICO.get(entidad, []):
            v = item.get(campo)
            if v not in (None, "", [], {}):
                item[campo] = {"_redactado": True, "largo": len(json.dumps(v, ensure_ascii=False))}
    return item


def minimizar(ent, item):
    """(20/10) Sin contrato firmado (D12/C12) de una ficha o un plan solo queda el id: alcanza para vincular las citas de la fase
    ocupación sin marcarlas huérfanas. El resto se descarta acá, en memoria, antes de curar o de guardar nada."""
    return {"id": item.get("id")} if isinstance(item, dict) else item


def extraer(cli, args, log=print):
    """Extracción completa (o incremental). Devuelve dict entidad -> {'items': [...], 'completo': bool, 'status': int}.
    (20/10) Sin --contrato-firmado NO se piden las entidades con datos personales/clínicos (SIN_CONTRATO_NO_PEDIR) y de
    fichas y planes solo se conserva el id (SIN_CONTRATO_SOLO_ID): la primera corrida real los bajó completos sin necesitarlos."""
    datos, desde = {}, args.desde
    hacer = set(args.solo.split(",")) if args.solo else None
    sin_contrato = not getattr(args, "contrato_firmado", False)
    for ent, ruta, campo_inc in LISTAS:
        if hacer and ent not in hacer:
            continue
        if sin_contrato and ent in SIN_CONTRATO_NO_PEDIR:
            continue
        q = {campo_inc: {"gte": desde}} if (desde and campo_inc) else None
        t0 = time.time()
        items, completo, st = cli.paginar(ruta, q=q, max_paginas=args.max_paginas)
        if sin_contrato and ent in SIN_CONTRATO_SOLO_ID:
            items = [minimizar(ent, x) for x in items]
        datos[ent] = {"items": [redactar(ent, x, args.incluir_clinico) for x in items], "completo": completo and not q,
                      "incremental": bool(q), "status": st}
        log(f"  {ent:<24} {len(items):>6} filas  ({'completo' if completo else 'INCOMPLETO'}{', incremental' if q else ''}, {time.time() - t0:.0f} s)")
    for ent, padre, ruta in ANIDADAS:
        if hacer and ent not in hacer:
            continue
        if sin_contrato and ent in SIN_CONTRATO_NO_PEDIR:
            continue
        if ent == "tratamiento_detalles" and args.sin_detalles:
            continue
        padres = datos.get(padre, {}).get("items", [])
        ids = [p["id"] for p in padres if isinstance(p, dict) and p.get("id") is not None]
        incremental = False
        if ent == "tratamiento_detalles" and desde:
            # incremental: solo los planes nuevos o cuyos totales cambiaron respecto del espejo (el 20/10 había 687 de 689 planes
            # abiertos, así que "solo abiertos" no ahorraba nada). Sin espejo para comparar: solo los abiertos. La semanal completa trae todo.
            previos = getattr(args, "totales_planes", None)
            if previos is not None:
                ids = [p["id"] for p in padres if p.get("id") is not None and previos.get(p["id"]) != totales_plan(p)]
            else:
                ids = [p["id"] for p in padres if p.get("id") is not None and not bol(p.get("finalizado"))]
            incremental = True
        if ent == "devoluciones" and desde:  # incremental: solo cajas abiertas o cerradas desde la última corrida (305 pedidos → pocos)
            ids = [c["id"] for c in padres if c.get("id") is not None and (not txt(c.get("fecha_cierre")) or str(c.get("fecha_cierre"))[:10] >= desde[:10])]
            incremental = True
        items, completo, sts, t0 = [], True, Counter(), time.time()
        for pid in ids:
            sub, ok, st = cli.paginar(ruta.format(id=pid))
            sts[st] += 1
            for x in sub:
                if isinstance(x, dict):
                    x.setdefault("_padre_id", pid)
                    items.append(redactar(ent, x, args.incluir_clinico))
            completo = completo and (ok or st == 404)
        datos[ent] = {"items": items, "completo": completo and not incremental, "incremental": incremental, "status": dict(sts), "padres": len(ids)}
        log(f"  {ent:<24} {len(items):>6} filas  ({len(ids)} pedidos, {'completo' if completo else 'INCOMPLETO'}, {time.time() - t0:.0f} s)")
    if getattr(args, "con_archivos", False):
        # Solo existen por paciente (2 pedidos por ficha). Archivos = metadatos (los binarios se bajan aparte, plan §5); sin
        # --incluir-clinico solo quedan id y nombres de campos. Adicionales = campos personalizados de la ficha.
        pacs = [p["id"] for p in datos.get("pacientes", {}).get("items", []) if p.get("id") is not None]
        for sub in ("archivos", "adicionales"):
            items, completo, sts, t0 = [], True, Counter(), time.time()
            for pid in pacs:
                lst, ok, st = cli.paginar(f"/pacientes/{pid}/{sub}")
                sts[st] += 1
                completo = completo and (ok or st == 404)  # 404 = esa ficha no tiene
                for i, x in enumerate(lst):
                    if not isinstance(x, dict):
                        continue
                    x = dict(x)
                    x.setdefault("id", pid * 1000 + i)  # los adicionales no traen id: clave estable ficha*1000+posición
                    x["_padre_id"] = pid
                    if sub == "archivos" and not args.incluir_clinico:
                        x = {"id": x["id"], "_padre_id": pid, "_campos": sorted(k for k in x if not k.startswith("_"))}
                    items.append(x)
            datos[f"paciente_{sub}"] = {"items": items, "completo": completo, "status": dict(sts), "padres": len(pacs)}
            log(f"  paciente_{sub:<16} {len(items):>6} filas  ({len(pacs)} pedidos, {'completo' if completo else 'INCOMPLETO'}, {time.time() - t0:.0f} s)")
    return datos


def totales_plan(p):
    """Firma de un plan para saber si cambió (incremental de /tratamientos/{id}/detalles)."""
    f = lambda v: None if num(v) is None else float(num(v))  # noqa: E731
    return (f(p.get("total")), f(p.get("total_realizado")), f(p.get("abonado")), f(p.get("deuda")), bol(p.get("finalizado")))


def descubrir(cli, datos, n_muestra=30, log=print):
    """Rutas candidatas + muestreo de las rutas por paciente. Solo estado HTTP y cantidad: nada de contenido."""
    rutas = {}
    for r in CANDIDATAS:
        st, b = cli.get(r)
        n = len(b["data"]) if isinstance(b, dict) and isinstance(b.get("data"), list) else (1 if isinstance(b, dict) and isinstance(b.get("data"), dict) else None)
        msg = ""
        if st != 200 and isinstance(b, dict) and isinstance(b.get("error"), dict):
            msg = str(b["error"].get("message") or "")[:120]
        rutas[r] = {"status": st, "n_primera_pagina": n, "mensaje": msg}
    pac = [p["id"] for p in datos.get("pacientes", {}).get("items", []) if p.get("id")]
    con_citas = Counter(c.get("id_paciente") for c in datos.get("citas", {}).get("items", []))
    rnd = random.Random(20261020)
    muestra = sorted(set(rnd.sample(pac, min(n_muestra // 2, len(pac))) + [p for p, _ in con_citas.most_common(n_muestra // 2) if p in set(pac)]))
    por_pac = {}
    for sub in POR_PACIENTE:
        sts, filas, con = Counter(), 0, 0
        for pid in muestra:
            st, b = cli.get(f"/pacientes/{pid}/{sub}")
            sts[st] += 1
            n = len(b["data"]) if isinstance(b, dict) and isinstance(b.get("data"), list) else 0
            filas += n
            con += 1 if n else 0
        por_pac[sub] = {"pacientes_muestra": len(muestra), "status": dict(sts), "filas": filas, "pacientes_con_datos": con}
        log(f"  /pacientes/{{id}}/{sub:<18} status={dict(sts)} filas={filas}")
    return {"rutas": rutas, "por_paciente": por_pac}


# ===================================================================================================================== conversores
def txt(v):
    if v is None or isinstance(v, (dict, list)):
        return None
    s = re.sub(r"\s+", " ", str(v).replace("\x00", "")).strip()
    return s or None


def ent(v):
    if v is None or v == "" or isinstance(v, bool):
        return None if v is None or v == "" else int(v)
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return None


def num(v):
    if v is None or v == "":
        return None
    try:
        return float(v) if "." in str(v) else int(v)
    except (TypeError, ValueError):
        return None


def bol(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "si", "sí", "t")


def fecha(v):
    s = txt(v)
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s) or None
    if m:
        try:
            return dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            return None
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", s)
    if m:
        try:
            return dt.date(int(m[3]), int(m[2]), int(m[1])).isoformat()
        except ValueError:
            return None
    return None


def hora(v):
    s = txt(v)
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", s or "")
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        return None
    return f"{int(m[1]):02d}:{m[2]}:{m[3] or '00'}"


def ts(v):
    s = txt(v)
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)", s or "")
    if not m or not fecha(m[1]):
        return fecha(s) and (fecha(s) + " 00:00:00")
    return f"{m[1]} {hora(m[2]) or '00:00:00'}"


def minutos(h):
    return int(h[:2]) * 60 + int(h[3:5]) if h else None


def sin_tildes(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def clave_nombre(*partes):
    s = sin_tildes(" ".join(p for p in partes if p)).lower()
    toks = [t for t in re.split(r"[^a-z]+", s) if len(t) >= 2]
    return " ".join(sorted(toks)) or None


# ===================================================================================================================== curado R1-R4
def normalizar_celular(v):
    """R1. Devuelve (normalizado|None, estado)."""
    s = txt(v)
    if not s:
        return None, "vacio"
    if "@lid" in s.lower():
        return None, "lid"
    con_mas = s.lstrip().startswith("+")
    d = re.sub(r"\D", "", s)
    if len(d) < 6:
        return None, "falso"
    if d.startswith("00") and len(d) >= 12:  # prefijo internacional (00 + país + número)
        d, con_mas = d[2:], True
    if len(d) >= 14 and not d.startswith("54"):
        return None, "lid"
    if con_mas and not d.startswith("54"):
        return d, "extranjero"
    if RX_SINTETICO.fullmatch(d):
        return None, "sintetico"
    original_ok = bool(re.fullmatch(r"549[123]\d{9}", d))
    n = d
    if n.startswith("54"):
        n = n[2:]
        if n.startswith("9"):
            n = n[1:]
    if n.startswith("0"):
        n = n[1:]
    if len(n) == 11 and n.startswith("9"):
        n = n[1:]
    if len(n) == 12:
        for corte in ((2,) if n.startswith("11") else (3, 4)):
            if n[corte:corte + 2] == "15":
                n = n[:corte] + n[corte + 2:]
                break
    if re.fullmatch(r"(\d)\1+", n) or n in ("1234567890", "0123456789") or re.search(r"(\d)\1{6,}", n):
        return None, "falso"
    if len(n) == 10 and n[0] in "123":
        return "549" + n, "ok" if original_ok else "normalizado"
    if 6 <= len(n) <= 8:
        return None, "sin_codigo_area"
    return None, "invalido"


def normalizar_telefono(v):
    """Teléfono fijo/alternativo: misma limpieza, forma nacional 54+10 dígitos (sin el 9, porque no se sabe si es celular)."""
    n, est = normalizar_celular(v)
    return ("54" + n[3:], est) if n and n.startswith("549") else (n, est)


def normalizar_documento(v, tipo_documento=None, es_pasaporte=None):
    """R2. Devuelve (normalizado|None, estado)."""
    s = txt(v)
    if not s:
        return None, "vacio"
    n = re.sub(r"[\s.\-]", "", s).upper()
    if bol(es_pasaporte) or not n.isdigit():
        return (n if re.fullmatch(r"[A-Z0-9]{5,15}", n) else None), "pasaporte_u_otro"
    n = n.lstrip("0") or "0"
    if re.fullmatch(r"(\d)\1+", n) or n in ("12345678", "1234567", "123456789"):
        return None, "falso"
    if 7 <= len(n) <= 8:
        return n, "ok"
    if len(n) in (6, 9):
        return n, "dudoso"
    return None, "invalido"


RX_EMAIL = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
RX_EMAIL_FALSO = re.compile(r"^(no|sin|ninguno|notiene|no\.?tiene|nomail|sinmail|sin\.?mail|noemail|xxx+|aaa+|test|prueba)[@.]|@(no|sin|xxx|mail)\.", re.I)


def normalizar_email(v):
    """R3."""
    s = txt(v)
    if not s:
        return None, "vacio"
    e = s.lower().replace(" ", "")
    if RX_EMAIL_FALSO.search(e):
        return None, "falso"
    return (e, "ok") if RX_EMAIL.match(e) else (None, "invalido")


def edad(nac, hoy):
    if not nac:
        return None
    a, m, d = map(int, nac.split("-"))
    return hoy.year - a - ((hoy.month, hoy.day) < (m, d))


# ===================================================================================================================== curado por entidad
def ids(datos, entidad):
    return {x.get("id") for x in datos.get(entidad, {}).get("items", []) if x.get("id") is not None}


def ref(valor, conjunto, flags, nombre):
    """FK: el id si existe en el catálogo extraído; si no, NULL (+ flag si venía un id distinto de 0/vacío)."""
    v = ent(valor)
    if v is None:
        return None
    if v in conjunto:
        return v
    if v != 0:
        flags.add(f"{nombre}_inexistente")
    return None


def similares(a, b):
    ta, tb = set((a or "").split()), set((b or "").split())
    if not ta or not tb:
        return False
    return len(ta & tb) >= 2 or ta <= tb or tb <= ta


def curar(datos, hoy):
    """Arma las filas de cada tabla del espejo (todas las columnas, de todas las fases) + flags. Lo filtra por fase cargar()."""
    I = {e: ids(datos, e) for e in ("sucursales", "especialidades", "dentistas", "sillones", "estados_cita", "aranceles", "categorias",
                                     "prestaciones", "bancos", "usuarios", "cajas", "pacientes", "tratamientos", "convenios", "laboratorios")}
    T = {}
    def it(e):
        """Ítems de una entidad SIN ids repetidos (la paginación de Dentalink puede devolver la misma fila dos veces: el 20/10,
        17 en /evoluciones). Se queda la última aparición. Las anidadas compartidas (una prestación en varios laboratorios) se
        unen en dentalink_otros más abajo."""
        vistos, sin_id = {}, []
        for x in datos.get(e, {}).get("items", []):
            if not isinstance(x, dict):
                continue
            if x.get("id") is None or e in ("horarios", "laboratorio_prestaciones", "paciente_adicionales", "paciente_archivos"):
                sin_id.append(x)
            else:
                vistos[x["id"]] = x
        return list(vistos.values()) + sin_id

    T["sucursales"] = [dict(id=x["id"], nombre=txt(x.get("nombre")), direccion=txt(x.get("direccion")), telefono=txt(x.get("telefono")),
                            ciudad=txt(x.get("ciudad")), comuna=txt(x.get("comuna")), habilitada=bol(x.get("habilitada"))) for x in it("sucursales")]
    T["especialidades"] = [dict(id=x["id"], nombre=txt(x.get("nombre")), id_tipo_sucursal=ent(x.get("id_tipo_sucursal")),
                                habilitada=bol(x.get("habilitada"))) for x in it("especialidades")]
    T["profesionales"] = []
    for x in it("dentistas"):
        f = set()
        T["profesionales"].append(dict(id=x["id"], nombre=txt(x.get("nombre")), apellidos=txt(x.get("apellidos")),
                                       especialidad_id=ref(x.get("id_especialidad"), I["especialidades"], f, "especialidad"),
                                       sucursal_id=ref(x.get("id_sucursal"), I["sucursales"], f, "sucursal"), usuario_dentalink_id=ent(x.get("id_usuario")),
                                       intervalo_min=ent(x.get("intervalo")), habilitado=bol(x.get("habilitado")), agenda_online=bol(x.get("agenda_online")),
                                       rut=txt(x.get("rut")), email=txt(x.get("email")), celular=txt(x.get("celular")), telefono=txt(x.get("telefono")),
                                       direccion=txt(x.get("direccion")), ciudad=txt(x.get("ciudad")), comuna=txt(x.get("comuna")), calidad=sorted(f)))
    T["sillones"] = [dict(id=x["id"], nombre=txt(x.get("nombre"))) for x in it("sillones")]
    T["estados_cita"] = [dict(id=x["id"], nombre=txt(x.get("nombre")), color=txt(x.get("color")), anulacion=bol(x.get("anulacion")),
                              reservado=bol(x.get("reservado")), uso_interno=bol(x.get("uso_interno")), habilitado=bol(x.get("habilitado")),
                              categoria=categoria_estado(x)) for x in it("estados_cita")]
    anula = {e["id"]: bool(e["anulacion"]) for e in T["estados_cita"]}
    T["horarios"] = []
    grilla = {}  # (dentista, dia) -> (ini, fin, intervalo)
    for h in it("horarios"):
        for d in h.get("dias") or []:
            fila = dict(profesional_id=ent(h.get("id_dentista")), sucursal_id=ent(h.get("id_sucursal")), dia_semana=ent(d.get("dia")),
                        hora_inicio=hora(d.get("hora_inicio")), hora_fin=hora(d.get("hora_fin")), break_inicio=hora(d.get("hora_inicio_break")),
                        break_fin=hora(d.get("hora_fin_break")), intervalo_min=ent(h.get("intervalo")), sillones=ent(d.get("sillones")),
                        box_dentalink_id=ent(d.get("id_box")))
            if fila["profesional_id"] in I["dentistas"] and fila["sucursal_id"] in I["sucursales"] and fila["dia_semana"]:
                T["horarios"].append(fila)
                grilla[(fila["profesional_id"], fila["dia_semana"])] = (minutos(fila["hora_inicio"]), minutos(fila["hora_fin"]), fila["intervalo_min"] or 10)
    T["aranceles"] = [dict(id=x["id"], nombre=txt(x.get("nombre")), habilitado=bol(x.get("habilitado"))) for x in it("aranceles")]
    T["categorias_prestacion"] = [dict(id=x["id"], nombre=txt(x.get("nombre")), tipo=txt(x.get("tipo")), id_tipo=ent(x.get("id_tipo")),
                                       habilitado=bol(x.get("habilitado"))) for x in it("categorias")]
    T["prestaciones"] = []
    for x in it("prestaciones"):
        f = set()
        T["prestaciones"].append(dict(id=x["id"], codigo=txt(x.get("codigo")), nombre=txt(x.get("nombre")), precio=num(x.get("precio")),
                                      arancel_id=ref(x.get("id_arancel"), I["aranceles"], f, "arancel"),
                                      categoria_id=ref(x.get("id_categoria"), I["categorias"], f, "categoria"), tipo=txt(x.get("tipo")),
                                      id_tipo=ent(x.get("id_tipo")), habilitado=bol(x.get("habilitado")), calidad=sorted(f)))
    T["bancos"] = [dict(id=x["id"], nombre=txt(x.get("nombre")), habilitado=bol(x.get("habilitado"))) for x in it("bancos")]
    T["laboratorios"] = [dict(id=x["id"], nombre=txt(x.get("nombre")), direccion=txt(x.get("direccion")), telefono=txt(x.get("telefono")),
                              detalle=txt(x.get("detalle")), habilitado=bol(x.get("habilitado"))) for x in it("laboratorios")]
    T["convenios"] = [dict(id=x["id"], nombre=txt(x.get("nombre")), datos=x) for x in it("convenios")]
    T["usuarios"] = []
    for x in it("usuarios"):
        f = set()
        T["usuarios"].append(dict(id=x["id"], usuario=txt(x.get("usuario")), nombre=txt(x.get("nombre")),
                                  profesional_id=ref(x.get("id_dentista"), I["dentistas"], f, "profesional"),
                                  sucursal_id=ref(x.get("id_sucursal"), I["sucursales"], f, "sucursal"), habilitado=bol(x.get("habilitado")),
                                  rut=txt(x.get("rut")), email=txt(x.get("email")), celular=txt(x.get("celular")), telefono=txt(x.get("telefono")),
                                  calidad=sorted(f)))
    T["cajas"] = []
    for x in it("cajas"):
        f = set()
        T["cajas"].append(dict(id=x["id"], sucursal_id=ref(x.get("id_sucursal"), I["sucursales"], f, "sucursal"),
                               usuario_id=ref(x.get("id_usuario"), I["usuarios"], f, "usuario"), estado=ent(x.get("estado")),
                               fecha_apertura=ts(x.get("fecha_apertura")), fecha_cierre=ts(x.get("fecha_cierre")),
                               abono_inicial=num(x.get("abono_inicial")), acumulado=num(x.get("acumulado")), gastos=num(x.get("gastos")),
                               saldo_anterior=num(x.get("saldo_anterior")), saldo_inicial=num(x.get("saldo_inicial")),
                               saldo_cierre=num(x.get("saldo_cierre")), saldo_total=num(x.get("saldo_total")), calidad=sorted(f)))

    # ------------------------------------------------------------------ fichas (R1-R6)
    citas_por_ficha = Counter(ent(c.get("id_paciente")) for c in it("citas"))
    fichas = []
    for x in it("pacientes"):
        f = set()
        cel, cel_est = normalizar_celular(x.get("celular"))
        tel, _ = normalizar_telefono(x.get("telefono"))
        doc, doc_est = normalizar_documento(x.get("rut"), x.get("tipo_documento"), x.get("es_pasaporte"))
        mail, mail_est = normalizar_email(x.get("email"))
        crudo_nac = txt(x.get("fecha_nacimiento"))
        nac = fecha(crudo_nac)
        if not crudo_nac or crudo_nac.startswith("0000"):
            f.add("nacimiento_vacio")
            nac = None
        elif not nac:
            f.add("nacimiento_invalido")
        elif nac[:3] == "190" and nac[5:] == "01-01":
            f.add("nacimiento_relleno")
            nac = None
        elif nac < "1900-01-01" or nac > hoy.isoformat() or edad(nac, hoy) > 110:
            f.add("nacimiento_invalido")
            nac = None
        e = edad(nac, hoy)
        f.add(f"celular_{cel_est}") if cel_est not in ("ok",) else None
        f.add(f"documento_{doc_est}") if doc_est != "ok" else None
        f.add(f"email_{mail_est}") if mail_est != "ok" else None
        if not txt(x.get("direccion")):
            f.add("direccion_vacia")
        if not cel and tel:
            f.add("sin_celular_con_telefono")
        nombre_n = clave_nombre(x.get("nombre"), x.get("apellidos"))
        if not nombre_n:
            f.add("nombre_vacio")
        if RX_PRUEBA.search(f"{x.get('nombre') or ''} {x.get('apellidos') or ''}") or cel_est == "sintetico":
            f.add("posible_prueba")
        crudo_cel = re.sub(r"\D", "", str(x.get("celular") or ""))
        sin_extra = not txt(x.get("email")) and not txt(x.get("direccion")) and not nac
        origen = "staff"
        if re.fullmatch(r"549\d{10}", crudo_cel) and str(x.get("celular")).strip() == crudo_cel and sin_extra:
            origen = "bot_v7" if doc else "bot_v6"
        elif cel_est == "lid" and sin_extra:
            origen = "bot_v6"
        fichas.append(dict(id=x["id"], habilitado=bol(x.get("habilitado")), celular_normalizado=cel, celular_estado=cel_est,
                           es_menor=(e < 18) if e is not None else None, fecha_afiliacion=fecha(x.get("fecha_afiliacion")),
                           origen_probable=origen, nombre=txt(x.get("nombre")), apellidos=txt(x.get("apellidos")),
                           nombre_social=txt(x.get("nombre_social")), nombre_normalizado=nombre_n, documento=txt(x.get("rut")),
                           documento_normalizado=doc, documento_estado=doc_est, tipo_documento=ent(x.get("tipo_documento")),
                           es_pasaporte=bol(x.get("es_pasaporte")), fecha_nacimiento=nac, sexo=txt(x.get("sexo")), id_genero=ent(x.get("id_genero")),
                           celular=txt(x.get("celular")), telefono=txt(x.get("telefono")), telefono_normalizado=tel, email=txt(x.get("email")),
                           email_normalizado=mail, direccion=txt(x.get("direccion")), ciudad=txt(x.get("ciudad")), comuna=txt(x.get("comuna")),
                           numero_ficha=txt(x.get("numero_ficha")), fecha_deshabilitacion=fecha(x.get("fecha_deshabilitacion")),
                           usuario_deshabilitacion_dentalink_id=ent(x.get("id_usuario_deshabilitacion")), es_carga=bol(x.get("es_carga")),
                           tiene_cargas=bol(x.get("tiene_cargas")), observaciones=x.get("observaciones") if isinstance(x.get("observaciones"), str) else None,
                           _citas=citas_por_ficha.get(x["id"], 0), _flags=f, duplicado_de=None, duplicado_regla=None, celular_compartido_n=None))
    marcar_duplicados(fichas)
    por_cel = Counter(fi["celular_normalizado"] for fi in fichas if fi["celular_normalizado"])
    for fi in fichas:
        n = por_cel.get(fi["celular_normalizado"]) if fi["celular_normalizado"] else None
        if n and n > 1:
            fi["celular_compartido_n"] = n
            otros = [o for o in fichas if o["celular_normalizado"] == fi["celular_normalizado"] and o is not fi and not o["duplicado_de"] and not fi["duplicado_de"]]
            if any(o["nombre_normalizado"] != fi["nombre_normalizado"] for o in otros):
                fi["_flags"].add("celular_compartido")
        fi["calidad"] = sorted(fi.pop("_flags"))
    T["fichas"] = fichas
    prueba_ficha = {fi["id"] for fi in fichas if "posible_prueba" in fi["calidad"]}

    # ------------------------------------------------------------------ planes de tratamiento
    T["tratamientos"] = []
    for x in it("tratamientos"):
        f = set()
        T["tratamientos"].append(dict(id=x["id"], ficha_id=ref(x.get("id_paciente"), I["pacientes"], f, "paciente"),
                                      paciente_dentalink_id=ent(x.get("id_paciente")),
                                      profesional_id=ref(x.get("id_dentista"), I["dentistas"], f, "profesional"),
                                      sucursal_id=ref(x.get("id_sucursal"), I["sucursales"], f, "sucursal"),
                                      convenio_dentalink_id=ent(x.get("id_convenio")) or None, nombre=txt(x.get("nombre")), fecha=fecha(x.get("fecha")),
                                      total=num(x.get("total")), total_realizado=num(x.get("total_realizado")), abonado=num(x.get("abonado")),
                                      deuda=num(x.get("deuda")), abono_libre=num(x.get("abono_libre")), asignado_realizado=num(x.get("asignado_realizado")),
                                      asignado_sin_realizar=num(x.get("asignado_sin_realizar")), finalizado=bol(x.get("finalizado")),
                                      bloqueado=bol(x.get("bloqueado")), comentario=x.get("comentario") if isinstance(x.get("comentario"), str) else None,
                                      _f=f))
        if (num(x.get("deuda")) or 0) < 0:
            f.add("deuda_negativa")
        if not txt(x.get("nombre")):
            f.add("sin_nombre")
    for r in T["tratamientos"]:
        r["calidad"] = sorted(r.pop("_f"))

    # ------------------------------------------------------------------ citas (R7)
    citas = []
    for x in it("citas"):
        f = set()
        est = ref(x.get("id_estado"), I["estados_cita"], f, "estado")
        if "estado_inexistente" in f:
            f.discard("estado_inexistente")
            f.add("estado_desconocido")
        pid = ent(x.get("id_paciente"))
        ficha_id = ref(pid, I["pacientes"], f, "paciente")
        if not pid:
            f.add("sin_paciente")
        trat = ent(x.get("id_tratamiento"))
        trat_id = ref(trat, I["tratamientos"], f, "tratamiento") if not bol(x.get("tratamiento_sin_asignar")) else (trat if trat in I["tratamientos"] else None)
        prof = ref(x.get("id_dentista"), I["dentistas"], f, "profesional")
        fe, hi, hf, du = fecha(x.get("fecha")), hora(x.get("hora_inicio")), hora(x.get("hora_fin")), ent(x.get("duracion"))
        if hi and hf and du is not None and minutos(hf) - minutos(hi) != du:
            f.add("duracion_inconsistente")
        dia = dt.date.fromisoformat(fe).isoweekday() if fe else None
        g = grilla.get((prof, dia))
        fuera = False
        if hi and g:
            ini, fin, paso = g
            if minutos(hi) % (paso or 10):
                f.add("fuera_de_grilla")
            if ini is None or fin is None or fin <= ini or minutos(hi) < ini or minutos(hi) >= fin:
                fuera = True
                f.add("fuera_de_horario")
        if x.get("_prueba_texto") or (ficha_id in prueba_ficha):
            f.add("posible_prueba")
        citas.append(dict(id=x["id"], fecha=fe, hora_inicio=hi, hora_fin=hf, duracion_min=du, estado_id=est,
                          anulada=anula.get(est) if est is not None else None, estado_confirmacion=ent(x.get("estado_confirmacion")),
                          estado_anulacion=ent(x.get("estado_anulacion")), sucursal_id=ref(x.get("id_sucursal"), I["sucursales"], f, "sucursal"),
                          profesional_id=prof, sillon_id=ref(x.get("id_sillon"), I["sillones"], f, "sillon"), motivo_atencion=txt(x.get("motivo_atencion")),
                          tratamiento_sin_asignar=bol(x.get("tratamiento_sin_asignar")), dentalink_actualizado_at=ts(x.get("fecha_actualizacion")),
                          origen_inferido=x.get("_origen_inferido"), _solape=False, fuera_de_horario=fuera,
                          ficha_id=ficha_id, paciente_dentalink_id=pid or None, tratamiento_id=trat_id, tratamiento_dentalink_id=trat or None,
                          comentarios=x.get("comentarios") if isinstance(x.get("comentarios"), str) else None, _f=f))
    # solapes: mismo profesional y día, ambas no anuladas, intervalos que se pisan
    por_dia = defaultdict(list)
    for c in citas:
        if c["fecha"] and c["hora_inicio"] and c["hora_fin"] and c["anulada"] is False:
            por_dia[(c["profesional_id"], c["fecha"])].append(c)
    for lista in por_dia.values():
        lista.sort(key=lambda c: c["hora_inicio"])
        fin_max, previa = -1, None
        for c in lista:
            ini = minutos(c["hora_inicio"])
            if previa is not None and ini < fin_max:
                c["_solape"] = previa["_solape"] = True  # solo para el reporte: en la base lo recalcula agenda.recalcular_solapes()
            if minutos(c["hora_fin"]) > fin_max:
                fin_max, previa = minutos(c["hora_fin"]), c
    for c in citas:
        c["calidad"] = sorted(c.pop("_f"))
    T["citas"] = citas

    T["tratamiento_detalles"] = []
    for x in it("tratamiento_detalles"):
        f = set()
        T["tratamiento_detalles"].append(dict(id=x["id"], tratamiento_id=ref(x.get("id_tratamiento") or x.get("_padre_id"), I["tratamientos"], f, "tratamiento"),
                                              prestacion_id=ref(x.get("id_prestacion"), I["prestaciones"], f, "prestacion"),
                                              nombre_prestacion=txt(x.get("nombre_prestacion")), tipo_prestacion=txt(x.get("tipo_prestacion")),
                                              precio=num(x.get("precio")), descuento_convenio=num(x.get("descuento_convenio")),
                                              descuento_usuario=num(x.get("descuento_usuario")), descuento_total=num(x.get("descuento_total")),
                                              total=num(x.get("total")), pagado=num(x.get("pagado")), realizado=bol(x.get("realizado")),
                                              futura_realizacion=bol(x.get("futura_realizacion")), liquidado=bol(x.get("liquidado")),
                                              fecha_creacion=ts(x.get("fecha_creacion")), fecha_realizacion=ts(x.get("fecha_realizacion")),
                                              profesional_realizador_id=ref(x.get("id_dentista_realizador"), I["dentistas"], f, "profesional"),
                                              usuario_creador_dentalink_id=ent(x.get("id_usuario_creador")),
                                              pieza=x.get("pieza") if isinstance(x.get("pieza"), list) else None, calidad=sorted(f)))
    T["pagos"] = []
    for x in it("pagos"):
        f = set()
        if (num(x.get("monto_pago")) or 0) <= 0:
            f.add("monto_no_positivo")
        T["pagos"].append(dict(id=x["id"], ficha_id=ref(x.get("id_paciente"), I["pacientes"], f, "paciente"), paciente_dentalink_id=ent(x.get("id_paciente")) or None,
                               caja_id=ref(x.get("id_caja"), I["cajas"], f, "caja"), sucursal_id=ref(x.get("id_sucursal"), I["sucursales"], f, "sucursal"),
                               banco_id=ref(x.get("id_banco"), I["bancos"], f, "banco"), medio_pago_dentalink_id=ent(x.get("id_medio_pago")),
                               medio_pago=txt(x.get("medio_pago")), monto=num(x.get("monto_pago")), folio=txt(x.get("folio")),
                               numero_referencia=txt(x.get("numero_referencia")), fecha_creacion=ts(x.get("fecha_creacion")),
                               fecha_recepcion=fecha(x.get("fecha_recepcion")), fecha_vencimiento=fecha(x.get("fecha_vencimiento")),
                               tipo_pagador=txt(x.get("tipo_pagador")), pagador_dentalink_id=ent(x.get("id_pagador")) or None,
                               nombre_pagador=txt(x.get("nombre_pagador")), rut_emisor=txt(x.get("rut_emisor")), calidad=sorted(f)))
    T["evoluciones"] = []
    for x in it("evoluciones"):
        f = set()
        T["evoluciones"].append(dict(id=x["id"], ficha_id=ref(x.get("id_paciente"), I["pacientes"], f, "paciente"), paciente_dentalink_id=ent(x.get("id_paciente")) or None,
                                     tratamiento_id=ref(x.get("id_tratamiento"), I["tratamientos"], f, "tratamiento"),
                                     profesional_id=ref(x.get("id_dentista"), I["dentistas"], f, "profesional"),
                                     sucursal_id=ref(x.get("id_sucursal"), I["sucursales"], f, "sucursal"), usuario_dentalink_id=ent(x.get("id_usuario")),
                                     fecha=fecha(x.get("fecha")), fecha_registro=ts(x.get("fecha_registro")), habilitado=bol(x.get("habilitado")),
                                     datos=x.get("datos") if isinstance(x.get("datos"), str) else None, calidad=sorted(f)))
    T["recetas"] = []
    for x in it("recetas"):
        f = set()
        T["recetas"].append(dict(id=x["id"], ficha_id=ref(x.get("id_paciente"), I["pacientes"], f, "paciente"), paciente_dentalink_id=ent(x.get("id_paciente")) or None,
                                 tratamiento_id=ref(x.get("id_tratamiento"), I["tratamientos"], f, "tratamiento"), creador_dentalink_id=ent(x.get("id_creador")),
                                 eliminador_dentalink_id=ent(x.get("id_eliminador")) or None, fecha_creacion=ts(x.get("fecha_creacion")),
                                 fecha_eliminacion=ts(x.get("fecha_eliminacion")), habilitado=bol(x.get("habilitado")),
                                 detalles=x.get("detalles") if isinstance(x.get("detalles"), str) else None, calidad=sorted(f)))
    T["dentalink_otros"] = []
    otros = {}
    for e, fase in (("contratos", "c"), ("liquidaciones", "c"), ("laboratorio_prestaciones", "a"), ("devoluciones", "c"),
                    ("paciente_adicionales", "c"), ("paciente_archivos", "d")):
        for x in it(e):
            if x.get("id") is None:
                continue
            clave = (e, x["id"])
            if clave in otros:  # la misma fila bajo otro padre (p. ej. una prestación en dos laboratorios): se anota el padre
                otros[clave]["datos"].setdefault("_padres", [otros[clave]["padre_dentalink_id"]]).append(x.get("_padre_id"))
                continue
            limpio = {k: v for k, v in x.items() if k not in ("links",) and not k.startswith("_")}
            otros[clave] = dict(entidad=e, dentalink_id=x["id"], padre_dentalink_id=x.get("_padre_id"), fase=fase, datos=limpio)
    T["dentalink_otros"] = list(otros.values())
    return T


def categoria_estado(x):
    i, n = ent(x.get("id")), sin_tildes(txt(x.get("nombre")) or "").lower()
    if bol(x.get("anulacion")):
        return "anulada"
    if i == 2 or n.startswith("atendido"):
        return "atendida"
    if i == 8 or "no asiste" in n:
        return "no_asistio"
    if i in (5, 6) or "sala de espera" in n or "atendiendose" in n:
        return "en_curso"
    if n.startswith("confirmado"):
        return "confirmada"
    if n.startswith("notificado"):
        return "notificada"
    if i == 7 or n.startswith("no confirmado") or "agenda online" in n:
        return "pendiente"
    return "otro"


def marcar_duplicados(fichas):
    """R5. Union-find por documento, nombre+nacimiento, nombre+celular. Marca duplicado_de/duplicado_regla; no borra nada."""
    padre = {f["id"]: f["id"] for f in fichas}
    regla = {}
    por_id = {f["id"]: f for f in fichas}

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    def unir(a, b, r):
        ra, rb = raiz(a), raiz(b)
        if ra != rb:
            padre[rb] = ra
            regla.setdefault(b, r)
            regla.setdefault(a, r)

    grupos = defaultdict(list)
    for f in fichas:
        if f["documento_estado"] == "ok":
            grupos[("doc", f["documento_normalizado"])].append(f)
        if f["nombre_normalizado"] and f["fecha_nacimiento"]:
            grupos[("nac", f["nombre_normalizado"], f["fecha_nacimiento"])].append(f)
        if f["nombre_normalizado"] and f["celular_normalizado"]:
            grupos[("cel", f["nombre_normalizado"], f["celular_normalizado"])].append(f)
    nombres_regla = {"doc": "mismo_documento", "nac": "mismo_nombre_y_nacimiento", "cel": "mismo_nombre_y_celular"}
    for k, lista in grupos.items():
        if len(lista) < 2:
            continue
        base = lista[0]
        for otro in lista[1:]:
            if k[0] == "doc" and not similares(base["nombre_normalizado"], otro["nombre_normalizado"]):
                base["_flags"].add("documento_compartido_nombres_distintos")
                otro["_flags"].add("documento_compartido_nombres_distintos")
                continue
            if k[0] == "doc" or not (base["documento_normalizado"] and otro["documento_normalizado"] and base["documento_normalizado"] != otro["documento_normalizado"]):
                unir(base["id"], otro["id"], nombres_regla[k[0]])
    componentes = defaultdict(list)
    for f in fichas:
        componentes[raiz(f["id"])].append(f)
    for comp in componentes.values():
        if len(comp) < 2:
            continue
        canon = sorted(comp, key=lambda f: (f["documento_estado"] != "ok", f["habilitado"] is not True, f["id"]))[0]
        for f in comp:
            if f is not canon:
                f["duplicado_de"] = canon["id"]
                f["duplicado_regla"] = regla.get(f["id"], "mismo_documento")
                f["_flags"].add("duplicado")
        canon["_flags"].add("tiene_duplicados")


# ===================================================================================================================== esquema de carga
# tabla -> (fase mínima de la tabla, clave de conflicto, {columna: (fase, tipo)}). Tipos: i entero, n numérico, t texto, b bool,
# d fecha, h hora, s timestamp, j jsonb, a text[]. 'id' = dentalink_id (las filas propias nuevas arrancan en 10.000.000).
C = lambda **kw: kw  # noqa: E731
ESQUEMA = {
    "sucursales": ("a", "dentalink_id", C(nombre=("a", "t"), direccion=("a", "t"), telefono=("a", "t"), ciudad=("a", "t"), comuna=("a", "t"), habilitada=("a", "b"))),
    "especialidades": ("a", "dentalink_id", C(nombre=("a", "t"), id_tipo_sucursal=("a", "i"), habilitada=("a", "b"))),
    "profesionales": ("a", "dentalink_id", C(nombre=("a", "t"), apellidos=("a", "t"), especialidad_id=("a", "i"), sucursal_id=("a", "i"),
                                             usuario_dentalink_id=("a", "i"), intervalo_min=("a", "i"), habilitado=("a", "b"), agenda_online=("a", "b"),
                                             calidad=("a", "a"), rut=("c", "t"), email=("c", "t"), celular=("c", "t"), telefono=("c", "t"),
                                             direccion=("c", "t"), ciudad=("c", "t"), comuna=("c", "t"))),
    "sillones": ("a", "dentalink_id", C(nombre=("a", "t"))),
    "estados_cita": ("a", "dentalink_id", C(nombre=("a", "t"), color=("a", "t"), anulacion=("a", "b"), reservado=("a", "b"), uso_interno=("a", "b"),
                                            habilitado=("a", "b"), categoria=("a", "t"))),
    "horarios": ("a", "profesional_id,sucursal_id,dia_semana", C(profesional_id=("a", "i"), sucursal_id=("a", "i"), dia_semana=("a", "i"),
                                                                 hora_inicio=("a", "h"), hora_fin=("a", "h"), break_inicio=("a", "h"), break_fin=("a", "h"),
                                                                 intervalo_min=("a", "i"), sillones=("a", "i"), box_dentalink_id=("a", "i"))),
    "aranceles": ("a", "dentalink_id", C(nombre=("a", "t"), habilitado=("a", "b"))),
    "categorias_prestacion": ("a", "dentalink_id", C(nombre=("a", "t"), tipo=("a", "t"), id_tipo=("a", "i"), habilitado=("a", "b"))),
    "prestaciones": ("a", "dentalink_id", C(codigo=("a", "t"), nombre=("a", "t"), precio=("a", "n"), arancel_id=("a", "i"), categoria_id=("a", "i"),
                                            tipo=("a", "t"), id_tipo=("a", "i"), habilitado=("a", "b"), calidad=("a", "a"))),
    "bancos": ("a", "dentalink_id", C(nombre=("a", "t"), habilitado=("a", "b"))),
    "laboratorios": ("a", "dentalink_id", C(nombre=("a", "t"), direccion=("a", "t"), telefono=("a", "t"), detalle=("a", "t"), habilitado=("a", "b"))),
    "convenios": ("c", "dentalink_id", C(nombre=("c", "t"), datos=("c", "j"))),
    "usuarios": ("a", "dentalink_id", C(usuario=("a", "t"), nombre=("a", "t"), profesional_id=("a", "i"), sucursal_id=("a", "i"), habilitado=("a", "b"),
                                        calidad=("a", "a"), rut=("c", "t"), email=("c", "t"), celular=("c", "t"), telefono=("c", "t"))),
    "cajas": ("c", "dentalink_id", C(sucursal_id=("c", "i"), usuario_id=("c", "i"), estado=("c", "i"), fecha_apertura=("c", "s"), fecha_cierre=("c", "s"),
                                     abono_inicial=("c", "n"), acumulado=("c", "n"), gastos=("c", "n"), saldo_anterior=("c", "n"), saldo_inicial=("c", "n"),
                                     saldo_cierre=("c", "n"), saldo_total=("c", "n"), calidad=("c", "a"))),
    "fichas": ("b", "dentalink_id", C(habilitado=("b", "b"), celular_normalizado=("b", "t"), celular_estado=("b", "t"), es_menor=("b", "b"),
                                      fecha_afiliacion=("b", "d"), origen_probable=("b", "t"), duplicado_de=("b", "i"), duplicado_regla=("b", "t"),
                                      celular_compartido_n=("b", "i"), calidad=("b", "a"),
                                      nombre=("c", "t"), apellidos=("c", "t"), nombre_social=("c", "t"), nombre_normalizado=("c", "t"),
                                      documento=("c", "t"), documento_normalizado=("c", "t"), documento_estado=("c", "t"), tipo_documento=("c", "i"),
                                      es_pasaporte=("c", "b"), fecha_nacimiento=("c", "d"), sexo=("c", "t"), id_genero=("c", "i"), celular=("c", "t"),
                                      telefono=("c", "t"), telefono_normalizado=("c", "t"), email=("c", "t"), email_normalizado=("c", "t"),
                                      direccion=("c", "t"), ciudad=("c", "t"), comuna=("c", "t"), numero_ficha=("c", "t"),
                                      fecha_deshabilitacion=("c", "d"), usuario_deshabilitacion_dentalink_id=("c", "i"), es_carga=("c", "b"),
                                      tiene_cargas=("c", "b"), observaciones=("d", "t"))),
    "tratamientos": ("c", "dentalink_id", C(ficha_id=("c", "i"), paciente_dentalink_id=("c", "i"), profesional_id=("c", "i"), sucursal_id=("c", "i"),
                                            convenio_dentalink_id=("c", "i"), nombre=("c", "t"), fecha=("c", "d"), total=("c", "n"),
                                            total_realizado=("c", "n"), abonado=("c", "n"), deuda=("c", "n"), abono_libre=("c", "n"),
                                            asignado_realizado=("c", "n"), asignado_sin_realizar=("c", "n"), finalizado=("c", "b"), bloqueado=("c", "b"),
                                            calidad=("c", "a"), comentario=("d", "t"))),
    "citas": ("a", "dentalink_id", C(fecha=("a", "d"), hora_inicio=("a", "h"), hora_fin=("a", "h"), duracion_min=("a", "i"), estado_id=("a", "i"),
                                     anulada=("a", "b"), estado_confirmacion=("a", "i"), estado_anulacion=("a", "i"), sucursal_id=("a", "i"),
                                     profesional_id=("a", "i"), sillon_id=("a", "i"), motivo_atencion=("a", "t"), tratamiento_sin_asignar=("a", "b"),
                                     dentalink_actualizado_at=("a", "s"), origen_inferido=("a", "t"), fuera_de_horario=("a", "b"), calidad=("a", "a"), ficha_id=("b", "i"), paciente_dentalink_id=("b", "i"),
                                     tratamiento_id=("c", "i"), tratamiento_dentalink_id=("c", "i"), comentarios=("d", "t"))),
    "tratamiento_detalles": ("c", "dentalink_id", C(tratamiento_id=("c", "i"), prestacion_id=("c", "i"), nombre_prestacion=("c", "t"),
                                                    tipo_prestacion=("c", "t"), precio=("c", "n"), descuento_convenio=("c", "n"), descuento_usuario=("c", "n"),
                                                    descuento_total=("c", "n"), total=("c", "n"), pagado=("c", "n"), realizado=("c", "b"),
                                                    futura_realizacion=("c", "b"), liquidado=("c", "b"), fecha_creacion=("c", "s"),
                                                    fecha_realizacion=("c", "s"), profesional_realizador_id=("c", "i"),
                                                    usuario_creador_dentalink_id=("c", "i"), calidad=("c", "a"), pieza=("d", "j"))),
    "pagos": ("c", "dentalink_id", C(ficha_id=("c", "i"), paciente_dentalink_id=("c", "i"), caja_id=("c", "i"), sucursal_id=("c", "i"), banco_id=("c", "i"),
                                     medio_pago_dentalink_id=("c", "i"), medio_pago=("c", "t"), monto=("c", "n"), folio=("c", "t"),
                                     numero_referencia=("c", "t"), fecha_creacion=("c", "s"), fecha_recepcion=("c", "d"), fecha_vencimiento=("c", "d"),
                                     tipo_pagador=("c", "t"), pagador_dentalink_id=("c", "i"), nombre_pagador=("c", "t"), rut_emisor=("c", "t"),
                                     calidad=("c", "a"))),
    "evoluciones": ("d", "dentalink_id", C(ficha_id=("d", "i"), paciente_dentalink_id=("d", "i"), tratamiento_id=("d", "i"), profesional_id=("d", "i"),
                                           sucursal_id=("d", "i"), usuario_dentalink_id=("d", "i"), fecha=("d", "d"), fecha_registro=("d", "s"),
                                           habilitado=("d", "b"), datos=("d", "t"), calidad=("d", "a"))),
    "recetas": ("d", "dentalink_id", C(ficha_id=("d", "i"), paciente_dentalink_id=("d", "i"), tratamiento_id=("d", "i"), creador_dentalink_id=("d", "i"),
                                       eliminador_dentalink_id=("d", "i"), fecha_creacion=("d", "s"), fecha_eliminacion=("d", "s"), habilitado=("d", "b"),
                                       detalles=("d", "t"), calidad=("d", "a"))),
    "dentalink_otros": ("a", "entidad,dentalink_id", C(entidad=("a", "t"), dentalink_id=("a", "i"), padre_dentalink_id=("a", "i"), fase=("a", "t"),
                                                       datos=("a", "j"))),
}
ORDEN = list(ESQUEMA)  # ya está en orden de dependencias
ENTIDAD_DE = {"profesionales": "dentistas", "categorias_prestacion": "categorias", "fichas": "pacientes", "estados_cita": "estados_cita"}


def lit(v, tipo):
    if v is None:
        return "null"
    if tipo == "b":
        return "true" if v else "false"
    if tipo == "i":
        return str(int(v))
    if tipo == "n":
        return repr(float(v)) if isinstance(v, float) else str(int(v))
    if tipo == "j":
        return "'" + json.dumps(v, ensure_ascii=False).replace("\x00", "").replace("'", "''") + "'::jsonb"
    if tipo == "a":
        return "array[" + ",".join(lit(x, "t") for x in v) + "]::text[]" if v else "'{}'::text[]"
    s = str(v).replace("\x00", "").replace("'", "''")
    return {"d": f"'{s}'::date", "h": f"'{s}'::time", "s": f"'{s}'::timestamp"}.get(tipo, f"'{s}'")


def sentencias_carga(T, datos, fases, tipo, corrida, pedidos, conteos, lote=400):
    """SQL de la carga (una transacción). La misma lista la ejecuta --apply y la escribe --dump-sql."""
    fx = set(fases)
    out = ["begin;", "set local statement_timeout = '600s';", "set local lock_timeout = '5s';",
           f"do $$ begin if not exists (select 1 from agenda.esquema_version where version = '{VERSION_ESQUEMA}') then "
           f"raise exception 'falta aplicar sql/{VERSION_ESQUEMA}_dentalink_espejo.sql'; end if; end $$;",
           f"select set_config('agenda.corrida_id', '{corrida}', true);",
           "insert into agenda.sync_corridas (id, inicio, tipo, fases, estado, pedidos_dentalink, conteos, script_version) values ("
           f"'{corrida}', now(), {lit(tipo, 't')}, {lit(sorted(fx), 'a')}, 'en_curso', {int(pedidos)}, {lit(conteos, 'j')}, {lit(VERSION_SCRIPT, 't')});"]
    for tabla in ORDEN:
        fase_t, conflicto, cols = ESQUEMA[tabla]
        if fase_t not in fx:
            continue
        filas = T.get(tabla, [])
        if tabla == "dentalink_otros":
            filas = [r for r in filas if r["fase"] in fx]
        usar = [c for c, (fa, _) in cols.items() if fa in fx]
        tiene_id = conflicto == "dentalink_id"
        lista = (["id", "dentalink_id"] if tiene_id else []) + usar
        tipos = ({"id": "i", "dentalink_id": "i"} if tiene_id else {}) | {c: cols[c][1] for c in usar}
        ent_api = ENTIDAD_DE.get(tabla, tabla)
        completo = datos.get(ent_api, {}).get("completo", False) and not datos.get(ent_api, {}).get("incremental")
        if tiene_id and completo and tipo == "completa" and filas:
            out.append(f"do $$ declare n bigint; begin select count(*) into n from agenda.{tabla} where dentalink_id is not null and desaparecida_at is null; "
                       f"if n > 0 and {len(filas)} < n * 0.9 then raise exception '{tabla}: Dentalink devolvió % filas y el espejo tiene % activas: "
                       f"se aborta (extracción incompleta)', {len(filas)}, n; end if; end $$;")
        claves = conflicto.split(",")
        unicas = {}
        for r in filas:  # ON CONFLICT DO UPDATE no admite la misma clave dos veces en un mismo INSERT
            unicas[tuple((r["id"] if (c == "dentalink_id" and tiene_id) else r.get(c)) for c in claves)] = r
        filas = list(unicas.values())
        for i in range(0, len(filas), lote):
            vals = []
            for r in filas[i:i + lote]:
                fila = dict(r)
                if tiene_id:
                    fila["dentalink_id"] = fila["id"]
                vals.append("(" + ", ".join(lit(fila.get(c), tipos[c]) for c in lista) + f", '{corrida}'::uuid)")
            upd = [c for c in lista if c not in ("id", "dentalink_id") and c not in conflicto.split(",")]
            set_ = ", ".join(f"{c} = excluded.{c}" for c in upd)
            dif = " or ".join(f"t.{c} is distinct from excluded.{c}" for c in upd) or "false"
            reaparece = ", desaparecida_at = null" if tiene_id else ""
            out.append(f"insert into agenda.{tabla} as t ({', '.join(lista)}, espejo_corrida_id) values\n  " + ",\n  ".join(vals) +
                       f"\non conflict ({conflicto}) do update set {set_}{', ' if set_ else ''}espejo_corrida_id = excluded.espejo_corrida_id, "
                       f"espejo_actualizado_at = now(){reaparece}\n  where {dif}" + (" or t.desaparecida_at is not null" if tiene_id else "") + ";")
        if tiene_id and completo and tipo == "completa":
            vistos = "{" + ",".join(str(int(r["id"])) for r in filas) + "}"
            out.append(f"update agenda.{tabla} set desaparecida_at = now(), espejo_corrida_id = '{corrida}'::uuid where dentalink_id is not null "
                       f"and desaparecida_at is null and not (dentalink_id = any('{vistos}'::bigint[]));")
    out.append("select agenda.recalcular_solapes();")
    out.append(f"update agenda.sync_corridas set fin = now(), estado = 'ok' where id = '{corrida}';")
    out.append(f"update agenda.config set valor = {lit(','.join(sorted(fx)), 't')}, actualizado_at = now(), actualizado_por = 'migrar_dentalink' "
               "where clave = 'espejo_ultimas_fases';")
    out.append("commit;")
    return out


# ===================================================================================================================== reporte (solo agregados)
def vacio(v):
    return v in (None, "", [], {}) or (isinstance(v, str) and (v.strip() == "" or v.startswith("0000-00-00")))


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def inventario(datos, T, hoy):
    rep = {}
    fechas = {"pacientes": ["fecha_afiliacion"], "citas": ["fecha", "fecha_actualizacion"], "tratamientos": ["fecha"],
              "pagos": ["fecha_recepcion", "fecha_creacion"], "evoluciones": ["fecha", "fecha_registro"], "cajas": ["fecha_apertura"],
              "recetas": ["fecha_creacion"], "tratamiento_detalles": ["fecha_creacion", "fecha_realizacion"]}
    for e, d in datos.items():
        items = [x for x in d.get("items", []) if isinstance(x, dict)]
        campos = sorted({k for x in items for k in x if k != "links" and not k.startswith("_")})
        cob = {}
        for c in campos:
            nv = sum(1 for x in items if not (vacio(x.get(c)) or (c.startswith("id_") and x.get(c) in (0, "0"))))
            cob[c] = pct(nv, len(items))
        rangos = {}
        for c in fechas.get(e, []):
            vs = sorted(v for v in (fecha(x.get(c)) for x in items) if v)
            if vs:
                rangos[c] = [vs[0], vs[-1]]
        ids_ = [x.get("id") for x in items if x.get("id") is not None]
        rep[e] = {"filas": len(items), "completo": d.get("completo"), "status": d.get("status"), "campos": len(campos), "cobertura_pct": cob,
                  "rango_fechas": rangos, "ids_unicos": len(set(ids_)), "ids_repetidos": len(ids_) - len(set(ids_))}
        if "padres" in d:
            rep[e]["pedidos"] = d["padres"]
    return rep


def calidad(T, datos, hoy):
    q = {}
    F = T.get("fichas", [])
    if F:
        cnt = lambda pred: sum(1 for f in F if pred(f))  # noqa: E731
        q["fichas"] = {
            "total": len(F), "habilitadas": cnt(lambda f: f["habilitado"]), "deshabilitadas": cnt(lambda f: f["habilitado"] is False),
            "celular_estado": dict(Counter(f["celular_estado"] for f in F)), "documento_estado": dict(Counter(f["documento_estado"] for f in F)),
            "email_estado": dict(Counter(normalizar_email(f["email"])[1] for f in F)),
            "nacimiento_vacio": cnt(lambda f: "nacimiento_vacio" in f["calidad"]), "nacimiento_relleno_1900": cnt(lambda f: "nacimiento_relleno" in f["calidad"]),
            "nacimiento_invalido": cnt(lambda f: "nacimiento_invalido" in f["calidad"]),
            "direccion_vacia": cnt(lambda f: "direccion_vacia" in f["calidad"]), "sin_celular_con_telefono": cnt(lambda f: "sin_celular_con_telefono" in f["calidad"]),
            "menores": cnt(lambda f: f["es_menor"] is True), "edad_desconocida": cnt(lambda f: f["es_menor"] is None),
            "duplicadas_marcadas": cnt(lambda f: f["duplicado_de"]), "grupos_con_duplicados": cnt(lambda f: "tiene_duplicados" in f["calidad"]),
            "duplicado_regla": dict(Counter(f["duplicado_regla"] for f in F if f["duplicado_regla"])),
            "documento_compartido_nombres_distintos": cnt(lambda f: "documento_compartido_nombres_distintos" in f["calidad"]),
            "celulares_compartidos_por_varias_fichas": len({f["celular_normalizado"] for f in F if f["celular_compartido_n"]}),
            "fichas_en_celular_compartido": cnt(lambda f: f["celular_compartido_n"]),
            "max_fichas_por_celular": max([f["celular_compartido_n"] or 1 for f in F] or [0]),
            "origen_probable": dict(Counter(f["origen_probable"] for f in F)),
            "origen_bot_por_mes_alta": dict(Counter((f["fecha_afiliacion"] or "?")[:7] for f in F if f["origen_probable"].startswith("bot"))),
            "posible_prueba": cnt(lambda f: "posible_prueba" in f["calidad"]),
            "nombre_vacio": cnt(lambda f: "nombre_vacio" in f["calidad"]),
            "sin_ninguna_cita": cnt(lambda f: f["_citas"] == 0), "tipo_documento": dict(Counter(str(f["tipo_documento"]) for f in F)),
            "fichas_creadas_por_mes_ultimos_12": dict(sorted(Counter((f["fecha_afiliacion"] or "?")[:7] for f in F
                                                                     if (f["fecha_afiliacion"] or "") >= (hoy - dt.timedelta(days=365)).isoformat()).items())),
        }
    Ci = T.get("citas", [])
    if Ci:
        est = {e["id"]: e["nombre"] for e in T.get("estados_cita", [])}
        cat = {e["id"]: e["categoria"] for e in T.get("estados_cita", [])}
        hoy_s = hoy.isoformat()
        fut = [c for c in Ci if (c["fecha"] or "") >= hoy_s]
        flags = Counter(fl for c in Ci for fl in c["calidad"])
        q["citas"] = {
            "total": len(Ci), "futuras": len(fut), "pasadas": len(Ci) - len(fut),
            "por_estado": {f"{k} {est.get(k, '?')}": v for k, v in sorted(Counter(c["estado_id"] for c in Ci).items(), key=lambda kv: -kv[1])},
            "por_categoria": dict(Counter(cat.get(c["estado_id"], "?") for c in Ci)),
            "futuras_por_estado": {f"{k} {est.get(k, '?')}": v for k, v in sorted(Counter(c["estado_id"] for c in fut).items(), key=lambda kv: -kv[1])},
            "por_anio": dict(sorted(Counter((c["fecha"] or "?")[:4] for c in Ci).items())),
            "duracion_min": dict(Counter(c["duracion_min"] for c in Ci).most_common(8)),
            "flags": dict(flags.most_common()),
            "flags_en_futuras_no_anuladas": dict(Counter(fl for c in fut if c["anulada"] is False for fl in c["calidad"]).most_common()),
            "origen_inferido": dict(Counter(c["origen_inferido"] for c in Ci)),
            "origen_inferido_ultimos_90_dias": dict(Counter(c["origen_inferido"] for c in Ci if (c["fecha"] or "") >= (hoy - dt.timedelta(days=90)).isoformat())),
            "motivos_distintos": len({c["motivo_atencion"] for c in Ci if c["motivo_atencion"]}),
            "motivos_frecuentes": {k: v for k, v in Counter(c["motivo_atencion"] for c in Ci if c["motivo_atencion"]).most_common(12) if v >= 10 and len(k) <= 40},
            "sin_tratamiento_asignado": sum(1 for c in Ci if c["tratamiento_sin_asignar"]),
            "pacientes_distintos": len({c["paciente_dentalink_id"] for c in Ci if c["paciente_dentalink_id"]}),
            # ¿quién pone cada estado? (AGE-02: el 15 "Notificado por WhatsApp"): a qué hora y cuántos días antes del turno se actualizó la cita
            "hora_actualizacion_por_estado": {str(k): dict(sorted(Counter(c["dentalink_actualizado_at"][11:13] for c in Ci if c["estado_id"] == k and c["dentalink_actualizado_at"]).items()))
                                              for k in (1, 7, 15, 18, 19, 20, 22)},
            "dias_antes_del_turno_por_estado": {str(k): dict(sorted(Counter(min(max((dt.date.fromisoformat(c["fecha"]) - dt.date.fromisoformat(c["dentalink_actualizado_at"][:10])).days, -1), 8)
                                                                              for c in Ci if c["estado_id"] == k and c["dentalink_actualizado_at"] and c["fecha"]).items()))
                                                for k in (1, 7, 15, 18, 19, 20, 22)},
            "solapes_no_anuladas": sum(1 for c in Ci if c["_solape"]),
            "solapes_futuras": sum(1 for c in fut if c["_solape"]),
        }
    Tr = T.get("tratamientos", [])
    if Tr:
        q["tratamientos"] = {"total": len(Tr), "finalizados": sum(1 for t in Tr if t["finalizado"]), "con_deuda": sum(1 for t in Tr if (t["deuda"] or 0) > 0),
                             "flags": dict(Counter(fl for t in Tr for fl in t["calidad"])), "nombres_distintos": len({t["nombre"] for t in Tr if t["nombre"]}),
                             "nombres_frecuentes": {k: v for k, v in Counter(t["nombre"] for t in Tr if t["nombre"]).most_common(15) if v >= 10 and len(k) <= 40},
                             "fichas_con_plan": len({t["ficha_id"] for t in Tr if t["ficha_id"]})}
    for tabla in ("pagos", "evoluciones", "tratamiento_detalles", "recetas", "cajas", "prestaciones", "usuarios", "profesionales"):
        R = T.get(tabla, [])
        if R:
            q[tabla] = {"total": len(R), "flags": dict(Counter(fl for r in R for fl in r.get("calidad", [])))}
    if T.get("pagos"):
        q["pagos"]["medio_pago"] = dict(Counter(p["medio_pago"] for p in T["pagos"]))
        q["pagos"]["tipo_pagador"] = dict(Counter(p["tipo_pagador"] for p in T["pagos"]))
    if T.get("evoluciones"):
        q["evoluciones"]["con_texto"] = len({x.get("id") for x in datos.get("evoluciones", {}).get("items", []) if not vacio(x.get("datos"))})
        q["evoluciones"]["fichas_con_evoluciones"] = len({e["ficha_id"] for e in T["evoluciones"] if e["ficha_id"]})
    if T.get("tratamiento_detalles"):
        q["tratamiento_detalles"]["realizadas"] = sum(1 for x in T["tratamiento_detalles"] if x["realizado"])
        q["tratamiento_detalles"]["con_pieza_dental"] = sum(1 for x in datos.get("tratamiento_detalles", {}).get("items", []) if not vacio(x.get("pieza")))
    if T.get("usuarios"):
        q["usuarios"]["habilitados"] = sum(1 for u in T["usuarios"] if u["habilitado"])
    q["estados_cita_catalogo"] = [{"id": e["id"], "nombre": e["nombre"], "anulacion": e["anulacion"], "categoria": e["categoria"],
                                   "habilitado": e["habilitado"]} for e in T.get("estados_cita", [])]
    q["horarios"] = [{"profesional_id": h["profesional_id"], "dia": h["dia_semana"], "desde": h["hora_inicio"], "hasta": h["hora_fin"],
                      "intervalo": h["intervalo_min"]} for h in T.get("horarios", []) if h["hora_fin"] and h["hora_inicio"] and h["hora_fin"] > h["hora_inicio"]]
    return q


def carga_simulada(T, fases):
    fx, res = set(fases), {}
    for tabla, (fase_t, _, cols) in ESQUEMA.items():
        filas = T.get(tabla, [])
        res[tabla] = {"fase_tabla": LETRA_NOMBRE[fase_t], "filas": len(filas), "se_carga_con_esta_fase": fase_t in fx,
                      "columnas_por_fase": {LETRA_NOMBRE[k]: v for k, v in Counter(fa for fa, _ in cols.values()).items()}}
    return res


# ===================================================================================================================== base (apply / verificar)
def conectar(solo_lectura=True):
    import psycopg2
    req = ["SUPABASE_DB_HOST", "SUPABASE_DB_PORT", "SUPABASE_DB_NAME", "SUPABASE_DB_USER", "SUPABASE_DB_PASSWORD"]
    falta = [k for k in req if not env(k)]
    if falta:
        sys.exit(f"ERROR: faltan {falta} en el .env del repo")
    c = psycopg2.connect(host=env("SUPABASE_DB_HOST"), port=env("SUPABASE_DB_PORT"), dbname=env("SUPABASE_DB_NAME"),
                         user=env("SUPABASE_DB_USER"), password=env("SUPABASE_DB_PASSWORD"), sslmode="require", connect_timeout=15)
    if solo_lectura:
        c.set_session(readonly=True, autocommit=True)
    return c


def esquema_listo(cur):
    cur.execute("select to_regclass('agenda.esquema_version') is not null")
    if not cur.fetchone()[0]:
        return False
    cur.execute("select 1 from agenda.esquema_version where version = %s", (VERSION_ESQUEMA,))
    return cur.fetchone() is not None


def desde_ultima_corrida(cur):
    cur.execute("select max(inicio) from agenda.sync_corridas where estado = 'ok'")
    r = cur.fetchone()[0]
    return (r - dt.timedelta(days=1)).strftime("%Y-%m-%d 00:00:00") if r else None


def verificar(T, datos):
    c = conectar(True)
    cur = c.cursor()
    if not esquema_listo(cur):
        print("El esquema agenda no está aplicado: nada que verificar.")
        return 2
    mal = 0
    print(f"{'tabla':<24}{'dentalink':>10}{'espejo':>10}{'faltan':>8}{'sobran':>8}{'desap.':>8}")
    for tabla, (fase_t, conflicto, _) in ESQUEMA.items():
        if conflicto != "dentalink_id" or tabla == "dentalink_otros" or ENTIDAD_DE.get(tabla, tabla) not in datos:
            continue  # sin clave de Dentalink, o no se extrajo en esta corrida (p. ej. --sin-detalles)
        esperado = {r["id"] for r in T.get(tabla, [])}
        cur.execute(f"select dentalink_id, desaparecida_at is not null from agenda.{tabla} where dentalink_id is not null")
        filas = cur.fetchall()
        if not filas and not esperado:
            continue
        activos = {i for i, d in filas if not d}
        desap = sum(1 for _, d in filas if d)
        faltan, sobran = len(esperado - activos), len(activos - esperado)
        cargada = bool(filas)
        estado = "" if (not faltan and not sobran) else ("  <- NO CARGADA (fase)" if not cargada else "  <- DIFERENCIA")
        mal += 1 if (cargada and (faltan or sobran)) else 0
        print(f"{tabla:<24}{len(esperado):>10}{len(activos):>10}{faltan:>8}{sobran:>8}{desap:>8}{estado}")
    if T.get("citas"):
        cur.execute("select estado_id, count(*) from agenda.citas where desaparecida_at is null group by 1")
        en_espejo = dict(cur.fetchall())
        en_dl = Counter(x["estado_id"] for x in T["citas"])
        dif = {k: (en_dl.get(k, 0), en_espejo.get(k, 0)) for k in set(en_dl) | set(en_espejo) if en_dl.get(k, 0) != en_espejo.get(k, 0)}
        print("citas por estado:", "iguales" if not dif else f"DIFERENCIAS {dif}")
        mal += 1 if dif else 0
    print("RESULTADO:", "OK, espejo conciliado" if not mal else f"{mal} diferencias")
    return 0 if not mal else 1


# ===================================================================================================================== main
def main():
    ap = argparse.ArgumentParser(description="Espejo de Dentalink en agenda.* (simulación por defecto)")
    ap.add_argument("--apply", action="store_true", help="carga real en el Supabase v3 (exige el SQL aplicado)")
    ap.add_argument("--verificar", action="store_true", help="compara Dentalink vs espejo (solo lectura)")
    ap.add_argument("--fase", default="ocupacion", choices=list(FASE_NOMBRE),
                    help="ocupacion (sin datos de pacientes) | ficha_minima (C12 b) | pacientes (completo, tras el contrato) | clinica")
    ap.add_argument("--contrato-firmado", action="store_true", help="confirma SEG-17 firmado: habilita ficha_minima, pacientes y clinica")
    ap.add_argument("--incluir-clinico", action="store_true", help="extrae y guarda texto clínico (fase clinica). Sin esto solo su largo")
    ap.add_argument("--incremental", action="store_true", help="citas/evoluciones desde la última corrida OK (-1 día)")
    ap.add_argument("--desde", help="incremental manual: 'YYYY-MM-DD HH:MM:SS' para citas.fecha_actualizacion y evoluciones.fecha_registro")
    ap.add_argument("--usar-cache", action="store_true", help="no pide nada a Dentalink: usa la última extracción de --cache-dir")
    ap.add_argument("--guardar-cache", action="store_true", help="(20/10) guarda la extracción cruda en --cache-dir. Por defecto NO se guarda nada en disco")
    ap.add_argument("--cache-dir", default=os.environ.get("DENTALINK_CACHE_DIR", str(Path(tempfile.gettempdir()) / "dentalink_espejo")))
    ap.add_argument("--reporte", help="escribe el reporte agregado (JSON, sin datos personales) en esta ruta")
    ap.add_argument("--descubrir", action="store_true", help="prueba rutas candidatas y muestrea las rutas por paciente")
    ap.add_argument("--solo", help="limitar a estas entidades (coma). Para pruebas")
    ap.add_argument("--max-paginas", type=int, help="tope de páginas por lista. Para pruebas (la corrida queda INCOMPLETA)")
    ap.add_argument("--sin-detalles", action="store_true", help="no pide /tratamientos/{id}/detalles (1 pedido por plan)")
    ap.add_argument("--con-archivos", action="store_true", help="pide /pacientes/{id}/archivos y /adicionales (2 pedidos por ficha, ~50 min)")
    ap.add_argument("--pausa", type=float, default=1.6, help="segundos mínimos entre pedidos (default 1.6)")
    ap.add_argument("--fixture", help="JSON {entidad: [items crudos]} SINTÉTICO en lugar de la API (sin red)")
    ap.add_argument("--dump-sql", help="escribe el SQL de carga en este archivo (no ejecuta nada)")
    ap.add_argument("--hoy", help="fecha de referencia YYYY-MM-DD (tests)")
    ap.add_argument("--corrida-id", help="uuid de la corrida (tests)")
    args = ap.parse_args()

    fases = FASE_NOMBRE[args.fase]
    if args.fase != "ocupacion" and not args.contrato_firmado and (args.apply or args.dump_sql) and not args.fixture:
        sys.exit(f"ERROR: --fase {args.fase} copia datos de pacientes: exige --contrato-firmado (SEG-17, D12/C12). "
                 "Antes del contrato solo --fase ocupacion")
    if "d" in fases and not args.incluir_clinico and (args.apply or args.dump_sql) and not args.fixture:
        sys.exit("ERROR: --fase clinica (historia clínica) exige --incluir-clinico (decisión de la Dra., Ley 26.529)")
    if args.verificar and (args.desde or args.incremental or args.apply):
        sys.exit("ERROR: --verificar compara contra una extracción COMPLETA y no carga nada (sin --desde/--incremental/--apply)")
    if args.con_archivos and not args.contrato_firmado and not args.fixture:
        sys.exit("ERROR: --con-archivos pide los archivos de cada ficha (datos de pacientes): exige --contrato-firmado (SEG-17, D12/C12)")
    if args.apply and (args.solo or args.max_paginas or args.fixture):
        sys.exit("ERROR: --solo/--max-paginas/--fixture son para pruebas: con --apply dejarían FKs en NULL o marcarían desaparecidos")
    cache = Path(args.cache_dir).resolve()
    if ROOT.resolve() in [cache, *cache.parents]:
        sys.exit("ERROR: --cache-dir no puede estar dentro del repo (es público y la caché tiene datos de pacientes)")
    hoy = dt.date.fromisoformat(args.hoy) if args.hoy else dt.date.today()
    corrida = args.corrida_id or str(uuid.uuid4())
    t0 = time.time()

    if args.incremental and not args.desde and args.apply:
        con = conectar(True)
        cur = con.cursor()
        if not esquema_listo(cur):
            sys.exit("ERROR: el esquema agenda no está aplicado (correr primero sql/2026-10-20_dentalink_espejo.sql)")
        args.desde = desde_ultima_corrida(cur)
        cur.execute("select dentalink_id, total, total_realizado, abonado, deuda, finalizado from agenda.tratamientos where dentalink_id is not null")
        args.totales_planes = {r[0]: tuple([None if v is None else float(v) for v in r[1:5]] + [r[5]]) for r in cur.fetchall()} or None
        con.close()
        print(f"Incremental desde {args.desde or '(no hay corrida previa: completa)'}")

    descubrimiento, pedidos, stats = None, 0, {}
    if args.fixture:
        crudo = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
        datos = {k: {"items": [redactar(k, x, True) for x in v], "completo": True, "status": 200} for k, v in crudo.items()}
        print(f"Fixture sintético: {sum(len(v['items']) for v in datos.values())} filas")
    elif args.usar_cache:
        ult = sorted(cache.glob("extraccion_*.json"))
        if not ult:
            sys.exit(f"ERROR: no hay extracciones en {cache}")
        datos = json.loads(ult[-1].read_text(encoding="utf-8"))
        meta = datos.pop("_meta", {})
        descubrimiento = meta.get("descubrimiento")
        pedidos, stats = meta.get("pedidos", 0), meta.get("stats", {})
        print(f"Caché: {ult[-1].name} ({meta.get('fecha')}, {pedidos} pedidos, clínico incluido: {meta.get('incluir_clinico')})")
        edad_h = (dt.datetime.now() - dt.datetime.fromisoformat(meta.get("fecha", "2000-01-01T00:00:00"))).total_seconds() / 3600
        if args.apply and edad_h > 2:
            sys.exit(f"ERROR: la caché tiene {edad_h:.0f} h: cargarla pisaría cambios más nuevos (y marcaría como desaparecido lo creado después). "
                     "Extraer de nuevo (sin --usar-cache)")
        if args.apply and "d" in fases and not meta.get("incluir_clinico"):
            sys.exit("ERROR: esa caché no tiene el texto clínico (se extrajo sin --incluir-clinico): cargar la fase d desde ella lo dejaría en NULL")
        args.desde = meta.get("desde")
    else:
        cli = DentalinkSoloLectura(leer_token(), pausa=args.pausa)
        print(f"Extrayendo de Dentalink (solo GET, ≥{args.pausa} s entre pedidos){' desde ' + args.desde if args.desde else ''}…")
        try:
            datos = extraer(cli, args)
            if args.descubrir:
                print("Descubrimiento de rutas…")
                descubrimiento = descubrir(cli, datos)
        except DentalinkSaturado as e:
            sys.exit(f"CORTADO: {e}. Pedidos hechos: {cli.pedidos}")
        pedidos, stats = cli.pedidos, dict(cli.stats)
        if args.guardar_cache:
            cache.mkdir(parents=True, exist_ok=True)
            f = cache / f"extraccion_{dt.datetime.now():%Y%m%d_%H%M%S}.json"
            f.write_text(json.dumps({**datos, "_meta": {"fecha": dt.datetime.now().isoformat(timespec="seconds"), "pedidos": pedidos, "stats": stats,
                                                        "incluir_clinico": args.incluir_clinico, "desde": args.desde,
                                                        "descubrimiento": descubrimiento}}, ensure_ascii=False), encoding="utf-8")
            print(f"Extracción: {pedidos} pedidos en {time.time() - t0:.0f} s. Caché cruda (fuera del repo; borrarla al terminar): {f}")
        else:
            print(f"Extracción: {pedidos} pedidos en {time.time() - t0:.0f} s (sin caché en disco; --guardar-cache para guardarla)")

    T = curar(datos, hoy)
    inv, cal = inventario(datos, T, hoy), calidad(T, datos, hoy)
    tipo = "incremental" if args.desde else "completa"
    incompletas = [e for e, d in datos.items() if not d.get("completo") and not d.get("incremental")]
    reporte = {"generado": dt.datetime.now().isoformat(timespec="seconds"), "script": VERSION_SCRIPT, "hoy": hoy.isoformat(), "tipo": tipo,
               "pedidos_dentalink": pedidos, "stats_http": stats, "entidades_incompletas": incompletas, "inventario": inv, "calidad": cal,
               "carga_simulada": carga_simulada(T, FASES if not args.apply else fases), "descubrimiento": descubrimiento}

    print("\n=== INVENTARIO (filas por entidad) ===")
    for e, r in inv.items():
        print(f"  {e:<26}{r['filas']:>7}  campos={r['campos']:<3} {'' if r['completo'] else 'INCOMPLETO '}{r['rango_fechas'] or ''}")
    print("\n=== CALIDAD (agregados) ===")
    for k in ("fichas", "citas", "tratamientos", "pagos", "evoluciones", "tratamiento_detalles"):
        if k in cal:
            print(f"  [{k}] " + json.dumps({a: b for a, b in cal[k].items() if a not in ("fichas_creadas_por_mes_ultimos_12",)}, ensure_ascii=False)[:1800])
    print("\n=== CARGA (qué tablas entran con qué fases) ===")
    for t, r in reporte["carga_simulada"].items():
        print(f"  agenda.{t:<24}{r['filas']:>7} filas  fase {r['fase_tabla']}  columnas por fase {r['columnas_por_fase']}")
    if args.reporte:
        Path(args.reporte).write_text(json.dumps(reporte, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nReporte agregado: {args.reporte}")

    if args.verificar:
        sys.exit(verificar(T, datos))
    sql = None
    if args.apply or args.dump_sql:
        conteos = {t: len(T.get(t, [])) for t in ESQUEMA}
        sql = sentencias_carga(T, datos, fases, tipo, corrida, pedidos, conteos)
    if args.dump_sql:
        Path(args.dump_sql).write_text("\n".join(sql) + "\n", encoding="utf-8")
        print(f"SQL de carga ({len(sql)} sentencias) en {args.dump_sql}")
    if not args.apply:
        print(f"\nSIMULACIÓN: no se escribió nada en ninguna base. Para cargar: --apply --fase {args.fase}"
              + (" --contrato-firmado" if args.fase != "ocupacion" else "") + (" --incluir-clinico" if args.fase == "clinica" else ""))
        return
    if incompletas:
        sys.exit(f"ERROR: extracción incompleta en {incompletas}: no se carga nada")
    con = conectar(False)
    con.autocommit = True  # la transacción la abren/cierran el begin/commit del propio SQL
    cur = con.cursor()
    if not esquema_listo(cur):
        sys.exit("ERROR: el esquema agenda no está aplicado (correr primero sql/2026-10-20_dentalink_espejo.sql)")
    try:
        for s in sql:
            cur.execute(s)
        print(f"APLICADO: corrida {corrida} ({tipo}, fase {args.fase}) en {time.time() - t0:.0f} s")
    except Exception as e:
        try:
            cur.execute("rollback")
        except Exception:
            pass
        try:
            cur.execute("insert into agenda.sync_corridas (id, inicio, fin, tipo, fases, estado, pedidos_dentalink, avisos, script_version) "
                        "values (%s, now(), now(), %s, %s, 'error', %s, %s::jsonb, %s)",
                        (corrida, tipo, sorted(set(fases)), pedidos, json.dumps([str(e)[:300]]), VERSION_SCRIPT))
        except Exception:
            pass
        sys.exit(f"ERROR en la carga (rollback, nada quedó a medias): {str(e)[:300]}")
    finally:
        con.close()
    if tipo == "completa":
        print("\nVerificación contra esta misma extracción (conteos, ids y citas por estado):")
        sys.exit(verificar(T, datos))


if __name__ == "__main__":
    main()
