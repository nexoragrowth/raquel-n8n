import psycopg2, sys
from lib_env import env

sys.stdout.reconfigure(encoding="utf-8")

conn = psycopg2.connect(
    host=env('SUPABASE_V3_DB_HOST'), port=env('SUPABASE_V3_DB_PORT'),
    dbname=env('SUPABASE_V3_DB_NAME'), user=env('SUPABASE_V3_DB_USER'),
    password=env('SUPABASE_V3_DB_PASSWORD'), sslmode='require', connect_timeout=5
)
cur = conn.cursor()
cur.execute("""
    SELECT id, categoria, titulo, contenido 
    FROM knowledge_base 
    WHERE contenido ILIKE '%dentalink%' 
       OR contenido ILIKE '%amarillo%' 
       OR contenido ILIKE '%sin limite%' 
       OR contenido ILIKE '%/bot%' 
       OR contenido ILIKE '%irina%'
       OR contenido ILIKE '%iri%'
       OR contenido ILIKE '%plazo maximo%'
    ORDER BY id ASC;
""")
rows = cur.fetchall()
print(f"Total filas contaminadas detectadas: {len(rows)}\n")
for r in rows:
    print(f"=== ID={r[0]} | Cat={r[1]} | Título={r[2]} ===")
    print(r[3].strip())
    print("\n" + "="*50 + "\n")
cur.close()
conn.close()
