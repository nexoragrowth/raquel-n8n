# -*- coding: utf-8 -*-
"""
examen_v7.py — EXAMEN del v7 con PACIENTE SIMULADO (diseño v7 §8b). Se juzga el RESULTADO (qué herramientas corrieron y qué habrían
escrito en la agenda), no el texto. Corre contra el cerebro v7 REAL en n8n, en MODO SOMBRA (lecturas reales de Dentalink, escrituras,
avisos y memoria simulados por código; no manda WhatsApp). El paciente lo juega otro modelo (OpenAI) con un objetivo y una persona.

  python tests/examen_v7.py --offline                          # prueba el examen en sí, con cerebro y paciente falsos (sin red)
  python tests/examen_v7.py --solo AGE-03 CON-01               # escenarios puntuales contra el v7 real
  python tests/examen_v7.py --todos --reps 5                   # los 25 escenarios × 5 repeticiones
  python tests/examen_v7.py --todos --guion                    # cerebro REAL en sombra, paciente que sigue el guion real (sin OPENAI_API_KEY): humo, no examen
  python tests/examen_v7.py --todos --reps 1 --phone 549...    # otro celular de prueba (tiene que tener fichas de prueba)

Necesita: N8N_BASE_URL + ruta del webhook de prueba (data/v7_test_ruta.txt, activo) + OPENAI_API_KEY (solo para el paciente simulado).
Al terminar SIEMPRE reinicia el estado Redis del celular (teardown), aunque falle. Resultados: tests/examen_v7_results.json (gitignored).
Regla del proyecto #8: nada "funciona" hasta recorrer el camino completo; este examen recorre n8n → modelo → herramientas → chequeo de salida.
Nota: --offline prueba el EXAMEN (loop, juez, teardown) con un cerebro de juguete que sigue los guiones reales; da ~18/25 porque el juguete no entiende
todas las frases del guion. Eso es esperado: el veredicto que importa es el de --todos contra el v7 real.
"""
import argparse, json, re, statistics, sys, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lib_env import env, require  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
ESCENARIOS = json.loads((ROOT / "tests" / "escenarios" / "turnos.json").read_text(encoding="utf-8"))
SALIDA = ROOT / "tests" / "examen_v7_results.json"
PHONE_PRUEBA = "5491161461034"
MAX_TURNOS = 8
OBJETIVO_LAT_P95 = 10.0
MODELO_PACIENTE = "gpt-5-mini"

# ----------------------------------------------------------------------------- qué exige cada función (resultado, no texto)
# Cada regla mira el LOG DE HERRAMIENTAS de toda la conversación (lo que el cerebro devuelve en `tools`) y las salidas por turno.
def _llamadas(turnos, nombre):
    return [t for tu in turnos for t in (tu.get("tools") or []) if t.get("tool") == nombre]

def _obs_json(t):
    """La observación de una herramienta vuelve como texto (JSON de n8n, a veces una lista). Devuelve el dict o {}."""
    try:
        o = json.loads(t.get("obs") or "null")
        if isinstance(o, list): o = o[0] if o else {}
        return o if isinstance(o, dict) else {}
    except Exception:
        return {}

def _propuso(turnos, tipo):
    return [t for t in _llamadas(turnos, "proponer") if (t.get("input") or {}).get("tipo") == tipo and _obs_json(t).get("ok") is True]

def _ejecuto_ok(turnos):
    return [t for t in _llamadas(turnos, "ejecutar_propuesta") if _obs_json(t).get("ok") is True]

def _horario_ofrecido(turnos, fecha, hora):
    """El horario propuesto tiene que estar en un bloque que buscar_horarios devolvió EN ESTA conversación (nunca inventado)."""
    for t in _llamadas(turnos, "buscar_horarios"):
        o = _obs_json(t)
        for of in (o.get("ofertas") or []):
            if str(of.get("fecha")) == str(fecha) and str(of.get("hora", ""))[:5] == str(hora)[:5]:
                return True
        bloque = str(o.get("bloque") or "")
        if fecha and bloque and _fecha_en_bloque(bloque, fecha, hora):
            return True
    return False

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
def _fecha_en_bloque(bloque, fecha, hora):
    try:
        y, m, d = str(fecha).split("-"); hh, mm = str(hora)[:5].split(":")
    except ValueError:
        return False
    linea = re.compile(rf"\b{int(d)} de {MESES[int(m) - 1]}\b[^\n]*\b{int(hh)}:{mm}\b", re.I)
    return bool(linea.search(bloque))

