# -*- coding: utf-8 -*-
"""
insert_kb_huecos.py — Inserta las 4 respuestas blindadas que cubren los huecos de tratamientos
en knowledge_base (Supabase) y genera sus embeddings OpenAI (text-embedding-3-small, 1536 dims).

HUECOS CUBIERTOS:
1. Blanqueamiento dental y limpiezas generales (foco exclusivo ortodoncia/estética + consulta $50k)
2. Duración estimada de los tratamientos (12 a 24 meses orientativo + diagnóstico formal $50k)
3. Radiografías y estudios previos (no obligatorio traer, orden médica entregada en consulta)
4. Pacientes con brackets previos de otro profesional (evaluación obligatoria $50k)
"""
import json, sys, urllib.request, psycopg2
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env
def get_openai_key():
    env_local = Path(__file__).resolve().parent.parent.parent / "nexora-whatsapp-agent" / ".env.local"
    if env_local.exists():
        for line in env_local.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("OPENAI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None

KEY = get_openai_key()
if not KEY:
    sys.exit("ERROR: No se encontró OPENAI_API_KEY en ../nexora-whatsapp-agent/.env.local")

NUEVOS_HUECOS = [
    {
        "categoria": "tratamientos",
        "titulo": "Blanqueamiento dental y limpiezas generales",
        "contenido": "La Dra. Raquel Rodríguez se especializa de manera exclusiva en Ortodoncia y Ortopedia Facial (brackets y alineadores transparentes). En la primera consulta de valoración ($50.000) se evalúa la alineación, mordida y estética integral de tu sonrisa para planificar el tratamiento indicado. No realizamos odontología general (limpiezas o extracciones comunes), pero podemos coordinar la consulta de diagnóstico ortodóncico."
    },
    {
        "categoria": "tratamientos",
        "titulo": "Duración estimada del tratamiento de ortodoncia",
        "contenido": "La duración del tratamiento varía según la complejidad, alineación y mordida de cada paciente, situándose habitualmente entre 12 y 24 meses. El tiempo exacto y la planificación digital personalizada se definen y entregan en la cita de devolución, luego de la primera consulta de diagnóstico ($50.000)."
    },
    {
        "categoria": "estudios",
        "titulo": "Estudios radiográficos y radiografías previas",
        "contenido": "No es obligatorio traer estudios ni radiografías a la primera consulta. Durante la cita, la Dra. Raquel realiza la evaluación clínica, toma fotografías diagnósticas y entrega la orden médica específica para los estudios que hagan falta (panorámica, telerradiografía). Si el paciente ya cuenta con radiografías recientes, puede traerlas para revisarlas en la consulta ($50.000)."
    },
    {
        "categoria": "tratamientos",
        "titulo": "Tratamientos iniciados o brackets de otro odontólogo",
        "contenido": "Para pacientes que ya tienen brackets o aparatología colocada por otro profesional y desean continuar su atención con la Dra. Raquel, es indispensable realizar una primera consulta de evaluación ($50.000). En dicha cita, la Dra. revisa el estado actual del aparato, el cementado y la salud dental para determinar si es viable continuar el caso o readecuar el plan de tratamiento."
    }
]

def get_embedding(text):
    req = urllib.request.Request(
        "https://api.openai.com/v1/embeddings",
        data=json.dumps({"model": "text-embedding-3-small", "dimensions": 1536, "input": text}).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())["data"][0]["embedding"]

def main():
    host = env("SUPABASE_V3_DB_HOST")
    port = env("SUPABASE_V3_DB_PORT")
    db = env("SUPABASE_V3_DB_NAME")
    user = env("SUPABASE_V3_DB_USER")
    pwd = env("SUPABASE_V3_DB_PASSWORD")

    conn = psycopg2.connect(host=host, port=port, dbname=db, user=user, password=pwd, sslmode="require")
    conn.autocommit = True
    cur = conn.cursor()

    print("── Insertando respuestas blindadas en knowledge_base ──\n")
    for item in NUEVOS_HUECOS:
        cat = item["categoria"]
        tit = item["titulo"]
        cont = item["contenido"]

        # Verificar si ya existe para evitar duplicar
        cur.execute("SELECT id FROM knowledge_base WHERE titulo = %s LIMIT 1;", (tit,))
        row = cur.fetchone()
        
        text_to_embed = f"{cat} | {tit}\n{cont}"
        vec = get_embedding(text_to_embed)
        vec_str = "[" + ",".join(map(str, vec)) + "]"

        if row:
            kb_id = row[0]
            cur.execute("""
                UPDATE knowledge_base
                SET categoria = %s, contenido = %s, embedding = %s::vector
                WHERE id = %s;
            """, (cat, cont, vec_str, kb_id))
            print(f"  ✓ [ACTUALIZADO id={kb_id}] {tit}")
        else:
            cur.execute("""
                INSERT INTO knowledge_base (categoria, titulo, contenido, embedding, metadata)
                VALUES (%s, %s, %s, %s::vector, '{}'::jsonb)
                RETURNING id;
            """, (cat, tit, cont, vec_str))
            new_id = cur.fetchone()[0]
            print(f"  ✓ [INSERTADO id={new_id}] {tit}")

    cur.execute("SELECT count(*) FROM knowledge_base;")
    total = cur.fetchone()[0]
    print(f"\n✅ Total filas en knowledge_base: {total}")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
