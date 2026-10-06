# -*- coding: utf-8 -*-
"""
analizar_conversaciones_reales.py — Analiza los ~9.000 mensajes reales de pacientes en Supabase.
Mapea el flujo conversacional real, detecta:
1. Mensajes de apertura (primer mensaje del paciente)
2. Fricciones reales (cuando piden 'secretaria', 'humano', se quejan, o el bot se colgó)
3. Distribución de intenciones de los pacientes
4. Cuándo el bot resolvió vs cuándo tuvo que intervenir la secretaria
"""
import psycopg2, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env

def main():
    conn = psycopg2.connect(
        host=env("SUPABASE_V3_DB_HOST"), port=env("SUPABASE_V3_DB_PORT"),
        dbname=env("SUPABASE_V3_DB_NAME"), user=env("SUPABASE_V3_DB_USER"),
        password=env("SUPABASE_V3_DB_PASSWORD"), sslmode="require"
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT session_id, message->>'type' as tipo, message->>'content' as content, id
        FROM n8n_chat_histories
        ORDER BY session_id, id ASC;
    """)
    rows = cur.fetchall()
    conn.close()

    sesiones = defaultdict(list)
    for s_id, tipo, content, mid in rows:
        if content:
            sesiones[s_id].append({"id": mid, "tipo": tipo, "content": content.strip()})

    total_sesiones = len(sesiones)
    primeros_mensajes = []
    pedidos_humano = []
    urgencias = []
    turnos_nuevos = []
    reprogramaciones = []
    precios_pagos = []
    solo_saludos = []

    patron_saludo = re.compile(r"^(hola|buenas?|buen d[ií]a|buenas tardes|buenas noches|holaa+)\b[!.\s]*$", re.I)
    patron_humano = re.compile(r"(secretaria|humano|persona|hablar con alguien|atienda alguien|doctora|raquel|iri)", re.I)
    patron_urgencia = re.compile(r"(pincha|alambre|bracket|urgenc|dolor|sangr|molest|lastim|se me sali|se rompi|se cay|despeg)", re.I)
    patron_turno = re.compile(r"(turno|agend|cita|consulta|primer|evaluaci)", re.I)
    patron_reprog = re.compile(r"(cambi|reprogram|mover|pospon|otro d[ií]a|otra hora|no voy a poder|no puedo ir|cancel)", re.I)
    patron_precio = re.compile(r"(precio|cuanto|costo|valor|alias|cbu|transfer|abon|pag)", re.I)

    for sid, msgs in sesiones.items():
        user_msgs = [m for m in msgs if m["tipo"] == "human"]
        if not user_msgs:
            continue
        
        primer_msg = user_msgs[0]["content"]
        primeros_mensajes.append(primer_msg)

        # Evaluar intencion del primer mensaje
        if patron_saludo.match(primer_msg):
            solo_saludos.append(primer_msg)
        elif patron_urgencia.search(primer_msg):
            urgencias.append(primer_msg)
        elif patron_reprog.search(primer_msg):
            reprogramaciones.append(primer_msg)
        elif patron_turno.search(primer_msg):
            turnos_nuevos.append(primer_msg)
        elif patron_precio.search(primer_msg):
            precios_pagos.append(primer_msg)

        # Friccion: pidieron humano en algun punto
        for m in user_msgs:
            if patron_humano.search(m["content"]):
                pedidos_humano.append((sid, m["content"]))
                break

    print(f"==================================================")
    print(f"ANÁLISIS DE DATOS REALES (MÉTODO KARPATHY / DATA-DRIVEN)")
    print(f"Total Sesiones Analizadas: {total_sesiones}")
    print(f"Total Mensajes Analizados: {len(rows)}")
    print(f"==================================================\n")

    print(f"📊 DISTRIBUCIÓN DEL PRIMER MENSAJE (CÓMO ARRANCAN LOS PACIENTES):")
    print(f"1. Saludos puros ('hola', 'buenas'):       {len(solo_saludos)} ({round(len(solo_saludos)/len(primeros_mensajes)*100, 1)}%)")
    print(f"2. Pedido de turno nuevo / consulta:       {len(turnos_nuevos)} ({round(len(turnos_nuevos)/len(primeros_mensajes)*100, 1)}%)")
    print(f"3. Consultas de precios / pagos / alias:   {len(precios_pagos)} ({round(len(precios_pagos)/len(primeros_mensajes)*100, 1)}%)")
    print(f"4. Urgencias (alambre, bracket, dolor):    {len(urgencias)} ({round(len(urgencias)/len(primeros_mensajes)*100, 1)}%)")
    print(f"5. Reprogramación o cancelación de cita:   {len(reprogramaciones)} ({round(len(reprogramaciones)/len(primeros_mensajes)*100, 1)}%)")
    
    print(f"\n🚨 FRICCIONES DETECTADAS (PACIENTE PIDIÓ HUMANO / SECRETARIA):")
    print(f"Total sesiones que pidieron humano: {len(pedidos_humano)} ({round(len(pedidos_humano)/total_sesiones*100, 1)}% de las sesiones)")
    print("Muestra de pedidos de humano:")
    for sid, text in pedidos_humano[:8]:
        print(f"  - '{text[:90]}'")

    print(f"\n💡 TOP 10 MENSAJES DE APERTURA TEXTUALES MÁS COMUNES:")
    top_aperturas = Counter([m.lower().strip() for m in primeros_mensajes]).most_common(10)
    for text, count in top_aperturas:
        print(f"  [{count} veces] '{text}'")

if __name__ == "__main__":
    main()