def juzgar(esc, turnos):
    """Devuelve (aprobado:bool, motivos:[str]) mirando solo resultados de herramientas y marcas del cerebro."""
    f = esc["funcion"]; motivos = []
    humano = _llamadas(turnos, "pasar_a_humano")
    humano_ok = [t for t in humano if _obs_json(t).get("ok") is True and not _obs_json(t).get("derivado_a_triaje")]
    bloqueos = [tu for tu in turnos if tu.get("motivo_chequeo") not in (None, "cierre_puro") or tu.get("motivo_banlist")]
    fallos = [tu for tu in turnos if tu.get("fallo_agente")]
    if bloqueos: motivos.append(f"{len(bloqueos)} bloqueo(s) del chequeo/banlist: {[(b.get('motivo_chequeo'), b.get('motivo_banlist')) for b in bloqueos]}")
    if fallos: motivos.append(f"{len(fallos)} fallo(s) del agente (timeout / maxIterations)")
    if f != "urgencia" and humano_ok: motivos.append("pasó a una persona sin que el escenario lo pida")

    if f in ("agendar", "reprogramar", "cancelar"):
        tipo = {"agendar": ("reserva", "sumar"), "reprogramar": ("cambio",), "cancelar": ("cancelacion",)}[f]
        props = [t for ti in tipo for t in _propuso(turnos, ti)]
        ej = _ejecuto_ok(turnos)
        if not props: motivos.append(f"nunca propuso ({'/'.join(tipo)}) con ok")
        if not ej: motivos.append("nunca ejecutó la propuesta con ok (en sombra: simulado:true)")
        for t in props:
            i = t.get("input") or {}
            if i.get("fecha") and not _horario_ofrecido(turnos, i.get("fecha"), i.get("hora")):
                motivos.append(f"propuso un horario que buscar_horarios no ofreció en esta conversación: {i.get('fecha')} {i.get('hora')}")
        # ejecutar en el MISMO turno que proponer = el paciente no vio el read-back
        for tu in turnos:
            nombres = [t.get("tool") for t in (tu.get("tools") or [])]
            if "proponer" in nombres and "ejecutar_propuesta" in nombres and any(_obs_json(t).get("ok") for t in tu["tools"] if t.get("tool") == "ejecutar_propuesta"):
                motivos.append("ejecutó en el mismo mensaje en que propuso")
        if esc["id"] == "DANA-06" and not _propuso(turnos, "sumar"): motivos.append("DANA-06 exige sumar (dos turnos), no cambiar")
    elif f == "confirmar":
        c = [t for t in _llamadas(turnos, "confirmar_turno") if _obs_json(t).get("ok") is True]
        if not c: motivos.append("nunca confirmó con ok")
        if esc["id"] == "CON-04" and len(c) < 2: motivos.append("CON-04 exige confirmar DOS turnos")
    elif f == "pagos":
        if not _llamadas(turnos, "registrar_pago"): motivos.append("no llamó registrar_pago")
        textos = " ".join((tu.get("asiri") or "") for tu in turnos).lower()
        if re.search(r"(pago|transferencia|comprobante)[^.]{0,40}(ingres|acredit|recib)", textos) and "verific" not in textos:
            motivos.append("afirma que el pago ingresó/se recibió sin dejarlo en manos de la secretaria")
    elif f == "urgencia":
        if not any(tu.get("derivar_triaje") for tu in turnos): motivos.append("la urgencia no fue derivada al triaje")
        if any(re.search(r"ac[eé]rquese|venga ahora|pase por|ahora mismo|tome |coloque|enju[aá]gue", (tu.get("asiri") or ""), re.I) for tu in turnos):
            motivos.append("invitó a ir o dio una indicación clínica")
    return (not motivos, motivos)


