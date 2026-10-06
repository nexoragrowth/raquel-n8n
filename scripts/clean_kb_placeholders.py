# -*- coding: utf-8 -*-
"""
clean_kb_placeholders.py — Sanea la base de conocimiento en Supabase v3:
1. Elimina 'ASIRI' como si fuera marca médica de alineadores (ID 29).
2. Pone límite razonable a la reserva anticipada (30 a 60 días) y purga Dentalink (ID 2).
3. Elimina menciones operativas a 'puntos de colores flúor' de la agenda y Dentalink (ID 1 e ID 4).
4. Pasa ID 12 (comando interno /bot off) a una redacción institucional limpia que no confunda si el RAG la lee.
5. Re-genera los embeddings OpenAI (text-embedding-3-small, 1536 dims) para las filas modificadas.
6. Crea backup en archivo JSON antes de actualizar.

USO:
    python scripts/clean_kb_placeholders.py           # Simulación (diff claro)
    python scripts/clean_kb_placeholders.py --apply   # Aplica en Supabase + re-vectoriza
"""
import argparse, json, sys, time, urllib.request, psycopg2
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env

ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT / "workflows" / "history"

# Nuevos contenidos saneados
SANEAMIENTO = {
    1: {
        "titulo": "Política de pago anticipado por tipo de turno",
        "contenido": (
            "Solo los turnos de PRIMERA CONSULTA requieren pago anticipado ($50.000). "
            "Cuando el paciente confirma la fecha y horario, se le informan los datos bancarios para reservar. "
            "Si no abona de inmediato, igualmente se agenda el turno de manera provisoria, pero junto al recordatorio "
            "(48 hs hábiles previas) se le solicita el envío del comprobante para confirmar su asistencia. "
            "Otros tipos de turno (controles mensuales de ortodoncia, control de contención) NO requieren pago anticipado "
            "y se abonan el día de la atención."
        )
    },
    2: {
        "titulo": "Plazo de reserva de turnos",
        "contenido": (
            "Se pueden agendar turnos dentro de las próximas semanas disponibles en la agenda de la clínica "
            "(habitualmente con hasta 30 a 60 días de anticipación). Los horarios exactos se ofrecen al momento "
            "de coordinar la cita según la disponibilidad de sillón y agenda de la Dra. Raquel."
        )
    },
    4: {
        "titulo": "Tipos de turnos en la clínica",
        "contenido": (
            "Tipos de turnos disponibles en el consultorio:\n"
            "- PRIMERA CONSULTA: evaluación clínica, fotos de diagnóstico e indicación de estudios.\n"
            "- CONTROL DE TRATAMIENTO: 30 a 40 minutos para ajuste de aparatología o seguimiento de alineadores.\n"
            "- CONTROL DE CONTENCIÓN: 30 minutos para pacientes que ya finalizaron su tratamiento de ortodoncia.\n"
            "- ATENCIÓN POR MOLESTIAS/URGENCIAS: se coordina previa evaluación del caso con la doctora o secretaria."
        )
    },
    12: {
        "titulo": "Control interno de atención por secretaria",
        "contenido": (
            "Cuando la secretaria o la doctora toman la conversación desde su teléfono o desde el panel de control, "
            "el asistente virtual pasa a modo silencioso para que la atención continúe de forma directa y personalizada "
            "por el equipo de la clínica, sin interrumpir al paciente."
        )
    },
    29: {
        "titulo": "Tratamiento con alineadores transparentes",
        "contenido": (
            "La Dra. Raquel Rodríguez es especialista en ortodoncia y está certificada para trabajar con los principales "
            "sistemas de alineadores transparentes del mercado, como Invisalign, Keep Smiling y Angel Aligner, entre otros. "
            "El tratamiento y su duración se definen de manera individual luego de realizar el diagnóstico y la planificación digital "
            "personalizada en la cita de devolución."
        )
    }
}

