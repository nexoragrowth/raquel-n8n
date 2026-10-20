# -*- coding: utf-8 -*-
"""
escenarios_reales_v7.py — v7 · el examen con CONVERSACIONES REALES (opción B, 07/10).
El examen normal tiene un paciente simulado que escribe prolijo. Acá cada escenario sale de una charla real de los últimos 90 días: qué quería el paciente,
qué cuenta como resuelto y cómo escribe (con sus faltas y mensajes cortados). El paciente simulado imita ese estilo y Asiri lo atiende en SOMBRA con la
ficha de prueba (o con el celular sintético sin ficha si era un paciente nuevo). Nada se escribe en la agenda ni se le manda nada a nadie.

PRIVACIDAD: las conversaciones reales se leen de Supabase (solo lectura) y lo que se guarda va a data/ (fuera del repo). Los ejemplos de estilo se reescriben
con nombres, DNI y teléfonos cambiados; el objetivo se escribe en abstracto.

USO:
  python tests/escenarios_reales_v7.py --armar --n 16          # elige y resume charlas reales → data/escenarios_reales.json
  python tests/escenarios_reales_v7.py --correr                # corre todos en sombra → data/escenarios_reales_resultados.json
  python tests/escenarios_reales_v7.py --correr --ids REAL-03 REAL-07 --reps 2
"""
import argparse, json, random, re, sys, urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests")); sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")
from examen_v7 import CerebroReal, PacienteReal, PHONE_PRUEBA, PHONE_NUEVO, correr_escenario, juzgar  # noqa: E402
from retrospectiva_v7 import conectar  # noqa: E402
from probar_v7 import require  # noqa: E402

DATA = ROOT / "data"; ESCENARIOS = DATA / "escenarios_reales.json"; RESULTADOS = DATA / "escenarios_reales_resultados.json"
EXCLUIR = ("1161461034", "3885786946", "3513976787", "9990000123", "0000000651")   # Lucas, Irina, la Dra., celulares de prueba
FUNCIONES = ("agendar", "reprogramar", "cancelar", "confirmar", "pagos", "urgencia", "consulta")
MODELO = "gpt-5-mini"

RESUMIR = """Te paso una conversación REAL de WhatsApp entre un paciente (o su familia) y una clínica de ortodoncia de Jujuy. Devolvé SOLO un JSON con:
- "descartar": true si no sirve para probar al bot (spam, proveedor, solo audios/fotos sin texto, solo un saludo, mensaje del personal) — si es true, el resto puede ir vacío.
- "funcion": una de agendar | reprogramar | cancelar | confirmar | pagos | urgencia | consulta (lo PRINCIPAL que quería; consulta = preguntas de precio, horarios, tratamientos, etc.).
- "objetivo": en segunda persona y en abstracto, qué querías lograr, sin fechas ni nombres reales. Ej.: "OBJETIVO: tenés un turno y querés pasarlo a otro día por la tarde; si te ofrecen horarios elegí uno de la tarde."
- "exito": en una frase, qué cuenta como resuelto para vos.
- "nuevo": true si parece un paciente que nunca fue (pide su primera consulta y no menciona un turno que ya tenga).
- "primer_mensaje": tu PRIMER mensaje, reescrito con la MISMA forma (faltas, abreviaturas, mayúsculas, emojis) pero con nombres, DNI, teléfonos y direcciones cambiados por otros inventados y sin fechas concretas si las hay (usá "el jueves", "la semana que viene").
- "estilo": hasta 3 mensajes más tuyos de esa charla, reescritos igual (misma forma, datos cambiados).
CONVERSACIÓN (lo más viejo arriba):
"""


def charlas_reales(dias=90):
    cur = conectar().cursor()
    cur.execute("SELECT session_id, created_at, message FROM n8n_chat_histories WHERE created_at > now() - %s * interval '1 day' ORDER BY session_id, id", (dias,))
    por = defaultdict(list)
    for s, t, m in cur.fetchall():
        if any(x in str(s) for x in EXCLUIR): continue
        if isinstance(m, str):
            try: m = json.loads(m)
            except Exception: continue
        por[s].append((t, m))
    out = []
    for sesion, filas in por.items():
        actual, ultimo = [], None
        for t, m in filas:
            if ultimo is not None and (t - ultimo).total_seconds() > 12 * 3600 and actual:
                out.append((sesion, actual)); actual = []
            actual.append((t, m)); ultimo = t
        if actual: out.append((sesion, actual))
    utiles = []
    for sesion, filas in out:
        humanos = [str(m.get("content") or "").strip() for _, m in filas if m.get("type") == "human" and str(m.get("content") or "").strip() and not str(m.get("content")).startswith("[")]
        if len(humanos) >= 2:
            utiles.append({"sesion": sesion, "fecha": str(filas[0][0])[:10], "filas": filas})
    return utiles


def texto_charla(filas):
    lineas = []
    for _, m in filas[:24]:
        c = str(m.get("content") or "").strip().replace("\n", " ")
        if not c or c.startswith("[NOTA INTERNA"): continue
        quien = "PACIENTE" if m.get("type") == "human" else ("PERSONAL" if c.startswith("[ATENCION HUMANA") else "BOT")
        lineas.append(f"{quien}: {c[:300]}")
    return "\n".join(lineas)