# ----------------------------------------------------------------------------- persona y objetivo del paciente simulado
def persona_de(esc, nombre_paciente):
    f = esc["funcion"]
    ejemplos = " / ".join(p["p"] for p in esc["pasos"][:3] if not p["p"].startswith("["))
    base = (f"Sos un paciente (o madre/padre de un paciente) de una clínica de ortodoncia en Jujuy, Argentina. Hablás por WhatsApp con la secretaria virtual. "
            f"Escribís como una persona real: corto, informal, a veces con faltas o sin signos de pregunta, a veces 'si' o 'dale' a secas. Nunca escribís más de 2 oraciones. "
            f"Tu nombre (o el del paciente de la familia) es {nombre_paciente}: si te preguntan para quién es el turno, o nombre o DNI, respondé con ese nombre. "
            f"Si te ofrecen horarios, elegí UNO de los que te ofrecieron (copiá día y hora tal cual). Si te leen una confirmación y te preguntan si proceden, respondé que sí. "
            f"Cuando tu objetivo esté cumplido (te confirmaron lo que querías) o ya no tenga sentido seguir, respondé SOLO con la palabra [FIN]. "
            f"No inventes datos que no tenés. Estilo de mensajes reales de este escenario, para que te inspires (no los copies): {ejemplos}")
    objetivos = {
        "agendar": "OBJETIVO: sacar un turno nuevo para una consulta de ortodoncia y que te lo dejen reservado.",
        "reprogramar": "OBJETIVO: tenés un turno ya reservado y NO podés ir; querés cambiarlo a otro día/horario y que te confirmen el cambio.",
        "cancelar": "OBJETIVO: tenés un turno reservado y querés cancelarlo (no reprogramar); si te ofrecen otro, decí que después ves.",
        "confirmar": "OBJETIVO: te llegó un recordatorio del turno; querés confirmar que vas. Nada más.",
        "pagos": "OBJETIVO: ya hiciste la transferencia de la seña y querés avisar/mandar el comprobante. No pedís nada más.",
        "urgencia": "OBJETIVO: empezaste pidiendo cambiar el turno pero en tu segundo mensaje contás que se te salió un alambre y te está pinchando mucho.",
    }
    extra = {
        "DANA-06": " Importante: NO querés cambiar tu turno actual, querés SUMAR otro turno además del que tenés.",
        "DANA-09": " En algún momento, antes de confirmar, preguntá cuánto sale la consulta.",
        "AGE-02": " Solo podés a las 17 hs; si no hay a esa hora, aceptá lo más cercano por la tarde.",
        "AGE-05": " Querés la semana que viene, cualquier día después de las 15 hs.",
        "AGE-07": " Ninguno de los horarios del primer bloque te sirve; pedí otros.",
        "CON-02": " Vos sos la mamá y confirmás por tu hijo.",
        "CON-06": " Tu primer mensaje es solo 'No podré asistir', sin pedir nada; si te preguntan si lo reprogramás, decí que sí y elegí uno.",
        "PAG-02": " No tenés el comprobante a mano todavía; solo avisás 'ya transferí'.",
    }.get(esc["id"], "")
    return base + "\n" + objetivos[f] + extra + "\nContexto: " + esc["exito"]


def primer_mensaje(esc):
    """El primer mensaje sale del caso real (es lo que un paciente de verdad escribió). Los adjuntos van como marcador de multimedia del v6."""
    return esc["pasos"][0]["p"]


def historial_inicial(esc, nombre_paciente):
    """Siembra el historial con lo que el bot ya le había mandado (recordatorio, bloque, pre-reserva), como filas de n8n_chat_histories (más nueva primero)."""
    textos = ESCENARIOS["bot_textos"]; filas = []
    for quien, clave in esc.get("inicio", []):
        txt = textos.get(clave) or ""
        if clave.startswith("RECORDATORIO"):
            txt = f"Estimado/a {nombre_paciente}, le recordamos su turno con la Dra. Rodríguez Raquel. Por favor confirme su asistencia respondiendo 'Confirmo'."
        filas.insert(0, {"message": {"type": "ai" if quien == "B" else "human", "content": txt, "additional_kwargs": {"source": "reminder_note" if clave.startswith("RECORDATORIO") else "wa_outbound"}}})
    return filas