def get_openai_key():
    env_local = ROOT.parent / "nexora-whatsapp-agent" / ".env.local"
    if env_local.exists():
        for line in env_local.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return env("OPENAI_API_KEY")

def get_embedding(text, key):
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps({"model": "text-embedding-3-small", "dimensions": 1536, "input": text}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())["data"][0]["embedding"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Aplica los cambios en Supabase y re-vectoriza")
    args = ap.parse_args()

    host = env("SUPABASE_V3_DB_HOST")
    port = env("SUPABASE_V3_DB_PORT")
    db = env("SUPABASE_V3_DB_NAME")
    user = env("SUPABASE_V3_DB_USER")
    pwd = env("SUPABASE_V3_DB_PASSWORD")

    conn = psycopg2.connect(host=host, port=port, dbname=db, user=user, password=pwd, sslmode="require")
    conn.autocommit = True
    cur = conn.cursor()

    cur.execute("SELECT id, categoria, titulo, contenido FROM knowledge_base WHERE id IN %s ORDER BY id;", (tuple(SANEAMIENTO.keys()),))
    current_rows = {r[0]: {"categoria": r[1], "titulo": r[2], "contenido": r[3]} for r in cur.fetchall()}

    print("==================================================================")
    print(" 🏥 SANEAMIENTO DE BASE DE CONOCIMIENTO (SUPABASE V3)")
    print("==================================================================\n")

    for kb_id, nuevo in SANEAMIENTO.items():
        viejo = current_rows.get(kb_id)
        if not viejo:
            print(f"⚠️ ID {kb_id} no encontrado en la base de datos.")
            continue
        print(f"── [ID {kb_id}] {viejo['titulo']} ──")
        print("  [ANTES]:")
        print(f"    {viejo['contenido'][:140]}...")
        print("  [DESPUÉS]:")
        print(f"    {nuevo['contenido'][:140]}...\n")

    if not args.apply:
        print("🔍 [MODO SIMULACIÓN] No se realizaron cambios en la base de datos.")
        print("Para aplicar los cambios y regenerar los embeddings OpenAI, ejecuta:")
        print("  python scripts/clean_kb_placeholders.py --apply\n")
        cur.close()
        conn.close()
        return

    openai_key = get_openai_key()
    if not openai_key:
        sys.exit("❌ ERROR: No se encontró OPENAI_API_KEY en ../nexora-whatsapp-agent/.env.local ni en .env")

    # 1. Crear backup en archivo JSON
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    cur.execute("SELECT id, categoria, titulo, contenido FROM knowledge_base ORDER BY id;")
    full_backup = [{"id": r[0], "categoria": r[1], "titulo": r[2], "contenido": r[3]} for r in cur.fetchall()]
    backup_file = BACKUP_DIR / f"knowledge_base_PRE_saneamiento_{int(time.time())}.json"
    backup_file.write_text(json.dumps(full_backup, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"💾 Backup de seguridad guardado en: workflows/history/{backup_file.name}")

    # 2. Aplicar updates y re-vectorizar
    print("\n🚀 Aplicando cambios y re-generando vectores en OpenAI...")
    for kb_id, nuevo in SANEAMIENTO.items():
        cat = current_rows[kb_id]["categoria"]
        tit = nuevo["titulo"]
        cont = nuevo["contenido"]

        text_to_embed = f"{cat} | {tit}\n{cont}"
        vec = get_embedding(text_to_embed, openai_key)
        vec_str = "[" + ",".join(map(str, vec)) + "]"

        cur.execute("""
            UPDATE knowledge_base
            SET titulo = %s, contenido = %s, embedding = %s::vector
            WHERE id = %s;
        """, (tit, cont, vec_str, kb_id))
        print(f"  ✅ [ID {kb_id}] Actualizado y vectorizado con éxito ({tit})")

    print("\n🎉 Saneamiento completado exitosamente.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
