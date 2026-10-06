import psycopg2
from lib_env import env

conn = psycopg2.connect(
    host=env("SUPABASE_V3_DB_HOST"), port=env("SUPABASE_V3_DB_PORT"),
    dbname=env("SUPABASE_V3_DB_NAME"), user=env("SUPABASE_V3_DB_USER"),
    password=env("SUPABASE_V3_DB_PASSWORD"), sslmode="require", connect_timeout=5
)
cur = conn.cursor()
cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default 
    FROM information_schema.columns 
    WHERE table_name = 'pacientes'
    ORDER BY ordinal_position;
""")
for r in cur.fetchall():
    print(r)

print("\n--- SAMPLE PACIENTE CON TELEFONO ---")
cur.execute("SELECT id, telefono, nombre, human_takeover FROM pacientes LIMIT 5;")
for r in cur.fetchall():
    print(r)

cur.close()
conn.close()