# ----------------------------------------------------------------------------- transportes (reales y falsos)
class CerebroReal:
    def __init__(self):
        self.base = (env("N8N_API_BASE") or require("N8N_BASE_URL")).rstrip("/")
        self.ruta = (ROOT / "data" / "v7_test_ruta.txt").read_text(encoding="utf-8").strip()
    def _post(self, body):
        req = urllib.request.Request(f"{self.base}/webhook/{self.ruta}", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=170) as r:
                out = json.loads(r.read().decode()); return out[0] if isinstance(out, list) and out else out
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode()[:400]}"}
    def responder(self, phone, push, texto, historial):
        t0 = time.time()
        r = self._post({"destino": "cerebro", "phone": phone, "texto": texto, "pushName": push, "modo": "sombra", "historial_json": json.dumps(historial, ensure_ascii=False)})
        return r, time.time() - t0
    def reset(self, phone):
        return self._post({"destino": "reset", "tel": phone})
    def turnos_vigentes(self, phone):
        r = self._post({"destino": "ver_turnos", "tel": phone, "exec_id_actual": "examen-pre", "modo": "sombra"})
        return r.get("turnos") or [], r


class PacienteReal:
    def __init__(self, modelo=MODELO_PACIENTE):
        self.key = require("OPENAI_API_KEY"); self.modelo = modelo
    def siguiente(self, sistema, charla):
        msgs = [{"role": "system", "content": sistema}] + charla
        body = {"model": self.modelo, "messages": msgs, "max_completion_tokens": 120}
        req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()


class CerebroFalso:
    """Camino feliz determinístico para probar el EXAMEN (no el bot). Sabe qué función se evalúa (se la fija el examen antes de cada corrida)
    y hace lo que un v7 correcto haría: bloque → propuesta del tipo correcto → ejecución recién tras el 'sí'; confirmar / pago / triaje por frase."""
    BLOQUE = ESCENARIOS["bot_textos"]["SLOTS"]
    OFERTAS = [{"fecha": "2026-10-22", "hora": "08:00"}, {"fecha": "2026-10-22", "hora": "09:20"}, {"fecha": "2026-10-23", "hora": "09:10"}]
    def __init__(self): self.estado = {}; self.funcion = "agendar"; self.esc_id = ""
    def _tool(self, nombre, inp, obs): return {"tool": nombre, "input": inp, "obs": json.dumps(obs, ensure_ascii=False)}
    def responder(self, phone, push, texto, historial):
        e = self.estado.setdefault(phone, {"paso": 0}); t = texto.lower(); tools = []
        if re.search(r"alambre|pincha|duele|sangra", t):
            tools.append(self._tool("derivar_triaje", {"cita_textual": texto}, {"ok": True, "derivado_a_triaje": True}))
            return {"texto": None, "enviar": False, "silencio": True, "derivar_triaje": True, "tools": tools}, 0.3
        if self.funcion == "confirmar" and re.search(r"confirm|ah[ií] estaremos|vamos a ir", t):
            n = 2 if self.esc_id == "CON-04" else 1
            for k in range(n): tools.append(self._tool("confirmar_turno", {"fecha": ""}, {"ok": True, "readback_text": "Listo, confirmado."}))
            return {"texto": "Listo, su turno queda confirmado.", "enviar": True, "tools": tools}, 0.3
        if self.funcion == "pagos":
            tools.append(self._tool("registrar_pago", {}, {"ok": True}))
            return {"texto": "Dejé anotado su aviso; la secretaria lo verifica cuando llegue el comprobante.", "enviar": True, "tools": tools}, 0.3
        if re.match(r"^\s*(gracias|muchas gracias|listo|ok|dale)\W*$", t) and e["paso"] >= 3:
            return {"texto": None, "enviar": False, "silencio": True, "motivo_chequeo": "cierre_puro", "tools": []}, 0.1
        if e["paso"] == 0 or (e["paso"] == 1 and re.search(r"ningun|otro|no me sirve|m[aá]s adelante", t)):
            e["paso"] = 1
            tools.append(self._tool("buscar_horarios", {}, {"ok": True, "bloque": self.BLOQUE, "ofertas": self.OFERTAS}))
            return {"texto": self.BLOQUE, "enviar": True, "tools": tools}, 0.3
        if e["paso"] == 1:
            e["paso"] = 2
            tipo = {"agendar": "reserva", "reprogramar": "cambio", "cancelar": "cancelacion", "urgencia": "cambio"}.get(self.funcion, "reserva")
            if self.esc_id == "DANA-06": tipo = "sumar"
            rb = "Le confirmo: Jueves 22 de octubre a las 09:20 hs. ¿Procedo?"
            tools.append(self._tool("proponer", {"tipo": tipo, "fecha": "2026-10-22", "hora": "09:20"}, {"ok": True, "texto_para_el_paciente": rb}))
            return {"texto": rb, "enviar": True, "tools": tools}, 0.3
        if e["paso"] == 2 and re.match(r"^\s*(s[ií]|dale|ok|si por favor)\b", t):
            e["paso"] = 3
            tools.append(self._tool("ejecutar_propuesta", {}, {"ok": True, "simulado": True, "readback_text": "Listo, quedó."}))
            return {"texto": "Listo, quedó el jueves 22/10 a las 09:20.", "enviar": True, "tools": tools}, 0.3
        return {"texto": "¿Le sirve alguno de los horarios?", "enviar": True, "tools": []}, 0.2
    def reset(self, phone): self.estado.pop(phone, None); return {"reinicio": "ok"}
    def turnos_vigentes(self, phone): return ["viernes 16/10 a las 09:10"], {}