def llm(prompt):
    body = {"model": MODELO, "messages": [{"role": "user", "content": prompt}], "max_completion_tokens": 2500, "reasoning_effort": "low", "response_format": {"type": "json_object"}}
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {require('OPENAI_API_KEY')}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(json.loads(r.read().decode())["choices"][0]["message"]["content"] or "{}")


def armar(n, semilla):
    charlas = charlas_reales()
    rnd = random.Random(semilla); rnd.shuffle(charlas)
    print(f"Charlas reales con 2+ mensajes de texto del paciente (90 días, sin celulares de prueba): {len(charlas)}")
    por_funcion, elegidos = defaultdict(int), []
    tope = max(2, n // 5)                                       # variedad: pocas de cada función
    for c in charlas:
        if len(elegidos) >= n: break
        try: r = llm(RESUMIR + texto_charla(c["filas"]))
        except Exception as e: print("  (resumen falló)", str(e)[:80]); continue
        if r.get("descartar") or r.get("funcion") not in FUNCIONES or not r.get("primer_mensaje"): continue
        if por_funcion[r["funcion"]] >= tope: continue
        por_funcion[r["funcion"]] += 1
        k = len(elegidos) + 1
        esc = {"id": f"REAL-{k:02d}", "origen": f"REAL: charla del {c['fecha']} (reescrita)", "funcion": r["funcion"], "objetivo_real": str(r.get("objetivo") or ""),
               "exito": str(r.get("exito") or ""), "nuevo": bool(r.get("nuevo")) and r["funcion"] == "agendar",
               "inicio": [["B", "RECORDATORIO"]] if r["funcion"] == "confirmar" else [],
               "pasos": [{"p": str(r["primer_mensaje"])}] + [{"p": str(x)} for x in (r.get("estilo") or [])[:3]]}
        elegidos.append(esc)
        print(f"  {esc['id']} {esc['funcion']:11} {'(nuevo) ' if esc['nuevo'] else ''}«{esc['pasos'][0]['p'][:70]}»")
    DATA.mkdir(exist_ok=True)
    ESCENARIOS.write_text(json.dumps({"escenarios": elegidos}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(elegidos)} escenarios → {ESCENARIOS.relative_to(ROOT)} (fuera del repo) · por función: {dict(por_funcion)}")


def correr(ids, reps):
    escs = json.loads(ESCENARIOS.read_text(encoding="utf-8"))["escenarios"]
    if ids: escs = [e for e in escs if e["id"] in ids]
    cerebro = CerebroReal("cerebro"); vigentes, _ = cerebro.turnos_vigentes(PHONE_PRUEBA)
    import examen_v7; examen_v7.TURNO_PRUEBA = re.sub(r"\s*\([^)]*\)\s*$", "", vigentes[0]) if vigentes else ""   # el recordatorio del historial coincide con la agenda
    print(f"ESCENARIOS REALES v7 · sombra · {len(escs)} escenarios × {reps} · turnos de prueba: {vigentes}")
    resultados = []
    try:
        for esc in escs:
            print(f"\n== {esc['id']} ({esc['funcion']}) · {esc['objetivo_real'][:110]}")
            phone, push, nombre = (PHONE_NUEVO, "Sofía", "Sofía Prueba (DNI 40999888)") if esc.get("nuevo") else (PHONE_PRUEBA, "Lucas Test", "Lucas")
            reps_out = []
            for k in range(1, reps + 1):
                cerebro.reset(phone)
                turnos = correr_escenario(esc, cerebro, PacienteReal(), phone, push, nombre, verbose=True)
                ok, motivos = juzgar(esc, turnos)
                if any(t.get("error") for t in turnos): ok, motivos = False, motivos + ["error de red o del webhook"]
                lat = [t["segundos"] for t in turnos]
                reps_out.append({"ok": ok, "motivos": motivos, "mensajes": len(turnos), "latencias": lat, "turnos": turnos})
                print(f"  {'APROBADO' if ok else 'REPROBADO'} · {len(turnos)} mensajes" + ("" if ok else f" · {motivos}"))
            resultados.append({"id": esc["id"], "funcion": esc["funcion"], "estado": "evaluado", "reps": reps_out})
    finally:
        cerebro.reset(PHONE_PRUEBA); cerebro.reset(PHONE_NUEVO)
    RESULTADOS.write_text(json.dumps({"resultados": resultados, "escenarios": escs}, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in resultados if all(x["ok"] for x in r["reps"]))
    print(f"\n==== {ok}/{len(resultados)} aprobados (chequeos automáticos; el juicio fino es leyendo las charlas) · detalle: {RESULTADOS.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--armar", action="store_true"); ap.add_argument("--correr", action="store_true")
    ap.add_argument("--n", type=int, default=16); ap.add_argument("--semilla", type=int, default=11)
    ap.add_argument("--ids", nargs="*", default=[]); ap.add_argument("--reps", type=int, default=1)
    a = ap.parse_args()
    if a.armar: armar(a.n, a.semilla)
    if a.correr: correr(a.ids, a.reps)
    if not (a.armar or a.correr): ap.print_help()


if __name__ == "__main__":
    main()
