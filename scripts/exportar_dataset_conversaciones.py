# -*- coding: utf-8 -*-
"""
exportar_dataset_conversaciones.py — Extrae las conversaciones reales de Supabase,
las limpia y genera un reporte estructurado y dataset JSON listo para análisis profundo.
"""
import psycopg2, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_env import env

ROOT = Path(__file__).resolve().parent.parent

def main():
    conn = psycopg2.connect(
        host=env("SUPABASE_V3_DB_HOST"), port=env("SUPABASE_V3_DB_PORT"),
        dbname=env("SUPABASE_V3_DB_NAME"), user=env("SUPABASE_V3_DB_USER"),
        password=env("SUPABASE_V3_DB_PASSWORD"), sslmode="require"
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT session_id, message->>'type' as role, message->>'content' as content, id
        FROM n8n_chat_histories
        ORDER BY session_id, id ASC;
    """)
    rows = cur.fetchall()
    conn.close()

    sesiones = defaultdict(list)
    for s_id, role, content, mid in rows:
        if content and content.strip():
            sesiones[s_id].append({
                "id": mid,
                "role": role,
                "text": content.strip()
            })

    # Filtrar sesiones de prueba (Lucas admin, Dra, Irina)
    admins = {"5491161461034", "5493513976787", "5493885786946"}
    dataset = []

    patron_intents = {
        "agendar_nuevo": re.compile(r"\b(turno|cita|consulta|agendar|primer|atenci[oó]n|cu[aá]ndo tiene)\b", re.I),
        "urgencia_dolor": re.compile(r"\b(dolor|sangr|pincha|alambre|bracket|urgenc|molest|lastim|despeg|cay[oó]|zaf[oó])\b", re.I),
        "cancelar_reprogramar": re.compile(r"\b(cambi|reprogram|mover|pospon|otro d[ií]a|no voy a poder|no puedo ir|cancel)\b", re.I),
        "confirmar_cita": re.compile(r"\b(confirmo|confirmado|asistir[eé]|s[ií] voy|dale voy)\b", re.I),
        "precios_pagos": re.compile(r"\b(precio|cu[aá]nto|costo|valor|alias|cbu|transfer|abon|comprobante|pag)\b", re.I),
        "obras_sociales": re.compile(r"\b(obra social|isj|instituto|osde|swiss|reintegro|factura)\b", re.I),
        "seguimiento_clinico": re.compile(r"\b(alineador|curcuma|frenillo|retenedor|microimplante|tomar|calmante|perno)\b", re.I)
    }

    stats = {
        "total_sesiones_reales": 0,
        "total_mensajes": 0,
        "distribucion_intents": Counter(),
        "fricciones_escaladas": 0,
        "longitudes_sesion": []
    }

    for sid, msgs in sesiones.items():
        if sid in admins:
            continue
        
        user_msgs = [m for m in msgs if m["role"] == "human"]
        if not user_msgs:
            continue

        stats["total_sesiones_reales"] += 1
        stats["total_mensajes"] += len(msgs)
        stats["longitudes_sesion"].append(len(msgs))

        # Clasificar la intencion principal de la conversacion
        intents_detectados = set()
        for um in user_msgs:
            t = um["text"]
            for intent, pat in patron_intents.items():
                if pat.search(t):
                    intents_detectados.add(intent)

        for it in intents_detectados:
            stats["distribucion_intents"][it] += 1

        # Detectar si intervino humano o escalo
        tiene_humano = any("[ATENCION HUMANA" in m["text"] or "Irina" in m["text"] for m in msgs)
        if tiene_humano:
            stats["fricciones_escaladas"] += 1

        dataset.append({
            "session_id": sid,
            "total_mensajes": len(msgs),
            "intents": list(intents_detectados),
            "intervino_humano": tiene_humano,
            "dialogo": msgs[:12] # primeros 12 turnos para contexto
        })

    # Guardar archivo json estructurado
    out_file = ROOT / "docs" / "dataset_conversaciones_reales.json"
    out_file.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"==================================================")
    print(f"ANÁLISIS GLOBAL DE PACIENTES REALES (ÁUREA)")
    print(f"Total Pacientes/Sesiones Reales: {stats['total_sesiones_reales']}")
    print(f"Total Mensajes Reales:           {stats['total_mensajes']}")
    print(f"Sesiones donde intervino Humano: {stats['fricciones_escaladas']} ({round(stats['fricciones_escaladas']/stats['total_sesiones_reales']*100, 1)}%)")
    print(f"==================================================\n")

    print(f"🔥 CLUSTERING DE INTENCIONES DE LOS PACIENTES:")
    for intent, count in stats["distribucion_intents"].most_common():
        pct = round(count / stats['total_sesiones_reales'] * 100, 1)
        print(f"  • {intent.ljust(22)}: {str(count).rjust(3)} pacientes ({pct}%)")

    print(f"\n📁 Dataset exportado con éxito a: docs/dataset_conversaciones_reales.json")

if __name__ == "__main__":
    main()