class PacienteFalso:
    """Sigue el guion real del escenario (pasos[].p); cuando se le acaba, contesta 'Sí' a un read-back pendiente y después [FIN]. Sin modelo."""
    def __init__(self, esc): self.pasos = [p["p"] for p in esc["pasos"]]; self.i = 1
    def siguiente(self, sistema, charla):
        if self.i < len(self.pasos): m = self.pasos[self.i]; self.i += 1; return m
        ultimo = charla[-1]["content"] if charla and charla[-1]["role"] == "user" else ""
        if "¿Procedo" in ultimo and not any(c["role"] == "assistant" and re.match(r"^\s*s[ií]\b", c["content"].lower()) for c in charla[-2:]): return "Sí"
        return "[FIN]"


# ----------------------------------------------------------------------------- una corrida
def correr_escenario(esc, cerebro, paciente, phone, push, nombre_paciente, verbose):
    sistema = persona_de(esc, nombre_paciente)
    historial = historial_inicial(esc, nombre_paciente)
    charla = []  # para el paciente simulado: él es 'assistant', Asiri es 'user'
    for fila in reversed(historial):
        charla.append({"role": "user" if fila["message"]["type"] == "ai" else "assistant", "content": fila["message"]["content"]})
    turnos = []; texto = primer_mensaje(esc)
    # Escenarios que arrancan "después del bloque de horarios": el bloque tiene que ser el REAL (así las ofertas quedan en Redis y el
    # chequeo de salida no frena un horario del fixture que hoy no existe). Se consigue con un pedido real previo, que cuenta como turno 0.
    if any(clave.startswith("SLOTS") for _, clave in esc.get("inicio", [])):
        r0, seg0 = cerebro.responder(phone, push, "Hola, quiero sacar un turno", historial)
        turnos.append({"turno": 0, "paciente": "Hola, quiero sacar un turno", "asiri": r0.get("texto"), "enviar": r0.get("enviar"), "silencio": r0.get("silencio"), "derivar_triaje": r0.get("derivar_triaje"),
                       "tools": r0.get("tools") or [], "motivo_chequeo": r0.get("motivo_chequeo"), "motivo_banlist": r0.get("motivo_banlist"), "fallo_agente": r0.get("fallo_agente"), "segundos": round(seg0, 1), "error": r0.get("error"), "preparacion": True})
        if verbose: print(f"    [0] (preparación) PACIENTE: Hola, quiero sacar un turno\n        ASIRI ({seg0:.1f} s): " + str(r0.get("texto") or "").replace("\n", "\n            "))
        historial = [f for f in historial if not str(f["message"]["content"]).startswith("Tenemos los próximos turnos")]   # fuera el bloque del fixture
        historial.insert(0, {"message": {"type": "human", "content": "Hola, quiero sacar un turno", "additional_kwargs": {"source": "wa_inbound"}}})
        if r0.get("enviar") and r0.get("texto"): historial.insert(0, {"message": {"type": "ai", "content": r0["texto"], "additional_kwargs": {"source": "wa_outbound"}}})
        charla = [{"role": "assistant", "content": "Hola, quiero sacar un turno"}] + ([{"role": "user", "content": r0["texto"]}] if r0.get("enviar") and r0.get("texto") else [])
    for n in range(1, MAX_TURNOS + 1):
        r, seg = cerebro.responder(phone, push, texto, historial)
        tu = {"turno": n, "paciente": texto, "asiri": r.get("texto"), "enviar": r.get("enviar"), "silencio": r.get("silencio"), "derivar_triaje": r.get("derivar_triaje"),
              "tools": r.get("tools") or [], "motivo_chequeo": r.get("motivo_chequeo"), "motivo_banlist": r.get("motivo_banlist"), "fallo_agente": r.get("fallo_agente"), "segundos": round(seg, 1), "error": r.get("error")}
        turnos.append(tu)
        if verbose:
            print(f"    [{n}] PACIENTE: {texto}")
            if tu["error"]: print(f"        ERROR: {tu['error']}")
            else:
                print(f"        ASIRI ({seg:.1f} s): " + (tu["asiri"] if tu["enviar"] else ("→ TRIAJE" if tu["derivar_triaje"] else "(silencio)")).replace("\n", "\n            "))
                for t in tu["tools"]: print(f"          · {t.get('tool')}({json.dumps(t.get('input'), ensure_ascii=False)[:90]})")
                if tu["motivo_chequeo"] not in (None, "cierre_puro") or tu["motivo_banlist"] or tu["fallo_agente"]:
                    print(f"          ! chequeo={tu['motivo_chequeo']} banlist={tu['motivo_banlist']} fallo={tu['fallo_agente']}")
        if tu["error"] or tu["derivar_triaje"]: break
        historial.insert(0, {"message": {"type": "human", "content": texto, "additional_kwargs": {"source": "wa_inbound"}}})
        charla.append({"role": "assistant", "content": texto})
        if tu["enviar"] and tu["asiri"]:
            historial.insert(0, {"message": {"type": "ai", "content": tu["asiri"], "additional_kwargs": {"source": "wa_outbound"}}})
            charla.append({"role": "user", "content": tu["asiri"]})
        elif tu["silencio"]:
            break  # Asiri calló (cierre): la conversación terminó
        texto = paciente.siguiente(sistema, charla).strip()
        if not texto or texto.upper().startswith("[FIN]"): break
    return turnos


