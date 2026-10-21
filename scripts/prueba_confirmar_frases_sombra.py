# -*- coding: utf-8 -*-
"""
prueba_confirmar_frases_sombra.py — 2026-10-21 · batería de COMPORTAMIENTO del v7 (cerebro real, modelos reales, MODO SOMBRA: no escribe en la agenda,
no guarda memoria, no avisa al grupo) para la respuesta a recordatorios: un celular con DOS recordatorios el mismo día responde con frases reales.
Regla de Lucas (21/10): cualquier forma de "sí" confirma TODO; solo se limita si dice explícitamente que confirma uno solo o que otro no va.

Siembra 2 filas en recordatorios_enviados para el número de prueba de Lucas (tipo 'prueba-confirmar', citas reales pasadas por argumento solo para
el GET de verificación), pasa los recordatorios como historial, corre cada frase por el webhook de prueba (siempre sombra) y BORRA lo sembrado.

USO:  python scripts/prueba_confirmar_frases_sombra.py --citas 9116 9120
"""
import argparse, datetime as dt, json, subprocess, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_migracion_contacto_tipos import conectar
from migrar_dentalink import leer_token

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
TEL = "5491161461034"
TIPO = "prueba-confirmar"
NOMBRES = ["Pedro Gómez", "Hilario Gómez"]
# (frase, qué tiene que pasar): "todos" = confirma los dos; "uno:<nombre>" = solo ese
FRASES = [
    ("Confirmo", "todos"),
    ("hola siii vamos a ir con martin", "todos"),
    ("Si, ahí estaremos", "todos"),
    ("dale gracias 👍", "todos"),
    ("Pedro 9:50 e Hilario 10:30", "todos"),
    ("si vamos los dos", "todos"),
    ("Buen día. Confirmamos asistencia", "todos"),
    ("confirmo solo el de Pedro", "uno:Pedro"),
]


def cita(cid, tok):
    with urllib.request.urlopen(urllib.request.Request(f"https://api.dentalink.healthatom.com/api/v1/citas/{cid}", headers={"Authorization": "Token " + tok}), timeout=20) as r:
        return json.loads(r.read().decode()).get("data") or {}


def probar(*args):
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "probar_v7.py"), *args], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    return p.stdout + p.stderr


def a_json(out):
    i = out.find("{")
    try:
        return json.loads(out[i:]) if i >= 0 else {}
    except Exception:
        return {"_crudo": out[-400:]}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--citas", nargs=2, type=int, required=True); a = ap.parse_args()
    tok = leer_token()
    cs = [cita(c, tok) for c in a.citas]
    if not all(c.get("id") for c in cs): sys.exit("No encontré las dos citas en Dentalink.")
    hace = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
    hist = [{"message": {"type": "ai", "content": f"✨ ÁUREA ODONTOLOGÍA ESTÉTICA ✨\n\nEstimado/a {NOMBRES[i]}, le recordamos su turno con la Dra. Rodríguez Raquel:\n📅 viernes 23 de octubre\n🕔 {str(d['hora_inicio'])[:5]} hs\nPara confirmar su asistencia responda CONFIRMO.",
                         "additional_kwargs": {"source": "reminder_note"}}, "created_at": hace} for i, d in enumerate(cs)]
    c = conectar(solo_lectura=False); cur = c.cursor()
    sembradas, resultados = [], []
    try:
        for i, d in enumerate(cs):
            cur.execute("""INSERT INTO recordatorios_enviados (telefono, id_cita_dentalink, id_paciente_dentalink, nombre_paciente, fecha_turno, hora_turno, tipo, enviado_at)
                           VALUES (%s, %s, NULL, %s, %s, %s, %s, now() - interval '1 hour') RETURNING id""", (TEL, d["id"], NOMBRES[i], d["fecha"], d["hora_inicio"], TIPO))
            sembradas.append(cur.fetchone()[0])
        c.commit()
        print(probar("--activar").strip().splitlines()[-1])
        for k, (frase, esperado) in enumerate(FRASES):
            out = a_json(probar("--destino", "cerebro", "--campo", f"phone={TEL}", "--campo", f"texto={frase}", "--campo", "modo=sombra",
                                "--campo", "historial_json=" + json.dumps(hist, ensure_ascii=False)))
            tools = out.get("tools") or []
            conf = [t for t in tools if t.get("tool") == "confirmar_turno"]
            entradas = [t.get("input") for t in conf]
            texto = (out.get("texto") or "").replace("\n", " / ")
            # Se evalúa por la RESPUESTA (la traza de las herramientas viene recortada a 400 caracteres).
            limpio = "?" not in texto and "Tenemos los próximos" not in texto
            if esperado == "todos":
                ok = "quedaron confirmados" in texto and "Pedro" in texto and "Hilario" in texto and limpio
            else:
                ok = "09:50 está confirmado" in texto and "10:30" not in texto and limpio
            resultados.append(ok)
            print(f"\n[{'OK ' if ok else 'MAL'}] «{frase}» (espera {esperado})\n   confirmar_turno: {len(conf)} llamada(s) {entradas}\n   respuesta: {texto[:260]}")
    finally:
        print("\n" + probar("--desactivar").strip().splitlines()[-1])
        if sembradas:
            cur.execute("DELETE FROM recordatorios_enviados WHERE id = ANY(%s) AND tipo = %s", (sembradas, TIPO)); c.commit()
            print(f"limpieza: {cur.rowcount} filas sembradas borradas")
        cur.execute("SELECT count(*) FROM recordatorios_enviados WHERE tipo = %s", (TIPO,)); print("filas de prueba que quedan:", cur.fetchone()[0])
        c.close()
    print(f"\nRESULTADO: {sum(resultados)}/{len(FRASES)} frases como se espera")
    sys.exit(0 if all(resultados) else 1)


if __name__ == "__main__":
    main()
