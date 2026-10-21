# -*- coding: utf-8 -*-
"""
prueba_confirmar_familia_sombra.py — 2026-10-21 · prueba de punta a punta EN PRODUCCIÓN (modo sombra: verifica contra Dentalink, no escribe) del caso
del incidente del 21/10: un celular con DOS recordatorios abiertos el MISMO día que responde "Confirmo" → tienen que confirmarse los dos en un solo
mensaje (antes: "¿Cuál de estos turnos confirma?" en bucle).

Cómo: siembra 2 filas en recordatorios_enviados para el celular SINTÉTICO del arnés (5490000000651, tipo 'prueba-confirmar') apuntando a dos citas
reales que se pasan por argumento (se usan solo para el GET de verificación; en sombra no hay PUT ni se marca nada), llama a la herramienta
confirmar_turno por el webhook de prueba del v7 (siempre sombra) y BORRA las filas sembradas pase lo que pase (regla 9).

USO:  python scripts/prueba_confirmar_familia_sombra.py --citas 9116 9120
"""
import argparse, json, subprocess, sys, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_migracion_contacto_tipos import conectar
from migrar_dentalink import leer_token

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
TEL = "5490000000651"
TIPO = "prueba-confirmar"


def cita(cid, tok):
    with urllib.request.urlopen(urllib.request.Request(f"https://api.dentalink.healthatom.com/api/v1/citas/{cid}", headers={"Authorization": "Token " + tok}), timeout=20) as r:
        return json.loads(r.read().decode()).get("data") or {}


def probar(*args):
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "probar_v7.py"), *args], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    return p.stdout + p.stderr


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--citas", nargs=2, type=int, required=True); a = ap.parse_args()
    tok = leer_token()
    cs = [cita(c, tok) for c in a.citas]
    if not all(c.get("id") for c in cs): sys.exit("No encontré las dos citas en Dentalink.")
    c = conectar(solo_lectura=False); cur = c.cursor()
    sembradas = []
    try:
        for i, d in enumerate(cs):
            cur.execute("""INSERT INTO recordatorios_enviados (telefono, id_cita_dentalink, id_paciente_dentalink, nombre_paciente, fecha_turno, hora_turno, tipo, enviado_at)
                           VALUES (%s, %s, NULL, %s, %s, %s, %s, now()) RETURNING id""", (TEL, d["id"], ["Prueba Uno", "Prueba Dos"][i], d["fecha"], d["hora_inicio"], TIPO))
            sembradas.append(cur.fetchone()[0])
        c.commit()
        print(f"sembradas {len(sembradas)} filas de prueba para {TEL} (citas {a.citas}, {cs[0]['fecha']})")
        print(probar("--activar").strip().splitlines()[-1])
        out = probar("--destino", "confirmar_turno", "--campo", f"tel={TEL}", "--campo", "exec_id_actual=prueba-familia")
        print(out.strip())
    finally:
        print(probar("--desactivar").strip().splitlines()[-1])
        if sembradas:
            cur.execute("DELETE FROM recordatorios_enviados WHERE id = ANY(%s) AND tipo = %s", (sembradas, TIPO)); c.commit()
            print(f"limpieza: {cur.rowcount} filas sembradas borradas")
        cur.execute("SELECT count(*) FROM recordatorios_enviados WHERE telefono = %s", (TEL,)); print("quedan para el celular de prueba:", cur.fetchone()[0])
        c.close()


if __name__ == "__main__":
    main()