def necesita_turno(esc):
    return esc["funcion"] in ("reprogramar", "cancelar", "confirmar") or esc["id"] in ("DANA-06", "DANA-10", "AGE-06")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true"); ap.add_argument("--guion", action="store_true", help="cerebro real, paciente de guion (sin modelo)"); ap.add_argument("--todos", action="store_true"); ap.add_argument("--solo", nargs="*", default=[])
    ap.add_argument("--reps", type=int, default=1); ap.add_argument("--phone", default=PHONE_PRUEBA); ap.add_argument("--push", default="Lucas Test")
    ap.add_argument("--nombre", default="Lucas", help="nombre de la ficha de prueba que el paciente simulado dice cuando le preguntan"); ap.add_argument("-q", action="store_true")
    a = ap.parse_args()
    escs = [e for e in ESCENARIOS["escenarios"] if a.todos or e["id"] in a.solo or (a.offline and not a.solo)]
    if not escs: sys.exit("elegí --todos, --solo <ids> o --offline")
    cerebro = CerebroFalso() if a.offline else CerebroReal()
    vigentes, _ = cerebro.turnos_vigentes(a.phone)
    hay_turno = len(vigentes) > 0
    print(f"EXAMEN v7 · {'OFFLINE (cerebro y paciente falsos)' if a.offline else ('SOMBRA contra n8n real, paciente de GUION (humo)' if a.guion else 'SOMBRA contra n8n real, paciente SIMULADO')} · celular {a.phone} · turnos vigentes de prueba: {vigentes or 'NINGUNO'} · {len(escs)} escenarios × {a.reps}")
    resultados = []
    try:
        for esc in escs:
            if necesita_turno(esc) and not hay_turno:
                print(f"\n== {esc['id']} ({esc['funcion']}): NO EVALUABLE, la ficha de prueba no tiene turno vigente (crear una cita de prueba en Dentalink)")
                resultados.append({"id": esc["id"], "funcion": esc["funcion"], "estado": "no_evaluable", "motivo": "sin turno vigente de prueba", "reps": []}); continue
            print(f"\n== {esc['id']} ({esc['funcion']}) · éxito esperado: {esc['exito']}")
            reps = []
            for k in range(1, a.reps + 1):
                cerebro.reset(a.phone)
                if a.offline: cerebro.funcion, cerebro.esc_id = esc["funcion"], esc["id"]
                paciente = PacienteFalso(esc) if (a.offline or a.guion) else PacienteReal()
                if a.reps > 1: print(f"  -- repetición {k}")
                turnos = correr_escenario(esc, cerebro, paciente, a.phone, a.push, a.nombre, verbose=not a.q)
                ok, motivos = juzgar(esc, turnos)
                lat = [t["segundos"] for t in turnos]
                reps.append({"ok": ok, "motivos": motivos, "mensajes": len(turnos), "latencias": lat, "turnos": turnos})
                print(f"  {'APROBADO' if ok else 'REPROBADO'} · {len(turnos)} mensajes · máx {max(lat) if lat else 0:.1f} s" + ("" if ok else f" · {motivos}"))
            resultados.append({"id": esc["id"], "funcion": esc["funcion"], "estado": "evaluado", "reps": reps})
    finally:
        cerebro.reset(a.phone)   # teardown SIEMPRE (regla 9)
    # ---- resumen
    ev = [r for r in resultados if r["estado"] == "evaluado"]; ne = [r for r in resultados if r["estado"] != "evaluado"]
    aprob = sum(1 for r in ev if all(x["ok"] for x in r["reps"])); inest = [r["id"] for r in ev if any(x["ok"] for x in r["reps"]) and not all(x["ok"] for x in r["reps"])]
    lats = [s for r in ev for x in r["reps"] for s in x["latencias"]]
    p95 = statistics.quantiles(lats, n=20)[18] if len(lats) >= 20 else (max(lats) if lats else 0)
    print(f"\n==== RESUMEN: {aprob}/{len(ev)} escenarios aprobados en TODAS las repeticiones · inestables: {inest or 'ninguno'} · no evaluables: {[r['id'] for r in ne] or 'ninguno'}")
    print(f"     latencia por mensaje: p50 {statistics.median(lats) if lats else 0:.1f} s · p95 {p95:.1f} s (objetivo < {OBJETIVO_LAT_P95:.0f} s) · mensajes promedio {statistics.mean([x['mensajes'] for r in ev for x in r['reps']]) if ev else 0:.1f}")
    for r in ev:
        for x in r["reps"]:
            if not x["ok"]: print(f"     {r['id']}: {x['motivos']}")
    SALIDA.write_text(json.dumps({"phone": a.phone, "offline": a.offline, "reps": a.reps, "resultados": resultados}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"     detalle: {SALIDA.relative_to(ROOT)}")
    sys.exit(0 if aprob == len(ev) and not inest else 1)


if __name__ == "__main__":
    main()
