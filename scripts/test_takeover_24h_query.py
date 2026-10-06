import psycopg2
from lib_env import env

conn = psycopg2.connect(
    host=env('SUPABASE_V3_DB_HOST'), port=env('SUPABASE_V3_DB_PORT'),
    dbname=env('SUPABASE_V3_DB_NAME'), user=env('SUPABASE_V3_DB_USER'),
    password=env('SUPABASE_V3_DB_PASSWORD'), sslmode='require', connect_timeout=5
)
cur = conn.cursor()
sql = 'SELECT (human_takeover = true AND human_takeover_at > now() - interval \'24 hours\') AS "hasHumanoLabel" FROM pacientes WHERE telefono = %s LIMIT 1;'
cur.execute(sql, ('5491161461034',))
print("Resultado del query:", cur.fetchall())
cur.close()
conn.close()
